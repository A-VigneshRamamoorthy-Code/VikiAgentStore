"""Collage elements: label chips, stamps, hand-drawn red marker, photo cut-outs.

These are the "voice" of the style. `paper.py` makes the materials; this module
makes the things that carry meaning.
"""

from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import paper
from paper import PALETTE, clamp8

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

_FONT_CACHE: dict = {}


def font(kind: str, size: int, weight: float = 900, width: float = 78):
    """`kind` is one of display | condensed | typewriter | mono."""
    key = (kind, size, weight, width)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    files = {
        "display": "Archivo[wdth,wght].ttf",
        "condensed": "Oswald[wght].ttf",
        "typewriter": "SpecialElite-Regular.ttf",
        "mono": "CourierPrime-Regular.ttf",
    }
    f = ImageFont.truetype(os.path.join(FONT_DIR, files[kind]), size)
    try:
        if kind == "display":
            f.set_variation_by_axes([weight, width])
        elif kind == "condensed":
            f.set_variation_by_axes([min(700, weight)])
    except Exception:
        pass
    _FONT_CACHE[key] = f
    return f


def measure(f, text: str):
    box = f.getbbox(text)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


def tracked_text(draw, xy, text, f, fill, tracking: float = 0.0):
    """Draw text with letter-spacing (Pillow has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking


def text_width(f, text: str, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    return sum(f.getlength(c) for c in text) + tracking * (len(text) - 1)


# ------------------------------------------------------------ ink on paper ----


def _ink_texture(img: Image.Image, seed: int = 0, bite: float = 0.5) -> Image.Image:
    """Erode ink slightly with noise so type looks printed, not vector-crisp."""
    a = np.asarray(img, dtype=np.float32)
    if a.shape[2] < 4:
        return img
    h, w = a.shape[:2]
    n = paper.value_noise(w, h, max(8, w // 14), seed + 5, octaves=3)
    fine = paper.value_noise(w, h, max(24, w // 4), seed + 9, octaves=2)
    m = 1.0 - bite * (0.55 * (1 - n) + 0.45 * (1 - fine))
    a[:, :, 3] *= np.clip(m, 0, 1)
    return Image.fromarray(clamp8(a), "RGBA")


# ------------------------------------------------------------- label chip ----


def label_chip(
    text: str,
    size: int = 54,
    kind: str = "display",
    weight: float = 900,
    width: float = 74,
    tracking: float = 2.0,
    fg=PALETTE["ink"],
    bg=(238, 232, 210),
    pad=(34, 20),
    seed: int = 0,
    torn: bool = False,
) -> Image.Image:
    """The cream keyword card — the workhorse caption of this style."""
    f = font(kind, size, weight, width)
    tw = text_width(f, text, tracking)
    box = f.getbbox(text)
    th = box[3] - box[1]
    w = int(tw + pad[0] * 2)
    h = int(th + pad[1] * 2)

    if torn:
        card = paper.torn_card(w, h, seed=seed + 3, color=bg, depth=0.05, grain=6)
    else:
        card = paper.parchment(w, h, seed=seed + 3, light=bg,
                               deep=tuple(int(c * 0.9) for c in bg), blotches=2).convert("RGBA")

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tracked_text(d, (pad[0], pad[1] - box[1]), text, f, fg + (255,), tracking)
    layer = _ink_texture(layer, seed, bite=0.45)
    return Image.alpha_composite(card, layer)


def stamp(
    text: str,
    size: int = 44,
    fg=(228, 220, 196),
    bg=(52, 50, 40),
    tracking: float = 3.0,
    pad=(30, 16),
    seed: int = 0,
) -> Image.Image:
    """A dark inked stamp block (the 'KUALA LUMPUR DEPARTED' device)."""
    f = font("condensed", size, 700)
    tw = text_width(f, text, tracking)
    box = f.getbbox(text)
    th = box[3] - box[1]
    w, h = int(tw + pad[0] * 2), int(th + pad[1] * 2)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(
        [(2, 3), (w - 3, 0), (w - 1, h - 2), (1, h - 4)],
        fill=bg + (246,),
    )
    tracked_text(d, (pad[0], pad[1] - box[1]), text, f, fg + (255,), tracking)
    return _ink_texture(img, seed + 21, bite=0.34)


def typed_line(text: str, size: int = 30, fg=PALETTE["ink_soft"], seed: int = 0, tracking: float = 1.0):
    """A small typewritten annotation, for dates / captions / file numbers."""
    f = font("typewriter", size)
    w = int(text_width(f, text, tracking) + 8)
    box = f.getbbox(text)
    h = int(box[3] - box[1] + 12)
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tracked_text(d, (4, 6 - box[1]), text, f, fg + (255,), tracking)
    return _ink_texture(img, seed + 33, bite=0.55)


# --------------------------------------------------------------- red marker ----


def catmull_rom(pts, samples_per_seg: int = 24):
    """Smooth a control polygon into a curve (centripetal Catmull-Rom)."""
    p = np.asarray(pts, dtype=np.float64)
    if len(p) < 3:
        return p
    ext = np.vstack([p[0] + (p[0] - p[1]), p, p[-1] + (p[-1] - p[-2])])
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for j in range(samples_per_seg):
            t = j / samples_per_seg
            t2, t3 = t * t, t * t * t
            out.append(
                0.5 * ((2 * p1) + (-p0 + p2) * t
                       + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            )
    out.append(ext[-2])
    return np.asarray(out)


def _rough_polyline(pts, wobble: float, seed: int, samples: int = 260, smooth: bool = True):
    """Resample a path and add correlated jitter so it looks hand-drawn."""
    rng = np.random.default_rng(seed)
    pts = np.asarray(pts, dtype=np.float64)
    if len(pts) < 2:
        return pts
    if smooth and len(pts) >= 3:
        pts = catmull_rom(pts)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return pts
    u = np.linspace(0, total, samples)
    x = np.interp(u, cum, pts[:, 0])
    y = np.interp(u, cum, pts[:, 1])

    # smooth noise for the wobble
    def smooth_noise(n, k):
        base = rng.normal(0, 1, k)
        idx = np.linspace(0, k - 1, n)
        return np.interp(idx, np.arange(k), base)

    nx = smooth_noise(samples, 9) * wobble
    ny = smooth_noise(samples, 9) * wobble
    return np.stack([x + nx, y + ny], axis=1)


def marker_stroke(
    size,
    pts,
    color=PALETTE["accent"],
    width: float = 15,
    progress: float = 1.0,
    wobble: float = 3.0,
    seed: int = 0,
    overshoot: float = 0.0,
    alpha: int = 255,
    smooth: bool = True,
) -> Image.Image:
    """A hand-drawn marker stroke along `pts`, revealed to `progress` (0..1).

    Rendered at 2x and downsampled: cheap anti-aliasing plus a slightly soft
    edge, which is what a felt-tip on rough paper actually looks like.
    """
    W, H = size
    ss = 2
    img = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    if progress <= 0:
        return img.resize((W, H), Image.LANCZOS)

    path = _rough_polyline(pts, wobble, seed, smooth=smooth)
    if overshoot > 0 and len(path) > 2:
        d = path[-1] - path[-2]
        n = np.linalg.norm(d)
        if n > 0:
            path = np.vstack([path, path[-1] + d / n * overshoot])

    n_keep = max(2, int(len(path) * min(1.0, progress)))
    path = path[:n_keep] * ss

    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed + 77)
    base_w = width * ss
    # taper: thin at the very start, full body through the middle
    for i in range(len(path) - 1):
        t = i / max(1, len(path) - 2)
        taper = min(1.0, t / 0.06) if t < 0.06 else 1.0
        wv = base_w * taper * (0.86 + 0.28 * abs(math.sin(t * 9.1 + seed)))
        a = int(alpha * (0.80 + 0.20 * rng.random()))
        d.line([tuple(path[i]), tuple(path[i + 1])], fill=color + (a,), width=max(1, int(wv)))
        r = wv / 2
        d.ellipse([path[i][0] - r, path[i][1] - r, path[i][0] + r, path[i][1] + r], fill=color + (a,))

    img = img.resize((W, H), Image.LANCZOS)
    # dry-media break-up
    a = np.asarray(img, dtype=np.float32)
    tex = paper.value_noise(W, H, max(10, W // 22), seed + 3, octaves=3)
    a[:, :, 3] *= np.clip(0.72 + 0.45 * tex, 0, 1)
    return Image.fromarray(clamp8(a), "RGBA")


def pad_box(box, px: int = 26, py: int = 18):
    """Grow a box so a marker annotation clears the type inside it."""
    x0, y0, x1, y1 = box
    return (x0 - px, y0 - py, x1 + px, y1 + py)


def box_of(img: Image.Image, pos, pad_x: int = 26, pad_y: int = 16):
    """Marker box around an element placed at `pos`, with breathing room."""
    return pad_box((pos[0], pos[1], pos[0] + img.size[0], pos[1] + img.size[1]), pad_x, pad_y)


def marker_rect(size, box, progress=1.0, width=14, seed=0, color=PALETTE["accent"], wobble=2.6):
    """Hand-drawn rectangle that draws on clockwise from the top-left."""
    x0, y0, x1, y1 = box
    over = (x1 - x0) * 0.03
    pts = [
        (x0 - over * 0.5, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 - over * 0.2),
        (x0 + over, y0 - over * 0.25),
    ]
    return marker_stroke(size, pts, color, width, progress, wobble, seed, smooth=False)


def marker_ellipse(size, box, progress=1.0, width=14, seed=0, color=PALETTE["accent"], wobble=3.0):
    """Hand-drawn circle-ish ring, slightly more than one full turn."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    pts = []
    start = -2.2
    for i in range(97):
        a = start + (i / 96) * (2 * math.pi * 1.08)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return marker_stroke(size, pts, color, width, progress, wobble, seed, smooth=False)


