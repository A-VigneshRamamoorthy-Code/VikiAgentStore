"""Generate a 1280x720 thumbnail in the paper documentary style.

The sibling `thumbnail.py` renders the news-debate look: a red band, a gold
"VS" burst, lightning. That is the right thumbnail for an argument show and
the wrong one for a documentary -- on a film about people who were killed it
reads as tasteless, and it also lies about the video, which is the one thing a
thumbnail must not do.

This renders the same artwork the film is made of, so the thumbnail is
continuous with the first frame the viewer sees:

    +----------------------------------------------------+
    |  [STAMP]                                           |
    |                                                    |
    |   HEADLINE          .-.                            |
    |   HEADLINE       ( subject illustration )          |
    |   ~~~~~~~~~~~~                                     |
    |   kicker line                                      |
    +----------------------------------------------------+

Everything is driven by `meta/thumbnail.json`, so it is reusable for any film
built with the paper style:

    {
      "style":    "doc",
      "headline": ["SIXTY", "HOURS"],
      "kicker":   "MUMBAI - 26 NOVEMBER 2008",
      "stamp":    "CASE FILE",
      "subject":  {"fn": "grand_hotel", "w": 900, "h": 520},
      "smoke":    {"w": 620, "h": 620, "density": 0.95},
      "seed":     7
    }

`subject.fn` names any function in the paper style's `illustrations.py`, so a
different film points at `mumbai_map`, `figure`, `boat` and so on without
touching this file.

The hard constraint is the 168px-wide search result. Two short words stacked
at this weight survive that; a sentence does not. The renderer therefore
measures the headline and refuses to emit a thumbnail whose text would fall
below the legibility floor, rather than quietly shipping mush.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

import _shared  # noqa: F401  (locates config.py)
from config import LIMITS, Publish

# production-designer owns the art styles. Import the paper style rather
# than reimplementing it, so the thumbnail cannot drift away from the film's own
# look.
_SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_REGISTRY = os.path.join(_SKILLS, "production-designer", "scripts")
sys.path.insert(0, _REGISTRY)
try:
    import registry as _registry  # noqa: E402
    _PAPER_SCRIPTS = _registry.style_scripts("paper")
except (ImportError, LookupError) as exc:
    raise SystemExit(
        "the paper style is required for documentary thumbnails. Install the "
        f"style-paper skill alongside head-of-marketing. ({exc})")
if not os.path.isdir(_PAPER_SCRIPTS):
    raise SystemExit(
        "the paper style is required for documentary thumbnails but its "
        f"scripts directory was not found at {_PAPER_SCRIPTS}. Ensure "
        "style-paper/scripts is installed alongside "
        "head-of-marketing.")
sys.path.insert(0, _PAPER_SCRIPTS)

import collage as C  # noqa: E402
import illustrations as I  # noqa: E402
import paper as P  # noqa: E402

TW, TH = 1280, 720

# Below roughly this cap height the headline stops being readable once YouTube
# has scaled the thumbnail to a search row. Measured, not guessed: 168/1280 is
# a 7.6x reduction, so a 96px cap lands at ~12px on screen.
MIN_CAP_PX = 96


def _headline(img, lines, seed, max_w, top, left):
    """Stack the headline, fitted to `max_w`, and underline the last line."""
    size = 190
    while size > MIN_CAP_PX:
        f = C.font("display", size, 900, 74)
        if max(C.text_width(f, ln, 2.0) for ln in lines) <= max_w:
            break
        size -= 4
    else:
        raise SystemExit(
            f"headline {lines!r} cannot fit {max_w}px above the {MIN_CAP_PX}px "
            "legibility floor -- break it across more lines (\"LINE ONE\\n"
            "LINE TWO\", or a list of 2-3 lines), widen `headline_width`, "
            "or use shorter words")

    f = C.font("display", size, 900, 74)
    y = top
    last_x1 = left
    for ln in lines:
        strip = Image.new("RGBA", (int(C.text_width(f, ln, 2.0)) + 8,
                                   int(size * 1.35)), (0, 0, 0, 0))
        d = ImageDraw.Draw(strip)
        box = f.getbbox(ln)
        C.tracked_text(d, (0, -box[1] + int(size * 0.08)), ln, f,
                       P.PALETTE["ink"] + (255,), 2.0)
        strip = P.drop_shadow(strip, blur=10, dy=5, dx=2, alpha=90)
        img.alpha_composite(strip, (left - 12, int(y)))
        last_x1 = max(last_x1, left + C.text_width(f, ln, 2.0))
        y += size * 1.02

    # A marker rule under the last word does the job the red band did in the
    # debate style: one saturated shape so the eye lands somewhere.
    rule = C.marker_underline(img.size, left, int(last_x1),
                              int(y + size * 0.02), width=14, seed=seed + 3)
    img.alpha_composite(rule)
    return int(y + size * 0.16), size, last_x1


def render(spec, out_path):
    seed = int(spec.get("seed", 7))
    img = P.parchment(TW, TH, seed=seed).convert("RGBA")

    # The best documentary thumbnails often carry no text at all -- the image
    # is the whole claim, and a title fights it. That is a different layout,
    # not an absent headline, so it is opted into explicitly: leaving
    # `headline` out by accident still fails loudly.
    layout = str(spec.get("layout", "headline")).strip().lower()
    if layout not in ("headline", "art-only"):
        raise SystemExit(
            f"unknown layout {layout!r} -- use \"headline\" (text left, "
            "subject right) or \"art-only\" (a centred subject, no text)")

    # Subject illustration on the right, with optional smoke behind it. Drawn
    # before the text so the headline always wins any overlap.
    art_left = None
    sub = spec.get("subject") or {}
    if sub.get("fn"):
        fn = getattr(I, sub["fn"], None)
        if fn is None:
            raise SystemExit(f"no illustration called {sub['fn']!r}")
        kwargs = {k: v for k, v in sub.items() if k not in ("fn", "x", "y")}
        art = fn(seed=seed, **kwargs)
        if layout == "art-only":
            ax = int(sub.get("x", (TW - art.width) // 2))
            ay = int(sub.get("y", (TH - art.height) // 2))
        else:
            ax = int(sub.get("x", TW - art.width - 40))
            ay = int(sub.get("y", TH - art.height - 54))

        sm = spec.get("smoke")
        if sm:
            plume = I.smoke(w=int(sm.get("w", 620)), h=int(sm.get("h", 620)),
                            seed=seed + 5,
                            density=float(sm.get("density", 0.95)))
            img.alpha_composite(plume, (
                int(sm.get("x", ax + art.width * 0.46)),
                int(sm.get("y", max(0, ay - plume.height * 0.72)))))

        img.alpha_composite(P.drop_shadow(art, blur=18, dy=10, dx=4,
                                          alpha=120), (ax, ay))
        art_left = ax
    elif layout == "art-only":
        raise SystemExit(
            "an art-only thumbnail is nothing but its subject -- give "
            "`subject.fn`")

    if layout == "art-only":
        return _finish(img, out_path, spec, seed, None)

    left = 64
    top = int(spec.get("top", 150))
    max_w = int(spec.get("headline_width", 700))
    # A headline may be given as a list of lines or as one string with
    # newlines. Passing the string straight through iterates its characters,
    # which silently stacks the headline one letter per line.
    headline = spec.get("headline")
    if headline is None:
        raise SystemExit(
            "no `headline` -- give \"LINE ONE\\nLINE TWO\", or set "
            "\"layout\": \"art-only\" for a thumbnail with no text on it")
    if isinstance(headline, str):
        headline = headline.splitlines()
    headline = [" ".join(str(ln).split()) for ln in headline]
    headline = [ln for ln in headline if ln]
    if not headline:
        raise SystemExit(
            "`headline` is empty -- give \"LINE ONE\\nLINE TWO\" or "
            "[\"LINE ONE\", \"LINE TWO\"]")
    y, cap, text_right = _headline(
        img, headline, seed, max_w, top, left)

    if spec.get("kicker"):
        k = C.typed_line(spec["kicker"], size=int(spec.get("kicker_size", 38)),
                         seed=seed + 7, tracking=1.6)
        img.alpha_composite(k, (left, y + 26))
        text_right = max(text_right, left + k.width)

    # Text over the illustration is the failure this layout invites, and it is
    # invisible in a thumbnail-sized preview -- so it is an error, not a nudge.
    if art_left is not None and text_right > art_left:
        raise SystemExit(
            f"text runs to {int(text_right)}px but the illustration starts at "
            f"{int(art_left)}px -- reduce headline_width or move subject.x")

    return _finish(img, out_path, spec, seed, cap)


def _finish(img, out_path, spec, seed, cap):
    """Tape, vignette, grain, then step quality down to the size cap."""
    if spec.get("stamp"):
        st = C.stamp(spec["stamp"], size=40, seed=seed + 9)
        img.alpha_composite(P.drop_shadow(st, blur=10, dy=5, dx=2, alpha=110),
                            (60, 52))

    for i, (tx, ty, tw_, th_) in enumerate(spec.get(
            "tape", [[-30, 44, 240, 62], [TW - 190, TH - 66, 250, 60]])):
        tape = P.tape_strip(int(tw_), int(th_), seed=seed + 30 + i)
        img.alpha_composite(tape, (int(tx), int(ty)))

    img = P.vignette(img.convert("RGB"), strength=0.34, power=1.7)
    img = P.add_grain(img, amount=7, seed=seed + 11)

    # Quality is stepped down only as far as the 2MB cap requires; the paper
    # texture is noise, so it costs more than a flat graphic would.
    for q in (95, 92, 88, 84, 78, 72):
        img.convert("RGB").save(out_path, "JPEG", quality=q, optimize=True,
                                progressive=True)
        if os.path.getsize(out_path) <= LIMITS["thumbnail_bytes"]:
            return cap, q, os.path.getsize(out_path)
    raise SystemExit(f"cannot fit {out_path} under "
                     f"{LIMITS['thumbnail_bytes']} bytes")


def main():
    ap = argparse.ArgumentParser(
        description="Render a documentary-style thumbnail")
    ap.add_argument("project")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    pub = Publish(a.project)
    spec_path = a.spec or pub.p("meta", "thumbnail.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"missing {spec_path}")
    spec = json.load(open(spec_path))
    out = a.out or pub.thumbnail

    os.makedirs(os.path.dirname(out), exist_ok=True)
    cap, q, size = render(spec, out)
    fit = f"cap {cap}px" if cap else "art-only"
    print(f"{fit}  jpeg q{q}  {size/1024:.0f} KB  -> {out}")


if __name__ == "__main__":
    main()
