#!/usr/bin/env python3
"""Refuse to publish a video whose title or thumbnail is not fit to ship.

A session publishes unattended for hours, so every quality rule that lives
only in a document is a rule that will eventually be skipped by a tired loop
at two in the morning. These are the ones that are not negotiable, expressed
as a program that exits non-zero:

* a title that is present, distinct, and not the shared topical fallback;
* a thumbnail that exists, carries its title card, and still carries it after
  the crop the platform is actually going to apply.

All three failures shipped in one session. Forty-three Shorts served a
truncated headline over an empty red band, and five carried the same generic
title because quote mining had rejected their audio. None of it was visible
from inside the pipeline, because every individual step reported success:
the renderer rendered, the uploader uploaded, and the defect only existed in
the crop nobody looked at.

    python3 publishgate.py publish/sh07            # one item
    python3 publishgate.py publish/*/ --json       # a whole session

Exit status is 0 only if every item passed.
"""
import argparse
import glob
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:                                    # pragma: no cover
    print("publishgate: needs Pillow and numpy", file=sys.stderr)
    raise

# YouTube's own ceiling for a custom thumbnail.
MAX_BYTES = 2 * 1024 * 1024
MAX_TITLE = 100

# A band is "the title card" when it covers most of the width. Ink is measured
# only inside it, because the surrounding photo is full of dark and light
# pixels that would otherwise read as text.
BAND_COVER = 0.55
MIN_INK = 0.010          # glyph pixels within the band


def _bands(a):
    """Row ranges of the paper (near-white) and red title cards."""
    red = (a[:, :, 0] > 110) & (a[:, :, 1] < 70) & (a[:, :, 2] < 70)
    paper = (a[:, :, 0] > 200) & (a[:, :, 1] > 200) & (a[:, :, 2] > 195)
    out = []
    for mask, kind in ((paper, "paper"), (red, "red")):
        rows = [i for i in range(a.shape[0]) if mask[i].mean() > BAND_COVER]
        if rows:
            out.append((kind, rows[0], rows[-1] + 1, mask))
    return out


def _ink(a, kind, top, bot, mask):
    """Glyph pixels inside one band, and the band's own column extent.

    The column extent matters. A band qualifies on covering most of the
    width, not all of it, so at the far left and right of those rows there
    can still be photograph -- and photograph contains dark pixels, which
    read as glyphs. Measuring across the full width therefore reports that
    every thumbnail's text runs off the edge. Ink is only meaningful inside
    the card itself.
    """
    band = a[top:bot]
    if kind == "paper":
        ink = (band[:, :, 0] < 90) & (band[:, :, 1] < 90) & (band[:, :, 2] < 90)
    else:
        ink = ((band[:, :, 0] > 200) & (band[:, :, 1] > 200)
               & (band[:, :, 2] > 200))
    card = mask[top:bot].mean(axis=0) > 0.5
    cols = np.where(card)[0]
    if cols.size == 0:
        return ink, 0, ink.shape[1] - 1
    lo, hi = int(cols[0]), int(cols[-1])
    keep = np.zeros(ink.shape[1], dtype=bool)
    keep[lo:hi + 1] = True
    return ink & keep, lo, hi


def check_image(path, portrait):
    """Problems with one thumbnail file, as a list of strings."""
    bad = []
    if not os.path.exists(path):
        return [f"no thumbnail at {path}"]
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        bad.append(f"thumbnail is {size/1e6:.1f} MB, over YouTube's 2 MB limit")
    try:
        im = Image.open(path).convert("RGB")
    except Exception as e:
        return [f"thumbnail will not open ({str(e)[:40]})"]
    if im.width < 1280 or im.height < 720:
        bad.append(f"thumbnail is {im.width}x{im.height}, under 1280x720")

    layout = _layout(path)
    if layout is not None:
        return bad + _check_layout(layout, im, portrait)
    return bad + _check_pixels(im, portrait)


def _layout(path):
    p = path + ".layout.json"
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        return None
    return d if d.get("blocks") else None


