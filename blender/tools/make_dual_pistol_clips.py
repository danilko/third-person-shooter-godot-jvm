"""Build the DUAL-PISTOL poses from the pistol ones: the right arm's pose X-flipped onto the left arm, so each
hand holds its own gun (CS's Dual Berettas / L4D's dual pistols). A one-shot in the import_melee_pack.py
contract: it writes game actions into the clip source (shino.blend) and nothing re-runs it.

    blender -b assets/characters/shino/shino.blend --python blender/tools/make_dual_pistol_clips.py -- [--save]

  upright_aim_dual_pistol-loop  <- upright_aim_pistol-loop
  crouch_aim_dual_pistol-loop   <- crouch_aim_pistol-loop
  crawl_aim_dual_pistol-loop    <- crawl_aim_pistol-loop
  upright_hold_dual_pistol-loop <- upright_hold_pistol-loop

THE PAIR IS SYMMETRIC IN THE WORLD, NOT IN THE CHEST (2026-10-10, user: "the dup sits toward one side, though the
copied animation should balance them"). The first version mirrored the right arm's LOCAL rotations onto the left
under the pistol pose's own spine. That spine is BLADED (a two-handed pistol stance turns the chest), so the pair was
symmetric about a turned chest: measured in Godot with the aim layers off, both barrels 4.8 deg to the right and the
guns 11.8 cm apart. The aim modifier then turned the upper body 4.8 deg back, which swung the narrow pair 5.6 cm to
the left: the right gun sat on the crosshair, the left gun 12 cm out (tools/godot/measure_gun_screen.gd). Now, per
frame:
  1. the BODY is symmetrized (every bone outside the two arm chains averaged with its partner's mirror, `Root`
     kept): the chest faces the way the body does and the stance is square (isosceles, the dual-wield stance);
  2. the RIGHT HAND keeps the pistol pose's height and reach, goes to HALF_SPAN to its own side of the midline,
     and is turned about the world vertical until the gun's bore (Shino's SocketPistol) points straight ahead;
     the arm reaches it by a two-bone solve that keeps the elbow on the side it was;
  3. the right arm chain is X-flipped onto the left (pose_weapon_hold.py's reflection; the rig is X-symmetric to
     0.0002), which on a symmetric body IS the world mirror.
The carry (hold) gets 1 and 3 and the hand moved out to HALF_SPAN, but no bore turn (a lowered gun has no aim).
Then each clip is moved back onto the rig in FK (arp_clips.move_to_arp, exact), so the rig and the export agree.
"""
import math
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, "/data/danilko/git/third-person-shooter/blender/tools")
import arp_clips as ac  # noqa: E402

CLIPS = {
    "upright_aim_dual_pistol-loop": "upright_aim_pistol-loop",
    "crouch_aim_dual_pistol-loop": "crouch_aim_pistol-loop",
    "crawl_aim_dual_pistol-loop": "crawl_aim_pistol-loop",
    "upright_hold_dual_pistol-loop": "upright_hold_pistol-loop",
}
HALF_SPAN = 0.12          # m: each hand this far to its own side of the midline (the guns ~24 cm apart)
MIRROR_S = Matrix(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))
UP = Vector((0, 0, 1))    # world
VISUALS = "/data/danilko/git/third-person-shooter/src/main/resources/com/openworld/character/CharacterVisuals_Shino.tscn"
AIMS = {"upright_aim_dual_pistol-loop", "crouch_aim_dual_pistol-loop", "crawl_aim_dual_pistol-loop"}

rig, game = ac.rigs()
B = game.data.bones


def mirror_name(n):
    return n[:-2] + "_l" if n.endswith("_r") else n[:-2] + "_r" if n.endswith("_l") else n


def _reflect(bone):
    src, dst = B[bone].matrix_local.to_3x3(), B[mirror_name(bone)].matrix_local.to_3x3()
    return src.inverted() @ MIRROR_S @ dst


