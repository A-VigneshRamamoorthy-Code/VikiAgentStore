/**
 * Locomotion — physics-correct ground movement for 2D characters.
 *
 * ── The rule this module exists to enforce ──────────────────────────────────
 *
 *   A character's FACING and STRIDE PHASE are DERIVED from where its body
 *   actually goes. Neither is ever authored by hand.
 *
 * Every backwards-walking character ever shipped by this crew came from
 * breaking that rule. The canonical example, from an earlier film:
 *
 *     const facing = from === 'left';
 *     const flip   = local > tOut ? !facing : facing;   // "leaving means
 *                                                       //  facing the other way"
 *
 * It does not. A visitor who entered from the left and exits stage *right* is
 * still travelling right, so flipping them on the way out drew a figure
 * moonwalking off the screen at 24fps. The author flipped a boolean that
 * described the *story* ("they're leaving") instead of measuring the thing
 * that matters ("which way is the body moving").
 *
 * So: you give this module a path — where the body is, over time — and it
 * returns everything a rig needs to be drawn honestly. There is no way to
 * ask it for a facing that disagrees with the motion, because facing is not
 * an input.
 *
 * ── What it guarantees ─────────────────────────────────────────────────────
 *
 *  1. Facing always agrees with velocity. Impossible to moonwalk.
 *  2. Stride phase advances with DISTANCE TRAVELLED, never with a clock.
 *     This is what kills foot slide: the feet cannot outrun the body,
 *     because the body's displacement is the only thing that moves them.
 *  3. A standing character has no cycle. Idle is a pose, not phase 0.
 *  4. Turning around costs frames. The character pivots through a squash
 *     rather than teleporting its facing between two drawings.
 *  5. Gait follows speed. You cannot walk at running speed or the legs
 *     visibly under-rotate; the solver picks the gait and the stride length
 *     that matches the pace.
 *  6. Weight: the body bobs twice per stride (once per footfall), leans into
 *     acceleration, and lands its feet on the ground plane every time.
 */

const TAU = Math.PI * 2;
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const smooth = (u) => u * u * (3 - 2 * u);

/* ── gait ─────────────────────────────────────────────────────────────────
 *
 * These live here rather than next to the drawing code, and that placement is
 * load-bearing. The solver has to know how long a foot stays down in order to
 * say where it is; the rig has to know the same thing in order to draw it. The
 * first version kept two copies — the solver assumed a foot was planted for
 * half the cycle, the rig planted it for 0.62 of one — and the validator duly
 * reported foot slide on every path, on a rig whose feet were in fact glued
 * down. A discrepancy between two descriptions of the same walk is not a
 * physics failure; it is a bookkeeping failure that looks exactly like one.
 *
 * `duty` is the fraction of the cycle a given foot is on the ground. Above 0.5
 * both feet are briefly down (a walk); below it, neither is (a run).
 */
export const GAITS = {
  walk: {duty: 0.62, lift: 54, armSwing: 0.30, bodyLean: 2.5, heel: 0.5},
  run: {duty: 0.38, lift: 132, armSwing: 0.68, bodyLean: 9.0, heel: 0.9},
};

/**
 * A gait is a dial, not a switch.
 *
 * Treating it as a switch left one frame in every walk-to-run transition where
 * the stride changed instantly, which teleported the planted foot ~50 units
 * sideways — a real, visible slip, correctly reported by the validator. Nobody
 * changes stride length in 33 milliseconds; they lengthen it over a step or
 * two. `mix` is that ramp, 0 walk to 1 run, and everything a gait implies is
 * read off it.
 *
 * Both the solver and the rig call this, so a blended frame is described the
 * same way in scene space and in character space.
 */
export const gaitAt = (mix) => {
  const m = clamp(mix, 0, 1);
  const w = GAITS.walk;
  const r = GAITS.run;
  const L = (a, b) => a + (b - a) * m;
  return {
    duty: L(w.duty, r.duty),
    lift: L(w.lift, r.lift),
    armSwing: L(w.armSwing, r.armSwing),
    bodyLean: L(w.bodyLean, r.bodyLean),
    heel: L(w.heel, r.heel),
  };
};

/** The stride implied by a gait mix, given the two endpoints. */
export const strideAt = (mix, walkStride, runStride) =>
  walkStride + (runStride - walkStride) * clamp(mix, 0, 1);

