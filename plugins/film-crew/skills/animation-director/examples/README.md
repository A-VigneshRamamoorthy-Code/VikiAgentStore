# Worked example — *The Last Lantern on Kestrel Hill*

The film this skill was validated on. An original 24-line short story, boarded
as 37 beats, rendered twice through `style-paper` — once ignoring the motion
plan and once obeying it — and measured both times.

| file | what it is |
|------|-----------|
| `lines.json` | the narration script, 24 lines |
| `beat-plan.json` | 37 beats, validates clean, 126.0s on the plan clock |
| `motion-plan.json` | the allocation this skill produced |

## Reproducing it

```bash
F=skills                       # from the film-crew plugin root

python3 $F/voice-booth/scripts/narrate.py lines.json -o vo/ \
        --voice en-GB-RyanNeural --rate "-10%"
python3 $F/storyboard-artist/scripts/beatplan.py beat-plan.json

# the undirected cut
python3 $F/style-paper/scripts/compile.py beat-plan.json -o sb-baseline.json
python3 $F/style-paper/scripts/render.py sb-baseline.json

# the directed cut
python3 $F/animation-director/scripts/framebudget.py beat-plan.json \
        -o motion-plan.json
python3 $F/style-paper/scripts/compile.py beat-plan.json -o sb-directed.json \
        --motion-plan motion-plan.json
python3 $F/style-paper/scripts/render.py sb-directed.json

# the verdict
python3 $F/animation-director/scripts/motionprofile.py directed.mp4 \
        --plan motion-plan.json --timeline directed.timeline.json
```

## The allocation

37 beats, 100 drawing-cost units, 2.7 per shot.

| tier | shots | share | runtime |
|------|-------|-------|---------|
| `hold` | 13 | 35.1% | 34% |
| `limited` | 13 | 35.1% | 36% |
| `full` | 7 | 18.9% | 20% |
| `sakuga` | 2 | 5.4% | 6% |
| `impact` | 2 | 5.4% | 5% |

Cheap share 70.3%. Only 24.3% of beats get a camera move at all.

## The result

| | undirected | directed |
|---|-----------|----------|
| camera moves | 37 | 23 |
| shake events | 0 | 2 |
| zoom range | 1.00–1.10 | 1.00–1.19, per-beat |
| camera rests | {0.4, 0.5} | {0.4 … 3.2} |
| mean motion | 1.749 | 1.282 |
| dynamic range | 3.01 | 3.27 |
| **tier_separation** | **1.009** | **1.558** |
| checks passed | 5 of 6 | **6 of 6** |

The undirected cut fails on one thing only: its loud beats average 1.802 and
its quiet beats 1.785. Nothing in it is an accent because everything is.

## Three things this example taught the skill

1. **Impacts are cheap, not short.** The first allocator looked for beats
   under 1.6s and found none — the average beat is 3.4s. An impact is a jolt
   into a *held* drawing; the gate is emphasis.
2. **Holds need a run limit.** The first allocation put eleven consecutive
   holds across 37 seconds. Restraint that long reads as a broken render.
3. **Zoom has a cropping budget.** Pushing to 1.32 to win the motion metric
   turned `KESTREL` into `ESTREL`. Per-beat headroom, computed from what each
   beat actually contains, gets the motion without the damage.
