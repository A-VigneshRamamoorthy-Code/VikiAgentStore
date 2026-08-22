"""Procedural paper, texture and material generation for the archival collage style.

Everything here is deterministic given a seed, so a storyboard renders identically
on every machine. No external image assets are required.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


# ---------------------------------------------------------------- palette ----

PALETTE = {
    "paper_light": (222, 211, 180),
    "paper_mid": (206, 191, 154),
    "paper_deep": (176, 158, 122),
    "paper_shadow": (140, 124, 95),
    "ink": (58, 58, 48),
    "ink_soft": (96, 92, 76),
    "accent": (200, 62, 42),
    "accent_deep": (168, 46, 30),
    "card": (236, 228, 203),
    "tape": (214, 196, 150),
    "night": (44, 46, 52),
}


def clamp8(a: np.ndarray) -> np.ndarray:
    return np.clip(a, 0, 255).astype(np.uint8)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


# ------------------------------------------------------------------ noise ----


def value_noise(w: int, h: int, cells: int, seed: int, octaves: int = 4) -> np.ndarray:
    """Fractal value noise in 0..1, produced by upsampling random lattices."""
    rng = _rng(seed)
    acc = np.zeros((h, w), dtype=np.float32)
    amp, total, c = 1.0, 0.0, cells
    for _ in range(octaves):
        gh, gw = max(2, int(c)), max(2, int(c * w / h))
        grid = rng.random((gh, gw)).astype(np.float32)
        layer = np.asarray(
            Image.fromarray((grid * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
            dtype=np.float32,
        ) / 255.0
        acc += layer * amp
        total += amp
        amp *= 0.5
        c *= 2.1
    acc /= total
    acc -= acc.min()
    return acc / (acc.max() + 1e-6)


def fiber_noise(w: int, h: int, seed: int) -> np.ndarray:
    """Directional streaks that read as paper fibre."""
    rng = _rng(seed)
    base = rng.random((h, w)).astype(np.float32)
    img = Image.fromarray((base * 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    a = np.asarray(img, dtype=np.float32) / 255.0
    # smear horizontally so fibres run across the sheet
    k = 9
    ker = np.ones(k, dtype=np.float32) / k
    a = np.apply_along_axis(lambda r: np.convolve(r, ker, mode="same"), 1, a)
    a -= a.min()
    return a / (a.max() + 1e-6)


# ------------------------------------------------------------------ paper ----


def parchment(
    w: int,
    h: int,
    seed: int = 7,
    light=PALETTE["paper_light"],
    deep=PALETTE["paper_deep"],
    blotches: int = 9,
) -> Image.Image:
    """An aged sheet: mottled tone, fibre, blotches and edge darkening."""
    rng = _rng(seed)
    n = value_noise(w, h, 3, seed, octaves=5)
    fine = value_noise(w, h, 26, seed + 101, octaves=3)
    fib = fiber_noise(w, h, seed + 202)

    t = (0.62 * n + 0.24 * fine + 0.14 * fib).astype(np.float32)
    t = (t - t.min()) / (t.max() - t.min() + 1e-6)
    t = t ** 0.85

    lo = np.array(deep, dtype=np.float32)
    hi = np.array(light, dtype=np.float32)
    rgb = lo[None, None, :] + (hi - lo)[None, None, :] * t[:, :, None]

    # irregular tea-stain blotches
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for _ in range(blotches):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.10, 0.34) * max(w, h)
        d = np.sqrt(((xx - cx) / r) ** 2 + ((yy - cy) / (r * rng.uniform(0.6, 1.4))) ** 2)
        m = np.clip(1.0 - d, 0, 1) ** 2
        rgb *= (1.0 - 0.11 * rng.uniform(0.4, 1.0) * m)[:, :, None]

    img = Image.fromarray(clamp8(rgb))
    return add_grain(img, amount=6, seed=seed + 303)


def coffee_ring(size: int, seed: int = 3, alpha: int = 42) -> Image.Image:
    """A wobbly stain ring — the signature 'desk' detail of the reference."""
    rng = _rng(seed)
    s = size * 2
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = s / 2
    base = s * 0.36
    pts_out, pts_in = [], []
    for i in range(241):
        a = i / 240 * 2 * math.pi
        wob = (
            1
            + 0.040 * math.sin(a * 3 + seed)
            + 0.022 * math.sin(a * 7 + seed * 2)
            + 0.012 * math.sin(a * 13 + seed * 3)
        )
        ro = base * wob
        ri = ro * rng.uniform(0.955, 0.972)
        pts_out.append((cx + ro * math.cos(a), cy + ro * math.sin(a)))
        pts_in.append((cx + ri * math.cos(a), cy + ri * math.sin(a)))
    d.polygon(pts_out, fill=(104, 68, 34, alpha))
    d.polygon(pts_in, fill=(0, 0, 0, 0))
    # very faint wash inside the ring
    inner = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(inner).polygon(pts_in, fill=(112, 78, 42, max(6, alpha // 6)))
    img = Image.alpha_composite(inner, img)
    img = img.filter(ImageFilter.GaussianBlur(s * 0.0035))
    return img.resize((size, size), Image.LANCZOS)


def ghost_print(w: int, h: int, seed: int = 21, alpha: int = 30, scale: float = 1.0) -> Image.Image:
    """Faint blocks of unreadable printed text — the archival 'document' underlay.

    Drawn as ticks rather than real glyphs: at this opacity it reads as dense
    body copy, costs nothing to render, and never says anything unintended.
    """
    rng = _rng(seed)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = PALETTE["ink"]
    y = rng.uniform(0, 40 * scale)
    while y < h:
        col_x = rng.uniform(0, w * 0.10)
        block_w = rng.uniform(0.30, 0.62) * w
        lh = rng.uniform(9, 13) * scale
        lines = rng.integers(4, 14)
        for _ in range(int(lines)):
            if y > h:
                break
            x = col_x
            end = col_x + block_w * rng.uniform(0.82, 1.0)
            while x < end:
                wl = rng.uniform(9, 46) * scale
                th = max(1, int(rng.uniform(1.6, 3.0) * scale))
                d.rectangle([x, y, min(x + wl, end), y + th], fill=ink + (alpha,))
                x += wl + rng.uniform(5, 11) * scale
            y += lh
        y += rng.uniform(14, 46) * scale
    return img.filter(ImageFilter.GaussianBlur(0.4 * scale))


def grid_fragment(w: int, h: int, seed: int = 31, alpha: int = 34, pitch: int = 34) -> Image.Image:
    """Graph-paper ruling, used behind technical/diagram elements."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (72, 92, 104, alpha)
    for x in range(0, w, pitch):
        d.line([(x, 0), (x, h)], fill=c, width=1)
    for y in range(0, h, pitch):
        d.line([(0, y), (w, y)], fill=c, width=1)
    for x in range(0, w, pitch * 5):
        d.line([(x, 0), (x, h)], fill=(72, 92, 104, min(255, alpha * 2)), width=2)
    for y in range(0, h, pitch * 5):
        d.line([(0, y), (w, y)], fill=(72, 92, 104, min(255, alpha * 2)), width=2)
    return img


