"""The shot and time model for the 2D character-animation style.

This is the film's clock. It knows nothing about pixels, and imports no
drawing library, so `compile.py` can plan a board with it without dragging
PIL into a process that only wants to reason about time.

Three jobs:

* **Times.** `"l3"`, `"l3+0.4"`, `"l3-0.15"`, `"l3.end"`, `"l3.end+0.2"` and
  bare seconds all resolve to a position in the finished film, against the
  line times the audio stage measured.
* **Shots.** Every shot gets an absolute `start` and `end`, the list is
  checked for order and overlap, and the film's running time falls out of it.
* **Camera.** Given a shot and a shot-local time, the view rect the frame is
  cut from — centre and zoom — with the move, the easing and the settle
  applied.

Everything here is a **pure function of time**. Nothing accumulates frame to
frame. That is not tidiness: the renderer composes frames in parallel workers
that have never seen the frame before theirs, so a camera that integrated its
own velocity would drift differently at `-j 1` and `-j 4` and the two renders
would stop matching.
"""

from __future__ import annotations

import math
import re
import zlib
from bisect import bisect_right
from dataclasses import dataclass, field

__all__ = [
    "TimeError", "ShotError", "Timeline", "Shot", "ShotList", "Camera", "View",
    "SCENE_LONG", "ON_FOR_TIER", "DEFAULT_ON", "MOVES", "PARALLAX",
    "PARALLAX_MIN_LAYERS", "IMPACT_ONES_FRAMES", "CAMERA_EASE", "WHIP_EASE",
    "MECHANICAL_EASES", "MIN_HOLD_FRAMES", "KEY_EASE", "CREEP_EASE",
    "CREEP_MIN_RATE", "CREEP_MAX_SETTLE",
    "PACE_MEAN", "PACE_REACTION", "PACE_SETUP", "PACE_CUTS_PER_MIN",
    "scene_box", "split_time", "build", "resolve_on", "quantise",
    "quantise_frame", "actor_at", "actor_phase", "timeline_document", "ease",
    "pacing_report", "EASE_SOURCE",
    "actor_travel", "stages_travel", "gait_phase", "implied_rate",
]

# The long edge of the composition box, in scene units. A 16:9 board is
# 100 x 56.25, a 9:16 board 56.25 x 100 (see reference/rig.md).
SCENE_LONG = 100.0

#: How many frames one drawing is held for, per motion tier.
#:
#: `sakuga` is the only tier that earns ones — a film on ones throughout reads
#: as a tween, which is the failure this whole style exists to avoid. `hold`
#: and `limited` are the table's "held shots, background business" and go on
#: threes. `impact` stays on twos deliberately: an impact frame is punctuation
#: slammed onto a *held* drawing, and it is the smear and the squash that sell
#: it, not the drawing rate.
ON_FOR_TIER = {"hold": 3, "limited": 3, "full": 2, "sakuga": 1, "impact": 2}
DEFAULT_ON = 2

#: Frames either side of a contact that are promoted to ones.
#:
#: An impact is the one moment the audience is looking straight at the thing
#: that moves, and a held drawing across it loses the hit entirely. Two frames
#: each side at 30fps is a sixth of a second — long enough to carry the
#: anticipation, the contact and the recoil as three distinct drawings.
IMPACT_ONES_FRAMES = 2

MOVES = ("none", "push", "pull", "track", "pan", "whip", "follow", "handheld")

#: Camera moves decelerate into their final framing. A linear move is a named
#: failure of this style — it reads as a machine panning, not an operator
#: arriving — so `linear` on a camera is substituted and reported rather than
#: honoured. `out` is ease-out-cubic; `overshoot` is the overshoot-settle
#: curve, which is what a whip does when it lands.
CAMERA_EASE = "out"
WHIP_EASE = "overshoot"
MECHANICAL_EASES = frozenset({"linear", "in", "hold"})

#: The one constant-rate camera move this style allows, and the only ease
#: exempt from :data:`MECHANICAL_EASES`.
#:
#: The ban on `linear` is a ban on *arriving* at constant speed: a dramatic
#: move that runs at one rate and then simply stops reads as a machine rather
#: than as an operator finding a frame. A creep is the opposite case. It is a
#: move the audience must **never notice** — a slow drift across a long shot
#: whose only job is that the frame is never twice the same, so a five-second
#: hold on a breathing character does not render as a run of byte-identical
#: frames and does not read as a freeze.
#:
#: For that job constant rate is not a compromise, it is the only correct
#: shape, and an ease-out substituted into it fails at both ends:
#:
#:   * ease-out-cubic leaves at **3.64x** its own average speed, so the first
#:     half-second registers as a deliberate accent the shot never intended;
#:   * it arrives asymptotically — its final frame moves **0.00x** average —
#:     so the last third is the frozen tail the creep existed to prevent.
#:
#: (Both figures measured off `Camera.view`, a 5.2s push from 1.55 to 1.90.
#: The same push on a creep ramps from 0.67x to 1.00x of average: zoom is
#: interpolated linearly while the view is its reciprocal, so a creep in fact
#: accelerates very slightly. That is the safe direction — no departure
#: spike, and emphatically no dead tail.)
#:
#: Measured on the pursuit film, per shot, clip-rendered and read with the
#: same mean-frame-delta metric `motionprofile` uses (longest run under its
#: 0.60 hold threshold):
#:
#:   ===== ======== ======== =====================
#:   shot  ease-out `creep`  `creep`, settle removed
#:   ===== ======== ======== =====================
#:   s15    1.57s    0.57s    0.03s
#:   s20    1.17s    0.53s    0.00s
#:   ===== ======== ======== =====================
#:
#: Same mean, same peak, a third of the frozen run — the curve redistributes
#: the motion rather than adding any. So `linear` stays banned for any move
#: meant to be perceived, and `creep` is exempt precisely because it must not
#: be.
CREEP_EASE = "creep"

#: A creep may still settle, but not for so long that the settle is itself the
#: frozen run. Measured: 0.6s of hold on a creeping shot leaves a 0.53-0.57s
#: identical-frame run, which no tool objects to; past about a second it is
#: just an ease-out with extra steps.
CREEP_MAX_SETTLE = 1.0

#: A creep slower than this — as a fraction of the view per second — is a
#: freeze with extra steps. Measured, not guessed: rendering a bare set with a
#: constant-rate zoom and reading the mean frame delta that `motionprofile`
#: reads gives a straight line, `delta ~= 0.25 * rate%/s + 0.06`, so a creep
#: on its own crosses that tool's 0.60 hold threshold at about 2.2%/s and not
#: below. 2.0%/s is the floor here — the permissive side of the measurement,
#: because this is a warning and a false alarm costs more than a near miss.
#: A real shot has scene business on top, but the creep must be able to carry
#: a still frame by itself: that is the whole reason it was added.
#:
#: Practically: a 5.2s shot holding 0.6s has 4.6s of move, so it wants at
#: least ~9% of view change — a push from 1.55 to about 1.86.
CREEP_MIN_RATE = 0.020

