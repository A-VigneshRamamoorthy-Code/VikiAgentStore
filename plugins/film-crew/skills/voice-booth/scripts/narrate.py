#!/usr/bin/env python3
"""Generate one narration clip per line.

This is the producer side of the contract with rendering skills such as
`paper style`, which consume narration audio and never synthesise it.

Input is a JSON file: a list of objects with `id` and `text`.

    [ { "id": "l1", "text": "*This* is a line. [[slnc 380]] With a pause." } ]

Output is `<outdir>/<id>.wav`, one per line, plus a printed duration table.

    python3 narrate.py lines.json -o vo/ --voice en-GB-RyanNeural

It also writes `<outdir>/voice.json`, recording the voice, rate and pitch each
clip was actually made with. Nothing else in the pipeline stores this, so
without it a finished film cannot be matched — adding one line months later
means guessing at the settings, and a clip in the wrong voice is obvious.

The record is **per clip and merged, never overwritten**, because re-running
this on a handful of ids is the normal way to patch a film. A whole-file
rewrite would leave the sidecar claiming the entire film used whatever the last
patch used, which is worse than recording nothing at all.

`[[slnc N]]` inserts an exact N-millisecond pause. `*word*` marks emphasis for
providers that support it; edge-tts ignores it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import wave

import tts


def duration_of(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


SIDECAR = "voice.json"


def record_voices(outdir: str, made: dict) -> str:
    """Merge this run's clips into the outdir's voice record.

    Read-modify-write rather than a plain dump: patching four lines of a
    hundred-line film must not erase what the other ninety-six were made with.
    A corrupt or hand-mangled sidecar is rebuilt from this run rather than
    killing it -- losing the older entries is bad, but refusing to narrate is
    worse, and the entries we do have are still correct.
    """
    path = os.path.join(outdir, SIDECAR)
    doc = {"schema": 1, "clips": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
        if isinstance(old, dict) and isinstance(old.get("clips"), dict):
            doc = old
            doc.setdefault("schema", 1)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        print("  ! %s was unreadable (%s); rewriting it from this run only"
              % (SIDECAR, e), file=sys.stderr)

    doc["clips"].update(made)
    doc["updated"] = _utcnow()

    # A film narrated in one voice is the common case and the one people ask
    # about, so answer it directly instead of making them diff the clips.
    keys = ("provider", "voice", "rate", "pitch")
    settings = {tuple(c.get(k) for k in keys) for c in doc["clips"].values()}
    if len(settings) == 1:
        doc["settings"] = dict(zip(keys, settings.pop()))
    else:
        doc.pop("settings", None)
        doc["mixed_settings"] = True

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


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
    made = {}
    for i, ln in enumerate(lines):
        lid = ln.get("id", f"l{i + 1}")
        out = os.path.join(a.outdir, f"{lid}.wav")
        try:
            provider = tts.synth(ln["text"], out, dict(cfg))
            used.add(provider)
        except RuntimeError as e:
            print(f"! {lid}: {e}", file=sys.stderr)
            return 1
        d = duration_of(out)
        total += d
        made[lid] = {"provider": provider, "voice": a.voice, "rate": a.rate,
                     "pitch": a.pitch, "seconds": round(d, 3)}
        print(f"  {lid:>4}  {d:6.2f}s  {out}")

    print(f"\n  provider: {', '.join(sorted(used))}")
    print(f"  speech total: {total:.2f}s (gaps are added by the renderer)")
    print(f"  recorded settings for {len(made)} clip(s) -> "
          f"{record_voices(a.outdir, made)}")
    if used <= {"say", "silent"}:
        print("  ! robotic fallback in use — install edge-tts for a natural voice")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
