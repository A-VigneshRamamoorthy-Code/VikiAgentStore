#!/usr/bin/env python3
"""Grade a finished film against this style's measured look envelope.

`motionprofile.py` (in `style-animation-director`) asks whether a film *moves*
like the plan says it should. This asks the other half of the question:
whether it *looks* like the style claims to. They are independent failures --
a film can hit every motion target while being twice as saturated and cut ten
times as often as the thing it is supposed to resemble. That is exactly what
happened here, and nothing in the toolchain noticed, because nothing was
looking.

The numbers in `style.json -> verify.look` were measured off the two reference
films rather than chosen, so this is a comparison against evidence and not
against taste. Run it on the reference itself and it passes, by construction;
that is the point, and `--reference` makes the claim checkable rather than
asking you to take it on faith.

    python3 lookcheck.py film.mp4
    python3 lookcheck.py film.mp4 --reference ref.webm   # grade both, side by side
    python3 lookcheck.py film.mp4 --json

Exit status is 0 when every metric is inside the envelope, 1 otherwise, so it
drops straight into a verification step.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_JSON = os.path.join(os.path.dirname(HERE), "style.json")

# Sampling. A fixed *rate*, not a fixed count.
#
# A fixed count was tried first and is subtly wrong in two ways at once. Cut
# detection depends on how far apart the samples are, so a fixed count makes a
# long film look like it cuts less than a short one with identical grammar;
# and normalising the result back to minutes then requires knowing which kind
# of minute you meant. (It reported the 115s reference at 6.0 "cuts/min"
# against a measured truth of 3.1 -- the count was per 60 samples, not per 60
# seconds.) A fixed rate makes every number directly comparable between films
# of any length, and 4 fps is close enough that no cut can hide between two
# samples. At 320px wide it costs well under a second for a 2-minute film.
FPS = 4.0
WIDTH = 320

# A frame-to-frame greyscale delta above this is a cut rather than motion.
# Chosen from the reference films: their within-shot deltas sit around 0.01
# and their cuts land above 0.2, so anywhere in between separates them
# cleanly. 0.10 is the middle of that gap in log terms.
CUT_DELTA = 0.10


def _need(binary):
    if shutil.which(binary) is None:
        sys.exit("lookcheck: %s not found on PATH" % binary)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        sys.exit("lookcheck: cannot read duration of %s" % path)


def sample(path, fps=FPS):
    """Return an (n, h, w, 3) float array in 0..1, and the film's duration."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        sys.exit("lookcheck: needs numpy and Pillow (%s)" % exc)

    dur = duration(path)
    tmp = tempfile.mkdtemp(prefix="lookcheck-")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", path,
             "-vf", "fps=%.6f,scale=%d:-1" % (fps, WIDTH),
             os.path.join(tmp, "f%04d.png")], check=True)
        files = sorted(glob.glob(os.path.join(tmp, "f*.png")))
        if len(files) < 2:
            sys.exit("lookcheck: %s yielded %d frames" % (path, len(files)))
        arr = np.stack([
            np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) / 255.0
            for f in files])
        return arr, dur
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def measure(path):
    import numpy as np
    a, dur = sample(path)

    mx, mn = a.max(-1), a.min(-1)
    # HSV saturation, guarding the black point: (max-min)/max is undefined at
    # max=0 and explodes just above it, which would let a few near-black
    # pixels dominate the mean of an otherwise pale film.
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    val = mx

    grey = a.mean(-1)
    delta = np.abs(np.diff(grey, axis=0)).mean(axis=(1, 2))
    cuts = int((delta > CUT_DELTA).sum())

    return {
        "duration_s": round(dur, 2),
        "saturation_mean": round(float(sat.mean()), 4),
        "saturation_hot_area": round(float((sat > 0.35).mean()), 4),
        "value_mean": round(float(val.mean()), 4),
        "cuts_per_min": round(cuts / max(dur, 1e-6) * 60.0, 2),
        "frame_diff_median": round(float(np.median(delta)), 4),
        "frame_diff_mean": round(float(delta.mean()), 4),
    }


def envelope():
    with open(STYLE_JSON) as fh:
        look = (json.load(fh).get("verify") or {}).get("look") or {}
    if not look:
        sys.exit("lookcheck: style.json has no verify.look envelope")
    return look


# metric -> (label, how to read the bound)
CHECKS = [
    ("saturation_mean",    "saturation_mean",         "range"),
    ("saturation_hot_area", "saturation_hot_area_max", "max"),
    ("value_mean",         "value_mean",              "range"),
    ("cuts_per_min",       "cuts_per_min_max",        "max"),
    # A *range*, and the floor matters as much as the ceiling. The ceiling
    # says "do not thrash"; the floor says "do not freeze". The floor is what
    # makes `compile.py`'s `SELF_ANIMATING` exemption safe: shots compiled
    # from `observe` skip the camera-creep rescue on the promise that the set
    # animates itself, and this is where that promise is actually collected.
    # A film of one motionless drawing scores 0.000 and fails here.
    ("frame_diff_median",  "frame_diff_median",       "range"),
]


def grade(m, env):
    rows = []
    for metric, key, kind in CHECKS:
        bound = env.get(key)
        if bound is None:
            continue
        got = m[metric]
        if kind == "range":
            lo, hi = bound
            ok = lo <= got <= hi
            want = "%.3f..%.3f" % (lo, hi)
        else:
            ok = got <= bound
            want = "<= %.3f" % bound
        rows.append((metric, got, want, ok))
    return rows


def report(label, m, rows):
    print("\n%s  (%.1fs)" % (label, m["duration_s"]))
    for metric, got, want, ok in rows:
        print("  %-20s %8.3f   want %-14s %s"
              % (metric, got, want, "ok" if ok else "FAIL"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film")
    ap.add_argument("--reference", action="append", default=[],
                    metavar="FILM",
                    help="also measure this film, for a side-by-side. Graded "
                         "too, so a reference that fails tells you the "
                         "envelope is wrong rather than the film.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    _need("ffmpeg")
    _need("ffprobe")
    env = envelope()

    mine = measure(args.film)
    rows = grade(mine, env)
    refs = [(p, measure(p)) for p in args.reference]

    if args.json:
        print(json.dumps({
            "film": {"path": args.film, **mine,
                     "pass": all(r[3] for r in rows),
                     "checks": [{"metric": r[0], "value": r[1],
                                 "want": r[2], "pass": r[3]} for r in rows]},
            "reference": [{"path": p, **m} for p, m in refs],
            "envelope": env,
        }, indent=2))
        return 0 if all(r[3] for r in rows) else 1

    report(os.path.basename(args.film), mine, rows)
    for p, m in refs:
        report("reference: " + os.path.basename(p), m, grade(m, env))

    bad = [r[0] for r in rows if not r[3]]
    print()
    if bad:
        print("FAIL -- outside the reference envelope: %s" % ", ".join(bad))
        return 1
    print("ok -- inside the reference envelope on all %d metrics" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
