#!/usr/bin/env python3
"""Regression test for the pause and pitch-spike detectors.

    python scripts/test_qa.py

`qa.py` judges audio, so it cannot be tested against real clips — that would
just be asserting today's output. Instead this builds synthetic signals whose
defects are known exactly, and checks the detector finds those and nothing else.

The interesting cases are the negatives. A detector that fires on a slow pitch
rise, or on a two-frame tracker glitch, is worse than no detector: the first run
of `qa.py` flagged all nine shipped voices and was therefore useless.
"""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import f0_track, median_filter  # noqa: E402
from qa import find_bad_pauses, find_spikes  # noqa: E402

SR = 16000


def tone(freq_at, dur: float, amp: float = 0.35):
    """Sawtooth-ish waveform at a time-varying pitch.

    A pure sine has a weak autocorrelation structure at the true period; a
    harmonic-rich wave is both more speech-like and what the tracker expects.
    """
    n = int(dur * SR)
    phase, out = 0.0, []
    for i in range(n):
        f = freq_at(i / SR)
        phase += 2 * math.pi * f / SR
        v = sum(math.sin(phase * k) / k for k in (1, 2, 3, 4))
        out.append(amp * v / 2.0)
    return out


def silence(dur: float):
    return [0.0] * int(dur * SR)


def write(path: Path, samples) -> None:
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples))


def const(f):
    return lambda t: f


def spike_at(base: float, peak: float, start: float, width: float):
    def f(t):
        return peak if start <= t < start + width else base
    return f


def build(tmp: Path) -> list[tuple[str, Path, int, int]]:
    """(name, path, expected_spikes, expected_bad_pauses)"""
    cases = []

    def add(name, samples, spikes, pauses):
        p = tmp / f"{name}.wav"
        write(p, samples)
        cases.append((name, p, spikes, pauses))

    # -- pitch spikes ------------------------------------------------------
    add("clean_steady", tone(const(150), 4.0), 0, 0)
    # One phoneme jumping +8.8 st and coming straight back: the real artefact.
    add("one_spike", tone(spike_at(150, 250, 2.0, 0.10), 4.0), 1, 0)
    add("two_spikes",
        tone(lambda t: 250 if (1.0 <= t < 1.1 or 2.5 <= t < 2.6) else 150, 4.0),
        2, 0)
    # Slow rise across a second = intonation. Must NOT fire.
    add("slow_rise", tone(lambda t: 150 * (2 ** (min(t, 2.0) / 2.4)), 4.0), 0, 0)
    # A 20 ms blip is below pitch perception and is almost always a glitch.
    add("micro_blip", tone(spike_at(150, 300, 2.0, 0.02), 4.0), 0, 0)
    # A small wobble within normal stress range must NOT fire.
    add("mild_stress", tone(spike_at(150, 178, 2.0, 0.10), 4.0), 0, 0)
    # High-pitched voice: thresholds are in semitones, so this behaves the same.
    add("female_spike", tone(spike_at(240, 400, 2.0, 0.10), 4.0), 1, 0)

    # -- pauses ------------------------------------------------------------
    even = (tone(const(150), 1.2) + silence(0.30) + tone(const(150), 1.2)
            + silence(0.30) + tone(const(150), 1.2) + silence(0.30)
            + tone(const(150), 1.2))
    add("even_pauses", even, 0, 0)

    stall = (tone(const(150), 1.2) + silence(0.30) + tone(const(150), 1.2)
             + silence(1.60) + tone(const(150), 1.2) + silence(0.30)
             + tone(const(150), 1.2))
    add("one_stall", stall, 0, 1)

    # Under the 1.0 s ceiling but wildly out of character for this clip.
    ragged = (tone(const(150), 1.0) + silence(0.15) + tone(const(150), 1.0)
              + silence(0.80) + tone(const(150), 1.0) + silence(0.15)
              + tone(const(150), 1.0))
    add("ragged_pauses", ragged, 0, 1)

    # Long lead-in and tail-out are trimming artefacts, not rhythm.
    edges = (silence(1.50) + tone(const(150), 2.0) + silence(1.50))
    add("edge_silence", edges, 0, 0)

    return cases


def main() -> int:
    failed = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, path, want_spikes, want_pauses in build(tmp):
            spikes = find_spikes(median_filter(f0_track(path)))
            pauses = find_bad_pauses(path)
            if len(spikes) != want_spikes:
                failed.append(
                    f"  FAIL {name}: expected {want_spikes} spike(s), "
                    f"got {len(spikes)} {[(s['at'], s['st']) for s in spikes]}")
            if len(pauses) != want_pauses:
                failed.append(
                    f"  FAIL {name}: expected {want_pauses} bad pause(s), "
                    f"got {len(pauses)} {[(p['at'], p['why']) for p in pauses]}")

    for f in failed:
        print(f)
    total = 22          # 11 cases x 2 assertions
    print(f"\n{total - len(failed)}/{total} passing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
