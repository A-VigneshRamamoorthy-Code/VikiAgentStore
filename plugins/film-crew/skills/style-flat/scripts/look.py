"""Mid-century flat vector — the look layer.

This style is the deliberate inverse of `style-paper`. Where paper is muted,
grained, torn-edged and shadowed, this is **saturated, perfectly flat, hard
edged and shadowless**. The two exist so a story can be shot twice and
compared, and they are only worth comparing if they disagree about everything.

    paper                          flat
    ---------------------------    ---------------------------
    beige stock, mottled           one saturated colour field
    white torn border on every     no border at all
      cut-out
    contact shadow under every     no shadow; depth is overlap
      piece                          and overlap only
    grain over the whole frame     no texture whatsoever
    one ink for the whole film     a designed palette per mood

The historical ground is UPA — *Gerald McBoing-Boing* (1950), *Rooty Toot
Toot* (1951) — together with Saul Bass's title sequences and Mary Blair's
concept art. That lineage matters for more than looks: **UPA invented limited
animation**. Held backgrounds, sliding layers, pose-to-pose with no
in-betweens and "transition as animation" are all theirs, so every
frame-saving technique the engine already uses is native to this style rather
than borrowed into it.

Nothing here draws illustrations. It re-points the three functions that make
the paper look — the sticker border, the grain, and the parchment background
— at flat equivalents, so all forty-odd existing drawings render in the new
style without being redrawn. That is the whole trick, and it is why a second
style costs a few hundred lines instead of a few thousand.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# --------------------------------------------------------------- palettes ----

#: Mood -> flat-vector palette. `field`/`field2` are the background colour
#: field (a two-stop vertical gradient, which is the only gradient this style
#: permits); `papers` are the sheets the shapes are cut from; `ink` is used
#: for scenery so it sits behind the subject.
#:
#: These are taken from the researched mid-century references rather than
#: invented: deep midnight against cadmium lemon and hot magenta is the Saul
#: Bass register, and the tender and curious rows are Mary Blair's.
PALETTES = {
    "dread": {
        "field": "#0D0D12", "field2": "#2A0A12",
        "ink": "#1A1A22",
        "papers": ["#CC2222", "#FFD700", "#881838", "#E8552F", "#5A1F3A"],
        "note": "near-black with one bright warning — menace",
    },
    "elegy": {
        "field": "#1C1C2E", "field2": "#2E3A5C",
        "ink": "#242437",
        "papers": ["#7A8BA8", "#A8B8D0", "#5B6B8C", "#C9A227", "#8E7BA6"],
        "note": "cold blues, one warm note — grief",
    },
    "tension": {
        "field": "#181818", "field2": "#3A1A1A",
        "ink": "#101010",
        "papers": ["#FF4444", "#FF8C00", "#F2F2F2", "#7A1F1F", "#2E6E8E"],
        "note": "stark reds against black — threat",
    },
    "curious": {
        "field": "#F7F3E8", "field2": "#FFE066",
        "ink": "#3A3226",
        "papers": ["#FF6B35", "#41C7B9", "#E84686", "#2E5F8A", "#F2B705"],
        "note": "bright, warm, open — discovery",
    },
    "tender": {
        "field": "#FFF0F5", "field2": "#FFB5C2",
        "ink": "#5C4450",
        "papers": ["#E8709F", "#B896E6", "#FFB067", "#6FB7C4", "#D64D7A"],
        "note": "Mary Blair pinks and violets — intimacy",
    },
    "triumph": {
        "field": "#0A1628", "field2": "#1E3A5F",
        "ink": "#16233A",
        "papers": ["#FFD700", "#FF4500", "#F2F2F2", "#41C7B9", "#E84686"],
        "note": "gold on midnight — arrival",
    },
    "reflective": {
        "field": "#1A2744", "field2": "#2E4A6E",
        "ink": "#20304F",
        "papers": ["#6EB5C0", "#A8C4D4", "#F2E85C", "#4A7FA5", "#D98E5A"],
        "note": "petrol blues with one warm note — memory",
    },
    "voyage": {
        "field": "#10344A", "field2": "#1F6E82",
        "ink": "#16394D",
        # The fifth sheet was #2E5F8A, which sat 39.6 redmean from this
        # palette's own #1F6E82 field — every other sheet in every other
        # palette clears 99. Anything cut from it stopped reading as a shape
        # and became a dark hole in the water, which is the "it went grey
        # again" defect. Violet is the far corner from the teal/yellow/orange
        # the rest of the set occupies, and clears 241 against both.
        "papers": ["#41C7B9", "#F2E85C", "#E8703A", "#8FD6C8", "#B04AC7"],
        "note": "sea blues and a hot sail — distance",
    },
}

DEFAULT = "reflective"

#: How a `style-paper` palette name maps onto a flat one, so the same story
#: chooses a coherent look in either style rather than two unrelated ones.
FROM_PAPER = {
    "noir": "dread", "ash": "elegy", "ember": "triumph", "tide": "voyage",
    "dust": "curious", "moss": "curious", "bone": "reflective",
    "sepia": "reflective",
}

#: `score.py` moods that are not palette names in their own right.
FROM_MOOD = {
    "memorial": "elegy", "crime": "dread", "warm": "tender",
    "wonder": "curious", "pastoral": "curious", "drive": "tension",
    "music_box": "tender", "clinical": "reflective", "arid": "curious",
    "record": "reflective", "warmth": "tender",
}


def choose(paper_name=None, mood=None):
    """``(name, palette)`` for a film, from whatever the story already chose."""
    for key in (mood, paper_name):
        if not key:
            continue
        if key in PALETTES:
            return key, dict(PALETTES[key])
        for table in (FROM_MOOD, FROM_PAPER):
            if key in table:
                return table[key], dict(PALETTES[table[key]])
    return DEFAULT, dict(PALETTES[DEFAULT])


def _rgb(h):
    """Accept ``#rrggbb``, ``rrggbb`` or an already-unpacked RGB(A) tuple.

    Colours reach this module from two directions — hex strings out of the
    palette tables, and integer tuples out of the engine, whose callers pass
    their own stock colour down into `parchment`. Taking both means neither
    side has to know which one it is holding.
    """
    if isinstance(h, (tuple, list)):
        return tuple(int(c) for c in h[:3])
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------ flat pieces ----


def colour_field(w: int, h: int, top, bottom, seed: int = 0) -> Image.Image:
    """The background: one two-stop vertical gradient and nothing else.

    Paper's `parchment` builds mottle, fibre, blotches and edge darkening.
    All of that is texture, and texture is exactly what this style does not
    have. What replaces it is *colour* — a large, confident field that the
    shapes are arranged on.

    The one concession is a faint dither. An 8-bit vertical gradient across
    1080 lines bands visibly, and banding is a rendering artefact rather than
    a design choice, so it is removed by adding sub-LSB noise before the
    quantisation that causes it.
    """
    t = np.array(_rgb(top), dtype=np.float32)
    b = np.array(_rgb(bottom), dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    # eased rather than linear: a straight ramp reads as a technical
    # gradient, an eased one reads as sky
    ramp = ramp * ramp * (3.0 - 2.0 * ramp)
    field = t[None, None, :] + (b - t)[None, None, :] * ramp[:, :, None]
    field = np.repeat(field, w, axis=1)
    rng = np.random.default_rng(seed)
    field += rng.uniform(-0.6, 0.6, size=field.shape).astype(np.float32)
    out = np.clip(field, 0, 255).astype(np.uint8)
    img = Image.fromarray(out, "RGB").convert("RGBA")
    return img


def flat_sticker(img, *_args, **_kwargs):
    """No border, no shadow — the shape as drawn.

    `collage.sticker` is what makes a drawing read as a piece of cut paper:
    it grows the alpha channel into a white margin and drops a contact shadow
    under it. Both are removed here, and removing them is most of the visual
    difference between the two styles. A flat shape with a hard edge sitting
    directly on a colour field is the entire UPA vocabulary.
    """
    return img


def no_grain(img, *_args, **_kwargs):
    """Grain is the medium showing through. This style has no medium."""
    return img
