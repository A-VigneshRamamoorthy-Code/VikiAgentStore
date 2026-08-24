"""sets.py — sets, props and parallax for the flat-vector 2D style.

The picture department. `look.py` decides what colour the world is; this
module decides what shape it is.

House rules, inherited from the style contract and not negotiable here:

* **Flat colour only.** Every shape is one solid fill. Shading is another
  flat shape, never a gradient, never a texture, never grain. There are
  exactly two exceptions and both are named here. The sky may carry one
  2-stop linear ramp — `_Pen.vgrad`, fed by `look.sky_gradient`, and called
  from nowhere but a layer named ``sky``. The `peak` set paints its rock
  instead of filling it, because a flat cone reads as a road sign at any
  colour; see the banner above `_set_peak` for why that one is allowed and
  what keeps it deterministic.
* **The line is not one black line.** Outlines come from
  `look.outline_for` — the shape's own hue, a touch more saturated and a
  lot darker — so a red car has a dark red edge. `look["ink"]` is kept for
  silhouettes and for facial features, and is never pure black.
* **Weight falls off with distance.** `STROKE_PX` sets the line weight per
  depth band (1.5px far to 3.8px foreground, at `REF_UNIT`); every layer
  pen carries its band's multiplier, so a far building draws a lighter line
  than a foreground railing without any set code asking for it.
* **Everything on the ground has a contact shadow.** `contact_shadow` is
  public so `rig.py` can put the same ellipse under a character that this
  module puts under a car. Without it, everything reads as a sticker.
* **Depth is overlap, scale and desaturation.** Distant layers are washed
  toward the sky by `look.depth_tint`; nothing is blurred and nothing is
  drawn in perspective.
* **Nothing is invented silently.** Ask for a set or a prop this module does
  not have and you get a loud labelled placeholder with the name you asked
  for written on it — never a lookalike. The names land in `MISSING` so a
  caller can find out without reading the pixels.
* **Deterministic.** Same arguments, same pixels. Every random-looking
  decision comes out of the explicit `seed` through a positional hash, so a
  building at world-x 340 looks the same whatever the camera is doing.

Coordinate system (frozen, see reference/rig.md)
------------------------------------------------
A 16:9 shot is composed in a ``100 x 56.25`` unit box, 9:16 in
``56.25 x 100``. ``x`` runs right, ``y`` runs **down**. Ground level in a
street shot is ``y = 44``; a default adult is ``18`` units tall.
``unit`` is pixels per scene unit and ``origin`` is the scene coordinate
sitting at the image's top-left pixel.

Public contract
---------------
::

    SETS: dict[str, callable]
    PROPS: dict[str, callable]

    draw_set(img, name, look, *, unit, origin, t, camera, seed)
    draw_prop(img, kind, look, *, at, unit, origin, scale=1.0, phase=0.0, seed=0)
    prop_bbox(kind, scale=1.0) -> (x0, y0, x1, y1)

Additive, keyword-only, and safe to ignore::

    PARALLAX      the four canonical scroll rates
    SET_LAYERS    per-set layer names and their scroll rate `k`
    STROKE_PX     line weight per depth band, in reference pixels
    stroke_w(depth, *, unit=None)
    contact_shadow(img, look, *, at, unit, origin, foot_span, height,
                   opacity=SHADOW_OPACITY)
    layer_origins(name, *, origin, camera, t)
    draw_set(..., layers=[...])            draw a subset of the stack
    draw_prop(..., t=, anim=, shadow=)

Both draw functions return ``None`` when they drew the thing asked for and a
truthy ``{"missing": True, ...}`` dict when they drew a placeholder instead.
"""

from __future__ import annotations

import colorsys
import math
import sys

from PIL import Image, ImageDraw, ImageFont

try:                                    # normal import, running as a module
    from . import look as _look         # type: ignore
except ImportError:                     # running as a script from scripts/
    import look as _look

mix = _look.mix
shade = _look.shade
tint = _look.tint
desaturate = _look.desaturate
rotate_hue = _look.rotate_hue
lightness = _look.lightness
alpha = _look.alpha
depth_tint = _look.depth_tint
outline_for = _look.outline_for
sky_gradient = _look.sky_gradient

#: Contact-shadow geometry and opacity, straight from `look`.
SHADOW_A = _look.SHADOW_A
SHADOW_B = _look.SHADOW_B
SHADOW_OPACITY = _look.SHADOW_OPACITY

RGB = tuple[int, int, int]
Pt = tuple[float, float]

# ------------------------------------------------------------------ scene ----

SCENE_W = 100.0
SCENE_H = 56.25
#: Ground line for a street-level shot. Feet, tyres and prop bases sit here.
GROUND_Y = 44.0

#: Apex of the `peak` set's mountain, in scene units: a shade right of centre
#: and a shade above the middle of a 16:9 frame. It lives up here with the
#: other scene constants because it is two things at once — the point the
#: summit is drawn to and the mark the cast stands on — and those must not be
#: allowed to become two numbers. See the `set: peak` section.
PEAK_APEX: Pt = (50.5, 25.4)

#: Where the ground is in each set, or ``None`` for the sets that have no
#: ground plane (looking down at a city, or up at open sky).
SET_GROUND: dict[str, float | None] = {
    "street": GROUND_Y,
    "suburb": GROUND_Y,
    "highway": GROUND_Y,
    "office": GROUND_Y,
    "aerial": None,
    # The summit has a ground line, but it is not the street's: the cast
    # stand on the apex, less than half way down the frame.
    "peak": PEAK_APEX[1],
    "sky": None,
}

#: Supersample factors. Sets cover the whole frame so they get the cheaper
#: one; props are small, full of curves and get the expensive one.
#: The plugin renders at 30 fps. Anything on its own clock — rotor, light
#: bar, wheel spin — is checked against this so it cannot land on a rate that
#: strobes or aliases.
FPS = 30

SS_SET = 2
SS_PROP = 3

_MAX_TILE_PX = 18_000_000      # refuse to allocate a supersampled tile bigger

# ---------------------------------------------------------------- missing ----

#: Every ``("set", name)`` / ``("prop", name)`` this module was asked for and
#: did not have. Populated as a side effect of drawing a placeholder so a
#: caller can report it without parsing pixels. Call `clear_missing()` between
#: runs.
MISSING: set[tuple[str, str]] = set()


def clear_missing() -> None:
    """Forget everything in `MISSING`."""
    MISSING.clear()


# ------------------------------------------------------ deterministic noise --

_M64 = (1 << 64) - 1


def _hash(*vals: float) -> int:
    """A stable 64-bit mix of integers. Not `hash()`, which is salted."""
    h = 0xCBF29CE484222325
    for v in vals:
        i = int(v) & _M64
        for _ in range(4):
            h = (h ^ (i & 0xFFFF)) & _M64
            h = (h * 0x100000001B3) & _M64
            i >>= 16
        h ^= (h >> 29)
    h = (h * 0xFF51AFD7ED558CCD) & _M64
    h ^= (h >> 32)
    return h


def _r01(*vals: float) -> float:
    """Uniform 0..1 from a position, not from a sequence of draws."""
    return (_hash(*vals) >> 11) / float(1 << 53)


def _rr(lo: float, hi: float, *vals: float) -> float:
    return lo + (hi - lo) * _r01(*vals)


def _ri(lo: int, hi: int, *vals: float) -> int:
    """Inclusive integer in ``[lo, hi]``."""
    return lo + int(_r01(*vals) * (hi - lo + 1)) if hi > lo else lo


def _pick(seq, *vals):
    return seq[int(_r01(*vals) * len(seq)) % len(seq)]


def _chance(p: float, *vals: float) -> bool:
    return _r01(*vals) < p


# ----------------------------------------------------------------- colour ----

_FALLBACK: dict[str, RGB] = dict(_look.PALETTES[_look.DEFAULT_PALETTE])


def _norm(look: dict | None) -> dict[str, RGB]:
    """Accept any dict that quacks like a palette; never raise on a bad one.

    A set is not the right place to discover that a palette is short of a key,
    so anything missing is filled from the house default. Sets only ever read
    the fourteen contract keys, which means they work with a `look.derive()`d
    palette exactly as well as with a named one.
    """
    out = dict(_FALLBACK)
    if isinstance(look, dict):
        for k in _look.PALETTE_KEYS:
            v = look.get(k)
            if (isinstance(v, (tuple, list)) and len(v) >= 3
                    and all(isinstance(c, (int, float)) for c in v[:3])):
                out[k] = (int(v[0]), int(v[1]), int(v[2]))
    return out


def _hue(c: RGB) -> float:
    r, g, b = [v / 255.0 for v in c[:3]]
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 1e-9:
        return 0.0
    if mx == r:
        h = 60.0 * (((g - b) / (mx - mn)) % 6.0)
    elif mx == g:
        h = 60.0 * ((b - r) / (mx - mn) + 2.0)
    else:
        h = 60.0 * ((r - g) / (mx - mn) + 4.0)
    return h % 360.0


def _lin1(v: float) -> float:
    v = float(v) / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _chroma_angle(c: RGB) -> float:
    """Where a colour sits on the plane `rotate_hue` actually turns.

    `_hue` is an HSV angle; `look.rotate_hue` rotates in linear light about
    the Rec.709 luminance axis. They are *different* planes, and confusing
    them is how you ask for police blue and get pond green. Anything that
    wants a named hue goes through here.
    """
    r, g, b = _lin1(c[0]), _lin1(c[1]), _lin1(c[2])
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return math.degrees(math.atan2(b - y, r - y))


def _hsv(h: float, s: float, v: float) -> RGB:
    r, g, b = colorsys.hsv_to_rgb((float(h) % 360.0) / 360.0,
                                  max(0.0, min(1.0, s)),
                                  max(0.0, min(1.0, v)))
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


_HUE_REF: dict[int, float] = {}


def _hue_ref(deg: float) -> float:
    """The chroma-plane angle of the pure colour at HSV hue `deg`."""
    k = int(round(deg)) % 360
    a = _HUE_REF.get(k)
    if a is None:
        a = _chroma_angle(_hsv(k, 1.0, 1.0))
        _HUE_REF[k] = a
    return a


def _toward(c: RGB, target_deg: float, amount: float) -> RGB:
    """Rotate a colour part-way toward a target hue, keeping its lightness."""
    d = (_hue_ref(target_deg) - _chroma_angle(c) + 180.0) % 360.0 - 180.0
    return rotate_hue(c, d * max(0.0, min(1.0, amount)))


def _hued(h: float, sat: float, target_l: float) -> RGB:
    """A colour of exactly this hue and saturation, at this L*.

    For the handful of things whose hue is a fact about the world rather
    than a choice about the film — leaves, an emergency light, a lit
    window. Their *value* still comes from the palette, which is why they
    sit down properly in a night set and a noon set alike.
    """
    lo, hi = 0.0, 1.0
    for _ in range(20):
        m = (lo + hi) / 2.0
        if lightness(_hsv(h, sat, m)) < target_l:
            lo = m
        else:
            hi = m
    return _hsv(h, sat, (lo + hi) / 2.0)


def _at_lightness(c: RGB, target: float) -> RGB:
    """The same colour, moved to a given L* by blending to black or white."""
    target = max(0.0, min(100.0, float(target)))
    cur = lightness(c)
    if abs(cur - target) < 0.4:
        return c
    end = (0, 0, 0) if cur > target else (255, 255, 255)
    lo, hi = 0.0, 1.0
    for _ in range(20):
        m = (lo + hi) / 2.0
        if (lightness(mix(c, end, m)) > target) == (cur > target):
            lo = m
        else:
            hi = m
    return mix(c, end, (lo + hi) / 2.0)


def _night(look: dict) -> bool:
    """Whether this palette is lit from the sky or from windows."""
    return lightness(look["sky"]) < 42.0


def _foliage(look: dict, *, dark: bool = False) -> RGB:
    """Green, at the palette's value, tinged by the palette's light."""
    h = 116.0 + 0.22 * ((_hue(look["sky"]) - 116.0 + 180.0) % 360.0 - 180.0)
    base = lightness(mix(look["mid"], look["far"], 0.55))
    tgt = max(9.0, min(72.0, base * (0.54 if dark else 0.76)))
    return _at_lightness(mix(_hued(h, 0.52, tgt), look["far"], 0.16), tgt)


def _glass(look: dict) -> RGB:
    """What a window reflects: mostly sky, a little of the wall it is in."""
    return mix(look["sky"], look["near"], 0.42)


def _lit_window(look: dict) -> RGB:
    """A window that is switched on. By day that reads darker than the
    reflection; at night it is the only thing holding the city up."""
    if _night(look):
        return _hued(43.0, 0.62, min(84.0, lightness(look["sky"]) + 58.0))
    return mix(_glass(look), look["ink"], 0.42)


def _lit_rate(look: dict) -> float:
    return 0.42 if _night(look) else 0.16


def _sun(look: dict) -> tuple[RGB, RGB]:
    """Disc and halo — never the accent. Accents belong to the story."""
    sky = look["sky"]
    if _night(look):
        return (_at_lightness(mix(sky, (238, 243, 255), 0.92), 88.0),
                mix(sky, (216, 228, 255), 0.18))
    return (mix(sky, (255, 247, 216), 0.90), mix(sky, (255, 247, 216), 0.26))


def _cloud_cols(look: dict, z: float) -> tuple[RGB, RGB]:
    """Cloud body and shadowed underside, at the sky's own value."""
    sky = look["sky"]
    ls = lightness(sky)
    if ls >= 46.0:
        body = _at_lightness(desaturate(mix(look["near"], (255, 255, 255),
                                            0.70), 0.55),
                             min(97.0, ls + 24.0))
    else:
        body = _at_lightness(mix(sky, look["far"], 0.55), min(62.0, ls + 19.0))
    # The underside is the same cloud with the sky reflected into it, never a
    # different hue: a green-bellied cloud is the classic flat-vector tell.
    under = _at_lightness(mix(body, sky, 0.46),
                          max(3.0, lightness(body) - 13.0))
    return (depth_tint(body, z * 0.55, sky), depth_tint(under, z * 0.72, sky))


def _asphalt(look: dict) -> RGB:
    """Road, not ground.

    Every palette names the *pavement* in `ground`; tarmac is much darker
    than that in daylight and never quite black at night, or the car has
    nothing to be seen against.
    """
    g = look["ground"]
    lg = lightness(g)
    if lg > 42.0:
        return _at_lightness(desaturate(mix(g, look["ink"], 0.30), 0.55),
                             36.0)
    if lg < 20.0:
        return _at_lightness(desaturate(mix(g, look["far"], 0.35), 0.35),
                             21.0)
    return desaturate(g, 0.40)


# -------------------------------------------------------------------- pen ----

class _Pen:
    """Draws in scene units onto a supersampled surface.

    Every method takes scene coordinates and unit-valued stroke widths; the
    pen owns the only multiplication by `unit` in the module, which is what
    keeps the set code readable and the parallax honest.
    """

    __slots__ = ("d", "u", "ox", "oy", "w", "h", "wk")

    def __init__(self, d: ImageDraw.ImageDraw, unit: float, origin: Pt,
                 size: tuple[int, int], stroke: float = 1.0):
        self.d = d
        self.u = float(unit)
        self.ox = float(origin[0])
        self.oy = float(origin[1])
        self.w, self.h = int(size[0]), int(size[1])
        #: Depth multiplier on every stroke width this pen draws. Set once
        #: per layer so distant scenery carries a lighter line than the
        #: foreground without any set code having to think about it.
        self.wk = float(stroke)

    # -- mapping --
    def X(self, x: float) -> float:
        return (float(x) - self.ox) * self.u

    def Y(self, y: float) -> float:
        return (float(y) - self.oy) * self.u

    def pt(self, p) -> tuple[float, float]:
        return ((float(p[0]) - self.ox) * self.u,
                (float(p[1]) - self.oy) * self.u)

    def pts(self, seq) -> list[tuple[float, float]]:
        return [self.pt(p) for p in seq]

    def px(self, units: float) -> int:
        return max(1, int(round(float(units) * self.u * self.wk)))

    def bounds(self) -> tuple[float, float, float, float]:
        """The scene rectangle this pen can see — the whole point of a pen.

        Set code asks the pen what is on screen and only builds that, which
        is how the worlds scroll for ever without a world model.
        """
        return (self.ox, self.oy,
                self.ox + self.w / self.u, self.oy + self.h / self.u)

    # -- primitives --
    def fill(self, col) -> None:
        self.d.rectangle([-1, -1, self.w + 1, self.h + 1], fill=col)

    def vgrad(self, top: RGB, bottom: RGB, y0=None, y1=None) -> None:
        """The **only** gradient this style permits: a 2-stop linear sky.

        Every other fill in the frame — character, prop, building, cloud — is
        one flat colour. See `look.sky_gradient`.
        """
        py0 = -1 if y0 is None else int(math.floor(self.Y(y0)))
        py1 = self.h + 1 if y1 is None else int(math.ceil(self.Y(y1)))
        py0, py1 = max(-1, py0), min(self.h + 1, py1)
        span = max(1, py1 - py0)
        for row in range(py0, py1):
            u = (row - py0) / span
            self.d.rectangle([-1, row, self.w + 1, row + 1],
                             fill=mix(top, bottom, u))

    def rect(self, x0, y0, x1, y1, col=None, ink=None, w=0.0) -> None:
        a, b = self.pt((x0, y0)), self.pt((x1, y1))
        box = [min(a[0], b[0]), min(a[1], b[1]),
               max(a[0], b[0]), max(a[1], b[1])]
        if box[2] - box[0] < 0.6:
            box[2] = box[0] + 0.6
        if box[3] - box[1] < 0.6:
            box[3] = box[1] + 0.6
        self.d.rectangle(box, fill=col,
                         outline=ink if w > 0 else None,
                         width=self.px(w) if w > 0 else 0)

    def rrect(self, x0, y0, x1, y1, r, col=None, ink=None, w=0.0) -> None:
        a, b = self.pt((x0, y0)), self.pt((x1, y1))
        box = [min(a[0], b[0]), min(a[1], b[1]),
               max(a[0], b[0]), max(a[1], b[1])]
        rad = max(0.0, min(float(r) * self.u,
                           (box[2] - box[0]) / 2.0, (box[3] - box[1]) / 2.0))
        self.d.rounded_rectangle(box, radius=rad, fill=col,
                                 outline=ink if w > 0 else None,
                                 width=self.px(w) if w > 0 else 0)

    def poly(self, points, col=None, ink=None, w=0.0) -> None:
        p = self.pts(points)
        if len(p) < 3:
            return
        if col is not None:
            self.d.polygon(p, fill=col)
        if ink is not None and w > 0:
            self.d.line(p + [p[0]], fill=ink, width=self.px(w), joint="curve")

    def ellipse(self, cx, cy, rx, ry, col=None, ink=None, w=0.0) -> None:
        c = self.pt((cx, cy))
        ex, ey = abs(float(rx)) * self.u, abs(float(ry)) * self.u
        box = [c[0] - ex, c[1] - ey, c[0] + ex, c[1] + ey]
        if box[2] - box[0] < 0.6 or box[3] - box[1] < 0.6:
            box = [box[0], box[1], box[0] + max(0.6, box[2] - box[0]),
                   box[1] + max(0.6, box[3] - box[1])]
        self.d.ellipse(box, fill=col, outline=ink if w > 0 else None,
                       width=self.px(w) if w > 0 else 0)

    def circle(self, cx, cy, r, col=None, ink=None, w=0.0) -> None:
        self.ellipse(cx, cy, r, r, col, ink, w)

    def pie(self, cx, cy, r, a0, a1, col=None) -> None:
        c = self.pt((cx, cy))
        rr = abs(float(r)) * self.u
        self.d.pieslice([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr],
                        a0, a1, fill=col)

    def line(self, points, col, w=0.3, cap=True) -> None:
        p = self.pts(points)
        if len(p) < 2:
            return
        self.d.line(p, fill=col, width=self.px(w),
                    joint="curve" if len(p) > 2 else None)
        if cap and self.px(w) > 2:
            r = self.px(w) / 2.0
            for q in (p[0], p[-1]):
                self.d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r],
                               fill=col)

    def text(self, x, y, s, col, size_units=2.0, anchor="mm") -> None:
        """Only ever used by the placeholder. Artwork carries no text."""
        f = _font(max(7, int(round(size_units * self.u))))
        self.d.text(self.pt((x, y)), s, fill=col, font=f, anchor=anchor)


_FONTS: dict[int, ImageFont.FreeTypeFont] = {}


def _font(px: int):
    """Pillow's bundled font only — a system TTF would make output vary."""
    px = max(6, min(400, int(px)))
    f = _FONTS.get(px)
    if f is None:
        try:
            f = ImageFont.load_default(size=px)
        except TypeError:               # very old Pillow
            f = ImageFont.load_default()
        _FONTS[px] = f
    return f


def _rot(points, cx: float, cy: float, deg: float):
    """Rotate scene points about a pivot. Positive is clockwise (y is down)."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y in points:
        dx, dy = float(x) - cx, float(y) - cy
        out.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return out


# --------------------------------------------------------------- parallax ----

#: Every set's layers, back to front, with a parallax factor.
#:
#: ``1.0`` means "pinned to the world" — it slides past at exactly camera
#: speed, which is what the ground does. ``0.0`` means "pinned to the frame",
#: which is what a sky does. Above ``1.0`` is nearer than the action and
#: whips past faster. Exported so a renderer can reason about the stack, and
#: so `draw_set(..., layers=[...])` can ask for a subset.
#: The four scroll rates the style is built on. A travelling shot uses at
#: least three of them, ideally all four: without parallax a travel scene is
#: a character sliding across a static painting.
PARALLAX: dict[str, float] = {
    "foreground": 1.50,   # nearer than the action, whips past
    "character":  1.00,   # the plane the actors stand on — pinned to the world
    "mid":        0.50,   # mid background
    "far":        0.18,   # far background, almost held
}

#: `k` per named layer. `layer_origin = origin - offset * (1 - k)`, so `k=1`
#: is pinned to the world and `k=0` is pinned to the frame.
SET_LAYERS: dict[str, tuple[tuple[str, float], ...]] = {
    "street": (("sky", 0.00), ("clouds", 0.06), ("skyline", 0.18),
               ("blocks", 0.50), ("frontage", 0.74), ("road", 1.00),
               ("foreground", 1.50)),
    "suburb": (("sky", 0.00), ("clouds", 0.06), ("treeline", 0.18),
               ("houses", 0.50), ("gardens", 0.74), ("road", 1.00),
               ("foreground", 1.50)),
    "highway": (("sky", 0.00), ("clouds", 0.06), ("hills", 0.18),
                ("distant", 0.50), ("verge", 0.74), ("road", 1.00),
                ("rail", 1.50)),
    # A top-down city has real depth, but it is *building height*, not
    # distance to a horizon: from a chopper the street is furthest away and a
    # tower roof is a third of the way to the camera, so towers slide over the
    # streets as you fly. The city is therefore banded by height rather than
    # by "background/foreground", and every band draws a whole building —
    # cast shadow, mass and roof clutter together — so nothing can come apart
    # from itself. Only the ground plane and the cloud under the aircraft sit
    # outside the bands.
    "aerial": (("base", 0.18), ("markings", 0.20), ("traffic", 0.24),
               ("lowrise", 0.55), ("midrise", 0.85), ("towers", 1.20),
               ("wisp", 1.50)),
    "office": (("wall", 0.18), ("openings", 0.50), ("furniture", 0.74),
               ("floor", 1.00)),
    # The chopper's own plane is `clouds`: cloud at the aircraft's altitude
    # slides past at exactly the aircraft's speed.
    "sky": (("sky", 0.00), ("sun", 0.04), ("high", 0.10),
            ("horizon", 0.18), ("far_clouds", 0.50), ("clouds", 1.00),
            ("near_clouds", 1.50)),
    # The summit stands on the character plane, because that is what the
    # character stands on. Everything behind it is ridge, and the low mist
    # in front of it is the only foreground the set has.
    "peak": (("sky", 0.00), ("clouds", 0.06), ("ridges", 0.18),
             ("shoulders", 0.50), ("summit", 1.00), ("mist", 1.50),
             ("rain", 1.85)),
}

#: Pixels per scene unit in the reference frame (960 x 540 for 100 x 56.25).
REF_UNIT = 960.0 / SCENE_W

#: Stroke weight, in reference pixels, by depth. A uniform line across body,
#: face, props and background is a named cheap-look failure: distance has to
#: thin the line as well as wash the colour.
STROKE_PX: dict[str, float] = {
    "far": 1.5, "mid": 2.2, "character": 3.0, "foreground": 3.8,
}


def stroke_w(depth: str = "character", *, unit: float | None = None) -> float:
    """Stroke weight for a depth band, in **scene units**.

    Scene units, not pixels, so it scales with `unit` automatically: pass
    `unit` only if you want the answer in pixels instead.
    """
    w = STROKE_PX.get(str(depth), STROKE_PX["character"]) / REF_UNIT
    return w if unit is None else w * float(unit)


def _stroke_band(k: float) -> str:
    """Which stroke weight a parallax layer draws with."""
    if k <= 0.28:
        return "far"
    if k <= 0.62:
        return "mid"
    if k < 1.22:
        return "character"
    return "foreground"


def _pt2(v, default: Pt) -> Pt:
    if isinstance(v, dict):
        v = (v.get("x", default[0]), v.get("y", default[1]))
    if isinstance(v, (tuple, list)) and len(v) >= 2:
        try:
            return (float(v[0]), float(v[1]))
        except (TypeError, ValueError):
            return default
    if isinstance(v, (int, float)):
        return (float(v), default[1])
    return default


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _camera_offset(camera: dict, origin: Pt, size_units: Pt,
                   t: float, seed: int) -> tuple[Pt, Pt]:
    """Work out how far the camera has travelled from its parallax anchor.

    Returns ``(base_origin, offset)``. `base_origin` is the top-left the
    frame would have if `camera["scroll"]` had actually moved it; `offset` is
    the vector a fully-pinned background has to be pushed back by.

    The camera dict is read defensively on purpose: it is documented as
    ``{"move","from","to","zoom","ease","hold"}`` but arrives from a
    renderer that adds its own keys, and it is legal for it to be ``{}``.
    Keys are tried in decreasing order of how much they actually know:

    1. ``dx``/``dy``            — the renderer already did the subtraction.
    2. ``cx``/``cy`` + ``base_cx``/``base_cy`` — do it here.
    3. ``anchor`` or ``from``   — the shot's starting centre.
    4. nothing                  — no parallax, everything moves together.

    ``scroll`` is an extra: scene units per second of world travel, for a
    caller that wants a street to stream past without driving `origin`
    itself. ``zoom`` is deliberately ignored — the renderer expresses zoom
    through `unit`, and honouring it twice would double it.
    """
    cam = camera if isinstance(camera, dict) else {}
    cx = origin[0] + size_units[0] / 2.0
    cy = origin[1] + size_units[1] / 2.0

    sx, sy = 0.0, 0.0
    scroll = cam.get("scroll")
    if scroll is not None:
        s = _pt2(scroll, (_num(scroll), 0.0))
        sx, sy = s[0] * float(t), s[1] * float(t)

    if "dx" in cam or "dy" in cam:
        dx, dy = _num(cam.get("dx")), _num(cam.get("dy"))
    elif ("base_cx" in cam or "base_cy" in cam) and ("cx" in cam or "cy" in cam):
        dx = _num(cam.get("cx"), cx) - _num(cam.get("base_cx"), cx)
        dy = _num(cam.get("cy"), cy) - _num(cam.get("base_cy"), cy)
    else:
        anchor = cam.get("anchor", cam.get("from"))
        if anchor is None:
            dx, dy = 0.0, 0.0
        else:
            ax, ay = _pt2(anchor, (cx, cy))
            dx, dy = cx - ax, cy - ay

    if str(cam.get("move", "")).lower() == "handheld":
        # A seeded wobble, sampled from `t` rather than accumulated, so
        # scrubbing to a frame gives the same frame.
        w = 0.30
        dx += w * math.sin(t * 2.7 + _r01(seed, 11) * 6.283)
        dy += w * 0.7 * math.sin(t * 3.9 + _r01(seed, 12) * 6.283)

    return ((origin[0] + sx, origin[1] + sy), (dx + sx, dy + sy))


class _Stage:
    """One frame's worth of drawing surface, plus the parallax arithmetic."""

    def __init__(self, d, size_px, unit, base_origin, offset, want,
                 layers=()):
        self.d = d
        self.size = size_px
        self.u = float(unit)
        self.origin = base_origin
        self.off = offset
        self.want = want
        #: `SET_LAYERS` is the single source of truth for scroll rates, so a
        #: set asks for a layer *by name* and cannot drift from the table.
        self.kmap = dict(layers)

    def layer(self, name: str, k: float | None = None) -> _Pen | None:
        """A pen whose origin has been shifted for this layer's depth.

        Deriving the shift from the origin rather than translating the
        drawing means a layer can ask `pen.bounds()` what part of the world
        it needs to build, and get the answer for *its own* depth.
        """
        if self.want is not None and name not in self.want:
            return None
        if name not in self.kmap and k is None:
            raise KeyError(f"layer {name!r} is not declared in SET_LAYERS")
        k = self.kmap.get(name, k if k is not None else 1.0)
        o = (self.origin[0] - self.off[0] * (1.0 - k),
             self.origin[1] - self.off[1] * (1.0 - k))
        band = _stroke_band(k)
        return _Pen(self.d, self.u, o, self.size,
                    stroke=STROKE_PX[band] / STROKE_PX["character"])


