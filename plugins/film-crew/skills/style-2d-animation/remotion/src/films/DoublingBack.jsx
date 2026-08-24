import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

import {solveLocomotion} from '../lib/locomotion';
import {chart} from '../lib/timing';
import {HumaaansCharacter, humaaansStride, prepareBottom} from '../components/Humaaans.jsx';
import {StreetSet, StreetForeground} from '../components/Sets.jsx';
import {getPack} from '../lib/packs';

import headCurly from '../../../assets/packs/humaaans/head/Curly.json';
import headBeard from '../../../assets/packs/humaaans/head/Short-Beard.json';
import headPony from '../../../assets/packs/humaaans/head/Pony.json';
import bodyJacket from '../../../assets/packs/humaaans/body/Jacket.json';
import bodyHoodie from '../../../assets/packs/humaaans/body/Hoodie.json';
import bodyTrench from '../../../assets/packs/humaaans/body/Trench-Coat.json';
import bottomSweats from '../../../assets/packs/humaaans/bottom/Sweatpants.json';

/**
 * Doubling Back — fifteen seconds, built to the rules in reference/motion-craft.md.
 *
 * ── Why this shot and not a prettier one ───────────────────────────────────
 *
 * The story is deliberately the one that is hardest to fake:
 *
 *     walk  ->  stop  ->  a held beat  ->  turn  ->  run back
 *
 * Every join in that chain is a place a rig lies. Stopping exposes whether
 * weight settles or the figure just freezes. The held beat exposes whether a
 * standing character is alive or is a parked cut-out. The turn exposes
 * whether facing is derived from travel or authored by hand -- authored
 * facing moonwalks here, visibly, every time. And the run exposes whether the
 * gait is a dial or a switch, because a switch teleports the planted foot on
 * the frame it flips.
 *
 * A film of people strolling politely past each other hides all four.
 *
 * ── Craft applied ─────────────────────────────────────────────────────────
 *
 *  - Contact poses are the only keys; everything between them is solved.
 *  - The bob is asymmetric -- falls accelerate, rises decelerate.
 *  - The head lags the shoulders by two frames (the chain principle).
 *  - The camera anticipates: it eases the opposite way before a reversal.
 *  - Linear staging: during the held beat the rest of the street goes quiet,
 *    so there is exactly one thing to look at.
 *  - Speed is contrast, not velocity: Ivo ambles the other way at a third her
 *    pace, and the run is fast relative to him.
 */

const FPS = 30;
export const DOUBLING_DURATION = 15 * FPS;

const SCALE = 0.95;
const WALK = humaaansStride(SCALE, 'walk');
const RUN = humaaansStride(SCALE, 'run') * 1.12;

const LEGS = prepareBottom(bottomSweats);

