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

Two more culprits, both of which have actually shipped in a renderer built with
this skill, and neither of which looks like randomness at the call site:

- **`np.random` used inside a look or grade pass.** One engine dithered its
  colour grade with the global unseeded generator, under a comment that
  asserted "the same deterministic noise at each position" — the comment
  described an intent the code did not implement. The damage was far larger
  than ±1 suggests: a nudge either side of a steep segment of a mood LUT lands
  in a different output band, so **86% of pixels differed by up to 31 code
  values** between two runs of the same frame. Seed a generator once, cache the
  pattern by shape, and reuse it.
- **Python's built-in `hash()` of a string as a seed.** String hashing is
  salted per process unless `PYTHONHASHSEED` is set, so `abs(hash(shot_id))`
  gives every worker a different number *inside one render*. Use `zlib.crc32`,
  which is stable across processes, machines and interpreter versions.

**Check run-to-run, not only across worker counts.** Render the same shot twice
with the identical command and compare. `-j 1` against `-j 4` is a good test of
segmentation but it is one comparison; the question you actually need answered
is whether the renderer is a function of its inputs at all.

**Until that answer is yes, you cannot optimise anything.** Determinism is not
hygiene here, it is the precondition for every other claim in this file. An
engine that cannot reproduce its own frames also invalidates its frame cache —
whose whole premise is that a shot's pixels are a function of its inputs — and
makes "did this change alter the picture?" unanswerable, so every optimisation
becomes an unverifiable rewrite.

### Prove an optimisation byte-identical, don't eyeball it

"Make the same picture, faster" is a claim about bytes, and bytes are cheap to
compare, so there is no reason to check it by eye. Keep a golden-frame oracle:
render the smallest shot of each render class with the cache forced off, hash
every frame, and diff against a stored baseline.

```bash
python3 tools/golden.py --record      # before the change
python3 tools/golden.py --verify      # after it, exits non-zero and names
                                      # the first differing frame
```

Two hours of measured work on one such engine gave **1.8x with every frame
byte-identical** — and the oracle earned its cost immediately by failing on the
first optimisation, which is how the two non-determinism bugs above were found.

It also disciplines the design. Two optimisations that looked obvious were
rejected because the oracle said they changed pixels, and measuring *why*
produced better versions:

- **`cv2.warpAffine` is not bit-stable under translation.** Shifting the
  translation terms to warp into a smaller destination changes ~35% of pixels
  by up to 5e-5, because OpenCV samples through a fixed-point inverse map and
  moving the translation changes the rounding. Measured, not assumed. Timing
  the two halves separately showed the *blend* cost 11.1 ms against the warp's
  1.4 ms, so the fix was to keep the bit-exact full-canvas warp and restrict
  only the blend — provably identical, since outside the transformed quad the
  alpha is exactly 0 and `x*1.0 == x`, `x+0.0 == x`.
- **A pass whose output is later masked away can be cropped — unless it
  normalises globally.** An ink pass that divides by `e.max()` over the whole
  frame cannot be cropped, because a smaller crop changes the maximum and moves
  the threshold *inside* the crop too. Keep the global edge detection and crop
  only the per-pixel compose that follows it.

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

### Schedule the render by measured cost, not by frame count

A pool of workers finishes when its *slowest worker* finishes, so a long shot
picked up last leaves three cores idle while it renders alone. The classic fix
is longest-processing-time-first — but "longest" has to mean seconds, not
frames.

Measured across 35 shots of a finished film, per-frame cost varied **5.2x**
(0.19 s to 0.98 s). A HELD shot renders one cel and copies it; a FULL shot with
two rigged characters and particles pays the whole look pass every frame. Frame
count does not predict that at all.

So persist what you measured and use it next time:

- write `{shot: seconds_per_frame}` to `work_dir/.shot-timings.json` as each
  shot completes;
- order the next run by `timing[shot] * frames`, descending;
- fall back to frame count on the first run, when no timings exist.

On that film the *simulated* makespan went `8.65 → 8.61 → 8.53` min for plan
order, frame count, and measured LPT — the last landing within **0.8%** of the
theoretical `total/workers` bound, against 2.2% for plan order.

Then measure it end to end before you believe it. Two full renders of that film
came in at **16m02s and 16m53s** — the second, with real timings driving LPT,
was the *slower* one. The predicted saving (tens of seconds) is smaller than
run-to-run noise on a laptop that thermally throttles. So: keep the scheduler,
because it is free and it provably removes the tail in the model, but do not
claim a speedup you cannot measure. **A simulated win is a hypothesis, not a
result.**

Two things to get right, or you trade a real bug for a fake speedup:

- **Sort the results back into input order.** Dispatching out of order is fine;
  *returning* out of order will silently reshuffle anything downstream that
  zips results against the plan. Sorting on the way out also makes the pipeline
  strictly more deterministic than an unordered map.
- **Re-run the golden oracle.** Reordering work changes which worker touches
  which shot, which is exactly how a latent shared-state or RNG-seeding bug
  surfaces. If the frames are still byte-identical, the reordering was safe.

The end-to-end version of that oracle is cheap and worth doing once the film is
finished: render the whole thing twice and hash the *streams*, not the file
(the container carries timestamps, the streams do not).

```bash
for f in a b; do ffmpeg -v error -i $D/$f.mp4 -map 0:v -f hash -hash sha256 -; done
for f in a b; do ffmpeg -v error -i $D/$f.mp4 -map 0:a -f hash -hash sha256 -; done
```

