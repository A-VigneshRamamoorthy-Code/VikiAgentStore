#!/usr/bin/env python3
"""Leap VPN App Store frames (dark set).

    python3 make_frames.py      # raw/ -> screenshots/iphone (1320x2868) + screenshots/mac (2880x1800)

Raw captures are not committed; README.md documents how each one was taken.
Nothing here retouches a captured pixel: captures are only scaled DOWN, cropped,
masked and captioned. Every caption must be literally true of the shipped app.

The streaming frames use generic drawn glyphs only — no third-party app icons or
marks (Guideline 2.3.7). `stream_sources(True)` is kept but unused.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "screenshots"

W, H = 1320, 2868
INK = (8, 12, 11)
MINT = (104, 232, 160)
WHITE = (255, 255, 255)
MUTED = (160, 170, 166)
SFNS = "/System/Library/Fonts/SFNS.ttf"
SFMONO = "/System/Library/Fonts/SFNSMono.ttf"
SQ_N = 3.9
ICON_N = 5.0
BODY_R_RATIO = 0.26

# Per-frame bloom so the gallery strip doesn't read as one repeated image.
GREEN, TEAL, BLUE, VIOLET, AMBER, RED = (40, 170, 110), (30, 150, 160), (40, 100, 220), (120, 70, 210), (210, 140, 40), (200, 50, 60)


def font(path, size, variation="Bold"):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_name(variation)
    except Exception:
        pass
    return f


# ------------------------------------------------------------------ geometry
def squircle_mask(w, h, r, n=None, ss=4):
    n = SQ_N if n is None else n
    r = max(1.0, min(r, min(w, h) / 2.0))
    ws, hs, rs = w * ss, h * ss, r * ss
    xs, ys = np.arange(ws, dtype="float64"), np.arange(hs, dtype="float64")
    dx = np.maximum.reduce([rs - xs, xs - (ws - rs), np.zeros_like(xs)])
    dy = np.maximum.reduce([rs - ys, ys - (hs - rs), np.zeros_like(ys)])
    inside = ((dy[:, None] / rs) ** n + (dx[None, :] / rs) ** n) <= 1.0
    return Image.fromarray(np.where(inside, 255, 0).astype("uint8"), "L").resize((w, h), Image.LANCZOS)


def squircle_ring(w, h, r, width, n=None):
    inner = Image.new("L", (w, h), 0)
    inner.paste(squircle_mask(w - 2 * width, h - 2 * width, r - width, n), (width, width))
    return ImageChops.subtract(squircle_mask(w, h, r, n), inner)


def soft_shadow(size, box, r, alpha, blur, n=None):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    layer.paste(Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, alpha)), (x0, y0), squircle_mask(x1 - x0, y1 - y0, r, n))
    return layer.filter(ImageFilter.GaussianBlur(blur)).filter(ImageFilter.GaussianBlur(blur * 0.6))


def paste(canvas: Image.Image, layer: Image.Image, x, y):
    """alpha-composite `layer` at (x, y), clipping anything off-canvas (incl. negative offsets)."""
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    ex, ey = min(layer.width, canvas.width - x), min(layer.height, canvas.height - y)
    if ex <= sx or ey <= sy:
        return
    part = layer.crop((sx, sy, ex, ey))
    base = canvas.crop((x + sx, y + sy, x + ex, y + ey)).convert("RGBA")
    canvas.paste(Image.alpha_composite(base, part).convert(canvas.mode), (x + sx, y + sy))


def place(canvas, layer, cx, cy, angle=0.0):
    """Paste `layer` centred on (cx, cy), rotated `angle` degrees (counter-clockwise, Pillow)."""
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    paste(canvas, layer, cx - layer.width / 2, cy - layer.height / 2)


# ---------------------------------------------------------------- background
def background(wash, w=None, h=None, lower=None):
    w, h = w or W, h or H
    bg = Image.new("RGB", (w, h), INK)
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    r = int(w * 0.6)
    gd.ellipse([w // 2 - r, int(h * 0.11) - r, w // 2 + r, int(h * 0.11) + r], fill=58)
    bg = Image.composite(Image.new("RGB", (w, h), wash), bg, glow.filter(ImageFilter.GaussianBlur(w * 0.17)))
    if lower:
        glow2 = Image.new("L", (w, h), 0)
        r2 = int(w * 0.7)
        ImageDraw.Draw(glow2).ellipse([w // 2 - r2, int(h * 0.78) - r2, w // 2 + r2, int(h * 0.78) + r2], fill=30)
        bg = Image.composite(Image.new("RGB", (w, h), lower), bg, glow2.filter(ImageFilter.GaussianBlur(w * 0.2)))
    d = ImageDraw.Draw(bg)
    step = 44 if w < 2000 else 48
    for y in range(70, h, step):
        for x in range(step, w, step):
            d.ellipse([x, y, x + 3, y + 3], fill=(22, 30, 27))
    return bg


def caption(img, eyebrow, lines, sub=None, top=128, wash=MINT, w=None, head=104, sub_size=44):
    w = w or img.width
    d = ImageDraw.Draw(img)
    ef = font(SFMONO, 34 if w < 2000 else 40)
    et = " ".join(list(eyebrow.replace(" ", "\u2009")))
    d.text(((w - d.textlength(et, font=ef)) / 2, top), et, font=ef, fill=wash)
    size = head
    while size > 62:
        f = font(SFNS, size)
        if max(d.textlength(l, font=f) for l in lines) <= w - 170:
            break
        size -= 2
    f = font(SFNS, size)
    y = top + 70
    for l in lines:
        d.text(((w - d.textlength(l, font=f)) / 2, y), l, font=f, fill=WHITE)
        y += int(size * 1.12)
    if sub:
        sf = font(SFNS, sub_size, "Semibold")
        words, cur, out = sub.split(), "", []
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=sf) <= min(w - 230, 1700):
                cur = t
            else:
                out.append(cur)
                cur = wd
        out.append(cur)
        y += 18
        for l in out:
            d.text(((w - d.textlength(l, font=sf)) / 2, y), l, font=sf, fill=MUTED)
            y += int(sub_size * 1.3)
    return y


# -------------------------------------------------------------------- device
def dynamic_island(screen, sw):
    u = sw / 402.0  # iPhone 17 Pro: 402pt wide
    w, h, top = 125 * u, 37 * u, 11 * u
    x0 = (sw - w) / 2
    ImageDraw.Draw(screen).rounded_rectangle([x0, top, x0 + w, top + h], radius=h / 2, fill=(0, 0, 0, 255))


def device(path, screen_w, pad=150):
    """A titanium iPhone body: squircle outer edge, CONCENTRIC screen corner
    (screen_r = body_r - bezel), side buttons, Dynamic Island, soft shadow."""
    im = Image.open(path).convert("RGB")
    assert screen_w <= im.width, "never upscale a capture"
    sh = round(screen_w * im.height / im.width)
    im = im.resize((screen_w, sh), Image.LANCZOS)
    bezel = max(12, round(screen_w * 0.028))
    bw, bh = screen_w + 2 * bezel, sh + 2 * bezel
    br = round(bw * BODY_R_RATIO)
    sr = br - bezel
    grad = Image.new("RGB", (1, bh))
    for y in range(bh):
        t = y / (bh - 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip((78, 80, 86), (38, 39, 43))))
    body = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    body.paste(grad.resize((bw, bh)), (0, 0), squircle_mask(bw, bh, br))
    body.paste(Image.new("RGBA", (bw, bh), (160, 162, 168, 210)), (0, 0), squircle_ring(bw, bh, br, 2))
    bd = ImageDraw.Draw(body)
    btn = max(3, round(bezel * 0.45))
    for x, a, b in ((-1, .150, .196), (-1, .232, .303), (-1, .318, .389), (bw - btn, .263, .377)):
        bd.rounded_rectangle([x, int(bh * a), x + btn, int(bh * b)], radius=btn, fill=(100, 102, 108, 255))
    screen = Image.new("RGBA", (screen_w, sh), (0, 0, 0, 0))
    screen.paste(im, (0, 0), squircle_mask(screen_w, sh, sr))
    screen.paste(Image.new("RGBA", (screen_w, sh), (0, 0, 0, 150)), (0, 0), squircle_ring(screen_w, sh, sr, 2))
    dynamic_island(screen, screen_w)
    body.alpha_composite(screen, (bezel, bezel))
    layer = Image.new("RGBA", (bw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, soft_shadow(layer.size, (pad, pad + 28, pad + bw, pad + bh + 28), br, 150, 56))
    layer.alpha_composite(body, (pad, pad))
    return layer


def card(path, box, width, r_ratio=0.075, pad=120, n=SQ_N, rim=True):
    """A crop of a capture, masked to a rounded card with a hairline and shadow."""
    im = Image.open(path).convert("RGB").crop(box)
    assert width <= im.width, "never upscale a capture"
    h = round(width * im.height / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    r = round(width * r_ratio)
    c = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    c.paste(im, (0, 0), squircle_mask(width, h, r, n))
    if rim:
        c.paste(Image.new("RGBA", (width, h), (255, 255, 255, 40)), (0, 0), squircle_ring(width, h, r, 2, n))
    layer = Image.new("RGBA", (width + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, soft_shadow(layer.size, (pad, pad + 26, pad + width, pad + h + 26), r, 170, 48, n))
    layer.alpha_composite(c, (pad, pad))
    return layer


def mac_window(path, width, pad=140, box=None):
    im = Image.open(path).convert("RGB")
    if box:
        im = im.crop(box)
    assert width <= im.width, "never upscale a capture"
    h = round(width * im.height / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    r = max(10, round(width * 0.0125))
    c = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    c.paste(im, (0, 0), squircle_mask(width, h, r, 5.0))
    c.paste(Image.new("RGBA", (width, h), (255, 255, 255, 46)), (0, 0), squircle_ring(width, h, r, 2, 5.0))
    layer = Image.new("RGBA", (width + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, soft_shadow(layer.size, (pad, pad + 30, pad + width, pad + h + 30), r, 170, 50, 5.0))
    layer.alpha_composite(c, (pad, pad))
    return layer


# ------------------------------------------------------------- streaming tiles
LOGOS = ["Netflix", "Prime_Video", "Disney+", "YouTube", "Max", "Hulu", "JioHotstar", "Spotify"]


def icon_tile(img: Image.Image, size, pad=70):
    img = img.convert("RGB").resize((size, size), Image.LANCZOS)
    r = round(size * 0.225)
    t = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    t.paste(img, (0, 0), squircle_mask(size, size, r, ICON_N))
    layer = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, soft_shadow(layer.size, (pad, pad + 18, pad + size, pad + size + 18), r, 170, 30, ICON_N))
    layer.alpha_composite(t, (pad, pad))
    return layer


GLYPH_COLORS = [(196, 40, 52), (24, 110, 200), (36, 60, 150), (210, 60, 60), (110, 60, 200), (30, 160, 110), (230, 140, 30), (40, 170, 90)]


def glyph_tile(i, size=512):
    """A generic streaming glyph (no third-party marks): play, TV, clapper, note, ball…"""
    c1 = GLYPH_COLORS[i % len(GLYPH_COLORS)]
    c2 = tuple(max(0, v - 70) for v in c1)
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    im = g.resize((size, size)).convert("RGBA")
    d = ImageDraw.Draw(im)
    s, m, wh = size, size / 2, (255, 255, 255, 255)
    k = i % 6
    if k == 0:  # play
        d.polygon([(s * .38, s * .28), (s * .38, s * .72), (s * .74, s * .5)], fill=wh)
    elif k == 1:  # tv
        d.rounded_rectangle([s * .22, s * .28, s * .78, s * .66], radius=s * .05, outline=wh, width=int(s * .055))
        d.line([(s * .4, s * .76), (s * .6, s * .76)], fill=wh, width=int(s * .055))
    elif k == 2:  # clapperboard
        d.rounded_rectangle([s * .24, s * .42, s * .76, s * .74], radius=s * .03, fill=wh)
        d.polygon([(s * .24, s * .30), (s * .74, s * .22), (s * .76, s * .34), (s * .26, s * .40)], fill=wh)
    elif k == 3:  # music note
        d.ellipse([s * .28, s * .56, s * .46, s * .72], fill=wh)
        d.rectangle([s * .42, s * .26, s * .47, s * .64], fill=wh)
        d.polygon([(s * .42, s * .26), (s * .70, s * .20), (s * .70, s * .32), (s * .47, s * .37)], fill=wh)
    elif k == 4:  # popcorn-ish film reel
        d.ellipse([s * .24, s * .24, s * .76, s * .76], outline=wh, width=int(s * .055))
        for a in range(0, 360, 72):
            x, y = m + s * .14 * math.cos(math.radians(a)), m + s * .14 * math.sin(math.radians(a))
            d.ellipse([x - s * .05, y - s * .05, x + s * .05, y + s * .05], fill=wh)
    else:  # sports ball
        d.ellipse([s * .26, s * .26, s * .74, s * .74], outline=wh, width=int(s * .05))
        d.line([(s * .26, m), (s * .74, m)], fill=wh, width=int(s * .04))
        d.arc([s * .38, s * .26, s * .62, s * .74], 270, 90, fill=wh, width=int(s * .04))
        d.arc([s * .38, s * .26, s * .62, s * .74], 90, 270, fill=wh, width=int(s * .04))
    return im.convert("RGB")


def stream_sources(logos: bool):
    if logos:
        return [Image.open(RAW / "logos" / f"{n}.png") for n in LOGOS]
    return [glyph_tile(i) for i in range(len(LOGOS))]


# ---------------------------------------------------------------- iPhone set
IOS = RAW / "ios"
# The glass connect card's true bounds in each capture. Its own corners are rounder than a
# squircle of the same radius, so the masks use a low exponent; otherwise the map shows
# through at the corners.
HOME_CARD = (40, 1652, 1166, 2588)
MAC_CARD = (526, 626, 1314, 1238)


def f_device(raw, eyebrow, lines, sub, wash, screen_w=1000, top=None, angle=0.0, cx=None, lower=None):
    bg = background(wash, lower=lower)
    y = caption(bg, eyebrow, lines, sub, wash=MINT)
    dev = device(IOS / raw, screen_w)
    t = (top if top is not None else y + 40) - 150
    if angle:
        place(bg, dev, cx or W / 2, t + dev.height / 2, angle)
    else:
        paste(bg, dev, (W - dev.width) / 2 + (cx - W / 2 if cx else 0), t)
    return bg


HERO_CENTER = {"ob1.png": (603, 1066), "ob2.png": (603, 920)}  # centre of the glowing ring in each capture
HERO_TITLE_Y = {"ob1.png": 1508, "ob2.png": 1362}  # first row of the page title; the art must stop above it
HERO_R = 560


def hero_art(raw):
    """The onboarding page's real artwork (ring, icon, dot map), round-feathered into the frame."""
    cx, cy = HERO_CENTER[raw]
    im = Image.open(IOS / raw).convert("RGB").crop((cx - HERO_R, cy - HERO_R, cx + HERO_R, cy + HERO_R))
    n = 2 * HERO_R
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - HERO_R + .5, yy - HERO_R + .5)
    a = np.clip((HERO_R - r) / (HERO_R - 300), 0, 1) ** 1.4
    cut = HERO_TITLE_Y[raw] - 50 - (cy - HERO_R)  # crop row where the page title begins (minus its glow)
    a *= np.clip((cut - yy) / 120, 0, 1)
    out = im.convert("RGBA")
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    return out


