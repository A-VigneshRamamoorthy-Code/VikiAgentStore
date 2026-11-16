#!/usr/bin/env python3
"""Aven VPN deadman: deallocate this VM if the agent has stopped reporting.

Runs from a systemd timer, separately from the agent, so a crashed or wedged
agent cannot keep the VM (and its bill) running. The agent rewrites
/run/avenvpn/status.json every 15 s; if that is older than STALE seconds -- or
never appeared within STALE of the deadman's first run on this boot -- this asks
Azure to deallocate the VM using the VM's managed identity.

The grace is not measured from boot: Azure can hand out pre-provisioned VMs that
have already been up for hours before cloud-init installs this, so /proc/uptime
says nothing about how long the agent has had to start.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

STATUS = "/run/avenvpn/status.json"
STALE = int(os.environ.get("AVENVPN_DEADMAN_STALE", "600"))
# /run is tmpfs: this marker is per boot.
SINCE = "/run/avenvpn/deadman-since"
IMDS = "http://169.254.169.254/metadata"


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Metadata": "true"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def main() -> int:
    with open("/proc/uptime") as fh:
        uptime = float(fh.read().split()[0])
    try:
        with open(SINCE) as fh:
            since = float(fh.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        since = time.monotonic()
        try:
            os.makedirs(os.path.dirname(SINCE), exist_ok=True)
            with open(SINCE, "w") as fh:
                fh.write(f"{since}\n")
        except OSError:
            since = time.monotonic() - uptime  # can't remember: fall back to boot time
    watched = min(uptime, max(0.0, time.monotonic() - since))
    if watched < STALE:
        return 0
    age = watched
    try:
        with open(STATUS) as fh:
            status = json.load(fh)
        with open("/proc/sys/kernel/random/boot_id") as fh:
            boot_id = fh.read().strip()
        if status.get("boot_id") == boot_id and isinstance(status.get("mono"), (int, float)):
            # Same boot: CLOCK_MONOTONIC never steps, unlike the wall clock.
            age = time.monotonic() - status["mono"]
        else:
            # Older agent: fall back to mtime. The guest clock is stepped (often by hours)
            # after a resume, so cap at uptime and treat a future mtime as stale, not fresh.
            age = time.time() - os.stat(STATUS).st_mtime
            age = watched if age < 0 else min(age, watched)
    except (FileNotFoundError, ValueError, OSError):
        pass
    if age < STALE:
        return 0
    rid = get(f"{IMDS}/instance?api-version=2021-02-01")["compute"]["resourceId"]
    tok = get(f"{IMDS}/identity/oauth2/token?api-version=2018-02-01&resource="
              + urllib.parse.quote("https://management.azure.com/", safe=""))["access_token"]
    req = urllib.request.Request(
        f"https://management.azure.com{rid}/deallocate?api-version=2024-07-01",
        data=b"", method="POST", headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"agent silent for {int(age)}s -- deallocate requested (HTTP {resp.status})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
