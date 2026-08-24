"""Audio for the 2D character-animation style: chase score, cartoon SFX, radio voice.

Almost none of the hard part is here. The synthesis primitives, the sound
library, the narration loader, the ducking, the limiter and the delivery
mastering all belong to `style-paper/scripts/audio.py`, which has been fitted
against real films and measured end to end. This module *borrows* that engine
and adds the three things a comedy chase needs and a documentary does not:

1. **Chase sound effects.** Sirens, rotors, tyres, horns and the cartoon
   accent kit — `boing`, `pop`, `thud`. Comic accents are not decoration in
   this genre, they are how the gag lands.
2. **A radio voice filter.** `filter: "radio"` on a narration line band-limits
   it to roughly 300 Hz - 3.4 kHz, saturates and compresses it and puts a
   squelch either side, so a news-chopper reporter sounds like she is in the
   helicopter rather than in a booth. `tannoy` and `phone` are the same idea
   with different geometry.
3. **A chase bed.** Walking bass, off-beat stabs, brushes. The moods
   `style-paper` ships are documentary moods; the nearest, `crime`, is a
   *procedural* bed — sub drone, dry plucks, ticking clock. Under a cartoon
   pursuit it reads as a murder investigation. See `CHASE_MOODS`.

Plus one mix decision that is specific to comedy: **a comic accent ducks the
music, rather than the music burying the accent.** See `build`.

---

## Loading the sibling engine — read this before editing

This file is called `audio.py`. So is the engine's. A script's own directory
is prepended to `sys.path`, so a plain ``import audio`` from here resolves to
*this file* — and it does so silently: you get a module, it has the right
name, and every attribute you wanted is missing or, worse, subtly yours. The
same trap is documented in `style-flat/SKILL.md` for `render.py`, where it
cost a full render in the wrong style before anyone noticed.

So the engine is loaded by explicit path (`_sibling`), under a name that
cannot collide, and `_verify_sibling` asserts at import time that what came
back is the engine and not us.

For the same reason this module does **not** import `style-paper/render.py`,
which is where that style's cue renderer lives. `render.py` does
``import audio as A`` by name — loading it from here would resolve that to
*this* file and hand the paper renderer a module with no `Track` in it. The
cue renderer below is therefore written locally, but every instrument it
plays (`low_drone`, `warm_pad`, `pluck`, `celesta`, `bowed`, `pulse_bass`,
`shaker`, `tick`) is the engine's.

## Public API

    build(board, base_dir, total_dur, *, seed=0)   -> mono float32 mix
    master_to(wav_path, out_path, **kw)            -> delivery report
    line_times(board, base_dir)                    -> {line_id: (start, end)}
    SFX                                            -> {name: gen(dur, seed, gain)}

and, for the renderer's convenience:

    film_duration(board, base_dir)   how long the film is, before any picture
    resolve_time(times, spec)        the "l3+0.4" / "l3.end" / 12.5 grammar
    mix_to(board, base_dir, dur, wav_path, seed=0)
    voice_filter(x, kind, seed=0)    the radio/tannoy/phone chain on its own
    render_cue(spec, dur)            one music cue
    MOODS, SCALES, AMBIENCE, ACCENTS, FILTERS

Everything is deterministic: every random choice comes from an explicit seed,
never from `random` and never from the clock.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import math
import os
import shutil
import subprocess
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
#: The shared engine, kept as a sibling rather than vendored so a fix to the
#: limiter or the loudness chain reaches every style at once.
ENGINE = os.path.normpath(os.path.join(HERE, "..", "..", "style-paper", "scripts"))


def _sibling(alias: str, filename: str):
    """Load a module from the paper engine by *path*, never by name.

    `alias` is deliberately not the module's own basename: registering the
    engine's `audio.py` in `sys.modules` as ``"audio"`` would make the trap in
    the header worse rather than better, because a later ``import audio``
    anywhere in the process would then get the engine instead of whichever
    style's module the caller meant.
    """
    cached = sys.modules.get(alias)
    if cached is not None and getattr(cached, "__file__", None):
        return cached
    path = os.path.join(ENGINE, filename)
    if not os.path.exists(path):
        raise ImportError(
            f"the shared audio engine is missing: {path}\n"
            "    This style borrows `style-paper/scripts/{audio,score}.py`. "
            "Both skills must be installed."
        )
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


P = _sibling("paper_audio", "audio.py")     # the engine
S = _sibling("paper_score", "score.py")     # the mood vocabulary


def _verify_sibling():
    """Prove we loaded the engine and not ourselves.

    This costs microseconds and catches the one failure in this file that is
    otherwise invisible: a self-import produces a module that looks fine until
    a film renders with no music, no effects and no explanation.
    """
    mine = os.path.abspath(__file__)
    theirs = os.path.abspath(getattr(P, "__file__", "") or "")
    if not theirs or theirs == mine:
        raise ImportError(
            "self-import: the sibling engine resolved to this very file "
            f"({mine}). It must be loaded by path from {ENGINE}."
        )
    if os.path.dirname(theirs) != ENGINE:
        raise ImportError(f"engine loaded from the wrong place: {theirs}")
    missing = [n for n in ("SR", "Track", "master", "duck", "trim_silence",
                           "loop_to", "measure_lufs", "write_wav", "read_wav",
                           "soft_clip", "envelope_follow", "SFX")
               if not hasattr(P, n)]
    if missing:
        raise ImportError("engine is missing %s — is it really style-paper's "
                          "audio.py?" % ", ".join(missing))
    if not hasattr(S, "MOODS"):
        raise ImportError("score module is missing MOODS")
    return True


_verify_sibling()

SR = P.SR

# Re-exported so a caller never has to reach into the engine itself, and so
# the sample rate, the file IO and the loudness meter are provably the same
# ones the paper style ships.
write_wav = P.write_wav
read_wav = P.read_wav
measure_lufs = P.measure_lufs
loop_to = P.loop_to
trim_silence = P.trim_silence
soft_clip = P.soft_clip
midi_hz = P.midi_hz
Track = P.Track

_t = P._t                      # arange(dur * SR) / SR


# ============================================================== fast filters ==
#
# The engine's `_hp`, `_lp` and `_biquad_bp` iterate in Python, one sample at
# a time. That is fine for the short buffers they were written for — a 0.3 s
# stamp is 14k samples — but a narration line is a quarter of a million, and
# the radio chain filters it four times. Measured: 1.3 s per line, per pass.
#
# So anything applied to *speech-length* audio here is done in the frequency
# domain instead: one rfft, a Butterworth magnitude, one irfft. It is
# zero-phase, which for a voice colouration is a feature rather than a
# compromise, and it is roughly two hundred times faster. The engine's
# per-sample filters are still used unchanged inside the effects that
# borrowed them.


def _bw(f: np.ndarray, fc: float, order: float, high: bool = False) -> np.ndarray:
    """Butterworth magnitude response, evaluated on a frequency axis."""
    fc = max(1e-6, float(fc))
    r = np.maximum(np.asarray(f, dtype=np.float64), 1e-6) / fc
    if high:
        r = 1.0 / r
    # The clip is purely numerical: r**(2*order) overflows float64 long before
    # the response means anything, and the answer out there is zero regardless.
    r = np.clip(r, 0.0, 1e4)
    return 1.0 / np.sqrt(1.0 + r ** (2.0 * float(order)))


def _shape(x: np.ndarray, resp) -> np.ndarray:
    """Apply a frequency-domain magnitude response to a signal.

    Zero-padded either side, because an rfft/irfft pair is a *circular*
    convolution: without the pad the tail of a line wraps onto its head, which
    on a voice sounds like a click before the first word.
    """
    x = np.asarray(x, dtype=np.float32)
    n = len(x)
    if n == 0:
        return x
    pad = min(4096, n)
    xp = np.concatenate([np.zeros(pad, np.float32), x, np.zeros(pad, np.float32)])
    m = len(xp)
    y = np.fft.irfft(np.fft.rfft(xp) * resp(np.fft.rfftfreq(m, 1.0 / SR)), m)
    return y[pad:pad + n].astype(np.float32)


def lowpass(x, fc, order=6):
    return _shape(x, lambda f: _bw(f, fc, order))


def highpass(x, fc, order=6):
    return _shape(x, lambda f: _bw(f, fc, order, high=True))


def bandpass(x, lo, hi, order=6):
    return _shape(x, lambda f: _bw(f, hi, order) * _bw(f, lo, order, high=True))


def _peaking(x, fc, q=1.4, gain_db=6.0):
    """A single resonant bump — the 'honk' that makes a small speaker."""
    g = 10.0 ** (float(gain_db) / 20.0) - 1.0

    def resp(f):
        f = np.maximum(np.asarray(f, dtype=np.float64), 1e-6)
        # a normalised resonance curve, 1.0 at fc, falling either side
        bw = fc / max(0.1, q)
        return 1.0 + g / (1.0 + ((f - fc) / bw) ** 2)

    return _shape(x, resp)


def _rms(x) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def _match_rms(y, x, ceiling: float = 0.99):
    """Return `y` at `x`'s level.

    A voice filter is a *colour*, not a level change. If `radio` also made a
    line 4 dB quieter the storyboard would have to compensate by hand, and the
    same board would mix differently depending on which lines were diegetic.
    """
    ry, rx = _rms(y), _rms(x)
    if ry <= 1e-9 or rx <= 1e-9:
        return np.asarray(y, dtype=np.float32)
    out = np.asarray(y, dtype=np.float32) * (rx / ry)
    peak = float(np.abs(out).max()) if len(out) else 0.0
    if peak > ceiling:
        out = out * (ceiling / peak)
    return out.astype(np.float32)


def _saturate(x, drive=2.5):
    """Soft asymmetric saturation — a small transmitter running a little hot."""
    d = max(0.05, float(drive))
    y = np.tanh(np.asarray(x, dtype=np.float32) * d) / math.tanh(d)
    return y.astype(np.float32)


def _compress(x, thresh_db=-24.0, ratio=5.0, attack_ms=4.0, release_ms=110.0,
              makeup_db=0.0):
    """Level compression, using the engine's own envelope follower.

    Radio is compressed to within an inch of its life — that is most of why it
    sounds like radio. It is also why it survives being ducked under a chase
    bed: a dense, flat-level voice keeps its intelligibility at a lower fader.
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) == 0:
        return x
    env = P.envelope_follow(x, attack_ms, release_ms)
    env_db = 20.0 * np.log10(np.maximum(env, 1e-6))
    over = np.maximum(0.0, env_db - float(thresh_db))
    gain_db = -over * (1.0 - 1.0 / max(1.0001, float(ratio))) + float(makeup_db)
    return (x * (10.0 ** (gain_db / 20.0))).astype(np.float32)


