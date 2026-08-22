# Choosing a style

A **style** is how the film looks. It is a folder under
`production-designer/styles/`, and the director never hard-codes any of
them — styles are discovered from the filesystem, so one added tomorrow works
without changing this skill.

```bash
R=skills/production-designer/scripts/registry.py

python3 $R list              # what is installed, with aliases
python3 $R show paper        # what it suits, what it needs, how to drive it
python3 $R rank "<topic>"    # score every style against a subject
python3 $R doctor            # are their dependencies actually installed
```

---

## How a style gets chosen

**Named explicitly.** `--paper`, or `--style paper`. Aliases resolve too, so
`--style documentary` and `--style paper-explainer` both land on `paper`.

**Ranked from the topic.** With no style given, the director scores each style's
declared `strengths` and `avoid` against the topic.

Two deliberate asymmetries:

- An `avoid` match is penalised (−4) more heavily than a `strength` is rewarded
  (+3). The cost of the wrong style is a whole wasted render, so the ranker is
  built to reject rather than to enthuse.
- When the top two are within 3 points, or the best score is not positive, the
  director **stops and asks** instead of picking. A style chosen by a coin flip
  is worse than a question.

---

## The vocabulary

Ranking uses a closed list of terms — `registry.py list` prints it. Styles
declare `strengths` and `avoid` from it.

A term outside the vocabulary is **inert, not an error**. The style still works;
it just gets no ranking signal from that term. A typo should cost a signal, not
break the registry.

---

## What a style owes the pipeline

Two entrypoints, and one promise.

| entrypoint | does |
|---|---|
| `compile` | beat plan → this style's own storyboard |
| `render` | storyboard → video |

The promise: **a style never invents a picture.** If a beat asks for something it
cannot draw, it emits a labelled placeholder and reports it, rather than
substituting the nearest thing it has.

Every placeholder is a decision for a human — draw it, rephrase the beat, or
change style. A documentary that shows the wrong building is making a false
claim in pictures, and it does it silently.

---

## Installed now

### `paper`

Aliases `paper-explainer`, `collage`, `documentary`.

An archival paper board: parchment ground, torn-paper collage, condensed keyword
chips, hand-drawn red annotation, a synthesised score and a broadcast-standard
mix.

**Good for** history, disaster, investigation, science, business — anything
where the evidence is documents and the mood is archival.

**Wrong for** software demos, screen recordings and anything needing live
action. It has no way to show a user interface, and it will tell you so rather
than approximate one.

### `news`

Aliases `broadcast`, `bulletin`, `lower-third`, `newsroom`, `report`.

A rolling news bulletin: full-bleed picture under a stacked white kicker bar and
red headline bar, a channel bug bottom-left and a location chip bottom-right.
Name straps for people, astonishers for figures, list builds and split
comparisons.

**Good for** journalism, investigation, business, disaster — anything that
should carry the authority of reporting. It is the only style that also renders
`9:16` and `1:1`, so a Short can be shot in it directly rather than cropped.

**Wrong for** comedy, gaming, screen recordings and product demos. Bulletin
furniture makes light material look like a hostage tape.

---

## Adding a style

Drop a folder in `styles/`. Nothing else changes.

The full contract:
[`../../production-designer/reference/style-contract.md`](../../production-designer/reference/style-contract.md).

`styles/<id>/STYLE.md` is deliberately not registered as a skill, so a style's
documentation costs nothing in context until that style is chosen. This is the
main reason the plugin can carry many styles without getting heavier.
