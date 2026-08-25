import React, {useMemo} from 'react';
import {Figure} from './peeps/Figure.jsx';
import layout from './peeps/assets/layout.json';

import headLongBangs from './peeps/assets/head/LongBangs.json';
import headGrayShort from './peeps/assets/head/GrayShort.json';
import faceCute from './peeps/assets/face/Cute.json';
import faceAwe from './peeps/assets/face/Awe.json';
import faceBigSmile from './peeps/assets/face/BigSmile.json';
import faceConcerned from './peeps/assets/face/Concerned.json';
import faceOld from './peeps/assets/face/Old.json';
import faceSolemn from './peeps/assets/face/Solemn.json';
import faceCalm from './peeps/assets/face/Calm.json';
import beardFullMax from './peeps/assets/beard/FullMax.json';

import bRestTee from './peeps/assets/body/RestingColorTee.json';
import bRestPants from './peeps/assets/body/RestingColorPants.json';
import bCrossTee from './peeps/assets/body/CrossArmColorTee.json';
import bCrossPants from './peeps/assets/body/CrossArmColorPants.json';
import bPointPants from './peeps/assets/body/PointingFingerColorPants.json';

import plan from '../generated/cast.json';

/**
 * Actors, drawn rather than solved.
 *
 * This layer has now been round the houses twice, and both trips are worth
 * recording because they were the same mistake at different scales.
 *
 * First the board gave every figure a walk cycle and nowhere to go, so they
 * scissored their legs on the spot. That was fixed by giving them somewhere to
 * go. Then the fix itself was the problem: a rig that solves a body out of
 * primitives is animating *constantly* -- limbs, lean, bob, squash -- and a
 * quiet, dialogue-led film does not want a character who is never still.
 *
 * So nothing is solved any more. The pack ships sixty-one bodies already drawn
 * in different attitudes; a character is one of those drawings, moved as a
 * whole and swapped for another drawing when the story needs a new attitude.
 * That is cut-out animation, and it is the honest form for this material: the
 * audience reads a pose change as a beat, and reads stillness as attention.
 *
 * It also means every frame of every character is line-for-line what Pablo
 * Stanley drew. Nothing in here invents anatomy.
 */

const HEADS = {LongBangs: headLongBangs, GrayShort: headGrayShort};
const FACES = {
  Cute: faceCute, Awe: faceAwe, BigSmile: faceBigSmile,
  Concerned: faceConcerned, Old: faceOld, Solemn: faceSolemn, Calm: faceCalm,
};
const BEARDS = {FullMax: beardFullMax};
const BODIES = {
  RestingColorTee: bRestTee, RestingColorPants: bRestPants,
  CrossArmColorTee: bCrossTee, CrossArmColorPants: bCrossPants,
  PointingFingerColorPants: bPointPants,
};

const look = (id, faceOverride) => {
  const c = plan.cast[id];
  return {
    palette: c.palette,
    hair: HEADS[c.hair],
    face: FACES[faceOverride ?? c.face] ?? FACES[c.face],
    beard: c.beard ? BEARDS[c.beard] : null,
    layout,
  };
};

/**
 * Which drawing a character stands in, for a named attitude.
 *
 * The pack's "Color" naming says a garment is recolourable but not *which*
 * one -- `ShirtColorTee` leaves the tee to be painted, `RestingColorTee`
 * leaves the trousers -- and, worse, the sixty-one bodies are sixty-one
 * *outfits* rather than one outfit in sixty-one attitudes. Choosing them by
 * pose name puts a character in a button shirt in one shot, a t-shirt in the
 * next and a jacket over a tee in the third, which reads exactly as badly as
 * it sounds.
 *
 * So the board names an attitude and the casting names the drawing, and the
 * casting is responsible for every drawing it names being the same clothes.
 * Only two families survive that test -- "colour top over dark trousers" and
 * its inverse -- and giving two characters opposite families is also the
 * cheapest way to make them read apart in a two-shot. Those five drawings are
 * the only bodies vendored here; the rest of the sixty-one are a wardrobe
 * change waiting to happen.
 */
