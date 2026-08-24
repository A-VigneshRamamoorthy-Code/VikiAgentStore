import React from 'react';
import {Vector} from '../lib/Vector.jsx';
import traced from '../generated/sets.json';

/**
 * Sets, replayed from the Python engine's own layers.
 *
 * `tools/trace-sets.py` records each parallax layer as a strip of world, so
 * the scenery is the film's actual scenery rather than a lookalike. What
 * Remotion adds is the parallax: the engine re-draws every layer at a shifted
 * origin on every frame, whereas these are static groups moved by a
 * transform -- the one part of the job a browser is genuinely built for.
 *
 * The shift matches `sets.layer_origins`: a layer's origin moves by
 * `off * (1 - k)`, where `off` is the camera's travel from the shot's
 * starting centre. So k = 1 sits in the world, k = 0 is pinned to the frame,
 * and k = 1.5 overtakes it.
 *
 * Every layer comes per shot, because the renderer seeds each shot separately
 * -- ten street shots are ten different streets, not ten cuts of one wall,
 * and three aerial shots are three different rush hours.
 *
 * Moving layers arrive delta-encoded: one drawing plus, per time sample, an
 * offset for each group of points that travels together. That is what the
 * aerial traffic actually is -- a few hundred cars keeping their identity and
 * moving -- so it costs a fraction of a snapshot per sample and pays for a
 * much finer sample rate. See `pack_motion` in tools/trace-sets.py.
 */

export const SET_GROUND = traced.ground;
export const GROUND = 44.0;

export const Set = ({name, shotId, view, board, t = 0}) => {
  const set = traced.sets[name];
  const perShot = traced.shots[shotId];
  if (!set) return null;

  const anchor = view?.anchor ?? [view?.cx ?? 50, view?.cy ?? 28];
  const off = [(view?.cx ?? 50) - anchor[0], (view?.cy ?? 28) - anchor[1]];
  const span = set.span ?? 6;
  const fps = set.fps ?? 30;

  // Foreground furniture -- kerbs, bollards, the aerial's rail -- is dressed
  // against the bottom of the frame, not pinned to a world coordinate, so the
  // engine re-places it as the camera zooms. The tracer works out which
  // layers behave that way; here they are simply re-hung off the current
  // view's bottom edge. See `frame_anchored` in tools/trace-sets.py.
  const anchored = new global.Set(set.anchored ?? []);
  const viewBottom = (view?.cy ?? 28) + (view?.h ?? board?.h ?? 56.25) / 2;
  const anchorDy = viewBottom - (set.bottom ?? 0);

  const bag = new Map();
  for (const l of perShot?.layers ?? []) bag.set(l.name, l);
  for (const l of set.layers ?? []) bag.set(l.name, l);

  return (
    <>
      {set.order.map((lname) => {
        const layer = bag.get(lname);
        if (!layer) return null;

        // A per-frame layer is indexed by the frame, full stop -- no
        // resampling, because there is nothing between two frames to
        // resample to. Coarser layers keep the phase-wrapped lookup.
        const pick = (n) =>
          layer.perFrame
            ? Math.min(Math.max(0, Math.round(t * fps)), n - 1)
            : ((Math.floor((t / span) * n) % n) + n) % n;

        let ops = layer.ops;
        if (layer.frames?.length) ops = layer.frames[pick(layer.frames.length)];
        if (!ops?.length) return null;

        const motion = layer.motion;
        if (motion) {
          const d = motion.delta[pick(motion.delta.length)];
          // Shift the shared drawing rather than swapping it. Points are
          // addressed by a flat index across the layer, in the same order
          // the tracer walked them.
          const shift = new Float64Array(2 * countPoints(ops));
          motion.idx.forEach((group, gi) => {
            const [gx, gy] = d[gi];
            for (const i of group) {
              shift[2 * i] = gx;
              shift[2 * i + 1] = gy;
            }
          });
          ops = applyShift(ops, shift);
        }

        const dx = off[0] * (1 - layer.k);
        const dy = anchored.has(lname)
          ? anchorDy
          : off[1] * (1 - layer.k);
        return (
          <g key={lname} transform={`translate(${dx} ${dy})`}>
            <Vector ops={ops} idPrefix={`${shotId}-${lname}`} />
          </g>
        );
      })}
    </>
  );
};

const countPoints = (ops) => {
  let n = 0;
  for (const o of ops) n += o.p ? o.p.length : 0;
  return n;
};

/** Re-emit a drawing with each point moved by its group's offset. */
const applyShift = (ops, shift) => {
  const out = new Array(ops.length);
  let i = 0;
  for (let j = 0; j < ops.length; j++) {
    const o = ops[j];
    if (!o.p) {
      out[j] = o;
      continue;
    }
    const p = new Array(o.p.length);
    for (let q = 0; q < o.p.length; q++, i++) {
      p[q] = [o.p[q][0] + shift[2 * i], o.p[q][1] + shift[2 * i + 1]];
    }
    out[j] = {...o, p};
  }
  return out;
};

/** Layers that belong in front of the cast. `Set` is taken, so: a list. */
export const FOREGROUND = ['foreground'];