def _fade(x, secs=0.01):
    """Top and tail, so a mixed one-shot never clicks."""
    x = np.asarray(x, dtype=np.float32).copy()
    n = min(int(secs * SR), len(x) // 2)
    if n > 1:
        x[:n] *= np.linspace(0, 1, n, dtype=np.float32)
        x[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
    return x


def _phase(freq: np.ndarray) -> np.ndarray:
    """Instantaneous phase from an instantaneous-frequency curve.

    Every swept, doppler-shifted or wobbling sound in this file is built this
    way: decide what the frequency is doing over time, then integrate. Sweeping
    by `np.linspace` inside a `sin` gives the wrong pitch — that is a chirp
    whose *phase* is linear, not its frequency — and is why naive sirens sound
    like a theremin.
    """
    return (2.0 * np.pi * np.cumsum(np.asarray(freq, dtype=np.float64)) / SR)


# =========================================================== voice treatment ==
#
# `narration[].filter` in the storyboard. The default, `none`, is the booth
# read and is left alone.
#
# Every filter here must return **exactly as many samples as it was given**.
# `line_times` computes the whole film's timing from line lengths; if a filter
# prepended a squelch, sound would slide later than picture by a few hundred
# milliseconds per line and the film would drift apart by the end. Squelches
# are therefore mixed *into* the line's own span, over the room tone at its
# head and tail.


def _squelch(dur: float, seed: int, bright: float = 1.0) -> np.ndarray:
    """The burst of noise as a radio link opens or closes."""
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    noise = rng.standard_normal(n).astype(np.float32)
    env = np.exp(-np.linspace(0.0, 7.0, n, dtype=np.float32))
    x = bandpass(noise * env, 700.0 * bright, 3000.0 * bright, order=6)
    # the little carrier chirp underneath the hiss
    t = _t(dur)[:n]
    f = np.linspace(1900.0, 900.0, n)
    x = x + 0.35 * np.sin(_phase(f))[:n].astype(np.float32) * env
    return _fade(x * 0.5, 0.004)


def _radio(x, seed=0, *, lo=300.0, hi=3400.0, order=6, drive=3.2,
           hiss=0.006, squelch=True, room=0.0):
    """Band-limit, saturate, compress: the news-helicopter reporter.

    The second bandpass is not redundant. Saturation is a non-linearity, so it
    manufactures harmonics — a 2 kHz formant comes back with energy at 4, 6 and
    8 kHz, which is exactly the band the first filter just removed. Filtering
    only before the drive leaves the result measurably *wider* than the radio
    channel it is meant to be squeezed through.
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) == 0:
        return x
    rng = np.random.default_rng((int(seed) * 7919 + 17) & 0xFFFFFFFF)
    y = bandpass(x, lo, hi, order=order)
    y = _peaking(y, 1800.0, q=1.1, gain_db=5.0)       # presence, for intelligibility
    y = _saturate(y, drive)
    y = bandpass(y, lo, hi, order=order)              # re-limit after the drive
    y = _compress(y, thresh_db=-26.0, ratio=6.0, attack_ms=3.0, release_ms=90.0)

    if room > 0:
        # a short slap, for a voice coming out of a box in a room
        d = int(0.021 * SR)
        if d < len(y):
            y[d:] += y[:-d] * float(room)

    if hiss > 0:
        n = bandpass(rng.standard_normal(len(y)).astype(np.float32), lo, hi, order=6)
        y = y + n * float(hiss)

    if squelch:
        for pos, ln, br in ((0.0, 0.075, 1.0), (max(0.0, len(y) / SR - 0.10), 0.10, 0.85)):
            s = _squelch(ln, seed + int(pos * 1000) + 3, br)
            a = min(len(y), int(pos * SR))
            b = min(len(y), a + len(s))
            if b > a:
                y[a:b] += s[:b - a] * 0.45

    # One last pass through the channel, steeper, over *everything* — the
    # voice, the hiss and the squelch alike. A real link band-limits its own
    # noise; filtering only the voice and then adding wideband hiss and a
    # wideband squelch on top leaves a signal with more energy above 4 kHz
    # than the one that went in, which is the opposite of the effect wanted.
    y = bandpass(y, lo, hi, order=order + 2)
    return _match_rms(y, x)


def _tannoy(x, seed=0):
    """Station PA. Narrower, hornier, and thrown down a tiled corridor."""
    y = _radio(x, seed, lo=380.0, hi=2900.0, order=8, drive=4.5,
               hiss=0.004, squelch=False, room=0.34)
    y = _peaking(y, 1150.0, q=0.75, gain_db=7.5)      # the cardboard honk
    return _match_rms(y, x)


def _phone(x, seed=0):
    """Handset. Clean, tight, no room and no hiss — it is a codec, not a link."""
    y = bandpass(np.asarray(x, dtype=np.float32), 300.0, 3200.0, order=8)
    y = _saturate(y, 1.8)
    y = bandpass(y, 300.0, 3200.0, order=8)
    y = _compress(y, thresh_db=-22.0, ratio=4.0, attack_ms=6.0, release_ms=140.0)
    return _match_rms(y, x)


def _dry(x, seed=0):
    return np.asarray(x, dtype=np.float32)


#: `narration[].filter` -> treatment. Unknown names fall back to `none` with a
#: warning rather than an exception: one mistyped field should not cost a film.
FILTERS = {
    "none": _dry,
    "dry": _dry,
    "clean": _dry,
    "radio": _radio,
    "walkie": _radio,
    "comms": _radio,
    "tannoy": _tannoy,
    "pa": _tannoy,
    "megaphone": _tannoy,
    "phone": _phone,
    "telephone": _phone,
    "call": _phone,
}


def voice_filter(x, kind: str = "none", seed: int = 0):
    """Apply a named voice treatment. Length-preserving, level-preserving."""
    name = (kind or "none").strip().lower()
    fn = FILTERS.get(name)
    if fn is None:
        _warn(f"unknown voice filter {kind!r}; using none")
        fn = _dry
    return fn(x, seed)


# ================================================================== reporting ==
#
# A board that names an effect this module does not have is a *content* bug,
# not a crash: the film should still render so the director can see the rest.
# But it must not be silent either — a missing gag is very hard to spot in a
# finished mix. So it warns once, and accumulates into a report the renderer
# can print or fail on.

WARNINGS: list[str] = []


def _warn(msg: str):
    if msg not in WARNINGS:
        WARNINGS.append(msg)
        print(f"[audio] {msg}", file=sys.stderr)


def warnings() -> list[str]:
    """Everything this module could not do, since import."""
    return list(WARNINGS)


# ============================================================ sound effects ==
#
# The chase kit. `style-paper` already has whooshes, cracks, steps, wind,
# crowds, engines and weather; those are merged in wholesale at the bottom of
# this section. What follows is what a pursuit needs and a documentary does
# not: things with wheels, rotors and slide whistles.
#
# Every generator has the same shape — `(dur, seed, gain, **params)` — and
# every one is pure: same seed, same samples, always.


def sfx_siren(dur=3.0, seed=0, gain=1.0, doppler=0.0, hi=622.0, lo=466.0,
              rate=0.45):
    """Two-tone police wail. Set `doppler` to have it pass you.

    Two-tone rather than a continuous sweep because that is the European car;
    the American wail is `rate` around 0.18 with `hi`/`lo` an octave apart.
    """
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    # a square-ish alternation, but rounded — a real horn takes a few ms to
    # slew between the two notes, and the hard switch reads as a glitch
    sw = np.tanh(12.0 * np.sin(2.0 * np.pi * t / max(0.05, rate * 2.0)))
    freq = lo + (hi - lo) * (sw * 0.5 + 0.5)

    if doppler:
        d = float(np.clip(doppler, -1.0, 1.0))
        # pass-by at the midpoint: frequency falls through it, loudness peaks
        u = np.linspace(-1.0, 1.0, n)
        shift = 1.0 + 0.16 * d * np.tanh(-u * 3.0)
        freq = freq * shift
        near = 1.0 / (1.0 + (u * 2.6) ** 2)             # Lorentzian approach
        amp = 0.25 + 0.75 * near
        bright = np.clip(0.45 + 0.55 * near, 0.0, 1.0)
    else:
        amp = np.ones(n)
        bright = None

    ph = _phase(freq)[:n]
    x = (np.sin(ph) + 0.34 * np.sin(2 * ph) + 0.16 * np.sin(3 * ph)
         + 0.07 * np.sin(4 * ph)).astype(np.float32)
    x *= amp.astype(np.float32)
    if bright is not None:
        # as it recedes the top goes first: a cheap distance cue that works
        x = (x * bright + lowpass(x, 900.0, 4) * (1.0 - bright)).astype(np.float32)
    return _fade(x * 0.30 * gain, 0.02)


def sfx_rotor(dur=3.0, seed=0, gain=1.0, blade_hz=11.0, spin=1.0):
    """Helicopter. A thump at blade-pass rate, plus the chop of the air.

    The thump is the whole sound. Filtered noise alone is a hairdryer; what
    makes it a helicopter is a hard periodic transient at the rate the blades
    cross — five rotors at roughly 5.4 Hz per blade, so ~11 Hz thumps.
    """
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    f = float(blade_hz) * float(spin)

    phase = (t * f) % 1.0
    thump_env = np.exp(-phase / 0.085).astype(np.float32)
    body = (np.sin(2 * np.pi * 46.0 * t) + 0.6 * np.sin(2 * np.pi * 92.0 * t)
            + 0.3 * np.sin(2 * np.pi * 138.0 * t)).astype(np.float32)
    thump = body * thump_env

    chop = rng.standard_normal(n).astype(np.float32)
    chop = bandpass(chop, 280.0, 4200.0, order=3)
    chop *= (0.35 + 0.65 * thump_env)                  # the blade slap on the noise

    whine = 0.05 * np.sin(2 * np.pi * (1180.0 * spin) * t).astype(np.float32)
    whine *= (0.7 + 0.3 * np.sin(2 * np.pi * 0.7 * t)).astype(np.float32)

    x = thump * 0.55 + chop * 0.22 + whine
    return _fade(x * 0.42 * gain, 0.05)


def sfx_tyres(dur=1.6, seed=0, gain=1.0):
    """Tyre squeal. Quasi-tonal, wobbling, on the edge of grip."""
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    wob = 1.0 + 0.055 * np.sin(2 * np.pi * 7.3 * t) + 0.03 * np.sin(2 * np.pi * 19.0 * t)
    base = 330.0 * wob
    ph = _phase(base)[:n]
    tone = sum(a * np.sin(k * ph) for k, a in
               ((1, 0.5), (2, 0.62), (3, 0.45), (4, 0.3), (5, 0.18))).astype(np.float32)
    scrub = bandpass(rng.standard_normal(n).astype(np.float32), 1200.0, 6500.0, order=3)
    env = np.minimum(1.0, np.linspace(0, 6, n)) * np.exp(-np.linspace(0, 2.4, n))
    x = (tone * 0.55 + scrub * 0.3) * env.astype(np.float32)
    return _fade(x * 0.34 * gain, 0.01)


def sfx_skid(dur=1.1, seed=0, gain=1.0):
    """A skid that stops: squeal, pitch drop, and a bark at the end."""
    rng = np.random.default_rng((int(seed) * 31 + 5) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    freq = 420.0 * (1.0 - 0.45 * u ** 2) * (1.0 + 0.05 * np.sin(2 * np.pi * 9.0 * t))
    ph = _phase(freq)[:n]
    tone = (0.5 * np.sin(ph) + 0.55 * np.sin(2 * ph) + 0.35 * np.sin(3 * ph)).astype(np.float32)
    scrub = bandpass(rng.standard_normal(n).astype(np.float32), 900.0, 5200.0, order=3)
    env = (np.minimum(1.0, np.linspace(0, 8, n)) * (1.0 - 0.75 * u)).astype(np.float32)
    x = (tone * 0.5 + scrub * 0.28) * env
    # the rubber grabbing at the end
    stop = int(0.9 * n)
    m = n - stop
    if m > 8:
        bark = rng.standard_normal(m).astype(np.float32) * np.exp(-np.linspace(0, 9, m))
        x[stop:] += lowpass(bark, 320.0, 3) * 0.9
    return _fade(x * 0.36 * gain, 0.008)


def sfx_crash(dur=1.4, seed=0, gain=1.0, glass=1.0):
    """Impact: a thump that drops, metal that rings, and debris after."""
    rng = np.random.default_rng((int(seed) * 131 + 11) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)

    boom_f = 120.0 * np.exp(-3.4 * u) + 34.0
    boom = np.sin(_phase(boom_f)[:n]).astype(np.float32) * np.exp(-np.linspace(0, 7, n)).astype(np.float32)

    metal = np.zeros(n, np.float32)
    for f, a, d in ((523.0, 0.5, 5.0), (781.0, 0.4, 6.5), (1147.0, 0.3, 8.0),
                    (1663.0, 0.22, 10.0), (2411.0, 0.15, 12.0)):
        jitter = 1.0 + 0.02 * float(rng.standard_normal())
        metal += (a * np.sin(2 * np.pi * f * jitter * t)
                  * np.exp(-d * u)).astype(np.float32)

    burst = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 14, n)).astype(np.float32)
    burst = bandpass(burst, 200.0, 8000.0, order=2)

    x = boom * 0.85 + metal * 0.3 + burst * 0.5

    if glass > 0:
        # debris: a scatter of tiny high pings, thinning out
        for _ in range(int(26 * glass)):
            at = int(abs(float(rng.exponential(0.22))) * SR)
            if at >= n - 64:
                continue
            m = min(n - at, int(0.09 * SR))
            f = float(rng.uniform(2600.0, 7200.0))
            ping = (np.sin(2 * np.pi * f * t[:m]) *
                    np.exp(-np.linspace(0, 16, m))).astype(np.float32)
            x[at:at + m] += ping * float(rng.uniform(0.05, 0.16)) * glass
    return _fade(x * 0.5 * gain, 0.004)


def sfx_horn(dur=0.9, seed=0, gain=1.0, freq=440.0):
    """Car horn. Two detuned reeds, which is why it beats."""
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    x = np.zeros(n, np.float32)
    for f, a in ((freq, 1.0), (freq * 1.25, 0.85)):
        for k, ka in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.2), (5, 0.13), (6, 0.08)):
            x += (a * ka * np.sin(2 * np.pi * f * k * t)).astype(np.float32)
    env = np.minimum(1.0, np.linspace(0, 40, n)) * np.minimum(1.0, np.linspace(1, 0, n) * 6.0)
    x = x * env.astype(np.float32)
    x = lowpass(x, 4200.0, 3)
    return _fade(x * 0.075 * gain, 0.006)


def sfx_boing(dur=0.7, seed=0, gain=1.0, up=False):
    """Cartoon spring. Falling pitch, wobbling as it goes."""
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    base = (180.0 + 620.0 * u) if up else (760.0 * np.exp(-2.6 * u) + 90.0)
    wobble = 1.0 + 0.28 * np.sin(2 * np.pi * 17.0 * t) * np.exp(-2.2 * u)
    ph = _phase(base * wobble)[:n]
    x = (np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)).astype(np.float32)
    x *= np.exp(-np.linspace(0, 4.2, n)).astype(np.float32)
    return _fade(x * 0.34 * gain, 0.004)


def sfx_pop(dur=0.18, seed=0, gain=1.0, freq=520.0):
    """Cork out of a bottle. Very short — a pop that rings is a boing."""
    rng = np.random.default_rng((int(seed) * 17 + 3) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    f = freq * (1.0 + 2.6 * np.exp(-38.0 * u))
    x = np.sin(_phase(f)[:n]).astype(np.float32) * np.exp(-np.linspace(0, 26, n)).astype(np.float32)
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 90, n)).astype(np.float32)
    x = x * 0.9 + bandpass(click, 900.0, 6000.0, order=2) * 0.35
    return _fade(x * 0.55 * gain, 0.002)


def sfx_thud(dur=0.5, seed=0, gain=1.0):
    """Body hits floor. Low, dry, and over quickly."""
    rng = np.random.default_rng((int(seed) * 61 + 7) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    u = np.linspace(0.0, 1.0, n)
    f = 96.0 * np.exp(-6.0 * u) + 42.0
    x = np.sin(_phase(f)[:n]).astype(np.float32) * np.exp(-np.linspace(0, 11, n)).astype(np.float32)
    slap = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 40, n)).astype(np.float32)
    x = x * 0.95 + lowpass(slap, 700.0, 3) * 0.4
    return _fade(x * 0.5 * gain, 0.003)


def sfx_radio_squelch(dur=0.3, seed=0, gain=1.0):
    """The link opening. Also used inside the radio voice filter."""
    n = max(1, int(dur * SR))
    x = _squelch(dur, seed)
    if len(x) < n:
        x = np.concatenate([x, np.zeros(n - len(x), np.float32)])
    return _fade(x[:n] * 1.5 * gain, 0.003)


def sfx_slide_whistle(dur=0.8, seed=0, gain=1.0, down=True):
    """The oldest gag in animation. Breathy, because it is a whistle."""
    rng = np.random.default_rng((int(seed) * 13 + 1) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    u = np.linspace(0.0, 1.0, n)
    f = (1500.0 * np.exp(-2.2 * u) + 380.0) if down else (420.0 * np.exp(2.0 * u))
    ph = _phase(f)[:n]
    x = (np.sin(ph) + 0.08 * np.sin(2 * ph)).astype(np.float32)
    breath = bandpass(rng.standard_normal(n).astype(np.float32), 1800.0, 7000.0, order=2)
    env = (np.minimum(1.0, np.linspace(0, 25, n))
           * np.minimum(1.0, np.linspace(1.4, 0, n))).astype(np.float32)
    x = (x * 0.5 + breath * 0.06) * env
    return _fade(x * 0.42 * gain, 0.006)


def sfx_clang(dur=1.2, seed=0, gain=1.0, freq=430.0):
    """Frying pan, bin lid, lamppost. Inharmonic on purpose."""
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    x = np.zeros(n, np.float32)
    # ratios from a struck plate, not a string — no integer relationships
    for ratio, a, d in ((1.0, 0.5, 3.0), (2.76, 0.36, 4.4), (5.40, 0.24, 6.0),
                        (8.93, 0.16, 8.0), (13.3, 0.09, 11.0)):
        x += (a * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-d * u)).astype(np.float32)
    strike = np.exp(-np.linspace(0, 120, n)).astype(np.float32)
    x = x + highpass(strike, 2000.0, 2) * 0.5
    return _fade(x * 0.42 * gain, 0.003)


def sfx_zip(dur=0.35, seed=0, gain=1.0):
    """Zip-away exit — the character leaving a person-shaped hole."""
    n = max(1, int(dur * SR))
    u = np.linspace(0.0, 1.0, n)
    f = 300.0 * np.exp(3.1 * u)
    x = np.sin(_phase(f)[:n]).astype(np.float32)
    x = x * (np.minimum(1.0, np.linspace(0, 20, n)) * np.exp(-np.linspace(0, 3.0, n))).astype(np.float32)
    return _fade(x * 0.3 * gain, 0.004)


def _adapt(fn):
    """Give every generator the same call signature.

    The engine's library grew organically and is not uniform — `sfx_chime`
    takes `(freq, dur, gain)` with the frequency *first* and no seed at all,
    which is why the paper renderer special-cases it by name. Rather than
    inherit that, each function is inspected once and called with only the
    keywords it actually accepts; anything it cannot take is dropped, and
    `gain` is applied by hand if it has no gain of its own.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    accepts = set(params)
    variadic = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    def call(dur=None, seed=0, gain=1.0, **extra):
        kw = dict(extra)
        if dur is not None and ("dur" in accepts or variadic):
            kw["dur"] = float(dur)
        if "seed" in accepts or variadic:
            kw["seed"] = int(seed)
        post = 1.0
        if "gain" in accepts or variadic:
            kw["gain"] = float(gain)
        else:
            post = float(gain)
        if not variadic:
            kw = {k: v for k, v in kw.items() if k in accepts}
        out = np.asarray(fn(**kw), dtype=np.float32)
        return out * post if post != 1.0 else out

    call.__name__ = getattr(fn, "__name__", "sfx")
    call.__doc__ = fn.__doc__
    call.raw = fn
    return call


#: Everything the engine already has — whooshes, cracks, steps, wind, crowd,
#: engine, rain, thunder, creaks, birds, clocks, hearts, water, bells — plus
#: the chase kit above. Borrowing rather than re-writing means a `whoosh` in
#: this style is the same whoosh the paper films use.
_NEW = {
    "siren": sfx_siren,
    "rotor": sfx_rotor,
    "tyres": sfx_tyres,
    "skid": sfx_skid,
    "crash": sfx_crash,
    "horn": sfx_horn,
    "boing": sfx_boing,
    "pop": sfx_pop,
    "thud": sfx_thud,
    "radio_squelch": sfx_radio_squelch,
    "slide_whistle": sfx_slide_whistle,
    "clang": sfx_clang,
    "zip": sfx_zip,
}

SFX: dict = {name: _adapt(fn) for name, fn in getattr(P, "SFX", {}).items()}
SFX.update({name: _adapt(fn) for name, fn in _NEW.items()})

#: Names a storyboard is likely to reach for that are really something we have.
#: Cheap, and it turns a silent missing gag into the right sound.
ALIASES = {
    "helicopter": "rotor", "chopper": "rotor", "blades": "rotor",
    "police": "siren", "police_siren": "siren", "wail": "siren",
    "screech": "tyres", "tires": "tyres", "squeal": "tyres",
    "impact": "crash", "smash": "crash", "collision": "crash",
    "beep": "horn", "honk": "horn",
    "spring": "boing", "bounce": "boing",
    "bonk": "thud", "bump": "thud", "land": "thud",
    "swoosh": "whoosh", "swish": "whoosh", "dash": "whoosh",
    "squelch": "radio_squelch", "static": "radio_squelch",
    "whistle": "slide_whistle", "slide": "slide_whistle",
    "bang": "clang", "metal": "clang",
    "footsteps": "steps", "run": "steps", "running": "steps",
    "car": "engine", "motor": "engine", "traffic": "engine",
    "people": "crowd", "chatter": "crowd",
    "snap": "crack", "break": "crack",
}

#: Comic punctuation. These punch *through* the music (see `build`); the rest
#: sit in the bed with it. The distinction is the whole reason the mix has an
#: accent bus at all — a `boing` that arrives 6 dB under a chase bass is not a
#: joke, it is a noise.
ACCENTS = frozenset({
    "boing", "pop", "thud", "crash", "horn", "slide_whistle", "clang",
    "whoosh", "skid", "crack", "radio_squelch", "zip", "stamp", "chime",
    "bell", "tyres",
})

#: Roughly how long each effect wants to be if the board does not say. Used
#: only as a default; `sfx[].dur` always wins.
_DEFAULT_DUR = {
    "siren": 3.0, "rotor": 3.0, "tyres": 1.6, "skid": 1.1, "crash": 1.4,
    "horn": 0.9, "boing": 0.7, "pop": 0.18, "thud": 0.5, "radio_squelch": 0.3,
    "slide_whistle": 0.8, "clang": 1.2, "zip": 0.35,
}


def sfx(kind: str, dur=None, seed: int = 0, gain: float = 1.0, **params):
    """Render one effect by name, resolving aliases. `None` if unknown."""
    name = (kind or "").strip().lower().replace("-", "_").replace(" ", "_")
    name = ALIASES.get(name, name)
    fn = SFX.get(name)
    if fn is None:
        _warn(f"no sound effect named {kind!r} — skipped "
              f"(have: {', '.join(sorted(SFX)[:12])} ...)")
        return None
    if dur is None:
        dur = _DEFAULT_DUR.get(name)
    return fn(dur=dur, seed=seed, gain=gain, **params)


# ==================================================================== ambience ==
#
# `ambience` in this style's board is a bare string. The engine has beds for
# the documentary vocabulary (room, street, forest, sea, rain, night, fire,
# crowd); a chase wants a couple it does not have, and wants `city` to mean
# something denser than `street`.


def _amb_city(dur, seed):
    rng = np.random.default_rng((int(seed) * 5 + 2) & 0xFFFFFFFF)
    n = int(dur * SR)
    x = np.asarray(SFX["crowd"](dur=dur, seed=seed, gain=0.55), dtype=np.float32)[:n]
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    eng = np.asarray(SFX["engine"](dur=dur, seed=seed + 3, gain=0.4), dtype=np.float32)[:n]
    if len(eng) < n:
        eng = np.pad(eng, (0, n - len(eng)))
    x = x + lowpass(eng, 1400.0, 3) * 0.6
    # one distant horn, so the city has a foreground
    at = int(float(rng.uniform(0.2, max(0.3, dur - 1.2))) * SR)
    h = sfx_horn(0.6, seed + 9, 0.22)
    m = min(n - at, len(h))
    if m > 0:
        x[at:at + m] += lowpass(h[:m], 2000.0, 3)
    return x


def _amb_chopper(dur, seed):
    return sfx_rotor(dur, seed, gain=0.5, blade_hz=10.4, spin=0.92)


def _amb_sirens(dur, seed):
    rng = np.random.default_rng((int(seed) * 23 + 4) & 0xFFFFFFFF)
    n = int(dur * SR)
    x = np.zeros(n, np.float32)
    for i in range(2):
        s = sfx_siren(dur, seed + i * 7, gain=0.22,
                      hi=622.0 * (1.0 + 0.03 * i), lo=466.0 * (1.0 + 0.03 * i),
                      rate=0.45 + 0.06 * i)
        s = lowpass(s, 1500.0, 4) * float(rng.uniform(0.5, 0.9))
        x[:len(s)] += s[:n]
    return x


def _amb_traffic(dur, seed):
    x = np.asarray(SFX["engine"](dur=dur, seed=seed, gain=0.5), dtype=np.float32)
    return lowpass(x, 900.0, 3)


AMBIENCE = {name: (lambda d, s, _f=fn: np.asarray(_f(dur=d, seed=s), dtype=np.float32))
            for name, fn in
            {n: SFX[n] for n in getattr(P, "AMBIENT", ()) if n in SFX}.items()}
AMBIENCE.update({
    "city": _amb_city,
    "street": _amb_city,
    "urban": _amb_city,
    "traffic": _amb_traffic,
    "chopper": _amb_chopper,
    "helicopter": _amb_chopper,
    "rotor": _amb_chopper,
    "sirens": _amb_sirens,
    "pursuit": _amb_sirens,
})


def build_ambience(name: str, dur: float, seed: int = 0, gain: float = 1.0):
    """A looped bed of `dur` seconds. Empty on an unknown or absent name."""
    key = (name or "").strip().lower().replace("-", "_")
    if not key or key in ("none", "silence", "silent"):
        return np.zeros(int(dur * SR), np.float32)
    fn = AMBIENCE.get(key) or AMBIENCE.get(ALIASES.get(key, ""))
    if fn is None:
        base = SFX.get(ALIASES.get(key, key))
        if base is None:
            _warn(f"no ambience named {name!r} — running dry")
            return np.zeros(int(dur * SR), np.float32)
        fn = lambda d, s, _f=base: np.asarray(_f(dur=d, seed=s), dtype=np.float32)

    # Six seconds is long enough that the loop is not obvious and short enough
    # that a 90-second film does not spend a second of CPU on room tone.
    seg = float(min(max(6.0, dur * 0.25), max(1.0, dur)))
    bed = fn(seg, int(seed))
    bed = _fade(np.asarray(bed, dtype=np.float32), 1.2)
    out = P.loop_to(bed, int(dur * SR))
    return _fade(np.asarray(out, dtype=np.float32) * float(gain), 0.8)


# ======================================================================= score ==
#
# `style-paper`'s thirteen moods are documentary moods, and every one of them
# sits at or below 92 bpm — deliberately, because a bed under a 145 wpm read
# should not fight the read. The nearest thing it has to a pursuit is `crime`
# (minor, 92, sub drone, dry plucks, clock), which is a *procedural* bed: under
# a cartoon chase it reads as a murder investigation rather than a joke.
#
# So four moods are added here. They break the 92 bpm ceiling, and the reason
# they are allowed to is the reason the ceiling exists: the rule is about not
# competing with speech. These beds keep their harmonic rhythm slow — one chord
# per two bars, so a chord change every ~4.4 s at 108 bpm, slower than `crime`
# changes at 92 — and put their energy into a walking bass and off-beat stabs
# that sit *between* the syllables rather than on top of them. `scramble`, the
# fastest, is flagged for wordless sequences only.
#
# Everything in `S.MOODS` still works; these are added, not substituted.

CHASE_MOODS = {
    "chase":    dict(scale="dorian",     bpm=108, root=55.00, melody_root=69,
                     colour="comic pursuit — light on its feet, not menacing",
                     kit="chase"),
    "caper":    dict(scale="dorian",     bpm=100, root=58.27, melody_root=70,
                     colour="scheming, tiptoe, a plan going slightly wrong",
                     kit="chase"),
    "romp":     dict(scale="mixolydian", bpm=116, root=61.74, melody_root=73,
                     colour="daft momentum, no one is in real danger",
                     kit="chase"),
    "scramble": dict(scale="minor",      bpm=126, root=49.00, melody_root=71,
                     colour="everything at once — wordless peaks only",
                     kit="chase"),
}

MOODS = dict(getattr(S, "MOODS", {}))
MOODS.update(CHASE_MOODS)

MOOD_ALIASES = {
    "pursuit": "chase", "comedy": "romp", "comic": "romp", "funny": "romp",
    "heist": "caper", "sneaky": "caper", "panic": "scramble",
    "frantic": "scramble", "action": "chase",
}

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "minor_pentatonic": [0, 3, 5, 7, 10],
}

#: Which cue renderer a mood wants. Anything not listed gets the generic bed.
_CHASE_KIT = frozenset(CHASE_MOODS)


def resolve_mood(name) -> tuple[str, dict]:
    """Name -> (canonical name, spec). Unknown moods become `chase`."""
    key = (name or "chase").strip().lower().replace("-", "_")
    key = MOOD_ALIASES.get(key, key)
    spec = MOODS.get(key)
    if spec is None:
        _warn(f"unknown mood {name!r} — using chase")
        key, spec = "chase", MOODS["chase"]
    return key, dict(spec)


def _degree(scale, root_midi, degree):
    """Scale degree -> MIDI note, wrapping into octaves above and below."""
    n = len(scale)
    octave, idx = divmod(int(degree), n)
    return root_midi + 12 * octave + scale[idx]


def _bass(freq, dur, gain=1.0, seed=0):
    """Upright bass note: fundamental, a little body, and a finger click.

    The engine's `pulse_bass` is a synth pulse — right for a documentary
    ostinato, wrong here. A walking line needs a note with an attack you can
    hear, because in a walking line the *rhythm* is the point.
    """
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    x = (np.sin(2 * np.pi * freq * t)
         + 0.30 * np.sin(4 * np.pi * freq * t)
         + 0.12 * np.sin(6 * np.pi * freq * t)).astype(np.float32)
    body = np.exp(-3.1 * u).astype(np.float32)
    click = np.exp(-np.linspace(0, 160, n)).astype(np.float32)
    x = x * body + highpass(click, 1400.0, 2) * 0.10
    return _fade(x * 0.32 * float(gain), 0.004)


def _stab(freqs, dur, gain=1.0, seed=0):
    """Off-beat chord stab — short, bright, and gone before the next word."""
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    u = np.linspace(0.0, 1.0, n)
    x = np.zeros(n, np.float32)
    for i, f in enumerate(freqs):
        x += ((0.9 ** i) * (np.sin(2 * np.pi * f * t)
                            + 0.45 * np.sin(4 * np.pi * f * t)
                            + 0.18 * np.sin(6 * np.pi * f * t))).astype(np.float32)
    x *= (np.minimum(1.0, np.linspace(0, 60, n)) * np.exp(-7.5 * u)).astype(np.float32)
    x = bandpass(x, 220.0, 5200.0, order=2)
    return _fade(x * 0.17 * float(gain) / max(1, len(freqs)) ** 0.5, 0.003)


def _brush(dur, seed=0, gain=1.0, beat=0.5, swirl=1.0):
    """Brushed snare: a continuous circular swirl, modulated at the beat.

    Sticks would be wrong. The swirl is what keeps a comic bed *light* — it
    gives constant motion without a single hard transient to trip over a word.
    """
    rng = np.random.default_rng((int(seed) * 97 + 13) & 0xFFFFFFFF)
    n = max(1, int(dur * SR))
    t = _t(dur)[:n]
    noise = rng.standard_normal(n).astype(np.float32)
    swish = highpass(noise, 2600.0, 2)
    rate = 1.0 / max(0.05, beat)
    mod = (0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t - np.pi / 2))).astype(np.float32)
    return (swish * mod * 0.045 * float(gain) * float(swirl)).astype(np.float32)


