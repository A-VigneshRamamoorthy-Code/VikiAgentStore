import React from 'react';
import {P} from './palette.js';
import {Ink, Hatch} from './Paper.jsx';

// One locked composition, held for the whole film. The reference never cuts
// and never moves the camera, so the set is built once and nothing in here
// ever animates.
//
// It is authored in world units and then framed by CAM (below) rather than
// being drawn straight into the 1920x1080 viewBox. Authoring at figure scale
// and framing afterwards is the only way to keep the proportions honest: a
// first pass drawn directly in screen space produced a correct-looking
// panorama in which the characters were 200px tall and read as ants.

export const GROUND = 858;

// Proportions come from the figure, not from taste. The rig is ~203 units
// tall, so a 45 cm bench seat on a 170 cm person lands at 26% of that.
export const SEAT_H = 58;
const BACK_H = 116;
const BENCH_LEN = 236;
export const BENCH_X = 794;

/**
 * The camera.
 *
 * A single scale-and-translate wrapped round the whole set. `scale` is what
 * decides how big a person is in frame -- at 1.8 a 203-unit figure is 365 px
 * of a 1080 frame, which is roughly where the reference puts its cast.
 *
 * The visible world window that falls out of this is x 379..1445, y 391..991,
 * and everything below is laid out to fill exactly that.
 */
export const CAM = {scale: 1.8, x: -681.6, y: -704.4};
export const cameraTransform = `translate(${CAM.x} ${CAM.y}) scale(${CAM.scale})`;

/** The terrace behind the park: drawn faint, so it reads as distance. */
const Terrace = () => {
  const blocks = [
    {x: 330, w: 200, h: 296}, {x: 540, w: 158, h: 372}, {x: 706, w: 220, h: 250},
    {x: 934, w: 148, h: 340}, {x: 1090, w: 196, h: 282}, {x: 1294, w: 170, h: 364},
    {x: 1472, w: 150, h: 272},
  ];
  return (
    <g filter="url(#pencilFar)" opacity="0.62">
      {blocks.map((b, i) => {
        const top = GROUND - b.h;
        // Derived, not hand-entered: a floor count typed in by hand drifts
        // out of agreement with the height the moment either is edited.
        const floors = Math.max(2, Math.floor((b.h - 90) / 56) + 1);
        const cols = Math.max(2, Math.ceil(b.w / 58));
        const win = [];
        for (let f = 0; f < floors; f++) {
          for (let c = 0; c < cols; c++) {
            const wx = b.x + 18 + c * 52;
            const wy = top + 32 + f * 56;
            if (wx + 26 > b.x + b.w - 12) continue;
            win.push(<rect key={`${f}-${c}`} x={wx} y={wy} width="26" height="32"
                           fill={P.wash} stroke={P.lineFaint} strokeWidth="1" />);
          }
        }
        return (
          <g key={i}>
            <rect x={b.x} y={top} width={b.w} height={b.h}
                  fill={P.paperDeep} stroke={P.lineFaint} strokeWidth="1.3" />
            <Ink d={`M${b.x - 10} ${top} L${b.x + b.w + 10} ${top}`} w={0} far />
            {win}
          </g>
        );
      })}
    </g>
  );
};

/** Park railing. Repetition drawn by hand always drifts; this drifts too. */
const Railing = () => {
  const posts = [];
  for (let x = 320; x < 1470; x += 54) {
    const lean = ((x * 13) % 7) / 7 - 0.5;          // deterministic drift
    posts.push(
      <g key={x}>
        <Ink d={`M${x} ${GROUND - 6} L${x + lean * 3} ${GROUND - 96}`} w={1} />
        <circle cx={x + lean * 3} cy={GROUND - 101} r="4.5"
                fill={P.paper} stroke={P.lineSoft} strokeWidth="1.4" />
      </g>,
    );
  }
  return (
    <g filter="url(#pencil)" opacity="0.8">
      {posts}
      <Ink d={`M300 ${GROUND - 86} L1500 ${GROUND - 89}`} w={1} />
      <Ink d={`M300 ${GROUND - 50} L1500 ${GROUND - 52}`} w={0} />
    </g>
  );
};

