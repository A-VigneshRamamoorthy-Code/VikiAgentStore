#!/usr/bin/env python3
"""Record the Python engine's vector artwork so Remotion can replay it.

The renderer draws every prop through a small pen abstraction (`sets._Pen`)
in *design units* around the prop's own anchor, and folds `scale` into the
pen rather than into the drawing code. That makes the pen the single seam in
the whole module -- so a pen that writes JSON instead of pixels gets the
artwork out exactly as authored, with no transcription and no drift.

Hand-porting the drawings was the alternative. `_prop_policecar` alone is
~60 primitive calls with derived colours (`_edge`, `mix`, `_at_lightness`);
doing that by eye for seven props would take hours and would still be a
different film.

Two things a first cut got wrong, both worth stating because they are not
guessable from the drawing code:

* **A prop's wheels only turn if the board gave it an `anim`.** The renderer
  computes ``rate = prop["rate"] if prop.get("anim") else 0.0`` and then
  ``phase = (prop["phase"] + t_pose * rate) % 1``, so in this board every
  vehicle except the helicopter has a *constant* phase. The cars are staged
  on the spot and the scenery moves past them.
* **`phase` and `t` are different clocks.** `phase` is quantised with the
  characters -- a wheel turning on ones beside a body on twos separates from
  it -- while `t` is the shot's true local time, for the parts of a prop that
  are scenery rather than drawing: a light bar, a rotor. Sampling them on one
  shared index couples two things the engine deliberately keeps apart.

So each prop *instance* is traced with the seed that instance really gets,
over only the axes it actually responds to, which is measured rather than
assumed.

    python3 tools/trace-props.py -o src/generated/props.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import look as L          # noqa: E402
import render as R        # noqa: E402
import sets as S          # noqa: E402
import shots as SH        # noqa: E402


def _hex(col):
    """Pillow colour -> CSS. Keeps alpha, because the engine uses it."""
    if col is None:
        return None
    if isinstance(col, str):
        return col
    c = tuple(col)
    r, g, b = (max(0, min(255, int(round(v)))) for v in c[:3])
    if len(c) >= 4 and int(c[3]) < 255:
        return f"rgba({r},{g},{b},{round(int(c[3]) / 255.0, 4)})"
    return f"#{r:02x}{g:02x}{b:02x}"


#: Decimal places kept on a scene coordinate. At 1920 px across 100 scene
#: units one unit is 19.2 px, so two places resolve 0.02 px -- comfortably
#: below anything a renderer can show, and roughly a fifth off the payload
#: compared with three.
DP = 2


def _r(v):
    return round(float(v), DP)


def _pts(seq):
    return [[_r(p[0]), _r(p[1])] for p in seq]


class RecordingPen:
    """Duck-types `sets._Pen`, but appends primitives instead of rasterising.

    Coordinates stay in scene units: the SVG side owns the mapping, exactly
    as the real pen owns the only multiplication by `unit`.
    """

    def __init__(self, bounds=(-200.0, -200.0, 200.0, 200.0), unit=10.0):
        self.ops = []
        self.u = float(unit)
        self.wk = 1.0
        self._b = bounds
        self.w = int((bounds[2] - bounds[0]) * unit)
        self.h = int((bounds[3] - bounds[1]) * unit)
        self.ox, self.oy = bounds[0], bounds[1]

    def X(self, x):
        return (float(x) - self.ox) * self.u

    def Y(self, y):
        return (float(y) - self.oy) * self.u

    def pt(self, p):
        return ((float(p[0]) - self.ox) * self.u,
                (float(p[1]) - self.oy) * self.u)

    def pts(self, seq):
        return [self.pt(p) for p in seq]

    def px(self, units):
        return max(1, int(round(float(units) * self.u * self.wk)))

    def bounds(self):
        return self._b

    def _emit(self, kind, **kw):
        op = {"k": kind}
        for key, val in kw.items():
            if val is not None:
                op[key] = val
        self.ops.append(op)

    def fill(self, col):
        self._emit("fill", c=_hex(col))

    def vgrad(self, top, bottom, y0=None, y1=None):
        self._emit("vgrad", a=_hex(top), b=_hex(bottom),
                   y0=None if y0 is None else _r(y0),
                   y1=None if y1 is None else _r(y1))

    def rect(self, x0, y0, x1, y1, col=None, ink=None, w=0.0):
        self._emit("rect", p=_pts([(x0, y0), (x1, y1)]), c=_hex(col),
                   i=_hex(ink) if w > 0 else None,
                   w=_r(w) if w > 0 else None)

    def rrect(self, x0, y0, x1, y1, r, col=None, ink=None, w=0.0):
        self._emit("rrect", p=_pts([(x0, y0), (x1, y1)]), r=_r(r),
                   c=_hex(col), i=_hex(ink) if w > 0 else None,
                   w=_r(w) if w > 0 else None)

    def poly(self, points, col=None, ink=None, w=0.0):
        p = _pts(points)
        if len(p) < 3:
            return
        self._emit("poly", p=p, c=_hex(col), i=_hex(ink) if w > 0 else None,
                   w=_r(w) if w > 0 else None)

    def ellipse(self, cx, cy, rx, ry, col=None, ink=None, w=0.0):
        self._emit("ell", p=[[_r(cx), _r(cy)]],
                   r=[_r(abs(rx)), _r(abs(ry))],
                   c=_hex(col), i=_hex(ink) if w > 0 else None,
                   w=_r(w) if w > 0 else None)

    def circle(self, cx, cy, r, col=None, ink=None, w=0.0):
        self.ellipse(cx, cy, r, r, col, ink, w)

    def pie(self, cx, cy, r, a0, a1, col=None):
        self._emit("pie", p=[[_r(cx), _r(cy)]],
                   r=[_r(abs(r))],
                   a=[round(float(a0), 2), round(float(a1), 2)], c=_hex(col))

    def line(self, points, col, w=0.3, cap=True):
        p = _pts(points)
        if len(p) < 2:
            return
        self._emit("line", p=p, c=_hex(col), w=_r(w),
                   cap=bool(cap))

    def text(self, x, y, s, col, size_units=2.0, anchor="mm"):
        self._emit("text", p=[[_r(x), _r(y)]],
                   s=str(s), c=_hex(col), sz=round(float(size_units), 2),
                   an=str(anchor))


#: Steps around one full `phase` cycle, for a prop the board animates.
PHASES = 24

#: `t` samples and the window they span. The fastest thing driven by `t` is
#: the police light bar at `_LIGHTBAR` (0.28 s) per state, so the window is
#: two full states and the step resolves it four times over. A prop with a
#: slower `t` response is caught by `axes_used` sampling beyond one window.
T_SPAN = S._LIGHTBAR * 2.0
T_STEPS = 8


def trace(kind, look, *, phase, t, seed, anim):
    fn = S.PROPS.get(kind)
    if fn is None:
        raise SystemExit(f"unknown prop {kind!r}")
    pen = RecordingPen()
    fn(pen, look, 1.0, phase, t, seed, anim)
    return pen.ops


def axes_used(kind, look, seed, anim):
    """``(uses_phase, uses_t)``, measured rather than assumed.

    Sampling an axis a prop ignores multiplies the payload for nothing, and
    guessing wrong in the other direction freezes something that should move.
    """
    base = json.dumps(trace(kind, look, phase=0.0, t=0.0, seed=seed, anim=anim))
    ph = any(
        json.dumps(trace(kind, look, phase=p, t=0.0, seed=seed, anim=anim)) != base
        for p in (0.25, 0.5, 0.75)
    )
    tt = any(
        json.dumps(trace(kind, look, phase=0.0, t=v, seed=seed, anim=anim)) != base
        for v in (S._LIGHTBAR, S._LIGHTBAR * 1.5, 0.9, 2.3)
    )
    return ph, tt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--palette", default="pursuit")
    ap.add_argument("--board", default=os.path.join(SKILL, "examples",
                                                    "pursuit", "board.json"))
    args = ap.parse_args()

    look = L.palette(args.palette) if hasattr(L, "palette") \
        else L.PALETTES[args.palette]
    board = json.load(open(args.board))
    d = os.path.dirname(os.path.abspath(args.board))
    film = R.Film(board, d, 1920, 1080, 30, line_times=R.line_times(board, d),
                  quiet=True)
    shot_seed = {sh.id: sh.seed for sh in film.shots}

    out = {"palette": args.palette, "phases": PHASES, "tSteps": T_STEPS,
           "tSpan": round(T_SPAN, 4), "bbox": {}, "instances": {}}

    total = 0
    for sh in board["shots"]:
        for i, prop in enumerate(sh.get("props") or []):
            kind = prop["kind"]
            anim = prop.get("anim")
            at = prop.get("at") or [50.0, 44.0]
            seed = (film.seed ^ shot_seed.get(sh["id"], 0)
                    ^ SH._seed_of(kind, at[0], at[1])) & 0x7FFFFFFF

            uses_ph, uses_t = axes_used(kind, look, seed, anim)
            # The engine zeroes the rate unless the board asked for an anim,
            # so a prop with no anim holds one drawing however fast it looks.
            rate = float(prop.get("rate", 1.0) or 0.0) if anim else 0.0
            if rate == 0.0:
                uses_ph = False

            nph = PHASES if uses_ph else 1
            nt = T_STEPS if uses_t else 1
            grid = []
            for pi in range(nph):
                row = []
                for ti in range(nt):
                    row.append(trace(kind, look,
                                     phase=(float(prop.get("phase", 0.0))
                                            + pi / nph) % 1.0 if uses_ph
                                     else float(prop.get("phase", 0.0)) % 1.0,
                                     t=ti / nt * T_SPAN,
                                     seed=seed, anim=anim))
                grid.append(row)

            key = f"{sh['id']}:{i}"
            out["instances"][key] = {
                "kind": kind, "anim": anim or "",
                "phase0": float(prop.get("phase", 0.0)), "rate": rate,
                "usesPhase": uses_ph, "usesT": uses_t, "grid": grid,
            }
            out["bbox"][kind] = [round(v, 3) for v in S._BBOX.get(kind, ())]
            n = sum(len(c) for row in grid for c in row)
            total += n
            print(f"  {key:8s} {kind:12s} anim={anim or '-':5s} "
                  f"phase={'Y' if uses_ph else 'n'} t={'Y' if uses_t else 'n'} "
                  f"{nph}x{nt} {n:6d} ops", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"wrote {args.out}  ({os.path.getsize(args.out) / 1024:.0f} kB, "
          f"{total} ops)", file=sys.stderr)


if __name__ == "__main__":
    main()
