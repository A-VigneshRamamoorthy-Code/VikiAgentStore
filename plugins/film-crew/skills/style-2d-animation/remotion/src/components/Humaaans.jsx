import React from 'react';
import {GAITS, gaitAt, strideAt, footOffset} from '../lib/locomotion';
import {lag} from '../lib/overlap';

/**
 * Humaaans (CC0, Pablo Stanley) drawn on the locomotion solver.
 *
 * Why this is a separate rig rather than a palette swap on the Open Peeps one:
 * the two libraries are not the same shape of person. Humaaans' legs are 56% of
 * standing height; the Peeps rig's are 43%. Forcing this art onto those
 * proportions produces a squat figure with a long back, which is precisely the
 * "assets don't match" failure the asset pipeline exists to prevent. So the
 * proportions below are read out of `layout.json` -- the artist's own composed
 * figures -- and the *physics* is shared instead of the geometry.
 *
 * What is shared is the part that must never diverge: `GAITS`, `footOffset`,
 * `gaitAt` and `strideAt` are imported from the solver, so this rig and the
 * thing that decides where a character stands cannot disagree about when a foot
 * is on the ground. That disagreement was the original foot-slide bug.
 *
 * The other visible difference is that Humaaans has no outlines at all. It is
 * flat shape against flat shape, so the limbs here are single strokes in the
 * garment colour rather than the ink-under-fill pair the Peeps rig uses.
 */

const TAU = Math.PI * 2;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/* ── proportions, in Humaaans units with y=0 on the ground ───────────────── */

/**
 * The composed figures place head at y=0, body at y=82 and bottom at y=187,
 * with the feet landing near y=426. Everything below is that table, re-based so
 * the ground is 0 and up is negative -- the convention the solver already uses.
 */
export const FIG = {
  height: 426,
  centre: 150,
  headTop: -426,
  headW: 136,
  headX: -68,
  bodyTop: -344,
  bodyW: 256,
  bodyX: -128,
  hipY: -239,
};

const PELVIS_Y = FIG.hipY;

/**
 * The ankle, taken from the drawing instead of chosen.
 *
 * This was -14, and that single number is what "the legs are longer than the
 * body" actually was. The `bottom/` artwork is 199 units from its waistband to
 * its ankle anchor; putting the ankle at -14 makes the rig's leg 225, so every
 * leg was skinned onto a bone THIRTEEN PER CENT longer than the artist drew
 * it. Nothing else in the figure was stretched, so the proportion went wrong
 * in exactly the way the eye is best at spotting.
 *
 * -40 is the artwork's own value: the composed figures put the bottom piece at
 * y=187 in a 426-tall figure, and the piece's ankle sits 199 below its top.
 * The check that it is right is that the artist's shoe -- which hangs about 40
 * below the ankle anchor -- then lands exactly on the ground line, with no
 * fudge factor anywhere.
 */
const ANKLE_Y = -40;
const HIP_H = ANKLE_Y - PELVIS_Y; // 199, the artwork's own leg

// Kept in the artwork's proportion (they used to be 120/115 against a 225 leg)
// so the stroke fallback and the IK still agree with the drawing.
const THIGH = 106;
const SHIN = 102;
const LEG = THIGH + SHIN;
const LEG_EFF = LEG * 0.985;

/**
 * Leg geometry, measured off the artist's own `bottom/` artwork rather than
 * guessed.
 *
 * Sampling the trouser outlines gives a single leg about 47-52 units across at
 * the thigh narrowing to ~36 at the ankle, and roughly 108 across the pair.
 * Both numbers matter and the second one is the one that bites: a constant
 * 78-wide stroke at a 134 span turned the pair into one navy slab wider than
 * the torso, which is what "the legs are enormous" actually was. A real leg
 * tapers, so this one is drawn as two strokes -- thigh then shin -- whose
 * round caps overlap into a knee.
 */
