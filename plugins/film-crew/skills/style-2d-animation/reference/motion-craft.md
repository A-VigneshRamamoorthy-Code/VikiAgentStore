# Motion craft

What an eighteen-part animation course actually says, reduced to the parts a
program can execute.

This document exists because the first films made with this skill were
*technically* correct and still looked wrong. The physics validator was clean
— no moonwalk, no foot slide, no teleport — and the result was floaty,
robotic, and read as a puppet being dragged rather than a person walking. The
gap was craft, not correctness.

The source is Toniko Pantoja's animation course (18 videos, ~3.5 hours), read
in full via transcript. Where a rule below is attributed, the attribution is
to the video that states it.

Everything here is sorted into two kinds:

| | meaning |
|---|---|
| **CODED** | implemented in `lib/`, enforced by `scripts/check-physics.mjs` |
| **ADVISORY** | true and useful, but a judgement call — it informs how you write a film, not what a library does |

Nothing has been invented to fill gaps. Where the course says something that
cannot be reduced to a number, it is listed as advisory and left there.

---

## 1. Timing and spacing

> "Speed is spacing over timing."

The single most load-bearing idea in the course, and the one most often
misunderstood by procedural rigs.

**Timing** is how many frames a move takes. **Spacing** is where the drawing
sits inside those frames. A move can take exactly the same number of frames
and read as heavy, weightless, snappy, or mechanical depending entirely on
spacing. Procedural animation defaults to *even* spacing, which is why
procedural animation defaults to looking mechanical.

### Timing charts are easing curves — CODED

The course teaches spacing through **timing charts**: a line with the two
extremes at either end and the in-betweens marked along it. This is precisely
a normalised easing curve, drawn by hand.

Charts are built from three primitives, and only three:

| primitive | position | use |
|---|---|---|
| **halves** | 0.5 | the neutral in-between |
| **thirds** | 1/3, 2/3 | a gentle bias |
| **favours** | 0.10–0.20 or 0.80–0.90 of the parent interval | a hard bias — the cushion |

A "favour" is the chart's word for crowding a drawing right up against one
extreme. It is what produces both the *hang* at the top of an arc and the
*cushion* into a stop.

Two charts from the course, implemented verbatim in `lib/timing.js`:

```
even     0, 0.125, 0.25,  0.5,   0.75,  0.875, 1      symmetric, 13 frames / 7 drawings
cushion  0, 0.056, 0.222, 0.667, 0.833, 0.958, 1      hangs, bursts, cushions
```

Sampling between chart points uses **Fritsch–Carlson monotone interpolation**,
not a Catmull-Rom spline. This matters more than it sounds: a plain spline
through those points overshoots between them, which silently adds an
overshoot the animator never drew. Monotone interpolation cannot exceed its
own data, so the curve does exactly what the chart says and nothing else.

```js
import {chart} from '../lib/timing';
chart('cushion', u);   // u in 0..1 -> eased 0..1
```

**A chart is direction- and speed-neutral.** It says only how drawings relate
to each other. The same cushion chart serves a stop, a door closing, and a
head turn. This is why they compose.

### On twos — CODED, not wired in

> "On ones for fast action, on twos for everything else."

Holding each drawing for two frames is the default of hand-drawn animation,
and it reads as *deliberate* rather than cheap. Fast action needs ones, or the
strobing becomes visible.

```js
onTwos(frame)             // Math.floor(frame / 2) * 2
exposureFor(speedPxPerFrame)  // 1 above ~26 px/frame, else 2
```

Implemented and tested; deliberately **not** applied to any film yet, because
it is a large stylistic commitment and should be a per-film choice rather than
a house default.

---

## 2. Gravity

This section produced the single highest-value fix found in the whole course.

### Gravity is asymmetric — CODED

> A body going up **decelerates**. A body coming down **accelerates**.

Obvious once stated, and violated by almost every procedural bounce, including
the one this repo shipped. The old vertical bob was:

```js
-Math.abs(Math.sin(phase * TAU)) * bobAmp    // WRONG: symmetric
```

`|sin|` rises and falls with identical spacing. The eye reads that as
buoyancy — the classic "floaty" tell. The fix models the two halves
separately:

```js
bobShape(phase)   // rise: decelerating (1-(1-t)^2)   fall: accelerating (t^2)
```

The checker enforces it: **`gravity is asymmetric (fall accelerates, rise
decelerates)`** samples the bob and fails if the two halves are mirror images.

### Galileo's odd rule — CODED

> A falling body covers **1 : 3 : 5 : 7** across equal slices of time.

