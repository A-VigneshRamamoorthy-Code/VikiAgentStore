import React, {useMemo} from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, interpolate} from 'remotion';
import {Character, strideUnits} from '../components/Character.jsx';
import {solveLocomotion} from '../lib/locomotion.js';
import {
  AtticSet, ForestSet, STORY_WORLDS, MagicBook,
} from '../components/StorySets.jsx';
import layout from '../../../assets/packs/peeps/layout.json';

import hairBun from '../../../assets/packs/peeps/head/Bun.json';
import hairGray from '../../../assets/packs/peeps/head/GrayShort.json';
import faceAwe from '../../../assets/packs/peeps/face/Awe.json';
import faceOld from '../../../assets/packs/peeps/face/Old.json';
import beardFullMax from '../../../assets/packs/peeps/beard/FullMax.json';

const FPS = 30;
const W = 1920;
const H = 1080;

export const SAMPLE_DURATION = 552;      // 18.4 s -- long holds: <=7 cuts/min
const A_END = 186;
const B_END = 366;

const cast = (skin, hair, shirt, trousers, shoes, accent) => ({
  ink: '#221d1a', skin, hair, shirt, sleeve: shirt, clothing: shirt,
  trousers, shoes, accent, lip: '#a4574d', paper: '#00000000',
});

/** E1 and W1 — the two picks the plan recommends. */
const EMMA = {
  palette: cast('#f0c8a0', '#8a5a3b', '#e0a458', '#7d8c5c', '#6b4a2f', '#c8553d'),
  hair: hairBun, face: faceAwe, beard: null, accessory: null, layout, robe: false,
};
const WIZARD = {
  palette: cast('#e0b48a', '#d8d2c8', '#4a4372', '#4a4372', '#2c2723', '#e0a458'),
  hair: hairGray, face: faceOld, beard: beardFullMax, accessory: null,
  layout, robe: true,
};

const EMMA_SCALE = 0.42;

/**
 * A drawn particle.
 *
 * Imported FX packs are greyscale alpha and tint well as a CSS mask over a flat
 * colour (see reference/assets.md). They are deliberately *not* bundled here —
 * a film's effects should not be the one thing a clean clone cannot render. So
 * the two shapes this style actually needs are drawn instead, in flat colour:
 * `glow` is concentric discs rather than a radial gradient, because the style
 * permits exactly one gradient per film and it is spent on the sky.
 */
const Particle = ({kind = 'star', x, y, size, color, opacity = 1, rotate = 0}) => {
  if (opacity <= 0.002) return null;
  const r = size / 2;
  if (kind === 'glow') {
    return (
      <g opacity={opacity}>
        {[1, 0.74, 0.5, 0.3, 0.15].map((k, i) => (
          <circle key={i} cx={x} cy={y} r={r * k} fill={color}
                  opacity={0.1 + i * 0.055} />
        ))}
      </g>
    );
  }
  const a = r, b = r * 0.17;
  return (
    <path transform={`translate(${x} ${y}) rotate(${rotate})`} fill={color}
          opacity={opacity}
          d={`M0 ${-a} Q${b} ${-b} ${a} 0 Q${b} ${b} 0 ${a} Q${-b} ${b} ${-a} 0 Q${-b} ${-b} 0 ${-a} Z`} />
  );
};

/* ── shot A: the attic, and a walk that has to hold up ───────────────────── */

const EMMA_PATH = [
  {t: 0, x: 1520}, {t: 116, x: 700}, {t: 185, x: 700},
];

