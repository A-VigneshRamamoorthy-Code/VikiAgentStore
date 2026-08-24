---
name: style-2d-animation
description: >
  2D character animation for production-designer: rigged characters that
  actually perform — solved and drawn per frame from joint angles, with weight,
  squash and stretch, anticipation and comic holds — staged in soft, desaturated
  air on locked-off compositions that hold. Calibrated against measured
  reference films and graded by `lookcheck.py`: a pale, low-chroma world with a
  single saturated figure in it, long takes, few cuts. Animates on twos, renders
  16:9 and 9:16, and works narrated or wordless. Use for comedy, character-led
  explainers, adverts and any story where someone has to *do* something.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# 2D character animation

The other styles in this crew arrange pictures. This one makes a character do
something.

That is the whole difference, and it is not a small one. `paper`, `flat` and
`news` are **board styles**: they place artwork on a surface and move a camera
over it. Their people are silhouettes — `illustrations.figure()` draws a figure
standing to attention, and it will still be standing to attention in the last
frame of the film. When the story needs someone to run, panic, drive badly or
calmly eat a sandwich while being pursued by six police cars, none of them can
help you.

Here a character is a **rig**: fifteen joints solved from angles and drawn fresh
every frame. It can be posed, blended, mirrored, scaled and made to carry weight.

---

## Golden rules

1. **Animate on twos.** Character poses are evaluated at 15 drawings a second
   and held. Backgrounds, parallax and the camera stay on ones. This one
   decision accounts for about a third of whether the result reads as
   hand-crafted or as an auto-tween — and getting the *split* wrong is worse
   than getting neither, because a camera on twos reads as dropped frames.
2. **This style *can* cut — and mostly shouldn't.** It is a shot list, not a
   single board, so a cut is available where `style-paper` forbids one. But the
   films this style is calibrated against cut **5.2 and 0.0 times a minute**
   — one of them has no cuts at all in 83 seconds. The default grammar is a
   locked-off camera holding a long take while something moves *inside* the
   frame. Use `intent: "observe"` for that; it is the only intent that leaves
   the camera alone without dragging an overlay in with it. Reach for a cut
   when the story genuinely changes place or time, and let the mist, the
   traffic or the performance carry everything else.
3. **The world is pale; the figure carries the colour.** Mean saturation across
   the whole frame sits at **0.05–0.15**, and no more than **4.5%** of pixels
   may exceed 0.35 saturation. That budget is almost exactly one character. A
   set painted in confident colour spends the entire allowance on scenery and
   the person stops reading as the subject. Desaturate with distance —
   `look.depth_tint` exists for this — and let the figure be the only saturated
   thing on screen.
4. **Nothing fast starts or stops without easing.** Fast departure, overshoot by
   8–15% — the shipped curve is 12% — then settle. Not ease-in-out, and never
   linear: a linear tween between two poses is the clearest possible tell of a
   generated film, and `shots.py` refuses `linear` on a moving camera outright.
   (The one exemption is the `creep` ease — a constant-rate drift on a long
   static shot, exempt because it must *not* be perceived.)
5. **The hold is the joke.** After a gag, the picture stops for 20–36 frames.
   Cutting away on the punchline is the most common timing mistake in comedy
   animation. The hold is where the laugh goes.
6. **A held pose is not a still frame.** Underneath every hold the character
   breathes and blinks every 72–96 frames — which means driving the actor at
   `rate: 0.33`, because `stand` blinks once per three-second cycle. Without
   that, a hold reads as a crashed render — the same lesson `style-paper`
   learned as "move the artwork, not the camera".
7. **A planted foot never slides.** The foot is fixed in scene space and the
   pelvis travels over it. Sliding feet are the loudest tell of procedural
   animation there is — and the board can cause them on its own, so make `to`
   agree with `poses.stride_units`.
8. **Contact shadows, always.** A low-opacity ellipse under everything on the
   ground, at 30.6%. Its absence is the most jarring depth error available in
   flat 2D — a character without one is a sticker on a backdrop.
9. **No black outlines, and one gradient in the whole film.** Every body outline
   is derived from its own fill — same hue, more saturated, 40% darker;
   `#000000` reads as clip art. Flat colour otherwise: shading is another flat
   shape. The single exception is a two-stop linear sky, and
   `look.sky_gradient` is the only function permitted to make one.
10. **Three-fingered mittens.** Real fingers destroy the silhouette at this size.
11. **The face carries the acting.** At the scale these films play at, an
    audience reads the silhouette and the brows. Spend the budget there, not on
    the elbows.

The full numbers behind all eleven are in
[`animation-principles.md`](reference/animation-principles.md).

---

## Quick start

```bash
S=skills/style-2d-animation

python3 $S/scripts/compile.py beat-plan.json -o sb.json \
        --motion-plan motion-plan.json          # always pass the plan
python3 $S/scripts/render.py sb.json --sheet    # contact sheet first, always
python3 $S/scripts/render.py sb.json -j 0       # the film
```

The same beat plan shoots either aspect — `--aspect` is the only thing that
changes, and beats marked `"safe": "vertical"` are the ones staged to survive
the crop:

```bash
python3 $S/scripts/compile.py beat-plan.json -o short.json \
        --motion-plan motion-plan.json --aspect 9:16
```

Narration is **not** produced here. Generate one clip per line with
[`voice-booth`](../voice-booth/) and point the board at them — or leave
`narration` out of the board entirely and make a wordless film scored to music
and SFX, which this style supports and the board styles do not.

Useful while iterating:

```bash
python3 $S/scripts/render.py sb.json --frame 12.4   # one PNG
python3 $S/scripts/render.py sb.json --clip 20 28   # judge motion, full res
python3 $S/scripts/render.py sb.json --preview      # half-res
python3 $S/scripts/render.py sb.json --motion 24    # mean frame difference
python3 $S/scripts/render.py sb.json --audio-only   # remux a new mix
python3 $S/scripts/render.py sb.json --self-test    # -j 1 vs -j 4, by SHA-256
```

A finished render is never overwritten — an existing `output.path` becomes
`name-002.mp4`. Pass `--force` when you mean to replace one.

**Always look at the contact sheet before rendering.** It costs seconds and
catches the two things a single frame cannot show: a character drifting out of
frame across a shot, and two actors standing in the same place.

---

## Where it fits

The director's pipeline reaches this style at `compile`, holding a style-neutral
[`beat-plan.json`](../storyboard-artist/reference/beat-plan.md).

```
board → animate → compile → render
        (motion-plan.json)   ↑ you are here
```

It consumes a motion plan (`"motion_plan": 1`) and maps the animation director's
five tiers into its own vocabulary — which for once is literal rather than
metaphorical, because this style really is spending drawings:

| tier | here |
|---|---|
| `hold` | held drawing on threes, breathing and blinks only |
| `limited` | held character, slow push, background parallax |
| `full` | the character acts, the camera travels, on twos |
| `sakuga` | on ones, full body, smears — the one cut that earns it |
| `impact` | on twos, but the frames within ±2 of the contact go on ones, then a hard hold |

## Good for, wrong for

**Good for** comedy, character-led explainers, adverts, chases, fiction — any
story with someone in it who does something.

**Wrong for** journalism, investigation and disaster. Not because it cannot draw
them, but because it should not: a rigged cartoon character trivialises an
atrocity, and the style declares those in its `avoid` list so the ranker steers
away from them rather than leaving it to taste.

Also wrong for screen recordings, live action and text-heavy material, for the
same reason as every other style here — it has no way to show a user interface
and will say so rather than approximate one.

---

## The one rule this style will not bend

**It never invents a picture.** The set, prop, cast and action catalogues are
fixed. When a beat asks for something not in them, `compile.py` emits a labelled
placeholder, reports it and exits non-zero — it does not substitute the nearest
lookalike.

Either add the set or prop, rephrase the beat toward something the catalogue
has, or tell the director this style is wrong for the film.

---

## Reference

Load only what you need.

| Doc | Read it when |
|---|---|
| [`animation-principles.md`](reference/animation-principles.md) | **the numbers** — exposure, easing, anticipation, squash, smears, holds, and the twelve ways this looks cheap |
| [`rig.md`](reference/rig.md) | the skeleton, the pose format, and every module's exact contract |
| [`storyboard-reference.md`](reference/storyboard-reference.md) | the complete board schema — shots, actors, camera, overlays, time syntax |
| [`comedic-timing.md`](reference/comedic-timing.md) | building a gag: setup, anticipation, snap, hold |
| [`audio-style.md`](reference/audio-style.md) | music, cartoon SFX, the diegetic `radio` voice filter, the mix |
| [`verification.md`](reference/verification.md) | the ship checklist and the exact commands |

Working examples:

- [`examples/summit/`](examples/summit/) — the **calibration film**, and the
  one to copy. A **79 s** wordless comedy: a climber conquers a misty peak and
  the weather slowly clears to reveal that he is standing in a car park. Four
  shots, **three cuts in the whole film**, one locked-off composition, no
  camera move anywhere. Every frame is kept alive by drifting mist rather than
  by cutting, which is the mechanism the reference films use. It is the only
  example that passes `lookcheck.py`.
- [`examples/pursuit/`](examples/pursuit/) — a **78 s** narrated comedy: a news
  helicopter reports a high-speed police pursuit, and the pictures quietly
  disagree with every word of it. Twenty-five shots, mean 3.1 s, 19.3 cuts a
  minute, eleven of them held. It exercises cuts, a sakuga cut, comic holds,
  vehicles, parallax, chyrons and a diegetic narrator — but it is deliberately
  **off-reference**, and `lookcheck.py` fails it on all five metrics. Keep it
  for the machinery it demonstrates; do not copy its grammar.

---

## Verify before you ship

| Check | Expected |
|---|---|
| Format | 1920×1080 @ 30 `yuv420p` (1080×1920 for a Short) |
| Loudness | −14 LUFS, true peak ≤ −1 dBFS |
| **Look** | **`lookcheck.py film.mp4` exits 0 — all five metrics inside the measured reference envelope** |
| Motion | mean frame difference above `verify.motion_mean_min` (1.2) in `style.json` |
| Tier separation | `motionprofile.py` against the plan — well above 1.0 |
| Determinism | `render.py --self-test`: `-j 1` and `-j 4` agree by SHA-256 |

`lookcheck.py` is the one that catches a film which is technically perfect and
still looks nothing like the style:

```bash
python3 scripts/lookcheck.py out/film.mp4
python3 scripts/lookcheck.py out/film.mp4 --reference some_reference.mp4
```

It grades saturation, saturated area, brightness, cut rate and frame-to-frame
difference against numbers **measured from the reference films**, not chosen —
they are recorded in `style.json → verify.look`, and running the tool on the
references themselves passes. Note that frame difference is a *range*: the
ceiling stops a film thrashing, and the floor stops it freezing. That floor is
what makes `intent: "observe"` safe, since an `observe` shot opts out of the
camera-creep rescue on the promise that its set moves on its own.

Commands in [`verification.md`](reference/verification.md).
