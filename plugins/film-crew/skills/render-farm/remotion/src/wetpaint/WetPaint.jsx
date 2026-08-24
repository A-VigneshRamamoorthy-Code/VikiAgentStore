import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {P} from './palette.js';
import {PencilDefs, Paper, step} from './Paper.jsx';
import {ParkSet, Bench, Sign, GROUND, BENCH_X, cameraTransform, CAM} from './Set.jsx';
import {Figure, Dog, CapHat, BowlerHat, BunHair, Beanie, PaintTin, Newspaper} from './Figures.jsx';
import {Cloud, Lettering} from './Type.jsx';

// "Wet Paint" -- an original short in the manner of the reference, not a
// remake of it. The reference is a locked wide shot of a street; this is a
// locked wide shot of a park, with its own cast, its own gag and its own
// ending. What is deliberately shared is only what was *measured*: the cream
// paper, the near-monochrome palette, the 24 fps stepped drawing, the single
// saturated object, and the refusal to cut.

// Seats are world coordinates on the bench, which starts at BENCH_X.
const SEAT_X = BENCH_X + 96;
const STRIDE = 96;          // world units per full stride, tuned to the legs

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const ease = (t) => t * t * (3 - 2 * t);

/**
 * One visitor's whole routine: walk on, sit, dwell, stand, leave striped.
 *
 * Written as a function of a single local frame rather than as a sequence of
 * states, because the thing that has to be right is the *handover* -- the
 * moment the walk stops and the sit starts is where a rig like this normally
 * pops, and expressing both as one continuous function of time is what stops
 * that happening.
 *
 * `layer` is what makes sitting read. A seated figure has to be drawn between
 * the bench's backrest and its seat, so each visitor is mounted twice and
 * renders in whichever pass matches its current state. Cheaper alternatives
 * were tried and all of them put the figure in front of the whole bench,
 * where a sit is indistinguishable from a stand.
 */
const Visitor = ({
  local, from = 'left', hat, torso, carry = null, dwell = 84,
  withDog = false, scale = 1, walkOut = 62, seat = SEAT_X, layer = 'front',
}) => {
  const IN = 58;
  const SIT = 14;
  const STAND = 14;
  const tSit = IN + SIT;
  const tStand = tSit + dwell;
  const tOut = tStand + STAND;
  const total = tOut + walkOut;
  if (local < 0 || local > total) return null;

  const entry = from === 'left' ? 300 : 1520;
  const exit = from === 'left' ? 1520 : 300;

  let x, phase, sitting = false, stripes = 0, headTilt = 0;

  if (local < IN) {
    const u = ease(local / IN);
    x = entry + (seat - entry) * u;
    phase = (Math.abs(x - entry) / STRIDE) % 1;
  } else if (local < tSit) {
    // Settling onto the seat. The figure is already standing at the bench, so
    // only the hips move -- handled inside the rig by `sitting`.
    x = seat;
    phase = 0;
    sitting = (local - IN) / SIT > 0.45;
  } else if (local < tStand) {
    x = seat;
    phase = 0;
    sitting = true;
    // A small idle: the head turns once, late, so the hold does not read as a
    // freeze. Drawn animation holds still, but it does not hold *dead*.
    const u = (local - tSit) / dwell;
    headTilt = Math.sin(u * Math.PI * 2) * 4;
  } else if (local < tOut) {
    x = seat;
    phase = 0;
    sitting = (local - tStand) / STAND < 0.5;
    stripes = clamp01((local - tStand) / STAND - 0.4);
  } else {
    const u = ease((local - tOut) / walkOut);
    x = seat + (exit - seat) * u;
    phase = (Math.abs(x - seat) / STRIDE) % 1;
    stripes = 1;
  }

  if ((layer === 'seated') !== sitting) return null;

  /*
   * Facing is DERIVED FROM TRAVEL. It is not a property of the story.
   *
   * This line used to read:
   *
   *     const flip = local > tOut ? !facing : facing;   // "leaving means
   *                                                     //  facing the other way"
   *
   * and it is the reason the finished film had somebody moonwalking out of
   * shot. Leaving does not mean facing the other way. A visitor who comes on
   * from the left walks rightwards to the bench (300 → seat) and then keeps
   * walking rightwards to get off (seat → 1520): same direction, both times.
   * Flipping them on the way out drew a figure gliding backwards.
   *
   * The mistake was flipping a boolean that described the intention ("they're
   * leaving") instead of measuring the only thing that decides which way a
   * drawing should point — the sign of the distance it is covering.
   */
  const travel = local > tOut ? exit - seat : seat - entry;
  const facingRight = travel >= 0;

  return (
    <g>
      <Figure x={x} y={GROUND} scale={scale} flip={!facingRight} phase={phase}
              sitting={sitting} walking={local < IN || local > tOut}
              hat={hat} torso={torso} carry={sitting ? carry : null}
              stripes={stripes} headTilt={headTilt} />
      {withDog && (
        <Dog x={x + (facingRight ? 92 : -92)} y={GROUND} scale={0.82}
             phase={phase} flip={!facingRight} />
      )}
    </g>
  );
};