def f_hero(raw, eyebrow, lines, sub, rows, wash, lower=None):
    bg = background(wash, lower=lower)
    caption(bg, eyebrow, lines, sub, wash=MINT)
    art = hero_art(raw)
    paste(bg, art, (W - art.width) / 2, 1080 - HERO_R)
    d = ImageDraw.Draw(bg)
    f = font(SFNS, 70, "Semibold")
    widest = max(d.textlength(t, font=f) for t in rows)
    x = (W - widest - 96) / 2 + 40
    for i, t in enumerate(rows):
        cy = 1740 + i * 200
        mark(d, x, cy, 42, True)
        d.text((x + 88, cy - 70 * 0.62), t, font=f, fill=WHITE)
    return bg


def f_streaming(logos: bool):
    bg = background(RED, lower=(60, 40, 140))
    caption(bg, "TRAVEL WITH YOUR OWN SERVICES", ["Your shows,", "wherever you are"],
            "Connect to a server back home and keep watching the subscriptions you already pay for.")
    srcs = stream_sources(logos)
    # (cx, cy, size, angle) around the connect card.
    spots = [(200, 930, 230, 8), (650, 880, 200, -6), (1100, 940, 250, -9), (420, 1240, 180, -5),
             (920, 1250, 190, 7), (230, 2530, 220, 6), (690, 2650, 200, 5), (1100, 2510, 240, -8)]
    for (cx, cy, s, a), src in zip(spots, srcs):
        place(bg, icon_tile(src, s), cx, cy, a)
    # The real connect card (iPhone, connected to Amsterdam), cropped inside its own corners.
    c = card(IOS / "home.png", HOME_CARD, 1060, r_ratio=0.15, n=2.4)
    place(bg, c, W / 2, 1900, -3)
    return bg


