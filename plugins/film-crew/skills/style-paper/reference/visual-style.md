# Visual style

Reverse-engineered from a 30-second reference cut of the archival-documentary
style, then codified. Every number here came out of measuring the reference,
not from taste.

---

## 1. The structural rule: there are no cuts

Scene-cut detection was run over the reference at thresholds from 0.20 all the
way down to 0.03. **It found zero cuts at every threshold.**

That is the whole style in one fact. The video is a single continuous shot of a
paper board. Nothing ever replaces the frame. Instead:

- elements **arrive** on the board and stay,
- the camera **slowly pushes in and drifts**,
- red annotation **draws itself on** over what is already there.

Everything else in this document follows from that. When a beat needs to land,
you add a chip or draw a line — you never cut away.

### Beat cadence

Frame-difference analysis at 1 fps put major visual events at roughly
t = 3, 6, 7, 9, 12, 15, 19, 24, 29 s.

> **One visual beat every 2–4 seconds. About 9–10 beats per 30 seconds.**

Slower than that and it reads as a slideshow. Faster and the collage turns to
mush, because nothing ever leaves.

---

## 2. Palette

Sampled directly off reference frames.

| Role | Hex | Use |
|---|---|---|
| Accent red | `#d0442d` → `#c03423` | **annotation only** |
| Parchment light | `#d3d3ad`, `#dacba2` | paper highs |
| Parchment mid | `#bcb692` | body of the sheet |
| Parchment deep | `#b1a17f` | edges, vignette, stains |
| Warm ink | `#3a3a30` | type, silhouettes |
| Sticker white | `#eee8d2` | photo cut-out borders |
| Stamp ground | `#343228` | dark stamp blocks |

Two rules govern colour:

1. **One accent, one job.** Red appears *only* as hand annotation — boxes,
   circles, routes, arrows, underlines. If red shows up in artwork, the
   annotation stops reading as annotation and the whole device collapses.
2. **Everything else is desaturated warm.** Aim for a chroma range narrow
   enough that the board could pass for a scan of real paper.

In a storyboard:

```json
"style": {
  "accent": "#c8402a",
  "paper_light": [216, 208, 178],
  "paper_deep":  [168, 158, 132]
}
```

---

## 3. Materials

The ground is never flat colour. It is built in layers, all procedural:

| Layer | Function | Where |
|---|---|---|
| Fibre noise | paper tooth | `paper.parchment` |
| Value-noise blotches | age, damp, uneven bleach | `paper.parchment(blotches=…)` |
| Ghost print | faint rows of unreadable type | `paper.ghost_print` |
| Map / grid underlay | the "research" signal | `paper.map_fragment`, `paper.grid_fragment` |
| Coffee rings | handled, lived-with | `paper.coffee_ring` |
| Grain | film / scan noise | `paper.add_grain` |
| Vignette | focuses the eye, ages the edges | `paper.vignette` |

### Torn edges

Real torn paper has an **irregular contour but square corners** — the sheet was
cut, then torn. `paper.torn_mask` implements this: the four corner points are
fixed, and the wobble along each edge is tapered by `sin(πu)^0.55` so it decays
to zero at both ends.

> Getting this wrong is the single most common way the look fails. An untapered
> contour notches the corners into white spikes and the "paper" instantly reads
> as a badly masked PNG.

#### The torn core — paper has *thickness*

Look closely at any torn card in the reference and the tear is edged with a
**pale, fibrous lip**: the pulp inside the sheet, which is lighter and warmer
than the printed surface. On dark stock this is the loudest cue in the whole
frame, and without it a torn card reads as a shape with a wobbly outline rather
than as paper.

`paper.torn_core` draws it by eroding the mask and filling the difference:

```python
pulp = 0.82 * (252, 248, 236) + 0.18 * surface
```

The blend is **deliberately near-independent of the surface colour**. Deriving
the pulp from the surface instead (e.g. `surface * 1.16 + 26`) makes the core
grey on dark stock and the effect disappears exactly where it matters most.

Thickness scales with the scrap, so a small chip and a full sheet both read
correctly. Override with `core` when a chip needs a heavier deckle.

### Depth

Depth is driven by one authored number per element, `elevation`, from which
`paper.elevated_shadow` derives offset, blur *and* opacity together. A scrap at
`0.5` casts a large soft shadow; one at `0.1` casts a tight dark one. Because
all three move together the result stays physically consistent, and a stack of
scraps at different elevations reads instantly as a stack.

Light comes from **up and to the left** (`paper.LIGHT_ANGLE = 62°`), so shadows
fall down-right. Every element on the board obeys it — a single contradicting
shadow is very visible.

Three more cues complete the material:

- **`paper.edge_light`** puts a highlight on the cut edge of the stock. Apply it
  to the *paper margin only*, never to the artwork sitting on it — lighting the
  whole silhouette bleaches thin line art (a red marker stroke turns cream).
- **`paper.fold_crease`** darkens one side of a wandering line and lifts the
  other. Keep it narrow; a wide falloff stops being a fold and becomes a
  gradient across the frame.
- **`paper.paper_stack`** offsets two or three sheets behind an element, each
  with its own shadow, for a pile of documents.

Photo cut-outs additionally get a white sticker border (`collage.sticker`,
border ≈ 9 px) — the instant-print / scrapbook cue.

Shadows are expensive, so `render.py` quantises `elevation` to 1/24 steps and
caches the result. The shadow canvas uses a **fixed** pad, so the element's
centre never shifts as its elevation animates.

---

## 4. Typography

Three voices, no more.

| Voice | Font | Job |
|---|---|---|
| **Display** | Archivo (variable `wdth`,`wght`) at ~900 weight, ~74 width | keyword chips |
| **Stamp** | Oswald | dark angled stamp blocks |
| **Typewriter** | Courier Prime / Special Elite | captions, marginalia, credits |

All fonts are OFL/Apache and ship in `fonts/`.

### Rules

- **Chips are uppercase, always.** Heavy, condensed, tracked out ~2 px.
- **Chips are short.** One to three words. A chip is a label, not a sentence —
  if it needs a fourth word, it belongs in the narration instead.
- **Type is never clean.** `collage._ink_texture` erodes the letterforms so they
  look printed on absorbent stock rather than composited.
- **Typewriter type is small and quiet.** It is texture and credit, never the
  message.

### Chips are pasted, not typed

A chip is a *card*: paper rectangle, ink texture, slight rotation (±1–3°), drop
shadow, sometimes torn edges. It arrives with a `stamp` entrance — overshoot
then settle — because it is being physically slapped down.

---

## 5. Layout grammar

Author in design space, 1920×1080. **`at` is the element centre, not its
top-left.** This is deliberate: shadow and sticker padding grow symmetrically,
so centre-anchoring means padding never shifts your layout.

The board itself is rendered `OVER = 1.12` larger than the output so the camera
always has room to move.

### Slots, and how big a picture should be

The compiler lays every beat inside its own **slot** — a box, not a point, so a
beat's picture and its chips can never stray into a neighbour's. The board is
currently two large side-by-side slots, and a picture is on screen for one
further slot turn after its own.

The count is a real design decision, not an implementation detail. A four-box
2×2 grid was tried first and is what produced the commonest complaint about
this style — *"the same static visuals over and over"* — because four boxes on
a 1920-wide frame make every drawing about a sixth of the frame, and a frame of
small stamps on a large empty field reads as one texture no matter how often
the stamps change. Halving the number of slots roughly doubles every picture.

Two rules follow from that, and both were bugs before they were rules:

- **A beat that draws nothing must not take a slot.** If it does, it evicts the
  previous picture and leaves a hole, so a run of quiet beats blanks the board.
  Slots cycle over the beats that *draw*; an empty beat holds what is up.