def map_fragment(w: int, h: int, seed: int = 41, alpha: int = 34) -> Image.Image:
    """Wandering contour/coastline lines that read as an old chart underlay."""
    rng = _rng(seed)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (96, 84, 58, alpha)
    for _ in range(rng.integers(5, 9)):
        x = rng.uniform(-0.1, 0.5) * w
        y = rng.uniform(0, h)
        pts, a = [], rng.uniform(-0.7, 0.7)
        for _ in range(90):
            a += rng.normal(0, 0.22)
            x += math.cos(a) * w * 0.016
            y += math.sin(a) * w * 0.016
            pts.append((x, y))
        d.line(pts, fill=ink, width=max(1, int(w * 0.0012)), joint="curve")
    return img.filter(ImageFilter.GaussianBlur(0.5))


# ------------------------------------------------------------- torn edges ----


def torn_mask(w: int, h: int, seed: int = 5, depth: float = 0.035, sides=(1, 1, 1, 1)) -> Image.Image:
    """L-mode mask with irregular deckled edges. `sides` = (top,right,bottom,left).

    The contour is a chunky fractal: a few big lobes carrying finer teeth, which
    reads as a hand-torn edge rather than a wavy line.
    """
    rng = _rng(seed)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    dx, dy = depth * w, depth * h

    # Fixed corners, shared by adjoining edges, so the outline never notches.
    x0 = dx * 0.5 if sides[3] else 0.0
    x1 = w - (dx * 0.5 if sides[1] else 0.0)
    y0 = dy * 0.5 if sides[0] else 0.0
    y1 = h - (dy * 0.5 if sides[2] else 0.0)

    def wobble(n, amp):
        """Deviation series that tapers to zero at both ends."""
        if amp <= 0:
            return [0.0] * (n + 1)
        lat = [rng.random(k) for k in (4, 9, 19, 41)]
        out = []
        for i in range(n + 1):
            u = i / n
            v, a, tot = 0.0, 1.0, 0.0
            for L in lat:
                x = u * (len(L) - 1)
                j = min(int(x), len(L) - 2)
                f = x - j
                f = f * f * (3 - 2 * f)
                v += (L[j] * (1 - f) + L[j + 1] * f) * a
                tot += a
                a *= 0.52
            taper = math.sin(math.pi * u) ** 0.55
            out.append((v / tot - 0.5) * 2 * amp * taper)
        return out

    n = 96
    wt = wobble(n, dy if sides[0] else 0)
    wr = wobble(n, dx if sides[1] else 0)
    wb = wobble(n, dy if sides[2] else 0)
    wl = wobble(n, dx if sides[3] else 0)

    top = [(x0 + (x1 - x0) * i / n, y0 + wt[i]) for i in range(n + 1)]
    rig = [(x1 + wr[i], y0 + (y1 - y0) * i / n) for i in range(n + 1)]
    bot = [(x1 - (x1 - x0) * i / n, y1 + wb[i]) for i in range(n + 1)]
    lef = [(x0 + wl[i], y1 - (y1 - y0) * i / n) for i in range(n + 1)]

    d.polygon(top + rig + bot + lef, fill=255)
    return m.filter(ImageFilter.GaussianBlur(0.8))


