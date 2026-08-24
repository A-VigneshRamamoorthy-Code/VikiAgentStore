import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

import {solveLocomotion} from '../lib/locomotion';
import {chart} from '../lib/timing';
import {settle} from '../lib/overlap';
import {HumaaansCharacter, humaaansStride, prepareBottom} from '../components/Humaaans.jsx';
import {MeadowSet, MeadowForeground, Blanket, Basket} from '../components/MeadowSet.jsx';
import {Butterflies, wanderPath} from '../components/Butterflies.jsx';
import {Dog, dogStride} from '../components/Dog.jsx';
import {getPack} from '../lib/packs';
import {
  FPS, DURATION_SEC, ADULT, CHILD, DOG_S,
  ARRIVE, SIT_IN, SIT_OUT, NOTICE, LAUNCH, SKID,
  BLANKET_X, S, picnicPaths,
} from './picnic.paths.js';

import headCurly from '../../../assets/packs/humaaans/head/Curly.json';
import headBeard from '../../../assets/packs/humaaans/head/Short-Beard.json';
import headPony from '../../../assets/packs/humaaans/head/Pony.json';
import bodyJacket from '../../../assets/packs/humaaans/body/Jacket.json';
import bodyHoodie from '../../../assets/packs/humaaans/body/Hoodie.json';
import bodyTrench from '../../../assets/packs/humaaans/body/Trench-Coat.json';
import bottomSweats from '../../../assets/packs/humaaans/bottom/Sweatpants.json';

/**
 * The Picnic — eighteen seconds.
 *
 * ── Why this story ────────────────────────────────────────────────────────
 *
 * `DoublingBack` was a stress test: one figure, four joins, every one of them
 * a place a rig lies. This is the opposite exam. Nothing here is hard to
 * solve in isolation; what is hard is four bodies of three different builds
 * sharing one ground plane and one clock without any of them reading as a
 * sticker.
 *
 *     arrive  ->  settle  ->  eat  ->  the dog notices  ->  the chase
 *
 * The beats that matter are the quiet ones. Sitting down is where weight
 * either exists or does not. The meal is a held beat with four characters in
 * it, which is four chances to look like furniture. And the chase only reads
 * as fast because it follows three seconds of almost nothing.
 *
 * ── Craft applied (reference/motion-craft.md) ─────────────────────────────
 *
 *  - Contact poses are the only keys; the solver fills everything between.
 *  - Speed is contrast: adults amble, the child runs ahead, the dog is the
 *    fastest thing on screen — and the chase is staged AFTER the stillest
 *    part of the film, which is what actually makes it feel quick.
 *  - Asymmetric gravity everywhere: the sit cushions, the dog's bound falls
 *    faster than it rises, the butterflies climb decelerating and drop
 *    accelerating.
 *  - Overlap: the four heads nod out of phase while eating, because a family
 *    that chews in unison is a chorus line.
 *  - Anticipation: the dog crouches backwards before it launches, and the
 *    camera drifts left before it swings right.
 *  - Linear staging: only one thing moves at a time. The family goes still
 *    before the butterflies arrive, and stays still through the chase.
 */

export const PICNIC_DURATION = DURATION_SEC * FPS;

const WALK = humaaansStride(ADULT, 'walk');
const KID_WALK = humaaansStride(CHILD, 'walk');
const KID_RUN = humaaansStride(CHILD, 'run');
const DOG_TROT = dogStride(DOG_S, 'trot');
const DOG_BOUND = dogStride(DOG_S, 'bound');

const LEGS = prepareBottom(bottomSweats);

const CAST = {
  mum: {head: headCurly, body: bodyJacket, palette: 'a'},
  dad: {head: headBeard, body: bodyTrench, palette: 'b'},
  kid: {head: headPony, body: bodyHoodie, palette: 'c'},
};

const look = (pack, id) => {
  const c = CAST[id];
  return {
    palette: pack.palettes[c.palette],
    head: c.head, body: c.body, bottom: LEGS,
  };
};

/**
 * Sitting down, 0 standing to 1 seated.
 *
 * `cushion` and not a linear ramp, because a body lowering itself is not a
 * lift descending. It commits, drops most of the way under gravity, and then
 * the legs catch the last of it — the deceleration at the bottom is the only
 * evidence on screen that the character has any weight at all.
 *
 * `settle` adds the small compression that follows. Two frames of it. Take it
 * out and the figure arrives at the ground like a decal being placed.
 */
const sitAmount = (frame, inSec, outSec) => {
  const a = S(inSec);
  const b = S(outSec);
  if (frame <= a) return 0;
  if (frame >= b) return 1 + settle(frame - b, {period: 8, decay: 0.3}) * 0.035;
  return chart('cushion', (frame - a) / (b - a));
};

/**
 * Every path, from the module the validator also reads.
 *
 * Stride lengths are measured off the rigs here and handed in, because the
 * paths module is plain JS so that Node can run it without Remotion.
 */
