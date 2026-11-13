#!/usr/bin/env python3
"""LeapVPN server agent — runs on every VPN VM.

Deallocates its own VM as soon as no device holds a session lease.

Leases are blobs in the `leases` container, named `<region>/<device>`. A client
writes its lease *before* it starts the VM and rewrites it every ~45 s while it
is connected; the blob's server-side Last-Modified time is the heartbeat. A
lease older than LEASE_TTL is dead (crashed app, sleeping laptop, lost network).

The agent also keeps the WireGuard peer list in sync with `config/peers.json`.

Home exits: a machine on a residential connection (e.g. a Windows PC at home)
keeps an outbound `ssh -R 127.0.0.1:<port>` open to this VM, which turns that
machine into a SOCKS proxy reachable on the VM's loopback. Exits are described
by blobs `exits/<region>/<id>.json`; for each one the agent authorises its SSH
key (remote forwarding to its own port only, no shell) and runs tun2socks on a
`vx<port>` tun device. A device that wants to leave through a home exit says so
in its lease's `exit` metadata, and the agent policy-routes that device's
traffic into the tun. Home exits never keep the VM alive: only leases do.

Standard library only. Identity comes from the VM's managed identity via IMDS.
"""
from __future__ import annotations

import email.utils
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from email.utils import parsedate_to_datetime

IMDS = "http://169.254.169.254/metadata"
ARM = "https://management.azure.com"
LEASE_TTL = int(os.environ.get("LEAPVPN_LEASE_TTL", "180"))
IDLE_DEBOUNCE = int(os.environ.get("LEAPVPN_IDLE_DEBOUNCE", "45"))
# A lease only keeps the VM up while its device's tunnel is alive: clients send a
# keepalive every 25 s, so WireGuard re-handshakes at least every ~2 minutes.
HANDSHAKE_MAX = int(os.environ.get("LEAPVPN_HANDSHAKE_MAX", "300"))
CONNECT_GRACE = int(os.environ.get("LEAPVPN_CONNECT_GRACE", "300"))
ERROR_LIMIT = int(os.environ.get("LEAPVPN_ERROR_LIMIT", "600"))
INTERVAL = 15
PEER_SYNC_EVERY = 60
STATUS_PATH = "/run/leapvpn/status.json"
WG_IF = "wg0"

EXIT_USER = "leapexit"
EXIT_PORTS = range(10801, 10900)
RULE_DNS, RULE_EXIT = 1000, 1100
BLACKHOLE_TABLE = 10799  # devices whose chosen home exit is not ready: never fall back to Azure
TUN2SOCKS = "/opt/leapvpn/tun2socks"
TUN2SOCKS_URL = ("https://github.com/xjasonlyu/tun2socks/releases/download/v2.7.0/"
                 "tun2socks-linux-amd64.zip")
TUN2SOCKS_SHA256 = "a612baa287a3b6de6221f74fd02b442a50888508227ecf51e1288a5ccbb77381"
EXIT_UNIT = """[Unit]
Description=LeapVPN home exit on port %i
After=network-online.target

[Service]
ExecStartPre=-/sbin/ip link del vx%i
ExecStart=/opt/leapvpn/tun2socks --device tun://vx%i --proxy socks5://127.0.0.1:%i --loglevel warning
ExecStartPost=/bin/sh -c 'for n in $$(seq 100); do ip link show vx%i >/dev/null 2>&1 \
&& break; sleep 0.1; done; ip link set vx%i up; sysctl -qw net.ipv4.conf.vx%i.rp_filter=0; \
ip route replace default dev vx%i table %i'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
SSHD_DROPIN = f"""Match User {EXIT_USER}
    AllowTcpForwarding remote
    GatewayPorts no
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    AllowStreamLocalForwarding no
    PermitTunnel no
    ForceCommand /bin/false
