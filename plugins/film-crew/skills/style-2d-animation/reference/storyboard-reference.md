# The storyboard

`storyboard.json` is this style's own board. `compile.py` writes it from a
style-neutral [beat plan](../../storyboard-artist/reference/beat-plan.md), and
`render.py` turns it into video.

Unlike `style-paper`, whose board is one continuous surface, **this board is a
shot list**. The film cuts.

---

## Top level

```json
{
  "schema": 1,
  "style": "2d-animation",
  "title": "Pursuit",
  "seed": 19,
  "output": { "path": "pursuit.mp4", "width": 1920, "height": 1080, "fps": 30 },
  "palette": "pursuit",
  "cast": { "driver": { "shirt": [188, 62, 54] } },
  "narration": [ … ],
  "music": { "mood": "chase", "gain": 0.8 },
  "ambience": "city",
  "mix": { "music": 0.62, "duck_db": 11.0 },
  "timing": { "lead_in": 1.2, "tail": 1.6 },
  "shots": [ … ]
}
```

| field | required | meaning |
|---|---|---|
| `schema` | yes | `1` |
| `style` | yes | `"2d-animation"`. The renderer refuses another style's board |
| `title` | yes | default output filename |
| `seed` | no | every random choice derives from this, so a board reproduces byte-for-byte |
| `output` | yes | `width`/`height` decide the aspect: `1920×1080` or `1080×1920` |
| `palette` | no | a name from `look.PALETTES`, or one `look.derive` has minted; omitted means chosen from `music.mood` and `title` |
| `cast` | no | per-character colour overrides. See below |
| `narration` | no | spoken lines. **Omit entirely for a wordless film** |
| `music` | no | `mood` from the score vocabulary, plus `gain` |
| `ambience` | no | a continuous bed under the whole film — a name, or `{ "name": …, "gain": … }` |
| `mix` | no | bus levels and ducking depths. See [`audio-style.md`](audio-style.md) |
| `timing` | no | `lead_in` before the first word, `tail` after the last, `gap` as the default `gap_after`, `min_duration` as a floor. See below |
| `shots` | yes | the film |

`compile.py` writes `schema`, `style`, `title`, `seed`, `output`, `timing`,
`shots` and — when the story gives it one — `music`, `narration` and
`ambience`. `palette`, `cast` and `mix` are hand-added when a film needs them.

### `timing`

| key | default | is |
|---|---|---|
| `lead_in` | `0.6` | silence before the first word |
| `tail` | `1.2` | silence after the last |
| `gap` | `0.55` | the `gap_after` a line gets when it does not say |
| `min_duration` | `0.0` | a floor on the whole film, for a delivery slot |

`shots.py` and `audio.py` share those defaults, so a board that omits `timing`
altogether is timed identically by both. `compile.py` is the exception: when it
*writes* a board it puts in a more generous `lead_in: 1.0` and `tail: 1.5`,
because a film assembled from a beat plan has a title to get out of the way of.
Either way the value in the board wins — the defaults only cover its absence.

### `cast`

`rig.draw` takes one palette, so a costume reaches it as a variant of the
film's own. Each entry may override `skin`, `hair`, `shirt`, `trouser`, `shoe`,
`accent`, `accent2` and `ink`; anything else in the entry is ignored.

```jsonc
"cast": { "officer": { "shirt": [40, 62, 118], "trouser": [30, 40, 76] } }
```

**A board with a `cast` table is checked against it.** An actor naming a `cast`
that is not in the table is drawn as a labelled placeholder — that is how a
typo becomes visible instead of becoming a character in the wrong coat. A board
with no `cast` key at all is simply a film whose characters all wear the
palette's clothes, which is a look decision, not a missing picture.

Do not confuse the board's `cast` with `compile.CAST`, which is a different
table for a different job: the five archetypes the compiler knows how to stage
when a beat plan names a character, each with a costume word, a `build` size
multiplier and a height.

| `compile.CAST` | shirt | build | height |
|---|---|---|---|
| `norman` | `cardigan` | `1.00` | `18.0` |
| `officer` | `uniform` | `1.05` | `18.4` |
| `cyclist` | `lycra` | `0.92` | `17.4` |
| `reporter` | `jacket` | `0.96` | `17.8` |
| `civilian` | `plain` | `1.00` | `18.0` |