/**
 * Hip separation, measured off the artwork rather than chosen.
 *
 * The two leg paths in `bottom/Sweatpants` have their top-band midpoints at
 * x=143 and x=155 -- **twelve units apart**. The rig was splaying them to 48,
 * four times what the artist drew, which is most of what read as "the legs
 * are not attached": a crotch that wide leaves the pelvis a hole, and the two
 * legs stop reading as one body.
 *
 * The fore-and-aft separation in a stride comes from the FEET, not from the
 * hips. Widening the hips to get a wider step is a mistake the geometry does
 * not need.
 *
 * Note that the cut-out rig does not consult this at all: it takes each hip
 * from the waistband of that leg's own drawing, which happens to put them
 * about 10 apart -- so the number was right, but it is better read off the
 * artwork than agreed with it.
 */
const HIP_DX = 11;

/**
 * Foot lift, converted out of the other rig's units.
 *
 * `GAITS.lift` is a LENGTH, and it was measured in Open Peeps character space
 * where the hips sit 392 units up. Handing that number to a figure whose hips
 * are at 225 asks for a foot lift of a third of its own height -- which is why
 * the first run cycle looked like hurdling rather than running. Everything else
 * a gait carries (duty, lean, heel) is a ratio or an angle and ports unchanged;
 * only this one is dimensional, so only this one is scaled.
 */
const PEEPS_HIP_H = 392;
const LIFT_K = HIP_H / PEEPS_HIP_H;
const scaleGait = (g) => ({...g, lift: g.lift * LIFT_K});

/**
 * How far the hips may drop, which is what sets the stride.
 *
 * Same derivation as the other rig and the same reason: a leg is a fixed
 * length, so the only way to put the feet further apart is to lower the hips.
 * Pick the dip, and the step follows. Scaled from the Peeps rig by figure
 * height (426/1010), then pulled in a little because Humaaans' long shins make
 * the geometric maximum read as a lunge.
 */
const SINK = {walk: 9, run: 22};

const pelvisSink = (ax) => Math.max(0, HIP_H - Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - ax * ax)));

const strideChar = (gait = 'walk') => {
  const g = GAITS[gait] ?? GAITS.walk;
  const reach = HIP_H - (SINK[gait] ?? SINK.walk);
  const A = Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - reach * reach));
  return (2 * A) / g.duty;
};

export const H_STRIDE_UNITS = {walk: strideChar('walk'), run: strideChar('run')};

/** Stride in SCENE units for a Humaaan drawn at `scale`. */
export const humaaansStride = (scale = 1, gait = 'walk') =>
  (H_STRIDE_UNITS[gait] ?? H_STRIDE_UNITS.walk) * scale;

/* ── part rendering ──────────────────────────────────────────────────────── */

const CAMEL = /[A-Z]/g;
const attrName = (k) => (k.includes('-') ? k : k.replace(CAMEL, (m) => `-${m.toLowerCase()}`));

const paint = (v, palette) =>
  typeof v === 'string' && v.startsWith('@') ? palette[v.slice(1)] ?? 'none' : v;

/**
 * One extracted Humaaans piece.
 *
 * Emits no `<svg>` of its own for the same reason the Peeps renderer doesn't:
 * pieces are positioned against each other by transform, and a nested viewBox
 * would rescale each independently and slide the head off the shoulders.
 */
export const HPart = ({asset, palette}) => {
  if (!asset) return null;
  return (
    <g>
      {asset.els.map((el, i) => {
        const {tag, ...rest} = el;
        const props = {};
        for (const [k, v] of Object.entries(rest)) props[attrName(k)] = paint(v, palette);
        return React.createElement(tag, {key: i, ...props});
      })}
    </g>
  );
};

/* ── legs ────────────────────────────────────────────────────────────────────
 *
 * There used to be a second, stroke-drawn leg system here: an IK solve painted
 * with round-capped lines, used whenever an asset's legs could not be pulled
 * apart. It is deleted rather than left dormant, because a silent fallback is
 * how it kept reaching the screen -- swapping in a bottom whose legs happen to
 * be fused was enough to turn a rigged character back into stick limbs with no
 * error anywhere. There is now one way to draw a leg: the artist's drawing,
 * rotated about the artist's joint.
 */

/* ── legs drawn from the artwork ─────────────────────────────────────────── */