def _kick(dur=0.16, gain=1.0):
    n = max(1, int(dur * SR))
    u = np.linspace(0.0, 1.0, n)
    f = 110.0 * np.exp(-9.0 * u) + 44.0
    x = np.sin(_phase(f)[:n]).astype(np.float32) * np.exp(-14.0 * u).astype(np.float32)
    return _fade(x * 0.30 * float(gain), 0.003)


def _render_chase(spec, dur, seed=0, intensity=1.0):
    """The comedy chase bed: walking bass, off-beat stabs, brushes, a hook.

    `intensity` (0..1) is how the film builds and releases. It moves four
    things at once — how many stabs there are, whether the bass walks in
    quavers or crotchets, how present the brushes are, and whether the comic
    hook shows up — because a bed that only gets *louder* does not read as
    tension, it reads as a fader move.
    """
    n = max(1, int(dur * SR))
    if n < 16:
        return np.zeros(n, np.float32)
    rng = np.random.default_rng((int(seed) * 1009 + 7) & 0xFFFFFFFF)
    inten = float(np.clip(intensity, 0.0, 1.0))

    bpm = float(spec.get("bpm", 108))
    beat = 60.0 / max(20.0, bpm)
    bar = beat * 4.0
    scale = SCALES.get(spec.get("scale", "dorian"), SCALES["dorian"])
    root_hz = float(spec.get("root", 55.0))
    root_midi = int(round(69 + 12 * math.log2(root_hz / 440.0)))
    mel_root = int(spec.get("melody_root", 69)) + (12 if inten > 0.85 else 0)

    track = P.Track(dur)
    # i - IV - i - V in scale degrees: a two-chords-per-four-bars turnaround,
    # slow enough to sit under speech, familiar enough to feel like a chase.
    prog = [0, 3, 0, 4]
    nbars = int(math.ceil(dur / bar))

    for b in range(nbars):
        t0 = b * bar
        if t0 >= dur:
            break
        deg = prog[b % len(prog)]
        chord_root = _degree(scale, root_midi, deg)

        # --- walking bass: one note a beat, stepping into the next chord ---
        nxt = _degree(scale, root_midi, prog[(b + 1) % len(prog)])
        walk = [chord_root, chord_root + scale[2], chord_root + scale[4], nxt - 1]
        step = beat if inten < 0.9 else beat
        for i, note in enumerate(walk):
            at = t0 + i * step
            if at >= dur:
                break
            track.add(_bass(P.midi_hz(note), beat * 0.92,
                            gain=0.85 + 0.15 * inten, seed=seed + b * 4 + i), at)
            if inten > 0.72 and i in (1, 3):
                # a passing quaver, only when it is pressing
                track.add(_bass(P.midi_hz(note + 2), beat * 0.42, 0.55,
                                seed + b * 40 + i), at + beat * 0.5)

        # --- off-beat stabs: the '&' of 2 and 4, plus 3 when it is busy ----
        chord = [P.midi_hz(_degree(scale, root_midi, deg + k) + 24) for k in (0, 2, 4)]
        offs = [1.5, 3.5] + ([2.5] if inten >= 0.8 else [])
        for o in offs:
            at = t0 + o * beat
            if at < dur:
                track.add(_stab(chord, beat * 0.55, gain=0.7 + 0.6 * inten,
                                seed=seed + b * 7 + int(o * 2)), at)

        # --- percussion --------------------------------------------------
        track.add(_kick(0.16, 0.8 + 0.4 * inten), t0)
        if inten > 0.35:
            track.add(_kick(0.14, 0.5), min(dur, t0 + beat * 2.5))
        for o in (1.0, 3.0):
            at = t0 + o * beat
            if at < dur:
                track.add(np.asarray(P.shaker(beat * 0.4, 0.35 + 0.35 * inten),
                                     dtype=np.float32), at)

        # --- the comic hook, every four bars, once it is moving -----------
        if b % 4 == 2 and inten > 0.5:
            hook = [0, 2, 1, 4] if rng.random() < 0.5 else [4, 2, 3, 0]
            for i, d in enumerate(hook):
                at = t0 + (i * 0.5 + 0.5) * beat
                if at < dur:
                    track.add(np.asarray(
                        P.pluck(P.midi_hz(_degree(scale, mel_root - 12, d) + 12),
                                beat * 0.45, 0.5 + 0.3 * inten), dtype=np.float32), at)

    out = track.array().reshape(-1)[:n]
    if len(out) < n:
        out = np.pad(out, (0, n - len(out)))
    out = out + _brush(dur, seed, gain=0.55 + 0.9 * inten, beat=beat)[:n]
    return highpass(out.astype(np.float32), 34.0, 2)


