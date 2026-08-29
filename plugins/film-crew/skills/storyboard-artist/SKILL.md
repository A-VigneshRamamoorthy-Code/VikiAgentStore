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

## Continuity across shots

A beat plan is read one beat at a time and rendered one beat at a time, so
nothing in the pipeline compares a beat with the one before it. That makes
continuity **your** job, and two errors in particular survive all the way to a
finished film because every individual shot is defensible.

### Where a character is at the end of a shot is where they start the next one

If shot A walks someone from 0.24 to 0.40 across the frame and shot B opens
with them at 0.24 again, the audience sees them snap backwards and then walk
over ground they already covered. It is one of the few defects viewers report
in plain language — *"the character is already there and then walks there
again"* — and it is invisible in any single frame, any contact sheet, and any
per-shot check.

Audit it as a sequence, per character, per set:

```python
last = {}                                   # (character, set) -> x they ended at
for shot in shots:
    for who, start, end in blocking(shot):
        prev = last.get((who, shot.set))
        if prev is not None and abs(start - prev) > 0.02:
            print(f"{shot.id}: {who} jumps {prev:.2f} -> {start:.2f}")
        last[(who, shot.set)] = end
```

Then fix it by **continuing the move**, not by shortening it: keep the travel
distance the shot was written for and slide both ends along. A search that ran
0.28 → 0.46 after the previous shot left the character at 0.42 becomes
0.42 → 0.60.

A flagged jump is not automatically wrong. Deliberate scene breaks — the
character leaves and returns later — should jump, and those are the ones to
leave alone. The audit exists to make you decide, not to be silenced.

### A camera cannot pan somewhere it has no picture for

`cx` and `cy` are fractions of the plate, and the viewport is `1/zoom` wide, so
a camera centred at `cx` needs

```
zoom  >=  1 / (2 * min(cx, 1 - cx))
```

to stay on the plate. A pan out to `cx = 0.30` therefore demands `zoom >= 1.667`
whatever else the shot wants.

**Asking for a bigger canvas does not help**, and this is worth internalising
because it is the first thing everyone tries. Bake the plate at `K` times the
size and the renderer rescales the board's zoom to `z/K` over a plate `K` times
wider; both sides of the inequality scale together and the constraint is
unchanged. It is a statement about *fractions of the picture*, not about
pixels.

What makes this bad is not the constraint but **where renderers enforce it**.
The usual implementation silently raises zoom on whichever frames overshoot,
so a shot that is legal at its start and illegal at its end zooms normally,
then lurches as the clamp engages, then lurches back. Viewers describe it as
*"the video suddenly moves a bit"* and blame frame drops. On one shot here the
clamp pumped between 1.10 and 1.667 and cropped away 52% of the picture.

So: **board a pan the shot can actually hold.** Either keep `cx` inside
`1 - 1/(2·zoom)`, or accept a tighter lens for the whole shot — one constant,
decided once, is always better than a correction applied per frame. Ask the
renderer to raise on overscan rather than clamp, so an impossible move is a
loud failure at compile time instead of a wobble in the delivered file.

## Registers

A 40-second Short and a 25-minute investigation are boarded differently. For
long-form investigative work — primary sources only, evidence objects treated
as recurring characters, animated maps, held chapter cards and slow motion on
stills — read
[`reference/documentary.md`](reference/documentary.md) **before** boarding.

## Handing off

Your plan goes to the animation director first, who decides how much motion
each beat gets, and then to the production designer, who compiles both into a
style's own storyboard:

```bash
python3 skills/animation-director/scripts/framebudget.py beat-plan.json \
        -o motion-plan.json
python3 skills/production-designer/scripts/registry.py show <style>
```

The `emphasis` and `intent` you set on each beat are what the animation
director allocates against — a beat plan where everything is `emphasis: 0.5`
gives it nothing to work with and produces a flat film. Make the important
beats visibly more important than the rest.

Anything it cannot draw comes back as a labelled placeholder and a note. Those
notes are yours to resolve — either rephrase the beat toward something the style
can draw, or tell the director the style is wrong for this film.
