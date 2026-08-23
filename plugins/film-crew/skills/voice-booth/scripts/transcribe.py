#!/usr/bin/env python3
"""Transcribe a reference clip to get its exact --ref-text.

    python scripts/transcribe.py me.m4a
    python scripts/transcribe.py me.m4a --words     # word-level timings

OmniVoice aligns a reference against its transcript, so a wrong or approximate
ref_text noticeably degrades the clone. Word timings are useful when a clip is
longer than REF_MAX_S and you need to know where to cut without splitting a word.

Note: mlx_audio's bundled Whisper cannot be used here — the mlx-community repo
is missing preprocessor_config.json and raises "Processor not found". The
standalone mlx-whisper package works.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--words", action="store_true", help="print word-level timings")
    ap.add_argument("--lang", help="force a language instead of detecting")
    args = ap.parse_args()

    if not args.audio.exists():
        sys.exit(f"Not found: {args.audio}")

    try:
        import mlx_whisper
    except ImportError:
        sys.exit("mlx-whisper not installed. Run: bash scripts/setup.sh")

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "in.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(args.audio),
                        "-ac", "1", "-ar", "16000", str(wav)], check=True)

        kw = {"path_or_hf_repo": MODEL, "word_timestamps": args.words}
        if args.lang:
            kw["language"] = args.lang
        result = mlx_whisper.transcribe(str(wav), **kw)

    print(f"language: {result.get('language')}\n")
    print(result["text"].strip())

    if args.words:
        print("\nword timings:")
        for seg in result["segments"]:
            for w in seg.get("words", []):
                print(f"  {w['start']:6.2f}-{w['end']:6.2f}  {w['word']}")
        print("\nCut at a word boundary, then trim ref_text to match exactly.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