const {mum: MUM_PATH, dad: DAD_PATH, kid: KID_PATH, dog: DOG_PATH} = picnicPaths({
  WALK, KID_WALK, KID_RUN, DOG_TROT, DOG_BOUND,
});

/**
 * The butterflies' mean path.
 *
 * A slow loop that drifts right once the chase starts. The loop is what the
 * dog overshoots; without it the insects would simply outrun him in a
 * straight line and the joke would be a race.
 */
const butterflyPath = (groundY) => {
  const wander = wanderPath({
    cx: BLANKET_X + 620,
    cy: groundY - 250,
    rx: 210,
    ry: 120,
    hz: 0.15,
    tilt: -0.15,
  });
  return (t) => {
    const p = wander(t);
    // They enter from off right, come in to the family, then lead the dog away.
    const enter = -Math.max(0, 1 - Math.max(0, t - 6.2) / 2.6) * 900;
    const flee = Math.max(0, t - LAUNCH) * 118;
    const climb = -Math.max(0, t - LAUNCH - 2.4) * 46;
    return [p[0] + enter + flee, p[1] + climb];
  };
};

export const Picnic = ({packId = 'humaaans-meadow'}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const pack = getPack(packId);
  const groundY = height * pack.ground;
  const t = frame / FPS;

  /**
   * Framing, derived from the ground line exactly as in `DoublingBack`: a
   * 9:16 crop has nearly twice the sky above the same horizon, so a single
   * typed-in scale frames one aspect well and leaves the other empty.
   *
   * A meadow needs more of it than a street does. A skyline fills the top of
   * a frame by itself; a hedge and some hills do not, and shot flat this was
   * two-thirds empty sky with a strip of picnic along the bottom.
   *
   * `visW` is the consequence nobody remembers: once the scene is scaled, the
   * camera is no longer working in screen pixels. A lead of `width * 0.4`
   * asks for 768 units of a frame that is only showing 1280 of them, and the
   * subject leaves on the wrong side. Every camera offset below is a fraction
   * of what is actually VISIBLE.
   */
  const SKY_WORLD = (1080 * pack.ground) / 1.5;
  const FRAME = Math.max(1, groundY / SKY_WORLD);
  const visW = width / FRAME;
  const fx = width / 2;
  const fy = groundY;
  /**
   * The scale-up happens about the CENTRE of the frame, not its left edge, so
   * the visible world window does not start at the camera -- it starts half a
   * frame's worth of shrinkage to the right of it. Solving `cam` without that
   * term put every shot a constant 320 world units off, which is why the cast
   * spent the whole film piled against the left edge with the right half of
   * the screen empty. Framing is arithmetic; it was never a staging choice.
   *
   * `shot(x, f)` is the camera that puts world x at fraction f across.
   */
  const PAD = (width - visW) / 2;
  const shot = (x, f) => x - visW * f - PAD;

  const tracks = useMemo(() => {
    const human = {
      fps: FPS,
      walkStride: humaaansStride(ADULT, 'walk'),
      runStride: humaaansStride(ADULT, 'run'),
      idleBelow: 0.35,
      runAbove: (humaaansStride(ADULT, 'run') * 0.5) / FPS,
      turnFrames: 8,
    };
    const kid = {
      ...human,
      walkStride: KID_WALK,
      runStride: KID_RUN,
      runAbove: (KID_RUN * 0.46) / FPS,
      turnFrames: 6,          // a lighter body turns faster
    };
    const dog = {
      ...human,
      walkStride: DOG_TROT,
      runStride: DOG_BOUND,
      runAbove: (DOG_BOUND * 0.42) / FPS,
      turnFrames: 5,
    };
    return {
      mum: solveLocomotion(MUM_PATH, human),
      dad: solveLocomotion(DAD_PATH, human),
      kid: solveLocomotion(KID_PATH, kid),
      dog: solveLocomotion(DOG_PATH, dog),
    };
  }, []);

  /**
   * The camera.
   *
   * It holds on the blanket for the whole meal — a camera that keeps nudging
   * during a still beat destroys the stillness the chase is being measured
   * against — and only starts leading again when the dog goes.
   *
   * The launch frame is FOUND, not typed: the pass below looks for where the
   * dog's speed crosses into a run. Retime the chase and the camera retimes
   * with it. Before that frame it drifts the wrong way, so the swing right is
   * a release rather than a reaction.
   */
  const camTrack = useMemo(() => {
    const d = tracks.dog.frames;
    const fast = (DOG_BOUND * 0.7) / FPS;

    let goAt = -1;
    for (let i = S(NOTICE); i < d.length; i++) {
      if (d[i].speed > fast) {
        goAt = i;
        break;
      }
    }

    const ANTICIPATE = S(0.9);
    const AMOUNT = visW * 0.05;

    const out = [];
    let c = shot(BLANKET_X, 0.58);
    for (let i = 0; i < d.length; i++) {
      const chasing = goAt > 0 && i > goAt - S(0.3) && i < S(SKID);

      /**
       * Three framings, not two.
       *
       * Before the chase the camera watches the blanket, sat left of centre so
       * there is room on screen for four characters to walk IN — a subject
       * centred at rest has nowhere to enter from. During the chase it leads
       * the dog. And after the skid it pulls back to the midpoint between the
       * dog and the family, so the film ends on both of them.
       *
       * That last one is not decoration. Ending on the camera's last subject
       * left the picnic off screen entirely and closed the film on an empty
       * field with a dog in it.
       */
      let want;
      if (chasing) {
        want = shot(d[i].x, d[i].facing > 0 ? 0.38 : 0.62);
      } else if (goAt > 0 && i >= S(SKID)) {
        want = shot((BLANKET_X + d[i].x) / 2, 0.5);
      } else {
        want = shot(BLANKET_X, 0.58);
      }

      if (goAt > 0 && i < goAt && i > goAt - ANTICIPATE) {
        const u = (i - (goAt - ANTICIPATE)) / ANTICIPATE;
        want -= AMOUNT * chart('accel', u);
      }

      // The recovery has ground to make up and only a couple of seconds to do
      // it in, so it is the quickest of the three.
      c += (want - c) * (chasing ? 0.05 : goAt > 0 && i >= S(SKID) ? 0.075 : 0.03);
      out.push(c);
    }
    return out;
  }, [tracks, visW]);

  const cam = camTrack[Math.min(frame, camTrack.length - 1)];
  const drift = Math.sin(frame / 240) * 9;

  const mum = tracks.mum.at(frame);
  const dad = tracks.dad.at(frame);
  const kid = tracks.kid.at(frame);
  const dog = tracks.dog.at(frame);

  /**
   * Eating.
   *
   * A small forward nod on a slow cycle, with each character on a different
   * period AND a different phase. Shared timing is the single loudest tell
   * that a crowd is one puppet copied — the course calls it moving in unison
   * and it is worth avoiding for the price of three magic numbers.
   */
  const meal = Math.max(0, Math.min(1, (t - SIT_OUT) / 0.8)) * Math.max(0, Math.min(1, (16.6 - t) / 1.2));
  const nod = (period, phase, amp) => Math.sin((t / period + phase) * Math.PI * 2) * amp * meal;

  const sitM = sitAmount(frame, SIT_IN + 0.15, SIT_OUT + 0.15);
  const sitD = sitAmount(frame, SIT_IN + 0.4, SIT_OUT + 0.4);
  const sitK = sitAmount(frame, SIT_IN - 0.3, SIT_OUT - 0.35);

  const put = (m, id, scale, sit, lift = 0, extraLean = 0) => (
    <HumaaansCharacter
      m={{...m, x: m.x - cam, y: groundY + lift, lean: m.lean + extraLean}}
      look={look(pack, id)}
      scale={scale}
      sit={sit}
    />
  );

  const bPath = useMemo(() => butterflyPath(groundY), [groundY]);

  return (
    <AbsoluteFill style={{backgroundColor: pack.sky[1]}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <g transform={`translate(${fx} ${fy}) scale(${FRAME}) translate(${-fx} ${-fy})`}>
          <MeadowSet pack={pack} camX={cam + drift} W={width} Hgt={height} seed={23} />

          {/* The blanket is world geometry, so it moves with the camera like
              everything else. Anything pinned to the screen during a pan is
              the one thing the eye will notice. */}
          <g transform={`translate(${(-cam).toFixed(2)} 0)`}>
            <Blanket x={BLANKET_X} ground={groundY + 6} w={660} s={1} look={pack.world} />
            <Basket x={BLANKET_X + 232} ground={groundY - 2} s={0.72} look={pack.world} />
          </g>

          {/* Upstage before downstage. Dad sits behind the blanket line, the
              child in front of it, which is what gives four figures on one
              ground plane any depth at all. */}
          {put(dad, 'dad', ADULT * 0.97, sitD, -26, nod(2.9, 0.0, 2.6))}
          {put(mum, 'mum', ADULT, sitM, -8, nod(3.4, 0.37, 2.2))}
          {put(kid, 'kid', CHILD, sitK, 10, nod(2.2, 0.71, 3.4))}

          <g transform={`translate(${(dog.x - cam).toFixed(2)} ${(groundY + 4).toFixed(2)})`}>
            <Dog
              m={{...dog, x: 0, y: 0}}
              scale={DOG_S}
              look={{
                body: '#f0e2cf',
                ear: '#b08a5f',
                nose: '#2b2b40',
                collar: pack.world.accent,
              }}
            />
          </g>

          <g transform={`translate(${(-cam).toFixed(2)} 0)`}>
            <Butterflies t={t} path={bPath} count={3} seed={5} scale={1.5}
                         look={{wing: '#f5c451', wingDark: '#e58b3a', body: '#3a2f2a'}} />
          </g>

          <MeadowForeground pack={pack} camX={cam + drift} W={width} Hgt={height} seed={23} />
        </g>
</svg>
    </AbsoluteFill>
  );
};

export const PicnicVertical = (props) => <Picnic {...props} />;