"""

_tokens: dict[str, tuple[str, float]] = {}
_device_ips: dict[str, str] = {}   # device name -> tunnel IPv4, from peers.json
_device_keys: dict[str, str] = {}  # device name -> WireGuard public key
_exit_keys: dict[int, str] = {}    # exit port -> SSH key authorised for it
_dead_logged: set[str] = set()
_exit_ports: dict[str, int] = {}   # exit id -> loopback SOCKS port on this VM
_routes: dict[str, int] = {}       # device IPv4 -> routing table (exit port) applied


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%S ") + msg, flush=True)


def http(method: str, url: str, headers: dict | None = None,
         body: bytes | None = None, timeout: int = 20):
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers), resp.read()


def imds_instance() -> dict:
    _, _, raw = http("GET", f"{IMDS}/instance?api-version=2021-02-01",
                     {"Metadata": "true"})
    return json.loads(raw)


def token(resource: str) -> str:
    cached = _tokens.get(resource)
    if cached and cached[1] - time.time() > 300:
        return cached[0]
    url = (f"{IMDS}/identity/oauth2/token?api-version=2018-02-01"
           f"&resource={urllib.request.quote(resource, safe='')}")
    _, _, raw = http("GET", url, {"Metadata": "true"})
    data = json.loads(raw)
    _tokens[resource] = (data["access_token"], float(data["expires_on"]))
    return data["access_token"]


def storage_headers() -> dict:
    return {"Authorization": "Bearer " + token("https://storage.azure.com/"),
            "x-ms-version": "2021-08-06"}


def active_leases(account: str, region: str) -> tuple[dict[str, str], float]:
    """Return ({active device name: requested exit id or ""}, server time) for this region.

    A lease whose device has not completed a WireGuard handshake recently is ignored
    once the lease is older than CONNECT_GRACE: the app is alive but its tunnel is not.
    """
    url = (f"https://{account}.blob.core.windows.net/leases?restype=container"
           f"&comp=list&include=metadata&prefix={region}/")
    _, headers, raw = http("GET", url, storage_headers())
    now = parsedate_to_datetime(headers["Date"]).timestamp()
    active = {}
    for blob in ET.fromstring(raw).iter("Blob"):
        name = blob.findtext("Name") or ""
        modified = blob.findtext("Properties/Last-Modified")
        if not modified:
            continue
        age = now - parsedate_to_datetime(modified).timestamp()
        if age >= LEASE_TTL:
            continue
        device = name.split("/", 1)[-1]
        created = blob.findtext("Properties/Creation-Time")
        lease_age = now - parsedate_to_datetime(created).timestamp() if created else 0
        if device.startswith("_") or tunnel_alive(device) or lease_age < CONNECT_GRACE:
            active[device] = blob.findtext("Metadata/exit") or ""
            _dead_logged.discard(device)
        elif device not in _dead_logged:
            log(f"lease from {device} ignored: no WireGuard handshake in {HANDSHAKE_MAX}s")
            _dead_logged.add(device)
    return active, now


def tunnel_alive(device: str) -> bool:
    key = _device_keys.get(device)
    last = handshakes().get(key, 0) if key else 0
    return last > 0 and time.time() - last < HANDSHAKE_MAX


def sync_peers(account: str) -> int:
    url = f"https://{account}.blob.core.windows.net/config/peers.json"
    _, _, raw = http("GET", url, storage_headers())
    desired = {p["pubkey"]: p for p in json.loads(raw).get("peers", [])}
    _device_ips.clear()
    _device_ips.update({p["name"]: p["ip4"] for p in desired.values()})
    _device_keys.clear()
    _device_keys.update({p["name"]: p["pubkey"] for p in desired.values()})
    current = subprocess.run(["wg", "show", WG_IF, "peers"], check=True,
                             capture_output=True, text=True).stdout.split()
    for pub in current:
        if pub not in desired:
            subprocess.run(["wg", "set", WG_IF, "peer", pub, "remove"], check=True)
    for pub, peer in desired.items():
        allowed = f"{peer['ip4']}/32,{peer['ip6']}/128"
        subprocess.run(["wg", "set", WG_IF, "peer", pub, "allowed-ips", allowed],
                       check=True)
    return len(desired)


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def write_if_changed(path: str, content: str, mode: int = 0o644) -> bool:
    try:
        if open(path).read() == content:
            return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    return True


def ensure_tun2socks() -> None:
    if os.path.exists(TUN2SOCKS):
        return
    _, _, raw = http("GET", TUN2SOCKS_URL, timeout=60)
    if hashlib.sha256(raw).hexdigest() != TUN2SOCKS_SHA256:
        raise RuntimeError("tun2socks download failed its checksum")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        member = next(n for n in zf.namelist() if n.startswith("tun2socks"))
        data = zf.read(member)
    with open(TUN2SOCKS + ".tmp", "wb") as fh:
        fh.write(data)
    os.chmod(TUN2SOCKS + ".tmp", 0o755)
    os.replace(TUN2SOCKS + ".tmp", TUN2SOCKS)
    log("tun2socks installed")


def sync_exits(account: str, region: str) -> int:
    """Make this VM's home exits match `exits/<region>/*.json`."""
    url = (f"https://{account}.blob.core.windows.net/exits?restype=container"
           f"&comp=list&prefix={region}/")
    try:
        _, _, raw = http("GET", url, storage_headers())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raw = b"<EnumerationResults/>"
        else:
            raise
    # Exits register themselves through a single-blob invite SAS, so treat the
    # contents as untrusted: the id must match the blob name, keys must be ed25519,
    # and if two exits claim a port the older blob (server-side creation time) wins.
    blobs = sorted(((b.findtext("Properties/Creation-Time") or "", b.findtext("Name") or "")
                    for b in ET.fromstring(raw).iter("Blob")),
                   key=lambda t: email.utils.parsedate_to_datetime(t[0]).timestamp() if t[0] else 0)
    exits, taken = {}, set()
    for _, name in blobs:
        try:
            _, _, body = http("GET", f"https://{account}.blob.core.windows.net/exits/{name}",
                              storage_headers())
            ex = json.loads(body)
            port, key = int(ex.get("port", 0)), str(ex.get("sshPublicKey") or "").strip()
        except (urllib.error.URLError, ValueError, TypeError, AttributeError) as exc:
            log(f"exit {name}: unreadable ({exc})")
            continue
        eid = str(ex.get("id", ""))
        if not key:
            continue  # invite issued, PC not set up yet
        if (name != f"{region}/{eid}.json" or not re.fullmatch(r"[a-z0-9-]{1,40}", eid)
                or port not in EXIT_PORTS or port in taken
                or not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]{60,80}( [\x21-\x7e]{0,64})?", key)):
            log(f"exit {name}: rejected")
            continue
        taken.add(port)
        exits[eid] = (port, key.split()[0] + " " + key.split()[1])

    unit_changed = False
    if exits:
        ensure_tun2socks()
        if run("id", EXIT_USER, check=False).returncode != 0:
            run("useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", EXIT_USER)
        if write_if_changed("/etc/ssh/sshd_config.d/60-leapexit.conf", SSHD_DROPIN):
            run("systemctl", "reload", "ssh", check=False)
        unit_changed = write_if_changed("/etc/systemd/system/leapvpn-exit@.service", EXIT_UNIT)
        run("systemctl", "daemon-reload")
    keys = "".join(f'restrict,port-forwarding,permitlisten="127.0.0.1:{p}",'
                   f'command="/bin/false" {k} leapvpn-exit-{i}\n'
                   for i, (p, k) in sorted(exits.items()))
    home = f"/home/{EXIT_USER}"
    if os.path.isdir(home):
        ak = f"{home}/.ssh/authorized_keys"
        if write_if_changed(ak, keys, 0o600):
            run("chown", "-R", f"{EXIT_USER}:{EXIT_USER}", f"{home}/.ssh")
            os.chmod(f"{home}/.ssh", 0o700)

    wanted = {p for p, _ in exits.values()}
    units = run("systemctl", "list-units", "--all", "--plain", "--no-legend",
                "leapvpn-exit@*", check=False).stdout
    for port in {int(m) for m in re.findall(r"leapvpn-exit@(\d+)\.service", units)} - wanted:
        run("systemctl", "disable", "--now", f"leapvpn-exit@{port}", check=False)
    # A removed (or re-issued) exit must lose its live SSH session too, not just its key.
    keyed = {p: k for p, k in exits.values()}
    for port in set(_exit_keys) | set(keyed):
        if _exit_keys.get(port) and _exit_keys.get(port) != keyed.get(port):
            kill_listener(port)
    _exit_keys.clear()
    _exit_keys.update(keyed)
    for port in wanted:
        if unit_changed:
            run("systemctl", "restart", f"leapvpn-exit@{port}", check=False)
        elif run("systemctl", "is-active", f"leapvpn-exit@{port}", check=False).stdout.strip() != "active":
            run("systemctl", "enable", "--now", f"leapvpn-exit@{port}", check=False)
    _exit_ports.clear()
    _exit_ports.update({i: p for i, (p, _) in exits.items()})
    return len(exits)


