import React, {useId} from 'react';
import {GAITS, gaitAt, strideAt, footOffset} from '../lib/locomotion';
import {compileLimb, limbRest} from '../lib/skin';
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
const ANKLE_Y = -14;
const HIP_H = ANKLE_Y - PELVIS_Y; // 225, hip height above the ankle

const THIGH = 120;
const SHIN = 115;
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
 */
const HIP_DX = 11;
const THIGH_W = 46;
const SHIN_W = 33;
// The artwork's shoes measure about 61 x 21. The first pass drew 82 x 26 --
// a third too long -- which put a slab on the end of each leg and was most of
// what read as "the legs are enormous".
const SHOE_L = 60;
const SHOE_H = 22;

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

/* ── legs ────────────────────────────────────────────────────────────────── */

const ik = (hx, hy, fx, fy, l1, l2, bend) => {
  let dx = fx - hx;
  let dy = fy - hy;
  let d = Math.hypot(dx, dy);
  const reach = (l1 + l2) * 0.995;
  if (d > reach) {
    const k = reach / d;
    dx *= k;
    dy *= k;
    d = reach;
    fx = hx + dx;
    fy = hy + dy;
  }
  if (d < 1e-6) return {jx: hx, jy: hy + l1, fx, fy};
  const a = Math.acos(clamp((d * d + l1 * l1 - l2 * l2) / (2 * d * l1), -1, 1));
  const ang = Math.atan2(dy, dx) + bend * a;
  return {jx: hx + Math.cos(ang) * l1, jy: hy + Math.sin(ang) * l1, fx, fy};
};

/** A flat Humaaans limb: rounded strokes, no outline. */
const Stroke = ({a, b, fill, w}) => (
  <path
    d={`M${a[0].toFixed(1)} ${a[1].toFixed(1)} L${b[0].toFixed(1)} ${b[1].toFixed(1)}`}
    fill="none"
    stroke={fill}
    strokeWidth={w}
    strokeLinecap="round"
  />
);

/**
 * A leg: hip to knee to ankle, thick then thin. Drawn as two strokes so it
 * narrows the way the artwork does; the round caps meeting at the knee do the
 * joint for free.
 */
const Pant = ({pts, fill}) => (
  <g>
    <Stroke a={pts[0]} b={pts[1]} fill={fill} w={THIGH_W} />
    <Stroke a={pts[1]} b={pts[2]} fill={fill} w={SHIN_W} />
  </g>
);

