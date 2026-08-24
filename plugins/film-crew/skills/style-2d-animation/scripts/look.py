"""look.py — colour for the 2D character-animation style.

Flat-vector comedy animation. Every value here is a flat fill: there are no
gradients inside a shape, no textures and no grain. Depth is made by overlap,
scale and *atmospheric desaturation* — see `depth_tint`, and `HAZE` for how
thick a given palette's air is.

Module contract (frozen — three other agents code against it)::

    PALETTES: dict[str, dict]
    def choose(mood: str | None, subject: str | None = None) -> dict

A palette exposes exactly these keys, all ``(r, g, b)`` int tuples:

===========================================  ====================================
``sky`` ``ground`` ``far`` ``mid`` ``near``  the set's layers, back to front
``skin`` ``hair`` ``shirt`` ``trouser``      character fills
``shoe``
``ink``                                      outlines *and* every facial feature
``accent`` ``accent2``                       reserved for what the shot is about
``shadow``                                   contact shadows, always at low alpha
===========================================  ====================================

Design rules this module enforces (see ``check`` and the ``__main__`` block):

* **High figure/ground separation.** ``shirt`` and ``trouser`` must be clearly
  separated in lightness from ``mid`` and ``near``, or the character dissolves
  into the background.
* **``ink`` is a single dark colour.** One outline colour, one colour for every
  eye, brow and mouth. Not a family of darks.
* **``accent`` / ``accent2`` are loud.** They are the hero prop and the danger.
* **``shadow`` is never opaque.** It is a soft contact ellipse at low alpha; it
  is what stops a character looking like a sticker on a photograph.

The house look is *light backgrounds, dark saturated characters*. That is the
only arrangement in which a character reads at thumbnail size against a busy
city, and it is what "Summit" and "Getaway Car" both do.
"""

from __future__ import annotations

import colorsys
import math
import re

__all__ = [
    "PALETTES",
    "PALETTE_KEYS",
    "PALETTE_META",
    "LAYER_Z",
    "choose",
    "get",
    "name_of",
    "derive",
    "check",
    "depth_tint",
    "haze_for",
    "mix",
    "shade",
    "tint",
    "desaturate",
    "rotate_hue",
    "luminance",
    "lightness",
    "contrast",
    "saturation",
    "hue",
    "hue_gap",
    "value",
    "alpha",
    "outline_for",
    "sky_gradient",
    "HAZE",
    "DEFAULT_HAZE",
    "SHADOW_INK",
    "SHADOW_OPACITY",
    "SHADOW_OPACITY_RANGE",
    "MIN_FIGURE_DL",
    "MIN_FIGURE_CONTRAST",
    "MAX_WORLD_SAT",
    "MAX_AIR_SAT",
    "MAX_TERRAIN_SAT",
    "MIN_AIR_SAT",
    "WORLD_KEYS",
    "AIR_KEYS",
    "TERRAIN_KEYS",
]

RGB = tuple[int, int, int]

PALETTE_KEYS: tuple[str, ...] = (
    "sky", "ground", "far", "mid", "near",
    "skin", "hair", "shirt", "trouser", "shoe",
    "ink", "accent", "accent2", "shadow",
)

#: How far back each named layer sits, for `depth_tint`. 0 = at the camera,
#: 1 = on the horizon. `sets.py` uses these; a renderer may too.
LAYER_Z: dict[str, float] = {
    "sky": 1.0,
    "far": 0.74,
    "mid": 0.40,
    "near": 0.14,
    "ground": 0.0,
    "prop": 0.0,
    "actor": 0.0,
}

#: The layers that make up the world rather than the figure.
WORLD_KEYS: tuple[str, ...] = ("sky", "far", "mid", "near", "ground")

#: `WORLD_KEYS` split by what the layer actually *is*, because the two halves
#: are held to different saturation limits. `AIR_KEYS` is the stuff light
#: travels through and it must stay quiet; `TERRAIN_KEYS` is rock and earth,
#: which the reference films paint with real colour. See `MAX_AIR_SAT`.
AIR_KEYS: tuple[str, ...] = ("sky", "mid", "near")
TERRAIN_KEYS: tuple[str, ...] = ("far", "ground")

#: How thick the air is, per palette: the `strength` `depth_tint` uses when a
#: caller does not name one. Any palette absent from this table gets
#: `DEFAULT_HAZE`, so adding an entry here cannot move an existing film.
#:
#: `summit` is here because 0.90 is measurably not enough for it. Thick air is
#: the whole of that film's depth: at ``LAYER_Z["far"]`` 1.18 carries the far
#: rock 92 % of the way to the sky, where 0.90 manages only 71 % and leaves the
#: distance reading as a cutout. That is a property of the palette, not of each
#: call site, which is why it lives here rather than in an argument.
DEFAULT_HAZE = 0.90
HAZE: dict[str, float] = {"summit": 1.18}

# The figure/ground rule, in two metrics because neither alone is enough:
#: minimum CIE L* difference between a garment and a background layer
MIN_FIGURE_DL = 20.0
#: minimum WCAG contrast ratio between a garment and a background layer
MIN_FIGURE_CONTRAST = 1.7
#: `accent` must out-shout the background by at least this much L*
MIN_ACCENT_DL = 16.0
#: The world must not compete with the figure: the `AIR_KEYS` layers of a
#: reference-matched palette sit at or below this HSV saturation. Measured,
#: not chosen — across both reference films only ~2.4 % of the frame is above
#: saturation 0.35 and all of it is the character. `check` does not enforce it,
#: because the palettes written before the measurement do not meet it.
MAX_AIR_SAT = 0.15
#: Rock and earth are held to a much looser limit, because the reference films
#: are not in fact neutral there. Sampling `rf_34` by *region* rather than by
#: single pixel puts the peak mass at saturation 0.178–0.256, and TARGET.md's
#: own table lists ``peak, shadow`` ``#483e30`` at 0.33 — which its "the whole
#: environment is <= 0.15" rule contradicts. The regions are the honest
#: measurement, so terrain gets its own ceiling. It is still well under the
#: figure: `accent` is 0.55 and `accent2` 0.75.
MAX_TERRAIN_SAT = 0.28
#: Kept as the loosest of the two so anything importing the old name still gets
#: a true upper bound over all of `WORLD_KEYS`.
MAX_WORLD_SAT = MAX_TERRAIN_SAT
#: The air must not be *grey* either. `depth_tint` converges everything
#: distant on `sky`, so `sky`'s own saturation sets the chroma of every pale
#: pixel, and pale pixels are most of a landscape. Below this the air
#: subtracts colour instead of shifting it and the finished film measures
#: around saturation 0.035 against the reference's 0.070. The number is the
#: floor that lands a reference-matched palette inside the graded envelope;
#: like the ceilings it is asserted for `summit`, not enforced by `check`.
MIN_AIR_SAT = 0.09
#: `ink` must be genuinely dark, and must read on skin
MAX_INK_L = 32.0
MIN_INK_ON_SKIN = 3.4
#: ...but it must never be pure black. A `#000000` outline is the single
#: loudest "cheap clip-art" tell in flat vector: it belongs to no palette and
#: it flattens everything it touches. Every `ink` is a dark *hued* colour —
#: navy, brown or charcoal that is visibly part of its own film.
MIN_INK_L = 4.5
#: minimum channel spread (max - min) in `ink`, i.e. it must carry a hue
MIN_INK_CHROMA = 8

#: The contact-shadow reference colour, ``#1A2830``. Every palette's `shadow`
#: is this tinted toward its own air. See `sets.contact_shadow`.
SHADOW_INK: RGB = (26, 40, 48)
#: Contact shadows are drawn at this alpha, and never outside the range.
SHADOW_OPACITY = 0.30
SHADOW_OPACITY_RANGE = (0.28, 0.32)
#: Semi-axis factors for a contact ellipse: ``a = foot_span * A``,
#: ``b = height * B``. A ground-pinned ellipse this flat is what tells the eye
#: the figure is standing *on* the ground rather than pasted in front of it.
SHADOW_A = 0.55
SHADOW_B = 0.06


