#!/usr/bin/env python3
"""Provision LeapVPN for Network Extension development signing — no Xcode needed.

Uses the App Store Connect API to make sure that:
  * bundle IDs exist for the app and its packet-tunnel extension, with the
    Network Extensions capability enabled;
  * this Mac is a registered device;
  * a macOS development provisioning profile exists for each bundle ID, signed by
    your "Apple Development" certificate and including this Mac.

Profiles are written to mac/.build/profiles/<bundle-id>.provisionprofile.

    ASC_KEY_ID=… ASC_ISSUER_ID=… python3 provision.py [--key ~/.appstoreconnect/private_keys/AuthKey_<id>.p8]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.appstoreconnect.apple.com/v1"
APP_ID = os.environ.get("LEAPVPN_BUNDLE_ID", "com.sololeap.leapvpn")
TUNNEL_ID = APP_ID + ".tunnel"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", ".build", "profiles"))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def der_to_raw(sig: bytes) -> bytes:
    """ECDSA DER signature → 64-byte r||s, as JWS ES256 requires."""
    i = 2 if sig[1] < 0x80 else 3
    out = b""
    for _ in range(2):
        n = sig[i + 1]
        out += sig[i + 2:i + 2 + n].lstrip(b"\0").rjust(32, b"\0")
        i += 2 + n
    return out


def token(key_id: str, issuer: str, key_path: str) -> str:
    header = b64url(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    now = int(time.time())
    claims = b64url(json.dumps({"iss": issuer, "iat": now, "exp": now + 1100,
                                "aud": "appstoreconnect-v1"}).encode())
    signing_input = f"{header}.{claims}".encode()
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path], input=signing_input,
                         capture_output=True, check=True).stdout
    return f"{header}.{claims}.{b64url(der_to_raw(der))}"


class ASC:
    def __init__(self, tok: str):
        self.tok = tok

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(API + path, method=method,
                                     data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": "Bearer " + self.tok,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise SystemExit(f"ASC {method} {path} → {e.code}: {e.read().decode()[:800]}")


def q(s: str) -> str:
    return urllib.parse.quote(s)


def log(msg: str) -> None:
    print(f"provision {msg}", file=sys.stderr)


def ensure_bundle(asc: ASC, identifier: str, name: str) -> str:
    found = asc.call("GET", f"/bundleIds?filter[identifier]={q(identifier)}&limit=20")["data"]
    found = [b for b in found if b["attributes"]["identifier"] == identifier]
    if found:
        bid = found[0]["id"]
    else:
        bid = asc.call("POST", "/bundleIds", {"data": {"type": "bundleIds", "attributes": {
            "identifier": identifier, "name": name, "platform": "UNIVERSAL"}}})["data"]["id"]
        log(f"created bundle id {identifier}")
    caps = asc.call("GET", f"/bundleIds/{bid}/bundleIdCapabilities")["data"]
    if not any(c["attributes"]["capabilityType"] == "NETWORK_EXTENSIONS" for c in caps):
        asc.call("POST", "/bundleIdCapabilities", {"data": {
            "type": "bundleIdCapabilities",
            "attributes": {"capabilityType": "NETWORK_EXTENSIONS"},
            "relationships": {"bundleId": {"data": {"type": "bundleIds", "id": bid}}}}})
        log(f"enabled Network Extensions on {identifier}")
    return bid


def this_mac_udid() -> str:
    out = subprocess.run(["system_profiler", "SPHardwareDataType"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "Provisioning UDID" in line:
            return line.split(":", 1)[1].strip()
    raise SystemExit("could not read this Mac's Provisioning UDID")


def ensure_device(asc: ASC) -> str:
    udid = this_mac_udid()
    found = asc.call("GET", f"/devices?filter[udid]={q(udid)}&limit=5")["data"]
    if found:
        return found[0]["id"]
    log(f"registering this Mac ({udid})")
    return asc.call("POST", "/devices", {"data": {"type": "devices", "attributes": {
        "name": "LeapVPN Mac", "udid": udid, "platform": "MAC_OS"}}})["data"]["id"]


def local_dev_serials() -> set[str]:
    """Serial numbers of Apple Development certificates with a private key in this keychain."""
    valid = subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"],
                           capture_output=True, text=True).stdout.upper()
    pem = subprocess.run(["security", "find-certificate", "-a", "-c", "Apple Development", "-p"],
                         capture_output=True, text=True).stdout
    serials = set()
    for block in pem.split("-----END CERTIFICATE-----"):
        if "BEGIN CERTIFICATE" not in block:
            continue
        info = subprocess.run(["openssl", "x509", "-noout", "-serial", "-fingerprint", "-sha1"],
                              input=block + "-----END CERTIFICATE-----\n",
                              capture_output=True, text=True).stdout.splitlines()
        fields = {l.split("=", 1)[0].strip(): l.split("=", 1)[1] for l in info if "=" in l}
        fp = fields.get("SHA1 Fingerprint", fields.get("sha1 Fingerprint", "")).replace(":", "").upper()
        if fp and fp in valid:
            serials.add(fields["serial"].upper().lstrip("0"))
    return serials


def ensure_cert(asc: ASC) -> str:
    serials = local_dev_serials()
    for c in asc.call("GET", "/certificates?limit=200")["data"]:
        a = c["attributes"]
        if a["certificateType"] in ("DEVELOPMENT", "MAC_APP_DEVELOPMENT") and \
                a["serialNumber"].upper().lstrip("0") in serials:
            return c["id"]
    raise SystemExit("no Apple Development certificate in App Store Connect matches a signing "
                     "identity in this keychain")


def ensure_profile(asc: ASC, identifier: str, bid: str, cert: str, device: str) -> str:
    name = f"Leap VPN Dev {identifier}"
    content = None
    for p in asc.call("GET", f"/profiles?filter[name]={q(name)}&limit=20")["data"]:
        devs = asc.call("GET", f"/profiles/{p['id']}/devices")["data"]
        crts = asc.call("GET", f"/profiles/{p['id']}/certificates")["data"]
        if content is None and p["attributes"]["profileState"] == "ACTIVE" \
                and any(d["id"] == device for d in devs) and any(c["id"] == cert for c in crts):
            content = p["attributes"]["profileContent"]
        else:
            asc.call("DELETE", f"/profiles/{p['id']}")
    if content is None:
        content = asc.call("POST", "/profiles", {"data": {
            "type": "profiles",
            "attributes": {"name": name, "profileType": "MAC_APP_DEVELOPMENT"},
            "relationships": {
                "bundleId": {"data": {"type": "bundleIds", "id": bid}},
                "certificates": {"data": [{"type": "certificates", "id": cert}]},
                "devices": {"data": [{"type": "devices", "id": device}]}}}})["data"]["attributes"]["profileContent"]
        log(f"created profile {name}")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{identifier}.provisionprofile")
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(content))
    return path


def main() -> None:
    key_id = os.environ.get("ASC_KEY_ID", "")
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.path.expanduser(f"~/.appstoreconnect/private_keys/AuthKey_{key_id}.p8"))
    args = ap.parse_args()
    issuer = os.environ.get("ASC_ISSUER_ID", "")
    if not key_id or not issuer or not os.path.exists(args.key):
        raise SystemExit("set ASC_KEY_ID and ASC_ISSUER_ID and make sure the .p8 key exists")
    asc = ASC(token(key_id, issuer, args.key))
    cert = ensure_cert(asc)
    device = ensure_device(asc)
    for identifier, name in ((APP_ID, "Leap VPN"), (TUNNEL_ID, "Leap VPN Tunnel")):
        bid = ensure_bundle(asc, identifier, name)
        print(ensure_profile(asc, identifier, bid, cert, device))


if __name__ == "__main__":
    main()
