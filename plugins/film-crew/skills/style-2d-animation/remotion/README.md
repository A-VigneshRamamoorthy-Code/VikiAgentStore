# A Remotion renderer for `style-2d-animation`

A second renderer for the **pursuit** film, built to answer one question:
is Remotion a better way to make this style than the Python engine — on
**efficiency** and on **control over animation**?

It is a real comparison rather than a demo. Both renderers consume the same
`examples/pursuit/board.json` and the same resolved timeline, so the only
thing that differs is the picture pipeline.

```bash
npm install
npm run studio     # scrub the film in a browser
npm run render     # out/pursuit.mp4
npm run bench      # time both renderers on the same board
npm run parity     # numeric diff against the Python render
```

---

## The answer, in numbers

Full film, 2333 frames, 1920×1080 @30, video only, on the same machine:

| renderer | wall clock | user CPU | sys | cores kept busy |
|---|---|---|---|---|
| Python `-j 4` | **390.07 s** | 452.58 s | 13.50 s | **1.19** |
| Remotion `--concurrency=4` | **71.57 s** | 268.68 s | 17.11 s | **3.99** |

**5.5× faster in wall clock** — and the reason is in the last column, not the
first. Python's `-j 4` kept 1.2 cores busy across 390 s: on this workload the
`-j` flag bought almost nothing. Remotion's workers kept 4.0 of the 4 they
were given.

(Both figures come from `npm run bench` on one machine and will move on
another. The ratio and the core counts are the transferable part.)

The per-frame work is also cheaper. Python composites every layer in PIL at
3× supersample and downsamples; the browser rasterises SVG once and moves
static layers with GPU-composited transforms, which is exactly the shape of
work a browser is built for.

