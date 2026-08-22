#!/usr/bin/env python3
"""Resolve a beat plan's hook into the window a Short is actually cut from.

The hook marks its span by narration id -- `from: l39`, `to: l44` -- because
that is what the story means. Turning those ids into seconds is arithmetic, and
doing it by hand is how a Short ends up starting mid-sentence.

The tempting shortcut is to add up the narration clips: lead-in, then each
line's duration and the gap after it. That number is wrong. The renderer trims
the recorded silence off every clip before it lays the voice down, so the file
on disk runs about a second longer than what plays, and the error compounds
line by line. Measured on a 12-minute film it put the window 12 seconds late --
far enough that the cut opened halfway through a sentence and closed on the
wrong beat entirely, two lines past the image it was chosen for.

So this reads the timeline the renderer published rather than recomputing it.

    python3 cut.py --hook h1 \
        --beat-plan ep1/beat-plan.json \
        --timeline ep1/cooper.timeline.json \
        --title "He Stepped Off The Back Of An Airliner" \
        -o short1/short.json
"""

import argparse
import json
import os
import sys

# YouTube stops treating an upload as a Short past this length.
SHORTS_MAX = 60.0
# Under about fifteen seconds there is no room to land a hook and a turn.
SHORTS_MIN = 15.0


def die(msg, code=2):
    print("cut: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def load(path, what):
    if not os.path.exists(path):
        die("no such %s: %s" % (what, path))
    with open(path) as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as e:
            die("%s is not valid JSON: %s" % (path, e))


def resolve(hook, spans, film_end):
    """Turn a hook's `from`/`to` ids into a start and end in seconds."""
    fid, tid = hook.get("from"), hook.get("to") or hook.get("from")
    if not fid:
        die("hook %r has no `from`, so there is nothing to resolve"
            % hook.get("id"))
    for lid in (fid, tid):
        if lid not in spans:
            die("the timeline does not place %r. Either the hook names a line "
                "that was cut, or the timeline is from an older render." % lid)
    start = spans[fid][0]
    end = spans[tid][1]
    if end <= start:
        die("hook %r runs backwards: %s ends at %.2fs, before %s starts at "
            "%.2fs" % (hook.get("id"), tid, end, fid, start))
    return start, min(end, film_end)


def main():
    ap = argparse.ArgumentParser(
        description="Resolve a beat plan hook into a Short's cut window.")
    ap.add_argument("--beat-plan", required=True, metavar="JSON")
    ap.add_argument("--timeline", required=True, metavar="JSON",
                    help="the renderer's published *.timeline.json")
    ap.add_argument("--hook", help="hook id; defaults to the first "
                                   "short_worthy one")
    ap.add_argument("--source", help="storyboard path recorded in the cut, "
                                     "relative to the short's directory")
    ap.add_argument("--title", help="the Short's own on-card hook")
    ap.add_argument("--ends-on", dest="ends_on",
                    help="the beat the cut closes on, for review")
    ap.add_argument("--lead", type=float, default=0.0, metavar="S",
                    help="seconds of picture before the first line")
    ap.add_argument("--tail", type=float, default=0.0, metavar="S",
                    help="seconds held after the last line")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    plan = load(a.beat_plan, "beat plan")
    tl = load(a.timeline, "timeline")

    spans = {}
    for it in tl.get("lines") or []:
        if isinstance(it, dict) and "id" in it:
            spans[it["id"]] = (float(it["start"]), float(it["end"]))
    if not spans:
        die("%s lists no lines, so it cannot place anything" % a.timeline)
    film_end = float(tl.get("duration") or max(b for _, b in spans.values()))

    hooks = plan.get("hooks") or []
    if not hooks:
        die("%s carries no `hooks`, so there is nothing to cut" % a.beat_plan)
    if a.hook:
        picked = next((h for h in hooks if h.get("id") == a.hook), None)
        if picked is None:
            die("no hook %r in %s. It has: %s"
                % (a.hook, a.beat_plan,
                   ", ".join(str(h.get("id")) for h in hooks)))
    else:
        picked = next((h for h in hooks if h.get("short_worthy")), None)
        if picked is None:
            die("no hook in %s is marked `short_worthy`. Pass --hook to "
                "override, or mark one." % a.beat_plan)

    start, end = resolve(picked, spans, film_end)
    start = max(0.0, start - a.lead)
    end = min(film_end, end + a.tail)
    dur = end - start

    out = {
        "source": a.source or "../ep1/storyboard.json",
        "hook": picked.get("id"),
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(dur, 2),
        "aspect": "9:16",
        "why": picked.get("why", ""),
        "title": a.title or "",
        "ends_on": a.ends_on or "",
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")

    print("cut: %s  %s -> %s  %.2f-%.2fs (%.1fs)"
          % (picked.get("id"), picked.get("from"),
             picked.get("to") or picked.get("from"), start, end, dur))
    print("  %s" % a.out)

    problems = []
    if dur > SHORTS_MAX:
        problems.append(
            "%.1fs is past the %.0fs Shorts ceiling -- YouTube will treat it "
            "as an ordinary upload. Trim the hook's span, or use --tail/--lead "
            "to reframe it." % (dur, SHORTS_MAX))
    if dur < SHORTS_MIN:
        problems.append(
            "%.1fs leaves no room to land a hook and a turn; %.0fs is about "
            "the floor." % (dur, SHORTS_MIN))
    if not out["title"]:
        problems.append("no --title, so the card has no hook text to burn in.")
    for p in problems:
        print("cut: %s" % p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
