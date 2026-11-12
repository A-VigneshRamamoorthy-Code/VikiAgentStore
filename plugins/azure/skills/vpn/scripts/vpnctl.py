#!/usr/bin/env python3
"""vpnctl — deploy and operate VikiVPN, an on-demand WireGuard VPN on Azure.

Every region is one small VM that is *deallocated* whenever no device holds a
session lease, so compute is only billed while someone is connected.

    vpnctl.py init                      # storage, roles, client identity (once)
    vpnctl.py deploy --region in nl us ca
    vpnctl.py reconciler                # serverless backstop that deallocates leaks
    vpnctl.py add-device mac            # keys + peer + client configs
    vpnctl.py install-mac mac           # app config + Keychain secrets for the app
    vpnctl.py upgrade [--region in]     # push the current agent/firewall to deployed VMs
    vpnctl.py status                    # power state, leases, cost so far
    vpnctl.py verify-idle               # proof: every VPN VM is deallocated
    vpnctl.py stop [--region in]        # admin deallocate
    vpnctl.py destroy                   # delete everything

Standard library only. Uses the Azure CLI that the `compute` skill installs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
HOME = os.path.expanduser(os.environ.get("VIKIVPN_HOME", "~/.vikivpn"))
STATE_PATH = os.path.join(HOME, "state.json")
APP_SUPPORT = os.path.expanduser("~/Library/Application Support/VikiVPN")
REGIONS = json.load(open(os.path.join(HERE, "regions.json")))

CTL_RG = "vikivpn-ctl"
CTL_LOCATION = "centralindia"
VM_SIZE = os.environ.get("VIKIVPN_VM_SIZE", "Standard_B2ats_v2")
IMAGE = "Canonical:ubuntu-24_04-lts:server:latest"
PORT = 51820
LEASE_TTL = 180
KEYCHAIN_SERVICE = "VikiVPN"
ROLE_STARTER = "VikiVPN Starter"
ROLE_STOPPER = "VikiVPN Stopper"
API = "2024-07-01"


# --------------------------------------------------------------- output ----

def say(msg: str) -> None:
    print(f"\033[36mvpn\033[0m {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    print(f"\033[32mvpn ok\033[0m {msg}", file=sys.stderr, flush=True)


def fail(msg: str) -> None:
    print(f"\033[31mvpn error\033[0m {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# ------------------------------------------------------- IPv4-first DNS ----
# Python has no happy-eyeballs: on networks with a broken IPv6 path every HTTPS
# call stalls for a minute per address. Prefer IPv4 here and inside `az`.

_getaddrinfo = socket.getaddrinfo


def _v4first(*a, **k):
    return sorted(_getaddrinfo(*a, **k), key=lambda r: r[0] != socket.AF_INET)


socket.getaddrinfo = _v4first

AZ_SHIM = """
import socket, runpy, sys
_g = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: sorted(_g(*a, **k), key=lambda r: r[0] != socket.AF_INET)
sys.argv = ["az"] + sys.argv[1:]
runpy.run_module("azure.cli", run_name="__main__", alter_sys=True)
"""


def _az_cmd() -> list[str]:
    path = shutil.which("az")
    if not path:
        fail("Azure CLI not found — run the compute skill's `azc.py doctor` first")
    try:
        text = open(path, errors="ignore").read(4000)
        m = re.search(r"(/\S+/python\S*) -Im azure\.cli", text)
        if m and os.path.exists(m.group(1)):
            return [m.group(1), "-I", "-c", AZ_SHIM]
    except OSError:
        pass
    return [path]


AZ = None
AZ_ENV = {**os.environ, "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
          "AZURE_CORE_NO_COLOR": "true", "AZURE_CORE_COLLECT_TELEMETRY": "false",
          "AZURE_CORE_DISABLE_CONFIRM_PROMPT": "true", "AZURE_CORE_SURVEY_MESSAGE": "no"}


def az(*args: str, parse: bool = True, check: bool = True, timeout: int = 1800):
    global AZ
    AZ = AZ or _az_cmd()
    cmd = AZ + list(args)
    if parse and "-o" not in args and "--output" not in args:
        cmd += ["-o", "json"]
    proc = subprocess.run(cmd, env=AZ_ENV, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        if check:
            fail(f"az {' '.join(args[:4])} failed:\n{(proc.stderr or proc.stdout).strip()}")
        return None
    out = proc.stdout.strip()
    if not parse:
        return out
    return json.loads(out) if out else None


# ---------------------------------------------------------------- state ----

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {"regions": {}, "devices": {}}


_STATE_LOCK = threading.Lock()


def save_state(state: dict) -> None:
    with _STATE_LOCK:
        os.makedirs(HOME, mode=0o700, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, STATE_PATH)


def need_init(state: dict) -> None:
    if not state.get("storage"):
        fail("run `vpnctl.py init` first")


def suffix(n: int = 6) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


# ------------------------------------------------------------- keychain ----

def keychain_get(account: str) -> str | None:
    proc = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                           "-a", account, "-w"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def keychain_set(account: str, secret: str, apps: list[str] | None = None,
                 label: str = "VikiVPN client secret") -> None:
    # Re-create rather than update (-U) so the app access list is replaced too.
    subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account],
                   capture_output=True)
    cmd = ["security", "add-generic-password", "-s", KEYCHAIN_SERVICE,
           "-a", account, "-w", secret, "-l", label]
    for app in apps or []:
        cmd += ["-T", app]
    cmd += ["-T", "/usr/bin/security"]
    subprocess.run(cmd, check=True, capture_output=True)


# -------------------------------------------------------------- storage ----

def user_token(resource: str) -> str:
    return az("account", "get-access-token", "--resource", resource,
              "--query", "accessToken", "-o", "tsv", parse=False)


def blob(method: str, account: str, path: str, body: bytes | None = None,
         token: str | None = None, ctype: str = "application/json"):
    token = token or user_token("https://storage.azure.com/")
    headers = {"Authorization": "Bearer " + token, "x-ms-version": "2021-08-06"}
    if method == "PUT":
        headers.update({"x-ms-blob-type": "BlockBlob", "Content-Type": ctype})
    req = urllib.request.Request(f"https://{account}.blob.core.windows.net/{path}",
                                 data=body if body is not None else (b"" if method == "PUT" else None),
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def blob_retry(method, account, path, body=None, attempts=20):
    """Role assignments take a minute or two to propagate; retry 403s."""
    for i in range(attempts):
        status, data = blob(method, account, path, body)
        if status != 403:
            return status, data
        if i == 0:
            say("waiting for storage role assignment to propagate…")
        time.sleep(15)
    return status, data


class AdminLease:
    """Hold a lease for a region while vpnctl itself needs the VM running."""

    def __init__(self, account: str, region: str):
        self.account, self.path = account, f"leases/{region}/_vpnctl"
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._renew, daemon=True)

    def _put(self):
        blob_retry("PUT", self.account, self.path, b'{"by":"vpnctl"}')

    def _renew(self):
        while not self.stop.wait(45):
            try:
                self._put()
            except Exception as exc:  # noqa: BLE001
                say(f"lease renew failed: {exc}")

    def __enter__(self):
        self._put()
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        blob("DELETE", self.account, self.path)


# ----------------------------------------------------------------- init ----

def ensure_role(name: str, actions: list[str], sub: str) -> None:
    existing = az("role", "definition", "list", "--custom-role-only", "true", "--name", name)
    if existing:
        return
    body = {"Name": name, "IsCustom": True,
            "Description": f"{name} — VikiVPN on-demand VPN",
            "Actions": actions, "NotActions": [],
            "AssignableScopes": [f"/subscriptions/{sub}"]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(body, fh)
    az("role", "definition", "create", "--role-definition", fh.name)
    os.unlink(fh.name)
    ok(f"custom role {name}")


def assign(principal: str, role: str, scope: str, ptype: str = "ServicePrincipal") -> None:
    for i in range(12):
        res = az("role", "assignment", "create", "--assignee-object-id", principal,
                 "--assignee-principal-type", ptype, "--role", role, "--scope", scope,
                 check=False)
        if res is not None:
            return
        time.sleep(10)  # new identities and custom roles replicate slowly
    fail(f"could not assign {role} on {scope}")


def cmd_init(args) -> None:
    state = load_state()
    acct = az("account", "show")
    sub, tenant = acct["id"], acct["tenantId"]
    state.update({"subscription": sub, "tenant": tenant})
    me = az("ad", "signed-in-user", "show", "--query", "id", "-o", "tsv", parse=False)

    ensure_role(ROLE_STARTER, ["Microsoft.Compute/virtualMachines/read",
                               "Microsoft.Compute/virtualMachines/instanceView/read",
                               "Microsoft.Compute/virtualMachines/start/action"], sub)
    ensure_role(ROLE_STOPPER, ["Microsoft.Compute/virtualMachines/read",
                               "Microsoft.Compute/virtualMachines/instanceView/read",
                               "Microsoft.Compute/virtualMachines/deallocate/action"], sub)

    az("group", "create", "-n", CTL_RG, "-l", CTL_LOCATION, "--tags", "vikivpn=1")
    if not state.get("storage"):
        state["storage"] = "vikivpn" + suffix(8)
        save_state(state)
    account = state["storage"]
    if not az("storage", "account", "show", "-n", account, "-g", CTL_RG, check=False):
        say(f"creating storage account {account}")
        az("storage", "account", "create", "-n", account, "-g", CTL_RG, "-l", CTL_LOCATION,
           "--sku", "Standard_LRS", "--kind", "StorageV2", "--min-tls-version", "TLS1_2",
           "--allow-blob-public-access", "false", "--allow-shared-key-access", "false")
    acct_id = az("storage", "account", "show", "-n", account, "-g", CTL_RG,
                 "--query", "id", "-o", "tsv", parse=False)
    state["storageId"] = acct_id
    for container in ("leases", "config", "exits"):
        az("storage", "container-rm", "create", "--storage-account", acct_id, "-n", container,
           "--public-access", "off", check=False)
    assign(me, "Storage Blob Data Contributor", acct_id, "User")

    if not state.get("clientId"):
        say("creating client identity (service principal) for the apps")
        app = az("ad", "sp", "create-for-rbac", "--name", "vikivpn-client", "--years", "2")
        state["clientId"] = app["appId"]
        keychain_set(app["appId"], app["password"])
        save_state(state)
    state["clientObjectId"] = az("ad", "sp", "show", "--id", state["clientId"],
                                 "--query", "id", "-o", "tsv", parse=False)
    assign(state["clientObjectId"], "Storage Blob Data Contributor",
           f"{acct_id}/blobServices/default/containers/leases")
    assign(state["clientObjectId"], "Storage Blob Data Contributor",
           f"{acct_id}/blobServices/default/containers/exits")
    # Home-exit invites are user-delegation SAS URLs; the key can only be issued at account scope.
    assign(state["clientObjectId"], "Storage Blob Delegator", acct_id)
    assign(state["clientObjectId"], "Cost Management Reader", f"/subscriptions/{sub}")

    status, _ = blob_retry("GET", account, "config/peers.json")
    if status == 404:
        blob_retry("PUT", account, "config/peers.json", b'{"peers": []}')
    save_state(state)
    ok(f"initialised: storage={account} client={state['clientId']}")


# --------------------------------------------------------------- deploy ----

def cloud_init() -> str:
    def b64(name: str) -> str:
        return base64.b64encode(open(os.path.join(SKILL, "server", name), "rb").read()).decode()

    return f"""#cloud-config