def _render_generic(spec, dur, seed=0, intensity=1.0):
    """Any of the engine's moods, in a compact form.

    Not a re-implementation of the paper renderer — that one is 300 lines and
    lives in a `render.py` this module deliberately cannot import (see the
    header). It is a drone, a pad and a sparse figure, which is enough to keep
    every documented mood usable from this style without duplicating the
    engine's whole score department.
    """
    n = max(1, int(dur * SR))
    if n < 16:
        return np.zeros(n, np.float32)
    rng = np.random.default_rng((int(seed) * 733 + 3) & 0xFFFFFFFF)
    inten = float(np.clip(intensity, 0.0, 1.0))
    bpm = float(spec.get("bpm", 72))
    beat = 60.0 / max(20.0, bpm)
    scale = SCALES.get(spec.get("scale", "minor"), SCALES["minor"])
    root_hz = float(spec.get("root", 55.0))
    root_midi = int(round(69 + 12 * math.log2(root_hz / 440.0)))
    mel_root = int(spec.get("melody_root", 69))

    track = P.Track(dur)
    track.add(np.asarray(P.low_drone(root_hz, dur, 0.5), dtype=np.float32), 0.0)
    track.add(np.asarray(P.warm_pad([P.midi_hz(root_midi + 12),
                                     P.midi_hz(_degree(scale, root_midi, 4) + 12)],
                                    dur, 0.28 + 0.2 * inten, seed=seed),
                         dtype=np.float32), 0.0)

    voice = (P.celesta if spec.get("scale") in ("major", "lydian")
             else (P.bowed if bpm < 62 else P.pluck))
    step = beat * (2.0 if inten < 0.6 else 1.0)
    at = beat
    i = 0
    while at < dur - step * 0.5:
        if rng.random() > 0.30 * (1.0 - inten) + 0.12:
            deg = int(rng.integers(0, 5))
            note = _degree(scale, mel_root, deg)
            track.add(np.asarray(voice(P.midi_hz(note), step * 0.9,
                                       0.32 + 0.2 * inten), dtype=np.float32), at)
        at += step
        i += 1

    out = track.array().reshape(-1)[:n]
    if len(out) < n:
        out = np.pad(out, (0, n - len(out)))
    return highpass(out.astype(np.float32), 30.0, 2)


