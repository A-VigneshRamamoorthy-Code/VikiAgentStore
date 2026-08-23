"""Staging — compose a beat's nouns into a scene instead of a row of cutouts.

The compiler's original grammar was a *collage*: two slots, left and right, one
illustration dropped into each. That grammar can pin a hill, a lantern and a
person onto a board, but it can never say *"she lit the lantern on the hill"* —
because three cutouts side by side is a list of nouns, not a sentence. A viewer
reads position as meaning, and the collage put everything in the same two
places, so every beat meant the same thing.

This module gives the compiler a second grammar: a **stage**. A stage has a
ground line. Settings sit on it and recede; actors stand on it; props are held
by the actor holding them; sky things go above. Positions are then *derived
from the relationship*, so the composition changes when the sentence does.

Nothing here draws. It returns placements — centre, size and z — which the
compiler turns into ordinary elements. That matters for movement: keeping the
actor a separate element is what lets it walk across the setting later
(`traverse` below). Compositing the scene into one picture would have been
simpler and would have made every journey impossible to show.

Coordinates are design units with the origin top-left, and every returned `at`
is a **centre**, because that is what `render.place_centered` consumes.
"""

from __future__ import annotations

import inspect
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- roles ----

#: Places. Drawn wide and low; the first one on a stage defines the ground
#: line for everything else. These are the only illustrations allowed to be
#: bigger than the actor standing in front of them.
GROUND = frozenset({
    "hill", "sea", "forest", "terminus", "cafe", "hospital", "hotel",
    "stairs", "map",
})

#: Weather and particle fields. Not a place and not a thing — a layer that
#: covers the whole frame and sits *over* everything, because that is where
#: falling snow and drifting smoke actually are relative to a figure standing
#: in them. Treating snow as a "place" put a drift of it on the ground line
#: where it competed with the hill for the same slot and the figure standing
#: in the weather ended up standing beside it.
#:
#: This is also the cheapest motion in the whole style: a particle layer over
#: a held drawing reads as a living shot without redrawing the subject, which
#: is the oldest trick in limited animation.
ATMOS = frozenset({"snow", "smoke"})

#: Things that can act, and therefore things that can *move*. An actor is
#: scaled against the frame, not against its setting, so a person never comes
#: out taller than the hill they are standing on.
ACTOR = frozenset({
    "figure", "crowd", "mouse", "car", "airliner", "helicopter", "boat",
    "dinghy", "trawler", "parachute",
})

#: Things carried, handed over, or found. A prop is anchored to whichever
#: actor is on stage rather than given a slot of its own, which is the whole
#: difference between "a person, and a lantern" and "a person holding a
#: lantern".
PROP = frozenset({
    "lantern", "candle", "flame", "note", "briefcase", "document", "envelope",
    "ticket", "coin", "banknotes", "necktie", "cigarette", "glass", "phone",
    "sketch", "magnifier", "fingerprint", "cctv", "radar",
})

#: Things that belong overhead. Placed in the top third regardless of what
#: else is on stage; a moon at eye level reads as a lamp.
SKY = frozenset({"moon", "star", "halo"})

#: Data-bearing drawings. They are not part of the scene's space at all — they
#: are an inset the film cuts to, so they get the frame to themselves.
DIAGRAM = frozenset({"timeline", "thread", "clock"})


def role_of(name: str) -> str:
    """Which grammar slot an illustration occupies."""
    if name in GROUND:
        return "ground"
    if name in ATMOS:
        return "atmos"
    if name in ACTOR:
        return "actor"
    if name in SKY:
        return "sky"
    if name in DIAGRAM:
        return "diagram"
    if name in PROP:
        return "prop"
    return "prop"


# ------------------------------------------------------- natural sizes ----

_BOX_CACHE: dict = {}


def _render_blocks() -> dict:
    """The body of each ``name == "..."`` branch in ``render.make_art``.

    Parsed rather than restated, because the renderer is the authority on how
    big a drawing is *meant* to be: it calls ``sc("w", 800, 500)``, and that
    pair is the box the picture was designed for. A hand-copied table here
    would disagree with it the first time either changed.
    """
    try:
        with open(os.path.join(HERE, "render.py"), encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        return {}
    out = {}
    # Both `img = I.f(...)` and `return I.f(...)` appear; taking the text up
    # to the next branch covers either without caring which.
    parts = re.split(r'name == "([a-z_]+)":', body)
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1][:400]
    return out


def _name_to_func() -> dict:
    """Map storyboard art names to the illustration functions behind them."""
    out = {}
    for name, blk in _render_blocks().items():
        m = re.search(r"I\.([a-z_]+)\(", blk)
        if m:
            out[name] = m.group(1)
    return out


