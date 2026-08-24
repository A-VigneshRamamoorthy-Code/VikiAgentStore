"""Procedural pose functions — the cycles and the acting.

Every cycle here is a **phase function**, never a keyframe table. `phase` runs
`0..1` and wraps: `walk(0.0)` and `walk(1.0)` are the same drawing, or the
cycle pops once per stride. A phase function costs nothing to store, cannot
desync from anything, and retimes for free.

The gait is built the only way that keeps a planted foot planted: the **feet
are placed in scene space first** and the legs are solved to reach them with
two-bone IK. Authoring hip and knee angles directly and hoping is what makes
procedural walks skate. The IK result is then written back out as joint angles,
so the pose stays a pose — angles only, blendable, mirrorable, rescalable.

    stance   the foot's scene x is *constant*; the pelvis travels over it
    swing    a Hermite arc whose end tangents match the stance velocity, so
             the foot is momentarily still in scene space at toe-off and at
             heel-strike — no scrub at either boundary

Arms oppose legs, the pelvis rises twice per stride, and the head is evaluated
a couple of frames behind the chest so it lags into every direction change.

A walking pose's ``at`` already contains its own travel, so playing the phase
forward walks the character across the scene. A renderer that would rather own
the trajectory has two ways not to fight it: pass ``travel=False`` for a
treadmill cycle, or advance its own ``at`` at exactly ``stride_units(name, h)``
per cycle. Any other rate reintroduces the foot slide the IK just removed.
"""

from __future__ import annotations

import math

import rig
from rig import BONES, DEPTH, HIP_HALF, SOLE, signed_angle

H_DEF = rig.DEFAULT_HEIGHT
LEG = BONES["thigh"] + BONES["shin"]
GROUND = 44.0  # the standard street ground line

DOWN = (0.0, 1.0)
FWD = (1.0, 0.0)

#: How far behind the chest the head is evaluated, as a fraction of a cycle.
#: ~2.4 frames at 30 fps on a one-second cycle. This is follow-through, and it
#: is most of what sells weight.
HEAD_LAG = 0.08

#: This plugin renders at **30 fps**, so "on twos" is 15 drawings a second.
FPS = 30

#: An idle cycle is three seconds — one slow breath. Drive :func:`stand` at
#: ``1 / IDLE_CYCLE_S`` cycles per second and the blink lands every 90 frames,
#: inside the 72-96 the style calls for.
IDLE_CYCLE_S = 3.0
BLINK_FRAMES = 4                              # four frames shut, at 30 fps
BLINK_AT = 0.90                               # where in the cycle it happens
BLINK_SPAN = BLINK_FRAMES / (IDLE_CYCLE_S * FPS)

#: Wind-up lengths at 30 fps: ``(frames to the peak, frames held at the peak)``.
#: The hold is the whole point. A wind-up that eases straight into the release
#: reads as motion-tweened explainer animation; the freeze before the snap is
#: what makes it land.
ANTICIPATION_FRAMES = {
    "head_turn": (3, 2),      # 2-4 frames
    "jump": (7, 3),           # 6-8, as a crouch-squash
    "reaction": (12, 4),      # 10-14 for a big comedic take
    "run_start": (5, 2),      # 4-6
}


# ------------------------------------------------------------------ maths ----


def _smooth(t: float) -> float:
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


def _key_curve(p: float, keys) -> float:
    """Smoothly interpolate a wrapping table of ``(phase, value)`` keys.

    The table is closed by repeating the first value at 1.0, so anything built
    from it is continuous across the wrap by construction.
    """
    p = p % 1.0
    ks = list(keys)
    if ks[-1][0] < 1.0:
        ks.append((1.0, ks[0][1]))
    for i in range(len(ks) - 1):
        p0, v0 = ks[i]
        p1, v1 = ks[i + 1]
        if p0 <= p <= p1:
            if p1 - p0 < 1e-9:
                return v1
            return v0 + (v1 - v0) * _smooth((p - p0) / (p1 - p0))
    return ks[-1][1]


def _ik2(hip, target, a: float, b: float):
    """Two-bone IK. Returns ``(thigh_dir, shin_dir)`` with the knee forward.

    The target is clamped into reach rather than the bones being stretched —
    a rig never breaks its own bone lengths.
    """
    dx, dy = target[0] - hip[0], target[1] - hip[1]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return (0.0, 1.0), (0.0, 1.0)
    u = (dx / d, dy / d)
    d = min(max(d, abs(a - b) + 1e-4), (a + b) * 0.9995)
    cos_a = (a * a + d * d - b * b) / (2.0 * a * d)
    alpha = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    thigh = rig._rot(u, -alpha)            # negative swings the knee forward
    knee = (hip[0] + thigh[0] * a, hip[1] + thigh[1] * a)
    shin = rig._norm((target[0] - knee[0], target[1] - knee[1]))
    return thigh, shin


def _leg(side: str, ankle, toe_deg: float, H: float, squash: float = 1.0,
         tilt: float = 0.0) -> dict:
    """Joint angles that put ``side``'s ankle at ``ankle`` (pelvis-relative
    scene units) with the shoe pointing ``toe_deg`` below horizontal.

    ``squash`` and ``tilt`` are undone first. The rig applies both after
    solving, about the pelvis, so a squashed or leaning character whose legs
    were solved naively would drag its own feet off their marks. Solving in
    pre-transform space is what keeps a planted foot planted.
    """
    sgn = 1.0 if side == "r" else -1.0
    foot = rig._rot(FWD, toe_deg)
    if abs(tilt) > 1e-9:
        ankle = rig._rot(ankle, -tilt)
        foot = rig._rot(foot, -tilt)
    if abs(squash - 1.0) > 1e-9:
        sx, sy = rig.squash_scale(squash)
        ankle = (ankle[0] / sx, ankle[1] / sy)
        foot = rig._norm((foot[0] / sx, foot[1] / sy))
    hip = (sgn * HIP_HALF * DEPTH * H, 0.0)
    thigh, shin = _ik2(hip, ankle, BONES["thigh"] * H, BONES["shin"] * H)
    return {
        "hip." + side: signed_angle(DOWN, thigh),
        "knee." + side: signed_angle(thigh, shin),
        "ankle." + side: signed_angle(shin, foot),
    }