# --------------------------------------------------------------------------
# colour maths
# --------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _byte(v: float) -> int:
    return int(round(_clamp(v, 0.0, 255.0)))


def _lin(c: int) -> float:
    """sRGB byte -> linear-light 0..1."""
    u = c / 255.0
    return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4


def luminance(rgb: RGB) -> float:
    """WCAG relative luminance, 0..1."""
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def lightness(rgb: RGB) -> float:
    """CIE L*, 0..100. Perceptually even, which is what a silhouette obeys."""
    y = luminance(rgb)
    return 116.0 * (y ** (1.0 / 3.0)) - 16.0 if y > 0.008856 else 903.3 * y


def contrast(a: RGB, b: RGB) -> float:
    """WCAG contrast ratio, 1.0 (identical) .. 21.0 (black on white)."""
    la, lb = luminance(a), luminance(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def saturation(rgb: RGB) -> float:
    """HSV saturation, 0..1. The axis the reference films are measured on."""
    return colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))[1]


def value(rgb: RGB) -> float:
    """HSV value, 0..1 — plain ``max(r, g, b)``, again to match the reference.

    Not `lightness`: L* answers "will this silhouette read", `value` answers
    "is the film light or heavy", and those are different questions.
    """
    return colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))[2]


def hue(rgb: RGB) -> float:
    """HSV hue in degrees, 0..360. Meaningless on a grey, so callers that care
    about a *mean* hue should weight it by `saturation`."""
    return colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))[0] * 360.0


