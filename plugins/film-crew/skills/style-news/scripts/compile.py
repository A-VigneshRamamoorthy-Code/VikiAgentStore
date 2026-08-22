#!/usr/bin/env python3
"""Compile a style-neutral beat plan into a broadcast-news storyboard.

The beat plan says *what is on screen and when*. This turns that into the
vocabulary of a rolling news bulletin: a stacked **kicker** and **headline**
under the frame, a channel bug, a location chip, name straps for people and
astonisher cards for figures.

    python3 compile.py beat-plan.json -o storyboard.json
    python3 compile.py beat-plan.json --check

The mapping is deliberately narrow. A news bulletin has about six graphics and
uses them relentlessly; inventing a seventh for an intent that does not fit is
how a style stops looking like the thing it is imitating.
"""

import argparse
import json
import os
import re
import sys

SCHEMA = 1

#: Every beat intent, and the graphic a news bulletin would use for it. The
#: beat plan's vocabulary is closed, so this table is total by construction --
#: an intent with no entry here is a bug in one file or the other, not
#: something to fall back from silently.
GRAPHIC = {
    "establish":  "locator",
    "reveal":     "headline",
    "evidence":   "astonisher",
    "portrait":   "namestrap",
    "locate":     "locator",
    "compare":    "split",
    "list":       "bullets",
    "annotate":   "callout",
    "emphasise":  "headline",
    "transition": "sting",
}

#: Which graphics carry the running headline stack, and therefore should not be
#: stacked on top of another one that is already up.
EXCLUSIVE = {"headline", "astonisher", "split", "bullets", "namestrap"}

#: How long each graphic stays up, in seconds, before something replaces it.
#: Broadcast convention: a name strap is brief, an astonisher holds.
HOLD = {"headline": 4.5, "astonisher": 5.0, "namestrap": 3.5, "locator": 3.0,
        "bullets": 6.0, "split": 5.0, "callout": 2.5, "sting": 1.2}

#: If nothing has taken the screen by this many seconds, the compiler opens on
#: a title card instead. Viewers leave during a bare frame.
OPEN_BY = 1.2

#: The frame shapes declared in style.json. Kept here rather than derived from
#: a ratio so the numbers are the exact ones the encoder wants: both dimensions
#: even, and the vertical one the size a phone actually plays.
FRAME = {
    "16:9": {"width": 1920, "height": 1080},
    "9:16": {"width": 1080, "height": 1920},
    "1:1": {"width": 1080, "height": 1080},
}

TIME_RE = re.compile(r"^(l\d+)(\.end)?(?:([+-])([0-9.]+))?$")


def die(msg):
    print("news/compile: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def warn(msg):
    print("news/compile: %s" % msg, file=sys.stderr)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (path, e))


def clean(text, limit):
    """One line of on-screen text.

    Newlines and runs of whitespace are collapsed because a bar is one line
    high; anything longer than the bar is the writer's problem to fix, so it is
    reported rather than quietly truncated mid-word.
    """
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t[:limit].rstrip() if len(t) > limit else t


def upper(text):
    """Bulletin graphics shout. Non-Latin scripts have no case and are safe."""
    return text.upper()


def line_ids(plan):
    return [l.get("id") for l in plan.get("narration") or []]


def end_of_narration(plan):
    """When the voice stops -- the natural end of the last graphic.

    Returned as a number rather than a reference so the renderer needs no
    special case for "the end"; `resolve` already takes either.
    """
    t = 0.0
    for l in plan.get("narration") or []:
        t += float(l.get("duration") or 0.0) + float(l.get("gap_after") or 0.0)
    return round(t, 3)


def resolve_at(ref, plan):
    """A time reference in seconds. Mirrors the renderer's own resolver."""
    if isinstance(ref, (int, float)):
        return float(ref)
    m = TIME_RE.match(str(ref or ""))
    if not m:
        return 0.0
    t = 0.0
    for l in plan.get("narration") or []:
        d = float(l.get("duration") or 0.0)
        if l.get("id") == m.group(1):
            base = t + d if m.group(2) else t
            if m.group(3):
                off = float(m.group(4))
                base += off if m.group(3) == "+" else -off
            return max(0.0, base)
        t += d + float(l.get("gap_after") or 0.0)
    return 0.0


def check_time(ref, ids, where):
    if isinstance(ref, (int, float)):
        return
    m = TIME_RE.match(str(ref or ""))
    if not m:
        die("%s: %r is not a time reference. Use \"l4\", \"l4+0.2\", "
            "\"l4.end\" or a number." % (where, ref))
    if m.group(1) not in ids:
        die("%s: %r refers to line %r, which is not in the narration."
            % (where, ref, m.group(1)))


