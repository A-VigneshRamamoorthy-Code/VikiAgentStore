"""Easing and entrance choreography for the archival collage style.

The reference video never cuts. Everything arrives *onto* a persistent board,
so entrances carry all the rhythm — they must be crisp and physical.
"""

from __future__ import annotations

import math

from PIL import Image


# ------------------------------------------------------------------ easing ----


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def linear(t):
    return t


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_out_quint(t):
    return 1 - (1 - t) ** 5


def ease_out_expo(t):
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t, s=1.70158):
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def ease_out_settle(t, freq=2.6, damp=5.5):
    """Overshoot then settle — the 'stamped down' feel."""
    if t >= 1:
        return 1.0
    return 1 - math.exp(-damp * t) * math.cos(freq * math.pi * t)


EASINGS = {
    "linear": linear,
    "out_cubic": ease_out_cubic,
    "out_quint": ease_out_quint,
    "out_expo": ease_out_expo,
    "in_out_cubic": ease_in_out_cubic,
    "out_back": ease_out_back,
    "settle": ease_out_settle,
}


def phase(t: float, start: float, dur: float, ease: str = "out_cubic") -> float:
    """Normalised 0..1 progress of a sub-animation at absolute time `t`."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return EASINGS.get(ease, ease_out_cubic)(clamp((t - start) / dur))


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------- transforms ----


def transform(
    img: Image.Image,
    scale: float = 1.0,
    rotate: float = 0.0,
    opacity: float = 1.0,
) -> Image.Image:
    """Scale, rotate and fade an RGBA element (expanding the canvas as needed)."""
    out = img
    if abs(scale - 1.0) > 1e-3:
        w = max(1, int(round(out.size[0] * scale)))
        h = max(1, int(round(out.size[1] * scale)))
        out = out.resize((w, h), Image.LANCZOS)
    if abs(rotate) > 1e-3:
        out = out.rotate(rotate, expand=True, resample=Image.BICUBIC)
    if opacity < 0.999:
        a = out.getchannel("A").point(lambda v: int(v * clamp(opacity)))
        out = out.copy()
        out.putalpha(a)
    return out


def place_centered(canvas: Image.Image, el: Image.Image, center):
    """Composite `el` so its centre lands on `center` — keeps scale anchored."""
    x = int(round(center[0] - el.size[0] / 2))
    y = int(round(center[1] - el.size[1] / 2))
    canvas.alpha_composite(el, (x, y))


# ------------------------------------------------------------- entrances ----
#
# Each returns (scale, rotate, opacity, dx, dy) for a given progress p in 0..1.


def enter_stamp(p, angle=0.0, from_scale=1.22):
    """Slams down from slightly above, overshoots, settles. For chips & stamps."""
    e = ease_out_settle(p, freq=2.2, damp=6.0)
    s = lerp(from_scale, 1.0, min(1.0, e))
    return s, angle * (1 - ease_out_cubic(p)) * 0.6 + angle, clamp(p / 0.28), 0, int(-26 * (1 - ease_out_expo(p)))


def enter_pin(p, angle=0.0, drop=54):
    """Drops in and lands, as if pinned to the board."""
    e = ease_out_back(clamp(p))
    return lerp(1.06, 1.0, e), angle, clamp(p / 0.25), 0, int(drop * (1 - e))


def enter_slide(p, dx=0, dy=0, angle=0.0, ease="out_quint"):
    e = EASINGS[ease](clamp(p))
    return 1.0, angle, clamp(p / 0.30), int(dx * (1 - e)), int(dy * (1 - e))


def enter_fade_rise(p, rise=30, angle=0.0):
    e = ease_out_cubic(clamp(p))
    return lerp(1.02, 1.0, e), angle, e, 0, int(rise * (1 - e))


def exit_fade(p, fall=18):
    """p is exit progress 0..1 (0 = fully present)."""
    e = ease_in_out_cubic(clamp(p))
    return 1.0 - 0.02 * e, 0.0, 1.0 - e, 0, int(fall * e)


def exit_pan(p, dx=0, fall=0):
    """An exit that *leaves*, rather than one that dissolves on the spot.

    A fade says the thing stopped existing; a pan says the camera moved on and
    the thing is still back there. That difference is the whole reason a
    scene change in animation reads as continuous space rather than as a
    slideshow advancing.

    The opacity curve is deliberately late — the element stays fully solid for
    the first half of its exit and only thins once it is most of the way off
    frame, so it reads as travelling out of shot rather than as evaporating
    while it slides.
    """
    e = ease_in_out_cubic(clamp(p))
    op = 1.0 - clamp((p - 0.55) / 0.45) ** 1.5
    return 1.0, 0.0, op, int(dx * e), int(fall * e)


# ----------------------------------------------------------------- camera ----


def camera_drift(t: float, duration: float, amount: float = 0.030, zoom: float = 0.045, seed: float = 0.0):
    """Slow continuous push-in and wander — the reference never sits still.

    Returns (scale, dx_fraction, dy_fraction).
    """
    u = clamp(t / max(duration, 1e-6))
    s = 1.0 + zoom * ease_in_out_cubic(u)
    dx = amount * math.sin(u * math.pi * 0.9 + seed)
    dy = amount * 0.55 * math.sin(u * math.pi * 0.62 + 1.7 + seed)
    return s, dx, dy


def apply_camera(frame: Image.Image, out_size, scale: float, dx: float, dy: float) -> Image.Image:
    """Crop a scaled window out of an oversized board render."""
    W, H = out_size
    bw, bh = frame.size
    cw, ch = W / scale, H / scale
    cx = bw / 2 + dx * bw
    cy = bh / 2 + dy * bh
    left = clamp(cx - cw / 2, 0, max(0, bw - cw))
    top = clamp(cy - ch / 2, 0, max(0, bh - ch))
    box = (int(left), int(top), int(left + cw), int(top + ch))
    return frame.crop(box).resize((W, H), Image.LANCZOS)


# ------------------------------------------------------- flight & parallax ----


def enter_fly(p, rotate=0.0, from_x=0.0, from_y=0.0, height=1.35, spin=7.0):
    """A scrap thrown onto the board.

    Returns the usual 5-tuple plus the *elevation* to cast the shadow at. The
    scrap arrives large (it is nearer the lens), rotated, and high above the
    board; it settles down onto it with an overshoot. Because the shadow tightens
    as the elevation falls, the eye reads real distance rather than a scale tween.
    """
    e = ease_out_settle(p)
    elev = height * (1.0 - ease_out_cubic(p))
    scale = 1.0 + 0.30 * height * (1.0 - e)
    rot = rotate + spin * (1.0 - e)
    op = clamp(p / 0.32)
    dx = from_x * (1.0 - e)
    dy = from_y * (1.0 - e)
    return scale, rot, op, dx, dy, elev


def idle_float(t, seed=0, amp=1.0, rot_amp=0.16):
    """A never-quite-still breath applied to every loose element.

    The reference board is hand-held and lit by a live camera: nothing on it is
    ever perfectly static. Without this the collage reads as a PNG stack the
    moment an element stops animating.
    """
    a = (seed % 17) * 0.37
    b = (seed % 23) * 0.29
    c = (seed % 31) * 0.19
    fx = math.sin(t * 0.37 + a) * 0.6 + math.sin(t * 0.83 + b) * 0.4
    fy = math.sin(t * 0.31 + b) * 0.6 + math.sin(t * 0.71 + c) * 0.4
    fr = math.sin(t * 0.23 + c) * 0.7 + math.sin(t * 0.61 + a) * 0.3
    return fx * amp, fy * amp, fr * rot_amp


def parallax_offset(depth, cdx, cdy, scale, strength=1.0):
    """Displace an element against the camera move according to its depth.

    `depth` is signed: positive is nearer the lens (moves more), negative is
    further away (moves less). This is what turns a flat pan into a board with
    physical layers.
    """
    k = depth * strength * scale
    return -cdx * k, -cdy * k


def camera_path(t: float, moves, duration: float, base_zoom: float = 1.0):
    """Interpolate an authored camera path.

    `moves` is a list of ``(t, x, y, zoom)`` — or ``(t, x, y, zoom, cut)`` —
    in *storyboard* coordinates, sorted by time. The plain 4-tuple form is
    always accepted, so existing callers that never pass a `cut` flag keep
    working unchanged. Between two keys the camera eases in and out, so it
    settles on a beat instead of sliding constantly — which is what the
    reference does and what makes the travel read as intentional rather than
    as a slow zoom.

    When the key being arrived at carries a truthy 5th ``cut`` element, that
    segment is *not* eased: the camera holds at the previous key's position
    for the whole segment and only reaches the new one once `t` lands on the
    key's own time — an instant jump rather than a whip pan. The move still
    eases away from that key as usual afterwards, unless the following key is
    itself a cut.
    """
    if not moves:
        return None
    if t <= moves[0][0]:
        x, y, z = moves[0][1], moves[0][2], moves[0][3]
        return x, y, z * base_zoom
    if t >= moves[-1][0]:
        x, y, z = moves[-1][1], moves[-1][2], moves[-1][3]
        return x, y, z * base_zoom
    for i in range(len(moves) - 1):
        t0, x0, y0, z0 = moves[i][0], moves[i][1], moves[i][2], moves[i][3]
        nxt = moves[i + 1]
        t1, x1, y1, z1 = nxt[0], nxt[1], nxt[2], nxt[3]
        cut = bool(nxt[4]) if len(nxt) > 4 else False
        if t0 <= t <= t1:
            if cut:
                if t < t1:
                    return x0, y0, z0 * base_zoom
                return x1, y1, z1 * base_zoom
            u = ease_in_out_cubic(clamp((t - t0) / max(1e-6, t1 - t0)))
            return (x0 + (x1 - x0) * u,
                    y0 + (y1 - y0) * u,
                    (z0 + (z1 - z0) * u) * base_zoom)
    x, y, z = moves[-1][1], moves[-1][2], moves[-1][3]
    return x, y, z * base_zoom


def camera_shake(t: float, events):
    """Deliberate camera jolt(s) — additive on top of the authored path.

    `events` is a list of dicts, each an absolute (already `Timeline.resolve`d)
    start time `t` plus `dur`, `amp` (peak offset in design units), `freq`
    (oscillations/sec) and `decay` (exponential decay constant). Returns the
    summed ``(dx, dy)`` in design units — multiple overlapping shakes add.

    x and y run at different frequencies and phases so the motion never reads
    as a straight-line vibration; y also decays a little faster than x, which
    reads as a touch of rotational give rather than a pure bounce. The decay
    envelope is additionally tapered to exactly zero at `dur`, so an author
    picking a small `decay` (a slow, lingering wobble) still cuts out cleanly
    instead of popping.
    """
    dx = dy = 0.0
    for ev in events:
        dur = max(1e-6, float(ev.get("dur", 1.0)))
        u = t - float(ev.get("t", 0.0))
        if u < 0.0 or u > dur:
            continue
        amp = float(ev.get("amp", 20.0))
        freq = float(ev.get("freq", 10.0))
        decay = float(ev.get("decay", 3.0))
        taper = 1.0 - (u / dur) ** 2  # forces the envelope to 0 right at `dur`
        ex = math.exp(-decay * u) * taper
        ey = math.exp(-decay * 1.35 * u) * taper
        dx += amp * ex * math.cos(u * freq * 2 * math.pi)
        dy += amp * 0.8 * ey * math.cos(u * freq * 1.6 * 2 * math.pi + 0.6)
    return dx, dy
