"""Storyboard-driven renderer for archival-collage explainer videos.

    python3 render.py storyboard.json [--preview] [--frame 4.2] [--sheet]

Design notes
------------
* Positions are authored in **design space** (the output resolution). The board
  is rendered slightly larger so the camera always has room to drift.
* Narration is synthesised first and *measured*; beat times may refer to a line
  by id (``"l3"``, ``"l3+0.4"``, ``"l3.end-0.2"``), so visuals stay locked to
  speech even after the script is reworded.
* Static elements are baked into the background once. Only animating elements
  are recomposited per frame.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

import numpy as np
from PIL import Image

import audio as A
import collage as C
import illustrations as I
import motion as M
import paper
from paper import PALETTE

OVER = 1.34  # board is this much larger than the output, to allow camera travel


# ------------------------------------------------------------------ config ----


def hex_rgb(s):
    if isinstance(s, (list, tuple)):
        return tuple(int(v) for v in s[:3])
    s = s.lstrip("#")
    return tuple(int(s[i: i + 2], 16) for i in (0, 2, 4))


class Timeline:
    """Resolves narration line ids to absolute seconds."""

    def __init__(self):
        self.lines = {}   # id -> (start, end)
        self.duration = 0.0

    def resolve(self, spec, default=0.0):
        if spec is None:
            return default
        if isinstance(spec, (int, float)):
            return float(spec)
        s = str(spec).strip()
        for op in ("+", "-"):
            if op in s[1:]:
                i = s.rindex(op)
                base, delta = s[:i].strip(), float(s[i:].strip())
                return self._point(base) + delta
        return self._point(s)

    def _point(self, name):
        if name.endswith(".end"):
            key = name[:-4]
            if key not in self.lines:
                raise KeyError(f"unknown narration line '{key}'")
            return self.lines[key][1]
        if name in self.lines:
            return self.lines[name][0]
        try:
            return float(name)
        except ValueError:
            raise KeyError(f"unknown time reference '{name}'")


# --------------------------------------------------------------- narration ----


def timeline_path(out_path):
    """Where the resolved timeline for a given film lives."""
    return os.path.splitext(out_path)[0] + ".timeline.json"


def write_timeline(out_path, tl: Timeline, sb):
    """Record the exact times the voice was laid down at.

    Consumers -- captions above all -- need the times the renderer *used*, not
    the ones they would compute from the source clips, which are longer than
    what plays because they still carry the recorder's leading and trailing
    silence.
    """
    doc = {
        "schema": 1,
        "duration": round(tl.duration, 3),
        "lead_in": float(sb.get("timing", {}).get("lead_in", 0.6)),
        "tail": float(sb.get("timing", {}).get("tail", 1.2)),
        "lines": [{"id": lid, "start": round(a, 3), "end": round(b, 3)}
                  for lid, (a, b) in tl.lines.items()],
    }
    path = timeline_path(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
    return path


def build_narration(sb, workdir, tl: Timeline, sb_dir: str = "."):
    """Measure every narration clip and lay out the speech track.

    Narration audio is an **input**, not something this skill produces. Each
    line either points at an audio file with `audio`, or declares a bare
    `duration` to reserve silent time so a board can be previewed before the
    narration exists.
    """
    lead_in = float(sb.get("timing", {}).get("lead_in", 0.6))

    cursor = lead_in
    pieces = []
    supplied = 0
    placeholder = 0
    for idx, ln in enumerate(sb.get("narration", [])):
        lid = ln.get("id", f"l{idx + 1}")
        src = ln.get("audio")
        if src:
            path = src if os.path.isabs(src) else os.path.join(sb_dir, src)
            a = A.trim_silence(A.load_narration(path))
            supplied += 1
        else:
            dur = float(ln.get("duration", 0.0))
            if dur <= 0:
                raise ValueError(
                    f"narration line '{lid}' has neither `audio` nor `duration`.\n"
                    "    Point `audio` at a clip from the `voice-booth` skill, or "
                    "set `duration` to block the timing out first."
                )
            a = np.zeros(int(dur * A.SR), dtype=np.float32)
            placeholder += 1
        tl.lines[lid] = (cursor, cursor + len(a) / A.SR)
        pieces.append((cursor, a))
        cursor += len(a) / A.SR + float(ln.get("gap_after", 0.55))

    if supplied:
        print(f"  narration: {supplied} supplied clip(s)", flush=True)
    if placeholder:
        print(f"  ! {placeholder} line(s) are silent placeholders — timing only, "
              "no voice. Generate narration with the `voice-booth` skill.",
              flush=True)

    tail = float(sb.get("timing", {}).get("tail", 1.2))
    total = max(cursor + tail, float(sb.get("timing", {}).get("min_duration", 0.0)))
    tl.duration = total

    track = np.zeros(int(total * A.SR) + 1, dtype=np.float32)
    for at, a in pieces:
        i = int(at * A.SR)
        j = min(len(track), i + len(a))
        track[i:j] += a[: j - i]
    return track


# -------------------------------------------------------------------- music ----

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
}


def build_music_from_file(m, duration, sb_dir="."):
    """Use a supplied audio file as the bed instead of synthesising one.

    The rest of the skill is deliberately asset-free, but a bed is the one
    element a user may already own and be licensed for. The file is loaded,
    crossfade-looped to the exact runtime, high-passed to keep it out of the
    narration's way, and normalised — so `mix.music` means the same thing it
    means for a synthesised bed.
    """
    path = m["file"]
    if not os.path.isabs(path):
        path = os.path.join(sb_dir, path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"music.file not found: {path}")
    src = A.load_audio(path)
    n = int(duration * A.SR) + 1
    if len(src) < n:
        print(f"· looping music bed ({len(src) / A.SR:.1f}s -> {duration:.1f}s)", flush=True)
    out = A.loop_to(src, n, crossfade=float(m.get("crossfade", 2.5)))
    hp = float(m.get("highpass", 0.0))
    if hp > 0:
        out = A._hp(out, hp)
    peak = float(np.abs(out).max())
    if peak > 0:
        out = out * (0.9 / peak)
    out = out * float(m.get("gain", 1.0))
    f = min(int(float(m.get("fade", 2.0)) * A.SR), n // 4)
    if f > 1:
        out[:f] *= np.linspace(0, 1, f)
        out[-f:] *= np.linspace(1, 0, f)
    peak = float(np.abs(out).max())
    if peak > 0.95:
        out *= 0.95 / peak
    return out.astype(np.float32)


def build_music(sb, duration, tl, sb_dir="."):
    """Synthesise an original bed. Three moods, all built from the same parts."""
    m = sb.get("music", {})
    if m.get("enabled", True) is False:
        return np.zeros(int(duration * A.SR) + 1, dtype=np.float32)

    if m.get("file"):
        return build_music_from_file(m, duration, sb_dir)

    mood = m.get("mood", "music_box")
    root = float(m.get("root", 65.41))          # C2
    gain = float(m.get("gain", 1.0))
    default_scale = {"music_box": "major", "memorial": "minor",
                     "crime": "minor"}.get(mood, "dorian")
    scale = SCALES.get(m.get("scale", default_scale))
    rng = np.random.default_rng(int(m.get("seed", 5)))

    tr = A.Track(duration + 2.0)

    # sustained floor
    if mood == "music_box":
        tr.add(A.warm_pad([root * 2, root * 3, root * 4], duration + 1.5), 0.0, 0.55 * gain)
        tr.add(A.low_drone(root, duration + 1.5), 0.0, 0.40 * gain)
    elif mood == "memorial":
        # heavier floor, less air — the room should feel low and still
        tr.add(A.low_drone(root, duration + 1.5), 0.0, 1.00 * gain)
        tr.add(A.low_drone(root * 1.5, duration + 1.5), 0.0, 0.30 * gain)
        tr.add(A.warm_pad([root * 4, root * 6], duration + 1.5), 0.0, 0.22 * gain)
    elif mood == "crime":
        # Sub floor plus a little body. Gains here were fitted against the
        # reference's music-only windows — see reference/audio-style.md.
        tr.add(A.low_drone(root, duration + 1.5), 0.0, 0.60 * gain)
        tr.add(A.warm_pad([root * 4, root * 6, root * 7], duration + 1.5), 0.0, 0.30 * gain)
    else:
        tr.add(A.low_drone(root, duration + 1.5), 0.0, 0.85 * gain)
        tr.add(A.warm_pad([root * 3, root * 4.5], duration + 1.5), 0.0, 0.30 * gain)

    # melodic figure
    bpm = float(m.get("bpm", 68))
    beat = 60.0 / bpm
    step = {"music_box": beat / 2, "memorial": beat * 2,
            "crime": beat / 2}.get(mood, beat)
    base_midi = float(m.get("melody_root", 72))
    # a falling line is the elegiac gesture; a rising one sounds hopeful
    FALL = [4, 3, 2, 1, 0, 4, 2, 1, 0, -3, -1, 0]
    # a short cell that will not resolve — the procedural motif
    CELL = [0, 3, 4, 3, 0, 3, 4, 6]
    t = 0.0
    i = 0
    while t < duration - 0.4:
        deg = scale[(i * 2 + (i // 4)) % len(scale)]
        octv = 12 * (1 if (i % 8) in (3, 6) else 0)
        f = A.midi_hz(base_midi + deg + octv)
        vel = 0.85 if i % 4 == 0 else 0.5
        if mood == "music_box":
            tr.add(A.celesta(f, 1.9), t, vel * 0.85 * gain)
            if i % 4 == 2:
                tr.add(A.celesta(A.midi_hz(base_midi + deg + 7), 1.5), t + step * 0.5, 0.30 * gain)
        elif mood == "memorial":
            idx = FALL[i % len(FALL)]
            note = base_midi + scale[idx % len(scale)] + (-12 if idx < 0 else 0)
            tr.add(A.bowed(A.midi_hz(note), step * 1.45, seed=i), t,
                   (0.72 if i % 3 == 0 else 0.46) * gain)
            if i % 4 == 0:                       # remembrance, not a horror sting
                tr.add(A.toll(root, step * 2.2), t, 0.45 * gain)
        elif mood == "crime":
            # The eighth-note pulse is the whole engine of the mood. It sits at
            # root*4 so its fundamental lands in the 80-250 Hz *body* register
            # rather than the sub — that is where the reference keeps its weight.
            on_beat = (i % 2 == 0)
            hum = float(rng.normal(0, 0.005))    # a perfect grid sounds like a drum machine
            vv = float(rng.uniform(0.9, 1.1))
            tr.add(A.pulse_bass(root * 4, step * 0.92), max(0.0, t + hum),
                   (0.80 if on_beat else 0.50) * vv * gain)
            tr.add(A.pulse_bass(root * 2, step * 0.80), max(0.0, t + hum),
                   (0.41 if on_beat else 0.23) * vv * gain)
            if i % 8 == 0:                       # octave drop marks the bar
                tr.add(A.pulse_bass(root * 2, step * 1.6), t, 0.50 * gain)
            # the unresolved motif, carrying the midrange
            if i % 4 == 2:
                note = base_midi + scale[CELL[(i // 4) % len(CELL)] % len(scale)]
                tr.add(A.pluck(A.midi_hz(note), step * 2.4, seed=i), t, 2.70 * gain)
                tr.add(A.pluck(A.midi_hz(note - 12), step * 2.0, seed=i + 3), t, 1.40 * gain)
            if i % 4 == 0:
                note = base_midi + scale[CELL[(i // 4) % len(CELL)] % len(scale)] - 12
                tr.add(A.pluck(A.midi_hz(note), step * 1.7, seed=i + 11), t, 1.10 * gain)
            if i % 16 == 9:
                note = base_midi + scale[CELL[(i // 4) % len(CELL)] % len(scale)] + 12
                tr.add(A.pluck(A.midi_hz(note), step * 1.6, seed=i + 7), t, 0.85 * gain)
        else:
            if i % 2 == 0:
                tr.add(A.celesta(f, 2.4), t, vel * 0.55 * gain)
        t += step
        i += 1

    # the ticking layer — a clock the investigation is running against
    if mood == "crime" and m.get("percussion", True) is not False:
        sub = step / 2
        t = 0.0
        k = 0
        while t < duration - 0.2:
            if k % 4 != 3:                       # a gap keeps it from sounding mechanical
                jit = float(rng.normal(0, 0.006))
                tr.add(A.tick(seed=k), max(0.0, t + jit),
                       (3.06 if k % 4 == 0 else 1.62)
                       * float(rng.uniform(0.86, 1.14)) * gain)
            t += sub
            k += 1

    # light pulse
    if m.get("percussion", True) and mood != "crime":
        t = 0.0
        k = 0
        while t < duration:
            tr.add(A.shaker(seed=k), t, (0.5 if k % 2 else 0.85) * 0.55 * gain)
            t += beat
            k += 1

    out = tr.array()[:, 0]
    n = int(duration * A.SR) + 1
    out = out[:n] if len(out) >= n else np.pad(out, (0, n - len(out)))
    # gentle fade in/out
    f = int(1.4 * A.SR)
    out[:f] *= np.linspace(0, 1, f)
    out[-f:] *= np.linspace(1, 0, f)
    # never hand back a bed that is already clipping — a dense mood can stack
    # past 1.0, and scaling here is uniform so it cannot change the timbre
    peak = float(np.abs(out).max())
    if peak > 0.95:
        out *= 0.95 / peak
    return out


# ------------------------------------------------------------------ assets ----


class Element:
    """A renderable with an entrance, an optional exit, and a cached base image."""

    def __init__(self, spec, tl, S, seedbase=0):
        self.spec = spec
        self.type = spec["type"]
        self.S = S
        self.seed = int(spec.get("seed", seedbase))
        ein = spec.get("in", {}) or {}
        eout = spec.get("out", {}) or {}
        self.id = spec.get("id")
        self.t_in = tl.resolve(ein.get("t", 0.0))
        self.d_in = float(ein.get("dur", 0.45))
        self.anim = ein.get("anim", "stamp")
        self.t_out = tl.resolve(eout.get("t"), None) if eout.get("t") is not None else None
        self.d_out = float(eout.get("dur", 0.40))
        self.rotate = float(spec.get("rotate", 0.0))
        self.sfx = spec.get("sfx")
        self.sfx_gain = float(spec.get("sfx_gain", 1.0))
        self.z = int(spec.get("z", 0))
        drift = spec.get("drift") or {}
        self.drift_x = float(drift.get("x", 0.0))
        self.drift_y = float(drift.get("y", 0.0))
        self.drift_from = tl.resolve(drift.get("from"), None) if drift.get("from") is not None else None
        self.drift_to = tl.resolve(drift.get("to"), None) if drift.get("to") is not None else None
        self.has_drift = bool(drift)
        # `sway`: a slow, endless back-and-forth. `drift` travels from A to B
        # and then stops dead, so an element that outlives its drift becomes a
        # frozen picture -- exactly what a long narration beat exposes. Sway
        # never settles, so a held image keeps breathing without ever going
        # anywhere. Phase is measured from the element's own entry so it
        # starts at zero offset and eases out of its arrival rather than
        # popping into the middle of a swing.
        sway = spec.get("sway") or {}
        self.sway_x = float(sway.get("x", 0.0))
        self.sway_y = float(sway.get("y", 0.0))
        self.sway_scale = float(sway.get("scale", 0.0))
        self.sway_period = max(1.0, float(sway.get("period", 11.0)))
        self.sway_ramp = max(0.05, float(sway.get("ramp", 1.2)))
        self.has_sway = bool(sway) and (self.sway_x or self.sway_y
                                        or self.sway_scale)
        self.base = None
        self._cache = {}
        self.art_pad = 0
        self.art = None
        self._sh = {}
        # depth: how high the scrap rests, how high it is thrown from, and how
        # strongly it reacts to the camera move
        self.elevation = float(spec.get("elevation", 0.28))
        self.fly_h = float((spec.get("in", {}) or {}).get("height", 1.35))
        # nearer layers react more to the camera; authored `parallax` wins
        self.parallax = float(spec.get("parallax", min(0.5, self.z / 46.0)))
        self.float_amp = float(spec.get("float", 1.0))
        self.sh_pad = 0
        self.shadow = bool(spec.get("shadow", True))
        # `at` is the element CENTRE in design space, so shadow padding never
        # shifts a layout.
        self.pos = [v * S for v in spec.get("at", [960, 540])]

    def build_shadow(self, S):
        """Fix the shadow canvas once, sized for the highest this scrap flies."""
        if self.art is None:
            return
        max_e = max(self.elevation, self.fly_h if self.anim == "fly" else 0.0)
        self.bb = max(3.0, 9.0 * S)
        self.bd = max(3.0, 8.0 * S)
        self.sh_pad = int(self.bb * (1 + 2.8 * max_e) * 3 + self.bd * (1 + 5.5 * max_e)) // 2 + 2

    def shadowed(self, elev):
        """Elevation-quantised shadow cache — smooth enough at 30 fps, cheap."""
        if not self.shadow or self.art is None:
            return self.art
        key = round(max(0.0, elev) * 24) / 24.0
        img = self._sh.get(key)
        if img is None:
            img = paper.elevated_shadow(self.art, key, pad=self.sh_pad,
                                        base_blur=self.bb, base_dist=self.bd)
            self._sh[key] = img
        return img

    def anchor(self, mx, my):
        """Shift design-space coords into the centred region of the board."""
        self.pos = [self.pos[0] + mx, self.pos[1] + my]

    # -- geometry -------------------------------------------------------
    def visible(self, t):
        if t < self.t_in - 1e-6:
            return False
        if self.t_out is not None and t > self.t_out + self.d_out:
            return False
        return True

    def progress(self, t):
        return M.clamp((t - self.t_in) / self.d_in) if self.d_in > 0 else 1.0

    def out_progress(self, t):
        if self.t_out is None or t < self.t_out:
            return 0.0
        return M.clamp((t - self.t_out) / self.d_out) if self.d_out > 0 else 1.0


#: Set in the parent just before forking; the workers inherit it by copy.
_COMPOSE = None


def _compose_at(t):
    """Render one frame in a worker. Module level so `imap` can reach it."""
    return _COMPOSE(t).tobytes()


def make_base(spec, S, accent, seed):
    """Build the un-animated artwork for an element spec."""
    ty = spec["type"]
    sc = lambda v, d=0: int(float(spec.get(v, d)) * S)  # noqa: E731

    if ty == "chip":
        return C.label_chip(
            spec["text"], size=sc("size", 54),
            kind=spec.get("font", "display"),
            weight=float(spec.get("weight", 900)),
            width=float(spec.get("width", 74)),
            tracking=float(spec.get("tracking", 2.0)) * S,
            fg=hex_rgb(spec.get("color", PALETTE["ink"])),
            bg=hex_rgb(spec.get("bg", (238, 232, 210))),
            pad=(sc("pad_x", 34), sc("pad_y", 20)),
            seed=seed, torn=bool(spec.get("torn", False)),
        )
    if ty == "stamp":
        return C.stamp(
            spec["text"], size=sc("size", 44),
            fg=hex_rgb(spec.get("color", (228, 220, 196))),
            bg=hex_rgb(spec.get("bg", (52, 50, 40))),
            tracking=float(spec.get("tracking", 3.0)) * S,
            pad=(sc("pad_x", 30), sc("pad_y", 16)), seed=seed,
        )
    if ty == "typed":
        return C.typed_line(spec["text"], size=sc("size", 30),
                            fg=hex_rgb(spec.get("color", PALETTE["ink_soft"])), seed=seed)
    if ty == "card":
        fold = spec.get("fold")
        return paper.torn_card(sc("w", 600), sc("h", 320), seed=seed,
                               color=hex_rgb(spec.get("color", PALETTE["card"])),
                               depth=float(spec.get("depth", 0.035)),
                               sides=tuple(spec.get("sides", (1, 1, 1, 1))),
                               core=None if spec.get("core") is None else float(spec["core"]) * S,
                               fold=None if fold is None else float(fold),
                               fold_strength=float(spec.get("fold_strength", 1.0)))
    if ty == "tape":
        return paper.tape_strip(sc("w", 230), sc("h", 60), seed=seed,
                                color=hex_rgb(spec.get("color", PALETTE["tape"])))
    if ty == "pin":
        return paper.push_pin(sc("size", 60), color=hex_rgb(spec.get("color", accent)), seed=seed)
    if ty == "ring":
        return paper.coffee_ring(sc("size", 380), seed=seed, alpha=int(spec.get("alpha", 42)))
    if ty == "art":
        return make_art(spec, S, seed)
    raise ValueError(f"unknown element type: {ty}")


def make_art(spec, S, seed):
    """Named procedural illustration.

    Most illustrations are sized by an explicit `w`/`h` pair rather than by
    `size`, because their natural proportions are not square -- a parachute is
    taller than it is wide, a timeline far wider than tall. The compiler,
    however, fits art to a layout slot and expresses that fit as `size`. Left
    unconnected, twenty-three of the twenty-nine illustrations quietly ignored
    the slot and drew at their hard-coded defaults, so the layout logic had no
    effect on them and tall art ran off the bottom of the frame.

    `sc` therefore falls back to scaling the illustration's own default box so
    that its longest side is `size`, which honours the slot while preserving
    the proportions the drawing was designed with. An explicit `w`/`h` in the
    spec still wins.
    """
    name = spec["name"]
    want = spec.get("size")

    def sc(v, d, _other=None):
        if v in spec:
            return int(float(spec[v]) * S)
        if want and _other:
            longest = float(max(d, _other))
            if longest > 0:
                return int(float(want) * (float(d) / longest) * S)
        return int(float(d) * S)
    if name == "mouse":
        img = I.mouse(sc("size", 240), seed=seed, facing=int(spec.get("facing", 1)))
    elif name == "lantern":
        img = I.lantern(sc("size", 280), seed=seed, glow=float(spec.get("glow", 0.0)))
    elif name == "moon":
        img = I.moon(sc("size", 320), seed=seed)
    elif name == "star":
        img = I.star(sc("size", 60), seed=seed)
    elif name == "hill":
        img = I.hill(sc("w", 1200, 420), sc("h", 420, 1200), seed=seed)
    elif name == "snow":
        return I.snow_layer(sc("w", 800, 500), sc("h", 500, 800), int(spec.get("count", 90)), seed)
    elif name == "halo":
        return I.glow_halo(sc("size", 400), float(spec.get("intensity", 1.0)))
    elif name == "hotel":
        img = I.grand_hotel(sc("w", 900, 520), sc("h", 520, 900), seed=seed)
    elif name == "boat":
        img = I.boat(sc("w", 260, 130), sc("h", 130, 260), seed=seed)
    elif name == "sea":
        img = I.sea(sc("w", 1400, 300), sc("h", 300, 1400), seed=seed)
    elif name == "clock":
        img = I.clock(sc("size", 300), seed=seed,
                      hours=float(spec.get("hours", 10.0)),
                      minutes=float(spec.get("minutes", 10.0)))
    elif name == "candle":
        img = I.candle(sc("h", 260, 119), seed=seed, lit=float(spec.get("lit", 1.0)))
    elif name == "map":
        markers = [tuple(m) for m in spec.get("markers", [])]
        img = I.region_map(sc("w", 900, 640), sc("h", 640, 900), seed=seed,
                           markers=markers, highlight=int(spec.get("highlight", -1)),
                           region=spec.get("region", "generic"))
    elif name == "thread":
        pts = [tuple(p) for p in spec.get("points", [])]
        img = I.route_thread(sc("w", 900, 640), sc("h", 640, 900), seed=seed, points=pts,
                             progress=float(spec.get("progress", 1.0)),
                             style=spec.get("style", "taut"),
                             pins=bool(spec.get("pins", True)))
    elif name == "timeline":
        ticks = [tuple(pt) for pt in spec.get("ticks", [])]
        img = I.timeline_chart(sc("w", 220, 860), sc("h", 860, 220), seed=seed,
                               ticks=ticks, progress=float(spec.get("progress", 1.0)))
    elif name == "car":
        img = I.car(sc("w", 260, 130), sc("h", 130, 260), seed=seed, kind=spec.get("kind", "sedan"))
    elif name == "figure":
        img = I.figure(sc("h", 260, 119), seed=seed, kind=spec.get("kind", "civilian"))
    elif name == "crowd":
        img = I.crowd(sc("w", 1200, 480), sc("h", 480, 1200), seed=seed, count=int(spec.get("count", 24)))
    elif name == "terminus":
        img = I.terminus(sc("w", 900, 520), sc("h", 520, 900), seed=seed)
    elif name == "cafe":
        img = I.cafe_front(sc("w", 700, 460), sc("h", 460, 700), seed=seed)
    elif name == "hospital":
        img = I.hospital(sc("w", 900, 520), sc("h", 520, 900), seed=seed)
    elif name == "dinghy":
        img = I.dinghy(sc("w", 260, 130), sc("h", 130, 260), seed=seed)
    elif name == "trawler":
        img = I.trawler(sc("w", 520, 220), sc("h", 220, 520), seed=seed)
    elif name == "helicopter":
        img = I.helicopter(sc("w", 420, 220), sc("h", 220, 420), seed=seed, rotor=float(spec.get("rotor", 0.0)))
    elif name == "smoke":
        img = I.smoke(sc("w", 700, 700), sc("h", 700, 700), seed=seed, density=float(spec.get("density", 1.0)))
    elif name == "flame":
        img = I.flame(sc("w", 400, 500), sc("h", 500, 400), seed=seed, strength=float(spec.get("strength", 1.0)))
    elif name == "phone":
        img = I.phone(sc("h", 220, 264), seed=seed, kind=spec.get("kind", "handset"))
    elif name == "airliner":
        img = I.airliner(sc("w", 900, 320), sc("h", 320, 900), seed=seed,
                         stairs=float(spec.get("stairs", 0.0)),
                         view=spec.get("view", "side"))
    elif name == "parachute":
        img = I.parachute(sc("w", 420, 520), sc("h", 520, 420), seed=seed,
                          canopy=float(spec.get("canopy", 1.0)),
                          figure=bool(spec.get("figure", True)))
    elif name == "banknotes":
        img = I.banknotes(sc("w", 420, 260), sc("h", 260, 420), seed=seed,
                          bundles=int(spec.get("bundles", 3)),
                          bands=bool(spec.get("bands", True)))
    elif name == "necktie":
        img = I.necktie(sc("w", 220, 560), sc("h", 560, 220), seed=seed,
                        clip=bool(spec.get("clip", True)))
    elif name == "cctv":
        img = I.cctv(sc("w", 260, 220), sc("h", 220, 260), seed=seed)
    else:
        raise ValueError(f"unknown art: {name}")
    # atmospheric and overlay layers default to no paper-cutout border;
    # a thread in particular must sit *on* the map, so a white cut-out edge
    # around the cord would read as a road rather than string
    default_sticker = name not in ("smoke", "crowd", "map", "thread")
    if spec.get("sticker", default_sticker):
        img = C.sticker(img, border=max(2, int(float(spec.get("border", 9)) * S)),
                        shadow=False, seed=seed)
    return img


# ------------------------------------------------------------------ marker ----


def render_marker(spec, S, size, progress, accent, seed, offset=(0.0, 0.0)):
    """Render a marker annotation into a tight sub-canvas for speed."""
    ty = spec["type"]
    width = float(spec.get("width", 14)) * S
    color = hex_rgb(spec.get("color", accent))
    ox, oy = offset

    if ty == "marker_path":
        pts = [(p[0] * S + ox, p[1] * S + oy) for p in spec["points"]]
        smooth = bool(spec.get("smooth", True))
    elif ty in ("marker_rect", "marker_ellipse"):
        if "_abs_box" in spec:
            x0, y0, x1, y1 = spec["_abs_box"]
        else:
            x0, y0, x1, y1 = [v * S for v in spec["box"]]
            x0, x1, y0, y1 = x0 + ox, x1 + ox, y0 + oy, y1 + oy
        if ty == "marker_rect":
            over = (x1 - x0) * 0.03
            pts = [(x0 - over * .5, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 - over * .2),
                   (x0 + over, y0 - over * .25)]
        else:
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            pts = [(cx + rx * math.cos(-2.2 + i / 96 * 2 * math.pi * 1.08),
                    cy + ry * math.sin(-2.2 + i / 96 * 2 * math.pi * 1.08)) for i in range(97)]
        smooth = False
    else:
        raise ValueError(ty)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = width * 2.6 + 14
    bx0 = max(0, int(min(xs) - pad))
    by0 = max(0, int(min(ys) - pad))
    bx1 = min(size[0], int(max(xs) + pad))
    by1 = min(size[1], int(max(ys) + pad))
    if bx1 <= bx0 or by1 <= by0:
        return None, (0, 0)

    local = [(p[0] - bx0, p[1] - by0) for p in pts]
    img = C.marker_stroke((bx1 - bx0, by1 - by0), local, color=color, width=width,
                          progress=progress, wobble=float(spec.get("wobble", 2.6)) * S,
                          seed=seed, smooth=smooth)
    return img, (bx0, by0)


# ------------------------------------------------------------------- board ----


def build_board(sb, S, BW, BH, accent):
    """Bake the static background: sheet, ghost print, underlays, static decor."""
    st = sb.get("style", {})
    seed = int(st.get("seed", 7))
    light = hex_rgb(st.get("paper_light", PALETTE["paper_light"]))
    deep = hex_rgb(st.get("paper_deep", PALETTE["paper_deep"]))
    board = paper.parchment(BW, BH, seed=seed, light=light, deep=deep,
                            blotches=int(st.get("blotches", 9))).convert("RGBA")

    if st.get("ghost_print", True):
        board.alpha_composite(paper.ghost_print(BW, BH, seed=seed + 21,
                                                alpha=int(st.get("ghost_alpha", 26)),
                                                scale=S))
    if st.get("map_underlay"):
        board.alpha_composite(paper.map_fragment(BW, BH, seed=seed + 41,
                                                 alpha=int(st.get("map_alpha", 26))))
    if st.get("grid_underlay"):
        board.alpha_composite(paper.grid_fragment(BW, BH, seed=seed + 51,
                                                  alpha=int(st.get("grid_alpha", 26)),
                                                  pitch=int(34 * S)))
    if st.get("night"):
        board.alpha_composite(I.night_wash(BW, BH, float(st.get("night", 0.0)),
                                           hex_rgb(st.get("night_tint", (38, 44, 62)))))
    return board


# ------------------------------------------------------------------ render ----


def unique_path(path, force=False):
    """Resolve a video path that is guaranteed not to exist yet.

    A render costs minutes and is not reproducible once a storyboard moves on,
    so finished videos are never overwritten. If `path` is taken we return the
    next free `name-002.mp4`, `name-003.mp4`, ... Pass `force=True` to opt out.
    """
    if force or not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    root = re.sub(r"-\d{3}$", "", root)   # keep one series, don't nest suffixes
    n = 2
    while os.path.exists(f"{root}-{n:03d}{ext}"):
        n += 1
    return f"{root}-{n:03d}{ext}"


def _style_verify():
    """The delivery targets `style.json` declares, if it can be read.

    Duplicating them as literals here is how the declared target and the
    delivered one drift apart: either file can be edited alone and nothing
    disagrees until a mix report does, a full render later.
    """
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            os.pardir, "style.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("verify") or {}
    except Exception:
        return {}


def render(sb, out_path, preview=False, single_frame=None, sheet=False, force=False,
           sb_dir=".", audio_only=False, motion_samples=0, clip=None,
           jobs=1):
    if jobs is not None and int(jobs) <= 0:
        jobs = os.cpu_count() or 1
    jobs = max(1, int(jobs or 1))
    out = sb.get("output", {})
    W = int(out.get("width", 1920))
    H = int(out.get("height", 1080))
    fps = int(out.get("fps", 30))
    if preview:
        W, H = W // 2, H // 2
        # never write over the finished render — authors iterate with --preview
        # and would otherwise silently replace a full-resolution file
        root, ext = os.path.splitext(out_path)
        out_path = f"{root}_preview{ext}"
    if single_frame is None and not sheet and not audio_only and not clip:
        fresh = unique_path(out_path, force)
        if fresh != out_path:
            print(f"note: {os.path.basename(out_path)} exists -> writing "
                  f"{os.path.basename(fresh)}")
        out_path = fresh
    S = W / 1920.0                      # design-space -> pixels
    BW, BH = int(W * OVER), int(H * OVER)
    accent = hex_rgb(sb.get("style", {}).get("accent", PALETTE["accent"]))

    workdir = tempfile.mkdtemp(prefix="archival_")
    tl = Timeline()

    # ---- audio first: it defines the length of everything
    print("· laying out narration", flush=True)
    voice_track = build_narration(sb, workdir, tl, sb_dir)
    duration = tl.duration
    print(f"· timeline: {duration:.2f}s", flush=True)
    for lid, (a, b) in tl.lines.items():
        print(f"    {lid:>4}  {a:6.2f} → {b:6.2f}", flush=True)

    # Narration clips are trimmed before they are laid down, so a downstream
    # stage that measures the source wavs instead sees every line about a
    # second longer than it plays and drifts steadily out of sync -- over a
    # 12-minute film, by two minutes. The resolved timeline is published at
    # the end of a successful encode so nobody has to re-derive it.

    # ---- elements
    MX, MY = (BW - W) / 2.0, (BH - H) / 2.0
    elements = []
    for i, spec in enumerate(sb.get("elements", [])):
        el = Element(spec, tl, S, seedbase=100 + i * 7)
        el.anchor(MX, MY)
        if spec["type"].startswith("marker_"):
            el.base = None
        else:
            el.art = make_base(spec, S, accent, el.seed)
            el.build_shadow(S)
            el.base = el.shadowed(el.elevation)
        elements.append(el)
    elements.sort(key=lambda e: e.z)

    # resolve `box_of`: fit a marker around another element's actual artwork
    by_id = {e.id: e for e in elements if e.id}
    for el in elements:
        ref = el.spec.get("box_of")
        if not ref:
            continue
        if ref not in by_id:
            raise KeyError(f"box_of references unknown element id '{ref}'")
        tgt = by_id[ref]
        if tgt.art is None:
            raise ValueError(f"box_of target '{ref}' has no artwork")
        pad_x = float(el.spec.get("pad_x", 26)) * S
        pad_y = float(el.spec.get("pad_y", 16)) * S
        # measure the ink itself, not the canvas: illustrations carry a lot of
        # transparent margin and shadow padding varies with elevation
        bb = tgt.art.getchannel("A").getbbox() or (0, 0, *tgt.art.size)
        aw, ah = tgt.art.size
        cx, cy = tgt.pos
        x0 = cx - aw / 2 + bb[0]
        y0 = cy - ah / 2 + bb[1]
        x1 = cx - aw / 2 + bb[2]
        y1 = cy - ah / 2 + bb[3]
        el.spec["_abs_box"] = (x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)

    board = build_board(sb, S, BW, BH, accent)

    # bake elements that never move and are present from t=0
    all_elements = list(elements)
    for el in list(elements):
        if el.spec.get("static") and el.base is not None:
            M.place_centered(board, el.base, (el.pos[0], el.pos[1]))
            elements.remove(el)

    # ---- precomputed post-process
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (xx / W - 0.5) * 2, (yy / H - 0.5) * 2
    r = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
    vig_strength = float(sb.get("style", {}).get("vignette", 0.42))
    vig = (1.0 - vig_strength * (r ** 1.6))[:, :, None].astype(np.float32)
    grain_amt = float(sb.get("style", {}).get("grain", 7))
    grng = np.random.default_rng(99)
    grain_pool = [grng.normal(0, grain_amt, (H, W, 1)).astype(np.float32) for _ in range(16)]

    cam = sb.get("camera", {})
    cam_zoom = float(cam.get("zoom", 0.05))
    cam_amount = float(cam.get("drift", 0.028))
    cam_moves = []
    for mv in cam.get("moves", []):
        x, y = mv.get("at", [960, 540])
        t0 = tl.resolve(mv.get("t", 0.0))
        # a `cut` key is an instant jump rather than an eased travel -- see
        # M.camera_path, which reads this optional 5th tuple element
        cut = bool(mv.get("cut", False))
        key = (float(x), float(y), float(mv.get("zoom", 1.0)), cut)
        cam_moves.append((t0,) + key)
        # `hold` parks the camera on the beat before it travels on, which is
        # what makes the move read as a decision rather than a constant slide
        hold = float(mv.get("hold", cam.get("hold", 0.0)))
        if hold > 0:
            cam_moves.append((t0 + hold,) + key)
    cam_moves.sort(key=lambda m: m[0])

    cam_shake = [
        {
            "t": tl.resolve(sh.get("t", 0.0)),
            "dur": float(sh.get("dur", 1.0)),
            "amp": float(sh.get("amp", 20.0)),
            "freq": float(sh.get("freq", 10.0)),
            "decay": float(sh.get("decay", 3.0)),
        }
        for sh in cam.get("shake", [])
    ]

    def compose(t):
        frame = board.copy()
        cs, cdx, cdy = M.camera_drift(t, duration, cam_amount, cam_zoom)
        if cam_moves:
            # authored travel dominates; the sine wander stays as a small
            # hand-held overlay so the camera is never mathematically still
            tx, ty, tz = M.camera_path(t, cam_moves, duration)
            cs = tz + cam_zoom * M.ease_in_out_cubic(min(1.0, t / max(duration, 1e-6)))
            cdx = (tx * S + MX) / BW - 0.5 + cdx * 0.25
            cdy = (ty * S + MY) / BH - 0.5 + cdy * 0.25
        if cam_shake:
            # a deliberate jolt, layered on top of the authored path/drift --
            # same design-unit -> board-fraction conversion as tx/ty above
            sdx, sdy = M.camera_shake(t, cam_shake)
            cdx += sdx * S / BW
            cdy += sdy * S / BH
        for el in elements:
            if not el.visible(t):
                continue
            p = el.progress(t)
            op_out = el.out_progress(t)

            if el.type.startswith("marker_"):
                img, org = render_marker(el.spec, S, (BW, BH),
                                         M.ease_out_cubic(p), accent, el.seed, (MX, MY))
                if img is None:
                    continue
                if op_out > 0:
                    img = M.transform(img, opacity=1.0 - M.ease_in_out_cubic(op_out))
                frame.alpha_composite(img, org)
                continue

            anim = el.anim
            elev = el.elevation
            if anim == "stamp":
                s, rot, op, dx, dy = M.enter_stamp(p, el.rotate)
                elev += 0.55 * (1.0 - M.ease_out_cubic(p))
            elif anim == "pin":
                s, rot, op, dx, dy = M.enter_pin(p, el.rotate, drop=54 * S)
                elev += 0.75 * (1.0 - M.ease_out_cubic(p))
            elif anim == "slide":
                s, rot, op, dx, dy = M.enter_slide(
                    p, float(el.spec.get("from_x", 0)) * S,
                    float(el.spec.get("from_y", 60)) * S, el.rotate)
                elev += 0.45 * (1.0 - M.ease_out_cubic(p))
            elif anim == "fly":
                s, rot, op, dx, dy, fe = M.enter_fly(
                    p, el.rotate,
                    float(el.spec.get("from_x", 0)) * S,
                    float(el.spec.get("from_y", -140)) * S,
                    height=el.fly_h, spin=float(el.spec.get("spin", 7.0)))
                elev += fe
            elif anim == "fade":
                s, rot, op, dx, dy = M.enter_fade_rise(p, 30 * S, el.rotate)
            elif anim == "none":
                s, rot, op, dx, dy = 1.0, el.rotate, 1.0, 0, 0
            else:
                s, rot, op, dx, dy = M.enter_fade_rise(p, 30 * S, el.rotate)

            if op_out > 0:
                s2, _, op2, _, dy2 = M.exit_fade(op_out, 18 * S)
                s *= s2
                op *= op2
                dy += dy2

            drift = el.spec.get("drift")
            if drift:
                a = el.drift_from if el.drift_from is not None else el.t_in
                b = el.drift_to if el.drift_to is not None else duration
                u = M.clamp((t - a) / max(0.001, b - a))
                e = M.ease_in_out_cubic(u)
                dx += el.drift_x * S * e
                dy += el.drift_y * S * e

            if el.has_sway:
                tau = max(0.0, t - el.t_in)
                w = 2.0 * math.pi / el.sway_period
                # the two axes run on incommensurate periods so the element
                # traces a slow open figure rather than sliding along one line
                ramp = M.clamp(tau / el.sway_ramp)
                dx += el.sway_x * S * ramp * math.sin(w * tau)
                dy += el.sway_y * S * ramp * math.sin(w * 0.61 * tau + 1.05)
                if el.sway_scale:
                    s *= 1.0 + el.sway_scale * ramp * math.sin(w * 0.47 * tau)

            # nothing on a live board is ever perfectly still
            if el.float_amp:
                fx, fy, fr = M.idle_float(t, el.seed, amp=el.float_amp * S * 1.6)
                dx += fx
                dy += fy
                rot += fr

            # layers react to the camera in proportion to their depth
            if el.parallax:
                px, py = M.parallax_offset(el.parallax, cdx, cdy, cs)
                dx += px
                dy += py

            img = M.transform(el.shadowed(elev), scale=s, rotate=rot, opacity=op)
            M.place_centered(frame, img, (el.pos[0] + dx, el.pos[1] + dy))

        view = M.apply_camera(frame, (W, H), max(cs, W / BW), cdx, cdy)

        a = np.asarray(view.convert("RGB"), dtype=np.float32)
        a += grain_pool[int(t * fps) % len(grain_pool)]
        a *= vig
        return np.clip(a, 0, 255).astype(np.uint8)

    # ---- single frame / contact sheet modes
    if single_frame is not None:
        img = Image.fromarray(compose(single_frame))
        p = out_path.rsplit(".", 1)[0] + f"_t{single_frame:g}.jpg"
        img.save(p, quality=92)
        print("wrote", p)
        return p
    if motion_samples:
        # Estimate verification check 4 (mean frame-to-frame difference at
        # 320x180) without encoding the film. Sampling frame *pairs* costs a
        # few minutes instead of a full render, which makes the pacing of a
        # board something you can iterate on rather than guess at.
        rng = np.random.default_rng(7)
        n_frames = max(2, int(duration * fps))
        idx = rng.choice(n_frames - 1, size=min(motion_samples, n_frames - 1),
                         replace=False)
        diffs = []
        for k, i in enumerate(sorted(idx.tolist())):
            a0 = Image.fromarray(compose(i / fps)).convert("L").resize(
                (320, 180), Image.BILINEAR)
            a1 = Image.fromarray(compose((i + 1) / fps)).convert("L").resize(
                (320, 180), Image.BILINEAR)
            d = np.abs(np.asarray(a0, dtype=np.float32)
                       - np.asarray(a1, dtype=np.float32)).mean()
            diffs.append(d)
            if (k + 1) % 25 == 0:
                print(f"  {k + 1}/{len(idx)} mean so far {np.mean(diffs):.3f}",
                      flush=True)
        m = float(np.mean(diffs))
        se = float(np.std(diffs) / math.sqrt(len(diffs)))
        print(f"motion estimate {m:.3f} +/- {1.96 * se:.3f} "
              f"(95% CI, {len(diffs)} sampled frame pairs)")
        return m

    if clip:
        # Render one contiguous stretch, silent, at full resolution. A full
        # render is ~40 minutes, which is far too slow a loop to judge whether
        # a transition reads as a pan or a lurch; a ten-second clip takes
        # seconds and shows exactly the same frames the film will contain.
        a, b = max(0.0, float(clip[0])), min(duration, float(clip[1]))
        if b <= a:
            raise SystemExit(f"--clip needs END > START (got {a} {b})")
        i0, i1 = int(round(a * fps)), int(round(b * fps))
        p = out_path.rsplit(".", 1)[0] + f"_clip{a:g}-{b:g}.mp4"
        ff = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", p]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        prev = None
        worst = (0.0, 0.0)
        for i in range(i0, i1):
            fr = compose(i / fps)
            proc.stdin.write(fr.tobytes())
            small = np.asarray(Image.fromarray(fr).convert("L").resize(
                (320, 180), Image.BILINEAR), dtype=np.float32)
            if prev is not None:
                d = float(np.abs(small - prev).mean())
                if d > worst[0]:
                    worst = (d, i / fps)
            prev = small
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        shutil.rmtree(workdir, ignore_errors=True)
        print(f"wrote {p}  ({i1 - i0} frames)")
        print(f"largest single-frame change {worst[0]:.2f} at t={worst[1]:.2f}s")
        return p

    if sheet:
        cols, rows = 5, 4
        n = cols * rows
        thumbs = [Image.fromarray(compose(duration * i / (n - 1) * 0.99)) for i in range(n)]
        tw, th = W // 4, H // 4
        s_img = Image.new("RGB", (tw * cols, th * rows), (12, 12, 12))
        for i, im in enumerate(thumbs):
            s_img.paste(im.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
        p = out_path.rsplit(".", 1)[0] + "_sheet.jpg"
        s_img.save(p, quality=88)
        print("wrote", p)
        return p

    # ---- audio mix
    print("· building music bed", flush=True)
    music = build_music(sb, duration, tl, sb_dir)
    n = int(duration * A.SR) + 1
    voice = np.pad(voice_track, (0, max(0, n - len(voice_track))))[:n]

    sfx = np.zeros(n, dtype=np.float32)
    for el in all_elements:
        if el.sfx:
            fn = A.SFX.get(el.sfx)
            if fn:
                sig = fn() if el.sfx == "chime" else fn(seed=el.seed % 1000)
                i0 = int(el.t_in * A.SR)
                j = min(n, i0 + len(sig))
                if j > i0:
                    sfx[i0:j] += sig[: j - i0] * el.sfx_gain
    for cue in sb.get("sfx", []):
        fn = A.SFX.get(cue["type"])
        if not fn:
            continue
        sig = fn() if cue["type"] == "chime" else fn(seed=int(cue.get("seed", 0)))
        i0 = int(tl.resolve(cue["t"]) * A.SR)
        j = min(n, i0 + len(sig))
        if j > i0:
            sfx[i0:j] += sig[: j - i0] * float(cue.get("gain", 1.0))

    mix_cfg = sb.get("mix", {})
    # The style declares the delivery target; a storyboard may tighten it but
    # not quietly relax it, or the contract the style advertises is not the one
    # that ships.
    _dec = _style_verify()
    _lufs = float(mix_cfg.get("lufs", _dec.get("loudness_lufs", -14.0)))
    _tp = float(mix_cfg.get("true_peak", _dec.get("true_peak_dbfs", -1.0)))
    _dtp = _dec.get("true_peak_dbfs")
    if _dtp is not None and _tp > float(_dtp):
        print("! storyboard mix.true_peak %.1f is looser than the %.1f this "
              "style declares; using the style's" % (_tp, float(_dtp)), flush=True)
        _tp = float(_dtp)
    ducked = A.duck(music, voice,
                    depth_db=float(mix_cfg.get("duck_db", -11.0)))
    mixed = (voice * float(mix_cfg.get("voice", 1.0))
             + ducked * float(mix_cfg.get("music", 0.62))
             + sfx * float(mix_cfg.get("sfx", 0.55)))
    mixed = A.soft_clip(mixed, 0.95)
    raw_wav = os.path.join(workdir, "mix_raw.wav")
    A.write_wav(raw_wav, np.stack([mixed, mixed], axis=1))
    mastered = os.path.join(workdir, "mix.wav")
    _m = A.master(raw_wav, mastered, lufs=_lufs, tp=_tp)
    if _m.get("true_peak") is None:
        print("· master: could not meter the delivered peak; shipping unverified",
              flush=True)
    elif _m["within_target"]:
        print("· master: %.1f dBTP delivered against %.1f target (guard %.1f dB)"
              % (_m["true_peak"], _m["target_true_peak"], _m["guard_db"]), flush=True)
    else:
        print("! master: %.1f dBTP delivered, over the %.1f target even at a "
              "%.1f dB guard -- the mix is too hot to limit cleanly"
              % (_m["true_peak"], _m["target_true_peak"], _m["guard_db"]), flush=True)

    # ---- audio-only: swap the track into the existing render, keep the frames
    if audio_only:
        ff = shutil.which("ffmpeg") or "ffmpeg"
        if not os.path.exists(out_path):
            raise SystemExit(f"--audio-only needs an existing {out_path} to remux")
        tmp_out = out_path + ".remux.mp4"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", out_path,
                        "-i", mastered, "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-movflags", "+faststart", "-shortest",
                        tmp_out], check=True)
        os.replace(tmp_out, out_path)
        shutil.rmtree(workdir, ignore_errors=True)
        print(f"remuxed audio into {out_path} (frames untouched)")
        return out_path

    # ---- video
    n_frames = int(round(duration * fps))
    ff = shutil.which("ffmpeg") or "ffmpeg"
    # Per-frame grain is incompressible, so CRF alone lets the bitrate explode.
    # Cap it: the reference video sits near 19 Mbps.
    maxrate = str(out.get("maxrate", "20M"))
    cmd = [
        ff, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", mastered,
        "-c:v", "libx264", "-preset", out.get("preset", "medium"),
        "-crf", str(out.get("crf", 20)), "-pix_fmt", "yuv420p",
        "-maxrate", maxrate, "-bufsize", str(out.get("bufsize", "40M")),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", out_path,
    ]
    print(f"· rendering {n_frames} frames at {W}x{H}"
          + (f" on {jobs} workers" if jobs > 1 else ""), flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def report(i):
        if i % 30 == 0:
            pct = 100 * i / max(1, n_frames)
            print(f"\r  {pct:5.1f}%  frame {i}/{n_frames}", end="", flush=True)

    # ffmpeg holds the read end of a pipe this process is still writing to, so
    # anything that escapes the frame loop has to take the encoder with it.
    # Left running it waits forever on a write end nobody will close.
    try:
        if jobs > 1:
            # Every frame is a pure function of its timestamp, so they compose
            # independently; only the write order matters, and `imap` preserves
            # it. `fork` is required because `compose` is a closure over the
            # built board and cannot be pickled for `spawn`.
            ctx = multiprocessing.get_context("fork")
            global _COMPOSE
            _COMPOSE = compose
            # The workers fork *after* ffmpeg is spawned, so each inherits a
            # copy of its stdin write end and ffmpeg only reaches EOF once
            # every copy is gone. That makes the teardown order below
            # load-bearing: the pool must be joined before
            # `proc.stdin.close()`, which is why the `finally` exists rather
            # than a bare `with`. Closing the descriptor inside the workers
            # instead would be worse -- a replacement worker forked mid-render
            # inherits a half-filled buffer, and closing that flushes duplicate
            # bytes into the encoder.
            #
            # `imap` pulls from its input as fast as the workers can drain it
            # and holds every finished frame until the consumer asks for it.
            # A 1080p frame is 6 MB, so against ffmpeg --
            # which is slower than eight compositors -- the backlog grows
            # without bound and the parent is OOM-killed. That kill is silent:
            # it leaves no traceback, and all you see is a wall of broken pipes
            # from workers whose results now have nowhere to go. Gate the input
            # so only a few frames per worker are ever in flight.
            #
            # The gate is acquired by the pool's own feeder thread and released
            # by this loop, so anything that stops the loop -- a worker
            # exception, the guard below, Ctrl-C -- leaves the feeder parked on
            # `acquire()` forever, and pool teardown, which can only unstick a
            # feeder blocked in `put()`, waits on it just as long. Trading a
            # silent OOM for a silent hang is no trade, so abandonment has to
            # be explicit: set the flag, hand back enough permits to wake the
            # feeder, and let it see the flag and return before anything tries
            # to join it.
            inflight = threading.Semaphore(jobs * 3)
            abort = threading.Event()

            def gated():
                for i in range(n_frames):
                    inflight.acquire()
                    if abort.is_set():
                        return
                    yield i / fps

            expect = W * H * 3
            pool = ctx.Pool(jobs)
            # Pool quietly replaces a worker that dies, so by the time anyone
            # looks the corpse is gone from its roster and the only trace left
            # is that the pids changed. With the default maxtasksperchild a
            # worker lives for the whole pool, so a pid going missing is never
            # routine -- it always means a task was lost with it.
            crew = {w.pid for w in getattr(pool, "_pool", ())}
            try:
                it = pool.imap(_compose_at, gated(), chunksize=1)
                i = -1
                while True:
                    # A worker that dies *abruptly* -- SIGKILL under memory
                    # pressure, a segfault in the imaging stack, anything
                    # raising BaseException -- never sends a result back,
                    # because pool's own wrapper only catches Exception. The
                    # task it was holding then has no answer and never will,
                    # so an untimed `next()` waits for the rest of the run and
                    # the feeder waits behind it: another silent hang. The
                    # timeout is a poll interval rather than a deadline -- a
                    # legitimately slow frame just loops again -- so the only
                    # thing it can turn into an error is a worker that is
                    # genuinely gone.
                    try:
                        buf = it.next(timeout=5.0)
                    except multiprocessing.TimeoutError:
                        now = {w.pid for w in getattr(pool, "_pool", ())}
                        if not crew - now:
                            continue
                        raise RuntimeError(
                            f"a render worker died around frame {i + 1} of "
                            f"{n_frames} without returning a frame, and the "
                            "pool replaced it. The usual cause is the OS "
                            "killing it for memory. Retry with fewer "
                            "workers: -j 2.") from None
                    except StopIteration:
                        break
                    i += 1
                    inflight.release()
                    if len(buf) != expect:
                        raise RuntimeError(
                            f"frame {i} composed to {len(buf)} bytes, "
                            f"expected {expect} ({W}x{H}x3). The compositor "
                            "produced the wrong shape or dtype; this is a bug "
                            "in compose(), not in ffmpeg.")
                    proc.stdin.write(buf)
                    report(i)
            except BaseException:
                abort.set()
                for _ in range(jobs * 4 + 8):
                    inflight.release()
                raise
            finally:
                pool.terminate()
                pool.join()
                _COMPOSE = None
        else:
            for i in range(n_frames):
                proc.stdin.write(compose(i / fps).tobytes())
                report(i)
    except BaseException:
        proc.kill()
        proc.wait()
        # Only safe now that ffmpeg is reaped: closing a pipe it was still
        # reading could raise on the way out and mask the real exception.
        try:
            proc.stdin.close()
        except OSError:
            pass
        raise
    proc.stdin.close()
    rc = proc.wait()
    print("\r  100.0%            ")
    if rc != 0:
        raise RuntimeError("ffmpeg failed")
    shutil.rmtree(workdir, ignore_errors=True)
    # The layout the voice was actually placed on is published *after* the
    # encode, and only in the modes that produce the film it describes. A
    # sidecar next to a film that does not exist is worse than none: caption
    # and cut stages discover it by name and would time themselves against a
    # render that never happened.
    write_timeline(out_path, tl, sb)
    print("wrote", out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Render an archival-collage explainer video.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out")
    ap.add_argument("--preview", action="store_true", help="render at half resolution")
    ap.add_argument("--frame", type=float, help="write a single frame at time T and exit")
    ap.add_argument("--jobs", "-j", type=int, default=1,
                    help="compose frames on N processes (0 = one per core). "
                         "Frames are independent, so this is a near-linear "
                         "speed-up on a long film")
    ap.add_argument("--sheet", action="store_true", help="write a contact sheet and exit")
    ap.add_argument("--clip", type=float, nargs=2, metavar=("START", "END"),
                    help="render only START..END seconds, silent, for review")
    ap.add_argument("--motion", type=int, default=0, metavar="N",
                    help="estimate the mean frame difference from N sampled "
                         "frame pairs and exit, instead of rendering")
    ap.add_argument("--audio-only", action="store_true", dest="audio_only",
                    help="rebuild only the audio and remux it into the existing "
                         "video, copying the frames (seconds, not minutes)")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting an existing video (default: write a new file)")
    a = ap.parse_args()

    try:
        with open(a.storyboard) as f:
            sb = json.load(f)
    except FileNotFoundError:
        sys.exit("render: no storyboard at %r — run compile.py first"
                 % a.storyboard)
    except json.JSONDecodeError as e:
        sys.exit("render: %s is not valid JSON (line %d, column %d: %s)"
                 % (a.storyboard, e.lineno, e.colno, e.msg))
    except OSError as e:
        sys.exit("render: cannot read %s: %s" % (a.storyboard, e.strerror or e))
    if not isinstance(sb, dict):
        sys.exit("render: %s should hold a storyboard object, found %s"
                 % (a.storyboard, type(sb).__name__))
    base = os.path.dirname(os.path.abspath(a.storyboard))
    out_path = a.out or os.path.join(base, sb.get("output", {}).get("path", "out.mp4"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    render(sb, out_path, preview=a.preview, single_frame=a.frame, sheet=a.sheet,
           force=a.force, sb_dir=base, audio_only=a.audio_only,
           motion_samples=a.motion, clip=a.clip, jobs=a.jobs)


if __name__ == "__main__":
    main()