def kicker_for(plan, beat, allow_keyword=True):
    """The quiet line above the headline -- the act, or the subject.

    Real bulletins use it for context ("COST OF LIVING"), not for a second
    sentence, so it takes the act title where there is one.

    `allow_keyword` is off for graphics whose body is already built from the
    keywords: a list headed by its own first item reads as a stutter.
    """
    for act in plan.get("acts") or []:
        if beat.get("id") in (act.get("beats") or []):
            return upper(clean(act.get("title"), 42))
    kw = beat.get("keywords") or []
    if kw and allow_keyword:
        return upper(clean(kw[0], 42))
    return ""


def headline_for(beat):
    """The loud line. Subject if there is one, else the keywords."""
    if beat.get("subject"):
        return clean(beat["subject"], 68)
    kw = beat.get("keywords") or []
    if kw:
        return clean(" · ".join(kw), 68)
    return ""


def build_graphic(plan, beat, ids):
    kind = GRAPHIC.get(beat.get("intent"))
    if kind is None:
        die("beat %s has intent %r, which this style has no graphic for. The "
            "beat plan's intents are a closed set; if a new one was added, "
            "this table needs an entry." % (beat.get("id"), beat.get("intent")))

    check_time(beat.get("at"), ids, "beat %s" % beat.get("id"))
    g = {
        "id": beat.get("id"),
        "kind": kind,
        "at": beat.get("at"),
        "hold": HOLD[kind],
        "emphasis": beat.get("emphasis", 0.5),
        "safe": beat.get("safe", "full"),
    }

    head = headline_for(beat)
    kick = kicker_for(plan, beat, allow_keyword=(kind != "bullets"))

    if kind == "headline":
        g["kicker"], g["headline"] = kick, upper(head)
    elif kind == "astonisher":
        # A figure deserves the frame. Split "12,000 dead" into the number and
        # what it counts, because that is how the graphic is laid out.
        m = re.match(r"^([\d.,]+\s*(?:%|per cent|million|billion|bn|m|k)?)\s+"
                     r"(.*)$", head, re.I)
        g["figure"] = upper(m.group(1)) if m else ""
        g["caption"] = clean(m.group(2) if m else head, 54)
        g["kicker"] = kick
    elif kind == "namestrap":
        # "Jyoti Amge, wire worker" -> name over role.
        name, _, role = head.partition(",")
        g["name"] = upper(clean(name, 34))
        g["role"] = clean(role or beat.get("intent"), 44)
    elif kind == "locator":
        g["place"] = upper(clean(head or kick, 28))
    elif kind == "split":
        parts = [p for p in re.split(r"\s+(?:vs?\.?|versus|against)\s+", head,
                                     flags=re.I) if p]
        if len(parts) < 2:
            parts = (beat.get("keywords") or [head, ""])[:2]
        g["left"] = upper(clean(parts[0], 26))
        g["right"] = upper(clean(parts[1] if len(parts) > 1 else "", 26))
    elif kind == "bullets":
        items = beat.get("keywords") or [head]
        g["items"] = [clean(i, 40) for i in items[:4]]
        g["kicker"] = kick
    elif kind == "callout":
        g["mark"] = (beat.get("annotate") or {}).get("mark", "circle")
        g["label"] = upper(clean((beat.get("keywords") or [""])[0], 24))
    elif kind == "sting":
        g["label"] = upper(clean(kick or head, 30))

    art = (beat.get("assets") or [{}])[0]
    g["plate"] = {"kind": art.get("kind", "footage"),
                  "hint": art.get("hint") or beat.get("subject") or ""}
    return g


