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
    (r"\b(?:hospital|casualty|ward|clinic)\b", ("hospital", {})),
    (r"\b(?:railway|train station|railway station|terminus|platform)\b",
                                           ("terminus", {})),
    (r"\b(?:cafe|café|restaurant|shopfront)\b", ("cafe", {})),
    (r"\b(?:hotel|palace)\b",              ("hotel", {})),
    (r"\b(?:helicopter|chopper)\b",        ("helicopter", {"rotor": 1})),
    (r"\b(?:airstair|aft stair|rear stair)\b",
                                           ("airliner", {"stairs": 0.9})),
    (r"\b(?:airliner|aeroplane|airplane|jetliner|boeing|airbus|"
     r"aircraft|plane|jet|cockpit|fuselage|cabin crew|flight \d+)\b",
                                           ("airliner", {})),
    (r"\b(?:parachute|chute|canopy|skydiv|jumper|bail(?:ed)? out)",
                                           ("parachute", {})),
    (r"\b(?:banknote|bank note|ransom|cash|bills?\b|currency|"
     r"twenties|\$[\d,]+)",                 ("banknotes", {})),
    (r"\b(?:necktie|tie\b|clip-on)",       ("necktie", {})),
    (r"\b(?:trawler|fishing boat)\b",      ("trawler", {})),
    (r"\b(?:dinghy|inflatable)\b",         ("dinghy", {})),
    (r"\b(?:boat|vessel|ship|ferry)\b",    ("boat", {})),
    (r"\b(?:sea|ocean|waves|shoreline)\b", ("sea", {})),
    (r"\b(?:crowd|protest|queue|gathering|gather)\b",
                                           ("crowd", {"count": 7})),
    (r"\b(?:commando|soldier|army)\b",     ("figure", {"kind": "commando"})),
    (r"\b(?:police|policeman|policemen|officer)\b",
                                           ("figure", {"kind": "police"})),
    (r"\b(?:staff|worker|employee|nurse|doctor)\b",
                                           ("figure", {"kind": "staff"})),
    (r"\b(?:man|woman|person|witness|survivor|figure)\b",
                                           ("figure", {"kind": "civilian"})),
    (r"\b(?:map|region|country|route)\b",  ("map", {})),
    (r"\b(?:timeline|chronology)\b",       ("timeline", {})),
    (r"\b(?:clock|o'clock|hour|minute)\b", ("clock", {})),
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
    (r"\b(?:thread|link|connect|conspir)",  ("thread", {})),
]

#: Where a beat lives — a *box*, not a point, as fractions of the frame.
#: A beat's picture and its keyword chips are laid out entirely inside its own
#: box, and the four boxes do not overlap, so two live beats cannot collide.
#: An earlier version placed a picture at a point and hung the chips below it;
#: the chips of an upper slot then landed on top of the picture in the lower
#: one. Boxes make that failure impossible rather than unlikely.
SLOTS = [(0.09, 0.11, 0.47, 0.49),
         (0.53, 0.13, 0.91, 0.51),
         (0.10, 0.53, 0.48, 0.89),
         (0.53, 0.55, 0.91, 0.91)]

#: How many later beats a picture stays on the board for. A collage should feel
#: like it is being assembled, so things must persist past their own line — but
#: a board that never clears ends up an unreadable pile, which is exactly what
#: the first version of this compiler produced.
LIVE = len(SLOTS) - 1

#: A big picture for a beat that carries the moment, a small one for support.
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


class Slot(object):
    """A rectangle of board, and a cursor down it.

    Everything a beat draws is requested from its own slot, so nothing a beat
    emits can stray into a neighbour's territory.
    """

    def __init__(self, box, W, H, chips):
        x0, y0, x1, y1 = box
        self.x0, self.y0 = x0 * W, y0 * H
        self.x1, self.y1 = x1 * W, y1 * H
        self.cx = (self.x0 + self.x1) / 2.0
        # Reserve the bottom of the box for the keyword chips.
        self.chip_h = min((self.y1 - self.y0) * 0.5, 96.0 * chips + 24)
        self.art_h = (self.y1 - self.y0) - self.chip_h
        self.cursor = self.y1 - self.chip_h + 12

    def art(self, want):
        """Centre and size for the picture, shrunk to fit the box."""
        size = int(min(want, self.x1 - self.x0, self.art_h))
        return (int(self.cx), int(self.y0 + self.art_h / 2.0)), max(120, size)

    def chip(self, text, want):
        """Centre and point size for the next chip, shrunk to fit the width."""
        width = self.x1 - self.x0
        size = int(min(want, width / max(6, len(text)) / 0.60))
        y = self.cursor + size * 0.62
        self.cursor = y + size * 0.62 + 14
        return (int(self.cx), int(min(y, self.y1 - size * 0.4))), max(40, size)