def _check_layout(layout, im, portrait):
    """Exact check: does every text block survive the crop that gets served?

    Preferred over reading pixels, because the renderer already knows where
    it put the text and a pixel search does not. Searching for a near-white
    card and dark glyphs inside it finds a speaker's white shirt with a
    shadow on it just as readily, which is a false accusation, and it cannot
    distinguish a whole word from the tail of one, which is a false pass.
    """
    bad = []
    for kind, x0, x1 in _views(im.width, im.height, portrait):
        for b in layout["blocks"]:
            bx, _by, bw, _bh = b["bbox"]
            if bw <= 0:
                bad.append(f"{kind}: {b['kind']} has no text")
                continue
            if bx < x0 - 1 or bx + bw > x1 + 1:
                lost = bw - max(0, min(bx + bw, x1) - max(bx, x0))
                how = ("entirely outside the frame" if lost >= bw
                       else f"{lost}px of {bw} outside the frame")
                bad.append(f"{kind}: {b['kind']} is cut off "
                           f"({how}) — {b['text'][:24]!r}")
    return bad


def _views(w, h, portrait):
    """The horizontal windows a thumbnail has to survive, as (name, x0, x1)."""
    out = [("16:9", 0, w)]
    if portrait:
        # A Short's tile is centre-cropped to 9:16, keeping 405 of 1280 px --
        # under a third of the canvas. This is the view that actually gets
        # served, and the one that is never looked at.
        cw = int(h * 9 / 16)
        x = (w - cw) // 2
        out.append(("9:16", x, x + cw))
    return out


def _check_pixels(im, portrait):
    """Fallback for a thumbnail this pipeline did not render.

    Deliberately conservative: it can only report a card that is completely
    empty, which is unambiguous. It does not try to judge truncation, because
    without knowing where the text was meant to be it cannot tell a short
    word from a cut one.
    """
    bad = []
    for label, x0, x1 in _views(im.width, im.height, portrait):
        a = np.asarray(im.crop((x0, 0, x1, im.height))).astype(int)
        bands = _bands(a)
        if not bands:
            bad.append(f"{label}: no title card at all")
            continue
        for kind, top, bot, mask in bands:
            ink, _lo, _hi = _ink(a, kind, top, bot, mask)
            if ink.mean() < MIN_INK:
                bad.append(f"{label}: the {kind} title card is empty")
    return bad


def _title_of(item):
    for rel in ("meta/metadata.json", "meta/youtube_metadata.json"):
        p = os.path.join(item, rel)
        if os.path.exists(p):
            try:
                t = json.load(open(p)).get("title")
            except (OSError, ValueError):
                continue
            if t:
                return t.strip()
    return ""


def _thumb_of(item):
    for rel in ("out/thumbnail.jpg", "out/thumbnail.png", "meta/thumbnail.jpg"):
        p = os.path.join(item, rel)
        if os.path.exists(p):
            return p
    return os.path.join(item, "out/thumbnail.jpg")


def check_item(item, titles_seen, portrait=None):
    """Everything that must hold before this directory may be uploaded."""
    name = os.path.basename(item.rstrip("/"))
    if portrait is None:
        portrait = name.startswith("sh")
    bad = []

    title = _title_of(item)
    if not title:
        bad.append("no title")
    else:
        if len(title) > MAX_TITLE:
            bad.append(f"title is {len(title)} chars, over {MAX_TITLE}")
        # A title shared with another video is either the topical fallback,
        # used when quote mining gave up, or a mis-paired quote carrying
        # another video's words. Both are wrong, and neither is detectable by
        # reading the title on its own -- only by comparing the set.
        other = titles_seen.get(title)
        if other and other != name:
            bad.append(f"title is identical to {other}'s")
        else:
            titles_seen.setdefault(title, name)

    bad += check_image(_thumb_of(item), portrait)
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("items", nargs="+", help="publish/<id> directories")
    ap.add_argument("--portrait", action="store_true",
                    help="treat every item as a Short")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    items = []
    for pat in a.items:
        items += sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
    items = [i for i in items if os.path.isdir(i)]

    seen, report, failed = {}, {}, 0
    for item in items:
        bad = check_item(item, seen, True if a.portrait else None)
        name = os.path.basename(item.rstrip("/"))
        report[name] = bad
        if bad:
            failed += 1

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for name, bad in report.items():
            if bad:
                print(f"REFUSED {name}")
                for b in bad:
                    print(f"    {b}")
        print(f"{len(items) - failed}/{len(items)} fit to publish")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
