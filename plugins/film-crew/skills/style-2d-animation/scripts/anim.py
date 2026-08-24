"""Timing. The part that decides whether the drawings read as animation.

Three ideas run through this module.

**Nothing moves linearly.** Linear interpolation is the single loudest tell of
procedural work: real mass takes time to start and time to stop. Every move in
this style carries a curve, and the two that matter most are the two a normal
tweening library does not ship -- ``anticipate`` (wind up against the target
before going) and ``overshoot`` (sail past it and settle back).

**Fast motion is not drawn sharply.** When a limb crosses more ground in one
frame than its own width, a clean in-between reads as a teleport. ``smear``
returns the stretched, dragged in-between that a 2D animator would draw
instead -- and returns ``None`` when the move is too small to earn one, because
a smear on a slow move looks like a bug.

**Impacts ring.** ``squash_stretch`` is a decaying oscillation, not a step: a
landing compresses, rebounds past its rest shape, and settles.

Deterministic: no clocks, no unseeded randomness, no module state.
"""

from __future__ import annotations

import math

import poses as _poses
import rig as _rig

__all__ = ["ease", "EASES", "squash_stretch", "smear", "track"]

#: Seconds the head trails the chest through a keyed change. Two and a half
#: frames at 30fps -- the follow-through rule in the rig spec.
HEAD_LAG = 0.083

#: Wind-up lengths at 30 fps: ``(frames to the peak, frames held at the peak)``.
#: Re-exported from :mod:`poses` so a caller timing a move has one place to
#: look. The hold is the part everyone leaves out and the part that makes it
#: read as this style rather than as a motion tween.
ANTICIPATION_FRAMES = _poses.ANTICIPATION_FRAMES


# ------------------------------------------------------------------ easing ---


def _linear(t: float) -> float:
    return t


def _in(t: float) -> float:
    """Slow out of the pose, accelerating. Weight starting to move."""
    return t * t * t


def _out(t: float) -> float:
    """Arrives fast and decelerates into the pose. The default for most moves."""
    u = 1.0 - t
    return 1.0 - u * u * u


def _inout(t: float) -> float:
    return 4.0 * t * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _snap(t: float) -> float:
    """Almost a cut: holds, then crosses in the last fifth. Limited animation
    lives on this curve -- it is what buys the held drawings their stillness."""
    if t < 0.78:
        return 0.06 * (t / 0.78)
    u = (t - 0.78) / 0.22
    return 0.06 + 0.94 * (1.0 - (1.0 - u) ** 2)


def _anticipate(t: float) -> float:
    """Against the target first, **hold there**, then away.

    Nothing fast may start without one. The hold is not a detail: a wind-up
    that eases straight into the release reads as motion-tweened explainer
    animation, where this style wants a freeze and then a snap.

    Dips to -0.18 by t=0.16, sits there until t=0.30, then departs on the
    overshoot-settle profile. See :data:`ANTICIPATION_FRAMES` for how long the
    first two beats should last at 30 fps.
    """
    depth, wind, hold = 0.18, 0.16, 0.14
    if t < wind:
        u = t / wind
        return -depth * u * u * (3.0 - 2.0 * u)
    if t < wind + hold:
        return -depth
    s = (t - wind - hold) / (1.0 - wind - hold)
    return -depth + (1.0 + depth) * _overshoot(s)


def _overshoot(t: float, overshoot: float = 0.12, settle_decay: float = 3.5) -> float:
    """Fast departure, past the target by 12%, then a decaying settle.

    **This is the house curve.** A move from A to B in this style is not an
    ease-in-out; it leaves fast, sails past, and rings down onto the pose. It
    is what ``ease`` falls back to for an unknown name and what :func:`track`
    uses when a key does not say otherwise.
    """
    if t < 0.6:
        # Guarded for the same reason `_elastic` below guards `t <= 0.0`: an
        # eased value arrives as a difference of floats and can sit a hair
        # under zero, which `math.sqrt` rejects outright.
        return math.sqrt(max(0.0, t) / 0.6) * (1.0 + overshoot)
    s = (t - 0.6) / 0.4
    return 1.0 + overshoot * math.cos(s * math.pi) * math.exp(-settle_decay * s)


