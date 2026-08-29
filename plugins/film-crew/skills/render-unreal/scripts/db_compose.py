#!/usr/bin/env python3
"""Flatten a DragonBones rig into a single PNG cut-out.

A lot of the best free 2D characters ship as a modular rig — a folder of loose
limbs plus a skeleton file — which is useless to a renderer that wants one
sprite. Rather than eyeball the parts back together, this evaluates the rig the
way the runtime would: compose each bone's transform up the hierarchy, apply
the slot's display transform, and paste the parts in the armature's own draw
order. The result is the pose the artist actually authored.

    python3 db_compose.py magician_DB_ske.json out.png
    python3 db_compose.py magician_DB_ske.json walk.png --anim walk --frame 6

Only translate/rotate/scale bone timelines are evaluated. That covers the
standing and walking poses these rigs are usually wanted for; mesh deformation
and IK are ignored, so a rig that leans on them will come out in bind pose.
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image


def matrix(t):
    """DragonBones transform -> 3x3 affine. skX/skY are degrees and may differ,
    which is a skew rather than a rotation, so they are kept separate."""
    t = t or {}
    x = float(t.get("x", 0.0))
    y = float(t.get("y", 0.0))
    sk_x = math.radians(float(t.get("skX", 0.0)))
    sk_y = math.radians(float(t.get("skY", 0.0)))
    sc_x = float(t.get("scX", 1.0))
    sc_y = float(t.get("scY", 1.0))
    return np.array([
        [math.cos(sk_y) * sc_x, -math.sin(sk_x) * sc_y, x],
        [math.sin(sk_y) * sc_x, math.cos(sk_x) * sc_y, y],
        [0.0, 0.0, 1.0],
    ], dtype=float)


def blend(base, frames, index):
    """Bind-pose transform combined with an animation frame's offsets."""
    if not frames:
        return dict(base or {})
    total = 0
    chosen = frames[0]
    for f in frames:
        chosen = f
        total += int(f.get("duration", 0) or 0)
        if index < total:
            break
    out = dict(base or {})
    for k in ("x", "y"):
        if k in chosen:
            out[k] = float(out.get(k, 0.0)) + float(chosen[k])
    for k in ("skX", "skY"):
        if "rotate" in chosen:
            out[k] = float(out.get(k, 0.0)) + float(chosen["rotate"])
    for src, dst in (("scaleX", "scX"), ("scaleY", "scY")):
        if src in chosen:
            out[dst] = float(out.get(dst, 1.0)) * float(chosen[src])
    return out


def world_transforms(bones, anim_bones, frame):
    local, parent = {}, {}
    for b in bones:
        name = b["name"]
        parent[name] = b.get("parent")
        tl = anim_bones.get(name, {})
        t = b.get("transform")
        if tl:
            t = blend(t, tl.get("translateFrame"), frame)
            t = blend(t, tl.get("rotateFrame"), frame)
            t = blend(t, tl.get("scaleFrame"), frame)
        local[name] = matrix(t)

    world, resolving = {}, set()

    def resolve(name):
        if name in world:
            return world[name]
        if name in resolving:            # a cycle would otherwise hang
            world[name] = local[name]
            return world[name]
        resolving.add(name)
        p = parent.get(name)
        world[name] = (resolve(p) @ local[name]) if p and p in local else local[name]
        resolving.discard(name)
        return world[name]

    for b in bones:
        resolve(b["name"])
    return world


def db_matrix(v):
    """DragonBones packs a 2D matrix as [a, b, c, d, tx, ty]."""
    a, b, c, d, tx, ty = v
    return np.array([[a, c, tx], [b, d, ty], [0, 0, 1]], float)


