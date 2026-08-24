#!/usr/bin/env python3
"""Compile a style-neutral beat plan into a 2d-animation storyboard.

The one rule this file exists to enforce: **it never invents a picture.**
Every set, prop, cast member and action a beat asks for is checked against the
live catalogues in ``sets.py`` and ``poses.py`` -- read at run time, never
copied -- so the compiler cannot offer something the renderer has no way to
draw. What it cannot resolve becomes a labelled placeholder, is reported, and
exits non-zero.

    python3 compile.py beat-plan.json -o storyboard.json
    python3 compile.py beat-plan.json --check
    python3 compile.py beat-plan.json -o sb.json --motion-plan motion-plan.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCHEMA = 1
STYLE = "2d-animation"


# --------------------------------------------------------------------------
# the catalogues, read from the modules that actually draw them
# --------------------------------------------------------------------------

def _audio_moods():
    """The cue names `audio.py` actually publishes, or an empty set.

    Returns empty rather than raising when audio is unavailable: a missing
    optional module must not stop a board compiling.
    """
    try:
        import audio as _audio
        return set(getattr(_audio, "MOODS", ()) or ())
    except Exception:
        return set()


def ground_of(set_name):
    """The y of a set's ground line, or None for a top-down or skyward set.

    Framing has to know this: zooming about the middle of the scene crops the
    ground away, and the ground is where the characters are.
    """
    try:
        import sets as _sets
        table = getattr(_sets, "SET_GROUND", {}) or {}
        if set_name in table:
            return table[set_name]
        # A set the table does not mention is assumed to stand on the ground;
        # that is true of every set in this style except the aerial ones.
        return getattr(_sets, "GROUND_Y", GROUND_Y)
    except Exception:                                         # pragma: no cover
        return GROUND_Y


def catalogues():
    """Return (sets, props, poses, prop_anims, problems), straight from the engine.

    `prop_anims` maps a prop to the named states it accepts, so a beat asking
    for a lamp that does not exist is caught here rather than silently ignored.

    Imported lazily and defensively: `--check` on a machine where a drawing
    module is mid-edit should report that plainly rather than traceback.
    """
    sets_, props, poses_ = set(), set(), set()
    prop_anims = {}
    problems = []
    try:
        import sets as _sets
        sets_ = _names(_sets, "SETS", "SET_LAYERS", "SET_GROUND")
        props = _names(_sets, "PROPS", "PROP_ANCHOR", "PROP_ANIMS")
        prop_anims = {k: tuple(v) for k, v in
                      (getattr(_sets, "PROP_ANIMS", None) or {}).items()}
    except Exception as exc:                                  # pragma: no cover
        problems.append("sets.py unavailable (%s)" % exc)
    try:
        import poses as _poses
        poses_ = _names(_poses, "POSES", "POSE_LIBRARY", "LIBRARY")
    except Exception as exc:                                  # pragma: no cover
        problems.append("poses.py unavailable (%s)" % exc)
    return sets_, props, poses_, prop_anims, problems


def _names(mod, *candidates):
    """Union the keys of whichever catalogue dicts a module actually exposes.

    The drawing modules are free to key their catalogues however they like, so
    long as the names users type are the keys. Reading every known catalogue
    and taking the union means a set registered in only one of them still
    counts as drawable -- and a name in none of them is genuinely missing.
    """
    found = set()
    for attr in candidates:
        value = getattr(mod, attr, None)
        if isinstance(value, dict):
            found |= set(value)
        elif isinstance(value, (list, tuple, set, frozenset)):
            found |= {str(v) for v in value}
    return found


# --------------------------------------------------------------------------
# cast
# --------------------------------------------------------------------------

# A cast member is a costume and a build, not a drawing -- the rig draws it.
# Anything a beat names that is not here is reported, never guessed at.
CAST = {
    "norman":  {"shirt": "cardigan", "build": 1.0,  "height": 18.0},
    "officer": {"shirt": "uniform",  "build": 1.05, "height": 18.4},
    "cyclist": {"shirt": "lycra",    "build": 0.92, "height": 17.4},
    "reporter": {"shirt": "jacket",  "build": 0.96, "height": 17.8},
    "civilian": {"shirt": "plain",   "build": 1.0,  "height": 18.0},
}

# What a cast member does when the beat does not say.
DEFAULT_ACTION = {
    "norman": "drive", "officer": "stand", "cyclist": "walk",
    "reporter": "stand", "civilian": "stand",
}


# --------------------------------------------------------------------------
# intent -> staging
# --------------------------------------------------------------------------

# Each intent gets a camera grammar and a framing. The amount is scaled later
# by the motion plan, so these are shapes rather than magnitudes.
INTENT = {
    "establish":  {"move": "track", "framing": "wide",  "overlay": None},
    "reveal":     {"move": "push",  "framing": "mid",   "overlay": None},
    "evidence":   {"move": "push",  "framing": "close", "overlay": "chyron"},
    "portrait":   {"move": "push",  "framing": "close", "overlay": None},
    "locate":     {"move": "pull",  "framing": "wide",  "overlay": "map"},
    "compare":    {"move": "none",  "framing": "wide",  "overlay": "split"},
    "list":       {"move": "none",  "framing": "mid",   "overlay": "counter"},
    "annotate":   {"move": "none",  "framing": "mid",   "overlay": "circle"},
    "emphasise":  {"move": "push",  "framing": "close", "overlay": None},
    "transition": {"move": "whip",  "framing": "wide",  "overlay": None},
    # The only intent that leaves the camera alone. Every other locked-off
    # grammar here (`compare`, `list`, `annotate`) drags an overlay in with
    # it, so a film that simply wants to point a camera at something and let
    # the performance play had nowhere to go. A shot compiled from `observe`
    # is exempt from the frozen-frame rescue below -- see `SELF_ANIMATING`.
    "observe":    {"move": "none",  "framing": "wide",  "overlay": None},
}

# Intents whose shots are exempt from the frozen-frame camera rescue.
#
# The rescue below exists because a still camera on a still set produces runs
# of byte-identical frames, which `longest_hold_s <= 2.5` forbids. Its cure is
# a slow zoom. That cure is *wrong* for a film whose set moves on its own --
# drifting mist, running water, falling snow, a crowd -- because there the
# frames already differ and the added zoom buys nothing while destroying the
# locked-off composition the style is built on. Measured on the reference
# films this style targets: the camera is locked for minutes at a time and the
# frame stays alive entirely on atmospheric drift.
#
# Exempting an intent does not repeal the law, it relocates the obligation.
# `compile.py` cannot measure pixels, so it cannot verify that the set is
# really moving; it can only decline to paper over the question. The check
# still happens -- `render.py` reports frozen runs and `motionprofile.py`
# grades `longest_hold_s` on the finished film -- so a film that claims
# `observe` over a static set fails there, loudly, instead of quietly
# shipping with a zoom nobody asked for.
SELF_ANIMATING = {"observe"}

FRAMING_ZOOM = {"wide": 1.00, "mid": 1.22, "close": 1.55}

# Tier -> how hard the shot works. `hold` and `impact` get no camera move at
# all; that obligation comes from the style contract, not from taste.
TIER = {
    "hold":    {"on": 3, "amount": 0.00, "move": False},
    "limited": {"on": 3, "amount": 0.09, "move": True},
    "full":    {"on": 2, "amount": 0.18, "move": True},
    "sakuga":  {"on": 1, "amount": 0.30, "move": True},
    "impact":  {"on": 2, "amount": 0.00, "move": False},
}


# --------------------------------------------------------------------------
# mood, taken from the story rather than from a default
# --------------------------------------------------------------------------

MOOD_WORDS = {
    "chase":   ("pursu", "chase", "police", "siren", "speed", "escape", "getaway",
                "suspect", "fleeing", "patrol"),
    "comic":   ("sandwich", "politely", "calm", "queue", "wave", "tea", "neat",
                "indicat", "orderly", "patient"),
    "tension": ("standoff", "stopped", "nobody", "dares", "wait", "silence",
                "frozen", "tense"),
    "warm":    ("home", "family", "garden", "door", "evening", "return"),
    "bright":  ("morning", "sun", "open", "start", "new", "clear"),
    "night":   ("night", "dark", "neon", "midnight", "late"),
    "high":    ("summit", "peak", "mountain", "mist", "cloud", "climb", "ridge",
                "view", "air", "weather"),
}

# The story's mood is not the composer's vocabulary.
#
# `audio.py` publishes its own cue names, and three of the moods above --
# `comic`, `bright`, `night` -- are not among them. A board naming one got
# `unknown mood ... using chase`, so a gentle film about fog on a hill was
# scored like a car chase. The fallback was doing its job; the two modules
# simply never agreed on a word list. This is that agreement, written down.
MOOD_MUSIC = {
    "chase": "chase",
    "comic": "caper",
    "tension": "tension",
    "warm": "warm",
    "bright": "curious",
    "night": "crime",
    "high": "pastoral",
}


def choose_mood(plan):
    """Pick the film's mood from its own narration.

    Deliberately not a constant. Two unrelated films that compile to the same
    colour mean the compiler is defaulting rather than deciding -- the style
    contract calls that out as an invisible failure, so it is scored here.
    """
    text = " ".join(l.get("text", "") for l in plan.get("narration", [])).lower()
    text += " " + " ".join(b.get("subject", "") for b in plan.get("beats", [])).lower()
    if not text.strip():
        return None
    best, best_n = None, 0
    for mood, words in MOOD_WORDS.items():
        n = sum(text.count(w) for w in words)
        if n > best_n:
            best, best_n = mood, n
    return best


# --------------------------------------------------------------------------
# time helpers -- the beat plan's syntax, unchanged
# --------------------------------------------------------------------------

_OFFSET = re.compile(r"^(?P<base>.+?)\s*(?P<op>[+-])\s*(?P<off>[0-9.]+)\s*$")


def line_lengths(plan, base_dir):
    """Measure every narration line. Returns {id: seconds}."""
    out = {}
    for line in plan.get("narration", []):
        lid = line.get("id")
        if line.get("duration") is not None:
            out[lid] = float(line["duration"])
            continue
        rel = line.get("audio")
        if not rel:
            out[lid] = 0.0
            continue
        path = os.path.join(base_dir, rel)
        out[lid] = _probe(path)
    return out


def _probe(path):
    import subprocess
    if not os.path.exists(path):
        return 0.0
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def line_clock(plan, lengths, lead_in):
    """Absolute start/end for every line, including its gap."""
    clock, t = {}, float(lead_in)
    for line in plan.get("narration", []):
        lid = line.get("id")
        dur = lengths.get(lid, 0.0)
        clock[lid] = (t, t + dur)
        t += dur + float(line.get("gap_after", 0.0) or 0.0)
    return clock, t


def resolve_time(spec, clock):
    """`l3`, `l3+0.4`, `l3.end`, `l3.end+0.2`, or absolute seconds."""
    if isinstance(spec, (int, float)):
        return float(spec)
    s = str(spec).strip()
    off = 0.0
    m = _OFFSET.match(s)
    if m:
        s = m.group("base").strip()
        off = float(m.group("off")) * (1 if m.group("op") == "+" else -1)
    end = False
    if s.endswith(".end"):
        s, end = s[:-4], True
    if s in clock:
        lo, hi = clock[s]
        return (hi if end else lo) + off
    try:
        return float(s) + off
    except ValueError:
        raise ValueError("cannot resolve time %r" % spec)


# --------------------------------------------------------------------------
# staging
# --------------------------------------------------------------------------

# Where a beat's subject lands when nothing more specific is known. Kept
# deliberately small: guessing a rich layout is how a compiler produces a board
# that renders and says nothing.
GROUND_Y = 44.0
CENTRE_X = 50.0
SCENE_H = 56.25
# The scene is 100 units wide, so a scene unit is also a percentage of frame
# width at zoom 1.0 -- which is what lets travel and zoom be compared directly.
SCENE_W = 100.0
# Past this, a shot with nothing animate in it stops reading as a held beat
# and starts reading as a stalled video. `motionprofile.py` checks the same.
FROZEN_FRAME_S = 2.5
# How fast a rescued hold creeps, as a fraction of frame size per second.
# Calibrated twice, because the right answer depends on the curve. Against an
# ease-out the rescue needed ~9%/s, since that curve spends most of its motion
# in the first moments and arrives with nothing left: at 4.3s, x1.09 still left
# a 3.90s frozen run, x1.25 left 2.43s and x1.45 left 1.83s.
#
# A constant-rate creep wastes none of it, and `shots.py` measures the frozen
# threshold at ~2.2%/s on a bare set. 3.5%/s clears that with margin while
# staying far below the rate at which a creep starts to read as a move.
#
# Driving it harder is not free: at 9%/s the creep lifted the film's *median*
# motion enough to raise the accent bar (2.2x median) above beats that were
# deliberately loud, and `hit_rate` fell from 1.0 to 0.714. A rescue must add
# the least motion that prevents a frozen frame, or it drowns the accents it
# shares the film with.
CREEP_PER_S = 0.035
# A cast member is 18 scene units tall (see reference/rig.md), so their middle
# sits half that above the ground -- which is where a frame should be centred.
CHAR_H = 18.0


def stage_actor(cast, idx, n, framing, ground=None):
    """Spread actors across the frame without collisions.

    `ground` is the set's own ground line. Defaulting to `GROUND_Y` puts every
    character on the street even when the set is a mountain, which does not
    read as a mistake so much as a character sunk to the neck in scenery --
    the set is drawn over them and only a head survives.
    """
    if n <= 1:
        x = CENTRE_X
    else:
        span = 34.0 if framing != "close" else 20.0
        x = CENTRE_X - span / 2.0 + span * idx / float(n - 1)
    y = GROUND_Y if ground is None else float(ground)
    return [round(x, 2), round(y, 2)]


def compile_plan(plan, base_dir, motion=None, aspect="16:9"):
    """beat plan -> (storyboard dict, list of placeholder reports)."""
    sets_, props, poses_, prop_anims, cat_problems = catalogues()
    reports = list(cat_problems)

    timing = plan.get("timing", {}) or {}
    lead_in = float(timing.get("lead_in", 1.0) or 0.0)
    tail = float(timing.get("tail", 1.5) or 0.0)

    lengths = line_lengths(plan, base_dir)
    clock, spoken_end = line_clock(plan, lengths, lead_in)

    tiers = {}
    if motion:
        shots = motion.get("shots", []) or []
        known = {s.get("beat") or s.get("id") for s in shots}
        beat_ids = {b.get("id") for b in plan.get("beats", [])}
        missing = len([b for b in known if b not in beat_ids])
        if known and missing > len(known) / 2:
            raise SystemExit(
                "motion plan does not match this beat plan: %d of %d planned "
                "shots name beats that do not exist. It is stale -- re-run "
                "framebudget.py against the current plan." % (missing, len(known)))
        for s in shots:
            tiers[s.get("beat") or s.get("id")] = s

    beats = plan.get("beats", [])
    out_shots = []
    planned = []
    prev_set = None
    prev_actors = []
    prev_props = []
    prev_mist = None

    for i, beat in enumerate(beats):
        bid = beat.get("id")
        intent = beat.get("intent", "establish")
        grammar = INTENT.get(intent, INTENT["establish"])
        # A beat may override the framing its intent implies. Intent says what
        # a shot is *for*; framing says how much of the set is in it, and the
        # two are not the same decision. On a locked-off film it is the only
        # compositional lever there is -- there is no camera move to reframe
        # with -- so denying it would leave every `observe` shot stuck at the
        # same wide.
        want_framing = (beat.get("framing") or "").strip().lower()
        if want_framing:
            if want_framing in FRAMING_ZOOM:
                grammar = dict(grammar, framing=want_framing)
            else:
                reports.append(
                    "%s: no framing %r (want %s) -- using %r"
                    % (bid, want_framing, "/".join(sorted(FRAMING_ZOOM)),
                       grammar["framing"]))
        plan_shot = tiers.get(bid, {})
        tier = plan_shot.get("tier", "limited")
        tcfg = TIER.get(tier, TIER["limited"])

        start = resolve_time(beat.get("at"), clock)
        at_expr = beat.get("at")
        # The film may not open on an empty frame. The first beat is usually
        # written against the first line of narration, which starts after the
        # lead-in, so the opening shot is pulled back to zero and simply holds
        # its first frame under the lead-in.
        if i == 0 and start > 0.0:
            at_expr = 0.0
            start = 0.0
        nxt = beats[i + 1].get("at") if i + 1 < len(beats) else None
        if nxt is not None:
            end = resolve_time(nxt, clock)
        else:
            # The last beat normally ends when the narration does, plus the
            # tail. A wordless film has no narration, so `spoken_end` is 0 and
            # that expression lands *before* the beat starts -- collapsing the
            # final shot to the 0.6s floor below. Since this style supports
            # wordless films, the last beat may state its own duration. It is
            # the one place an absolute duration is safe: nothing follows it,
            # so there is nothing for it to drift against.
            end = spoken_end + tail
            explicit = beat.get("dur")
            if explicit is not None:
                try:
                    end = max(end, start + float(explicit))
                except (TypeError, ValueError):
                    reports.append(
                        "%s: dur %r is not a number -- ignored"
                        % (bid, explicit))
        if end <= start:
            end = start + 0.6
            nxt = None

        assets = beat.get("assets")
        inherit = assets is not None and len(assets) == 0

        shot = {
            "id": "s%d" % (i + 1),
            "beat": bid,
            "at": at_expr,
            "tier": tier,
            "on": tcfg["on"],
            "set": prev_set,
            "mist": prev_mist,
            "actors": [],
            "props": [],
        }

        # A cut list is defined by its cut points, so a shot ends where the
        # next one begins -- said symbolically, so both endpoints resolve
        # against whichever clock the renderer uses. Writing an absolute `dur`
        # here instead would silently drift the moment narration is retimed
        # (the planning clock counts whole clips; the renderer trims silence).
        if nxt is not None:
            shot["until"] = nxt
        else:
            shot["dur"] = round(end - start, 3)
        planned.append(end - start)

        if inherit:
            # The picture this line calls for is already on screen. Hold it
            # rather than drawing a second copy -- a second copy is the
            # slideshow effect, not emphasis.
            shot["actors"] = json.loads(json.dumps(prev_actors))
            shot["props"] = json.loads(json.dumps(prev_props))
        else:
            actors, sprops = [], []
            for asset in (assets or []):
                kind = (asset.get("kind") or "").lower()
                hint = (asset.get("hint") or "").strip()
                if not hint:
                    continue
                if kind == "set":
                    if hint in sets_:
                        shot["set"] = hint
                    else:
                        shot["set"] = hint
                        reports.append(
                            "%s: no set %r -- placeholder" % (bid, hint))
                    # A set may take a continuous parameter -- how thick the
                    # mist is, how heavy the rain. Unlike a prop's named
                    # state this is a dial, not a menu, so it is validated as
                    # a range rather than against a catalogue. It is carried
                    # per-shot because changing it *across* shots is how a
                    # locked-off film reveals things without moving.
                    if "mist" in asset:
                        try:
                            mist = float(asset["mist"])
                        except (TypeError, ValueError):
                            reports.append(
                                "%s: set mist %r is not a number -- ignored"
                                % (bid, asset["mist"]))
                        else:
                            if not 0.0 <= mist <= 1.0:
                                reports.append(
                                    "%s: set mist %.3f outside 0..1 -- clamped"
                                    % (bid, mist))
                            shot["mist"] = round(min(max(mist, 0.0), 1.0), 3)
                elif kind == "prop":
                    if hint not in props:
                        reports.append(
                            "%s: no prop %r -- placeholder" % (bid, hint))
                    # A beat may size and place its own prop. A hand-held
                    # object staged at a vehicle's scale simply covers the
                    # actor holding it.
                    where = asset.get("at")
                    if not (isinstance(where, (list, tuple)) and len(where) >= 2):
                        where = [CENTRE_X, GROUND_Y]
                    sprop = {"kind": hint,
                             "at": [round(float(where[0]), 2),
                                    round(float(where[1]), 2)],
                             "scale": round(float(asset.get("scale", 1.0)), 3)}
                    # `sets.py` gives some props named states -- which lamp on a
                    # traffic light is lit, whether an indicator blinks. Without
                    # this the board could not ask for them.
                    anim = (asset.get("anim") or "").strip()
                    if anim:
                        allowed = prop_anims.get(hint)
                        if allowed and anim not in allowed:
                            reports.append(
                                "%s: prop %r has no state %r -- placeholder"
                                % (bid, hint, anim))
                        sprop["anim"] = anim
                        sprop["rate"] = round(float(asset.get("rate", 1.0)), 3)
                    sprops.append(sprop)
                elif kind == "actor":
                    if hint not in CAST:
                        reports.append(
                            "%s: no cast member %r -- placeholder" % (bid, hint))
                    # The beat may direct the performance; otherwise the cast
                    # member does what that character does by default.
                    action = (asset.get("action") or "").strip().lower() \
                        or DEFAULT_ACTION.get(hint, "stand")
                    if action not in poses_ and poses_:
                        reports.append(
                            "%s: no action %r -- placeholder" % (bid, action))
                    actor = {"id": hint or "actor%d" % len(actors),
                             "cast": hint, "action": action}
                    # A beat may stage and direct its own actor, exactly as it
                    # may already stage and animate its own prop. Without this
                    # the two halves of the catalogue obey different rules:
                    # a bin can be put anywhere in the scene and a person
                    # cannot, which makes a character physically unable to
                    # stand on a summit, a roof, a kerb or a stage.
                    where = asset.get("at")
                    if isinstance(where, (list, tuple)) and len(where) >= 2:
                        actor["at"] = [round(float(where[0]), 2),
                                       round(float(where[1]), 2)]
                    for key in ("rate", "scale"):
                        if asset.get(key) is not None:
                            actor[key] = round(float(asset[key]), 3)
                    if asset.get("bones"):
                        actor["bones"] = str(asset["bones"]).strip()
                    if asset.get("height") is not None:
                        actor["height"] = round(float(asset["height"]), 3)
                    if asset.get("facing") is not None:
                        actor["facing"] = 1 if float(asset["facing"]) >= 0 else -1
                    actors.append(actor)
                else:
                    reports.append("%s: unknown asset kind %r" % (bid, kind))
            for j, a in enumerate(actors):
                # Auto-staging is a fallback, not a mandate: a beat that named
                # a position has already said where the character stands, and
                # overwriting it here is what put the climber inside the
                # mountain rather than on top of it.
                if "at" not in a:
                    a["at"] = stage_actor(a["cast"], j, len(actors),
                                          grammar["framing"],
                                          ground=ground_of(shot["set"] or "street"))
                a.setdefault("facing", 1)
                a.setdefault("rate", 1.0)
                a["phase"] = round((j * 0.37) % 1.0, 3)
            shot["actors"] = actors
            shot["props"] = sprops

        if not shot["set"]:
            shot["set"] = "street"
        prev_set = shot["set"]
        # Weather persists until the film says otherwise. Resetting it per
        # shot would make a four-shot reveal impossible to write: every beat
        # would have to restate the condition it inherited.
        prev_mist = shot.get("mist")
        if prev_mist is None:
            shot.pop("mist", None)
        prev_actors = shot["actors"]
        prev_props = shot["props"]

        # camera --------------------------------------------------------
        zoom0 = FRAMING_ZOOM.get(grammar["framing"], 1.0)
        # Frame the subject rather than the middle of the set. On a ground set
        # the scene centre is sky, so a zoom about it pushes the actors out of
        # the bottom of frame; on an aerial set there is no ground and the
        # scene centre is exactly right.
        ground = ground_of(shot["set"])
        if ground is None:
            eye_y = SCENE_H / 2.0
        else:
            eye_y = ground - CHAR_H * 0.5
        if tcfg["move"] and tcfg["amount"] > 0 and intent not in SELF_ANIMATING:
            amount = float(plan_shot.get("amount", tcfg["amount"]) or tcfg["amount"])
            amount = max(amount, 0.06)
            move = grammar["move"]
            if move == "none":
                move = "push"
            cam = {"move": move, "ease": "out",
                   "hold": round(min(0.6, (end - start) * 0.25), 2)}
            if move in ("push", "pull"):
                z1 = zoom0 * (1.0 + amount) if move == "push" else zoom0 / (1.0 + amount)
                cam["zoom"] = [round(zoom0, 3), round(z1, 3)]
                cam["from"] = [CENTRE_X, round(eye_y, 2)]
            else:
                # A whip is not a track played faster -- it covers far more
                # ground, which is the whole reason a board asks for one.
                reach = {"whip": 62.0, "pan": 40.0}.get(move, 26.0)
                span = reach * amount
                cam["from"] = [round(CENTRE_X - span / 2, 2), round(eye_y, 2)]
                cam["to"] = [round(CENTRE_X + span / 2, 2), round(eye_y, 2)]
                cam["zoom"] = [round(zoom0, 3), round(zoom0, 3)]
        else:
            # hold and impact: no camera move at all. The style contract is
            # explicit that the previous rest is extended instead. An
            # `observe` shot lands here too at every tier -- the tier decides
            # how hard the *character* works, and on a locked-off film that
            # has to stay independent of whether the camera moves. Without
            # this the `none` above is coerced to a push and the style's
            # defining discipline is silently overridden by its own grader.
            cam = {"move": "none", "zoom": [round(zoom0, 3), round(zoom0, 3)],
                   "from": [CENTRE_X, round(eye_y, 2)]}
        if tier == "impact":
            # An impact is a jolt. On its own the tier only changes the
            # drawing cadence, which the audience cannot see; the camera has
            # to actually move or the hit does not register as one.
            cam["move"] = "handheld"
            shot["impact"] = 0.0
        # An actor on screen is what the shot is about, so let the renderer
        # hold them in frame instead of trusting a fixed centre.
        if shot["actors"]:
            cam["subject"] = shot["actors"][0]["id"]
        elif shot["props"] and ground is not None:
            cam["from"] = [round(shot["props"][0]["at"][0], 2), round(eye_y, 2)]
        # Past ~2.5s a shot whose camera barely moves stops reading as a held
        # beat and starts reading as a stalled video. Three traps here, all
        # found by measuring rendered frames rather than by reading the board:
        #
        #   * Idle life is not enough. A standing, breathing character still
        #     rendered 94 byte-identical frames -- at this scale the breath
        #     moves less than a pixel and the blink cycle outlasts the shot.
        #   * The *name* of the move proves nothing. A `push` of 1.55 -> 1.643
        #     across 5.2s is stiller than most locked shots.
        #   * Neither does the *presence* of travel. `s12` was a `track` that
        #     crossed 1.56 of 100 scene units -- 1.5% of the frame, invisible.
        #
        # So the test is magnitude, not vocabulary: whatever the move is
        # called, how much of the frame does the camera actually cross? Zoom
        # and travel are converted to the same unit -- fractions of a frame --
        # and the shortfall is made up on the zoom, which is the one lever
        # that cannot walk off the edge of the set.
        #
        # A handheld drift was tried and is far too subtle on a flat set
        # (mean frame delta 0.21 against a 0.60 threshold). A push is the
        # slowest *continuous* move that registers. On an occupied shot it is
        # simply a yori, which the style uses anyway.
        dur = end - start
        if dur > FROZEN_FRAME_S and intent not in SELF_ANIMATING:
            z0, z1 = cam["zoom"]
            lo, hi = min(z0, z1), max(z0, z1)
            # Mirrors `shots.Camera._creep_rate` deliberately: a zoom of
            # 1 -> 1+k walks each *edge* only k/2 across the view, so the
            # zoom's contribution is halved. Measuring it any other way
            # under-drives the creep by exactly 2x and the renderer then
            # reports runs of identical frames.
            zoom_rate = (hi / max(lo, 1e-6) - 1.0) / 2.0
            travel = 0.0
            frm, to = cam.get("from"), cam.get("to")
            if frm and to:
                view_w = SCENE_W / max(lo, 1e-3)
                view_h = SCENE_H / max(lo, 1e-3)
                travel = math.hypot((to[0] - frm[0]) / view_w,
                                    (to[1] - frm[1]) / view_h)
            need = CREEP_PER_S * dur
            if zoom_rate + travel < need:
                if cam["move"] == "none":
                    cam["move"] = "push"
                # The zoom makes up whatever the travel does not, doubled back
                # out of edge-rate units into a zoom ratio.
                grow = 1.0 + 2.0 * max(need - travel, 0.0)
                # A creep is a constant-rate move, and `shots.py` honours it
                # rather than substituting `out`. That distinction matters:
                # an ease-out rescue moves fastest at the start (a spurious
                # accent) and decays to a near-stop (the frozen tail it was
                # meant to prevent), so it fails both ways. Measured on this
                # film, swapping the curve cut the longest frozen run from
                # 1.57s to 0.57s with the same mean and peak. The settle is
                # the whole residual -- dropping it takes it to 0.03s -- and
                # a creep has nothing to settle into, so it goes too.
                #
                # Only a shot that is *otherwise still* may creep. A whip, an
                # impact or a follow is a move the audience is meant to feel,
                # and it has to overshoot and settle to land; flattening one
                # to a constant rate would break the very beat it carries.
                # Those shots still get the extra zoom -- they just keep
                # their own curve.
                if cam["move"] in ("push", "pull"):
                    cam["ease"] = "creep"
                    cam.pop("hold", None)
                # Only ever zoom *further in*, never further out: a wider start
                # can walk off the edge of the set, a tighter one cannot. The
                # final framing is the one the shot is about, so a pull keeps
                # its end and a push extends past it. `max` guards the rescue
                # against ever *reducing* a span it was called to enlarge.
                if z1 >= z0:
                    cam["zoom"] = [round(z0, 3), round(max(z1, z0 * grow), 3)]
                else:
                    cam["zoom"] = [round(max(z0, z1 * grow), 3), round(z1, 3)]
        shot["camera"] = cam

        # overlay -------------------------------------------------------
        ov = grammar["overlay"]
        if ov == "chyron":
            kws = beat.get("keywords") or []
            shot["overlay"] = {"kind": "chyron",
                               "text": (kws[0] if kws else beat.get("subject", ""))[:46].upper()}
        elif ov == "map":
            shot["overlay"] = {"kind": "map", "marker": [0.5, 0.5]}
        elif ov == "circle" and shot["props"]:
            # `label` is always sent, even when empty: the renderer falls back
            # to the *target's asset id* when the key is missing, which puts
            # an internal name like "policecar" on screen as if it were a
            # broadcast caption. A beat that wants words must say them.
            shot["overlay"] = {"kind": "circle",
                               "target": shot["props"][0]["kind"],
                               "label": str(beat.get("label", ""))[:26]}
        elif ov == "counter":
            shot["overlay"] = {"kind": "counter", "label": "", "from": 0, "to": len(beats)}
        elif ov == "split":
            shot["overlay"] = {"kind": "split", "left": shot["set"], "right": shot["set"]}

        if beat.get("subject"):
            shot["note"] = beat["subject"]

        # Effects belong to the beat that motivates them, so they ride along
        # rather than being invented here. `audio.build` resolves a cue's `at`
        # against the same clock as everything else, so a cue may be written
        # either shot-local ("0.4") or on the film clock ("l4+0.2").
        cues = beat.get("sfx")
        if cues:
            shot["sfx"] = [{"kind": c} if isinstance(c, str) else dict(c)
                           for c in cues]
        out_shots.append(shot)

    mood = choose_mood(plan)
    board = {
        "schema": SCHEMA,
        "style": STYLE,
        "title": plan.get("title", "Untitled"),
        "seed": plan.get("seed", 0),
        "output": {
            "path": re.sub(r"[^a-z0-9]+", "-", plan.get("title", "film").lower()).strip("-") + ".mp4",
            "width": 1080 if aspect == "9:16" else 1920,
            "height": 1920 if aspect == "9:16" else 1080,
            "fps": 30,
        },
        "timing": {"lead_in": lead_in, "tail": tail,
                   "planned_dur": round(sum(planned) + lead_in, 3)},
        "shots": out_shots,
    }
    if mood:
        # A plan may name the cue outright; otherwise the story's mood is
        # translated into the composer's vocabulary. Validated here rather
        # than discovered at render time, where the only symptom is a line of
        # log and a film scored to the wrong thing.
        cue = str(plan.get("music") or "").strip() or MOOD_MUSIC.get(mood, mood)
        known = _audio_moods()
        if known and cue not in known:
            reports.append(
                "music %r is not one of audio.MOODS (%s) -- it will fall back"
                % (cue, ", ".join(sorted(known))))
        board["music"] = {"mood": cue, "gain": 0.8}
    # `render.py` already reads `board["palette"]` and only falls back to the
    # mood when it is absent -- but nothing was ever writing it, so the film's
    # look was decided entirely by a keyword scan of its own narration. That
    # is a reasonable default and a poor mandate: a wordless film has no
    # narration to scan, and two films can legitimately share a mood and want
    # different colour. A plan may therefore name its palette outright.
    if plan.get("palette"):
        board["palette"] = str(plan["palette"]).strip()
    if plan.get("narration"):
        narr = []
        for line in plan["narration"]:
            item = {"id": line.get("id")}
            if line.get("audio"):
                item["audio"] = line["audio"]
            if line.get("duration") is not None:
                item["duration"] = line["duration"]
            item["gap_after"] = line.get("gap_after", 0.0)
            narr.append(item)
        board["narration"] = narr
    amb = _ambience_for(mood)
    if amb:
        board["ambience"] = amb
    return board, reports


def _ambience_for(mood):
    return {"chase": "city", "comic": "city", "tension": "city",
            "warm": "suburb", "bright": "city", "night": "city"}.get(mood)


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("beat_plan")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true",
                    help="validate and report; write nothing")
    ap.add_argument("--motion-plan")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    args = ap.parse_args(argv)

    with open(args.beat_plan) as fh:
        plan = json.load(fh)
    base_dir = os.path.dirname(os.path.abspath(args.beat_plan))

    motion = None
    if args.motion_plan:
        with open(args.motion_plan) as fh:
            motion = json.load(fh)

    board, reports = compile_plan(plan, base_dir, motion, aspect=args.aspect)

    n = len(board["shots"])
    dur = board["timing"]["planned_dur"]
    print("%s  --  %d shots, %.1fs, mood %s"
          % (board["title"], n, dur, (board.get("music") or {}).get("mood", "-")))
    tiers = {}
    for s in board["shots"]:
        tiers[s["tier"]] = tiers.get(s["tier"], 0) + 1
    print("  tiers: " + "  ".join("%s %d" % (k, v) for k, v in sorted(tiers.items())))

    if reports:
        print("\n%d placeholder(s) -- this style never invents a picture:"
              % len(reports), file=sys.stderr)
        for r in reports:
            print("  " + r, file=sys.stderr)
        print("\nAdd the artwork, rephrase the beat, or change style.",
              file=sys.stderr)

    if args.check:
        return 1 if reports else 0

    if not args.out:
        ap.error("-o is required unless --check")
    with open(args.out, "w") as fh:
        json.dump(board, fh, indent=2, ensure_ascii=False)
    print("  wrote %s" % args.out)
    return 1 if reports else 0


if __name__ == "__main__":
    sys.exit(main())