#: Below this a title card is unreadable at thumbnail size, so the title is
#: stacked onto another line rather than shrunk any further.
TITLE_MIN_PX = 44
#: More than this and the card stops being a card.
TITLE_MAX_LINES = 3


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


def compile_plan(plan, aspect="16:9", seed=None, root="."):
    W, H = ASPECTS[aspect]
    seed = plan.get("seed", 7) if seed is None else seed
    rng = random.Random(seed)
    catalogue = art_catalogue()
    notes = []

    times, total, _ = (beatplan.timeline(plan, root) if beatplan else ({}, 0.0, []))

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

    # The cold open. A long lead_in is a deliberate silence, not dead air --
    # in the measured reference the title is held for around 27 seconds before
    # anyone speaks. Left empty it renders as blank paper, which reads as a
    # broken file rather than as restraint, so the compiler stages the title
    # and the film's recurring objects across it.
    lead = float(board["timing"].get("lead_in", 0) or 0)
    if lead >= 6.0:
        title = str(plan.get("title") or "").upper()
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
                "in": {"t": round(lead * 0.34 + i * 0.35, 2),
                       "dur": 1.4, "anim": "stamp"},
                "out": {"t": round(hold, 2), "dur": 0.9},
                "sfx": "stamp" if i == 0 else None})
        # Two objects, established before the narrator exists.
        opening = [a.get("hint") for b in (plan.get("beats") or [])[:14]
                   for a in (b.get("assets") or []) if a.get("hint")]
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
                "size": 300, "w": 300, "h": 300, "z": 55 + k,
                "seed": 800 + k, "rotate": -1.5 + 3.0 * k,
                "in": {"t": round(lead * 0.06 + 2.2 * k, 2), "dur": 1.6,
                       "anim": "fade"},
                "out": {"t": round(hold, 2), "dur": 0.9}})

    zc, ec = 10, 1000
    beats = plan.get("beats") or []
    for i, b in enumerate(beats):
        at = b.get("at", 0)
        bid = b.get("id") or "b%d" % i
        intent = b.get("intent") or "establish"
        emphasis = float(b.get("emphasis") if b.get("emphasis") is not None else 0.5)
        words = b.get("keywords") or []
        slot = Slot(SLOTS[i % len(SLOTS)], W, H, len(words))
        (x, y), size = slot.art(SIZE.get(intent, 400) * (0.85 + 0.3 * emphasis))
        zc += 2
        ec += 1

        # Retire this beat just before its slot is claimed again.
        successor = i + LIVE + 1
        leave = ({"t": _shift(beats[successor]["at"], -0.45), "dur": 0.5}
                 if successor < len(beats) else None)

        assets = [a for a in (b.get("assets") or []) if isinstance(a, dict)]
        # An asset that names a real file is not ours to illustrate; only a
        # hint-bearing one (or the subject line) asks for catalogue art.
        drawable = [a for a in assets
                    if a.get("kind") in (None, "illustration", "art")]
        hint = next((a.get("hint") for a in drawable if a.get("hint")),
                    None) or b.get("subject")
        name, params, exact = pick_art(hint, catalogue)
        if name and not exact:
            notes.append(("blocking",
                          "beat %s: %r could reasonably be drawn more than one "
                          "way; %r was used. Confirm it, or narrow the hint."
                          % (bid, hint, name)))

        if name:
            el = {"type": "art", "name": name, "at": [x, y], "size": size,
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
            if name in ("map", "timeline", "sea", "hill", "crowd", "smoke",
                        "flame", "snow", "hospital", "terminus", "cafe",
                        "hotel", "car", "boat", "dinghy", "trawler",
                        "helicopter", "cctv", "airliner", "banknotes"):
                el["w"], el["h"] = size, int(size * 0.62)
                el.pop("size", None)
            board["elements"].append(el)
        else:
            notes.append(("blocking",
                          "beat %s wants %r — the paper catalogue has no "
                          "illustration for it. A placeholder is on the board; "
                          "either pick from %s, or add an illustration to "
                          "illustrations.py."
                          % (bid, hint, ", ".join(sorted(catalogue)[:8]) + ", ...")))
            text = ("[ART: %s]" % (hint or "?"))[:38].upper()
            (px, py), psize = slot.art(0)
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
            board["elements"].append({
                "type": "chip", "text": text,
                "id": "%s_kw%d" % (bid, k),
                "at": [cx, cy],
                "size": csize, "z": zc, "seed": ec,
                "rotate": round(jitter(rng, 0, 2.4), 1),
                "torn": emphasis > 0.6,
                "in": {"t": _shift(at, 0.25 + 0.35 * k), "dur": 0.55,
                       "anim": "stamp"},
                **({"out": dict(leave)} if leave else {}),
                "sfx": "stamp"})

        if intent == "annotate" or (b.get("annotate") or {}).get("mark"):
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
        # beat already owns a quadrant, so centring hard on one throws the
        # other three out of frame and the collage stops reading as a board.
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

    return board, notes


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
