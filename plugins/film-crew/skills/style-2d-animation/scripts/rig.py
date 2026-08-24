"""The character rig — skeleton, solver, and flat-vector renderer.

A character in this style is never a bitmap that moves. It is fifteen angles
evaluated into scene-unit points by :func:`solve`, and drawn as tapered shapes
by :func:`draw`. Everything downstream — cycles, blends, smears — operates on
the angles, which is what lets a wave compose with a lean and a walk retime for
free.

Read ``reference/rig.md`` first; this module implements it literally.

    * ``x`` right, ``y`` down (PIL's convention), scene units, not pixels.
    * Angles are degrees, **positive is clockwise on screen**, and every angle
      is measured relative to its parent bone's direction.
    * ``pelvis`` is the root: it carries a position, never an angle.

The module deliberately depends on nothing else in the style — it is handed a
palette object and reads keys off it. That is what lets the set, look and shot
layers be written in parallel against this file.

Everything is deterministic: no randomness, no clock, no module state. The same
pose, palette and ``unit`` produce identical pixels on every run.
"""

from __future__ import annotations

import colorsys
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# --------------------------------------------------------------- constants ---

SS = 3  # supersample factor: draw at 3x, composite down through LANCZOS

DEFAULT_HEIGHT = 18.0  # scene units, head to heel

#: Every joint that carries an angle. Four chains hanging off the pelvis.
JOINTS = (
    "spine", "neck", "head",
    "shoulder.l", "elbow.l", "wrist.l",
    "shoulder.r", "elbow.r", "wrist.r",
    "hip.l", "knee.l", "ankle.l",
    "hip.r", "knee.r", "ankle.r",
)

#: The neutral pose — every joint zero. A missing joint in a pose *is* zero,
#: so a pose only ever states what it changes.
REST: dict[str, float] = {name: 0.0 for name in JOINTS}

#: Bone name -> length as a fraction of total height ``H``.
#:
#: These are cartoon proportions, not human ones: the figure stands about
#: **4.3 heads tall**, where a real adult is seven and a half. The genre reads
#: compact — a big head carries the acting and short legs carry the comedy.
#: Override them per character with ``pose["bones"]`` (see :func:`bones_for`).
BONES: dict[str, float] = {
    "spine": 0.262,       # pelvis -> chest
    "neck": 0.042,        # chest -> head base
    "head": 0.247,        # head base -> crown
    "upper_arm": 0.146,
    "forearm": 0.136,
    "hand": 0.052,
    "thigh": 0.206,
    "shin": 0.190,
    "foot": 0.070,
}

#: Ready-made builds. A cast in which everyone is the same shape reads as one
#: character in different shirts. Pass by name: ``pose["bones"] = "kid"``.
BONE_VARIANTS: dict[str, dict[str, float]] = {
    "default": {},
    "kid": {"head": 0.290, "spine": 0.222, "thigh": 0.196, "shin": 0.180,
            "upper_arm": 0.130, "forearm": 0.120},
    "heavy": {"head": 0.240, "spine": 0.252, "thigh": 0.208, "shin": 0.192,
              "upper_arm": 0.140, "forearm": 0.128},
    "lanky": {"head": 0.222, "spine": 0.252, "thigh": 0.246, "shin": 0.228,
              "upper_arm": 0.162, "forearm": 0.152},
}


def bones_for(pose: dict | None) -> dict[str, float]:
    """The bone table a pose is drawn with.

    ``pose["bones"]`` is optional and may be a name from :data:`BONE_VARIANTS`
    or a partial dict of overrides. Anything absent falls back to :data:`BONES`,
    so a pose that says nothing gets the house build.
    """
    over = (pose or {}).get("bones")
    if isinstance(over, str):
        over = BONE_VARIANTS.get(over, {})
    if not isinstance(over, dict) or not over:
        return dict(BONES)
    out = dict(BONES)
    for k, v in over.items():
        if k in out:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out

#: Drawn widths, also fractions of ``H``. A limb is tapered: it is drawn from
#: the first width to the second, with a circle of the matching diameter at
#: each end, so a joint can never show a seam.
WIDTHS: dict[str, float] = {
    "neck": 0.058,
    "chest": 0.178,
    "waist": 0.142,
    "hip": 0.162,
    "upper_arm": 0.064,
    "elbow": 0.054,
    "wrist": 0.044,
    "hand": 0.062,
    "thigh": 0.092,
    "knee": 0.072,
    "ankle": 0.050,
    "shoe": 0.070,
}

HEAD_W = 0.222          # head width, fraction of H — about as wide as it is tall
SHOULDER_HALF = 0.105   # shoulder half-width
HIP_HALF = 0.078        # hip half-width

#: The rig is drawn three-quarters-on. The left/right offset of the shoulders
#: and hips is mostly *depth*, so only this fraction of it projects onto the
#: screen — enough to separate the near and far limbs, not enough to read as a
#: twist.
DEPTH = 0.30

LEG = BONES["thigh"] + BONES["shin"]  # hip -> ankle, fraction of H
SOLE = 0.034                          # ankle -> ground, i.e. shoe thickness

#: Pelvis height above the ground when standing, as a fraction of ``H``. The
#: renderer needs this to stand a character on a ground line:
#:     pelvis_y = ground_y - PELVIS_TO_SOLE * height
#: The 0.965 is a soft knee: a leg locked dead straight cannot be reached by
#: two-bone IK and reads as a mannequin, so standing keeps a little bend.
PELVIS_TO_SOLE = LEG * 0.965 + SOLE

#: Crown to sole, standing. ~0.99 H — see the note in the module tests.
CROWN_TO_SOLE = BONES["spine"] + BONES["neck"] + BONES["head"] + PELVIS_TO_SOLE

#: How many head-heights tall the default build stands. The genre lives
#: between 4 and 4.5; five or more starts to read as an explainer video.
HEADS_TALL = CROWN_TO_SOLE / (BONES["head"] * 0.94)

#: Stroke weights, as fractions of ``H``. They are **not** equal: uniform line
#: weight is a named failure of this style. Calibrated so that a figure drawn
#: 700 px tall carries a 3.5 px body outline and 2 px face detail, and both
#: scale with ``unit`` from there.
INK_W = 3.5 / 700.0
FACE_W = 2.0 / 700.0

SCLERA = (250, 249, 244)  # the one colour not taken from the palette

_FALLBACK = {
    "skin": (240, 197, 160), "hair": (58, 44, 38), "shirt": (206, 74, 62),
    "trouser": (52, 68, 104), "shoe": (38, 38, 46), "ink": (28, 26, 34),
    "accent": (240, 180, 60), "accent2": (70, 190, 180),
    "shadow": (24, 22, 40), "sky": (198, 214, 228),
}


def ground_pelvis(ground_y: float, height: float = DEFAULT_HEIGHT,
                  bones: dict | None = None) -> float:
    """Pelvis ``y`` that stands a character of ``height`` on ``ground_y``.

    Pass ``bones`` (or a pose) when the character is not the default build, or
    a short-legged variant will float.
    """
    if bones:
        b = bones_for(bones if "bones" in bones else {"bones": bones})
        leg = (b["thigh"] + b["shin"]) * 0.965 + SOLE
        return ground_y - leg * height
    return ground_y - PELVIS_TO_SOLE * height


