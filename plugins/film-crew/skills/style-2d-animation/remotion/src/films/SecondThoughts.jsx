import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Sequence} from 'remotion';
import {Character, strideUnits, H as CH} from '../components/Character.jsx';
import {StreetSet, StreetForeground} from '../components/Sets.jsx';
import {solveLocomotion} from '../lib/locomotion.js';
import {getPack} from '../lib/packs.js';
import layout from '../../../assets/packs/peeps/layout.json';

import headAfro from '../../../assets/packs/peeps/head/Afro.json';
import headHat from '../../../assets/packs/peeps/head/HatHip.json';
import headBun from '../../../assets/packs/peeps/head/Bun.json';
import faceCalm from '../../../assets/packs/peeps/face/Calm.json';
import faceSmile from '../../../assets/packs/peeps/face/Smile.json';
import faceCheeky from '../../../assets/packs/peeps/face/Cheeky.json';
import faceAwe from '../../../assets/packs/peeps/face/Awe.json';
import accGlasses from '../../../assets/packs/peeps/accessory/Glasses.json';
import beardGoatee from '../../../assets/packs/peeps/beard/Goatee.json';

/**
 * "Second Thoughts" — 30 seconds, and every second of it is an argument.
 *
 * The film exists to prove the two things the previous generation of this
 * style got wrong, so it is staged around them rather than around a joke:
 *
 *  1. **A character turns around, on purpose, in the middle of a shot.** This
 *     is the exact move that produced a moonwalking figure in the last film:
 *     the author flipped a boolean meaning "they're leaving" and the drawing
 *     stopped agreeing with the direction of travel. Here nobody sets facing
 *     at all. The walk is a path; the pivot is a consequence.
 *
 *  2. **The cast is the same cast in every shot.** Faces are real illustration
 *     with fixed identities and fixed palettes, so there is nothing to drift.
 *
 * It also runs a gait change (walk into run) and a two-character pass, because
 * both are places where phase and facing are easy to get wrong and neither can
 * be checked from a single frame.
 */

const FPS = 30;
export const DURATION = 30 * FPS;

const SCALE = 0.42;                 // character height on a 1080-tall frame

/**
 * Speeds, not distances.
 *
 * These paths were originally written as "be at x=1750 by 6.5 seconds", and
 * every one of those numbers was silently wrong the moment the rig's stride
 * changed: the character still arrived on time, but at whatever cadence the
 * distance implied — which is how you get a stroll played at four steps a
 * second. Saying how FAST and for HOW LONG makes cadence the input and
 * position the consequence, so a change to the legs can never desynchronise
 * the staging again.
 *
 * One cycle per second is an unhurried walk; a run is nearer 1.5.
 */
const WALK = strideUnits(SCALE, 'walk') * 1.0;
const RUN = strideUnits(SCALE, 'run') * 1.5;

/* ── the cast ────────────────────────────────────────────────────────────── */

const CAST = {
  ada: {hair: headAfro, face: faceCalm, accessory: accGlasses, palette: 'a'},
  ben: {hair: headHat, face: faceSmile, beard: beardGoatee, palette: 'b'},
  cal: {hair: headBun, face: faceCheeky, palette: 'c'},
};

const look = (pack, id, faceOverride) => {
  const c = CAST[id];
  return {
    palette: pack.palettes[c.palette],
    hair: c.hair,
    face: faceOverride ?? c.face,
    beard: c.beard ?? null,
    accessory: c.accessory ?? null,
    layout,
  };
};

/* ── staging ─────────────────────────────────────────────────────────────── */

const S = (sec) => Math.round(sec * FPS);

/** Appends a leg of `dur` seconds travelled at `speed` units/second. */
const seg = (keys, dur, speed, ease) => {
  const last = keys[keys.length - 1];
  keys.push({t: last.t + S(dur), x: last.x + speed * dur, ease});
  return keys;
};

/**
 * Ada's path. Read it as a story and the physics falls out of it:
 * she walks on, stops dead, has second thoughts, goes back the way she came,
 * then breaks into a run when she realises she is late.
 *
 * Note what is NOT here: any mention of which way she is facing. A negative
 * speed is a fact about travel; the drawing works out the rest.
 */
const ADA_PATH = (() => {
  const k = [{t: 0, x: -600, ease: 'creep'}];
  seg(k, 6.0, WALK, 'easeOut');            // walks on, arrives, settles
  seg(k, 2.5, 0, 'linear');                // the stop — a dwell, so: idle pose
  seg(k, 3.5, -WALK * 0.92, 'easeInOut');  // turns, walks back the way she came
  seg(k, 2.0, 0, 'linear');                // second thoughts about the second thoughts
  seg(k, 6.0, RUN * 0.62, 'easeIn');       // gives up and runs for it
  seg(k, 10.0, RUN, 'creep');
  return k;
})();

