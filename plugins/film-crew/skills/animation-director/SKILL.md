---
name: animation-director
description: >
  Decides how much motion every beat of a film gets, the way a TV anime
  allocates drawings: most shots held almost still, a handful given
  everything. Produces a style-neutral motion plan and measures the finished
  render against it. Use when a video looks busy but flat, when motion feels
  like wallpaper, or whenever a beat plan is about to be compiled into a film.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Animation director

A Japanese TV series ships a 22-minute episode on roughly **3,000–4,000
drawings**. Full animation would need 12,000 or more. The episode does not
look four times cheaper, because the missing drawings were not shaved evenly
off every shot — they were taken from the shots nobody was watching closely
and handed to the three or four that carry the episode.

That is your entire job: **decide where the money goes.**

You sit between the storyboard artist and the production designer. The board
says *what* is on screen and *when*. You say *how hard each beat works*. The
style then renders it. You never choose colours, fonts or artwork.

Your deliverable is `motion-plan.json`.

## The one idea

Even motion reads as no motion.

A film where every beat gets the same gentle push has no accents, because an
accent is a *contrast*, not a quantity. The measurement that proves this is
`tier_separation` — the average motion during beats you marked loud, divided
by the average during beats you marked quiet:

| cut | separation | verdict |
|-----|-----------|---------|
| undirected, one camera move per beat | **1.009** | motion as wallpaper |
| same board, directed | **1.558** | motion as punctuation |

The undirected cut was not lazy. It moved *more* overall — mean 1.749 against
1.282 — and it still read flat, because its loud beats (1.802) were
indistinguishable from its quiet ones (1.785). Spending less, unevenly, is
what bought the drama.

## The five tiers

Every beat gets exactly one.

| tier | cost | what it is |
|------|------|-----------|
| `hold` | 1 | One drawing. Camera parked. Alive only through a slow ambient drift. |
| `limited` | 2 | One drawing under a slow push (*yori*), 5–12% over 2–4s. |
| `full` | 5 | Things arrive, the camera travels. |
| `sakuga` | 12 | The showcase cut. **One to three in an entire film.** |
| `impact` | 1 | A held drawing whose *first frames* are a jolt — flash, shake — then it sits. |

`impact` is the one people get wrong. It is not a short shot; it is a *cheap*
one. The jolt lasts 6–18 frames and the drawing it slams into is held. A
first implementation here selected impacts by looking for beats under 1.6
seconds and found none, because the average beat was 3.4 seconds. The gate is
emphasis, not duration.

## The distribution law

Enforced by `framebudget.py --check`, and worth knowing by heart:

- **≥ 35%** of beats are `hold`
- **≥ 62%** of beats are `hold` or `limited` — the cheap majority
- **≤ 28%** are `full`
- **1 to 3** `sakuga` cuts, never zero, never four
- **≤ 38%** of beats get any camera move at all
- no run of holds longer than **13 seconds**

That last rule exists because the allocator, left alone, produced eleven
consecutive holds spanning 37 seconds of a two-minute film. A run that long
stops reading as restraint and starts reading as a broken render.

## Workflow

```bash
A=skills/animation-director/scripts

# 1. Allocate. Reads the beat plan, writes the motion plan.
python3 $A/framebudget.py beat-plan.json -o motion-plan.json

# 2. Audit the distribution against the law.
python3 $A/framebudget.py beat-plan.json --check

# 3. Compile through a style that accepts a plan.
python3 skills/style-paper/scripts/compile.py beat-plan.json \
        -o storyboard.json --motion-plan motion-plan.json

# 4. Render, then judge the film against the plan you wrote.
python3 $A/motionprofile.py film.mp4 --plan motion-plan.json \
        --timeline film.timeline.json
```

**Always pass `--timeline`.** The plan's seconds are computed from raw
narration clips, which still carry their recorded silence; the renderer trims
that silence and its film is shorter. On the validation story the two clocks
differed by 24 seconds across a 126-second plan — a fifth of the running time
— so a plan checked without it compares the right shots at the wrong moments.
The renderer publishes `<output-stem>.timeline.json` for exactly this reason.

## Rules you may not delegate

1. **Choose the sakuga cut yourself.** The distribution is mechanical; the
   peak is a story decision. The allocator will pick the highest-emphasis beat
   in the last third, which is a defensible guess and nothing more. Open the
   plan and move it to the moment that earns it.
2. **Never raise every tier at once.** If the film feels weak, the fix is to
   lower the quiet beats, not lift the loud ones. Separation is a ratio.
3. **A budget is spent, not cut.** Damping the quiet beats alone dropped the
   validation film below its own style's motion floor. Whatever you save on
   the held beats must be handed to the loud ones.
4. **Check the render, not the plan.** A plan that audits clean can still
   produce a flat film if the style ignores half of it. Only
   `motionprofile.py` against the finished `.mp4` settles it.

## What "cheap" looks like when it goes wrong

These are the failure modes that make limited animation read as *badly made*
rather than *economical*:

- a camera move on every shot (the flat-wash trap — this is the default)
- a push with no easing, or with no pause before and after it
- a held drawing with nothing moving in it at all
- the same walk cycle looping over a background that visibly repeats
- a bank of stock footage dropped into the wrong emotional register

## Reference

| file | when to read it |
|------|-----------------|
| [`reference/frame-economy.md`](reference/frame-economy.md) | the numbers — ones/twos/threes, cut counts, hold lengths |
| [`reference/camera-and-overlays.md`](reference/camera-and-overlays.md) | how to buy motion without drawing: yori, parallax, particles, shake |
| [`reference/reuse.md`](reference/reuse.md) | walk cycles, bank systems, the Blue Lock playbook |
| [`reference/motion-plan.md`](reference/motion-plan.md) | the `motion-plan.json` schema |
| [`reference/verification.md`](reference/verification.md) | every metric, what it means, and what it cannot tell you |
| [`examples/`](examples/) | a validated 37-beat plan and its measured before/after |
