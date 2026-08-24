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

// Matches Crosstown.jsx, which drives the Humaaans rig. A second rig means a
// second set of stride units, and a path that is safe at one figure's cadence
// is not automatically safe at another's -- so it gets checked too.
const H_SCALE = 0.95;
const H_WALK_U = 268 * H_SCALE;    // humaaansStride(H_SCALE,'walk')
const H_RUN_U = 585 * H_SCALE;
const HWALK = H_WALK_U * 1.0;
const HRUN = H_RUN_U * 1.15;

const H_OPTS = {
  fps: FPS,
  walkStride: H_WALK_U,
  runStride: H_RUN_U,
  idleBelow: 0.35,
  runAbove: (HRUN * 0.5) / FPS,
  turnFrames: 7,
};

const humaaansPaths = () => {
  const maya = [{t: 0, x: -420, ease: 'creep'}];
  seg(maya, 4.2, HWALK, 'easeOut');
  seg(maya, 1.4, 0, 'linear');
  seg(maya, 1.6, HWALK * 0.85, 'easeInOut');
  seg(maya, 5.6, HRUN, 'easeIn');
  seg(maya, 2.2, HWALK * 0.9, 'easeOut');

  const omar = [{t: 0, x: 2150, ease: 'creep'}];
  seg(omar, 1.2, 0, 'linear');
  seg(omar, 8.0, -HWALK * 0.9, 'easeInOut');
  seg(omar, 1.5, 0, 'linear');
  seg(omar, 6.0, -HWALK * 0.75, 'easeIn');

  const sam = [{t: 0, x: 1250}];
  seg(sam, 4.0, HWALK * 0.5, 'easeInOut');
  seg(sam, 1.6, 0, 'linear');
  seg(sam, 4.0, -HWALK * 0.5, 'easeInOut');
  seg(sam, 7.0, HWALK * 0.45, 'easeInOut');

  const nia = [{t: 0, x: 4750}];
  seg(nia, 9.0, 0, 'linear');
  seg(nia, 6.0, HWALK * 0.45, 'easeInOut');

  return {maya, omar, sam, nia};
};

/**
 * Matches DoublingBack.jsx. The most demanding path in the repository: a full
 * stop, a held beat, a reversal and a run, back to back. Every one of those
 * joins is somewhere the solver could produce a slide, so it is worth more
 * checking than a path where somebody strolls in a straight line.
 */
const DB_WALK = H_WALK_U;
const DB_RUN = H_RUN_U * 1.12;
const DB_OPTS = {...H_OPTS, runAbove: (DB_RUN * 0.5) / FPS, turnFrames: 8};

