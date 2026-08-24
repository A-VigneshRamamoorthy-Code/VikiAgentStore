import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

import {solveLocomotion} from '../lib/locomotion';
import {HumaaansCharacter, humaaansStride, prepareBottom} from '../components/Humaaans.jsx';
import {StreetSet, StreetForeground} from '../components/Sets.jsx';
import {getPack} from '../lib/packs';

import headCurly from '../../../assets/packs/humaaans/head/Curly.json';
import headBeard from '../../../assets/packs/humaaans/head/Short-Beard.json';
import headTurban from '../../../assets/packs/humaaans/head/Turban-1.json';
import headPony from '../../../assets/packs/humaaans/head/Pony.json';
import bodyJacket from '../../../assets/packs/humaaans/body/Jacket.json';
import bodyHoodie from '../../../assets/packs/humaaans/body/Hoodie.json';
import bodyLong from '../../../assets/packs/humaaans/body/Long-Sleeve.json';
import bodyTrench from '../../../assets/packs/humaaans/body/Trench-Coat.json';
import bottomSweats from '../../../assets/packs/humaaans/bottom/Sweatpants.json';

/**
 * Crosstown — fifteen seconds of Humaaans, to prove the second asset pack.
 *
 * The point of this film is not the story, it is that a whole second art
 * library drops onto the same locomotion solver without the physics being
 * re-derived or the staging re-tuned. Everything that decides where a foot
 * lands is shared with the Peeps films; only the drawing is new.
 *
 * As before, no path below says which way anybody is facing. A negative speed
 * is a fact about travel, and the rig works the rest out — which is why a
 * character in here cannot moonwalk, whatever the paths are edited to say.
 */

const FPS = 30;
export const CROSSTOWN_DURATION = 15 * FPS;

/**
 * Humaaans stand 426 units tall against the Peeps rig's ~1010, so the scale
 * that fills the same amount of frame is completely different. Asking the
 * component for its own stride rather than hardcoding one is what keeps this
 * honest: change the proportions and the staging follows.
 */
const SCALE = 0.95;

const WALK = humaaansStride(SCALE, 'walk') * 1.0;
const RUN = humaaansStride(SCALE, 'run') * 1.15;

/**
 * One leg shape for the whole cast, skinned to each character's own bones.
 *
 * Prepared once at module scope: it parses SVG path data, which is not work to
 * repeat sixty times a second. Reusing a single pair of legs across the cast is
 * what the artist does too -- Sprint is one leg drawn once and rotated.
 */
const LEGS = prepareBottom(bottomSweats);

const CAST = {
  maya: {head: headCurly, body: bodyJacket, palette: 'a'},
  omar: {head: headBeard, body: bodyHoodie, palette: 'b'},
  sam: {head: headTurban, body: bodyLong, palette: 'c'},
  nia: {head: headPony, body: bodyTrench, palette: 'd'},
};

const look = (pack, id) => {
  const c = CAST[id];
  return {palette: pack.palettes[c.palette], head: c.head, body: c.body, bottom: LEGS};
};

const S = (sec) => Math.round(sec * FPS);

const seg = (keys, dur, speed, ease) => {
  const last = keys[keys.length - 1];
  keys.push({t: last.t + S(dur), x: last.x + speed * dur, ease});
  return keys;
};

/**
 * Maya: walks on, stops when she spots Omar, runs to catch her train, then
 * settles back to a walk. The last leg is not decoration — a film that ends
 * mid-sprint ends because it ran out of frames, and it reads that way.
 */
const MAYA_PATH = (() => {
  const k = [{t: 0, x: -420, ease: 'creep'}];
  seg(k, 4.2, WALK, 'easeOut');
  seg(k, 1.4, 0, 'linear');
  seg(k, 1.6, WALK * 0.85, 'easeInOut');
  seg(k, 5.6, RUN, 'easeIn');
  seg(k, 2.2, WALK * 0.9, 'easeOut');
  return k;
})();

