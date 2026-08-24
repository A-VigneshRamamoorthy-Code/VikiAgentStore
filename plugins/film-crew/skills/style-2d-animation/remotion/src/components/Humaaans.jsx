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
const mul = (m, n) => [
  m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1],
  m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
  m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5],
];

/**
 * Fold a transform chain left to right, the order SVG applies it in.
 *
 * Variadic on purpose. The pairwise version was called with six matrices
 * once, silently used the first two and threw the rest away, and the seated
 * figure it measured came out flat on the ground -- a wrong answer with no
 * error attached, which is the expensive kind.
 */
const compose = (...ms) => ms.reduce(mul, [1, 0, 0, 1, 0, 0]);

const matrixOf = (tr) => {
  let m = [1, 0, 0, 1, 0, 0];
  if (!tr) return m;
  for (const [, fn, argstr] of String(tr).matchAll(/([a-zA-Z]+)\s*\(([^)]*)\)/g)) {
    const v = (argstr.match(/-?\d*\.?\d+(?:e-?\d+)?/gi) || []).map(Number);
    if (fn === 'translate') m = compose(m, [1, 0, 0, 1, v[0] || 0, v[1] || 0]);
    else if (fn === 'scale') m = compose(m, [v[0] ?? 1, 0, 0, v[1] ?? v[0] ?? 1, 0, 0]);
    else if (fn === 'matrix') m = compose(m, v.slice(0, 6));
    else if (fn === 'rotate') {
      const r = ((v[0] || 0) * Math.PI) / 180;
      const c = Math.cos(r);
      const sn = Math.sin(r);
      let rot = [c, sn, -sn, c, 0, 0];
      if (v.length >= 3) {
        rot = compose([1, 0, 0, 1, v[1], v[2]], compose(rot, [1, 0, 0, 1, -v[1], -v[2]]));
      }
      m = compose(m, rot);
    }
  }
  return m;
};

const applyM = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

/** A rotation matrix, radians, in SVG's sense: positive turns x toward y. */
const rotM = (r) => [Math.cos(r), Math.sin(r), -Math.sin(r), Math.cos(r), 0, 0];

/** Where a piece's own origin lands: its placement, however it was written. */
const lastTranslate = (tr) => applyM(matrixOf(tr), 0, 0);

/**
 * Points ON a path, with its curves flattened.
 *
 * The difference between this and reading every number in the `d` string is a
 * cubic's CONTROL points, which lie outside the curve they steer. Measuring a
 * limb's lowest point off the control hull over-estimates how far the ink
 * reaches, and the seated figure it produced hovered a clear 30 units above
 * the grass -- a wrong answer that looked like a posing problem for as long as
 * it took to stop trusting the estimate.
 *
 * Humaaans paths use M/L/C/Z only, but relative forms appear in the pack, so
 * both cases are handled. Eight samples per curve is well under a pixel here.
 */
const flatten = (d) => {
  const toks = String(d).match(/[MmLlHhVvCcZz]|-?\d*\.?\d+(?:e-?\d+)?/gi) || [];
  const pts = [];
  let i = 0;
  let cx = 0;
  let cy = 0;
  let sx = 0;
  let sy = 0;
  let cmd = 'M';
  const num = () => Number(toks[i++]);
  const push = (x, y) => { pts.push([x, y]); cx = x; cy = y; };
  while (i < toks.length) {
    if (/[A-Za-z]/.test(toks[i])) cmd = toks[i++];
    if (i >= toks.length && !/[Zz]/.test(cmd)) break;
    const rel = cmd === cmd.toLowerCase();
    const ox = rel ? cx : 0;
    const oy = rel ? cy : 0;
    switch (cmd.toUpperCase()) {
      case 'M': push(num() + ox, num() + oy); sx = cx; sy = cy; cmd = rel ? 'l' : 'L'; break;
      case 'L': push(num() + ox, num() + oy); break;
      case 'H': push(num() + ox, cy); break;
      case 'V': push(cx, num() + oy); break;
      case 'C': {
        const x0 = cx;
        const y0 = cy;
        const x1 = num() + ox;
        const y1 = num() + oy;
        const x2 = num() + ox;
        const y2 = num() + oy;
        const x3 = num() + ox;
        const y3 = num() + oy;
        for (let t = 1; t <= 8; t++) {
          const u = t / 8;
          const v = 1 - u;
          pts.push([
            v * v * v * x0 + 3 * v * v * u * x1 + 3 * v * u * u * x2 + u * u * u * x3,
            v * v * v * y0 + 3 * v * v * u * y1 + 3 * v * u * u * y2 + u * u * u * y3,
          ]);
        }
        cx = x3; cy = y3;
        break;
      }
      case 'Z': push(sx, sy); break;
      default: i++; break;
    }
  }
  return pts;
};

