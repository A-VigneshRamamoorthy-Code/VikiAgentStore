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
npx remotion render src/index.jsx DoublingBack out/doubling.mp4 \
    --concurrency=4 --pixel-format=yuv420p --color-space=bt709
npx remotion render src/index.jsx Picnic out/picnic.mp4 \
    --concurrency=4 --pixel-format=yuv420p --color-space=bt709

node ../scripts/check-physics.mjs        # MUST pass before you render
python3 ../scripts/fetch_assets.py --sources   # where more art comes from
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
- **Flat artwork gets a cut-out rig: rigid pieces, drawn pivots, rotation
  only.** This is the single most expensive lesson in the file. The legs were
  first drawn procedurally as strokes, then *warped* — the drawn trousers
  skinned onto a solved two-bone chain — and both produced everything the film
  was rejected for: wire limbs with stub hands, hard-edged rectangles floating
  at every hip, shoes shearing off ankles, legs longer than torsos. A warp can
  change a limb's length and a warp needs a hip, and `limbRest` reads a hip as
  the midpoint of a limb's topmost band, which for a `bottom/` asset is the
  **waistband**; slicing the trousers into two independently-warped ribbons
  therefore throws the pelvis away, and the hole it leaves is what the invented
  `Seat` rectangle was plugging. None of it was needed. In the artist's own
  composition the hip closes for free because the torso is drawn *over* the
  trousers — stack bottom, then body, then head. `prepareBottom` returns whole
  drawn pieces — never ribbons — and the shoe is a *child* of the solved ankle,
  so it cannot leave it. The leg itself is bent (see below) rather than skinned
  onto a chain: the distinction that matters is that the bend is the identity at
  rest and takes its hip from the artwork's own ankle, so it can never throw the
  pelvis away or change the limb's width.
- **A rig has no business posing a rest pose.** Standing returns the drawing
  untouched — no rotation, no scale, no solve. If the rig at rest is not pixel
  identical to the reference composition beside it in `HumaaansBench`, the rig
  is wrong, and that comparison is worth more than any moving test.
- **Take proportions off the drawing, not out of the rig.** `ANKLE_Y` was
  `-14`, giving a 225-long leg. The artwork's own waistband-to-ankle is **199**.
  That one number stretched every leg by 13% while nothing else in the figure
  moved, which is precisely the defect the eye is best at catching — it read as
  "the legs are longer than the body" because it *was*. The confirmation that
  199 is right costs nothing: the artist's shoe hangs ~40 below the ankle
  anchor, and at `ANKLE_Y = -40` its sole lands exactly on the ground line with
  no fudge anywhere. Whenever a constant and a drawing disagree, the drawing is
  the measurement and the constant is the guess.
- **A rigid leg cannot bend a knee. Foreshortening is not a knee, and the
  difference is the whole walk.** Rotation alone is genuinely not enough —
  hip→ankle needs 194–240 across a walk and 149–251 across a run. The first
  answer here was to scale along the limb's own axis, and it is worth
  understanding why that failed, because it *measured* correct: a squashed leg
  is still a **straight** leg, so it telescopes instead of folding, and the
  figure marches. Worse, the squash needs a floor to stay recognisable, and the
  frame it hits that floor is the frame the drawn ankle stops agreeing with the
  solved one — which is exactly when the shoe detaches. The reported bug and
  the marching gait were the same bug.
  The technique that works is **two-bone IK plus a bone-weighted bend of the
  drawn outline**. Describe each outline point in the rest leg's own frame — `s`
  along the limb, `n` across it — then rebuild it on the posed thigh and on the
  posed shin and blend across a narrow band at the knee:

  ```
  A  = hip  + s·d₁ + n·d₁⊥              (on the thigh)
  B  = knee + (s−a)·d₂ + n·d₂⊥          (on the shin)
  P' = lerp(A, B, smoothstep((s − (a−band)) / 2·band))
  ```

  The property that makes it safe is that when the skeleton is straight and at
  its drawn angle **both mappings collapse to the identity**, so a leg with
  nothing to do is the artist's drawing to the last decimal. The shoe stays a
  rigid child of the solved ankle, so it still cannot detach.
- **Resample the outline first, or the leg tears instead of bending.** A
  trouser seam flattened to two points stays a straight line under any
  skeleton: the leg bends, the seam does not, and the limb rips open at the
  knee. Cut every edge into ~3-unit pieces before binding. This is the
  non-obvious prerequisite — the bend maths is correct without it and produces
  garbage.
