#!/usr/bin/env python3
"""Regression test for language detection.

    python scripts/test_detect.py

The rules in `core.detect_lang` interact: a marker that looks safe on its own
often collides with an ordinary English word. Whenever you add or change a
marker, add a case here and run the whole set — checking only your new case is
how the previous regressions got in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import detect_lang  # noqa: E402

# (text, expected label). Grouped by the rule each case is meant to pin down.
CASES: list[tuple[str, str]] = [
    # -- no letters at all -------------------------------------------------
    ("12345 !!!", "english"),
    ("", "english"),
    ("— 2026 —", "english"),

    # -- pure Tamil script -------------------------------------------------
    ("வணக்கம். இந்த குரல் ஆங்கிலத்துல இருந்து வந்தது.", "tamil"),
    ("கோழி கொக்கரக்கோன்னு கூவுச்சு", "tamil"),
    ("நான் ஒரு கதை சொல்லப் போறேன்", "tamil"),

    # -- Tamil script + English words = tanglish ---------------------------
    ("special-ஆ இருக்கும்", "tanglish"),
    ("இன்னைக்கு ஒரு super update இருக்கு நண்பர்களே", "tanglish"),
    ("Payment status-ஐ நான் check பண்ணி சொல்றேன்", "tanglish"),
    ("உங்க booking confirm ஆயிடுச்சு சார்", "tanglish"),

    # -- romanised Tamil, no Tamil script ----------------------------------
    ("enna pannunga ippo", "tanglish"),
    ("vanakkam nanbargale", "tanglish"),
    ("appadi illa, romba nalla irukku", "tanglish"),

    # -- plain English -----------------------------------------------------
    ("Every voice here can speak any language.", "english"),
    ("This is the fastest AI voice cloning technology available today.", "english"),
    # Weak markers that are also ordinary English words. Two or more English
    # stopwords must veto them, or these get misread as Tamil.
    ("Anna and Ava ate naan with sari-wrapped gifts", "english"),
    ("The anna in the story wore a sari to the party", "english"),
]


def main() -> int:
    failed = []
    for text, expected in CASES:
        got = detect_lang(text)["label"]
        if got != expected:
            failed.append((text, expected, got))

    for text, expected, got in failed:
        shown = text if len(text) <= 46 else text[:43] + "..."
        print(f"  FAIL {shown!r}\n       expected {expected}, got {got}")

    total = len(CASES)
    print(f"\n{total - len(failed)}/{total} passing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
