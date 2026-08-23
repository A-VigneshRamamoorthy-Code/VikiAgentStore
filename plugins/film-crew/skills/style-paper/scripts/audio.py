"""Audio for the paper explainer: music bed, paper SFX, mixing, mastering.

Narration drives the edit, but this skill does not *make* narration — it is
supplied as an audio file per line and *measured* here, so visual beats are
laid out against real speech durations rather than guesses. That is the single
most important trick for making the sync feel tight.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np

SR = 48000
#: Where the limiter starts, in dB below the declared true-peak ceiling. Only a
#: starting point: `master` measures what the delivery codec actually produces
#: and widens this until the result is inside the target.
GUARD_DB = 3.0


# ------------------------------------------------------------------ buffer ----


class Track:
    def __init__(self, duration: float, channels: int = 1):
        self.n = int(duration * SR) + 1
        self.data = np.zeros((self.n, channels), dtype=np.float32)

    def add(self, sig: np.ndarray, at: float, gain: float = 1.0):
        i = int(at * SR)
        if i < 0:
            sig = sig[-i:]
            i = 0
        if sig.ndim == 1:
            sig = sig[:, None]
        if sig.shape[1] != self.data.shape[1]:
            sig = np.repeat(sig, self.data.shape[1], axis=1)
        j = min(self.n, i + len(sig))
        if j > i:
            self.data[i:j] += sig[: j - i] * gain
        return self

    def array(self):
        return self.data


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def _env(dur: float, attack: float = 0.004, release: float = 0.10, tau: float | None = None):
    t = _t(dur)
    e = np.ones_like(t)
    a = max(1, int(attack * SR))
    e[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    if tau is not None:
        e *= np.exp(-t / tau)
    r = max(1, int(release * SR))
    if r < len(e):
        e[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return e


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12.0)


# ------------------------------------------------------------- instruments ----


def celesta(freq: float, dur: float = 1.6, gain: float = 1.0) -> np.ndarray:
    """Music-box / celesta bell: a few inharmonic partials with fast decay."""
    t = _t(dur)
    partials = [(1.0, 1.0, 0.9), (2.01, 0.42, 0.55), (3.86, 0.22, 0.34),
                (5.4, 0.10, 0.22), (8.2, 0.05, 0.15)]
    out = np.zeros_like(t)
    for mult, amp, tau_s in partials:
        out += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t / (tau_s * dur * 0.55))
    strike = np.random.default_rng(int(freq)).normal(0, 1, len(t)).astype(np.float32)
    strike *= np.exp(-t / 0.004) * 0.05
    out = out + strike
    return (out * _env(dur, 0.002, 0.12) * 0.22 * gain).astype(np.float32)


def warm_pad(freqs, dur: float, gain: float = 1.0, detune: float = 0.004,
             seed: int = 0) -> np.ndarray:
    """Soft sustained bed — the 'air' under everything.

    Partial phases are drawn from a *seeded* generator: the global RNG would
    make every render of the same storyboard a different file, which breaks the
    byte-for-byte reproducibility the rest of the skill depends on.
    """
    t = _t(dur)
    rng = np.random.default_rng(seed)
    out = np.zeros_like(t)
    for f in freqs:
        for k, d in ((1.0, 0.0), (1.0, detune), (1.0, -detune), (2.0, 0.0)):
            amp = 0.5 if k == 1.0 else 0.14
            out += amp * np.sin(2 * np.pi * f * k * (1 + d) * t + rng.random() * 6.28)
    out /= max(1, len(freqs) * 2)
    lfo = 1 + 0.08 * np.sin(2 * np.pi * 0.13 * t)
    return (out * lfo * _env(dur, 1.2, 1.6) * 0.30 * gain).astype(np.float32)


def low_drone(freq: float, dur: float, gain: float = 1.0) -> np.ndarray:
    """The documentary-tension floor: a slow, barely-moving low tone."""
    t = _t(dur)
    out = (np.sin(2 * np.pi * freq * t)
           + 0.5 * np.sin(2 * np.pi * freq * 2 * t + 0.6)
           + 0.2 * np.sin(2 * np.pi * freq * 3 * t + 1.2))
    out *= 1 + 0.05 * np.sin(2 * np.pi * 0.08 * t)
    return (out * _env(dur, 1.5, 2.0) * 0.16 * gain).astype(np.float32)


def bowed(freq: float, dur: float = 2.6, gain: float = 1.0, seed: int = 0) -> np.ndarray:
    """A bowed, string-like sustain: slow swell, slight vibrato, no bell attack.

    The elegiac counterpart to `celesta`. A struck bell says 'once upon a time';
    a bowed note says 'this happened'. Use it whenever the subject is grave.
    """
    t = _t(dur)
    rng = np.random.default_rng(seed)
    vib = 1 + 0.0035 * np.sin(2 * np.pi * 4.6 * t + rng.random() * 6.28)
    out = np.zeros_like(t)
    for k, amp in ((1.0, 1.0), (2.0, 0.34), (3.0, 0.17), (4.0, 0.08), (5.0, 0.04)):
        out += amp * np.sin(2 * np.pi * freq * k * t * vib + rng.random() * 6.28)
    # bow noise, band-limited around the fundamental
    hair = _biquad_bp(rng.normal(0, 1, len(t)).astype(np.float32), freq * 2.2, q=0.7)
    out = out / 1.6 + hair * 0.05
    out = _lp(out, 2600)
    swell = np.clip(t / max(0.35, dur * 0.32), 0, 1) ** 1.4
    return (out * swell * _env(dur, 0.30, dur * 0.42) * 0.20 * gain).astype(np.float32)


def toll(freq: float = 58.0, dur: float = 4.5, gain: float = 1.0) -> np.ndarray:
    """A deep, slow bell toll — the memorial pulse. Use extremely sparingly:
    one every few bars reads as remembrance, four to the bar reads as a horror
    trailer."""
    t = _t(dur)
    out = np.zeros_like(t)
    for mult, amp, tau_s in ((1.0, 1.0, 0.85), (2.0, 0.30, 0.45),
                             (2.76, 0.16, 0.30), (4.2, 0.07, 0.18)):
        out += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t / (tau_s * dur * 0.5))
    out = _lp(out, 1400)
    return (out * _env(dur, 0.012, dur * 0.35) * 0.24 * gain).astype(np.float32)


def pulse_bass(freq: float, dur: float = 0.30, gain: float = 1.0) -> np.ndarray:
    """A short, punchy, filtered bass note — the driving eighth-note ostinato of
    an investigative bed. Fast attack, hard decay, no ring: it must read as a
    *pulse*, not a held bass note, or the bed turns into a drone."""
    t = _t(dur)
    # narrow saw stack, low-passed hard: body without fizz
    out = np.zeros_like(t)
    for k, amp in ((1, 1.0), (2, 0.42), (3, 0.20), (4, 0.10), (5, 0.05)):
        out += amp * np.sin(2 * np.pi * freq * k * t)
    out += 0.55 * np.sign(np.sin(2 * np.pi * freq * t)) * np.exp(-t / (dur * 0.10))
    out = _lp(out, max(180.0, freq * 7))
    body = np.exp(-t / (dur * 0.26))
    click = np.exp(-t / 0.004) * 0.30          # attack transient
    return ((out * body + click) * _env(dur, 0.002, dur * 0.22) * 0.26 * gain).astype(np.float32)


def pluck(freq: float, dur: float = 0.55, gain: float = 1.0, seed: int = 0) -> np.ndarray:
    """A muted, staccato plucked string (Karplus–Strong). Dry and clipped — the
    unease motif of a procedural bed. Unlike `celesta` it has no shimmer, so it
    never sounds like a storybook."""
    n = int(dur * SR)
    ln = max(2, int(SR / max(20.0, freq)))
    rng = np.random.default_rng(seed)
    buf = rng.uniform(-1, 1, ln).astype(np.float32)
    buf -= buf.mean()
    out = np.empty(n, dtype=np.float32)
    damp = 0.494                                # <0.5 = fast decay, muted
    for i in range(n):
        out[i] = buf[i % ln]
        buf[i % ln] = damp * (buf[i % ln] + buf[(i + 1) % ln])
    out = _lp(_lp(out, 1600), 1600)             # dark and muted: stays clear of
                                                # the 1-4 kHz narration band
    return (out * _env(dur, 0.001, dur * 0.30) * 0.30 * gain).astype(np.float32)


def tick(dur: float = 0.045, gain: float = 1.0, seed: int = 0) -> np.ndarray:
    """A dry, short rim/clock click — the layer that keeps an investigation
    feeling like it is counting something.

    It sits deliberately *above* 4 kHz. A click in the 1-4 kHz band lands right
    on top of the narration and eats intelligibility; the reference keeps its
    high percussion out of the voice's way, and so must this.
    """
    t = _t(dur)
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _biquad_bp(n, 5400 + rng.random() * 1200, q=1.4)
    n = _hp(n, 3800)
    return (n * np.exp(-t / 0.0090) * 0.30 * gain).astype(np.float32)


def shaker(dur: float = 0.10, gain: float = 1.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _hp(n, 4200)
    return (n * np.exp(-t / 0.020) * 0.18 * gain).astype(np.float32)


# ---------------------------------------------------------------- paper SFX ----


def _hp(x: np.ndarray, fc: float) -> np.ndarray:
    """One-pole high-pass."""
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    prev_x = prev_y = 0.0
    for i in range(len(x)):
        prev_y = a * (prev_y + x[i] - prev_x)
        prev_x = x[i]
        y[i] = prev_y
    return y


def _lp(x: np.ndarray, fc: float) -> np.ndarray:
    a = 1 - math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev += a * (x[i] - prev)
        y[i] = prev
    return y


def _biquad_bp(x, f0, q=1.0):
    """Vectorised-ish band-pass (RBJ), used to colour noise into 'paper'."""
    w0 = 2 * math.pi * f0 / SR
    alpha = math.sin(w0) / (2 * q)
    b0, b1, b2 = alpha, 0.0, -alpha
    a0, a1, a2 = 1 + alpha, -2 * math.cos(w0), 1 - alpha
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        v = b[0] * x[i] + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        x2, x1 = x1, x[i]
        y2, y1 = y1, v
        y[i] = v
    return y


def sfx_paper(dur: float = 0.30, seed: int = 0, gain: float = 1.0) -> np.ndarray:
    """Paper handling: a crisp, dry rustle. Use when a scrap lands."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _hp(n, 1800)
    # crackle: random micro-bursts
    env = np.exp(-t / (dur * 0.28))
    burst = (rng.random(len(t)) < 0.010).astype(np.float32)
    burst = _lp(burst, 900) * 6.0
    return ((n * (0.5 + burst)) * env * 0.30 * gain).astype(np.float32)


