/**
 * A meadow.
 *
 * Same contract as `StreetSet` -- `{pack, camX, W, Hgt}`, parallax by depth,
 * everything derived from the pack so a colour change is one edit -- but built
 * out of soft horizontals instead of hard verticals, because a picnic staged
 * against a skyline reads as a lunch break rather than a day out.
 *
 * The layer order is the whole trick to depth without any painting: sky,
 * hills, tree line, ground, then a foreground grass band that the characters
 * stand BEHIND at the ankles. That last band is what stops them looking pasted
 * on top of a photograph of a field.
 */

import React from 'react';
import {Layer, Cloud, Tree, rim, spread, jitter} from './Sets.jsx';

/** A rolling hill: one wide, very flat arc. Hills are not semicircles. */
const Hill = ({x, w, h, ground, fill}) => (
  <path
    d={`M${x - w} ${ground} Q ${x - w * 0.45} ${ground - h}, ${x} ${ground - h * 0.92}
        Q ${x + w * 0.5} ${ground - h * 0.82}, ${x + w} ${ground} Z`}
    fill={fill}
  />
);

/** A distant conifer. Three stacked triangles; anything more is invisible at
 *  this scale and just costs draw calls. */
const Conifer = ({x, s, ground, fill}) => (
  <g transform={`translate(${x} ${ground}) scale(${s})`}>
    <rect x={-5} y={-30} width={10} height={30} fill={fill} />
    <path d="M0 -150 L34 -74 L-34 -74 Z" fill={fill} />
    <path d="M0 -112 L40 -40 L-40 -40 Z" fill={fill} />
    <path d="M0 -76 L46 -6 L-46 -6 Z" fill={fill} />
  </g>
);

/** A tuft of grass. Blades fan from one root, which is why they share an x. */
const Tuft = ({x, y, s, fill, lean = 0}) => (
  <g transform={`translate(${x} ${y}) scale(${s}) rotate(${lean})`}>
    {[-16, -8, 0, 9, 17].map((dx, i) => {
      const h = 34 - Math.abs(dx) * 0.8;
      return (
        <path key={i} d={`M0 0 Q ${dx * 0.5} ${-h * 0.6}, ${dx} ${-h} Q ${dx * 0.35} ${-h * 0.55}, 0 0 Z`} fill={fill} />
      );
    })}
  </g>
);

const Flower = ({x, y, s, stem, petal, heart}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <path d="M0 0 Q 3 -16, 1 -30" stroke={stem} strokeWidth="3" fill="none" strokeLinecap="round" />
    {[0, 1, 2, 3, 4].map((i) => (
      <ellipse key={i} cx={0} cy={-38} rx={4.4} ry={7.6} fill={petal}
               transform={`rotate(${i * 72} 0 -30)`} />
    ))}
    <circle cx={1} cy={-30} r={3.4} fill={heart} />
  </g>
);

/**
 * The picnic blanket.
 *
 * Drawn as a squashed quad rather than a rectangle, because the ground plane
 * is being seen at a shallow angle and a true rectangle reads as a wall. The
 * check is clipped to the quad so the pattern shares its perspective instead
 * of floating in screen space.
 */
export const Blanket = ({x, ground, w = 620, s = 1, look}) => {
  const a = look.blanket ?? '#e2574c';
  const b = look.blanketAlt ?? '#f6efe2';
  const id = `bl${Math.round(x)}`;
  const hw = w / 2;
  const d = `M${-hw} 0 L${hw} 0 L${hw * 0.72} ${-58} L${-hw * 0.72} ${-58} Z`;
  return (
    <g transform={`translate(${x} ${ground}) scale(${s})`}>
      <defs>
        <clipPath id={id}>
          <path d={d} />
        </clipPath>
      </defs>
      <path d={d} fill={b} />
      <g clipPath={`url(#${id})`}>
        {Array.from({length: 9}, (_, i) => (
          <rect key={`v${i}`} x={-hw + i * (w / 9)} y={-70} width={w / 18} height={80} fill={a} opacity={0.85} />
        ))}
        {Array.from({length: 4}, (_, i) => (
          <rect key={`h${i}`} x={-hw} y={-62 + i * 17} width={w} height={8} fill={a} opacity={0.6} />
        ))}
      </g>
      {/* A blanket on grass is not flat. The lifted corners are the only thing
          in the shot admitting there is fabric involved. */}
      <path d={`M${-hw} 0 q ${-16} ${-10}, ${-4} ${-24} l 18 6 z`} fill={b} />
      <path d={`M${hw} 0 q ${16} ${-10}, ${4} ${-24} l ${-18} 6 z`} fill={b} />
    </g>
  );
};