def f_homepc():
    bg = background(AMBER, lower=(40, 120, 80))
    caption(bg, "HOME PC", ["Or browse from", "your own home PC"],
            "Pair a PC at home and connect straight to it — no Azure server needed.")
    # Status bar → map → sheet header → Direct/Through Azure → this device → home PC.
    # Cropped just above the sheet's explainer paragraph, which the owner asked to leave out.
    c = card(IOS / "homepc.png", (0, 0, 1206, 1912), 1150, r_ratio=0.07)
    paste(bg, c, (W - c.width) / 2, 640 - 120)
    return bg


def f_both():
    bg = background(BLUE, lower=(30, 120, 90))
    caption(bg, "ONE SUBSCRIPTION, BOTH DEVICES", ["iPhone and Mac.", "One subscription."],
            "Your locations and settings, ready on every device you own.")
    mac = mac_window(RAW / "mac" / "home.png", 1220)
    paste(bg, mac, (W - mac.width) / 2 - 40, 760)
    dev = device(IOS / "home.png", 560)
    paste(bg, dev, W - dev.width + 40, 1240)
    return bg


# ------------------------------------------------------------ drawn panels
def panel(w, h, fill, rim, r=None, pad=90, alpha=255):
    r = r or round(min(w, h) * 0.12)
    p = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    p.paste(Image.new("RGBA", (w, h), fill + (alpha,)), (0, 0), squircle_mask(w, h, r))
    p.paste(Image.new("RGBA", (w, h), rim), (0, 0), squircle_ring(w, h, r, 3))
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, soft_shadow(layer.size, (pad, pad + 22, pad + w, pad + h + 22), r, 150, 40))
    layer.alpha_composite(p, (pad, pad))
    return layer, pad


