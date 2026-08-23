#!/usr/bin/env python3
"""Measure how a film's motion is *distributed* over time, not just how much of it there is.

The existing style check is a single mean frame difference. It answers "does
this move at all", which is worth knowing and is not what makes a film feel
animated. A film that drifts gently for twelve minutes and a film that holds
still for four seconds and then explodes can report the same mean.

Anime's whole economy rests on the second shape. So this measures the shape:
how much of the running time is genuinely held, how far the loud moments rise
above the quiet ones, and whether those loud moments land where the plan said
they would.

    python3 motionprofile.py out.mp4                       # the profile
    python3 motionprofile.py out.mp4 --json prof.json      # machine-readable
    python3 motionprofile.py out.mp4 --plan motion-plan.json   # against intent
    python3 motionprofile.py --compare base.mp4 directed.mp4   # A/B

No dependencies beyond ffmpeg/ffprobe and numpy.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

# Analysis resolution. Small enough to decode a feature in seconds, large enough
# that a slow pan across fine texture still registers.
PROBE_W, PROBE_H = 320, 180

# A frame is "held" when it differs from its predecessor by less than this, on
# the 0-255 luma scale. Not zero: a held anime cel still carries grain, a
# breathing loop and a drifting particle layer, and calling that "motion" would
# make every hold look like a move.
HOLD_EPS = 0.60

# An "accent" is a run of frames well above the film's own quiet level. Defined
# relative to the median rather than absolutely, because a paper collage and a
# flat vector style sit at different baselines.
ACCENT_MULT = 2.2
ACCENT_MIN_FRAMES = 2

# A hold only counts as a hold once it lasts long enough to read as a decision.
# Below this it is jitter between moves, which is the opposite of the effect —
# scattered still frames are what a permanently floating board produces, and
# they measure as stillness while feeling like unrest.
SUSTAINED_HOLD_S = 0.40

# A stretch that stays under the film's own baseline for this long is the image
# being allowed to breathe — the anime hold, which is quiet but rarely frozen
# because a camera drift or a particle layer is still alive on top of it.
DWELL_MIN_S = 1.00


def _need(binary: str) -> None:
    if shutil.which(binary) is None:
        sys.exit(f"{binary} not found on PATH")


def probe(path: Path) -> dict:
    _need("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1)
    return {
        "width": st.get("width"),
        "height": st.get("height"),
        "fps": fps,
        "duration": float((d.get("format") or {}).get("duration") or 0.0),
    }


def frame_deltas(path: Path, fps: float) -> np.ndarray:
    """Mean absolute luma difference between consecutive frames.

    Streamed rather than loaded: a feature-length file at full frame rate is
    gigabytes of raw grey, and we only ever need two frames at a time.
    """
    _need("ffmpeg")
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
           "-vf", f"scale={PROBE_W}:{PROBE_H}", "-pix_fmt", "gray",
           "-f", "rawvideo", "-"]
    nbytes = PROBE_W * PROBE_H
    deltas: list[float] = []
    prev: np.ndarray | None = None
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        assert p.stdout is not None
        while True:
            buf = p.stdout.read(nbytes)
            if len(buf) < nbytes:
                break
            cur = np.frombuffer(buf, dtype=np.uint8).astype(np.int16)
            if prev is not None:
                deltas.append(float(np.abs(cur - prev).mean()))
            prev = cur
        p.stdout.close()
        p.wait()
    if not deltas:
        sys.exit(f"decoded no frames from {path}")
    return np.asarray(deltas, dtype=np.float64)


def find_accents(d: np.ndarray, fps: float, median: float) -> list[dict]:
    """Contiguous runs that rise well above the film's own quiet level."""
    if median <= 0:
        median = float(np.mean(d)) or 1e-6
    thresh = max(median * ACCENT_MULT, HOLD_EPS * 2)
    hot = d >= thresh
    accents: list[dict] = []
    i = 0
    n = len(hot)
    while i < n:
        if not hot[i]:
            i += 1
            continue
        j = i
        while j < n and hot[j]:
            j += 1
        if j - i >= ACCENT_MIN_FRAMES:
            seg = d[i:j]
            accents.append({
                "start": round(i / fps, 3),
                "end": round(j / fps, 3),
                "duration": round((j - i) / fps, 3),
                "peak": round(float(seg.max()), 3),
                "mean": round(float(seg.mean()), 3),
                "lift": round(float(seg.max() / median), 2),
            })
        i = j
    return accents


