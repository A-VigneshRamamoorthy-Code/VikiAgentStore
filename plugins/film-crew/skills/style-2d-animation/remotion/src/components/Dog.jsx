import React from 'react';
import {footOffset, strideAt} from '../lib/locomotion.js';
import {bobShape, springScale} from '../lib/timing.js';
import {chainPhases, whipAmplitude, whipPose} from '../lib/overlap.js';

/**
 * Dog -- a procedurally-drawn quadruped riding the same solver the bipeds do.
 *
 * The solver (`lib/locomotion.js`) only ever hands out a body position, a
 * facing and a phase -- it does not know or care how many legs stand under
 * that body. Everything species-specific lives here: a quadruped's gait is
 * not "a walk with two extra legs bolted on", it is a different topology of
 * which feet share a beat, and that is the one thing worth getting right.
 *
 * A TROT pairs the legs diagonally (front-left with back-right) so the body
 * is always supported on two feet that brace each other fore-and-aft and
 * side-to-side -- which is also why a trot barely bobs. A BOUND pairs them
 * laterally instead (both front feet, then both back feet, offset a quarter
 * cycle) with a real flight phase between -- which is why it bobs hard and
 * needs a much longer stride. Both are expressed as one continuous per-leg
 * phase OFFSET that is blended by `mix`, not switched at a threshold: a hard
 * switch would jump a planted foot's phase discontinuously, which is exactly
 * the teleport the solver goes to some trouble to avoid everywhere else.
 *
 * The tail and the head+ear both reuse `chainPhases` -- the same accumulating
 * 2-frames-per-link delay the reference doc asks for. The only reason there
 * are two separate chains rather than one four-link one is that they hang off
 * different anchors (the hip, and the neck) and travel at different rates
 * while the dog is standing still: a parked dog's tail keeps idling, its head
 * does not.
 */

const TAU = Math.PI * 2;
const D2R = Math.PI / 180;
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const lerp = (a, b, u) => a + (b - a) * u;

/* ── proportions, dog units, ground at y=0, up negative -------------------
 *
 * Same convention `locomotion.js` and `Humaaans.jsx` already use. Front and
 * back axles share one standing height: a generic, level-backed dog rather
 * than any one breed, which is what a rig meant to be recoloured for a whole
 * cast needs to be.
 */
export const DOG = {
  hipH: 78,        // shoulder/hip height off the ground, standing
  thigh: 42,
  shin: 42,
  hipDx: 7,        // near/far splay per axle -- kept small, same reason as
                   // Humaaans' HIP_DX: the fore-aft gap in a stride comes
                   // from the FEET, not from spreading the joints apart
  bodyLen: 150,
  bodyH: 70,
  shoulderX: 50,   // front axle, from body centre
  hipX: -50,       // rear axle
  headX: 116,
  headY: -134,
  headR: 32,
  earLen: 30,
  tailLinks: 3,
  tailLen: 24,
};

const HIP_H = DOG.hipH;
const THIGH = DOG.thigh;
const SHIN = DOG.shin;
const LEG_EFF = (THIGH + SHIN) * 0.985; // never fully lock the knee
const ANKLE_Y = 0;
const PELVIS_Y = ANKLE_Y - HIP_H;        // -78, shared rest height, both axles
const HIP_DX = DOG.hipDx;

const BODY_TOP = PELVIS_Y - 50;          // belly hangs 20 below the hip line,
                                          // so legs read as emerging from it

/* ── gait ------------------------------------------------------------------
 *
 * Dog-specific, not read from `GAITS` in locomotion.js -- that table is a
 * biped's walk/run and a quadruped's gaits are a different animal, literally.
 * A trot's duty is close to a walk's for the same reason (two-point support
 * most of the time); a bound's duty is lower than a run's because ALL FOUR
 * feet leave the ground at once, not just the trailing one.
 */
