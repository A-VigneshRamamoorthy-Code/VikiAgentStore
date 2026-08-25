import {footOffset} from './locomotion.js';

/**
 * The leg rig: everything below the waist, as pure geometry.
 *
 * This is deliberately separate from the component that draws it, and the
 * reason is a defect that has now escaped review twice. Both times the rig
 * shipped something no test could see -- shoes drifting off ankles, then legs
 * that could not bend a knee -- because the only measurements of the posed
 * geometry lived in probe scripts written to diagnose the bug and deleted
 * once it was fixed. Geometry tangled up in JSX cannot be imported by a
 * checker, so it never gets a permanent test, so the next regression is
 * invisible again.
 *
 * Everything here is a function of numbers and returns numbers or a points
 * string. `scripts/check-physics.mjs` imports it directly and grades the leg
 * at every phase of a stride.
 */

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

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
export const flatten = (d) => {
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

/**
 * Break long edges up so the outline has somewhere to bend.
 *
 * This is the step that decides whether a knee is visible at all. A trouser
 * seam drawn as one straight line from hip to ankle has exactly two points,
 * and two points define a straight line no matter what skeleton is underneath
 * them -- so the leg bends and the seam does not, and the limb tears. Cutting
 * every edge into pieces a few units long costs nothing and removes the whole
 * class of problem.
 */
const resample = (pts, maxSeg = 3) => {
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    out.push(a);
    const n = Math.floor(Math.hypot(b[0] - a[0], b[1] - a[1]) / maxSeg);
    for (let s = 1; s < n; s++) {
      const u = s / n;
      out.push([a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]);
    }
  }
  return out;
};

/**
 * Two-bone IK: where the knee goes if the hip is here and the foot is there.
 *
 * The knee bows toward +x, which for a figure facing +x is forward -- the way
 * a human knee actually goes. Get that sign wrong and the character walks
 * with its knees backwards, which reads instantly as a bird.
 *
 * The reach is clamped rather than allowed to fail, because a solver that
 * returns NaN for an unreachable target puts the leg somewhere undefined for
 * one frame and the figure flickers. Clamping straightens the leg instead,
 * which is what a real leg does when you ask it to reach too far.
 */
export const ik = (hip, target, a, b, forward = 1) => {
  let dx = target[0] - hip[0];
  let dy = target[1] - hip[1];
  let dist = Math.hypot(dx, dy);
  const lo = Math.abs(a - b) + 1e-3;
  const hi = a + b - 1e-3;
  if (dist > hi) { const s = hi / dist; dx *= s; dy *= s; dist = hi; }
  if (dist < lo) { const s = lo / Math.max(dist, 1e-6); dx *= s; dy *= s; dist = lo; }
  const cosA = (a * a + dist * dist - b * b) / (2 * a * dist);
  const A = Math.acos(clamp(cosA, -1, 1)) * forward;
  const base = Math.atan2(dy, dx);
  const t1 = base - A;
  const knee = [hip[0] + a * Math.cos(t1), hip[1] + a * Math.sin(t1)];
  const ankle = [hip[0] + dx, hip[1] + dy];
  return {t1, t2: Math.atan2(ankle[1] - knee[1], ankle[0] - knee[0]), knee, ankle};
};

/**
 * The knee sits where the artist put it: 106 of a 208 leg, so just above half.
 */
export const KNEE_F = 106 / 208;

/**
 * How far either side of the knee the two bones blend into each other.
 *
 * A hard switch at the joint creases the outline into a sharp V, which is the
 * paper-puppet look. Blending over a band turns the crease into a knee. Too
 * wide and the whole limb curves like a hose instead of hinging -- measured
 * at 0.26 of leg length the shin visibly balloons -- so this is deliberately
 * narrow.
 */
const KNEE_BAND = 0.1;

export const smoothstep = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));

