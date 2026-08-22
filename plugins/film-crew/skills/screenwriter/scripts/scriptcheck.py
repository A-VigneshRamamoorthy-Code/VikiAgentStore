#!/usr/bin/env python3
"""Lint a research-backed narration script.

Checks that the script fits its runtime, that every spoken fact is bound to a
claim in the fact ledger, that every claim is sourced at least twice, and that
contested figures are hedged.

    python3 scriptcheck.py script.md
    python3 scriptcheck.py script.md --strict     # warnings are fatal
    python3 scriptcheck.py script.md --json       # machine-readable report
    python3 scriptcheck.py script.md --plain      # narration only, for TTS

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# --------------------------------------------------------------------- config

#: A contested claim has to stay contested in the narration, and there are two
#: different ways a claim is contested. Sometimes the *quantity* is disputed
#: and the honest form is a range. Sometimes the *fact itself* is disputed,
#: unproven or merely asserted by somebody -- and there the honest form is to
#: say who says it, or to say plainly that nobody knows.
#:
#: Only the first family used to count, which pushed writers toward nonsense:
#: there is no "roughly" available for "the wording of the note cannot be
#: established". Refusing to assert is a stronger hedge than approximating,
#: not a weaker one, so it is recognised here.
QUANTITY_HEDGES = [
    "at least", "about", "around", "roughly", "more than", "nearly", "some",
    "an estimated", "estimated", "up to", "over", "approximately",
    "in excess of", "close to", "at most", "fewer than", "as many as",
    "nearer to", "or so", "somewhere around", "a shade", "thereabouts",
]

#: Attribution and admitted uncertainty. Each of these either names whose
#: assertion it is, or concedes the limit of what is known. A bare "claimed"
#: or "reportedly" is deliberately absent -- an unattributed passive is how a
#: rumour gets laundered into a fact.
EPISTEMIC_HEDGES = [
    "we do not know", "we don't know", "nobody knows", "no one knows",
    "cannot be established", "never been established", "never been found",
    "not been confirmed", "unconfirmed", "never confirmed",
    "disputed", "contested", "alleged", "allegedly",
    "according to", "said to be", "described as", "apparently",
    "may have", "might have", "is believed", "was believed", "thought to be",
    "argued", "argue", "disagreed", "disagree", "denied", "deny",
    "asserted", "assert", "suggested", "suggests", "suggesting",
    "put forward", "put his name forward", "put that name forward",
    "described him as", "described her as", "described them as",
    "proposed", "leans toward", "his own account",
    "her own account", "told reporters", "publicly said", "said publicly",
    "not everyone", "some argued", "one account",
    # Plain uncertainty. These are the words a careful narrator actually
    # reaches for, and leaving them out pushes the writer toward a flat
    # assertion of something the ledger records as unsettled.
    "possible", "possibly", "not likely", "unlikely", "uncertain",
    "no way to know", "cannot say", "remains open", "never resolved",
    "has not been", "have not been", "if he", "whether he", "whether she",
]

HEDGES = QUANTITY_HEDGES + EPISTEMIC_HEDGES

DRAMATISING = [
    "massacre", "slaughter", "carnage", "bloodbath", "butcher", "bloodshed",
    "horrific", "chilling", "terrifying", "shocking", "brutal", "savage",
    "cold-blooded", "evil", "monster", "mastermind", "stormed", "unleashed",
    "rampage", "hail of bullets", "war zone", "miraculously", "tragically",
    "heartbreaking", "innocent victims", "claimed the lives", "gruesome",
    "bloody", "barbaric", "senseless", "unimaginable", "nightmare",
]

#: A line is one visual beat -- the board gives it a single image -- so the
#: real limit is how long an audience will hold on one picture, not how many
#: words it takes to get there. Expressing it in seconds keeps the two
#: registers honest: the old feed cap of 18 words at 112 wpm and a naive
#: documentary cap of 28 at 160 wpm are the same ten seconds wearing
#: different clothes. Documentary lets an image breathe longer, and 13
#: seconds also clears the ninety-seventh percentile sentence of a measured
#: reference documentary, so the rule stops fighting the cadence check that
#: asks for long sentences on purpose.
MAX_LINE_SECONDS = {"feed": 10.0, "documentary": 13.0}
DEFAULT_REGISTER = "feed"
MIN_SOURCES_PER_CLAIM = 2
CHAPTER_DRIFT_TOLERANCE = 12.0  # seconds
DEFAULT_TOLERANCE = 0.08

# Words that are spoken but should not be counted as narration payload.
DIRECTION_RE = re.compile(r"\[\[[^\]]*\]\]")
LINE_RE = re.compile(r"^(l[0-9]+[a-z]?)\s+(.*)$")
CHAPTER_RE = re.compile(r"^##\s*(?:\[(\d{1,2}):(\d{2})\]\s*)?(.*)$")
REFS_RE = re.compile(r"\{([^}]*)\}\s*$")
# A "figure" is anything a viewer would treat as a checkable quantity.
FIGURE_RE = re.compile(
    r"(?<![A-Za-z])(?:\d[\d,.:]*|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"dozen|dozens|hundreds|thousands|million|billion)(?![A-Za-z])",
    re.I,
)

RESET = "\033[0m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"


def paint(s: str, colour: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return s
    return f"{colour}{s}{RESET}"


# --------------------------------------------------------------------- parsing


class ParseError(Exception):
    pass


def parse_frontmatter(text: str) -> tuple[dict, int]:
    """Read the leading `---` block. Returns (data, line offset of the body)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ParseError("script must start with a --- frontmatter block")
    data: dict = {}
    for i, raw in enumerate(lines[1:], start=1):
        if raw.strip() == "---":
            return data, i + 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise ParseError(f"line {i + 1}: not a `key: value` pair")
        key, _, value = raw.partition(":")
        value = value.strip().strip('"').strip("'")
        low = value.lower()
        if low in ("true", "false"):
            data[key.strip()] = low == "true"
        else:
            try:
                data[key.strip()] = int(value) if value.isdigit() else float(value)
            except ValueError:
                data[key.strip()] = value
    raise ParseError("frontmatter block is not closed with ---")


