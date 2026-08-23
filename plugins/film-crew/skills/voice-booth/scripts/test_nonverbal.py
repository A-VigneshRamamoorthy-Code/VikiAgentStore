#!/usr/bin/env python3
"""Regression test for nonverbal tag checking.

    python scripts/test_nonverbal.py

`core.unknown_nonverbal` exists to catch a *silent* failure: OmniVoice performs
`[sigh]` as a sound, but reads any bracket it does not recognise aloud as words.
The audio comes out valid, just wrong, so nothing downstream can flag it.

Two things are checked here:

1. the expected verdict for each case, and
2. that the verdict **agrees with OmniVoice's own regex**.

(2) is the one that matters. The checker is only useful while it mirrors the
model exactly — matching is case-sensitive and whitespace-free because the
model's pattern is. If a future checkpoint changes its tag list, this test fails
instead of the skill quietly warning about tags that are actually fine.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import NONVERBAL_TAGS, nonverbal_hint, unknown_nonverbal  # noqa: E402

BRACKETS = re.compile(r"\[[^\[\]]*\]")

# (text, tags expected to be spoken as words rather than performed)
CASES: list[tuple[str, list[str]]] = [
    # -- no brackets -------------------------------------------------------
    ("No brackets at all.", []),
    ("", []),

    # -- real tags pass through --------------------------------------------
    ("She paused. [sigh] Then went on.", []),
    ("[question-ah] really?", []),
    ("[laughter] that's the one", []),

    # -- plausible but unsupported ----------------------------------------
    ("Wait [pause] then speak.", ["[pause]"]),
    ("[breath] then [pause]", ["[breath]", "[pause]"]),
    ("[]", ["[]"]),

    # -- deduplicated, order preserved ------------------------------------
    ("[pause] and [pause] again", ["[pause]"]),

    # -- case and spacing: the model is strict, so we must be too ----------
    ("[laughter] yes! [LAUGHTER] again", ["[LAUGHTER]"]),
    ("[Sigh] capitalised", ["[Sigh]"]),
    ("[ sigh ] spaced", ["[ sigh ]"]),

    # -- Tamil script around the tags --------------------------------------
    ("வணக்கம் [sigh] நண்பர்களே", []),
    ("வணக்கம் [nirutham] நண்பர்களே", ["[nirutham]"]),
]

# Tags that should produce a "did you mean" hint rather than a bare warning.
HINT_CASES: list[tuple[str, bool]] = [
    ("[Sigh]", True),
    ("[ sigh ]", True),
    ("[LAUGHTER]", True),
    ("[pause]", False),
    ("[]", False),
]


def model_pattern():
    """OmniVoice's own nonverbal regex, or None if it cannot be imported."""
    try:
        from mlx_audio.tts.models.omnivoice.omnivoice import _NONVERBAL_PATTERN
    except Exception:                                  # noqa: BLE001
        return None
    return _NONVERBAL_PATTERN


def main() -> int:
    failed: list[str] = []

    for text, expected in CASES:
        got = unknown_nonverbal(text)
        if got != expected:
            shown = text if len(text) <= 40 else text[:37] + "..."
            failed.append(f"  FAIL {shown!r}\n       expected {expected}, got {got}")

    for tag, wants_hint in HINT_CASES:
        hint = nonverbal_hint(tag)
        if bool(hint) != wants_hint:
            failed.append(f"  FAIL hint for {tag!r}: expected "
                          f"{'a hint' if wants_hint else 'none'}, got {hint!r}")

    # The important check: do we agree with the model itself?
    pattern = model_pattern()
    if pattern is None:
        print("  note: mlx_audio not importable — skipped the cross-check "
              "against OmniVoice's regex")
    else:
        for text, _ in CASES:
            truth = [b for b in dict.fromkeys(BRACKETS.findall(text))
                     if not pattern.fullmatch(b)]
            got = unknown_nonverbal(text)
            if got != truth:
                failed.append(f"  FAIL disagrees with OmniVoice on {text!r}\n"
                              f"       model would speak {truth}, we report {got}")
        # And that our tag list is exactly the model's.
        listed = sorted(NONVERBAL_TAGS)
        actual = sorted(t for t in pattern.pattern
                        .replace("\\[(", "").replace(")\\]", "").split("|"))
        if listed != actual:
            failed.append(f"  FAIL NONVERBAL_TAGS drifted from the model\n"
                          f"       ours:  {listed}\n       model: {actual}")

    for f in failed:
        print(f)

    total = len(CASES) + len(HINT_CASES) + (0 if pattern is None else len(CASES) + 1)
    print(f"\n{total - len(failed)}/{total} passing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