const DOG_GAITS = {
  trot: {duty: 0.58, lift: 16},
  bound: {duty: 0.35, lift: 34},
};
const SINK = {trot: 6, bound: 24}; // how much the hips may drop -- this IS the stride, see below

const dogGaitAt = (mix) => ({
  duty: lerp(DOG_GAITS.trot.duty, DOG_GAITS.bound.duty, mix),
  lift: lerp(DOG_GAITS.trot.lift, DOG_GAITS.bound.lift, mix),
});

/** Drop needed for a fixed-length leg to reach a foot `ax` ahead of its hip --
 *  the same triangle Humaaans/Character use, read backwards to get stride. */
const pelvisSink = (ax) =>
  Math.max(0, HIP_H - Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - ax * ax)));

const strideDog = (gait) => {
  const g = DOG_GAITS[gait] ?? DOG_GAITS.trot;
  const reach = HIP_H - (SINK[gait] ?? SINK.trot);
  const A = Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - reach * reach));
  return (2 * A) / g.duty;
};

const DOG_STRIDE = {trot: strideDog('trot'), bound: strideDog('bound')};

/** Stride in SCENE units for a dog drawn at `scale`. */
export const dogStride = (scale = 1, gait = 'trot') =>
  (DOG_STRIDE[gait] ?? DOG_STRIDE.trot) * scale;

/**
 * Per-leg phase offset from the body's own gait phase.
 *
 * At mix=0 this is the trot the brief asks for: FL and BR both land at
 * offset 0 (a diagonal pair), FR and BL both land at offset 0.5 (the other
 * diagonal, half a cycle later). At mix=1 it is a bound: both front feet
 * together at 0, both back feet together a quarter-cycle after -- gather,
 * then extend. The four numbers are lerped between those two tables rather
 * than the pairing being switched at some mix threshold, because a switch
 * would move a currently-planted foot's phase in one frame, which is a
 * slide by definition.
 */
const legOffsets = (mix) => ({
  FL: 0,
  FR: lerp(0.5, 0, mix),
  BL: lerp(0.5, 0.25, mix),
  BR: lerp(0, 0.25, mix),
});

/** Two-bone IK, identical in shape to Humaaans/Character -- same physics,
 *  same failure mode (hyperextension) if it were ever copied and drifted. */
const ik = (hx, hy, fx, fy, l1, l2, bend) => {
  let dx = fx - hx;
  let dy = fy - hy;
  let d = Math.hypot(dx, dy);
  const reach = (l1 + l2) * 0.995;
  if (d > reach) {
    const k = reach / d;
    dx *= k;
    dy *= k;
    d = reach;
    fx = hx + dx;
    fy = hy + dy;
  }
  if (d < 1e-6) return {jx: hx, jy: hy + l1, fx, fy};
  const a = Math.acos(clamp((d * d + l1 * l1 - l2 * l2) / (2 * d * l1), -1, 1));
  const ang = Math.atan2(dy, dx) + bend * a;
  return {jx: hx + Math.cos(ang) * l1, jy: hy + Math.sin(ang) * l1, fx, fy};
};

/* ── legs -------------------------------------------------------------- */

const Stroke = ({a, b, fill, w}) => (
  <path
    d={`M${a[0].toFixed(1)} ${a[1].toFixed(1)} L${b[0].toFixed(1)} ${b[1].toFixed(1)}`}
    fill="none"
    stroke={fill}
    strokeWidth={w}
    strokeLinecap="round"
  />
);

const THIGH_W = 24;
const SHIN_W = 16;
// Off `DOG.shin` rather than a free-floating number, so the pad scales with
// the leg it belongs to: wider than the shin's own stroke so it steps out
// past it, flatter than tall so it reads as resting on the ground rather
// than as the stroke's own round cap.
const PAW_RX = DOG.shin * 0.32;
const PAW_RY = DOG.shin * 0.17;

/** Hip to knee to paw, two round-capped strokes overlapping into a joint --
 *  exactly `WalkingLegs`' `Pant`, just with a paw pad instead of a shoe. */