const Shoe = ({x, y, fill, heel}) => {
  const back = -SHOE_H * 0.9;          // heel, just behind the ankle
  const toe = SHOE_L + back;
  const t = -SHOE_H / 2;
  const b = SHOE_H / 2;
  return (
    <g transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(-heel * 12).toFixed(1)})`}>
      <path
        d={`M${back + 8} ${t} L${toe - 10} ${t} Q${toe} ${t} ${toe} ${t + 9} L${toe} ${b - 4} Q${toe} ${b} ${toe - 7} ${b} L${back + 8} ${b} Q${back} ${b} ${back} ${0} Q${back} ${t} ${back + 8} ${t} Z`}
        fill={fill}
      />
    </g>
  );
};

/* ── legs drawn from the artwork ─────────────────────────────────────────── */

/** The final translate in a transform string -- the piece's placement. */
const lastTranslate = (tr) => {
  if (!tr) return [0, 0];
  const all = [...tr.matchAll(/translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)/g)];
  if (!all.length) return [0, 0];
  const m = all[all.length - 1];
  return [Number(m[1]), Number(m[2])];
};

/**
 * Pulls the animatable limbs out of a `bottom/` asset.
 *
 * A limb is a `@clothing` path tall enough to span most of the piece; the short
 * ones are cuffs and waistbands, which must not be skinned onto a bone. Each is
 * paired with whichever shoe sits nearest its ankle in x, so the pairing comes
 * out of the drawing rather than out of a hand-written table.
 *
 * Returns `null` for assets whose legs are fused into a single path (the
 * Skinny-Jeans family). Those genuinely cannot be articulated, and saying so
 * here is better than skinning a two-legged silhouette onto one bone.
 */
export const prepareBottom = (asset) => {
  const shoes = asset.els
    .filter((e) => e.fill === '@shoe' && e.d)
    .map((e) => ({d: e.d, at: lastTranslate(e.transform)}));

  const limbs = asset.els
    .filter((e) => e.fill === '@clothing' && e.d)
    .map((e) => ({d: e.d, rest: limbRest(e.d)}))
    .filter((l) => l.rest && l.rest.ankle[1] - l.rest.hip[1] > asset.h * 0.6);

  if (limbs.length < 2) return null;

  limbs.sort((a, b) => a.rest.ankle[0] - b.rest.ankle[0]);
  const legs = limbs.slice(0, 2).map((l) => {
    const shoe = shoes.length
      ? shoes.reduce((best, s) =>
          Math.abs(s.at[0] - l.rest.ankle[0]) < Math.abs(best.at[0] - l.rest.ankle[0]) ? s : best)
      : null;
    return {
      warp: compileLimb(l.d),
      rest: l.rest,
      shoe: shoe && {
        d: shoe.d,
        off: [shoe.at[0] - l.rest.ankle[0], shoe.at[1] - l.rest.ankle[1]],
      },
    };
  });
  return {legs, len: legs[0].rest.ankle[1] - legs[0].rest.hip[1]};
};

/**
 * One leg of real artwork, bent to a pose.
 *
 * The silhouette, its taper and its ankle are the artist's; only the joint is
 * ours. The shoe is a rigid child of the shin -- a shoe does not deform, it
 * points where the foot points.
 */
const ArtLeg = ({leg, hip, knee, ankle, fill, shoeFill}) => {
  const d = leg.warp({rest: leg.rest, pose: {hip, knee, ankle}});
  const deg = (Math.atan2(ankle[1] - knee[1], ankle[0] - knee[0]) * 180) / Math.PI - 90;
  return (
    <g>
      <path d={d} fill={fill} />
      {leg.shoe && (
        <g transform={`translate(${ankle[0].toFixed(1)} ${ankle[1].toFixed(1)}) rotate(${deg.toFixed(1)})`}>
          <g transform={`translate(${leg.shoe.off[0].toFixed(1)} ${leg.shoe.off[1].toFixed(1)})`}>
            <path d={leg.shoe.d} fill={shoeFill} />
          </g>
        </g>
      )}
    </g>
  );
};

/**
 * The seat.
 *
 * `limbRest` takes a leg's hip as the midpoint of its topmost band, which for
 * these assets is the WAISTBAND -- every leg path in `bottom/` starts at y=0.
 * So slicing the trousers into two ribbons and warping each independently
 * throws the pelvis away: there is no longer anything joining the legs, and
 * the two straight top edges rotate with their thighs and show through the
 * V-notch of an open jacket as a hard angular slab. That is the "legs are not
 * attached" defect, and no amount of tuning the legs fixes it, because the
 * missing piece is not a leg.
 *
 * A cut-out rig solves this with a rigid hip piece that the thighs hang
 * behind. This is that piece. It is drawn AFTER both legs, so a rotated
 * thigh-top can never show at any pose, and it is drawn in the near leg's
 * colour because it is the front of the trousers.
 *
 * Its width is the artwork's: the two leg paths together span 117 units, so
 * ±56 about the hip centre. Its lower edge sits just above the torso hem, so
 * the leg reads as emerging from under the jacket rather than starting at the
 * waist -- which is also what made the legs look longer than the body.
 */
const WAIST_DROP = -6;
const SEAT_W = 56;
const SEAT_TOP = -6;
const SEAT_BOT = 66;

// A shoe sole reaches about 14 below the ankle; 26 clears it with margin and
// still cuts anything that would otherwise be drawn under the grass.
const GROUND_CLIP = 26;

const Seat = ({hy, fill}) => {
  const W = SEAT_W;
  const top = hy + SEAT_TOP;
  const bot = hy + SEAT_BOT;
  const R = 0;
  const R2 = 22;
  const nW = 18;
  const notch = 16;
  const d = [
    `M${-W},${top + R}`,
    `Q${-W},${top} ${-W + R},${top}`,
    `L${W - R},${top}`,
    `Q${W},${top} ${W},${top + R}`,
    `L${W},${bot - R2}`,
    `Q${W},${bot} ${W - R2},${bot}`,
    `L${nW},${bot}`,
    `Q${nW * 0.4},${bot} 0,${bot - notch}`,
    `Q${-nW * 0.4},${bot} ${-nW},${bot}`,
    `L${-W + R2},${bot}`,
    `Q${-W},${bot} ${-W},${bot - R2}`,
    'Z',
  ].join('');
  return <path d={d} fill={fill} />;
};

/**
 * Sitting on the ground, knees up, measured against the rig's own bones.
 *
 * The knee is not chosen, it is SOLVED: given a hip on the ground and a heel
 * planted in front of it, there is exactly one knee that satisfies a 120 thigh
 * and a 115 shin without stretching either. Eyeballing it instead is what made
 * the first pass look like a folded deckchair -- the shin came out 11% long and
 * the shoe floated off the end of the trouser.
 *
 * The far leg is not a mirror of the near one. Two legs folded into identical
 * shapes stack into a single silhouette and the figure loses a limb.
 */
const SIT = {
  hip: [0, -46],
  knee: [97, -116],
  ankle: [150, ANKLE_Y],
  lean: -7,
  far: {knee: [89, -126], ankle: [116, ANKLE_Y]},
};

export const SIT_HIP_Y = SIT.hip[1];

const ArtLegs = ({phase, stride, g, palette, bottom, moving, breathe, sink, sit = 0}) => {
  const plan = moving ? planLegs(phase, stride, g) : null;
  const hy = PELVIS_Y + (moving ? sink : breathe * 2) + sit * (SIT.hip[1] - PELVIS_Y);

  // Standing and seated are the same three joints, so the transition is a
  // blend between two solved poses rather than a second rig.
  const to = (a, b) => [a[0] + (b[0] - a[0]) * sit, a[1] + (b[1] - a[1]) * sit];

  /**
   * When the artwork hands over to the strokes.
   *
   * Not linear with `sit`, because a straight cross-fade leaves the middle of
   * the move showing both legs at half opacity and the figure goes briefly
   * transparent. The handover happens EARLY instead, over a third of the move,
   * while the knee is still shallow enough that the two versions sit on top of
   * each other and there is nothing to see.
   */
  const xf = Math.min(1, Math.max(0, (sit - 0.18) / 0.34));

  const solve = (f, dx, splay, seat) => {
    const target = f
      ? [dx + f.x, ANKLE_Y + f.y]
      : [dx + splay * 7, ANKLE_Y];
    const {jx, jy, fx, fy} = ik(dx, PELVIS_Y + (moving ? sink : breathe * 2),
                               target[0], target[1], THIGH, SHIN, -1);
    return {
      hip: [dx, hy],
      knee: to([jx, jy], [dx + seat.knee[0], seat.knee[1]]),
      ankle: to([fx, fy], [dx + seat.ankle[0], seat.ankle[1]]),
    };
  };

  const far = solve(plan && plan.far, -HIP_DX, -1, SIT.far);
  const near = solve(plan && plan.near, HIP_DX, 1, SIT);

  /**
   * Everything below the waist is clipped to a flat top at the hip line.
   *
   * A rotated thigh carries its top band round with it, so at a wide stride
   * the corner of a leg -- or of the seat -- swings ABOVE the hip and out
   * from under the torso, wherever that garment's hem happens to be cut high.
   * The jacket's back hem is cut high, which is exactly where it was showing.
   *
   * Covering the corner with more geometry only moves the problem, because
   * the covering piece then has a corner of its own. Removing it is what
   * actually ends it: nothing exists above the waist line, so nothing can
   * appear there for any pose.
   *
   * WHERE that line goes is measured, not chosen. `body/Jacket` is an OPEN
   * jacket and has a vent between its panels; the artist's own compositions
   * show trousers through it, so the waist has to stay high enough to be
   * behind that vent. Dropping it below instead leaves a bare notch, which
   * is a worse defect than the one being fixed and was tried first.
   *
   * The seat's top corners are square for the same reason. A rounded corner
   * seen through a straight vent is what read as a torn rectangle floating
   * at the hip; a flat waistband seen through it reads as trousers.
   */
  const clip = useId().replace(/:/g, '');
  /**
   * The waist line only has a job while the figure is upright.
   *
   * It exists to swallow the top corner of a thigh that has rotated out from
   * under a high-cut hem, which can only happen mid-stride. A seated figure
   * has its KNEES above its hips, so the same rectangle that saves the walk
   * amputates the sit -- which it duly did, and the legs vanished entirely.
   *
   * So the ceiling lifts with the pose. There is no stride to hide by then.
   */
  const waist = hy + WAIST_DROP - sit * 260;

  return (
    <g>
      <defs>
        <clipPath id={clip}>
          {/* Floor as well as ceiling. The seat piece is a slab deep enough to
              bridge the pelvis at a full stride, which puts its lower edge
              under the ground once the hips drop to it. Nothing below the
              shoes should ever be drawn, in any pose. */}
          <rect x={-260} y={waist} width={520} height={GROUND_CLIP - waist} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clip})`}>
        {/* The trouser artwork is a nearly straight leg. Warping it round a
            right angle shears the outline and tears the shoe off the ankle,
            which is exactly what a folded knee asks it to do -- so at a fold
            that deep the art hands over to the stroke legs, which are two
            round-capped lines and bend at any angle by construction.

            A cross-fade and not a switch: both are solved from the SAME three
            joints, so they occupy the same space and the swap has nothing to
            pop between. */}
        <g opacity={1 - xf}>
          <g opacity="0.82">
            <ArtLeg leg={bottom.legs[0]} {...far}
                    fill={palette.trousersBack ?? palette.trousers}
                    shoeFill={palette.shoesBack ?? palette.shoes} />
          </g>
          <ArtLeg leg={bottom.legs[1]} {...near}
                  fill={palette.trousers} shoeFill={palette.shoes} />
        </g>
        {xf > 0.001 && (
          <g opacity={xf}>
            <g opacity="0.82">
              <Pant pts={[far.hip, far.knee, far.ankle]}
                    fill={palette.trousersBack ?? palette.trousers} />
              <Shoe x={far.ankle[0]} y={far.ankle[1]}
                    fill={palette.shoesBack ?? palette.shoes} heel={0} />
            </g>
            <Pant pts={[near.hip, near.knee, near.ankle]} fill={palette.trousers} />
            <Shoe x={near.ankle[0]} y={near.ankle[1]} fill={palette.shoes} heel={0} />
          </g>
        )}
        <Seat hy={hy} fill={palette.trousers} />
      </g>
    </g>
  );
};