def parse_script(text: str) -> tuple[dict, list[dict]]:
    """Parse frontmatter and chapters. Chapters hold their lines in order."""
    meta, offset = parse_frontmatter(text)
    body = text.splitlines()[offset:]

    chapters: list[dict] = []
    current: dict | None = None
    pending: dict | None = None  # a line still accumulating continuations

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            current["lines"].append(pending)
            pending = None

    for i, raw in enumerate(body, start=offset + 1):
        stripped = raw.strip()

        if stripped.startswith("## "):
            flush()
            m = CHAPTER_RE.match(stripped)
            mm, ss, title = m.group(1), m.group(2), m.group(3).strip()
            planned = None
            if mm is not None:
                planned = int(mm) * 60 + int(ss)
            current = {
                "title": title, "planned_start": planned, "lineno": i, "lines": [],
            }
            chapters.append(current)
            continue

        if not stripped or stripped.startswith("#"):
            flush()
            continue

        m = LINE_RE.match(stripped)
        if m:
            flush()
            if current is None:
                current = {
                    "title": "(untitled)", "planned_start": None,
                    "lineno": i, "lines": [],
                }
                chapters.append(current)
            pending = {
                "id": m.group(1), "text": m.group(2).strip(),
                "lineno": i, "refs": None,
            }
        elif pending is not None and raw.startswith((" ", "\t")):
            pending["text"] += " " + stripped
        else:
            flush()

        if pending is not None:
            rm = REFS_RE.search(pending["text"])
            if rm:
                pending["refs"] = [
                    r.strip() for r in rm.group(1).split(",") if r.strip()
                ]
                pending["text"] = pending["text"][: rm.start()].strip()
                flush()

    flush()
    return meta, chapters


def spoken(text: str) -> str:
    return DIRECTION_RE.sub(" ", text)


def word_count(text: str) -> int:
    return len([w for w in spoken(text).split() if any(c.isalnum() for c in w)])


