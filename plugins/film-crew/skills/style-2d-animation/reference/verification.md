# Verification

Five numbers and one picture. All cheap, all checked before anything ships.

```bash
S=skills/style-2d-animation
F=pursuit.mp4
```

---

## 1. Look at the contact sheet — first, always

```bash
python3 $S/scripts/render.py sb.json --sheet
```

Twenty frames evenly sampled across the film on one JPG — `5×4` landscape,
`4×5` for a Short. Seconds instead of minutes, and it is the only check that
catches the two failures a single frame physically cannot show:

- a character drifting out of frame across a shot;
- two actors standing in the same place.

Nothing else in this list matters if the sheet is wrong.

## 2. Format

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,pix_fmt \
  -of default=nw=1 "$F"
```

| | expected |
|---|---|
| episode | `1920×1080`, `30/1`, `yuv420p` |
| short | `1080×1920`, `30/1`, `yuv420p` |

## 3. Loudness

```bash
ffmpeg -nostats -i "$F" -af ebur128=peak=true -f null - 2>&1 | tail -12
```

−14 LUFS integrated, true peak ≤ −1 dBFS, **0 clipped samples**.

If it is off, the mix is wrong. **Do not fix loudness by re-encoding** — rebuild
it with `--audio-only`.

## 4. Motion

```bash
python3 $S/scripts/render.py sb.json --motion 24
```

`style.json` sets the floor at `verify.motion_mean_min = 1.2` and the target at
`motion_mean_target = 2.4`. Below the floor you have made a slideshow. The flag
samples `N` frame pairs and reports a mean difference with a 95% confidence
interval, so a number whose interval straddles the floor means *sample more*,
not *ship it*.

A caveat specific to this style: **a low number is not automatically a failure
here.** Comedy is held far more than a documentary is, and a film full of
deliberate comic holds legitimately measures lower than a film full of camera
moves — the worked example in `examples/pursuit/` measures around `1.0` and
prints `UNDER`, because 62% of its frames are held on purpose. Read this number
together with the contact sheet and the tier separation below, never alone.

Two ceilings exist for the opposite failure, and they disagree, so know which
one you are being judged by. `style.json` declares
`verify.longest_hold_s_max = 5.0`; nothing reads it — it is a statement of
intent. `motionprofile.py` enforces its own, stricter `longest_hold_s ≤ 2.5`.
A hold past either is not a beat, it is a stall.

## 5. Tier separation

```bash
A=skills/animation-director/scripts
python3 $A/motionprofile.py "$F" --plan motion-plan.json \
        --timeline "${F%.mp4}.timeline.json" --strict
