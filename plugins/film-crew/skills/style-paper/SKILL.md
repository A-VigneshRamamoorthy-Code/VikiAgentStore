---
name: style-paper
description: >
  Archival-collage documentary visual style for production-designer:
  deterministic ffmpeg/Python rendering from JSON storyboards, generated
  paper textures, illustrations, music and SFX. Narration comes from
  voice-booth. Use for paper-collage explainers, documentary stories,
  Vox-style motion graphics or narration over procedural visuals as a style module.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.3.0"
---

# Paper Style

Make a narrated video that looks like a documentary researcher's pinboard: aged
paper, torn photographs, typewriter labels, and one red pen.

This is the `paper` style of the `production-designer` skill. It defines
what the video looks and sounds like, and ships a renderer that produces it.
Hooks, retention structure and virality are a separate concern.

**It is self-contained.** Everything it needs to make the video — the renderer,
the fonts and their licences, the music and SFX synthesis, a worked example —
lives in this folder. Copy the folder anywhere and it runs. The only external
requirements are `ffmpeg`, `python3`, and the two packages in
`scripts/requirements.txt`. Narration audio is the one thing it does not make;
supply it from the [`voice-booth`](../voice-booth/) skill.

---

## Golden rules

1. **Never cut.** The reference style has *zero* scene cuts. One continuous
   board; rhythm comes from elements arriving on it, not from editing. If you
   feel the urge to cut, add an element instead.
2. **The camera travels between beats.** Author a `camera.moves` path, one move
   per beat, with a `hold` so it settles before travelling on. A single slow
   push across the whole piece measures as movement but feels frozen.
3. **Paper has thickness.** Every torn edge shows a pale fibrous core, every
   scrap has an `elevation` that drives its cast shadow, and light always comes
   from the upper left. Flat silhouettes are what make a collage look like
   vector art instead of paper.
4. **Nothing is ever still.** Give every scrap a small seeded `float`. Subjects
   arrive with `"anim": "fly"` — lifted, so their shadow contracts as they land.
   When narration dwells on one image for more than a few seconds, add a `sway`
   so the *image* breathes instead of panning the camera across it.
5. **One red.** Red is reserved for hand annotation — boxes, circles, routes,
   arrows, underlines. Never for artwork, never for a second accent. Everything
   else lives in warm desaturated sepia.
6. **Chips land on the word.** A keyword chip must appear on the syllable it
   names, within about +0.3 s. Author beats against narration line ids, never
   against wall-clock guesses.
7. **Narration is an input.** This skill does not synthesise speech. Generate
   it with the [`voice-booth`](../voice-booth/) skill and reference one clip per
   line; the renderer measures those clips and derives the whole timeline from
   them.
8. **Write the audio first.** The renderer measures narration *before* laying
   out a single frame, so timings survive a rewrite of the script.
9. **Score the genre, not the emotion.** Pick `music.mood` from the story type:
   `music_box` for a children's story, `crime` for an investigation or an
   attack, `memorial` for a tribute, `warm` for a personal essay, `tension` when
   nothing else fits. Reportage about an atrocity is a *crime* story, not a
   funeral — the piece is asking what happened. See
   [audio-style.md](reference/audio-style.md) for the full table.
10. **Nothing is imported.** All texture, artwork and sound is generated. A
   storyboard plus this skill reproduces the video byte-for-byte on any machine.

---

## Rules that do not bend

Everything above is guidance you can weigh. These are not. Each one is a
defect a viewer reported on a finished film, and each is now **checked by the
compiler**, which refuses the board rather than emitting one that breaks them.
If you are tempted to work around one, you have found a bug in the fix, not an
exception to the rule.

1. **The camera never shakes.** Not on impact, not for emphasis, not "just a
   little". A shake reads as a mistake in a film made of paper. Where you want
   force, use a *slow pan* — a longer, heavier move into the subject with a
   long hold on the end of it. This is enforced twice: the compiler emits no
   `camera.shake`, and the renderer discards one if a hand-written board
   supplies it anyway.
2. **A scene starts clean.** When the story moves to a new place, the previous
   place *leaves* — every drawing from scene *k* is retired as scene *k+1*'s
   setting lands. Never let two places share a frame, and never let a new scene
   be built on top of the old one. Overlapping two settings is the single most
   confusing thing this style can do.