# ---------------------------------------------------------------------- report


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)


# ---------------------------------------------------------------------- checks


def check_ledger(ledger: dict, rep: Report) -> dict[str, dict]:
    sources = {s["id"]: s for s in ledger.get("sources", []) if "id" in s}
    if len(sources) != len(ledger.get("sources", [])):
        rep.error("ledger: duplicate or id-less entries in `sources`")

    for sid, s in sources.items():
        if not s.get("url"):
            rep.warn(f"ledger: source `{sid}` has no url")
        if not s.get("accessed"):
            rep.warn(f"ledger: source `{sid}` has no accessed date")
        if s.get("tier") not in ("A", "B", "C", "D", None):
            rep.warn(f"ledger: source `{sid}` has unknown tier {s.get('tier')!r}")

    claims: dict[str, dict] = {}
    for c in ledger.get("claims", []):
        cid = c.get("id")
        if not cid:
            rep.error("ledger: a claim has no id")
            continue
        if cid in claims:
            rep.error(f"ledger: duplicate claim id `{cid}`")
        claims[cid] = c

        refs = c.get("sources") or []
        unknown = [r for r in refs if r not in sources]
        for u in unknown:
            rep.error(f"claim `{cid}` cites unknown source `{u}`")
        distinct = {r for r in refs if r in sources}
        if len(distinct) < MIN_SOURCES_PER_CLAIM:
            rep.error(
                f"claim `{cid}` has {len(distinct)} distinct source(s); "
                f"{MIN_SOURCES_PER_CLAIM} required"
            )
        if c.get("confidence") not in ("high", "medium", "low"):
            rep.error(
                f"claim `{cid}` has confidence {c.get('confidence')!r}; "
                "expected high|medium|low"
            )
        if c.get("confidence") == "high":
            tiers = {sources[r].get("tier") for r in distinct}
            if not tiers & {"A", "B"}:
                rep.warn(
                    f"claim `{cid}` is `high` confidence but rests only on "
                    f"tier {sorted(t for t in tiers if t)} sources"
                )
        if c.get("contested") and not c.get("note"):
            rep.warn(f"claim `{cid}` is contested but records no note")
        if not str(c.get("claim", "")).strip():
            rep.error(f"claim `{cid}` has empty claim text")

    return claims


def register_of(meta):
    """The register this script is written in.

    Taken from the frontmatter, which the screenwriter copies from
    `brief.register` -- the one place the decision is made. It is deliberately
    NOT guessed from the pace. Register and wpm are not monotonically related:
    a memorial documentary runs at 90 to 100 wpm while a social vertical runs
    at 150 to 180, so any speed threshold misclassifies in both directions and
    does it silently. A script that predates the key is feed, which is also
    the safe way to be wrong -- the strict cap shows up as warnings rather
    than quietly licensing lines nobody meant to allow.
    """
    want = str(meta.get("register") or "").strip().lower()
    if want in MAX_LINE_SECONDS:
        return want
    if want:
        return None
    return ""


