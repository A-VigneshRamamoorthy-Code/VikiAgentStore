#!/usr/bin/env python3
"""Render a broadcast-news storyboard to video.

    python3 render.py storyboard.json                 # the film
    python3 render.py storyboard.json --sheet         # a contact sheet
    python3 render.py storyboard.json --frame 12.5    # one frame

The look is a rolling bulletin: full-bleed plate, a stacked kicker and headline
across the lower third, a channel bug bottom-left and a location chip
bottom-right.

**Always look at the contact sheet before rendering.** Pile-up and overlap are
invisible in a single frame and obvious across sixteen; that is the whole
reason `--sheet` exists.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                    # pragma: no cover
    print("news/render: needs Pillow (pip install Pillow)", file=sys.stderr)
    raise SystemExit(2)

TIME_RE = re.compile(r"^(l\d+)(\.end)?(?:([+-])([0-9.]+))?$")

#: Tried in order. The first that exists and can draw the string wins, so a
#: Tamil headline falls through to a font that has Tamil rather than rendering
#: a row of empty boxes -- which is what a single hardcoded font would do.
FONT_STACK = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_FONT_CACHE = {}

#: Scripts whose glyphs must be reordered or joined to be correct. Pillow can
#: only do that when it was built against libraqm; without it the characters
#: are drawn in codepoint order, which turns Tamil, Devanagari or Arabic into
#: confident-looking nonsense. Someone who cannot read the script will not
#: notice, which is exactly why this is checked rather than left to the eye.
COMPLEX_RANGES = (
    (0x0590, 0x05FF, "Hebrew"), (0x0600, 0x06FF, "Arabic"),
    (0x0700, 0x074F, "Syriac"), (0x0750, 0x077F, "Arabic"),
    (0x0900, 0x097F, "Devanagari"), (0x0980, 0x09FF, "Bengali"),
    (0x0A00, 0x0A7F, "Gurmukhi"), (0x0A80, 0x0AFF, "Gujarati"),
    (0x0B00, 0x0B7F, "Odia"), (0x0B80, 0x0BFF, "Tamil"),
    (0x0C00, 0x0C7F, "Telugu"), (0x0C80, 0x0CFF, "Kannada"),
    (0x0D00, 0x0D7F, "Malayalam"), (0x0D80, 0x0DFF, "Sinhala"),
    (0x0E00, 0x0E7F, "Thai"), (0x0E80, 0x0EFF, "Lao"),
    (0x1000, 0x109F, "Myanmar"), (0x1780, 0x17FF, "Khmer"),
    (0xFB50, 0xFDFF, "Arabic"), (0xFE70, 0xFEFF, "Arabic"),
)

TEXT_FIELDS = ("kicker", "headline", "figure", "caption", "name", "role",
               "place", "left", "right", "label")


def complex_scripts(sb):
    """Which shaping-dependent scripts appear in this storyboard's text."""
    found = set()
    for g in sb.get("graphics") or []:
        vals = [g.get(k) for k in TEXT_FIELDS] + list(g.get("items") or [])
        for v in vals:
            for ch in str(v or ""):
                c = ord(ch)
                for lo, hi, name in COMPLEX_RANGES:
                    if lo <= c <= hi:
                        found.add(name)
                        break
    return sorted(found)


def check_shaping(sb):
    try:
        from PIL import features
        ok = features.check("raqm")
    except Exception:
        ok = False
    if ok:
        return
    scripts = complex_scripts(sb)
    if not scripts:
        return
    print(
        "news/render: WARNING -- this storyboard contains %s text, but Pillow\n"
        "  here was built without libraqm, so it cannot reorder or join glyphs.\n"
        "  The text WILL render incorrectly, and will still look plausible.\n"
        "  Fix it before publishing:  brew install libraqm  (then reinstall\n"
        "  Pillow with  pip install --force-reinstall --no-binary :all: Pillow)\n"
        "  Verify with: python3 -c \"from PIL import features;"
        "print(features.check('raqm'))\"" % ", ".join(scripts),
        file=sys.stderr)