The course teaches this as a spacing recipe for drawing a fall, and it is the
same statement as `s ∝ t²` — the odd numbers are the first difference of the
squares. It is where the quadratic in `bobShape` comes from, and it is
checked directly:

```js
odd(k, n)   // the k-th slice of n, as a fraction of the whole drop
```

**`bob obeys Galileo's odd rule (spacing 1:3:5:7)`** in the validator.

### Contact, down, passing, up — CODED

The four poses of a walk, and the course is specific about their status:

- **contact** — the *keyframes*. The whole cycle is authored from these.
- **down** — the low point. Squash. Weight has landed.
- **passing** — the transfer.
- **up** — the high point. Stretch.

The course calls down and up the poses that "ground the animation in
reality", and the reason is exactly the asymmetry above: they are where
gravity is visible.

The solver now emits a `squash` field per frame alongside `bob`, and the rig
applies it as a **volume-preserving** scale — `sy` up means `sx` down — so
the character compresses rather than shrinking.

---

## 3. Chains, overlap and follow-through

The richest and most codeable section of the course, and the one that most
changes how a rig reads.

### One lag, three names — ADVISORY (the vocabulary), CODED (the mechanism)

The course is careful that these are three *views* of a single phenomenon:

| name | what it describes |
|---|---|
| **overlapping action** | the offset in **time** |
| **drag** | the offset in **space** |
| **follow-through** | the part that keeps going after the parent has stopped |

There is one mechanism underneath: a child follows its parent late.

### Two frames per link, accumulating — CODED

> "Each successive link lags the one before it by about two frames."

Not two frames for the whole chain — two frames *per joint*, accumulating:

```
link 1 (anchor)   0 frames
link 2           -2
link 3           -4
link 4           -6
```

```js
import {chainPhases, lag} from '../lib/overlap';
chainPhases(headPhase, 4, cycleFrames)   // [p, p-2f, p-4f, p-6f] as phases
```

**The delay must be converted to phase using the actual pace.** Two frames is
a fifth of a sprint cycle and a fifteenth of an amble; a fixed phase offset is
wrong at every speed but one. Hence `cycleFrames = stride / speed`, computed
per frame.

### Amplitude grows to the tip — CODED

> Cloth is "a wave with a tension point."

The anchored end barely moves; the free end travels furthest, and the growth
is **non-linear** — quadratic, not proportional to link index.

```js
whipAmplitude(i, n)   // 0 at the anchor, 1 at the tip, quadratic between
```

Checked: **`whip amplitude is zero at the anchor and grows to the tip`**.

### The reversal passes through straight — CODED

When a whipping chain reverses, it does not go C → S. It goes:

```
C  ->  straight  ->  S  ->  C
```

The **straight** pose is the one animators most often skip, and skipping it is
what makes a tail or a scarf look like it is being rotated rather than
travelling. `whipPose(t, n)` walks the full four-stage sequence.

### Cloth lags acceleration, not velocity — CODED

A subtle point and easy to get backwards. Fabric responds to *changes* in
motion. A coat on someone walking at a constant pace is nearly still; the same
coat flares when they start, stop or turn.

```js
clothLag(accel, i, n)
```

### Follow-through overshoots, then rings down — CODED

```js
settle(framesSince, amplitude, period, decay)
```

A damped oscillation. This is the **one** stateful-looking helper in the
library, and it is safe because its input is "frames since the event", not an
accumulated value — so frame 300 still solves without simulating frames 1–299.

Checked: **`follow-through overshoots then rings down`**.

---

## 4. Full-body coordination

### Joints have limits — CODED

> Spine: roughly **+90° forward, −30° back**. Pure rotation, no translation.

Hips have a **narrower** range than shoulders, because the hip socket is
deeper. The course is emphatic that a spine bend is rotation about a joint,
not a translation of the torso — sliding the chest is the tell of a rig built
by moving pieces rather than turning them.

### Limbs travel arcs, never lines — CODED

A bone is a fixed length pinned at one end, so its tip can only travel a
circular arc. Linearly interpolating a hand between two positions makes the
arm visibly *shorten* mid-move. Everything in `locomotion.js` that moves a
limb moves it in polar terms for this reason.

### What the course does *not* say

The video titled as though it covers gait coordination is a joint-taxonomy
lecture and contains no rules about arm/leg phase relationships. Rather than
invent some, the existing counter-rotation in the solver was left as it was.
Noted here so the gap is visible rather than assumed-covered.

---

## 5. Staging and camera

### Speed is contrast — ADVISORY

> "The higher the contrast, the higher the perceived speed."

A runner alone in an empty frame is not fast. The same runner passing a
lamppost, a slow walker, and a foreground bush is. This is a *writing* rule:
put something slow in the shot.

