"""Export the character rig + animations to the .glb the game actually loads.

    blender -b assets/characters/shino/shino.blend --python blender/tools/export_character.py

The game loads the exported `.glb` (`CharacterVisuals_<Body>.tscn` instances it), never the .blend —
so a .blend edit is invisible to the game until this runs, and the shared clip library is rebuilt
(`tools/godot/build_character_anims.gd`) from that .glb. Settings below are the ones the shipped
.glb was produced with; changing them changes every clip at once, so change them deliberately.

Two naming rules the pipeline depends on (see CLAUDE.md "Animation"):
  * the glTF animation name is the ACTION name, and Godot's importer strips a trailing `-loop`
    (that suffix is what sets loop mode) — action `crouch_idle-loop` -> clip `crouch_idle`;
  * an action that is both the object's ACTIVE action and stashed exports twice, merged into one
    animation with doubled channels. Keep one named NLA track per clip and no active action;
    `check_character_anim.py` fails the build if that regresses.
"""
import bpy
import os
import sys

# Derived from the .blend being exported, so ONE exporter serves every body. A hardcoded output
# meant a second character could only be built by editing this file, and a mistake there would
# silently overwrite the first body's export.
#
# This .blend is the CLIP SOURCE as well as a body: the shared library
# (src/main/resources/com/openworld/character/anim/character_anims.res) is built from its export by
# tools/godot/build_character_anims.gd. A body brought in from a .vrm carries no clips at all --
# see blender/tools/import_vrm_body.py and blender/SKELETON_CONTRACT.md.
OUT = os.path.splitext(bpy.data.filepath)[0] + ".glb"

def deform_armature():
    """The armature the MESHES are skinned to -- the only one that may reach the export.

    Found through the meshes rather than by name, so one exporter serves every body and a second
    armature in the file (an authoring control rig) can never be mistaken for it.
    """
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for m in ob.modifiers:
            if m.type == 'ARMATURE' and m.object is not None:
                return m.object
    return bpy.data.objects.get("Godot_Chan_Stealth")


arm = deform_armature()
if arm is not None and arm.animation_data is not None and arm.animation_data.action is not None:
    print(f"[export_character] clearing active action {arm.animation_data.action.name!r} "
          f"(it would export a second time)")
    arm.animation_data.action = None


# ---------------------------------------------------------------- the control rig: bake, then off
#
# THE ARTIST NEVER TOUCHES A SWITCH. The file opens with its control rig ON (Auto-Rig Pro poses the
# body; game_export_ui.py turns it on at load), and the EXPORT is what knows the rig must be off:
#   1. every clip that lives on the rig (`ARP_<clip>`) is baked into its game clip `<clip>`
#      (blender/tools/arp_clips.py, the one owner of that bake);
#   2. every control-rig switch -- ARP's `drive_game_rig`, our own layer's `CTRL_root["ik_*"]` -- goes to 0,
#      so the game clips play on the 53 bones exactly as authored;
#   3. after the export -- or a refusal -- every switch is put back as it was.
# It lives HERE rather than in the button so that a command-line export does the same thing: a
# second path that skipped the bake would ship a stale clip and look perfectly fine.
SWITCH_KEYS = ("drive_game_rig",)


def _drivers_refresh():
    # tag + depsgraph update: re-setting (or stepping) the frame did NOT re-evaluate the switch drivers in
    # every file -- measured, all 312 influences stayed 1.0 and the export was refused
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            ob.update_tag(refresh={'OBJECT', 'DATA'})
    bpy.context.evaluated_depsgraph_get().update()
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)


if any(a.name.startswith("ARP_") for a in bpy.data.actions):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import arp_clips
    _stripped = arp_clips.strip_switch_keys()
    if _stripped:
        print(f"[export_character] removed {_stripped} key curve(s) on the rig switch from ARP clips "
              f"(the switch is never animation -- a keyed one undoes the export's switch-off)")
    print(f"[export_character] baked the control-rig clips into their game clips: {arp_clips.bake_all()}")

