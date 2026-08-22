# Architecture

What each module owns, the order the renderer does things in, and where to
extend it.

---

## Modules

| Module | Provides |
|---|---|
| `paper.py` | parchment, torn edges with an exposed fibrous core, elevation shadows, edge light, fold creases, paper stacks, tape, pins, coffee rings, ghost print, grain, vignette, halftone |
| `collage.py` | tracked type, label chips, ink stamps, typewriter lines, red marker strokes, photo stickers |
| `illustrations.py` | procedural cut-out artwork (mouse, lantern, moon, star, hill, snow, hotel, boat, sea, clock, candle) |
| `motion.py` | easings, entrances (`stamp`, `pin`, `slide`, `fly`, `fade`), idle float, parallax, keyframed camera paths |
| `audio.py` | synthesis primitives, music beds, paper SFX, narration loading, ducking, R128 mastering |
| `render.py` | storyboard orchestration, layout, encoding |

Only `render.py` is executable. Everything else is a library.

---

## Pipeline order

The order matters, and one step in particular is load-bearing:

1. **Narration is loaded and measured first** (`build_narration`). The clips
   come from the [`voice-booth`](../../voice-booth/) skill; this skill never
   synthesises speech. Every line's real duration is known before any layout
   happens, which is why symbolic times like `"l4+0.35"` survive a rewrite.
2. **The music bed is generated** to the now-known total duration
   (`build_music`).
3. **Elements are resolved** — `box_of` fits a marker around another element's
   actual rendered artwork, so red annotation cannot drift off its target.
4. **Static elements are baked** once, into a single layer.
5. **Frames are composited**, camera applied per frame.
6. **Audio is mixed** — duck, master to −14 LUFS.
7. **Video is encoded** with a bitrate cap.

Step 1 is the reason for golden rule 8, *write the audio first*. If you ever
find yourself hand-typing a wall-clock time into a storyboard, you are fighting
this design.

> Per-frame grain is incompressible, so CRF alone lets the bitrate explode to
> 60–100 Mbps. `render.py` caps it near the reference's ~19 Mbps.

---

## Extension points

**New subject matter → a new function in `illustrations.py`** returning an RGBA
`Image`, plus a branch in `render.make_art`. This is the only extension most
pieces need.

**New instrument → a function in `audio.py`** returning a float array at
`SR = 48000`, plus use in the relevant `build_music` branch.

⚠️ **Never call `np.random.*` directly in an instrument.** Take a `seed`
argument and build your own `np.random.default_rng(seed)`. The global RNG is
unseeded, and using it silently breaks the byte-for-byte reproducibility
promise in [`STYLE.md`](../SKILL.md) golden rule 10 — see
[`troubleshooting.md`](troubleshooting.md#the-same-storyboard-renders-a-different-file-every-time)
for the bug this actually caused.

**New mood → a branch in `build_music`**, plus entries in the `default_scale`
and `step` dicts. Check whether the generic percussion layer should be gated
off for it; a mood with its own percussion will otherwise get two layers.

---

## Conventions inside the scripts

- Design space is **1920×1080** and `at` is always an element **centre**.
- `SR = 48000` throughout `audio.py`.
- `OVER = 1.34` — the board is rendered larger than frame so the camera has
  somewhere to travel.
- Anything random takes a seed. Same storyboard, same bytes.
