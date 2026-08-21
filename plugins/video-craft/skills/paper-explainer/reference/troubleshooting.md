# Troubleshooting

Environment traps and look failures, with the fixes. Read this the first time
something is wrong — most of these cost hours to rediscover.

---

## Environment

### `ffmpeg` has no `drawtext`

Many builds — including Homebrew's default — are compiled **without
libfreetype**, so `drawtext` does not exist. Check:

```bash
ffmpeg -hide_banner -filters | grep drawtext
```

**This renderer never uses `drawtext`.** All text goes through Pillow. If you
extend the pipeline, keep it that way — it is also the only way to get variable
fonts, ink texture and torn chips.

Filters that *are* reliably present and used here: `zoompan`, `overlay`,
`rotate`, `gblur`, `xfade`, `noise`, `perspective`, `colorchannelmixer`,
`libx264`, `aac`, `loudnorm`, `ebur128`.

### A downloaded font is not a font

Google Fonts paths differ by licence — Special Elite lives under
`apache/specialelite/`, **not** `ofl/`. A wrong path returns an HTML error page
that saves happily as `.ttf` and fails much later with a confusing error.

**Always verify the magic bytes.** A real TrueType file starts `00010000`:

```bash
xxd -l 4 -p fonts/SpecialElite-Regular.ttf   # expect 00010000
```

If you see `0a0a0a0a` or `3c21444f`, you downloaded HTML.

### Variable fonts

Pillow supports them via `set_variation_by_axes` (FreeType ≥ 2.9). `raqm` is
often unavailable — that only affects complex-script shaping, which this style
does not use.

### Headless Chrome

Not needed here, but noted because it is tempting: headless Chrome hangs
indefinitely on some macOS setups. Nothing in this skill requires a browser.

---

## Rendering

### Output file is enormous (60–100 Mbps)

Per-frame grain is **incompressible**, so CRF alone lets x264 spend without
limit.

**Fix:** cap it. `"maxrate": "20M", "bufsize": "40M"` in `output`. The reference
sits near 19 Mbps.

### Paper corners have white spikes / notches

The torn contour is not anchored at the corners.

**Fix:** lock the four corner points and taper the edge wobble to zero at both
ends (`sin(πu)^0.55`). Already handled in `paper.torn_mask` — but if you write
a new torn shape, replicate it.

### A red marker box doesn't fit its chip

You hand-wrote `box`. Chips are auto-sized from their text, so any hand-written
box is wrong the moment the text changes.

**Fix:** give the chip an `id` and use `box_of`.

```json
{ "type": "chip", "id": "chip_night", "text": "ONE NIGHT", ... },
{ "type": "marker_rect", "box_of": "chip_night", "pad_x": 34, "pad_y": 24 }
```

### A marker circle around artwork is way too big

`box_of` compensates for sticker/shadow padding on `art` elements
automatically. If you are seeing a huge ellipse, the target is probably an
illustration with a lot of transparent margin (the mouse canvas is 1.75× as wide
as it is tall). Reduce `pad_x` — negative values are allowed — or circle a
tighter element.

### A drifting element ends up somewhere unexpected

`drift` with no `from`/`to` runs from the element's entrance to the **end of the
video**, not to the next beat.

**Fix:** always specify the window.

```json
"drift": { "x": 600, "y": -88, "from": "l4+0.25", "to": "l5+0.6" }
```

### A glow appears as a hard-edged disc

`sticker()` outlines whatever you hand it, including a soft halo.

**Fix:** `halo` is a separate `art` name for exactly this reason. Composite it
as its own element **behind** the lit object (lower `z`), never as part of it.

### Freehand red lines look like polygons

Catmull-Rom smoothing is off. `marker_path` defaults to `smooth: true`; if you
set it false, you get straight segments. Geometric shapes (`marker_rect`,
`marker_ellipse`) deliberately keep it off — a drawn rectangle should have
corners.

### An object floats above the ground

The renderer has no physics. Compute the terrain height yourself. For
`hill(w, h)` placed centred at `(cx, cy)`:

```
u       = (x - (cx - w/2)) / w
surface = (cy - h/2) + h - 0.8*h * sin(pi*u)**1.25
```

Then set the object's centre y to `surface - object_height/2`.

### Render is slow

- Use `--sheet` for layout, not full renders. Measured **≈ 17 s** for a 27 s
  piece, including re-synthesising the narration.
- `--preview` halves the resolution and uses a fast preset.
- Mark decorative furniture `"static": true` so it bakes into the background
  once instead of compositing every frame.

