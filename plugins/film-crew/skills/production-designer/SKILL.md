---
name: production-designer
description: >
  Owns the look of a film. Holds the style registry — paper collage and any
  style added later — picks the right one for a topic, compiles a beat plan
  into that style's storyboard, and renders it. Use when choosing a visual
  style, rendering a video, or adding a new style.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Production designer

You own how the film looks. A **style** is a self-contained folder under
`styles/` that knows how to turn a beat plan into frames. Adding one is a
filesystem operation — no code in this skill changes.

```bash
R=skills/production-designer/scripts/registry.py

python3 $R list                  # styles, aliases, and the ranking vocabulary
python3 $R show paper            # what it is good at, what it needs
python3 $R rank "<topic>"        # which style suits this subject
python3 $R doctor [style]        # are its dependencies actually installed
```

## Shooting a film in a style

Three steps, all driven by the style's own entrypoints:

```bash
python3 $R show <style>          # prints the exact commands for that style
```

1. **`compile`** — beat plan → that style's storyboard. It produces a *draft
   that renders*: the timing, layout and camera are mechanical and it gets them
   right; the taste is yours. Open the result and cut what is decorative.
2. **Edit the storyboard.** This is the actual design work.
3. **`render`** — storyboard → video. Check a contact sheet before committing to
   a full render; it is seconds instead of minutes, and it shows collisions and
   pile-ups that a single frame hides.

### Unless the production chose a different renderer

`entrypoints.render` is the style's *own* renderer, and it is the default —
but it is not the only one. If `production.json` carries a `renderer`, step 3
is carried out by that skill instead, and `director.py next` prints a `RENDER`
block saying which and what changes.

```bash
python3 $R list                  # marks styles that have opted in
```

Steps 1 and 2 are unchanged: **the storyboard is renderer-neutral.** That is
the whole reason one renderer can serve every style — it consumes the same
artifact the style's own renderer does.

A style opts in by listing ids in `style.json`:

```json
"renderers": ["remotion"]
```

Only list a renderer that can actually draw this style. The entry records a
port someone has done, not an intention, and the director refuses the flag
rather than planning a render that cannot happen.

## The rule that matters most

**A style never invents a picture.** When a beat asks for something the style
cannot draw, it emits a *labelled placeholder* and reports it. It does not
substitute the nearest thing it has.

This is not fussiness. A documentary that shows the wrong building, or a stock
crowd standing in for a real one, is making a false claim in pictures. Every
placeholder is a decision for a human: draw it, rephrase the beat, or change
style.

## Choosing

`rank` scores each style's declared `strengths` and `avoid` against the topic,
using a **closed vocabulary** (`registry.py list` prints it). It penalises an
`avoid` match harder than it rewards a strength, because the cost of the wrong
style is a wasted render.

When the top two are close, it says so rather than picking. Ask the human.

Ties break alphabetically, which means `flat` wins over `news` and `paper`. That
is deliberate and worth keeping: when the ranking cannot tell the styles apart,
the boldest-coloured one is the safer default, because the failure mode viewers
actually complain about is a film that looks washed out, not one that looks too
saturated.

### Colour is not optional

No style may deliver a film that reads as grey or brown. This has been the
single most repeated note from viewers across every review round, and each time
the cause was a *default* rather than a decision:

- the palette reached the renderer as one `ink`, so every drawing in a film was
  the same colour;
- the paper stocks were beige at 5–53% saturation, and the stock is the largest
  area of every frame;
- scenery was painted in the film's darkest ink, and scenery is the largest area
  after the stock — so four different places in one film were four identical
  near-black rectangles.

Each fix was correct and none of them was sufficient alone, because the
*next*-largest surface was still colourless. When checking a new style, measure
the areas in descending order and make sure each one carries hue.

## Adding a style

A style is a **skill of its own**, named `style-<id>`. It declares
`provides_style` in its `crew.json` and carries a `style.json` beside it, plus
the entrypoints that manifest names; `registry.py doctor <id>` tells you what is
missing. Nothing else in the plugin needs editing — the registry discovers
whichever style skills are installed.

The contract, field by field, with a worked example:
[`reference/style-contract.md`](reference/style-contract.md).

A style skill's own documentation lives with it, so it costs nothing here until
that style is actually chosen. Keep style documentation there, not in this
skill.

## Styles available now

| id | good for | avoid |
|---|---|---|
| `paper` · aliases `paper-explainer`, `collage`, `documentary` | history, disaster, investigation, science, business — anything archival | software demos, screen recordings, live action |
| `flat` · aliases `vector`, `mid-century`, `upa`, `saul-bass`, `modernist` | essays, thrillers, sport, fiction, title sequences — anything that should be bold rather than archival | product demos, screen recordings, text-heavy films |
| `news` · aliases `broadcast`, `bulletin`, `newsroom`, `report` | journalism, investigation, business, disaster — anything that should read as reporting | comedy, gaming, screen recordings, product demos |
| `stock` · aliases `footage`, `b-roll`, `pexels`, `live-action`, `cinematic` | real places, cities, travel, business, sport, nature, true-crime atmosphere, reportage — anything where real photography beats illustration | fantasy, talking characters, a specific named person, precise invented objects, screen recordings |

Details: [`style-paper`](../style-paper/SKILL.md) ·
[`style-flat`](../style-flat/SKILL.md) ·
[`style-news`](../style-news/SKILL.md) ·
[`style-stock`](../style-stock/SKILL.md).

`stock` is the only style that **downloads its pictures instead of drawing
them**, so it alone needs a network key (`PEXELS_API_KEY`) and it alone can
fail to find a shot. It never invents footage: an unfindable beat becomes a
labelled placeholder and the stage exits non-zero.

`paper` and `flat` **share a compiler and an engine** and differ only in the
look, so the same storyboard renders in either. That makes them the pair to
reach for when a film's look is in question: compile once, render both, and
choose from the two contact sheets rather than from a description.

```bash
python3 style-paper/scripts/compile.py beat-plan.json --motion-plan mp.json -o sb.json
python3 style-paper/scripts/render.py sb.json --sheet -o paper.jpg
python3 style-flat/scripts/render.py  sb.json --sheet -o flat.jpg
```

### Default to `flat`

**When the brief does not name a style, render `flat`.** Both were built to the
same board and shown side by side; `flat` was chosen, and the reason is
measurable rather than a matter of taste. On the same story `paper` rendered at
**mean saturation 0.19 around hue 53°** — brown — because its stock, its inks
and its texture all pull toward newsprint, and every one of those surfaces has
to be fought to hold colour. `flat` rendered the same board at **0.62 around
181°**. It starts colourful and stays colourful.

Reach for `paper` when the *archival* quality is the point — a film about
documents, evidence, or the past, where looking like aged newsprint is doing
narrative work. Otherwise the colourful style is the better default, and a film
that comes out grey or brown by accident is a bug, not a mood.


This table is a convenience, not the source of truth — `registry.py list` reads
the filesystem, so it is right even when this is stale.
