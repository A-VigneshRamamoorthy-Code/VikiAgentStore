"""Original music + SFX synthesis with numpy -> 16-bit stereo WAV.

A modern, playful groove whose beat "drops" when the demo starts and breaks down
under the end-card. All original (no copyrighted audio). Driven by config.music /
config.sfx and the computed timeline.
"""
from __future__ import annotations
import wave
import numpy as np

SR = 44100


def _m2hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


class _Buf:
    def __init__(self, dur):
        self.n = int((dur + 0.3) * SR)
        self.L = np.zeros(self.n, np.float32)
        self.R = np.zeros(self.n, np.float32)

    def add(self, start, sig, pan=0.0):
        s = int(start * SR)
        if s >= self.n or s + len(sig) <= 0:
            return
        a = max(0, -s)
        s0 = max(0, s)
        e0 = min(self.n, s + len(sig))
        seg = sig[a:a + (e0 - s0)]
        self.L[s0:e0] += seg * (1 - max(0.0, pan))
        self.R[s0:e0] += seg * (1 + min(0.0, pan))


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _pluck(freq, dur=0.5, tau=0.17, bright=False):
    t = _t(dur)
    env = np.exp(-t / tau) * (1 - np.exp(-t / 0.004))
    s = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 2 * freq * t) + 0.22 * np.sin(2 * np.pi * 3.01 * freq * t)
    if bright:
        s += 0.2 * np.sin(2 * np.pi * 4 * freq * t)
    return (s * env).astype(np.float32)


def _bass(freq, dur=0.42):
    t = _t(dur)
    env = np.exp(-t / 0.22) * (1 - np.exp(-t / 0.004))
    s = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) + 0.12 * np.sin(2 * np.pi * 3 * freq * t)
    return (s * env).astype(np.float32)


def _kick(dur=0.16):
    t = _t(dur)
    env = np.exp(-t / 0.085)
    f = 48 + 130 * np.exp(-t / 0.025)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(phase) * env).astype(np.float32)


def _clap(dur=0.13):
    t = _t(dur)
    env = np.exp(-t / 0.045)
    nse = np.random.uniform(-1, 1, len(t))
    nse = np.concatenate([[0], np.diff(nse)])  # high-pass
    out = np.zeros(len(t), np.float32)
    for d in (0.0, 0.009, 0.018):
        sh = int(d * SR)
        if sh < len(t):
            out[sh:] += (nse * env)[:len(t) - sh]
    return (out * 0.5).astype(np.float32)


def _hat(open=False):
    dur = 0.09 if open else 0.03
    t = _t(dur)
    env = np.exp(-t / (0.045 if open else 0.012))
    nse = np.random.uniform(-1, 1, len(t))
    hp = np.concatenate([[0], np.diff(nse)])
    return (hp * env).astype(np.float32)


def _pad(freqs, dur):
    t = _t(dur)
    a = np.minimum(1, t / 0.2) * np.minimum(1, (dur - t) / 0.3)
    s = np.zeros(len(t), np.float32)
    for f in freqs:
        s += np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.006 * t)
    return (s / max(1, len(freqs) * 2) * a).astype(np.float32)


def _pop(freq=720, tau=0.11, chirp=200):
    t = _t(tau * 4)
    env = np.exp(-t / tau) * (1 - np.exp(-t / 0.002))
    f = freq + chirp * np.exp(-t / 0.05)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return ((np.sin(phase) + 0.4 * np.sin(2 * phase)) * env).astype(np.float32)


def _whoosh(dur=0.34):
    t = _t(dur)
    env = np.sin(np.pi * np.linspace(0, 1, len(t)))
    nse = np.random.uniform(-1, 1, len(t))
    for i in range(1, len(nse)):
        nse[i] = nse[i - 1] * 0.85 + nse[i] * 0.15
    return (nse * env).astype(np.float32)


def _sparkle():
    notes = [1568, 2093, 2637, 3136]
    out = _Buf(1.0)
    for i, f in enumerate(notes):
        t = _t(0.25)
        env = np.exp(-t / 0.09) * (1 - np.exp(-t / 0.002))
        out.add(i * 0.06, (np.sin(2 * np.pi * f * t) * env).astype(np.float32), -0.3 if i % 2 == 0 else 0.3)
    return out