def kill_listener(port: int) -> None:
    out = run("ss", "-Hltnp", f"sport = :{port}", check=False).stdout
    for pid in {int(p) for p in re.findall(r"pid=(\d+)", out)}:
        try:
            os.kill(pid, 15)
            log(f"exit port {port}: revoked session (pid {pid}) closed")
        except OSError:
            pass


def clear_rules() -> None:
    for prio in (RULE_DNS, RULE_EXIT):
        while run("ip", "-4", "rule", "del", "priority", str(prio), check=False).returncode == 0:
            pass


def apply_routes(active: dict[str, str]) -> None:
    """Send each leased device that asked for a home exit into that exit's tun.

    DNS stays on the VM's own uplink (SOCKS over SSH carries TCP only); other UDP
    such as QUIC is rejected by the firewall so apps fall back to TCP.
    """
    desired = {}
    for device, exit_id in active.items():
        ip = _device_ips.get(device)
        if ip and exit_id:
            desired[ip] = _exit_ports.get(exit_id, BLACKHOLE_TABLE)
    if desired == _routes:
        return
    for ip, port in list(_routes.items()):
        if desired.get(ip) != port:
            run("ip", "-4", "rule", "del", "from", f"{ip}/32", "priority", str(RULE_EXIT), check=False)
            run("ip", "-4", "rule", "del", "from", f"{ip}/32", "ipproto", "udp", "dport", "53",
                "priority", str(RULE_DNS), check=False)
            del _routes[ip]
    for ip, port in desired.items():
        if ip not in _routes:
            run("ip", "-4", "rule", "add", "from", f"{ip}/32", "ipproto", "udp", "dport", "53",
                "lookup", "main", "priority", str(RULE_DNS))
            run("ip", "-4", "rule", "add", "from", f"{ip}/32", "lookup", str(port),
                "priority", str(RULE_EXIT))
            _routes[ip] = port
    run("ip", "route", "flush", "cache", check=False)
    log(f"home-exit routes: {desired or 'none'}")