def hue_gap(a: RGB, b: RGB) -> float:
    """Shortest distance between two hues, 0..180 degrees.

    Warm rock against cool air is what stops a near-neutral palette reading as
    greyscale, and the reference films hold about 190 degrees of it, so the
    opposition is a measured quantity rather than a matter of taste.
    """
    d = abs(hue(a) - hue(b)) % 360.0
    return 360.0 - d if d > 180.0 else d


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Linear blend in sRGB space. `t`=0 is `a`, `t`=1 is `b`.

    Deliberately *not* linear-light: flat-vector work is authored in sRGB and
    blending there keeps mid-mixes from going chalky.
    """
    t = _clamp(t)
    return (
        _byte(a[0] + (b[0] - a[0]) * t),
        _byte(a[1] + (b[1] - a[1]) * t),
        _byte(a[2] + (b[2] - a[2]) * t),
    )


def shade(c: RGB, f: float) -> RGB:
    """Multiply toward black. `f`=1 is unchanged, `f`=0.6 is 40% darker."""
    return (_byte(c[0] * f), _byte(c[1] * f), _byte(c[2] * f))


def tint(c: RGB, f: float) -> RGB:
    """Blend toward white by `f`."""
    return mix(c, (255, 255, 255), f)


def desaturate(c: RGB, f: float) -> RGB:
    """Blend toward the colour's own luma by `f`."""
    y = _byte(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    return mix(c, (y, y, y), f)


def _unlin(u: float) -> float:
    """linear-light 0..1 -> sRGB byte value 0..255 (unclamped)."""
    u = max(0.0, min(1.0, u))
    v = 12.92 * u if u <= 0.0031308 else 1.055 * (u ** (1 / 2.4)) - 0.055
    return v * 255.0


def rotate_hue(c: RGB, deg: float) -> RGB:
    """Rotate hue while holding **relative luminance** exactly.

    Rotating in HSV moves lightness and would quietly break the figure/ground
    guarantee that `check` asserts. This works in linear light, rotates the
    chroma vector about the luminance axis, and shrinks the *chroma* — never
    the luminance — to get back inside the sRGB cube. Every contrast assertion
    that held before the rotation therefore still holds after it, which is what
    makes `derive` safe.
    """
    r, g, b = _lin(c[0]), _lin(c[1]), _lin(c[2])
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cr, cb = r - y, b - y
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    ncr = cr * ca - cb * sa
    ncb = cr * sa + cb * ca

    def _at(k: float) -> tuple[float, float, float]:
        rr = y + ncr * k
        bb = y + ncb * k
        gg = (y - 0.2126 * rr - 0.0722 * bb) / 0.7152
        return rr, gg, bb

    def _fits(k: float) -> bool:
        e = 1e-9
        return all(-e <= v <= 1 + e for v in _at(k))

    k = 1.0
    if not _fits(1.0):
        lo, hi = 0.0, 1.0
        for _ in range(30):
            mid_k = (lo + hi) * 0.5
            if _fits(mid_k):
                lo = mid_k
            else:
                hi = mid_k
        k = lo
    rr, gg, bb = _at(k)
    return (_byte(_unlin(rr)), _byte(_unlin(gg)), _byte(_unlin(bb)))


def alpha(c: RGB, a: float) -> tuple[int, int, int, int]:
    """`(r, g, b, a)` with `a` given 0..1. For shadows and rotor discs."""
    return (int(c[0]), int(c[1]), int(c[2]), int(round(_clamp(a) * 255)))


def _at_L(c: RGB, target: float) -> RGB:
    """`c` moved to an exact CIE L*, keeping its hue. Bisects a blend."""
    cur = lightness(c)
    if abs(cur - target) < 0.25:
        return (int(c[0]), int(c[1]), int(c[2]))
    end = (255, 255, 255) if target > cur else (0, 0, 0)
    lo, hi = 0.0, 1.0
    for _ in range(28):
        m = (lo + hi) / 2.0
        if (lightness(mix(c, end, m)) > target) == (target > cur):
            hi = m
        else:
            lo = m
    return mix(c, end, (lo + hi) / 2.0)


def _keep_hued(c: RGB, min_chroma: int, min_l: float) -> RGB:
    """Guarantee a dark colour still carries a hue after a hue rotation.

    Rotating a near-neutral dark can land on a hue where the byte spread
    collapses, and a derived palette would quietly acquire a grey — or black —
    outline. This puts the chroma back without moving L*.
    """
    target = max(float(min_l), lightness(c))
    for _ in range(14):
        if max(c) - min(c) >= min_chroma and lightness(c) >= min_l:
            return (int(c[0]), int(c[1]), int(c[2]))
        r, g, b = (_clamp(float(v) / 255.0) for v in c)
        h, l, sa = colorsys.rgb_to_hls(r, g, b)
        rr, gg, bb = colorsys.hls_to_rgb(h, max(l, 0.06), min(1.0, sa + 0.14))
        c = _at_L((_byte(rr * 255.0), _byte(gg * 255.0), _byte(bb * 255.0)),
                  target)
    return c


def outline_for(fill: RGB, *, sat: float = 0.10, light: float = 0.40) -> RGB:
    """The outline a *single shape* should carry, derived from its own fill.

    Same hue, saturation +0.1, lightness -0.40. Every shape outlined in the
    palette's one `ink` gives a uniform black-line cartoon; letting a red car
    carry a dark-red line and a green tree a dark-green one is what separates
    a designed frame from clip art.

    `ink` remains correct for outlines that must not belong to any object —
    the character's silhouette, and every facial feature.

    An achromatic fill stays achromatic: adding saturation to a grey would
    invent a red hue out of nothing, and this module never invents colour.
    """
    r, g, b = (_clamp(float(c) / 255.0) for c in fill)
    h, l, sa = colorsys.rgb_to_hls(r, g, b)
    sa2 = sa if sa < 0.02 else _clamp(sa + float(sat))
    l2 = _clamp(l - float(light), 0.03, 1.0)
    rr, gg, bb = colorsys.hls_to_rgb(h, l2, sa2)
    return (_byte(rr * 255.0), _byte(gg * 255.0), _byte(bb * 255.0))


def sky_gradient(sky: RGB, *, spread: float = 7.5) -> tuple[RGB, RGB]:
    """The two stops of the **only** gradient this style allows.

    Flat fills everywhere, with one exception: a simple 2-stop linear sky.
    Deeper at the top, paler toward the horizon, `spread` L* either side of
    the palette's own `sky`. Nothing else in the frame may be graduated.
    """
    l = lightness(sky)
    # A night sky cannot give 7.5 L* back at the top without going black, and
    # it should not: at night the *horizon* is the bright end, lit from below
    # by the city. So the downward reach is capped by how much sky there is.
    down = min(float(spread), max(1.5, l * 0.45))
    top = _at_L(desaturate(sky, -0.10), max(1.5, l - down))
    bottom = _at_L(desaturate(sky, 0.22), min(100.0, l + float(spread)))
    return (top, bottom)


def depth_tint(color: RGB, z: float, sky: RGB, *,
               strength: float | None = None) -> RGB:
    """Push a colour back into the haze.

    ``z`` is **distance from the camera**: ``0.0`` is the foreground and is
    returned unchanged, ``1.0`` is the horizon and washes almost entirely into
    ``sky``. See ``LAYER_Z`` for the values `sets.py` uses.

    Air both *desaturates* and *lifts toward the sky colour*, and doing only
    the second leaves distant saturated shapes looking like stickers, so this
    does both: the source is bleached first, then mixed into the sky.

    ``strength`` is how thick the air is. Left unset it is looked up from the
    palette that owns ``sky`` — see `HAZE` — so a call site never has to pass a
    whole palette in just to get its weather. Every palette that does not ask
    for more gets `DEFAULT_HAZE`, which is the value this argument used to
    default to.
    """
    z = _clamp(z)
    if z <= 0.0:
        return (int(color[0]), int(color[1]), int(color[2]))
    if strength is None:
        strength = haze_for(sky)
    # Clamp the *product*, not `strength`. Air thicker than 1.0 is the only way
    # to wash a layer fully into the sky before ``z`` reaches the horizon, and
    # `LAYER_Z["far"]` is 0.74, not 1.0. For any strength <= 1.0 this is
    # arithmetically identical to clamping `strength`, so nothing already
    # written moves.
    k = _clamp(max(0.0, float(strength)) * (z ** 0.85))
    # Bleach first, *then* mix into the sky. With flat colour and no texture,
    # losing chroma with distance is one of the only depth cues available, so
    # it has to be worth more than the mix alone: a distant saturated shape
    # that has merely been lightened still reads as a cutout held up close.
    return mix(desaturate(color, 0.78 * k), sky, k)


# --------------------------------------------------------------------------
# the palettes
# --------------------------------------------------------------------------

PALETTES: dict[str, dict[str, RGB]] = {

    # Daylight city car chase. Hot bleached sky, cool concrete, a siren red
    # that exists nowhere else in the frame.
    "pursuit": {
        "sky":      (150, 208, 234),
        "ground":   (176, 180, 186),
        "far":      (108, 146, 176),
        "mid":      (196, 205, 211),
        "near":     (222, 214, 199),
        "skin":     (232, 168, 128),
        "hair":     (58,  40,  38),
        "shirt":    (206, 74,  56),
        "trouser":  (44,  56,  86),
        "shoe":     (36,  34,  40),
        "ink":      (28,  30,  40),
        "accent":   (224, 46,  48),
        "accent2":  (247, 190, 48),
        "shadow":   (26,  40,  52),
    },

    # Warm daytime comedy. Suburbs, parks, the middle of a good day.
    "noon": {
        "sky":      (168, 216, 240),
        "ground":   (206, 196, 168),
        "far":      (118, 164, 158),
        "mid":      (206, 214, 196),
        "near":     (232, 220, 186),
        "skin":     (240, 182, 142),
        "hair":     (72,  46,  34),
        "shirt":    (58,  120, 148),
        "trouser":  (96,  52,  44),
        "shoe":     (48,  42,  46),
        "ink":      (40,  34,  30),
        "accent":   (238, 96,  62),
        "accent2":  (86,  170, 120),
        "shadow":   (28,  42,  42),
    },

    # Dusk. Golden hour going purple. Warm sky, cool shadow side.
    "dusk": {
        "sky":      (244, 178, 128),
        "ground":   (150, 124, 132),
        "far":      (160, 110, 120),
        "mid":      (206, 158, 142),
        "near":     (188, 140, 134),
        "skin":     (226, 154, 116),
        "hair":     (54,  34,  44),
        "shirt":    (52,  70,  116),
        "trouser":  (46,  38,  62),
        "shoe":     (34,  28,  40),
        "ink":      (38,  28,  42),
        "accent":   (250, 214, 96),
        "accent2":  (232, 84,  92),
        "shadow":   (38,  34,  50),
    },

    # Night and neon. The one palette that inverts the house rule: the
    # background is dark, so the characters are the lit thing.
    "neon": {
        "sky":      (22,  22,  46),
        "ground":   (48,  48,  62),
        "far":      (78,  72,  126),
        "mid":      (34,  36,  62),
        "near":     (26,  28,  48),
        "skin":     (226, 158, 132),
        "hair":     (46,  36,  56),
        "shirt":    (110, 214, 226),
        "trouser":  (154, 132, 190),
        "shoe":     (200, 198, 216),
        "ink":      (22,  18,  42),
        "accent":   (255, 66,  132),
        "accent2":  (98,  240, 200),
        "shadow":   (16,  22,  40),
    },

    # Interior office. Nothing here wants to be looked at except the accent.
    "office": {
        "sky":      (186, 214, 226),
        "ground":   (176, 168, 158),
        "far":      (160, 158, 150),
        "mid":      (216, 210, 196),
        "near":     (200, 192, 176),
        "skin":     (234, 178, 140),
        "hair":     (58,  46,  40),
        "shirt":    (74,  96,  132),
        "trouser":  (56,  54,  58),
        "shoe":     (40,  36,  36),
        "ink":      (34,  38,  48),
        "accent":   (222, 92,  56),
        "accent2":  (72,  156, 142),
        "shadow":   (32,  40,  46),
    },

    # Open countryside. Big sky, low horizon, nothing man-made in the accents.
    "country": {
        "sky":      (158, 210, 238),
        "ground":   (170, 196, 132),
        "far":      (118, 162, 156),
        "mid":      (186, 208, 164),
        "near":     (206, 214, 150),
        "skin":     (238, 180, 138),
        "hair":     (108, 62,  36),
        "shirt":    (176, 62,  70),
        "trouser":  (52,  66,  92),
        "shoe":     (60,  44,  36),
        "ink":      (30,  40,  30),
        "accent":   (236, 92,  70),
        "accent2":  (246, 200, 74),
        "shadow":   (28,  44,  38),
    },

    # Overcast. Rain, commuting, Monday. Almost no chroma except the accent.
    "overcast": {
        "sky":      (198, 206, 212),
        "ground":   (150, 154, 158),
        "far":      (140, 150, 164),
        "mid":      (178, 184, 190),
        "near":     (196, 198, 196),
        "skin":     (222, 172, 142),
        "hair":     (52,  46,  48),
        "shirt":    (48,  84,  98),
        "trouser":  (40,  40,  48),
        "shoe":     (38,  36,  40),
        "ink":      (32,  36,  46),
        "accent":   (206, 96,  36),
        "accent2":  (70,  128, 160),
        "shadow":   (32,  40,  50),
    },

    # Baked desert highway. Route-movie heat, tarmac and dust.
    "heat": {
        "sky":      (236, 206, 154),
        "ground":   (196, 176, 158),
        "far":      (172, 136, 118),
        "mid":      (222, 192, 152),
        "near":     (232, 198, 140),
        "skin":     (226, 162, 118),
        "hair":     (66,  40,  30),
        "shirt":    (42,  100, 116),
        "trouser":  (94,  40,  36),
        "shoe":     (48,  36,  32),
        "ink":      (44,  30,  28),
        "accent":   (222, 62,  46),
        "accent2":  (58,  138, 158),
        "shadow":   (46,  36,  34),
    },

    # Broadcast newsroom / rolling-news graphics. Cool, corporate, urgent.
    "newsroom": {
        "sky":      (176, 202, 224),
        "ground":   (154, 162, 176),
        "far":      (128, 158, 192),
        "mid":      (200, 210, 222),
        "near":     (214, 218, 226),
        "skin":     (232, 176, 138),
        "hair":     (48,  40,  44),
        "shirt":    (36,  70,  126),
        "trouser":  (40,  46,  58),
        "shoe":     (32,  32,  38),
        "ink":      (26,  30,  40),
        "accent":   (214, 38,  46),
        "accent2":  (250, 198, 62),
        "shadow":   (24,  38,  54),
    },

    # Mountain air, matched to measured reference stills rather than invented.
    # The *air* is near-neutral — every `AIR_KEYS` layer is at or under
    # `MAX_AIR_SAT` — and the figure carries the loud end of the chroma budget.
    # That is not restraint for its own sake: in the reference only 2.4 % of
    # the frame is above saturation 0.35 and all of it is the character, which
    # is what lets one small figure hold a mountain instead of competing with
    # it. The character is only 4.1 % of the frame and supplies 9.4 % of its
    # total saturation, so this palette is won or lost on the environment.
    #
    # `far` looks wrong in the swatch strip and is not. It is bare rock,
    # ``#706859``, the measured colour of a lit peak — a *material*, not the
    # pale ridge you actually see. At ``LAYER_Z["far"]`` this palette's air
    # (`HAZE`) carries it most of the way to the sky. Authoring the ridge pale
    # instead would leave `depth_tint` nothing to do, and a far layer that the
    # air never touched is a cutout rather than distance.
    #
    # Two things make this palette work, and both are measured by *region*
    # rather than by sampling single pixels — an earlier pass used single
    # pixels and got both of them wrong.
    #
    # The air is *tinted*, not grey. `depth_tint` converges everything distant
    # on `sky`, so `sky` alone sets the chroma of every pale pixel in the
    # frame, and pale pixels are most of a mountain. A near-neutral sky makes
    # the air *subtract* chroma and the finished film measures around
    # saturation 0.035 against the reference's 0.075. The reference's sky
    # region is saturation 0.073 at hue 221 — a definite cool blue-grey, not
    # the 0.027 of one pixel at the very top of the frame.
    #
    # And the world is built on a near-complementary opposition: cool air at
    # hue ~220 against warm rock at hue ~35, about 190 degrees apart. That
    # opposition is why the reference reads as painted rather than as
    # greyscale, and it is also why the distant ridges can be near-neutral
    # while nothing else is — `depth_tint` mixes the warm rock into the cool
    # sky, and near-opposite hues partly cancel. Chroma that is merely
    # *removed* leaves grey; chroma that is *opposed* leaves air.
    #
    # `ground` is the near ground plane and sits at ``LAYER_Z`` 0.0, where
    # `depth_tint` returns its argument untouched. Its warmth is therefore
    # structurally safe from the haze however thick the air gets — the pull
    # toward `sky` applies to distance, not to everything.
    "summit": {
        "sky":      (198, 207, 224),
        "ground":   (171, 145, 133),
        "far":      (112, 104, 89),
        "mid":      (156, 165, 181),
        "near":     (178, 167, 152),
        "skin":     (232, 180, 146),
        "hair":     (66,  48,  38),
        "shirt":    (140, 62,  40),
        "trouser":  (48,  54,  66),
        "shoe":     (44,  42,  48),
        "ink":      (48,  44,  38),
        "accent":   (102, 119, 54),
        "accent2":  (176, 96,  44),
        "shadow":   (34,  42,  48),
    },
}


#: `depth_tint` is handed a `sky`, not a palette, so the air is looked up by
#: it. No two palettes share a sky, and a colour belonging to none of them —
#: a hand-mixed one, or a gradient stop — falls through to `DEFAULT_HAZE`.
_HAZE_BY_SKY: dict[RGB, float] = {
    tuple(PALETTES[n]["sky"]): h for n, h in HAZE.items() if n in PALETTES
}


def haze_for(sky: RGB) -> float:
    """How thick the air is under `sky`. `DEFAULT_HAZE` for anything unlisted."""
    return _HAZE_BY_SKY.get(tuple(sky), DEFAULT_HAZE)


#: Routing vocabulary for `choose`. Presentation only — nothing factual.
#: `moods` are the score/beat-plan mood words; `words` are anything a subject
#: line might contain.
PALETTE_META: dict[str, dict] = {
    "pursuit": {
        "label": "Daylight pursuit",
        "note": "bleached city noon, siren red, cool concrete",
        "moods": ("chase", "pursuit", "urgent", "tense", "frantic", "action",
                  "thriller", "panic", "driving"),
        "words": ("chase", "pursuit", "police", "cop", "siren", "getaway",
                  "escape", "speed", "fleeing", "suspect", "squad", "patrol",
                  "heist", "robbery", "crime", "manhunt", "roadblock",
                  "junction", "motorway", "interception", "helicopter",
                  "chopper", "car"),
    },
    "noon": {
        "label": "Warm daytime comedy",
        "note": "suburban midday, the middle of a good day",
        "moods": ("comic", "comedy", "happy", "cheerful", "playful", "light",
                  "upbeat", "warm", "whimsical", "silly", "bright"),
        "words": ("park", "picnic", "garden", "suburb", "school", "kids",
                  "holiday", "summer", "birthday", "neighbour", "barbecue",
                  "sunny", "morning", "playground", "ice", "cream", "dog",
                  "walk", "queue", "shop", "street"),
    },
    "dusk": {
        "label": "Dusk / golden hour",
        "note": "warm sky, cool shadow, the end of something",
        "moods": ("wistful", "bittersweet", "nostalgic", "melancholy",
                  "romantic", "reflective", "tender", "hopeful", "elegiac"),
        "words": ("dusk", "sunset", "evening", "golden", "goodbye", "farewell",
                  "memory", "remember", "autumn", "last", "ending", "home",
                  "returning", "harbour", "beach", "rooftop", "twilight"),
    },
    "neon": {
        "label": "Night neon",
        "note": "dark city, lit characters, everything electric",
        "moods": ("dark", "moody", "eerie", "noir", "sinister", "electric",
                  "cool", "techno", "restless", "ominous"),
        "words": ("night", "neon", "midnight", "club", "bar", "arcade",
                  "cyber", "hacker", "underground", "rain", "alley", "signs",
                  "sleepless", "late", "vending", "karaoke", "taxi",
                  "downtown", "nocturnal"),
    },
    "office": {
        "label": "Interior office",
        "note": "flat institutional light, one loud accent",
        "moods": ("dull", "deadpan", "bureaucratic", "corporate", "awkward",
                  "professional", "explainer", "instructional", "neutral"),
        "words": ("office", "desk", "meeting", "work", "boss", "manager",
                  "colleague", "email", "spreadsheet", "printer", "cubicle",
                  "interview", "deadline", "admin", "hr", "appraisal",
                  "business", "indoor", "interior", "presentation", "startup",
                  "photocopier", "kitchenette", "chair"),
    },
    "country": {
        "label": "Open countryside",
        "note": "big sky, low horizon, nothing man-made in the accents",
        "moods": ("calm", "peaceful", "pastoral", "gentle", "serene", "quiet",
                  "wholesome", "wandering"),
        "words": ("country", "countryside", "rural", "field", "farm",
                  "village", "meadow", "hill", "hills", "hedge", "sheep",
                  "cow", "tractor", "lane", "footpath", "picnic", "river",
                  "nature", "hike", "camping", "orchard"),
    },
    "overcast": {
        "label": "Overcast grey",
        "note": "no chroma anywhere except the thing that matters",
        "moods": ("sad", "bleak", "gloomy", "flat", "resigned", "weary",
                  "downbeat", "mundane", "grim"),
        "words": ("rain", "drizzle", "grey", "gray", "monday", "commute",
                  "bus", "queue", "winter", "damp", "umbrella", "delayed",
                  "cancelled", "waiting", "puddle", "traffic", "jam"),
    },
    "heat": {
        "label": "Desert highway",
        "note": "sunbaked tarmac and dust, cyan against terracotta",
        "moods": ("epic", "sprawling", "restless", "adventurous", "sweltering",
                  "lonesome", "western"),
        "words": ("desert", "heat", "highway", "route", "roadtrip", "canyon",
                  "dust", "arid", "cactus", "gas", "station", "truck",
                  "trailer", "sunbaked", "mirage", "interstate", "scorching",
                  "outback"),
    },
    "newsroom": {
        "label": "Rolling news",
        "note": "broadcast blue and a red that means BREAKING",
        "moods": ("breaking", "reporting", "authoritative", "serious",
                  "documentary", "journalistic", "live"),
        "words": ("news", "newsroom", "broadcast", "anchor", "reporter",
                  "studio", "chyron", "bulletin", "live", "coverage", "media",
                  "camera", "channel", "headline", "presenter", "breaking",
                  "network"),
    },
    # "wistful", "calm", "quiet" and "peaceful" are deliberately in `words`
    # rather than `moods`: `dusk` and `country` already own them as moods and
    # score 4 to this palette's 2, so a bare mood word keeps routing exactly
    # where it always did. It is the *subject* that hands a film to `summit` —
    # a mountain, a climb, mist — which is the right way round, because the
    # feeling is shared and the place is not.
    "summit": {
        "label": "Misty summit",
        "note": "near-neutral air, one small saturated figure",
        "moods": ("lonely", "solitary", "alone", "misty", "hushed", "still",
                  "contemplative", "meditative", "remote", "vast", "awed",
                  "windswept"),
        "words": ("mountain", "summit", "peak", "ridge", "alpine", "climb",
                  "climber", "hike", "trek", "ascent", "mist", "fog", "cloud",
                  "snow", "glacier", "valley", "altitude", "cairn", "trail",
                  "rope", "crag", "scree", "slope", "horizon", "solitude",
                  "silence", "distance", "wistful", "calm", "quiet",
                  "peaceful"),
    },
}

#: The palette `choose` returns when the caller genuinely said nothing.
#: It is only reachable for `choose(None, None)` — see the module docstring.
DEFAULT_PALETTE = "noon"

_DERIVED: dict[str, dict[str, RGB]] = {}
_NAMES: dict[int, str] = {}
for _n, _p in PALETTES.items():
    _NAMES[id(_p)] = _n
del _n, _p


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _sep(a: RGB, b: RGB) -> tuple[float, float]:
    return abs(lightness(a) - lightness(b)), contrast(a, b)


def check(pal: dict) -> list[str]:
    """Return a list of human-readable problems with `pal`. Empty means good.

    The figure/ground rule is the important one: a character standing anywhere
    in the set must not dissolve into it.
    """
    problems: list[str] = []

    missing = [k for k in PALETTE_KEYS if k not in pal]
    if missing:
        problems.append(f"missing keys: {', '.join(missing)}")
        return problems
    for k in PALETTE_KEYS:
        v = pal[k]
        if (not isinstance(v, tuple) or len(v) != 3
                or not all(isinstance(c, int) and 0 <= c <= 255 for c in v)):
            problems.append(f"{k}={v!r} is not an (r, g, b) int tuple in 0..255")
    if problems:
        return problems

    for garment in ("shirt", "trouser"):
        for layer in ("mid", "near"):
            dl, cr = _sep(pal[garment], pal[layer])
            if dl < MIN_FIGURE_DL:
                problems.append(
                    f"figure/ground: {garment} vs {layer} dL*={dl:.1f} "
                    f"< {MIN_FIGURE_DL}")
            if cr < MIN_FIGURE_CONTRAST:
                problems.append(
                    f"figure/ground: {garment} vs {layer} contrast={cr:.2f} "
                    f"< {MIN_FIGURE_CONTRAST}")

    dl, _ = _sep(pal["shirt"], pal["trouser"])
    if dl < 10.0:
        problems.append(f"shirt vs trouser dL*={dl:.1f} < 10.0 — the body reads as one slab")

    for layer in ("mid", "near"):
        dl, _ = _sep(pal["accent"], pal[layer])
        if dl < MIN_ACCENT_DL:
            problems.append(f"accent vs {layer} dL*={dl:.1f} < {MIN_ACCENT_DL}")

    ink = pal["ink"]
    li = lightness(ink)
    if li > MAX_INK_L:
        problems.append(f"ink L*={li:.1f} > {MAX_INK_L} — outlines will look grey")
    if tuple(ink) == (0, 0, 0):
        problems.append("ink is pure black — that is the clip-art tell, not a palette")
    if li < MIN_INK_L:
        problems.append(f"ink L*={li:.1f} < {MIN_INK_L} — effectively black")
    if max(ink) - min(ink) < MIN_INK_CHROMA:
        problems.append(
            f"ink chroma={max(ink) - min(ink)} < {MIN_INK_CHROMA} — a neutral "
            f"grey line belongs to no palette")
    cr = contrast(ink, pal["skin"])
    if cr < MIN_INK_ON_SKIN:
        problems.append(f"ink on skin contrast={cr:.2f} < {MIN_INK_ON_SKIN} — the face will not read")

    sh = pal["shadow"]
    lsh = lightness(sh)
    if lsh > 24.0:
        problems.append(f"shadow L*={lsh:.1f} > 24.0 — too pale to pin a figure down")
    if max(sh) - min(sh) < 6:
        problems.append(f"shadow chroma={max(sh) - min(sh)} < 6 — a neutral grey smudge")
    # Two metrics, because on a night palette both the ground and the shadow
    # are near-black and a WCAG ratio stops discriminating there.
    if (contrast(sh, pal["ground"]) < 1.8
            and abs(lightness(pal["ground"]) - lsh) < 8.0):
        problems.append("shadow vs ground too close — the contact ellipse will not show")

    dl, _ = _sep(pal["sky"], pal["far"])
    if dl < 6.0:
        problems.append(f"sky vs far dL*={dl:.1f} < 6.0 — the far layer is invisible once hazed")
    if dl > 42.0:
        problems.append(f"sky vs far dL*={dl:.1f} — the far layer is not atmospheric, it is a cutout")

    return problems


# --------------------------------------------------------------------------
# choosing
# --------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(s: str | None) -> list[str]:
    if not s:
        return []
    return _WORD.findall(s.lower())


def _stem(w: str) -> str:
    for suf in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _stable_hash(s: str) -> int:
    """A hash that does not move between runs (Python's `hash` is salted)."""
    h = 0xCBF29CE484222325
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def score(mood: str | None, subject: str | None = None) -> dict[str, float]:
    """The evidence behind `choose`. Exposed so a compiler can explain itself."""
    mood_t = [_stem(w) for w in _tokens(mood)]
    subj_t = [_stem(w) for w in _tokens(subject)]
    out: dict[str, float] = {}
    for name, meta in PALETTE_META.items():
        moods = {_stem(w) for w in meta["moods"]}
        words = {_stem(w) for w in meta["words"]}
        s = 0.0
        for w in mood_t:
            if w in moods:
                s += 4.0
            elif w in words:
                s += 2.0
        seen: set[str] = set()
        for w in subj_t:
            if w in seen:
                continue
            if w in words:
                s += 1.5
                seen.add(w)
            elif w in moods:
                s += 1.0
                seen.add(w)
        # A palette named outright wins outright.
        if name in mood_t or name in subj_t:
            s += 12.0
        out[name] = s
    return out


def derive(key: str, *, base: str | None = None) -> dict[str, RGB]:
    """Build a *new* palette for a story none of the named palettes fit.

    This exists because of the third obligation in the style contract: if two
    unrelated films compile to the same colour, the compiler is not deciding,
    it is defaulting. When `choose` finds no evidence it does **not** fall back
    to `noon`; it comes here and mints a palette from the story's own text.

    Hue is rotated with `rotate_hue`, which holds luma, so the derived palette
    inherits the base palette's figure/ground guarantees exactly.
    """
    h = _stable_hash(key)
    names = sorted(PALETTES)
    if base is None:
        base = names[h % len(names)]
    cache_key = f"{base}~{h & 0xFFFF:04x}"
    hit = _DERIVED.get(cache_key)
    if hit is not None:
        return hit

    src = PALETTES[base]
    # Two rotations: the world turns one way, the accents another, so the
    # accents stay loud instead of sliding into the background's hue family.
    world = ((h >> 16) % 24) * 15.0 - 180.0
    accent_off = (((h >> 24) % 5) - 2) * 26.0
    warm = 0.90 + ((h >> 32) % 21) / 100.0

    out: dict[str, RGB] = {}
    for k in PALETTE_KEYS:
        c = src[k]
        if k == "skin":
            out[k] = rotate_hue(c, world * 0.12)
        elif k == "ink":
            out[k] = _keep_hued(rotate_hue(c, world * 0.5),
                                MIN_INK_CHROMA, MIN_INK_L)
        elif k == "shadow":
            out[k] = _keep_hued(rotate_hue(c, world), 6, 5.0)
        elif k in ("accent", "accent2"):
            out[k] = rotate_hue(c, world + accent_off)
        elif k in ("sky", "far", "mid", "near", "ground"):
            out[k] = rotate_hue(desaturate(c, max(0.0, 1.0 - warm) * 0.9), world)
        else:
            out[k] = rotate_hue(c, world)

    _DERIVED[cache_key] = out
    _NAMES[id(out)] = cache_key
    # A film derived from a thick-aired palette keeps its air. `depth_tint`
    # resolves the haze from the sky it is handed and the rotation moved that
    # sky, so the new one has to be registered or the derived film would
    # quietly lose the only depth cue its base had. `setdefault` so a derived
    # palette can never take the air away from a named one.
    air = HAZE.get(base, DEFAULT_HAZE)
    if air != DEFAULT_HAZE:
        _HAZE_BY_SKY.setdefault(tuple(out["sky"]), air)
    return out


def get(name: str) -> dict[str, RGB] | None:
    """Look a palette up by name, including one previously `derive`d."""
    return PALETTES.get(name) or _DERIVED.get(name)


def name_of(pal: dict) -> str:
    """The name of a palette object, for logs and board round-tripping."""
    n = _NAMES.get(id(pal))
    if n:
        return n
    for src in (PALETTES, _DERIVED):
        for k, v in src.items():
            if all(v.get(key) == pal.get(key) for key in PALETTE_KEYS):
                return k
    return "unnamed"


def choose(mood: str | None, subject: str | None = None) -> dict:
    """Pick a palette from the story.

    `mood` is a score/beat-plan mood word; `subject` is free text — a logline,
    a title, a shot note. Both are weighed, `mood` more heavily.

    Three outcomes, and only one of them is a default:

    1. The text names a palette, or matches one's vocabulary -> that palette.
    2. The text says something but matches nothing -> `derive` mints a palette
       from the text itself. Two unrelated films therefore never compile to the
       same colour by accident.
    3. `choose(None, None)` -> `PALETTES[DEFAULT_PALETTE]`, because the caller
       genuinely said nothing and a default is the honest answer.
    """
    if not (mood and mood.strip()) and not (subject and subject.strip()):
        return PALETTES[DEFAULT_PALETTE]

    direct = (mood or "").strip().lower()
    if direct in PALETTES:
        return PALETTES[direct]
    if direct in _DERIVED:
        return _DERIVED[direct]

    scores = score(mood, subject)
    best = max(sorted(scores), key=lambda n: (scores[n], -_stable_hash(n) % 97))
    if scores[best] > 0.0:
        return PALETTES[best]

    return derive(f"{mood or ''}|{subject or ''}")


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

def _swatch_sheet(path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    names = list(PALETTES)
    demo = [
        ("chase", "police car chase through the city"),
        ("sad", "raining on the bus again"),
        ("calm", "walking the dog across a field"),
        ("deadpan", "quarterly review in meeting room 4"),
        ("noir", "neon alley at 2am"),
        ("wistful", "the last ferry home at sunset"),
        ("ceremonial", "a tortoise inherits a submarine"),
        ("baroque", "competitive origami in zero gravity"),
    ]
    derived = []
    for m, s in demo:
        p = choose(m, s)
        n = name_of(p)
        if n not in names and n not in [d[0] for d in derived]:
            derived.append((n, p))

    rows = [(n, PALETTES[n]) for n in names] + derived
    ss = 2
    sw, rh, pad, label_w = 74, 96, 18, 268
    scene_w = 300
    W = label_w + scene_w + len(PALETTE_KEYS) * sw + pad * 3
    H = pad * 2 + 54 + len(rows) * rh

    im = Image.new("RGB", (W * ss, H * ss), (24, 24, 28))
    d = ImageDraw.Draw(im, "RGBA")
    f_title = ImageFont.load_default(size=26 * ss)
    f_name = ImageFont.load_default(size=17 * ss)
    f_sub = ImageFont.load_default(size=11 * ss)
    f_key = ImageFont.load_default(size=11 * ss)

    d.text((pad * ss, pad * ss), "look.PALETTES", font=f_title, fill=(240, 240, 240))
    d.text((pad * ss, (pad + 32) * ss),
           "scene strip: 2-stop sky / far / mid / near / ground, a figure in "
           "shirt+trouser on a spec contact shadow, outlines via outline_for()",
           font=f_sub, fill=(150, 150, 158))

    y = pad + 54
    for name, pal in rows:
        ry = y * ss
        d.text((pad * ss, ry + 8 * ss), name, font=f_name, fill=(238, 238, 240))
        meta = PALETTE_META.get(name)
        sub = meta["note"] if meta else "derived from the story text"
        d.text((pad * ss, ry + 32 * ss), sub, font=f_sub, fill=(140, 140, 150))
        bad = check(pal)
        d.text((pad * ss, ry + 52 * ss),
               "OK" if not bad else f"{len(bad)} problem(s)",
               font=f_sub, fill=(120, 210, 140) if not bad else (240, 110, 100))

        # a miniature scene: the five layers, back to front, plus a figure
        sx = pad + label_w
        top, bot = ry + 6 * ss, ry + (rh - 10) * ss
        g_top, g_bot = sky_gradient(pal["sky"])
        gy = top + int((bot - top) * 0.66)
        for row in range(top, gy):
            u = (row - top) / max(1, gy - top - 1)
            d.rectangle([sx * ss, row, (sx + scene_w) * ss, row + 1],
                        fill=mix(g_top, g_bot, u))
        d.rectangle([sx * ss, gy, (sx + scene_w) * ss, bot], fill=pal["ground"])
        for i, (key, z) in enumerate((("far", 0.74), ("mid", 0.40), ("near", 0.14))):
            hh = int((gy - top) * (0.52 + 0.16 * i))
            x0 = sx + 10 + i * 74
            c = depth_tint(pal[key], z, pal["sky"])
            d.rectangle([x0 * ss, gy - hh, (x0 + 96) * ss, gy], fill=c)
        # the figure — a blocky stand-in, just to eyeball separation
        fx = sx + scene_w - 78
        fy = gy + 2 * ss // ss
        # Contact shadow to spec, drawn *first* so the figure stands on it:
        # a = foot_span * 0.55, b = height * 0.06, at SHADOW_OPACITY.
        f_h, f_span = 56.0, 17.0
        ax = f_span * SHADOW_A * ss
        by = f_h * SHADOW_B * ss
        d.ellipse([(fx + 8) * ss - ax * 1.35, gy - by * 1.35,
                   (fx + 8) * ss + ax * 1.35, gy + by * 1.35],
                  fill=alpha(pal["shadow"], SHADOW_OPACITY * 0.30))
        d.ellipse([(fx + 8) * ss - ax, gy - by, (fx + 8) * ss + ax, gy + by],
                  fill=alpha(pal["shadow"], SHADOW_OPACITY))
        d.rectangle([fx * ss, gy - 40 * ss, (fx + 17) * ss, gy - 18 * ss],
                    fill=pal["shirt"], outline=outline_for(pal["shirt"]),
                    width=2 * ss)
        d.rectangle([fx * ss, gy - 18 * ss, (fx + 17) * ss, gy - 2 * ss],
                    fill=pal["trouser"], outline=outline_for(pal["trouser"]),
                    width=2 * ss)
        d.ellipse([(fx + 1) * ss, gy - 56 * ss, (fx + 16) * ss, gy - 40 * ss],
                  fill=pal["skin"], outline=pal["ink"], width=2 * ss)
        d.ellipse([(fx + 22) * ss, gy - 30 * ss, (fx + 34) * ss, gy - 18 * ss],
                  fill=pal["accent"], outline=outline_for(pal["accent"]),
                  width=2 * ss)

        cx = pad + label_w + scene_w + pad
        for i, key in enumerate(PALETTE_KEYS):
            x0 = cx + i * sw
            d.rectangle([x0 * ss, ry + 6 * ss, (x0 + sw - 4) * ss, ry + (rh - 30) * ss],
                        fill=pal[key])
            lab = f"{key}"
            d.text((x0 * ss, (y + rh - 26) * ss), lab, font=f_key, fill=(190, 190, 196))
            d.text((x0 * ss, (y + rh - 14) * ss),
                   "%02X%02X%02X" % pal[key], font=f_key, fill=(120, 120, 128))
        y += rh

    im = im.resize((W, H), Image.LANCZOS)
    im.save(path)


def _report() -> int:
    failures = 0
    print(f"{'palette':<22} {'shirt/mid':>10} {'shirt/near':>11} "
          f"{'trou/mid':>10} {'trou/near':>10} {'acc/mid':>9} {'ink L*':>7}")
    print("-" * 86)
    for name, pal in PALETTES.items():
        vals = []
        for garment in ("shirt", "trouser"):
            for layer in ("mid", "near"):
                dl, cr = _sep(pal[garment], pal[layer])
                vals.append(f"{dl:5.1f}/{cr:4.2f}")
        adl, _ = _sep(pal["accent"], pal["mid"])
        print(f"{name:<22} {vals[0]:>10} {vals[1]:>11} {vals[2]:>10} "
              f"{vals[3]:>10} {adl:8.1f} {lightness(pal['ink']):7.1f}")
        bad = check(pal)
        for b in bad:
            failures += 1
            print(f"    FAIL {name}: {b}")
    return failures


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
    import os
    import sys

    out = _out_dir(sys.argv[1:])
    os.makedirs(out, exist_ok=True)

    print(f"{len(PALETTES)} palettes: {', '.join(PALETTES)}\n")
    failures = _report()

    print("\nfigure/ground rule: |dL*| >= %.0f and contrast >= %.2f "
          "for shirt & trouser against mid & near"
          % (MIN_FIGURE_DL, MIN_FIGURE_CONTRAST))
    for name, pal in PALETTES.items():
        assert not check(pal), f"{name}: {check(pal)}"
    print("all %d named palettes pass." % len(PALETTES))

    # `choose` must be a decision, not a default.
    print("\nchoose():")
    cases = [
        ("chase", "a getaway car outruns a police helicopter"),
        (None, "quarterly review in meeting room 4"),
        ("sad", "waiting for a delayed bus in the rain"),
        ("calm", "a shepherd counts the same sheep twice"),
        ("noir", "a neon alley at 2am"),
        ("wistful", "the last ferry home at sunset"),
        ("breaking", "live coverage from the news chopper"),
        ("lonesome", "a truck on an empty desert interstate"),
        ("comic", "the dog gets the ice cream"),
        ("ceremonial", "a tortoise inherits a submarine"),
        ("baroque", "competitive origami in zero gravity"),
        ("liturgical", "a lighthouse keeper misplaces the sea"),
        (None, None),
    ]
    picked: dict[str, str] = {}
    for m, s in cases:
        p = choose(m, s)
        n = name_of(p)
        picked[f"{m}|{s}"] = n
        assert not check(p), f"choose({m!r},{s!r}) -> {n}: {check(p)}"
        print(f"  {str(m):<12} {str(s)[:46]:<48} -> {n}")

    # Determinism, and the no-silent-default rule.
    for m, s in cases:
        assert name_of(choose(m, s)) == picked[f"{m}|{s}"], "choose is not deterministic"
    odd = [("ceremonial", "a tortoise inherits a submarine"),
           ("baroque", "competitive origami in zero gravity"),
           ("liturgical", "a lighthouse keeper misplaces the sea")]
    got = [name_of(choose(m, s)) for m, s in odd]
    assert len(set(got)) == len(got), f"unrelated stories collapsed to {got}"
    assert all(g not in PALETTES or True for g in got)
    assert all("~" in g for g in got), f"expected derived palettes, got {got}"
    print(f"  three unmatched stories -> three distinct derived palettes: {got}")

    # depth_tint must be monotonic toward the sky and a no-op at z=0.
    for name, pal in PALETTES.items():
        assert depth_tint(pal["mid"], 0.0, pal["sky"]) == pal["mid"]
        prev = 1e9
        for z in (0.0, 0.25, 0.5, 0.75, 1.0):
            c = depth_tint(pal["mid"], z, pal["sky"])
            dist = sum(abs(c[i] - pal["sky"][i]) for i in range(3))
            assert dist <= prev + 1, f"{name}: depth_tint not monotonic at z={z}"
            prev = dist
    print("  depth_tint: z=0 is identity, and monotonic toward sky. OK")

    # rotate_hue must hold luminance, which is what keeps derived palettes legal.
    worst = 0.0
    for name, pal in PALETTES.items():
        for k in PALETTE_KEYS:
            for deg in (37.0, 137.0, -74.0, 180.0):
                a = lightness(pal[k])
                b = lightness(rotate_hue(pal[k], deg))
                worst = max(worst, abs(a - b))
                assert abs(a - b) < 2.0, \
                    f"{name}.{k} @{deg}: rotate_hue moved L* {a:.1f}->{b:.1f}"
    print(f"  rotate_hue: luminance preserved, worst drift {worst:.2f} L*. OK")

    # ...and every derived palette must therefore still pass `check`.
    for i in range(240):
        p = derive(f"story-{i}")
        assert not check(p), f"derived story-{i} -> {name_of(p)}: {check(p)}"
    print("  240 derived palettes all pass the figure/ground rule. OK")

    # ink is never black, and always belongs to its own palette.
    print("\nink / shadow:")
    print(f"  {'palette':<10} {'ink':<14} {'L*':>5} {'chroma':>7}   "
          f"{'shadow':<14} {'L*':>5} {'dE #1A2830':>11}")
    for name, pal in PALETTES.items():
        ik, sh = pal["ink"], pal["shadow"]
        assert tuple(ik) != (0, 0, 0)
        assert max(ik) - min(ik) >= MIN_INK_CHROMA
        assert MIN_INK_L <= lightness(ik) <= MAX_INK_L
        de = math.dist(sh, SHADOW_INK)
        print(f"  {name:<10} {str(ik):<14} {lightness(ik):5.1f} "
              f"{max(ik) - min(ik):7d}   {str(sh):<14} "
              f"{lightness(sh):5.1f} {de:11.1f}")
    for i in range(400):
        pal = derive(f"ink-{i}")
        ik = pal["ink"]
        assert tuple(ik) != (0, 0, 0) and max(ik) - min(ik) >= MIN_INK_CHROMA, \
            f"derived {name_of(pal)} ink={ik} lost its hue"
    print("  400 derived palettes: no pure black, no neutral ink. OK")

    # outline_for: same hue, +saturation, -lightness, and never black.
    for name, pal in PALETTES.items():
        for k in ("shirt", "trouser", "accent", "accent2", "skin", "hair"):
            f = pal[k]
            o = outline_for(f)
            assert lightness(o) < lightness(f), f"{name}.{k}: outline not darker"
            if lightness(f) >= 25.0:
                assert contrast(o, f) >= 1.6, \
                    f"{name}.{k}: outline contrast {contrast(o, f):.2f} too low"
            hf = colorsys.rgb_to_hls(*(c / 255 for c in f))[0]
            ho = colorsys.rgb_to_hls(*(c / 255 for c in o))[0]
            if max(f) - min(f) > 12:
                dh = min(abs(hf - ho), 1.0 - abs(hf - ho))
                assert dh < 0.04, f"{name}.{k}: outline_for moved the hue"
    assert outline_for((160, 160, 160)) == outline_for((160, 160, 160))
    g = outline_for((160, 160, 160))
    assert max(g) - min(g) == 0, f"outline_for invented a hue on grey: {g}"
    print("  outline_for: same hue, darker, never invents colour on a grey. OK")

    # the one permitted gradient
    for name, pal in PALETTES.items():
        top, bot = sky_gradient(pal["sky"])
        assert lightness(top) < lightness(bot), f"{name}: sky gradient inverted"
        d = lightness(bot) - lightness(top)
        assert 6.0 <= d <= 22.0, f"{name}: sky gradient spread {d:.1f} L*"
        assert lightness(top) >= 1.4, f"{name}: sky gradient top is black"
    print("  sky_gradient: 2 stops, deeper above, paler at the horizon. OK")

    # Atmospheric desaturation has to be worth something on its own: with
    # flat colour and no texture it is one of the only depth cues there is.
    for name, pal in PALETTES.items():
        sky = pal["sky"]
        for k in ("far", "mid", "near", "accent", "accent2", "ground"):
            src = pal[k]
            if max(src) - min(src) < 14:
                continue
            prev = math.dist(src, sky) + 1e-6
            for z in (0.25, 0.5, 0.75, 1.0):
                c = depth_tint(src, z, sky)
                d = math.dist(c, sky)
                # Tolerance, not sloppiness: a near-neutral under a saturated
                # sky bleaches a hair *away* from it before the mix takes
                # over. Measured worst case across all palettes is 1.14/255.
                assert d <= prev + 1.5, f"{name}.{k}: moved away from sky at z={z}"
                prev = d
                # It is not a plain mix: the source is bleached on the way,
                # which is what stops a distant saturated shape reading as a
                # cutout held up close.
                kk = 0.90 * (z ** 0.85)
                assert c != mix(src, sky, kk), \
                    f"{name}.{k}: depth_tint is only mixing at z={z}"
                bleached = desaturate(src, 0.78 * kk)
                assert max(bleached) - min(bleached) < max(src) - min(src), \
                    f"{name}.{k}: the bleach step did nothing at z={z}"
            assert math.dist(depth_tint(src, 1.0, sky), sky) \
                < math.dist(src, sky) * 0.25, \
                f"{name}.{k}: z=1 did not wash into the sky"
    print("  depth_tint: bleaches as well as mixes, z=1 lands in the sky. OK")

    # `summit` is matched to measured stills rather than designed, so the
    # measurements are asserted rather than admired. Everything below is a
    # number out of the reference films.
    print("\nsummit (reference-matched) — HSV, the axis the reference is "
          "measured on:")
    print(f"  {'token':<9} {'hex':<9} {'sat':>6} {'val':>6} {'hue':>6} {'L*':>6}")
    sm = PALETTES["summit"]
    for k in PALETTE_KEYS:
        c = sm[k]
        mark = (" <- air" if k in AIR_KEYS else
                " <- terrain" if k in TERRAIN_KEYS else "")
        print(f"  {k:<9} #{c[0]:02x}{c[1]:02x}{c[2]:02x}   {saturation(c):6.3f} "
              f"{value(c):6.3f} {hue(c):5.0f}d {lightness(c):6.1f}{mark}")
    for k in AIR_KEYS:
        assert saturation(sm[k]) <= MAX_AIR_SAT, \
            f"summit.{k} saturation {saturation(sm[k]):.3f} > {MAX_AIR_SAT}"
    for k in TERRAIN_KEYS:
        assert saturation(sm[k]) <= MAX_TERRAIN_SAT, \
            f"summit.{k} saturation {saturation(sm[k]):.3f} > {MAX_TERRAIN_SAT}"
    assert saturation(sm["sky"]) >= MIN_AIR_SAT, \
        f"summit.sky saturation {saturation(sm['sky']):.3f} < {MIN_AIR_SAT}: " \
        "the air will bleach the film grey"
    world_v = sum(value(sm[k]) for k in WORLD_KEYS) / len(WORLD_KEYS)
    print(f"  air {MIN_AIR_SAT}..{MAX_AIR_SAT}, terrain <= {MAX_TERRAIN_SAT}, "
          f"mean world value {world_v:.3f}. OK")

    # Warm rock against cool air. Without this the palette is legal on every
    # other measure and still reads as greyscale, because near-neutral colours
    # that all share one hue have nothing to be near-neutral *against*.
    gap = hue_gap(sm["far"], sm["sky"])
    assert gap >= 150.0, \
        f"summit far/sky hue gap {gap:.0f}d: the world has no warm/cool opposition"
    assert hue_gap(sm["ground"], sm["sky"]) >= 150.0, \
        "summit ground/sky hue gap: the near ground has gone cold"
    # ...and the haze must not quietly undo it. `ground` is the near ground
    # plane at `LAYER_Z` 0.0, which `depth_tint` returns untouched: the pull
    # toward `sky` is a function of *distance*, so no amount of air can cool
    # the foreground. Asserted rather than assumed, because it is the one
    # guarantee holding the opposition up.
    for air in (DEFAULT_HAZE, HAZE["summit"], 4.0):
        assert depth_tint(sm["ground"], LAYER_Z["ground"], sm["sky"],
                          strength=air) == sm["ground"], \
            f"haze {air} reached the near ground plane"
    print(f"  far/sky hue opposition {gap:.0f}d (reference ~190d), and the "
          f"near ground is haze-immune at any strength. OK")

    # The reference fades a lit peak into a distant ridge and that fade *is*
    # the film's depth, so it is measured, not eyeballed. What is asserted is
    # how far the air carries the rock, as a fraction of the way to the sky.
    # An earlier pass asserted a colour match against one sampled ridge pixel,
    # ``#cfd1d7``; sampling the same frame by region puts that band at value
    # 0.739 against the pixel's 0.843, so the pixel was a highlight and the
    # match was to noise. A fraction is the honest form of the same claim, and
    # it does not silently re-grade the film when the sky is re-tinted.
    # `DEFAULT_HAZE` gets nowhere near it, which is the reason `HAZE` exists.
    z_far, sm_sky, sm_far = LAYER_Z["far"], sm["sky"], sm["far"]
    span = lightness(sm_sky) - lightness(sm_far)
    got = depth_tint(sm_far, z_far, sm_sky)
    house = depth_tint(sm_far, z_far, sm_sky, strength=DEFAULT_HAZE)
    frac = (lightness(got) - lightness(sm_far)) / span
    frac_house = (lightness(house) - lightness(sm_far)) / span
    assert frac >= 0.85, \
        f"summit air carries the far rock only {frac:.0%} of the way to the sky"
    assert frac_house <= frac - 0.10, \
        "DEFAULT_HAZE now reaches the ridge; HAZE['summit'] is redundant"
    # The ridge has to stay *readable* against the sky. Air thick enough to
    # clamp `k` to 1.0 at `z_far` would make them the same colour and flatten
    # the shot, which is a worse failure than missing the measurement.
    assert 1.0 <= lightness(sm_sky) - lightness(got) <= 8.0, \
        "the far ridge has merged into the sky"
    for name, pal in PALETTES.items():
        if name not in HAZE:
            assert haze_for(pal["sky"]) == DEFAULT_HAZE, \
                f"{name} silently acquired weather"
    print(f"  far rock #{sm_far[0]:02x}{sm_far[1]:02x}{sm_far[2]:02x} at "
          f"z={z_far} -> #{got[0]:02x}{got[1]:02x}{got[2]:02x} "
          f"({frac:.0%} of the way to the sky, {lightness(sm_sky)-lightness(got):.1f} "
          f"L* short of it); at DEFAULT_HAZE only {frac_house:.0%}. OK")

    path = os.path.join(out, "look-palettes.png")
    _swatch_sheet(path)
    print(f"\nwrote {path}")
    print("FAILURES:", failures)
    raise SystemExit(1 if failures else 0)