def mirror_quat(bone, q):
    """The local rotation `mirror_name(bone)` needs to mirror `bone`'s local rotation `q` across the midplane."""
    A = _reflect(bone)
    return (A @ q.to_matrix() @ A.inverted()).to_quaternion()


def chain(root="clavicle_r"):
    out, todo = [], [B[root]]
    while todo:
        b = todo.pop()
        out.append(b.name)
        todo.extend(b.children)
    return out


def curves(act):
    return {(fc.data_path, fc.array_index): fc for fc in ac._fcurves(act)}


def set_key(cv, bone, idx, frame, value, prop="rotation_quaternion"):
    fc = cv.get(('pose.bones["%s"].%s' % (bone, prop), idx))
    if fc is None:
        return False
    for kp in fc.keyframe_points:
        if abs(kp.co[0] - frame) < 1e-3:
            kp.co[1] = kp.handle_left[1] = kp.handle_right[1] = value
    fc.update()
    return True


def socket():
    """SocketPistol in hand_r's bone frame (the glTF keeps bone frames, so Godot's is Blender's)."""
    import re
    m = re.search(r'\[node name="SocketPistol"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', open(VISUALS).read())
    v = [float(x) for x in m.group(1).split(",")]
    M = Matrix.Identity(4)
    for r in range(3):
        for c in range(3):
            M[r][c] = v[r * 3 + c]
    M[0][3], M[1][3], M[2][3] = v[9], v[10], v[11]
    return M


SOCKET = socket()


def W(name):
    return game.matrix_world @ game.pose.bones[name].matrix


def set_W(name, M):
    game.pose.bones[name].matrix = game.matrix_world.inverted() @ M
    bpy.context.view_layer.update()


def turn_about_head(name, R3):
    """Pre-multiply a bone's WORLD rotation by R3 (3x3), pivoting on its head."""
    M = W(name)
    h = M.translation
    set_W(name, Matrix.Translation(h) @ R3.to_4x4() @ Matrix.Translation(-h) @ M)


def point_at(name, target):
    """Swing a bone (the smallest rotation, so its roll is kept) until its +Y axis points at `target`."""
    M = W(name)
    y = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    turn_about_head(name, y.rotation_difference((target - M.translation).normalized()).to_matrix())


def bore_yaw():
    """The right gun's bore yaw off the body's forward (world -Y), + = toward the character's right (-X)."""
    d = (W("hand_r").to_3x3().normalized() @ SOCKET.to_3x3() @ Vector((0, 0, -1))).normalized()
    return math.atan2(-d.x, -d.y)


def two_bone(target, pole):
    S = W("upperarm_r").translation
    a = (W("lowerarm_r").translation - S).length
    b = (W("hand_r").translation - W("lowerarm_r").translation).length
    to = target - S
    d = min(to.length, (a + b) * 0.999)
    u = to.normalized()
    v = (pole - S) - u * (pole - S).dot(u)
    v = v.normalized() if v.length > 1e-6 else Vector((0, 0, -1))
    ca = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
    elbow = S + u * (a * ca) + v * (a * math.sqrt(1 - ca * ca))
    point_at("upperarm_r", elbow)
    point_at("lowerarm_r", S + u * d)