const bodyOf = (id, pose) => {
  const c = plan.cast[id];
  return BODIES[c.bodies[pose]] ?? BODIES[c.bodies.rest];
};

/**
 * Walking speed, in character heights per second.
 *
 * An adult at an ordinary pace covers about 0.8 of their own height every
 * second. This is deliberately well under that: a slow cross reads as a
 * decision rather than as a transition. Expressing it in heights rather than
 * scene units means a child and an adult move at speeds that look right next
 * to each other without a second number to keep in step.
 */
const SPEED = 0.45;

/** Stride length as a fraction of height, from the pack's own walk geometry. */
const STRIDE = 0.586;

/** Vertical travel of the body over a step, as a fraction of height. */
const BOB = 0.009;

/**
 * Degrees a figure leans into a move.
 *
 * There is no walk drawing any more. Every body the pack draws mid-stride is
 * a short-sleeved tee, and every body drawn at rest is long-sleeved, so
 * swapping one in for the length of a cross changes the character's clothes
 * every time they move -- nineteen times in three minutes, on the board this
 * was found on. A whole figure sliding rigidly is worse again, so what sells
 * the move instead is a lean: two degrees into the direction of travel, eased
 * in and out, pivoting on the feet. It is the smallest possible cue and it is
 * the one the eye actually reads.
 */
const LEAN = 2.0;

const smooth = (u) => u * u * (3 - 2 * u);

/**
 * Where a figure is, and what it is doing, on a given frame.
 *
 * Travel takes as long as the distance needs at a fixed speed and no longer;
 * the rest of the shot is a stand. Easing is symmetric, so a character never
 * starts or stops abruptly -- which was the note that started this rewrite.
 */
const step = (entry, frame, fps) => {
  const last = Math.max(1, entry.frames - 1);
  const dist = Math.abs(entry.x1 - entry.x0);
  const dir = dist > 1e-6 ? Math.sign(entry.x1 - entry.x0) : (entry.facing ?? 1);

  if (dist <= 1e-6) {
    return {x: entry.x0, dy: 0, lean: 0, walking: false, facing: entry.facing ?? 1};
  }

  const height = entry.height;
  const arrive = Math.min(last, Math.max(2, Math.round((dist / (SPEED * height)) * fps)));
  const t = Math.max(0, Math.min(frame, last));

  if (t >= arrive) return {x: entry.x1, dy: 0, lean: 0, walking: false, facing: dir};

  const u = smooth(t / arrive);
  // Two steps to a stride, and the bob is driven by distance covered rather
  // than by time, so it slows down as the figure does instead of running on.
  const phase = (Math.abs(entry.x0 + (entry.x1 - entry.x0) * u - entry.x0) / (STRIDE * height)) * 2;
  // The lean follows *speed*, not position, so the figure tips into the move
  // as it starts and comes upright as it settles.
  const speed = Math.sin(Math.PI * Math.min(1, t / arrive));
  return {
    x: entry.x0 + (entry.x1 - entry.x0) * u,
    dy: -Math.abs(Math.sin(phase * Math.PI)) * BOB * height,
    lean: dir * LEAN * speed,
    walking: true,
    facing: dir,
  };
};

export const PeepsActors = ({shotId, frame, fps = 30}) => {
  const entries = plan.shots[shotId];
  const drawn = useMemo(() => (entries ?? []).map((e) => ({
    look: look(e.id, e.face),
    body: bodyOf(e.id, e.pose || 'rest'),
  })), [shotId]);
  if (!entries || !entries.length) return null;

  return (
    <>
      {entries.map((e, i) => {
        const m = step(e, Math.max(0, frame), fps);
        return (
          <Figure
            key={`${e.id}-${i}`}
            body={drawn[i].body}
            look={drawn[i].look}
            x={m.x}
            y={e.y + m.dy}
            lean={m.lean}
            height={e.height}
            facing={m.facing}
          />
        );
      })}
    </>
  );
};

export const hasPeepsActors = (shotId) => Boolean(plan.shots[shotId]);
