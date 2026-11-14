#!/usr/bin/env python3
"""Leap VPN App Store frames (dark set).

    python3 make_frames.py      # raw/ -> screenshots/iphone (1320x2868) + screenshots/mac (2880x1800)

Raw captures are not committed; README.md documents how each one was taken.
Nothing here retouches a captured pixel: captures are only scaled DOWN, cropped,
masked and captioned. Every caption must be literally true of the shipped app.

Variants: `04-streaming.png` floats the streaming apps' real App Store icons (the
owner asked for them). That uses third-party marks — Guideline 2.3.7 / trademark
risk — so `alt/04-streaming-glyphs.png` is the same frame with generic glyphs.
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


def f_streaming(logos: bool):
    bg = background(RED if logos else VIOLET, lower=(60, 40, 140))
    caption(bg, "TRAVEL WITH YOUR OWN SERVICES", ["Your shows,", "wherever you are"],
            "Connect to a server back home and keep watching the subscriptions you already pay for.")
    srcs = stream_sources(logos)
    # (cx, cy, size, angle) around the connect card.
    spots = [(200, 930, 230, 8), (650, 880, 200, -6), (1100, 940, 250, -9), (420, 1240, 180, -5),
             (920, 1250, 190, 7), (230, 2530, 220, 6), (690, 2650, 200, 5), (1100, 2510, 240, -8)]
    for (cx, cy, s, a), src in zip(spots, srcs):
        place(bg, icon_tile(src, s), cx, cy, a)
    # The real connect card (iPhone, connected to Amsterdam), cropped inside its own corners.
    c = card(IOS / "home.png", (44, 1660, 1162, 2578), 1060, r_ratio=0.085)
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


IPHONE = [
    ("01-your-network", lambda: f_device("home.png", "YOUR OWN VPN", ["Your network.", "Your rules."],
                                         "WireGuard servers in your own Azure account. Only you hold the keys.", GREEN,
                                         screen_w=1000, angle=-4)),
    ("02-blocking", lambda: f_device("ob2.png", "AD & TRACKER BLOCKING", ["Ads and trackers", "blocked in every app"],
                                     "Filtered on your own server, at no extra cost.", TEAL, screen_w=1000)),
    ("03-locations", lambda: f_device("locations.png", "40 LOCATIONS", ["Pick from 40", "locations worldwide"],
                                      "Americas, Europe, the Middle East, Africa and Asia-Pacific. No bandwidth caps from us.",
                                      BLUE, screen_w=1000)),
    ("04-streaming", lambda: f_streaming(True)),
    ("05-pay-while-on", lambda: f_device("usage.png", "PAY ONLY WHILE CONNECTED", ["From about", "1.5\u00a2 an hour"],
                                         "Servers stop when you disconnect, and Azure bills you directly.", AMBER,
                                         screen_w=1000, lower=(40, 120, 80))),
    ("06-private", lambda: f_device("ob1.png", "PRIVATE BY DESIGN", ["No one else", "sees your traffic"],
                                    "We run no VPN servers and keep no logs. The servers are yours.", VIOLET, screen_w=1000)),
    ("07-home-pc", f_homepc),
    ("08-iphone-and-mac", f_both),
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
    bg = background(RED if logos else VIOLET, MW, MH)
    caption(bg, "TRAVEL WITH YOUR OWN SERVICES", ["Your shows, wherever you are"],
            "Connect to a server back home and keep watching the subscriptions you already pay for.",
            top=110, head=104, sub_size=48)
    srcs = stream_sources(logos)
    spots = [(560, 640, 250, 8), (300, 1050, 220, -7), (640, 1500, 260, 6), (1130, 1640, 170, -5),
             (2320, 640, 260, -8), (2600, 1080, 220, 7), (2240, 1500, 250, -6), (1760, 1650, 170, 5)]
    for (cx, cy, s, a), src in zip(spots, srcs):
        place(bg, icon_tile(src, s), cx, cy, a)
    # The real Mac connect card (connected to Amsterdam), at native size.
    c = card(MAC / "home.png", (530, 630, 1310, 1236), 780, r_ratio=0.085)
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


MACS = [
    ("01-your-network", lambda: m_window("home.png", "YOUR OWN VPN", "Your network. Your rules.",
                                         "WireGuard servers in your own Azure account. Only you hold the keys.", GREEN)),
    ("02-streaming", lambda: m_streaming(True)),
    ("03-pay-while-on", lambda: m_window("usage.png", "PAY ONLY WHILE CONNECTED", "From about 1.5\u00a2 an hour",
                                         "Servers stop when you disconnect, and Azure bills you directly.", AMBER)),
    ("04-iphone-and-mac", m_both),
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
    if not only:
        save(f_streaming(False), OUT / "iphone" / "alt" / "04-streaming-glyphs.png", (W, H))
        save(m_streaming(False), OUT / "mac" / "alt" / "02-streaming-glyphs.png", (MW, MH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