def natural_box(name: str) -> tuple[float, float]:
    """The proportions an illustration was designed at, as ``(w, h)``.

    Anchoring needs this: to stand a figure's *feet* on a ground line the
    compiler must know how tall the figure will be drawn, and `size` alone
    only ever meant "longest side".

    The renderer's own ``sc("w", …)``/``sc("h", …)`` defaults win, since they
    are what it will actually draw at. Illustrations sized by a single
    ``size`` argument have no width there, so those fall back to the drawing
    function's signature.
    """
    if name in _BOX_CACHE:
        return _BOX_CACHE[name]
    box = None
    blk = _render_blocks().get(name, "")
    mw = re.search(r'sc\("w",\s*([\d.]+)', blk)
    mh = re.search(r'sc\("h",\s*([\d.]+)', blk)
    if mw and mh:
        box = (float(mw.group(1)), float(mh.group(1)))
    if box is None:
        try:
            import illustrations as I  # noqa: N817  - deferred; heavy import
            f = getattr(I, _name_to_func().get(name, name), None)
            if f is not None:
                p = inspect.signature(f).parameters
                w = p["w"].default if "w" in p else None
                h = p["h"].default if "h" in p else None
                s = p["size"].default if "size" in p else None
                if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                    box = (float(w), float(h))
                elif isinstance(h, (int, float)):
                    # `figure`, `lantern`, `candle`: designed by height alone.
                    # They are all uprights, so a 0.62 ratio is closer than
                    # the square a missing width would otherwise imply — and
                    # the renderer's `sc("size", …)` for these means "longest
                    # side", not "square", so it must not be read as a box.
                    box = (float(h) * 0.62, float(h))
                elif isinstance(s, (int, float)):
                    box = (float(s), float(s))
        except Exception:
            pass
    if box is None:
        # Genuinely square drawings (a halo, a coin, a radar sweep) whose
        # size argument carries no default to introspect.
        ms = re.search(r'sc\("size",\s*([\d.]+)', blk)
        if ms:
            box = (float(ms.group(1)), float(ms.group(1)))
    box = box or (1.0, 1.0)
    _BOX_CACHE[name] = box
    return box


def _fit(name: str, want_w: float, want_h: float) -> tuple[float, float]:
    """Scale a drawing's own proportions to fit inside a box."""
    nw, nh = natural_box(name)
    k = min(want_w / max(nw, 1e-6), want_h / max(nh, 1e-6))
    return nw * k, nh * k


# ------------------------------------------------------------- staging ----

#: Where the ground sits, as a fraction of frame height. Low enough to leave
#: sky, high enough that a figure standing on it is not cramped against the
#: bottom edge.
GROUND_Y = 0.775

#: An actor's height as a fraction of the frame. A person is not the frame's
#: subject by being huge; they are its subject by being *placed*.
ACTOR_H = 0.30

#: A setting's width as a fraction of the frame. Over 1.0 deliberately: a
#: landscape should run past both edges so the frame is a window onto it
#: rather than a picture of it sitting on a table.
GROUND_W = 1.12