def _max_pelvis(H: float, feet, squash: float = 1.0) -> float:
    """Highest the pelvis can sit, in scene units above the ground, with those
    foot ``x`` offsets planted. Reaching past this makes the IK clamp and the
    character lifts off the floor -- a crouch that anticipates upward has to
    stop here."""
    reach = (BONES["thigh"] + BONES["shin"]) * H * 0.985
    sx, sy = rig.squash_scale(squash)
    best = None
    for side, fx in feet.items():
        dx = fx / sx - (1.0 if side == "r" else -1.0) * HIP_HALF * DEPTH * H
        y = math.sqrt(max(0.0, reach * reach - dx * dx)) * sy
        best = y if best is None else min(best, y)
    return (best or 0.0) + SOLE * H


def _pose(H, at, facing, joints, face, squash=1.0, tilt=0.0) -> dict:
    return {
        "at": [float(at[0]), float(at[1])],
        "facing": 1 if facing >= 0 else -1,
        "height": float(H),
        "squash": float(squash),
        "tilt": float(tilt),
        "joints": {k: float(v) for k, v in joints.items()},
        "face": dict(face),
    }


def _stage(kw, hip_h: float, H: float):
    """Resolve where the character is standing.

    Accepts ``ground=`` (a ground line) or ``at=`` (a pelvis position, as the
    storyboard writes it) and returns ``(x, ground_y)``.
    """
    at = kw.get("at")
    if kw.get("ground") is not None:
        g = float(kw["ground"])
        x = float(at[0]) if at is not None else float(kw.get("x", 50.0))
    elif at is not None:
        x, g = float(at[0]), float(at[1]) + hip_h * H
    else:
        x, g = float(kw.get("x", 50.0)), GROUND
    return x, g


def _face(**kw) -> dict:
    f = {"brow": 0.0, "eyes": "open", "mouth": "line", "look": [0.25, 0.0]}
    f.update({k: v for k, v in kw.items() if v is not None})
    return f


def _idle(phase: float):
    """Breath and blink for a held pose. Returns ``(breath, blink)``.

    Most of any shot in this style is a character *holding* a drawing, and a
    hold with nothing moving in it reads as a dropped frame rather than as a
    beat. One slow breath and one blink per cycle is all it takes to keep a
    held pose alive.
    """
    p = phase % 1.0
    return math.sin(2.0 * math.pi * p), (BLINK_AT <= p < BLINK_AT + BLINK_SPAN)


def _windup(t: float, *, wind: float = 0.28, hold: float = 0.12,
            depth: float = 0.20, overshoot: float = 0.12,
            decay: float = 3.5) -> float:
    """The house move, as one curve: ``0 -> -depth -> hold -> 1 (+overshoot)``.

    Three beats, and every one of them matters:

    * **anticipation** — the pose moves *against* its target first,
    * **the hold** — and then stops dead there for a few frames,
    * **the release** — fast departure, past the target by ``overshoot``, then
      a decaying settle onto it.

    ``_windup(0) == 0`` and ``_windup(1) == 1`` exactly, so it is safe to key.
    See :data:`ANTICIPATION_FRAMES` for how long the first two beats run at
    30 fps.
    """
    if t <= 0.0:
        return 0.0
    if t < wind:
        return -depth * _smooth(t / wind)
    if t < wind + hold:
        return -depth                       # the freeze before the snap
    span = max(1e-6, 1.0 - wind - hold)
    s = (t - wind - hold) / span
    if s >= 1.0:
        return 1.0
    o = overshoot / (1.0 + depth)           # so the peak is exactly 1+overshoot
    if s < 0.6:
        base = math.sqrt(s / 0.6) * (1.0 + o)
    else:
        r = (s - 0.6) / 0.4
        base = 1.0 + o * math.cos(r * math.pi) * math.exp(-decay * r)
    return -depth + (1.0 + depth) * base


# ------------------------------------------------------------------- gait ----


def _foot_x(p: float, stride: float, duty: float, front: float) -> float:
    """Pelvis-relative x of one foot at leg-phase ``p``.

    Stance is a straight line of slope ``-stride``, which exactly cancels the
    pelvis' forward travel — that cancellation *is* the planted foot. Swing is
    a Hermite whose end tangents match, so the foot is momentarily stationary
    in scene space as it lifts and as it lands.
    """
    travel = stride * duty
    a_f, a_b = travel * front, travel * (1.0 - front)
    if p < duty:
        return a_f - stride * p
    u = (p - duty) / (1.0 - duty)
    m = -stride * (1.0 - duty)
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * -a_b + (u3 - 2 * u2 + u) * m
            + (-2 * u3 + 3 * u2) * a_f + (u3 - u2) * m)


def _gait(phase, *, H, stride, duty, front, hip_h, bob, bob_peak, lift,
          heel_lift, toe_keys, squash=1.0):
    """The legs and the pelvis for one gait. Returns ``(dx, dy, joints)`` where
    ``dx`` is forward travel and ``dy`` the pelvis bob, both scene units."""
    raw, phase = phase, phase % 1.0
    stride_u, lift_u = stride * H, lift * H
    # twice per stride: up over the planted leg, down through the pass
    bob_y = bob * H * math.cos(4.0 * math.pi * (phase - bob_peak))
    ph = hip_h * H + bob_y          # pelvis height above the ground
    joints = {}
    for side, off in (("r", 0.0), ("l", 0.5)):
        p = (phase + off) % 1.0
        fx = _foot_x(p, stride_u, duty, front)
        toe = _key_curve(p, toe_keys)
        if p < duty:
            # the heel peels off through the back of stance, which is what
            # lets the leg reach without the hip having to sink
            up = heel_lift * H * _smooth((p - duty * 0.62) / (duty * 0.38))
        else:
            u = (p - duty) / (1.0 - duty)
            up = (heel_lift * H * (1.0 - _smooth(u / 0.30))
                  + lift_u * math.sin(math.pi * u ** 0.85))
        joints.update(_leg(side, (fx, ph - SOLE * H - up), toe, H, squash))
    return stride_u * raw, -bob_y, joints