def torn_card(
    w: int,
    h: int,
    seed: int = 5,
    color=PALETTE["card"],
    depth: float = 0.035,
    sides=(1, 1, 1, 1),
    grain: int = 7,
    core: float | None = None,
    fold: float | None = None,
    fold_strength: float = 1.0,
) -> Image.Image:
    """A torn scrap of paper with an exposed fibrous core along the tear.

    `core` is the thickness of the exposed pulp in pixels; it defaults to a
    proportion of the scrap so small chips and big sheets both read correctly.
    """
    sheet = parchment(
        w, h, seed=seed, light=color,
        deep=tuple(int(c * 0.86) for c in color), blotches=3,
    )
    mask = torn_mask(w, h, seed, depth, sides)
    card = sheet.convert("RGBA")
    card.putalpha(mask)

    if fold is not None:
        card = fold_crease(card, pos=fold, vertical=True, seed=seed + 3,
                           strength=fold_strength)
        card.putalpha(mask)

    if core is None:
        core = max(2.0, min(w, h) * 0.012)
    # A torn edge exposes raw pulp, which is pale *whatever* the surface is
    # printed — that contrast is the whole cue on dark stock.
    pulp = tuple(int(0.82 * p + 0.18 * c) for p, c in zip((252, 248, 236), color))
    card = torn_core(card, mask, core=core, seed=seed, color=pulp)
    card = edge_light(card, mask, px=max(1.5, core * 0.5))
    return add_grain(card, amount=grain, seed=seed + 11)


# ----------------------------------------------------------------- extras ----