def layer_origins(name: str, *, unit: float, origin: Pt, size_px,
                  t: float = 0.0, camera: dict | None = None, seed: int = 0):
    """Where each layer of `name` would be drawn, without drawing anything.

    ``{layer: (k, (ox, oy))}`` back to front. Exported so a caller can
    reason about — or test — the parallax without reading pixels, and so a
    renderer that wants to composite the layers itself knows how far apart
    they are. Returns ``{}`` for a set this module does not have.
    """
    stack = SET_LAYERS.get(name)
    if not stack:
        return {}
    u = float(unit) or 1.0
    su = (int(size_px[0]) / u, int(size_px[1]) / u)
    base, off = _camera_offset(camera or {}, (float(origin[0]),
                                              float(origin[1])),
                               su, float(t), int(seed))
    return {ln: (k, (base[0] - off[0] * (1.0 - k),
                     base[1] - off[1] * (1.0 - k))) for ln, k in stack}


# ------------------------------------------------------------ placeholder ----

def _placeholder(d: ImageDraw.ImageDraw, box, label: str, look: dict,
                 note: str = "") -> None:
    """A deliberately ugly hole where a picture we do not have would go.

    It must never be mistakable for artwork at thumbnail size, and it must
    say what was asked for, because "the street looks wrong" is a much worse
    bug report than "MISSING SET: alleyway".
    """
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x1 - x0 < 4 or y1 - y0 < 4:
        return
    w, h = x1 - x0, y1 - y0
    acc = look.get("accent", (224, 46, 48))
    # Every fill here is opaque: a placeholder drawn straight onto an RGBA
    # frame would otherwise leave the hole see-through as well as ugly.
    back = (26, 26, 30)
    d.rectangle([x0, y0, x1, y1], fill=back + (255,))
    hatch = mix(acc, back, 0.76)
    step = max(10, int(min(w, h) * 0.13))
    for i in range(-h, w, step):
        d.line([(x0 + i, y1), (x0 + i + h, y0)], fill=hatch + (255,),
               width=max(1, step // 7))
    d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], outline=acc + (255,),
                width=max(2, int(min(w, h) * 0.014)))
    f = _font(max(9, int(min(w * 0.075, h * 0.16))))
    d.text(((x0 + x1) / 2, (y0 + y1) / 2), label, fill=(255, 255, 255, 255),
           font=f, anchor="mm")
    if note:
        fs = _font(max(8, int(min(w * 0.042, h * 0.09))))
        d.text(((x0 + x1) / 2, (y0 + y1) / 2 + h * 0.13), note,
               fill=acc + (255,), font=fs, anchor="mm")


# ------------------------------------------------------------- draw_set ------

def draw_set(img, name, look, *, unit, origin, t: float = 0.0,
             camera: dict | None = None, seed: int = 0,
             layers: list[str] | tuple[str, ...] | None = None):
    """Paint a set across the whole of `img`.

    Parameters
    ----------
    img     : the frame, ``RGB`` or ``RGBA``. Fully covered on success.
    name    : a key of `SETS`.
    look    : a `look.py` palette. Only the fourteen contract keys are read.
    unit    : pixels per scene unit.
    origin  : scene coordinate at the image's top-left pixel.
    t       : shot-local seconds. Anything on its own clock reads this.
    camera  : may be ``{}``; see `_camera_offset` for what is understood.
    seed    : the only source of randomness.
    layers  : optional subset of `SET_LAYERS[name]` to draw, for a renderer
              that wants to composite the stack itself. Additive and
              keyword-only, so the frozen call still works untouched.

    Returns ``None`` on success, or a truthy ``{"missing": True, ...}`` when
    it drew a placeholder because it does not have `name`.
    """
    W, H = img.size
    fn = SETS.get(name)
    if fn is None:
        MISSING.add(("set", str(name)))
        d = ImageDraw.Draw(img, "RGBA")
        _placeholder(d, (0, 0, W - 1, H - 1), f"MISSING SET: {name}",
                     _norm(look), note="sets.py has no set by that name")
        return {"missing": True, "kind": "set", "name": str(name),
                "have": sorted(SETS)}

    u = float(unit)
    if u <= 0 or W < 2 or H < 2:
        return None

    ss = SS_SET
    while ss > 1 and (W * ss) * (H * ss) > _MAX_TILE_PX:
        ss -= 1

    # RGB, deliberately. `ImageDraw.Draw(im, "RGBA")` only *blends* onto an
    # RGB surface; on an RGBA one it writes the tuple verbatim, so every
    # low-alpha fill — cloud, cast shadow, wisp — would punch a translucent
    # hole straight through the frame instead of veiling what is under it.
    big = Image.new("RGB", (W * ss, H * ss), tuple(_norm(look)["sky"]))
    d = ImageDraw.Draw(big, "RGBA")

    size_units = (W / u, H / u)
    base_origin, off = _camera_offset(camera or {}, tuple(origin), size_units,
                                      float(t), int(seed))
    want = None
    if layers is not None:
        want = {str(s) for s in layers}

    st = _Stage(d, (W * ss, H * ss), u * ss, base_origin, off, want,
                SET_LAYERS.get(str(name), ()))
    fn(st, _norm(look), float(t), int(seed))

    if ss > 1:
        big = big.resize((W, H), Image.LANCZOS)
    img.paste(big, (0, 0))
    return None


# ------------------------------------------------------------- draw_prop -----

#: How a prop is anchored to its ``at`` point.
#:
#: ``"ground"``  ``at`` is where it touches the floor, bbox ``y1 == 0``.
#: ``"vehicle"`` ``at`` is the body centre; it touches the floor at ``y1``.
#: ``"air"``     it does not touch anything and gets no contact shadow.
PROP_ANCHOR: dict[str, str] = {
    "car": "vehicle", "policecar": "vehicle", "milkfloat": "vehicle",
    "helicopter": "air",
    "cone": "ground", "bin": "ground", "hydrant": "ground",
    "lamppost": "ground", "tree": "ground", "building": "ground",
    "sign": "ground", "trafficlight": "ground", "cloud": "air",
    # Held props and close-ups: they hang in shot, so no contact shadow.
    "sandwich": "air", "indicator": "air",
}

#: Which props respond to which `anim` names, for a caller that wants to
#: validate a storyboard before rendering it.
PROP_ANIMS: dict[str, tuple[str, ...]] = {
    "car": ("bounce", "idle"),
    "policecar": ("bounce", "idle"),
    "milkfloat": ("bounce", "idle"),
    "helicopter": ("bob",),
    "tree": ("sway",),
    "cloud": ("drift",),
    # A traffic light's `anim` names the lamp that is lit. "cycle" runs the
    # real sequence off `t`; with no `anim` at all the state comes from
    # `phase`, so a board can hold it on red without knowing about any of it.
    "trafficlight": ("red", "amber", "green", "redamber", "cycle"),
    "indicator": ("blink", "on", "off"),
}

#: Half-extents in scene units at ``scale = 1``, as
#: ``(x0, y0, x1, y1)`` relative to ``at``.
_BBOX: dict[str, tuple[float, float, float, float]] = {
    "car":        (-22.0, -8.6, 22.0, 8.0),
    "policecar":  (-22.0, -11.9, 22.0, 8.0),
    "helicopter": (-31.0, -16.5, 35.0, 10.5),
    "cone":       (-3.4, -7.0, 3.4, 0.0),
    "bin":        (-3.9, -11.0, 3.9, 0.0),
    "hydrant":    (-2.9, -9.0, 2.9, 0.0),
    "lamppost":   (-1.6, -34.0, 8.2, 0.0),
    "tree":       (-11.0, -25.0, 11.0, 0.0),
    "building":   (-17.0, -46.0, 17.0, 0.0),
    "sign":       (-7.0, -19.0, 7.0, 0.0),
    "cloud":      (-16.0, -6.5, 16.0, 3.0),
    "milkfloat":  (-17.5, -17.6, 17.5, 8.0),
    "trafficlight": (-4.6, -35.4, 4.6, 0.0),
    "sandwich":   (-12.0, -16.8, 12.4, 0.6),
    "indicator":  (-9.0, -6.4, 9.0, 6.4),
}


def prop_bbox(kind: str, scale: float = 1.0):
    """The box a prop occupies, relative to its ``at``, with `scale` applied.

    An unknown kind gets the box the placeholder will be drawn in, so a
    caller that lays out from the bbox and a caller that draws stay in
    agreement about where the hole is.
    """
    s = float(scale) if scale else 1.0
    bb = _BBOX.get(kind)
    if bb is None:
        bb = (-6.0, -9.0, 6.0, 0.0)
    return (bb[0] * s, bb[1] * s, bb[2] * s, bb[3] * s)


def _edge(look: dict, fill: RGB, floor: float = 0.44) -> RGB:
    """The outline for one shape, derived from that shape's own fill.

    Same hue, a little more saturated, a lot darker. Every shape sharing one
    black line is what makes flat vector read as clip art; a red car wants a
    dark red edge, not a dark navy one. `look["ink"]` stays for silhouettes
    and for every facial feature, which do want to agree.
    """
    e = outline_for(fill)
    if lightness(e) > 46.0:                 # a pale fill would give a pale
        e = mix(e, look["ink"], floor)      # edge, which reads as no edge
    return e


#: Where a prop actually touches the ground, in design units. This is not
#: its bounding box: a car contacts the road across its tyres, not across
#: its bumpers, and a tree touches at the trunk, not at the canopy.
PROP_FOOT: dict[str, float] = {
    "car": 31.2, "policecar": 31.2, "cone": 6.8, "bin": 6.6,
    "hydrant": 5.2, "lamppost": 3.2, "tree": 12.0, "building": 34.0,
    "sign": 3.2, "milkfloat": 24.4, "trafficlight": 4.4,
}


def _prop_foot(kind: str) -> tuple[float, float]:
    """``(foot_span, height)`` for a prop's contact shadow, design units."""
    bb = _BBOX.get(kind, (-1.0, -1.0, 1.0, 1.0))
    return (PROP_FOOT.get(kind, (bb[2] - bb[0]) * 0.8),
            max(1.0, bb[3] - bb[1]))


def _shadow_axes(foot_span: float, height: float) -> tuple[float, float]:
    """Semi-axes of a contact shadow, in the caller's units.

    ``a = foot_span * 0.55``, ``b = height * 0.06`` — the house numbers. `b`
    is then held between a tenth and a third of `a`, so a wide flat prop like
    a car does not get a degenerate sliver and a tall thin one like a
    lamppost does not get a circle.
    """
    a = max(0.35, abs(float(foot_span)) * SHADOW_A)
    b = min(max(a * 0.10, abs(float(height)) * SHADOW_B), a * 0.34)
    return a, b


def _shadow_ellipse(pen: _Pen, look: dict, cx: float, gy: float,
                    foot_span: float, height: float,
                    opacity: float = SHADOW_OPACITY) -> None:
    """The contact ellipse, pinned to the ground plane.

    Semi-axes ``a = foot_span * SHADOW_A``, ``b = height * SHADOW_B``, drawn
    at `opacity`. This is the single most jarring depth error in flat 2D when
    it is missing: without it every figure and vehicle reads as a sticker
    floating in front of the background rather than standing on it.

    A wider skirt at a third of the opacity sits underneath. It is still two
    flat fills — the style forbids a gradient inside a shape — but it stops
    the ellipse itself having a hard cut edge.
    """
    sh = look.get("shadow") or (26, 40, 48)
    a, b = _shadow_axes(foot_span, height)
    o = min(0.60, max(0.0, float(opacity)))
    # Sat a little in front of the contact line rather than centred on it.
    # Side-on, the ground plane is seen almost edge-on: an ellipse centred on
    # the feet puts half its area on the wall behind them.
    cy = gy + b * 0.50
    pen.ellipse(cx, cy, a * 1.34, b * 1.18, col=alpha(sh, o * 0.30))
    pen.ellipse(cx, cy, a, b, col=alpha(sh, o))


def contact_shadow(img, look: dict, *, at: Pt, unit: float, origin: Pt,
                   foot_span: float, height: float,
                   opacity: float = SHADOW_OPACITY, ss: int = SS_PROP) -> None:
    """Draw a contact shadow on the ground under anything.

    Public so that characters and vehicles match: `rig.py` should call this
    for an actor rather than rolling its own, or the two will disagree about
    how hard the ground is.

    ``at`` is the point where the subject meets the ground, in scene units.
    ``foot_span`` is how wide its footprint is and ``height`` how tall it
    stands; both in scene units. `opacity` is clamped to `look`'s house range.
    """
    lk = _norm(look)
    lo, hi = _look.SHADOW_OPACITY_RANGE
    o = min(hi, max(lo, float(opacity)))
    a, b = _shadow_axes(foot_span, height)
    ea, eb = a * 1.34 + 1.0, b * 1.18 + 1.0
    u = float(unit)
    x0 = float(at[0]) - ea
    y0 = float(at[1]) - eb
    tw = max(2, int(math.ceil(ea * 2 * u)))
    th = max(2, int(math.ceil((eb + b * 0.5 + eb) * u)))
    tile = Image.new("RGBA", (tw * ss, th * ss), (0, 0, 0, 0))
    pen = _Pen(ImageDraw.Draw(tile, "RGBA"), u * ss, (x0, y0),
               (tw * ss, th * ss))
    _shadow_ellipse(pen, lk, float(at[0]), float(at[1]),
                    foot_span, height, o)
    tile = tile.resize((tw, th), Image.LANCZOS)
    px = int(round((x0 - float(origin[0])) * u))
    py = int(round((y0 - float(origin[1])) * u))
    img.alpha_composite(tile, (px, py)) if img.mode == "RGBA" else \
        img.paste(tile, (px, py), tile)


def _contact_shadow(pen: _Pen, look: dict, cx: float, gy: float,
                    foot_span: float, height: float = 0.0,
                    strength: float = 1.0) -> None:
    """`_shadow_ellipse` at the house opacity, for internal callers."""
    _shadow_ellipse(pen, look, cx, gy, foot_span,
                    height if height > 0 else foot_span * 0.32,
                    SHADOW_OPACITY * max(0.0, min(1.6, strength)))