def main():
    save = "--save" in sys.argv
    ac._drive(rig, 0)
    arms = chain("clavicle_r") + chain("clavicle_l")
    body = [b.name for b in B if b.name not in arms and b.parent is not None]   # `Root` keeps its keys
    right = chain("clavicle_r")
    for src in set(CLIPS.values()):          # the pistol sources as the rig has them now
        ac.bake_to_game(src)
    track_like = next(t for t in game.animation_data.nla_tracks if t.strips and t.strips[0].action.name == "upright_aim_pistol-loop")
    for dst, src in CLIPS.items():
        old = bpy.data.actions.get(dst)
        if old is not None:
            for t in list(game.animation_data.nla_tracks):
                if t.name == dst:
                    game.animation_data.nla_tracks.remove(t)
            bpy.data.actions.remove(old)
        a = bpy.data.actions[src].copy()
        a.name = dst
        a.use_fake_user = False
        cv = curves(a)
        frames = sorted({round(k.co[0], 3) for fc in cv.values() for k in fc.keyframe_points})
        ac._bind(game, a)
        missing = set()
        for f in frames:
            bpy.context.scene.frame_set(int(f)); ac._drive(rig, 0)
            pb = game.pose.bones
            hand0 = W("hand_r")                       # the pistol pose's right hand, before anything moves
            elbow0 = W("lowerarm_r").translation.copy()
            yaw0 = bore_yaw()
            # 1. the body symmetric: each bone averaged with its partner's mirror (read before any is written)
            q0 = {n: pb[n].rotation_quaternion.copy() for n in body}
            l0 = {n: pb[n].location.copy() for n in body}
            for n in body:
                m = mirror_name(n)
                if m not in q0:
                    continue
                mq = mirror_quat(m, q0[m])
                q = q0[n].slerp(mq if mq.dot(q0[n]) >= 0 else -mq, 0.5).normalized()
                pb[n].rotation_quaternion = q
                pb[n].location = (l0[n] + _reflect(m) @ l0[m]) * 0.5
            bpy.context.view_layer.update()
            mid = W("spine_03").translation
            # 2. the right hand out to its side, the bore straight ahead (aims only), the arm solved to it
            target = hand0.translation.copy()
            target.x = mid.x - HALF_SPAN               # the character's RIGHT is -X (it faces -Y)
            rot = hand0.to_3x3().normalized()
            if dst in AIMS:
                rot = Matrix.Rotation(yaw0, 3, UP) @ rot   # + yaw is toward -X; turning about +Z by +yaw undoes it
            two_bone(target, elbow0)
            cur = W("hand_r").to_3x3().normalized()
            turn_about_head("hand_r", rot @ cur.inverted())
            # 3. key the body and the right chain, then X-flip the right chain onto the left
            for n in body:
                for i in range(4):
                    if not set_key(cv, n, i, f, pb[n].rotation_quaternion[i]):
                        missing.add(n)
                if n == "pelvis":
                    for i in range(3):
                        set_key(cv, n, i, f, pb[n].location[i], "location")
            for n in right:
                q = pb[n].rotation_quaternion.copy()
                ml = mirror_quat(n, q)
                for i in range(4):
                    set_key(cv, n, i, f, q[i])
                    set_key(cv, mirror_name(n), i, f, ml[i])
        t = game.animation_data.nla_tracks.new()
        t.name = dst
        s = t.strips.new(dst, int(frames[0]), a)
        s.extrapolation, s.blend_type = track_like.strips[0].extrapolation, track_like.strips[0].blend_type
        t.mute = track_like.mute
        # measure, at the first frame, from the keys just written
        bpy.context.scene.frame_set(int(frames[0])); ac._drive(rig, 0)
        sp = W("spine_03").translation
        hr, hl = W("hand_r").translation, W("hand_l").translation
        mirr = (Vector((sp.x - hr.x, hr.y, hr.z)) - Vector((hl.x - sp.x, hl.y, hl.z))).length
        print("[dual] %-30s from %-26s hands %+.3f / %+.3f m off the spine (right / left), mirror error %.4f m, "
              "right bore yaw %+.2f deg (was %+.2f in the source)%s"
              % (dst, src, sp.x - hr.x, hl.x - sp.x, mirr, math.degrees(bore_yaw()), math.degrees(yaw0),
                 ", %d body bones without game keys (hair, secondary)" % len(missing) if missing else ""))
    game.animation_data.action = None
    for dst in CLIPS:                             # back onto the rig, in FK (exact): the export bakes from there
        ac.move_to_arp(dst)
        print("[dual] %s on the rig" % dst)
    ac._drive(rig, 1)
    if save:
        bpy.ops.wm.save_mainfile()
        print("[dual] saved")


main()