_switches = []
for _ob in bpy.data.objects:
    if _ob.type == 'ARMATURE' and _ob.pose is not None:
        for _pb in _ob.pose.bones:
            for _k in list(_pb.keys()):
                if _k in SWITCH_KEYS or (_pb.name == "CTRL_root" and _k.startswith("ik_")):
                    _switches.append((_pb, _k, _pb[_k]))
                    _pb[_k] = 0.0
if _switches:
    _drivers_refresh()
    print(f"[export_character] control rig off for the export ({len(_switches)} switch(es)); "
          f"it is switched back afterwards")


def _switches_back():
    for pb, k, v in _switches:
        pb[k] = v
    if _switches:
        _drivers_refresh()


# ---------------------------------------------------------------- authoring data is neutralised
#
# ONE FILE, AND THE EXPORT ENFORCES THE SEPARATION RATHER THAN THE ARTIST REMEMBERING IT.
#
# A control rig may live in this .blend beside the deform armature -- that is the whole point of
# `blender/tools/add_control_rig.py`, and an ARP or Rigify rig would sit here too. Three things then
# have to be true of the export, and only the first two were already handled:
#
#   1. control BONES must not become joints. `export_def_bones=True` below does that (measured: a
#      CTRL_ bone comes through as a 54th joint without it).
#   2. widget objects must not become meshes. They live in a hidden collection and `use_visible`
#      drops them.
#   3. NOTHING MAY BE DRIVING THE DEFORM BONES. The exporter samples the EVALUATED pose, so a live
#      constraint is baked into every clip it touches -- an artist who left the IK switch on would
#      ship 167 clips with an IK result welded into them, and nothing downstream could tell.
#
# So the export mutes every constraint on the deform armature and hides every other armature, and
# then CHECKS that doing so changed nothing. If it changed something, a constraint was contributing
# to the pose and the export would be wrong either way -- so it refuses instead of writing a file
# that looks fine. Same shape as `export_world.py` unlinking the ground cutters and restoring them,
# and `NavBaker.NO_PED_TOKEN` clearing collision layers for the duration of a parse.
def evaluated_pose(a):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = a.evaluated_get(dg).pose.bones
    # DEFORM bones only: they are what reaches the skin and the file. A control rig's own machinery
    # (the hidden MCH_ solving chain, add_control_rig.py) is SUPPOSED to move when its IK is muted,
    # and counting it refused a file whose every deform bone was bit-identical (measured: MCH_F_
    # lowerarm_l "moved 0.327 m" while the worst deform bone moved 0.000000).
    return {b.name: ev[b.name].matrix.translation.copy() for b in a.pose.bones if b.bone.use_deform}


def neutralise(a):
    """Mute the deform armature's constraints and hide every other armature. Returns an undo."""
    muted = []
    for pb in a.pose.bones:
        for con in pb.constraints:
            if not con.mute:
                con.mute = True
                muted.append(con)
    hidden = []
    # ONLY THE BODY'S OWN MESHES EXPORT. A mesh no Armature modifier binds to this armature is a
    # reference the artist posed against -- a gun placed in the hand, a prop -- and `use_visible` would
    # have shipped it inside the character (measured: a stray ASR1 and SHG1 floating behind her head).
    was = {}                                    # object -> (hide_render, hide_viewport, hide_get) before
    anc = set()
    p = a.parent
    while p is not None:
        anc.add(p)
        p = p.parent
    for ob in bpy.data.objects:
        stray_mesh = ob.type == 'MESH' and not any(m.type == 'ARMATURE' and m.object is a for m in ob.modifiers)
        stray_empty = ob.type == 'EMPTY' and ob not in anc      # socket previews, weapon instances, markers
        if (stray_mesh or stray_empty) and ob.visible_get():
            was[ob] = (ob.hide_render, ob.hide_viewport, ob.hide_get())
            ob.hide_render = ob.hide_viewport = True
            ob.hide_set(True)
            hidden.append(ob)
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE' and ob is not a and (not ob.hide_render or not ob.hide_viewport):
            was.setdefault(ob, (ob.hide_render, ob.hide_viewport, ob.hide_get()))
            ob.hide_render = ob.hide_viewport = True
            if ob not in hidden:
                hidden.append(ob)
    # ...and whatever a hidden rig hangs from: Auto-Rig Pro parents its `rig` under an empty
    # `char_grp`, which otherwise exports as a stray node (measured: 165 nodes against 164). The game
    # armature's own ancestors stay.
    ours = set()
    p = a.parent
    while p is not None:
        ours.add(p)
        p = p.parent
    for rig in [o for o in list(hidden) if o.type == 'ARMATURE']:
        p = rig.parent
        while p is not None and p not in ours:
            if not p.hide_viewport or not p.hide_render:
                was.setdefault(p, (p.hide_render, p.hide_viewport, p.hide_get()))
                p.hide_viewport = p.hide_render = True
                hidden.append(p)
            p = p.parent

    def undo():
        for con in muted:
            con.mute = False
        for ob in hidden:
            r, v, g = was.get(ob, (False, False, False))
            ob.hide_render, ob.hide_viewport = r, v
            ob.hide_set(g)
    return muted, hidden, undo


