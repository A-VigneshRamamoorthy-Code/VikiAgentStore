// Palette, measured from the reference rather than picked by eye.
//
// Sampling six frames of the reference across its runtime gives mean
// saturation 0.132, mean value 0.878, and only 0.92% of pixels above
// saturation 0.35. That last number is the whole discipline of this look: it
// is a warm near-monochrome drawing with one small coloured thing in it, and
// the moment a second thing competes the style stops reading as pencil.
//
// So there is exactly one saturated token here -- `paint` -- and everything
// else is a warm grey stepped off the paper.

export const P = {
  // The eight dominant colours of the reference quantise to a cream paper and
  // a ladder of warm greys. These are those readings, not an interpretation.
  paper: '#f0e8d0',
  paperDeep: '#e8e0cc',
  wash: '#d8d0c0',
  washDeep: '#c0b8a8',
  shade: '#b8b0a0',

  // Pencil. Never pure black -- graphite on cream reads brown-grey, and #000
  // is the single fastest way to lose the medium.
  line: '#4a463c',
  lineSoft: '#6f6a5c',
  lineFaint: '#9a9483',

  // The one colour in the film. It is the gag, so it is allowed to be the
  // only saturated thing on screen -- but the reference keeps its coloured
  // object under 1% of frame area, so this is a muted sage rather than a
  // true teal. At sat 0.25 it still reads as "the only colour here" without
  // punching a hole in a pencil drawing.
  paint: '#578f84',
  paintWet: '#679c92',
};

/** Ink at an arbitrary strength, for depth without introducing a new hue. */
export const ink = (a) => `rgba(74,70,60,${a})`;