def squash_scale(squash: float) -> tuple[float, float]:
    """``squash`` -> the ``(x, y)`` scale factors that realise it.

    Squash and stretch **preserve area**: the reference values are pairs like
    0.75 tall x 1.30 wide, so width is the reciprocal of height, not its
    inverse square root. A character that loses volume when it lands reads as
    deflating rather than as compressing.
    """
    sy = max(0.25, float(squash))
    return (1.0 / sy, sy)


def outline_of(fill, *, darken: float = 0.40, saturate: float = 0.10,
               floor: float = 0.06):
    """The outline colour for a fill: same hue, a little more saturated, a lot
    darker.

    Pure black outlines are what make flat-vector work read as clip-art
    stickers. Every body outline in :func:`draw` comes from here; the palette's
    ``ink`` is reserved for facial features, where a true dark line is wanted.
    """
    r, g, b = (max(0, min(255, int(c))) / 255.0 for c in fill)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(floor, l - darken)
    s = min(1.0, s + saturate)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


# ------------------------------------------------------------------ maths ----


def _rot(v, deg):
    """Rotate ``v`` by ``deg``. Positive is clockwise on screen (y points down)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(v, k):
    return (v[0] * k, v[1] * k)


def _neg(v):
    return (-v[0], -v[1])


def _perp(v):
    """The vector 90 degrees clockwise from ``v``."""
    return (-v[1], v[0])


def _norm(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-9 else (0.0, -1.0)


def signed_angle(u, v) -> float:
    """Degrees from ``u`` to ``v``, positive clockwise on screen.

    The inverse of :func:`_rot`, and what :mod:`poses` uses to turn a solved
    limb direction back into a joint angle.
    """
    cross = u[0] * v[1] - u[1] * v[0]
    dot = u[0] * v[0] + u[1] * v[1]
    return math.degrees(math.atan2(cross, dot))


# --------------------------------------------------------------- the solve ---


def solve(pose: dict) -> dict:
    """Pose -> absolute scene-unit points for every joint.

    Pure: no drawing, no globals, no module state. Applies ``facing``,
    ``height``, ``squash`` and ``tilt``.

    Returns ``pelvis, chest, head_base, crown``, and ``shoulder/elbow/wrist/
    hand`` and ``hip/knee/ankle/foot`` for both ``.l`` and ``.r``.

    ``squash`` scales the body along its own axis and compensates the width as
    ``1/squash``, so **area** is preserved (0.75 tall reads as 1.30 wide);
    ``tilt`` then rotates the whole body about the pelvis, and ``facing``
    mirrors the result. Angles are never mirrored — a pose reads the same
    whichever way the character faces.

    ``pose["bones"]`` optionally overrides the build, by name or partial dict.
    """
    pose = pose or {}
    H = float(pose.get("height", DEFAULT_HEIGHT))
    src = pose.get("joints") or {}

    def a(name: str) -> float:
        return float(src.get(name, 0.0))

    L = {k: v * H for k, v in bones_for(pose).items()}
    up, down = (0.0, -1.0), (0.0, 1.0)

    pelvis = (0.0, 0.0)
    d_spine = _rot(up, a("spine"))
    chest = _add(pelvis, _mul(d_spine, L["spine"]))
    d_neck = _rot(d_spine, a("neck"))
    head_base = _add(chest, _mul(d_neck, L["neck"]))
    d_head = _rot(d_neck, a("head"))
    crown = _add(head_base, _mul(d_head, L["head"]))

    pts = {"pelvis": pelvis, "chest": chest, "head_base": head_base, "crown": crown}

    across = _perp(d_spine)  # the shoulder line, forward-positive
    for side, sgn in (("l", -1.0), ("r", 1.0)):
        shoulder = _add(chest, _mul(across, sgn * SHOULDER_HALF * DEPTH * H))
        d_upper = _rot(_neg(d_spine), a("shoulder." + side))
        elbow = _add(shoulder, _mul(d_upper, L["upper_arm"]))
        d_fore = _rot(d_upper, a("elbow." + side))
        wrist = _add(elbow, _mul(d_fore, L["forearm"]))
        d_hand = _rot(d_fore, a("wrist." + side))
        hand = _add(wrist, _mul(d_hand, L["hand"]))

        hip = (sgn * HIP_HALF * DEPTH * H, 0.0)
        d_thigh = _rot(down, a("hip." + side))
        knee = _add(hip, _mul(d_thigh, L["thigh"]))
        d_shin = _rot(d_thigh, a("knee." + side))
        ankle = _add(knee, _mul(d_shin, L["shin"]))
        d_foot = _rot(d_shin, a("ankle." + side))
        foot = _add(ankle, _mul(d_foot, L["foot"]))

        pts["shoulder." + side] = shoulder
        pts["elbow." + side] = elbow
        pts["wrist." + side] = wrist
        pts["hand." + side] = hand
        pts["hip." + side] = hip
        pts["knee." + side] = knee
        pts["ankle." + side] = ankle
        pts["foot." + side] = foot

    squash = max(0.25, float(pose.get("squash", 1.0)))
    sx, sy = squash_scale(squash)
    tilt = float(pose.get("tilt", 0.0))
    facing = -1.0 if float(pose.get("facing", 1)) < 0 else 1.0
    at = pose.get("at") or (50.0, ground_pelvis(44.0, H))
    ax, ay = float(at[0]), float(at[1])

    out = {}
    for name, (x, y) in pts.items():
        x, y = x * sx, y * sy
        if tilt:
            x, y = _rot((x, y), tilt)
        if facing < 0:
            x = -x
        out[name] = (x + ax, y + ay)
    return out


def bbox(pose: dict) -> tuple[float, float, float, float]:
    """Scene-unit ``(x0, y0, x1, y1)`` the drawn character occupies.

    Generous by a hair: it includes the ink outline and the drawn volume around
    each joint, so the compiler can use it to keep actors apart and to frame a
    shot without clipping a hand.
    """
    P = solve(pose)
    H = float(pose.get("height", DEFAULT_HEIGHT))
    squash = max(0.25, float(pose.get("squash", 1.0)))
    w = squash_scale(squash)[0]  # widths are scaled with the body
    pad = INK_W * H * 1.5
    B = bones_for(pose)

    head_r = max(HEAD_W * 0.5 * w, B["head"] * 0.58) * H
    radii = [
        ("pelvis", WIDTHS["hip"] * 0.5 * w * H),
        ("chest", WIDTHS["chest"] * 0.5 * w * H),
        ("head_base", head_r), ("crown", head_r),
    ]
    for s in ("l", "r"):
        radii += [
            ("shoulder." + s, WIDTHS["upper_arm"] * 0.5 * w * H),
            ("elbow." + s, WIDTHS["elbow"] * 0.5 * w * H),
            ("wrist." + s, WIDTHS["wrist"] * 0.5 * w * H),
            ("hand." + s, WIDTHS["hand"] * 0.80 * w * H),
            ("hip." + s, WIDTHS["thigh"] * 0.5 * w * H),
            ("knee." + s, WIDTHS["knee"] * 0.5 * w * H),
            ("ankle." + s, WIDTHS["ankle"] * 0.5 * w * H),
            ("foot." + s, WIDTHS["shoe"] * 0.62 * w * H),
        ]

    xs0, ys0, xs1, ys1 = [], [], [], []
    for name, r in radii:
        x, y = P[name]
        xs0.append(x - r); xs1.append(x + r)
        ys0.append(y - r); ys1.append(y + r)
    return (min(xs0) - pad, min(ys0) - pad, max(xs1) + pad, max(ys1) + pad)


# ------------------------------------------------------------------ colour ---


def _as_rgb(v, fallback):
    if v is None:
        return fallback
    if isinstance(v, str):
        s = v.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) >= 6:
            try:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except ValueError:
                return fallback
        return fallback
    try:
        r, g, b = (int(v[0]), int(v[1]), int(v[2]))
    except Exception:
        return fallback
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _pick(look, key):
    """Read one colour off a palette object without caring what it is."""
    fallback = _FALLBACK.get(key, (128, 128, 128))
    if look is None:
        return fallback
    v = None
    if isinstance(look, dict):
        v = look.get(key)
    else:
        try:
            v = look[key]
        except Exception:
            v = None
        if v is None:
            getter = getattr(look, "get", None)
            if callable(getter):
                try:
                    v = getter(key, None)
                except Exception:
                    v = None
        if v is None:
            v = getattr(look, key, None)
    return _as_rgb(v, fallback)


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _shade(c, shadow, t):
    """Push a fill towards the palette's shadow — the far side of the body."""
    return _mix(c, shadow, t)


