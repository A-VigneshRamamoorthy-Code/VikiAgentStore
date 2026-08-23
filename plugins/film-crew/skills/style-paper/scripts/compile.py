"""Compile a style-neutral beat plan into a paper storyboard draft.

This is the paper style's half of the contract. The storyboard artist says
*"at l4+0.3, establish the factory, keyword UNION CARBIDE, circle it"*; this
turns that into torn cards, chips, marker rings and a camera path.

What it produces is a **draft that renders**, not a finished board. It gets the
timing, the structure, the layout and the camera right — the things that are
mechanical — and leaves taste to the human. Treat its output as a first pass to
edit, exactly like a storyboard artist's rough.

Two rules it will not break:

*   **It never invents a picture.** The paper renderer draws from a fixed
    catalogue of procedural illustrations. When a beat asks for something that
    is not in it, the compiler emits a labelled placeholder and says so. A
    silent substitution — a `hotel` standing in for a chemical plant — is how a
    documentary ends up showing the wrong building.
*   **It reads the catalogue out of the renderer**, so the two cannot drift.

    python3 compile.py beat-plan.json -o storyboard.json
    python3 compile.py beat-plan.json --check          # dry run, report only
    python3 compile.py beat-plan.json --aspect 9:16    # vertical cut

Exit 0 clean, 1 if something needs a human. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_ROOT = os.path.dirname(HERE)

# The storyboard artist owns the plan format; reuse its parser rather than
# writing a second, subtly different one.
#
# The sibling skill is found by walking up, not by counting `dirname`s. A
# fixed count silently broke when the styles moved up two levels to become
# skills of their own: the import fell through to `beatplan = None`, which
# disabled beat-plan validation and every string-time offset without one word
# of complaint. Searching for the file cannot rot that way, and a miss is now
# loud.
def _find_beatplan():
    d = HERE
    for _ in range(6):
        d = os.path.dirname(d)
        cand = os.path.join(d, "storyboard-artist", "scripts")
        if os.path.isfile(os.path.join(cand, "beatplan.py")):
            return cand
    return None


_BEATPLAN_DIR = _find_beatplan()
if _BEATPLAN_DIR:
    sys.path.insert(0, _BEATPLAN_DIR)
try:
    import beatplan
except ImportError:  # pragma: no cover
    beatplan = None

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}

#: hint keyword -> (art name, extra params). First match wins, so order matters:
#: put the specific before the generic ("ambulance" before "car").
#:
#: Every alternation is wrapped in a group that carries the word boundary.
#: Written as ``\bboat|vessel|ship`` the ``\b`` binds to the first alternative
#: only, so ``ship`` matches inside "leadership" and a beat about a management
#: team gets illustrated with a boat — exactly the silent substitution this
#: module exists to prevent. Prefixes that must stem ("burn" -> "burning")
#: deliberately omit the closing boundary.
HINTS = [
    (r"\b(?:ambulance)",                   ("car", {"kind": "ambulance"})),
    (r"\b(?:police car|patrol\b|patrol car)", ("car", {"kind": "police"})),
    (r"\b(?:taxi|cab)\b",                  ("car", {"kind": "taxi"})),
    (r"\b(?:bus|coach)\b",                 ("car", {"kind": "bus"})),
    (r"\b(?:car|vehicle|truck|lorry)\b",   ("car", {"kind": "sedan"})),
    # Objects a narration names directly. These sit above the generic nouns
    # because "a note" and "the rear seat" are the *subject* of their beat; if
    # they fall through to `figure` or `airliner` the film stops illustrating
    # what is being said and starts decorating it.
    (r"\b(?:note\b|notes?\b|slip of paper|handwritten|hand-written|"
     r"demand note|scrawl|scribbled)\b",   ("note", {})),
    (r"\b(?:ransom note|the note)\b",      ("note", {})),
    (r"\b(?:seat|seat \d+[a-f]?|rear row|aisle|window seat|sat down|"
     r"seated|passenger seat|rear cabin|the cabin|rows of|boarded)\b",
                                           ("seat_row", {})),
    (r"\b(?:briefcase|attach[eé] case|satchel|bag\b)\b",
                                           ("briefcase", {})),
    (r"\b(?:bomb|dynamite|explosive|detonator|red sticks|bundle of wires|wired to)\b",
                                           ("briefcase", {"opened": 0.85})),
    (r"\b(?:sketch|composite|likeness|police sketch|artist.s impression|"
     r"wanted poster|portrait|drawings?|described him|description|"
     r"five foot|brown eyes|dark hair|his face|his name|nameless|"
     r"anonymous|unidentified|who he was|his identity)\b",
                                           ("sketch", {})),
    (r"\b(?:document|report|file\b|dossier|memo|teletype|affidavit|"
     r"transcript|paperwork|records?|statements?|testimony|evidence|"
     r"accounts?|reconstructions?|manifest)\b",  ("document", {})),
    (r"\b(?:forest|woods|woodland|treeline|tree line|timber|pines?|trees?\b|"
     r"conifer|wilderness|undergrowth|drop zone|terrain|canopy of)\b",
                                           ("forest", {})),
    (r"\b(?:ticket|boarding pass|ticket counter|the counter|clerk|"
     r"one-way|fare|checked in)\b",        ("ticket", {})),
    (r"\b(?:coin toss|fifty-fifty|odds\b|a gamble|wager|even chance|"
     r"chance of|coin\b)\b",               ("coin", {"tossed": 0.7})),
    (r"\b(?:envelope|letter\b|posted|mailed|in the mail|correspondence)\b",
                                           ("envelope", {})),
    (r"\b(?:search(?:ed|ing)?\b|hunt|combed|scoured|looked for|"
     r"investigat\w*|examin\w*|scrutin\w*|clues?\b|leads?\b)",
                                           ("magnifier", {})),
    (r"\b(?:fingerprints?|forensic|dna|latent print|lifted a print|"
     r"partial print|traces?\b)\b",        ("fingerprint", {})),
    (r"\b(?:cigarette|smoked|smoking|chain-smok\w*|ashtray|butts?)\b",
                                           ("cigarette", {})),
    (r"\b(?:bourbon|whisk(?:e)?y|drink|tumbler|glass\b|liquor)\b",
                                           ("glass", {})),
    (r"\b(?:radar|radar scope|air traffic|blip|air traffic controller)\b",
                                           ("radar", {})),
    (r"\b(?:stairway|staircase|air ?stairs?|stairs\b|aft stairs?)\b",
                                           ("stairs", {})),
    (r"\b(?:hospital|casualty|ward|clinic)\b", ("hospital", {})),
    (r"\b(?:railway|train station|railway station|terminus|platform)\b",
                                           ("terminus", {})),
    (r"\b(?:cafe|café|restaurant|shopfront)\b", ("cafe", {})),
    (r"\b(?:hotel|palace)\b",              ("hotel", {})),
    (r"\b(?:helicopter|chopper)\b",        ("helicopter", {"rotor": 1})),
    (r"\b(?:airstair|aft stair|rear stair)\b",
                                           ("airliner", {"stairs": 0.9})),
    (r"\b(?:airliner|aeroplane|airplane|jetliner|boeing|airbus|"
     r"aircraft|plane|jet|cockpit|fuselage|cabin crew|flight \d+|"
     r"landing gear|flaps|airborne|took off|takeoff|in the air|"
     r"ten thousand feet|altitude|throttle|tail section)\b",
                                           ("airliner", {})),
    (r"\b(?:parachute|chute|canopy|skydiv|jumper|bail(?:ed)? out|"
     r"ripcord|harness|jumped|the jump|leapt|leaped)",
                                           ("parachute", {})),
    (r"\b(?:banknote|bank note|ransom|cash|bills?\b|currency|"
     r"twenties|\$[\d,]+|two hundred thousand|serial numbers?|"
     r"the money|bundles?)",                ("banknotes", {})),
    (r"\b(?:necktie|tie\b|clip-on)",       ("necktie", {})),
    (r"\b(?:trawler|fishing boat)\b",      ("trawler", {})),
    (r"\b(?:dinghy|inflatable)\b",         ("dinghy", {})),
    (r"\b(?:boat|vessel|ship|ferry)\b",    ("boat", {})),
    (r"\b(?:sea|ocean|waves|shoreline|river|riverbank|sandbar|"
     r"the bank|beach|water)\b", ("sea", {})),
    (r"\b(?:crowd|protest|queue|gathering|gather|passengers|"
     r"forty-three|thirty-six|people (?:sat|boarded|aboard))\b",
                                           ("crowd", {"count": 7})),
    (r"\b(?:commando|soldier|army)\b",     ("figure", {"kind": "commando"})),
    (r"\b(?:police|policeman|policemen|officer|agents?\b|the bureau|"
     r"f\.?b\.?i\.?|detectives?|investigators?|marshals?|sheriff)\b",
                                           ("figure", {"kind": "police"})),
    (r"\b(?:staff|worker|employee|nurse|doctor|flight attendants?|"
     r"stewardess|crew members?|the crew|purser)\b",
                                           ("figure", {"kind": "staff"})),
    (r"\b(?:man|woman|person|witness|survivor|figure)\b",
                                           ("figure", {"kind": "civilian"})),
    (r"\b(?:map|region|country|route|flown to|flight path|"
     r"headed (?:north|south|east|west)|corridor|border)\b",  ("map", {})),
    (r"\b(?:timeline|chronology|sequence of events|years later|"
     r"decades?\b)\b",                     ("timeline", {})),
    (r"\b(?:clock|o'clock|hours?\b|minutes?\b|deadline|by nightfall|"
     r"running out of time|past eight|past nine|midnight)\b",
                                           ("clock", {})),
    (r"\b(?:smoke|fumes|plume|tear gas|gas leak|gas cloud)\b",     ("smoke", {"density": 0.7})),
    (r"\b(?:fire|flame|blaze|burn)",       ("flame", {"strength": 0.8})),
    (r"\b(?:phone|telephone|radio|handset)\b", ("phone", {"kind": "handset"})),
    (r"\b(?:cctv|camera|surveillance)\b",  ("cctv", {})),
    (r"\b(?:candle|vigil)\b",              ("candle", {"lit": 1.0})),
    (r"\b(?:lantern|lamp)\b",              ("lantern", {"glow": 0.8})),
    (r"\b(?:moon|night sky)\b",            ("moon", {})),
    (r"\b(?:star|stars)\b",                ("star", {})),
    (r"\b(?:hill|mountain|ridge)\b",       ("hill", {})),
    (r"\b(?:snow|winter)\b",               ("snow", {"count": 60})),
    (r"\b(?:thread|link|connect|conspir|theor(?:y|ies)|suspects?\b|"
     r"inference|points? to|adds? up)",     ("thread", {})),
    (r"\b(?:moon|night sky|that night|after dark|darkness)\b", ("moon", {})),

    # --- what an analytical line puts on screen ---------------------------
    # A documentary spends much of its length not on events but on records,
    # claims, money and time. Those lines still show something concrete — a
    # file, a sketch, a sum — and if the table has no rule for them the beat
    # falls back to whatever the author reached for, which is where decorative
    # pictures come from. Every rule here names a real object the line means.
    (r"\b(?:volumes?|dossiers?|case file|files?\b|archives?|records?|"
     r"reports?|affidavits?|testimon\w*|statements?|transcripts?|"
     r"courtroom|court\b|lawsuit|ruling|warrants?|boxed and shelved)\b",
                                           ("document", {"stamp": True})),
    (r"\b(?:claims?|claimed|confessed|confession|alleg\w*|asserted|"
     r"denied|unconfirmed|not been confirmed|deathbed)\b",
                                           ("document", {"stamp": False})),
    (r"\b(?:sketch|composite|likeness|artist'?s? impression|description|"
     r"descriptions|john doe|template|identikit|the name is wrong|"
     r"his name|unidentified|who he was|never identified)\b",
                                           ("sketch", {})),
    (r"\b(?:dollars?|ransom|payout|share came to|reward|"
     r"bills?\b|banknotes?|currency|serial numbers?)\b",
                                           ("banknotes", {})),
    (r"\b(?:years? (?:later|after|of)|decades?|anniversar\w*|"
     r"to this day|still (?:called|bolted)|ever since|"
     r"over the years|by then|nineteen \w+|for \w+ years)\b",
                                           ("timeline", {})),
    (r"\b(?:search|searched|hunt|combed|looking|investigat\w*|examin\w*|"
     r"analys\w*|analyz\w*|forensic|traces?\b|particles?|elements?\b|"
     r"evidence|clues?|metal detectors?)\b",
                                           ("magnifier", {})),
    (r"\b(?:demands?|instructions?|ultimatum|told her|written on|"
     r"in one breath|said (?:only|simply))\b",
                                           ("note", {})),
    (r"\b(?:hijack\w*|skyjack\w*|copycat|copying him|imitators?)\b",
                                           ("airliner", {"view": "side"})),
    (r"\b(?:vane|tail stairs?|aft stairs?|airstair|rear stairs?|"
     r"off the back of it|lowered in flight)\b",
                                           ("stairs", {})),
    (r"\b(?:suits?\b|overcoats?|loafers|raincoat|clothing|"
     r"what he was wearing|dressed in)\b", ("figure", {"kind": "civilian"})),
    (r"\b(?:devices?|mechanisms?|apparatus|contraption|"
     r"opened it|comes apart)\b",
                                           ("briefcase", {"opened": 0.85})),
    (r"\b(?:hinge|the substance|contradic\w*|does not fit|fits some|"
     r"holds up|falls apart|the whole story)\b",  ("thread", {})),
]

#: Where a beat lives — a *box*, not a point, as fractions of the frame.
#: A beat's picture and its keyword chips are laid out entirely inside its own
#: box, and the boxes do not overlap, so two live beats cannot collide.
#: An earlier version placed a picture at a point and hung the chips below it;
#: the chips of an upper slot then landed on top of the picture in the lower
#: one. Boxes make that failure impossible rather than unlikely.
#:
#: The *count* is a design decision, not a detail. A 2x2 grid was tried first
#: and produced the commonest complaint about this style — "the same static
#: visuals over and over" — because four boxes on a 1920-wide frame make every
#: drawing about a sixth of the frame, and a field of small stamps reads as one
#: texture however often the stamps change. Two slots roughly double every
#: picture. Adding a slot back shrinks them all again.
SLOTS = [(0.04, 0.10, 0.49, 0.92),
         (0.51, 0.10, 0.96, 0.92)]

#: How many later beats a picture stays on the board for. A collage should feel
#: like it is being assembled, so things must persist past their own line — but
#: a board that never clears ends up an unreadable pile, which is exactly what
#: the first version of this compiler produced.
LIVE = len(SLOTS) - 1

#: A big picture for a beat that carries the moment, a small one for support.
SIZE_REF = 520  #: the largest `SIZE` entry; a beat asking for this fills
                #: its slot, and everything else is a share of it.
SIZE = {"establish": 460, "reveal": 520, "evidence": 400, "portrait": 430,
        "locate": 480, "compare": 360, "list": 300, "annotate": 380,
        "emphasise": 500, "transition": 340}


def art_catalogue():
    """The illustration names the renderer actually implements.

    Parsed from ``render.py`` rather than duplicated, so adding an illustration
    to the renderer makes it available here with no second edit — and so this
    compiler can never offer a picture that does not exist.
    """
    src = os.path.join(HERE, "render.py")
    try:
        with open(src, encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        return set()
    return set(re.findall(r'name == "([a-z_]+)"', body))


#: Pictures that win over a person or a place when both are in the same hint.
#: Longest-match alone gets this backwards: "he handed the flight attendant a
#: note" resolves to a member of staff, because "flight attendant" is a longer
#: string than "note" -- and the beat is about the note. These are the things a
#: narration *hands over, shows, or finds*, and when one is named it is the
#: subject of its beat. A person can be drawn from any line; the note cannot.
OBJECT_FIRST = frozenset({
    "note", "briefcase", "ticket", "envelope", "document", "banknotes",
    "necktie", "cigarette", "glass", "sketch", "fingerprint", "parachute",
    "seat_row", "stairs",
})


def pick_art(hint, catalogue):
    """``(name, params, exact)``. ``exact`` False means a human must look.

    A hint can honestly mean two different pictures — "gas station" reads as
    both a forecourt and a plume — and picking the higher row of the table
    without saying so is the quiet kind of wrong. So every rule is tried and
    the *longest* match wins, because the longer phrase is the more specific
    one: "police car" matches both `police` and `car`, and it is a car.

    Only matches of that same winning length are allowed to make a hint
    ambiguous. Without that, every compound phrase would be flagged — "police
    car" and "fishing boat" would each raise a question that their own wording
    already answers — while "ambulance vehicle", where two equally-long rules
    genuinely disagree, would be indistinguishable from them.
    """
    h = (hint or "").lower()
    hits = []
    for pattern, (name, params) in HINTS:
        m = re.search(pattern, h)
        if m and name in catalogue:
            hits.append((m.end() - m.start(), name, params))
    if not hits:
        return None, {}, False
    # An object the line names outranks a person or a place it also names,
    # whatever their string lengths; within a rank, the longer phrase wins.
    objects = [h for h in hits if h[1] in OBJECT_FIRST]
    if objects:
        hits = objects
    best = max(n for n, _, _ in hits)
    top = [(name, params) for n, name, params in hits if n == best]
    name, params = top[0]
    unambiguous = all(n == name for n, _ in top)
    return name, dict(params), unambiguous


def jitter(rng, base, spread):
    return base + rng.uniform(-spread, spread)


def _slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", (title or "film").lower()).strip("-")
    return s or "film"


def _half(size):
    """Half the drawn height of a chip at this point size.

    A chip is its glyph box plus a fixed 20px of padding above and below, so
    the height is affine in the point size rather than a multiple of it -- and
    the slope has to allow for uppercase glyphs that drop below the baseline
    (Q, J), which set the worst case. `Slot` runs where PIL is not guaranteed,
    so this has to be modelled rather than measured.
    """
    return 0.42 * size + 24


def _stack_h(size, n):
    """Height a stack of `n` chips at this point size occupies, gaps included.

    There are only `n - 1` gaps between `n` chips; charging one after the last
    of them made a stack look taller than it is, which reported slots as
    crowded that were not.
    """
    return 12 + n * 2 * _half(size) + 14 * (n - 1)


def _fit_size(height, n):
    """Largest point size whose stack of `n` fits `height`. Inverse of `_stack_h`."""
    return max(CHIP_MIN_PX,
               (height - 12 - 14 * (n - 1) - 48 * n) / (0.84 * n))


#: Below this a keyword chip stops being readable at thumbnail size.
CHIP_MIN_PX = 40
#: A chip that lands later than this before its slot is reused is a flash
#: nobody can read, so a late cue is pulled back to it.
CHIP_MIN_ON = 1.2
#: The smallest illustration `Slot.art` will hand out; the chip reserve grows
#: at the picture's expense, but never past this.
ART_MIN_PX = 120


class Slot(object):
    """A rectangle of board, and a cursor down it.

    Everything a beat draws is requested from its own slot, so nothing a beat
    emits can stray into a neighbour's territory.
    """

    def __init__(self, box, W, H, chips, want=None):
        x0, y0, x1, y1 = box
        self.x0, self.y0 = x0 * W, y0 * H
        self.x1, self.y1 = x1 * W, y1 * H
        self.cx = (self.x0 + self.x1) / 2.0
        n = max(0, int(chips))
        span = self.y1 - self.y0
        if not n:
            # No chips, so no reserve. `max(1, chips)` here used to hold back a
            # row for a caption that never arrives, and since most beats carry
            # no keywords it quietly cost every picture in the film about a
            # third of its height -- which is most of why the board reads as a
            # scatter of small stamps rather than as illustration.
            self.chip_h = 0.0
            self.cap = 0
            self.art_h = span
            self.cursor = self.y1
            self.crowded = False
            return
        # The stack is planned as a whole, because a chip sized against
        # whatever the cursor has left cannot know how tall the rest wants to
        # be. Doing it one at a time fails in both directions: the flat
        # 96-per-chip reserve is under what even floor-size chips need, so they
        # drew on top of each other -- and sizing each to its share of the
        # reserve shrank a pair to ~41px in a slot with room for ~100px.
        base = min(span * 0.5, 96.0 * n + 24)
        # Growing the reserve costs the illustration its height, so it stops
        # at the minimum `art()` will hand out rather than squeezing it away.
        # This is a hard cap, not one term among several: `base` is a heuristic
        # starting size, and in a slot shorter than about 240px it exceeds what
        # is actually available, which would leave `art()` handing out a picture
        # taller than the space left for it -- straight back into the overlap
        # this is all here to prevent.
        room = max(span * 0.35, span - ART_MIN_PX)
        wanted = _stack_h(want, n) if want else base
        floor = _stack_h(CHIP_MIN_PX, n)
        self.chip_h = min(max(base, wanted, floor), room)
        #: The largest point size whose stack fits the reserve just set. Chips
        #: may still come out smaller -- a long one shrinks to fit the width.
        self.cap = (want if want and wanted <= self.chip_h
                    else _fit_size(self.chip_h, n))
        self.art_h = span - self.chip_h
        self.cursor = self.y1 - self.chip_h + 12
        #: True when even a floor-size stack cannot fit the grown reserve.
        self.crowded = self.chip_h + 0.5 < floor

    def art(self, want):
        """Centre, size and the box the picture may fill.

        `size` is kept for renderers that only understand a longest side; the
        box is what lets a wide drawing be wide.

        The box is scaled by how much the beat asked for, because otherwise
        `fit` would silently flatten the hierarchy: every picture would fill
        its slot and a `list` beat would come out the same size as a `reveal`.
        `want` still means "longest side", so it is turned into a share of the
        slot rather than a hard cap -- capping it is what left a wide drawing
        using a third of the height it had been given.
        """
        bw = (self.x1 - self.x0) * 0.94
        bh = self.art_h * 0.94
        size = int(min(want, bw, bh))
        rel = max(0.62, min(1.0, float(want) / float(SIZE_REF)))
        return ((int(self.cx), int(self.y0 + self.art_h / 2.0)),
                max(ART_MIN_PX, size),
                (max(ART_MIN_PX, int(bw * rel)),
                 max(ART_MIN_PX, int(bh * rel))))

    def chip(self, text, want):
        """Centre and point size for the next chip, shrunk to fit the width."""
        width = self.x1 - self.x0
        # `self.cap` is the vertical budget, decided for the stack as a whole;
        # the width term is this chip's own. Stepping the cursor by
        # `size * 0.62` assumed a chip's half-height was a flat fraction of its
        # point size, but the real half is `0.42 * size + 24` and the fixed 24
        # dominates at small sizes -- a 40pt chip is ~82px tall and the cursor
        # moved 64, so a stack overlapped by design. Advance and clamp now both
        # use `_half`, and with the reserve planned the clamp is an assertion
        # rather than the thing keeping chips on the board.
        size = min(want, self.cap, width / max(6, len(text)) / 0.60)
        size = max(CHIP_MIN_PX, int(size))
        half = _half(size)
        y = self.cursor + half
        self.cursor = y + half + 14
        return (int(self.cx), int(min(y, self.y1 - half))), size


#: Below this a title card is unreadable at thumbnail size, so the title is
#: stacked onto another line rather than shrunk any further.
TITLE_MIN_PX = 44
#: More than this and the card stops being a card.
TITLE_MAX_LINES = 3
#: How long the card sits on screen after a teaser hands over to it.
#: Short on purpose: the long hold in the reference is buying silence
#: that a narrated teaser has already spent.
TITLE_HOLD = 2.8


def _title_lines(title, width):
    """Break a title onto as few lines as will fit the frame.

    Returns balanced lines; a title that still cannot fit at
    `TITLE_MIN_PX` on `TITLE_MAX_LINES` is returned as-is and clamped, which
    is a deliberate last resort rather than silent overflow.
    """
    if not title:
        return [""]
    budget = width * 0.84
    words = title.split()
    for n in range(1, min(TITLE_MAX_LINES, len(words)) + 1):
        per = len(words) / n
        lines, i = [], 0
        for k in range(n):
            j = len(words) if k == n - 1 else int(round(per * (k + 1)))
            lines.append(" ".join(words[i:j]))
            i = j
        lines = [ln for ln in lines if ln]
        longest = max(len(ln) for ln in lines)
        if budget / max(longest, 1) / 0.62 >= TITLE_MIN_PX:
            return lines
    return lines


def _known_regions():
    """The map regions this style can draw, or `None` if that cannot be
    determined.

    Imported lazily: compiling a board is otherwise pure stdlib, and a plan
    should still compile on a machine with no drawing libraries installed.
    An unknown region is only *detected* here -- it is fatal at render time,
    minutes later, so catching it at the cheap stage is the whole point."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from illustrations import _REGIONS
    except Exception:
        return None
    return set(_REGIONS)


