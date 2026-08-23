#!/usr/bin/env python3
"""Check each character's ref_text actually matches its reference audio.

    python scripts/check_refs.py --characters templates/characters.json

OmniVoice aligns the reference audio against `ref_text`. When they disagree the
clone inherits the misalignment: it rushes, slurs, or drops syllables. This is
rule 3 of the skill ("never blindly truncate a reference"), made checkable.

The clip is transcribed with Whisper and compared to the stored text. The score
is a similarity ratio, not a grade — Whisper mishears Tamil too, so treat it as
a **relative** signal:

    >= 90%   fine
    80-90%   worth reading the diff
    <  80%   suspect; this predicted the worst-sounding clone in the cast

**Whisper is systematically worse at colloquial Tamil than at English**, so the
threshold is language-aware. A Tamil reference can score in the mid-70s while
being perfectly aligned: the shipped `karthik` scores 76.2 %, but every word is
correct and only the spelling differs (`ஆறு`/`ஆரு`, `மணி`/`மனி`), and its clone is
the *best* in the cast — 94.2 % round-trip intelligibility and 0.9 % F0 drift.

So: **always read the diff before changing a ref_text.** If the words match and
only the orthography differs, the reference is fine. If whole phrases are missing
or a different language appears, it is not.

Characters built from `source_voice` are skipped: their reference is generated
from the very text stored as ref_text, so it matches by construction.

Characters with `ref_trim` are checked against the **trimmed** span, not the
whole source file — otherwise every trimmed reference reports a false SUSPECT
because ref_text deliberately covers only part of the original recording.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

GOOD = 90.0
SUSPECT = 80.0

# Whisper's own error rate on colloquial Tamil is high enough that a correctly
# aligned Tamil reference lands in the mid-70s. Holding Tamil to the English bar
# produces false positives and tempts you into "fixing" a good reference.
SUSPECT_BY_LANG = {"en": 80.0, "ta": 70.0}
GOOD_BY_LANG = {"en": 90.0, "ta": 85.0}

# Compare content, not orthography: case, punctuation and spacing differences
# are not misalignments.
_STRIP = re.compile(r"[^\w\u0b80-\u0bff]+")


def normalise(s: str) -> str:
    return " ".join(_STRIP.sub(" ", s.lower()).split())


def trimmed_copy(src: Path, trim: list[float], tmp: Path) -> Path:
    """Cut `src` to the ref_trim window so ref_text is compared against the
    audio the model will actually be given."""
    start, end = trim
    out = tmp / f"{src.stem}_trim.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ss", str(start), "-t", str(max(0.0, end - start)),
         "-ac", "1", "-ar", "24000", str(out)],
        check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--characters", type=Path, required=True)
    ap.add_argument("--only", help="check just this key")
    args = ap.parse_args()

    chars = json.loads(args.characters.read_text(encoding="utf-8"))["characters"]
    if args.only:
        chars = [c for c in chars if c["key"] == args.only]

    # Match build_cast.py: a relative ref_audio is relative to the characters
    # file, not to wherever this happens to be run from.
    base = args.characters.resolve().parent
    for c in chars:
        ref = c.get("ref_audio")
        if ref:
            p = Path(ref).expanduser()
            c["ref_audio"] = str(p if p.is_absolute() else (base / p).resolve())

    todo = [c for c in chars if c.get("ref_audio")]
    skipped = [c["key"] for c in chars if not c.get("ref_audio")]
    if not todo:
        print("Nothing to check — no character uses ref_audio.")
        return 0

    import mlx_whisper

    print(f"{'character':<14}{'match':>8}   verdict")
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for c in todo:
            src = Path(c["ref_audio"]).expanduser()
            if not src.exists():
                print(f"{c['key']:<14}{'—':>8}   MISSING {src}")
                rows.append((c["key"], 0.0, "", 100.0))
                continue
            clip = src
            note = ""
            if c.get("ref_trim"):
                clip = trimmed_copy(src, c["ref_trim"], tmp)
                a, b = c["ref_trim"]
                note = f" (trimmed {a:g}-{b:g}s)"
            # `language` is the character's native language; the reference is in it.
            result = mlx_whisper.transcribe(
                str(clip), path_or_hf_repo=WHISPER_MODEL,
                language=c["lang"], verbose=False)
            heard = result["text"].strip()
            score = difflib.SequenceMatcher(
                None, normalise(c["ref_text"]), normalise(heard)).ratio() * 100
            good = GOOD_BY_LANG.get(c["lang"], GOOD)
            floor = SUSPECT_BY_LANG.get(c["lang"], SUSPECT)
            verdict = ("ok" if score >= good
                       else "check" if score >= floor else "SUSPECT")
            print(f"{c['key']:<14}{score:>7.1f}%   {verdict}{note}")
            rows.append((c["key"], score, heard, floor))

    bad = [(k, s, h) for k, s, h, floor in rows if s < floor]
    for key, _score, heard in bad:
        stored = next(c["ref_text"] for c in todo if c["key"] == key)
        print(f"\n--- {key} ---\n  stored: {stored}\n  heard : {heard}")

    if skipped:
        print(f"\nskipped (generated from ref_text): {', '.join(skipped)}")
    print(f"\n{len(rows)} checked, {len(bad)} suspect")
    if bad:
        print("Read the diff before editing anything: if the words match and only\n"
              "the spelling differs, Whisper misheard and the reference is fine.\n"
              "If whole phrases are missing or another language appears, fix the\n"
              "ref_text, or set ref_trim to keep only the part that matches.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
