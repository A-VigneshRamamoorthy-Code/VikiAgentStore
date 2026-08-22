#!/usr/bin/env python3
"""
Snaps clip in/out points to natural conversation boundaries.

A clip should begin as a speaker starts talking and end once they have
finished, never mid-sentence. Speech onsets are the *ends* of silences and
speech offsets are the *starts* of silences, so the in-point is chosen from
silence ends near the target and the out-point from silence starts.

Candidates are scored by pause length minus distance from the target, which
prefers a strong, natural pause over one that merely sits closest.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project  # noqa: E402

# A debating chamber floors around -24 dB mean, so -38 dB reliably separates
# room tone from speech. A hotter or quieter mix needs this retuned -- expose
# it in project.json rather than editing here.
NOISE_DB = -38
MIN_SIL = 0.30          # shorter gaps are breaths, not boundaries


def silences(path, start, dur, noise=NOISE_DB, mind=MIN_SIL):
    """Absolute (start, end) of every detected pause in the window."""
    start = max(0.0, start)
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-i", path,
         "-t", str(dur),
         "-af", f"silencedetect=noise={noise}dB:d={mind}", "-f", "null", "-"],
        capture_output=True, text=True).stderr

    sils, cur = [], None
    for m in re.finditer(r"silence_(start|end):\s*(-?[\d.]+)", out):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            cur = start + val
        elif cur is not None:
            sils.append((cur, start + val))
            cur = None
    if cur is not None:
        sils.append((cur, start + dur))
    return sils


def snap(pr, t0, t1, pre=20.0, post=28.0, min_len=None, max_len=None):
    """Move (t0, t1) onto speech onset / offset boundaries.

    Returns (in_point, out_point, info). Falls back to the original points
    whenever no natural boundary exists, which is honest: a clip that must cut
    mid-sentence is better than one silently stretched somewhere arbitrary.
    """
    min_len = pr.get("longform", "min_clip", default=34.0) \
        if min_len is None else min_len
    max_len = pr.get("longform", "max_clip", default=95.0) \
        if max_len is None else max_len
    noise = pr.get("audio", "noise_db", default=NOISE_DB)
    mind = pr.get("audio", "min_silence", default=MIN_SIL)

    lo = max(0.0, t0 - pre)
    hi = t1 + post
    sils = silences(pr.audio, lo, hi - lo, noise, mind)
    if not sils:
        return t0, t1, {"snapped": False, "reason": "no silences detected"}

    def dur(s):
        return s[1] - s[0]

    # in-point: end of a pause == the moment speech resumes
    ins = [s for s in sils if lo <= s[1] <= t0 + pre * 0.5]
    # out-point: start of a pause == the moment speech stops
    outs = [s for s in sils if t1 - post * 0.4 <= s[0] <= hi]

    if not ins or not outs:
        return t0, t1, {"snapped": False, "reason": "no candidate boundary"}

    best = None
    for si in ins:
        a = si[1]
        for so in outs:
            b = so[0]
            length = b - a
            if not (min_len <= length <= max_len):
                continue
            score = (min(dur(si), 2.0) + min(dur(so), 2.0)) \
                - 0.05 * (abs(a - t0) + abs(b - t1))
            if best is None or score > best[0]:
                best = (score, a, b, dur(si), dur(so))

    if best is None:
        return t0, t1, {"snapped": False, "reason": "no pair within length limits"}

    _, a, b, pa, pb = best
    return a, b, {
        "snapped": True,
        "in_pause": round(pa, 2),
        "out_pause": round(pb, 2),
        "shift_in": round(a - t0, 2),
        "shift_out": round(b - t1, 2),
        "length": round(b - a, 2),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Preview boundary snapping for every planned clip")
    ap.add_argument("project")
    a = ap.parse_args()
    pr = Project(a.project)
    plan = pr.load("plan")
    if not plan:
        raise SystemExit("no meta/plan.json -- run plan.py first")
    items = [(e["id"], c) for e in plan["episodes"] for c in e["clips"]]
    items += [(s["id"], s) for s in plan["shorts"]]
    for name, c in items:
        x, y, info = snap(pr, float(c["start"]), float(c["end"]))
        print(f"{name} {c.get('tc','')}  {c['start']:.0f}-{c['end']:.0f} -> "
              f"{x:.2f}-{y:.2f}  {info}")


if __name__ == "__main__":
    main()
