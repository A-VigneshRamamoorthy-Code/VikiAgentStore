/**
 * Butterflies.
 *
 * A butterfly is the cleanest possible demonstration of asymmetric gravity,
 * which is why it is worth drawing properly rather than sliding a sprite along
 * a sine wave.
 *
 * It does not fly. It falls, catches itself, and falls again. Each downstroke
 * is a single impulse of lift, so the creature RISES fast and decelerating,
 * hangs at the top with almost no vertical speed, then DROPS slowly at first
 * and then faster. That is `rise` on the way up and `fall` on the way down --
 * the same asymmetry the course spends a whole video on, at a scale where an
 * audience can actually see it.
 *
 * Get that one thing right and the insect reads as alive even at four pixels
 * of wingspan. Use a symmetric sine and it reads as a bouncing ball with
 * decoration, no matter how good the wing art is.
 *
 * Everything here is a pure function of time. Nothing integrates, so any frame
 * can be drawn without having drawn the one before it.
 */

import React from 'react';
import {fall, rise} from '../lib/timing.js';

const TAU = Math.PI * 2;

/** Deterministic per-butterfly variation. Two butterflies on one path that
 *  share a phase are one butterfly drawn twice. */
const vary = (seed) => {
  let h = Math.sin(seed * 127.1) * 43758.5453;
  return () => {
    h = Math.sin(h * 91.7 + 7.3) * 43758.5453;
    return h - Math.floor(h);
  };
};

export const butterflySpec = (seed = 1, over = {}) => {
  const r = vary(seed);
  return {
    seed,
    flapHz: 5.2 + r() * 2.4,          // wingbeats per second
    hop: 26 + r() * 16,               // height gained per beat
    hang: 0.34 + r() * 0.12,          // fraction of the beat spent at the top
    wobble: 16 + r() * 14,            // lateral drift amplitude
    wobbleHz: 0.55 + r() * 0.4,
    phase: r(),
    ...over,
  };
};

/**
 * Where a butterfly is at time `t`, relative to its path point.
 *
 * `beat` runs 0..1 once per wingbeat. The first `1 - hang` of it is the climb,
 * eased with `rise` so it decelerates into the top; the rest is the drop,
 * eased with `fall` so it accelerates out of it. The wings are fully spread at
 * the bottom of the climb and folded at the top, a quarter-beat ahead of the
 * body -- the stroke causes the lift, so it cannot be in phase with it.
 */
export const butterflyAt = (t, spec) => {
  const beat = (t * spec.flapHz + spec.phase) % 1;
  const climb = 1 - spec.hang;

  const lift = beat < climb
    ? rise(beat / climb)
    : 1 - fall((beat - climb) / spec.hang);

  const drift = Math.sin((t * spec.wobbleHz + spec.phase) * TAU) * spec.wobble;
  const drift2 = Math.sin((t * spec.wobbleHz * 1.7 + spec.phase * 3) * TAU) * spec.wobble * 0.4;

  // The wing angle leads the lift. Folded (0) at the top, spread (1) at the
  // bottom, because the power stroke is downward.
  const stroke = beat < climb ? 1 - rise(beat / climb) * 0.92 : 0.08 + fall((beat - climb) / spec.hang) * 0.92;

  return {
    dx: drift + drift2,
    dy: -lift * spec.hop,
    stroke,
    // Rolling into the drift is what stops it looking like it is on rails.
    roll: -Math.cos((t * spec.wobbleHz + spec.phase) * TAU) * 13,
  };
};

/** One wing, hinged at the body. Folding is a horizontal squash of the whole
 *  wing, which is what a wing seen from the side actually does. */
const Wing = ({spread, fill, dark, flip}) => (
  <g transform={`scale(${flip} 1) scale(${(0.16 + spread * 0.84).toFixed(3)} 1)`}>
    <path d="M0 -2 C 2 -20, 20 -30, 26 -19 C 31 -10, 20 -3, 6 -1 Z" fill={fill} />
    <path d="M0 1 C 3 8, 17 12, 20 6 C 23 0, 12 -1, 4 0 Z" fill={dark} />
  </g>
);

/**
 * @param {number} t      seconds
 * @param {[number,number]} at  the path point this butterfly is fluttering around
 */
export const Butterfly = ({t, at, spec, look = {}, scale = 1}) => {
  const f = butterflyAt(t, spec);
  const fill = look.wing ?? '#f2b134';
  const dark = look.wingDark ?? '#e07a3f';
  const body = look.body ?? '#2b2b40';

  // The far wing is the same shape a shade darker, and slightly behind in the
  // stroke. Both wings at identical brightness collapse into one silhouette.
  const farStroke = Math.max(0.06, f.stroke * 0.86);

  return (
    <g transform={`translate(${(at[0] + f.dx).toFixed(2)} ${(at[1] + f.dy).toFixed(2)}) scale(${scale}) rotate(${f.roll.toFixed(2)})`}>
      <g opacity="0.72">
        <Wing spread={farStroke} fill={fill} dark={dark} flip={-1} />
      </g>
      <path d="M0 -6 C 2 -6, 2 6, 0 8 C -2 6, -2 -6, 0 -6 Z" fill={body} />
      <path d="M-1 -6 C -3 -12, -5 -13, -6 -12" stroke={body} strokeWidth="1" fill="none" strokeLinecap="round" />
      <path d="M1 -6 C 3 -12, 5 -13, 6 -12" stroke={body} strokeWidth="1" fill="none" strokeLinecap="round" />
      <Wing spread={f.stroke} fill={fill} dark={dark} flip={1} />
    </g>
  );
};

/**
 * A path a butterfly wanders along, as a function of time.
 *
 * Butterflies do not commute. The mean path is a slow loop rather than a line,
 * so a dog chasing one has something to overshoot -- which is the whole reason
 * the chase is funny.
 */
export const wanderPath = ({cx, cy, rx, ry, hz = 0.16, phase = 0, tilt = 0}) => (t) => {
  const a = (t * hz + phase) * TAU;
  const x = Math.cos(a) * rx;
  const y = Math.sin(a * 2) * ry * 0.5 + Math.sin(a) * ry * 0.5;
  const c = Math.cos(tilt);
  const s = Math.sin(tilt);
  return [cx + x * c - y * s, cy + x * s + y * c];
};

/** A group of butterflies sharing a path, each with its own beat. */
export const Butterflies = ({t, path, count = 3, seed = 1, look, scale = 1, spread = 60}) => {
  const specs = React.useMemo(
    () => Array.from({length: count}, (_, i) => butterflySpec(seed + i * 17.3)),
    [count, seed],
  );
  return (
    <g>
      {specs.map((s, i) => {
        const lead = i * 0.28;
        const p = path(t - lead);
        const off = ((i % 2) * 2 - 1) * spread * (0.4 + (i / count) * 0.6);
        return <Butterfly key={i} t={t} at={[p[0] + off, p[1] - i * 18]} spec={s} look={look} scale={scale} />;
      })}
    </g>
  );
};
