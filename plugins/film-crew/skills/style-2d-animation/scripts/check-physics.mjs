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

const {solveLocomotion, validateLocomotion, gaitAt} = await import(
  join(ROOT, 'remotion/src/lib/locomotion.js')
);

// The picnic's paths come from the film itself, not from a copy of it.
const {
  picnicPaths,
  ADULT: PIC_ADULT,
  CHILD: PIC_CHILD,
  DOG_S: PIC_DOG,
} = await import(join(ROOT, 'remotion/src/films/picnic.paths.js'));

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

/**
 * The Humaaans stride, derived here from the artwork rather than imported.
 *
 * This is a deliberate duplicate. Every other shared number in this file was
 * moved into `films/picnic.paths.js` after a hand-copied mirror silently drifted
 * from the film and let a broken shot render clean four times running -- but a
 * stride that is IMPORTED cannot catch a mistake in how the stride is computed,
 * only a mistake in using it. So the physics is restated from first principles
 * and the two are required to agree.
 *
 * A leg is rigid, so the only way to put the feet further apart is to lower the
 * hips. The hip sits 199 above the ankle -- the drawn hip-to-ankle of the
 * `bottom/` artwork, NOT a chosen number -- and dips by `sink` at mid-stance,
 * so each foot reaches sqrt(leg^2 - (199 - sink)^2) either side of the hip.
 * That excursion happens over the fraction of the cycle the foot is down.
 *
 * If this stops matching `H_STRIDE_UNITS`, one of the two is wrong: 199 is the
 * measurement most likely to have moved.
 */
const H_HIP = 199;
const H_LEG = (106 + 102) * 0.985;
const H_SINK = {walk: 9, run: 22};
const H_DUTY = {walk: 0.62, run: 0.38};
const hUnits = (gait) => {
  const reach = H_HIP - H_SINK[gait];
  return (2 * Math.sqrt(H_LEG * H_LEG - reach * reach)) / H_DUTY[gait];
};

// Matches Crosstown.jsx, which drives the Humaaans rig. A second rig means a
// second set of stride units, and a path that is safe at one figure's cadence
// is not automatically safe at another's -- so it gets checked too.
const H_SCALE = 0.95;
const H_WALK_U = hUnits('walk') * H_SCALE;
const H_RUN_U = hUnits('run') * H_SCALE;
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

/**
 * Matches Picnic.jsx.
 *
 * Three different builds — two adults, a child and a dog — on one ground
 * plane. Body size is the thing this case exists to catch: stride scales with
 * the figure, so a child solved against an adult's stride cycles its legs at
 * the wrong cadence and slides, and a dog solved against either does it worse.
 * Each gets its own options, and each is checked separately.
 *
 * The dog's path is also the longest dwell in the repository — three and a
 * half seconds parked, then a bound — which is exactly the join a treadmill
 * shows up in.
 */

const hStride = (scale, gait) => hUnits(gait) * scale;

/**
 * Dog.jsx's stride, recomputed rather than copied.
 *
 * A typed-in number here was wrong by 35% on the first attempt — the trot was
 * guessed at 190 against a real 140.6 — and a mirror that is wrong is worse
 * than no mirror, because it passes. These four constants are the dog's
 * geometry; if they change in Dog.jsx this file has to change with them, and
 * the arithmetic in between is the same triangle for both.
 */
const DOG_HIP_H = 78;
const DOG_LEG_EFF = (42 + 42) * 0.985;
const DOG_DUTY = {trot: 0.58, bound: 0.35};
const DOG_SINK = {trot: 6, bound: 24};
const dStride = (scale, gait) => {
  const reach = DOG_HIP_H - DOG_SINK[gait];
  const A = Math.sqrt(Math.max(0, DOG_LEG_EFF * DOG_LEG_EFF - reach * reach));
  return ((2 * A) / DOG_DUTY[gait]) * scale;
};

const PIC_WALK = hStride(PIC_ADULT, 'walk');
const PIC_KID_WALK = hStride(PIC_CHILD, 'walk');
const PIC_KID_RUN = hStride(PIC_CHILD, 'run');
const PIC_TROT = dStride(PIC_DOG, 'trot');
const PIC_BOUND = dStride(PIC_DOG, 'bound');

const PIC_HUMAN = {
  fps: FPS,
  walkStride: PIC_WALK,
  runStride: hStride(PIC_ADULT, 'run'),
  idleBelow: 0.35,
  runAbove: (hStride(PIC_ADULT, 'run') * 0.5) / FPS,
  turnFrames: 8,
};
const PIC_KID = {
  ...PIC_HUMAN,
  walkStride: PIC_KID_WALK,
  runStride: PIC_KID_RUN,
  runAbove: (PIC_KID_RUN * 0.46) / FPS,
  turnFrames: 6,
};
const PIC_DOGO = {
  ...PIC_HUMAN,
  walkStride: PIC_TROT,
  runStride: PIC_BOUND,
  runAbove: (PIC_BOUND * 0.42) / FPS,
  turnFrames: 5,
};

