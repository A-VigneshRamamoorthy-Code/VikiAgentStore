# Physics

Everything in this document exists because of one recurring failure: a
character who moves in a way a body cannot.

Those failures are hard to catch in review. They are invisible in a still, and
nearly invisible in playback — a character moonwalking out of frame looks, on a
scrubbed timeline, exactly like a character walking out of frame. You notice on
the second or third viewing, by which point the shot is signed off. So the
rules below are enforced by code, not by eye.

---

## The one rule

> **Facing and stride phase are DERIVED from where the body actually goes.
> Neither is ever authored.**

Every backwards-walking character this crew has shipped came from breaking it.
The canonical example, from `wetpaint`:

```js
const facing = from === 'left';
const flip   = local > tOut ? !facing : facing;   // "leaving means facing
                                                  //  the other way"
```

It does not. A visitor who enters from the left walks *rightwards* to the bench
(`300 → seat`) and then keeps walking *rightwards* to leave (`seat → 1520`).
Same direction, both times. Flipping them on the way out drew a figure gliding
backwards across the shot.

The author flipped a boolean describing the *intention* ("they're leaving")
instead of measuring the only thing that decides which way a drawing points:
the sign of the distance it is covering.

`solveLocomotion` makes this class of bug unrepresentable. You give it a path —
where the body is, over time — and it returns everything a rig needs. There is
no way to ask it for a facing that disagrees with the motion, because facing is
not an input.

```js
const track = solveLocomotion(
  [
    {t: 0,   x: -600, ease: 'creep'},
    {t: 180, x: 600,  ease: 'easeOut'},
    {t: 255, x: 600},                    // a dwell — so, an idle pose
    {t: 360, x: -100, ease: 'easeInOut'} // reverses; the turn draws itself
  ],
  {fps: 30, walkStride: 200, runStride: 430}
);
```

---

## What the solver guarantees

| # | Guarantee | How |
|---|-----------|-----|
| 1 | Facing agrees with velocity | `facing = sign(vx)`, with hysteresis so a jitter near zero cannot flicker |
| 2 | Legs cannot cycle on a parked body | phase integrates `dx / stride` — never a frame counter |
| 3 | A planted foot does not move | stance excursion is linear, and stride is held constant across a step |
| 4 | Turns take time | `facingScale` sweeps through a clamped zero over `turnFrames` |
| 5 | Weight follows acceleration | lean is `ax` in the character's own local space |

### Why phase must come from distance

If phase advances with the clock, a character who slows down keeps taking the
same number of steps and their feet skid. If it advances with distance, the
step rate falls out of the speed automatically — which is the actual physical
relationship. This single decision removes foot-slide as a category.

```js
ph += Math.abs(dx) / stride;    // right
ph += 1 / (fps * cadence);      // wrong: legs run on a clock
```

---

## Why the pelvis moves

The first version of the rig held the pelvis at a fixed height and let the IK
sort the legs out. It could not.

The legs are exactly as long as the hip is high — so the moment a foot moved
forward at all, the target was further from the hip than the leg could reach.
The solver clamped it, and the clamp swung both legs out toward the horizon.
The character walked like a pair of compasses.

Real walking solves this the other way round. A leg is a fixed length, so
standing on one with your feet apart **requires** the hips to drop. That dip is
where the bob in a walk cycle actually comes from — it is not decoration added
on top of the walk, it is a consequence of the leg length.

```
sink(ax) = hipHeight − √(legLength² − ax²)
```

So the stride is read off that same triangle in the opposite direction: pick an
acceptable dip, and it tells you the step length. Change a bone and the stride
follows. The two cannot drift apart, because they are one triangle read two
ways.

**Consequence for the scene graph:** legs are drawn in ground space, *outside*
the group that carries the bob. A foot that bobs with the body is a foot that
is not standing on anything.

---

## Why a gait is a dial, not a switch

Switching `walk → run` between two frames changes the stride instantly, which
teleports the planted foot sideways. Blending the stride per-frame is worse: it
replaces one 50-unit slip with twenty small ones, and it is not possible to
lengthen your stride halfway through a step, because one of your feet is on the
ground and it is not going anywhere.

So the gait mix is smoothed, then **sampled once per step and held** — steps
being the half-cycle boundaries where the trailing foot lifts. A planted foot
then provably cannot move, because nothing determining its position changes
while it is down.

Both the solver and the rig call `gaitAt(mix)` and `strideAt(mix, …)`, so a
blended frame is described identically in scene space and in character space.

---

## Keeping the two descriptions in one place

`GAITS` and `footOffset` live in `locomotion.js`, next to the solver, and the
rig imports them. That placement is load-bearing.

The solver has to know how long a foot stays down in order to say where it is;
the rig has to know the same thing in order to draw it. An earlier version kept
two copies — the solver assumed a foot was planted for half the cycle, the rig
planted it for 0.62 of one — and the validator reported foot slide on every
path, on a rig whose feet were in fact glued down.

A discrepancy between two descriptions of the same walk is not a physics
failure. It is a bookkeeping failure that looks exactly like one, and it will
cost you an afternoon.

---

## The validator