const Lamppost = ({x = 470}) => (
  <g filter="url(#pencil)">
    <Ink d={`M${x} ${GROUND} L${x + 4} 520`} w={2} />
    <Ink d={`M${x} ${GROUND} q-26 3 -40 7`} w={1} />
    <Ink d={`M${x} ${GROUND} q26 3 40 7`} w={1} />
    <path d={`M${x - 24} 520 q28 -28 56 0 l-6 23 q-22 -15 -44 0 z`}
          fill={P.paperDeep} stroke={P.line} strokeWidth="2.2" strokeLinejoin="round" />
    <Ink d={`M${x - 17} 499 q21 -18 42 0`} w={1} />
  </g>
);

/**
 * A plane tree, drawn trunk-first so the canopy has something to sit on.
 *
 * An earlier pass built the clumps at an arbitrary height and left them
 * floating a clear 150 units above the branches -- invisible while drawing,
 * unmissable in the render.
 */
const Tree = ({x: TX = 1290, top: TOP = 650}) => {
  const clumps = [
    [TX - 65, TOP - 23, 71], [TX + 4, TOP - 65, 79], [TX + 71, TOP - 18, 68],
    [TX - 23, TOP - 114, 65], [TX + 50, TOP - 102, 60], [TX + 102, TOP - 65, 53],
    [TX - 101, TOP - 71, 53],
  ];
  return (
    <g filter="url(#pencil)">
      <path d={`M${TX - 13} ${GROUND} q5 -120 2 -186 q-1 -34 -7 -52`}
            fill="none" stroke={P.line} strokeWidth="3.4" strokeLinecap="round" />
      <path d={`M${TX + 13} ${GROUND} q-5 -120 -1 -186 q2 -32 9 -50`}
            fill="none" stroke={P.line} strokeWidth="3.4" strokeLinecap="round" />
      <Ink d={`M${TX - 13} ${GROUND} q-34 5 -50 9`} w={1} />
      <Ink d={`M${TX + 13} ${GROUND} q34 5 50 9`} w={1} />
      {/* branches, each one reaching into a clump */}
      <Ink d={`M${TX - 9} ${TOP + 52} q-38 -20 -62 -42`} w={1} />
      <Ink d={`M${TX + 9} ${TOP + 30} q37 -19 60 -40`} w={1} />
      <Ink d={`M${TX} ${TOP + 14} q3 -34 1 -52`} w={1} />

      {clumps.map(([cx, cy, r], i) => (
        <circle key={i} cx={cx} cy={cy} r={r}
                fill={i % 2 ? P.paperDeep : P.paper}
                stroke={P.lineSoft} strokeWidth="1.9" opacity="0.97" />
      ))}
      {clumps.slice(0, 4).map(([cx, cy, r], i) => (
        <Hatch key={`h${i}`} id={`tree${i}`}
               d={`M${cx - r} ${cy} a${r} ${r} 0 1 0 ${r * 2} 0 a${r} ${r} 0 1 0 ${-r * 2} 0`}
               x={cx - r} y={cy - r} w={r * 2} h={r * 2} gap={10} opacity={0.14} />
      ))}
    </g>
  );
};

/** The paving the whole scene stands on. */
const Ground = () => {
  const slabs = [];
  for (let x = 300; x < 1560; x += 118) {
    slabs.push(<Ink key={x} d={`M${x} ${GROUND + 8} L${x - 42} 1010`} w={0} opacity={0.32} />);
  }
  return (
    <g filter="url(#pencil)">
      <rect x="200" y={GROUND} width="1500" height="220" fill={P.paperDeep} />
      <Ink d={`M280 ${GROUND} L1520 ${GROUND}`} w={2} />
      <Ink d={`M280 ${GROUND + 44} L1520 ${GROUND + 41}`} w={0} opacity={0.4} />
      {slabs}
    </g>
  );
};