def _depth(c, haze, z):
    """Desaturate and lift a colour for distance. ``z`` 1 is here, 0 is far."""
    z = max(0.0, min(1.0, float(z)))
    if z >= 0.999:
        return c
    grey = sum(c) / 3.0
    d = 1.0 - z
    c = tuple(c[i] + (grey - c[i]) * (0.55 * d) for i in range(3))
    return tuple(int(round(c[i] + (haze[i] - c[i]) * (0.50 * d))) for i in range(3))


# ---------------------------------------------------------------- drawing ----


def _limb(d, a, b, w0, w1, fill, caps=(True, True)):
    """A tapered bone: a quad from width ``w0`` to ``w1``, capped by a circle
    at each end of exactly the matching diameter. No seam is possible."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n > 1e-6:
        px, py = -dy / n * 0.5, dx / n * 0.5
        d.polygon([
            (a[0] + px * w0, a[1] + py * w0), (b[0] + px * w1, b[1] + py * w1),
            (b[0] - px * w1, b[1] - py * w1), (a[0] - px * w0, a[1] - py * w0),
        ], fill=fill)
    if caps[0]:
        d.ellipse([a[0] - w0 / 2, a[1] - w0 / 2, a[0] + w0 / 2, a[1] + w0 / 2], fill=fill)
    if caps[1]:
        d.ellipse([b[0] - w1 / 2, b[1] - w1 / 2, b[0] + w1 / 2, b[1] + w1 / 2], fill=fill)


def _oval(d, c, u, ru, rv, fill, n=56):
    """An ellipse with radius ``ru`` along ``u`` and ``rv`` across it."""
    v = _perp(u)
    pts = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        ca, sa = math.cos(a) * ru, math.sin(a) * rv
        pts.append((c[0] + u[0] * ca + v[0] * sa, c[1] + u[1] * ca + v[1] * sa))
    d.polygon(pts, fill=fill)


def _arc_line(d, pts, w, fill):
    """A thick polyline with round caps and joins."""
    for i in range(len(pts) - 1):
        _limb(d, pts[i], pts[i + 1], w, w, fill)


def _mitten(d, wrist, tip, w, swell, fill):
    """A hand: a mitten with three fingers and a thumb.

    Never five anatomically correct fingers. At the size these characters are
    seen, five fingers collapse into a fringe and take the silhouette with
    them — the hand stops reading as a hand. Three lumps and a thumb read
    instantly, and are what the genre has used for eighty years.

    Drawn as a union of a palm and four bumps, so one outline pass followed by
    one fill pass leaves no seam anywhere.
    """
    u = _norm((tip[0] - wrist[0], tip[1] - wrist[1]))
    v = _perp(u)

    def PT(a, b):
        return (wrist[0] + u[0] * a * w + v[0] * b * w,
                wrist[1] + u[1] * a * w + v[1] * b * w)

    palm = PT(0.44, 0.0)
    _oval(d, palm, u, w * 0.58 + swell, w * 0.54 + swell, fill)
    _limb(d, wrist, palm, w * 0.72 + 2 * swell, w * 1.02 + 2 * swell, fill)
    for k in (-0.30, 0.0, 0.30):                      # three fingers
        f = PT(0.88, k)
        r = w * (0.23 if k else 0.25)
        _limb(d, f, f, 2 * r + 2 * swell, 2 * r + 2 * swell, fill)
    th = PT(0.30, 0.52)                               # and a thumb
    _limb(d, palm, th, w * 0.38 + 2 * swell, w * 0.40 + 2 * swell, fill)


def _downsample(tile: Image.Image, w: int, h: int) -> Image.Image:
    """LANCZOS down to 1x through premultiplied alpha, so the ink edge does not
    bleed black into the transparent surround."""
    a = np.asarray(tile, dtype=np.float32).copy()
    al = a[..., 3:4] * (1.0 / 255.0)
    a[..., :3] *= al
    small = Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA").resize(
        (max(1, w), max(1, h)), Image.LANCZOS)
    b = np.asarray(small, dtype=np.float32).copy()
    bl = np.maximum(b[..., 3:4] * (1.0 / 255.0), 1e-4)
    b[..., :3] /= bl
    return Image.fromarray(np.clip(b + 0.5, 0, 255).astype(np.uint8), "RGBA")


# -------------------------------------------------------------------- face ---


def _curve(pts, n=9):
    """Quadratic Bezier through three control points, sampled smooth."""
    p0, p1, p2 = pts
    out = []
    for i in range(n):
        t = i / (n - 1)
        m = 1.0 - t
        out.append((m * m * p0[0] + 2 * m * t * p1[0] + t * t * p2[0],
                    m * m * p0[1] + 2 * m * t * p1[1] + t * t * p2[1]))
    return out


#: Brow presets. The brow carries more of the expression than the mouth does,
#: so each state is an explicit ``((tilt, lift), (tilt, lift))`` pair — far brow
#: first. Positive ``tilt`` drives the inner end (the one by the nose bridge)
#: **down**; ``lift`` raises the whole brow, in eye-radii. ``confused`` and
#: ``smug`` are asymmetric on purpose: that asymmetry *is* the expression.
BROWS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "neutral":   ((-2.0, 0.00), (0.0, -0.06)),
    "surprised": ((-9.0, 1.05), (-7.0, 0.96)),
    "angry":     ((29.0, -0.36), (25.0, -0.30)),
    "sad":       ((-30.0, 0.14), (-26.0, 0.08)),
    "confused":  ((-25.0, 0.90), (19.0, -0.18)),
    "strain":    ((17.0, -0.55), (14.0, -0.48)),
    "smug":      ((-19.0, 0.72), (6.0, -0.14)),
}


def _brow_pair(brow):
    """``pose["face"]["brow"]`` -> ``((tilt, lift), (tilt, lift))``.

    Accepts a name from :data:`BROWS` or the frozen ``-1..1`` scalar. The
    scalar path still produces a slightly asymmetric pair — a perfectly
    mirrored face reads as a mask.
    """
    if isinstance(brow, str):
        p = BROWS.get(brow.strip().lower())
        if p is not None:
            return p
        try:
            brow = float(brow)
        except ValueError:
            return BROWS["neutral"]
    try:
        b = max(-1.0, min(1.0, float(brow)))
    except (TypeError, ValueError):
        b = 0.0
    if b >= 0.0:
        far = (-2.0 - 7.0 * b, 1.05 * b)
    else:
        far = (-2.0 - 29.0 * b, 0.36 * b)
    return (far, (far[0] * 0.88, far[1] - 0.06))


def _draw_face(d, face, C, ink, fw, centre, up, fwd, rx, ry):
    """Eyes, brows and mouth. The face carries the acting, so the states are
    drawn to be distinct in silhouette at thumbnail size rather than to be
    anatomically polite. Ear and nose are drawn earlier, with the skull.

    Every measurement is a fraction of the drawn head, so a character built
    with a different ``BONES`` table gets a face that fits it. ``fw`` is the
    face stroke — finer than the body outline, on purpose."""
    def P(f, u):
        return (centre[0] + fwd[0] * f + up[0] * u, centre[1] + fwd[1] * f + up[1] * u)

    eyes = str(face.get("eyes", "open"))
    mouth = str(face.get("mouth", "line"))
    gaze = face.get("look") or (0.0, 0.0)
    gx = max(-1.0, min(1.0, float(gaze[0]))) if len(gaze) > 0 else 0.0
    gy = max(-1.0, min(1.0, float(gaze[1]))) if len(gaze) > 1 else 0.0

    # the two eyes of a three-quarter face: the far one smaller and nearer the
    # centre line, the near one out towards the nose
    far, near = 0.05 * rx, 0.70 * rx
    eye_u = -0.02 * ry
    k = 1.30 if eyes == "wide" else 1.0
    r_far, r_near = 0.158 * rx * k, 0.188 * rx * k

    for f, r in ((far, r_far), (near, r_near)):
        c = P(f, eye_u)
        if eyes == "shut":
            # a closed lid is a curve, never a half-drawn eye. Kept light and
            # short so it never fuses with the brow into one black bar.
            w = r * 1.25
            _arc_line(d, _curve([P(f - w, eye_u + 0.15 * r), P(f, eye_u - 0.95 * r),
                                 P(f + w, eye_u + 0.15 * r)]), fw * 1.30, ink)
            continue
        if eyes == "squint":
            # a narrowed eye still shows a pupil -- a solid slab reads as a
            # blindfold, not as suspicion
            _oval(d, c, fwd, r * 1.16 + fw * 0.8, r * 0.50 + fw * 0.8, ink)
            _oval(d, c, fwd, r * 1.16, r * 0.50, C["sclera"])
            pc = (c[0] + fwd[0] * gx * (r * 0.42), c[1] + fwd[1] * gx * (r * 0.42))
            _oval(d, pc, fwd, r * 0.44, r * 0.44, ink)
            _arc_line(d, _curve([P(f - r * 1.15, eye_u - 0.16 * r),
                                 P(f, eye_u - 0.62 * r),
                                 P(f + r * 1.15, eye_u - 0.16 * r)]), fw * 1.4, ink)
            continue
        _oval(d, c, fwd, r * 0.92 + fw * 0.85, r * 1.12 + fw * 0.85, ink)
        _oval(d, c, fwd, r * 0.92, r * 1.12, C["sclera"])
        pr = r * (0.38 if eyes == "wide" else 0.50)
        pc = (c[0] + fwd[0] * gx * (r * 0.34) + up[0] * (-gy * r * 0.46),
              c[1] + fwd[1] * gx * (r * 0.34) + up[1] * (-gy * r * 0.46))
        _oval(d, pc, fwd, pr, pr * 1.12, ink)
        if eyes == "dead":
            # a heavy lid over the top half of an open eye: unimpressed
            _limb(d, P(f - r * 1.0, eye_u + r * 0.66), P(f + r * 1.0, eye_u + r * 0.66),
                  r * 1.25, r * 1.25, ink)

    # brows: each one tilts and lifts independently, up to +/-30 degrees. They
    # are the heaviest thing on the face for a reason — the brow carries more
    # of the expression than the mouth does.
    (t_far, l_far), (t_near, l_near) = _brow_pair(face.get("brow", 0.0))
    for f, r, inner, tilt, lift in ((far, r_far, 1.0, t_far, l_far),
                                    (near, r_near, -1.0, t_near, l_near)):
        tilt = max(-30.0, min(30.0, float(tilt)))
        w = r * 1.40
        base = eye_u + r * 1.34 + 0.045 * rx + float(lift) * r * 0.62
        drop = math.tan(math.radians(tilt)) * w
        arch = r * 0.34 * (1.0 - 0.70 * min(1.0, abs(tilt) / 30.0))
        _arc_line(d, _curve([P(f + inner * w, base - drop),
                             P(f, base + arch),
                             P(f - inner * w, base + drop)], 9), fw * 1.85, ink)

    # mouth
    mf, mu = 0.34 * rx, -0.60 * ry
    mw = 0.412 * rx
    if mouth == "open":
        _oval(d, P(mf, mu), fwd, mw * 0.90, mw * 0.60, ink)
    elif mouth == "oh":
        _oval(d, P(mf, mu), fwd, mw * 0.52, mw * 0.66, ink)
    elif mouth == "gasp":
        _oval(d, P(mf, mu - 0.06 * ry), fwd, mw * 0.58, mw * 1.05, ink)
    elif mouth == "wide":
        _oval(d, P(mf, mu + 0.04 * ry), fwd, mw * 0.98, mw * 0.66, ink)
        _limb(d, P(mf - mw * 0.74, mu + 0.04 * ry + 0.38 * mw),
              P(mf + mw * 0.74, mu + 0.04 * ry + 0.38 * mw),
              fw * 1.9, fw * 1.9, C["sclera"])
    elif mouth == "grin":
        lipl, lipr = P(mf - mw * 1.25, mu + mw * 0.55), P(mf + mw * 1.25, mu + mw * 0.55)
        arc = _curve([lipl, P(mf, mu - mw * 1.55), lipr], 11)
        d.polygon(arc + [lipr, lipl], fill=ink)
        _arc_line(d, arc, fw * 1.3, ink)
        _limb(d, P(mf - mw * 0.95, mu + mw * 0.38), P(mf + mw * 0.95, mu + mw * 0.38),
              fw * 1.6, fw * 1.6, C["sclera"])
    elif mouth == "frown":
        _arc_line(d, _curve([P(mf - mw * 1.05, mu - mw * 0.55), P(mf, mu + mw * 0.85),
                             P(mf + mw * 1.05, mu - mw * 0.55)]), fw * 1.5, ink)
    else:  # line
        _arc_line(d, _curve([P(mf - mw * 0.95, mu + mw * 0.12), P(mf, mu - mw * 0.30),
                             P(mf + mw * 0.95, mu + mw * 0.12)]), fw * 1.4, ink)


# -------------------------------------------------------------------- draw ---


def draw(img, pose: dict, look, *, unit: float, origin=(0.0, 0.0), z: float = 1.0,
         shadow: bool = True, ground: float | None = None):
    """Draw one character onto a PIL image.

    ``unit``    pixels per scene unit
    ``origin``  scene coordinate at the image's top-left
    ``look``    a palette object — read as a mapping, an attribute bag, or
                anything else that yields ``(r, g, b)`` or ``"#rrggbb"``
    ``z``       depth, ``1`` here, ``0`` far: distant figures desaturate and lift
    ``shadow``  draw the contact ellipse under the feet
    ``ground``  scene ``y`` for that shadow; the lowest sole if omitted

    Drawn at 3x and composited down. Pure with respect to the pose.
    """
    P = solve(pose)
    H = float(pose.get("height", DEFAULT_HEIGHT))
    face = pose.get("face") or {}

    x0, y0, x1, y1 = bbox(pose)
    m = 0.03 * H + INK_W * H

    # the contact shadow is sized first, so the tile can never clip it
    sh_rect = None
    if shadow:
        soles = [P["ankle.l"][1] + SOLE * H, P["ankle.r"][1] + SOLE * H]
        gy = float(ground) if ground is not None else max(soles)
        cx = (P["ankle.l"][0] + P["ankle.r"][0]) * 0.5
        k = 1.0 / (1.0 + max(0.0, gy - max(soles)) / (0.22 * H))
        rw, rh = 0.26 * H * k, 0.050 * H * k
        sh_rect = (cx, gy, rw, rh, k)
        x0, x1 = min(x0, cx - rw * 1.3), max(x1, cx + rw * 1.3)
        y0, y1 = min(y0, gy - rh * 1.3), max(y1, gy + rh * 1.3)

    px0 = int(math.floor((x0 - m - origin[0]) * unit))
    py0 = int(math.floor((y0 - m - origin[1]) * unit))
    px1 = int(math.ceil((x1 + m - origin[0]) * unit))
    py1 = int(math.ceil((y1 + m - origin[1]) * unit))
    px0, py0 = max(0, px0), max(0, py0)
    px1, py1 = min(img.width, px1), min(img.height, py1)
    if px1 <= px0 or py1 <= py0:
        return img
    tw, th = px1 - px0, py1 - py0

    tile = Image.new("RGBA", (tw * SS, th * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    s = unit * SS

    def T(p):
        return ((p[0] - origin[0]) * unit - px0) * SS, ((p[1] - origin[1]) * unit - py0) * SS

    haze = _pick(look, "sky")
    shadow_c = _pick(look, "shadow")
    C = {k: _depth(_pick(look, k), haze, z)
         for k in ("skin", "hair", "shirt", "trouser", "shoe", "ink", "accent", "accent2")}
    C["sclera"] = _depth(SCLERA, haze, z)
    ink = C["ink"]

    # Two weights, never one: a uniform line reads as clip art. The body
    # outline is heavy, face detail is about half of it.
    lw = max(2.0, INK_W * H * s)
    fw = max(1.4, FACE_W * H * s)

    _ol_cache: dict[tuple, tuple] = {}

    def OL(c):
        """The outline for a fill — same hue, darker. Never pure black."""
        v = _ol_cache.get(c)
        if v is None:
            v = _ol_cache[c] = outline_of(c)
        return v

    W = {k: v * H * s for k, v in WIDTHS.items()}
    sq = max(0.25, float(pose.get("squash", 1.0)))
    wsx = squash_scale(sq)[0]
    for k in W:
        W[k] *= wsx

    # ---- contact shadow -------------------------------------------------
    if sh_rect is not None:
        cx, gy, rw, rh, k = sh_rect
        sc = T((cx, gy))
        rw, rh = rw * s, rh * s
        blur = 0.010 * H * s
        sh = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([sc[0] - rw, sc[1] - rh, sc[0] + rw, sc[1] + rh],
                                   fill=(*_depth(shadow_c, haze, z), int(78 * k)))
        tile.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))

    # ---- limbs ----------------------------------------------------------
    def leg(side, col_leg, col_shoe):
        hip, knee, ank = T(P["hip." + side]), T(P["knee." + side]), T(P["ankle." + side])
        foot = T(P["foot." + side])
        for swell, fill in ((lw, OL(col_leg)), (0.0, col_leg)):
            _limb(d, hip, knee, W["thigh"] + 2 * swell, W["knee"] + 2 * swell, fill)
            _limb(d, knee, ank, W["knee"] + 2 * swell, W["ankle"] + 2 * swell, fill)
        # the shoe: a wedge from the heel, sitting below the ankle line
        fd = _norm((foot[0] - ank[0], foot[1] - ank[1]))
        dn = _perp(fd)
        if dn[1] < 0:  # keep the sole on the downhill side
            dn = _neg(dn)
        heel = (ank[0] - fd[0] * 0.020 * H * s, ank[1] - fd[1] * 0.020 * H * s)
        for swell, fill in ((lw, OL(col_shoe)), (0.0, col_shoe)):
            th_ = W["shoe"] * 0.42 + swell
            _limb(d, heel, foot, W["ankle"] + 2 * swell, th_ * 1.1, fill)
            quad = [
                (heel[0] + dn[0] * th_, heel[1] + dn[1] * th_),
                (foot[0] + dn[0] * th_, foot[1] + dn[1] * th_),
                (foot[0] - dn[0] * th_, foot[1] - dn[1] * th_),
                (heel[0] - dn[0] * th_, heel[1] - dn[1] * th_),
            ]
            d.polygon(quad, fill=fill)
            _limb(d, foot, foot, th_ * 2, th_ * 2, fill)

    def arm(side, col_sleeve, col_skin):
        sh, el = T(P["shoulder." + side]), T(P["elbow." + side])
        wr, hd = T(P["wrist." + side]), T(P["hand." + side])
        for swell, fill in ((lw, OL(col_sleeve)), (0.0, col_sleeve)):
            _limb(d, sh, el, W["upper_arm"] + 2 * swell, W["elbow"] + 2 * swell, fill)
            _limb(d, el, wr, W["elbow"] + 2 * swell, W["wrist"] + 2 * swell, fill)
        for swell, fill in ((lw, OL(col_skin)), (0.0, col_skin)):
            _mitten(d, wr, hd, W["hand"], swell, fill)

    far = 0.30  # how much the far side of the body sinks towards the shadow
    C_far_sleeve, C_far_skin = _shade(C["shirt"], shadow_c, far), _shade(C["skin"], shadow_c, far)

    # An arm raised above the head cannot be hidden behind it: on these
    # proportions the whole upper arm fits inside the skull, and a hand with
    # no arm attached is the loudest possible drawing error. An arm that is
    # overhead *and* passing behind the face is therefore laid over the skull,
    # the way a cartoonist would draw it -- but always under the face, because
    # the face is the only thing acting. An arm sweeping across the front of
    # the head keeps the normal ordering, so it reads as passing in front.
    # Keyed on the solved pose, so it stays deterministic.
    hb_px, cr_px = T(P["head_base"]), T(P["crown"])
    head_mid_y = (hb_px[1] + cr_px[1]) * 0.5
    head_cx = (hb_px[0] + cr_px[0]) * 0.5
    fsign = -1.0 if float(pose.get("facing", 1)) < 0 else 1.0

    def _laid_over(side):
        if T(P["hand." + side])[1] >= head_mid_y:
            return False
        return (T(P["elbow." + side])[0] - head_cx) * fsign <= 0.10 * H * s

    over_l, over_r = _laid_over("l"), _laid_over("r")

    leg("l", _shade(C["trouser"], shadow_c, far), _shade(C["shoe"], shadow_c, far))
    if not over_l:
        arm("l", C_far_sleeve, C_far_skin)

    # ---- torso ----------------------------------------------------------
    pel, che = T(P["pelvis"]), T(P["chest"])
    hb = T(P["head_base"])
    waist = ((pel[0] + che[0]) * 0.5, (pel[1] + che[1]) * 0.5)
    u_spine = _norm((che[0] - pel[0], che[1] - pel[1]))
    for swell, fill in ((lw, OL(C["skin"])), (0.0, C["skin"])):
        _limb(d, che, hb, W["neck"] + 2 * swell, W["neck"] * 0.92 + 2 * swell, fill)
    for swell, fill in ((lw, OL(C["trouser"])), (0.0, C["trouser"])):
        _limb(d, pel, waist, W["hip"] + 2 * swell, W["waist"] + 2 * swell, fill)
    # the trunk is capped with a shallow yoke rather than a circle: a circle
    # of shoulder width would swallow the neck whole
    for swell, fill in ((lw, OL(C["shirt"])), (0.0, C["shirt"])):
        _limb(d, waist, che, W["waist"] + 2 * swell, W["chest"] + 2 * swell, fill,
              caps=(True, False))
        _oval(d, che, u_spine, 0.042 * H * s + swell, W["chest"] * 0.5 + swell, fill)

    leg("r", C["trouser"], C["shoe"])

    # ---- head -----------------------------------------------------------
    crown, head_base = T(P["crown"]), T(P["head_base"])
    up = _norm((crown[0] - head_base[0], crown[1] - head_base[1]))
    facing = -1.0 if float(pose.get("facing", 1)) < 0 else 1.0
    fwd = _mul(_perp(up), facing)
    hl = math.hypot(crown[0] - head_base[0], crown[1] - head_base[1])
    ry = hl * 0.47
    rx = HEAD_W * 0.5 * H * s * wsx
    hc = (head_base[0] + up[0] * hl * 0.53, head_base[1] + up[1] * hl * 0.53)

    def HP(f, u):
        return (hc[0] + fwd[0] * f + up[0] * u, hc[1] + fwd[1] * f + up[1] * u)

    skin_ol = OL(C["skin"])
    # ear first, so the skull covers all but the bump
    er = 0.150 * rx
    ear = HP(-0.96 * rx, -0.24 * ry)
    _limb(d, ear, ear, er * 2 + 2 * lw, er * 2 + 2 * lw, skin_ol)
    _limb(d, ear, ear, er * 2, er * 2, C["skin"])

    _oval(d, hc, up, ry + lw, rx + lw, skin_ol)
    _oval(d, hc, up, ry, rx, C["skin"])

    # nose: a bump on the forward silhouette, then the skull is re-laid over
    # it so only the protruding crescent keeps its outline. It is what stops
    # the head reading as a ball.
    nr = 0.200 * rx
    nc = HP(0.94 * rx, -0.20 * ry)
    _limb(d, nc, nc, nr * 2 + 2 * lw, nr * 2 + 2 * lw, skin_ol)
    _limb(d, nc, nc, nr * 2, nr * 2, C["skin"])
    _oval(d, hc, up, ry, rx, C["skin"])

    # hair: the skull oval clipped to a hairline that recedes towards the
    # front, plus a tuft — the tuft is most of the silhouette's identity. Both
    # are laid down twice, swollen in the derived outline then filled, so the
    # hairline gets a line of its own rather than butting against the skin.
    u0, slope = 0.52 * ry, 0.20

    def cap():
        pts = []
        for i in range(49):
            a = 2.0 * math.pi * i / 48.0
            f, u = math.sin(a) * rx, math.cos(a) * ry
            pts.append(HP(f, max(u, u0 + slope * f)))
        return pts

    def tuft():
        return [HP(0.52 * rx, u0 + slope * 0.52 * rx),
                HP(1.30 * rx, 0.88 * ry), HP(0.28 * rx, 1.00 * ry),
                HP(-0.20 * rx, u0)]

    hair_ol = OL(C["hair"])
    shapes = (cap(), tuft())
    for poly in shapes:                     # one uniform outline, then the fills
        d.polygon(poly, fill=hair_ol)
        _arc_line(d, poly + [poly[0]], lw * 1.7, hair_ol)
    for poly in shapes:
        d.polygon(poly, fill=C["hair"])

    # overhead arms sit on the skull, under the face
    if over_l:
        arm("l", C_far_sleeve, C_far_skin)
    if over_r:
        arm("r", C["shirt"], C["skin"])

    _draw_face(d, face, C, ink, fw, hc, up, fwd, rx, ry)

    if not over_r:
        arm("r", C["shirt"], C["skin"])

    # ---- composite ------------------------------------------------------
    small = _downsample(tile, tw, th)
    if img.mode == "RGBA":
        img.alpha_composite(small, (px0, py0))
    else:
        img.paste(small.convert("RGB"), (px0, py0), small.getchannel("A"))
    return img


# ------------------------------------------------------------- self-test -----

if __name__ == "__main__":
    import os

    OUT = os.environ.get("RIG_TEST_OUT", "/tmp")

    LOOK = {
        "sky": (200, 220, 235), "ground": (168, 190, 160),
        "skin": (242, 199, 162), "hair": (52, 38, 34), "shirt": (214, 78, 62),
        "trouser": (46, 62, 100), "shoe": (36, 34, 44), "ink": (26, 24, 32),
        "accent": (247, 196, 62), "accent2": (64, 190, 178), "shadow": (30, 26, 52),
    }

    def P(joints=None, **kw):
        p = {"at": (0.0, 0.0), "facing": 1, "height": DEFAULT_HEIGHT,
             "joints": dict(joints or {}),
             "face": {"brow": 0.0, "eyes": "open", "mouth": "line", "look": [0.2, 0.0]}}
        p.update(kw)
        return p

    FLAT = -90.0  # ankle angle that puts a foot flat on the ground
    cases = [
        ("rest (all zeros)", P()),
        ("stand", P({"spine": 2, "neck": -1, "head": -1,
                     "shoulder.l": 6, "elbow.l": -14, "shoulder.r": -5, "elbow.r": -18,
                     "hip.l": -3, "knee.l": 3, "ankle.l": FLAT,
                     "hip.r": 4, "knee.r": 2, "ankle.r": FLAT})),
        ("stride", P({"spine": 5, "neck": -3, "head": -2,
                      "shoulder.l": -24, "elbow.l": -30, "shoulder.r": 22, "elbow.r": -22,
                      "hip.l": -22, "knee.l": 6, "ankle.l": FLAT - 8,
                      "hip.r": 20, "knee.r": 22, "ankle.r": FLAT + 16},
                     face={"brow": 0.2, "eyes": "open", "mouth": "line", "look": [0.5, 0]})),
        ("point", P({"spine": 3, "neck": -2, "head": -4,
                     "shoulder.r": -96, "elbow.r": -6, "wrist.r": 4,
                     "shoulder.l": 16, "elbow.l": -30,
                     "hip.l": -8, "knee.l": 8, "ankle.l": FLAT,
                     "hip.r": 8, "knee.r": 4, "ankle.r": FLAT},
                    face={"brow": -0.5, "eyes": "wide", "mouth": "wide", "look": [0.8, 0]})),
        ("shock", P({"spine": -12, "neck": 6, "head": 8,
                     "shoulder.l": 52, "elbow.l": -104, "shoulder.r": -46, "elbow.r": -112,
                     "hip.l": -16, "knee.l": 26, "ankle.l": FLAT - 10,
                     "hip.r": 14, "knee.r": 14, "ankle.r": FLAT + 6},
                    squash=1.10, tilt=-6,
                    face={"brow": 1.0, "eyes": "wide", "mouth": "gasp", "look": [0.4, -0.4]})),
        ("brace", P({"spine": 16, "neck": -14, "head": -6,
                     "shoulder.l": -62, "elbow.l": -118, "shoulder.r": -70, "elbow.r": -124,
                     "hip.l": -34, "knee.l": 62, "ankle.l": FLAT - 26,
                     "hip.r": -28, "knee.r": 58, "ankle.r": FLAT - 22},
                    squash=0.88,
                    face={"brow": -0.8, "eyes": "shut", "mouth": "line", "look": [0, 0]})),
        ("facing -1", P({"spine": 4, "shoulder.r": -70, "elbow.r": -40,
                         "shoulder.l": 14, "elbow.l": -20,
                         "hip.l": -14, "knee.l": 10, "ankle.l": FLAT,
                         "hip.r": 12, "knee.r": 6, "ankle.r": FLAT},
                        facing=-1,
                        face={"brow": 0.6, "eyes": "squint", "mouth": "grin",
                              "look": [0.6, 0.2]})),
        ("dead / frown", P({"spine": -2, "shoulder.l": 8, "elbow.l": -10,
                            "shoulder.r": 6, "elbow.r": -12,
                            "hip.l": -2, "knee.l": 2, "ankle.l": FLAT,
                            "hip.r": 2, "knee.r": 2, "ankle.r": FLAT},
                           face={"brow": -0.2, "eyes": "dead", "mouth": "frown",
                                 "look": [0.1, 0]})),
    ]

    STAND = dict(cases[1][1])
    builds = [(n, dict(STAND, bones=n)) for n in ("default", "kid", "heavy", "lanky")]

    # -- proportions and colour -------------------------------------------
    print(f"heads tall: {HEADS_TALL:.2f}  (target 4.0 - 4.5)")
    assert 4.0 <= HEADS_TALL <= 4.5, HEADS_TALL
    for name, p in builds:
        b = bones_for(p)
        tall = (b["spine"] + b["neck"] + b["head"]
                + (b["thigh"] + b["shin"]) * 0.965 + SOLE) / (b["head"] * 0.94)
        print(f"  {name:<8} {tall:.2f} heads")
        assert 3.4 <= tall <= 5.0, (name, tall)
    assert bones_for({}) == BONES and bones_for(None) == BONES
    assert bones_for({"bones": {"head": 0.31}})["head"] == 0.31
    assert bones_for({"bones": {"nope": 9.0}}) == BONES

    # outlines are derived from the fill, and are never pure black
    for key in ("skin", "hair", "shirt", "trouser", "shoe"):
        ol = outline_of(LOOK[key])
        assert sum(ol) > 12, (key, ol)                       # not black
        assert sum(ol) < sum(LOOK[key]) or sum(LOOK[key]) < 40, (key, ol)
    assert outline_of((255, 255, 255)) != (0, 0, 0)
    print("outline_of(shirt) =", outline_of(LOOK["shirt"]),
          " outline_of(shoe) =", outline_of(LOOK["shoe"]))

    # squash preserves area: width is the reciprocal of height
    for sq in (0.75, 0.85, 0.88, 1.0, 1.18, 1.20, 1.30):
        sx, sy = squash_scale(sq)
        assert abs(sx * sy - 1.0) < 1e-12, (sq, sx, sy)
    assert INK_W > FACE_W, "body outline must be heavier than face detail"

    # brows: seven distinct states, two of them asymmetric
    seen = set()
    for nm, ((tf, lf), (tn, ln)) in BROWS.items():
        assert abs(tf) <= 30.0 and abs(tn) <= 30.0, nm
        seen.add((round(tf, 1), round(lf, 2)))
    assert len(seen) == len(BROWS), "two brow presets are identical"
    for nm in ("confused", "smug"):
        (tf, _), (tn, _) = BROWS[nm]
        assert (tf > 0) != (tn > 0), nm + " should be asymmetric"
    assert _brow_pair("angry") == BROWS["angry"]
    assert _brow_pair(-1.0)[0][0] > 20 and _brow_pair(1.0)[0][1] > 0.9
    assert _brow_pair(0.0)[0] != _brow_pair(0.0)[1], "idle brows must not mirror"
    assert _brow_pair("nonsense") == BROWS["neutral"]

    # -- the face is never behind a sleeve --------------------------------
    # An arm laid over the skull must pass behind the face. This renders the
    # real pixels and looks inside the forward half of the head for shirt
    # colour, which is the actual failure the ordering exists to prevent.
    def sleeve_pixels_on_the_face(pose, unit=26.0):
        """(sleeve pixels, face-region pixels) in a real render of ``pose``."""
        p = dict(pose)
        p["at"] = (0.0, 0.0)
        b = bbox(p)
        pad = 1.0
        im = Image.new("RGB", (int((b[2] - b[0] + 2 * pad) * unit),
                               int((b[3] - b[1] + 2 * pad) * unit)), (255, 255, 255))
        origin = (b[0] - pad, b[1] - pad)
        draw(im, p, LOOK, unit=unit, origin=origin, shadow=False)
        s = solve(p)
        hb, cr = s["head_base"], s["crown"]
        hl = math.hypot(cr[0] - hb[0], cr[1] - hb[1])
        up = _norm((cr[0] - hb[0], cr[1] - hb[1]))
        fwd = _mul(_perp(up), -1.0 if float(p.get("facing", 1)) < 0 else 1.0)
        hc = (hb[0] + up[0] * hl * 0.53, hb[1] + up[1] * hl * 0.53)
        H = float(p.get("height", DEFAULT_HEIGHT))
        rx, ry = HEAD_W * 0.5 * H, hl * 0.47
        bad_cols = [LOOK["shirt"], outline_of(LOOK["shirt"]),
                    _shade(LOOK["shirt"], LOOK["shadow"], 0.30),
                    outline_of(_shade(LOOK["shirt"], LOOK["shadow"], 0.30))]
        ok_cols = [LOOK["skin"], outline_of(LOOK["skin"]), LOOK["hair"],
                   outline_of(LOOK["hair"]), LOOK["ink"], SCLERA, (255, 255, 255)]
        near = lambda c, t: max(abs(c[k] - t[k]) for k in range(3)) <= 8
        px, hits, area = im.load(), 0, 0
        for iy in range(im.height):
            for ix in range(im.width):
                sx = origin[0] + (ix + 0.5) / unit
                sy = origin[1] + (iy + 0.5) / unit
                dx, dy = sx - hc[0], sy - hc[1]
                f = dx * fwd[0] + dy * fwd[1]
                u = dx * up[0] + dy * up[1]
                if f <= 0.0 or (f / (rx * 0.86)) ** 2 + (u / (ry * 0.86)) ** 2 > 1.0:
                    continue
                area += 1
                c = px[ix, iy]
                if any(near(c, t) for t in ok_cols):
                    continue
                if any(near(c, t) for t in bad_cols):
                    hits += 1
        return hits, area

    import poses as _p_test                     # test-only; rig itself imports nothing
    worst = 0.0
    for label, pose in (("panic 0.00", _p_test.panic(0.00)),
                        ("panic 0.25", _p_test.panic(0.25)),
                        ("panic 0.50", _p_test.panic(0.50)),
                        ("panic 0.75", _p_test.panic(0.75)),
                        ("panic mirrored", _p_test.panic(0.25, facing=-1)),
                        ("glee", _p_test.react(1.0, kind="glee")),
                        ("shock", _p_test.react(1.0, kind="shock")),
                        ("point", _p_test.point(1.0))):
        n, area = sleeve_pixels_on_the_face(pose)
        # a sleeve *across* the face covers 15-40% of it; a few pixels of a
        # sleeve edge clipping the jawline are invisible and allowed
        assert n <= 0.005 * area, f"{label}: {n / area:.1%} of the face is sleeve"
        worst = max(worst, n / area)
    print(f"no sleeve over the face in 8 arms-up poses "
          f"(rendered pixels, worst {worst:.2%})")

    # -- geometry ---------------------------------------------------------
    print(f"{'case':<18} {'bbox (x0,y0,x1,y1)':<42} {'w x h':<14}")
    for name, pose in cases:
        b = bbox(pose)
        print(f"{name:<18} ({b[0]:7.2f},{b[1]:7.2f},{b[2]:7.2f},{b[3]:7.2f})"
              f"   {b[2]-b[0]:6.2f} x {b[3]-b[1]:6.2f}")

    st = solve(cases[1][1])
    print(f"\ncrown->sole standing: {st['ankle.l'][1] + SOLE * 18 - st['crown'][1]:.3f} "
          f"units (H = 18, PELVIS_TO_SOLE = {PELVIS_TO_SOLE:.4f} H)")

    # purity: solve must not touch the pose it is given
    import copy
    probe = copy.deepcopy(cases[2][1])
    before = copy.deepcopy(probe)
    solve(probe); bbox(probe)
    assert probe == before, "solve/bbox mutated the pose"

    # determinism: identical pixels on a second pass
    def sheet():
        cols, rows = 4, 2
        cw, ch = 300, 340
        img = Image.new("RGB", (cols * cw, rows * ch), (246, 243, 236))
        dd = ImageDraw.Draw(img)
        unit = 13.0
        for i, (name, pose) in enumerate(cases):
            cx, cy = (i % cols) * cw, (i // cols) * ch
            dd.rectangle([cx, cy, cx + cw - 1, cy + ch - 1], outline=(214, 208, 196))
            dd.text((cx + 10, cy + 10), name, fill=(90, 86, 78))
            p = dict(pose)
            p["at"] = (0.0, 0.0)
            b = bbox(p)
            ox = b[0] - (cw / unit - (b[2] - b[0])) / 2 - cx / unit
            oy = b[1] - (ch / unit - (b[3] - b[1])) / 2 - cy / unit
            draw(img, p, LOOK, unit=unit, origin=(ox, oy))
        return img

    import hashlib
    a, b = sheet(), sheet()
    ha = hashlib.sha256(a.tobytes()).hexdigest()
    hb = hashlib.sha256(b.tobytes()).hexdigest()
    assert ha == hb, "draw is not deterministic"
    print(f"deterministic: {ha[:16]} == {hb[:16]}")

    path = os.path.join(OUT, "rig_sheet.png")
    a.save(path)
    print("wrote", path)

    # -- the brow grid: the expression carrier, at the size it is seen ----
    def grid(rows, cols, cw, ch, unit, cell, head=False):
        img = Image.new("RGB", (cols * cw, rows * ch), (246, 243, 236))
        dd = ImageDraw.Draw(img)
        for i in range(rows * cols):
            label, pose = cell(i)
            if pose is None:
                continue
            cx, cy = (i % cols) * cw, (i // cols) * ch
            dd.rectangle([cx, cy, cx + cw - 1, cy + ch - 1], outline=(214, 208, 196))
            p = dict(pose)
            p["at"] = (0.0, 0.0)
            if head:
                s = solve(p)
                fx = (s["crown"][0] + s["head_base"][0]) * 0.5
                fy = (s["crown"][1] + s["head_base"][1]) * 0.5
                ox = fx - (cw * 0.5) / unit - cx / unit
                oy = fy - (ch * 0.5) / unit - cy / unit
            else:
                b = bbox(p)
                ox = b[0] - (cw / unit - (b[2] - b[0])) / 2 - cx / unit
                oy = b[1] - (ch / unit - (b[3] - b[1])) / 2 - cy / unit
            draw(img, p, LOOK, unit=unit, origin=(ox, oy), shadow=not head)
            dd.text((cx + 8, cy + 8), label, fill=(90, 86, 78))
        return img

    brow_cases = [(nm, "open", "line") for nm in BROWS] + [
        ("surprised", "wide", "gasp"), ("angry", "squint", "frown"),
        ("smug", "squint", "grin"), ("sad", "shut", "frown"),
        ("strain", "shut", "wide"), ("neutral", "dead", "oh"),
        ("confused", "open", "oh"), ("neutral", "open", "grin"),
    ]
    head_only = {"spine": 2, "neck": -1, "head": -2, "shoulder.l": 6, "elbow.l": -14,
                 "shoulder.r": -5, "elbow.r": -18, "hip.l": -3, "knee.l": 3,
                 "ankle.l": FLAT, "hip.r": 4, "knee.r": 2, "ankle.r": FLAT}

    def brow_cell(i):
        if i >= len(brow_cases):
            return "", None
        nm, ey, mo = brow_cases[i]
        return (f"{nm}/{ey}/{mo}",
                P(head_only, face={"brow": nm, "eyes": ey, "mouth": mo,
                                   "look": [0.35, -0.1]}))

    path = os.path.join(OUT, "rig_faces.png")
    grid(3, 5, 240, 250, 30.0, brow_cell, head=True).save(path)
    print("wrote", path)

    def build_cell(i):
        if i >= len(builds):
            return "", None
        return builds[i][0], builds[i][1]

    path = os.path.join(OUT, "rig_builds.png")
    grid(1, 4, 300, 340, 13.0, build_cell).save(path)
    print("wrote", path)