/** The lowest point a drawn element reaches once `m` is applied to it. */
const lowestY = (el, m) => {
  let low = -Infinity;
  for (const [px, py] of flatten(el.d)) low = Math.max(low, applyM(m, px, py)[1]);
  return low;
};

/** Every numeric literal in a path or a points list, in order. */
const NUMS = /-?\d*\.?\d+(?:e-?\d+)?/gi;
const coords = (src) => {
  const v = (String(src).match(NUMS) || []).map(Number);
  const out = [];
  for (let i = 0; i + 1 < v.length; i += 2) out.push([v[i], v[i + 1]]);
  return out;
};

/**
 * Pulls the rigid limb pieces out of a `bottom/` asset.
 *
 * ── What changed, and why ─────────────────────────────────────────────────
 *
 * This used to compile each leg into a deformable skin and warp it onto a
 * solved two-bone chain. That is the wrong tool for this artwork, and it is
 * the cause of nearly every defect reported against these figures:
 *
 *  - warping a nearly-straight drawn leg through a bent pose SHEARS the
 *    outline, which is what tore shoes off ankles;
 *  - the warp needs a hip, and `limbRest` reads a leg's hip as the midpoint of
 *    its topmost band -- which for these assets is the WAISTBAND -- so slicing
 *    the trousers into two independently-warped ribbons threw the pelvis away
 *    and left a hole that had to be plugged with an invented rectangle;
 *  - and a warp is free to change a limb's length, so the legs quietly grew.
 *
 * Humaaans is flat cut-out artwork. The correct rig for cut-out artwork is a
 * cut-out rig: every drawn piece stays EXACTLY as drawn, and all motion is a
 * rotation about a joint. Nothing is deformed, nothing is redrawn, nothing is
 * invented. A shoe cannot come off an ankle because it is a child of the leg
 * that carries it.
 *
 * Pairing comes out of the drawing rather than a table: a leg is a `@clothing`
 * path tall enough to span the piece (the short ones are cuffs, which must not
 * be rigged), its hip is the midpoint of its own waistband, and its ankle is
 * the translate the artist gave the nearest shoe.
 *
 * Returns `null` for assets whose legs are fused into one path (the
 * Skinny-Jeans family). Those genuinely cannot be articulated.
 */
