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
    return {b.name: ev[b.name].matrix.translation.copy() for b in a.pose.bones}


def neutralise(a):
    """Mute the deform armature's constraints and hide every other armature. Returns an undo."""
    muted = []
    for pb in a.pose.bones:
        for con in pb.constraints:
            if not con.mute:
                con.mute = True
                muted.append(con)
    hidden = []
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE' and ob is not a and not ob.hide_render:
            ob.hide_render = True
            hidden.append(ob)
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE' and ob is not a and not ob.hide_viewport:
            ob.hide_viewport = True
            if ob not in hidden:
                hidden.append(ob)

    def undo():
        for con in muted:
            con.mute = False
        for ob in hidden:
            ob.hide_render = False
            ob.hide_viewport = False
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
        raise SystemExit(
            f"[export_character] REFUSED: a live constraint is driving the deform armature "
            f"({worst!r} moves {moved:.4f} m when it is muted). The exporter samples the EVALUATED "
            f"pose, so that result would be baked into every clip. Switch the control rig off "
            f'(CTRL_root["ik"] = 0, or BAKE the pose down) and export again.')

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
if restore is not None:
    restore()
print(f"[export_character] wrote {OUT} ({os.path.getsize(OUT)} bytes)")
print("[export_character] now run BOTH, in this order:")
print("  1. godot --headless --path . --import      <-- NOT OPTIONAL after a rename")
print("  2. python3 blender/tools/check_character_anim.py")
print("[export_character] Godot does NOT rescan imports on a `--headless --script` run, so without")
print("[export_character] step 1 every headless gate measures the PREVIOUS export: the AnimationTree")
print("[export_character] asks for the new clip names, the cached library still holds the old ones,")
print("[export_character] nothing resolves and the skeleton falls back to its REST pose. That reads")
print("[export_character] as a plausible failure (crawl's chest 129 deg -> 44) rather than as a stale")
print("[export_character] cache, and check_character_anim.py cannot see it -- it reads the .glb.")
