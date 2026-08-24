#!/usr/bin/env node
/**
 * Extracts Open Peeps (CC0) character art into flat, inspectable JSON assets.
 *
 * Open Peeps ships as compiled React components: a `Config` object carrying the
 * viewBox, and a tree of `React.createElement("path", {...})` calls whose fills
 * are *variables* — `skinColor`, `clothingColor`, `outlineColor`, `hairColor`.
 * That parameterisation is the whole reason this library is worth importing
 * rather than redrawing: one head asset recolours into an entire cast without
 * ever going off-model.
 *
 * We do not want a React dependency on someone else's package inside a film, so
 * this lifts the geometry out into data:
 *
 *     { name, w, h, viewBox, paths: [ {d, fill: "@skin" | "#hex", ...} ] }
 *
 * Colour variables become `@role` tokens. The renderer resolves them against a
 * character's palette at draw time, which is what keeps a cast consistent
 * across shots — the colour is looked up once, centrally, not typed per shot.
 *
 * Usage:
 *   node extract-peeps.mjs <path-to-open-peeps-build> <out-dir>
 */

import fs from 'node:fs';
import path from 'node:path';

const [, , SRC, OUT] = process.argv;
if (!SRC || !OUT) {
  console.error('usage: extract-peeps.mjs <open-peeps-build-dir> <out-dir>');
  process.exit(2);
}

/** Colour variables Open Peeps exposes, mapped to our own palette roles. */
const ROLES = {
  outlineColor: '@ink',
  skinColor: '@skin',
  clothingColor: '@clothing',
  hairColor: '@hair',
  facialHairColor: '@hair',
  maskColor: '@accent',
  backgroundColor: '@paper',
  lipColor: '@lip',
  hatColor: '@accent',
};

/**
 * Pull `key: value` pairs out of one `React.createElement("path", { ... })`.
 *
 * Written against the actual compiled output rather than by parsing JS: the
 * attribute set is small and closed (`d`, `fill`, `stroke`, `strokeWidth`,
 * `strokeLinecap`, `fillRule`, `clipRule`, `opacity`, `transform`), and every
 * value is either a single-quoted literal or one of the colour variables above.
 */
const ATTR = /(\w+):\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|([A-Za-z_$][\w$]*))/g;

const parseProps = (src) => {
  const out = {};
  let m;
  ATTR.lastIndex = 0;
  while ((m = ATTR.exec(src))) {
    const key = m[1];
    const literal = m[2] ?? m[3];
    const ident = m[4];
    if (literal !== undefined) {
      out[key] = literal.replace(/\\'/g, "'");
    } else if (ident !== undefined) {
      if (ROLES[ident]) out[key] = ROLES[ident];
      else if (ident === 'undefined' || ident === 'null') continue;
      // Anything else is a local variable we do not model; skip it rather than
      // emit a broken reference.
    }
  }
  return out;
};

/**
 * Elements appear in paint order in the source, and paint order is load-bearing
 * — Open Peeps draws skin, then clothing, then the ink outline on top. Keeping
 * the original sequence is the difference between a face and a smudge.
 */
const extractElements = (src) => {
  const els = [];
  const re = /React\.createElement\(\s*"(path|circle|ellipse|rect|g|mask|defs|clipPath|use|line|polygon)"\s*,\s*\{/g;
  let m;
  while ((m = re.exec(src))) {
    const tag = m[1];
    // Walk to the matching close brace so nested objects (style, transform)
    // do not truncate the match.
    let i = re.lastIndex - 1;
    let depth = 0;
    let end = i;
    for (; i < src.length; i++) {
      const c = src[i];
      if (c === '{') depth++;
      else if (c === '}') {
        depth--;
        if (depth === 0) { end = i; break; }
      }
    }
    const body = src.slice(re.lastIndex, end);
    const props = parseProps(body);
    if (tag === 'path' && !props.d) continue;
    els.push({tag, ...props});
  }
  return els;
};

const readConfig = (src) => {
  const num = (k) => {
    const m = src.match(new RegExp(`${k}:\\s*(\\d+)`));
    return m ? Number(m[1]) : null;
  };
  const vb = src.match(/viewBox:\s*"([^"]+)"/);
  const nm = src.match(/name:\s*"([^"]+)"/);
  return {
    name: nm ? nm[1] : null,
    w: num('width'),
    h: num('height'),
    viewBox: vb ? vb[1] : null,
  };
};

const walk = (dir) => {
  const out = [];
  for (const e of fs.readdirSync(dir, {withFileTypes: true})) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.isFile() && e.name.endsWith('.js') && e.name !== 'index.js') out.push(p);
  }
  return out;
};

