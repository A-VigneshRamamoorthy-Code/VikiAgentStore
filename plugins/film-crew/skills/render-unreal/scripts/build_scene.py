#!/usr/bin/env python3
"""Runs INSIDE Unreal. Turns a `scene.json` from cast_board.py into a level and
a Level Sequence, then saves both.

    UEA_SCENE=/abs/scene.json UEA_MAP=/Game/Maps/Film UEA_SEQ=/Game/Seq/SEQ_Film \
        ue.sh py Film.uproject build_scene.py

Deliberately dumb: every decision was already made by the compiler. This file
only creates assets and keys channels, which keeps the part that costs an
editor launch to test as boring as possible.
"""
import json
import os
import re
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_ue as U

EAL = unreal.EditorAssetLibrary
EAS = unreal.EditorActorSubsystem()
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary

TEX_PKG = "/Game/Tex"
MAT_PKG = "/Game/M"
PLANE = "/Engine/BasicShapes/Plane"

# The Plane primitive is 100x100 uu lying flat with its normal on +Z. Rolling it
# +90 stands it up facing +Y, which is where the camera is. Local X stays world
# X (screen right) and local Y becomes world -Z (screen down) — the same
# handedness as image space, so textures land upright.
PLANE_ROLL = 90.0
PLANE_UNIT = 100.0

CHANNELS = ("Location.X", "Location.Y", "Location.Z",
            "Rotation.X", "Rotation.Y", "Rotation.Z",
            "Scale.X", "Scale.Y", "Scale.Z")

_tex_cache = {}
_mat_cache = {}


def slug(path):
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    return name or "tex"


def unique(base, taken):
    name, n = base, 2
    while name in taken:
        name, n = "%s_%d" % (base, n), n + 1
    taken.add(name)
    return name


_taken_tex = set()

# Source-file timestamps of everything already imported, kept beside the project
# so a rebuild can tell a stale texture from an up-to-date one.
_STAMP_FILE = os.path.join(os.path.expanduser("~"), ".uea_texture_stamps.json")
try:
    with open(_STAMP_FILE) as _fh:
        _stamps = json.load(_fh)
except Exception:
    _stamps = {}


def save_stamps():
    try:
        with open(_STAMP_FILE, "w") as fh:
            json.dump(_stamps, fh)
    except Exception as exc:
        U.log("could not write texture stamps: %s" % exc)


def import_texture(src):
    """Import a PNG as a Texture2D, once, with settings that keep 2D art sharp.

    Compression is left off: DXT chews visible artefacts into the soft alpha
    edges that make cut-out artwork read as drawn rather than stamped, and mips
    are pointless for planes that are never seen at a steep angle.
    """
    if src in _tex_cache:
        return _tex_cache[src]

    name = unique(slug(src), _taken_tex)
    dest = "%s/%s" % (TEX_PKG, name)

    # Re-import whenever the file on disk has changed. Skipping an existing
    # asset is the obvious optimisation and it is a trap: edited artwork then
    # never reaches the engine, and the whole render lap looks identical to the
    # previous one with nothing to indicate why.
    stamp = str(os.path.getmtime(src)) if os.path.exists(src) else ""
    if not EAL.does_asset_exist(dest) or _stamps.get(dest) != stamp:
        task = unreal.AssetImportTask()
        task.filename = src
        task.destination_path = TEX_PKG
        task.destination_name = name
        task.automated = True
        task.replace_existing = True
        task.save = True
        task.factory = unreal.TextureFactory()
        AT.import_asset_tasks([task])
        _stamps[dest] = stamp

    tex = EAL.load_asset(dest)
    if tex is None:
        U.log("TEXTURE FAILED: %s" % src)
        return None

    tex.set_editor_property("compression_settings",
                            unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("mip_gen_settings",
                            unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("srgb", True)
    tex.set_editor_property("filter", unreal.TextureFilter.TF_TRILINEAR)
    EAL.save_asset(dest)

    _tex_cache[src] = tex
    return tex


def master_material():
    """One unlit, translucent, two-sided master that every sprite instances.

    Unlit because the artwork already contains its own shading; translucent
    rather than masked because masked cutouts turn every anti-aliased edge into
    a staircase. Translucency's usual sorting problem is dealt with per
    component via an explicit sort priority.
    """
    path = MAT_PKG + "/M_Sprite"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)

    unreal.EditorAssetLibrary.make_directory(MAT_PKG)
    mat = AT.create_asset("M_Sprite", MAT_PKG, unreal.Material,
                          unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("two_sided", True)

    tex = MEL.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
    tex.set_editor_property("parameter_name", "Tex")

    tint = MEL.create_material_expression(
        mat, unreal.MaterialExpressionVectorParameter, -700, 300)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))

    opacity = MEL.create_material_expression(
        mat, unreal.MaterialExpressionScalarParameter, -700, 480)
    opacity.set_editor_property("parameter_name", "Opacity")
    opacity.set_editor_property("default_value", 1.0)

    rgb = MEL.create_material_expression(
        mat, unreal.MaterialExpressionMultiply, -380, 60)
    MEL.connect_material_expressions(tex, "RGB", rgb, "A")
    MEL.connect_material_expressions(tint, "", rgb, "B")

    alpha = MEL.create_material_expression(
        mat, unreal.MaterialExpressionMultiply, -380, 400)
    MEL.connect_material_expressions(tex, "A", alpha, "A")
    MEL.connect_material_expressions(opacity, "", alpha, "B")

    MEL.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(alpha, "", unreal.MaterialProperty.MP_OPACITY)

    MEL.recompile_material(mat)
    EAL.save_asset(path)  # an unsaved material renders black in -game
    return mat