3. **Nothing new on screen means no camera move.** If a beat draws the same
   things as the beat before it, the camera has been given nothing to look at,
   and moving anyway produces the low-level churn that viewers report as
   "shaky" even when no shake exists. The camera parks.
4. **A parked camera is never a still frame.** Whatever the camera stops
   looking at must keep breathing — a slow `sway` of roughly ±1–2% of frame
   width, with a ~3% scale pulse, over an 8–12 second period. Long enough that
   nobody can point at it; large enough that the shot is alive. This is the
   trick limited animation is built on: *move the artwork, not the camera*.
5. **Colour is not optional.** A film that renders grey or brown is a bug. The
   largest surface in the frame decides the film's colour, so check the stock,
   then the scenery, then the cards — in descending order of area — and make
   sure each one carries hue from the film's own palette rather than a module
   default. See [art-direction.md](reference/art-direction.md).
6. **Nothing is drawn on top of anything else.** Placement is decided per beat
   and cannot see what an earlier beat left standing, so the compiler resolves
   collisions on the finished board: it pushes subjects apart, and where the
   frame has no room it draws the newcomer smaller, and failing that retires
   the older one. Two drawings from different beats sharing pixels is a
   blocking defect, not a style. Only two things are exempt, and both are
   narrow: a **ground**, which is meant to be stood on, and an **attachment**
   — a flame on its lantern, a chair beside its figure. Two *actors* are never
   exempt, not even in the same beat and not even on different depth planes;
   that is how a boat came to be drawn inside a trawler and a figure's head
   inside a hull.
7. **Two places never share the frame at the same size.** A beat may bring in
   a second setting — standing on a hilltop and looking out to sea — but it
   goes to **distance**: scaled down, lifted to the held ground's shoulder,
   and pushed behind it, carrying its own cast with it. Two full-size grounds
   is two horizons, and it is what makes a staircase appear to stand in open
   water.
8. **Everything is on top of something.** A person needs land under them, a
   hull needs water under it, and neither may be moved off it to resolve a
   collision. What they stand on is the **drawn silhouette**, not the bounding
   box, and each ground has its own measured profile (`staging.SURFACE`): a
   hill is a cosine whose peak reaches only 80% of its box, the sea is flat, a
   staircase is level then falls away. That profile settles both the usable
   width — a prop clamped only to the box floats out past the hillside — and
   the *height*, because after anything is moved sideways it must be re-seated
   onto the surface at its new x, or it keeps the height it had at the summit
   and hangs in the sky. Never re-derive this curve by eye; read it from the
   table, and make any check read it too. The renderer must also *draw* each
   element at the size the compiler placed — a drawing scaled to 62% of the
   slot it was seated by hangs above the ground by the difference, and no
   amount of correct storyboard geometry will show it.
9. **A caption is never occluded.** Chips are lifted into a reserved z band
   above every drawing. A chip is deliberately held past its own beat so it
   can be read, which means later beats routinely lay artwork over the top of
   it — measured on a 37-beat board, seven captions were buried this way.
10. **Height is distance.** Up the frame means further away, so it settles
    depth as well as position: a boat floating higher than a shoreline's base
    is drawn *behind* the land, never across it. Water is not land for this
    purpose, or the boat disappears behind its own sea.
11. **A drawing made of words has a minimum size.** Sizes are handed out by
    role, and a chart beside an actor is only a "prop" — which took a timeline
    designed at 520 px wide down to 173 px and made its dates unreadable. A
    lettered drawing is grown back to reading size, and may be moved but never
    shrunk to resolve a collision.
12. **The ground outlives whoever stands on it.** Casting land into a beat is
    only half of rule 8: a hillside that is retired while the figure standing
    on it stays draws exactly the same frame — a person on open sea — for
    exactly the same reason. Every ground is held until the last actor
    standing on it has left.
13. **Nothing appears for less time than it takes to appear.** Retiring a
    drawing to resolve a collision can leave it a tenth of a second of life
    against a half-second entrance, and the renderer will happily freeze it
    part-way in: translucent, offset, its cut-out edge not yet opaque. Against
    a dark field that is a colourless smear — reported as "the ship is grey",
    a colour defect whose cause contains no colour. Entrances are compressed
    to fit, and a drawing too brief even for that is dropped.