/**
 * Where one foot is, relative to the pelvis, at leg-phase `p`.
 *
 * During stance the foot is PLANTED, so relative to a pelvis moving forward at
 * a constant rate it must travel backwards at exactly that rate — a straight
 * line, not a curve. That single linear segment is what makes the foot stick
 * to the ground; ease it and the character skates.
 *
 * The excursion is `stride * duty`, because that is exactly how far the body
 * travels while this foot is down. Work it through and the world position of a
 * stance foot is `x0 + stride*duty/2` for the whole of stance — independent of
 * phase, which is the algebraic statement of "it is standing still".
 */
export const footOffset = (p, stride, g) => {
  const A = (stride * g.duty) / 2;
  if (p < g.duty) {
    return {x: A - 2 * A * (p / g.duty), y: 0, planted: true};
  }
  const u = (p - g.duty) / (1 - g.duty);
  return {
    x: -A + 2 * A * smooth(u),
    y: -g.lift * Math.sin(Math.PI * u),
    planted: false,
  };
};

/* ── easing ──────────────────────────────────────────────────────────────── */

/**
 * `linear` is deliberately absent from anything that moves a body. A linear
 * tween between two positions is the single clearest tell of a generated
 * film. It survives here only for `creep` — a constant-rate drift slow enough
 * that it must not be perceived at all.
 */
export const EASES = {
  creep: (t) => t,
  easeIn: (t) => t * t,
  easeOut: (t) => 1 - (1 - t) * (1 - t),
  easeInOut: (t) => (t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2),
  /**
   * The house curve: leave fast, overshoot by 12%, settle. Used for anything
   * that starts or stops sharply. The overshoot is what makes a stop read as
   * a body with mass arriving somewhere, rather than a value reaching a
   * number.
   */
  overshoot: (t) => {
    if (t >= 1) return 1;
    const c = 1.70158 * 0.7;
    const u = t - 1;
    return 1 + (c + 1) * u * u * u + c * u * u;
  },
};

/* ── path sampling ───────────────────────────────────────────────────────── */

/**
 * Keys are `{t, x, y?, ease?}`, `t` in frames. `ease` describes how the body
 * travels INTO that key from the previous one.
 *
 * A repeated position is a dwell, and a dwell is how you stand still — the
 * solver sees zero velocity and drops the character into an idle pose. You do
 * not tell it to stand; you tell it not to go anywhere.
 */
const samplePath = (keys, N) => {
  const xs = new Float64Array(N);
  const ys = new Float64Array(N);
  let k = 0;
  for (let i = 0; i < N; i++) {
    while (k < keys.length - 2 && i >= keys[k + 1].t) k++;
    const a = keys[k];
    const b = keys[Math.min(k + 1, keys.length - 1)];
    if (b === a || b.t <= a.t) {
      xs[i] = b.x;
      ys[i] = b.y ?? 0;
      continue;
    }
    const raw = clamp((i - a.t) / (b.t - a.t), 0, 1);
    const ease = EASES[b.ease ?? 'easeInOut'] ?? EASES.easeInOut;
    const u = ease(raw);
    xs[i] = a.x + (b.x - a.x) * u;
    ys[i] = (a.y ?? 0) + ((b.y ?? 0) - (a.y ?? 0)) * u;
  }
  return {xs, ys};
};

/* ── the solver ──────────────────────────────────────────────────────────── */

/**
 * @param {Array} keys  `[{t, x, y?, ease?}, ...]`, ascending `t`, frames.
 * @param {Object} opts
 * @param {number} opts.fps
 * @param {number} opts.walkStride  ground units covered by ONE full walk
 *                                  cycle at this character's scale. Get this
 *                                  wrong and the feet slide — it is the only
 *                                  number in here you have to measure against
 *                                  the artwork rather than guess.
 * @param {number} opts.runStride   same, for a run. Longer: a run is not a
 *                                  fast walk, it is a bigger one.
 * @param {number} opts.idleBelow   units/frame under which the body counts as
 *                                  stationary.
 * @param {number} opts.runAbove    units/frame over which the gait becomes a run.
 * @param {number} opts.turnFrames  frames spent pivoting when direction reverses.
 * @param {number} opts.initialFacing  +1 right, -1 left. Only consulted while
 *                                  the body has never moved.
 *
 * @returns {{frames: Array, at: (f:number)=>Object, duration: number}}
 *   Each frame carries:
 *     x, y        ground position
 *     vx          signed velocity, units/frame
 *     speed       |vx|
 *     facing      +1 | -1, the settled direction
 *     facingScale -1..+1 — what you actually put in `scaleX`. Passes through
 *                 a clamped zero during a turn, which draws the pivot for free.
 *     turning     0..1, non-zero only mid-pivot
 *     phase       0..1 through the current stride cycle
 *     gait        'idle' | 'walk' | 'run'
 *     bob         vertical offset from the double-bounce, already negative-up
 *     lean        degrees, leaning into acceleration
 *     plantedFoot 'near' | 'far' | null
 *     plantedX    world x of the planted foot, for slide checking
 */
