#!/usr/bin/env python3
"""hookcheck — lint a narration script for retention and TTS safety.

Checks the things that silently ruin a narrated video: markup edge-tts would
read aloud, characters the normaliser has to guess at, sentences too long for
the ear, and an opening that spends its first seconds on nothing.

    python3 hookcheck.py script.txt [--strict] [--json]
                         [--register feed|documentary] [--wpm N]

Exit 0 pass, 1 fail. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict

CHUNK_LIMIT = 4096

#: Narration has two registers and they want opposite things, so one set of
#: thresholds cannot serve both. `feed` is the short, hook-first cadence of
#: social video. `documentary` is the longer analytic cadence of a
#: twenty-to-thirty-minute investigation.
#:
#: The documentary numbers are measured, not guessed. Against a 4,663-word
#: investigative documentary with twenty-four million views, the `feed`
#: thresholds raise **47 errors and 95 warnings** and estimate the runtime at
#: 41m38s for a film that actually runs 29m26s. A linter that rejects the
#: benchmark is measuring the wrong thing. In that script the median sentence
#: is 16 words, the ninetieth percentile is 27, and 16% of sentences run past
#: 24 words -- so under `documentary` a long sentence is normal and only a
#: genuinely unspeakable one is an error.
REGISTERS = {
    "feed": {
        "max_sentence": 24, "warn_sentence": 16,
        "warn_opening": 12, "wpm": 112,
    },
    "documentary": {
        # Thresholds are percentiles of the measured reference, not guesses.
        # A warning at 26 fired on twelve percent of a professional script and
        # contradicted the cadence floor below, which asks for long sentences on
        # purpose. 33 is that script's ninety-seventh percentile, so it now
        # flags the genuinely unusual; 46 sits above its longest sentence and
        # stays an error because past it the engine misplaces breath.
        "max_sentence": 46, "warn_sentence": 33,
        "warn_opening": 24, "wpm": 160,
        # Cadence. Passing every other rule still permits prose that is
        # rhythmically flat — a wall of competent mid-length sentences that
        # narrates like a list. What separates the form is dynamic range: a
        # long, considered sentence that earns a short one after it. These
        # bands come from measuring a 4,663-word investigative documentary
        # (mean 16.4, 16.2% of sentences over 24 words, 16.2% under 8).
        "mean_band": (14.0, 19.0),
        "min_long_ratio": 0.08,
    },
}
DEFAULT_REGISTER = "feed"

# Spoken aloud by edge-tts because input is XML-escaped.
MARKUP = re.compile(r"<[a-zA-Z/][^>]*>|\[\[\s*slnc[^\]]*\]\]")
BRACKETS = re.compile(r"[()\[\]{}]")
DIGITS = re.compile(r"\d")
SYMBOLS = re.compile(r"[$%&@#+*/=]|\b\d+\s*(?:km|kg|ms|mm|cm|lb|oz)\b")
ABBREV = re.compile(r"\b(?:St|No|Mr|Mrs|Dr|Prof|vs|etc|approx|Ave|Rd)\.", re.I)

# Homographs the engine must disambiguate from context.
HOMOGRAPHS = {
    "read": ("has", "had", "have", "will", "to", "finished", "reads"),
    "lead": ("the", "metal", "pipes", "pipe", "paint", "a"),
    "live": ("a", "the", "was", "is", "broadcast", "show", "stream"),
    "bow": ("a", "the", "her", "his", "take", "ship", "violin"),
    "tear": ("a", "the", "her", "his", "ran", "rolled"),
    "wind": ("the", "cold", "north", "blew", "rose", "up", "down"),
    "bass": ("the", "a", "guitar", "player", "line", "drum"),
    "content": ("the", "was", "felt", "she", "he", "seemed", "of"),
    "close": ("was", "so", "too", "very", "get", "came", "stood"),
    "minute": ("a", "one", "the", "every", "last", "first"),
}

THROAT_CLEARING = (
    "hey guys", "hi guys", "what's up guys", "welcome back",
    "in this video", "today i want to", "today we're going to",
    "before we begin", "before we start", "let me just say",
    "don't forget to", "make sure to subscribe", "smash that",
)

LEVELS = ("error", "warning", "info")


@dataclass
class Finding:
    level: str
    line: int
    rule: str
    message: str


def split_sentences(text: str) -> list[tuple[int, str]]:
    """Return (line_number, sentence) pairs, ignoring ellipsis as a terminator."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        # Protect ellipses so they are not treated as sentence ends.
        guarded = line.replace("...", "\u0000")
        for part in re.split(r"(?<=[.!?])\s+", guarded):
            sentence = part.replace("\u0000", "...").strip()
            if sentence:
                out.append((lineno, sentence))
    return out


