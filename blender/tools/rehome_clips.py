"""Move the shared clip library from one body's .blend to another's (PLAN.md: Shino as the base).

    blender -b assets/characters/shino/shino.blend --python-exit-code 1 \
        --python blender/tools/rehome_clips.py -- \
        --from assets/characters/godot_chan/merged_animation.blend [--save]

A ONE-SHOT, like `import_melee_pack.py` and `add_control_rig.py`: it runs when the clip library
changes home, the result lives in the .blend, and nothing depends on it running again.

WHY A CLIP MOVES AT ALL, AND WHAT HAS TO CHANGE ON THE WAY
----------------------------------------------------------
W40's contract is that a clip is a fact about the SKELETON, not about a body: the rests of every
body are conformed to the reference's, so a clip's ROTATION channels mean the same thing on any of
them and transfer unchanged. What does NOT transfer is POSITION, because a position key is an
absolute offset in METRES:

  * `Root` and `pelvis` carry real motion -- the stance drop above all, `crawl_idle` taking Root to
    -0.601 m and `crouch_idle` to -0.289 -- and those metres belong to the body they were authored
    on. Moving the library to a body whose pelvis rests higher means scaling them by the same ratio
    `Skeleton3D.motion_scale` applies at runtime (W47), so that the new home's scale becomes 1.0.
  * EVERY OTHER BONE's position keys are dropped outright. They are constant-at-rest to within
    0.000036 m (W40 measured it) and `build_character_anims.gd` already drops them BY RULE at
    library build -- but they are still IN the .blend, in the old body's metres, so on the new rig
    they would override its own bone lengths and show a broken pose to the artist in Blender even
    though the exported library is fine. W43 is that defect seen from the other side: a kept
    clavicle key lifted the shoulder 9-13 cm on a body it was not authored on. Dropping them here
    makes the .blend agree with the library.

The ratio is derived from the two skeletons' own PELVIS RESTS, never typed: the stance drop is the
pelvis travelling from standing to prone, so it scales with the leg.
"""
import bpy
import os
import sys

TRANSLATING = ("Root", "pelvis")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def arg(name, default=None):
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


def flag(name):
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return name in a


def armature():
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        for m in ob.modifiers:
            if m.type == 'ARMATURE' and m.object is not None:
                return m.object
    return next(o for o in bpy.data.objects if o.type == 'ARMATURE')


def pelvis_rest_y(path):
    """The pelvis's rest height in a .blend, without opening it as the main file."""
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.armatures = [a for a in src.armatures]
    y = None
    for a in dst.armatures:
        b = a.bones.get("pelvis")
        if b is not None:
            y = b.head_local.z if abs(b.head_local.z) > abs(b.head_local.y) else b.head_local.y
            break
    for a in dst.armatures:
        bpy.data.armatures.remove(a)
    return y


def channelbag(action):
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            cb = strip.channelbag(action.slots[0]) if action.slots else None
            if cb is not None:
                return cb
    return None


def bone_of(data_path):
    if not data_path.startswith('pose.bones["'):
        return None
    return data_path.split('"')[1]


def main():
    src_blend = arg("--from")
    if not src_blend:
        raise SystemExit("rehome_clips: give --from <source .blend>")
    src_blend = src_blend if os.path.isabs(src_blend) else os.path.join(ROOT, src_blend)
    here = bpy.data.filepath
    arm = armature()

    # the scale, from the two skeletons' own pelvis rests
    src_pelvis = pelvis_rest_y(src_blend)
    my_pelvis = arm.data.bones["pelvis"].head_local.z if abs(arm.data.bones["pelvis"].head_local.z) > \
        abs(arm.data.bones["pelvis"].head_local.y) else arm.data.bones["pelvis"].head_local.y
    ratio = my_pelvis / src_pelvis
    print("[rehome] %s pelvis %.4f  <-  %s pelvis %.4f   ratio %.6f"
          % (os.path.basename(here), my_pelvis, os.path.basename(src_blend), src_pelvis, ratio))

    existing = {a.name for a in bpy.data.actions}
    with bpy.data.libraries.load(src_blend, link=False) as (src, dst):
        dst.actions = [a for a in src.actions if a not in existing]
    brought = [a for a in dst.actions if a is not None]
    print("[rehome] imported %d action(s) (%d already here were left alone)"
          % (len(brought), len(existing)))

    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    have_tracks = {t.name for t in ad.nla_tracks}

    scaled = dropped = tracks = 0
    for act in brought:
        cb = channelbag(act)
        if cb is None:
            print("[rehome]   %-34s no channelbag -- skipped" % act.name)
            continue
        doomed = []
        for fc in cb.fcurves:
            if ".location" not in fc.data_path:
                continue
            b = bone_of(fc.data_path)
            if b in TRANSLATING:
                for k in fc.keyframe_points:
                    k.co[1] *= ratio
                    k.handle_left[1] *= ratio
                    k.handle_right[1] *= ratio
                scaled += 1
            else:
                doomed.append(fc)
        for fc in doomed:
            cb.fcurves.remove(fc)
        dropped += len(doomed)
        # the export needs ONE named NLA track per clip and no active action
        if act.name not in have_tracks:
            trk = ad.nla_tracks.new()
            trk.name = act.name
            trk.strips.new(act.name, int(act.frame_range[0]), act)
            tracks += 1
    ad.action = None
    print("[rehome] scaled %d translating fcurve(s) by %.6f ; dropped %d other position fcurve(s)"
          % (scaled, ratio, dropped))
    print("[rehome] created %d NLA track(s)" % tracks)

    if flag("--save"):
        bpy.ops.wm.save_mainfile()
        print("[rehome] saved %s" % here)
    else:
        print("[rehome] DRY RUN -- pass --save to write")


main()
