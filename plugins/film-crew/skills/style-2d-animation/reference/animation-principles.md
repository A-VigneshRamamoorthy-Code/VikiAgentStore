# Animation principles, with numbers

Everything here is a measurement or a rule you can implement. The classical
twelve principles are a vocabulary, not a spec; this file is the spec.

Frame counts are given at **30 fps**, the rate this whole plugin renders at.
The reference genre is usually shot at 24 — where a number came from a 24 fps
source it has been converted, not copied.

---

## 1. Exposure: on ones, twos and threes

**This is the highest-impact decision in the style.** Roughly a third of whether
a result reads as legitimate comes from this alone.

| what | rate |
|---|---|
| character poses | **on twos** — 15 unique drawings/sec |
| slow deliberate action | on threes — 10/sec |
| smears, and impact frames within ±2 of contact | on ones |
| **backgrounds, parallax and camera** | **on ones, always** |

The split in that last row is the one people get wrong. A character on twos
reads as hand-crafted; a *camera* on twos reads as dropped frames. The renderer
therefore quantises pose evaluation and never quantises the camera. It goes
further: a set is drawn at the **unquantised** `t` while props and characters
get the quantised one, so a wheel on ones beside a body on twos visibly
separates — which is the effect.

`shots.ON_FOR_TIER` is where the default comes from: `hold` and `limited` on
threes, `full` and `impact` on twos, `sakuga` on ones, and `DEFAULT_ON = 2` for
a shot that names no tier at all. The ±2 in the third row is
`shots.IMPACT_ONES_FRAMES`, and it applies to every impact cue the shot
declares — `impact`, `accent`, an actor's `impact`, an actor's `squash.at`.

Perfectly smooth character motion at 30 fps does not look expensive. It looks
like an auto-tween, because that is the only way it is normally produced.

## 2. Easing: fast out, overshoot, settle

The second-highest-impact item, and the one most likely to be got wrong by
reaching for a standard tweening library. The signature profile is **not**
ease-in-out — it is `anim._overshoot`, and it is what `anim.ease` falls back to
for a name it does not recognise:

```python
def _overshoot(t, overshoot=0.12, settle_decay=3.5):
    if t < 0.6:                                  # fast departure
        return math.sqrt(t / 0.6) * (1.0 + overshoot)
    s = (t - 0.6) / 0.4                          # oscillating settle
    return 1.0 + overshoot * math.cos(s * math.pi) * math.exp(-settle_decay * s)
```

Roughly: 60–70% of the distance in the first three frames, overshoot the target
by 8–15%, then settle back with decaying oscillation. The shipped default sits
mid-band at **12%**, peaking at exactly `1.12` at `t = 0.6`. Because `t` is
normalised, "three frames" is really the first 20–23% of the move — which is
three frames of a half-second one, and the reason a snap wants a short
duration rather than a steeper curve.

**Linear interpolation between poses is indefensible here.** It is the single
clearest tell of a generated film. `shots.py` enforces this on the camera:
`linear`, `in` and `hold` are refused on a moving camera and swapped for `out`,
with the substitution printed.

**The one exemption is `creep`, and it proves the rule.** `linear` remains
banned for any move the audience is *meant to perceive*; a creep is exempt
precisely because it must **not** be perceived. Its only job is that no two
frames are identical, so a long shot on a breathing character never renders as
a frozen run — and for that job constant rate is not a compromise, it is the
only correct shape. An ease-out substituted into a creep fails at both ends at
once: it leaves at 3.64× its own average speed, which registers as an accent
the shot never intended, and it arrives asymptotically (final frame 0.00×
average), which puts back the frozen tail the creep existed to prevent.

Measured on the pursuit film, clip-rendered, reading the longest run under
`motionprofile`'s 0.60 hold threshold:

| shot | ease-out | `creep` | `creep`, settle removed |
|------|---------:|--------:|------------------------:|
| `s15` (2.70s) | 1.57s | 0.57s | 0.03s |
| `s20` (4.07s) | 1.17s | 0.53s | 0.00s |

Same mean, same peak — the curve redistributes the motion rather than adding
any. `shots.py` accepts `creep` on any move, and warns if the creep is slower
than `shots.CREEP_MIN_RATE` (2%/s of the view, below which it is a freeze with
extra steps) or carries more than `shots.CREEP_MAX_SETTLE` of `hold`.

## 3. Anticipation

Nothing fast starts without a wind-up *against* the direction of travel.
`poses.ANTICIPATION_FRAMES` is the shipped table, in frames at 30 fps:

