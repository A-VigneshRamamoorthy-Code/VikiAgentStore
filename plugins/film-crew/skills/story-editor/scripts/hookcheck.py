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


CLOSERS = "\"'\u201d\u2019)\\]"
SENT_SPLIT = re.compile(rf"(?<=[.!?])\s+|(?<=[.!?][{CLOSERS}])\s+")


def split_sentences(text: str) -> list[tuple[int, str]]:
    """Return (line_number, sentence) pairs, ignoring ellipsis as a terminator."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        # Protect ellipses so they are not treated as sentence ends.
        guarded = line.replace("...", "\u0000")
        # A quoted sentence ends at `."`, not at `.`, so the terminator is one
        # character further left than the naive lookbehind expects. Without the
        # second alternative a line of reported speech fuses with the sentence
        # after it, and the linter then reports a "52-word sentence" that
        # nobody wrote. Each lookbehind is separately fixed-width, which is
        # what `re` requires.
        for part in re.split(SENT_SPLIT, guarded):
            sentence = part.replace("\u0000", "...").strip()
            if sentence:
                out.append((lineno, sentence))
    return out


def words_in(sentence: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", sentence)


#: `l12  Some narration.` -- the screenwriter's line id, not spoken.
LINE_ID = re.compile(r"^l\d+[a-z]*\s+")
#: `{c14}` -- a ledger claim reference, not spoken.
CLAIM_REF = re.compile(r"\{[^{}]*\}")


def parse_front(text: str) -> tuple[dict, str]:
    """Split a `---` YAML-ish frontmatter block off the front of a script.

    Only flat `key: value` pairs are read, which is all a script header ever
    holds. Anything else is left to the screenwriter's own parser.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta = {}
    for raw in text[3:end].splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip("'\"")
    return meta, text[end + 4:].lstrip("-\n")


def narration_of(text: str) -> str:
    """The spoken words only.

    `check()` measures prose: sentence length, cadence, duration. Handed a
    whole `script.md` it would lint the frontmatter and the chapter headings
    as if they were narration -- and it did, silently, reporting hundreds of
    confident errors about text nobody ever says aloud. Feeding it the file
    the pipeline actually produces has to mean the same thing as feeding it
    `scriptcheck --plain`.
    """
    _, body = parse_front(text)
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        if LINE_ID.match(line):
            out.append(LINE_ID.sub("", line))
        elif out:
            # A wrapped continuation of the line above. Left on its own row it
            # would be measured as a separate sentence, which shortens every
            # cadence statistic by exactly the amount the author wrapped.
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    cleaned = (" ".join(CLAIM_REF.sub("", ln).split()) for ln in out)
    return "\n".join(ln for ln in cleaned if ln)


def check(text: str, wpm: int, register: str = DEFAULT_REGISTER) -> list[Finding]:
    R = REGISTERS[register]
    # The error bound is a *time*, not a word count. Its own reason -- past it
    # the engine misplaces breath -- is a property of how long the sentence
    # takes to say, so a script delivered faster may legitimately carry more
    # words in the same breath. Holding it at a fixed word count made the two
    # linters contradict: at 170 wpm a 26-word feed line is well inside
    # scriptcheck's shot-duration cap yet was a hard error here, blocking a
    # script neither check actually objected to. The word figures below are
    # the measured thresholds *at each register's reference pace*; they are
    # converted to seconds once and back at the script's real pace.
    max_sentence = max(R["max_sentence"],
                       int(round(R["max_sentence"] * wpm / R["wpm"])))
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
    ap.add_argument("--register", choices=sorted(REGISTERS), default=None,
                    help="override the script's own `register:` "
                         "(default %s when the script declares none)"
                         % DEFAULT_REGISTER)
    ap.add_argument("--wpm", type=int, default=None,
                    help="override the register's gross wpm")
    args = ap.parse_args()

    try:
        raw = open(args.script, encoding="utf-8").read()
    except OSError as exc:
        print(f"cannot read {args.script}: {exc}", file=sys.stderr)
        return 1

    # Register comes from the script unless the caller overrides it. It is
    # never inferred from the pace: a memorial documentary runs slower than a
    # social vertical, so any speed threshold is wrong in both directions.
    # A script that does not declare one is linted as feed, whose tighter
    # caps fail loudly rather than quietly licensing lines nobody meant.
    meta, _ = parse_front(raw)
    register = args.register
    if register is None:
        declared = str(meta.get("register", "")).strip().lower()
        if declared and declared not in REGISTERS:
            print(f"unknown register {declared!r} in {args.script}; "
                  f"expected one of {', '.join(sorted(REGISTERS))}",
                  file=sys.stderr)
            return 1
        register = declared or DEFAULT_REGISTER

    wpm = args.wpm
    if wpm is None:
        try:
            wpm = int(float(meta["wpm"]))
        except (KeyError, TypeError, ValueError):
            wpm = REGISTERS[register]["wpm"]
    if wpm <= 0:
        print(f"wpm must be positive, got {wpm}", file=sys.stderr)
        return 1

    text = narration_of(raw)
    findings = check(text, wpm, register)
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
