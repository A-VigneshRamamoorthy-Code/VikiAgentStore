"""Pillow graphics + the per-frame Scene compositor (the overlay layer).

`Scene(config, timeline)` prerenders every overlay element (intro card, captions,
logo bug, wipes, outro, end-card) once, then `render_frame(t)` composites them for
any output time `t` using the easing in `motion.py`.
"""
from __future__ import annotations
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import motion

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(SKILL_DIR, "fonts")


# ----------------------------- color helpers -----------------------------
def hexa(c, a=255):
    if isinstance(c, (tuple, list)):
        return tuple(list(c)[:3] + [a if len(c) < 4 else c[3]])
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def mix(c1, c2, t):
    a, b = hexa(c1), hexa(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


# ----------------------------- fonts -----------------------------
def _font_file(path_opt, default_name, system_names):
    if path_opt and os.path.exists(path_opt):
        return path_opt
    cand = os.path.join(FONTS_DIR, default_name)
    if os.path.exists(cand):
        return cand
    for s in system_names:
        if os.path.exists(s):
            return s
    return None


class Fonts:
    def __init__(self, config):
        self.reg = _font_file(config.get("font"), "Inter-Regular.ttf", [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        ])
        self.bold = _font_file(config.get("font_bold"), "Inter-Bold.ttf", [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        ])

    def get(self, size, weight=400):
        path = self.bold if weight >= 600 else self.reg
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            try:
                f.set_variation_by_name(
                    {400: "Regular", 600: "SemiBold", 700: "Bold", 900: "Black"}.get(weight, "Regular"))
            except Exception:
                pass
        return f


# ----------------------------- drawing -----------------------------
def measure(font, text):
    img = Image.new("RGBA", (4, 4))
    d = ImageDraw.Draw(img)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    return (r - l, b - t, -l, -t)


def text_img(text, font, color, pad=(0, 0), shadow=True):
    w, h, ox, oy = measure(font, text)
    W, H = w + pad[0] * 2 + 8, h + pad[1] * 2 + 8
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x, y = pad[0] + 4 + ox, pad[1] + 4 + oy
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        ds.text((x, y + 4), text, font=font, fill=(0, 0, 0, 150))
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        img = Image.alpha_composite(img, sh)
        d = ImageDraw.Draw(img)
    d.text((x, y), text, font=font, fill=hexa(color))
    return img


def rounded(size, radius, fill, stroke=None, stroke_w=0):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=fill,
                        outline=stroke, width=stroke_w)
    return img


def vgradient(W, H, colors):
    colors = [hexa(c) for c in (colors or ["#14172B", "#1E2348", "#101326"])]
    if len(colors) == 1:
        colors = colors * 2
    arr = np.zeros((H, W, 4), np.uint8)
    seg = H / (len(colors) - 1)
    for y in range(H):
        i = min(len(colors) - 2, int(y / seg))
        t = (y - i * seg) / seg
        arr[y, :] = [int(colors[i][k] + (colors[i + 1][k] - colors[i][k]) * t) for k in range(4)]
    return Image.fromarray(arr, "RGBA")


def with_shadow(img, blur=24, dy=10, alpha=140):
    a = img.getchannel("A").point(lambda v: int(v * alpha / 255))
    sh = Image.new("RGBA", (img.width, img.height + dy + blur * 2), (0, 0, 0, 0))
    black = Image.new("RGBA", img.size, (0, 0, 0, 255))
    black.putalpha(a)
    sh.paste(black, (0, dy + blur), black)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    out = Image.alpha_composite(out, sh)
    out.alpha_composite(img, (0, blur))
    return out


