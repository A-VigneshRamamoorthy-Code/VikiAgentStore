import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig, Audio, staticFile} from 'remotion';
import {PURSUIT as P} from './lib/palette.js';
import {boardSize, viewTransform} from './lib/anim.js';
import {Set as SetLayer, GROUND} from './sets/Sets.jsx';
import {Prop} from './props/Props.jsx';
import {Actors} from './actors/Actors.jsx';
import {PeepsActors} from './actors/PeepsActors.jsx';
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
const Shot = ({entry, lead = 0}) => {
  // A dissolving shot is mounted `lead` frames before its own cut so it can
  // fade up over the outgoing one. Those lead frames are not part of the shot,
  // so its clock is held at frame 0 through them -- the trace is never read
  // out of range and the shot still starts on its real first frame.
  const frame = Math.max(0, useCurrentFrame() - lead);
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

  // The cross-dissolve. A cut between two near-identical framings on one set
  // reads as a jump rather than as an edit -- the eye has nothing to re-anchor
  // on, so the slow zoom appears to snap backwards. Fading the incoming shot
  // up over the outgoing one gives it that anchor. Set changes stay hard cuts,
  // because there the new geography *is* the anchor.
  const raw = useCurrentFrame();
  const opacity = lead > 0 ? Math.min(1, (raw + 1) / (lead + 1)) : 1;

  return (
    <AbsoluteFill style={{backgroundColor: P.sky, overflow: 'hidden', opacity}}>
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

          {/* Which rig draws the cast is the board's call, the same way the
              broadcast furniture is. A board of distant figures wants the
              traced cels; a board that holds on two faces for three minutes
              wants the illustrated rig, and says so. */}
          {board.cast_art === 'peeps'
            ? <PeepsActors shotId={entry.id} frame={frame} fps={fps} />
            : <Actors shotId={entry.id} frame={frame} />}

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

const broadcast = board.broadcast || null;

/** Frames a same-set cut is softened over. Long enough to read as an edit
 *  rather than a jump, short enough that it is not a scene transition. */
const DISSOLVE = 8;

/** How far the framing may change before a cut is left hard.
 *
 *  A dissolve is the answer to a cut the eye cannot read as an edit, which is
 *  a cut between two nearly identical framings -- there the slow drift appears
 *  to snap backwards because nothing else in the picture has changed. It is
 *  the wrong answer to an insert. Cutting from a wide room to a close-up of a
 *  prop on the floor is already legible as an edit, and fading between two
 *  images at twice each other's magnification only makes both of them muddy.
 */
const SOFT_RATIO = 1.35;

const startZoom = (id) => (byId[id]?.camera?.zoom ?? [1])[0];
const endZoom = (id) => {
  const z = byId[id]?.camera?.zoom ?? [1];
  return z[z.length - 1];
};

export const Pursuit = () => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const t = frame / fps;

  // Each shot runs to the frame the next one starts on. Rounding the start and
  // the *duration* independently -- which is the obvious way to write this --
  // disagrees with itself whenever a shot boundary lands mid-frame, and leaves
  // a one-frame hole that renders as a black flash. Eleven of these opened on
  // a fifty-one shot board. Deriving the length from the neighbouring cuts
  // cannot leave a gap, because there is only one clock.
  const cuts = timeline.shots.map((s) => Math.round(s.start * fps));
  const last = timeline.shots[timeline.shots.length - 1];
  const ends = cuts.slice(1).concat([Math.round(last.end * fps)]);

  return (
    <AbsoluteFill style={{backgroundColor: P.ink}}>
      {timeline.shots.map((entry, i) => {
        const prev = i > 0 ? timeline.shots[i - 1] : null;
        const a = prev ? endZoom(prev.id) : 0;
        const b = startZoom(entry.id);
        const ratio = a > 0 && b > 0 ? Math.max(a / b, b / a) : Infinity;
        const soft = prev && prev.set === entry.set && ratio <= SOFT_RATIO;
        const lead = soft ? Math.min(DISSOLVE, Math.max(0, cuts[i] - cuts[i - 1] - 2)) : 0;
        const from = cuts[i] - lead;
        const durationInFrames = Math.max(1, ends[i] - from);
        return (
          <Sequence key={entry.id} from={from} durationInFrames={durationInFrames} name={entry.id}>
            <Shot entry={entry} lead={lead} />
          </Sequence>
        );
      })}

      {/* Broadcast furniture rides above every cut, because it belongs to the
          channel rather than to any shot -- so it is the board that asks for
          it, not the component. A film that is not a news bulletin sets no
          `broadcast` key and gets no clock, no logo bug and no location tag. */}
      {broadcast && (
        <>
          <LiveClock t={t} />
          <ChannelMark />
          {broadcast.location && <LocationTag text={broadcast.location} />}
        </>
      )}
    </AbsoluteFill>
  );
};
