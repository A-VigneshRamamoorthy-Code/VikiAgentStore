/**
 * The palette, lifted verbatim from `scripts/look.py`.
 *
 * These are the same fourteen tokens the Python renderer paints with, so a
 * frame from either engine can be compared against the other without first
 * arguing about colour. If `look.py` moves, this moves with it -- there is a
 * check for exactly that in `bench.mjs`.
 */
export const PURSUIT = {
  sky: '#96d0ea',
  ground: '#b0b4ba',
  far: '#6c92b0',
  mid: '#c4cdd3',
  near: '#ded6c7',
  skin: '#e8a880',
  hair: '#3a2826',
  shirt: '#ce4a38',
  trouser: '#2c3856',
  shoe: '#242228',
  ink: '#1c1e28',
  accent: '#e02e30',
  accent2: '#f7be30',
  shadow: '#1a2834',
};

const hex2rgb = (h) => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];

const rgb2hex = (c) =>
  '#' + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');

/** Mix two palette colours. `k` of 0 returns `a`, 1 returns `b`. */
export const mix = (a, b, k) => {
  const [ar, ag, ab] = hex2rgb(a);
  const [br, bg, bb] = hex2rgb(b);
  return rgb2hex([ar + (br - ar) * k, ag + (bg - ag) * k, ab + (bb - ab) * k]);
};

/** Lighten toward white; `k` of 1 is white. */
export const tint = (c, k) => mix(c, '#ffffff', k);

/** Darken toward the ink colour rather than toward black. */
export const shade = (c, k) => mix(c, PURSUIT.ink, k);

/**
 * Push a colour toward the sky by distance.
 *
 * This is the single most load-bearing trick in the style: it is what makes a
 * flat vector drawing read as having depth. Everything far away loses contrast
 * against the air in front of it, so a "far" layer is not a darker version of a
 * "near" one, it is a *skywards* one.
 */
export const depth = (c, k) => mix(c, PURSUIT.sky, k);