In `DoublingBack.jsx` this is Ivo, who ambles the other way at 42% of a walk
and exists for no other reason.

Parallax speed and depth-of-field blur both scale with `(1 − z)`.

### Linear staging — ADVISORY

> One focal action at a time.

The course's diagnosis of why procedural animation looks robotic is precise
and worth quoting in full: **every joint oscillates constantly**. Real
performance is sequential — the character does one thing, finishes it, then
does the next. Non-focal joints should be damped, not merely quieter.

In `DoublingBack.jsx` this is the held beat: Ada stops, and Ivo and Tess stop
too, so there is exactly one thing on screen to look at.

### The camera anticipates — CODED (in the film), ADVISORY (as a rule)

> "Our camera is going to be moving to the right, so I shifted it slightly to
> the left first as an extreme."

A camera that simply chases its subject is a camera nobody is operating. A
real one settles back a beat before it swings.

`DoublingBack.jsx` implements this without hardcoding *when*: it scans the
solved track for the frame where facing flips, then eases an opposing offset
in over the second before it, using the `accel` chart. Retime the story and
the camera retimes itself.

> "Animate the background as if it were a character."

### Background depth — ADVISORY

Three passes, in order: a **contrast map** (near = high contrast, far =
washed), then **ambient skylight**, then **directional sun**. Doing them in
that order is what stops a background looking like flat shapes with a gradient
on top.

---

## 6. Failure modes

The course's own list of tells, all of which the early films in this repo
exhibited:

| tell | cause | fix |
|---|---|---|
| **Floaty** | symmetric vertical motion, too much airtime | `bobShape` — asymmetric gravity |
| **Robotic** | every joint oscillating at once | linear staging; damp non-focal joints |
| **Puppet-on-a-stick** | no lag between parent and child | `lag()` / `chainPhases()` |
| **Rotating, not travelling** | whip reversal skips the straight pose | `whipPose()` |
| **Weightless** | no squash at contact, no cushion into a stop | `squash` field; `cushion` chart |
| **Dead** | a neutral rest pose inside an active cycle | never return to neutral mid-action |
| **Doll-like** | twinning — left and right doing the same thing | offset the sides |
| **Nothing to look at** | everything moving equally | pick the focal action |

---

## 7. What this changed, concretely

Before this pass the validator ran **14** checks and was clean, and the films
still looked wrong. It now runs **25**, and the eleven new ones are all craft
rather than correctness:

```
gravity is asymmetric (fall accelerates, rise decelerates)
bob obeys Galileo's odd rule (spacing 1:3:5:7)
bob peaks at the passing pose, lands at contact
timing charts are monotone and span 0..1
accel and decel are genuinely opposite
chain lag wraps into phase and accumulates down the chain
whip amplitude is zero at the anchor and grows to the tip
follow-through overshoots then rings down
```

Plus three new path cases from `DoublingBack`, whose stop → hold → turn → run
sequence is the most demanding in the repository.

---

## 8. On rigs

The reference this work was measured against — EthanAnims rigging Hilda — was
examined frame by frame rather than taken on description. It is a **cut-out
puppet rig**: separate limb pieces on pivots, exactly the architecture already
in use here.

That is a useful negative result. The gap between this repo's output and that
reference was never the technique. It was asymmetric gravity, overlap, squash,
and staging — every one of which is in this document.

The way to build a character for such a rig, as the course describes it:

1. Draw the character **in a neutral T-or-A pose**, whole.
2. Separate into pieces **at the joints**, with each piece overlapping its
   neighbour so no gap opens when it rotates.
3. Set each piece's **pivot at the joint centre**, not at its bounding box.
4. Parent them into a chain: hip → spine → chest → head, hip → thigh → shin →
   foot.
5. Animate by **rotation**, and translate only the root.

`components/Humaaans.jsx` follows this literally, and the one time it did not
is the one time the film was rejected. Steps 3–5 are the rig: pivots taken from
the drawing, a hip → leg → shoe chain, rotation everywhere and translation only
at the root. Step 2 is the part that was skipped — the vendored artwork is
already separated at the hip and the ankle, but *not* at the knee, and the
tempting fix is to deform the piece to invent the missing joint. Warping a
cut-out piece is a different technique from cut-out animation, and mixing them
produced sheared trousers, detached shoes and a hole at the pelvis. The
cut-out-native answer to a joint the artwork does not have is to **foreshorten
along the limb**, which is what an animator drawing this flat would do.

---

## Sources

Toniko Pantoja, *Animation course* (18 videos). Transcripts read in full.
Individual attributions are given inline above where a rule comes from one
specific video.
