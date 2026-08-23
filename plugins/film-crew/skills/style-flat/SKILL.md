---
name: style-flat
description: >
  Mid-century flat-vector visual style for production-designer: saturated flat
  colour on a hard-edged field, with no texture, no outline and no shadow — the
  UPA / Saul Bass / Mary Blair vocabulary. Shares the paper style's compiler and
  engine, so the same storyboard renders in either look. Use for essays,
  thrillers, sport, history and title sequences, and whenever a film needs to be
  bold rather than archival.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Flat style

Saturated flat colour on a hard-edged field. No paper, no grain, no torn
border, no drop shadow. A shape is a shape: one colour, one silhouette,
sitting on a large confident field of another colour.

This is the `flat` style of the `production-designer` skill. It is the
counterpart to [`style-paper`](../style-paper/) and deliberately inverts it.

| | paper | flat |
|---|---|---|
| surface | mottled stock, fibre, blotches | one two-stop gradient |
| edge | torn white border, contact shadow | none |
| colour | muted, low-chroma, aged | saturated, high-contrast |
| feeling | evidence, archive, the past | assertion, design, the present |

**It does not have its own compiler or renderer.** It shares both with the
paper style and changes only the look. That is the point: give both styles
the *same* storyboard and the only difference in the two films is how they
look, never what they say.

---

## Golden rules

1. **Colour carries the mood, because nothing else can.** With no texture and
   no shading there is exactly one expressive channel left. Eight palettes are
   chosen from the story's own words (see `look.PALETTES`); a palette is a
   near-black or saturated *field* plus five *papers* that everything on
   screen is drawn in.
2. **A shape has one colour.** No gradient inside a shape, no outline, no
   highlight, no shadow. Depth comes from overlap and scale.
3. **Captions are the one guaranteed-legible element.** They are forced to a
   bright chip with field-coloured text, so they survive any palette. Never
   let a caption inherit the scenery ink — in a dark palette that is
   near-black on near-black.
4. **Big shapes, few of them.** Flat colour rewards scale. Three large shapes
   read; nine small ones look like a diagram.
5. **The field is a character.** It changes with the act, and it is usually
   the largest area of colour on screen.

---

## Use it

The compile step is the paper style's, unchanged:

```bash
python3 ../style-paper/scripts/compile.py beat-plan.json \
        --motion-plan motion-plan.json -o sb.json
python3 scripts/render.py sb.json --sheet          # contact sheet first
python3 scripts/render.py sb.json -o film.mp4 -j 0
```

`--palette <name>` forces a palette; otherwise it is chosen from the board's
own mood, falling back to a mapping from the paper palette it was compiled
for.

Always look at the contact sheet before rendering. Removing the white border
is most of this style, and it is also the one change that can cost
figure/ground separation — a dark figure on a dark field disappears in a way
it never could when every shape had a white margin.

---

## How it works

`scripts/look.py` holds the palettes and three replacement primitives:
`colour_field` (the background), `flat_sticker` (a no-op where paper grew a
white border) and `no_grain`.

`scripts/render.py` is a thin wrapper. `install()` patches the paper look out
of the shared engine before a single pixel is drawn, then hands over to it.

### Four traps, all of which this file has already fallen into

1. **`import render` inside a file called `render.py` imports itself.** A
   script's own directory is prepended to `sys.path`, so the engine must be
   loaded by explicit path (`_engine()`), never by name. Loading itself is
   silent — the film renders, in the wrong style, and looks like the patches
   did nothing.
2. **`from paper import PALETTE` binds the dict object.** Mutate it in place;
   never rebind it. A reassignment leaves every already-imported module
   pointing at the old table.
3. **Default arguments capture colour at import time.** `def marker_rect(...,
   color=PALETTE["accent"])` is evaluated once, when the module loads, so
   updating `PALETTE` afterwards does nothing for it. `_retint_defaults()`
   walks every module-level function and rewrites `__defaults__` and
   `__kwdefaults__`.
4. **`parchment` is called by two different kinds of caller.** The frame-sized
   board, whose colour this style owns, and small surfaces — chips, cards,
   labels — that name a stock colour and mean it. Honour the caller's colour
   only for the small ones, or the film's background reverts to paper.

---

## Palettes

A palette is a **field** (the background, and usually the largest area of
colour on screen) plus five **papers** that everything else is drawn in. They
are named after the story moods the score already uses, so a film's picture
and its music are chosen by the same word.

| name | field | papers | reads as |
|---|---|---|---|
| `dread` | `#0D0D12` | `#CC2222` `#FFD700` `#881838` `#E8552F` `#5A1F3A` | near-black with one bright warning — menace |
| `elegy` | `#1C1C2E` | `#7A8BA8` `#A8B8D0` `#5B6B8C` `#C9A227` `#8E7BA6` | cold blues, one warm note — grief |
| `tension` | `#181818` | `#FF4444` `#FF8C00` `#F2F2F2` `#7A1F1F` `#2E6E8E` | stark reds against black — threat |
| `curious` | `#F7F3E8` | `#FF6B35` `#41C7B9` `#E84686` `#2E5F8A` `#F2B705` | bright, warm, open — discovery |
| `tender` | `#FFF0F5` | `#E8709F` `#B896E6` `#FFB067` `#6FB7C4` `#D64D7A` | Mary Blair pinks and violets — intimacy |
| `triumph` | `#0A1628` | `#FFD700` `#FF4500` `#F2F2F2` `#41C7B9` `#E84686` | gold on midnight — arrival |
| `reflective` | `#1A2744` | `#6EB5C0` `#A8C4D4` `#F2E85C` `#4A7FA5` `#D98E5A` | petrol blues with one warm note — memory |
| `voyage` | `#10344A` | `#41C7B9` `#F2E85C` `#E8703A` `#8FD6C8` `#2E5F8A` | sea blues and a hot sail — distance |

Selection order, in `look.choose()`:

1. the board's `music.mood`, if it names one of the above;
2. otherwise `FROM_PAPER`, which maps the paper palette the board was
   compiled for onto its nearest flat equivalent (`sepia` → `reflective`,
   `noir` → `dread`, `ember` → `triumph`, …);
3. otherwise `reflective`.

`--palette <name>` overrides all three.

Two of the eight — `curious` and `tender` — are **light-field** palettes.
They are the ones to reach for when a story should not look like a thriller,
and the ones to check hardest on a contact sheet, because a pale figure on a
pale field is where this style is weakest.

