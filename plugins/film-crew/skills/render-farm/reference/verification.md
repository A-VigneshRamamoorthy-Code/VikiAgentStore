# Verification

A render is not done because it finished. These are the checks, what each one
is actually capable of proving, and the ones that pass while the film is
broken.

---

## Delivery format

Non-negotiable, and the same as every other renderer in this crew:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,pix_fmt,color_range,color_primaries \
  -of default=nw=1 out/film.mp4
```

Expect `1920×1080` (or `1080×1920`), the style's fps, `pix_fmt=yuv420p`,
`color_range=tv`, `color_primaries=bt709`.

`yuvj420p` means the CLI flags were dropped — see
[`environment.md`](environment.md#config-setters-that-are-accepted-and-ignored).
It is the single most likely regression on this renderer, because the thing
that causes it looks like tidying.

---

## Contact sheet, before the full render

```bash
ffmpeg -i out/film.mp4 -vf "fps=1/4,scale=320:-1,tile=6x8" -frames:v 1 sheet.jpg
```

Costs seconds; catches every layout failure a single still hides. Run it before
committing to a multi-minute render, and again afterwards to confirm the film
reads as a story rather than as a sequence of correct frames.

For a still mid-iteration, skip video entirely:

```bash
npx remotion still src/index.jsx <Composition> out/check.png --frame=500 --gl=swiftshader
```

---

## Parity, when porting

`npm run parity` renders mid-shot frames of every shot from both renderers at
**exact frame indices** and reports mean absolute error.

Two rules make the number mean something:

- **Compare at identical frame indices.** Comparing "the same moment" by
  eye compares two different frames and measures nothing.
- **Mask anything deliberately redesigned.** Scoring a change you chose to
  make measures the change, not the port.

Achieved on the reference port: **mean masked MAE 5.96/255 — 2.3% of range, 25
of 27 shots under 10.**

**About 0.3–0.8 of that is the encoder, not the drawing.** Both renderers
deliver studio-range `yuv420p`/bt709, but by different roads: Python lets
swscale convert RGB→YUV while Remotion inserts a `zscale` filter, and they
disagree by a fraction of a level. Rendering one identical 16-frame window
twice — same pictures, only the encode changed — scores 3.33 full-range against
3.65 studio-range.

So: subtract the encoder floor before drawing conclusions, and do not chase the
last point by changing the delivery format.

---

## Dropped frames

A hole in the timeline renders as one flat frame of the composition
background. Nothing structural catches it: the frame count, duration and
container are all exactly right, because the frame *is* there — it just
belongs to no shot.

Scan for frames with no variance at all. A real picture, however dark or
however empty, has structure:

```bash
ffmpeg -v error -i out/film.mp4 -vf "scale=32:18,format=gray" -f rawvideo - \
| python3 -c "
import sys, statistics as st
N = 32*18; i = 0
while True:
    b = sys.stdin.buffer.read(N)
    if len(b) < N: break
    if st.pstdev(b) < 0.5: print('uniform frame', i, 'mean', sum(b)/N)
    i += 1
"
```

**Expect zero**, minus however many impact frames the board authored. The
cause is almost always rounding a shot's start and its duration independently;
[`cutting.md`](cutting.md#a-shot-ends-where-the-next-one-starts) has the fix.

Run this on the delivered file rather than the raw render, so it also covers
anything the colour and mux passes did.

---

## Props draw behind actors, always

The Python renderer sorts props against actors by `z` and `layer`, so a prop
with no depth deliberately sits in *front* — the parapet an actor is tucked
behind. **The trace does not implement that sort.** `Film.jsx` emits the set,
then every prop in board order, then the cast, so a prop is behind an actor
unconditionally and `layer` is ignored.

The consequence is a staging rule rather than a bug to file: **a prop within
about a fifth of a figure's height of its centreline will be hidden by the
body.** Something a character is meant to be holding has to be placed clear of
their silhouette — beside the hand rather than in it — or it simply is not in
the film.

Worth auditing rather than eyeballing, because a hidden prop looks identical
to a prop that was never authored:

```python
for p in shot["props"]:
    for a in shot["actors"]:
        if abs(p["at"][0] - a["at"][0]) < 0.2 * a["height"]:
            print(shot["id"], p["kind"], "is behind", a["id"])
```

The same pass is the right place to check that anything meant to rest on a
surface is actually on it.

---

## Motion

A film can be structurally perfect and still be a slideshow. Two cheap checks:

```bash
# mean absolute difference between adjacent frames
ffmpeg -i out/film.mp4 -vf "select='gt(scene,0)',metadata=print" -f null - 2>&1 | tail
```

- **Mean frame difference above the style's floor** — proves something moves.
- **Tier separation** — if the style declares a motion plan, frames inside a
  `sakuga` beat must differ measurably more than frames inside a `hold`. A
  ratio near 1.0 means the plan was ingested and ignored, which no structural
  check catches.

Adjacent-frame difference is also the right way to compare *generated* content
that cannot match exactly: the reference port's aerial traffic is different
traffic, but at 3.0 against Python's 3.5 it is demonstrably as busy.

---

## Determinism

```bash
npx remotion render … --concurrency=1 out/a.mp4
npx remotion render … --concurrency=4 out/b.mp4
shasum -a 256 out/a.mp4 out/b.mp4
```

Different hashes mean a random value is being drawn at **module scope** rather
than seeded from the frame. Module scope evaluates once per worker, so the film
changes at the boundaries between workers' frame ranges — invisible in Studio,
invisible at `--concurrency=1`, and shipped.

---

## Audio

The checks that matter, in order, because the first two are the ones that get
skipped.

**1. Does it contain sound at all?** A silent placeholder muxes into a
perfectly valid AAC track. `ffprobe` reports a healthy stream, correct
container, correct duration. Nothing structural distinguishes it from a real
mix:

```bash
ffmpeg -i out/film.mp4 -af astats=metadata=1 -f null - 2>&1 | grep -i "RMS level\|Peak level"
```

Digital silence reports `-inf`. Assert on the number, not on the stream's
existence.

**2. Is it in sync?** Remotion's AAC path delays audio by **42.6 ms** — 2048
uncompensated priming samples, two frames at 24 fps. Cross-correlate the
rendered track against the source you handed it; expect lag 0. If it is
negative by ~341 samples at 8 kHz, that is this bug. Render `--muted` and mux
with ffmpeg.

**3. Loudness.** The crew's target is −14 LUFS, true peak ≤ −1 dBFS, zero
clipped samples:

```bash
ffmpeg -i out/film.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -20
```

Remotion does not synthesise audio. Whatever these numbers are, they came from
upstream, and upstream is where they get fixed.

---

## Look grading, for a native film

When a style is calibrated against a reference, verify against the *measured*
contract rather than an impression. Sample frames and compute the same
statistics that defined the style:

| statistic | reference | native example achieved |
|---|---|---|
| mean saturation | 0.132 | **0.131** |
| fraction of pixels sat > 0.35 | 0.92% | 0.00–0.9% |
| mean value (brightness) | 0.878 | **0.886** |

The second row is the one that catches real drift. A single over-saturated
element — one solid slab of a brand colour — spends the entire budget while the
mean barely moves. Grade on the tail, not just the average.

---

## The order to run them

1. `remotion still` on the frame you changed — seconds.
2. Contact sheet — catches staging.
3. Delivery format probe — catches the tidying regression.
4. Dropped frames — catches a hole nothing else measures.
5. Motion and tier separation — catches a slideshow.
6. Audio statistics — catches silence and sync.
7. Determinism — before shipping only.
8. Parity — only when porting, and only after the encode matches.
