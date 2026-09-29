"""SEED the male and female walks from the one walk, in the clip .blend -- once (user, 2026-09-27/28).

    blender -b assets/characters/shino/shino.blend --python blender/tools/derive_gait.py -- [--save]
        [--gait=male|m,f] [--force | --force=<clip>,...]

The source walk (`upright_walk_forward` and its ring) drops the hips 20.5 deg with no pelvic rotation and
carries the arms bent and behind, so neither sex plays it raw. This writes, INTO shino.blend, ordinary
clips that an artist sees in the Game sidebar and edits on the rig like any other:

    male_upright_walk_forward, _forward_left, _forward_right, _back, male_upright_walk
    female_upright_walk_forward, _forward_left, _forward_right, _back, female_upright_walk

`<gait>_upright_walk` is the NORMAL walk, hands empty (the AnimationTree's out-of-combat branch plays it);
the `_forward` ring is the walk with a weapon up. `character_gaits.json` says which body plays which, and
`tools/godot/build_character_anims.gd` puts each gait's clips under the BASE names in its own library.

It is a SEED, not a build step: a clip already in the file is KEPT, because it may hold an artist's edit.
`--force` (or `--force=<clip>`) derives it again from the source walk and loses that edit. Each new clip is
moved onto the Auto-Rig Pro controls (arp_clips.move_to_arp, FK, proved exact by an unedited bake).

What the FEMALE derivation changes, each measured on the source first (Shino, 2026-09-27); the male one
uses the same steps with less hip drop, a small pelvic turn and the feet pushed WIDER, and re-carries the arms:
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

The NORMAL walk (`<prefix>upright_walk-loop`) adds what each walk does above the waist:
the female a gentle chest counter-roll, the male a shoulder-line turn with his arms; each profile's `arms`
block re-carries the arms (see PROFILES). It is played ONLY while no weapon is
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
NORMAL_WALK = "upright_walk-loop"          # the hands-down walk (the AnimationTree's Relaxed branch plays it)
LEGACY_PREFIXES = ("f_", "m_")               # the first, regenerated-every-time names; removed on sight

# ONE GAIT PER PROFILE (2026-09-28). The source walk is neither: measured on Shino it drops the hips 20.5 deg
# peak-to-peak with NO pelvic rotation at all -- a catwalk sway, which is what read wrong on Fumiriya. So a
# male body plays a derived `m_` copy too; the source clip is only the shared pose the two are made from.
#   narrow    fraction of the planted step width taken out (female 9.3 cm -> ~5.0 cm); NEGATIVE widens
#             (male 9.3 cm -> ~12.6 cm)
#             A fraction, not metres: the diagonals already plant narrower (6.1-8.1 cm), and a fixed
#             2.15 cm per foot put forward_right's feet 1.8 cm apart, i.e. crossing.
#   shift     m the pelvis moves over the standing foot at mid-stance
#   roll_gain the clip's own hip drop x this (1.35 left the standing leg short of the ground)
#   yaw_deg   peak pelvic ROTATION about the vertical, the hip on the swing side coming forward with its leg
#   relaxed   whether the gait gets its own relaxed (hands-down) clip; if not, the gait table maps the
#             relaxed walk onto the gait's forward clip
#   chest_roll_deg / chest_yaw_deg  relaxed only: the chest's counter-roll against the hip drop, and its
#             counter-yaw against the ARM swing (the shoulder of the forward-swinging arm comes forward)
#   arms      the ARM CARRIAGE, or None to keep the source's. The source holds both elbows bent a fixed 41 deg
#             and swings the upper arm only BEHIND the body (-22..-2 deg), with still shoulders -- a feminine
#             carriage, and the whole of why the first male walk still read female. Each field:
#               mean     deg, the upper arm's centre of swing (+ = forward of hanging straight down)
#               gain     x the source's own swing amplitude (the source's phase is kept)
#               out      deg the upper arm hangs out from the body
#               elbow    deg of elbow bend at the back of the swing ...
#               elbow_fwd  ... plus this much more as the arm comes fully forward
#               clav_deg deg the collarbone protracts/retracts with its arm's swing (the SHOULDER drives it)
#               relaxed_only  apply only in the relaxed clip (female: user, the steady walk stays as it is)
#             The hand keeps its own local pose, so it simply follows the forearm (no extra wrist roll).
PROFILES = {
    "f": {"prefix": "female_", "narrow": 0.46, "shift": 0.022, "roll_gain": 1.15, "yaw_deg": 0.0, "relaxed": True,
          "chest_roll_deg": 2.5, "chest_yaw_deg": 0.0,
          "arms": {"mean": -6.0, "gain": 1.0, "out": 8.0, "elbow": 20.0, "elbow_fwd": 10.0, "clav_deg": 1.0,
                   "relaxed_only": True}},
    # male (user, 2026-09-28): hips mostly still -- barely any turn, a small drop -- and a WIDER stance; the
    # arms hang nearly straight and swing from the shoulder, evenly in front and behind, a little out from
    # the body; in the relaxed walk the shoulder line turns a few degrees with the arms.
    "m": {"prefix": "male_", "narrow": -0.35, "shift": 0.010, "roll_gain": 0.45, "yaw_deg": 1.0, "relaxed": True,
          "chest_roll_deg": 0.0, "chest_yaw_deg": 3.0,
          "arms": {"mean": -4.0, "gain": 1.4, "out": 13.0, "elbow": 10.0, "elbow_fwd": 14.0, "clav_deg": 3.0,
                   "relaxed_only": False}},
}
ARMS = None
NARROW = SHIFT = ROLL_GAIN = YAW_DEG = 0.0   # set from the profile being derived (_use)
PREFIX = "female_"


def _use(profile):
    global NARROW, SHIFT, ROLL_GAIN, YAW_DEG, PREFIX, ARMS, CHEST_ROLL_DEG, CHEST_YAW_DEG
    p = PROFILES[profile]
    ARMS, CHEST_ROLL_DEG, CHEST_YAW_DEG = p.get("arms"), p.get("chest_roll_deg", 0.0), p.get("chest_yaw_deg", 0.0)
    NARROW, SHIFT, ROLL_GAIN, YAW_DEG, PREFIX = p["narrow"], p["shift"], p["roll_gain"], p["yaw_deg"], p["prefix"]
    return p

# relaxed-only, above the waist
CHEST_ROLL_DEG = 0.0   # set per profile (_use)
CHEST_YAW_DEG = 0.0
CHEST_YAW_GAIN = 0.25  # chest counter-yaw against the pelvis yaw

SIDE = Vector((1.0, 0.0, 0.0))       # armature space: +X is the body's LEFT
FWD = Vector((0.0, -1.0, 0.0))       # -Y is forward
UP = Vector((0.0, 0.0, 1.0))

KEYED = ["pelvis", "spine_01", "spine_03", "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
ARM_KEYED = ["clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r"]


def _arm_angles(P, s):
    """(swing, out, elbow) in degrees, armature space: swing + = upper arm forward of straight down."""
    sg = 1.0 if s == "l" else -1.0
    sh, el, wr = (P[b + "_" + s][0].translation for b in ("upperarm", "lowerarm", "hand"))
    u, f = el - sh, wr - el
    return (math.degrees(math.atan2(-u.y, -u.z)), math.degrees(math.atan2(sg * u.x, -u.z)),
            math.degrees(u.angle(f)))


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
    arm_sw = {s: [_arm_angles(P, s)[0] for P in S] for s in ("l", "r")}
    arm_mean = {s: sum(arm_sw[s][:cyc]) / cyc for s in arm_sw}
    arm_peak = max(1e-6, max(abs(v - arm_mean[s]) for s in arm_sw for v in arm_sw[s][:cyc]))
    do_arms = ARMS is not None and (relaxed or not ARMS["relaxed_only"])
    # Pelvic rotation: the hip on the side whose foot is FORWARD leads (-Y is forward), peaking at heel strike.
    lead = [P["foot_r"][0].translation.y - P["foot_l"][0].translation.y for P in S]
    lead_mean = sum(lead[:cyc]) / cyc
    lead_peak = max(1e-6, max(abs(v - lead_mean) for v in lead[:cyc]))
    pyaw = [-math.radians(YAW_DEG) * (v - lead_mean) / lead_peak for v in lead]

    act = src.copy()
    act.name = out_name
    act.use_fake_user = False
    keyed = KEYED + (ARM_KEYED if do_arms else [])
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
        R = Quaternion(UP, pyaw[i]) @ Quaternion(FWD, extra)   # hip drop scaled, plus the pelvic rotation
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
            # the shoulder of the forward-swinging arm comes forward (+X is left, -Y forward: a negative turn)
            dy -= math.radians(CHEST_YAW_DEG) * ((arm_sw["l"][i] - arm_mean["l"]) - (arm_sw["r"][i] - arm_mean["r"])) \
                / (2 * arm_peak)
            Rc = Quaternion(UP, dy) @ Quaternion(FWD, dr)
            W3 = _about(W3, W3.translation, Rc)
        # 3. legs: each foot toward the centre line while planted, the leg re-solved to reach it
        Wl = {}
        for s, sign in (("l", 1.0), ("r", -1.0)):
            Wt = _fk(game, "thigh_" + s, Wp, B["thigh_" + s])
            Wc = _fk(game, "calf_" + s, Wt, B["calf_" + s])
            Wf = _fk(game, "foot_" + s, Wc, B["foot_" + s])
            ankle_goal = W["foot_" + s].translation.copy()
            if narrow >= 0:
                ankle_goal.x += (mid_x - ankle_goal.x) * min(1.0, narrow / max(1e-6, abs(ankle_goal.x - mid_x))) \
                    * plant[s][i]
            else:
                # WIDEN each foot out on its OWN side (+X is the body's left). Pushing away from the midline
                # instead flips sign when a diagonal walk's planted foot crosses it, and the foot slides 2 cm.
                ankle_goal.x += sign * (-narrow) * plant[s][i]
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
        # 4. the arm carriage: collarbone with its arm's swing, then the upper arm aimed at its new swing/out,
        #    then the elbow opened to its new bend in the arm's own plane; the hand follows in its own pose
        arms = {}
        if do_arms:
            A = ARMS
            for s, sg in (("l", 1.0), ("r", -1.0)):
                ph = (arm_sw[s][i] - arm_mean[s]) / arm_peak               # -1 back .. +1 forward
                Wcl = _fk(game, "clavicle_" + s, W3, B["clavicle_" + s])
                Wcl = _about(Wcl, Wcl.translation, Quaternion(UP, -sg * math.radians(A["clav_deg"]) * ph))
                Wu = _fk(game, "upperarm_" + s, Wcl, B["upperarm_" + s])
                Wlo = _fk(game, "lowerarm_" + s, Wu, B["lowerarm_" + s])
                sw = math.radians(A["mean"] + A["gain"] * (arm_sw[s][i] - arm_mean[s]))
                out = math.radians(A["out"])
                t = Vector((sg * math.tan(out), -math.tan(sw), -1.0)).normalized()
                Wu = _about(Wu, Wu.translation, _arc(Wlo.translation - Wu.translation, t))
                Wlo = _fk(game, "lowerarm_" + s, Wu, B["lowerarm_" + s])
                Wh = _fk(game, "hand_" + s, Wlo, B["hand_" + s])
                u = Wlo.translation - Wu.translation
                fv = Wh.translation - Wlo.translation
                bend = math.degrees(u.angle(fv))
                goal = A["elbow"] + A["elbow_fwd"] * max(0.0, ph)
                axis = fv.cross(u)
                if axis.length > 1e-6:
                    Wlo = _about(Wlo, Wlo.translation, Quaternion(axis.normalized(), math.radians(bend - goal)))
                arms[s] = (Wcl, Wu, Wlo)
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
            if do_arms:
                Wcl, Wu, Wlo = arms[s]
                pbs["clavicle_" + s].matrix_basis = _basis(game, "clavicle_" + s, Wcl, W3)
                pbs["upperarm_" + s].matrix_basis = _basis(game, "upperarm_" + s, Wu, Wcl)
                pbs["lowerarm_" + s].matrix_basis = _basis(game, "lowerarm_" + s, Wlo, Wu)
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


def check(game, src_name, out_name, relaxed=False, profile="f"):
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
    if NARROW > 0 and not wb < wa - 0.02:
        errs.append("planted feet %.3f m apart, source %.3f: not narrower" % (wb, wa))
    if NARROW < 0 and not wb > wa + 0.015:
        errs.append("planted feet %.3f m apart, source %.3f: not wider" % (wb, wa))

    def slide(S, s):
        pts = [S[i]["foot_" + s][0].translation for i in planted[s]]
        return max(((p - q).length for p in pts for q in pts), default=0.0)
    for s in ("l", "r"):
        if slide(B, s) > slide(A, s) + 0.01:
            errs.append("foot_%s slides %.3f m while planted (source %.3f)" % (s, slide(B, s), slide(A, s)))
    side = [P["pelvis"][0].translation.x for P in B]
    ra = [_hip_roll(P) for P in A]; rb = [_hip_roll(P) for P in B]
    roll_a, roll_b = math.degrees(max(ra) - min(ra)), math.degrees(max(rb) - min(rb))
    if not relaxed and ROLL_GAIN > 1 and not roll_b > roll_a * 1.08:
        errs.append("hip drop %.1f deg, source %.1f: not larger" % (roll_b, roll_a))
    if not relaxed and ROLL_GAIN < 1 and not roll_b < roll_a * (ROLL_GAIN + 0.15):
        errs.append("hip drop %.1f deg, source %.1f: not reduced to ~x%.2f" % (roll_b, roll_a, ROLL_GAIN))
    ya = [_pelvis_yaw(P) for P in A]; yb = [_pelvis_yaw(P) for P in B]
    yaw_b = math.degrees(max(yb) - min(yb))
    if YAW_DEG > 0 and not yaw_b < math.degrees(max(ya) - min(ya)) + 2 * YAW_DEG + 1.0:
        errs.append("pelvic rotation %.1f deg peak-to-peak, wanted at most ~%.1f" % (yaw_b, 2 * YAW_DEG))
    arm_b = [_arm_angles(P, "l") for P in B]
    arm_txt = " | arm swing %.0f..%.0f out %.0f elbow %.0f..%.0f" % (
        min(x[0] for x in arm_b), max(x[0] for x in arm_b), sum(x[1] for x in arm_b) / len(arm_b),
        min(x[2] for x in arm_b), max(x[2] for x in arm_b))
    upper = max(abs(math.degrees(a["upperarm_l"][0].to_quaternion().rotation_difference(
        b["upperarm_l"][0].to_quaternion()).angle)) for a, b in zip(A, B))
    print("[gait] %-34s spine_03 %.2f deg %.4f m | feet %.3f -> %.3f m | pelvis side %.3f m | hip drop %.1f -> %.1f deg"
          " | hip rotation %.1f -> %.1f deg | arm %.1f deg%s" % (out_name, worst_rot, worst_pos, wa, wb, max(side) - min(side), roll_a, roll_b,
          math.degrees(max(ya) - min(ya)), yaw_b, upper, (" (relaxed)" if relaxed else "") + arm_txt))
    return errs


def _drop(name):
    """Remove a clip: its game action, its NLA track and its rig copy."""
    _, game = _arm()
    ad = game.animation_data
    for t in list(ad.nla_tracks):
        if t.name == name or any(st.action is not None and st.action.name == name for st in t.strips):
            ad.nla_tracks.remove(t)
    for n in (name, arp_clips.PREFIX + name):
        if n in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[n])


def main():
    """A ONE-TIME SEED (user, 2026-09-28: "bake into the master blend, so an artist sees it in Blender"):
    each gait clip is written ONCE, moved onto the Auto-Rig Pro controls like every other clip, and from
    then on it is an ordinary clip in shino.blend -- listed in the Game sidebar, edited on the rig, exported
    by the Export button. A clip that already exists is KEPT (it may carry an artist's edit); `--force`
    (or `--force=<clip>,...`) derives it again from the source walk, throwing that edit away."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rig, game = _arm()
    only = next(([{"male": "m", "female": "f"}.get(x, x) for x in a.split("=", 1)[1].split(",")]
                 for a in argv if a.startswith("--gait=")), list(PROFILES))
    force_arg = next((a for a in argv if a.startswith("--force")), None)
    force_all = force_arg == "--force"
    force_some = set(force_arg.split("=", 1)[1].split(",")) if force_arg and "=" in force_arg else set()
    for old in [a.name for a in bpy.data.actions if a.name.startswith(LEGACY_PREFIXES)
                or a.name.startswith(tuple(arp_clips.PREFIX + p for p in LEGACY_PREFIXES))]:
        if old in bpy.data.actions:
            name = old[len(arp_clips.PREFIX):] if old.startswith(arp_clips.PREFIX) else old
            _drop(name)
            print("[gait] removed the old generated clip %s" % name)

    arp_clips._drive(rig, 0.0)                 # the body plays its own clips, not the rig
    use_nla, game.animation_data.use_nla = game.animation_data.use_nla, False
    made, kept, errs = [], [], []
    for g in only:
        p = _use(g)
        jobs = [(name, PREFIX + name, False) for name in SOURCES if name in bpy.data.actions]
        if p["relaxed"]:
            jobs.append((RELAXED_SOURCE, PREFIX + NORMAL_WALK, True))
        for src, out, rel in jobs:
            short = out[:-5] if out.endswith("-loop") else out
            exists = out in bpy.data.actions or (arp_clips.PREFIX + out) in bpy.data.actions
            if exists and not (force_all or out in force_some or short in force_some):
                kept.append(out)
                continue
            _drop(out)
            derive(game, src, out, relaxed=rel)
            errs += ["%s: %s" % (out, e) for e in check(game, src, out, rel, g)]
            made.append(out)
    game.animation_data.use_nla = use_nla
    arp_clips._bind(game, None)
    for out in kept:
        print("[gait] KEPT %s (already in the file -- it may hold an edit; --force=%s to derive it again)" % (out, out))
    for e in errs:
        print("[gait] FAIL " + e)
    if errs:
        arp_clips._drive(rig, 1.0)
        sys.exit(1)
    # onto the rig, like every clip: an unedited bake must write 0 keys, i.e. the rig reproduces it exactly
    for out in made:
        arp_clips.move_to_arp(out, to_ik=False)
        n = arp_clips.bake_to_game(out, force=True)
        print("[gait] %s on the rig: %s" % (out, "exact" if n == 0 else "%d keys differ" % n))
        if n != 0:
            errs.append("%s: the rig does not reproduce it (%d keys)" % (out, n))
    arp_clips._drive(rig, 1.0)                 # the file opens in ARP (game_export_ui's rule)
    for e in errs:
        print("[gait] FAIL " + e)
    if errs:
        sys.exit(1)
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
        print("[gait] saved %s" % bpy.data.filepath)
    print("[gait] PASS %d clip(s) derived, %d kept" % (len(made), len(kept)))


if __name__ == "__main__":
    main()