_taken_mat = set()


def sprite_material(src, tint=None, opacity=1.0):
    key = (src, tuple(tint) if tint else None, round(float(opacity), 3))
    if key in _mat_cache:
        return _mat_cache[key]

    tex = import_texture(src)
    if tex is None:
        return None

    name = unique("MI_" + slug(src), _taken_mat)
    path = "%s/%s" % (MAT_PKG, name)
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)

    mi = AT.create_asset(name, MAT_PKG, unreal.MaterialInstanceConstant,
                         unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, master_material())
    MEL.set_material_instance_texture_parameter_value(mi, "Tex", tex)
    if tint:
        MEL.set_material_instance_vector_parameter_value(
            mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
    if opacity != 1.0:
        MEL.set_material_instance_scalar_parameter_value(mi, "Opacity", float(opacity))
    EAL.save_asset(path)

    _mat_cache[key] = mi
    return mi


def texture_size(tex):
    w = float(tex.blueprint_get_size_x())
    h = float(tex.blueprint_get_size_y())
    return (w or 1.0), (h or 1.0)


def solve_scale(tex, spec, stage):
    """Turn a fit request into a plane scale, using the texture's real aspect.

    `cover` grows a backdrop until it overflows the frame on both axes at its
    own depth; `height` sizes a cut-out to a given world height and lets width
    follow from the art.
    """
    tw, th = texture_size(tex)

    if spec.get("fit") == "cover":
        ratio = float(spec.get("ratio", 1.0)) * float(spec.get("cover", 1.0))
        need_w = stage["w"] * ratio
        need_h = stage["h"] * ratio
        s = max(need_w / tw, need_h / th)
        return tw * s, th * s

    h = float(spec.get("height_uu", 200.0))
    return h * (tw / th), h


def spawn_plane(spec, stage, sort_priority, label):
    mi = sprite_material(spec["texture"], spec.get("tint"),
                         spec.get("opacity", 1.0))
    if mi is None:
        return None
    tex = _tex_cache[spec["texture"]]
    w, h = solve_scale(tex, spec, stage)

    a = EAS.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(float(spec["x"]), float(spec["y"]), float(spec["z"])),
        unreal.Rotator(PLANE_ROLL, 0.0, 0.0))
    c = a.static_mesh_component
    c.set_static_mesh(EAL.load_asset(PLANE))

    sx = w / PLANE_UNIT
    if spec.get("flip"):
        sx = -sx  # the master material is two-sided, so a mirror is safe
    a.set_actor_scale3d(unreal.Vector(sx, h / PLANE_UNIT, 1.0))

    c.set_material(0, mi)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property("cast_shadow", False)
    # Deterministic draw order: the further back, the earlier it is painted.
    c.set_editor_property("translucency_sort_priority", int(sort_priority))
    a.set_actor_label(label)
    return a


