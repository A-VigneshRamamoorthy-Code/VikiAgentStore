#!/usr/bin/env python3
"""Aven VPN server agent — runs on every VPN VM.

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
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from email.utils import parsedate_to_datetime

IMDS = "http://169.254.169.254/metadata"
ARM = "https://management.azure.com"
LEASE_TTL = int(os.environ.get("AVENVPN_LEASE_TTL", "180"))
IDLE_DEBOUNCE = int(os.environ.get("AVENVPN_IDLE_DEBOUNCE", "45"))
# A lease only keeps the VM up while its device's tunnel is alive: clients send a
# keepalive every 25 s, so WireGuard re-handshakes at least every ~2 minutes.
HANDSHAKE_MAX = int(os.environ.get("AVENVPN_HANDSHAKE_MAX", "300"))
CONNECT_GRACE = int(os.environ.get("AVENVPN_CONNECT_GRACE", "300"))
ERROR_LIMIT = int(os.environ.get("AVENVPN_ERROR_LIMIT", "600"))
INTERVAL = 15
HEARTBEAT = "_agent"
HEARTBEAT_EVERY = 60
PEER_SYNC_EVERY = 60
STATUS_PATH = "/run/avenvpn/status.json"
WG_IF = "wg0"

EXIT_USER = "avenexit"
EXIT_PORTS = range(10801, 10900)
RULE_DNS, RULE_EXIT = 1000, 1100
# Ad blocking: devices whose lease carries `adblock=1` have their DNS redirected to dnsmasq
# on the tunnel address, which answers NXDOMAIN for the oisd.nl "big" list.
DNS_ADDR = "10.66.0.1"
DNS_UNIT = "avenvpn-dns"
DNS_CHAIN, DOT_CHAIN = "AVENVPN_DNS", "AVENVPN_DOT"
BLOCKLIST_URL = "https://big.oisd.nl/dnsmasq2"
BLOCKLIST_PATH = "/var/lib/avenvpn/blocklist.conf"
# Public resolvers whose DNS-over-HTTPS endpoints are reached by IP (DDR, Chrome auto-upgrade).
DOH_RESOLVERS = ("1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112")
BLOCKLIST_MAX_AGE = 24 * 3600
BLOCKLIST_RETRY = 15 * 60
BLOCKLIST_MAX_BYTES = 40 << 20
BLOCKLIST_DEADLINE = 120
BLOCKLIST_MIN_ENTRIES = 20000
BLOCKLIST_LINE = re.compile(r"^local=/((?:[a-z0-9_-]+\.)+[a-z0-9_-]+)/$")
# Never blocked, whatever the list says: streaming playback and Aven VPN's own control plane.
ALLOW_SUFFIXES = (
    "netflix.com", "netflix.net", "nflxvideo.net", "nflximg.net", "nflximg.com", "nflxext.com",
    "nflxso.net", "primevideo.com", "amazonvideo.com", "aiv-cdn.net", "aiv-delivery.net",
    "pv-cdn.net", "media-amazon.com", "ssl-images-amazon.com",
    "login.microsoftonline.com", "management.azure.com", "login.live.com",
)
# Well-known ad and tracking hosts that OISD leaves out to stay breakage-free; blocking them
# only stops ads/analytics (e.g. the Google Publisher Tag loader), never page content.
EXTRA_BLOCK = (
    "googletagservices.com", "google-analytics.com", "ad.doubleclick.net", "scorecardresearch.com",
    "adservice.google.com", "adservice.google.co.in", "app-measurement.com", "samsungads.com",
    "ads.tiktok.com",
)
BLACKHOLE_TABLE = 10799  # devices whose chosen home exit is not ready: never fall back to Azure
TUN2SOCKS = "/opt/avenvpn/tun2socks"
TUN2SOCKS_URL = ("https://github.com/xjasonlyu/tun2socks/releases/download/v2.7.0/"
                 "tun2socks-linux-amd64.zip")
TUN2SOCKS_SHA256 = "a612baa287a3b6de6221f74fd02b442a50888508227ecf51e1288a5ccbb77381"
EXIT_UNIT = """[Unit]
Description=Aven VPN home exit on port %i
After=network-online.target

