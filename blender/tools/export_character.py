"""Export the character rig + animations to the .glb the game actually loads.

    blender -b assets/characters/godot_chan/merged_animation.blend --python blender/tools/export_character.py

`assets/characters/godot_chan/merged_animation.tscn` instances `assets/characters/godot_chan/merged_animation.glb`, NOT the .blend — so a
.blend edit is invisible to the game until this runs. Settings below are the ones the shipped
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

arm = bpy.data.objects.get("Godot_Chan_Stealth")
if arm is not None and arm.animation_data is not None and arm.animation_data.action is not None:
    print(f"[export_character] clearing active action {arm.animation_data.action.name!r} "
          f"(it would export a second time)")
    arm.animation_data.action = None

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