export const prepareBottom = (asset) => {
  const shoes = asset.els
    .filter((e) => e.fill === '@shoe' && e.d)
    .map((e) => ({el: e, at: lastTranslate(e.transform)}));

  const limbs = asset.els
    .filter((e) => e.fill === '@clothing' && e.d)
    .map((e) => {
      const pts = coords(e.d);
      if (!pts.length) return null;
      const ys = pts.map((q) => q[1]);
      const top = pts.filter((q) => q[1] < Math.min(...ys) + 6).map((q) => q[0]);
      if (!top.length) return null;
      const toe = pts.filter((q) => q[1] > Math.max(...ys) - 6).map((q) => q[0]);
      return {
        el: e,
        span: Math.max(...ys) - Math.min(...ys),
        hip: [(Math.min(...top) + Math.max(...top)) / 2, Math.min(...ys)],
        toe: toe.length ? (Math.min(...toe) + Math.max(...toe)) / 2 : null,
      };
    })
    .filter((l) => l && l.span > asset.h * 0.6);

  if (limbs.length < 2 || !shoes.length) return null;

  limbs.sort((a, b) => a.hip[0] - b.hip[0]);
  const pick = [limbs[0], limbs[limbs.length - 1]];

  /**
   * Shoes are matched to legs at the ANKLE, and as a one-to-one assignment.
   *
   * The obvious "nearest shoe to this hip" is wrong twice over: the hips of a
   * standing figure are ~10 apart while its feet are ~90 apart, so both hips
   * are nearest the same shoe -- and nothing stops two legs claiming it. The
   * first run of this code did exactly that and gave one leg a shoe and the
   * other a bare stump. Comparing the foot ends and testing both pairings is
   * two lines and cannot produce that.
   */
  const foot = (l) => (l.toe == null ? l.hip[0] : l.toe);
  const cost = (a, b) => Math.abs(foot(pick[0]) - a.at[0]) + Math.abs(foot(pick[1]) - b.at[0]);
  const [s0, s1] = shoes.length < 2
    ? [shoes[0], shoes[0]]
    : cost(shoes[0], shoes[1]) <= cost(shoes[1], shoes[0])
      ? [shoes[0], shoes[1]]
      : [shoes[1], shoes[0]];

  const legs = pick.map((l, i) => {
    const shoe = i === 0 ? s0 : s1;
    const dx = shoe.at[0] - l.hip[0];
    const dy = shoe.at[1] - l.hip[1];
    return {
      el: l.el,
      shoe: shoe.el,
      hip: l.hip,
      ankle: shoe.at,
      dx,
      dy,
      len: Math.hypot(dx, dy),
      rest: Math.atan2(dx, dy),   // angle off vertical, as drawn
    };
  });

  /**
   * The ground is where the artist drew the soles, not a constant.
   *
   * This is the same rule that fixed the leg length: the drawing is the ruler.
   * Measuring the lowest inked point of the standing pose gives the ground
   * line in the asset's own coordinates, which is what the seated pose is
   * then placed against -- so a pack with differently proportioned figures
   * needs no new number anywhere.
   */
  let ground = -Infinity;
  for (const l of legs) {
    for (const e of [l.el, l.shoe]) ground = Math.max(ground, lowestY(e, matrixOf(e.transform)));
  }

  // Far leg first: the one whose ankle is further from the direction of travel
  // reads as the upstage one, and it is drawn first so the near leg overlaps it.
  return {legs, len: legs[0].len, ground};
};

/**
 * Where a leg's foot has to be, in the asset's own coordinates.
 *
 * `footOffset` already returns the solved contact -- x downrange, y lifted --
 * and that is the ONLY thing allowed to place a foot. Its `y` is negative for
 * a raised foot, and the asset's y also grows downward, so the lift ADDS; the
 * first version subtracted it and drove every swinging foot into the ground,
 * which then showed up as a limp rather than as an obvious sign error. Deriving the pose from
 * the solver rather than from a sine is what stops the moonwalking: a planted
 * foot is planted because the solver says so, not because the drawing happens
 * to line up.
 */
const footTarget = (L, f) => [
  // Measured from the HIP, not from where the foot happens to be drawn. These
  // assets are a standing pose with the feet about 94 apart, so offsetting the
  // drawn ankle keeps that splay baked in and the figure walks with its legs
  // permanently astride -- which is exactly how it first came out.
  L.hip[0] + (f ? f.x : 0),
  L.ankle[1] + (f ? f.y : 0),
];