`npm run bench` reproduces this, and `node bench.mjs --seconds 12` gives the
same picture in a fraction of the time (4.6×, cores 1.18 vs 3.55 — a short run
pays the browser's startup out of a smaller budget, so it understates).

## The answer, on control

Harder to tabulate, and more important:

- **You can see the frame you are editing.** `npm run studio` gives a scrubbable
  timeline with hot reload. The Python loop is edit → re-render → open the file.
- **Time is composable.** `<Sequence from={...}>` re-bases the clock, so a shot
  gets `frame` starting at 0 and stepping-on-twos falls out for free instead of
  being arithmetic every component has to remember.
- **Layers are components.** Parallax is a `transform` on a `<g>`, not a
  re-draw at a shifted origin.
- **Both aspect ratios are the same component.** `PursuitVertical` is the
  16:9 film at 1080×1920 with a second camera trace; no re-authored staging.

The honest counterweight: **all the artwork is still Python's.** See below.

---

## How it works: tracing, not porting

The set and prop drawings are ~4,800 lines of Python. Hand-porting them would
have taken hours and still produced a *different film* — which would have
destroyed the comparison, because any difference in the output could be blamed
on transcription.

So nothing is ported. `sets.py` draws everything through a `_Pen` abstraction
that owns the only multiplication by `unit`, which makes the pen the single
seam in the whole module. Swapping in a **`RecordingPen` that appends JSON
instead of rasterising** gets the artwork out exactly as authored.

| tool | what it captures | output |
|---|---|---|
| `tools/trace-props.py` | every prop *instance* in the board, on the axes it responds to | `src/generated/props.json` |
| `tools/trace-sets.py` | every parallax layer, per shot, delta-encoded when it moves | `src/generated/sets.json` |
| `tools/trace-actors.py` | the rig's poses as transparent cels | `src/generated/actors.json` + `public/actors/` |
| `tools/trace-camera.py` | the resolved view rect, one entry per frame | `src/generated/camera.json` |

Regenerate all four with `npm run trace`. They need the Python engine and its
dependencies, and they read the board directly, so re-timing the board
re-generates correctly without any constant being edited by hand.

The rig is the exception: it paints straight onto a PIL surface at 3× rather
than through the pen, so there was no seam to record vectors from. Actors are
therefore **cels** — which is what limited animation does on paper anyway.
100 frames of Norman driving are 20 drawings, because the film holds on threes;
the cyclist's smears deliberately defeat the cache at 82 drawings for 84
frames, which is the style working rather than the cache failing.

---

## Parity

`npm run parity` renders mid-shot frames of all 27 shots from both videos at
**exact frame indices** and reports mean absolute error. Broadcast furniture is
masked, because those overlays were deliberately redesigned and scoring them
would measure an intended change.

**Mean masked MAE 5.96/255 — 2.3% of range. 25 of 27 shots under 10.**

About **0.3–0.8** of that is the *encoder*, not the drawing. Both engines now
deliver studio-range `yuv420p`/bt709, but they get there by different roads:
`render.py` lets swscale do the RGB→YUV conversion while Remotion inserts a
`zscale` filter, and the two disagree by a fraction of a level. Rendering one
identical 16-frame window twice — same pictures, only the encode changed —
scores 3.33 full-range against 3.65 studio-range. Full range would flatter this
number; it would also ship a file tagged `pc` that many players letterbox into
studio range anyway, so the film would come out lighter in the blacks than the
Python render of the same board. Matching the delivery format is worth more
than 0.3 of a diagnostic metric.

Getting there was mostly a matter of finding places where I had *assumed*
instead of read. Each of these was found by diffing numbers, not by looking:

1. **Scenery is seeded per shot** (`self.seed ^ shot.seed`), not per set. Ten
   street shots are ten different streets. Tracing per set made them identical
   and visibly wrong.
2. **Foreground layers anchor to the frame's bottom edge**, not to a world Y.
   `tools/trace-sets.py` detects this automatically by tracing twice with
   different window bottoms and seeing which layers move.
3. **Actors default to `z = 0.5`**, and `rig.draw` desaturates with depth.
   Baking cels at `z = 1.0` made every character too saturated.
4. **A prop's wheels only turn if the board gave it an `anim`.** The renderer
   zeroes the rate otherwise — so in this board every vehicle except the
   helicopter holds one drawing while the scenery moves past it. An earlier
   cut spun the wheels of parked cars.
5. **`phase` and `t` are different clocks.** `phase` is quantised with the
   characters; `t` is true shot-local time, for the things that are scenery
   rather than drawing — a light bar, a rotor, a blinker.
6. **The camera was the big one.** `track`, `pan` and `whip` are the *same*
   interpolation in the engine; what separates them is a default easing curve,
   a `hold`/`pre_hold` settle carved out before easing, a pass that silently
   refuses mechanical eases, a seeded handheld table, and a `follow` mode that
   depends on where an actor is. Reimplementing that was five chances to be
   almost right, and the measurement said so: every `push`/`none` shot scored
   under MAE 5 while every `track`/`whip`/`handheld` shot scored 12–19.
   Replaying `CameraSolver.view(t)` per frame fixed all nine at once and cut
   the mean by a third in a single change — 8.09 to 5.31, measured before the
   encode was matched to `render.py`, which later added back ~0.6.

### What does *not* match, and why

- **The three aerial shots (MAE 8–16).** The aerial traffic is generated
  against the pen's bounds, and the engine's bounds are the **view rect of
  that frame** — so which cars exist depends on where the camera is. Tracing
  the same layer over two different windows produces zero identical
  primitives, even in the overlapping region. A world-strip trace cannot
  reproduce it. The traffic here is equally dense, equally busy and moves
  with the same character (adjacent-frame MAE 3.0 vs Python's 3.5), but it
  is *different traffic*. Reproducing it exactly would mean re-tracing per
  frame at the frame's own view rect, at roughly 60 MB, to match an artefact
  of how the RNG is consumed.
- **Edge antialiasing everywhere.** The residual on a good shot is a
  one-pixel outline around every shape: PIL supersampling and the browser's
  rasteriser disagree about edges. This is the floor, and it is why 2.3 is
  about as low as a shot gets.
- **The broadcast overlays are intentionally different**, redesigned against
  a supplied reference. They are masked out of the score rather than counted
  as either a win or a loss.

---

## Environment

**Remotion needs `--gl=swiftshader` on this machine.** `remotion.config.mjs`
sets it, so nothing has to remember the flag.

This is worth writing down because the failure is silent and the error message
points the wrong way. With the default ANGLE backend every render dies with
`TimeoutError: Timed out after 25000 ms while trying to connect to the
browser!` and Chrome logs nothing. Verbose logging shows the real cause:

```
gl_factory.cc:110: Requested GL implementation (gl=none,angle=none) not found
in allowed implementations: [(gl=egl-angle,angle=opengl),(gl=egl-angle,angle=metal)]
```

The repository's `AGENTS.md` says headless Chrome hangs on this macOS setup and
that jsdom is the supported path. That is half right — the *browser* is fine,
the GL backend is not.

Also: npm 11 blocks install scripts, which leaves esbuild unbuilt. If a render
fails at bundle time:

```bash
npm approve-scripts esbuild && npm rebuild esbuild
```

One more trap, because it fails quietly: **`Config.setPixelFormat()` and
`Config.setColorSpace()` are accepted and then ignored by `remotion render`**
(4.0.516). They belong in `remotion.config.mjs` next to the GL renderer, and
putting them there produces a file that is still full-range `yuvj420p` with no
warning — you only find out by reading the FFmpeg command that verbose logging
prints. The equivalent CLI flags do work, so `--pixel-format=yuv420p
--color-space=bt709` live in the `render` and `render:vertical` scripts, and
in `bench.mjs` so both sides of the benchmark do the same encoding work.
Tidying them back into the config silently reverts the fix.

---

## Generated data is not source

`src/generated/*.json` (~8 MB) and `public/actors/` (~2.7 MB) are **build
output** and are gitignored. They are reproducible from the board with
`npm run trace`, and the tracers require the Python engine, which lives two
directories up — so there is no checkout in which the tracers are available
but the data cannot be rebuilt.

## Layout

```
remotion/
├── remotion.config.mjs      # the swiftshader setting; read the comment
├── bench.mjs                # times both renderers on the same board
├── data/board.json          # copy of examples/pursuit/board.json
├── data/timeline.json       # shot times resolved by the Python engine
├── tools/trace-*.py         # the four tracers
├── tools/parity.py          # numeric diff against the Python render
└── src/
    ├── Root.jsx             # Pursuit 1920x1080, PursuitVertical 1080x1920
    ├── Film.jsx             # the sequencer; the two-clock rule lives here
    ├── lib/Vector.jsx       # replays 11 recorded pen primitives as SVG
    ├── sets/Sets.jsx        # parallax + delta-decoded moving layers
    ├── props/Props.jsx      # selects a traced drawing; draws nothing
    ├── actors/Actors.jsx    # composites cels at absolute scene coords
    └── overlays/Overlays.jsx # the only hand-authored artwork here
```

## Would I build the style this way?

For a **new** style, yes — Studio alone is worth it, and the parallelism is
free rather than fought for.

For *this* style, the honest answer is that this port is a renderer, not a
replacement. Every drawing still comes out of the Python engine; the tracers
are a bridge, and a bridge needs both banks. Replacing `sets.py` and `rig.py`
with React components would be a much larger job than making them render 6×
faster — and the 6× is available today without touching either.
