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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette  # noqa: E402  - sibling module, needs the path above
import staging  # noqa: E402  - sibling module, needs the path above
import score  # noqa: E402  - sibling module, needs the path above

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

#: How far the camera leans toward the subject of a shot.
#:
#: The reference film this style was calibrated on panned across a board
#: 789px wide and 430px tall over its twelve minutes. Measured again after
#: the slot grid collapsed from four quadrants to the two half-frames above,
#: the same figure was **384 x 20**: the lens had effectively stopped
#: travelling, and a viewer who had seen both said so.
#:
#: Two things caused it and this constant is only one of them. The other is
#: that the two slots share a vertical centre, so every beat asked the camera
#: to look at the same height — hence the 20px. The fix for that is to aim at
#: the staged subject rather than at the slot (see `subject_xy`); this raises
#: how far the lens is willing to go once it has somewhere to look.
#:
#: Overshoot is safe: `motion.apply_camera` clamps the crop inside the board,
#: so a lean that asks for more travel than exists parks at the edge instead
#: of showing blank paper.
#:
#: Calibrated down from 0.62 after a viewer reported "a bunch of unnecessary
#: camera shakes". The reference film's moves have a *mean* of 182px; at 0.62
#: this board's mean was 245px with a 501px peak, and constant movement that
#: large has no rest in it, so it reads as shaking rather than as travelling.
#: At 0.44 the mean is 191px — the reference's own figure — with a gentler
#: peak. Note that this constant does not set the median: the commonest moves
#: are tier-driven and belong to `_TIER_CAMERA`.
CAM_LEAN = 0.44

#: The camera sits pushed in slightly at all times. A lens at 1.0 has almost
#: no room to move — the board is only `OVER` larger than the frame — so a
#: film authored at zoom 1.0 cannot pan even when it is asked to. The
#: reference film never dropped below 1.12.
CAM_ZOOM_BASE = 1.12

#: What an `impact` beat gets instead of a shake.
#:
#: There is no camera shake in this style, anywhere. It was the most repeated
#: complaint across every review round: first as constant mid-size churn that
#: had no shake in it at all, then — once real shakes were gated down to beats
#: where something physically strikes — as the two remaining honest ones. A
#: shaken frame reads as a broken camera rather than as force, whatever the
#: sentence says.
#:
#: A beat that wants weight gets a **slow pan**: the furthest lean of any tier,
#: taken slowly, on a long ease. Same emphasis, made of travel instead of
#: vibration. `SLOW_PAN_LEAN` is deliberately above every entry in
#: `_TIER_CAMERA` so the loudest beat is still the one that moves furthest.
SLOW_PAN_LEAN = 0.78
SLOW_PAN_EASE = "in_out_cubic"

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


#: Hour names a narration spells out, for "half past ten".
_WORD_HOUR = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
              "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0,
              "ten": 10.0, "eleven": 11.0, "twelve": 12.0}


#: Every regex that can produce a given drawing, so a caller can ask how often
#: and how early a story actually names it. `pick_cast` ranks by match length,
#: which answers "which wording is most specific" and not "what is this act
#: about"; both questions have a use and they need different tables.
_NAME_PATTERNS = {}
for _pat, (_nm, _pp) in HINTS:
    _NAME_PATTERNS.setdefault(_nm, []).append(_pat)


def pick_cast(text, catalogue, limit=4):
    """Everything a line calls for, ordered so it can be staged.

    `pick_art` answers "what is this beat *about*" and returns one noun. That
    is the right question for a collage and the wrong one for a scene: a line
    that says *she carried the lantern up the hill* names three things, and
    drawing only the winner is what reduced this style to a slideshow of
    single objects. Worse, the winner was chosen by string length and an
    `OBJECT_FIRST` override, so a story about a hill drew `stairs` three
    times because "stairs" outranks "hill" whatever the sentence means.

    So this collects *all* the matches and keeps the best one per staging
    role — a place, someone in it, something they are holding, something
    overhead. Roles are what make the result composable: the stage knows how
    to put an actor on a ground and a prop in the actor's hand, and it cannot
    know that from a flat list of nouns.

    Returns ``[(name, params), ...]`` in staging order, longest match first
    within each role.
    """
    h = (text or "").lower()
    hits = []
    for pattern, (name, params) in HINTS:
        m = re.search(pattern, h)
        if m and name in catalogue:
            hits.append((m.end() - m.start(), name, dict(params)))
    if not hits:
        return []

    best = {}
    for span, name, params in hits:
        # A drawing named twice by one line is still one drawing; keep the
        # sighting with the more specific wording.
        if name not in best or span > best[name][0]:
            best[name] = (span, params)

    by_role = {}
    for name, (span, params) in best.items():
        by_role.setdefault(staging.role_of(name), []).append((span, name, params))
    for role in by_role:
        by_role[role].sort(key=lambda r: -r[0])

    #: How many of each role a single frame can hold before it stops being a
    #: composition and becomes a pile. Two actors is a conversation; three is
    #: a crowd, and there is a `crowd` drawing for that.
    room = {"ground": 1, "actor": 2, "prop": 2, "sky": 1, "atmos": 1, "diagram": 1}
    cast = []
    for role in ("ground", "actor", "prop", "sky", "atmos", "diagram"):
        for _span, name, params in by_role.get(role, [])[:room[role]]:
            cast.append((name, params))
    return cast[:limit]


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
# How long the film may open on blank paper before it reads as a stalled
# file. Two seconds, not the "2-5s" the reference used to suggest: a viewer
# reported exactly this defect on a four-second lead, which is the evidence
# that settled it. `lead_in` is silence before the first narration line, so
# whatever it is worth musically, visually it is an empty board.
BLANK_OPEN = 2.0

# A lead this long instead earns a staged opening -- the title card and two
# establishing objects -- so the paper is not blank and the rule above does
# not apply.
STAGED_OPEN = 6.0

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


