#!/usr/bin/env python3
"""Generate a synthetic product demo recording for testing the product-launch skill.

Renders a fake "Acme Notes" desktop app with Pillow and pipes raw frames to ffmpeg.
100% cross-platform (no macOS APIs) — works anywhere ffmpeg + Pillow are installed.

  python3 make_sample_demo.py --output sample_demo.mp4 [--ffmpeg /path/to/ffmpeg]

The demo has clear feature "beats" you can caption:
  ~2-10s  adding notes      ~11s  checking one off      ~14-18s  search / filter
"""
from __future__ import annotations
import argparse
import math
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, DUR = 1920, 1080, 30, 21.0
ACCENT = (59, 130, 246)          # blue
GREEN = (34, 197, 94)
INK = (28, 33, 48)
GRAY = (148, 158, 178)
FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

NOTES = [
    {"text": "Buy groceries",      "type": (2.0, 3.4), "add": 3.7, "tag": ACCENT},
    {"text": "Finish the report",  "type": (4.8, 6.4), "add": 6.7, "tag": (245, 158, 11)},
    {"text": "Call the dentist",   "type": (7.6, 9.0), "add": 9.3, "tag": (236, 72, 153)},
]
CHECK_AT = 11.0
SEARCH_TYPE = (13.8, 15.0)
SEARCH_QUERY = "report"
FILTER_ON, FILTER_OFF = 15.2, 18.2

WIN = (160, 110, 1760, 970)
LIST_TOP, ITEM_GAP = 396, 96


