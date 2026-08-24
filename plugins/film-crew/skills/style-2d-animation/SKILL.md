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

## Characters: drawn art, solved motion

There are two ways to build a character here, and picking the wrong one is why
the earlier films looked the way they did.

| | Python rig | **Peeps rig** (`remotion/`) |
|---|---|---|
| Art | drawn in code from shapes | **real CC0 illustration** for the head |
| Motion | posed per beat | solved from a path by `locomotion.js` |
| Use for | boards, crowds, background action | **anything the audience looks at** |

The Python rig draws everything from primitives. That is fine at distance and
it is what the board pipeline uses. It is also why `wetpaint` came out as
sparse stick-figure doodles and `pursuit` filled its frames with tiny generic
people whose art drifted between shots — nobody had drawn them, so nothing held
them together.

The Peeps rig fixes the two causes separately:

- **Identity comes from artwork.** Heads, faces, beards and accessories are
  Open Peeps — 172 committed CC0 assets by Pablo Stanley — composed through
  real per-hairstyle offsets. Bodies are rigged to match that ink weight, and
  every colour in a shot comes from **one pack**, so two characters cannot
  quietly end up with different blacks.
- **Motion comes from physics.** Facing and stride phase are *derived* from
  where the body goes. They cannot be authored, so they cannot disagree with
  it.

```bash
cd remotion && npm install

npx remotion still src/index.jsx RigPortrait /tmp/rig.png   # judge the rig
npx remotion still src/index.jsx RigTest     /tmp/walk.png  # judge the walk
npx remotion render src/index.jsx SecondThoughts out/film.mp4 \
    --concurrency=4 --pixel-format=yuv420p --color-space=bt709
npx remotion render src/index.jsx Crosstown out/humaaans.mp4 \
    --concurrency=4 --pixel-format=yuv420p --color-space=bt709

node ../scripts/check-physics.mjs        # MUST pass before you render
```

Four style packs ship. Three — `ink-street`, `dusk-park`, `flat-poster` — are
Open Peeps in different worlds; they share the rig and change the world, which
is what makes a run of films look like a series instead of a pile.

### The second art library: Humaaans

`humaaans-city` is the fourth, and it is a different thing: a whole second
CC0 library (Humaaans, also by Pablo Stanley — 47 committed assets) with its
own rig, `Humaaans.jsx`, and its own film, `Crosstown`.

It is a separate rig on purpose. Humaaans' legs are **56%** of standing height
against the Peeps rig's **43%**; forcing this art onto those proportions gives
a squat figure with a long back, which is exactly the "the assets don't match"
failure this skill exists to prevent. So the geometry is bespoke — but the
**physics is shared**. `Humaaans.jsx` imports `GAITS`, `footOffset`, `gaitAt`
and `strideAt` from the same `locomotion.js`, so the rig and the solver cannot
disagree about when a foot is planted.

Two things that are easy to get wrong when adding a third library, both of
which were live bugs here:

- **`GAITS.lift` is a length, not a ratio.** It is measured in Open Peeps
  character space (hips at 392). Handed unscaled to a figure whose hips are at
  225, it asks for a foot lift of a third of the figure's own height, and the
  run reads as hurdling. Scale dimensional gait values into your rig's space;
  `duty`, `bodyLean` and `heel` are ratios and angles and port unchanged.
- **There ARE leg assets, and you still cannot use them.** `bottom/` ships 8
  standing and 4 sitting pieces, but each is a single frozen silhouette of
  *both* legs in one path — there is no joint in there to drive from the
  solver's phase. So legs are drawn procedurally and the assets are used as a
  **ruler** instead: sampling their outlines gives ~47–52 units across a thigh
  narrowing to ~36, ~108 across the pair, and a 61×21 shoe. Guessing those
  numbers instead produced legs half again too wide with 82-wide shoes on the
  end — a figure standing on two navy slabs.
- **A pack is a look, and that includes line weight.** These sets draw their
  outlines as a copy of each shape in ink, sitting a few pixels proud. Humaaans
  artwork has no outlines at all, so `humaaans-city` sets `world.rim: false`
  and every rim collapses into its own fill. Without it the buildings wear an
  ink halo the cast does not have, and the frame reads as two films spliced
  together.

