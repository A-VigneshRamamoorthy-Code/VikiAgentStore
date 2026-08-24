#!/usr/bin/env node
/**
 * Time the two renderers on the same board.
 *
 * The comparison is only worth anything if the *only* difference is the
 * picture pipeline, so both sides render the same `examples/pursuit/board.json`
 * at the same size and frame rate, and both render video only -- the mix is
 * built by the same Python `audio.py` either way and would just add a constant
 * to both columns.
 *
 *   node bench.mjs                 # the whole film, 1920x1080
 *   node bench.mjs --seconds 20    # a shorter slice, for a quick answer
 *   node bench.mjs --skip-python   # re-time the port on its own
 *
 * Wall clock is the headline, but CPU seconds are the interesting number:
 * they say whether a renderer is *using* the cores it was given. See README.md.
 */

import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.dirname(HERE);
const BOARD = path.join(SKILL, 'examples', 'pursuit', 'board.json');
const OUT = path.join(HERE, 'out');

const argv = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i === -1 ? fallback : argv[i + 1];
};
const has = (name) => argv.includes(`--${name}`);

const seconds = Number(flag('seconds', 0)) || null;
const concurrency = Number(flag('concurrency', 4));
const jobs = Number(flag('jobs', 4));
const width = Number(flag('width', 1920));
const height = Number(flag('height', 1080));

// The film's own length, read from the camera trace rather than hardcoded, so
// re-timing the board re-times the benchmark.
const cameraTrace = JSON.parse(
  readFileSync(path.join(HERE, 'src', 'generated', 'camera.json'), 'utf8'));
const TOTAL_SECONDS = cameraTrace.total / cameraTrace.fps;

/**
 * Run a command and return `{wall, user, sys}` in seconds.
 *
 * `/usr/bin/time -p` is used rather than timing in Node because the child's
 * CPU time is the point: a renderer that takes 600 s of wall clock and 607 s
 * of CPU never left one core, however many workers it was asked for.
 */
function timed(label, cmd, args, opts = {}) {
  process.stdout.write(`\n▸ ${label}\n  ${cmd} ${args.join(' ')}\n`);
  const started = Date.now();
  const r = spawnSync('/usr/bin/time', ['-p', cmd, ...args], {
    stdio: ['ignore', 'inherit', 'pipe'],
    encoding: 'utf8',
    ...opts,
  });
  const wall = (Date.now() - started) / 1000;
  const err = r.stderr ?? '';
  const num = (k) => {
    const m = err.match(new RegExp(`^${k}\\s+([0-9.]+)`, 'm'));
    return m ? Number(m[1]) : null;
  };
  if (r.status !== 0) {
    process.stderr.write(err.split('\n').slice(-25).join('\n') + '\n');
    throw new Error(`${label} exited ${r.status}`);
  }
  return {wall: num('real') ?? wall, user: num('user'), sys: num('sys')};
}

if (!existsSync(OUT)) mkdirSync(OUT, {recursive: true});

// `--clip` is the engine's own "video only, full resolution" path, which is
// what makes this an apples-to-apples picture benchmark. With no `--seconds`
// the whole film is clipped, which costs nothing and keeps both sides silent.
const clip = ['--clip', '0', String(seconds ?? TOTAL_SECONDS)];
const results = {};

if (!has('skip-python')) {
  results.python = timed(
    `Python renderer  (-j ${jobs}, video only)`,
    'python3',
    [path.join(SKILL, 'scripts', 'render.py'), BOARD,
     '-o', path.join(OUT, 'bench_python.mp4'),
     '-j', String(jobs), '--force', ...clip],
  );
}

if (!has('skip-remotion')) {
  const frames = seconds ? ['--frames', `0-${Math.round(seconds * 30) - 1}`] : [];
  results.remotion = timed(
    `Remotion renderer (--concurrency ${concurrency})`,
    'npx',
    ['remotion', 'render', 'src/index.jsx', 'Pursuit',
     path.join(OUT, 'bench_remotion.mp4'),
     `--concurrency=${concurrency}`, '--log=error', ...frames],
    {cwd: HERE},
  );
}

const row = (name, r) => {
  const par = r.user != null && r.wall ? (r.user + (r.sys ?? 0)) / r.wall : null;
  return `  ${name.padEnd(10)} ${r.wall.toFixed(2).padStart(9)} s ` +
    `${(r.user ?? 0).toFixed(2).padStart(9)} s ` +
    `${(r.sys ?? 0).toFixed(2).padStart(8)} s ` +
    `${par ? par.toFixed(2).padStart(7) : '      -'}`;
};

console.log(`\n${'='.repeat(62)}`);
console.log(`  ${width}x${height} @30${seconds ? `, first ${seconds}s` : ', full film'}`);
console.log(`  ${'renderer'.padEnd(10)} ${'wall'.padStart(11)} ${'user CPU'.padStart(11)} ` +
            `${'sys'.padStart(10)} ${'cores'.padStart(7)}`);
if (results.python) console.log(row('python', results.python));
if (results.remotion) console.log(row('remotion', results.remotion));
if (results.python && results.remotion) {
  const x = results.python.wall / results.remotion.wall;
  console.log(`\n  Remotion is ${x.toFixed(1)}x faster in wall clock.`);
  console.log('  "cores" is (user+sys)/wall -- how many cores the renderer');
  console.log('  actually kept busy, which is where the difference comes from.');
}
console.log('='.repeat(62));
