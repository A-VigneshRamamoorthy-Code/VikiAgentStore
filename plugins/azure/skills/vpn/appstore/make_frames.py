#!/usr/bin/env python3
"""Leap VPN App Store frames. Regenerates screenshots/{iphone,mac} from raw captures.

Raw captures (not committed): /tmp/cap (iPhone 17 Pro Max sim, 1206x2622),
/tmp/mcap (Mac app cacheDisplay snapshots, @2x). See README.md for capture states.
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "screenshots")
CAP, MCAP = "/tmp/cap", "/tmp/mcap"
SF = "/System/Library/Fonts/SFNS.ttf"
SFR = "/System/Library/Fonts/SFNSRounded.ttf"
GREEN = (0, 122, 77)
INK = (16, 24, 22)
SUB = (78, 92, 88)
SQ_N = 4.2


def font(size, weight="Bold", path=SF):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def squircle_mask(w, h, r, n=SQ_N, ss=4):
    W, H, R = w * ss, h * ss, r * ss
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.rectangle((R, 0, W - R, H), fill=255)
    d.rectangle((0, R, W, H - R), fill=255)
    steps = 400
    import math
    pts = []
    for i in range(steps + 1):
        t = i / steps * (math.pi / 2)
        c, s = math.cos(t), math.sin(t)
        pts.append((R * (c ** (2 / n)), R * (s ** (2 / n))))
    for cx, cy, sx, sy in ((W - R, H - R, 1, 1), (R, H - R, -1, 1), (R, R, -1, -1), (W - R, R, 1, -1)):
        d.polygon([(cx, cy)] + [(cx + sx * x, cy + sy * y) for x, y in pts], fill=255)
    return m.resize((w, h), Image.LANCZOS)


def background(w, h, bloom, bloom2=None):
    bg = Image.new("RGB", (w, h), (246, 250, 248))
    layer = Image.new("RGB", (w, h), (246, 250, 248))
    d = ImageDraw.Draw(layer)
    d.ellipse((-w * 0.3, -h * 0.25, w * 0.9, h * 0.45), fill=bloom)
    if bloom2:
        d.ellipse((w * 0.25, h * 0.55, w * 1.35, h * 1.25), fill=bloom2)
    return Image.blend(bg, layer.filter(ImageFilter.GaussianBlur(w // 5)), 0.85)


def paste(canvas, img, x, y):
    """alpha_composite that tolerates negative / off-canvas boxes."""
    x, y = int(x), int(y)
    sx, sy = max(0, -x), max(0, -y)
    img = img.crop((sx, sy, min(img.width, canvas.width - x), min(img.height, canvas.height - y)))
    canvas.alpha_composite(img, (x + sx, y + sy))


def shadow(w, h, r, blur, alpha=70):
    pad = blur * 3
    s = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    m = squircle_mask(w, h, r)
    s.paste(Image.new("RGBA", (w, h), (10, 30, 25, alpha)), (pad, pad), m)
    return s.filter(ImageFilter.GaussianBlur(blur)), pad


def device(cap, scale):
    """iPhone-style body around an uncropped capture. scale<=1 (never upscale)."""
    assert scale <= 1
    sw, sh = int(cap.width * scale), int(cap.height * scale)
    screen = cap.convert("RGBA").resize((sw, sh), Image.LANCZOS)
    bezel = int(sw * 0.035)
    bw, bh = sw + 2 * bezel, sh + 2 * bezel
    body_r = int(bw * 0.152)
    screen_r = body_r - bezel
    body = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    body.paste(Image.new("RGBA", (bw, bh), (28, 30, 32, 255)), (0, 0), squircle_mask(bw, bh, body_r))
    rim = Image.new("RGBA", (bw - 6, bh - 6), (0, 0, 0, 0))
    rim.paste(Image.new("RGBA", rim.size, (12, 12, 14, 255)), (0, 0), squircle_mask(bw - 6, bh - 6, body_r - 3))
    body.alpha_composite(rim, (3, 3))
    scr = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    scr.paste(screen, (0, 0), squircle_mask(sw, sh, screen_r))
    body.alpha_composite(scr, (bezel, bezel))
    return body, body_r


def card(cap, crop, r_ratio=0.06, max_w=None):
    img = cap.convert("RGBA").crop(crop)
    if max_w and img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)), Image.LANCZOS)
    r = int(min(img.size) * r_ratio)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), squircle_mask(*img.size, r))
    border = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, outline=(0, 0, 0, 30), width=2)
    out.alpha_composite(border)
    return out, r


def place(canvas, layer, r, x, y, blur=40, alpha=70):
    s, pad = shadow(layer.width, layer.height, r, blur, alpha)
    paste(canvas, s, x - pad, y - pad + blur // 2)
    paste(canvas, layer, x, y)


def caption(canvas, head, sub, y, size, cx=None, width=None, align="center"):
    d = ImageDraw.Draw(canvas)
    cx = canvas.width // 2 if cx is None else cx
    hf, sf = font(size, "Bold"), font(int(size * 0.46), "Medium")
    for i, line in enumerate(head.split("\n")):
        w = d.textlength(line, font=hf)
        x = cx - w / 2 if align == "center" else cx
        d.text((x, y), line, font=hf, fill=INK)
        y += int(size * 1.12)
    y += int(size * 0.25)
    for line in sub.split("\n"):
        w = d.textlength(line, font=sf)
        x = cx - w / 2 if align == "center" else cx
        d.text((x, y), line, font=sf, fill=SUB)
        y += int(size * 0.62)
    return y


def chip(canvas, x, y, text, glyph=None, size=46, fill=(255, 255, 255, 235), ink=INK):
    d = ImageDraw.Draw(canvas)
    f = font(size, "Semibold")
    tw = d.textlength(text, font=f)
    gw = size * 1.3 if glyph else 0
    w, h = int(tw + gw + size * 1.4), int(size * 2.1)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=fill)
    tx = size * 0.7
    if glyph:
        glyph(ld, int(tx), h // 2, int(size * 0.95))
        tx += gw
    ld.text((tx, h / 2), text, font=f, fill=ink, anchor="lm")
    place(canvas, layer, h // 2, x, y, blur=18, alpha=40)
    return w, h


# --- generic glyphs (no third-party marks) ---------------------------------
def g_play(d, x, y, s):
    d.ellipse((x, y - s // 2, x + s, y + s // 2), fill=GREEN)
    d.polygon([(x + s * 0.38, y - s * 0.22), (x + s * 0.38, y + s * 0.22), (x + s * 0.74, y)], fill="white")


def g_tv(d, x, y, s):
    d.rounded_rectangle((x, y - s * 0.38, x + s, y + s * 0.3), s // 8, outline=GREEN, width=max(3, s // 10))
    d.line((x + s * 0.3, y + s * 0.45, x + s * 0.7, y + s * 0.45), fill=GREEN, width=max(3, s // 10))


def g_film(d, x, y, s):
    d.rounded_rectangle((x, y - s * 0.4, x + s, y + s * 0.4), s // 8, fill=GREEN)
    for i in range(3):
        cx = x + s * (0.2 + 0.3 * i)
        d.rectangle((cx - s * 0.06, y - s * 0.32, cx + s * 0.06, y - s * 0.2), fill="white")
        d.rectangle((cx - s * 0.06, y + s * 0.2, cx + s * 0.06, y + s * 0.32), fill="white")


def g_music(d, x, y, s):
    d.ellipse((x, y + s * 0.05, x + s * 0.38, y + s * 0.4), fill=GREEN)
    d.rectangle((x + s * 0.3, y - s * 0.45, x + s * 0.38, y + s * 0.25), fill=GREEN)
    d.polygon([(x + s * 0.3, y - s * 0.45), (x + s * 0.85, y - s * 0.3), (x + s * 0.85, y - s * 0.15), (x + s * 0.38, y - s * 0.3)], fill=GREEN)


def g_check(d, x, y, s):
    d.ellipse((x, y - s // 2, x + s, y + s // 2), fill=GREEN)
    d.line([(x + s * 0.27, y), (x + s * 0.45, y + s * 0.18), (x + s * 0.75, y - s * 0.18)], fill="white", width=max(3, s // 8))


def g_dot(color):
    def g(d, x, y, s):
        d.ellipse((x + s * 0.2, y - s * 0.3, x + s * 0.8, y + s * 0.3), fill=color)
    return g


def save(canvas, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    canvas.convert("RGB").save(path, "PNG", optimize=True)
    print("wrote", os.path.relpath(path, HERE))


def load(path):
    return Image.open(path)


# --- iPhone 6.9" (1320 x 2868) ---------------------------------------------
IW, IH = 1320, 2868


def iphone_device_frame(name, cap, head, sub, bloom, bloom2, scale=0.86, top=640, extras=None):
    c = background(IW, IH, bloom, bloom2).convert("RGBA")
    caption(c, head, sub, 170, 96)
    body, r = device(load(cap), scale)
    place(c, body, r, (IW - body.width) // 2, top)
    if extras:
        extras(c)
    save(c, f"{OUT}/iphone/{name}")


def iphone():
    iphone_device_frame("01-home.png", f"{CAP}/home.png",
                        "Your own VPN.\nOn your own servers.",
                        "Leap builds it in your Azure account",
                        (200, 238, 220), (210, 228, 250))
    iphone_device_frame("02-locations.png", f"{CAP}/locations.png",
                        "40 server locations",
                        "Pick the countries you want, from India to Canada",
                        (214, 230, 252), (205, 240, 225))
    iphone_device_frame("03-blocking.png", f"{CAP}/ob2.png",
                        "Ads and trackers\nblocked",
                        "Filtered on your server, in every app",
                        (255, 226, 214), (214, 240, 226))

    # 04 streaming (generic glyphs only) + home capture
    c = background(IW, IH, (226, 220, 252), (206, 240, 226)).convert("RGBA")
    caption(c, "Your shows,\nwherever you travel", "Reach your own subscriptions on a\nserver back home", 170, 96)
    body, r = device(load(f"{CAP}/home.png"), 0.80)
    place(c, body, r, (IW - body.width) // 2, 900)
    chips = [("Movies", g_film), ("TV", g_tv), ("Streaming", g_play), ("Music", g_music)]
    x, y = 120, 720
    for t, g in chips:
        w, h = chip(c, x, y, t, g, size=40)
        x += w + 26
    save(c, f"{OUT}/iphone/04-streaming.png")

    iphone_device_frame("05-pay-while-on.png", f"{CAP}/ob3.png",
                        "$0 while it's off",
                        "Servers start when you connect and stop\nwhen you're done. Azure bills you directly.",
                        (214, 244, 226), (252, 238, 210))
    iphone_device_frame("06-private.png", f"{CAP}/ob1.png",
                        "Only you hold the keys",
                        "No Leap servers. No one else's servers.\nNothing passes through us.",
                        (206, 236, 230), (224, 222, 250))

    # 07 usage card
    c = background(IW, IH, (252, 236, 206), (210, 236, 250)).convert("RGBA")
    caption(c, "See what you spend", "Hours, data and cost per location.\nNo bandwidth caps from us.", 170, 96)
    cap = load(f"{CAP}/usage.png")
    cd, r = card(cap, (40, 230, 1166, 2622), r_ratio=0.05)
    place(c, cd, r, (IW - cd.width) // 2, 700)
    save(c, f"{OUT}/iphone/07-usage.png")

    # 08 one subscription, iPhone + Mac
    c = background(IW, IH, (210, 240, 226), (214, 226, 252)).convert("RGBA")
    caption(c, "One subscription.\niPhone and Mac.", "Same servers, same settings, both devices", 170, 96)
    mac = load(f"{MCAP}/home.png").convert("RGBA")
    mw = 1200
    mac = mac.resize((mw, int(mac.height * mw / mac.width)), Image.LANCZOS)
    m = Image.new("RGBA", mac.size, (0, 0, 0, 0))
    m.paste(mac, (0, 0), squircle_mask(*mac.size, 24, n=5))
    place(c, m, 24, 60, 760)
    body, r = device(load(f"{CAP}/home.png"), 0.52)
    place(c, body, r, IW - body.width - 70, 1240)
    save(c, f"{OUT}/iphone/08-iphone-and-mac.png")


# --- Mac (2880 x 1800) -------------------------------------------------------
MW, MH = 2880, 1800


def window(cap_path, crop=None, max_w=None, r=28):
    img = load(cap_path).convert("RGBA")
    if crop:
        img = img.crop(crop)
    if max_w and img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)), Image.LANCZOS)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), squircle_mask(*img.size, r, n=5))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, outline=(0, 0, 0, 40), width=2)
    return out, r


def mac_frame(name, head, sub, bloom, bloom2, layers):
    c = background(MW, MH, bloom, bloom2).convert("RGBA")
    caption(c, head, sub, 150, 104)
    for img, r, x, y in layers:
        place(c, img, r, x, y, blur=50, alpha=80)
    save(c, f"{OUT}/mac/{name}")


def mac():
    home, r = window(f"{MCAP}/home.png")
    mac_frame("01-home.png", "Your own VPN. On your own servers.",
              "Leap builds it in your Azure account. Nothing runs while you're off.",
              (200, 238, 220), (210, 228, 250),
              [(home, r, (MW - home.width) // 2, 500)])

    # Settings: crop away the account card (personal email); keep LOCATIONS onward.
    locs, r = window(f"{MCAP}/settings.png", crop=(0, 360, 960, 1280))
    mac_frame("02-locations.png", "40 server locations, your choice of speed",
              "Economy or Turbo per location, ad blocking on the shield",
              (214, 230, 252), (205, 240, 225),
              [(window(f"{MCAP}/home.png", max_w=1640)[0], 28, 200, 520),
               (locs, r, 1680, 470)])

    usage, r = window(f"{MCAP}/usage.png")
    mac_frame("03-usage.png", "Pay only while connected",
              "Azure bills you directly for the hours you use. See every cent here.",
              (252, 236, 206), (210, 236, 250),
              [(usage, r, (MW - usage.width) // 2, 500)])

    # 04 privacy + blocking: home window plus text chips
    c = background(MW, MH, (206, 236, 230), (255, 226, 214)).convert("RGBA")
    caption(c, "Private by design", "No Leap servers, no logs, nothing passes through us.", 150, 104)
    hw, r = window(f"{MCAP}/home.png", max_w=1500)
    place(c, hw, r, 1240, 470, blur=50, alpha=80)
    y = 620
    for t in ["Only you hold the keys", "Servers in your own Azure", "Ads blocked, in apps too",
              "Trackers blocked", "No bandwidth caps from us"]:
        w, h = chip(c, 160, y, t, g_check, size=50)
        y += h + 40
    save(c, f"{OUT}/mac/04-private.png")

    # 05 one subscription
    c = background(MW, MH, (210, 240, 226), (214, 226, 252)).convert("RGBA")
    caption(c, "One subscription. Mac and iPhone.", "Same servers and settings on both", 150, 104)
    hw, r = window(f"{MCAP}/home.png", max_w=1640)
    place(c, hw, r, 300, 470, blur=50, alpha=80)
    body, br = device(load(f"{CAP}/home.png"), 0.46)
    place(c, body, br, 1980, 520)
    save(c, f"{OUT}/mac/05-mac-and-iphone.png")


if __name__ == "__main__":
    iphone()
    mac()
