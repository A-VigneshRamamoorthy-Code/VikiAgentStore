# The Remotion project

The runnable half of the [`render-farm`](../SKILL.md) skill: a Remotion
project holding the shared scaffold and two complete worked films.

Method, environment traps and verification live in
[`../reference/`](../reference/). This file is about *this directory*.

```bash
npm install
npm run studio            # scrub any composition in a browser
npm run render            # traced example  -> out/pursuit.mp4
npm run render:vertical   #                 -> out/pursuit-vertical.mp4
npm run bench             # time this renderer against the Python one
npm run parity            # numeric diff against a Python render
npm run trace             # rebuild the traced example's data
```

First run in a fresh checkout also needs
`npm approve-scripts esbuild && npm rebuild esbuild` — npm 11 blocks install
scripts and Remotion bundles with esbuild.

---

## Layout

```
remotion/
├── remotion.config.mjs      # the swiftshader setting; read the comment
├── bench.mjs                # times both renderers on the same board
├── data/                    # board + resolved timeline for the traced example
├── tools/trace-*.py         # the four tracers
├── tools/parity.py          # numeric diff against the Python render
└── src/
    ├── index.jsx            # entry point — .jsx, not .js
    ├── Root.jsx             # every composition is registered here
    ├── lib/Vector.jsx       # replays 11 recorded pen primitives as SVG
    │
    ├── Film.jsx             # ── traced example ──────────────────
    ├── sets/Sets.jsx        # parallax + delta-decoded moving layers
    ├── props/Props.jsx      # selects a traced drawing; draws nothing
    ├── actors/Actors.jsx    # composites cels at absolute scene coords
    ├── overlays/Overlays.jsx
    │
    └── wetpaint/            # ── native example ──────────────────
        ├── Paper.jsx        # paper grain + the pencil filter
        ├── Set.jsx          # the world, the camera, the bench
        ├── Figures.jsx      # the rig: walk, stand, sit
        ├── Type.jsx         # clouds and hand lettering
        └── WetPaint.jsx     # the film: beats, staging, depth
```

`src/lib/` is the only part tied to no style. Everything else is an example.

---

## The two examples

### Traced — `Film.jsx` and friends

The `style-2d-animation` pursuit film, 27 shots, rendered from data recorded
out of that style's Python engine. No artwork was transcribed; a recording pen
captured it as JSON and React replays it. Scores **2.3% mean masked difference**
against the Python render of the same board.

Its tracers import the style's modules, so they need the Python engine. The
style is named explicitly and can be pointed elsewhere:

```bash
FILM_STYLE_SKILL=/path/to/skills/style-2d-animation npm run trace
```

`src/generated/*.json` (~8 MB) and `public/actors/` (~2.7 MB) are **build
output** and gitignored — rebuild with `npm run trace`.

Method and the five assumptions that were wrong:
[`../reference/porting-a-style.md`](../reference/porting-a-style.md).

### Native — `wetpaint/`

A 64-second film with no Python anywhere: set, cast, performance and lettering
are React components drawing SVG. Registered as `WetPaint` (1920×1080, 24 fps,
1540 frames).

It exists to answer honestly what a browser can do unaided. It can do the whole
picture — paper grain, a boiling pencil line, hatching, hand lettering, a rig
that walks and sits, depth sorting, stepped time — and it lands inside the
measured envelope of the style it was calibrated against (mean saturation 0.131
against 0.132). It cannot do the sound; Remotion muxes audio and synthesises
none, which is why this film is silent and says so.

Three things in it are worth stealing for any native film:

- **`PencilDefs({seed, scale, cam})` divides displacement by the camera
  scale.** `feDisplacementMap`'s `scale` is in the filtered element's user
  units, so anything inside a scaled camera group gets its wobble multiplied by
  that scale. A separate `#pencilFlat` filter serves screen-space elements,
  which must *not* be divided.

- **The depth sandwich.** A face-on bench and a profile sitter are
  incompatible: the thigh lies along the seat slats at exactly their height and
  disappears into them, so the figure reads as standing *behind* the bench. Two
  changes fix it together — turn the figure front-on the moment it sits, and
  draw the seat band *in front of* its hips. `Bench` renders in two parts and
  the film draws back → seated cast → seat → standing cast, mounting the whole
  cast twice via a `layer` prop.

- **Standing is its own pose, not phase 0 of the walk.** Sampling a walk cycle
  at rest welds the feet together and hides both arms behind the torso.
  Relatedly, driving two legs off `sin(p)` and `-sin(p)` makes them exact
  mirrors, so at the passing position both go vertical at the same x and the
  figure loses its legs for a frame.

---

## Adding a film

Copy either example's folder, register a `<Composition>` in `src/Root.jsx`, and
work from `npm run studio`. A vertical cut is a second `<Composition>` at
1080×1920 pointing at the same component — not re-authored staging.
