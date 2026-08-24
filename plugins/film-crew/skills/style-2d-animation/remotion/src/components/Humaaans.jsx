import React from 'react';
import {GAITS, gaitAt, strideAt, footOffset} from '../lib/locomotion';

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

const HIP_DX = 28;
// Humaaans draws a leg with the same weight as a sleeve. At 46 these read as
// wire, and the figure came out as a torso on stilts.
const PANT_W = 78;
const SHOE_W = 60;

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

/** A flat Humaaans limb: one rounded stroke, no outline. */
const Pant = ({pts, fill, w}) => (
  <path
    d={pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')}
    fill="none"
    stroke={fill}
    strokeWidth={w}
    strokeLinecap="round"
    strokeLinejoin="round"
  />
);

const Shoe = ({x, y, fill, heel}) => (
  <g transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(-heel * 12).toFixed(1)})`}>
    <path d={`M-14 -12 L${SHOE_W - 14} -12 Q${SHOE_W - 2} -12 ${SHOE_W - 2} 2 L${SHOE_W - 2} 8 Q${SHOE_W - 2} 14 ${SHOE_W - 12} 14 L-14 14 Q-24 14 -24 2 Q-24 -12 -14 -12 Z`}
          fill={fill} />
  </g>
);

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
      <Pant pts={[[-HIP_DX, hy], [HIP_DX, hy]]} fill={palette.trousers} w={PANT_W} />
      {/* Far leg first, a shade darker. With no outlines available, tone is the
          only thing separating the two legs when they cross. */}
      <g opacity="0.82">
        <Pant pts={far.pts} fill={palette.trousersBack ?? palette.trousers} w={PANT_W} />
        <Shoe x={far.fx} y={far.fy} fill={palette.shoesBack ?? palette.shoes} heel={heel(far)} />
      </g>
      <Pant pts={near.pts} fill={palette.trousers} w={PANT_W} />
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
        <Pant pts={far} fill={palette.trousersBack ?? palette.trousers} w={PANT_W} />
        <Shoe x={far[2][0]} y={ANKLE_Y} fill={palette.shoesBack ?? palette.shoes} heel={0} />
      </g>
      <Pant pts={near} fill={palette.trousers} w={PANT_W} />
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
export const HumaaansCharacter = ({m, look, scale = 1, shadow = true}) => {
  const {palette, head, body} = look;

  const mix = m.gaitMix ?? (m.gait === 'run' ? 1 : 0);
  const g = gaitAt(mix);
  const stride = strideAt(mix, H_STRIDE_UNITS.walk, H_STRIDE_UNITS.run);

  const breathe = Math.sin(m.t * 0.62 * TAU * 0.34);
  const moving = m.moving;

  const plan = moving ? planLegs(m.phase, stride, g) : null;
  const gaitSink = plan ? plan.sink : 0;
  const bodyY = m.bob * 0.3 + gaitSink;

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
  const lean = m.lean + (moving ? g.bodyLean * 0.3 : 0) + sway;

  return (
    <g transform={`translate(${m.x.toFixed(2)} ${(m.y ?? 0).toFixed(2)}) scale(${scale})`}>
      {shadow && (
        <ellipse
          cx={0}
          cy={4}
          rx={(moving ? 74 : 84) * (1 - air * 0.42)}
          ry={13 * (1 - air * 0.3)}
          fill={palette.shadow ?? '#191847'}
          opacity={0.16 * (1 - air * 0.6)}
        />
      )}
      <g transform={`scale(${m.facingScale.toFixed(3)} 1)`}>
        {/* Legs in ground space, outside the bob — a foot that bobs with the
            body is a foot that is not standing on anything. */}
        {moving ? (
          <WalkingLegs phase={m.phase} stride={stride} g={g} palette={palette} sink={bodyY} />
        ) : (
          <StandingLegs palette={palette} breathe={breathe} />
        )}

        <g transform={`translate(0 ${bodyY.toFixed(2)}) rotate(${lean.toFixed(2)} 0 ${PELVIS_Y})`}>
          <g transform={`translate(${FIG.bodyX} ${FIG.bodyTop})`}>
            <HPart asset={body} palette={palette} />
          </g>
          <g transform={`translate(${FIG.headX} ${FIG.headTop})`}>
            <HPart asset={head} palette={palette} />
          </g>
        </g>
      </g>
    </g>
  );
};
