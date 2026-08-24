import React from 'react';

/**
 * Sets, drawn in the same ink language as the cast.
 *
 * These are authored here rather than imported from a stock library, and that
 * is a deliberate reversal of where the characters come from. Character art is
 * worth importing because a good face is hard and Open Peeps already drew 53 of
 * them. Backgrounds are not worth importing, because the thing that makes a
 * background good is that it *matches the characters standing in front of it* —
 * and no stock pack matches anything.
 *
 * Mixing sources is exactly how a film ends up looking assembled instead of
 * drawn: pixel-art scenery behind an ink figure, four different line weights,
 * a sky from one artist and a pavement from another. So the sets take their
 * ink colour, their accent and their greens from the same pack the cast does,
 * and there is no path by which they can disagree.
 *
 * Everything is a pure function of `(pack, camera)`. There is no randomness at
 * render time — layouts are derived from a seed so a frame is reproducible,
 * which is what makes a re-render comparable to the one before it.
 */

const mulberry = (seed) => {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/**
 * One parallax layer.
 *
 * `depth` is how much of the camera's movement this layer receives: 0 is
 * painted on the lens, 1 travels with the ground. Everything else follows from
 * that one number, including the desaturation, because things that are far
 * away are both slower and paler and it is a mistake to let those two drift
 * apart.
 */
const Layer = ({depth, camX, children}) => (
  <g transform={`translate(${(-camX * depth).toFixed(2)} 0)`}>{children}</g>
);

/**
 * The rim colour for a shape.
 *
 * These sets have no strokes: the outline you see is a copy of the shape in
 * ink, drawn behind and a few pixels proud. That is the right look for an ink
 * pack and the wrong one for a flat pack, where the art has no outlines at all
 * and a rim reads as a halo around every building.
 *
 * So a pack says `world.rim: false` and every rim collapses into its own fill,
 * which costs one draw call and keeps the geometry identical between packs.
 */
const rim = (world, own) => (world.rim === false ? own : world.ink);

/* ── pieces ──────────────────────────────────────────────────────────────── */

const Building = ({x, w, h, fill, ink, windowFill, seed, ground}) => {
  const rnd = mulberry(seed);
  const cols = Math.max(2, Math.round(w / 120));
  const rows = Math.max(2, Math.round(h / 150));
  const wins = [];
  const mw = w / (cols + 1);
  const mh = h / (rows + 0.8);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (rnd() < 0.22) continue;
      wins.push(
        <rect
          key={`${r}-${c}`}
          x={x + mw * 0.6 + c * mw * ((cols + 1) / cols) * 0.92}
          y={ground - h + 60 + r * mh}
          width={mw * 0.52}
          height={mh * 0.46}
          fill={windowFill}
          opacity={0.75 + rnd() * 0.25}
        />
      );
    }
  }
  return (
    <g>
      <rect x={x} y={ground - h} width={w} height={h} fill={ink} />
      <rect x={x + 7} y={ground - h + 7} width={w - 14} height={h} fill={fill} />
      {wins}
    </g>
  );
};

const Tree = ({x, s, ground, world}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    <path d="M-16 0 L-11 -170 L11 -170 L16 0 z" fill={rim(world, world.trunk)} />
    <path d="M-11 0 L-7 -166 L7 -166 L11 0 z" fill={world.trunk} />
    <circle cx="0" cy="-232" r="118" fill={rim(world, world.leaf)} />
    <circle cx="-74" cy="-186" r="84" fill={rim(world, world.leafDeep)} />
    <circle cx="76" cy="-192" r="80" fill={rim(world, world.leaf)} />
    <circle cx="0" cy="-232" r="107" fill={world.leaf} />
    <circle cx="-74" cy="-186" r="73" fill={world.leafDeep} />
    <circle cx="76" cy="-192" r="69" fill={world.leaf} />
  </g>
);

const Lamppost = ({x, ground, world, s = 1}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    <path d="M-9 0 L-9 -430 L9 -430 L9 0 z" fill={world.ink} />
    <path d="M-9 -430 q0 -46 62 -46 l0 20 q-42 0 -42 26 z" fill={world.ink} />
    <ellipse cx="66" cy="-455" rx="26" ry="17" fill={world.ink} />
    <ellipse cx="66" cy="-457" rx="19" ry="11" fill={world.accent} />
  </g>
);