const Leg = ({hip, knee, paw, fill}) => (
  <g>
    <Stroke a={hip} b={knee} fill={fill} w={THIGH_W} />
    <Stroke a={knee} b={paw} fill={fill} w={SHIN_W} />
    <ellipse cx={paw[0]} cy={paw[1]} rx={PAW_RX} ry={PAW_RY} fill={fill} />
  </g>
);

/** Off-side pair: the same leg in less light, not a different limb, so the
 *  cue is a translucent wash of the shadow tone over the same fill (works
 *  for any caller's colour string, no parsing needed) layered under the
 *  existing opacity dim -- alpha alone barely shows on a light fur tone. */
const OFFSIDE_SHADE = '#191847';
const OffsideLeg = (props) => (
  <g opacity="0.8">
    <Leg {...props} />
    <g opacity="0.32">
      <Leg {...props} fill={OFFSIDE_SHADE} />
    </g>
  </g>
);

const buildLeg = (hipX, hipY, plan) => {
  const {jx, jy, fx, fy} = ik(hipX, hipY, hipX + plan.x, ANKLE_Y + plan.y, THIGH, SHIN, -1);
  return {hip: [hipX, hipY], knee: [jx, jy], paw: [fx, fy]};
};

/** A parked leg: a small relaxed splay plus the idle breathing drift, no
 *  gait phase involved -- standing still is a pose, not phase 0. */
const standingLeg = (hipX, splay, breathe) => {
  const hipY = PELVIS_Y + breathe;
  return {
    hip: [hipX, hipY],
    knee: [hipX + splay * 2.5, (hipY + ANKLE_Y) / 2 + breathe * 0.3],
    paw: [hipX + splay * 4, ANKLE_Y],
  };
};

/* ── tail: a 3-link chain ------------------------------------------------
 *
 * Rest angles curl the tail up and back -- a relaxed, happy carriage -- and
 * the dynamic part is only ever added ON TOP of that curl. Amplitude is zero
 * at link 0 (bolted to the spine, per `whipAmplitude`'s own contract) and
 * grows to the tip, so the base barely moves and the tip does the swishing,
 * which is what a real tail actually does.
 */
const TAIL_REST_DEG = [200, 233, 262];
const TAIL_SWING_DEG = 34;
const TAIL_W = [11, 8, 6];

const Tail = ({anchor, phases, fill}) => {
  let [x, y] = anchor;
  const parts = [];
  for (let i = 0; i < phases.length; i++) {
    const swing = whipPose(phases[i]).bend * TAIL_SWING_DEG * whipAmplitude(i / (phases.length - 1));
    const ang = (TAIL_REST_DEG[i] + swing) * D2R;
    const len = DOG.tailLen * (1 - i * 0.08);
    const nx = x + Math.cos(ang) * len;
    const ny = y + Math.sin(ang) * len;
    parts.push(<Stroke key={i} a={[x, y]} b={[nx, ny]} fill={fill} w={TAIL_W[i]} />);
    x = nx;
    y = ny;
  }
  parts.push(<circle key="tip" cx={x} cy={y} r={TAIL_W[TAIL_W.length - 1] * 0.55} fill={fill} />);
  return <g>{parts}</g>;
};

/* ── ear: one link is enough --------------------------------------------
 *
 * A single hinged flap, drawn already hanging in its own local frame so
 * `rotate` alone both sets its rest lean and carries its swing -- the same
 * "one link, one transform" shape as a tail segment, just filled instead of
 * stroked because a floppy ear reads as a flat shape, not a rod. The path is
 * authored at `EAR_REF_LEN`, so `DOG.earLen` is a real knob, not a decoration.
 */