The heights are the interesting column: 17.4 to 18.4 is a spread of one whole
scene unit, about a quarter of a head-width — enough to tell two silhouettes
apart in a long shot without anybody looking like a different species.

### Narration is optional, and that is a feature

```jsonc
"narration": [
  { "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.5, "filter": "radio" }
]
```

| field | meaning |
|---|---|
| `id` | the handle shots point at |
| `audio` | path to the clip, relative to the board |
| `duration` | instead of `audio`, to reserve silent time before the voice exists |
| `gap_after` | silence after the line — **this is where pacing lives**. Defaults to `timing.gap`, `0.55` |
| `gain` | line level, `1.0` by default |
| `filter` | `none` (default), `radio`, `tannoy`, `phone`. A band-limited voice for a diegetic narrator |

Every clip is **trimmed of its recorded silence** before it is laid down, so
the film's clock is shorter than the sum of the source files. That is why
`--timeline` exists — see [`verification.md`](verification.md).

`filter: "radio"` is what makes a news-chopper reporter sound like she is
actually in a helicopter rather than in a booth. It is a **diegetic** choice: use
it when the narrator exists inside the film, never for a neutral voice-over.

With no `narration` key at all the film is scored and cut to music and SFX
alone, every shot's `at` is absolute seconds, and every shot must carry an
explicit `dur` or an absolute `until`.

---

## A shot

```json
{
  "id": "s7",
  "at": "l6", "until": "l7",
  "tier": "full",
  "on": 2,
  "set": "street",
  "camera": { "move": "track", "from": [50, 28], "to": [74, 28],
              "zoom": [1.0, 1.05], "ease": "inout", "hold": 0.4 },
  "actors": [
    { "id": "driver", "cast": "driver", "action": "drive",
      "at": [46, 44], "facing": 1, "rate": 1.0 }
  ],
  "props": [
    { "kind": "car", "at": [46, 44], "scale": 1.15, "anim": "bounce" }
  ],
  "overlay": { "kind": "chyron", "text": "LIVE — JUNCTION 9" },
  "sfx": [ { "kind": "siren", "at": 0.0, "gain": 0.7 } ],
  "note": "she says he is cornered; he is not"
}
```

| field | required | meaning |
|---|---|---|
| `id` | yes | unique. Two shots with one id is a `ShotError` |
| `at` | yes | when the shot starts — a line-relative time, exactly as in the beat plan (`"l6"`, `"l6+0.3"`, `"l6.end"`), or absolute seconds in a wordless film |
| `until` / `dur` | one | when it ends. `until` takes the same time syntax and is preferred, because it cannot drift when a line is re-recorded. A shot with neither is a `ShotError` |
| `tier` | no | `hold` `limited` `full` `sakuga` `impact` — from the motion plan |
| `on` | no | animate on ones, twos or threes. Defaults from `tier` |
| `set` | yes | a key of `sets.SETS`: `street` `highway` `suburb` `aerial` `office` `sky` |
| `camera` | no | see below. Omitted means a locked-off camera |
| `actors` | no | characters in the shot |
| `props` | no | vehicles, objects, scenery pieces |
| `overlay` | no | one overlay: `chyron` `title` `map` `circle` `split` `counter` |
| `sfx` | no | effects, timed against this shot |
| `impact` / `accent` | no | when something lands, so the frames around it go on ones |
| `beat` | no | the beat this shot came from. `pacing_report` reads it as a *kind* word, not an id — see below |
| `kind` | no | the same thing under a clearer name, and checked first if `beat` is absent |
| `note` | no | ignored by the renderer, read by humans |

### It is a cut list, and it is checked like one

`shots.build` refuses anything that is not a clean sequence of cuts, because
two pictures at once is not a dissolve here, it is an ambiguity about which one
the frame shows:

- Shots must be **listed in the order they play**, or `ShotError`.
- Two shots that **overlap** are a `ShotError`, with the overlap measured in
  the message.
- A shot that ends at or before it starts is a `ShotError`.
- A **gap** is legal but loud: the previous shot's last frame is held across
  it and a warning names both shots. Time before the first shot holds its
  opening frame, so a film never cuts to black by accident.
- A narration line that would run past the end of the film is a `ShotError`,
  because a line cut off mid-word is never what anyone meant.