/** The painter's own routine, which bookends the film. */
const Painter = ({local, mode}) => {
  if (mode === 'paint') {
    // Kneeling at the bench, arm working back and forth. The stroke rate is
    // deliberately not the walk rate -- nothing in a drawing should share a
    // frequency with anything else, or the whole frame starts to pulse.
    const stroke = (Math.sin(local / 7) + 1) / 2;
    const done = clamp01((local - 150) / 40);
    const x = 726 + stroke * 26;
    return (
      <Figure x={done > 0 ? 726 + done * 18 : x} y={GROUND} scale={0.98}
              flip={false} phase={0} hat={CapHat} torso={P.wash}
              reach={done > 0 ? 0 : 0.4 + stroke * 0.6} carry={PaintTin}
              lean={done > 0 ? 0 : 6} />
    );
  }
  return null;
};

/**
 * The painter comes back, admires the work, reads nothing, and sits in it.
 * Layered for the same reason the visitors are.
 */
const PainterReturn = ({local, layer = 'front'}) => {
  const IN = 64, LOOK = 46, SETTLE = 14, PROUD = 74, UP = 16;
  const tSit = IN + LOOK, tUp = tSit + SETTLE + PROUD, tSee = tUp + UP;
  if (local < 0) return null;

  let x = 1520, phase = 0, sitting = false, stripes = 0, tilt = 0;
  if (local < IN) {
    const u = ease(local / IN);
    x = 1520 + (SEAT_X + 170 - 1520) * u;
    phase = (Math.abs(x - 1520) / STRIDE) % 1;
  } else if (local < tSit) {
    // Standing back to admire it: a long, still hold. The reference trusts
    // stillness completely, and it is the hardest thing to leave in.
    x = SEAT_X + 170;
    tilt = Math.sin((local - IN) / 14) * 3;
  } else if (local < tUp) {
    x = SEAT_X;
    sitting = local >= tSit + 6;
    tilt = Math.sin((local - tSit) / 18) * 2.5;
  } else {
    x = SEAT_X;
    sitting = local < tUp + 8;
    stripes = clamp01((local - tUp) / UP - 0.35);
    // The double take: he looks at the bench, then at his own sign.
    tilt = local > tSee ? -16 : Math.sin((local - tUp) / 6) * 5;
  }
  if ((layer === 'seated') !== sitting) return null;

  return (
    <Figure x={x} y={GROUND} scale={0.98} flip phase={phase}
            sitting={sitting} walking={local < IN} hat={CapHat} torso={P.wash}
            stripes={stripes} headTilt={tilt} />
  );
};

