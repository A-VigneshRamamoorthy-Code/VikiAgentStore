#!/usr/bin/env node
/**
 * Extracts Humaaans (CC0, Pablo Stanley) character art into flat JSON assets.
 *
 * Humaaans ships as plain Sketch-exported SVG rather than the compiled React of
 * Open Peeps, so the job is different: the colours are literal hex, not
 * variables. What makes the library recolourable anyway is that every shape
 * sits inside a group with a *semantic* id -- `Skin`, `Hair`, `Clothes`,
 * `Shade`, `Leg`, `Shoe`. Those ids are the parameterisation, and they are what
 * we turn into `@role` tokens so a palette can drive the whole cast centrally,
 * exactly as the Open Peeps pipeline does.
 *
 * Two things are deliberately NOT done here:
 *
 *  - Transforms are not flattened into path data. Sketch nests
 *    `translate/rotate/translate` triples to rotate a limb about its own
 *    origin, and re-deriving that as a matrix by hand is a good way to put an
 *    arm through a torso. The accumulated transform list is carried through
 *    verbatim instead, which SVG applies in exactly the order it was authored.
 *  - Geometry is not simplified. The art is already small (a few KB a piece)
 *    and every edit is a chance to go off-model.
 *
 * The stacking offsets are read from the 32 pre-composed figures rather than
 * guessed, because those files ARE the artist's own answer to "where does a
 * head sit on a body". See `layout.json`.
 *
 * Usage:
 *   node extract-humaaans.mjs <path-to-"Flat Assets"-dir> <out-dir>
 */

import fs from 'node:fs';
import path from 'node:path';

const [, , SRC, OUT] = process.argv;
if (!SRC || !OUT) {
  console.error('usage: extract-humaaans.mjs <flat-assets-dir> <out-dir>');
  process.exit(2);
}

/**
 * Group id -> palette role.
 *
 * Matched case-insensitively against the id of the nearest enclosing `<g>`, so
 * `Hair-Back` and `Coat-Front` resolve without needing an entry each.
 */
const ROLE_BY_ID = [
  [/^skin$/i, '@skin'],
  [/hair/i, '@hair'],
  [/^shade$/i, '@shade'],
  [/shoe/i, '@shoe'],
  [/^leg$/i, '@clothing'],
  [/^pant/i, '@clothing'],
  [/coat|shirt|clothes|jacket|hoodie|sleeve|dress|skirt|top/i, '@clothing'],
];

/**
 * Fallback: Humaaans reuses a fixed skin ramp and one signature ink navy across
 * every piece, so a fill alone identifies those two roles reliably even when a
 * shape sits outside a named group.
 */
const ROLE_BY_FILL = {
  '#b28b67': '@skin',
  '#997659': '@skin',
  '#a0704a': '@skin',
  '#191847': '@ink',
  '#000000': '@shade',
};

/**
 * Nearest-id-wins. The element's OWN id is consulted first, because Sketch puts
 * the meaningful names on the paths -- `Skin`, `Shade`, `Coat-Front` -- while
 * the enclosing group is named for the garment (`Body/Hoodie`). Searching only
 * the group stack painted a hoodie's bare arms as fabric.
 */
const roleFor = (idStack, fill) => {
  for (let i = idStack.length - 1; i >= 0; i--) {
    const id = idStack[i];
    if (!id) continue;
    for (const [re, role] of ROLE_BY_ID) if (re.test(id)) return role;
  }
  const byFill = ROLE_BY_FILL[String(fill || '').toLowerCase()];
  return byFill || null;
};

const ATTR = /([\w:-]+)\s*=\s*"([^"]*)"/g;
const attrs = (s) => {
  const out = {};
  let m;
  ATTR.lastIndex = 0;
  while ((m = ATTR.exec(s))) out[m[1]] = m[2];
  return out;
};

const DRAWABLE = new Set(['path', 'polygon', 'circle', 'ellipse', 'rect', 'line', 'polyline']);
const TAG = /<(\/?)([a-zA-Z][\w:-]*)((?:"[^"]*"|[^>"])*?)(\/?)>/g;

