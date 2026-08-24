#!/usr/bin/env python3
"""Record each set's layers as vectors, so Remotion can parallax them itself.

Same trick as `trace-props.py`, one level up: a set draws through a stage
that hands out one pen per parallax layer, and each layer builds its content
from `pen.bounds()` -- ask for a wide window and you get a wide strip of
world. Recording those strips gives Remotion the real scenery instead of an
imitation of it, and leaves the parallax to CSS transforms, which is the part
Remotion is actually better at than a compositor.

    python3 tools/trace-sets.py -o src/generated/sets.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import look as L          # noqa: E402
import sets as S          # noqa: E402

sys.path.insert(0, HERE)
from importlib import import_module  # noqa: E402

_tp = import_module("trace-props".replace("-", "_")) if False else None

# trace-props.py is not an importable name, so load the pen directly.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "traceprops", os.path.join(HERE, "trace-props.py"))
_tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tp)
RecordingPen = _tp.RecordingPen


#: The strip of world recorded per layer. The camera never travels more than
#: ~40 units in a shot and the widest zoom-out shows 100, so +/-110 around the
#: board leaves room for the fastest foreground layer (k = 1.5) to slide
#: without running out of scenery.
WINDOW = (-110.0, -14.0, 210.0, 62.0)

#: Time samples for a set whose scenery moves on its own. The aerial traffic
#: is the only one in this board; 24 samples over 6 s is 4 fps of distant
#: cars, which at that scale -- and under a camera that is pushing anyway --
#: is indistinguishable from continuous, and keeps the payload sane.
#: Time samples across `SAMPLE_SPAN` seconds for the layers that move.
#:
#: 24 samples over 6 s ran the aerial traffic at 4 fps, which reads as a
#: stutter under a film whose *characters* are on twos. Delta encoding (see
#: `pack_motion`) made a sample cheap enough to more than double.
SAMPLES = 60
SAMPLE_SPAN = 6.0



def _points_of(ops):
    """Every mutable coordinate in a layer, in a stable order."""
    out = []
    for o in ops:
        for pt in o.get("p", ()):
            out.append(pt)
    return out


def pack_motion(base, snaps):
    """Compress an animated layer to one drawing plus per-group offsets.

    Traffic is the most expensive thing in this film by an order of
    magnitude, and storing a snapshot per time sample stored the *same cars*
    over and over. But the layer is not one moving picture: sampling it twice
    showed identical op counts, shapes and colours, with ~292 distinct
    per-point offsets in a 1792-op layer. In other words each car keeps its
    identity and simply moves -- 292 motions, not 1792, and not 1.

    So points are grouped by their offset *signature across every sample*,
    which makes the grouping exact by construction rather than inferred from
    one pair of frames: two cars that happen to coincide early but diverge
    later get different signatures and land in different groups.

    Returns ``None`` if the layer does not behave this way -- a layer that
    adds or removes primitives over time has no correspondence to exploit --
    and the caller falls back to whole snapshots.
    """
    bp = _points_of(base)
    sig = {}
    for snap in snaps:
        if len(snap) != len(base):
            return None
        for a, b in zip(base, snap):
            if a["k"] != b["k"] or a.get("c") != b.get("c") \
                    or a.get("i") != b.get("i") \
                    or len(a.get("p", ())) != len(b.get("p", ())):
                return None
        sp = _points_of(snap)
        for i, (a, b) in enumerate(zip(bp, sp)):
            sig.setdefault(i, []).append((round(b[0] - a[0], 2),
                                          round(b[1] - a[1], 2)))

    groups = {}
    for i, key in sig.items():
        groups.setdefault(tuple(key), []).append(i)
    if len(groups) >= len(bp):
        return None            # nothing shared; deltas would cost more

    keys = list(groups)
    return {
        "idx": [groups[k] for k in keys],
        "delta": [[[d[0], d[1]] for d in
                   (k[i] for k in keys)] for i in range(len(snaps))],
    }


def window_for(board, name, shot_id=None):
    """The strip of world a set actually needs, derived from the board.

    Tracing a fixed wide window wasted most of its output: the aerial set
    needed 132 units and was being given 320, and since the aerial traffic
    is by far the densest layer in the film that alone was ~60% of the
    payload. Asking the shots how far the camera travels is both smaller and
    self-maintaining -- re-time the board and the window follows.

    With `shot_id`, the window narrows to what that *one* shot sees. That is
    what makes per-shot tracing affordable: a set-wide window has to span
    every camera position in the film, while a single shot usually sits in a
    small part of it.
    """
    lo, hi, zmin = 1e9, -1e9, 9.0
    for sh in board["shots"]:
        if sh.get("set") != name:
            continue
        if shot_id is not None and sh.get("id") != shot_id:
            continue
        cam = sh.get("camera") or {}
        fr = cam.get("from") or [50.0, 28.0]
        to = cam.get("to") or fr
        z = cam.get("zoom", [1.0, 1.0])
        z = z if isinstance(z, (list, tuple)) else [z, z]
        for p in (fr, to):
            lo, hi = min(lo, float(p[0])), max(hi, float(p[0]))
        zmin = min(zmin, min(float(v) for v in z))
    if lo > hi:
        return WINDOW_FALLBACK

    view = SCENE_LONG / max(zmin, 0.05)
    travel = hi - lo
    # A layer at parallax k is drawn shifted by `off * (1 - k)`, where `off`
    # is the camera's travel from its own anchor -- so `off` runs 0..travel
    # rather than being free. Working the extremes through:
    #
    #   left edge  = min over cx of (cx - view/2 - (cx - lo)(1 - k))
    #              = lo - view/2                    (at k = 0)
    #   right edge = hi + view/2 + travel/2         (at k = 1.5)
    #
    # The old symmetric `view/2 + travel` pad therefore over-traced by a
    # whole `travel` on the left and `travel/2` on the right, on a set whose
    # densest layer is the most expensive thing in the file.
    return (lo - view / 2.0 - 6.0, -14.0,
            hi + view / 2.0 + travel / 2.0 + 6.0, 62.0)


SCENE_LONG = 100.0
WINDOW_FALLBACK = (-110.0, -14.0, 210.0, 62.0)


class _RecStage:
    """Duck-types `sets._Stage`: one recording pen per layer, same bounds."""

    def __init__(self, layers, window, want=None):
        self.kmap = dict(layers)
        self.window = window
        self.want = want
        self.pens = {}

    def layer(self, name, k=None):
        if self.want is not None and name not in self.want:
            return None
        if name not in self.kmap and k is None:
            raise KeyError(name)
        band = S._stroke_band(self.kmap.get(name, k or 1.0))
        pen = RecordingPen(bounds=self.window)
        # Depth stroke scaling is the pen's job in the engine; keep it, so a
        # distant building carries the lighter line it is supposed to.
        pen.wk = S.STROKE_PX[band] / S.STROKE_PX["character"]
        self.pens[name] = pen
        return pen


def _shift_y(ops, dy):
    """The same ops, moved down by `dy`. Used only to compare two traces."""
    out = []
    for op in ops:
        o = dict(op)
        if "p" in o:
            o["p"] = [[x, round(y + dy, 2)] for x, y in o["p"]]
        for key in ("y0", "y1"):
            if o.get(key) is not None:
                o[key] = round(o[key] + dy, 2)
        out.append(o)
    return out


def frame_anchored(name, look, window, seed):
    """Which layers hang off the frame's bottom edge rather than the world.

    `_street_fg` and its siblings read `pen.bounds()[3]` and put the kerb and
    the bollards just above it, because foreground furniture belongs at the
    bottom of the *frame* -- it is how the shot is dressed, not where the
    world is. A traced strip therefore cannot be placed in world space: as
    the camera pushes in, the real renderer moves that layer up.

    Rather than hard-code a list that would rot the moment a set is added,
    this traces the set twice with different window bottoms and asks which
    layers moved with it.
    """
    probe = (window[0], window[1], window[2], window[3] + 10.0)
    a = trace_set(name, look, window, t=0.0, seed=seed)
    b = trace_set(name, look, probe, t=0.0, seed=seed)
    out = set()
    for la, lb in zip(a, b):
        if la["ops"] and json.dumps(_shift_y(la["ops"], 10.0)) == \
                json.dumps(lb["ops"]):
            out.add(la["name"])
    return out


def trace_set(name, look, window, t=0.0, seed=19):
    fn = S.SETS.get(name)
    if fn is None:
        raise SystemExit(f"unknown set {name!r}")
    layers = S.SET_LAYERS[name]
    st = _RecStage(layers, window)
    fn(st, look, t, seed)
    return [
        {"name": ln, "k": k, "ops": st.pens[ln].ops}
        for ln, k in layers if ln in st.pens
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--palette", default="pursuit")
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--board", default=os.path.join(
        SKILL, "examples", "pursuit", "board.json"))
    args = ap.parse_args()

    look = L.palette(args.palette) if hasattr(L, "palette") else L.PALETTES[args.palette]
    board = json.load(open(args.board))
    seed = int(board.get("seed", args.seed))

    used = sorted({sh["set"] for sh in board["shots"] if sh.get("set")})

    # The renderer seeds each shot separately (`self.seed ^ shot.seed`), so
    # the same street is a different street in every shot -- different awning
    # colours, different shop widths. Tracing one strip per *set* threw that
    # away and made ten street shots look like ten cuts of one wall.
    import render as R
    d = os.path.dirname(os.path.abspath(args.board))
    lt = R.line_times(board, d)
    film = R.Film(board, d, 1920, 1080, 30, line_times=lt, quiet=True)
    shot_seed = {sh.id: film.seed ^ sh.seed for sh in film.shots}
    frame_count = {sh.id: int(round(sh.dur * args.fps)) for sh in film.shots}

    out = {"palette": args.palette, "seed": seed, "ground": {},
           "sets": {}, "shots": {}}

    # Every layer is traced per shot, moving ones included.
    #
    # An earlier cut shared the moving layers across a set to save payload,
    # on the argument that nobody can tell one distant car from another. That
    # is true of a *still*, and false of a comparison: the three aerial shots
    # differed from the reference render by MAE 7-15 while every other shot
    # sat near 4, and the diff map was solid white cars. Per-shot seeding
    # costs a copy per shot and buys the aerial set back.
    #
    # What pays for it is the window: each shot is traced over the strip *it*
    # sees rather than the union across the film, which is much smaller.
    for name in used:
        window = window_for(board, name)
        layers = trace_set(name, look, window, t=0.0, seed=seed)

        # Only pay for extra samples on the layers that actually move with
        # `t`. In this board that is the aerial traffic and nothing else, so
        # sampling every set over time would multiply the payload for three
        # shots' worth of moving cars.
        alt = trace_set(name, look, window, t=SAMPLE_SPAN / SAMPLES, seed=seed)
        moving = [l["name"] for l, m in zip(layers, alt)
                  if json.dumps(l["ops"]) != json.dumps(m["ops"])]

        anchored = frame_anchored(name, look, window, seed)
        if anchored:
            print(f"            frame-anchored: {','.join(sorted(anchored))}",
                  file=sys.stderr)

        out["sets"][name] = {
            "anchored": sorted(anchored),
            "bottom": round(window[3], 3),
            "layers": [l for l in layers if l["name"] in moving],
            "animated": moving,
            "window": [round(v, 2) for v in window],
            "order": [ln for ln, _k in S.SET_LAYERS[name]],
            "samples": SAMPLES, "span": SAMPLE_SPAN, "fps": args.fps,
        }
        out["ground"][name] = S.SET_GROUND.get(name)
        n = sum(len(l["ops"]) + sum(len(f) for f in l.get("frames", []))
                for l in layers)
        print(f"  {name:9s} {len(layers)} layers, {n:6d} ops"
              f"  win {window[0]:.0f}..{window[2]:.0f}"
              f"{'  moving: ' + ','.join(moving) if moving else ''}",
              file=sys.stderr)

    # Now every layer, per shot, on that shot's own seed and its own window.
    for sh in board["shots"]:
        name = sh.get("set")
        if not name or name not in out["sets"]:
            continue
        window = window_for(board, name, sh["id"])
        moving = out["sets"][name]["animated"]
        sd = shot_seed.get(sh["id"], seed)
        layers = trace_set(name, look, window, t=0.0, seed=sd)

        # A moving layer is sampled once per *rendered frame*, not on a
        # coarse grid. Sampling the aerial traffic every 0.1 s looked
        # defensible until it was measured: the cars cross ~27 units a
        # second, so half a sample is 1.3 units -- about 26 px, and a quarter
        # of a car. There is no sample rate short of the frame rate at which
        # a comparison stops seeing them, and delta encoding makes the frame
        # rate the cheaper option anyway.
        nf = frame_count.get(sh["id"], 0)
        if moving and nf:
            frames = {}
            for i in range(nf):
                snap = trace_set(name, look, window, t=i / float(args.fps),
                                 seed=sd)
                for l in snap:
                    if l["name"] in moving:
                        frames.setdefault(l["name"], []).append(l["ops"])
            for l in layers:
                if l["name"] not in moving:
                    continue
                packed = pack_motion(l["ops"], frames[l["name"]])
                if packed:
                    l["motion"] = packed
                    l["perFrame"] = True
                else:
                    l["frames"] = frames[l["name"]]
                    l["perFrame"] = True
                    l["ops"] = []

        out["shots"][sh["id"]] = {
            "set": name,
            "bottom": round(window[3], 3),
            "layers": layers,
        }

    # The per-set copy exists only for its metadata now; the layers all come
    # from the per-shot pass.
    for v in out["sets"].values():
        v["layers"] = []

    n_shot = sum(len(v["layers"]) for v in out["shots"].values())
    n_ops = sum(len(l["ops"]) + sum(len(f) for f in l.get("frames", []))
                for v in out["shots"].values() for l in v["layers"])
    print(f"  per-shot: {len(out['shots'])} shots, {n_shot} layers, "
          f"{n_ops} ops", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"wrote {args.out}  ({os.path.getsize(args.out) / 1024:.0f} kB)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
