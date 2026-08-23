"""Everything that shells out to `az`, plus VM provisioning and teardown."""
from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import sys

from azc_common import fail, ok, say

# Keep `az` quiet and scriptable: no colour, no telemetry, no prompts, no nags.
# Without these the CLI writes survey banners and confirmation prompts into
# output we parse, and blocks forever on a subscription picker at login.
AZ_ENV = {
    **os.environ,
    "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
    "AZURE_CORE_NO_COLOR": "true",
    "AZURE_CORE_COLLECT_TELEMETRY": "false",
    "AZURE_CORE_DISABLE_CONFIRM_PROMPT": "true",
    "AZURE_CORE_LOGIN_EXPERIENCE_V2": "false",
    "AZURE_CORE_SURVEY_MESSAGE": "no",
    "AZURE_CORE_OUTPUT": "json",
}

TAG_MARK = "azc"


# ------------------------------------------------------------ az plumbing ---

def az_path() -> str | None:
    return shutil.which("az")


def az(args: list[str], parse: bool = True, check: bool = True,
       timeout: int = 900, stream: bool = False):
    """Run an az command. Returns parsed JSON, or the CompletedProcess."""
    cmd = [az_path() or "az"] + args
    if parse and "--output" not in args and "-o" not in args:
        cmd += ["--output", "json"]
    if "--only-show-errors" not in args:
        cmd += ["--only-show-errors"]

    if stream:
        proc = subprocess.run(cmd, env=AZ_ENV, timeout=timeout)
        if check and proc.returncode != 0:
            fail(f"az {' '.join(args[:3])} failed (exit {proc.returncode})")
        return proc

    proc = subprocess.run(cmd, env=AZ_ENV, capture_output=True,
                          text=True, timeout=timeout)
    if proc.returncode != 0:
        if check:
            detail = (proc.stderr or proc.stdout or "").strip()
            fail(f"az {' '.join(args[:3])} failed:\n{detail}")
        return None
    if not parse:
        return proc
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


# --------------------------------------------------------------- install ---

INSTALL_HINTS = {
    "Darwin": "brew update && brew install azure-cli",
    "Linux": "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash",
    "Windows": "winget install -e --id Microsoft.AzureCLI",
}


def ensure_cli(auto: bool = True) -> None:
    if az_path():
        return
    system = platform.system()
    say(f"Azure CLI not found — installing for {system}")

    if not auto:
        fail("Azure CLI is missing. Install it with:\n  " +
             INSTALL_HINTS.get(system, INSTALL_HINTS["Linux"]))

    try:
        if system == "Darwin":
            if not shutil.which("brew"):
                fail("Homebrew not found. Install Homebrew from https://brew.sh "
                     "then re-run, or install the Azure CLI manually:\n  "
                     "https://learn.microsoft.com/cli/azure/install-azure-cli-macos")
            subprocess.run(["brew", "update"], check=False, timeout=600)
            subprocess.run(["brew", "install", "azure-cli"], check=True, timeout=1800)
        elif system == "Linux":
            distro = ""
            try:
                with open("/etc/os-release", encoding="utf-8") as fh:
                    distro = fh.read().lower()
            except OSError:
                pass
            if "debian" in distro or "ubuntu" in distro:
                subprocess.run(
                    "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash",
                    shell=True, check=True, timeout=1800)
            else:
                subprocess.run(
                    "curl -sL https://aka.ms/InstallAzureCli | sudo bash",
                    shell=True, check=True, timeout=1800)
        elif system == "Windows":
            subprocess.run(["winget", "install", "-e", "--id",
                            "Microsoft.AzureCLI", "--accept-package-agreements",
                            "--accept-source-agreements"], check=True, timeout=1800)
        else:
            fail(f"unsupported platform {system} — install the Azure CLI manually")
    except subprocess.CalledProcessError as exc:
        fail(f"Azure CLI install failed ({exc}). Install manually:\n  " +
             INSTALL_HINTS.get(system, INSTALL_HINTS["Linux"]))

    # A fresh install may not be on this process's PATH yet.
    if not az_path():
        fail("Azure CLI installed but not on PATH — open a new shell and re-run.")
    ok("Azure CLI installed")


