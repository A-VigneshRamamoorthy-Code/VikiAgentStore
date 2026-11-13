#!/usr/bin/env python3
"""LeapVPN deadman: deallocate this VM if the agent has stopped reporting.

Runs from a systemd timer, separately from the agent, so a crashed or wedged
agent cannot keep the VM (and its bill) running. The agent rewrites
/run/leapvpn/status.json every 15 s; if that is older than STALE seconds -- or
never appeared within STALE of boot -- this asks Azure to deallocate the VM
using the VM's managed identity.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

STATUS = "/run/leapvpn/status.json"
STALE = int(os.environ.get("LEAPVPN_DEADMAN_STALE", "600"))
IMDS = "http://169.254.169.254/metadata"


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Metadata": "true"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def main() -> int:
    with open("/proc/uptime") as fh:
        uptime = float(fh.read().split()[0])
    if uptime < STALE:
        return 0
    age = uptime
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
            age = uptime if age < 0 else min(age, uptime)
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
