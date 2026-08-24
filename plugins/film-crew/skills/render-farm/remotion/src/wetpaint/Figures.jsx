import React from 'react';
import {P} from './palette.js';

// One rig, five performances. The reference's cast are flat, round-headed and
// drawn with a handful of strokes each -- there is no anatomy to get wrong,
// which is what lets a scene hold six of them without the drawing collapsing.
//
// Everything is authored around a standing figure 200 units tall with its
// origin between the feet, so a caller only ever supplies a ground position
// and a scale.

const lerp = (a, b, t) => a + (b - a) * t;

/**
 * A walking figure.
 *
 * `phase` runs 0..1 through one full stride. The legs are two-segment and
 * driven off the same phase in antiphase, the arms counter-swing, and the body
 * takes a double bob per stride -- one per footfall -- which is the part that
 * sells weight. Without the bob a walk reads as a paper cut-out sliding.
 */
// Hip height when standing. Sitting *lowers* the hips onto the bench seat --
// the seat is 54 units off the floor and a standing hip is 86, so the figure
// drops 32. An earlier pass had this as a lift, which stood everyone up on
// their toes over the bench instead of sitting them in it.
const HIP = -86;
export const SEAT_DROP = 28;
const TAU = Math.PI * 2;

/**
 * One leg, as a function of its own phase.
 *
 * Foot contact is at p=0.25 (forward) and p=0.75 (back); in between it drags
 * along the ground, and from 0.75 round to 0.25 it swings through the air with
 * a bent knee, peaking at p=0. The two legs run half a cycle apart.
 *
 * The previous version drove both legs off `sin` and `-sin`, which meant they
 * were exact mirrors -- so at the passing position both went dead vertical at
 * the same x and the figure lost its legs entirely for a frame. Lifting the
 * swinging leg is what stops that, and it is also just what a walk does.
 */
const legPath = (p, hipX) => {
  const fx = 42 * Math.sin(p * TAU);
  const lift = Math.max(0, 26 * Math.sin(p * TAU + Math.PI / 2));
  const kx = hipX + fx * 0.45 + lift * 0.35;
  const ky = -44 + lift * 0.28;
  const ax = fx + hipX;
  const ay = -3 - lift;
  // The foot. Flat on the ground at contact, toe-down while it swings, which
  // is the difference between a walk and a pair of scissors opening.
  const toe = lift * 0.22;
  return `M${hipX} ${HIP} L${kx} ${ky} L${ax} ${ay} L${ax + 14} ${ay + toe}`;
};

