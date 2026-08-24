# Environment

Everything here fails **silently or misleadingly**. None of it is discoverable
from an error message, which is the only reason it is written down.

---

## GL: `--gl=swiftshader` is not optional

With the default ANGLE backend every render on this machine dies with:

```
TimeoutError: Timed out after 25000 ms while trying to connect to the browser!
```

Chrome logs nothing. The message points at a missing or broken browser
install, and that is not the problem. Verbose logging shows the real cause:

```
gl_factory.cc:110: Requested GL implementation (gl=none,angle=none) not found
in allowed implementations: [(gl=egl-angle,angle=opengl),(gl=egl-angle,angle=metal)]
```

The browser is fine. The **GL backend** is not. `remotion.config.mjs` sets
`Config.setChromiumOpenGlRenderer('swiftshader')` so nothing has to remember —
but any command run outside the npm scripts needs `--gl=swiftshader` passed
explicitly.

This is a useful correction to a note in the repository's `AGENTS.md`, which
says headless Chrome hangs on this macOS setup and that jsdom is the supported
path. That is half right, and the half that is wrong costs a day.

Software rasterisation is slower per frame than a GPU. It is still 5.5× the
Python renderer, because the win is thread scaling, not pixel throughput.

---

## The entry point is `src/index.jsx`

Passing `src/index.js` — a file that does not exist — produces:

```
No entry point specified.
```

Not "file not found". The message reads as though the argument were missing
entirely.

---

## Config setters that are accepted and ignored

`remotion render` 4.0.516 ignores these when they are set in
`remotion.config.mjs`:

- `Config.setPixelFormat()`
- `Config.setColorSpace()`

No warning, no error. The render produces a full-range `yuvj420p` file, and the
only way to find out is to read the FFmpeg command that verbose logging prints.

The **CLI flags do work**:

```bash
--pixel-format=yuv420p --color-space=bt709
```

They live in the `render` and `render:vertical` npm scripts and in `bench.mjs`,
each with a comment saying why. Tidying them back into the config file silently
reverts the fix.

**Why studio range matters here:** full range would score slightly better on a
parity diff. It would also ship a file tagged `pc` that many players letterbox
into studio range anyway, so the film comes out lighter in the blacks than the
Python render of the same board. Matching the delivery format the rest of the
crew produces is worth more than 0.3 of a diagnostic metric.

---

## npm 11 leaves esbuild unbuilt

npm 11 blocks install scripts by default. Remotion bundles with esbuild, so a
render fails at bundle time with an esbuild binary error:

```bash
npm approve-scripts esbuild && npm rebuild esbuild
```

Once per checkout.

---

## Audio: Remotion muxes, it does not synthesise

There is no oscillator, no synth, no procedural sound. `<Audio src={…} />`
plays a file you already have. If the film needs a score, something else has to
make it — in this crew, `style-paper/scripts/audio.py` and `score.py` do, and
`sound-designer` owns the mix.

Two consequences:

**A silent placeholder passes every check.** A WAV of digital silence muxes
into a valid AAC track. `ffprobe` reports a healthy audio stream, the
container is correct, the duration matches. Nothing structural can tell you the
film is silent. Measure the mix — peak, RMS, loudness — or do not claim it has
one.

**The AAC path delays audio by 42.6 ms.** 2048 priming samples that Remotion
does not compensate for. Measured by cross-correlating a rendered track against
its source:

| path | lag | correlation |
|---|---|---|
| `.mov` + `--audio-codec=pcm-16` | **0 samples** | **1.0000** |
| default AAC | −341 samples @ 8 kHz (**−42.6 ms**) | 0.9903 |

Two frames at 24 fps. Enough to make a footstep land wrong.

The fix is to render `--muted` and mux the audio in with ffmpeg afterwards,
which also removes an entire re-encode from the loop:

```bash
npx remotion render src/index.jsx Film out/silent.mp4 --muted --gl=swiftshader
ffmpeg -i out/silent.mp4 -i mix.wav -c:v copy -c:a aac -b:a 192k \
       -shortest out/film.mp4
```

`--audio-codec=pcm-16` requires a `.mkv` or `.mov` container. It will refuse an
`.mp4` and the message does say so, which makes it the friendliest failure on
this page.

---

## Concurrency and determinism

`--concurrency=N` opens N browser tabs. On the reference machine 4 is the sweet
spot; beyond that memory pressure costs more than the parallelism returns.

Renders are deterministic across concurrency settings **provided every random
value is seeded from the frame number or a fixed seed**, never from
`Math.random()` at module scope. Module scope evaluates once per worker, so a
module-level random differs between tabs and the film changes at the seams
between their frame ranges — a defect that appears only at `--concurrency>1`
and is invisible in Studio.

Check it the same way the rest of the crew does:

```bash
npx remotion render … --concurrency=1 out/a.mp4
npx remotion render … --concurrency=4 out/b.mp4
shasum -a 256 out/a.mp4 out/b.mp4
```

---

## Cost, for planning

Reference machine, 1920×1080, `--concurrency=4`, swiftshader:

| film | frames | wall | user CPU |
|---|---|---|---|
| traced, 27 shots | 2333 | 72 s | 269 s |
| native, hand-drawn SVG | 1540 | 3 m 22 s | 21 m |

The native film is far more expensive per frame: every frame rasterises paper
grain, a displacement-mapped pencil filter and a full cast, where the traced
film mostly composites pre-rendered cels. Budget by **what a frame contains**,
not by frame count.

---

## Fonts

A cursive or display font that resolves through a **system fallback** will look
right locally and wrong in CI, silently. Either bundle it with
`@remotion/google-fonts`, or draw the letterforms as paths. Do not rely on a
family name being installed.
