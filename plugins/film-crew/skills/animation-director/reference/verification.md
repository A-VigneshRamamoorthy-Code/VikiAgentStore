# Verification

How to tell whether a film was directed or merely rendered.

```bash
A=skills/animation-director/scripts

python3 $A/motionprofile.py film.mp4                      # profile
python3 $A/motionprofile.py film.mp4 --plan motion-plan.json \
                                     --timeline film.timeline.json
python3 $A/motionprofile.py --compare before.mp4 after.mp4
python3 $A/motionprofile.py film.mp4 --strict             # also grade stillness
```

The profiler streams 320×180 greyscale frames from ffmpeg and measures the
mean absolute difference between consecutive frames. It is fast — about two
seconds for half a minute of film — so it belongs in the edit loop, not at
the end of it.

## The graded checks

| check | want | what it means |
|-------|------|---------------|
| `p90` | ≥ 2.2 | the loud tail is genuinely lively |
| `dynamic_range` | ≥ 2.2 | p90 ÷ median — loud moments rise clear of quiet ones |
| `longest_hold_s` | ≤ 2.5 | no frozen frame outstays its welcome |
| `tier_separation` | ≥ 1.35 | **the thesis** — planned-loud beats really are louder |
| `hit_rate` | ≥ 0.75 | the beats marked loud actually register as accents |
| `loud_mean_delta` | ≥ 1.5 | the beats carrying the style clear the style's own floor |

The last three need `--plan`.

## Why the global mean is not graded

It is the obvious metric and it is the wrong one.

A style's mean-motion floor is calibrated on undirected boards, where every
beat gets identical treatment. A directed film spends most of its runtime
deliberately quiet, so its mean is *supposed* to fall. Measured on the
validation story:

| | undirected | directed |
|---|-----------|----------|
| mean | **1.749** | **1.282** |
| p90 | 3.824 | 2.812 |
| dynamic_range | 3.01 | 3.27 |
| loud beats | 1.802 | 1.742 |
| quiet beats | 1.785 | 1.118 |
| **tier_separation** | **1.009** | **1.558** |

The undirected cut moves more and reads flat. Grading on the mean would pass
it and fail the directed cut — rejecting exactly the films this skill exists
to make. `p90` is graded instead, because a lively tail is what the floor was
really protecting, and `loud_mean_delta` holds the loud beats to the style's
original standard.

## tier_separation

The average frame-difference during planned-loud shots (`full`, `sakuga`,
`impact`) divided by the average during planned-quiet ones (`hold`,
`limited`).

- **≈ 1.0** — undirected. Motion is a texture. This is the default state of
  any compiler that gives every beat a camera move.
- **1.35+** — directed.
- **above ~2.5** — check the quiet beats are not simply dead.

It is deliberately independent of a style's absolute motion floor, so the same
bar applies everywhere.

## Always pass --timeline

The motion plan's seconds come from the beat plan, whose clock sums raw
narration clips that still carry their recorded silence. The renderer trims
that silence, so its film is shorter — 101.7s against a planned 126.0s on the
validation story, a fifth of the running time.

Without `--timeline`, the profiler falls back to linear scaling and says so.
That is an approximation; with the renderer's published
`<output-stem>.timeline.json` every shot is re-resolved from its line-relative
`at` and the check is exact.

## Reading stray accents

`--plan` reports accents that no shot asked for. A handful is normal — an
entrance or a cut will register. Dozens means the style is generating motion
on its own account and the plan is not really in control.

Measured: the undirected cut hit all 11 planned accents *and* 29 unplanned
ones. It was not failing to accent; it was accenting everything, which is the
same as accenting nothing.

## What this cannot tell you

It measures pixels, not meaning. A film can score perfectly and still put its
sakuga cut on the wrong line. The profile tells you the *distribution* is
right; only watching the film tells you the *choices* are.

Two specific blind spots worth knowing:

- **Cropping.** Motion metrics improve as you push the camera harder, right up
  to the point where the push is eating your captions. Render a contact sheet
  (`render.py board.json --sheet`) and read it.
- **Renderer quantisation.** A parameter can be honest in the board and absent
  from the film. `style-paper` caches element transforms on quantised scale
  and rotation, so doubling every element's idle drift moved the finished
  film's mean from 1.280 to 1.284 — effectively nothing. Always confirm a
  lever works by measuring the render, never by reading the storyboard.
