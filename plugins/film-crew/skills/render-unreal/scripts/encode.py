#!/usr/bin/env python3
"""Turn a directory of rendered PNG frames into a finished file.

The interesting part is `first_settled_frame`. Unreal's capture writes a
variable number of warm-up frames, and they are not all black: on this pipeline
frame 0 is black, **frame 1 contains the backdrop but none of the translucent
characters**, and only frame 2 onward is correct. Anything that trims on
"first non-black" therefore ships a film whose opening frame has no cast in it,
which is both wrong and very easy to miss.

So instead of trusting brightness, this measures how much each frame differs
from the next. Warm-up frames differ from their successor enormously compared
with the frame-to-frame difference of genuine motion, so the first frame whose
difference falls into the normal range is the first real one.

    python3 encode.py /tmp/render out.mp4 --fps 30 --audio mix.wav
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image


def frame_paths(folder):
    files = sorted(glob.glob(os.path.join(folder, "*.png")))
    if not files:
        sys.exit("encode: no PNG frames in %s" % folder)
    return files


def _small(path, size=(320, 180)):
    return np.asarray(Image.open(path).convert("RGB").resize(size)).astype(np.float32)


def _ink(frame):
    """Fraction of the frame that is not its own dominant colour.

    A rough measure of how much *stuff* is in shot. It is the signal that
    actually separates a warm-up frame from a real one: a half-initialised
    frame is missing whole layers, so its ink collapses, whereas ordinary
    motion barely moves it.
    """
    quantised = (frame // 16).astype(np.int32)
    flat = quantised.reshape(-1, 3)
    colours, counts = np.unique(flat, axis=0, return_counts=True)
    modal = colours[counts.argmax()]
    return float((np.abs(quantised - modal).sum(axis=2) > 2).mean())


def first_settled_frame(files, max_warmup=12, probe=40, verbose=True):
    """Index of the first frame that belongs to the film rather than the warm-up.

    Two independent signals, because neither is sufficient alone. A large
    difference to the next frame catches the black frame; a collapse in ink
    coverage catches the far nastier case where the backdrop has drawn but the
    translucent cast has not. Trimming an extra frame costs 1/30th of a second
    and nobody will ever see it; keeping a bad one ruins the opening shot, so
    where the two disagree this believes whichever says warm-up.
    """
    n = min(len(files) - 1, probe)
    if n < 4:
        return 0

    thumbs = [_small(f) for f in files[:n + 1]]
    diffs = [float(np.abs(thumbs[i + 1] - thumbs[i]).mean()) for i in range(n)]
    inks = [_ink(t) for t in thumbs]

    # The settled part of the probe window defines what normal looks like.
    tail = slice(max(max_warmup, len(inks) // 2), None)
    plateau = float(np.median(inks[tail])) or 1e-6
    baseline = float(np.median(diffs[len(diffs) // 2:])) or 0.01
    diff_limit = max(baseline * 3.0, 0.5)

    scan = min(max_warmup, n)
    last_bad = -1
    for i in range(scan):
        starved = inks[i] < plateau * 0.75
        jumpy = diffs[i] > diff_limit
        if starved or jumpy:
            last_bad = i
    start = min(last_bad + 1, scan)

    if verbose:
        print("warm-up scan: ink plateau %.3f, diff baseline %.2f" % (plateau, baseline))
        print("  frame    ink   diff-to-next  verdict")
        for i in range(min(scan + 2, len(inks))):
            d = diffs[i] if i < len(diffs) else 0.0
            verdict = "warm-up" if i < start else "ok"
            print("  %5d  %6.3f  %11.2f  %s" % (i, inks[i], d, verdict))
        print("  -> first real frame %d" % start)
    return start


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("encode: command failed\n%s\n%s" % (" ".join(cmd), proc.stderr[-2000:]))
    return proc


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frames")
    ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--audio")
    ap.add_argument("--captions", help="an .srt to burn in")
    ap.add_argument("--crf", type=int, default=17)
    ap.add_argument("--start", type=int, default=-1,
                    help="override warm-up detection")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("encode: ffmpeg not found")

    files = frame_paths(args.frames)
    start = args.start if args.start >= 0 else first_settled_frame(files)

    pattern = files[0]
    stem = os.path.basename(pattern).rsplit(".", 2)[0]
    pattern = os.path.join(args.frames, stem + ".%04d.png")

    cmd = ["ffmpeg", "-y", "-start_number", str(start),
           "-framerate", str(args.fps), "-i", pattern]
    if args.audio:
        cmd += ["-i", args.audio]

    filters = []
    if args.captions:
        # A path is interpolated into a filter string, so its separators and
        # colons have to be escaped or ffmpeg reads them as filter syntax.
        srt = args.captions.replace("\\", "/").replace(":", "\\:")
        filters.append("subtitles='%s'" % srt)
    if filters:
        cmd += ["-vf", ",".join(filters)]

    cmd += ["-c:v", "libx264", "-crf", str(args.crf), "-preset", "slow",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if args.audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += [args.out]

    run(cmd)

    probe = run(["ffprobe", "-v", "error", "-show_entries",
                 "format=duration,size:stream=codec_type,width,height,r_frame_rate",
                 "-of", "default=noprint_wrappers=1", args.out])
    print("\n%s" % args.out)
    for line in probe.stdout.strip().splitlines():
        print("  " + line)
    print("  frames used: %d of %d (trimmed %d warm-up)"
          % (len(files) - start, len(files), start))


if __name__ == "__main__":
    main()