def handshakes() -> dict[str, int]:
    out = subprocess.run(["wg", "show", WG_IF, "latest-handshakes"],
                         capture_output=True, text=True).stdout
    result = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            result[parts[0]] = int(parts[1])
    return result


def deallocate(resource_id: str) -> None:
    url = f"{ARM}{resource_id}/deallocate?api-version=2024-07-01"
    status, _, _ = http("POST", url, {
        "Authorization": "Bearer " + token("https://management.azure.com/"),
        "Content-Length": "0"}, body=b"")
    log(f"deallocate requested (HTTP {status})")


def write_status(state: dict) -> None:
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    tmp = STATUS_PATH + ".tmp"
    # Monotonic time + boot id let the deadman measure staleness immune to clock steps.
    with open("/proc/sys/kernel/random/boot_id") as fh:
        state = dict(state, boot_id=fh.read().strip(), mono=time.monotonic())
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATUS_PATH)


def main() -> int:
    meta = imds_instance()["compute"]
    tags = {t["name"]: t["value"] for t in meta.get("tagsList", [])}
    resource_id = meta["resourceId"]
    region = tags["leapvpn-region"]
    account = tags["leapvpn-storage"]
    log(f"agent up: region={region} storage={account} ttl={LEASE_TTL}s")

    started = time.monotonic()
    last_active = started
    last_ok = started
    last_sync = float("-inf")  # monotonic() starts near 0 at boot: sync peers immediately
    clear_rules()
    run("ip", "route", "replace", "blackhole", "default", "table", str(BLACKHOLE_TABLE), check=False)
    run("sysctl", "-qw", "net.ipv4.conf.all.rp_filter=2", check=False)
    while True:
        now = time.monotonic()
        try:
            if now - last_sync >= PEER_SYNC_EVERY:
                count = sync_peers(account)
                last_sync = now
                log(f"peers synced: {count}")
                try:
                    exits = sync_exits(account, region)
                    if exits:
                        log(f"home exits synced: {exits}")
                except Exception as exc:
                    log(f"home exit sync failed: {exc!r}")
            active, _ = active_leases(account, region)
            last_ok = now
            try:
                apply_routes(active)
            except Exception as exc:
                log(f"route update failed: {exc!r}")
            if active:
                last_active = now
            elif now - last_active >= IDLE_DEBOUNCE:
                # Re-check right before stopping: a client may have just leased.
                active, _ = active_leases(account, region)
                if not active:
                    log("no active leases — deallocating this VM")
                    write_status({"state": "deallocating", "region": region})
                    deallocate(resource_id)
                    time.sleep(120)
                    continue
                last_active = now
            write_status({"state": "running", "region": region,
                          "leases": active, "exits": _exit_ports, "routes": _routes,
                          "handshakes": handshakes(),
                          "idleFor": round(now - last_active)})
        except Exception as exc:  # keep running; fail safe below
            log(f"error: {exc!r}")
            if now - last_ok > ERROR_LIMIT:
                log("control plane unreachable too long — deallocating")
                try:
                    deallocate(resource_id)
                except Exception as exc2:
                    log(f"deallocate failed: {exc2!r}")
                last_ok = now
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
