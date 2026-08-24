"""Storyboard -> MP4 for the 2D character-animation style.

    python3 render.py storyboard.json --sheet        # look at this first
    python3 render.py storyboard.json --frame 12.4
    python3 render.py storyboard.json --clip 20 28
    python3 render.py storyboard.json --preview
    python3 render.py storyboard.json -j 0           # the film

What makes this renderer different from `style-paper`'s
------------------------------------------------------

**It cuts.** `style-paper` composes one continuous board and moves a camera
over it; this style is a shot list. Every shot is composed independently, from
its own set, with its own camera, and the frames are simply concatenated. A
cut is the absence of a transition.

**It animates on twos.** Pose evaluation is quantised to the shot's `on`
(1, 2 or 3 frames) while **the camera is evaluated every single frame**. That
split is the most important line of code in the file. Quantising the camera
too costs nothing and looks like a bug: a pan on twos judders, and an audience
reads judder as dropped frames rather than as drawings held. Holding the
drawings *is* the look; holding the camera is a fault.

**Its determinism is verified, not assumed.** Segment boundaries come from the
running time and the frame rate alone, so `-j 1` and `-j 4` hand ffmpeg
identical spans and produce identical bytes. `--self-test` proves it with
SHA-256 rather than asserting it in a comment.

**It never invents a picture.** A set, cast, action or prop that the modules do
not have is drawn as a labelled placeholder and reported to stderr. A film with
a plausible-looking substitute in it is worse than one with a hole, because the
hole is the only version anybody notices.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import importlib
import inspect
import json
import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import shots as SH

# Frames are encoded in contiguous segments, each by its own ffmpeg, so
# encoding scales with the cores instead of funnelling through one process.
# The length is derived from the running time rather than from the worker
# count: that is what keeps the output reproducible, because the same board
# then cuts into the same segments on a four-core laptop and a sixty-four-core
# server.
SEG_TARGET = 64
SEG_MIN_SECONDS = 4.0
SEG_POLL_SECONDS = 5.0

# Memory and core budgeting, ported from the sibling renderer; the reasoning
# there applies unchanged, since a worker here also holds its own palette, its
# own set caches and its own encoder.
WORKER_GB = 1.5
RESERVE_GB = 2.0

SAFE = 0.045          # title-safe inset, as a fraction of the frame's width
#: Contact-shadow geometry. Alpha 78/255 is 30.6%, mid-band of the style's
#: 28-32%: enough to seat a figure, not enough to read as a second object.
#: `a` is the semi-axis across the contact patch, `b` the one along it.
SHADOW_ALPHA = 78     # contact shadows are always low-alpha; see rule 4
SHADOW_A = 0.55       # semi-axis a = foot_span * SHADOW_A
SHADOW_B = 0.06       # semi-axis b = height    * SHADOW_B

#: The largest excursion a pose may add to its staged pelvis, as a fraction of
#: the character's height, before the renderer concludes the pose ignored the
#: stage rather than moved on it. The bobs in `poses` top out at 0.026 H (a
#: run) and an idle's weight shift at 0.010 H, so this is an order of
#: magnitude of headroom — it is a sanity check, not a clamp.
POSE_EXCURSION = 0.35

#: How an actor's horizontal is arranged for one shot. `stride` is the gait's
#: travel per cycle in scene units (0 if the action is not a gait), `travel`
#: whether the cycle carries the character itself, `locked` whether the phase
#: is being driven from the staged travel to keep the feet planted, and
#: `owner` which of the three arrangements was chosen, for the timeline.
_GaitPlan = collections.namedtuple("_GaitPlan",
                                   "stride travel locked owner")


# ------------------------------------------------------- sibling modules ----

#: The modules that draw. They are separate agents' files and may legitimately
#: be absent while the style is being built, so the import is tolerated here
#: and enforced at render time, where the error can say what it was about to
#: do with them.
_MODULE_NAMES = ("rig", "poses", "anim", "look", "sets", "audio")
MODS: dict[str, object] = {}
IMPORT_ERRORS: dict[str, str] = {}

for _name in _MODULE_NAMES:
    try:
        MODS[_name] = importlib.import_module(_name)
    except Exception as exc:                     # pragma: no cover - env dependent
        MODS[_name] = None
        IMPORT_ERRORS[_name] = f"{type(exc).__name__}: {exc}"


def need(*names, why=""):
    """Fail loudly for a module that is genuinely missing.

    Called at the point of use, not at import, so `--help` works and so the
    message can name the thing that was about to happen.
    """
    lack = [n for n in names if MODS.get(n) is None]
    if not lack:
        return [MODS[n] for n in names]
    lines = [f"render: cannot {why or 'render'} without "
             + ", ".join(f"{n}.py" for n in lack)]
    for n in lack:
        lines.append(f"    {n}.py  {IMPORT_ERRORS.get(n, 'not found')}")
    lines.append("    These live beside render.py and are written by the rig, "
                 "poses, anim, look, sets and audio agents.")
    raise SystemExit("\n".join(lines))


def _accepts(fn, name):
    """Does `fn` take a keyword called `name`? Used to forward optional hints."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if p.name == name:
            return True
    return False


def _names(fn, name):
    """Does `fn` declare `name` explicitly? `**kwargs` does not count.

    Used where a wrong answer is silent rather than loud: handing `shadow=`
    to a rig that swallows it in `**kw` and ignores it would take every
    contact shadow out of the film without saying so.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    p = sig.parameters.get(name)
    return p is not None and p.kind is not inspect.Parameter.VAR_KEYWORD


def _registry(mod, *names):
    """The set of names a module says it can draw.

    `sets.py` publishes its catalogue under whichever of these it happens to
    use; an empty answer only means the early check is off, never that the
    catalogue is empty, because every call is wrapped anyway.
    """
    for n in names:
        table = getattr(mod, n, None)
        if isinstance(table, dict) and table:
            return set(table)
        if isinstance(table, (set, frozenset, list, tuple)) and table:
            return set(table)
    return set()


# ------------------------------------------------------------- reporting ----

_REPORTED: set = set()


def report(key, msg):
    """Say something is missing, once."""
    if key in _REPORTED:
        return
    _REPORTED.add(key)
    print(f"! {msg}", file=sys.stderr, flush=True)


def _warn_key(msg):
    """One dedupe key per warning, whoever raised it.

    `shots.build` and `Film.pacing` can reach the same conclusion about the
    same board, and saying it twice makes it look like two problems.
    """
    m = msg.lstrip("! ").strip()
    if m.startswith("pacing:"):
        m = m[7:].strip()
        return ("pace:" + m[:48], "pacing: " + m)
    return ("build:" + m[:60], m)


def _cam_warn(msg):
    report(f"cam:{msg}", msg)


# --------------------------------------------------------------- palette ----


def _rgb(v, default=(128, 128, 128)):
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return (int(v[0]), int(v[1]), int(v[2]))
    if isinstance(v, str):
        s = v.lstrip("#")
        if len(s) == 6:
            try:
                return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
    return default


DEFAULT_LOOK = {
    # Only ever reached when `look.py` gave nothing back for a key. Every one
    # of these is a neutral, not a design: a hole in the palette should look
    # like a hole, not like a decision somebody made.
    "sky": (206, 214, 222), "ground": (146, 152, 148),
    "far": (176, 184, 192), "mid": (150, 158, 164), "near": (120, 128, 134),
    "skin": (226, 188, 158), "hair": (58, 48, 46), "shirt": (72, 108, 156),
    "trouser": (60, 64, 78), "shoe": (40, 40, 44),
    "ink": (26, 26, 30), "accent": (222, 78, 60), "accent2": (240, 190, 70),
    "shadow": (30, 34, 40),
}


def col(look, key, default=None):
    """A palette colour, tolerating a missing key or a hex string."""
    if isinstance(look, dict) and key in look:
        return _rgb(look[key], DEFAULT_LOOK.get(key, (128, 128, 128)))
    v = getattr(look, key, None) if look is not None else None
    if v is not None:
        return _rgb(v, DEFAULT_LOOK.get(key, (128, 128, 128)))
    return default if default is not None else DEFAULT_LOOK.get(
        key, (128, 128, 128))


def _plate(look, factor=0.16):
    """A darker relative of the board's ink, for panels and chrome.

    Scaled toward 8 rather than replaced by a grey, so a palette whose ink is
    a hued near-black keeps its hue. Nothing here is allowed to assume
    `(0, 0, 0)`: these palettes do not contain it.
    """
    c = col(look, "ink")
    return tuple(int(v * (1 - factor) + 8 * factor) for v in c)


def outline_for(look, fill):
    """The line that goes round a filled shape.

    `look.py` owns this decision -- a light fill wants the palette's ink, a
    dark one wants something lifted off it -- and publishes `outline_for`. It
    is consulted when present; the fallback is the ink itself, which is what
    this was before the helper existed.
    """
    fn = getattr(MODS.get("look"), "outline_for", None)
    if callable(fn):
        try:
            return _rgb(fn(tuple(int(v) for v in fill[:3])), col(look, "ink"))
        except Exception:
            pass
    return col(look, "ink")


def choose_look(board):
    """The film's palette: the board's name first, then the story's mood."""
    look_mod = MODS.get("look")
    if look_mod is None:
        need("look", why="pick a palette")
    name = board.get("palette")
    palettes = getattr(look_mod, "PALETTES", {}) or {}
    if name:
        if name in palettes:
            return palettes[name]
        # `derive`d palettes are not in the table, but `get` knows them.
        getter = getattr(look_mod, "get", None)
        if callable(getter):
            try:
                found = getter(name)
            except Exception:
                found = None
            if found:
                return found
        report(f"palette:{name}",
               f"palette '{name}' is not in look.PALETTES ({', '.join(sorted(palettes)) or 'empty'})"
               " — falling back to the mood")
    mood = (board.get("music") or {}).get("mood")
    chooser = getattr(look_mod, "choose", None)
    if chooser is None:
        need("look", why="pick a palette")
    return chooser(mood, board.get("title"))


def cast_look(base, board, cast_id):
    """A per-character palette.

    `rig.draw` takes one palette, so a costume can only reach it as a variant
    of the film's own. A board with no `cast` table at all is simply a board
    whose characters all wear the palette's clothes — that is a look decision
    `look.py` owns, not a missing picture.
    """
    table = board.get("cast")
    if not isinstance(table, dict) or not cast_id:
        return base
    entry = table.get(cast_id)
    if entry is None:
        report(f"cast:{cast_id}",
               f"cast '{cast_id}' is not in the board's `cast` table "
               f"({', '.join(sorted(table)) or 'empty'}) — drawing a placeholder")
        return None
    if not isinstance(entry, dict):
        return base
    out = dict(base) if isinstance(base, dict) else base
    if isinstance(out, dict):
        for k in ("skin", "hair", "shirt", "trouser", "shoe", "accent",
                  "accent2", "ink"):
            if entry.get(k) is not None:
                out[k] = _rgb(entry[k], col(base, k))
    return out


# ------------------------------------------------------------- text/font ----

_FONT_CANDIDATES = (
    # A deterministic search order. The first that exists on the machine wins,
    # so two renders on one machine always pick the same face.
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/System/Library/Fonts/Helvetica.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("/Library/Fonts/Arial Bold.ttf", 0),
)
_FONT_REGULAR = (
    ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
    ("/System/Library/Fonts/Helvetica.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
)
_FONTS: dict = {}


def font(size, bold=True):
    size = max(8, int(round(size)))
    key = (size, bool(bold))
    f = _FONTS.get(key)
    if f is not None:
        return f
    for path, index in (_FONT_CANDIDATES if bold else _FONT_REGULAR):
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size, index=index)
                break
            except Exception:
                continue
    if f is None:
        try:
            f = ImageFont.load_default(size=size)
        except TypeError:                        # pragma: no cover - old Pillow
            f = ImageFont.load_default()
    _FONTS[key] = f
    return f


def text_size(d, s, f):
    box = d.textbbox((0, 0), s, font=f)
    return box[2] - box[0], box[3] - box[1]