/**
 * Walk an SVG in document order, carrying a stack of enclosing group ids and
 * transforms. Returns the drawable elements with their accumulated transform.
 */
const parseSvg = (src) => {
  const root = /<svg\b([^>]*)>/i.exec(src);
  const rootAttrs = root ? attrs(root[1]) : {};
  const vb = rootAttrs.viewBox || null;
  const els = [];
  const idStack = [];
  const tfStack = [];
  // Sketch routinely sets `fill` (and opacity) on the <g> and leaves the child
  // paths bare. Without inheriting, every such shape silently defaults to black
  // -- which is how a face first came out as a black blob.
  const fillStack = [];
  const opacityStack = [];

  let m;
  TAG.lastIndex = 0;
  while ((m = TAG.exec(src))) {
    const [, closing, tagRaw, attrSrc, selfClose] = m;
    const tag = tagRaw.toLowerCase();

    if (tag === 'svg' || tag === 'title' || tag === 'desc' || tag === 'defs') continue;

    if (tag === 'g') {
      if (closing) {
        idStack.pop();
        tfStack.pop();
        fillStack.pop();
        opacityStack.pop();
      } else if (!selfClose) {
        const a = attrs(attrSrc);
        idStack.push(a.id || '');
        tfStack.push(a.transform || '');
        fillStack.push(a.fill);
        opacityStack.push(a.opacity ?? a['fill-opacity']);
      }
      continue;
    }

    if (closing || !DRAWABLE.has(tag)) continue;

    const a = attrs(attrSrc);
    const inheritedFill = [...fillStack].reverse().find((f) => f !== undefined);
    // `none` is meaningful (an unfilled outline); absent everywhere means black.
    const fill = a.fill !== undefined ? a.fill
               : inheritedFill !== undefined ? inheritedFill
               : '#000000';
    const role = fill === 'none' ? null : roleFor([...idStack, a.id || ''], fill);

    const transform = [...tfStack, a.transform || ''].filter(Boolean).join(' ');
    const el = {tag};
    for (const k of ['d', 'points', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y',
                     'width', 'height', 'x1', 'y1', 'x2', 'y2', 'fillRule',
                     'fill-rule', 'opacity', 'fill-opacity', 'stroke',
                     'stroke-width', 'stroke-linecap']) {
      if (a[k] !== undefined) el[k] = a[k];
    }
    if (el.opacity === undefined) {
      const inheritedOpacity = [...opacityStack].reverse().find((o) => o !== undefined);
      if (inheritedOpacity !== undefined) el.opacity = inheritedOpacity;
    }
    el.fill = role || fill;
    if (transform) el.transform = transform;
    els.push(el);
  }

  return {viewBox: vb, width: rootAttrs.width, height: rootAttrs.height, els};
};

const num = (s) => {
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : 0;
};

const slug = (name) =>
  name.replace(/\.svg$/i, '').trim().replace(/\s+/g, '-').replace(/[^\w-]/g, '');

const walk = (dir) => {
  const out = [];
  for (const e of fs.readdirSync(dir, {withFileTypes: true})) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.toLowerCase().endsWith('.svg')) out.push(p);
  }
  return out;
};

