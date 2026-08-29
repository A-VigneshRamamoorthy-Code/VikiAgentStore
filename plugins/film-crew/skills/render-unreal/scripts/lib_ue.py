"""Reusable UE-side helpers. Copy next to your scene script and `import lib_ue`.

Wraps the calls whose argument order, ordering constraints or side effects are
easy to get wrong. Everything here has run headlessly on UE 5.8.

    import lib_ue as U
    U.reset_level("/Game/Maps/Shot")
    ink  = U.unlit_material("M_INK", (0.01, 0.012, 0.028))
    pm   = U.physical_material("PM_Grip")
    U.spawn(U.CUBE, (0, 0, -25), scale=(40, 4, 0.5), mat=ink, name="Ground")
    U.ortho_camera((-40, 1500, 190), ortho_width=1280.0)
    U.save_level("/Game/Maps/Shot")
"""
import unreal

LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

CUBE = unreal.load_asset("/Engine/BasicShapes/Cube")      # 100 cm cube
SPHERE = unreal.load_asset("/Engine/BasicShapes/Sphere")
CYLINDER = unreal.load_asset("/Engine/BasicShapes/Cylinder")
PLANE = unreal.load_asset("/Engine/BasicShapes/Plane")

_LOG = []


def log(m):
    _LOG.append(str(m))
    unreal.log("UEA " + str(m))


def dump_log(path="/tmp/ue_build.txt"):
    open(path, "w").write("\n".join(_LOG))


# ------------------------------------------------------------------ level ----

def reset_level(map_path):
    """Idempotent: wipe the level if it exists, else create it."""
    if EAL.does_asset_exist(map_path):
        LES.load_level(map_path)
        for a in EAS.get_all_level_actors():
            EAS.destroy_actor(a)
    else:
        LES.new_level(map_path)


def save_level(map_path):
    """`save_current_level()` fails after `new_level()` — use save_map."""
    ok = unreal.EditorLoadingAndSavingUtils.save_map(UES.get_editor_world(), map_path)
    log("save_map(%s)=%s actors=%d" % (map_path, ok, len(EAS.get_all_level_actors())))
    return ok


def actor(label):
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def dump_transforms(path="/tmp/ue_transforms.txt"):
    """Triage tool: are the SAVED transforms right? If yes, any visual fault is
    in the solver or the capture, not in the build script."""
    rows = []
    for a in sorted(EAS.get_all_level_actors(), key=lambda x: x.get_actor_label()):
        l, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
        rows.append("%-16s pos=(%9.2f,%8.2f,%8.2f) rot=(%6.2f,%6.2f,%6.2f) scale=(%.2f,%.2f,%.2f)"
                    % (a.get_actor_label(), l.x, l.y, l.z, r.roll, r.pitch, r.yaw, s.x, s.y, s.z))
    open(path, "w").write("\n".join(rows))
    return rows


# --------------------------------------------------------------- materials ----

def _fresh(name, pkg, cls, factory):
    p = pkg + "/" + name
    if EAL.does_asset_exist(p):
        EAL.delete_asset(p)
    return AT.create_asset(name, pkg, cls, factory), p