WALK = dict(stride=0.58, duty=0.60, front=0.45, hip_h=0.91 * LEG + SOLE,
            bob=0.012, bob_peak=0.30, lift=0.075, heel_lift=0.030,
            toe_keys=[(0.00, -14.0), (0.12, 0.0), (0.45, 2.0), (0.60, 30.0),
                      (0.70, 6.0), (0.86, -18.0)])

RUN = dict(stride=1.00, duty=0.38, front=0.35, hip_h=0.85 * LEG + SOLE,
           bob=0.026, bob_peak=0.44, lift=0.150, heel_lift=0.090,
           toe_keys=[(0.00, -6.0), (0.10, 6.0), (0.30, 26.0), (0.38, 44.0),
                     (0.52, 2.0), (0.80, -16.0)])

SCRAMBLE = dict(stride=0.72, duty=0.40, front=0.38, hip_h=0.83 * LEG + SOLE,
                bob=0.030, bob_peak=0.44, lift=0.185, heel_lift=0.080,
                toe_keys=[(0.00, -10.0), (0.12, 8.0), (0.30, 30.0), (0.40, 50.0),
                          (0.55, -4.0), (0.82, -20.0)])


def _torso(phase: float, lean: float, sway: float) -> float:
    """Spine angle. Positive leans forward, and it sways once per step."""
    return lean + sway * math.cos(4.0 * math.pi * phase)


def _head_lag(phase: float, lean: float, sway: float, lag: float = HEAD_LAG):
    """Neck and head angles that hold the head up but *late*.

    Absolute head tilt ends up as ``spine(now) - spine(then)``, so the head is
    always a couple of frames behind the chest — follow-through, for free.
    """
    late = _torso(phase - lag, lean, sway)
    return -late * 0.62, -late * 0.38


def _arms(phase, *, swing, elbow, elbow_swing, lag=0.05):
    """Arms oppose legs: the right arm is back when the right leg is forward."""
    s = math.cos(2.0 * math.pi * phase)
    e = math.cos(2.0 * math.pi * (phase - lag))
    return {
        "shoulder.r": swing * s,
        "shoulder.l": -swing * s,
        "elbow.r": -(elbow + elbow_swing * max(0.0, -e)),
        "elbow.l": -(elbow + elbow_swing * max(0.0, e)),
        "wrist.r": -6.0 - 5.0 * s,
        "wrist.l": -6.0 + 5.0 * s,
    }


# ------------------------------------------------------------- the cycles ----


def stand(phase: float = 0.0, **kw) -> dict:
    """Idle: breathing, a slow weight shift, and a blink. Never truly still —
    a character frozen on a held drawing reads as a bug, not as a hold.

    Deliberately **asymmetrical**, and that is not decoration. A mirrored idle
    is one of the loudest tells of a rig: the weight sits on the right leg, the
    left foot is back and turned out, the right hand hangs lower than the left,
    and the head is off-axis by four degrees. Contrapposto, in other words.

    One cycle is :data:`IDLE_CYCLE_S` seconds. Driven at that rate the blink
    lands every 90 frames — inside the 72-96 window the style wants. Pass
    ``blink=False`` for a character who must not blink on this beat.
    """
    H = float(kw.get("height", H_DEF))
    hip_h = rig.PELVIS_TO_SOLE
    x, g = _stage(kw, hip_h, H)
    phase = phase % 1.0

    breath, blinking = _idle(phase)
    shift = math.sin(2.0 * math.pi * (phase * 0.5))     # long, lazy weight shift
    ph = hip_h * H + 0.004 * H * breath
    dx = 0.010 * H * shift

    # weight on the right leg: it is nearly under the pelvis and nearly
    # straight, while the left is back, turned out, and idling
    joints = {}
    joints.update(_leg("r", (0.028 * H - dx, ph - SOLE * H), -1.0, H))
    joints.update(_leg("l", (-0.082 * H - dx, ph - SOLE * H), 9.0, H))
    lean = 2.0 + 0.8 * breath
    neck, head = _head_lag(phase, 2.0, 0.8, lag=0.10)
    joints.update({
        "spine": lean, "neck": neck + 0.6 * breath, "head": head + 4.0,
        # the right arm hangs straighter, so that hand sits lower
        "shoulder.r": -3.0 - 2.0 * breath, "elbow.r": -8.0 - 3.0 * breath,
        "shoulder.l": 7.0 + 2.0 * breath, "elbow.l": -30.0 - 3.0 * breath,
        "wrist.r": -3.0, "wrist.l": 7.0,
    })
    blink = kw.get("blink", True) and blinking
    face = _face(eyes="shut" if blink else kw.get("eyes"),
                 mouth=kw.get("mouth"), brow=kw.get("brow"),
                 look=kw.get("look", [0.25, 0.0]))
    return _pose(H, (x + dx, g - ph), kw.get("facing", 1), joints, face)


def _cycle(phase, params, *, swing, elbow, elbow_swing, lean, sway, kw,
           face=None, extra=None, squash=1.0):
    H = float(kw.get("height", H_DEF))
    x, g = _stage(kw, params["hip_h"], H)
    dx, dy, joints = _gait(phase, H=H, squash=squash, **params)
    if not kw.get("travel", True):
        dx = 0.0            # treadmill: the set scrolls instead
    cyc = phase % 1.0       # everything but the travel is periodic, exactly
    joints.update(_arms(cyc, swing=swing, elbow=elbow, elbow_swing=elbow_swing))
    neck, head = _head_lag(cyc, lean, sway)
    joints.update({"spine": _torso(cyc, lean, sway), "neck": neck, "head": head})
    if extra:
        joints.update(extra)
    return _pose(H, (x + dx, g - params["hip_h"] * H + dy),
                 kw.get("facing", 1), joints, face or _face(), squash=squash)


def walk(phase: float = 0.0, **kw) -> dict:
    """One full stride per phase. Two steps, one bob cycle per step."""
    return _cycle(phase, WALK, swing=19.0, elbow=20.0, elbow_swing=16.0,
                  lean=3.0, sway=1.4, kw=kw,
                  face=_face(eyes=kw.get("eyes"), mouth=kw.get("mouth"),
                             brow=kw.get("brow"), look=kw.get("look")))