def _fit(d, s, f, limit):
    """Ellipsise `s` so it fits `limit` pixels — half a word is a lie."""
    if limit <= 0 or text_size(d, s, f)[0] <= limit:
        return s
    for n in range(len(s) - 1, 0, -1):
        cut = s[:n] + "…"
        if text_size(d, cut, f)[0] <= limit:
            return cut
    return "…"


# ------------------------------------------------------------ placeholder ----


def placeholder(img, box, label, look, *, note=""):
    """A labelled hole where a picture the modules do not have would go.

    Deliberately ugly. It has to survive being glanced at in a contact sheet
    without ever being mistaken for artwork.
    """
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x1 <= x0 or y1 <= y0:
        return
    w, h = x1 - x0, y1 - y0
    patch = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(patch)
    d.rectangle([0, 0, w - 1, h - 1], fill=_plate(look, 0.55) + (235,))
    acc = col(look, "accent")
    step = max(12, int(min(w, h) * 0.12))
    for i in range(-h, w, step):
        d.line([(i, h), (i + h, 0)], fill=acc + (70,), width=2)
    dash = max(2, int(min(w, h) * 0.02))
    for i in range(0, w, dash * 3):
        d.line([(i, 0), (min(i + dash * 2, w), 0)], fill=acc + (255,), width=3)
        d.line([(i, h - 2), (min(i + dash * 2, w), h - 2)], fill=acc + (255,),
               width=3)
    for i in range(0, h, dash * 3):
        d.line([(0, i), (0, min(i + dash * 2, h))], fill=acc + (255,), width=3)
        d.line([(w - 2, i), (w - 2, min(i + dash * 2, h))], fill=acc + (255,),
               width=3)
    fs = max(11, int(min(w / max(len(label) * 0.62, 1), h * 0.16)))
    f = font(fs, bold=True)
    tw, th = text_size(d, label, f)
    while tw > w * 0.94 and fs > 9:          # measured, not estimated: a
        fs = max(9, int(fs * 0.9))           # clipped hole reads as artwork
        f = font(fs, bold=True)
        tw, th = text_size(d, label, f)
    label = _fit(d, label, f, w * 0.94)
    tw, th = text_size(d, label, f)
    d.text(((w - tw) / 2, (h - th) / 2 - fs * 0.35), label,
           font=f, fill=(255, 255, 255, 255))
    if note:
        fs2 = max(9, int(fs * 0.55))
        f2 = font(fs2, bold=False)
        tw2, _ = text_size(d, note, f2)
        while tw2 > w * 0.94 and fs2 > 8:
            fs2 = max(8, int(fs2 * 0.9))
            f2 = font(fs2, bold=False)
            tw2, _ = text_size(d, note, f2)
        note = _fit(d, note, f2, w * 0.94)
        tw2, _ = text_size(d, note, f2)
        d.text(((w - tw2) / 2, (h - th) / 2 + fs * 0.95), note, font=f2,
               fill=(230, 230, 235, 220))
    img.alpha_composite(patch, (x0, y0))


# ----------------------------------------------------------------- shadow ----


def contact_shadow(img, view, W, H, cx, y_ground, foot_span, look, *,
                   height=None, strength=1.0):
    """The soft ellipse that puts a figure on the ground instead of on a wall.

    Without it a character is a sticker on a backdrop; it is the cheapest
    single thing in the renderer and the most obvious by its absence.

    The geometry is the style's: semi-axis `a` is the contact patch — the
    span between the feet, not the width of the whole silhouette, so a figure
    with its arms out does not grow a shadow — and `b` follows the figure's
    height, which is what makes a lamppost's shadow read as tighter than a
    car's. `sets.py` may publish the same helper; if it does it is preferred,
    so that actors and vehicles are lit by the same lamp.
    """
    fn = getattr(MODS.get("sets"), "contact_shadow", None)
    if callable(fn) and _names(fn, "foot_span"):
        try:
            kw = {}
            if _names(fn, "opacity"):
                kw["opacity"] = min(0.42, max(0.0, (SHADOW_ALPHA / 255.0)
                                              * float(strength)))
            fn(img, look, at=(cx, y_ground), unit=view.unit(W),
               origin=view.origin, foot_span=float(foot_span),
               height=float(height) if height else float(foot_span) * 2.4,
               **kw)
            return
        except Exception as exc:
            report("setsshadow",
                   f"sets.contact_shadow raised {type(exc).__name__}: {exc} — "
                   "using the renderer's own")

    u = view.unit(W)
    hgt = float(height) if height else float(foot_span) * 2.4
    rx = max(2.0, float(foot_span) * SHADOW_A * u)
    ry = max(1.2, hgt * SHADOW_B * u)
    x0, y0 = view.origin
    px = (cx - x0) * u
    py = (y_ground - y0) * u
    pad = int(max(4, ry * 1.6))
    bw = int(rx * 2 + pad * 2)
    bh = int(ry * 2 + pad * 2)
    if bw <= 0 or bh <= 0:
        return
    if px + rx + pad < 0 or px - rx - pad > W or py + ry + pad < 0 or py - ry - pad > H:
        return
    patch = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(patch).ellipse(
        [pad, pad, pad + rx * 2, pad + ry * 2],
        fill=int(SHADOW_ALPHA * max(0.0, min(1.6, strength))))
    patch = patch.filter(ImageFilter.GaussianBlur(max(1.2, ry * 0.55)))
    sh = Image.new("RGBA", (bw, bh), col(look, "shadow") + (0,))
    sh.putalpha(patch)
    img.alpha_composite(sh, (int(round(px - rx - pad)), int(round(py - ry - pad))))


# ------------------------------------------------------------------- film ----


