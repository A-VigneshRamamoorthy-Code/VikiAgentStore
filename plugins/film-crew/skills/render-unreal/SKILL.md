# Unreal render unit

An alternative picture pipeline for film-crew. The board is unchanged; only the
photography changes. Flat artwork is stood up as textured planes in a real 3D
set and photographed by a camera that moves through it, so parallax and camera
travel are produced by optics rather than by scaling layers on a canvas.

Runs entirely headless. No editor UI, no C++ module, Blueprint-only project.

---

## Why you would choose it

A compositor fakes depth by scaling and offsetting layers. That is cheap,
predictable, and completely correct for a locked-off shot. The moment the
camera moves, though, a compositor has to be *told* how much each layer should
slide, and getting a whole film's worth of those numbers to agree is fiddly.

Put the layers at real distances and the problem disappears: push the camera in
and near layers grow faster than far ones because that is what perspective
does. You buy that for a heavier, slower render.

Use it for camera-led films. Stay with the style's own renderer for
locked-off, graphic, poster-like work — Unreal has nothing to offer there.

---

## The shape of a job

```
cast_board.py   storyboard + timeline + casting  ->  scene.json
build_scene.py  scene.json                       ->  .umap + LevelSequence
ue.sh render    the sequence                     ->  PNG frames
encode.py       frames + mix.wav                 ->  mp4
```

`cast_board.py` runs outside Unreal and makes every decision. `build_scene.py`
runs inside and makes none — it only creates assets and keys channels. The
split matters because the compiler is the half you iterate on and it runs in
milliseconds, while anything that imports `unreal` costs an editor launch to
test.

```bash
S=~/.copilot/installed-plugins/VikiAgentStore/film-crew/skills/render-unreal/scripts
U=~/.copilot/skills/unreal-animation/scripts

python3 $S/cast_board.py storyboard.json film.mixed.timeline.json casting.json -o scene.json

python3 $U/new_project.py ~/UEProjects/Film                       # once
UEA_SCENE=$PWD/scene.json UEA_MAP=/Game/Maps/Film UEA_SEQ=/Game/Seq/SEQ_Film \
  bash $U/ue.sh py ~/UEProjects/Film/Film.uproject $S/build_scene.py

bash $U/ue.sh render ~/UEProjects/Film/Film.uproject \
     /Game/Maps/Film /Game/Seq/SEQ_Film /tmp/render 1920 1080 30 1.0

python3 $S/encode.py /tmp/render film.mp4 --fps 30 --audio meta/mix.wav
```

---

## Two ideas do all the work

**Bays.** Every shot gets a private copy of its set, parked `BAY_STRIDE` apart
on X. Nothing is shared between shots, so there are no visibility tracks to
key, two settings can never share a frame, and one shot's staging cannot leak
into another. Cuts are hard, so the camera teleporting between bays is
invisible. A 51-shot film becomes 51 independent problems.

**A camera per shot.** A camera that only lives in one shot cannot interpolate
across a cut, which removes the one-frame smear you get where a shot's last key
meets the next shot's first. Cameras are free.

Both trade a bigger scene for the removal of an entire class of silent failure.

---

## Verify the stage before you shoot on it

Three constants can each be wrong in a way that renders perfectly cleanly:
the plane's roll, the direction texture V runs, and which way the camera reads
X. A mirrored film looks *fine* until you notice everyone faces the wrong way.

```bash
python3 $S/orient_test.py /tmp/orient
# then build and render /tmp/orient/scene.json exactly as above
```

It stages labelled artwork whose correct orientation is unambiguous. One frame
settles it:

| symptom | cause |
| --- | --- |
| labels upside down | `PLANE_ROLL` inverted |
| text reads backwards | camera yaw mirrored (`+90` instead of `-90`) |
| wedge points down | texture V runs the other way |
| pure black | a material was not saved before capture |

Verified on UE 5.8 / macOS: `PLANE_ROLL = 90`, camera yaw `-90`, textures land
upright, and `facing: -1` mirrors correctly via negative X scale.