def render_cue(cue: dict, dur: float, seed: int = 0):
    """One music cue. `cue` carries mood/bpm/register/density overrides."""
    name, spec = resolve_mood(cue.get("mood"))
    for k in ("bpm", "scale", "root", "melody_root"):
        if cue.get(k) is not None:
            spec[k] = cue[k]
    reg = int(cue.get("register", 0) or 0)
    if reg:
        spec["root"] = float(spec["root"]) * (2.0 ** reg)
        spec["melody_root"] = int(spec["melody_root"]) + 12 * reg
    inten = float(cue.get("intensity",
                          min(1.0, 0.55 * float(cue.get("density", 1.0)) + 0.3)))
    fn = _render_chase if name in _CHASE_KIT else _render_generic
    return fn(spec, float(dur), int(cue.get("seed", seed)), inten)


def _arc_envelope(dur, peak=1.0, tail=0.7, edge=1.6):
    """Rise, hold, settle — a cue that arrives and leaves, not a fader.

    Mirrors the engine's `_cue_envelope`: up to `peak` at about 70% through,
    down to `tail` by the end, with soft edges so the entry is not a click and
    the exit is not a cut.
    """
    n = max(1, int(dur * SR))
    u = np.linspace(0.0, 1.0, n)
    shape = np.where(u < 0.7,
                     0.72 + (float(peak) - 0.72) * (u / 0.7),
                     float(peak) + (float(tail) - float(peak)) * ((u - 0.7) / 0.3))
    e = min(int(min(edge, dur * 0.35) * SR), n // 2)
    if e > 1:
        shape[:e] *= np.linspace(0.0, 1.0, e) ** 1.5
        shape[-e:] *= np.linspace(1.0, 0.0, e) ** 1.2
    return shape.astype(np.float32)


#: Where each act sits on the intensity scale. The chase gets going, presses,
#: then lets go — a film that is flat out from the first frame has nowhere to
#: build to and stops being funny about forty seconds in.
ARC_INTENSITY = (0.45, 0.72, 1.00, 0.55)


def cue_plan(music: dict, total_dur: float, seed: int = 0) -> list[dict]:
    """Spot a film into cues, honouring `music.cues` if the board supplies them."""
    music = dict(music or {})
    given = music.get("cues")
    if given:
        out = []
        for i, c in enumerate(given):
            c = dict(c)
            c.setdefault("mood", music.get("mood", "chase"))
            c.setdefault("seed", (int(seed) + i * 17) % 9973)
            c.setdefault("at", 0.0)
            c.setdefault("dur", max(0.0, total_dur - float(c["at"])))
            out.append(c)
        return out

    mood = music.get("mood", "chase")
    if total_dur < 6.0:
        n = 1
    elif total_dur < 24.0:
        n = 2
    elif total_dur < 60.0:
        n = 3
    else:
        n = 4

    arc = getattr(S, "ARC", None) or [{}]
    span = total_dur / n
    cues = []
    for i in range(n):
        shape = dict(arc[min(i, len(arc) - 1)]) if n > 1 else dict(arc[min(1, len(arc) - 1)])
        if n > 1 and i == n - 1:
            shape = dict(arc[-1])
        t0, t1 = i * span, (i + 1) * span
        # Silence in front of every cue. This is what makes the next one an
        # event rather than a continuation, and it is the single cheapest way
        # to stop 90 seconds of bed turning into wallpaper.
        lead = min(float(shape.get("silence", 1.2)), max(0.0, (t1 - t0) * 0.22))
        start = t0 + lead
        length = max(0.0, t1 - start)
        if length < 1.5:
            continue
        _, base = resolve_mood(mood)
        cues.append({
            "mood": mood,
            "at": round(start, 3),
            "dur": round(length, 3),
            "bpm": round(float(base["bpm"]) * float(shape.get("tempo", 1.0)), 1),
            "register": int(shape.get("register", 0)),
            "intensity": ARC_INTENSITY[min(i, len(ARC_INTENSITY) - 1)],
            "peak": float(shape.get("peak", 1.0)),
            "tail": float(shape.get("tail", 0.7)),
            "seed": (int(seed) + i * 17) % 9973,
            "_act": shape.get("name", "act%d" % i),
        })
    return cues


def build_music(music: dict, total_dur: float, seed: int = 0):
    """The whole score: every cue, enveloped, laid onto one bed."""
    out = np.zeros(int(total_dur * SR), np.float32)
    music = dict(music or {})
    if music.get("mood") in ("none", "silence") or music.get("gain") == 0:
        return out
    for cue in cue_plan(music, total_dur, seed):
        at = max(0.0, float(cue.get("at", 0.0)))
        dur = min(float(cue.get("dur", 0.0)), max(0.0, total_dur - at))
        if dur < 1.0:
            continue
        sig = render_cue(cue, dur, seed)
        sig = sig * _arc_envelope(dur, cue.get("peak", 1.0), cue.get("tail", 0.7))
        a = int(at * SR)
        b = min(len(out), a + len(sig))
        if b > a:
            out[a:b] += sig[:b - a]
    return out


# =================================================================== narration ==
#
# This skill does not synthesise speech. `narration[].audio` points at a file
# made elsewhere (the `voice-booth` skill, or anything ffmpeg can read); a line
# with only a `duration` is a *placeholder*, which is how a board can be timed
# and animated before a word has been recorded.
#
# The important rule here is that `line_times` and the mix must agree to the
# sample. The whole film's timing hangs off `line_times` — every shot that says
# `at: "l3"` resolves through it — so if the mix trimmed silence a hair
# differently, picture and sound would slide apart a little more with every
# line. They therefore share one cached loader and neither can measure a line
# the other will not play.

_LINE_CACHE: dict = {}


def _stable_hash(text: str) -> int:
    """A hash that survives a restart. See `_line_signal`."""
    return zlib.crc32(str(text).encode("utf-8")) % 9973


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _load_audio(path: str) -> np.ndarray:
    """Mono float32 at the project rate, straight from ffmpeg's stdout.

    The engine's `load_audio` does the same job via `tempfile.mktemp`. Piping
    avoids the temp file (and the race that `mktemp` carries) — but the engine
    is still the fallback, so a machine without ffmpeg on PATH behaves exactly
    as the paper style does rather than failing differently.
    """
    if path.lower().endswith(".wav"):
        try:
            a, sr = P.read_wav(path)
            if sr == SR:
                return np.asarray(a, dtype=np.float32)
        except Exception:
            pass
    if shutil.which("ffmpeg") is None:
        return np.asarray(P.load_audio(path), dtype=np.float32)
    r = subprocess.run(
        [_ffmpeg(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
         "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"could not read narration {path}: "
                           f"{r.stderr.decode('utf-8', 'replace')[:200]}")
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float32)


def _line_signal(line: dict, base_dir: str, seed: int = 0) -> np.ndarray:
    """The audio for one narration line: loaded, trimmed, filtered.

    Cached on the file's identity *and* the filter, because `line_times` and
    `build` both want it and the loudness of a filtered line is not the same as
    the raw one.
    """
    audio = line.get("audio")
    filt = (line.get("filter") or "none").strip().lower()
    lid = str(line.get("id", ""))

    if not audio:
        # a placeholder line: silence of the stated length, so timing works
        # before the voice exists
        dur = float(line.get("duration", 0.0) or 0.0)
        return np.zeros(max(0, int(dur * SR)), np.float32)

    path = audio if os.path.isabs(audio) else os.path.join(base_dir or ".", audio)
    path = os.path.normpath(path)
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size, filt, int(seed))
    except OSError:
        _warn(f"narration file missing for line {lid!r}: {path} — using silence")
        dur = float(line.get("duration", 0.0) or 0.0)
        return np.zeros(max(0, int(dur * SR)), np.float32)

    hit = _LINE_CACHE.get(key)
    if hit is not None:
        return hit

    x = _load_audio(path)
    x = np.asarray(P.trim_silence(x), dtype=np.float32)
    if filt not in ("none", "dry", "clean", ""):
        # Seeded off the line id, so the same line always gets the same hiss
        # and the same squelch however often the board is re-rendered.
        # `crc32`, not `hash`: Python salts string hashing per process, so
        # `hash("l2")` differs between runs and the "deterministic" render
        # would quietly produce a different file every time it was invoked.
        x = voice_filter(x, filt, seed=int(seed) + _stable_hash(lid))
    _LINE_CACHE[key] = x
    return x


def line_times(board: dict, base_dir: str = ".") -> dict:
    """Measure the read: ``{line_id: (start_sec, end_sec)}``.

    Returns `{}` for a wordless film — which is a legitimate board, not an
    error, and the caller must cope with it.
    """
    lines = (board or {}).get("narration") or []
    timing = (board or {}).get("timing") or {}
    cursor = float(timing.get("lead_in", 0.6) or 0.0)
    gap_default = float(timing.get("gap", 0.55) or 0.0)

    out: dict = {}
    for i, line in enumerate(lines):
        lid = str(line.get("id") or f"l{i + 1}")
        sig = _line_signal(line, base_dir, seed=0)
        dur = len(sig) / SR
        if dur <= 0.0:
            dur = float(line.get("duration", 0.0) or 0.0)
        start = cursor
        end = start + dur
        out[lid] = (round(start, 4), round(end, 4))
        cursor = end + float(line.get("gap_after", gap_default) or 0.0)
    return out


def film_duration(board: dict, base_dir: str = ".") -> float:
    """How long the film runs: the read, plus the tail, or at least the shots.

    A wordless board has no read, so the shots decide — which is why this does
    not simply return the end of the last line.
    """
    board = board or {}
    timing = board.get("timing") or {}
    times = line_times(board, base_dir)
    end = max((e for _, e in times.values()), default=0.0)
    end += float(timing.get("tail", 1.2) or 0.0)

    for sh in board.get("shots") or []:
        until = resolve_time(times, sh.get("until"), None)
        if until is not None:
            end = max(end, until)
            continue
        at = resolve_time(times, sh.get("at"), None)
        if at is not None:
            end = max(end, at + float(sh.get("dur", 2.0) or 2.0))
    return max(1.0, round(end, 3))


# ================================================================ time syntax ==


def resolve_time(times: dict, spec, default=0.0):
    """The board's time grammar: ``12.5``, ``"l3"``, ``"l3+0.4"``, ``"l3.end"``.

    Anchoring to a line rather than to a number is what lets a board survive
    re-recording: the reporter says her line half a second slower, every cut
    tied to it moves with her, and no one re-times the film by hand.
    """
    if spec is None:
        return default
    if isinstance(spec, (int, float)):
        return float(spec)

    s = str(spec).strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        pass

    # An exact line id wins before anything is split off it, so an id that
    # happens to contain a hyphen ("line-3") is not read as "line" minus 3.
    if s in times:
        return float(times[s][0])

    sign, offset = 1.0, 0.0
    for op in ("+", "-"):
        if op in s[1:]:
            head, _, tail = s[1:].rpartition(op)
            head = s[0] + head
            try:
                offset = float(tail.strip())
                sign = 1.0 if op == "+" else -1.0
                s = head.strip()
                break
            except ValueError:
                pass

    at_end = False
    if s.endswith(".end"):
        s, at_end = s[:-4], True
    elif s.endswith(".start"):
        s = s[:-6]

    span = times.get(s)
    if span is None:
        _warn(f"time reference {spec!r} names no narration line — using {default}")
        return default
    return float(span[1] if at_end else span[0]) + sign * offset


# ========================================================================= mix ==


def _duck_by(bed, trigger, depth_db=-5.0, attack_ms=3.0, release_ms=180.0,
             thresh=0.02):
    """Duck `bed` under `trigger`, with a shape of our choosing.

    The engine's `duck` is tuned for speech — 8 ms attack, 260 ms release,
    which is right for a sentence and much too slow for a `boing`. A comic
    accent is over in 400 ms; by the time a speech-shaped ducker had opened
    its gain back up the joke would have finished. Hence a second, faster one.
    """
    bed = np.asarray(bed, dtype=np.float32)
    trg = np.asarray(trigger, dtype=np.float32)
    n = max(len(bed), len(trg))
    if n == 0:
        return bed
    b = np.pad(bed, (0, n - len(bed)))
    t = np.pad(trg, (0, n - len(trg)))
    env = P.envelope_follow(t, attack_ms, release_ms)
    drive = np.clip((env - float(thresh)) / 0.10, 0.0, 1.0)
    gain = 10.0 ** ((float(depth_db) * drive) / 20.0)
    return (b * gain).astype(np.float32)


def _limit(x, ceiling=0.55, attack_ms=1.0, release_ms=60.0):
    """Fast peak control for the comic accents.

    A `crash` has a crest factor of about 20 dB: almost all of its level lives
    in the first two milliseconds. Left alone it owns the headroom of the whole
    film — the delivery limiter spends its range flattening one transient, and
    the master comes back measurably quiet because of it. Flattening the accent
    *here* instead is also what a dub mixer would do: an accent should be
    dense, not spiky, or it reads as a click rather than a joke.
    """
    x = np.asarray(x, dtype=np.float32)
    if not len(x):
        return x
    env = P.envelope_follow(x, attack_ms, release_ms)
    gain = np.minimum(1.0, float(ceiling) / np.maximum(env, 1e-6))
    return (x * gain).astype(np.float32)


def _fit(x, n):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if len(x) >= n:
        return x[:n]
    return np.pad(x, (0, n - len(x)))


def build(board: dict, base_dir: str = ".", total_dur: float | None = None,
          *, seed: int = 0, report: dict | None = None):
    """The complete mix for a storyboard: narration, score, ambience, effects.

    Returns **mono** float32, one dimension, `total_dur` seconds long. Mono
    because that is what the engine's `write_wav` and `master` expect to be
    handed (the paper renderer stacks it to stereo at the very last moment,
    and any panning decision belongs there, not here).

    The order of operations is the whole argument of this function:

    1. Lay the read down first. Everything else is timed against it.
    2. Duck the score and the ambience under the read — the engine's own
       ducker, at its own depth, because that part is solved.
    3. Add the effects **after** that ducking, at full level. A siren is a
       story event; it should not drop 11 dB because someone is talking.
    4. Duck the score and the ambience *again*, this time under the comic
       accents only, fast and shallow. This is the comedy-specific move: a
       `boing` should punch a hole in the bed and drop through it. Buried
       under a walking bass it is not a gag, it is a noise.
    """
    board = board or {}
    rep = report if report is not None else {}
    times = line_times(board, base_dir)
    if total_dur is None:
        total_dur = film_duration(board, base_dir)
    total_dur = float(max(0.5, total_dur))
    n = int(total_dur * SR)

    mix_cfg = dict(board.get("mix") or {})
    g_voice = float(mix_cfg.get("voice", 1.0))
    g_music = float(mix_cfg.get("music", 0.62))
    g_amb = float(mix_cfg.get("ambience", 0.45))
    g_sfx = float(mix_cfg.get("sfx", 0.55))
    duck_db = -abs(float(mix_cfg.get("duck_db", 11.0)))
    accent_db = -abs(float(mix_cfg.get("accent_duck_db", 5.0)))

    # ---------------------------------------------------------- narration --
    voice = np.zeros(n, np.float32)
    lines = board.get("narration") or []
    if not lines:
        rep["narration"] = 0
        # A wordless film. The bed and the effects carry it, so the music
        # should not sit politely in the background: nothing is competing.
        g_music = float(mix_cfg.get("music", 0.86))
    else:
        rep["narration"] = len(lines)
        for i, line in enumerate(lines):
            lid = str(line.get("id") or f"l{i + 1}")
            sig = _line_signal(line, base_dir, seed=seed)
            if not len(sig):
                continue
            at = times.get(lid, (0.0, 0.0))[0]
            a = int(at * SR)
            b = min(n, a + len(sig))
            if b > a:
                voice[a:b] += sig[:b - a] * float(line.get("gain", 1.0) or 1.0)

    # -------------------------------------------------------------- score --
    music_cfg = dict(board.get("music") or {})
    if music_cfg or not lines:
        music_cfg.setdefault("mood", "chase")
    music = build_music(music_cfg, total_dur, seed) if music_cfg else np.zeros(n, np.float32)
    music = _fit(music, n) * float(music_cfg.get("gain", 1.0) or 1.0)
    rep["mood"] = resolve_mood(music_cfg.get("mood"))[0] if music_cfg else None

    # ----------------------------------------------------------- ambience --
    amb_cfg = board.get("ambience")
    amb_gain = 1.0
    if isinstance(amb_cfg, dict):
        amb_gain = float(amb_cfg.get("gain", 1.0) or 1.0)
        amb_cfg = amb_cfg.get("name") or amb_cfg.get("kind")
    ambience = _fit(build_ambience(amb_cfg or "", total_dur, seed + 5), n) * amb_gain
    rep["ambience"] = amb_cfg or None

    # ------------------------------------------------------------ effects --
    accents = np.zeros(n, np.float32)
    beds = np.zeros(n, np.float32)
    placed, missing = 0, []
    for si, shot in enumerate(board.get("shots") or []):
        shot_at = resolve_time(times, shot.get("at"), 0.0)
        for k, cue in enumerate(shot.get("sfx") or []):
            if isinstance(cue, str):
                cue = {"kind": cue}
            kind = str(cue.get("kind") or cue.get("name") or "")
            local = cue.get("at", 0.0)
            # `at` inside a shot is shot-local seconds, but a board that writes
            # "l4+0.2" there clearly means the film clock; accept both.
            if isinstance(local, str):
                when = resolve_time(times, local, shot_at)
            else:
                when = shot_at + float(local or 0.0)
            dur = cue.get("dur", cue.get("duration"))
            gain = float(cue.get("gain", 1.0) or 1.0)
            extra = {k2: v for k2, v in cue.items()
                     if k2 not in ("kind", "name", "at", "dur", "duration", "gain")}
            sig = sfx(kind, dur, seed=seed + si * 31 + k * 7, gain=gain, **extra)
            if sig is None:
                missing.append(kind)
                continue
            canon = ALIASES.get(kind.strip().lower().replace("-", "_"),
                                kind.strip().lower().replace("-", "_"))
            target = accents if canon in ACCENTS else beds
            a = int(max(0.0, when) * SR)
            b = min(n, a + len(sig))
            if b > a:
                target[a:b] += sig[:b - a]
                placed += 1
    rep["sfx_placed"] = placed
    rep["sfx_missing"] = sorted(set(missing))

    # ------------------------------------------------------------- ducking --
    if lines:
        music = np.asarray(P.duck(music, voice, depth_db=duck_db), dtype=np.float32)[:n]
        ambience = np.asarray(P.duck(ambience, voice, depth_db=duck_db * 0.45),
                              dtype=np.float32)[:n]
        music, ambience = _fit(music, n), _fit(ambience, n)

    if accents.any():
        accents = _limit(accents, float(mix_cfg.get("accent_ceiling", 0.55)))
        music = _duck_by(music, accents, accent_db)[:n]
        ambience = _duck_by(ambience, accents, accent_db * 0.7)[:n]
        beds = _duck_by(beds, accents, accent_db * 0.6)[:n]

    mixed = (voice * g_voice
             + music * g_music
             + ambience * g_amb
             + (beds + accents) * g_sfx)

    rep["duration"] = round(total_dur, 3)
    rep["peak"] = round(float(np.abs(mixed).max()) if len(mixed) else 0.0, 4)
    return P.soft_clip(mixed.astype(np.float32), 0.95).astype(np.float32)


def mix_to(board: dict, base_dir: str, total_dur: float | None, wav_path: str,
           *, seed: int = 0, stereo: bool = True, report: dict | None = None):
    """`build`, written to a WAV. Stereo by duplication — see `build`."""
    mono = build(board, base_dir, total_dur, seed=seed, report=report)
    data = np.stack([mono, mono], axis=1) if stereo else mono
    os.makedirs(os.path.dirname(os.path.abspath(wav_path)) or ".", exist_ok=True)
    P.write_wav(wav_path, data)
    return wav_path


# ==================================================================== delivery ==


def _delivery_target():
    """Read the numbers out of `style.json` rather than hard-coding them.

    The style declares its own delivery spec; duplicating it here is how the
    two drift apart when someone changes one of them.
    """
    lufs, tp = -14.0, -1.0
    try:
        with open(os.path.normpath(os.path.join(HERE, "..", "style.json"))) as f:
            v = (json.load(f).get("verify") or {})
        lufs = float(v.get("loudness_lufs", lufs))
        tp = float(v.get("true_peak_dbfs", tp))
    except Exception:
        pass
    return lufs, tp


def master_to(wav_path: str, out_path: str, **kw):
    """Deliver at -14 LUFS, true peak <= -1 dBTP.

    Straight through to the engine's `master`, which does the part that is
    genuinely hard. `out_path` is a **PCM WAV** master — the engine writes
    `pcm_s16le`, so handing it a `.m4a` produces an ffmpeg container error, not
    an AAC file. What it does instead is smarter: it encodes a throwaway AAC
    probe, measures the true peak that comes back *out of the codec*, and
    widens its guard band and re-runs if the delivered file broke the ceiling.
    Inter-sample peaks after lossy encoding are exactly the kind of thing that
    passes on the WAV and fails on the deliverable.

    Returns the engine's report: `{target_true_peak, true_peak, guard_db,
    within_target}`, where `true_peak` is what the AAC actually delivered.
    """
    lufs, tp = _delivery_target()
    kw.setdefault("lufs", lufs)
    kw.setdefault("tp", tp)
    if out_path.lower().endswith((".m4a", ".aac", ".mp3", ".mp4")):
        _warn(f"master_to writes a PCM master; {os.path.basename(out_path)} "
              "will contain WAV data despite its extension")
    target = float(kw["lufs"])
    tol = float(kw.pop("tolerance", 0.25))
    passes = int(kw.pop("loudness_tries", 3))

    # The engine iterates on true peak but takes loudnorm's word for the
    # loudness, which is the right trade for a documentary. It is not quite
    # enough here. A comedy mix has a much higher crest factor than a narrated
    # one — a `crash` or a `boing` is 20 dB of transient over the bed — so the
    # delivery limiter has real work to do, and every dB it shaves comes off
    # the integrated loudness that loudnorm had already committed to. Measured
    # on this style's own self-test that lands about 0.3-0.5 LU light: inside
    # spec, but sitting on the edge of it, and programme-dependent enough that
    # some other film would fall out.
    #
    # So: master, measure what came out, and if it missed, aim off by the
    # error and go again. Still the engine doing the work — this only chooses
    # what to ask it for.
    best = None
    aim = target
    for _ in range(max(1, passes)):
        kw["lufs"] = aim
        info = P.master(wav_path, out_path, **kw)
        try:
            got = P.measure_lufs(out_path)[0]
        except Exception:
            return info
        info = dict(info, lufs=round(got, 2), target_lufs=target,
                    aimed_at=round(aim, 2))
        err = target - got
        if best is None or abs(err) < abs(target - best[0]):
            best = (got, info, _read_master(out_path))
        if abs(err) <= tol:
            return info
        aim = min(target + 3.0, max(target - 3.0, aim + err))

    # Nothing beat the best pass, so put that one back on disk rather than
    # leaving whichever take happened to run last.
    if best is not None and best[2] is not None:
        P.write_wav(out_path, best[2])
        return best[1]
    return best[1] if best else {}


def _read_master(path):
    try:
        a, sr = P.read_wav(path)
        return np.asarray(a, dtype=np.float32)
    except Exception:
        return None


# ==================================================================== self-test ==
#
#   python3 audio.py [--out DIR] [--keep]
#
# Each check guards a failure that is otherwise silent in a finished film:
#
#   1. the sibling engine is really the engine (a self-import gives you a
#      module with your own name and none of the functions you wanted);
#   2. every effect makes a sound and none of them clip (a generator with a
#      sign error produces a valid, silent WAV);
#   3. a whole film masters to spec (a mix that peaks at 0.99 still masters,
#      it just arrives distorted);
#   4. a comic accent punches a hole in the bed, and only under itself;
#   5. the radio filter measurably band-limits (saturation after a bandpass
#      quietly puts the top end back — see `_radio`).


def _scratch_dir(argv):
    """Where the self-test writes.

    The brief for this module said `/tmp`. This sandbox refuses writes there,
    and the repository must stay clean, so it defaults to the user cache and
    takes `--out` or `$FILM_CREW_SCRATCH` if you want it somewhere else.
    """
    if "--out" in argv:
        return os.path.abspath(argv[argv.index("--out") + 1])
    env = os.environ.get("FILM_CREW_SCRATCH")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.expanduser("~"), ".cache", "film-crew",
                        "2d-selftest")