| action | wind-up | held at the peak |
|---|---|---|
| head turn | 3 | 2 |
| run start | 5 | 2 |
| jump (crouch-squash) | 7 | 3 |
| big comedic reaction | 12 | 4 |

**The hold at the peak is not a detail.** That freeze before the snap is the
difference between this style and a smooth explainer tween. A character that
jumps with no crouch looks launched by an invisible force; one that crouches
and releases in the same breath looks motion-tweened.

`anim.ease("anticipate")` implements it as a curve: down to `-0.18` by
`t = 0.16`, flat there until `t = 0.30`, then away on the overshoot profile.
The flat middle *is* the hold.

The full state machine for any fast action:

```
IDLE → ANTICIPATE (3–12f) → HOLD (2–4f) → SMEAR (1f) → ACTION → SETTLE (4f) → HOLD (20f) → IDLE
```

## 4. Squash and stretch

Always area-preserving: width × height = constant, exactly.
`rig.squash_scale(s)` returns `(1/s, s)` — the reciprocal, not the inverse
square root. The square root is the *volume*-preserving formula, and it does
not belong here: a flat character has no third dimension to borrow from, so
the quantity the eye reads as volume is the area of the silhouette, and
holding that constant forces the plain reciprocal. Under `1/√s` a hard landing
would draw `1.155` wide instead of `1.333` and shed 13% of its area at the
moment of impact — a character that loses volume when it lands reads as
deflating rather than as compressing.

`anim.SQUASH_EVENTS` is the table, and `squash_stretch(event=…)` rings it down:

| event | height | width | timing |
|---|---|---|---|
| `hard_landing` | 0.75 | 1.30 | 2f contact, 4f settle |
| `soft_landing` | 0.88 | 1.12 | 2f + 2f |
| `crouch` (anticipation) | 0.85 | 1.15 | 5f contact, 4f settle |
| `apex` (jump stretch) | 1.18 | 0.88 | 3f + 3f |
| `pop` (startled) | 1.20 | 0.85 | 2f, 4f settle |
| impact received | 0.70 | 1.35 | 2f, 4f bounce-back |

The widths above are the reference targets the values were chosen against; the
rig draws the exact reciprocal, so `0.75` is drawn `1.333` wide. The last row
is not in `SQUASH_EVENTS` — author it directly with
`squash: {"at": t, "impact": 0.30, "decay": 8.0}`.

