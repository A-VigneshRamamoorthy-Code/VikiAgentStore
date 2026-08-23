#!/usr/bin/env python3
"""Measure whether two voices actually sound like different people.

    python scripts/timbre.py out/cast/*.mp3
    python scripts/timbre.py --manifest out/cast/manifest.json

Median F0 alone is a bad distinctness test. Two characters cloned from
*different* recordings can sit 1 Hz apart and still be obviously different
speakers, because accent, formants and cadence do the work that pitch doesn't.
This compares the timbre itself — the average cepstrum, which is roughly "what
shape is this person's vocal tract" — so `build_cast.py`'s "check by ear"
advisory becomes something you can actually check.

Cosine similarity of mean+std MFCCs, ignoring c0 (loudness):

    < 0.90   distinct     different people
    < 0.97   close        same-ish; confirm by ear before shipping both
    >= 0.97  TOO CLOSE    listeners will not reliably tell them apart

Only same-gender pairs are compared; cross-gender pairs are distinct by
construction and would just add noise to the table.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.fftpack import dct

# OmniVoice's native rate; everything in this skill is resampled to it.
SR = 24000

N_FFT = 1024
HOP = 256
N_MFCC = 20
N_MEL = 40
# Below ~0.90 two voices read as different people; at/above 0.97 they don't.
DISTINCT = 0.90
TOO_CLOSE = 0.97
# Voiced speech energy lives well inside this band; going wider just adds
# hiss and MP3 cutoff artefacts to the comparison.
FMIN, FMAX = 50, 8000
# Frames quieter than 5% of peak are pauses. Averaging them in makes every
# voice look alike, because silence has no timbre.
SILENCE_REL = 0.05


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(path),
         "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def mel_filterbank() -> np.ndarray:
    to_mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)  # noqa: E731
    to_hz = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)  # noqa: E731
    points = to_hz(np.linspace(to_mel(FMIN), to_mel(FMAX), N_MEL + 2))
    bins = np.floor((N_FFT + 1) * points / SR).astype(int)
    fb = np.zeros((N_MEL, N_FFT // 2 + 1))
    for i in range(N_MEL):
        lo, mid, hi = bins[i], bins[i + 1], bins[i + 2]
        if mid > lo:
            fb[i, lo:mid] = (np.arange(lo, mid) - lo) / (mid - lo)
        if hi > mid:
            fb[i, mid:hi] = (hi - np.arange(mid, hi)) / (hi - mid)
    return fb


def profile(path: Path) -> np.ndarray:
    y = decode(path)
    if y.size < N_FFT * 4:
        raise ValueError(f"{path.name}: too short to profile")
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP]
    rms = np.sqrt((frames ** 2).mean(1) + 1e-12)
    frames = frames[rms > rms.max() * SILENCE_REL]
    spec = np.abs(np.fft.rfft(frames * np.hanning(N_FFT), axis=1)) ** 2
    log_mel = np.log(spec @ mel_filterbank().T + 1e-10)
    m = dct(log_mel, type=2, axis=1, norm="ortho")[:, :N_MFCC]
    return np.concatenate([m.mean(0)[1:], m.std(0)[1:]])


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def verdict(score: float) -> str:
    if score < DISTINCT:
        return "distinct"
    return "close" if score < TOO_CLOSE else "TOO CLOSE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--manifest", type=Path,
                    help="read clips and genders from a cast manifest")
    args = ap.parse_args()

    genders: dict[str, str] = {}
    files: list[Path] = []

    if args.manifest:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        root = args.manifest.parent
        for c in data.get("characters", []):
            p = root / f"{c['key']}.mp3"
            if p.exists():
                files.append(p)
                genders[p.stem] = c["gender"]
    files += [f for f in args.files if f.exists()]

    if not files:
        print("no audio files found", file=sys.stderr)
        return 2
    if len(files) < 2:
        print("need at least 2 clips to compare", file=sys.stderr)
        return 2

    profiles = {}
    for f in files:
        try:
            profiles[f.stem] = profile(f)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {f.name}: {e}", file=sys.stderr)

    rows = []
    for a, b in itertools.combinations(sorted(profiles), 2):
        # Without a manifest every clip is treated as one pool.
        if genders and genders.get(a) != genders.get(b):
            continue
        rows.append((cosine(profiles[a], profiles[b]), f"{a} / {b}"))

    if not rows:
        print("no same-gender pairs to compare")
        return 0

    print(f"{'pair':<28}{'cosine':>8}   verdict")
    for score, name in sorted(rows):
        print(f"{name:<28}{score:>8.3f}   {verdict(score)}")

    bad = [n for s, n in rows if s >= TOO_CLOSE]
    print()
    if bad:
        print(f"{len(bad)} pair(s) too similar: {', '.join(bad)}")
        print("Re-cast one of each pair from a different reference recording.")
        return 1
    print(f"{len(rows)} pair(s) compared, all separable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
