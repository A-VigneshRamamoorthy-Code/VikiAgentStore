/**
 * Timing, easing and camera -- the parts of the style that are arithmetic
 * rather than drawing.
 *
 * Every function here is a port of a named function in the Python engine, and
 * the point of keeping them together is that this file is the whole of the
 * behavioural contract. If a frame from this renderer disagrees with a frame
 * from that one, the disagreement is either here or in a drawing, and this is
 * the cheaper half to check.
 */

// ------------------------------------------------------------------ board ---

/**
 * The board's long edge is always 100 units, whatever the aspect.
 *
 * A 16:9 board is therefore 100 x 56.25 and a 9:16 board is 56.25 x 100. This
 * is the one geometric fact that has to be right before anything else can be:
 * get it backwards and a vertical cut silently reframes every shot in the film.
 */
export const SCENE_LONG = 100.0;

export const boardSize = (width, height) => {
  const long = SCENE_LONG;
  const short = (long * Math.min(width, height)) / Math.max(width, height);
  return width >= height ? {w: long, h: short} : {w: short, h: long};
};

// ----------------------------------------------------------------- easing ---

const _overshoot = (t, overshoot = 0.12, decay = 3.5) => {
  if (t < 0.6) return Math.sqrt(Math.max(0, t) / 0.6) * (1 + overshoot);
  const s = (t - 0.6) / 0.4;
  return 1 + overshoot * Math.cos(s * Math.PI) * Math.exp(-decay * s);
};

const _out = (t) => {
  const u = 1 - t;
  return 1 - u * u * u;
};

const _in = (t) => t * t * t;

const _inout = (t) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

const _anticipate = (t) => {
  const depth = 0.18, wind = 0.16, hold = 0.14;
  if (t < wind) {
    const u = t / wind;
    return -depth * u * u * (3 - 2 * u);
  }
  if (t < wind + hold) return -depth;
  const s = (t - wind - hold) / (1 - wind - hold);
  return _overshoot(s) * (1 + depth) - depth;
};

const _linear = (t) => t;
const _hold = (t) => (t >= 1 ? 1 : 0);

const EASES = {
  overshoot: _overshoot,
  out: _out,
  in: _in,
  inout: _inout,
  anticipate: _anticipate,
  linear: _linear,
  hold: _hold,
  // A camera curve, not one of anim.py's ten: constant rate, no departure
  // spike and no asymptotic tail. It is the identity, and it is only legal
  // because a creep is meant to be imperceptible -- the thing that makes
  // `linear` indefensible on a character is exactly what makes it right here.
  creep: _linear,
};

/**
 * Shape `t` in 0..1. Unknown names fall back to `overshoot`, deliberately:
 * a typo in a storyboard should cost a nicety, not the render.
 *
 * The result is **not** clamped between 0 and 1. `anticipate` returns negative
 * values early and `overshoot` exceeds 1 in the middle; that is the entire
 * point of them.
 */
export const ease = (name, t) => {
  const u = t < 0 ? 0 : t > 1 ? 1 : t;
  if (u <= 0) return 0;
  if (u >= 1) return 1;
  const fn = EASES[String(name ?? 'overshoot').trim().toLowerCase().replace(/_/g, '-')] ?? _overshoot;
  return fn(u);
};

// --------------------------------------------------------------- stepping ---
//
// Stepping -- holding a drawing for two or three frames while the camera keeps
// moving every frame -- is the single most characteristic thing this style
// does, and it is not implemented here either.
//
// The engine's `on` can change *inside* a shot, and its quantised pose clock
// is resolved alongside the smear window that lets a fast drawing escape the
// hold. Both come out of `generated/camera.json` per frame, so there is one
// source of truth for when a drawing changes rather than two that can drift.
//
// The rule it encodes is still worth stating: quantise poses, never the
// camera. A stepped camera reads as dropped frames, not as animation.

// ----------------------------------------------------------------- camera ---
//
// There is deliberately no camera solver here.
//
// An earlier version of this file resolved a board camera itself -- lerping
// `from` to `to`, easing it, and laying two sine terms over `handheld`. It
// looked right and measured wrong: every `push`/`none` shot matched the
// Python render to under MAE 5 while every `track`/`whip`/`handheld` shot sat
// at 12-19, because the engine's solver also carves a `hold`/`pre_hold`
// settle out of the span before easing, silently refuses mechanical eases,
// drives handheld from a seeded table, and resolves `follow` against an
// actor's actual position.
//
// The camera now comes from `generated/camera.json`, one entry per frame, via
// `tools/trace-camera.py`. See remotion/README.md.

/**
 * A camera view as a CSS transform on a board-sized stage.
 *
 * Written as a single string so the browser composites it on the GPU as one
 * matrix rather than laying anything out again -- this is the reason a camera
 * move costs nothing here and costs a full re-render per frame in the Python
 * engine.
 */
export const viewTransform = (view, board, pxPerUnit) => {
  const {cx, cy, zoom} = view;
  const halfW = (board.w / 2) * pxPerUnit;
  const halfH = (board.h / 2) * pxPerUnit;
  const dx = halfW - cx * pxPerUnit * zoom;
  const dy = halfH - cy * pxPerUnit * zoom;
  return `translate(${dx}px, ${dy}px) scale(${zoom})`;
};