def sfx_stamp(dur: float = 0.34, seed: int = 1, gain: float = 1.0) -> np.ndarray:
    """A rubber stamp: wood knock + paper slap."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    body = np.sin(2 * np.pi * 128 * t) * np.exp(-t / 0.035)
    body += np.sin(2 * np.pi * 74 * t) * np.exp(-t / 0.055) * 0.8
    click = _hp(rng.normal(0, 1, len(t)).astype(np.float32), 2600) * np.exp(-t / 0.010)
    return ((body * 0.55 + click * 0.45) * 0.55 * gain).astype(np.float32)


def sfx_pin(dur: float = 0.16, seed: int = 2, gain: float = 1.0) -> np.ndarray:
    """A pin pushed into cork: short, high, woody."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    click = _hp(rng.normal(0, 1, len(t)).astype(np.float32), 3800) * np.exp(-t / 0.006)
    tone = np.sin(2 * np.pi * 320 * t) * np.exp(-t / 0.018) * 0.5
    return ((click + tone) * 0.42 * gain).astype(np.float32)


def sfx_draw(dur: float = 0.55, seed: int = 3, gain: float = 1.0) -> np.ndarray:
    """Marker on paper: sustained, mid-band scratch that fades with the stroke."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _biquad_bp(n, 2100, q=0.8)
    wobble = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 11 * t))
    env = np.minimum(1.0, t / 0.05) * np.exp(-t / (dur * 0.9))
    return (n * wobble * env * 0.28 * gain).astype(np.float32)


def sfx_whoosh(dur: float = 0.42, seed: int = 4, gain: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _lp(n, 1400)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.6
    return (n * env * 0.26 * gain).astype(np.float32)


def sfx_chime(freq: float = 880.0, dur: float = 1.8, gain: float = 1.0) -> np.ndarray:
    """A soft resolving bell for the final beat."""
    return celesta(freq, dur, gain * 1.3)


SFX = {
    "paper": sfx_paper,
    "stamp": sfx_stamp,
    "pin": sfx_pin,
    "draw": sfx_draw,
    "whoosh": sfx_whoosh,
    "chime": sfx_chime,
}


# ------------------------------------------------------------- story SFX ----
#
# Everything above this line is *paper foley* — the sound of the collage being
# assembled. It is the sound of the medium, and for a long time it was the
# only sound this style could make, so a film about a blizzard and a film
# about a courtroom were both scored to rubber stamps.
#
# What follows is the sound of the world the story happens in. All of it is
# synthesised from noise and enveloped tone for the same reason the artwork is
# procedural: the style ships no assets and needs no licence.


def sfx_wind(dur: float = 3.0, seed: int = 10, gain: float = 1.0) -> np.ndarray:
    """Wind: band-passed noise whose centre and level drift in slow gusts.

    A steady hiss reads as tape noise, not weather. What makes noise sound
    like wind is that it *breathes* — so both the filter centre and the
    amplitude are modulated by slow, irregular envelopes.
    """
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    n = _lp(_hp(n, 260), 2200)
    # two incommensurate slow LFOs so the gusting never audibly repeats
    gust = (0.55
            + 0.30 * np.sin(2 * np.pi * 0.13 * t + rng.uniform(0, 6))
            + 0.20 * np.sin(2 * np.pi * 0.31 * t + rng.uniform(0, 6)))
    gust = np.clip(gust, 0.05, 1.2)
    whistle = _biquad_bp(n, 900, q=3.5) * 0.25 * gust
    env = np.minimum(1.0, t / 0.6) * np.minimum(1.0, (dur - t) / 0.6)
    return ((n * gust + whistle) * env * 0.20 * gain).astype(np.float32)


def sfx_waves(dur: float = 4.0, seed: int = 11, gain: float = 1.0) -> np.ndarray:
    """Surf: a low swell that breaks into hiss and drags back out."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    period = 3.4
    phase = (t % period) / period
    # each wave: slow rise, sharp break at 0.45, long decay
    swell = np.where(phase < 0.45,
                     (phase / 0.45) ** 2.2,
                     np.exp(-(phase - 0.45) / 0.22))
    body = _lp(n, 700) * swell
    spray = _hp(n, 1900) * np.clip(swell - 0.62, 0, 1) * 1.1
    # Surf is a low collapse you feel first and a hiss you hear second. The
    # first build had the spray 1.8x and the body unweighted, which put 78%
    # of the energy above 4 kHz and made the sea sound like a cymbal.
    rumble = _lp(n, 180) * swell * 3.2
    env = np.minimum(1.0, t / 0.5) * np.minimum(1.0, (dur - t) / 0.8)
    return (((rumble + body * 2.2 + spray) * env) * 0.12 * gain).astype(np.float32)


