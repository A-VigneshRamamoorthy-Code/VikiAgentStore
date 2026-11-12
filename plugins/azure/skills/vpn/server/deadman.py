#!/usr/bin/env python3
"""VikiVPN deadman: deallocate this VM if the agent has stopped reporting.

Runs from a systemd timer, separately from the agent, so a crashed or wedged
agent cannot keep the VM (and its bill) running. The agent rewrites
/run/vikivpn/status.json every 15 s; if that is older than STALE seconds -- or
never appeared within STALE of boot -- this asks Azure to deallocate the VM
using the VM's managed identity.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

STATUS = "/run/vikivpn/status.json"
STALE = int(os.environ.get("VIKIVPN_DEADMAN_STALE", "600"))
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
    try:
        age = time.time() - os.stat(STATUS).st_mtime
    except FileNotFoundError:
        age = uptime
    # The guest clock is stepped (often by hours) right after a VM resumes from
    # deallocation, so wall-clock mtimes can look far older than this boot.
    age = min(age, uptime)
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
