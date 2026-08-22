#!/usr/bin/env python3
"""Render a channel's icon and banner from the project's brand tokens.

A new channel with a default avatar and an empty grey banner reads as
abandoned, and that judgement is made before a single video is played. This
renders both from the same `publish.json` brand block the thumbnails and
stings use, so the channel and its videos are visibly one thing.

    python3 brand.py <project>            # icon + banner
    python3 brand.py <project> --icon     # just one of them

Outputs `out/channel_icon.png` (800x800) and `out/channel_banner.png`
(2560x1440). Upload them with `upload.py branding <project>`.

The two formats have very different constraints and are NOT the same artwork
scaled:

* The **icon** is masked to a circle and is routinely seen at 48px or less, so
  it must survive as one or two high-contrast shapes. Anything finer than a
  letterform disappears.
* The **banner** is cropped differently on every device. Only a centred
  1235x338 region is guaranteed to be visible; TV shows the whole 2560x1440.
  So everything that must be read lives in the safe area, and everything
  outside it is texture that is expected to be cropped away.
"""
import argparse
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import _shared  # noqa: F401  (locates config.py)
from config import Publish, say

ICON = 800
BANNER_W, BANNER_H = 2560, 1440
# The only region of a banner visible on every device, centred.
SAFE_W, SAFE_H = 1235, 338

# The paper style ships the fonts the films are lettered in. Reusing them is
# what makes the channel art look like the videos rather than like a generic
# template. Falling back keeps this skill usable on its own.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REGISTRY = os.path.normpath(
    os.path.join(_HERE, "..", "..", "production-designer", "scripts"))
sys.path.insert(0, _REGISTRY)
_MISSING = ("the paper style is required for channel branding. Install the "
            "style-paper skill alongside head-of-marketing")
try:
    import registry as _registry
except ImportError as exc:
    raise SystemExit("%s. (%s)" % (_MISSING, exc))
try:
    _PAPER_DIR = _registry.style_dir("paper")
except LookupError as exc:
    raise SystemExit("%s. (%s)" % (_MISSING, exc))
try:
    _FONTS = _registry.style_fonts("paper")
except LookupError:
    _FONTS = os.path.join(_PAPER_DIR, "fonts")