const EAR_REF_LEN = 31;
const Ear = ({hinge, angleDeg, fill}) => (
  <g
    transform={`translate(${hinge[0].toFixed(1)} ${hinge[1].toFixed(1)}) rotate(${angleDeg.toFixed(1)}) scale(${(DOG.earLen / EAR_REF_LEN).toFixed(3)})`}
  >
    <path d="M-9 -2 C-17 6,-17 21,-7 29 C1 35,11 28,10 15 C9 6,2 -5,-9 -2 Z" fill={fill} />
  </g>
);

/** Skull and muzzle as two fused ellipses -- the flat-fill equivalent of the
 *  two-sphere heads the reference course draws a dog's head as. */
const Head = ({cx, cy, r, fill, noseFill}) => (
  <g>
    <ellipse cx={cx} cy={cy} rx={r} ry={r * 0.92} fill={fill} />
    <ellipse cx={cx + r * 0.86} cy={cy + r * 0.32} rx={r * 0.62} ry={r * 0.42} fill={fill} />
    <circle cx={cx + r * 1.42} cy={cy + r * 0.42} r={r * 0.16} fill={noseFill} />
    <circle cx={cx + r * 0.3} cy={cy - r * 0.26} r={r * 0.1} fill={noseFill} />
  </g>
);

/* ── the character --------------------------------------------------------- */

/**
 * A dog, posed by a solver frame.
 *
 * @param m      one frame from `solveLocomotion` -- the only source of
 *               position, facing, phase, speed and lean. Nothing here reads
 *               the clock directly except `m.t`, and only for the idle tail
 *               and the breathing drift, both of which are meant to run
 *               whether or not the body is going anywhere.
 * @param look   `{body, ear, nose, collar}`, all optional.
 */
