import React from 'react';
import {Head} from './Peeps.jsx';
import {GAITS, gaitAt, strideAt, footOffset} from './locomotion.js';

/**
 * A character: an Open Peeps head on a rigged body.
 *
 * ── Why it is built this way ────────────────────────────────────────────────
 *
 * Open Peeps ships beautiful hand-drawn bodies, but they are *fixed poses* —
 * "Walking" is one drawing of someone mid-stride, not a cycle. You cannot
 * animate a walk out of it.
 *
 * The previous generation of this style solved that by drawing everything
 * procedurally, and paid for it in the faces: a character built from ellipses
 * has no expression, and an audience reads a face long before it reads a knee.
 *
 * So the split follows where the value is. The head — identity, expression,
 * the thing actually being watched — is real illustration, held stable across
 * every shot a character appears in. The body below the neck is a rig, because
 * the body's job is to move correctly, and correctness there is geometry
 * rather than draughtsmanship.
 *
 * Everything below is authored in one canonical space: **feet on y = 0, top of
 * head at y = -1000, facing +x**. Facing is applied once, by the caller, as a
 * mirror. Nothing in here knows which way the character is pointing, which is
 * precisely why nothing in here can point it the wrong way.
 */

const TAU = Math.PI * 2;
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const smooth = (u) => u * u * (3 - 2 * u);

/* ── proportions ─────────────────────────────────────────────────────────── */

/**
 * Roughly four and a third heads tall, which is where Open Peeps sits and
 * where stylised cartoon figures generally sit. Real people are seven and a
 * half; a figure drawn at that ratio next to these heads reads as a stilt
 * walker, which was the first thing this rig got wrong.
 */
export const H = 1000;
const HEAD_TOP = -1000;
const HEAD_H = 232;
const PEEPS_HAIR_H = 567;        // its height in Open Peeps units
const HEAD_SCALE = HEAD_H / PEEPS_HAIR_H;
const HEAD_W = 507 * HEAD_SCALE;

const NECK_Y = -778;
const SHOULDER_Y = -700;
const TORSO_TOP = -752;
const PELVIS_Y = -430;
const KNEE_Y = -225;
const ANKLE_Y = -38;

const THIGH = 210;
const SHIN = 194;
const UPPER_ARM = 172;
const FOREARM = 164;

const HIP_DX = 44;
/** Shoulders sit ON the torso edge, so an arm hangs outside the silhouette
 *  rather than being drawn across the chest — which is what it was doing. */
const SHOULDER_DX = 100;
const TORSO_HALF = 100;
const WAIST_HALF = 92;

/** Ink weights. Open Peeps draws a heavy, confident line; thin strokes here
 *  instantly read as a different illustrator. */
const LIMB_INK = 84;
const LIMB_FILL = 54;
const ARM_INK = 64;
const ARM_FILL = 40;
const TORSO_INK = 26;

/* ── the pelvis is not a fixed height ─────────────────────────────────────
 *
 * The first version of this rig held the pelvis at a constant height and let
 * the IK sort the legs out. It could not: the legs are exactly as long as the
 * hip is high, so the moment a foot moved forward at all the target was
 * further away than the leg could reach, the solver clamped it, and the clamp
 * swung both legs out toward the horizon. The character walked like a compass.
 *
 * Real walking solves this the other way round. A leg is a fixed length, so
 * standing on one with the feet apart REQUIRES the hips to drop — that dip is
 * where the bob in a walk cycle actually comes from. It is not decoration
 * added on top of the walk; it is a consequence of the leg length.
 *
 * So the sink is computed, not chosen, and the stride is derived from how much
 * sink is acceptable. The two cannot drift apart because they are the same
 * triangle read in opposite directions.
 */
const HIP_H = ANKLE_Y - PELVIS_Y;          // hip height above the ankle
const LEG = THIGH + SHIN;
const LEG_EFF = LEG * 0.985;               // never fully lock the knee

/** Vertical drop needed for a leg of fixed length to reach a foot `ax` away. */
const pelvisSink = (ax) => {
  const reach = Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - ax * ax));
  return Math.max(0, HIP_H - reach);
};

/** How much dip each gait is allowed to spend. This is what sets the stride. */
const SINK = {walk: 38, run: 76};

/**
 * Two-bone IK. `bend` is which side the middle joint breaks toward: -1 puts a
 * knee in front of the leg (facing +x), +1 puts an elbow behind the arm.
 */
