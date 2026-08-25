/**
 * Timing — spacing curves taken from traditional 2D practice.
 *
 * ── Why this file exists ────────────────────────────────────────────────────
 *
 * A hand animator does not think in cubic-beziers. They draw a TIMING CHART:
 * a little ladder beside the key, with a tick for every in-between, bunched
 * where the motion is slow and spread where it is fast. That chart is an
 * easing curve — it is *literally* a plot of position against frame — and the
 * conventions for drawing one are far more specific than "ease-in-out".
 *
 * Everything here is that vocabulary, made numeric:
 *
 *     "spacing over timing equals speed"
 *
 * so a curve is fully described by WHERE the in-betweens sit, and the craft is
 * entirely in choosing those positions. Three primitives do all the work:
 *
 *     halves   in-between splits the remaining distance 50/50   — neutral
 *     thirds   splits it 1/3 : 2/3                              — snappy
 *     favour   sits 10-20% from one end, hugging it             — cushioned
 *
 * `chart()` below reproduces the standard ladders those primitives build.
 *
 * ── The part that actually fixes renders ───────────────────────────────────
 *
 * Gravity is ASYMMETRIC and almost every naive rig gets it wrong. A body
 * falling is accelerated by gravity; a body rising is decelerated by it. So a
 * bounce is NOT a sine wave — the down half must be fast-in and the up half
 * slow-out. A symmetric |sin| bob is the single most common reason a walk
 * reads as floating rather than weighing something.
 *
 * `bobShape()` is the corrected curve, and `odd()` is where its exponent comes
 * from: Galileo's odd rule, that a falling body covers distance in the ratio
 * 1 : 3 : 5 : 7 across equal time slices — which integrates to t².
 */

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

/* ── timing charts ────────────────────────────────────────────────────────
 *
 * Each chart is the ladder an animator would draw: `t` is the in-between's
 * position in TIME (uniform, because drawings are exposed evenly), `x` is its
 * position in SPACE along the move. Bunched x-values against evenly spaced
 * t-values is exactly what a cushion is.
 *
 * These are transcribed from a 13-frame, 7-drawing exposure on twos, which is
 * the worked example the discipline is usually taught with.
 */
export const CHARTS = {
  /** Even halves both ends. The default; reads neutral and mechanical. */
  even: {
    t: [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1],
    x: [0, 0.125, 0.25, 0.5, 0.75, 0.875, 1],
  },
  /** Starts slow, ends fast. Midpoint deferred to the penultimate drawing. */
  accel: {
    t: [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1],
    x: [0, 0.016, 0.047, 0.109, 0.234, 0.5, 1],
  },
  /** Starts fast, ends slow. Midpoint reached on the second drawing. */
  decel: {
    t: [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1],
    x: [0, 0.5, 0.766, 0.891, 0.953, 0.984, 1],
  },
  /**
   * Thirds into the middle, favour onto the end. Hangs, bursts, then cushions
   * hard into the stop — the shape of a held wind-up releasing into an impact.
   */
  cushion: {
    t: [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1],
    x: [0, 0.056, 0.222, 0.667, 0.833, 0.958, 1],
  },
};

/**
 * Monotone cubic interpolation (Fritsch–Carlson).
 *
 * Plain Catmull-Rom through these points overshoots — it would send a cushion
 * curve past its own key and back, which on screen is an overshoot nobody
 * asked for. Fritsch–Carlson clamps the tangents so the result can never
 * exceed the data, which is the correct guarantee for a chart: the animator
 * drew every position they wanted.
 */