/**
 * The bench: the only object in the film that changes, so it takes its paint
 * coverage as a prop rather than owning it.
 *
 * Drawn as a true **front elevation**. An earlier pass stacked three seat
 * slats vertically -- which is a plan view of the seat flattened into the
 * front of the drawing -- and the result was a solid teal slab that spent the
 * whole colour budget and left a sitting figure nowhere to put its legs. Seen
 * from the front you see the *edge* of the seat plank: one band.
 *
 * It renders in two parts so the film can sandwich a sitting figure between
 * them, and that sandwich is the whole trick. With the seat band crossing in
 * front of the hips the pose reads instantly as sitting; without it the
 * identical figure reads as standing in front of the bench.
 *
 * `wet` runs 0..1 over three painted pieces, filling in the order someone
 * would actually paint them: back slats first, then the seat.
 */
export const Bench = ({wet = 0, x = BENCH_X, part = 'all'}) => {
  const seatY = -SEAT_H;
  const backTop = -BACK_H;
  const slat = (i, yy, x0, len, h) => {
    const cover = Math.max(0, Math.min(1, wet * 4 - i));
    return (
      <g key={`${yy}-${i}`}>
        <rect x={x0} y={yy} width={len} height={h} rx="3"
              fill={P.paperDeep} stroke={P.line} strokeWidth="2" />
        {cover > 0 && (
          <rect x={x0} y={yy} width={len * cover} height={h} rx="3"
                fill={P.paint} stroke={P.paint} strokeWidth="0.8" />
        )}
      </g>
    );
  };
  return (
    <g filter="url(#pencil)" transform={`translate(${x} ${GROUND})`}>
      {part !== 'seat' && (
        <>
          <Ink d={`M38 ${seatY} L42 ${backTop}`} w={2} />
          <Ink d={`M${BENCH_LEN - 38} ${seatY} L${BENCH_LEN - 42} ${backTop}`} w={2} />
          {slat(0, backTop, 38, BENCH_LEN - 76, 14)}
          {slat(1, backTop + 23, 38, BENCH_LEN - 76, 14)}
        </>
      )}
      {part !== 'back' && (
        <>
          <ellipse cx={BENCH_LEN / 2} cy="4" rx={BENCH_LEN * 0.56} ry="8"
                   fill={P.shade} opacity="0.34" />
          <Ink d="M22 -46 L28 0" w={2} />
          <Ink d={`M${BENCH_LEN - 22} -46 L${BENCH_LEN - 28} 0`} w={2} />
          <Ink d={`M28 -22 L${BENCH_LEN - 28} -24`} w={0} opacity={0.55} />
          {slat(2, seatY, 14, BENCH_LEN - 28, 11)}
        </>
      )}
    </g>
  );
};

/** The sign nobody reads. Hand-lettered, and askew from the moment it lands. */
export const Sign = ({x = 1190, tilt = -3}) => (
  <g filter="url(#pencil)" transform={`translate(${x} ${GROUND}) rotate(${tilt})`}>
    <Ink d="M14 0 L30 -66" w={2} />
    <Ink d="M92 0 L76 -66" w={2} />
    <Ink d="M23 -30 L85 -30" w={0} />
    <path d="M12 -118 h82 v54 h-82 z" fill={P.paper} stroke={P.line} strokeWidth="2.2" />
    <text x="53" y="-93" textAnchor="middle" fill={P.line}
          style={{font: '600 23px "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive'}}>WET</text>
    <text x="53" y="-71" textAnchor="middle" fill={P.line}
          style={{font: '600 23px "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive'}}>PAINT</text>
    <ellipse cx="53" cy="4" rx="41" ry="6" fill={P.shade} opacity="0.34" />
  </g>
);

export const ParkSet = () => (
  <g>
    <Terrace />
    <Tree />
    <Railing />
    <Ground />
    <Lamppost />
  </g>
);