const CAST = {
  ada: {head: headCurly, body: bodyJacket, palette: 'a'},
  ivo: {head: headBeard, body: bodyHoodie, palette: 'b'},
  tess: {head: headPony, body: bodyTrench, palette: 'd'},
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

/* ── the beat ─────────────────────────────────────────────────────────────
 *
 * Named, because three separate things have to agree about when it happens:
 * Ada's path stops, the street quiets, and the camera stops leading. Three
 * copies of "about six seconds in" is how a beat drifts apart.
 */
const BEAT_IN = 5.9;
const BEAT_OUT = 7.5;

/**
 * Ada. The whole film is her changing her mind.
 *
 * The stop is `easeOut` rather than linear because a body arriving at rest
 * decelerates -- it does not run out of velocity like a clock running down.
 * The run is `easeIn` for the mirror-image reason.
 */
const ADA_PATH = (() => {
  const k = [{t: 0, x: -300, ease: 'creep'}];
  seg(k, 4.4, WALK, 'easeOut');        // on, with purpose
  seg(k, 1.5, 0, 'easeOut');           // she slows and stops
  seg(k, 1.6, 0, 'linear');            // the beat -- she has realised something
  seg(k, 1.1, -WALK * 0.55, 'easeIn'); // turns and starts back
  seg(k, 4.6, -RUN, 'easeIn');         // and now she is running
  seg(k, 1.8, -WALK * 0.9, 'easeOut'); // arrives, drops to a walk
  return k;
})();

/**
 * Ivo ambles the other way and never hurries.
 *
 * He is the measuring stick. "The higher the contrast, the higher the
 * perceived speed" -- Ada's run is only fast next to something slow, and an
 * empty street gives the eye nothing to compare against. He also stops during
 * the beat, because two moving things is two things to look at.
 */
const IVO_PATH = (() => {
  const k = [{t: 0, x: 1980, ease: 'creep'}];
  seg(k, BEAT_IN, -WALK * 0.42, 'easeInOut');
  seg(k, BEAT_OUT - BEAT_IN, 0, 'easeOut');   // quiet, for the beat
  seg(k, 15 - BEAT_OUT, -WALK * 0.5, 'easeIn');
  return k;
})();

/**
 * Tess is upstage scenery with a pulse, and she is also where Ada is running
 * back TO -- the film needs a reason on screen, even an unexplained one.
 */
const TESS_PATH = (() => {
  const k = [{t: 0, x: -1150}];
  seg(k, 4.0, WALK * 0.3, 'easeInOut');
  seg(k, 3.5, 0, 'easeOut');
  seg(k, 7.5, WALK * 0.22, 'easeInOut');
  return k;
})();

export const DoublingBack = ({packId = 'humaaans-city'}) => {
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
      turnFrames: 8,
    };
    return {
      ada: solveLocomotion(ADA_PATH, opts),
      ivo: solveLocomotion(IVO_PATH, {...opts, initialFacing: -1}),
      tess: solveLocomotion(TESS_PATH, opts),
    };
  }, []);

  /**
   * The camera, with anticipation.
   *
   * "Our camera is going to be moving to the right, so I shifted it slightly
   * to the left first as an extreme." A camera that simply chases its subject
   * is a camera nobody is operating; a real one settles back a beat before it
   * swings, and that tiny wrong-way drift is what makes the swing read as
   * intended rather than reactive.
   *
   * Ada reverses once, around the beat. Rather than hardcode when, the pass
   * below FINDS her reversal by looking at where her facing changes, then
   * eases a small opposing offset in over the second before it. Retime the
   * story and the camera retimes with it.
   */
  const camTrack = useMemo(() => {
    const f = tracks.ada.frames;

    // Where does she turn? Derived, never authored.
    let turnAt = -1;
    for (let i = 1; i < f.length; i++) {
      if (f[i].facing !== f[i - 1].facing) {
        turnAt = i;
        break;
      }
    }

    const ANTICIPATE = S(1.0);
    const AMOUNT = width * 0.055;

    const out = [];
    let c = f[0].x - width * 0.42;
    for (let i = 0; i < f.length; i++) {
      const lead = width * (f[i].facing > 0 ? 0.36 : 0.64);
      let want = f[i].x - lead;

      // Drift AGAINST the coming move, easing in over the last second before
      // it, so the camera is already loaded when she goes.
      if (turnAt > 0 && i < turnAt && i > turnAt - ANTICIPATE) {
        const u = (i - (turnAt - ANTICIPATE)) / ANTICIPATE;
        want += AMOUNT * chart('accel', u) * f[i].facing;
      }

      c += (want - c) * 0.075;
      out.push(c);
    }
    return out;
  }, [tracks, width]);

  const cam = camTrack[Math.min(frame, camTrack.length - 1)];
  const drift = Math.sin(frame / 210) * 12;

  const ada = tracks.ada.at(frame);
  const ivo = tracks.ivo.at(frame);
  const tess = tracks.tess.at(frame);

  const put = (m, id, scale = SCALE, lift = 0) => (
    <HumaaansCharacter
      m={{...m, x: m.x - cam, y: groundY + lift}}
      look={look(pack, id)}
      scale={scale}
    />
  );

  /**
   * Framing.
   *
   * Shot flat, the street occupies the bottom third and the top of frame is
   * empty sky -- a plate that is *correct* and badly composed. Scaling the
   * whole scene about the ground line fixes it without touching the set: the
   * horizon stays pinned, the skyline grows into the dead space, and because
   * the scale is greater than one the content still overruns all four edges,
   * so nothing can gap.
   *
   * The scale is DERIVED from the ground line rather than typed in, because a
   * 9:16 crop has nearly twice the sky of a 16:9 one above the same horizon.
   * A single hardcoded number frames the landscape cut well and leaves the
   * Short two-thirds empty -- which is exactly what it did before this was
   * computed.
   *
   * This is framing, not staging. Every ground contact is decided before it
   * gets here, so the camera cannot introduce a slide.
   */
  const SKY_WORLD = (1080 * pack.ground) / 1.16;
  const FRAME = Math.max(1, groundY / SKY_WORLD);
  const fx = width / 2;
  const fy = groundY;

  return (
    <AbsoluteFill style={{backgroundColor: pack.sky[1]}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <g transform={`translate(${fx} ${fy}) scale(${FRAME}) translate(${-fx} ${-fy})`}>
          <StreetSet pack={pack} camX={cam + drift} W={width} Hgt={height} seed={41} />

          {/* Upstage figures sit higher on the plate and smaller: two people on
              one ground line at one size read as the same cut-out twice. */}
          <g opacity="0.92">{put(tess, 'tess', SCALE * 0.84, -24)}</g>
          {put(ivo, 'ivo', SCALE * 0.93, -12)}
          {put(ada, 'ada')}

          <StreetForeground pack={pack} camX={cam + drift} W={width} Hgt={height} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

export const DoublingBackVertical = (props) => <DoublingBack {...props} />;