def sfx_fire(dur: float = 3.0, seed: int = 12, gain: float = 1.0) -> np.ndarray:
    """Fire: a low roar under sparse, sharp crackles.

    The crackles are what identify it. They are Poisson-distributed rather
    than periodic, because a fire that pops in time sounds like a drum
    machine.
    """
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    roar = _lp(n, 420) * 0.9
    pops = (rng.random(len(t)) < 0.0016).astype(np.float32)
    idx = np.nonzero(pops)[0]
    crack = np.zeros(len(t), dtype=np.float32)
    for j in idx:
        ln = int(SR * rng.uniform(0.004, 0.020))
        seg = rng.normal(0, 1, min(ln, len(t) - j)).astype(np.float32)
        seg *= np.exp(-np.arange(len(seg)) / (ln * 0.30 + 1))
        crack[j:j + len(seg)] += seg * rng.uniform(0.4, 1.0)
    crack = _hp(crack, 900)
    env = np.minimum(1.0, t / 0.4) * np.minimum(1.0, (dur - t) / 0.5)
    # Weighted towards the roar. A fire is mostly a low, breathing rush with
    # occasional pops on top; leading with the pops gave 86% of the energy
    # above 4 kHz, which reads as frying, not as a hearth.
    return (((roar * 3.4 + crack * 0.7) * env) * 0.16 * gain).astype(np.float32)