/**
 * The affine matrix an SVG transform string actually applies.
 *
 * The previous version of this just grabbed the last `translate(...)` in the
 * list and called it the placement. That is true for most Humaaans pieces and
 * quietly false for the interesting ones: several shoes are placed with a
 * `translate rotate translate translate` chain, and reading one term out of
 * four gives a point that is nowhere near the drawing. It cost an afternoon
 * as a seated figure that hovered above the grass -- the geometry was right
 * and the measurement of it was wrong.
 *
 * Matrices are [a b c d e f] in SVG's own order.
 */
import {
  prepareBottom, poseLeg, artSink, bendLeg, ik, planFeet, KNEE_F,
} from '../lib/legrig';

export {prepareBottom, artSink};

/** One drawn element, painted from the palette, otherwise untouched. */
const RawEl = ({el, fill}) => {
  const {tag, ...rest} = el;
  const props = {};
  for (const [k, v] of Object.entries(rest)) props[attrName(k)] = v;
  if (fill) props.fill = fill;
  return React.createElement(tag, props);
};


/**
 * One leg of real artwork, bent onto its solved skeleton.
 *
 * The drawing is not rotated -- it is DEFORMED, point by point, onto a thigh
 * and a shin. That is the whole difference between this and the rig it
 * replaced: a rotation can only ever produce a straight leg, and a walk with
 * straight legs is a march.
 *
 * The shoe is still rigid, because a foot does not bend when a knee does. It
 * is carried to the ankle the solver landed on, so it cannot come off however
 * hard the leg is bent -- the failure that the old axial squash reintroduced
 * every time it hit its floor.
 */
const ArtLeg = ({leg, t1, t2, knee, ankle, pitch, fill, shoeFill}) => {
  const deg = (r) => ((r * 180) / Math.PI).toFixed(2);
  const [ax, ay] = ankle;

  const shoe = `translate(${(ax - leg.ankle[0]).toFixed(2)} ${(ay - leg.ankle[1]).toFixed(2)}) `
    + `translate(${leg.ankle[0].toFixed(2)} ${leg.ankle[1].toFixed(2)}) rotate(${deg(-pitch)}) `
    + `translate(${(-leg.ankle[0]).toFixed(2)} ${(-leg.ankle[1]).toFixed(2)})`;

  return (
    <g>
      <polygon points={bendLeg(leg, {t1, t2, knee})} fill={fill} />
      <g transform={shoe}><RawEl el={leg.shoe} fill={shoeFill} /></g>
    </g>
  );
};

/**
 * Sitting is a POSE OF THE WALKING LEGS, not a second drawing.
 *
 * The pack does ship a `sitting/` category, and it was used first, and it was
 * wrong -- for a reason worth recording, because the artwork looked like the
 * obviously right answer. Those pieces are drawn perched on a stool: hips 172
 * above the soles, which is 72% of this figure's standing hip height. Drop the
 * stool and the character sits in mid-air. Rotating the drawing forward about
 * its hip was tried next and cannot fix it either -- swung all the way to 90
 * degrees the hips are still 89 up, because a drawn knee bend takes the same
 * room whichever way you turn it. There is no ground-sit in the folder.
 *
 * So the sit is solved by the same rig that walks: both legs swung forward to
 * roughly horizontal and lightly foreshortened, which is a person sitting on
 * the grass with their legs out in front of them. That keeps ONE leg drawing
 * in the whole film -- the seated figure is wearing the trousers it walked in
 * -- and it puts the hips where a sitting body actually has them.
 */
/**
 * A seated leg lies ALONG the ground; it does not point at it.
 *
 * `SIT_SWING` is the angle off vertical, so 90 is dead horizontal -- hip and
 * ankle at the same height, both resting on the grass, which is what sitting
 * with your legs out in front actually is. It used to be 86, tipping the ankle
 * 14 units below the hip, and `SIT_K` used to be 0.92, which asks a 199-unit
 * leg to reach 183 and buys that with a 46-degree knee. Bowing a knee that far
 * UP lifts the whole limb clear of the ground, so the drop-to-ground landed
 * the heel and left the calf and thigh hanging in the air. Nearly straight is
 * correct here: the bend that reads as relaxed is about 20 degrees, not 46.
 */
const SIT_SWING = 90;
const SIT_SPREAD = 3;
const SIT_K = 0.985;
/**
 * The shoe's own angle, which is NOT the leg's.
 *
 * This used to be handed `theta` -- the leg's 86-degree swing -- which rotated
 * the shoe 86 degrees and stood the character's toes vertically on end. The
 * foot is a separate joint: with the legs out, the toes fall back toward the
 * shin a little and no further.
 */