On top of that `pacing_report` prints advisory notes — mean shot length outside
`3–4 s`, cut rate outside `~15.5–23.3` per minute, a `hold` tier shorter than
`MIN_HOLD_FRAMES` (20 frames), a reaction outside `1.0–1.5 s`, a setup outside
`6–10 s`. **Nothing there raises.** A deliberate comic hold is allowed to run
straight past the band; that is the point of it.

The last two of those need a word of warning. `pacing_report` decides what a
shot *is* by lower-casing `beat`, falling back to `kind`, and matching it
against a fixed vocabulary: `reaction` `react` `cut-in` `cutin` for the
reaction band, `setup` `establish` `establishing` `reveal` for the setup band.
But `compile.py` writes the beat's **id** into `beat` — `"b14"`, not
`"reaction"` — so on a compiled board neither check ever fires. If you want
them, add `"kind": "reaction"` to the shot by hand. It costs nothing and it is
the only pacing feedback in the tool that knows what a shot is for.

### `on` — ones, twos and threes

The most important number in the file.

| `on` | effective rate | for |
|---|---|---|
| `1` | 30 fps | `sakuga` only — the one cut that earns it |
| `2` | 15 fps | the default for anything that moves |
| `3` | 10 fps | held shots, background business |

Left to the tier, `shots.ON_FOR_TIER` decides: `hold` and `limited` go on
threes, `full` and `impact` on twos, `sakuga` on ones. A board with neither
`on` nor `tier` gets twos.

Holding each drawing for two frames is not a cost saving that happens to look
right. It **is** the look: hand-drawn television animation is shot on twos, and
a film rendered entirely on ones reads as a Flash tween — smooth, weightless
and cheap. The renderer therefore quantises pose evaluation to `on`, while the
camera keeps moving every frame, because a camera on twos judders visibly.

Two documented exceptions break the hold, both deliberately:

- **An impact goes on ones.** Any frame within `IMPACT_ONES_FRAMES` (2) of a
  cue listed in `impact`, `accent`, an actor's `impact` or an actor's `squash.at`
  is drawn fresh, so a contact reads as anticipation, hit and recoil rather
  than as one smeared drawing. An `impact`-tier shot with no cue named puts
  the contact on the cut itself.
- **A smear breaks the hold.** When `anim.smear` decides a limb has crossed
  more distance than the eye can follow, the drawing is rebuilt every frame
  across the held interval — a smear that is itself held for two frames reads
  as a rendering fault rather than as speed. `hold`-tier shots are exempt.

### `camera`

| field | meaning |
|---|---|
| `move` | `none` `push` `pull` `track` `pan` `whip` `follow` `handheld`. An unknown name falls back to `none` |
| `from` / `to` | scene-unit centre at the start and end |
| `zoom` | `[start, end]` scale factors, or one number for a fixed zoom |
| `ease` | any name from `anim.ease`, plus `creep`. Defaults to **`out`** — `overshoot` on a `whip` |
| `hold` | seconds to settle at the end before the cut |
| `pre_hold` | seconds to sit still *before* the move starts |
| `subject` | actor id — `follow` keeps this actor at a fixed frame position |
| `frame` | where a followed subject sits, `[fx, fy]` as fractions of the view. Default `[0.5, 0.56]` |

A `push` with no `zoom` still pushes (`1.0 → 1.12`), and a `pull` still pulls,
because otherwise the board's word for the move would mean nothing.

**Mechanical easing is refused.** `linear`, `in` and `hold` do not decelerate
into a final framing, so on any moving camera they are swapped for the default
and the substitution is printed. A camera that arrives at constant speed and
simply stops reads as a machine rather than as an operator finding a frame.

**`creep` is the one constant-rate ease, and it is not a way round that.**
`linear` stays banned for any move the audience is meant to perceive; `creep`
is exempt precisely because it must *not* be perceived. Use it for the rescue
move on a long, otherwise-static shot — the drift whose only job is that no two
frames come out identical, so a held shot never renders as a frozen run:

```json
"camera": { "move": "push", "zoom": [1.55, 1.90], "ease": "creep" }
```

An ease-out here would be wrong twice over: it leaves at 3.64× its average
speed (a spurious accent) and arrives asymptotically (the frozen tail returns).
Two rules `shots.py` will warn about:

- a creep slower than **2%/s of the view** (`shots.CREEP_MIN_RATE`) is a freeze
  with extra steps — a 5.2s shot wants roughly 9% of view change, e.g. a push
  from `1.55` to `1.86`;