def compile_plan(plan, path, aspect="16:9"):
    if plan.get("schema") != SCHEMA:
        die("beat plan schema is %r, expected %d" % (plan.get("schema"), SCHEMA))
    ids = line_ids(plan)
    if not ids:
        die("beat plan has no narration, so no beat can be timed")
    beats = plan.get("beats") or []
    if not beats:
        die("beat plan has no beats -- there would be nothing on screen")

    graphics = [build_graphic(plan, b, ids) for b in beats]

    # Chaining below gives each graphic the *next* one's start as its end, so
    # it is only correct if the list is in time order. A beat plan is written
    # by hand and is not required to be sorted -- an out-of-order beat would
    # otherwise compile to a graphic whose `until` precedes its `at`, which
    # the renderer draws as a negative span: the card never appears, or two
    # headlines sit on screen at once. Sorting is stable, so beats that share
    # a timestamp keep the order the author wrote them in.
    graphics.sort(key=lambda g: resolve_at(g["at"], plan))

    # A bulletin opens on its title. Without this the film can begin with
    # several seconds of bare plate -- the single most expensive mistake in
    # the first ten seconds of a video, and one a beat plan will not always
    # avoid on its own because its first beat is often an establishing shot.
    ends = end_of_narration(plan)
    first = next((g for g in graphics if g["kind"] in EXCLUSIVE), None)
    if plan.get("title") and (first is None
                              or resolve_at(first["at"], plan) > OPEN_BY):
        graphics.insert(0, {
            "id": "open",
            "kind": "headline",
            "at": 0,
            "hold": HOLD["headline"],
            "emphasis": 1.0,
            "safe": "full",
            "kicker": upper(clean(plan.get("channel") or "REPORT", 42)),
            "headline": upper(clean(plan["title"], 68)),
            "plate": (graphics[0].get("plate") if graphics else None) or
                     {"kind": "footage", "hint": plan["title"]},
        })

    # Chain the timeline. Two full-width graphics that overlap look like a
    # fault on air, and a gap between them looks like one too -- so each
    # exclusive graphic runs exactly until the next one takes the screen, and
    # the last runs to the end of the narration. Dead air is not a style
    # choice; it is the thing a contact sheet is for catching.
    excl = [i for i, g in enumerate(graphics) if g["kind"] in EXCLUSIVE]
    for n, i in enumerate(excl):
        graphics[i]["until"] = (graphics[excl[n + 1]]["at"]
                                if n + 1 < len(excl) else ends)

    # The locator is an overlay, not a card: the place stays in the corner
    # under whatever else is on screen, until the report moves somewhere else.
    loc = [i for i, g in enumerate(graphics) if g["kind"] == "locator"]
    for n, i in enumerate(loc):
        graphics[i]["until"] = (graphics[loc[n + 1]]["at"]
                                if n + 1 < len(loc) else ends)

    # A graphic that ends before it starts is invisible, and one that ends
    # after the film does is a hang. Both are cheap to assert and expensive
    # to spot on a contact sheet.
    for g in graphics:
        if "until" not in g:
            continue
        a, u = resolve_at(g["at"], plan), resolve_at(g["until"], plan)
        if u < a:
            die("graphic %s would run from %.2fs to %.2fs -- backwards. Beats "
                "are compiled in time order, so this means two beats resolve "
                "to times the narration cannot produce." % (g["id"], a, u))

    empty = [g["id"] for g in graphics
             if g["kind"] in ("headline", "astonisher")
             and not (g.get("headline") or g.get("figure") or g.get("caption"))]
    if empty:
        warn("%d beat(s) compile to an empty bar (%s). A bulletin with a blank "
             "headline reads as a technical fault -- give those beats a "
             "`subject` or `keywords`." % (len(empty), ", ".join(empty[:5])))

    return {
        "schema": SCHEMA,
        "style": "news",
        "title": plan.get("title") or os.path.splitext(
            os.path.basename(path))[0],
        "seed": plan.get("seed", 7),
        "narration": plan.get("narration"),
        "output": dict(FRAME[aspect], fps=30, crf=20, preset="medium",
                       path="%s.mp4" % re.sub(r"[^a-z0-9]+", "_",
                                              (plan.get("title") or "news"
                                               ).lower()).strip("_")),
        "brand": {
            "name": plan.get("channel") or "",
            "accent": "#bb1919",
            "bar": "#f2f0eb",
            "ink": "#111111",
            "chip": "#3d3d3d",
        },
        "graphics": graphics,
        "hooks": plan.get("hooks") or [],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("beat_plan")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true",
                    help="validate and report, write nothing")
    ap.add_argument("--aspect", default="16:9", choices=sorted(FRAME),
                    help="frame shape (default 16:9)")
    a = ap.parse_args(argv)

    plan = load(a.beat_plan)
    sb = compile_plan(plan, a.beat_plan, a.aspect)

    if a.check:
        kinds = {}
        for g in sb["graphics"]:
            kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
        print("ok: %d graphic(s) -- %s"
              % (len(sb["graphics"]),
                 ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))))
        return 0

    out = a.out or "storyboard.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sb, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote %s (%d graphics)" % (out, len(sb["graphics"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