const SIT_TOES = 26;

/**
 * The seated pose, and the height it puts the hips at.
 *
 * `drop` is MEASURED off the posed geometry rather than derived, because the
 * legs have thickness: the underside of a horizontal limb is half a trouser
 * width below its own axis, and that -- not the ankle -- is what rests on the
 * grass. Assuming the ankle sets the height buries the thigh in the ground.
 */
export const sitPose = (bottom) => {
  const poses = bottom.legs.map((L, i) => {
    /**
     * The NEAR leg is the one that lies on the grass, and the upstage one is
     * the one allowed to tip up past vertical.
     *
     * Both orderings put the same hip at the same height, so this looks like
     * a coin toss and is not: the near leg is the one drawn on top and the
     * one the eye reads, and with the spread the other way round it was the
     * visible limb that floated while the grounded one sat hidden behind it.
     * The pose measured correct and looked wrong, which is the failure mode
     * that only ever shows up in a render.
     */
    const deg = SIT_SWING + (i ? -SIT_SPREAD : SIT_SPREAD);
    const theta = (deg * Math.PI) / 180;
    /**
     * Solved to a TARGET rather than posed as an angle, so the sit gets the
     * same gently bent knee the walk does. The target is where the old rigid
     * pose put the ankle -- 0.92 of a leg out along the swing -- so the pose
     * that was measured and tuned against renders is preserved exactly, while
     * the knee stops being a straight line.
     */
    const target = [
      L.hip[0] + SIT_K * L.len * Math.sin(theta),
      L.hip[1] + SIT_K * L.len * Math.cos(theta),
    ];
    const a = L.len * KNEE_F;
    // The knee bows UP here, not forward: a person sitting with their legs out
    // in front has the joint above the hip-to-ankle line. Taking the walk's
    // sign put it below, which folded the leg into the grass.
    const solved = ik(L.hip, target, a, L.len - a, 1);
    // The foot is posed relative to the SHIN, not to the world: a shoe left
    // level under a horizontal leg reads as a broken ankle, and a shoe given
    // the leg's own swing stands on its toe.
    return {...solved, pitch: (SIT_TOES * Math.PI) / 180, span: L.len};
  });

  /**
   * The LIMB sets the height, not the shoe.
   *
   * Taking the lowest point of the whole leg puts the heel on the grass and
   * leaves the calf hanging in the air above it -- a pair of planks at hip
   * height, which is what the first version rendered. A person sitting with
   * their legs out rests them ON the ground along their length; the foot then
   * tips up off the end, which is why the shoe is measured but not obeyed.
   */
  let low = -Infinity;
  bottom.legs.forEach((L, i) => {
    // Measured off exactly the points `ArtLeg` draws, or the measurement is of
    // a pose the film never shows.
    for (const pair of bendLeg(L, poses[i]).trim().split(' ')) {
      low = Math.max(low, Number(pair.split(',')[1]));
    }
  });

  return {legs: poses, drop: bottom.ground - low};
};

/** How far a seated figure tips back. Small: the drawing already has the pose. */
const SIT_LEAN = -6;

/**
 * Everything below the waist, in the artwork's own coordinates.
 *
 * The whole group is placed once, exactly the way Humaaans' own composed
 * figures place it -- bottom piece at x=0, y=187 of a 426-tall figure -- and
 * then the legs rotate inside it. Because the torso is drawn afterwards and
 * overlaps the waistband, the hip closes itself. That is how the reference
 * artwork does it, and it is why no filler piece is needed: the previous
 * rig's `Seat` rectangle existed only to plug a hole that warping had made.
 */