14. **A flame belongs at the wick.** An attachment — flame, halo, smoke — is
    drawn small at an anchor on its host. Compose it with its host and that is
    automatic, but light a lantern *across a beat boundary* and the flame
    arrives as an independent drawing, gets seated on the ground like scenery,
    and burns out of the lantern's foot instead of inside its glass. Stray
    attachments are re-anchored last, after everything that could move the
    host. They are exempt from ground seating and from the legibility floor,
    because they stand on their host and are meant to be small. An attachment
    also inherits its host's exit: a flame that outlives its lantern is a
    flame burning in mid-air, and hand-over staggering changes host schedules
    after the flame has been placed.
15. **A beat hands over with a cut, not a dissolve.** A newcomer's `in.t` is
    set to the outgoing drawing's `out.t`, which is a cross-fade — for the
    third of a second it lasts, both are on screen and both readable, and if
    they share a patch of ground that is the "last scene overlaid on the new
    scene" defect. It cannot be fixed by moving things apart, because the two
    are *meant* to be in the same place. Where their boxes collide, the
    outgoing fade is cut to a 0.15 s wipe and the newcomer waits for it;
    everywhere else, dissolves are left alone so the film still flows.
    **A drawing is on screen until `out.t + out.dur`, not until `out.t`** —
    measure lifetimes any other way and every hand-over becomes invisible to
    the geometry *and* to the checks. And because a fade makes two acts'
    grounds coexist, "the ground under this" must mean the one it shares the
    most time with, not the first one found. The two drawings meet in either
    order and both orders are the same defect: a new act's ground often
    starts fading *in* before the old act's figure begins to leave, and since
    that ground is drawn on a higher layer — it must be, to cover the act it
    replaces — the hillside slides over the person. Nothing can be delayed
    there, so the departure is pulled forward instead. And a ground that
    arrives above drawings still playing beneath it has no hand-over partner
    at all — it simply covers them — so its own fade is the defect and is cut
    to a wipe. Retiring what it covers is a false economy: forcing those
    drawings out invents fresh cross-fades of the very kind being removed.
    Two drawings of the **same illustration** are always a hand-over wherever
    they sit, boxes touching or not: a lantern at the foot of the hill and the
    same lantern on the summit are at opposite ends of the frame, and showing
    both at once reads as two lanterns rather than one that was carried up.
16. **A drawing that travels arrives somewhere it could have stood.** A drift
    is what makes a figure *climb* the stairs instead of cutting from the foot
    to the top, and it is the whole answer to "show them walking from one
    place to another". But it is a delta, and every other rule here reads
    `at` — where the drawing *starts*. Measured on the two boards, **1 of 2
    and 10 of 10** travelling drawings arrived off the frame or off the
    ground; one figure finished 29 px above the top of the board and spent
    four seconds as a pair of legs sliding along the top edge, having passed
    every check, because where it started it was perfectly placed. A drift's
    destination is seated exactly as its start is, and landed last, because
    everything above it can still move `at`.
18. **A ground carries only the things that belong on it.** Grounds are exempt
    from the overlap check on purpose — a hill is *meant* to have a figure
    standing on it — but that exemption was written as "a ground never
    collides", which is one word too broad. Measured at t=42 on the lab board:
    a new beat's hill spanning x=[250,1670] landed at 41.85 over a trawler at
    x=[994,1570] that the previous beat had put on open water and that ran
    until 45.78. Both fully opaque, nothing dissolving, every other check
    clean — and on screen, a fishing boat parked on a hillside for four
    seconds. **7 such leftovers on the lab board, 3 on the regression board.**
    An arriving ground hands over too: whatever was already standing there and
    does not belong to it is gone *by* the time it lands, not fading out as it
    fades in — retiring on the arrival itself only trades a leftover for a
    cross-fade. Held scene backdrops are not arrivals; things standing in
    front of them is the point.
17. **A word on screen is a word inside the frame.** Captions are placed in
    stage space, but the camera decides what is *in* the frame, and the two
    had never been checked against each other: act-change swings lean a flat
    `0.18 × W` with no framing check at all, unlike motion-plan moves, which
    are clamped. Measured, **3 of the lab board's moves and 35 of the
    regression board's** pointed away from a caption that was on screen —
    "THE ROCKS" rendered as "ROCKS". A move that would cut a caption is eased
    out and then aimed back until the words fit; the camera gives way, not
    the writing. A caption counts as on screen for the legible part of its
    fade, not to the last frame of it, so the camera is not dragged around by
    a word at a tenth opacity.