def marker_underline(size, x0, x1, y, progress=1.0, width=13, seed=0, color=PALETTE["accent"]):
    return marker_stroke(size, [(x0, y), ((x0 + x1) / 2, y + 3), (x1, y - 2)],
                         color, width, progress, 2.2, seed, smooth=False)


def arrow_head(size, tip, angle, length=44, color=PALETTE["accent"], width=13, seed=0, progress=1.0):
    """Two short strokes forming an arrow head; use with a marker path."""
    if progress <= 0:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    a1 = angle + math.radians(150)
    a2 = angle - math.radians(150)
    img = marker_stroke(size, [tip, (tip[0] + math.cos(a1) * length, tip[1] + math.sin(a1) * length)],
                        color, width, 1.0, 1.6, seed)
    img2 = marker_stroke(size, [tip, (tip[0] + math.cos(a2) * length, tip[1] + math.sin(a2) * length)],
                         color, width, 1.0, 1.6, seed + 1)
    return Image.alpha_composite(img, img2)


def path_angle(pts, u=1.0):
    p = np.asarray(pts, dtype=np.float64)
    i = max(1, min(len(p) - 1, int(u * (len(p) - 1))))
    d = p[i] - p[i - 1]
    return math.atan2(d[1], d[0])


# -------------------------------------------------------------- cut-outs ----