- more than **1.0s** of `hold`/`pre_hold` (`shots.CREEP_MAX_SETTLE`) locks the
  camera off for exactly as long, which is the run the creep was added to
  prevent. A short settle is fine: 0.6s measured a 0.53–0.57s identical-frame
  run, and removing it took that to 0.00–0.03s.

Do not use `creep` for a move that carries meaning. That move should decelerate.

`handheld` is reserved for the chopper's own camera: three seeded sine
components summed into a slow wander, plus the operator taking about 55% of it
back a second and a half later. It is deliberately **not** a spring — a spring
rings, and a rung camera is a shake. It rides the film's clock, not the shot's,
so two adjacent handheld shots do not start at the same point in the same wave.

On a `hold`-tier shot with no `from`, `to` or `zoom` of its own, the drift is
switched off entirely and the frame is genuinely locked. A hold is the joke
landing, and the one thing that can ruin it is the renderer being helpful.

### `actors`

| field | meaning |
|---|---|
| `id` | unique within the shot; `camera.subject` may name it |
| `cast` | a key of the board's `cast` table — the costume |
| `action` | a `poses.POSES` name, or a list of keyframes (below) |
| `at` | **pelvis** position, scene units — see [`rig.md`](rig.md) |
| `to` | travel to here across the shot |
| `ease` | the curve for `to`. Defaults to `linear` |
| `facing` | `1` or `-1` |
| `rate` | cycles per second. `1.0` ≈ two steps a second |
| `phase` | starting phase, `0..1` — offset two walkers so they are not in lockstep |
| `height` | override the default `18` |
| `z` | `0..1` depth; distant actors are hazed towards the sky and drawn first |
| `tilt` | whole-body rotation, degrees |
| `squash` | `{ "at": sec, "impact": 0.25, "decay": 6.0 }` — a landing, rung down. See below |
| `shadow` | `false` to suppress the contact ellipse. Almost never right |
| `impact` | shot-local seconds at which this actor lands |

`squash` is the one actor field with its own defaults, and they are **not**
`anim.squash_stretch`'s. The renderer reads exactly three keys — `at`,
`impact` and `decay` — and supplies `0.25` and `6.0` where the module itself
would use `0.18` and `8.0`. The default `impact` is not arbitrary: `1 - 0.25`
is `0.75`, the calibrated hard landing. A bare `{"at": 1.2}` is therefore a
hard landing that rings down lazily, over roughly half a second rather than
the table's six frames. `at` is shot-local seconds, and `t = at` is the
**contact frame at full compression**, not the approach.