def sfx_steps(dur: float = 2.4, seed: int = 13, gain: float = 1.0,
              pace: float = 0.62, surface: str = "stone") -> np.ndarray:
    """Footsteps: paired thuds with a slight limp in the timing.

    Human walking is not a metronome — the two feet are never quite equal —
    so alternate steps are nudged and their level varied. Perfectly even
    footsteps read as a machine.

    `surface` matters more than anything else here, and it is the one thing a
    sample library cannot give you cheaply: snow does not ring, gravel is all
    scatter and no body, wood is a hollow box. A single generic footstep used
    for every film is the audio equivalent of drawing every location as the
    same beige rectangle.
    """
    rng = np.random.default_rng(seed)
    out = np.zeros(int(dur * SR) + 1, dtype=np.float32)
    # (body Hz, body decay, grit HP Hz, grit decay, body/grit balance)
    SURFACE = {
        "stone":  (92.0, 0.020, 2200.0, 0.012, 0.60),
        # Snow has almost no resonant body — it is a squeaky compression of
        # packed crystals, so the "thud" is short and the noise is the sound.
        "snow":   (68.0, 0.009, 1500.0, 0.055, 0.22),
        "gravel": (78.0, 0.011, 1900.0, 0.070, 0.28),
        "wood":   (120.0, 0.045, 2600.0, 0.010, 0.75),
        "grass":  (70.0, 0.014, 1200.0, 0.038, 0.35),
        "metal":  (210.0, 0.090, 3400.0, 0.016, 0.70),
    }
    f_body, d_body, f_grit, d_grit, bal = SURFACE.get(surface, SURFACE["stone"])
    tt, k = 0.0, 0
    while tt < dur - 0.15:
        ln = int(max(0.16, d_grit * 4 + 0.10) * SR)
        te = np.arange(ln) / SR
        body = (np.sin(2 * np.pi * f_body * te) * np.exp(-te / d_body)
                + np.sin(2 * np.pi * f_body * 0.63 * te)
                * np.exp(-te / (d_body * 1.7)) * 0.7)
        grit = _hp(rng.normal(0, 1, ln).astype(np.float32), f_grit) * np.exp(-te / d_grit)
        if surface == "snow":
            # the squeak: a narrow, wavering band that only packed snow makes
            sq = _biquad_bp(rng.normal(0, 1, ln).astype(np.float32),
                            rng.uniform(1700, 2600), q=6.0)
            grit = grit + sq * np.exp(-te / (d_grit * 0.8)) * 1.6
        step = (body * bal + grit * (1 - bal)) * rng.uniform(0.75, 1.05)
        j = int(tt * SR)
        m = min(ln, len(out) - j)
        out[j:j + m] += step[:m].astype(np.float32)
        tt += pace * (1.0 + (0.06 if k % 2 else -0.04)) * rng.uniform(0.96, 1.04)
        k += 1
    peak = float(np.abs(out).max())
    if peak > 0:
        out *= min(1.0, 0.42 / peak)
    return (out * gain).astype(np.float32)