```

It prints a table of nine checks with their thresholds:

| check | want | means |
|---|---|---|
| `p90` | ≥ 2.2 | the loud tail is genuinely lively |
| `dynamic_range` | ≥ 2.2 | loud moments rise clear of quiet ones |
| `longest_hold_s` | ≤ 2.5 | no frozen frame outstays a viewer's patience |
| `tier_separation` | ≥ 1.35 | planned-loud beats really are louder than planned-quiet ones |
| `hit_rate` | ≥ 0.75 | the beats marked loud actually register as accents |
| `loud_mean_delta` | ≥ 1.5 | the beats that carry the style clear the style's own floor |
| `dwell_pct` | ≥ 25.0 | a quarter of the film lets the image breathe |
| `longest_dwell_s` | ≥ 2.0 | at least one shot is genuinely allowed to rest |
| `accents_per_min` | 2.0–14.0 | accents are events, not a texture |

The first six are `motionprofile.TARGETS` and apply to every style. The last
three are `STRICT_TARGETS` and appear only under `--strict`: they are an
aesthetic a style opts into, and the grader itself says a style can be
structurally unable to reach them. This one reaches them, so it claims them.

`tier_separation` is the one that says whether the animation stage bought
anything: at `1.0` the loud beats and the quiet beats are indistinguishable and
the plan may as well not have existed. The worked example scores `1.52`, i.e.
its loud beats really do move about half again as much as its quiet ones.

The worked example passes all nine under `--strict`, but it did not start
there, and the failures were worth more than the passes. `longest_hold_s`
failed at 5.4 s until the compiler learned to give a shot that would otherwise
freeze the smallest camera creep that keeps every frame different. `hit_rate`
sat at 0.57 because three beats the plan marked loud measured quiet — and each
one turned out to be a real staging fault rather than a metrics quirk: a
helicopter parked on the tarmac, an "overtaking" cyclist standing still, and an
impact cut between two shots that shared a set, a camera and therefore most of
their pixels.

Treat the table as nine questions, not nine gates: a failure tells you to go
and look at that moment and decide, and only then to change something. Twice
here the honest answer was to change the film, not the threshold.

**Pass `--strict`.** Without it the tool prints `N check(s) failed` and still
exits `0`, which is exactly the shape of failure a CI step sails past.

**Always pass `--timeline` too.** The plan's clock comes from raw narration
clips that still carry their recorded silence; the renderer trims it and its
film is shorter. Without the timeline the check compares the right shots at the
wrong moments — on one validation film the two clocks differed by 24 seconds.

The renderer publishes `<output-stem>.timeline.json` for exactly this reason.
It carries the resolved line times, every shot's start, end, tier, `on`, set,
impact cues and camera move, the parallax table and the pacing report — so the
comparison never has to guess.

## 6. Determinism

```bash
python3 $S/scripts/render.py sb.json --self-test
```

Renders a short window twice — once at `-j 1`, once at `-j 4` — and compares
SHA-256. `--self-test-seconds S` sets how much of the film that window covers.

Segment boundaries are computed from running time and frame rate alone, never
from the worker count, so every `-j` must produce the same bytes. A mismatch
means unseeded randomness has got into a drawing routine — the usual culprits
are `random` without a seed, `time`, or dict iteration order.

The same check on the whole film, if you want it, is the same thing written out
by hand — just keep the scratch files out of the repository:

```bash
D=~/.cache/film-crew/verify && mkdir -p $D
python3 $S/scripts/render.py sb.json -o $D/a.mp4 -j 1
python3 $S/scripts/render.py sb.json -o $D/b.mp4 -j 4
shasum -a 256 $D/a.mp4 $D/b.mp4      # must match
```

The audio engine has its own one-line version, which is the fastest way to find
out whether a change to the mix was intended:

```bash
python3 $S/scripts/audio.py --digest
```

---

## Before it ships

- [ ] Contact sheet read, and actually looked at
- [ ] `compile.py --check` exits 0 with **zero placeholders**
- [ ] Format, loudness and motion as above
- [ ] `motionprofile.py --plan --timeline --strict` exits 0
- [ ] `--self-test` passes
- [ ] `registry.py doctor 2d-animation` clean
- [ ] Every comic hold survived — count them on the sheet against the script
- [ ] No `[ART: …]` placeholder anywhere in the finished film

```bash
python3 skills/production-designer/scripts/registry.py doctor 2d-animation
```

should print `2d-animation: ok` and list `ffmpeg`, `ffprobe`, `PIL` and
`numpy` — the four things this style cannot run without.

The last two are the ones that get skipped. A placeholder that reached the
render is a picture the style promised it would never invent, and a comic hold
quietly optimised away is the difference between a comedy and a summary of one.

---

## Never let the validator mirror the film

`scripts/check-physics.mjs` runs in plain Node, outside Remotion, so it cannot
import a `.jsx` film. The obvious workaround is to keep a hand-written copy of
the film's paths inside the validator.

**Do not do this.** It has already cost a full afternoon.

The picnic's paths were retimed. The search-and-replace matched the validator's
whitespace and silently did not match the film's, so three segment durations
changed in one file and not the other. The validator went on printing

```
physics: 36 checks clean
```

for four more render cycles — while the film contained a segment of *negative*
duration (`SKID - 15.0` with `SKID` at `14.0`) and ended with its subject nine
hundred units outside the frame. Every check passed because the validator was
faithfully validating **itself**.

A mirror that drifts is strictly worse than no validator at all, because it
converts a visible bug into a passing test and buys the bug a signature.

### The shape that works

Put the paths in a **plain-JS module** both sides import:

```
remotion/src/films/picnic.paths.js     <- clock, seg/place, all four paths
    ^                    ^
    |                    |
Picnic.jsx          check-physics.mjs
```

The film keeps the JSX; the *numbers* live somewhere Node can reach.

Anything genuinely unreachable — stride lengths, which are measured off the
rigs in `Humaaans.jsx` and `Dog.jsx` — becomes a **parameter** rather than a
copy:

```js
export const picnicPaths = ({WALK, KID_WALK, KID_RUN, DOG_TROT, DOG_BOUND}) => …
```

The film passes the rig's real numbers. The validator passes the ones it
derives independently from the same skeleton constants. Now the duplication is
load-bearing: the two derivations are a **cross-check**, and a disagreement
between them is a real finding rather than a silent lie.

### And make impossible states throw

The negative duration was survivable only because `seg` accepted it — a key
placed before the one it follows interpolates straight through, so the film
teleports rather than erroring. It now refuses:

```js
if (!(dur > 0)) throw new Error(`seg: duration must be positive, got ${dur}`);
```

A retime that produces a negative leg is always a bug. Fail at build time, not
in the ninth contact sheet.

### Symptom → cause

| What you see | What it usually is |
|---|---|
| Validator clean, render obviously wrong | The validator is a mirror; go and diff it against the film |
| A subject leaves frame and never returns | Camera cannot close a gap wider than the lens — shorten the **travel**, not the lens |
| Character teleports across a beat | Negative or zero segment duration |
| Everyone lands in the wrong place after a retime | A path authored forwards from a start; anchor the **arrival** with `place()` |