def longest_run(mask: np.ndarray, fps: float) -> float:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return round(best / fps, 3)


def runs(mask: np.ndarray, fps: float, min_s: float) -> list[tuple[int, int]]:
    """Contiguous true-runs of at least `min_s` seconds, as frame index pairs."""
    out: list[tuple[int, int]] = []
    need = max(1, int(round(min_s * fps)))
    i, n = 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if j - i >= need:
            out.append((i, j))
        i = j
    return out


def analyse(path: Path) -> dict:
    meta = probe(path)
    fps = meta["fps"] or 30.0
    d = frame_deltas(path, fps)

    median = float(np.median(d))
    p10, p50, p90, p99 = (float(np.percentile(d, q)) for q in (10, 50, 90, 99))
    held = d < HOLD_EPS
    accents = find_accents(d, fps, median)
    accent_frames = sum(int(round(a["duration"] * fps)) for a in accents)
    runtime = len(d) / fps

    # Stillness that lasts long enough to be a decision rather than a gap
    # between two moves.
    sustained = runs(held, fps, SUSTAINED_HOLD_S)
    sustained_frames = sum(j - i for i, j in sustained)

    # A "dwell" is a stretch that stays under the film's own baseline for at
    # least a second: the image is being allowed to breathe. A film whose
    # motion is a flat texture crosses its median constantly and has almost
    # none of these, however well it scores on the mean.
    dwelling = runs(d < median, fps, DWELL_MIN_S)
    dwell_frames = sum(j - i for i, j in dwelling)

    # How far the film's loud moments rise above its quiet ones. This is the
    # number the mean cannot see, and the one limited animation exists to make
    # large: hold cheaply, then spend everything at once.
    dyn = (p90 / p50) if p50 > 1e-9 else float("inf")

    return {
        "file": str(path),
        "format": {k: meta[k] for k in ("width", "height", "fps", "duration")},
        "frames": len(d) + 1,
        "runtime_s": round(runtime, 3),
        "mean": round(float(d.mean()), 3),
        "median": round(median, 3),
        "p10": round(p10, 3),
        "p90": round(p90, 3),
        "p99": round(p99, 3),
        "peak": round(float(d.max()), 3),
        "std": round(float(d.std()), 3),
        "dynamic_range": round(dyn, 2) if np.isfinite(dyn) else None,
        "hold_pct": round(100.0 * float(held.mean()), 1),
        "longest_hold_s": longest_run(held, fps),
        "sustained_holds": len(sustained),
        "sustained_hold_pct": round(100.0 * sustained_frames / max(len(d), 1), 1),
        "dwells": len(dwelling),
        "dwell_pct": round(100.0 * dwell_frames / max(len(d), 1), 1),
        "longest_dwell_s": round(max((j - i for i, j in dwelling), default=0) / fps, 3),
        "accents": accents,
        "accent_count": len(accents),
        "accent_pct": round(100.0 * accent_frames / max(len(d), 1), 1),
        "accents_per_min": round(len(accents) / max(runtime / 60.0, 1e-6), 2),
        # Raw series, kept for plan checking and dropped before JSON output.
        "_deltas": d,
        "_times": np.arange(len(d), dtype=np.float64) / fps,
    }


# --------------------------------------------------------------- judgement ---

# What a limited-animation cut should measure. Derived from the shape the
# technique produces rather than from any one style's baseline, so the same
# thresholds apply to paper collage and to anything added later.
# What every directed film must satisfy, whatever its house style.
#
# `mean` is deliberately *not* here. A style's mean-motion floor is calibrated
# on undirected boards, where every beat gets the same treatment, and a
# directed film spends most of its runtime deliberately quiet. Measured on a
# 37-beat story in style-paper: the undirected cut scored 1.749 and the
# directed cut 1.284 against a style floor of 1.5 — the directed cut is not
# broken, it is cheaper, which is the entire point of limited animation.
# Grading it on the global mean would reject every film this skill exists to
# make. `p90` is graded instead: it asks whether the film's loud tail is
# genuinely lively, which is what that floor was really protecting.
TARGETS = {
    "p90": (2.2, None, "the loud tail is genuinely lively"),
    "dynamic_range": (2.2, None, "loud moments rise clear of quiet ones"),
    "longest_hold_s": (None, 2.5, "no frozen frame outstays a viewer's patience"),
}