[Service]
ExecStartPre=-/sbin/ip link del vx%i
ExecStart=/opt/avenvpn/tun2socks --device tun://vx%i --proxy socks5://127.0.0.1:%i --loglevel warning
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
_adblock: set[str] = set()         # devices whose current lease asks for ad blocking
_dns_applied: set[str] | None = None  # device IPv4s redirected to the ad-blocking resolver
_blocklist_tried = float("-inf")
_blocklist_thread: threading.Thread | None = None


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
    adblock = set()
    for blob in ET.fromstring(raw).iter("Blob"):
        name = blob.findtext("Name") or ""
        modified = blob.findtext("Properties/Last-Modified")
        if not modified:
            continue
        age = now - parsedate_to_datetime(modified).timestamp()
        device = name.split("/", 1)[-1]
        if device == HEARTBEAT:
            continue
        # A live tunnel counts even when its lease went stale: iOS suspends the app
        # (and its renewals) while the tunnel keeps running.
        alive = tunnel_alive(device)
        if age >= LEASE_TTL and not alive:
            continue
        created = blob.findtext("Properties/Creation-Time")
        lease_age = now - parsedate_to_datetime(created).timestamp() if created else 0
        if device.startswith("_") or alive or lease_age < CONNECT_GRACE:
            active[device] = blob.findtext("Metadata/exit") or ""
            if (blob.findtext("Metadata/adblock") or "") == "1":
                adblock.add(device)
            _dead_logged.discard(device)
        elif device not in _dead_logged:
            log(f"lease from {device} ignored: no WireGuard handshake in {HANDSHAKE_MAX}s")
            _dead_logged.add(device)
    _adblock.clear()
    _adblock.update(adblock)
    return active, now


def heartbeat(account: str, region: str, live: bool, devices=()) -> None:
    """Keep leases/<region>/_agent fresh while any tunnel is up, so the app's sweeper
    and the reconciler (which cannot see handshakes) treat the server as in use. It lists
    the devices with a live handshake, so the apps can warn them before a Switch IP."""
    url = f"https://{account}.blob.core.windows.net/leases/{region}/{HEARTBEAT}"
    try:
        if live:
            http("PUT", url, dict(storage_headers(), **{"x-ms-blob-type": "BlockBlob",
                 "Content-Type": "application/json"}), body=json.dumps({"device": "_agent", "live": sorted(devices)}).encode())
        else:
            http("DELETE", url, storage_headers())
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            log(f"heartbeat failed: HTTP {exc.code}")


