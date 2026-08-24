import React from 'react';
import {AbsoluteFill} from 'remotion';

import {HumaaansCharacter, HPart, FIG, prepareBottom} from '../components/Humaaans.jsx';
import {getPack} from '../lib/packs';

import head from '../../../assets/packs/humaaans/head/Curly.json';
import body from '../../../assets/packs/humaaans/body/Jacket.json';
import bottomJeans from '../../../assets/packs/humaaans/bottom/Skinny-Jeans.json';
import bottomSweats from '../../../assets/packs/humaaans/bottom/Sweatpants.json';

/**
 * The proportion bench.
 *
 * `RigTest` answers "does the walk hold together over a cycle". This answers a
 * different and earlier question: "is this figure shaped like the thing the
 * artist drew". Those are not the same check, and skipping this one is how the
 * rig ended up with legs half again too wide -- every frame was individually
 * defensible and the figure was still wrong.
 *
 * Column 1 is the artist's own composition: head, body and a real `bottom/`
 * asset stacked at the offsets in `layout.json`, with no rig involved at all.
 * It is the control. Columns 2 and 3 are the rig standing and mid-stride, and
 * they have to read as the same person.
 *
 * That claim used to end "...and the `bottom/` assets cannot be used for the
 * film itself, because each is a single frozen silhouette with no joint to
 * drive". It was wrong, and believing it cost the rig its proportions: the
 * legs in `bottom/Sweatpants` are two separate paths with a waistband apiece
 * and a shoe apiece, which is a joint and a foot -- everything a cut-out rig
 * needs. The films now use exactly these drawings, so column 1 is no longer
 * just a ruler, it is the same artwork the rig is posing.
 */

const FPS = 30;
export const BENCH_DURATION = FPS;

/** The offsets `layout.json` composes a figure at, in rig coordinates. */
const BOTTOM_X = -150;
const BOTTOM_Y = FIG.hipY;

const Reference = ({palette, bottom}) => (
  <g>
    <g transform={`translate(${BOTTOM_X} ${BOTTOM_Y})`}>
      <HPart asset={bottom} palette={palette} />
    </g>
    <g transform={`translate(${FIG.bodyX} ${FIG.bodyTop})`}>
      <HPart asset={body} palette={palette} />
    </g>
    <g transform={`translate(${FIG.headX} ${FIG.headTop})`}>
      <HPart asset={head} palette={palette} />
    </g>
  </g>
);

const pose = (over = {}) => ({
  x: 0, y: 0, t: 0, phase: 0, bob: 0, lean: 0,
  facing: 1, facingScale: 1, moving: false, gait: 'walk', gaitMix: 0,
  ...over,
});

const Label = ({x, y, text}) => (
  <text x={x} y={y} fontSize="26" fontFamily="monospace" fill="#191847"
        textAnchor="middle" opacity="0.75">{text}</text>
);

export const HumaaansBench = () => {
  const pack = getPack('humaaans-city');
  const palette = pack.palettes.a;
  const W = 2760;
  const H = 900;
  const ground = 760;
  const scale = 1.35;

  const col = (i) => 175 + i * 240;
  const art = prepareBottom(bottomSweats);

  return (
    <AbsoluteFill style={{backgroundColor: '#f7f6f4'}}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {/* A shared ground line and a shared shoulder line. Two figures the
            same height with different internal proportions look identical
            until something straight crosses both of them. */}
        <rect x={0} y={ground} width={W} height={4} fill="#191847" opacity="0.35" />
        <rect x={0} y={ground + FIG.hipY * scale} width={W} height={2}
              fill="#e87613" opacity="0.55" />
        <rect x={0} y={ground + FIG.bodyTop * scale} width={W} height={2}
              fill="#e87613" opacity="0.35" />

        <g transform={`translate(${col(0)} ${ground}) scale(${scale})`}>
          <Reference palette={palette} bottom={bottomJeans} />
        </g>
        <g transform={`translate(${col(1)} ${ground}) scale(${scale})`}>
          <Reference palette={palette} bottom={bottomSweats} />
        </g>

        {/* Standing, straight off the drawing: the rig at rest must be pixel
            identical to the reference beside it, because at rest it is not
            allowed to do anything at all. */}
        <g transform={`translate(${col(2)} 0)`}>
          <HumaaansCharacter m={pose({x: 0, y: ground})}
                             look={{palette, head, body, bottom: art}} scale={scale} shadow={false} />
        </g>
        <g transform={`translate(${col(3)} 0)`}>
          <HumaaansCharacter m={pose({x: 0, y: ground, sit: 1})} sit={1}
                             look={{palette, head, body, bottom: art}}
                             scale={scale} shadow={false} />
        </g>
        {[0.12, 0.32, 0.5].map((ph, i) => (
          <g key={`a${ph}`} transform={`translate(${col(4 + i)} 0)`}>
            <HumaaansCharacter m={pose({x: 0, y: ground, moving: true, phase: ph})}
                               look={{palette, head, body, bottom: art}} scale={scale} shadow={false} />
          </g>
        ))}
        {/* The stress case. A run asks for more reach than a straight drawn
            leg has, so this is where the foreshortening earns its place --
            and where a rig that only rotated would drag its feet. */}
        {[0.1, 0.3, 0.55].map((ph, i) => (
          <g key={`r${ph}`} transform={`translate(${col(7 + i)} 0)`}>
            <HumaaansCharacter
              m={pose({x: 0, y: ground, moving: true, phase: ph, gait: 'run', gaitMix: 1})}
              look={{palette, head, body, bottom: art}} scale={scale} shadow={false} />
          </g>
        ))}

        <Label x={col(0)} y={ground + 50} text="art jeans" />
        <Label x={col(1)} y={ground + 50} text="art sweats" />
        <Label x={col(2)} y={ground + 50} text="rig rest" />
        <Label x={col(3)} y={ground + 50} text="rig sit" />
        <Label x={col(4)} y={ground + 50} text="WALK .12" />
        <Label x={col(5)} y={ground + 50} text="WALK .32" />
        <Label x={col(6)} y={ground + 50} text="WALK .50" />
        <Label x={col(7)} y={ground + 50} text="RUN .10" />
        <Label x={col(8)} y={ground + 50} text="RUN .30" />
        <Label x={col(9)} y={ground + 50} text="RUN .55" />
      </svg>
    </AbsoluteFill>
  );
};
