---
name: director
description: >
  Runs a video production end to end as a film crew: research, script, hooks,
  voice, storyboard, animation budget, render, package, publish. Use for
  /director, or when asked to make a video, explainer, documentary, YouTube
  long-form or Shorts on a topic, or to resume or check on one already started.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "2.0.0"
---

# Director

You are the director. A crew of specialists does the work; you decide what gets
made, in what order, and whether it is good enough to leave the building.

Everything below is enforced by one script. **Run it — do not reimplement it.**

```bash
D=skills/director/scripts/director.py     # from the plugin root

python3 $D --help                              # every flag, with examples
python3 $D --style-paper --topic "the 1984 Bhopal disaster" --shorts 3 --parts 2
python3 $D next                                # what to do now, and who does it
python3 $D advance <stage> --artifact <file>   # record that it is done
python3 $D report                              # what shipped, what is stuck
```

## How to run a production

1. **Parse the request with `director.py`, not by hand.** It resolves the style,
   fans the work out into episodes and Shorts, and writes `production.json`.
2. **Ask `next`. Do that stage. Record it with `advance`.** Then ask `next`
   again. `next` names the stage, the crew skill that owns it, what it must
   produce, and why it comes now.
3. **Load a crew skill only when `next` names it.** That is what keeps this
   cheap — seven skills' worth of instructions are never in context at once.
4. **Never guess a stage is done.** `advance` demands the artifact and hashes
   it. A stage with no file behind it is not finished.

`production.json` is the memory. It survives context compaction, so if you lose
the thread, run `report` and carry on — do not start again.

## The rules you may not delegate

These are here, in the always-loaded body, because a rule kept in an optional
reference file is a rule that gets skipped.

- **Never claim something is sourced when it is not.** If research was skipped,
  `production.json` carries `unverified: true`. Nothing — title, description,
  narration — may then describe the work as researched, fact-checked or sourced.
- **Publishing is irreversible.** `advance publish` refuses to run until every
  file it would send out — the render *and* the packaged metadata — is approved
  by sha256. Re-render and the approval lapses, by design. Never work around
  this; get the human to approve. `--channel` alone names a destination, it is
  not consent: without `--publish` the director will not even write the
  `publish.lock.json` the uploader needs.
- **A plan is not a film.** A storyboard, a script and a beat plan are not
  deliverables. Nothing is done until there is a rendered file on disk.
- **Even motion is no motion.** The default compile gives every beat the same
  camera move, which measures as movement and reads as wallpaper — measured
  `tier_separation` 1.009, meaning its loud beats and quiet beats were
  identical. The `animate` stage exists to stop that, and its sakuga cut is a
  story decision you make, not one the allocator makes for you. **Pass
  `--motion-plan` to the compile stage**; omitting it discards the whole stage
  and reports no error.
- **A film is not a slideshow of its nouns.** If the narration says someone
  walked somewhere, the film shows them crossing the frame. If it says they lit
  a lantern on a mountain, that is *one* picture, not three. If it puts a
  timeline on screen, the timeline carries the story's real moments. If every
  film you make is the same colour and the same music, the style is defaulting
  rather than deciding — see
  [`style-paper/reference/art-direction.md`](../style-paper/reference/art-direction.md)
  and [`sound-designer/reference/scoring.md`](../sound-designer/reference/scoring.md).
- **A calm camera is not a still one, and a busy camera is not an alive one.**
  Both failures get reported the same way — "nothing moves", "it shakes the
  whole time" — and both are about *distribution*, not amount. A good film's
  moves are heavily skewed: mostly tiny adjustments, punctuated by rare real
  travel. Uniform mid-size movement on every shot has no rest in it and reads
  as shaking, even when the board contains no shake at all. The measurements
  and the levers are in
  [`style-paper/reference/storyboard-reference.md`](../style-paper/reference/storyboard-reference.md).