class RegionLock:
    """The region lock every device shares (leases/_locks/<region>, a 60 s blob lease)."""

    def __init__(self, account: str, region: str):
        self.url = f"https://{account}.blob.core.windows.net/leases/_locks/{region}"
        self.id = None

    def __enter__(self):
        try:
            http("PUT", self.url, dict(storage_headers(), **{"x-ms-blob-type": "BlockBlob",
                 "If-None-Match": "*"}), body=b"{}")
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 412):
                raise
        proposed = hashlib.sha256(os.urandom(16)).hexdigest()[:32]
        proposed = "-".join([proposed[:8], proposed[8:12], proposed[12:16], proposed[16:20], proposed[20:]])
        try:
            http("PUT", self.url + "?comp=lease", dict(storage_headers(), **{
                "x-ms-lease-action": "acquire", "x-ms-lease-duration": "60",
                "x-ms-proposed-lease-id": proposed, "Content-Length": "0"}), body=b"")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return None  # a device is building, joining or cleaning up
            raise
        self.id = proposed
        return self

    def __exit__(self, *_):
        if self.id:
            try:
                http("PUT", self.url + "?comp=lease", dict(storage_headers(), **{
                    "x-ms-lease-action": "release", "x-ms-lease-id": self.id,
                    "Content-Length": "0"}), body=b"")
            except Exception as exc:
                log(f"lock release failed: {exc!r}")
        return False


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
        if write_if_changed("/etc/ssh/sshd_config.d/60-avenexit.conf", SSHD_DROPIN):
            run("systemctl", "reload", "ssh", check=False)
        unit_changed = write_if_changed("/etc/systemd/system/avenvpn-exit@.service", EXIT_UNIT)
        run("systemctl", "daemon-reload")
    keys = "".join(f'restrict,port-forwarding,permitlisten="127.0.0.1:{p}",'
                   f'command="/bin/false" {k} avenvpn-exit-{i}\n'
                   for i, (p, k) in sorted(exits.items()))
    home = f"/home/{EXIT_USER}"
    if os.path.isdir(home):
        ak = f"{home}/.ssh/authorized_keys"
        if write_if_changed(ak, keys, 0o600):
            run("chown", "-R", f"{EXIT_USER}:{EXIT_USER}", f"{home}/.ssh")
            os.chmod(f"{home}/.ssh", 0o700)

    wanted = {p for p, _ in exits.values()}
    units = run("systemctl", "list-units", "--all", "--plain", "--no-legend",
                "avenvpn-exit@*", check=False).stdout
    for port in {int(m) for m in re.findall(r"avenvpn-exit@(\d+)\.service", units)} - wanted:
        run("systemctl", "disable", "--now", f"avenvpn-exit@{port}", check=False)
    # A removed (or re-issued) exit must lose its live SSH session too, not just its key.
    keyed = {p: k for p, k in exits.values()}
    for port in set(_exit_keys) | set(keyed):
        if _exit_keys.get(port) and _exit_keys.get(port) != keyed.get(port):
            kill_listener(port)
    _exit_keys.clear()
    _exit_keys.update(keyed)
    for port in wanted:
        if unit_changed:
            run("systemctl", "restart", f"avenvpn-exit@{port}", check=False)
        elif run("systemctl", "is-active", f"avenvpn-exit@{port}", check=False).stdout.strip() != "active":
            run("systemctl", "enable", "--now", f"avenvpn-exit@{port}", check=False)
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


def allowed(domain: str, account: str) -> bool:
    """True if blocking `domain` would also block something on the allow list."""
    keep = ALLOW_SUFFIXES + (f"{account}.blob.core.windows.net",)
    return any(domain == k or domain.endswith("." + k) or k.endswith("." + domain) for k in keep)


def sync_blocklist(account: str) -> None:
    """Refresh the ad-blocking list once a day (cached on disk across reboots).

    Only well-formed `local=/domain/` lines are kept, so a tampered or truncated
    download can never inject other dnsmasq options or empty the list.
    """
    global _blocklist_tried
    if not os.path.exists("/usr/sbin/dnsmasq"):  # servers built by the CLI: no resolver
        return
    now = time.time()
    # A new agent with a different allow/extra list must not wait a day for the cache to age.
    policy = "# policy " + hashlib.sha256(
        repr((ALLOW_SUFFIXES, EXTRA_BLOCK, account)).encode()).hexdigest()[:16]
    try:
        with open(BLOCKLIST_PATH) as f:
            current = f.readline().strip() == policy
        age = now - os.path.getmtime(BLOCKLIST_PATH) if current else None
    except OSError:
        age = None
    if age is not None and age < BLOCKLIST_MAX_AGE:
        return
    if time.monotonic() - _blocklist_tried < BLOCKLIST_RETRY:
        return
    _blocklist_tried = time.monotonic()
    try:
        raw = download_capped(BLOCKLIST_URL, BLOCKLIST_MAX_BYTES, BLOCKLIST_DEADLINE)
    except Exception as exc:
        log(f"blocklist download failed: {exc!r}")
        return
    kept, dropped = [], 0
    for line in raw.decode("utf-8", "replace").splitlines():
        m = BLOCKLIST_LINE.match(line.strip())
        if not m:
            continue
        if allowed(m.group(1), account):
            dropped += 1
            continue
        kept.append(line.strip())
    if len(kept) < BLOCKLIST_MIN_ENTRIES:
        log(f"blocklist rejected: only {len(kept)} entries")
        return
    listed = set(kept)
    kept += [e for e in (f"local=/{d}/" for d in EXTRA_BLOCK) if e not in listed]
    if write_if_changed(BLOCKLIST_PATH, "\n".join([policy] + kept) + "\n"):
        run("systemctl", "restart", DNS_UNIT, check=False)
        log(f"blocklist updated: {len(kept)} domains ({dropped} allow-listed)")
    else:
        os.utime(BLOCKLIST_PATH)