Expect a **full 1080p30 render to take several minutes** — a 29.7 s piece
(892 frames) runs about 5–8 minutes on a modern laptop. It is compositing
dozens of layers with shadows and per-frame grain, so this is normal; budget
for it rather than assuming something has hung.

---

## Look

### The picture jumps

The camera teleports between framings instead of travelling. Causes, in order
of how often they are the culprit:

1. **A `cut` key.** Cutting is the honest fix for "the camera wanders", but it
   trades one complaint for a worse one, and it *lowers* the motion score
   rather than raising it (see [`verification.md`](verification.md#what-actually-moves-this-number)).
2. **A move with no room.** If a reframe is scheduled 0.5 s before the next
   key, the camera covers the whole distance in 0.5 s. Time each move by the
   distance it covers, not by a constant, and drop moves that will not fit at
   a walking pace rather than letting them run fast.
3. **Budgeting on average speed.** `camera_path` eases with a cubic, whose
   velocity at the midpoint is **three times** the average. A move planned at
   a comfortable average is three times that fast in its middle, which is
   exactly where the eye reads a lurch. Divide by three.

A useful ceiling: keep peak travel under **~0.35 screen widths per second**
(around 520 design units/s at a typical zoom). Confirm with `--clip A B`, and
read the *shape* of the difference profile — a smooth hump is a pan, an
isolated spike is a jump.

### It reads as a slideshow

Beats are too far apart, or the camera stopped. Check every gap is ≤ 4 s, that
`camera.moves` has roughly one entry per beat, and that elements have a small
`float`. Measure it rather than guessing:

```bash
ffmpeg -v error -i out.mp4 -vf \
  "scale=320:180,format=gray,tblend=all_mode=difference,signalstats,\
metadata=print:key=lavfi.signalstats.YAVG:file=-" -an -f null /dev/null \
  | awk -F= '/YAVG/{s+=$2;n++; if($2>m)m=$2} END{print "mean",s/n,"peak",m}'
```

Below ~1.5 mean is a slideshow. Target 2.4–3.0 with peaks above 15 — the
reference measures 2.55 / 28.7.

**The metric is contrast-sensitive, so only compare like with like.** It reports
luma *difference*, not displacement, so a large near-black cut-out on pale paper
scores several times higher than mid-tone artwork moving at exactly the same
speed. One measured board reads 4.88 mean with a perfectly calm camera: it sits
at 1.5–3.8 for its first seven seconds and roughly doubles the moment a
near-black silhouette lands, with no change at all to `camera.moves`.

So a high reading is not by itself evidence of a problem. Before retuning the
camera, measure the **actual pan velocity**, which is what viewers perceive:

```bash
mkdir -p /tmp/mfr && ffmpeg -v error -ss <peak_time> -i out.mp4 \
  -frames:v 8 -vf scale=480:270,format=gray /tmp/mfr/f%02d.png
python3 - <<'PY'
import numpy as np, glob
from PIL import Image
a = [np.asarray(Image.open(f), np.float32) for f in sorted(glob.glob('/tmp/mfr/*.png'))]
R = 14
for i in range(len(a) - 1):
    c = a[i][R:-R, R:-R]
    best = min(((dx, dy, np.abs(c - a[i+1][R+dy:a[i+1].shape[0]-R+dy,
                                             R+dx:a[i+1].shape[1]-R+dx]).mean())
                for dy in range(-R, R+1) for dx in range(-R, R+1)), key=lambda t: t[2])
    print(f"{i}->{i+1}: dx={best[0]*4:+d} dy={best[1]*4:+d} px/frame")
PY
```

Scaled to 1920, **4–8 px/frame is a smooth cinematic pan**; above ~25 px/frame
is a whip. Retune the camera only if that number is high. The residual left
after alignment is the non-camera motion (float, entrances, grain).

**If you group elements into scenes, check where the scene centres actually
are.** A long piece is easiest to lay out by giving each beat a cluster and
placing item offsets relative to a scene centre — but the centres are then easy
to leave near the middle of the board, because every cluster looks correct on
its own. One twelve-minute board had all thirty-two centres inside a
220 × 190 patch: consecutive moves were 50–120 design units and it measured
**0.84**, a slideshow, despite having 133 camera moves. Respreading the same
centres across x 640–1300 and y 380–690, alternating left/right so each cut
crosses the board, raised the mean jump to ~610 units. Print the distances:

```python
d = [math.dist(c[i], c[i+1]) for i in range(len(c) - 1)]
print(min(d), sum(d) / len(d), max(d))
```

Item offsets are relative to the centre, so moving centres does not invalidate
any placement. Two things do need re-checking afterwards, and both bit:

- **Outgoing clusters get sliced.** If the previous scene's elements start
  their fade-out at the moment the camera *arrives*, they spend the whole fade
  cut in half by the new frame edge. Start the fade so it *ends* on arrival.
- **`camera.zoom` shrinks the late frame.** It adds a slow push across the
  whole runtime, so the final zoom is `scene zoom + camera.zoom`. Raising it
  from 0.02 to 0.05 to buy motion instead pulled 44 captions off the edge in
  the last four minutes — and bought almost nothing, since 0.05 spread over
  twelve minutes is invisible frame to frame. Get motion from travel, not zoom.

#### The metric tracks total distance, not speed

This is the thing to internalise before retuning anything. Mean frame
difference is a *sum over every frame*, so it measures how far the picture
travels across the whole runtime. Bigger jumps between the same number of
beats barely help — the board is only ~900 × 500 design units of legal camera
centre, so travel per move is capped. Two renders of the same twelve-minute
board measured:

| camera path length | mean frame difference |
|---|---|
| 11,469 units | 0.84 |
| 26,698 units | 1.16 |
| 57,462 units | 1.81 |

which fits `motion ≈ 0.60 + 2.1e-5 × path` almost exactly. The intercept is
the board's own texture — grain, `float`, entrances — and everything above it
is camera travel. That model turns a forty-minute render into arithmetic: pick
your target, solve for the path length you need, and score the storyboard
first by walking `camera_path` frame by frame and summing the distance.

**A parked camera is what actually costs you.** `hold` contributes exactly
zero distance, and on a long piece the holds dominate: that board spent 200 s
of its 721 s parked and another 514 s waiting between beats. Concentrating
travel into faster bursts does *not* raise the mean — it moves the same
distance in fewer frames. The fix is to keep moving while waiting. Walking the
camera slowly around a circle inside the scene while it sits on a beat added
31,000 units without widening the framing by a single pixel, because the orbit
radius stays inside the offset budget the layout was already proven against.

Sample the orbit about six keys per turn. Fewer and it degenerates — at two
keys per turn the camera just slides out and back, adding almost nothing — and
`camera_path` eases between every pair of keys, so very dense keys make the
camera stop and start repeatedly. One turn every 5–6 s at a radius of 66–80
units works out to roughly 4 px/frame at 1920, which is the low end of the
smooth-pan band above.

> Related: `camera.drift` will not rescue a long video. Its wander is
> normalised by duration — `sin(t / duration × π × 0.9)` — so it completes
> less than half a cycle no matter how long the piece is. A sixty-second video
> gets that displacement over 1,800 frames; a twelve-minute one spreads the
> same displacement over 21,600 and it disappears into the noise floor.

### The camera moves constantly but the piece still feels static

A single slow push across the whole video technically moves every pixel yet
reads as nothing happening, because the framing never changes. Replace it with
authored `camera.moves` and a `hold`, so the camera settles on a beat and then
travels to the next one.

### The camera pans across blank paper for no reason

The complaint is usually phrased as "it pans when there's nothing on screen",
and it is a real defect rather than a taste question. On a board built out of
scattered scene clusters, an unmotivated move spends its travel over empty
parchment: the frame the viewer is looking at contains no content at all for a
second or more.

**Cutting is the obvious fix and the wrong one.** It removes this complaint and
replaces it with a worse one — "the video jumps" — while also collapsing the
motion check (see [Cutting instead of panning](storyboard-reference.md#cutting-instead-of-panning)).
Fix the *motivation* instead:

1. **Only move to greet new content.** A move should be triggered by something
   arriving — a scrap, a highlight, a line being drawn. If nothing changes,
   the camera does not move. This alone removes almost all of the complaint,
   because the travel now always terminates on something worth looking at.
2. **Time each move by the distance it covers**, at a fixed peak speed, rather
   than giving every move the same duration.
3. **Drop what will not fit.** Reserve the window the next scene change needs;
   if a late move would leave too little room, delete the move rather than
   letting the transition sprint. Fewer, slower moves always beat more, faster
   ones.
4. **Let held images sway** so a parked camera never reads as a frozen frame.

Measure the distances before assuming a pan is unaffordable — on a normally
composed board the median hop between scene centres is around a third of a
frame width, which is a comfortable one-to-two-second travel.

If you *do* keep a deliberate cut somewhere, two traps follow:

- **Cuts do not feed the motion check.** The metric sums how far the picture
  travels over every frame, and a cut is one frame. Re-measure after converting
  any pan to a cut, because you have just deleted most of its travel.
- **An orbit or idle move must be allowed to run right up to the cut.** A
  post-pass that skips the gap before a scene change is correct for pans and
  wrong for cuts: with a cut there is no travel, so that gap is dead air. Gate
  it on the *arriving* key's `cut` flag, and when it is set, keep circling the
  current scene centre instead of steering toward the next one.

### A `name` that exists in `illustrations.py` still raises `unknown art`

The storyboard's `name` is the key in `render.make_art`'s dispatch, which is
not required to match the Python function name and sometimes deliberately
doesn't (`cafe_front()` is dispatched as `"cafe"`). Grep the dispatch, not the
module:

```bash
grep -oE 'name == "[a-z_]+"' render.py
```

It fails at render time, not at build time, so a board can pass every layout
check and still die forty minutes into a render. Render one frame that contains
each new illustration before starting a full pass.

### A caption is unreadable even though nothing is clipped

An edge check answers "is the text inside the frame?" It cannot answer "is the
text legible against what is behind it?", and those are different questions. Two
failures slip past it:

- **Bare `typed` text over dark art.** The word is drawn *on top* — z-order is
  usually fine — but dark grey letters over a smoke plume, a crowd or a building
  silhouette have almost no contrast, so the middle of the sentence dissolves.
  `chip` and `stamp` are immune, because their light plate travels with them.
  That asymmetry is the whole rule: **a caption crossing dark art must be a chip,
  or it must move.**
- **Text over text.** Two elements authored on the same row with different
  lengths will not collide until one of them is long enough. Nothing warns you.

Both are cheap to catch offline: build every element's box the way the renderer
does, then intersect the pairs that share screen time.

```python
e = R.Element(spec, tl, S)
w, h = R.make_base(spec, S, accent, e.seed).size      # the real rendered size
x, y = spec.get("at", [960, 540])
```

Two traps when writing that check. `t_out` is `None` for anything that lives to
the end of its scene, so treat it as `+inf` before comparing. And a *bounding
box* over-reports badly for irregular drawings — a helicopter's box is mostly
empty air, and a chart legitimately contains its own labels — so treat the
output as a shortlist and confirm each hit by rendering that one frame with
`--frame T`. Judge art-over-text by eye; treat text-over-text as a hard failure.

### Fixing the mix should not cost another full render

Audio and video are independent in the output: an equalisation, a music level or
a duck depth changes no pixel. Rebuilding the whole film to move the bed 6 dB
wastes half an hour and risks introducing an unrelated change.

`render.py --audio-only` rebuilds just the mix and remuxes it into the existing
file with `-c:v copy`. On a 12-minute film that is **~90 seconds instead of ~35
minutes**. The storyboard must still resolve to the same duration — regenerate
it first and confirm the element and camera-move counts are unchanged, because
the flag trusts that the frames on disk still match.

### It reads as a corporate explainer

Almost always narration pace, which is set when the voiceover is recorded —
see the [`voiceover`](../../voiceover/) skill. From this side you can still buy
air by widening `gap_after` between lines, which is where documentary pacing
lives anyway.

### The narration is too slow

Do not fix this — or cause it — with the TTS `--rate`. A negative rate slows the
*articulation*: every vowel stretches, and the result is a voice that sounds
sedated rather than measured. It is the single most common reason a piece feels
funereal.

Record at the voice's natural rate and control the pace entirely with
`gap_after`. Speech and silence are then independent, which is what you want:
the sentences stay crisp while the film still breathes where it should.

Two numbers keep it honest. Measure **speech-only** duration after
`trim_silence` (edge-tts pads over a second onto every clip, so raw file
lengths overstate it badly), and treat the `wpm` in the script front-matter as
a *gross* rate covering speech plus silence. A natural delivery around 175 wpm
of actual speech sits near 130 gross once the gaps are in.

Better than hand-tuning each gap: author the gaps as **relative weights** —
quick inside a list, long after a figure or a death — and solve one scale
factor so that

```
speech + Σ gaps + lead_in + tail == target_duration
```

The shape of the rhythm is then a design decision and the absolute length is
arithmetic, so retiming the whole piece is one number instead of a hundred.
Clamp the solved gaps to a floor and ceiling and redistribute the remainder, or
one long pause will swallow the budget.

### The red stops feeling like annotation

Red leaked into artwork. Audit every element: red belongs **only** to
`marker_*`.

### A red marker stroke renders cream instead of red

`edge_light` was applied to the whole silhouette rather than to the paper margin
alone. On a thin stroke every pixel is "edge", so the highlight bleaches it.
Light the border layer *before* compositing the artwork on top.

### The board looks flat / composited

- Missing shadows. Every physical object needs one. Set `elevation` — do not
  rely on `sticker()`'s built-in shadow, which chips and stamps never get.
- All shadows are identical. Vary `elevation` by layer; equal shadows on a stack
  cancel the depth cue entirely.
- No torn core. A torn card needs the pale pulp lip along the tear, otherwise it
  is a wobbly shape rather than paper.
- Grain is static. Cycle a pool of noise fields per frame; one fixed field reads
  as a dirty lens.
- Type is too clean. `collage._ink_texture` should be eroding the letterforms.

### A fold looks like a shadow across the frame

`fold_crease` falloff is too wide for the sheet. On a full-bleed backing sheet
use `fold_strength` around `0.5`; the crease should be a line you notice only
when you look for it.

### Everything greyed out after adding a backing sheet

A large `card` behind the scene replaces the parchment background over most of
the frame, so its colour becomes the palette. Warm it (around
`[226, 213, 176]`), and let it bleed off at least one edge so it reads as a
sheet on the board rather than a border around the video.

### Two elements changed when I edited one

Duplicate `seed` values. Seeds are how elements are identified for
randomisation, and bulk edits keyed on `seed` will hit every match. Keep them
unique across the storyboard.

### The audio sounds thin

Check ducking is on (`duck_db`) and the music bed truly runs edge to edge —
including under the lead-in and tail. Then confirm the master:

```bash
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

Expect I ≈ −14.0 LUFS, true peak ≤ −1 dBFS. If loudness is right but the peak is
hot, `loudnorm`'s linear mode overshot — `audio.master` appends an `alimiter` at
the ceiling for exactly this.

### The narration sounds wrong, robotic, or is missing

Narration is **not produced by this skill**. Anything about voices, providers,
pace or pronunciation belongs to the [`voiceover`](../../voiceover/) skill —
regenerate the clips there and re-run `--sheet`.

What this skill will tell you:

- `narration audio not found: …` — the `audio` path is wrong. It resolves
  relative to the storyboard file, not the working directory.
- `! N line(s) are silent placeholders` — those lines have `duration` instead of
  `audio`. That is a layout aid, never a deliverable.

### The timeline changed after I re-recorded the voiceover

Working as designed. Beats are timed against measured speech, so a new take
moves everything with it. Re-run `--sheet` and check the board still reads;
a longer take can push a chip past the camera move that was framing it.

### The same storyboard renders a different file every time

Fixed, but worth knowing why, because it silently contradicted the
byte-for-byte reproducibility claim in [`SKILL.md`](../SKILL.md) principle 10.

`warm_pad` drew its partial phases from the **global, unseeded** NumPy RNG:

```python
ph = np.random.random(len(partials)) * 2 * np.pi     # ← non-deterministic
```

Every mood uses a pad, so *every* render produced a different music bed — a
different `sha256`, and audibly different phase relationships in the low end.
It is invisible in casual listening, which is exactly why it survived so long.

The fix is a seeded generator (`np.random.default_rng(seed)`), matching what
`celesta` already did with `default_rng(int(freq))`.

**If you add an instrument, never touch `np.random.*` directly.** Take a `seed`
argument and make your own generator. To check, hash the bed twice:

```python
h = [hashlib.sha256(build_music(sb, 20.0, []).tobytes()).hexdigest() for _ in range(2)]
assert h[0] == h[1]
```

All five moods now pass this. Note that `warm` and `tension` legitimately hash
*the same as each other* — `warm` has no branch of its own yet and falls
through to `tension`.

### Comparing two beds' band profiles gives nonsense

Only compare band ratios computed over **equal-length windows with the same FFT
size**. A magnitude-sum ratio taken from a 0.55 s clip against a 20 s bed makes
the wide high bands look enormous, purely because they contain far more bins at
finer resolution — it once made a bed look 2.4× too bright when per-instrument
measurement showed the opposite. Use an averaged fixed-window PSD (4096-pt,
hop 2048) on both sides.

And do not reach for spectral centroid. Across tick settings spanning
band-pass 1650 → 1050 Hz and decay 0.0075 → 0.022 s — parameters that change
the sound completely — the centroid moved 5796 → 5851 Hz. It cannot hear the
difference. Band ratios and L1 distance can.
