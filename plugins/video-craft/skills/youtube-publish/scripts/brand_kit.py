"""Politainment brand kit — shared design tokens and drawing helpers.

All output is 1080p (1920x1080). Tokens here define the channel's visual
language so intro, outro and thumbnail stay consistent.
"""
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1920, 1080
FPS = 30

# ---- Design tokens -------------------------------------------------------
INK = (10, 14, 26)           # deep navy base
INK_2 = (18, 25, 44)         # raised surface
CRIMSON = (214, 34, 54)      # primary accent - political urgency
CRIMSON_HI = (255, 74, 92)   # hot highlight
GOLD = (245, 194, 78)        # secondary accent - assembly / authority
PAPER = (247, 245, 240)      # near-white text
MUTED = (156, 168, 194)

LATIN_BOLD = "/System/Library/Fonts/Supplemental/Futura.ttc"
LATIN_FALLBACK = "/System/Library/Fonts/HelveticaNeue.ttc"
TAMIL = "/System/Library/Fonts/Supplemental/Tamil Sangam MN.ttc"
TAMIL_MN = "/System/Library/Fonts/Supplemental/Tamil MN.ttc"


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.truetype(LATIN_FALLBACK, size)


def latin(size, bold=True):
    """Heavy geometric sans for the wordmark."""
    for path, idx in ((LATIN_BOLD, 1 if bold else 0), (LATIN_FALLBACK, 1)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def tamil(size, bold=True):
    for path in (TAMIL_MN, TAMIL):
        for idx in ((1, 0) if bold else (0, 1)):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


# ---- Easing --------------------------------------------------------------
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease_out_expo(t):
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - pow(2, -10 * t)


def ease_out_back(t, s=1.70158):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_in_out_cubic(t):
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def ease_out_cubic(t):
    return 1 - pow(1 - clamp(t), 3)


def seg(t, start, dur):
    """Normalised progress of a sub-animation starting at `start`."""
    if dur <= 0:
        return 1.0
    return clamp((t - start) / dur)


# ---- Drawing helpers -----------------------------------------------------
def base_frame(color=INK):
    return Image.new("RGB", (W, H), color)


def vignette(img, strength=0.55):
    """Soft radial darkening for cinematic depth."""
    v = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(v)
    cx, cy = W / 2, H / 2
    maxr = math.hypot(cx, cy)
    steps = 60
    for i in range(steps, 0, -1):
        f = i / steps
        r = maxr * f
        a = int(255 * strength * (f ** 2.2))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, v)


def texture(img, amount=7):
    """Subtle film grain so flat fills don't band."""
    import random
    px = img.load()
    rnd = random.Random(7)
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            n = rnd.randint(-amount, amount)
            r, g, b = px[x, y]
            px[x, y] = (clamp(r + n, 0, 255), clamp(g + n, 0, 255), clamp(b + n, 0, 255))
    return img


def text_center(draw, cx, cy, s, fnt, fill, anchor="mm"):
    draw.text((cx, cy), s, font=fnt, fill=fill, anchor=anchor)


def measure(fnt, s):
    b = fnt.getbbox(s)
    return b[2] - b[0], b[3] - b[1]


def rounded_bar(draw, x, y, w, h, color, r=None):
    r = r if r is not None else h / 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=color)


def glow_text(img, xy, s, fnt, color, blur=18, glow=(214, 34, 54), anchor="mm"):
    """Draw text with a soft coloured glow behind it."""
    from PIL import ImageFilter
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text(xy, s, font=fnt, fill=glow + (200,), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img = Image.alpha_composite(img.convert("RGBA"), layer)
    d2 = ImageDraw.Draw(img)
    d2.text(xy, s, font=fnt, fill=color, anchor=anchor)
    return img.convert("RGB")