const ArtLegs = ({phase, stride, g, palette, bottom, seat, moving, sink, sit = 0}) => {
  const plan = moving ? planLegs(phase, stride, g) : null;
  const far = poseLeg(bottom.legs[0], plan && plan.far, sink);
  const near = poseLeg(bottom.legs[1], plan && plan.near, sink);

  const backT = palette.trousersBack ?? palette.trousers;
  const backS = palette.shoesBack ?? palette.shoes;

  /**
   * Standing and seated are two DRAWINGS, and the change between them is a
   * cut, not a dissolve.
   *
   * Cross-fading them was the obvious thing and it looks like exactly what it
   * is: for a third of a second there are two translucent pairs of legs on
   * screen at once. Traditional cut-out work swaps poses on a single frame and
   * lets the movement either side sell it, which is why the hips keep
   * descending continuously THROUGH the swap -- the standing legs crouch into
   * it and the seated pose settles out of it, so the eye is following a body
   * going down rather than inspecting the frame it changed on.
   */
  const seated = sit >= 0.5 && seat;

  return (
    <g transform={`translate(${-FIG.centre} ${PELVIS_Y})`}>
      {seated ? (
        // Full drop the moment it appears: the hips are on the grass and the
        // heels are on the grass, always. Easing it in floated both for a few
        // frames, and a figure hovering over a meadow is a worse read than a
        // pose that arrives sharply -- which is anyway what sitting down does
        // at the end, when you stop lowering and simply land.
        <g transform={`translate(0 ${seat.drop.toFixed(2)})`}>
          <ArtLeg leg={bottom.legs[0]} {...seat.legs[0]} fill={backT} shoeFill={backS} />
          <ArtLeg leg={bottom.legs[1]} {...seat.legs[1]} fill={palette.trousers} shoeFill={palette.shoes} />
        </g>
      ) : (
        <g transform={`translate(0 ${sink.toFixed(2)})`}>
          <ArtLeg leg={bottom.legs[0]} {...far} fill={backT} shoeFill={backS} />
          <ArtLeg leg={bottom.legs[1]} {...near} fill={palette.trousers} shoeFill={palette.shoes} />
        </g>
      )}
    </g>
  );
};

export const planLegs = (phase, stride, gIn) => {
  const {near, far} = planFeet(phase, stride, scaleGait(gIn));
  const load = Math.max(near.planted ? Math.abs(near.x) : 0, far.planted ? Math.abs(far.x) : 0);
  return {sink: pelvisSink(load), near, far};
};

/* ── the character ───────────────────────────────────────────────────────── */

/**
 * A Humaaan, posed by a solver frame.
 *
 * The arms are part of the torso artwork and cannot be swung independently, so
 * the upper body carries the gait instead: it counter-rotates a few degrees per
 * step. That is not a workaround, it is what Pablo Stanley's own composed
 * figures do -- several of them apply a `rotate(-10)` to the body group for
 * exactly this reason.
 */