package_update: true
packages: [wireguard-tools, iptables]
write_files:
  - path: /opt/vikivpn/agent.py
    encoding: b64
    permissions: '0755'
    content: {b64('agent.py')}
  - path: /opt/vikivpn/firewall.sh
    encoding: b64
    permissions: '0755'
    content: {b64('firewall.sh')}
  - path: /etc/systemd/system/vikivpn-agent.service
    encoding: b64
    content: {b64('vikivpn-agent.service')}
  - path: /etc/sysctl.d/90-vikivpn.conf
    content: |
      net.ipv4.ip_forward = 1
runcmd:
  - [sh, -c, 'umask 077; [ -s /etc/wireguard/server.key ] || wg genkey > /etc/wireguard/server.key; wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub; chmod 644 /etc/wireguard/server.pub']
  - [sh, -c, 'umask 077; printf "[Interface]\\nAddress = 10.66.0.1/24, fd66::1/64\\nListenPort = {PORT}\\nPrivateKey = %s\\nPostUp = /opt/vikivpn/firewall.sh up\\nPostDown = /opt/vikivpn/firewall.sh down\\n" "$(cat /etc/wireguard/server.key)" > /etc/wireguard/wg0.conf']
  - sysctl --system
  - systemctl daemon-reload
  - systemctl enable --now wg-quick@wg0
  - systemctl enable --now vikivpn-agent
