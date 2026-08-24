import React from 'react';
import {Img, staticFile} from 'remotion';
import meta from '../generated/actors.json';

/**
 * Actors, composited as cels.
 *
 * Unlike the props and sets, the rig does not draw through a pen -- it paints
 * onto a PIL surface at 3x and composites down -- so there was no seam to
 * record vectors from. `tools/trace-actors.py` therefore drives the engine's
 * own pose solver and saves each distinct drawing as a transparent PNG.
 *
 * That is what limited animation does on paper, and the numbers show why it
 * is cheap: 100 frames of Norman driving are 20 drawings, because the film
 * holds on threes. The exception is the cyclist, whose smears deliberately
 * break the hold -- 82 drawings for 84 frames -- which is the style working
 * as designed rather than the cache failing.
 *
 * Boxes are absolute scene coordinates straight from `rig.bbox`, so a cel
 * lands exactly where the Python renderer would have drawn it.
 */

export const Actors = ({shotId, frame}) => {
  const entries = Object.entries(meta.actors).filter(
    ([, a]) => a.shot === shotId
  );
  if (!entries.length) return null;

  return (
    <>
      {entries.map(([key, a]) => {
        const i = Math.min(Math.max(0, frame), a.frames.length - 1);
        const cel = a.frames[i];
        if (!cel) return null;
        const [x0, y0, x1, y1] = cel.box;
        return (
          <image key={key} href={staticFile(`actors/${cel.src}`)}
                 x={x0} y={y0} width={x1 - x0} height={y1 - y0}
                 style={{imageRendering: 'auto'}} />
        );
      })}
    </>
  );
};

export const hasActors = (shotId) =>
  Object.values(meta.actors).some((a) => a.shot === shotId);
