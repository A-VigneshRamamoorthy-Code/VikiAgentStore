"""Generate a 1280x720 thumbnail in the news-debate style.

Driven entirely by `meta/thumbnail.json` in a publish project, so the layout is
reusable for any channel and any language. Layout:

    +--------------------------------------------------+
    |  RED BAND: two lines of heavy Tamil, white on red |  ~36%
    +--------------------------------------------------+
    |                                                  |
    |  live frame from the session, punchy grade        |  ~64%
    |          (optional) lightning + VS burst          |
    |                                        [BRAND]    |
    +--------------------------------------------------+

Why this beats the previous side-scrim design: at the 168px-wide search
thumbnail the headline still occupies a third of the area and never overlaps a
face, and the red band is the single strongest colour signal in a YouTube feed.
"""
import argparse
import json
import math
import os
import sys
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "brand"))
import ct_text as ct  # noqa: E402

TW, TH = 1280, 720
BAND_H = 262
RED_TOP = (168, 16, 24)
RED_BOT = (198, 24, 30)
GOLD = (255, 205, 60)
BOLT = (255, 214, 40)
WHITE = (255, 255, 255)
INK = (8, 10, 18)

# --- news style -----------------------------------------------------------
# A stacked lower third over a full-bleed frame: a light bar carrying the
# spoken quote, a red bar under it carrying the plain-language gloss. The
# quote is the thing people react to, so it gets the calm high-contrast bar
# rather than being reversed out of red.
PAPER = (238, 236, 232)
NEWS_RED = (183, 15, 26)
TAG_GREY = (104, 104, 104)
NEWS_INK = (17, 17, 17)


def _outline(img, timg, cx, cy, width=6, colour=(0, 0, 0, 255)):
    """Paste `timg` centred at (cx, cy) with a hard outline.

    CoreText gives no stroke, so the outline is built from the glyph alpha:
    the mask is stamped in a ring of offsets, then the fill goes on top. A
    hard outline (not a blur) is what makes Tamil headlines survive the
    thumbnail downscale.
    """
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    solid = Image.new("RGBA", timg.size, colour)
    x0, y0 = int(cx - timg.width / 2), int(cy - timg.height / 2)
    for a in range(0, 360, 30):
        dx = int(round(math.cos(math.radians(a)) * width))
        dy = int(round(math.sin(math.radians(a)) * width))
        layer.paste(solid, (x0 + dx, y0 + dy), timg)
    layer.paste(timg, (x0, y0), timg)
    return Image.alpha_composite(img.convert("RGBA"), layer)


def _fit(text, max_w, start, minimum=44, colour=WHITE + (255,)):
    size = start
    while size > minimum:
        t = ct.render_text(text, ct.TAMIL_BOLD, size, colour)
        if t.width <= max_w:
            return t, size
        size -= 3
    return ct.render_text(text, ct.TAMIL_BOLD, minimum, colour), minimum