def mark(d, cx, cy, rad, ok):
    """A filled circle with a tick (ok) or a cross."""
    col = (52, 199, 112) if ok else (120, 46, 52)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)
    w = max(4, round(rad * 0.22))
    if ok:
        d.line([(cx - rad * .45, cy + rad * .02), (cx - rad * .1, cy + rad * .38), (cx + rad * .5, cy - rad * .36)],
               fill=WHITE, width=w, joint="curve")
    else:
        k = rad * .38
        d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=(255, 150, 150), width=w)
        d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=(255, 150, 150), width=w)


def checklist(title, tag, rows, ok, w, row_h=104, size=50):
    h = 150 + row_h * len(rows) + 30
    fill, rim = ((22, 46, 34), (104, 232, 160, 150)) if ok else ((24, 24, 28), (255, 255, 255, 34))
    layer, pad = panel(w, h, fill, rim)
    d = ImageDraw.Draw(layer)
    tf = font(SFNS, 58)
    d.text((pad + 60, pad + 46), title, font=tf, fill=WHITE if ok else (200, 200, 205))
    gf = font(SFMONO, 30)
    tw = d.textlength(tag, font=gf)
    tx = pad + w - 60 - tw - 36
    d.rounded_rectangle([tx, pad + 52, tx + tw + 36, pad + 106], radius=27,
                        fill=(52, 199, 112, 60) if ok else (255, 255, 255, 18))
    d.text((tx + 18, pad + 61), tag, font=gf, fill=MINT if ok else MUTED)
    rf = font(SFNS, size, "Semibold")
    y = pad + 150
    for text in rows:
        mark(d, pad + 92, y + row_h / 2 - 6, 30, ok)
        d.text((pad + 150, y + row_h / 2 - 6 - size * 0.62), text, font=rf, fill=WHITE if ok else (150, 150, 158))
        y += row_h
    return layer


