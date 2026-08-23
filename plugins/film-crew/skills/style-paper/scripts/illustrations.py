"""Procedural paper cut-out artwork.

Everything is drawn as a filled silhouette in archival ink, then handed to
`collage.sticker()` for the white paper border and contact shadow. Drawn at 3x
and downsampled, so edges stay clean at any size.

These are deliberately simple, iconic shapes — the style reads as *cut from a
magazine*, not as illustration. Add your own here for new subjects.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

import paper
from paper import PALETTE

SS = 3  # supersample factor
INK = (54, 52, 44)


def _canvas(w, h):
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _finish(img, w, h, seed=0, texture=True):
    out = img.resize((w, h), Image.LANCZOS)
    if texture:
        out = paper.add_grain(out, amount=5, seed=seed)
    return out


def _blob(d, pts, fill):
    d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)


def _spline(ctrl, samples_per_seg: int = 20):
    """Catmull-Rom through control points, for tails and organic curves."""
    p = [tuple(map(float, c)) for c in ctrl]
    if len(p) < 3:
        return p
    ext = [(2 * p[0][0] - p[1][0], 2 * p[0][1] - p[1][1])] + p + \
          [(2 * p[-1][0] - p[-2][0], 2 * p[-1][1] - p[-2][1])]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for j in range(samples_per_seg):
            t = j / samples_per_seg
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
            ))
    out.append(ext[-2])
    return out


def _ellipse(d, box, fill):
    d.ellipse([v * SS for v in box], fill=fill)


def _lighten(color, amt):
    """Blend an ink colour toward paper white by `amt` (0..1)."""
    return tuple(int(c + (255 - c) * amt) for c in color[:3])


def _darken(color, amt):
    """Blend an ink colour toward black by `amt` (0..1)."""
    return tuple(int(c * (1 - amt)) for c in color[:3])


# ------------------------------------------------------------------ mouse ----


def mouse(h: int = 260, ink=INK, seed: int = 0, facing: int = 1) -> Image.Image:
    """A small round mouse in profile. `facing` 1 = looking right."""
    w = int(h * 1.75)
    img, d = _canvas(w, h)

    bx, by = w * 0.44, h * 0.60      # body centre
    br_w, br_h = w * 0.21, h * 0.27  # body radii

    # --- tail: sweeps back from the body and curls up at the tip
    ctrl = [
        (bx - br_w * 0.60, by + br_h * 0.30),
        (bx - br_w * 1.55, by + br_h * 0.78),
        (bx - br_w * 2.35, by + br_h * 0.16),
        (bx - br_w * 2.55, by - br_h * 0.85),
    ]
    tail = _spline(ctrl)
    for i in range(len(tail) - 1):
        t = i / (len(tail) - 1)
        wd = max(1, int((h * 0.034) * (1 - 0.78 * t) * SS))
        d.line([(tail[i][0] * SS, tail[i][1] * SS), (tail[i + 1][0] * SS, tail[i + 1][1] * SS)],
               fill=ink + (255,), width=wd)
    tip = tail[-1]
    tr = h * 0.008
    _ellipse(d, (tip[0] - tr, tip[1] - tr, tip[0] + tr, tip[1] + tr), ink + (255,))

    # --- feet
    _ellipse(d, (bx - br_w * 0.55, by + br_h * 0.66, bx - br_w * 0.02, by + br_h * 1.06), ink + (255,))
    _ellipse(d, (bx + br_w * 0.34, by + br_h * 0.70, bx + br_w * 0.94, by + br_h * 1.08), ink + (255,))

    # --- ear (behind the head so the head circle crops it cleanly)
    hx, hy = bx + br_w * 0.95, by - br_h * 0.24
    hr = h * 0.185
    er = h * 0.145
    ex, ey = hx - hr * 0.62, hy - hr * 0.86
    _ellipse(d, (ex - er, ey - er, ex + er, ey + er), ink + (255,))
    _ellipse(d, (ex - er * 0.55, ey - er * 0.50, ex + er * 0.55, ey + er * 0.60), (168, 142, 124, 255))

    # --- body + head
    _ellipse(d, (bx - br_w, by - br_h, bx + br_w, by + br_h), ink + (255,))
    _ellipse(d, (hx - hr, hy - hr, hx + hr, hy + hr), ink + (255,))

    # --- snout, tapering to a point
    _blob(d, [(hx + hr * 0.20, hy - hr * 0.46),
              (hx + hr * 1.72, hy + hr * 0.34),
              (hx + hr * 1.70, hy + hr * 0.52),
              (hx + hr * 0.18, hy + hr * 0.88)], ink + (255,))
    # nose
    nr = h * 0.020
    nx, ny = hx + hr * 1.70, hy + hr * 0.43
    _ellipse(d, (nx - nr, ny - nr, nx + nr, ny + nr), (196, 150, 146, 255))

    # --- eye
    eyr = h * 0.030
    exx, eyy = hx + hr * 0.42, hy - hr * 0.02
    _ellipse(d, (exx - eyr, eyy - eyr, exx + eyr, eyy + eyr), (250, 246, 234, 255))
    pr = eyr * 0.46
    _ellipse(d, (exx + pr * 0.35 - pr, eyy - pr, exx + pr * 0.35 + pr, eyy + pr), (32, 30, 24, 255))

    # --- whiskers
    for k in (-1, 0, 1):
        a = math.radians(6 + k * 13)
        sx, sy = hx + hr * 1.25, hy + hr * 0.36
        d.line([(sx * SS, sy * SS),
                ((sx + math.cos(a) * hr * 1.30) * SS, (sy + math.sin(a) * hr * 1.30) * SS)],
               fill=ink + (190,), width=max(1, int(h * 0.007 * SS)))

    out = _finish(img, w, h, seed)
    if facing < 0:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    return out


# ---------------------------------------------------------------- lantern ----


def lantern(h: int = 300, ink=INK, seed: int = 0, glow: float = 0.0) -> Image.Image:
    """A small storm lantern. `glow` 0..1 lights the glass warm."""
    w = int(h * 0.62)
    img, d = _canvas(w, h)
    cx = w * 0.5

    # handle
    d.arc([(cx - w * 0.28) * SS, (h * 0.03) * SS, (cx + w * 0.28) * SS, (h * 0.26) * SS],
          200, 340, fill=ink + (255,), width=int(h * 0.022 * SS))
    # cap
    _blob(d, [(cx - w * 0.34, h * 0.28), (cx + w * 0.34, h * 0.28),
              (cx + w * 0.22, h * 0.17), (cx - w * 0.22, h * 0.17)], ink + (255,))
    # glass housing
    gx0, gy0, gx1, gy1 = cx - w * 0.30, h * 0.30, cx + w * 0.30, h * 0.74
    d.rectangle([gx0 * SS, gy0 * SS, gx1 * SS, gy1 * SS], fill=ink + (255,))
    # glass panel (knocked out of the body)
    px0, py0, px1, py1 = cx - w * 0.20, h * 0.35, cx + w * 0.20, h * 0.69
    glass = (232, 226, 206) if glow <= 0 else (
        int(232 + (255 - 232) * glow), int(226 + (206 - 226) * glow * -0.4), int(206 - 96 * glow))
    d.rectangle([px0 * SS, py0 * SS, px1 * SS, py1 * SS], fill=glass + (255,))
    # flame
    if glow > 0.02:
        fh = h * 0.13 * (0.55 + 0.45 * glow)
        fx, fy = cx, h * 0.60
        _blob(d, [(fx, fy - fh), (fx + w * 0.075, fy), (fx, fy + h * 0.028), (fx - w * 0.075, fy)],
              (255, 196, 92, 255))
        _blob(d, [(fx, fy - fh * 0.55), (fx + w * 0.035, fy - fh * 0.02),
                  (fx, fy + h * 0.012), (fx - w * 0.035, fy - fh * 0.02)], (255, 246, 214, 255))
    # frame bars
    d.rectangle([(cx - w * 0.022) * SS, py0 * SS, (cx + w * 0.022) * SS, py1 * SS], fill=ink + (215,))
    # base
    _blob(d, [(cx - w * 0.36, h * 0.92), (cx + w * 0.36, h * 0.92),
              (cx + w * 0.27, h * 0.74), (cx - w * 0.27, h * 0.74)], ink + (255,))

    out = _finish(img, w, h, seed)
    return out


def glow_halo(size: int, intensity: float = 1.0, color=(255, 206, 122)) -> Image.Image:
    """A soft warm halo. Composite this *behind* an already-stickered element,
    otherwise the paper border traces the halo instead of the object."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.30 * (0.7 + 0.6 * intensity)
    c = size / 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=color + (int(110 * intensity),))
    return img.filter(ImageFilter.GaussianBlur(size * 0.11))


# ------------------------------------------------------------------- moon ----


def moon(size: int = 360, seed: int = 4, ink=(232, 226, 202)) -> Image.Image:
    """A full moon disc with soft craters — cream on transparent."""
    img, d = _canvas(size, size)
    r = size * 0.46
    c = size * 0.5
    _ellipse(d, (c - r, c - r, c + r, c + r), ink + (255,))
    rng = paper._rng(seed)
    for _ in range(11):
        a = rng.uniform(0, 6.283)
        rad = rng.uniform(0, r * 0.74)
        cr = rng.uniform(size * 0.030, size * 0.085)
        cx, cy = c + math.cos(a) * rad, c + math.sin(a) * rad
        f = rng.uniform(0.88, 0.95)
        shade = tuple(int(v * f) for v in ink)
        _ellipse(d, (cx - cr, cy - cr, cx + cr, cy + cr), shade + (255,))
    return _finish(img, size, size, seed)


def star(size: int = 60, ink=(238, 232, 208), seed: int = 0) -> Image.Image:
    """Four-point sparkle."""
    img, d = _canvas(size, size)
    c = size / 2
    a, b = size * 0.48, size * 0.085
    _blob(d, [(c, c - a), (c + b, c - b), (c + a, c), (c + b, c + b),
              (c, c + a), (c - b, c + b), (c - a, c), (c - b, c - b)], ink + (255,))
    return _finish(img, size, size, seed, texture=False)


# ------------------------------------------------------------------- hill ----


def hill(w: int = 1200, h: int = 420, seed: int = 9, ink=(74, 72, 60)) -> Image.Image:
    """A snowy hill silhouette with a torn top edge and a pale snow cap."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    pts = [(0, h)]
    n = 120
    for i in range(n + 1):
        u = i / n
        y = h - (h * 0.80) * math.sin(math.pi * u) ** 1.25
        y += math.sin(u * 13 + seed) * h * 0.016 + rng.normal(0, h * 0.004)
        pts.append((u * w, y))
    pts.append((w, h))
    _blob(d, pts, ink + (255,))

    # snow along the crest
    snow = [(x, y) for x, y in pts[1:-1]]
    band = snow + [(x, y + h * 0.055 + math.sin(x * 0.02 + seed) * h * 0.018) for x, y in reversed(snow)]
    _blob(d, band, (236, 232, 216, 255))
    return _finish(img, w, h, seed)


def snow_layer(w: int, h: int, count: int = 90, seed: int = 12, ink=(244, 240, 226)) -> Image.Image:
    """Scattered snow flecks — use sparingly, they read as paper speckle."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = paper._rng(seed)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(1.6, 5.2)
        a = int(rng.uniform(90, 215))
        d.ellipse([x - r, y - r, x + r, y + r], fill=ink + (a,))
    return img


# ---------------------------------------------------------------- helpers ----


def night_wash(w: int, h: int, strength: float = 0.62, tint=(38, 44, 62)) -> Image.Image:
    """A cool overlay that turns the warm board into night without killing texture."""
    img = Image.new("RGBA", (w, h), tint + (int(255 * strength),))
    return img


# ----------------------------------------------------- landmark & document ----


