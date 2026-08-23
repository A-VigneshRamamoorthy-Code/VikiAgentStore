#!/usr/bin/env python3
"""Decide how much motion each beat gets, and prove the answer is not flat.

A beat plan says what is on screen and when. It says nothing about how hard the
film should work at that moment, so every renderer that reads one ends up doing
the same amount of work everywhere — a camera move on every beat, the same zoom
on every beat. That is the Ken Burns failure: motion becomes wallpaper and
stops meaning anything.

Japanese TV animation solves it by refusing to spend evenly. Most cuts are a
held drawing with the camera parked. A handful get everything. This allocates
a beat plan the same way and writes the result as `motion-plan.json`.

    python3 framebudget.py beat-plan.json -o motion-plan.json
    python3 framebudget.py beat-plan.json --check       # report, write nothing
    python3 framebudget.py motion-plan.json --audit     # judge an edited plan

The plan it writes is a draft that is *correct*, not one that is *right*: the
distribution is enforced mechanically, but which shot deserves the budget is a
judgement. Open it and move the sakuga to the moment that earns it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_beatplan():
    d = HERE
    for _ in range(6):
        d = os.path.dirname(d)
        cand = os.path.join(d, "storyboard-artist", "scripts")
        if os.path.isfile(os.path.join(cand, "beatplan.py")):
            return cand
    return None


_BP = _find_beatplan()
if _BP:
    sys.path.insert(0, _BP)
try:
    import beatplan
except ImportError:  # pragma: no cover
    beatplan = None

SCHEMA = 1

# ---------------------------------------------------------------- the tiers --
#
# Named for what the anime pipeline actually does, because the names carry the
# cost model with them. `cost` is a notional drawing budget: what this shot
# spends relative to the cheapest possible one.

TIERS = {
    "hold":    {"cost": 1,  "camera": "still",
                "about": "one drawing, camera parked. Alive only through "
                         "ambient drift and whatever breathes on top of it."},
    "limited": {"cost": 2,  "camera": "push",
                "about": "one drawing under a slow push or a short pan — the "
                         "yori that says 'this matters' without redrawing."},
    "full":    {"cost": 5,  "camera": "track",
                "about": "things arrive and the camera travels to meet them."},
    "sakuga":  {"cost": 12, "camera": "travel",
                "about": "the showcase cut. Travel, arrivals and parallax at "
                         "once. There are one or two in a film, not ten."},
    "impact":  {"cost": 1,  "camera": "shake",
                "about": "a held drawing whose first frames are a jolt — "
                         "flash, shake, snap, then let the picture sit. Costs "
                         "almost nothing and reads as the loudest thing in "
                         "the film."},
}

LOUD = ("full", "sakuga", "impact")

# The distribution law. These are shares of the shot count, and they encode the
# one finding every source agreed on: the majority of a film must be cheap, or
# there is nothing left to make the expensive moments feel expensive.
LAW = {
    "hold_min":        0.35,   # at least this share is genuinely parked
    "cheap_min":       0.62,   # hold + limited
    "full_max":        0.28,
    "sakuga_max":      0.10,
    "sakuga_min_n":    1,      # a film with no showcase cut has no peak
    "sakuga_max_n":    3,
    "impact_max":      0.10,
    "emphatic_max":    0.38,   # full + sakuga — the "≤35% of shots move" rule
    "hold_run_max_s":  13.0,   # how long the camera may stay parked in a row
}

# How much each intent wants to move. A portrait is a face you hold; a reveal is
# something arriving. This is a prior, not a verdict — emphasis overrides it.
INTENT_BIAS = {
    "reveal":     0.26,
    "compare":    0.16,
    "list":       0.14,
    "transition": 0.10,
    "establish":  0.02,
    "locate":     0.00,
    "annotate":  -0.06,
    "emphasise": -0.06,
    "evidence":  -0.12,
    "portrait":  -0.16,
}

# Intents that must never be spent as an impact. A flash-and-shake over a face
# held for a reason, or over a document a viewer is trying to read, is the
# technique used against the shot it is decorating.
NO_IMPACT = {"portrait", "evidence", "list", "compare"}


def load(path):
    with open(path) as fh:
        return json.load(fh)


def _times(plan, root):
    if beatplan is None:
        sys.exit("cannot import beatplan.py — is the storyboard-artist skill "
                 "installed beside this one?")
    return beatplan.timeline(plan, root=root)


def _at(spec, times):
    try:
        return float(beatplan.resolve(spec, times))
    except Exception:
        return 0.0


def _hook_windows(plan, times):
    out = []
    for h in plan.get("hooks") or []:
        a, b = h.get("from"), h.get("to")
        if not a or not b:
            continue
        try:
            out.append((_at(a, times), _at(b + ".end", times)))
        except Exception:
            continue
    return out


def score_beats(plan, times, total):
    """A want-to-move score per beat, before any quota is applied."""
    beats = plan.get("beats") or []
    hooks = _hook_windows(plan, times)
    rows = []
    for i, b in enumerate(beats):
        bid = b.get("id") or "b%d" % (i + 1)
        start = _at(b.get("at"), times)
        emph = b.get("emphasis")
        emph = 0.5 if not isinstance(emph, (int, float)) else float(emph)
        intent = b.get("intent") or "establish"

        s = 0.55 * emph + INTENT_BIAS.get(intent, 0.0)

        pos = (start / total) if total else 0.0
        # Where the budget goes, per the production accounts: the opening,
        # which decides whether anyone stays, and the climax, which is what
        # they stayed for. The middle is carried on held drawings.
        if pos <= 0.08:
            s += 0.18
        if pos >= 0.72:
            s += 0.16 * ((pos - 0.72) / 0.28)
        if any(a - 0.25 <= start <= b_ + 0.25 for a, b_ in hooks):
            s += 0.12

        rows.append({"id": bid, "beat": bid, "intent": intent,
                     "at": b.get("at"), "start": round(start, 3),
                     "emphasis": round(emph, 3), "_score": round(s, 4),
                     "subject": b.get("subject")})

    rows.sort(key=lambda r: r["start"])
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["start"] if i + 1 < len(rows) else total
        r["end"] = round(max(nxt, r["start"] + 0.5), 3)
        r["duration"] = round(r["end"] - r["start"], 3)
    return rows


def allocate(rows, total):
    """Spend the budget: rank by want-to-move, then pour into quotas."""
    n = len(rows)
    if not n:
        return rows

    n_sakuga = max(LAW["sakuga_min_n"],
                   min(LAW["sakuga_max_n"], int(round(n * 0.055))))
    n_impact = int(round(n * 0.06))
    n_full = int(round(n * 0.20))
    n_limited = int(round(n * 0.26))

    order = sorted(rows, key=lambda r: (-r["_score"], r["start"]))

    # The showcase cuts go to the highest-scoring beats, but at least one must
    # sit in the last third. A film whose best shot is at 0:15 has spent its
    # peak before the audience had a reason to care.
    late = [r for r in order if r["start"] >= 0.62 * total]
    chosen = []
    if late and n_sakuga:
        chosen.append(late[0])
    for r in order:
        if len(chosen) >= n_sakuga:
            break
        if r not in chosen:
            chosen.append(r)
    for r in chosen:
        r["tier"] = "sakuga"

    rest = [r for r in order if "tier" not in r]

    for r in rest:
        if n_impact <= 0:
            break
        # An impact is not a short shot. It is the first few frames of a shot:
        # a flash and a jolt, and then the drawing is simply held — the
        # impact-frame-into-manga-panel move. So length is irrelevant; what
        # matters is whether the beat has earned a physical punctuation.
        if r["intent"] in NO_IMPACT or r["emphasis"] < 0.7:
            continue
        r["tier"] = "impact"
        n_impact -= 1

    rest = [r for r in order if "tier" not in r]
    for r in rest[:n_full]:
        r["tier"] = "full"

    rest = [r for r in order if "tier" not in r]
    # Limited goes to the *most* wanting of what is left, so the tail is holds.
    for r in rest[:n_limited]:
        r["tier"] = "limited"

    for r in rows:
        r.setdefault("tier", "hold")

    _break_hold_runs(rows)
    return rows


def _break_hold_runs(rows):
    """Stop the camera parking for so long that the film stalls.

    Holding is the point, but a run of holds is still one continuous stretch
    with a motionless camera, and past roughly a quarter-minute that stops
    reading as restraint and starts reading as a stalled render. The fix is
    the cheapest one available: promote the most deserving hold in the run to
    a slow push, which costs one camera move and resets the clock.
    """
    limit = LAW["hold_run_max_s"]
    i, n = 0, len(rows)
    while i < n:
        if rows[i]["tier"] != "hold":
            i += 1
            continue
        j = i
        while j < n and rows[j]["tier"] == "hold":
            j += 1
        span = rows[j - 1]["end"] - rows[i]["start"]
        if span > limit:
            run = rows[i:j]
            # Promote from the middle outward, so the pushes land inside the
            # run rather than next to the loud shots that already bracket it.
            k = max(1, int(round(span / limit)))
            picks = sorted(run, key=lambda r: -r["emphasis"])[:k]
            for r in picks:
                r["tier"] = "limited"
        i = j


def dress(rows, total):
    """Give each shot the camera and the secondary motion its tier implies."""
    for i, r in enumerate(rows):
        t = r["tier"]
        d = r["duration"]
        r["camera"] = TIERS[t]["camera"]
        r["cost"] = TIERS[t]["cost"]

        if t == "hold":
            r["amount"] = 0.0
            # A parked camera is not a dead frame. Something on top of it has
            # to be alive or the shot reads as a stall, and that something is
            # the cheapest motion in the film.
            r["secondary"] = ["sway", "grain"]
        elif t == "limited":
            # A yori is 5-12% of scale over 2-4s. Longer shots get the slower,
            # shallower end of that so the push stays under the dialogue.
            r["amount"] = round(0.05 if d > 4.0 else 0.09, 3)
            r["secondary"] = ["sway"]
        elif t == "full":
            r["amount"] = round(0.12 + 0.05 * r["emphasis"], 3)
            r["secondary"] = ["arrive", "parallax"]
        elif t == "sakuga":
            r["amount"] = round(0.18 + 0.10 * r["emphasis"], 3)
            r["secondary"] = ["arrive", "parallax", "particles"]
        elif t == "impact":
            r["amount"] = 0.0
            r["secondary"] = ["shake", "flash"]

        # Every move rests before it travels and rests after it lands. This one
        # field is the difference between an anime camera and a slideshow.
        r["pre_hold"] = 0.5 if t in ("full", "sakuga") else 0.35
        r["why"] = _why(r)
    return rows


def _why(r):
    t = r["tier"]
    if t == "sakuga":
        return "the film's peak — spend everything here"
    if t == "impact":
        return "a jolt, measured in frames"
    if t == "full":
        return "something arrives; the camera goes to meet it"
    if t == "limited":
        return "a slow push so the line lands"
    return "held — let the picture sit and the voice carry it"


def summarise(rows, total):
    n = max(len(rows), 1)
    counts = {t: 0 for t in TIERS}
    for r in rows:
        counts[r["tier"]] += 1
    shares = {t: counts[t] / n for t in counts}
    held_s = sum(r["duration"] for r in rows if r["tier"] == "hold")
    return {
        "shots": len(rows),
        "runtime_s": round(total, 3),
        "counts": counts,
        "shares": {t: round(v, 3) for t, v in shares.items()},
        "cheap_share": round(shares["hold"] + shares["limited"], 3),
        "emphatic_share": round(shares["full"] + shares["sakuga"], 3),
        "held_seconds": round(held_s, 2),
        "held_share_of_runtime": round(held_s / total, 3) if total else 0.0,
        "drawing_cost": sum(r["cost"] for r in rows),
        "cost_per_shot": round(sum(r["cost"] for r in rows) / n, 2),
    }


def audit(rows, summary):
    """Check the plan against the law. Returns (errors, warnings)."""
    errs, warns = [], []
    n = max(len(rows), 1)
    c, s = summary["counts"], summary["shares"]

    if s["hold"] < LAW["hold_min"]:
        errs.append("only %.0f%% of shots are held (need >= %.0f%%). A film "
                    "that never parks has no quiet for its loud moments to "
                    "rise out of."
                    % (100 * s["hold"], 100 * LAW["hold_min"]))
    if summary["cheap_share"] < LAW["cheap_min"]:
        errs.append("cheap shots (hold+limited) are %.0f%% (need >= %.0f%%). "
                    "Spending everywhere is the same as spending nowhere."
                    % (100 * summary["cheap_share"], 100 * LAW["cheap_min"]))
    if summary["emphatic_share"] > LAW["emphatic_max"]:
        errs.append("%.0f%% of shots carry an emphatic camera move (max "
                    "%.0f%%). Past this the move stops reading as emphasis "
                    "and becomes the film's texture."
                    % (100 * summary["emphatic_share"],
                       100 * LAW["emphatic_max"]))
    if c["sakuga"] < LAW["sakuga_min_n"]:
        errs.append("no sakuga cut. A film with no peak is evenly paced, "
                    "which is not the same as well paced.")
    if c["sakuga"] > max(LAW["sakuga_max_n"], int(n * LAW["sakuga_max"])):
        errs.append("%d sakuga cuts is more than a film this length can pay "
                    "for; the showcase stops being a showcase." % c["sakuga"])
    if s["full"] > LAW["full_max"]:
        warns.append("full-motion shots are %.0f%% (soft max %.0f%%)"
                     % (100 * s["full"], 100 * LAW["full_max"]))
    if s["impact"] > LAW["impact_max"]:
        warns.append("%.0f%% impacts — a jolt every few seconds is a tic"
                     % (100 * s["impact"]))

    total = summary["runtime_s"]
    sak = [r for r in rows if r["tier"] == "sakuga"]
    if sak and total and all(r["start"] < 0.55 * total for r in sak):
        warns.append("every sakuga cut is in the first half; the film peaks "
                     "before it has earned it")

    for r in rows:
        if r["tier"] == "hold" and r["duration"] > 6.0:
            warns.append("%s is held %.1fs with the camera parked — past ~6s "
                         "a hold needs a push, a pan or something arriving"
                         % (r["id"], r["duration"]))

    for i in range(1, len(rows)):
        if rows[i]["tier"] == "impact" and rows[i - 1]["tier"] == "impact":
            warns.append("%s and %s are both impacts, back to back — a second "
                         "jolt lands on an audience still absorbing the first"
                         % (rows[i - 1]["id"], rows[i]["id"]))

    runs, i, n_rows = [], 0, len(rows)
    while i < n_rows:
        if rows[i]["tier"] not in LOUD:
            i += 1
            continue
        j = i
        while j < n_rows and rows[j]["tier"] in LOUD:
            j += 1
        if j - i >= 3:
            runs.append((rows[i]["start"], j - i))
        i = j
    # A sustained run of loud shots at the climax is the shape the whole
    # technique is building toward, so it is not a fault. The same run in the
    # second act is: it spends the budget where nothing has been earned yet,
    # and leaves the ending with nothing left to rise to.
    for t, k in [(t, k) for t, k in runs if total and t < 0.62 * total]:
        warns.append("%d loud shots in a row at %.0fs, well before the "
                     "climax — a run like this belongs at the peak, and here "
                     "it flattens the film's second act" % (k, t))

    i = 0
    while i < n_rows:
        if rows[i]["tier"] != "hold":
            i += 1
            continue
        j = i
        while j < n_rows and rows[j]["tier"] == "hold":
            j += 1
        span = rows[j - 1]["end"] - rows[i]["start"]
        if span > LAW["hold_run_max_s"]:
            warns.append("the camera is parked for %.0fs straight from %.0fs "
                         "— at that length restraint stops being legible and "
                         "the film reads as stalled" % (span, rows[i]["start"]))
        i = j
    return errs, warns


def build(plan, root, title=None):
    times, total, missing = _times(plan, root)
    if total <= 0:
        sys.exit("this plan has no measurable runtime — the narration has "
                 "neither audio nor durations, so there is nothing to budget")
    rows = score_beats(plan, times, total)
    rows = allocate(rows, total)
    rows = dress(rows, total)
    for r in rows:
        r.pop("_score", None)
    summary = summarise(rows, total)
    return {
        "schema": SCHEMA,
        "title": title or plan.get("title") or "untitled",
        "runtime_s": round(total, 3),
        "accent_tolerance_s": 0.75,
        "summary": summary,
        "law": LAW,
        "shots": rows,
    }, missing


def fmt(mp, errs, warns):
    s = mp["summary"]
    L = ["%s  —  %d shots over %.1fs"
         % (mp["title"], s["shots"], s["runtime_s"]), ""]
    for t in ("hold", "limited", "full", "sakuga", "impact"):
        n = s["counts"][t]
        bar = "#" * int(round(40 * s["shares"][t]))
        L.append("  %-8s %3d  %5.1f%%  %s" % (t, n, 100 * s["shares"][t], bar))
    L.append("")
    L.append("  cheap %.0f%%   emphatic %.0f%%   held %.1fs of %.1fs (%.0f%%)"
             % (100 * s["cheap_share"], 100 * s["emphatic_share"],
                s["held_seconds"], s["runtime_s"],
                100 * s["held_share_of_runtime"]))
    L.append("  notional drawing cost %d (%.1f per shot)"
             % (s["drawing_cost"], s["cost_per_shot"]))
    if errs:
        L.append("")
        for e in errs:
            L.append("  ERROR  " + e)
    if warns:
        L.append("")
        for w in warns:
            L.append("  warn   " + w)
    if not errs and not warns:
        L.append("\n  the distribution is sound — now check it is the right "
                 "one, which no script can do for you")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="framebudget.py",
        description="Allocate a beat plan's motion budget the way a TV anime "
                    "allocates drawings: cheap almost everywhere, everything "
                    "in one or two places.")
    ap.add_argument("plan", help="beat-plan.json, or motion-plan.json with --audit")
    ap.add_argument("-o", "--out", default="motion-plan.json")
    ap.add_argument("--check", action="store_true",
                    help="report what it would write, and write nothing")
    ap.add_argument("--audit", action="store_true",
                    help="judge an existing motion plan instead of building one")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    a = ap.parse_args(argv)

    root = os.path.dirname(os.path.abspath(a.plan)) or "."
    doc = load(a.plan)

    if a.audit or doc.get("schema") == SCHEMA and "shots" in doc:
        mp = doc
        rows = mp.get("shots") or []
        for r in rows:
            r.setdefault("duration",
                         round(float(r.get("end", 0)) - float(r.get("start", 0)), 3))
            r.setdefault("cost", TIERS.get(r.get("tier"), {}).get("cost", 1))
        mp["summary"] = summarise(rows, mp.get("runtime_s") or 0.0)
        errs, warns = audit(rows, mp["summary"])
        print(json.dumps(mp["summary"], indent=2) if a.json
              else fmt(mp, errs, warns))
        return 1 if errs else 0

    mp, missing = build(doc, root)
    errs, warns = audit(mp["shots"], mp["summary"])
    if missing:
        warns.append("%d narration line(s) have no measurable length (%s) — "
                     "every shot after them is budgeted against a guess"
                     % (len(missing), ", ".join(str(m) for m in missing[:4])))

    print(json.dumps(mp, indent=2) if a.json else fmt(mp, errs, warns))

    if not a.check:
        with open(a.out, "w") as fh:
            json.dump(mp, fh, indent=2)
        if not a.json:
            print("\n  wrote %s" % a.out)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
