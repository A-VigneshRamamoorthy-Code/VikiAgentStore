#!/usr/bin/env node
/**
 * fetch-source.mjs — read sources that refuse a plain HTTP request.
 *
 * A large share of the outlets worth citing (major newspapers, encyclopaedias,
 * government portals) answer `curl` with a bot-challenge page instead of an
 * article. This fetches them through a real browser engine and writes the
 * readable text to disk, plus a manifest you can lift straight into
 * `ledger.json`.
 *
 *   node fetch-source.mjs targets.json out/
 *   node fetch-source.mjs out/ britannica=https://www.britannica.com/event/...
 *
 * `targets.json` is a flat object of `{ "source-id": "url" }`, and the
 * source-ids should be the ids you intend to use in the ledger.
 *
 * The browser is ALWAYS headless. It never opens a window.
 *
 * Requires Playwright's Chromium, which is not a dependency of this skill:
 *
 *   npm i --no-save playwright-core
 *   npx playwright install chromium --only-shell
 *
 * `scriptcheck.py` has no dependencies at all; only this optional helper does.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const NAV_TIMEOUT = 75_000;
const SETTLE_MS = 2_500;

function cacheRoot() {
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) return process.env.PLAYWRIGHT_BROWSERS_PATH;
  const home = os.homedir();
  if (process.platform === 'darwin') return path.join(home, 'Library/Caches/ms-playwright');
  if (process.platform === 'win32') return path.join(home, 'AppData/Local/ms-playwright');
  return path.join(home, '.cache/ms-playwright');
}

/**
 * Locate a headless Chromium shell. Returns undefined so Playwright can fall
 * back to its own resolution if nothing is found here.
 */
function headlessShell() {
  const root = cacheRoot();
  let dirs;
  try {
    dirs = fs.readdirSync(root).filter((d) => d.startsWith('chromium')).sort().reverse();
  } catch {
    return undefined;
  }
  const names = ['chrome-headless-shell', 'headless_shell', 'chrome-headless-shell.exe'];
  for (const dir of dirs) {
    const base = path.join(root, dir);
    let subs;
    try {
      subs = fs.readdirSync(base);
    } catch {
      continue;
    }
    for (const sub of subs) {
      for (const bin of names) {
        const p = path.join(base, sub, bin);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return undefined;
}

function parseArgs(argv) {
  const targets = {};
  let outDir = null;
  for (const arg of argv) {
    const eq = arg.indexOf('=');
    if (eq > 0 && /^https?:/.test(arg.slice(eq + 1))) {
      targets[arg.slice(0, eq)] = arg.slice(eq + 1);
    } else if (arg.endsWith('.json') && fs.existsSync(arg)) {
      Object.assign(targets, JSON.parse(fs.readFileSync(arg, 'utf8')));
    } else {
      outDir = arg;
    }
  }
  return { targets, outDir: outDir || 'sources' };
}

const { targets, outDir } = parseArgs(process.argv.slice(2));
if (!Object.keys(targets).length) {
  console.error('usage: node fetch-source.mjs [targets.json] [out-dir] [id=url ...]');
  process.exit(2);
}

let chromium;
try {
  chromium = await loadChromium();
} catch {
  chromium = null;
}
if (!chromium) {
  console.error('playwright-core is not installed.\n  npm i --no-save playwright-core');
  console.error('  npx playwright install chromium --only-shell');
  process.exit(2);
}

/** Resolve playwright-core from the cwd, then from NODE_PATH, then from this file. */
async function loadChromium() {
  const pick = (m) => (m && (m.chromium || (m.default && m.default.chromium))) || null;
  try {
    const found = pick(await import('playwright-core'));
    if (found) return found;
  } catch {
    /* fall through to explicit resolution */
  }
  const roots = [
    path.join(process.cwd(), 'node_modules'),
    ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean),
  ];
  for (const root of roots) {
    const entry = path.join(root, 'playwright-core', 'index.js');
    if (!fs.existsSync(entry)) continue;
    try {
      const found = pick(await import(pathToFileURL(entry).href));
      if (found) return found;
    } catch {
      /* try the next root */
    }
  }
  return null;
}

fs.mkdirSync(outDir, { recursive: true });
const accessed = new Date().toISOString().slice(0, 10);

const browser = await chromium.launch({
  headless: true,
  executablePath: headlessShell(),
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const ctx = await browser.newContext({ userAgent: UA, viewport: { width: 1280, height: 900 } });

const manifest = [];
for (const [id, url] of Object.entries(targets)) {
  const page = await ctx.newPage();
  const record = { id, url, accessed, ok: false };
  try {
    const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    await page.waitForTimeout(SETTLE_MS);
    record.status = res ? res.status() : null;
    record.title = await page.title();
    const text = await page.evaluate(() => {
      document
        .querySelectorAll('script,style,noscript,nav,header,footer,aside,form')
        .forEach((el) => el.remove());
      return document.body ? document.body.innerText.replace(/\s+/g, ' ').trim() : '';
    });
    const file = path.join(outDir, `${id}.txt`);
    fs.writeFileSync(file, text);
    record.file = file;
    record.chars = text.length;
    // A challenge or error page is short and must not be mistaken for an article.
    record.ok = text.length > 1200;
    console.log(
      `${record.ok ? 'OK  ' : 'THIN'} ${String(text.length).padStart(7)}  ${id}` +
        (record.ok ? '' : '  <- probably a challenge or error page, check it')
    );
  } catch (e) {
    record.error = String(e.message).split('\n')[0].slice(0, 120);
    console.log(`FAIL          -  ${id}  ${record.error}`);
  } finally {
    manifest.push(record);
    await page.close();
  }
}

await browser.close();

fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
const good = manifest.filter((r) => r.ok).length;
console.log(`\n${good}/${manifest.length} usable · manifest at ${path.join(outDir, 'manifest.json')}`);
console.log('A source that failed here is not a source. Record the failure and demote the claim.');
process.exit(good === manifest.length ? 0 : 1);