Rules 3 and 4 are one idea seen from two sides, and together they are what the
reference film does that a naive board does not: **the camera holds still and
the world moves.** Reversing that — a busy camera over frozen artwork — is what
makes a limited-animation film feel cheap instead of deliberate.

---

## Quick start

```bash
cd scripts
python3 -m pip install -r requirements.txt        # pillow, numpy

python3 render.py ../examples/template/storyboard.json
```

Narration audio is **not** produced here. Generate one clip per line with the
[`voice-booth`](../voice-booth/) skill and point the storyboard at them:

```jsonc
"narration": [
  { "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.75 }
]
```

To block a board out before the narration exists, give a line `duration`
instead of `audio` and it reserves silent time. The renderer warns when it does.

Useful modes while you iterate:

```bash
python3 render.py sb.json --sheet          # 4x5 contact sheet, ~17s — use this
python3 render.py sb.json --frame 12.4     # one PNG at t=12.4s
python3 render.py sb.json --clip 320 336   # full-res silent range — judge motion
python3 render.py sb.json --motion 320     # estimate the motion check in ~1 min
python3 render.py sb.json --preview        # half-res -> sb_preview.mp4
python3 render.py sb.json --audio-only     # rebuild the mix, keep the frames
python3 render.py sb.json                  # picks a worker count for this machine
python3 render.py sb.json -j 2             # force fewer, when memory is tight
python3 render.py sb.json --hw             # encode on the media engine, not x264
```

**Feature-length renders are parallel by default.** The film is cut into
contiguous segments, and each worker composes *and encodes* its own segment to
its own file; the parts are joined without re-encoding and the audio is laid
over once at the end. Segment boundaries are computed from the running time and
frame rate alone — never from the worker count — so every value of `-j`
produces a byte-identical file. That is verified, not assumed: `-j 1` and `-j 4`
render the template to the same SHA-256.

**More workers is not better, and the default already knows that.** Each worker
carries its own copy of the board, its own transform cache and its own encoder,
so workers cost memory rather than sharing it. Measured on a 4+4-core, 8 GB
machine over the same 3,568 full-resolution frames: one worker 379 s, two 220 s,
four 155 s, eight 318 s. Eight is slower than two, and kernel time over the run
grows seven-fold — the machine stops rendering and starts paging. `-j 0` (the
default) therefore picks from the *fast* core count and the memory ceiling,
not from `os.cpu_count()`, and honours a container's cgroup limits. Override it
with an explicit `-j` only to go lower. See
[`reference/performance.md`](reference/performance.md).

**Always check `--sheet` before a full render.** It costs seconds instead of
minutes and catches every layout problem.

**A contact sheet cannot tell a pan from a cut.** Camera work has to be judged
with `--clip`, and judged on the *shape* of its difference profile — a smooth
hump is a pan, an isolated spike is a jump.

**`--audio-only` remuxes a new mix into an existing render** with `-c:v copy`,
so a music-level or duck change costs ~90 s instead of a full re-render. Only
the audio may have changed — regenerate the storyboard first and confirm the
duration and element counts still match.

**Finished renders are never overwritten.** If `output.path` exists the renderer
writes `name-002.mp4`, `name-003.mp4`, … and says so. Pass `--force` only when
you really do want to replace one.

---

## The workflow

The director's pipeline reaches this style at the `compile` stage, holding a
style-neutral
[`beat-plan.json`](../storyboard-artist/reference/beat-plan.md).

1. **Get the narration audio.** One clip per line, from the
   [`voice-booth`](../voice-booth/) skill.