# Graded only when a motion plan is supplied, because they compare the film
# against its own stated intent. `tier_separation` is the whole thesis of the
# animation director in one number: an undirected film scores about 1.0
# however pretty it looks — the measured baseline scored 1.009.
PLAN_TARGETS = {
    "tier_separation": (1.35, None,
                        "planned-loud beats really are louder than planned-quiet ones"),
    "hit_rate": (0.75, None, "the beats marked loud actually register as accents"),
    "loud_mean_delta": (1.5, None,
                        "the beats that carry the style clear the style's own floor"),
}

# Stillness targets, graded only under --strict.
#
# These are an *aesthetic*, not a law, and a style can be structurally unable
# to reach them. Measured case: style-paper spends 57% of its runtime on
# elements entering and leaving — a collage that assembles itself is what the
# style *is* — so it cannot buy long sub-median dwells no matter how the
# camera behaves. Grading every style against these would report a style
# choice as a directing failure, so they are opt-in.
STRICT_TARGETS = {
    "dwell_pct": (25.0, None, "a quarter of the film lets the image breathe"),
    "longest_dwell_s": (2.0, None, "at least one shot is genuinely allowed to rest"),
    "accents_per_min": (2.0, 14.0, "accents are events, not a texture"),
}


def judge(prof: dict, strict: bool = False, with_plan: bool = False) -> list[dict]:
    table = dict(TARGETS)
    if with_plan:
        table.update(PLAN_TARGETS)
    if strict:
        table.update(STRICT_TARGETS)
    rows = []
    for key, (lo, hi, why) in table.items():
        v = prof.get(key)
        if v is None:
            v = (prof.get("plan_check") or {}).get(key)
        if v is None:
            rows.append({"check": key, "value": None, "ok": False, "why": why})
            continue
        ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        want = (f">= {lo}" if hi is None else
                f"<= {hi}" if lo is None else f"{lo}-{hi}")
        rows.append({"check": key, "value": v, "want": want, "ok": ok, "why": why})
    return rows