export const Basket = ({x, ground, s = 1, look}) => {
  const c = look.basket ?? '#c98a3c';
  const dark = look.basketDark ?? '#a26a26';
  return (
    <g transform={`translate(${x} ${ground}) scale(${s})`}>
      <path d="M-42 -66 a 42 42 0 0 1 84 0" stroke={dark} strokeWidth="7" fill="none" />
      <path d="M-46 -60 L46 -60 L38 0 L-38 0 Z" fill={c} />
      {[-28, -14, 0, 14, 28].map((dx, i) => (
        <rect key={i} x={dx - 2} y={-58} width={4} height={56} fill={dark} opacity={0.45} />
      ))}
      <rect x={-50} y={-66} width={100} height={12} rx={5} fill={dark} />
    </g>
  );
};

/** Meadow colour roles, derived from the pack so the set inherits the grade. */
const meadowWorld = (pack) => {
  const w = pack.world;
  return {
    ...w,
    grass: w.grass ?? w.leafDeep ?? w.mid,
    grassLit: w.grassLit ?? w.leaf ?? w.accent,
    hillFar: w.hillFar ?? w.mid,
    hillNear: w.hillNear ?? w.leafDeep ?? w.mid,
  };
};

export const MeadowSet = ({pack, camX = 0, W, Hgt, seed = 11}) => {
  const world = meadowWorld(pack);
  const ground = Hgt * pack.ground;

  /**
   * Cloud height is measured UP FROM THE GROUND, not down from the top of the
   * frame.
   *
   * A film scales the whole scene about its ground line to fill the sky, and
   * anything positioned in raw screen space gets multiplied away from that
   * line along with everything else. Screen y=150 at a framing scale of 1.5
   * lands at -207: above the top edge, invisible, and the sky the scale was
   * supposed to fill comes out emptier than before it was applied.
   */
  const clouds = spread(camX, 0.06, W, 660).map(({i, x}) => {
    const r = jitter(i, seed + 3);
    return {key: i, x: x + r() * 280, y: ground - (300 + r() * 230), s: 0.8 + r() * 1.1};
  });
  const conifers = spread(camX, 0.3, W, 150).map(({i, x}) => {
    const r = jitter(i, seed + 5);
    return {key: i, x, s: 0.7 + r() * 0.7, y: ground - 40 - r() * 26};
  });
  const trees = spread(camX, 0.62, W, 720).map(({i, x}) => {
    const r = jitter(i, seed + 7);
    return {key: i, x, s: 0.62 + r() * 0.3};
  });
  const tufts = spread(camX, 1, W, 96).map(({i, x}) => {
    const r = jitter(i, seed + 11);
    return {key: i, x, s: 0.7 + r() * 0.8, lean: -14 + r() * 28, y: ground + 6 + r() * 26};
  });
  const flowers = spread(camX, 1, W, 260).map(({i, x}) => {
    const r = jitter(i, seed + 13);
    return {key: i, x: x + r() * 90, s: 0.7 + r() * 0.5, y: ground + 10 + r() * 22, warm: r() > 0.5};
  });

  return (
    <g>
      <defs>
        <linearGradient id="mdsky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={pack.sky[0]} />
          <stop offset="100%" stopColor={pack.sky[1]} />
        </linearGradient>
        <linearGradient id="mdground" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={world.grassLit} />
          <stop offset="100%" stopColor={world.grass} />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={W} height={Hgt} fill="url(#mdsky)" />

      <Layer depth={0.06} camX={camX}>
        {clouds.map((c) => (
          <Cloud key={c.key} x={c.x} y={c.y} s={c.s} fill={pack.sky[0]} />
        ))}
      </Layer>

      {/* Hills sit ON the horizon, not on the ground line -- a hill whose base
          is at the character's feet is a wall behind them. */}
      <Layer depth={0.16} camX={camX}>
        <g opacity="0.5">
          <Hill x={W * 0.18} w={W * 0.5} h={Hgt * 0.16} ground={ground - 30} fill={world.hillFar} />
          <Hill x={W * 0.78} w={W * 0.56} h={Hgt * 0.2} ground={ground - 30} fill={world.hillFar} />
        </g>
      </Layer>

      <Layer depth={0.3} camX={camX}>
        <g opacity="0.72">
          {conifers.map((c) => (
            <Conifer key={c.key} x={c.x} s={c.s} ground={c.y} fill={world.hillNear} />
          ))}
        </g>
      </Layer>

      {/* The ground plane. Everything above this line is distance; everything
          below is the field the characters are actually standing in. */}
      <rect x={0} y={ground - 34} width={W} height={Hgt - ground + 40} fill="url(#mdground)" />
      <path
        d={`M0 ${ground - 34} Q ${W * 0.3} ${ground - 52}, ${W * 0.62} ${ground - 32} T ${W} ${ground - 40} L${W} ${ground} L0 ${ground} Z`}
        fill={world.grassLit}
        opacity="0.5"
      />

      <Layer depth={0.62} camX={camX}>
        {trees.map((t) => (
          <Tree key={t.key} x={t.x} s={t.s} ground={ground - 18} world={world} />
        ))}
      </Layer>

      <Layer depth={1} camX={camX}>
        <g opacity="0.85">
          {tufts.filter((_, i) => i % 2 === 0).map((g) => (
            <Tuft key={g.key} x={g.x} y={g.y - 30} s={g.s * 0.7} fill={world.grass} lean={g.lean} />
          ))}
        </g>
      </Layer>
    </g>
  );
};

