#!/usr/bin/env python3
"""Put a film next to its reference, frame for frame, so a claim about the
look can be checked by eye rather than argued about.

`lookcheck.py` answers the question numerically. This answers it visually,
which is the only form of the answer anyone actually trusts. Both are needed:
the numbers catch what the eye forgives, and the eye catches what the numbers
have no metric for -- composition, silhouette, where the weight of the frame
sits.

    python3 sidebyside.py mine.mp4 reference.webm -o compare.jpg

Sampled at matched *fractions* of each film rather than matched seconds, so
films of different lengths line up at their beginning, middle and end instead
of drifting apart.

Either argument may also be a **still** (`.png`/`.jpg`), which is how you
compare one composed frame against one reference frame:

    python3 sidebyside.py mine.png ref.png -o compare.jpg

It also prints the region readings below, because the eye is unreliable about
exactly the things this style is graded on. Every one of these caught a real
defect that looking at the frame had missed:

* **sky sat/hue** -- a near-neutral sky drags the whole film to grey through
  `depth_tint`, however colourful the rest of the palette is.
* **warm/cool gap** -- the reference opposes a ~220 deg sky against a ~35 deg
  peak. Without that opposition the frame reads as greyscale, not as painted.
* **terrain apex/width** -- composition, which no colour metric sees.
* **streak energy** -- weather that is meant to be noticed second, not first.

Character pixels are excluded from the terrain readings: the figure is the
most saturated thing in frame, and a naive threshold reports its hat as the
mountain top.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROWS = 4
LABEL_H = 22
GAP = 6


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return float(out)


STILL_EXT = (".png", ".jpg", ".jpeg", ".webp")


def is_still(path):
    return os.path.splitext(path)[1].lower() in STILL_EXT


def frames_at(path, fractions, width):
    """One frame per fraction of the film's duration, as PIL images.

    A still is returned once per requested fraction, so a still can stand in
    for a film anywhere a film is expected.
    """
    from PIL import Image
    if is_still(path):
        im = Image.open(path).convert("RGB")
        im = im.resize((width, max(1, round(width * im.height / im.width))),
                       Image.LANCZOS)
        return [im.copy() for _ in fractions]
    dur = duration(path)
    tmp = tempfile.mkdtemp(prefix="sbs-")
    out = []
    try:
        for i, f in enumerate(fractions):
            t = max(0.0, min(dur - 0.05, dur * f))
            dst = os.path.join(tmp, "f%02d.png" % i)
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % t,
                 "-i", path, "-frames:v", "1",
                 "-vf", "scale=%d:-1" % width, dst], check=True)
            out.append(Image.open(dst).convert("RGB").copy())
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def measure(im):
    """Region readings for one frame. Returns a dict, or None without numpy."""
    try:
        import numpy as np
    except ImportError:
        return None
    import colorsys

    rgb = np.asarray(im, np.float32) / 255.0
    H, W = rgb.shape[:2]
    mx, mn = rgb.max(2), rgb.min(2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    val = mx
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)

    def hue_of(region):
        m = region.reshape(-1, 3).mean(0)
        return colorsys.rgb_to_hsv(*m)[0] * 360.0

    top = slice(0, int(H * 0.25))
    out = {
        "frame sat": float(sat.mean()),
        "frame val": float(val.mean()),
        "sky sat": float(sat[top].mean()),
        "sky hue": hue_of(rgb[top]),
    }

    # The character is the most saturated thing in the frame, so it has to be
    # excluded before anything is asked about the terrain -- otherwise a hat
    # is measured as the summit.
    figure = sat > 0.30
    ys, xs = np.nonzero(figure)
    if len(ys) > 40:
        out["figure height"] = float((ys.max() - ys.min()) / H * 100.0)
        out["figure sat"] = float(sat[figure].mean())

    terrain = (lum < 0.45) & (sat < 0.28)
    tops = [(x, np.nonzero(terrain[:, x])[0]) for x in range(W)]
    tops = {x: c.min() for x, c in tops if len(c) >= max(4, H // 100)}
    if tops:
        ax = min(tops, key=lambda k: tops[k])
        ks = sorted(tops)
        out["terrain apex y"] = float(tops[ax] / H * 100.0)
        out["terrain width"] = float((ks[-1] - ks[0]) / W * 100.0)

    # Near-vertical streaks (rain) register on a *horizontal* derivative; the
    # smooth cloud gradient does not. Measured on sky only, to keep terrain
    # edges out of it.
    sky = lum[top]
    if sky.shape[0] > 2:
        out["streak energy"] = float(np.abs(np.diff(sky, axis=1)).mean() * 1000.0)
    return out


def print_measurements(mine, ref):
    a, b = measure(mine), measure(ref)
    if a is None or b is None:
        print("  (install numpy for region measurements)")
        return
    print("\n  %-16s %9s %9s" % ("region", "mine", "reference"))
    for k in ("frame sat", "frame val", "sky sat", "sky hue", "figure height",
              "figure sat", "terrain apex y", "terrain width", "streak energy"):
        if k in a and k in b:
            print("  %-16s %9.3f %9.3f" % (k, a[k], b[k]))
    if "sky hue" in a:
        print("\n  warm/cool: the reference opposes a cool sky against a warm "
              "peak by ~180 deg;\n  a frame whose regions share a hue reads as "
              "greyscale however saturated it is.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film")
    ap.add_argument("reference")
    ap.add_argument("-o", "--out", default="compare.jpg")
    ap.add_argument("--rows", type=int, default=ROWS)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--stack", action="store_true",
                    help="stack the two vertically instead of side by side, "
                         "which keeps full width for a single-frame compare")
    ap.add_argument("--no-measure", action="store_true",
                    help="skip the region readings")
    args = ap.parse_args(argv)

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("sidebyside: needs Pillow")

    n = max(2, args.rows)
    if is_still(args.film) and is_still(args.reference):
        n = 1                       # two stills are one row, not four copies
    # Avoid 0.0 and 1.0: the first frame of a film is often a fade-in and the
    # last is often a fade-out, and neither is representative of the look.
    fracs = [(i + 0.5) / n for i in range(n)]

    mine = frames_at(args.film, fracs, args.width)
    ref = frames_at(args.reference, fracs, args.width)

    cw = args.width
    ch = max(max(im.height for im in mine), max(im.height for im in ref))
    if args.stack:
        W = cw + GAP * 2
        H = n * (LABEL_H + ch + LABEL_H + ch + GAP) + GAP
    else:
        W = cw * 2 + GAP * 3
        H = LABEL_H + n * (ch + GAP) + GAP

    sheet = Image.new("RGB", (W, H), (18, 18, 20))
    d = ImageDraw.Draw(sheet)
    mine_label = "MINE — %s" % os.path.basename(args.film)
    ref_label = "REFERENCE — %s" % os.path.basename(args.reference)

    if args.stack:
        y = GAP
        for i in range(n):
            d.text((GAP + 4, y), mine_label, fill=(120, 220, 255))
            y += LABEL_H
            sheet.paste(mine[i], (GAP, y)); y += ch
            d.text((GAP + 4, y), ref_label, fill=(255, 220, 120))
            y += LABEL_H
            sheet.paste(ref[i], (GAP, y)); y += ch + GAP
    else:
        d.text((GAP + 4, 6), mine_label, fill=(120, 220, 255))
        d.text((GAP * 2 + cw + 4, 6), ref_label, fill=(255, 220, 120))
        for i in range(n):
            y = LABEL_H + i * (ch + GAP)
            sheet.paste(mine[i], (GAP, y + (ch - mine[i].height) // 2))
            sheet.paste(ref[i], (GAP * 2 + cw, y + (ch - ref[i].height) // 2))

    sheet.save(args.out, quality=92)
    print("wrote %s  (%dx%d, %d rows)" % (args.out, W, H, n))
    if not args.no_measure:
        print_measurements(mine[0], ref[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