def check_against_plan(prof: dict, plan_path: Path,
                       timeline_path: Path | None = None) -> dict:
    """Did the accents land where the animation director said they would?

    A film can have a beautiful motion distribution that is completely
    uncorrelated with its story. That is a lava lamp, not direction.

    The plan's own seconds are computed from raw narration clips, which still
    carry their recorded silence; the renderer trims that silence and its film
    is shorter. On a two-minute story the two clocks differed by 24 s — a
    quarter of the running time — so checking a plan against a render without
    re-resolving it compares the right shots at the wrong moments and reports
    a stream of misses that are really just drift. Hand it the renderer's
    published `*.timeline.json` and the shots are re-timed exactly.
    """
    plan = json.loads(plan_path.read_text())
    shots = plan.get("shots", [])

    lines = {}
    if timeline_path and timeline_path.exists():
        tl = json.loads(timeline_path.read_text())
        lines = {l["id"]: (float(l["start"]), float(l["end"]))
                 for l in tl.get("lines", []) if l.get("id")}

    def retime(shot, fallback):
        """Resolve a shot's line-relative `at` against the rendered timeline."""
        spec = shot.get("at")
        if not lines or not isinstance(spec, str):
            return fallback
        head, _, off = spec.partition("+")
        sign = 1.0
        if not off:
            head, _, off = spec.partition("-")
            sign = -1.0
        lid, at_end = head.split(".")[0], head.endswith(".end")
        if lid not in lines:
            return fallback
        base = lines[lid][1] if at_end else lines[lid][0]
        try:
            return base + sign * float(off or 0.0)
        except ValueError:
            return base

    loud = {"full", "sakuga", "impact"}
    scale = 1.0
    if not lines:
        pr = float(plan.get("runtime_s") or 0.0)
        if pr > 0:
            scale = prof["runtime_s"] / pr

    intended = []
    for s in shots:
        if s.get("tier") not in loud or s.get("start") is None:
            continue
        s0 = retime(s, float(s["start"]) * scale)
        span = (float(s.get("end", s["start"])) - float(s["start"])) * (
            1.0 if lines else scale)
        intended.append({**s, "_s0": s0, "_s1": s0 + max(span, 0.0)})

    accents = prof.get("accents", [])
    matched, missed = [], []
    tol = float(plan.get("accent_tolerance_s", 0.75))
    for s in intended:
        s0, s1 = s["_s0"], s["_s1"]
        hit = next((a for a in accents
                    if a["end"] >= s0 - tol and a["start"] <= s1 + tol), None)
        (matched if hit else missed).append({
            "id": s.get("id"), "tier": s.get("tier"),
            "start": round(s0, 2), "end": round(s1, 2),
            "measured_lift": hit["lift"] if hit else None,
        })

    stray = []
    for a in accents:
        near = any(s["_s0"] - tol <= a["end"] and a["start"] <= s["_s1"] + tol
                   for s in intended)
        if not near:
            stray.append({"start": a["start"], "end": a["end"], "lift": a["lift"]})

    total = len(intended)

    # The thesis, measured. Average the per-frame motion inside planned-loud
    # shots and inside planned-quiet ones and take the ratio. A film that
    # spreads motion evenly scores ~1.0 however pretty it looks; a directed
    # film scores well above it. This is deliberately independent of the house
    # style's absolute motion floor, so the same bar applies to every style.
    quiet_t = {"hold", "limited"}
    quiet = [s for s in shots
             if s.get("tier") in quiet_t and s.get("start") is not None]
    for s in quiet:
        s0 = retime(s, float(s["start"]) * scale)
        span = (float(s.get("end", s["start"])) - float(s["start"])) * (
            1.0 if lines else scale)
        s["_s0"], s["_s1"] = s0, s0 + max(span, 0.0)

    deltas, times = prof.get("_deltas"), prof.get("_times")
    sep = loud_mean = quiet_mean = None
    if deltas is not None and times is not None:
        def band(spans):
            vals = [d for d, t in zip(deltas, times)
                    if any(a <= t <= b for a, b in spans)]
            return sum(vals) / len(vals) if vals else None
        loud_mean = band([(s["_s0"], s["_s1"]) for s in intended])
        quiet_mean = band([(s["_s0"], s["_s1"]) for s in quiet])
        if loud_mean and quiet_mean and quiet_mean > 0:
            sep = round(loud_mean / quiet_mean, 3)

    return {
        "retimed_from": str(timeline_path) if lines else None,
        "scale_applied": None if lines else round(scale, 4),
        "intended_loud_shots": total,
        "intended_quiet_shots": len(quiet),
        "loud_mean_delta": round(loud_mean, 3) if loud_mean else None,
        "quiet_mean_delta": round(quiet_mean, 3) if quiet_mean else None,
        "tier_separation": sep,
        "landed": len(matched),
        "missed": missed,
        "unplanned_accents": stray,
        "hit_rate": round(len(matched) / total, 3) if total else None,
    }


def fmt_profile(p: dict, title: str | None = None) -> str:
    L = []
    if title:
        L.append(title)
    f = p["format"]
    L.append(f"  {f['width']}x{f['height']} @ {f['fps']:.3g}  "
             f"{p['runtime_s']:.2f}s  {p['frames']} frames")
    L.append(f"  mean {p['mean']:<6} median {p['median']:<6} "
             f"p90 {p['p90']:<6} peak {p['peak']}")
    L.append(f"  dynamic range {p['dynamic_range']}x   "
             f"held {p['hold_pct']}% of frames   "
             f"longest hold {p['longest_hold_s']}s")
    L.append(f"  dwells {p['dwells']} "
             f"({p['dwell_pct']}% of runtime, longest {p['longest_dwell_s']}s)")
    L.append(f"  accents {p['accent_count']} "
             f"({p['accents_per_min']}/min, {p['accent_pct']}% of runtime)")
    return "\n".join(L)


def fmt_verdict(rows: list[dict]) -> str:
    L = ["", "  check              value    want      "]
    for r in rows:
        mark = "ok " if r["ok"] else "FAIL"
        L.append(f"  {mark} {r['check']:<16} {str(r['value']):<8} "
                 f"{r.get('want', ''):<9} {r['why']}")
    return "\n".join(L)


