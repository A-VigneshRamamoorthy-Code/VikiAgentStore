#!/usr/bin/env python3
"""Serve the voice gallery for auditioning.

    python scripts/serve.py                 # http://localhost:8899
    python scripts/serve.py --verify        # also confirm every clip decodes

--verify matters: an HTTP 200 only proves the file was served, not that the
browser can decode it. A truncated or malformed mp3 still returns 200 and then
plays as silence. The check uses Playwright to actually decode each clip.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socket
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
GALLERY = ROOT / "templates" / "gallery.html"


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):            # keep the console readable
        pass


def port_taken(port: int) -> bool:
    """True if something already answers on this port.

    Needed because SO_REUSEADDR lets us bind 0.0.0.0:PORT even while another
    process holds 127.0.0.1:PORT. Both "succeed", but the more specific bind
    wins every localhost request — so we would serve nobody and then verify
    the *other* server's files, which shows up as every clip being
    undecodable. Refusing to start is far easier to diagnose.
    """
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def verify(port: int) -> int:
    """Decode every clip in a real browser and report the ones that fail."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed — skipping decode check.\n"
              "  uv pip install playwright && playwright install chromium")
        return 0

    manifest = OUT / "cast" / "manifest.json"
    if not manifest.exists():
        print("No manifest to verify.")
        return 1

    # Relative URLs, so a 404 here proves the gallery's own <audio> src is wrong.
    paths = [f"cast/{c['key']}.mp3"
             for c in json.loads(manifest.read_text(encoding="utf-8"))["characters"]]

    samples = OUT / "samples" / "manifest.json"
    if samples.exists():
        paths += [f"samples/{s['file']}"
                  for s in json.loads(samples.read_text(encoding="utf-8")).get("samples", [])]

    ab = OUT / "ab" / "manifest.json"
    if ab.exists():
        paths += [f"ab/{v['file']}"
                  for v in json.loads(ab.read_text(encoding="utf-8")).get("variants", [])]

    errors: list[str] = []

    # samples/ and ab/ are optional extras; the page probes for them and copes
    # when they are absent. Letting those 404s count as errors would leave a
    # permanent non-zero baseline and hide a real console error later.
    optional = [f"{d}/manifest.json" for d in ("samples", "ab")
                if not (OUT / d / "manifest.json").exists()]

    def note(text: str, url: str = "") -> None:
        if "404" in text and any(o in url for o in optional):
            return
        errors.append(text)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: note(m.text, (m.location or {}).get("url", ""))
                if m.type == "error" else None)
        page.on("pageerror", lambda e: note(str(e)))
        page.goto(f"http://localhost:{port}/")
        page.wait_for_timeout(600)          # let the manifest fetches settle
        cards = page.locator(".card").count()
        results = page.evaluate("""async (paths) => {
            const out = {};
            for (const path of paths) {
                try {
                    const res = await fetch(path);
                    if (!res.ok) { out[path] = `FAIL: HTTP ${res.status}`; continue; }
                    const buf = await res.arrayBuffer();
                    const ctx = new AudioContext();
                    const audio = await ctx.decodeAudioData(buf);
                    out[path] = +audio.duration.toFixed(2);
                } catch (e) { out[path] = 'FAIL: ' + e.message; }
            }
            return out;
        }""", paths)
        browser.close()

    bad = 0
    for k, v in results.items():
        ok = isinstance(v, (int, float)) and v > 1.0
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {k:<28} {v}")

    print(f"\n{len(results)} clip(s), {bad} undecodable · {cards} card(s) rendered")
    if errors:
        print(f"{len(errors)} console error(s):")
        for e in errors[:5]:
            print(f"  {e}")
    if cards < len(results):
        print(f"Only {cards} card(s) for {len(results)} clip(s) — gallery did not "
              "render everything.")
    return 1 if (bad or errors or cards < len(results)) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(GALLERY, OUT / "index.html")

    if port_taken(args.port):
        sys.exit(
            f"Port {args.port} is already answering — another server is running.\n"
            f"  Find it:  lsof -nP -iTCP:{args.port} -sTCP:LISTEN\n"
            f"  Then:     kill <PID>      (or use --port {args.port + 1})\n"
            "Refusing to start: binding anyway would serve the other server's\n"
            "files and make every clip look undecodable."
        )

    handler = functools.partial(Handler, directory=str(OUT))
    # Only for our own quick restarts; the squatter case is caught above.
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        sys.exit(f"Port {args.port} unavailable ({exc}). Try --port {args.port + 1}.")

    url = f"http://localhost:{args.port}/"
    print(f"Serving {OUT} at {url}")

    if args.verify:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        code = verify(args.port)
        httpd.shutdown()
        return code

    if not args.no_open:
        webbrowser.open(url)
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