def spawn_camera(shot, lens, label):
    cam = EAS.spawn_actor_from_class(
        unreal.CineCameraActor,
        unreal.Vector(shot["camera"]["from"]["x"],
                      shot["camera"]["from"]["y"],
                      shot["camera"]["from"]["z"]),
        unreal.Rotator(0.0, 0.0, -90.0))  # on +Y looking -Y, so +X reads right
    cam.set_actor_label(label)

    cc = cam.camera_component
    filmback = unreal.CameraFilmbackSettings()
    filmback.set_editor_property("sensor_width", lens["sensor_w"])
    filmback.set_editor_property("sensor_height", lens["sensor_h"])
    cc.set_editor_property("filmback", filmback)

    focus = unreal.CameraFocusSettings()
    focus.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", focus)
    cc.set_editor_property("current_focal_length", lens["focal_mm"])

    pp = unreal.PostProcessSettings()
    # Flat artwork must render as the exact colours it was drawn in. UE's
    # default filmic curve is built for photographic latitude and it desaturates
    # and shifts flat fills badly — measured on this pipeline, a (240,186,70)
    # yellow came back as (220,134,95). Bypassing the tone curve and gamut
    # expansion turns the render into a faithful compositor instead of a camera.
    for k, v in [("auto_exposure_min_brightness", 1.0),
                 ("auto_exposure_max_brightness", 1.0),
                 ("auto_exposure_bias", 0.0),
                 ("tone_curve_amount", 0.0),
                 ("expand_gamut", 0.0),
                 ("blue_correction", 0.0),
                 ("bloom_intensity", 0.0),
                 ("vignette_intensity", 0.0),
                 ("film_grain_intensity", 0.0),
                 ("scene_fringe_intensity", 0.0),
                 ("motion_blur_amount", 0.0)]:
        pp.set_editor_property("override_" + k, True)
        pp.set_editor_property(k, v)
    cc.set_editor_property("post_process_settings", pp)
    return cam


def transform_section(binding, actor):
    """A transform section seeded from the actor's live transform.

    An unkeyed channel on a new section evaluates as 0.0, so keying one axis
    would otherwise zero the actor's rotation and scale — silently, and with a
    log that still says the capture succeeded.
    """
    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    sec = track.add_section()
    sec.set_start_frame_bounded(False)
    sec.set_end_frame_bounded(False)

    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scl = actor.get_actor_scale3d()
    live = dict(zip(CHANNELS, (loc.x, loc.y, loc.z,
                               rot.roll, rot.pitch, rot.yaw,
                               scl.x, scl.y, scl.z)))

    channels = {}
    for ch in sec.get_all_channels():
        name = str(ch.get_name())  # carries a trailing '_0'
        for key, value in live.items():
            if name.startswith(key):
                try:
                    ch.set_default(value)
                except Exception:
                    ch.add_key(unreal.FrameNumber(0), value)
                channels[key] = ch
                break
    return sec, channels


def key(channel, frame, value):
    channel.add_key(unreal.FrameNumber(int(frame)), float(value))


