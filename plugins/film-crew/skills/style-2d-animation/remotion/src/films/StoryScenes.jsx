import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Character} from '../components/Character.jsx';
import {
  AtticSet, ForestSet, CaveSet, STORY_WORLDS, MagicBook, Crystal,
} from '../components/StorySets.jsx';
import layout from '../../../assets/packs/peeps/layout.json';

import hairBun from '../../../assets/packs/peeps/head/Bun.json';
import hairGray from '../../../assets/packs/peeps/head/GrayShort.json';
import faceAwe from '../../../assets/packs/peeps/face/Awe.json';
import faceOld from '../../../assets/packs/peeps/face/Old.json';
import beardFullMax from '../../../assets/packs/peeps/beard/FullMax.json';

const cast = (skin, hair, shirt, trousers, shoes, accent) => ({
  ink: '#221d1a', skin, hair, shirt, sleeve: shirt, clothing: shirt,
  trousers, shoes, accent, lip: '#a4574d', paper: '#00000000',
});

const EMMA = {
  palette: cast('#f0c8a0', '#8a5a3b', '#e0a458', '#7d8c5c', '#6b4a2f', '#c8553d'),
  hair: hairBun, face: faceAwe, beard: null, accessory: null, layout, robe: false,
};

const WIZARD = {
  palette: cast('#e0b48a', '#d8d2c8', '#4a4372', '#4a4372', '#2c2723', '#e0a458'),
  hair: hairGray, face: faceOld, beard: beardFullMax, accessory: null,
  layout, robe: true,
};

const still = (x, y) => ({
  t: 0, phase: 0, moving: false, gait: 'walk', gaitMix: 0,
  bob: 0, lean: 0, x, y, facingScale: 1,
});

const W = 1920;
const H = 1080;

export const AtticScene = () => {
  const t = useCurrentFrame() / 30;
  const world = STORY_WORLDS.attic;
  return (
    <AbsoluteFill style={{backgroundColor: world.air}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <AtticSet W={W} Hgt={H} world={world} t={t} />
        <g transform={`translate(${W * 0.34} ${H * 0.80})`}>
          <Character m={still(0, 0)} look={EMMA} build="kid" scale={0.42} />
        </g>
        <g transform={`translate(${W * 0.215} ${H * 0.665}) rotate(-6)`}>
          <MagicBook s={0.42} world={world} t={t} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

export const ForestScene = () => {
  const t = useCurrentFrame() / 30;
  const world = STORY_WORLDS.forest;
  return (
    <AbsoluteFill style={{backgroundColor: world.sky}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <ForestSet W={W} Hgt={H} world={world} t={t} />
        <g transform={`translate(${W * 0.36} ${H * 0.84})`}>
          <Character m={still(0, 0)} look={EMMA} build="kid" scale={0.44} />
        </g>
        <g transform={`translate(${W * 0.60} ${H * 0.845}) scale(-1 1)`}>
          <Character m={still(0, 0)} look={WIZARD} scale={0.56} />
        </g>
        <g transform={`translate(${W * 0.47} ${H * 0.50})`}>
          <MagicBook s={0.34} open world={STORY_WORLDS.attic} t={t} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

export const CaveScene = () => {
  const t = useCurrentFrame() / 30;
  const world = STORY_WORLDS.cave;
  return (
    <AbsoluteFill style={{backgroundColor: world.air}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <CaveSet W={W} Hgt={H} world={world} t={t} />
        <g transform={`translate(${W * 0.40} ${H * 0.80})`}>
          <Character m={still(0, 0)} look={EMMA} build="kid" scale={0.42} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

export const CrystalCard = () => {
  const t = useCurrentFrame() / 30;
  return (
    <AbsoluteFill style={{backgroundColor: '#f4efe6'}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <g transform={`translate(${W * 0.25} ${H * 0.5}) scale(2.1)`}>
          <Crystal world={STORY_WORLDS.cave} t={t} />
        </g>
        <g transform={`translate(${W * 0.58} ${H * 0.5}) scale(1.15)`}>
          <MagicBook world={STORY_WORLDS.attic} t={t} />
        </g>
        <g transform={`translate(${W * 0.85} ${H * 0.5}) scale(0.8)`}>
          <MagicBook world={STORY_WORLDS.attic} open t={t} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};
