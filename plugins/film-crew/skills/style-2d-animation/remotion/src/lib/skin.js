/**
 * Two-bone skinning for flat vector limbs.
 *
 * ── Why this exists ────────────────────────────────────────────────────────
 *
 * The Humaaans `bottom/` assets are often described as unusable for animation
 * because each one is "a static pose". That is half true and the useful half
 * is the other one: several of them (Sweatpants, Sprint) draw each leg as its
 * OWN path, and Sprint already rotates one about a hip pivot. The artist rigs
 * them. What is missing is not separability, it is a knee.
 *
 * Rotating a rigid leg about the hip gets you one degree of freedom, and the
 * solver needs two. Measured over a real cycle, the hip-to-ankle distance this
 * rig asks for varies from -14% to +7% of the standing leg length in a walk,
 * and -34% to +12% in a run. The walk you could just about fake by squashing
 * the leg along its axis. The run you cannot: a leg a third short does not read
 * as a bent knee, it reads as a broken one.
 *
 * So instead of moving the whole path, this moves its POINTS. Every coordinate
 * in the outline -- anchors and bezier handles alike -- is weighted by how far
 * down the leg it sits and transformed by a blend of two bones, thigh and shin.
 * That is standard linear blend skinning, and it works here because these
 * particular paths are clean ribbons: two long edges running hip to ankle,
 * capped top and bottom, with y increasing monotonically down the limb. The
 * y coordinate IS the skinning parameter, already there in the data.
 *
 * The result is the artist's own silhouette -- its taper, its curve, its
 * ankle -- bending at a knee the drawing never had.
 *
 * ── Limits ─────────────────────────────────────────────────────────────────
 *
 * This is only valid for paths shaped like limbs. Handing it a torso, or a leg
 * whose outline doubles back on itself in y, will produce a mess. It is not a
 * general-purpose warp and is not meant to be one.
 */

/** Absolute-only path grammar. These assets use M, L, C and Z, and nothing else. */
const NUM = /-?\d*\.?\d+(?:[eE][-+]?\d+)?/g;

/**
 * Splits a path into a token list of `{cmd, pts:[[x,y],...]}`.
 *
 * Coordinates are kept as point pairs rather than a flat number list so a
 * transform can be applied without knowing which command produced them --
 * every number in M/L/C is half of a coordinate, which is exactly why the
 * grammar is restricted to those.
 */
export const parsePath = (d) => {
  const out = [];
  const re = /([MLCZmlcz])([^MLCZmlcz]*)/g;
  let m;
  while ((m = re.exec(d)) !== null) {
    const cmd = m[1].toUpperCase();
    const nums = (m[2].match(NUM) || []).map(Number);
    if (cmd === 'Z') {
      out.push({cmd: 'Z', pts: []});
      continue;
    }
    const pts = [];
    for (let i = 0; i + 1 < nums.length; i += 2) pts.push([nums[i], nums[i + 1]]);
    out.push({cmd, pts});
  }
  return out;
};

/** Re-emits a token list, mapping every coordinate through `fn`. */
export const emitPath = (tokens, fn) =>
  tokens
    .map(({cmd, pts}) => {
      if (cmd === 'Z') return 'Z';
      const mapped = pts.map(([x, y]) => {
        const [nx, ny] = fn(x, y);
        return `${nx.toFixed(2)},${ny.toFixed(2)}`;
      });
      return cmd + mapped.join(' ');
    })
    .join(' ');

/**
 * The similarity transform taking segment `p0->p1` onto `q0->q1`.
 *
 * Scale is deliberately included rather than clamped away. It is what absorbs
 * the difference between the drawn leg's length and the one the solver asked
 * for, and on a flat silhouette a few percent along the limb axis is invisible
 * -- it is squash and stretch, which is a principle rather than a defect.
 */
const boneXform = (p0, p1, q0, q1) => {
  const px = p1[0] - p0[0];
  const py = p1[1] - p0[1];
  const qx = q1[0] - q0[0];
  const qy = q1[1] - q0[1];
  const pl = Math.hypot(px, py) || 1e-6;
  const ql = Math.hypot(qx, qy);
  const s = ql / pl;
  const ang = Math.atan2(qy, qx) - Math.atan2(py, px);
  const c = Math.cos(ang) * s;
  const sn = Math.sin(ang) * s;
  return (x, y) => {
    const dx = x - p0[0];
    const dy = y - p0[1];
    return [q0[0] + dx * c - dy * sn, q0[1] + dx * sn + dy * c];
  };
};

const smoothstep = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));

/**
 * Builds the point mapping for a limb.
 *
 * `rest` describes where the limb is in the artwork -- hip and ankle in the
 * asset's own coordinates. `pose` is where the rig wants it. `kneeT` is how far
 * down the limb the knee sits (0.5 is anatomically about right and is what the
 * bone lengths in the rig already assume), and `blend` is the width of the band
 * over which the two bones hand off, as a fraction of limb length.
 *
 * A blend of 0 gives a visible crease -- the outline shears where the weight
 * flips. Widening it rounds the knee, which is also what a real one does.
 */
export const skinLimb = ({rest, pose, kneeT = 0.5, blend = 0.34}) => {
  const {hip: h0, ankle: a0} = rest;
  const {hip, knee, ankle} = pose;

  const k0 = [h0[0] + (a0[0] - h0[0]) * kneeT, h0[1] + (a0[1] - h0[1]) * kneeT];

  const thigh = boneXform(h0, k0, hip, knee);
  const shin = boneXform(k0, a0, knee, ankle);

  // Axis of the limb as drawn, used only to ask "how far down is this point".
  const ax = a0[0] - h0[0];
  const ay = a0[1] - h0[1];
  const len2 = ax * ax + ay * ay || 1e-6;

  const lo = kneeT - blend / 2;

  return (x, y) => {
    const t = ((x - h0[0]) * ax + (y - h0[1]) * ay) / len2;
    const w = smoothstep((t - lo) / blend);
    if (w <= 0) return thigh(x, y);
    if (w >= 1) return shin(x, y);
    const [tx, ty] = thigh(x, y);
    const [sx, sy] = shin(x, y);
    return [tx + (sx - tx) * w, ty + (sy - ty) * w];
  };
};

/** Convenience: parse once, then deform per frame. */
export const compileLimb = (d) => {
  const tokens = parsePath(d);
  return (opts) => emitPath(tokens, skinLimb(opts));
};

/**
 * The hip and ankle of a limb path, taken as the midpoints of its topmost and
 * bottommost edges.
 *
 * Derived rather than configured, because a hand-written pivot per asset is a
 * number that silently rots the moment the artwork is re-fetched.
 */
export const limbRest = (d) => {
  const pts = parsePath(d).flatMap((t) => t.pts);
  if (!pts.length) return null;
  const ys = pts.map((p) => p[1]);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const band = (target) => {
    const tol = (yMax - yMin) * 0.06 + 1e-6;
    const xs = pts.filter((p) => Math.abs(p[1] - target) <= tol).map((p) => p[0]);
    return xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : null;
  };
  return {hip: [band(yMin), yMin], ankle: [band(yMax), yMax]};
};