def grand_hotel(w: int = 900, h: int = 520, seed: int = 21, ink=INK) -> Image.Image:
    """A grand colonial-era hotel — central ribbed dome on a drum, four corner
    turrets, an arcaded facade. A silhouette, not an elevation drawing."""
    img, d = _canvas(w, h)
    F = ink + (255,)
    cx = w * 0.5
    roof = h * 0.56          # top of the main block
    base = h * 0.985

    # main block
    _blob(d, [(w * 0.10, base), (w * 0.10, roof), (w * 0.90, roof), (w * 0.90, base)], F)

    # arcaded windows, three storeys
    pale = (238, 233, 214, 255)
    cols, rows = 11, 3
    for r in range(rows):
        y0 = roof + h * (0.085 + r * 0.113)
        y1 = y0 + h * 0.072
        for c in range(cols):
            x0 = w * 0.135 + c * (w * 0.73 / cols)
            x1 = x0 + w * 0.73 / cols * 0.52
            d.rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=pale)
            d.pieslice([x0 * SS, (y0 - (x1 - x0) * 0.5) * SS,
                        x1 * SS, (y0 + (x1 - x0) * 0.5) * SS], 180, 360, fill=pale)

    # central dome on a drum
    dr_w, dr_h = w * 0.26, h * 0.075
    _blob(d, [(cx - dr_w / 2, roof), (cx - dr_w / 2, roof - dr_h),
              (cx + dr_w / 2, roof - dr_h), (cx + dr_w / 2, roof)], F)
    dome_r = w * 0.155
    dome_b = roof - dr_h
    dome_h = dome_r * 1.52
    left, right = [], []
    n = 48
    for i in range(n + 1):
        v = i / n
        hw = dome_r * (max(0.0, 1.0 - v ** 2.4) ** 0.62)
        y = dome_b - dome_h * v
        left.append((cx - hw, y))
        right.append((cx + hw, y))
    _blob(d, left + list(reversed(right)), F)

    # ribs on the dome
    for k in (-0.66, -0.34, 0.0, 0.34, 0.66):
        pts = []
        for i in range(0, n + 1, 2):
            v = i / n
            hw = dome_r * (max(0.0, 1.0 - v ** 2.4) ** 0.62)
            pts.append(((cx + hw * k) * SS, (dome_b - dome_h * v) * SS))
        d.line(pts, fill=(238, 233, 214, 175),
               width=max(1, int(w * 0.006 * SS)), joint="curve")

    # finial
    tip = dome_b - dome_h
    d.line([cx * SS, tip * SS, cx * SS, (tip - dome_r * 0.30) * SS],
           fill=F, width=max(1, int(w * 0.010 * SS)))
    _ellipse(d, (cx - w * 0.017, tip - dome_r * 0.40,
                 cx + w * 0.017, tip - dome_r * 0.29), F)

    # four corner turrets with small domes
    for sx in (0.145, 0.315, 0.685, 0.855):
        tx = w * sx
        tw = w * 0.052
        ttop = roof - h * (0.115 if sx in (0.145, 0.855) else 0.075)
        _blob(d, [(tx - tw / 2, roof), (tx - tw / 2, ttop),
                  (tx + tw / 2, ttop), (tx + tw / 2, roof)], F)
        cap = tw * 0.78
        _ellipse(d, (tx - cap, ttop - cap * 0.95, tx + cap, ttop + cap * 0.95), F)
        d.line([tx * SS, (ttop - cap * 0.9) * SS, tx * SS, (ttop - cap * 1.7) * SS],
               fill=F, width=max(1, int(w * 0.006 * SS)))

    return _finish(img, w, h, seed)


def boat(w: int = 260, h: int = 130, seed: int = 22, ink=INK) -> Image.Image:
    """A small open inflatable seen side-on — how the attackers came ashore."""
    img, d = _canvas(w, h)
    F = ink + (255,)
    hull = [(w * 0.04, h * 0.52), (w * 0.16, h * 0.80), (w * 0.80, h * 0.80),
            (w * 0.97, h * 0.50), (w * 0.86, h * 0.52), (w * 0.20, h * 0.55)]
    _blob(d, hull, F)
    # outboard motor
    _blob(d, [(w * 0.02, h * 0.30), (w * 0.10, h * 0.30),
              (w * 0.10, h * 0.56), (w * 0.02, h * 0.56)], F)
    # a low wake line under it
    d.line([(w * 0.06) * SS, (h * 0.90) * SS, (w * 0.96) * SS, (h * 0.90) * SS],
           fill=ink + (120,), width=max(1, int(h * 0.030 * SS)))
    return _finish(img, w, h, seed)


def sea(w: int = 1400, h: int = 300, seed: int = 23, ink=(84, 88, 92)) -> Image.Image:
    """A band of stylised water — stacked wave rules, darkest at the bottom."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    rows = 9
    for r in range(rows):
        u = r / (rows - 1)
        y = h * (0.10 + 0.86 * u)
        a = int(70 + 150 * u)
        amp = h * (0.020 + 0.016 * (1 - u))
        thick = max(1, int(h * (0.016 + 0.020 * u) * SS))
        pts = []
        for i in range(121):
            x = w * i / 120
            pts.append((x * SS, (y + math.sin(x * 0.021 + r * 1.7 + seed) * amp
                                 + rng.normal(0, h * 0.004)) * SS))
        d.line(pts, fill=ink + (a,), width=thick, joint="curve")
    return _finish(img, w, h, seed, texture=False)


def clock(size: int = 300, seed: int = 24, ink=INK, hours: float = 10.0,
          minutes: float = 10.0) -> Image.Image:
    """An analogue clock face — for durations and timestamps."""
    img, d = _canvas(size, size)
    F = ink + (255,)
    c = size / 2
    r = size * 0.44
    _ellipse(d, (c - r, c - r, c + r, c + r), F)
    _ellipse(d, (c - r * 0.88, c - r * 0.88, c + r * 0.88, c + r * 0.88),
             (240, 236, 220, 255))
    for i in range(12):
        a = math.pi * 2 * i / 12 - math.pi / 2
        r0 = r * (0.66 if i % 3 else 0.60)
        d.line([(c + math.cos(a) * r0) * SS, (c + math.sin(a) * r0) * SS,
                (c + math.cos(a) * r * 0.80) * SS, (c + math.sin(a) * r * 0.80) * SS],
               fill=F, width=max(1, int(size * (0.014 if i % 3 else 0.022) * SS)))
    for val, per, ln, wd in ((hours % 12, 12.0, 0.42, 0.030),
                             (minutes % 60, 60.0, 0.62, 0.020)):
        a = math.pi * 2 * (val / per) - math.pi / 2
        d.line([c * SS, c * SS,
                (c + math.cos(a) * r * ln) * SS, (c + math.sin(a) * r * ln) * SS],
               fill=F, width=max(1, int(size * wd * SS)))
    _ellipse(d, (c - size * 0.022, c - size * 0.022, c + size * 0.022, c + size * 0.022), F)
    return _finish(img, size, size, seed)


def candle(h: int = 260, seed: int = 25, ink=INK, lit: float = 1.0) -> Image.Image:
    """A memorial candle. `lit` fades the flame in."""
    w = int(h * 0.46)
    img, d = _canvas(w, h)
    F = ink + (255,)
    _blob(d, [(w * 0.28, h * 0.99), (w * 0.28, h * 0.34),
              (w * 0.72, h * 0.34), (w * 0.72, h * 0.99)], F)
    d.line([(w * 0.5) * SS, (h * 0.34) * SS, (w * 0.5) * SS, (h * 0.25) * SS],
           fill=F, width=max(1, int(w * 0.05 * SS)))
    if lit > 0:
        a = int(255 * min(1.0, lit))
        flame = [(w * 0.50, h * 0.045), (w * 0.63, h * 0.16), (w * 0.60, h * 0.245),
                 (w * 0.50, h * 0.275), (w * 0.40, h * 0.245), (w * 0.37, h * 0.16)]
        _blob(d, flame, (250, 206, 118, a))
        inner = [(w * 0.50, h * 0.115), (w * 0.565, h * 0.185), (w * 0.50, h * 0.245),
                 (w * 0.435, h * 0.185)]
        _blob(d, inner, (255, 240, 198, a))
    return _finish(img, w, h, seed)


# --------------------------------------------------------- map & timeline ----

# South Mumbai / Salsette peninsula: a real, hand-checked coastline (not a
# procedural taper) so the map reads as Mumbai -- Back Bay's smooth bite on
# the south-west coast, the narrow Colaba tail below it, Mumbai Harbour's
# ragged docks on the east side, Mahim Bay and the Worli promontory further
# north. (lon, lat) pairs, traced north (Bandra) to south (Colaba Point) down
# the west coast, then back north up the harbour side to close the ring.
_MUMBAI_COAST = [
    (72.8320, 19.0780),  # Bandra, north frame edge
    (72.8210, 19.0650),  # Carter Road
    (72.8175, 19.0530),  # Bandra Bandstand
    (72.8145, 19.0430),  # Bandra Fort -- north horn of Mahim Bay
    (72.8210, 19.0404),
    (72.8268, 19.0379),
    (72.8315, 19.0353),
    (72.8347, 19.0328),
    (72.8360, 19.0302),
    (72.8353, 19.0277),
    (72.8327, 19.0252),
    (72.8286, 19.0226),
    (72.8234, 19.0200),
    (72.8175, 19.0175),  # Worli north shore -- south horn of Mahim Bay
    (72.8060, 19.0090),  # Worli Koliwada -- promontory tip
    (72.8090, 18.9905),  # Haji Ali
    (72.8010, 18.9685),  # Breach Candy
    (72.7925, 18.9530),  # Malabar Point -- north horn of Back Bay
    (72.7978, 18.9491),
    (72.8030, 18.9452),
    (72.8078, 18.9413),
    (72.8121, 18.9374),
    (72.8157, 18.9335),
    (72.8185, 18.9296),
    (72.8203, 18.9257),  # Nariman Point -- deepest point of Back Bay
    (72.8171, 18.9217),
    (72.8084, 18.9178),
    (72.7978, 18.9139),
    (72.7983, 18.9100),
    (72.7989, 18.9061),
    (72.7994, 18.9022),
    (72.7999, 18.8983),
    (72.8005, 18.8944),
    (72.8010, 18.8905),  # Colaba Point (west) -- south tip
    (72.8040, 18.8890),  # Colaba Point (east) -- south tip
    (72.8090, 18.8945),
    (72.8300, 18.9075),  # Sassoon Dock / Colaba Causeway
    (72.8365, 18.9225),  # Gateway of India
    (72.8420, 18.9280),  # Mumbai Harbour docks begin, jagged north to Wadala
    (72.8469, 18.9318),
    (72.8444, 18.9356),
    (72.8450, 18.9394),
    (72.8484, 18.9432),
    (72.8446, 18.9469),
    (72.8417, 18.9507),
    (72.8463, 18.9545),
    (72.8475, 18.9583),
    (72.8461, 18.9621),
    (72.8515, 18.9659),
    (72.8550, 18.9697),
    (72.8512, 18.9735),
    (72.8513, 18.9773),
    (72.8540, 18.9811),
    (72.8502, 18.9848),
    (72.8490, 18.9886),
    (72.8549, 18.9924),
    (72.8563, 18.9962),
    (72.8551, 19.0000),
    (72.8620, 19.0150),
    (72.8600, 19.0280),
    (72.8560, 19.0400),
    (72.8500, 19.0520),
    (72.8400, 19.0650),
]

# Reference bounding box the projection below is fit to, and the fixed
# canvas/margin it is fit against. `mumbai_lonlat_to_frac` always projects
# against this fixed box -- independent of whatever `w`/`h` a particular
# `mumbai_map()` call actually renders at -- so a caller can compute marker
# fractions once (as `render.py` does) and have them line up at any size.
# The window is widened past the peninsula itself -- east across Mumbai
# Harbour to a sliver of the mainland/Navi Mumbai shore, and a little open
# water west of the coast. The island alone is a ~0.38 aspect sliver (~0.095
# degrees of cos-corrected longitude against ~0.25 of latitude); fit into any
# normal tile that leaves huge blank margins either side. Harbour + far shore
# give the frame real content to fill without changing the island itself.
_MUMBAI_LAT_N, _MUMBAI_LAT_S = 18.978, 18.894
_MUMBAI_LON_W, _MUMBAI_LON_E = 72.779, 72.846
_MUMBAI_REF_W, _MUMBAI_REF_H = 617.0, 820.0
_MUMBAI_MARGIN_Y = 0.055  # top/bottom breathing room, as a fraction of height

# --- region registry -------------------------------------------------------
# A map that names places is making a factual claim, so the geography cannot
# live in the style: a film about Washington State must never be handed a map
# of Mumbai. Each region carries everything the drawing needs -- its window,
# its land or its water, its labels -- and a board picks one by name. A board
# that names none gets `generic`, which draws a credible chart with no place
# names at all, because an unlabelled map is honest where a confidently
# mislabelled one is a lie the viewer can read.
_REGIONS: dict = {}
_REGION_FIT: dict = {}


def _region(name):
    """Return `(region, fit)` for `name`, computing the projection fit once."""
    key = name or "generic"
    reg = _REGIONS.get(key)
    if reg is None:
        raise ValueError(f"unknown map region: {name!r} "
                         f"(known: {', '.join(sorted(_REGIONS))})")
    fit = _REGION_FIT.get(key)
    if fit is None:
        lon_w, lon_e, lat_s, lat_n = reg["window"]
        ref_w, ref_h = reg["ref"]
        margin = reg.get("margin_y", 0.055)
        cos0 = math.cos(math.radians((lat_n + lat_s) / 2))
        scale = (ref_h * (1 - 2 * margin)) / (lat_n - lat_s)
        fit = {
            "lon_w": lon_w, "lat_n": lat_n, "cos0": cos0, "scale": scale,
            "ref_w": ref_w, "ref_h": ref_h,
            "mx": (ref_w - (lon_e - lon_w) * cos0 * scale) / 2,
            "my": ref_h * margin,
        }
        # The fit constrains the *vertical* extent only -- the scale comes
        # from the latitude span. A window whose cos-corrected width then
        # overflows `ref_w` pushes the extreme longitudes outside the tile,
        # which clips an island's coastline off the frame silently. Catch a
        # bad window when the region is first used, not by eye.
        if fit["mx"] < 0:
            raise ValueError(
                "region %r is %.0fpx wider than its %.0fpx reference box: "
                "widen `ref`, or narrow `window`, or the edges of the "
                "geography fall outside the tile."
                % (key, -2 * fit["mx"], ref_w))
        _REGION_FIT[key] = fit
    return reg, fit


def lonlat_to_frac(lon: float, lat: float,
                   region: str = "mumbai") -> tuple[float, float]:
    """Return (x_frac, y_frac) in 0..1 for a real coordinate, matching
    exactly the projection region_map() uses: equirectangular, with a
    cos(latitude) correction on longitude so the aspect ratio is honest, fit
    with a small margin to a fixed reference box/canvas. The fit is against
    that fixed reference, not the `w`/`h` of any one `region_map()` call, so
    a caller can compute a marker's fraction once (see `render.py`) and it
    will still land in the right place at whatever size is actually drawn."""
    _, f = _region(region)
    x = (lon - f["lon_w"]) * f["cos0"] * f["scale"] + f["mx"]
    y = (f["lat_n"] - lat) * f["scale"] + f["my"]
    return x / f["ref_w"], y / f["ref_h"]


def mumbai_lonlat_to_frac(lon: float, lat: float) -> tuple[float, float]:
    """Back-compatible alias for the Mumbai region."""
    return lonlat_to_frac(lon, lat, "mumbai")


# The far shore of Mumbai Harbour/Navi Mumbai. Deliberately plainer than the
# island -- a simple, mostly-straight coast with a couple of gentle bends --
# it is there to make the harbour read as a harbour and to give the frame
# real content to fill, not to be studied. Its own lighter tint (see
# mumbai_map) keeps the peninsula the hero; it never touches _MUMBAI_COAST,
# so the gap between the two always reads as open water.
_MUMBAI_MAINLAND = [
    (72.955, 19.09), (72.93, 19.04), (72.915, 18.99), (72.925, 18.94),
    (72.945, 18.895), (72.97, 18.86), (73.05, 18.87), (73.05, 19.10),
]


def _point_in_ring(px, py, ring):
    """Ray-casting point-in-polygon test, used only for the land stipple."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            xin = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < xin:
                inside = not inside
    return inside