class Film:
    """Everything needed to compose any frame of one board.

    Built once in the parent process; workers fork it, so the cost of setting
    it up is paid a single time however many jobs are asked for.
    """

    def __init__(self, board, sb_dir, W, H, fps, *, line_times=None,
                 quiet=False):
        self.board = board
        self.sb_dir = sb_dir
        self.W, self.H, self.fps = int(W), int(H), int(fps)
        self.seed = int(board.get("seed", 0) or 0)
        self.scene = SH.scene_box(self.W, self.H)
        warn = (lambda m: None) if quiet else (
            lambda m: report(*_warn_key(m)))
        self.shots = SH.build(board, line_times or {}, warn=warn)
        self.duration = self.shots.duration
        self.look = choose_look(board)
        self.cameras = {s.index: SH.Camera(s, self.scene, seed=self.seed,
                                          warn=None if quiet else _cam_warn)
                        for s in self.shots}
        self._cast_looks = {}

        sets_mod = MODS.get("sets")
        self._set_names = _registry(sets_mod, "SETS", "SET_LAYERS")
        self._prop_names = _registry(sets_mod, "PROPS", "PROP_ANCHOR")
        self._pose_names = set(getattr(MODS.get("poses"), "POSES", {}) or {})
        dp = getattr(sets_mod, "draw_prop", None)
        self._prop_takes_anim = _accepts(dp, "anim") if dp else False
        self._prop_takes_t = _names(dp, "t") if dp else False
        self._prop_owns_shadow = _names(dp, "shadow") if dp else False
        ds = getattr(sets_mod, "draw_set", None)
        self._set_takes_shot = _accepts(ds, "shot") if ds else False
        self._set_takes_mist = _accepts(ds, "mist") if ds else False
        # Rule 4: every actor stands on a soft, low-alpha ellipse. This module
        # draws it, so that actors and props share one shadow language and a
        # film always has exactly one shadow per figure. A rig that offers its
        # own is asked to stand down rather than stack a second on top.
        rd = getattr(MODS.get("rig"), "draw", None)
        self._rig_owns_shadow = _names(rd, "shadow") if rd else False
        self._rig_takes_ground = _names(rd, "ground") if rd else False

    # -- resolution --------------------------------------------------------

    def cast_look_for(self, cast_id):
        if cast_id not in self._cast_looks:
            self._cast_looks[cast_id] = cast_look(self.look, self.board,
                                                  cast_id)
        return self._cast_looks[cast_id]

    def preflight(self):
        """Name everything the modules cannot draw, before a frame is composed.

        Doing this in the parent means the report is printed once, in order,
        instead of once per forked worker in whatever order they got there.
        """
        missing = []
        for s in self.shots:
            if self._set_names and s.set not in self._set_names:
                missing.append(("set", s.set, s.id))
            for a in s.actors:
                act = a.get("action")
                names = ([k.get("pose") for k in act
                          if isinstance(k, dict)] if isinstance(act, list)
                         else [act or "stand"])
                for n in names:
                    if self._pose_names and n and n not in self._pose_names:
                        missing.append(("action", n, s.id))
                table = self.board.get("cast")
                if isinstance(table, dict) and a.get("cast") not in table:
                    missing.append(("cast", a.get("cast"), s.id))
            for p in s.props:
                k = p.get("kind")
                if self._prop_names and k not in self._prop_names:
                    missing.append(("prop", k, s.id))
            ov = s.overlay or {}
            if ov and ov.get("kind") not in OVERLAYS:
                missing.append(("overlay", ov.get("kind"), s.id))
        for kind, name, sid in missing:
            report(f"{kind}:{name}",
                   f"no {kind} called '{name}' (first wanted by shot '{sid}')"
                   " — drawing a labelled placeholder")
        self.pacing()
        self._check_parallax()
        return missing

    def _check_parallax(self):
        """Warn about a set that is too flat to read as depth.

        Three layers is the floor: something far that barely moves, the plane
        the characters stand on, and something between them. `sets.py`
        publishes its own layer rates; where it does, they are counted rather
        than assumed.
        """
        table = getattr(MODS.get("sets"), "SET_LAYERS", None)
        if not isinstance(table, dict):
            return
        for name in sorted({s.set for s in self.shots}):
            layers = table.get(name)
            if layers is None:
                continue
            try:
                rates = [float(r) for _, r in layers]
            except (TypeError, ValueError):
                continue
            if len(rates) < SH.PARALLAX_MIN_LAYERS:
                report(f"flat:{name}",
                       f"set '{name}' has {len(rates)} parallax layer(s) — "
                       f"under {SH.PARALLAX_MIN_LAYERS} there is no depth for "
                       "the camera to separate")
            elif max(rates) - min(rates) < 0.4:
                report(f"flatrate:{name}",
                       f"set '{name}' spreads its layers over only "
                       f"{max(rates) - min(rates):.2f} of parallax — the style"
                       f" runs far {SH.PARALLAX['far']} to fore "
                       f"{SH.PARALLAX['fore']}")

    def pacing(self, *, verbose=False):
        """Cutting-rhythm diagnostics. Advisory: nothing here stops a render.

        A film in this genre lives or dies on its cut, and the two ways to get
        it wrong are opposite: shots so short nothing registers, and a hold so
        brief it reads as a stumble rather than as the beat after a joke.
        """
        rep = SH.pacing_report(self.shots, self.fps)
        if verbose:
            print(f"  pacing   {rep['shots']} shots, mean {rep['mean']:.2f}s "
                  f"(median {rep['median']:.2f}, {rep['shortest']:.2f}"
                  f"–{rep['longest']:.2f}), {rep['cuts_per_min']:.1f} cuts/min,"
                  f" {rep['holds']} holds, {rep['impacts']} impacts")
        for note in rep["notes"]:
            report(*_warn_key("pacing: " + note))
        return rep
    # -- per-frame ---------------------------------------------------------

    def state(self, t):
        """`(shot, camera, view, t_local, t_pose, span)` at absolute time `t`.

        The camera is sampled at the true time and the poses at the quantised
        one. Everything downstream inherits that split from here: characters
        step at the shot's `on` — on twos that is fifteen drawings a second,
        which is the single loudest signal that a human drew this — while the
        camera, the parallax and the sets run on ones, because a camera
        quantised to twos judders and reads as a dropped frame.

        `span` is `(t_pose, t_next, frac)`: the interval the current drawing
        is held across and how far through it the true time is. It is what
        lets a smear frame escape the hold and be drawn on ones.
        """
        frame = int(round(float(t) * self.fps))
        shot = self.shots[self.shots.index_at(frame / float(self.fps))]
        cam = self.cameras[shot.index]
        t_local = shot.local(frame / float(self.fps))
        # Integer frame arithmetic, not float seconds: `frac` has to be
        # exactly 0.0 on a key drawing, or a rounding residue opens the smear
        # path on a shot that is already running on ones.
        lf = shot.local_frame(frame, self.fps)
        on = max(1, shot.on_at(frame, self.fps))
        pf = SH.quantise_frame(lf, on)
        t_pose = pf / float(self.fps)
        frac = 0.0 if on <= 1 else (lf - pf) / float(on)
        span = (t_pose, min((pf + on) / float(self.fps), shot.dur), frac)
        subject = None
        if cam.move == "follow":
            a = shot.actor(cam.subject) if cam.subject else None
            if a is not None:
                subject = lambda tt, _a=a, _s=shot: SH.actor_at(
                    _a, _s.pose_time(int(round((_s.start + tt) * self.fps)),
                                     self.fps), _s.dur)
            elif cam.subject:
                report(f"subject:{shot.id}:{cam.subject}",
                       f"shot '{shot.id}' follows actor '{cam.subject}', which "
                       "is not in the shot — holding the authored framing")
        return shot, cam, cam.view(t_local, subject), t_local, t_pose, span

    def compose(self, t):
        """One finished frame as an `(H, W, 3)` uint8 array."""
        W, H = self.W, self.H
        shot, cam, view, t_local, t_pose, span = self.state(t)
        img = Image.new("RGBA", (W, H), col(self.look, "sky") + (255,))

        self._draw_set(img, shot, view, t_local)

        # Draw order, back to front: set, distant props, actors far -> near,
        # near props, overlays. Ties keep the board's own order, so an author
        # can settle an ambiguity by moving a line.
        far_props, near_props = [], []
        for i, p in enumerate(shot.props):
            (far_props if _is_far_prop(p) else near_props).append((i, p))
        far_props.sort(key=lambda ip: (-_z_of(ip[1], 0.75), ip[0]))
        near_props.sort(key=lambda ip: (-_z_of(ip[1], 0.35), ip[0]))
        actors = sorted(enumerate(shot.actors),
                        key=lambda ia: (-_z_of(ia[1], 0.5), ia[0]))

        for _, p in far_props:
            self._draw_prop(img, shot, p, view, t_local, t_pose)
        for _, a in actors:
            self._draw_actor(img, shot, a, view, t_pose, t_local, span)
        for _, p in near_props:
            self._draw_prop(img, shot, p, view, t_local, t_pose)

        if shot.overlay:
            self._draw_overlay(img, shot, view, t_local)

        arr = np.asarray(img.convert("RGB"), dtype=np.uint8)
        if view.blur > 0.06:
            arr = _whip_blur(arr, view, cam)
        return arr

    # -- layers ------------------------------------------------------------

    def _camera_dict(self, shot, cam, view):
        d = view.as_dict()
        d.update({"move": cam.move, "shot": shot.id,
                  "base_cx": cam.p0[0], "base_cy": cam.p0[1],
                  "dx": view.cx - cam.p0[0], "dy": view.cy - cam.p0[1],
                  "scene_w": self.scene[0], "scene_h": self.scene[1],
                  # One parallax table for the whole style, so a set built by
                  # a different hand still separates by the same amounts. A
                  # layer at rate `r` is displaced by `(1 - r) * (dx, dy)`:
                  # the character plane at 1.0 is pinned to the camera, the
                  # far background at 0.18 barely follows it, the foreground
                  # at 1.5 slides the other way. Three layers is the minimum.
                  "parallax": SH.PARALLAX,
                  "min_layers": SH.PARALLAX_MIN_LAYERS,
                  "still": cam.still, "on": shot.on})
        return d

    def _draw_set(self, img, shot, view, t_local):
        sets_mod = MODS.get("sets")
        if sets_mod is None:
            need("sets", why="draw a set")
        if self._set_names and shot.set not in self._set_names:
            placeholder(img, (0, 0, self.W, self.H), f"MISSING SET: {shot.set}",
                        self.look, note=f"shot {shot.id}")
            return
        cam = self.cameras[shot.index]
        try:
            # The set gets the *true* shot-local time, not the quantised one:
            # rotors, flashing lights and wheels live on their own clock, and
            # `sets.py` owns the decision about what rate they run at.
            kw = {}
            # A continuous set parameter -- how thick the weather is -- is
            # only meaningful to sets that model weather, and passing it to
            # one that does not is a TypeError that would be caught below and
            # silently downgraded to a placeholder. So it is offered rather
            # than imposed: asked for by name, and only if the signature has
            # somewhere to put it.
            mist = shot.raw.get("mist")
            if mist is not None and self._set_takes_mist:
                kw["mist"] = float(mist)
            sets_mod.draw_set(img, shot.set, self.look, unit=view.unit(self.W),
                              origin=view.origin, t=t_local,
                              camera=self._camera_dict(shot, cam, view),
                              seed=self.seed ^ shot.seed, **kw)
        except Exception as exc:
            report(f"setfail:{shot.set}",
                   f"sets.draw_set('{shot.set}') raised {type(exc).__name__}: "
                   f"{exc} — drawing a placeholder")
            placeholder(img, (0, 0, self.W, self.H), f"SET FAILED: {shot.set}",
                        self.look, note=f"{type(exc).__name__}: {exc}"[:90])

    def _draw_prop(self, img, shot, prop, view, t_local, t_pose):
        sets_mod = MODS.get("sets")
        if sets_mod is None:
            need("sets", why="draw a prop")
        kind = prop.get("kind")
        at = _pt(prop.get("at"), (self.scene[0] / 2, self.scene[1] * 0.78))
        scale = float(prop.get("scale", 1.0) or 1.0)
        u = view.unit(self.W)

        bb = self._prop_bbox(kind, scale)
        if prop.get("shadow", True) and bb and not _is_far_prop(prop, 0.9):
            # A prop's contact patch is the whole footprint — a car sits on
            # four wheels a car's width apart — so the span is its full width.
            contact_shadow(img, view, self.W, self.H,
                           at[0] + (bb[0] + bb[2]) / 2.0, at[1] + bb[3],
                           max(bb[2] - bb[0], 1.0), self.look,
                           height=max(bb[3] - bb[1], 1.0),
                           strength=0.85)

        if self._prop_names and kind not in self._prop_names:
            box = bb or (-4.0 * scale, -6.0 * scale, 4.0 * scale, 0.0)
            x0, y0 = view.origin
            placeholder(img,
                        ((at[0] + box[0] - x0) * u, (at[1] + box[1] - y0) * u,
                         (at[0] + box[2] - x0) * u, (at[1] + box[3] - y0) * u),
                        f"PROP: {kind}", self.look, note=f"shot {shot.id}")
            return

        # A prop's `phase` is its own animation input, and it is quantised with
        # the characters: a prop is a drawing too, and a wheel that turns on
        # ones beside a body on twos separates from it.
        rate = float(prop.get("rate", 1.0) or 0.0) if prop.get("anim") else 0.0
        phase = (float(prop.get("phase", 0.0)) + t_pose * rate) % 1.0
        kw = {}
        if self._prop_takes_anim and prop.get("anim"):
            kw["anim"] = prop["anim"]
        if self._prop_takes_t:
            # A prop's own clock, unquantised, for the parts of it that are
            # scenery rather than drawing — a beacon, a wiper, a flag.
            kw["t"] = t_local
        if self._prop_owns_shadow:
            kw["shadow"] = False        # rule 4 is this module's job; see Film
        try:
            sets_mod.draw_prop(img, kind, self.look, at=at, unit=u,
                               origin=view.origin, scale=scale, phase=phase,
                               seed=(self.seed ^ shot.seed
                                     ^ SH._seed_of(kind, at[0], at[1])) & 0x7FFFFFFF,
                               **kw)
        except Exception as exc:
            report(f"propfail:{kind}",
                   f"sets.draw_prop('{kind}') raised {type(exc).__name__}: "
                   f"{exc} — drawing a placeholder")
            box = bb or (-4.0 * scale, -6.0 * scale, 4.0 * scale, 0.0)
            x0, y0 = view.origin
            placeholder(img,
                        ((at[0] + box[0] - x0) * u, (at[1] + box[1] - y0) * u,
                         (at[0] + box[2] - x0) * u, (at[1] + box[3] - y0) * u),
                        f"PROP FAILED: {kind}", self.look)

    def _prop_bbox(self, kind, scale):
        fn = getattr(MODS.get("sets"), "prop_bbox", None)
        if fn is None:
            return None
        try:
            bb = fn(kind, scale)
            return tuple(float(v) for v in bb[:4])
        except Exception:
            return None

    def _draw_actor(self, img, shot, actor, view, t_pose, t_local, span=None):
        rig = MODS.get("rig")
        if rig is None:
            need("rig", why="draw a character")
        u = view.unit(self.W)
        z = _z_of(actor, 0.5)
        look = self.cast_look_for(actor.get("cast"))
        pose = self._pose_for(shot, actor, t_pose, span)
        at = SH.actor_at(actor, t_pose, shot.dur)
        height = float(actor.get("height", 18.0) or 18.0)

        if pose is None or look is None:
            x0, y0 = view.origin
            placeholder(img,
                        ((at[0] - height * 0.28 - x0) * u,
                         (at[1] - height * 0.62 - y0) * u,
                         (at[0] + height * 0.28 - x0) * u,
                         (at[1] + height * 0.44 - y0) * u),
                        f"{'CAST' if look is None else 'ACTION'}: "
                        f"{actor.get('cast') if look is None else _action_name(actor)}",
                        self.look, note=f"{actor.get('id', '?')} in {shot.id}")
            return

        if actor.get("shadow", True):
            bb = self._pose_bbox(pose, pose.get("at") or at, height)
            span, feet = self._foot_span(pose, height)
            contact_shadow(img, view, self.W, self.H,
                           feet if feet is not None else (bb[0] + bb[2]) / 2.0,
                           bb[3], span, self.look, height=height,
                           strength=1.0 - 0.45 * z)
        kw = {}
        if self._rig_owns_shadow:
            kw["shadow"] = False
        elif self._rig_takes_ground:
            kw["ground"] = at[1]
        try:
            rig.draw(img, pose, look, unit=u, origin=view.origin, z=z, **kw)
        except Exception as exc:
            report(f"rigfail:{_action_name(actor)}",
                   f"rig.draw raised {type(exc).__name__}: {exc} for actor "
                   f"'{actor.get('id')}' — drawing a placeholder")
            x0, y0 = view.origin
            placeholder(img,
                        ((at[0] - height * 0.28 - x0) * u,
                         (at[1] - height * 0.62 - y0) * u,
                         (at[0] + height * 0.28 - x0) * u,
                         (at[1] + height * 0.44 - y0) * u),
                        "RIG FAILED", self.look, note=str(exc)[:80])

    def _foot_span(self, pose, height):
        """`(span, centre_x)` of the contact patch, in scene units.

        The shadow belongs under the feet, not under the silhouette: a figure
        pointing at something has a wide bbox and exactly the same two shoes
        on the ground. `rig.solve` knows where they are; without it, a guess
        scaled off the height is still closer than the bbox.
        """
        fn = getattr(MODS.get("rig"), "solve", None)
        if fn is not None:
            try:
                j = fn(pose)
                pts = [j[k] for k in ("foot.l", "foot.r", "ankle.l", "ankle.r")
                       if k in j]
                if len(pts) >= 2:
                    xs = [float(p[0]) for p in pts]
                    span = max(xs) - min(xs)
                    # Both feet together is still a foot-wide contact patch.
                    return (max(span, height * 0.16),
                            (max(xs) + min(xs)) / 2.0)
            except Exception:
                pass
        return (height * 0.30, None)

    def _pose_bbox(self, pose, at, height):
        fn = getattr(MODS.get("rig"), "bbox", None)
        if fn is not None:
            try:
                bb = tuple(float(v) for v in fn(pose)[:4])
                if bb[2] > bb[0] and bb[3] > bb[1]:
                    return bb
            except Exception:
                pass
        return (at[0] - height * 0.22, at[1] - height * 0.6,
                at[0] + height * 0.22, at[1] + height * 0.44)

    def _pose_for(self, shot, actor, t_pose, span=None):
        """The drawing on screen, with a smear allowed to break the hold.

        Holding a drawing for two frames is the style. The exception is the
        frame where a limb crosses more distance than the eye can follow:
        `anim.smear` decides whether that has happened, and if it has, the
        drawing is rebuilt every frame across the held interval, because a
        smear that is itself held for two frames reads as a rendering fault
        rather than as speed. `anim.smear` returns `None` on anything slow,
        so this costs nothing on a quiet shot.
        """
        pose = self._pose_at(shot, actor, t_pose)
        anim_mod = MODS.get("anim")
        if (pose is None or not span or span[2] <= 0.0
                or anim_mod is None or not hasattr(anim_mod, "smear")):
            return pose
        if shot.is_hold:
            # A hold is the beat after the joke, and it is load-bearing. On
            # threes even a gentle idle puts a big delta between consecutive
            # drawings, which reads to `anim.smear` as speed — so the one
            # place the renderer would add motion to a held shot is the one
            # place it is refused.
            return pose
        t_pose, t_next, frac = span
        if t_next <= t_pose:
            return pose
        nxt = self._pose_at(shot, actor, t_next)
        if nxt is None:
            return pose
        try:
            sm = anim_mod.smear(pose, nxt, frac)
        except Exception as exc:
            report("smearfail",
                   f"anim.smear raised {type(exc).__name__}: {exc} — holding "
                   "the drawing")
            return pose
        if not sm:
            return pose
        sm = dict(sm)
        a0 = pose.get("at") or [0.0, 0.0]
        a1 = nxt.get("at") or a0
        sm["at"] = [a0[0] + (a1[0] - a0[0]) * frac,
                    a0[1] + (a1[1] - a0[1]) * frac]
        return sm

    def _pose_at(self, shot, actor, t_pose):
        """The drawing an actor is holding at the quantised time.

        A cycle is a phase function; a keyframed action is a track between
        poses. Both are evaluated at the *current* phase, so a keyframe that
        names `walk` keeps walking while it blends toward the next key rather
        than freezing on the cycle's first drawing.

        The pose's own `at` is **composed** with the board's staging, never
        substituted for it. A cycle returns a pelvis, and that pelvis carries
        the gait's bob — it rises twice per stride, over each planted leg —
        along with any lateral weight shift an idle has. Overwriting `at` with
        the staged position throws all of that away and pins the pelvis to a
        rail, which is most of the difference between a walk and a slide.
        `_gait_plan` decides who owns the horizontal, `_compose_at` puts the
        two contributions back together.
        """
        poses_mod, anim_mod = MODS.get("poses"), MODS.get("anim")
        if poses_mod is None:
            need("poses", why="pose a character")
        staged = tuple(SH.actor_at(actor, t_pose, shot.dur))
        facing = int(actor.get("facing", 1) or 1)
        height = float(actor.get("height",
                                 getattr(poses_mod, "H_DEF", 18.0)))
        plan = self._gait_plan(shot, actor, height, facing)
        phase = (SH.gait_phase(actor, t_pose, shot.dur, stride=plan.stride,
                               facing=facing) if plan.locked
                 else SH.actor_phase(actor, t_pose, wrap=not plan.travel))
        stage_kw = {"at": staged, "height": height, "facing": facing,
                    "travel": plan.travel}
        action = actor.get("action")

        if isinstance(action, list):
            if anim_mod is None:
                need("anim", why="run a keyframed action")
            keys = []
            for k in action:
                if not isinstance(k, dict):
                    continue
                kw = _pose_kwargs(k)
                kw.update(stage_kw)
                p = self._call_pose(k.get("pose"), phase, kw)
                if p is None:
                    return None
                keys.append({"t": float(k.get("t", 0.0)), "pose": p,
                             "ease": k.get("ease", SH.KEY_EASE)})
            if not keys:
                return None
            try:
                pose = anim_mod.track(keys, t_pose)
            except Exception as exc:
                report("trackfail",
                       f"anim.track raised {type(exc).__name__}: {exc} — "
                       "holding the first key")
                pose = keys[0]["pose"]
        else:
            kw = _pose_kwargs(actor)
            kw.update(stage_kw)
            pose = self._call_pose(action or "stand", phase, kw)
            if pose is None:
                return None

        pose = dict(pose)
        pose["at"] = self._compose_at(actor, pose, staged, facing, plan, phase)
        pose["facing"] = int(actor.get("facing", pose.get("facing", 1)) or 1)
        pose["height"] = float(actor.get("height", pose.get("height", 18.0)))
        sq = actor.get("squash")
        if isinstance(sq, dict) and anim_mod is not None:
            try:
                pose["squash"] = float(anim_mod.squash_stretch(
                    float(pose.get("squash", 1.0)),
                    impact=float(sq.get("impact", 0.25)),
                    decay=float(sq.get("decay", 6.0)),
                    t=t_pose - float(sq.get("at", 0.0))))
            except Exception:
                pass
        if actor.get("tilt") is not None:
            pose["tilt"] = float(actor["tilt"])
        # Which physical build the rig draws. `rig.py` selects its bone and
        # width tables from `pose["bones"]`, so without this the alternative
        # builds it publishes are unreachable from a board -- the film could
        # only ever be cast with the house figure.
        if actor.get("bones") is not None:
            pose["bones"] = actor["bones"]
        return pose

    def _gait_plan(self, shot, actor, height, facing):
        """Who owns this actor's horizontal, and at what cadence.

        A gait plants its feet *against its own travel*: through stance the
        foot slides backwards relative to the pelvis at exactly the stride
        rate, so a pelvis advancing at that rate leaves the foot still. Only
        `poses.stride_units` knows what that rate is, and any other rate is
        foot slide. There are therefore exactly two coherent arrangements, and
        the choice is made per actor:

        `staged` — the board gives a `to` or a keyframed path, so the board
            owns the trajectory. The gait's own travel is switched off and the
            **phase is locked to the distance actually covered**, which plants
            the foot whether or not `to` agrees with `rate x stride x dur`.
            The board's `rate` is a request; the ground overrules it.

        `cycle`  — the board stages the actor on the spot, which is a
            treadmill: the set scrolls past a character who does not move. The
            gait's travel stays off and the board's `rate` drives the cycle.

        A board that wants the third arrangement — the cycle carrying the
        character across the scene under its own power — asks for it with
        `travel: true`, and then gets an unwrapped phase, because a wrapped
        one would snap it back a full stride once a cycle.
        """
        want = actor.get("travel")
        stride = self._stride_units(_action_name(actor), height)
        if want is not None:
            return _GaitPlan(stride, bool(want), False, "gait")
        if stride > 0.0 and SH.stages_travel(actor, shot.dur):
            self._check_cadence(shot, actor, stride)
            return _GaitPlan(stride, False, True, "staged")
        return _GaitPlan(stride, False, False, "cycle")

    def _stride_units(self, action, height):
        """Scene units a named gait covers per cycle; 0 for anything that is
        not a gait, which is most of the vocabulary."""
        fn = getattr(MODS.get("poses"), "stride_units", None)
        if not callable(fn):
            return 0.0
        best = 0.0
        for name in str(action).split("+"):
            try:
                best = max(best, abs(float(fn(name.strip(), height))))
            except Exception:
                continue
        return best

    def _check_cadence(self, shot, actor, stride):
        """Tell an author when their `to` is about to retime their walk.

        Foot-locking always wins, so this never changes what is rendered — but
        a walk asked to cover twice the ground in the same time becomes a run,
        and the author should hear that from the renderer rather than discover
        it in the file.
        """
        want = float(actor.get("rate", 1.0) or 0.0)
        if want <= 0.0:
            return
        got = SH.implied_rate(actor, shot.dur, stride=stride)
        if got <= 0.0 or 0.75 <= got / want <= 1.34:
            return
        report(f"cadence:{shot.id}:{actor.get('id')}",
               f"{shot.id}/{actor.get('id', '?')}: rate {want:.2f} c/s is "
               f"authored but the staged travel implies {got:.2f} c/s — "
               f"foot-locking to the travel, because the alternative is "
               f"{abs(got - want) * stride:.1f} units/s of foot slide")

    def _compose_at(self, actor, pose, staged, facing, plan, phase=0.0):
        """The board's staging plus the pose's own excursion.

        The pose returns a pelvis, not a position: its `at` is the staged
        point *plus* whatever the body is doing to it — the bob that rises
        twice a stride over each planted leg, an idle's slow weight shift,
        and, if the cycle owns the travel, the travel too. Every one of those
        is measured back out here and re-applied to wherever the board has
        actually put the actor, so staging and animation compose instead of
        one overwriting the other.

        The horizontal part is mirrored by `facing`, because a cycle's travel
        is forward in *body* space while `at` is in scene space, and `poses`
        does not apply the sign itself.
        """
        raw = pose.get("at")
        if raw is None:
            return list(staged)
        try:
            dx = float(raw[0]) - staged[0]
            dy = float(raw[1]) - staged[1]
        except (TypeError, ValueError, IndexError):
            return list(staged)
        # The vertical excursion is a bob and is bounded. The horizontal one
        # is bounded too, unless the cycle is carrying the character itself,
        # in which case it grows by a stride per cycle and the bound has to
        # grow with it.
        bound = POSE_EXCURSION * float(pose.get("height", 18.0))
        bx = (plan.stride * (abs(float(phase)) + 1.0) + bound if plan.travel
              else bound) + 1e-6
        if abs(dx) > bx or abs(dy) > bound + 1e-6:
            # The pose ignored the stage we handed it, so its `at` is an
            # absolute position from somewhere else and the difference is not
            # an excursion. Stage it ourselves and say so.
            report(f"stageless:{_action_name(actor)}",
                   f"pose '{_action_name(actor)}' ignored the staged `at` "
                   f"(off by {math.hypot(dx, dy):.1f} units) — staging it "
                   f"from the board instead, so its bob is lost")
            return list(staged)
        return [staged[0] + facing * dx, staged[1] + dy]

    def _call_pose(self, name, phase, kwargs):
        poses_mod = MODS["poses"]
        table = getattr(poses_mod, "POSES", {}) or {}
        fn = table.get(name) or getattr(poses_mod, str(name or ""), None)
        if not callable(fn):
            report(f"action:{name}",
                   f"no pose called '{name}' in poses.POSES "
                   f"({', '.join(sorted(table)) or 'empty'}) — placeholder")
            return None
        try:
            return fn(phase, **kwargs)
        except TypeError:
            try:
                return fn(phase)
            except Exception as exc:
                report(f"posefail:{name}",
                       f"poses.{name} raised {type(exc).__name__}: {exc}")
                return None
        except Exception as exc:
            report(f"posefail:{name}",
                   f"poses.{name} raised {type(exc).__name__}: {exc}")
            return None

    # -- overlays ----------------------------------------------------------

    def _draw_overlay(self, img, shot, view, t_local):
        ov = shot.overlay or {}
        kind = str(ov.get("kind", "") or "")
        fn = OVERLAYS.get(kind)
        if fn is None:
            W = self.W
            placeholder(img, (W * SAFE, self.H * 0.82, W * (1 - SAFE),
                              self.H * 0.94),
                        f"OVERLAY: {kind or '(none)'}", self.look,
                        note=f"shot {shot.id}")
            return
        try:
            fn(self, img, shot, ov, view, t_local)
        except Exception as exc:
            report(f"overlayfail:{kind}",
                   f"overlay '{kind}' raised {type(exc).__name__}: {exc}")