#: The approach curve for a keyframe that names none — for the pose track and
#: for the actor's path alike, so a body and its position arrive on the same
#: curve. `anim.track` documents `overshoot` as its default and calls it the
#: house curve; naming `inout` here made that default unreachable, and
#: ease-in-out is the wrong shape for this style: it leaves at the same speed
#: it arrives, which is how a slider moves, not how a body does.
KEY_EASE = "overshoot"

#: Relative layer speeds, as multiples of the character plane. Published to
#: `sets.draw_set` in the camera dict so every set uses one table instead of
#: inventing its own. A layer at rate `r` is displaced by `(1 - r) * (dx, dy)`:
#: the character plane at 1.0 does not move against the camera at all, the far
#: background at 0.18 lags it almost entirely, and the foreground at 1.5 runs
#: the other way. Three layers is the minimum that reads as depth.
PARALLAX = {"fore": 1.5, "char": 1.0, "mid": 0.5, "far": 0.18}
PARALLAX_MIN_LAYERS = 3

#: Pacing bands, in seconds, for the diagnostics in `pacing_report`.
#:
#: These were once guessed from an idea of what this genre "should" feel like,
#: and every one of them was wrong in the same direction: far too fast. The
#: reference films were then measured at `lookcheck.py`'s own sampling rate
#: and cut **5.21 and 0.00 times a minute** -- one of them does not cut at all
#: in 83 seconds -- against a band that used to demand 15.5 to 23.3. A film
#: built to the old numbers cannot look like the reference, and worse, the
#: warning fired on the correct films and stayed silent on the wrong ones.
#:
#: `PACE_REACTION` and `PACE_SETUP` still describe how long a *given kind* of
#: shot needs to be read, which is a fact about an audience rather than about
#: this genre, so they are unchanged.
PACE_MEAN = (6.0, 24.0)
PACE_REACTION = (1.0, 1.5)
PACE_SETUP = (6.0, 10.0)
PACE_CUTS_PER_MIN = (0.0, 7.0)      # measured: summit 5.21, getaway 0.00
#: The shortest hold that reads as a hold rather than as a stumble.
MIN_HOLD_FRAMES = 20

# How long the camera takes to notice a followed actor and catch up. A rig
# that is welded to the frame reads as a screensaver; a fraction of a second
# of lag reads as an operator.
FOLLOW_LAG = 0.18
FOLLOW_LAG_MIX = 0.35

# handheld: a drift, never a shake. Every component sits below a third of a
# hertz — two orders of magnitude below the 8-20 Hz that reads as a shake —
# but high enough that the wander is actually visible inside a three-second
# cut. Tuned against the measurement in `--self-test`'s sibling check: over a
# four-second shot the frame should travel roughly ten pixels at 1920 and
# reverse at most once. Amplitudes are fractions of the *view*, so a long lens
# drifts by the same amount of picture as a wide one.
HH_FREQ_X = (0.11, 0.19, 0.31)
HH_FREQ_Y = (0.09, 0.17, 0.27)
HH_AMP_X = 0.011          # of view width, summed across components
HH_AMP_Y = 0.007          # of view height
HH_CORRECT = 0.55         # how much of the wander the operator takes back
HH_CORRECT_LAG = 1.4      # how long they take to notice, seconds
HH_ZOOM = 0.004           # breathing, as a fraction of the zoom


class TimeError(ValueError):
    """A time reference that cannot be resolved."""


class ShotError(ValueError):
    """A shot list that does not describe a film."""


# ----------------------------------------------------------------- easing ----

# `anim.ease` is the film's easing vocabulary and is preferred whenever it can
# be imported. The fallback exists only so this module stays usable while
# `anim.py` is still being written; `EASE_SOURCE` says which one is live, and
# the renderer prints a warning when it is not the real thing.
try:                                            # pragma: no cover - import path
    from anim import ease as _anim_ease
    EASE_SOURCE = "anim"
except Exception:                               # pragma: no cover - import path
    _anim_ease = None
    EASE_SOURCE = "fallback"


def _fallback_ease(name, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    n = (name or "inout").lower()
    if n == "hold":
        return 0.0
    if n == "linear":
        return t
    if n == "in":
        return t * t * t
    if n == "out":
        return 1.0 - (1.0 - t) ** 3
    if n == "inout":
        return 4 * t ** 3 if t < 0.5 else 1.0 - (-2 * t + 2) ** 3 / 2.0
    if n == "snap":
        # Almost all of the move happens in the middle fifth.
        return 0.0 if t < 0.4 else (1.0 if t > 0.6 else (t - 0.4) / 0.2)
    if n == "anticipate":
        c = 1.70158
        return t * t * ((c + 1) * t - c)
    if n == "overshoot":
        c = 1.70158
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2
    if n == "elastic":
        if t in (0.0, 1.0):
            return t
        return (2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3))
                + 1.0)
    if n == "bounce":
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        if t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        if t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
    return t


def ease(name, t):
    """Easing curve `name` sampled at `t` in 0..1.

    `creep` is resolved here rather than delegated, because it is a *camera*
    curve belonging to this module's staging vocabulary and not one of the ten
    in `anim.ease`. It is the identity: constant rate, no departure spike, no
    asymptotic tail. See :data:`CREEP_EASE` for why that is allowed when
    `linear` is not.
    """
    if str(name or "").lower() == CREEP_EASE:
        return 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    if _anim_ease is not None:
        return float(_anim_ease(name or "inout", t))
    return _fallback_ease(name, t)


# ------------------------------------------------------------------ times ----

# A line id may itself contain a hyphen, so the offset is found by taking the
# *rightmost* `+`/`-` that is followed by nothing but a number. `.+` is greedy
# and backtracks from the right, which is exactly that.
_OFFSET_RE = re.compile(r"^(?P<base>.+?)\s*(?P<op>[+-])\s*"
                        r"(?P<off>[0-9]+(?:\.[0-9]+)?)\s*$")


def split_time(spec):
    """Split a time reference into `(base, offset)`.

    `base` is `None` when the whole thing is an absolute number.

        >>> split_time("l3.end+0.2")
        ('l3.end', 0.2)
        >>> split_time("l3-0.15")
        ('l3', -0.15)
        >>> split_time(12.5)
        (None, 12.5)
    """
    if isinstance(spec, bool):
        raise TimeError(f"{spec!r} is not a time")
    if isinstance(spec, (int, float)):
        return None, float(spec)
    if spec is None:
        raise TimeError("missing time reference")
    s = str(spec).strip()
    if not s:
        raise TimeError("empty time reference")
    try:                       # a bare number, in any float spelling
        return None, float(s)
    except ValueError:
        pass
    m = _OFFSET_RE.match(s)
    if not m:
        return s, 0.0
    off = float(m.group("off"))
    if m.group("op") == "-":
        off = -off
    return m.group("base").strip(), off


