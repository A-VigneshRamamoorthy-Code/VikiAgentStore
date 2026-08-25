#!/usr/bin/env python3
"""Synthesise a music bed for a stock-footage film.

    python3 score.py --mood tension --duration 117.1 -o bed.wav

A stock-footage cut is forty strangers' clips in a row. Two things make it one
film: a single colour grade, and a single piece of music running underneath.
Without the second, the cut reads as a showreel — every shot is competing, and
nothing tells the viewer that the last shot and the next one belong together.

So this style scores itself rather than shipping a silent cut and hoping the
sound designer gets to it. The bed is deliberately plain: a pulse, a bass, a
pad, and no melody at all. A bed you can hum is a bed that is fighting the
script — see the sound designer's second non-negotiable.

Self-contained: numpy and the standard library. No samples, no assets, no
network. The sound designer still owns the *mix* — this only makes the bed.
"""

import argparse
import math
import os
import struct
import sys
import wave

try:
    import numpy as np
except ImportError:
    print("stock/score: numpy is required", file=sys.stderr)
    raise SystemExit(1)

SR = 44100

#: Every mood is one scale, one tempo and one instrumentation. They are the
#: sound designer's mood names, so a film's picture, its grade and its score
#: are all chosen by the same word out of the story.
#:
#: `degrees` are semitone offsets from the root, and the progression walks them
#: one chord per bar. Minor sixths and flat seconds are what make the tense
#: moods tense; there is no cleverness beyond that.
MOODS = {
    "tension": {
        "root": 41.0, "bpm": 132, "pulse": True, "ticks": True,
        "chords": [(0, 3, 7), (0, 3, 7), (-2, 1, 5), (0, 3, 7)],
        "pad": 0.16, "bass": 0.42, "drone": 0.20, "bright": 0.9,
    },
    "dread": {
        "root": 36.0, "bpm": 84, "pulse": False, "ticks": False,
        "chords": [(0, 3, 6), (0, 3, 6), (-1, 2, 6), (0, 3, 7)],
        "pad": 0.22, "bass": 0.30, "drone": 0.34, "bright": 0.45,
    },
    "triumph": {
        "root": 43.0, "bpm": 104, "pulse": True, "ticks": False,
        "chords": [(0, 4, 7), (5, 9, 12), (-3, 4, 7), (0, 4, 7)],
        "pad": 0.26, "bass": 0.32, "drone": 0.14, "bright": 1.0,
    },
    "elegy": {
        "root": 38.0, "bpm": 68, "pulse": False, "ticks": False,
        "chords": [(0, 3, 7), (-4, 3, 8), (-2, 3, 7), (0, 3, 10)],
        "pad": 0.30, "bass": 0.22, "drone": 0.22, "bright": 0.5,
    },
    "curious": {
        "root": 45.0, "bpm": 112, "pulse": True, "ticks": True,
        "chords": [(0, 4, 7), (2, 5, 9), (0, 4, 9), (-3, 2, 7)],
        "pad": 0.20, "bass": 0.26, "drone": 0.10, "bright": 1.0,
    },
    "reflective": {
        "root": 40.0, "bpm": 76, "pulse": False, "ticks": False,
        "chords": [(0, 4, 7), (-3, 2, 7), (0, 4, 9), (-5, 0, 7)],
        "pad": 0.30, "bass": 0.20, "drone": 0.18, "bright": 0.6,
    },
}


def hz(midi):
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def lowpass(x, fc, sr=SR):
    """One-pole lowpass. Crude, stable, and exactly what a bed wants —
    anything sharper starts sounding like an effect."""
    a = math.exp(-2.0 * math.pi * fc / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _fast_lowpass(x, fc, sr=SR):
    """A vectorised approximation of the above, for signals long enough that
    the Python loop would dominate the render."""
    n = max(1, int(sr / max(1.0, fc)))
    k = np.hanning(n * 2 + 1)
    k /= k.sum()
    return np.convolve(x, k, mode="same")


def pad(freqs, dur, gain, bright, seed=0):
    """A slow, detuned stack. The bed's harmonic body."""
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.006, 0.0, 0.006):
            ph = rng.random() * 2 * math.pi
            out += np.sin(2 * math.pi * f * (1 + det) * t + ph)
            out += 0.28 * bright * np.sin(4 * math.pi * f * (1 + det) * t + ph)
    out /= max(1.0, len(freqs) * 3.0)
    # Breathe, so a held chord is not a held tone.
    lfo = 1.0 + 0.10 * np.sin(2 * math.pi * 0.09 * t + seed)
    env = np.ones(n)
    a = min(n, int(0.7 * SR))
    env[:a] = np.linspace(0, 1, a)
    env[-a:] *= np.linspace(1, 0, a)
    return out * lfo * env * gain