def _pose_kwargs(spec):
    """Everything in an actor or keyframe that is not the renderer's business.

    `point(dir=-1)` and `react(kind="shock")` take their arguments straight
    from the board this way, without the renderer having to know the pose
    vocabulary.
    """
    skip = {"id", "cast", "action", "at", "to", "facing", "rate", "phase",
            "height", "z", "ease", "squash", "tilt", "shadow", "t", "pose",
            "note"}
    return {k: v for k, v in spec.items() if k not in skip}


def _action_name(actor):
    a = actor.get("action")
    if isinstance(a, list):
        return "+".join(str(k.get("pose")) for k in a if isinstance(k, dict))
    return str(a or "stand")


def _z_of(spec, default):
    try:
        return float(spec.get("z", default))
    except (TypeError, ValueError):
        return default


def _is_far_prop(prop, threshold=0.55):
    """Does this prop belong behind the actors?

    `layer` settles it outright; otherwise depth does, and a prop with no
    depth at all sits in front, because the common foreground prop — a car, a
    desk, a parapet — is the one an actor is meant to be tucked behind.
    """
    layer = str(prop.get("layer", "") or "").lower()
    if layer in ("back", "far", "behind"):
        return True
    if layer in ("front", "near", "fore"):
        return False
    return _z_of(prop, 0.5) > threshold


