#!/usr/bin/env python3
"""Render each actor as transparent cel sprites for Remotion to composite.

The props and sets came over as vectors because they draw through a pen.
The rig does not -- `rig.draw` paints straight onto a PIL image at 3x and
composites down, so there is no seam to record. Re-implementing it in SVG
would mean re-deriving bone tables, width tables, mitten hands, squash and
the gait solver, and would still be a *different* character.

So the figures come over as cels instead. That is not a workaround: a cel is
what limited animation actually ships, and the film already holds each
drawing for two or three frames, so a sprite per distinct drawing is exactly
the right number of images -- ~29 per actor for a 2.9 s shot on threes.

Poses are built by the engine's own `Film._pose_for`, so the gait solver,
the stride planting and the squash all stay where they were written.

    python3 tools/trace-actors.py -o ../public/actors --meta src/generated/actors.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# The tracers reach into the style they are tracing. This project no
# longer lives inside that style, so the link is explicit and
# overridable rather than implied by the directory tree.
SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SKILL = os.environ.get("FILM_STYLE_SKILL",
                       os.path.join(SKILLS, "style-2d-animation"))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import render as R        # noqa: E402
import rig                # noqa: E402
import shots as SH        # noqa: E402


#: Pixels per scene unit is worked out per shot, from the tightest zoom that
#: shot actually reaches. A single global value has to serve the closest shot
#: in the film, which made every wide shot's cels ~4x larger than anything
#: that would ever be sampled from them -- and the cyclist, the one actor
#: whose smears defeat the hold and so needs the most cels, is in one of the
#: widest shots.
HEADROOM = 1.12
MAX_UNIT = 44.0

#: Scene-unit padding around the pose bbox, so a smear or a swinging hand is
#: never clipped by its own sprite.
PAD = 3.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True, help="sprite directory")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--board", default=os.path.join(SKILL, "examples",
                                                    "pursuit", "board.json"))
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    board = R.load_board(args.board) if hasattr(R, "load_board") \
        else json.load(open(args.board))
    d = os.path.dirname(os.path.abspath(args.board))
    lt = R.line_times(board, d)
    film = R.Film(board, d, 1920, 1080, args.fps, line_times=lt, quiet=True)

    os.makedirs(args.out, exist_ok=True)
    meta = {"fps": args.fps, "actors": {}}
    total = 0

    for shot in film.shots:
        raw = next((s for s in board["shots"] if s["id"] == shot.id), {})
        actors = raw.get("actors") or []
        if not actors:
            continue

        on = max(1, int(raw.get("on") or 3))
        nframes = max(1, int(round(shot.dur * args.fps)))

        cam = raw.get("camera") or {}
        z = cam.get("zoom", [1.0, 1.0])
        z = z if isinstance(z, (list, tuple)) else [z, z]
        unit = min(MAX_UNIT,
                   max(float(v) for v in z) * (1920.0 / 100.0) * HEADROOM)

        for a_i, actor in enumerate(actors):
            key = f"{shot.id}-{actor.get('id', a_i)}"
            look = film.cast_look_for(actor.get("cast"))
            # Depth, not a constant: the renderer defaults an actor to z=0.5
            # and `rig.draw` desaturates and lifts with distance, so baking a
            # cel at z=1 gives a figure that is too saturated for its plane.
            z = R._z_of(actor, 0.5)
            height = float(actor.get("height", 18.0) or 18.0)
            frames = []
            seen = {}

            # Every frame is visited, but a cel is only written when the
            # drawing actually changes. That collapses the holds for free and
            # still catches a smear, which by design breaks the hold and so
            # differs from its neighbours.
            for f in range(nframes):
                pf = SH.quantise_frame(f, on)
                t_pose = pf / float(args.fps)
                frac = 0.0 if on <= 1 else (f - pf) / float(on)
                span = (t_pose, min((pf + on) / float(args.fps), shot.dur),
                        frac)
                try:
                    pose = film._pose_for(shot, actor, t_pose, span)
                except Exception as exc:                    # noqa: BLE001
                    print(f"  ! {key} f{f}: {exc}", file=sys.stderr)
                    pose = None
                if pose is None or look is None:
                    continue

                sig = json.dumps(pose, sort_keys=True, default=str)
                at = SH.actor_at(actor, t_pose, shot.dur)

                if sig in seen:
                    src, box = seen[sig]
                else:
                    bb = rig.bbox(pose)
                    x0, y0 = bb[0] - PAD, bb[1] - PAD
                    x1, y1 = bb[2] + PAD, bb[3] + PAD
                    w = max(8, int(round((x1 - x0) * unit)))
                    h = max(8, int(round((y1 - y0) * unit)))
                    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    try:
                        rig.draw(img, pose, look, unit=unit,
                                 origin=(x0, y0), z=z, shadow=False)
                    except TypeError:
                        rig.draw(img, pose, look, unit=unit,
                                 origin=(x0, y0), z=z)
                    src = f"{key}-{len(seen):03d}.png"
                    # Flat vector art is a handful of colours plus the
                    # anti-aliased seams between them, so a palette holds it
                    # exactly where a truecolour PNG spends most of its bytes.
                    img.quantize(colors=128, method=Image.FASTOCTREE) \
                       .save(os.path.join(args.out, src), optimize=True)
                    box = [round(x0, 3), round(y0, 3),
                           round(x1, 3), round(y1, 3)]
                    seen[sig] = (src, box)
                    total += 1

                frames.append({"f": f, "src": src, "box": box,
                               "at": [round(float(at[0]), 3),
                                      round(float(at[1]), 3)]})

            if frames:
                meta["actors"][key] = {
                    "shot": shot.id, "on": on, "id": actor.get("id"),
                    "height": height, "unit": round(unit, 2),
                    "cels": len(seen), "frames": frames,
                }
                print(f"  {key:22s} {len(seen):3d} cels / {nframes} frames",
                      file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(args.meta)), exist_ok=True)
    with open(args.meta, "w") as fh:
        json.dump(meta, fh, separators=(",", ":"))

    kb = sum(os.path.getsize(os.path.join(args.out, f))
             for f in os.listdir(args.out) if f.endswith(".png")) / 1024.0
    print(f"wrote {total} cels ({kb:.0f} kB) + {args.meta}", file=sys.stderr)


if __name__ == "__main__":
    main()