def stage(cast, W: float, H: float, z0: int = 0, facing: int = 1):
    """Place a beat's cast on a shared stage.

    `cast` is an ordered list of ``(name, params)``. Returns a list of
    ``dict(name, params, at, fit, z, role)`` ready to become elements.

    The rules are the ones a layout artist would use, in this order:

    * the **ground** is drawn wide, and its base is set *below* the ground
      line so the near edge runs off the bottom of the frame;
    * an **actor** stands with its feet on the ground line;
    * a **prop** is carried at the actor's hand — beside the body, a little
      above its middle — and is drawn small, because a lantern the size of a
      person is a lantern, not a person holding one;
    * **sky** goes in the top third, pushed to the opposite side from the
      actor so it does not sit on their head;
    * a **diagram** ignores all of this and takes the frame.
    """
    out = []
    z = z0
    ground_y = H * GROUND_Y
    actor_box = None

    grounds = [c for c in cast if role_of(c[0]) == "ground"]
    actors = [c for c in cast if role_of(c[0]) == "actor"]
    props = [c for c in cast if role_of(c[0]) == "prop"]
    skies = [c for c in cast if role_of(c[0]) == "sky"]
    atmos = [c for c in cast if role_of(c[0]) == "atmos"]
    diagrams = [c for c in cast if role_of(c[0]) == "diagram"]

    # A diagram is a cutaway, not a place. If a beat asks for one it gets the
    # frame, because a chronology squeezed beside a landscape is unreadable
    # and reading it is the only reason it is there.
    #
    # The exception is a thread over a map. `route_thread` takes its points as
    # fractions *of its own tile* precisely so they can be the same fractions
    # used for the map's markers — so the two must be given an identical box
    # and centre, or the route lands next to the places it is meant to join.
    if diagrams:
        maps = [c for c in grounds if c[0] == "map"]
        threads = [c for c in diagrams if c[0] == "thread"]
        if maps and threads:
            name, params = maps[0]
            w, h = _fit(name, W * 0.52, H * 0.70)
            at = [W * 0.5, H * 0.46]
            z += 2
            out.append({"name": name, "params": params, "at": list(at),
                        "fit": [w, h], "z": z, "role": "diagram"})
            tname, tparams = threads[0]
            z += 1
            out.append({"name": tname, "params": tparams, "at": list(at),
                        # identical box: the thread is an overlay on the map,
                        # not a second picture beside it
                        "fit": [w, h], "z": z, "role": "route"})
            return out
        if not (grounds or actors):
            name, params = diagrams[0]
            w, h = _fit(name, W * 0.46, H * 0.66)
            z += 2
            return [{"name": name, "params": params, "at": [W * 0.5, H * 0.46],
                     "fit": [w, h], "z": z, "role": "diagram"}]

    for name, params in grounds[:1]:
        w, h = _fit(name, W * GROUND_W, H * 0.46)
        z += 2
        out.append({"name": name, "params": params,
                    # base sits a little under the ground line: the setting
                    # is what the actor stands *on*, so its horizon must be
                    # behind their feet, not level with them.
                    "at": [W * 0.5, ground_y - h * 0.5 + h * 0.30],
                    "fit": [w, h], "z": z, "role": "ground"})

    # A second place in the same beat is the far distance: smaller, higher,
    # and offset, which is the cheapest honest parallax there is.
    for name, params in grounds[1:2]:
        w, h = _fit(name, W * 0.52, H * 0.24)
        z += 1
        out.append({"name": name, "params": params,
                    "at": [W * (0.72 if facing > 0 else 0.28),
                           ground_y - h * 0.5 - H * 0.16],
                    "fit": [w, h], "z": z - 1, "role": "ground_far"})

    for idx, (name, params) in enumerate(actors[:2]):
        w, h = _fit(name, W * 0.30, H * ACTOR_H)
        # Two actors face each other across the middle rather than both
        # standing in the centre of the frame on top of one another.
        if len(actors[:2]) > 1:
            x = W * (0.34 if idx == 0 else 0.66)
        else:
            x = W * (0.38 if facing > 0 else 0.62)
        z += 2
        box = {"name": name, "params": params,
               "at": [x, ground_y - h * 0.5], "fit": [w, h],
               "z": z, "role": "actor"}
        out.append(box)
        if actor_box is None:
            actor_box = (x, ground_y - h * 0.5, w, h)

    for name, params in props[:2]:
        if actor_box is None and not grounds:
            # A prop with nobody to hold it and nowhere to be *is* the
            # subject of its beat — a note, a ticket, a fingerprint. Drawn at
            # hand size in the middle of an empty frame it reads as a mistake,
            # so it takes the frame instead.
            w, h = _fit(name, W * 0.34, H * 0.52)
            z += 2
            out.append({"name": name, "params": params,
                        "at": [W * 0.5, H * 0.47], "fit": [w, h],
                        "z": z, "role": "subject"})
            continue
        w, h = _fit(name, W * 0.13, H * 0.17)
        if actor_box:
            ax, ay, aw, ah = actor_box
            # hand height: a little above the body's middle, off to the
            # leading side
            x = ax + (aw * 0.52 + w * 0.42) * facing
            y = ay - ah * 0.06
        else:
            # On a stage with a place but no person, the prop sits on the
            # ground rather than floating: it is resting there.
            x, y = W * (0.62 if facing > 0 else 0.38), ground_y - h * 0.5
        z += 2
        out.append({"name": name, "params": params, "at": [x, y],
                    "fit": [w, h], "z": z, "role": "prop"})

    for name, params in skies[:2]:
        w, h = _fit(name, W * 0.17, H * 0.20)
        x = W * (0.74 if facing > 0 else 0.26)
        z += 1
        out.append({"name": name, "params": params,
                    "at": [x, H * 0.19], "fit": [w, h],
                    # sky sits behind everything on the ground
                    "z": z0 + 1, "role": "sky"})

    # Weather goes on last and on top, covering the frame. It is the only
    # element allowed to overlap the actor, because that is the point of it.
    for name, params in atmos[:1]:
        z += 4
        out.append({"name": name, "params": params,
                    "at": [W * 0.5, H * 0.46],
                    "fit": [W * 1.06, H * 1.0],
                    "z": z, "role": "atmos"})

    # A diagram that reached this far shares its beat with a scene, so it
    # cannot have the frame. It becomes an inset on the side the actor is not
    # occupying — the pinned-up chart behind the subject.
    for name, params in diagrams[:1]:
        w, h = _fit(name, W * 0.20, H * 0.34)
        z += 2
        out.append({"name": name, "params": params,
                    "at": [W * (0.80 if facing > 0 else 0.20), H * 0.36],
                    "fit": [w, h], "z": z, "role": "inset"})

    return out