The module's `event=` shortcut — `hard_landing`, `soft_landing`, `crouch`,
`apex`, `pop`, the calibrated table in
[`animation-principles.md`](animation-principles.md#4-squash-and-stretch) — is
**not reachable from a board**: `render.py` never forwards it. Convert by
hand instead. The height column is `1 - impact` and the module's decay is
`3.2 × 30 / (contact + settle)`, which reproduces the event exactly:

| event | board equivalent |
|---|---|
| `hard_landing` | `{"impact": 0.25, "decay": 16.0}` |
| `soft_landing` | `{"impact": 0.12, "decay": 24.0}` |
| `crouch` | `{"impact": 0.15, "decay": 10.7}` |
| `apex` | `{"impact": -0.18, "decay": 16.0}` |
| `pop` | `{"impact": -0.20, "decay": 16.0}` |

A negative `impact` stretches instead of squashing, which is how a jump apex
and a startled pop are expressed in the same field.

**Anything else on the actor is passed straight to the pose function.** That is
how `{"action": "point", "dir": -1}` and `{"action": "react", "kind": "glee"}`
work without the renderer knowing the pose vocabulary — and it is why a typo
in a field name is silently accepted by the renderer and rejected by the pose.

The seven actions are `stand` `walk` `run` `panic` `drive` `point` `react`.

Keyframed acting instead of a cycle:

```json
"action": [
  { "t": 0.0, "pose": "stand" },
  { "t": 0.5, "pose": "react", "kind": "shock", "ease": "anticipate" },
  { "t": 1.4, "pose": "panic", "ease": "overshoot" }
]
```

A key may also carry its own `at`, which gives the actor a path rather than a
single position — that, or `to`, is what makes a `follow` camera mean anything.

A key that names no `ease` gets **`inout`**. Note that this contradicts
`anim.track`'s own docstring, which promises the house curve `overshoot` to a
key that says nothing: both callers (`shots.py` and `render.py`) fill in
`inout` before `track` ever sees the key, so the house default is unreachable
from a board. **Name `overshoot` explicitly on any key that should snap** —
relying on the default gets you the mechanical one.

`anim.track` then re-evaluates the head, neck and face `HEAD_LAG` (0.083 s)
in the past, so the head trails the body through the change.

### `props`

| field | meaning |
|---|---|
| `kind` | a key of `sets.PROPS` |
| `at` | anchor position, scene units |
| `scale` | `1.0` is the design size |
| `anim` | one of the names that prop answers to — see [`rig.md`](rig.md) |
| `phase` | starting phase, `0..1` |
| `rate` | cycles per second for `anim`. Only read when `anim` is set |
| `z` | `0..1` depth |
| `layer` | `back`/`far`/`behind` or `front`/`near`/`fore` — settles draw order outright |
| `shadow` | `false` to suppress the contact ellipse |

The fifteen props are `car` `policecar` `milkfloat` `helicopter` `cone` `bin`
`hydrant` `lamppost` `trafficlight` `tree` `building` `sign` `cloud`
`sandwich` `indicator`.

A **beat plan** may set `anim` (and `rate`) on a prop asset and `compile.py`
passes them straight through, checked against `sets.PROP_ANIMS`; an unknown
state is reported as a placeholder rather than dropped in silence. This is how
a beat asks for `{"kind": "prop", "hint": "trafficlight", "anim": "red"}`
without knowing anything about how the lamp is drawn.

**`at` does not mean the same thing for every prop**, and `sets.PROP_ANCHOR`
says which:

| anchor | props | `at` is |
|---|---|---|
| `ground` | `cone` `bin` `hydrant` `lamppost` `trafficlight` `tree` `building` `sign` | where it touches the floor |
| `vehicle` | `car` `policecar` `milkfloat` | the body centre; the wheels are below it |
| `air` | `helicopter` `cloud` `sandwich` `indicator` | nothing — and it gets no contact shadow |

`air` is doing double duty in that last row, and it is worth understanding why.
A helicopter and a cloud are airborne. A sandwich and an indicator are not —
they are *attached to something else*, a hand and a car, and the thing they are
attached to already casts the shadow. Giving either its own ellipse would put a
second shadow on the road under a sandwich being eaten at head height, which is
the sort of error that is invisible in a still and unmissable in motion.

`sets.prop_bbox(kind, scale)` returns the box, so a caller can lay out from
the same numbers the renderer draws from.

Draw order is back to front: set, far props, actors sorted far to near, near
props, overlay. A prop counts as *far* if its `layer` says so, or if its `z` is
above `0.55`; **a prop with no depth at all sits in front**, because the common
foreground prop — a car, a desk, a parapet — is the one an actor is meant to be
tucked behind.

### `sfx`

A list of bare strings, or objects:

```jsonc
"sfx": [
  "radio_squelch",
  { "kind": "siren", "at": 0.0, "dur": 3.0, "gain": 0.7 },
  { "kind": "bell",  "at": "l4+0.2" }
]
```

| field | meaning |
|---|---|
| `kind` | a name or alias from `audio.SFX` |
| `at` | a **number** is shot-local seconds; a **string** is the film clock, in the same grammar as `at` above. Defaults to `0.0`, the cut |
| `dur` | seconds. Each effect has its own sensible default |
| `gain` | level, `1.0` by default |

Anything else in the object is passed to the synthesiser — `sfx_siren` takes
`doppler`, `hi` and `lo`, `sfx_horn` takes `freq`, and so on.

### `overlay`

The chopper's furniture, and the only place text appears. One per shot.

| `kind` | fields |
|---|---|
| `chyron` | `text`, optional `kicker` |
| `title` | `text`, optional `sub` |
| `map` | `route`, optional `label` and `marker` (`[x, y]`, fractions of the plate) |
| `circle` | `target` (an actor or prop id), optional `label` — the news-feed ring |
| `split` | `left`, `right` (two set names) |
| `counter` | `from`, `to`, optional `label`, `unit`, `decimals`, `hold`, `ease` |

An unknown `kind` becomes a labelled placeholder across the lower third
rather than being quietly dropped.

### Where the overlays come from

You rarely write an `overlay` by hand, because `compile.py` derives one from
the beat's `intent`. `compile.INTENT` is the whole mapping, and it is worth
reading before arguing with a compiled board:

| `intent` | `move` | framing | overlay |
|---|---|---|---|
| `establish` | `track` | wide | — |
| `locate` | `pull` | wide | `map` |
| `compare` | `none` | wide | `split` |
| `transition` | `whip` | wide | — |
| `reveal` | `push` | mid | — |
| `list` | `none` | mid | `counter` |
| `annotate` | `none` | mid | `circle` |
| `evidence` | `push` | close | `chyron` |
| `portrait` | `push` | close | — |
| `emphasise` | `push` | close | — |

`compile.FRAMING_ZOOM` turns the middle column into a number: `wide 1.00`,
`mid 1.22`, `close 1.55`. Note the shape of the table — the wide intents move
laterally or not at all, and every close intent pushes. That is not a
coincidence: pushing in on a wide establishing shot throws away the
establishing, and tracking across a close-up loses the face, which is the only
thing a close-up is for.

---

## Times

Identical to the beat plan, deliberately, so a director reading both is never
switching grammar:

| form | means |
|---|---|
| `"l3"` | when line `l3` starts |
| `"l3+0.4"` | 0.4 s after it starts |
| `"l3-0.15"` | 0.15 s *before* it starts |
| `"l3.end"` | when it finishes |
| `"l3.start"` | when it starts — the explicit spelling of `"l3"` |
| `12.5` | absolute seconds — the only option in a wordless film |

The offset is split off at the **rightmost** `+` or `-` followed by nothing but
a number, so a line id may itself contain a hyphen. An id that matches exactly
wins before anything is split off it. An unresolvable reference is a
`TimeError` naming every line the board does have.

---

## What the renderer guarantees

1. **Determinism.** The same board and seed produce a byte-identical file, at
   any `-j`. Segment boundaries come from the running time and the frame rate,
   never from the worker count. `--self-test` proves it.
2. **It never invents a picture.** A `set`, `cast`, `action`, `prop` or
   `overlay` it does not have is drawn as a labelled placeholder and reported
   once, in board order, from the parent process; `compile.py` exits non-zero
   rather than substituting a lookalike.
3. **Finished renders are never overwritten.** An existing `output.path` becomes
   `name-002.mp4`. Pass `--force` to replace one.
4. **It publishes its own clock.** Every film render writes
   `<output-stem>.timeline.json` beside the video: the resolved line times,
   every shot's start, end, tier, `on`, set, impacts and camera move, the
   parallax table and the pacing report.

---

## `render.py`

```bash
python3 scripts/render.py sb.json --sheet        # 20 frames on one JPG — always first
python3 scripts/render.py sb.json --frame 12.4   # one PNG
python3 scripts/render.py sb.json --clip 20 28   # silent range at full res
python3 scripts/render.py sb.json --preview      # half-res, written as *_preview.mp4
python3 scripts/render.py sb.json --audio-only   # remux a new mix
python3 scripts/render.py sb.json --motion 24    # estimate mean frame difference
python3 scripts/render.py sb.json --self-test    # -j 1 vs -j 4, by SHA-256
python3 scripts/render.py sb.json -j 0           # the film
```

| flag | does |
|---|---|
| `-o`, `--out` | output path. Defaults to `output.path`, resolved beside the board |
| `--preview` | half resolution, alongside as `*_preview.mp4` |
| `--frame T` | one PNG at time `T`, written as `*_tT.png` |
| `--sheet` | 20 frames evenly sampled across the film, as one JPG — `5×4` landscape, `4×5` for a Short |
| `--clip START END` | that range only, silent, at full resolution |
| `--audio-only` | rebuild the mix and remux it, copying the frames |
| `--motion N` | mean frame difference from `N` sampled frame pairs, with a 95% CI |
| `-j`, `--jobs N` | render on `N` processes. `0` picks for this machine |
| `--force` | overwrite an existing video |
| `--self-test` | render a short window at `-j 1` and `-j 4` and compare SHA-256 |
| `--self-test-seconds S` | how much of the film that window covers |

**Always look at the contact sheet before rendering.** It costs seconds, and it
catches the two failures a single frame cannot show: a character drifting out of
frame across a shot, and two actors occupying the same scene position. The sheet
samples evenly across the film rather than once per shot, for exactly that
reason — a drift is invisible in any one frame of the shot it happens in.