- **`KNEE_BAND` is a measurement, not a taste.** Blend the two mappings over
  ±10% of leg length. Swept: 0.26 balloons the shin and the limb reads as a
  rubber hose; 0.08–0.10 is a crisp hinge. And bind leg shapes **by nearest
  shoe**, not one skeleton each — this artwork gives the far leg a second
  overlapping crease piece in the same fill, and putting it on its own bones
  tears it off the leg on the first frame that bends.
- **Both legs must be the same length, or the character limps and nobody can
  see why.** This pack draws its figures standing with the feet apart — one leg
  splayed 16.6° out, the other 6.7° back — so hip-to-ankle differs by 7.3 units
  between them. They are not different legs. They are the same leg at two
  angles, and the tell is that **both ankles sit exactly 199.0 below their
  hip**. Taking the drawn length as the bone made the hip ride 7 units lower on
  every other step: invisible in any single frame, obvious the instant hip
  height was plotted over a full cycle. Take the vertical drop as the bone and
  keep the drawn length only as the axis the artwork is measured along — which
  means the bone span has to travel **with the pose**, because a standing
  figure keeps its splay and a walking one does not.
- **A constraint is not a curve.** The pelvis was driven by "the highest
  position no planted leg objects to", which is a perfectly valid *floor* and a
  terrible *trajectory*: it holds the hip up as long as any leg can hold it,
  then drops it 24 units the frame the next foot lands. A leg can always bend
  more than it has to; it can never bend less than it must — only one of those
  is a constraint. Drive the hip with the **compass gait** instead, an inverted
  pendulum vaulting over the support point: lowest at contact, highest at
  midstance, one arc per *step*. The support point jumps from −A to +A at the
  changeover, but the height it implies depends on distance from under the hip
  and that is even in `x`, so the jump costs nothing. Then clamp with the floor.
  Result: a 24-unit sawtooth became a 14-unit arc, 7% of leg length.
- **The heel lifts so the hip does not have to fall.** Subtract the foot's own
  roll depth from that leg's claim on the pelvis. Skip it and the trailing leg
  holds the hip down until its foot physically leaves the ground and then
  releases it all at once. This is not smoothing — it is what a heel lift is
  *for*: the body keeps rising over the ball of the foot while the ankle rises
  with it, so the leg never has to choose between staying straight and staying
  on the ground.
- **Ankle rise is a constraint, not two rules.** "The ankle is never lower than
  the foot's own roll allows" replaces the whole planted-vs-swinging special
  case, and it is what makes the heel actually leave the ground at push-off:
  the ankle rises *because the toe is still down*, which is what a heel lifting
  **is**. It falls out of the geometry instead of being posed. Keep the
  correction purely vertical and the no-slip guarantee survives it intact.
- **Write the foot's roll as one curve around the whole cycle.** Stance and
  swing glued together at toe-off put a 15° snap at the join and jumped the
  ankle 20 units with it — one frame, and it reads as a limp. Heel strike with
  the toes a few degrees up, flat through midstance, heel off at the end, then
  *carry on* unwinding through swing back to the next strike. Mind the sign:
  the renderer applies `rotate(−pitch)` and SVG's positive rotation turns x
  toward y — downward — so a **positive pitch lifts the toes**. Getting that
  backwards is silent: it bent the knee 24° at heel strike, the one moment a
  real leg is straightest.
- **Clearance peaks EARLY in swing, at about 38% of it.** A symmetric
  `sin(πu)` is the obvious choice and is wrong: it leaves the ankle on the
  ground for the first frames after toe-off, exactly when a real leg is folding
  hardest to get the foot out of the way. Measured, that flat start dragged the
  knee from 42° back to 16° and up again to 47° over three frames. `sin(πu^0.72)`
  moves the peak to 0.38 and the flexion rises monotonically.
- **Add the hip's give as extra hip drop, never as a knee angle.** Lowering the
  hip over a planted foot forces the solver to bend the knee by exactly the
  amount that keeps the foot where it is, so give and contact can never
  disagree. Posing the knee directly moves the foot and reintroduces the slip
  the rig exists to prevent. Omitting the give altogether is what makes a walk
  read as a **march** — and the magnitude is small: 18° of knee flexion drops
  the hip only ~2.5 units on a 204-unit leg. Most of the bob is the compass.
- **Grade the knee against the real curve, not against "it bends".** A walk has
  **two** flexion peaks, and only one of them is obvious. Target: ~0° at
  contact, 15–20° through loading, easing at midstance, ~40° at toe-off, 60–70°
  at the swing peak, straight again before the next heel strike. This rig now
  measures 0.4 / 21 / 12 / 44 / 60.5 / 0.4.