def check_lines(chapters, claims, meta, rep: Report) -> dict:
    register = register_of(meta)
    if register == "":
        rep.info(f"no `register` in the frontmatter; assuming {DEFAULT_REGISTER}")
        register = DEFAULT_REGISTER
    elif register is None:
        rep.error("frontmatter `register` must be one of: %s"
                  % ", ".join(sorted(MAX_LINE_SECONDS)))
        register = DEFAULT_REGISTER
    try:
        wpm = float(meta.get("wpm", 0) or 0)
    except (TypeError, ValueError):
        wpm = 0.0
    wpm = wpm or 112.0
    max_line_words = round(MAX_LINE_SECONDS[register] * wpm / 60.0)
    sensitive = bool(meta.get("sensitive"))
    used: set[str] = set()
    seen_ids: dict[str, int] = {}
    total_words = 0
    unsourced_factual = 0

    for ch in chapters:
        if not ch["lines"]:
            rep.warn(f"chapter '{ch['title']}' (line {ch['lineno']}) has no lines")
        for ln in ch["lines"]:
            text, lid, no = ln["text"], ln["id"], ln["lineno"]
            words = word_count(text)
            ln["words"] = words
            total_words += words

            if lid in seen_ids:
                rep.error(
                    f"{no}: duplicate line id `{lid}` "
                    f"(first used at line {seen_ids[lid]})"
                )
            seen_ids[lid] = no

            refs = ln["refs"]
            if refs is None:
                rep.error(f"{no}: `{lid}` has no {{claim-ids}} and is not marked {{~}}")
                if FIGURE_RE.search(spoken(text)):
                    unsourced_factual += 1
                continue

            if refs == ["~"]:
                if FIGURE_RE.search(spoken(text)):
                    rep.error(
                        f"{no}: `{lid}` is marked {{~}} but states a figure — "
                        "an unsourced line may not contain a number or date"
                    )
                    unsourced_factual += 1
                continue

            if "~" in refs:
                rep.error(f"{no}: `{lid}` mixes {{~}} with claim ids")

            for r in refs:
                if r == "~":
                    continue
                if r not in claims:
                    rep.error(f"{no}: `{lid}` cites unknown claim `{r}`")
                    continue
                used.add(r)
                if claims[r].get("contested"):
                    low = spoken(text).lower()
                    if not any(h in low for h in HEDGES):
                        rep.error(
                            f"{no}: `{lid}` uses contested claim `{r}` "
                            "without a hedge (according to / alleged / "
                            "cannot be established / at least / about …)"
                        )

            if words == 0:
                rep.warn(f"{no}: `{lid}` has no spoken words")
            elif words > max_line_words:
                rep.warn(f"{no}: `{lid}` is {words} words, about "
                         f"{words / wpm * 60:.0f}s on one image "
                         f"(max {max_line_words} at {MAX_LINE_SECONDS[register]:.0f}s "
                         f"in the {register} register)")

            if sensitive:
                low = spoken(text).lower()
                for term in DRAMATISING:
                    if term in low:
                        rep.warn(f"{no}: `{lid}` uses dramatising term '{term}'")

    for cid in claims:
        if cid not in used:
            rep.info(f"claim `{cid}` is never used")

    return {"total_words": total_words, "used": used,
            "unsourced_factual": unsourced_factual}