/**
 * The band of grass the cast stands behind.
 *
 * Drawn after the characters. Their shoes disappear a few pixels into it,
 * which is the cheapest possible way to seat a figure in a scene -- and the
 * only one here, since nothing casts a real shadow.
 */
export const MeadowForeground = ({pack, camX = 0, W, Hgt, seed = 11}) => {
  const world = meadowWorld(pack);
  const ground = Hgt * pack.ground;
  const tufts = spread(camX, 1.12, W, 84).map(({i, x}) => {
    const r = jitter(i, seed + 17);
    return {key: i, x, s: 0.9 + r() * 1.1, lean: -18 + r() * 36, y: ground + 14 + r() * 30};
  });
  const flowers = spread(camX, 1.12, W, 300).map(({i, x}) => {
    const r = jitter(i, seed + 19);
    return {key: i, x: x + r() * 120, s: 0.9 + r() * 0.7, y: ground + 20 + r() * 26, warm: r() > 0.5};
  });
  return (
    <Layer depth={1.12} camX={camX}>
      {tufts.map((g) => (
        <Tuft key={g.key} x={g.x} y={g.y} s={g.s} fill={rim(world, world.grass)} lean={g.lean} />
      ))}
      {flowers.map((f) => (
        <Flower key={`f${f.key}`} x={f.x} y={f.y} s={f.s}
                stem={world.grass}
                petal={f.warm ? (world.accent ?? '#f2b134') : (pack.sky[0] ?? '#fff')}
                heart={world.accent2 ?? '#f6efe2'} />
      ))}
    </Layer>
  );
};
