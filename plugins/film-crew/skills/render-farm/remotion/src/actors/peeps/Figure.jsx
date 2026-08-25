import React from 'react';
import {Part} from './Peeps.jsx';

/**
 * A whole character, assembled out of drawn parts.
 *
 * `Character.jsx` next door builds a body out of primitives and animates it.
 * That is the right tool when a figure has to do something no illustrator drew
 * -- but the pack ships sixty-one bodies already in different attitudes, and a
 * drawn body beats a solved one every time the camera is close enough to tell.
 * So this composes: a body from `body/standing`, and the same head the rig
 * uses, set on its neck.
 *
 * The pack's own `layout.json` only records head offsets for the *effigy*
 * busts, which are a different drawing at a different scale, so the offset for
 * a standing figure is measured here instead. Every standing body leaves a
 * skin-coloured neck stub at its top edge; find that stub and you know where
 * the chin goes, whatever the pose.
 */

const NUM = /-?\d+(?:\.\d+)?/g;

const bboxOf = (els) => {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of els) {
    if (!e.d) continue;
    const v = e.d.match(NUM);
    if (!v) continue;
    for (let i = 0; i + 1 < v.length; i += 2) {
      const x = +v[i], y = +v[i + 1];
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
  }
  return {x0, y0, x1, y1};
};

/**
 * The neck stub, which is where the head belongs.
 *
 * It is the topmost run of bare skin -- but so is a raised hand, and one of
 * these poses is pointing at something. A hand that high is always out at the
 * side of the canvas, so anything beyond a third of the width from the
 * centreline is not a neck.
 */
const neckOf = (body) => {
  const skin = body.els.find((e) => e.fill === '@skin');
  const v = skin.d.match(NUM);
  const pts = [];
  for (let i = 0; i + 1 < v.length; i += 2) pts.push([+v[i], +v[i + 1]]);
  const top = Math.min(...pts.map((p) => p[1]));
  const mid = body.w / 2;
  const xs = pts
    .filter((p) => p[1] < top + 60 && Math.abs(p[0] - mid) < body.w * 0.35)
    .map((p) => p[0]);
  return {x: (Math.min(...xs) + Math.max(...xs)) / 2, y: top};
};

/** How far the head sinks onto the stub, in body units. */
const NECK_OVERLAP = 100;

const cache = new Map();

export const measure = (body, look) => {
  const key = `${body.id}|${look.hair.id}|${look.face.id}|${look.beard?.id ?? ''}`;
  const hit = cache.get(key);
  if (hit) return hit;

  const base = look.layout.base;
  const neck = neckOf(body);
  const fb = bboxOf(look.face.els);

  // Set the chin on the stub, then hang the hair off the face by the same
  // relative offset the pack uses everywhere else.
  const face = {
    x: neck.x - (fb.x0 + fb.x1) / 2,
    y: neck.y + NECK_OVERLAP - fb.y1,
  };
  const hair = {
    x: face.x - (base.face[0] - base.hair[0]),
    y: face.y - (base.face[1] - base.hair[1]),
  };
  const beard = {
    x: hair.x + (base.beard[0] - base.hair[0]),
    y: hair.y + (base.beard[1] - base.hair[1]),
  };

  const bodyBox = bboxOf(body.els);
  const hairBox = bboxOf(look.hair.els);
  const hairNudge = look.layout.nudge.hair[look.hair.id] || [0, 0];

  // Height is crown to sole, deliberately ignoring outstretched limbs: a
  // pointing arm must not make the character shorter when the pose changes.
  const out = {
    face, beard,
    hair: {x: hair.x + hairNudge[0], y: hair.y + hairNudge[1]},
    anchorX: neck.x,
    foot: bodyBox.y1,
    height: bodyBox.y1 - (hairBox.y0 + hair.y + hairNudge[1]),
  };
  cache.set(key, out);
  return out;
};

/**
 * @param body   one of the `body/standing` assets
 * @param look   palette, hair, face, beard, layout -- as `Character` takes it
 * @param x,y    where the soles stand, in the parent's units
 * @param height how tall the character is, in those same units
 * @param facing 1 or -1
 * @param lean   degrees to tip the whole figure, pivoting on the soles
 *
 * Hair reads as ink in this pack -- fifty-three of the fifty-three head assets
 * draw it with the outline colour -- so the head is drawn with `ink` remapped
 * to `hair`. That lets one character be brown-haired and another grey without
 * lightening a single outline anywhere else in the frame.
 */
export const Figure = ({body, look, x, y, height, facing = 1, lean = 0}) => {
  const g = measure(body, look);
  const s = height / g.height;
  const head = {...look.palette, ink: look.palette.hair};
  // The lean is applied outside the mirror, so its sign is a direction in the
  // scene rather than in the figure's own handedness.
  const stand = lean ? `translate(${x} ${y}) rotate(${lean})` : `translate(${x} ${y})`;

  return (
    <g transform={`${stand} scale(${s * facing} ${s}) translate(${-g.anchorX} ${-g.foot})`}>
      <Part asset={body} palette={look.palette} fallback={look.palette.clothing} />
      <g transform={`translate(${g.hair.x} ${g.hair.y})`}>
        <Part asset={look.hair} palette={head} fallback={look.palette.hair} />
      </g>
      {look.beard ? (
        <g transform={`translate(${g.beard.x} ${g.beard.y})`}>
          <Part asset={look.beard} palette={head} fallback={look.palette.hair} />
        </g>
      ) : null}
      <g transform={`translate(${g.face.x} ${g.face.y})`}>
        <Part asset={look.face} palette={look.palette} fallback={look.palette.ink} />
      </g>
    </g>
  );
};

export default Figure;
