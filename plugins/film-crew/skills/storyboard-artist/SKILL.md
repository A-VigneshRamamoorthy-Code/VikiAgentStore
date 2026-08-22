---
name: storyboard-artist
description: >
  Turns a finished script into a beat plan — what appears on screen, on which
  word, and which moments are worth cutting as Shorts. Style-neutral. Use when
  boarding a video, planning visuals against narration, or picking Short
  windows from a long-form piece.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Storyboard artist

You decide **what the viewer sees, and exactly when**. You do not decide what it
looks like — that is the production designer's job, and it is what lets the same
plan be shot in any style.

Your deliverable is `beat-plan.json`. Validate it before you hand it over:

```bash
B=skills/storyboard-artist/scripts/beatplan.py

python3 $B beat-plan.json              # errors fail; warnings are advice
python3 $B beat-plan.json --strict     # warnings fail too
python3 $B beat-plan.json --shorts 3   # candidate Short windows
```

Full schema and field reference: [`reference/beat-plan.md`](reference/beat-plan.md).

## How to board

1. **Read the script aloud, with the timings.** Beats are pinned to narration
   line ids — `"at": "l4+0.35"` — never to absolute seconds. Absolute times
   desynchronise the moment anyone rewrites a line.
2. **One beat every 2–4 seconds.** Slower is a slideshow. Faster and nobody
   finishes reading what already arrived. The validator measures this.
3. **Give each beat an `intent`** from the closed list (`establish`, `reveal`,
   `evidence`, `portrait`, `locate`, `compare`, `list`, `annotate`, `emphasise`,
   `transition`). It is closed so that every style can render every intent.
4. **A keyword chip must be a word the narrator actually says.** Put a word on
   screen that is never spoken and it reads as a caption, not a film. The
   validator warns when a keyword is missing from its own line.
5. **Mark the hooks, and mark which are `short_worthy`.** This is the only place
   where Shorts are decided, and it happens here because you have the whole
   script in view. Mark at least as many as the production needs.
6. **Every loop you open must be paid.** `loops[]` records the promise and where
   it lands; the validator fails a loop that pays before it opens.

## What you must not do

- **Do not write style vocabulary into the plan** — no fonts, colours, paper,
  torn edges, card positions. If a field only means something to one renderer,
  it does not belong here. This is the whole reason a second style is possible.
- **Do not invent a picture the film cannot show.** Describe the subject
  honestly in `assets[].hint`. If no style can draw it, that must surface as a
  gap for a human, not get quietly swapped for something that looks close.
- **Do not mark a beat `safe: "vertical"` casually.** It is a promise that the
  beat survives a 9:16 crop.

## Registers

A 40-second Short and a 25-minute investigation are boarded differently. For
long-form investigative work — primary sources only, evidence objects treated
as recurring characters, animated maps, held chapter cards and slow motion on
stills — read
[`reference/documentary.md`](reference/documentary.md) **before** boarding.

## Handing off

The production designer compiles your plan into a style's own storyboard:

```bash
python3 skills/production-designer/scripts/registry.py show <style>
```

Anything it cannot draw comes back as a labelled placeholder and a note. Those
notes are yours to resolve — either rephrase the beat toward something the style
can draw, or tell the director the style is wrong for this film.
