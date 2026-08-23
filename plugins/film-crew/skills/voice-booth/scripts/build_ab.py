#!/usr/bin/env python3
"""Compare Tamil references head-to-head on one line, and rank them.

    python scripts/build_ab.py

Answers the question "which reference gives the best Tamil pronunciation?"
by synthesizing the *same* line from every candidate and measuring round-trip
intelligibility. Writes `out/ab/manifest.json` for the gallery so the ranking
can be checked by ear, not just read.

Why this exists: a clone can pass every acoustic check — right pitch, no gaps,
silent noise floor, timbre matched to source — and still pronounce Tamil badly.
Nothing in `analyze.py` sees that. Comparing candidates on identical text does.

The line is deliberately colloquial Chennai Tamil with Tanglish and dramatic
pauses, because that is the register that exposes unnatural delivery. Literary
Tamil hides it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    load_model, master, measure, median_f0, pitch_range_st, prepare_ref, synth,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "ab"
EDGE_REFS = ROOT / "out" / "edge_refs"
PREPARED = ROOT / "out" / "refs"
VOICE_REF = ROOT.parents[3] / "voice-reference"

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

# A single line is not enough to rank references: on one line Pallavi scored
# 85.0% and on another 93.4%, which reversed the whole order. Scoring is
# therefore averaged over several lines in different registers, and the
# per-line spread is reported so the noise stays visible.
LINES = [
    ("dramatic",
     "சரி... இப்போ நான் சொல்ல போற விஷயம் இருக்கே, அது கொஞ்சம் shock-ஆ இருக்கும். "
     "ஆனா... அன்னைக்கு நடந்தது யாருமே எதிர்பார்க்காத ஒண்ணு. என்ன நடந்துச்சு?"),
    ("greeting",
     "வணக்கம் நண்பர்களே! இன்னைக்கு நான் சொல்ல போற விஷயம் கொஞ்சம் special-ஆ இருக்கும். "
     "தமிழ்ல ஒரு அழகான கதை. கேட்க தயாரா?"),
    ("plain",
     "சிங்கம் காட்டுக்குள்ள மெதுவா நடந்து போச்சு. தங்கம் மாதிரி பளபளன்னு வெயில் அடிச்சுது. "
     "அவங்க ரெண்டு பேரும் அங்க தான் இருந்தாங்க."),
]
LINE = LINES[0][1]

EL_MALE_TEXT = ("அன்னைக்கி காலையிலா ஆறு மணி இருக்கும். கோழி கொக்கரக்கோன்னு கூவுச்சு. "
                "ElevenLabs பேமன்ட் வரும்ன்னு wait பண்ணிட்டிருந்தேன். ஒன்னும் வரல.")
EL_MALE_TRIM_TEXT = "அன்னைக்கி காலையிலா ஆறு மணி இருக்கும். கோழி கொக்கரக்கோன்னு கூவுச்சு."
EL_FEM_TEXT = ("ஒரு அழகான காட்டில், குட்டியானை அப்பு ஜாலியா நடந்து போய்ட்டு இருந்துச்சாம். "
               "அப்போ திடீர்னு ஒரு பெரிய சிங்கம் வந்துச்சாம்.")

# (key, title, ref_audio | None, ref_text, note, denoise_output)
# denoise_output mirrors what build_cast.py does for that character, so the
# comparison reflects the real pipeline: real recordings get it, synthetic
# Edge/no-reference material is already silent and would only be dulled.
TRIALS = [
    ("el_male_trim", "ElevenLabs Tamil male — trimmed reference",
     PREPARED / "karthik.wav", EL_MALE_TRIM_TEXT,
     "same speaker as el_male, reference cut to its clean Tamil-only 4 s "
     "(ref_trim) — the single biggest pronunciation win measured here", True),
    ("valluvar", "Edge Valluvar (ta-IN, male)",
     EDGE_REFS / "valluvar.wav", LINE,
     "native Indian Tamil TTS as the reference", False),
    ("pallavi", "Edge Pallavi (ta-IN, female)",
     EDGE_REFS / "pallavi.wav", LINE,
     "native Indian Tamil TTS as the reference", False),
    ("noref", "No reference (model's own voice)",
     None, "",
     "keeps the model's native Tamil prosody, but the identity is not yours", False),
    ("el_male", "ElevenLabs Tamil male — full reference",
     VOICE_REF / "tamil-male.mp3", EL_MALE_TEXT,
     "the untrimmed original: its last sentences are code-mixed English, so "
     "ref_text only matches the audio ~76% and the clone rushes", True),
    ("el_female", "ElevenLabs Tamil female",
     VOICE_REF / "tamil-female.mp3", EL_FEM_TEXT,
     "your supplied reference", True),
]

# Mirrors templates/characters.json so the A/B reflects the shipped cast.
REF_TRIM = {"el_male_trim": (0.0, 3.98)}

_STRIP = re.compile(r"[^\w\u0b80-\u0bff]+")


def normalise(s: str) -> str:
    return " ".join(_STRIP.sub(" ", s.lower()).split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-synth", action="store_true",
                    help="re-measure existing clips instead of regenerating")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    missing = [t[0] for t in TRIALS if t[2] is not None and not t[2].exists()]
    if missing and not args.skip_synth:
        print(f"missing reference audio for: {', '.join(missing)}", file=sys.stderr)
        print("Build the references first:\n"
              "  python scripts/build_cast.py --characters "
              "templates/characters.json --only karthik,valluvar,pallavi",
              file=sys.stderr)
        return 2

    model = None
    if not args.skip_synth:
        print("Loading OmniVoice...")
        model = load_model()
        print(f"Synthesizing {len(LINES)} lines from each reference...\n")

    import mlx_whisper
    entries = []

    for key, title, ref, ref_text, note, denoise_out in TRIALS:
        # Every raw recording goes through prepare_ref first, exactly as
        # build_cast.py does. Comparing a prepared reference against an
        # unprepared one measures the preparation, not the reference.
        use_ref = ref
        if ref is not None and ref.suffix.lower() != ".wav":
            use_ref = OUT / f"_ref_{key}.wav"
            prepare_ref(ref, use_ref, denoise=True, quiet=True,
                        trim=REF_TRIM.get(key))

        per_line, kept_mp3, heard_first = [], None, ""
        for tag, line in LINES:
            mp3 = OUT / (f"{key}.mp3" if tag == LINES[0][0] else f"_{key}_{tag}.mp3")
            if model is not None:
                raw = OUT / f"_{key}_{tag}.wav"
                try:
                    synth(model, line, "ta", use_ref, ref_text, raw)
                except Exception as exc:                  # noqa: BLE001
                    print(f"  FAIL {key}/{tag}: {exc}", file=sys.stderr)
                    continue
                master(raw, mp3, extra_denoise=denoise_out)
                raw.unlink(missing_ok=True)
            if not mp3.exists():
                continue

            heard = mlx_whisper.transcribe(
                str(mp3), path_or_hf_repo=WHISPER_MODEL,
                language="ta", verbose=False)["text"].strip()
            score = difflib.SequenceMatcher(
                None, normalise(line), normalise(heard)).ratio() * 100
            per_line.append({"line": tag, "match": round(score, 1), "heard": heard})
            if tag == LINES[0][0]:
                kept_mp3, heard_first = mp3, heard

        if not per_line or kept_mp3 is None:
            continue
        scores = [p["match"] for p in per_line]
        mean = sum(scores) / len(scores)

        m = measure(kept_mp3)
        entries.append({
            "key": key, "name": title, "file": f"{key}.mp3", "note": note,
            "match": round(mean, 1),
            "spread": round(max(scores) - min(scores), 1),
            "per_line": per_line, "heard": heard_first,
            "spread_st": pitch_range_st(median_f0(kept_mp3)), **m,
        })
        print(f"  {title:<44} {mean:>5.1f}%  (±{(max(scores)-min(scores))/2:>4.1f})"
              f"  {m['dur']:>5}s  {m['f0']:>6} Hz")

    entries.sort(key=lambda e: -e["match"])
    for junk in OUT.glob("_*"):
        junk.unlink(missing_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(
        {"lines": [{"tag": t, "text": l} for t, l in LINES],
         "line": LINE, "variants": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"\n-> {OUT / 'manifest.json'}")
    if entries:
        print(f"best: {entries[0]['name']} ({entries[0]['match']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