def sfx_rain(dur: float = 3.0, seed: int = 14, gain: float = 1.0) -> np.ndarray:
    """Rain: dense high noise plus individual drops."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    hiss = _hp(n, 1800) * 0.8
    drops = (rng.random(len(t)) < 0.004).astype(np.float32)
    drops = _biquad_bp(drops, 3200, q=2.0) * 3.0
    env = np.minimum(1.0, t / 0.4) * np.minimum(1.0, (dur - t) / 0.4)
    return (((hiss + drops) * env) * 0.18 * gain).astype(np.float32)


def sfx_thunder(dur: float = 3.2, seed: int = 15, gain: float = 1.0) -> np.ndarray:
    """Thunder: a low rumble with a rough leading edge and a long tail."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    low = _lp(n, 160)
    crackedge = _lp(n, 900) * np.exp(-t / 0.09)
    env = np.exp(-t / (dur * 0.32)) * (1.0 - np.exp(-t / 0.015))
    # a second, later roll — thunder almost never arrives as one event
    roll = np.roll(low * np.exp(-t / (dur * 0.5)), int(0.7 * SR)) * 0.5
    return (((low * env + crackedge * 0.6 + roll)) * 0.30 * gain).astype(np.float32)


def sfx_creak(dur: float = 1.1, seed: int = 16, gain: float = 1.0) -> np.ndarray:
    """A door on a dry hinge: stick-slip friction, rising in pitch."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    sweep = 220 + 340 * (t / dur) ** 1.6
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    # stick-slip: the tone is chopped by an irregular gate
    grind = (0.5 + 0.5 * np.sign(np.sin(phase * 0.5
                                        + 2.0 * np.sin(2 * np.pi * 7.3 * t))))
    tone = np.sin(phase) * grind
    n = _biquad_bp(rng.normal(0, 1, len(t)).astype(np.float32), 1400, q=1.4)
    env = np.minimum(1.0, t / 0.05) * np.exp(-t / (dur * 0.6))
    return (((tone * 0.6 + n * 0.4) * env) * 0.20 * gain).astype(np.float32)


def sfx_birds(dur: float = 2.6, seed: int = 17, gain: float = 1.0) -> np.ndarray:
    """Birdsong: short frequency-swept chirps at irregular intervals."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(dur * SR) + 1, dtype=np.float32)
    tt = rng.uniform(0.05, 0.3)
    while tt < dur - 0.25:
        ln = int(rng.uniform(0.05, 0.13) * SR)
        te = np.arange(ln) / SR
        f0 = rng.uniform(1900, 3400)
        f1 = f0 * rng.uniform(0.65, 1.6)
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, ln)) / SR
        chirp = np.sin(ph) * np.sin(np.pi * np.linspace(0, 1, ln)) ** 1.4
        chirp += np.sin(2 * ph) * 0.25 * np.sin(np.pi * np.linspace(0, 1, ln))
        j = int(tt * SR)
        m = min(ln, len(out) - j)
        out[j:j + m] += chirp[:m].astype(np.float32) * rng.uniform(0.5, 1.0)
        tt += rng.uniform(0.16, 0.55)
    return (out * 0.16 * gain).astype(np.float32)


def sfx_engine(dur: float = 3.0, seed: int = 18, gain: float = 1.0) -> np.ndarray:
    """A working engine: a harmonic stack on a firing rate, plus mechanism."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    f0 = 27.0
    x = np.zeros(len(t), dtype=np.float32)
    for h, amp in ((1, 1.0), (2, 0.55), (3, 0.33), (4, 0.20), (6, 0.12)):
        x += np.sin(2 * np.pi * f0 * h * t + rng.uniform(0, 6)) * amp
    # slight speed wander, or it sounds like a test tone
    x *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.23 * t)
    mech = _biquad_bp(rng.normal(0, 1, len(t)).astype(np.float32), 1800, q=1.2)
    mech *= 0.4 + 0.6 * (np.sin(2 * np.pi * f0 * t) > 0.6)
    env = np.minimum(1.0, t / 0.5) * np.minimum(1.0, (dur - t) / 0.5)
    return (((x * 0.22 + mech * 0.25) * env) * 0.30 * gain).astype(np.float32)


def sfx_crowd(dur: float = 3.5, seed: int = 19, gain: float = 1.0) -> np.ndarray:
    """A room of people: formant-shaped noise, many voices, none legible."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    out = np.zeros(len(t), dtype=np.float32)
    # vowel formants — this is what separates babble from plain noise
    for f0, q, a in ((520, 3.0, 1.0), (1180, 3.5, 0.7), (2500, 4.0, 0.35)):
        out += _biquad_bp(n, f0 * rng.uniform(0.92, 1.08), q=q) * a
    # syllabic rhythm, around 4 Hz, which is roughly speech rate
    syl = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * 3.8 * t
                                      + 1.5 * np.sin(2 * np.pi * 0.7 * t)))
    env = np.minimum(1.0, t / 0.6) * np.minimum(1.0, (dur - t) / 0.6)
    return ((out * syl * env) * 0.16 * gain).astype(np.float32)