**The clock starts at the contact.** `squash_stretch` returns `v × (1 - impact)`
at `t = 0`, so `t = 0` is the frame of the hit at full compression — not the
rest pose leading into it. The anticipation before a landing is the *pose's*
job (§2), not this curve's. Each event settles inside its own `contact +
settle` budget: six frames after a hard landing the figure is back to `1.001`.

A character that hits a surface without squashing reads instantly as an inert
shape moving on rails.

## 5. Smears

One frame. Between two key poses, never on a held one. `anim.smear` returns
`None` on anything slower than **38° of joint travel or 0.15 H of body
travel**, and refusing is as important as producing one: a smear on a slow move
looks like a rendering fault. Those two thresholds are the loosest of the
reference-film measurements, and the shipped code sits deliberately above them
— it would rather miss a marginal smear than draw a spurious one.

- **Elongation** — the body stretches **1.5× at the threshold to 3× flat out**
  along the direction of travel and compresses to the reciprocal across it,
  leaning up to 14° into the move, with the trailing limbs dragged 26% back
  behind the clean in-between. This is what ships.
- **Ghosting** — 2–3 copies at 50% and 25% opacity along the arc. For frantic
  repeated motion.
- **Blob** — an abstract shape approximating the swept volume, for a small fast
  object.

Their absence is more noticeable than their presence: without one, a fast action
reads as *popped* rather than *snapped*. Two consecutive smears read as a broken
renderer, which is why `render.py` refuses them on `hold`-tier shots entirely —
on threes even a gentle idle puts a big delta between drawings, and the one
place the renderer would add motion to a held shot is the one place it is
forbidden.

## 6. The hold, which is the joke

After a gag lands, the picture stops.

| | frames | seconds |
|---|---|---|
| standard gag | 20–36 | 0.7–1.2 |
| the film's central joke | 48–72 | 1.6–2.4 |

`shots.MIN_HOLD_FRAMES` is **20**, and `pacing_report` warns about any
`hold`-tier shot shorter than that — advisory, because a deliberate hold that
runs long is the whole point and must not be clipped by a linter.

Cutting away on the punchline is the most common timing error there is. **The
hold is the laugh track** — it is the room the audience needs to register the
joke. The sample film's narration gaps say it plainly: `0.35–0.7 s` after a
setup line, `1.0–1.6 s` after a punchline, and the two longest gaps in the film
(`1.5` and `1.6`) are its last two lines.

A hold is not a freeze. Underneath it the character keeps breathing, and blinks
every **72–96 frames**. `poses.stand` blinks once per cycle, and one cycle is
`IDLE_CYCLE_S = 3.0` seconds — so an actor driven at `rate: 0.33` blinks every
90 frames, right in the band. At the default `rate: 1.0` it is every 30 frames,
which reads as a tic. Without any blink at all, a hold reads as a crashed
render.

## 7. Weight, in four rules

1. A planted foot does not slide. The pelvis travels over it.
2. The pelvis rises over the planted leg and drops through the pass, twice per
   stride, about `0.012 H` — `0.026 H` at a run, `0.030 H` in a scramble.
3. Arms oppose legs.
4. The head lags the chest by 2–3 frames on any direction change
   (`anim.HEAD_LAG = 0.083 s`), and the face goes with it, because the face
   belongs to the head.

Rule 4 is follow-through, and it is most of what sells weight. Rule 1 is the
loudest tell of procedural animation when broken — and it is the one the
storyboard can break on its own, because `render.py` drives an actor's position
from `at`/`to` rather than from the cycle. Use `poses.stride_units` to make the
two agree, or pin the actor with `travel: false` and move the set instead.

## 8. Parallax, in four planes

Depth in a flat-colour world is overlap, scale and **differential travel**.
`shots.PARALLAX` is the reference table — how far a plane moves for one unit of
camera travel:

| plane | `shots.PARALLAX` | factor |
|---|---|---|
| foreground | `fore` | `1.5` |
| characters | `char` | `1.0` |
| mid background | `mid` | `0.5` |
| far background | `far` | `0.18` |

`sets.PARALLAX` carries the same four numbers under the spelled-out names
`foreground` `character` `mid` `far`, so the set painter and the camera agree
by construction.

`PARALLAX_MIN_LAYERS` is **3**: two planes is a cut-out theatre, three is a
world. The foreground factor above 1.0 is the one people leave out, and it is
the one that does the work — something crossing *faster* than the characters is
the only cue in a flat image that says "this is nearer than they are".

Each set declares which of its layers sit on which plane. `sets.SET_LAYERS` is
a dict of **tuples of `(layer name, rate)` pairs, in draw order back to front**
— a tuple, not a dict, because the order is the render order:

| set | layers, back → front |
|---|---|
| `street` | `sky 0.0` `clouds 0.06` `skyline 0.18` `blocks 0.5` `frontage 0.74` `road 1.0` `foreground 1.5` |
| `highway` | `sky 0.0` `clouds 0.06` `hills 0.18` `distant 0.5` `verge 0.74` `road 1.0` `rail 1.5` |
| `suburb` | `sky 0.0` `clouds 0.06` `treeline 0.18` `houses 0.5` `gardens 0.74` `road 1.0` `foreground 1.5` |
| `sky` | `sky 0.0` `sun 0.04` `high 0.1` `horizon 0.18` `far_clouds 0.5` `clouds 1.0` `near_clouds 1.5` |
| `office` | `wall 0.18` `openings 0.5` `furniture 0.74` `floor 1.0` |
| `aerial` | `base 0.94` `markings 0.96` `shadows 0.97` `blocks 0.98` `roofs 1.0` `traffic 1.02` |

The four canonical rates show through: every ground-level set's far band is
`0.18`, its mid `0.5`, its road `1.0`, its foreground `1.5`, with `0.74`
interpolated for the plane just behind the actors. `aerial` is the deliberate
exception — looking straight down there is no depth to parallax, so every layer
is pinned between `0.94` and `1.02` and faking more reads as a wobble. A layer
at rate `r` is displaced by `(1 - r) × (dx, dy)` against the camera, which is
why `1.0` is locked to the characters and `0.0` never moves at all.

The renderer's parallax linter does not know about that exception, so an
`aerial` shot prints

```
! set 'aerial' spreads its layers over only 0.08 of parallax
  — the style runs far 0.18 to fore 1.5