const Bench = ({x, ground, world, s = 1}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    <path d="M-124 0 L-108 0 L-108 -78 L-124 -78 z" fill={world.ink} />
    <path d="M108 0 L124 0 L124 -78 L108 -78 z" fill={world.ink} />
    {[0, 1, 2].map((i) => (
      <rect key={i} x={-134} y={-96 - i * 30} width={268} height={20} rx={8} fill={world.ink} />
    ))}
    {[0, 1, 2].map((i) => (
      <rect key={i} x={-129} y={-92 - i * 30} width={258} height={12} rx={6} fill={world.accent} opacity={0.85} />
    ))}
    <rect x={-134} y={-78} width={268} height={20} rx={8} fill={world.ink} />
    <rect x={-129} y={-74} width={258} height={12} rx={6} fill={world.accent} opacity={0.85} />
  </g>
);

const Cloud = ({x, y, s, fill}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity="0.55">
    <circle cx="0" cy="0" r="46" fill={fill} />
    <circle cx="52" cy="10" r="34" fill={fill} />
    <circle cx="-48" cy="12" r="30" fill={fill} />
    <rect x="-48" y="8" width="102" height="34" rx="17" fill={fill} />
  </g>
);

/* ── the street ──────────────────────────────────────────────────────────── */

/**
 * A city street, built once per pack and then only translated.
 *
 * The layout is generated from a seed and cached by the caller, so the same
 * building is the same building in every shot of a film. A set that regenerates
 * per frame is the most expensive kind of inconsistency there is, because it
 * looks like the world is boiling.
 */
/**
 * The indices of a repeating element that are visible right now.
 *
 * Every layer in this set used to be a fixed array built once around x=0 —
 * forty railings, eight trees, buildings out to `W + 2400`. That is fine until
 * somebody walks further than the array is long, at which point the world
 * simply stops and the character runs off the end of their own street. It
 * happened at about twenty seconds of a thirty-second film.
 *
 * So elements are generated from the camera instead: given the parallax offset
 * this layer actually has, emit exactly the tiles that land on screen. The
 * street is then endless in both directions and costs no more to draw, and a
 * film can travel as far as it likes.
 */
const spread = (camX, depth, W, period, x0 = 0, margin = 600) => {
  const lo = Math.floor((camX * depth - margin - x0) / period);
  const hi = Math.ceil((camX * depth + W + margin - x0) / period);
  const out = [];
  for (let i = lo; i <= hi; i++) out.push({i, x: x0 + i * period});
  return out;
};

/** Deterministic per-tile jitter: same index, same building, forever. */
const jitter = (i, salt) => {
  const r = mulberry(((i * 2654435761) ^ (salt * 40503)) >>> 0);
  r();
  return r;
};

