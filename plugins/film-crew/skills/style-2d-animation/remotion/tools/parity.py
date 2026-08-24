#!/usr/bin/env python3
"""Numeric parity between the Python renderer and the Remotion port.

Both engines consume the same board and the same resolved timeline, so a
difference is a difference in the picture pipeline and nothing else. This
compares **exact frame indices** rather than timestamps: a timestamp seek can
land a frame either side of a cut, and on a shot with a moving camera that
single frame is worth more MAE than any real error.

Broadcast furniture is masked out by default. The overlays were redesigned
against the reference the user supplied, so they are deliberately *not* the
Python engine's -- scoring them would measure an intended change.

    python3 tools/parity.py --shots s2 s5 s10 --diff /tmp/diff
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: Fractional (x0, y0, x1, y1) boxes that hold broadcast furniture.
#:
#: These follow the *actual* geometry in `src/overlays/Overlays.jsx` rather
#: than where furniture is conventionally put: the channel mark and the live
#: clock are anchored to the bottom corners here, not the top ones, and a
#: mask placed by convention scores the lower third twice while leaving the
#: real thing exposed.
OVERLAY_BOXES = [
    (0.00, 0.68, 1.00, 1.00),   # lower third, channel mark, clock, ticker
    (0.00, 0.02, 0.34, 0.13),   # location tag
    (0.70, 0.07, 0.98, 0.43),   # map inset
]


def frame_from(video, index, out):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video,
         "-vf", f"select=eq(n\\,{index})", "-vsync", "0", "-frames:v", "1", out],
        check=True)
    return out


def mask_for(shape):
    h, w = shape[:2]
    m = np.ones((h, w), dtype=bool)
    for x0, y0, x1, y1 in OVERLAY_BOXES:
        m[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = False
    return m


def compare(a_path, b_path, diff_path=None, masked=True):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.float32)
    if a.shape != b.shape:
        raise SystemExit(f"shape {a.shape} != {b.shape}")
    d = np.abs(a - b)
    full = float(d.mean())
    m = mask_for(a.shape) if masked else np.ones(a.shape[:2], dtype=bool)
    sub = float(d[m].mean())
    if diff_path:
        vis = np.clip(d.mean(axis=2) * 4.0, 0, 255).astype(np.uint8)
        vis = np.stack([vis, vis, vis], axis=2)
        vis[~m] = [0, 0, 60]
        Image.fromarray(vis).save(diff_path)
    return full, sub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="/tmp/pursuit_python_clip0-77.775.mp4")
    ap.add_argument("--remotion",
                    default=os.path.join(ROOT, "out", "pursuit_remotion.mp4"))
    ap.add_argument("--timeline",
                    default=os.path.join(ROOT, "data", "timeline.json"))
    ap.add_argument("--shots", nargs="*", default=None)
    ap.add_argument("--diff", default=None)
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()

    shots = json.load(open(args.timeline))["shots"]
    if args.shots:
        shots = [s for s in shots if s["id"] in set(args.shots)]
    if args.diff:
        os.makedirs(args.diff, exist_ok=True)

    tmp = "/tmp/_parity"
    os.makedirs(tmp, exist_ok=True)
    rows = []
    for s in shots:
        n = int(round((s["start"] + s["end"]) / 2.0 * args.fps))
        pa = frame_from(args.python, n, f"{tmp}/py_{s['id']}.png")
        rb = frame_from(args.remotion, n, f"{tmp}/rm_{s['id']}.png")
        dp = os.path.join(args.diff, f"{s['id']}.png") if args.diff else None
        full, sub = compare(pa, rb, dp)
        rows.append((s["id"], s["set"], s["camera"], n, full, sub))
        print(f"{s['id']:5s} {s['set']:8s} {s['camera']:9s} f{n:5d} "
              f"full {full:6.2f}  masked {sub:6.2f}")

    if rows:
        vals = [r[5] for r in rows]
        print(f"\nmean masked MAE {sum(vals) / len(vals):6.2f}/255 "
              f"({sum(vals) / len(vals) / 255 * 100:.1f}%)   "
              f"best {min(vals):.2f}  worst {max(vals):.2f}   n={len(vals)}")


if __name__ == "__main__":
    main()
