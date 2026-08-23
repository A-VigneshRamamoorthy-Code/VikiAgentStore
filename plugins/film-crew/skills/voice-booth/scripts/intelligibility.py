#!/usr/bin/env python3
"""Round-trip intelligibility: does the audio still say what you asked for?

    python scripts/intelligibility.py --text "…" out/ab/*.mp3
    python scripts/intelligibility.py --text-file line.txt --lang ta clip.mp3

Synthesize -> transcribe -> compare against the intended text. It is the only
objective proxy this skill has for *pronunciation*, which every other check
misses: pitch, noise floor, gaps and timbre are all perfect on a clip that
mispronounces every other word.

Whisper mishears Tamil too, so the absolute number is meaningless — **only the
ranking between clips of the same text is meaningful.** Always compare
variants, never judge one clip alone.

Measured on one Tamil line (higher is better):

    Pallavi clone        91.5%
    Valluvar clone       88.8%
    no reference         88.2%
    ElevenLabs male      86.7%
    + instruct            0.0%   degenerate: "நான் நான் நான்…"
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

_STRIP = re.compile(r"[^\w\u0b80-\u0bff]+")


def normalise(s: str) -> str:
    """Content only — case, punctuation and spacing are not pronunciation."""
    return " ".join(_STRIP.sub(" ", s.lower()).split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--text", help="the text the clips were asked to say")
    ap.add_argument("--text-file", type=Path)
    ap.add_argument("--lang", default="ta", help="ta or en (default ta)")
    ap.add_argument("--show", action="store_true",
                    help="print what Whisper actually heard")
    args = ap.parse_args()

    if not (args.text or args.text_file):
        return ap.error("provide --text or --text-file")
    target = (args.text_file.read_text(encoding="utf-8") if args.text_file else args.text).strip()
    tgt = normalise(target)

    files = [f for f in args.files if f.exists()]
    if not files:
        print("no files found", file=sys.stderr)
        return 2

    import mlx_whisper

    rows = []
    for f in files:
        result = mlx_whisper.transcribe(
            str(f), path_or_hf_repo=WHISPER_MODEL,
            language=args.lang, verbose=False)
        heard = result["text"].strip()
        score = difflib.SequenceMatcher(None, tgt, normalise(heard)).ratio() * 100
        rows.append((score, f.stem, heard))

    rows.sort(reverse=True)
    width = max(len(r[1]) for r in rows) + 2
    print(f"{'clip':<{width}}{'match':>8}")
    for score, name, heard in rows:
        print(f"{name:<{width}}{score:>7.1f}%")
        if args.show:
            print(f"{'':<{width}}{heard[:90]}")

    if len(rows) > 1:
        best, worst = rows[0], rows[-1]
        print(f"\nbest: {best[1]} ({best[0]:.1f}%) · "
              f"worst: {worst[1]} ({worst[0]:.1f}%) · "
              f"spread {best[0] - worst[0]:.1f} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