def words_in(sentence: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", sentence)


def check(text: str, wpm: int, register: str = DEFAULT_REGISTER) -> list[Finding]:
    R = REGISTERS[register]
    max_sentence = R["max_sentence"]
    warn_sentence = R["warn_sentence"]
    warn_opening = R["warn_opening"]
    findings: list[Finding] = []
    add = findings.append

    for lineno, raw in enumerate(text.splitlines(), 1):
        if m := MARKUP.search(raw):
            add(Finding("error", lineno, "markup",
                        f"edge-tts will speak this aloud: {m.group(0)!r}. "
                        "Use punctuation for timing."))
        if m := BRACKETS.search(raw):
            add(Finding("error", lineno, "brackets",
                        f"{m.group(0)!r} is unreliable in TTS. Rewrite as a sentence."))
        if m := DIGITS.search(raw):
            add(Finding("error", lineno, "digits",
                        f"Digit {m.group(0)!r} — spell it as it should be said "
                        "('twenty twenty-four', 'number five')."))
        if m := SYMBOLS.search(raw):
            add(Finding("error", lineno, "symbols",
                        f"Symbol {m.group(0)!r} — write the word instead."))
        if m := ABBREV.search(raw):
            add(Finding("error", lineno, "abbreviation",
                        f"{m.group(0)!r} — write the whole word ('Saint', 'number')."))

    sentences = split_sentences(text)

    for lineno, sentence in sentences:
        tokens = words_in(sentence)
        lowered = [t.lower() for t in tokens]
        n = len(tokens)

        if n > max_sentence:
            add(Finding("error", lineno, "sentence-length",
                        f"{n} words. Over {max_sentence} the engine misplaces "
                        f"stress. Split it."))
        elif n > warn_sentence:
            add(Finding("warning", lineno, "sentence-length",
                        f"{n} words. In the {register} register aim for "
                        f"{warn_sentence} or fewer."))

        for i, word in enumerate(lowered):
            if word in HOMOGRAPHS:
                neighbours = set(lowered[max(0, i - 2):i] + lowered[i + 1:i + 3])
                if not neighbours & set(HOMOGRAPHS[word]):
                    add(Finding("warning", lineno, "homograph",
                                f"{word!r} has two pronunciations and no disambiguating "
                                "neighbour. Rewrite the line."))

    if sentences:
        opening = sentences[0][1]
        low = opening.lower()
        for phrase in THROAT_CLEARING:
            if phrase in low:
                add(Finding("error", 1, "throat-clearing",
                            f"Opening contains {phrase!r}. Open on the story, not on preamble."))
                break
        n = len(words_in(opening))
        if n > warn_opening:
            add(Finding("warning", 1, "opening-length",
                        f"Opening sentence is {n} words. Under {warn_opening} "
                        f"lands harder in the {register} register."))
    else:
        add(Finding("error", 0, "empty", "No narration found."))

    if "..." not in text:
        add(Finding("warning", 0, "no-beats",
                    "No '...' anywhere — no engineered pause. "
                    "Punctuation is the only timing control edge-tts offers."))

    size = len(text.encode("utf-8"))
    if size > CHUNK_LIMIT:
        add(Finding("warning", 0, "chunk-size",
                    f"{size} bytes exceeds the {CHUNK_LIMIT}-byte boundary; "
                    "edge-tts may split mid-thought."))

    lengths = [len(words_in(s)) for _, s in sentences]
    lengths = [n for n in lengths if n]
    band = R.get("mean_band")
    if band and len(lengths) >= 30:
        mean = sum(lengths) / len(lengths)
        long_ratio = sum(1 for n in lengths if n > 24) / len(lengths)
        lo, hi = band
        if mean < lo:
            add(Finding("warning", 0, "cadence",
                        f"Mean sentence is {mean:.1f} words; the {register} "
                        f"register sits between {lo:.0f} and {hi:.0f}. Clipped "
                        "prose reads as a list of facts rather than an account. "
                        "Join related sentences instead of stacking them."))
        elif mean > hi:
            add(Finding("warning", 0, "cadence",
                        f"Mean sentence is {mean:.1f} words; the {register} "
                        f"register sits between {lo:.0f} and {hi:.0f}. Long "
                        "throughout is as flat as short throughout."))
        floor = R.get("min_long_ratio", 0.0)
        if long_ratio < floor:
            add(Finding("warning", 0, "cadence-range",
                        f"Only {long_ratio * 100:.1f}% of sentences run past 24 "
                        f"words; the register wants at least {floor * 100:.0f}%. "
                        "Without a long sentence to lean against, a short one "
                        "has nothing to land after."))

    total = sum(lengths)
    if total:
        secs = total / wpm * 60
        add(Finding("info", 0, "duration",
                    f"{total} words ≈ {int(secs // 60)}m {secs % 60:04.1f}s "
                    f"at {wpm} gross wpm ({register})."))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint a narration script.")
    ap.add_argument("script")
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--register", choices=sorted(REGISTERS),
                    default=DEFAULT_REGISTER,
                    help="cadence to lint against (default %s)" % DEFAULT_REGISTER)
    ap.add_argument("--wpm", type=int, default=None,
                    help="override the register's gross wpm")
    args = ap.parse_args()
    wpm = args.wpm or REGISTERS[args.register]["wpm"]

    try:
        text = open(args.script, encoding="utf-8").read()
    except OSError as exc:
        print(f"cannot read {args.script}: {exc}", file=sys.stderr)
        return 1

    findings = check(text, wpm, args.register)
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    failed = bool(errors) or (args.strict and bool(warnings))

    if args.json:
        print(json.dumps({"passed": not failed, "findings": [asdict(f) for f in findings]},
                         indent=2))
        return 1 if failed else 0

    for level in LEVELS:
        for f in (x for x in findings if x.level == level):
            where = f"line {f.line}" if f.line else "script"
            print(f"{level:>7}  {where:<9} [{f.rule}] {f.message}")

    print()
    verdict = "FAIL" if failed else "PASS"
    print(f"{verdict}  {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