let n = 0;
const index = {};
for (const file of walk(SRC)) {
  const src = fs.readFileSync(file, 'utf8');
  const cfg = readConfig(src);
  if (!cfg.viewBox || !cfg.name) continue;
  const els = extractElements(src);
  if (els.length === 0) continue;

  const rel = path.relative(SRC, file);
  const category = path.dirname(rel).split(path.sep).join('/');
  // Key off the source filename, not the display name: `name` is prose
  // ("Walking Color Pants") and a board referring to an asset by a string with
  // spaces in it is a typo waiting to happen.
  const id = path.basename(file, '.js');
  const asset = {
    id,
    name: cfg.name,
    category,
    w: cfg.w,
    h: cfg.h,
    viewBox: cfg.viewBox,
    source: 'open-peeps',
    license: 'CC0-1.0',
    els,
  };
  const dest = path.join(OUT, category, `${id}.json`);
  fs.mkdirSync(path.dirname(dest), {recursive: true});
  fs.writeFileSync(dest, JSON.stringify(asset));
  (index[category] ??= []).push(id);
  n++;
}

for (const k of Object.keys(index)) index[k].sort();
fs.mkdirSync(OUT, {recursive: true});
fs.writeFileSync(
  path.join(OUT, 'index.json'),
  JSON.stringify({source: 'open-peeps', license: 'CC0-1.0', count: n, categories: index}, null, 2)
);

/* ── composition layout ───────────────────────────────────────────────────
 *
 * The parts are drawn in their own coordinate systems and only line up when
 * placed at the offsets `Effigy.js` uses. Those offsets are not decoration:
 * get the face one wrong and the eyes sit on the forehead.
 *
 * Most of them are constant, but 44 hairstyles and 6 body types carry their
 * own nudge, so the table is lifted out of the source rather than copied by
 * hand — the copy would rot the moment the library is bumped.
 */
const effigy = path.join(SRC, 'Effigy.js');
if (fs.existsSync(effigy)) {
  const src = fs.readFileSync(effigy, 'utf8');

  const baseOf = (id) => {
    const m = src.match(new RegExp(`id:\\s*'${id}',\\s*transform:\\s*'translate\\(([-\\d.]+)[ ,]+([-\\d.]+)\\)`));
    return m ? [Number(m[1]), Number(m[2])] : [0, 0];
  };

  /** Per-type nudges inside one `createX` factory. */
  const nudgesOf = (fnName, varName) => {
    const body = src.match(new RegExp(`var ${fnName} = function[\\s\\S]*?\\n};`));
    if (!body) return {};
    const out = {};
    const re = new RegExp(
      `${varName}\\.type === "([^"]+)"[\\s\\S]{0,220}?translate\\((-?[\\d.]+)[ ,]+(-?[\\d.]+)\\)`,
      'g'
    );
    let m;
    while ((m = re.exec(body[0]))) out[m[1]] = [Number(m[2]), Number(m[3])];
    return out;
  };

  const vb = src.match(/viewBox:\s*'([^']+)'/);
  fs.writeFileSync(
    path.join(OUT, 'layout.json'),
    JSON.stringify(
      {
        viewBox: vb ? vb[1] : null,
        base: {
          body: baseOf('Body'),
          hair: baseOf('Hair'),
          face: baseOf('Face'),
          beard: baseOf('Beard'),
          accessory: baseOf('Accessories'),
        },
        nudge: {
          hair: nudgesOf('createHair', 'head'),
          face: nudgesOf('createFace', 'face'),
          beard: nudgesOf('createBeard', 'beard'),
          accessory: nudgesOf('createAccessory', 'accessory'),
          headByBody: nudgesOf('createHead', 'body'),
        },
      },
      null,
      2
    )
  );
}

console.log(`extracted ${n} assets into ${OUT}`);
for (const [k, v] of Object.entries(index)) console.log(`  ${k}: ${v.length}`);
