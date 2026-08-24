import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {Character, strideUnits} from '../components/Character.jsx';
import {solveLocomotion} from '../lib/locomotion.js';
import {getPack} from '../lib/packs.js';
import layout from '../../../assets/packs/peeps/layout.json';

import headAfro from '../../../assets/packs/peeps/head/Afro.json';
import faceCalm from '../../../assets/packs/peeps/face/Calm.json';
import accGlasses from '../../../assets/packs/peeps/accessory/Glasses.json';

/**
 * The rig, big and side-on, at eight points around one stride.
 *
 * This is the bench every change to `Character.jsx` gets judged on before it
 * goes anywhere near a film. A walk is wrong in ways a single frame hides and
 * a moving picture hides even better — the eye forgives a lot at 30fps — so
 * the cycle is laid out flat and compared against itself.
 *
 * The bottom row is the same rig standing still, which is a different pose
 * rather than phase 0 of the walk, and is the thing most often got wrong.
 */
const FPS = 30;
export const RIG_DURATION = 120;

export const RigTest = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const pack = getPack('ink-street');

  // The figure is solved at the size it is drawn, so the stride it is given
  // and the stride it walks are the same number by construction.
  const CELL_SCALE = 0.40;
  const SPEED = strideUnits(CELL_SCALE) * 1.1;   // ~1.1 cycles/sec: a stroll

  const track = useMemo(
    () =>
      solveLocomotion(
        [
          {t: 0, x: 0, ease: 'linear'},
          {t: 300, x: SPEED * 10, ease: 'linear'},
        ],
        {
          fps: FPS,
          walkStride: strideUnits(CELL_SCALE, 'walk'),
          runStride: strideUnits(CELL_SCALE, 'run'),
          idleBelow: 0.35,
        }
      ),
    [SPEED]
  );

  const look = {
    palette: pack.palettes.a,
    hair: headAfro,
    face: faceCalm,
    accessory: accGlasses,
    beard: null,
    layout,
  };

  /**
   * Pick real solved frames by the phase they actually reached, rather than
   * computing which frame *ought* to hold a phase. If the solver and the rig
   * ever disagree about how fast the cycle runs, this sheet shows it instead
   * of hiding it behind arithmetic that assumes they agree.
   */
  const pickByPhase = (want) => {
    let best = track.frames[0];
    let bestErr = Infinity;
    for (const f of track.frames) {
      if (!f.moving) continue;
      const d = Math.abs(((f.phase - want + 1.5) % 1) - 0.5);
      if (d < bestErr) {
        bestErr = d;
        best = f;
      }
    }
    return best;
  };

  const cols = 4;
  const cellW = width / cols;
  const rowY = [height * 0.47, height * 0.95];

  const cells = [];
  for (let i = 0; i < 8; i++) {
    const phase = i / 8;
    const m = pickByPhase(phase);
    cells.push(
      <g key={i} transform={`translate(${(i % cols) * cellW + cellW / 2} ${rowY[Math.floor(i / cols)]})`}>
        <Character m={{...m, x: 0, y: 0, facingScale: 1}} look={look} scale={CELL_SCALE} />
        <text x={0} y={30} fontSize={20} fill="#8a7f70" textAnchor="middle" fontFamily="monospace">
          {`${phase.toFixed(3)} ${m.phase.toFixed(3)}`}
        </text>
      </g>
    );
  }

  const live = track.at(frame);

  return (
    <AbsoluteFill style={{backgroundColor: '#f2ece1'}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <rect x={0} y={0} width={width} height={height} fill="#f2ece1" />
        {[rowY[0], rowY[1]].map((y, i) => (
          <line key={i} x1={0} y1={y} x2={width} y2={y} stroke="#d6cbb8" strokeWidth={2} />
        ))}
        {cells}
      </svg>
    </AbsoluteFill>
  );
};

/** One character, standing still, as large as the frame allows. */
export const RigPortrait = () => {
  const {width, height} = useVideoConfig();
  const frame = useCurrentFrame();
  const pack = getPack('ink-street');

  const track = useMemo(
    () => solveLocomotion([{t: 0, x: 0}, {t: 120, x: 0}], {fps: FPS, walkStride: 500}),
    []
  );
  const m = track.at(frame);
  const look = {
    palette: pack.palettes.a,
    hair: headAfro,
    face: faceCalm,
    accessory: accGlasses,
    beard: null,
    layout,
  };
  const scale = (height * 0.86) / 1000;
  return (
    <AbsoluteFill style={{backgroundColor: '#f2ece1'}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <rect x={0} y={0} width={width} height={height} fill="#f2ece1" />
        <line x1={0} y1={height * 0.93} x2={width} y2={height * 0.93} stroke="#d6cbb8" strokeWidth={3} />
        <g transform={`translate(${width / 2} ${height * 0.93})`}>
          <Character m={{...m, x: 0, y: 0}} look={look} scale={scale} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};
