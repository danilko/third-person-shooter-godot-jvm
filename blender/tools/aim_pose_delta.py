"""Apply a measured DELTA to an authored aim clip: lean the spine, or change the blade.

    blender -b <blend> --python-exit-code 1 --python blender/tools/aim_pose_delta.py -- \
        [--action upright_aim_rifle-loop] [--lean 8] [--blade -20] [--save]

A DELTA, not a solve: `pose_weapon_hold.py solve-aim` rebuilds the pose from its row's arguments and
would discard whatever the artist adopted (W25). This keeps every authored choice and changes one
thing, and it reports the measurement either side so the change is a number rather than an opinion.

--lean  degrees of FORWARD bend, shared equally by spine_01/02/03 about the body's lateral axis.
        Nothing is counter-rotated: the arms and the gun ride the chest, the aim modifiers re-point
        the bore in game, and what SURVIVES that is the POSITION -- the chest, shoulders and head
        move forward over the weapon. That is the whole point of a lean, and it is why it needs no
        compensation anywhere.

--blade degrees added to (negative: taken off) the shoulder line, applied by turning BOTH
        CLAVICLES about the body's vertical axis with the arms and the weapon riding along.

        **The lever is the arms' direction relative to the CHEST, not the chest's own rotation.**
        In game the aim modifiers turn the body until the BORE is on the target, so a chest rotation
        the arms ride along with is simply undone -- the in-game blade is a function of the clip's
        own chest-to-bore angle and nothing else. Turning the chest while restoring the CLAVICLES'
        world orientation does not work either, and W44 measured why: a clavicle's origin sits ~2 cm
        off the spine axis, so the shoulder barely moves and the shoulder line barely changes
        (asked for -33 deg, measured -4.8). Turning the clavicles themselves moves both the arms and
        the bore against the chest, which is the quantity that survives.

        It needs NO counter-rotation anywhere, and that is what makes it safe where W44's +8 deg was
        not: a clavicle rotation is the POSE, carried by `WeaponBlend` into every stance, rather
        than a compensation for a chest rotation that only Upright and Crouch receive
        (`WeaponTorsoBlend` is gated on `Stance.weaponTorsoLayer`).
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Vector

SPINE = ["spine_01", "spine_02", "spine_03"]
CLAVS = ["clavicle_l", "clavicle_r"]


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"action": "upright_aim_rifle-loop", "lean": 0.0, "blade": 0.0, "save": False}
    i = 0
    while i < len(a):
        if a[i] == "--action":
            out["action"] = a[i + 1]; i += 2
        elif a[i] == "--lean":
            out["lean"] = float(a[i + 1]); i += 2
        elif a[i] == "--blade":
            out["blade"] = float(a[i + 1]); i += 2
        elif a[i] == "--save":
            out["save"] = True; i += 1
        else:
            raise SystemExit("[aim-delta] unknown argument %r" % a[i])
    return out


def report(arm, tag):
    """Blade (shoulder line vs the chest's forward), and where the head sits over the gun hand."""
    pb = arm.pose.bones
    l, r = pb["upperarm_l"].head, pb["upperarm_r"].head
    # the rig rests facing -Y with the left arm at +X, so the shoulder line's yaw against -Y IS the
    # blade; measured in the armature's own frame, which the export does not change (W40)
    # The shoulder line runs left->right, i.e. along -X when square (the rig rests facing -Y with
    # the left arm at +X), and "bladed" means the RIGHT shoulder has gone BACK, which is +Y. So the
    # blade is the line's angle measured from -X toward +Y, and a square stance reads 0.
    d = (r - l)
    blade = math.degrees(math.atan2(d.y, -d.x))
    chest = pb["spine_03"].matrix.to_3x3() @ Vector((0.0, 1.0, 0.0))
    lean = math.degrees(math.asin(max(-1.0, min(1.0, -chest.y))))
    # In the .blend the head bone is `head`; Godot's importer renames it `head_2` because the
    # export also carries a MESH called `head` (W40). Ask for whichever this file has.
    head = pb["head" if "head" in pb else "head_2"].head
    hand = pb["hand_r"].head
    print("[aim-delta] %-9s blade %+6.1f deg | chest lean %+5.1f deg | head-to-gun-hand %.3f m "
          "(fwd %+.3f, up %+.3f)" % (tag, blade, lean, (head - hand).length,
                                     -(head - hand).y, (head - hand).z))
    return blade


def main():
    a = args()
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
    act = bpy.data.actions[a["action"]]
    bpy.context.view_layer.objects.active = arm
    arm.animation_data_create()
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    if arm.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
    print("[aim-delta] %s  %s  frames %d..%d  lean %+.1f  blade %+.1f"
          % (os.path.basename(bpy.data.filepath), a["action"], lo, hi, a["lean"], a["blade"]))
    bpy.context.scene.frame_set(lo)
    bpy.context.view_layer.update()
    report(arm, "before")

    # A forward bend tips the body's UP toward its FORWARD. The rig faces -Y with up +Z, so that is
    # a POSITIVE rotation about +X -- derived from the contract's rest, not assumed.
    lean = Matrix.Rotation(math.radians(a["lean"] / len(SPINE)), 3, 'X')
    # +Z takes +X (the rig's LEFT) toward +Y (back), i.e. it turns the left shoulder back and so
    # REDUCES a right-shoulder-back blade; a positive --blade must increase it, hence the sign.
    blade = Matrix.Rotation(math.radians(-a["blade"]), 3, 'Z')

    touched = set()
    for f in range(lo, hi + 1):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        if a["lean"]:
            for b in SPINE:
                pb = arm.pose.bones[b]
                m = pb.matrix.copy()
                pb.matrix = Matrix.Translation(m.translation) @ (lean @ m.to_3x3()).to_4x4()
                bpy.context.view_layer.update()
                touched.add(b)
        if a["blade"]:
            for c in CLAVS:                     # the arms and the weapon ride along
                pb = arm.pose.bones[c]
                m = pb.matrix.copy()
                pb.matrix = Matrix.Translation(m.translation) @ (blade @ m.to_3x3()).to_4x4()
                bpy.context.view_layer.update()
                touched.add(c)
        for b in touched:
            arm.pose.bones[b].keyframe_insert(data_path="rotation_quaternion", frame=f)

    bpy.context.scene.frame_set(lo)
    bpy.context.view_layer.update()
    report(arm, "after")
    arm.animation_data.action = None            # the export rule: no active action
    if a["save"]:
        bpy.ops.wm.save_mainfile()
        print("[aim-delta] saved %s" % bpy.data.filepath)
    else:
        print("[aim-delta] NOT saved (pass --save)")


main()