export function solveLocomotion(keys, opts = {}) {
  const {
    fps = 30,
    walkStride = 132,
    runStride = 190,
    idleBelow = 0.12,
    runAbove = 6.0,
    turnFrames = 6,
    gaitBlendFrames = 14,   // ~half a second to change stride, as people do
    initialFacing = 1,
    bobAmp = 5,
    leanPerAccel = 6.5,
    maxLean = 9,
  } = opts;

  if (!keys || keys.length === 0) throw new Error('solveLocomotion: no keys');
  const sorted = [...keys].sort((a, b) => a.t - b.t);
  const N = Math.max(1, Math.ceil(sorted[sorted.length - 1].t) + 1);
  const {xs, ys} = samplePath(sorted, N);

  // ── velocity, by central difference so acceleration is symmetric ──────────
  const vx = new Float64Array(N);
  for (let i = 0; i < N; i++) {
    const a = xs[Math.max(0, i - 1)];
    const b = xs[Math.min(N - 1, i + 1)];
    const span = Math.min(N - 1, i + 1) - Math.max(0, i - 1);
    vx[i] = span === 0 ? 0 : (b - a) / span;
  }
  const ax = new Float64Array(N);
  for (let i = 0; i < N; i++) {
    const a = vx[Math.max(0, i - 1)];
    const b = vx[Math.min(N - 1, i + 1)];
    const span = Math.min(N - 1, i + 1) - Math.max(0, i - 1);
    ax[i] = span === 0 ? 0 : (b - a) / span;
  }

  // ── desired facing: purely a reading of the velocity ──────────────────────
  //
  // Carried forward through stationary stretches, because a character who
  // stops walking does not also stop facing the way they were facing.
  const desired = new Int8Array(N);
  let carry = initialFacing >= 0 ? 1 : -1;
  for (let i = 0; i < N; i++) {
    if (Math.abs(vx[i]) > idleBelow) carry = vx[i] > 0 ? 1 : -1;
    desired[i] = carry;
  }
  // A character standing still at the top of a shot should already be facing
  // wherever they are about to go, rather than snapping round on frame 2.
  for (let i = N - 1; i >= 0; i--) {
    if (Math.abs(vx[i]) > idleBelow) break;
    desired[i] = desired[Math.min(N - 1, i + 1)];
  }
  {
    let first = -1;
    for (let i = 0; i < N; i++) {
      if (Math.abs(vx[i]) > idleBelow) { first = i; break; }
    }
    if (first > 0) for (let i = 0; i < first; i++) desired[i] = desired[first];
  }

  // ── turns cost frames ─────────────────────────────────────────────────────
  //
  // `facingScale` sweeps old → new through a clamped zero, so the body
  // narrows, passes through its own axis and opens out the other way. That is
  // how limited animation turns a character around, and it costs two drawings
  // instead of a whole 3/4 view.
  const facing = new Int8Array(N);
  const facingScale = new Float64Array(N);
  const turning = new Float64Array(N);
  const flips = [];
  for (let i = 1; i < N; i++) if (desired[i] !== desired[i - 1]) flips.push(i);

  for (let i = 0; i < N; i++) {
    facing[i] = desired[i];
    facingScale[i] = desired[i];
  }
  const half = Math.max(1, Math.round(turnFrames / 2));
  for (const f of flips) {
    const from = desired[f - 1];
    for (let d = -half; d <= half; d++) {
      const i = f + d;
      if (i < 0 || i >= N) continue;
      const u = clamp((d + half) / (2 * half), 0, 1);
      const c = Math.cos(u * Math.PI);
      const mag = Math.max(0.14, Math.abs(c));
      facingScale[i] = from * Math.sign(c === 0 ? 1 : c) * mag;
      turning[i] = 1 - Math.abs(c);
    }
  }

  // ── gait, then phase from distance ────────────────────────────────────────
  //
  // Phase is integrated from |dx| over the stride length of the gait actually
  // being used. Nothing here reads the frame number, which is the whole point:
  // if the body does not move, the legs cannot.
  //
  // The gait itself is resolved in two passes. The first classifies each frame
  // by speed; the second smooths that classification into a continuous mix, so
  // a character breaking into a run lengthens their stride over about half a
  // second rather than between two frames.
  const gait = new Array(N);
  const rawMix = new Float64Array(N);
  for (let i = 0; i < N; i++) {
    const sp = Math.abs(vx[i]);
    gait[i] = sp <= idleBelow ? 'idle' : sp >= runAbove ? 'run' : 'walk';
    rawMix[i] = gait[i] === 'run' ? 1 : 0;
  }

  const mix = new Float64Array(N);
  const blendHalf = Math.max(1, Math.round(gaitBlendFrames / 2));
  for (let i = 0; i < N; i++) {
    let sum = 0;
    let n = 0;
    for (let j = i - blendHalf; j <= i + blendHalf; j++) {
      sum += rawMix[clamp(j, 0, N - 1)];
      n++;
    }
    mix[i] = sum / n;
  }

  // A stride may only change while the foot is off the ground.
  //
  // Blending the mix per-frame replaced one 50-unit slip with twenty small
  // ones, which is worse: it is not possible to lengthen your stride halfway
  // through a step, because one of your feet is on the ground and it is not
  // going anywhere. So the mix is sampled once per step and HELD, and steps
  // are exactly where the trailing foot lifts — the half-cycle boundaries.
  // A planted foot then provably cannot move, because nothing that determines
  // its position changes while it is down.
  const mixHeld = new Float64Array(N);
  const phase = new Float64Array(N);
  let ph = 0;
  let held = mix[0];
  for (let i = 0; i < N; i++) {
    if (i > 0) {
      const stride = strideAt(held, walkStride, runStride);
      const dx = Math.abs(xs[i] - xs[i - 1]);
      if (gait[i] !== 'idle' && stride > 0) {
        const prev = ph;
        ph += dx / stride;
        if (Math.floor(prev * 2) !== Math.floor(ph * 2)) held = mix[i];
      }
    }
    mixHeld[i] = held;
    phase[i] = ph % 1;
  }

  // ── weight ────────────────────────────────────────────────────────────────
  const frames = new Array(N);
  for (let i = 0; i < N; i++) {
    const moving = gait[i] !== 'idle';
    // Two bounces per cycle: one per footfall. Without it a walk reads as a
    // cut-out being dragged sideways.
    const bob = moving ? -Math.abs(Math.sin(phase[i] * TAU)) * bobAmp : 0;
    // Lean into acceleration, expressed in the character's own local space so
    // it stays correct after the facing mirror is applied.
    const accelAlong = ax[i] * facing[i];
    const lean = moving ? clamp(accelAlong * leanPerAccel, -maxLean, maxLean) : 0;

    // Which foot is down, and where it is in the WORLD. This is derived from
    // the same `footOffset` the rig draws with, so the two cannot disagree —
    // and the facing mirror is applied once, properly. (The previous version
    // wrote `facing * facing`, which is 1 for every value facing can take,
    // and so silently checked the wrong foot on every leftward walk.)
    //
    // During double support — most of a walk, where duty exceeds 0.5 — both
    // feet are down and one must be chosen. It is the one that landed MOST
    // RECENTLY, which is `phase < 0.5 ? near : far`. Reporting the older foot
    // instead makes the changeover fall in the middle of a stance rather than
    // at its edge, and any stride adjustment then looks like that foot slipped
    // when in truth it was simply about to be lifted.
    let plantedFoot = null;
    let plantedX = null;
    if (moving) {
      const g = gaitAt(mixHeld[i]);
      const stride = strideAt(mixHeld[i], walkStride, runStride);
      const newest = phase[i] < 0.5 ? 'near' : 'far';
      const p = newest === 'near' ? phase[i] : (phase[i] + 0.5) % 1;
      const f = footOffset(p, stride, g);
      // In a run there is a flight phase where neither foot is down at all.
      if (f.planted) {
        plantedFoot = newest;
        plantedX = xs[i] + facing[i] * f.x;
      }
    }

    frames[i] = {
      i,
      t: i / fps,
      x: xs[i],
      y: ys[i],
      vx: vx[i],
      ax: ax[i],
      speed: Math.abs(vx[i]),
      facing: facing[i],
      facingScale: facingScale[i],
      turning: turning[i],
      phase: phase[i],
      gait: gait[i],
      gaitMix: mixHeld[i],
      moving,
      bob,
      lean,
      plantedFoot,
      plantedX,
    };
  }

  const at = (f) => frames[clamp(Math.round(f), 0, N - 1)];
  return {frames, at, duration: N, fps};
}