def run(phase: float = 0.0, **kw) -> dict:
    """Longer stride, a flight phase, a real forward lean, arms driving."""
    return _cycle(phase, RUN, swing=42.0, elbow=78.0, elbow_swing=26.0,
                  lean=15.0, sway=2.2, kw=kw,
                  face=_face(brow=kw.get("brow", "strain"), eyes=kw.get("eyes", "squint"),
                             mouth=kw.get("mouth", "open"), look=kw.get("look", [0.5, 0.0])))


def panic(phase: float = 0.0, **kw) -> dict:
    """A run with the arms flung up and back, and no dignity left in the spine."""
    f = 2.0 * math.pi * (phase % 1.0)
    flail = 14.0 * math.sin(3.0 * f)
    # Both arms trail up and behind. On these proportions the shoulder sits
    # slightly forward of the skull, so an arm anywhere near vertical draws a
    # sleeve straight across the face -- and the face is the whole gag.
    extra = {
        "shoulder.r": -246.0 + flail, "elbow.r": -18.0 - 14.0 * math.cos(3.0 * f),
        "shoulder.l": -232.0 - flail, "elbow.l": -24.0 + 14.0 * math.cos(3.0 * f),
        "wrist.r": 12.0 * math.sin(5.0 * f), "wrist.l": -12.0 * math.sin(5.0 * f),
    }
    p = _cycle(phase, SCRAMBLE, swing=0.0, elbow=0.0, elbow_swing=0.0,
               lean=9.0, sway=3.0, kw=kw, extra=extra,
               squash=1.0 + 0.02 * math.sin(4.0 * f),
               face=_face(brow=kw.get("brow", "surprised"), eyes=kw.get("eyes", "wide"),
                          mouth=kw.get("mouth", "gasp"), look=kw.get("look", [0.55, -0.3])))
    p["joints"]["head"] += 6.0 * math.sin(2.0 * f)
    return p


def drive(phase: float = 0.0, **kw) -> dict:
    """Seated, hands at ten and two, riding the road surface.

    Seated poses ignore the ground: ``at`` is the pelvis, on the seat.
    """
    H = float(kw.get("height", H_DEF))
    at = kw.get("at") or (50.0, GROUND - 0.34 * H)
    f = 2.0 * math.pi * (phase % 1.0)
    jog = math.sin(f * 3.0) * 0.5 + math.sin(f * 7.0) * 0.25   # road buzz
    steer = math.sin(f) * float(kw.get("steer", 1.0))

    joints = {
        "spine": -4.0 + 0.8 * jog, "neck": 5.0 - 0.5 * jog, "head": 1.0 - 0.4 * jog,
        "shoulder.r": -58.0 - 4.0 * steer, "elbow.r": -46.0 + 8.0 * steer,
        "wrist.r": -8.0,
        "shoulder.l": -50.0 + 4.0 * steer, "elbow.l": -52.0 - 8.0 * steer,
        "wrist.l": 8.0,
        "hip.r": -84.0, "knee.r": 74.0, "ankle.r": 6.0,
        "hip.l": -78.0, "knee.l": 82.0, "ankle.l": 2.0,
    }
    face = _face(brow=kw.get("brow", "neutral"), eyes=kw.get("eyes", "open"),
                 mouth=kw.get("mouth", "line"), look=kw.get("look", [0.6, 0.0]))
    return _pose(H, (at[0], at[1] + 0.004 * H * jog), kw.get("facing", 1),
                 joints, face, tilt=0.6 * jog)


def point(phase: float = 0.0, dir: int = 1, **kw) -> dict:
    """Anticipate, **hold**, thrust past, settle, hold. One-shot: ``phase`` is
    progress, not a loop.

    Past ``phase = 1`` the pose keeps going as a held drawing with breath and a
    blink in it — advance the surplus at ``1 / IDLE_CYCLE_S`` cycles a second
    and the hold stays alive instead of freezing.
    """
    H = float(kw.get("height", H_DEF))
    hip_h = rig.PELVIS_TO_SOLE
    x, g = _stage(kw, hip_h, H)
    t = 0.0 if phase < 0.0 else (1.0 if phase > 1.0 else float(phase))
    held = max(0.0, float(phase) - 1.0)
    breath, blinking = _idle(held)
    ahead = 1.0 if dir >= 0 else -1.0

    # a point is a small move, so a short wind-up: 5 frames in, 2 held
    k = _windup(t, wind=0.17, hold=0.07, depth=0.22, overshoot=0.12)
    arm = (-96.0 if ahead > 0 else -250.0) * 1.0
    rest = 8.0
    shoulder_r = rest + (arm - rest) * k
    settle = math.sin(2.0 * math.pi * t) * 0.6 * max(0.0, 1.0 - t * 1.4)

    joints = {}
    ph = hip_h * H + (0.004 * H * breath if held else 0.0)
    joints.update(_leg("r", (0.030 * H, ph - SOLE * H), -1.0, H))
    joints.update(_leg("l", (-0.078 * H, ph - SOLE * H), 8.0, H))
    lean = 2.0 + 5.0 * k * ahead + 0.8 * breath * (1.0 if held else 0.0)
    neck, head = -0.62 * lean, -0.38 * lean
    joints.update({
        "spine": lean, "neck": neck - 2.0 * k, "head": head - 3.0 * k + settle + 3.0,
        "shoulder.r": shoulder_r, "elbow.r": -22.0 + 18.0 * k,
        "wrist.r": 4.0 * k,
        "shoulder.l": 12.0 - 16.0 * k, "elbow.l": -28.0 - 14.0 * k, "wrist.l": 6.0,
    })
    eyes = kw.get("eyes") or ("wide" if k > 0.6 else "open")
    if held and blinking and kw.get("blink", True):
        eyes = "shut"
    face = _face(brow=kw.get("brow", "angry" if k > 0.6 else "neutral"), eyes=eyes,
                 mouth=kw.get("mouth", "wide" if k > 0.6 else "line"),
                 look=kw.get("look", [0.85 * ahead, 0.0]))
    return _pose(H, (x, g - ph), kw.get("facing", 1), joints, face)