def sticker(
    img: Image.Image,
    border: int = 10,
    border_color=(246, 242, 230),
    shadow_blur: int = 18,
    shadow_dy: int = 12,
    shadow_alpha: int = 135,
    shadow: bool = True,
    seed: int = 0,
) -> Image.Image:
    """Give any RGBA art a white paper border + contact shadow (scrapbook cut-out).

    Pass ``shadow=False`` when the caller applies its own elevation-driven
    shadow — otherwise the two stack and the scrap reads as floating twice.
    """
    a = img.getchannel("A")
    grown = a.filter(ImageFilter.MaxFilter(3))
    for _ in range(max(0, border // 2)):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    grown = grown.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.GaussianBlur(0.6))

    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    edge = Image.new("RGBA", img.size, border_color + (255,))
    edge.putalpha(grown)
    # the cut edge of the print stock catches the key light — the *paper*
    # margin only, never the artwork sitting on top of it, otherwise thin
    # line art (marker strokes, routes) is bleached to cream.
    edge = paper.edge_light(edge, grown, px=max(1.5, border * 0.35), alpha=58)
    out = Image.alpha_composite(out, edge)
    out = Image.alpha_composite(out, img)
    if not shadow:
        return out
    return paper.drop_shadow(out, blur=shadow_blur, dy=shadow_dy, alpha=shadow_alpha)


def archival_photo(img: Image.Image, seed: int = 0, contrast: float = 1.35, dot: int = 5) -> Image.Image:
    """Push any image to high-contrast, grainy, halftoned black & white."""
    g = img.convert("L")
    a = np.asarray(g, dtype=np.float32) / 255.0
    a = np.clip((a - 0.5) * contrast + 0.48, 0, 1)
    # warm duotone rather than neutral grey
    lo = np.array([38, 36, 30], dtype=np.float32)
    hi = np.array([226, 220, 200], dtype=np.float32)
    rgb = lo[None, None, :] + (hi - lo)[None, None, :] * a[:, :, None]
    out = Image.fromarray(clamp8(rgb)).convert("RGBA")
    out = paper.halftone(out, dot=dot, strength=0.22)
    return paper.add_grain(out, amount=9, seed=seed)
