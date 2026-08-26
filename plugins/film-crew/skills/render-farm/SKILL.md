---
name: render-farm
description: >
  Renders a film-crew film through Remotion — React and SVG in a headless
  browser — instead of compositing it in PIL. A renderer, not a style: it is
  orthogonal to `style-paper`, `style-flat`, `style-news` and
  `style-2d-animation`, and any of them can be driven through it. Two routes
  are supported and documented: **trace** an existing Python renderer so the
  artwork comes across exactly as authored, or **author natively** in React.
  Measured 5.5× faster in wall clock than the Python renderer on the same
  board, because it is the only path here that saturates the cores it is
  given. Use when a film is slow to iterate on, when you want a scrubbable
  timeline, or when starting a new style from scratch.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Render farm

Every other renderer in this crew is the same shape: Python opens a PIL canvas,
composites layers onto it, and writes frames. This one hands the drawing to a
browser.

That is a **renderer** decision, not a **style** decision, and the two are
worth keeping apart. A style says what the film looks like — palette, line,
staging, timing. A renderer says how those instructions become pixels. This
skill owns the second question only, so it is available to `style-paper`,
`style-flat`, `style-news` and `style-2d-animation` alike, and to any style
added later.

---

## Why it is worth the swap

Measured on one machine, same board, same 2333 frames at 1920×1080:

| renderer | wall clock | user CPU | cores kept busy |
|---|---|---|---|
| Python `render.py -j 4` | 390 s | 453 s | **1.19** |
| Remotion `--concurrency=4` | **72 s** | 269 s | **3.99** |

The interesting column is the last one. `-j 4` kept 1.2 cores busy for six and
a half minutes — on that workload the flag bought almost nothing. The browser's
workers kept 4.0 of the 4 they were given. **The win is parallelism you get
rather than parallelism you fight for**, and it transfers; the absolute times
do not.

Three things that matter more than the number:

- **You can see the frame you are editing.** `npm run studio` is a scrubbable
  timeline with hot reload. The Python loop is edit → re-render → open a file.
- **Time is composable.** `<Sequence from={…}>` re-bases the clock, so a shot
  gets `frame` starting at 0 and animating on twos falls out of one helper
  instead of being arithmetic every component has to remember.
- **Both aspect ratios are the same component.** A 9:16 cut is a second
  `<Composition>` at 1080×1920, not re-authored staging.

And the counterweight, because it decides which of the two routes below you
want: **tracing a style gets you a faster renderer, not a new one.** The
drawings still come out of Python. Only native authoring makes the browser the
place the film is actually made.

---

## The two routes

### 1. Trace an existing style

Use when the style already has a working Python renderer and you want it
faster without changing a pixel.

Nothing is ported. The Python renderer draws through a pen abstraction; swap in
a **recording pen that appends JSON instead of rasterising** and the artwork
comes out exactly as authored — no transcription, so no drift, and any
remaining difference is measurable rather than arguable. React replays the
recording.

The `style-2d-animation` port is the worked example: **mean masked difference
2.3% of range** against the Python render of the same board, about a third of
which is the encoder rather than the drawing.

Full method, including the five ways an assumption gets baked into a trace and
how each was caught: [`porting-a-style.md`](reference/porting-a-style.md).

### 2. Author natively

Use when starting a new style, or when the thing you want is control rather
than speed.

No Python anywhere: the set, the cast and the performance are React components
drawing SVG. [`remotion/src/wetpaint/`](remotion/src/wetpaint/) is a complete
64-second film built this way, and it exists to answer honestly what the
browser can and cannot do on its own.