def tape_strip(w: int, h: int, seed: int = 2, color=PALETTE["tape"]) -> Image.Image:
    """Translucent masking tape with ragged torn ends and a soft sheen."""
    rng = _rng(seed)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    jag = max(3, int(w * 0.02))
    left = [(jag * rng.uniform(0.1, 1.0), y) for y in np.linspace(0, h, 9)]
    right = [(w - jag * rng.uniform(0.1, 1.0), y) for y in np.linspace(0, h, 9)]
    d.polygon(left + list(reversed(right)), fill=color + (176,))

    tex = value_noise(w, h, 5, seed + 3, octaves=3)
    a = np.asarray(img, dtype=np.float32)
    a[:, :, :3] *= (0.9 + 0.2 * tex)[:, :, None]
    # lengthwise sheen
    yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    a[:, :, :3] *= (1.0 + 0.10 * (1 - yy ** 2))[:, :, None]
    a[:, :, 3] *= 0.86 + 0.14 * tex
    return Image.fromarray(clamp8(a))


def push_pin(size: int, color=(196, 66, 48), seed: int = 1) -> Image.Image:
    """A domed pin head with specular highlight and contact shadow."""
    s = size * 3
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    r = s * 0.28
    d.ellipse([c - r * 0.95, c - r * 0.55, c + r * 1.35, c + r * 1.5], fill=(40, 34, 24, 90))
    for i in range(int(r), 0, -1):
        t = i / r
        col = tuple(int(ch * (0.55 + 0.55 * (1 - t))) for ch in color)
        d.ellipse([c - i, c - i, c + i, c + i], fill=col + (255,))
    hr = r * 0.30
    d.ellipse(
        [c - r * 0.45 - hr, c - r * 0.45 - hr, c - r * 0.45 + hr, c - r * 0.45 + hr],
        fill=(255, 248, 235, 190),
    )
    img = img.filter(ImageFilter.GaussianBlur(s * 0.004))
    return img.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------ post effects ----


def add_grain(img: Image.Image, amount: int = 8, seed: int = 0) -> Image.Image:
    if amount <= 0:
        return img
    rng = _rng(seed)
    a = np.asarray(img, dtype=np.float32)
    noise = rng.normal(0, amount, a.shape[:2]).astype(np.float32)[:, :, None]
    if a.shape[2] == 4:
        a[:, :, :3] = np.clip(a[:, :, :3] + noise, 0, 255)
    else:
        a = np.clip(a + noise, 0, 255)
    return Image.fromarray(a.astype(np.uint8), img.mode)


def halftone(img: Image.Image, dot: int = 4, strength: float = 0.35) -> Image.Image:
    """Newsprint dot screen — sells the 'scanned archive' feel on photos."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grid = (np.sin(xx * math.pi / dot) * np.sin(yy * math.pi / dot)) ** 2
    a = np.asarray(img, dtype=np.float32)
    f = 1.0 - strength + strength * grid
    a[:, :, :3] *= f[:, :, None]
    return Image.fromarray(clamp8(a), img.mode)


def vignette(img: Image.Image, strength: float = 0.42, power: float = 1.6) -> Image.Image:
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / w - 0.5) * 2
    ny = (yy / h - 0.5) * 2
    r = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
    m = 1.0 - strength * (r ** power)
    a = np.asarray(img, dtype=np.float32)
    a[:, :, :3] *= m[:, :, None]
    return Image.fromarray(clamp8(a), img.mode)


def drop_shadow(img: Image.Image, blur: int = 16, dy: int = 10, dx: int = 4, alpha: int = 130) -> Image.Image:
    """Return a new RGBA image with a soft contact shadow behind `img`."""
    pad = blur * 3
    w, h = img.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = img.getchannel("A").point(lambda v: int(v * alpha / 255))
    tint = Image.new("RGBA", (w, h), (34, 28, 20, 255))
    tint.putalpha(a)
    sh.paste(tint, (pad + dx, pad + dy), tint)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out = Image.alpha_composite(out, sh)
    out.paste(img, (pad, pad), img)
    return out


def paper_curl(img: Image.Image, strength: float = 0.30) -> Image.Image:
    """Darken two opposite corners so a flat scrap reads as slightly lifted."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = ((xx / w) * 0.5 + (yy / h) * 0.5)
    m = 1.0 - strength * (g - 0.5).clip(0, None) * 2
    a = np.asarray(img, dtype=np.float32)
    a[:, :, :3] *= m[:, :, None]
    return Image.fromarray(clamp8(a), img.mode)