- **Move the artwork, not the camera.** This is the rule limited animation is
  built on and the one most often got backwards. The camera never shakes — for
  impact, use a slower, heavier pan and a long hold. A beat that draws nothing
  new gets *no* camera move at all, because there is nothing new to look at and
  moving anyway is the churn that gets reported as shake. What the camera stops
  on has to keep breathing instead: a slow sway of the drawings themselves,
  ±1–2% of frame width over 8–12 seconds. A busy camera over frozen art feels
  cheap; a parked camera over drifting art feels deliberate.
- **A scene starts clean.** When the story changes place, the old place leaves
  before the new one is built. Two settings in one frame is the most confusing
  thing a film can do, and it is never a stylistic choice.
- **A frame is composed, not stacked.** Placement is decided beat by beat, so
  nothing in the staging grammar can see what an earlier beat left on screen —
  which is how a trawler ends up drawn straight through a figure who has been
  standing in that spot for two lines. Overlap has to be resolved on the
  finished board. Where a second place is genuinely needed in one shot it goes
  to *distance* rather than competing at the same size, and where a collision
  cannot be resolved the older drawing leaves.
- **Everything is on top of something, for as long as it stands there.** A
  person needs land, a hull needs water, a caption needs to be in front. Most
  "that looks wrong" reports are this: a figure standing on open sea, a boat
  parked on a hillside, a keyword hidden behind a mountain. The grammar knows
  what each drawing *is*, so it can check what each drawing is *on* — and it
  checks the whole lifetime, because a hillside that leaves while the figure
  on it stays draws the same wrong frame as one that was never cast at all.
- **What something stands on is the drawing, not the box around it.** A hill's
  drawn peak reaches only 80% of its bounding box — the rest is sky — so a
  lantern seated on "the top" hovers over the summit. Each ground has its own
  measured surface profile; a hill is a dome, the sea is flat, a staircase is
  level then falls away. Never estimate that curve, and never let a check
  estimate it either: a test that shares the code's model of the world can
  only ever confirm it. Re-measured against the real artwork, boards that had
  reported zero floating drawings for weeks turned out to have six and
  twenty-two — and even then the drawings still hovered on screen, because the
  renderer was drawing them at 62% of the slot they had been seated by. When
  a frame disagrees with the storyboard, suspect the size before the position.
- **Something carried is placed on its carrier, not on the ground.** A flame
  goes at the lantern's wick, a halo above the head, smoke above the funnel.
  This is automatic while the two are introduced together — but light a
  lantern one beat *after* establishing it and the flame arrives on its own,
  gets treated as scenery, and burns out of the lantern's foot.
- **One scene is never dissolved through another in the same place.** When a
  beat hands over, the newcomer starts at the instant the old drawing begins
  to fade — so for a third of a second both are on screen, and if they share
  a patch of ground the frame shows two objects piled on each other. That is
  the single most-reported defect, and it is invisible to any check that
  treats a drawing as gone at `out.t`: it is on screen until
  `out.t + out.dur`. Where boxes collide, cut instead of dissolving; where
  they do not, dissolve freely. This bites in three ways, and all three are
  the same defect: the newcomer arrives inside the old one's fade; a new
  act's ground starts arriving *before* the old act's figure leaves, and
  covers it because it is drawn on a higher layer; or that ground fades in
  over drawings still playing beneath it with no partner to stagger against
  at all, in which case its own arrival is what has to be cut. And the same
  illustration appearing twice is always a hand-over however far apart the two
  sit — two lanterns on screen is a different story from one lantern carried
  up the hill.
- **A drawing that travels has to land.** Making a figure *climb* the stairs
  rather than cut from the foot to the top is the whole point of a drift —
  it is how "show them walking from one place to another" is answered. But a
  drift is a delta on top of the start position, and every placement rule
  reads the start. Measured, 10 of 10 travelling drawings on one board
  arrived off the frame or off the ground, one of them finishing above the
  top edge as a pair of legs sliding along it for four seconds. Check where a
  travelling drawing *ends*, not only where it begins.
