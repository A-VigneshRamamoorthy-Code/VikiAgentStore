import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig, Audio, staticFile} from 'remotion';
import {PURSUIT as P} from './lib/palette.js';
import {boardSize, viewTransform} from './lib/anim.js';
import {Set as SetLayer, GROUND} from './sets/Sets.jsx';
import {Prop} from './props/Props.jsx';
import {Actors} from './actors/Actors.jsx';
import {ChannelMark, LiveClock, LocationTag, MapInset, NewsLower, TrackingRing} from './overlays/Overlays.jsx';

import board from '../data/board.json';
import timeline from '../data/timeline.json';
import cameraWide from './generated/camera.json';
import cameraTall from './generated/camera_v.json';

/**
 * The film.
 *
 * `board.json` is the same file the Python engine renders, and the shot times
 * come from that engine's own resolver rather than being re-derived here --
 * the board states them symbolically ("l8.end+0.3") against narration audio, so
 * re-deriving them would make the two renders quietly disagree about *when*
 * while we were trying to compare *what*.
 *
 * The camera is read from `generated/camera.json` for the same reason, one
 * entry per frame. `track`, `pan` and `whip` are the *same* interpolation in
 * the engine; what separates them is a default easing curve, a `hold` and
 * `pre_hold` settle carved out of the span before easing, a pass that
 * silently refuses mechanical eases, a seeded handheld noise table, and a
 * `follow` mode that depends on where an actor actually is. Reimplementing
 * that was five chances to be almost right, and measurably was: every
 * `push`/`none` shot scored under MAE 5 while every `track`/`whip`/`handheld`
 * shot scored 12-19. Replaying it is exact and costs 137 kB.
 */

const byId = Object.fromEntries(board.shots.map((s) => [s.id, s]));

/** One shot. Inside a <Sequence>, frame 0 is the cut, which is what stepping wants. */
const Shot = ({entry}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const shot = byId[entry.id] ?? {};
  const board3 = boardSize(width, height);
  const pxPerUnit = Math.max(width, height) / 100;

  const dur = entry.end - entry.start;

  // Two clocks, deliberately. The camera runs on every frame; poses run on the
  // shot's `on` value. Quantising both is the classic mistake -- it turns a
  // stylistic choice into a broken render, because a stepped camera reads as
  // dropped frames rather than as animation. Both come out of the trace, so
  // the split is the engine's rather than an approximation of it, and an `on`
  // that changes *inside* a shot is carried correctly.
  // The vertical cut is not a crop. `SCENE_LONG` sits on the *long* edge, so
  // at 9:16 the board is 56.25 x 100 and the solver returns a different view
  // rect for the same shot -- reusing the 16:9 trace would silently reframe
  // every composition. Two traces, chosen by the canvas.
  const camera = height > width ? cameraTall : cameraWide;
  const cam = camera.shots[entry.id];
  const f = Math.min(frame, cam.frames.length - 1);
  const [cx, cy, zoom, vw, vh, blur, tPose, frac, tLocal] = cam.frames[f];
  const view = {cx, cy, zoom, w: vw, h: vh, blur, anchor: cam.anchor};
  const transform = viewTransform(view, board3, pxPerUnit);

  const ground = shot.set === 'aerial' ? null : GROUND;

  return (
    <AbsoluteFill style={{backgroundColor: P.sky, overflow: 'hidden'}}>
      <AbsoluteFill style={{transform, transformOrigin: '0 0'}}>
        <svg width={board3.w * pxPerUnit} height={board3.h * pxPerUnit}
             viewBox={`0 0 ${board3.w} ${board3.h}`}
             style={{position: 'absolute', left: 0, top: 0, overflow: 'visible',
                     shapeRendering: 'geometricPrecision'}}>
          {/* The set runs on the *true* shot clock, not the pose clock:
              rotors, flashing lights and traffic live on their own timing and
              `sets.py` owns their rate. Feeding it the quantised time steps
              the scenery with the characters, which is exactly the judder the
              two-clock split exists to avoid. */}
          <SetLayer name={shot.set} shotId={entry.id} view={view}
                    board={board3} t={tLocal} />

          {(shot.props ?? []).map((p, i) => {
            const at = p.at ?? [50, ground ?? 28];
            const s = p.scale ?? 1;
            return (
              <g key={`${p.kind}-${i}`} transform={`translate(${at[0]} ${at[1]}) scale(${s})`}>
                <Prop shot={entry.id} index={i} tPose={tPose} tLocal={tLocal} />
              </g>
            );
          })}

          <Actors shotId={entry.id} frame={frame} />

        </svg>
      </AbsoluteFill>

      {shot.overlay?.kind === 'circle' && (
        <TrackingRing t={tLocal} label={shot.overlay.label} x={50} y={30} r={14} />
      )}
      {shot.overlay?.kind === 'chyron' && (
        <NewsLower t={tLocal} dur={dur} kicker="BREAKING" headline={shot.overlay.text} />
      )}
      {shot.overlay?.kind === 'map' && (
        <MapInset t={tLocal} marker={shot.overlay.marker} />
      )}
    </AbsoluteFill>
  );
};

export const Pursuit = () => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const t = frame / fps;

  return (
    <AbsoluteFill style={{backgroundColor: P.ink}}>
      {timeline.shots.map((entry) => {
        const from = Math.round(entry.start * fps);
        const durationInFrames = Math.max(1, Math.round((entry.end - entry.start) * fps));
        return (
          <Sequence key={entry.id} from={from} durationInFrames={durationInFrames} name={entry.id}>
            <Shot entry={entry} />
          </Sequence>
        );
      })}

      {/* Broadcast furniture rides above every cut, because it belongs to the
          channel rather than to any shot. */}
      <LiveClock t={t} />
      <ChannelMark />
      <LocationTag text="CITY WEST" />
    </AbsoluteFill>
  );
};