def _pt(v, default):
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return (float(v[0]), float(v[1]))
    return (float(default[0]), float(default[1]))


def _whip_blur(arr, view, cam):
    """Smear a whip pan along its own axis.

    A whip that is not blurred is just a very fast pan, and reads as a mistake
    at the frame rate rather than as a move.
    """
    dx = cam.p1[0] - cam.p0[0]
    dy = cam.p1[1] - cam.p0[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return arr
    span = int(round(min(28.0, 30.0 * view.blur)))
    if span < 2:
        return arr
    ux, uy = dx / n, dy / n
    acc = np.zeros(arr.shape, dtype=np.float32)
    taps = 5
    for k in range(taps):
        off = (k / (taps - 1.0) - 0.5) * span
        sx, sy = int(round(-ux * off)), int(round(-uy * off))
        acc += np.roll(np.roll(arr, sy, axis=0), sx, axis=1)
    return (acc / taps).astype(np.uint8)


# --------------------------------------------------------------- overlays ----
#
# The only place text appears in this style, and therefore the only place
# legibility is the renderer's problem rather than the rig's. Everything here
# is drawn at final resolution with hard edges — a chyron that has been
# resampled reads as a screenshot of a chyron.


def _panel(d, box, fill, *, radius=0, outline=None, width=2):
    if radius:
        d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline,
                            width=width)
    else:
        d.rectangle(box, fill=fill, outline=outline, width=width)


def _ov_chyron(film, img, shot, ov, view, t_local):
    W, H = film.W, film.H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # Wipe on over a third of a second and off before the cut, so the
    # furniture arrives and leaves rather than blinking.
    tin = min(1.0, t_local / 0.35)
    tout = min(1.0, max(0.0, (shot.dur - t_local) / 0.30))
    reveal = SH.ease("out", tin) * SH.ease("out", tout)
    if reveal <= 0.01:
        return
    fs = int(H * 0.042)
    pad = int(H * 0.020)
    bar_h = fs + pad * 2
    y1 = int(H * (1 - SAFE * 1.6))
    y0 = y1 - bar_h
    x0 = int(W * SAFE)
    kicker = str(ov.get("kicker", "") or "")
    f = font(fs)
    fk = font(int(fs * 0.62))
    text = str(ov.get("text", "") or "")
    tw, _ = text_size(d, text, f)
    kw_ = (text_size(d, kicker, fk)[0] + pad * 2) if kicker else 0
    total = int(min(W * (1 - SAFE * 2), tw + pad * 3 + kw_))
    x1 = x0 + int(total * reveal)
    plate = _plate(film.look)
    # The hairline round the plate comes from look.py when it offers one, so
    # a hued palette gets its own line instead of a black one.
    _panel(d, [x0, y0, x1, y1], plate + (232,), width=1,
           outline=outline_for(film.look, plate) + (200,))
    if kicker:
        kx1 = x0 + int(kw_ * min(1.0, reveal * 2.2))
        _panel(d, [x0, y0, kx1, y1], col(film.look, "accent") + (255,))
        if kx1 - x0 > kw_ * 0.75:
            d.text((x0 + pad, y0 + (bar_h - fs * 0.62) / 2 - fs * 0.08), kicker,
                   font=fk, fill=(255, 255, 255, 255))
    if x1 - x0 > kw_ + pad:
        clip = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dc = ImageDraw.Draw(clip)
        dc.text((x0 + kw_ + pad, y0 + (bar_h - fs) / 2 - fs * 0.12), text,
                font=f, fill=(246, 247, 250, 255))
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle([x0, y0, x1, y1], fill=255)
        lay.paste(clip, (0, 0), Image.composite(clip.getchannel("A"),
                                                Image.new("L", (W, H), 0), mask))
    d.line([(x0, y1), (x1, y1)], fill=col(film.look, "accent") + (255,),
           width=max(2, int(H * 0.004)))
    img.alpha_composite(lay)


def _ov_title(film, img, shot, ov, view, t_local):
    W, H = film.W, film.H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    u = SH.ease("out", min(1.0, t_local / 0.5))
    fade = min(1.0, max(0.0, (shot.dur - t_local) / 0.35))
    a = int(255 * u * fade)
    if a <= 4:
        return
    text = str(ov.get("text", "") or "")
    sub = str(ov.get("sub", "") or "")
    fs = int(H * 0.115)
    f = font(fs)
    tw, th = text_size(d, text, f)
    while tw > W * (1 - SAFE * 3) and fs > 14:
        fs = int(fs * 0.92)
        f = font(fs)
        tw, th = text_size(d, text, f)
    cx, cy = W / 2, H * 0.46
    rise = (1 - u) * H * 0.03
    d.text((cx - tw / 2, cy - th / 2 + rise), text, font=f,
           fill=(250, 250, 252, a),
           stroke_width=max(2, int(fs * 0.05)),
           stroke_fill=_plate(film.look) + (min(255, a),))
    rule_w = int((tw * 0.5) * u)
    d.line([(cx - rule_w, cy + th * 0.78), (cx + rule_w, cy + th * 0.78)],
           fill=col(film.look, "accent") + (a,), width=max(3, int(H * 0.006)))
    if sub:
        fs2 = int(fs * 0.32)
        f2 = font(fs2, bold=False)
        sw, sh = text_size(d, sub, f2)
        d.text((cx - sw / 2, cy + th * 0.78 + sh * 0.7), sub, font=f2,
               fill=(238, 238, 242, a), stroke_width=max(1, int(fs2 * 0.06)),
               stroke_fill=_plate(film.look) + (min(255, a),))
    img.alpha_composite(lay)


def _ov_map(film, img, shot, ov, view, t_local):
    W, H = film.W, film.H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    reveal = SH.ease("out", min(1.0, t_local / 0.4))
    mw, mh = int(W * 0.26), int(H * 0.30)
    x0 = int(W * (1 - SAFE) - mw)
    y0 = int(H * SAFE * 1.4)
    r = int(min(mw, mh) * 0.06)
    _panel(d, [x0, y0, x0 + mw, y0 + mh], _plate(film.look, 0.30) + (225,),
           radius=r, outline=col(film.look, "accent") + (255,),
           width=max(2, int(H * 0.003)))
    inner = (x0 + mw * 0.08, y0 + mh * 0.16, x0 + mw * 0.92, y0 + mh * 0.88)
    # A grid, so the panel reads as a map rather than as a dark rectangle.
    grid = col(film.look, "mid") + (90,)
    for i in range(1, 5):
        gx = inner[0] + (inner[2] - inner[0]) * i / 5.0
        gy = inner[1] + (inner[3] - inner[1]) * i / 5.0
        d.line([(gx, inner[1]), (gx, inner[3])], fill=grid, width=1)
        d.line([(inner[0], gy), (inner[2], gy)], fill=grid, width=1)

    route = ov.get("route")
    pts = []
    if isinstance(route, (list, tuple)):
        for p in route:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                pts.append((inner[0] + (inner[2] - inner[0]) * float(p[0]),
                            inner[1] + (inner[3] - inner[1]) * float(p[1])))
    if len(pts) >= 2:
        n = max(2, int(len(pts) * reveal + 0.999))
        d.line(pts[:n], fill=col(film.look, "accent") + (255,),
               width=max(3, int(H * 0.005)), joint="curve")
    label = route if isinstance(route, str) else ov.get("label")
    if label:
        fl = font(int(mh * 0.13), bold=True)
        d.text((x0 + mw * 0.08, y0 + mh * 0.03), str(label)[:26], font=fl,
               fill=(240, 240, 245, 255))

    marker = ov.get("marker")
    mp = None
    if isinstance(marker, (list, tuple)) and len(marker) >= 2:
        mp = (inner[0] + (inner[2] - inner[0]) * float(marker[0]),
              inner[1] + (inner[3] - inner[1]) * float(marker[1]))
    elif pts:
        mp = pts[min(len(pts) - 1, int((len(pts) - 1) * reveal))]
    if mp:
        # A slow pulse, on the film's clock, so the panel is never inert.
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 0.8 * (shot.start + t_local))
        rr = max(3.0, mh * (0.030 + 0.020 * pulse))
        d.ellipse([mp[0] - rr * 2.1, mp[1] - rr * 2.1, mp[0] + rr * 2.1,
                   mp[1] + rr * 2.1],
                  outline=col(film.look, "accent2") + (int(90 + 90 * (1 - pulse)),),
                  width=max(2, int(H * 0.002)))
        d.ellipse([mp[0] - rr, mp[1] - rr, mp[0] + rr, mp[1] + rr],
                  fill=col(film.look, "accent2") + (255,))
    img.alpha_composite(lay)


def _ov_circle(film, img, shot, ov, view, t_local):
    """The news-feed ring: a target being called out inside a live picture."""
    W, H = film.W, film.H
    target = ov.get("target")
    pos = None
    size = 6.0
    a = shot.actor(target) if target else None
    if a is not None:
        pos = SH.actor_at(a, shot.pose_time(int(round((shot.start + t_local)
                                                      * film.fps)), film.fps),
                          shot.dur)
        h = float(a.get("height", 18.0) or 18.0)
        pos = (pos[0], pos[1] - h * 0.30)
        size = h * 0.62
    else:
        for p in shot.props:
            if target in (p.get("id"), p.get("kind")):
                pos = _pt(p.get("at"), (film.scene[0] / 2, film.scene[1] / 2))
                bb = film._prop_bbox(p.get("kind"),
                                     float(p.get("scale", 1.0) or 1.0))
                if bb:
                    pos = (pos[0] + (bb[0] + bb[2]) / 2,
                           pos[1] + (bb[1] + bb[3]) / 2)
                    size = max(bb[2] - bb[0], bb[3] - bb[1]) * 0.75
                break
    if pos is None:
        report(f"circle:{shot.id}:{target}",
               f"overlay circle in shot '{shot.id}' targets '{target}', which "
               "is not an actor or prop in the shot")
        return
    u = view.unit(W)
    x0, y0 = view.origin
    px, py = (pos[0] - x0) * u, (pos[1] - y0) * u
    r = max(18.0, size * 0.5 * u)
    grow = SH.ease("overshoot", min(1.0, t_local / 0.45))
    r *= 0.6 + 0.4 * grow
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    acc = col(film.look, "accent")
    d.ellipse([px - r, py - r, px + r, py + r], outline=acc + (255,),
              width=max(3, int(H * 0.005)))
    d.ellipse([px - r * 1.14, py - r * 1.14, px + r * 1.14, py + r * 1.14],
              outline=acc + (90,), width=max(1, int(H * 0.002)))
    # Leader line out to a label, away from the middle of the frame.
    side = 1 if px < W * 0.5 else -1
    lx = px + side * r * 1.25
    ly = py - r * 0.75
    ex = lx + side * W * 0.055
    d.line([(lx, ly), (ex, ly - H * 0.03)], fill=acc + (255,),
           width=max(2, int(H * 0.003)))
    lab = str(ov.get("label", target) or "")
    if lab:
        f = font(int(H * 0.030))
        tw, th = text_size(d, lab, f)
        tx = ex if side > 0 else ex - tw
        ty = ly - H * 0.03 - th * 1.55
        _panel(d, [tx - th * 0.4, ty - th * 0.25, tx + tw + th * 0.4,
                   ty + th * 1.3], _plate(film.look) + (230,))
        d.text((tx, ty), lab, font=f, fill=(246, 246, 250, 255))
    img.alpha_composite(lay)


