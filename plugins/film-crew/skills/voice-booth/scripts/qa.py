#!/usr/bin/env python3
"""Catch the two defects that pass every other check: bad pauses and pitch spikes.

    python scripts/qa.py out/cast/*.mp3
    python scripts/qa.py --manifest out/cast/manifest.json
    python scripts/qa.py clip.mp3 --detail

`analyze.py` asks "is this audio valid?" — duration, median F0, noise floor,
half-second holes. A take can pass all of it and still sound wrong, because both
of the faults listeners actually notice are *local*:

**Uneven pauses.** A 1.4 s hole in the middle of a sentence measures the same as
a 1.4 s pause between two sentences. Only the position and the surrounding rhythm
tell them apart, and the median never moves.

**Single-letter pitch spikes.** One phoneme jumping most of an octave and coming
straight back is the single most synthetic-sounding artefact this model produces.
It shifts the median F0 by well under a hertz, so nothing upstream sees it.

Both thresholds below are deliberately conservative: this is a screening tool
whose job is to say "listen here", not to fail a voice on its own authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    CAST, duration_of, f0_track, median_filter, silences,
)

# --- pause thresholds ------------------------------------------------------
# Natural narration pauses cluster in three bands: intra-phrase (~0.15-0.30 s),
# clause (~0.35-0.60 s) and sentence (~0.60-0.90 s). A hole past 1.0 s inside a
# clip reads as a stall rather than punctuation.
LONG_PAUSE_S = 1.0
# Silences at the very start or end are trimming artefacts, not rhythm. Ignore
# anything within this distance of either edge.
EDGE_MARGIN_S = 0.35
# A pause this much longer than the clip's own median is out of character even
# when it is under the absolute ceiling — the ratio catches a voice whose pauses
# are all short except one.
PAUSE_RATIO = 4.0
# Below this many pauses the ratio test is meaningless, so only the ceiling runs.
MIN_PAUSES_FOR_RATIO = 3

# --- pitch-spike thresholds ------------------------------------------------
# Semitones above the local median that count as an excursion. Natural stress
# peaks reach 3-4 st; 6 lands well clear of them.
SPIKE_ST = 6.0
# An excursion is a *spike* only if it is short enough to be one sound. Beyond
# this it is intonation — a raised phrase, a question — which is wanted.
SPIKE_MAX_S = 0.22
# ...and long enough to actually hear. One 20 ms frame is below the threshold of
# pitch perception and is almost always a tracker glitch rather than audio: the
# first run of this tool flagged 60 single-frame "spikes" across nine clean
# voices, every one of them an octave artefact.
SPIKE_MIN_S = 0.06
# Local median window. Wide enough to span a phrase so ordinary intonation sits
# near zero, narrow enough that a slow drift in pitch does not mask a spike.
LOCAL_WINDOW_S = 1.5
FRAME_S = 0.02

# How many spikes a clip may contain before it is worth re-rolling. Calibrated
# against clips a listener judged good: the approved Tamil takes carried 2-3
# spikes each, and the raw Edge voices — the cleanest audio measured here —
# carried 0-1. So a handful of short excursions is normal in speech that sounds
# fine, and a zero-tolerance verdict would just flag everything.
SPIKE_BUDGET = 3


def semitones(a: float, b: float) -> float:
    """How far `a` sits above `b`, in semitones."""
    import math
    if a <= 0 or b <= 0:
        return 0.0
    return 12.0 * math.log2(a / b)


def find_spikes(track: list[tuple[float, float]]) -> list[dict]:
    """Short, high excursions above the local pitch — one per contiguous run."""
    import numpy as np

    if len(track) < 5:
        return []
    times = np.array([t for t, _ in track])
    freqs = np.array([f for _, f in track])

    # Local median over a sliding window, so ordinary intonation is subtracted
    # out and only departures from the current phrase survive.
    dev = np.zeros(len(freqs))
    for i, t in enumerate(times):
        sel = np.abs(times - t) <= LOCAL_WINDOW_S / 2
        local = float(np.median(freqs[sel]))
        dev[i] = semitones(float(freqs[i]), local)

    spikes, run = [], []
    for i, d in enumerate(dev):
        if d >= SPIKE_ST:
            run.append(i)
            continue
        if run:
            spikes.append(run)
            run = []
    if run:
        spikes.append(run)

    out = []
    for run in spikes:
        # Frames are only emitted for voiced audio, so a run that is contiguous
        # in index can still straddle a silence. Span, not count, is the length.
        span = times[run[-1]] - times[run[0]] + FRAME_S
        if span > SPIKE_MAX_S or span < SPIKE_MIN_S:
            continue                                  # intonation, or a glitch
        out.append({
            "at": round(float(times[run[0]]), 2),
            "span": round(float(span), 3),
            "st": round(float(dev[run].max()), 1),
            "hz": round(float(freqs[run].max()), 1),
        })
    return out


def find_bad_pauses(path: Path) -> list[dict]:
    """Silences that break the clip's own rhythm, or stall outright."""
    import numpy as np

    dur = duration_of(path)
    spans = silences(path)
    inner = [(s, d) for s, d in spans
             if s > EDGE_MARGIN_S and (s + d) < dur - EDGE_MARGIN_S]
    if not inner:
        return []

    lens = np.array([d for _, d in inner])
    med = float(np.median(lens))
    bad = []
    for start, d in inner:
        why = None
        if d > LONG_PAUSE_S:
            why = f"{d:.2f}s stall"
        elif (len(inner) >= MIN_PAUSES_FOR_RATIO and med > 0
              and d / med > PAUSE_RATIO):
            why = f"{d:.2f}s vs {med:.2f}s median"
        if why:
            bad.append({"at": round(start, 2), "dur": round(d, 3), "why": why})
    return bad