# ----------------------------------------------------------- traversal ----

#: Verbs that mean "this went somewhere", and the medium it went through.
#: A journey named in the narration and not shown is the single most common
#: way this style used to lie: the line said *walked the length of the ridge*
#: and the picture was a person standing still in the middle of the frame.
MOTION = [
    (r"\b(?:flew|flies|flying|flight|took off|airborne|in the air|bound for)\b", "air"),
    (r"\b(?:sail(?:s|ed|ing)?|row(?:s|ed|ing)?|put out to sea|"
     r"cross(?:es|ed|ing)? the water|adrift|steam(?:s|ed|ing)?|"
     r"ferr(?:y|ied|ying))\b", "water"),
    (r"\b(?:drove|driving|drives|sped|speeding|rac(?:e|ed|ing)|"
     r"pull(?:s|ed|ing)? away|drive)\b", "road"),
    # Stems rather than exact forms: the first version of this table listed
    # "climb" and "climbed" but not "climbing", so the one line in the test
    # film that was purely about someone approaching -- *"Footsteps. Below
    # her. Climbing."* -- was rendered as a person standing still.
    (r"\b(?:walk(?:s|ed|ing)?|climb(?:s|ed|ing)?|ran|running|runs|"
     r"rode|rid(?:e|es|ing)|fled|flee(?:s|ing)?|cross(?:es|ed|ing)?|"
     r"travel(?:s|led|ed|ling|ing)?|trudg(?:e|ed|ing)|"
     r"wander(?:s|ed|ing)?|march(?:es|ed|ing)?|"
     r"made (?:her|his|their) way|set out|carried it|carrying it|"
     r"went up|came down|approach(?:es|ed|ing)?)\b", "ground"),
]

#: How far across the frame a traverse runs, as a fraction of frame width.
#: Short enough to stay on screen at any zoom, long enough to read as travel
#: rather than drift.
TRAVEL = 0.34


def motion_of(text: str):
    """The medium of travel a line describes, or ``None``."""
    t = (text or "").lower()
    for pattern, medium in MOTION:
        if re.search(pattern, t):
            return medium
    return None


def traverse(medium: str, at, duration: float, facing: int = 1):
    """A `drift` spec that moves an element across the stage.

    Returned in design units for the renderer's own `drift`, which eases
    cubically from A to B over a window — so this is real travel, not a
    wobble. The vertical component is what separates the media: something
    airborne climbs as it crosses, a boat rises and falls a little, and a
    walker stays on the ground because the ground is flat.
    """
    span = TRAVEL * facing
    rise = {"air": -0.06, "water": 0.012, "road": 0.0, "ground": 0.0}.get(medium, 0.0)
    return {"x": round(span, 4), "y": round(rise, 4),
            "from": at, "to": _plus(at, max(0.8, duration * 0.92))}


def _plus(at, dt: float):
    """Offset a timeline reference (``"l4"``, ``"l4+0.3"``, or a number)."""
    if isinstance(at, (int, float)):
        return round(float(at) + dt, 3)
    s = str(at)
    m = re.match(r"^([a-z]+\d+)\s*([+-]\s*[\d.]+)?$", s.strip())
    if not m:
        return s
    base, off = m.group(1), m.group(2)
    cur = float(off.replace(" ", "")) if off else 0.0
    return "%s%+.2f" % (base, cur + dt)


def route_points(n: int, seed: int = 0, medium: str = "air"):
    """Waypoints for a `thread`, as ``(x_frac, y_frac)`` of its own tile.

    A journey between named places is drawn as a line joining them — the
    pinboard thread the style already knows how to draw. Air routes bow
    upward across the middle, because a great-circle drawn flat reads as a
    road; sea and land routes wander.
    """
    n = max(2, min(6, int(n)))
    pts = []
    for i in range(n):
        u = i / (n - 1)
        x = 0.10 + 0.80 * u
        if medium == "air":
            y = 0.62 - 0.34 * (1.0 - (2.0 * u - 1.0) ** 2)
        else:
            y = 0.44 + 0.20 * ((i % 2) - 0.5) * 2 * (0.4 + 0.6 * u)
        pts.append((round(x, 3), round(y, 3)))
    return pts