def _ov_split(film, img, shot, ov, view, t_local):
    """Two pictures at once — the only time this style shows more than one."""
    W, H = film.W, film.H
    sets_mod = MODS.get("sets")
    wipe = SH.ease("inout", min(1.0, t_local / 0.4))
    vertical = W >= H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    halves = []
    for side in ("left", "right"):
        name = ov.get(side)
        if not name or name == shot.set:
            halves.append(None)          # the live picture stays on this side
            continue
        half = Image.new("RGBA", (W, H), col(film.look, "sky") + (255,))
        known = getattr(sets_mod, "SETS", {}) or {}
        if known and name not in known:
            placeholder(half, (0, 0, W, H), f"MISSING SET: {name}", film.look,
                        note=f"{side} of split in {shot.id}")
        else:
            try:
                sets_mod.draw_set(half, name, film.look, unit=view.unit(W),
                                  origin=view.origin, t=t_local,
                                  camera=view.as_dict(),
                                  seed=film.seed ^ SH._seed_of(name, side))
            except Exception as exc:
                placeholder(half, (0, 0, W, H), f"SET FAILED: {name}",
                            film.look, note=str(exc)[:80])
        halves.append(half)

    edge = int((W if vertical else H) * 0.5)
    for i, half in enumerate(halves):
        if half is None:
            continue
        if vertical:
            box = (0, 0, edge, H) if i == 0 else (edge, 0, W, H)
        else:
            box = (0, 0, W, edge) if i == 0 else (0, edge, W, H)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rectangle(list(box), fill=int(255 * wipe))
        lay.paste(half, (0, 0), mask)
    d = ImageDraw.Draw(lay)
    thick = max(3, int(min(W, H) * 0.006))
    if vertical:
        d.rectangle([edge - thick, 0, edge + thick, H],
                    fill=col(film.look, "accent") + (255,))
    else:
        d.rectangle([0, edge - thick, W, edge + thick],
                    fill=col(film.look, "accent") + (255,))
    img.alpha_composite(lay)


def _ov_counter(film, img, shot, ov, view, t_local):
    W, H = film.W, film.H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    a0 = float(ov.get("from", 0) or 0)
    a1 = float(ov.get("to", 0) or 0)
    span = max(1e-6, shot.dur - float(ov.get("hold", 0.35) or 0.0))
    u = SH.ease(ov.get("ease", "out"), min(1.0, t_local / span))
    v = a0 + (a1 - a0) * u
    dp = int(ov.get("decimals", 0 if abs(a1 - a0) >= 8 else 1))
    text = f"{v:,.{dp}f}"
    if ov.get("unit"):
        text += str(ov["unit"])
    label = str(ov.get("label", "") or "")
    fs = int(H * 0.105)
    f = font(fs)
    fl = font(int(fs * 0.28))
    tw, th = text_size(d, text, f)
    lw, lh = text_size(d, label, fl) if label else (0, 0)
    pad = int(H * 0.022)
    bw = max(tw, lw) + pad * 2
    bh = th + (lh + pad * 0.5 if label else 0) + pad * 1.8
    x1 = int(W * (1 - SAFE))
    y0 = int(H * SAFE * 1.4)
    plate = _plate(film.look)
    _panel(d, [x1 - bw, y0, x1, y0 + bh], plate + (228,),
           radius=int(H * 0.012), width=1,
           outline=outline_for(film.look, plate) + (200,))
    d.rectangle([x1 - bw, y0, x1 - bw + max(3, int(H * 0.005)), y0 + bh],
                fill=col(film.look, "accent") + (255,))
    if label:
        d.text((x1 - bw + pad, y0 + pad * 0.6), label, font=fl,
               fill=col(film.look, "accent2") + (255,))
    d.text((x1 - bw + pad, y0 + pad * 0.6 + (lh + pad * 0.4 if label else 0)),
           text, font=f, fill=(248, 248, 252, 255))
    img.alpha_composite(lay)


OVERLAYS = {
    "chyron": _ov_chyron,
    "title": _ov_title,
    "map": _ov_map,
    "circle": _ov_circle,
    "split": _ov_split,
    "counter": _ov_counter,
}


# ---------------------------------------------------------------- workers ----

#: `fork` is required — `compose` is a bound method of a `Film` holding PIL
#: images and will not pickle — and it is also what makes this cheap: the film
#: is shared copy-on-write rather than rebuilt in every worker.
_COMPOSE = None
_SEGMENT = None


def _segment_bounds(n_frames, fps, seg_seconds=None):
    """Cut `n_frames` into contiguous `[start, stop)` spans.

    A pure function of the frame count and the rate. Segment boundaries must
    never depend on how many workers happen to be available, or `-j 1` and
    `-j 4` would hand ffmpeg different spans and the two files would differ
    even though every frame in them was identical.
    """
    fps = max(float(fps), 1e-6)
    if seg_seconds:
        seconds = float(seg_seconds)
    else:
        seconds = max(SEG_MIN_SECONDS, (n_frames / fps) / SEG_TARGET)
    step = max(1, int(round(seconds * fps)))
    return [(k, i, min(i + step, n_frames))
            for k, i in enumerate(range(0, n_frames, step))]


