"""Reset a clip whose COLLARBONE is turned further than a shoulder turns, keeping the hand put.

    blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \
        --python blender/tools/fix_shoulder_overbend.py -- [--limit 60] [--dry-run] [--save]

A ONE-SHOT, like `add_control_rig.py` and `import_melee_pack.py`: it runs when a clip needs
resetting, the result is committed inside the `.blend`, and nothing depends on it running again.
The permanent eye is `check_character_anim.py`'s `shoulder_overbend`, which fails the export when a
clip comes back over the limit -- including one an artist has just hand-posed.

WHAT IT FIXES, and it is the same defect six times. W34 retargeted the melee and throw attacks
ARMS-ONLY: every bone below the clavicles holds `upright_idle`'s first frame while the arms keep the
source's WORLD directions, because the `Attack` one-shot plays over a chest the aim modifiers have
squared to the target. That is right for the arms and it leaves the COLLARBONE to absorb the whole
difference between the source's torso and our held one. Measured on the shipped clips, the
clavicle's own channel reaches:

    attack_slash_mw1 / attack_swing_mw2   159 deg left, 171 right
    attack_chop_mw2                       126 / 122
    attack_throw                          110 / 110
    attack_jab_fist                        73 /  62
    attack_cross_fist / attack_stab_mw1    43 /  51

against at most 35 deg in every aim, hold, idle, locomotion and reload pose in the library. And it
SHIPS: `clavicle_l` and `clavicle_r` are both in the `Attack` one-shot's filter, so every melee
swing in the game plays it.

THE FIX KEEPS THE HAND AND MOVES ONLY THE SHOULDER. The clavicle's channel is scaled back along its
own axis until it is at the limit -- a continuous function of the input, so a clip does not step
where the fix starts, and frames already inside the limit are not touched at all -- and the arm is
then re-solved with two-bone IK so the WRIST returns to where the swing had it, with the hand's own
world orientation restored on top. So the swing still reads: the weapon travels the same path, held
by a shoulder that can hold it.

It is a CLAMP and an explicit solve rather than a pass of Blender's IK solver (which
`add_control_rig.py` now limits the same way). The solver re-solves a chain from REST, so it would
also move frames that were already fine and could flip the elbow plane between frames; this touches
only what is over the limit and cannot flip anything.
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_control_rig as crig          # noqa: E402  (CLAV_LIMIT_DEG, clavicle_deg -- one owner)

SIDES = [("clavicle_l", "upperarm_l", "lowerarm_l", "hand_l"),
         ("clavicle_r", "upperarm_r", "lowerarm_r", "hand_r")]
EPS = 1e-5


def log(m):
    print("[shoulder] %s" % m)


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"limit": crig.CLAV_LIMIT_DEG, "save": False, "dry": False, "only": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--save":
            out["save"] = True; i += 1
        elif a == "--dry-run":
            out["dry"] = True; i += 1
        elif a == "--limit":
            out["limit"] = float(argv[i + 1]); i += 2
        elif a.startswith("--limit="):
            out["limit"] = float(a.split("=", 1)[1]); i += 1
        elif a.startswith("--only="):
            out["only"] = a.split("=", 1)[1].split(","); i += 1
        else:
            raise SystemExit("[shoulder] unknown argument %r" % a)
    return out


def channel_deg(pb):
    """The bone's own rotation from rest, degrees. No constraint is running here, so the pose
    channel IS the answer (`add_control_rig.clavicle_deg` is the evaluated-pose twin, for when one
    is)."""
    q = pb.matrix_basis.to_quaternion()
    return math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))


def clamp_channel(pb, limit_deg):
    """Scale the bone's own rotation back to `limit_deg` about its own axis. Returns the angle it
    had. The axis is kept, so the shoulder still leans the way the animator leaned it."""
    q = pb.matrix_basis.to_quaternion().normalized()
    if q.w < 0.0:
        q = Quaternion((-q.w, -q.x, -q.y, -q.z))    # the short arc, or `angle` reads the long one
    ang = q.angle
    if math.degrees(ang) <= limit_deg + 1e-6:
        return math.degrees(ang), False
    axis = q.axis
    if axis.length < EPS:
        return math.degrees(ang), False
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = Quaternion(axis.normalized(), math.radians(limit_deg))
    return math.degrees(ang), True


def head(arm, name):
    return (arm.matrix_world @ arm.pose.bones[name].matrix).translation.copy()


def tail(arm, name):
    pb = arm.pose.bones[name]
    return (arm.matrix_world @ pb.matrix @ Vector((0.0, pb.bone.length, 0.0)))


def direction(arm, name):
    return (arm.matrix_world @ arm.pose.bones[name].matrix).col[1].xyz.normalized()


def aim_bone(arm, name, want_dir):
    """Turn a bone so its own +Y points along `want_dir`, keeping its twist about that axis."""
    pb = arm.pose.bones[name]
    m = (arm.matrix_world @ pb.matrix).copy()
    cur = m.col[1].xyz.normalized()
    w = want_dir.normalized()
    if cur.dot(w) > 1.0 - 1e-9:
        return
    R = cur.rotation_difference(w).to_matrix()
    out = Matrix.Translation(m.translation) @ (R @ m.to_3x3()).to_4x4()
    pb.matrix = arm.matrix_world.inverted() @ out
    bpy.context.view_layer.update()


def two_bone(arm, upper, lower, target, plane_normal):
    """Put `lower`'s tail on `target` by turning `upper` and `lower` only, in the given bend plane.

    Law of cosines, the same solve `character.TwoBoneIK` runs in game: a target past the arm's reach
    straightens it rather than stretching it, and the shortfall is what the caller reports.
    """
    S = head(arm, upper)
    L1 = (head(arm, lower) - S).length
    L2 = arm.pose.bones[lower].bone.length
    to = target - S
    d = to.length
    if d < EPS or L1 < EPS or L2 < EPS:
        return (tail(arm, lower) - target).length
    reach = min(max(d, abs(L1 - L2) + EPS), L1 + L2 - EPS)
    cosA = (L1 * L1 + reach * reach - L2 * L2) / (2.0 * L1 * reach)
    A = math.acos(max(-1.0, min(1.0, cosA)))
    base = to.normalized()
    n = plane_normal
    if n.length < EPS:
        n = base.cross(Vector((0.0, 0.0, 1.0)))
        if n.length < EPS:
            n = base.cross(Vector((1.0, 0.0, 0.0)))
    n = n.normalized()
    upper_dir = Matrix.Rotation(A, 4, n).to_3x3() @ base
    aim_bone(arm, upper, upper_dir)
    aim_bone(arm, lower, (target - head(arm, lower)).normalized())
    return (tail(arm, lower) - target).length


def bind(arm, act):
    arm.animation_data_create()
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]


def main():
    a = args()
    arm = crig.find_armature(crig.ARM_DEFAULT)
    bpy.context.view_layer.objects.active = arm
    if arm.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    limit = a["limit"]
    log("%s: limit %.0f deg%s" % (os.path.basename(bpy.data.filepath), limit,
                                  "  (DRY RUN, nothing written)" if a["dry"] else ""))

    names = a["only"] or [act.name for act in bpy.data.actions]
    touched = []
    for name in sorted(names):
        act = bpy.data.actions.get(name)
        if act is None:
            continue
        if not all(b in arm.pose.bones for side in SIDES for b in side):
            raise SystemExit("[shoulder] this rig has no clavicle/arm chain -- is it a contract rig?")
        lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
        bind(arm, act)
        # ── pass 1: does this clip go over at all? ──────────────────────────────────────────
        over = {s[0]: 0.0 for s in SIDES}
        for f in range(lo, hi + 1):
            bpy.context.scene.frame_set(f)
            bpy.context.view_layer.update()
            for clav, _, _, _ in SIDES:
                over[clav] = max(over[clav], channel_deg(arm.pose.bones[clav]))
        bad = [c for c, v in over.items() if v > limit + 0.5]
        if not bad:
            continue
        log("%-24s over: %s" % (name, ", ".join("%s %.1f deg" % (c, over[c]) for c in bad)))
        if a["dry"]:
            touched.append(name)
            continue

        # ── pass 2: clamp the shoulder, put the wrist back ──────────────────────────────────
        worst_miss, fixed_frames = 0.0, 0
        after = {c: 0.0 for c in bad}
        for f in range(lo, hi + 1):
            bpy.context.scene.frame_set(f)
            bpy.context.view_layer.update()
            for clav, upper, lower, hand in SIDES:
                if clav not in bad:
                    continue
                want_wrist = tail(arm, lower)
                hand_world = (arm.matrix_world @ arm.pose.bones[hand].matrix).copy()
                # the bend plane the animator posed, kept so the elbow does not flip sides
                normal = (head(arm, lower) - head(arm, upper)).cross(want_wrist - head(arm, upper))
                was, changed = clamp_channel(arm.pose.bones[clav], limit)
                if not changed:
                    after[clav] = max(after[clav], was)
                    continue
                bpy.context.view_layer.update()
                miss = two_bone(arm, upper, lower, want_wrist, normal)
                # the hand's own orientation is not the arm's business: restore it exactly
                arm.pose.bones[hand].matrix = arm.matrix_world.inverted() @ hand_world
                bpy.context.view_layer.update()
                worst_miss = max(worst_miss, miss)
                fixed_frames += 1
                after[clav] = max(after[clav], channel_deg(arm.pose.bones[clav]))
                for b in (clav, upper, lower, hand):
                    arm.pose.bones[b].keyframe_insert(data_path="rotation_quaternion", frame=f)
        log("%-24s -> %s ; %d frames re-solved, worst wrist %.4f m"
            % ("", ", ".join("%s %.1f deg" % (c, after[c]) for c in bad), fixed_frames, worst_miss))
        touched.append(name)

    arm.animation_data.action = None          # the export rule: no active action
    bpy.context.scene.frame_set(int(bpy.context.scene.frame_start))
    log("%d clip(s) %s: %s" % (len(touched), "would change" if a["dry"] else "changed",
                               ", ".join(touched) or "none"))
    if a["save"] and not a["dry"]:
        bpy.ops.wm.save_mainfile()
        log("saved %s" % bpy.data.filepath)
    elif not a["dry"]:
        log("NOT saved (pass --save)")


main()
