#!/usr/bin/env python3
"""Prove the stage's geometry before committing a film to it.

Three constants in build_scene.py can each be wrong in a way that renders
perfectly cleanly and is only obvious side by side with what you meant: the
plane's roll, the direction texture V runs, and which way the camera reads X.
A mirrored film looks *fine* until you notice every character faces the wrong
way and the sun sets in the east.

So this generates artwork whose correct orientation is unambiguous, feeds it
through the real build path, and lets one rendered frame settle it.

    python3 orient_test.py /tmp/orient
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

STAGE_W, STAGE_H = 1920.0, 1080.0
CAM_DIST = 4000.0

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return None


def label(draw, xy, text, fill, size=48):
    """Draw text, falling back to an upscaled bitmap font when no TTF exists.

    Legibility is the entire point of this test image, so it must not quietly
    degrade to something unreadable.
    """
    f = font(size)
    if f is not None:
        draw.text(xy, text, fill=fill, font=f)
        return

    small = Image.new("RGBA", (len(text) * 7 + 4, 12), (0, 0, 0, 0))
    ImageDraw.Draw(small).text((1, 0), text, fill=fill,
                               font=ImageFont.load_default())
    k = max(1, size // 10)
    big = small.resize((small.width * k, small.height * k), Image.NEAREST)
    draw._image.paste(big, (int(xy[0]), int(xy[1])), big)


def backdrop(path, w=2400, h=1400):
    """A grid whose corners say which corner they are. If the image is flipped
    or mirrored the labels end up somewhere they cannot be."""
    img = Image.new("RGBA", (w, h), (28, 34, 52, 255))
    d = ImageDraw.Draw(img)

    for x in range(0, w, 100):
        d.line([x, 0, x, h], fill=(52, 62, 92, 255), width=2)
    for y in range(0, h, 100):
        d.line([0, y, w, y], fill=(52, 62, 92, 255), width=2)

    m = 60
    label(d, (m, m), "TOP-LEFT", (250, 210, 90, 255), 90)
    label(d, (w - 700, m), "TOP-RIGHT", (250, 210, 90, 255), 90)
    label(d, (m, h - 160), "BOTTOM-LEFT", (120, 220, 250, 255), 90)
    label(d, (w - 830, h - 160), "BOTTOM-RIGHT", (120, 220, 250, 255), 90)

    # A wedge that is only this shape when the image is the right way up.
    d.polygon([(w // 2, 200), (w // 2 - 160, 560), (w // 2 + 60, 560)],
              fill=(230, 90, 110, 255))
    d.rectangle([0, 0, w - 1, h - 1], outline=(240, 240, 240, 255), width=6)
    img.save(path)
    return path


def cutout(path, w=400, h=900):
    """An asymmetric figure with real alpha, facing screen RIGHT. Mirrored, it
    faces left and the F reads backwards."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([120, 40, 300, 220], fill=(240, 200, 160, 255))     # head
    d.rectangle([140, 220, 280, 620], fill=(240, 186, 70, 255))   # body
    d.rectangle([280, 300, 380, 360], fill=(240, 186, 70, 255))   # arm, pointing right
    d.rectangle([150, 620, 200, 860], fill=(86, 60, 44, 255))     # legs
    d.rectangle([225, 620, 275, 860], fill=(86, 60, 44, 255))
    label(d, (160, 350), "F", (20, 20, 30, 255), 190)              # reversed if mirrored
    d.ellipse([250, 90, 280, 120], fill=(30, 30, 40, 255))        # eye on the right
    img.save(path)
    return path


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/orient"
    os.makedirs(out, exist_ok=True)

    bg = backdrop(os.path.join(out, "orient_bg.png"))
    fg = cutout(os.path.join(out, "orient_fig.png"))

    def shot(i, sid, flip, cam_from, cam_to, note):
        bay = i * 60000.0
        return {
            "id": sid, "index": i, "set": "test", "bay_x": bay,
            "start": i * 2.0, "end": (i + 1) * 2.0,
            "tier": "limited", "note": note, "mist": 0.0,
            "camera": {
                "from": {"x": bay + cam_from[0], "y": CAM_DIST / cam_from[2],
                         "z": cam_from[1]},
                "to": {"x": bay + cam_to[0], "y": CAM_DIST / cam_to[2],
                       "z": cam_to[1]},
                "move": "push", "ease": "linear", "hold": 0.0,
            },
            "layers": [{
                "texture": bg, "x": bay, "y": -900.0, "z": 0.0,
                "fit": "cover", "ratio": (CAM_DIST + 900.0) / CAM_DIST,
                "cover": 1.2, "tint": None, "opacity": 1.0,
            }],
            "actors": [{
                "id": "fig", "texture": fg,
                "x": bay - 300.0, "y": 0.0, "z": -120.0,
                "to": {"x": bay + 320.0, "z": -120.0},
                "height_uu": 620.0, "fit": "height", "flip": flip,
                "ease": "linear", "action": "walk",
            }],
            "props": [],
        }

    scene = {
        "schema": 1, "title": "orientation test",
        "fps": 30, "width": 1920, "height": 1080, "duration": 4.0,
        "stage": {"w": STAGE_W, "h": STAGE_H, "cam_dist": CAM_DIST},
        "lens": {"focal_mm": 50.0, "sensor_w": 23.76, "sensor_h": 13.365},
        "palette": None,
        "shots": [
            shot(0, "t1", False, (0, 0, 1.0), (150, 0, 1.15),
                 "figure faces RIGHT, walks RIGHT, camera pushes in"),
            shot(1, "t2", True, (0, 0, 1.0), (0, 0, 1.0),
                 "same figure mirrored: must face LEFT"),
        ],
        "warnings": [],
    }

    path = os.path.join(out, "scene.json")
    with open(path, "w") as fh:
        json.dump(scene, fh, indent=1)

    print("wrote %s" % path)
    print("""
what the render must show
  frame 1  backdrop labels read TOPLEFT / TOPRIGHT on top,
           BOTLEFT / BOTRIGHT beneath, none of them mirrored;
           red wedge points UP; figure faces RIGHT with its eye and
           arm on the right; it walks left-to-right as the camera pushes in
  frame 2  the same figure facing LEFT

  if the labels are upside down     -> PLANE_ROLL is inverted
  if the text reads backwards       -> camera yaw is mirrored (+90 not -90)
  if the wedge points down          -> texture V runs the other way
  if nothing but black              -> material was not saved before capture
""")


if __name__ == "__main__":
    main()