- **A seated leg lies ALONG the ground; it does not point at it.** Sitting was
  posed at 86° off vertical reaching 0.92 of the leg, which buys a 46° knee —
  and bowing a knee that far *up* lifts the whole limb clear of the grass, so
  dropping the group to the ground landed the heel and left the calf and thigh
  hanging. Horizontal and nearly straight is correct: hip and ankle at the same
  height, both resting. And the foot is a **separate joint** — handing the
  shoe the leg's own 86° swing stood the character on its toes.
- **Derive the rotation; do not pattern-match it.** To swing a limb drawn at
  angle `rest` to angle `θ`, the rotation is `rest − θ`. The obvious
  `θ − rest` is a *reflection about the rest angle*: correct when `θ = rest`
  and wrong everywhere else, so it stands up perfectly and comes apart the
  moment the figure takes a step. Compose it as
  `rotate(−θ) · scale(1, k) · rotate(rest)` about the hip.
- **Parse the whole transform, not the last `translate`.** Several shoes are
  placed with `translate rotate translate translate`; reading one term of four
  puts the piece nowhere near where it is drawn. That shortcut cost an
  afternoon of a seated figure hovering over the grass — the geometry was right
  and the *measurement* of it was wrong.
- **Match feet to legs at the ankle, as a one-to-one assignment.** "Nearest shoe
  to this hip" fails twice: a standing figure's hips are ~10 apart while its
  feet are ~90 apart, so both hips are nearest the same shoe, and nothing stops
  two legs claiming it. One leg got a shoe and the other a bare stump.
- **Measure the curve, not the control points.** Pulling every number out of a
  `d` string and treating them as points includes a cubic's control handles,
  which lie *outside* the curve they steer — so a limb's measured extent is
  wider than its ink. Flatten the path (8 samples a curve is plenty here)
  before measuring anything that has to touch the ground.
- **Framing is arithmetic.** The world is scaled up about the *centre* of the
  frame, so the visible window does not begin at the camera — it begins half
  the shrinkage to the right of it. Solving `cam = x − visW·f` and omitting
  that term put every shot in `Picnic` a constant 320 world units out and left
  the cast piled against the left edge with the right half empty for eighteen
  seconds. It looked like a staging opinion and it was a missing term:
  `cam = x − visW·f − (width − visW)/2`.
- **Ground contact is measurable, so measure it.** Rasterise the rig at 16
  phases and read the lowest inked row against the ground line. A walk must
  read flat (a foot is always down); a run must sit flat *except* in its flight
  windows and must never go below. Every leg bug in this rebuild — the swing
  scuff, the toe dig at toe-off, the splayed stride, the hovering sit — showed
  up as a number in that sweep before it was visible to the eye.
- **Delete fallbacks; do not leave them dormant.** The stroke-drawn leg system
  survived because it was silent: hand it an asset whose legs happen to be
  fused (`Skinny-Jeans`) and a rigged character quietly became stick limbs with
  no error anywhere. `HumaaansCharacter` now *throws* if `look.bottom` is
  missing. There is one way to draw a leg.
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

### Sitting, and things that are not people

`humaaans-meadow` is the same library outdoors, and `Picnic` is its film: two
adults, a child and a dog share one ground plane, settle onto a blanket, eat,
and then the dog leaves at four times anyone else's pace. Where `DoublingBack`
stress-tests one figure through four hard joins, this one tests whether a
crowd of different builds can hold still together without reading as furniture.

Three additions, and the trap in each:

- **`HumaaansCharacter` takes `sit={0..1}`, and sitting is a *pose of the
  walking legs*.** The pack does ship a `sitting/` category — complete seated
  legs, knee bend and shoes all drawn — and it was used first, and it is wrong
  for a picnic. Those pieces are drawn perched on a stool: hips **172 above the
  soles, 72% of the figure's standing hip height**. Drop the stool and the
  character sits in mid-air; rotate the drawing forward about its hip and it
  still cannot be saved, because at a full 90° the hips are *still* 89 up — a
  drawn knee bend occupies the same room whichever way you turn it. There is no
  ground-sit in the folder. So the sit is solved by the same rig that walks:
  both legs swung to roughly horizontal (86° ± 3) and foreshortened to 0.92,
  with the shoes carried **round with the leg** rather than left flat, because
  someone sitting with their legs out has their toes up. That measures out at a
  hip **13% of standing height** — where a sitting body's hips actually are —
  keeps one leg drawing in the entire film, and needs no second asset. Three
  details decide whether it reads, and all three were found in a render rather
  than in the arithmetic: the **limb** sets the ground height and not the shoe
  (obey the shoe and the heel touches while the calf hangs in the air above
  it); the **near** leg is the one laid flat, because it is the one drawn on
  top and the one the eye follows; and the spread between the two legs is
  small, because two limbs fanned apart read as a pair of planks while two
  nearly overlapping ones read as a single pair of legs.