def compile_plan(plan, aspect="16:9", seed=None, root="."):
    W, H = ASPECTS[aspect]
    seed = plan.get("seed", 7) if seed is None else seed
    rng = random.Random(seed)
    catalogue = art_catalogue()
    notes = []

    times, total, _ = (beatplan.timeline(plan, root) if beatplan else ({}, 0.0, []))
    # What each line actually says, in order. A keyword chip defaults to the
    # start of its beat's anchor line, which is why a name could land on the
    # board seconds before the narrator said it; with the text and the measured
    # durations in hand a chip can instead be held until the word is spoken.
    texts = {ln.get("id"): (ln.get("text") or "")
             for ln in (plan.get("narration") or []) if ln.get("id")}
    order = [ln.get("id") for ln in (plan.get("narration") or []) if ln.get("id")]

    # Geography is a claim about the world, so it belongs to the film rather
    # than to the style. A plan that names no region gets `generic` -- an
    # unlabelled chart -- rather than inheriting some other film's coastline.
    region = plan.get("region") or "generic"

    board = {
        "title": plan.get("title") or "untitled",
        "note": "Compiled from a beat plan by compile.py. This is a draft: the "
                "timing and layout are right, the taste is not yet.",
        "output": {"width": W, "height": H, "fps": 30, "crf": 20,
                   "preset": "medium", "path": _slug(plan.get("title")) + ".mp4",
                   "maxrate": "20M", "bufsize": "40M"},
        "style": {"seed": seed, "accent": "#c8402a", "region": region,
                  "paper_light": [216, 208, 178], "paper_deep": [168, 158, 132],
                  "blotches": 8, "ghost_print": True, "ghost_alpha": 22,
                  "map_underlay": True, "map_alpha": 20,
                  "vignette": 0.3, "grain": 6},
        # drift and zoom are *fractions* of the frame, not design units.
        "camera": {"zoom": 0.03, "drift": 0.02, "moves": []},
        # The silence before the first word, and after the last. A feed piece
        # cannot afford either. A documentary is built on them: in the measured
        # reference the first narration arrives at 56 s, over score and a held
        # title card, and the film is trusted precisely because it does not
        # hurry. The beat plan owns this; the numbers below are only the
        # fallback for a plan that does not say.
        "timing": plan.get("timing") or {"lead_in": 0.9, "tail": 2.2},
        "music": plan.get("music") or {
            "mood": "tension", "scale": "minor", "root": 43.65,
            "melody_root": 67, "bpm": 60, "gain": 0.85,
            "percussion": False, "seed": seed % 97},
        "mix": plan.get("mix") or {"voice": 1.0, "music": 0.5, "sfx": 0.5,
                                   "duck_db": -10.0, "lufs": -14.0},
        "narration": [],
        "elements": [],
        "sfx": [],
    }

    for line in plan.get("narration") or []:
        entry = {"id": line["id"]}
        for k in ("audio", "duration", "gap_after", "text"):
            if line.get(k) is not None:
                entry[k] = line[k]
        board["narration"].append(entry)

    # The board itself.
    board["elements"].append({
        "type": "card", "at": [W // 2, H // 2],
        "w": int(W * 0.99), "h": int(H * 1.12),
        "seed": seed * 10, "rotate": round(jitter(rng, 0, 1.6), 2),
        "elevation": 0.16, "parallax": 0.05, "float": 0.4, "z": 0,
        "color": [226, 213, 176], "depth": 0.03, "fold": 0.3,
        "sides": [1, 0, 1, 1], "fold_strength": 0.55,
        "in": {"t": 0.0, "dur": 1.1, "anim": "fade"},
    })

    # The cold open. Two shapes are supported, and they are not equivalent.
    #
    # A plan that marks a hook `kind: "cold-open"` over its opening lines has
    # written a *teaser*: it plays narrated and scored, and the title lands
    # when it ends. That is what the measured reference does — the film opens
    # in the middle of its own most cinematic moment, and the card arrives
    # after it, not over it.
    #
    # A plan with neither gets the fallback: a silent lead-in with the title
    # stamped across it. It is staged rather than left blank because blank
    # paper reads as a broken file, but silence is not a hook and the compiler
    # says so rather than letting it ship as one.
    lead = float(board["timing"].get("lead_in", 0) or 0)
    teaser_ref, teaser_lines = None, set()
    for hk in plan.get("hooks") or []:
        if (hk.get("kind") or "").replace("_", "-") != "cold-open":
            continue
        first = order[0] if order else None
        if not first or hk.get("from") not in (first, "%s+0" % first):
            continue
        to = hk.get("to") or hk.get("from")
        if to in times:
            # Line-relative, not a float. `beatplan.timeline` measures the
            # untrimmed wavs and defaults a missing gap to zero, while the
            # renderer trims them and defaults the gap to 0.55 -- so an
            # absolute second computed here drifts, and the title lands in the
            # middle of the body. A reference is resolved against whichever
            # timeline is actually being rendered.
            teaser_ref = "%s.end" % to
            a, z = order.index(first), order.index(to)
            teaser_lines = set(order[a:z + 1])
        break

    if lead >= 6.0 and teaser_ref is None:
        notes.append(("fyi",
                      "the film opens on %.0fs of silence. That is a held "
                      "title, not a cold open — a viewer has nothing to "
                      "listen to yet. Write a teaser as the opening lines "
                      "and mark a hook `kind: \"cold-open\"` over them, and "
                      "the title will land when it ends." % lead))
    elif teaser_ref is not None and lead > 2.0:
        # The teaser cannot fill the lead-in: `lead_in` is silence *before*
        # the first narration line, so the teaser starts only once it has
        # elapsed. A plan with both opens on blank paper and then plays its
        # cold open, which looks like a stalled file.
        #
        # The threshold is two seconds, not six. A hook is the one place in
        # the film where the delay is measured against a viewer deciding
        # whether to stay, and four seconds of blank paper is long enough to
        # lose them -- it does not have to reach six to be a defect.
        notes.append(("blocking",
                      "the cold open does not start until %.1fs of blank "
                      "paper has played, because `lead_in` runs before the "
                      "first narration line. Cut `lead_in` to a beat or two "
                      "— the teaser is the opening." % lead))

    def _hint_of(b):
        assets = [a for a in (b.get("assets") or []) if isinstance(a, dict)]
        drawable = [a for a in assets
                    if a.get("kind") in (None, "illustration", "art")]
        # An *explicitly empty* asset list is a deliberate "this beat shows
        # nothing". Falling back to the subject there would put a picture on
        # screen the author had just decided against -- usually a second copy
        # of what is already on the board.
        if isinstance(b.get("assets"), list) and not b["assets"]:
            return None
        return next((a.get("hint") for a in drawable if a.get("hint")),
                    None) or b.get("subject")

    if teaser_ref is not None or lead >= 6.0:
        title = str(plan.get("title") or "").upper()
        # A teaser puts the card at its end and holds it; a silent lead-in
        # stamps it partway through and clears before the narrator starts.
        if teaser_ref is not None:
            title_at = _shift(teaser_ref, 0.45)
            hold = _shift(teaser_ref, 0.45 + TITLE_HOLD)
        else:
            title_at = round(lead * 0.34, 2)
            hold = max(2.5, lead - 3.0)
        # Fit the strip inside the frame with a margin. A title card that runs
        # off the edge is the first thing anyone sees -- and a floor on the
        # point size cannot be the whole answer, because below it the strip
        # simply overflows instead of shrinking. A long title is stacked onto
        # a second line, which is what a real title card does anyway; only
        # then is the size clamped.
        lines = _title_lines(title, W)
        n = len(lines)
        size = min(104, min(int(W * 0.84 / max(len(ln), 1) / 0.62)
                            for ln in lines)) if title else 104
        if size < TITLE_MIN_PX:
            notes.append(("blocking",
                          "the title %r cannot fit the frame on %d lines even "
                          "at %dpx -- shorten it or it will run off the edge"
                          % (title, TITLE_MAX_LINES, TITLE_MIN_PX)))
        size = max(TITLE_MIN_PX, size)
        step = int(size * 1.22)
        top = int(H * 0.46) - int(step * (n - 1) / 2)
        for i, ln in enumerate(lines):
            board["elements"].append({
                "type": "chip",
                "id": "titlecard" if i == 0 else "titlecard%d" % (i + 1),
                "text": ln,
                "at": [W // 2, top + i * step],
                "size": size,
                "z": 60, "seed": 777 + i, "rotate": -0.8 + i * 0.5,
                "torn": True,
                "in": {"t": _shift(title_at, i * 0.35),
                       "dur": 1.4, "anim": "stamp"},
                "out": {"t": hold, "dur": 0.9},
                "sfx": "stamp" if i == 0 else None})

        # Two objects, established before the narrator exists. A teaser has its
        # own beats carrying its own pictures, so this is only for the silent
        # lead-in, where otherwise nothing at all is on the paper. They are
        # taken from *later* in the film: lifting them from the opening beats
        # puts the same drawing on screen twice running, straight through the
        # cut the title card is supposed to make.
        early = {pick_art(_hint_of(b), catalogue)[0]
                 for b in (plan.get("beats") or [])[:6] if _hint_of(b)}
        opening = ([] if teaser_ref is not None else
                   [_hint_of(b) for b in (plan.get("beats") or [])[6:40]
                    if _hint_of(b)
                    and pick_art(_hint_of(b), catalogue)[0] not in early])
        seen_art, picks = set(), []
        for h in opening:
            if h not in seen_art:
                seen_art.add(h)
                picks.append(h)
        for k, hint in enumerate(picks[:2]):
            name, params, _ = pick_art(hint, catalogue)
            if not name:
                continue
            board["elements"].append({
                "type": "art", "name": name, **params,
                "at": [int(W * (0.30 + 0.40 * k)), int(H * 0.72)],
                "size": 300, "fit": [300, 300], "z": 55 + k,
                "seed": 800 + k, "rotate": -1.5 + 3.0 * k,
                "in": {"t": round(lead * 0.06 + 2.2 * k, 2), "dur": 1.6,
                       "anim": "fade"},
                "out": {"t": hold, "dur": 0.9}})

    zc, ec = 10, 1000
    beats = plan.get("beats") or []

    # Which beats actually put something on the board. A beat can legitimately
    # show nothing -- the picture its line calls for may already be up there --
    # and such a beat must not be given a slot, because taking one evicts the
    # previous occupant and leaves a hole. Slots therefore cycle over the beats
    # that *draw*, so an empty beat extends what is on screen instead of
    # clearing it.
    hints = [_hint_of(b) for b in beats]
    draws = [i for i, b in enumerate(beats)
             if hints[i] is not None or (b.get("keywords") or [])]
    slot_order = {i: k for k, i in enumerate(draws)}

    for i, b in enumerate(beats):
        at = b.get("at", 0)
        bid = b.get("id") or "b%d" % i
        intent = b.get("intent") or "establish"
        emphasis = float(b.get("emphasis") if b.get("emphasis") is not None else 0.5)
        words = b.get("keywords") or []
        hint = hints[i]
        if i not in slot_order:
            continue
        k = slot_order[i]
        slot = Slot(SLOTS[k % len(SLOTS)], W, H, len(words), 84 + 24 * emphasis)
        if slot.crowded:
            notes.append(("fyi",
                          "beat %s carries %d keywords and its slot cannot "
                          "stack that many without them touching, even at the "
                          "smallest readable size. Keep two, or split the beat."
                          % (bid, len(words))))
        (x, y), size, box = slot.art(
            SIZE.get(intent, 400) * (0.85 + 0.3 * emphasis))
        zc += 2
        ec += 1

        # Retire this beat just before its slot is claimed again.
        successor = k + LIVE + 1
        leave = ({"t": _shift(beats[draws[successor]]["at"], -0.45),
                  "dur": 0.5}
                 if successor < len(draws) else None)

        name, params, exact = pick_art(hint, catalogue)
        if name and not exact:
            notes.append(("blocking",
                          "beat %s: %r could reasonably be drawn more than one "
                          "way; %r was used. Confirm it, or narrow the hint."
                          % (bid, hint, name)))

        if name:
            el = {"type": "art", "name": name, "at": [x, y], "size": size,
                  "fit": list(box),
                  "id": bid, "z": zc, "seed": ec,
                  "elevation": round(0.22 + 0.16 * emphasis, 2),
                  "parallax": round(min(0.5, zc / 46.0), 2),
                  "float": round(0.8 + emphasis, 1),
                  "in": {"t": at, "dur": round(0.5 + 0.2 * (1 - emphasis), 2),
                         "anim": "fly", "from_y": -140,
                         "height": round(1.1 + 0.2 * emphasis, 2),
                         "spin": round(jitter(rng, 0, 8), 1)},
                  "sfx": "paper"}
            if leave:
                el["out"] = dict(leave)
            el.update(params)
            # These names used to be forced to a 1:0.62 landscape box, from
            # before `fit` existed and `size` could only mean "longest side".
            # `fit` scales a drawing's *own* proportions into the slot, so the
            # override now only distorts: it squashed the portrait `timeline`
            # spine into a landscape strip that rendered as a bare vertical
            # bar, and made the airliner stubby. The drawing's designed shape
            # is the right one.
            board["elements"].append(el)
        elif hint is None:
            # The beat asked for nothing, so nothing is missing. Silence here
            # is the difference between "the author left this frame to the
            # picture already on the board" and "the catalogue failed".
            pass
        else:
            notes.append(("blocking",
                          "beat %s wants %r — the paper catalogue has no "
                          "illustration for it. A placeholder is on the board; "
                          "either pick from %s, or add an illustration to "
                          "illustrations.py."
                          % (bid, hint, ", ".join(sorted(catalogue)[:8]) + ", ...")))
            text = ("[ART: %s]" % (hint or "?"))[:38].upper()
            (px, py), psize, _pbox = slot.art(0)
            board["elements"].append({
                "type": "chip", "id": bid, "text": text,
                "at": [px, py],
                "size": max(34, min(54, int((slot.x1 - slot.x0)
                                            / len(text) / 0.60))),
                "z": zc, "seed": ec,
                "rotate": round(jitter(rng, 0, 3), 1), "torn": True,
                "in": {"t": at, "dur": 0.5, "anim": "stamp"},
                **({"out": dict(leave)} if leave else {}),
                "sfx": "stamp"})

        for k, kw in enumerate(words):
            zc += 1
            ec += 1
            text = str(kw).upper()
            (cx, cy), csize = slot.chip(text, 84 + 24 * emphasis)
            # Stagger the stack, then hold each chip back until its word is
            # actually spoken. Whichever is later wins: the stagger keeps two
            # chips from stamping at once, the cue keeps a chip from spoiling
            # the narration.
            cue_in = _shift(at, 0.25 + 0.35 * k)
            spoken = _word_cue(at, kw, texts, times, order)
            if spoken and _sortable(spoken, times) > _sortable(cue_in, times):
                cue_in = spoken
                # A word said near the very end of a beat would leave its chip
                # on screen for a blink. Better a slightly early reveal than
                # one nobody can read, so it is pulled back to the last moment
                # that is still legible.
                if leave:
                    latest = _sortable(leave["t"], times) - CHIP_MIN_ON
                    if _sortable(cue_in, times) > latest:
                        cue_in = _shift(leave["t"], -CHIP_MIN_ON)
            board["elements"].append({
                "type": "chip", "text": text,
                "id": "%s_kw%d" % (bid, k),
                "at": [cx, cy],
                "size": csize, "z": zc, "seed": ec,
                "rotate": round(jitter(rng, 0, 2.4), 1),
                "torn": emphasis > 0.6,
                "in": {"t": cue_in, "dur": 0.55,
                       "anim": "stamp"},
                **({"out": dict(leave)} if leave else {}),
                "sfx": "stamp"})

        if ((intent == "annotate" or (b.get("annotate") or {}).get("mark"))
                and name):
            # A marker is drawn *around* the beat's artwork, so it needs one to
            # exist. A beat that drew nothing -- or fell back to a placeholder
            # chip -- has no box to circle, and the marker would reference an
            # id the renderer cannot resolve.
            mark = (b.get("annotate") or {}).get("mark", "circle")
            zc += 1
            ec += 1
            board["elements"].append({
                "type": "marker_ellipse" if mark == "circle" else "marker_rect",
                "box_of": bid, "pad_x": 40, "pad_y": 30, "width": 16,
                "z": zc, "seed": ec,
                "in": {"t": _shift(at, 0.6), "dur": 0.65},
                "out": {"t": _shift(at, 3.2), "dur": 0.5},
                "sfx": "draw"})

        if b.get("safe") == "vertical" and aspect == "16:9":
            notes.append(("fyi",
                          "beat %s is marked safe:vertical — keep it inside "
                          "the centre %d px if this cut is reused for a Short."
                          % (bid, int(W * 0.5625))))

        # The camera leans *toward* the live beat; it does not chase it. Each
        # beat already owns a slot, so centring hard on one throws the others
        # out of frame and the collage stops reading as a board.
        # A gentle lean plus the global drift is what makes it feel hand-held.
        board["camera"]["moves"].append({
            "t": at,
            "at": [int(W / 2 + (x - W / 2) * 0.18),
                   int(H / 2 + (y - H / 2) * 0.18)],
            "zoom": round(1.02 + 0.08 * emphasis, 3),
            "hold": 0.5})

    for act in plan.get("acts") or []:
        if act.get("from"):
            board["camera"]["moves"].append(
                {"t": act["from"], "at": [W // 2, H // 2],
                 "zoom": 1.0, "hold": 0.4})
    board["camera"]["moves"].sort(key=lambda m: _sortable(m["t"], times))

    # Stamp the region onto every chart, wherever in the board it was emitted,
    # so a reader can see which real place each shot claims to draw.
    for el in board["elements"]:
        if el.get("name") == "map":
            el.setdefault("region", region)

    # Clear the teaser off the board before the title lands. The title card is
    # a full-width strip across the middle of the frame, so anything the cold
    # open left up there is printed over -- in the first cut it landed across
    # the suspect sketch and hid the face. A documentary cuts to its title on a
    # clear frame; so does this.
    teaser_beats = {(b.get("id") or "b%d" % i)
                    for i, b in enumerate(beats)
                    if str(b.get("at", "")).split("+")[0].split("-")[0]
                    in teaser_lines}
    if teaser_ref is not None and teaser_beats:
        clear = _shift(title_at, -0.4)
        clear_at = _sortable(clear, times)
        for el in board["elements"]:
            if el.get("id") in teaser_beats and el.get("type") in ("art",
                                                                   "chip"):
                # Cap, never extend. A teaser picture whose slot is reused
                # inside the teaser already leaves early, and pushing it out to
                # the title would put two drawings in the same slot at once.
                cur = el.get("out")
                if cur and _sortable(cur.get("t"), times) <= clear_at:
                    continue
                el["out"] = {"t": clear, "dur": 0.45}

    notes.extend(_variety_notes(
        board, len(beats),
        [b.get("id") or "b%d" % i for i, b in enumerate(beats)],
        {(beats[i].get("id") or "b%d" % i): k
         for i, k in slot_order.items()}))

    return board, notes


#: A single illustration carrying more than this share of the beats is the
#: signature of a board that reached for whatever was nearest.
ART_SHARE_MAX = 0.12


def _variety_notes(board, n_beats, beat_ids=None, slot_of=None):
    """Report a board that draws the same few pictures over and over.

    Nothing else in the compiler can see this. Every individual beat is
    perfectly legal — it names a subject the catalogue can draw — and the
    result still plays as one static image, because the same map came back
    forty-six times. The renderer cannot catch it either: film grain and float
    keep the frame technically in motion, so a mean-frame-difference check
    passes on a film a viewer would call a slideshow.
    """
    out = []
    # Only beat art counts. The cold open's establishing objects are not
    # beats, and letting them in both inflates the share and invents
    # adjacency that the beats themselves do not have.
    ids = {b for b in (beat_ids or ())}
    art = [e for e in board.get("elements") or []
           if e.get("type") == "art" and (not ids or e.get("id") in ids)]
    if not art or not n_beats:
        return out
    used = [e.get("name") for e in art]
    counts = Counter(used)

    # A six-beat feed video cannot give any picture less than a sixth of the
    # film, so a share test alone would block every short plan. The floor is
    # what makes this a test for monotony rather than for brevity.
    floor = max(4, n_beats * ART_SHARE_MAX)
    for name, n in counts.most_common():
        if n > floor:
            out.append(("blocking",
                        "%r is drawn in %d of %d beats (%.0f%%). One picture "
                        "carrying that much of a film is what makes it look "
                        "like a slideshow — give those beats their own "
                        "subjects, or add illustrations the story actually "
                        "needs."
                        % (name, n, n_beats, 100.0 * n / n_beats)))

    # Two pictures are on the board together only if their *slots* overlap in
    # time. Measuring the gap in this list instead counts a beat that drew
    # nothing as no distance at all, which flagged pairs that are never on
    # screen together -- and this is a blocking note, so it failed correct
    # boards.
    slots = slot_of or {}
    pos = [slots.get(e.get("id"), i) for i, e in enumerate(art)]
    seen, close = {}, []
    for i, name in enumerate(used):
        if name in seen and pos[i] - pos[seen[name]] <= LIVE:
            close.append((name, art[seen[name]].get("id") or "#%d" % seen[name],
                          art[i].get("id") or "#%d" % i))
        seen[name] = i
    if close:
        shown = ", ".join("%s (%s and %s)" % c for c in close[:4])
        out.append(("blocking",
                    "%d pictures are still on the board when the same drawing "
                    "arrives again, so two copies are on screen at once: %s%s"
                    % (len(close), shown, ", ..." if len(close) > 4 else "")))

    distinct = len(counts)
    if n_beats >= 20 and distinct < max(8, n_beats // 12):
        out.append(("fyi",
                    "%d beats are carried by only %d different illustrations. "
                    "A documentary of this length usually wants a wider "
                    "vocabulary than that." % (n_beats, distinct)))
    return out


def _word_cue(at, word, texts, times, order, look=4):
    """When ``word`` is first spoken at or after the beat anchor ``at``.

    Returns a line-relative reference (``"l12+1.30"``) so the cue re-times
    itself if the voiceover is re-recorded, or None when the word is never
    said. The offset within a line is interpolated from the word's character
    position: a narrator does not speak at a perfectly even rate, so it is an
    estimate — but the alternative in place until now was the *start of the
    line*, which is how a name came to appear on the board seconds before
    anyone said it.
    """
    if not word or not texts or beatplan is None:
        return None
    try:
        line, _end, _off = beatplan.parse_time(at)
    except Exception:
        return None
    if line is None or line not in order:
        return None
    pat = re.compile(r"\b%s\b" % re.escape(str(word).strip()), re.I)
    start = order.index(line)
    for lid in order[start:start + max(1, look)]:
        txt, span = texts.get(lid) or "", times.get(lid)
        if not txt or not span:
            continue
        m = pat.search(txt)
        if not m:
            continue
        dur = span[1] - span[0]
        if dur <= 0:
            return None
        return "%s%+g" % (lid, round(dur * (m.start() / len(txt)), 2))
    return None


def _shift(at, delta):
    """Offset a time reference without losing its line anchor."""
    if isinstance(at, (int, float)):
        return round(float(at) + delta, 2)
    try:
        line, end, off = beatplan.parse_time(at)
    except Exception:
        return at
    if line is None:
        return round(off + delta, 2)
    return "%s%s%+g" % (line, ".end" if end else "", round(off + delta, 2))


def _sortable(at, times):
    if isinstance(at, (int, float)):
        return float(at)
    try:
        return beatplan.resolve(at, times)
    except Exception:
        return 0.0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compile.py",
        description="Beat plan -> paper storyboard draft.")
    p.add_argument("plan")
    p.add_argument("-o", "--out", default="storyboard.json")
    p.add_argument("--aspect", choices=sorted(ASPECTS), default="16:9")
    p.add_argument("--seed", type=int)
    p.add_argument("--check", action="store_true",
                   help="report what it would do; write nothing")
    a = p.parse_args(argv)

    try:
        with open(a.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, ValueError) as e:
        print("compile: cannot read %s: %s" % (a.plan, e), file=sys.stderr)
        return 1

    root = os.path.dirname(os.path.abspath(a.plan))
    if beatplan:
        problems, _, _ = beatplan.validate(plan, root, measure=True)
        errs = [x for x in problems if x.level == "error"]
        if errs:
            print("compile: the beat plan does not validate; fix it first.\n",
                  file=sys.stderr)
            for x in errs:
                print("  %s" % x, file=sys.stderr)
            return 1

    region = plan.get("region")
    known = _known_regions()
    if region and known is not None and region not in known:
        print("compile: unknown region %r. This style draws: %s. Omit "
              "`region` for an unlabelled chart rather than a wrong one."
              % (region, ", ".join(sorted(known))), file=sys.stderr)
        return 1

    board, notes = compile_plan(plan, a.aspect, a.seed, root)

    if not a.check:
        tmp = a.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(board, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, a.out)

    print("%s  %d elements, %d camera moves, %d narration lines"
          % ("would write" if a.check else "wrote " + a.out,
             len(board["elements"]), len(board["camera"]["moves"]),
             len(board["narration"])))
    blocking = [n for sev, n in notes if sev == "blocking"]
    fyi = [n for sev, n in notes if sev != "blocking"]
    if blocking:
        print("\nneeds a human:")
        for n in blocking:
            print("  - %s" % n)
    if fyi:
        print("\nworth knowing:")
        for n in fyi:
            print("  - %s" % n)
    print("\nThis is a draft. Open it, cut what is decorative, and give the "
          "beats that matter more room.")
    # Only a board with a placeholder on it is a failure. A vertical-safe
    # reminder is advice, and exiting non-zero for advice trains people to
    # ignore the exit code.
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