_FALLBACKS = [
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def font(kind, size, weight=900, width=78):
    """`kind` is display | condensed | typewriter, matching the film's fonts."""
    files = {"display": "Archivo[wdth,wght].ttf",
             "condensed": "Oswald[wght].ttf",
             "typewriter": "SpecialElite-Regular.ttf"}
    path = os.path.join(_FONTS, files.get(kind, files["display"]))
    if os.path.exists(path):
        f = ImageFont.truetype(path, size)
        try:
            if kind == "display":
                f.set_variation_by_axes([weight, width])
            elif kind == "condensed":
                f.set_variation_by_axes([min(700, weight)])
        except Exception:
            pass
        return f
    for fb in _FALLBACKS:
        try:
            return ImageFont.truetype(fb, size, index=1)
        except Exception:
            continue
    return ImageFont.load_default()


def text_w(f, s, tracking=0.0):
    if not s:
        return 0.0
    return sum(f.getlength(c) for c in s) + tracking * (len(s) - 1)


def tracked(draw, xy, s, f, fill, tracking=0.0, anchor_mid=False):
    """Letterspaced text. Pillow cannot track, so glyphs are placed by hand."""
    x, y = xy
    if anchor_mid:
        x -= text_w(f, s, tracking) / 2.0
    for c in s:
        draw.text((x, y), c, font=f, fill=fill)
        x += f.getlength(c) + tracking


def paper(w, h, base, seed=7, grain=9):
    """Aged paper: warm base, fibre grain, soft blotches, edge darkening.

    Flat fills band badly once YouTube re-encodes them, and a perfectly even
    rectangle reads as a placeholder. The noise is what sells it as stock.
    """
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 3), dtype=np.float32)
    arr[:, :] = np.array(base, dtype=np.float32)

    # Fine fibre grain.
    arr += rng.normal(0, grain, (h, w, 1))

    # Low-frequency blotching, built small and scaled up so it stays soft.
    small = rng.normal(0, 1, (max(2, h // 14), max(2, w // 14), 1))
    blot = np.array(Image.fromarray(
        np.clip(small[:, :, 0] * 40 + 128, 0, 255).astype(np.uint8)
    ).resize((w, h), Image.BICUBIC), dtype=np.float32)
    arr += (blot[:, :, None] - 128) * 0.07

    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    # Vignette so the sheet has a centre.
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    shade = np.clip(1.0 - 0.20 * np.clip(r - 0.45, 0, None) ** 1.7, 0.55, 1.0)
    out = np.array(img, dtype=np.float32) * shade[:, :, None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _wobbler(seed, wobble, cycles=(2.0, 3.3, 5.1)):
    """A smooth, slow radius modulation.

    Per-point random jitter looks like a sawtooth, not a pen. A hand wobbles
    over a few centimetres, so the deviation has to be low frequency: a sum of
    a handful of sinusoids at random phase gives a stroke that drifts rather
    than vibrates.
    """
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, math.tau) for _ in cycles]
    amp = [rnd.uniform(0.6, 1.0) for _ in cycles]
    norm = sum(amp)

    def f(u):
        return sum(a * math.sin(u * math.tau * c + p)
                   for a, c, p in zip(amp, cycles, ph)) / norm * wobble / 100.0
    return f


def marker_ellipse(size, box, color, width=14, wobble=3.0, seed=3):
    """A hand-drawn red ring, the same annotation the films use.

    Drawn as an overshooting polyline rather than an ellipse so it reads as
    something a person did with a marker, not a shape tool.
    """
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    wob = _wobbler(seed, wobble)
    rnd = random.Random(seed + 1)
    start = rnd.uniform(-0.5, 0.2)
    pts = []
    steps = 260
    # Slightly more than one full turn: the overlap is the giveaway that it
    # was drawn by hand.
    for i in range(steps + 1):
        u = i / steps
        a = start + u * (math.pi * 2 * 1.07)
        k = 1.0 + wob(u)
        pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    for i in range(len(pts) - 1):
        t = i / len(pts)
        wdt = width * (0.72 + 0.5 * math.sin(math.pi * t))
        d.line([pts[i], pts[i + 1]], fill=color + (255,),
               width=int(max(3, wdt)), joint="curve")
    return layer


def marker_underline(size, x0, x1, y, color, width=11, wobble=2.2, seed=4):
    """Two overlapping rough strokes under a word.

    An underline flatters a long wordmark where a ring does not -- a ring
    around a wide, short word collapses into a thin lens shape.
    """
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    span = x1 - x0
    for k, (ov0, ov1, dy, wd) in enumerate(
            ((-0.02, 1.03, 0.0, 1.0), (0.03, 0.94, 0.42, 0.62))):
        wob = _wobbler(seed + k * 7, wobble)
        pts = []
        for i in range(121):
            u = i / 120
            x = x0 + span * (ov0 + (ov1 - ov0) * u)
            pts.append((x, y + dy * width + wob(u) * width * 5.0))
        for i in range(len(pts) - 1):
            t = i / len(pts)
            d.line([pts[i], pts[i + 1]], fill=color + (255,),
                   width=int(max(3, width * wd * (0.7 + 0.5 * math.sin(math.pi * t)))),
                   joint="curve")
    return layer


def render_icon(pub, out):
    """800x800, judged at 48px.

    Kept to two shapes -- a ring and a monogram -- because at avatar size a
    timeline, a tagline or any third element turns to mud.
    """
    ink = pub.rgb("ink")
    accent = pub.rgb("crimson")
    spec = _spec(pub)
    mono = spec.get("monogram", "TR")

    img = paper(ICON, ICON, pub.rgb("paper"), seed=11, grain=7).convert("RGBA")

    # Mask to a disc: YouTube crops to a circle, and rendering the disc
    # ourselves keeps the edge clean instead of letting the crop bite corners.
    disc = Image.new("L", (ICON, ICON), 0)
    ImageDraw.Draw(disc).ellipse([0, 0, ICON - 1, ICON - 1], fill=255)
    img.putalpha(disc)

    f = font("display", 300, weight=900, width=62)
    d = ImageDraw.Draw(img)
    w = text_w(f, mono, tracking=6)
    bb = f.getbbox(mono)
    tracked(d, (ICON / 2 - w / 2, ICON / 2 - (bb[3] + bb[1]) / 2 - 8),
            mono, f, tuple(ink) + (255,), tracking=6)

    ring = marker_ellipse((ICON, ICON),
                          [ICON * 0.13, ICON * 0.20, ICON * 0.87, ICON * 0.80],
                          tuple(accent), width=26, wobble=2.4, seed=5)
    img = Image.alpha_composite(img, ring)
    img.putalpha(disc)

    img.save(out)
    say(f"icon   {out}  {ICON}x{ICON}  {os.path.getsize(out)/1024:.0f} KB")
    return out


def render_banner(pub, out):
    """2560x1440 with everything legible inside the centred 1235x338."""
    ink, accent = pub.rgb("ink"), pub.rgb("crimson")
    soft = tuple(int(c * 0.62 + 90 * 0.38) for c in ink)
    spec = _spec(pub)
    wordmark = pub.get("brand", "wordmark", default="CHANNEL")
    tagline = spec.get("tagline", "")
    ticks = spec.get("ticks", [])

    img = paper(BANNER_W, BANNER_H, pub.rgb("paper"), seed=23, grain=8)
    d = ImageDraw.Draw(img)

    sx = (BANNER_W - SAFE_W) / 2
    sy = (BANNER_H - SAFE_H) / 2
    cx = BANNER_W / 2

    # --- lay the type out first -------------------------------------------
    # The timeline has to be drawn around the tagline, so every text box is
    # measured before anything is committed to the canvas.
    size = 132
    f = font("display", size, weight=900, width=72)
    track = 10
    while text_w(f, wordmark, track) > SAFE_W - 40 and size > 40:
        size -= 4
        f = font("display", size, weight=900, width=72)
    wm_w = text_w(f, wordmark, track)
    wm_y = sy + 24
    wm_bottom = wm_y + f.getbbox(wordmark)[3]

    tag_box = None
    if tagline:
        fs = 44
        ft = font("condensed", fs, weight=500)
        while text_w(ft, tagline, 3) > SAFE_W - 80 and fs > 20:
            fs -= 2
            ft = font("condensed", fs, weight=500)
        tw = text_w(ft, tagline, 3)
        ty = wm_bottom + 48
        tb = ft.getbbox(tagline)
        tag_box = (cx - tw / 2 - 26, ty + tb[1] - 8, cx + tw / 2 + 26,
                   ty + tb[3] + 8)

    # --- the timeline, full bleed -----------------------------------------
    # Deliberately runs past the safe area: on a wide desktop crop it reads as
    # a line without end, which is the idea, and losing its ends on mobile
    # costs nothing. The tick *labels* however must finish inside the safe
    # area -- a year sliced in half horizontally looks like a rendering bug.
    rule_y = sy + SAFE_H - 70
    d.line([(0, rule_y), (BANNER_W, rule_y)], fill=tuple(ink) + (255,), width=5)
    if ticks:
        ftk = font("typewriter", 30)
        gap = BANNER_W / (len(ticks) + 1)
        for i, label in enumerate(ticks):
            x = gap * (i + 1)
            top = rule_y - (34 if i % 2 == 0 else 20)
            # Stop the tick short of the tagline rather than spearing it.
            if tag_box and tag_box[0] <= x <= tag_box[2]:
                top = max(top, tag_box[3] + 6)
            if top < rule_y - 4:
                d.line([(x, top), (x, rule_y + 6)],
                       fill=tuple(ink) + (255,), width=4)
            lw = ftk.getlength(str(label))
            d.text((x - lw / 2, rule_y + 18), str(label), font=ftk, fill=soft)

    # --- wordmark ---------------------------------------------------------
    tracked(d, (cx - wm_w / 2, wm_y), wordmark, f, tuple(ink), tracking=track)

    # --- marker underline, the film's own annotation ----------------------
    rule = marker_underline(
        (BANNER_W, BANNER_H), cx - wm_w / 2, cx + wm_w / 2, wm_bottom + 20,
        tuple(accent), width=11, wobble=1.4, seed=9)
    img = Image.alpha_composite(img.convert("RGBA"), rule).convert("RGB")
    d = ImageDraw.Draw(img)

    # --- tagline ----------------------------------------------------------
    if tagline:
        tracked(d, (cx - tw / 2, ty), tagline, ft, soft, tracking=3)

    # JPEG, not PNG: a 2560x1440 noise field encodes to ~5 MB as PNG, and
    # YouTube rejects a banner over 6 MB.
    img.save(out, quality=94, subsampling=0)
    say(f"banner {out}  {BANNER_W}x{BANNER_H}  "
        f"{os.path.getsize(out)/1024:.0f} KB  safe {SAFE_W}x{SAFE_H}")
    return out


def _spec(pub):
    import json
    p = pub.p("meta", "brand_spec.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def main():
    ap = argparse.ArgumentParser(description="Render channel icon and banner")
    ap.add_argument("project")
    ap.add_argument("--icon", action="store_true")
    ap.add_argument("--banner", action="store_true")
    a = ap.parse_args()

    pub = Publish(a.project)
    os.makedirs(pub.p("out"), exist_ok=True)
    both = not (a.icon or a.banner)
    if a.icon or both:
        render_icon(pub, pub.p("out", "channel_icon.png"))
    if a.banner or both:
        render_banner(pub, pub.p("out", "channel_banner.jpg"))


if __name__ == "__main__":
    main()