- **Size the picture by its box, not by its longest side.** See `fit` in
  [storyboard-reference.md](storyboard-reference.md#art--procedural-illustration).
  `size` alone leaves a wide drawing using a third of the height it was given.

### Composition

- **Give the accent somewhere to go.** Red annotation needs clear parchment
  around it. Crowding it against artwork kills it.
- **Chips sit off the subject**, not on it — beside, above, or in dead space.
- **Watch drifting elements.** An element that moves will cross the space where
  you parked a chip. Check the contact sheet, not a single frame.
- **Weight the frame asymmetrically.** Subject on one side, annotation on the
  other. A centred board looks like a slide.

### Layering (`z`)

```
 0  background board, ghost print, rings, map underlay
 1  atmosphere (snow, dust)
 2  distant artwork (moon, stars)
 3  terrain
10  subject artwork
20  chips, stamps, labels
22  red marker annotation      ← always on top
25  typewriter captions
```

Red annotation sits **above everything**, including photos. That is how real
annotation works: someone drew on the print after it was pinned up.

---

## 6. Motion

### Camera

The camera is the largest single source of movement on screen — larger than any
element animation. It works in two layers.

**Authored travel.** A list of `moves`, one per beat, each centring the frame on
a point at a given magnification:

```json
"camera": {
  "zoom": 0.03, "drift": 0.020, "hold": 0.62,
  "moves": [
    { "t": 0.0,       "at": [985, 505], "zoom": 1.10 },
    { "t": "l1+0.10", "at": [720, 390], "zoom": 1.28 },
    { "t": "l1+1.30", "at": [1020, 520], "zoom": 1.12 }
  ]
}
```

Between two moves the camera eases in *and out*, and `hold` parks it on arrival.
That settle-then-travel rhythm is what makes the move read as a decision. A
camera that slides continuously — a single slow push across the whole piece —
measures as movement but feels static, because nothing ever changes.

**Every move needs a motive.** Travel to *greet* something new — a scrap
arriving, a highlight moving, a line being drawn — then stop. A move across
content the viewer has already been looking at has no motivation, and reads as
restlessness rather than intent. Where the narration dwells, hold the frame and
let the artwork itself `sway`.

**Cap the speed, and cap the *peak*.** Keep travel under roughly **0.35 screen
widths per second** at its fastest instant. The easing is cubic, whose midpoint
velocity is **three times** its own average, so a move budgeted on average
speed runs three times too fast exactly in the middle — which is where the eye
reads a lurch. A move that cannot fit at a walking pace should be dropped, not
hurried; see [`troubleshooting.md`](troubleshooting.md#the-picture-jumps).

**Hand-held overlay.** `zoom` and `drift` add a slow sine wander on top, at 25 %
weight when `moves` are present. It exists so the frame is never mathematically
still.

Elements react to the travel in proportion to `parallax`, which defaults from
`z`. Near layers slide further than far ones, and the board gains real depth
whenever the camera moves.

> **Calibration.** Mean frame-to-frame luma difference (320×180, greyscale) is a
> good proxy for how busy a piece is. The reference measures **≈ 2.5** with peaks
> near 29 — it rests, then moves decisively. A single slow push measures ≈ 0.9,
> which is far too quiet. Aim for 2.4–3.0 with peaks above 15.
>
> ```bash
> ffmpeg -v error -i out.mp4 -vf \
>   "scale=320:180,format=gray,tblend=all_mode=difference,signalstats,\
> metadata=print:key=lavfi.signalstats.YAVG:file=-" -an -f null /dev/null \
>   | awk -F= '/YAVG/{s+=$2;n++} END{print s/n}'
> ```

Keep `zoom` between 1.10 and 1.32. The board is rendered `OVER`× larger than the
output (1.34) purely to give the camera room; ask for more and it clamps.

### Entrances

| Entrance | Motion | Use for |
|---|---|---|
| `stamp` | scale overshoot → settle, slight rotation | chips, stamps — anything "slapped down" |
| `pin` | drop in with a small bounce | pinned scraps, stars |
| `slide` | translate in from `from_x` / `from_y` | terrain, characters entering |
| `fly` | sails in from off-frame while lifted, shadow tightening as it lands | subjects, chips, tape — the signature move |
| `fade` | opacity only | atmosphere, glow, anything ambient |

`fly` is the one that sells the material. The scrap arrives at an elevation of
`height`× its resting value, so its cast shadow is large and soft in flight and
contracts as it settles — the shadow does the work, not the translation. Add a
few degrees of `spin` so it rotates out of the throw.

Entrances run **0.45–0.85 s**. Longer feels sluggish against a 2–4 s beat.

### Nothing is ever still

Give every scrap a small `float`: a seeded, slow wander of a pixel or two and a
fraction of a degree, unique per element. It is invisible when you look for it
and unmistakable when it is missing — without it the board reads as a slideshow
of static PNGs between animations.

Pinned and drawn things (`pin`, `marker_*`, coffee rings) get `float: 0`. They
are attached to the board.

### Red annotation draws on

Marker strokes are never revealed by fading — they **draw**, progressively along
the path, over 0.65–1.4 s. Longer paths take longer, exactly as a hand would.

Implementation notes that matter to the look: strokes render at 2× and
downsample (soft felt-tip edges), get value-noise breakup (ink starvation), and
freehand paths are Catmull-Rom smoothed so they curve like a wrist rather than
a polyline. Geometric shapes (`marker_rect`, `marker_ellipse`) skip smoothing —
a drawn rectangle should have corners.

### Exits

Most elements **never leave**. Only exit a chip when it would collide with a
later beat, and then fade it over ~0.45 s. The accumulating board *is* the
style; clearing it wastes the effect.

---

## 7. Finishing

Applied after the camera, at output resolution:

- **Grain** — a pool of 16 pre-generated noise fields cycled per frame. A single
  static field reads as a dirty lens; cycling reads as film.
- **Vignette** — ~0.36–0.5 strength.

### Encoding

```
1920×1080 · 30 fps · h264 High · yuv420p · bt709
CRF 20 with -maxrate 20M -bufsize 40M
AAC-LC 192 kbps 48 kHz stereo
```

**Cap the bitrate.** Per-frame grain is incompressible, so CRF alone happily
produces 90 Mbps. The reference sits near 19 Mbps; 20M is the right ceiling.