def sfx_clock(dur: float = 3.0, seed: int = 20, gain: float = 1.0) -> np.ndarray:
    """A clock: alternating tick and tock, one second apart."""
    out = np.zeros(int(dur * SR) + 1, dtype=np.float32)
    tt, k = 0.0, 0
    while tt < dur - 0.1:
        one = tick(dur=0.05, gain=1.0 if k % 2 == 0 else 0.78, seed=k)
        j = int(tt * SR)
        m = min(len(one), len(out) - j)
        out[j:j + m] += one[:m]
        tt += 1.0
        k += 1
    return (out * 0.55 * gain).astype(np.float32)


def sfx_heart(dur: float = 3.0, seed: int = 21, gain: float = 1.0,
              bpm: float = 68.0) -> np.ndarray:
    """A heartbeat: the lub-dub pair, felt more than heard."""
    out = np.zeros(int(dur * SR) + 1, dtype=np.float32)
    period = 60.0 / bpm
    tt = 0.0
    while tt < dur - 0.2:
        for off, amp in ((0.0, 1.0), (0.16, 0.62)):
            ln = int(0.19 * SR)
            te = np.arange(ln) / SR
            thud = (np.sin(2 * np.pi * 46 * te) * np.exp(-te / 0.045)
                    + np.sin(2 * np.pi * 30 * te) * np.exp(-te / 0.070) * 0.8)
            j = int((tt + off) * SR)
            m = min(ln, len(out) - j)
            if m > 0:
                out[j:j + m] += thud[:m].astype(np.float32) * amp
        tt += period
    return (out * 0.40 * gain).astype(np.float32)


def sfx_water(dur: float = 3.0, seed: int = 22, gain: float = 1.0) -> np.ndarray:
    """Running water: hiss plus the resonant bloops of trapped bubbles."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    flow = _biquad_bp(n, 1600, q=0.7) * 0.8
    out = np.zeros(len(t), dtype=np.float32)
    for _ in range(int(dur * 9)):
        j = int(rng.uniform(0, dur - 0.1) * SR)
        ln = int(rng.uniform(0.03, 0.09) * SR)
        te = np.arange(ln) / SR
        # a bubble's pitch rises as it collapses — that rise is the "bloop"
        f0 = rng.uniform(500, 1500)
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f0 * 1.9, ln)) / SR
        b = np.sin(ph) * np.exp(-te / (ln / SR * 0.4)) * rng.uniform(0.3, 0.9)
        m = min(ln, len(out) - j)
        out[j:j + m] += b[:m].astype(np.float32)
    env = np.minimum(1.0, t / 0.3) * np.minimum(1.0, (dur - t) / 0.3)
    return (((flow + out * 0.5) * env) * 0.18 * gain).astype(np.float32)


def sfx_bell(dur: float = 3.5, seed: int = 23, gain: float = 1.0,
             freq: float = 220.0) -> np.ndarray:
    """A struck bell, low and slow. Ceremony, an hour, a warning."""
    return toll(freq, dur, gain)


def sfx_crack(dur: float = 1.4, seed: int = 24, gain: float = 1.0) -> np.ndarray:
    """A hard report — a shot, a snapping branch — and its room tail."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = rng.normal(0, 1, len(t)).astype(np.float32)
    hit = _hp(n, 1200) * np.exp(-t / 0.006)
    body = _lp(n, 300) * np.exp(-t / 0.045)
    tail = _lp(n, 1800) * np.exp(-t / (dur * 0.30)) * 0.22
    return (((hit * 1.2 + body * 0.9 + tail)) * 0.34 * gain).astype(np.float32)


SFX.update({
    "wind": sfx_wind,
    "waves": sfx_waves,
    "fire": sfx_fire,
    "steps": sfx_steps,
    "rain": sfx_rain,
    "thunder": sfx_thunder,
    "creak": sfx_creak,
    "birds": sfx_birds,
    "engine": sfx_engine,
    "crowd": sfx_crowd,
    "clock": sfx_clock,
    "heart": sfx_heart,
    "water": sfx_water,
    "bell": sfx_bell,
    "crack": sfx_crack,
})