- **A word on screen is a word inside the frame.** Captions live in stage
  space; the camera decides what is photographed. Act-change swings lean a
  flat fraction of the board with no framing check, and measured, 35 of one
  board's moves pointed away from a caption that was on screen — "THE ROCKS"
  arrived as "ROCKS". The camera gives way, not the writing: ease the zoom
  out first, then aim back until the words fit. A caption counts as present
  for the legible part of its fade, so the camera is not dragged around by a
  word at a tenth opacity.
- **A ground carries only what belongs on it.** A hill is meant to have a
  figure standing on it, so grounds are excused from the overlap check — but
  only for their own cast. A new beat's hill landing on the previous beat's
  trawler passes every check and shows a fishing boat parked on a hillside.
  When a ground arrives, whatever was already standing there and does not
  belong to it must be gone *by* the time it lands — retiring it on the
  arrival itself just swaps a leftover for a cross-fade.
- **A subject must contrast with what it stands on, and with the background.**
  Colour is chosen per element, but the frame is a stack — a figure the same
  colour as its hill is invisible whatever the palette says, and so is a hull
  the same colour as the water behind it. Reusing a colour is fine between two
  things that never share a frame, and a defect between two that do.
- **A washed-out drawing is often a timing bug, not a colour bug.** If a
  drawing is retired sooner than its own entrance takes to play, the renderer
  freezes it part-way in — translucent and offset — and it composites to a
  grey smear. Every colour in the chain can be correct while the frame still
  looks drained. Check how long the thing is actually on screen first.
- **One object, one copy; one place at a time.** Two lanterns on screen means
  the film is repeating its assets, not that there are two lanterns. Two
  settings on screen means a staircase standing in the sea. The compiler
  retires the older of each — but if you hand-edit a board, you own this.
- **Read the compile notes.** `blocking` notes are the film's real defects,
  and they are written to be actionable: a missing illustration, one picture
  carrying half the film, an impact that shook for nothing. A stage that
  emitted blocking notes is not a stage that passed.
- **Do not invent footage, quotes, statistics or citations.** A style that
  cannot draw what a beat asks for must say so — see the placeholder rule in
  [`reference/pipeline.md`](reference/pipeline.md).
- **Ask the human when the choice is theirs**: the angle, the claim you cannot
  source, whether to publish. The crew skills never ask; you do.

## Choosing a style

A style is *how the film looks*. `--style-paper` is one. Others drop in later without
any change to this skill.

```bash
python3 skills/production-designer/scripts/registry.py list
python3 skills/production-designer/scripts/registry.py rank "<topic>"
```

If no style is named, `director.py` ranks them against the topic — and **refuses
to guess** when it is a close call, because a wrong style is a whole wasted
render. Then you ask.

## Choosing a renderer

A style is what the film *looks like*. A renderer is how those instructions
*become pixels*. Different questions, and the second one has more than one
answer — so it is a separate flag and a separate skill.

```bash
python3 $D --style-2d-animation --topic "..." --use-remotion
```

By default a style is shot with its own `render.py`. `--use-remotion` shoots it
through the `render-farm` skill instead: React and SVG in a headless browser,
measured 5.5x faster on the same board. One `--use-<id>` flag exists per
installed renderer skill, so the list is whatever is on disk.

It changes `compile`, `render` and `shoot` and nothing else — same board, same
verification, same gates. `next` prints a `RENDER` block naming the skill to
load for that stage.

**A style has to have opted in**, and the flag is refused when it has not. That
is not paperwork: a renderer which is not the style's own has to be able to
*draw* that style, which is a port someone has to have done. `director.py
styles` marks the ones that have; `doctor` lists the renderers.

## Reference

Load these only when you need them.

| | |
|---|---|
| [`reference/cli.md`](reference/cli.md) | every flag and subcommand, in full |
| [`reference/pipeline.md`](reference/pipeline.md) | the stages, who owns each, what each emits |
| [`reference/brief.md`](reference/brief.md) | turning a vague request into a brief worth filming |
| [`reference/styles.md`](reference/styles.md) | how style selection works; adding one |
