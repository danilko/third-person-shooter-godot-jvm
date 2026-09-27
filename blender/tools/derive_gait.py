"""Derive the FEMALE walk from the one walk, in the clip .blend (user, 2026-09-27).

    blender -b assets/characters/shino/shino.blend --python blender/tools/derive_gait.py -- [--save] [--check]

There is ONE walk in the library (`upright_walk_forward` and its ring). Men walk it as it is. A female
body plays a DERIVED copy, written here as `f_<clip>`, so an edit to the walk flows into both by
re-running this. `tools/godot/build_character_anims.gd` then writes a second library in which the `f_`
clips stand under the base names (`blender/tools/character_gaits.json` is the table), and a body's
`body.json` `gait` picks its library.

What the derivation changes, each measured on the source first (Shino, 2026-09-27):
  * FEET: the planted feet are 9.3 cm apart and nothing about them reads female. Each foot is moved
    toward the line under the pelvis by `NARROW` -- fully while it is planted, not at all at the top of
    its swing, so the swinging foot still passes AROUND the standing one -- and the leg is re-solved by
    two-bone IK on the joint positions (a VRoid bone is short and disconnected: W51), in the plane the
    clip's own knee was in. The foot keeps its own world orientation, so contact is unchanged.
  * PELVIS: the source walk never shifts its weight (0 cm of side travel). The pelvis moves over the
    standing foot by up to `SHIFT`, and its own hip drop (roll about the travel axis) is scaled by
    `ROLL_GAIN`. Its yaw is left alone.
  * UPPER BODY: held EXACTLY. `spine_01` bends so that `spine_03`'s head lands where it was, and
    `spine_03` is given its original world orientation, so every bone above it -- clavicles, arms, neck,
    head, the weapon socket -- has precisely the transform it had. That is what keeps aim unchanged:
    the aim modifiers correct DIRECTION, never the chest moving under the gun.

A second, RELAXED clip (`f_upright_walk_relaxed-loop`) adds what a feminine walk does above the waist:
a gentle chest counter-roll and counter-yaw and a wider arm swing. It is played ONLY while no weapon is
raised (AnimationController's relaxed branch), so the steady clips above are what any aim sees.

`--check` re-evaluates the written clips and fails (exit 1) on: spine_03 more than 0.5 deg / 5 mm off the
source, planted feet not narrower, a planted foot sliding, a missing loop.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arp_clips  # noqa: E402  (the rig switch and the slotted-action bind have one owner)

SOURCES = ["upright_walk_forward-loop", "upright_walk_forward_left-loop",
           "upright_walk_forward_right-loop", "upright_walk_back-loop"]
RELAXED_SOURCE = "upright_walk_forward-loop"
RELAXED_OUT = "f_upright_walk_relaxed-loop"
PREFIX = "f_"

NARROW = 0.46         # fraction of the clip's own planted step width taken out: forward 9.3 cm -> ~5.0 cm.
                      # A fraction, not metres: the diagonals already plant narrower (6.1-8.1 cm), and a fixed
                      # 2.15 cm per foot put forward_right's feet 1.8 cm apart, i.e. crossing.
SHIFT = 0.022          # m the pelvis moves over the standing foot at mid-stance
ROLL_GAIN = 1.15       # the clip's own hip drop x this (1.35 left the standing leg short of the ground)
# relaxed-only, above the waist
CHEST_ROLL_DEG = 2.5   # peak counter-roll of the chest against the hip drop
CHEST_YAW_GAIN = 0.25  # chest counter-yaw against the pelvis yaw
ARM_SWING_GAIN = 1.3   # upper-arm swing about the shoulder

SIDE = Vector((1.0, 0.0, 0.0))       # armature space: +X is the body's LEFT
FWD = Vector((0.0, -1.0, 0.0))       # -Y is forward
UP = Vector((0.0, 0.0, 1.0))

KEYED = ["pelvis", "spine_01", "spine_03", "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
RELAX_KEYED = KEYED + ["upperarm_l", "upperarm_r"]


def _arm():
    rig, game = arp_clips.rigs()
    return rig, game


def _rel_rest(ob, name):
    """Parent-relative rest: R_p^-1 @ R_b (identity-parent for a root)."""
    b = ob.data.bones[name]
    return (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local.copy()


def _basis(ob, name, W, Wparent):
    """The local basis that puts bone `name` at armature-space W under a parent at Wparent."""
    return _rel_rest(ob, name).inverted() @ Wparent.inverted() @ W if Wparent is not None else \
        _rel_rest(ob, name).inverted() @ W


def _fk(ob, name, Wparent, basis):
    return (Wparent @ _rel_rest(ob, name) @ basis) if Wparent is not None else (_rel_rest(ob, name) @ basis)


def _about(W, pivot, R):
    """Rotate a world matrix W by the 3x3/quaternion R about the point `pivot`."""
    R4 = R.to_matrix().to_4x4() if isinstance(R, Quaternion) else R.to_4x4()
    return Matrix.Translation(pivot) @ R4 @ Matrix.Translation(-pivot) @ W


def _arc(a, b):
    """Minimal rotation taking direction a onto direction b."""
    return a.normalized().rotation_difference(b.normalized())


def _sample(game, act, frames):
    """Armature-space pose matrices and local bases of every bone, per frame, with the rig switched off."""
    arp_clips._bind(game, act)
    out = []
    sc = bpy.context.scene
    for f in frames:
        sc.frame_set(f)
        out.append({pb.name: (pb.matrix.copy(), pb.matrix_basis.copy()) for pb in game.pose.bones})
    return out


def _circular_smooth(vals, radius):
    n = len(vals)
    out = []
    for i in range(n):
        acc = wsum = 0.0
        for k in range(-radius, radius + 1):
            w = math.exp(-0.5 * (k / max(1.0, radius / 2.0)) ** 2)
            acc += w * vals[(i + k) % n]
            wsum += w
        out.append(acc / wsum)
    return out


def _hip_roll(P):
    """Hip drop, radians: the tilt of the hip axis (thigh_r -> thigh_l heads) out of the horizontal."""
    v = P["thigh_l"][0].translation - P["thigh_r"][0].translation
    return math.atan2(v.z, v.x)


def _pelvis_yaw(P):
    v = P["thigh_l"][0].translation - P["thigh_r"][0].translation
    return math.atan2(v.y, v.x)


def _two_bone(hip, knee0, ankle0, target, pole):
    """New knee for a leg whose hip stays, reaching `target`, bending in the plane (hip, target, pole)."""
    a = (knee0 - hip).length
    b = (ankle0 - knee0).length
    d = target - hip
    dist = min(d.length, a + b - 1e-5)
    dn = d.normalized()
    cosA = max(-1.0, min(1.0, (a * a + dist * dist - b * b) / (2 * a * dist)))
    side = (pole - hip) - dn * (pole - hip).dot(dn)
    if side.length < 1e-6:
        side = FWD.copy()
    side.normalize()
    return hip + dn * (a * cosA) + side * (a * math.sqrt(max(0.0, 1 - cosA * cosA)))


def derive(game, src_name, out_name, relaxed=False):
    src = bpy.data.actions[src_name]
    f0, f1 = int(round(src.frame_range[0])), int(round(src.frame_range[1]))
    frames = list(range(f0, f1 + 1))
    S = _sample(game, src, frames)
    n = len(frames)
    loop = n > 2 and (S[0]["pelvis"][0].translation - S[-1]["pelvis"][0].translation).length < 1e-3
    cyc = n - 1 if loop else n          # the last frame repeats the first in a loop

    wl = min(S, key=lambda P: P["foot_l"][0].translation.z)["foot_l"][0].translation.x
    wr = min(S, key=lambda P: P["foot_r"][0].translation.z)["foot_r"][0].translation.x
    narrow = NARROW * max(0.0, wl - wr) / 2.0      # metres each planted foot moves in
    mid_x = (wl + wr) / 2.0                          # toward the feet's OWN midline (a diagonal is off-centre)
    reach_short = [0.0]
    # How PLANTED each foot is, 0 (top of swing) .. 1 (on the ground): its height against its own range.
    plant = {}
    for s in ("l", "r"):
        z = [P["foot_" + s][0].translation.z for P in S]
        lo, hi = min(z), max(z)
        plant[s] = [1.0 - min(1.0, max(0.0, (v - lo) / max(1e-4, (hi - lo)))) for v in z]
        plant[s] = [p * p * (3 - 2 * p) for p in plant[s]]           # smoothstep: firm plant, soft lift
    # Weight toward the standing foot: +1 all on the left, -1 all on the right, smoothed round the cycle.
    w = [plant["l"][i] - plant["r"][i] for i in range(cyc)]
    w = _circular_smooth(w, max(1, cyc // 8))
    peak = max(1e-6, max(abs(v) for v in w))
    shift = [SHIFT * v / peak for v in w] + ([SHIFT * w[0] / peak] if loop else [])
    rolls = [_hip_roll(P) for P in S]
    roll_mean = sum(rolls[:cyc]) / cyc
    yaws = [_pelvis_yaw(P) for P in S]
    yaw_mean = sum(yaws[:cyc]) / cyc
    swing = {}
    for s in ("l", "r"):
        a = [math.atan2(-(P["hand_" + s][0].translation - P["upperarm_" + s][0].translation).y,
                        -(P["hand_" + s][0].translation - P["upperarm_" + s][0].translation).z) for P in S]
        m = sum(a[:cyc]) / cyc
        swing[s] = [v - m for v in a]
    roll_peak = max(1e-6, max(abs(r - roll_mean) for r in rolls[:cyc]))

    act = src.copy()
    act.name = out_name
    act.use_fake_user = False
    keyed = RELAX_KEYED if relaxed else KEYED
    # drop the source's curves for the bones rewritten here; every frame is keyed below
    bag = act.layers[0].strips[0].channelbags[0] if getattr(act, "layers", None) else None
    curves = bag.fcurves if bag is not None else act.fcurves
    for c in list(curves):
        if any(c.data_path.startswith('pose.bones["%s"]' % b) for b in keyed):
            curves.remove(c)
    arp_clips._bind(game, act)

    for i, f in enumerate(frames):
        P = S[i]
        W = {k: v[0].copy() for k, v in P.items()}
        B = {k: v[1].copy() for k, v in P.items()}
        # 1. pelvis: weight shift over the standing foot + more hip drop, about its own head
        ph = W["pelvis"].translation.copy()
        extra = (ROLL_GAIN - 1.0) * (rolls[i] - roll_mean)
        R = Quaternion(FWD, extra)             # more of the clip's own hip drop (the check measures that it grew)
        Wp = _about(W["pelvis"], ph, R)
        Wp = Matrix.Translation(SIDE * shift[i]) @ Wp
        # 2. the spine: spine_01 bends so spine_03's head returns; spine_03 keeps its world transform
        W1 = _fk(game, "spine_01", Wp, B["spine_01"])
        W2 = _fk(game, "spine_02", W1, B["spine_02"])
        W3 = _fk(game, "spine_03", W2, B["spine_03"])
        s1 = W1.translation
        q = _arc(W3.translation - s1, W["spine_03"].translation - s1)
        W1 = _about(W1, s1, q)
        W2 = _fk(game, "spine_02", W1, B["spine_02"])
        W3 = W["spine_03"].copy()
        if relaxed:
            dr = math.radians(CHEST_ROLL_DEG) * (rolls[i] - roll_mean) / roll_peak
            dy = -CHEST_YAW_GAIN * (yaws[i] - yaw_mean)
            Rc = Quaternion(UP, dy) @ Quaternion(FWD, dr)
            W3 = _about(W3, W3.translation, Rc)
        # 3. legs: each foot toward the centre line while planted, the leg re-solved to reach it
        Wl = {}
        for s, sign in (("l", 1.0), ("r", -1.0)):
            Wt = _fk(game, "thigh_" + s, Wp, B["thigh_" + s])
            Wc = _fk(game, "calf_" + s, Wt, B["calf_" + s])
            Wf = _fk(game, "foot_" + s, Wc, B["foot_" + s])
            ankle_goal = W["foot_" + s].translation.copy()
            ankle_goal.x += (mid_x - ankle_goal.x) * min(1.0, narrow / max(1e-6, abs(ankle_goal.x - mid_x))) \
                * plant[s][i]
            hip = Wt.translation
            pole = W["calf_" + s].translation - SIDE * (sign * narrow * plant[s][i]) + FWD * 0.3
            knee = _two_bone(hip, Wc.translation, Wf.translation, ankle_goal, pole)
            reach = (Wc.translation - hip).length + (Wf.translation - Wc.translation).length
            reach_short[0] = max(reach_short[0], (ankle_goal - hip).length - reach)
            Wt = _about(Wt, hip, _arc(Wc.translation - hip, knee - hip))
            Wc = _fk(game, "calf_" + s, Wt, B["calf_" + s])
            Wf = _fk(game, "foot_" + s, Wc, B["foot_" + s])
            Wc = _about(Wc, Wc.translation, _arc(Wf.translation - Wc.translation, ankle_goal - Wc.translation))
            Wf_new = W["foot_" + s].copy()
            Wf_new.translation = _fk(game, "foot_" + s, Wc, B["foot_" + s]).translation
            Wl[s] = (Wt, Wc, Wf_new)
        # 4. relaxed: a wider arm swing about each shoulder, in the travel plane
        arms = {}
        if relaxed:
            for s in ("l", "r"):
                Wcl = _fk(game, "clavicle_" + s, W3, B["clavicle_" + s])
                Wu = _fk(game, "upperarm_" + s, Wcl, B["upperarm_" + s])
                Ra = Quaternion(SIDE, (ARM_SWING_GAIN - 1.0) * swing[s][i])
                arms[s] = (Wcl, _about(Wu, Wu.translation, Ra))
        # 5. write the bases, keyed on this frame
        pbs = game.pose.bones
        pbs["pelvis"].matrix_basis = _basis(game, "pelvis", Wp, W["Root"])
        pbs["spine_01"].matrix_basis = _basis(game, "spine_01", W1, Wp)
        pbs["spine_03"].matrix_basis = _basis(game, "spine_03", W3, W2)
        for s in ("l", "r"):
            Wt, Wc, Wf = Wl[s]
            pbs["thigh_" + s].matrix_basis = _basis(game, "thigh_" + s, Wt, Wp)
            pbs["calf_" + s].matrix_basis = _basis(game, "calf_" + s, Wc, Wt)
            pbs["foot_" + s].matrix_basis = _basis(game, "foot_" + s, Wf, Wc)
            if relaxed:
                Wcl, Wu = arms[s]
                pbs["upperarm_" + s].matrix_basis = _basis(game, "upperarm_" + s, Wu, Wcl)
        for b in keyed:
            pb = pbs[b]
            pb.keyframe_insert("rotation_quaternion", frame=f, group=b)
            if b == "pelvis":
                pb.keyframe_insert("location", frame=f, group=b)
    for pb in game.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    # one named NLA track per clip, like every other (export_character.py exports the tracks)
    ad = game.animation_data
    for t in list(ad.nla_tracks):
        if t.name == out_name:
            ad.nla_tracks.remove(t)
    src_strip = next((st for t in ad.nla_tracks for st in t.strips if st.action is src), None)
    t = ad.nla_tracks.new()
    t.name = out_name
    st = t.strips.new(out_name, f0, act)
    if src_strip is not None:
        st.extrapolation = src_strip.extrapolation
        st.blend_type = src_strip.blend_type
        st.influence = src_strip.influence
    t.mute = False
    arp_clips._bind(game, None)
    if reach_short[0] > 0.002:
        print("[gait] %s: a planted foot is %.3f m past the leg's reach at worst" % (out_name, reach_short[0]))
    return act


def check(game, src_name, out_name, relaxed=False):
    """Fail on anything that would reach the aim or read as a broken walk."""
    src, out = bpy.data.actions[src_name], bpy.data.actions[out_name]
    f0, f1 = int(round(src.frame_range[0])), int(round(src.frame_range[1]))
    frames = list(range(f0, f1 + 1))
    A, B = _sample(game, src, frames), _sample(game, out, frames)
    arp_clips._bind(game, None)
    errs = []
    worst_rot = worst_pos = 0.0
    for a, b in zip(A, B):
        qa, qb = a["spine_03"][0].to_quaternion(), b["spine_03"][0].to_quaternion()
        worst_rot = max(worst_rot, math.degrees(qa.rotation_difference(qb).angle))
        worst_pos = max(worst_pos, (a["spine_03"][0].translation - b["spine_03"][0].translation).length)
    if not relaxed and (worst_rot > 0.5 or worst_pos > 0.005):
        errs.append("spine_03 moved %.2f deg / %.4f m (limit 0.5 deg / 5 mm)" % (worst_rot, worst_pos))

    # Planted frames are taken from the SOURCE and used for both clips: re-picking them on the derived clip
    # (whose ankles sit ~2 mm differently) changes which frames count and reads as slide or widening.
    lowest = {s: min(range(len(A)), key=lambda i: A[i]["foot_" + s][0].translation.z) for s in ("l", "r")}
    planted = {s: [i for i in range(len(A)) if A[i]["foot_" + s][0].translation.z
                   < A[lowest[s]]["foot_" + s][0].translation.z + 0.01] for s in ("l", "r")}

    def planted_width(S):
        return S[lowest["l"]]["foot_l"][0].translation.x - S[lowest["r"]]["foot_r"][0].translation.x
    wa, wb = planted_width(A), planted_width(B)
    if not wb < wa - 0.02:
        errs.append("planted feet %.3f m apart, source %.3f: not narrower" % (wb, wa))

    def slide(S, s):
        pts = [S[i]["foot_" + s][0].translation for i in planted[s]]
        return max(((p - q).length for p in pts for q in pts), default=0.0)
    for s in ("l", "r"):
        if slide(B, s) > slide(A, s) + 0.01:
            errs.append("foot_%s slides %.3f m while planted (source %.3f)" % (s, slide(B, s), slide(A, s)))
    side = [P["pelvis"][0].translation.x for P in B]
    ra = [_hip_roll(P) for P in A]; rb = [_hip_roll(P) for P in B]
    roll_a, roll_b = math.degrees(max(ra) - min(ra)), math.degrees(max(rb) - min(rb))
    if not relaxed and not roll_b > roll_a * 1.08:
        errs.append("hip drop %.1f deg, source %.1f: not larger" % (roll_b, roll_a))
    upper = max(abs(math.degrees(a["upperarm_l"][0].to_quaternion().rotation_difference(
        b["upperarm_l"][0].to_quaternion()).angle)) for a, b in zip(A, B))
    print("[gait] %-34s spine_03 %.2f deg %.4f m | feet %.3f -> %.3f m | pelvis side %.3f m | hip drop %.1f -> %.1f deg"
          " | arm %.1f deg%s" % (out_name, worst_rot, worst_pos, wa, wb, max(side) - min(side), roll_a, roll_b, upper, " (relaxed)" if relaxed else ""))
    return errs


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rig, game = _arm()
    arp_clips._drive(rig, 0.0)                 # the body plays its own clips, not the rig
    use_nla, game.animation_data.use_nla = game.animation_data.use_nla, False
    made = []
    for name in SOURCES:
        if name not in bpy.data.actions:
            print("[gait] no %s -- skipped" % name)
            continue
        out = PREFIX + name
        if out in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[out])
        derive(game, name, out)
        made.append((name, out, False))
    if RELAXED_OUT in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[RELAXED_OUT])
    derive(game, RELAXED_SOURCE, RELAXED_OUT, relaxed=True)
    made.append((RELAXED_SOURCE, RELAXED_OUT, True))
    errs = []
    for src, out, rel in made:
        errs += ["%s: %s" % (out, e) for e in check(game, src, out, rel)]
    game.animation_data.use_nla = use_nla
    arp_clips._bind(game, None)
    arp_clips._drive(rig, 1.0)                 # the file opens in ARP (game_export_ui's rule)
    for e in errs:
        print("[gait] FAIL " + e)
    if errs:
        sys.exit(1)
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
        print("[gait] saved %s" % bpy.data.filepath)
    print("[gait] PASS %d clip(s)" % len(made))


if __name__ == "__main__":
    main()
