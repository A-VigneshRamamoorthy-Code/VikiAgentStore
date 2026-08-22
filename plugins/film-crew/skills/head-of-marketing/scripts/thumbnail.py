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