2. **Compile the beat plan into a storyboard draft:**

   ```bash
   python3 scripts/compile.py beat-plan.json -o storyboard.json
   python3 scripts/compile.py beat-plan.json --check     # report only

   # with an animation director's motion plan — strongly preferred
   python3 scripts/compile.py beat-plan.json -o storyboard.json \
           --motion-plan motion-plan.json
   ```

   Without a motion plan the compiler gives **every** beat the same camera
   move. That measures as motion and reads as wallpaper: on a 37-beat test
   film its loud beats averaged 1.802 and its quiet beats 1.785, a separation
   of 1.009. With a plan the same board scored 1.558. See
   [`animation-director`](../animation-director/).

   A plan changes four things: held beats lose their camera move entirely and
   the previous rest is stretched to cover them; `impact` beats get a decaying
   shake; each surviving move is pushed as hard as *its own composition*
   allows; and entrances on quiet beats soften from `stamp`/`fly` to short
   fades, because 57% of an undirected film's runtime is the collage
   assembling itself.

   It gets the mechanical things right — the timing, a four-quadrant layout that
   cannot collide, retiring each beat before its quadrant is reused, and a
   camera that leans toward the live beat without throwing the rest out of
   frame. It does not get the taste right. **Open the result and edit it**: cut
   what is decorative, give the beats that matter more room.

   It also stages each beat as a *scene* rather than a lone cutout, holds one
   background per act, moves anything the narration says travels, fills
   diagrams with the story's real acts and times, and picks the palette, mood,
   ambience and effects from the story itself — see
   [`reference/art-direction.md`](reference/art-direction.md).

   > **An explicit `music` block in the beat plan suppresses story-driven
   > scoring.** That is correct when you want control and a silent trap when
   > you copied the block from another film. If every film you compile sounds
   > identical, this is why.

   It exits non-zero when a beat asks for a picture this style has no
   illustration for. That is not a failure to work around — see the golden rule
   below. Resolve every placeholder before rendering.

3. `--sheet`, look, fix, repeat.
4. Full render, then verify duration, loudness and motion.

Boarding by hand instead? Skip step 2 and write the storyboard directly; the
format is the same and [`reference/storyboard-reference.md`](reference/storyboard-reference.md)
documents every field.

### The one rule this style will not bend

**It never invents a picture.** The illustration catalogue is fixed, and
`compile.py` reads it straight out of `render.py` so the two cannot drift. When
a beat asks for something not in it, you get a labelled `[ART: …]` placeholder
and a note — never the nearest lookalike.

A documentary that shows the wrong building is making a false claim in
pictures, and it does it silently. Either add the illustration to
`illustrations.py`, rephrase the beat toward something the catalogue has, or
tell the director this style is wrong for the film.

---

## Reference

Load only what you need — that is the point of the split.

| Doc | Read it when |
|---|---|
| [`visual-style.md`](reference/visual-style.md) | palette, materials, typography, layout grammar, motion, the no-cut rule |
| [`art-direction.md`](reference/art-direction.md) | **what is on screen and where**: scene staging, held backgrounds, journeys, diagrams with real data, story-chosen colour |
| [`audio-style.md`](reference/audio-style.md) | the narration input contract, music beds and moods, paper SFX, ducking, mastering |
| [`storyboard-reference.md`](reference/storyboard-reference.md) | the complete JSON schema — every element type, field and time syntax |
| [`authoring-guide.md`](reference/authoring-guide.md) | turning a script into a board that reads: composition, collisions, arc |
| [`architecture.md`](reference/architecture.md) | what each module owns, the pipeline order, how to extend it |
| [`verification.md`](reference/verification.md) | the ship checklist and the exact commands |
| [`matching-a-reference.md`](reference/matching-a-reference.md) | making output measurably match a reference film |
| [`troubleshooting.md`](reference/troubleshooting.md) | **first stop when anything looks wrong** |

Working example:

- [`examples/template/`](examples/template/) — a neutral 22.9 s board that
  exercises every element type and motion device in the spec. Its narration
  clips live in `examples/template/vo/`, generated by the
  [`voice-booth`](../voice-booth/) skill. Copy it and replace the copy.

---

## Verify before you ship

Four numbers, all cheap to check. Full commands in
[`verification.md`](reference/verification.md).

| Check | Expected |
|---|---|
| Format | 1920×1080 @ 30, `yuv420p` |
| Loudness | **−14 LUFS**, true peak ≤ −1 dBFS — the render meters the delivered AAC and prints it |
| Clipping | 0 samples |
| Motion | mean frame difference **≈ 2.5**; below ~1.5 it is a slideshow |

If loudness is off, **the mix is wrong — do not fix it by re-encoding.**