def _hf_fraction(x, split=4000.0):
    """Share of the signal's energy above `split`, in dB. The radio proof."""
    x = np.asarray(x, dtype=np.float64)
    if not len(x):
        return -np.inf
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / SR)
    total = float(spec.sum())
    if total <= 0:
        return -np.inf
    hi = float(spec[freqs > split].sum())
    return 10.0 * math.log10(max(hi / total, 1e-18))


def _fake_voice(dur, seed, out_path):
    """A synthetic 'recording' with real silence either side.

    The padding is the point: it proves `trim_silence` is running in both
    `line_times` and the mix, which is the one bug in this file that would
    make picture and sound drift apart over a long film.
    """
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = 130.0 + 22.0 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    buzz = sum(np.sin(k * ph) / k for k in range(1, 14))
    # syllables, so the ducker has something to follow
    syl = (0.5 + 0.5 * np.sin(2 * np.pi * 3.4 * t - 1.2)) ** 3
    x = (buzz * syl * 0.28).astype(np.float32)
    x = bandpass(x, 90.0, 7000.0, order=2)
    # Fricatives. Without them the test signal is a dark buzz with almost
    # nothing above 4 kHz, and a band-limiting proof against a source that is
    # already band-limited proves nothing. Real speech puts an /s/ at 5-9 kHz,
    # which is exactly the energy a radio channel is supposed to remove.
    for k in range(6):
        at = int((0.18 + 0.29 * k) * SR)
        if at + int(0.09 * SR) >= n:
            break
        m_ = int(0.09 * SR)
        hiss_ = rng.standard_normal(m_).astype(np.float32)
        hiss_ = highpass(hiss_, 4200.0, 3) * np.hanning(m_).astype(np.float32)
        x[at:at + m_] += hiss_ * 0.10
    x += rng.standard_normal(n).astype(np.float32) * 0.002
    pad = np.zeros(int(0.42 * SR), np.float32)
    sig = np.concatenate([pad, x, pad])
    P.write_wav(out_path, sig)
    return dur