# ------------------------------------------------------- depth & layering ----
#
# The reference style is not flat collage: every scrap is a *physical* piece of
# paper with measurable thickness, sitting at a measurable height above the
# board. Three things sell that, and all three have to be present:
#
#   1. a torn edge that exposes the pale fibrous core of the stock,
#   2. a cast shadow whose offset and softness track the scrap's elevation,
#   3. a lit edge on the side facing the (constant, upper-left) key light.


LIGHT_ANGLE = 62.0  # degrees; shadows fall down-and-right from an upper-left key


def _erode(mask: Image.Image, px: int) -> Image.Image:
    """Shrink an L mask by roughly `px` pixels."""
    out = mask
    for _ in range(max(0, int(px))):
        out = out.filter(ImageFilter.MinFilter(3))
    return out


def _dilate(mask: Image.Image, px: int) -> Image.Image:
    out = mask
    for _ in range(max(0, int(px))):
        out = out.filter(ImageFilter.MaxFilter(3))
    return out


def torn_core(
    card: Image.Image,
    mask: Image.Image,
    core: float = 5.0,
    seed: int = 0,
    color=(252, 249, 238),
    strength: float = 1.0,
) -> Image.Image:
    """Expose the pale fibrous core along a torn edge.

    Real paper is a sandwich: coloured/printed surface over a lighter pulp core.
    Tearing it reveals that core as a ragged bright lip, which is *the* cue that
    separates a torn scrap from an alpha-masked rectangle. The lip is deliberately
    uneven — modulated by noise and thicker in places — because a constant-width
    outline reads as a stroke effect instead of a tear.
    """
    w, h = card.size
    px = max(1, int(round(core)))
    inner = _erode(mask, px)
    lip = ImageChops.subtract(mask, inner)

    # break the lip up so the fibres bunch and thin like real pulp
    n = value_noise(w, h, max(6, int(min(w, h) / 26)), seed + 991, octaves=4)
    n = (0.30 + 1.15 * n) * strength
    arr = np.asarray(lip, dtype=np.float32) * np.clip(n, 0, 1.6)
    lip = Image.fromarray(clamp8(arr), "L")
    lip = lip.filter(ImageFilter.GaussianBlur(0.6))
    lip = ImageChops.multiply(lip, mask)

    fib = Image.new("RGBA", (w, h), tuple(color) + (255,))
    fib.putalpha(lip)
    return Image.alpha_composite(card, fib)


def edge_light(
    card: Image.Image,
    mask: Image.Image,
    px: float = 2.5,
    angle: float = LIGHT_ANGLE,
    alpha: int = 70,
) -> Image.Image:
    """Catch a highlight on the edge facing the key light."""
    w, h = card.size
    p = max(1, int(round(px)))
    rad = math.radians(angle)
    dx, dy = -int(round(math.cos(rad) * p * 1.6)), -int(round(math.sin(rad) * p * 1.6))

    inner = _erode(mask, p)
    rim = ImageChops.subtract(mask, inner)
    shifted = Image.new("L", (w, h), 0)
    shifted.paste(rim, (dx, dy))
    rim = ImageChops.multiply(shifted, mask).filter(ImageFilter.GaussianBlur(p * 0.7))

    hi = Image.new("RGBA", (w, h), (255, 253, 245, 255))
    hi.putalpha(rim.point(lambda v: int(v * alpha / 255)))
    return Image.alpha_composite(card, hi)