def _elastic(t: float) -> float:
    """Rubbery: several diminishing wobbles past the target. Use sparingly --
    it is a gag curve, not a walk curve."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    p = 0.30
    return (2.0 ** (-10.0 * t)) * math.sin((t - p / 4.0) * (2.0 * math.pi) / p) + 1.0


def _bounce(t: float) -> float:
    """Ballistic: hits, rebounds smaller, hits again. Reads as hard ground."""
    n, d = 7.5625, 2.75
    if t < 1.0 / d:
        return n * t * t
    if t < 2.0 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def _hold(t: float) -> float:
    """No motion at all until the very end, then a cut. A held drawing."""
    return 0.0 if t < 1.0 else 1.0


EASES = {
    "linear": _linear,
    "in": _in,
    "out": _out,
    "inout": _inout,
    "snap": _snap,
    "anticipate": _anticipate,
    "overshoot": _overshoot,
    "elastic": _elastic,
    "bounce": _bounce,
    "hold": _hold,
    # a few aliases the storyboards are likely to reach for
    "ease": _inout,
    "ease-in": _in,
    "ease-out": _out,
    "ease-inout": _inout,
    "easein": _in,
    "easeout": _out,
    "cut": _hold,
    "none": _linear,
    "back": _overshoot,
    "anticipation": _anticipate,
}


def ease(name: str, t: float) -> float:
    """Shape ``t`` in ``[0, 1]``.

    **The default is ``overshoot``, not ``inout``.** In this style a move
    departs fast, passes its target by about 12% and settles back; straight
    linear interpolation between two poses is visually indefensible, and a
    symmetric ease-in-out is only marginally better. Reach for ``overshoot``
    unless there is a reason not to, and for ``anticipate`` on anything fast
    that starts from rest.

    Unknown names fall back to ``overshoot`` rather than raising: a typo in a
    storyboard should cost a nicety, not the render. ``anticipate`` returns
    negative values early and ``overshoot`` exceeds 1 in the middle -- that is
    the entire point of them, so the result is deliberately not clamped.
    """
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    fn = EASES.get(str(name).strip().lower().replace("_", "-"), _overshoot)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return fn(t)


# ------------------------------------------------------------ squash/stretch --

#: Reference squash and stretch, as ``(height, width, contact_frames,
#: settle_frames)`` at 30 fps. Every pair multiplies to about 1: a shape that
#: loses area when it lands reads as deflating, not as compressing. The rig
#: derives width from height (``rig.squash_scale``), so only the height is fed
#: to :func:`squash_stretch`; the width column is here to be checked against.
SQUASH_EVENTS: dict[str, tuple[float, float, int, int]] = {
    "hard_landing": (0.75, 1.30, 2, 4),
    "soft_landing": (0.88, 1.12, 2, 2),
    "crouch": (0.85, 1.15, 5, 4),      # anticipation, held 4-6 frames
    "apex": (1.18, 0.88, 3, 3),        # stretched at the top of a jump
    "pop": (1.20, 0.85, 2, 4),         # startled
}

#: This module is written for 30 fps, like the rest of the plugin.
FPS = 30


def width_for(height: float) -> float:
    """The width that keeps a squash area-preserving. ``0.75 -> 1.33``."""
    return 1.0 / max(1e-6, float(height))


def squash_stretch(v: float = 1.0, *, impact: float | None = None,
                   decay: float | None = None, t: float = 0.0,
                   event: str | None = None) -> float:
    """A value ringing down after a hit.

    ``v``       the rest value (a height, a width, a rig ``squash``)
    ``impact``  peak deviation as a fraction of ``v``: 0.18 is a solid landing
    ``decay``   how fast it dies, per second. 6-10 is cartoon-crisp
    ``t``       seconds since the impact
    ``event``   a key of :data:`SQUASH_EVENTS` -- sets ``impact`` and ``decay``
                from the reference table, so ``squash_stretch(event="hard_landing",
                t=0)`` is exactly 0.75 and it has settled four frames later

    Only the height is produced. The rig's width follows from it and preserves
    area (:func:`rig.squash_scale`), which is why a 0.75 squash draws 1.30 wide.
    """
    if event is not None:
        h, _w, contact, settle = SQUASH_EVENTS[str(event)]
        if impact is None:
            impact = (float(v) - h) / float(v) if v else 0.0
        if decay is None:
            # dead by the end of the settle: e^(-decay * settle_seconds) ~ 0.04
            decay = 3.2 * FPS / max(1.0, float(contact + settle))
    impact = 0.18 if impact is None else float(impact)
    decay = 8.0 if decay is None else float(decay)

    t = float(t)
    if t <= 0.0:
        return float(v) * (1.0 - impact)
    k = math.exp(-decay * t) * math.cos(2.0 * math.pi * 1.35 * t)
    out = float(v) * (1.0 - impact * k)
    lo, hi = float(v) * 0.25, float(v) * 3.0
    if v < 0:
        lo, hi = hi, lo
    return max(min(out, hi), lo) if v >= 0 else min(max(out, hi), lo)


# ------------------------------------------------------------------- smear ---

#: A joint has to travel at least this many degrees between the two poses
#: before a smear is worth drawing.
SMEAR_DEG = 38.0
#: ...or the body has to travel this fraction of its own height.
SMEAR_TRAVEL = 0.15
#: How far the moving shape stretches along its travel, at the two ends of
#: "fast". The perpendicular compresses to the reciprocal, so a 2x stretch is
#: half as wide -- the rig preserves area.
SMEAR_STRETCH = (1.5, 3.0)
#: The body can only lean this far into the move before it reads as falling
#: over; whatever direction is left over is expressed as the stretch axis.
SMEAR_TILT = 14.0


def _travel(a: dict, b: dict) -> tuple[float, float, float]:
    """``(dx, dy, distance)`` between two poses' anchors, in scene units."""
    pa = a.get("at") or (0.0, 0.0)
    pb = b.get("at") or (0.0, 0.0)
    dx, dy = float(pb[0]) - float(pa[0]), float(pb[1]) - float(pa[1])
    return dx, dy, math.hypot(dx, dy)


