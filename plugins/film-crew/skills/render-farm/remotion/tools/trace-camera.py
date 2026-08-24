#!/usr/bin/env python3
"""Record the resolved camera, one entry per rendered frame.

The camera solver is the part of the engine least worth reimplementing and
easiest to get subtly wrong. `track`, `pan` and `whip` are all the *same*
linear interpolation -- what separates them is the default easing curve, the
`hold`/`pre_hold` settle carved out of the span before easing, a
`_pick_ease` pass that silently refuses mechanical curves, a seeded handheld
noise table, and a `follow` mode whose centre depends on where an actor
actually is at that instant.

A port of all that is five opportunities to be almost right. Reading
`CameraSolver.view(t)` once per frame is none: it is a few hundred kB of
numbers that cannot drift, and it makes `follow` free.

This is the same trick as the pen tracer, applied to motion instead of
artwork -- the engine stays the single source of truth and the port only
replays.

    python3 tools/trace-camera.py -o src/generated/camera.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The tracers reach into the style they are tracing. This project no
# longer lives inside that style, so the link is explicit and
# overridable rather than implied by the directory tree.
SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SKILL = os.environ.get("FILM_STYLE_SKILL",
                       os.path.join(SKILLS, "style-2d-animation"))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import render as R      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--board", default=os.path.join(SKILL, "examples",
                                                    "pursuit", "board.json"))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("-W", "--width", type=int, default=1920)
    ap.add_argument("-H", "--height", type=int, default=1080)
    args = ap.parse_args()

    board = json.load(open(args.board))
    d = os.path.dirname(os.path.abspath(args.board))
    film = R.Film(board, d, args.width, args.height, args.fps,
                  line_times=R.line_times(board, d), quiet=True)

    total = int(round(film.shots.total() * args.fps)) if hasattr(
        film.shots, "total") else int(round(
            max(sh.start + sh.dur for sh in film.shots) * args.fps))

    out = {"fps": args.fps, "width": args.width, "height": args.height,
           "total": total, "shots": {}}
    order = []
    for f in range(total):
        t = f / float(args.fps)
        shot, solver, view, t_local, t_pose, span = film.state(t)
        rec = out["shots"].get(shot.id)
        if rec is None:
            order.append(shot.id)
            rec = out["shots"][shot.id] = {
                "start": round(shot.start, 4), "dur": round(shot.dur, 4),
                "startFrame": f,
                "move": getattr(solver, "move", "none"),
                # The parallax anchor: `_camera_offset` measures travel from
                # the shot's authored `from`, not from the frame it is on.
                "anchor": [round(float(getattr(solver, "p0", (50.0, 28.0))[0]), 4),
                           round(float(getattr(solver, "p0", (50.0, 28.0))[1]), 4)],
                "sceneW": round(float(getattr(solver, "scene_w", 100.0)), 4),
                "sceneH": round(float(getattr(solver, "scene_h", 56.25)), 4),
                "frames": [],
            }
        rec["frames"].append([
            round(view.cx, 4), round(view.cy, 4), round(view.zoom, 5),
            round(view.w, 4), round(view.h, 4), round(view.blur, 4),
            # The pose clock and the smear window, so the port never has to
            # recompute a quantisation that can vary inside a single shot.
            round(t_pose, 5), round(span[2], 5), round(t_local, 5),
        ])
    out["order"] = order
    for sid in order:
        r = out["shots"][sid]
        print(f"  {sid:5s} {r['move']:9s} {len(r['frames']):4d} frames",
              file=sys.stderr)
    n = total

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"wrote {args.out}  ({os.path.getsize(args.out) / 1024:.0f} kB, "
          f"{n} frames)", file=sys.stderr)


if __name__ == "__main__":
    main()