/** Ben crosses the other way, so the two of them pass mid-frame. */
const BEN_PATH = (() => {
  const k = [{t: 0, x: 2350, ease: 'creep'}];
  seg(k, 2.0, 0, 'linear');
  seg(k, 11.0, -WALK * 0.88, 'easeInOut');
  seg(k, 3.0, 0, 'linear');
  seg(k, 14.0, -WALK * 0.80, 'easeIn');
  return k;
})();

/** Cal is scenery with a pulse: paces a short beat near the second bench. */
const CAL_PATH = (() => {
  const k = [{t: 0, x: 1500}];
  seg(k, 5.0, WALK * 0.55, 'easeInOut');
  seg(k, 2.0, 0, 'linear');
  seg(k, 5.0, -WALK * 0.55, 'easeInOut');
  seg(k, 2.0, 0, 'linear');
  seg(k, 6.0, WALK * 0.60, 'easeInOut');
  seg(k, 10.0, 0, 'linear');
  return k;
})();

export const SecondThoughts = ({packId = 'ink-street'}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const pack = getPack(packId);
  const groundY = height * pack.ground;

  // Solved once, not per frame: the whole point of an arc-length solution is
  // that it is a property of the path, not of the moment you ask about it.
  const tracks = useMemo(() => {
    const opts = {
      fps: FPS,
      walkStride: strideUnits(SCALE, 'walk'),
      runStride: strideUnits(SCALE, 'run'),
      idleBelow: 0.35,
      runAbove: (RUN * 0.5) / FPS,   // halfway between the two cadences
      turnFrames: 7,
    };
    return {
      ada: solveLocomotion(ADA_PATH, opts),
      ben: solveLocomotion(BEN_PATH, {...opts, initialFacing: -1}),
      cal: solveLocomotion(CAL_PATH, opts),
    };
  }, []);

  const ada = tracks.ada.at(frame);
  const ben = tracks.ben.at(frame);
  const cal = tracks.cal.at(frame);

  /* Camera: trails Ada and LEADS her — more room ahead of where she faces
     than behind — then smooths the result so the frame has some give in it.
     The previous version interpolated between a value and itself, which is a
     long way of writing "weld the camera to the subject", and reads on screen
     as a tripod bolted to a car. */
  const camTrack = useMemo(() => {
    const out = [];
    let c = tracks.ada.frames[0].x - width * 0.42;
    for (const f of tracks.ada.frames) {
      const want = f.x - width * (f.facing > 0 ? 0.36 : 0.64);
      c += (want - c) * 0.05;
      out.push(c);
    }
    return out;
  }, [tracks, width]);

  const cam = camTrack[Math.min(frame, camTrack.length - 1)];

  // A slow breath on the framing so a held shot is never dead.
  const drift = Math.sin(frame / 210) * 14;

  /* `lift` places a character further upstage: higher on the plate and
     smaller. Two figures on an identical ground line at an identical size
     read as one cut-out duplicated, however different their drawings are. */
  const put = (m, id, faceOverride, scale = SCALE, lift = 0) => (
    <Character
      m={{...m, x: m.x - cam, y: groundY + lift}}
      look={look(pack, id, faceOverride)}
      scale={scale}

    />
  );

  // Ada's expression follows the beat: calm, then caught out at the turn,
  // then determined once she runs.
  const adaFace =
    frame > S(20.2) ? faceCheeky : frame > S(8.4) && frame < S(12.6) ? faceAwe : faceCalm;

  return (
    <AbsoluteFill style={{backgroundColor: pack.sky[1]}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <StreetSet pack={pack} camX={cam + drift} W={width} Hgt={height} seed={11} />

        {/* Far figure sits behind the near cast, and smaller: depth is scale
            plus overlap, and skipping either flattens the street. */}
        <g opacity="0.92">{put(cal, 'cal', null, SCALE * 0.84, -30)}</g>
        {put(ben, 'ben', null, SCALE * 0.95, -14)}
        {put(ada, 'ada', adaFace)}

        <StreetForeground pack={pack} camX={cam + drift} W={width} Hgt={height} />
      </svg>
    </AbsoluteFill>
  );
};

/** The same film, in each pack, to prove a pack really does change the look. */
export const SecondThoughtsDusk = () => <SecondThoughts packId="dusk-park" />;
export const SecondThoughtsFlat = () => <SecondThoughts packId="flat-poster" />;