def _max_joint_delta(a: dict, b: dict) -> float:
    ja, jb = a.get("joints") or {}, b.get("joints") or {}
    worst = 0.0
    for k in set(ja) | set(jb):
        d = abs(_poses._shortest(float(ja.get(k, 0.0)), float(jb.get(k, 0.0))))
        worst = max(worst, d)
    return worst


def smear(pose_a: dict, pose_b: dict, t: float) -> dict | None:
    """A stretched in-between for motion too fast to draw cleanly.

    Returns ``None`` when the two poses are close enough that a normal
    in-between reads fine. A smear on a slow move looks like a rendering fault,
    so refusing is as important as producing one — and a smear never belongs on
    a **held** pose, only between two keys.

    **One frame.** This is not a state to sit in: draw it on the single frame
    between the two keys and be back on a clean drawing next frame. Two
    consecutive smears read as a broken renderer.

    The shape is the classic elongation smear: the body stretches 1.5x to 3x
    along the direction of travel and compresses to the reciprocal across it
    (the rig preserves area), leaning up to :data:`SMEAR_TILT` into the move,
    with the trailing limbs dragged back behind the clean in-between.
    """
    if not pose_a or not pose_b:
        return None
    H = float(pose_a.get("height", _rig.DEFAULT_HEIGHT))
    dx, dy, dist = _travel(pose_a, pose_b)
    swing = _max_joint_delta(pose_a, pose_b)
    if swing < SMEAR_DEG and dist < SMEAR_TRAVEL * H:
        return None

    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    out = _poses.blend(pose_a, pose_b, t)

    # strongest in the middle of the crossing, nothing at either key
    k = math.sin(math.pi * t)
    heat = min(1.0, swing / 180.0 + dist / (0.9 * H))
    lo, hi = SMEAR_STRETCH
    peak = lo + (hi - lo) * heat        # 1.5x at the threshold, 3x flat out
    stretch = 1.0 + (peak - 1.0) * k * heat

    facing = -1.0 if float(out.get("facing", 1)) < 0 else 1.0
    if dist > 1e-9:
        # angle of travel measured off the body's up axis, folded to +/-90:
        # a smear is symmetric, so travelling up and travelling down stretch
        # the same way
        ang = math.degrees(math.atan2(dx * facing, -dy))
        while ang > 90.0:
            ang -= 180.0
        while ang < -90.0:
            ang += 180.0
    else:
        ang = 0.0
    lean = max(-SMEAR_TILT, min(SMEAR_TILT, ang))
    residual = ang - lean
    # what the lean could not absorb decides how much of the stretch lands on
    # the long axis and how much on the short one: +1 tall, -1 wide
    axis = math.cos(math.radians(2.0 * residual))
    out["squash"] = float(out.get("squash", 1.0)) * (stretch ** axis)
    out["tilt"] = float(out.get("tilt", 0.0)) + lean * k * heat

    # trailing limbs: everything that is swinging keeps going a little past
    # where the clean in-between would put it
    ja, jb = pose_a.get("joints") or {}, pose_b.get("joints") or {}
    drag = 0.26 * k * heat
    joints = dict(out.get("joints") or {})
    for name in ("shoulder.l", "shoulder.r", "elbow.l", "elbow.r",
                 "wrist.l", "wrist.r", "hip.l", "hip.r", "knee.l", "knee.r",
                 "ankle.l", "ankle.r", "head", "neck"):
        if name not in joints:
            continue
        step = _poses._shortest(float(ja.get(name, 0.0)), float(jb.get(name, 0.0)))
        joints[name] = joints[name] - step * drag
    out["joints"] = joints
    out["smear"] = True          # so the renderer can skip a shadow if it likes
    return out