const ShotAttic = () => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const world = STORY_WORLDS.attic;
  const track = useMemo(() => solveLocomotion(EMMA_PATH, {
    fps: FPS,
    walkStride: strideUnits(EMMA_SCALE, 'walk'),
    runStride: strideUnits(EMMA_SCALE, 'run'),
    idleBelow: 0.35,
    turnFrames: 7,
  }), []);
  const m = track.at(Math.min(frame, track.duration - 1));
  const ground = H * 0.80;

  return (
    <AbsoluteFill style={{backgroundColor: world.air, overflow: 'hidden'}}>
     <AbsoluteFill style={{transform: `scale(${interpolate(frame, [0, 185], [1.045, 1.0])})`}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <AtticSet W={W} Hgt={H} world={world} t={t} />
        <g transform={`translate(0 ${ground})`}>
          <Character m={m} look={EMMA} build="kid" scale={EMMA_SCALE} />
        </g>
        <g transform={`translate(${W * 0.215} ${H * 0.665}) rotate(-6)`}>
          <MagicBook s={0.42} world={world} t={t} />
        </g>
      </svg>
     </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* ── shot B: the book wakes up ───────────────────────────────────────────── */

const ShotBook = () => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const world = STORY_WORLDS.attic;
  const open = frame > 26;
  const glow = interpolate(frame, [26, 60], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const bx = W * 0.44;
  const by = H * 0.36;

  const motes = Array.from({length: 14}, (_, i) => {
    const life = ((frame - 30 + i * 7) % 90) / 90;
    if (frame < 30 || life < 0) return null;
    const ang = (i / 14) * Math.PI * 2;
    return (
      <Particle key={i} kind="star"
                x={bx + Math.cos(ang) * (70 + life * 260)}
                y={by - life * 300 + Math.sin(ang) * 40}
                size={20 + (i % 3) * 12}
                color="#e0a458"
                opacity={glow * Math.sin(life * Math.PI) * 0.95}
                rotate={life * 180} />
    );
  });

  const push = interpolate(frame, [0, 178], [1.0, 1.06], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{backgroundColor: world.air, overflow: 'hidden'}}>
     <AbsoluteFill style={{transform: `scale(${push})`}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <AtticSet W={W} Hgt={H} world={world} t={t} seed={11} />
        <g transform={`translate(${W * 0.62} ${H * 0.80})`}>
          <Character m={{t, phase: 0, moving: false, gait: 'walk', gaitMix: 0,
                         bob: 0, lean: 0, x: 0, y: 0, facingScale: -1}}
                     look={EMMA} build="kid" scale={EMMA_SCALE} />
        </g>
        <g transform={`translate(${bx} ${by}) scale(${1 + glow * 0.12})`}>
          <MagicBook s={0.72} open={open} world={world} t={t} />
        </g>
        <Particle kind="glow" x={bx} y={by - 30} size={700}
                  color="#f3d79a" opacity={glow * 0.5} />
        {motes}
      </svg>
     </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* ── shot C: the Forest of Wonders ───────────────────────────────────────── */

const ShotForest = () => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const world = STORY_WORLDS.forest;
  const flash = interpolate(frame, [0, 10, 26], [1, 0.55, 0], {
    extrapolateRight: 'clamp',
  });
  const ground = H * 0.84;

  const sparks = Array.from({length: 16}, (_, i) => {
    const life = ((frame + i * 11) % 120) / 120;
    return (
      <Particle key={i} kind="star"
                x={W * (0.12 + (i * 0.055) % 0.78)}
                y={H * 0.30 + Math.sin(t * 0.8 + i) * 60 + life * 90}
                size={16 + (i % 4) * 9}
                color="#f0e6b8"
                opacity={Math.sin(life * Math.PI) * 0.8}
                rotate={life * 90} />
    );
  });

  return (
    <AbsoluteFill style={{backgroundColor: world.sky, overflow: 'hidden'}}>
     <AbsoluteFill style={{transform: `scale(${interpolate(frame, [0, 185], [1.07, 1.0], {extrapolateRight: 'clamp'})})`}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <ForestSet W={W} Hgt={H} world={world} t={t} />
        <g transform={`translate(${W * 0.36} ${ground})`}>
          <Character m={{t, phase: 0, moving: false, gait: 'walk', gaitMix: 0,
                         bob: 0, lean: 0, x: 0, y: 0, facingScale: 1}}
                     look={EMMA} build="kid" scale={0.44} />
        </g>
        <g transform={`translate(${W * 0.62} ${ground + 6})`}>
          <Character m={{t, phase: 0, moving: false, gait: 'walk', gaitMix: 0,
                         bob: 0, lean: 0, x: 0, y: 0, facingScale: -1}}
                     look={WIZARD} scale={0.56} />
        </g>
        {sparks}
      </svg>
     </AbsoluteFill>
      <AbsoluteFill style={{backgroundColor: '#fff', opacity: flash}} />
    </AbsoluteFill>
  );
};

export const SampleFilm = () => (
  <AbsoluteFill style={{backgroundColor: '#f4efe6'}}>
    <Sequence durationInFrames={A_END}><ShotAttic /></Sequence>
    <Sequence from={A_END} durationInFrames={B_END - A_END}><ShotBook /></Sequence>
    <Sequence from={B_END} durationInFrames={SAMPLE_DURATION - B_END}><ShotForest /></Sequence>
  </AbsoluteFill>
);