/** Omar crosses the other way so the two of them pass mid-frame. */
const OMAR_PATH = (() => {
  const k = [{t: 0, x: 2150, ease: 'creep'}];
  seg(k, 1.2, 0, 'linear');
  seg(k, 8.0, -WALK * 0.9, 'easeInOut');
  seg(k, 1.5, 0, 'linear');
  seg(k, 6.0, -WALK * 0.75, 'easeIn');
  return k;
})();

/** Sam is scenery with a pulse — a short beat further up the street. */
const SAM_PATH = (() => {
  const k = [{t: 0, x: 1250}];
  seg(k, 4.0, WALK * 0.5, 'easeInOut');
  seg(k, 1.6, 0, 'linear');
  seg(k, 4.0, -WALK * 0.5, 'easeInOut');
  seg(k, 7.0, WALK * 0.45, 'easeInOut');
  return k;
})();

/**
 * Nia is further down the street, and exists because of what the back half of
 * the film looked like without her: Maya running through an empty set, with
 * nothing to measure the speed against. A runner is only fast relative to
 * something. She is overtaken near the end, which is that measurement.
 */
const NIA_PATH = (() => {
  const k = [{t: 0, x: 4750}];
  seg(k, 9.0, 0, 'linear');
  seg(k, 6.0, WALK * 0.45, 'easeInOut');
  return k;
})();

export const Crosstown = ({packId = 'humaaans-city'}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const pack = getPack(packId);
  const groundY = height * pack.ground;

  const tracks = useMemo(() => {
    const opts = {
      fps: FPS,
      walkStride: humaaansStride(SCALE, 'walk'),
      runStride: humaaansStride(SCALE, 'run'),
      idleBelow: 0.35,
      runAbove: (RUN * 0.5) / FPS,
      turnFrames: 7,
    };
    return {
      maya: solveLocomotion(MAYA_PATH, opts),
      omar: solveLocomotion(OMAR_PATH, {...opts, initialFacing: -1}),
      sam: solveLocomotion(SAM_PATH, opts),
      nia: solveLocomotion(NIA_PATH, opts),
    };
  }, []);

  const maya = tracks.maya.at(frame);
  const omar = tracks.omar.at(frame);
  const sam = tracks.sam.at(frame);
  const nia = tracks.nia.at(frame);

  // Trails Maya and leads her: more room ahead of where she faces than behind.
  const camTrack = useMemo(() => {
    const out = [];
    let c = tracks.maya.frames[0].x - width * 0.42;
    for (const f of tracks.maya.frames) {
      const want = f.x - width * (f.facing > 0 ? 0.36 : 0.64);
      // Snappier than the walking films: a smoothing that flatters a stroll
      // lags half a second behind a run, which crowds the runner against the
      // edge she is running towards -- the opposite of leading her.
      c += (want - c) * 0.075;
      out.push(c);
    }
    return out;
  }, [tracks, width]);

  const cam = camTrack[Math.min(frame, camTrack.length - 1)];
  const drift = Math.sin(frame / 210) * 12;

  const put = (m, id, scale = SCALE, lift = 0) => (
    <HumaaansCharacter
      m={{...m, x: m.x - cam, y: groundY + lift}}
      look={look(pack, id)}
      scale={scale}
    />
  );

  return (
    <AbsoluteFill style={{backgroundColor: pack.sky[1]}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <StreetSet pack={pack} camX={cam + drift} W={width} Hgt={height} seed={23} />

        {/* Upstage figures higher on the plate and smaller. Two people on one
            ground line at one size read as the same cut-out twice. */}
        <g opacity="0.94">{put(sam, 'sam', SCALE * 0.82, -26)}</g>
        <g opacity="0.94">{put(nia, 'nia', SCALE * 0.86, -22)}</g>
        {put(omar, 'omar', SCALE * 0.93, -12)}
        {put(maya, 'maya')}

        <StreetForeground pack={pack} camX={cam + drift} W={width} Hgt={height} />
      </svg>
    </AbsoluteFill>
  );
};
