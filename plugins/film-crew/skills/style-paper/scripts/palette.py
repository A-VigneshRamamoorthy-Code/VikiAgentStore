"""Palette — let the story choose the film's colour.

Every film this style has ever produced came out the same shade of brown,
because the compiler wrote one hard-coded accent (``#c8402a``) and one paper
stock into every storyboard, and the renderer passed no ink at all to any of
its forty-six drawings. A story about snow and a story about a fire were
rendered in identical sepia. Colour was doing no work.

This module picks a palette from the words of the narration. It is deliberately
a small, legible table rather than anything clever: the point is that a film
about the sea is blue-green and a film about a hearth is warm, and that a
reader of this file can see why a given story got the palette it did and
disagree with it.

Every palette stays *paper*. These are ink-on-stock combinations — a cold grey
sheet with slate ink, a warm cream sheet with sanguine — not screen colours.
The medium does not change; only its temperature does.
"""

from __future__ import annotations

import re

#: Each palette carries the four things the renderer can actually act on
#: (`paper_light`, `paper_deep`, `ink`, `accent`) plus a `score` hint, because
#: the look and the music should agree: a palette chosen for grief and a cue
#: chosen for triumph in the same film is a mistake the audience feels without
#: being able to name.
PALETTES = {
    "sepia": {
        "paper_light": [216, 208, 178], "paper_deep": [168, 158, 132],
        "ink": "#3a3a30", "accent": "#c8402a",
        "papers": ["#c8402a", "#2f6f7a", "#d99a2b", "#4a6a3a", "#7a4a6a", "#3a3a30"],
        "score": {"mood": "record", "scale": "minor", "bpm": 62},
        "note": "the archival default — records, documents, history",
    },
    "ash": {
        "paper_light": [206, 210, 214], "paper_deep": [150, 158, 168],
        "ink": "#2e3742", "accent": "#5b7f9c",
        "papers": ["#2f5d80", "#7d9ab5", "#b5495b", "#d8b25a", "#3f6b63", "#2e3742"],
        "score": {"mood": "elegy", "scale": "aeolian", "bpm": 52},
        "note": "snow, winter, night, grief — a cold sheet and slate ink",
    },
    "ember": {
        "paper_light": [228, 206, 168], "paper_deep": [178, 140, 96],
        "ink": "#43291a", "accent": "#d2691e",
        "papers": ["#d2541e", "#e8a33d", "#8c3a2b", "#3f6f6a", "#a8632f", "#43291a"],
        "score": {"mood": "warmth", "scale": "dorian", "bpm": 66},
        "note": "fire, lantern, hearth, candle — warm stock, sanguine ink",
    },
    "tide": {
        "paper_light": [202, 214, 210], "paper_deep": [140, 164, 164],
        "ink": "#1f3f43", "accent": "#2e7d75",
        "papers": ["#1f7a86", "#3fa89b", "#e06b3a", "#2e5f8a", "#c8a94a", "#1f3f43"],
        "score": {"mood": "voyage", "scale": "dorian", "bpm": 58},
        "note": "sea, boats, harbour, rain — green-blue wash",
    },
    "dust": {
        "paper_light": [226, 210, 176], "paper_deep": [186, 160, 116],
        "ink": "#4a3b26", "accent": "#b5651d",
        "papers": ["#c86a2a", "#e0a640", "#8a5a2a", "#4a7a86", "#a8452f", "#4a3b26"],
        "score": {"mood": "arid", "scale": "mixolydian", "bpm": 70},
        "note": "desert, heat, drought, roads — ochre and sun",
    },
    "moss": {
        "paper_light": [212, 214, 190], "paper_deep": [156, 164, 130],
        "ink": "#2c3a24", "accent": "#5a7d3a",
        "papers": ["#4a7d3a", "#7ba650", "#c8802a", "#2f6f6a", "#a8452f", "#2c3a24"],
        "score": {"mood": "pastoral", "scale": "lydian", "bpm": 64},
        "note": "forest, fields, growing things",
    },
    "bone": {
        "paper_light": [232, 230, 224], "paper_deep": [186, 184, 178],
        "ink": "#33343a", "accent": "#7a8794",
        "papers": ["#3f6f8c", "#c8455a", "#5aa89a", "#d99a2b", "#6a5a8c", "#33343a"],
        "score": {"mood": "clinical", "scale": "phrygian", "bpm": 56},
        "note": "hospitals, laboratories, procedure — bleached and even",
    },
    "noir": {
        "paper_light": [196, 190, 178], "paper_deep": [120, 116, 108],
        "ink": "#1c1c20", "accent": "#a8231c",
        "papers": ["#a8231c", "#d4a017", "#2f5d70", "#7a2f4a", "#4a6a5a", "#1c1c20"],
        "score": {"mood": "dread", "scale": "phrygian", "bpm": 54},
        "note": "crime, pursuit, threat — hard contrast",
    },
}