def main():
    scene_path = os.environ.get("UEA_SCENE")
    map_path = os.environ.get("UEA_MAP", "/Game/Maps/Film")
    seq_path = os.environ.get("UEA_SEQ", "/Game/Seq/SEQ_Film")
    if not scene_path or not os.path.exists(scene_path):
        U.log("UEA_SCENE missing or not found: %r" % scene_path)
        U.dump_log()
        return

    scene = json.load(open(scene_path))
    stage = scene["stage"]
    lens = scene["lens"]
    fps = scene["fps"]

    U.reset_level(map_path)
    master_material()

    cameras = {}
    movers = []          # (actor, shot) pairs that need animating
    n_planes = 0

    for shot in scene["shots"]:
        sid = shot["id"]

        # Back to front, so the sort priority rises towards the camera.
        for i, layer in enumerate(shot["layers"]):
            if spawn_plane(layer, stage, i, "%s_bg%d" % (sid, i)):
                n_planes += 1

        base = len(shot["layers"])
        for i, prop in enumerate(shot["props"]):
            # The halo is painted first so the prop reads on top of its own glow.
            if prop.get("halo"):
                if spawn_plane(prop["halo"], stage, base + i * 2,
                               "%s_halo_%s" % (sid, prop["kind"])):
                    n_planes += 1
            a = spawn_plane(prop, stage, base + i * 2 + 1,
                            "%s_prop_%s" % (sid, prop["kind"]))
            if a:
                n_planes += 1

        base += len(shot["props"]) * 2
        for i, act in enumerate(shot["actors"]):
            a = spawn_plane(act, stage, base + i, "%s_%s" % (sid, act["id"]))
            if a:
                n_planes += 1
                if act.get("to"):
                    movers.append((a, shot, act))

        cameras[sid] = spawn_camera(shot, lens, "CAM_" + sid)

    U.log("spawned %d planes, %d cameras" % (n_planes, len(cameras)))
    U.save_level(map_path)

    # ---------------------------------------------------------------- sequence
    seq_dir, seq_name = seq_path.rsplit("/", 1)
    if EAL.does_asset_exist(seq_path):
        EAL.delete_asset(seq_path)
    seq = AT.create_asset(seq_name, seq_dir, unreal.LevelSequence,
                          unreal.LevelSequenceFactoryNew())
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start_seconds(0.0)
    seq.set_playback_end_seconds(float(scene["duration"]))

    cut = seq.add_track(unreal.MovieSceneCameraCutTrack)
    sections = []

    for shot in scene["shots"]:
        cam = cameras[shot["id"]]
        f0 = int(round(shot["start"] * fps))
        f1 = int(round(shot["end"] * fps))

        b = seq.add_possessable(cam)
        sec = cut.add_section()
        sec.set_range(f0, f1)
        bid = unreal.MovieSceneObjectBindingID()
        bid.set_editor_property("guid", b.get_id())
        sec.set_camera_binding_id(bid)

        c = shot["camera"]
        moved = (abs(c["from"]["x"] - c["to"]["x"]) > 0.01 or
                 abs(c["from"]["y"] - c["to"]["y"]) > 0.01 or
                 abs(c["from"]["z"] - c["to"]["z"]) > 0.01)
        if moved:
            tsec, ch = transform_section(b, cam)
            sections.append(tsec)
            # A hold delays the move without shortening it at the tail.
            fh = f0 + int(round(shot["camera"].get("hold", 0.0) * fps))
            for axis, name in (("x", "Location.X"), ("y", "Location.Y"),
                               ("z", "Location.Z")):
                key(ch[name], f0, c["from"][axis])
                if fh > f0:
                    key(ch[name], fh, c["from"][axis])
                key(ch[name], f1, c["to"][axis])

    for actor_obj, shot, act in movers:
        f0 = int(round(shot["start"] * fps))
        f1 = int(round(shot["end"] * fps))
        b = seq.add_possessable(actor_obj)
        tsec, ch = transform_section(b, actor_obj)
        sections.append(tsec)
        key(ch["Location.X"], f0, act["x"])
        key(ch["Location.X"], f1, act["to"]["x"])

        # A cut-out held in one pose and slid sideways reads as a sticker being
        # dragged. Two paces per second of vertical bob, plus a matching sway,
        # is enough for the eye to accept it as walking without a real cycle.
        bob = float(act.get("bob") or 0.0)
        if bob <= 0.0 or f1 <= f0:
            key(ch["Location.Z"], f0, act["z"])
            key(ch["Location.Z"], f1, act["to"]["z"])
            continue

        steps = max(2, int((f1 - f0) / fps * 4.0))
        for i in range(steps + 1):
            t = i / steps
            f = int(round(f0 + (f1 - f0) * t))
            z = act["z"] + (act["to"]["z"] - act["z"]) * t
            key(ch["Location.Z"], f, z + (bob if i % 2 else 0.0))
            key(ch["Rotation.Y"], f, (1.2 if i % 2 else -1.2))

    EAL.save_asset(seq_path)

    empty = [c for s in sections for c in s.get_all_channels()
             if c.get_num_keys() == 0]
    U.log("sequence %s: %d cuts, %d transform sections, %d unkeyed channels"
          % (seq_path, len(scene["shots"]), len(sections), len(empty)))

    result = {
        "map": map_path,
        "sequence": seq_path,
        "planes": n_planes,
        "cameras": len(cameras),
        "textures": len(_tex_cache),
        "movers": len(movers),
        "duration": scene["duration"],
        "fps": fps,
    }
    with open("/tmp/ue_build_result.json", "w") as fh:
        json.dump(result, fh, indent=1)
    save_stamps()
    U.log("RESULT " + json.dumps(result))
    U.dump_log()


main()