def skin_vertices(display, bones, world):
    """Deform a weighted mesh by its bone weights.

    A weighted DragonBones mesh does not live in its slot's bone space: its
    vertices are authored in mesh space, carried into armature bind space by
    `slotPose`, and then driven by several bones at once. Multiplying such a
    mesh by its slot's parent bone — the way a plain image display is handled —
    stretches it into a giant blob. Each vertex has to be pushed into every
    influencing bone's local space using that bone's bind matrix, moved by the
    bone's current world matrix, and weight-blended back together.
    """
    weights = display.get("weights")
    slot_pose = display.get("slotPose")
    bone_pose = display.get("bonePose")
    if not weights or not slot_pose or not bone_pose:
        return None

    slot_m = db_matrix(slot_pose)

    # bonePose is a flat run of [boneIndex, a, b, c, d, tx, ty] groups, and the
    # weight list indexes them by position in that run, not by armature index.
    binds = []
    for i in range(0, len(bone_pose) - 6, 7):
        idx = int(bone_pose[i])
        binds.append((idx, db_matrix(bone_pose[i + 1:i + 7])))

    verts = display["vertices"]
    out, off = [], 0
    for i in range(len(verts) // 2):
        p = slot_m @ np.array([verts[i * 2], verts[i * 2 + 1], 1.0])
        count = int(weights[off]); off += 1
        acc = np.zeros(2)
        for _ in range(count):
            bi = int(weights[off]); w = float(weights[off + 1]); off += 2
            if bi >= len(binds):
                continue
            armature_index, bind = binds[bi]
            name = bones[armature_index]["name"] if armature_index < len(bones) else None
            try:
                local = np.linalg.inv(bind) @ p
            except np.linalg.LinAlgError:
                continue
            acc += w * (world.get(name, np.eye(3)) @ local)[:2]
        out.append((acc[0], acc[1]))
    return out


def paste_mesh(canvas, img, display, m, origin, dst=None):
    """Render a mesh display by warping each triangle individually.

    A mesh's vertices live in bone space and its UVs index the source image, so
    the two together define the mapping — the display transform that governs a
    plain image is meaningless here. Treating a mesh as a flat image is exactly
    how a rig's skirt or cape ends up as a giant undeformed blob.
    """
    verts = display.get("vertices") or []
    uvs = display.get("uvs") or []
    tris = display.get("triangles") or []
    if len(verts) < 6 or len(uvs) < 6 or not tris:
        return False

    w, h = img.size
    src = [(uvs[i * 2] * w, uvs[i * 2 + 1] * h) for i in range(len(uvs) // 2)]

    if dst is not None:
        dst = [(x + origin[0], y + origin[1]) for x, y in dst]
    else:
        dst = []
        for i in range(len(verts) // 2):
            p = m @ np.array([verts[i * 2], verts[i * 2 + 1], 1.0])
            dst.append((p[0] + origin[0], p[1] + origin[1]))

    from PIL import ImageDraw
    cw, ch = canvas.size

    for t in range(0, len(tris) - 2, 3):
        i0, i1, i2 = tris[t], tris[t + 1], tris[t + 2]
        if max(i0, i1, i2) >= min(len(src), len(dst)):
            continue
        s0, s1, s2 = src[i0], src[i1], src[i2]
        d0, d1, d2 = dst[i0], dst[i1], dst[i2]

        # Solve the affine that carries the source triangle onto the destination.
        a = np.array([[d0[0], d0[1], 1], [d1[0], d1[1], 1], [d2[0], d2[1], 1]], float)
        try:
            coef_x = np.linalg.solve(a, np.array([s0[0], s1[0], s2[0]], float))
            coef_y = np.linalg.solve(a, np.array([s0[1], s1[1], s2[1]], float))
        except np.linalg.LinAlgError:
            continue  # a degenerate triangle contributes nothing

        piece = img.transform(
            (cw, ch), Image.AFFINE,
            (coef_x[0], coef_x[1], coef_x[2], coef_y[0], coef_y[1], coef_y[2]),
            resample=Image.BICUBIC)

        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).polygon([d0, d1, d2], fill=255)
        piece.putalpha(Image.composite(piece.getchannel("A"),
                                       Image.new("L", (cw, ch), 0), mask))
        canvas.alpha_composite(piece)
    return True


def paste(canvas, img, m, origin):
    """Affine-paste an image whose local origin is its own centre."""
    w, h = img.size
    full = np.array([[1, 0, origin[0]], [0, 1, origin[1]], [0, 0, 1]], float) @ m
    full = full @ np.array([[1, 0, -w / 2.0], [0, 1, -h / 2.0], [0, 0, 1]], float)

    try:
        inv = np.linalg.inv(full)
    except np.linalg.LinAlgError:
        return  # a zero scale collapses the part; skip rather than crash

    cw, ch = canvas.size
    layer = img.transform(
        (cw, ch), Image.AFFINE,
        (inv[0, 0], inv[0, 1], inv[0, 2], inv[1, 0], inv[1, 1], inv[1, 2]),
        resample=Image.BICUBIC)
    canvas.alpha_composite(layer)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skeleton")
    ap.add_argument("out")
    ap.add_argument("--anim")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--pad", type=int, default=300,
                    help="canvas margin; the result is cropped to its alpha "
                         "afterwards, so err large or limbs get clipped")
    ap.add_argument("--hide", default="", help="comma-separated slots to omit")
    args = ap.parse_args()

    data = json.load(open(args.skeleton))
    base = os.path.dirname(os.path.abspath(args.skeleton))
    arm = data["armature"][0]
    hide = {s.strip() for s in args.hide.split(",") if s.strip()}

    anim_bones = {}
    if args.anim:
        found = [a for a in arm.get("animation", []) if a["name"] == args.anim]
        if not found:
            sys.exit("no animation %r; have %s"
                     % (args.anim, [a["name"] for a in arm.get("animation", [])]))
        anim_bones = {b["name"]: b for b in found[0].get("bone", [])}

    world = world_transforms(arm["bone"], anim_bones, args.frame)
    displays = {s["name"]: s["display"] for s in arm["skin"][0]["slot"]}

    aabb = arm["aabb"]
    pad = args.pad
    size = (int(aabb["width"]) + pad * 2, int(aabb["height"]) + pad * 2)
    origin = (-aabb["x"] + pad, -aabb["y"] + pad)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))

    drawn, skipped = 0, []
    for slot in arm["slot"]:
        name = slot["name"]
        if name in hide:
            continue
        entries = displays.get(name)
        if not entries:
            continue
        index = int(slot.get("displayIndex", 0) or 0)
        entry = entries[index] if index < len(entries) else entries[0]

        path = os.path.join(base, entry["name"] + ".png")
        if not os.path.exists(path):
            # DragonBones disambiguates repeated display names with a '_#N'
            # suffix that has no counterpart on disk.
            stripped = re.sub(r"_#\d+$", "", entry["name"])
            path = os.path.join(base, stripped + ".png")
        if not os.path.exists(path):
            skipped.append(entry["name"])
            continue

        bone = world.get(slot.get("parent"), np.eye(3))
        art = Image.open(path).convert("RGBA")
        if entry.get("type") == "mesh":
            skinned = skin_vertices(entry, arm["bone"], world)
            if paste_mesh(canvas, art, entry, bone, origin, dst=skinned):
                drawn += 1
                continue
        paste(canvas, art, bone @ matrix(entry.get("transform")), origin)
        drawn += 1

    bbox = canvas.getbbox()
    if not bbox:
        sys.exit("composited to an empty image — the rig did not resolve")
    canvas = canvas.crop(bbox)

    if args.scale != 1.0:
        canvas = canvas.resize(
            (max(1, int(canvas.width * args.scale)),
             max(1, int(canvas.height * args.scale))), Image.LANCZOS)

    canvas.save(args.out)
    print("%s  %dx%d  %d parts%s"
          % (args.out, canvas.width, canvas.height, drawn,
             ("  (missing: %s)" % ", ".join(skipped)) if skipped else ""))


if __name__ == "__main__":
    main()