class Timeline:
    """Resolves narration line ids to absolute seconds.

    Built from whatever `audio.line_times()` measured, so the times here are
    the ones the film actually plays — narration clips are trimmed of their
    recorded silence before they are laid down, and a stage that re-derives
    the times from the source wavs instead drifts steadily late.
    """

    def __init__(self, lines=None, lead_in=0.6, tail=1.2):
        self.lines = {k: (float(a), float(b))
                      for k, (a, b) in (lines or {}).items()}
        self.lead_in = float(lead_in)
        self.tail = float(tail)
        self.duration = 0.0

    @classmethod
    def from_board(cls, board, line_times=None):
        t = board.get("timing", {}) or {}
        return cls(line_times or {},
                   lead_in=float(t.get("lead_in", 0.6)),
                   tail=float(t.get("tail", 1.2)))

    @property
    def narration_end(self):
        return max((b for _, b in self.lines.values()), default=0.0)

    def resolve(self, spec, default=None, *, what=""):
        if spec is None:
            if default is None:
                raise TimeError(f"missing time{' for ' + what if what else ''}")
            return float(default)
        base, off = split_time(spec)
        if base is None:
            return off
        return self._point(base, what) + off

    def _point(self, name, what=""):
        key, at_end = name, False
        for suffix, end in ((".end", True), (".start", False)):
            if name.endswith(suffix):
                key, at_end = name[: -len(suffix)], end
                break
        if key in self.lines:
            return self.lines[key][1 if at_end else 0]
        try:
            return float(name)
        except ValueError:
            pass
        known = ", ".join(sorted(self.lines)) or "none — this board has no narration"
        raise TimeError(
            f"unknown time reference {name!r}"
            f"{' for ' + what if what else ''}. Known lines: {known}")

    def can_resolve(self, spec):
        try:
            self.resolve(spec)
            return True
        except TimeError:
            return False


# ------------------------------------------------------------------ shots ----


@dataclass
class Shot:
    """One cut of the film, resolved onto the finished film's clock."""

    index: int
    id: str
    start: float
    end: float
    set: str
    on: int
    tier: str | None = None
    camera: dict = field(default_factory=dict)
    actors: list = field(default_factory=list)
    props: list = field(default_factory=list)
    overlay: dict | None = None
    sfx: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    seed: int = 0
    #: Shot-local seconds at which something lands. Poses are drawn on ones
    #: within IMPACT_ONES_FRAMES of each one.
    impacts: tuple = ()

    @property
    def dur(self):
        return self.end - self.start

    def contains(self, t, eps=1e-9):
        return self.start - eps <= t < self.end + eps

    def local(self, t):
        """Shot-local seconds, clamped into the shot."""
        return min(max(t - self.start, 0.0), max(self.dur, 0.0))

    def local_frame(self, frame, fps):
        """Shot-local frame index for an absolute frame index.

        Integer arithmetic on purpose: the drawing rate is quantised against
        this, and a float that lands a millionth under a frame boundary would
        hold one drawing a frame longer in one worker than in another.
        """
        return max(0, int(frame) - int(round(self.start * float(fps))))

    def impact_frames(self, fps):
        """Shot-local frame indices of the contacts, as a sorted tuple."""
        fps = float(fps)
        return tuple(sorted({int(round(t * fps)) for t in self.impacts}))

    def on_at(self, frame, fps):
        """The drawing rate in force at `frame` — the shot's `on`, or 1.

        Held drawings are the whole point of the style, but an impact is the
        exception: a contact wants anticipation, hit and recoil as three
        separate drawings, so the frames around one are promoted to ones.
        Pure function of the board and the frame rate, so every worker agrees.
        """
        if self.on <= 1 or not self.impacts:
            return self.on
        lf = self.local_frame(frame, fps)
        for f in self.impact_frames(fps):
            if abs(lf - f) <= IMPACT_ONES_FRAMES:
                return 1
        return self.on

    def is_ones(self, frame, fps):
        return self.on_at(frame, fps) == 1

    def pose_frame(self, frame, fps):
        """The frame whose drawing is on screen at `frame` — the shot's `on`.

        A cut always shows a fresh drawing, because the count restarts at the
        shot boundary rather than running off the film's clock.
        """
        lf = self.local_frame(frame, fps)
        return quantise_frame(lf, self.on_at(frame, fps))

    def pose_time(self, frame, fps):
        return self.pose_frame(frame, fps) / float(fps)

    def next_pose_time(self, frame, fps):
        """When the drawing after the one on screen at `frame` appears.

        The far end of the interval a smear has to cross.
        """
        on = self.on_at(frame, fps)
        return (self.pose_frame(frame, fps) + max(1, on)) / float(fps)

    @property
    def is_hold(self):
        return (self.tier or "").lower() == "hold"

    def actor(self, actor_id):
        for a in self.actors:
            if a.get("id") == actor_id:
                return a
        return None


class ShotList:
    """The film as an ordered, gap-aware list of shots."""

    def __init__(self, shots, timeline, duration, gaps=()):
        self.shots = list(shots)
        self.timeline = timeline
        self.duration = float(duration)
        self.gaps = list(gaps)
        self._starts = [s.start for s in self.shots]

    def __len__(self):
        return len(self.shots)

    def __iter__(self):
        return iter(self.shots)

    def __getitem__(self, i):
        return self.shots[i]

    @property
    def lead_in(self):
        return self.timeline.lead_in

    @property
    def tail(self):
        return self.timeline.tail

    def by_id(self, shot_id):
        for s in self.shots:
            if s.id == shot_id:
                return s
        return None

    def index_at(self, t):
        """Index of the shot on screen at `t`.

        Time before the first shot shows the first shot's opening frame and
        time after the last shows the last shot's final frame, so the tail and
        the lead-in are held pictures rather than black. A gap between two
        shots holds the earlier one — the alternative is a hole in the film.
        """
        if not self.shots:
            raise ShotError("this board has no shots")
        i = bisect_right(self._starts, t) - 1
        return 0 if i < 0 else i

    def at(self, t):
        """`(shot, shot_local_seconds)` for an absolute time."""
        s = self.shots[self.index_at(t)]
        return s, s.local(t)

    def frame_at(self, frame, fps):
        """`(shot, shot_local_frame)`, in whole frames."""
        s = self.shots[self.index_at(frame / float(fps))]
        return s, s.local_frame(frame, fps)


