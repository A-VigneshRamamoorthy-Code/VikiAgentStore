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
python3 $D --paper --topic "the 1984 Bhopal disaster" --shorts 3 --parts 2
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
- **Everything is on top of something.** A person needs land, a hull needs
  water, a caption needs to be in front. Most "that looks wrong" reports are
  this: a figure standing on open sea, a boat parked on a hillside, a keyword
  hidden behind a mountain. The grammar knows what each drawing *is*, so it
  can check what each drawing is *on*.
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

A style is *how the film looks*. `--paper` is one. Others drop in later without
any change to this skill.

```bash
python3 skills/production-designer/scripts/registry.py list
python3 skills/production-designer/scripts/registry.py rank "<topic>"
```

If no style is named, `director.py` ranks them against the topic — and **refuses
to guess** when it is a close call, because a wrong style is a whole wasted
render. Then you ask.

## Reference

Load these only when you need them.

| | |
|---|---|
| [`reference/cli.md`](reference/cli.md) | every flag and subcommand, in full |
| [`reference/pipeline.md`](reference/pipeline.md) | the stages, who owns each, what each emits |
| [`reference/brief.md`](reference/brief.md) | turning a vague request into a brief worth filming |
| [`reference/styles.md`](reference/styles.md) | how style selection works; adding one |