# ------------------------------------------------------------------- track ---


def _as_pose(p):
    """A key's ``pose`` may be a pose dict or the name of a cycle."""
    if isinstance(p, str):
        fn = _poses.POSES.get(p)
        return fn() if fn else _poses.stand()
    return p


def track(keys: list[dict], t: float) -> dict:
    """The pose at time ``t`` seconds along a keyframed track.

    ``keys`` is ``[{"t": sec, "pose": {...}, "ease": "overshoot"}, ...]``. The
    ease named on a key governs the approach *to* that key, which is how a
    storyboard reads: "arrive on this pose, overshooting". A key that names no
    ease gets ``overshoot``, because that is the house curve — see :func:`ease`.

    Before the first key and after the last, the track holds -- an actor with
    nothing keyed yet is standing there, not missing.

    The head and neck are re-evaluated ``HEAD_LAG`` seconds in the past, so on
    a direction change the head arrives two to three frames after the chest.
    That lag is most of what sells weight.
    """
    if not keys:
        return _poses.stand()
    ks = sorted(({"t": float(k.get("t", 0.0)),
                  "pose": _as_pose(k.get("pose")),
                  "ease": k.get("ease", "overshoot")} for k in keys),
                key=lambda k: k["t"])
    t = float(t)

    def sample(u: float) -> dict:
        if u <= ks[0]["t"] or len(ks) == 1:
            return ks[0]["pose"]
        if u >= ks[-1]["t"]:
            return ks[-1]["pose"]
        i = 0
        while i + 1 < len(ks) and ks[i + 1]["t"] <= u:
            i += 1
        a, b = ks[i], ks[i + 1]
        span = b["t"] - a["t"]
        f = 0.0 if span <= 0 else (u - a["t"]) / span
        return _poses.blend(a["pose"], b["pose"], ease(b["ease"], f))

    out = dict(sample(t))
    if t > ks[0]["t"] and HEAD_LAG > 0.0:
        late = sample(max(ks[0]["t"], t - HEAD_LAG))
        joints = dict(out.get("joints") or {})
        for name in ("neck", "head"):
            if name in (late.get("joints") or {}):
                joints[name] = float(late["joints"][name])
        out["joints"] = joints
        # the face belongs to the head, so it arrives late too -- and it snaps
        out["face"] = dict(late.get("face") or out.get("face") or {})
    return out


# ------------------------------------------------------------- self-test -----