THEIRS = ["Their servers", "Your data on their disks", "Their ad & tracker lists", "Their shared IP addresses", "Their rules"]
YOURS = ["Your servers", "Your data, in your account", "Your ad & tracker filters", "Your own IP addresses", "Your rules"]


def f_owns():
    bg = background(GREEN, lower=(30, 90, 70))
    caption(bg, "WHO OWNS YOUR VPN?", ["Other VPNs own it.", "With Leap, you do."],
            "Servers, data, filters and IPs live in your own Azure account. No one else holds the keys.")
    a = checklist("A typical VPN", "THE COMPANY", THEIRS, False, 1140, row_h=116, size=50)
    paste(bg, a, (W - a.width) / 2, 640 - 90)
    b = checklist("Leap VPN", "YOU", YOURS, True, 1180, row_h=134, size=56)
    paste(bg, b, (W - b.width) / 2, 1480 - 90)
    d = ImageDraw.Draw(bg)
    f = font(SFNS, 50, "Semibold")
    for i, t in enumerate(["No company in the middle.", "The most private VPN you can get."]):
        d.text(((W - d.textlength(t, font=f)) / 2, 2460 + i * 70), t, font=f, fill=MINT if i else MUTED)
    return bg


def f_new_ip():
    bg = background(BLUE, lower=(30, 120, 90))
    caption(bg, "FRESH IP ON DEMAND", ["A new IP", "whenever you need it"],
            "Tap \u21bb for a new address on your own server. Economy hands you a fresh one every time you connect.")
    c = card(IOS / "home.png", HOME_CARD, 1060, r_ratio=0.15, n=2.4)
    cx, cy = W / 2, 1480
    place(bg, c, cx, cy)
    # Ring the real New IP button in the capture (its centre in raw pixels -> canvas).
    s = 1060 / (HOME_CARD[2] - HOME_CARD[0])
    bx = cx - 530 + (1040 - HOME_CARD[0]) * s
    by = cy - c.height / 2 + 120 + (1971 - HOME_CARD[1]) * s
    ring = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    for rr, a in ((66, 255), (84, 90)):
        rd.ellipse([bx - rr, by - rr, bx + rr, by + rr], outline=MINT + (a,), width=8 if a == 255 else 5)
    bg.paste(Image.alpha_composite(bg.convert("RGBA"), ring).convert("RGB"))
    d = ImageDraw.Draw(bg)
    chips = ["New IP in one tap", "Economy: a new IP every connect", "40 locations to hop between"]
    f = font(SFNS, 50, "Semibold")
    y = 2160
    for t in chips:
        tw = d.textlength(t, font=f)
        x = (W - tw - 130) / 2
        d.rounded_rectangle([x, y, x + tw + 130, y + 116], radius=58, fill=(26, 34, 40), outline=(70, 80, 88), width=2)
        mark(d, x + 58, y + 58, 26, True)
        d.text((x + 102, y + 58 - 50 * 0.62), t, font=f, fill=WHITE)
        y += 150
    return bg