- **The swap between two poses is a cut, not a dissolve.** Cross-fading
  standing and seated legs puts two translucent pairs of legs on screen for a
  third of a second and looks exactly like what it is. Swap on one frame and
  let the movement either side sell it — the hips keep descending *through* the
  swap, so the eye follows a body going down instead of inspecting the frame it
  changed on. That is how cut-out animation has always done it.
- **Borrowing a prop is the same mistake as inventing one.** The seated
  drawings come with the stool, and keeping it looked like the conservative
  choice. It was not: three pale boxes on a picnic blanket read as exactly the
  "wire things" the rebuild existed to remove, and a scene does not get props
  because a rig needed one. If the pose only works with furniture under it, the
  pose is wrong — which is how the sit ended up solved rather than drawn.
- **`Dog.jsx` is a quadruped, not a person with four legs.** Diagonal pairs
  share a phase in a trot; a bound is a different pairing, not a faster trot.
  Its paws come from the same `footOffset()` as everyone else's feet, so it
  cannot moonwalk, and its tail is a lagging chain rather than a wave.
- **`Butterflies.jsx` is the asymmetric-gravity demo.** A butterfly does not
  fly, it falls and catches itself: `rise` up, hang, `fall` down, wings a
  quarter-beat ahead of the body because the stroke *causes* the lift. Use a
  symmetric sine and you get a bouncing ball with decoration.

Every character in a film must be graded by `check-physics.mjs` against **its
own** stride options — stride scales with body size, so a child solved against
an adult's stride slides, and a dog does it worse.

Do **not** grade it by copying the film's paths into the validator. That copy
drifts, and a drifted mirror reports `36 checks clean` while the film teleports
its dog off the side of the frame — which is precisely what happened here, for
four render cycles. Put the paths in a plain-JS module the film and the
validator both import (`films/picnic.paths.js` is the worked example) and pass
in anything Node genuinely cannot reach. Full post-mortem in
[`verification.md`](reference/verification.md#never-let-the-validator-mirror-the-film).

One staging law came out of the same film: **a camera cannot hold two subjects
further apart than the lens is wide.** When the ending loses somebody, shorten
the travel — moving the camera faster only pans across empty grass.

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

### The four that make it stop looking procedural

Correct physics is not the same as good animation. The first films made with
this skill passed every check and still read as floaty and robotic. Four
fixes, drawn from a full animation course and documented in
[`motion-craft.md`](reference/motion-craft.md), closed most of that gap:

1. **Gravity is asymmetric.** A falling body accelerates; a rising one
   decelerates. A symmetric bounce — `|sin|`, the obvious implementation, and
   the one this repo shipped — reads as buoyancy. `bobShape()` in
   [`timing.js`](remotion/src/lib/timing.js).
2. **Children lag parents by two frames, per link, accumulating.** Not two
   frames for the whole chain. `chainPhases()` in
   [`overlap.js`](remotion/src/lib/overlap.js). The delay must be converted
   to phase through the *actual* pace, or it is wrong at every speed but one.
3. **Weight lands.** Contact poses are the keys; the down pose squashes and
   the up pose stretches, volume-preserved. Without them a walk is a slide.
4. **One focal action at a time.** The reason procedural rigs look robotic is
   that every joint oscillates constantly. Real performance is sequential —
   damp everything that is not the point of the shot.

`DoublingBack` is the film that exercises all four: walk → stop → held beat →
turn → run. Every join in that chain is a place a rig lies.

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
| [`motion-craft.md`](reference/motion-craft.md) | **craft** — an 18-part animation course reduced to code: timing charts, asymmetric gravity, the two-frame chain lag, staging, and the eight ways this reads as floaty or robotic |
| [`assets.md`](reference/assets.md) | **art** — what is bundled, why Freepik is not, how a character is assembled, and the two staging rules for sets |
| [`SOURCES.md`](assets/SOURCES.md) | **where more art comes from** — every source, its licence, and which ones this repo may ship |
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
| **Physics** | **`node scripts/check-physics.mjs` exits 0 — 36 checks: no moonwalk, treadmill, foot slide, teleport or snap turn; gravity asymmetric, charts monotone, chain lag accumulating, follow-through ringing down; each rig's stride derived from its own measured leg rather than typed in; and the leg rig itself graded — standing pose untouched, both legs the same length, hip bobbing once per step without vaulting, foot rolling heel-to-toe with no break in the curve, sole never through the ground, knee bending only forwards, stance knee yielding after contact** |
| **Rig** | **`HumaaansBench` — at rest the rig must be pixel-identical to the artist's stacked composition beside it; and the sole must sit on the ground line at every walk phase, off rendered pixels, not by eye** |
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
