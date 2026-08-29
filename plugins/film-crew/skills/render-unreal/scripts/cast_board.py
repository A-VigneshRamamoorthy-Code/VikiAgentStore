#!/usr/bin/env python3
"""Compile a film-crew storyboard into a flat `scene.json` that an in-engine
builder can execute without interpreting anything.

Two ideas carry the whole design.

**Bays.** Every shot gets a private copy of its set, parked far away on X from
every other shot. Nothing is ever shared between shots, so there are no
visibility tracks to key, no chance of two settings sharing a frame, and no
possibility of one shot's staging leaking into another. Cuts are hard, so the
camera teleporting between bays is invisible.

**One camera per shot.** A camera that only ever lives in one shot cannot
interpolate across a cut, which removes the one-frame smear you otherwise get
where a shot's last key meets the next shot's first.

Both trade a larger scene for the elimination of an entire class of silent
failure, which on a 51-shot film is a bargain.

Kept outside Unreal on purpose: this is the half that needs iterating on, and
it runs in milliseconds where anything importing `unreal` costs an editor
launch to test.

    python3 cast_board.py storyboard.json timeline.json casting.json -o scene.json
"""
import argparse
import json
import sys
from pathlib import Path

# The storyboard's own 0-100 percentage grid, mapped into Unreal world units.
# At zoom 1 the camera frames exactly this rectangle.
STAGE_W = 1920.0
STAGE_H = 1080.0

# How far apart consecutive shot bays sit on X. Comfortably larger than any
# set, so no camera can ever see its neighbour.
BAY_STRIDE = 60000.0

# Camera distance to the action plane at zoom 1. Paired with a ~50mm lens this
# is long enough that flat artwork shows no visible perspective distortion, yet
# short enough that a dolly still produces real parallax against the layers.
CAM_DIST = 4000.0

# Extra coverage on backdrop planes so a camera move never reaches an edge.
COVER = 1.35


def load(path):
    with open(path) as fh:
        return json.load(fh)


def stage_to_world(x_pct, y_pct, bay_x):
    """Storyboard percentages -> (X, Z) in world units. Stage Y counts downward,
    Unreal Z counts upward, hence the flip."""
    return (
        bay_x + (x_pct - 50.0) / 100.0 * STAGE_W,
        (50.0 - y_pct) / 100.0 * STAGE_H,
    )


def resolve_shots(board, timeline, warn):
    """Merge the board's staging into the timeline's absolute times.

    The board carries actors, props and camera geometry but times everything
    symbolically ("l5+2.9"); the timeline has resolved seconds but has dropped
    the staging. Neither file is sufficient alone.
    """
    times = {s["id"]: s for s in timeline["shots"]}
    out = []
    for shot in board["shots"]:
        t = times.get(shot["id"])
        if not t:
            warn(f"shot {shot['id']} is in the board but not the timeline")
            continue
        merged = dict(shot)
        merged["start"] = float(t["start"])
        merged["end"] = float(t["end"])
        out.append(merged)
    out.sort(key=lambda s: s["start"])
    return out


def backdrop(set_name, casting, bay_x, warn):
    """The stacked plane layers for one bay, far to near.

    `depth` is distance *behind* the action plane. Because the camera is
    perspective, a layer's apparent motion falls off with depth all by itself —
    that is the parallax, and it costs nothing to compute.
    """
    spec = casting["sets"].get(set_name)
    if not spec:
        warn(f"set '{set_name}' has no casting entry")
        return []

    layers = []
    for i, layer in enumerate(spec["layers"]):
        depth = float(layer.get("depth", 500.0 + i * 400.0))
        dx, dz = stage_to_world(50.0 + float(layer.get("shift_x", 0.0)),
                                50.0 - float(layer.get("shift_y", 0.0)), bay_x)
        layers.append({
            "texture": layer["file"],
            "x": dx,
            "y": -depth,
            "z": dz,
            "fit": "cover",
            "ratio": (CAM_DIST + depth) / CAM_DIST,
            "cover": COVER * float(layer.get("cover", 1.0)),
            "tint": layer.get("tint"),
            "opacity": float(layer.get("opacity", 1.0)),
        })
    return layers