> **Render `HumaaansBench` after any change to `Humaaans.jsx`.** It stands the
> artist's own composition — head, body and a real `bottom/` asset stacked at
> the `layout.json` offsets, no rig involved — next to the rig standing and
> mid-stride, over shared hip and shoulder rules. `RigTest` asks "does the walk
> hold together"; this asks the earlier question, "is this figure shaped like
> the thing the artist drew". They are not the same check, and skipping this
> one is exactly how the legs got too big: every frame was individually
> defensible and the figure was still wrong.

> **Render `RigTest` after any change to `Character.jsx`.** A walk is wrong in
> ways a single frame hides and a moving picture hides even better — the eye
> forgives a great deal at 30fps. The bench lays the cycle out flat and
> compares it against itself.

Details: [`assets.md`](reference/assets.md) and [`physics.md`](reference/physics.md).

### About the asset source you were probably given

**magnific.com is Freepik**, and its content cannot be bundled here. Terms
§8.1(3)–(4) forbid including it in "a database, archive or … library, for
distribution" and forbid sublicensing; §2 forbids scripted access. This is a
public MIT repository, so committing it would do both.

`scripts/fetch_assets.py` refuses those hosts before any network call and
prints the governing clause. Use CC0 sources, or use Freepik art locally under
your own licence — not in the repo.

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

   In the reference the figure measures **sat 0.236** against an environment
   averaging **0.067**, and supplies **9.4%** of the frame's entire saturation
   from **4.1%** of its pixels. A bare figure cannot do that, so the accent
   lives in what it *wears*: `"hat"` and `"pack"` on an actor dress it with a
   coloured beanie or brim and a daypack. Both are off unless asked, and both
   also buy an asymmetric silhouette that reads in profile at a distance.
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
7. **A planted foot never slides, and nobody ever walks backwards.** Both follow
   from one rule: **facing and stride phase are derived from where the body
   goes, never authored.** Phase integrates from *distance travelled*, so a
   character who slows down takes fewer steps instead of skidding; facing is
   the sign of velocity, so moonwalking is unrepresentable. `wetpaint` shipped
   a figure gliding backwards out of shot because one line read `local > tOut ?
   !facing : facing` — "leaving means facing the other way". It does not.
   Use `solveLocomotion`, and let `check-physics.mjs` prove it.
8. **Contact shadows, always.** A low-opacity ellipse under everything on the
   ground, at 30.6%. Its absence is the most jarring depth error available in
   flat 2D — a character without one is a sticker on a backdrop.
9. **Something must pass in front of the cast.** Depth in a flat drawing is
   overlap, and overlap only reads if scenery occludes the actors as well as
   sitting behind them. Street furniture also belongs *upstage* of the acting
   line — higher on the plate, slightly smaller — but at the **same parallax
   depth**, because it is standing on the same pavement. Buying depth by
   slowing a layer to 0.95 makes the furniture slide along the ground it is
   bolted to, and parks a lamppost behind the lead's head for seconds at a time.
10. **Generate the set from the camera, never as a fixed array.** A hand-listed
    row of trees is a set with an edge, and anyone who walks far enough will
    reach it. Emit only the tiles the camera can see, seed each tile from its
    own index so it doesn't reshuffle, and give trees, lampposts and benches
    periods that disagree (815 / 937 / 1783) so they don't stack up.
11. **No black outlines, and one gradient in the whole film.** Every body outline
    is derived from its own fill — same hue, more saturated, 40% darker;
    `#000000` reads as clip art. Flat colour otherwise: shading is another flat
    shape. The single exception is a two-stop linear sky, and
    `look.sky_gradient` is the only function permitted to make one.
12. **Three-fingered mittens.** Real fingers destroy the silhouette at this size.
13. **The face carries the acting.** At the scale these films play at, an
    audience reads the silhouette and the brows. Spend the budget there, not on
    the elbows.

The full numbers behind them are in
[`animation-principles.md`](reference/animation-principles.md); the motion
rules are enforced by [`physics.md`](reference/physics.md).

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

### Rendering somewhere bigger

A full-resolution film is the only expensive stage here, and it parallelises
per frame, so it is worth offloading to a rented machine. `stage-render.sh`
builds the payload for [`azure/compute`](../../../azure/skills/compute/):

```bash
bash $S/scripts/stage-render.sh /tmp/payload
python3 plugins/azure/skills/compute/scripts/azc.py offload \
  --profile render --hours 1 --push /tmp/payload \
  --cmd "cd skills/style-2d-animation && python3 scripts/render.py board.json -j 0 -o out/film.mp4" \
  --pull :skills/style-2d-animation/out --dest ./out
```