export const planLegs = (phase, stride, gIn) => {
  const g = scaleGait(gIn);
  const near = footOffset(phase, stride, g);
  const far = footOffset((phase + 0.5) % 1, stride, g);
  const load = Math.max(near.planted ? Math.abs(near.x) : 0, far.planted ? Math.abs(far.x) : 0);
  return {sink: pelvisSink(load), near, far};
};

const WalkingLegs = ({phase, stride, g, palette, sink}) => {
  const hy = PELVIS_Y + sink;
  const build = (f, dx) => {
    const {jx, jy, fx, fy} = ik(dx, hy, dx + f.x, ANKLE_Y + f.y, THIGH, SHIN, -1);
    return {pts: [[dx, hy], [jx, jy], [fx, fy]], fx, fy, planted: f.planted};
  };
  const plan = planLegs(phase, stride, g);
  const far = build(plan.far, -HIP_DX);
  const near = build(plan.near, HIP_DX);
  const heel = (l) => (l.planted ? 0 : g.heel);
  return (
    <g>
      {/* Bridges the two hip joints. Invisible while the torso is upright and
          the only thing between a hard lean and a hole through the pelvis. */}
      <Stroke a={[-HIP_DX, hy]} b={[HIP_DX, hy]} fill={palette.trousers} w={THIGH_W} />
      {/* Far leg first, a shade darker. With no outlines available, tone is the
          only thing separating the two legs when they cross. */}
      <g opacity="0.82">
        <Pant pts={far.pts} fill={palette.trousersBack ?? palette.trousers} />
        <Shoe x={far.fx} y={far.fy} fill={palette.shoesBack ?? palette.shoes} heel={heel(far)} />
      </g>
      <Pant pts={near.pts} fill={palette.trousers} />
      <Shoe x={near.fx} y={near.fy} fill={palette.shoes} heel={heel(near)} />
    </g>
  );
};

