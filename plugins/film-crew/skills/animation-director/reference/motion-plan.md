# motion-plan.json

Style-neutral. It names beats and how hard each one works; it never names a
colour, a font or an asset. Any style may consume it, and a style that ignores
it must still render a valid film.

Written by `framebudget.py`, read by a style's compiler and by
`motionprofile.py`.

```jsonc
{
  "schema": 1,
  "title": "The Last Lantern on Kestrel Hill",
  "runtime_s": 126.034,          // from the beat plan's clock, not the render's
  "accent_tolerance_s": 0.75,    // how far a measured accent may sit from its shot
  "summary": { ... },            // counts, shares, drawing cost — see below
  "law": { ... },                // the thresholds this plan was audited against
  "shots": [ ... ]
}
```

## A shot

```jsonc
{
  "id": "b12",
  "beat": "b12",                 // the beat-plan id this belongs to
  "intent": "portrait",          // copied from the beat plan
  "at": "l7+2.60",               // line-relative, and the field that survives retiming
  "start": 35.834,               // seconds, on the beat plan's clock
  "end": 38.166,
  "duration": 2.332,
  "emphasis": 0.45,              // copied from the beat plan
  "subject": "Mira turned eighty that winter",

  "tier": "hold",                // hold | limited | full | sakuga | impact
  "camera": "still",             // still | push | track | travel | shake
  "cost": 1,                     // notional drawing cost, for the budget total
  "amount": 0.0,                 // how much camera, 0.0-0.3; 0 for held shots
  "secondary": ["sway", "grain"],// what keeps the shot alive while it is held
  "pre_hold": 0.35,              // stillness before anything starts
  "why": "held — let the picture sit and the voice carry it"
}
```

### `at` is the field that matters

`start` and `end` are convenience values on the **beat plan's** clock, which
is built from raw narration clips and runs long — 126.0s against a finished
film of 101.7s on the validation story. `at` is line-relative and survives,
so both `motionprofile.py` and any style compiler re-resolve it against the
renderer's published `*.timeline.json`. Never treat `start` as a position in
the finished film.

## `summary`

```jsonc
"summary": {
  "shots": 37,
  "counts":  { "hold": 13, "limited": 13, "full": 7, "sakuga": 2, "impact": 2 },
  "shares":  { "hold": 0.351, "limited": 0.351, "full": 0.189, ... },
  "cheap_share": 0.703,          // hold + limited
  "emphatic_share": 0.243,       // shots that get any camera move
  "held_seconds": 42.85,
  "held_share_of_runtime": 0.34,
  "drawing_cost": 100,           // sum of per-shot cost
  "cost_per_shot": 2.7           // the headline economy number
}
```

`cost_per_shot` is the one to watch. A film where every beat got a camera move
scores 2.0 by definition and tells you nothing; a directed film lands near 2.7
with the spread concentrated, and a runaway one climbs past 4.

## What a style is expected to do with it

A style consuming a plan should, at minimum:

- give `hold` and `impact` beats **no camera move at all**, extending the
  previous move's rest instead
- scale its push by `amount` for `limited`, `full` and `sakuga`
- add its own jolt on `impact`, decaying
- keep its expensive entrance animations for the loud tiers and soften them
  elsewhere

`style-paper` implements all four in `apply_motion_plan()`; read it as the
reference implementation.
