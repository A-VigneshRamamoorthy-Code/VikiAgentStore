#!/usr/bin/env node
/**
 * Generates the store's derived registries from the filesystem.
 *
 * SOURCE OF TRUTH  ->  plugins/<id>/plugin.json
 *                      plugins/<id>/skills/<skill>/SKILL.md   (YAML frontmatter)
 *                      mcp/<id>/mcp.json
 *                      scripts/store-meta.json                (curated presentation only)
 *
 * GENERATED        ->  docs/catalog.json                      (read by the website)
 *                      .github/plugin/marketplace.json        (read by the Copilot CLI)
 *
 * Both outputs are generated. Never hand-edit them.
 *
 *   node scripts/generate-catalog.mjs           # write
 *   node scripts/generate-catalog.mjs --check   # exit 1 if out of date (CI)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PLUGINS_DIR = path.join(ROOT, 'plugins');
const MCP_DIR = path.join(ROOT, 'mcp');
const META_FILE = path.join(ROOT, 'scripts', 'store-meta.json');
const CATALOG_OUT = path.join(ROOT, 'docs', 'catalog.json');
const MARKETPLACE_OUT = path.join(ROOT, '.github', 'plugin', 'marketplace.json');

const CHECK = process.argv.includes('--check');

/* ------------------------------------------------------------------ utils */

const readJSON = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const exists = (p) => fs.existsSync(p);
const dirs = (p) =>
  exists(p)
    ? fs.readdirSync(p, { withFileTypes: true })
        .filter((d) => d.isDirectory() && !d.name.startsWith('.'))
        .map((d) => d.name)
        .sort()
    : [];

function countMarkdown(dir) {
  let n = 0;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.')) continue;
      const full = path.join(d, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.name.toLowerCase().endsWith('.md')) n++;
    }
  };
  if (exists(dir)) walk(dir);
  return n;
}

/**
 * Minimal YAML frontmatter reader — enough for the SKILL.md dialect used here:
 * `key: value`, folded/literal blocks (`>` and `|`), quoted scalars, and one
 * level of nesting (the `metadata:` block).
 */