const StandingLegs = ({palette, breathe}) => {
  const drop = breathe * 2;
  const leg = (hx, splay) => [
    [hx, PELVIS_Y + drop],
    [hx + splay * 3, (PELVIS_Y + ANKLE_Y) / 2 + drop * 0.4],
    [hx + splay * 7, ANKLE_Y],
  ];
  const far = leg(-HIP_DX, -1);
  const near = leg(HIP_DX, 1);
  return (
    <g>
      <g opacity="0.82">
        <Pant pts={far} fill={palette.trousersBack ?? palette.trousers} />
        <Shoe x={far[2][0]} y={ANKLE_Y} fill={palette.shoesBack ?? palette.shoes} heel={0} />
      </g>
      <Pant pts={near} fill={palette.trousers} />
      <Shoe x={near[2][0]} y={ANKLE_Y} fill={palette.shoes} heel={0} />
    </g>
  );
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

  const mix = m.gaitMix ?? (m.gait === 'run' ? 1 : 0);
  const g = gaitAt(mix);
  const stride = strideAt(mix, H_STRIDE_UNITS.walk, H_STRIDE_UNITS.run);

  const breathe = Math.sin(m.t * 0.62 * TAU * 0.34);
  const moving = m.moving;

  const plan = moving ? planLegs(m.phase, stride, g) : null;
  const gaitSink = plan ? plan.sink : 0;
  // Sitting drops the pelvis the whole way to the ground; the torso has to
  // travel with it or the figure sits down and leaves its body standing.
  const gaitY = m.bob * 0.3 * (1 - sit) + gaitSink;
  const bodyY = gaitY + sit * (SIT_HIP_Y - PELVIS_Y);

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
  const lean = m.lean + (moving ? g.bodyLean * 0.3 : 0) + sway * (1 - sit) + sit * SIT.lean;

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
        {bottom ? (
          <ArtLegs phase={m.phase} stride={stride} g={g} palette={palette}
                   bottom={bottom} moving={moving} breathe={breathe} sink={gaitY} sit={sit} />
        ) : moving ? (
          <WalkingLegs phase={m.phase} stride={stride} g={g} palette={palette} sink={bodyY} />
        ) : (
          <StandingLegs palette={palette} breathe={breathe} />
        )}

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