IPHONE = [
    ("01-your-network", lambda: f_device("home.png", "YOUR OWN VPN", ["Your network.", "Your rules."],
                                         "WireGuard servers in your own Azure account. Only you hold the keys.", GREEN,
                                         screen_w=1000, angle=-4)),
    ("02-who-owns", f_owns),
    ("03-most-private", lambda: f_hero("ob1.png", "PRIVATE BY DESIGN", ["The most private VPN", "is the one you own"],
                                       "No VPN company in the middle.",
                                       ["Servers in your own Azure", "We see none of your traffic", "We keep no logs",
                                        "Only you hold the keys"], VIOLET)),
    ("04-blocking", lambda: f_hero("ob2.png", "TRACKER & AD BLOCKING", ["Trackers stopped.", "Ads blocked."],
                                   "Filtered on your own server.",
                                   ["Block trackers", "Block ads", "Blocks ads in apps", "No extra cost"], TEAL)),
    ("05-new-ip", f_new_ip),
    ("06-streaming", lambda: f_streaming(False)),
    ("07-locations", lambda: f_device("locations.png", "40 LOCATIONS", ["Pick from 40", "locations worldwide"],
                                      "Americas, Europe, the Middle East, Africa and Asia-Pacific. No bandwidth caps from us.",
                                      BLUE, screen_w=1000)),
    ("08-pay-while-on", lambda: f_device("usage.png", "PAY ONLY WHILE CONNECTED", ["From about", "1.5\u00a2 an hour"],
                                         "Servers stop when you disconnect, and Azure bills you directly.", AMBER,
                                         screen_w=1000, lower=(40, 120, 80))),
    ("09-iphone-and-mac", f_both),
    ("10-home-pc", f_homepc),
]