_REACT = {
    # kind: (spine, tilt, squash, arm_r, arm_l, elbow, knee_flex, head, face)
    "shock": dict(spine=-14.0, tilt=-5.0, squash=1.20, sh_r=-54.0, sh_l=48.0,
                  elbow=-104.0, flex=0.12, head=9.0, lift=0.010,
                  face=dict(brow="surprised", eyes="wide", mouth="gasp",
                            look=[0.35, -0.35])),
    "dismay": dict(spine=13.0, tilt=0.0, squash=0.93, sh_r=16.0, sh_l=22.0,
                   elbow=-26.0, flex=0.22, head=-16.0, lift=-0.012,
                   face=dict(brow="sad", eyes="squint", mouth="frown",
                             look=[0.1, 0.55])),
    "glee": dict(spine=-9.0, tilt=0.0, squash=1.07, sh_r=-212.0, sh_l=-198.0,
                 elbow=-22.0, flex=0.04, head=11.0, lift=0.055,
                 face=dict(brow="surprised", eyes="shut", mouth="grin",
                           look=[0.2, -0.2])),
    "brace": dict(spine=20.0, tilt=0.0, squash=0.85, sh_r=-72.0, sh_l=-64.0,
                  elbow=-122.0, flex=0.40, head=-12.0, lift=-0.030,
                  face=dict(brow="strain", eyes="shut", mouth="line",
                            look=[0.0, 0.2])),
}


def react(phase: float = 1.0, kind: str = "shock", **kw) -> dict:
    """A take: anticipate, **hold the wind-up**, hit, then vibrate onto the pose.

    One-shot like :func:`point`. ``react(1.0)`` is the readable extreme, which
    is what a keyframe should aim at; ``react(0.0)`` is neutral. The wind-up
    runs 12 frames with 4 held at the peak (:data:`ANTICIPATION_FRAMES`), which
    is the length a big comedic take wants at 30 fps — assuming the whole take
    is played over about a second.
    """
    H = float(kw.get("height", H_DEF))
    R = _REACT.get(str(kind), _REACT["shock"])
    x, g = _stage(kw, rig.PELVIS_TO_SOLE, H)
    t = 0.0 if phase < 0.0 else (1.0 if phase > 1.0 else float(phase))
    held = max(0.0, float(phase) - 1.0)
    breath, blinking = _idle(held)

    wind, hold = (f / (FPS * 1.0) for f in ANTICIPATION_FRAMES["reaction"])
    k = _windup(t, wind=wind, hold=hold, depth=0.22, overshoot=0.13)
    # the ring only exists after the hit, or the wind-up hold is not a hold
    rel = max(0.0, t - (wind + hold))
    ring = math.exp(-5.0 * rel) * math.sin(13.0 * rel) * 0.9

    sq = 1.0 + (R["squash"] - 1.0) * k
    fx_r = 0.055 * H + 0.02 * H * k
    fx_l = -0.060 * H - 0.03 * H * k
    ph = (rig.PELVIS_TO_SOLE - R["flex"] * LEG * k + R["lift"] * k) * H
    ph += 0.004 * H * breath if held else 0.0
    ph = min(ph, _max_pelvis(H, {"r": fx_r, "l": fx_l}, sq))
    joints = {}
    tilt = R["tilt"] * k
    joints.update(_leg("r", (fx_r, ph - SOLE * H), -4.0 - 10.0 * k, H, sq, tilt))
    joints.update(_leg("l", (fx_l, ph - SOLE * H), 4.0 + 6.0 * k, H, sq, tilt))
    spine = R["spine"] * k
    joints.update({
        "spine": spine + ring,
        "neck": -spine * 0.55 + R["head"] * k * 0.5,
        "head": -spine * 0.30 + R["head"] * k * 0.5 + ring + 3.0,
        "shoulder.r": 6.0 + (R["sh_r"] - 6.0) * k,
        "shoulder.l": 8.0 + (R["sh_l"] - 8.0) * k,
        "elbow.r": -18.0 + (R["elbow"] + 18.0) * k,
        "elbow.l": -18.0 + (R["elbow"] + 18.0) * k * 0.92,
        "wrist.r": -10.0 * k, "wrist.l": 10.0 * k,
    })
    face = dict(R["face"]) if t >= wind + hold else _face(brow="surprised")
    if held and blinking and kw.get("blink", True) and face.get("eyes") != "shut":
        face["eyes"] = "shut"
    for key in ("brow", "eyes", "mouth", "look"):
        if kw.get(key) is not None:
            face[key] = kw[key]
    return _pose(H, (x, g - ph), kw.get("facing", 1), joints, face,
                 squash=sq, tilt=tilt)


POSES = {
    "stand": stand, "walk": walk, "run": run, "panic": panic,
    "drive": drive, "point": point, "react": react,
}

#: Scene units a gait advances per full phase cycle, per unit of height.
STRIDES = {"walk": WALK["stride"], "run": RUN["stride"], "panic": SCRAMBLE["stride"]}


def stride_units(name: str, height: float = H_DEF) -> float:
    """How far ``name`` travels in one full phase cycle, in scene units.

    A renderer that drives an actor's ``at`` itself must advance it at this
    rate, or the planted foot slides -- the cycle plants its feet against its
    own travel, and nothing else can know what that is. For an actor crossing
    at ``v`` units per second, the phase rate is ``v / stride_units(name, h)``
    cycles per second.
    """
    return STRIDES.get(str(name), 0.0) * float(height)


# ------------------------------------------------------------------ blend ----


def _shortest(a: float, b: float) -> float:
    """The signed difference from ``a`` to ``b`` on the shortest arc."""
    return (b - a + 180.0) % 360.0 - 180.0


