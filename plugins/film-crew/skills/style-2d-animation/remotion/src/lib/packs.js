/**
 * Style packs.
 *
 * A pack is everything that has to agree for a film to look like one film: the
 * palette, the set treatment, the ground line, and the colour roles every
 * character resolves against.
 *
 * The reason this file exists at all is the failure it prevents. When palette
 * decisions live in the shots that use them, shot 4 gets a slightly different
 * blue from shot 9, the sky changes temperature at a cut, and a character's
 * jacket drifts over the course of a film. Nobody can point at the frame where
 * it went wrong, because no single frame is wrong — the inconsistency is
 * spread across all of them.
 *
 * So a film names one pack, and every colour in it comes from here.
 *
 * ── Adding a pack ──────────────────────────────────────────────────────────
 * Copy an existing one and change the numbers. The required keys are checked
 * by `check-packs.mjs`; a pack missing a role fails loudly rather than
 * rendering something grey.
 */

/**
 * Character colour roles. `@skin`, `@clothing` and friends in the Open Peeps
 * geometry resolve against this, so a cast member is defined once and cannot
 * drift between shots.
 */
const cast = (skin, hair, shirt, trousers, shoes, accent) => ({
  ink: '#221d1a',
  skin,
  hair,
  shirt,
  sleeve: shirt,
  clothing: shirt,
  trousers,
  shoes,
  accent,
  lip: '#a4574d',
  paper: '#00000000',
});

/**
 * Humaaans colour roles.
 *
 * A different role set from `cast()` because the art is different: Humaaans has
 * no outlines, so there is no ink role doing the heavy lifting. What it has
 * instead is `shade` — a multiply-ish overlay the artist uses to turn a flat
 * garment into a folded one — and separate back-leg tones, which is the only
 * depth cue available when the two legs cross and no outline separates them.
 */
const humaaan = (skin, hair, clothing, trousers, shoes) => ({
  skin,
  hair,
  clothing,
  shade: '#191847',
  ink: '#191847',
  shoe: shoes,
  shoes,
  trousers,
  // Knocked back rather than a separate hue: a back leg is the same trouser in
  // less light, and giving it its own colour reads as two different garments.
  trousersBack: trousers,
  shoesBack: shoes,
  shadow: '#191847',
  paper: '#00000000',
});