Staging is not optional and not just tidiness. `audio.py` loads the mixer from
**`style-paper`** by relative path, on purpose, so one fix reaches both styles
— which means a payload containing only this skill renders **silently** on a
bare machine. That is the compute skill's classic missing-font failure in its
cross-skill form. `stage-render.sh` ships the sibling and preserves the
directory layout so the import still resolves.

The `render` profile already carries ffmpeg, Pillow and numpy.

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
| [`physics.md`](reference/physics.md) | **motion** — why facing is derived, why the pelvis sinks, why a gait is a dial; and the validator that enforces all of it |
| [`assets.md`](reference/assets.md) | **art** — what is bundled, why Freepik is not, how a character is assembled, and the two staging rules for sets |
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

## Rendering this style with Remotion

This style ships a Python renderer, and that is the supported way to make a
film with it. There is also a **second, faster picture pipeline** available:
the [`render-farm`](../render-farm/SKILL.md) skill renders a board through
Remotion — React and SVG in a headless browser — and it is style-agnostic, so
it is not specific to this style.

The measurement was made on this style's pursuit board, which is why it is
worth knowing here: **5.5× faster in wall clock**, at **2.3% mean masked
difference** from the Python render of the same board. Nothing is redrawn — a
recording pen captures `sets.py`'s output as JSON and React replays it.

Two things that port taught us about *this* engine, which apply whichever
renderer you use:

- **A prop only animates if the board gave it an `anim`.** `render.py` zeroes
  the rate otherwise, so a `policecar` with no `anim` holds one drawing and
  the scenery moves past it. If you want wheels to turn, say `"anim"`.
- **Aerial traffic depends on the camera.** It is generated against the pen's
  bounds, which are the current view rect, so which cars exist changes as the
  camera moves. It is unreproducible outside the engine and worth avoiding as
  a place to stage anything that must stay put.

Ship with `render.py`. Read `render-farm` before deciding how to build a *new*
style.

This style has **opted in** to that renderer — `style.json` lists
`"renderers": ["remotion"]`, which is what makes this legal:

```bash
director.py --2d-animation --topic "..." --use-remotion
```

The opt-in records the port that exists, not an intention. A style that has not
been brought across refuses the flag rather than planning a render nobody can
carry out.

---

## Verify before you ship

| Check | Expected |
|---|---|
| Format | 1920×1080 @ 30 `yuv420p` (1080×1920 for a Short) |
| Loudness | −14 LUFS, true peak ≤ −1 dBFS |
| **Physics** | **`node scripts/check-physics.mjs` exits 0 — no moonwalk, treadmill, foot slide, teleport or snap turn on any path** |
| **Look** | **`lookcheck.py film.mp4` exits 0 — all five metrics inside the measured reference envelope** |
| **Eye** | **`sidebyside.py film.mp4 reference.webm` — composition and silhouette, which no metric grades** |
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

### When the numbers pass and it still looks wrong

`lookcheck.py` grades colour and motion. It has no metric for composition,
silhouette or where the weight of a frame sits, and this style can satisfy
every number while looking nothing like the reference. `sidebyside.py` is the
other half — it puts the film next to its reference and prints the region
readings that the eye is unreliable about:

```bash
python3 scripts/sidebyside.py out/film.mp4 reference.webm -o compare.jpg
python3 scripts/sidebyside.py mine.png ref.png --stack -o compare.jpg
```

Sampling is at matched *fractions*, so films of different lengths line up at
their beginning, middle and end. Every defect found while calibrating this
style was caught by one of its readings and missed by looking at the frame:

- **sky sat/hue** — a near-neutral sky drags the whole film to grey through
  `depth_tint`, however colourful the rest of the palette is. This was the
  single largest error in the first build: sky at sat 0.027 against the
  reference's 0.073.
- **warm/cool gap** — the reference opposes a ~220° sky against a ~35° peak.
  Without that opposition a frame reads as greyscale no matter how saturated
  its tokens are.
- **terrain apex and width** — composition, which no colour metric sees.
- **streak energy** — weather meant to be noticed second, not first.

Two traps, both of which produced wrong numbers before they were understood: a
naive `saturation > 0.3` bounding box catches **anything else saturated in
frame**, not just the character, and a dark-pixel scan finds the character's
**hat** rather than the mountain top. The tool excludes figure pixels before
asking anything about terrain, and you should distrust any apex reading taken
without that exclusion.