def bass_note(f, dur, gain):
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / SR
    env = np.exp(-t * 5.5)
    w = np.sin(2 * math.pi * f * t) + 0.35 * np.sin(4 * math.pi * f * t)
    return w * env * gain


def tick(dur, gain, seed):
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    return rng.standard_normal(n) * np.exp(-t * 90.0) * gain


def build(mood, duration, seed=7):
    spec = MOODS.get(mood) or MOODS["reflective"]
    n = int(duration * SR)
    out = np.zeros(n + SR)

    bar = 4.0 * 60.0 / spec["bpm"]
    beat = 60.0 / spec["bpm"]
    root = spec["root"]

    # ---- pad: one chord per bar, overlapping so chords cross-fade rather
    # than cut. A bed that changes chord on a hard edge is audible as an edit.
    i, t = 0, 0.0
    while t < duration:
        chord = spec["chords"][i % len(spec["chords"])]
        freqs = [hz(root + 12 + d) for d in chord]
        seg = pad(freqs, bar * 1.25, spec["pad"], spec["bright"], seed + i)
        s = int(t * SR)
        e = min(len(out), s + len(seg))
        out[s:e] += seg[:e - s]
        t += bar
        i += 1

    # ---- drone: the root, continuous, felt rather than heard.
    if spec["drone"] > 0:
        tt = np.arange(len(out)) / SR
        f = hz(root)
        drone = (np.sin(2 * math.pi * f * tt)
                 + 0.5 * np.sin(2 * math.pi * f * 0.5 * tt))
        drone *= 1.0 + 0.06 * np.sin(2 * math.pi * 0.05 * tt)
        out += drone * spec["drone"] * 0.5

    # ---- bass: on the bar for the calm moods, on the beat for the driving
    # ones. This single switch is most of the difference between a bed that
    # sits still and one that pushes.
    step = beat if spec["pulse"] else bar
    i, t = 0, 0.0
    while t < duration:
        chord = spec["chords"][(int(t / bar)) % len(spec["chords"])]
        f = hz(root + chord[0])
        accent = 1.0 if (i % 2 == 0 or not spec["pulse"]) else 0.55
        seg = bass_note(f, min(step * 1.6, 1.2), spec["bass"] * accent)
        s = int(t * SR)
        e = min(len(out), s + len(seg))
        out[s:e] += seg[:e - s]
        t += step
        i += 1

    # ---- ticks: a clock under a chase. Off-beat, quiet, and the one element
    # a viewer notices consciously — so it is used in two moods only.
    if spec["ticks"]:
        t = beat / 2.0
        j = 0
        while t < duration:
            seg = tick(0.05, 0.09, seed + j)
            s = int(t * SR)
            e = min(len(out), s + len(seg))
            out[s:e] += seg[:e - s]
            t += beat
            j += 1

    out = out[:n]
    out = _fast_lowpass(out, 5200.0)

    # Top and tail, so the bed arrives and leaves rather than being switched on.
    a = min(n // 2, int(2.2 * SR))
    if a > 0:
        out[:a] *= np.linspace(0, 1, a)
        out[-a:] *= np.linspace(1, 0, a)

    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak * 0.5


def write_wav(path, mono):
    stereo = np.stack([mono, mono], axis=1)
    data = np.clip(stereo, -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def main():
    ap = argparse.ArgumentParser(description="Synthesise a music bed.")
    ap.add_argument("--mood", default="reflective", choices=sorted(MOODS))
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    if a.duration <= 0:
        print("stock/score: duration must be positive", file=sys.stderr)
        raise SystemExit(1)

    bed = build(a.mood, a.duration, a.seed)
    write_wav(a.out, bed)
    print("stock/score: %s bed, %.1fs -> %s" % (a.mood, a.duration, a.out),
          file=sys.stderr)


if __name__ == "__main__":
    main()
