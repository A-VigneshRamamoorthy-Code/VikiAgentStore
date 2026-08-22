"""Decide how many videos this session yields, and what goes in each.

The count is **derived, not configured**. A quiet procedural sitting produces
one digest; a session with six flashpoints produces several themed episodes and
a Short for each flashpoint. Forcing a fixed number is what makes a channel
publish padded 12-minute videos on days when nothing happened, which is the
fastest way to lose a session-based audience.

Ranking rules, in order:

1. **Clashes outrank everything.** A confirmed shouting match is the single
   most watched artefact a legislature produces, so it leads its episode and
   always gets its own Short.
2. **VIP presence overrides packaging.** If a configured public figure appears
   inside a segment, that segment's episode is packaged around them -- title,
   thumbnail and Short hook -- because a recognisable face outperforms an
   issue headline in a feed.
3. **Everything else by highlight score**, which blends energy, onset density
   and spectral character (see analyse.py).

Reads  meta/candidates.json  (+ optional meta/vip_hits.json, meta/labels.json)
Writes meta/plan.json
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, hhmmss, mmss, say  # noqa: E402


def merge_overlaps(cands, gap=8.0):
    """Collapse candidates that describe the same moment.

    The scorer slides a window, so one flashpoint routinely produces three or
    four overlapping rows. Publishing those as separate clips would show the
    viewer the same argument three times.
    """
    if not cands:
        return []
    ordered = sorted(cands, key=lambda c: c["start"])
    out = [dict(ordered[0])]
    for c in ordered[1:]:
        prev = out[-1]
        if c["start"] <= prev["end"] + gap:
            # Keep the better-scoring row's character, widen to the union.
            better = c if c["highlight"] > prev["highlight"] else prev
            merged = dict(better)
            merged["start"] = min(prev["start"], c["start"])
            merged["end"] = max(prev["end"], c["end"])
            merged["kind"] = ("clash" if "clash" in (prev["kind"], c["kind"])
                              else better["kind"])
            merged["highlight"] = max(prev["highlight"], c["highlight"])
            merged["clash"] = max(prev.get("clash", 0), c.get("clash", 0))
            out[-1] = merged
        else:
            out.append(dict(c))
    return out


def rank(cands):
    """Clashes first, then by highlight score."""
    return sorted(cands, key=lambda c: (c["kind"] != "clash",
                                        -c["highlight"]))


def attach_vip(cands, hits, pad=20.0):
    """Mark segments in which the VIP was seen on camera.

    `pad` is generous because the detector samples every few seconds; a face
    seen just outside the window is still almost certainly in the segment.
    """
    for c in cands:
        seen = [h for h in hits
                if c["start"] - pad <= h["t"] <= c["end"] + pad]
        c["vip_hits"] = len(seen)
        c["vip"] = bool(seen)
        if seen:
            c["vip_best"] = round(max(h.get("score", 0) for h in seen), 3)
    return cands


def label_for(c, labels):
    """Human label for a segment, if transcription supplied one."""
    for l in labels:
        if l["start"] <= c["start"] < l["end"] or \
           c["start"] <= l["start"] < c["end"]:
            return l
    return {}


def select_strong(cands, floor, keep_frac):
    """Which moments are worth publishing at all.

    An absolute score bar does not survive contact with real sessions: the
    scorer normalises within a session, so on a dull day everything scores
    "high" relative to nothing happening. Judging each moment against this
    session's own distribution is what stops a procedural sitting being
    inflated into five episodes of filler.

    Clashes bypass the bar entirely -- a confirmed flashpoint is publishable
    even in an otherwise flat session.
    """
    clashes = [c for c in cands if c["kind"] == "clash"]
    rest = [c for c in cands if c["kind"] != "clash"]
    if not rest:
        return clashes

    scores = sorted(c["highlight"] for c in rest)
    cut = scores[int(len(scores) * (1 - keep_frac))] if len(scores) > 2 else 0
    bar = max(floor, cut)
    kept = [c for c in rest if c["highlight"] >= bar]
    return clashes + kept


def episode_count(strong, per_episode, lo, hi):
    """How many long-form videos this session justifies."""
    if not strong:
        return 0
    return max(lo, min(hi, math.ceil(len(strong) / per_episode)))


def clamp_clip(c, lo, hi):
    """Trim or extend a segment to a publishable clip length."""
    start, end = float(c["start"]), float(c["end"])
    dur = end - start
    if dur < lo:
        grow = (lo - dur) / 2
        start, end = max(0.0, start - grow), end + grow
    elif dur > hi:
        # Keep the front: the flashpoint is at the onset, not the tail.
        end = start + hi
    return round(start, 2), round(end, 2)


def build_plan(pr):
    cands = pr.load("candidates") or []
    if not cands:
        raise SystemExit("no meta/candidates.json -- run analyse.py first")
    hits = (pr.load("vip_hits") or {}).get("hits", []) \
        if pr.get("vip", "enabled", default=False) else []
    labels = pr.load("labels") or []

    lf = pr["longform"]
    sh = pr["shorts"]

    cands = merge_overlaps(cands)
    if hits:
        cands = attach_vip(cands, hits)
    ordered = rank(cands)

    # "Strong" = worth publishing at all. Clashes always qualify.
    floor = pr.get("longform", "min_highlight", default=0.55)
    keep_frac = pr.get("longform", "keep_fraction", default=0.45)
    strong = select_strong(ordered, floor, keep_frac)
    strong = rank(strong)

    per_ep = max(1, lf["max_clips"])
    n_eps = episode_count(strong, per_ep, 1,
                          pr.get("longform", "max_episodes", default=6))
    say(f"{len(cands)} distinct moments, {len(strong)} strong "
        f"({sum(1 for c in strong if c['kind'] == 'clash')} clash) "
        f"-> {n_eps} long-form episode(s)")

    # Deal moments round-robin so episode 1 is not simply the best of
    # everything followed by three weak ones -- every episode needs a hook.
    buckets = [[] for _ in range(n_eps)]
    for i, c in enumerate(strong[:n_eps * per_ep]):
        buckets[i % n_eps].append(c)

    episodes = []
    for i, bucket in enumerate(buckets, 1):
        if not bucket:
            continue
        bucket = sorted(bucket, key=lambda c: (c["kind"] != "clash",
                                               -c["highlight"]))
        clips = []
        for c in bucket:
            a, b = clamp_clip(c, lf["min_clip"], lf["max_clip"])
            lab = label_for(c, labels)
            clips.append({
                "start": a, "end": b, "tc": hhmmss(a),
                "kind": c["kind"], "highlight": round(c["highlight"], 4),
                "clash": round(c.get("clash", 0), 4),
                "vip": bool(c.get("vip")),
                "label": lab.get("label", ""),
                "gloss": lab.get("gloss", ""),
            })
        # Chronological inside the episode: a session tells a story in order.
        clips.sort(key=lambda c: c["start"])
        # An episode below the minimum is padding, not programming; its
        # moments are better served as Shorts.
        if len(clips) < lf["min_clips"] and not any(
                c["kind"] == "clash" for c in clips):
            say(f"  dropping thin episode ({len(clips)} clips < "
                f"{lf['min_clips']}) -- its moments stay available as Shorts")
            continue
        has_clash = any(c["kind"] == "clash" for c in clips)
        has_vip = any(c["vip"] for c in clips)
        episodes.append({
            "id": f"ep{i:02d}",
            "kind": "longform",
            "theme": "clash" if has_clash else "digest",
            "vip": has_vip,
            "runtime": round(sum(c["end"] - c["start"] for c in clips), 1),
            "clips": clips,
        })

    shorts = plan_shorts(pr, strong, episodes, labels, sh)
    plan = {
        "source": pr["source"],
        "generated_from": "meta/candidates.json",
        "episodes": episodes,
        "shorts": shorts,
        "policy": {
            "clash_first": True,
            "vip_packaging": bool(hits),
            "note": ("Counts are derived from highlight density, never fixed. "
                     "A calm session legitimately yields fewer videos."),
        },
    }
    return plan


def plan_shorts(pr, strong, episodes, labels, sh):
    """One Short per standalone moment, each pointing at its long-form home.

    Shorts are the discovery surface and the long-form is the destination, so
    every Short records which episode it came from; the description and the
    end card link back to it. A Short that does not route viewers anywhere is
    a dead end.
    """
    home = {}
    for ep in episodes:
        for c in ep["clips"]:
            home[round(c["start"])] = ep["id"]

    picks = [c for c in strong if c["kind"] == "clash"]
    picks += [c for c in strong if c["kind"] != "clash"]
    limit = pr.get("shorts", "max_count", default=6)

    out, seen = [], set()
    for c in picks:
        if len(out) >= limit:
            break
        key = round(c["start"] / 30)
        if key in seen:
            continue
        seen.add(key)
        a, b = clamp_clip(c, sh["min_len"], sh["max_len"])
        parent = home.get(round(a)) or nearest_home(a, episodes)
        lab = label_for(c, labels)
        out.append({
            "id": f"sh{len(out)+1:02d}",
            "kind": "short",
            "start": a, "end": b, "tc": hhmmss(a),
            "length": round(b - a, 1),
            "theme": "clash" if c["kind"] == "clash" else "moment",
            "vip": bool(c.get("vip")),
            "parent": parent,
            "label": lab.get("label", ""),
            "gloss": lab.get("gloss", ""),
        })
    say(f"{len(out)} Short(s) planned "
        f"({sum(1 for s in out if s['theme'] == 'clash')} clash)")
    return out


def nearest_home(t, episodes):
    best, dist = None, float("inf")
    for ep in episodes:
        for c in ep["clips"]:
            d = abs(c["start"] - t)
            if d < dist:
                best, dist = ep["id"], d
    return best


def main():
    ap = argparse.ArgumentParser(
        description="Plan episodes and Shorts from detected highlights")
    ap.add_argument("project")
    a = ap.parse_args()

    pr = Project(a.project)
    plan = build_plan(pr)
    pr.save("plan", plan)

    for ep in plan["episodes"]:
        flags = [ep["theme"]] + (["VIP"] if ep["vip"] else [])
        say(f"  {ep['id']}  {len(ep['clips'])} clips  "
            f"{mmss(ep['runtime'])}  [{'/'.join(flags)}]")
    for s in plan["shorts"]:
        say(f"  {s['id']}  {s['tc']}  {s['length']:.0f}s  "
            f"[{s['theme']}] -> {s['parent']}")
    say(f"wrote {pr.p('meta', 'plan.json')}")


if __name__ == "__main__":
    main()