def check_timing(chapters, meta, total_words, rep: Report) -> dict:
    wpm = float(meta.get("wpm", 0) or 0)
    target = float(meta.get("target_duration", 0) or 0)
    tol = float(meta.get("tolerance", DEFAULT_TOLERANCE))
    if wpm <= 0 or target <= 0:
        rep.error("frontmatter needs positive `wpm` and `target_duration`")
        return {}

    budget = target * wpm / 60.0
    lo, hi = budget * (1 - tol), budget * (1 + tol)
    est = total_words / wpm * 60.0
    drift = (total_words - budget) / budget if budget else 0.0

    if total_words < lo or total_words > hi:
        rep.error(
            f"word count {total_words} is outside the budget "
            f"{lo:.0f}–{hi:.0f} for {target:.0f}s @ {wpm:.0f} wpm "
            f"({drift:+.1%})"
        )

    cursor = 0.0
    for ch in chapters:
        ch["actual_start"] = cursor
        ch["words"] = sum(l.get("words", 0) for l in ch["lines"])
        ch["seconds"] = ch["words"] / wpm * 60.0
        if ch["planned_start"] is not None:
            d = cursor - ch["planned_start"]
            if abs(d) > CHAPTER_DRIFT_TOLERANCE:
                rep.warn(
                    f"chapter '{ch['title']}' starts at "
                    f"{fmt_ts(cursor)} but is headed {fmt_ts(ch['planned_start'])} "
                    f"({d:+.0f}s)"
                )
        cursor += ch["seconds"]

    return {"budget": budget, "lo": lo, "hi": hi, "estimated": est, "drift": drift}


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ------------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint a research-backed narration script.")
    ap.add_argument("script")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--json", action="store_true", help="emit a JSON report")
    ap.add_argument("--plain", action="store_true", help="print narration only")
    ap.add_argument("--lines", action="store_true",
                    help="emit [{id, text}] for the voice booth and beat plan")
    ap.add_argument("--register", choices=sorted(MAX_LINE_SECONDS),
                    help="override the frontmatter register (use brief.register)")
    args = ap.parse_args()

    try:
        text = open(args.script, encoding="utf-8").read()
    except OSError as e:
        print(f"cannot read script: {e}", file=sys.stderr)
        return 2

    rep = Report()
    try:
        meta, chapters = parse_script(text)
        if args.register:
            meta["register"] = args.register
    except ParseError as e:
        print(f"{args.script}: {e}", file=sys.stderr)
        return 2

    if args.lines:
        out = [{"id": ln["id"], "text": spoken(ln["text"]).strip(),
                "chapter": ch["title"]}
               for ch in chapters for ln in ch["lines"]
               if spoken(ln["text"]).strip()]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.plain:
        for ch in chapters:
            for ln in ch["lines"]:
                out = spoken(ln["text"]).strip()
                if out:
                    print(out)
            print()
        return 0

    ledger_path = os.path.join(
        os.path.dirname(os.path.abspath(args.script)), meta.get("ledger", "ledger.json")
    )
    try:
        ledger = json.load(open(ledger_path, encoding="utf-8"))
    except OSError as e:
        print(f"cannot read ledger: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"ledger is not valid JSON: {e}", file=sys.stderr)
        return 2

    claims = check_ledger(ledger, rep)
    stats = check_lines(chapters, claims, meta, rep)
    timing = check_timing(chapters, meta, stats["total_words"], rep)

    n_lines = sum(len(c["lines"]) for c in chapters)
    ok = not rep.errors and not (args.strict and rep.warnings)

    if args.json:
        print(json.dumps({
            "script": args.script,
            "title": meta.get("title"),
            "ok": ok,
            "words": stats["total_words"],
            "lines": n_lines,
            "chapters": [
                {"title": c["title"], "words": c["words"],
                 "seconds": round(c["seconds"], 1),
                 "start": round(c["actual_start"], 1),
                 "planned_start": c["planned_start"]}
                for c in chapters if "seconds" in c
            ],
            "claims": len(claims),
            "claims_used": len(stats["used"]),
            "sources": len(ledger.get("sources", [])),
            "timing": {k: round(v, 3) for k, v in timing.items()},
            "errors": rep.errors,
            "warnings": rep.warnings,
            "infos": rep.infos,
        }, indent=2))
        return 0 if ok else 1

    print(paint(meta.get("title", args.script), GREEN if ok else RED))
    if timing:
        print(f"  target {meta['target_duration']:.0f}s @ {meta['wpm']:.0f} wpm"
              f"  ->  {timing['lo']:.0f}–{timing['hi']:.0f} words")
        verdict = "OK" if not rep.errors else "FAIL"
        print(f"  actual {stats['total_words']} words  ~{timing['estimated']:.0f}s"
              f"  ({timing['drift']:+.1%})"
              f"{'':<8}{paint(verdict, GREEN if not rep.errors else RED)}")
    print(f"  claims {len(claims)} ({len(stats['used'])} used) · "
          f"sources {len(ledger.get('sources', []))} · lines {n_lines} · "
          f"unsourced factual lines {stats['unsourced_factual']}")

    if chapters and any("seconds" in c for c in chapters):
        print()
        for c in chapters:
            if "seconds" not in c:
                continue
            head = f"  {fmt_ts(c['actual_start'])}  {c['title']}"
            print(f"{head:<52}{c['words']:>5}w {c['seconds']:>6.1f}s")

    for label, items, colour in (
        ("error", rep.errors, RED),
        ("warn", rep.warnings, YELLOW),
        ("info", rep.infos, DIM),
    ):
        if not items:
            continue
        print()
        for m in items:
            print(f"  {paint(label, colour)}  {m}")

    print()
    if ok:
        print(paint("  passed", GREEN))
    else:
        print(paint(f"  failed — {len(rep.errors)} error(s), "
                    f"{len(rep.warnings)} warning(s)", RED))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