const Legs = ({phase, sitting, walking = true}) => {
  if (sitting) {
    const hip = HIP + SEAT_DROP;
    // Front-on, deliberately.
    //
    // The bench is drawn face-on, so a figure sitting in profile has nowhere
    // to put its legs -- the thigh ends up lying along the seat slats at
    // exactly their height and disappears into them, and the result reads as
    // someone standing behind the bench. Turning the figure to face the
    // camera the moment it sits fixes it completely: the thighs foreshorten
    // to nothing, the shins drop in front of the seat, and the pose is
    // legible at a glance. The reference does the same thing.
    return (
      <g>
        <path d={`M-16 ${hip} L-18 -30 L-19 -3`} fill="none" stroke={P.line}
              strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <path d={`M16 ${hip} L18 -30 L19 -3`} fill="none" stroke={P.line}
              strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M-27 -3 L-13 -3" stroke={P.line} strokeWidth="7" strokeLinecap="round" />
        <path d="M13 -3 L27 -3" stroke={P.line} strokeWidth="7" strokeLinecap="round" />
      </g>
    );
  }
  if (!walking) {
    // Standing still is its own pose, not phase 0 of the walk. Sampling a
    // cycle at rest is how a held figure ends up standing to attention with
    // its feet welded together.
    return (
      <g>
        <path d={`M-7 ${HIP} L-13 -44 L-15 -3`} fill="none" stroke={P.lineSoft}
              strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <path d={`M7 ${HIP} L12 -44 L13 -3`} fill="none" stroke={P.line}
              strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M-23 -3 L-11 -3" stroke={P.lineSoft} strokeWidth="7" strokeLinecap="round" />
        <path d="M9 -3 L21 -3" stroke={P.line} strokeWidth="7" strokeLinecap="round" />
      </g>
    );
  }
  // Far leg lighter than the near one, so the two stay legible even where
  // they cross. It is the cheapest depth cue in flat 2D and the only one
  // available without shading.
  return (
    <g>
      <path d={legPath(phase + 0.5, -5)} fill="none" stroke={P.lineSoft} strokeWidth="7"
            strokeLinecap="round" strokeLinejoin="round" />
      <path d={legPath(phase, 5)} fill="none" stroke={P.line} strokeWidth="7"
            strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

/**
 * Arms, split into the two that go behind the body and the two that go in
 * front of it, because the torso has to be drawn between them.
 *
 * They are also *long*. An earlier version ended the hands at y -98, above
 * the torso hem at -86, so both arms lived entirely inside the body outline
 * and read as a pair of lines printed on the chest rather than as limbs. A
 * real arm reaches mid-thigh: from a shoulder at -150 that is about -66.
 */
const armSwing = (phase, sitting) => (sitting ? 0 : Math.sin(phase * TAU) * 26);

const ArmBack = ({phase, sitting, walking = true}) => {
  if (!sitting && !walking) {
    // At rest the arms hang at the sides of the body. Sampled from the walk
    // at phase 0 they hang dead centre instead, vanish behind the torso, and
    // the figure appears to have none.
    return (
      <path d="M-12 -148 L-22 -110 L-21 -70" fill="none" stroke={P.lineSoft}
            strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
    );
  }
  if (sitting) {
    return (
      <path d="M-8 -148 L-27 -112 L-23 -74" fill="none" stroke={P.lineSoft}
            strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
    );
  }
  const s = armSwing(phase, sitting);
  return (
    <path d={`M-3 -150 L${-3 + s * 0.5} -108 L${-3 + s} -66`} fill="none"
          stroke={P.lineSoft} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
  );
};

const ArmFront = ({phase, sitting, reach = 0, carry, walking = true}) => {
  if (!sitting && !walking && !reach) {
    return (
      <g>
        <path d="M14 -148 L24 -110 L23 -70" fill="none" stroke={P.line}
              strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        {carry && <g transform="translate(23 -68)">{carry}</g>}
      </g>
    );
  }
  if (sitting) {
    // Symmetric, because the figure has turned to face the camera. Anything
    // asymmetric here immediately re-reads as a profile and fights the legs.
    return (
      <g>
        <path d="M8 -148 L27 -112 L23 -74" fill="none" stroke={P.line}
              strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        {carry && <g transform="translate(0 -96) scale(0.92)">{carry}</g>}
      </g>
    );
  }
  const s = -armSwing(phase, sitting);
  const d = reach
    ? `M5 -150 L${lerp(30, 62, reach)} ${lerp(-114, -132, reach)} L${lerp(50, 98, reach)} ${lerp(-92, -126, reach)}`
    : `M5 -150 L${5 + s * 0.55} -108 L${5 + s} -66`;
  return (
    <g>
      <path d={d} fill="none" stroke={P.line} strokeWidth="6"
            strokeLinecap="round" strokeLinejoin="round" />
      {carry && !reach && <g transform={`translate(${5 + s} -64)`}>{carry}</g>}
    </g>
  );
};

/**
 * @param stripes  0..1 -- how much wet paint this figure is carrying on their
 *                 back. This is the gag, so it is a first-class property of
 *                 the rig rather than something painted on afterwards.
 */
export const Figure = ({
  x, y, scale = 1, flip = false, phase = 0, sitting = false, walking = false,
  torso = P.paperDeep, hat = null, reach = 0, carry = null,
  stripes = 0, lean = 0, headTilt = 0,
}) => {
  const bob = walking && !sitting ? Math.abs(Math.sin(phase * Math.PI * 2)) * -5 : 0;
  const drop = sitting ? SEAT_DROP : 0;
  return (
    <g filter="url(#pencil)"
       transform={`translate(${x} ${y}) scale(${(flip ? -scale : scale)} ${scale}) translate(0 ${bob}) rotate(${lean})`}>
      <ellipse cx="0" cy="4" rx="34" ry="8" fill={P.shade} opacity="0.34" />
      <Legs phase={phase} sitting={sitting} walking={walking} />

      {/* Everything above the hips moves as one piece, so sitting never needs
          a second set of torso, arm and head coordinates to drift out of sync
          with the standing set. */}
      <g transform={`translate(0 ${drop})`}>
        <ArmBack phase={phase} sitting={sitting} walking={walking} />
        <path d="M-26 -152 q26 -14 52 0 l6 66 q-32 12 -64 0 z"
              fill={torso} stroke={P.line} strokeWidth="2.6" strokeLinejoin="round" />

        {/* Wet paint, picked up from the slats. Two bands, because the bench
            back has two slats -- the stripes are evidence, so they have to
            agree with the thing that made them. */}
        {stripes > 0 && [0, 1].map((i) => (
          <rect key={i} x={-28 + i * 1.5} y={-140 + i * 22} width={56 - i * 3} height="12"
                rx="3" fill={P.paint} opacity={Math.min(1, stripes * 1.4)} />
        ))}

        <ArmFront phase={phase} sitting={sitting} walking={walking}
                  reach={reach} carry={carry} />

        <g transform={`rotate(${headTilt} 0 -176)`}>
          <circle cx="0" cy="-176" r="27" fill={P.paper}
                  stroke={P.line} strokeWidth="2.8" />
          <circle cx={sitting ? 10 : 11} cy="-180" r="3.1" fill={P.line} />
          <circle cx={sitting ? -10 : -8} cy="-180" r="3.1" fill={P.line} />
          {hat}
        </g>
      </g>
    </g>
  );
};

// ---- hats, which are the only way these figures tell each other apart ----

export const CapHat = (
  <g>
    <path d="M-28 -190 q28 -26 56 0 z" fill={P.washDeep}
          stroke={P.line} strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M-28 -190 q-16 2 -22 8 q22 6 22 -8" fill={P.washDeep}
          stroke={P.line} strokeWidth="2.2" />
  </g>
);

export const BowlerHat = (
  <g>
    <path d="M-22 -194 q22 -30 44 0 z" fill={P.wash}
          stroke={P.line} strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M-34 -193 q34 8 68 0" fill="none" stroke={P.line} strokeWidth="2.6" />
  </g>
);

export const BunHair = (
  <g>
    <circle cx="-20" cy="-192" r="12" fill={P.wash} stroke={P.line} strokeWidth="2.2" />
    <path d="M-27 -186 q27 -22 54 -2" fill="none" stroke={P.line} strokeWidth="2.4" />
  </g>
);

export const Beanie = (
  <g>
    <path d="M-27 -188 q27 -30 54 0 z" fill={P.shade}
          stroke={P.line} strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M-29 -188 q29 8 58 0" fill="none" stroke={P.line} strokeWidth="2.8" />
  </g>
);

// ---- props ----

export const PaintTin = (
  <g transform="scale(0.9)">
    <path d="M-11 0 h22 l-3 20 h-16 z" fill={P.paperDeep}
          stroke={P.line} strokeWidth="2.2" strokeLinejoin="round" />
    <path d="M-12 0 h24" fill="none" stroke={P.line} strokeWidth="2.4" />
    <path d="M-9 2 h18 l-1 5 h-16 z" fill={P.paint} />
    <path d="M-11 -1 q11 -14 22 0" fill="none" stroke={P.lineSoft} strokeWidth="1.8" />
  </g>
);

export const Newspaper = (
  <g transform="scale(0.95)">
    <path d="M-2 -4 l30 -8 l6 26 l-30 8 z" fill={P.paper}
          stroke={P.line} strokeWidth="2" strokeLinejoin="round" />
    {[0, 1, 2, 3].map((i) => (
      <path key={i} d={`M4 ${-1 + i * 5} l24 -6`} stroke={P.lineFaint} strokeWidth="1.5" />
    ))}
  </g>
);

/** A small dog on a lead, drawn with the same economy as the people. */
export const Dog = ({x, y, scale = 1, phase = 0, flip = false}) => {
  const s = Math.sin(phase * Math.PI * 2) * 6;
  return (
    <g filter="url(#pencil)"
       transform={`translate(${x} ${y}) scale(${flip ? -scale : scale} ${scale})`}>
      <ellipse cx="0" cy="2" rx="26" ry="6" fill={P.shade} opacity="0.32" />
      <path d="M-22 -34 q22 -12 44 0 l-2 18 q-20 8 -40 0 z" fill={P.paperDeep}
            stroke={P.line} strokeWidth="2.4" strokeLinejoin="round" />
      <circle cx="26" cy="-42" r="13" fill={P.paper} stroke={P.line} strokeWidth="2.4" />
      <path d="M20 -52 q4 -12 10 -4" fill={P.wash} stroke={P.line} strokeWidth="2" />
      <circle cx="31" cy="-44" r="2.4" fill={P.line} />
      <path d={`M-20 -34 q-12 -8 ${-6 + s * 0.4} -20`} fill="none"
            stroke={P.line} strokeWidth="2.6" strokeLinecap="round" />
      <path d={`M-14 -16 l${-2 + s * 0.3} 14`} stroke={P.line} strokeWidth="3" strokeLinecap="round" />
      <path d={`M14 -16 l${2 - s * 0.3} 14`} stroke={P.line} strokeWidth="3" strokeLinecap="round" />
    </g>
  );
};