restore = None
if arm is not None:
    before = evaluated_pose(arm)
    muted, hidden, restore = neutralise(arm)
    after = evaluated_pose(arm)
    moved = max(((before[n] - after[n]).length for n in before), default=0.0)
    print(f"[export_character] neutralised {len(muted)} constraint(s) and hid {len(hidden)} other "
          f"armature(s); the pose moved {moved:.6f} m")
    if moved > 1e-5:
        worst = max(before, key=lambda n: (before[n] - after[n]).length)
        restore()
        _switches_back()
        raise SystemExit(
            f"[export_character] REFUSED: a live constraint is driving the deform armature "
            f"({worst!r} moves {moved:.4f} m when it is muted). The exporter samples the EVALUATED "
            f"pose, so that result would be baked into every clip. Switch the control rig off "
            f'(the switches this exporter knows are already off -- this is some other constraint) '
            f'and export again.')

# A MUTED CONSTRAINT STILL CHANGES THE FILE. Blender's glTF exporter decides per channel whether to
# read the action's curves or to resample the evaluated pose, and ANY constraint on the bone forces
# the resample (`fcurves/channels.py`: `len(animation_target.constraints) != 0` -> "Baking animation
# because of unsupported constraints"), muted or not. Measured with Auto-Rig Pro's 312 constraints
# on Shino: identical key values, but 652 channels in 32 clips went STEP -> LINEAR, i.e. Godot would
# blend between keys the shipped file holds. So when the armature carries constraints the export is
# made from a TEMPORARY copy with none -- same name, same armature data, same clips -- which the meshes
# are pointed at for the duration, and which is deleted afterwards. The guard above has already
# proved the constraints contribute nothing to the pose, so dropping them changes no value.
export_copy = None
if arm is not None and any(len(pb.constraints) for pb in arm.pose.bones):
    real_name = arm.name
    export_copy = arm.copy()                       # shares the armature data and the NLA tracks
    for coll in arm.users_collection:
        coll.objects.link(export_copy)
    if export_copy.animation_data:
        for fc in list(export_copy.animation_data.drivers):
            export_copy.animation_data.drivers.remove(fc)
    for pb in export_copy.pose.bones:
        for con in list(pb.constraints):
            pb.constraints.remove(con)
    repointed = []
    for ob in bpy.data.objects:
        for m in ob.modifiers:
            if m.type == 'ARMATURE' and m.object == arm:
                m.object = export_copy
                repointed.append(m)
        if ob.parent is arm:
            mw = ob.matrix_world.copy()
            ob.parent = export_copy
            ob.matrix_world = mw
    arm.name = real_name + "__constrained"         # the glTF node keeps the real name
    export_copy.name = real_name
    arm.hide_viewport = arm.hide_render = True
    print(f"[export_character] exporting from a constraint-free copy of {real_name!r} "
          f"({len(repointed)} mesh(es) re-pointed)")
    game_arm = export_copy
else:
    game_arm = arm