const ik = (hx, hy, fx, fy, l1, l2, bend) => {
  let dx = fx - hx;
  let dy = fy - hy;
  let d = Math.hypot(dx, dy);
  const reach = (l1 + l2) * 0.995;
  if (d > reach) {
    // Do not let the limb snap straight and stretch: pull the target in. A
    // hyper-extended knee is more visible than a slightly short step.
    const k = reach / d;
    dx *= k;
    dy *= k;
    d = reach;
    fx = hx + dx;
    fy = hy + dy;
  }
  if (d < 1e-6) return {jx: hx, jy: hy + l1, fx, fy};
  const a = Math.acos(clamp((d * d + l1 * l1 - l2 * l2) / (2 * d * l1), -1, 1));
  const base = Math.atan2(dy, dx);
  const ang = base + bend * a;
  return {jx: hx + Math.cos(ang) * l1, jy: hy + Math.sin(ang) * l1, fx, fy};
};

/* ── drawing ─────────────────────────────────────────────────────────────── */

/**
 * A limb, drawn as ink underneath and colour on top.
 *
 * Two stacked strokes rather than a stroked outline: it gives a true even ink
 * border around a rounded joint without the mitre artefacts a stroked polygon
 * produces at the knee, and it is how the reference art reads.
 */
const Limb = ({pts, ink, fill, w, wi}) => {
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  return (
    <g>
      <path d={d} fill="none" stroke={ink} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={fill} strokeWidth={wi} strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

/** A shoe: a rounded wedge that reads as a foot from the side at any size.
 *  Drawn from the ankle down, so the sole lands on the ground plane rather
 *  than near it. */
const Shoe = ({x, y, ink, fill, heel}) => (
  <g transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(-heel * 14).toFixed(1)})`}>
    <path
      d="M-34 -10 C-34 -32 38 -34 50 -10 C62 12 80 22 80 32 C80 42 66 45 42 45 L-28 45 C-38 45 -40 28 -38 12 Z"
      fill={ink}
    />
    <path
      d="M-25 -6 C-25 -23 33 -25 43 -6 C54 12 68 20 68 28 C68 35 57 37 38 37 L-21 37 C-29 37 -30 24 -28 11 Z"
      fill={fill}
    />
  </g>
);

const StandingLegs = ({palette, breathe}) => {
  const drop = breathe * 3;
  const leg = (hx, splay) => {
    const hip = [hx, PELVIS_Y + drop];
    const knee = [hx + splay * 4, KNEE_Y + drop * 0.4];
    const ankle = [hx + splay * 9, ANKLE_Y];
    return [hip, knee, ankle];
  };
  const far = leg(-HIP_DX, -1);
  const near = leg(HIP_DX, 1);
  return (
    <g>
      <g opacity="0.88">
        <Limb pts={far} ink={palette.ink} fill={palette.trousers} w={LIMB_INK} wi={LIMB_FILL} />
        <Shoe x={far[2][0] - 10} y={ANKLE_Y} ink={palette.ink} fill={palette.shoes} heel={0} />
      </g>
      <Limb pts={near} ink={palette.ink} fill={palette.trousers} w={LIMB_INK} wi={LIMB_FILL} />
      <Shoe x={near[2][0] - 10} y={ANKLE_Y} ink={palette.ink} fill={palette.shoes} heel={0} />
    </g>
  );
};

/**
 * Plans both legs for a phase, and reports the pelvis height they demand.
 *
 * The caller must apply `sink` to the whole upper body, because the feet are
 * in ground space and everything above the hips is what moves.
 */
export const planLegs = (phase, stride, g) => {
  const fNear = footOffset(phase, stride, g);
  const fFar = footOffset((phase + 0.5) % 1, stride, g);
  // Only a planted foot can force the hips down; a lifted one is free.
  const load = Math.max(fNear.planted ? Math.abs(fNear.x) : 0, fFar.planted ? Math.abs(fFar.x) : 0);
  return {sink: pelvisSink(load), near: fNear, far: fFar};
};

const WalkingLegs = ({phase, stride, g, palette, sink}) => {
  const hy = PELVIS_Y + sink;
  const build = (f, dx) => {
    const {jx, jy, fx, fy} = ik(dx, hy, dx + f.x, ANKLE_Y + f.y, THIGH, SHIN, -1);
    return {pts: [[dx, hy], [jx, jy], [fx, fy]], fx, fy, planted: f.planted};
  };
  const plan = planLegs(phase, stride, g);
  // The far leg is the one half a cycle ahead; drawing it first and slightly
  // knocked back in tone is the only depth cue available in flat ink.
  const far = build(plan.far, -HIP_DX);
  const near = build(plan.near, HIP_DX);
  const heelOf = (l) => (l.planted ? 0 : g.heel);
  return (
    <g>
      <g opacity="0.88">
        <Limb pts={far.pts} ink={palette.ink} fill={palette.trousers} w={LIMB_INK} wi={LIMB_FILL} />
        <Shoe x={far.fx - 10} y={far.fy} ink={palette.ink} fill={palette.shoes} heel={heelOf(far)} />
      </g>
      <Limb pts={near.pts} ink={palette.ink} fill={palette.trousers} w={LIMB_INK} wi={LIMB_FILL} />
      <Shoe x={near.fx - 10} y={near.fy} ink={palette.ink} fill={palette.shoes} heel={heelOf(near)} />
    </g>
  );
};

/**
 * One arm, from a shoulder angle.
 *
 * Sign convention, which this got wrong on the first pass and which put both
 * arms inside the torso: in a y-down space, `PI/2` points straight down, and
 * *subtracting* swings the limb toward +x, which is forward for a character
 * drawn facing +x. The elbow then only ever flexes — `flex` is clamped
 * non-negative, because an arm that hyperextends at the back of a swing is
 * the single most obviously wrong thing a walk cycle can do.
 */
const Arm = ({dx, swing, palette, carry}) => {
  const sx = dx;
  const sy = SHOULDER_Y;
  const a1 = Math.PI / 2 - swing;
  const ex = sx + Math.cos(a1) * UPPER_ARM;
  const ey = sy + Math.sin(a1) * UPPER_ARM;
  const flex = 0.14 + 0.42 * Math.max(0, swing);
  const a2 = a1 - flex;
  const wx = ex + Math.cos(a2) * FOREARM;
  const wy = ey + Math.sin(a2) * FOREARM;
  return (
    <g>
      <Limb pts={[[sx, sy], [ex, ey], [wx, wy]]} ink={palette.ink} fill={palette.sleeve} w={ARM_INK} wi={ARM_FILL} />
      <circle cx={wx} cy={wy} r={ARM_INK / 2 + 2} fill={palette.ink} />
      <circle cx={wx} cy={wy} r={ARM_FILL / 2 + 5} fill={palette.skin} />
      {carry && <g transform={`translate(${wx.toFixed(1)} ${wy.toFixed(1)})`}>{carry}</g>}
    </g>
  );
};

/**
 * The torso, as one closed path stroked in ink.
 *
 * Stroking beats drawing a second, larger copy underneath: the outline stays
 * an even width all the way round the shoulder, which the copy-underneath
 * trick cannot do on a curve.
 */
const Torso = ({palette}) => {
  const d =
    `M${-TORSO_HALF} ${SHOULDER_Y}` +
    ` C${-TORSO_HALF + 4} ${TORSO_TOP + 16} ${-46} ${TORSO_TOP} 0 ${TORSO_TOP}` +
    ` C${46} ${TORSO_TOP} ${TORSO_HALF - 4} ${TORSO_TOP + 16} ${TORSO_HALF} ${SHOULDER_Y}` +
    ` C${TORSO_HALF + 10} ${SHOULDER_Y + 96} ${WAIST_HALF + 10} ${PELVIS_Y - 96} ${WAIST_HALF} ${PELVIS_Y + 14}` +
    ` L${-WAIST_HALF} ${PELVIS_Y + 14}` +
    ` C${-WAIST_HALF - 10} ${PELVIS_Y - 96} ${-TORSO_HALF - 10} ${SHOULDER_Y + 96} ${-TORSO_HALF} ${SHOULDER_Y}` +
    ` Z`;
  return (
    <path
      d={d}
      fill={palette.shirt}
      stroke={palette.ink}
      strokeWidth={TORSO_INK}
      strokeLinejoin="round"
    />
  );
};

/* ── the character ───────────────────────────────────────────────────────── */

/**
 * @param m      one frame from `solveLocomotion` — the ONLY source of facing,
 *               phase, bob and lean. Nothing may be passed alongside it that
 *               contradicts it.
 * @param look   `{palette, hair, face, beard, accessory, layout}`
 *
 * Stride is deliberately NOT a prop. It used to be, and every caller had to
 * convert scene units to character units by dividing by its own scale — which
 * is precisely the kind of bookkeeping that silently goes wrong the moment two
 * characters are drawn at different sizes. The rig owns its own stride now;
 * callers ask `strideUnits(scale, gait)` for the matching scene distance.
 */
export const Character = ({
  m, look, scale = 1, sitting = false, carry = null, shadow = true,
}) => {
  const {palette, hair, face, beard, accessory, layout} = look;
  // The blended gait, resolved from the same mix the solver used. Reading the
  // discrete label instead would snap the stride mid-transition and slide the
  // planted foot — which is exactly the fault the solver goes to some trouble
  // to avoid, undone at the last step.
  const mix = m.gaitMix ?? (m.gait === 'run' ? 1 : 0);
  const g = gaitAt(mix);
  const stride = strideAt(mix, STRIDE_UNITS.walk, STRIDE_UNITS.run);

  // A held pose is not a still frame: the chest rises about every three
  // seconds even when nothing else happens.
  const breathe = Math.sin(m.t * 0.62 * TAU * 0.34);
  const moving = m.moving && !sitting;

  /**
   * Arms oppose legs. The extreme of the arm swing belongs at the contact
   * poses — phase 0 and 0.5, where the feet are furthest apart — not between
   * them, which is where a plain `sin(phase)` puts it. Cosine, negated: at
   * phase 0 the near foot is forward, so the near arm is back.
   */
  const swingA = moving ? -Math.cos(m.phase * TAU) * g.armSwing : breathe * 0.05 + 0.1;
  const swingB = moving ? Math.cos(m.phase * TAU) * g.armSwing : -breathe * 0.05 - 0.1;

  // The bob is the pelvis sink the legs demand, not a sine wave laid on top of
  // them. `m.bob` remains as the solver's small breathing/settle contribution.
  const gaitSink = moving ? planLegs(m.phase, stride, g).sink : 0;
  const bodyY = (sitting ? 0 : m.bob * 0.3) + gaitSink;
  const lean = sitting ? 0 : m.lean + (moving ? g.bodyLean * 0.35 : 0);

  const headScale = HEAD_SCALE;
  const headX = -HEAD_W / 2;

  return (
    <g transform={`translate(${m.x.toFixed(2)} ${(m.y ?? 0).toFixed(2)}) scale(${scale})`}>
      {shadow && (
        <ellipse
          cx={0}
          cy={6}
          rx={moving ? 150 : 170}
          ry={26}
          fill={palette.ink}
          opacity={0.18}
        />
      )}
      {/* Facing is a mirror of the whole body, applied here and nowhere else.
          `facingScale` passes through a narrow waist during a turn, which is
          what draws the pivot. */}
      <g transform={`scale(${m.facingScale.toFixed(3)} 1)`}>
        {/* Legs live in GROUND space, outside the bob. A foot that bobs with
            the body is a foot that is not standing on anything. */}
        {moving ? (
          <WalkingLegs phase={m.phase} stride={stride} g={g}
                       palette={palette} sink={bodyY} />
        ) : (
          <StandingLegs palette={palette} breathe={breathe} />
        )}

        <g transform={`translate(0 ${bodyY.toFixed(2)}) rotate(${lean.toFixed(2)} 0 ${PELVIS_Y})`}>
          {/* back arm first: the torso has to be drawn between the two */}
          <g opacity="0.88">
            <Arm dx={-SHOULDER_DX} swing={swingB} palette={palette} />
          </g>

          <Torso palette={palette} />

          {/* neck, then the head sitting on it. Short: a long neck is the
              fastest way to make a stylised figure look plucked. */}
          <path
            d={`M0 ${NECK_Y} L0 ${TORSO_TOP + 20}`}
            stroke={palette.ink}
            strokeWidth={72}
            strokeLinecap="round"
          />
          <path
            d={`M0 ${NECK_Y} L0 ${TORSO_TOP + 20}`}
            stroke={palette.skin}
            strokeWidth={48}
            strokeLinecap="round"
          />

          <Arm dx={SHOULDER_DX} swing={swingA} palette={palette} carry={carry} />

          <g transform={`translate(${headX.toFixed(1)} ${HEAD_TOP}) scale(${headScale.toFixed(5)})`}>
            <Head hair={hair} face={face} beard={beard} accessory={accessory}
                  layout={layout} palette={palette} />
          </g>
        </g>
      </g>
    </g>
  );
};

/**
 * Stride, derived from the sink the legs are allowed to spend.
 *
 * This began as a fraction of standing height — the anthropometric figure,
 * 0.41 per step — and it produced a character whose legs shot out sideways.
 * The reason was not the fraction but the assumption underneath it: that the
 * pelvis stays at one height. It cannot. A leg is a fixed length, so spreading
 * the feet pulls the hips down, and how far you are willing to let them drop
 * is exactly what limits how far apart the feet may be.
 *
 * So the stride is read off that same triangle, in the opposite direction:
 * pick an acceptable dip, and it tells you the step. Change a bone length or
 * the dip and the stride follows, which is the only way the walk and the
 * distance travelled can be guaranteed never to disagree.
 */
const strideChar = (gait = 'walk') => {
  const g = GAITS[gait] ?? GAITS.walk;
  const reach = HIP_H - (SINK[gait] ?? SINK.walk);
  const A = Math.sqrt(Math.max(0, LEG_EFF * LEG_EFF - reach * reach));
  return (2 * A) / g.duty;
};

/** Stride in CHARACTER units — what the rig itself walks. */
export const STRIDE_UNITS = {walk: strideChar('walk'), run: strideChar('run')};

/**
 * Stride in SCENE units for a character drawn at `scale`. This is what the
 * locomotion solver needs, because the solver works in scene space.
 */
export const strideUnits = (scale = 1, gait = 'walk') =>
  (STRIDE_UNITS[gait] ?? STRIDE_UNITS.walk) * scale;