function frontmatter(md) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(md);
  if (!m) return {};
  const lines = m[1].split(/\r?\n/);
  const out = {};
  let key = null, block = null, blockIndent = 0, buf = [], parent = null;

  const flush = () => {
    if (!key) return;
    let v = buf.join(block === '|' ? '\n' : ' ').trim();
    if (block === '>') v = v.replace(/\s+/g, ' ');
    (parent ? (out[parent] ||= {}) : out)[key] = v;
    key = null; block = null; buf = [];
  };

  for (const raw of lines) {
    if (!raw.trim()) { if (block) buf.push(''); continue; }
    const indent = raw.length - raw.trimStart().length;
    const line = raw.trim();

    if (block && indent > blockIndent) { buf.push(line); continue; }
    if (block) flush();

    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (!kv) continue;
    const [, k, rest] = kv;

    // a nested block opens when a bare key is followed by deeper-indented keys
    if (rest === '' ) {
      if (indent === 0) { parent = k; out[k] ||= {}; }
      continue;
    }
    if (rest === '>' || rest === '|' || rest === '>-' || rest === '|-') {
      key = k; block = rest[0]; blockIndent = indent; buf = [];
      continue;
    }
    if (indent === 0) parent = null;
    let v = rest.trim().replace(/^["'](.*)["']$/, '$1');
    (parent && indent > 0 ? (out[parent] ||= {}) : out)[k] = v;
  }
  flush();
  return out;
}

const titleCase = (s) =>
  s.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/* --------------------------------------------------------------- scanning */

function readSkills(pluginDir, overrides) {
  const skillsDir = path.join(pluginDir, 'skills');
  const out = [];
  for (const name of dirs(skillsDir)) {
    const file = path.join(skillsDir, name, 'SKILL.md');
    if (!exists(file)) continue;
    const fm = frontmatter(fs.readFileSync(file, 'utf8'));
    const author =
      (overrides.skillAuthors && overrides.skillAuthors[name]) ||
      (fm.metadata && fm.metadata.author) ||
      overrides.author ||
      '';
    // A shorter display blurb may be curated in store-meta.json; otherwise the
    // SKILL.md frontmatter is authoritative, so new skills need no curation.
    const description =
      (overrides.skillDescriptions && overrides.skillDescriptions[name]) ||
      (fm.description || '').trim();
    out.push({ name: fm.name || name, author, description });
  }
  return out;
}

function scanPlugins(meta) {
  const list = [];
  for (const id of dirs(PLUGINS_DIR)) {
    const dir = path.join(PLUGINS_DIR, id);
    const manifest = path.join(dir, 'plugin.json');
    if (!exists(manifest)) {
      console.warn(`  ! skipping plugins/${id} — no plugin.json`);
      continue;
    }
    const pj = readJSON(manifest);
    const ov = (meta.plugins && meta.plugins[id]) || {};
    const skills = readSkills(dir, ov);

    list.push({
      id,
      name: ov.name || titleCase(pj.name || id),
      icon: ov.icon || '\u{1F9E9}',
      accent: ov.accent || 'brand',
      category: ov.category || 'Uncategorised',
      tagline: ov.tagline || (pj.description || '').split('. ')[0],
      description: pj.description || '',
      version: pj.version || '1.0.0',
      license: pj.license || 'MIT',
      author: ov.author || meta.store?.author || '',
      path: `plugins/${id}`,
      docCount: countMarkdown(dir),
      tags: ov.tags || [],
      highlights: ov.highlights || skills.map((s) => s.description.split('. ')[0]).slice(0, 4),
      skills,
    });
  }
  return list;
}

function scanMCP(meta) {
  const list = [];
  for (const id of dirs(MCP_DIR)) {
    const manifest = path.join(MCP_DIR, id, 'mcp.json');
    if (!exists(manifest)) continue;
    const mj = readJSON(manifest);
    const ov = (meta.mcp && meta.mcp[id]) || {};
    list.push({
      id,
      name: ov.name || mj.displayName || titleCase(mj.name || id),
      icon: ov.icon || '\u{1F50C}',
      accent: ov.accent || 'orange',
      category: ov.category || 'MCP Servers',
      tagline: ov.tagline || (mj.description || '').split('. ')[0],
      description: mj.description || '',
      version: mj.version || '1.0.0',
      license: mj.license || 'MIT',
      author: ov.author || meta.store?.author || '',
      path: `mcp/${id}`,
      docCount: countMarkdown(path.join(MCP_DIR, id)),
      tags: ov.tags || ['mcp', 'server'],
      highlights: ov.highlights || (mj.tools || []).map((t) => t.name || String(t)).slice(0, 4),
      type: 'mcp',
      skills: (mj.tools || []).map((t) => ({
        name: t.name || String(t),
        author: ov.author || meta.store?.author || '',
        description: t.description || '',
      })),
    });
  }
  return list;
}

/* ---------------------------------------------------------------- outputs */

function buildCatalog(meta, entries) {
  const wanted = meta.categoryOrder || ['All'];
  const present = [...new Set(entries.map((e) => e.category))];
  const categories = ['All'];
  for (const c of wanted) if (c !== 'All' && present.includes(c)) categories.push(c);
  for (const c of present.sort()) if (!categories.includes(c)) categories.push(c);

  const order = new Map((meta.categoryOrder || []).map((c, i) => [c, i]));
  const sorted = [...entries].sort((a, b) => {
    const d = (order.get(a.category) ?? 99) - (order.get(b.category) ?? 99);
    return d || a.name.localeCompare(b.name);
  });

  return { store: meta.store, categories, plugins: sorted };
}

function buildMarketplace(meta, entries) {
  const s = meta.store || {};
  return {
    name: s.marketplace || 'VikiAgentStore',
    metadata: {
      description: meta.marketplaceDescription || s.description || '',
      version: meta.marketplaceVersion || '1.0.0',
    },
    owner: meta.owner || { name: s.author || '', email: '' },
    plugins: entries
      .filter((e) => e.type !== 'mcp')
      .map((e) => ({
        name: e.id,
        source: e.path,
        description: e.description,
        version: e.version,
      })),
  };
}

/* ------------------------------------------------------------------- main */

const serialize = (o) => JSON.stringify(o, null, 2) + '\n';

function writeOrCheck(file, content) {
  const rel = path.relative(ROOT, file);
  const current = exists(file) ? fs.readFileSync(file, 'utf8') : null;
  if (current === content) { console.log(`  = ${rel} (up to date)`); return false; }
  if (CHECK) { console.error(`  ! ${rel} is OUT OF DATE`); return true; }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
  console.log(`  ${current === null ? '+' : '~'} ${rel}`);
  return true;
}

function main() {
  const meta = readJSON(META_FILE);
  const entries = [...scanPlugins(meta), ...scanMCP(meta)];

  const plugins = entries.filter((e) => e.type !== 'mcp');
  const mcp = entries.filter((e) => e.type === 'mcp');
  const skills = entries.reduce((n, e) => n + e.skills.length, 0);
  console.log(
    `\nscanned ${plugins.length} plugin(s), ${mcp.length} MCP server(s), ${skills} skill(s)\n`
  );

  let stale = false;
  stale = writeOrCheck(CATALOG_OUT, serialize(buildCatalog(meta, entries))) || stale;
  stale = writeOrCheck(MARKETPLACE_OUT, serialize(buildMarketplace(meta, entries))) || stale;

  if (CHECK && stale) {
    console.error('\nGenerated files are out of date. Run: node scripts/generate-catalog.mjs\n');
    process.exit(1);
  }
  console.log(CHECK ? '\nup to date\n' : '\ndone\n');
}

main();
