# Storyboard reference

A storyboard is one JSON file. It fully determines the video: same file plus
same seed always yields the same output.

```jsonc
{
  "title":     "...",
  "output":    { ... },
  "style":     { ... },
  "camera":    { ... },
  "voice":     { ... },
  "timing":    { ... },
  "music":     { ... },
  "mix":       { ... },
  "narration": [ ... ],
  "elements":  [ ... ],
  "sfx":       [ ... ]
}
```

---

## Coordinates and time

**Design space is the output resolution** (1920×1080 by default). Author every
position and size in those units regardless of what you finally render at —
`--preview` rescales everything for you.

> **`at` is the element CENTRE.** Not the top-left. Shadows and sticker borders
> pad symmetrically, so centre-anchoring makes padding irrelevant to layout.

### Time references

Anywhere a time is accepted you may write:

| Form | Meaning |
|---|---|
| `2.4` | absolute seconds |
| `"l3"` | when narration line `l3` starts |
| `"l3+0.4"` | 0.4 s after `l3` starts |
| `"l3-0.15"` | 0.15 s before `l3` starts |
| `"l3.end"` | when `l3` finishes |
| `"l3.end+0.2"` | 0.2 s after `l3` finishes |

Prefer line-relative times for everything that carries meaning. Reserve absolute
seconds for the lead-in and the tail.

---

## `output`

```json
{ "width": 1920, "height": 1080, "fps": 30,
  "crf": 20, "preset": "medium",
  "maxrate": "20M", "bufsize": "40M",
  "path": "out.mp4" }
```

