#!/usr/bin/env python3
"""hookcheck — lint a narration script for retention and TTS safety.

Checks the things that silently ruin a narrated video: markup edge-tts would
read aloud, characters the normaliser has to guess at, sentences too long for
the ear, and an opening that spends its first seconds on nothing.

It also checks what the script *owes the viewer*: teases with no named payoff,
superlatives with nothing in the ledger behind them, an opening minute that is
all future tense, and loops that are opened and never paid.

    python3 hookcheck.py script.txt [--strict] [--json]
                         [--register feed|documentary] [--wpm N]

Exit 0 pass, 1 fail. Python 3.9+, standard library only.

Deliberately *not* checked: cut intervals, re-hook timers, a 70% thirty-second
threshold, a 50% APV promotion rule. Those are folklore or house preference,
and a linter that enforced them would be asserting things nobody can source.
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

# ---------------------------------------------------------------------------
# Promise and payoff.
#
# Retention is not decided by sentence length, it is decided by whether the
# script pays what it promised. These patterns look for promises made in a form
# that cannot be paid: a tease with no named subject, a superlative with no
# claim behind it, an opening minute spent entirely in the future tense, and a
# loop nobody closes.
# ---------------------------------------------------------------------------

#: Teases that name no payload. "Stay until the end" is not a promise, it is a
#: request. Loewenstein's information gap has to be a *specific* missing fact.
EMPTY_TEASE = re.compile(
    r"\b(?:"
    r"watch (?:un)?til the end|stick around (?:un)?til the end|stay (?:un)?til the end|"
    r"you won'?t believe|you'?ll never guess|wait (?:un)?til you see|"
    r"what happens next|the results? (?:will )?shock|"
    r"more on that later|but first|stay tuned"
    r")\b", re.I)

#: A superlative is a factual claim, so it needs something in the ledger. These
#: are the forms that are almost always assertions rather than idiom.
SUPERLATIVE = re.compile(
    r"\b(?:world'?s|world record|first ever|ever recorded|in history|"
    r"guaranteed|nobody has ever|no one has ever|"
    r"largest|biggest|smallest|fastest|slowest|deadliest|richest|poorest|"
    r"oldest|longest|tallest|rarest|strongest|heaviest)\b", re.I)

#: ...except when the superlative is attached to an abstract noun, where it is
#: ordinary English rather than a claim. "The biggest mistake of his life" is
#: not something the ledger can source.
SUPERLATIVE_IDIOM = re.compile(
    r"\b(?:largest|biggest|smallest|fastest|slowest|deadliest|richest|poorest|"
    r"oldest|longest|tallest|rarest|strongest|heaviest)\s+"
    r"(?:mistake|problem|fear|regret|challenge|part|thing|moment|question|"
    r"difference|risk|danger|lesson|mystery|worry|surprise|secret)\b", re.I)

#: Future-tense promotion. Fine in small doses; fatal when it is the whole
#: opening. The handbook's phrasing: "Stop telling people what they will be
#: watching and start showing them."
HYPE = re.compile(
    r"\b(?:we'?re going to|we will|i'?m going to show|i'?ll show you|you'?ll see|"
    r"coming up|by the end of this|later in this|in a moment you'?ll|"
    r"we'?re about to|get ready (?:to|for))\b", re.I)

SPONSOR = re.compile(
    r"\b(?:sponsor(?:ed|s|ing)?|brought to you by|thanks to .{0,40}? for sponsoring)\b",
    re.I)

#: Story-editor directives live on their own `>` lines.
#:
#: This matters for interoperability. The screenwriter's `scriptcheck` reads a
#: trailing `{...}` as a comma-separated list of *claim ids* and errors with
#: "cites unknown claim" on anything it cannot find in the ledger -- so an
#: inline `{loop:A:open}` would break the tool upstream of this one. A `>` line
#: matches neither its line pattern nor its continuation rule, so it is skipped
#: by `scriptcheck`, skipped by `narration_of`, and never reaches edge-tts.
#:
#:     l5  Why did the bell ring thirteen times?
#:     > loop A open
#:     l7  The thirteenth strike was a flood warning.  {c14}
#:     > loop A close
#:
#: A directive annotates the narration line immediately above it.
DIRECTIVE_LINE = re.compile(r"^>\s*(.+?)\s*$")
LOOP_DIRECTIVE = re.compile(r"^loop\s+([A-Za-z0-9_-]+)\s+(open|progress|close)$", re.I)
EXEC_DIRECTIVE = re.compile(r"^execution$", re.I)
PAYOFF_DIRECTIVE = re.compile(r"^payoff\s*:\s*\S.*$", re.I)
SPONSOR_DIRECTIVE = re.compile(r"^sponsor\s*:\s*story-bridge$", re.I)

#: `{c14}` -- a claim the researcher's ledger can source. Already the pipeline's
#: convention, so the superlative check reuses it rather than inventing one.
CLAIM_MARKER = re.compile(r"\{[^{}]*\bc\d+\b[^{}]*\}", re.I)

#: A new loop opened this late demands an answer the film has no room to give.
LATE_LOOP_FRACTION = 0.9

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


def scan_script(raw: str) -> tuple[list[dict], int]:
    """Walk the narration, returning its lines and the total spoken words.

    Each entry is ``{"line", "text", "words_before", "directives"}`` where
    ``line`` numbers the *narration*, matching every other finding this file
    emits, and ``directives`` holds the `>` annotations attached to that line.
    Word positions let "the opening minute" and "the final tenth" be computed
    without ever consulting a byte offset.
    """
    _, body = parse_front(raw)
    lines: list[dict] = []
    words = 0
    for source in body.splitlines():
        stripped = source.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if m := DIRECTIVE_LINE.match(stripped):
            if lines:
                lines[-1]["directives"].append(m.group(1))
            else:
                # A directive before any narration still needs a home, so that
                # a loop opened at the very top is not silently dropped.
                lines.append({"line": 0, "text": "", "words_before": 0,
                              "directives": [m.group(1)]})
            continue
        if LINE_ID.match(stripped):
            text = LINE_ID.sub("", stripped)
        elif lines and lines[-1]["text"]:
            lines[-1]["text"] += " " + stripped
            words += len(words_in(CLAIM_REF.sub("", stripped)))
            continue
        else:
            text = stripped
        lines.append({"line": len(lines) + 1, "text": text,
                      "words_before": words, "directives": []})
        words += len(words_in(CLAIM_REF.sub("", text)))
    for index, entry in enumerate(lines, 1):
        entry["line"] = index
    return lines, words


def check_promises(raw: str, wpm: int) -> list[Finding]:
    """Lint what the script owes the viewer.

    Everything here is about promises: made in a payable form, and then paid.
    None of it is a cadence rule -- there is no evidence for re-hook timers or
    cut intervals, so this function does not pretend otherwise.
    """
    findings: list[Finding] = []
    add = findings.append

    lines, total_words = scan_script(raw)
    if not lines:
        return findings

    def has(entry: dict, pattern: re.Pattern) -> bool:
        return any(pattern.match(d) for d in entry["directives"])

    uses_ledger = any(CLAIM_MARKER.search(e["text"]) for e in lines)

    for entry in lines:
        text = entry["text"]
        if not text:
            continue

        if not has(entry, PAYOFF_DIRECTIVE):
            if m := EMPTY_TEASE.search(text):
                add(Finding("warning", entry["line"], "empty-tease",
                            f"{m.group(0)!r} promises nothing specific. Name "
                            "the payload, or annotate the line `> payoff: "
                            "what it pays`."))

        if not CLAIM_MARKER.search(text):
            for m in SUPERLATIVE.finditer(text):
                window = text[max(0, m.start() - 40):m.end() + 40]
                if SUPERLATIVE_IDIOM.search(window):
                    continue
                add(Finding("warning" if uses_ledger else "info",
                            entry["line"], "unsupported-superlative",
                            f"{m.group(0)!r} is a factual claim with no claim "
                            "reference on the line. Cite it or soften it."))
                break

    if not any(has(e, SPONSOR_DIRECTIVE) for e in lines):
        for entry in lines:
            if entry["text"] and SPONSOR.search(entry["text"]):
                add(Finding("warning", entry["line"], "sponsor-reset",
                            "A sponsor mention with no story bridge is an "
                            "exit. Make the sentence before it create a need "
                            "the segment answers, then annotate it "
                            "`> sponsor: story-bridge`."))
                break

    # Hype without execution. The opening can promise, but it cannot be *only*
    # promises -- "stop telling people what they will be watching and start
    # showing them". In a script shorter than a minute the whole script is the
    # opening, which is why this is a cap and not a guard: a Short that never
    # stops promising is the worst case, not an exempt one.
    opening_words = min(wpm, total_words)
    hype_hits: list[str] = []
    executed = False
    for entry in lines:
        if entry["words_before"] >= opening_words:
            break
        if has(entry, EXEC_DIRECTIVE):
            executed = True
        hype_hits.extend(m.group(0) for m in HYPE.finditer(entry["text"]))
    if len(hype_hits) >= 2 and not executed:
        shown = ", ".join(repr(h) for h in hype_hits[:3])
        add(Finding("warning", 1, "hype-without-execution",
                    f"The opening minute is {len(hype_hits)} promises of what "
                    f"is coming ({shown}) and no execution. Show the thing, "
                    "or annotate the beat `> execution`."))

    # The loop ledger. The one hard rule here: a loop without a close is an
    # unpaid promise, and there is no third option.
    state: dict[str, str] = {}
    opened_at: dict[str, int] = {}
    opened_on: dict[str, int] = {}
    for entry in lines:
        for directive in entry["directives"]:
            m = LOOP_DIRECTIVE.match(directive)
            if not m:
                continue
            name, phase = m.group(1), m.group(2).lower()
            lineno = entry["line"]
            if phase == "open":
                if name in state:
                    add(Finding("error", lineno, "loop-ledger",
                                f"Loop {name!r} is opened twice. Give the "
                                "second question its own name."))
                else:
                    state[name] = "open"
                    opened_at[name] = entry["words_before"]
                    opened_on[name] = lineno
            elif phase == "progress":
                if name not in state:
                    add(Finding("error", lineno, "loop-ledger",
                                f"Loop {name!r} progresses before it is opened."))
                elif state[name] == "closed":
                    add(Finding("error", lineno, "loop-ledger",
                                f"Loop {name!r} progresses after it is closed."))
            else:
                if name not in state:
                    add(Finding("error", lineno, "loop-ledger",
                                f"Loop {name!r} closes before it is opened."))
                elif state[name] == "closed":
                    add(Finding("error", lineno, "loop-ledger",
                                f"Loop {name!r} is closed twice. The second "
                                "close pays a promise nobody is still owed."))
                else:
                    state[name] = "closed"

    for name, status in sorted(state.items()):
        if status != "closed":
            add(Finding("error", opened_on.get(name, 0), "loop-ledger",
                        f"Loop {name!r} is opened and never closed. Write the "
                        "payoff or cut the loop."))

    if total_words:
        threshold = total_words * LATE_LOOP_FRACTION
        for name, position in sorted(opened_at.items()):
            if position >= threshold:
                add(Finding("warning", opened_on.get(name, 0), "late-loop",
                            f"Loop {name!r} opens in the final tenth of the "
                            "script. A question raised this late cannot be "
                            "answered properly -- close the film instead."))

    return findings


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
    findings.extend(check_promises(raw, wpm))
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
