#!/usr/bin/env node
/**
 * Grades every motion path in the project against the physics validator, and
 * exits non-zero if any of them lies.
 *
 * This exists because the failures it catches are invisible in review and
 * nearly invisible in playback. A character who moonwalks out of frame looks,
 * on a timeline, exactly like a character who walks out of frame; you only
 * notice at full speed, on the second or third viewing, and by then the shot
 * has been signed off. The previous film shipped with precisely that bug.
 *
 * Run it in CI. It is fast — it solves paths, it does not render anything.
 *
 *   node scripts/check-physics.mjs
 *   node scripts/check-physics.mjs --verbose
 */

import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

const {solveLocomotion, validateLocomotion} = await import(
  join(ROOT, 'remotion/src/lib/locomotion.js')
);

const verbose = process.argv.includes('--verbose');

/* ── the cases ────────────────────────────────────────────────────────────
 *
 * Two kinds live here, deliberately.
 *
 * The first are the paths the films actually use, so a change to the staging
 * is checked. The second are adversarial: each one reproduces a fault that
 * has genuinely shipped from this crew, and asserts the solver now refuses to
 * produce it. Without those, the suite passes trivially the moment someone
 * writes only gentle paths, and stops being evidence of anything.
 */

const FPS = 30;
const S = (sec) => Math.round(sec * FPS);
const seg = (keys, dur, speed, ease) => {
  const last = keys[keys.length - 1];
  keys.push({t: last.t + S(dur), x: last.x + speed * dur, ease});
  return keys;
};

// Matches SecondThoughts.jsx. Kept as literals rather than imported, because
// importing JSX here would mean carrying a transform into CI for no benefit.
const SCALE = 0.34;
const WALK = 203 * SCALE * 1.0;   // strideUnits(SCALE,'walk') ≈ 586*SCALE
const RUN = 1272 * SCALE * 1.5;

const OPTS = {
  fps: FPS,
  walkStride: 586 * SCALE,
  runStride: 1272 * SCALE,
  idleBelow: 0.35,
  runAbove: (RUN * 0.5) / FPS,
  turnFrames: 7,
};

const filmPaths = () => {
  const ada = [{t: 0, x: -600, ease: 'creep'}];
  seg(ada, 6.0, 586 * SCALE, 'easeOut');
  seg(ada, 2.5, 0, 'linear');
  seg(ada, 3.5, -586 * SCALE * 0.92, 'easeInOut');
  seg(ada, 2.0, 0, 'linear');
  seg(ada, 6.0, RUN * 0.62, 'easeIn');
  seg(ada, 10.0, RUN, 'creep');

  const ben = [{t: 0, x: 3400, ease: 'creep'}];
  seg(ben, 2.0, 0, 'linear');
  seg(ben, 11.0, -586 * SCALE * 0.88, 'easeInOut');
  seg(ben, 3.0, 0, 'linear');
  seg(ben, 14.0, -586 * SCALE * 0.8, 'easeIn');

  const cal = [{t: 0, x: 2100}];
  seg(cal, 5.0, 586 * SCALE * 0.55, 'easeInOut');
  seg(cal, 2.0, 0, 'linear');
  seg(cal, 5.0, -586 * SCALE * 0.55, 'easeInOut');
  seg(cal, 2.0, 0, 'linear');
  seg(cal, 6.0, 586 * SCALE * 0.6, 'easeInOut');
  seg(cal, 10.0, 0, 'linear');

  return {ada, ben, cal};
};

const P = filmPaths();

const CASES = [
  {name: 'SecondThoughts / ada', keys: P.ada, opts: OPTS},
  {name: 'SecondThoughts / ben', keys: P.ben, opts: {...OPTS, initialFacing: -1}},
  {name: 'SecondThoughts / cal', keys: P.cal, opts: OPTS},

  // The wetpaint bug, reduced to its essence: enter from the left, leave to
  // the right. Facing must stay +1 throughout. The old code flipped on exit.
  {
    name: 'adversarial / cross the frame without turning',
    keys: [{t: 0, x: -400}, {t: S(8), x: 1900, ease: 'linear'}],
    opts: OPTS,
  },
  // A genuine reversal. Facing must change exactly once, and the phase must
  // not run backwards through the pivot.
  {
    name: 'adversarial / full reversal mid-shot',
    keys: [
      {t: 0, x: 0},
      {t: S(5), x: 1200, ease: 'easeOut'},
      {t: S(7), x: 1200},
      {t: S(12), x: -200, ease: 'easeInOut'},
    ],
    opts: OPTS,
  },
  // Long dwells: the classic treadmill, where legs cycle on a parked body.
  {
    name: 'adversarial / stand still for six seconds',
    keys: [{t: 0, x: 500}, {t: S(6), x: 500}, {t: S(9), x: 900, ease: 'easeInOut'}],
    opts: OPTS,
  },
  // Hard acceleration into a sprint: the stride must grow, not the cadence
  // run away.
  {
    name: 'adversarial / walk breaking into a run',
    keys: [
      {t: 0, x: 0, ease: 'creep'},
      {t: S(4), x: 4 * 586 * SCALE, ease: 'linear'},
      {t: S(10), x: 4 * 586 * SCALE + 6 * RUN, ease: 'easeIn'},
    ],
    opts: OPTS,
  },
];