# ------------------------------------------------------------------- Mac set
MW, MH = 2880, 1800
MAC = RAW / "mac"


def m_window(raw, eyebrow, headline, sub, wash, width=1840):
    bg = background(wash, MW, MH)
    caption(bg, eyebrow, [headline], sub, top=110, head=104, sub_size=48)
    win = mac_window(MAC / raw, width)
    paste(bg, win, (MW - win.width) / 2, 470 - 140)
    return bg


def m_streaming(logos: bool):
    bg = background(RED, MW, MH)
    caption(bg, "TRAVEL WITH YOUR OWN SERVICES", ["Your shows, wherever you are"],
            "Connect to a server back home and keep watching what you already pay for.",
            top=110, head=104, sub_size=48)
    srcs = stream_sources(logos)
    spots = [(560, 640, 250, 8), (300, 1050, 220, -7), (640, 1500, 260, 6), (1130, 1640, 170, -5),
             (2320, 640, 260, -8), (2600, 1080, 220, 7), (2240, 1500, 250, -6), (1760, 1650, 170, 5)]
    for (cx, cy, s, a), src in zip(spots, srcs):
        place(bg, icon_tile(src, s), cx, cy, a)
    # The real Mac connect card (connected to Amsterdam), at native size.
    c = card(MAC / "home.png", MAC_CARD, 780, r_ratio=0.11, n=2.6)
    place(bg, c, MW / 2, 1130, -2)
    return bg


def m_both():
    bg = background(BLUE, MW, MH, lower=(30, 120, 90))
    caption(bg, "ONE SUBSCRIPTION, BOTH DEVICES", ["iPhone and Mac. One subscription."],
            "Your locations and settings, ready on every device you own.", top=110, head=104, sub_size=48)
    win = mac_window(MAC / "home.png", 1640)
    paste(bg, win, 300 - 140, 470 - 140)
    dev = device(IOS / "home.png", 560)
    paste(bg, dev, 2000 - 150, 560 - 150)
    return bg


def m_owns():
    bg = background(GREEN, MW, MH, lower=(30, 90, 70))
    caption(bg, "WHO OWNS YOUR VPN?", ["Other VPNs own it. With Leap, you do."],
            "Servers, data, filters and IPs live in your own Azure account.",
            top=110, head=104, sub_size=48)
    a = checklist("A typical VPN", "THE COMPANY", THEIRS, False, 1120, row_h=124, size=52)
    b = checklist("Leap VPN", "YOU", YOURS, True, 1160, row_h=124, size=54)
    paste(bg, a, MW / 2 - 60 - a.width + 90, 520)
    paste(bg, b, MW / 2 + 60 - 90, 500)
    d = ImageDraw.Draw(bg)
    f = font(SFNS, 56, "Semibold")
    t1, t2 = "No company in the middle.  ", "The most private VPN you can get."
    w1, w2 = d.textlength(t1, font=f), d.textlength(t2, font=f)
    x = (MW - w1 - w2) / 2
    d.text((x, 1560), t1, font=f, fill=MUTED)
    d.text((x + w1, 1560), t2, font=f, fill=MINT)
    return bg


MACS = [
    ("01-your-network", lambda: m_window("home.png", "YOUR OWN VPN", "Your network. Your rules.",
                                         "WireGuard servers in your own Azure account. Only you hold the keys.", GREEN)),
    ("02-who-owns", m_owns),
    ("03-streaming", lambda: m_streaming(False)),
    ("04-pay-while-on", lambda: m_window("usage.png", "PAY ONLY WHILE CONNECTED", "From about 1.5\u00a2 an hour",
                                         "Servers stop when you disconnect, and Azure bills you directly.", AMBER)),
    ("05-iphone-and-mac", m_both),
]


def save(img, path, size):
    img = img.convert("RGB")
    assert img.size == size, (path, img.size)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    print(f"  {path.relative_to(HERE)}  {img.width}x{img.height}")


def main():
    for sub in ("iphone", "mac"):
        for old in (OUT / sub).glob("**/*.png"):
            old.unlink()
    only = set(sys.argv[1:])
    for name, fn in IPHONE:
        if not only or name in only:
            save(fn(), OUT / "iphone" / f"{name}.png", (W, H))
    for name, fn in MACS:
        if not only or "mac-" + name in only:
            save(fn(), OUT / "mac" / f"{name}.png", (MW, MH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