/**
 * Pose one leg: an angle, and a foreshortening along its own length.
 *
 * A cut-out leg is one rigid piece, so it cannot bend a knee -- and the first
 * version of this rig, which only rotated, showed exactly why that matters:
 * the swinging foot swept through the ground on every pass. A straight leg is
 * LONGER than a bent one, so a figure whose legs only rotate cannot get its
 * feet past each other without ploughing a furrow.
 *
 * The fix is the same one a camera gives you for free: a bent leg, seen flat,
 * is a shorter leg. Scaling along the limb's own axis foreshortens it without
 * touching its width or its outline, so the drawing stays the drawing. The
 * shoe is exempt -- feet do not foreshorten when a knee bends -- so it is
 * carried to the new ankle at full size instead.
 *
 * `k` is floored because past about a quarter the leg stops reading as bent
 * and starts reading as broken; the residual is absorbed by the pelvis.
 */
const K_MIN = 0.74;

/** Roughly how far a shoe reaches past its ankle, and so how far a tilt digs. */
const SHOE_TIP = 34;

const poseLeg = (L, f, drop) => {
  // Standing is the drawing, exactly as drawn: no rotation, no scale, no
  // solve. A rig that "poses" a rest pose is a rig that redraws the artist.
  if (!f) return {theta: L.rest, k: 1, pitch: 0};

  const [tx, ty] = footTarget(L, f);
  const dx = tx - L.hip[0];
  const dy = ty - L.hip[1] - drop;
  const dist = Math.hypot(dx, dy);
  const k = clamp(dist / L.len, K_MIN, 1);
  const theta = Math.atan2(dx, Math.max(1e-6, dy));

  /**
   * A planted foot is flat, because it is the thing being pivoted over. A
   * swinging one trails the shin -- toe down as it leaves, levelling as it
   * reaches -- which is half the leg's own angle and needs no curve of its own.
   *
   * The pitch is faded out by HEIGHT rather than switched on by the planted
   * flag, because a foot a few units off the ground is still a foot that can
   * put its toe through the ground: pitching about the ankle swings the toe
   * down about half a shoe length, which measured 7.5 units of grass at
   * toe-off. Tying it to clearance means the foot can only tilt once it has
   * somewhere to tilt into.
   */
  const clearance = clamp(-f.y / (SHOE_TIP * 0.5), 0, 1);
  return {theta, k, pitch: f.planted ? 0 : theta * 0.5 * clearance};
};

/**
 * How far the pelvis must drop for the planted foot to stay on the ground.
 *
 * With rigid legs this is not a number to tune, it is arithmetic: a leg swung
 * to angle t reaches `len * cos t` below its hip, so the hip comes down by
 * exactly the difference. That is the compass gait -- it is where the bob in a
 * walk actually comes from, rather than something added on top of one.
 *
 * The reduction is a MAXIMUM over the planted legs, and that pairs with the
 * foreshortening above: the most extended leg is straight and sets the hip
 * height, and any other leg that is also down has slack to lose, which it
 * loses by bending. That is what double support looks like in a real walk --
 * front leg straight, back leg bent -- and it falls out rather than being
 * posed. The two legs are not the same length, because the artist drew one
 * splayed further than the other, so this is not symmetric and cannot be
 * short-cut to a single sine.
 */
export const artSink = (bottom, plan) => {
  if (!bottom || !plan) return 0;
  const pairs = [[bottom.legs[0], plan.far], [bottom.legs[1], plan.near]];
  let drop = null;
  for (const [L, f] of pairs) {
    if (!f || !f.planted) continue;
    const reach = Math.sqrt(Math.max(0, L.len * L.len - f.x * f.x));
    const d = L.ankle[1] - L.hip[1] - reach;
    drop = drop === null ? d : Math.max(drop, d);
  }
  return drop === null ? 0 : drop;
};

/** One drawn element, painted from the palette, otherwise untouched. */
const RawEl = ({el, fill}) => {
  const {tag, ...rest} = el;
  const props = {};
  for (const [k, v] of Object.entries(rest)) props[attrName(k)] = v;
  if (fill) props.fill = fill;
  return React.createElement(tag, props);
};

/**
 * One leg of real artwork, rotated about its hip. Nothing else.
 *
 * The shoe is inside the same rotation, carrying its own original transform,
 * so it stays welded to the ankle at every angle by construction rather than
 * by a correction term.
 */
