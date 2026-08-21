#!/usr/bin/env python3
"""Generate one narration clip per line.

This is the producer side of the contract with rendering skills such as
`paper-explainer`, which consume narration audio and never synthesise it.

Input is a JSON file: a list of objects with `id` and `text`.

    [ { "id": "l1", "text": "*This* is a line. [[slnc 380]] With a pause." } ]

Output is `<outdir>/<id>.wav`, one per line, plus a printed duration table.

    python3 narrate.py lines.json -o vo/ --voice en-GB-RyanNeural

`[[slnc N]]` inserts an exact N-millisecond pause. `*word*` marks emphasis for
providers that support it; edge-tts ignores it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import wave

import tts


def duration_of(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate narration clips, one per line.")
    ap.add_argument("lines", help="JSON file: [{id, text}, ...]")
    ap.add_argument("-o", "--outdir", default="vo", help="directory for the clips")
    ap.add_argument("--voice", help="provider voice name, e.g. en-GB-RyanNeural")
    ap.add_argument("--rate", help='edge rate, e.g. "-13%%"')
    ap.add_argument("--pitch", help='edge pitch, e.g. "-5Hz"')
    ap.add_argument("--provider", default="auto",
                    help="auto | edge | gemini | openai | say")
    a = ap.parse_args()

    with open(a.lines) as f:
        lines = json.load(f)

    os.makedirs(a.outdir, exist_ok=True)
    cfg = {"provider": a.provider}
    if a.voice:
        cfg["voice"] = cfg["edge_voice"] = a.voice
    if a.rate:
        cfg["edge_rate"] = a.rate
    if a.pitch:
        cfg["edge_pitch"] = a.pitch

    total = 0.0
    used = set()
    for i, ln in enumerate(lines):
        lid = ln.get("id", f"l{i + 1}")
        out = os.path.join(a.outdir, f"{lid}.wav")
        try:
            used.add(tts.synth(ln["text"], out, dict(cfg)))
        except RuntimeError as e:
            print(f"! {lid}: {e}", file=sys.stderr)
            return 1
        d = duration_of(out)
        total += d
        print(f"  {lid:>4}  {d:6.2f}s  {out}")

    print(f"\n  provider: {', '.join(sorted(used))}")
    print(f"  speech total: {total:.2f}s (gaps are added by the renderer)")
    if used <= {"say", "silent"}:
        print("  ! robotic fallback in use — install edge-tts for a natural voice")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