def draw_prop(img, kind, look, *, at, unit, origin, scale: float = 1.0,
              phase: float = 0.0, seed: int = 0, t: float | None = None,
              anim: str | None = None, shadow: bool = True):
    """Paint one prop onto `img` at scene position `at`.

    `phase` is 0..1 and drives anything that cycles with the character
    animation — wheel spin, a bounce. `t` is shot-local seconds and drives
    anything on its own clock; when the caller does not pass it, it is
    derived from `phase` so a rotor still turns. Both `t` and `anim` are
    additive keyword-only arguments with defaults, so the frozen signature
    keeps working exactly as written.

    Returns ``None`` on success, or a truthy ``{"missing": True, ...}``.
    """
    W, H = img.size
    u = float(unit)
    if u <= 0 or W < 2 or H < 2:
        return None
    s = float(scale) if scale else 1.0
    ax, ay = float(at[0]), float(at[1])
    ox, oy = float(origin[0]), float(origin[1])
    L = _norm(look)
    tt = float(t) if t is not None else float(phase)

    fn = PROPS.get(kind)
    bb = prop_bbox(kind, s)

    if fn is None:
        MISSING.add(("prop", str(kind)))
        d = ImageDraw.Draw(img, "RGBA")
        _placeholder(d, ((ax + bb[0] - ox) * u, (ay + bb[1] - oy) * u,
                         (ax + bb[2] - ox) * u, (ay + bb[3] - oy) * u),
                     f"PROP: {kind}", L, note="no such prop")
        return {"missing": True, "kind": "prop", "name": str(kind),
                "have": sorted(PROPS)}

    pad = 2.6 * max(0.35, s)
    lx0, ly0 = bb[0] - pad, bb[1] - pad
    lx1, ly1 = bb[2] + pad, bb[3] + pad
    if shadow and PROP_ANCHOR.get(kind, "ground") != "air":
        # The contact shadow is wider and lower than the prop that casts it,
        # so the tile has to be grown or it gets sliced off at the bumper.
        sa, sb = _shadow_axes(*_prop_foot(kind))
        ub0 = prop_bbox(kind, 1.0)
        scx = (ub0[0] + ub0[2]) / 2.0 * s
        lx0 = min(lx0, scx - sa * 1.34 * s - 0.4)
        lx1 = max(lx1, scx + sa * 1.34 * s + 0.4)
        ly1 = max(ly1, bb[3] + sb * 1.68 * s + 0.4)

    # Cull before allocating: an off-screen prop is the common case in a
    # wide set full of street furniture.
    px0 = (ax + lx0 - ox) * u
    py0 = (ay + ly0 - oy) * u
    px1 = (ax + lx1 - ox) * u
    py1 = (ay + ly1 - oy) * u
    if px1 < 0 or py1 < 0 or px0 > W or py0 > H:
        return None

    tw = max(2, int(math.ceil((lx1 - lx0) * u)))
    th = max(2, int(math.ceil((ly1 - ly0) * u)))
    ss = SS_PROP
    while ss > 1 and (tw * ss) * (th * ss) > _MAX_TILE_PX:
        ss -= 1

    tile = Image.new("RGBA", (tw * ss, th * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile, "RGBA")
    # `scale` is folded into the pen, so every prop below draws in its own
    # design units and never has to think about it.
    pen = _Pen(d, u * ss * s, (lx0 / s, ly0 / s), (tw * ss, th * ss))
    ub = prop_bbox(kind, 1.0)

    if shadow and PROP_ANCHOR.get(kind, "ground") != "air":
        _contact_shadow(pen, L, (ub[0] + ub[2]) / 2.0, ub[3],
                        *_prop_foot(kind))

    fn(pen, L, s, float(phase) % 1.0, tt, int(seed), anim)

    if ss > 1:
        tile = tile.resize((tw, th), Image.LANCZOS)
    img.paste(tile, (int(round(px0)), int(round(py0))), tile)
    return None


# --------------------------------------------------------- shared drawing ----

def _win_grid(pen: _Pen, x0, y0, x1, y1, cols, rows, off_col, on_col,
              seed, idx, lit=0.0, gap=0.55) -> None:
    """A grid of flat windows. The only "texture" the style allows: shapes."""
    cols, rows = max(1, int(cols)), max(1, int(rows))
    w = (x1 - x0 - gap * (cols + 1)) / cols
    h = (y1 - y0 - gap * (rows + 1)) / rows
    if w <= 0.12 or h <= 0.12:
        return
    for r in range(rows):
        for c in range(cols):
            wx = x0 + gap + c * (w + gap)
            wy = y0 + gap + r * (h + gap)
            col = off_col
            if lit > 0 and _chance(lit, seed, idx, r, c, 3):
                col = on_col
            pen.rect(wx, wy, wx + w, wy + h, col=col)


def _blob(pen: _Pen, cx, cy, w, h, col, seed, idx, dy=0.0) -> None:
    """A flat-bottomed cluster of circles: the cartoon cloud/canopy shape."""
    n = 3 + int(_r01(seed, idx, 7) * 3)
    base = cy + h * 0.5 + dy
    xs, rs = [], []
    for i in range(n):
        fx = (i + 0.5) / n
        r = h * (0.40 + 0.36 * math.sin(math.pi * fx)) \
            * _rr(0.84, 1.18, seed, idx, i, 5)
        x = cx - w / 2.0 + fx * w
        pen.circle(x, base - r, r, col=col)
        xs.append(x)
        rs.append(r)
    # The base is flat, but only between the outermost circle *centres*.
    # Any wider and the corners poke out as a ledge, which is what makes a
    # thin cloud read as a lozenge with a plank under it.
    pen.rect(xs[0], base - min(rs) * 0.92, xs[-1], base, col=col)


def _cloud_shape(pen: _Pen, cx, cy, w, h, body, under, seed, idx) -> None:
    """Two flat shapes, not a gradient: the body and the shadowed underside."""
    _blob(pen, cx, cy, w, h, under, seed, idx, dy=h * 0.18)
    _blob(pen, cx, cy, w, h, body, seed, idx, dy=0.0)


def _cloud_band(pen: _Pen, look: dict, *, z, period, yr, seed,
                w=(26.0, 46.0), h=(7.0, 13.0)) -> None:
    """Clouds that tile for ever along x at one depth."""
    body, under = _cloud_cols(look, z)
    b = pen.bounds()
    i0 = int(math.floor((b[0] - period) / period))
    i1 = int(math.ceil((b[2] + period) / period))
    for i in range(i0, i1 + 1):
        if not _chance(0.72, seed, i, 1):
            continue
        cx = i * period + _rr(-period * 0.3, period * 0.3, seed, i, 2)
        cy = _rr(yr[0], yr[1], seed, i, 3)
        cw = _rr(w[0], w[1], seed, i, 4)
        ch = _rr(h[0], h[1], seed, i, 5)
        _cloud_shape(pen, cx, cy, cw, ch, body, under, seed, i)


def _tower(pen: _Pen, x0, x1, top, base, body, ink, glass, seed, idx,
           lit=0.0, on=None) -> None:
    """One flat block with a window grid, a cap and an edge shade."""
    pen.rect(x0, top, x1, base, col=body)
    pen.rect(x1 - (x1 - x0) * 0.17, top, x1, base, col=shade(body, 0.93))
    cap = _r01(seed, idx, 21)
    if cap < 0.34:
        pen.rect(x0 - 0.5, top - 1.0, x1 + 0.5, top, col=shade(body, 0.86))
    elif cap < 0.55:
        pen.poly([(x0, top), (x1, top), ((x0 + x1) / 2, top - (x1 - x0) * 0.34)],
                 col=shade(body, 0.88))
    cols = max(2, int((x1 - x0) / 2.6))
    rows = max(2, int((base - top) / 3.1))
    _win_grid(pen, x0 + 0.9, top + 1.5, x1 - 0.9, base - 1.2, cols, rows,
              glass, on if on is not None else mix(glass, ink, 0.45),
              seed, idx, lit=lit, gap=0.7)
    del ink


# ----------------------------------------------------------- set: street -----

def _skyline(pen: _Pen, look: dict, gy: float, z: float, seed: int) -> None:
    sky, ink = look["sky"], look["ink"]
    fam = (look["mid"], look["far"], mix(look["mid"], look["far"], 0.5),
           mix(look["far"], look["near"], 0.35))
    b = pen.bounds()
    P = 17.0
    for i in range(int(math.floor(b[0] / P)) - 2, int(math.ceil(b[2] / P)) + 2):
        x0 = i * P + _rr(0.0, 3.0, seed, i, 1)
        x1 = x0 + _rr(9.0, 15.5, seed, i, 2)
        top = gy - _rr(20.0, 41.0, seed, i, 3)
        body = depth_tint(_pick(fam, seed, i, 4), z, sky)
        glass = depth_tint(mix(_glass(look), look["far"], 0.4), z * 0.94, sky)
        on = depth_tint(_lit_window(look), z * 0.55, sky)
        _tower(pen, x0, x1, top, gy + 2.0, body, ink, glass, seed, i,
               lit=_lit_rate(look) + 0.14, on=on)
        if _chance(0.28, seed, i, 9):
            mx = (x0 + x1) / 2.0
            pen.rect(mx - 0.22, top - _rr(3.0, 7.0, seed, i, 10), mx + 0.22,
                     top, col=shade(body, 0.84))


def _city_blocks(pen: _Pen, look: dict, gy: float, z: float,
                 seed: int) -> None:
    sky, ink = look["sky"], look["ink"]
    fam = (mix(look["mid"], look["near"], 0.30), shade(look["mid"], 0.94),
           mix(look["mid"], look["far"], 0.24), tint(look["mid"], 0.10),
           mix(look["near"], look["far"], 0.20))
    b = pen.bounds()
    P = 25.0
    for i in range(int(math.floor(b[0] / P)) - 2, int(math.ceil(b[2] / P)) + 2):
        x0 = i * P + _rr(0.0, 4.0, seed, i, 1)
        x1 = x0 + _rr(15.0, 21.0, seed, i, 2)
        top = gy - _rr(22.0, 36.0, seed, i, 3)
        body = depth_tint(_pick(fam, seed, i, 4), z, sky)
        glass = depth_tint(_glass(look), z * 0.9, sky)
        pen.rect(x0, top, x1, gy + 2.0, col=body)
        pen.rect(x1 - (x1 - x0) * 0.15, top, x1, gy + 2.0,
                 col=shade(body, 0.94))
        # parapet and a string course, both flat bands
        pen.rect(x0 - 0.6, top - 1.1, x1 + 0.6, top, col=shade(body, 0.85))
        pen.rect(x0, top + 4.6, x1, top + 5.4, col=shade(body, 0.90))
        cols = max(2, int((x1 - x0) / 3.4))
        rows = max(3, int((gy - top - 7.0) / 4.0))
        _win_grid(pen, x0 + 1.2, top + 6.4, x1 - 1.2, gy - 1.0, cols, rows,
                  glass, depth_tint(_lit_window(look), z * 0.5, sky), seed, i,
                  lit=_lit_rate(look) + 0.08, gap=0.9)
        r = _r01(seed, i, 30)
        if r < 0.30:                                   # water tank
            tx = x0 + (x1 - x0) * _rr(0.25, 0.7, seed, i, 31)
            tw, th = 3.4, 3.6
            c = depth_tint(mix(look["far"], ink, 0.30), z, sky)
            pen.rect(tx - tw / 2, top - 1.1 - th, tx + tw / 2, top - 1.1, col=c)
            pen.poly([(tx - tw / 2 - 0.5, top - 1.1 - th),
                      (tx + tw / 2 + 0.5, top - 1.1 - th),
                      (tx, top - 1.1 - th - 1.9)], col=shade(c, 0.9))
        elif r < 0.50:                                 # rooftop billboard
            bw = (x1 - x0) * 0.7
            bx = (x0 + x1) / 2.0
            bh = 5.2
            frame = depth_tint(mix(ink, look["far"], 0.45), z, sky)
            pen.rect(bx - bw / 2, top - 1.1 - bh, bx + bw / 2, top - 1.1,
                     col=depth_tint(look["accent2"], z * 0.55, sky),
                     ink=frame, w=0.3)
            pen.rect(bx - bw * 0.30, top - 1.1 - bh * 0.68,
                     bx + bw * 0.30, top - 1.1 - bh * 0.34,
                     col=depth_tint(look["accent"], z * 0.55, sky))
            pen.line([(bx - bw / 2 + 1, top - 1.1), (bx - bw / 2 + 1, top + 0.6)],
                     frame, 0.28)
            pen.line([(bx + bw / 2 - 1, top - 1.1), (bx + bw / 2 - 1, top + 0.6)],
                     frame, 0.28)
        elif r < 0.66:                                 # roof boxes
            c = depth_tint(shade(body, 0.86), 0.0, sky)
            for k in range(2):
                bx = x0 + (x1 - x0) * (0.25 + 0.4 * k)
                pen.rect(bx - 1.6, top - 1.1 - 2.2, bx + 1.6, top - 1.1, col=c)


def _frontage(pen: _Pen, look: dict, gy: float, seed: int) -> None:
    ink = look["ink"]
    glass = _glass(look)
    onc = _lit_window(look)
    shop = mix(onc, glass, 0.25) if _night(look) else glass
    fam = (look["near"], shade(look["near"], 0.93), tint(look["near"], 0.08),
           mix(look["near"], look["mid"], 0.45),
           mix(look["near"], look["accent"], 0.10))
    awn = (look["accent"], look["accent2"], mix(look["accent"], ink, 0.22),
           mix(look["accent2"], look["far"], 0.30))
    b = pen.bounds()
    P = 21.0
    for i in range(int(math.floor(b[0] / P)) - 2, int(math.ceil(b[2] / P)) + 2):
        gap = _rr(1.6, 5.0, seed, i, 0)
        x0 = i * P + gap
        x1 = i * P + P - _rr(0.0, 1.2, seed, i, 1)
        if x1 - x0 < 8.0:
            continue
        top = gy - _rr(15.0, 24.0, seed, i, 2)
        body = _pick(fam, seed, i, 3)
        pen.rect(x0, top, x1, gy + 2.0, col=body)
        pen.rect(x1 - (x1 - x0) * 0.10, top, x1, gy + 2.0,
                 col=shade(body, 0.93))
        pen.rect(x0 - 0.7, top - 1.3, x1 + 0.7, top, col=shade(body, 0.84))
        pen.rect(x0 - 0.4, top - 1.3, x1 + 0.4, top - 0.8,
                 col=shade(body, 0.74))

        # upper storeys
        rows = max(1, int((gy - 11.0 - top) / 5.4))
        cols = max(2, int((x1 - x0) / 4.6))
        _win_grid(pen, x0 + 1.4, top + 2.2, x1 - 1.4, gy - 11.4, cols, rows,
                  glass, onc, seed, i, lit=_lit_rate(look) + 0.06, gap=1.3)
        for r in range(rows):                          # sills
            sy = top + 2.2 + (r + 1) * (gy - 13.6 - top) / rows
            pen.rect(x0 + 1.0, sy, x1 - 1.0, sy + 0.42,
                     col=shade(body, 0.86))

        # shopfront
        sh_top = gy - 9.4
        pen.rect(x0, sh_top, x1, gy, col=shade(body, 0.90))
        wx0, wx1 = x0 + 1.2, x1 - 5.6
        pen.rect(wx0, sh_top + 1.6, wx1, gy - 0.6, col=shop,
                 ink=mix(ink, body, 0.35), w=0.32)
        pen.poly([(wx0 + 0.6, gy - 1.2), (wx0 + (wx1 - wx0) * 0.42, sh_top + 2.2),
                  (wx0 + (wx1 - wx0) * 0.60, sh_top + 2.2),
                  (wx0 + (wx1 - wx0) * 0.20, gy - 1.2)],
                 col=tint(glass, 0.40))
        dx0 = x1 - 4.8
        pen.rect(dx0, sh_top + 1.2, dx0 + 3.4, gy, col=shade(body, 0.66),
                 ink=mix(ink, body, 0.4), w=0.3)
        pen.rect(dx0 + 0.5, sh_top + 1.9, dx0 + 2.9, sh_top + 4.6,
                 col=mix(shop, ink, 0.18))
        pen.circle(dx0 + 3.0, gy - 4.2, 0.34, col=ink)

        # awning: flat scallops, no gradient
        ac = _pick(awn, seed, i, 6)
        ay0, ay1 = sh_top - 0.4, sh_top + 2.4
        pen.poly([(x0 + 0.6, ay0), (wx1 + 0.6, ay0),
                  (wx1 + 1.4, ay1), (x0 - 0.2, ay1)], col=ac)
        nsc = max(3, int((wx1 - x0) / 2.4))
        for k in range(nsc):
            sx = x0 - 0.2 + (k + 0.5) * (wx1 + 1.6 - x0) / nsc
            pen.circle(sx, ay1, (wx1 + 1.6 - x0) / nsc * 0.5, col=ac)
        pen.rect(x0 - 0.2, ay1 - 0.5, wx1 + 1.4, ay1 - 0.1,
                 col=shade(ac, 0.80))

        # fascia sign board — a shape, never text
        pen.rect(x0 + 0.8, sh_top - 3.6, wx1 + 0.4, sh_top - 0.9,
                 col=shade(body, 0.72), ink=mix(ink, body, 0.5), w=0.26)
        pen.rect(x0 + 2.0, sh_top - 2.9, x0 + 2.0 + (wx1 - x0) * 0.42,
                 sh_top - 1.7, col=_pick(awn, seed, i, 7))

        if _chance(0.34, seed, i, 8):                  # air-con box
            pen.rect(x1 - 4.2, top + 3.0, x1 - 2.2, top + 4.6,
                     col=shade(body, 0.74))


def _road(pen: _Pen, look: dict, gy: float, seed: int,
          residential: bool = False) -> None:
    """Pavement, kerb, then tarmac.

    `gy` is where a character stands, so the band immediately below it has
    to be pavement — put the road there and every walk cycle happens in the
    middle of the traffic.
    """
    ink = look["ink"]
    road = _asphalt(look)
    b = pen.bounds()
    x0, x1, ybot = b[0] - 8.0, b[2] + 8.0, b[3] + 4.0
    pave = mix(look["ground"], look["near"], 0.34)
    kerb_top = gy + 2.3
    kerb_bot = gy + 3.1

    pen.rect(x0, gy, x1, kerb_top, col=pave)
    pen.line([(x0, gy + 0.05), (x1, gy + 0.05)], shade(pave, 0.72), 0.24)
    for i in range(int(x0 // 6) - 1, int(x1 // 6) + 2):          # slabs
        pen.rect(i * 6.0, gy + 0.4, i * 6.0 + 0.22, kerb_top,
                 col=shade(pave, 0.92))
    pen.rect(x0, kerb_top, x1, kerb_bot, col=shade(pave, 0.74))
    pen.rect(x0, kerb_top, x1, kerb_top + 0.3, col=tint(pave, 0.22))
    pen.rect(x0, kerb_bot, x1, ybot, col=road)
    pen.rect(x0, kerb_bot, x1, kerb_bot + 0.9, col=shade(road, 0.82))

    patch = tint(road, 0.05)
    for i in range(int(x0 // 23) - 1, int(x1 // 23) + 2):
        px = i * 23.0 + _rr(0, 14, seed, i, 1)
        pw = _rr(6.0, 13.0, seed, i, 2)
        py = kerb_bot + _rr(1.6, 7.6, seed, i, 3)
        pen.rect(px, py, px + pw, py + _rr(1.6, 3.4, seed, i, 4), col=patch)

    man = shade(road, 0.84)
    for i in range(int(x0 // 37) - 1, int(x1 // 37) + 2):
        mx = i * 37.0 + _rr(0, 26, seed, i, 5)
        my = kerb_bot + _rr(2.6, 7.0, seed, i, 6)
        pen.ellipse(mx, my, 2.5, 0.85, col=man)
        pen.ellipse(mx, my, 1.7, 0.5, col=shade(road, 0.74))

    paint = _at_lightness(mix(look["near"], (255, 255, 255), 0.6),
                          min(96.0, lightness(road) + 42.0))
    if residential:
        # A quiet residential street has no centre line. It does have double
        # yellows outside somebody's drive, which is the only paint here.
        yellow = _hued(48.0, 0.80, min(84.0, lightness(road) + 34.0))
        for i in range(int(x0 // 34) - 1, int(x1 // 34) + 2):
            if not _chance(0.45, seed, i, 11):
                continue
            lx = i * 34.0 + _rr(0.0, 18.0, seed, i, 12)
            lw = _rr(12.0, 24.0, seed, i, 13)
            pen.rect(lx, kerb_bot + 1.5, lx + lw, kerb_bot + 1.98, col=yellow)
            pen.rect(lx, kerb_bot + 2.4, lx + lw, kerb_bot + 2.88, col=yellow)
        # a faint gutter line the whole way, so the tarmac is not a void
        pen.rect(x0, kerb_bot + 0.95, x1, kerb_bot + 1.25,
                 col=mix(paint, road, 0.62))
    else:
        lane_y = kerb_bot + (ybot - kerb_bot) * 0.46
        for i in range(int(x0 // 15) - 1, int(x1 // 15) + 2):
            pen.rect(i * 15.0, lane_y, i * 15.0 + 7.6, lane_y + 0.78,
                     col=paint)
        pen.rect(x0, kerb_bot + 1.5, x1, kerb_bot + 1.92,
                 col=mix(paint, road, 0.30))          # gutter edge line
    del ink


def _street_fg(pen: _Pen, look: dict, seed: int) -> None:
    ink, road = look["ink"], _asphalt(look)
    b = pen.bounds()
    x0, x1, ybot = b[0] - 10.0, b[2] + 10.0, b[3]
    kerb_y = ybot - 2.0
    dark = mix(road, ink, 0.42)
    for i in range(int(x0 // 27) - 1, int(x1 // 27) + 2):
        bx = i * 27.0 + _rr(0, 20, seed, i, 1)
        pen.rrect(bx - 0.85, kerb_y - 4.4, bx + 0.85, kerb_y + 0.6, 0.8,
                  col=dark)
        pen.rect(bx - 0.85, kerb_y - 3.6, bx + 0.85, kerb_y - 3.1,
                 col=mix(look["accent2"], dark, 0.45))
    pen.rect(x0, kerb_y, x1, ybot + 4.0, col=mix(road, ink, 0.42))
    pen.rect(x0, kerb_y, x1, kerb_y + 0.55, col=mix(road, look["near"], 0.28))
    pen.rect(x0, kerb_y - 0.35, x1, kerb_y, col=mix(road, ink, 0.62))


def _set_street(st: _Stage, look: dict, t: float, seed: int) -> None:
    gy = GROUND_Y
    p = st.layer("sky")
    if p:
        top, bot = sky_gradient(look["sky"])
        p.vgrad(top, bot, 0.0, gy + 2.0)
    p = st.layer("clouds")
    if p:
        _cloud_band(p, look, z=0.80, period=58.0, yr=(4.0, 15.0),
                    seed=seed ^ 0x11)
    p = st.layer("skyline")
    if p:
        _skyline(p, look, gy, 0.62, seed ^ 0x21)
    p = st.layer("blocks")
    if p:
        _city_blocks(p, look, gy, 0.28, seed ^ 0x31)
    p = st.layer("frontage")
    if p:
        _frontage(p, look, gy, seed ^ 0x41)
    p = st.layer("road")
    if p:
        _road(p, look, gy, seed ^ 0x51)
    p = st.layer("foreground")
    if p:
        _street_fg(p, look, seed ^ 0x61)
    del t


# ---------------------------------------------------------- set: highway -----

def _hills(pen: _Pen, base_y, col, seed, period=46.0, amp=(5.0, 13.0)) -> None:
    b = pen.bounds()
    P = period
    i0 = int(math.floor((b[0] - P) / P))
    i1 = int(math.ceil((b[2] + P) / P))
    keys = [(i * P, base_y - _rr(amp[0], amp[1], seed, i, 1))
            for i in range(i0, i1 + 2)]
    poly = []
    for k in range(len(keys) - 1):
        (x0, y0), (x1, y1) = keys[k], keys[k + 1]
        for s in range(10):
            f = s / 10.0
            ff = (1.0 - math.cos(f * math.pi)) / 2.0
            poly.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * ff))
    poly.append(keys[-1])
    poly += [(keys[-1][0], base_y + 14.0), (keys[0][0], base_y + 14.0)]
    pen.poly(poly, col=col)


def _pylon(pen: _Pen, x, base_y, h, col) -> None:
    w = h * 0.24
    pen.line([(x - w / 2, base_y), (x - w * 0.13, base_y - h)], col, 0.32)
    pen.line([(x + w / 2, base_y), (x + w * 0.13, base_y - h)], col, 0.32)
    for k in range(4):
        f0, f1 = k / 4.0, (k + 1) / 4.0
        y0, y1 = base_y - h * f0, base_y - h * f1
        w0 = w * (0.5 - 0.37 * f0)
        w1 = w * (0.5 - 0.37 * f1)
        pen.line([(x - w0, y0), (x + w1, y1)], col, 0.20)
        pen.line([(x + w0, y0), (x - w1, y1)], col, 0.20)
        pen.line([(x - w0, y0), (x + w0, y0)], col, 0.20)
    for k, f in ((0, 0.72), (1, 0.86)):
        y = base_y - h * f
        aw = w * (1.5 - 0.4 * k)
        pen.line([(x - aw, y), (x + aw, y)], col, 0.26)


def _tree_shape(pen: _Pen, x, base_y, h, leaf, dark, trunk, ink, seed, idx,
                lean=0.0) -> None:
    tw = h * 0.075
    pen.poly([(x - tw, base_y), (x + tw, base_y),
              (x + tw * 0.55 + lean, base_y - h * 0.58),
              (x - tw * 0.55 + lean, base_y - h * 0.58)], col=trunk)
    cx = x + lean
    cy = base_y - h * 0.72
    r = h * 0.30
    for dxx, dyy, rr in ((-0.62, 0.20, 0.72), (0.62, 0.16, 0.70),
                         (0.0, -0.34, 0.82), (-0.24, 0.42, 0.62),
                         (0.30, 0.44, 0.60), (-0.44, -0.14, 0.58),
                         (0.42, -0.16, 0.56)):
        pen.circle(cx + dxx * r * 1.5, cy + dyy * r * 1.5, r * rr, col=leaf)
    for dxx, dyy, rr in ((0.52, 0.44, 0.52), (0.02, 0.56, 0.46),
                         (-0.46, 0.48, 0.42)):
        pen.circle(cx + dxx * r * 1.5, cy + dyy * r * 1.5, r * rr, col=dark)
    for dxx, dyy, rr in ((-0.30, -0.30, 0.34), (0.26, -0.10, 0.28)):
        pen.circle(cx + dxx * r * 1.5, cy + dyy * r * 1.5, r * rr,
                   col=tint(leaf, 0.16))
    del ink, seed, idx


def _set_highway(st: _Stage, look: dict, t: float, seed: int) -> None:
    sky, ink = look["sky"], look["ink"]
    gy = GROUND_Y
    road = _asphalt(look)

    p = st.layer("sky")
    if p:
        top, bot = sky_gradient(sky)
        p.vgrad(top, bot, 0.0, gy + 2.0)
        b = p.bounds()
        sx = b[0] + (b[2] - b[0]) * 0.30
        disc, halo = _sun(look)
        p.circle(sx, 7.2, 10.0, col=mix(sky, halo, 0.22))
        p.circle(sx, 7.2, 6.8, col=mix(sky, halo, 0.48))
        p.circle(sx, 7.2, 4.2, col=disc)
    p = st.layer("clouds")
    if p:
        _cloud_band(p, look, z=0.82, period=52.0, yr=(5.0, 18.0),
                    seed=seed ^ 0x71, w=(30.0, 54.0), h=(8.0, 15.0))
    p = st.layer("hills")
    if p:
        _hills(p, gy - 2.0, depth_tint(look["far"], 0.66, sky), seed ^ 0x72,
               period=58.0, amp=(6.0, 15.0))
        _hills(p, gy - 0.5, depth_tint(mix(look["far"], look["ground"], 0.35),
                                       0.52, sky), seed ^ 0x73,
               period=41.0, amp=(3.0, 9.0))
    p = st.layer("distant")
    if p:
        c = depth_tint(mix(look["far"], ink, 0.35), 0.42, sky)
        b = p.bounds()
        for i in range(int(b[0] // 42) - 1, int(b[2] // 42) + 2):
            _pylon(p, i * 42.0 + _rr(0, 26, seed, i, 3), gy - 1.5,
                   _rr(11.0, 15.0, seed, i, 4), c)
        leaf = depth_tint(_foliage(look), 0.46, sky)
        for i in range(int(b[0] // 11) - 1, int(b[2] // 11) + 2):
            if _chance(0.55, seed, i, 5):
                p.circle(i * 11.0 + _rr(0, 8, seed, i, 6), gy - 3.4,
                         _rr(2.2, 3.8, seed, i, 7), col=leaf)
        p.rect(b[0] - 6, gy - 2.6, b[2] + 6, gy + 2.0, col=leaf)
    p = st.layer("verge")
    if p:
        b = p.bounds()
        grass = _foliage(look)
        p.rect(b[0] - 8, gy - 3.2, b[2] + 8, gy + 2.0, col=grass)
        p.rect(b[0] - 8, gy - 3.2, b[2] + 8, gy - 2.75, col=tint(grass, 0.22))
        for i in range(int(b[0] // 34) - 1, int(b[2] // 34) + 2):
            r = _r01(seed, i, 8)
            x = i * 34.0 + _rr(0, 24, seed, i, 9)
            if r < 0.42:
                _tree_shape(p, x, gy - 2.2, _rr(16.0, 24.0, seed, i, 10),
                            grass, shade(grass, 0.80),
                            mix(ink, look["ground"], 0.45), ink, seed, i)
            elif r < 0.62:                             # gantry sign
                _gantry(p, x, gy - 2.2, look, seed, i)
            elif r < 0.78:                             # roadside billboard
                bw, bh = 15.0, 8.0
                p.rect(x - 0.6, gy - 2.2 - 12.0, x + 0.6, gy - 2.2,
                       col=mix(ink, look["ground"], 0.40))
                p.rect(x - bw / 2, gy - 14.2 - bh, x + bw / 2, gy - 14.2,
                       col=look["accent2"], ink=mix(ink, look["ground"], 0.4),
                       w=0.32)
                p.rect(x - bw * 0.3, gy - 14.2 - bh * 0.66,
                       x + bw * 0.3, gy - 14.2 - bh * 0.34, col=look["accent"])
    p = st.layer("road")
    if p:
        b = p.bounds()
        x0, x1, ybot = b[0] - 10, b[2] + 10, b[3] + 4
        bar = _at_lightness(desaturate(mix(look["near"], ink, 0.24), 0.72),
                            min(88.0, lightness(road) + 34.0))
        for i in range(int(x0 // 7) - 1, int(x1 // 7) + 2):
            p.rect(i * 7.0 - 0.34, gy - 2.4, i * 7.0 + 0.34, gy - 0.1,
                   col=shade(bar, 0.60))
        p.rect(x0, gy - 3.1, x1, gy - 1.85, col=bar)
        p.rect(x0, gy - 2.55, x1, gy - 2.2, col=shade(bar, 0.76))
        p.rect(x0, gy - 1.85, x1, gy - 1.5, col=shade(bar, 0.52))
        p.rect(x0, gy, x1, ybot, col=road)
        p.line([(x0, gy + 0.05), (x1, gy + 0.05)], mix(ink, road, 0.5), 0.24)
        paint = _at_lightness(mix(look["near"], (255, 255, 255), 0.6),
                              min(96.0, lightness(road) + 42.0))
        p.rect(x0, gy + 1.2, x1, gy + 1.75, col=paint)
        p.rect(x0, ybot - 3.6, x1, ybot - 3.05, col=paint)
        for lane_y in (gy + (ybot - gy) * 0.36, gy + (ybot - gy) * 0.68):
            for i in range(int(x0 // 19) - 1, int(x1 // 19) + 2):
                p.rect(i * 19.0, lane_y, i * 19.0 + 11.0, lane_y + 0.85,
                       col=paint)
    p = st.layer("rail")
    if p:
        b = p.bounds()
        x0, x1, ybot = b[0] - 12, b[2] + 12, b[3]
        rail = _at_lightness(desaturate(mix(look["near"], ink, 0.30), 0.70),
                             max(16.0, lightness(road) - 12.0))
        dark = shade(rail, 0.62)
        for i in range(int(x0 // 12) - 1, int(x1 // 12) + 2):
            p.rect(i * 12.0 - 0.7, ybot - 2.2, i * 12.0 + 0.7, ybot + 4.0,
                   col=dark)
        p.rect(x0, ybot - 2.9, x1, ybot + 4.0, col=rail)
        p.rect(x0, ybot - 2.9, x1, ybot - 2.4, col=shade(rail, 1.28))
        p.rect(x0, ybot - 1.5, x1, ybot - 1.1, col=dark)
    del t


def _gantry(pen: _Pen, x, base_y, look: dict, seed, idx) -> None:
    ink = look["ink"]
    post = mix(ink, look["ground"], 0.42)
    h = _rr(15.0, 19.0, seed, idx, 20)
    pen.rect(x - 0.7, base_y - h, x + 0.7, base_y, col=post)
    arm = _rr(11.0, 16.0, seed, idx, 21)
    pen.rect(x, base_y - h, x + arm, base_y - h + 1.0, col=post)
    bw, bh = arm * 0.8, 6.4
    bx = x + arm - bw / 2 - 0.4
    board = _at_lightness(_hued(148.0, 0.44, 30.0), 28.0)
    pen.rect(bx - bw / 2, base_y - h + 1.0, bx + bw / 2,
             base_y - h + 1.0 + bh, col=board, ink=shade(board, 0.7), w=0.28)
    pen.rect(bx - bw * 0.34, base_y - h + 2.4, bx + bw * 0.10,
             base_y - h + 3.2, col=mix(look["near"], look["sky"], 0.3))
    pen.poly([(bx + bw * 0.18, base_y - h + 2.0),
              (bx + bw * 0.36, base_y - h + 2.8),
              (bx + bw * 0.18, base_y - h + 3.6)],
             col=mix(look["near"], look["sky"], 0.3))


# ----------------------------------------------------------- set: aerial -----

_A_PX = 38.0        # road grid pitch, x
_A_PY = 30.0        # road grid pitch, y
_A_RW = 9.0         # road width


def _aerial_cells(pen: _Pen, pad=1):
    b = pen.bounds()
    i0 = int(math.floor(b[0] / _A_PX)) - pad
    i1 = int(math.ceil(b[2] / _A_PX)) + pad
    j0 = int(math.floor(b[1] / _A_PY)) - pad
    j1 = int(math.ceil(b[3] / _A_PY)) + pad
    return i0, i1, j0, j1


def _aerial_block(i, j):
    """The rectangle of the city block between roads ``i..i+1``, ``j..j+1``."""
    return (i * _A_PX + _A_RW / 2, j * _A_PY + _A_RW / 2,
            (i + 1) * _A_PX - _A_RW / 2, (j + 1) * _A_PY - _A_RW / 2)


def _set_aerial(st: _Stage, look: dict, t: float, seed: int) -> None:
    ink = look["ink"]
    road = shade(_asphalt(look), 0.90)

    p = st.layer("base")
    if p:
        p.fill(road)

    p = st.layer("markings")
    if p:
        i0, i1, j0, j1 = _aerial_cells(p)
        paint = _at_lightness(mix(look["near"], (255, 255, 255), 0.6),
                              min(94.0, lightness(road) + 40.0))
        dash = mix(paint, road, 0.28)
        for j in range(j0, j1 + 1):
            y = j * _A_PY
            for k in range(int(i0 * _A_PX // 8), int(i1 * _A_PX // 8) + 1):
                p.rect(k * 8.0, y - 0.35, k * 8.0 + 4.4, y + 0.35, col=dash)
        for i in range(i0, i1 + 1):
            x = i * _A_PX
            for k in range(int(j0 * _A_PY // 8), int(j1 * _A_PY // 8) + 1):
                p.rect(x - 0.35, k * 8.0, x + 0.35, k * 8.0 + 4.4, col=dash)
        stripe = paint
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                cx, cy = i * _A_PX, j * _A_PY
                for k in range(4):
                    o = -_A_RW / 2 + 1.2 + k * 2.0
                    p.rect(cx + o, cy - _A_RW / 2 - 2.4,
                           cx + o + 1.0, cy - _A_RW / 2 - 0.6, col=stripe)
                    p.rect(cx - _A_RW / 2 - 2.4, cy + o,
                           cx - _A_RW / 2 - 0.6, cy + o + 1.0, col=stripe)

    #: How tall a plot builds. Fixed per plot, so a building keeps its height
    #: — and therefore its parallax band — for the whole film.
    def tier_of(i, j):
        r = _r01(seed, i, j, 41)
        return 2 if r > 0.86 else (1 if r > 0.54 else 0)

    fam = (look["mid"], look["near"], mix(look["mid"], look["far"], 0.35),
           mix(look["near"], look["ground"], 0.30), shade(look["mid"], 0.88),
           tint(look["near"], 0.10))

    p = st.layer("base")
    if p:
        p.fill(road)
        i0, i1, j0, j1 = _aerial_cells(p)
        g = _foliage(look)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if not _chance(0.13, seed, i, j, 1):
                    continue
                bx0, by0, bx1, by1 = _aerial_block(i, j)
                p.rrect(bx0, by0, bx1, by1, 1.6, col=g)
                for k in range(9):
                    p.circle(_rr(bx0 + 2, bx1 - 2, seed, i, j, k, 2),
                             _rr(by0 + 2, by1 - 2, seed, i, j, k, 3),
                             _rr(1.1, 2.1, seed, i, j, k, 4),
                             col=shade(g, 0.78))
                p.line([(bx0 + 1.5, by0 + 1.5), (bx1 - 1.5, by1 - 1.5)],
                       mix(g, look["ground"], 0.55), 0.7)

    p = st.layer("markings")
    if p:
        i0, i1, j0, j1 = _aerial_cells(p)
        paint = _at_lightness(mix(look["near"], (255, 255, 255), 0.6),
                              min(94.0, lightness(road) + 40.0))
        dash = mix(paint, road, 0.28)
        for j in range(j0, j1 + 1):
            y = j * _A_PY
            for k in range(int(i0 * _A_PX // 8), int(i1 * _A_PX // 8) + 1):
                p.rect(k * 8.0, y - 0.35, k * 8.0 + 4.4, y + 0.35, col=dash)
        for i in range(i0, i1 + 1):
            x = i * _A_PX
            for k in range(int(j0 * _A_PY // 8), int(j1 * _A_PY // 8) + 1):
                p.rect(x - 0.35, k * 8.0, x + 0.35, k * 8.0 + 4.4, col=dash)
        stripe = paint
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                cx, cy = i * _A_PX, j * _A_PY
                for k in range(4):
                    o = -_A_RW / 2 + 1.2 + k * 2.0
                    p.rect(cx + o, cy - _A_RW / 2 - 2.4,
                           cx + o + 1.0, cy - _A_RW / 2 - 0.6, col=stripe)
                    p.rect(cx - _A_RW / 2 - 2.4, cy + o,
                           cx - _A_RW / 2 - 0.6, cy + o + 1.0, col=stripe)

    p = st.layer("traffic")
    if p:
        i0, i1, j0, j1 = _aerial_cells(p)
        neutral = (mix(look["near"], ink, 0.30), shade(look["near"], 0.72),
                   mix(look["mid"], ink, 0.45), mix(look["far"], ink, 0.25))
        span = (i1 - i0 + 2) * _A_PX
        for j in range(j0, j1 + 1):
            for lane, sgn in ((-2.2, 1.0), (2.2, -1.0)):
                for s in range(int(span // 17.0) + 2):
                    spd = _rr(16.0, 27.0, seed, j, lane > 0, s, 21) * sgn
                    x = (i0 * _A_PX + s * 17.0 + spd * t)
                    x = i0 * _A_PX + ((x - i0 * _A_PX) % span)
                    hero = (j % 7 == 0 and s % 11 == 0)
                    tail = (j % 7 == 0 and s % 11 == 5)
                    c = (look["accent"] if hero else
                         look["accent2"] if tail else
                         _pick(neutral, seed, j, s, 22))
                    _aerial_car(p, x, j * _A_PY + lane, 5.6, 2.6, c, ink,
                                sgn > 0)
        for i in range(i0, i1 + 1):
            for lane, sgn in ((-2.2, 1.0), (2.2, -1.0)):
                for s in range(int((j1 - j0 + 2) * _A_PY // 21.0) + 2):
                    spd = _rr(13.0, 21.0, seed, i, lane > 0, s, 23) * sgn
                    ln = (j1 - j0 + 2) * _A_PY
                    y = j0 * _A_PY + (((s * 21.0 + spd * t) % ln))
                    c = _pick(neutral, seed, i, s, 24)
                    _aerial_car(p, i * _A_PX + lane, y, 2.6, 5.6, c, ink,
                                sgn > 0, vertical=True)

    for lname, tier in (("lowrise", 0), ("midrise", 1), ("towers", 2)):
        p = st.layer(lname)
        if p is None:
            continue
        i0, i1, j0, j1 = _aerial_cells(p)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if _chance(0.13, seed, i, j, 1):        # a park, not a block
                    continue
                if tier_of(i, j) != tier:
                    continue
                _aerial_plot(p, look, seed, i, j, tier, fam, True)
        for i in range(i0, i1 + 1):          # every mass over every shadow,
            for j in range(j0, j1 + 1):      # or a neighbour's shadow lands
                if _chance(0.13, seed, i, j, 1):   # on top of this roof
                    continue
                if tier_of(i, j) != tier:
                    continue
                _aerial_plot(p, look, seed, i, j, tier, fam, False)

    p = st.layer("wisp")
    if p:
        _aerial_wisp(p, look, t, seed ^ 0x71)


def _aerial_plot(pen: _Pen, look: dict, seed: int, i: int, j: int, tier: int,
                 fam, drop: bool) -> None:
    """One city block: its cast shadow, then its mass and roof clutter.

    Both passes live in the same parallax band, which is the whole point of
    banding by height — a tower may slide a long way over the street below
    it, but it can never slide away from its own shadow.
    """
    bx0, by0, bx1, by1 = _aerial_block(i, j)
    lift = (1.0, 2.2, 3.8)[tier]
    grow = (1.0, 1.045, 1.10)[tier]     # nearer the camera, so bigger
    mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
    n = 1 + int(_r01(seed, i, j, 5) * 3)
    span = (bx1 - bx0) / n
    parts = []
    for k in range(n):
        ax0 = bx0 + k * span + (0.7 if k else 0.0)
        ax1 = bx0 + (k + 1) * span - (0.7 if k < n - 1 else 0.0)
        ry0 = by0 + _rr(0.0, 1.8, seed, i, j, k, 6)
        ry1 = by1 - _rr(0.0, 1.8, seed, i, j, k, 7)
        parts.append((k,
                      mx + (ax0 - mx) * grow, my + (ry0 - my) * grow,
                      mx + (ax1 - mx) * grow, my + (ry1 - my) * grow))

    if drop:
        # Asphalt is already dark, so a polite shadow reads as nothing at
        # all. These have to be firm to survive landing on the road.
        for k, ax0, ry0, ax1, ry1 in parts:
            off = (1.3 + _r01(seed, i, j, k, 8) * 1.5) * lift
            pen.rect(ax0 + off, ry0 + off * 1.15, ax1 + off, ry1 + off * 1.15,
                     col=alpha(look["shadow"], 0.36 + 0.05 * tier))
        return

    for k, ax0, ry0, ax1, ry1 in parts:
        c = _pick(fam, seed, i, j, k, 9)
        if tier:                                        # taller catches light
            c = tint(c, 0.06 * tier)
        pen.rect(ax0, ry0, ax1, ry1, col=c)
        pen.rect(ax0, ry0, ax1, ry0 + 0.7, col=shade(c, 0.88))
        pen.rect(ax0, ry1 - 0.7, ax1, ry1, col=shade(c, 0.88))
        pen.rect(ax0, ry0, ax0 + 0.7, ry1, col=shade(c, 0.88))
        pen.rect(ax1 - 0.7, ry0, ax1, ry1, col=shade(c, 0.88))

    bx0, by0 = mx + (bx0 - mx) * grow, my + (by0 - my) * grow
    bx1, by1 = mx + (bx1 - mx) * grow, my + (by1 - my) * grow
    base = mix(look["mid"], look["ground"], 0.35)       # then the roof
    for k in range(3):
        if not _chance(0.62, seed, i, j, k, 11):
            continue
        w = _rr(2.2, 4.6, seed, i, j, k, 12)
        h = _rr(2.0, 3.8, seed, i, j, k, 13)
        x = _rr(bx0 + 2, bx1 - w - 2, seed, i, j, k, 14)
        y = _rr(by0 + 2, by1 - h - 2, seed, i, j, k, 15)
        c = shade(base, 0.80 + 0.16 * _r01(seed, i, j, k, 16))
        pen.rect(x, y, x + w, y + h, col=c)
        pen.rect(x, y, x + w, y + h * 0.34, col=shade(c, 0.86))
    if tier == 2 and _chance(0.42, seed, i, j, 17):     # helipad, up top
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        r = min(bx1 - bx0, by1 - by0) * 0.30
        mark = mix(look["near"], look["sky"], 0.55)
        pen.circle(cx, cy, r, col=shade(base, 0.86), ink=mark, w=0.5)
        pen.rect(cx - r * 0.42, cy - r * 0.5,
                 cx - r * 0.18, cy + r * 0.5, col=mark)
        pen.rect(cx + r * 0.18, cy - r * 0.5,
                 cx + r * 0.42, cy + r * 0.5, col=mark)
        pen.rect(cx - r * 0.42, cy - r * 0.13,
                 cx + r * 0.42, cy + r * 0.13, col=mark)


def _aerial_wisp(pen: _Pen, look: dict, t: float, seed: int) -> None:
    """Cloud between the aircraft and the city, torn past at 1.5x.

    The only near plane a top-down plate has. Kept soft and sparse: it is a
    depth cue, not weather.
    """
    b = pen.bounds()
    w = max(1.0, b[2] - b[0])
    h = max(1.0, b[3] - b[1])
    hi = _cloud_cols(look, 0.24)[0]
    span = w * 2.2
    for k in range(4):
        if not _chance(0.62, seed, k, 31):
            continue
        rx = w * _rr(0.16, 0.30, seed, k, 32)
        ry = h * _rr(0.07, 0.14, seed, k, 33)
        drift = _rr(3.0, 7.0, seed, k, 34)
        cy = b[1] + h * _rr(-0.05, 1.05, seed, k, 35)
        cx = b[0] - w * 0.6 + ((w * _rr(0.0, 2.2, seed, k, 36)
                                + drift * float(t)) % span)
        a = _rr(0.13, 0.22, seed, k, 37)
        pen.ellipse(cx, cy, rx, ry, col=alpha(hi, a))
        pen.ellipse(cx - rx * 0.46, cy + ry * 0.28, rx * 0.66, ry * 0.78,
                    col=alpha(hi, a * 0.82))
        pen.ellipse(cx + rx * 0.52, cy - ry * 0.22, rx * 0.58, ry * 0.72,
                    col=alpha(hi, a * 0.74))


def _aerial_car(pen: _Pen, cx, cy, w, h, col, ink, forward, vertical=False):
    pen.rect(cx - w / 2 + 0.5, cy - h / 2 + 0.6, cx + w / 2 + 0.9,
             cy + h / 2 + 0.9, col=alpha(ink, 0.20))
    pen.rrect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 0.7, col=col)
    g = mix(col, ink, 0.45)
    if vertical:
        pen.rect(cx - w * 0.34, cy - h * 0.14, cx + w * 0.34, cy + h * 0.20,
                 col=g)
        f = cy - h / 2 + 0.4 if forward else cy + h / 2 - 0.4
        pen.rect(cx - w * 0.30, f - 0.22, cx + w * 0.30, f + 0.22,
                 col=mix(col, (255, 255, 255), 0.55))
    else:
        pen.rect(cx - w * 0.14, cy - h * 0.34, cx + w * 0.20, cy + h * 0.34,
                 col=g)
        f = cx + w / 2 - 0.4 if forward else cx - w / 2 + 0.4
        pen.rect(f - 0.22, cy - h * 0.30, f + 0.22, cy + h * 0.30,
                 col=mix(col, (255, 255, 255), 0.55))


# ----------------------------------------------------------- set: office -----

def _monitor(pen: _Pen, x, top, w, h, look, on) -> None:
    ink = look["ink"]
    case = mix(ink, look["ground"], 0.35)
    pen.rrect(x - w / 2, top, x + w / 2, top + h, 0.5, col=case)
    scr = mix(look["sky"], ink, 0.30) if on else shade(case, 0.7)
    pen.rect(x - w / 2 + 0.45, top + 0.45, x + w / 2 - 0.45, top + h - 0.45,
             col=scr)
    if on:
        for k in range(3):
            pen.rect(x - w / 2 + 1.1, top + 1.2 + k * 1.15,
                     x - w / 2 + 1.1 + (w - 3.0) * (0.8 - 0.2 * k),
                     top + 1.7 + k * 1.15, col=mix(scr, look["sky"], 0.6))
    pen.rect(x - 0.5, top + h, x + 0.5, top + h + 1.4, col=case)
    pen.rect(x - 2.0, top + h + 1.4, x + 2.0, top + h + 1.9, col=case)


def _desk(pen: _Pen, x0, x1, top, gy, look, seed, idx) -> None:
    ink = look["ink"]
    wood = mix(look["near"], look["ground"], 0.42)
    leg = shade(wood, 0.72)
    pen.rect(x0 - 0.5, top, x1 + 0.5, top + 1.1, col=wood)
    pen.rect(x0 - 0.5, top + 1.1, x1 + 0.5, top + 1.6, col=shade(wood, 0.78))
    pen.rect(x0 + 0.8, top + 1.6, x0 + 2.0, gy, col=leg)
    pen.rect(x1 - 2.0, top + 1.6, x1 - 0.8, gy, col=leg)
    pen.rect(x0 + 0.4, gy - 0.5, x0 + 2.4, gy, col=shade(leg, 0.78))
    pen.rect(x1 - 2.4, gy - 0.5, x1 - 0.4, gy, col=shade(leg, 0.78))
    pen.rect(x0 + 1.4, top + 2.4, x1 - 1.4, top + 3.0, col=shade(wood, 0.86))
    ped = _rr(0.0, 1.0, seed, idx, 1) < 0.6
    if ped:
        px0 = x1 - 8.0
        pen.rect(px0, top + 1.5, px0 + 6.6, gy, col=shade(wood, 0.88))
        for k in range(3):
            y = top + 2.4 + k * 3.0
            pen.rect(px0 + 0.5, y, px0 + 6.1, y + 2.4, col=shade(wood, 0.80))
            pen.rect(px0 + 2.2, y + 1.0, px0 + 4.4, y + 1.5,
                     col=mix(ink, wood, 0.5))


def _chair(pen: _Pen, x, gy, look, flip=False) -> None:
    """Side-on task chair: base, gas lift, seat pad, tilted back."""
    ink = look["ink"]
    frame = mix(ink, look["far"], 0.30)
    pad = mix(look["far"], ink, 0.42)
    s = -1.0 if flip else 1.0
    for dx in (-4.4, -2.2, 2.2, 4.4):
        pen.line([(x, gy - 2.6), (x + dx, gy - 0.55)], frame, 0.42)
        pen.circle(x + dx, gy - 0.4, 0.62, col=shade(frame, 0.78))
    pen.rect(x - 0.42, gy - 8.6, x + 0.42, gy - 2.4, col=frame)
    pen.rrect(x - 4.2 * s, gy - 9.9, x + 4.4 * s, gy - 8.2, 0.7, col=pad)
    pen.rrect(x - 4.2 * s, gy - 8.9, x + 4.4 * s, gy - 8.2, 0.5,
              col=shade(pad, 0.80))
    pen.line([(x - 3.6 * s, gy - 9.4), (x - 4.4 * s, gy - 15.2)], frame, 0.55)
    pen.poly([(x - 5.9 * s, gy - 16.4), (x - 3.0 * s, gy - 16.0),
              (x - 2.6 * s, gy - 10.4), (x - 5.3 * s, gy - 10.8)],
             col=pad)
    pen.poly([(x - 5.9 * s, gy - 16.4), (x - 3.0 * s, gy - 16.0),
              (x - 3.1 * s, gy - 15.2), (x - 5.8 * s, gy - 15.6)],
             col=shade(pad, 0.82))
    pen.poly([(x + 0.4 * s, gy - 9.6), (x + 4.2 * s, gy - 9.3),
              (x + 4.4 * s, gy - 8.4), (x + 0.4 * s, gy - 8.6)],
             col=shade(pad, 0.88))


def _set_office(st: _Stage, look: dict, t: float, seed: int) -> None:
    ink = look["ink"]
    gy = GROUND_Y
    wall = mix(look["near"], look["far"], 0.32)

    p = st.layer("wall")
    if p:
        b = p.bounds()
        x0, x1 = b[0] - 12, b[2] + 12
        p.fill(wall)
        p.rect(x0, b[1] - 4, x1, 6.4, col=tint(wall, 0.24))
        p.rect(x0, 6.4, x1, 6.9, col=shade(wall, 0.86))
        for i in range(int(x0 // 30) - 1, int(x1 // 30) + 2):
            lx = i * 30.0 + 8.0
            p.rrect(lx, 3.0, lx + 15.0, 4.6, 0.5,
                    col=mix(look["sky"], look["near"], 0.55))
            p.rect(lx, 4.6, lx + 15.0, 5.0, col=shade(wall, 0.80))
        p.rect(x0, 27.0, x1, 27.6, col=shade(wall, 0.90))

    p = st.layer("openings")
    if p:
        b = p.bounds()
        frame = shade(look["near"], 0.70)
        for i in range(int(b[0] // 62) - 1, int(b[2] // 62) + 2):
            wx0 = i * 62.0 + 6.0
            wx1 = wx0 + 30.0
            p.rect(wx0 - 0.9, 11.1, wx1 + 0.9, 30.9, col=frame)
            p.rect(wx0, 12.0, wx1, 30.0, col=look["sky"])
            sky_far = depth_tint(look["mid"], 0.80, look["sky"])
            for k in range(7):
                bx = wx0 + 1.0 + k * 4.2
                bh = _rr(3.0, 11.0, seed, i, k, 1)
                p.rect(bx, 30.0 - bh, bx + _rr(2.4, 3.8, seed, i, k, 2),
                       30.0, col=sky_far)
            p.rect(wx0, 29.0, wx1, 30.0, col=depth_tint(look["ground"], 0.86,
                                                        look["sky"]))
            p.rect((wx0 + wx1) / 2 - 0.45, 12.0, (wx0 + wx1) / 2 + 0.45, 30.0,
                   col=frame)
            p.rect(wx0, 20.6, wx1, 21.5, col=frame)
            for k in range(5):                          # rolled-up blind
                p.rect(wx0 + 0.2, 12.2 + k * 0.62, wx1 - 0.2, 12.6 + k * 0.62,
                       col=shade(look["near"], 0.94))

            dx0 = wx0 + 40.0                            # door
            p.rect(dx0 - 1.0, 13.0, dx0 + 12.0, gy, col=frame)
            p.rect(dx0, 14.0, dx0 + 11.0, gy, col=shade(look["near"], 0.84))
            p.rect(dx0 + 1.4, 15.6, dx0 + 9.6, 22.0,
                   col=mix(_glass(look), look["near"], 0.4))
            p.circle(dx0 + 9.6, 32.0, 0.55, col=mix(ink, look["ground"], 0.3))

            wb0 = wx0 + 56.0                            # whiteboard
            p.rect(wb0, 13.4, wb0 + 24.0, 27.4,
                   col=tint(look["near"], 0.55), ink=frame, w=0.5)
            p.rect(wb0 + 2.0, 16.0, wb0 + 11.0, 16.8, col=mix(ink, wall, 0.35))
            p.rect(wb0 + 2.0, 18.4, wb0 + 16.5, 19.2, col=mix(ink, wall, 0.35))
            p.line([(wb0 + 14.0, 22.4), (wb0 + 18.0, 25.4)],
                   look["accent2"], 0.55)
            p.line([(wb0 + 18.0, 25.4), (wb0 + 21.5, 21.0)],
                   look["accent2"], 0.55)
            p.rect(wb0 + 2.0, 21.6, wb0 + 8.0, 22.3, col=mix(ink, wall, 0.35))

            cx = wx0 + 48.0                             # clock
            p.circle(cx, 15.0, 2.6, col=tint(look["near"], 0.5),
                     ink=mix(ink, wall, 0.25), w=0.35)
            p.line([(cx, 15.0), (cx, 13.2)], ink, 0.28)
            p.line([(cx, 15.0), (cx + 1.4, 15.6)], ink, 0.28)

    p = st.layer("furniture")
    if p:
        b = p.bounds()
        for i in range(int(b[0] // 58) - 1, int(b[2] // 58) + 2):
            ox = i * 58.0
            _desk(p, ox + 6.0, ox + 28.0, 33.0, gy, look, seed, i)
            _monitor(p, ox + 13.0, 25.2, 9.0, 6.4, look, True)
            p.rect(ox + 19.0, 32.0, ox + 25.6, 33.0,
                   col=mix(ink, look["ground"], 0.42))
            p.rrect(ox + 25.0, 30.8, ox + 27.4, 33.0, 0.5, col=look["accent"])
            p.rect(ox + 27.4, 31.4, ox + 28.2, 32.4, col=look["accent"])
            _chair(p, ox + 34.0, gy, look)

            fx = ox + 44.0                              # filing cabinet
            cab = mix(look["mid"], look["ground"], 0.5)
            p.rect(fx, 29.0, fx + 9.0, gy, col=cab)
            for k in range(3):
                y = 30.2 + k * 4.4
                p.rect(fx + 0.7, y, fx + 8.3, y + 3.6, col=shade(cab, 0.9))
                p.rect(fx + 3.6, y + 1.5, fx + 5.4, y + 2.1,
                       col=mix(ink, cab, 0.45))
            p.rect(fx - 0.4, 28.2, fx + 9.4, 29.0, col=shade(cab, 0.8))

            wcx = ox + 52.0                             # water cooler
            water = _hued(196.0, 0.34, min(86.0, lightness(wall) + 12.0))
            p.rect(wcx, 34.2, wcx + 5.0, gy,
                   col=shade(look["near"], 0.86), ink=mix(ink, wall, 0.45),
                   w=0.26)
            p.rrect(wcx + 0.7, 26.6, wcx + 4.3, 34.2, 1.0, col=water,
                    ink=mix(ink, wall, 0.45), w=0.26)
            p.rect(wcx + 0.7, 26.6, wcx + 4.3, 28.4, col=tint(water, 0.34))
            p.rect(wcx + 0.9, 36.2, wcx + 4.1, 37.4, col=mix(ink, wall, 0.4))

            px = ox + 2.0                               # plant
            leaf = _foliage(look)
            dleaf = _foliage(look, dark=True)
            for a, ln in ((-72, 6.4), (-40, 8.2), (-12, 9.4),
                          (16, 9.0), (46, 7.8), (74, 6.0)):
                ra = math.radians(a)
                tipx = px + ln * math.sin(ra)
                tipy = 37.4 - ln * math.cos(ra)
                mx = px + ln * 0.55 * math.sin(ra)
                my = 37.4 - ln * 0.62 * math.cos(ra)
                wd = 2.1
                p.poly([(px, 37.8), (mx - wd, my - wd * 0.30),
                        (tipx, tipy), (mx + wd, my + wd * 0.30)],
                       col=leaf if abs(a) < 50 else dleaf)
            p.poly([(px - 2.6, gy), (px + 2.6, gy), (px + 2.0, 37.0),
                    (px - 2.0, 37.0)],
                   col=_hued(20.0, 0.52, 54.0))
            p.rect(px - 2.8, 36.4, px + 2.8, 37.4,
                   col=_hued(20.0, 0.52, 44.0))

    p = st.layer("floor")
    if p:
        b = p.bounds()
        x0, x1, ybot = b[0] - 10, b[2] + 10, b[3] + 4
        floor = look["ground"]
        p.rect(x0, gy, x1, ybot, col=floor)
        p.rect(x0, gy - 1.2, x1, gy, col=shade(look["near"], 0.72))
        p.rect(x0, gy - 1.2, x1, gy - 0.85, col=shade(look["near"], 0.60))
        for i in range(int(x0 // 13) - 1, int(x1 // 13) + 2):
            p.line([(i * 13.0, gy), (i * 13.0 - 7.0, ybot)],
                   shade(floor, 0.94), 0.22)
        p.rect(x0, gy + (ybot - gy) * 0.55, x1, gy + (ybot - gy) * 0.55 + 0.4,
               col=shade(floor, 0.94))
    del t


# -------------------------------------------------------------- set: sky -----

def _set_sky(st: _Stage, look: dict, t: float, seed: int) -> None:
    sky = look["sky"]
    p = st.layer("sky")
    if p:
        top, bot = sky_gradient(sky, spread=9.0)
        p.vgrad(top, bot)
    p = st.layer("sun")
    if p:
        b = p.bounds()
        sx = b[0] + (b[2] - b[0]) * 0.20
        sy = b[1] + (b[3] - b[1]) * 0.17
        disc, halo = _sun(look)
        p.circle(sx, sy, 12.4, col=mix(sky, halo, 0.30))
        p.circle(sx, sy, 8.2, col=mix(sky, halo, 0.66))
        p.circle(sx, sy, 4.8, col=disc)
    p = st.layer("high")
    if p:
        b = p.bounds()
        c = alpha(_cloud_cols(look, 0.30)[0], 0.42)
        for i in range(int(b[0] // 24) - 1, int(b[2] // 24) + 2):
            for k in range(3):
                x = i * 24.0 + _rr(0, 18, seed, i, k, 1)
                y = _rr(b[1] + 2, b[1] + (b[3] - b[1]) * 0.34, seed, i, k, 2)
                p.ellipse(x, y, _rr(6.0, 13.0, seed, i, k, 3),
                          _rr(0.5, 1.1, seed, i, k, 4), col=c)
    p = st.layer("horizon")
    if p:
        b = p.bounds()
        hy = b[1] + (b[3] - b[1]) * 0.90
        land = depth_tint(mix(look["ground"], look["far"], 0.45), 0.74, sky)
        city = depth_tint(look["mid"], 0.80, sky)
        far_city = depth_tint(look["mid"], 0.90, sky)
        p.rect(b[0] - 8, hy - 9.0, b[2] + 8, hy + 1.0,
               col=depth_tint(look["far"], 0.93, sky))
        for i in range(int(b[0] // 7) - 1, int(b[2] // 7) + 2):
            h = _rr(1.0, 6.5, seed, i, 5)
            p.rect(i * 7.0, hy - 1.6 - h,
                   i * 7.0 + _rr(3.4, 6.6, seed, i, 6), hy + 1.0, col=far_city)
        for i in range(int(b[0] // 11) - 1, int(b[2] // 11) + 2):
            h = _rr(1.0, 4.4, seed, i, 7)
            p.rect(i * 11.0 + _rr(0, 5, seed, i, 8), hy - h,
                   i * 11.0 + _rr(6.0, 10.0, seed, i, 9), hy + 1.4, col=city)
        p.rect(b[0] - 8, hy, b[2] + 8, b[3] + 6, col=land)
        p.rect(b[0] - 8, hy, b[2] + 8, hy + 0.55, col=tint(land, 0.30))
    p = st.layer("far_clouds")
    if p:
        _cloud_band(p, look, z=0.74, period=44.0, yr=(6.0, 30.0),
                    seed=seed ^ 0x81, w=(20.0, 34.0), h=(5.0, 9.0))
    p = st.layer("clouds")
    if p:
        _cloud_band(p, look, z=0.34, period=61.0, yr=(10.0, 40.0),
                    seed=seed ^ 0x82, w=(30.0, 52.0), h=(9.0, 16.0))
    p = st.layer("near_clouds")
    if p:
        b = p.bounds()
        body, under = _cloud_cols(look, 0.0)
        for i in range(int(b[0] // 78) - 1, int(b[2] // 78) + 2):
            if not _chance(0.7, seed, i, 9):
                continue
            cx = i * 78.0 + _rr(-20, 20, seed, i, 10)
            cy = b[3] + _rr(-2.0, 7.0, seed, i, 11)
            _cloud_shape(p, cx, cy, _rr(52, 84, seed, i, 12),
                         _rr(16, 26, seed, i, 13), body, under, seed, i)
    del t


# ----------------------------------------------------------- set: suburb ----
#
# Where the film ends: a quiet residential street. Same seven-layer stack as
# `street` so the two cut together, but the frontage is houses with pitched
# roofs, driveways, hedges and — the shot the board actually asks for — a
# front door.


def _house(pen: _Pen, look: dict, x0: float, x1: float, gy: float,
           z: float, seed: int, idx: int, *, hero: bool = False) -> None:
    """One detached house: walls, pitched roof, chimney, door, windows."""
    sky = look["sky"]
    walls = (mix(look["near"], (255, 255, 255), 0.30),
             mix(look["near"], look["accent"], 0.16),
             shade(look["near"], 0.90),
             mix(look["near"], look["mid"], 0.35))
    roofs = (mix(look["ink"], look["accent"], 0.30),
             mix(look["mid"], look["ink"], 0.45),
             mix(look["ink"], look["far"], 0.28))
    w = x1 - x0
    body = depth_tint(_pick(walls, seed, idx, 1), z, sky)
    roof = depth_tint(_pick(roofs, seed, idx, 2), z, sky)
    glass = depth_tint(_glass(look), z * 0.92, sky)
    onc = depth_tint(_lit_window(look), z * 0.5, sky)
    trim = shade(body, 0.86)

    eaves = gy - _rr(15.0, 18.5, seed, idx, 3)
    ridge = eaves - w * _rr(0.30, 0.40, seed, idx, 4)

    pen.rect(x0, eaves, x1, gy + 2.0, col=body)
    pen.rect(x1 - w * 0.09, eaves, x1, gy + 2.0, col=shade(body, 0.93))

    # chimney first, so the roof laps over its base
    cx = x0 + w * _rr(0.16, 0.30, seed, idx, 5)
    ctop = ridge - _rr(3.0, 5.2, seed, idx, 6)
    pen.rect(cx, ctop, cx + w * 0.10, eaves, col=shade(body, 0.88))
    pen.rect(cx - w * 0.015, ctop - 0.7, cx + w * 0.115, ctop,
             col=shade(body, 0.74))

    pen.poly([(x0 - 1.3, eaves + 0.6), (x0 + w * 0.5, ridge),
              (x1 + 1.3, eaves + 0.6), (x1 + 1.3, eaves + 1.5),
              (x0 - 1.3, eaves + 1.5)], col=roof)
    pen.poly([(x0 + w * 0.5, ridge), (x1 + 1.3, eaves + 0.6),
              (x1 + 1.3, eaves + 1.5), (x0 + w * 0.5, ridge + 0.9)],
             col=shade(roof, 0.86))
    pen.rect(x0 - 1.3, eaves + 1.5, x1 + 1.3, eaves + 2.1, col=trim)

    lit = _lit_rate(look) + (0.20 if hero else 0.0)
    _win_grid(pen, x0 + w * 0.12, eaves + 3.4, x0 + w * 0.88, eaves + 8.2,
              2, 1, glass, onc, seed, idx, lit=lit, gap=w * 0.10)

    # ground floor: bay window on one side, front door on the other
    door_left = _chance(0.5, seed, idx, 7) and not hero
    dx = x0 + (w * 0.14 if door_left else w * 0.66)
    dw = w * 0.20
    dtop = gy - 8.2
    porch = depth_tint(look["accent"] if hero else
                       _pick((look["accent"], look["accent2"],
                              mix(look["accent"], look["ink"], 0.40)),
                             seed, idx, 8), z * 0.7, sky)
    pen.rect(dx - 0.5, dtop - 1.0, dx + dw + 0.5, gy, col=trim)
    pen.rect(dx, dtop, dx + dw, gy, col=porch, ink=_edge(look, porch), w=0.24)
    pen.rect(dx + dw * 0.16, dtop + 0.9, dx + dw * 0.84, dtop + 3.0,
             col=depth_tint(mix(glass, onc, 0.5), z * 0.6, sky))
    pen.circle(dx + dw * 0.80, gy - 4.0, 0.30, col=shade(porch, 0.55))
    pen.rect(dx - 1.1, dtop - 1.6, dx + dw + 1.1, dtop - 1.0,
             col=shade(trim, 0.88))
    if hero:
        pen.circle(dx + dw + 1.9, dtop - 0.4, 0.75,
                   col=depth_tint(onc, z * 0.4, sky))
        pen.rect(dx + dw + 1.5, dtop - 1.2, dx + dw + 2.3, dtop - 0.9,
                 col=shade(trim, 0.7))
        pen.poly([(dx - 1.0, gy), (dx + dw + 1.0, gy),
                  (dx + dw + 3.0, gy + 2.0), (dx - 3.0, gy + 2.0)],
                 col=shade(body, 0.80))

    bx = x0 + (w * 0.44 if door_left else w * 0.10)
    bw = w * 0.36
    pen.rect(bx - 0.6, gy - 9.0, bx + bw + 0.6, gy - 2.2, col=trim)
    pen.rect(bx, gy - 8.4, bx + bw, gy - 2.8, col=glass)
    pen.rect(bx + bw * 0.48, gy - 8.4, bx + bw * 0.52, gy - 2.8, col=trim)
    pen.poly([(bx + 0.4, gy - 3.2), (bx + bw * 0.42, gy - 8.0),
              (bx + bw * 0.60, gy - 8.0), (bx + bw * 0.18, gy - 3.2)],
             col=tint(glass, 0.34))


def _treeline(pen: _Pen, look: dict, gy: float, z: float, seed: int) -> None:
    """Distant roofs and trees, washed most of the way into the sky."""
    sky = look["sky"]
    leaf = depth_tint(_foliage(look), z, sky)
    dark = depth_tint(_foliage(look, dark=True), z, sky)
    roof = depth_tint(mix(look["mid"], look["ink"], 0.35), z, sky)
    wall = depth_tint(mix(look["mid"], look["near"], 0.45), z, sky)
    b = pen.bounds()
    P = 19.0
    for i in range(int(math.floor(b[0] / P)) - 2, int(math.ceil(b[2] / P)) + 2):
        x = i * P + _rr(0.0, 8.0, seed, i, 1)
        if _chance(0.55, seed, i, 2):
            h = _rr(9.0, 15.0, seed, i, 3)
            wd = _rr(11.0, 17.0, seed, i, 4)
            pen.rect(x, gy - h, x + wd, gy + 2.0, col=wall)
            pen.poly([(x - 1.2, gy - h), (x + wd * 0.5, gy - h - wd * 0.30),
                      (x + wd + 1.2, gy - h)], col=roof)
        else:
            th = _rr(13.0, 21.0, seed, i, 5)
            _blob(pen, x + 5.0, gy - th * 0.62, th * 0.86, th * 0.72,
                  leaf, seed, i)
            pen.rect(x + 4.4, gy - th * 0.34, x + 5.6, gy + 2.0, col=dark)
    pen.rect(b[0] - 8.0, gy, b[2] + 8.0, gy + 3.0,
             col=depth_tint(mix(look["ground"], look["mid"], 0.4), z * 0.7,
                            sky))


def _gardens(pen: _Pen, look: dict, gy: float, seed: int) -> None:
    """Front walls, hedges, gates and driveways between houses and kerb."""
    ink = look["ink"]
    leaf = _foliage(look)
    dark = _foliage(look, dark=True)
    brick = mix(look["near"], look["mid"], 0.5)
    drive = mix(look["ground"], look["near"], 0.5)
    b = pen.bounds()
    P = 40.0
    for i in range(int(math.floor(b[0] / P)) - 2, int(math.ceil(b[2] / P)) + 2):
        x0 = i * P + _rr(0.0, 5.0, seed, i, 1)
        if _chance(0.55, seed, i, 2):                       # driveway
            dw = _rr(13.0, 19.0, seed, i, 3)
            pen.rect(x0, gy - 0.2, x0 + dw, gy + 2.3, col=drive)
            for k in range(4):
                sx = x0 + dw * (k + 1) / 5.0
                pen.rect(sx, gy - 0.2, sx + 0.26, gy + 2.3,
                         col=shade(drive, 0.92))
        if _chance(0.62, seed, i, 4):                       # hedge
            hx = x0 + _rr(16.0, 24.0, seed, i, 5)
            hw = _rr(9.0, 15.0, seed, i, 6)
            hh = _rr(3.4, 5.2, seed, i, 7)
            pen.rect(hx, gy - hh, hx + hw, gy, col=dark)
            for k in range(max(2, int(hw / 2.4))):
                cx = hx + 1.1 + k * 2.2
                pen.circle(cx, gy - hh, 1.5, col=leaf)
            pen.rect(hx, gy - hh * 0.34, hx + hw, gy, col=dark)
        else:                                               # low front wall
            wx = x0 + _rr(15.0, 23.0, seed, i, 8)
            ww = _rr(8.0, 14.0, seed, i, 9)
            pen.rect(wx, gy - 2.6, wx + ww, gy, col=brick)
            pen.rect(wx - 0.4, gy - 3.1, wx + ww + 0.4, gy - 2.6,
                     col=shade(brick, 0.84))
            for k in range(2):
                px = wx - 0.6 + k * (ww + 1.2 - 1.6)
                pen.rect(px, gy - 4.4, px + 1.6, gy, col=shade(brick, 0.92))
                pen.rect(px - 0.3, gy - 4.9, px + 1.9, gy - 4.4,
                         col=shade(brick, 0.78))
        if _chance(0.30, seed, i, 10):                      # wheelie bin
            wx = x0 + _rr(28.0, 36.0, seed, i, 11)
            bc = _pick((mix(look["far"], ink, 0.30),
                        mix(_foliage(look, dark=True), ink, 0.25)),
                       seed, i, 12)
            pen.poly([(wx, gy), (wx + 3.2, gy), (wx + 2.9, gy - 5.6),
                      (wx + 0.3, gy - 5.6)], col=bc)
            pen.rect(wx - 0.2, gy - 6.4, wx + 3.4, gy - 5.5,
                     col=shade(bc, 0.82))
    del ink


def _suburb_fg(pen: _Pen, look: dict, seed: int) -> None:
    """A low kerbside hedge hugging the bottom edge, this side of the road.

    Deliberately shallow. A foreground band tall enough to cover the road
    would hide the thing the shot is about — the vehicle driving down it.
    """
    leaf = shade(_foliage(look), 0.84)
    dark = shade(_foliage(look, dark=True), 0.80)
    b = pen.bounds()
    x0, x1, ybot = b[0] - 12.0, b[2] + 12.0, b[3]
    top = ybot - 2.3
    pen.rect(x0, top + 0.6, x1, ybot + 4.0, col=dark)
    for i in range(int(x0 // 1.9) - 1, int(x1 // 1.9) + 2):
        cx = i * 1.9
        # every fifth clump grows a little, so the silhouette scallops
        tall = 2.2 if (i % 5 == 0) else 0.0
        cy = top - tall + _rr(-0.35, 0.45, seed, i, 1)
        pen.circle(cx, cy, 1.62, col=dark)
    for i in range(int(x0 // 1.9) - 1, int(x1 // 1.9) + 2):
        cx = i * 1.9
        tall = 2.2 if (i % 5 == 0) else 0.0
        cy = top - tall + _rr(-0.35, 0.45, seed, i, 1)
        if _chance(0.5, seed, i, 2):
            pen.circle(cx, cy - 0.34, 1.16, col=leaf)
    pen.rect(x0, top + 1.5, x1, ybot + 4.0, col=dark)


def _set_suburb(st: _Stage, look: dict, t: float, seed: int) -> None:
    gy = GROUND_Y
    p = st.layer("sky")
    if p:
        top, bot = sky_gradient(look["sky"])
        p.vgrad(top, bot, 0.0, gy + 2.0)
    p = st.layer("clouds")
    if p:
        _cloud_band(p, look, z=0.80, period=64.0, yr=(4.0, 16.0),
                    seed=seed ^ 0x13)
    p = st.layer("treeline")
    if p:
        _treeline(p, look, gy - 6.0, 0.66, seed ^ 0x23)
    p = st.layer("houses")
    if p:
        b = p.bounds()
        P = 40.0
        for i in range(int(math.floor(b[0] / P)) - 2,
                       int(math.ceil(b[2] / P)) + 2):
            x0 = i * P + _rr(1.0, 5.0, seed ^ 0x33, i, 0)
            x1 = x0 + _rr(26.0, 33.0, seed ^ 0x33, i, 1)
            _house(p, look, x0, x1, gy, 0.20, seed ^ 0x33, i,
                   hero=(i % 3 == 0))
    p = st.layer("gardens")
    if p:
        _gardens(p, look, gy, seed ^ 0x43)
    p = st.layer("road")
    if p:
        _road(p, look, gy, seed ^ 0x53, residential=True)
    p = st.layer("foreground")
    if p:
        _suburb_fg(p, look, seed ^ 0x63)
    del t


# ------------------------------------------------------------- set: peak ----
#
# One mountain, a lot of weather, and room for exactly one figure on top.
#
# This is the set the style was measured against, and it is built to a
# different brief from the city sets above. Depth is carried entirely by how
# far each ridge has faded into the sky, the whole world sits at low
# saturation so that the only colourful thing in frame is the character on
# the summit, and the camera is expected to lock off and hold.
#
# It is also the one place the flat-fill rule is relaxed, and deliberately
# so: a flat cone reads as a road sign at any colour you paint it. The rock
# is scumbled instead — banded shading plus seeded marks — but only ever out
# of the three tones `_rock` derives from the palette, and only ever placed
# through the positional hash, so the mountain is still deterministic to the
# byte and still cannot invent a colour the palette does not own.

#: Where the flanks would reach full width. Below the bottom of the frame on
#: purpose, so the base is always cut off by mist rather than by the picture
#: edge — a mountain whose feet you can see is a triangle. The apex itself is
#: `PEAK_APEX`, up with the scene constants, because it is also the set's
#: ground line.
PEAK_BASE_Y = 57.5
#: Half-width at `PEAK_BASE_Y`.
PEAK_HALF = 28.0
#: Knots in each flank's seeded profile. Few enough that a wobble reads as a
#: shoulder rather than as noise, many enough that the two sides are visibly
#: not mirror images of each other.
_PEAK_KNOTS = 9


def _rock(look: dict) -> tuple[RGB, RGB, RGB]:
    """Body, shadow and lit rim for the summit, in that order.

    Earth is brown the way leaves are green — a fact about the world rather
    than a choice about the film — so the hue is built here and only nudged
    toward the palette's own ground, exactly as `_foliage` does. It has to
    be: half the palettes name a neutral grey ground, and rotating the hue
    of a neutral gets you a neutral.

    Everything else about it comes from the palette. The body lands a fixed
    distance *below* the sky in L*, so a pale sky gives dark rock and a
    night sky gives a silhouette without either needing a special case, and
    the saturation is kept low because at the size this thing occupies any
    real colour in it would out-shout the figure standing on top — which is
    the one thing this composition cannot afford.
    """
    sky = look["sky"]
    h = 34.0 + max(-10.0, min(10.0, 0.20 * (
        (_hue(look["ground"]) - 34.0 + 180.0) % 360.0 - 180.0)))
    tgt = max(12.0, min(46.0, lightness(sky) - 50.0))
    body = _at_lightness(mix(_hued(h, 0.44, tgt), look["far"], 0.14), tgt)
    # Down toward black rather than toward the palette's blue `shadow`: a
    # mountain's own shade is the same earth with less light on it, and
    # mixing a cool neutral in is what turns rock into slate.
    dark = mix(_at_lightness(body, max(5.0, tgt - 16.0)), look["shadow"], 0.12)
    rim = _at_lightness(mix(body, sky, 0.26), min(94.0, tgt + 15.0))
    return (body, dark, rim)


def _air(look: dict, lift: float = 0.0) -> RGB:
    """The colour of air you can see: cloud, haze, valley mist, all of it.

    One colour at several lightnesses beats four nearly-identical greys —
    the reference's weather reads as one atmosphere, not as a stack of
    unrelated overlays, and that only holds if they share a hue.
    """
    base = desaturate(mix(look["sky"], look["near"], 0.24), 0.62)
    return _at_lightness(base,
                         max(4.0, min(98.0, lightness(look["sky"]) + lift)))


def _mist_rings(a: float) -> tuple[float, ...]:
    """Radii of the nested rings one mist lobe is stacked from, outermost
    first.

    The count scales with the density asked for, because the visible defect
    changes with it: at low alpha five steps is already enough to stop a
    lobe showing its own outline, while a dense cloud drawn from five rings
    shows the rings themselves as contours. Softness is bought in rings.
    """
    n = max(5, min(12, 5 + int(a * 20.0)))
    return tuple(1.0 - 0.75 * k / (n - 1) for k in range(n))


def _mist_bank(pen: _Pen, col: RGB, *, cx, cy, rx, ry, a, seed, idx,
               lobes: int = 7, t: float = 0.0, churn: float = 0.0) -> None:
    """One soft mass, stacked out of low-alpha ellipses.

    `_blob` is the cartoon cloud the city sets are built from and it has a
    hard edge on purpose; the weather here has no edge at all. Overlapping
    alpha is the softest thing PIL will draw without a blur, and it stays
    reproducible because every lobe is placed from the hash rather than from
    a generator.

    `a` is what the *centre of a lobe* ends up at, not what each ellipse is
    drawn at — the per-ring value is solved for, so changing the ring count
    changes the softness and not the density.

    `churn` is how far, in scene units, each lobe wanders around its own
    place as `t` runs. Sliding a bank of mist sideways barely changes a
    frame, because its long edges are horizontal and translating a
    horizontal edge along itself is very nearly a no-op; the wander is what
    makes the mass *billow* rather than merely pass by, and it is what keeps
    a locked-off shot of this set from measuring as a frozen frame. Every
    lobe gets its own rate and phase out of the hash and the whole thing
    stays a pure function of `t`, so scrubbing to a frame gives that frame.
    """
    rings = _mist_rings(a)
    n = len(rings)
    tau = math.tau
    for k in range(lobes):
        s = _rr(0.46, 1.02, seed, idx, k, 3)
        ex = rx * s
        ey = ry * s * _rr(0.62, 1.16, seed, idx, k, 4)
        ox = cx + _rr(-0.62, 0.62, seed, idx, k, 1) * rx
        oy = cy + _rr(-0.55, 0.55, seed, idx, k, 2) * ry
        if churn:
            fx = _rr(0.15, 0.34, seed, idx, k, 6)
            fy = _rr(0.21, 0.46, seed, idx, k, 7)
            px_ = _rr(0.0, 6.283, seed, idx, k, 8)
            py_ = _rr(0.0, 6.283, seed, idx, k, 9)
            ox += churn * 1.7 * math.sin(tau * fx * t + px_)
            oy += churn * math.sin(tau * fy * t + py_)
            # breathing as well as wandering: a mass that only slides keeps
            # its silhouette, and a kept silhouette is what reads as a cel
            ey *= 1.0 + 0.30 * math.sin(tau * fy * t + px_)
        want = max(0.0, min(0.98, a * _rr(0.55, 1.0, seed, idx, k, 5)))
        la = 1.0 - (1.0 - want) ** (1.0 / n)
        for ring in rings:
            pen.ellipse(ox, oy, ex * ring, ey * ring, col=alpha(col, la))


def _peak_half(f: float, seed: int, side: int) -> float:
    """Half-width of the cone `f` of the way from apex to base.

    A mountain is not a triangle: it steepens toward the top, flares toward
    the bottom, and each flank carries its own shoulder. The profile is
    recomputed from the hash instead of being stored, so anything painting
    on the rock can ask where its own edge is without the silhouette having
    to be passed around.
    """
    f = max(0.0, min(1.0, f))
    k = f * (_PEAK_KNOTS - 1)
    i = min(_PEAK_KNOTS - 2, int(k))
    g = (1.0 - math.cos((k - i) * math.pi)) / 2.0
    a = _rr(-0.075, 0.08, seed, side, i)
    b = _rr(-0.075, 0.08, seed, side, i + 1)
    # The wobble grows toward the base rather than peaking mid-flank: the
    # reference's upper cone is almost a clean triangle and all its
    # roughness is down where the mist is about to eat it anyway.
    wob = (a + (b - a) * g) * f ** 1.1
    return max(0.0, PEAK_HALF * (f ** 0.90 + wob))


def _peak_pt(f: float, u: float, seed: int) -> Pt:
    """Scene point at surface coordinates `f` down the flank, `u` across it.

    ``u`` runs -1 at the left silhouette through 0 at the crest to +1 at the
    right. Marks are placed in these coordinates so that they stay stuck to
    the rock whatever the camera does, and so clipping a brush stroke to the
    silhouette is one comparison rather than a mask.
    """
    side = 0 if u < 0.0 else 1
    return (PEAK_APEX[0] + u * _peak_half(f, seed, side),
            PEAK_APEX[1] + f * (PEAK_BASE_Y - PEAK_APEX[1]))


def _peak_poly(seed: int, steps: int = 34) -> list[Pt]:
    """The summit outline, apex first, down the right flank and back up."""
    pts = [PEAK_APEX]
    pts += [_peak_pt(i / steps, 1.0, seed) for i in range(1, steps + 1)]
    pts += [_peak_pt(i / steps, -1.0, seed) for i in range(steps, 0, -1)]
    return pts


def _peak_crest(f: float, seed: int) -> float:
    """Where the lit face gives way to the shadowed one, across the cone.

    Not a straight line down the middle: the reference's crest wanders, and
    a straight one turns the mountain back into two flat triangles.
    """
    return (0.06 + 0.30 * f
            + 0.16 * math.sin(f * 4.1 + _r01(seed, 61) * 6.283))


def _peak_clamp(p: Pt, seed: int, inset: float = 0.12) -> Pt:
    """Pull a point back inside the silhouette.

    Cheaper and more exact than working out in advance how large a mark is
    allowed to be, and it fails in the right direction: a stroke that would
    have run off the mountain gets flattened along the edge instead, which
    is what a brush loaded with paint does anyway.
    """
    y = max(PEAK_APEX[1] + 0.05, min(PEAK_BASE_Y, p[1]))
    f = (y - PEAK_APEX[1]) / (PEAK_BASE_Y - PEAK_APEX[1])
    lo = PEAK_APEX[0] - max(0.0, _peak_half(f, seed, 0) - inset)
    hi = PEAK_APEX[0] + max(0.0, _peak_half(f, seed, 1) - inset)
    return (max(lo, min(hi, p[0])), y)


def _peak_mark(pen: _Pen, col: RGB, *, f: float, u: float, length: float,
               width: float, a: float, seed: int, idx: int) -> None:
    """One brush mark on the rock, lying along the fall line.

    Discs are what a stipple looks like when you can still see it, and a
    mountain covered in them reads as gravel. These are elongated down the
    flank, their outline is jittered so no two are the same shape, and every
    vertex is clamped to the silhouette so the paint stays on the rock.
    """
    cx, cy = _peak_pt(f, u, seed)
    ax, ay = u * 0.68, 1.0
    n = math.hypot(ax, ay)
    ax, ay = ax / n, ay / n
    pts = []
    for k in range(6):
        th = math.pi * k / 3.0
        rl = length * 0.5 * _rr(0.58, 1.32, seed, idx, k, 1) * math.cos(th)
        rw = width * 0.5 * _rr(0.50, 1.36, seed, idx, k, 2) * math.sin(th)
        pts.append(_peak_clamp((cx + ax * rl - ay * rw,
                                cy + ay * rl + ax * rw), seed))
    pen.poly(pts, col=alpha(col, a))


#: The brushwork, as ``(count, f-range, length, width, alpha, face)``. `face`
#: is -1 for the lit side only, +1 for the shadowed side only, 0 for both.
#: Ordered coarse to fine, because the fine marks have to land on top.
_PEAK_MARKS = (
    ("shade", 70, (0.04, 0.98), (2.2, 6.4), (0.9, 2.4), (0.05, 0.12), 0),
    ("lift", 44, (0.60, 1.00), (3.4, 8.4), (1.3, 3.2), (0.04, 0.09), 0),
    ("moss", 44, (0.38, 1.00), (1.6, 5.2), (0.9, 2.4), (0.06, 0.14), 0),
    ("rim", 64, (0.06, 0.94), (1.4, 4.2), (0.5, 1.5), (0.05, 0.13), -1),
    ("dark", 64, (0.06, 0.98), (1.4, 4.2), (0.6, 1.8), (0.05, 0.13), 1),
    ("grain", 210, (0.02, 1.00), (0.7, 2.6), (0.22, 0.75), (0.05, 0.14), 0),
)


def _summit(pen: _Pen, look: dict, seed: int) -> None:
    """The mountain: painted rather than filled.

    Four passes, cheapest first. A banded value ramp that darkens toward the
    apex and lifts into the haze toward the base; the shadowed face; the lit
    rim; then the brushwork, which is what breaks every edge the first three
    passes left straight.
    """
    body, dark, rim = _rock(look)
    haze = _air(look, -8.0)
    moss = mix(_foliage(look, dark=True), body, 0.40)
    tone = {"shade": dark, "lift": haze, "moss": moss, "rim": rim,
            "dark": dark}

    pen.poly(_peak_poly(seed), col=body)

    # 1. the value ramp. Bands overlap by more than their pitch so no seam
    # of background can show through between two of them.
    n = 44
    for i in range(n):
        f0 = i / n
        f1 = min(1.0, (i + 1.7) / n)
        l0, r0 = _peak_pt(f0, -1.0, seed), _peak_pt(f0, 1.0, seed)
        l1, r1 = _peak_pt(f1, -1.0, seed), _peak_pt(f1, 1.0, seed)
        g = (i + 0.5) / n
        col = mix(mix(dark, body, min(1.0, g * 2.3)), haze, 0.60 * g ** 2.4)
        col = mix(col, dark if _chance(0.5, seed, i, 71) else rim,
                  _rr(0.0, 0.07, seed, i, 72))
        pen.poly([l0, r0, r1, l1], col=col)

    # 2. the shadowed face, hung off the wandering crest so the two halves of
    # the cone are different shapes as well as different values. Three
    # narrowing passes rather than one: a single alpha poly puts a clean
    # drawn line down the middle of the mountain, and the fall of light
    # across a rounded cone has no line in it at all.
    steps = 26
    for off, a in ((-0.10, 0.13), (0.06, 0.13), (0.22, 0.13)):
        face = [PEAK_APEX]
        face += [_peak_pt(i / steps,
                          min(0.97, _peak_crest(i / steps, seed) + off), seed)
                 for i in range(1, steps + 1)]
        face += [_peak_pt(i / steps, 1.0, seed) for i in range(steps, 0, -1)]
        pen.poly(face, col=alpha(dark, a))

    # 3. the lit rim. Inset in *units*, not in `u`, or it would be a hairline
    # at the apex and a stripe a third of the mountain wide at the base; and
    # wobbled along its length, or it is a strip of tape stuck to the edge.
    for band, a in ((2.2, 0.20), (0.9, 0.42)):
        out, inn = [], []
        for i in range(steps + 1):
            f = i / steps
            hw = max(0.5, _peak_half(f, seed, 0))
            inset = band * _rr(0.35, 1.35, seed, i, 73)
            out.append(_peak_pt(f, -1.0, seed))
            inn.append(_peak_pt(f, min(-0.16, -1.0 + inset / hw), seed))
        pen.poly(out + inn[::-1], col=alpha(rim, a))

    # 4. the brushwork
    for j, (tag, count, fr, ln, wd, ar, face_side) in enumerate(_PEAK_MARKS):
        col = tone.get(tag, body)
        for i in range(count):
            f = _rr(fr[0], fr[1], seed, j, i, 81)
            u = _rr(-0.97, 0.97, seed, j, i, 82)
            if face_side and (u < _peak_crest(f, seed)) != (face_side < 0):
                continue
            if tag == "grain":
                col = dark if _chance(0.55, seed, j, i, 86) else rim
            _peak_mark(pen, col, f=f, u=u,
                       length=_rr(ln[0], ln[1], seed, j, i, 83),
                       width=_rr(wd[0], wd[1], seed, j, i, 84),
                       a=_rr(ar[0], ar[1], seed, j, i, 85),
                       seed=seed, idx=(j << 12) ^ i)


def _peak_ridge(pen: _Pen, look: dict, *, base_y: float, z: float, seed: int,
                period: float, amp: tuple[float, float]) -> None:
    """One distant ridge, washed toward the sky and stood in its own mist.

    `depth_tint` alone leaves a distant ridge with a crisp edge, which is
    the tell that gives away a drawn horizon. The veil along its foot is
    what turns three flat silhouettes into distance.
    """
    sky = look["sky"]
    # Nearer ridges are darker as well as less hazed. `depth_tint` alone
    # only ever moves a colour toward the sky, so four calls on one base
    # colour give four greys eight L* apart and no distance at all.
    land = depth_tint(mix(look["far"], look["ink"], 0.08 + 0.62 * (1.0 - z)),
                      z, sky)
    _hills(pen, base_y, land, seed, period=period, amp=amp)
    b = pen.bounds()
    veil = _air(look, -2.0)
    step = max(12.0, period * 0.7)
    i0 = int(math.floor(b[0] / step)) - 1
    for i in range(i0, int(math.ceil(b[2] / step)) + 2):
        if not _chance(0.72, seed, i, 10):
            continue                       # patchy, or it is a second sky
        _mist_bank(pen, veil, cx=i * step + _rr(-6.0, 6.0, seed, i, 11),
                   cy=base_y - _rr(0.0, 2.4, seed, i, 12),
                   rx=_rr(11.0, 21.0, seed, i, 13),
                   ry=_rr(1.4, 3.2, seed, i, 14),
                   a=0.07 + 0.13 * z, seed=seed, idx=i, lobes=4)
        # a second, thinner pass riding the crest, because the tell of a
        # drawn horizon is not the silhouette's shape but how cleanly its
        # top edge cuts the sky
        _mist_bank(pen, veil, cx=i * step + _rr(-9.0, 9.0, seed, i, 15),
                   cy=base_y - amp[1] * _rr(0.35, 0.85, seed, i, 16),
                   rx=_rr(14.0, 26.0, seed, i, 17),
                   ry=_rr(1.6, 3.6, seed, i, 18),
                   a=0.05 + 0.09 * z, seed=seed ^ 0x5B, idx=i, lobes=4)


def _peak_weather(pen: _Pen, look: dict, t: float, seed: int, *,
                  yr: tuple[float, float], period: float, drift: float,
                  size: tuple[float, float], a: float, lift: float,
                  churn: float = 0.0) -> None:
    """Soft cloud tiling for ever along x and sliding with `t`.

    The drift is folded into the tile index rather than accumulated, so
    scrubbing to a frame gives that frame and nothing has to remember where
    the weather was last time.
    """
    col = _air(look, lift)
    sh = drift * float(t)
    i0 = int(math.floor((pen.bounds()[0] - sh - period) / period))
    i1 = int(math.ceil((pen.bounds()[2] - sh + period) / period))
    for i in range(i0, i1 + 1):
        if not _chance(0.78, seed, i, 21):
            continue
        _mist_bank(pen, col,
                   cx=i * period + sh + _rr(-period * 0.3, period * 0.3,
                                            seed, i, 22),
                   cy=_rr(yr[0], yr[1], seed, i, 23),
                   rx=_rr(size[0], size[1], seed, i, 24),
                   ry=_rr(size[0], size[1], seed, i, 25) * 0.30,
                   a=a * _rr(0.7, 1.25, seed, i, 26), seed=seed, idx=i,
                   lobes=8, t=float(t), churn=churn)


def _peak_mist(pen: _Pen, look: dict, t: float, seed: int) -> None:
    """Valley cloud pooling round the foot of the mountain.

    Drawn in front of the summit and thickening downward, which is what
    hides the join between the cone and the bottom of the frame and what
    stops the peak from reading as an object standing on a floor.

    It is also the fastest-moving thing in the set, and on purpose. The one
    place in frame with real contrast is where mist crosses the dark rock,
    so that is where the motion has to be — and the lobes are kept narrow
    for the same reason, since it is their vertical edges, not the long
    horizontal ones, that a moving frame is measured on.
    """
    b = pen.bounds()
    # warmed toward the ground: in the reference the valley cloud is the one
    # part of the weather that is not blue, and that warmth is most of what
    # separates it from the ridges standing in it
    pale = mix(_air(look, -2.0), look["ground"], 0.18)
    for r in range(7):
        y = 43.5 + r * 2.3
        a = 0.06 + 0.055 * r
        step = 13.0
        sh = (9.5 + 3.2 * r) * float(t)
        i0 = int(math.floor((b[0] - sh - step) / step)) - 1
        for i in range(i0, int(math.ceil((b[2] - sh + step) / step)) + 2):
            _mist_bank(pen, pale,
                       cx=i * step + sh + _rr(-5.0, 5.0, seed, r, i, 31),
                       cy=y + _rr(-1.6, 1.6, seed, r, i, 32),
                       rx=_rr(7.0, 15.0, seed, r, i, 33),
                       ry=_rr(1.8, 4.2, seed, r, i, 34),
                       a=a, seed=seed ^ (r * 0x2F), idx=i, lobes=5,
                       t=float(t), churn=2.2 + 0.5 * r)
    # and a floor of it, built as a ramp of overlapping slabs rather than one
    # rectangle: a single low-alpha rect announces its own top edge as a rule
    # ruled across the frame, which is the one thing mist must never do. The
    # per-slab alpha ramps up from almost nothing for the same reason — the
    # first slab is an edge too, it is just a fainter one.
    for k in range(18):
        pen.rect(b[0] - 8.0, 45.0 + k * 0.72, b[2] + 8.0, b[3] + 6.0,
                 col=alpha(pale, 0.010 + 0.0095 * k))


#: How many drizzle strokes fall across the frame at once. Kept low and made
#: up in stroke *length* instead: long strokes read as rain and short ones
#: read as grain, and grain is the one thing the style contract forbids
#: outright.
_RAIN_N = 420


def _peak_rain(pen: _Pen, look: dict, t: float, seed: int) -> None:
    """Fine drizzle, falling and leaning with the wind.

    The reference frames have it, so it is not an invention — but it earns
    its place twice over. A locked-off camera on a pale, soft, low-contrast
    world is the worst case there is for a frozen frame, and everything else
    in this set is soft on purpose. Drizzle is the opposite: thin, crisp and
    fast, so it renews a few percent of the frame every single frame for
    almost no visual weight.

    Each stroke's position is ``start + speed * t`` wrapped into the frame,
    which is a pure function of `t` — nothing accumulates, so scrubbing to a
    frame gives that frame and a re-render gives the same bytes.
    """
    b = pen.bounds()
    col = _air(look, -30.0)
    w = (b[2] - b[0]) + 24.0
    span = (b[3] - b[1]) + 34.0
    for i in range(_RAIN_N):
        speed = _rr(58.0, 96.0, seed, i, 41)
        slant = _rr(-0.30, -0.12, seed, i, 42)
        y = b[1] - 17.0 + (_rr(0.0, 1.0, seed, i, 43) * span
                           + speed * float(t)) % span
        x = b[0] - 12.0 + _rr(0.0, 1.0, seed, i, 44) * w + y * slant
        ln = _rr(4.5, 11.0, seed, i, 45)
        pen.line([(x, y), (x + slant * ln, y + ln)],
                 col=alpha(col, _rr(0.09, 0.20, seed, i, 46)),
                 w=_rr(0.13, 0.26, seed, i, 47), cap=False)


def _set_peak(st: _Stage, look: dict, t: float, seed: int) -> None:
    sky = look["sky"]
    p = st.layer("sky")
    if p:
        top, bot = sky_gradient(sky, spread=5.0)
        p.vgrad(top, bot)
    p = st.layer("clouds")
    if p:
        _peak_weather(p, look, t, seed ^ 0x91, yr=(0.0, 22.0), period=58.0,
                      drift=3.8, size=(26.0, 54.0), a=0.36, lift=-20.0,
                      churn=3.2)
        _peak_weather(p, look, t, seed ^ 0x92, yr=(6.0, 22.0), period=37.0,
                      drift=2.5, size=(16.0, 32.0), a=0.28, lift=8.0,
                      churn=2.4)
        # the bright band the ridges stand in front of. Without it the
        # horizon is the darkest part of the sky, which reads as dusk.
        _peak_weather(p, look, t, seed ^ 0x99, yr=(26.0, 33.0), period=29.0,
                      drift=1.3, size=(18.0, 34.0), a=0.34, lift=10.0,
                      churn=1.4)
    p = st.layer("ridges")
    if p:
        _peak_ridge(p, look, base_y=34.0, z=0.94, seed=seed ^ 0x93,
                    period=21.0, amp=(3.0, 9.0))
        _peak_ridge(p, look, base_y=37.2, z=0.76, seed=seed ^ 0x94,
                    period=17.0, amp=(3.0, 8.0))
    p = st.layer("shoulders")
    if p:
        _peak_ridge(p, look, base_y=41.0, z=0.56, seed=seed ^ 0x95,
                    period=14.0, amp=(2.5, 7.0))
        _peak_ridge(p, look, base_y=44.5, z=0.40, seed=seed ^ 0x96,
                    period=11.0, amp=(2.0, 5.5))
    p = st.layer("summit")
    if p:
        _summit(p, look, seed ^ 0x97)
    p = st.layer("mist")
    if p:
        _peak_mist(p, look, t, seed ^ 0x98)
    p = st.layer("rain")
    if p:
        _peak_rain(p, look, t, seed ^ 0x9A)


SETS: dict[str, object] = {
    "street": _set_street,
    "suburb": _set_suburb,
    "highway": _set_highway,
    "aerial": _set_aerial,
    "office": _set_office,
    "sky": _set_sky,
    "peak": _set_peak,
}


# ------------------------------------------------------------------ props ----
#
# Every prop draws in *design units* around its own anchor at ``(0, 0)``.
# `draw_prop` folds `scale` into the pen, so nothing below multiplies by it.

def _wheel(pen: _Pen, cx, cy, r, deg, look: dict, hub: tuple) -> None:
    """A wheel you can see turn. `deg` comes straight from `phase`."""
    ink = look["ink"]
    tyre = mix(ink, look["ground"], 0.14)
    pen.circle(cx, cy, r, col=tyre)
    pen.circle(cx, cy, r * 0.60, col=hub)
    a0 = math.radians(deg)
    for k in range(5):
        a = a0 + k * (2 * math.pi / 5)
        pen.line([(cx + math.cos(a) * r * 0.14, cy + math.sin(a) * r * 0.14),
                  (cx + math.cos(a) * r * 0.52, cy + math.sin(a) * r * 0.52)],
                 shade(hub, 0.62), r * 0.13)
    pen.circle(cx + math.cos(a0) * r * 0.40, cy + math.sin(a0) * r * 0.40,
               r * 0.13, col=ink)
    pen.circle(cx, cy, r * 0.17, col=shade(hub, 0.50))


_CAR_BODY = [(-21.2, 5.8), (-21.7, 1.6), (-18.6, -0.7), (-11.6, -1.5),
             (-7.4, -6.4), (-1.0, -7.1), (4.2, -6.9), (9.8, -1.7),
             (18.2, -0.6), (21.7, 1.5), (21.9, 5.8)]
_CAR_GLASS = [(-8.9, -2.3), (-6.4, -5.9), (3.0, -6.1), (8.6, -2.3)]
_CAR_WHEELS = ((-12.6, 5.0), (12.6, 5.0))
_CAR_R = 3.0


def _car_body(pen: _Pen, look: dict, body: RGB, *, phase, t, seed, anim,
              police=False) -> None:
    ink = look["ink"]
    a = str(anim or "").lower()
    if a == "bounce":
        bob = -1.10 * abs(math.sin(math.pi * phase))
        tilt = 2.0 * math.sin(2 * math.pi * phase)
    else:
        bob = -0.11 * (1.0 - math.cos(2 * math.pi * phase))
        tilt = 0.30 * math.sin(2 * math.pi * phase)

    def xf(pts):
        return _rot([(x, y + bob) for x, y in pts], 0.0, 4.0, tilt)

    dark = shade(body, 0.84)
    glass = mix(look["sky"], look["near"], 0.50)
    edge = _edge(look, body)
    gedge = _edge(look, glass)

    for wx, wy in _CAR_WHEELS:                          # arches, behind wheels
        p = xf([(wx, wy - 0.4)])[0]
        pen.circle(p[0], p[1], _CAR_R + 1.15, col=shade(body, 0.70))

    pen.poly(xf(_CAR_BODY), col=body, ink=edge, w=0.34)
    pen.poly(xf([(-21.4, 3.4), (21.8, 3.4), (21.9, 5.8), (-21.2, 5.8)]),
             col=dark)
    pen.poly(xf(_CAR_GLASS), col=glass, ink=gedge, w=0.26)
    pen.poly(xf([(-6.2, -5.6), (-1.4, -5.9), (-1.4, -2.6), (-7.9, -2.6)]),
             col=tint(glass, 0.34))
    pen.poly(xf([(-1.0, -2.5), (-1.0, -6.0), (0.2, -6.0), (0.2, -2.5)]),
             col=body)                                  # B-pillar
    pen.poly(xf([(-5.6, -6.7), (3.2, -6.6), (3.0, -6.0), (-5.4, -6.1)]),
             col=tint(body, 0.20))                      # flat roof highlight

    pen.line(xf([(-1.6, -1.9), (-2.6, 3.3)]), mix(edge, body, 0.30), 0.24)
    pen.line(xf([(-9.4, -0.9), (-9.9, 3.3)]), mix(edge, body, 0.30), 0.20)
    pen.poly(xf([(-4.4, 0.4), (-2.4, 0.2), (-2.4, 0.9), (-4.4, 1.1)]),
             col=mix(look["near"], ink, 0.25))          # door handle

    pen.poly(xf([(18.6, 0.6), (21.5, 1.6), (21.4, 2.9), (18.4, 2.3)]),
             col=mix(look["accent2"], (255, 255, 255), 0.42))
    pen.poly(xf([(-21.5, 1.7), (-19.0, 0.8), (-19.2, 2.5), (-21.4, 3.0)]),
             col=mix(look["accent"], ink, 0.26))
    pen.poly(xf([(-21.8, 3.6), (-19.6, 3.6), (-19.6, 5.4), (-21.6, 5.4)]),
             col=shade(body, 0.62))
    pen.poly(xf([(19.8, 3.6), (22.0, 3.6), (22.0, 5.4), (19.8, 5.4)]),
             col=shade(body, 0.62))

    if police:
        pen.poly(xf([(-14.0, 0.1), (7.0, -0.7), (7.0, 3.3), (-14.0, 3.7)]),
                 col=_hued(218.0, 0.72, 26.0))
        pen.poly(xf([(-14.0, 0.1), (7.0, -0.7), (7.0, 0.6), (-14.0, 1.4)]),
                 col=_hued(354.0, 0.80, 44.0))
        pen.circle(*xf([(-5.0, 1.7)])[0], 1.6,
                   col=mix(look["near"], (255, 255, 255), 0.7),
                   ink=_hued(218.0, 0.72, 22.0), w=0.30)
        pen.poly(xf([(21.2, 0.4), (23.2, 1.0), (23.2, 5.2), (21.2, 5.2)]),
                 col=mix(ink, look["near"], 0.22))
        pen.line(xf([(22.2, 0.7), (22.2, 5.2)]),
                 mix(ink, look["near"], 0.22), 0.9)

    wdeg = phase * 360.0
    for wx, wy in _CAR_WHEELS:
        p = xf([(wx, wy)])[0]
        _wheel(pen, p[0], p[1], _CAR_R, wdeg, look,
               mix(look["near"], look["sky"], 0.30))
    del t, seed
    return xf


def _prop_car(pen, look, s, phase, t, seed, anim):
    _car_body(pen, look, look["accent"], phase=phase, t=t, seed=seed,
              anim=anim)
    del s


#: Half-period of the light bar, seconds. Two states, so the pair alternates
#: at 1/(2*_LIGHTBAR) = 1.79 Hz — inside the 1.5-2 Hz the style calls for, and
#: 8.4 frames per state at 30 fps, which is far from any strobing threshold.
_LIGHTBAR = 0.28


def _prop_policecar(pen, look, s, phase, t, seed, anim):
    ink = look["ink"]
    # White, at the palette's brightest, not "the palette's beige".
    body = _at_lightness(desaturate(mix(look["near"], (255, 255, 255), 0.72),
                                    0.66),
                         min(95.0, lightness(look["near"]) + 10.0))
    xf = _car_body(pen, look, body, phase=phase, t=t, seed=seed, anim=anim,
                   police=True)

    # Emergency lights are red and blue everywhere on earth; only their
    # brightness is the film's business.
    red = _hued(354.0, 0.88, 50.0)
    blue = _hued(218.0, 0.84, 50.0)
    side = int(math.floor(float(t) / _LIGHTBAR)) % 2
    lit = (red, shade(blue, 0.34)) if side == 0 else (shade(red, 0.34), blue)

    ty = -7.2
    hot = red if side == 0 else blue
    hx, hy = xf([(-3.85 if side == 0 else 3.85, ty - 1.8)])[0]
    pen.ellipse(hx, hy, 5.0, 2.9, col=alpha(hot, 0.16))
    pen.ellipse(hx, hy, 3.2, 2.0, col=alpha(hot, 0.20))
    pen.poly(xf([(-8.5, ty - 3.6), (-8.1, ty - 3.6), (-7.7, ty - 0.6),
                 (-8.1, ty - 0.6)]), col=mix(ink, look["near"], 0.30))
    pen.poly(xf([(-7.4, ty - 0.7), (7.4, ty - 0.7), (7.0, ty + 0.2),
                 (-7.0, ty + 0.2)]), col=mix(ink, look["ground"], 0.26))
    pen.poly(xf([(-7.2, ty - 3.0), (-0.5, ty - 3.0), (-0.5, ty - 0.6),
                 (-7.2, ty - 0.6)]), col=lit[0], ink=_edge(look, lit[0]),
             w=0.24)
    pen.poly(xf([(0.5, ty - 3.0), (7.2, ty - 3.0), (7.2, ty - 0.6),
                 (0.5, ty - 0.6)]), col=lit[1], ink=_edge(look, lit[1]),
             w=0.24)
    pen.poly(xf([(-0.55, ty - 3.1), (0.55, ty - 3.1), (0.55, ty - 0.5),
                 (-0.55, ty - 0.5)]), col=mix(ink, look["ground"], 0.26))
    for c, x0, x1 in ((lit[0], -7.0, -0.7), (lit[1], 0.7, 7.0)):
        pen.poly(xf([(x0, ty - 2.9), (x1, ty - 2.9), (x1, ty - 2.3),
                     (x0, ty - 2.3)]), col=tint(c, 0.34))
    del s, seed


def _prop_helicopter(pen, look, s, phase, t, seed, anim):
    """Faces right, like the car. The rotor is a disc, never blades.

    At 12-24 fps discrete blades strobe and read as a stopped propeller, so
    the rotor is a flat translucent ellipse with one slow sweep chord: the
    eye reads "spinning fast" and no frame rate can alias it.
    """
    ink = look["ink"]
    body = desaturate(mix(look["near"], look["far"], 0.30), 0.55)
    dark = shade(body, 0.76)
    glass = _glass(look)
    metal = mix(ink, look["ground"], 0.36)

    a = str(anim or "").lower()
    bob = (-0.55 * math.sin(2 * math.pi * phase)) if a == "bob" else 0.0

    def xf(pts):
        return [(x, y + bob) for x, y in pts]

    # tail boom, fin, stabiliser
    pen.poly(xf([(-28.8, -9.4), (-25.0, -8.4), (-22.4, 0.6), (-27.2, 0.9)]),
             col=body, ink=ink, w=0.30)
    pen.poly(xf([(-28.0, -1.4), (-7.0, -3.6), (-7.0, 3.4), (-28.0, 1.2)]),
             col=dark, ink=ink, w=0.30)
    pen.poly(xf([(-27.6, -3.2), (-18.4, -2.3), (-18.4, -1.1), (-27.6, -1.7)]),
             col=body, ink=ink, w=0.22)
    pen.poly(xf([(-25.0, -1.6), (-11.0, -2.9), (-11.0, -1.5), (-25.0, -0.4)]),
             col=look["accent"])

    # tail rotor: same trick, smaller
    trx, try_ = xf([(-26.4, -4.8)])[0]
    pen.circle(trx, try_, 4.4, col=alpha(ink, 0.07))
    pen.circle(trx, try_, 4.4, ink=alpha(ink, 0.16), w=0.22)
    ta = math.radians(t * 300.0)
    pen.line([(trx + math.cos(ta) * 4.3, try_ + math.sin(ta) * 4.3),
              (trx - math.cos(ta) * 4.3, try_ - math.sin(ta) * 4.3)],
             alpha(ink, 0.30), 0.40)
    pen.circle(trx, try_, 0.7, col=metal)

    # cabin
    pen.poly(xf([(-7.0, -6.6), (0.0, -7.8), (9.0, -7.0), (15.4, -4.2),
                 (19.4, 0.4), (18.0, 4.6), (11.0, 6.8), (0.0, 7.0),
                 (-6.4, 5.2)]), col=body, ink=ink, w=0.34)
    pen.poly(xf([(-6.6, 2.6), (18.4, 2.6), (17.2, 5.0), (10.6, 6.8),
                 (0.0, 7.0), (-6.4, 5.2)]), col=dark)
    pen.poly(xf([(4.4, -5.6), (10.8, -5.4), (17.4, -0.8), (16.4, 3.4),
                 (6.6, 3.4), (4.2, -0.8)]), col=glass, ink=ink, w=0.28)
    pen.poly(xf([(5.2, -4.4), (9.8, -4.3), (13.0, -1.0), (6.0, -1.0)]),
             col=tint(glass, 0.36))
    pen.poly(xf([(-4.2, -4.6), (1.8, -5.0), (1.8, -0.6), (-4.2, -0.6)]),
             col=glass, ink=ink, w=0.24)
    pen.poly(xf([(-6.6, -0.2), (18.9, -0.2), (19.1, 1.2), (-6.8, 1.2)]),
             col=look["accent"])

    # skids
    for sx, ex in ((-3.0, -4.6), (10.0, 11.4)):
        pen.line(xf([(sx, 6.0), (ex, 9.9)]), metal, 0.62)
    pen.line(xf([(-8.0, 10.1), (15.0, 10.1)]), metal, 0.70)

    # nose camera ball: the only reason a news chopper is in the shot
    cbx, cby = xf([(14.6, 7.4)])[0]
    pen.circle(cbx, cby, 2.2, col=metal, ink=ink, w=0.24)
    pen.circle(cbx + 0.7, cby + 0.4, 1.0, col=look["accent2"])

    # main rotor
    mx, my = xf([(2.0, -12.4)])[0]
    pen.ellipse(mx, my, 30.0, 3.1, col=alpha(ink, 0.12))
    pen.ellipse(mx, my, 30.0, 3.1, ink=alpha(ink, 0.18), w=0.22)
    pen.ellipse(mx, my, 20.0, 2.1, col=alpha(ink, 0.10))
    ra = math.radians(t * 324.0)
    pen.line([(mx + math.cos(ra) * 29.4, my + math.sin(ra) * 3.0),
              (mx - math.cos(ra) * 29.4, my - math.sin(ra) * 3.0)],
             alpha(ink, 0.26), 0.52)
    pen.poly(xf([(1.1, -12.4), (2.9, -12.4), (2.9, -6.8), (1.1, -6.8)]),
             col=metal)
    pen.poly(xf([(0.4, -13.6), (3.6, -13.6), (3.3, -12.2), (0.7, -12.2)]),
             col=shade(metal, 0.82), ink=ink, w=0.22)
    pen.circle(mx, my, 1.3, col=metal, ink=ink, w=0.22)
    del s, seed


def _prop_cone(pen, look, s, phase, t, seed, anim):
    ink = _edge(look, look["accent"])
    band = mix(look["near"], look["sky"], 0.30)
    pen.rrect(-3.4, -1.05, 3.4, 0.0, 0.35,
              col=shade(look["accent"], 0.74), ink=ink, w=0.22)
    pen.poly([(-2.35, -1.05), (2.35, -1.05), (0.72, -6.6), (-0.72, -6.6)],
             col=look["accent"], ink=ink, w=0.24)
    pen.rrect(-0.85, -7.0, 0.85, -6.3, 0.32, col=look["accent"], ink=ink,
              w=0.22)
    pen.poly([(-1.86, -3.0), (1.86, -3.0), (1.63, -3.8), (-1.63, -3.8)],
             col=band)
    pen.poly([(-1.36, -4.7), (1.36, -4.7), (1.19, -5.3), (-1.19, -5.3)],
             col=band)
    del s, phase, t, seed, anim


def _prop_bin(pen, look, s, phase, t, seed, anim):
    body = mix(look["far"], look["ink"], 0.34)
    ink = _edge(look, body)
    pen.poly([(-3.2, 0.0), (3.2, 0.0), (3.7, -9.4), (-3.7, -9.4)],
             col=body, ink=ink, w=0.28)
    pen.poly([(1.4, 0.0), (3.2, 0.0), (3.7, -9.4), (1.9, -9.4)],
             col=shade(body, 0.86))
    for x in (-1.9, -0.2, 1.5):
        pen.line([(x, -9.0), (x + 0.12, -0.5)], shade(body, 0.78), 0.24)
    pen.rrect(-4.0, -10.5, 4.0, -9.2, 0.5, col=shade(body, 0.80), ink=ink,
              w=0.26)
    pen.rrect(-1.0, -11.0, 1.0, -10.3, 0.3, col=shade(body, 0.68))
    del s, phase, t, seed, anim


def _prop_hydrant(pen, look, s, phase, t, seed, anim):
    body = look["accent"]
    ink = _edge(look, body)
    pen.rrect(-2.6, -0.9, 2.6, 0.0, 0.3, col=shade(body, 0.70), ink=ink,
              w=0.22)
    pen.rrect(-2.9, -5.2, -1.0, -3.9, 0.35, col=shade(body, 0.80), ink=ink,
              w=0.24)
    pen.rrect(1.0, -5.2, 2.9, -3.9, 0.35, col=shade(body, 0.80), ink=ink,
              w=0.24)
    pen.rrect(-1.65, -7.0, 1.65, -0.7, 0.7, col=body, ink=ink, w=0.26)
    pen.circle(0.0, -7.0, 1.65, col=body, ink=ink, w=0.26)
    pen.rect(-1.7, -6.0, 1.7, -5.45, col=tint(body, 0.26))
    pen.rrect(-0.75, -8.6, 0.75, -7.8, 0.3, col=shade(body, 0.74), ink=ink,
              w=0.22)
    pen.rrect(-1.2, -8.0, 1.2, -7.4, 0.25, col=shade(body, 0.86))
    del s, phase, t, seed, anim


def _prop_lamppost(pen, look, s, phase, t, seed, anim):
    metal = mix(look["ink"], look["far"], 0.32)
    ink = _edge(look, metal)
    lamp = mix(look["near"], look["sky"], 0.55)
    pen.rrect(-1.6, -2.6, 1.6, 0.0, 0.4, col=shade(metal, 0.84), ink=ink,
              w=0.24)
    pen.poly([(-1.05, -2.4), (1.05, -2.4), (0.72, -31.0), (-0.72, -31.0)],
             col=metal, ink=ink, w=0.24)
    pen.rect(-1.3, -6.6, 1.3, -5.8, col=shade(metal, 0.82))
    pen.line([(0.0, -30.6), (2.0, -33.2), (4.9, -34.0), (6.9, -33.6)],
             metal, 0.86)
    pen.poly([(5.0, -33.6), (8.2, -33.2), (7.5, -31.4), (5.8, -31.7)],
             col=shade(metal, 0.86), ink=ink, w=0.24)
    pen.poly([(5.7, -32.4), (7.9, -32.1), (7.5, -31.6), (5.9, -31.8)],
             col=lamp)
    del s, phase, t, seed, anim


def _prop_tree(pen, look, s, phase, t, seed, anim):
    lean = 0.0
    if str(anim or "").lower() == "sway":
        lean = 0.9 * math.sin(2 * math.pi * phase)
    _tree_shape(pen, 0.0, 0.0, 22.0, _foliage(look),
                _foliage(look, dark=True), mix(look["ink"], look["ground"],
                                               0.34),
                _edge(look, _foliage(look)), seed, 0, lean=lean)
    del s, t


def _prop_building(pen, look, s, phase, t, seed, anim):
    body = mix(look["mid"], look["near"], 0.45)
    glass = _glass(look)
    ink = _edge(look, body)
    pen.rect(-17.0, -46.0, 17.0, 0.0, col=body)
    pen.rect(11.2, -46.0, 17.0, 0.0, col=shade(body, 0.92))
    pen.rect(-17.6, -47.4, 17.6, -46.0, col=shade(body, 0.84))
    pen.rect(-17.2, -47.4, 17.2, -46.9, col=shade(body, 0.72))
    rows, top, bot = 8, -43.4, -11.4
    step = (bot - top) / rows
    for r in range(rows):
        y = top + r * step
        pen.rect(-15.8, y, 15.8, y + step - 1.2, col=shade(body, 0.78))
        _win_grid(pen, -15.6, y, 15.6, y + step - 1.2, 5, 1, glass,
                  _lit_window(look), seed, r, lit=_lit_rate(look), gap=0.4)
    pen.rect(-17.0, -10.2, 17.0, 0.0, col=shade(body, 0.90))
    pen.rect(-17.4, -10.8, 17.4, -9.9, col=shade(body, 0.78))
    pen.rrect(-4.4, -8.2, 4.4, 0.0, 0.6, col=glass, ink=ink, w=0.32)
    pen.rect(-0.35, -8.0, 0.35, 0.0, col=mix(ink, body, 0.42))
    pen.poly([(-3.4, -0.6), (-1.6, -6.6), (-0.7, -6.6), (-2.5, -0.6)],
             col=tint(glass, 0.30))
    for x0 in (-15.4, 6.6):
        pen.rect(x0, -7.6, x0 + 8.8, -1.6, col=glass, ink=shade(body, 0.72),
                 w=0.30)
        pen.poly([(x0 + 1.0, -1.9), (x0 + 4.2, -7.3), (x0 + 5.6, -7.3),
                  (x0 + 2.4, -1.9)], col=tint(glass, 0.30))
        pen.rect(x0 - 0.4, -9.4, x0 + 9.2, -7.8, col=look["accent2"])
    pen.line([(-17.0, 0.0), (17.0, 0.0)], ink, 0.34)
    del s, phase, t, anim


def _prop_cloud(pen, look, s, phase, t, seed, anim):
    body = mix(look["near"], (255, 255, 255), 0.62)
    under = mix(look["near"], look["far"], 0.36)
    dx = 0.0
    if str(anim or "").lower() == "drift":
        dx = 1.6 * math.sin(2 * math.pi * phase)
    _cloud_shape(pen, dx, 0.0, 23.0, 4.8, body, under, seed, 0)
    del s, t


def _prop_sign(pen, look, s, phase, t, seed, anim):
    face = look["accent2"]
    ink = _edge(look, face)
    metal = mix(look["ink"], look["ground"], 0.40)
    pen.rrect(-1.4, -1.0, 1.4, 0.0, 0.3, col=shade(metal, 0.85))
    pen.poly([(-0.62, -0.8), (0.62, -0.8), (0.5, -11.6), (-0.5, -11.6)],
             col=metal, ink=ink, w=0.22)
    pen.rrect(-7.0, -19.0, 7.0, -11.0, 0.9, col=face, ink=ink, w=0.34)
    pen.rrect(-6.1, -18.1, 6.1, -11.9, 0.5, col=None,
              ink=mix(ink, face, 0.25), w=0.26)
    arrow = mix(ink, face, 0.12)
    pen.poly([(-3.4, -15.9), (0.4, -15.9), (0.4, -17.6), (4.2, -15.0),
              (0.4, -12.4), (0.4, -14.1), (-3.4, -14.1)], col=arrow)
    del s, phase, t, seed, anim


#: Every prop this module can draw. A name that is not a key here is drawn
#: as a labelled placeholder and recorded in `MISSING` -- never substituted.
# --- milkfloat ---------------------------------------------------------------
#
# The getaway vehicle. It has to belong to the same world as `car` — same
# wheel, same bob-and-tilt, same edge language — while being unmistakably
# the wrong choice: boxy, upright, open-sided, tiny wheels, and a load of
# bottles that rattle every time it moves.

_MF_WHEELS = ((-9.8, 5.4), (9.8, 5.4))
_MF_R = 2.6


def _crate(pen: _Pen, look: dict, x: float, y: float, w: float, h: float,
           crate: RGB, milk: RGB, seed: int, idx: int) -> None:
    """One crate of bottles, sitting with its base at `y`."""
    top = y - h
    pen.rect(x, top + h * 0.42, x + w, y, col=crate,
             ink=_edge(look, crate), w=0.20)
    for k in range(3):
        gx = x + w * (0.18 + k * 0.32)
        pen.rect(gx, top + h * 0.56, gx + w * 0.14, y - h * 0.10,
                 col=shade(crate, 0.74))
    n = 3 if w > 5.0 else 2
    for k in range(n):
        bx = x + w * (k + 0.5) / n
        bh = h * _rr(0.52, 0.66, seed, idx, k)
        pen.rect(bx - w * 0.11, top + h * 0.42 - bh, bx + w * 0.11,
                 top + h * 0.46, col=milk)
        pen.rect(bx - w * 0.05, top + h * 0.42 - bh - h * 0.13,
                 bx + w * 0.05, top + h * 0.42 - bh + h * 0.03, col=milk)
        pen.rect(bx - w * 0.07, top + h * 0.42 - bh - h * 0.19,
                 bx + w * 0.07, top + h * 0.42 - bh - h * 0.11,
                 col=shade(look["accent2"], 0.92))


def _prop_milkfloat(pen, look, s, phase, t, seed, anim):
    ink = look["ink"]
    a = str(anim or "").lower()
    if a == "bounce":
        # Heavier and slower than the car's bounce: it wallows, it does not
        # leap, and the crates get their own lag so the load rattles.
        bob = -0.85 * abs(math.sin(math.pi * phase))
        tilt = 1.35 * math.sin(2 * math.pi * phase)
        rattle = 0.42 * math.sin(2 * math.pi * phase + 1.1)
    else:
        bob = -0.09 * (1.0 - math.cos(2 * math.pi * phase))
        tilt = 0.22 * math.sin(2 * math.pi * phase)
        rattle = 0.10 * math.sin(2 * math.pi * phase + 0.8)

    def xf(pts, dy=0.0):
        return _rot([(x, y + bob + dy) for x, y in pts], 0.0, 4.0, tilt)

    # Dairy white, like the police car is police white: the palette sets how
    # bright it is, not what it is.
    body = _at_lightness(desaturate(mix(look["near"], (255, 255, 255), 0.70),
                                    0.60),
                         min(94.0, lightness(look["near"]) + 9.0))
    edge = _edge(look, body)
    milk = _at_lightness(desaturate(mix(look["near"], (255, 255, 255), 0.86),
                                    0.80),
                         min(96.0, lightness(look["near"]) + 14.0))
    crate = mix(look["accent2"], ink, 0.20)
    glass = mix(look["sky"], look["near"], 0.50)
    stripe = look["accent"]
    deck = shade(body, 0.72)

    for wx, wy in _MF_WHEELS:                        # arches, behind wheels
        px_, py_ = xf([(wx, wy - 0.3)])[0]
        pen.circle(px_, py_, _MF_R + 0.95, col=shade(body, 0.70))

    # chassis slab
    pen.poly(xf([(-16.6, 1.4), (16.8, 1.4), (16.8, 5.6), (-16.6, 5.6)]),
             col=deck, ink=edge, w=0.26)
    pen.poly(xf([(-16.6, 4.2), (16.8, 4.2), (16.8, 5.6), (-16.6, 5.6)]),
             col=shade(deck, 0.80))
    # the dairy band runs the length of the skirt, below the deck, so the
    # load never has a stripe painted across it
    pen.poly(xf([(-16.6, 1.9), (16.8, 1.9), (16.8, 3.5), (-16.6, 3.5)]),
             col=stripe)

    # load bay: crates on the open deck, drawn before the roof posts
    for k, (cx, cw, ch) in enumerate(((-15.6, 6.6, 6.2), (-8.6, 6.6, 6.2),
                                      (-1.6, 6.0, 6.2))):
        pts = xf([(cx, 1.5)], dy=rattle * (0.4 if k % 2 else -0.6))
        _crate(pen, look, pts[0][0], pts[0][1], cw, ch, crate, milk, seed, k)
    for k, (cx, cw, ch) in enumerate(((-14.2, 6.0, 5.4), (-7.4, 5.6, 5.4))):
        pts = xf([(cx, -4.8)], dy=rattle * (1.0 if k == 0 else -0.7))
        _crate(pen, look, pts[0][0], pts[0][1], cw, ch, crate, milk,
               seed, 7 + k)

    # cab: upright, square, sensible
    pen.poly(xf([(2.6, -12.4), (16.9, -12.4), (17.2, -4.0), (17.2, 4.6),
                 (2.6, 4.6)]), col=body, ink=edge, w=0.32)
    pen.poly(xf([(4.2, -11.2), (15.6, -11.2), (15.9, -5.4), (4.2, -5.4)]),
             col=glass, ink=_edge(look, glass), w=0.24)
    pen.poly(xf([(4.6, -10.8), (8.4, -10.8), (5.4, -5.8), (4.6, -5.8)]),
             col=tint(glass, 0.36))
    pen.poly(xf([(9.6, -11.2), (10.6, -11.2), (10.6, -5.4), (9.6, -5.4)]),
             col=body)                                 # windscreen divider
    pen.poly(xf([(2.6, -1.2), (17.2, -1.2), (17.2, 1.0), (2.6, 1.0)]),
             col=stripe)                               # cab belt line
    pen.poly(xf([(3.4, -4.6), (8.2, -4.6), (8.2, -2.2), (3.4, -2.2)]),
             col=shade(body, 0.88))                    # door panel
    pen.poly(xf([(7.0, -3.9), (7.9, -3.9), (7.9, -3.2), (7.0, -3.2)]),
             col=mix(ink, body, 0.34))                 # handle

    # full-length flat roof on two thin posts: the milk-float silhouette
    pen.poly(xf([(-17.4, -14.0), (17.4, -14.0), (17.4, -12.4),
                 (-17.4, -12.4)]), col=shade(body, 0.90), ink=edge, w=0.26)
    pen.poly(xf([(-17.4, -14.6), (17.4, -14.6), (17.4, -14.0),
                 (-17.4, -14.0)]), col=shade(body, 0.74))
    for rx in (-16.4, -2.2):
        pen.poly(xf([(rx, -12.4), (rx + 1.0, -12.4), (rx + 1.0, 1.4),
                     (rx, 1.4)]), col=shade(body, 0.82))

    # roof sign: a dairy board carrying a bottle mark, not lettering
    pen.poly(xf([(-6.4, -17.6), (7.4, -17.6), (7.4, -14.4), (-6.4, -14.4)]),
             col=milk, ink=edge, w=0.24)
    pen.poly(xf([(-6.4, -15.4), (7.4, -15.4), (7.4, -14.4), (-6.4, -14.4)]),
             col=stripe)                               # sign footer band
    pen.poly(xf([(-4.6, -16.9), (-3.4, -16.9), (-3.4, -16.4),
                 (-4.6, -16.4)]), col=crate)           # bottle cap
    pen.poly(xf([(-4.5, -16.4), (-3.5, -16.4), (-3.1, -15.9),
                 (-3.1, -15.7), (-4.9, -15.7), (-4.9, -15.9)]),
             col=stripe)                               # bottle shoulders
    pen.poly(xf([(-2.2, -16.9), (5.8, -16.9), (5.8, -15.7), (-2.2, -15.7)]),
             col=mix(stripe, ink, 0.30))               # the dairy's name

    # lamps and the slow-vehicle plate
    pen.poly(xf([(17.0, -2.6), (18.0, -2.2), (18.0, -0.6), (17.0, -0.8)]),
             col=mix(look["accent2"], (255, 255, 255), 0.42))
    pen.poly(xf([(-17.4, -0.2), (-16.4, -0.6), (-16.4, 1.2), (-17.4, 1.0)]),
             col=mix(look["accent"], ink, 0.24))
    tri = _hued(18.0, 0.86, 52.0)
    pen.poly(xf([(-15.4, 5.4), (-11.6, 5.4), (-13.5, 2.0)]),
             col=tri, ink=_edge(look, tri), w=0.22)

    wdeg = phase * 360.0
    for wx, wy in _MF_WHEELS:
        px_, py_ = xf([(wx, wy)])[0]
        _wheel(pen, px_, py_, _MF_R, wdeg, look,
               mix(look["near"], look["sky"], 0.30))
    del s, t


# --- trafficlight ------------------------------------------------------------

#: The lamp order down the head, top to bottom.
_TL_LAMPS = ("red", "amber", "green")

#: One full sequence in seconds, for ``anim="cycle"``.
_TL_CYCLE = ((3.2, "red"), (0.9, "redamber"), (3.4, "green"), (0.9, "amber"))


def _tl_state(phase: float, t: float, anim) -> str:
    """Which lamp is lit. `anim` wins, then `t` if cycling, then `phase`."""
    a = str(anim or "").strip().lower()
    if a in _TL_LAMPS or a == "redamber":
        return a
    if a == "cycle":
        span = sum(d for d, _ in _TL_CYCLE)
        u = float(t) % span
        for d, name in _TL_CYCLE:
            if u < d:
                return name
            u -= d
        return _TL_CYCLE[-1][1]
    return _TL_LAMPS[min(2, max(0, int(float(phase) % 1.0 * 3)))]


def _prop_trafficlight(pen, look, s, phase, t, seed, anim):
    ink = look["ink"]
    metal = mix(ink, look["far"], 0.30)
    edge = _edge(look, metal)
    state = _tl_state(phase, t, anim)
    on = {"red": ("red",), "amber": ("amber",), "green": ("green",),
          "redamber": ("red", "amber")}.get(state, ("red",))

    # Traffic-light red, amber and green are the same everywhere; the palette
    # only decides how bright the night is.
    lit_l = 62.0 if _night(look) else 54.0
    bulbs = {"red": _hued(2.0, 0.90, lit_l),
             "amber": _hued(38.0, 0.92, lit_l + 6.0),
             "green": _hued(138.0, 0.80, lit_l)}

    pen.rrect(-2.6, -2.2, 2.6, 0.0, 0.6, col=shade(metal, 0.82), ink=edge,
              w=0.24)
    pen.poly([(-1.05, -2.0), (1.05, -2.0), (0.78, -21.6), (-0.78, -21.6)],
             col=metal, ink=edge, w=0.22)
    pen.rrect(-1.5, -22.4, 1.5, -21.0, 0.4, col=shade(metal, 0.90))

    back = mix(metal, ink, 0.34)
    pen.rrect(-4.6, -35.4, 4.6, -21.4, 1.3, col=shade(back, 0.88))
    pen.rrect(-3.5, -34.4, 3.5, -22.4, 1.0, col=back, ink=edge, w=0.26)

    for k, name in enumerate(_TL_LAMPS):
        cy = -31.6 + k * 3.9
        base = bulbs[name]
        if name in on:
            pen.circle(0.0, cy, 2.55, col=mix(back, base, 0.30))
            pen.circle(0.0, cy, 2.05, col=mix(back, base, 0.62))
            col = base
        else:
            col = _at_lightness(desaturate(base, 0.55),
                                max(8.0, lightness(base) * 0.30))
        r = 1.72 if name in on else 1.55
        pen.circle(0.0, cy, r, col=col, ink=_edge(look, col), w=0.20)
        if name in on:
            pen.circle(-0.5, cy - 0.5, 0.62, col=tint(base, 0.58))
        # hood
        pen.poly([(-2.05, cy - 0.5), (2.05, cy - 0.5), (2.35, cy - 1.9),
                  (-2.35, cy - 1.9)], col=shade(back, 0.76))
    del s, seed


# --- sandwich ----------------------------------------------------------------


def _prop_sandwich(pen, look, s, phase, t, seed, anim):
    """A triangular sandwich, built to hold a close-up.

    Read as a cut cross-section: bottom slice, filling stack, top slice,
    all clipped to the wedge. Food colours are food colours in any palette —
    the same rule the police lights follow. `look` sets how bright the world
    is, not what bread is.
    """
    day = not _night(look)
    k = 0.0 if day else -8.0
    bread = _hued(38.0, 0.40, 81.0 + k)
    bread2 = _hued(38.0, 0.44, 74.0 + k)
    crust = _hued(26.0, 0.62, 52.0 + k)
    butter = _hued(48.0, 0.62, 87.0 + k)
    ham = _hued(354.0, 0.44, 68.0 + k)
    cheese = _hued(46.0, 0.88, 76.0 + k)
    salad = _hued(114.0, 0.58, 50.0 + k)
    salad2 = _hued(96.0, 0.52, 60.0 + k)
    tomato = _hued(6.0, 0.82, 47.0 + k)

    apex, base_y, half = -16.8, 0.0, 11.6

    def w_at(y):                     # half-width of the wedge at height `y`
        return half * (y - apex) / (base_y - apex)

    def band(y0, y1, col, inset=0.0):
        a0, a1 = max(0.0, w_at(y0) - inset), max(0.0, w_at(y1) - inset)
        if a0 <= 0.02 and a1 <= 0.02:
            return
        pen.poly([(-a0, y0), (a0, y0), (a1, y1), (-a1, y1)], col=col)

    # the wedge itself — this is the top slice; the filling is laid over it
    pen.poly([(0.0, apex), (half, base_y), (-half, base_y)],
             col=bread, ink=_edge(look, bread), w=0.30)

    inset = 1.15
    # bottom slice
    band(base_y - 0.55, -2.9, bread2, inset=inset)
    pen.line([(-(half - inset - 0.4), -2.9), (half - inset - 0.4, -2.9)],
             shade(bread2, 0.86), 0.22)
    # filling stack, bottom up
    band(-2.9, -4.5, ham, inset=inset)
    band(-4.5, -5.6, cheese, inset=inset)

    # tomato slices sit on the cheese, clipped inside the bread
    for cx, cy, r in ((-4.3, -6.4, 1.55), (2.9, -6.5, 1.45)):
        if abs(cx) + r < w_at(cy) - inset - 0.2:
            pen.circle(cx, cy, r, col=tomato)
            pen.circle(cx, cy, r * 0.44, col=tint(tomato, 0.45))

    # salad, scalloped along the top of the stack, never past the bread
    band(-5.6, -6.9, salad, inset=inset)
    for i in range(9):
        cx = -8.0 + i * 2.0
        cy = -6.9 + (0.45 if i % 2 else -0.35)
        r = 1.35 if i % 2 else 1.15
        if abs(cx) + r < w_at(cy) - inset - 0.15:
            pen.circle(cx, cy, r, col=salad if i % 2 else salad2)

    # butter, the thin bright line that says "this is a sandwich"
    band(-7.4, -8.2, butter, inset=inset)

    # crusts: the two edges that were the outside of the loaf
    pen.poly([(0.0, apex), (1.05, apex + 1.6), (half - 1.7, base_y),
              (half, base_y)], col=crust)
    pen.poly([(0.0, apex), (-1.05, apex + 1.6), (-half + 1.7, base_y),
              (-half, base_y)], col=crust)

    # one narrow flat highlight, no gradient
    pen.poly([(-0.35, apex + 2.9), (1.15, apex + 2.9), (2.75, apex + 7.4),
              (1.25, apex + 7.4)], col=tint(bread, 0.30))
    del s, phase, t, seed, anim


# --- indicator ---------------------------------------------------------------

#: Half-period of a car indicator, seconds. 1.5 Hz — the legal rate, and 10
#: clean frames per state at 30 fps.
_INDICATOR = 1.0 / 3.0


def _prop_indicator(pen, look, s, phase, t, seed, anim):
    """A car indicator lamp in close-up, blinking amber on its own clock."""
    a = str(anim or "").strip().lower()
    if a == "on":
        lit = True
    elif a == "off":
        lit = False
    else:
        lit = int(math.floor(float(t) / _INDICATOR)) % 2 == 0

    ink = look["ink"]
    shell = mix(look["near"], ink, 0.28)
    chrome = _at_lightness(desaturate(look["near"], 0.55),
                           min(88.0, lightness(look["near"]) + 12.0))
    amber = _hued(38.0, 0.94, 60.0)
    dark = _hued(34.0, 0.90, 43.0)          # dim, but still plainly amber
    lens = amber if lit else dark

    if lit:
        # ellipses, not rounded rects: a bloom must not read as a second bezel
        bloom = mix(amber, (255, 255, 255), 0.70)
        pen.ellipse(0.0, 0.0, 10.6, 7.6, col=alpha(bloom, 0.18))
        pen.ellipse(0.0, 0.0, 9.1, 6.4, col=alpha(bloom, 0.30))

    pen.rrect(-7.4, -5.2, 7.4, 5.2, 2.0, col=shell,
              ink=_edge(look, shell), w=0.30)
    pen.rrect(-7.0, -4.8, 7.0, 4.8, 1.7, col=chrome)
    pen.rrect(-6.2, -4.1, 6.2, 4.1, 1.3, col=lens,
              ink=_edge(look, lens), w=0.26)

    # lens fluting: flat vertical facets, never a gradient
    face = tint(lens, 0.24) if lit else tint(lens, 0.26)
    for i in range(5):
        fx = -5.0 + i * 2.5
        pen.rect(fx, -3.5, fx + 1.0, 3.5, col=face)
    pen.rect(-5.9, -3.8, 5.9, -3.0, col=face)

    if lit:
        pen.ellipse(-2.9, -1.7, 1.35, 0.85, col=tint(amber, 0.60))
        for k in range(4):
            ang = math.radians(28.0 + k * 90.0)
            x0 = math.cos(ang) * 7.6
            y0 = math.sin(ang) * 5.6
            pen.line([(x0, y0), (x0 * 1.30, y0 * 1.30)],
                     alpha(mix(amber, (255, 255, 255), 0.30), 0.72), 0.60)
    del s, phase, seed


PROPS: dict[str, callable] = {
    "car": _prop_car,
    "policecar": _prop_policecar,
    "helicopter": _prop_helicopter,
    "cone": _prop_cone,
    "bin": _prop_bin,
    "hydrant": _prop_hydrant,
    "lamppost": _prop_lamppost,
    "tree": _prop_tree,
    "building": _prop_building,
    "cloud": _prop_cloud,
    "sign": _prop_sign,
    "milkfloat": _prop_milkfloat,
    "trafficlight": _prop_trafficlight,
    "sandwich": _prop_sandwich,
    "indicator": _prop_indicator,
}


# --------------------------------------------------------------- self test ---

def _sheet_label(im, text: str, look: dict) -> None:
    """Caption a self-test sheet. Test scaffolding only, never artwork."""
    look = _norm(look)
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(max(11, im.size[0] // 68))
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0] + 14, box[3] - box[1] + 10
    d.rectangle([6, 6, 6 + w, 6 + h], fill=mix(look["ink"], look["sky"], 0.14))
    d.text((13, 11 - box[1]), text, font=f,
           fill=mix(look["near"], (255, 255, 255), 0.7))


def _render_set(name, look, *, w=960, h=540, t=0.0, camera=None, seed=7,
                origin=(0.0, 0.0), unit=None, layers=None):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    u = float(unit) if unit else w / SCENE_W
    miss = draw_set(im, name, look, unit=u, origin=origin, t=t,
                    camera=camera or {}, seed=seed, layers=layers)
    return im, miss


def _prop_card(kind, look, *, w=300, h=300, phase=0.0, t=0.0, seed=3,
               anim=None, scale=1.0):
    """One prop, auto-framed, on a flat card with a floor line."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im, "RGBA")
    L = _norm(look)
    d.rectangle([0, 0, w, h], fill=mix(L["sky"], L["near"], 0.30))
    bb = prop_bbox(kind, scale)
    bw, bh = max(1e-3, bb[2] - bb[0]), max(1e-3, bb[3] - bb[1])
    u = min(w / (bw * 1.25), h / (bh * 1.30))
    ax = bb[0] + bw / 2.0
    ay = bb[1] + bh / 2.0
    origin = (ax - w / (2 * u), ay - h / (2 * u))
    if PROP_ANCHOR.get(kind, "ground") != "air":
        gy = int(round((0.0 - origin[1]) * u))
        d.rectangle([0, gy, w, h], fill=L["ground"])
        d.rectangle([0, gy, w, gy + max(1, int(u * 0.16))],
                    fill=shade(L["ground"], 0.86))
    miss = draw_prop(im, kind, look, at=(0.0, 0.0), unit=u, origin=origin,
                     scale=scale, phase=phase, seed=seed, t=t, anim=anim)
    return im, miss


def _grid(cells, cols, pad=8, bg=(18, 20, 24, 255)):
    if not cells:
        return Image.new("RGBA", (2, 2), bg)
    cw = max(c.size[0] for c in cells)
    ch = max(c.size[1] for c in cells)
    rows = (len(cells) + cols - 1) // cols
    im = Image.new("RGBA", (cols * cw + pad * (cols + 1),
                            rows * ch + pad * (rows + 1)), bg)
    for i, c in enumerate(cells):
        r, q = divmod(i, cols)
        im.paste(c, (pad + q * (cw + pad), pad + r * (ch + pad)))
    return im


def _sig(im) -> str:
    import hashlib
    return hashlib.sha256(im.convert("RGBA").tobytes()).hexdigest()[:16]


def _mean(im) -> float:
    """Mean pixel value of a single-channel image. Test scaffolding only."""
    b = im.tobytes()
    return (sum(b) / len(b)) if b else 0.0


def _diff(a, b) -> float:
    """Mean absolute RGB difference, 0..255. Proves a frame really moved."""
    pa, pb = a.convert("RGB").tobytes(), b.convert("RGB").tobytes()
    n = min(len(pa), len(pb))
    if n == 0:
        return 0.0
    step = max(1, n // 90000)
    tot = cnt = 0
    for i in range(0, n, step):
        tot += abs(pa[i] - pb[i])
        cnt += 1
    return tot / max(1, cnt)


def _main(out_dir: str) -> int:
    import os
    import re
    from pathlib import Path
    os.makedirs(out_dir, exist_ok=True)
    fails: list[str] = []

    def ck(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL  {msg}")
        return bool(cond)

    def save(im, fn):
        p = os.path.join(out_dir, fn)
        im.convert("RGB").save(p)
        return p

    P = _look.PALETTES
    print(f"sets.py self-test -> {out_dir}")
    print(f"  sets:  {', '.join(sorted(SETS))}")
    print(f"  props: {', '.join(sorted(PROPS))}")

    # ---- 1. the registries agree with each other -------------------------
    print("\n[1] contract")
    ck(set(PROPS) == set(_BBOX), "PROPS vs _BBOX key mismatch")
    ck(set(PROPS) == set(PROP_ANCHOR), "PROPS vs PROP_ANCHOR key mismatch")
    ck(set(SETS) == set(SET_LAYERS), "SETS vs SET_LAYERS key mismatch")
    for k, anchor in PROP_ANCHOR.items():
        bb = _BBOX[k]
        ck(bb[0] < bb[2] and bb[1] < bb[3], f"{k}: degenerate bbox {bb}")
        if anchor == "ground":
            ck(abs(bb[3]) < 1e-9, f"{k}: ground prop must have y1 == 0")
    for k in PROPS:
        bb1, bb2 = prop_bbox(k, 1.0), prop_bbox(k, 2.0)
        ck(all(abs(a * 2 - b) < 1e-9 for a, b in zip(bb1, bb2)),
           f"{k}: prop_bbox does not scale linearly")
    ck(set(PROP_ANIMS) <= set(PROPS), "PROP_ANIMS names an unknown prop")
    print(f"  {len(SETS)} sets, {len(PROPS)} props, registries agree"
          if not fails else "  see failures above")

    # ---- 2. every set, at a palette that suits it ------------------------
    print("\n[2] sets")
    plan = (("street", "pursuit"), ("suburb", "noon"), ("highway", "heat"),
            ("aerial", "newsroom"), ("office", "office"), ("sky", "noon"))
    for name, pal in plan:
        look = P[pal]
        im, miss = _render_set(name, look, t=1.4, camera={}, seed=11)
        ck(miss is None, f"{name}: unexpected missing marker {miss}")
        _sheet_label(im, f"set '{name}'  palette '{pal}'", look)
        print(f"  {name:9s} {pal:9s} -> {os.path.basename(save(im, f'set-{name}.png'))}")

    # a set must not care which palette it gets
    for name, pal in (("street", "neon"), ("street", "dusk"),
                      ("highway", "country"), ("aerial", "noon"),
                      ("sky", "dusk"), ("office", "newsroom"),
                      ("suburb", "dusk"), ("suburb", "country")):
        im, _ = _render_set(name, P[pal], t=0.6, seed=5)
        _sheet_label(im, f"set '{name}'  palette '{pal}'", P[pal])
        save(im, f"set-{name}-{pal}.png")
    print("  + 8 alternate-palette renders")

    # ...including one nobody named: a derived palette from a raw story
    story = ("a rain-slicked getaway through the old town at dawn, "
             "the thief laughing")
    dl = _look.choose("frantic", story)
    im, _ = _render_set("street", dl, t=0.9, seed=23)
    dn = _look.name_of(dl)
    _sheet_label(im, f"set 'street'  derived '{dn}'", dl)
    save(im, "set-street-derived.png")
    print(f"  derived palette '{dn}' renders cleanly")

    # ---- 3. parallax ------------------------------------------------------
    print("\n[3] parallax")
    look = P["pursuit"]
    cam = {"move": "track", "scroll": 30.0}
    frames = []
    for t in (0.0, 1.0, 2.0):
        im, _ = _render_set("street", look, t=t, camera=cam, seed=11)
        _sheet_label(im, f"street  scroll 30 u/s  t={t:.1f}s", look)
        frames.append(im)
        save(im, f"parallax-street-t{t:.1f}.png")
    ck(_diff(frames[0], frames[1]) > 2.0, "parallax: nothing moved")

    # The exact test. A layer with factor k, after `dt` seconds of a
    # `scroll` camera, must be *identical* to the same layer drawn with no
    # camera at all from an origin moved by k * scroll * dt. Comparing raw
    # frame-to-frame deltas cannot do this: a busy far layer changes more
    # pixels moving 4 units than flat asphalt does moving 30.
    #
    # (Ordering is asserted on the arithmetic, which `layer_origins`
    # exposes, and equivalence is then asserted on the pixels.)
    dt, sc = 1.0, 30.0
    lo = layer_origins("street", unit=960 / SCENE_W, origin=(0.0, 0.0),
                       size_px=(960, 540), t=dt, camera=cam, seed=11)
    ck(sorted(lo) == sorted(dict(SET_LAYERS["street"])),
       "layer_origins does not cover the street stack")
    for lname, k in SET_LAYERS["street"]:
        want = k * sc * dt
        got = lo[lname][1][0]
        ck(abs(got - want) < 1e-9,
           f"{lname}: parallax origin {got:.4f}, expected {want:.4f}")
    shifts = [lo[n][1][0] for n, _ in SET_LAYERS["street"]]
    ck(all(b > a for a, b in zip(shifts, shifts[1:])),
       "layers must travel strictly further as they come forward")

    for lname, k in SET_LAYERS["street"]:
        a, _ = _render_set("street", look, t=dt, camera=cam, seed=11,
                           layers=[lname])
        b, _ = _render_set("street", look, t=0.0, camera={}, seed=11,
                           layers=[lname], origin=(k * sc * dt, 0.0))
        dv = _diff(a, b)
        ck(dv < 0.6, f"{lname}: k={k} does not move at k x camera ({dv:.2f})")
        print(f"  {lname:11s} k={k:4.2f}  travels {k * sc * dt:6.2f}u  "
              f"residual {dv:.3f}")

    # ...and a layer must not be pinned when it should move, or the test
    # above would pass trivially on a set that never moves anything.
    for lname, k in SET_LAYERS["street"]:
        a, _ = _render_set("street", look, t=0.0, camera=cam, seed=11,
                           layers=[lname])
        b, _ = _render_set("street", look, t=dt, camera=cam, seed=11,
                           layers=[lname])
        moved = _diff(a, b) > 0.25
        ck(moved == (k > 0.0), f"{lname}: k={k} but moved={moved}")
    save(_grid([f.resize((480, 270), Image.LANCZOS) for f in frames], 1),
         "parallax-street-strip.png")

    # the suburb runs the same stack, so it gets the same proof
    for lname, k in SET_LAYERS["suburb"]:
        a, _ = _render_set("suburb", P["noon"], t=dt, camera=cam, seed=17,
                           layers=[lname])
        b, _ = _render_set("suburb", P["noon"], t=0.0, camera={}, seed=17,
                           layers=[lname], origin=(k * sc * dt, 0.0))
        dv = _diff(a, b)
        ck(dv < 0.6, f"suburb/{lname}: k={k} does not track the camera "
                     f"({dv:.2f})")
    print("  suburb: all 7 layers track the camera at their own rate")

    # aerial drifts diagonally instead
    ad = [_render_set("aerial", P["newsroom"], t=t,
                      camera={"move": "drift", "scroll": (7.0, 4.0)},
                      seed=4)[0] for t in (0.0, 1.5, 3.0)]
    ck(_diff(ad[0], ad[2]) > 2.0, "aerial drift did not move")
    for i, im in enumerate(ad):
        _sheet_label(im, f"aerial  drift  t={i * 1.5:.1f}s", P["newsroom"])
        save(im, f"parallax-aerial-t{i * 15:02d}.png")
    print(f"  aerial drift delta {_diff(ad[0], ad[2]):.2f}")

    # the four canonical rates, and enough layers to actually read as depth
    scrolling = ("street", "suburb", "highway", "office", "sky")
    for nm in scrolling:
        ks = [k for _, k in SET_LAYERS[nm]]
        ck(len(ks) >= 3, f"{nm} has only {len(ks)} layers, want >= 3")
        ck(ks == sorted(ks), f"{nm} layers are not ordered back to front")
        for want in ("far", "mid", "character"):
            ck(any(abs(k - PARALLAX[want]) < 1e-9 for k in ks),
               f"{nm} has no {want} layer at k={PARALLAX[want]}")
    for nm in ("street", "suburb", "highway", "sky"):
        ck(any(abs(k - PARALLAX["foreground"]) < 1e-9
               for _, k in SET_LAYERS[nm]),
           f"{nm} has no foreground layer at k={PARALLAX['foreground']}")
    print("  canonical rates far 0.18 / mid 0.50 / character 1.00 / fg 1.50"
          f" present in {', '.join(scrolling)}")

    # ---- 3b. stroke weight by depth ---------------------------------------
    print("\n[3b] stroke weight")
    bands = ("far", "mid", "character", "foreground")
    for a, b in zip(bands, bands[1:]):
        ck(stroke_w(a) < stroke_w(b), f"stroke {a} is not lighter than {b}")
    for nm in bands:
        w = stroke_w(nm) * REF_UNIT
        ck(1.4 <= w <= 4.0, f"stroke {nm} is {w:.2f}px, want 1.5-4")
    for k, want in ((0.00, "far"), (0.18, "far"), (0.50, "mid"),
                    (0.74, "character"), (1.00, "character"),
                    (1.50, "foreground")):
        got = _stroke_band(k)
        ck(got == want, f"layer k={k} draws {got} weight, want {want}")
    # and the pen really carries it: a far layer's line is thinner in pixels
    probe = {}
    for nm, k in (("far", 0.18), ("near", 1.00), ("fore", 1.50)):
        pn = _Pen(ImageDraw.Draw(Image.new("RGBA", (8, 8))), REF_UNIT,
                  (0, 0), (8, 8),
                  stroke=STROKE_PX[_stroke_band(k)] / STROKE_PX["character"])
        probe[nm] = pn.px(stroke_w("character"))
    ck(probe["far"] < probe["near"] < probe["fore"],
       f"pen stroke does not thin with depth: {probe}")
    print("  reference px  " + "  ".join(
        f"{n}={stroke_w(n) * REF_UNIT:.1f}" for n in bands)
        + f"   pen check {probe}")

    # ---- 3c. the one permitted gradient -----------------------------------
    print("\n[3c] sky gradient")
    for nm in ("street", "suburb", "highway", "sky"):
        im, _ = _render_set(nm, P["noon"], seed=4, layers=["sky"])
        col = [im.getpixel((im.size[0] // 2, y))[:3]
               for y in range(2, int(im.size[1] * 0.55), 3)]
        ck(len(set(col)) >= 6,
           f"{nm} sky is flat, not a 2-stop gradient ({len(set(col))} steps)")
        ls = [lightness(c) for c in col]
        drops = sum(1 for a, b in zip(ls, ls[1:]) if b < a - 0.02)
        ck(drops <= 1,
           f"{nm} sky ramp is not monotone ({drops} reversals)")
        ck(abs(ls[0] - ls[-1]) >= 1.5,
           f"{nm} sky ramp spans only {abs(ls[0] - ls[-1]):.2f} L*")
        print(f"  {nm:8s} sky ramps {ls[0]:.1f} -> {ls[-1]:.1f} L* over "
              f"{len(set(col))} steps")
    # everything else stays flat: a prop fill is one colour, not a ramp
    # everything that is not the sky stays flat. A flat-vector image is a
    # handful of colours plus antialiasing; a ramp is a long tail.
    def _top8(im):
        cols = im.convert("RGB").getcolors(maxcolors=1 << 22) or []
        cols.sort(reverse=True)
        return sum(n for n, _ in cols[:8]) / max(1, sum(n for n, _ in cols))

    for kind in sorted(PROPS):
        card, _ = _prop_card(kind, P["noon"], seed=3)
        sh = _top8(card)
        ck(sh >= 0.55, f"prop {kind} is not flat colour: 8 colours cover "
                       f"only {sh:.0%} of the card")
    print("  every prop card is >= 55% its 8 commonest colours (flat fill); "
          f"the sky layer is {_top8(_render_set('street', P['noon'], seed=4, layers=['sky'])[0]):.0%}")
    # and structurally: `vgrad` is the only gradient primitive, and it is
    # only ever called on a layer named "sky".
    src = Path(__file__).read_text(encoding="utf-8").splitlines()
    calls = [i for i, ln in enumerate(src)
             if re.match(r"\s*p\.vgrad\(", ln)]
    ck(len(calls) >= 4, f"expected 4 sky gradients, found {len(calls)}")
    for i in calls:
        ctx = "\n".join(src[max(0, i - 4):i])
        ck('st.layer("sky")' in ctx,
           f"line {i + 1}: vgrad outside a sky layer -- gradients are "
           f"permitted in the sky and nowhere else")
    print(f"  vgrad appears {len(calls)} times, every one inside a sky layer")

    # ---- 3d. contact shadow ------------------------------------------------
    print("\n[3d] contact shadow")
    lo, hi = _look.SHADOW_OPACITY_RANGE
    ck(lo <= SHADOW_OPACITY <= hi,
       f"SHADOW_OPACITY {SHADOW_OPACITY} outside {lo}-{hi}")
    lkp = P["pursuit"]
    for span, hgt in ((6.0, 18.0), (44.0, 16.6), (3.0, 7.0)):
        base = Image.new("RGBA", (240, 90), tuple(lkp["ground"]) + (255,))
        contact_shadow(base, lkp, at=(12.0, 6.6), unit=5.0, origin=(0.0, 0.0),
                       foot_span=span, height=hgt)
        px = base.load()
        c0 = px[60, 33][:3]
        ck(c0 != tuple(lkp["ground"]), "contact shadow drew nothing")
        drop = lightness(lkp["ground"]) - lightness(c0)
        ck(2.0 <= drop <= 26.0,
           f"contact shadow darkens by {drop:.1f} L*, want a soft 2-26")
        a, b = _shadow_axes(span, hgt)
        print(f"  span {span:5.1f} h {hgt:5.1f} -> a={a:5.2f} b={b:4.2f} "
              f"@ {SHADOW_OPACITY:.0%}  ground drops {drop:.1f} L*")
    # a prop and a character of the same footprint must agree
    solo = Image.new("RGBA", (240, 90), tuple(lkp["ground"]) + (255,))
    contact_shadow(solo, lkp, at=(12.0, 6.6), unit=5.0, origin=(0.0, 0.0),
                   foot_span=44.0, height=16.6)
    solo2 = Image.new("RGBA", (240, 90), tuple(lkp["ground"]) + (255,))
    contact_shadow(solo2, lkp, at=(12.0, 6.6), unit=5.0, origin=(0.0, 0.0),
                   foot_span=44.0, height=16.6)
    ck(_diff(solo, solo2) == 0.0, "contact_shadow is not reproducible")

    # ---- 3e. no pure-black ink --------------------------------------------
    print("\n[3e] ink")
    for nm, pal in P.items():
        ck(tuple(pal["ink"]) != (0, 0, 0), f"{nm}: ink is pure black")
    for fill_name in ("accent", "accent2", "shirt", "far"):
        f = P["pursuit"][fill_name]
        e = outline_for(f)
        ck(lightness(e) < lightness(f) or lightness(f) < 6.0,
           f"outline_for({fill_name}) is not darker than its fill")
    print("  no palette inks pure black; outlines derive from their own fill")

    # ---- 4. props ---------------------------------------------------------
    print("\n[4] props")
    look = P["pursuit"]
    cards = []
    # a catalogue sheet should show a lamp doing its job, so the props whose
    # look depends on their own clock get a `t` that lands on the lit beat
    lit_t = {"indicator": 0.10, "trafficlight": 0.4, "policecar": 0.10}
    for kind in sorted(PROPS):
        im, miss = _prop_card(kind, look, seed=9, phase=0.12,
                              t=lit_t.get(kind, 0.35))
        ck(miss is None, f"prop {kind}: unexpected missing marker")
        _sheet_label(im, kind, look)
        cards.append(im)
    save(_grid(cards, 4), "props-all.png")
    print(f"  {len(cards)} prop cards -> props-all.png")

    # ---- 5. things that must actually move -------------------------------
    print("\n[5] motion")

    # NB: signatures are always taken *before* labelling, or the caption
    # text alone would make every frame look different.
    phs = (0.0, 0.25, 0.5, 0.75)

    wheels = [_prop_card("car", look, phase=p, seed=2)[0] for p in phs]
    ws = [_sig(w) for w in wheels]
    ck(len(set(ws)) == 4, f"car wheels do not turn with phase: {ws}")
    for im, p in zip(wheels, phs):
        _sheet_label(im, f"car  phase={p:.2f}", look)
    save(_grid(wheels, 4), "motion-car-wheels.png")
    print(f"  car wheel frames distinct: {len(set(ws))}/4")

    bounce = [_prop_card("car", look, phase=p, seed=2, anim="bounce")[0]
              for p in phs]
    bs = [_sig(b) for b in bounce]
    bdiff = _diff(wheels[1], bounce[1])
    ck(len(set(bs)) == 4, "car bounce is not animating")
    ck(bdiff > 0.5, "anim='bounce' changed nothing")
    for im, p in zip(bounce, phs):
        _sheet_label(im, f"car  anim=bounce  phase={p:.2f}", look)
    save(_grid(bounce, 4), "motion-car-bounce.png")
    print(f"  bounce differs from idle by {bdiff:.2f}")

    # the milk float: same wheel and same bounce contract as the car
    mf = [_prop_card("milkfloat", look, phase=p, seed=2)[0] for p in phs]
    ms = [_sig(m) for m in mf]
    ck(len(set(ms)) == 4, f"milkfloat wheels do not turn with phase: {ms}")
    mfb = [_prop_card("milkfloat", look, phase=p, seed=2, anim="bounce")[0]
           for p in phs]
    mbd = _diff(mf[1], mfb[1])
    ck(len(set(_sig(x) for x in mfb)) == 4, "milkfloat bounce is not moving")
    ck(mbd > 0.5, "milkfloat anim='bounce' changed nothing")
    for im, p in zip(mf, phs):
        _sheet_label(im, f"milkfloat  phase={p:.2f}", look)
    for im, p in zip(mfb, phs):
        _sheet_label(im, f"milkfloat  anim=bounce  phase={p:.2f}", look)
    save(_grid(mf + mfb, 4), "motion-milkfloat.png")
    # it shares the car's silhouette language but is not the same shape:
    # boxier (taller for its length) and on visibly smaller wheels
    cb, mb = prop_bbox("car"), prop_bbox("milkfloat")
    car_ar = (cb[3] - cb[1]) / (cb[2] - cb[0])
    mf_ar = (mb[3] - mb[1]) / (mb[2] - mb[0])
    ck(mf_ar > car_ar * 1.25,
       f"milkfloat is not boxier than the car ({mf_ar:.2f} vs {car_ar:.2f})")
    ck(_MF_R < _CAR_R, "milkfloat wheels are not smaller than the car's")
    ck((mb[2] - mb[0]) < (cb[2] - cb[0]), "milkfloat is not shorter")
    print(f"  milkfloat: wheels turn, bounce differs by {mbd:.2f}; "
          f"height/length {mf_ar:.2f} vs car {car_ar:.2f}, "
          f"wheel r {_MF_R} vs {_CAR_R}")

    # the traffic light: red and green must be unmistakable, both ways in
    tl_named = {n: _prop_card("trafficlight", look, seed=2, anim=n)[0]
                for n in ("red", "amber", "green")}
    ck(len({_sig(v) for v in tl_named.values()}) == 3,
       "traffic light states are not distinct")
    tl_phase = {n: _prop_card("trafficlight", look, seed=2,
                              phase=ph)[0]
                for n, ph in (("red", 0.1), ("amber", 0.5), ("green", 0.9))}
    for n in ("red", "amber", "green"):
        ck(_diff(tl_named[n], tl_phase[n]) < 0.01,
           f"trafficlight: phase and anim disagree about {n}")
    # ...and it is the *right* lamp: find the pixels wearing each bulb's
    # colour and check they sit where that lamp is, top to bottom.
    lit_l = 62.0 if _night(look) else 54.0
    want = {"red": _hued(2.0, 0.90, lit_l),
            "amber": _hued(38.0, 0.92, lit_l + 6.0),
            "green": _hued(138.0, 0.80, lit_l)}

    def _lamp_y(im, col):
        px = im.convert("RGB").load()
        w_, h_ = im.size
        ys, n = 0.0, 0
        for y in range(h_):
            for x in range(0, w_, 2):
                r, g, bl = px[x, y]
                if (abs(r - col[0]) + abs(g - col[1]) + abs(bl - col[2])) < 30:
                    ys += y
                    n += 1
        return (ys / n, n) if n else (None, 0)

    heads = {}
    for n in ("red", "amber", "green"):
        y, cnt = _lamp_y(tl_named[n], want[n])
        ck(cnt > 40, f"trafficlight {n}: lit lamp is not on screen ({cnt}px)")
        heads[n] = None if y is None else round(y, 1)
    ck(heads["red"] is not None and heads["amber"] is not None
       and heads["green"] is not None, f"lamp not found: {heads}")
    ck(heads["red"] < heads["amber"] < heads["green"],
       f"the lamps are lit in the wrong order down the head: {heads}")
    # and a lamp that is off must not be wearing its lit colour
    for n, other in (("red", "green"), ("green", "red")):
        _, cnt = _lamp_y(tl_named[other], want[n])
        ck(cnt < 12,
           f"trafficlight shows {n} while set to {other} ({cnt}px)")
    cyc = [_sig(_prop_card("trafficlight", look, seed=2, t=tt,
                           anim="cycle")[0]) for tt in (0.5, 3.5, 5.0, 7.9)]
    ck(len(set(cyc)) == 4, "anim='cycle' does not run through the sequence")
    for n in ("red", "amber", "green"):
        _sheet_label(tl_named[n], f"trafficlight  {n}", look)
    save(_grid([tl_named[n] for n in ("red", "amber", "green")], 3),
         "motion-trafficlight.png")
    print(f"  trafficlight: red/amber/green distinct and unmistakable, "
          f"lit-lamp centroid y {heads}")

    # the indicator: amber, blinking on `t` at the legal rate
    ihz = 1.0 / (2.0 * _INDICATOR)
    ck(1.0 <= ihz <= 2.0, f"indicator blinks at {ihz:.2f} Hz, want 1-2")
    ck(_INDICATOR * FPS >= 6.0,
       f"indicator holds only {_INDICATOR * FPS:.1f} frames at {FPS} fps")
    its = tuple(_INDICATOR * (i + 0.5) for i in range(4))
    ind = [_prop_card("indicator", look, seed=2, t=tt)[0] for tt in its]
    isg = [_sig(x) for x in ind]
    ck(isg[0] != isg[1], "indicator does not blink")
    ck(isg[0] == isg[2] and isg[1] == isg[3], "indicator is not 2-state")
    ck(_mean(ind[0].convert("L")) > _mean(ind[1].convert("L")),
       "indicator: the 'on' frame is not the brighter one")
    ck(_diff(_prop_card("indicator", look, seed=2, anim="on")[0], ind[0])
       < 0.01, "indicator anim='on' does not match its lit frame")
    for im, tt in zip(ind, its):
        _sheet_label(im, f"indicator  t={tt:.2f}s", look)
    save(_grid(ind, 4), "motion-indicator.png")
    print(f"  indicator blinks at {ihz:.2f} Hz "
          f"({_INDICATOR * FPS:.1f} frames per state at {FPS} fps)")

    # the sandwich has to survive a close-up
    big = _prop_card("sandwich", look, w=520, h=520, seed=2, scale=2.4)[0]
    small = _prop_card("sandwich", look, seed=2, scale=0.5)[0]
    ck(_mean(big.convert("L")) > 1.0, "sandwich rendered blank")
    _sheet_label(big, "sandwich  close-up  scale=2.4", look)
    save(big, "motion-sandwich-closeup.png")
    del small

    hz = 1.0 / (2.0 * _LIGHTBAR)
    ck(1.5 <= hz <= 2.0, f"light bar runs at {hz:.2f} Hz, want 1.5-2.0")
    ck(_LIGHTBAR * FPS >= 6.0,
       f"light bar holds only {_LIGHTBAR * FPS:.1f} frames at {FPS} fps")
    lts = tuple(_LIGHTBAR * (i + 0.5) for i in range(4))
    lights = [_prop_card("policecar", look, phase=0.1, t=tt, seed=2)[0]
              for tt in lts]
    ls = [_sig(x) for x in lights]
    ck(ls[0] != ls[1], "light bar does not alternate")
    ck(ls[0] == ls[2] and ls[1] == ls[3], "light bar is not 2-state")
    for im, tt in zip(lights, lts):
        _sheet_label(im, f"policecar  t={tt:.2f}s", look)
    save(_grid(lights, 4), "motion-policecar-lightbar.png")
    print(f"  light bar alternates on t at {hz:.2f} Hz "
          f"({_LIGHTBAR * FPS:.1f} frames per state at {FPS} fps)")

    rts = (0.0, 0.12, 0.24, 0.36)
    rot = [_prop_card("helicopter", P["newsroom"], phase=0.0, t=tt, seed=2)[0]
           for tt in rts]
    rs = [_sig(r) for r in rot]
    ck(len(set(rs)) == 4, "rotor does not spin with t")
    for im, tt in zip(rot, rts):
        _sheet_label(im, f"helicopter  t={tt:.2f}s", P["newsroom"])
    save(_grid(rot, 2), "motion-helicopter-rotor.png")
    print(f"  rotor frames distinct: {len(set(rs))}/4")

    # scale must actually scale, measured on the ink rather than assumed
    scs = (0.35, 0.7, 1.0)
    widths = []
    for x in scs:
        t_im = Image.new("RGBA", (900, 400), (0, 0, 0, 0))
        draw_prop(t_im, "car", look, at=(22.0, 20.0), unit=9.0,
                  origin=(0.0, 0.0), scale=x, phase=0.3, seed=2,
                  shadow=False)
        bx = t_im.getbbox()
        widths.append((bx[2] - bx[0]) if bx else 0)
    for a, b, ra in zip(widths, widths[1:], (scs[1] / scs[0], scs[2] / scs[1])):
        ck(abs(b / max(1, a) - ra) < 0.06,
           f"scale is not linear in the drawing: {widths} for {scs}")
    band = Image.new("RGBA", (900, 400), (0, 0, 0, 255))
    ImageDraw.Draw(band).rectangle([0, 0, 900, 400],
                                   fill=mix(look["sky"], look["near"], 0.30))
    ImageDraw.Draw(band).rectangle([0, 270, 900, 400], fill=look["ground"])
    for i, x in enumerate(scs):
        draw_prop(band, "car", look, at=(16.0 + i * 34.0, 30.0 - 8.0 * x),
                  unit=9.0, origin=(0.0, 0.0), scale=x, phase=0.3, seed=2)
    _sheet_label(band, f"car  scale {scs}  ink widths {widths}px", look)
    save(band, "motion-car-scale.png")
    print(f"  car ink width by scale {scs} -> {widths} px")

    # ---- 6. props on a set, which is the only test that matters ----------
    print("\n[6] composite")
    look = P["pursuit"]
    im, _ = _render_set("street", look, t=1.1, camera={"scroll": 30.0},
                        seed=11)
    u = 960 / SCENE_W
    for kind, at, sca, ph, an in (
            ("lamppost", (16.0, 44.0), 0.66, 0.0, None),
            ("tree", (88.0, 44.0), 0.70, 0.0, None),
            ("bin", (32.0, 44.0), 0.62, 0.0, None),
            ("hydrant", (70.0, 44.0), 0.72, 0.0, None),
            ("sign", (6.0, 44.0), 0.60, 0.0, None),
            ("cone", (86.0, 52.6), 0.75, 0.0, None),
            ("policecar", (20.0, 49.2), 0.66, 0.62, "bounce"),
            ("car", (63.0, 49.6), 0.72, 0.31, "bounce")):
        draw_prop(im, kind, look, at=at, unit=u, origin=(0.0, 0.0),
                  scale=sca, phase=ph, seed=13, t=1.1, anim=an)
    draw_prop(im, "helicopter", look, at=(72.0, 12.0), unit=u,
              origin=(0.0, 0.0), scale=0.34, phase=0.0, seed=13, t=1.1)
    _sheet_label(im, "composite: street + props, pursuit", look)
    save(im, "composite-chase.png")
    print("  composite-chase.png")

    im2, _ = _render_set("office", P["office"], t=0.4, seed=6)
    for kind, at, sca in (("bin", (12.0, 44.0), 0.55),
                          ("sign", (63.5, 43.6), 0.38)):
        draw_prop(im2, kind, P["office"], at=at, unit=960 / SCENE_W,
                  origin=(0.0, 0.0), scale=sca, seed=2)
    _sheet_label(im2, "composite: office + props", P["office"])
    save(im2, "composite-office.png")

    im3, _ = _render_set("sky", P["newsroom"], t=0.5, seed=8)
    draw_prop(im3, "helicopter", P["newsroom"], at=(48.0, 26.0),
              unit=960 / SCENE_W, origin=(0.0, 0.0), scale=0.9, seed=1,
              t=0.5, anim="bob")
    _sheet_label(im3, "composite: sky + helicopter", P["newsroom"])
    save(im3, "composite-chopper.png")
    print("  composite-office.png, composite-chopper.png")

    # the sample film's last shot: the getaway vehicle arrives home
    im4, _ = _render_set("suburb", P["noon"], t=2.0,
                         camera={"scroll": 14.0}, seed=5)
    for kind, at, sca, ph, an, tt in (
            ("trafficlight", (80.0, 44.0), 0.85, 0.0, "green", 2.0),
            ("bin", (13.0, 44.0), 0.50, 0.0, None, 2.0),
            ("milkfloat", (44.0, 48.4), 0.62, 0.42, "bounce", 2.0),
            ("indicator", (54.6, 47.4), 0.12, 0.0, "on", 2.0)):
        draw_prop(im4, kind, P["noon"], at=at, unit=u, origin=(0.0, 0.0),
                  scale=sca, phase=ph, seed=17, t=tt, anim=an)
    _sheet_label(im4, "composite: suburb + milk float, noon", P["noon"])
    save(im4, "composite-suburb.png")

    # and the close-up the board asks for
    im5, _ = _render_set("suburb", P["noon"], t=0.0, seed=5)
    draw_prop(im5, "sandwich", P["noon"], at=(38.0, 30.0), unit=u,
              origin=(0.0, 0.0), scale=1.5, seed=4)
    draw_prop(im5, "indicator", P["noon"], at=(72.0, 30.0), unit=u,
              origin=(0.0, 0.0), scale=1.3, seed=4, t=0.1)
    _sheet_label(im5, "composite: close-ups at scale", P["noon"])
    save(im5, "composite-closeups.png")
    print("  composite-suburb.png, composite-closeups.png")

    # ---- 7. never invent a picture ---------------------------------------
    print("\n[7] missing")
    clear_missing()
    im = Image.new("RGBA", (640, 360), (0, 0, 0, 255))
    m1 = draw_set(im, "alleyway", P["noon"], unit=6.4, origin=(0.0, 0.0),
                  t=0.0, camera={}, seed=1)
    m2 = draw_prop(im, "unicycle", P["noon"], at=(50.0, 40.0), unit=6.4,
                   origin=(0.0, 0.0))
    ck(bool(m1) and m1.get("missing"), "unknown set returned no marker")
    ck(bool(m2) and m2.get("missing"), "unknown prop returned no marker")
    ck(("set", "alleyway") in MISSING, "MISSING did not record the set")
    ck(("prop", "unicycle") in MISSING, "MISSING did not record the prop")
    ck(m1.get("have") == sorted(SETS), "marker should list what does exist")
    save(im, "missing-placeholder.png")
    print(f"  MISSING = {sorted(MISSING)}")
    clear_missing()

    # ---- 8. determinism ---------------------------------------------------
    print("\n[8] determinism")
    for name, pal in plan:
        a, _ = _render_set(name, P[pal], t=1.37, camera={"scroll": 12.0},
                           seed=99, w=480, h=270)
        b, _ = _render_set(name, P[pal], t=1.37, camera={"scroll": 12.0},
                           seed=99, w=480, h=270)
        ck(_sig(a) == _sig(b), f"{name}: not deterministic")
    for kind in sorted(PROPS):
        a, _ = _prop_card(kind, P["dusk"], phase=0.41, t=0.83, seed=77)
        b, _ = _prop_card(kind, P["dusk"], phase=0.41, t=0.83, seed=77)
        ck(_sig(a) == _sig(b), f"prop {kind}: not deterministic")
    # ...and seed must actually do something
    s1, _ = _render_set("street", P["noon"], t=0.0, seed=1)
    s2, _ = _render_set("street", P["noon"], t=0.0, seed=2)
    ck(_sig(s1) != _sig(s2), "seed had no effect on the street")
    print("  all sets and props reproduce bit-for-bit; seed varies the world")

    # ---- 9. a partial palette must not crash anything --------------------
    print("\n[9] robustness")
    thin = {"sky": (150, 190, 220), "ink": (20, 20, 24),
            "accent": (220, 60, 60)}
    for name in sorted(SETS):
        im, miss = _render_set(name, thin, w=320, h=180, t=0.3, seed=3)
        ck(miss is None, f"{name}: broke on a 3-key palette")
    for kind in sorted(PROPS):
        _prop_card(kind, thin, w=160, h=160)
    for cam in ({}, None, {"move": "handheld"}, {"move": "push", "zoom": 1.4},
                {"from": [10, 20], "to": [80, 30], "ease": "inout"},
                {"cx": 60.0, "cy": 30.0, "base_cx": 50.0, "base_cy": 28.0},
                {"dx": -18.0, "dy": 3.0}, {"scroll": "nonsense"},
                {"scroll": [4, "x"]}):
        im, miss = _render_set("street", P["noon"], w=320, h=180, t=0.7,
                               camera=cam, seed=3)
        ck(miss is None, f"camera {cam!r} broke draw_set")
    ck(prop_bbox("nope") == prop_bbox("nope", 1.0), "unknown bbox unstable")
    print("  survives thin palettes, odd cameras and junk scroll values")

    # ---- 10. the renderer's own call, on every name in the catalogue -----
    #
    # Sections 2 and 4 draw through this file's own helpers, which is exactly
    # how a set can be green here and raise inside render.py. So this section
    # rebuilds `render.py`'s call by hand — the full camera dict it assembles
    # from `View.as_dict()` plus the shot fields, an RGBA frame at film size,
    # `t` and `anim` and `shadow` keywords included — and walks every key in
    # SET_LAYERS and PROP_ANCHOR. Nothing may raise, nothing may report
    # itself missing, and no frame may come back with a hole in it.
    print("\n[10] renderer contract")

    def _render_camera(move, cx, cy, w, h, dx, dy, on):
        """Byte-for-byte the dict `render.py::_camera_dict` hands over."""
        return {"cx": cx, "cy": cy, "zoom": 1.0, "w": w, "h": h,
                "x0": cx - w / 2.0, "y0": cy - h / 2.0, "blur": 0.0,
                "move": move, "shot": "s1",
                "base_cx": cx - dx, "base_cy": cy - dy,
                "dx": dx, "dy": dy,
                "scene_w": SCENE_W, "scene_h": SCENE_H,
                "parallax": {"fore": 1.5, "char": 1.0, "mid": 0.5,
                             "far": 0.18},
                "min_layers": 3, "still": False, "on": on}

    FW, FH = 480, 270
    cams = [
        _render_camera("none", 50.0, 28.125, 100.0, 56.25, 0.0, 0.0, 2),
        _render_camera("track", 62.0, 28.125, 100.0, 56.25, 12.0, 0.0, 3),
        _render_camera("push", 50.0, 26.0, 74.0, 41.6, -4.0, -2.1, 1),
        _render_camera("handheld", 44.0, 30.0, 100.0, 56.25, -6.0, 1.9, 3),
        _render_camera("whip", 50.0, 28.125, 100.0, 56.25, 38.0, 0.0, 2),
    ]
    set_calls = 0
    for name in sorted(SET_LAYERS):
        for cam in cams:
            for tl in (0.0, 1.37):
                frame = Image.new("RGBA", (FW, FH), (0, 0, 0, 255))
                view_w = float(cam["w"])
                try:
                    miss = draw_set(frame, name, P["pursuit"],
                                    unit=FW / view_w,
                                    origin=(cam["x0"], cam["y0"]), t=tl,
                                    camera=cam, seed=0x51 ^ hash(name) & 0xFFFF)
                except Exception as exc:                 # noqa: BLE001
                    ck(False, f"draw_set({name!r}) raised "
                              f"{type(exc).__name__}: {exc}")
                    continue
                set_calls += 1
                ck(miss is None,
                   f"draw_set({name!r}) reported itself missing")
                ck(frame.getchannel("A").getextrema()[0] == 255,
                   f"draw_set({name!r}, move={cam['move']}) left a "
                   "translucent hole in the frame")
    print(f"  draw_set: {len(SET_LAYERS)} sets x {len(cams)} cameras x 2 "
          f"times = {set_calls} calls, none raised, every frame opaque")

    # every prop, every declared anim, through the renderer's keyword set
    prop_calls = 0
    for kind in sorted(PROP_ANCHOR):
        anims = (None,) + tuple(PROP_ANIMS.get(kind, ()))
        for an in anims:
            for tl, ph, sca in ((0.0, 0.0, 1.0), (1.37, 0.42, 0.35),
                                (2.61, 0.86, 2.2)):
                frame = Image.new("RGBA", (FW, FH), (0, 0, 0, 255))
                kw = {"t": tl, "shadow": False}
                if an:
                    kw["anim"] = an
                try:
                    miss = draw_prop(frame, kind, P["pursuit"],
                                     at=(50.0, 44.0), unit=FW / SCENE_W,
                                     origin=(0.0, 0.0), scale=sca, phase=ph,
                                     seed=0x33 ^ (hash(kind) & 0x7FFFFFFF),
                                     **kw)
                except Exception as exc:                 # noqa: BLE001
                    ck(False, f"draw_prop({kind!r}, anim={an!r}) raised "
                              f"{type(exc).__name__}: {exc}")
                    continue
                prop_calls += 1
                ck(miss is None,
                   f"draw_prop({kind!r}) reported itself missing")
    print(f"  draw_prop: {len(PROP_ANCHOR)} props x every declared anim x 3 "
          f"scales = {prop_calls} calls, none raised")

    # the contact-sheet call, which passes the bare view dict and no shot
    for name in sorted(SET_LAYERS):
        half = Image.new("RGBA", (FW // 2, FH // 2), (0, 0, 0, 255))
        try:
            draw_set(half, name, P["noon"], unit=(FW // 2) / SCENE_W,
                     origin=(0.0, 0.0), t=0.5,
                     camera={"cx": 50.0, "cy": 28.125, "zoom": 1.0,
                             "w": 100.0, "h": 56.25, "x0": 0.0, "y0": 0.0,
                             "blur": 0.0},
                     seed=7)
        except Exception as exc:                         # noqa: BLE001
            ck(False, f"contact-sheet draw_set({name!r}) raised "
                      f"{type(exc).__name__}: {exc}")
    print(f"  contact sheet: {len(SET_LAYERS)} sets through the bare view "
          "dict, none raised")

    # and the two catalogues the renderer introspects must agree with the
    # two it actually calls, or this whole section proves nothing
    ck(set(SET_LAYERS) == set(SETS),
       f"SET_LAYERS != SETS: {set(SET_LAYERS) ^ set(SETS)}")
    # SET_GROUND is load-bearing for composition, not just placement: a shot
    # that cannot find the ground line frames its zoom on the middle of the
    # scene, puts the camera in the sky and crops the cast out of frame.
    ck(set(SET_LAYERS) == set(SET_GROUND),
       f"SET_LAYERS != SET_GROUND: {set(SET_LAYERS) ^ set(SET_GROUND)}")
    ck(set(PROP_ANCHOR) == set(PROPS),
       f"PROP_ANCHOR != PROPS: {set(PROP_ANCHOR) ^ set(PROPS)}")
    ck(set(_BBOX) == set(PROPS),
       f"_BBOX != PROPS: {set(_BBOX) ^ set(PROPS)}")
    ck(set(PROP_ANIMS) <= set(PROPS),
       f"PROP_ANIMS names a prop that does not exist: "
       f"{set(PROP_ANIMS) - set(PROPS)}")
    for nm, stack in SET_LAYERS.items():
        rs = [r for _, r in stack]
        ck(len(rs) >= 3, f"set {nm!r} has only {len(rs)} parallax layers")
        ck(max(rs) - min(rs) >= 0.4,
           f"set {nm!r} spreads its layers over only "
           f"{max(rs) - min(rs):.2f} of parallax")
    print("  SET_LAYERS/SETS/SET_GROUND, PROP_ANCHOR/PROPS/_BBOX/PROP_ANIMS "
          "in sync; every set >=3 layers and >=0.4 of parallax spread")

    print("\n" + "-" * 62)
    print(f"FAILURES: {len(fails)}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


def _out_dir(argv: list[str]) -> str:
    """First non-flag argument, else ``/tmp``.

    Flags such as ``--selftest`` are accepted and ignored so that a caller
    poking at the module cannot accidentally create a directory named after
    a switch.
    """
    for a in argv:
        if not a.startswith("-"):
            return a
    return "/tmp"


if __name__ == "__main__":
    raise SystemExit(_main(_out_dir(sys.argv[1:])))