# Place names drawn on the tile itself. A viewer who does not know the city
# sees an abstract grey shape without them; the bay, the harbour and the
# Colaba tail are precisely what make it read as Mumbai. Each sits in open
# space rather than on the sites, and is dropped entirely if a pin is there.
_MUMBAI_PLACES = [
    (72.7878, 18.9690, "ARABIAN SEA"),
    (72.8060, 18.9290, "BACK BAY"),
    (72.8402, 18.9135, "HARBOUR"),
    (72.8140, 18.9068, "COLABA"),
]


# The lower Columbia -- the corridor the D. B. Cooper story happens in, and the
# first region added after Mumbai, which is what forced this registry to exist.
# Here the water is a river system rather than a coastline, so it is drawn as
# courses over land rather than land over sea; see `mode`. The courses run past
# the window edge deliberately: PIL clips them there, and a river that stops in
# open country reads as a drawing error.
_PNW_COLUMBIA = [
    (-123.45, 46.26), (-123.30, 46.22), (-123.15, 46.18), (-123.05, 46.15),
    (-122.96, 46.12), (-122.90, 46.08), (-122.84, 46.02), (-122.81, 45.95),
    (-122.80, 45.88), (-122.79, 45.81), (-122.78, 45.74), (-122.76, 45.68),
    (-122.71, 45.64), (-122.64, 45.61), (-122.55, 45.585), (-122.44, 45.575),
    (-122.32, 45.575), (-122.20, 45.57), (-122.05, 45.565), (-121.90, 45.60),
    (-121.72, 45.62),
]
_PNW_WILLAMETTE = [
    (-122.67, 45.38), (-122.665, 45.47), (-122.675, 45.52), (-122.70, 45.57),
    (-122.73, 45.61), (-122.765, 45.653),
]
_PNW_LEWIS = [
    (-122.78, 45.86), (-122.72, 45.865), (-122.66, 45.88), (-122.60, 45.90),
    (-122.54, 45.945), (-122.47, 45.96), (-122.40, 45.955), (-122.30, 45.94),
]
_PNW_PLACES = [
    (-122.98, 45.90, "COLUMBIA RIVER"),
    (-122.60, 46.00, "LEWIS RIVER"),
    (-122.66, 45.49, "PORTLAND"),
    (-122.56, 45.67, "VANCOUVER"),
]


_REGIONS.update({
    "mumbai": {
        "mode": "island",
        "coast": _MUMBAI_COAST,
        "mainland": _MUMBAI_MAINLAND,
        "window": (_MUMBAI_LON_W, _MUMBAI_LON_E, _MUMBAI_LAT_S, _MUMBAI_LAT_N),
        "ref": (_MUMBAI_REF_W, _MUMBAI_REF_H),
        "margin_y": _MUMBAI_MARGIN_Y,
        "graticule": ((18.90, 18.92, 18.94, 18.96),
                      (72.79, 72.81, 72.83, 72.84)),
        "places": _MUMBAI_PLACES,
    },
    "pacific-northwest": {
        "mode": "rivers",
        "water": [(_PNW_COLUMBIA, 1.0), (_PNW_WILLAMETTE, 0.55),
                  (_PNW_LEWIS, 0.5)],
        "window": (-123.45, -121.78, 45.42, 46.15),
        "ref": (900.0, 640.0),
        "margin_y": 0.06,
        "roads": False,
        "graticule": ((45.6, 45.8, 46.0),
                      (-123.2, -122.9, -122.6, -122.3, -122.0)),
        "places": _PNW_PLACES,
    },
    "generic": {
        "mode": "generic",
        "window": (0.0, 1.0, 0.0, 0.63),
        "ref": (900.0, 640.0),
        "margin_y": 0.06,
        "graticule": ((0.1, 0.25, 0.4, 0.55), (0.15, 0.35, 0.55, 0.75, 0.95)),
        "places": [],
    },
})


def _place_labels(d, w, h, ink, markers, places, region):
    """Letterspaced cartographic place names, clamped inside the tile.

    Letterspacing is drawn a character at a time because that wide, airy
    tracking is what separates a map label from a caption, and PIL has no
    tracking control of its own."""
    import collage

    size = max(8.0, h * 0.021)
    f = collage.font("condensed", int(round(size * SS)), weight=500)
    col = _lighten(ink, 0.34) + (238,)
    track = size * 0.34
    for lon, lat, text in places:
        xf, yf = lonlat_to_frac(lon, lat, region)
        widths = [d.textlength(c, font=f) / SS for c in text]
        tw = sum(widths) + track * (len(text) - 1)
        x = min(max(xf * w - tw / 2, w * 0.015), max(w * 0.015, w * 0.985 - tw))
        y = yf * h - size * 0.5
        clash = False
        for mx, my in markers:
            px, py_lo, py_hi = mx * w, my * h - h * 0.105, my * h + h * 0.012
            if (x < px + w * 0.045 and x + tw > px - w * 0.045
                    and y < py_hi and y + size > py_lo):
                clash = True
                break
        if clash:
            continue
        cx = x
        for ch, cw in zip(text, widths):
            d.text((cx * SS, y * SS), ch, font=f, fill=col)
            cx += cw + track


