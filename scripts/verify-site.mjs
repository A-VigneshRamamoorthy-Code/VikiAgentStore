#!/usr/bin/env node
/**
 * Renders the store front-end and asserts that everything in the catalog
 * actually reaches the DOM.
 *
 *   node scripts/verify-site.mjs                      # test docs/ on disk
 *   node scripts/verify-site.mjs https://example.com  # test a deployed site
 *
 * Requires jsdom:  npm i --no-save jsdom
 *
 * Why jsdom and not headless Chrome: the page is rendered entirely by app.js,
 * so curl proves nothing — and headless Chrome was found to hang indefinitely
 * on this project's macOS setup. jsdom executes the real app.js against the real
 * index.html, which is a stronger check than dumping the DOM anyway.
 *
 * Note that skills and install commands are rendered ONLY inside the modal,
 * which app.js builds on click — so this script clicks every card.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

let JSDOM, VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = await import('jsdom'));
} catch {
  console.error('jsdom is not installed.  Run:  npm i --no-save jsdom');
  process.exit(2);
}

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const target = process.argv[2] ? process.argv[2].replace(/\/$/, '') : null;

const load = async (file) => {
  if (!target) return readFileSync(join(root, 'docs', file), 'utf8');
  const r = await fetch(`${target}/${file}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${file} -> HTTP ${r.status}`);
  return r.text();
};

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  - ' + detail : ''}`);
};

const [html, appjs, catalogText] = await Promise.all([
  load('index.html'),
  load('app.js'),
  load('catalog.json'),
]);
const catalog = JSON.parse(catalogText);

const vc = new VirtualConsole();
vc.on('jsdomError', (e) => console.log('   [jsdom error]', e.message));

const base = target || 'https://agentstore.sololeapinc.com';
const dom = new JSDOM(html, { runScripts: 'outside-only', url: base + '/', virtualConsole: vc });
const w = dom.window;

w.fetch = async (u) =>
  String(u).includes('catalog.json')
    ? { ok: true, status: 200, json: async () => JSON.parse(catalogText), text: async () => catalogText }
    : { ok: false, status: 404, json: async () => ({}), text: async () => '' };
w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
w.scrollTo = () => {};
w.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
w.cancelAnimationFrame = () => {};
w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

w.eval(appjs);
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
await new Promise((r) => setTimeout(r, 800));

const body = w.document.body.innerHTML;
const text = w.document.body.textContent.replace(/\s+/g, ' ');

check('page rendered', body.length > 2000, `${body.length} bytes of DOM`);

for (const p of catalog.plugins) {
  check(`card: ${p.id}`, text.includes(p.name) || body.includes(p.id));
}

const modalEl = w.document.querySelector('#modal');
const openModal = async (id) => {
  const card = w.document.querySelector(`.card[data-id="${id}"]`);
  if (!card) return null;
  card.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 60));
  return modalEl ? modalEl.innerHTML : null;
};

const missingSkills = [];
const missingInstall = [];
for (const p of catalog.plugins) {
  const modal = await openModal(p.id);
  if (modal == null) { missingSkills.push(`${p.id}:<no card>`); continue; }
  for (const s of p.skills) if (!modal.includes(s.name)) missingSkills.push(`${p.id}/${s.name}`);
  const expected = p.type === 'mcp' ? p.id : `${p.id}@VikiAgentStore`;
  if (!modal.includes(expected)) missingInstall.push(p.id);
}

const skillTotal = catalog.plugins.reduce((n, p) => n + p.skills.length, 0);
check(`all ${skillTotal} skills render in their modal`, missingSkills.length === 0,
  missingSkills.join(', '));
check('every plugin shows an install command', missingInstall.length === 0,
  missingInstall.join(', '));

for (const cat of [...new Set(catalog.plugins.map((p) => p.category))]) {
  check(`category: ${cat}`, text.includes(cat));
}

const statOf = (id) => (w.document.getElementById(id) || {}).textContent?.trim();
check('stat-plugins correct', statOf('stat-plugins') === String(catalog.plugins.length),
  `got ${statOf('stat-plugins')}`);
check('stat-skills correct', statOf('stat-skills') === String(skillTotal),
  `got ${statOf('stat-skills')}`);
check('stat-docs populated', !!statOf('stat-docs') && statOf('stat-docs') !== '0',
  `got ${statOf('stat-docs')}`);
check('no "undefined" rendered', !body.includes('undefined'));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} passed against ${target || 'docs/ (local)'}`);
process.exit(failed ? 1 : 0);