`validateLocomotion(track)` grades a solved track for the six faults that make
an audience say "that looks wrong" without being able to say why:

| Fault | Meaning |
|-------|---------|
| `MOONWALK` | body travelling one way, drawing facing the other |
| `TREADMILL` | stride phase advancing on a stationary body |
| `FOOT SLIDE` | a planted foot moving in world space |
| `TELEPORT` | a per-frame jump that reads as a cut, not a move |
| `SNAP TURN` | facing reversed inside a single frame |
| `OFF GROUND` | feet leaving the ground plane without a jump |

Every one of these has shipped in a film from this crew at least once.

### Run it

```bash
node scripts/check-physics.mjs            # exits non-zero on any fault
node scripts/check-physics.mjs --verbose
```

It solves paths; it renders nothing, so it is fast enough for every commit.

The suite checks the films' real paths **and** a set of adversarial ones, plus
three deliberately-broken hand-built tracks that assert the validator still
catches what it claims to. That last group matters: the solver is built so it
*cannot* produce a moonwalk, so without a negative control a validator that had
silently stopped working would look exactly like a clean run.

---

## Authoring paths

Give **speeds and durations**, not positions.

The film's staging was originally written as "be at x=1750 by 6.5 seconds", and
every one of those numbers was silently wrong the moment the rig's stride
changed: the character still arrived on time, but at whatever cadence the
distance implied — which is how you get a stroll played at four steps a second.

```js
const seg = (keys, dur, speed, ease) => {
  const last = keys[keys.length - 1];
  keys.push({t: last.t + S(dur), x: last.x + speed * dur, ease});
  return keys;
};

const WALK = strideUnits(SCALE, 'walk') * 1.0;   // ~1 cycle/sec: unhurried
const RUN  = strideUnits(SCALE, 'run')  * 1.5;

const path = [{t: 0, x: -600, ease: 'creep'}];
seg(path, 6.0,  WALK,         'easeOut');
seg(path, 2.5,  0,            'linear');      // a dwell, so: idle pose
seg(path, 3.5, -WALK * 0.92,  'easeInOut');   // reverses. No facing mentioned.
seg(path, 6.0,  RUN * 0.62,   'easeIn');
```

Cadence becomes the input and position the consequence, so a change to the legs
can never desynchronise the staging again.

Note what never appears in a path: which way anybody is facing.

---

## The world has to be as long as the walk

A set built as a fixed array is a set with an edge, and the moment somebody
walks past that edge the film shows it — buildings stop, trees stop, and the
character is running along a blank plate. This set used to be forty railings and
eight trees generated once around `x = 0`; it ran out at about twenty seconds of
a thirty-second film.

Generate scenery *from the camera* instead. For a layer at parallax `depth`,
only the tiles that actually land on screen exist:

```js
const spread = (camX, depth, W, period, x0 = 0, margin = 600) => {
  const lo = Math.floor((camX * depth - margin - x0) / period);
  const hi = Math.ceil((camX * depth + W + margin - x0) / period);
  const out = [];
  for (let i = lo; i <= hi; i++) out.push({i, x: x0 + i * period});
  return out;
};
```

Two things make this safe to repeat forever:

- **Seed variation from the tile index, not from a running generator.** A shared
  `rnd()` sequence gives a different building every time the array is rebuilt,
  so the skyline reshuffles as the camera moves. Deriving the seed from `i`
  means tile 37 is the same building whenever it comes back on screen.
- **Give each class of object its own period, and make the periods disagree.**
  Trees every 815, lampposts every 937, benches every 1783. Round, harmonious
  numbers (760 / 900 / 1700) line up regularly, and every time they do you get a
  tree, a lamppost and a bench stacked in one spot.

## Anything resting on a plane shares that plane's depth

Parallax is not a styling dial. If an object is standing on the pavement, and
the pavement is drawn at depth 1, then the object travels at depth 1 — because
it is bolted to it. Putting the street furniture at `0.95` for "a bit of depth"
meant every lamppost slid slowly along the ground it was supposedly fixed to.

The second, worse symptom is a composition one. A 5% differential is *almost*
locked to the character, so a lamppost that happened to line up behind somebody's
head stayed behind their head for seconds — the oldest bad shot there is. Objects
at a true separate depth sweep past and the tangent breaks itself.

Get depth from staging, not from cheating the parallax:

| Want | Do |
|------|-----|
| Furniture behind the cast | Same depth; raise the ground line, scale down slightly |
| A genuinely distant row | Its own depth *and* its own ground line (trees at 0.86) |
| Something in front | Depth **above** 1 (the kerb railing runs at 1.1) |

---

## Checklist before you call a shot done

- [ ] `node scripts/check-physics.mjs` passes.
- [ ] Nobody's facing is written down anywhere.
- [ ] Every dwell longer than ~0.5s reads as an idle pose, not a frozen walk.
- [ ] Reversals have a turn in them, not a mirror flip.
- [ ] Characters pass *in front of* or *behind* scenery, never through it.
- [ ] The set is generated from the camera, so it cannot run out.
- [ ] Nothing resting on the ground has a parallax depth other than the ground's.