def region_map(w: int = 1100, h: int = 820, seed: int = 0, ink=INK,
               markers=None, highlight: int = -1,
               region: str = "generic") -> Image.Image:
    """A stylised chart of a named region from `_REGIONS`.

    The geography is data, never taste, so a board picks the region and this
    only draws it. Three shapes of region are supported, because real places
    do not all have the same one:

    `island` washes sea over the tile and lays land on top -- Mumbai's South
    peninsula, traced from a real, hand-checked coastline: Back Bay's smooth
    west-coast bite, the narrow Colaba tail, the ragged harbour docks.

    `rivers` inverts that -- land over the whole tile with the water cut into
    it -- because in a river corridor like the lower Columbia the water is the
    line, not the edge.

    `generic` is the default and draws an invented coast with no place names
    at all. That is the point: an unnamed chart reads as a map without
    claiming to be anywhere, whereas a wrong name is a factual error the
    viewer can read off the screen.

    `markers` are pins in 0..1 image fractions (see `lonlat_to_frac`),
    anchored exactly at `(x_frac * w, y_frac * h)`; `highlight` calls one out
    in a darker ink."""
    reg, _ = _region(region)
    mode = reg["mode"]
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    land = _lighten(ink, 0.86 if mode == "rivers" else 0.66) + (255,)
    mainland_fill = _lighten(ink, 0.62) + (255,)
    coast = ink + (255,)
    sea = _lighten(ink, 0.87) + (255,)
    # In a river region the water is the drawn feature, not the edge, so the
    # tones have to flip with the polarity. Filling the tile mid-grey and then
    # tracing the courses in the *sea* tone leaves a light line on a grey field
    # with no full-strength ink anywhere on it — which is how the lower
    # Columbia came out as a blank grey rectangle. Light ground, mid water,
    # inked banks: the same three-tone structure an island gets.
    river_fill = _lighten(ink, 0.55) + (255,)
    lon_w, lon_e, lat_s, lat_n = reg["window"]

    def proj(lo, la):
        return lonlat_to_frac(lo, la, region)

    # A wash over the whole tile so the water is a *surface* rather than bare
    # paper. Without it a coastline has nothing to be a coastline against and
    # the land reads as a torn scrap. In a river region the polarity flips:
    # the tile is land, and the courses are cut into it below.
    d.rectangle([0, 0, w * SS, h * SS], fill=(land if mode == "rivers" else sea))

    # a faint lat/long graticule across the tile, under everything else, so
    # what follows reads as a feature traced on a chart
    grat = ink + (16,)
    grat_w = max(1, int(w * 0.0015 * SS))
    lats, lons = reg["graticule"]
    for lat in lats:
        y = proj(lon_w, lat)[1] * h
        d.line([(0, y * SS), (w * SS, y * SS)], fill=grat, width=grat_w)
    for lon in lons:
        x = proj(lon, lat_n)[0] * w
        d.line([(x * SS, 0), (x * SS, h * SS)], fill=grat, width=grat_w)

    outline, no_speck = None, []
    if mode == "island":
        outline = [(xf * w, yf * h) for xf, yf in
                   (proj(lo, la) for lo, la in reg["coast"])]
        # the mainland shore is context, not the subject: a flat, lighter wash
        # with no coastline stroke, drawn behind the island, so the harbour
        # reads as open water between two landmasses rather than one ragged edge
        if reg.get("mainland"):
            _blob(d, [(xf * w, yf * h) for xf, yf in
                      (proj(lo, la) for lo, la in reg["mainland"])], mainland_fill)
    elif mode == "generic":
        # An invented coast: smooth, plausible, and deliberately nowhere. The
        # seed varies it so two maps in one film are not the same island.
        cx, cy, pts = 0.52, 0.5, []
        for i in range(48):
            a = 2 * math.pi * i / 48
            r = (0.30 + 0.085 * math.sin(a * 2 + seed * 0.7)
                 + 0.055 * math.sin(a * 3 + seed * 1.3)
                 + 0.030 * math.sin(a * 5 + seed * 2.1))
            pts.append(((cx + r * math.cos(a) * 1.25) * w, (cy + r * math.sin(a)) * h))
        outline = pts

    if outline is not None:
        _blob(d, outline, land)
        d.line([(x * SS, y * SS) for x, y in outline + [outline[0]]], fill=coast,
               width=max(1, int(w * 0.006 * SS)), joint="curve")

    if mode == "rivers":
        # Each course is stroked twice: an inked bank a little wider than the
        # channel, then the water laid inside it. Drawn in that order the
        # course reads as cut into the land, and the film gets the full-ink
        # line it needs to register as a chart at all.
        for pts_ll, weight in reg["water"]:
            xy = [(xf * w, yf * h) for xf, yf in (proj(lo, la) for lo, la in pts_ll)]
            no_speck.extend(xy)
            wide = max(2, int(w * 0.017 * weight * SS))
            bank = max(1, int(w * 0.0034 * SS))
            d.line([(x * SS, y * SS) for x, y in xy], fill=coast,
                   width=wide + 2 * bank, joint="curve")
            d.line([(x * SS, y * SS) for x, y in xy], fill=river_fill,
                   width=wide, joint="curve")

    # a restrained stipple texture on the land, kept off the water
    if mode == "rivers":
        x_lo, x_hi, y_lo, y_hi = 0.0, float(w), 0.0, float(h)
    else:
        xs, ys = [p[0] for p in outline], [p[1] for p in outline]
        x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
    keep_out = (w * 0.022) ** 2
    for _ in range(130):
        px, py = rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi)
        if outline is not None and not _point_in_ring(px, py, outline):
            continue
        if any((px - qx) ** 2 + (py - qy) ** 2 < keep_out for qx, qy in no_speck):
            continue
        r = rng.uniform(w * 0.0012, w * 0.0028)
        # PIL's ImageDraw doesn't alpha-blend onto the already-opaque land
        # fill, so a translucent dot would just punch a see-through hole; use
        # a solid, slightly-darker land tone instead.
        speck = _lighten(ink, rng.uniform(0.30, 0.40)) + (255,)
        d.ellipse([(px - r) * SS, (py - r) * SS, (px + r) * SS, (py + r) * SS],
                  fill=speck)

    # a couple of suggested arterial roads, following the region's long axis,
    # centred on the land's own midline rather than the frame's -- the
    # coastline above isn't symmetric in the box. A river region opts out:
    # these are invented, and invented roads that stride across a real river
    # without a bridge are worse than no roads at all.
    cx0 = (x_lo + x_hi) / (2 * w)
    for rx, amp, alpha in (((cx0, 0.009, 130), (cx0 - 0.045, 0.006, 95), (cx0 + 0.045, 0.007, 95))
                           if reg.get("roads", True) else ()):
        pts = []
        for i in range(41):
            u = i / 40
            x = w * (rx + amp * math.sin(u * 3.1 + seed + rx * 9))
            y = y_lo + (y_hi - y_lo) * (0.04 + 0.92 * u)
            pts.append((x * SS, y * SS))
        d.line(pts, fill=ink + (alpha,), width=max(1, int(w * 0.0035 * SS)), joint="curve")

    _place_labels(d, w, h, ink, markers or [], reg["places"], region)

    # markers: a pin dropped with its point exactly on the given coordinate
    for i, (xf, yf) in enumerate(markers or []):
        big = (i == highlight)
        ax, ay = xf * w, yf * h
        r = w * (0.020 if big else 0.013)
        stalk = h * (0.050 if big else 0.034)
        col = (tuple(PALETTE["accent_deep"]) + (255,)) if big else (ink + (232,))
        cx, cy = ax, ay - stalk - r
        d.line([ax * SS, ay * SS, cx * SS, cy * SS], fill=col,
               width=max(1, int(w * (0.0075 if big else 0.005) * SS)))
        ring_r = r * 1.9
        d.ellipse([(cx - ring_r) * SS, (cy - ring_r) * SS,
                   (cx + ring_r) * SS, (cy + ring_r) * SS],
                  outline=col, width=max(1, int(w * 0.0035 * SS)))
        _ellipse(d, (cx - r, cy - r, cx + r, cy + r), col)
        _ellipse(d, (ax - r * 0.26, ay - r * 0.26, ax + r * 0.26, ay + r * 0.26), coast)

    return _finish(img, w, h, seed)


def mumbai_map(w: int = 1100, h: int = 820, seed: int = 0, ink=INK,
               markers=None, highlight: int = -1) -> Image.Image:
    """Back-compatible alias for the Mumbai region of `region_map`."""
    return region_map(w, h, seed=seed, ink=ink, markers=markers,
                      highlight=highlight, region="mumbai")


BRASS = (176, 138, 74)

