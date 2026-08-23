#!/usr/bin/env python3
"""Measure generated audio against the acceptance criteria.

    python scripts/analyze.py out/cast/*.mp3
    python scripts/analyze.py --compare source.m4a clone.mp3

Never trust a voice by ear alone — several failure modes (fixed-canvas padding,
inherited hiss, gender inversion) are obvious in numbers and easy to miss when
listening casually.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import F0_RANGE, measure, median_f0  # noqa: E402


def verdict(m: dict, gender: str | None) -> tuple[str, list[str]]:
    problems = []
    if m["gaps"] > 0:
        problems.append(f"{m['gaps']} gap(s) >0.5s — duration_s was probably set")
    if m["noise_floor"] > -45:
        problems.append(f"noise floor {m['noise_floor']} dB — denoise the reference")
    if m["dur"] < 1.0:
        problems.append("under 1s — generation truncated")
    if gender:
        lo, hi = F0_RANGE[gender]
        if not (lo <= m["f0"] <= hi):
            problems.append(f"F0 {m['f0']} Hz outside {gender} {lo}-{hi} Hz")
    return ("FAIL" if problems else "ok"), problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--gender", choices=["male", "female"],
                    help="also check F0 falls in this gender's range")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("SOURCE", "CLONE"),
                    help="check a clone inherited its source's timbre")
    args = ap.parse_args()

    if args.compare:
        src, clone = args.compare
        a, b = median_f0(src), median_f0(clone)
        if not a["n"] or not b["n"]:
            print("No voiced frames in one of the files.")
            return 1
        drift = abs(b["median"] - a["median"]) / a["median"] * 100
        print(f"source  {src.name:<28} {a['median']:6.1f} Hz  "
              f"({a['p10']:.0f}-{a['p90']:.0f})")
        print(f"clone   {clone.name:<28} {b['median']:6.1f} Hz  "
              f"({b['p10']:.0f}-{b['p90']:.0f})")
        print(f"\ndrift {drift:.1f}%  ->  "
              f"{'timbre transferred' if drift < 5 else 'CLONE DID NOT MATCH'}")
        return 0 if drift < 5 else 1

    if not args.files:
        return ap.error("give files to analyze, or use --compare")

    failures = 0
    print(f"{'file':<26}{'dur':>7}{'F0':>8}{'noise':>9}{'gaps':>6}  status")
    for f in args.files:
        if not f.exists():
            print(f"{f.name:<26}  missing")
            failures += 1
            continue
        m = measure(f)
        status, problems = verdict(m, args.gender)
        print(f"{f.name:<26}{m['dur']:6.1f}s{m['f0']:7.1f}Hz"
              f"{m['noise_floor']:8.1f}dB{m['gaps']:6}  {status}")
        for p in problems:
            print(f"    ! {p}")
            failures += 1

    print(f"\n{len(args.files)} file(s), {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