def scene_box(width, height):
    """The composition box in scene units for an output size.

    16:9 gives `(100, 56.25)`, 9:16 gives `(56.25, 100)` — the long edge is
    always 100 units, so a board composed for one aspect keeps its scale in
    the other.
    """
    width, height = float(width), float(height)
    if width <= 0 or height <= 0:
        raise ValueError("output width and height must be positive")
    if width >= height:
        return SCENE_LONG, SCENE_LONG * height / width
    return SCENE_LONG * width / height, SCENE_LONG


def resolve_on(shot, tier=None):
    """Frames per drawing, from the shot's own `on` or from its tier."""
    if isinstance(shot, Shot):
        return shot.on
    raw = shot if isinstance(shot, dict) else {}
    on = raw.get("on")
    if on is None:
        t = tier if tier is not None else raw.get("tier")
        on = ON_FOR_TIER.get(str(t).lower() if t else "", DEFAULT_ON)
    try:
        on = int(round(float(on)))
    except (TypeError, ValueError):
        on = DEFAULT_ON
    return min(max(on, 1), 6)


def quantise_frame(local_frame, on):
    """The drawing on screen at `local_frame`, held `on` frames at a time."""
    on = max(1, int(on))
    f = max(0, int(local_frame))
    return f - (f % on)


def quantise(t_local, on, fps):
    """Shot-local seconds -> the time of the drawing that is on screen."""
    fps = float(fps)
    # `+ 1e-6` because callers hand us `i / fps`, which for many rates is a
    # hair under the integer it stands for.
    f = int(math.floor(max(0.0, float(t_local)) * fps + 1e-6))
    return quantise_frame(f, on) / fps


def _seed_of(*parts):
    """A stable seed from strings and numbers.

    `hash()` is randomised per process and would give a forked worker a
    different answer from a fresh one, so it can never appear anywhere near a
    rendered picture.
    """
    h = 0
    for p in parts:
        h = zlib.crc32(str(p).encode("utf-8"), h & 0xFFFFFFFF)
    return h & 0x7FFFFFFF


def _impacts_of(raw, tl, start, end, tier, where, say):
    """Shot-local seconds at which something lands, for the ones override.

    A bare number is read as shot-local seconds — inside a shot that is what
    an author means. A time *reference* (`l3+0.4`) is absolute and is folded
    back to local. An `impact`-tier shot with no cue named puts the contact on
    the cut itself, which is where this style normally places one.
    """
    out = []
    dur = max(0.0, end - start)

    def add(v, what):
        if v is None:
            return
        if isinstance(v, (list, tuple)):
            for one in v:
                add(one, what)
            return
        if isinstance(v, dict):
            add(v.get("at", v.get("t")), what)
            return
        try:
            t = float(v)
        except (TypeError, ValueError):
            try:
                t = tl.resolve(v, what=f"{where}.{what}") - start
            except TimeError as exc:
                say(f"! {where}: {exc} — ignoring that impact cue")
                return
        if not (-1e-6 <= t <= dur + 1e-6):
            say(f"! {where}: impact cue at {t:+.2f}s is outside the shot "
                f"(0–{dur:.2f}s) — ignoring it")
            return
        out.append(min(max(t, 0.0), dur))

    add(raw.get("impact"), "impact")
    add(raw.get("accent"), "accent")
    for a in raw.get("actors") or []:
        if not isinstance(a, dict):
            continue
        add(a.get("impact"), "actor impact")
        sq = a.get("squash")
        if isinstance(sq, dict):
            add(sq.get("at"), "squash")
        elif sq is not None:
            add(sq, "squash")

    if not out and (tier or "").lower() == "impact":
        out.append(0.0)
    return tuple(sorted(set(out)))


#: A beat *identifier* — `b14`, `s3`, `12`. `compile.py` writes one of these
#: into a shot's `beat`, so it is not a beat *kind* and must not be matched
#: against one.
_BEAT_ID = re.compile(r"[a-z]{0,2}\d+")


def _beat_kind(raw):
    """The *kind* of beat a shot is, if the board actually says.

    `compile.py` writes the beat's **id** into `beat` (`"b14"`), not its kind,
    so reading `beat` alone means the kind checks below never fire on a
    compiled board. Ids are recognised and discarded here, and `kind`/`role`
    are consulted as well, so the named checks work on a hand-written board
    and the duration checks cover the compiled one.
    """
    if not isinstance(raw, dict):
        return ""
    for field in ("kind", "role", "beat_kind", "beat"):
        v = raw.get(field)
        if not isinstance(v, str):
            continue
        v = v.strip().lower()
        if v and not _BEAT_ID.fullmatch(v):
            return v
    return ""