export const HumaaansCharacter = ({m, look, scale = 1, shadow = true, sit = 0}) => {
  const {palette, head, body, bottom} = look;
  if (!bottom) {
    throw new Error(
      'HumaaansCharacter needs a rigged bottom. Run the asset through ' +
      'prepareBottom(); if it returns null the asset\'s legs are fused into ' +
      'one path and cannot be articulated -- pick another (Sweatpants works). ' +
      'There is deliberately no stroke-drawn fallback any more.'
    );
  }

  const mix = m.gaitMix ?? (m.gait === 'run' ? 1 : 0);
  const g = gaitAt(mix);
  const stride = strideAt(mix, H_STRIDE_UNITS.walk, H_STRIDE_UNITS.run);

  const breathe = Math.sin(m.t * 0.62 * TAU * 0.34);
  const moving = m.moving;

  const plan = moving ? planLegs(m.phase, stride, g) : null;

  /**
   * The bob is not authored. It is measured off the legs.
   *
   * `pelvisSink` used to estimate this from bone lengths and it was then added
   * to a separate hand-tuned `m.bob * 0.3`, so the body's rise and fall and
   * the legs' rise and fall were two different numbers that happened to look
   * similar. With rigid drawn legs there is only one correct answer -- how far
   * the hip must come down for the planted foot to stay on the ground -- and
   * `artSink` returns it exactly. Feet cannot drift because there is nothing
   * left to drift against.
   */
  const gaitY = artSink(bottom, plan);
  // Sitting drops the pelvis to the height the seated drawing was drawn at;
  // the torso travels with it or the figure sits down and leaves its body
  // standing.
  const seat = React.useMemo(() => (bottom ? sitPose(bottom) : null), [bottom]);
  const seatDrop = seat ? seat.drop : 0;
  /**
   * The descent is front-loaded so the torso is nearly down by the time the
   * leg drawing swaps, which keeps the swap from also being a jump. It is not
   * a straight ramp for the same reason it is not linear in life: you lower
   * yourself most of the way under control and drop the last part.
   */
  const seatT = sit >= 0.5 ? 1 : Math.pow(sit, 0.55);
  const bodyY = gaitY * (1 - sit) + seatT * seatDrop;
  // The legs share the torso's descent, so the standing pair crouches into the
  // swap instead of standing bolt upright under a sinking body.
  const legY = bodyY;

  /**
   * How far off the ground the lower foot is, 0 planted to 1 fully airborne.
   *
   * A run has a real flight phase -- for part of every stride neither foot is
   * down -- and the rig already draws it. What it did not do was tell the
   * shadow, so a figure at the top of its stride kept a hard contact shadow
   * pinned under it and read as levitating rather than running.
   */
  const yLow = plan ? Math.max(plan.near.y, plan.far.y) : 0;
  const air = Math.min(1, Math.max(0, -yLow / 60));

  // One torso sway per stride, not per step: a body that counter-rotates on
  // every footfall reads as a limp.
  const sway = moving ? -Math.sin(m.phase * TAU) * (2.2 + g.bodyLean * 0.4) : breathe * 0.5;
  const lean = m.lean + (moving ? g.bodyLean * 0.3 : 0) + sway * (1 - sit) + sit * SIT_LEAN;

  /**
   * The head does not arrive when the shoulders do.
   *
   * "Not all objects move at the same time even within one physical body" --
   * the chain principle. The neck is a link, so the head samples the torso's
   * own sway from two frames ago rather than sharing it. That single frame of
   * lag is most of the difference between a figure that is walking and a
   * decal that is being slid across the frame.
   *
   * The cycle length has to come from the actual pace, because a delay fixed
   * in FRAMES is a different delay in PHASE at every speed -- two frames is a
   * fifth of a sprint cycle and a fifteenth of an amble.
   */
  const cycleFrames = moving && m.speed > 0.01 ? stride / m.speed : 0;
  const headSway = moving
    ? -Math.sin(lag(m.phase, 2, cycleFrames) * TAU) * (2.2 + g.bodyLean * 0.4)
    : sway;
  const headLag = (headSway - sway) * 0.75;

  // Taking weight compresses the body; pushing off extends it. Volume is
  // preserved on the other axis, so the figure never gains mass.
  const sy = m.squash ?? 1;
  const sx = 1 / sy;

  return (
    <g transform={`translate(${m.x.toFixed(2)} ${(m.y ?? 0).toFixed(2)}) scale(${scale})`}>
      {shadow && (
        <ellipse
          cx={0}
          cy={4}
          rx={((moving ? 74 : 84) + sit * 46) * (1 - air * 0.42)}
          ry={13 * (1 - air * 0.3)}
          fill={palette.shadow ?? '#191847'}
          opacity={0.16 * (1 - air * 0.6)}
        />
      )}
      <g transform={`scale(${m.facingScale.toFixed(3)} 1)`}>
        {/* Legs in ground space, outside the bob — a foot that bobs with the
            body is a foot that is not standing on anything. */}
        <ArtLegs phase={m.phase} stride={stride} g={g} palette={palette}
                 bottom={bottom} seat={seat} moving={moving}
                 sink={legY} sit={sit} />

        <g transform={`translate(0 ${bodyY.toFixed(2)}) rotate(${lean.toFixed(2)} 0 ${PELVIS_Y})`}>
          <g transform={`translate(0 ${PELVIS_Y}) scale(${sx.toFixed(4)} ${sy.toFixed(4)}) translate(0 ${-PELVIS_Y})`}>
            <g transform={`translate(${FIG.bodyX} ${FIG.bodyTop})`}>
              <HPart asset={body} palette={palette} />
            </g>
            <g transform={`rotate(${headLag.toFixed(2)} 0 ${FIG.headTop + 120})`}>
              <g transform={`translate(${FIG.headX} ${FIG.headTop})`}>
                <HPart asset={head} palette={palette} />
              </g>
            </g>
          </g>
        </g>
      </g>
    </g>
  );
};