`path` is resolved relative to the storyboard file. Keep `maxrate` — see
[visual-style.md](visual-style.md#encoding).

## `style`

```json
{ "seed": 19,
  "accent": "#c8402a",
  "paper_light": [216, 208, 178],
  "paper_deep":  [168, 158, 132],
  "blotches": 8,
  "ghost_print": true,  "ghost_alpha": 22,
  "map_underlay": true, "map_alpha": 20,
  "vignette": 0.36,
  "grain": 6 }
```

`seed` drives every random decision. Change it to reshuffle the paper without
touching the layout.

## `camera`

```json
{
  "zoom": 0.03,
  "drift": 0.020,
  "hold": 0.62,
  "moves": [
    { "t": 0.0,       "at": [985, 505], "zoom": 1.10 },
    { "t": "l1+0.10", "at": [720, 390], "zoom": 1.28 },
    { "t": "l2+0.30", "at": [520, 690], "zoom": 1.24, "hold": 0.9 },
    { "t": "l3+0.05", "at": [1280, 400], "zoom": 1.18, "cut": true }
  ],
  "shake": [
    { "t": "l9+0.20", "amp": 16, "dur": 0.9, "freq": 9, "decay": 4 }
  ]
}
```

| Field | Meaning |
|---|---|
| `zoom` | fractional push-in across the whole piece, applied *on top of* `moves` |
| `drift` | amplitude of the slow sine wander — the hand-held feel |
| `moves` | authored camera path. **This is what creates most of the movement.** |
| `hold` | seconds the camera parks on each move before travelling on |
| `shake` | optional list of deliberate jolts, additive on top of the path |

Each move centres the frame on `at` (design-space coordinates, same as
elements) at `zoom`× magnification. Between two moves the camera eases in and
out; `hold` inserts a rest at the arrival point, so the camera *settles on a
beat and then travels*, rather than sliding continuously. That settle-then-move
rhythm is the single biggest reason the reference feels alive.

`hold` may be set globally on `camera` and overridden per move.

### Aim at the subject, and lean hard

The camera aims at the beat's **ranked subject** — the thing the shot is about —
not at a layout slot. This is easy to regress and expensive when it does, so it
is worth knowing how the regression looked.

A film made before the scene grammar arrived measured a camera x-range of 789px,
a y-range of 430px and zoom 1.12–1.22. A film made after it measured x-range
384px, **y-range 20px** and zoom pinned at 1.00 — the same number of moves per
minute, so cadence was intact and only *amplitude* had collapsed. Five separate
causes had stacked up, each individually plausible and none individually
sufficient:

1. `SLOTS` had been collapsed from a 2×2 quadrant grid to two full-height
   half-frames. Two half-frames share one vertical centre, so every beat asked
   the camera to look at the same height.
2. The lean was hardcoded low, on the argument that translation is what crops a
   word off the edge.
3. **The camera aimed at `slot.art()` while the scene grammar staged across the
   whole frame and ignored the slot entirely** — so the lens was pointed at a
   rectangle nothing was drawn in.
4. `_TIER_CAMERA` in `apply_motion_plan` *overrode* the lean, and
   `--motion-plan` is always passed, so the tier table was what actually
   shipped.
5. `_zoom_headroom` counted the deliberately-oversized landscape (`GROUND_W`
   is 1.12 — a setting is drawn wider than the frame *on purpose*, so the frame
   is a window onto a place) as something that had to stay framed. That is
   unframeable: `(W/2)/dx ≈ 0.89`, floored to 1.0. Every beat that stood
   someone in a place was therefore pinned at zoom 1.0 with no room to pan.

The fixes that matter, in order of leverage:

- **`readable=True`** on `_beat_bbox` skips anything ≥ `0.85 × W` wide, so
  scenery stops pinning the lens. Both `_zoom_headroom` and `_frame_camera`
  pass it.
- **Lean hard, then clamp.** `_frame_camera` pulls the aim back until the beat
  is framed, and only ever *reduces* a lean. That is why `CAM_LEAN` can be 0.62
  where the old comment argued for 0.18: the answer to "a big move might crop a
  caption" is to measure and correct it, not to refuse to move.
  `motion.apply_camera` additionally clamps the crop inside the board, so
  overshoot degrades to parking at the edge rather than showing blank paper.
- **Vary the horizon per scene** (`staging.horizon_for`) instead of restoring
  the quadrant slots. The scene grammar needs the full frame to stage in, so
  moving the *ground line* between acts is what puts the vertical variation
  back without taking the stage away.

Measured after: x-range 999, y-range 143, zoom 1.00–1.33.

### Calm is a distribution, not an average

Having fixed a dead camera it is easy to overshoot into a shaky one, and the
second failure is reported as *"a bunch of unnecessary camera shakes"* even when
the board carries only one real `shake` event.

What produces that impression is the **shape** of the move distribution. The
reference film's jumps have a median of 57px, a mean of 182px and a maximum of
725px — heavily skewed, so it is mostly tiny adjustments punctuated by rare real
travel. An over-corrected board measured a *median* of 209px with a smaller
maximum: uniform mid-size movement on every shot, with no rest and no
punctuation. A viewer reads that constant churn as shaking.

So the budget has to be spent unevenly:

- `_TIER_CAMERA["limited"]` is the commonest tier and must stay genuinely
  small. Raising it is what moves the median, and the median is the thing that
  reads as calm or not.
- `full` and `sakuga` are rare by construction, so they can be loud.
- `CAM_LEAN` does **not** set the median — `apply_motion_plan` overrides every
  move it recognises with the tier table. `CAM_LEAN` governs the moves the plan
  does not claim: act boundaries, scene pans, follow moves. It is what moves the
  *mean*.

Genuine `shake` is reserved for the `impact` tier — something actually strikes,
falls or detonates. It is never decoration.

Two details the first implementation got wrong, both worth knowing:

- **An impact tier is a frame-budget decision, not a physics one.** The tier
  buys a held drawing whose first frames are a jolt, and the allocator hands it
  to whichever beats carry the most weight — which on one board were *"footsteps
  below her, climbing"* and *"Mira turned around"*. Neither is a collision. The
  hold and the flash still belong to them; the shake does not, and gating it on
  `staging.is_impact()` is what stops the film developing a tic.
- **A beat can own more than one camera move.** A travel beat carries a follow
  move, so keying the shake off the move rather than the beat emitted it twice
  at the same timestamp — two shakes stacked into one double-amplitude jolt.

### Captions outlive their beat

Every beat is pushed as hard as its own composition allows, and the aim is then
pulled back until that beat is inside the frame. Both calculations look only at
the *current* beat — but a chip is deliberately held past its beat so the viewer
can finish reading it. A hard push on a tight beat therefore crops the word off
the beat before it: measured, a 1.29 push aimed left cut "KALVARI" in half while
the lens was busy framing "312 STEPS".

Every caption that is *live at that moment* has to be in the box, not just the
ones belonging to the beat being framed.

### One place, one copy, one time

Two rules that each fix a defect a viewer named directly:

- **Settings do not share a frame.** Act backgrounds are held and their
  lifetimes deliberately overlap so an act change reads as continuous. But two
  *settings* on screen at once do not read as continuity, they read as an
  error — "stairs shown in the water", a hillside standing in the sea. The
  outgoing setting leaves as the incoming one lands.
- **One object, one copy.** A later beat naming the same drawing stamps a
  second copy beside the first — two lanterns, two boats, two figures — which
  a viewer reads as the film repeating its assets. The later copy wins and the
  earlier is retired as it arrives, so the object appears to have *moved*.
  Scope this to *different* beats: two copies of one drawing inside a single
  beat are how depth is staged.

> **`apply_motion_plan` is the real authority on the camera.** It re-aims every
> move it recognises from `mv["_xy"]`, falling back to frame centre when that is
> absent. Any new camera move carrying a `_beat` **must** also carry `_xy`, or
> it is silently converted into a move back to the middle. A follow-move for a
> travelling beat is the usual casualty.

### Cutting instead of panning

A move with `"cut": true` is not travelled to — the camera holds the previous
position and **snaps** to the new one at exactly `t`.

**Prefer not to use it.** The intuition that an eased pan between two distant
clusters "spends its travel over blank paper" is worth testing before you act
on it, because on a normally-composed board it is usually false. Measure the
distances between consecutive scene centres first:

- On a feature-length board built this way, the median inter-scene distance was
  **579 design units against a frame width of ~1613** — roughly a third of a
  screen. Every single transition was affordable as a slow pan.

Cuts also cost you the motion check twice over. `verify.py` measures mean
frame-to-frame difference, and a cut changes everything for *one* frame in
thirty while the other twenty-nine are frozen — so the mean collapses. Measured
on the same film:

| Camera policy | Motion score |
|---|---|
| Continuous orbit | 1.83 |
| Hard cuts + static holds | **1.00** (fails) |
| Eased, motivated pans | 1.77 |

So the honest aesthetic and the metric agree: travel, slowly, and only when
there is something new to travel to. Reserve `cut` for a genuine discontinuity
you *want* the viewer to feel — and remember that viewers reliably report cuts
as "the video jumps".

Two mechanical consequences if you do cut. A cut removes that travel from the
total camera path. And because a cut is instant, any outgoing element must
finish fading **before** it, or it spends its fade sliced by the new frame edge.

### `shake` — removed

**This style no longer shakes, and the field is ignored.** The compiler emits
no `camera.shake`, and the renderer discards the block if a hand-written board
supplies one, printing `· ignoring N camera shake(s)`.

The rule arrived in three steps, which is worth recording because each
intermediate position looked reasonable:

1. Shakes fired on any dramatic beat. Reported as "unnecessary camera shakes".
2. Gated to beats where something physically strikes. Two survived — "footsteps
   below her, climbing" and "Mira turned around" — neither of which is an
   impact, because the classifier was reading *tension*, not physics. A third
   fired twice at one timestamp: travel beats own a second follow move carrying
   the same `_beat`, so the per-beat side effect ran twice.
3. Removed. Reported again as "the camera shake still exists" even at two
   events in a 53-second film.

The lesson is that the threshold was never the problem. In a film made of
still paper, a shake does not read as force — it reads as a rendering fault,
because nothing else in the frame behaves like that. **Where you want impact,
slow down instead**: the compiler now converts what used to be a shake into a
heavier pan — `lean` 0.78, at least 1.6 s long, with a hold of a quarter of its
duration on the end. Weight comes from the size and slowness of a move and from
the silence after it, not from vibration.

### Move the artwork, not the camera

The two rules that most changed how these films feel:

**A beat that draws nothing new gets no camera move.** Compare the live element
names of consecutive beats; if the set is unchanged, the camera has been given
nothing to look at. Moving anyway produces a stream of small mid-size
adjustments with no rest in it, which viewers report as "shaky" even when the
board contains no shake at all. The move is dropped and the previous move's
`hold` absorbs the time.

**What the camera stops on has to keep breathing.** A parked camera over still
artwork is a slideshow. Every drawing on a parked beat gets a `sway` instead —
and scenery is included deliberately, because it is the largest thing in frame
and the one whose stillness is most obvious.

Measured against the reference film: **68 of 282 elements (24%) carry a sway**,
with x amplitudes of 11–26 px, y of 6–14 px, a 2.8% scale pulse, and periods of
8–12 seconds. The compiler scales amplitude by each element's own width
(`SWAY_X = 0.030`, `SWAY_Y = 0.017`), so a hillside drifts further than a
lantern and the parallax between them reads as depth; the period is seeded off
the element id so no two pieces drift in lockstep.

Those numbers are the target because they are the boundary either side of which
it stops working. Slower or smaller and the frame is dead; faster or larger and
the paper looks like it is floating. Eight to twelve seconds is long enough
that a viewer cannot point at the motion but never doubts the film is running.

This is what limited animation actually is. A frame budget is not spent evenly:
it is spent on **one thing moving slowly** while everything else holds, and the
commonest way to waste it is to spend it on the camera.

<details>
<summary>The old <code>shake</code> field, for reading historical boards</summary>

| Field | Meaning |
|---|---|
| `t` | start, same reference syntax as `moves` |
| `amp` | peak offset in design units |
| `dur` | total length; the envelope is forced to exactly zero here |
| `freq` | oscillations per second (default `10`) |
| `decay` | exponential decay constant (default `3`) |

</details>

Rules of thumb:

- One move per beat, roughly every 1.5–2.5 s — **unless the beat draws nothing
  new**, in which case no move at all.
- Keep `zoom` between `1.10` and `1.32`. Below 1.10 the camera runs out of board
  to travel across; above ~1.35 the parchment grain starts to soften.
- Check the contact sheet: any move that crops a **word** is wrong. Cropping a
  picture element is fine and very much in style.

The board is rendered `OVER`× larger than the output (`render.py`, currently
1.34) purely to give the camera somewhere to go. Raising `zoom` past that limit
clamps rather than showing an edge.

## `narration`

One entry per spoken line. **This skill does not generate speech** — each line
points at an audio clip produced by the [`voice-booth`](../../voice-booth/) skill.

```jsonc
"narration": [
  { "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.75 },
  { "id": "l2", "audio": "vo/l2.wav", "gap_after": 0.85 }
]
```

| Key | Meaning |
|---|---|
| `id` | The handle beats refer to — `"l2+0.35"`. Defaults to `l1`, `l2`, … in order |
| `audio` | Path to the clip, relative to the storyboard. Any format ffmpeg reads |
| `duration` | Used **instead of** `audio` to reserve silent time before the narration exists. The renderer warns |
| `gap_after` | Silence after this line, in seconds. This is where documentary pacing lives — 0.4–0.9 s |

Clips are trimmed of leading and trailing silence and measured, and the whole
timeline is derived from those measurements. Change the narration and every
beat follows it; re-run `--sheet` afterwards, because the total runtime moves.

## `timing`

```json
{ "lead_in": 0.9, "tail": 2.8 }
```

Silence before the first line and after the last. The tail is where the final
image is allowed to breathe — do not cut it short.

## `music` / `mix` / `ambience`

See [audio-style.md](audio-style.md).

The bed is synthesised from `music.mood` by default. Setting `music.file`
instead points at an audio file — relative paths resolve against the storyboard
— which is peak-normalised, crossfade-looped to the exact runtime, and used in
place of the synthesiser. See
[audio-style.md](audio-style.md#supplying-your-own-track-instead).

`ambience` is a separate continuous bed under the whole film, chosen from the
story's setting rather than its mood:

```json
"ambience": { "type": "waves", "gain": 0.45 }
```

`type` is one of `wind`, `waves`, `rain`, `fire`, `crowd`, `engine`, `birds`.
It is ducked under narration like the music, at 0.7× the depth — it is texture
rather than melody, so it needs less removal, but leaving it unducked costs
intelligibility for nothing. A per-element `sfx` one-shot of the sound already
running as the bed is suppressed, since it would only make the bed briefly
louder.

## Elements

Common fields on every element:

| Field | Default | Meaning |
|---|---|---|
| `type` | — | see below |
| `at` | — | `[x, y]` **centre** in design space |
| `id` | — | name it so `box_of` can target it |
| `z` | `0` | layer order |
| `rotate` | `0` | degrees |
| `seed` | style seed | per-element randomisation — **must be unique** |
| `static` | `false` | bake into the background (no animation) |
| `in` | — | `{ "t": …, "dur": …, "anim": … }` |
| `out` | — | `{ "t": …, "dur": … }` — fades out |
| `drift` | — | `{ "x": …, "y": …, "from": …, "to": … }` |
| `elevation` | `0.28` | how far the scrap sits off the board — drives its cast shadow |
| `parallax` | `min(0.5, z/46)` | how strongly it reacts to camera travel |
| `float` | `0` | idle drift amplitude; nothing on a real board is perfectly still |
| `shadow` | `true` | set `false` for glows, coffee rings and anything not made of paper |
| `sfx` | — | cue name. Paper foley: `paper`, `stamp`, `pin`, `draw`, `whoosh`, `chime`. Story effects: `wind`, `waves`, `fire`, `steps`, `rain`, `thunder`, `creak`, `birds`, `engine`, `crowd`, `clock`, `heart`, `water`, `bell`, `crack` |
| `sfx_params` | — | per-cue options. `steps` takes `{"surface": "snow"⎪"wood"⎪"stone"⎪"gravel"⎪"grass"⎪"water"}` — the physics genuinely differ, and one footstep for every floor is the most audible tell of a cheap mix |
| `sfx_gain` | `1.0` | 0.4–1.0 |

### Depth: `elevation`, `parallax`, `float`

These three are what stop the collage reading as flat vector art.

`elevation` (0 – 0.6) sets the height of a scrap above the board. It drives the
offset, blur and opacity of its cast shadow together, so one number gives a
physically consistent result. Use it to build a **stack**:

| Layer | `elevation` |
|---|---|
| backing sheet / full-bleed document | `0.10 – 0.16` |
| pinned index card | `0.20 – 0.24` |
| chips, stamps, typed notes | `0.30 – 0.34` |
| the subject of the shot | `0.42 – 0.50` |

Never give two touching layers the same elevation — the whole cue is that the
shadows differ.

`parallax` shifts a layer against the camera move. It defaults from `z`, so
layer order usually does the right thing; override it when a background element
needs to feel far away (`0.04`) or a foreground cut-out very close (`0.34`).

`float` adds a slow, seeded wander of a pixel or two plus a fraction of a
degree. Use `0.3–0.6` on big sheets, `1.2–1.5` on chips and cut-outs, `2.2` on
sparkles, and `0` on anything that is pinned or drawn.

### `in.anim`

`stamp` · `pin` · `slide` (with `from_x` / `from_y`) · `fade` · `fly`

`fly` is the reference's signature entrance: the scrap sails in from off-frame
while **lifted**, so its shadow is large and soft on arrival and tightens as it
settles. Extra fields:

| Field | Default | Meaning |
|---|---|---|
| `from_x` / `from_y` | `0` | where it flies in from, relative to `at` |
| `height` | `1.2` | peak elevation multiplier during the flight |
| `spin` | `0` | degrees of rotation it settles out of |

```json
"in": { "t": "l2+0.15", "dur": 0.85, "anim": "fly",
        "from_x": -430, "from_y": -150, "height": 1.5, "spin": -11 }
```

### `drift`

```json
"drift": { "x": 600, "y": -88, "from": "l4+0.25", "to": "l5+0.6" }
```

Moves the element by `x`,`y` over the window, eased in and out. **Always set
`from` and `to`** — omitting them drifts from the element's entrance to the end
of the video, which is almost never what you mean.

> **`x` and `y` are design units, not fractions.** Like `at` and `fit`, they
> are measured in the 1920×1080 design space and the renderer scales them by
> the output size. A journey across half the frame is `"x": 960`, not
> `"x": 0.5`.
>
> This is worth stating because it has already been got wrong once, and the
> failure is silent: a generator emitted `0.34` meaning *a third of the
> frame*, every journey in every film moved a third of **one pixel**, and the
> check that was supposed to catch it counted how many elements had a `drift`
> key rather than how far any of them travelled. If you are verifying motion,
> assert on the magnitude, not on the presence.

### `sway`

```json
"sway": { "x": 22, "y": 12, "scale": 0.028, "period": 10.5, "ramp": 1.3 }
```

An endless slow loop, phased from the element's own entrance so it starts at
zero offset and never pops. Use it on a **picture that stays on screen while a
long line is read**: `drift` arrives somewhere and then stops dead, so a
long-held image becomes a frozen photograph, which is what makes a film feel
like a slideshow. Sway never arrives anywhere.

`sway` uses the same design-unit convention as `drift`.

| key | meaning |
|-----|---------|
| `x`, `y` | amplitude in design units; the two axes run on different periods so the element traces an open loop rather than sliding along a line |
| `scale` | fractional size breathing — the strongest "this is alive" cue, and the safest, since it grows symmetrically |
| `period` | seconds for the x cycle; vary it per element or a wall of images pulses in unison |
| `ramp` | seconds to fade the sway in after entry |

Two cautions:

- **Never sway one tile of a registered pair.** A `map` and the `thread` drawn
  over it are separate images that must stay aligned to the pixel, and each
  one's phase runs from its *own* entry, so swaying them pulls them apart.
- **Never sway something a `marker_rect` boxes.** The box is computed from the
  target's resting position and will not follow it.

Keep amplitude in the same range as `float` (roughly 10–26). `check_overlap.py`
reasons about resting positions only, so a large sway can walk art under a
caption without any checker noticing.

---

### `chip` — the keyword label

```json
{ "type": "chip", "text": "ONE NIGHT", "at": [620, 330], "size": 104,
  "rotate": -1.6, "torn": false, "z": 20,
  "in": { "t": "l1+0.05", "dur": 0.5, "anim": "stamp" }, "sfx": "stamp" }
```

`weight` (900) · `width` (74) · `tracking` (2.0) · `color` · `bg` · `pad_x` ·
`pad_y` · `torn`.

### `stamp` — dark angled block

```json
{ "type": "stamp", "text": "CLASSIFIED", "at": [1400, 220], "size": 44, "rotate": -6 }
```

### `typed` — typewriter line

```json
{ "type": "typed", "text": "field note  ·  no. 1", "at": [355, 128], "size": 34 }
```

### `card` / `tape` / `pin` / `ring`

Paper furniture. `card` takes `w`, `h`, `depth`, `sides`, `core`, `fold` and
`fold_strength`; `tape` takes `w`,`h`; `pin` and `ring` take `size`. `ring` also
takes `alpha`.

| Field | Default | Meaning |
|---|---|---|
| `depth` | `0.035` | how ragged the torn edge is, as a fraction of the scrap |
| `sides` | `[1,1,1,1]` | which edges are torn (top, right, bottom, left); `0` = clean cut |
| `core` | auto | thickness in px of the exposed pale pulp along the tear |
| `fold` | — | position `0–1` of a vertical crease across the sheet |
| `fold_strength` | `1.0` | `0.4–0.6` on large sheets, `0.8–1.0` on small cards |

A `fold` on a big backing sheet must be **subtle** — at full strength across
1900 px it stops reading as a crease and becomes a shadow band down the frame.

Mark decorative furniture `"static": true` so it bakes into the background.
Anything with a `fold`, `float` or `fly` must **not** be static.

> **Never make text `static`.** A static element is composited into the board
> *before* the draw list runs, so it loses to every drawn element regardless
> of the `z` you give it — it is the one kind of element that can never win a
> z-fight. A baked sources credit on this project was quietly destroyed by
> seven different drawings, and neither the layout nor the overlap checker
> saw it, because overlap checkers habitually skip static decor. Persistent
> credits belong either in a clear lane no art occupies, or — better — in
> their own beat in the tail, where nothing competes with them.

### `art` — procedural illustration

```json
{ "type": "art", "name": "mouse", "at": [300, 830], "size": 300, "facing": 1,
  "sticker": true, "border": 9, "z": 10 }
```

**Sizing.** `size` means *longest side*, so a wide drawing given `size: 400`
comes out 400 wide and only as tall as its own proportions allow. That is why
`fit` exists:

```json
{ "type": "art", "name": "airliner", "at": [520, 300], "fit": [780, 430] }
```

`fit` is a box the drawing is scaled into, keeping its designed proportions and
touching whichever edge it reaches first. Prefer it whenever you know how much
room the picture has — with `size` alone, a wide drawing in a wide slot uses a
fraction of the height it was given, which is what makes a board of pictures
read as a scatter of small stamps.

**Precedence: `w`/`h` → `fit` → `size`.** An explicit `w`/`h` is a deliberate
override and wins. `fit` beats `size`, because the compiler emits both — `size`
only as a fallback for anything that understands nothing else. Getting this
backwards is not a small error: `size` was checked first once, which made `fit`
dead for every illustration scaled by a single `size` parameter (most of the
catalogue), so the entire slot-fitting layer had no effect and each of those
pictures drew at roughly two thirds of the box it had been given. It is
invisible in the storyboard — the JSON carries a correct `fit` that nothing
reads — so it can only be caught by measuring a rendered frame.

| `name` | Params |
|---|---|
| `mouse` | `size`, `facing` (1 / −1) |
| `lantern` | `size`, `glow` (0.0 dark → 1.0 lit) |
| `moon` | `size` |
| `star` | `size` |
| `hill` | `w`, `h` |
| `snow` | `w`, `h`, `count` — *no sticker* |
| `halo` | `size`, `intensity` — *no sticker*, composite **behind** the lit object |
| `hotel` | `w`, `h` — a grand hotel: onion dome on a drum, corner turrets, arcaded facade |
| `boat` | `w`, `h` — small open inflatable, side-on |
| `sea` | `w`, `h` — stacked wave rules, darkest at the bottom |
| `clock` | `size`, `hours`, `minutes` — analogue face, for durations |
| `candle` | `h`, `lit` (0.0 unlit → 1.0 lit) |
| `map` | `region` (see below), `w`, `h`, `markers` (list of `[x, y]` in 0–1 image fractions), `highlight` (index, `-1` for none) |
| `timeline` | `w`, `h`, `ticks` (list of `[y_frac, major]`), `labels` (list of strings, one per tick), `progress` (0–1) — a **vertical** spine |
| `car` | `w`, `h`, `kind`: `sedan` · `police` · `taxi` · `bus` · `ambulance` |
| `figure` | `h`, `kind`: `civilian` · `police` · `commando` · `staff` |
| `crowd` | `w`, `h`, `count` — a rank of figures, fading back with depth |
| `terminus` | `w`, `h` — a grand railway station: clock tower, gothic arcade |
| `cafe` | `w`, `h` — shopfront with awning, pavement tables |
| `hospital` | `w`, `h` — window-grid block with a cross |
| `dinghy` | `w`, `h` — inflatable, side-on |
| `trawler` | `w`, `h` — small fishing boat with wheelhouse and mast |
| `helicopter` | `w`, `h`, `rotor` (0 still → 1 blurred) |
| `smoke` | `w`, `h`, `density` — soft plume, *no sticker* by default |
| `flame` | `w`, `h`, `strength` |
| `phone` | `h`, `kind`: `handset` · `sat` |
| `cctv` | `w`, `h` — body on a wall bracket |
| `airliner` | `w`, `h`, `view`: `side` · `plan`, `stairs` (0 stowed → 1 fully lowered aft airstair) |
| `parachute` | `w`, `h`, `canopy` (0 streamed/unopened → 1 fully open), `figure` |
| `banknotes` | `w`, `h`, `bundles`, `bands` — rubber-banded stacks |
| `necktie` | `w`, `h`, `clip` (`true` for a clip-on's flat bar, `false` for a knot) |
| `note` | `w`, `h`, `lines` — a handwritten slip, scribbled ruled strokes |
| `seat_row` | `w`, `h`, `occupied` (index, or −1) — an airliner row from behind |
| `briefcase` | `w`, `h`, `open` — closed case, or open on its contents |
| `sketch` | `w`, `h` — the police-artist portrait: shaded oval, dark glasses |
| `document` | `w`, `h`, `stamp` — a typed sheet with a rubber stamp |
| `forest` | `w`, `h`, `count` — a stand of conifers on a ground line |
| `cigarette` | `w`, `h`, `smoke` — a lit cigarette with rising curl |
| `glass` | `w`, `h`, `level` — a tumbler filled to `level` (0–1) |
| `radar` | `size`, `sweep` (0–1) — a scope, sweep arm and blips |
| `stairs` | `w`, `h`, `steps` — the aft airstair, lowered |
| `ticket` | `w`, `h` — a stub with a perforation and a punched hole |
| `coin` | `size` — a milled-edge coin |
| `envelope` | `w`, `h`, `open` — a sealed or opened envelope |
| `magnifier` | `size`, `angle` — a lens on a handle |
| `fingerprint` | `size` — a whorl of concentric ridges |

Both aircraft views point the **nose left**. Laid over a west-to-east route an
unmirrored plan view is flying backwards, which every viewer notices and no
one can articulate — flip it at the caller. Use `view: "plan"` on a roughly
square frame: a 727's span is about 0.70 of its length, so on a wide frame the
span collapses and the aircraft reads as a missile.

`sticker: true` (default) adds the white cut-out border and drop shadow.

**Prefer a picture to a caption.** A viewer reads an illustration in a glance
and a sentence in a second and a half, so a scene whose only content is text is
a scene the film is not using. Reserve bare-text frames for the few beats where
emptiness *is* the point — a casualty figure, a list of names.

**`map` beats `chip("COLABA")`.** A place name means nothing to a viewer who
does not know the city; a pin on a coastline they have now seen five times
means everything. Reuse one map with a moving `highlight` rather than a
different picture each time — the repetition is what makes it legible.

**Say which region, or get an unlabelled one.** The map tile draws real
geography from a named region, and the film picks it once: put `region` at the
top level of the beat plan and the compiler stamps it onto every `map` element
and onto `style.region`. The regions that ship are:

| `region` | Draws |
|---|---|
| `mumbai` | South Mumbai / Salsette — `ARABIAN SEA`, `BACK BAY`, `HARBOUR`, `COLABA` |
| `pacific-northwest` | The lower Columbia — `COLUMBIA RIVER`, `LEWIS RIVER`, `PORTLAND`, `VANCOUVER` |
| `generic` | An invented coast with **no place names** — the default |

A plan that names no region gets `generic`, and that is deliberate. An
unlabelled chart reads as a map without claiming to be anywhere; a map that
confidently labels the wrong continent is a factual error the viewer can read
straight off the screen. A film about Washington State once shipped 42 shots
of Mumbai this way. If your story happens somewhere not listed, add a region
to `_REGIONS` in `illustrations.py` rather than letting a wrong one stand —
`island` regions carry a coast ring, `rivers` regions a list of water courses.

Place names are placed in open water and on the wide part of the land, and
dropped automatically wherever a pin would collide. Without them the coastline
is an abstract grey shape and viewers report that it "doesn't look like the
city"; with them it is unmistakable. Pin labels are still the caller's job,
and belong *beside their pin*, not in a caption at the foot of the tile where
nothing connects the two.

**`timeline` beats `chip("21:44")`.** A bare clock time asks the viewer to hold
a number; the spine shows them *where in the night they are*. Advance
`progress` and re-emit it at each time beat, and pin the labels to the exact
tick fractions so they line up.

**Once a scene has art, its captions must be `chip`, not `typed`.** Illustrations
here are large, dark silhouettes, and bare `typed` text is dark grey — a caption
that crosses a smoke plume, a crowd or a building loses its middle words
entirely. A chip carries its own light plate, so it stays readable over
anything. Either make the caption a chip or park the `typed` line where no art
reaches: above the drawing, or outside its horizontal span. An edge-clipping
check will not catch this, because nothing is clipped.

> **New subject matter = a new function in `illustrations.py`** returning an
> RGBA `Image`, plus a branch in `render.make_art`. That is the intended
> extension point.

---

### `marker_path` / `marker_rect` / `marker_ellipse` — the red pen

```json
{ "type": "marker_path", "z": 22, "width": 14, "wobble": 2.2, "seed": 63,
  "points": [[290, 985], [560, 935], [1150, 832]],
  "in": { "t": "l4+0.35", "dur": 1.4 }, "sfx": "draw" }
```

Markers **draw on** over `in.dur`. They have no `at` — geometry is absolute.

| Field | Meaning |
|---|---|
| `points` | path, design space (`marker_path` only) |
| `box` | `[x0, y0, x1, y1]` (rect / ellipse) |
| `box_of` | **id of another element — auto-fits the box to it** |
| `pad_x`, `pad_y` | padding around a `box_of` target |
| `width` | stroke width (14–17) |
| `wobble` | hand tremor (2.0–3.5) |
| `smooth` | Catmull-Rom smoothing; default `true` for paths |

#### Use `box_of`, not `box`

```json
{ "type": "chip", "id": "chip_night", "text": "ONE NIGHT", ... },
{ "type": "marker_rect", "box_of": "chip_night", "pad_x": 34, "pad_y": 24 }
```

Chips are auto-sized from their text, so a hand-written `box` is guesswork that
breaks the moment anyone edits a word. `box_of` measures the real artwork —
including compensating for sticker and shadow padding — and always fits.

---

## Global `sfx`

Cues not tied to an element:

```json
"sfx": [ { "type": "whoosh", "t": 0.15, "gain": 0.5 },
         { "type": "paper", "t": "l3+0.2", "gain": 0.35, "seed": 17 } ]
```

---

## CLI

```bash
python3 render.py sb.json              # full render
python3 render.py sb.json --sheet      # 4x5 contact sheet  (seconds)
python3 render.py sb.json --frame 12.4 # single frame
python3 render.py sb.json --preview    # half-res, fast preset
python3 render.py sb.json --force      # allow overwriting an existing video
```

### Renders are never overwritten

A render costs minutes and cannot be recovered once the storyboard has moved on,
so if `output.path` already exists the renderer writes the next free
`name-002.mp4`, `name-003.mp4`, … and prints which one it chose:

```
note: explainer.mp4 exists -> writing explainer-002.mp4
```

Suffixes do not nest — `name-002.mp4` yields `name-003.mp4`, never
`name-002-002.mp4`. Pass `--force` only when you genuinely want to replace a
file. Stills (`--frame`, `--sheet`) are cheap to regenerate and are still
overwritten in place, so iterating on layout does not litter the directory.