# THE GLTF SCENE CARRIES NO EXTRAS. export_extras writes every custom AND add-on property of the Blender
# scene into it: Auto-Rig Pro's limb map and its retarget settings (`source_action`, `bones_map_index`,
# ...) and the action filter below -- measured, 170 entries, none of which the game reads. The shipped
# file has no scene extras, and extras must stay on (108 clips and a mesh carry their own), so for the
# duration of the export the exporter's scene gatherer is handed a `generate_extras` that answers None
# for a Scene and defers to the original for everything else.
import importlib
_gather = importlib.import_module(bpy.types.EXPORT_SCENE_OT_gltf.__module__.split(".")[0] + ".blender.exp.gather")
# kept on the module, so an export that died half-way (the button runs this inside the session) cannot
# leave a wrapper that the next export then wraps again
_orig_generate_extras = _gather.__dict__.setdefault("_ow_orig_generate_extras", _gather.generate_extras)
_gather.generate_extras = lambda el: None if isinstance(el, bpy.types.Scene) else _orig_generate_extras(el)

# CONTROL-RIG ACTIONS ARE NOT GAME CLIPS. With `export_animation_mode='ACTIONS'` the glTF exporter takes
# every action that animates ANY bone of the armature, and an Auto-Rig Pro action (`ARP_<clip>`, see
# blender/tools/arp_clips.py) shares the finger and hair bone names -- measured, it came through as a
# 169th clip. The exporter's own per-action filter (`Scene.gltf_action_filter`, keep=False) leaves them
# out; it is registered for the export only and removed after.
_gltf = sys.modules[bpy.types.EXPORT_SCENE_OT_gltf.__module__.split(".")[0]]
_rig_actions = [a for a in bpy.data.actions if a.name.startswith("ARP_")]
_filter_added = False
if _rig_actions and not hasattr(bpy.context.scene, "gltf_action_filter"):
    import types as _types
    _gltf.on_export_action_filter_changed(_types.SimpleNamespace(export_action_filter=True), bpy.context)
    _filter_added = True
if _rig_actions:
    for item in bpy.data.scenes[0].gltf_action_filter:
        if item.action is not None and item.action.name.startswith("ARP_"):
            item.keep = False
    print(f"[export_character] leaving out {len(_rig_actions)} control-rig action(s): "
          f"{', '.join(a.name for a in _rig_actions)}")

# The exporter starts with `mode_set(OBJECT)` on the ACTIVE object, and a control rig in the file
# (Auto-Rig Pro leaves its `rig` active) has just been hidden above -- "Cannot edit hidden object".
# The game armature is the one thing this export is about, so it is the active one.
if game_arm is not None:
    bpy.context.view_layer.objects.active = game_arm

bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLB',
    use_visible=True,          # keeps the scratch `Icosphere` out of the export
    export_yup=True,
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_tangents=True,
    export_vertex_color='NONE',
    export_materials='EXPORT',
    export_extras=True,
    export_cameras=True,
    export_lights=True,
    export_skins=True,
    export_all_influences=True,
    # TRUE since the control layer landed (blender/tools/add_control_rig.py): a CTRL_ bone is not a
    # deform bone, but `use_deform = False` does NOT keep it out of the export -- measured, it comes
    # through as a 54th joint with its own animation track, which breaks the 53-bone contract
    # silently. With this on: 53 joints, no CTRL_ node, no CTRL_ track, all 171 clips, and an IK
    # result still fully baked (the exporter samples the evaluated pose).
    # It is NOT bit-identical: it shifts rotations by up to 0.065 deg, against the 0.056 deg of
    # float32 key noise probe_shared_anims already tolerates. So a re-export is a gate pass, not a
    # no-op -- which is why the shipped .glb was deliberately NOT re-baked when this was flipped.
    export_def_bones=True,
    export_animations=True,
    export_animation_mode='ACTIONS',
    export_force_sampling=True,
    export_bake_animation=True,
    export_optimize_animation_size=False,
    export_anim_slide_to_zero=False,
    export_negative_frame='SLIDE',
)
if _filter_added:
    _gltf.on_export_action_filter_changed(_types.SimpleNamespace(export_action_filter=False), bpy.context)