const monotone = (ts, xs, u) => {
  const n = ts.length;
  if (u <= ts[0]) return xs[0];
  if (u >= ts[n - 1]) return xs[n - 1];

  const d = [];
  for (let i = 0; i < n - 1; i++) d.push((xs[i + 1] - xs[i]) / (ts[i + 1] - ts[i]));

  const m = [d[0]];
  for (let i = 1; i < n - 1; i++) {
    m.push(d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2);
  }
  m.push(d[n - 2]);

  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / d[i];
    const b = m[i + 1] / d[i];
    const s = a * a + b * b;
    if (s > 9) {
      const k = 3 / Math.sqrt(s);
      m[i] = k * a * d[i];
      m[i + 1] = k * b * d[i];
    }
  }

  let i = 0;
  while (i < n - 2 && u > ts[i + 1]) i++;
  const h = ts[i + 1] - ts[i];
  const s = (u - ts[i]) / h;
  const s2 = s * s;
  const s3 = s2 * s;
  return (
    (2 * s3 - 3 * s2 + 1) * xs[i] +
    (s3 - 2 * s2 + s) * h * m[i] +
    (-2 * s3 + 3 * s2) * xs[i + 1] +
    (s3 - s2) * h * m[i + 1]
  );
};

/** Evaluate a named timing chart at normalised time `t`. */
export const chart = (name, t) => {
  const c = CHARTS[name] || CHARTS.even;
  return monotone(c.t, c.x, clamp(t, 0, 1));
};

/* ── gravity ──────────────────────────────────────────────────────────────
 *
 * The odd rule: across equal slices of time a falling body covers distance in
 * the ratio 1 : 3 : 5 : 7 : 9. Summing consecutive odd numbers gives the
 * squares, so cumulative fall is exactly t² — which is why every falling arc
 * in this codebase is quadratic and never linear or sinusoidal.
 */

/** Cumulative fall after fraction `t` of a drop. Accelerating. */
export const fall = (t) => {
  const u = clamp(t, 0, 1);
  return u * u;
};

/** Cumulative rise after fraction `t` of a launch. Decelerating. */
export const rise = (t) => {
  const u = clamp(t, 0, 1);
  return 1 - (1 - u) * (1 - u);
};

/**
 * The per-frame spacing the odd rule predicts, for `n` slices.
 *
 * Exposed mostly so the physics checker can assert against it rather than
 * against a magic number: slice k of n should be (2k+1)/n² of the total.
 */
export const odd = (k, n) => (2 * k + 1) / (n * n);

/**
 * Vertical shape of a body bouncing on its own legs, 0 at the bottom of the
 * step and 1 at the top.
 *
 * Two bounces per stride — one per footfall. Within each, the body RISES off
 * the planted leg decelerating (it is lifting its own mass against gravity)
 * and FALLS onto the next one accelerating (gravity is doing the work). That
 * asymmetry is the whole point; replacing this with |sin| restores the floaty
 * look it exists to remove.
 */
export const bobShape = (phase) => {
  const u = (phase % 0.5) / 0.5;
  return u < 0.5 ? rise(u / 0.5) : 1 - fall((u - 0.5) / 0.5);
};

/* ── exposure ─────────────────────────────────────────────────────────────
 *
 * Hand animation is rarely exposed on every frame. Held two frames at a time
 * ("on twos") it reads as deliberate and drawn; on ones it reads smooth and,
 * in a vector rig, often plasticky — because a solver's output is *too*
 * continuous, with none of the quantisation the eye reads as draughtsmanship.
 *
 * Fast action still wants ones: a hold of two on a limb crossing the frame in
 * five frames is a visible stutter rather than a style.
 */
export const onTwos = (frame, step = 2) => Math.floor(frame / step) * step;

/**
 * Choose an exposure from how fast the thing is actually moving.
 *
 * Screen units per frame. The thresholds are deliberately generous: the cost
 * of holding a fast move is a stutter the audience notices, and the cost of
 * running a slow move on ones is only that it looks slightly cleaner.
 */
export const exposureFor = (speed) => (speed > 26 ? 1 : 2);

/**
 * Squash/stretch factor as a body takes and releases weight.
 *
 * Returns a vertical scale: <1 compressed, >1 extended, volume preserved by
 * the caller via sx = 1/sy. Peak compression sits just after contact (the
 * "down" extreme) and peak extension just before the next one (push-off).
 */
export const springScale = (phase, amount = 0.05) => {
  const u = (phase % 0.5) / 0.5;
  return 1 + amount * Math.sin(u * Math.PI * 2);
};

export const easing = {chart, fall, rise, bobShape, onTwos, springScale};