DEFAULT = "sepia"

#: Words that vote for a palette. Weighted because some words are decisive and
#: others are only suggestive: "snow" is a strong vote for a cold film, while
#: "cold" alone might be a cold coffee.
CUES = {
    "ash": [(r"\b(snow|snowfall|blizzard|frost|ice|icy|winter|freezing)\b", 3),
            (r"\b(grief|mourning|funeral|widow|lost|died|death|drowned|gone)\b", 2),
            (r"\b(cold|bleak|bitter|grey|gray|pale)\b", 1),
            (r"\b(night|dark|darkness)\b", 1)],
    "ember": [(r"\b(lantern|candle|flame|fire|hearth|ember|lamp|torch)\b", 3),
              (r"\b(burn|burning|lit|alight|glow|glowing|warm|warmth)\b", 2),
              (r"\b(kitchen|home|supper|kettle)\b", 1)],
    "tide": [(r"\b(sea|ocean|tide|harbour|harbor|shore|coast|wave|waves)\b", 3),
             (r"\b(boat|trawler|dinghy|ship|sail|sailed|fishing|fisherman|"
              r"fishermen|ferry)\b", 2),
             (r"\b(rain|storm|wet|salt|drown|drowned)\b", 1)],
    "dust": [(r"\b(desert|dune|sand|drought|arid|dry|parched)\b", 3),
             (r"\b(heat|sun|scorching|noon|summer)\b", 2),
             (r"\b(road|highway|track|dust)\b", 1)],
    "moss": [(r"\b(forest|wood|woods|trees?|jungle|thicket|grove)\b", 3),
             (r"\b(field|meadow|garden|moss|fern|green)\b", 2),
             (r"\b(spring|grow|growing|leaf|leaves)\b", 1)],
    "bone": [(r"\b(hospital|clinic|ward|surgery|laboratory|lab|morgue)\b", 3),
             (r"\b(doctor|nurse|patient|specimen|sample|autopsy)\b", 2),
             (r"\b(sterile|clinical|procedure|protocol)\b", 1)],
    "noir": [(r"\b(murder|killer|crime|suspect|detective|police|investigation)\b", 3),
             (r"\b(gun|blood|body|witness|interrogat|alibi)\b", 2),
             (r"\b(threat|hunted|pursued|fled|escape)\b", 1)],
    "sepia": [(r"\b(archive|record|file|document|history|historical|"
               r"letter|ledger|register)\b", 2),
              (r"\b(nineteen|century|decade|years ago)\b", 1)],
}


def score(text: str) -> dict:
    """How strongly a text votes for each palette."""
    t = (text or "").lower()
    out = {}
    for name, rules in CUES.items():
        total = 0
        for pattern, weight in rules:
            total += weight * len(re.findall(pattern, t))
        out[name] = total
    return out


def choose(text: str, default: str = DEFAULT):
    """``(name, palette)`` for a story.

    Ties and near-ties fall back to the default rather than picking the first
    alphabetically. A story that does not clearly signal a temperature should
    look archival, which is this style's native register — guessing wildly
    from one stray word is worse than being neutral.
    """
    votes = score(text)
    best = max(votes, key=lambda k: votes[k])
    if votes[best] < 3:
        return default, dict(PALETTES[default])
    # A clear winner has to actually beat the runner-up; otherwise the story
    # is genuinely mixed and the neutral stock is the honest answer.
    rest = sorted((v for k, v in votes.items() if k != best), reverse=True)
    if rest and best != default and votes[best] - rest[0] < 2:
        return default, dict(PALETTES[default])
    return best, dict(PALETTES[best])