def pacing_report(shot_list, fps=30):
    """Cutting-rhythm diagnostics: what is long, what is short, how often.

    Advisory only. The bands come from the style brief; a deliberate comic
    hold is allowed to run right past them, which is why nothing here raises.

    A board that names its beats (`kind: "reaction"`) gets those checked
    directly. A compiled board carries only ids, so the same shots are caught
    by duration against the same bands instead.
    """
    fps = float(fps)
    shots = list(shot_list)
    durs = [s.dur for s in shots]
    total = float(getattr(shot_list, "duration", sum(durs)) or sum(durs))
    n = len(shots)
    mean = (sum(durs) / n) if n else 0.0
    ordered = sorted(durs)
    median = ordered[n // 2] if n % 2 else (
        (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0 if n else 0.0)
    cpm = (n / (total / 60.0)) if total > 0 else 0.0

    notes = []
    if n >= 3 and not (PACE_MEAN[0] <= mean <= PACE_MEAN[1]):
        how = "slack" if mean > PACE_MEAN[1] else "frantic"
        notes.append(
            f"average shot is {mean:.2f}s — this style sits at "
            f"{PACE_MEAN[0]:.0f}–{PACE_MEAN[1]:.0f}s, so the cut reads {how}")
    if n >= 3 and total > 20 and not (
            PACE_CUTS_PER_MIN[0] <= cpm <= PACE_CUTS_PER_MIN[1]):
        notes.append(
            f"{n} cuts in {total:.0f}s is {cpm:.1f}/min — the genre runs "
            f"{PACE_CUTS_PER_MIN[0]:.0f}–{PACE_CUTS_PER_MIN[1]:.0f}/min "
            f"(the reference films measure 5.2 and 0.0)")

    for s in shots:
        kind = _beat_kind(s.raw)
        tier = (s.tier or "").lower()
        frames = int(round(s.dur * fps))
        # A locked-off camera is this style's *default* grammar, not an
        # oversight: the films it is calibrated against cut 5.2 and 0.0 times
        # a minute, and hold one composition while the weather and the
        # performance carry the frame. So a long take on a static camera is
        # not a shot that forgot to say `tier: hold` -- warning about it on
        # every well-formed film in the house style teaches the opposite of
        # what the style wants.
        locked = str((s.raw.get("camera") or {}).get("move", "")).lower() \
            in ("", "none", "static", "lock", "locked")
        if tier == "hold" and frames < MIN_HOLD_FRAMES:
            notes.append(
                f"'{s.id}' is a hold of {frames} frames ({s.dur:.2f}s) — under "
                f"{MIN_HOLD_FRAMES} frames it reads as a stumble, not a beat")
        if kind in ("reaction", "react", "cut-in", "cutin"):
            if not (PACE_REACTION[0] <= s.dur <= PACE_REACTION[1]):
                notes.append(
                    f"'{s.id}' is a reaction at {s.dur:.2f}s — those land at "
                    f"{PACE_REACTION[0]:.1f}–{PACE_REACTION[1]:.1f}s")
        elif kind in ("setup", "establish", "establishing", "reveal"):
            if not (PACE_SETUP[0] <= s.dur <= PACE_SETUP[1]):
                notes.append(
                    f"'{s.id}' is a {kind} shot at {s.dur:.2f}s — those need "
                    f"{PACE_SETUP[0]:.0f}–{PACE_SETUP[1]:.0f}s to be read")
        elif s.dur < PACE_REACTION[0] and tier != "impact":
            notes.append(
                f"'{s.id}' is {s.dur:.2f}s ({frames} frames) — under "
                f"{PACE_REACTION[0]:.1f}s only an impact cut reads; anything "
                f"an audience has to take in needs longer")
        elif s.dur > PACE_SETUP[1] and tier != "hold" and not locked:
            notes.append(
                f"'{s.id}' runs {s.dur:.2f}s on tier '{tier or 'none'}' — past "
                f"{PACE_SETUP[0]:.0f}–{PACE_SETUP[1]:.0f}s a shot is either a "
                f"reveal or a comic hold, and a hold should say so in `tier`")

    return {
        "shots": n,
        "duration": round(total, 3),
        "mean": round(mean, 3),
        "median": round(median, 3),
        "shortest": round(min(durs), 3) if durs else 0.0,
        "longest": round(max(durs), 3) if durs else 0.0,
        "cuts_per_min": round(cpm, 2),
        "holds": sum(1 for s in shots if s.is_hold),
        "impacts": sum(len(s.impacts) for s in shots),
        "notes": notes,
    }


def build(board, line_times=None, *, strict=True, warn=None):
    """Resolve a board's shots onto the finished film's clock.

    `line_times` is `audio.line_times(board, base_dir)` — a mapping of line id
    to `(start, end)`. A wordless board needs none, and then every shot must
    carry absolute seconds and an explicit `dur`.
    """
    tl = Timeline.from_board(board, line_times)
    raw_shots = board.get("shots") or []
    if not raw_shots:
        raise ShotError("board has no `shots` — there is no film to render")

    say = warn if warn is not None else (lambda msg: None)
    seed0 = int(board.get("seed", 0) or 0)

    shots = []
    for i, raw in enumerate(raw_shots):
        if not isinstance(raw, dict):
            raise ShotError(f"shot {i} is {type(raw).__name__}, not an object")
        sid = str(raw.get("id") or f"s{i + 1}")
        where = f"shot '{sid}'"
        if "at" not in raw:
            raise ShotError(f"{where} has no `at` — every shot needs a start")
        start = tl.resolve(raw["at"], what=where)

        if raw.get("until") is not None:
            end = tl.resolve(raw["until"], what=f"{where}.until")
        elif raw.get("dur") is not None:
            try:
                end = start + float(raw["dur"])
            except (TypeError, ValueError):
                raise ShotError(f"{where} has a non-numeric `dur`")
        else:
            raise ShotError(
                f"{where} has neither `until` nor `dur` — it never ends")

        if end <= start:
            raise ShotError(
                f"{where} ends at {end:.3f}s, at or before its start "
                f"{start:.3f}s")

        tier = raw.get("tier")
        if not raw.get("set"):
            raise ShotError(f"{where} names no `set`")

        shots.append(Shot(
            index=i, id=sid, start=start, end=end,
            set=str(raw["set"]), on=resolve_on(raw, tier), tier=tier,
            camera=raw.get("camera") or {},
            actors=list(raw.get("actors") or []),
            props=list(raw.get("props") or []),
            overlay=raw.get("overlay"),
            sfx=list(raw.get("sfx") or []),
            raw=raw,
            seed=_seed_of(seed0, sid),
            impacts=_impacts_of(raw, tl, start, end, tier, where, say),
        ))

    seen = {}
    for s in shots:
        if s.id in seen:
            raise ShotError(
                f"two shots share the id '{s.id}' (#{seen[s.id]} and #{s.index})"
                " — ids are how the camera and the overlays find them")
        seen[s.id] = s.index

    # Order and overlap. Shots are a *cut list*: two shots live at once is not
    # a dissolve here, it is an ambiguity about which one the frame shows.
    ordered = sorted(shots, key=lambda s: (s.start, s.index))
    if [s.index for s in ordered] != list(range(len(shots))):
        pairs = ", ".join(f"{a.id}@{a.start:.2f}" for a in ordered[:6])
        raise ShotError(
            "shots are out of order — they must be listed in the order they "
            f"play. Sorted by time they run: {pairs}...")

    gaps = []
    eps = 1e-6
    for a, b in zip(shots, shots[1:]):
        if b.start < a.end - eps:
            raise ShotError(
                f"shots '{a.id}' ({a.start:.3f}–{a.end:.3f}s) and '{b.id}' "
                f"({b.start:.3f}–{b.end:.3f}s) overlap by "
                f"{a.end - b.start:.3f}s. This style cuts; it cannot show two "
                "shots at once")
        if b.start > a.end + eps:
            gaps.append((a.id, b.id, a.end, b.start))

    if shots[0].start < -eps:
        raise ShotError(f"shot '{shots[0].id}' starts before the film does "
                        f"({shots[0].start:.3f}s)")

    for a, b, t0, t1 in gaps:
        say(f"! gap of {t1 - t0:.2f}s between '{a}' and '{b}' — holding "
            f"'{a}'s last frame across it")
    if shots[0].start > eps:
        say(f"! nothing is on screen for the first {shots[0].start:.2f}s — "
            f"holding '{shots[0].id}'s opening frame")

    shots_end = shots[-1].end
    if tl.lines:
        total = max(shots_end, tl.narration_end + tl.tail)
    else:
        # Wordless: absolute times are literal, and `tail` is the only thing
        # that can add time after the last cut.
        total = shots_end + tl.tail
    timing = board.get("timing", {}) or {}
    total = max(total, float(timing.get("min_duration", 0.0) or 0.0))
    tl.duration = total

    if strict and tl.lines:
        for lid, (a, b) in tl.lines.items():
            if b > total + 0.5:
                raise ShotError(
                    f"narration line '{lid}' ends at {b:.2f}s but the film is "
                    f"{total:.2f}s long — a line would be cut off")

    out = ShotList(shots, tl, total, gaps)
    for note in pacing_report(out, board.get("fps", 30) or 30)["notes"]:
        say(f"! pacing: {note}")
    return out


# ----------------------------------------------------------------- camera ----


@dataclass(frozen=True)
class View:
    """The rect the frame is cut from, in scene units."""

    cx: float
    cy: float
    zoom: float
    w: float
    h: float
    blur: float = 0.0       # whip-pan smear hint, 0..1

    @property
    def origin(self):
        """Scene coordinate at the image's top-left — `rig.draw`'s `origin`."""
        return (self.cx - self.w / 2.0, self.cy - self.h / 2.0)

    @property
    def rect(self):
        x0, y0 = self.origin
        return (x0, y0, x0 + self.w, y0 + self.h)

    def unit(self, pixel_width):
        """Pixels per scene unit for an image this wide."""
        return float(pixel_width) / self.w

    def to_screen(self, x, y, pixel_width, pixel_height):
        u = self.unit(pixel_width)
        x0, y0 = self.origin
        del pixel_height
        return ((x - x0) * u, (y - y0) * u)

    def as_dict(self):
        """What gets handed to `sets.draw_set` as `camera`."""
        return {"cx": self.cx, "cy": self.cy, "zoom": self.zoom,
                "w": self.w, "h": self.h,
                "x0": self.origin[0], "y0": self.origin[1],
                "blur": self.blur}


class Camera:
    """Evaluates one shot's camera at any shot-local time.

    Constructed once per shot and then called per frame. Pure: two calls with
    the same `t` give the same view, in any process, in any order.
    """

    def __init__(self, shot, scene, *, seed=0, warn=None):
        self.shot = shot
        self.warnings = []
        self.scene_w, self.scene_h = float(scene[0]), float(scene[1])
        cam = shot.camera if isinstance(shot.camera, dict) else {}
        self.spec = cam
        self.move = str(cam.get("move", "none") or "none").lower()
        if self.move not in MOVES:
            self.move = "none"
            self.unknown_move = str(cam.get("move"))
        else:
            self.unknown_move = None

        centre = (self.scene_w / 2.0, self.scene_h / 2.0)
        self.p0 = _point(cam.get("from"), centre)
        self.p1 = _point(cam.get("to"), self.p0)

        z = cam.get("zoom")
        if isinstance(z, (list, tuple)) and len(z) >= 2:
            z0, z1 = float(z[0]), float(z[1])
        elif isinstance(z, (int, float)):
            z0 = z1 = float(z)
        else:
            z0 = z1 = None
        # A push with no numbers still has to push, or the board's word for
        # the move means nothing.
        if self.move == "push":
            z0 = 1.0 if z0 is None else z0
            z1 = z0 * 1.12 if z1 is None or z1 == z0 else z1
        elif self.move == "pull":
            z0 = 1.12 if z0 is None else z0
            z1 = z0 / 1.12 if z1 is None or z1 == z0 else z1
        else:
            z0 = 1.0 if z0 is None else z0
            z1 = z0 if z1 is None else z1
        self.z0, self.z1 = max(z0, 1e-3), max(z1, 1e-3)

        self.ease = None
        self.hold = max(0.0, float(cam.get("hold", 0.0) or 0.0))
        self.pre_hold = max(0.0, float(cam.get("pre_hold", 0.0) or 0.0))
        self.subject = cam.get("subject")
        # Where in the frame a followed subject sits: 0..1 of width/height.
        fr = cam.get("frame") or cam.get("subject_frame") or (0.5, 0.56)
        self.frame_at = (float(fr[0]), float(fr[1]))
        self.dur = max(shot.dur, 1e-6)
        # Last, because a creep is only judged once its distance, its zoom and
        # the time it has to cross them are all known.
        self.ease = self._pick_ease(cam.get("ease"))
        self.seed = int(seed) ^ int(shot.seed)
        # A hold is the joke landing. The one thing that can ruin it is the
        # renderer being helpful, so on a hold-tier shot the drift the board
        # did not ask for is switched off and the frame is genuinely locked —
        # the character's own idle and the set's background business are the
        # only things left moving.
        self.still = bool(shot.is_hold and self.move in ("none", "handheld")
                          and not cam.get("from") and not cam.get("to")
                          and cam.get("zoom") is None)
        if self.still:
            self.move = "none"
            self.p1 = self.p0
            self.z1 = self.z0
        self._hh = self._handheld_table()
        if warn:
            for w in self.warnings:
                warn(w)

    def _pick_ease(self, asked):
        """Camera easing, with the mechanical curves refused.

        A camera that arrives at constant speed and simply stops is one of the
        named failures of this style: it reads as a machine, not as an
        operator finding a frame. Anything that does not decelerate into its
        final framing is swapped for one that does, and said out loud.

        `creep` is the single exemption, and it is exempt on the opposite
        grounds rather than as a loophole: it is a move designed not to be
        perceived at all, and constant rate is the only shape that neither
        spikes on departure nor freezes on arrival. See :data:`CREEP_EASE`.
        """
        default = WHIP_EASE if self.move == "whip" else CAMERA_EASE
        if asked is None or asked == "":
            return default
        name = str(asked).lower()
        if name == CREEP_EASE:
            self._check_creep()
            return name
        if name in MECHANICAL_EASES and self.move != "none":
            self.warnings.append(
                f"shot '{self.shot.id}': camera ease '{name}' does not "
                f"decelerate into its final framing — using '{default}' "
                f"(a move that must not be *noticed* wants '{CREEP_EASE}')")
            return default
        return name

    def _check_creep(self):
        """A creep exists to stop a long shot freezing. Say so when it won't.

        Two ways to write one that does not work, both of which look fine in
        the board and neither of which the renderer can fix on the author's
        behalf: too slow to move a pixel, or given a settle that puts the
        frozen tail straight back.
        """
        rate = self._creep_rate()
        if self.move == "none":
            self.warnings.append(
                f"shot '{self.shot.id}': camera move is 'none', so there is "
                f"nothing for '{CREEP_EASE}' to slow down — a creep needs a "
                f"move ('push' with a small zoom is the usual one)")
        elif rate is not None and rate < CREEP_MIN_RATE:
            self.warnings.append(
                f"shot '{self.shot.id}': a creep of {rate * 100:.2f}%/s is "
                f"under {CREEP_MIN_RATE * 100:.1f}%/s and will still render "
                f"runs of identical frames — a creep has to cross about "
                f"{CREEP_MIN_RATE * self.shot.dur * 100:.0f}% of the view "
                f"over {self.shot.dur:.1f}s to keep every frame different")
        settle = self.hold + self.pre_hold
        if settle > CREEP_MAX_SETTLE:
            self.warnings.append(
                f"shot '{self.shot.id}': a creep with {settle:.2f}s of "
                f"hold/pre_hold is locked off for that long — past "
                f"{CREEP_MAX_SETTLE:.1f}s that settle is itself the frozen "
                f"run the creep was added to prevent")

    def _creep_rate(self):
        """How fast a creep crosses the frame, as a fraction of the view per
        second — the quantity that decides whether a frame changes at all.

        Both halves of the move count: the translation, measured against the
        view it is crossing, and the zoom, whose edges travel even when the
        centre does not.
        """
        span = max(self.dur - self.hold - self.pre_hold, 1e-6)
        w = max(self.scene_w, 1e-6) / max(self.z0, 1e-3)
        h = max(self.scene_h, 1e-6) / max(self.z0, 1e-3)
        travel = math.hypot((self.p1[0] - self.p0[0]) / w,
                            (self.p1[1] - self.p0[1]) / h)
        # A zoom of 1 -> 1+k walks each edge k/2 of the way across the view.
        zoom = abs(self.z1 - self.z0) / max(self.z0, 1e-3) / 2.0
        return (travel + zoom) / span

    # -- progress ----------------------------------------------------------

    def progress(self, t):
        """Eased 0..1 through the move, with the settle and pre-hold taken out.

        `hold` is the settle before the cut. A move that runs right up to the
        cut is still travelling when the picture changes, and the eye reads
        the cut as a mistake rather than as a decision.
        """
        span = self.dur - self.hold - self.pre_hold
        if span <= 1e-6:
            return 1.0 if t >= self.dur - self.hold else 0.0
        u = (float(t) - self.pre_hold) / span
        return ease(self.ease, min(max(u, 0.0), 1.0))

    # -- the view ----------------------------------------------------------

    def view(self, t, subject=None):
        """The view rect at shot-local time `t`.

        `subject` is only consulted by `follow`: either an `(x, y)` scene
        position or a callable `f(t) -> (x, y)`, which lets the follow lag
        behind the actor by sampling them slightly in the past.
        """
        t = float(t)
        u = self.progress(t)
        zoom = self.z0 + (self.z1 - self.z0) * u
        blur = 0.0

        if self.move == "follow":
            cx, cy = self._follow_centre(t, subject, zoom)
        else:
            cx = self.p0[0] + (self.p1[0] - self.p0[0]) * u
            cy = self.p0[1] + (self.p1[1] - self.p0[1]) * u

        if self.move == "handheld" and not self.still:
            dx, dy, dz = self._handheld(t, zoom)
            cx += dx
            cy += dy
            zoom *= dz

        w = self.scene_w / zoom
        h = self.scene_h / zoom

        if self.move == "whip":
            # A whip is defined by how fast it is, so the smear hint is
            # measured rather than declared: sample the centre a frame either
            # side and normalise by the width of the view.
            dt = 1.0 / 60.0
            ax = self._centre_only(max(0.0, t - dt))
            bx = self._centre_only(min(self.dur, t + dt))
            speed = math.hypot(bx[0] - ax[0], bx[1] - ax[1]) / (2 * dt)
            blur = min(1.0, speed / max(w * 1.6, 1e-6))

        return View(cx, cy, zoom, w, h, blur)

    def _centre_only(self, t):
        u = self.progress(t)
        return (self.p0[0] + (self.p1[0] - self.p0[0]) * u,
                self.p0[1] + (self.p1[1] - self.p0[1]) * u)

    def _follow_centre(self, t, subject, zoom):
        pos = _subject_pos(subject, t)
        if pos is None:
            # Nothing to follow: fall back to the authored path rather than
            # snapping to the middle of the set, which would silently discard
            # a composition the board did state.
            return self._centre_only(t)
        if callable(subject):
            lag = _subject_pos(subject, max(0.0, t - FOLLOW_LAG))
            if lag is not None:
                mix = FOLLOW_LAG_MIX
                pos = (pos[0] * (1 - mix) + lag[0] * mix,
                       pos[1] * (1 - mix) + lag[1] * mix)
        w = self.scene_w / zoom
        h = self.scene_h / zoom
        fx, fy = self.frame_at
        # Keeping the subject at `fx` of the width means the view's left edge
        # sits `fx * w` to their left.
        return (pos[0] + (0.5 - fx) * w, pos[1] + (0.5 - fy) * h)

    # -- handheld ----------------------------------------------------------

    def _handheld_table(self):
        """Per-shot amplitudes and phases for the chopper camera.

        Seeded from the board seed and the shot id, so the same shot drifts
        the same way every render and two different shots never drift alike.
        """
        rows = []
        s = self.seed or 1
        for k, (fx, fy) in enumerate(zip(HH_FREQ_X, HH_FREQ_Y)):
            px = ((_seed_of(s, "px", k) % 100000) / 100000.0) * 2 * math.pi
            py = ((_seed_of(s, "py", k) % 100000) / 100000.0) * 2 * math.pi
            # Weight the slowest component heaviest: the frame should wander,
            # and only then wobble.
            wt = 1.0 / (k + 1.0)
            rows.append((fx, px, fy, py, wt))
        norm = sum(r[4] for r in rows) or 1.0
        return [(fx, px, fy, py, wt / norm) for fx, px, fy, py, wt in rows]

    def _wander(self, t, w, h):
        x = y = 0.0
        for fx, px, fy, py, wt in self._hh:
            x += wt * math.sin(2 * math.pi * fx * t + px)
            y += wt * math.sin(2 * math.pi * fy * t + py)
        return x * HH_AMP_X * w, y * HH_AMP_Y * h

    def _handheld(self, t, zoom):
        """A drift plus the operator quietly correcting it.

        The correction is a delayed, inverted copy of the wander: the frame
        goes somewhere, and about a second and a half later most of it comes
        back. It is deliberately *not* a spring — a spring rings, and a rung
        camera is a shake.
        """
        w = self.scene_w / zoom
        h = self.scene_h / zoom
        # A shot-local clock would start every handheld shot at the same point
        # in the same wave. Ride the film's clock instead.
        tt = self.shot.start + t
        wx, wy = self._wander(tt, w, h)
        cx, cy = self._wander(tt - HH_CORRECT_LAG, w, h)
        dz = 1.0 + HH_ZOOM * math.sin(2 * math.pi * 0.05 * tt + (self.seed % 628) / 100.0)
        return wx - HH_CORRECT * cx, wy - HH_CORRECT * cy, dz


def _point(v, default):
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return (float(v[0]), float(v[1]))
    return (float(default[0]), float(default[1]))


def _subject_pos(subject, t):
    if subject is None:
        return None
    if callable(subject):
        p = subject(t)
    else:
        p = subject
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return (float(p[0]), float(p[1]))
    return None


# ----------------------------------------------------------------- actors ----


def actor_at(actor, t_local, dur):
    """Where an actor's pelvis is at a shot-local time, in scene units.

    The board's `at` is a fixed position, which is all a locked-off shot
    needs. Two optional extras are honoured because a `follow` camera is
    meaningless without them: `to`, which travels the actor across the shot,
    and an `at` on any action keyframe, which gives them a path.
    """
    base = _point(actor.get("at"), (50.0, 44.0))
    dur = max(float(dur), 1e-6)
    t = min(max(float(t_local), 0.0), dur)

    keys = []
    action = actor.get("action")
    if isinstance(action, list):
        for k in action:
            if isinstance(k, dict) and k.get("at") is not None:
                keys.append((float(k.get("t", 0.0)), _point(k["at"], base),
                             k.get("ease", KEY_EASE)))
    if keys:
        keys.sort(key=lambda k: k[0])
        if t <= keys[0][0]:
            return keys[0][1]
        if t >= keys[-1][0]:
            return keys[-1][1]
        for (ta, pa, _), (tb, pb, eb) in zip(keys, keys[1:]):
            if ta <= t <= tb:
                u = ease(eb, (t - ta) / max(tb - ta, 1e-6))
                return (pa[0] + (pb[0] - pa[0]) * u,
                        pa[1] + (pb[1] - pa[1]) * u)

    if actor.get("to") is not None:
        end = _point(actor["to"], base)
        u = ease(actor.get("ease", "linear"), t / dur)
        return (base[0] + (end[0] - base[0]) * u,
                base[1] + (end[1] - base[1]) * u)
    return base


def actor_phase(actor, t_pose, *, wrap=True):
    """The cycle phase for an actor at a (quantised) time.

    `rate` is cycles per second, so 1.0 is roughly two steps a second, and
    `phase` offsets one walker from another so a crowd is not in lockstep.

    Wrapped to `0..1` by default, which is all a cycle needs. `wrap=False`
    returns the running total instead, for the one caller that needs the
    phase to be monotone — a gait asked to carry its own travel advances by
    `stride_units` per whole cycle, and a wrapped phase would snap it back a
    full stride every time it came round.
    """
    rate = float(actor.get("rate", 1.0) or 0.0)
    p = float(actor.get("phase", 0.0)) + float(t_pose) * rate
    return p % 1.0 if wrap else p


def actor_travel(actor, t_local, dur):
    """How far the board has carried this actor along x since the cut, in
    scene units. Signed: negative is screen-left."""
    return float(actor_at(actor, t_local, dur)[0]
                 - actor_at(actor, 0.0, dur)[0])


def stages_travel(actor, dur, eps=1e-6):
    """Does the board move this actor across the shot, rather than pose them
    on the spot?

    True when a `to` or an action keyframe path actually displaces them along
    x. That is the question that decides who owns the trajectory: the board,
    or the gait.
    """
    if not isinstance(actor, dict):
        return False
    dur = max(float(dur), 1e-6)
    xs = [actor_at(actor, dur * i / 8.0, dur)[0] for i in range(9)]
    return (max(xs) - min(xs)) > float(eps)


def gait_phase(actor, t_local, dur, *, stride, facing=1):
    """The cycle phase that keeps a planted foot planted, given the board's
    own trajectory.

    A gait plants its feet against **its own** travel: through stance the
    foot's position relative to the pelvis slides backwards at exactly the
    stride rate, so that a pelvis advancing at that same rate leaves the foot
    still. Drive the cycle at any other rate and the difference is foot slide,
    which is the single loudest tell of a procedural walk.

    So when the board owns the trajectory — an actor with a `to`, or a
    keyframed path — the *phase* is what has to give, not the framing. This
    returns the phase implied by the distance actually travelled:

        phase(t) = phase0 + travel(t) / (facing * stride)

    which plants the foot whether or not the board's `to` happens to agree
    with `rate x stride_units x dur`. The board's `rate` is only a request for
    a cadence; the ground has the casting vote.
    """
    stride = float(stride)
    p0 = float(actor.get("phase", 0.0))
    if abs(stride) < 1e-9:
        return actor_phase(actor, t_local)
    facing = -1.0 if float(facing or 1) < 0 else 1.0
    return (p0 + actor_travel(actor, t_local, dur) / (facing * stride)) % 1.0


def implied_rate(actor, dur, *, stride):
    """The cadence, in cycles per second, that `gait_phase` will actually
    run at. Compared against the board's `rate` to tell an author that their
    walk is about to be retimed to fit the distance they asked for."""
    dur = max(float(dur), 1e-6)
    stride = float(stride)
    if abs(stride) < 1e-9:
        return float(actor.get("rate", 1.0) or 0.0)
    return abs(actor_travel(actor, dur, dur)) / abs(stride) / dur


# --------------------------------------------------------------- timeline ----


def timeline_document(board, shot_list, *, fps=30, width=None, height=None,
                      output=None):
    """The `<stem>.timeline.json` sidecar.

    The plan's clock and the render's clock are not the same one: the plan is
    built from raw narration clips that still carry the recorder's silence,
    and the renderer trims it. `motionprofile.py` re-resolves the plan's
    line-relative times against `lines` here before it compares a plan to a
    film, so this file is the only thing that makes that comparison honest.
    """
    tl = shot_list.timeline
    return {
        "schema": 1,
        "style": board.get("style", "2d-animation"),
        "title": board.get("title"),
        "output": output,
        "duration": round(shot_list.duration, 3),
        "fps": int(fps),
        "width": int(width) if width else None,
        "height": int(height) if height else None,
        "lead_in": round(tl.lead_in, 3),
        "tail": round(tl.tail, 3),
        "lines": [{"id": lid, "start": round(a, 3), "end": round(b, 3)}
                  for lid, (a, b) in tl.lines.items()],
        "shots": [{"id": s.id, "start": round(s.start, 3),
                   "end": round(s.end, 3), "tier": s.tier, "on": s.on,
                   "set": s.set,
                   "impacts": [round(t, 3) for t in s.impacts],
                   "camera": str((s.camera or {}).get("move", "none")),
                   "ease": str((s.camera or {}).get("ease") or "")}
                  for s in shot_list],
        "parallax": dict(PARALLAX),
        "pacing": pacing_report(shot_list, fps),
    }