_gather.generate_extras = _orig_generate_extras
if export_copy is not None:
    for ob in bpy.data.objects:
        for m in ob.modifiers:
            if m.type == 'ARMATURE' and m.object == export_copy:
                m.object = arm
        if ob.parent is export_copy:
            mw = ob.matrix_world.copy()
            ob.parent = arm
            ob.matrix_world = mw
    bpy.data.objects.remove(export_copy, do_unlink=True)
    arm.name = real_name
    arm.hide_viewport = arm.hide_render = False
if restore is not None:
    restore()
_switches_back()
print(f"[export_character] wrote {OUT} ({os.path.getsize(OUT)} bytes)")


# ---------------------------------------------------------------- the hand sockets, if an artist moved one
#
# blender/tools/game_weapon_preview.py puts one empty per hand socket (`SOCKET_Rifle`, ...) on `hand_r`
# exactly where the game hangs that grip archetype's weapon. Moving or turning one is the edit: each socket
# that no longer matches the body's MEASURED socket (`<body>.body.json`, measure_body.gd) is written to
# `<body>.sockets.json`, which build_character_visuals.gd applies on top. A socket put back where it was
# measured leaves the file; the file is removed when nothing differs.
def _socket_overrides():
    import json, math, re
    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    facts = os.path.join(os.path.dirname(bpy.data.filepath), stem + ".body.json")
    empties = [o for o in bpy.data.objects if o.type == 'EMPTY' and "game_socket" in o.keys()
               and o.parent is arm and o.parent_bone]
    if arm is None or not empties or not os.path.exists(facts):
        return
    measured = json.load(open(facts)).get("sockets", {})
    if "SocketShotgun" not in measured and "SocketRifle" in measured:
        measured["SocketShotgun"] = measured["SocketRifle"]

    def parse(t):
        v = [float(x) for x in re.search(r"\(([^)]*)\)", t).group(1).split(",")]
        from mathutils import Matrix
        return Matrix(((v[0], v[1], v[2], v[9]), (v[3], v[4], v[5], v[10]), (v[6], v[7], v[8], v[11]), (0, 0, 0, 1)))

    def fmt(m):
        return "Transform3D(%s)" % ", ".join("%.6f" % x for x in (
            m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2],
            m[0][3], m[1][3], m[2][3]))

    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for e in empties:
        name = e["game_socket"]
        bone = arm.evaluated_get(dg).pose.bones[e.parent_bone]
        s = (arm.matrix_world @ bone.matrix).inverted() @ e.evaluated_get(dg).matrix_world
        ref = parse(measured[name]) if name in measured else None
        if ref is not None:
            dp = (s.translation - ref.translation).length
            dr = math.degrees(s.to_quaternion().rotation_difference(ref.to_quaternion()).angle)
            if dp < 0.0005 and min(dr, 360 - dr) < 0.05:
                continue
        out[name] = fmt(s)
    path = os.path.join(os.path.dirname(bpy.data.filepath), stem + ".sockets.json")
    if out:
        json.dump({"note": "hand-socket overrides from the SOCKET_* empties in %s.blend (export_character.py); "
                           "applied over %s.body.json by build_character_visuals.gd" % (stem, stem),
                   "sockets": out}, open(path, "w"), indent=2)
        print(f"[export_character] socket overrides written: {', '.join(sorted(out))} -> {os.path.basename(path)}")
    elif os.path.exists(path):
        os.remove(path)
        print(f"[export_character] every socket is back on its measured value; removed {os.path.basename(path)}")


_socket_overrides()
print("[export_character] now run BOTH, in this order:")
print("  1. godot --headless --path . --import      <-- NOT OPTIONAL after a rename")
print("  2. python3 blender/tools/check_character_anim.py")
print("[export_character] Godot does NOT rescan imports on a `--headless --script` run, so without")
print("[export_character] step 1 every headless gate measures the PREVIOUS export: the AnimationTree")
print("[export_character] asks for the new clip names, the cached library still holds the old ones,")
print("[export_character] nothing resolves and the skeleton falls back to its REST pose. That reads")
print("[export_character] as a plausible failure (crawl's chest 129 deg -> 44) rather than as a stale")
print("[export_character] cache, and check_character_anim.py cannot see it -- it reads the .glb.")