#: A tiny board that exercises narration, a filter, music, ambience and an
#: effect. Rendered in a subprocess under a different hash seed to prove the
#: module is deterministic across *processes*, not merely within one.
_DIGEST_BOARD = {
    "timing": {"lead_in": 0.5, "tail": 1.0},
    "music": {"mood": "caper"},
    "ambience": "sirens",
    "narration": [{"id": "l1", "duration": 1.2, "gap_after": 0.3},
                  {"id": "l2", "duration": 1.0, "filter": "radio"}],
    "shots": [{"id": "s1", "at": "l1", "dur": 2.0,
               "sfx": [{"kind": "boing", "at": 0.4}, {"kind": "siren", "at": 1.0}]}],
}


def _digest():
    import hashlib
    x = build(_DIGEST_BOARD, ".", 6.0, seed=11)
    print(hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest())
    return 0


def _selftest(argv):
    ok = True
    scratch = _scratch_dir(argv)
    os.makedirs(scratch, exist_ok=True)
    print(f"scratch: {scratch}\n")

    # -- 1. the engine is the engine -------------------------------------
    print("[1] sibling engine")
    assert os.path.abspath(P.__file__) != os.path.abspath(__file__), \
        "self-import: loaded this file instead of the engine"
    assert os.path.dirname(os.path.abspath(P.__file__)) == ENGINE
    assert P.SR == SR and hasattr(P, "master") and hasattr(P, "Track")
    assert len(getattr(P, "SFX", {})) > 10, "engine SFX library did not load"
    print(f"    engine : {P.__file__}")
    print(f"    score  : {S.__file__}")
    print(f"    self   : {os.path.abspath(__file__)}")
    print(f"    SR={SR}  engine SFX={len(P.SFX)}  total SFX={len(SFX)}  "
          f"moods={len(MOODS)} (+{len(CHASE_MOODS)} chase)\n")

    # -- 2. every effect ---------------------------------------------------
    print("[2] sound effects")
    print(f"    {'name':<16} {'dur':>6} {'peak':>7} {'rms':>7} {'dBFS':>7}  origin")
    silent, clipped = [], []
    for name in sorted(SFX):
        sig = np.asarray(sfx(name, seed=7), dtype=np.float32).reshape(-1)
        peak = float(np.abs(sig).max()) if len(sig) else 0.0
        rms = _rms(sig)
        dbfs = 20 * math.log10(peak) if peak > 0 else -999
        origin = "chase" if name in _NEW else "paper"
        print(f"    {name:<16} {len(sig)/SR:6.2f} {peak:7.4f} {rms:7.4f} "
              f"{dbfs:7.1f}  {origin}")
        if peak <= 1e-3:
            silent.append(name)
        if peak > 1.0:
            clipped.append(name)
        P.write_wav(os.path.join(scratch, f"sfx_{name}.wav"), sig)
    if silent:
        ok = False
        print(f"    FAIL silent: {silent}")
    if clipped:
        ok = False
        print(f"    FAIL clipping: {clipped}")
    if not silent and not clipped:
        print(f"    OK — {len(SFX)} effects, none silent, none over 0 dBFS")

    # The two effects that claim to model something get checked against it.
    # A rotor whose thump is not at the blade-pass rate is a hairdryer, and a
    # siren that does not change pitch as it goes past is a car alarm.
    def _mod_rate(x, lo=3.0, hi=40.0):
        env = P.envelope_follow(x, 1.0, 8.0)
        env = env - env.mean()
        spec_ = np.abs(np.fft.rfft(env)) ** 2
        f_ = np.fft.rfftfreq(len(env), 1.0 / SR)
        band = (f_ > lo) & (f_ < hi)
        return float(f_[band][spec_[band].argmax()])

    for spin, want in ((0.7, 7.7), (1.0, 11.0), (1.4, 15.4)):
        got = _mod_rate(sfx_rotor(3.0, 1, spin=spin))
        print(f"    rotor spin={spin:.1f}: blade-pass modulation {got:5.2f} Hz "
              f"(expected {want:.1f})")
        if abs(got - want) > 0.6:
            ok = False
            print("    FAIL rotor blade rate is wrong")

    def _centroid(y):
        sp_ = np.abs(np.fft.rfft(y)) ** 2
        f_ = np.fft.rfftfreq(len(y), 1.0 / SR)
        return float((sp_ * f_).sum() / max(sp_.sum(), 1e-18))

    d = sfx_siren(4.0, 1, doppler=0.9)
    h = len(d) // 2
    q = int(0.5 * SR)
    near, far = _rms(d[h - q // 2:h + q // 2]), _rms(d[:q])
    drop = _centroid(d[h:]) / max(_centroid(d[:h]), 1e-9) - 1.0
    print(f"    siren doppler: {20 * math.log10(near / max(far, 1e-9)):+.1f} dB "
          f"louder at closest approach, pitch {drop * 100:+.1f}% after it")
    if near < far * 2 or drop > -0.05:
        ok = False
        print("    FAIL the siren does not pass by")
    print()

    # -- 3. a whole film ---------------------------------------------------
    print("[3] full mix and delivery")
    for i, d in ((1, 1.9), (2, 2.4), (3, 1.6)):
        _fake_voice(d, 100 + i, os.path.join(scratch, f"l{i}.wav"))

    board = {
        "timing": {"lead_in": 0.6, "tail": 1.4},
        "music": {"mood": "chase", "gain": 1.0},
        "ambience": "city",
        "narration": [
            {"id": "l1", "audio": "l1.wav", "gap_after": 0.4},
            {"id": "l2", "audio": "l2.wav", "gap_after": 0.5, "filter": "radio"},
            {"id": "l3", "audio": "l3.wav", "gap_after": 0.6},
        ],
        "shots": [
            {"id": "s1", "at": "l1", "dur": 3.0,
             "sfx": [{"kind": "siren", "at": 0.2, "gain": 0.8, "doppler": 0.9},
                     {"kind": "tyres", "at": 1.4}]},
            {"id": "s2", "at": "l2", "dur": 3.0,
             "sfx": [{"kind": "rotor", "at": 0.0, "gain": 0.6},
                     {"kind": "boing", "at": 1.1, "gain": 1.2},
                     {"kind": "helicopter_blades_of_doom", "at": 2.0}]},
            {"id": "s3", "at": "l3.end", "dur": 2.5,
             "sfx": [{"kind": "crash", "at": 0.1}, {"kind": "pop", "at": 1.0},
                     {"kind": "slide_whistle", "at": 1.3}]},
        ],
    }

    t1 = line_times(board, scratch)
    t2 = line_times(board, scratch)
    assert t1 == t2, "line_times is not deterministic"
    starts = [v[0] for v in t1.values()]
    assert starts == sorted(starts), "lines overlap"
    for lid, (a, b) in t1.items():
        assert b > a, f"line {lid} has no length"
        # 0.42 s of silence was padded either side of a ~2 s read; if trimming
        # were not happening the measured line would be ~0.84 s longer
        assert b - a < 2.9, f"line {lid} was not trimmed ({b - a:.2f}s)"
    print("    line_times:", {k: (round(a, 2), round(b, 2)) for k, (a, b) in t1.items()})

    dur = film_duration(board, scratch)
    rep = {}
    mono = build(board, scratch, dur, seed=3, report=rep)
    assert mono.ndim == 1 and mono.dtype == np.float32
    assert len(mono) == int(dur * SR)
    peak = float(np.abs(mono).max())
    print(f"    duration {dur:.2f}s  peak {peak:.3f}  rms {_rms(mono):.4f}  {rep}")
    assert 0.05 < peak <= 1.0, f"mix peak {peak} is implausible"
    assert rep["sfx_missing"] == ["helicopter_blades_of_doom"], \
        f"unknown-effect reporting is wrong: {rep['sfx_missing']}"

    again = build(board, scratch, dur, seed=3)
    assert np.array_equal(mono, again), "build is not deterministic within a process"

    # And across processes. Python salts string hashing per run, so anything
    # seeded off `hash("l2")` renders differently every time while looking
    # perfectly deterministic to the check above.
    digests = set()
    for hs in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=hs)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--digest"],
                           capture_output=True, text=True, env=env,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        digests.add(r.stdout.strip())
    if len(digests) != 1 or not next(iter(digests)):
        ok = False
        print(f"    FAIL not deterministic across processes: {digests}")
    else:
        print(f"    deterministic across hash seeds: {next(iter(digests))[:16]}")

    wav = os.path.join(scratch, "mix.wav")
    mix_to(board, scratch, dur, wav, seed=3)
    master = os.path.join(scratch, "master.wav")
    info = master_to(wav, master)
    i_lufs, i_tp = P.measure_lufs(master)
    delivered_tp = info.get("true_peak")
    print(f"    master : {i_lufs:+.2f} LUFS   true peak {i_tp:+.2f} dBFS   "
          f"(aimed at {info.get('aimed_at')})")
    print(f"    as AAC : true peak {delivered_tp:+.2f} dBFS   "
          f"guard {info.get('guard_db')} dB   within target "
          f"{info.get('within_target')}")
    if not (abs(i_lufs + 14.0) <= 0.5):
        ok = False
        print(f"    FAIL loudness {i_lufs:+.2f} is not -14 +/- 0.5")
    for label, val in (("master", i_tp), ("delivered AAC", delivered_tp)):
        if val is None or val > -1.0 + 1e-6:
            ok = False
            print(f"    FAIL {label} true peak {val} exceeds -1.0 dBFS")
    if ok:
        print("    OK — on spec\n")

    # -- 4. a wordless film ------------------------------------------------
    print("[4] wordless board")
    silent_board = {"music": {"mood": "romp"}, "ambience": "sirens",
                    "shots": [{"id": "s1", "at": 0.5, "dur": 4.0,
                               "sfx": [{"kind": "horn", "at": 0.3},
                                       {"kind": "skid", "at": 1.9}]}]}
    assert line_times(silent_board, scratch) == {}
    w = build(silent_board, scratch, 6.0, seed=1)
    assert len(w) == int(6.0 * SR) and float(np.abs(w).max()) > 0.05
    print(f"    no narration: {len(w)/SR:.1f}s, peak {float(np.abs(w).max()):.3f} — "
          "music and effects carry it\n")

    # -- 5. comedy ducking ---------------------------------------------------
    print("[5] ducking")
    # A flat, continuous bed, so the measurement says something about the
    # ducker rather than about where the cues happened to fall.
    steady = (np.random.default_rng(4).standard_normal(int(6.0 * SR))
              .astype(np.float32) * 0.05)
    hit = np.zeros(len(steady), np.float32)
    at = int(3.0 * SR)
    b_ = sfx("boing", seed=1)
    hit[at:at + len(b_)] += b_
    ducked = _duck_by(steady, hit, -5.0)

    def win(x, t0, t1):
        return _rms(x[int(t0 * SR):int(t1 * SR)])

    under = 20 * math.log10(max(win(ducked, 3.0, 3.4), 1e-12)
                            / max(win(steady, 3.0, 3.4), 1e-12))
    away = 20 * math.log10(max(win(ducked, 0.5, 1.0), 1e-12)
                           / max(win(steady, 0.5, 1.0), 1e-12))
    print(f"    bed under the accent : {under:+.2f} dB")
    print(f"    bed elsewhere        : {away:+.2f} dB")
    if under > -3.0:
        ok = False
        print(f"    FAIL the accent did not open a hole in the bed ({under:+.2f} dB)")
    if abs(away) > 0.2:
        ok = False
        print(f"    FAIL the accent ducked the whole film ({away:+.2f} dB)")

    # ...and the accent itself must be untouched by the *narration* ducker,
    # which is the whole reason it is summed after that stage. Both renders
    # below are effects-only, with the effects at identical times: the sole
    # difference is whether anyone is talking over them.
    only_sfx = {"voice": 0.0, "music": 0.0, "ambience": 0.0}
    talking = dict(board, mix=only_sfx)
    # the same shots, but anchored to numbers, so removing the narration does
    # not also move every effect to zero
    fixed = []
    for sh in board["shots"]:
        sh = dict(sh)
        sh["at"] = round(resolve_time(t1, sh.get("at"), 0.0), 4)
        fixed.append(sh)
    wordless = {k: v for k, v in board.items() if k != "narration"}
    wordless = dict(wordless, shots=fixed, mix=only_sfx)

    p_with = float(np.abs(build(talking, scratch, dur, seed=3)).max())
    p_without = float(np.abs(build(wordless, scratch, dur, seed=3)).max())
    print(f"    effects peak with narration {p_with:.4f}, without {p_without:.4f}")
    if p_with < p_without * 0.99:
        ok = False
        print("    FAIL the narration ducker is eating the effects")
    print()

    # -- 6. the radio filter ------------------------------------------------
    print("[6] radio filter, spectral proof")
    raw = P.trim_silence(_load_audio(os.path.join(scratch, "l2.wav")))
    rows = []
    for kind in ("none", "radio", "tannoy", "phone"):
        y = voice_filter(raw, kind, seed=4)
        assert len(y) == len(raw), f"{kind} changed the length of the line"
        rows.append((kind, _hf_fraction(raw), _hf_fraction(y),
                     20 * math.log10(max(_rms(y), 1e-9) / max(_rms(raw), 1e-9))))
    print(f"    {'filter':<8} {'>4kHz before':>13} {'>4kHz after':>12} "
          f"{'drop':>8} {'level':>8}")
    for kind, before, after, lvl in rows:
        drop = before - after
        print(f"    {kind:<8} {before:12.1f}dB {after:11.1f}dB "
              f"{drop:7.1f}dB {lvl:+7.2f}dB")
        if kind == "none":
            assert abs(drop) < 1e-9, "'none' must not touch the signal"
            continue
        if drop < 18.0:
            ok = False
            print(f"    FAIL {kind} only removed {drop:.1f} dB above 4 kHz")
        if abs(lvl) > 1.5:
            ok = False
            print(f"    FAIL {kind} shifted the level by {lvl:+.2f} dB")
    for kind, before, after, _ in rows:
        P.write_wav(os.path.join(scratch, f"voice_{kind}.wav"),
                    voice_filter(raw, kind, seed=4))
    print()

    if WARNINGS:
        print("warnings raised (expected: one unknown effect):")
        for w_ in WARNINGS:
            print("   -", w_)
        print()

    if "--keep" not in argv:
        shutil.rmtree(scratch, ignore_errors=True)
        print(f"cleaned up {scratch}")

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--digest" in sys.argv[1:]:
        sys.exit(_digest())
    sys.exit(_selftest(sys.argv[1:]))