if __name__ == "__main__":
    import os

    OUT = os.environ.get("RIG_TEST_OUT", "/tmp")
    ok = 0

    def check(label, cond, detail=""):
        global ok
        assert cond, f"FAIL {label} {detail}"
        ok += 1
        print(f"  ok  {label}  {detail}")

    STANDARD = ["linear", "in", "out", "inout", "snap",
                "anticipate", "overshoot", "elastic", "bounce"]

    print("easing endpoints")
    for name in STANDARD + ["hold"]:
        check(f"{name}(0) == 0", ease(name, 0.0) == 0.0, f"{ease(name, 0.0)!r}")
        check(f"{name}(1) == 1", ease(name, 1.0) == 1.0, f"{ease(name, 1.0)!r}")
    check("unknown name falls back to the house curve",
          ease("wibble", 0.42) == ease("overshoot", 0.42), f"{ease('wibble', 0.42):.4f}")
    check("t is clamped", ease("out", -3.0) == 0.0 and ease("out", 9.0) == 1.0)

    print("monotone-ish curves stay inside [0, 1]")
    for name in ("linear", "in", "out", "inout", "snap", "hold"):
        vals = [ease(name, i / 400.0) for i in range(401)]
        check(f"{name} stays in range", min(vals) >= 0.0 and max(vals) <= 1.0,
              f"[{min(vals):.3f}, {max(vals):.3f}]")

    print("the two that matter")
    a = [ease("anticipate", i / 400.0) for i in range(401)]
    early = min(a[:int(401 * 0.28)])
    check("anticipate moves against the target first", early < -0.05,
          f"dips to {early:.4f} at t={a.index(early) / 400.0:.3f}")
    held = [v for i, v in enumerate(a) if 0.17 <= i / 400.0 <= 0.29]
    check("anticipate HOLDS at the peak of the wind-up",
          max(held) - min(held) < 1e-9,
          f"flat at {held[0]:.4f} for {len(held) / 400.0 * 100:.0f}% of the move")
    check("anticipate is back through zero by 40%",
          a[int(401 * 0.40)] > 0.0, f"{a[int(401 * 0.40)]:.4f}")
    check("anticipate still lands exactly", a[-1] == 1.0)

    o = [ease("overshoot", i / 400.0) for i in range(401)]
    peak = max(o)
    check("overshoot passes the target", peak > 1.0,
          f"peaks at {peak:.4f} (+{(peak - 1) * 100:.1f}%)")
    check("overshoot is the specified 12% over", abs(peak - 1.12) < 1e-9, f"{peak:.6f}")
    check("overshoot peaks at t=0.6", abs(o.index(peak) / 400.0 - 0.6) < 0.005,
          f"t={o.index(peak) / 400.0:.3f}")
    check("overshoot departs fast (half way by 15%)", o[int(401 * 0.15)] > 0.5,
          f"{o[int(401 * 0.15)]:.4f} at t=0.15")
    check("overshoot settles: it dips back under the target",
          min(o[int(401 * 0.62):]) < 1.0, f"min {min(o[int(401 * 0.62):]):.4f}")
    check("overshoot rings down (each swing smaller)",
          abs(o[int(401 * 0.80)] - 1.0) < abs(o[int(401 * 0.65)] - 1.0),
          f"{abs(o[int(401 * 0.65)] - 1.0):.4f} -> {abs(o[int(401 * 0.80)] - 1.0):.4f}")
    check("overshoot settles back to exactly 1", o[-1] == 1.0)
    check("overshoot is the default for a key with no ease named",
          track([{"t": 0.0, "pose": _poses.stand(0.0)},
                 {"t": 1.0, "pose": _poses.stand(0.0)}], 0.5) is not None)

    e = [ease("elastic", i / 400.0) for i in range(401)]
    over = [i for i, v in enumerate(e) if v > 1.0]
    under = [i for i, v in enumerate(e) if i > (over[0] if over else 0) and v < 1.0]
    check("elastic wobbles either side of the target",
          bool(over) and bool(under) and max(e) > 1.1,
          f"peaks {max(e):.3f}, then back under at t={min(under) / 400.0:.3f}")
    b = [ease("bounce", i / 400.0) for i in range(401)]
    check("bounce never passes the target", max(b) <= 1.0 + 1e-12, f"max {max(b):.4f}")
    check("bounce rebounds at least three times",
          sum(1 for i in range(1, 400) if b[i] > b[i - 1] and b[i] >= b[i + 1]) >= 3)
    h = [ease("hold", i / 400.0) for i in range(400)]
    check("hold does not move at all", max(h) == 0.0)
    check("snap holds then crosses late", ease("snap", 0.7) < 0.1 < ease("snap", 0.95),
          f"{ease('snap', 0.7):.3f} -> {ease('snap', 0.95):.3f}")

    print("squash_stretch")
    check("t=0 is the moment of impact, fully compressed",
          abs(squash_stretch(10.0, impact=0.3, decay=6.0, t=0.0) - 7.0) < 1e-9,
          f"{squash_stretch(10.0, impact=0.3, decay=6.0, t=0.0):.4f}")
    v = [squash_stretch(10.0, impact=0.30, decay=6.0, t=i / 400.0) for i in range(401)]
    check("compresses on impact", v[1] < 10.0, f"{v[1]:.4f} at t=0.0025")
    check("rebounds past rest", max(v) > 10.0, f"peaks {max(v):.4f}")
    check("settles back", abs(v[-1] - 10.0) < 0.2, f"{v[-1]:.4f} at t=1.0")
    check("deeper impact compresses further",
          squash_stretch(10.0, impact=0.5, decay=6.0, t=0.02)
          < squash_stretch(10.0, impact=0.2, decay=6.0, t=0.02))
    check("faster decay settles sooner",
          abs(squash_stretch(10.0, impact=0.4, decay=14.0, t=0.5) - 10.0)
          < abs(squash_stretch(10.0, impact=0.4, decay=3.0, t=0.5) - 10.0))
    check("never inverts the value",
          squash_stretch(10.0, impact=8.0, decay=0.5, t=0.02) > 0.0,
          f"{squash_stretch(10.0, impact=8.0, decay=0.5, t=0.02):.4f}")

    print("squash_stretch against the reference table")
    for name, (h, w, contact, settle) in SQUASH_EVENTS.items():
        check(f"{name}: the table preserves area", abs(h * w - 1.0) < 0.04,
              f"{h} x {w} = {h * w:.4f}")
        check(f"{name}: width_for matches the table", abs(width_for(h) - w) < 0.035,
              f"width_for({h}) = {width_for(h):.4f} vs {w}")
        check(f"{name}: rig agrees on the width",
              abs(_rig.squash_scale(h)[0] - w) < 0.035,
              f"rig says {_rig.squash_scale(h)[0]:.4f}")
        hit = squash_stretch(1.0, event=name, t=0.0)
        check(f"{name}: t=0 is exactly the table height", abs(hit - h) < 1e-9,
              f"{hit:.4f}")
        gone = squash_stretch(1.0, event=name, t=(contact + settle) / FPS)
        check(f"{name}: settled within {contact + settle} frames",
              abs(gone - 1.0) < 0.06,
              f"{gone:.4f} at frame {contact + settle} ({(contact + settle) / FPS * 1000:.0f} ms)")
        peaked = max(abs(squash_stretch(1.0, event=name, t=i / 600.0) - 1.0)
                     for i in range(601))
        check(f"{name}: never rings louder than the impact",
              peaked <= abs(h - 1.0) + 1e-9, f"peak deviation {peaked:.4f}")
    check("stretch events go the other way",
          squash_stretch(1.0, event="apex", t=0.0) > 1.0
          and squash_stretch(1.0, event="pop", t=0.0) > 1.0)
    check("width_for is an exact reciprocal",
          all(abs(width_for(h) * h - 1.0) < 1e-9 for h in (0.75, 0.85, 1.0, 1.18, 1.2)))
    check("the crouch is held 4-6 frames", 4 <= SQUASH_EVENTS["crouch"][2] <= 6,
          f"{SQUASH_EVENTS['crouch'][2]} frames at {FPS} fps")

    print("anticipation timing")
    for name, (wind, hold) in ANTICIPATION_FRAMES.items():
        check(f"{name}: wind-up is a sane length at {FPS} fps", 2 <= wind <= 14,
              f"{wind} frames ({wind / FPS * 1000:.0f} ms)")
        check(f"{name}: the peak is HELD 2-6 frames", 2 <= hold <= 6,
              f"{hold} frames")
    check("head turn winds 2-4 frames", 2 <= ANTICIPATION_FRAMES["head_turn"][0] <= 4)
    check("a jump crouches 6-8 frames", 6 <= ANTICIPATION_FRAMES["jump"][0] <= 8)
    check("a big reaction winds 10-14 frames",
          10 <= ANTICIPATION_FRAMES["reaction"][0] <= 14)
    check("a run start winds 4-6 frames",
          4 <= ANTICIPATION_FRAMES["run_start"][0] <= 6)

    print("smear")
    slow_a, slow_b = _poses.stand(0.0), _poses.stand(0.02)
    check("no smear for a near-identical pair", smear(slow_a, slow_b, 0.5) is None)
    check("no smear for a genuinely held pose",
          smear(_poses.stand(0.3), _poses.stand(0.3), 0.5) is None)
    fast_a = _poses.react(0.0, kind="shock")
    fast_b = _poses.react(1.0, kind="shock")
    sm = smear(fast_a, fast_b, 0.5)
    check("smear for a fast one", sm is not None,
          f"{_max_joint_delta(fast_a, fast_b):.1f} deg between the keys")
    check("smear is a valid pose", all(k in sm for k in ("joints", "at", "face")))
    check("smear is flagged", sm.get("smear") is True)
    check("smear drags the limbs off the clean in-between",
          any(abs(sm["joints"][k] - _poses.blend(fast_a, fast_b, 0.5)["joints"][k]) > 1.0
              for k in sm["joints"]))
    ends = (smear(fast_a, fast_b, 0.0), smear(fast_a, fast_b, 1.0))
    clean = (_poses.blend(fast_a, fast_b, 0.0), _poses.blend(fast_a, fast_b, 1.0))
    check("smear vanishes at both keys",
          all(abs(s["joints"][k] - c["joints"][k]) < 1e-6
              for s, c in zip(ends, clean) for k in s["joints"]))
    check("and carries no stretch at either key",
          all(abs(s["squash"] - c["squash"]) < 1e-9
              for s, c in zip(ends, clean)))

    print("smear geometry: stretch along travel, compress across it")
    H = _rig.DEFAULT_HEIGHT
    up_a = _poses.stand(0.0, at=(10.0, 20.0))
    up_b = _poses.stand(0.0, at=(10.0, 20.0 - 0.60 * H))
    sv = smear(up_a, up_b, 0.5)
    lo, hi = SMEAR_STRETCH
    check("a vertical whip stretches 1.5-3x along the body",
          lo - 0.01 <= sv["squash"] <= hi + 0.01, f"squash {sv['squash']:.4f}")
    check("...which draws it narrower by the same factor",
          abs(_rig.squash_scale(sv["squash"])[0] * sv["squash"] - 1.0) < 1e-9,
          f"{_rig.squash_scale(sv['squash'])[0]:.4f} wide")
    check("...and does not tilt (nothing to lean into)",
          abs(sv["tilt"] - up_a.get("tilt", 0.0)) < 1e-9, f"{sv['tilt']:.4f}")

    side_a = _poses.stand(0.0, at=(10.0, 20.0))
    side_b = _poses.stand(0.0, at=(10.0 + 0.60 * H, 20.0))
    sh = smear(side_a, side_b, 0.5)
    check("a horizontal whip goes WIDE instead",
          _rig.squash_scale(sh["squash"])[0] > 1.6,
          f"{_rig.squash_scale(sh['squash'])[0]:.4f}x wide, "
          f"{sh['squash']:.4f}x tall")
    check("...compressing across the travel to about half",
          0.40 <= sh["squash"] <= 0.62, f"{sh['squash']:.4f}")
    check("...and leans into the direction of travel",
          0.0 < sh["tilt"] <= SMEAR_TILT + 1e-9, f"{sh['tilt']:.2f} deg")
    back_b = _poses.stand(0.0, at=(10.0 - 0.60 * H, 20.0))
    sb = smear(side_a, back_b, 0.5)
    check("...the other way when it travels the other way",
          sb["tilt"] < 0.0 and abs(sb["tilt"] + sh["tilt"]) < 1e-9,
          f"{sb['tilt']:.2f} deg")
    check("the lean is never more than SMEAR_TILT",
          all(abs(smear(side_a,
                        _poses.stand(0.0, at=(10.0 + math.cos(th) * 0.6 * H,
                                              20.0 + math.sin(th) * 0.6 * H)),
                        0.5)["tilt"]) <= SMEAR_TILT + 1e-9
              for th in (i / 24.0 * 2.0 * math.pi for i in range(24))),
          f"cap {SMEAR_TILT} deg, checked all round the clock")
    check("a mirrored actor leans the same way on screen",
          smear(dict(side_a, facing=-1), dict(side_b, facing=-1), 0.5)["tilt"]
          == -sh["tilt"],
          "tilt is body-local, so it flips with the mirror")
    check("the smear peaks mid-crossing, not at the ends",
          smear(up_a, up_b, 0.5)["squash"] > smear(up_a, up_b, 0.15)["squash"]
          > smear(up_a, up_b, 0.0)["squash"])
    check("smear is deterministic",
          smear(fast_a, fast_b, 0.5) == smear(fast_a, fast_b, 0.5))
    jump_a = _poses.stand(0.0, at=(10.0, 20.0))
    jump_b = _poses.stand(0.0, at=(10.0, 12.0))
    sj = smear(jump_a, jump_b, 0.5)
    check("a big vertical move smears even with identical joints",
          sj is not None and sj["squash"] > 1.05, f"squash {sj['squash']:.4f}")

    print("track")
    keys = [
        {"t": 0.0, "pose": _poses.stand(0.0), "ease": "out"},
        {"t": 0.5, "pose": _poses.react(1.0, kind="shock"), "ease": "anticipate"},
        {"t": 1.2, "pose": _poses.react(1.0, kind="brace"), "ease": "overshoot"},
    ]
    check("holds before the first key",
          track(keys, -5.0)["joints"] == keys[0]["pose"]["joints"])
    check("holds after the last key",
          track(keys, 99.0)["joints"] == keys[-1]["pose"]["joints"])
    check("the body lands on a key", all(
        abs(track(keys, 1.2)["joints"][k] - keys[-1]["pose"]["joints"][k]) < 1e-6
        for k in keys[-1]["pose"]["joints"] if k not in ("head", "neck")))
    check("the head is still catching up on the key frame", any(
        abs(track(keys, 1.2)["joints"][k] - keys[-1]["pose"]["joints"][k]) > 0.05
        for k in ("head", "neck")),
        f"head {track(keys, 1.2)['joints']['head']:.2f} vs "
        f"{keys[-1]['pose']['joints']['head']:.2f}")
    check("and lands one lag later", all(
        abs(track(keys, 1.2 + HEAD_LAG)["joints"][k] - keys[-1]["pose"]["joints"][k]) < 1e-6
        for k in ("head", "neck")))
    mid = track(keys, 0.25)
    check("moves between keys", mid["joints"] != keys[0]["pose"]["joints"])
    check("track is deterministic", track(keys, 0.37) == track(keys, 0.37))
    check("empty track still returns a pose", "joints" in track([], 1.0))
    check("named poses resolve", "joints" in track([{"t": 0.0, "pose": "walk"}], 0.0))

    # the head arrives after the chest
    lagging = 0
    for i in range(1, 60):
        u = i / 60.0
        cur = track(keys, u)
        raw = _poses.blend(keys[0]["pose"], keys[1]["pose"],
                           ease(keys[1]["ease"], min(1.0, u / 0.5)))
        if abs(cur["joints"]["head"] - raw["joints"]["head"]) > 0.05:
            lagging += 1
    check("the head trails the chest through a keyed change", lagging > 25,
          f"{lagging}/59 sampled frames behind")

    # ---- a picture of the curves, because numbers are not a shape ----------
    from PIL import Image, ImageDraw

    names = STANDARD + ["hold"]
    cw, chh, pad = 190, 150, 16
    cols = 5
    rows = (len(names) + cols - 1) // cols
    img = Image.new("RGB", (cols * (cw + pad) + pad, rows * (chh + pad + 18) + pad),
                    (247, 244, 238))
    dd = ImageDraw.Draw(img)
    for i, name in enumerate(names):
        ox = pad + (i % cols) * (cw + pad)
        oy = pad + 18 + (i // cols) * (chh + pad + 18)
        dd.rectangle([ox, oy, ox + cw, oy + chh], fill=(255, 253, 249),
                     outline=(206, 200, 190))
        top, bot = oy + 26, oy + chh - 26     # room for the over/undershoot
        dd.line([ox, bot, ox + cw, bot], fill=(224, 218, 208))
        dd.line([ox, top, ox + cw, top], fill=(224, 218, 208))
        pts = []
        for k in range(cw + 1):
            u = k / cw
            pts.append((ox + k, bot - ease(name, u) * (bot - top)))
        dd.line(pts, fill=(212, 66, 48), width=3, joint="curve")
        dd.text((ox + 4, oy - 14), name, fill=(40, 38, 36))
    path = os.path.join(OUT, "anim_curves.png")
    img.save(path)

    print(f"\n{ok} checks passed")
    print(f"wrote {path}")