def route_thread(w: int = 1100, h: int = 820, seed: int = 0, ink=INK,
                 points=None, progress: float = 1.0, style: str = "taut",
                 pins: bool = True, sag: float = 0.16) -> Image.Image:
    """A red investigation-board thread running through `points`.

    `points` are (x_frac, y_frac) in 0..1 of this tile, so they can be handed
    the *same* fractions used for `mumbai_map` markers and the thread will land
    exactly on the pins. `progress` draws the thread on from the first point to
    the last, which is what turns a static diagram into a journey.

    `style="taut"` is the straight pinboard thread; `style="route"` bows each
    leg outward by `sag` of its own length, giving the looser travelled-route
    line. Set `pins=False` when the map underneath is already drawing them.
    """
    img, d = _canvas(w, h)
    pts = [(xf * w, yf * h) for xf, yf in (points or [])]
    if len(pts) < 2:
        return _finish(img, w, h, seed)

    rng = paper._rng(seed)
    thread = tuple(PALETTE["accent_deep"])
    # Build the full path first, then cut it at `progress`, so the speed of the
    # draw-on is even along the whole route rather than per-leg.
    path = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        if style == "route":
            dx, dy = x1 - x0, y1 - y0
            leg = math.hypot(dx, dy) or 1.0
            # perpendicular offset, alternating side so a multi-leg route
            # snakes instead of bulging the same way every time
            side = 1.0 if i % 2 == 0 else -1.0
            mx = (x0 + x1) / 2 - dy / leg * leg * sag * side
            my = (y0 + y1) / 2 + dx / leg * leg * sag * side
            seg = _spline([(x0, y0), (mx, my), (x1, y1)], samples_per_seg=18)
        else:
            seg = [(x0 + (x1 - x0) * t / 12.0, y0 + (y1 - y0) * t / 12.0)
                   for t in range(13)]
        path.extend(seg if i == 0 else seg[1:])

    # arc-length cut so `progress` advances at a constant speed
    cum, total = [0.0], 0.0
    for a, b in zip(path, path[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
        cum.append(total)
    want = max(0.0, min(1.0, progress)) * total
    drawn = [path[0]]
    for i in range(1, len(path)):
        if cum[i] <= want:
            drawn.append(path[i])
        else:
            span = cum[i] - cum[i - 1]
            t = (want - cum[i - 1]) / span if span else 0.0
            drawn.append((path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t,
                          path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t))
            break

    if len(drawn) > 1:
        wide = max(2, int(w * 0.009 * SS))
        # a soft offset shadow first, so the thread sits above the paper
        d.line([((x + w * 0.004) * SS, (y + h * 0.005) * SS) for x, y in drawn],
               fill=_darken(ink, 0.2) + (60,), width=wide, joint="curve")
        d.line([(x * SS, y * SS) for x, y in drawn], fill=thread + (255,),
               width=wide, joint="curve")
        # a lighter core catches the light the way twisted cord does; keep it
        # faint and offset, or it reads as a centre line down a road
        d.line([((x - w * 0.0012) * SS, (y - h * 0.0016) * SS) for x, y in drawn],
               fill=_lighten(thread, 0.34) + (48,),
               width=max(1, int(wide * 0.26)), joint="curve")

    if pins:
        reached = len(drawn)
        for i, (px, py) in enumerate(pts):
            # only pin the points the thread has actually got to
            if i and reached < len(path) and cum[min(reached, len(cum) - 1)] < \
                    _leg_start(path, pts, i):
                continue
            _brass_pin(d, px, py, w, ink, rng)

    return _finish(img, w, h, seed)


def _leg_start(path, pts, i):
    """Arc length at which vertex `i` of the polyline is reached."""
    target, run = pts[i], 0.0
    for a, b in zip(path, path[1:]):
        run += math.hypot(b[0] - a[0], b[1] - a[1])
        if math.hypot(b[0] - target[0], b[1] - target[1]) < 1e-6:
            return run
    return run


def _brass_pin(d, x, y, w, ink, rng):
    """A domed push-pin, point on (x, y), head up and slightly to the left."""
    r = w * 0.0135
    hx, hy = x - r * 0.42, y - r * 1.15
    d.line([(x + w * 0.003) * SS, (y + w * 0.003) * SS,
            (hx + w * 0.003) * SS, (hy + w * 0.003) * SS],
           fill=_darken(ink, 0.1) + (70,), width=max(1, int(w * 0.004 * SS)))
    _ellipse(d, (x - r * 0.22, y - r * 0.22, x + r * 0.22, y + r * 0.22),
             _darken(ink, 0.25) + (255,))
    d.line([x * SS, y * SS, hx * SS, hy * SS],
           fill=_darken(BRASS, 0.25) + (255,),
           width=max(1, int(w * 0.0035 * SS)))
    _ellipse(d, (hx - r, hy - r, hx + r, hy + r),
             tuple(BRASS) + (255,))
    _ellipse(d, (hx - r * 0.62, hy - r * 0.72, hx + r * 0.10, hy - r * 0.02),
             _lighten(BRASS, 0.45) + (220,))


def timeline_chart(w: int = 360, h: int = 900, seed: int = 0, ink=INK,
                    ticks=None, progress: float = 1.0) -> Image.Image:
    """A vertical timeline spine with tick marks. `progress` 0..1 fills the
    spine solid from the top down to that fraction and leaves the remainder
    a hollow channel, so the renderer can animate time advancing. Tick `y`
    positions are exact — the caller sets time labels beside them."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    sx = w * 0.16
    sw = w * 0.052
    top, bottom = h * 0.02, h * 0.98
    prog = max(0.0, min(1.0, progress))
    fill_y = top + (bottom - top) * prog
    near_end = fill_y >= bottom - sw

    d.rounded_rectangle([(sx - sw / 2) * SS, top * SS, (sx + sw / 2) * SS, bottom * SS],
                        radius=sw * 0.5 * SS, outline=ink + (130,),
                        width=max(1, int(sw * 0.30 * SS)))
    if fill_y > top + sw * 0.5:
        d.rounded_rectangle([(sx - sw / 2) * SS, top * SS, (sx + sw / 2) * SS, fill_y * SS],
                            radius=sw * 0.5 * SS, fill=ink + (255,),
                            corners=(True, True, near_end, near_end))

    for yf, major in (ticks or []):
        y = yf * h  # exact — never jittered, labels line up against this
        wob = 1 + float(rng.normal(0, 0.03))
        length = w * (0.34 if major else 0.17) * wob
        wid = max(1, int((sw * (0.60 if major else 0.28)) * SS))
        solid = y <= fill_y
        col = ink + (255,) if solid else ink + (140,)
        d.line([sx * SS, y * SS, (sx + length) * SS, y * SS], fill=col, width=wid)
        if major:
            dr = sw * 0.58
            _ellipse(d, (sx - dr, y - dr, sx + dr, y + dr), col)

    return _finish(img, w, h, seed)


# --------------------------------------------------------------- vehicles ----


def car(w: int = 320, h: int = 150, seed: int = 0, ink=INK, kind: str = "sedan") -> Image.Image:
    """Side-view vehicle silhouette. `kind`: sedan, police, taxi, suv,
    ambulance or bus — plain civic profiles, no markings beyond a light
    bar, sign or cross panel. Wheels are discs with a paper-lit hub."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (232, 224, 200, 255)
    gy = h * 0.66  # undercarriage line, shared by the body and the wheels

    bodies = {
        "sedan": [(0.05, 0), (0.05, -0.15), (0.13, -0.30), (0.29, -0.50),
                  (0.42, -0.56), (0.62, -0.56), (0.76, -0.48), (0.90, -0.28),
                  (0.97, -0.16), (0.97, 0)],
        "suv": [(0.05, 0), (0.05, -0.25), (0.10, -0.51), (0.20, -0.58),
                (0.80, -0.58), (0.90, -0.51), (0.95, -0.25), (0.95, 0)],
        "ambulance": [(0.04, 0), (0.04, -0.22), (0.08, -0.51), (0.30, -0.58),
                      (0.86, -0.58), (0.94, -0.40), (0.97, -0.22), (0.97, 0)],
        "bus": [(0.02, 0), (0.02, -0.16), (0.04, -0.50), (0.10, -0.58),
                (0.90, -0.58), (0.96, -0.50), (0.98, -0.16), (0.98, 0)],
    }
    bodies["police"] = bodies["sedan"]
    bodies["taxi"] = bodies["sedan"]
    frac = bodies.get(kind, bodies["sedan"])
    jx = float(rng.normal(0, w * 0.003))
    _blob(d, [(w * x + jx, gy + h * y) for x, y in frac], F)

    # cabin glazing
    if kind == "bus":
        wy0, wy1 = gy - h * 0.52, gy - h * 0.28
        n_win = 6
        for i in range(n_win):
            x0 = w * 0.12 + i * (w * 0.78 / n_win)
            x1 = x0 + w * 0.78 / n_win * 0.68
            d.rectangle([x0 * SS, wy0 * SS, x1 * SS, wy1 * SS], fill=pale)
    elif kind == "ambulance":
        _blob(d, [(w * 0.62, gy - h * 0.50), (w * 0.80, gy - h * 0.53),
                  (w * 0.80, gy - h * 0.28), (w * 0.62, gy - h * 0.28)], pale)
        cx0, cy0 = w * 0.58, gy - h * 0.38
        cw, ch = w * 0.10, h * 0.23
        d.rectangle([(cx0 - cw * 0.50) * SS, (cy0 - ch * 0.16) * SS,
                     (cx0 + cw * 0.50) * SS, (cy0 + ch * 0.16) * SS], fill=pale)
        d.rectangle([(cx0 - cw * 0.16) * SS, (cy0 - ch * 0.50) * SS,
                     (cx0 + cw * 0.16) * SS, (cy0 + ch * 0.50) * SS], fill=pale)
    else:
        d.rectangle([w * 0.31 * SS, (gy - h * 0.53) * SS, w * 0.74 * SS, (gy - h * 0.33) * SS], fill=pale)

    if kind == "police":
        bx0, bx1 = w * 0.42, w * 0.58
        by0, by1 = gy - h * 0.65, gy - h * 0.555
        d.rectangle([bx0 * SS, by0 * SS, bx1 * SS, by1 * SS], fill=F)
        d.rectangle([w * 0.495 * SS, by0 * SS, w * 0.505 * SS, by1 * SS], fill=pale)
    elif kind == "taxi":
        bx0, bx1 = w * 0.47, w * 0.57
        by0, by1 = gy - h * 0.63, gy - h * 0.555
        d.rectangle([bx0 * SS, by0 * SS, bx1 * SS, by1 * SS], fill=F)
        d.rectangle([(bx0 + w * 0.012) * SS, (by0 + h * 0.015) * SS,
                     (bx1 - w * 0.012) * SS, (by1 - h * 0.015) * SS], fill=pale)

    rW = h * 0.155
    wx = (0.15, 0.85) if kind == "bus" else (0.19, 0.83)
    for fx in wx:
        cx = w * fx
        _ellipse(d, (cx - rW, gy - rW, cx + rW, gy + rW), F)
        _ellipse(d, (cx - rW * 0.42, gy - rW * 0.42, cx + rW * 0.42, gy + rW * 0.42), pale)

    return _finish(img, w, h, seed)


def dinghy(w: int = 340, h: int = 130, seed: int = 0, ink=INK) -> Image.Image:
    """A low RIB-style inflatable — a fat rounded gunwale tube, a flat
    transom and a small outboard motor at the stern. Distinct from the
    slimmer, angular `boat()`."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    jy = float(rng.normal(0, h * 0.006))

    # fat rounded gunwale tube: a stadium shape, rounded at the bow
    # (left), squared off at the transom (right) — bold, not a sliver
    tube_x0, tube_x1 = w * 0.06, w * 0.78
    tube_y0, tube_y1 = h * 0.18 + jy, h * 0.64 + jy
    r = (tube_y1 - tube_y0) / 2
    d.rounded_rectangle([tube_x0 * SS, tube_y0 * SS, tube_x1 * SS, tube_y1 * SS],
                        radius=r * SS, corners=(True, False, True, False), fill=F)

    # shallow hull below, following the tube down to a flat keel
    hull = [(w * 0.10, h * 0.54), (w * 0.16, h * 0.83), (w * 0.55, h * 0.90),
            (w * 0.80, h * 0.86), (w * 0.80, h * 0.54)]
    _blob(d, hull, F)

    # a pale seam where the inflated tube sits above the hull, so it
    # reads as a tube-boat and not just a plain rounded hull
    seam_y = tube_y1 - r * 0.28
    d.line([w * 0.11 * SS, seam_y * SS, w * 0.76 * SS, seam_y * SS],
           fill=_lighten(ink, 0.6) + (150,), width=max(1, int(h * 0.018 * SS)))

    # outboard motor on the transom
    _blob(d, [(w * 0.77, h * 0.30), (w * 0.89, h * 0.32), (w * 0.89, h * 0.56),
              (w * 0.77, h * 0.58)], F)
    d.line([w * 0.89 * SS, h * 0.36 * SS, w * 0.97 * SS, h * 0.36 * SS],
           fill=F, width=max(1, int(h * 0.05 * SS)))

    d.line([w * 0.05 * SS, h * 0.93 * SS, w * 0.95 * SS, h * 0.93 * SS],
           fill=ink + (110,), width=max(1, int(h * 0.030 * SS)))
    return _finish(img, w, h, seed)


def trawler(w: int = 460, h: int = 230, seed: int = 0, ink=INK) -> Image.Image:
    """A small wooden fishing vessel — hull, a raised wheelhouse aft, and a
    mast and boom forward for the nets."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (232, 224, 200, 255)
    waterline = h * 0.68 + float(rng.normal(0, h * 0.006))

    hull = [(w * 0.04, waterline), (w * 0.05, waterline + h * 0.10),
            (w * 0.55, waterline + h * 0.14), (w * 0.90, waterline + h * 0.10),
            (w * 0.97, waterline - h * 0.02), (w * 0.90, waterline - h * 0.10),
            (w * 0.30, waterline - h * 0.16), (w * 0.10, waterline - h * 0.12)]
    _blob(d, hull, F)

    # raised wheelhouse, aft third — its base overlaps the deck line so it
    # reads as sitting on the hull, never floating above it
    wx0, wx1 = w * 0.66, w * 0.87
    wy0, wy1 = waterline - h * 0.34, waterline - h * 0.06
    d.rectangle([wx0 * SS, wy0 * SS, wx1 * SS, wy1 * SS], fill=F)
    d.rectangle([(wx0 - w * 0.015) * SS, (wy0 - h * 0.03) * SS,
                 (wx1 + w * 0.015) * SS, wy0 * SS], fill=F)
    d.rectangle([(wx0 + (wx1 - wx0) * 0.22) * SS, (wy0 + h * 0.06) * SS,
                 (wx0 + (wx1 - wx0) * 0.60) * SS, (wy0 + h * 0.17) * SS], fill=pale)

    # mast, boom and a thin forestay, forward third — for nets, never
    # rigged as anything else
    mx = w * 0.28
    mast_top = waterline - h * 0.62
    d.line([mx * SS, waterline * SS, mx * SS, mast_top * SS], fill=F, width=max(1, int(w * 0.012 * SS)))
    boom_y = mast_top + h * 0.20
    d.line([mx * SS, boom_y * SS, w * 0.07 * SS, (boom_y + h * 0.07) * SS],
           fill=F, width=max(1, int(w * 0.015 * SS)))
    d.line([mx * SS, mast_top * SS, w * 0.06 * SS, waterline * SS],
           fill=F, width=max(1, int(w * 0.004 * SS)))

    return _finish(img, w, h, seed)


def helicopter(w: int = 460, h: int = 210, seed: int = 0, ink=INK, rotor: float = 0.0) -> Image.Image:
    """Side view: bubble cabin, tapering tail boom, tail rotor and skids.
    `rotor` 0..1 blends the main rotor from resting blades to a spinning,
    flattened blur disc."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    t = max(0.0, min(1.0, rotor))
    body_y = h * 0.52 + float(rng.normal(0, h * 0.003))

    cabin = [(w * 0.10, body_y + h * 0.04), (w * 0.07, body_y - h * 0.10),
             (w * 0.16, body_y - h * 0.24), (w * 0.34, body_y - h * 0.28),
             (w * 0.34, body_y + h * 0.14), (w * 0.20, body_y + h * 0.20)]
    _blob(d, cabin, F)
    _ellipse(d, (w * 0.06, body_y - h * 0.20, w * 0.32, body_y + h * 0.16), F)

    # tail boom tapering back to a small fin and tail rotor
    boom = [(w * 0.30, body_y - h * 0.10), (w * 0.86, body_y - h * 0.03),
            (w * 0.86, body_y + h * 0.04), (w * 0.30, body_y + h * 0.06)]
    _blob(d, boom, F)
    fin = [(w * 0.84, body_y - h * 0.14), (w * 0.96, body_y - h * 0.16),
           (w * 0.94, body_y + h * 0.08), (w * 0.85, body_y + h * 0.07)]
    _blob(d, fin, F)
    tr = h * 0.075
    tcx, tcy = w * 0.945, body_y - h * 0.04
    d.line([tcx * SS, (tcy - tr) * SS, tcx * SS, (tcy + tr) * SS], fill=F, width=max(1, int(w * 0.006 * SS)))
    d.line([(tcx - tr) * SS, tcy * SS, (tcx + tr) * SS, tcy * SS], fill=F, width=max(1, int(w * 0.006 * SS)))

    # skids — both struts sit under the cabin, where the hull is tall
    # enough that the strut top is always inside the solid silhouette
    skid_x0, skid_x1 = w * 0.06, w * 0.40
    for dy in (0.0, 1.0):
        y = body_y + h * (0.24 + dy * 0.05)
        d.line([skid_x0 * SS, y * SS, skid_x1 * SS, y * SS], fill=F, width=max(1, int(h * 0.028 * SS)))
    for sx in (0.13, 0.30):
        d.line([w * sx * SS, (body_y + h * 0.06) * SS, w * sx * SS, (body_y + h * 0.24) * SS],
               fill=F, width=max(1, int(w * 0.014 * SS)))

    # main rotor: a mast, then blades fading to a blurred disc as `rotor` rises
    mast_x = w * 0.30
    mast_top = body_y - h * 0.34
    d.line([mast_x * SS, (body_y - h * 0.26) * SS, mast_x * SS, mast_top * SS],
           fill=F, width=max(1, int(w * 0.012 * SS)))
    span = w * 0.42
    if t < 0.999:
        a_blade = int(255 * (1 - t))
        ang = math.radians(14)
        dx, dy2 = math.cos(ang) * span, math.sin(ang) * span * 0.32
        d.line([(mast_x - dx) * SS, (mast_top - dy2) * SS, (mast_x + dx) * SS, (mast_top + dy2) * SS],
               fill=ink + (a_blade,), width=max(1, int(w * 0.014 * SS)))
        d.line([(mast_x - dy2 * 0.6) * SS, (mast_top - dx * 0.18) * SS,
                (mast_x + dy2 * 0.6) * SS, (mast_top + dx * 0.18) * SS],
               fill=ink + (a_blade,), width=max(1, int(w * 0.012 * SS)))
    if t > 0.001:
        a_disc = int(190 * t)
        rh = h * (0.012 + 0.020 * t)
        d.ellipse([(mast_x - span) * SS, (mast_top - rh) * SS, (mast_x + span) * SS, (mast_top + rh) * SS],
                  fill=ink + (a_disc,))

    return _finish(img, w, h, seed)


# ---------------------------------------------------------------- figures ----


def _person(d, cx, base_y, scale, ink, kind, rng):
    """Draw one calm, standing figure — feet at `base_y`, head-to-toe
    height `scale`. Shared by `figure()` and `crowd()`. Never armed."""
    F = ink + (255,)
    pale = _lighten(ink, 0.72) + (200,)
    head_r = scale * 0.085
    head_cy = base_y - scale * 0.915
    shoulder_y = head_cy + head_r * 0.80  # tucked under the head, no neck gap
    waist_y = base_y - scale * 0.44
    hip_y = base_y - scale * 0.40
    leg_split_y = hip_y + scale * 0.03
    sh_w = scale * (0.150 if kind == "commando" else 0.125)
    waist_w = scale * 0.085
    hip_w = scale * 0.105
    foot_gap = scale * 0.018

    # arms, drawn first so the torso crops the shoulder join cleanly
    arm_w = max(2.0, scale * 0.050)
    for side in (-1, 1):
        sx = cx + side * sh_w * 0.86
        wx = cx + side * sh_w * 0.98
        wy = waist_y + scale * 0.02
        d.line([sx * SS, shoulder_y * SS, wx * SS, wy * SS], fill=F, width=int(arm_w * SS))
        _ellipse(d, (wx - arm_w / 2, wy - arm_w / 2, wx + arm_w / 2, wy + arm_w / 2), F)

    # torso and legs as one silhouette, split by a narrow gap at the feet
    body = [
        (cx - sh_w, shoulder_y), (cx - waist_w, waist_y), (cx - hip_w, hip_y),
        (cx - hip_w, base_y), (cx - foot_gap, base_y), (cx - foot_gap, leg_split_y),
        (cx + foot_gap, leg_split_y), (cx + foot_gap, base_y),
        (cx + hip_w, base_y), (cx + hip_w, hip_y), (cx + waist_w, waist_y), (cx + sh_w, shoulder_y),
    ]
    _blob(d, body, F)

    _ellipse(d, (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), F)

    if kind == "police":
        crown_w, crown_h = head_r * 1.18, head_r * 0.60
        cy0 = head_cy - head_r * 0.92
        d.rectangle([(cx - crown_w) * SS, (cy0 - crown_h) * SS,
                     (cx + crown_w) * SS, (cy0 + crown_h * 0.3) * SS], fill=F)
        _ellipse(d, (cx - crown_w * 1.05, cy0 - head_r * 0.02, cx + crown_w * 1.05, cy0 + head_r * 0.22), F)
    elif kind == "commando":
        hel_r = head_r * 1.22
        hel_cy = head_cy - head_r * 0.12
        d.pieslice([(cx - hel_r) * SS, (hel_cy - hel_r) * SS, (cx + hel_r) * SS, (hel_cy + hel_r) * SS],
                   180, 360, fill=F)
        d.rectangle([(cx - hel_r) * SS, hel_cy * SS, (cx + hel_r) * SS, (hel_cy + head_r * 0.30) * SS], fill=F)
        rim_y = hel_cy + head_r * 0.30
        d.line([(cx - hel_r * 0.96) * SS, rim_y * SS, (cx + hel_r * 0.96) * SS, rim_y * SS],
               fill=pale, width=max(1, int(scale * 0.010 * SS)))
        for k in (0.30, 0.55):
            yy = shoulder_y + (waist_y - shoulder_y) * k
            d.line([(cx - sh_w * 0.7) * SS, yy * SS, (cx + sh_w * 0.7) * SS, yy * SS],
                   fill=pale, width=max(1, int(scale * 0.012 * SS)))
    elif kind == "staff":
        collar_y = shoulder_y + scale * 0.16
        for side in (-1, 1):
            d.line([cx * SS, (shoulder_y + scale * 0.02) * SS,
                    (cx + side * sh_w * 0.55) * SS, collar_y * SS],
                   fill=pale, width=max(1, int(scale * 0.014 * SS)))
        d.line([(cx - waist_w * 0.9) * SS, waist_y * SS, (cx + waist_w * 0.9) * SS, waist_y * SS],
               fill=pale, width=max(1, int(scale * 0.012 * SS)))


def figure(h: int = 280, seed: int = 0, ink=INK, kind: str = "civilian") -> Image.Image:
    """A single standing figure, calm and neutral. `kind`: civilian, police
    (peaked cap), commando (helmet and a bulky vest outline) or staff (a
    hint of a uniform jacket). No weapons or props of any kind."""
    w = int(h * 0.46)
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    cx = w * 0.5 + float(rng.normal(0, w * 0.008))
    _person(d, cx, h * 0.985, h * 0.93, ink, kind, rng)
    return _finish(img, w, h, seed)


def crowd(w: int = 900, h: int = 300, seed: int = 0, ink=INK, count: int = 14) -> Image.Image:
    """A loose row of overlapping standing figures at varied heights and
    spacing, receding slightly — reads as *a lot of people*, not
    individuals. Depth is faked with scale and a lighter ink."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    people = []
    for i in range(count):
        u = i / max(1, count - 1)
        depth = float(rng.uniform(0.5, 1.0))
        x = w * (0.04 + 0.92 * u) + float(rng.normal(0, w * 0.015))
        people.append((depth, x))
    people.sort(key=lambda t: t[0])  # far (small, pale) first, near drawn on top
    for depth, x in people:
        scale = h * (0.56 + 0.34 * depth)
        base_y = h * (0.88 + 0.08 * depth)
        shade = ink if depth > 0.82 else _lighten(ink, (1 - depth) * 0.5)
        _person(d, x, base_y, scale, shade, "civilian", rng)
    return _finish(img, w, h, seed)


# -------------------------------------------------------------- buildings ----


def terminus(w: int = 960, h: int = 560, seed: int = 0, ink=INK) -> Image.Image:
    """A Victorian-Gothic railway terminus — pointed arches, a gabled clock
    tower and slender spires. Deliberately distinct from the round-arched,
    dome-turreted `grand_hotel()`."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (238, 233, 214, 255)
    roof = h * 0.60 + float(rng.normal(0, h * 0.004))
    base = h * 0.985

    d.rectangle([w * 0.05 * SS, roof * SS, w * 0.40 * SS, base * SS], fill=F)
    d.rectangle([w * 0.60 * SS, roof * SS, w * 0.95 * SS, base * SS], fill=F)

    # pointed Gothic-arch windows, two storeys, on both wings
    for wx0, wx1 in ((0.05, 0.40), (0.60, 0.95)):
        cols = 5
        seg = (wx1 - wx0 - 0.056) / cols
        for r in range(2):
            y0 = roof + h * (0.10 + r * 0.20)
            y1 = y0 + h * 0.145
            for c in range(cols):
                x0 = w * (wx0 + 0.028 + c * seg)
                x1 = x0 + w * seg * 0.56
                mid = (x0 + x1) / 2
                rect_top = y0 + (x1 - x0) * 0.25
                apex = y0 - (x1 - x0) * 0.62
                d.rectangle([x0 * SS, rect_top * SS, x1 * SS, y1 * SS], fill=pale)
                _blob(d, [(x0, rect_top), (mid, apex), (x1, rect_top)], pale)

    # central block, taller than the wings, with a triangular gable
    cx = w * 0.5
    cb_top = roof - h * 0.20
    d.rectangle([w * 0.40 * SS, cb_top * SS, w * 0.60 * SS, base * SS], fill=F)
    gable_h = h * 0.10
    _blob(d, [(w * 0.385, cb_top), (cx, cb_top - gable_h), (w * 0.615, cb_top)], F)

    # clock roundel set into the gable
    cr = h * 0.062
    ccy = cb_top - gable_h * 0.42
    _ellipse(d, (cx - cr, ccy - cr, cx + cr, ccy + cr), pale)
    d.ellipse([(cx - cr) * SS, (ccy - cr) * SS, (cx + cr) * SS, (ccy + cr) * SS],
              outline=F, width=max(1, int(h * 0.008 * SS)))
    for a in (0, 90, 180, 270):
        rad = math.radians(a)
        d.line([cx * SS, ccy * SS, (cx + math.cos(rad) * cr * 0.78) * SS, (ccy + math.sin(rad) * cr * 0.78) * SS],
               fill=F, width=max(1, int(h * 0.010 * SS)))
    d.line([cx * SS, ccy * SS, (cx + cr * 0.30) * SS, (ccy - cr * 0.45) * SS],
           fill=F, width=max(1, int(h * 0.014 * SS)))
    d.line([cx * SS, ccy * SS, (cx - cr * 0.05) * SS, (ccy - cr * 0.55) * SS],
           fill=F, width=max(1, int(h * 0.010 * SS)))

    # tower above the gable: a ribbed drum, a dome, and a slender spire (not
    # a rounded finial) so the skyline reads differently from the hotel
    dr_w = w * 0.115
    drum_top = cb_top - gable_h
    drum_h = h * 0.075
    d.rectangle([(cx - dr_w / 2) * SS, (drum_top - drum_h) * SS, (cx + dr_w / 2) * SS, drum_top * SS], fill=F)
    dome_r = w * 0.075
    dome_h = dome_r * 1.3
    dome_b = drum_top - drum_h
    left, right = [], []
    n = 32
    for i in range(n + 1):
        v = i / n
        hw = dome_r * (max(0.0, 1.0 - v ** 2.2) ** 0.6)
        y = dome_b - dome_h * v
        left.append((cx - hw, y))
        right.append((cx + hw, y))
    _blob(d, left + list(reversed(right)), F)
    spire_h = h * 0.135
    tip = dome_b - dome_h
    _blob(d, [(cx - w * 0.014, tip), (cx, tip - spire_h), (cx + w * 0.014, tip)], F)

    # slender pointed corner spires (not domed turrets, unlike the hotel)
    for sx in (0.115, 0.885):
        tx = w * sx
        tw = w * 0.032
        ttop = roof - h * 0.135
        d.rectangle([(tx - tw / 2) * SS, ttop * SS, (tx + tw / 2) * SS, roof * SS], fill=F)
        _blob(d, [(tx - tw * 0.75, ttop), (tx, ttop - h * 0.075), (tx + tw * 0.75, ttop)], F)

    return _finish(img, w, h, seed)


def cafe_front(w: int = 720, h: int = 440, seed: int = 0, ink=INK) -> Image.Image:
    """A small street cafe — scalloped awning, big shopfront windows, and
    two round pavement tables with chairs out front."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (234, 227, 204, 255)

    # facade — its top sits below the awning's lowest scallop so the
    # scalloped fringe is visible against the paper, not swallowed by it
    d.rectangle([w * 0.06 * SS, h * 0.24 * SS, w * 0.94 * SS, h * 0.60 * SS], fill=F)

    # scalloped awning: a straight top edge, wavy bottom, one ink silhouette
    top_y = h * 0.04
    valley_y = top_y + h * 0.05
    depth = h * 0.12
    scallops = 7
    ax0, ax1 = w * 0.03, w * 0.97
    seg = (ax1 - ax0) / scallops
    pts = [(ax0, top_y)]
    for i in range(scallops):
        base_x = ax0 + seg * i
        for j in range(0, 9):
            t = j / 8
            y = valley_y + math.sin(math.pi * t) * depth
            pts.append((base_x + seg * t, y + float(rng.normal(0, h * 0.004))))
    pts.append((ax1, top_y))
    _blob(d, pts, F)

    # shopfront glass, two panes with a mullion between them
    gy0, gy1 = h * 0.28, h * 0.56
    d.rectangle([w * 0.11 * SS, gy0 * SS, w * 0.46 * SS, gy1 * SS], fill=pale)
    d.rectangle([w * 0.54 * SS, gy0 * SS, w * 0.89 * SS, gy1 * SS], fill=pale)
    for gx0, gx1 in ((0.11, 0.46), (0.54, 0.89)):
        midx = w * (gx0 + gx1) / 2
        d.line([midx * SS, gy0 * SS, midx * SS, gy1 * SS], fill=F, width=max(1, int(w * 0.006 * SS)))
        midy = h * (gy0 + gy1) / (2 * h)
        d.line([w * gx0 * SS, midy * SS, w * gx1 * SS, midy * SS], fill=F, width=max(1, int(w * 0.005 * SS)))

    # two round pavement tables with chairs
    for tx, seed_off in ((w * 0.24, 0), (w * 0.76, 1)):
        ty = h * 0.86
        leg_top = h * 0.78
        d.line([tx * SS, leg_top * SS, tx * SS, ty * SS], fill=F, width=max(1, int(w * 0.012 * SS)))
        _ellipse(d, (tx - w * 0.09, leg_top - h * 0.05, tx + w * 0.09, leg_top + h * 0.025), F)
        for cxo in (-1, 1):
            chx = tx + cxo * w * 0.145
            seat_half, back_half = w * 0.05, w * 0.022
            seat_y0, seat_y1 = h * 0.815, h * 0.865
            back_top = h * 0.70
            # backrest and seat as two fused solid bars — a bold chair
            # silhouette, not a wire outline — legs are the only thin lines
            back_cx = chx + cxo * (seat_half - back_half)
            d.rectangle([(back_cx - back_half) * SS, back_top * SS,
                         (back_cx + back_half) * SS, seat_y1 * SS], fill=F)
            d.rectangle([(chx - seat_half) * SS, seat_y0 * SS,
                         (chx + seat_half) * SS, seat_y1 * SS], fill=F)
            for lx in (chx - seat_half * 0.7, chx + seat_half * 0.7):
                d.line([lx * SS, seat_y1 * SS, lx * SS, h * 0.965 * SS],
                       fill=F, width=max(1, int(w * 0.010 * SS)))

    return _finish(img, w, h, seed)


def hospital(w: int = 820, h: int = 480, seed: int = 0, ink=INK) -> Image.Image:
    """A plain institutional block — rows of identical windows and a clear
    cross sign on the facade."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (236, 231, 212, 255)
    roof = h * 0.10
    base = h * 0.98

    d.rectangle([w * 0.06 * SS, roof * SS, w * 0.94 * SS, base * SS], fill=F)

    # rows of identical windows — plain and regular, an institution not a landmark
    cols, rows = 8, 4
    for r in range(rows):
        y0 = roof + h * (0.13 + r * 0.185)
        y1 = y0 + h * 0.115
        for c in range(cols):
            x0 = w * 0.11 + c * (w * 0.78 / cols)
            x1 = x0 + w * 0.78 / cols * 0.62
            d.rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=pale)

    # a raised sign panel with a clear cross, centred above the entrance
    px0, px1 = w * 0.42, w * 0.58
    py0, py1 = roof - h * 0.09, roof + h * 0.02
    d.rectangle([px0 * SS, py0 * SS, px1 * SS, py1 * SS], fill=F)
    pcx, pcy = (px0 + px1) / 2, (py0 + py1) / 2
    cw, ch = (px1 - px0) * 0.42, (py1 - py0) * 0.66
    d.rectangle([(pcx - cw * 0.5) * SS, (pcy - ch * 0.17) * SS, (pcx + cw * 0.5) * SS, (pcy + ch * 0.17) * SS], fill=pale)
    d.rectangle([(pcx - cw * 0.17) * SS, (pcy - ch * 0.5) * SS, (pcx + cw * 0.17) * SS, (pcy + ch * 0.5) * SS], fill=pale)

    return _finish(img, w, h, seed)


# ----------------------------------------------------------- fire & smoke ----


def smoke(w: int = 640, h: int = 560, seed: int = 0, ink=INK, density: float = 1.0) -> Image.Image:
    """A billowing plume, rising and widening, built from soft overlapping
    blobs. `density` 0..1 scales opacity and how much of it has built up.
    Smoke only — never flames or debris — for over a burning roofline."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    sw, sh = w * SS, h * SS
    dens = max(0.0, min(1.0, density))
    n = int(9 + 20 * dens)
    base_x = w * 0.5
    for i in range(n):
        u = i / max(1, n - 1)
        y = h * 0.95 - u * h * 0.86 + float(rng.normal(0, h * 0.01))
        x = base_x + math.sin(u * 3.3 + seed * 0.7) * w * 0.14 * u + float(rng.normal(0, w * 0.03))
        r = (w * 0.09 + w * 0.20 * u) * float(rng.uniform(0.80, 1.15))
        a = int((64 + 70 * dens) * (1 - 0.35 * u))
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse(
            [(x - r) * SS, (y - r * 0.8) * SS, (x + r) * SS, (y + r * 0.8) * SS], fill=ink + (a,))
        img = Image.alpha_composite(img, layer)
    img = img.filter(ImageFilter.GaussianBlur(max(2, int(w * SS * 0.010))))
    return _finish(img, w, h, seed, texture=False)


def flame(w: int = 280, h: int = 320, seed: int = 0, ink=INK, strength: float = 1.0) -> Image.Image:
    """A simple stylised fire shape — a few warm tongues, the same two-tone
    treatment as `candle()`. Used small and sparingly, never for ruin."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    s = max(0.05, min(1.0, strength))
    base_y = h * 0.95
    cx = w * 0.5

    def tongue(tcx, height, half_w):
        return [(tcx, base_y - height), (tcx + half_w, base_y - height * 0.50),
                (tcx + half_w * 0.77, base_y - height * 0.13), (tcx, base_y),
                (tcx - half_w * 0.77, base_y - height * 0.13), (tcx - half_w, base_y - height * 0.50)]

    # a faint ink scorch, grounding the flame before the warm tongues cover it
    _ellipse(d, (cx - w * 0.16, base_y - h * 0.01, cx + w * 0.16, base_y + h * 0.02), ink + (70,))

    outer = (222, 90, 40, 235)
    inner_c = (255, 202, 100, 235)
    layout = ((-0.20, 0.72, 0.17), (0.18, 0.62, 0.15), (0.0, 1.0, 0.22))
    for dx, hf, wf in layout:
        jx = float(rng.normal(0, w * 0.008))
        _blob(d, tongue(cx + dx * w + jx, h * hf * s, w * wf), outer)
    _blob(d, tongue(cx + float(rng.normal(0, w * 0.006)), h * 0.62 * s, w * 0.11), inner_c)

    return _finish(img, w, h, seed)


# ---------------------------------------------------------------- devices ----


def phone(h: int = 240, seed: int = 0, ink=INK, kind: str = "handset") -> Image.Image:
    """A telephone. `handset` is a classic curved receiver; `sat` is a
    blocky satellite phone with a stubby antenna."""
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (232, 226, 206, 255)

    if kind == "sat":
        w = int(h * 0.44)
        img, d = _canvas(w, h)
        jx = float(rng.normal(0, w * 0.01))
        ax = w * 0.5 + jx
        d.line([ax * SS, h * 0.14 * SS, ax * SS, h * 0.02 * SS],
               fill=F, width=max(1, int(w * 0.09 * SS)))
        _ellipse(d, (ax - w * 0.045, h * 0.0, ax + w * 0.045, h * 0.035), F)
        body = [(w * 0.16, h * 0.98), (w * 0.14, h * 0.20), (w * 0.22, h * 0.12),
                (w * 0.78, h * 0.12), (w * 0.86, h * 0.20), (w * 0.84, h * 0.98)]
        _blob(d, body, F)
        d.rectangle([w * 0.30 * SS, h * 0.24 * SS, w * 0.70 * SS, h * 0.38 * SS], fill=pale)
        for r in range(3):
            ry = h * (0.50 + r * 0.13)
            for c in range(3):
                rx = w * (0.32 + c * 0.18)
                _ellipse(d, (rx - w * 0.035, ry - w * 0.035, rx + w * 0.035, ry + w * 0.035), pale)
    else:
        w = int(h * 1.20)
        img, d = _canvas(w, h)
        cup_r = h * 0.225
        ax, ay = w * 0.20, h * 0.30
        bx, by = w * 0.80, h * 0.70
        mx, my = (ax + bx) / 2, (ay + by) / 2
        perp_x, perp_y = -(by - ay), (bx - ax)
        norm = math.hypot(perp_x, perp_y) or 1.0
        bow = h * 0.16
        ctrl = [(ax, ay), (mx + perp_x / norm * bow, my + perp_y / norm * bow), (bx, by)]
        spine = _spline(ctrl)
        bw = h * (0.30 + float(rng.normal(0, 0.006)))
        sw = max(1, int(bw * SS))
        pts = [(p[0] * SS, p[1] * SS) for p in spine]
        # a plain multi-point line leaves thin notches at each joint on a
        # stroke this thick — stamp a disc at every sample to seal them
        d.line(pts, fill=F, width=sw, joint="curve")
        rr = sw / 2
        for (px, py) in pts:
            d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=F)
        _ellipse(d, (ax - cup_r, ay - cup_r, ax + cup_r, ay + cup_r), F)
        _ellipse(d, (bx - cup_r, by - cup_r, bx + cup_r, by + cup_r), F)

    return _finish(img, w, h, seed)


def cctv(w: int = 300, h: int = 220, seed: int = 0, ink=INK) -> Image.Image:
    """A wall-mounted security camera on a bracket — CCTV evidence."""
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    pale = (232, 226, 206, 255)
    jx = float(rng.normal(0, w * 0.004))

    # wall mount plate, upper-left
    d.rectangle([w * 0.04 * SS, h * 0.04 * SS, w * 0.20 * SS, h * 0.30 * SS], fill=F)

    # camera body: a squat box with a lens ring at the front (right) end
    bx0, by0, bx1, by1 = w * 0.30 + jx, h * 0.32, w * 0.86 + jx, h * 0.62
    d.rounded_rectangle([bx0 * SS, by0 * SS, bx1 * SS, by1 * SS], radius=(by1 - by0) * 0.28 * SS, fill=F)

    # bracket arm: a straight constant-width rod from inside the wall plate
    # to inside the body, so both ends fuse cleanly with no seam
    ax0, ay0 = w * 0.16, h * 0.18
    ax1, ay1 = bx0 + (bx1 - bx0) * 0.12, by0 + (by1 - by0) * 0.30
    adx, ady = ax1 - ax0, ay1 - ay0
    alen = math.hypot(adx, ady) or 1.0
    aux, auy = adx / alen, ady / alen
    apx, apy = -auy, aux
    aw = h * 0.075
    arm = [(ax0 + apx * aw / 2, ay0 + apy * aw / 2), (ax1 + apx * aw / 2, ay1 + apy * aw / 2),
           (ax1 - apx * aw / 2, ay1 - apy * aw / 2), (ax0 - apx * aw / 2, ay0 - apy * aw / 2)]
    _blob(d, arm, F)

    # mounting yoke on top of the body — inboard of the rounded corners, and
    # deep enough into the body that the join reads as solid, not a floating tab
    hx0, hx1 = bx0 + (bx1 - bx0) * 0.38, bx0 + (bx1 - bx0) * 0.64
    d.rectangle([hx0 * SS, (by0 - h * 0.05) * SS, hx1 * SS, (by0 + h * 0.05) * SS], fill=F)

    lr = (by1 - by0) * 0.40
    lcx, lcy = bx1 - lr * 0.9, (by0 + by1) / 2
    _ellipse(d, (lcx - lr, lcy - lr, lcx + lr, lcy + lr), F)
    _ellipse(d, (lcx - lr * 0.55, lcy - lr * 0.55, lcx + lr * 0.55, lcy + lr * 0.55), pale)
    _ellipse(d, (lcx - lr * 0.22, lcy - lr * 0.22, lcx + lr * 0.22, lcy + lr * 0.22), F)

    _ellipse(d, (bx0 + w * 0.02, by0 + h * 0.02, bx0 + w * 0.05, by0 + h * 0.05), F)

    return _finish(img, w, h, seed)


def airliner(w: int = 900, h: int = 320, seed: int = 0, ink=INK,
             stairs: float = 0.0, view: str = "side") -> Image.Image:
    """A narrow-body tri-jet, the shape of the aircraft hijackings were flown in.

    `stairs` 0..1 lowers the rear airstair -- the detail that matters whenever
    the story is about someone leaving an aircraft in flight. `view` may be
    "side" or "plan".

    Two proportions are worth keeping if this is ever redrawn. The wingspan of
    a 727 is about 0.70 of its length, so a plan view needs a nearly square
    canvas; drawn on a wide one the span collapses and the aircraft reads as a
    missile. And the nose is blunt, not pointed -- a spike nose reads as a
    rocket at any size. The nose points **left** in both views, so an aircraft
    laid over a west-to-east route must be mirrored by the caller.
    """
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)

    if view == "plan":
        cx, cy = w * 0.5, h * 0.5 + float(rng.normal(0, h * 0.004))
        L = min(w * 0.94, h * 1.34)          # length, span stays ~0.70 * L
        x0, x1 = cx - L / 2, cx + L / 2
        r = L * 0.038                        # fuselage half-width
        tip = cy - L * 0.35                  # wing tip, one side

        def X(f):
            return x0 + L * f

        _blob(d, [(X(0.00), cy - r * 0.45), (X(0.05), cy - r),
                  (X(0.78), cy - r), (X(0.93), cy - r * 0.6),
                  (X(1.00), cy - r * 0.12), (X(1.00), cy + r * 0.12),
                  (X(0.93), cy + r * 0.6), (X(0.78), cy + r),
                  (X(0.05), cy + r), (X(0.00), cy + r * 0.45)], F)
        for sg in (-1, 1):
            def Y(v, sg=sg):
                return cy + sg * v
            # swept main wing: leading edge back-swept, trailing edge less so
            _blob(d, [(X(0.36), Y(r * 0.9)), (X(0.62), Y(abs(tip - cy))),
                      (X(0.70), Y(abs(tip - cy))), (X(0.56), Y(r * 0.9))], F)
            # tailplane, same sweep, roughly a third of the span
            _blob(d, [(X(0.80), Y(r * 0.9)), (X(0.90), Y(L * 0.13)),
                      (X(0.97), Y(L * 0.13)), (X(0.93), Y(r * 0.9))], F)
            # wing-root engine nacelle on the rear fuselage
            _blob(d, [(X(0.74), Y(r * 0.9)), (X(0.74), Y(r * 2.1)),
                      (X(0.88), Y(r * 2.0)), (X(0.90), Y(r * 0.9))], F)
        return _finish(img, w, h, seed)

    cy = h * 0.55 + float(rng.normal(0, h * 0.004))
    r = h * 0.105                            # fuselage half-height
    # fuselage: blunt nose left, straight body, tail cone lifting at the right
    _blob(d, [(w * 0.045, cy + r * 0.35), (w * 0.050, cy - r * 0.30),
              (w * 0.075, cy - r * 0.80), (w * 0.130, cy - r),
              (w * 0.740, cy - r), (w * 0.880, cy - r * 1.05),
              (w * 0.965, cy - r * 1.45), (w * 0.900, cy - r * 0.30),
              (w * 0.740, cy + r), (w * 0.130, cy + r)], F)
    # wing: root at mid-fuselage, sweeping back and down
    _blob(d, [(w * 0.40, cy + r * 0.6), (w * 0.60, cy + h * 0.29),
              (w * 0.71, cy + h * 0.29), (w * 0.56, cy + r * 0.6)], F)
    # far wing, higher and shorter, for depth
    _blob(d, [(w * 0.44, cy - r * 0.25), (w * 0.575, cy - h * 0.115),
              (w * 0.645, cy - h * 0.105), (w * 0.575, cy - r * 0.25)], F)
    # tail-mounted engine, clear of the fin so the two do not merge
    _blob(d, [(w * 0.700, cy - r * 1.05), (w * 0.715, cy - r * 1.95),
              (w * 0.820, cy - r * 2.00), (w * 0.835, cy - r * 1.15)], F)
    # fin, leading edge swept, carrying a T-tail
    _blob(d, [(w * 0.800, cy - r * 1.15), (w * 0.885, cy - h * 0.42),
              (w * 0.945, cy - h * 0.42), (w * 0.905, cy - r * 1.25)], F)
    d.line([w * 0.800 * SS, (cy - h * 0.435) * SS,
            w * 0.995 * SS, (cy - h * 0.405) * SS], fill=F,
           width=max(1, int(h * 0.042 * SS)))

    if stairs > 0.005:
        t = max(0.0, min(1.0, stairs))
        hx, hy = w * 0.760, cy + r * 0.90
        ang = math.radians(14 + 44 * t)
        L = h * 0.38
        ex, ey = hx + math.cos(ang) * L, hy + math.sin(ang) * L
        d.line([hx * SS, hy * SS, ex * SS, ey * SS], fill=F,
               width=max(1, int(h * 0.052 * SS)))
        for i in range(1, 5):
            f = i / 5.0
            sx, sy = hx + (ex - hx) * f, hy + (ey - hy) * f
            d.line([(sx - h * 0.028) * SS, (sy - h * 0.020) * SS,
                    (sx + h * 0.028) * SS, (sy + h * 0.020) * SS], fill=F,
                   width=max(1, int(h * 0.015 * SS)))
    return _finish(img, w, h, seed)


def parachute(w: int = 420, h: int = 520, seed: int = 0, ink=INK,
              canopy: float = 1.0, figure: bool = True) -> Image.Image:
    """An open round canopy with rigging lines and, optionally, a jumper.

    `canopy` 0..1 collapses the dome toward a streamed, unopened bundle, which
    is what a beat about a failed or undeployed jump needs.
    """
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    t = max(0.05, min(1.0, canopy))

    cx = w * 0.5 + float(rng.normal(0, w * 0.004))
    dome_w = w * (0.30 + 0.62 * t)
    dome_h = h * (0.14 + 0.28 * t)
    top = h * 0.06
    pts = []
    n = 15
    for i in range(n + 1):
        f = i / float(n)
        x = cx - dome_w / 2 + dome_w * f
        y = top + dome_h * (1.0 - math.sin(math.pi * f) ** 0.85)
        y += float(rng.normal(0, h * 0.004))
        pts.append((x, y))
    hem = h * 0.055 * t
    for i in range(n, -1, -1):
        f = i / float(n)
        x = cx - dome_w / 2 + dome_w * f
        scallop = hem * (0.45 + 0.55 * abs(math.sin(math.pi * f * 3.0)))
        pts.append((x, top + dome_h + scallop))
    _blob(d, pts, F)

    body_y = h * 0.86
    lw = max(1, int(w * 0.006 * SS))
    for f in (0.06, 0.24, 0.42, 0.58, 0.76, 0.94):
        x = cx - dome_w / 2 + dome_w * f
        d.line([x * SS, (top + dome_h + hem * 0.6) * SS,
                cx * SS, (body_y - h * 0.10) * SS], fill=F, width=lw)

    if figure:
        _ellipse(d, (cx - w * 0.045, body_y - h * 0.115,
                     cx + w * 0.045, body_y - h * 0.035), F)
        _blob(d, [(cx - w * 0.055, body_y - h * 0.045),
                  (cx + w * 0.055, body_y - h * 0.045),
                  (cx + w * 0.048, body_y + h * 0.045),
                  (cx - w * 0.048, body_y + h * 0.045)], F)
        for s in (-1, 1):
            d.line([cx * SS, (body_y - h * 0.02) * SS,
                    (cx + s * w * 0.13) * SS, (body_y - h * 0.075) * SS],
                   fill=F, width=max(1, int(w * 0.022 * SS)))
            d.line([(cx + s * w * 0.02) * SS, (body_y + h * 0.04) * SS,
                    (cx + s * w * 0.075) * SS, (body_y + h * 0.125) * SS],
                   fill=F, width=max(1, int(w * 0.026 * SS)))
    return _finish(img, w, h, seed)


def banknotes(w: int = 420, h: int = 260, seed: int = 0, ink=INK,
              bundles: int = 3, bands: bool = True) -> Image.Image:
    """Rubber-banded bundles of cash, stacked and slightly askew.

    Money in these stories is a physical object with a condition and a serial
    number, not an amount -- so it is drawn as something that could be found on
    a riverbank: banded, stacked, and not quite square.

    Two things keep this legible. The bands are a *dark strap over* the block,
    never a pale gap through it, because a light band splits the silhouette
    into loose rectangles. And the bundles are spaced with real paper between
    them; stacked flush they fuse into one slatted slab that reads as a crate.
    """
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    PAPER = (238, 233, 219, 255)
    n = max(1, int(bundles))
    bw = w * 0.62
    gap = h / (n + 0.55)
    bh = gap * 0.62

    for i in range(n):
        x = w * 0.19 + float(rng.normal(0, w * 0.016)) - w * 0.03 * i
        y = h * 0.90 - gap * i + float(rng.normal(0, h * 0.005))
        tilt = float(rng.normal(0, 0.05))
        c, s_ = math.cos(tilt), math.sin(tilt)

        def R(px, py, x=x, y=y, c=c, s_=s_):
            return (x + px * c - py * s_, y + px * s_ + py * c)

        _blob(d, [R(0, 0), R(bw, 0), R(bw, -bh), R(0, -bh)], F)
        # one short hairline so a bundle reads as a stack of notes, not a slab
        p0, p1 = R(bw * 0.06, -bh * 0.52), R(bw * 0.94, -bh * 0.52)
        d.line([p0[0] * SS, p0[1] * SS, p1[0] * SS, p1[1] * SS],
               fill=PAPER, width=max(1, int(h * 0.005 * SS)))
        if bands:
            for bx in (bw * 0.26, bw * 0.74):
                p0, p1 = R(bx, bh * 0.20), R(bx, -bh * 1.20)
                d.line([p0[0] * SS, p0[1] * SS, p1[0] * SS, p1[1] * SS],
                       fill=F, width=max(1, int(bh * 0.16 * SS)))
                q0, q1 = R(bx, bh * 0.10), R(bx, -bh * 1.10)
                d.line([q0[0] * SS, q0[1] * SS, q1[0] * SS, q1[1] * SS],
                       fill=PAPER, width=max(1, int(bh * 0.035 * SS)))
    return _finish(img, w, h, seed)


def necktie(w: int = 220, h: int = 560, seed: int = 0, ink=INK,
            clip: bool = True) -> Image.Image:
    """A tie, knot at the top, blade widening to a point.

    `clip` swaps the knot for the flat bar of a clip-on — a distinction that is
    occasionally the whole point of a beat.
    """
    img, d = _canvas(w, h)
    rng = paper._rng(seed)
    F = ink + (255,)
    cx = w * 0.5 + float(rng.normal(0, w * 0.01))

    if clip:
        _blob(d, [(cx - w * 0.30, h * 0.05), (cx + w * 0.30, h * 0.05),
                  (cx + w * 0.26, h * 0.15), (cx - w * 0.26, h * 0.15)], F)
        d.line([(cx - w * 0.30) * SS, h * 0.155 * SS,
                (cx + w * 0.30) * SS, h * 0.155 * SS], fill=F,
               width=max(1, int(w * 0.05 * SS)))
        neck = h * 0.16
    else:
        _blob(d, [(cx - w * 0.26, h * 0.04), (cx + w * 0.26, h * 0.04),
                  (cx + w * 0.20, h * 0.19), (cx - w * 0.20, h * 0.19)], F)
        neck = h * 0.19

    _blob(d, [(cx - w * 0.17, neck), (cx + w * 0.17, neck),
              (cx + w * 0.34, h * 0.80), (cx, h * 0.96),
              (cx - w * 0.34, h * 0.80)], F)
    return _finish(img, w, h, seed)
