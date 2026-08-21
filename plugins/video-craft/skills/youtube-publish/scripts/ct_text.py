"""Native macOS CoreText renderer.

Pillow has no HarfBuzz here, so Tamil combining marks (pulli, vowel signs)
render detached. CoreText does full Indic shaping, so all Tamil — and any
mixed Tamil/Latin — text is rasterised through this module instead.
"""
import Quartz
import CoreText
import AppKit
from PIL import Image


def _cf_attr_string(text, font_name, size, rgb, tracking=0.0):
    font = AppKit.NSFont.fontWithName_size_(font_name, size)
    if font is None:
        font = AppKit.NSFont.systemFontOfSize_(size)
    color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
        rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0,
        (rgb[3] / 255.0) if len(rgb) > 3 else 1.0)
    attrs = {
        AppKit.NSFontAttributeName: font,
        AppKit.NSForegroundColorAttributeName: color,
    }
    if tracking:
        attrs[AppKit.NSKernAttributeName] = tracking
    return AppKit.NSAttributedString.alloc().initWithString_attributes_(text, attrs)


def measure(text, font_name, size, tracking=0.0):
    """Return (width, height, ascent, descent) of shaped text in pixels."""
    astr = _cf_attr_string(text, font_name, size, (255, 255, 255), tracking)
    line = CoreText.CTLineCreateWithAttributedString(astr)
    width, ascent, descent, _leading = CoreText.CTLineGetTypographicBounds(
        line, None, None, None)
    return (width, ascent + descent, ascent, descent)


def render_text(text, font_name, size, rgb=(255, 255, 255, 255), tracking=0.0,
                pad=24):
    """Rasterise shaped text to a tight RGBA PIL image."""
    astr = _cf_attr_string(text, font_name, size, rgb, tracking)
    line = CoreText.CTLineCreateWithAttributedString(astr)
    width, ascent, descent, _leading = CoreText.CTLineGetTypographicBounds(
        line, None, None, None)

    w = int(width) + pad * 2
    h = int(ascent + descent) + pad * 2
    if w <= pad * 2 or h <= pad * 2:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    space = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, w, h, 8, w * 4, space,
        Quartz.kCGImageAlphaPremultipliedLast)

    Quartz.CGContextSetShouldAntialias(ctx, True)
    Quartz.CGContextSetShouldSmoothFonts(ctx, True)
    Quartz.CGContextSetTextPosition(ctx, pad, pad + descent)
    CoreText.CTLineDraw(line, ctx)

    data = Quartz.CGBitmapContextGetData(ctx)
    buf = data.as_buffer(w * h * 4)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", 0, 1)
    return img.crop(img.getbbox() or (0, 0, 1, 1))


def paste_center(base, text_img, cx, cy, alpha=1.0):
    """Composite a rendered text image centred on (cx, cy)."""
    if text_img.size == (1, 1):
        return base
    if alpha < 1.0:
        a = text_img.split()[3].point(lambda v: int(v * alpha))
        text_img = text_img.copy()
        text_img.putalpha(a)
    x = int(cx - text_img.width / 2)
    y = int(cy - text_img.height / 2)
    out = base.convert("RGBA")
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    layer.paste(text_img, (x, y), text_img)
    return Image.alpha_composite(out, layer).convert("RGB")


# Font family names as CoreText knows them
TAMIL_BOLD = "TamilSangamMN-Bold"
TAMIL_REG = "TamilSangamMN"
LATIN_HEAVY = "AvenirNext-Heavy"
LATIN_BOLD = "AvenirNext-Bold"
LATIN_DEMI = "AvenirNext-DemiBold"
LATIN_COND = "AvenirNextCondensed-Heavy"


def available(name):
    return AppKit.NSFont.fontWithName_size_(name, 12) is not None
