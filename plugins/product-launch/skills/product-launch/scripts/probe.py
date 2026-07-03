"""Contact-sheet generation: extract evenly-spaced frames and tile them with
time labels, so the agent can review footage and choose segments/caption times.
"""
from __future__ import annotations
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

import ffmpeg_utils


def _label_font(size):
    for p in ["/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def contact_sheet(ffmpeg, input_path, out_path, duration, n=24, cols=4, cell_w=440):
    times = [duration * i / max(1, n - 1) for i in range(n)]
    rows = (n + cols - 1) // cols
    cell_h = int(cell_w * 9 / 16)
    pad = 6
    sheet = None
    font = _label_font(18)
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(times):
            fp = os.path.join(td, f"f{i:03d}.png")
            r = ffmpeg_utils.run([ffmpeg, "-y", "-ss", f"{max(0, t-0.001):.3f}", "-i", input_path,
                                  "-frames:v", "1", "-vf", f"scale={cell_w}:-1", fp])
            if not os.path.exists(fp):
                continue
            try:
                cell = Image.open(fp).convert("RGB")
            except Exception:
                continue
            if sheet is None:
                ch = cell.height
                sheet = Image.new("RGB", (cols * (cell_w + pad) + pad, rows * (ch + pad) + pad), (30, 30, 36))
                cell_h = ch
            c, rr = i % cols, i // cols
            x = pad + c * (cell_w + pad)
            y = pad + rr * (cell_h + pad)
            sheet.paste(cell, (x, y))
            d = ImageDraw.Draw(sheet)
            lab = f"{t:.1f}s"
            d.rectangle([x + 3, y + 3, x + 3 + 9 * len(lab) + 8, y + 26], fill=(0, 0, 0))
            d.text((x + 7, y + 5), lab, fill=(255, 220, 0), font=font)
    if sheet is None:
        raise RuntimeError("Could not extract frames for the contact sheet (check ffmpeg/input).")
    sheet.save(out_path)
    return out_path