def _riser(dur=0.55):
    t = _t(dur)
    env = (np.linspace(0, 1, len(t))) ** 2
    nse = np.random.uniform(-1, 1, len(t))
    for i in range(1, len(nse)):
        nse[i] = nse[i - 1] * 0.7 + nse[i] * 0.3
    return (nse * env).astype(np.float32)


def render_audio(config, tl, out_path):
    music = config.get("music", {}) or {}
    total = tl["total"]
    buf = _Buf(total)
    vibe = music.get("vibe", "modern-playful")
    bpm = float(music.get("bpm", 120))
    has_drums = vibe in ("modern-playful", "energetic") and music.get("enabled", True)
    has_music = music.get("enabled", True)

    if has_music:
        beat = 60.0 / bpm
        sixteenth = beat / 4
        drop = tl["demo_start"]
        breakdown = total - 2.6
        chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
        arp = [0, 1, 2, 1, 2, 1, 2, 1]
        k = 0
        while True:
            t = 0.55 + k * sixteenth
            if t >= total - 0.1:
                break
            bar = k // 16
            inbar = k % 16
            beat_i = inbar // 4
            sub = inbar % 4
            chord = chords[bar % 4]
            live = has_drums and (drop <= t < breakdown)
            if live:
                if sub == 0 and beat_i in (0, 2):
                    buf.add(t, _kick() * 0.55)
                if beat_i == 2 and sub == 2:
                    buf.add(t, _kick() * 0.34)
                if sub == 0 and beat_i in (1, 3):
                    buf.add(t, _clap() * 0.26)
                if sub in (0, 2):
                    op = beat_i == 3 and sub == 2
                    buf.add(t, _hat(op) * (0.10 if op else 0.07), 0.12)
                if (beat_i == 0 and sub == 0) or (beat_i == 1 and sub == 2) or \
                   (beat_i == 2 and sub == 0) or (beat_i == 3 and sub == 2):
                    buf.add(t, _bass(_m2hz(chord[0] - 12)) * 0.17)
            if sub in (0, 2):
                ei = beat_i * 2 + (1 if sub == 2 else 0)
                note = chord[arp[ei % len(arp)] % len(chord)] + 12
                if bar % 2 == 1:
                    note += 12
                amp = 0.11 if (has_drums and t >= drop) else 0.07
                buf.add(t, _pluck(_m2hz(note), tau=0.13, bright=True) * amp, -0.2 if ei % 2 == 0 else 0.2)
                if has_drums and t >= drop:
                    buf.add(t + beat / 2, _pluck(_m2hz(note), tau=0.13, bright=True) * amp * 0.35, 0.3)
            if inbar == 0:
                buf.add(t, _pad([_m2hz(c - 12) for c in chord], beat * 4) * 0.035)
            k += 1
        if has_drums:
            buf.add(tl["demo_start"], _riser() * 0.12)

    # ---- SFX ----
    if config.get("sfx", True):
        buf.add(0.5, _pop(680, 0.16, 240) * 0.18)
        for c in config.get("captions", []):
            buf.add(c["start"], _pop(740 + np.random.uniform(-40, 60), 0.10, 200) * 0.13)
        for j in tl["joins"]:
            buf.add(j, _whoosh() * 0.13, 0.0)
        if tl["outro_dur"] > 0:
            buf.add(tl["outro_start"] + 0.25, _pop(540, 0.22, 180) * 0.20)
            if tl.get("endcard_at") is not None:
                buf.add(tl["endcard_at"], _pop(620, 0.18, 160) * 0.16)
                sp = _sparkle()
                buf.add(tl["endcard_at"] + 0.05, sp.L, -0.2)

    # ---- master: fades + soft clip ----
    gain = float(music.get("gain", 0.9))
    n = buf.n
    fi, fo = int(0.35 * SR), int(0.8 * SR)
    g = np.ones(n, np.float32)
    g[:fi] = np.linspace(0, 1, fi)
    g[n - fo:] = np.linspace(1, 0, fo)
    L = np.tanh(buf.L * g * gain * 1.3)
    R = np.tanh(buf.R * g * gain * 1.3)
    data = np.empty((n, 2), np.int16)
    data[:, 0] = np.clip(L, -1, 1) * 32767
    data[:, 1] = np.clip(R, -1, 1) * 32767
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return out_path