---

## Flat art needs the camera switched off

Unreal's default filmic tone curve is built for photographic latitude and it
mangles flat fills. Measured on this pipeline, a `(240,186,70)` yellow came
back as `(220,134,95)` — desaturated, with blue pushed up, and the whole frame
darkened.

`spawn_camera` therefore overrides `tone_curve_amount`, `expand_gamut`,
`blue_correction`, bloom, vignette, film grain, fringe and motion blur to zero,
and locks exposure. The render becomes a faithful compositor rather than a
camera. **Do not re-enable the tone curve to "make it look filmic"** — grade
afterwards instead, where it is reversible.

Materials are unlit (the artwork carries its own shading) and translucent
rather than masked, because masked cutouts turn every anti-aliased edge into a
staircase. Translucency's sorting problem is handled by setting an explicit
`translucency_sort_priority` per plane, back to front.

---

## Warm-up frames are not all black

The capture writes a variable number of warm-up frames. The dangerous one is
not the black frame, it is the *second* one: on this pipeline frame 0 is black,
**frame 1 contains the backdrop but none of the translucent cast**, and only
frame 2 onward is correct. Anything trimming on "first non-black" ships a film
whose opening frame has no characters in it.

`encode.py` therefore uses two signals — the difference to the next frame, and
a collapse in "ink" coverage — and trims to whichever says warm-up. Dropping an
extra frame costs 1/30th of a second; keeping a bad one ruins the opening.

It prints its reasoning. Read it, and override with `--start` if a film
genuinely opens on an empty frame, which this heuristic would trim.

---

## Modular characters

Many of the best free 2D characters ship as a rig — loose limbs plus a skeleton
file — which is useless to a renderer that wants one sprite. `db_compose.py`
flattens a DragonBones rig into a single PNG by evaluating it the way the
runtime would.

```bash
python3 $S/db_compose.py magician_DB_ske.json wizard.png
python3 $S/db_compose.py magician_DB_ske.json walk.png --anim walk --frame 8
python3 $S/db_compose.py rig_ske.json out.png --hide cape,hat
```

Mesh displays are warped per triangle from their own vertices and UVs. Treating
a mesh as a plain image is exactly how a rig's skirt or cape comes out as a
giant undeformed blob — if you see one, that is what happened.

Bone timelines cover translate, rotate and scale. IK and mesh *deformation*
timelines are ignored, so a rig that leans on them returns bind pose.

---

## The casting file

`cast_board.py` needs a `casting.json` binding the board's symbolic names to
real files:

```json
{
  "sets": {
    "attic": { "layers": [
      { "file": "art/attic_far.png",  "depth": 1400 },
      { "file": "art/attic_mid.png",  "depth": 700 },
      { "file": "art/attic_near.png", "depth": 200, "cover": 1.1 }
    ]}
  },
  "actors": { "emma":  { "file": "art/emma.png", "depth": 0 } },
  "props":  { "book":  { "file": "art/book.png", "base_h": 260 } }
}
```

`depth` is distance behind the action plane, and it is the only thing that
creates parallax — layers at the same depth move together no matter how they
are drawn. Actor `height` in the board is a percentage of frame height; prop
`scale` multiplies the prop's own `base_h`.

Missing entries are reported as warnings and the shot is built without them,
so a compile that "succeeds" with warnings has holes in it. Read them.

---

## Non-negotiables

1. **Look at the frames, not the log.** Unreal reports success while writing
   black images.
2. **Look-test before a full render.** One held frame per shot, tiled, catches
   nearly every look bug in two minutes instead of an hour.
3. **Re-run `build_scene.py` after any casting change.** Rebuilding respawns
   cameras with new GUIDs and stales the sequence bindings.
4. **Never key a transform channel without seeding all nine.** An unkeyed
   channel evaluates as `0.0`, so animating one axis silently zeroes rotation
   and scale. `transform_section()` seeds from the live transform; use it.
5. **Check `/tmp/ue_build_result.json`.** A wrong `.uproject` path exits 0
   having done nothing.