def _line_with_vs(text, max_w, start, gap=22):
    """Render a line, colouring a standalone 'VS' gold.

    CoreText trims leading/trailing whitespace per segment, so the spacing
    either side of the VS has to be added in pixels rather than as spaces.
    Returns a single RGBA strip so the caller can centre it as one unit.
    """
    parts = [p for p in text.replace(" VS ", "\x00VS\x00").split("\x00") if p]
    if len(parts) == 1:
        return _fit(text, max_w, start)

    size = start
    while size > 44:
        segs = [ct.render_text(p.strip(), ct.TAMIL_BOLD, size,
                               (GOLD + (255,)) if p == "VS" else WHITE + (255,))
                for p in parts]
        w = sum(s.width for s in segs) + gap * (len(segs) - 1)
        if w <= max_w:
            break
        size -= 3
    h = max(s.height for s in segs)
    strip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for i, s in enumerate(segs):
        strip.paste(s, (x, (h - s.height) // 2), s)
        x += s.width + (gap if i < len(segs) - 1 else 0)
    return strip, size


def _bolt(draw, cx, cy, h, colour=BOLT):
    """A chunky lightning bolt, as flanks the VS burst in the reference."""
    u = h / 10.0
    pts = [(cx + 0.6 * u, cy - 5 * u), (cx - 2.2 * u, cy + 0.6 * u),
           (cx - 0.3 * u, cy + 0.6 * u), (cx - 1.5 * u, cy + 5 * u),
           (cx + 2.4 * u, cy - 0.9 * u), (cx + 0.4 * u, cy - 0.9 * u)]
    draw.polygon([(x + 4, y + 5) for x, y in pts], fill=(0, 0, 0, 150))
    draw.polygon(pts, fill=colour + (255,), outline=(120, 60, 0, 255))


def _vs_burst(img, cx, cy, r=86):
    """Red spiked starburst with a white 'VS'."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for ring, col in ((r * 1.16, (255, 255, 255, 255)),
                      (r, (206, 22, 30, 255))):
        pts = []
        for i in range(28):
            a = math.radians(i * (360 / 28))
            rr = ring if i % 2 == 0 else ring * 0.72
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        d.polygon(pts, fill=col)
    out = Image.alpha_composite(img.convert("RGBA"), layer)
    vs = ct.render_text("VS", ct.LATIN_HEAVY, 74, WHITE + (255,), tracking=1)
    return _outline(out, vs, cx, cy + 2, width=4, colour=(90, 0, 6, 255))


def duo(left_path, right_path, w, h, seam=6):
    """Split stage: two stills from the same exchange, left and right.

    The reference thumbnail works because two faces are visible arguing. When
    a single frame does not contain both sides, two frames from the same
    exchange are paired instead -- honest, because both speakers really are in
    that clip -- with a gold seam so the split reads as deliberate.
    """
    half = (w - seam) // 2
    stage = Image.new("RGB", (w, h), INK)
    for i, p in enumerate((left_path, right_path)):
        im = Image.open(p).convert("RGB")
        s = max(half / im.width, h / im.height)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        # bias the crop toward the outer edge so faces sit away from the seam
        fx = 0.34 if i == 0 else 0.66
        x = int((im.width - half) * fx)
        y = int((im.height - h) * 0.30)
        stage.paste(im.crop((x, y, x + half, y + h)), (0 if i == 0 else half + seam, 0))
    ImageDraw.Draw(stage).rectangle([half, 0, half + seam, h], fill=GOLD)
    return stage


def _grade(im):
    im = ImageEnhance.Color(im).enhance(1.30)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Brightness(im).enhance(1.05)
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=115))


def _fill_frame(bg_path, w, h, focus=0.34):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        s = max(w / bg.width, h / bg.height)
        bg = bg.resize((int(bg.width * s), int(bg.height * s)), Image.LANCZOS)
        x = (bg.width - w) // 2
        y = int((bg.height - h) * focus)
        return _grade(bg.crop((x, y, x + w, y + h)))
    return Image.new("RGB", (w, h), INK)


def _fit_font(text, font, max_w, start, minimum, colour, tracking=0.0):
    size = start
    while size > minimum:
        t = ct.render_text(text, font, size, colour, tracking=tracking)
        if t.width <= max_w:
            return t, size
        size -= 3
    return ct.render_text(text, font, minimum, colour, tracking=tracking), minimum


def _face_boxes(img):
    """Face rectangles in the *final* frame's coordinates, best effort.

    Returned in the coordinates of the image passed in, so the caller must
    detect on the already-cropped frame rather than on the source still --
    otherwise the boxes point at the wrong part of the picture.

    Detection is optional. insightface is used when the project already has it
    (it is far steadier on the wide chamber shots than a cascade), OpenCV's
    bundled cascade is the fallback, and an empty list is a legitimate answer
    that simply restores the fixed-position behaviour.
    """
    import numpy as np
    arr = np.asarray(img.convert("RGB"))
    try:
        from insightface.app import FaceAnalysis
        global _FA
        try:
            app = _FA
        except NameError:
            app = None
        if app is None:
            app = FaceAnalysis(name="buffalo_l",
                               allowed_modules=["detection"],
                               providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            _FA = app
        return [tuple(int(v) for v in f.bbox)
                for f in app.get(arr[:, :, ::-1])]
    except Exception:
        pass
    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        found = cascade.detectMultiScale(grey, 1.1, 5, minSize=(60, 60))
        return [(int(x), int(y), int(x + w), int(y + h))
                for x, y, w, h in found]
    except Exception:
        return []


def _place_block(img, height, block, reserve_bottom):
    """Top edge for the text block that keeps the speaker's face uncovered.

    The rule is that the block goes *above or below* the face, never across it.
    Below is preferred -- that is where a broadcast lower-third belongs -- and
    the top of frame is the fallback for a speaker who sits low.

    Only faces big enough to matter are considered. A chamber wide shot holds
    twenty-odd heads, and respecting every one of them leaves nowhere to put
    the block; anything under a third of the tallest is background.

    The ordering matters. An earlier version fell straight from "clears every
    face" to a midline compromise that covered faces deliberately, so missing
    the ideal position by two pixels put the bar across the speaker's eyes --
    the exact failure this function exists to prevent. Clearing the *subject*
    is therefore tried, top and bottom, before any overlap is accepted.
    """
    boxes = _face_boxes(img)
    limit = TH - reserve_bottom - height
    if not boxes:
        return max(20, min(int(TH * block), limit))

    tallest = max(b[3] - b[1] for b in boxes)
    big = [b for b in boxes if (b[3] - b[1]) >= tallest * 0.34]
    subject = max(big, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    gap = 12

    below_all = max(b[3] for b in big) + gap
    if below_all <= limit:
        return below_all
    if limit >= subject[3] + gap:
        return limit
    above_all = min(b[1] for b in big) - gap - height
    if above_all >= 20:
        return above_all
    above_subject = subject[1] - gap - height
    if above_subject >= 20:
        return above_subject
    return max(20, limit)


def build_news(bg_path, line1, line2, kicker, out_path, badge="", block=0.40):
    """The broadcast lower-third style: quote on paper, gloss on red.

    Full-bleed frame rather than a letterboxed stage, because the face is the
    reason anyone clicks -- and for the same reason the block is positioned
    against the detected face rather than at a fixed height. A fixed offset
    landed squarely across the speaker's eyes on the first batch of episodes,
    which is exactly the shot the thumbnail exists to show. `block` is now only
    the fallback used when no face is found.
    """
    img = _fill_frame(bg_path, TW, TH, focus=0.26).convert("RGBA")

    pad_x, pad_y = 34, 20
    max_w = TW - pad_x * 2 - 20
    t1, _ = _fit_font(line1, ct.TAMIL_BOLD, max_w, 78, 40, NEWS_INK + (255,))
    t2 = None
    if line2:
        t2, _ = _fit_font(line2, ct.TAMIL_BOLD, max_w, 62, 32, WHITE + (255,))

    h1 = t1.height + pad_y * 2
    h2 = (t2.height + pad_y * 2) if t2 is not None else 0
    # the wordmark and region tag own the bottom strip; the block must clear it
    reserve = 30 + 54 + 10 if (badge or kicker) else 34
    top = _place_block(img, h1 + h2, block, reserve)

    # the paper bar is very slightly translucent, as in the reference, so the
    # frame still reads through it and the card does not look pasted on
    layer = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([0, top, TW, top + h1], fill=PAPER + (243,))
    if t2 is not None:
        ImageDraw.Draw(layer).rectangle(
            [0, top + h1, TW, top + h1 + h2], fill=NEWS_RED + (255,))
    img = Image.alpha_composite(img, layer)

    img = ct.paste_center(img, t1, pad_x + t1.width / 2, top + h1 / 2)
    if t2 is not None:
        img = ct.paste_center(img, t2, pad_x + t2.width / 2,
                              top + h1 + h2 / 2)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)

    # --- channel wordmark, bottom left ------------------------------------
    if badge:
        bt = ct.render_text(badge, ct.LATIN_HEAVY, 34, NEWS_INK + (255,),
                            tracking=2)
        bw, bh = bt.width + 34, bt.height + 20
        d.rectangle([30, TH - 30 - bh, 30 + bw, TH - 30], fill=WHITE)
        img = ct.paste_center(img, bt, 30 + bw / 2, TH - 30 - bh / 2)

    # --- region tag, bottom right -----------------------------------------
    if kicker:
        kt = ct.render_text(kicker, ct.TAMIL_BOLD, 38, WHITE + (255,))
        kw, kh = kt.width + 36, kt.height + 18
        layer = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rectangle(
            [TW - 30 - kw, TH - 30 - kh, TW - 30, TH - 30],
            fill=TAG_GREY + (232,))
        img = Image.alpha_composite(img.convert("RGBA"), layer)
        img = ct.paste_center(img, kt, TW - 30 - kw / 2, TH - 30 - kh / 2)
        img = img.convert("RGB")

    img.save(out_path, quality=94)
    print("thumbnail:", out_path, img.size,
          f"{os.path.getsize(out_path)/1024:.0f} KB")
    return out_path


def build(bg_path, line1, line2, kicker, out_path,
          badge="", vs=True, bg_right=None):
    # --- live frame, bottom two thirds ------------------------------------
    stage_h = TH - BAND_H
    if bg_right and os.path.exists(bg_right) and os.path.exists(bg_path or ""):
        bg = _grade(duo(bg_path, bg_right, TW, stage_h))
    elif bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        s = max(TW / bg.width, stage_h / bg.height)
        bg = bg.resize((int(bg.width * s), int(bg.height * s)), Image.LANCZOS)
        x = (bg.width - TW) // 2
        y = int((bg.height - stage_h) * 0.34)
        bg = _grade(bg.crop((x, y, x + TW, y + stage_h)))
    else:
        bg = Image.new("RGB", (TW, stage_h), INK)

    img = Image.new("RGB", (TW, TH), INK)
    img.paste(bg, (0, BAND_H))

    # --- red headline band -------------------------------------------------
    d = ImageDraw.Draw(img)
    for i in range(BAND_H):
        k = i / BAND_H
        d.line([(0, i), (TW, i)],
               fill=tuple(int(a + (b - a) * k) for a, b in zip(RED_TOP, RED_BOT)))
    d.rectangle([0, BAND_H - 7, TW, BAND_H - 1], fill=GOLD)
    d.rectangle([0, BAND_H - 1, TW, BAND_H + 3], fill=INK)

    max_w = TW - 150
    t1, s1 = _fit(line1, max_w, 96)
    t2, s2 = _line_with_vs(line2, max_w, 92) if line2 else (None, 0)

    if t2 is not None:
        y1 = int(BAND_H * 0.30)
        y2 = int(BAND_H * 0.71)
    else:
        y1, y2 = BAND_H // 2, 0
    img = _outline(img, t1, TW / 2, y1, width=7)
    if t2 is not None:
        img = _outline(img, t2, TW / 2, y2, width=7)
    img = img.convert("RGB")

    # --- confrontation graphic --------------------------------------------
    if vs:
        cy = BAND_H + stage_h * 0.52
        layer = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        bd = ImageDraw.Draw(layer)
        _bolt(bd, TW / 2 - 148, cy - 26, 168)
        _bolt(bd, TW / 2 + 148, cy + 22, 168)
        img = Image.alpha_composite(img.convert("RGBA"), layer)
        img = _vs_burst(img, TW / 2, cy).convert("RGB")

    # --- kicker + channel badge -------------------------------------------
    d = ImageDraw.Draw(img)
    if kicker:
        kt = ct.render_text(kicker, ct.TAMIL_BOLD, 34, (12, 14, 22, 255))
        cw, ch = kt.width + 44, kt.height + 22
        d.rounded_rectangle([28, BAND_H + 20, 28 + cw, BAND_H + 20 + ch],
                            radius=ch // 2, fill=GOLD)
        img = ct.paste_center(img, kt, 28 + cw / 2, BAND_H + 20 + ch / 2)

    bt = ct.render_text(badge, ct.LATIN_HEAVY, 30, (255, 255, 255, 255),
                        tracking=4)
    bw, bh = bt.width + 46, bt.height + 24
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([TW - 28 - bw, TH - 26 - bh, TW - 28, TH - 26],
                        radius=bh // 2, fill=(206, 22, 30))
    img = ct.paste_center(img, bt, TW - 28 - bw / 2, TH - 26 - bh / 2)

    img.save(out_path, quality=94)
    print("thumbnail:", out_path, img.size,
          f"{os.path.getsize(out_path)/1024:.0f} KB")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Render a 1280x720 thumbnail")
    ap.add_argument("project", help="directory containing publish.json")
    ap.add_argument("--spec", default=None,
                    help="defaults to <project>/meta/thumbnail.json")
    a = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _shared  # noqa: F401  (locates config.py in the publisher skill)
    from config import Publish
    pub = Publish(a.project)
    spec_path = a.spec or pub.p("meta", "thumbnail.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"missing {spec_path}")
    spec = json.load(open(spec_path))

    rel = lambda p: pub.p(p) if p else p  # noqa: E731
    badge = spec.get("badge") or pub.get("brand", "wordmark", default="")
    # `news` is the house style; the VS treatment is opt-in per thumbnail.
    style = spec.get("style") or ("vs" if spec.get("vs") else "news")
    if style == "news":
        out = build_news(rel(spec.get("bg")), spec["line1"],
                         spec.get("line2", ""), spec.get("kicker"),
                         rel(spec.get("out", "out/thumbnail.jpg")),
                         badge=badge, block=spec.get("block", 0.40))
    else:
        out = build(rel(spec.get("bg")), spec["line1"], spec["line2"],
                    spec.get("kicker"), rel(spec.get("out", "out/thumbnail.jpg")),
                    badge=badge, vs=spec.get("vs", True),
                    bg_right=rel(spec.get("bg_right")))

    # YouTube rejects thumbnails over 2 MB outright.
    size = os.path.getsize(out)
    if size > 2 * 1024 * 1024:
        raise SystemExit(f"thumbnail is {size/1e6:.1f} MB, limit is 2 MB")
    return out


if __name__ == "__main__":
    main()
