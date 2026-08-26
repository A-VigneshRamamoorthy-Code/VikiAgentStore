import React from 'react';
import {Layer, rim} from './Sets.jsx';

/**
 * Interior and wild sets: an attic, a forest and a cave.
 *
 * These are authored rather than imported for the same reason every other set
 * in this style is. A downloaded background carries another illustrator's
 * hand — a different ink weight, a different idea of how dark a shadow gets —
 * and the moment a rigged character stands in front of it the frame has two
 * authors in it. Searching the free packs for these three in particular turned
 * up top-down game tilesheets and storefront banners with advertising burnt
 * into them, which settled the argument.
 *
 * Everything below is drawn in frame space: the caller passes `W` and `Hgt`
 * and the set fills them. `ground` is where the floor meets the wall.
 */

const mulberry = (a) => () => {
  let t = (a += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

/* ── palettes ────────────────────────────────────────────────────────────── */

/**
 * Three worlds that still read as one film.
 *
 * The ink is the same in all three and the paper never goes fully grey — what
 * moves is the temperature and how much light the frame is allowed. The attic
 * is warm and starved of it, the forest is warm and full of it, the cave is
 * cold except where the crystal is, which is the only place the eye should go.
 */
export const STORY_WORLDS = {
  attic: {
    ink: '#221d1a', rim: true,
    air: '#eae2d2', wall: '#d9cec0', wallDark: '#cabfb0',
    floor: '#ccc0b0', floorDark: '#b9afa0',
    beam: '#a99e92', beamDark: '#948a7c',
    box: '#d8c8ac', boxDark: '#c6b596', crate: '#bcab92',
    sheet: '#e6ddcc', glass: '#9db8c4', rain: '#7f9daa',
    shaft: '#f8eed6', accent: '#c8553d', gold: '#d9a441',
  },
  forest: {
    ink: '#1f2318', rim: true,
    air: '#dfe6cf', sky: '#eef2df',
    far: '#c8d1bc', mid: '#9dad90', near: '#7f8f78',
    trunk: '#8a7d70', trunkDark: '#74695c',
    leaf: '#9ba792', leafDeep: '#798a72', leafFar: '#b3c2a3',
    fern: '#8d9a80', ground: '#939c86', groundDark: '#74806a',
    shaft: '#f2f0cf', accent: '#e0a458', glow: '#bfe08a',
  },
  cave: {
    ink: '#14161c', rim: true,
    air: '#3d4557', wall: '#4e5769', wallDark: '#3d4557',
    rock: '#5d677c', rockDark: '#474f61', rockFar: '#363d4c',
    floor: '#525b6e', floorDark: '#414857',
    glow: '#7fd8e8', glowWarm: '#bff0f6', crystal: '#8fe3f0',
    accent: '#e0a458', shaft: '#9fe6f2',
  },
};

/* ── the attic ───────────────────────────────────────────────────────────── */

const Box = ({x, y, w, h, world, flip = false}) => (
  <g transform={`translate(${x} ${y})${flip ? ' scale(-1 1)' : ''}`}>
    <rect x={-6} y={-h - 6} width={w + 12} height={h + 12} fill={world.ink} />
    <rect x={0} y={-h} width={w} height={h} fill={world.box} />
    <rect x={0} y={-h} width={w} height={h * 0.22} fill={world.boxDark} />
    <rect x={w * 0.42} y={-h} width={w * 0.16} height={h} fill={world.boxDark}
          opacity={0.55} />
  </g>
);

const Trunk = ({x, y, w, h, world}) => (
  <g transform={`translate(${x} ${y})`}>
    <path d={`M${-6} ${-h} Q${w / 2} ${-h - 34} ${w + 6} ${-h} L${w + 6} 6 L${-6} 6 Z`}
          fill={world.ink} />
    <path d={`M0 ${-h + 4} Q${w / 2} ${-h - 24} ${w} ${-h + 4} L${w} 0 L0 0 Z`}
          fill={world.crate} />
    <rect x={0} y={-h * 0.52} width={w} height={12} fill={world.beamDark} />
    <rect x={w * 0.44} y={-h * 0.62} width={w * 0.12} height={26} fill={world.gold} />
  </g>
);

/**
 * The attic. Rafters cage the frame, the window is the only light, and every
 * object is a rectangle turned a few degrees off true — a room where nothing
 * has been straightened in twenty years reads as neglected far more cheaply
 * than clutter does.
 */
export const AtticSet = ({W, Hgt, world = STORY_WORLDS.attic, seed = 11, t = 0}) => {
  const ground = Hgt * 0.80;
  const rnd = mulberry(seed);
  const winX = W * 0.66;
  const winY = Hgt * 0.30;
  const winR = Math.min(W, Hgt) * 0.115;

  const rain = [];
  for (let i = 0; i < 34; i++) {
    const a = rnd() * Math.PI * 2;
    const r = Math.sqrt(rnd()) * winR * 0.94;
    const px = winX + Math.cos(a) * r;
    const py = winY + Math.sin(a) * r + ((t * 220 + i * 47) % 90) - 45;
    rain.push(<path key={i} d={`M${px} ${py} l-7 26`} stroke={world.rain}
                    strokeWidth={2.4} strokeLinecap="round" opacity={0.6} />);
  }

  const motes = [];
  for (let i = 0; i < 26; i++) {
    const mx = winX - 40 - rnd() * 360;
    const my = winY + 60 + rnd() * (ground - winY - 40);
    const drift = Math.sin(t * 0.7 + i) * 9;
    motes.push(<circle key={i} cx={mx + drift} cy={my} r={1.6 + rnd() * 2.4}
                       fill={world.shaft} opacity={0.30 + rnd() * 0.4} />);
  }

  return (
    <g>
      <rect x={0} y={0} width={W} height={Hgt} fill={world.wall} />
      <rect x={0} y={0} width={W} height={Hgt * 0.34} fill={world.wallDark} />

      {/* the roof slopes in from both sides: an attic is defined by its ceiling */}
      <path d={`M0 0 L${W * 0.30} ${Hgt * 0.30} L0 ${Hgt * 0.30} Z`} fill={world.beamDark} />
      <path d={`M${W} 0 L${W * 0.70} ${Hgt * 0.30} L${W} ${Hgt * 0.30} Z`} fill={world.beamDark} />
      {[0.16, 0.42, 0.86].map((f, i) => (
        <path key={i} d={`M${W * f} 0 L${W * f + 46} 0 L${W * f + 300} ${Hgt * 0.34} L${W * f + 254} ${Hgt * 0.34} Z`}
              fill={world.beam} opacity={0.9} />
      ))}
      <rect x={0} y={Hgt * 0.055} width={W} height={30} fill={world.beam} />
      <rect x={0} y={Hgt * 0.055} width={W} height={8} fill={world.beamDark} />

      {/* window: the light source, so it is drawn before anything it lights */}
      <circle cx={winX} cy={winY} r={winR + 13} fill={world.ink} />
      <circle cx={winX} cy={winY} r={winR} fill={world.glass} />
      <g clipPath="url(#atticWin)">{rain}</g>
      <defs><clipPath id="atticWin">
        <circle cx={winX} cy={winY} r={winR} />
      </clipPath></defs>
      <path d={`M${winX - winR} ${winY} L${winX + winR} ${winY}`} stroke={world.ink} strokeWidth={9} />
      <path d={`M${winX} ${winY - winR} L${winX} ${winY + winR}`} stroke={world.ink} strokeWidth={9} />

      {/* the shaft, thrown down and to the left, wide where it lands */}
      <path d={`M${winX - winR * 0.8} ${winY + winR * 0.5} L${winX + winR * 0.8} ${winY + winR * 0.5}`
            + ` L${winX - winR * 0.2} ${ground + 10} L${winX - winR * 3.4} ${ground + 10} Z`}
            fill={world.shaft} opacity={0.20} />

      <rect x={0} y={ground} width={W} height={Hgt - ground} fill={world.floor} />
      <rect x={0} y={ground} width={W} height={12} fill={world.ink} opacity={0.5} />
      {Array.from({length: 13}, (_, i) => (
        <path key={i} d={`M${(i * W) / 12} ${ground} L${(i * W) / 12 - 60} ${Hgt}`}
              stroke={world.floorDark} strokeWidth={3} opacity={0.55} />
      ))}

      <Box x={W * 0.04} y={ground} w={150} h={124} world={world} />
      <Box x={W * 0.055} y={ground - 124} w={112} h={96} world={world} flip />
      <Trunk x={W * 0.20} y={ground} w={196} h={118} world={world} />
      <Box x={W * 0.86} y={ground} w={168} h={140} world={world} />

      {/* a sheet over something tall — the shape reads as furniture without
          anyone having to decide what the furniture is */}
      <path d={`M${W * 0.40} ${ground} L${W * 0.415} ${ground - 250}`
            + ` Q${W * 0.47} ${ground - 300} ${W * 0.525} ${ground - 244}`
            + ` L${W * 0.545} ${ground} Z`} fill={world.ink} />
      <path d={`M${W * 0.408} ${ground} L${W * 0.422} ${ground - 240}`
            + ` Q${W * 0.47} ${ground - 288} ${W * 0.518} ${ground - 234}`
            + ` L${W * 0.537} ${ground} Z`} fill={world.sheet} />

      {motes}
    </g>
  );
};

/* ── the forest ──────────────────────────────────────────────────────────── */

const ForestTree = ({x, s, ground, world, fill, deep, trunk}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    <path d="M-20 0 L-13 -210 L13 -210 L20 0 z" fill={rim(world, trunk)} />
    <path d="M-14 0 L-9 -206 L9 -206 L14 0 z" fill={trunk} />
    <circle cx={0} cy={-296} r={132} fill={rim(world, fill)} />
    <circle cx={-88} cy={-238} r={94} fill={rim(world, deep)} />
    <circle cx={90} cy={-246} r={88} fill={rim(world, fill)} />
    <circle cx={0} cy={-296} r={120} fill={fill} />
    <circle cx={-88} cy={-238} r={82} fill={deep} />
    <circle cx={90} cy={-246} r={76} fill={fill} />
  </g>
);

const Fern = ({x, ground, s, world}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    {[-1, -0.5, 0, 0.5, 1].map((k, i) => (
      <path key={i} d={`M0 0 Q${k * 54} ${-46} ${k * 84} ${-96}`}
            stroke={world.fern} strokeWidth={13} fill="none" strokeLinecap="round" />
    ))}
  </g>
);

/** The Forest of Wonders. Three depths, each paler and slower than the one in
 *  front, plus light coming down through the canopy — which is the whole
 *  reason a forest reads as enchanted rather than merely wooded. */
export const ForestSet = ({W, Hgt, world = STORY_WORLDS.forest, camX = 0, seed = 3, t = 0}) => {
  const ground = Hgt * 0.82;
  const rnd = mulberry(seed);
  const sparks = [];
  for (let i = 0; i < 30; i++) {
    const sx = rnd() * W;
    const sy = Hgt * 0.20 + rnd() * (ground - Hgt * 0.22);
    const tw = 0.45 + 0.55 * Math.abs(Math.sin(t * 1.3 + i * 1.7));
    sparks.push(<circle key={i} cx={sx} cy={sy + Math.sin(t + i) * 12}
                        r={2 + rnd() * 3} fill={world.glow} opacity={tw * 0.8} />);
  }
  return (
    <g>
      <rect x={0} y={0} width={W} height={Hgt} fill={world.sky} />
      <rect x={0} y={0} width={W} height={Hgt * 0.5} fill={world.air} opacity={0.6} />

      <Layer depth={0.15} camX={camX}>
        {[0.05, 0.26, 0.5, 0.72, 0.94].map((f, i) => (
          <ForestTree key={i} x={W * f} s={0.72} ground={ground - 40} world={world}
                      fill={world.leafFar} deep={world.far} trunk={world.far} />
        ))}
      </Layer>

      {/* shafts sit between the far and mid canopy, so trunks in front of them
          occlude and the light acquires depth for free */}
      {[0.18, 0.44, 0.74].map((f, i) => (
        <path key={i}
              d={`M${W * f} 0 L${W * f + 130} 0 L${W * f + 40} ${ground} L${W * f - 130} ${ground} Z`}
              fill={world.shaft} opacity={0.17} />
      ))}

      <Layer depth={0.45} camX={camX}>
        {[0.14, 0.38, 0.62, 0.88].map((f, i) => (
          <ForestTree key={i} x={W * f} s={0.95} ground={ground - 12} world={world}
                      fill={world.leafDeep} deep={world.mid} trunk={world.trunkDark} />
        ))}
      </Layer>

      <rect x={0} y={ground} width={W} height={Hgt - ground} fill={world.ground} />
      <path d={`M0 ${ground} Q${W * 0.3} ${ground - 22} ${W * 0.55} ${ground - 6}`
            + ` T${W} ${ground - 14} L${W} ${ground + 26} L0 ${ground + 26} Z`}
            fill={world.groundDark} opacity={0.7} />

      <Layer depth={1} camX={camX}>
        <ForestTree x={W * 0.08} s={1.25} ground={ground + 26} world={world}
                    fill={world.leaf} deep={world.leafDeep} trunk={world.trunk} />
        <ForestTree x={W * 0.93} s={1.35} ground={ground + 30} world={world}
                    fill={world.leaf} deep={world.leafDeep} trunk={world.trunk} />
        {[0.24, 0.46, 0.68, 0.82].map((f, i) => (
          <Fern key={i} x={W * f} ground={ground + 22} s={0.8 + (i % 2) * 0.3} world={world} />
        ))}
      </Layer>

      {sparks}
    </g>
  );
};

/* ── the cave ────────────────────────────────────────────────────────────── */

/** The cave. The frame is masked by rock so the audience is inside it, and the
 *  only warm thing in the palette is the glow — put the crystal there and no
 *  one needs telling where to look. */
export const CaveSet = ({W, Hgt, world = STORY_WORLDS.cave, seed = 5, t = 0}) => {
  const ground = Hgt * 0.80;
  const rnd = mulberry(seed);
  const gx = W * 0.62;
  const gy = ground - Hgt * 0.10;
  const pulse = 0.82 + 0.18 * Math.sin(t * 1.6);

  const spikes = (n, top) => Array.from({length: n}, (_, i) => {
    const x = (i + 0.5) * (W / n) + (rnd() - 0.5) * 60;
    const h = (0.06 + rnd() * 0.12) * Hgt;
    const w = 34 + rnd() * 40;
    return top
      ? <path key={i} d={`M${x - w} 0 L${x + w} 0 L${x} ${h} Z`} fill={world.rock} />
      : <path key={i} d={`M${x - w} ${Hgt} L${x + w} ${Hgt} L${x} ${Hgt - h} Z`} fill={world.rockDark} />;
  });

  return (
    <g>
      <rect x={0} y={0} width={W} height={Hgt} fill={world.air} />
      <ellipse cx={gx} cy={gy} rx={W * 0.42} ry={Hgt * 0.34}
               fill={world.glow} opacity={0.13 * pulse} />

      <rect x={0} y={0} width={W} height={Hgt * 0.16} fill={world.rockFar} />
      {spikes(9, true)}
      <rect x={0} y={ground} width={W} height={Hgt - ground} fill={world.floor} />
      <path d={`M0 ${ground} Q${W * 0.25} ${ground - 26} ${W * 0.52} ${ground - 8}`
            + ` T${W} ${ground - 18} L${W} ${Hgt} L0 ${Hgt} Z`} fill={world.floorDark} />

      {/* the rock that frames the shot, drawn last on the sides so figures
          walk behind it and the mouth of the cave stays a hole, not a wall */}
      <path d={`M0 0 L${W * 0.22} 0 Q${W * 0.13} ${Hgt * 0.42} ${W * 0.20} ${Hgt}`
            + ` L0 ${Hgt} Z`} fill={world.rockDark} />
      <path d={`M${W} 0 L${W * 0.80} 0 Q${W * 0.89} ${Hgt * 0.38} ${W * 0.82} ${Hgt}`
            + ` L${W} ${Hgt} Z`} fill={world.rockDark} />

      {[[W * 0.30, ground, 0.9], [W * 0.44, ground, 0.6], [W * 0.74, ground, 0.75]].map(([x, y, s], i) => (
        <g key={i} transform={`translate(${x} ${y}) scale(${s})`}>
          <path d="M-84 0 Q-66 -66 -6 -74 Q56 -70 78 0 Z" fill={world.ink} />
          <path d="M-76 0 Q-60 -58 -6 -66 Q50 -62 70 0 Z" fill={world.rock} />
        </g>
      ))}

      <g transform={`translate(${gx} ${gy})`}>
        <circle r={128} fill={world.glow} opacity={0.16 * pulse} />
        <circle r={74} fill={world.glow} opacity={0.24 * pulse} />
        <Crystal s={1.15} world={world} t={t} />
      </g>
    </g>
  );
};

/* ── props ───────────────────────────────────────────────────────────────── */

/** The crystal, drawn as facets rather than a gradient — a gradient is the one
 *  thing this style never does, and faceting reads as "gem" just as fast. */
export const Crystal = ({s = 1, world = STORY_WORLDS.cave, t = 0}) => {
  const p = 0.85 + 0.15 * Math.sin(t * 2.1);
  return (
    <g transform={`scale(${s})`}>
      <path d="M0 -96 L46 -18 L26 68 L-26 68 L-46 -18 Z" fill={world.ink}
            transform="scale(1.14)" />
      <path d="M0 -96 L46 -18 L26 68 L-26 68 L-46 -18 Z" fill={world.crystal} />
      <path d="M0 -96 L-46 -18 L-26 68 Z" fill={world.glowWarm} opacity={0.55} />
      <path d="M0 -96 L46 -18 L26 68 Z" fill={world.glow} opacity={0.35} />
      <path d="M0 -96 L0 68" stroke={world.glowWarm} strokeWidth={4} opacity={0.5 * p} />
    </g>
  );
};

/** The Book of Endless Adventures. `open` swings it into a spread with light
 *  climbing out of the gutter, which is the only moment it has to act. */
export const MagicBook = ({s = 1, open = false, world = STORY_WORLDS.attic, t = 0}) => {
  const p = 0.8 + 0.2 * Math.sin(t * 2.4);
  if (!open) {
    return (
      <g transform={`scale(${s})`}>
        <rect x={-118} y={-84} width={236} height={168} rx={9} fill={world.ink} />
        <rect x={-110} y={-76} width={220} height={152} rx={7} fill="#7a3f2e" />
        <rect x={-110} y={-76} width={22} height={152} fill="#5e2f22" />
        <rect x={-70} y={-52} width={140} height={104} rx={5} fill="none"
              stroke={world.gold} strokeWidth={6} />
        <circle cx={0} cy={0} r={26} fill={world.gold} opacity={0.9} />
        <path d="M0 -15 L5 -4 L17 -4 L7 3 L11 15 L0 8 L-11 15 L-7 3 L-17 -4 L-5 -4 Z"
              fill="#7a3f2e" />
      </g>
    );
  }
  return (
    <g transform={`scale(${s})`}>
      <ellipse cx={0} cy={-40} rx={210} ry={150} fill={world.gold} opacity={0.20 * p} />
      <path d="M-190 60 Q0 20 190 60 L172 -66 Q0 -104 -172 -66 Z" fill={world.ink} />
      <path d="M-178 52 Q0 14 178 52 L162 -58 Q0 -94 -162 -58 Z" fill="#f2e7cf" />
      <path d="M0 16 L0 -92" stroke={world.ink} strokeWidth={7} opacity={0.5} />
      <path d="M-150 -30 Q-76 -50 -14 -34" stroke="#b9a88a" strokeWidth={5} fill="none" />
      <path d="M14 -34 Q76 -50 150 -30" stroke="#b9a88a" strokeWidth={5} fill="none" />
      <path d="M-150 -6 Q-76 -26 -14 -10" stroke="#b9a88a" strokeWidth={5} fill="none" />
      <path d="M14 -10 Q76 -26 150 -6" stroke="#b9a88a" strokeWidth={5} fill="none" />
      <path d={`M0 10 L${26 * p} ${-58 * p} L0 ${-116 * p} L${-26 * p} ${-58 * p} Z`}
            fill={world.gold} opacity={0.85} />
    </g>
  );
};