def cast_actor(actor, casting, bay_x, warn):
    cast_id = actor.get("cast") or actor.get("id")
    spec = casting["actors"].get(cast_id)
    if not spec:
        warn(f"actor '{cast_id}' has no casting entry")
        return None

    # A pose overrides the default art without needing a separate cast member.
    # A moving actor gets the walk pose if one is cast, because a standing
    # cut-out gliding across the set reads as a bug rather than a walk.
    action = actor.get("action")
    poses = spec.get("poses") or {}
    moving = bool(actor.get("to")) and list(actor["to"]) != list(actor.get("at") or [])
    art = None
    if moving:
        art = poses.get((action or "stand") + "_walk") or poses.get("walk")
    art = art or poses.get(action) or spec.get("file")
    if not art:
        warn(f"actor '{cast_id}' has no art for action '{action}'")
        return None

    at = actor.get("at") or [50.0, 50.0]
    x, z = stage_to_world(at[0], at[1], bay_x)

    to = None
    if actor.get("to") and list(actor["to"]) != list(at):
        tx, tz = stage_to_world(actor["to"][0], actor["to"][1], bay_x)
        to = {"x": tx, "z": tz}

    depth = float(spec.get("depth", 0.0))
    height_uu = (float(actor.get("height", 14.0)) / 100.0 * STAGE_H
                 * float(spec.get("height_scale", 1.0)))

    # A storyboard stands people on a ground line, but a plane is positioned by
    # its centre, so anchoring by the feet is what makes an actor's `at` mean
    # what the board intended and lets a set's floor be matched to it directly.
    lift = height_uu / 2.0 if spec.get("anchor", "feet") == "feet" else 0.0
    if to:
        to["z"] += lift
    return {
        "id": actor.get("id", cast_id),
        "texture": art,
        "x": x,
        "y": -depth,
        "z": z + lift,
        "to": to,
        # `height` is a percentage of frame height; at the action plane the
        # frame is exactly STAGE_H tall, so the conversion is direct.
        "height_uu": height_uu,
        "fit": "height",
        "flip": int(actor.get("facing", 1)) < 0,
        "ease": actor.get("ease", "linear"),
        "action": action or "stand",
        # Only a walking actor bobs; a standing one holding still is correct.
        "bob": (height_uu * float(spec.get("bob", 0.018))) if moving else 0.0,
    }


def cast_prop(prop, casting, bay_x, warn):
    kind = prop.get("kind")
    spec = casting["props"].get(kind)
    if not spec:
        warn(f"prop '{kind}' has no casting entry")
        return None

    # Props change state through the film — a book is closed, then open, then
    # glowing — and each state is its own piece of art.
    anim = prop.get("anim")
    states = spec.get("states") or {}
    art = states.get(anim) or spec.get("file")
    if not art:
        warn(f"prop '{kind}' has no art for state '{anim}'")
        return None

    at = prop.get("at") or [50.0, 50.0]
    x, z = stage_to_world(at[0], at[1], bay_x)
    depth = float(spec.get("depth", -20.0))
    # Prop scale is relative to the prop's own nominal size, not the frame.
    height = float(prop.get("scale", 0.4)) * float(spec.get("base_h", 260.0))

    out = {
        "kind": kind,
        "texture": art,
        "x": x,
        "y": -depth,
        "z": z,
        "height_uu": height,
        "fit": "height",
        "anim": anim or "still",
    }

    # A halo sits behind the prop and is what actually sells "this is magic";
    # without it a glowing state is just the same picture again.
    halo = (spec.get("halos") or {}).get(anim) or spec.get("halo")
    if halo:
        out["halo"] = {
            "texture": halo,
            "x": x,
            "y": -depth - 15.0,
            "z": z,
            "height_uu": height * float(spec.get("halo_scale", 2.6)),
            "fit": "height",
            "opacity": float(spec.get("halo_opacity", 0.85)),
        }
    return out


