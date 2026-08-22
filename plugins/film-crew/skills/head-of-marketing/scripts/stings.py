"""Render a channel intro and an outro sting to 1080p MP4.

The outro is not decoration: it is where the subscribe conversion happens.
It animates a cursor to a SUBSCRIBE button, presses it, then springs in the
bell and rings it -- showing the exact gesture you want the viewer to copy.
Keep it free of body copy; competing text pulls attention off the button.

Wordmark, tagline and colours come from the project's publish.json, so any
channel can use this. All type is rasterised through CoreText (ct_text) so
non-Latin scripts shape correctly.
"""
import argparse
import os
import sys
import math
import subprocess
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brand_kit import *  # noqa
import ct_text as ct

OUT = os.path.dirname(os.path.abspath(__file__))
WORDMARK = "CHANNEL"
TAGLINE_TA = ""
SUB_LABEL = "SUBSCRIBE"
SUB_DONE = "SUBSCRIBED"


def configure(project):
    """Point the renderer at a project and adopt its brand."""
    global OUT, WORDMARK, TAGLINE_TA, SUB_LABEL, SUB_DONE
    import _shared  # noqa: F401  (locates config.py in the publisher skill)
    from config import Publish
    pub = Publish(project)
    OUT = pub.p("assets")
    os.makedirs(OUT, exist_ok=True)
    WORDMARK = pub.get("brand", "wordmark", default=WORDMARK) or WORDMARK
    TAGLINE_TA = pub.get("brand", "tagline", default=TAGLINE_TA) or ""
    SUB_LABEL = pub.get("brand", "subscribe_label", default=SUB_LABEL)
    SUB_DONE = pub.get("brand", "subscribed_label", default=SUB_DONE)
    return pub

_cache = {}


def T(text, fontname, size, rgb, tracking=0.0):
    k = (text, fontname, size, rgb, tracking)
    if k not in _cache:
        _cache[k] = ct.render_text(text, fontname, size, rgb, tracking)
    return _cache[k]


def backdrop(t):
    """Deep navy field with a soft breathing core light."""
    img = base_frame(INK)
    g = Image.new("RGB", (W, H), INK)
    gd = ImageDraw.Draw(g)
    pulse = 0.5 + 0.5 * math.sin(t * 1.6)
    r = 470 + pulse * 45
    gd.ellipse([W / 2 - r * 1.75, H / 2 - r, W / 2 + r * 1.75, H / 2 + r], fill=INK_2)
    g = g.filter(ImageFilter.GaussianBlur(130))
    return Image.blend(img, g, 0.9)