```

every time. It is correct about the number and wrong about the conclusion:
**expect that warning on `aerial` and `sky`, and act on it anywhere else.**

---

## The things that make it look cheap

Each of these is a specific, checkable failure — not a matter of taste.

1. **Linear tweens between poses.** See §2.
2. **Pure black outlines.** `#000000` reads as clip art. `rig.outline_of`
   derives every body outline from its own fill: same hue, saturation +0.10,
   lightness −0.40, floored at `0.06` so it never bottoms out at black. The
   palette's `ink` is reserved for facial features, where a true dark line *is*
   wanted — and `look.check` caps it at `L* ≤ 32` while demanding contrast
   `≥ 3.4` against skin, so it is dark without being black.
3. **A symmetrical idle.** Both arms mirrored and both feet parallel reads as
   frozen. `poses.stand` is contrapposto for this reason: weight on the right
   leg, left foot back and turned out, right hand lower, head off-axis by 4°.
4. **No contact shadow.** The single most jarring depth error available in flat
   2D. A low-opacity ellipse, always, under everything on the ground.
   `look.SHADOW_OPACITY_RANGE` is `(0.28, 0.32)` — the reference band, clamped
   in code — and `sets.SHADOW_OPACITY` sits at **0.30**, mid-band, with
   semi-axes `SHADOW_A = 0.55 × foot span` and `SHADOW_B = 0.06 × height`.
   `sets.contact_shadow` is public precisely so that characters and vehicles
   cannot disagree about how hard the ground is; `render.py` calls it for
   actors and props alike and passes `shadow=False` down to `rig.draw`, so
   there is exactly one shadow language in the film. `render.SHADOW_ALPHA`
   (`78/255`, **30.6%**) is only the fallback for when `sets.contact_shadow`
   is unavailable.
5. **Continuous motion with no holds.** Characters snap to a pose and hold. Most
   of a shot is held frames.
6. **Uniform stroke weight.** Two weights on the figure, never one:
   `rig.INK_W = 0.005 H` for the body and `rig.FACE_W ≈ 0.00286 H` for face
   detail, about 57% of it. Both are fractions of the *figure*, not of the
   frame, so the line does not thin out as the camera pushes in — at 1080p with
   a full-figure framing that is roughly 1.7 px and 1 px, and both grow with
   zoom. The set has a second, orthogonal rule: `sets.STROKE_PX` thins the line
   with distance — `far 1.5`, `mid 2.2`, `character 3.0`, `foreground 3.8`
   pixels at `REF_UNIT`, which `sets.stroke_w` converts to scene units so the
   ratios survive any zoom. Aerial perspective, done in line weight instead of
   haze.
7. **Smooth 30 fps character motion.** See §1.
8. **No anticipation.** See §3.
9. **Gradients anywhere except the sky.** Flat colour is `sets.py`'s first
   house rule and shading is another flat shape — with exactly one licensed
   exception. `look.sky_gradient` returns the two stops of a simple linear
   sky, deeper above and paler at the horizon, ±7.5 L* either side of the
   palette's own `sky`; at night the downward reach is capped so the top does
   not go black, because after dark the horizon is the *bright* end. Nothing
   else in the frame may be graduated: depth is `look.depth_tint` washing a
   layer toward the sky colour, never a blur and never a ramp.
10. **Five-fingered hands.** Three fingers and a thumb, always — at this size
    five fingers collapse into a fringe and take the silhouette with them.
11. **Cutting on the punchline.** See §6.
12. **A linear camera push.** The camera decelerates into its final framing, or
    it feels mechanical. `shots.MECHANICAL_EASES` refuses `linear`, `in` and
    `hold` on a moving camera outright — except for the named `creep` ease,
    which is a constant-rate drift the audience is not meant to notice. See §2.

---

## Ranked by impact

If time runs out, get these right in this order:

1. Pose-and-hold exposure (on twos)
2. Overshoot-settle easing on every animated parameter
3. Post-gag hold duration
4. A contact shadow under every character
5. Squash and stretch on landings
6. Coloured outlines rather than black
7. Brow expressiveness — brows carry the acting
8. Anticipation before every fast action
9. Background parallax, at least three layers
10. Proportions held to one master head-height unit
11. Smear frames on fast actions
12. Flat colour, no gradients on characters

---

## Provenance

Compiled from an analysis of **"Summit"** (Birdbox Studio — verified 116 s) and
**"Getaway Car"** (Board Studios), together with the standard literature on
limited animation and smear frames.

Be honest about what this is: the *film durations and story details* are
verified, and the *technique numbers* are the genre's well-established practice
rather than frame-by-frame measurements of those two specific films. They are
starting values that produce the right result, not claims about what Birdbox
did. Where a number here disagrees with your own eye on a contact sheet, trust
the contact sheet.