def build(board, timeline, casting):
    warnings = []
    warn = warnings.append

    shots = resolve_shots(board, timeline, warn)
    out_shots = []

    for i, s in enumerate(shots):
        bay_x = i * BAY_STRIDE
        cam = s.get("camera") or {}

        frm = cam.get("from") or [50.0, 50.0]
        to = cam.get("to") or frm
        zoom = cam.get("zoom") or [1.0, 1.0]
        z0, z1 = float(zoom[0]), float(zoom[-1])

        fx, fz = stage_to_world(frm[0], frm[1], bay_x)
        tx, tz = stage_to_world(to[0], to[1], bay_x)

        actors, props = [], []
        for a in s.get("actors") or []:
            c = cast_actor(a, casting, bay_x, warn)
            if c:
                actors.append(c)
        for p in s.get("props") or []:
            c = cast_prop(p, casting, bay_x, warn)
            if c:
                props.append(c)

        out_shots.append({
            "id": s["id"],
            "index": i,
            "set": s.get("set"),
            "bay_x": bay_x,
            "start": round(s["start"], 4),
            "end": round(s["end"], 4),
            "tier": s.get("tier"),
            "note": s.get("note", ""),
            "mist": float(s.get("mist", 0.0)),
            "camera": {
                # Zoom is a dolly rather than a focal change, so a push gains
                # parallax against the backdrop instead of merely cropping.
                "from": {"x": fx, "y": CAM_DIST / z0, "z": fz},
                "to": {"x": tx, "y": CAM_DIST / z1, "z": tz},
                "move": cam.get("move", "hold"),
                "ease": cam.get("ease", "linear"),
                "hold": float(cam.get("hold", 0.0)),
            },
            "layers": backdrop(s.get("set"), casting, bay_x, warn),
            "actors": actors,
            "props": props,
        })

    return {
        "schema": 1,
        "title": board.get("title") or timeline.get("title"),
        "fps": int(timeline.get("fps", 30)),
        "width": int(timeline.get("width", 1920)),
        "height": int(timeline.get("height", 1080)),
        "duration": float(timeline.get("duration", 0.0)),
        "stage": {"w": STAGE_W, "h": STAGE_H, "cam_dist": CAM_DIST},
        "lens": {"focal_mm": 50.0, "sensor_w": 23.76, "sensor_h": 13.365},
        "palette": board.get("palette"),
        "shots": out_shots,
        "warnings": sorted(set(warnings)),
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("timeline")
    ap.add_argument("casting")
    ap.add_argument("-o", "--out", default="scene.json")
    ap.add_argument("--only", default="",
                    help="comma-separated shot ids to compile alone, for a fast "
                         "look-test lap over a few representative shots")
    args = ap.parse_args()

    scene = build(load(args.storyboard), load(args.timeline), load(args.casting))

    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()}
        scene["shots"] = [s for s in scene["shots"] if s["id"] in keep]
        if not scene["shots"]:
            sys.exit(f"--only matched no shots; have {args.only!r}")
        # Pack the survivors contiguously. Keeping their original spacing would
        # leave the gaps of the shots that were dropped, so a six-shot test
        # would still render the whole film's worth of frames.
        cursor = 0.0
        for shot in scene["shots"]:
            length = shot["end"] - shot["start"]
            shot["start"] = cursor
            shot["end"] = cursor + length
            cursor += length
        scene["duration"] = cursor

    # Texture names in a casting file are written relative to that file, not to
    # whatever directory the compiler happens to be run from, so a casting file
    # stays portable and can be compiled from anywhere.
    casting = load(args.casting)
    root = Path(args.casting).resolve().parent / casting.get("art_dir", ".")
    for shot in scene["shots"]:
        for item in list(shot["layers"]) + list(shot["actors"]) + list(shot["props"]):
            item["texture"] = str((root / item["texture"]).resolve())
        for prop in shot["props"]:
            if prop.get("halo"):
                halo = prop["halo"]
                halo["texture"] = str((root / Path(halo["texture"]).name).resolve())

    Path(args.out).write_text(json.dumps(scene, indent=1))

    n_layer = sum(len(s["layers"]) for s in scene["shots"])
    n_act = sum(len(s["actors"]) for s in scene["shots"])
    n_prop = sum(len(s["props"]) for s in scene["shots"])
    print(f"{len(scene['shots'])} shots  {scene['duration']:.1f}s @ {scene['fps']}fps"
          f"  ->  {args.out}")
    print(f"  {n_layer} backdrop planes, {n_act} actors, {n_prop} props")

    textures = {l["texture"] for s in scene["shots"] for l in s["layers"]}
    textures |= {a["texture"] for s in scene["shots"] for a in s["actors"]}
    for s in scene["shots"]:
        for p in s["props"]:
            textures.add(p["texture"])
            if p.get("halo"):
                textures.add(p["halo"]["texture"])
    print(f"  {len(textures)} distinct textures")

    missing = sorted(t for t in textures if not Path(t).exists())
    for m in missing:
        print(f"  MISSING FILE: {m}")

    if scene["warnings"]:
        print(f"\n{len(scene['warnings'])} warning(s):")
        for w in scene["warnings"][:30]:
            print(f"  - {w}")

    return 1 if (scene["warnings"] or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