export const PACKS = {
  /**
   * Ink on warm paper. The house look: an off-white ground, muted architecture
   * and one or two figures carrying all the colour in the frame.
   */
  'ink-street': {
    name: 'Ink Street',
    fps: 30,
    ground: 0.80,               // fraction of frame height the ground sits at
    sky: ['#f2ece1', '#e6dccb'],
    world: {
      far: '#d9d0c0',
      mid: '#cabfab',
      near: '#b8ab93',
      road: '#cfc6b6',
      roadLine: '#efe9dd',
      kerb: '#bdb2a0',
      ink: '#221d1a',
      accent: '#c8553d',
      leaf: '#8a9a6b',
      leafDeep: '#6f7f54',
      trunk: '#8a7358',
      window: '#e9e2d4',
    },
    palettes: {
      a: cast('#d08b5b', '#2f2620', '#c8553d', '#3f4a56', '#2c2723', '#e0a458'),
      b: cast('#8d5524', '#1f1a17', '#4a7c8c', '#443b33', '#2c2723', '#c8553d'),
      c: cast('#edb98a', '#6b4a2f', '#7d8c5c', '#39424e', '#2c2723', '#e0a458'),
      d: cast('#c68642', '#3a2d24', '#a0616a', '#4a4238', '#2c2723', '#7d8c5c'),
    },
  },

  /**
   * The same cast at dusk. Not a filter over the first pack — the ground goes
   * cool while the light stays warm, which is the opposition that stops a
   * frame reading as greyscale, and the accent moves to the windows so the
   * buildings carry a little of the story.
   */
  'dusk-park': {
    name: 'Dusk Park',
    fps: 30,
    ground: 0.82,
    sky: ['#f6d9b0', '#c9a3a0'],
    world: {
      far: '#9d8fa0',
      mid: '#7f7488',
      near: '#5f586c',
      road: '#6f6678',
      roadLine: '#9d93a4',
      kerb: '#584f63',
      ink: '#1d1922',
      accent: '#f2b263',
      leaf: '#5b6f5c',
      leafDeep: '#42543f',
      trunk: '#4a3b34',
      window: '#f7c877',
    },
    palettes: {
      a: cast('#d08b5b', '#2b2028', '#e2794f', '#33303f', '#241f28', '#f2b263'),
      b: cast('#8d5524', '#1a1620', '#5d7f8f', '#3a3442', '#241f28', '#e2794f'),
      c: cast('#edb98a', '#5a3f2c', '#8f9a6a', '#2f2b39', '#241f28', '#f2b263'),
      d: cast('#c68642', '#332821', '#a86470', '#3d3746', '#241f28', '#8f9a6a'),
    },
  },

  /**
   * Flat poster. No paper texture, harder chroma, a single flat sky. Reads
   * cleanly at small sizes, which is what a vertical cut needs.
   */
  'flat-poster': {
    name: 'Flat Poster',
    fps: 30,
    ground: 0.78,
    sky: ['#bfe0e6', '#a9d2dc'],
    world: {
      far: '#8fbfc9',
      mid: '#6fa8b5',
      near: '#4c8a99',
      road: '#5b6b70',
      roadLine: '#e8eef0',
      kerb: '#465358',
      ink: '#17282e',
      accent: '#ef7d57',
      leaf: '#5aa06e',
      leafDeep: '#3f7d55',
      trunk: '#6b5541',
      window: '#f4e4c1',
    },
    palettes: {
      a: cast('#d08b5b', '#26201c', '#ef7d57', '#2f4858', '#1d2a2e', '#f4d35e'),
      b: cast('#8d5524', '#181410', '#3d7ea6', '#35302a', '#1d2a2e', '#ef7d57'),
      c: cast('#edb98a', '#5c3f28', '#5aa06e', '#2b3a45', '#1d2a2e', '#f4d35e'),
      d: cast('#c68642', '#2e241d', '#b5646f', '#3c3a33', '#1d2a2e', '#5aa06e'),
    },
  },

  /**
   * Humaaans. A separate pack rather than a palette on the house look, because
   * the art itself is a different language: no outlines anywhere, saturated
   * primaries against a pale ground, and one deep navy doing every job that ink
   * does elsewhere. Mixing it with the Peeps packs is exactly the sort of
   * asset-salad this system exists to stop, so it gets its own world too —
   * flatter architecture, cooler road, no visible kerb line.
   */
  'humaaans-city': {
    name: 'Humaaans City',
    fps: 30,
    ground: 0.84,
    sky: ['#f7f6f4', '#eceae6'],
    world: {
      far: '#e4e7ee',
      mid: '#d3d8e4',
      near: '#c2c9d8',
      road: '#dfe2e9',
      roadLine: '#f7f8fa',
      kerb: '#c8cddb',
      ink: '#191847',
      accent: '#e87613',
      // Humaaans art carries no outlines, so neither does its world. Without
      // this every building and tree gets an ink rim the cast does not have,
      // and the frame reads as two different films spliced together.
      rim: false,
      leaf: '#84b8a4',
      leafDeep: '#5f9c85',
      trunk: '#b5a394',
      window: '#c1dee2',
    },
    palettes: {
      a: humaaan('#b28b67', '#191847', '#2b44ff', '#191847', '#2f3676'),
      b: humaaan('#997659', '#191847', '#e87613', '#2f3676', '#191847'),
      c: humaaan('#b28b67', '#191847', '#89c5cc', '#1f28cf', '#191847'),
      d: humaaan('#a0704a', '#191847', '#ff4133', '#191847', '#2f3676'),
    },
  },
};

export const getPack = (id) => {
  const p = PACKS[id];
  if (!p) {
    throw new Error(
      `unknown style pack "${id}". Available: ${Object.keys(PACKS).join(', ')}`
    );
  }
  return p;
};