/** Category for a piece, derived from its path under `Single Pieces`. */
const categorise = (rel) => {
  const p = rel.replace(/\\/g, '/');
  if (/^Head\//i.test(p)) return 'head';
  if (/^Body\//i.test(p)) return 'body';
  if (/^Bottom\/Standing\//i.test(p)) return 'bottom';
  if (/^Bottom\/Sitting\//i.test(p)) return 'sitting';
  if (/^Objects\//i.test(p)) return 'object';
  if (/^Scene\//i.test(p)) return 'scene';
  return null;
};

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

const piecesDir = path.join(SRC, 'Single Pieces');
if (!fs.existsSync(piecesDir)) {
  console.error(`no "Single Pieces" directory under ${SRC}`);
  process.exit(2);
}

const index = {};
let written = 0;

for (const file of walk(piecesDir)) {
  const rel = path.relative(piecesDir, file);
  const cat = categorise(rel);
  if (!cat) continue;

  const parsed = parseSvg(fs.readFileSync(file, 'utf8'));
  if (!parsed.els.length) continue;

  const id = slug(path.basename(file));
  const [, , w, h] = (parsed.viewBox || '0 0 0 0').split(/[\s,]+/).map(num);

  const asset = {
    id,
    name: path.basename(file).replace(/\.svg$/i, ''),
    category: cat,
    w,
    h,
    viewBox: parsed.viewBox,
    els: parsed.els,
  };

  const dir = path.join(OUT, cat);
  fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(path.join(dir, `${id}.json`), JSON.stringify(asset));
  (index[cat] ||= []).push(id);
  written++;
}

// ---------------------------------------------------------------------------
// Layout, read out of the composed figures
// ---------------------------------------------------------------------------

/**
 * Sketch writes a rotation as translate(cx,cy) rotate(a) translate(-cx,-cy)
 * followed by the real placement translate. Only that LAST translate is the
 * piece's position, so take the final one rather than the first.
 */
const lastTranslate = (tf) => {
  const all = [...tf.matchAll(/translate\(\s*(-?[\d.]+)[\s,]+(-?[\d.]+)\s*\)/g)];
  if (!all.length) return null;
  const m = all[all.length - 1];
  return [num(m[1]), num(m[2])];
};

const composedDir = path.join(SRC, 'Humaaans');
const seen = {head: [], body: [], bottom: []};

if (fs.existsSync(composedDir)) {
  const G = /<g\s+id="((?:Head|Body|Bottom)\/[^"]*)"[^>]*transform="([^"]*)"/g;
  for (const file of walk(composedDir)) {
    const src = fs.readFileSync(file, 'utf8');
    let m;
    G.lastIndex = 0;
    while ((m = G.exec(src))) {
      const kind = m[1].split('/')[0].toLowerCase();
      const key = kind === 'bottom' ? 'bottom' : kind;
      const t = lastTranslate(m[2]);
      if (t && seen[key]) seen[key].push(t);
    }
  }
}

/** The offset the artist used most often for a category. */
const modal = (pts, fallback) => {
  if (!pts.length) return fallback;
  const tally = new Map();
  for (const [x, y] of pts) {
    const k = `${Math.round(x)},${Math.round(y)}`;
    tally.set(k, (tally.get(k) || 0) + 1);
  }
  const best = [...tally.entries()].sort((a, b) => b[1] - a[1])[0][0];
  return best.split(',').map(Number);
};

const layout = {
  note:
    'Offsets in Humaaans units, read from the 32 pre-composed figures rather ' +
    'than measured by eye. `base` is where each part sits relative to the ' +
    'figure origin; the composed art is 380x480 with the figure inset by 34,17.',
  figure: {w: 380, h: 480, inset: [34, 17]},
  base: {
    head: modal(seen.head, [61.95, 8.59]),
    body: modal(seen.body, [21.88, 95.21]),
    bottom: modal(seen.bottom, [0, 203.69]),
  },
  samples: {head: seen.head.length, body: seen.body.length, bottom: seen.bottom.length},
};

fs.mkdirSync(OUT, {recursive: true});
fs.writeFileSync(path.join(OUT, 'layout.json'), JSON.stringify(layout, null, 2));

for (const k of Object.keys(index)) index[k].sort();

// Same envelope the Open Peeps extractor writes, because fetch_assets.py
// validates every source against one contract: {source, license, count,
// categories}. A bare category map here would fetch fine and then fail
// --check, which is the worst of both worlds.
const manifestIndex = {
  source: 'humaaans',
  license: 'CC0-1.0',
  count: written,
  categories: Object.fromEntries(Object.keys(index).sort().map((k) => [k, index[k]])),
};
fs.writeFileSync(path.join(OUT, 'index.json'), JSON.stringify(manifestIndex, null, 2));

const counts = Object.entries(index)
  .map(([k, v]) => `${k}=${v.length}`)
  .join(' ');
console.log(`humaaans: wrote ${written} assets (${counts})`);
console.log(`  layout base: ${JSON.stringify(layout.base)} from ${layout.samples.head} composed figures`);
