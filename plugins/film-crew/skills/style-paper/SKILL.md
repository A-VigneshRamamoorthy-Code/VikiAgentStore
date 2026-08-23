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