export const Dog = ({m, look = {}, scale = 1, shadow = true}) => {
  const bodyFill = look.body ?? '#eecfa4';
  const earFill = look.ear ?? '#a97a4c';
  const noseFill = look.nose ?? '#2b2b40';
  const collarFill = look.collar ?? '#c8553d';

  const moving = m.moving;
  const mix = m.gaitMix ?? (m.gait === 'run' ? 1 : 0);
  const g = dogGaitAt(mix);
  const stride = strideAt(mix, DOG_STRIDE.trot, DOG_STRIDE.bound);

  const offsets = legOffsets(mix);
  const phaseOf = (o) => (((m.phase + o) % 1) + 1) % 1;
  const plan = (o) => (moving ? footOffset(phaseOf(o), stride, g) : {x: 0, y: 0, planted: true});

  const flPlan = plan(offsets.FL);
  const frPlan = plan(offsets.FR);
  const blPlan = plan(offsets.BL);
  const brPlan = plan(offsets.BR);

  // Each axle drops independently -- a trot's diagonal pairing means the
  // front and back feet are rarely at the same excursion at the same
  // instant, so a single shared pelvis-sink (as a biped has) would either
  // overreach one axle or slacken the other.
  const loadOf = (p) => (p.planted ? Math.abs(p.x) : 0);
  const frontSink = moving ? pelvisSink(Math.max(loadOf(flPlan), loadOf(frPlan))) : 0;
  const rearSink = moving ? pelvisSink(Math.max(loadOf(blPlan), loadOf(brPlan))) : 0;

  const breathe = moving ? 0 : Math.sin(m.t * 0.62 * TAU * 0.34);
  const frontHY = PELVIS_Y + (moving ? frontSink : breathe * 1.4);
  const rearHY = PELVIS_Y + (moving ? rearSink : breathe * 1.4);

  const flLeg = moving
    ? buildLeg(DOG.shoulderX - HIP_DX, frontHY, flPlan)
    : standingLeg(DOG.shoulderX - HIP_DX, -1, breathe);
  const frLeg = moving
    ? buildLeg(DOG.shoulderX + HIP_DX, frontHY, frPlan)
    : standingLeg(DOG.shoulderX + HIP_DX, 1, breathe);
  const blLeg = moving
    ? buildLeg(DOG.hipX - HIP_DX, rearHY, blPlan)
    : standingLeg(DOG.hipX - HIP_DX, -1, breathe);
  const brLeg = moving
    ? buildLeg(DOG.hipX + HIP_DX, rearHY, brPlan)
    : standingLeg(DOG.hipX + HIP_DX, 1, breathe);

  /**
   * Vertical bob and squash share one "feed" phase: `m.phase` scaled so a
   * full stride reads as TWO bounces at mix=0 (a trot's double footfall,
   * same reasoning as a biped's) collapsing to ONE at mix=1 (a bound's
   * single gather-and-extend). Blending the bounce COUNT with `mix`, rather
   * than switching it, is what keeps the crossover seamless.
   */
  const feed = (p) => p * (1 - mix * 0.5);
  const bounceAt = (p) => -bobShape(((p % 1) + 1) % 1);
  const bodyBobUnit = moving ? bounceAt(feed(m.phase)) : 0;
  const bobAmp = lerp(3, 13, mix);
  const gaitSink = moving ? (frontSink + rearSink) / 2 : breathe * 1.4;
  const bodyY = bodyBobUnit * bobAmp + gaitSink;

  // Volume-preserving squash/stretch: compresses on the gather, stretches on
  // the extend. `squashAmt` grows with `mix` because a trot's weight
  // transfer is subtle and a bound's is the whole point of the gait.
  const squashAmt = lerp(0.02, 0.15, mix);
  const sy = moving ? springScale(feed(m.phase), squashAmt) : 1;
  const sx = 1 / sy;

  // The spine pitches toward whichever axle has sunk less -- a bound's big
  // sink difference reads as the rocking-horse motion of a real gallop; a
  // trot's tiny one barely shows, which is correct for that gait too.
  const pitch = moving ? (rearSink - frontSink) * 0.4 : 0;
  const lean = (m.lean ?? 0) + pitch;

  /**
   * Head lags the body, ear lags the head: one chain, three phases, the
   * accumulating 2-frames-per-link delay `chainPhases` exists for. The cycle
   * length has to come from the real pace -- 2 frames is a fifth of a
   * bound's cycle and a fifteenth of an idle trot's -- so it is derived from
   * `stride / speed` exactly as `Humaaans.jsx` derives its own head lag.
   */
  const cycleFrames = moving && m.speed > 0.01 ? stride / m.speed : 0;
  const [, headPhase, earPhase] = chainPhases(m.phase, 3, cycleFrames);
  const headBobUnit = moving ? bounceAt(feed(headPhase)) : 0;
  const headBobLag = (headBobUnit - bodyBobUnit) * bobAmp * 0.8;
  const earSwingDeg = (moving ? whipPose(earPhase).bend : 0) * 22;

  /**
   * The tail never freezes. While the body travels it rides the same gait
   * cycle as the head/ear chain; parked, it drops onto a slow clock of its
   * own so a standing dog still reads as alive. `IDLE_CYCLE` is expressed in
   * frames at the project's 30fps convention purely so the 2-frames-per-link
   * delay stays the same NUMBER of frames whether the driving clock is the
   * gait or the idle wag -- the ratio is what matters, not the wall-clock
   * rate.
   */
  const IDLE_PERIOD_SEC = 1.7;
  const IDLE_CYCLE_FRAMES = IDLE_PERIOD_SEC * 30;
  const idlePhase = (m.t / IDLE_PERIOD_SEC) % 1;
  const tailBase = moving ? m.phase : idlePhase;
  const tailCycle = moving ? cycleFrames : IDLE_CYCLE_FRAMES;
  // Link 0 of `chainPhases` never lags -- that slot is the hip the tail
  // hangs from, same as the discarded first entry of the head/ear chain
  // above, so the first DRAWN segment already trails the hip by one link.
  const [, ...tailPhases] = chainPhases(tailBase, DOG.tailLinks + 1, tailCycle, 1.2);

  // How far off the ground the LOWEST paw currently is -- 0 while any paw is
  // planted, growing only through a bound's real flight phase. Ties the
  // contact shadow to the same feet the legs are actually drawn from.
  const yLow = moving ? Math.max(flPlan.y, frPlan.y, blPlan.y, brPlan.y) : 0;
  const air = clamp(-yLow / 40, 0, 1);

  const tailAnchor = [DOG.hipX - 26, PELVIS_Y - 4];
  const neckFrom = [DOG.shoulderX + 6, PELVIS_Y - 32];
  const neckTo = [DOG.headX - DOG.headR * 0.6, DOG.headY + DOG.headR * 0.55];
  // A collar is a band around the neck, not a stripe along it: perpendicular
  // to the neck axis, close enough to the head end that the jaw drawn on
  // top of it (below) covers half the band -- the rest reads as visible
  // collar, the same "partially occluded" cue the ear hinge relies on too.
  const neckLen = Math.hypot(neckTo[0] - neckFrom[0], neckTo[1] - neckFrom[1]) || 1;
  const neckUx = (neckTo[0] - neckFrom[0]) / neckLen;
  const neckUy = (neckTo[1] - neckFrom[1]) / neckLen;
  const collarCx = lerp(neckFrom[0], neckTo[0], 0.88);
  const collarCy = lerp(neckFrom[1], neckTo[1], 0.88);
  const collarHalf = 15; // spans just under the neck's own 32-wide girth
  const collarA = [collarCx - neckUy * collarHalf, collarCy + neckUx * collarHalf];
  const collarB = [collarCx + neckUy * collarHalf, collarCy - neckUx * collarHalf];

  return (
    <g transform={`translate(${m.x.toFixed(2)} ${(m.y ?? 0).toFixed(2)}) scale(${scale})`}>
      {shadow && (
        <ellipse
          cx={0}
          cy={2}
          rx={(moving ? 92 : 100) * (1 - air * 0.4)}
          ry={14 * (1 - air * 0.3)}
          fill="#191847"
          opacity={0.16 * (1 - air * 0.55)}
        />
      )}
      <g transform={`scale(${m.facingScale.toFixed(3)} 1)`}>
        {/* Legs in ground space, outside the bob -- a paw that bobs with the
            body is a paw that is not standing on anything. Off-side pair
            drawn first, behind the near pair and the body both. */}
        <OffsideLeg {...flLeg} fill={bodyFill} />
        <OffsideLeg {...blLeg} fill={bodyFill} />
        <Leg {...frLeg} fill={bodyFill} />
        <Leg {...brLeg} fill={bodyFill} />

        <g transform={`translate(0 ${bodyY.toFixed(2)}) rotate(${lean.toFixed(2)} 0 ${PELVIS_Y})`}>
          <g transform={`translate(0 ${PELVIS_Y}) scale(${sx.toFixed(4)} ${sy.toFixed(4)}) translate(0 ${-PELVIS_Y})`}>
            <Tail anchor={tailAnchor} phases={tailPhases} fill={bodyFill} />
            <rect
              x={-DOG.bodyLen / 2}
              y={BODY_TOP}
              width={DOG.bodyLen}
              height={DOG.bodyH}
              rx={DOG.bodyH / 2}
              ry={DOG.bodyH / 2}
              fill={bodyFill}
            />
            <g transform={`translate(0 ${headBobLag.toFixed(2)})`}>
              <Stroke a={neckFrom} b={neckTo} fill={bodyFill} w={32} />
              <Stroke a={collarA} b={collarB} fill={collarFill} w={13} />
              <Head cx={DOG.headX} cy={DOG.headY} r={DOG.headR} fill={bodyFill} noseFill={noseFill} />
              <Ear
                hinge={[DOG.headX - DOG.headR * 0.55, DOG.headY - DOG.headR * 0.6]}
                angleDeg={-14 + earSwingDeg}
                fill={earFill}
              />
            </g>
          </g>
        </g>
      </g>
    </g>
  );
};