/**
 * The picnic's paths are NOT re-implemented here.
 *
 * They were, once, and the copy silently drifted from the film: three segment
 * durations were retimed here and not there, and this script went on printing
 * "clean" while the film had a negative-duration segment in it and ended with
 * the dog off the side of the frame. A validator that mirrors its subject
 * validates itself.
 *
 * So the film and this script now import the same module. Only the STRIDE
 * lengths are still computed independently — they have to be, because they
 * come from JSX the film can import and Node cannot — and being independent is
 * the point: they are a cross-check against the rigs, not a copy of them.
 */
const PIC = picnicPaths({
  WALK: PIC_WALK,
  KID_WALK: PIC_KID_WALK,
  KID_RUN: PIC_KID_RUN,
  DOG_TROT: PIC_TROT,
  DOG_BOUND: PIC_BOUND,
});

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

  {name: 'Picnic / mum', keys: PIC.mum, opts: PIC_HUMAN},
  {name: 'Picnic / dad', keys: PIC.dad, opts: PIC_HUMAN},
  {name: 'Picnic / kid', keys: PIC.kid, opts: PIC_KID},
  {name: 'Picnic / dog', keys: PIC.dog, opts: PIC_DOGO},

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

/* ── the rig itself ────────────────────────────────────────────────────────
 *
 * Everything above grades a character's path through the SCENE. These grade
 * the LEG, which is a different thing and, until now, an unguarded one: the
 * rig has twice shipped a defect that no scene-level check could see -- shoes
 * separating from ankles, and legs that could not bend a knee -- because the
 * only measurement of the posed geometry lived in throwaway probe scripts
 * that were deleted at the end of the session that wrote them.
 *
 * These solve the rig at every phase of a stride and measure the result.
 */
const {prepareBottom, poseLeg, planFeet, bendLeg, KNEE_F, artSink, footRoll} = await import(
  join(ROOT, 'remotion/src/lib/legrig.js')
);

const SWEATS = JSON.parse(
  readFileSync(join(ROOT, 'assets/packs/humaaans/bottom/Sweatpants.json'), 'utf8')
);
const BOT = prepareBottom(SWEATS);
const PHASES = 16;
const RIG_GAIT = {...gaitAt(0), lift: gaitAt(0).lift * (199 / 392)};
const RIG_STRIDE = 247.271;

/** The interior angle the knee is bent through, in degrees. 0 is straight. */
const kneeAngle = (L, f, drop) => {
  const p = poseLeg(L, f, drop);
  let d = ((p.t2 - p.t1) * 180) / Math.PI;
  while (d > 180) d -= 360;
  while (d < -180) d += 360;
  return d;
};

/** The lowest point the posed leg AND its shoe reach, in asset coordinates. */
const soleLow = (L, f, drop) => {
  const p = poseLeg(L, f, drop);
  let low = -Infinity;
  for (const pair of bendLeg(L, p).trim().split(' ')) {
    low = Math.max(low, Number(pair.split(',')[1]));
  }
  const c = Math.cos(-p.pitch);
  const sn = Math.sin(-p.pitch);
  for (const [px, py] of L.sole) {
    low = Math.max(low, p.ankle[1] + (px * sn + py * c));
  }
  return low;
};

/**
 * The hip drop the rig would use this frame -- THE RIG'S OWN, not a copy.
 *
 * This was a reimplementation of `artSink` until it silently went stale: the
 * rig learned about the heel lift and the compass bob and this copy did not,
 * so the checks went on grading a figure that no longer existed. A checker
 * that reimplements the thing it checks agrees with itself and with nothing
 * else. Import the real one and let it fail loudly instead.
 */
const sinkFor = (plan) => artSink(BOT, plan);

craftCheck('rig: a standing leg is the artist drawing, untouched', () => {
  // With no gait to serve, the rig must hand back the drawing it was given.
  // If it does not, it is quietly redrawing the character and every other
  // measurement here is of the wrong figure.
  for (const L of BOT.legs) {
    const posed = poseLeg(L, null, 0);
    const drift = Math.max(
      Math.abs(posed.ankle[0] - L.ankle[0]),
      Math.abs(posed.ankle[1] - L.ankle[1])
    );
    if (drift > 0.5) return `standing ankle moved ${drift.toFixed(2)}`;
  }
  return true;
});