def _font(size, bold=False):
    for name in ([f"Inter-{'Bold' if bold else 'Regular'}.ttf"]):
        p = os.path.join(FONTS, name)
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                try:
                    f.set_variation_by_axes([700 if bold else 400])
                except Exception:
                    pass
                return f
            except Exception:
                pass
    return ImageFont.load_default()


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def rrect(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def typed(text, t, start, end):
    if t < start:
        return ""
    if t >= end:
        return text
    return text[:int(len(text) * (t - start) / (end - start) + 0.5)]


def cursor_pos(t):
    way = [
        (0.0, 1500, 760), (1.6, 360, 315), (3.7, 360, 315),
        (4.4, 360, 315), (6.7, 360, 315), (7.2, 360, 315), (9.3, 360, 315),
        (10.4, 250, LIST_TOP + 40), (11.6, 250, LIST_TOP + 40),
        (13.2, 1600, 220), (15.0, 1600, 220), (18.6, 1500, 760), (21.0, 1500, 760),
    ]
    for i in range(len(way) - 1):
        t0, x0, y0 = way[i]
        t1, x1, y1 = way[i + 1]
        if t < t1:
            p = smooth((t - t0) / max(1e-6, t1 - t0)) if t > t0 else 0.0
            return (lerp(x0, x1, p), lerp(y0, y1, p))
    return way[-1][1], way[-1][2]


def draw_cursor(img, x, y):
    d = ImageDraw.Draw(img)
    pts = [(x, y), (x, y + 34), (x + 9, y + 25), (x + 15, y + 38),
           (x + 21, y + 35), (x + 15, y + 22), (x + 26, y + 22)]
    d.polygon(pts, fill=(20, 24, 36), outline=(255, 255, 255))
    d.line(pts + [pts[0]], fill=(255, 255, 255), width=2)


def compose_text(t):
    for n in NOTES:
        if n["type"][0] <= t < n["add"]:
            return typed(n["text"], t, n["type"][0], n["type"][1]), True
    return "Add a note\u2026", False


def visible_items(t):
    items = []
    q = typed(SEARCH_QUERY, t, *SEARCH_TYPE).lower()
    filtering = FILTER_ON <= t < FILTER_OFF and q
    for i, n in enumerate(NOTES):
        if t < n["add"] - 0.0:
            continue
        if filtering and q not in n["text"].lower():
            continue
        items.append((i, n))
    return items, filtering


def draw_frame(t, fonts):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    # desktop gradient
    top, bot = (228, 233, 245), (205, 214, 232)
    px = img.load()
    for yy in range(0, H, 4):
        c = tuple(int(lerp(top[k], bot[k], yy / H)) for k in range(3))
        ImageDraw.Draw(img).rectangle([0, yy, W, yy + 4], fill=c)
    d = ImageDraw.Draw(img)

    # window shadow + card
    rrect(d, [WIN[0] + 6, WIN[1] + 18, WIN[2] + 6, WIN[3] + 18], 28, fill=(170, 178, 196))
    rrect(d, list(WIN), 28, fill=(255, 255, 255))
    # title bar
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = WIN[0] + 44 + i * 34
        d.ellipse([cx, WIN[1] + 30, cx + 20, WIN[1] + 50], fill=c)
    title = "Acme Notes"
    f_title = fonts["title"]
    tw = d.textbbox((0, 0), title, font=f_title)[2]
    d.text(((W - tw) / 2, WIN[1] + 26), title, font=f_title, fill=INK)
    d.line([WIN[0], WIN[1] + 78, WIN[2], WIN[1] + 78], fill=(232, 236, 244), width=2)

    # search field (top-right)
    sb = [WIN[2] - 360, WIN[1] + 96, WIN[2] - 40, WIN[1] + 150]
    focus_s = FILTER_ON - 1.4 <= t < FILTER_OFF
    rrect(d, sb, 27, fill=(242, 245, 250), outline=ACCENT if focus_s else (228, 232, 240), width=3 if focus_s else 2)
    d.ellipse([sb[0] + 18, sb[1] + 16, sb[0] + 40, sb[1] + 38], outline=GRAY, width=3)
    d.line([sb[0] + 37, sb[1] + 35, sb[0] + 46, sb[1] + 44], fill=GRAY, width=3)
    sq = typed(SEARCH_QUERY, t, *SEARCH_TYPE) if t < FILTER_OFF else ""
    d.text((sb[0] + 60, sb[1] + 13), sq or "Search", font=fonts["body"],
           fill=INK if sq else GRAY)

    # compose row
    cb = [WIN[0] + 40, WIN[1] + 168, WIN[2] - 240, WIN[1] + 240]
    ctext, focused = compose_text(t)
    rrect(d, cb, 18, fill=(248, 250, 253), outline=ACCENT if focused else (228, 232, 240), width=3 if focused else 2)
    caret = "|" if focused and int(t * 2) % 2 == 0 else ""
    d.text((cb[0] + 26, cb[1] + 16), (ctext + caret) if focused else ctext,
           font=fonts["body"], fill=INK if focused else GRAY)
    addb = [WIN[2] - 216, WIN[1] + 168, WIN[2] - 40, WIN[1] + 240]
    pressed = any(abs(t - n["add"]) < 0.18 for n in NOTES)
    rrect(d, addb, 18, fill=tuple(int(c * (0.8 if pressed else 1)) for c in ACCENT))
    d.text((addb[0] + 54, addb[1] + 16), "+ Add", font=fonts["bodyb"], fill=(255, 255, 255))

    # list
    items, filtering = visible_items(t)
    for slot, (i, n) in enumerate(items):
        y = LIST_TOP + slot * ITEM_GAP
        ap = smooth((t - n["add"]) / 0.4)
        dx = int((1 - ap) * 50)
        row = [WIN[0] + 40 + dx, y, WIN[2] - 40, y + 78]
        rrect(d, row, 16, fill=(249, 250, 252))
        checked = i == 0 and t >= CHECK_AT
        cp = smooth((t - CHECK_AT) / 0.5) if checked else 0.0
        cx, cy = WIN[0] + 84 + dx, y + 39
        if cp > 0:
            d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=tuple(int(lerp(255, GREEN[k], cp)) for k in range(3)))
            if cp > 0.4:
                d.line([cx - 10, cy + 1, cx - 2, cy + 10], fill=(255, 255, 255), width=4)
                d.line([cx - 2, cy + 10, cx + 12, cy - 8], fill=(255, 255, 255), width=4)
        else:
            d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], outline=GRAY, width=3)
        tcol = GRAY if checked else INK
        d.text((WIN[0] + 130 + dx, y + 20), n["text"], font=fonts["body"], fill=tcol)
        if checked and cp > 0.5:
            bb = d.textbbox((WIN[0] + 130 + dx, y + 20), n["text"], font=fonts["body"])
            d.line([bb[0], (bb[1] + bb[3]) // 2, bb[0] + int((bb[2] - bb[0]) * min(1, (cp - 0.5) * 2)), (bb[1] + bb[3]) // 2], fill=GRAY, width=3)
        d.ellipse([WIN[2] - 96, cy - 12, WIN[2] - 72, cy + 12], fill=n["tag"])

    if filtering:
        d.text((WIN[0] + 44, LIST_TOP + len(items) * ITEM_GAP + 12),
               f"Filtered by \u201c{SEARCH_QUERY}\u201d", font=fonts["small"], fill=GRAY)

    cxp, cyp = cursor_pos(t)
    draw_cursor(img, int(cxp), int(cyp))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="sample_demo.mp4")
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    args = ap.parse_args()

    fonts = {"title": _font(40, True), "body": _font(38), "bodyb": _font(36, True),
             "small": _font(30)}
    frames = int(DUR * FPS)
    cmd = [args.ffmpeg, "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
           "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "pipe:0",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-preset", "veryfast", "-movflags", "+faststart", args.output]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    step = max(1, frames // 10)
    try:
        for i in range(frames):
            proc.stdin.write(draw_frame(i / FPS, fonts).tobytes())
            if i % step == 0:
                print(f"  demo {int(100*i/frames):3d}%", end="\r", flush=True)
    except BrokenPipeError:
        pass
    proc.stdin.close()
    err = proc.stderr.read().decode(errors="ignore")
    proc.wait()
    print("  demo 100%      ")
    if proc.returncode != 0 or not os.path.exists(args.output):
        sys.exit("ffmpeg failed:\n" + err[-1200:])
    print(f"DONE -> {args.output}  ({DUR:.0f}s, {W}x{H}, {FPS}fps)")


if __name__ == "__main__":
    main()
