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

Details: [`style-paper`](../style-paper/SKILL.md) ·
[`style-flat`](../style-flat/SKILL.md) ·
[`style-news`](../style-news/SKILL.md).

`paper` and `flat` **share a compiler and an engine** and differ only in the
look, so the same storyboard renders in either. That makes them the pair to
reach for when a film's look is in question: compile once, render both, and
choose from the two contact sheets rather than from a description.

```bash
python3 style-paper/scripts/compile.py beat-plan.json --motion-plan mp.json -o sb.json
python3 style-paper/scripts/render.py sb.json --sheet -o paper.jpg
python3 style-flat/scripts/render.py  sb.json --sheet -o flat.jpg
```


This table is a convenience, not the source of truth — `registry.py list` reads
the filesystem, so it is right even when this is stale.
