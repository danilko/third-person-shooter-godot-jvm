"""Build the DUAL-PISTOL poses from the pistol ones: the right arm's pose X-flipped onto the left arm, so each
hand holds its own gun (CS's Dual Berettas / L4D's dual pistols). A one-shot in the import_melee_pack.py
contract: it writes game actions into the clip source (shino.blend) and nothing re-runs it.

    blender -b assets/characters/shino/shino.blend --python blender/tools/make_dual_pistol_clips.py -- [--save]

  upright_aim_dual_pistol-loop  <- upright_aim_pistol-loop
  crouch_aim_dual_pistol-loop   <- crouch_aim_pistol-loop
  crawl_aim_dual_pistol-loop    <- crawl_aim_pistol-loop
  upright_hold_dual_pistol-loop <- upright_hold_pistol-loop

Only the arm CHAIN moves: every bone from clavicle_r down (arm, hand, fingers) is mirrored onto its _l twin
with pose_weapon_hold.py's own reflection (the rig is X-symmetric to 0.0002); the spine, head and legs keep
the pistol pose. The pistol AIM already holds the right hand in front of its own shoulder (8 cm off the spine,
the shoulder at 10.5), so the two guns land ~16 cm apart. The relaxed carry crosses the right hand over to the
left, so there the upper arm is first swung out about its own shoulder (world vertical) until the hand is
MIN_OFF off the midline, the hand keeping its world orientation.
"""
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
MIN_OFF = 0.07            # m: each hand at least this far to its own side of the spine
MIRROR_S = Matrix(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))

rig, game = ac.rigs()
B = game.data.bones


def mirror_name(n):
    return n[:-2] + "_l" if n.endswith("_r") else n


def mirror_quat(bone, q):
    src, dst = B[bone].matrix_local.to_3x3(), B[mirror_name(bone)].matrix_local.to_3x3()
    A = src.inverted() @ MIRROR_S @ dst
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


def main():
    save = "--save" in sys.argv
    ac._drive(rig, 0)
    arm = chain()
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
        swung = 0.0
        for f in frames:
            bpy.context.scene.frame_set(int(f)); ac._drive(rig, 0)
            pb = game.pose.bones
            sp = game.matrix_world @ pb["spine_03"].matrix.translation
            hand = game.matrix_world @ pb["hand_r"].matrix.translation
            off = sp.x - hand.x                      # the character's RIGHT is -X (it faces -Y)
            if off < MIN_OFF:                        # swing the upper arm out about the world vertical
                head = pb["upperarm_r"].matrix.translation
                hand_rot = pb["hand_r"].matrix.to_3x3().copy()
                reach = max(0.05, Vector((hand.x - sp.x, hand.y - sp.y)).length)
                ang = min(0.9, (MIN_OFF - off) / reach)
                # toward the character's right (-X): a hand in front (-Y) of its shoulder goes to -X under a
                # NEGATIVE rotation about +Z ((0, -r) -> (-r sin a, -r cos a))
                R = Matrix.Translation(head) @ Matrix.Rotation(-ang, 4, 'Z') @ Matrix.Translation(-head)
                pb["upperarm_r"].matrix = R @ pb["upperarm_r"].matrix
                bpy.context.view_layer.update()
                m = pb["hand_r"].matrix.copy()
                pb["hand_r"].matrix = Matrix.Translation(m.translation) @ hand_rot.to_4x4()
                bpy.context.view_layer.update()
                for n in ("upperarm_r", "hand_r"):
                    for i in range(4):
                        set_key(cv, n, i, f, pb[n].rotation_quaternion[i])
                swung = max(swung, ang)
            # the right arm chain's basis, read back from the (possibly swung) pose, mirrored onto the left
            for n in arm:
                q = mirror_quat(n, pb[n].rotation_quaternion.copy())
                for i in range(4):
                    set_key(cv, mirror_name(n), i, f, q[i])
        t = game.animation_data.nla_tracks.new()
        t.name = dst
        s = t.strips.new(dst, int(frames[0]), a)
        s.extrapolation, s.blend_type = track_like.strips[0].extrapolation, track_like.strips[0].blend_type
        t.mute = track_like.mute
        # measure
        bpy.context.scene.frame_set(int(frames[0])); ac._drive(rig, 0)
        pb = game.pose.bones
        P = lambda b: game.matrix_world @ pb[b].matrix.translation
        sp = P("spine_03")
        print("[dual] %-30s from %-26s hands %+.3f / %+.3f m off the spine (right / left), mirror error %.4f m, arm swung %.1f deg"
              % (dst, src, sp.x - P("hand_r").x, P("hand_l").x - sp.x,
                 (Vector((sp.x - P("hand_r").x, P("hand_r").y, P("hand_r").z)) - Vector((P("hand_l").x - sp.x, P("hand_l").y, P("hand_l").z))).length,
                 swung * 57.2958))
    game.animation_data.action = None
    ac._drive(rig, 1)
    if save:
        bpy.ops.wm.save_mainfile()
        print("[dual] saved")


main()