def _render_segment(task):
    """Compose and encode one span of frames, in a worker, to its own file."""
    idx, i0, i1 = task
    W, H, fps, venc, workdir = _SEGMENT
    path = os.path.join(workdir, "seg%05d.mp4" % idx)
    ff = shutil.which("ffmpeg") or "ffmpeg"
    proc = subprocess.Popen(
        [ff, "-y", "-loglevel", "error", "-nostdin",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-"]
        + list(venc) + [path], stdin=subprocess.PIPE)
    try:
        for i in range(i0, i1):
            proc.stdin.write(_COMPOSE(i / float(fps)).tobytes())
    except BaseException:
        proc.kill()
        proc.wait()
        try:
            proc.stdin.close()
        except OSError:
            pass
        raise
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed encoding frames %d-%d" % (i0, i1))
    return idx, i1 - i0, path


# ------------------------------------------------------------------ probes ----


def unique_path(path, force=False):
    """A video path guaranteed not to exist yet.

    A render costs minutes and is not reproducible once a storyboard moves on,
    so finished videos are never overwritten. If `path` is taken the next free
    `name-002.mp4` is used instead. `--force` opts out.
    """
    if force or not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    root = re.sub(r"-\d{3}$", "", root)
    n = 2
    while os.path.exists(f"{root}-{n:03d}{ext}"):
        n += 1
    return f"{root}-{n:03d}{ext}"


def timeline_path(out_path):
    return os.path.splitext(out_path)[0] + ".timeline.json"


def write_timeline(out_path, film, fps, W, H):
    """Publish `<stem>.timeline.json`.

    `motionprofile.py` needs it: the animation director's plan is timed
    against raw narration clips that still carry the recorder's silence, and
    this renderer trims that silence, so the two clocks differ — by a quarter
    of the running time on the validation story. Comparing a plan to a film
    without this file compares the right shots at the wrong moments.
    """
    doc = SH.timeline_document(film.board, film.shots, fps=fps, width=W,
                               height=H, output=os.path.basename(out_path))
    path = timeline_path(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
    return path


def _probe_seconds(path):
    try:
        r = subprocess.run(
            [shutil.which("ffprobe") or "ffprobe", "-v", "error",
             "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
             path], capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return None


def _probe_frames(path):
    ff = shutil.which("ffprobe") or "ffprobe"
    base = [ff, "-v", "error", "-select_streams", "v:0", "-show_entries"]
    tail = ["-of", "default=nw=1:nk=1", path]
    for args in (["stream=nb_frames"], ["-count_frames", "stream=nb_read_frames"]):
        try:
            if args[0] == "-count_frames":
                cmd = base[:-1] + ["-count_frames", "-show_entries"] + args[1:] + tail
            else:
                cmd = base + args + tail
            r = subprocess.run(cmd, capture_output=True, text=True, check=True)
            n = int(r.stdout.strip())
            if n > 0:
                return n
        except Exception:
            continue
    return None


def _check_remux_target(out_path, duration):
    """Refuse to swap audio into a film that is not this storyboard's."""
    if not os.path.exists(out_path):
        raise SystemExit(f"--audio-only needs an existing {out_path} to remux")
    have = _probe_seconds(out_path)
    if have is None or abs(have - duration) <= 1.0:
        return
    stem, ext = os.path.splitext(out_path)
    sibs = []
    for g in sorted(glob.glob(stem + "-*" + ext)):
        got = _probe_seconds(g)
        if got is not None and abs(got - duration) <= 1.0:
            sibs.append(os.path.basename(g))
    raise SystemExit(
        "--audio-only will not remux %s: it runs %.1fs but this storyboard is "
        "%.1fs, so it is a different cut.%s"
        % (out_path, have, duration,
           ("\n  this storyboard's film looks like: %s\n  pass it with -o."
            % ", ".join(sibs)) if sibs else
           "\n  pass the film this storyboard rendered with -o."))


def _style_verify():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            os.pardir, "style.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("verify") or {}
    except Exception:
        return {}


def _parse_cpu_list(s):
    n = 0
    for part in s.strip().split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")[:2]
            n += int(b) - int(a) + 1
        else:
            n += 1
    return n


def _perf_cores():
    try:
        r = subprocess.run(["sysctl", "-n", "hw.perflevel0.logicalcpu"],
                           capture_output=True, text=True, check=True)
        n = int(r.stdout.strip())
        if n > 0:
            return n
    except Exception:
        pass
    try:
        n = _parse_cpu_list(open("/sys/devices/cpu_core/cpus").read())
        if n > 0:
            return n
    except Exception:
        pass
    return None


def _cgroup_bytes():
    for p in ("/sys/fs/cgroup/memory.max",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(p).read().strip()
            if v == "max":
                continue
            n = int(v)
            if 0 < n < (1 << 62):
                return n
        except Exception:
            continue
    return None


def _cgroup_cpus():
    try:
        q, p = open("/sys/fs/cgroup/cpu.max").read().split()[:2]
        if q != "max":
            return max(1, int(float(q) / float(p)))
    except Exception:
        pass
    try:
        q = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
        p = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        if q > 0 and p > 0:
            return max(1, int(q / p))
    except Exception:
        pass
    return None


def _default_jobs():
    """How many segment workers this machine can actually run at once.

    Bounded by *fast* cores and by memory, whichever runs out first —
    oversubscribing a laptop pages it and ends up slower than a single worker.
    """
    n = os.cpu_count() or 1
    fast = _perf_cores()
    if fast:
        n = min(n, fast)
    quota = _cgroup_cpus()
    if quota:
        n = min(n, quota)
    total = None
    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        pass
    cg = _cgroup_bytes()
    if cg:
        total = min(total, cg) if total else cg
    if total:
        gb = total / 1073741824.0
        n = min(n, int(max(1.0, (gb - RESERVE_GB) / WORKER_GB)))
    return max(1, n)


# ------------------------------------------------------------------ audio ----


def _write_wav(path, arr, sr):
    """Write a float mix to a 32-bit PCM wav, with the stdlib only."""
    a = np.asarray(arr, dtype=np.float32)
    if a.ndim == 1:
        a = a[:, None]
    a = np.clip(a, -1.0, 1.0)
    ints = (a * 2147483000.0).astype("<i4")
    with wave.open(path, "wb") as fh:
        fh.setnchannels(a.shape[1])
        fh.setsampwidth(4)
        fh.setframerate(int(sr))
        fh.writeframes(ints.tobytes())
    return path


def build_audio(board, sb_dir, duration, seed, workdir, *, quiet=False):
    """Mix and master the film's soundtrack. Returns a wav path, or None.

    A sibling module that throws in here must not cost the caller an hour of
    frames, so the failure is reported at the top of its voice and the film
    is finished silent. A silent film with a shouted reason is recoverable
    with `--audio-only`; a lost render is not.
    """
    A = MODS.get("audio")
    if A is None:
        need("audio", why="build the soundtrack")
    if not quiet:
        print("· building the mix", flush=True)
    try:
        mix = A.build(board, sb_dir, duration, seed=seed)
    except Exception as exc:
        report("mix", f"audio.build failed ({type(exc).__name__}: {exc}) — "
                      f"THE FILM WILL HAVE NO SOUND. Fix audio.py and rerun "
                      f"with --audio-only; the frames are kept.")
        return None
    sr = int(getattr(A, "SR", 48000))
    raw = os.path.join(workdir, "mix_raw.wav")
    _write_wav(raw, mix, sr)
    mastered = os.path.join(workdir, "mix.wav")
    v = _style_verify()
    kw = {"lufs": float(v.get("loudness_lufs", -14.0)),
          "tp": float(v.get("true_peak_dbfs", -1.0))}
    fn = getattr(A, "master_to", None) or getattr(A, "master", None)
    if fn is None:
        report("master", "audio.py has neither master_to nor master — "
                         "shipping the mix unmastered")
        return raw
    try:
        info = fn(raw, mastered, **kw)
    except TypeError:
        try:
            info = fn(raw, mastered)
        except Exception as exc:
            report("master", f"audio mastering failed ({exc}) — "
                             f"shipping the mix unmastered")
            return raw
    except Exception as exc:
        report("master", f"audio mastering failed ({exc}) — "
                         f"shipping the mix unmastered")
        return raw
    if isinstance(info, dict) and not quiet:
        tp = info.get("true_peak")
        if tp is not None:
            print("· master: %.1f dBTP delivered against %.1f target"
                  % (tp, info.get("target_true_peak", kw["tp"])), flush=True)
    return mastered if os.path.exists(mastered) else raw


def line_times(board, sb_dir):
    """Measured narration times, or `{}` for a wordless film."""
    if not board.get("narration"):
        return {}
    A = MODS.get("audio")
    if A is None:
        need("audio", why="measure the narration this board is cut to")
    lt = A.line_times(board, sb_dir)
    return {k: (float(v[0]), float(v[1])) for k, v in dict(lt).items()}


# ----------------------------------------------------------------- render ----


def render(sb, out_path, *, preview=False, single_frame=None, sheet=False,
           force=False, sb_dir=".", audio_only=False, motion_samples=0,
           clip=None, jobs=0, scale=None, limit=None, seg_seconds=None,
           quiet=False):
    if jobs is not None and int(jobs) <= 0:
        jobs = _default_jobs()
    jobs = max(1, int(jobs or 1))

    style = str(sb.get("style", "") or "")
    if style and style != "2d-animation":
        raise SystemExit(
            f"render: this is the 2d-animation renderer and the board says "
            f"style '{style}'. Render it with that style's own render.py.")

    out = sb.get("output", {}) or {}
    W = int(out.get("width", 1920))
    H = int(out.get("height", 1080))
    fps = int(out.get("fps", 30))
    if preview:
        W, H = W // 2, H // 2
        root, ext = os.path.splitext(out_path)
        out_path = f"{root}_preview{ext}"
    if scale:
        W = max(16, int(W * scale)) // 2 * 2
        H = max(16, int(H * scale)) // 2 * 2
    W, H = W // 2 * 2, H // 2 * 2          # yuv420p needs even dimensions

    film_mode = (single_frame is None and not sheet and not audio_only
                 and not clip and not motion_samples)
    if film_mode:
        fresh = unique_path(out_path, force)
        if fresh != out_path and not quiet:
            print(f"note: {os.path.basename(out_path)} exists -> writing "
                  f"{os.path.basename(fresh)}")
        out_path = fresh

    workdir = tempfile.mkdtemp(prefix="anim2d_")
    try:
        lt = line_times(sb, sb_dir)
        film = Film(sb, sb_dir, W, H, fps, line_times=lt, quiet=quiet)
        duration = film.duration
        if limit:
            duration = min(duration, float(limit))
        if not quiet:
            print(f"· {len(film.shots)} shots, {film.duration:.2f}s, "
                  f"{W}x{H} @ {fps}fps", flush=True)
            for s in film.shots:
                cam = film.cameras[s.index]
                bits = f"{cam.move} {cam.ease}" if cam.move != "none" else "—"
                if cam.still:
                    bits = "locked"
                if s.impacts:
                    bits += "  hit@" + ",".join(f"{t:.2f}" for t in s.impacts)
                print(f"    {s.id:>6}  {s.start:6.2f} → {s.end:6.2f}  "
                      f"{s.set:<12} on {s.on}  {bits}", flush=True)
            film.pacing(verbose=True)
            if SH.EASE_SOURCE != "anim":
                print("! anim.py could not be imported — shots.py is easing "
                      "with its fallback curves", file=sys.stderr, flush=True)
        film.preflight()

        compose = film.compose

        # ---- stills ------------------------------------------------------
        if single_frame is not None:
            t = min(max(0.0, float(single_frame)), max(0.0, duration - 1e-3))
            img = Image.fromarray(compose(t))
            p = os.path.splitext(out_path)[0] + f"_t{float(single_frame):g}.png"
            img.save(p)
            print("wrote", p)
            return p

        if sheet:
            # A 4x5 sheet, laid out the long way round for the aspect so it
            # stays roughly square either way. Even sampling, not one frame
            # per shot: the failures this catches — a character drifting out
            # of frame, two actors in the same place — need more than one
            # frame of a shot to be visible.
            cols, rows = (5, 4) if W >= H else (4, 5)
            n = cols * rows
            tw, th = W // 4, H // 4
            # Sheet chrome is mixed from the board's own ink, never from
            # black: these palettes are hued, and a neutral grid beside them
            # makes every frame look colour-cast when it is not.
            chrome = _plate(film.look, 0.55)
            s_img = Image.new("RGB", (tw * cols, th * rows), chrome)
            d = ImageDraw.Draw(s_img)
            f = font(max(11, th // 18), bold=True)
            for i in range(n):
                t = duration * (i / (n - 1)) * 0.995 if n > 1 else 0.0
                shot = film.state(t)[0]
                im = Image.fromarray(compose(t)).resize((tw, th), Image.LANCZOS)
                x, y = (i % cols) * tw, (i // cols) * th
                s_img.paste(im, (x, y))
                tag = f"{t:6.2f}s  {shot.id}  on{shot.on}"
                d.rectangle([x, y + th - f.size - 8, x + tw, y + th],
                            fill=_plate(film.look, 0.72))
                d.text((x + 6, y + th - f.size - 5), tag, font=f,
                       fill=(235, 235, 240))
                d.rectangle([x, y, x + tw - 1, y + th - 1],
                            outline=_plate(film.look, 0.35))
            p = os.path.splitext(out_path)[0] + "_sheet.jpg"
            s_img.save(p, quality=88)
            print("wrote", p)
            return p

        if motion_samples:
            # The verification target's mean frame-to-frame difference at
            # 320x180, without encoding the film — pacing becomes something
            # you can iterate on rather than guess at.
            rng = np.random.default_rng(7)
            n_frames = max(2, int(round(duration * fps)))
            k = min(int(motion_samples), n_frames - 1)
            idx = rng.choice(n_frames - 1, size=k, replace=False)
            small = (320, 180) if W >= H else (180, 320)
            diffs = []
            for j, i in enumerate(sorted(idx.tolist())):
                a0 = Image.fromarray(compose(i / fps)).convert("L").resize(
                    small, Image.BILINEAR)
                a1 = Image.fromarray(compose((i + 1) / fps)).convert("L").resize(
                    small, Image.BILINEAR)
                diffs.append(float(np.abs(np.asarray(a0, dtype=np.float32)
                                          - np.asarray(a1, dtype=np.float32)).mean()))
                if (j + 1) % 25 == 0:
                    print(f"  {j + 1}/{k} mean so far {np.mean(diffs):.3f}",
                          flush=True)
            m = float(np.mean(diffs))
            se = float(np.std(diffs) / math.sqrt(len(diffs)))
            want = _style_verify()
            print(f"motion estimate {m:.3f} +/- {1.96 * se:.3f} "
                  f"(95% CI, {len(diffs)} sampled frame pairs)")
            if want.get("motion_mean_min") is not None:
                print(f"  target >= {want['motion_mean_min']} "
                      f"(aiming for {want.get('motion_mean_target')})  "
                      f"{'ok' if m >= want['motion_mean_min'] else 'UNDER'}")
            return m

        if clip:
            a = max(0.0, float(clip[0]))
            b = min(duration, float(clip[1]))
            if b <= a:
                raise SystemExit(f"--clip needs END > START (got {clip[0]} "
                                 f"{clip[1]}), and the film is "
                                 f"{duration:.2f}s long")
            i0, i1 = int(round(a * fps)), int(round(b * fps))
            p = os.path.splitext(out_path)[0] + f"_clip{a:g}-{b:g}.mp4"
            ff = shutil.which("ffmpeg") or "ffmpeg"
            proc = subprocess.Popen(
                [ff, "-y", "-loglevel", "error", "-nostdin", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                 "-i", "-"] + _venc(out) + [p], stdin=subprocess.PIPE)
            prev, worst = None, (0.0, 0.0)
            for i in range(i0, i1):
                fr = compose(i / fps)
                proc.stdin.write(fr.tobytes())
                sm = np.asarray(Image.fromarray(fr).convert("L").resize(
                    (320, 180), Image.BILINEAR), dtype=np.float32)
                if prev is not None:
                    dd = float(np.abs(sm - prev).mean())
                    if dd > worst[0]:
                        worst = (dd, i / fps)
                prev = sm
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError("ffmpeg failed writing the clip")
            print(f"wrote {p}  ({i1 - i0} frames, silent)")
            print(f"largest single-frame change {worst[0]:.2f} at "
                  f"t={worst[1]:.2f}s")
            return p

        # ---- audio -------------------------------------------------------
        if audio_only:
            _check_remux_target(out_path, duration)
        mastered = build_audio(sb, sb_dir, duration, film.seed, workdir,
                               quiet=quiet)

        ff = shutil.which("ffmpeg") or "ffmpeg"
        if audio_only:
            if not mastered:
                raise RuntimeError(
                    "there is no mix to remux — audio.build failed, and this "
                    "mode exists only to put sound into %s" % out_path)
            tmp_out = out_path + ".remux.mp4"
            before = _probe_frames(out_path)
            subprocess.run([ff, "-y", "-loglevel", "error", "-nostdin",
                            "-i", out_path, "-i", mastered,
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                            "-ar", "48000", "-movflags", "+faststart",
                            # `apad` then `-shortest`: on its own `-shortest`
                            # cuts every stream at the shortest one, and a
                            # mastered track a rounding error short would trim
                            # the last frames off a film this mode promised
                            # not to touch.
                            "-af", "apad", "-shortest", tmp_out], check=True)
            after = _probe_frames(tmp_out)
            if before is not None and after is not None and after != before:
                os.remove(tmp_out)
                raise RuntimeError(
                    "remuxing the audio would have taken the film from %d "
                    "frames to %d, and this mode promises to leave the frames "
                    "alone — refusing to overwrite %s"
                    % (before, after, out_path))
            os.replace(tmp_out, out_path)
            write_timeline(out_path, film, fps, W, H)
            print(f"remuxed audio into {out_path} (frames untouched)")
            return out_path

        # ---- video -------------------------------------------------------
        n_frames = int(round(duration * fps))
        venc = _venc(out)
        segs = _segment_bounds(n_frames, fps, seg_seconds)
        if not quiet:
            print("· rendering %d frames at %dx%d in %d segments%s"
                  % (n_frames, W, H, len(segs),
                     (" on %d workers" % jobs) if jobs > 1 else ""), flush=True)

        global _COMPOSE, _SEGMENT
        _COMPOSE = compose
        _SEGMENT = (W, H, fps, venc, workdir)
        done = [0]
        parts = {}

        def landed(res):
            idx, count, path = res
            parts[idx] = path
            done[0] += count
            if not quiet:
                print("\r  %5.1f%%  %d/%d frames, %d/%d segments"
                      % (100.0 * done[0] / max(1, n_frames), done[0], n_frames,
                         len(parts), len(segs)), end="", flush=True)

        try:
            if jobs > 1 and len(segs) > 1:
                ctx = multiprocessing.get_context("fork")
                pool = ctx.Pool(min(jobs, len(segs)))
                try:
                    it = pool.imap_unordered(_render_segment, segs)
                    alive = {w.pid for w in pool._pool}
                    left = len(segs)
                    while left:
                        try:
                            landed(it.next(timeout=SEG_POLL_SECONDS))
                            left -= 1
                        except multiprocessing.TimeoutError:
                            # A worker killed outright sends no result back and
                            # Pool starts a replacement without re-queueing its
                            # segment, so waiting on the queue waits for ever.
                            # Watch the pids instead.
                            now = {w.pid for w in pool._pool}
                            if now != alive:
                                raise RuntimeError(
                                    "a render worker died with %d of %d "
                                    "segments still out — almost always "
                                    "memory. Retry with fewer workers, e.g. "
                                    "-j 2." % (left, len(segs)))
                            continue
                    pool.close()
                    pool.join()
                except BaseException:
                    pool.terminate()
                    pool.join()
                    raise
            else:
                # The same segments, one after another. Running the serial case
                # through this path too is the only way `-j 1` and `-j 8` can
                # be guaranteed to produce the same bytes.
                for task in segs:
                    landed(_render_segment(task))
        finally:
            _COMPOSE = None
            _SEGMENT = None

        missing = [k for k, _, _ in segs if k not in parts]
        if missing:
            raise RuntimeError("segments %s never came back" % missing)

        listing = os.path.join(workdir, "segments.txt")
        with open(listing, "w") as fh:
            for k, _, _ in segs:
                fh.write("file '%s'\n" % parts[k].replace("'", "'\\''"))
        join = [ff, "-y", "-loglevel", "error", "-nostdin",
                "-f", "concat", "-safe", "0", "-i", listing]
        if mastered:
            join += ["-i", mastered, "-map", "0:v:0", "-map", "1:a:0",
                     "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                     "-af", "apad", "-shortest"]
        else:
            join += ["-map", "0:v:0", "-an"]
        rc = subprocess.run(
            join + ["-c:v", "copy",
                    "-fflags", "+bitexact", "-flags:v", "+bitexact",
                    "-flags:a", "+bitexact", "-map_metadata", "-1",
                    "-movflags", "+faststart", out_path]).returncode
        if not quiet:
            print("\r  100.0%            ")
        if rc != 0:
            raise RuntimeError("ffmpeg failed joining %d segments" % len(segs))

        got = _probe_frames(out_path)
        if got is not None and got != n_frames:
            raise RuntimeError(
                "joined film has %d frames, expected %d — the segment "
                "boundaries did not line up" % (got, n_frames))
        write_timeline(out_path, film, fps, W, H)
        if not quiet:
            print("wrote", out_path)
        if mastered is None:
            print("! %s HAS NO SOUND — see the audio.build error above; "
                  "rerun with --audio-only once audio.py is fixed"
                  % os.path.basename(out_path), file=sys.stderr, flush=True)
        return out_path
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _venc(out):
    """The video encoder settings, chosen for reproducibility.

    `-threads 1` because x264 slices the picture between threads and the
    bitstream it emits therefore depends on how many it was given; the
    parallelism here comes from running many segments at once instead.
    `+bitexact` keeps the encoder's version string and the muxer's wall-clock
    timestamps out of the file, which is what lets two renders of the same
    board be compared with a hash at all.
    """
    return ["-c:v", "libx264", "-preset", str(out.get("preset", "medium")),
            "-crf", str(out.get("crf", 19)),
            "-pix_fmt", "yuv420p",
            "-maxrate", str(out.get("maxrate", "16M")),
            "-bufsize", str(out.get("bufsize", "32M")),
            "-threads", "1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709"]


# -------------------------------------------------------------- self-test ----


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gait_test(sb, sb_dir, quiet=False):
    """Prove the gait composes with the staging instead of being erased by it.

    Two properties, both of which a single line in `_pose_at` used to destroy
    by assigning the staged position over the pose's own `at`:

    **The pelvis bobs.** A cycle raises the pelvis twice per stride, over each
    planted leg in turn. Pinning `at` to the staged point flattens that to a
    dead-level glide, which is the difference between a walk and a chess piece
    being slid across a board.

    **A planted foot stays planted.** The gait plants its feet against its own
    stride rate, so the cycle has to be driven at the rate the board's travel
    implies — not at whatever `rate` says — or the foot slides by the
    difference. Measured at the **ankle**, which is the joint the IK plants;
    `foot` is the toe tip and legitimately rotates through stance.

    Boards deliberately mismatched from `rate x stride_units x dur` are the
    interesting case, and are what this checks.
    """
    rig_m, poses_m = MODS.get("rig"), MODS.get("poses")
    if rig_m is None or poses_m is None:
        print("gait-test: skipped — rig/poses not importable")
        return True

    fps = int((sb.get("output") or {}).get("fps", 30) or 30)
    height = float(getattr(poses_m, "H_DEF", 18.0))
    pelvis = 44.0 - float(getattr(rig_m, "PELVIS_TO_SOLE", 0.416)) * height
    stride = float(getattr(poses_m, "stride_units", lambda *_: 0.0)(
        "walk", height))
    ok = True

    def say(name, good, detail):
        nonlocal ok
        ok = ok and good
        if not quiet:
            print(f"  [{'PASS' if good else 'FAIL'}] {name}: {detail}")

    def walk(dur, to=None, facing=1):
        a = {"id": "w", "cast": "_gait", "action": "walk", "facing": facing,
             "at": [50.0, pelvis], "rate": 1.0, "phase": 0.0, "ease": "linear"}
        if to is not None:
            a["to"] = [50.0 + to, pelvis]
        b = {"style": "2d-animation", "seed": 0,
             "output": {"width": 640, "height": 360, "fps": fps},
             "timing": {"lead_in": 0.0, "tail": 0.0},
             "shots": [{"id": "g", "at": 0.0, "dur": dur, "tier": "full",
                        "on": 1, "set": (sb.get("shots") or [{}])[0].get("set"),
                        "actors": [a]}]}
        film = Film(b, sb_dir, 640, 360, fps, line_times={}, quiet=True)
        rows = []
        for i in range(int(round(dur * fps))):
            pose = film._pose_at(film.shots[0], a, i / fps)
            j = rig_m.solve(pose)
            rows.append((pose["at"], j["ankle.l"], j["ankle.r"]))
        return rows

    ys = [r[0][1] for r in walk(1.0)]
    p2p = max(ys) - min(ys)
    mid = sum(ys) / len(ys)
    cross = sum(1 for a, b in zip(ys, ys[1:]) if (a - mid) * (b - mid) < 0)
    say("the pelvis bobs", p2p > 1e-3 and cross == 4,
        f"{p2p:.4f} u peak-to-peak ({p2p / height:.4f} H), {cross} "
        f"mean-crossings per stride — twice per stride, over each planted leg")

    worst = 0.0
    for mult in (1.0, 0.55, 1.9, 0.37, -1.3):
        rows = walk(4.0, to=stride * 4.0 * mult,
                    facing=-1 if mult < 0 else 1)
        floor = max(max(r[1][1], r[2][1]) for r in rows)
        drift = [abs(b[i][0] - a[i][0]) for a, b in zip(rows, rows[1:])
                 for i in (1, 2)
                 if a[i][1] > floor - 0.06 and b[i][1] > floor - 0.06] or [0.0]
        worst = max(worst, sum(drift) / len(drift))
    say("a planted foot stays planted", worst < 1.0,
        f"{worst * 1000:.4f} milli-units/frame of ankle drift, worst of five "
        f"boards whose `to` is 0.37x to 1.9x of rate x stride x dur")

    print("gait-test: %s" % ("the gait composes with the staging" if ok
                             else "COMPOSITION IS BROKEN"))
    return ok


def self_test(sb, sb_dir, seconds=3.0, scale=0.25, jobs=(1, 4)):
    """Prove `-j 1` and `-j 4` produce the same bytes, with SHA-256.

    Determinism is a documented property of this renderer, and a documented
    property that is not measured is a wish. A short window at quarter size
    exercises the whole path — compose, segment, encode, concat, mux — in a
    few seconds, and the segment length is shortened so that even that window
    is cut into several pieces and the parallel path is genuinely used.
    """
    tmp = tempfile.mkdtemp(prefix="anim2d_selftest_")
    try:
        hashes = []
        for j in jobs:
            p = os.path.join(tmp, f"j{j}.mp4")
            render(sb, p, sb_dir=sb_dir, jobs=j, scale=scale, limit=seconds,
                   seg_seconds=0.4, force=True, quiet=True)
            hashes.append((j, sha256(p), os.path.getsize(p)))
        for j, h, n in hashes:
            print(f"  -j {j}: sha256 {h}  ({n} bytes)")
        ok = len({h for _, h, _ in hashes}) == 1
        print("self-test: %s" % ("IDENTICAL — deterministic" if ok
                                 else "MISMATCH — the render is NOT deterministic"))
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- main ----


def main():
    ap = argparse.ArgumentParser(
        description="Render a 2D character-animation storyboard.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out")
    ap.add_argument("--preview", action="store_true",
                    help="render at half resolution, alongside as *_preview.mp4")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="write a single PNG at time T and exit")
    ap.add_argument("--sheet", action="store_true",
                    help="write a 4x5 contact sheet JPG and exit — do this first")
    ap.add_argument("--clip", type=float, nargs=2, metavar=("START", "END"),
                    help="render only START..END seconds, silent, at full res")
    ap.add_argument("--audio-only", action="store_true", dest="audio_only",
                    help="rebuild the mix and remux it into the existing video, "
                         "copying the frames (seconds, not minutes)")
    ap.add_argument("--motion", type=int, default=0, metavar="N",
                    help="estimate the mean frame difference from N sampled "
                         "frame pairs and exit")
    ap.add_argument("--jobs", "-j", type=int, default=0,
                    help="render on N processes (0 = pick for this machine). "
                         "Segment boundaries come from the running time, not "
                         "from N, so every value of N produces the same file")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing video (default: write a new one)")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="check the gait composes with the staging, then "
                         "render a short window at -j 1 and -j 4 and compare "
                         "SHA-256, proving the render is deterministic")
    ap.add_argument("--self-test-seconds", type=float, default=3.0,
                    dest="self_test_seconds", metavar="S")
    a = ap.parse_args()

    try:
        with open(a.storyboard) as f:
            sb = json.load(f)
    except FileNotFoundError:
        sys.exit(f"render: no storyboard at {a.storyboard!r} — run compile.py "
                 "first")
    except json.JSONDecodeError as e:
        sys.exit("render: %s is not valid JSON (line %d, column %d: %s)"
                 % (a.storyboard, e.lineno, e.colno, e.msg))
    except OSError as e:
        sys.exit("render: cannot read %s: %s" % (a.storyboard, e.strerror or e))
    if not isinstance(sb, dict):
        sys.exit("render: %s should hold a storyboard object, found %s"
                 % (a.storyboard, type(sb).__name__))

    base = os.path.dirname(os.path.abspath(a.storyboard))
    out_path = a.out or os.path.join(
        base, (sb.get("output", {}) or {}).get("path")
        or ((sb.get("title") or "out").lower().replace(" ", "-") + ".mp4"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    if a.self_test:
        ok = gait_test(sb, base)
        ok = self_test(sb, base, seconds=a.self_test_seconds) and ok
        sys.exit(0 if ok else 1)

    try:
        render(sb, out_path, preview=a.preview, single_frame=a.frame,
               sheet=a.sheet, force=a.force, sb_dir=base,
               audio_only=a.audio_only, motion_samples=a.motion, clip=a.clip,
               jobs=a.jobs)
    except (SH.ShotError, SH.TimeError) as e:
        sys.exit(f"render: {e}")


if __name__ == "__main__":
    main()
