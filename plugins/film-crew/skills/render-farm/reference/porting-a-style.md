# Porting a style

How to move an existing Python-rendered style onto this renderer without
redrawing anything.

The worked example is `style-2d-animation`: 27 shots, cuts, camera moves,
parallax, vehicles and a rigged cast, reproduced at **mean masked difference
2.3% of range**. Everything below was learned doing it.

---

## The rule: do not transcribe, record

The tempting approach is to read `sets.py`, understand what it draws, and write
the React equivalent. Do not. Every shape is a chance to be *almost* right, the
errors accumulate quietly, and at the end you have two drawings that disagree
for reasons nobody can enumerate.

Instead: the Python renderer already draws through a **pen** — a small
interface of `line`, `polygon`, `ellipse`, `text` and so on. Swap in a
**recording pen that appends a JSON primitive instead of rasterising**, run the
existing code unmodified, and you have the artwork exactly as authored.

React then replays the recording. `lib/Vector.jsx` is 11 primitives mapped to
SVG elements and is the entire translation layer. It contains no knowledge of
the style.

This inverts where errors can live. They can no longer be in the drawing; they
can only be in **what you asked the drawing code for** — a seed, a coordinate
space, a clock. Those are findable by diffing numbers. Shapes drawn from memory
are not.

---

## The tracers

| tracer | records | output |
|---|---|---|
| `trace-props.py` | the recording pen itself, plus every prop drawing | `src/generated/props.json` |
| `trace-sets.py` | every parallax layer, per shot, delta-encoded when it moves | `src/generated/sets.json` |
| `trace-actors.py` | rig poses as transparent cels | `src/generated/actors.json` + `public/actors/` |
| `trace-camera.py` | the resolved view rect, one entry per frame | `src/generated/camera.json` |

`npm run trace` regenerates all four. They read the board directly, so
**re-timing the board re-traces correctly** with no constant edited by hand.

They import the style's own modules, so they need the Python engine and its
dependencies. The style they trace is named explicitly and can be overridden:

```bash
FILM_STYLE_SKILL=/path/to/skills/style-2d-animation npm run trace
```

### Cels are a legitimate answer

The rig was the one thing that could not be traced: it paints straight onto a
PIL surface at 3× rather than through the pen, so there was no seam to record
from. Actors are baked as **cels** instead.

That is not a compromise, it is what limited animation does on paper. 100
frames of a character driving are 20 drawings, because the film holds on
threes. Where the cache stops helping — a smear pass at 82 drawings for 84
frames — that is the style working, not the cache failing.

---

## The five assumptions that were wrong

Each was found by diffing numbers, never by looking at the picture. This is the
list to check against when a port is close but not right.

1. **Scenery is seeded per shot** (`self.seed ^ shot.seed`), not per set. Ten
   street shots are ten *different* streets. Tracing once per set made them
   identical, and once you know it, obviously wrong.

2. **Foreground layers anchor to the frame's bottom edge**, not to a world Y.
   `trace-sets.py` now detects this automatically: trace twice with different
   window bottoms and see which layers moved.

3. **Actors default to `z = 0.5`**, and the rig desaturates with depth. Baking
   cels at `z = 1.0` made every character too saturated — a uniform error
   across the whole film that looks like a palette bug.

4. **A prop's wheels only turn if the board gave it an `anim`.** The renderer
   zeroes the rate otherwise. In this board every vehicle except the helicopter
   holds one drawing while the scenery moves past it. An earlier cut spun the
   wheels of parked cars.

5. **`phase` and `t` are different clocks.** `phase` is quantised with the
   characters — animating on twos, so it steps. `t` is true shot-local time,
   for things that are scenery rather than drawing: a light bar, a rotor, a
   blinker. Using one where the other belongs makes a rotor stutter or a walk
   go smooth, and both read as "something is off" rather than as a bug.

---

## The camera is the hard part

`track`, `pan` and `whip` are the *same* interpolation in the engine. What
separates them is a default easing curve, a `hold`/`pre_hold` settle carved out
before easing, a pass that silently refuses mechanical eases, a seeded handheld
table, and a `follow` mode that depends on where an actor is.

Reimplementing that is five chances to be almost right, and the measurement
said so precisely: **every `push`/`none` shot scored under 5, while every
`track`/`whip`/`handheld` shot scored 12–19.**

The fix was to stop reimplementing and start recording — replay
`CameraSolver.view(t)` per frame from `camera.json`. That fixed all nine
camera-move shots at once and cut the overall mean by a third in one change,
8.09 → 5.31.

**Generalise this.** If a subsystem's behaviour is emergent from several
interacting rules, trace its *output*, not its logic. The camera solver is 300
lines of interacting special cases and 137 kB of recorded view rects. The
recording is the cheaper and more faithful artefact.

---

## What will not match, and why to stop

Know the floor before chasing it.

- **Anything generated against the camera's own bounds.** The pursuit's aerial
  traffic is generated against the pen's bounds, and the engine's bounds are
  *the view rect of that frame*. Which cars exist depends on where the camera
  is. Tracing the same layer over two windows produces zero identical
  primitives even in the overlap. The traffic in the port is equally dense and
  moves with the same character — adjacent-frame difference 3.0 against
  Python's 3.5 — but it is *different traffic*. Matching it exactly would mean
  re-tracing per frame at the frame's own view rect, roughly 60 MB, to
  reproduce an artefact of how the RNG is consumed.

- **Edge antialiasing, everywhere.** The residual on a *good* shot is a
  one-pixel outline around every shape: PIL's supersampling and the browser's
  rasteriser disagree about edges. This is the floor, and it is why 2.3% is
  about as low as a shot gets.

- **Anything deliberately redesigned.** Mask it out of the score rather than
  counting it as a win or a loss.

---

## Generated data is not source

`src/generated/*.json` (~8 MB) and `public/actors/` (~2.7 MB) are **build
output** and are gitignored. They rebuild from the board with `npm run trace`.

The tracers need the Python engine, which is a sibling skill — so there is no
checkout in which the tracers exist but the data cannot be rebuilt. Committing
the traces would put 11 MB of derived data in git to save a command.

---

## Is it worth it?

For a **new** style, yes without qualification — Studio alone earns it, and the
parallelism is free rather than fought for.

For an **existing** style, be honest about what you are buying. This port is a
renderer, not a replacement: every drawing still comes out of Python, and the
tracers are a bridge that needs both banks. Replacing the engine's `sets.py`
and `rig.py` with real React components would be a much larger job than making
them render 5.5× faster — and the 5.5× is available without touching either.

Trace when you want speed and a timeline. Author natively when you want the
browser to be where the film is *made*.
