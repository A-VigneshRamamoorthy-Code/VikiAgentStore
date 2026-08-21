#!/usr/bin/env python3
"""
Measures audio/video desync in a cut section by locating each stream
independently on the source timeline.

For a correctly cut section both streams should land on the same source
timestamp. The original sections were cut with `-c copy`, which snaps video
back to the nearest preceding keyframe while audio starts exactly at the seek
point -- so the audio runs ahead of the picture.

Run this on at least one clip after every cutting change. Desync is invisible
in a container probe -- both streams report a start time of zero regardless --
so the only way to detect it is to locate each stream on the source timeline
by correlation, which is what this does.

  python3 checks.py <project> <clip.mp4> <expected_source_start_seconds>
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project  # noqa: E402

SRC_A = None
SRC_V = None
SR = 8000


def wav(path, start=None, dur=None):
    """Decode a mono PCM window to a float array."""
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", path]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    return a


def audio_offset(clip, src_start, search=12.0):
    """Cross-correlate clip audio against a window of the source audio."""
    c = wav(clip, 0, 6.0)
    s = wav(SRC_A, src_start - search, 6.0 + 2 * search)
    if len(c) < SR or len(s) < SR:
        return None
    c = c - c.mean()
    s = s - s.mean()
    # envelope correlation is far more robust than raw waveform here
    def env(x, k=80):
        e = np.abs(x)
        return np.convolve(e, np.ones(k) / k, mode="same")
    ce, se = env(c), env(s)
    ce = (ce - ce.mean()) / (ce.std() + 1e-9)
    se = (se - se.mean()) / (se.std() + 1e-9)
    corr = np.correlate(se, ce, mode="valid")
    best = int(np.argmax(corr))
    return (best / SR) - search, float(corr[best] / len(ce))


def frame(path, t, w=160):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t), "-i", path, "-frames:v", "1",
           "-vf", f"scale={w}:-1,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if not raw:
        return None
    n = len(raw)
    h = n // w
    return np.frombuffer(raw[:w * h], np.uint8).astype(np.float32).reshape(h, w)


def video_offset(clip, src_start, search=12.0, step=0.5):
    """Find which source timestamp best matches the clip's opening frame."""
    ref = frame(clip, 0.5)
    if ref is None:
        return None
    best, bt = -2.0, None
    t = src_start - search
    while t <= src_start + search:
        f = frame(SRC_V, t)
        if f is not None and f.shape == ref.shape:
            a = ref.ravel() - ref.mean()
            b = f.ravel() - f.mean()
            d = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
            s = float(np.dot(a, b) / d)
            if s > best:
                best, bt = s, t
        t += step
    return (bt - src_start - 0.5), best


def main():
    global SRC_A, SRC_V
    ap = argparse.ArgumentParser(description="Measure A/V desync in a cut clip")
    ap.add_argument("project")
    ap.add_argument("clip")
    ap.add_argument("start", type=float,
                    help="expected start on the source timeline, in seconds")
    a = ap.parse_args()

    pr = Project(a.project)
    SRC_A = pr.audio
    SRC_V = pr.scan_video
    if not os.path.exists(SRC_A):
        raise SystemExit(f"missing reference audio {SRC_A}; run ingest.py")
    if not os.path.exists(SRC_V):
        raise SystemExit(f"missing scan video {SRC_V}; run ingest.py --video")

    clip, start = a.clip, a.start
    ao = audio_offset(clip, start)
    vo = video_offset(clip, start)
    print(f"clip: {os.path.basename(clip)}  expected source start {start}s")
    if ao:
        print(f"  audio lands at source {start + ao[0]:+.2f}s "
              f"(offset {ao[0]:+.2f}s, corr {ao[1]:.3f})")
    if vo:
        print(f"  video lands at source {start + vo[0]:+.2f}s "
              f"(offset {vo[0]:+.2f}s, corr {vo[1]:.3f})")
    if ao and vo:
        d = vo[0] - ao[0]
        verdict = "IN SYNC" if abs(d) < 0.35 else (
            "AUDIO LEADS PICTURE" if d > 0 else "PICTURE LEADS AUDIO")
        print(f"  => video minus audio = {d:+.2f}s  [{verdict}]")
        return 0 if abs(d) < 0.35 else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
