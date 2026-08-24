import React from 'react';
import {P} from './palette.js';
import {Ink} from './Paper.jsx';

// The reference opens and closes on near-empty paper with a line of hand
// lettering and a couple of clouds, and holds both far longer than a title
// card normally would. That patience is part of the joke's delivery, so the
// cards here are long too.

/**
 * A cloud, drawn as overlapping arcs rather than as a filled blob so the
 * pencil outline stays visible where the lobes cross.
 */
export const Cloud = ({x, y, s = 1, opacity = 0.75}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity} filter="url(#pencilFlat)">
    <path d="M0 0 q4 -30 34 -28 q10 -26 42 -18 q26 -16 42 10 q26 -2 24 22 q-2 16 -22 16 l-100 0 q-20 0 -20 -2 z"
          fill={P.paper} stroke={P.lineSoft} strokeWidth="2.2" strokeLinejoin="round" />
    <path d="M18 -8 q14 -12 30 -8" fill="none" stroke={P.lineFaint} strokeWidth="1.6" />
  </g>
);

/**
 * Hand lettering.
 *
 * The wobble is per-character and derived from the character's index, so it is
 * stable across frames -- letters that jitter every frame read as a glitch,
 * not as handwriting. The pencil filter supplies the line quality; this only
 * supplies the irregular baseline that hand lettering always has.
 */
export const Lettering = ({text, x, y, size = 92, opacity = 1, anchor = 'middle'}) => {
  const chars = [...text];
  const total = chars.length;
  return (
    <g opacity={opacity} filter="url(#pencilFlat)">
      <text x={x} y={y} textAnchor={anchor} fill={P.line}
            style={{font: `600 ${size}px "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive`}}>
        {chars.map((c, i) => (
          <tspan key={i}
                 dy={((i * 53) % 7) / 7 * (size * 0.045) - size * 0.022}
                 rotate={((i * 29) % 9) / 9 * 5 - 2.5}>
            {c}
          </tspan>
        ))}
      </text>
      {/* The underline is drawn as a bowed stroke, because a ruler is the one
          tool this medium never admits to owning. */}
      <Ink d={`M${x - total * size * 0.23} ${y + size * 0.28} q${total * size * 0.23} ${size * 0.09} ${total * size * 0.46} 0`}
           w={1} opacity={0.5} />
    </g>
  );
};