craftCheck('rig: both legs are the same length, so the figure cannot limp', () => {
  // The pack draws its figures with the feet apart, which makes hip-to-ankle
  // differ by 7 units between the two legs. Taking that as the bone length
  // made the hip ride 7 units lower on every other step -- a limp nobody
  // authored, invisible in any single frame, and obvious the moment the hip
  // height was plotted over a whole cycle.
  const [a, b] = BOT.legs.map((L) => L.len);
  if (Math.abs(a - b) > 0.01) return `legs differ by ${Math.abs(a - b).toFixed(2)}`;
  const drop = BOT.legs.map((L) => Math.abs(L.ankle[1] - L.hip[1]));
  if (Math.abs(drop[0] - drop[1]) > 0.01) return 'drawn ankles are not level';
  return true;
});

craftCheck('rig: the hip bobs once per step, smoothly, and never vaults', () => {
  // Two separate ways for the pelvis to be wrong, and both have been shipped
  // here. A hip driven by "the highest position no planted leg objects to"
  // rides flat and then PLUNGES the frame the next foot lands -- 24 units in
  // one frame, read as a stumble. A hip driven by a stride that is too long
  // for the leg vaults instead. The bob is an inverted pendulum: one arc per
  // STEP, so two per cycle, and under a tenth of leg length.
  const N = 64;
  const ys = [];
  for (let i = 0; i < N; i++) {
    ys.push(artSink(BOT, planFeet(i / N, RIG_STRIDE, RIG_GAIT)));
  }
  const span = Math.max(...ys) - Math.min(...ys);
  const leg = BOT.legs[0].len;
  if (span > leg * 0.1) return `bob is ${((span / leg) * 100).toFixed(1)}% of leg`;
  if (span < leg * 0.01) return 'hip does not bob at all';

  let jump = 0;
  for (let i = 0; i < N; i++) jump = Math.max(jump, Math.abs(ys[(i + 1) % N] - ys[i]));
  if (jump > span * 0.35) return `hip steps ${jump.toFixed(1)} in one frame of ${span.toFixed(1)}`;

  // Both halves of the cycle must be the same. This is what a limp breaks.
  let asym = 0;
  for (let i = 0; i < N / 2; i++) asym = Math.max(asym, Math.abs(ys[i] - ys[i + N / 2]));
  if (asym > leg * 0.005) return `steps differ by ${asym.toFixed(2)}`;
  return true;
});

craftCheck('rig: the foot rolls heel-to-toe, and the curve never breaks', () => {
  // Heel strike with the toes a few degrees up, flat through midstance, heel
  // off at the end -- then the same curve carries on THROUGH swing back to
  // the next strike. Writing stance and swing as two rules glued at toe-off
  // put a 15-degree snap at the join, and the ankle jumped 20 units with it.
  const N = 64;
  const r = [];
  for (let i = 0; i < N; i++) r.push(footRoll(i / N, RIG_GAIT.duty));
  const deg = (x) => (x * 180) / Math.PI;
  let jump = 0;
  for (let i = 0; i < N; i++) jump = Math.max(jump, Math.abs(deg(r[(i + 1) % N] - r[i])));
  if (jump > 6) return `foot snaps ${jump.toFixed(1)} degrees in one frame`;
  if (deg(r[0]) < 2) return 'toes are not up at heel strike';
  const off = Math.min(...r.map(deg));
  if (off > -10) return `heel never lifts (least ${off.toFixed(1)} degrees)`;
  const mid = deg(r[Math.round(N * RIG_GAIT.duty * 0.4)]);
  if (Math.abs(mid) > 1) return `foot is not flat at midstance (${mid.toFixed(1)} degrees)`;
  return true;
});

craftCheck('rig: the sole stays on the ground through every stride phase', () => {
  let worst = 0;
  let at = 0;
  for (let i = 0; i < PHASES; i++) {
    const phase = i / PHASES;
    const plan = planFeet(phase, RIG_STRIDE, RIG_GAIT);
    const drop = sinkFor(plan);
    for (const [L, f] of [[BOT.legs[0], plan.far], [BOT.legs[1], plan.near]]) {
      if (!f.planted) continue;
      const dip = soleLow(L, f, drop) + drop - BOT.ground;
      if (Math.abs(dip) > Math.abs(worst)) { worst = dip; at = phase; }
    }
  }
  // A couple of units either way is sub-pixel at every scale a film uses it
  // at; a foot sinking ten into the grass is the bug this exists to catch.
  if (Math.abs(worst) > 4) return `sole off ground by ${worst.toFixed(1)} at phase ${at.toFixed(3)}`;
  return true;
});