def decisive(text: str) -> bool:
    """Did the story's *imagery* clearly name a colour temperature?

    `choose()` already returns the default when the vote is weak or close.
    This answers the question that matters to a caller who has a second,
    independent reading of the same story: is the palette vote strong enough
    to be worth defending against it?

    The test is a **ratio**, not the absolute margin `choose()` uses. Votes
    scale with the length of the narration, so "beats the runner-up by 2" is
    a real bar for a 90-word short and no bar at all for a 900-word episode —
    it once let 44-vs-31 count as decisive, which is a 1.4x lead and not a
    clear answer to anything.
    """
    votes = score(text)
    if not votes:
        return False
    best = max(votes, key=lambda k: votes[k])
    rest = sorted((v for k, v in votes.items() if k != best), reverse=True)
    if votes[best] < 4:
        return False
    return not rest or votes[best] >= 1.6 * max(rest[0], 1)


#: A score mood → the palette that shares its emotional register. Several
#: score moods map onto one palette, because the score has a finer vocabulary
#: than the paper stock does: `crime`, `tension` and `dread` are three
#: different pieces of music but one colour of paper.
FOR_MOOD = {
    "dread": "noir",
    "crime": "noir",
    "tension": "noir",
    "elegy": "ash",
    "memorial": "ash",
    "music_box": "ash",
    "reflective": "sepia",
    "curious": "bone",
    "wonder": "bone",
    "drive": "dust",
    "pastoral": "moss",
    "voyage": "tide",
    "warm": "ember",
}


def for_mood(mood: str):
    """``(name, palette)`` for a score mood, or ``(None, None)``.

    The picture and the score read the same story twice, by different means:
    the palette votes on *imagery* ("snow", "furnace", "sea"), the score on
    the emotional register of the whole narration. When those two readings
    disagree the film ends up scored one way and coloured another — a dread
    film on warm amber paper — and the disagreement is invisible in the
    storyboard because each half looks correct on its own.

    Where the palette's own vote is not decisive, the score's reading wins:
    it is a reading of the story, where the palette's is a reading of the
    nouns in it.
    """
    name = FOR_MOOD.get((mood or "").lower())
    if not name or name not in PALETTES:
        return None, None
    return name, dict(PALETTES[name])


def for_beat(palette: dict, intent: str, emphasis: float):
    """A per-element ink for one beat.

    Beats that carry the film's weight are drawn in the palette's full ink;
    quiet supporting beats are drawn a step lighter, so the eye is pulled to
    the moments that matter without any change of composition. This is the
    colour equivalent of the animation budget: spend the darkest ink where it
    counts rather than everywhere.
    """
    ink = palette.get("ink")
    if not ink or emphasis >= 0.6 or intent in ("reveal", "emphasise"):
        return ink
    return _lighten(ink, 0.22)


#: Which cast roles are allowed a colour of their own, and which stay in the
#: film's ink. Scenery in full colour competes with the subject standing in
#: front of it, so a place is drawn a step back while the things that act are
#: drawn in cut paper.
_ROLE_TINT = {
    "actor": 0, "prop": 1, "subject": 1, "attach": 2, "sky": 3,
    "inset": 3, "diagram": 3, "route": 0,
}


def ink_for(palette: dict, role: str, index: int = 0, emphasis: float = 0.5):
    """The colour one element is cut from.

    This is the fix for every film coming out brown. A palette used to reach
    the renderer as a single `ink`, so all forty-six drawings in a film were
    the same colour and the only thing that ever varied was the paper behind
    them. Cut-paper collage does not work that way and never has — Matisse's
    cut-outs and Eric Carle's books are stacks of *many* saturated sheets, and
    the medium is what makes the colour legible rather than what forbids it.

    Scenery keeps the ink so it stays behind the subject; everything that acts
    gets a sheet of its own, cycled by position so two things on the same
    stage are never cut from the same paper.
    """
    papers = palette.get("papers") or []
    if not papers:
        return palette.get("ink")
    if role in ("ground", "ground_far", "atmos"):
        # A place is not a subject. Drawn in full colour it shouts over the
        # figure standing on it, so scenery stays in the film's ink.
        return palette.get("ink")
    base = _ROLE_TINT.get(role, 1)
    pick = papers[(base + index) % len(papers)]
    if emphasis < 0.35:
        return _lighten(pick, 0.18)
    return pick


def _lighten(hexcolor: str, amount: float) -> str:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda c: min(255, int(c + (255 - c) * amount))  # noqa: E731
    return "#%02x%02x%02x" % (f(r), f(g), f(b))
