---
name: style-news
description: >
  Broadcast-news visual style for production-designer: full-bleed footage under
  a stacked kicker and headline, channel bug, location chip, name straps and
  astonishers. Renders 16:9, 9:16 and 1:1 from a beat plan. Use for bulletins,
  investigations, current affairs and any report that should read as journalism.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# News style

A rolling news bulletin. Full-bleed picture, and across the lower third a
**white kicker bar** over a **red headline bar**; the channel bug bottom-left,
the location chip bottom-right.

This is the `news` style of the `production-designer` skill. It is
self-contained: copy the folder anywhere and it runs. It needs `ffmpeg`,
`python3` and Pillow, and — like every style — it does not make narration.
Get that from [`voice-booth`](../voice-booth/).

---

## Golden rules

1. **The screen is never bare.** Every second of the film carries a graphic.
   The compiler enforces this: each full-width graphic runs exactly until the
   next one takes the screen, and the film opens on a title card if the first
   beat would otherwise leave the top of the video empty. Dead air at the front
   of a video is the most expensive mistake available.
2. **One full-width graphic at a time.** Two overlapping headline bars read as
   a technical fault, not as a design. The compiler cuts the earlier one.
3. **The kicker is context, not a second sentence.** "COST OF LIVING", not
   "and this is what happened next". It takes the act title where there is one.
4. **A figure gets the frame.** When a beat's subject leads with a number, it
   compiles to an *astonisher* — the number huge, what it counts underneath.
   Do not bury a number in a headline bar.
5. **Never invent a picture.** A beat that names footage this style cannot draw
   gets a labelled plate, not the nearest lookalike. A report that shows the
   wrong building is making a false claim in pictures.

## Making one

```bash
S=skills/style-news

python3 $S/scripts/compile.py beat-plan.json --check         # validate only
python3 $S/scripts/compile.py beat-plan.json -o sb.json      # beat plan -> storyboard
python3 $S/scripts/render.py sb.json --sheet                 # LOOK AT THIS FIRST
python3 $S/scripts/render.py sb.json                         # the film
```

`--aspect 16:9|9:16|1:1` on `compile.py` sets the frame shape; `--preview` on
`render.py` halves the resolution, and `--frame 12.5` writes a single frame.

**Always read the contact sheet before rendering.** Pile-ups, dead frames and
collisions are invisible in one frame and obvious across sixteen. Every defect
this style has ever had was found that way and none of them were visible
otherwise.

## What each beat becomes

| beat `intent` | graphic | what it looks like |
|---|---|---|
| `establish` | `locator` | location chip only; the picture carries it |
| `locate` | `locator` | as above |
| `reveal` | `headline` | the kicker/headline stack |
| `emphasise` | `headline` | as above |
| `evidence` | `astonisher` | huge figure, caption under it |
| `portrait` | `namestrap` | name over role, lower left |
| `compare` | `split` | two labelled halves |
| `list` | `bullets` | items arrive one at a time |
| `annotate` | `callout` | circle or box over the plate |
| `transition` | `sting` | accent wipe across the frame |

Every intent in the beat plan's closed vocabulary has a graphic here, which is
the style contract: a style that cannot draw an intent must not be choosable
for a plan that uses it.

The full field-by-field storyboard schema, the timing grammar and the brand
overrides: [`reference/storyboard.md`](reference/storyboard.md).

## Timing

Graphics are pinned to narration lines, never to wall-clock seconds — `"l4"`,
`"l4+0.2"`, `"l4.end"`, or a plain number. The voice booth measures the real
audio, so the film's clock is the voice's clock and a re-recorded line moves
the graphics with it.

## Fonts and non-Latin scripts

The renderer walks a fallback chain and takes the first font that exists, so a
non-Latin headline renders in a font that has the script instead of a row of
empty boxes. Add a font to `FONT_STACK` in `scripts/render.py` if a script you
need is missing.

**Tamil, Devanagari, Arabic and other complex scripts need shaping**, and
Pillow can only shape when it was built against `libraqm`. Without it the
glyphs are drawn in codepoint order — vowel signs land in the wrong place and
the result looks plausible to anyone who cannot read the script. The renderer
detects this and warns; do not publish past that warning. To fix it:

```bash
brew install libraqm
pip install --force-reinstall --no-binary :all: Pillow
python3 -c "from PIL import features; print(features.check('raqm'))"   # True
```

## Worked example

[`examples/bulletin/`](examples/bulletin/) — a beat plan, its compiled
storyboard, and the contact sheet they produce. Start by rendering it.