def compile_plan(plan, aspect="16:9", seed=None, root=".", motion_plan=None):
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

    # The film's colour, chosen from what the narration is about. A plan may
    # name a palette outright; otherwise the words decide. Either way it is
    # recorded in the board as `style.palette`, so a reader can see which one
    # was picked and override it.
    story_text = " ".join(
        [str(plan.get("title") or "")]
        + [str(ln.get("text") or "") for ln in (plan.get("narration") or [])]
        + [str(b.get("subject") or "") for b in (plan.get("beats") or [])])
    look_name = plan.get("palette")
    if look_name in palette.PALETTES:
        look = dict(palette.PALETTES[look_name])
    else:
        look_name, look = palette.choose(story_text)

    # The look and the score are decided from the same reading of the same
    # text, so they agree by construction rather than by hoping. The palette's
    # own `score` hint is passed in as a bias, not a command: a story whose
    # words are unmistakably a ghost story should not be scored as a warm one
    # merely because its colours came out amber.
    _wpm = None
    if total and plan.get("narration"):
        _words = sum(len(str(ln.get("text") or "").split())
                     for ln in plan["narration"])
        if _words:
            _wpm = _words / (total / 60.0)
    _auto_music = score.music_for(
        story_text, palette_hint=(look.get("score") or {}).get("mood"),
        seed=seed % 9973, wpm=_wpm)

    # The bias above flows one way — palette into score — so when the score
    # overrules the hint, the picture is left contradicting the music: a film
    # scored as dread, printed on warm amber paper. Nothing catches it,
    # because each half is defensible alone.
    #
    # So the loop is closed here. If the score landed on a different mood and
    # the palette's own vote was not decisive, the picture follows the music.
    # The palette votes on the *nouns* in a story ("snow", "furnace"); the
    # score reads the whole narration. Where only one of them is sure, it
    # should be the one that wins.
    if not plan.get("palette"):
        _mood = (_auto_music or {}).get("mood")
        if _mood and _mood != (look.get("score") or {}).get("mood"):
            _n, _p = palette.for_mood(_mood)
            if _p and not palette.decisive(story_text):
                look_name, look = _n, _p
    # A film is spotted into cues, not covered by one bed. Act boundaries are
    # the natural cue boundaries because they are already where the story
    # turns; the last act runs to the end of the picture so its cue can
    # resolve rather than be cut off.
    _act_secs = []
    _marks = [a.get("from") for a in (plan.get("acts") or []) if a.get("from")]
    if _marks and total:
        _pts = [_sortable(mk, times) for mk in _marks]
        for _i, _p in enumerate(_pts):
            _end = _pts[_i + 1] if _i + 1 < len(_pts) else float(total)
            if _end - _p > 2.0:
                _act_secs.append((float(_p), float(_end)))
    if len(_act_secs) > 1:
        _auto_music = score.cue_sheet(
            story_text, _act_secs, wpm=_wpm,
            palette_hint=(look.get("score") or {}).get("mood"),
            seed=seed % 9973)
    _why_music = _auto_music.pop("_why", "")
    _auto_music.pop("_scores", None)
    _amb = score.ambience_for(story_text)
    _auto_ambience = {"type": _amb, "gain": 0.40} if _amb else None

    board = {
        "title": plan.get("title") or "untitled",
        "note": "Compiled from a beat plan by compile.py. This is a draft: the "
                "timing and layout are right, the taste is not yet.",
        "output": {"width": W, "height": H, "fps": 30, "crf": 20,
                   "preset": "medium", "path": _slug(plan.get("title")) + ".mp4",
                   "maxrate": "20M", "bufsize": "40M"},
        "style": {"seed": seed, "accent": look["accent"], "region": region,
                  "ink": look["ink"],
                  "paper_light": look["paper_light"],
                  "paper_deep": look["paper_deep"],
                  "palette": look_name,
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
        # The score is read out of the story, not stamped on it. Every film
        # this style made used to get `tension / minor / 60 bpm`, so a
        # children's story about a kite and a manhunt through a winter city
        # were scored identically. `score.music_for` picks the mode from the
        # story's valence, the tempo from its arousal and the register from
        # its subject; an explicit `music` block in the plan still wins.
        "music": plan.get("music") or _auto_music,
        "mix": plan.get("mix") or {"voice": 1.0, "music": 0.5, "sfx": 0.5,
                                   "duck_db": -10.0, "lufs": -14.0},
        "narration": [],
        "elements": [],
        "sfx": [],
    }
    if plan.get("ambience") or _auto_ambience:
        board["ambience"] = plan.get("ambience") or _auto_ambience

    for line in plan.get("narration") or []:
        entry = {"id": line["id"]}
        for k in ("audio", "duration", "gap_after", "text"):
            if line.get(k) is not None:
                entry[k] = line[k]
        board["narration"].append(entry)

    # The board itself. This card is the single largest surface in every frame
    # of the film, so whatever colour it is, that is the colour the film is.
    # It used to be a hardcoded beige, which is why every paper film came back
    # brown no matter which palette had been chosen: the palette was applied
    # faithfully to the drawings and then buried under a full-bleed sheet of
    # the same beige. Measured on a teal-palette film, the finished frames
    # averaged 19% saturation at hue 53 — brown — against the palette's own 46%.
    board["elements"].append({
        "type": "card", "at": [W // 2, H // 2],
        "w": int(W * 0.99), "h": int(H * 1.12),
        "seed": seed * 10, "rotate": round(jitter(rng, 0, 1.6), 2),
        "elevation": 0.16, "parallax": 0.05, "float": 0.4, "z": 0,
        "color": list(look["paper_light"]), "depth": 0.03, "fold": 0.3,
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

    # Blank paper at the open is the defect, and `lead_in` is where it comes
    # from: it is silence *before* the first narration line, so at that point
    # nothing has been drawn. Both shapes of opening can suffer it. For a
    # while only one of them was checked -- a four-second lead under a cold
    # open was blocked, while the same four seconds *without* one, which puts
    # exactly the same blank paper on screen, passed without a word -- so the
    # rule is stated once here and applied to both.
    #
    # The exception is a lead long enough to earn the staged title card and
    # its establishing objects below, which is the one case where the paper
    # is not blank.
    staged = teaser_ref is None and lead >= STAGED_OPEN
    if lead > BLANK_OPEN and not staged:
        notes.append(("blocking",
                      "the film opens on %.1fs of blank paper, because "
                      "`lead_in` runs before the first narration line%s. Cut "
                      "`lead_in` to a beat or two — %s." % (
                          lead,
                          " and the cold open only starts once it has elapsed"
                          if teaser_ref is not None else "",
                          "the teaser is the opening" if teaser_ref is not None
                          else "or hold it past %.0fs, which stages the title "
                               "card and two objects over it" % STAGED_OPEN)))

    if lead >= STAGED_OPEN and teaser_ref is None:
        notes.append(("fyi",
                      "the film opens on %.0fs of silence. That is a held "
                      "title, not a cold open — a viewer has nothing to "
                      "listen to yet. Write a teaser as the opening lines "
                      "and mark a hook `kind: \"cold-open\"` over them, and "
                      "the title will land when it ends." % lead))

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

    #: The narration each beat sits under. Casting a scene needs the whole
    #: sentence, not the one-word hint: "she carried the lantern up the hill"
    #: names a place, a prop and an action, and the hint carries at most one
    #: of them. Keyed by line id so a beat's `at` ("l4+0.30") can find it.
    line_text = {ln.get("id"): (ln.get("text") or "")
                 for ln in (plan.get("narration") or [])}

    def _beat_text(b):
        ref = str(b.get("at") or "")
        m = re.match(r"^([a-z]+\d+)", ref.strip())
        return " ".join(x for x in (b.get("subject"),
                                    _hint_of(b),
                                    line_text.get(m.group(1)) if m else None,
                                    " ".join(b.get("keywords") or [])) if x)

    #: The story's own chronology, as ``(y_fraction, label)`` pairs for a
    #: `timeline` drawing. Acts are the moments a story actually has; a
    #: timeline drawn from anything else is inventing a structure the film
    #: does not possess.
    _order = [ln.get("id") for ln in (plan.get("narration") or [])]

    def _line_frac(lid):
        try:
            return _order.index(lid) / max(1, len(_order) - 1)
        except ValueError:
            return None

    acts_ticks = []
    for a in (plan.get("acts") or []):
        f = _line_frac(a.get("from"))
        if f is None:
            continue
        # Inset a little top and bottom so the first and last entries are not
        # flush against the edge of the tile.
        acts_ticks.append((round(0.06 + 0.88 * f, 4), str(a.get("name") or "")))

    def _story_progress(beat_index):
        """How far through the narration this beat sits, 0..1."""
        b = beats[beat_index] if beat_index < len(beats) else {}
        m = re.match(r"^([a-z]+\d+)", str(b.get("at") or "").strip())
        f = _line_frac(m.group(1)) if m else None
        return 0.06 + 0.88 * (f if f is not None else 0.5)

    #: Times of day a narration can name, as clock hours. A clock drawn at
    #: its default 10:00 in a story that says "just before midnight" is
    #: actively misleading — it is a picture that contradicts the voice.
    _HOURS = [(r"\bmidnight\b", 0.0), (r"\bnoon|midday\b", 12.0),
              (r"\bdawn|sunrise|first light\b", 6.0),
              (r"\bdusk|sunset|nightfall\b", 19.5),
              (r"\bmorning\b", 8.5), (r"\bafternoon\b", 15.0),
              (r"\bevening\b", 20.0), (r"\bnight\b", 22.0)]

    def _clock_hours(text):
        t = (text or "").lower()
        m = re.search(r"\b(\d{1,2})[:.](\d{2})\b", t)
        if m:
            return round(int(m.group(1)) % 12 + int(m.group(2)) / 60.0, 3)
        m = re.search(r"\bhalf past (\w+)\b", t)
        if m and m.group(1) in _WORD_HOUR:
            return _WORD_HOUR[m.group(1)] + 0.5
        for pattern, hh in _HOURS:
            if re.search(pattern, t):
                return hh
        return None

    # ---- Held scene backgrounds -------------------------------------------
    # A background belongs to a *scene*, not to a shot. Limited animation
    # draws a location once and holds it while the characters move in front
    # of it. That is what makes the technique cheap, and it is also what makes
    # it legible: once the ground stops changing, the eye reads whatever *is*
    # changing as the subject. Re-picking a hillside from every individual
    # line produced the opposite -- every beat rebuilt its entire world, so a
    # quiet beat churned exactly as hard as a loud one and the film had no
    # motion contrast left to spend. Acts are the scene boundaries the plan
    # already declares, so each act establishes one setting and holds it.
    _act_bounds = [f for f in (_line_frac(a.get("from"))
                               for a in (plan.get("acts") or []))
                   if f is not None]

    def _act_of(beat_index):
        """Which act a beat falls in, by its position in the narration."""
        if not _act_bounds:
            return 0
        m = re.match(r"^([a-z]+\d+)",
                     str(beats[beat_index].get("at") or "").strip())
        f = _line_frac(m.group(1)) if m else None
        if f is None:
            return 0
        return max([0] + [j for j, bound in enumerate(_act_bounds)
                          if f >= bound - 1e-9])

    scene_of = {i: _act_of(i) for i in draws}
    #: act -> (first drawing beat, last drawing beat, staged setting cast).
    #: The setting is chosen from everything the act says rather than from
    #: one line of it, so a scene that opens indoors and mentions the window
    #: later still gets the room.
    scenes = {}
    _used_setting = []
    _prev_ground = []
    #: Every real ground the story has *named* so far, oldest first, and the
    #: most recent of them. Distinct from `_prev_ground`, which is only the
    #: last ground that was actually staged as a setting.
    _seen_grounds = []
    _last_named = None
    #: The staircase or slope the current act is standing on, if any, so a
    #: beat that climbs can measure its ascent against the thing on screen
    #: rather than against the frame.
    _held_ramp = None
    #: act -> (pan direction, the beat it opens on, the beat it closes on).
    #: Filled as each act's background is emitted, and read afterwards to give
    #: the camera a matching travel — the lens and the layers have to agree
    #: about which way the world is moving or the pan reads as a slip.
    _scene_pan = {}
    for _sc in sorted(set(scene_of.values())):
        _members = [i for i in draws if scene_of[i] == _sc]
        if not _members:
            continue
        _text = " ".join(_beat_text(beats[i]) for i in _members)
        # Deliberately *not* `pick_cast`: it keeps one ground per line, chosen
        # by match length, so the alternatives are gone before they can be
        # compared. An act's setting is a different question from a line's
        # subject and it needs to see every candidate the act named.
        _t_low = _text.lower()
        _cands = {}
        for _pat, (_nm, _pp) in HINTS:
            if _nm not in catalogue:
                continue
            _role = staging.role_of(_nm)
            if _role not in ("ground", "atmos", "sky"):
                continue
            for _m in re.finditer(_pat, _t_low):
                hits, first, _ = _cands.get(_nm, (0, len(_t_low), _pp))
                _cands[_nm] = (hits + 1, min(first, _m.start()), _pp)

        _recent = _used_setting[-2:]
        # How much of this act is about it, then which it names first. A story
        # that says "one lantern on the hill" and later "seven hundred steps"
        # is set on a hill that has steps on it, not in a stairwell.
        _grounds = sorted(
            ((n, dict(p)) for n, (_h, _f, p) in _cands.items()
             if staging.role_of(n) == "ground"),
            key=lambda c: (-_cands[c[0]][0], _cands[c[0]][1]))
        # A fixture is never a place: a staircase belongs *to* the hill it was
        # cut into. Ranked on mentions alone it wins whenever the story dwells
        # on the climb, and the wanting-a-fresh-place rule below makes that
        # worse — an act set by the sea, followed by an act about climbing, has
        # only the staircase left as a "new" ground. The act then holds a
        # flight of steps as its setting, the hill is demoted to a passing beat
        # and leaves, and the steps are still standing there in open water once
        # the story has put to sea. Held back until nothing else is on offer.
        _real_g = [c for c in _grounds if c[0] not in staging.FIXTURE]
        _fresh_g = [c for c in _real_g if c[0] not in _recent]
        # A fixture implies its host. "Three hundred and twelve steps" is not a
        # new place, it is the hill the story stopped at one line earlier —
        # and an act whose only fresh ground is a staircase would otherwise
        # fall through to whatever it *does* name, which here is the sea, and
        # set the climb out on the water. So when an act names a fixture and
        # no new place of its own, it inherits the last real ground the story
        # mentioned rather than the last one that happened to be staged.
        _fixture_here = [c for c in _grounds if c[0] in staging.FIXTURE]
        _host = ([c for c in _seen_grounds if c[0] == _last_named][:1]
                 if _fixture_here and _last_named else [])
        # Variety must never cost the ground itself. A scene with only weather
        # and a moon in it has nothing for anyone to stand on, and every figure
        # in the act floats. An act that names no new place has not moved --
        # it is still in the last one -- so inherit rather than invent.
        _ground = (_fresh_g or _host or _real_g or _prev_ground or _grounds)[:1]
        for _c in sorted(_real_g, key=lambda c: _cands[c[0]][1]):
            _seen_grounds = [g for g in _seen_grounds if g[0] != _c[0]] + [_c]
            _last_named = _c[0]
        _over = sorted(
            ((n, dict(p)) for n, (_h, _f, p) in _cands.items()
             if staging.role_of(n) in ("atmos", "sky")),
            key=lambda c: (-_cands[c[0]][0], _cands[c[0]][1]))[:1]
        _setting = _ground + _over
        if _setting:
            scenes[_sc] = (_members[0], _members[-1], _setting)
            if _ground:
                _prev_ground = list(_ground)
                _used_setting.append(_ground[0][0])

    def _leave_of(beat_index):
        """When the given beat's slot is claimed by a later beat."""
        succ = slot_order.get(beat_index)
        if succ is None:
            return None
        succ += LIVE + 1
        if succ >= len(draws):
            return None
        return {"t": _shift(beats[draws[succ]]["at"], -0.45), "dur": 0.5}

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
        # Where the camera will actually look, and where the shot's travel
        # ends. Both are filled in once the beat has been staged, because
        # neither is knowable from the slot.
        subject_xy = None
        travel_to = None
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

        btext = _beat_text(b)
        # Establish this scene's background, once, on the first beat that
        # draws in it. It is then held for the whole act: no exit, no
        # re-entrance, no idle float. Everything after this beat plays in
        # front of it.
        _sc = scene_of.get(i, 0)
        _scene = scenes.get(_sc)
        if _scene and _scene[0] == i:
            _first, _last, _setting = _scene
            _sleave = _leave_of(_last)
            # Which way this act's camera travels. Alternating means a film
            # never pans the same direction twice running, so successive
            # scene changes read as moving *through* a space rather than as a
            # conveyor belt running one way.
            _pan = -1 if (_sc % 2 == 0) else 1
            _scene_places = staging.stage(_setting, W, H, z0=zc, facing=1,
                                          horizon=staging.horizon_for(_sc))
            # A beat that climbs while its act holds the staircase has no
            # ground of its own to measure the ascent against, so without
            # this the figure fell back to a frame-relative guess and stood
            # beside the steps instead of on them.
            _held_ramp = next((p for p in _scene_places
                               if p["name"] in staging.RAMP), None) \
                or next((p for p in _scene_places
                         if p["role"] == "ground"), None)
            for si, spl in enumerate(_scene_places):
                ec += 1
                sel = {"type": "art", "name": spl["name"],
                       "at": [round(spl["at"][0], 1), round(spl["at"][1], 1)],
                       "fit": [round(spl["fit"][0], 1), round(spl["fit"][1], 1)],
                       "size": int(max(spl["fit"])),
                       "id": "sc%d_%d" % (_sc, si), "z": spl["z"], "seed": ec,
                       "elevation": 0.18,
                       "parallax": round(min(0.5, spl["z"] / 46.0), 2),
                       "float": 0.0,
                       # `_sc + si`, not `si`: every scene's first element is
                       # si=0, so indexing by position alone gave all four
                       # acts of a film the same coloured ground.
                       "ink": palette.ink_for(look, spl["role"], _sc + si, 0.5),
                       "sfx": None}
                if _sc == 0:
                    # The film's first place is not arrived at; it is simply
                    # where we start.
                    sel["in"] = {"t": _shift(at, 0.05 * si), "dur": 1.1,
                                 "anim": "fade"}
                else:
                    # Every later act *arrives*: the new place slides in from
                    # the edge the camera is travelling towards, which is what
                    # makes the cut read as the same continuous world seen
                    # further along rather than as a new slide.
                    sel["in"] = {"t": _shift(at, 0.05 * si), "dur": 1.0,
                                 "anim": "slide",
                                 "from_x": int(-_pan * W * 0.55), "from_y": 0}
                if _sleave:
                    # ...and leaves the same way, in one piece.
                    sel["out"] = dict(_sleave, anim="pan",
                                      dx=int(_pan * W * 0.62), dy=0)
                sel.update(spl["params"])
                board["elements"].append(sel)
            zc += 2 * len(_setting) + 2
            _scene_pan[_sc] = (_pan, at, _last)
        cast = pick_cast(btext, catalogue)
        # The scene already shows where this is. A beat that names the place
        # again would draw a second hillside on top of the first one.
        if _scene:
            cast = [(n, p) for n, p in cast
                    if staging.role_of(n) not in ("ground", "atmos", "sky")]
        # The hint is the author speaking directly, so whatever it names must
        # be in the scene even if the sentence around it never says the word.
        # Unless the held scene *is* that thing: re-inserting it drew a
        # second staircase exactly on top of the act's own staircase, which
        # is the doubled-image defect in its purest form.
        _scene_names = {n for n, _ in (_scene[2] if _scene else [])}
        if name and name not in [c[0] for c in cast] \
                and name not in _scene_names:
            cast.insert(0 if staging.role_of(name) == "ground" else len(cast),
                        (name, dict(params)))
            cast = cast[:4]

        # A vessel needs water under it. A beat that puts a boat into an act
        # held on land stages it on the ground line, and the ground line is
        # the hillside — so the film shows a trawler parked on a mountain.
        # The sea is brought in behind the land for it to sit on. Only when
        # the held setting is land: at sea the scene already is the water.
        if any(n in staging.WATERBORNE for n, _ in cast) \
                and _scene_names and not (_scene_names & staging.WATER) \
                and not any(n in staging.WATER for n, _ in cast):
            cast.insert(0, ("sea", {}))
            cast = cast[:4]

        # ...and a person needs land under them, which is the same rule seen
        # from the other side. An act held at sea stages its actors on the
        # ground line, and at sea the ground line is the water — so the film
        # showed Meera standing on the open ocean for the line "Meera sat down
        # beside the light". Whatever land the story last named is brought in
        # for her to stand on, unless she is aboard something that floats.
        #
        # This has to run *after* the traveller and companion rules below,
        # not before them: those are what put a figure into a beat whose text
        # never named one, and checking first meant the opening shot — "Meera
        # walked the shore road", cast from the word "sea" alone — was judged
        # to have nobody in it and left her walking on the water.
        def _needs_land(cast):
            return (_scene_names and (_scene_names & staging.WATER)
                    and any(n in staging.PERSON for n, _ in cast)
                    and not any(n in staging.WATERBORNE for n, _ in cast)
                    and not any(n in staging.GROUND and n not in staging.WATER
                                for n, _ in cast))

        medium = staging.motion_of(btext)

        depth = staging.depth_of(btext)
        # A journey needs a traveller. Prose routinely describes travel
        # without ever naming who is doing it -- *"For whoever was still
        # walking home"*, *"had carried it up for forty-one years"* -- and a
        # literal reading casts nobody, so the one shot that most needs to
        # move is the one shot that cannot. If the line travels, put someone
        # in it to do the travelling.
        if medium and not any(staging.role_of(c) == "actor" for c, _ in cast):
            mover = "boat" if medium == "water" else \
                    "plane" if medium == "air" else \
                    "car" if medium == "road" else "figure"
            if mover not in catalogue:
                mover = "figure"
            cast.append((mover, {}))
            cast = cast[:4]

        # "Behind her" needs two figures the same way a journey needs a
        # traveller: pursuit is a relation *between* two things, and a
        # sentence that names only one of them still means both are there.
        # Distance is not the same thing and must not cast a companion — read
        # as pursuit, "far out, a fishing boat" put a second boat in front of
        # the first, so the shot said two boats.
        if depth:
            _n_actors = sum(1 for c, _ in cast if staging.role_of(c) == "actor")
            if _n_actors == 0:
                depth = None
            elif depth == "pursuit" and _n_actors == 1 and "figure" in catalogue:
                cast.append(("figure", {}))
                cast = cast[:4]

        if _needs_land(cast):
            _land = _last_named if _last_named and _last_named \
                not in staging.WATER else "hill"
            cast.insert(0, (_land, {}))
            cast = cast[:4]

        # A flame is a *state of* a lantern, and the sentence that lights one
        # usually names only the fire. Staged alone the attachment has no host
        # to sit on, and a flame at hand size in an empty frame reads as a
        # mistake — which is how a lit lantern came to be drawn as a
        # frame-filling blaze. If the host is missing, put it back.
        _names = [c[0] for c in cast]
        for _nm in list(_names):
            _hosts = staging.ATTACH.get(_nm)
            if _hosts and not any(h in _names for h in _hosts):
                _h = next((h for h in _hosts if h in catalogue), None)
                if _h:
                    cast.insert(0, (_h, {}))
                    _names.insert(0, _h)
                    cast = cast[:4]

        # A climb needs something to climb. The verb says there is a slope
        # under the figure, so if the sentence never named one, put the one
        # it implies on stage — otherwise the ascent happens in mid-air.
        if medium in staging.VERTICAL and \
                not any(staging.role_of(c) == "ground" for c, _ in cast):
            _slope = "stairs" if re.search(r"stair|step", btext, re.I) else "hill"
            if _slope in catalogue and not _scene:
                cast.insert(0, (_slope, {}))
                cast = cast[:4]

        if cast:
            # Alternate which way the stage faces. A film whose every scene
            # looks the same way reads as one long shot of the same place;
            # flipping is the cheapest possible change of angle, and it costs
            # nothing because the drawings are symmetrical about their own box.
            facing = 1 if (k % 2 == 0) else -1
            places = staging.stage(cast, W, H, z0=zc, facing=facing,
                                   has_scene=bool(_scene),
                                   medium=medium, depth=depth,
                                   ramp_box=_held_ramp if _scene else None,
                                   # the same ground line the act's held
                                   # background was drawn on, or the figures
                                   # in front of it stand in mid-air
                                   horizon=staging.horizon_for(_sc))
            # Move this act's cast to this act's stage centre. Scenery stays
            # put — it is drawn wider than the frame and is what everything
            # stands on — so this is a rigid translation of the things that
            # act, which keeps every relative measurement (a climb's travel, a
            # separation, an attachment's offset) intact.
            _bias = W * staging.stage_x_for(_sc) - W * 0.5
            # A climb is measured against the act's *held* staircase, which is
            # scenery and does not move with the cast. Translating the figure
            # away from it puts them back beside the steps instead of on them
            # — the exact defect the ramp work was done to fix.
            if medium in staging.VERTICAL and _held_ramp is not None:
                _bias = 0.0
            _movable = [p for p in places
                        if p["role"] not in ("ground", "ground_far", "sky",
                                             "atmos")]
            if _bias and _movable:
                lo = min(p["at"][0] - p["fit"][0] / 2 for p in _movable)
                hi = max(p["at"][0] + p["fit"][0] / 2 for p in _movable)
                # never push the group off the board: an actor cropped in half
                # is a worse defect than one standing nearer the middle
                _bias = max(W * 0.03 - lo, min(W * 0.97 - hi, _bias))
                for p in _movable:
                    p["at"][0] += _bias
            # What the shot is about, ranked. The camera aims here instead of
            # at the slot: since the scene grammar arrived, a beat's picture
            # is staged across the whole frame and ignores its slot entirely,
            # so a lens pointed at the slot was pointed at a rectangle
            # nothing had been drawn in.
            _rank = {"actor": 0, "subject": 1, "diagram": 2, "route": 2,
                     "prop": 3, "inset": 4, "upstage": 5, "ground_far": 6,
                     "ground": 7, "sky": 8, "attach": 9, "atmos": 10}
            _subj = min(places, key=lambda p: _rank.get(p["role"], 11))
            subject_xy = (_subj["at"][0], _subj["at"][1])
            zc += 2 * len(places) + 2
            for pi, pl in enumerate(places):
                ec += 1
                # The first placement keeps the bare beat id; the rest are
                # suffixed. `apply_motion_plan` groups elements by the part
                # before the underscore, so the whole scene inherits its
                # beat's animation tier without any further bookkeeping.
                eid = bid if pi == 0 else "%s_s%d" % (bid, pi)
                # Only the subject of the shot gets an entrance. The ground it
                # stands on, the weather over it and the sky behind it are
                # *setting*: in limited animation the background is a held
                # layer and only the character moves, which is the entire
                # reason the technique is cheap and the entire reason it reads
                # as deliberate. Flying every element of a composed scene in
                # separately made every beat as busy as every other beat and
                # flattened the motion budget the whole film is built on.
                _setting = staging.role_of(pl["name"]) in ("ground", "atmos", "sky")
                if _setting:
                    _in = {"t": _shift(at, 0.04 * pi),
                           "dur": round(0.75 + 0.25 * (1 - emphasis), 2),
                           "anim": "fade"}
                else:
                    _in = {"t": _shift(at, 0.10 * pi),
                           "dur": round(0.5 + 0.2 * (1 - emphasis), 2),
                           "anim": "fly", "from_y": -140,
                           "height": round(1.1 + 0.2 * emphasis, 2),
                           "spin": round(jitter(rng, 0, 8), 1)}
                el = {"type": "art", "name": pl["name"],
                      "at": [round(pl["at"][0], 1), round(pl["at"][1], 1)],
                      "fit": [round(pl["fit"][0], 1), round(pl["fit"][1], 1)],
                      "size": int(max(pl["fit"])),
                      "id": eid, "z": pl["z"], "seed": ec,
                      "elevation": round(0.22 + 0.16 * emphasis, 2),
                      "parallax": round(min(0.5, pl["z"] / 46.0), 2),
                      # Settings do not bob. An idle float on a hillside makes
                      # the ground look like it is floating, because it is.
                      "float": 0.0 if _setting else round(0.8 + emphasis, 1),
                      # The sheet this piece is cut from. Without it every
                      # drawing in the film inherits the one film-level ink,
                      # which is precisely why every film came out brown no
                      # matter which palette the story chose.
                      "ink": palette.ink_for(look, pl["role"], pi, emphasis),
                      "in": _in,
                      "sfx": None}
                # What this shot sounds like, taken from what the line says.
                # Only the first placement in a scene carries it, or a beat
                # naming four things would fire the same effect four times.
                if pi == 0:
                    _s = score.sfx_for(btext)
                    # An ambient bed is already running underneath the whole
                    # film; firing a one-shot of the same sound on top of it
                    # just makes the bed briefly louder for no reason.
                    if _s and _s != (_auto_ambience or {}).get("type"):
                        el["sfx"] = _s
                        el["sfx_gain"] = 0.55
                        if _s == "steps":
                            # Footsteps on snow and footsteps on floorboards
                            # are not the same sound, and the line usually
                            # says which. Look at the whole story first so a
                            # blizzard established in act one still governs a
                            # later line that only says "she climbed".
                            el["sfx_params"] = {
                                "surface": score.surface_for(
                                    btext + " " + story_text)}
                    else:
                        # Fall back to the sound of the medium: a scrap of
                        # paper landing. It is honest about what is on screen
                        # and it keeps the cut from feeling silent.
                        el["sfx"] = "paper"
                        el["sfx_gain"] = 0.5
                if leave:
                    el["out"] = dict(leave)
                el.update(pl["params"])
                # A journey the narration names has to happen on screen. The
                # actor is the thing that travels; the ground it crosses
                # stays put, which is what makes the travel legible.
                if medium and pl["role"] == "actor":
                    el["drift"] = staging.traverse(medium, el["in"]["t"], 2.6,
                                                   facing=facing,
                                                   width=W, height=H)
                    # A climb measured against the slope beats a climb
                    # measured against the frame: the stage knows how tall the
                    # hill it just drew is, and `traverse` does not.
                    if pl.get("travel"):
                        el["drift"]["x"] = pl["travel"]["x"]
                        el["drift"]["y"] = pl["travel"]["y"]
                    # Where the traveller ends up, so the camera can go with
                    # them. A journey the lens does not follow is a journey
                    # that finishes in the corner of the frame.
                    travel_to = (pl["at"][0] + el["drift"]["x"],
                                 pl["at"][1] + el["drift"]["y"])
                    # Entering from the direction of travel, rather than
                    # dropping in from above, reads as "arriving".
                    el["in"] = dict(el["in"], anim="slide",
                                    from_x=int(-160 * facing), from_y=0)
                if pl["name"] == "thread":
                    el["points"] = staging.route_points(
                        max(2, len(words) or 3), seed=ec, medium=medium or "air")
                # A chronology with no moments in it, a clock with no time on
                # it and a route joining nowhere are decorations that merely
                # resemble information. If the film is going to put a diagram
                # on screen it has to say what the diagram is *of*, and the
                # plan already knows: its acts are the story's own moments.
                if pl["name"] == "timeline" and acts_ticks:
                    # `(position, is_major)` — every act boundary is a major
                    # moment by definition; that is what makes it an act.
                    el["ticks"] = [[t, True] for t, _ in acts_ticks]
                    el["labels"] = [lab for _, lab in acts_ticks]
                    el["progress"] = round(_story_progress(i), 3)
                if pl["name"] == "clock":
                    hh = _clock_hours(btext)
                    if hh is not None:
                        el["hours"] = hh
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
            # A caption placed hard against the slot edge survives a still
            # frame but not a moving one: since the camera started leaning
            # properly it crops the last letter off any chip sitting in the
            # outer margin. Pull it back inside a band the lens can always
            # reach without losing a word.
            _chw = (len(text) * csize * 0.60) / 2 + 30
            cx = max(W * 0.05 + _chw, min(W * 0.95 - _chw, cx))
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

        # The camera looks at what the shot is *about*, and leans most of the
        # way there rather than a token 18%. The old aim was the beat's slot,
        # which the scene grammar stopped using — and because the two slots
        # share a vertical centre, every beat in the film asked the lens to
        # look at the same height. See `CAM_LEAN`.
        _cx, _cy = subject_xy if subject_xy else (x, y)
        _lean = CAM_LEAN * (0.78 + 0.36 * emphasis)
        board["camera"]["moves"].append({
            "t": at,
            "at": [int(W / 2 + (_cx - W / 2) * _lean),
                   int(H / 2 + (_cy - H / 2) * _lean)],
            "zoom": round(CAM_ZOOM_BASE + 0.10 * emphasis, 3),
            "hold": 0.5,
            "_beat": bid, "_xy": [int(_cx), int(_cy)]})

        # If the beat travels, the lens travels with it, arriving where the
        # traveller arrives. This is the difference between a figure sliding
        # across a static frame and a shot that follows someone — and on a
        # climb it is the only thing that puts the *top* of the slope on
        # screen, since the camera started at the bottom with the climber.
        if travel_to is not None:
            board["camera"]["moves"].append({
                "t": _shift(at, 1.6),
                "at": [int(W / 2 + (travel_to[0] - W / 2) * _lean),
                       int(H / 2 + (travel_to[1] - H / 2) * _lean)],
                "zoom": round(CAM_ZOOM_BASE + 0.06 * emphasis, 3),
                "hold": 0.3, "_beat": bid,
                # `_xy` is not optional here. `apply_motion_plan` re-aims
                # every move it recognises from this key and falls back to
                # the centre of the frame when it is missing — so a follow
                # move without one is silently turned into a move back to
                # the middle, which is the opposite of following.
                "_xy": [int(travel_to[0]), int(travel_to[1])]})

    for act in plan.get("acts") or []:
        if act.get("from"):
            board["camera"]["moves"].append(
                {"t": act["from"], "at": [W // 2, H // 2],
                 "zoom": CAM_ZOOM_BASE, "hold": 0.4})

    # A scene change is a *move*, not a cut. The outgoing act slides out on
    # `out.anim = "pan"` and the incoming one slides in from the far edge;
    # these two moves are the lens doing the same thing at the same time, so
    # the audience reads one continuous space rather than two slides.
    #
    # The camera swings out ahead of the change and recovers to centre as the
    # new place settles. Without the recovery the film would drift further
    # off-centre with every act and end up looking at the corner of the board.
    for _sc, (_pan, _open_at, _close_i) in sorted(_scene_pan.items()):
        if _sc == 0:
            continue
        board["camera"]["moves"].append({
            "t": _shift(_open_at, -0.55),
            "at": [int(W / 2 - _pan * W * 0.18), H // 2],
            "zoom": CAM_ZOOM_BASE, "hold": 0.0, "_pan": _sc})
        board["camera"]["moves"].append({
            "t": _shift(_open_at, 0.85),
            "at": [W // 2, H // 2],
            "zoom": CAM_ZOOM_BASE, "hold": 0.3, "_pan": _sc})

    board["camera"]["moves"].sort(key=lambda m: _sortable(m["t"], times))

    if motion_plan:
        notes.extend(apply_motion_plan(board, motion_plan, W, H, times))
    for mv in board["camera"]["moves"]:
        mv.pop("_beat", None)
        mv.pop("_xy", None)
        mv.pop("_pan", None)

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

    # One object, one copy. Elements are held for several beats so a place
    # persists, but that also means a later beat naming the *same* drawing
    # stamps a second copy of it beside the first — two lanterns, two boats,
    # two figures — and a viewer reads that as the film repeating its assets
    # rather than as continuity. Whichever copy arrives later wins: the
    # earlier one is retired as the new one lands, so the object appears to
    # have moved rather than to have been cloned.
    #
    # Scoped to *different* beats on purpose. Two copies of one drawing inside
    # a single beat are deliberate — that is how depth is staged, a figure in
    # front and the same figure smaller behind — and retiring one of those
    # would undo the shot.
    def _beat_of(el):
        return (el.get("id") or "").split("_")[0]

    _live = {}
    for el in sorted((e for e in board["elements"] if e.get("type") == "art"
                      and e.get("name") and e.get("in")),
                     key=lambda e: _sortable(e["in"].get("t"), times)):
        nm = el["name"]
        prev = _live.get(nm)
        if prev is not None and _beat_of(prev) != _beat_of(el):
            arrives = _sortable(el["in"].get("t"), times)
            cur = prev.get("out")
            # Cap, never extend — a copy that already leaves earlier is not
            # made to linger just because a namesake turned up.
            if not cur or _sortable(cur.get("t"), times) > arrives:
                prev["out"] = {"t": el["in"].get("t"), "dur": 0.4}
        if prev is None or _beat_of(prev) != _beat_of(el):
            _live[nm] = el

    # One place at a time. Act backgrounds are deliberately held and their
    # lifetimes overlap so a change of act reads as continuous rather than as
    # a cut — but two *settings* on screen at once do not read as continuity,
    # they read as an error: a staircase drawn across open water, a hillside
    # standing in the sea. The outgoing setting leaves as the incoming one
    # lands.
    _scene_els = sorted((e for e in board["elements"]
                         if str(e.get("id") or "").startswith("sc")
                         and e.get("type") == "art" and e.get("in")),
                        key=lambda e: _sortable(e["in"].get("t"), times))
    for prev, nxt in zip(_scene_els, _scene_els[1:]):
        if str(prev.get("id")).split("_")[0] == str(nxt.get("id")).split("_")[0]:
            continue  # same act, two layers of one place
        arrives = _sortable(nxt["in"].get("t"), times)
        cur = prev.get("out")
        if not cur or _sortable(cur.get("t"), times) > arrives:
            prev["out"] = {"t": nxt["in"].get("t"), "dur": 0.6}

    # One place at a time, and nothing left over from the last one. Act
    # settings already hand off cleanly, but everything *else* an act staged —
    # its figures, its lantern, its boat — was still held for `LIVE` slots and
    # so walked into the next act's frame. A lantern from the hilltop still
    # burning over an open-sea scene reads as a mistake, not as continuity.
    # Every element belonging to an act leaves as the next act's setting lands.
    _beat_scene = {}
    for _i, _k in scene_of.items():
        _bid = beats[_i].get("id") or "b%d" % _i
        _beat_scene[_bid] = _k
    _scene_starts = {}
    for e in board["elements"]:
        _eid = str(e.get("id") or "")
        if _eid.startswith("sc") and e.get("in"):
            _k = _eid.split("_")[0]
            _t = _sortable(e["in"].get("t"), times)
            if _k not in _scene_starts or _t < _scene_starts[_k][0]:
                _scene_starts[_k] = (_t, e["in"].get("t"))
    for e in board["elements"]:
        _eid = str(e.get("id") or "")
        if _eid.startswith("sc") or e.get("type") not in ("art", "chip"):
            continue
        _k = _beat_scene.get(_eid.split("_")[0])
        if _k is None:
            continue
        _nxt = _scene_starts.get("sc%d" % (_k + 1))
        if not _nxt:
            continue
        cur = e.get("out")
        if not cur or _sortable(cur.get("t"), times) > _nxt[0]:
            e["out"] = {"t": _nxt[1], "dur": 0.5}

    _hold_ground_under_actors(board, times, notes)
    _recede_second_ground(board, times, W, H, notes)
    _keep_text_legible(board, times, W, H, notes)
    _reseat_vessels(board, times, None)
    _separate_live_overlaps(board, times, W, H, notes)
    # Seating is settled *after* separation, because separation is what moves
    # a drawing along the slope in the first place, and it is settled before
    # the vessels are, so a hull dropped onto a hillside still ends up back on
    # its own waterline.
    _seat_on_ground(board, times, notes)
    _reseat_vessels(board, times, notes)

    # Captions live above the world, always. A chip is given the z of the beat
    # that raised it, which is correct until a *later* beat lays artwork over
    # the top of it — and because a chip is deliberately held past its own
    # beat so it can be read, that happens constantly. Measured on the 37-beat
    # board, seven captions were buried this way. Lifting them into a reserved
    # band above every drawing costs nothing and cannot regress.
    _art_top = max([int(e.get("z", 0)) for e in board["elements"]
                    if e.get("type") == "art"] or [0])
    _lifted = 0
    for e in board["elements"]:
        if e.get("type") == "chip" and int(e.get("z", 0)) <= _art_top:
            e["z"] = _art_top + 1 + int(e.get("z", 0)) % 50
            _lifted += 1
    if _lifted:
        notes.append(("fyi",
                      "%d caption(s) were sitting below artwork raised by a "
                      "later beat and were lifted above it." % _lifted))

    _reanchor_attachments(board, times, notes)
    # Staggering moves arrival times, and which ground is on screen with a
    # drawing depends on those times — so seating is settled once more
    # against the timing the film will actually play.
    if _stagger_handovers(board, times, notes):
        _seat_on_ground(board, times, None)
        _reseat_vessels(board, times, None)
        _reanchor_attachments(board, times, None)
    # Last, because a drift is measured from `at` and every pass above may
    # still move it.
    _land_drifts(board, times, notes)
    # A ground is exempt from the overlap check because it is *meant* to have
    # things standing on it — but only the things that belong to it.
    if _clear_ground_arrivals(board, times, notes):
        _reanchor_attachments(board, times, None)
    # Where the lens points is settled only now: the motion plan re-aims every
    # move it recognises, and the caption lift above moves the very words this
    # checks for. Anything done earlier is overwritten by one or the other.
    _keep_captions_framed(board, times, W, H, notes)
    _drop_flickers(board, times, notes)

    notes.extend(_variety_notes(
        board, len(beats),
        [b.get("id") or "b%d" % i for i, b in enumerate(beats)],
        {(beats[i].get("id") or "b%d" % i): k
         for i, k in slot_order.items()},
        times))

    notes.extend(_hard_rules(board, _beat_scene, _scene_starts, times))

    if not plan.get("music"):
        notes.append(("fyi", "score read from the story: " + _why_music))
    if _auto_ambience and not plan.get("ambience"):
        notes.append(("fyi",
                      "ambience: a continuous bed of %s under the whole film, "
                      "because that is what this story is mostly about"
                      % _auto_ambience["type"]))

    return board, notes


#: A single illustration carrying more than this share of the beats is the
#: signature of a board that reached for whatever was nearest.
ART_SHARE_MAX = 0.12


# How hard the camera leans toward a beat, and how far it pushes in, per tier
# of the animation director's motion plan. `hold` is absent on purpose: a held
# shot emits no move at all, which is the whole point of it.
#
# Lean is deliberately conservative even at the top. Translation is what crops
# a word off the edge of the board; zoom is not, and on paper grain a push
# changes every pixel in every frame just as effectively. So the accent is
# bought mostly with zoom and only partly with travel.
def _beat_bbox(board, bid, W, H, readable=False):
    """The box every piece of a beat occupies, in board pixels.

    Uses the compiler's own geometry models rather than measuring glyphs,
    because `Slot` already has to run where PIL is not guaranteed and the two
    estimates must agree.

    `readable` narrows it to the things that have to stay *on screen*: the
    captions and the subject, but not the scenery. A staged setting is drawn
    `GROUND_W` — wider than the frame — on purpose, so that the frame is a
    window onto a place rather than a picture of one. Counted as something
    that must be framed, it is unframeable, and a camera asked to keep it in
    shot can only sit dead centre. That is a landscape doing the one thing it
    was drawn not to do: pin the lens down.
    """
    x0, y0, x1, y1 = W, H, 0, 0
    found = False
    for el in board["elements"]:
        eid = el.get("id") or ""
        if eid != bid and not eid.startswith(bid + "_") and el.get("box_of") != bid:
            continue
        cx, cy = el.get("at", [W // 2, H // 2])[:2]
        if el.get("type") == "chip":
            size = float(el.get("size", 60))
            hw = (len(str(el.get("text", ""))) * size * 0.60) / 2 + 30
            hh = _half(size)
        elif el.get("fit"):
            hw, hh = float(el["fit"][0]) / 2, float(el["fit"][1]) / 2
        elif el.get("w") and el.get("h"):
            hw, hh = float(el["w"]) / 2, float(el["h"]) / 2
        else:
            hw = hh = float(el.get("size", 200)) / 2
        if readable and hw * 2 >= W * 0.85:
            continue
        x0, y0 = min(x0, cx - hw), min(y0, cy - hh)
        x1, y1 = max(x1, cx + hw), max(y1, cy + hh)
        found = True
    return (x0, y0, x1, y1) if found else None


def _keep_captions_framed(board, times, W, H, notes=None):
    """No word is ever half off the edge, whoever aimed the lens.

    Moves that come from the motion plan are already pulled back until the
    beat and its captions fit. The moves that stage an **act change** are not:
    they lean a flat `0.18 * W` — 345 px — out ahead of the change so the
    outgoing place slides away, and they were written before captions were
    checked at all. Measured, that cropped 3 captions on the 12-beat board and
    **35** on the 37-beat one, including "THE ROCKS" arriving on screen as
    "ROCKS".

    It is the stage-space blind spot again, in its purest form: the caption is
    exactly where it should be on the board, and the lens is simply not
    pointing at it. So this runs over *every* move, whatever produced it,
    after the motion plan has had its say and the zooms are final. The aim is
    only ever pulled back toward the words, never pushed; where even a full
    frame cannot hold them the zoom is eased out first, and if that is still
    not enough the move is left alone for the zoom pass to own.
    """
    moved = 0
    for mv in board["camera"]["moves"]:
        bb = _live_chip_box(board, _sortable(mv.get("t"), times), times, W, H,
                            fade=0.65)
        if not bb:
            continue
        z = float(mv.get("zoom", 1.0) or 1.0)
        need_w, need_h = bb[2] - bb[0], bb[3] - bb[1]
        if need_w > W / z or need_h > H / z:
            z = max(1.0, min(z, W / max(1.0, need_w), H / max(1.0, need_h)))
            if need_w > W / z or need_h > H / z:
                continue
            mv["zoom"] = round(z, 3)
        hw, hh = W / 2.0 / z, H / 2.0 / z
        cx, cy = mv["at"][:2]
        ncx = min(max(cx, bb[2] - hw), bb[0] + hw)
        ncy = min(max(cy, bb[3] - hh), bb[1] + hh)
        if abs(ncx - cx) > 1.0 or abs(ncy - cy) > 1.0:
            mv["at"] = [int(round(ncx)), int(round(ncy))]
            moved += 1
    if moved and notes is not None:
        notes.append(("fyi",
                      "%d camera move(s) were pointing away from a caption "
                      "that was on screen and were aimed back" % moved))
    return moved


def _live_chip_box(board, at_t, times, W, H, fade=0.0):
    """The box covering every caption on screen at ``at_t``.

    A beat's own headroom says nothing about the captions a *previous* beat
    left standing. Those are held on purpose — a chip lingers so the viewer
    can finish reading it — but the next beat's camera does not know they are
    there, and a hard push on a tight beat crops the word off the one before
    it. Measured on a 12-beat film, a 1.29 push aimed left cropped "KALVARI"
    while the lens was busy framing "312 STEPS".
    """
    x0, y0, x1, y1 = W, H, 0, 0
    found = False
    for el in board["elements"]:
        if el.get("type") != "chip" or not el.get("in"):
            continue
        a = _sortable(el["in"].get("t"), times)
        b = _sortable(el["out"].get("t"), times) if el.get("out") else None
        if b is not None and fade:
            # A caption does not stop existing at `out.t`; it fades. `fade` is
            # the share of that fade over which it is still legible enough to
            # matter — 0.65 means "until it drops to about a third opacity".
            # Left at 0 for zoom headroom, which must not pay for a word that
            # is on its way out.
            b += float(el["out"].get("dur", 0.0) or 0.0) * fade
        if a > at_t or (b is not None and b < at_t):
            continue
        cx, cy = el.get("at", [W // 2, H // 2])[:2]
        size = float(el.get("size", 60))
        hw = (len(str(el.get("text", ""))) * size * 0.60) / 2 + 30
        hh = _half(size)
        x0, y0 = min(x0, cx - hw), min(y0, cy - hh)
        x1, y1 = max(x1, cx + hw), max(y1, cy + hh)
        found = True
    return (x0, y0, x1, y1) if found else None


def _zoom_headroom(board, bid, at, W, H, margin=0.97, extra=None):
    """How far this particular beat can be pushed before it loses a word.

    A global zoom cap is the wrong instrument. Some beats are a lone picture
    with a two-word caption and can take a hard push; others carry a caption
    like "NOT TO LOOK BACK" sitting near the frame edge and cannot take any.
    Capping everything to suit the tightest beat throws away the motion the
    loose ones were happy to give — measured, a flat 1.18 cap cost the film a
    fifth of its mean. So each beat is asked what it can afford.

    It asks about the *readable* box, not everything the beat drew. A staged
    setting is wider than the frame by design, and counted here it made every
    scene answer "no headroom at all": the cap came out below 1.0 and was
    floored to it, so every beat that stood someone in a place was pinned at
    zoom 1.0 — with the board only `OVER` larger than the frame, that is a
    lens with almost nowhere to pan. Cropping the edge off a landscape is not
    losing a word; it is what a landscape is for.
    """
    box = _beat_bbox(board, bid, W, H, readable=True)
    if extra:
        box = extra if not box else (min(box[0], extra[0]), min(box[1], extra[1]),
                                     max(box[2], extra[2]), max(box[3], extra[3]))
    if not box:
        return 1.30
    cx, cy = at
    dx = max(cx - box[0], box[2] - cx, 1.0)
    dy = max(cy - box[1], box[3] - cy, 1.0)
    return max(1.0, min((W / 2) / dx, (H / 2) / dy) * margin)


#: How hard each tier leans off centre, and how far it pushes in.
#:
#: The spread across tiers matters more than any single value. Measured
#: against the reference film, a board whose tiers were all set high produced
#: a *median* camera jump of 209px where the reference's was 57px — with a
#: similar maximum. The reference is heavily skewed: mostly tiny adjustments,
#: punctuated by rare real travel. A uniform mid-size move on every shot has
#: no rest in it and no punctuation, and a viewer reads that constant churn as
#: the camera shaking rather than as it moving.
#:
#: So `limited` — the commonest tier — must stay genuinely small. The budget
#: belongs to `full` and `sakuga`, which are rare by construction.
_TIER_CAMERA = {
    "limited": {"lean": 0.15, "base": 1.10, "hold": 0.70},
    "full":    {"lean": 0.52, "base": 1.18, "hold": 0.60},
    "sakuga":  {"lean": 0.72, "base": 1.24, "hold": 0.75},
}


def _frame_camera(at, box, zoom, W, H):
    """Pull a camera aim back until the beat it is aiming at is fully framed.

    This is what makes a hard lean safe. The old lean was 0.18 partly because
    translation is the thing that crops a word off the edge — but the answer
    to that is to *measure* it, not to refuse to move. At zoom `z` the lens
    sees a window `W/z` by `H/z` in design units; the beat has to fit inside
    it, so the aim is clamped to the range that keeps it there.

    A beat larger than the window cannot be framed at all, and is centred on
    instead — the same thing a camera operator would do.
    """
    if not box:
        return at
    ax, ay = at
    hw, hh = (W / max(zoom, 1e-6)) / 2.0, (H / max(zoom, 1e-6)) / 2.0
    for i, (lo, hi, half) in enumerate(((box[0], box[2], hw),
                                        (box[1], box[3], hh))):
        if hi - lo >= half * 2:
            v = (lo + hi) / 2.0
        else:
            v = min(max((ax, ay)[i], hi - half), lo + half)
        if i == 0:
            ax = v
        else:
            ay = v
    return [int(ax), int(ay)]

#: Idle loop given to a picture the camera has parked on, so the image breathes
#: instead of becoming a frozen photograph. Amplitudes sit in the range
#: visual-style.md gives for `float`, and the period is varied per element so a
#: board full of held art does not pulse in unison.
#: A parked camera is not a still frame.
#:
#: When the camera stops, the artwork has to keep breathing or the shot reads
#: as a slideshow — this is the whole trick limited animation runs on, and the
#: reference film does it on roughly a quarter of its elements: a slow endless
#: drift of ±11..26px in x and ±6..14px in y with a 2.8% scale pulse, over
#: periods of 8-12 seconds. Long enough that nobody can point at it, large
#: enough that the frame is never dead.
#:
#: Amplitudes are a fraction of the element's own size, so a hillside drifts
#: further than a lantern and the parallax between them reads as depth.
SWAY_X = 0.030
SWAY_Y = 0.017
SWAY_SCALE = 0.028
SWAY_PERIOD = (7.5, 12.5)
SWAY_RAMP = 1.3

#: How small a second setting becomes when it is sent behind the first, and
#: where its centre lands within the held ground's own box. Two places at the
#: same scale is two horizons; distance is what makes the pair legible.
DISTANCE_SCALE = 0.46
DISTANCE_LIFT = 0.16

#: Breathing room, in design units, required between two things that are not
#: part of the same beat.
OVERLAP_PAD = 26.0

#: Where a hull sits within its water's band. Measured from the rendered
#: frame rather than guessed: the `sea` drawing lays its first wave rule at
#: 10% and its last at 96%, so a hull seated at 0.34 sits on the topmost line
#: and reads as hovering above the water. Seated past halfway it sits *in* the
#: wave field, with water both in front of and behind it.
WATERLINE = 0.55

#: Two drawings at materially different depths cannot collide, whatever their
#: boxes say. A distant boat passing behind a figure on a hill is not an
#: overlap, it is a composition — and treating it as one made the compiler
#: retire the protagonist to make room for a trawler on the horizon.
DEPTH_APART = 0.2

#: A drawing may be reduced to this fraction of its staged size to fit, and no
#: further. Below it a boat stops being a boat. `MIN_ART` is the absolute
#: floor in design units, which matters because a drawing that has already
#: been sent to distance is measured against its *receded* size — 0.46 x 0.60
#: is 28% of what the artist drew, and at that scale nothing is legible.
SHRINK_FLOOR = 0.60
MIN_ART = (110.0, 72.0)


def _boxes_hit(a, b, pad=0.0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _add_sway(board, bid, W, H, strength=1.0):
    """Give every piece of a beat a slow, endless drift.

    Applied wherever the camera has been parked, which is what stops a held
    shot reading as a still. Scenery is included on purpose: it is the largest
    thing in the frame and the one whose stillness is most obvious.
    """
    n = 0
    for el in board["elements"]:
        eid = str(el.get("id") or "")
        if eid != bid and not eid.startswith(bid + "_"):
            continue
        if el.get("type") not in ("art", "card"):
            continue
        if el.get("sway"):
            continue
        span = float(el.get("w") or el.get("fit", [0, 0])[0]
                     or el.get("size") or W * 0.25)
        seed = sum(ord(c) for c in eid)
        el["sway"] = {
            "x": round(min(span * SWAY_X, W * 0.022) * strength, 1),
            "y": round(min(span * SWAY_Y, H * 0.020) * strength, 1),
            "scale": round(SWAY_SCALE * strength, 4),
            "period": round(SWAY_PERIOD[0]
                            + (seed % 100) / 100.0
                            * (SWAY_PERIOD[1] - SWAY_PERIOD[0]), 2),
            "ramp": SWAY_RAMP,
        }
        n += 1
    return n


def _beat_names(board, bid):
    """The set of drawings a beat put on the board."""
    out = set()
    for el in board["elements"]:
        eid = str(el.get("id") or "")
        if el.get("type") == "art" and el.get("name") \
                and (eid == bid or eid.startswith(bid + "_")):
            out.add(el["name"])
    return out


def apply_motion_plan(board, mp, W, H, times=None):
    """Re-spend the camera budget according to a motion plan.

    The compiler's default is one move per beat, all the same size. That is
    even, and evenness is the thing limited animation exists to avoid: a move
    on every beat is a move that means nothing on any of them.

    This throws that away and spends the budget where the plan says. Held beats
    lose their move entirely and get a sway instead, so the camera genuinely
    parks and the *picture* carries the shot. What is saved there is handed to
    the few shots that are supposed to be loud.
    """
    shots = {s.get("beat") or s.get("id"): s for s in (mp.get("shots") or [])}
    if not shots:
        return ["motion plan carried no shots — the camera was left as compiled"]

    notes, kept, prev = [], [], None
    _times = times or {}
    dropped = 0
    swayed = 0
    reused = 0
    last_names = set()
    panned = set()
    for mv in board["camera"]["moves"]:
        bid = mv.get("_beat")
        shot = shots.get(bid) if bid else None
        if shot is None:
            kept.append(mv)
            prev = mv
            continue

        tier = shot.get("tier") or "limited"
        dur = float(shot.get("duration") or 0.0)

        if tier == "impact" and bid not in panned:
            # An impact used to spend its weight on a camera *shake*. It does
            # not any more, at any tier, for any subject: a shaken camera is
            # the single defect viewers name most often, and gating it on
            # "something actually strikes" was not enough — the remaining
            # legitimate shakes still read as a fault rather than as force.
            #
            # The weight is spent on a slow pan instead. It is the same
            # emphasis, made of travel rather than vibration: the lens leans
            # further off centre than any other tier and takes longer doing
            # it, so the beat still lands hardest without the frame ever
            # snapping. `SLOW_PAN_EASE` is what keeps it reading as weight.
            panned.add(bid)
            x, y = mv.get("_xy") or [W // 2, H // 2]
            at = [int(W / 2 + (x - W / 2) * SLOW_PAN_LEAN),
                  int(H / 2 + (y - H / 2) * SLOW_PAN_LEAN)]
            _chips = _live_chip_box(board, _sortable(mv.get("t"), _times),
                                    _times, W, H)
            mv["zoom"] = round(max(1.0, min(
                CAM_ZOOM_BASE + float(shot.get("amount") or 0.06),
                _zoom_headroom(board, bid, at, W, H, extra=_chips))), 3)
            _bb = _beat_bbox(board, bid, W, H, readable=True)
            if _chips:
                _bb = _chips if not _bb else (
                    min(_bb[0], _chips[0]), min(_bb[1], _chips[1]),
                    max(_bb[2], _chips[2]), max(_bb[3], _chips[3]))
            mv["at"] = _frame_camera(at, _bb, mv["zoom"], W, H)
            mv["ease"] = SLOW_PAN_EASE
            mv["dur"] = round(max(dur * 0.9, 1.6), 2)
            mv["hold"] = round(max(dur * 0.25, 0.4), 2)
            kept.append(mv)
            prev = mv
            continue

        if tier == "hold":
            # No move. The camera stays exactly where the last one left it and
            # simply waits, which is what produces a hold long enough to read
            # as a decision rather than a gap between two moves.
            if prev is not None:
                prev["hold"] = round(min(float(prev.get("hold", 0.5))
                                         + max(dur * 0.55, 0.3), 3.2), 2)
            dropped += 1
            swayed += _add_sway(board, bid, W, H)
            continue

        # Nothing new to look at, so there is nothing to look *at*. A beat
        # that redraws the same things as the beat before it has given the
        # camera no reason to move, and moving anyway is what turns a film
        # into a series of nudges — the churn that gets reported as shake.
        # The camera parks and the artwork drifts instead, which is how a
        # limited-animation film keeps a repeated setup alive.
        names = _beat_names(board, bid)
        if names and names == last_names:
            if prev is not None:
                prev["hold"] = round(min(float(prev.get("hold", 0.5))
                                         + max(dur * 0.6, 0.4), 3.6), 2)
            dropped += 1
            reused += 1
            swayed += _add_sway(board, bid, W, H, strength=1.25)
            continue
        last_names = names or last_names

        spec = _TIER_CAMERA.get(tier, _TIER_CAMERA["limited"])
        x, y = mv.get("_xy") or [W // 2, H // 2]
        amt = float(shot.get("amount") or 0.06)
        at = [int(W / 2 + (x - W / 2) * spec["lean"]),
              int(H / 2 + (y - H / 2) * spec["lean"])]
        mv["at"] = at
        # Each beat is pushed as hard as its own composition allows and no
        # harder. A flat cap either crops the tight beats or starves the loose
        # ones; measured on a 37-beat board, a 1.32 cap turned "KESTREL" into
        # "ESTREL" across a dozen shots, and dropping it to a safe-for-all
        # 1.18 cost a fifth of the film's motion.
        # Held captions count too: a chip left standing by an earlier beat is
        # still on screen and still has to be readable.
        _chips = _live_chip_box(board, _sortable(mv.get("t"), _times), _times,
                                W, H)
        room = _zoom_headroom(board, bid, at, W, H, extra=_chips)
        mv["zoom"] = round(max(1.0, min(spec["base"] + amt, room)), 3)
        # Now that the zoom is known, pull the aim back until the beat is
        # actually inside the frame. Leaning and then checking is what lets
        # the lean be large: the aim is only ever reduced, never faked.
        _bb = _beat_bbox(board, bid, W, H, readable=True)
        if _chips:
            _bb = _chips if not _bb else (
                min(_bb[0], _chips[0]), min(_bb[1], _chips[1]),
                max(_bb[2], _chips[2]), max(_bb[3], _chips[3]))
        mv["at"] = _frame_camera(at, _bb, mv["zoom"], W, H)
        mv["hold"] = spec["hold"]
        kept.append(mv)
        prev = mv

    board["camera"]["moves"] = kept

    # Anything the camera has parked on has to be alive on its own. This is the
    # cheapest motion in the film and the reason a hold is not a stall.
    # Transition budget. The compiler gives almost every element a `stamp` or
    # `fly` entrance and a matching exit; measured on a 37-beat board that is
    # 108 transitions worth 58 s of animation inside a 102 s film. Fifty-seven
    # per cent of the runtime is the collage assembling itself, which is why
    # the undirected cut reads as one long even shimmer no matter what the
    # camera does. On a quiet beat the pieces should simply be *there*, so
    # their arrivals become short fades and the beat plays as one composed
    # picture instead of a queue of entrances.
    #
    # `float` is the other half. Every element carries an idle breath, pushed
    # as high as 1.5 by the variety pass. A parked camera keeps a modest
    # breath, because that drift is the only thing keeping a held drawing
    # alive; a beat already moving under a push gives most of it up, since the
    # lens is supplying the motion.
    # A budget is spent, not merely cut. Damping the quiet beats alone drops
    # the whole film below the style's own "it moves at all" floor — measured
    # 1.444 against a required 1.5 — so everything saved on the held beats is
    # handed to the loud ones. Quiet beats give up their entrances and most of
    # their breath; loud beats keep their stamps and get a livelier one. That
    # is the entire trade limited animation is built on.
    # `float` is a deliberately weak lever and is set for intent, not effect.
    # Doubling every value here moved the finished film's mean motion from
    # 1.280 to 1.284, because `Element.transformed` quantises scale, rotation
    # and opacity before caching, and an idle drift whose whole sweep is a
    # third of a degree lands in the same bucket frame after frame. What
    # actually carries motion in this style is the camera and the element
    # entrances; the breath is what stops a held beat reading as a flat PNG.
    QUIET = ("hold", "limited", "impact")
    breath = {"hold": 0.80, "limited": 0.55, "impact": 0.65,
              "full": 1.40, "sakuga": 1.60}
    softened = damped = 0
    for el in board["elements"]:
        eid = el.get("id") or ""
        # Chips, boxes and labels are named after the beat they annotate
        # (`b7_kw0`), so a beat's supporting pieces settle with their picture
        # instead of stamping in one at a time over a shot meant to be quiet.
        shot = shots.get(eid) or shots.get(eid.split("_")[0])
        tier = shot.get("tier") if shot else None
        if tier not in breath:
            continue
        if tier in QUIET:
            for key in ("in", "out"):
                t = el.get(key)
                if isinstance(t, dict) and t.get("anim") in ("stamp", "fly"):
                    el[key] = {k: v for k, v in t.items() if k in ("t", "delay")}
                    el[key]["anim"] = "fade"
                    el[key]["dur"] = 0.32 if key == "in" else 0.30
                    softened += 1
        el["float"] = round(min(float(el.get("float", 1.0)), 1.5)
                            * breath[tier], 3)
        damped += 1

    notes.append(("fyi",
                  "motion plan applied: %d beat(s) gave up their camera move "
                  "(%d because nothing on screen had changed) and %d element(s)"
                  " were given a slow drift instead, %d move(s) kept and "
                  "re-weighted, %d entrance/exit(s) on quiet beats softened to "
                  "fades, %d element(s) had their idle breath damped."
                  % (dropped, reused, swayed, len(kept), softened, damped)))
    return notes


def _box(el):
    """(x0, y0, x1, y1) for an element that carries a `fit`."""
    cx, cy = el.get("at", [0, 0])[:2]
    w, h = (el.get("fit") or [0, 0])[:2]
    return cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0


def _life_window(el, times):
    """When the element is *scheduled*, ignoring how long it takes to fade.

    The counterpart to `_live_window`. Everything that asks "is this on
    screen with that?" wants the visible window, fade included; but the
    flicker check asks "does this have time to play its own transitions?",
    and adding the fade to the life it is measuring against makes every
    element look long enough by exactly the amount in question.
    """
    a = _sortable(el["in"].get("t"), times) if el.get("in") else 0.0
    b = _sortable(el["out"].get("t"), times) if el.get("out") else 1e9
    return a, b


def _live_window(el, times):
    """When the element is **on screen**, which is not when it is "live".

    An element does not vanish at `out.t`: the renderer keeps drawing it for
    the whole of `out.dur` while it fades. Measuring only `in.t..out.t` makes
    every hand-over between beats invisible to the geometry passes — the
    outgoing drawing and the incoming one are believed never to coexist, so
    nothing separates them, and for the third of a second the fade lasts they
    are both solid enough to read as two objects on top of each other. That
    is the "last scene overlaid on the new scene" defect: it survived every
    fix aimed at placement, because the placement was never the problem.
    """
    a = _sortable(el["in"].get("t"), times) if el.get("in") else 0.0
    b = _sortable(el["out"].get("t"), times) if el.get("out") else 1e9
    if el.get("out") and b < 1e8:
        b += float(el["out"].get("dur", 0.0) or 0.0)
    return a, b


def _overlaps_in_time(a, b, slack=0.25):
    return a[0] < b[1] - slack and b[0] < a[1] - slack


def _group_of(board, bid):
    return [e for e in board["elements"]
            if str(e.get("id") or "") == bid
            or str(e.get("id") or "").startswith(bid + "_")]


def _hold_ground_under_actors(board, times, notes):
    """A ground may not leave while someone is still standing on it.

    The "a person needs land" rule fixes *casting* — it makes sure a water act
    has land in it. It says nothing about **lifetimes**, and that is a second,
    separate way to end up with a figure on the open sea: on the validation
    film the hill exited at `l3+0.3` while the woman standing on it stayed to
    `l4-0.3`, and for that second and a half she stood on the water with the
    hill already gone.

    The hill is what should change, not the woman: she is still the subject of
    the narration, so the ground she is on is still needed. Its departure is
    deferred to hers.
    """
    grounds = [g for g in board["elements"]
               if g.get("type") == "art" and g.get("fit") and g.get("in")
               and g.get("name") in staging.GROUND
               and g.get("name") not in staging.WATER]
    held = 0
    for el in board["elements"]:
        if el.get("type") != "art" or el.get("name") not in staging.PERSON:
            continue
        if not el.get("fit") or not el.get("in") or not el.get("out"):
            continue
        start, end = _live_window(el, times)
        base, cx = _box(el)[3], el["at"][0]
        host, gap = None, None
        for g in grounds:
            gs, ge = _live_window(g, times)
            if gs > start + 0.05 or ge <= start + 0.05:
                continue  # not underfoot when she arrives
            gb = _box(g)
            if not (gb[0] <= cx <= gb[2]) or gb[3] < base - 8.0:
                continue
            # The ground she is *on* is the one whose surface is nearest under
            # her feet. Choosing among only the early-leaving ones instead
            # matched a figure to a hill from two acts earlier and dragged it
            # forward through the whole film.
            d = abs(gb[3] - base)
            if gap is None or d < gap:
                host, gap = g, d
        if host is None or _live_window(host, times)[1] >= end - 0.05:
            continue
        host["out"] = dict(el["out"])
        held += 1
    if held and notes is not None:
        notes.append(("fyi",
                      "%d ground(s) were leaving while someone was still "
                      "standing on them and were held." % held))
    return held


def _recede_second_ground(board, times, W, H, notes):
    """Two places may never share the frame at the same size.

    A beat can legitimately need a second setting — the story is on a hilltop
    and looks *out to sea* — but the compiler was drawing both as full-bleed
    grounds at the same scale, centred on the same point. The result was a
    seascape painted across a hillside: two horizons, two ground lines, and a
    trawler apparently sailing over a mountain.

    The fix is the one a layout artist would use. The newcomer does not
    replace the held setting and does not compete with it: it **goes to
    distance**. Scaled down, lifted to sit near the held ground's peak, and
    pushed behind it in z, so the hill occludes its middle and the water reads
    as being far beyond — which is what the narration actually said.

    Everything the beat staged on that ground travels with it. A boat is only
    "far out" if it shrinks along with the sea it is floating on.
    """
    grounds = [e for e in board["elements"]
               if e.get("type") == "art" and e.get("name") in staging.GROUND
               and e.get("name") not in staging.FIXTURE
               and e.get("fit") and e.get("in")]
    grounds.sort(key=lambda e: _live_window(e, times)[0])
    moved = 0
    for i, later in enumerate(grounds):
        lw = _live_window(later, times)
        held = None
        for earlier in grounds[:i]:
            ew = _live_window(earlier, times)
            if _overlaps_in_time(ew, lw) and _boxes_hit(_box(earlier),
                                                       _box(later)):
                held = earlier
                break
        if held is None:
            continue
        bid = str(later.get("id") or "").split("_")[0]
        if bid.startswith("sc"):
            continue  # an act's own setting is never the one that recedes
        # Nor is the ground somebody is standing on. Distance is for the thing
        # being looked *at*; the moment a person is on it, it is the thing
        # being looked *from*, and shrinking it to 46% shrinks the subject of
        # the shot along with it.
        if any(e.get("name") in staging.PERSON
               for e in _group_of(board, bid)):
            continue
        hx0, hy0, hx1, hy1 = _box(held)
        # Only the artwork travels. A caption is not part of the scenery: it
        # belongs to the viewer, not to the world, and sweeping it into the
        # group shrank "FAR OUT" and filed it behind the hill, where the
        # occlusion rules promptly hid it.
        group = [e for e in _group_of(board, bid) if e.get("type") == "art"]
        if not group:
            continue
        gx0 = min(_box(e)[0] for e in group)
        gy0 = min(_box(e)[1] for e in group)
        gx1 = max(_box(e)[2] for e in group)
        gy1 = max(_box(e)[3] for e in group)
        gcx, gcy = (gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0
        s = DISTANCE_SCALE
        # Sit the receded group around the held ground's shoulder: far enough
        # up that it reads as beyond, not so far that it floats in empty sky.
        target_cy = hy0 + (hy1 - hy0) * DISTANCE_LIFT
        base_z = int(held.get("z", 10))
        for j, e in enumerate(sorted(group, key=lambda x: x.get("z", 0))):
            ex, ey = e.get("at", [gcx, gcy])[:2]
            e["at"] = [round(gcx + (ex - gcx) * s, 1),
                       round(target_cy + (ey - gcy) * s, 1)]
            if e.get("fit"):
                e["fit"] = [round(e["fit"][0] * s, 1),
                            round(e["fit"][1] * s, 1)]
            if isinstance(e.get("size"), (int, float)):
                e["size"] = round(e["size"] * s)
            e["z"] = base_z - len(group) + j
            e["parallax"] = round(min(0.9, float(e.get("parallax", 0.5))
                                      + 0.25), 2)
            moved += 1
        notes.append(("fyi",
                      "%s put a second setting (%s) on screen while %s was "
                      "still up, so it was sent to distance behind it at %d%% "
                      "— two places at the same scale is two horizons."
                      % (bid, later.get("name"), held.get("name"), s * 100)))
    return moved


def _separate_live_overlaps(board, times, W, H, notes):
    """Nothing that matters may be drawn on top of anything else that matters.

    Placement is decided per beat, so it cannot see what an *earlier* beat left
    standing. Measured on a 12-beat film, a trawler was handed x=1036.8 — the
    exact centre a figure had been holding for two lines — and drew straight
    over her. The stage grammar was right in isolation and wrong on the board.

    Subjects are pushed apart horizontally, away from each other, and the
    later arrival yields because the earlier one has already been established.
    Scenery is exempt: a ground is *meant* to have things standing on it.

    Two exemptions here were originally too generous, and each left a merge on
    screen that a viewer reported:

    * *A beat's own cast is composed on purpose* — true of a flame on its
      lantern or a chair beside a figure, and false of two independent
      subjects. One beat drew a trawler at x=[863,1128] and a second boat at
      x=[1033,1187], and the film showed a blue prow growing out of an orange
      hull. Same-beat pairs are compared when **both are actors**; props and
      diagrams keep the exemption, so attachments still sit where they were put.
    * *Different depths already read right* — true when one of the pair is
      scenery, because a hill behind a person is the whole point. Between two
      actors it is not: a figure on the near plane and a trawler on the far one
      shared x=[936,1128] and y=[346,418], and her head was drawn inside the
      hull. z-order cannot rescue two things of similar size.
    """
    def _is_actor(e):
        return staging.role_of(e.get("name")) == "actor"

    subs = [e for e in board["elements"]
            if e.get("type") == "art" and e.get("fit") and e.get("in")
            and e.get("name") not in staging.GROUND]
    subs.sort(key=lambda e: _live_window(e, times)[0])

    def _pairs():
        for i, late in enumerate(subs):
            for early in subs[:i]:
                both = _is_actor(early) and _is_actor(late)
                if not both and str(early.get("id") or "").split("_")[0] == \
                        str(late.get("id") or "").split("_")[0]:
                    continue  # one beat's own cast is composed on purpose
                if not _overlaps_in_time(_live_window(early, times),
                                         _live_window(late, times)):
                    continue
                if not both and abs(float(early.get("parallax", 0.5))
                                    - float(late.get("parallax", 0.5))) \
                        >= DEPTH_APART:
                    continue  # scenery behind a subject: z-order reads right
                yield early, late

    fixed = stuck = 0
    for _round in range(5):
        # One sweep is not enough: separating a pair can push one of them into
        # a third drawing, and the single-pass version measurably undid its own
        # work — a trawler moved clear of a figure was shoved back over her by
        # the next comparison. Sweep until nothing moves.
        for _ in range(8):
            moves = 0
            for early, late in _pairs():
                a, b = _box(early), _box(late)
                if not _boxes_hit(a, b, pad=OVERLAP_PAD):
                    continue
                need = (min(a[2], b[2]) - max(a[0], b[0])) / 2.0 + OVERLAP_PAD
                sign = 1.0 if (b[0] + b[2]) >= (a[0] + a[2]) else -1.0
                half = (b[2] - b[0]) / 2.0
                nx = late["at"][0] + sign * need
                span = _ground_span(board, late, times)
                if span and late.get("name") not in staging.GROUND:
                    lo, hi = span[0] + half, span[1] - half
                    nx = (span[0] + span[1]) / 2.0 if lo > hi \
                        else max(lo, min(hi, nx))
                else:
                    nx = max(half * 0.35, min(W - half * 0.35, nx))
                if abs(nx - late["at"][0]) < 1.0:
                    continue
                late["at"] = [round(nx, 1), late["at"][1]]
                moves += 1
            fixed += moves
            if not moves:
                break

        # Anything still colliding has run out of horizontal room, which
        # happens in a crowded frame. Depth is the way out: the later arrival
        # shrinks and lifts so it reads as standing further back rather than
        # in the way. Its z is left alone — a boat that stops overlapping a
        # figure but starts floating above the sea it rides has not been fixed.
        hit = 0
        for early, late in _pairs():
            if not _boxes_hit(_box(early), _box(late), pad=OVERLAP_PAD * 0.5):
                continue
            # Shrink, never lift. Almost everything in this style is seated on
            # something — a figure stands on the ground line, a hull sits on
            # the waterline — so raising a drawing to dodge a collision does
            # not send it upstage, it sends it into the sky. Measured: the
            # lifting version parked a figure at y=68, hovering over a hill.
            #
            # Shrinking has to have a floor for the same reason. Compounded
            # over five rounds an unbounded 0.78 took a trawler to 46x20 px —
            # technically not overlapping anything, and no longer a drawing of
            # a boat. Past the floor the pair is handed to the retirement rule
            # below instead.
            orig = late.setdefault("_fit0", list(late["fit"]))
            if late["fit"][0] <= orig[0] * SHRINK_FLOOR \
                    or late["fit"][0] * 0.78 < MIN_ART[0] \
                    or late["fit"][1] * 0.78 < MIN_ART[1]:
                continue
            # A drawing made of words is the exception: shrinking it does not
            # cost detail, it costs the whole point of the drawing. A chart
            # arriving on the last line is always the latest element on the
            # board and therefore always the one asked to yield, which took a
            # timeline that had just been enlarged to be readable straight
            # back down to 60% of it. Move it, or retire what it hit.
            if late.get("name") in TEXT_ART:
                nw, _nh = staging.natural_box(late["name"])
                if late["fit"][0] * 0.78 < nw * LEGIBLE_SCALE:
                    continue
            s = 0.78
            late["fit"] = [round(late["fit"][0] * s, 1),
                           round(late["fit"][1] * s, 1)]
            if isinstance(late.get("size"), (int, float)):
                late["size"] = round(late["size"] * s)
            hit += 1
        stuck += hit
        _reseat_vessels(board, times, None)
        if not hit:
            break

    # Still touching after all that means the frame genuinely has no room for
    # both. One of them has to go, and it is the older one: its beat is over,
    # the new arrival is what the narration is talking about now. This is the
    # same principle as clearing a scene, applied to a single drawing.
    cut = 0
    for early, late in _pairs():
        if not _boxes_hit(_box(early), _box(late), pad=2.0):
            continue
        arrives = late["in"].get("t")
        cur = early.get("out")
        if cur and _sortable(cur.get("t"), times) <= _live_window(late,
                                                                 times)[0]:
            continue
        early["out"] = {"t": arrives, "dur": 0.4}
        cut += 1
    for e in subs:
        e.pop("_fit0", None)
    if (fixed or stuck or cut) and notes is not None:
        notes.append(("fyi",
                      "%d drawing(s) were overlapping something already on "
                      "screen and were moved clear%s%s."
                      % (fixed,
                         "; %d were drawn smaller to fit" % stuck
                         if stuck else "",
                         "; %d older one(s) left early because the frame had "
                         "no room for both" % cut if cut else "")))
    return fixed + stuck + cut
    if fixed or stuck:
        notes.append(("fyi",
                      "%d drawing(s) were overlapping something already on "
                      "screen and were moved clear%s."
                      % (fixed,
                         "; %d had no room and were sent upstage instead"
                         % stuck if stuck else "")))
    return fixed + stuck


def _drop_flickers(board, times, notes):
    """Nothing appears for less time than it takes to appear.

    Retiring the older of two colliding drawings sets its `out` to the moment
    the newcomer lands, and when the two are only a beat-substep apart that
    leaves a lifetime shorter than the element's own transitions. On the
    validation film a trawler was given 0.10 s of life against a 0.56 s
    fly-in and a 0.40 s fade-out.

    The renderer does not clamp that. It simply evaluates the entrance at the
    fraction of it that elapsed, so the drawing is frozen part-way through:
    still translucent, still offset, its cut-out border not yet opaque. Blended
    against a dark field it becomes a colourless smear — which was reported as
    "the ship is grey", a colour bug with no colour in its cause. Both the
    trawler's ink and the palette were correct.

    Transitions are compressed to fit first, because a brief glimpse is
    sometimes the intent. Below what a glimpse can even be, the drawing is
    dropped: it was already competing for a frame it lost.
    """
    floor, dropped, tightened = 0.12, [], 0
    for e in list(board["elements"]):
        if e.get("type") != "art" or not e.get("in"):
            continue
        out = e.get("out") or {}
        if not out.get("t"):
            continue
        a, b = _life_window(e, times)
        if b >= 1e8:
            continue
        life = b - a
        need = float(e["in"].get("dur", 0.0)) + float(out.get("dur", 0.0))
        if life >= need:
            continue
        if life >= floor * 2:
            share = life / need if need else 1.0
            e["in"]["dur"] = round(max(floor, float(
                e["in"].get("dur", 0.0)) * share), 2)
            out["dur"] = round(max(floor, float(out.get("dur", 0.0))
                                   * share), 2)
            tightened += 1
        else:
            board["elements"].remove(e)
            dropped.append(str(e.get("id") or e.get("name")))
    if tightened:
        notes.append(("fyi", "%d drawing(s) had their entrance shortened to "
                             "fit the time they are on screen." % tightened))
    if dropped:
        notes.append(("fyi", "dropped %d drawing(s) that were retired before "
                             "they finished arriving: %s"
                      % (len(dropped), ", ".join(dropped))))
    return len(dropped)


def _seat_on_ground(board, times, notes):
    """A drawing standing on a hillside stands on its *surface*.

    `_ground_span` already knows a ground is a dome and not a rectangle, and
    it uses that to decide how far sideways something may be pushed. But it
    only ever constrained **x**. Separation moves an element along the slope
    and nothing then corrects its **y**, so a lantern shunted from the summit
    out to x=310 kept the height it had at the summit and hung 180 px above
    the hill in open sky — a defect that passes a bounding-box seating check,
    because the box of a dome includes all the empty air beside it.

    The surface height comes from `staging.surface_up`, which is measured off
    the real artwork, and `_ground_span` reads the same table — so the height
    something is seated at and the width it may be pushed to always agree.

    Vessels are excluded — they belong to the waterline, which
    `_reseat_vessels` owns — and so is lettered art, which has been lifted
    deliberately to stay readable. Attachments are excluded too: a flame
    stands on its lantern, not on the hill, and `_reanchor_attachments` puts
    it there afterwards.
    """
    grounds = [g for g in board["elements"]
               if g.get("type") == "art" and g.get("name") in staging.GROUND
               and g.get("fit") and g.get("in")]
    moved = 0
    for el in board["elements"]:
        if el.get("type") != "art" or not el.get("fit") or not el.get("in"):
            continue
        name = el.get("name")
        if name in staging.GROUND or name in staging.WATERBORNE \
                or name in TEXT_ART or name in staging.ATTACH:
            continue
        if staging.role_of(name) not in ("actor", "prop"):
            continue
        span = _ground_span(board, el, times)
        if not span:
            continue
        host = _ground_under(board, el, times)
        if host is None or host.get("name") in staging.WATER:
            continue
        gx0, gy0, gx1, gy1 = _box(host)
        half = max(1.0, (gx1 - gx0) / 2.0)
        h = max(1.0, gy1 - gy0)
        f = min(1.0, abs(el["at"][0] - (gx0 + gx1) / 2.0) / half)
        surface = gy1 - staging.surface_up(host.get("name"), f) * h
        base = el["at"][1] + el["fit"][1] / 2.0
        if abs(base - surface) < 6.0:
            continue
        el["at"] = [el["at"][0], round(surface - el["fit"][1] / 2.0, 1)]
        moved += 1
    if moved and notes is not None:
        notes.append(("info", "re-seated %d drawing(s) onto the surface of "
                              "the ground they stand on" % moved))
    return moved


def _land_drifts(board, times, notes):
    """A drawing that travels arrives somewhere it could have stood.

    A drift is what makes a figure *climb* rather than cut from the foot of
    the stairs to the top of them, and it is the whole answer to "show them
    walking from one place to another". But it is expressed as a delta, and
    every geometry pass in this file reads `at` — the place the element
    *starts*. Nothing has ever looked at where it ends up.

    So a figure seated correctly on the hill, given a 405 x -328 climb,
    finished with its centre 29 px **above the top of the board**: on screen
    it was a pair of legs sliding along the top edge for four seconds. It
    passed every check, because at `at` it was perfectly placed.

    The destination is therefore seated exactly as the start is — clamped
    into the frame, held inside the ground's span, and dropped onto the
    surface at the x it actually reaches — and the delta rewritten to match.
    Vessels keep their y, because a boat travels along its waterline and
    `_reseat_vessels` owns that height.
    """
    W, H = board.get("width", 1920), board.get("height", 1080)
    landed = 0
    for el in board["elements"]:
        drift = el.get("drift")
        if not drift or el.get("type") != "art" or not el.get("fit"):
            continue
        w, h = el["fit"]
        ex = el["at"][0] + float(drift.get("x", 0.0) or 0.0)
        ey = el["at"][1] + float(drift.get("y", 0.0) or 0.0)
        name = el.get("name")
        host = None
        if name not in staging.GROUND and name not in staging.WATERBORNE \
                and name not in TEXT_ART and name not in staging.ATTACH \
                and staging.role_of(name) in ("actor", "prop"):
            host = _ground_under(board, el, times)
            if host is not None and host.get("name") in staging.WATER:
                host = None
        if host is not None:
            gx0, _, gx1, gy1 = _box(host)
            ex = min(max(ex, gx0 + w / 2.0), gx1 - w / 2.0)
        ex = min(max(ex, w / 2.0 - w * 0.15), W - w / 2.0 + w * 0.15)
        if host is not None:
            gx0, gy0, gx1, gy1 = _box(host)
            half = max(1.0, (gx1 - gx0) / 2.0)
            f = min(1.0, abs(ex - (gx0 + gx1) / 2.0) / half)
            surface = gy1 - staging.surface_up(host.get("name"),
                                               f) * max(1.0, gy1 - gy0)
            ey = surface - h / 2.0
        elif name not in staging.WATERBORNE:
            ey = min(max(ey, h / 2.0), H - h / 2.0)
        else:
            ey = el["at"][1] + float(drift.get("y", 0.0) or 0.0)
            ey = min(max(ey, h / 2.0), H - h / 2.0)
        nx, ny = round(ex - el["at"][0], 2), round(ey - el["at"][1], 2)
        if abs(nx - float(drift.get("x", 0.0) or 0.0)) < 1.0 \
                and abs(ny - float(drift.get("y", 0.0) or 0.0)) < 1.0:
            continue
        drift["x"], drift["y"] = nx, ny
        landed += 1
    if landed and notes is not None:
        notes.append(("fyi",
                      "%d travelling drawing(s) were arriving off the frame "
                      "or off the ground and were landed" % landed))
    return landed


def _reanchor_attachments(board, times, notes):
    """A flame belongs at the wick, wherever the lantern ended up.

    `staging` already knows an attachment is drawn at an anchor on its host,
    but it can only apply that when both are cast into the *same* beat.
    A lantern lit across a beat boundary — the lantern established in one
    sub-beat, the flame added in the next — arrives as two independent
    elements, so the flame is placed as if it were scenery: seated on the
    ground, spanning the bottom third of the lantern, appearing to leak out
    of its foot rather than burn inside its glass.

    This runs last, after every pass that may have moved the host, and pins
    each stray attachment back onto whichever host is on screen with it.
    """
    fixed = 0
    for el in board["elements"]:
        name = el.get("name")
        if el.get("type") != "art" or name not in staging.ATTACH:
            continue
        if not el.get("fit") or not el.get("in"):
            continue
        win = _live_window(el, times)
        bid = str(el.get("id") or "").split("_")[0]
        host, best = None, None
        for h in board["elements"]:
            if h.get("type") != "art" or not h.get("fit") or not h.get("in"):
                continue
            if h.get("name") not in staging.ATTACH[name] or h is el:
                continue
            if not _overlaps_in_time(_live_window(h, times), win):
                continue
            same = str(h.get("id") or "").split("_")[0] == bid
            rank = (0 if same else 1, -(h["fit"][0] * h["fit"][1]))
            if best is None or rank < best:
                host, best = h, rank
        if host is None:
            continue
        dx, dy, scale = staging.ATTACH_ANCHOR.get(name, (0.0, -0.46, 0.42))
        hw, hh = host["fit"]
        want_h = hh * scale
        if el["fit"][1] > 1e-6:
            ratio = el["fit"][0] / el["fit"][1]
            el["fit"] = [round(want_h * ratio, 1), round(want_h, 1)]
            el["size"] = int(round(max(el["fit"])))
        cx = host["at"][0] + dx * hw
        cy = host["at"][1] + dy * hh
        # Timing is synced even when the position is already right, because
        # the second pass runs after hand-overs are staggered and the host's
        # schedule is what changed, not its position.
        if host.get("out"):
            el["out"] = dict(host["out"])
        elif el.get("out"):
            el.pop("out")
        if abs(cx - el["at"][0]) < 4.0 and abs(cy - el["at"][1]) < 4.0:
            continue
        el["at"] = [round(cx, 1), round(cy, 1)]
        el["z"] = max(el.get("z", 0), host.get("z", 0) + 1)
        el["parallax"] = host.get("parallax", el.get("parallax", 0.0))
        fixed += 1
    if fixed and notes is not None:
        notes.append(("info", "re-anchored %d attachment(s) onto the drawing "
                              "they belong to" % fixed))
    return fixed


def _clear_ground_arrivals(board, times, notes):
    """A ground may only carry the things that belong on it.

    Grounds are exempt from the overlap check on purpose: a hill is *meant* to
    have a figure standing on it, so comparing their boxes would flag every
    correctly composed frame. The exemption was written as "a ground never
    collides", which is one word too broad — it is only true of the drawings
    seated on that ground.

    Measured on the 12-beat board at t=42: a new act's hill spanning
    x=[250,1670] arrived at 41.85 straight over a trawler at x=[994,1570] that
    the previous act had put on open water and that ran on until 45.78. Both
    fully opaque, nothing dissolving, every check clean — and on screen a
    fishing boat was parked on a hillside for four seconds. Cutting the
    cross-fade stops two pictures blending; it does not stop the previous
    scene's cast being *left* on the new scene's ground.

    So an arriving ground hands over as well: anything that was already
    standing there when it arrived, and does not belong to it, leaves as it
    lands. Only non-grounds are retired — an earlier attempt that also retired
    the grounds a newcomer covered stranded a figure on open water, because a
    ground leaving takes the floor with it. Attachments are left alone and
    carried by `_reanchor_attachments`, so a flame follows its lantern out
    rather than being snuffed on its own.
    """
    grounds = [e for e in board["elements"]
               if e.get("type") == "art" and e.get("fit") and e.get("in")
               and e.get("name") in staging.GROUND
               and not str(e.get("id") or "").startswith("sc")]
    others = [e for e in board["elements"]
              if e.get("type") == "art" and e.get("fit") and e.get("in")
              and e.get("name") not in staging.GROUND
              and e.get("name") not in staging.ATTACH]
    cleared = 0
    for g in grounds:
        ga, gb = _live_window(g, times)
        gx0, gy0, gx1, gy1 = _box(g)
        gbeat = str(g.get("id") or "").split("_")[0]
        for e in others:
            if str(e.get("id") or "").split("_")[0] == gbeat:
                continue                    # this ground's own cast
            ea, eb = _live_window(e, times)
            if ea >= ga - 0.01 or eb <= ga + 0.01:
                continue                    # arrived later, or already gone
            ex0, ey0, ex1, ey1 = _box(e)
            if ex1 <= gx0 or ex0 >= gx1 or ey1 <= gy0 or ey0 >= gy1:
                continue                    # standing clear of it
            settled = ea + float((e.get("in") or {}).get("dur", 0.0) or 0.0)
            if ga - 0.15 - settled < 0.5:
                continue                    # too short a life to be worth it
            out = e.get("out") or {}
            if out.get("t") is not None and \
                    _sortable(out.get("t"), times) <= ga + 0.01:
                continue                    # already leaving
            # Gone *by* the time the ground lands, not fading out as it fades
            # in: retiring on the arrival itself simply trades a leftover for
            # a cross-fade, which is the defect one rule up.
            e["out"] = {"t": _shift_token(g["in"].get("t"), -0.15),
                        "dur": 0.15}
            cleared += 1
    if cleared and notes is not None:
        notes.append(("fyi",
                      "%d drawing(s) from an earlier beat were still standing "
                      "where a new ground landed and were retired as it "
                      "arrived." % cleared))
    return cleared


def _shift_token(tok, delta):
    """Move a symbolic time (`"l9+0.30"`) by `delta` seconds."""
    if not isinstance(tok, str):
        return round(float(tok) + delta, 2)
    m = re.match(r"^([A-Za-z0-9]+)([+-][\d.]+)?$", tok)
    if not m:
        return tok
    return "%s%+.2f" % (m.group(1), float(m.group(2) or 0.0) + delta)


def _stagger_handovers(board, times, notes):
    """A beat hands over to the next with a cut, not a dissolve.

    Every hand-over on the board is built the same way: the newcomer's `in.t`
    is set to exactly the outgoing drawing's `out.t`. That is a cross-fade —
    for the 0.3-0.5 s the fade lasts, both drawings are on screen, both solid
    enough to read, and if they occupy the same ground they read as two
    objects piled on top of each other. It is the "last scene overlaid on the
    new scene" defect, and no amount of moving things sideways fixes it,
    because the two are *supposed* to be in the same place — one is replacing
    the other.

    So the outgoing fade is tightened to a brief wipe and the newcomer is
    delayed to start when it finishes. The cost is ~0.15 s of arrival time;
    what it buys is that the frame only ever shows one of them.

    Only pairs whose boxes actually collide are staggered — two drawings at
    opposite ends of the frame may dissolve across each other freely, and
    that is what keeps the film from feeling like a slideshow.

    Grounds are included, and they are the most important case: an act change
    dissolves a whole setting through the next one, so for half a second the
    frame holds a hillside and the sea that replaces it at once, with the new
    act's boats already sailing through the old act's hill. A ground and the
    actors standing on it are never staggered against each other, because
    co-existing is not handing over — the trigger is specifically that one
    drawing's arrival lands inside another's fade.

    The two drawings can meet in either order, and both are the same defect.
    Usually the newcomer arrives as the old one leaves, and the fix is to cut
    the fade short and delay the arrival. But a new act's ground often starts
    fading *in* before the previous act's figure has begun to leave, and since
    that ground is drawn on a higher layer — it has to be, to cover the act it
    replaces — the hillside slides over the person. Nothing can be delayed
    there, because the arrival already began, so the departure is pulled
    forward instead: the figure is gone before the ground reaches it. That
    shift is capped, and refused outright if it would cut the drawing's life
    below half a second, because a beat that never plays is worse than a
    momentary overlap.
    """
    HANDOVER = 0.15
    art = [e for e in board["elements"]
           if e.get("type") == "art" and e.get("fit") and e.get("in")
           and e.get("name") not in staging.ATTACH]
    fixed = 0
    for a in art:
        out = a.get("out") or {}
        if not out.get("t"):
            continue
        for b in art:
            if b is a:
                continue
            a_out = _sortable(out.get("t"), times)
            a_gone = a_out + float(out.get("dur", 0.0) or 0.0)
            b_in = _sortable(b["in"].get("t"), times)
            b_here = b_in + float(b["in"].get("dur", 0.0) or 0.0)
            late = a_out - 0.01 <= b_in < a_gone - 0.01
            early = b_in < a_out < b_here - 0.01
            if not (late or early):
                continue
            # Two drawings of the *same* illustration are always a hand-over,
            # wherever they sit. Their boxes need not touch — a lantern at the
            # foot of the hill and the same lantern on the summit are at
            # opposite ends of the frame — but showing both at once reads as
            # two lanterns rather than one that was carried up.
            if a.get("name") != b.get("name") and not _boxes_hit(_box(a),
                                                                 _box(b)):
                continue
            out["dur"] = max(0.12, min(float(out.get("dur", 0.4) or 0.4),
                                       HANDOVER))
            if late:
                delay = (a_out + out["dur"]) - b_in
                if delay > 0.01:
                    b["in"]["t"] = _shift_token(b["in"].get("t"), delay)
            else:
                lead = (a_gone - b_in) + 0.05
                if lead > 0.01 and lead <= 0.7 and a_out - lead > _sortable(
                        a["in"].get("t"), times) + 0.5:
                    out["t"] = _shift_token(out.get("t"), -lead)
            fixed += 1

    # A third case, which neither of the above can see because nothing is
    # fading *out*: a new act's ground arrives on a layer above drawings that
    # are still mid-beat beneath it. For the half-second its fade lasts the
    # hillside is translucent and the previous act's boats sail through it.
    # There is no hand-over partner to stagger against — the ground simply
    # covers whatever is under it — so the fade itself is the defect, and it
    # is cut to a wipe. Only the ground's own arrival is touched: retiring
    # what it covers was tried first and is a false economy, because forcing
    # those drawings to fade out invents fresh cross-fades of exactly the kind
    # the two loops above exist to remove.
    grounds = [e for e in art if e.get("name") in staging.GROUND]
    for g in grounds:
        if float(g["in"].get("dur", 0.0) or 0.0) <= HANDOVER + 0.01:
            continue
        g_in = _sortable(g["in"].get("t"), times)
        beat_id = str(g.get("id") or "").split("_")[0]
        for e in art:
            if e is g or str(e.get("id") or "").split("_")[0] == beat_id:
                continue
            if e.get("z", 0) >= g.get("z", 0):
                continue
            lo, hi = _live_window(e, times)
            if not (lo <= g_in + 0.01 and hi > g_in + 0.05):
                continue
            if not _boxes_hit(_box(g), _box(e)):
                continue
            g["in"]["dur"] = HANDOVER
            fixed += 1
            break

        notes.append(("fyi",
                      "%d hand-over(s) were dissolving one drawing through "
                      "another in the same place and were cut instead"
                      % fixed))
    return fixed


def _reseat_vessels(board, times, notes):
    """A vessel sits on its water.

    Separation and upstaging move things vertically, and a boat is the one
    thing that cannot be moved vertically on its own: lift it clear of a
    figure and it is no longer floating, it is flying. Measured on this film,
    resolving a trawler-over-figure collision left the trawler 2 px above the
    top edge of the sea it was supposed to be sailing on.

    So vessels are re-seated last, after every other pass has had its say.
    Horizontal position — which is what separation actually cared about — is
    preserved; only the waterline is restored.
    """
    waters = [e for e in board["elements"]
              if e.get("type") == "art" and e.get("name") in staging.WATER
              and e.get("fit") and e.get("in")]
    seated = 0
    for el in board["elements"]:
        if el.get("type") != "art" or el.get("name") not in staging.WATERBORNE:
            continue
        if not el.get("fit") or not el.get("in"):
            continue
        win = _live_window(el, times)
        host = None
        for w in waters:
            if _overlaps_in_time(_live_window(w, times), win):
                wb = _box(w)
                if wb[0] <= el["at"][0] <= wb[2]:
                    host = w
                    break
        if host is None:
            continue
        wy0, wy1 = _box(host)[1], _box(host)[3]
        want_bottom = wy0 + (wy1 - wy0) * WATERLINE
        half_h = el["fit"][1] / 2.0
        ny = round(want_bottom - half_h, 1)
        if abs(ny - el["at"][1]) < 2.0:
            continue
        el["at"] = [el["at"][0], ny]
        el["z"] = max(int(el.get("z", 10)), int(host.get("z", 10)) + 1)
        seated += 1
    if seated and notes is not None:
        notes.append(("fyi",
                      "%d vessel(s) had drifted off their water and were "
                      "seated back on the waterline." % seated))
    _sink_behind_land(board, times, notes)
    return seated


def _sink_behind_land(board, times, notes):
    """Water further up the frame is water further away, so the land wins.

    Seating a vessel correctly is not enough on its own. On the closing beat
    of the validation film a boat was placed on the waterline at y=687 while
    the hill in the same shot had its base at y=905 — 218 px lower, and so
    unambiguously nearer the viewer — yet the boat carried the higher `z` and
    was drawn straight over the hillside. The staging was right twice and the
    frame still read as a boat sailing across a mountain.

    Height above the horizon *is* distance in this projection, so it decides
    the z-order too: anything floating higher than a ground's base line goes
    behind that ground.
    """
    grounds = [e for e in board["elements"]
               if e.get("type") == "art" and e.get("fit") and e.get("in")
               and e.get("name") in staging.GROUND
               and e.get("name") not in staging.WATER]
    sunk = 0
    for el in board["elements"]:
        if el.get("type") != "art" or el.get("name") not in staging.WATERBORNE:
            continue
        if not el.get("fit") or not el.get("in"):
            continue
        win, eb = _live_window(el, times), _box(el)
        for g in grounds:
            if not _overlaps_in_time(_live_window(g, times), win):
                continue
            gb = _box(g)
            if eb[0] >= gb[2] or gb[0] >= eb[2]:
                continue  # nowhere near it horizontally; nothing to resolve
            if eb[3] >= gb[3] - 4.0:
                continue  # at or below the land's base: genuinely in front
            if int(el.get("z", 0)) <= int(g.get("z", 0)):
                continue
            # Only the vessel moves. Its beat's other members are not on the
            # water and have no reason to follow it behind the hill — moving
            # the whole group once took a chart down with the boat.
            el["z"] = int(g.get("z", 0)) - 1
            sunk += 1
            break
    if sunk and notes is not None:
        notes.append(("fyi",
                      "%d vessel(s) were floating above a shoreline yet drawn "
                      "in front of it, and were put behind the land." % sunk))
    return sunk


#: Drawings that carry their own lettering. Everything else is a shape and
#: reads at any size; these stop meaning anything once the words go. Measured
#: on the validation film a `timeline` designed at 520x860 was drawn at
#: 173x286 — a third of scale — and its four labels were illegible smudges.
TEXT_ART = ("timeline", "region_map", "map")

#: The share of its designed width a lettered drawing must keep.
LEGIBLE_SCALE = 0.62

#: Clear space kept above a drawing that has been grown to be readable.
TOP_MARGIN = 28.0


def _keep_text_legible(board, times, W, H, notes):
    """A drawing made of words has a size below which it is decoration.

    Sizes are handed out by *role* — a diagram beside an actor is a prop, and
    a prop's allowance is small. That is right for a lantern and wrong for a
    chart, because shrinking a lantern loses nothing and shrinking a chart
    loses the only thing it was for.
    """
    grown = 0
    for el in board["elements"]:
        if el.get("type") != "art" or el.get("name") not in TEXT_ART:
            continue
        if not el.get("fit"):
            continue
        nw, nh = staging.natural_box(el["name"])
        want = nw * LEGIBLE_SCALE
        cur = float(el["fit"][0])
        if cur >= want - 1.0:
            continue
        cx, cy = el["at"][:2]
        bottom = cy + float(el["fit"][1]) / 2.0
        # Growing from the foot is right — the base is where the drawing was
        # placed against a ground line — but it means all the new height goes
        # *upward*, into space the camera may not be looking at. Board space
        # is not frame space: at the 1.15 zoom this beat holds, everything
        # above y=80 is outside the shot, and an earlier version put a date
        # label at y=39 and had it cropped off the top of the film.
        head = max(bottom - (_visible_top(board, el, times, H) + TOP_MARGIN),
                   1.0)
        k = min(want / max(cur, 1e-6),
                (W * 0.42) / max(cur, 1e-6),
                head / max(float(el["fit"][1]), 1e-6))
        if k <= 1.01:
            continue
        el["fit"] = [round(cur * k, 1), round(float(el["fit"][1]) * k, 1)]
        el["at"] = [cx, round(bottom - el["fit"][1] / 2.0, 1)]
        grown += 1
        if el["fit"][0] < want - 1.0 and notes is not None:
            notes.append((
                "fyi",
                "%r reads at %d px against the %d px its lettering was drawn "
                "for; the shot has no more headroom above it."
                % (el["name"], round(el["fit"][0]), round(want))))
    if grown and notes is not None:
        notes.append(("fyi",
                      "%d lettered drawing(s) were below reading size and "
                      "were enlarged." % grown))
    return grown


def _visible_top(board, el, times, H):
    """The highest board y the camera can actually see while `el` is on.

    The camera holds a different centre and zoom for every beat, so a margin
    measured against the board's own top edge means nothing. Only the
    tightest framing during the drawing's life is safe to grow into.
    """
    start, end = _live_window(el, times)
    moves = board.get("camera", {}).get("moves") or []
    breath = 1.0 + float((board.get("camera") or {}).get("zoom") or 0.0)
    stamped = [(_sortable(mv.get("t"), times), mv) for mv in moves]
    worst = None
    for i, (t, mv) in enumerate(stamped):
        nxt = stamped[i + 1][0] if i + 1 < len(stamped) else 1e9
        if t > end or nxt < start:
            continue
        # `zoom` breathes by the board's own amount; assume the tighter end of
        # that breath rather than the nominal value.
        z = max(float(mv.get("zoom") or 1.0) * breath, 1e-6)
        cy = float((mv.get("at") or [0, H / 2.0])[1])
        top = cy - (H / z) / 2.0
        worst = top if worst is None else max(worst, top)
    return 0.0 if worst is None else worst


def _ground_under(board, el, times):
    """The ground a drawing is actually standing on.

    A drawing's own beat may cast land for it; otherwise it stands on the
    act's ground. Where two acts' grounds are both on screen — which happens
    at every hand-over, and happens for longer now that a fade counts as
    being on screen — the right answer is the one it shares the most *time*
    with, not whichever comes first in the list. Taking the first put a
    lantern that lived 31.0-34.1 s on the outgoing act's hill, which left at
    31.4 s, leaving it hanging 238 px over the hill it spent its life on.

    `_ground_span` and `_seat_on_ground` must agree about this or they will
    fight, so they both come here.
    """
    bid = str(el.get("id") or "").split("_")[0]
    win = _live_window(el, times)
    own, act, best = None, None, 0.0
    for g in board["elements"]:
        if g.get("type") != "art" or g.get("name") not in staging.GROUND:
            continue
        if not g.get("fit") or not g.get("in"):
            continue
        gw = _live_window(g, times)
        if not _overlaps_in_time(gw, win):
            continue
        gid = str(g.get("id") or "")
        if gid.split("_")[0] == bid:
            own = g
        elif gid.startswith("sc"):
            shared = min(gw[1], win[1]) - max(gw[0], win[0])
            if shared > best:
                act, best = g, shared
    return own or act


def _ground_span(board, el, times):
    """The x-range an element is allowed to occupy: its own ground's.

    Separation moves things sideways to stop them colliding, and without a
    limit it will happily push a chair off the end of the hill it is standing
    on and out over open water. A drawing may be moved anywhere along the
    ground it belongs to, and nowhere else.
    """
    host = _ground_under(board, el, times)
    if host is None:
        return None
    gx0, gy0, gx1, gy1 = _box(host)
    # A ground is not a rectangle and not a uniform dome either: the usable
    # span is however wide the *drawn* surface still is at the height this
    # element sits at. `staging.SURFACE` holds that shape, measured from the
    # artwork, so a hill narrows like a hill and a quay stays flat like a quay.
    span = (gx1 - gx0) / 2.0
    mid = (gx0 + gx1) / 2.0
    h = max(1.0, gy1 - gy0)
    up = min(1.0, max(0.0, (gy1 - el.get("at", [0, gy1])[1]) / h))
    reach = staging.surface_reach(host.get("name"), up)
    span *= max(0.18, reach)
    return mid - span, mid + span


def _hard_rules(board, beat_scene, scene_starts, times):
    """The four rules this style does not get to break.

    Every one of these was a defect a viewer reported, not a theory. They are
    checked here — after everything else has had its say — because a rule that
    lives only in a reference document is a rule that comes back. A `blocking`
    note stops the compile.
    """
    out = []
    cam = board.get("camera") or {}

    # 1. The camera never shakes. Not for emphasis, not for impact. A shake
    #    reads as a mistake in a film made of paper; slow pans carry weight
    #    better and cost nothing.
    if cam.get("shake"):
        out.append(("blocking",
                    "the camera carries %d shake(s). This style does not "
                    "shake — use a slow pan instead."
                    % len(cam["shake"])))

    # 2. A scene starts clean. Nothing from the previous scene may still be on
    #    screen once the next scene's setting has landed, or the two places
    #    occupy one frame and the film stops making sense.
    late = []
    for e in board["elements"]:
        k = beat_scene.get(str(e.get("id") or "").split("_")[0])
        nxt = scene_starts.get("sc%d" % (k + 1)) if k is not None else None
        if not nxt or e.get("kind") == "scene":
            continue
        o = e.get("out")
        if not o or _sortable(o.get("t"), times) > nxt[0] + 0.35:
            late.append(str(e.get("id")))
    if late:
        out.append(("blocking",
                    "%d element(s) from an earlier scene are still on screen "
                    "when the next scene starts (%s). Clear a scene before "
                    "building the next one."
                    % (len(late), ", ".join(sorted(late)[:6]))))

    # 3. Nothing new on screen means no reason to move. Moving anyway is the
    #    churn that gets reported as shake even when no shake exists.
    # 4. ...but a parked camera over still artwork is a slideshow. Whatever
    #    the camera stops looking at has to keep breathing.
    parked = [e for e in board["elements"]
              if e.get("type") == "art" and not e.get("sway")
              and not e.get("drift") and float(e.get("float") or 0) <= 0.01]
    if len(parked) > max(2, len(board["elements"]) * 0.25):
        out.append(("blocking",
                    "%d drawing(s) have no drift, no sway and no float. A "
                    "parked camera over still artwork is a slideshow — give "
                    "them a slow sway." % len(parked)))

    # 5. Two places may not share the frame at the same size, and nothing may
    #    be drawn on top of anything else that matters. Both were reported as
    #    "image overlap" and both survived every earlier check, because those
    #    checks compared *scenes* and these defects happen inside one.
    art = [e for e in board["elements"]
           if e.get("type") == "art" and e.get("fit") and e.get("in")]
    twins, collided = [], []
    for i, late in enumerate(art):
        for early in art[:i]:
            if not _overlaps_in_time(_live_window(early, times),
                                     _live_window(late, times)):
                continue
            if not _boxes_hit(_box(early), _box(late)):
                continue
            if abs(float(early.get("parallax", 0.5))
                   - float(late.get("parallax", 0.5))) >= DEPTH_APART:
                continue  # different depths: z-order already reads right
            _g = staging.GROUND - staging.FIXTURE
            both_ground = (early.get("name") in _g
                           and late.get("name") in _g)
            if both_ground:
                ea = abs(_box(early)[2] - _box(early)[0])
                la = abs(_box(late)[2] - _box(late)[0])
                if min(ea, la) / max(ea, la, 1.0) > 0.7:
                    twins.append("%s+%s" % (early.get("id"), late.get("id")))
            elif str(early.get("id") or "").split("_")[0] != \
                    str(late.get("id") or "").split("_")[0] \
                    and early.get("name") not in staging.GROUND \
                    and late.get("name") not in staging.GROUND:
                collided.append("%s+%s" % (early.get("id"), late.get("id")))
    if twins:
        out.append(("blocking",
                    "two settings share the frame at the same scale (%s). One "
                    "of them must go to distance — two horizons is not a "
                    "picture." % ", ".join(sorted(set(twins))[:4])))
    if collided:
        out.append(("blocking",
                    "%d pair(s) of drawings from different beats are on top "
                    "of each other (%s). Move them clear."
                    % (len(collided), ", ".join(sorted(set(collided))[:4]))))

    # 6. A caption is never hidden. It belongs to the viewer rather than to
    #    the world, so no drawing may be stacked in front of one.
    buried = []
    for c in board["elements"]:
        if c.get("type") != "chip" or not c.get("in"):
            continue
        cw = len(str(c.get("text", ""))) * float(c.get("size", 60)) * 0.60
        cb = (c["at"][0] - cw / 2, c["at"][1] - float(c.get("size", 60)),
              c["at"][0] + cw / 2, c["at"][1] + float(c.get("size", 60)))
        for e in board["elements"]:
            if e.get("type") != "art" or not e.get("fit") or not e.get("in"):
                continue
            if int(e.get("z", 0)) <= int(c.get("z", 0)):
                continue
            if not _overlaps_in_time(_live_window(e, times),
                                     _live_window(c, times)):
                continue
            if _boxes_hit(_box(e), cb):
                buried.append("%s under %s" % (c.get("id"), e.get("id")))
                break
    if buried:
        out.append(("blocking",
                    "%d caption(s) are drawn behind artwork (%s). A caption "
                    "is never occluded."
                    % (len(buried), ", ".join(sorted(set(buried))[:4]))))
    return out


def _variety_notes(board, n_beats, beat_ids=None, slot_of=None, times=None):
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

    # Two pictures are on the board together only if their *lifetimes* overlap.
    # This used to be inferred from slot distance, on the assumption that every
    # element lives for LIVE slots. That assumption stopped being true once the
    # compiler started retiring a copy as its namesake arrives, so the estimate
    # flagged pairs that are provably never on screen together -- and this is a
    # blocking note, so it failed correct boards. Where an element states when
    # it leaves, believe it; fall back to the slot estimate only for the ones
    # that never leave.
    slots = slot_of or {}
    pos = [slots.get(e.get("id"), i) for i, e in enumerate(art)]
    tm = times or {}

    def _window(e, i):
        a = _sortable((e.get("in") or {}).get("t"), tm) if e.get("in") else None
        b = _sortable((e.get("out") or {}).get("t"), tm) if e.get("out") else None
        return a, b

    seen, close = {}, []
    for i, name in enumerate(used):
        j = seen.get(name)
        if j is not None:
            ai, bi = _window(art[j], j)
            aj, _ = _window(art[i], i)
            if bi is not None and aj is not None:
                # Both ends are known, so the answer is not a guess. A tenth of
                # a second of slack keeps a hand-off -- one leaving exactly as
                # the other lands -- from counting as an overlap.
                overlapping = aj < bi - 0.1
            else:
                overlapping = pos[i] - pos[j] <= LIVE
            if overlapping:
                close.append((name, art[j].get("id") or "#%d" % j,
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
    p.add_argument("--motion-plan", metavar="FILE",
                   help="motion-plan.json from the animation-director skill: "
                        "spends the camera budget unevenly instead of giving "
                        "every beat the same move")
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

    mp = None
    if a.motion_plan:
        try:
            with open(a.motion_plan, encoding="utf-8") as fh:
                mp = json.load(fh)
        except (OSError, ValueError) as e:
            print("compile: cannot read motion plan %s: %s"
                  % (a.motion_plan, e), file=sys.stderr)
            return 1
        # A motion plan built against a different cut of the film would move
        # the camera on beats that are no longer there. Silently ignoring the
        # mismatch is how a board ends up half-directed.
        planned = {s.get("beat") or s.get("id") for s in (mp.get("shots") or [])}
        actual = {b.get("id") or "b%d" % (i + 1)
                  for i, b in enumerate(plan.get("beats") or [])}
        orphan = planned - actual
        if orphan and len(orphan) > len(planned) * 0.5:
            print("compile: this motion plan does not describe this beat plan "
                  "— %d of %d shots name beats that do not exist. Rebuild it "
                  "with framebudget.py." % (len(orphan), len(planned)),
                  file=sys.stderr)
            return 1

    board, notes = compile_plan(plan, a.aspect, a.seed, root, motion_plan=mp)

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