def blend(a: dict, b: dict, t: float) -> dict:
    """Interpolate two poses.

    Angles blend on the shortest arc, so 350 -> 10 travels 20 degrees rather
    than 340 the wrong way round. ``at``, ``height``, ``squash`` and ``tilt``
    blend linearly. ``face`` and ``facing`` **snap** at ``t >= 0.5`` — an eye
    is open or shut, never half.

    ``t`` is deliberately not clamped to ``0..1``: `anim.ease` curves such as
    ``anticipate`` and ``overshoot`` leave that range on purpose, and that
    overshoot is the whole point of them.
    """
    a, b = a or {}, b or {}
    t = max(-0.6, min(1.6, float(t)))
    late = b if t >= 0.5 else a

    ja, jb = a.get("joints") or {}, b.get("joints") or {}
    joints = {}
    for name in set(ja) | set(jb):
        va, vb = float(ja.get(name, 0.0)), float(jb.get(name, 0.0))
        joints[name] = va + _shortest(va, vb) * t

    def num(key, default):
        return float(a.get(key, default)) + (
            float(b.get(key, default)) - float(a.get(key, default))) * t

    aa = a.get("at") or (0.0, 0.0)
    bb = b.get("at") or aa
    out = {
        "at": [aa[0] + (bb[0] - aa[0]) * t, aa[1] + (bb[1] - aa[1]) * t],
        "facing": late.get("facing", a.get("facing", 1)),
        "height": num("height", H_DEF),
        "squash": num("squash", 1.0),
        "tilt": num("tilt", 0.0),
        "joints": joints,
        "face": dict(late.get("face") or a.get("face") or _face()),
    }
    for key in set(a) | set(b):
        if key not in out:
            out[key] = late.get(key, a.get(key))
    return out


# ------------------------------------------------------------- self-test -----