def elevated_shadow(
    img: Image.Image,
    elevation: float = 0.25,
    pad: int | None = None,
    base_blur: float = 7.0,
    base_dist: float = 7.0,
    angle: float = LIGHT_ANGLE,
    alpha: int = 165,
    contact: bool = True,
) -> Image.Image:
    """Cast a shadow whose geometry encodes how high the scrap floats.

    `elevation` 0 → resting on the board (tight, dark, barely offset);
    1 → floating well above it (far, soft, faint). Animating this while an
    element flies in is what makes it read as paper falling onto a board rather
    than a sprite sliding across one.

    `pad` is fixed by the caller so the canvas size — and therefore the element's
    centre — stays put across the whole animation.
    """
    e = max(0.0, float(elevation))
    blur = base_blur * (1.0 + 2.8 * e)
    dist = base_dist * (1.0 + 5.5 * e)
    a = alpha * (1.0 - 0.42 * min(1.0, e))

    rad = math.radians(angle)
    dx = int(round(math.cos(rad) * dist))
    dy = int(round(math.sin(rad) * dist))

    if pad is None:
        pad = int(base_blur * (1 + 2.8) * 3 + base_dist * (1 + 5.5)) // 2
    w, h = img.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    src_a = img.getchannel("A")

    def _cast(off_x, off_y, blur_px, amount):
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        tint = Image.new("RGBA", (w, h), (30, 25, 18, 255))
        tint.putalpha(src_a.point(lambda v: int(v * amount / 255)))
        layer.paste(tint, (pad + int(off_x), pad + int(off_y)), tint)
        return layer.filter(ImageFilter.GaussianBlur(blur_px))

    # a tight ambient-occlusion core under the scrap plus the soft cast shadow
    if contact:
        out = Image.alpha_composite(
            out, _cast(dx * 0.25, dy * 0.25, max(1.0, blur * 0.30), a * 0.55)
        )
    out = Image.alpha_composite(out, _cast(dx, dy, blur, a))
    out.paste(img, (pad, pad), img)
    return out


def fold_crease(
    img: Image.Image,
    pos: float = 0.5,
    vertical: bool = True,
    seed: int = 0,
    strength: float = 1.0,
) -> Image.Image:
    """Fold the sheet: a darker valley on one side of the crease, a lit ridge on
    the other, with the line itself slightly wandering."""
    w, h = img.size
    if w < 4 or h < 4:
        return img
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rng = _rng(seed)

    if vertical:
        centre = pos * w + np.interp(
            yy[:, 0], np.linspace(0, h, 7), rng.normal(0, w * 0.006, 7)
        )[:, None]
        d = (xx - centre) / max(2.0, w * 0.020)
    else:
        centre = pos * h + np.interp(
            xx[0], np.linspace(0, w, 7), rng.normal(0, h * 0.006, 7)
        )[None, :]
        d = (yy - centre) / max(2.0, h * 0.020)

    # odd function: dark on one side of the crease, light on the other
    shade = np.tanh(d) * np.exp(-(d ** 2) * 0.85) * 0.20 * strength

    arr = np.asarray(img.convert("RGBA"), dtype=np.float32)
    arr[..., :3] *= (1.0 + shade)[..., None]
    return Image.fromarray(clamp8(arr), "RGBA")


def paper_stack(
    layers: list[Image.Image],
    offsets: list[tuple[int, int]] | None = None,
    gap_blur: float = 5.0,
    gap_alpha: int = 120,
) -> Image.Image:
    """Composite several sheets into one physical stack.

    Each sheet casts a short shadow onto the one beneath it, which is what makes
    a pile of paper read as a pile rather than as overlapping decals.
    """
    if not layers:
        raise ValueError("paper_stack needs at least one layer")
    if offsets is None:
        offsets = [(0, 0)] * len(layers)

    xs = [o[0] for o in offsets]
    ys = [o[1] for o in offsets]
    ws = [l.size[0] + o for l, o in zip(layers, xs)]
    hs = [l.size[1] + o for l, o in zip(layers, ys)]
    pad = int(gap_blur * 3 + 6)
    W = max(ws) - min(xs + [0]) + pad * 2
    H = max(hs) - min(ys + [0]) + pad * 2
    ox, oy = pad - min(xs + [0]), pad - min(ys + [0])

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for layer, (lx, ly) in zip(layers, offsets):
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tint = Image.new("RGBA", layer.size, (28, 24, 18, 255))
        tint.putalpha(layer.getchannel("A").point(lambda v: int(v * gap_alpha / 255)))
        rad = math.radians(LIGHT_ANGLE)
        sh.paste(
            tint,
            (ox + lx + int(math.cos(rad) * gap_blur), oy + ly + int(math.sin(rad) * gap_blur)),
            tint,
        )
        out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(gap_blur)))
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tmp.paste(layer, (ox + lx, oy + ly), layer)
        out = Image.alpha_composite(out, tmp)
    return out