def qa(path: Path, budget: int = SPIKE_BUDGET) -> dict:
    track = median_filter(f0_track(path))
    spikes = find_spikes(track)
    pauses = find_bad_pauses(path)
    all_pauses = [d for _, d in silences(path)]
    return {
        "file": path.name,
        "spikes": spikes,
        "pauses": pauses,
        "n_pauses": len(all_pauses),
        "max_pause": round(max(all_pauses), 2) if all_pauses else 0.0,
        # A pause defect is always worth reporting; spikes get a budget,
        # because a few are normal even in audio that sounds good.
        "ok": not pauses and len(spikes) <= budget,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*", type=Path)
    ap.add_argument("--manifest", type=Path,
                    help="QA every character in a cast manifest")
    ap.add_argument("--detail", action="store_true",
                    help="list each offending pause and spike with timestamps")
    ap.add_argument("--max-spikes", type=int, default=SPIKE_BUDGET,
                    help=f"spikes tolerated per clip (default {SPIKE_BUDGET}, "
                         f"calibrated against approved audio)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    clips = list(args.clips)
    if args.manifest:
        base = args.manifest.parent
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        clips += [base / f"{c['key']}.mp3" for c in data["characters"]]
    if not clips:
        clips = sorted(CAST.glob("*.mp3"))
    clips = [c for c in clips if c.exists()]
    if not clips:
        print("no audio files found", file=sys.stderr)
        return 1

    results = [qa(c, args.max_spikes) for c in clips]

    if args.json:
        print(json.dumps(results, indent=2))
        return 0 if all(r["ok"] for r in results) else 1

    print(f"{'file':<28}{'pauses':>8}{'longest':>9}{'spikes':>8}  verdict")
    for r in results:
        issues = []
        if r["pauses"]:
            issues.append(f"{len(r['pauses'])} uneven pause"
                          f"{'s' if len(r['pauses']) > 1 else ''}")
        if len(r["spikes"]) > args.max_spikes:
            issues.append(f"{len(r['spikes'])} pitch spikes "
                          f"(budget {args.max_spikes})")
        verdict = "ok" if r["ok"] else "CHECK — " + ", ".join(issues)
        print(f"{r['file']:<28}{r['n_pauses']:>8}{r['max_pause']:>8.2f}s"
              f"{len(r['spikes']):>8}  {verdict}")
        if args.detail:
            for p in r["pauses"]:
                print(f"      pause at {p['at']:>6.2f}s  {p['why']}")
            for s in r["spikes"]:
                print(f"      spike at {s['at']:>6.2f}s  +{s['st']} st "
                      f"({s['hz']} Hz) for {s['span']}s")

    bad = [r for r in results if not r["ok"]]
    print(f"\n{len(results)} clip(s), {len(bad)} to check by ear")
    if bad and not args.detail:
        print("Re-run with --detail for timestamps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
