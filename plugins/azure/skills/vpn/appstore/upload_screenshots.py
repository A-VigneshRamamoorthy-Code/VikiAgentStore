#!/usr/bin/env python3
"""Replace the App Store Connect screenshot sets with screenshots/ (does NOT submit for review).

    ASC_KEY_ID=... ASC_ISSUER_ID=... ASC_KEY_PATH=... python3 upload_screenshots.py

Order on the store = filename order. iPhone 1320x2868 -> APP_IPHONE_67 (the 6.9"/6.7" bucket);
Mac 2880x1800 -> APP_DESKTOP.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mac" / "tools"))
from provision import ASC, token  # noqa: E402

TARGETS = [
    # (version localisation id, display type, folder)
    ("6bdfbe00-a458-4114-991c-34fad98d013a", "APP_IPHONE_67", "iphone"),  # iOS en-US
    ("5ff55dd4-761f-44df-8f36-9af70268c21f", "APP_DESKTOP", "mac"),       # macOS en-US
]


def screenshot_set(a: ASC, loc: str, kind: str) -> str:
    sets = a.call("GET", f"/appStoreVersionLocalizations/{loc}/appScreenshotSets?limit=50")["data"]
    for s in sets:
        if s["attributes"]["screenshotDisplayType"] == kind:
            for old in a.call("GET", f"/appScreenshotSets/{s['id']}/appScreenshots?limit=50")["data"]:
                a.call("DELETE", f"/appScreenshots/{old['id']}")
            return s["id"]
    return a.call("POST", "/appScreenshotSets", {"data": {
        "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": kind},
        "relationships": {"appStoreVersionLocalization": {"data": {"type": "appStoreVersionLocalizations", "id": loc}}}}})["data"]["id"]


def upload(a: ASC, set_id: str, png: Path) -> str:
    data = png.read_bytes()
    shot = a.call("POST", "/appScreenshots", {"data": {
        "type": "appScreenshots", "attributes": {"fileName": png.name, "fileSize": len(data)},
        "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": set_id}}}}})["data"]
    for op in shot["attributes"]["uploadOperations"]:
        chunk = data[op["offset"]:op["offset"] + op["length"]]
        req = urllib.request.Request(op["url"], data=chunk, method=op["method"],
                                     headers={h["name"]: h["value"] for h in op["requestHeaders"]})
        urllib.request.urlopen(req, timeout=120).read()
    a.call("PATCH", f"/appScreenshots/{shot['id']}", {"data": {
        "type": "appScreenshots", "id": shot["id"],
        "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
    return shot["id"]


def main() -> int:
    a = ASC(token(os.environ.get("ASC_KEY_ID", "ZCT5D865V5"),
                  os.environ.get("ASC_ISSUER_ID", "b75bbafc-4c57-4d16-803f-25c367d01886"),
                  os.path.expanduser(os.environ.get("ASC_KEY_PATH", "~/.appstoreconnect/private_keys/AuthKey_ZCT5D865V5.p8"))))
    for loc, kind, folder in TARGETS:
        pngs = sorted((HERE / "screenshots" / folder).glob("*.png"))
        set_id = screenshot_set(a, loc, kind)
        ids = [upload(a, set_id, p) for p in pngs]
        print(f"{kind}: uploaded {len(ids)}")
        a.call("PATCH", f"/appScreenshotSets/{set_id}/relationships/appScreenshots",
               {"data": [{"type": "appScreenshots", "id": i} for i in ids]})
        for _ in range(40):
            shots = a.call("GET", f"/appScreenshotSets/{set_id}/appScreenshots?limit=50")["data"]
            states = [s["attributes"]["assetDeliveryState"]["state"] for s in shots]
            if all(st in ("COMPLETE", "FAILED") for st in states):
                break
            time.sleep(5)
        for s in shots:
            st = s["attributes"]["assetDeliveryState"]
            print(f"  {s['attributes']['fileName']:28} {st['state']} {st.get('errors') or ''}")
        if any(s["attributes"]["assetDeliveryState"]["state"] != "COMPLETE" for s in shots):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