craftCheck('rig: the knee actually bends, and only forwards', () => {
  let peak = 0;
  for (let i = 0; i < PHASES; i++) {
    const plan = planFeet(i / PHASES, RIG_STRIDE, RIG_GAIT);
    const drop = sinkFor(plan);
    for (const [L, f] of [[BOT.legs[0], plan.far], [BOT.legs[1], plan.near]]) {
      const k = kneeAngle(L, f, drop);
      // Negative means the joint has hinged the wrong way -- a bird's leg.
      if (k < -2) return `knee bent backwards ${k.toFixed(1)} deg`;
      peak = Math.max(peak, k);
    }
  }
  // A swinging leg has to fold to clear the ground. Real gait peaks at 60-70;
  // anything under 25 is the telescoping stick this rig replaced.
  if (peak < 25) return `peak knee flexion only ${peak.toFixed(1)} deg -- leg is not bending`;
  return true;
});

craftCheck('rig: the stance knee yields after contact, so the walk is not a march', () => {
  /**
   * Measured over EARLY stance only.
   *
   * Taking the peak over the whole of stance grades the wrong leg: at double
   * support the trailing foot is about to leave the ground, and a trailing leg
   * is legitimately bent 40 degrees or so on its way to toe-off. Averaging
   * that in hides whether the leg that just LANDED gave at all, which is the
   * thing being tested.
   */
  let peak = 0;
  for (let i = 0; i < PHASES; i++) {
    const phase = i / PHASES;
    const plan = planFeet(phase, RIG_STRIDE, RIG_GAIT);
    const drop = sinkFor(plan);
    for (const [L, f, p] of [[BOT.legs[0], plan.far, (phase + 0.5) % 1], [BOT.legs[1], plan.near, phase]]) {
      if (!f.planted || p > RIG_GAIT.duty * 0.35) continue;
      peak = Math.max(peak, kneeAngle(L, f, drop));
    }
  }
  if (peak < 4) return `stance knee never gives (peak ${peak.toFixed(1)} deg)`;
  if (peak > 40) return `stance knee collapses to ${peak.toFixed(1)} deg`;
  return true;
});

craftCheck('rig: the leg keeps its drawn width through the bend', () => {
  /**
   * The pinched-knee test.
   *
   * Blending the two bones by averaging their transformed POINTS -- linear
   * blend skinning, and the natural way to write `bendLeg` -- averages two
   * rotated copies of the same normal, so the limb narrows to cos(bend/2) of
   * its drawn width right where it is bent. That is 13% at a walk's 60 degrees
   * and 33% at a run's 96: a leg that visibly wasp-waists at the knee on every
   * stride. Nothing else here would notice, because the skeleton, the foot and
   * the hip are all still exactly right -- only the artwork is wrong.
   *
   * Measured by tracking the two outline vertices that straddle the knee and
   * asking whether they stay as far apart as they were drawn.
   */
  const L = BOT.legs[0];
  const [hx, hy] = L.hip;
  const ux = L.dx / L.art;
  const uy = L.dy / L.art;
  const rest = L.outline.map(([x, y]) => {
    const px = x - hx;
    const py = y - hy;
    return { s: px * ux + py * uy, n: px * -uy + py * ux };
  });

  const straddle = (sign) => {
    let best = -1;
    let bd = Infinity;
    for (let i = 0; i < rest.length; i++) {
      if (Math.sign(rest[i].n) !== sign) continue;
      const d = Math.abs(rest[i].s - L.art * KNEE_F);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  };
  const iL = straddle(-1);
  const iR = straddle(1);
  if (iL < 0 || iR < 0) return 'could not find outline vertices either side of the knee';

  const gap = (p) => {
    const pts = bendLeg(L, p).trim().split(' ').map((t) => t.split(',').map(Number));
    return Math.hypot(pts[iL][0] - pts[iR][0], pts[iL][1] - pts[iR][1]);
  };

  const drawn = gap(poseLeg(L, null, 0));
  let worst = 0;
  let at = 0;
  for (const speed of [0, 1]) {
    const g = { ...gaitAt(speed), lift: gaitAt(speed).lift * (199 / 392) };
    for (let i = 0; i < 64; i++) {
      const plan = planFeet(i / 64, RIG_STRIDE, g);
      for (const f of [plan.near, plan.far]) {
        const p = poseLeg(L, f, 0);
        const loss = Math.abs(1 - gap(p) / drawn);
        if (loss > worst) { worst = loss; at = Math.abs(kneeAngle(L, f, 0)); }
      }
    }
  }
  if (worst > 0.04) {
    return `knee pinches ${(worst * 100).toFixed(1)}% at ${at.toFixed(0)} deg of bend`;
  }
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