export const StreetSet = ({pack, camX = 0, W, Hgt, seed = 7}) => {
  const world = pack.world;
  const ground = Hgt * pack.ground;

  const far = spread(camX, 0.26, W, 210).map(({i, x}) => {
    const r = jitter(i, seed + 1);
    return {key: i, x, w: 130 + r() * 120, h: 330 + r() * 300, seed: seed + i * 13};
  });
  const mid = spread(camX, 0.52, W, 420).map(({i, x}) => {
    const r = jitter(i, seed + 2);
    return {key: i, x, w: 250 + r() * 200, h: 420 + r() * 340, seed: seed + 500 + i * 29};
  });
  const clouds = spread(camX, 0.08, W, 620).map(({i, x}) => {
    const r = jitter(i, seed + 3);
    return {key: i, x: x + r() * 260, y: 90 + r() * 210, s: 0.7 + r() * 0.9};
  });

  return (
    <g>
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={pack.sky[0]} />
          <stop offset="100%" stopColor={pack.sky[1]} />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={W} height={Hgt} fill="url(#sky)" />

      <Layer depth={0.08} camX={camX}>
        {clouds.map((c) => (
          <Cloud key={c.key} x={c.x} y={c.y} s={c.s} fill={pack.sky[0]} />
        ))}
      </Layer>

      <Layer depth={0.26} camX={camX}>
        <g opacity="0.55">
          {far.map((b) => (
            <Building key={b.key} {...b} ground={ground - 40} fill={world.far} ink={world.far}
                      windowFill={world.window} />
          ))}
        </g>
      </Layer>

      <Layer depth={0.52} camX={camX}>
        <g opacity="0.85">
          {mid.map((b) => (
            <Building key={b.key} {...b} ground={ground - 18} fill={world.mid} ink={rim(world, world.mid)}
                      windowFill={world.window} />
          ))}
        </g>
      </Layer>

      {/* Ground plane. Everything from here on travels with the characters,
          which is what makes them look like they are standing on it. */}
      <rect x={0} y={ground} width={W} height={Hgt - ground} fill={world.road} />
      <rect x={0} y={ground} width={W} height={9} fill={world.ink} />
      <rect x={0} y={ground + Hgt * 0.075} width={W} height={4} fill={world.kerb} opacity={0.7} />

      {/* Street furniture stands UPSTAGE of the acting line — a little higher
          on the plate and a little smaller — so the cast passes in front of it
          instead of through it. Sharing one ground line with the characters
          was cheap to write and looked exactly like what it was: a bench
          growing out of somebody's hip. */}
      <Layer depth={0.86} camX={camX}>
        {spread(camX, 0.86, W, 815, -500).map(({i, x}) => (
          <Tree key={i} x={x} s={0.82} ground={ground - 46} world={world} />
        ))}
      </Layer>

      {/* Depth 1, not 0.95. Anything RESTING on a plane must share that
          plane's parallax depth: the pavement below is drawn at depth 1, so a
          lamppost bolted to it travels at depth 1 too. At 0.95 the furniture
          slid slowly along the ground it was supposedly fixed to — and because
          the differential was only 5%, a lamppost that happened to line up
          behind somebody's head STAYED there for seconds at a time, which is
          the oldest bad composition there is. Stage furniture upstage with the
          ground line and scale instead; that is real depth, not fake parallax. */}
      <Layer depth={1} camX={camX}>
        {spread(camX, 1, W, 937, 210).map(({i, x}) => (
          <Lamppost key={i} x={x} ground={ground - 30} world={world} s={0.9} />
        ))}
        {spread(camX, 1, W, 1783, 1290).map(({i, x}) => (
          <Bench key={i} x={x} ground={ground - 28} world={world} s={0.9} />
        ))}
      </Layer>

      {/* The pavement the cast actually walks on, drawn after the furniture so
          its edge reads as being in front of it. */}
      <rect x={0} y={ground - 4} width={W} height={10} fill={world.ink} opacity={0.14} />

      {/* Road markings, on the deck itself. */}
      <Layer depth={1} camX={camX}>
        {spread(camX, 1, W, 260, -600).map(({i, x}) => (
          <rect key={i} x={x} y={ground + Hgt * 0.135} width={130} height={9}
                rx={4} fill={world.roadLine} opacity={0.75} />
        ))}
      </Layer>
    </g>
  );
};

/**
 * The layer that belongs IN FRONT of the cast.
 *
 * Depth in a flat drawing comes from overlap, and overlap only reads if
 * something occludes the actors as well as being occluded by them. With
 * scenery exclusively behind them, characters look like stickers on a
 * backdrop no matter how well the parallax is tuned.
 *
 * It is a kerbside railing, because a foreground element also has to be a
 * thing that would plausibly BE there — the first attempt put a hedge in the
 * middle of the carriageway, which occluded correctly and read as nonsense.
 * The railing runs along the kerb, crosses the actors at shin height, and
 * travels slightly faster than the ground.
 */
export const StreetForeground = ({pack, camX = 0, W, Hgt}) => {
  const world = pack.world;
  const ground = Hgt * pack.ground;
  const top = ground + Hgt * 0.038;
  const bottom = ground + Hgt * 0.105;
  return (
    <Layer depth={1.1} camX={camX}>
      {spread(camX, 1.1, W, 96, -1200).map(({i, x}) => (
        <rect key={i} x={x} y={top} width={11} height={bottom - top}
              rx={5} fill={world.ink} opacity={0.55} />
      ))}
      <rect x={camX * 1.1 - 700} y={top} width={W + 1400} height={13} rx={6}
            fill={world.ink} opacity={0.62} />
      <rect x={camX * 1.1 - 700} y={top + 30} width={W + 1400} height={9} rx={4}
            fill={world.ink} opacity={0.4} />
    </Layer>
  );
};
