import React from 'react';
import {P} from './palette.js';

/**
 * Hold a value on 2s or 3s.
 *
 * Drawn animation is not rendered every frame -- it is drawn once and held for
 * two or three, and that stutter is a large part of why it reads as drawn
 * rather than as tweened vector art. Everything in this film samples time
 * through here rather than through `useCurrentFrame()` directly.
 */
export const step = (frame, on = 2) => Math.floor(frame / on) * on;

/**
 * The filter stack that turns clean SVG into pencil.
 *
 * Two things are happening:
 *
 * 1. `feTurbulence` + `feDisplacementMap` push every point of every path
 *    sideways by a couple of pixels along a smooth noise field, so straight
 *    lines bow and corners stop being exact. This is the difference between
 *    "vector illustration" and "someone drew this".
 *
 * 2. The turbulence `seed` is re-rolled on every held frame. A fixed seed
 *    gives a wobbly drawing that is *identically* wobbly for the whole film,
 *    which looks like a warped photocopy. Re-rolling makes the line boil the
 *    way a redrawn line does. It is the single highest-value trick here.
 *
 * `scale` is deliberately small. Past about 3 device pixels the drawing stops
 * looking hand-made and starts looking underwater -- which is why `cam` exists:
 * displacement is measured in the *user* units of the filtered element, so
 * anything drawn inside a scaled camera group gets its wobble multiplied by
 * that scale for free. Dividing it back out is the difference between a pencil
 * line and a heat haze. `#pencilFlat` is the undivided version, for the title
 * cards and clouds, which are drawn in screen space.
 */
export const PencilDefs = ({seed, scale = 1.7, cam = 1}) => (
  <defs>
    <filter id="pencil" x="-12%" y="-12%" width="124%" height="124%"
            filterUnits="objectBoundingBox">
      <feTurbulence type="fractalNoise" baseFrequency="0.022" numOctaves="3"
                    seed={seed} result="n" />
      <feDisplacementMap in="SourceGraphic" in2="n" scale={scale / cam}
                         xChannelSelector="R" yChannelSelector="G" />
    </filter>

    <filter id="pencilFlat" x="-12%" y="-12%" width="124%" height="124%"
            filterUnits="objectBoundingBox">
      <feTurbulence type="fractalNoise" baseFrequency="0.022" numOctaves="3"
                    seed={seed} result="n" />
      <feDisplacementMap in="SourceGraphic" in2="n" scale={scale}
                         xChannelSelector="R" yChannelSelector="G" />
    </filter>

    {/* A softer pass for things that are far away. Distance in this medium is
        drawn with a lighter, looser pencil rather than with blur, so the
        displacement goes up while the contrast comes down. */}
    <filter id="pencilFar" x="-12%" y="-12%" width="124%" height="124%">
      <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2"
                    seed={seed + 7} result="n" />
      <feDisplacementMap in="SourceGraphic" in2="n" scale={(scale * 1.4) / cam}
                         xChannelSelector="R" yChannelSelector="G" />
    </filter>

    {/* Paper grain. Coarse, low-contrast, and multiplied over everything --
        a flat cream field is the other thing that gives vector away. */}
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="4"
                    seed="4" result="g" />
      <feColorMatrix in="g" type="saturate" values="0" />
    </filter>
  </defs>
);

/**
 * The cream field the whole film is drawn on.
 *
 * The vignette is not a photographic vignette -- it is the way the middle of a
 * sheet of paper catches light and the edges sit slightly darker, so it is
 * warm, very shallow, and elliptical rather than square.
 */
export const Paper = ({width, height}) => (
  <>
    <rect width={width} height={height} fill={P.paper} />
    <rect width={width} height={height} filter="url(#grain)"
          opacity="0.055" style={{mixBlendMode: 'multiply'}} />
    <radialGradient id="vig" cx="50%" cy="46%" r="72%">
      <stop offset="55%" stopColor="#000" stopOpacity="0" />
      <stop offset="100%" stopColor="#5a5240" stopOpacity="0.11" />
    </radialGradient>
    <rect width={width} height={height} fill="url(#vig)" />
  </>
);

/**
 * A stroked path in pencil.
 *
 * `w` is a weight class rather than a pixel width so the drawing keeps one
 * consistent hand: 0 is a construction line, 1 is ordinary, 2 is the weight
 * used to sit an object on the ground.
 */
export const Ink = ({d, w = 1, far = false, opacity = 1, fill = 'none', cap = 'round'}) => (
  <path d={d} fill={fill} stroke={far ? P.lineFaint : (w >= 2 ? P.line : P.lineSoft)}
        strokeWidth={[1.1, 1.9, 2.8][w] ?? 1.9} strokeLinecap={cap}
        strokeLinejoin="round" opacity={opacity} />
);

/**
 * Pencil hatching inside an arbitrary shape.
 *
 * The reference shades with visible diagonal strokes, never with flat fills,
 * so this lays parallel lines across the bounding box and clips them to the
 * shape. Slight per-line jitter keeps them from reading as a screen pattern.
 */
export const Hatch = ({id, d, x, y, w, h, gap = 7, angle = -38, opacity = 0.3}) => {
  const lines = [];
  const span = w + h;
  for (let i = -h; i < span; i += gap) {
    const j = ((i * 37) % 11) / 11 - 0.5;      // deterministic, not random
    lines.push(`M${x + i + j * 2} ${y + h} L${x + i + h * 0.9 + j * 2} ${y}`);
  }
  return (
    <g>
      <clipPath id={id}><path d={d} /></clipPath>
      <g clipPath={`url(#${id})`} transform={`rotate(${angle + 38} ${x + w / 2} ${y + h / 2})`}>
        {lines.map((l, i) => (
          <path key={i} d={l} stroke={P.line} strokeWidth="1.15"
                opacity={opacity} strokeLinecap="round" />
        ))}
      </g>
    </g>
  );
};