export const WetPaint = () => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();

  // Everything samples time here. Drawn animation is held on 2s; sampling the
  // clock anywhere else in the tree would put one element on 24s and quietly
  // break the medium.
  const f = step(frame, 2);
  const seed = (f / 2) % 97;

  // --- beats, in frames at 24 fps -------------------------------------
  const B = {
    titleIn: 0, titleOut: 104, sceneIn: 96,
    paint: 132, paintEnd: 316,
    signSet: 316, painterOut: 372,
    v1: 432, v2: 664, v3: 896,
    back: 1128, cardIn: 1408,
  };

  const titleOpacity = interpolate(f, [0, 14, B.titleOut - 18, B.titleOut], [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const sceneOpacity = interpolate(f, [B.sceneIn, B.sceneIn + 26], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cardOpacity = interpolate(f, [B.cardIn, B.cardIn + 20], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const sceneOut = interpolate(f, [B.cardIn - 10, B.cardIn + 16], [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // The bench fills with colour as it is painted, then simply stays wet. That
  // it never dries is the premise; the film is only a few minutes of an
  // afternoon.
  const wet = interpolate(f, [B.paint, B.paintEnd], [0.18, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const signUp = f > B.signSet;

  // Mounted twice, once per depth layer. Each performance renders in whichever
  // pass matches its current state and returns null in the other.
  const cast = (layer) => (
    <>
      {f >= B.paint && f < B.painterOut && layer === 'front' && (
        <Painter local={f - B.paint} mode="paint" />
      )}
      {f >= B.signSet && f < B.painterOut && layer === 'front' && (
        <Figure x={interpolate(f, [B.signSet + 30, B.painterOut], [1190, 1520],
          {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
          y={GROUND} scale={0.98} flip walking
          phase={((f - B.signSet) / STRIDE * 8) % 1}
          hat={CapHat} torso={P.wash} carry={PaintTin} />
      )}
      <Visitor local={f - B.v1} layer={layer} from="left" hat={BowlerHat}
               torso={P.washDeep} carry={Newspaper} dwell={96} seat={866} />
      <Visitor local={f - B.v2} layer={layer} from="right" hat={BunHair}
               torso={P.wash} dwell={84} withDog scale={0.96} seat={950} />
      <Visitor local={f - B.v3} layer={layer} from="left" hat={Beanie}
               torso={P.paperDeep} dwell={72} scale={1.02} seat={908} />
      {f < B.cardIn + 40 && <PainterReturn local={f - B.back} layer={layer} />}
    </>
  );

  return (
    <AbsoluteFill style={{backgroundColor: P.paper}}>
      <svg width={width} height={height} viewBox="0 0 1920 1080"
           style={{width: '100%', height: '100%'}}>
        <PencilDefs seed={seed} cam={CAM.scale} />
        <Paper width={1920} height={1080} />

        {/* Clouds drift across every part of the film, including the cards.
            They are the only thing that moves during a hold, and they are what
            stops a held frame from looking like a stalled render. */}
        <g opacity={0.9}>
          <Cloud x={((f * 0.34) % 2400) - 380} y={112} s={1.55} opacity={0.7} />
          <Cloud x={((f * 0.22 + 900) % 2400) - 380} y={196} s={1.15} opacity={0.5} />
          <Cloud x={((f * 0.44 + 1700) % 2400) - 380} y={62} s={1.3} opacity={0.45} />
        </g>

        <g opacity={sceneOpacity * sceneOut} transform={cameraTransform}>
          <ParkSet />

          {/* The depth sandwich: backrest, then whoever is sitting, then the
              seat in front of their hips. Everyone still on their feet is
              drawn after the lot, in front of the bench. */}
          <Bench wet={wet} part="back" />
          {cast('seated')}
          <Bench wet={wet} part="seat" />

          {signUp && <Sign />}
          {cast('front')}
        </g>

        {/* Title and end card share the paper with the clouds, so the film
            opens and closes on the same sheet it is drawn on. */}
        {f < B.titleOut && (
          <g opacity={titleOpacity}>
            <Lettering text="Wet Paint" x={960} y={560} size={116} />
          </g>
        )}
        {f >= B.cardIn && (
          <g opacity={cardOpacity}>
            <Lettering text="Some signs are for other people." x={960} y={560} size={62} />
          </g>
        )}
      </svg>
    </AbsoluteFill>
  );
};