const ArtLeg = ({leg, theta, k, pitch, fill, shoeFill}) => {
  const [hx, hy] = leg.hip;
  const T = `translate(${hx.toFixed(2)} ${hy.toFixed(2)})`;
  const Tinv = `translate(${(-hx).toFixed(2)} ${(-hy).toFixed(2)})`;
  const deg = (r) => ((r * 180) / Math.PI).toFixed(2);

  /**
   * Stand the limb up, foreshorten along it, swing it out.
   *
   * The signs are worth deriving rather than guessing. SVG's `rotate(a)` sends
   * (x, y) to (x cos a - y sin a, x sin a + y cos a), so a limb drawn at
   * `rest` off vertical is (sin rest, cos rest) * len -- and `rotate(rest)`
   * carries it to (0, len), straight down its own axis, which is the frame the
   * foreshortening has to happen in. `rotate(-theta)` then takes (0, k*len) to
   * k*len * (sin theta, cos theta), the pose asked for.
   *
   * The obvious `rotate(theta - rest)` is a REFLECTION about the rest angle,
   * not a rotation to it: it is right when theta equals rest and wrong
   * everywhere else, so it stands up perfectly and falls apart the moment the
   * figure takes a step -- which is precisely how it presented.
   */
  const limb = `${T} rotate(${deg(-theta)}) scale(1 ${k.toFixed(4)}) rotate(${deg(leg.rest)}) ${Tinv}`;

  // The shoe rides to wherever the shortened leg ended, at full size, and
  // pitches on its OWN angle rather than the leg's. A planted foot is flat --
  // it is the thing the leg is pivoting over -- and inheriting the leg's swing
  // was tipping the toe a centimetre into the grass at every mid-stance.
  // Because the shoe is placed FROM the leg's solved ankle rather than
  // alongside it, it still cannot drift off however the leg is posed.
  const ax = leg.hip[0] + k * leg.len * Math.sin(theta);
  const ay = leg.hip[1] + k * leg.len * Math.cos(theta);
  const shoe = `translate(${(ax - leg.ankle[0]).toFixed(2)} ${(ay - leg.ankle[1]).toFixed(2)}) `
    + `translate(${leg.ankle[0].toFixed(2)} ${leg.ankle[1].toFixed(2)}) rotate(${deg(-pitch)}) `
    + `translate(${(-leg.ankle[0]).toFixed(2)} ${(-leg.ankle[1]).toFixed(2)})`;

  return (
    <g>
      <g transform={limb}><RawEl el={leg.el} fill={fill} /></g>
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
const SIT_SWING = 86;
const SIT_SPREAD = 3;
const SIT_K = 0.92;

/**
 * The seated pose, and the height it puts the hips at.
 *
 * `drop` is MEASURED off the posed geometry rather than derived, because the
 * legs have thickness: the underside of a horizontal limb is half a trouser
 * width below its own axis, and that -- not the ankle -- is what rests on the
 * grass. Assuming the ankle sets the height buries the thigh in the ground.
 */
export const sitPose = (bottom) => {
  const legs = bottom.legs.map((L, i) => {
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
    // The foot comes round WITH the leg here, unlike a walk cycle where a
    // planted foot stays flat. Someone sitting with their legs out has their
    // toes up, and a shoe left level would read as a broken ankle.
    return {theta, k: SIT_K, pitch: theta};
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
    const {theta, k} = legs[i];
    const [hx, hy] = L.hip;
    // Exactly the chain `ArtLeg` renders, or the measurement is of a pose the
    // film never shows.
    const limb = compose(
      [1, 0, 0, 1, hx, hy], rotM(-theta), [1, 0, 0, k, 0, 0], rotM(L.rest),
      [1, 0, 0, 1, -hx, -hy], matrixOf(L.el.transform),
    );
    low = Math.max(low, lowestY(L.el, limb));
  });

  return {legs, drop: bottom.ground - low};
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
  const g = scaleGait(gIn);
  const near = footOffset(phase, stride, g);
  const far = footOffset((phase + 0.5) % 1, stride, g);
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
