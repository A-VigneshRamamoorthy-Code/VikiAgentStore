import React from 'react';
import {staticFile} from 'remotion';

/**
 * Open Peeps parts, drawn from extracted geometry.
 *
 * The art is CC0 and hand-drawn, which is the point: 53 heads, 33 faces and 16
 * beards recombine into a cast that looks like one illustrator drew all of it,
 * because one illustrator did. Nothing here is generated, so nothing here
 * drifts between shots — the failure mode of the procedural rig this replaced,
 * where every character was a fresh accident.
 *
 * Fills arrive as `@role` tokens rather than hex, and a character's palette
 * resolves them once. That is what lets the same head asset be four different
 * people without a second copy of the geometry, and what stops a character
 * changing colour when a shot changes.
 */

const CAMEL = /[A-Z]/g;
const attrName = (k) => k.replace(CAMEL, (m) => `-${m.toLowerCase()}`);

/** Resolve a `@role` token; anything else is already a literal. */
const paint = (v, palette) =>
  typeof v === 'string' && v.startsWith('@') ? palette[v.slice(1)] ?? 'none' : v;

const El = ({el, palette}) => {
  const {tag, ...rest} = el;
  const props = {};
  for (const [k, v] of Object.entries(rest)) {
    props[attrName(k)] = paint(v, palette);
  }
  return React.createElement(tag, props);
};

/**
 * One extracted part, drawn in its own coordinate space.
 *
 * Deliberately does NOT emit its own `<svg>`: parts are composed against each
 * other by transform, and a nested viewBox would rescale each one
 * independently and pull the face off the head.
 *
 * `fallback` paints elements the extractor found with no fill of their own.
 * In the body art those are the recolourable garments -- the "Color" in
 * `ShirtColorTee` -- which is why a body left alone renders in black trousers
 * and a black shirt.
 */
export const Part = ({asset, palette, fallback}) => {
  if (!asset) return null;
  return (
    <g>
      {asset.els.map((el, i) => (
        <El
          key={i}
          el={fallback && el.fill === undefined ? {...el, fill: fallback} : el}
          palette={palette}
        />
      ))}
    </g>
  );
};

/**
 * Head assembly: hair, face, beard and accessory at the offsets Open Peeps
 * composes them with, plus the per-hairstyle nudge.
 *
 * Authored in Open Peeps units and scaled by the caller, so every offset in
 * here matches `layout.json` exactly and none of them are re-derived by eye.
 */
export const Head = ({hair, face, beard, accessory, layout, palette}) => {
  const base = layout.base;
  const nudge = layout.nudge;
  const rel = (part) => [base[part][0] - base.hair[0], base[part][1] - base.hair[1]];
  const hairNudge = (hair && nudge.hair[hair.id]) || [0, 0];
  const [fx, fy] = rel('face');
  const [bx, by] = rel('beard');
  const [ax, ay] = rel('accessory');

  return (
    <g>
      <g transform={`translate(${hairNudge[0]} ${hairNudge[1]})`}>
        <Part asset={hair} palette={palette} />
      </g>
      <g transform={`translate(${fx} ${fy})`}>
        <Part asset={face} palette={palette} />
      </g>
      {beard && (
        <g transform={`translate(${bx} ${by})`}>
          <Part asset={beard} palette={palette} />
        </g>
      )}
      {accessory && (
        <g transform={`translate(${ax} ${ay})`}>
          <Part asset={accessory} palette={palette} />
        </g>
      )}
    </g>
  );
};

export const peepsUrl = (category, id) => staticFile(`peeps/${category}/${id}.json`);