Two independent 4163-frame renders matching on both is the strongest statement
you can make about a pipeline: every optimisation in it is invisible in the
output.

---

## Before it ships

- [ ] **Preflight passes, and its own `--self-test` proves it can fail**
- [ ] **Renderer proven deterministic run-to-run, and the golden oracle is clean**
- [ ] Contact sheet read, and actually looked at
- [ ] `compile.py --check` exits 0 with **zero placeholders**
- [ ] Format, loudness and motion as above
- [ ] `motionprofile.py --plan --timeline --strict` exits 0
- [ ] `--self-test` passes
- [ ] **Lip-sync gate passes — differenced against a forced-rest render**
- [ ] `registry.py doctor 2d-animation` clean
- [ ] Every comic hold survived — count them on the sheet against the script
- [ ] No `[ART: …]` placeholder anywhere in the finished film
- [ ] **Frames pulled from the delivered mp4 and looked at** — faces, mouths,
      hands, and the first and last frame of every camera move

```bash
python3 skills/production-designer/scripts/registry.py doctor 2d-animation
```

should print `2d-animation: ok` and list `ffmpeg`, `ffprobe`, `PIL` and
`numpy` — the four things this style cannot run without.

The last two are the ones that get skipped. A placeholder that reached the
render is a picture the style promised it would never invent, and a comic hold
quietly optimised away is the difference between a comedy and a summary of one.

### Every check above can pass on a broken film

This is not hypothetical. A three-minute film cleared this entire list — 0
black frames, 0.000s a/v drift, −15.1 LUFS, longest frozen run 1.17s, motion
above floor, determinism proven — while its two speaking characters had **no
mouths at all**, its one close-up of a hand was drawn from primitives, and its
camera lurched twice a shot.

Nothing on the list was wrong. They measure regressions in properties the film
has; none of them can notice a property it never had. So the final gate is
always the same, and it is manual:

```bash
# Exact frames. -ss BEFORE -i seeks to a keyframe and will not give you frame n.
ffmpeg -y -i out/film.mp4 -vf "select='eq(n\,435)+eq(n\,445)+eq(n\,455)'" \
       -vsync 0 /tmp/f_%02d.png
```

Crop to whatever the audience will be looking at, tile the frames into a strip,
and look. Three specific things repay it, because all three are invisible to
every automated check here:

- **Faces during dialogue** — is the mouth moving? Sample six consecutive
  frames of one line. Do not settle for "the frames differ"; a moving camera
  and an ambient layer guarantee that whatever the mouth is doing.
- **Any part that occludes another** — a beard, a hat brim, a collar, a prop
  held near the body. Draw order does not care that a feature is animating
  underneath it.
- **The first and last frame of every camera move**, against the middle. A
  clamp engaging mid-shot reads as a lurch in motion and as nothing at all in
  a per-frame metric.

### Decide from the plan what a render would otherwise teach you

The manual gate above is the *last* line of defence, not the first. On the film
described above, **every single rejection came from a human watching the cut,
and not one came from an automated check** — roughly six full renders, four or
five of them avoidable. At 25 minutes a render that is the dominant cost of the
whole production, and most of it was spent discovering things that were already
decidable before a pixel was drawn.

Most defects of this kind are properties of the *plan and the assets*, not of
the pixels. Check them in seconds, before rendering:

- **Every asset resolves with a cold cache.** Build each set from source art
  rather than trusting a cached plate — see the cached-plate trap in
  [`asset-library.md`](asset-library.md).
- **Every speaking rig can draw every viseme its own track asks for.** Resolve
  the whole (speaker × expression × viseme) product and let it raise.
- **Every line's wav exists and matches its planned duration.** A line planned
  longer than its audio moves the mouth over silence; shorter, and the tail
  plays over a closed mouth. Both read as broken lip sync and neither is.
- **Every camera move is legal at every frame, and smooth.** Sample the real
  camera solve, not a re-derivation of it, and check both that no frame samples
  off-canvas and that no single frame's step jumps relative to its neighbours.
- **Staging is continuous.** A character must resume each shot where the last
  one left them, and must never walk to a mark they already stand on.
- **Speech plus hold fits inside each shot, and the shots tile the film.**

Two design rules make this worth trusting. **Call the real production code** —
a preflight that reimplements the rule it guards drifts away from it and then
certifies a film the renderer will still get wrong. And **exempt only on a real
property of the shot**: a narrator has no body, a prop has no mouth art, a held
cel is one frozen drawing by design. An exemption that exists to keep the
report quiet is worse than no check.

Such a suite runs in about 4 seconds against a 25-minute render.

**Then prove the gate can fail.** Inject each historical defect and require the
matching check to catch it, and to pass again once it is removed:

```bash
python3 preflight.py --self-test    # 8/8 injected defects detected
```

This is not ceremony. The first run of one such self-test showed **two of six
checks did not detect the defect they were written for** — one because the
injected fault took a legitimate fallback path, and one because the threshold
had been chosen by eye rather than measured. A check that has never fired on a
real defect is a green light with no bulb in it.

**Set thresholds from both distributions, never by eye.** For the camera-jerk
check above, the fitted camera never exceeded 0.11 across 35 shots, while
re-enabling the old per-frame clamp pushed the five shots it overrode to 0.40,
0.57, 0.68, 1.10 and 1.39. A threshold of 0.25 sits with 2.3x margin above the
clean maximum and 1.6x below the mildest real defect. The first value tried was
1.5, which was quiet on every defect.

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
physics: 37 checks clean
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