# ------------------------------------------------------------------ auth ---

def current_account() -> dict | None:
    if not az_path():
        return None
    proc = subprocess.run([az_path(), "account", "show", "-o", "json",
                           "--only-show-errors"],
                          env=AZ_ENV, capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def ensure_login(interactive: bool = True) -> dict:
    acct = current_account()
    if acct:
        return acct

    sp_id = os.environ.get("AZURE_CLIENT_ID")
    sp_secret = os.environ.get("AZURE_CLIENT_SECRET")
    tenant = os.environ.get("AZURE_TENANT_ID")
    if sp_id and sp_secret and tenant:
        say("signing in with the service principal from the environment")
        az(["login", "--service-principal", "-u", sp_id, "-p", sp_secret,
            "--tenant", tenant], parse=False)
        acct = current_account()
        if acct:
            ok(f"signed in as service principal on {acct.get('name')}")
            return acct

    if not interactive:
        fail("not signed in to Azure. Run:  az login --use-device-code")

    say("not signed in — starting device-code sign-in")
    print("\n>>> Azure needs you to sign in. The code and URL appear below.\n",
          file=sys.stderr, flush=True)
    # Streamed so the device code reaches the user in real time.
    az(["login", "--use-device-code"], parse=False, stream=True, timeout=900)
    acct = current_account()
    if not acct:
        fail("sign-in did not complete")
    ok(f"signed in as {acct.get('user', {}).get('name')}")
    return acct


def subscription_policies(sub_id: str) -> dict:
    data = az(["rest", "--method", "get", "--url",
               f"https://management.azure.com/subscriptions/{sub_id}"
               "?api-version=2020-01-01"], check=False)
    return (data or {}).get("subscriptionPolicies", {}) or {}


# ----------------------------------------------------------------- quota ---

def quota(region: str) -> dict:
    rows = az(["vm", "list-usage", "--location", region], check=False) or []
    out = {}
    for row in rows:
        name = (row.get("name") or {}).get("value")
        if name:
            out[name] = (int(row.get("currentValue", 0)), int(row.get("limit", 0)))
    return out


def size_restricted(region: str, size: str) -> str | None:
    """Return a human reason if the SKU cannot be used here, else None."""
    rows = az(["vm", "list-skus", "--location", region, "--size", size,
               "--resource-type", "virtualMachines"], check=False) or []
    for row in rows:
        if row.get("name") != size:
            continue
        for r in row.get("restrictions") or []:
            if r.get("reasonCode") == "NotAvailableForSubscription":
                zones = (r.get("restrictionInfo") or {}).get("zones")
                if r.get("type") == "Zone" and zones:
                    continue          # only some zones blocked — still usable
                return "not available for this subscription in this region"
            if r.get("reasonCode") == "QuotaId":
                return "blocked for this subscription offer type"
        return None
    return "size not offered in this region"


# ------------------------------------------------------------- cloud-init ---

WATCHDOG = r"""#!/bin/bash
# azc watchdog — deletes this VM's whole resource group when the job is over,
# the deadline passes, or the controller stops checking in.
set -u
CONF=/etc/azc/job.env
[ -r "$CONF" ] || exit 0
. "$CONF"

HB=/var/lib/azc/heartbeat
now=$(date +%s)
reason=""

if [ -f /var/lib/azc/done ]; then
  reason="job-complete"
elif [ "$now" -ge "${AZC_DEADLINE:-0}" ]; then
  reason="deadline"
elif [ "${AZC_IDLE:-0}" -gt 0 ]; then
  hb=$(stat -c %Y "$HB" 2>/dev/null || echo 0)
  if [ "$hb" -gt 0 ] && [ $(( now - hb )) -ge "${AZC_IDLE}" ]; then
    reason="idle-$(( now - hb ))s"
  fi
fi

[ -z "$reason" ] && exit 0
logger -t azc "self-destruct: $reason"

RES="https%3A%2F%2Fmanagement.azure.com%2F"
TOKEN=$(curl -s -m 20 -H Metadata:true \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=${RES}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -n "$TOKEN" ]; then
  curl -s -m 30 -X DELETE -H "Authorization: Bearer $TOKEN" \
    "https://management.azure.com/subscriptions/${AZC_SUB}/resourcegroups/${AZC_RG}?api-version=2021-04-01" \
    >/dev/null 2>&1
  logger -t azc "resource group delete requested"
  sleep 25
else
  logger -t azc "no managed-identity token; falling back to poweroff"
fi

# Whatever happened above, stop the compute clock.
shutdown -P now
"""

SERVICE = """[Unit]
Description=azc watchdog
[Service]
Type=oneshot
ExecStart=/usr/local/bin/azc-watchdog
"""

TIMER = """[Unit]
Description=azc watchdog timer
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=15
[Install]
WantedBy=timers.target
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def cloud_init(profile: dict, sub_id: str, rg: str, deadline_epoch: int,
               idle_seconds: int, hard_poweroff_minutes: int) -> str:
    packages = profile.get("packages") or []
    pips = profile.get("pip") or []

    job_env = (f"AZC_SUB={sub_id}\nAZC_RG={rg}\n"
               f"AZC_DEADLINE={deadline_epoch}\nAZC_IDLE={idle_seconds}\n")

    lines = [
        "#cloud-config",
        "package_update: true",
        "packages:",
        "  - curl",
        "  - rsync",
        "  - python3",
    ]
    for pkg in packages:
        lines.append(f"  - {pkg}")

    lines += [
        "write_files:",
        "  - path: /usr/local/bin/azc-watchdog",
        "    permissions: '0755'",
        "    encoding: b64",
        f"    content: {_b64(WATCHDOG)}",
        "  - path: /etc/systemd/system/azc-watchdog.service",
        "    encoding: b64",
        f"    content: {_b64(SERVICE)}",
        "  - path: /etc/systemd/system/azc-watchdog.timer",
        "    encoding: b64",
        f"    content: {_b64(TIMER)}",
        "  - path: /etc/azc/job.env",
        "    permissions: '0644'",
        "    encoding: b64",
        f"    content: {_b64(job_env)}",
        "runcmd:",
        "  - [ mkdir, -p, /var/lib/azc ]",
        "  - [ chmod, '0777', /var/lib/azc ]",
        "  - [ touch, /var/lib/azc/heartbeat ]",
        "  - [ chmod, '0666', /var/lib/azc/heartbeat ]",
        # Hard backstop: even if the identity or the timer fails, the machine
        # powers itself off and stops costing money.
        f"  - shutdown -P +{hard_poweroff_minutes}",
        "  - [ systemctl, daemon-reload ]",
        "  - [ systemctl, enable, '--now', azc-watchdog.timer ]",
    ]
    if pips:
        quoted = " ".join(f"'{p}'" for p in pips)
        lines.append(f"  - pip3 install --break-system-packages {quoted} "
                     f"|| pip3 install {quoted} || true")
    lines.append("  - [ touch, /var/lib/azc/ready ]")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ rg lifecycle ---

def list_azc_groups() -> list:
    groups = az(["group", "list", "--tag", f"{TAG_MARK}=1"], check=False) or []
    return groups


def delete_rg(rg: str, wait: bool = False) -> None:
    args = ["group", "delete", "--name", rg, "--yes"]
    if not wait:
        args.append("--no-wait")
    az(args, parse=False, check=False, timeout=1800)


def rg_exists(rg: str) -> bool:
    res = az(["group", "exists", "--name", rg], check=False)
    return res is True or res == "true"
