import React from 'react';

/**
 * Replays recorded pen ops as SVG.
 *
 * `tools/trace-props.py` walks the Python renderer with a pen that records
 * instead of rasterising, so what arrives here is the engine's own artwork in
 * its own design units -- not a redrawing of it. This component is therefore
 * the entire "port": eleven primitives, and every prop in the film comes over
 * exactly as authored.
 *
 * Coordinates stay in design units and the caller supplies the transform,
 * which mirrors how the Python pen owns the only multiplication by `unit`.
 */

const pathOf = (pts, close) =>
  pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x} ${y}`).join('') + (close ? 'Z' : '');

const arcOf = (cx, cy, r, a0, a1) => {
  // Pillow's pieslice measures degrees clockwise from 3 o'clock, and y is
  // down in both systems, so the angles carry over untouched.
  const p0 = [cx + r * Math.cos((a0 * Math.PI) / 180), cy + r * Math.sin((a0 * Math.PI) / 180)];
  const p1 = [cx + r * Math.cos((a1 * Math.PI) / 180), cy + r * Math.sin((a1 * Math.PI) / 180)];
  const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
  return `M${cx} ${cy}L${p0[0]} ${p0[1]}A${r} ${r} 0 ${large} 1 ${p1[0]} ${p1[1]}Z`;
};

const Op = ({op, gid}) => {
  const {k, c, i, w, p, r} = op;

  switch (k) {
    case 'rect':
    case 'rrect': {
      const [[x0, y0], [x1, y1]] = p;
      const x = Math.min(x0, x1);
      const y = Math.min(y0, y1);
      const rw = Math.abs(x1 - x0);
      const rh = Math.abs(y1 - y0);
      const rad = k === 'rrect' ? Math.max(0, Math.min(r, rw / 2, rh / 2)) : undefined;
      return (
        <rect x={x} y={y} width={rw} height={rh} rx={rad} ry={rad}
              fill={c ?? 'none'} stroke={i ?? 'none'} strokeWidth={i ? w : undefined} />
      );
    }
    case 'poly':
      return (
        <path d={pathOf(p, true)} fill={c ?? 'none'} stroke={i ?? 'none'}
              strokeWidth={i ? w : undefined} strokeLinejoin="round" />
      );
    case 'ell':
      return (
        <ellipse cx={p[0][0]} cy={p[0][1]} rx={r[0]} ry={r[1]}
                 fill={c ?? 'none'} stroke={i ?? 'none'} strokeWidth={i ? w : undefined} />
      );
    case 'pie':
      return <path d={arcOf(p[0][0], p[0][1], r[0], op.a[0], op.a[1])} fill={c ?? 'none'} />;
    case 'line':
      return (
        <path d={pathOf(p, false)} fill="none" stroke={c} strokeWidth={w}
              strokeLinecap={op.cap === false ? 'butt' : 'round'} strokeLinejoin="round" />
      );
    case 'vgrad': {
      const id = `vg${gid}`;
      const y0 = op.y0 ?? -400;
      const y1 = op.y1 ?? 400;
      return (
        <>
          <defs>
            <linearGradient id={id} x1="0" y1={y0} x2="0" y2={y1} gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor={op.a} />
              <stop offset="1" stopColor={op.b} />
            </linearGradient>
          </defs>
          <rect x={-2000} y={y0} width={4000} height={y1 - y0} fill={`url(#${id})`} />
        </>
      );
    }
    case 'fill':
      return <rect x={-4000} y={-4000} width={8000} height={8000} fill={c} />;
    case 'text':
      return (
        <text x={p[0][0]} y={p[0][1]} fill={c} fontSize={op.sz}
              textAnchor="middle" dominantBaseline="middle"
              fontFamily="ui-sans-serif, system-ui, sans-serif">{op.s}</text>
      );
    default:
      return null;
  }
};

export const Vector = ({ops, idPrefix = 'v'}) => (
  <>
    {ops.map((op, n) => <Op key={n} op={op} gid={`${idPrefix}-${n}`} />)}
  </>
);