if __name__ == "__main__":
    import os

    from PIL import Image, ImageDraw

    OUT = os.environ.get("RIG_TEST_OUT", "/tmp")
    LOOK = {
        "sky": (200, 220, 235), "skin": (242, 199, 162), "hair": (52, 38, 34),
        "shirt": (214, 78, 62), "trouser": (46, 62, 100), "shoe": (36, 34, 44),
        "ink": (26, 24, 32), "accent": (247, 196, 62), "accent2": (64, 190, 178),
        "shadow": (30, 26, 52),
    }
    H = 18.0
    ok = 0

    def check(label, cond, detail=""):
        global ok
        assert cond, f"FAIL {label} {detail}"
        ok += 1
        print(f"  ok  {label}{('  ' + detail) if detail else ''}")

    # -- (a) the cycle wraps ---------------------------------------------
    print("wrap")
    for name, fn in (("walk", walk), ("run", run), ("panic", panic)):
        p0, p1 = fn(0.0), fn(1.0)
        worst = max(abs(p0["joints"][k] - p1["joints"][k]) for k in p0["joints"])
        check(f"{name}(0) joints == {name}(1)", worst < 1e-9, f"max delta {worst:.2e} deg")
        check(f"{name} bob wraps", abs(p0["at"][1] - p1["at"][1]) < 1e-9,
              f"dy {abs(p0['at'][1] - p1['at'][1]):.2e}")
        check(f"{name} face wraps", p0["face"] == p1["face"])
        adv = p1["at"][0] - p0["at"][0]
        check(f"{name} stride_units agrees with the travel",
              abs(stride_units(name, H) - (fn(1.0)["at"][0] - fn(0.0)["at"][0])) < 1e-9,
              f"{stride_units(name, H):.3f} units per cycle")
        check(f"{name} advances exactly one stride", abs(adv - {
            "walk": WALK, "run": RUN, "panic": SCRAMBLE}[name]["stride"] * H) < 1e-9,
              f"{adv:.3f} units")
        t0, t1 = fn(0.0, travel=False), fn(1.0, travel=False)
        check(f"{name} treadmill wraps whole", t0 == t1)

    # -- (b) a planted foot does not slide -------------------------------
    print("planted feet")
    for name, fn, params in (("walk", walk, WALK), ("run", run, RUN),
                             ("panic", panic, SCRAMBLE)):
        duty = params["duty"]
        for side, off in (("r", 0.0), ("l", 0.5)):
            xs = []
            n = 240
            for i in range(n + 1):
                p = (i / n) * duty * 0.98 + duty * 0.01     # inside stance
                phase = p - off      # monotonic: travel must accumulate
                pose = fn(phase)
                xs.append(rig.solve(pose)["ankle." + side][0])
            drift = max(xs) - min(xs)
            check(f"{name} {side} stance drift", drift < 0.01,
                  f"{drift * 1000:.4f} milli-units over {duty:.0%} of the cycle")
        # and the sole really is on the ground through stance
        pose = fn(0.25)
        sole = rig.solve(pose)["ankle.r"][1] + SOLE * H
        check(f"{name} sole on ground at mid-stance", abs(sole - GROUND) < 0.30,
              f"{sole - GROUND:+.3f} units")

    # every grounded pose really stands on the ground line, squash and all
    for label, pose in ([("stand", stand(0.0)), ("stand.5", stand(0.5)),
                         ("point", point(0.0)), ("point.6", point(0.6))]
                        + [(f"react/{k}@{t}", react(t, kind=k))
                           for k in _REACT for t in (0.1, 0.5, 1.0)]):
        s_ = rig.solve(pose)
        off = max(abs(s_["ankle." + side][1] + SOLE * H - GROUND) for side in "rl")
        check(f"{label} plants both soles", off < 0.02, f"{off * 1000:.2f} milli-units")

    # -- (c) arms oppose legs --------------------------------------------
    # Tested on effectors in scene space, not on the hip angle: with a bent
    # knee the thigh can point forward while the foot is behind, so the joint
    # angle is not a sound proxy for which way the limb is actually swinging.
    print("opposition")
    for name, fn in (("walk", walk), ("run", run)):
        n = 64
        foot, hand = {"l": [], "r": []}, {"l": [], "r": []}
        for i in range(n):
            s = rig.solve(fn(i / n, travel=False))
            px = s["pelvis"][0]
            for side in ("l", "r"):
                foot[side].append(s["ankle." + side][0] - px)
                hand[side].append(s["hand." + side][0] - px)
        for side in ("l", "r"):
            f = [v - sum(foot[side]) / n for v in foot[side]]
            h = [v - sum(hand[side]) / n for v in hand[side]]
            opposed = sum(1 for a, b in zip(f, h) if a * b < 0.0)
            corr = sum(a * b for a, b in zip(f, h)) / n
            check(f"{name} {side} arm opposes {side} leg", corr < 0.0 and opposed >= n * 0.85,
                  f"correlation {corr:+.3f}, opposed in {opposed}/{n} frames")
        # and the two legs are half a stride apart
        anti = sum(1 for a, b in zip(foot["l"], foot["r"]) if a * b < 0.0)
        check(f"{name} legs are in antiphase", anti >= n * 0.7, f"{anti}/{n} frames")

    # panic deliberately breaks opposition -- the arms are overhead, flailing
    over = 0
    for i in range(64):
        s = rig.solve(panic(i / 64.0, travel=False))
        if (s["hand.r"][1] < s["shoulder.r"][1] and s["hand.l"][1] < s["shoulder.l"][1]):
            over += 1
    check("panic keeps both hands above the shoulders", over == 64, f"{over}/64 frames")

    # A raised arm is drawn over the skull (see rig.draw), so a pose that
    # *rests* with an arm overhead must keep it BEHIND the face -- an elbow
    # out in front of the head puts a sleeve across the only thing that is
    # acting. Poses that hold a hand up in front of the head on purpose
    # (shock, brace) are drawn in front instead, which is what a hand raised
    # to the mouth should look like, so only the arms-overhead poses are held
    # to this.
    def clears_the_face(p):
        s = rig.solve(p)
        H = float(p["height"])
        face_ = -1.0 if float(p.get("facing", 1)) < 0 else 1.0
        mid_y = (s["head_base"][1] + s["crown"][1]) * 0.5
        cx = (s["head_base"][0] + s["crown"][0]) * 0.5
        for side in ("l", "r"):
            if s["hand." + side][1] < mid_y:      # this arm is overhead
                for j in ("elbow." + side, "wrist." + side):
                    if (s[j][0] - cx) * face_ > 0.10 * H:
                        return False, j, (s[j][0] - cx) * face_ / H
        return True, "", 0.0

    for i in range(64):
        okc, j, d = clears_the_face(panic(i / 64.0, travel=False))
        assert okc, f"panic {i / 64.0:.3f}: {j} is {d:.3f} H in front of the face"
    check("panic's overhead arms clear the face on every frame", True, "64/64")
    for i in range(64):
        okc, j, d = clears_the_face(panic(i / 64.0, travel=False, facing=-1))
        assert okc, f"panic mirrored {i / 64.0:.3f}: {j} is {d:.3f} H in front"
    check("...and mirrored too", True, "64/64")
    bad = [round(0.75 + i / 32.0, 3) for i in range(9)
           if not clears_the_face(react(0.75 + i / 32.0, kind="glee"))[0]]
    check("react/glee settles with its arms off the face", not bad,
          f"{bad or 'clean over the last quarter'}")

    # -- pelvis oscillates twice per stride, ~0.012 H --------------------
    print("pelvis")
    ys = [walk(i / 200.0, travel=False)["at"][1] for i in range(200)]
    amp = (max(ys) - min(ys)) / 2.0
    check("walk pelvis amplitude ~ 0.012 H", abs(amp - 0.012 * H) < 1e-6,
          f"{amp:.4f} units = {amp / H:.4f} H")
    mean = sum(ys) / len(ys)
    sgn = [s for s in (0 if abs(y - mean) < 1e-9 else (1 if y > mean else -1)
                       for y in ys) if s]
    crossings = sum(1 for i in range(len(sgn)) if sgn[i] != sgn[(i + 1) % len(sgn)])
    check("walk pelvis oscillates twice per stride", crossings == 4,
          f"{crossings} mean crossings")
    top = min(range(len(ys)), key=lambda i: ys[i]) / len(ys)
    check("walk pelvis is highest over the planted leg",
          abs(top - WALK["bob_peak"]) < 0.02 and WALK["bob_peak"] < WALK["duty"],
          f"peak at phase {top:.3f}, mid-stance {WALK['duty'] / 2:.3f}")

    # -- head lags the chest ---------------------------------------------
    print("follow-through")
    lags = []
    for i in range(60):
        j = walk(i / 60.0)["joints"]
        lags.append(j["spine"] + j["neck"] + j["head"])
    check("head is not rigidly locked to the chest", max(lags) - min(lags) > 0.15,
          f"absolute head tilt swings {max(lags) - min(lags):.2f} deg")
    now = _torso(0.25, 3.0, 1.4)
    late = _torso(0.25 - HEAD_LAG, 3.0, 1.4)
    check("head angle trails the chest", abs(now - late) > 0.05,
          f"{HEAD_LAG:.2f} of a cycle behind")

    # -- the idle is asymmetrical and alive -------------------------------
    print("idle")
    s0 = rig.solve(stand(0.0))
    px, py = s0["pelvis"]
    dr, dl = s0["ankle.r"][0] - px, s0["ankle.l"][0] - px
    check("stand is not a parallel stance", abs(abs(dr) - abs(dl)) > 0.02 * H,
          f"feet at {dr:+.2f} and {dl:+.2f} units about the pelvis")
    j0 = stand(0.0)["joints"]
    check("stand hangs one arm lower than the other",
          abs(s0["hand.r"][1] - s0["hand.l"][1]) > 0.01 * H,
          f"hands differ by {abs(s0['hand.r'][1] - s0['hand.l'][1]):.2f} units")
    check("stand tilts the head off axis", 3.0 <= abs(j0["head"]) <= 6.0,
          f"head {j0['head']:+.2f} deg")
    check("stand does not mirror its arms",
          abs(j0["elbow.r"] - j0["elbow.l"]) > 5.0,
          f"elbows {j0['elbow.r']:+.1f} vs {j0['elbow.l']:+.1f}")

    # a blink every 72-96 frames, driven at the documented rate
    frames = int(round(IDLE_CYCLE_S * FPS))
    shut = [i for i in range(frames * 3)
            if stand(i / frames)["face"]["eyes"] == "shut"]
    gaps = [b - a for a, b in zip(shut, shut[1:]) if b - a > 1]
    runs, cur = [], 1
    for a, b in zip(shut, shut[1:]):
        cur = cur + 1 if b - a == 1 else (runs.append(cur), 1)[1]
    runs.append(cur)
    check("stand blinks every 72-96 frames", gaps and all(72 <= g <= 96 for g in gaps),
          f"gaps {gaps} frames")
    check("a blink lasts 2-4 frames", all(2 <= r <= 4 for r in runs), f"runs {runs}")
    check("blink can be switched off",
          all(stand(i / frames, blink=False)["face"]["eyes"] != "shut"
              for i in range(frames)))
    ys = [stand(i / 60.0)["at"][1] for i in range(60)]
    check("stand breathes on the hold", max(ys) - min(ys) > 0.004 * H,
          f"pelvis moves {max(ys) - min(ys):.3f} units")

    # -- anticipation: against the target, held, then past it -------------
    print("anticipation")
    check("_windup starts and ends clean",
          abs(_windup(0.0)) < 1e-12 and abs(_windup(1.0) - 1.0) < 1e-12)
    ks = [_windup(i / 400.0) for i in range(401)]
    check("_windup moves against the target first", min(ks) < -0.15,
          f"reaches {min(ks):+.3f}")
    check("_windup overshoots the target", max(ks) > 1.10, f"peaks at {max(ks):.3f}")
    held = [k for k in ks if abs(k - min(ks)) < 1e-9]
    check("_windup holds at the peak of the wind-up", len(held) >= 400 * 0.10,
          f"{len(held) / 400.0:.2f} of the move")
    w, h = ANTICIPATION_FRAMES["reaction"]
    check("a big take winds up for 10-14 frames and holds 2-4",
          10 <= w <= 14 and 2 <= h <= 4, f"{w} + {h} frames at {FPS} fps")
    kr = [react(i / 200.0, "shock")["joints"]["spine"] for i in range(201)]
    check("react winds up against its own move",
          max(kr) > 0.0 and _REACT["shock"]["spine"] < 0.0,
          f"spine reaches {max(kr):+.2f} deg the wrong way first")
    check("react holds the wind-up pose",
          sum(1 for k in kr if abs(k - max(kr)) < 1e-9) >= 4,
          f"{sum(1 for k in kr if abs(k - max(kr)) < 1e-9)} of 200 samples")
    check("react(1) is the extreme",
          abs(react(1.0, "shock")["squash"] - _REACT["shock"]["squash"]) < 1e-9)
    for kind, want in (("shock", 1.20), ("brace", 0.85)):
        check(f"react/{kind} squash matches the reference table",
              abs(_REACT[kind]["squash"] - want) < 1e-9, f"{_REACT[kind]['squash']:.2f}")

    # -- blend ------------------------------------------------------------
    print("blend")
    a = {"joints": {"spine": 350.0}, "face": {"eyes": "open"}, "at": (0, 0)}
    b = {"joints": {"spine": 10.0}, "face": {"eyes": "shut"}, "at": (10, 0)}
    check("shortest arc 350 -> 10", abs(blend(a, b, 0.5)["joints"]["spine"] - 360.0) < 1e-9,
          f"{blend(a, b, 0.5)['joints']['spine']:.3f} deg")
    check("faces do not interpolate", blend(a, b, 0.49)["face"]["eyes"] == "open"
          and blend(a, b, 0.5)["face"]["eyes"] == "shut")
    check("blend extrapolates for overshoot",
          abs(blend(a, b, 1.08)["at"][0] - 10.8) < 1e-9)

    # -- determinism ------------------------------------------------------
    check("cycles are deterministic",
          all(walk(i / 37.0) == walk(i / 37.0) for i in range(37)))

    # -- the strip --------------------------------------------------------
    N = 8
    unit = 15.0
    cw, ch = 210, 330
    img = Image.new("RGB", (cw * N, ch * 3), (246, 243, 236))
    dd = ImageDraw.Draw(img)
    for row, (label, fn) in enumerate((("walk", walk), ("run", run), ("panic", panic))):
        for i in range(N):
            phase = i / N
            pose = fn(phase, travel=False, x=0.0, ground=0.0)
            cx, cy = i * cw, row * ch
            dd.rectangle([cx, cy, cx + cw - 1, cy + ch - 1], outline=(216, 210, 198))
            dd.text((cx + 8, cy + 8), f"{label} {phase:.3f}", fill=(90, 86, 78))
            # every panel shares one origin, so a sliding foot would be obvious
            draw_origin = (-cw / unit / 2 - cx / unit, -ch / unit * 0.86 - cy / unit)
            rig.draw(img, pose, LOOK, unit=unit, origin=draw_origin, ground=0.0)
        dd.line([(0, row * ch + int(ch * 0.86)), (cw * N, row * ch + int(ch * 0.86))],
                fill=(200, 120, 110), width=1)
    path = os.path.join(OUT, "poses_strip.png")
    img.save(path)

    # -- the acting strip: the wind-up, the hold, the hit, the settle -----
    rows = (("react shock", lambda p: react(p, "shock", x=0.0, ground=0.0)),
            ("react brace", lambda p: react(p, "brace", x=0.0, ground=0.0)),
            ("react glee", lambda p: react(p, "glee", x=0.0, ground=0.0)),
            ("point", lambda p: point(p, x=0.0, ground=0.0)),
            ("stand idle", lambda p: stand(p, x=0.0, ground=0.0)))
    img2 = Image.new("RGB", (cw * N, ch * len(rows)), (246, 243, 236))
    dd = ImageDraw.Draw(img2)
    for row, (label, fn) in enumerate(rows):
        for i in range(N):
            phase = i / (N - 1.0)
            cx, cy = i * cw, row * ch
            dd.rectangle([cx, cy, cx + cw - 1, cy + ch - 1], outline=(216, 210, 198))
            draw_origin = (-cw / unit / 2 - cx / unit, -ch / unit * 0.86 - cy / unit)
            rig.draw(img2, fn(phase), LOOK, unit=unit, origin=draw_origin, ground=0.0)
            dd.text((cx + 8, cy + 8), f"{label} {phase:.2f}", fill=(90, 86, 78))
        dd.line([(0, row * ch + int(ch * 0.86)), (cw * N, row * ch + int(ch * 0.86))],
                fill=(200, 120, 110), width=1)
    path2 = os.path.join(OUT, "poses_acting.png")
    img2.save(path2)

    print(f"\n{ok} checks passed")
    print("wrote", path)
    print("wrote", path2)
