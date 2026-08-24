# The rig

A character in this style is **not a picture that moves**. It is a skeleton
evaluated every frame from a *pose*, and drawn as tapered shapes.

That distinction is the whole style. A cutout that slides across the screen
reads as a slideshow with ambition; a rig that leans into its own acceleration,
plants a foot and lets its head lag half a frame behind its shoulders reads as
animation, even at six drawings a second.

---

## Coordinate system

**Scene units, not pixels.** A shot is composed in a `100 × 56.25` unit box
(16:9) or `56.25 × 100` (9:16). The renderer maps that box onto the output
frame, so the same board renders at any resolution and in either aspect.

- `x` increases to the **right**, `y` increases **downward** (PIL's convention).
- Ground level in a standard street shot is `y = 44`.
- A default adult character is **18 units** tall, head to heel.

Angles are **degrees**, and **positive is clockwise on screen**. Every angle is
measured **relative to the parent bone's direction**, so a pose of all zeros is
a character standing to attention.

> Relative angles are not a stylistic choice. They are what makes a wave
> compose with a lean: rotate the spine and the arm comes with it, without the
> arm's own keys having to know the spine moved.

---

## The skeleton

```
                    crown
                      │  head
                  head-base
                      │  neck
  hand.l ── wrist.l ─ chest ─ wrist.r ── hand.r
         elbow.l  │      │      │  elbow.r
      shoulder.l ─┘      │      └─ shoulder.r
                         │  spine
                       pelvis  ← the root
                      ╱      ╲
                 hip.l        hip.r
                   │            │
                knee.l        knee.r
                   │            │
                ankle.l       ankle.r
                   │            │
                foot.l        foot.r
```

Fifteen joints in four chains. `pelvis` is the root and carries no angle of its
own — it has a position instead.

### Rest directions

The direction a bone points when its angle is `0`:

| chain | joint | parent direction at rest |
|---|---|---|
| spine | `spine` | **up** (`−y`) |
| | `neck` | continues `spine` |
| | `head` | continues `neck` |
| arms | `shoulder.l` / `shoulder.r` | **down** (`+y`) — the reverse of the spine |
| | `elbow.*` | continues the upper arm |
| | `wrist.*` | continues the forearm |
| legs | `hip.l` / `hip.r` | **down** (`+y`) |
| | `knee.*` | continues the thigh |
| | `ankle.*` | continues the shin |

So `{"shoulder.r": -90}` raises the right arm forward to horizontal, and
`{"spine": 8, "shoulder.r": -90}` raises it from an already-leaning torso
without any extra arithmetic.

### Bone lengths

Proportions are ratios of total height `H`, so one number scales a character.
`rig.BONES` is the master table:

| `BONES` key | bone | length |
|---|---|---|
| `spine` | pelvis → chest | `0.262 H` |
| `neck` | chest → head-base | `0.042 H` |
| `head` | head-base → crown | `0.247 H` |
| `upper_arm` | shoulder → elbow | `0.146 H` |
| `forearm` | elbow → wrist | `0.136 H` |
| `hand` | wrist → hand | `0.052 H` |
| `thigh` | hip → knee | `0.206 H` |
| `shin` | knee → ankle | `0.190 H` |
| `foot` | ankle → toe | `0.070 H` |

That head is a quarter of the figure, which puts `HEADS_TALL` at **4.17** — a
cartoon proportion, not a human one. It is deliberate: at broadcast size a
realistic eight-heads-tall figure has a head too small to act with, and the
acting in this style is almost entirely in the head.

A whole different build is `pose["bones"]`, either a partial `{bone: ratio}`
override or a name from `rig.BONE_VARIANTS`:

| variant | `head` | `spine` | `thigh` | `shin` | `upper_arm` | `forearm` |
|---|---|---|---|---|---|---|
| `default` | `0.247` | `0.262` | `0.206` | `0.190` | `0.146` | `0.136` |
| `kid` | `0.290` | `0.222` | `0.196` | `0.180` | `0.130` | `0.120` |
| `heavy` | `0.240` | `0.252` | `0.208` | `0.192` | `0.140` | `0.128` |
| `lanky` | `0.222` | `0.252` | `0.246` | `0.228` | `0.162` | `0.152` |

(`default` is stored as an empty dict — "no overrides" — so the row above is
just `BONES` again.) Each variant is a *partial* table: `neck`, `hand` and
`foot` are never overridden, so a `kid` still has adult-proportioned
extremities, which is exactly what makes the big head read as young rather
than as a scaled-down adult.

`height` on the actor scales; `bones` changes the shape. A crowd of one build at
five heights still reads as one character five times.

Head width is `HEAD_W = 0.222 H` — about as wide as the head is tall — shoulder
half-width `SHOULDER_HALF = 0.105 H`, hip half-width `HIP_HALF = 0.078 H`. The
rig is drawn three-quarters-on, so only `DEPTH = 0.30` of the shoulder and hip
offsets projects onto the screen: enough to separate the near and far limbs,
not enough to read as a twist. Limb thicknesses live in a second table,
`rig.WIDTHS`, keyed by `neck` `chest` `waist` `hip` `upper_arm` `elbow` `wrist`
`hand` `thigh` `knee` `ankle` `shoe` — a limb is a taper between two of them,
which is why a forearm reads as an arm rather than as a stick.

Four derived constants matter when you are placing a character rather than
posing one:

| constant | value | is |
|---|---|---|
| `SOLE` | `0.034 H` | ankle → ground, i.e. the thickness of a shoe |
| `LEG` | `0.396 H` | thigh + shin |
| `PELVIS_TO_SOLE` | `0.41614 H` | pelvis height above the ground when standing |
| `CROWN_TO_SOLE` | `0.96714 H` | crown → sole, with the legs at rest |

`CROWN_TO_SOLE` is a little under `1.0` because the resting legs are not
locked straight; `H` is the design height, not a measurement of any one pose.

`rig.ground_pelvis(ground_y, height=18.0, bones=None)` turns a ground line into
the `at` that stands a character on it. Use it rather than arithmetic —
`44.0` happens to be the street ground line, but the pelvis does not sit at
`44.0`, and a `kid` or `lanky` build does not sit where `default` does.

---

## A pose

A pose is plain JSON, so it can be stored in a storyboard, interpolated,
blended and diffed.

```json
{
  "at": [50.0, 44.0],
  "facing": 1,
  "height": 18.0,
  "squash": 1.0,
  "tilt": 0.0,
  "joints": {
    "spine": 4, "neck": -2, "head": -3,
    "shoulder.l": 12, "elbow.l": -18, "wrist.l": 0,
    "shoulder.r": -14, "elbow.r": -22, "wrist.r": 0,
    "hip.l": -18, "knee.l": 26, "ankle.l": -8,
    "hip.r": 16, "knee.r": 8, "ankle.r": -4
  },
  "face": {
    "brow": -0.4,
    "eyes": "wide",
    "mouth": "oh",
    "look": [0.3, -0.1]
  }
}
```

| field | meaning |
|---|---|
| `at` | **pelvis** position, scene units — not the feet. See below |
| `facing` | `1` faces right, `-1` faces left. Mirrors the *drawing*, never the angles |
| `height` | head-to-heel height in scene units. Default `18` |
| `squash` | area-preserving vertical scale. `0.85` squashes, `1.15` stretches; width compensates as the **plain reciprocal** `1/squash` — not `1/√squash` — so `0.75` tall reads `1.33` wide. See [why](#why-squash_scale-is-a-reciprocal-and-not-a-square-root) |
| `tilt` | whole-body rotation about the pelvis, degrees |
| `joints` | any subset. **A missing joint is `0`**, so a pose only states what it changes |
| `bones` | optional build override — a partial `BONES` dict, or a name |
| `face` | see below |

### `at` is the pelvis, and this catches people

`solve` puts `pelvis` exactly at `at` and hangs the rest of the body off it, so
a character's feet land about `PELVIS_TO_SOLE × height` **below** the number
you wrote. That is deliberate — the pelvis is the root, and it is the only
landmark that does not move when a leg does — but it means `at` is not a
"stand here" coordinate.

Two consequences worth internalising:

- The street convention `"at": [x, 44]` puts the pelvis on the kerb line and
  the **feet out in the road**, roughly `y = 51`. That is the shot `street` is
  composed for, and it is what `compile.py` stages by default.
- To put the *feet* on a specific line, ask for it:
  `rig.ground_pelvis(44.0)` → `36.51`. A character posed there stands on the
  kerb, on the pavement, in front of the shopfronts.

Neither is wrong; they are different shots. Get them the wrong way round and
a character either wades or floats, which the contact sheet shows immediately.

### `face`

| field | values |
|---|---|
| `brow` | a name from `rig.BROWS`, or the `-1..1` scalar. Default `0` |
| `eyes` | `open` (default) `wide` `shut` `squint` `dead` |
| `mouth` | `line` (default) `open` `oh` `gasp` `wide` `grin` `frown` |
| `look` | `[dx, dy]`, each `-1..1` — pupil offset within the eye |

The seven brow presets are `neutral` `surprised` `angry` `sad` `confused`
`strain` `smug`, each an explicit `((tilt, lift), (tilt, lift))` pair — far brow
first. `confused` and `smug` are **asymmetric**, which no scalar can express,
and that is why the named form exists alongside the number. The scalar still
works: `-1` is angry, `+1` is raised and worried, and an unknown name falls
back to `neutral` rather than to nothing.

Anything not in those lists is drawn as the default rather than guessed at.
The whites are the one colour not taken from the palette (`rig.SCLERA`);
everything else on the face is drawn in `ink`.

**The face carries the comedy.** At the sizes these films play at, an audience
reads the silhouette and the face; the elbows are decoration. When a beat is
funny, the budget goes to `brow` and `mouth`, not to the arms. The brow is the
heaviest thing on the face for exactly that reason.

---

## Module contract — `rig.py`

```python
JOINTS: tuple[str, ...]         # the fifteen, in solve order
REST: dict[str, float]          # every joint -> 0.0
BONES: dict[str, float]         # bone name -> length as a fraction of H
BONE_VARIANTS: dict[str, dict]  # "default" | "kid" | "heavy" | "lanky"
WIDTHS: dict[str, float]        # limb thickness at each landmark
BROWS: dict[str, tuple]         # brow preset -> ((tilt, lift), (tilt, lift))
SCLERA: RGB                     # the one colour not from the palette
DEFAULT_HEIGHT = 18.0           # scene units, head to heel
HEADS_TALL  ~= 4.17             # cartoon proportion, derived from BONES
SS = 3                          # supersample factor for `draw`
INK_W = 0.005                   # body outline weight, fraction of H
FACE_W ~= 0.00286               # face detail weight — 4/7 of INK_W

def bones_for(pose: dict | None) -> dict[str, float]:
    """The bone table a pose is drawn with. `pose["bones"]` may be a name
    from `BONE_VARIANTS` or a partial dict of overrides; anything absent
    falls back to `BONES`, and an unknown bone name is ignored rather than
    added. (Not `pose["build"]` — that is `compile.py`'s overall size
    multiplier, a different thing.)"""

def signed_angle(u, v) -> float:
    """Degrees from `u` to `v`, positive clockwise on screen — the same
    convention every joint angle uses."""

def ground_pelvis(ground_y: float, height: float = DEFAULT_HEIGHT,
                  bones: dict | None = None) -> float:
    """The pelvis `y` that stands a character of `height` on `ground_y`."""

def squash_scale(squash: float) -> tuple[float, float]:
    """`(width_scale, height_scale)`. Exactly area-preserving: `(1/s, s)`."""
def outline_of(fill, *, darken=0.40, saturate=0.10, floor=0.06):
    """The outline colour for a fill: same hue, +0.10 saturation, -0.40
    lightness, never below `floor`. This is why nothing is drawn in
    `#000000`."""

def solve(pose: dict) -> dict:
    """Pose -> absolute scene-unit points for every joint.

    Twenty landmarks: "pelvis", "chest", "head_base", "crown",
    "shoulder.l/.r", "elbow.l/.r", "wrist.l/.r", "hand.l/.r",
    "hip.l/.r", "knee.l/.r", "ankle.l/.r", "foot.l/.r".
    Applies facing, height, squash and tilt. Pure — no drawing, no globals,
    and it does not mutate the pose it is given.
    """

def draw(img, pose: dict, look, *, unit: float, origin=(0.0, 0.0),
         z: float = 1.0, shadow: bool = True, ground: float | None = None):
    """Draw one character onto a PIL image.

    `unit`   pixels per scene unit
    `origin` scene-unit coordinate at the image's top-left
    `look`   a palette dict from look.py (see below)
    `z`      depth, 0..1; distant figures are hazed towards the sky colour
    `shadow` draw the contact ellipse. `render.py` passes **False** and draws
             it itself, so that actors and props share one shadow language
    `ground` the ground line to drop the shadow onto, when `shadow` is on
    Draws at SS× supersample internally and composites down through LANCZOS.
    """

def bbox(pose: dict) -> tuple[float, float, float, float]:
    """Scene-unit (x0, y0, x1, y1) the drawn character occupies, ink and
    drawn volume included. Used to place the contact shadow, to keep actors
    from overlapping, and to frame the camera."""
```

`draw` is **pure with respect to the pose** — the same pose, palette and
`unit` produce identical pixels every time. Determinism is verified by
`render.py --self-test`, which renders a short window at `-j 1` and `-j 4`
and compares SHA-256.

### Why `squash_scale` is a reciprocal and not a square root

`squash_scale(s)` returns `(1/s, s)`. The obvious-looking alternative,
`(1/√s, s)`, is the formula you would use to preserve *volume* in three
dimensions — and it is wrong here, so before "fixing" it, read this.

A flat character has no third dimension to borrow from. Its silhouette is the
whole performance, and the quantity an audience reads as *volume* is the area
of that silhouette. Area is `width × height`, so preserving it forces
`width = 1/height` exactly. The reference table is built the same way and
proves it: hard landing `0.75` tall by `1.30` wide, jump apex `1.18` by
`0.88`. Multiply either pair out and you get ≈ 1.0. Under the square root the
same landing would draw `1.155` wide, the figure would lose about 13% of its
area at the moment of impact, and it would read as *deflating* rather than as
compressing — the puncture-and-parp of a bad rig instead of the weight of a
good one.

The code is the exact reciprocal, so it draws a `0.75` squash at `1.333` wide
rather than the table's `1.30`. The table is the artist's reference target;
`squash_scale` is arithmetic, and the 3% is not visible.

---

## Module contract — `poses.py`

Cycles are **procedural phase functions**, never keyframe tables. A phase
function costs nothing to store, cannot desync, and retimes for free.

```python
def stand(phase: float = 0.0, **kw) -> dict   # idle: breathing, weight shift, blink
def walk(phase: float = 0.0, **kw) -> dict    # one full stride per phase 0..1
def run(phase: float = 0.0, **kw) -> dict
def panic(phase: float = 0.0, **kw) -> dict   # scramble, arms flailing overhead
def drive(phase: float = 0.0, **kw) -> dict   # seated, hands at ten-and-two
def point(phase: float = 0.0, dir: int = 1, **kw) -> dict
def react(phase: float = 1.0, kind: str = "shock", **kw) -> dict

POSES: dict[str, callable]   # the seven above, by name, for the compiler
STRIDES: dict[str, float]    # walk 0.58, run 1.00, panic 0.72 — stride/H
WALK / RUN / SCRAMBLE        # the gait parameter dicts
GROUND = 44.0                # the standard street ground line
FPS = 30
IDLE_CYCLE_S = 3.0           # one full idle cycle
BLINK_AT = 0.90              # where in that cycle the blink lands
BLINK_FRAMES = 4             # ...and how long it lasts
ANTICIPATION_FRAMES          # action -> (wind-up frames, hold-at-peak frames)

def stride_units(name: str, height: float = 18.0) -> float:
    """Scene units covered by one cycle. `rate` × this = units per second,
    which is how you stop a runner moonwalking across a `to`."""

def blend(a: dict, b: dict, t: float) -> dict:
    """Interpolate two poses. Angles blend on the shortest arc; `at`, `height`,
    `squash` and `tilt` blend linearly; `face` snaps at t >= 0.5 — an eye is
    open or shut, never half."""
```

`react`'s `kind` is one of **`shock` `dismay` `glee` `brace`**, and its `phase`
defaults to `1.0` — a reaction is normally wanted fully arrived, not at the
start of its own wind-up. Every pose takes `height`, `facing`, `at`/`ground`
and the face overrides `eyes`, `mouth`, `brow`, `look` as keyword arguments;
`render.py` forwards anything on the actor it does not recognise, which is how
`{"action": "point", "dir": -1}` and `{"action": "react", "kind": "glee"}`
reach the function from the board.

`phase` is `0..1` and **wraps**. `walk(0.0)` and `walk(1.0)` are the same
drawing — every joint angle is identical, and the only difference is `at`,
which has advanced by exactly one `stride_units` (`50.0 → 60.44` at the
default height). Anything else and the cycle would visibly pop once per
stride. `point` and `react` are one-shots instead — `phase` is progress, and
past `1.0` they keep going as a *held* drawing with breath and a blink in it,
so a long hold on a point stays alive rather than freezing.

`ANTICIPATION_FRAMES` is the timing table the wind-ups are built from, in
frames at 30 fps, as `(wind-up, hold at the peak)`:

| action | wind-up | hold |
|---|---|---|
| `head_turn` | 3 | 2 |
| `run_start` | 5 | 2 |
| `jump` | 7 | 3 |
| `reaction` | 12 | 4 |

Those numbers are not applied by hand at each call site. `poses._windup(t)` is
the house move expressed as a single curve, and every one-shot in the module
rides it:

```python
def _windup(t, *, wind=0.28, hold=0.12, depth=0.20,
            overshoot=0.12, decay=3.5) -> float
    # 0 -> -depth -> (hold there) -> 1, overshooting by `overshoot`
```

Three beats, in order: the pose moves *against* its target by `depth`, stops
dead there for `hold` of the move, then departs fast, passes the target by
`overshoot` and settles. `_windup(0)` is exactly `0.0` and `_windup(1)` is
exactly `1.0`, so it is safe to key against without the endpoints drifting.
It is private, but knowing it exists explains why every reaction in this style
has the same weight to it — and why a pose you write yourself that interpolates
straight from A to B will not match the ones that ship.

### The rules a cycle obeys

1. **A planted foot does not slide.** During its stance half the foot is fixed
   in scene space and the pelvis travels over it, solved through two-bone IK.
   Sliding feet are the single loudest tell of procedural animation.
2. **The pelvis oscillates twice per stride**, rising over the planted leg and
   dropping through the pass. `WALK["bob"]` is `0.012 H`; `RUN` is `0.026 H`
   and `SCRAMBLE` — which `panic` rides — is `0.030 H`.
3. **Arms oppose legs.** Right arm forward with left leg. Nothing looks more
   broken than a same-side swing.
4. **The head lags.** `poses.HEAD_LAG = 0.08` of a cycle behind the chest on
   any direction change — this is follow-through, and it is most of what sells
   weight. `anim.HEAD_LAG` is the same idea in seconds (`0.083`, two and a half
   frames at 30 fps) for keyframed acting.

### Travel, and why `stride_units` exists

A cycle plants its feet **against its own travel**: `walk` moves the pelvis
`stride_units("walk", H)` — `10.44` units at the default height — over one
phase. `render.py` drives an actor's position from the board instead, so the
board has to agree with the cycle or rule 1 breaks in the one way an audience
notices immediately.

For an actor crossing at `v` units per second, the phase rate is
`v / stride_units(action, height)` cycles per second. Going the other way:
with `rate` and a shot duration `d`, set `to` so that
`to.x - at.x == rate × stride_units(action, height) × d`. Anything else and
the feet skate.

The alternative is a **treadmill**: pass `travel: false` on the actor, keep
`at` fixed, and move the set under them with a `track` camera. That is how a
run across a long street is normally shot in this style, because it never
drifts.

### The idle is where the blink lives

`stand()` blinks by shutting the eyes for `BLINK_FRAMES` (4) at `BLINK_AT`
(phase `0.90`) — once per cycle. **The cadence is therefore the actor's `rate`,
not a constant.** One cycle is `IDLE_CYCLE_S = 3.0` seconds, so an actor driven
at `rate: 0.33` blinks every **90 frames**, inside the 72–96 band
[`animation-principles.md`](animation-principles.md) asks for. At the default
`rate: 1.0` a character blinks every 30 frames, which reads as a nervous tic.
Pass `blink: false` to switch it off for a beat.

The idle is also deliberately **asymmetrical** — weight on the right leg, left
foot back and turned out, right hand hanging lower, head off-axis by four
degrees. Contrapposto. A mirrored idle is one of the loudest tells of a rig.

---

## Module contract — `anim.py`

```python
EASES: dict[str, callable]
FPS = 30
HEAD_LAG = 0.083        # seconds the head trails the chest in `track`
SMEAR_DEG = 38.0        # a joint must travel this far before a smear is drawn
SMEAR_TRAVEL = 0.15     # ...or the body must travel this far, in H
SQUASH_EVENTS: dict[str, tuple[float, float, int, int]]
                        # name -> (height, width, contact frames, settle frames)

def ease(name: str, t: float) -> float
def width_for(height: float) -> float
def squash_stretch(v=1.0, *, impact=None, decay=None, t=0.0,
                   event: str | None = None) -> float
def smear(pose_a: dict, pose_b: dict, t: float) -> dict | None
def track(keys: list[dict], t: float) -> dict
    """keys are [{"t": sec, "pose": {...}, "ease": "overshoot"}, ...] -> pose
    at t. The ease on a key governs the approach *to* that key. A key naming
    no ease gets `overshoot` here — but see the caveat below."""
```

The ten curves are **`linear` `in` `out` `inout` `snap` `anticipate`
`overshoot` `elastic` `bounce` `hold`**. `EASES` also carries the spellings a
board is likely to reach for — `ease` `ease-in` `ease-out` `ease-inout`
`easein` `easeout` `cut` `none` `back` `anticipation` — so a board written in
CSS habits still works, and `_` is normalised to `-`. `t` is clamped to
`0..1`, but the **result is not**: `anticipate` returns negative values early
and `overshoot` exceeds 1 in the middle, which is the entire point of them.

`shots.py` adds one more name on the **camera** only — `creep`, a constant-rate
drift for a move that must not be noticed. It is not an `anim.ease` curve and
is not available between poses; `shots.ease` resolves it before delegating
here. See `storyboard-reference.md`.

**`overshoot` is this style's default curve, not merely its fallback**, and it
peaks at exactly `1.12` at `t = 0.60`. Reach for it unless there is a reason
not to, and for `anticipate` on anything fast that starts from rest. `linear`
is visually indefensible between two poses, and a symmetric `inout` is only
marginally better — it is the curve of a slider, not of a body, because a body
does not decelerate as gently as it accelerated.

**An unknown name therefore falls back to `overshoot`, not to `inout`.** That
is not leniency, it is the house curve: a typo in a storyboard should cost a
nicety, not the render, and the nicety it costs should still look like this
style.

`squash_stretch` supplies the *curve* only — a compression that rebounds past
rest and rings down at `decay` per second (6–10 is cartoon-crisp), clamped to
`0.25×..3×` the rest value. Only the height is produced; the rig derives the
width from it through `rig.squash_scale`, which is exactly area-preserving.
Passing `event=` fills `impact` and `decay` in from the reference table:

| `SQUASH_EVENTS` key | height | width | contact | settle |
|---|---|---|---|---|
| `hard_landing` | 0.75 | 1.30 | 2f | 4f |
| `soft_landing` | 0.88 | 1.12 | 2f | 2f |
| `crouch` | 0.85 | 1.15 | 5f | 4f |
| `apex` | 1.18 | 0.88 | 3f | 3f |
| `pop` | 1.20 | 0.85 | 2f | 4f |

The width column is the reference target; `squash_scale` draws the exact
reciprocal, so a `0.75` squash is `1.333` wide rather than `1.30`.

**`t = 0` is the contact frame, not the rest pose.** `squash_stretch` returns
`v × (1 - impact)` at `t = 0`, so `squash_stretch(event="hard_landing", t=0)`
is exactly `0.75` and `squash_stretch(t=0)` with no event is `0.82` — the
default `impact` of `0.18`. The clock starts at the hit, not before it. That
is deliberate and it matters when you key one: the anticipation belongs to the
*pose* (see `poses.ANTICIPATION_FRAMES`), and by the time this function is
asked for a value the character has already landed. Feed it seconds elapsed
since the frame of impact and it will ring down to rest inside
`contact + settle` frames — `1.001` after the hard landing's six.

### Easing is not decoration

Linear motion is the reason cheap animation looks cheap. Every transition in
this style carries an easing curve, and the two that matter most are the ones a
tweening library does not have:

- **`anticipate`** — moves *against* the target first, dipping to `-0.18` by
  `t = 0.16`, **sitting there until `t = 0.30`**, then departing on the
  overshoot profile and crossing zero at about `t = 0.308`. The flat middle is
  not a rounding artefact: a wind-up that eases straight into its release reads
  as motion-tweened explainer animation, where this style wants a freeze and
  then a snap. Nothing fast may start without it.
- **`overshoot`** — leaves fast, sails past the target by **exactly 12%** at
  `t = 0.6`, then rings down onto the pose with a decay of `3.5`. Nothing fast
  may stop without it. It is also what `ease` and `track` fall back to.

A move with neither reads as a slide, however well it is timed.

`track` re-evaluates `neck` and `head` — and the whole `face`, because the face
belongs to the head — `HEAD_LAG` seconds in the past, so on a direction change
the head arrives two to three frames after the chest. That lag is most of what
sells weight, and it is free: it costs one extra sample of a track you are
already evaluating.

**The `overshoot` default on a key is unreachable from a board.** `track`
promises it, but both of its callers — `shots.py` and `render.py` — substitute
`inout` for a missing `ease` before the key arrives. So a keyframed action
written without an `ease` gets the mechanical curve, not the house one. Name
`overshoot` explicitly on any key that should snap.

---

## Module contract — `look.py`

```python
PALETTE_KEYS: tuple[str, ...]           # the fourteen keys every palette has
PALETTES: dict[str, dict[str, RGB]]     # the nine named palettes
PALETTE_META: dict[str, dict]           # label, note, moods, words — for `choose`
DEFAULT_PALETTE = "noon"
LAYER_Z: dict[str, float]               # sky 1.0, far 0.74, mid 0.40, near 0.14,
                                        # ground/prop/actor 0.0 — haze depth
SHADOW_INK = (26, 40, 48)               # never neutral grey
SHADOW_OPACITY = 0.30
SHADOW_OPACITY_RANGE = (0.28, 0.32)     # every contact shadow is clamped here
SHADOW_A, SHADOW_B = 0.55, 0.06

def choose(mood: str | None, subject: str | None = None) -> dict
    """Pick a palette from the story. Never returns a fixed default when the
    story said something — see the style contract's third obligation."""

def get(name: str) -> dict[str, RGB] | None      # named or previously derived
def derive(key: str, *, base: str | None = None) -> dict[str, RGB]
def score(mood: str | None, subject: str | None = None) -> dict[str, float]
def check(pal: dict) -> list[str]                # empty means the palette is legal
def name_of(pal: dict) -> str
def sky_gradient(sky: RGB, *, spread: float = 7.5) -> tuple[RGB, RGB]
def depth_tint(color: RGB, z: float, sky: RGB, *, strength: float = 0.9) -> RGB
def outline_for(fill: RGB, ink: RGB, *, depth: str = "character") -> RGB
```

The nine palettes are **`pursuit` `noon` `dusk` `neon` `office` `country`
`overcast` `heat` `newsroom`**. A board's `palette` may also be a name `derive`
has minted, because `render.py` asks `get` before it gives up.

Plus the colour arithmetic every drawing module shares: `mix` `shade` `tint`
`desaturate` `rotate_hue` `alpha` `depth_tint` `lightness` `luminance`
`contrast`. `sets.py` re-exports the lot, so a set painter imports one module.

`sky_gradient` is the **only** function in the style allowed to return two
stops. Deeper above, paler at the horizon, `spread` L* either side of the
palette's `sky` — with the downward reach capped on a dark palette, because a
night sky cannot give 7.5 L* back at the top without going black, and at night
the horizon is the bright end anyway.

A palette is a plain `dict[str, RGB]` with exactly these keys:

| key | is |
|---|---|
| `sky`, `ground`, `far`, `mid`, `near` | the set's layers, back to front |
| `skin`, `hair`, `shirt`, `trouser`, `shoe` | character fills |
| `ink` | the outline colour, and the colour of every facial feature |
| `accent`, `accent2` | the two colours reserved for what matters |
| `shadow` | the contact-shadow colour, always used at low alpha |

All values are `(r, g, b)` int tuples.

### `check` is the palette's own contract

`check` is not advisory — `look.py`'s self-test asserts every shipped palette
passes it, so these thresholds are the reason the shipped nine look the way
they do:

| rule | threshold |
|---|---|
| `shirt`/`trouser` against `mid`/`near` | `dL* ≥ 20` **and** contrast `≥ 1.7` |
| `shirt` against `trouser` | `dL* ≥ 10` — or the body reads as one slab |
| `accent` against `mid`/`near` | `dL* ≥ 16` |
| `ink` lightness | `4.5 ≤ L* ≤ 32` — lighter looks grey, darker is black in disguise |
| `ink` is `(0,0,0)` | rejected outright — "the clip-art tell, not a palette" |
| `ink` chroma | `max−min ≥ 8` — a neutral grey line belongs to no palette |
| `ink` on `skin` | contrast `≥ 3.4` — or the face does not read |
| `shadow` lightness | `L* ≤ 24` — paler will not pin a figure down |
| `shadow` chroma | `max−min ≥ 6` — never a neutral grey smudge |
| `sky` against `far` | `6 ≤ dL* ≤ 42` — invisible below, a cutout above |

---

## Module contract — `sets.py`

```python
SCENE_W, SCENE_H = 100.0, 56.25     # the 16:9 composition box
GROUND_Y = 44.0                     # the standard street ground line
REF_UNIT = 9.6                      # px per scene unit the weights were tuned at

SETS: dict[str, callable]           # set name -> draw function
SET_LAYERS: dict[str, tuple[tuple[str, float], ...]]   # name -> (layer, parallax)
SET_GROUND: dict[str, float | None] # name -> ground line, or None for no ground
PROPS: dict[str, callable]          # prop kind -> draw function
PROP_ANCHOR: dict[str, str]         # kind -> "ground" | "vehicle" | "air"
PROP_ANIMS: dict[str, tuple[str, ...]]  # kind -> the `anim` names it answers to
PARALLAX = {"foreground": 1.5, "character": 1.0, "mid": 0.5, "far": 0.18}
STROKE_PX = {"far": 1.5, "mid": 2.2, "character": 3.0, "foreground": 3.8}
SHADOW_OPACITY = 0.30               # clamped to look.SHADOW_OPACITY_RANGE
SHADOW_A, SHADOW_B = 0.55, 0.06     # semi-axes: × foot span, × height
MISSING: set[tuple[str, str]]       # ("set"|"prop", name) asked for and not drawn

def draw_set(img, name, look, *, unit, origin, t: float = 0.0,
             camera: dict | None = None, seed: int = 0,
             layers: list[str] | tuple[str, ...] | None = None)

def draw_prop(img, kind, look, *, at, unit, origin, scale: float = 1.0,
              phase: float = 0.0, seed: int = 0, t: float | None = None,
              anim: str | None = None, shadow: bool = True)

def contact_shadow(img, look, *, at, unit, origin, foot_span, height,
                   opacity=SHADOW_OPACITY, ss=SS_PROP) -> None
def stroke_w(depth: str = "character", *, unit: float | None = None) -> float
def prop_bbox(kind: str, scale: float = 1.0) -> tuple[float, float, float, float]
def layer_origins(name, *, unit, origin, size_px, t=0.0, camera=None, seed=0)
    """{layer: (parallax_k, (ox, oy))} back to front, without drawing
    anything — so the parallax can be reasoned about, or tested, without
    reading pixels."""
def clear_missing() -> None
```

`sets.py` also re-exports `look.py`'s colour helpers by name — `sky_gradient`,
`depth_tint`, `outline_for`, `shade`, `tint`, `mix`, `alpha`, `lightness`,
`desaturate`, `rotate_hue` — so a set painter never has to import both.

Six sets ship: **`street` `highway` `suburb` `aerial` `office` `sky`**.
`street`, `highway` and `office` stand a character on `y = 44.0`; `aerial` and
`sky` have no ground line at all, which is `SET_GROUND`'s whole purpose — a
board that puts an actor in an `aerial` shot has misunderstood the shot.
(`suburb` is absent from `SET_GROUND` and therefore reads as groundless, which
its own `road` layer says it is not — treat that as a bug, not as guidance.)

Fifteen props ship: **`car` `policecar` `milkfloat` `helicopter` `cone` `bin`
`hydrant` `lamppost` `trafficlight` `tree` `building` `sign` `cloud`
`sandwich` `indicator`**. Eight answer to an `anim`:

| prop | `anim` |
|---|---|
| `car`, `policecar`, `milkfloat` | `bounce`, `idle` |
| `helicopter` | `bob` |
| `tree` | `sway` |
| `cloud` | `drift` |
| `trafficlight` | `red`, `redamber`, `green`, `amber`, `cycle` |
| `indicator` | `on`, `off`, `blink` |

Anything else is ignored rather than guessed at.

A set draws **back to front in named layers**, each with its own parallax
factor. `SET_LAYERS[name]` is a *tuple* of `(layer, rate)` pairs rather than a
dict, because the order is the draw order:

| set | layers, back → front |
|---|---|
| `street` | `sky 0.0` `clouds 0.06` `skyline 0.18` `blocks 0.5` `frontage 0.74` `road 1.0` `foreground 1.5` |
| `highway` | `sky 0.0` `clouds 0.06` `hills 0.18` `distant 0.5` `verge 0.74` `road 1.0` `rail 1.5` |
| `suburb` | `sky 0.0` `clouds 0.06` `treeline 0.18` `houses 0.5` `gardens 0.74` `road 1.0` `foreground 1.5` |
| `sky` | `sky 0.0` `sun 0.04` `high 0.1` `horizon 0.18` `far_clouds 0.5` `clouds 1.0` `near_clouds 1.5` |
| `office` | `wall 0.18` `openings 0.5` `furniture 0.74` `floor 1.0` |
| `aerial` | `base 0.94` `markings 0.96` `shadows 0.97` `blocks 0.98` `roofs 1.0` `traffic 1.02` |

The four canonical rates in `PARALLAX` show through every set: far `0.18`, mid
`0.5`, ground `1.0`, foreground `1.5`. `aerial` is the deliberate exception —
straight down there is no depth to parallax, so nothing strays outside `0.94`
to `1.02`. Pass `layers=` to `draw_set` to draw only some of them, which is how
`render.py` puts a character between two planes of the same set.

`t` is the shot-local time in seconds, unquantised, for anything that lives on
its own clock — a rotor, a beacon, a wheel. `phase`, by contrast, is quantised
with the characters: a wheel turning on ones beside a body on twos separates
from it.

`draw_prop`'s `shadow` is `True` by default, and `render.py` passes `False`
because it owns rule 4 for actors and props alike — through
`sets.contact_shadow`, which is public exactly so that a character and a car
cannot disagree about how hard the ground is.

---

## What the rig may not do

1. **No character may be drawn from a pre-rendered bitmap.** Everything is
   solved and drawn per frame, or the whole premise collapses.
2. **No pose may be authored in absolute joint positions.** Angles only —
   otherwise nothing can blend, mirror or rescale.
3. **A rig never breaks its own bone lengths.** Stretch belongs to `squash`,
   which preserves area; a limb that simply grows reads as a bug rather than
   as exaggeration. A whole *build* may be changed, through `pose["bones"]`,
   because that is a character rather than a stretch.
4. **Faces never interpolate.** An eye is open or shut. `blend` snaps `face`
   at `t >= 0.5`; half-shut is a distinct named state, not a tween.

---

## Running a module on its own

Every drawing module has a `__main__` block that asserts its own invariants
and, where there is something to look at, writes sheets. They take an output
directory — **give them one**, because the default is `/tmp`:

```bash
S=skills/style-2d-animation
OUT=~/.cache/film-crew/2d-selftest && mkdir -p $OUT

RIG_TEST_OUT=$OUT python3 $S/scripts/rig.py       # geometry, purity, pose sheet
RIG_TEST_OUT=$OUT python3 $S/scripts/poses.py     # cycles wrap, feet do not slide
RIG_TEST_OUT=$OUT python3 $S/scripts/anim.py      # easing endpoints, smears, tracks
python3 $S/scripts/look.py  $OUT                  # every palette passes `check`
python3 $S/scripts/sets.py  $OUT                  # set and prop contact sheets
python3 $S/scripts/audio.py --out $OUT            # the mix, metered
python3 $S/scripts/audio.py --digest              # one-line determinism digest
```

`rig.py`, `poses.py` and `anim.py` read `$RIG_TEST_OUT`; `look.py` and `sets.py`
take the directory as their first argument; `audio.py` takes `--out`, or
`$FILM_CREW_SCRATCH`, and otherwise writes to `~/.cache/film-crew/2d-selftest`
of its own accord.

There is no `--selftest` flag on any of them — running the file *is* the test,
and a non-zero exit is the failure.