const doublingPaths = () => {
  const BEAT_IN = 5.9;
  const BEAT_OUT = 7.5;

  const ada = [{t: 0, x: -300, ease: 'creep'}];
  seg(ada, 4.4, DB_WALK, 'easeOut');
  seg(ada, 1.5, 0, 'easeOut');
  seg(ada, 1.6, 0, 'linear');
  seg(ada, 1.1, -DB_WALK * 0.55, 'easeIn');
  seg(ada, 4.6, -DB_RUN, 'easeIn');
  seg(ada, 1.8, -DB_WALK * 0.9, 'easeOut');

  const ivo = [{t: 0, x: 1980, ease: 'creep'}];
  seg(ivo, BEAT_IN, -DB_WALK * 0.42, 'easeInOut');
  seg(ivo, BEAT_OUT - BEAT_IN, 0, 'easeOut');
  seg(ivo, 15 - BEAT_OUT, -DB_WALK * 0.5, 'easeIn');

  const tess = [{t: 0, x: -1150}];
  seg(tess, 4.0, DB_WALK * 0.3, 'easeInOut');
  seg(tess, 3.5, 0, 'easeOut');
  seg(tess, 7.5, DB_WALK * 0.22, 'easeInOut');

  return {ada, ivo, tess};
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
const H = humaaansPaths();
const D = doublingPaths();

const CASES = [
  {name: 'SecondThoughts / ada', keys: P.ada, opts: OPTS},
  {name: 'SecondThoughts / ben', keys: P.ben, opts: {...OPTS, initialFacing: -1}},
  {name: 'SecondThoughts / cal', keys: P.cal, opts: OPTS},

  {name: 'Crosstown / maya', keys: H.maya, opts: H_OPTS},
  {name: 'Crosstown / omar', keys: H.omar, opts: {...H_OPTS, initialFacing: -1}},
  {name: 'Crosstown / sam', keys: H.sam, opts: H_OPTS},
  {name: 'Crosstown / nia', keys: H.nia, opts: H_OPTS},

  {name: 'DoublingBack / ada', keys: D.ada, opts: DB_OPTS},
  {name: 'DoublingBack / ivo', keys: D.ivo, opts: {...DB_OPTS, initialFacing: -1}},
  {name: 'DoublingBack / tess', keys: D.tess, opts: DB_OPTS},

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

/* ── craft checks ─────────────────────────────────────────────────────────
 *
 * The locomotion tests above ask "is the motion honest". These ask "is it
 * DRAWN the way traditional practice draws it" -- the rules taken from the
 * animation course. They are cheap, they are pure maths, and every one of
 * them guards a bug that has actually shipped.
 */
const {bobShape, fall, rise, chart, odd} = await import(
  join(ROOT, 'remotion/src/lib/timing.js')
);
const {lag, whipAmplitude, settle} = await import(
  join(ROOT, 'remotion/src/lib/overlap.js')
);

const craft = [];
const craftCheck = (name, fn) => {
  let ok = false;
  let why = '';
  try {
    const r = fn();
    ok = r === true;
    if (!ok) why = ` -- ${r}`;
  } catch (e) {
    why = ` -- threw ${e.message}`;
  }
  craft.push({name, ok, why});
};

craftCheck('gravity is asymmetric (fall accelerates, rise decelerates)', () => {
  // First tenth of a fall must cover less ground than the last tenth; a
  // symmetric curve covers the same. This is the check that would have caught
  // the |sin| bob.
  const firstFall = fall(0.1) - fall(0);
  const lastFall = fall(1) - fall(0.9);
  if (!(lastFall > firstFall * 5)) return `fall not accelerating (${firstFall} vs ${lastFall})`;
  const firstRise = rise(0.1) - rise(0);
  const lastRise = rise(1) - rise(0.9);
  if (!(firstRise > lastRise * 5)) return `rise not decelerating (${firstRise} vs ${lastRise})`;
  return true;
});

craftCheck("bob obeys Galileo's odd rule (spacing 1:3:5:7)", () => {
  // Distance covered in successive equal slices of a fall should go 1,3,5,7.
  for (let k = 0; k < 4; k++) {
    const got = fall((k + 1) / 4) - fall(k / 4);
    const want = odd(k, 4);
    if (Math.abs(got - want) > 1e-9) return `slice ${k}: ${got} != ${want}`;
  }
  return true;
});

craftCheck('bob peaks at the passing pose, lands at contact', () => {
  // Two bounces per stride. Lowest at contact (0, 0.5), highest at passing.
  if (bobShape(0) > 1e-9) return `phase 0 should be at the bottom, got ${bobShape(0)}`;
  if (bobShape(0.5) > 1e-9) return `phase 0.5 should be at the bottom`;
  if (bobShape(0.25) < 0.999) return `phase 0.25 should be at the top, got ${bobShape(0.25)}`;
  return true;
});

craftCheck('timing charts are monotone and span 0..1', () => {
  for (const name of ['even', 'accel', 'decel', 'cushion']) {
    if (Math.abs(chart(name, 0)) > 1e-6) return `${name} does not start at 0`;
    if (Math.abs(chart(name, 1) - 1) > 1e-6) return `${name} does not end at 1`;
    let prev = -Infinity;
    for (let i = 0; i <= 100; i++) {
      const v = chart(name, i / 100);
      // A chart that backtracks is an overshoot the animator did not draw.
      if (v < prev - 1e-9) return `${name} backtracks at t=${i / 100}`;
      if (v < -1e-6 || v > 1 + 1e-6) return `${name} leaves 0..1 at t=${i / 100}`;
      prev = v;
    }
  }
  return true;
});

craftCheck('accel and decel are genuinely opposite', () => {
  // accel must sit below the diagonal, decel above it, everywhere in between.
  for (let i = 1; i < 100; i++) {
    const t = i / 100;
    if (chart('accel', t) >= t) return `accel not slow-in at t=${t}`;
    if (chart('decel', t) <= t) return `decel not fast-out at t=${t}`;
  }
  return true;
});

craftCheck('chain lag wraps into phase and accumulates down the chain', () => {
  const cyc = 20;
  const p = lag(0.1, 4, cyc);
  if (p < 0 || p >= 1) return `lag left the unit interval: ${p}`;
  if (Math.abs(p - 0.9) > 1e-9) return `expected 0.9, got ${p}`;
  // link 3 must trail link 1 by more than link 2 does
  const l1 = lag(0.5, 2, cyc);
  const l2 = lag(0.5, 4, cyc);
  if (!(0.5 - l1 < 0.5 - l2)) return 'delay does not accumulate';
  // a standing character has no cycle, so nothing may lag
  if (lag(0.3, 4, 0) !== 0.3) return 'lag applied with no cycle';
  return true;
});

craftCheck('whip amplitude is zero at the anchor and grows to the tip', () => {
  if (whipAmplitude(0) !== 0) return 'anchor moves';
  if (whipAmplitude(1) !== 1) return 'tip is not full amplitude';
  // Growth must accelerate toward the tip, not be linear.
  if (!(whipAmplitude(0.5) < 0.5 - 0.05)) return 'amplitude is linear, not whip-like';
  return true;
});

craftCheck('follow-through overshoots then rings down', () => {
  if (Math.abs(settle(0) - 1) > 1e-9) return 'does not start at full drag';
  let crossed = false;
  let overshoot = 0;
  for (let t = 0; t < 40; t += 0.25) {
    const v = settle(t);
    if (v < -0.01) {
      crossed = true;
      overshoot = Math.min(overshoot, v);
    }
  }
  if (!crossed) return 'never overshoots past rest';
  if (Math.abs(settle(60)) > 0.02) return 'never settles';
  return true;
});

for (const c of craft) {
  if (c.ok) lines.push(`ok    ${c.name}`);
  else {
    failed++;
    lines.push(`FAIL  ${c.name}${c.why}`);
  }
}

const total = CASES.length + 3 + craft.length;

console.log(lines.join('\n'));
console.log(
  failed === 0
    ? `\nphysics: ${total} checks clean`
    : `\nphysics: ${failed} of ${total} checks FAILED`
);
process.exit(failed === 0 ? 0 : 1);