#: Sounds that work as a continuous bed under a whole act rather than as a
#: one-shot punctuation. The mixer loops these and holds them low.
AMBIENT = ("wind", "waves", "rain", "crowd", "engine", "fire", "water")


# ------------------------------------------------------------------- files ----


def write_wav(path: str, data: np.ndarray, sr: int = SR):
    if data.ndim == 1:
        data = data[:, None]
    d = np.clip(data, -1.0, 1.0)
    pcm = (d * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav(path: str):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def _ffmpeg():
    return shutil.which("ffmpeg") or "ffmpeg"


def to_wav(src: str, dst: str, sr: int = SR):
    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(sr), dst],
        check=True,
    )


# --------------------------------------------------------------- narration ----


def load_audio(path: str) -> np.ndarray:
    """Load any file ffmpeg can read as mono float32 at the project rate."""
    if path.lower().endswith(".wav"):
        a, sr = read_wav(path)
    else:
        tmp = tempfile.mktemp(suffix=".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                        "-ac", "1", "-ar", str(SR), tmp], check=True)
        a, sr = read_wav(tmp)
        os.unlink(tmp)
    if sr != SR:
        n = int(round(len(a) * SR / sr))
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


def load_narration(path: str) -> np.ndarray:
    """Load a supplied narration clip and normalise it to the project rate.

    This skill does not synthesise speech. Narration audio is an *input*,
    produced by the `voice-booth` skill (or any other source) and referenced from
    the storyboard. Any format ffmpeg can read is accepted.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"narration audio not found: {path}\n"
            "    Generate it with the `voice-booth` skill, then point the "
            "storyboard line's `audio` field at it."
        )
    return load_audio(path)


def loop_to(x: np.ndarray, n: int, crossfade: float = 2.0) -> np.ndarray:
    """Repeat a clip to exactly n samples, crossfading each seam.

    A supplied bed is almost always shorter than the film. Butt-joining it
    leaves an audible click and an obvious restart every loop; an equal-power
    crossfade over the seam hides both.
    """
    if len(x) == 0:
        return np.zeros(n, dtype=np.float32)
    if len(x) >= n:
        return x[:n].astype(np.float32)
    xf = min(int(crossfade * SR), len(x) // 3)
    if xf < 1:
        reps = int(np.ceil(n / len(x)))
        return np.tile(x, reps)[:n].astype(np.float32)
    fi = np.sqrt(np.linspace(0, 1, xf, dtype=np.float32))
    fo = np.sqrt(np.linspace(1, 0, xf, dtype=np.float32))
    win = x.astype(np.float32).copy()
    win[:xf] *= fi
    win[-xf:] *= fo
    period = len(x) - xf                 # each copy overlaps the last by xf
    out = np.zeros(n + len(x), dtype=np.float32)
    first = True
    pos = 0
    while pos < n:
        c = x.astype(np.float32).copy() if first else win
        if first:
            c[-xf:] *= fo               # the opening copy starts at full level
            first = False
        out[pos:pos + len(c)] += c
        pos += period
    return out[:n]


def trim_silence(x: np.ndarray, thresh_db: float = -42.0, pad: float = 0.02) -> np.ndarray:
    """Tighten leading/trailing silence so line gaps are exactly what we set."""
    if len(x) == 0:
        return x
    thr = 10 ** (thresh_db / 20.0)
    win = max(1, int(0.005 * SR))
    env = np.convolve(np.abs(x), np.ones(win) / win, mode="same")
    idx = np.where(env > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * SR))
    b = min(len(x), idx[-1] + int(pad * SR))
    return x[a:b]


# ------------------------------------------------------------------- mixing ----


def envelope_follow(x: np.ndarray, attack_ms: float = 8, release_ms: float = 260) -> np.ndarray:
    """Level follower used to duck music under narration.

    The recursion runs on a 1 kHz decimation of the rectified signal and is then
    interpolated back up — identical result for ducking purposes, ~50x faster
    than iterating every sample.
    """
    if len(x) == 0:
        return x
    ds = max(1, SR // 1000)
    n_ds = len(x) // ds
    if n_ds < 2:
        return np.abs(x)
    trimmed = np.abs(x[: n_ds * ds]).reshape(n_ds, ds).max(axis=1)
    sr_ds = SR / ds
    a_at = math.exp(-1.0 / (sr_ds * attack_ms / 1000.0))
    a_rl = math.exp(-1.0 / (sr_ds * release_ms / 1000.0))
    out = np.empty(n_ds, dtype=np.float32)
    prev = 0.0
    for i in range(n_ds):
        c = trimmed[i]
        prev = (a_at * prev + (1 - a_at) * c) if c > prev else (a_rl * prev + (1 - a_rl) * c)
        out[i] = prev
    return np.interp(np.arange(len(x)), np.arange(n_ds) * ds, out).astype(np.float32)


def duck(music: np.ndarray, voice: np.ndarray, depth_db: float = -11.0, thresh: float = 0.012):
    """Sidechain the bed under the voice."""
    n = max(len(music), len(voice))
    m = np.pad(music, (0, n - len(music)))
    v = np.pad(voice, (0, n - len(voice)))
    env = envelope_follow(v)
    drive = np.clip((env - thresh) / 0.10, 0, 1)
    gain = 10 ** ((depth_db * drive) / 20.0)
    return m * gain


def soft_clip(x: np.ndarray, ceiling: float = 0.94) -> np.ndarray:
    return np.tanh(x / ceiling) * ceiling


def master(path_in: str, path_out: str, lufs: float = -14.0, tp: float = -1.0,
           bitrate: str = "192k", tries: int = 3):
    """Two-pass EBU R128 normalisation via ffmpeg's loudnorm.

    Returns what was actually delivered, so the caller can record it rather
    than assume it.
    """
    ff = _ffmpeg()
    measure = subprocess.run(
        [ff, "-hide_banner", "-i", path_in, "-af",
         f"loudnorm=I={lufs}:TP={tp}:LRA=9:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    import json as _json
    stats = None
    txt = measure.stderr
    if "{" in txt:
        try:
            stats = _json.loads(txt[txt.rindex("{"): txt.rindex("}") + 1])
        except Exception:
            stats = None
    if stats:
        af = (f"loudnorm=I={lufs}:TP={tp}:LRA=9:"
              f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
              f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
              f"offset={stats['target_offset']}:linear=true")
    else:
        af = f"loudnorm=I={lufs}:TP={tp}:LRA=9"
    # loudnorm's linear mode applies a flat gain and can overshoot the ceiling,
    # so back it up with a real true-peak limiter. The guard band underneath
    # `tp` is not slack: a lossy encoder reconstructs samples above the peak it
    # was handed, so the PCM has to sit low enough that the AAC downstream
    # still lands under the ceiling.
    #
    # The band has to cover three separate things. Measured end to end on a
    # 13-minute documentary master: `alimiter` is not a true-peak brick wall
    # and settles a little above the ceiling it is given; AAC then adds ~1.7 dB
    # decoding back to PCM; and true-peak metering finds a further ~0.4 dB
    # between samples. A 2.0 dB band shipped that film at -0.5 dBTP against a
    # -1.0 target, and the downstream mix check correctly flagged it.
    #
    # The AAC term is programme-dependent, so *any* fixed band is a band that
    # will eventually be exceeded -- a wider constant only moves the film that
    # breaks it. So the constant is a starting point and nothing more: encode
    # to the codec that will actually deliver this, measure the true peak that
    # comes back, and widen until it is inside the target. That turns the guard
    # from a promise into a measurement.
    guard, used, delivered = GUARD_DB, GUARD_DB, None
    for _ in range(max(1, int(tries))):
        used = guard
        ceiling = 10.0 ** ((tp - used) / 20.0)
        subprocess.run(
            [ff, "-y", "-loglevel", "error", "-i", path_in, "-af",
             af + f",alimiter=level_in=1:level_out=1:limit={ceiling:.4f}:level=disabled",
             "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", path_out],
            check=True,
        )
        delivered = _delivered_peak(path_out, bitrate)
        if delivered is None or delivered <= tp:
            break
        # Widen by the shortfall, plus a little so a second pass is not spent
        # landing exactly on the line. `used` is what produced the file that is
        # actually on disk -- reporting the *next* guard would describe a take
        # that was never written.
        guard = used + (delivered - tp) + 0.3
    return {"target_true_peak": tp, "true_peak": delivered,
            "guard_db": round(used, 2),
            "within_target": delivered is not None and delivered <= tp}


def _delivered_peak(path: str, bitrate: str):
    """True peak of `path` once the codec that will deliver it has had it.

    Metering the PCM answers the wrong question: it is the AAC the viewer
    decodes, and a lossy encoder reconstructs samples above the peak it was
    handed. Returns None if the probe cannot be made, so a missing measurement
    never silently reads as a pass.
    """
    probe = path + ".probe.m4a"
    try:
        subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-i", path,
             "-c:a", "aac", "-b:a", str(bitrate), "-ar", str(SR), probe],
            check=True,
        )
        return measure_lufs(probe)[1]
    except Exception:
        return None
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


def measure_lufs(path: str):
    """Return (integrated LUFS, true peak dBFS) for a rendered file."""
    r = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    out = r.stderr
    i = tp = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("I:") and "LUFS" in s:
            i = float(s.split()[1])
        if s.startswith("Peak:") and "dBFS" in s:
            tp = float(s.split()[1])
    return i, tp