def download_capped(url: str, max_bytes: int, deadline: float) -> bytes:
    """GET with a total time and size budget (urlopen's timeout is per read only)."""
    end = time.monotonic() + deadline
    req = urllib.request.Request(url, headers={"User-Agent": "AvenVPN"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        chunks, size = [], 0
        while chunk := resp.read(1 << 16):
            size += len(chunk)
            if size > max_bytes or time.monotonic() > end:
                raise RuntimeError("blocklist too large or too slow")
            chunks.append(chunk)
    return b"".join(chunks)


def refresh_blocklist_async(account: str, wanted: bool) -> None:
    """Refresh the list off the control loop, so a slow download never delays a stop.

    Nothing is fetched unless a connected device actually asked for ad blocking.
    """
    global _blocklist_thread
    if not wanted or (_blocklist_thread and _blocklist_thread.is_alive()):
        return

    def work() -> None:
        try:
            sync_blocklist(account)
        except Exception as exc:
            log(f"blocklist refresh failed: {exc!r}")

    _blocklist_thread = threading.Thread(target=work, name="blocklist", daemon=True)
    _blocklist_thread.start()


# A query for the Firefox canary, which dnsmasq answers locally (NXDOMAIN): proves the
# resolver is up and answering without depending on the upstream resolvers.
_PROBE = (b"\x4c\x56\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
          b"\x13use-application-dns\x03net\x00\x00\x01\x00\x01")


def dns_ready() -> bool:
    """True only if dnsmasq actually answers a query within a second."""
    if not os.path.exists(BLOCKLIST_PATH):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            sock.sendto(_PROBE, (DNS_ADDR, 53))
            reply = sock.recv(512)
        return reply[:2] == _PROBE[:2] and bool(reply[2] & 0x80)
    except OSError:
        return False


def forget_dns_flows(ips: set[str]) -> None:
    """Drop tracked DNS flows so a policy change applies to in-flight lookups too."""
    for ip in ips:
        for proto in ("udp", "tcp"):
            run("conntrack", "-D", "-s", ip, "-p", proto, "--dport", "53", check=False)


def apply_dns(active: dict[str, str] | None) -> None:
    """Redirect DNS of ad-blocking devices to dnsmasq; leave everyone else alone.

    Only while dnsmasq is running, so a broken resolver degrades to "no blocking",
    never to "no DNS". Encrypted DNS (DoT, DoQ and DoH to well-known resolver IPs) is
    refused for those devices so Android Private DNS, Apple DDR and Chrome fall back to
    plain DNS, which is then filtered. `active=None` (leases unreadable) keeps the
    current devices but still drops every redirect if the resolver stops answering.
    """
    global _dns_applied
    ready = dns_ready()
    if active is None:
        wanted = set(_dns_applied or ())
    else:
        wanted = {_device_ips[d] for d in active if d in _adblock and d in _device_ips}
    desired = wanted if ready else set()
    if desired == _dns_applied:
        return
    previous = set(_dns_applied or ())
    for table, chain, hook in (("nat", DNS_CHAIN, "PREROUTING"), ("filter", DOT_CHAIN, "FORWARD")):
        run("iptables", "-t", table, "-N", chain, check=False)
        run("iptables", "-t", table, "-F", chain)
        if run("iptables", "-t", table, "-C", hook, "-i", WG_IF, "-j", chain, check=False).returncode:
            run("iptables", "-t", table, "-I", hook, "1", "-i", WG_IF, "-j", chain)
    for ip in sorted(desired):
        for proto in ("udp", "tcp"):
            run("iptables", "-t", "nat", "-A", DNS_CHAIN, "-s", ip, "-p", proto, "--dport", "53",
                "-j", "DNAT", "--to-destination", f"{DNS_ADDR}:53")
        # Encrypted DNS would bypass the filter: DoT/DoQ anywhere, and DoH to the public
        # resolvers' own addresses (what macOS/iOS DDR and Chrome's auto-upgrade use).
        run("iptables", "-A", DOT_CHAIN, "-s", ip, "-p", "tcp", "--dport", "853",
            "-j", "REJECT", "--reject-with", "tcp-reset")
        run("iptables", "-A", DOT_CHAIN, "-s", ip, "-p", "udp", "--dport", "853", "-j", "REJECT")
        for proto in ("tcp", "udp"):
            run("iptables", "-A", DOT_CHAIN, "-s", ip, "-d", ",".join(DOH_RESOLVERS), "-p", proto,
                "--dport", "443", "-j", "REJECT", *(("--reject-with", "tcp-reset") if proto == "tcp" else ()))
    _dns_applied = desired
    forget_dns_flows(previous ^ desired)
    log(f"ad blocking for: {sorted(desired) or 'none'}" + ("" if ready else " (resolver not running)"))


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
    region = tags["avenvpn-region"]
    account = tags["avenvpn-storage"]
    log(f"agent up: region={region} storage={account} ttl={LEASE_TTL}s")

    started = time.monotonic()
    last_active = started
    last_ok = started
    last_beat = float("-inf")
    last_live: list = []
    last_sync = float("-inf")  # monotonic() starts near 0 at boot: sync peers immediately
    connecting = False  # a lease is waiting on its first handshake: maybe a newly registered key
    clear_rules()
    run("ip", "route", "replace", "blackhole", "default", "table", str(BLACKHOLE_TABLE), check=False)
    run("sysctl", "-qw", "net.ipv4.conf.all.rp_filter=2", check=False)
    while True:
        now = time.monotonic()
        try:
            if now - last_sync >= (INTERVAL if connecting else PEER_SYNC_EVERY):
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
            try:
                refresh_blocklist_async(account, any(d in _adblock for d in active))
            except Exception as exc:
                log(f"blocklist refresh failed: {exc!r}")
            try:
                apply_dns(active)
            except Exception as exc:
                log(f"ad blocking update failed: {exc!r}")
            live_devices = sorted(d for d in active if not d.startswith("_") and tunnel_alive(d))
            live = bool(live_devices)
            connecting = any(not d.startswith("_") and d not in live_devices for d in active)
            if live and (now - last_beat >= HEARTBEAT_EVERY or live_devices != last_live):
                heartbeat(account, region, True, live_devices)
                last_beat = now
            last_live = live_devices
            if active:
                last_active = now
            elif now - last_active >= IDLE_DEBOUNCE:
                # Final check under the region lock, so a device that is joining,
                # building or cleaning up is never stopped underneath.
                with RegionLock(account, region) as lock:
                    if lock is None:
                        log("region lock held by a device — not stopping yet")
                        active = {"_lock": ""}
                    else:
                        active, _ = active_leases(account, region)
                        if not active:
                            log("no active leases — deallocating this VM")
                            write_status({"state": "deallocating", "region": region})
                            heartbeat(account, region, False)
                            deallocate(resource_id)
                if not active:
                    time.sleep(120)
                    continue
                last_active = now
            write_status({"state": "running", "region": region,
                          "leases": active, "exits": _exit_ports, "routes": _routes,
                          "adblock": sorted(_dns_applied or ()),
                          "handshakes": handshakes(),
                          "idleFor": round(now - last_active)})
        except Exception as exc:  # keep running; fail safe below
            log(f"error: {exc!r}")
            try:
                apply_dns(None)  # fail open if the resolver died while leases are unreadable
            except Exception as exc2:
                log(f"ad blocking update failed: {exc2!r}")
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