/* ── run ─────────────────────────────────────────────────────────────────── */

let failed = 0;
const lines = [];

for (const c of CASES) {
  let track;
  try {
    track = solveLocomotion(c.keys, c.opts);
  } catch (err) {
    failed++;
    lines.push(`FAIL  ${c.name}\n      solver threw: ${err.message}`);
    continue;
  }

  const res = validateLocomotion(track, {
    idleBelow: c.opts.idleBelow,
    maxSlide: 2.5,
    maxStep: 60,
  });

  if (res.ok) {
    lines.push(`ok    ${c.name}  (${track.frames.length} frames)`);
    if (verbose) {
      const moving = track.frames.filter((f) => f.moving).length;
      const turns = track.frames.filter((f) => f.turning > 0.01).length;
      lines.push(`      moving ${moving}, turning ${turns}, ` +
        `x ${track.frames[0].x.toFixed(0)} → ${track.frames.at(-1).x.toFixed(0)}`);
    }
  } else {
    failed++;
    lines.push(`FAIL  ${c.name}`);
    const shown = res.summary ?? res.errors;
    for (const e of shown.slice(0, 8)) lines.push(`      ${e}`);
    if (shown.length > 8) lines.push(`      … and ${shown.length - 8} more`);
  }
}

/* ── negative controls ────────────────────────────────────────────────────
 *
 * A suite that cannot fail is not evidence. The solver is built so that it
 * cannot produce a moonwalk, which means none of the cases above can ever go
 * red for that reason — and a validator quietly returning `ok` for everything
 * would look identical to a validator that works.
 *
 * So these hand-build broken tracks and assert the validator CATCHES them.
 * Each reproduces a fault that has genuinely shipped from this crew.
 */
const brokenTracks = () => {
  const base = solveLocomotion(
    [{t: 0, x: 0}, {t: S(6), x: 6 * 586 * SCALE, ease: 'linear'}],
    OPTS
  );
  const clone = () => ({
    ...base,
    frames: base.frames.map((f) => ({...f})),
  });

  // The wetpaint bug, literally: facing authored from the story rather than
  // measured from the motion, and flipped on the way out.
  const moonwalk = clone();
  for (const f of moonwalk.frames) {
    if (f.t > 3) {
      f.facing = -1;
      f.facingScale = -1;
    }
  }

  // Legs driven by a clock instead of by distance: the body parks, the feet
  // keep going.
  const treadmill = clone();
  treadmill.frames.forEach((f, i) => {
    if (f.t > 3) {
      f.x = treadmill.frames[90].x;
      f.vx = 0;
      f.speed = 0;
      f.phase = (i / 24) % 1;
    }
  });

  // A cut that was never meant to be a move.
  const teleport = clone();
  for (let i = 100; i < teleport.frames.length; i++) teleport.frames[i].x += 900;

  return [
    {name: 'moonwalk (facing authored, not derived)', track: moonwalk, expect: 'MOONWALK'},
    {name: 'treadmill (phase from a clock)', track: treadmill, expect: 'TREADMILL'},
    {name: 'teleport (unintended jump cut)', track: teleport, expect: 'TELEPORT'},
  ];
};

for (const c of brokenTracks()) {
  const res = validateLocomotion(c.track, {idleBelow: OPTS.idleBelow, maxSlide: 2.5, maxStep: 60});
  const caught = !res.ok && res.errors.some((e) => e.includes(c.expect));
  if (caught) {
    lines.push(`ok    detects ${c.name}`);
  } else {
    failed++;
    lines.push(`FAIL  validator did NOT detect ${c.name} — expected ${c.expect}`);
  }
}

const total = CASES.length + 3;

console.log(lines.join('\n'));
console.log(
  failed === 0
    ? `\nphysics: ${total} checks clean`
    : `\nphysics: ${failed} of ${total} checks FAILED`
);
process.exit(failed === 0 ? 0 : 1);