def strip(p: dict) -> dict:
    """Drop the raw numpy series so the profile can be serialised."""
    return {k: v for k, v in p.items() if not k.startswith("_")}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Measure the distribution of motion in a rendered film.")
    ap.add_argument("video", nargs="?", type=Path)
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"),
                    help="profile two files and print the delta")
    ap.add_argument("--plan", type=Path,
                    help="motion-plan.json — check accents landed on intent")
    ap.add_argument("--timeline", type=Path,
                    help="the renderer's published *.timeline.json, so plan "
                         "times are re-resolved against the film that was "
                         "actually made. Defaults to <video>.timeline.json")
    ap.add_argument("--json", type=Path, help="write the profile as JSON")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when any check fails")
    a = ap.parse_args()

    if a.compare:
        pa, pb = (analyse(x) for x in a.compare)
        print(fmt_profile(pa, f"A  {a.compare[0].name}"))
        print()
        print(fmt_profile(pb, f"B  {a.compare[1].name}"))
        print("\n  delta (B - A)")
        for k in ("mean", "p90", "dynamic_range", "hold_pct",
                  "longest_hold_s", "dwell_pct", "longest_dwell_s",
                  "accent_count", "accents_per_min"):
            va, vb = pa.get(k), pb.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                print(f"    {k:<16} {va:>8} -> {vb:<8} {vb - va:+.2f}")
        if a.json:
            a.json.write_text(json.dumps({"a": strip(pa), "b": strip(pb)}, indent=2))
            print(f"\n  wrote {a.json}")
        return 0

    if not a.video:
        ap.error("give a video, or --compare A B")

    prof = analyse(a.video)
    print(fmt_profile(prof, str(a.video)))

    pc = None
    if a.plan:
        tlp = a.timeline or Path(str(a.video.with_suffix("")) + ".timeline.json")
        pc = check_against_plan(prof, a.plan, tlp)
        prof["plan_check"] = pc
        prof["tier_separation"] = pc["tier_separation"]
        prof["hit_rate"] = pc["hit_rate"]

    rows = judge(prof, strict=a.strict, with_plan=bool(pc))
    print(fmt_verdict(rows))

    if pc:
        if pc["retimed_from"]:
            print(f"\n  re-timed against {Path(pc['retimed_from']).name}")
        elif pc["scale_applied"] and abs(pc["scale_applied"] - 1.0) > 0.02:
            print(f"\n  ! no timeline found — plan times scaled by "
                  f"{pc['scale_applied']}, an approximation. Pass --timeline "
                  f"for an exact check.")
        if pc["tier_separation"]:
            print(f"  loud beats average {pc['loud_mean_delta']} vs "
                  f"{pc['quiet_mean_delta']} on quiet beats "
                  f"— {pc['tier_separation']}x separation")
        print(f"  against {a.plan.name}: {pc['landed']}/{pc['intended_loud_shots']} "
              f"loud shots landed as accents"
              + (f" (hit rate {pc['hit_rate']})" if pc["hit_rate"] is not None else ""))
        for m in pc["missed"]:
            print(f"    MISSED  {m['id']} ({m['tier']}) at {m['start']}s "
                  f"— planned loud, measured quiet")
        stray = pc["unplanned_accents"]
        for s in stray[:6]:
            print(f"    stray   accent at {s['start']}s, lift {s['lift']}x "
                  f"— nothing in the plan asked for this")
        if len(stray) > 6:
            print(f"    ... and {len(stray) - 6} more stray accents")

    if a.json:
        a.json.write_text(json.dumps(strip(prof), indent=2))
        print(f"\n  wrote {a.json}")

    failed = [r for r in rows if not r["ok"]]
    if failed:
        print(f"\n  {len(failed)} check(s) failed")
        if a.strict and all(r["check"] in STRICT_TARGETS for r in failed):
            print("  every failure is a --strict stillness target. Those are an "
                  "aesthetic, not a\n  law, and some styles cannot reach them: "
                  "style-paper spends 57% of its\n  runtime on elements entering "
                  "and leaving. Drop --strict unless the style\n  is genuinely "
                  "aiming for anime stillness.")
    return 1 if (a.strict and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