def die(msg):
    print("news/render: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def font(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for p in FONT_STACK:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[size] = f
                return f
            except OSError:
                continue
    _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def hex_rgb(s, default=(0, 0, 0)):
    s = (s or "").lstrip("#")
    if len(s) != 6:
        return default
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default


# ------------------------------------------------------------------ timing --


def line_times(narration):
    """Absolute start/end for every narration line.

    `duration` comes from the voice booth having measured the real audio, so
    this is the film's clock rather than an estimate.
    """
    t, out = 0.0, {}
    for l in narration or []:
        d = float(l.get("duration") or 0.0)
        out[l.get("id")] = (t, t + d)
        t += d + float(l.get("gap_after") or 0.0)
    return out, t


def resolve(ref, times):
    if isinstance(ref, (int, float)):
        return float(ref)
    m = TIME_RE.match(str(ref or ""))
    if not m:
        return 0.0
    start, end = times.get(m.group(1), (0.0, 0.0))
    base = end if m.group(2) else start
    if m.group(3):
        off = float(m.group(4))
        base += off if m.group(3) == "+" else -off
    return max(0.0, base)


def ease(x):
    """Smooth in/out. Broadcast graphics never snap; they are driven."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ drawing --


def fitted(draw, text, box_w, size, weight=0):
    """Largest font <= size whose text fits box_w."""
    s = size
    while s > 12:
        f = font(s)
        if draw.textlength(text, font=f) <= box_w:
            return f
        s -= 2
    return font(12)


def wrapped(draw, text, box_w, size, max_lines=2, floor=0.62):
    """Fit text by wrapping before shrinking it into illegibility.

    Shrink-to-fit alone is wrong on a narrow frame: a headline that fits 16:9
    on one line drops to a caption-sized sliver at 9:16. Below `floor` of the
    intended size the text wraps instead, which is what a real bulletin does.

    Returns ``(font, [line, ...])``.
    """
    s = size
    while s > max(12, int(size * floor)):
        f = font(s)
        if draw.textlength(text, font=f) <= box_w:
            return f, [text]
        s -= 2

    f = font(max(12, int(size * floor)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and draw.textlength(trial, font=f) > box_w:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
        else:
            cur = trial
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if not lines:
        lines = [text]
    # Anything that still will not fit is shrunk the rest of the way, so the
    # last resort is small text rather than text running off the frame.
    widest = max(draw.textlength(l, font=f) for l in lines)
    while widest > box_w and f.size > 12:
        f = font(f.size - 2)
        widest = max(draw.textlength(l, font=f) for l in lines)
    return f, lines


def plate(W, H, g, seed):
    """The picture behind the graphics.

    Real footage is not this style's job -- the production designer hands over
    whatever the plate hint names. With nothing supplied, a neutral graded
    field stands in, so a storyboard always renders and the graphics can be
    judged on their own.
    """
    hint = ((g or {}).get("plate") or {}).get("hint") or ""
    h = (sum(ord(c) for c in hint) + seed) % 360
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / max(1, H - 1)
        r = int(24 + 46 * k + (h % 30))
        gg = int(26 + 40 * k + (h // 6 % 24))
        b = int(32 + 52 * k + (h // 3 % 36))
        d.line([(0, y), (W, y)], fill=(min(r, 255), min(gg, 255), min(b, 255)))
    return img


def rounded(draw, box, r, fill):
    try:
        draw.rounded_rectangle(box, radius=r, fill=fill)
    except AttributeError:                              # pragma: no cover
        draw.rectangle(box, fill=fill)


def draw_bug(img, brand, W, H):
    """The channel bug, bottom-left: one white box per letter.

    Sized off the *short* edge. Sizing chrome off the height instead makes the
    bug a third of the width of a 9:16 frame, where it collides with the
    location chip -- a fault that is invisible at 16:9.
    """
    name = (brand.get("name") or "").strip()
    if not name:
        return
    letters = [c for c in name.upper() if c.isalnum()][:4]
    if not letters:
        return
    u = min(W, H)
    d = ImageDraw.Draw(img)
    s = int(u * 0.052)
    gap = int(s * 0.14)
    x, y = int(W * 0.028), int(H - s - u * 0.055)
    f = font(int(s * 0.74))
    for c in letters:
        d.rectangle([x, y, x + s, y + s], fill=(255, 255, 255))
        w = d.textlength(c, font=f)
        bb = f.getbbox(c)
        d.text((x + (s - w) / 2, y + (s - (bb[3] - bb[1])) / 2 - bb[1]),
               c, font=f, fill=(17, 17, 17))
        x += s + gap
    return x


def draw_chip(img, text, brand, W, H, alpha=210, floor=0):
    """The location chip, bottom-right.

    `floor` is where the channel bug ends; the chip is dropped onto its own
    row rather than overlapping it when the frame is too narrow for both.
    """
    if not text:
        return
    u = min(W, H)
    d = ImageDraw.Draw(img)
    f = fitted(d, text, int(W * 0.44), int(u * 0.046))
    pad = int(u * 0.018)
    w = d.textlength(text, font=f)
    bb = f.getbbox(text)
    h = (bb[3] - bb[1]) + pad * 2
    x1, y1 = int(W - W * 0.028), int(H - u * 0.055)
    x0, y0 = int(x1 - w - pad * 2), int(y1 - h)
    if x0 < floor + int(W * 0.02):
        y1 = int(y0 - u * 0.018)
        y0 = y1 - h
        x1 = int(W - W * 0.028)
        x0 = int(x1 - w - pad * 2)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([x0, y0, x1, y1],
                                    fill=hex_rgb(brand.get("chip"),
                                                 (61, 61, 61)) + (alpha,))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))
    d = ImageDraw.Draw(img)
    d.text((x0 + pad, y0 + pad - bb[1]), text, font=f, fill=(255, 255, 255))


def draw_stack(img, kicker, headline, brand, W, H, k):
    """The kicker bar over the headline bar -- the shape of the whole style.

    They slide in from the left on a shared curve but the headline trails
    slightly, which is what makes it read as one object being pushed on rather
    than two bars arriving.
    """
    d = ImageDraw.Draw(img)
    u = min(W, H)
    left = int(W * 0.012)
    bar_w = int(W * 0.976)
    pad = int(W * 0.018)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    paper = hex_rgb(brand.get("bar"), (242, 240, 235))
    ink = hex_rgb(brand.get("ink"), (17, 17, 17))

    blocks = []
    if kicker:
        f, lines = wrapped(d, kicker, bar_w - pad * 2, int(u * 0.072), 1)
        blocks.append((f, lines, paper, ink, 0.0))
    if headline:
        f, lines = wrapped(d, headline, bar_w - pad * 2, int(u * 0.086), 2)
        blocks.append((f, lines, accent, (255, 255, 255), 0.25))

    # Laid out from the bottom so a headline that wraps to two lines grows
    # upward into the picture instead of off the bottom of the frame.
    heights = []
    for f, lines, _, _, _ in blocks:
        lh = f.getbbox("Ag")[3] - f.getbbox("Ag")[1]
        heights.append(len(lines) * lh + int(u * 0.021) * (len(lines) + 1))
    y = int(H * 0.845) - sum(heights) - int(u * 0.006) * max(0, len(blocks) - 1)

    for (f, lines, bg, fg, lag), hh in zip(blocks, heights):
        off = int((1 - ease(max(0.0, (k - lag) / max(1e-6, 1 - lag)))) * -bar_w)
        d.rectangle([left + off, y, left + bar_w + off, y + hh], fill=bg)
        lh = f.getbbox("Ag")[3] - f.getbbox("Ag")[1]
        ty = y + int(u * 0.021)
        for line in lines:
            bb = f.getbbox(line)
            d.text((left + pad + off, ty - bb[1]), line, font=f, fill=fg)
            ty += lh + int(u * 0.021)
        y += hh + int(u * 0.006)


def draw_astonisher(img, g, brand, W, H, k):
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    fig = g.get("figure") or ""
    cap = g.get("caption") or ""
    box_w = int(W * 0.52)
    x = int(W * 0.06)
    y = int(H * 0.44)
    a = ease(k)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(
        [x, y, x + box_w, y + int(H * 0.30)], fill=accent + (int(238 * a),))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))
    d = ImageDraw.Draw(img)
    if fig:
        f = fitted(d, fig, box_w - int(W * 0.05), int(H * 0.17))
        bb = f.getbbox(fig)
        d.text((x + int(W * 0.025), y + int(H * 0.035) - bb[1]), fig,
               font=f, fill=(255, 255, 255))
    if cap:
        f = fitted(d, cap, box_w - int(W * 0.05), int(H * 0.05))
        bb = f.getbbox(cap)
        d.text((x + int(W * 0.025), y + int(H * 0.215) - bb[1]), cap,
               font=f, fill=(255, 255, 255))


def draw_namestrap(img, g, brand, W, H, k):
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    paper = hex_rgb(brand.get("bar"), (242, 240, 235))
    ink = hex_rgb(brand.get("ink"), (17, 17, 17))
    name, role = g.get("name") or "", g.get("role") or ""
    x = int(W * 0.055)
    y = int(H * 0.655)
    w = int(W * 0.56 * ease(k))
    if w < 8:
        return
    top, bot = int(H * 0.098), int(H * 0.072)
    d.rectangle([x, y, x + w, y + top], fill=accent)
    d.rectangle([x, y + top, x + w, y + top + bot], fill=paper)
    if w > int(W * 0.2):
        pad = int(W * 0.016)
        f = fitted(d, name, w - pad * 2, int(H * 0.070))
        bb = f.getbbox(name or "X")
        d.text((x + pad, y + (top - (bb[3] - bb[1])) / 2 - bb[1]), name,
               font=f, fill=(255, 255, 255))
        f2 = fitted(d, role, w - pad * 2, int(H * 0.046))
        bb2 = f2.getbbox(role or "X")
        d.text((x + pad, y + top + (bot - (bb2[3] - bb2[1])) / 2 - bb2[1]),
               role, font=f2, fill=ink)


def draw_bullets(img, g, brand, W, H, k):
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    paper = hex_rgb(brand.get("bar"), (242, 240, 235))
    ink = hex_rgb(brand.get("ink"), (17, 17, 17))
    items = g.get("items") or []
    x, y = int(W * 0.055), int(H * 0.34)
    w = int(W * 0.60)
    pad = int(W * 0.016)
    if g.get("kicker"):
        hh = int(H * 0.082)
        f = fitted(d, g["kicker"], w - pad * 2, int(H * 0.058))
        bb = f.getbbox(g["kicker"])
        d.rectangle([x, y, x + w, y + hh], fill=accent)
        d.text((x + pad, y + (hh - (bb[3] - bb[1])) / 2 - bb[1]), g["kicker"],
               font=f, fill=(255, 255, 255))
        y += hh + int(H * 0.010)
    # Items arrive one at a time -- the point of a list graphic.
    per = 1.0 / max(1, len(items))
    for i, it in enumerate(items):
        a = ease((k - i * per) / max(per, 1e-6))
        if a <= 0.01:
            continue
        hh = int(H * 0.088)
        ww = int(w * a)
        d.rectangle([x, y, x + ww, y + hh], fill=paper)
        if ww > int(W * 0.18):
            f = fitted(d, it, ww - pad * 2, int(H * 0.052))
            bb = f.getbbox(it)
            d.text((x + pad, y + (hh - (bb[3] - bb[1])) / 2 - bb[1]), it,
                   font=f, fill=ink)
        y += hh + int(H * 0.010)


def draw_split(img, g, brand, W, H, k):
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    a = ease(k)
    mid = W // 2
    d.rectangle([0, int(H * 0.78), int(mid * a), int(H * 0.88)], fill=accent)
    d.rectangle([W - int(mid * a), int(H * 0.78), W, int(H * 0.88)],
                fill=(30, 30, 30))
    for text, x0, x1, col in ((g.get("left"), 0, mid, (255, 255, 255)),
                              (g.get("right"), mid, W, (255, 255, 255))):
        if not text or a < 0.5:
            continue
        f = fitted(d, text, mid - int(W * 0.06), int(H * 0.055))
        w = d.textlength(text, font=f)
        bb = f.getbbox(text)
        d.text((x0 + (mid - w) / 2, int(H * 0.792) - bb[1]), text, font=f,
               fill=col)


def draw_callout(img, g, brand, W, H, k):
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    cx, cy = int(W * 0.62), int(H * 0.40)
    r = int(min(W, H) * 0.16 * (0.85 + 0.15 * ease(k)))
    wdt = max(3, int(H * 0.006))
    if g.get("mark") == "box":
        d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=accent, width=wdt)
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=wdt)
    if g.get("label") and k > 0.4:
        f = font(int(H * 0.042))
        bb = f.getbbox(g["label"])
        d.text((cx - r, cy + r + int(H * 0.02) - bb[1]), g["label"], font=f,
               fill=accent)


def draw_sting(img, g, brand, W, H, k):
    """A wipe between movements: the accent sweeps across and off."""
    d = ImageDraw.Draw(img)
    accent = hex_rgb(brand.get("accent"), (187, 25, 25))
    a = ease(k)
    if a < 0.5:
        w = int(W * (a * 2))
        d.rectangle([0, 0, w, H], fill=accent)
    else:
        x = int(W * ((a - 0.5) * 2))
        d.rectangle([x, 0, W, H], fill=accent)
    if g.get("label") and 0.15 < a < 0.85:
        f = font(int(H * 0.09))
        w = d.textlength(g["label"], font=f)
        bb = f.getbbox(g["label"])
        d.text(((W - w) / 2, H / 2 - (bb[3] - bb[1]) / 2 - bb[1]), g["label"],
               font=f, fill=(255, 255, 255))


DRAW = {"astonisher": draw_astonisher, "namestrap": draw_namestrap,
        "bullets": draw_bullets, "split": draw_split, "callout": draw_callout,
        "sting": draw_sting}


# ------------------------------------------------------------------- frame --


def active(graphics, times, t):
    """Every graphic on screen at t, with its 0..1 progress."""
    out = []
    for g in graphics:
        s = resolve(g.get("at"), times)
        end = resolve(g["until"], times) if g.get("until") else \
            s + float(g.get("hold") or 3.0)
        if s <= t < end:
            span = max(0.35, min(0.6, (end - s) * 0.25))
            out.append((g, min(1.0, (t - s) / span)))
    return out


def plate_at(graphics, times, t):
    """The picture under the graphics: the most recent one to have started.

    Taking it from the *active* graphics instead would change the background
    whenever the screen is momentarily bare, which on a contact sheet reads as
    the vision mixer cutting to the wrong source.
    """
    best, best_t = None, -1.0
    for g in graphics:
        s = resolve(g.get("at"), times)
        if s <= t and s >= best_t and (g.get("plate") or {}).get("hint"):
            best, best_t = g, s
    return best


def frame(sb, times, t, W, H):
    brand = sb.get("brand") or {}
    graphics = sb.get("graphics") or []
    on = active(graphics, times, t)
    img = plate(W, H, plate_at(graphics, times, t), sb.get("seed", 7))

    place = None
    for g, k in on:
        kind = g["kind"]
        if kind == "locator":
            place = g.get("place")
        elif kind == "headline":
            draw_stack(img, g.get("kicker"), g.get("headline"), brand, W, H, k)
        elif kind in DRAW:
            DRAW[kind](img, g, brand, W, H, k)

    end = draw_bug(img, brand, W, H)
    if place:
        draw_chip(img, place, brand, W, H, floor=end or 0)
    return img


# -------------------------------------------------------------------- main --


def have(binary):
    return shutil.which(binary) is not None


def narration_inputs(sb, base):
    """(path, start_seconds) for every narration line that has audio.

    Paths are relative to the storyboard, the same rule the rest of the file
    uses, so a storyboard and its `vo/` folder move together.
    """
    out, t = [], 0.0
    for l in sb.get("narration") or []:
        d = float(l.get("duration") or 0.0)
        src = l.get("audio")
        if src:
            p = src if os.path.isabs(src) else os.path.join(base, src)
            if os.path.exists(p):
                out.append((p, t))
            else:
                print("news/render: narration line %r points at %s, which does "
                      "not exist -- that line will be silent"
                      % (l.get("id"), src), file=sys.stderr)
        t += d + float(l.get("gap_after") or 0.0)
    return out


def _mix_chain(voice, first=1):
    """The adelay/amix graph that lays every clip on the timeline.

    `first` is the ffmpeg input index of the first wav: 1 in the real render,
    where input 0 is the image sequence, but 0 in the measuring pass, which
    has no video. Getting this wrong points the graph at a stream that does
    not exist, and the only symptom is silently un-normalised audio.
    """
    parts = []
    for i, (_, at) in enumerate(voice):
        # `adelay` takes milliseconds, and needs one value per channel.
        parts.append("[%d:a]adelay=%d:all=1[a%d]"
                     % (i + first, int(round(at * 1000)), i))
    mix = "".join("[a%d]" % i for i in range(len(voice)))
    return ";".join(parts) + ";" + mix + \
        "amix=inputs=%d:normalize=0[mix]" % len(voice)


def _measured(voice, lufs, tp):
    """Loudness of the assembled mix, for the second loudnorm pass.

    Single-pass loudnorm is adaptive and documented as approximate; it landed
    1.2 LU under target here. `paper` already masters in two passes for the
    same reason, so this follows it rather than inventing a second answer.
    Returns a `measured_*` suffix, or "" if the measuring pass tells us
    nothing -- in which case one pass is still better than no normalisation.
    """
    cmd = ["ffmpeg", "-hide_banner"]
    for p, _ in voice:
        cmd += ["-i", p]
    cmd += ["-filter_complex",
            _mix_chain(voice, first=0) +
            ";[mix]loudnorm=I=%s:TP=%s:LRA=11:print_format=json[out]" % (lufs, tp),
            "-map", "[out]", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = r.stderr or ""
    if "{" not in txt or "}" not in txt:
        return ""
    try:
        s = json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])
        return (":measured_I=%s:measured_TP=%s:measured_LRA=%s"
                ":measured_thresh=%s:offset=%s:linear=true"
                % (s["input_i"], s["input_tp"], s["input_lra"],
                   s["input_thresh"], s["target_offset"]))
    except Exception:
        return ""


def verify_spec():
    """The audio contract, read from `style.json` rather than restated here.

    The target used to be written out three times -- in the manifest, in the
    `loudnorm` literal and in the checker's default -- which agreed only
    because they were copied. Editing the manifest then moved the claim
    without moving either the encoder or the check. One reader, one truth.
    """
    spec = {"loudness_lufs": -14.0, "true_peak_dbfs": -1.0,
            "loudness_tolerance_lu": 1.5}
    # ffmpeg enforces these ranges itself, but it does so from inside a filter
    # graph, so the only symptom is a generic encoder failure with the reason
    # buried in a stderr tail. Checking here names the field instead.
    ok = {"loudness_lufs": (-70.0, -5.0), "true_peak_dbfs": (-9.0, 0.0),
          "loudness_tolerance_lu": (0.0, 20.0)}
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "style.json")
    try:
        with open(path, encoding="utf-8") as f:
            declared = (json.load(f) or {}).get("verify") or {}
        for k in spec:
            v = declared.get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            lo, hi = ok[k]
            if lo <= float(v) <= hi:
                spec[k] = float(v)
            else:
                print("news/render: style.json verify.%s is %s, outside the "
                      "usable range %g..%g -- using %g instead."
                      % (k, v, lo, hi, spec[k]), file=sys.stderr)
    except Exception:
        pass
    return spec


def render_video(sb, times, total, out, W, H, fps, sb_dir="."):
    if not have("ffmpeg"):
        die("ffmpeg is not installed, so there is nothing to encode with")
    spec = verify_spec()
    voice = narration_inputs(sb, sb_dir)
    if not voice:
        # A bulletin is narration over pictures. Shipping the pictures alone,
        # silently, is the kind of failure that is only noticed after upload.
        print("news/render: WARNING -- no narration line has an `audio` file, "
              "so this film will be SILENT.\n"
              "  Render the voice with the voice-booth skill and put its path "
              "in each line's `audio`.", file=sys.stderr)
    tmp = tempfile.mkdtemp(prefix="news-render-")
    try:
        n = max(1, int(total * fps))
        for i in range(n):
            frame(sb, times, i / fps, W, H).save(
                os.path.join(tmp, "f%06d.png" % i))
            if i % max(1, n // 10) == 0:
                print("  %d%%" % int(100 * i / n), flush=True)

        cmd = ["ffmpeg", "-y", "-framerate", str(fps),
               "-i", os.path.join(tmp, "f%06d.png")]
        for p, _ in voice:
            cmd += ["-i", p]
        if voice:
            # The film is `total` seconds long because that is how many frames
            # were drawn. The mix must not get a vote: `amix` ends with the
            # last *voiced* clip, so `-shortest` would truncate the film at
            # the last line that happens to have audio -- losing the ending of
            # any partly-voiced storyboard, without an error. Pad the audio
            # out instead and let `-t` cut both streams at the real length.
            lufs, tp = spec["loudness_lufs"], spec["true_peak_dbfs"]
            # The extra 0.6 dB absorbs the inter-sample overshoot the AAC
            # encoder adds downstream, the same margin `paper` uses.
            ceiling = 10.0 ** ((tp - 0.6) / 20.0)
            chain = _mix_chain(voice) + \
                ";[mix]loudnorm=I=%s:TP=%s:LRA=11%s[norm]" \
                % (lufs, tp, _measured(voice, lufs, tp)) + \
                ";[norm]alimiter=level_in=1:level_out=1:limit=%.4f" \
                ":level=disabled[lim]" % ceiling + \
                ";[lim]apad[aout]"
            cmd += ["-filter_complex", chain, "-map", "0:v", "-map", "[aout]",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        cmd += ["-t", "%.3f" % total,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", str(sb["output"].get("crf", 20)),
                "-preset", sb["output"].get("preset", "medium"), out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            die("ffmpeg failed:\n%s" % r.stderr[-1200:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("wrote %s%s" % (out, "" if voice else "   (SILENT — no narration)"))
    if voice:
        report_loudness(out, spec)


def report_loudness(path, spec):
    """Measure what actually came out, and say so.

    `style.json` declares a loudness target, but nothing read it -- it was a
    claim, not a check. Peak-constrained narration (a high crest factor) can
    stop loudnorm reaching the target at all, and the only way to know is to
    measure the finished file rather than trust the filter graph.
    """
    target = spec["loudness_lufs"]
    tol = spec["loudness_tolerance_lu"]
    ceiling = spec["true_peak_dbfs"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128=peak=true:framelog=quiet", "-f",
                        "null", "-"], capture_output=True, text=True)
    m = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", r.stderr or "")
    if not m:
        return
    got = float(m.group(1))
    peak = re.findall(r"Peak:\s*(-?[\d.]+)\s*dBFS", r.stderr or "")
    line = "  loudness %.1f LUFS (target %.1f)" % (got, target)
    if peak:
        line += ", true peak %s dBFS (ceiling %.1f)" % (peak[-1], ceiling)
    print(line)
    if abs(got - target) > tol:
        print("news/render: WARNING -- %.1f LUFS is %.1f LU from the %.1f "
              "target.\n  Narration with a high crest factor cannot be lifted "
              "further without clipping; master the voice clips closer to "
              "target before assembly." % (got, got - target, target),
              file=sys.stderr)
    if peak and float(peak[-1]) > ceiling:
        print("news/render: WARNING -- true peak %s dBFS is above the %.1f "
              "dBFS ceiling this style declares. The limiter should have "
              "prevented this, so treat it as a bug rather than a setting."
              % (peak[-1], ceiling), file=sys.stderr)


def contact_sheet(sb, times, total, out, W, H, cols=4, rows=4):
    n = cols * rows
    tw, th = W // cols, H // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    f = font(max(11, th // 14))
    for i in range(n):
        t = total * (i + 0.5) / n
        im = frame(sb, times, t, W, H).resize((tw, th), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
        d.text(((i % cols) * tw + 6, (i // cols) * th + 6), "%.1fs" % t,
               font=f, fill=(255, 220, 60))
    sheet.save(out)
    print("wrote %s  (%d frames across %.1fs)" % (out, n, total))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out")
    ap.add_argument("--sheet", action="store_true",
                    help="write a contact sheet and exit -- always do this first")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="write a single frame at time T and exit")
    ap.add_argument("--preview", action="store_true",
                    help="render at half resolution")
    a = ap.parse_args(argv)

    try:
        with open(a.storyboard, encoding="utf-8") as fh:
            sb = json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (a.storyboard, e))

    if sb.get("style") != "news":
        die("%s is a %r storyboard, not a news one"
            % (a.storyboard, sb.get("style")))

    check_shaping(sb)

    o = sb.get("output") or {}
    W, H = int(o.get("width", 1920)), int(o.get("height", 1080))
    if a.preview:
        W, H = W // 2, H // 2
    fps = int(o.get("fps", 30))

    times, total = line_times(sb.get("narration"))
    if total <= 0:
        # Without measured narration there is no clock, so fall back to the
        # graphics' own holds rather than rendering a zero-length film.
        total = sum(float(g.get("hold") or 3.0)
                    for g in sb.get("graphics") or []) or 6.0

    base = a.out or o.get("path") or "news.mp4"
    if a.frame is not None:
        p = os.path.splitext(base)[0] + "_frame.jpg"
        frame(sb, times, a.frame, W, H).save(p, quality=92)
        print("wrote %s" % p)
        return 0
    if a.sheet:
        p = os.path.splitext(base)[0] + "_sheet.jpg"
        contact_sheet(sb, times, total, p, W, H)
        return 0

    render_video(sb, times, total, base, W, H, fps,
                 os.path.dirname(os.path.abspath(a.storyboard)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