def brand_bg(W, H, config):
    g = vgradient(W, H, config["brand"].get("bg_gradient"))
    # soft accent glow upper-center
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    accent = hexa(config["brand"].get("primary", "#5B8DEF"))
    r = int(W * 0.32)
    gd.ellipse([W // 2 - r, int(H * 0.30) - r, W // 2 + r, int(H * 0.30) + r],
               fill=(accent[0], accent[1], accent[2], 60))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    return Image.alpha_composite(g, glow)


def generated_mark(size, config):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    accent = config["brand"].get("primary", "#5B8DEF")
    sq = vgradient(s, s, [mix(accent, "#ffffff", 0.15), accent])
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    img.paste(sq, (0, 0), mask)
    name = (config["brand"].get("name") or "?").strip()
    letter = name[0].upper() if name else "?"
    fonts = Fonts(config)
    f = fonts.get(int(s * 0.5), 900)
    ti = text_img(letter, f, "#ffffff", shadow=False)
    img.alpha_composite(ti, ((s - ti.width) // 2, (s - ti.height) // 2))
    return img


def load_logo(config, target=236):
    path = config["brand"].get("logo")
    if path and os.path.exists(path):
        try:
            im = Image.open(path).convert("RGBA")
            scale = target / max(im.width, im.height)
            return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
        except Exception:
            pass
    return generated_mark(target, config)


def caption_pill(text, config, fonts):
    f = fonts.get(46, 600)
    tw, th, ox, oy = measure(f, text)
    accent = hexa(config["brand"].get("primary", "#5B8DEF"))
    bullet, gap, padx, pady = 28, 18, 44, 30
    pw = bullet + gap + tw + padx * 2
    ph = max(th, bullet) + pady * 2
    pill = rounded((pw, ph), ph // 2, (0, 0, 0, 150),
                   stroke=(accent[0], accent[1], accent[2], 90), stroke_w=2)
    d = ImageDraw.Draw(pill)
    by = ph // 2
    bx = padx + bullet // 2
    d.ellipse([bx - bullet // 2, by - bullet // 2, bx + bullet // 2, by + bullet // 2], fill=accent)
    d.text((padx + bullet + gap + ox, (ph - th) // 2 + oy), text, font=f, fill=(255, 255, 255, 255))
    return with_shadow(pill, blur=22, dy=8, alpha=130)


def button(text, config, fonts):
    f = fonts.get(40, 700)
    tw, th, ox, oy = measure(f, text)
    accent = config["brand"].get("primary", "#5B8DEF")
    padx, pady = 50, 28
    pw, ph = tw + padx * 2, th + pady * 2
    grad = vgradient(pw, ph, [mix(accent, "#ffffff", 0.18), accent])
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=ph // 2, fill=255)
    pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    pill.paste(grad, (0, 0), mask)
    ImageDraw.Draw(pill).text((padx + ox, (ph - th) // 2 + oy), text, font=f, fill=(15, 15, 25, 255))
    return with_shadow(pill, blur=22, dy=8, alpha=120)


def chip(text, config, fonts, size=32):
    f = fonts.get(size, 500)
    tw, th, ox, oy = measure(f, text)
    accent = hexa(config["brand"].get("primary", "#5B8DEF"))
    padx, pady = 32, 18
    pw, ph = tw + padx * 2, th + pady * 2
    pill = rounded((pw, ph), ph // 2, (0, 0, 0, 110),
                   stroke=(accent[0], accent[1], accent[2], 80), stroke_w=2)
    ImageDraw.Draw(pill).text((padx + ox, (ph - th) // 2 + oy), text, font=f, fill=(255, 255, 255, 220))
    return pill


def logo_bug(config, fonts):
    name = config["brand"].get("name", "")
    f = fonts.get(30, 700)
    tw, th, ox, oy = measure(f, name)
    accent = hexa(config["brand"].get("primary", "#5B8DEF"))
    dot, gap, padx, pady = 18, 12, 26, 16
    pw = dot + gap + tw + padx * 2
    ph = max(th, dot) + pady * 2
    pill = rounded((pw, ph), ph // 2, (0, 0, 0, 110))
    d = ImageDraw.Draw(pill)
    by = ph // 2
    d.ellipse([padx, by - dot // 2, padx + dot, by + dot // 2], fill=accent)
    d.text((padx + dot + gap + ox, (ph - th) // 2 + oy), name, font=f, fill=(255, 255, 255, 235))
    return pill


# ----------------------------- Scene -----------------------------
class _El:
    def __init__(self, img, cx, cy, anim=None, wipe_join=None, z=0):
        self.img, self.cx, self.cy = img, cx, cy
        self.anim, self.wipe_join, self.z = anim, wipe_join, z


def _apply_opacity(img, op):
    if op >= 0.999:
        return img
    a = img.getchannel("A").point(lambda v: int(v * op))
    out = img.copy()
    out.putalpha(a)
    return out


class Scene:
    def __init__(self, config, tl):
        self.cfg = config
        self.tl = tl
        self.W, self.H = config["resolution"]
        self.total = tl["total"]
        pers = config.get("personality", "playful")
        fonts = Fonts(config)
        self.els = []

        # ---- captions ----
        for c in config.get("captions", []):
            img = caption_pill(c["text"], config, fonts)
            anim = motion.Appear(c["start"], c["end"], pers, rise=24)
            self.els.append(_El(img, self.W // 2, int(self.H * 0.80), anim=anim, z=20))

        # ---- logo bug ----
        if config.get("logo_bug", True) and tl["demo_end"] > tl["demo_start"]:
            img = logo_bug(config, fonts)
            anim = motion.Appear(tl["demo_start"] + 0.2, tl["outro_start"] - 0.2, pers, pop=False)
            self.els.append(_El(img, self.W - img.width // 2 - 24, self.H - img.height // 2 - 20,
                                anim=anim, z=15))

        # ---- wipes ----
        if config.get("transitions", "wipe") == "wipe":
            panel = self._wipe_panel(fonts)
            for j in tl["joins"]:
                self.els.append(_El(panel, self.W // 2, self.H // 2, wipe_join=j, z=40))

        # ---- intro ----
        if tl["intro_dur"] > 0:
            bg = brand_bg(self.W, self.H, config)
            self.els.append(_El(bg, self.W // 2, self.H // 2,
                                anim=motion.Appear(0, tl["intro_dur"] - 0.30, pers,
                                                   enter=0.25, exit=0.30, pop=False), z=50))
            title = self._token(config.get("intro", {}).get("title", "{brand.name}"))
            wm = text_img(title, fonts.get(120, 900), "#ffffff", shadow=True)
            self.els.append(_El(wm, self.W // 2, int(self.H * 0.46),
                                anim=motion.Appear(0.3, tl["intro_dur"] - 0.18, pers,
                                                   enter=0.42, start_scale=0.84, rise=10), z=55))
            sub = self._token(config.get("intro", {}).get("subtitle", "{brand.tagline}"))
            if sub:
                si = text_img(sub, fonts.get(42, 500), (255, 255, 255, 235), shadow=True)
                self.els.append(_El(si, self.W // 2, int(self.H * 0.57),
                                    anim=motion.Appear(0.55, tl["intro_dur"] - 0.18, pers,
                                                       enter=0.4, rise=18), z=55))

        # ---- outro ----
        if tl["outro_dur"] > 0:
            self._build_outro(config, fonts, pers)

    # -- helpers --
    def _token(self, s):
        if not s:
            return s
        return (s.replace("{brand.name}", self.cfg["brand"].get("name", ""))
                 .replace("{brand.tagline}", self.cfg["brand"].get("tagline", "") or ""))

    def _wipe_panel(self, fonts):
        bg = brand_bg(self.W, self.H, self.cfg)
        name = self.cfg["brand"].get("name", "")
        if name:
            wm = text_img(name, fonts.get(60, 900), "#ffffff", shadow=True)
            bg.alpha_composite(wm, ((self.W - wm.width) // 2, (self.H - wm.height) // 2))
        return bg

    def _build_outro(self, config, fonts, pers):
        os_, dur = self.tl["outro_start"], self.tl["outro_dur"]
        W, H = self.W, self.H
        outro = config.get("outro", {})
        end_card = outro.get("end_card", True) and dur > 4
        bg = brand_bg(W, H, config)
        self.els.append(_El(bg, W // 2, H // 2,
                            anim=motion.Appear(os_, None, pers, enter=0.32, pop=False), z=60))
        # logo (persists)
        logo = load_logo(config, target=236)
        logo = with_shadow(logo, blur=26, dy=10, alpha=120)
        self.els.append(_El(logo, W // 2, int(H * 0.38),
                            anim=motion.Appear(os_ + 0.2, None, pers, enter=0.42,
                                               start_scale=0.7, rise=0), z=62))
        tx_msg = (os_ + min(3.0, dur * 0.5)) if end_card else None
        ystack = [("headline", 0.55), ("cta", 0.66), ("link", 0.75), ("footnote", 0.83)]
        delays = {"headline": 0.4, "cta": 0.6, "link": 0.82, "footnote": 1.05}
        if outro.get("headline"):
            img = text_img(outro["headline"], fonts.get(66, 900), "#ffffff", shadow=True)
            self.els.append(_El(img, W // 2, int(H * 0.55),
                                anim=motion.Appear(os_ + delays["headline"], tx_msg, pers, rise=20), z=63))
        if outro.get("cta_text"):
            img = button(outro["cta_text"], config, fonts)
            self.els.append(_El(img, W // 2, int(H * 0.66),
                                anim=motion.Appear(os_ + delays["cta"], tx_msg, pers,
                                                   start_scale=0.86, rise=16), z=63))
        if outro.get("link"):
            img = chip(outro["link"], config, fonts)
            self.els.append(_El(img, W // 2, int(H * 0.75),
                                anim=motion.Appear(os_ + delays["link"], tx_msg, pers, rise=14), z=63))
        if outro.get("footnote"):
            img = text_img(outro["footnote"], fonts.get(30, 500), (255, 255, 255, 230), shadow=True)
            self.els.append(_El(img, W // 2, int(H * 0.83),
                                anim=motion.Appear(os_ + delays["footnote"], tx_msg, pers, rise=12), z=63))
        if end_card:
            name = text_img(config["brand"].get("name", ""), fonts.get(100, 900), "#ffffff", shadow=True)
            self.els.append(_El(name, W // 2, int(H * 0.55),
                                anim=motion.Appear(tx_msg + 0.35, None, pers, enter=0.5,
                                                   start_scale=0.84, rise=16), z=63))

    # -- per-frame render --
    def render_frame(self, t):
        frame = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        for el in sorted(self.els, key=lambda e: e.z):
            if el.wipe_join is not None:
                dx, op = motion.slide_x(t, el.wipe_join, width=self.W)
                if op <= 0:
                    continue
                img = _apply_opacity(el.img, op)
                frame.alpha_composite(img, (int(el.cx - img.width / 2 + dx),
                                            int(el.cy - img.height / 2)))
                continue
            op, scale, dy = el.anim.at(t)
            if op <= 0.003:
                continue
            img = el.img
            if abs(scale - 1.0) > 0.005:
                nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
                img = img.resize((nw, nh), Image.BILINEAR)
            img = _apply_opacity(img, op)
            x = int(el.cx - img.width / 2)
            y = int(el.cy - img.height / 2 - dy)
            frame.alpha_composite(img, (x, y))
        return frame