"""


def run_command(rg: str, vm: str, script: str) -> str:
    res = az("vm", "run-command", "invoke", "-g", rg, "-n", vm, "--command-id",
             "RunShellScript", "--scripts", script)
    return "\n".join(v.get("message", "") for v in res.get("value", []))


def power_state(rg: str, vm: str) -> str:
    view = az("vm", "get-instance-view", "-g", rg, "-n", vm, check=False) or {}
    for s in (view.get("instanceView") or {}).get("statuses", []):
        if s["code"].startswith("PowerState/"):
            return s["code"].split("/", 1)[1]
    return "unknown"


def wait_power(rg: str, vm: str, want: str, timeout: int) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if power_state(rg, vm) == want:
            return True
        time.sleep(10)
    return False


def deploy_region(state: dict, code: str, keys_dir: str) -> None:
    info = REGIONS[code]
    rg, vm = f"vikivpn-{code}", f"vikivpn-{code}"
    account = state["storage"]
    sub = state["subscription"]
    say(f"[{code}] deploying {VM_SIZE} in {info['location']}")
    az("group", "create", "-n", rg, "-l", info["location"], "--tags", "vikivpn=1")

    with AdminLease(account, code):
        exists = az("vm", "show", "-g", rg, "-n", vm, check=False)
        if not exists:
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
                fh.write(cloud_init())
            az("vm", "create", "-g", rg, "-n", vm, "-l", info["location"],
               "--image", IMAGE, "--size", VM_SIZE,
               "--admin-username", "vikivpn",
               "--ssh-key-values", os.path.join(keys_dir, "admin_ed25519.pub"),
               "--public-ip-sku", "Standard", "--public-ip-address-allocation", "static",
               "--public-ip-address", f"{vm}-ip", "--nsg", f"{vm}-nsg", "--nsg-rule", "NONE",
               "--os-disk-size-gb", "30", "--storage-sku", "StandardSSD_LRS",
               "--assign-identity", "[system]", "--custom-data", fh.name,
               "--tags", f"vikivpn-region={code}", f"vikivpn-storage={account}", "vikivpn=1")
            os.unlink(fh.name)
            az("network", "nsg", "rule", "create", "-g", rg, "--nsg-name", f"{vm}-nsg",
               "-n", "wireguard", "--priority", "100", "--direction", "Inbound",
               "--access", "Allow", "--protocol", "Udp", "--destination-port-ranges", str(PORT))
            open_exit_ssh(rg, vm)
        else:
            az("vm", "start", "-g", rg, "-n", vm)

        vm_info = az("vm", "show", "-g", rg, "-n", vm)
        vm_id, principal = vm_info["id"], vm_info["identity"]["principalId"]
        assign(principal, ROLE_STOPPER, vm_id)
        assign(principal, "Storage Blob Data Reader", state["storageId"])
        assign(state["clientObjectId"], ROLE_STARTER, f"/subscriptions/{sub}/resourceGroups/{rg}")

        say(f"[{code}] waiting for cloud-init")
        out = run_command(rg, vm, "cloud-init status --wait >/dev/null; "
                                  "echo PUB=$(cat /etc/wireguard/server.pub); "
                                  "echo HOSTKEY=$(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub); "
                                  "systemctl is-active wg-quick@wg0 vikivpn-agent")
        m = re.search(r"PUB=(\S+)", out)
        if not m:
            fail(f"[{code}] server key not found:\n{out}")
        ip = az("network", "public-ip", "show", "-g", rg, "-n", f"{vm}-ip",
                "--query", "ipAddress", "-o", "tsv", parse=False)
        hk = re.search(r"HOSTKEY=(ssh-ed25519 \S+)", out)
        state["regions"][code] = {"resourceGroup": rg, "vm": vm, "vmId": vm_id,
                                  "endpoint": ip, "serverPublicKey": m.group(1),
                                  "sshHostKey": hk.group(1) if hk else None,
                                  "location": info["location"], "size": VM_SIZE}
        save_state(state)
        ok(f"[{code}] {ip} pub={m.group(1)[:12]}… services: {' '.join(out.split()[-2:])}")

    say(f"[{code}] lease released — waiting for the VM agent to deallocate itself")
    if wait_power(rg, vm, "deallocated", 360):
        ok(f"[{code}] agent deallocated the VM on its own")
    else:
        say(f"[{code}] agent did not deallocate within 6 min — deallocating now")
        az("vm", "deallocate", "-g", rg, "-n", vm, "--no-wait")


def open_exit_ssh(rg: str, vm: str) -> None:
    """Home exits dial in over SSH (key-only, forwarding-only account)."""
    az("network", "nsg", "rule", "create", "-g", rg, "--nsg-name", f"{vm}-nsg",
       "-n", "home-exit-ssh", "--priority", "110", "--direction", "Inbound",
       "--access", "Allow", "--protocol", "Tcp", "--destination-port-ranges", "22")


def upgrade_region(state: dict, code: str) -> None:
    r = state["regions"][code]
    rg, vm = r["resourceGroup"], r["vm"]
    open_exit_ssh(rg, vm)
    with AdminLease(state["storage"], code):
        if power_state(rg, vm) != "running":
            say(f"[{code}] starting VM for upgrade")
            az("vm", "start", "-g", rg, "-n", vm)
        files = "".join(
            f"echo {base64.b64encode(open(os.path.join(SKILL, 'server', n), 'rb').read()).decode()}"
            f" | base64 -d > {dest}.new && chmod {mode} {dest}.new && mv {dest}.new {dest}; "
            for n, dest, mode in (("agent.py", "/opt/vikivpn/agent.py", "755"),
                                  ("firewall.sh", "/opt/vikivpn/firewall.sh", "755"),
                                  ("vikivpn-agent.service",
                                   "/etc/systemd/system/vikivpn-agent.service", "644")))
        out = run_command(rg, vm, files +
                          "systemctl daemon-reload; /opt/vikivpn/firewall.sh down; "
                          "/opt/vikivpn/firewall.sh up; systemctl restart vikivpn-agent; sleep 3; "
                          "echo HOSTKEY=$(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub); "
                          "systemctl is-active vikivpn-agent")
        hk = re.search(r"HOSTKEY=(ssh-ed25519 \S+)", out)
        if not hk or not re.search(r"^active$", out, re.M):
            fail(f"[{code}] upgrade failed:\n{out}")
        with _STATE_LOCK:
            r["sshHostKey"] = hk.group(1)
        save_state(state)
        ok(f"[{code}] agent upgraded, host key recorded")
    say(f"[{code}] lease released — the agent will deallocate the VM")


def cmd_upgrade(args) -> None:
    state = load_state()
    need_init(state)
    acct_id = state["storageId"]
    az("storage", "container-rm", "create", "--storage-account", acct_id, "-n", "exits",
       "--public-access", "off", check=False)
    assign(state["clientObjectId"], "Storage Blob Data Contributor",
           f"{acct_id}/blobServices/default/containers/exits")
    # Home-exit invites are user-delegation SAS URLs; the key can only be issued at account scope.
    assign(state["clientObjectId"], "Storage Blob Delegator", acct_id)
    regions = args.region or list(state["regions"])
    threads = [threading.Thread(target=upgrade_region, args=(state, c)) for c in regions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def cmd_deploy(args) -> None:
    state = load_state()
    need_init(state)
    keys_dir = os.path.join(HOME, "keys")
    os.makedirs(keys_dir, mode=0o700, exist_ok=True)
    key = os.path.join(keys_dir, "admin_ed25519")
    if not os.path.exists(key):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key,
                        "-C", "vikivpn-admin"], check=True)
    regions = args.region or ["in"]
    for code in regions:
        if code not in REGIONS:
            fail(f"unknown region {code}; choose from {', '.join(REGIONS)}")
    threads = [threading.Thread(target=deploy_region, args=(state, c, keys_dir)) for c in regions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if state.get("reconciler"):
        update_reconciler_settings(state)


# ----------------------------------------------------------- reconciler ----

def update_reconciler_settings(state: dict) -> None:
    rec = state["reconciler"]
    vms = [{"region": c, "id": r["vmId"]} for c, r in state["regions"].items()]
    az("functionapp", "config", "appsettings", "set", "-g", CTL_RG, "-n", rec["name"],
       "--settings", f"VIKIVPN_VMS={json.dumps(vms)}", f"VIKIVPN_STORAGE={state['storage']}",
       f"VIKIVPN_LEASE_TTL={LEASE_TTL}")
    for c, r in state["regions"].items():
        assign(rec["principal"], ROLE_STOPPER, r["vmId"])
    ok(f"reconciler watches {', '.join(state['regions'])}")


def cmd_reconciler(args) -> None:
    state = load_state()
    need_init(state)
    rec = state.get("reconciler") or {"name": "vikivpn-rec-" + suffix(6),
                                      "hostStorage": "vikivpnfn" + suffix(8)}
    state["reconciler"] = rec
    save_state(state)
    if not az("storage", "account", "show", "-n", rec["hostStorage"], "-g", CTL_RG, check=False):
        az("storage", "account", "create", "-n", rec["hostStorage"], "-g", CTL_RG,
           "-l", CTL_LOCATION, "--sku", "Standard_LRS", "--allow-blob-public-access", "false")
    if not az("functionapp", "show", "-g", CTL_RG, "-n", rec["name"], check=False):
        say(f"creating Flex Consumption function {rec['name']}")
        az("functionapp", "create", "-g", CTL_RG, "-n", rec["name"],
           "--storage-account", rec["hostStorage"], "--flexconsumption-location", CTL_LOCATION,
           "--runtime", "python", "--runtime-version", "3.12",
           "--instance-memory", "512", "--maximum-instance-count", "40")
    rec["principal"] = az("functionapp", "identity", "assign", "-g", CTL_RG, "-n", rec["name"],
                          "--query", "principalId", "-o", "tsv", parse=False)
    save_state(state)
    assign(rec["principal"], "Storage Blob Data Reader", state["storageId"])
    update_reconciler_settings(state)
    src = os.path.join(SKILL, "reconciler")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = shutil.make_archive(os.path.join(tmp, "rec"), "zip", src)
        az("functionapp", "deployment", "source", "config-zip", "-g", CTL_RG, "-n", rec["name"],
           "--src", zpath, "--build-remote", "true", timeout=1800)
    ok(f"reconciler deployed: {rec['name']} (every 5 min)")


# --------------------------------------------------------------- devices ----

def wg(*args: str, stdin: str | None = None) -> str:
    exe = shutil.which("wg") or "/opt/homebrew/bin/wg"
    return subprocess.run([exe, *args], input=stdin, capture_output=True, text=True,
                          check=True).stdout.strip()


def cmd_add_device(args) -> None:
    state = load_state()
    need_init(state)
    name = args.name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        fail("device names are lowercase letters, digits and dashes")
    account = state["storage"]
    status, raw = blob_retry("GET", account, "config/peers.json")
    peers = json.loads(raw)["peers"] if status == 200 else []
    dev_dir = os.path.join(HOME, "devices", name)
    os.makedirs(dev_dir, mode=0o700, exist_ok=True)
    key_path = os.path.join(dev_dir, "private.key")
    existing = next((p for p in peers if p["name"] == name), None)
    if existing and os.path.exists(key_path):
        priv = open(key_path).read().strip()
        peer = existing
    else:
        priv = wg("genkey")
        with open(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            fh.write(priv + "\n")
        used = {int(p["ip4"].rsplit(".", 1)[1]) for p in peers}
        host = next(i for i in range(2, 250) if i not in used)
        peer = {"name": name, "pubkey": wg("pubkey", stdin=priv),
                "ip4": f"10.66.0.{host}", "ip6": f"fd66::{host:x}"}
        peers = [p for p in peers if p["name"] != name] + [peer]
        status, raw = blob_retry("PUT", account, "config/peers.json",
                                 json.dumps({"peers": peers}, indent=2).encode())
        if status not in (200, 201):
            fail(f"could not update peers.json: {status} {raw[:200]!r}")
    state["devices"][name] = {"ip4": peer["ip4"], "ip6": peer["ip6"], "pubkey": peer["pubkey"]}
    save_state(state)
    for code, region in state["regions"].items():
        peer_block = (f"[Peer]\nPublicKey = {region['serverPublicKey']}\n"
                      f"Endpoint = {region['endpoint']}:{PORT}\n"
                      f"AllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n")
        for fname, iface in (
                (f"{code}.conf", f"[Interface]\nPrivateKey = {priv}\n"),
                (f"{code}.wg-quick.conf",
                 f"[Interface]\nPrivateKey = {priv}\nAddress = {peer['ip4']}/32, {peer['ip6']}/128\n"
                 f"DNS = 1.1.1.1, 1.0.0.1\nMTU = 1380\n")):
            path = os.path.join(dev_dir, fname)
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
                fh.write(iface + "\n" + peer_block)
    with open(os.path.join(dev_dir, "device.env"), "w") as fh:
        fh.write(f"ADDR4={peer['ip4']}\nADDR6={peer['ip6']}\nDNS='1.1.1.1 1.0.0.1'\nMTU=1380\n")
    ok(f"device {name}: {peer['ip4']} — configs in {dev_dir}")


def app_config(state: dict, device: str) -> dict:
    return {
        "tenantId": state["tenant"], "clientId": state["clientId"],
        "subscriptionId": state["subscription"], "storageAccount": state["storage"],
        "device": device, "leaseTTL": LEASE_TTL, "renewEvery": 45,
        "monthlyCredit": state.get("monthlyCredit"),
        "addresses": [f"{state['devices'][device]['ip4']}/32", f"{state['devices'][device]['ip6']}/128"],
        "dns": ["1.1.1.1", "1.0.0.1"], "mtu": 1380,
        "regions": [{"code": c, **{k: REGIONS[c][k] for k in ("name", "city", "flag", "country", "location")},
                     "resourceGroup": r["resourceGroup"], "vm": r["vm"], "vmId": r["vmId"],
                     "endpoint": r["endpoint"], "size": r["size"],
                     "serverPublicKey": r["serverPublicKey"], "sshHostKey": r.get("sshHostKey")}
                    for c, r in state["regions"].items()],
    }


def cmd_install_mac(args) -> None:
    """Write the app config and put the app's secrets in the login Keychain.

    The tunnel itself is the app's own Network Extension, so nothing here needs root.
    """
    state = load_state()
    need_init(state)
    device = args.name
    dev_dir = os.path.join(HOME, "devices", device)
    if not os.path.isdir(dev_dir):
        fail(f"run `vpnctl.py add-device {device}` first")
    if args.monthly_credit is not None:
        state["monthlyCredit"] = args.monthly_credit
        save_state(state)
    os.makedirs(APP_SUPPORT, exist_ok=True)
    with open(os.path.join(APP_SUPPORT, "config.json"), "w") as fh:
        json.dump(app_config(state, device), fh, indent=2)
    ok(f"app config → {APP_SUPPORT}/config.json")

    apps = [args.app] if os.path.exists(args.app) else []
    secret = keychain_get(state["clientId"])
    if not secret:
        fail("client secret missing from Keychain — run `vpnctl.py rotate-secret`")
    keychain_set(state["clientId"], secret, apps)
    priv = open(os.path.join(dev_dir, "private.key")).read().strip()
    keychain_set(f"wg-{device}", priv, apps, label="VikiVPN WireGuard key")
    ok("client secret and WireGuard key available to the app via Keychain")


def cmd_rotate_secret(args) -> None:
    state = load_state()
    need_init(state)
    cred = az("ad", "sp", "credential", "reset", "--id", state["clientId"], "--years", "2")
    keychain_set(state["clientId"], cred["password"])
    ok("client secret rotated and stored in Keychain (re-run install-mac)")


# ------------------------------------------------------------ operations ----

def leases(account: str) -> dict[str, list[tuple[str, float]]]:
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    token = user_token("https://storage.azure.com/")
    req = urllib.request.Request(
        f"https://{account}.blob.core.windows.net/leases?restype=container&comp=list",
        headers={"Authorization": "Bearer " + token, "x-ms-version": "2021-08-06"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        now = parsedate_to_datetime(resp.headers["Date"]).timestamp()
        root = ET.fromstring(resp.read())
    out: dict[str, list] = {}
    for b in root.iter("Blob"):
        region, _, dev = (b.findtext("Name") or "").partition("/")
        age = now - parsedate_to_datetime(b.findtext("Properties/Last-Modified")).timestamp()
        out.setdefault(region, []).append((dev, age))
    return out


def cmd_status(args) -> None:
    state = load_state()
    need_init(state)
    lease_map = leases(state["storage"])
    rows = []
    for code, r in state["regions"].items():
        power = power_state(r["resourceGroup"], r["vm"])
        live = [f"{d}({int(a)}s)" for d, a in lease_map.get(code, []) if a < LEASE_TTL]
        rows.append({"region": code, "power": power, "endpoint": r["endpoint"], "leases": live})
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    for row in rows:
        print(f"{row['region']:3} {row['power']:12} {row['endpoint']:16} "
              f"leases: {', '.join(row['leases']) or '-'}")


def cmd_verify_idle(args) -> None:
    state = load_state()
    need_init(state)
    bad = []
    for code, r in state["regions"].items():
        view = az("vm", "get-instance-view", "-g", r["resourceGroup"], "-n", r["vm"],
                  "--query", "instanceView.statuses[?starts_with(code,'PowerState/')].code | [0]",
                  "-o", "tsv", parse=False)
        print(f"{code:3} {r['vm']:12} {view}")
        if view != "PowerState/deallocated":
            bad.append(code)
    if bad:
        fail(f"not deallocated: {', '.join(bad)}")
    ok("every VPN VM is deallocated — no compute is billing")


def cmd_stop(args) -> None:
    state = load_state()
    need_init(state)
    for code in args.region or list(state["regions"]):
        r = state["regions"][code]
        az("vm", "deallocate", "-g", r["resourceGroup"], "-n", r["vm"], "--no-wait")
        say(f"[{code}] deallocate requested")


def cmd_destroy(args) -> None:
    state = load_state()
    for code, r in state.get("regions", {}).items():
        az("group", "delete", "-n", r["resourceGroup"], "--yes", "--no-wait", check=False)
        say(f"deleting {r['resourceGroup']}")
    az("group", "delete", "-n", CTL_RG, "--yes", "--no-wait", check=False)
    if state.get("clientId"):
        az("ad", "app", "delete", "--id", state["clientId"], check=False)
    for name in (ROLE_STARTER, ROLE_STOPPER):
        az("role", "definition", "delete", "--name", name, check=False)
    os.replace(STATE_PATH, STATE_PATH + ".destroyed")
    ok("teardown requested for every VikiVPN resource group")


def main() -> None:
    ap = argparse.ArgumentParser(prog="vpnctl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    p = sub.add_parser("deploy")
    p.add_argument("--region", nargs="+", choices=list(REGIONS))
    p.set_defaults(fn=cmd_deploy)
    sub.add_parser("reconciler").set_defaults(fn=cmd_reconciler)
    p = sub.add_parser("add-device")
    p.add_argument("name")
    p.set_defaults(fn=cmd_add_device)
    p = sub.add_parser("install-mac")
    p.add_argument("name")
    p.add_argument("--app", default="/Applications/VikiVPN.app")
    p.add_argument("--monthly-credit", type=float,
                   help="monthly Azure credit in billing currency (for the credits estimate)")
    p.set_defaults(fn=cmd_install_mac)
    sub.add_parser("rotate-secret").set_defaults(fn=cmd_rotate_secret)
    p = sub.add_parser("upgrade")
    p.add_argument("--region", nargs="+")
    p.set_defaults(fn=cmd_upgrade)
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)
    sub.add_parser("verify-idle").set_defaults(fn=cmd_verify_idle)
    p = sub.add_parser("stop")
    p.add_argument("--region", nargs="+")
    p.set_defaults(fn=cmd_stop)
    sub.add_parser("destroy").set_defaults(fn=cmd_destroy)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
