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

### `shake`

Each entry is a jolt added on top of the authored path:

| Field | Meaning |
|---|---|
| `t` | start, same reference syntax as `moves` |
| `amp` | peak offset in design units — `12`–`20` is a jolt, `>30` is slapstick |
| `dur` | total length; the envelope is forced to exactly zero here |
| `freq` | oscillations per second (default `10`) |
| `decay` | exponential decay constant (default `3`) |

x and y run at different frequencies and phases, so it never reads as a
straight-line vibration. Reserve it for a physical event the narration actually
describes — an explosion, an impact. On sensitive material do **not** shake to
punctuate a death; that is dramatising something the house style requires you
to report plainly.

Rules of thumb:

- One move per beat, roughly every 1.5–2.5 s.
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

## `music` / `mix`

See [audio-style.md](audio-style.md).

The bed is synthesised from `music.mood` by default. Setting `music.file`
instead points at an audio file — relative paths resolve against the storyboard
— which is peak-normalised, crossfade-looped to the exact runtime, and used in
place of the synthesiser. See
[audio-style.md](audio-style.md#supplying-your-own-track-instead).

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
| `sfx` | — | cue name (`paper`, `stamp`, `pin`, `draw`, `whoosh`, `chime`) |
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

### `sway`

```json
"sway": { "x": 22, "y": 12, "scale": 0.028, "period": 10.5, "ramp": 1.3 }
```

An endless slow loop, phased from the element's own entrance so it starts at
zero offset and never pops. Use it on a **picture that stays on screen while a
long line is read**: `drift` arrives somewhere and then stops dead, so a
long-held image becomes a frozen photograph, which is what makes a film feel
like a slideshow. Sway never arrives anywhere.

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
| `map` | `w`, `h`, `markers` (list of `[x, y]` in 0–1 image fractions), `highlight` (index, `-1` for none) |
| `timeline` | `w`, `h`, `ticks` (list of `[y_frac, major]`), `progress` (0–1) — a **vertical** spine |
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

The map tile draws its own letterspaced geography — `ARABIAN SEA`, `BACK BAY`,
`HARBOUR`, `COLABA` — placed in open water and on the wide part of the land,
and dropped automatically wherever a pin would collide. Without them the
coastline is an abstract grey shape and viewers report that it "doesn't look
like the city"; with them it is unmistakable. Pin labels are still the
caller's job, and belong *beside their pin*, not in a caption at the foot of
the tile where nothing connects the two.

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