def settle_bars(img, t, alpha=1.0):
    """Angled accent bars that fly in and settle into a fixed lock-up."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bars = [
        (-70, 250, CRIMSON, 0.00, 0.95),
        (330, 54, GOLD, 0.08, 0.85),
        (1500, 190, CRIMSON_HI, 0.14, 0.80),
        (1810, 44, GOLD, 0.20, 0.85),
    ]
    for fx, thick, col, delay, ba in bars:
        p = ease_out_expo(seg(t, delay, 0.85))
        if p <= 0.001:
            continue
        x = fx - (1 - p) * 1500
        a = int(255 * alpha * ba)
        d.polygon([(x, H + 220), (x + 470, -220),
                   (x + 470 + thick, -220), (x + thick, H + 220)],
                  fill=col + (a,))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def intro_frame(i, n):
    t = i / FPS
    dur = n / FPS
    img = backdrop(t)
    img = settle_bars(img, t, alpha=0.9)

    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    sp = ease_out_cubic(seg(t, 0.30, 0.5))
    sd.rectangle([0, H / 2 - 260, W, H / 2 + 260], fill=(10, 14, 26, int(160 * sp)))
    scrim = scrim.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    base_y = H / 2 - 40
    letters = [T(ch, ct.LATIN_HEAVY, 140, (247, 245, 240, 255)) for ch in WORDMARK]
    track = 10
    total_w = sum(l.width for l in letters) + track * (len(letters) - 1)
    x = (W - total_w) / 2
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for idx, gimg in enumerate(letters):
        p = ease_out_back(seg(t, 0.42 + idx * 0.032, 0.5))
        if p > 0.001:
            dy = (1 - p) * 95
            a = clamp(p * 1.5)
            g2 = gimg.copy()
            g2.putalpha(g2.split()[3].point(lambda v, _a=a: int(v * _a)))
            lay.paste(g2, (int(x), int(base_y - gimg.height / 2 + dy)), g2)
        x += gimg.width + track
    img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")

    rp = ease_out_expo(seg(t, 1.12, 0.55))
    if rp > 0:
        d = ImageDraw.Draw(img)
        rw = total_w * rp
        rounded_bar(d, W / 2 - rw / 2, base_y + 100, rw, 9, GOLD, r=4)

    tp = ease_out_cubic(seg(t, 1.5, 0.65))
    if tp > 0:
        tag = T(TAGLINE_TA, ct.TAMIL_BOLD, 54, (245, 194, 78, 255))
        img = ct.paste_center(img, tag, W / 2, base_y + 195 + (1 - tp) * 24, alpha=tp)

    img = vignette(img, 0.5)

    fl = seg(t, dur - 0.30, 0.30)
    if fl > 0:
        img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)),
                          ease_in_out_cubic(fl) * 0.9)
    return img


def bell_icon(size, color, clapper_swing=0.0):
    """Vector notification bell drawn to an RGBA tile of side `size`."""
    S = size
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    cx = S / 2
    top = S * 0.17
    bw = S * 0.52
    body_top = top + bw / 2
    base_y = S * 0.70

    d.ellipse([cx - S * 0.052, top - S * 0.10, cx + S * 0.052, top + S * 0.005],
              fill=color)
    d.pieslice([cx - bw / 2, top, cx + bw / 2, top + bw], 180, 360, fill=color)
    d.polygon([(cx - bw / 2, body_top), (cx + bw / 2, body_top),
               (cx + S * 0.39, base_y), (cx - S * 0.39, base_y)], fill=color)
    d.rounded_rectangle([cx - S * 0.43, base_y - S * 0.025,
                         cx + S * 0.43, base_y + S * 0.055],
                        radius=S * 0.035, fill=color)
    # the clapper lags behind the body, which sells the ring
    d.ellipse([cx - S * 0.078 + clapper_swing, base_y + S * 0.07,
               cx + S * 0.078 + clapper_swing, base_y + S * 0.225], fill=color)
    return tile


def ring_waves(img, cx, cy, size, p, color=GOLD):
    """Two arc pairs flying out of the bell as it rings."""
    if p <= 0:
        return img
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for k in range(2):
        q = clamp(p * 1.35 - k * 0.28)
        if q <= 0 or q >= 1:
            continue
        r = size * (0.62 + q * 0.55)
        a = int(210 * (1 - q))
        box = [cx - r, cy - r, cx + r, cy + r]
        d.arc(box, 205, 250, fill=color + (a,), width=max(3, int(size * 0.045)))
        d.arc(box, 290, 335, fill=color + (a,), width=max(3, int(size * 0.045)))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def click_ripple(img, cx, cy, p, color=PAPER):
    """Expanding ring at the click point."""
    if p <= 0 or p >= 1:
        return img
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = 34 + p * 132
    a = int(200 * (1 - p))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color + (a,), width=6)
    layer = layer.filter(ImageFilter.GaussianBlur(1.5))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def cursor(img, x, y, scale=1.0, alpha=1.0):
    """Classic arrow pointer with its tip at (x, y)."""
    if alpha <= 0:
        return img
    pts = [(0, 0), (0, 25), (6.4, 18.8), (10.6, 28.2),
           (15.0, 26.2), (10.9, 17.0), (18.4, 16.4)]
    s = 2.05 * scale
    poly = [(x + px * s, y + py * s) for px, py in pts]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sh = [(px + 5, py + 6) for px, py in poly]
    d.polygon(sh, fill=(0, 0, 0, int(120 * alpha)))
    layer = layer.filter(ImageFilter.GaussianBlur(5))
    d = ImageDraw.Draw(layer)
    d.polygon(poly, fill=(255, 255, 255, int(255 * alpha)),
              outline=(12, 16, 28, int(255 * alpha)))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def outro_frame(i, n):
    """Wordmark, then a cursor presses Subscribe and rings the bell.

    Deliberately carries no caption text under the button -- the interaction
    itself is the call to action.
    """
    t = i / FPS
    dur = n / FPS
    img = backdrop(t)
    img = settle_bars(img, t, alpha=0.5)

    # --- timeline ---------------------------------------------------------
    T_BTN, T_MOVE1, T_CLICK1 = 0.70, 1.30, 1.95
    T_BELL, T_MOVE2, T_CLICK2 = 2.30, 2.80, 3.40

    p = ease_out_back(seg(t, 0.12, 0.55))
    mark = T(WORDMARK, ct.LATIN_HEAVY, 92, (247, 245, 240, 255), tracking=8)
    if p > 0:
        img = ct.paste_center(img, mark, W / 2, 262 + (1 - p) * 42, alpha=clamp(p * 1.4))
        rp = ease_out_expo(seg(t, 0.48, 0.5))
        if rp > 0:
            d = ImageDraw.Draw(img)
            rw = mark.width * rp
            rounded_bar(d, W / 2 - rw / 2, 322, rw, 7, GOLD, r=3)

    # --- geometry: button and bell share one centred lock-up ---------------
    lab_sub = T(SUB_LABEL, ct.LATIN_HEAVY, 56, (247, 245, 240, 255), tracking=4)
    lab_done = T(SUB_DONE, ct.LATIN_HEAVY, 52, (176, 186, 208, 255), tracking=4)
    ph = 116
    pw = max(lab_sub.width, lab_done.width) + 150
    bell_s = 132
    gap = 44
    group_w = pw + gap + bell_s
    btn_cx = W / 2 - group_w / 2 + pw / 2
    bell_cx = W / 2 + group_w / 2 - bell_s / 2
    cy = H / 2 + 96

    clicked1 = t >= T_CLICK1
    press1 = 1.0 - 0.075 * math.sin(math.pi * clamp((t - T_CLICK1) / 0.20)) \
        if T_CLICK1 <= t < T_CLICK1 + 0.20 else 1.0

    sp = ease_out_back(seg(t, T_BTN, 0.6))
    if sp > 0:
        breathe = 1.0 if clicked1 else 1.0 + 0.03 * math.sin((t - T_BTN) * 5.0)
        s = sp * breathe
        pw_s, ph_s = pw * s, ph * s * press1
        fill = (44, 52, 72) if clicked1 else CRIMSON

        if not clicked1:
            halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            hd = ImageDraw.Draw(halo)
            hd.rounded_rectangle([btn_cx - pw_s / 2 - 18, cy - ph_s / 2 - 18,
                                  btn_cx + pw_s / 2 + 18, cy + ph_s / 2 + 18],
                                 radius=(ph_s + 36) / 2, fill=CRIMSON + (140,))
            halo = halo.filter(ImageFilter.GaussianBlur(30))
            img = Image.alpha_composite(img.convert("RGBA"), halo).convert("RGB")

        d = ImageDraw.Draw(img)
        d.rounded_rectangle([btn_cx - pw_s / 2, cy - ph_s / 2,
                             btn_cx + pw_s / 2, cy + ph_s / 2],
                            radius=ph_s / 2, fill=fill)
        if sp > 0.9:
            img = ct.paste_center(img, lab_done if clicked1 else lab_sub, btn_cx, cy)

    img = click_ripple(img, btn_cx, cy, seg(t, T_CLICK1, 0.55))

    # --- bell -------------------------------------------------------------
    bp = ease_out_back(seg(t, T_BELL, 0.55))
    if bp > 0:
        clicked2 = t >= T_CLICK2
        press2 = 1.0 - 0.09 * math.sin(math.pi * clamp((t - T_CLICK2) / 0.20)) \
            if T_CLICK2 <= t < T_CLICK2 + 0.20 else 1.0
        # damped oscillation after the click reads as a ring
        ring = clamp((t - T_CLICK2) / 1.05) if clicked2 else 0.0
        ang = 0.0
        swing = 0.0
        if 0 < ring < 1:
            decay = math.exp(-4.2 * ring)
            ang = 15.0 * decay * math.sin(ring * 26.0)
            swing = bell_s * 0.055 * decay * math.sin(ring * 26.0 - 0.7)

        s = bp * press2
        size = int(bell_s * s)
        if size > 4:
            col = GOLD if clicked2 else (214, 221, 236)
            tile = bell_icon(size, col, clapper_swing=swing * s)
            if abs(ang) > 0.01:
                tile = tile.rotate(ang, resample=Image.BICUBIC,
                                   center=(size / 2, size * 0.10))
            img.paste(tile, (int(bell_cx - size / 2), int(cy - size / 2)), tile)
        if clicked2:
            img = ring_waves(img, bell_cx, cy, bell_s, ring)

    img = click_ripple(img, bell_cx, cy, seg(t, T_CLICK2, 0.55))

    # --- cursor: glide to the button, click, glide to the bell, click ------
    cur_a = clamp(seg(t, T_MOVE1 - 0.18, 0.25) - seg(t, dur - 0.85, 0.35))
    if cur_a > 0:
        start = (W / 2 + 430, H - 90)
        m1 = ease_in_out_cubic(seg(t, T_MOVE1, 0.62))
        cxp = start[0] + (btn_cx + 18 - start[0]) * m1
        cyp = start[1] + (cy + 14 - start[1]) * m1
        m2 = ease_in_out_cubic(seg(t, T_MOVE2, 0.55))
        if m2 > 0:
            cxp += (bell_cx + 10 - (btn_cx + 18)) * m2
            cyp += (cy + 12 - (cy + 14)) * m2
        nudge = 1.0
        for tc in (T_CLICK1, T_CLICK2):
            if tc <= t < tc + 0.18:
                nudge = 1.0 - 0.16 * math.sin(math.pi * ((t - tc) / 0.18))
        img = cursor(img, cxp, cyp, scale=nudge, alpha=cur_a)

    img = vignette(img, 0.5)
    fade = seg(t, dur - 0.55, 0.55)
    if fade > 0:
        img = Image.blend(img, Image.new("RGB", (W, H), INK), ease_in_out_cubic(fade))
    return img


def render(name, fn, seconds):
    n = int(seconds * FPS)
    d = os.path.join(OUT, f"_frames_{name}")
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        fn(i, n).save(os.path.join(d, f"{i:05d}.png"))
        if i % 25 == 0:
            print(f"  {name} {i}/{n}", flush=True)
    mp4 = os.path.join(OUT, f"{name}.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
        "-i", os.path.join(d, "%05d.png"),
        "-s", "1920x1080", "-c:v", "libx264", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow", mp4], check=True)
    subprocess.run(["rm", "-rf", d], check=True)
    print("wrote", mp4, flush=True)
    return mp4


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render channel intro/outro stings")
    ap.add_argument("project", help="directory containing publish.json")
    ap.add_argument("--which", default="all",
                    choices=["all", "intro", "outro"])
    ap.add_argument("--intro-seconds", type=float, default=4.0)
    ap.add_argument("--outro-seconds", type=float, default=5.4)
    a = ap.parse_args()
    configure(a.project)
    if a.which in ("all", "intro"):
        render("intro", intro_frame, a.intro_seconds)
    if a.which in ("all", "outro"):
        render("outro", outro_frame, a.outro_seconds)