/**
 * Bend a drawn leg onto a solved skeleton.
 *
 * Every point of the outline is first described in the REST leg's own frame --
 * how far down the limb it lies, and how far to the side of it -- and then
 * rebuilt on the posed thigh and on the posed shin. Near the knee the two
 * answers are mixed, which is what makes the joint a joint.
 *
 * The property that matters: when the skeleton is straight and at its drawn
 * angle, both mappings collapse to the identity, so a resting leg is the
 * artist's drawing to the last decimal. The rig cannot quietly redraw the
 * character, which is the guarantee the old rigid cut-out gave and the reason
 * it was worth keeping.
 */
export const bendLeg = (leg, pose) => {
  const [hx, hy] = leg.hip;
  // The DRAWN axis measures the artwork; the SKELETON carries the pose. They
  // are different lengths on purpose -- see `len` in `prepareBottom` -- so the
  // position along the limb is measured in the drawing and then scaled onto
  // the bones. Using one length for both silently reintroduces the limp.
  const ux = leg.dx / leg.art;
  const uy = leg.dy / leg.art;
  const span = pose.span || leg.len;
  const k = span / leg.art;
  const a = span * KNEE_F;
  const band = span * KNEE_BAND;

  const c1 = Math.cos(pose.t1);
  const s1 = Math.sin(pose.t1);
  const c2 = Math.cos(pose.t2);
  const s2 = Math.sin(pose.t2);
  const [kx, ky] = pose.knee;

  let out = '';
  for (let i = 0; i < leg.outline.length; i++) {
    const px = leg.outline[i][0] - hx;
    const py = leg.outline[i][1] - hy;
    const s = (px * ux + py * uy) * k;  // along the limb, in skeleton units
    const n = px * -uy + py * ux;       // across it, unscaled: legs keep their width
    const w = smoothstep((s - (a - band)) / (2 * band));

    // Blend the two bones' SPINES, then step out by the drawn width along a
    // blended normal that is put back to unit length.
    //
    // Averaging the offset POINTS instead -- plain linear blend skinning, the
    // obvious way to write this -- quietly shortens that step to cos(bend/2),
    // because it is averaging two rotated copies of the same normal. The limb
    // loses 13% of its width at the 60 degrees a walk reaches and 33% at the
    // 96 degrees of a run: the classic pinched knee. Re-normalising costs one
    // square root and keeps the leg exactly its drawn width at every angle.
    //
    // Straight and at the drawn angle the two normals coincide and the two
    // spines agree, so this still collapses to the identity and a resting leg
    // is untouched artwork -- the guarantee the whole rig is built on.
    const spx = hx + s * c1;
    const spy = hy + s * s1;
    const sx = spx + (kx + (s - a) * c2 - spx) * w;
    const sy = spy + (ky + (s - a) * s2 - spy) * w;

    let nx = -s1 + (s1 - s2) * w;
    let ny = c1 + (c2 - c1) * w;
    const m = Math.hypot(nx, ny);
    if (m > 1e-6) {
      nx /= m;
      ny /= m;
    }
    out += `${(sx + n * nx).toFixed(1)},${(sy + n * ny).toFixed(1)} `;
  }
  return out;
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
      art: Math.hypot(dx, dy),    // the leg as DRAWN, splay and all
      /**
       * The leg as a BONE is the vertical drop, not the drawn length.
       *
       * The artist drew this figure standing with its feet apart -- one leg
       * splayed 16.6 degrees out, the other 6.7 the other way -- so measuring
       * hip-to-ankle gives two legs 7.3 units different in length. They are
       * not different lengths. They are the same leg at two angles, and both
       * ankles sit exactly 199.0 below their hip.
       *
       * Taking the drawn length as the bone made the figure LIMP, and did so
       * invisibly: the hip rides at whatever height the leg currently in
       * stance demands, so it sat 7 units lower on every other step and then
       * recovered. Measured over a cycle that was a 24-unit sawtooth -- 12% of
       * leg length, where a walk's whole bob should be under 10% and shaped
       * like two smooth arcs. The vertical drop is the same for both legs by
       * construction, which is the tell that it is the real quantity.
       */
      len: Math.abs(dy),
      /**
       * The drawn outline, as a dense polyline, ready to be bent.
       *
       * Flattening alone is not enough: a straight edge with a point at each
       * end stays straight however the skeleton under it bends, so the
       * trouser seam would run dead straight through a folded knee. The
       * resample is what gives the outline somewhere to bend.
       */
      outline: resample(flatten(l.el.d), 3),
      /**
       * The shoe's own outline, relative to its ankle, so the foot roll can be
       * measured rather than assumed. The pack's shoes carry far more length
       * in front of the ankle than behind it, so a toe-down roll digs several
       * times deeper than a toe-up one of the same angle.
       */
      sole: flatten(shoe.el.d),
      soleFlat: Math.max(...flatten(shoe.el.d).map((q) => q[1])),
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
 * Pose one leg: a thigh angle, a shin angle, and where the foot points.
 *
 * ── Why this is not a rotation ────────────────────────────────────────────
 *
 * The rig used to swing each leg as ONE rigid piece and fake the knee by
 * squashing the drawing along its own axis. That is a real technique, and it
 * is the wrong one here, for two reasons that both show on screen:
 *
 *  - a squashed leg is still a STRAIGHT leg. It telescopes rather than bends,
 *    so the figure marches on stilts. Omitting the knee is the single most
 *    common reason an animated walk reads as fake;
 *  - the squash has to be floored somewhere -- past about a quarter the limb
 *    reads as broken -- and the moment it hits that floor the drawn ankle
 *    stops agreeing with the solved one, so the shoe separates from the leg.
 *    That was still happening at two phases of every stride.
 *
 * So the leg is solved as a two-bone chain instead and the DRAWING is bent
 * onto it. The foot lands exactly where the contact solver puts it, at every
 * phase, because the solve is an IK solve rather than an approximation.
 */

/** Roughly how far a shoe reaches past its ankle, and so how far a tilt digs. */
const SHOE_TIP = 34;

/**
 * The stance-phase yield: the knee bend that stops a walk looking like a march.
 *
 * Just after the heel lands, the knee gives about 15-20 degrees and the body
 * sinks onto it, absorbing the fall. It is the least visible part of a walk
 * and the most missed, and leaving it out is precisely what makes a rig read
 * as a pogo stick -- the leg arrives straight, so the body has nothing to land
 * ON and simply changes direction.
 *
 * It also fixes WHERE the body is lowest. A straight-legged compass gait is
 * lowest at contact; a real one keeps descending through the yield and
 * bottoms out an eighth of a cycle later. Adding the yield moves the low
 * point on its own, which is the sign it is the real mechanism rather than a
 * curve laid on top of one.
 */
const YIELD = 0.019;

/** Fraction of stance over which the knee gives, then recovers. */
const YIELD_END = 0.56;

export const yieldAt = (p, duty) => {
  if (p < 0 || p >= duty) return 0;
  const u = p / duty / YIELD_END;
  return u >= 1 ? 0 : Math.sin(Math.PI * u);
};

/**
 * The foot's angle through stance -- the heel-to-toe rocker, in radians.
 *
 * Stance is not one event, it is four: the heel lands with the toes a few
 * degrees clear of the ground, the foot slaps flat, it stays flat while the
 * body travels over it, and then the heel lifts and the body rolls off the
 * ball of the foot. Holding a planted foot rigidly flat for all of it -- which
 * is what this rig did -- is why the feet read as boards.
 *
 * The sign is worth stating because it is not the intuitive one. The renderer
 * applies `rotate(-pitch)`, and SVG's positive rotation turns x toward y --
 * downward, since y grows down -- so a POSITIVE pitch lifts the toes. Getting
 * that backwards is not a subtle error but it is a silent one: it lifted the
 * ankle at heel strike, which bent the knee 24 degrees at the exact moment a
 * real leg is straightest, and it left the foot flat through push-off, where
 * the heel should be rising. Both showed up as numbers before they showed up
 * on screen.
 */
const ROLL_STRIKE = 5 * (Math.PI / 180);    // toes up as the heel lands
const ROLL_OFF = -18 * (Math.PI / 180);     // toes down, rolling off the ball
const FLAT_IN = 0.17;                       // heel strike -> foot flat
const FLAT_OUT = 0.62;                      // foot flat -> heel off

export const footRoll = (p, duty) => {
  if (p < duty) {
    const u = p / duty;
    if (u < FLAT_IN) return ROLL_STRIKE * (1 - u / FLAT_IN);
    if (u < FLAT_OUT) return 0;
    return ROLL_OFF * smoothstep((u - FLAT_OUT) / (1 - FLAT_OUT));
  }
  /**
   * Swing is part of the SAME curve, not a separate rule.
   *
   * Treating stance and swing as two formulas glued together at toe-off left
   * the foot pointed 15 degrees down on one frame and flat on the next, and
   * the ankle jumped 20 units with it -- a one-frame snap that the eye reads
   * as a limp. The foot leaves the ground where push-off left it, unwinds to
   * neutral to clear the ground, and is back at heel-strike attitude by the
   * time it lands.
   */
  const u = (p - duty) / (1 - duty);
  return ROLL_OFF * (1 - smoothstep(u / 0.4)) + ROLL_STRIKE * smoothstep((u - 0.6) / 0.4);
};

export const poseLeg = (L, f, drop) => {
  const a = L.len * KNEE_F;
  const b = L.len - a;

  /**
   * Standing is the drawing, exactly as drawn -- splay and all.
   *
   * A figure with nowhere to walk to has no business being straightened up.
   * The bones here span the leg AS DRAWN rather than the shared skeleton
   * length, which makes the bend the identity and hands the artist's leg back
   * untouched. `span` travels with the pose for exactly this reason: the two
   * regimes measure the limb differently, and a leg that used one length to
   * pose and another to draw comes out 4% short.
   */
  if (!f) {
    const rest = ik(L.hip, [L.ankle[0], L.ankle[1]], L.art * KNEE_F,
                    L.art - L.art * KNEE_F, L.dx >= 0 ? 1 : -1);
    return {...rest, pitch: 0, span: L.art};
  }

  /**
   * The ankle is never lower than the foot's own roll allows.
   *
   * This one line replaces the planted/swinging special case that used to sit
   * here. A foot pitched toes-down reaches below its ankle, so the ankle has
   * to rise by that much or the toe goes through the ground -- and that is
   * true whether the foot is bearing weight or swinging past. Stating it as a
   * constraint rather than as two rules is what makes the heel actually lift
   * at push-off: the ankle rises because the toe is still down, which is what
   * a heel lifting IS, and it falls out instead of being posed.
   *
   * The correction is PURELY VERTICAL, so the foot's contact does not move
   * downrange and the solver's no-slip guarantee survives it intact.
   */
  const [tx, ty0] = footTarget(L, f);
  const ty = ty0 - Math.max(0, soleDip(L, f.roll || 0) + (f.y || 0));
  /**
   * The knee bows the way the figure is walking.
   *
   * These assets are drawn with the feet apart, so one leg trails behind the
   * hip and the other leads. Choosing the bend direction from the DRAWN leg
   * rather than from a constant is what keeps both knees pointing the same
   * way; picking a constant gave the upstage leg a backwards knee.
   */
  const solved = ik(L.hip, [tx, ty - drop], a, b, 1);
  solved.span = L.len;

  /**
   * A planted foot rolls; it does not sit flat.
   *
   * Real stance is a rocker: the heel lands with the toes a few degrees up,
   * the foot flattens, and at the end the heel lifts and the body pivots over
   * the ball of the foot. Holding it rigidly flat for the whole of stance is
   * what makes feet look glued on. The roll is written against the phase
   * because that is what it is -- an event schedule, not a curve.
   *
   * A swinging foot instead trails its own shin, levelling out as it reaches
   * for the next contact, and is faded in by GROUND CLEARANCE so that a foot
   * with nowhere to tilt into cannot tilt its toe through the grass.
   */
  return {...solved, pitch: f.roll || 0};
};

/**
 * How far a shoe pitched by `pitch` reaches below where it sits when flat.
 *
 * Measured off the artist's own sole rather than a shoe-length constant,
 * because the pack's shoes are not symmetric about the ankle -- there is far
 * more shoe in front of it than behind, so a toe-down roll digs several times
 * deeper than a toe-up one of the same angle.
 */
const soleDip = (L, pitch) => {
  if (!pitch || !L.sole) return 0;
  const c = Math.cos(-pitch);
  const sn = Math.sin(-pitch);
  let low = -Infinity;
  for (const [px, py] of L.sole) low = Math.max(low, px * sn + py * c);
  return Math.max(0, low - L.soleFlat);
};
export const artSink = (bottom, plan) => {
  if (!bottom || !plan) return 0;
  const pairs = [[bottom.legs[0], plan.far], [bottom.legs[1], plan.near]];
  const L0 = bottom.legs[0].len;
  const xs = plan.support || 0;
  let drop = L0 - Math.sqrt(Math.max(0, L0 * L0 - xs * xs));
  for (const [L, f] of pairs) {
    if (!f || !f.planted) continue;
    const reach = Math.sqrt(Math.max(0, L.len * L.len - f.x * f.x));
    /**
     * The yield is added HERE, as extra hip drop, rather than as a knee angle.
     *
     * Lowering the hip over a planted foot forces the IK to bend the knee by
     * exactly the right amount to keep the foot where it is, so the give and
     * the contact can never disagree. Posing the knee directly would have
     * moved the foot and reintroduced the slip this rig exists to prevent.
     */
    /**
     * The heel lift RELIEVES this leg's claim on the hip.
     *
     * Without this term the trailing leg holds the hip down until the instant
     * its foot leaves the ground, at which point the hip snaps up 12 units in
     * one frame -- a bounce, and the reason the knee unbent and re-bent in the
     * middle of the stride. Subtracting the lift is not a smoothing hack; it
     * is what a heel lifting is FOR. The body keeps rising over the ball of
     * the foot while the ankle rises with it, so the leg never has to choose
     * between staying straight and staying on the ground.
     */
    const lift = Math.max(0, soleDip(L, f.roll || 0) + (f.y || 0));
    const d = L.ankle[1] - L.hip[1] - lift - reach + (f.give || 0) * L.len * YIELD;
    drop = Math.max(drop, d);
  }
  return drop;
};


/**
 * Where both feet are this frame, and what each is doing.
 *
 * The two schedules a foot carries -- its heel-to-toe roll and its knee's
 * give -- are functions of STANCE PHASE, not of where the foot has got to, so
 * they are attached here where the phase is known rather than rediscovered
 * from a position further down.
 */
export const planFeet = (phase, stride, g) => {
  const pn = phase;
  const pf = (phase + 0.5) % 1;
  const near = footOffset(pn, stride, g);
  const far = footOffset(pf, stride, g);
  near.roll = footRoll(pn, g.duty);
  far.roll = footRoll(pf, g.duty);
  near.give = yieldAt(pn, g.duty);
  far.give = yieldAt(pf, g.duty);
  /**
   * Where the body's weight is, as one continuous sawtooth.
   *
   * This is the COMPASS GAIT: the pelvis vaults over the supporting foot like
   * an inverted pendulum, so it is lowest at contact -- legs at full spread --
   * and highest at midstance, once per step. The support point runs +A to -A
   * over each half-cycle and jumps back, but the height it implies depends on
   * its DISTANCE from under the hip, and that is even in x, so the jump costs
   * nothing: both feet are the same distance out at the changeover, which is
   * what double support means.
   *
   * Deriving the bob this way replaced taking a max over whichever legs
   * happened to be planted. The max is a valid FLOOR -- no leg may be asked to
   * over-extend -- but it is a terrible curve, because it holds the hip as
   * high as every leg will allow and then drops it 16 units the frame the next
   * foot lands. A leg can always bend more than it has to; it can never bend
   * less than it must. Only one of those is a constraint.
   */
  const A = (stride * g.duty) / 2;
  const support = A * (1 - 2 * ((phase % 0.5) / 0.5));
  return {near, far, support};
};