/* ── the validator ───────────────────────────────────────────────────────── */

/**
 * Grades a solved track for the errors that make an audience say "that looks
 * wrong" without being able to say why. Run it in CI: every one of these has
 * shipped in a film from this crew at least once.
 *
 * Returns `{ok, errors: [...]}`. `errors` are strings ready to print.
 */
export function validateLocomotion(track, opts = {}) {
  const {
    idleBelow = 0.12,
    maxSlide = 2.0,       // world units a planted foot may drift per frame
    maxStep = 60,         // units/frame above which a move is a teleport
    groundY = null,       // if given, feet must stay on it
  } = opts;
  const errors = [];
  const F = track.frames;

  for (let i = 1; i < F.length; i++) {
    const p = F[i - 1];
    const c = F[i];

    // 1. Moonwalk: the body is moving one way while the drawing faces the other.
    if (c.speed > idleBelow && c.turning < 0.2) {
      const dir = c.vx > 0 ? 1 : -1;
      if (dir !== c.facing) {
        errors.push(
          `frame ${i}: MOONWALK — travelling ${dir > 0 ? 'right' : 'left'} ` +
          `(vx=${c.vx.toFixed(2)}) while facing ${c.facing > 0 ? 'right' : 'left'}`
        );
      }
    }

    // 2. Cycling on the spot: legs walking while the body is parked.
    if (c.speed <= idleBelow && Math.abs(c.phase - p.phase) > 1e-6) {
      errors.push(
        `frame ${i}: TREADMILL — stride phase advanced ${(c.phase - p.phase).toFixed(4)} ` +
        `at speed ${c.speed.toFixed(3)}`
      );
    }

    // 3. Foot slide: a planted foot that moves in world space.
    if (c.plantedFoot && p.plantedFoot === c.plantedFoot && p.plantedX !== null) {
      const slide = Math.abs(c.plantedX - p.plantedX);
      if (slide > maxSlide) {
        errors.push(
          `frame ${i}: FOOT SLIDE — planted ${c.plantedFoot} foot moved ` +
          `${slide.toFixed(2)} units`
        );
      }
    }

    // 4. Teleport.
    if (Math.abs(c.x - p.x) > maxStep) {
      errors.push(
        `frame ${i}: TELEPORT — body jumped ${Math.abs(c.x - p.x).toFixed(1)} units`
      );
    }

    // 5. Facing snapping between drawings instead of pivoting.
    if (c.facing !== p.facing && c.turning < 0.2 && p.turning < 0.2) {
      errors.push(`frame ${i}: SNAP TURN — facing flipped with no pivot`);
    }

    // 6. Leaving the ground plane.
    if (groundY !== null && Math.abs(c.y - groundY) > 0.5) {
      errors.push(
        `frame ${i}: OFF GROUND — y=${c.y.toFixed(1)} vs ground ${groundY}`
      );
    }
  }

  // Collapse runs of the same fault so one bad move is one line, not 200.
  const seen = new Map();
  for (const e of errors) {
    const kind = e.slice(e.indexOf(': ') + 2, e.indexOf(' —'));
    seen.set(kind, (seen.get(kind) ?? 0) + 1);
  }
  return {
    ok: errors.length === 0,
    errors,
    summary: [...seen.entries()].map(([k, n]) => `${k} ×${n}`),
  };
}

/**
 * Stride length that a rig of a given height should cover in one cycle.
 *
 * Human proportion: a comfortable step is about 0.41 × standing height, and a
 * cycle is two steps. Deriving it means a character rescaled for depth keeps
 * its feet planted instead of skating, which hand-tuned numbers never survive.
 */
export const strideForHeight = (height, gait = 'walk') =>
  height * (gait === 'run' ? 1.18 : 0.82);