def unlit_material(name, rgb, pkg="/Game/M"):
    """Flat, shadeless colour. With an ortho camera this reads as 2D art.

    Colours are LINEAR, so they render brighter than the numbers suggest.
    """
    m, p = _fresh(name, pkg, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    c = unreal.MaterialEditingLibrary.create_material_expression(
        m, unreal.MaterialExpressionConstant3Vector, -300, 0)
    c.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    unreal.MaterialEditingLibrary.connect_material_property(
        c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(m)
    EAL.save_asset(p)          # unsaved materials -> a black render in -game
    return m


def physical_material(name, friction=0.45, restitution=0.12, pkg="/Game/M"):
    pm, p = _fresh(name, pkg, unreal.PhysicalMaterial, unreal.PhysicalMaterialFactoryNew())
    pm.set_editor_property("friction", friction)
    pm.set_editor_property("restitution", restitution)
    EAL.save_asset(p)
    return pm


# ------------------------------------------------------------------ actors ----

def spawn(mesh, loc, rot=(0, 0, 0), scale=(1, 1, 1), mat=None, name=None,
          sim=False, mass=None, phys_mat=None, angular_damping=0.0,
          plane_lock=True):
    """Spawn a StaticMeshActor. Order matters:
    mesh -> scale -> material -> mobility -> simulate -> constraint -> physmat.

    rot is (roll, pitch, yaw). For a side-on XZ shot, `pitch` tilts in-plane.
    Prefer an UPRIGHT pose for anything that must stand: a tilted box rests on a
    single edge, rocks onto its face, and can topple itself. Use resting_z().
    """
    a = EAS.spawn_actor_from_class(unreal.StaticMeshActor,
                                   unreal.Vector(*loc), unreal.Rotator(*rot))
    c = a.static_mesh_component
    c.set_static_mesh(mesh)
    a.set_actor_scale3d(unreal.Vector(*scale))
    if mat is not None:
        c.set_material(0, mat)
    if name:
        a.set_actor_label(name)
    if sim:
        c.set_mobility(unreal.ComponentMobility.MOVABLE)   # must precede simulate
        c.set_simulate_physics(True)
        if plane_lock:
            c.set_constraint_mode(unreal.DOFMode.XZ_PLANE)
        if phys_mat is not None:
            c.set_phys_material_override(phys_mat)         # a method, not a property
        c.set_angular_damping(angular_damping)
        if mass:
            c.set_mass_override_in_kg("None", mass, True)  # "None" string, not name_none
    else:
        c.set_mobility(unreal.ComponentMobility.STATIC)
    return a


def spawn_skeletal(mesh, loc, rot=(0, 0, -90), scale=(1, 1, 1), mat=None,
                   name=None, anim=None, simulate=False):
    """Spawn a SkeletalMeshActor (a character).

    Note the differences from spawn(): a different actor class, a different
    component accessor, EVERY material slot must be overridden for the flat 2D
    look, and the origin is at the FEET -- pass loc z = ground_z, never
    resting_z(), which is box maths.

    `anim` sets a single-node pose so the mesh is not a T-pose in the editor;
    for a RENDER the animation must also go on a MovieSceneSkeletalAnimationTrack
    (see reference/assets-and-characters.md).
    """
    a = EAS.spawn_actor_from_class(unreal.SkeletalMeshActor,
                                   unreal.Vector(*loc),
                                   unreal.Rotator(rot[0], rot[1], rot[2]))
    if name:
        a.set_actor_label(name)
    c = a.skeletal_mesh_component
    c.set_skeletal_mesh(mesh)
    a.set_actor_scale3d(unreal.Vector(*scale))
    if mat is not None:
        for i in range(c.get_num_materials()):    # slot counts differ per mesh
            c.set_material(i, mat)
    if anim is not None:
        c.set_editor_property("animation_mode",
                              unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        c.set_animation(anim)
        c.play(True)
    if simulate:
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        c.set_simulate_physics(True)              # full ragdoll; needs a PhysicsAsset
    return a


def anim_track(seq, binding, anim, start, end, play_rate=None):
    """Attach an AnimSequence to a sequence binding so it actually renders.

    Short clips loop to fill the section. play_rate is a MovieSceneTimeWarpVariant
    in UE5.8, not a float -- omit it unless you need it.
    """
    track = binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    sec = track.add_section()
    p = unreal.MovieSceneSkeletalAnimationParams()
    p.set_editor_property("animation", anim)
    if play_rate is not None:
        tw = unreal.MovieSceneTimeWarpVariant()
        tw.set_fixed_play_rate(play_rate)
        p.set_editor_property("play_rate", tw)
    sec.set_editor_property("params", p)
    sec.set_range(start, end)
    return sec


def transform_channel(section, name):
    """Fetch a transform channel by logical name.

    Channels are really called 'Location.X_0', 'Rotation.Z_0', ... -- an exact
    == match raises IndexError.
    """
    for ch in section.get_all_channels():
        if str(ch.get_name()).startswith(name):
            return ch
    raise KeyError("%s not in %s" % (
        name, [str(c.get_name()) for c in section.get_all_channels()]))


def balance_angle(width_cm, height_cm):
    """Degrees from vertical at which an upright box tips over. Keep any
    deliberate lean well inside this (about a third of it)."""
    import math
    return math.degrees(math.atan(width_cm / float(height_cm)))


def resting_z(width_cm, height_cm, lean_deg=0.0, gap=0.1, ground_z=0.0):
    """Centre height at which a LEANING box just rests on the ground.

    A tilted box pivots about its lowest corner, which sits higher than h/2:

        z = (h/2)*cos(lean) + (w/2)*sin(lean) + gap

    Using plain `h/2` with a lean buries that corner in the floor. The solver
    resolves the penetration with an impulse that rotates the box — and one
    piece in a row spontaneously topples before anything touches it. This is
    the single easiest way to get a chain reaction that triggers itself.
    """
    import math
    r = math.radians(abs(lean_deg))
    return ground_z + (height_cm / 2.0) * math.cos(r) + (width_cm / 2.0) * math.sin(r) + gap


# ------------------------------------------------------------------ camera ----

def ortho_camera(loc, ortho_width=1280.0, label="ShotCam",
                 rot=(0, 0, -90), bloom=0.22, near=1.0, far=6000.0):
    """Orthographic side camera.

    Default rot (0,0,-90) expects the camera on +Y looking towards -Y, which
    makes +X read to the RIGHT. Yaw +90 mirrors the shot.
    Exposure is locked, otherwise the palette washes out and drifts mid-shot.
    """
    cam = EAS.spawn_actor_from_class(unreal.CineCameraActor,
                                     unreal.Vector(*loc), unreal.Rotator(*rot))
    cam.set_actor_label(label)
    cc = cam.camera_component
    cc.set_editor_property("projection_mode", unreal.CameraProjectionMode.ORTHOGRAPHIC)
    cc.set_editor_property("ortho_width", float(ortho_width))
    cc.set_editor_property("ortho_near_clip_plane", near)
    cc.set_editor_property("ortho_far_clip_plane", far)
    pp = unreal.PostProcessSettings()
    for k, v in [("auto_exposure_min_brightness", 1.0),
                 ("auto_exposure_max_brightness", 1.0),
                 ("auto_exposure_bias", 0.0),
                 ("bloom_intensity", bloom),
                 ("vignette_intensity", 0.0)]:
        pp.set_editor_property("override_" + k, True)
        pp.set_editor_property(k, v)
    cc.set_editor_property("post_process_settings", pp)
    return cam