**It can do the picture, entirely.** Paper grain, a pencil line that boils,
diagonal hatching, hand lettering, a rigged cast that walks and sits, depth
sorting, stepped time — all of it is SVG filters and maths, and it renders
inside the measured style envelope of the reference films it was calibrated
against (mean saturation 0.131 against the reference's 0.132).

**It cannot do the sound.** Remotion mixes and muxes audio; it synthesises
none. A score has to be made elsewhere and handed over. That boundary is the
single most important thing to know before planning a film around this skill —
see [`verification.md`](reference/verification.md#audio), which also documents
a 42.6 ms delay Remotion's AAC path introduces and how to avoid it.

---

## Quick start

```bash
S=skills/render-farm/remotion

cd $S && npm install
npm run studio            # scrub any registered composition in a browser
npm run render            # the traced example -> out/pursuit.mp4
npm run bench             # time this renderer against the Python one
npm run parity            # numeric diff against a Python render
```

To render a specific composition:

```bash
npx remotion render src/index.jsx <Composition> out/film.mp4 \
    --concurrency=4 --gl=swiftshader \
    --pixel-format=yuv420p --color-space=bt709
```

A single frame, which is how most iteration should happen:

```bash
npx remotion still src/index.jsx <Composition> out/check.png \
    --frame=500 --gl=swiftshader
```

### Starting a new film

Copy an existing composition folder, register it in `src/Root.jsx`, and work
from `npm run studio`. `src/lib/` is the part that is not tied to any style —
`Vector.jsx` replays recorded pen primitives, `anim.js` holds the easing and
stepped-time helpers.

---

## Four things that will waste an afternoon

All four fail **silently**, which is why they are here and not in a
troubleshooting appendix.

1. **`--gl=swiftshader` is mandatory on this machine.** Without it every render
   dies on `Timed out after 25000 ms while trying to connect to the browser`,
   with Chrome having logged nothing — which reads like a missing binary and is
   not one. `remotion.config.mjs` sets it, so nothing has to remember.
2. **`Config.setPixelFormat()` and `Config.setColorSpace()` are accepted and
   then ignored** by `remotion render` (4.0.516). They look like they belong in
   the config; putting them there produces a full-range `yuvj420p` file with no
   warning. The CLI flags work, so they live in the npm scripts. Tidying them
   back into the config reverts the fix.
3. **An unused `<Audio>` import still writes an audio track.** A film with
   `Audio` imported and never rendered ships with a valid AAC stream containing
   nothing but digital silence, and every structural check passes. Measure the
   mix, do not probe for its existence.
4. **Rounding a shot's start and its duration separately drops frames.** The
   two roundings disagree whenever a cut lands mid-frame, and the gap renders
   as a flash of the background colour — eleven of them on a fifty-one shot
   board. Every structural check passes, and because a single black frame is
   also a real technique it gets described as a flash rather than as a bug.
   Derive each shot's length from the next shot's cut:
   [`cutting.md`](reference/cutting.md#a-shot-ends-where-the-next-one-starts).

All of them, with the evidence:
[`environment.md`](reference/environment.md).

---

## Where it fits

It does not add a stage. The director's pipeline is unchanged; this is a
substitute for what happens *inside* `render`:

```
board → animate → compile → render
                            ↑ swap the picture pipeline here
```

A style keeps its own `compile.py`, its own board schema and its own
verification. What changes is that `render` runs a browser.

Because of that, `crew.json` declares no stage. The skill is discovered by name
when a style or a director asks for it, never inserted automatically.

### How a production asks for it

```bash
director.py --style-2d-animation --topic "..." --use-remotion
```

`--use-remotion` exists because this skill is installed — `crew.json` declares
`provides_renderer`, and the director generates one `--use-<id>` flag per
installed renderer. The choice is recorded in `production.json`, and from then
on `director.py next` prints a `RENDER` block at `compile`, `render` and
`shoot` naming this skill and what that stage does differently.

**A style has to have opted in**, by listing `"renderers": ["remotion"]` in its
`style.json`. That is refused rather than attempted when it is missing, because
the opt-in records a port someone has actually done — this skill can only draw
a style that has been brought across, and no flag makes that true. Porting one
is [`porting-a-style.md`](reference/porting-a-style.md); it is a day's work,
not a flag.

`director.py doctor` lists every installed renderer, whether `node`, `npm` and
`ffmpeg` are present, and which styles use it.

---

## Good for, wrong for

**Good for** long films, films you are iterating on visually, anything you want
a scrubbable timeline for, vector and flat-shaded styles, and any new style
where the artwork has not been written yet.

**Wrong for** styles whose look depends on per-pixel image processing that a
browser has no equivalent for, and for a one-off render of a film that is
already finished — the browser's startup is a fixed cost that a short render
does not amortise. It is also the wrong tool if you need the picture and the
score to come out of one pipeline, because it will only ever give you the
picture.

---

## Reference

| Doc | Read it when |
|---|---|
| [`environment.md`](reference/environment.md) | something fails silently — GL, colour, audio, npm, determinism |
| [`cutting.md`](reference/cutting.md) | placing shots on the timeline, dropped frames, dissolves, zoom continuity |
| [`porting-a-style.md`](reference/porting-a-style.md) | tracing an existing Python renderer into React |
| [`verification.md`](reference/verification.md) | proving a render is correct: parity, delivery format, audio, benchmarks |

Worked examples, both inside [`remotion/`](remotion/README.md):

- **`src/Film.jsx` + `src/{sets,props,actors,overlays}/`** — the traced port of
  `style-2d-animation`'s pursuit film. Twenty-seven shots, cuts, camera moves,
  parallax and cels. Shows the tracing route end to end.
- **`src/wetpaint/`** — a 64-second film authored natively, no Python involved.
  Shows what the browser can do unaided, and where it stops.

### Two things the board turns on

Both default to off, so an existing board keeps rendering exactly as it did.

- **`broadcast`** — the live clock, channel bug and location tag. These used to
  be unconditional, which meant every film rendered through `Film.jsx` got a
  news chyron whether it was a news bulletin or not. A board now asks:
  `"broadcast": {"location": "CITY WEST"}`.
- **`cast_art: "peeps"`** — draws the cast as whole illustrated cut-out figures
  (`actors/PeepsActors.jsx`) instead of the traced cels. Use it when the camera
  is close enough to tell that nobody drew the people. It reads
  `src/generated/cast.json`, which a production writes; `npm run trace` seeds a
  schema-documenting default from `src/actors/peeps/cast.default.json` if there
  is none, and never overwrites one that exists.
