"""Add an IK CONTROL LAYER to a character .blend, so a pose is made by moving a hand or a foot.

    blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \
        --python blender/tools/add_control_rig.py -- --save

A ONE-SHOT, like `import_melee_pack.py` and `normalize_kit.py --init`: it runs when a body needs a
control layer, the result is committed inside the `.blend`, and **nothing depends on it running
again** -- no gate calls it, no build step, no export path. That is deliberate: a tool every export
depends on is how a repo grows legacy. The clips are already protected by gates that exist
(`probe_shared_anims.gd`, `probe_body_contract.gd`, `check_character_anim.py`), so this needs none
of its own. The workflow and the snap helpers are written INTO the `.blend` as a text block, so they
travel with the file and do not depend on this script surviving.

Why this and not Rigify / Auto-Rig Pro / Rigodotify (measured 2026-09-20, CLAUDE.md "W42"):
those GENERATE a rig, and a generated rig brings its own bone ROLLS. Our rest orientations are half
the skeleton contract (`blender/SKELETON_CONTRACT.md`) and both VRoid bodies were CONFORMED to them,
so changing the reference rest would re-mean all 171 clips, force a re-conform of every body, and
move every bone-frame constant in the game (the six weapon sockets, the mount anchors, the holster
slings, the ragdoll frames, all three `<body>.body.json`). This script instead ADDS bones and
constraints and touches no rest, no deform bone and no action. It also needs no add-on, runs
headless, and is idempotent -- the same contract every other generator here has.

WHAT IT ADDS (nothing else):
  * 4 IK targets  CTRL_hand_l/r, CTRL_foot_l/r   -- the thing you grab
  * 4 pole targets CTRL_elbow_l/r, CTRL_knee_l/r -- which way the joint bends
  * 1 root        CTRL_root                      -- parent of all of the above, to move the lot
  * an IK constraint on lowerarm_l/r (chain 3: THE CLAVICLE IS IN IT) and calf_l/r (chain 2),
    **influence 0**
  * stiffness and a symmetric angle envelope on each clavicle, so the hand pushes the adjustment up
    into the shoulder only as far as it must and can never dislocate it (CLAV_STIFFNESS /
    CLAV_LIMIT_DEG)
  * a hideable bone collection `CTRL`, wire widgets in a hidden `CTRL_WIDGETS` collection
  * a `IK CONTROLS` text block: the workflow, and the snap-to-FK helper

**THE INFLUENCE IS 0 AND THAT IS THE WHOLE SAFETY ARGUMENT.** An IK constraint at full influence
OVERRIDES the chain's own rotation channels, so switching it on globally would silently replace the
arms of all 171 clips with whatever the control bone happens to be near. At 0 the rig evaluates
exactly as it did before -- asserted by this script, and by `probe_shared_anims.gd` afterwards.

TWO WAYS TO USE IT, and the second is the one that keeps the clips portable:
  1. raise the constraint's influence, pose, and KEY the control. The glTF export samples the
     evaluated pose, so the .glb is correct -- but the ACTION then keys control bones, which means
     every body in `animation_review.blend` needs this layer too, and `export_def_bones` must be on.
  2. raise the influence, pose, then SNAP TO FK (the text block's helper) and drop it back to 0.
     The action ends up keying only the 53 contract bones, exactly as today: no control keys, no
     export flag needed, and the review file and every other body are unaffected. Prefer this.

The pole angle is SOLVED, not guessed: after the constraints are built the script sweeps
`pole_angle` and keeps the one that moves the limb least away from the pose it already has, so
turning IK on does not snap the elbow to a new plane. It reports the residual.
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector

ARM_DEFAULT = "Godot_Chan_Stealth"
COLLECTION = "CTRL"
WIDGETS = "CTRL_WIDGETS"
TEXT_BLOCK = "IK CONTROLS"

# (control, chain tip bone, IK owner = last bone of the chain, pole, pole direction in BLENDER axes)
# The rig rests facing -Y with the left arm at +X (the contract), so "behind" is +Y and "in front"
# is -Y. That is an anatomical fact about a humanoid, and it is used rather than derived from the
# rest pose because a T-posed arm is STRAIGHT: shoulder, elbow and wrist are collinear there, so
# the bend plane cannot be measured from it at all.
LIMBS = [
    {"ctrl": "CTRL_hand_l", "tip": "hand_l", "owner": "lowerarm_l", "pole": "CTRL_elbow_l",
     "joint": "lowerarm_l", "dir": Vector((0.0, 1.0, 0.0)), "size": 0.09,
     "chain": 3, "shoulder": "clavicle_l"},
    {"ctrl": "CTRL_hand_r", "tip": "hand_r", "owner": "lowerarm_r", "pole": "CTRL_elbow_r",
     "joint": "lowerarm_r", "dir": Vector((0.0, 1.0, 0.0)), "size": 0.09,
     "chain": 3, "shoulder": "clavicle_r"},
    {"ctrl": "CTRL_foot_l", "tip": "foot_l", "owner": "calf_l", "pole": "CTRL_knee_l",
     "joint": "calf_l", "dir": Vector((0.0, -1.0, 0.0)), "size": 0.11, "chain": 2},
    {"ctrl": "CTRL_foot_r", "tip": "foot_r", "owner": "calf_r", "pole": "CTRL_knee_r",
     "joint": "calf_r", "dir": Vector((0.0, -1.0, 0.0)), "size": 0.11, "chain": 2},
]
POLE_TOLERANCE = 0.02   # metres the elbow may move when IK is switched on
POLE_REACH = 0.35        # metres out from the joint; scaled by the body's own limb length
IK_NAME = "CTRL_IK"

# ---------------------------------------------------------------- the shoulder

# THE ARM CHAIN REACHES THE CLAVICLE, and that is the whole point of the 3-bone chain: a support
# hand that cannot reach its grip is short because of the SHOULDER, not the arm (measured on the
# three shipped bodies -- Shino's shoulders are 0.2174 m against the other two's 0.2955, and it is
# that 7.8 cm, not her arm length, that misses ASR1's and SHG1's handguards). Protracting the
# shoulder is what a human does to extend reach, so the gesture the artist wants is "move the hand
# and let the shoulder follow", not "pose the collarbone first and then the arm".
#
# IT GOES UP ONLY AS FAR AS IT MUST. `ik_stiffness` is a per-bone resistance, so at 0.9 the solver
# spends the elbow and the shoulder joint first and reaches the collarbone only when the arm has
# run out -- which is the behaviour the runtime `SupportHandIKModifier` already has (it protracts
# ONLY past the arm's own reach) and the two now agree.
CLAV_STIFFNESS = 0.9
# AND IT CANNOT OVER-ROTATE. A limit is what stops the solver answering "I cannot reach" with a
# dislocated shoulder, which is the defect this layer must not introduce. It is measured against
# the clips rather than taken from an anatomy table: over the 171 shared clips every aim, hold,
# idle, locomotion and reload pose turns a clavicle at most 35 deg on its OWN channel (the aim
# poses use 24-35), so 60 leaves every authored pose alone with room to spare while refusing the
# 72-171 deg the six ARMS-ONLY retargeted attack clips carry (W34) -- see
# `blender/tools/fix_shoulder_overbend.py`, which resets exactly those against this same number.
CLAV_LIMIT_DEG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "character_anim_naming.json")))["limits"]["shoulder_channel_deg"]


def log(msg):
    print("[control-rig] %s" % msg)


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"armature": ARM_DEFAULT, "save": False, "out": None}
    for a in argv:
        if a == "--save":
            out["save"] = True
        elif a.startswith("--armature="):
            out["armature"] = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out["out"] = a.split("=", 1)[1]
        else:
            raise SystemExit("[control-rig] unknown argument %r" % a)
    return out


def find_armature(name):
    """The named armature, else the only one in the file. A body may name its armature anything."""
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type == 'ARMATURE':
        return ob
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(arms) == 1:
        log("no object %r; using the file's only armature %r" % (name, arms[0].name))
        return arms[0]
    raise SystemExit("[control-rig] cannot pick an armature (%d in the file): %s"
                     % (len(arms), [o.name for o in arms]))


def widget(name, kind, size):
    """A wire mesh for a control bone, in a hidden collection so nothing renders or exports."""
    coll = bpy.data.collections.get(WIDGETS)
    if coll is None:
        coll = bpy.data.collections.new(WIDGETS)
        bpy.context.scene.collection.children.link(coll)
        coll.hide_viewport = True
        coll.hide_render = True
    ob = bpy.data.objects.get(name)
    if ob is not None:
        return ob
    me = bpy.data.meshes.new(name)
    if kind == "cube":
        s = size * 0.5
        vs = [(x * s, y * s, z * s) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        es = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7),
              (4, 5), (4, 6), (5, 7), (6, 7)]
    else:  # a diamond, for a pole
        s = size * 0.5
        vs = [(0, 0, s), (s, 0, 0), (0, s, 0), (-s, 0, 0), (0, -s, 0), (0, 0, -s)]
        es = [(0, 1), (0, 2), (0, 3), (0, 4), (5, 1), (5, 2), (5, 3), (5, 4),
              (1, 2), (2, 3), (3, 4), (4, 1)]
    me.from_pydata(vs, es, [])
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.hide_viewport = True
    ob.hide_render = True
    return ob


def build_bones(arm, scale):
    """Create or MOVE the control bones. Idempotent: an existing CTRL_ bone is repositioned."""
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    made, moved = [], []

    def ensure(name):
        b = eb.get(name)
        if b is None:
            b = eb.new(name)
            made.append(name)
        else:
            moved.append(name)
        b.use_deform = False       # belt and braces; export_def_bones is what actually excludes it
        b.parent = None
        return b

    root = ensure("CTRL_root")
    root.head = Vector((0.0, 0.0, 0.0))
    root.tail = Vector((0.0, 0.0, 0.10 * scale))
    root.roll = 0.0

    for L in LIMBS:
        tip = eb.get(L["tip"])
        owner = eb.get(L["owner"])
        if tip is None or owner is None:
            raise SystemExit("[control-rig] %r has no bone %r/%r -- is this a contract rig?"
                             % (arm.name, L["tip"], L["owner"]))
        # An IK constraint drives the OWNER's tail onto the TARGET's HEAD, and the owner's tail is
        # the tip bone's head -- so the control's head must sit exactly there or the limb jumps the
        # moment influence is raised.
        c = ensure(L["ctrl"])
        c.head = tip.head.copy()
        c.tail = tip.tail.copy() if (tip.tail - tip.head).length > 1e-6 else tip.head + Vector((0, 0, 0.05))
        c.roll = tip.roll
        c.parent = root

        # the pole sits out from the JOINT (the owner's head) along the anatomical bend direction
        j = eb.get(L["joint"])
        p = ensure(L["pole"])
        limb_len = (owner.tail - owner.head).length + (j.tail - j.head).length
        off = L["dir"].normalized() * (POLE_REACH * max(limb_len, 1e-6) / 0.6)
        p.head = j.head + off
        p.tail = p.head + Vector((0.0, 0.0, 0.05 * scale))
        p.roll = 0.0
        p.parent = root

    bpy.ops.object.mode_set(mode='OBJECT')
    return made, moved


def build_constraints(arm):
    """One IK per limb, influence 0. An existing CTRL_IK is updated rather than duplicated."""
    for L in LIMBS:
        pb = arm.pose.bones[L["owner"]]
        con = pb.constraints.get(IK_NAME)
        if con is None:
            con = pb.constraints.new('IK')
            con.name = IK_NAME
        con.target = arm
        con.subtarget = L["ctrl"]
        con.pole_target = arm
        con.pole_subtarget = L["pole"]
        con.chain_count = L.get("chain", 2)
        con.use_tail = True
        con.use_stretch = False        # a game skeleton does not stretch; W25's Limit Scale reason
        con.influence = 0.0            # <- the safety argument; see the module docstring
    # nothing else on the rig may silently stretch either
    for L in LIMBS:
        arm.pose.bones[L["owner"]].ik_stretch = 0.0
        if L.get("shoulder"):
            shoulder_limits(arm.pose.bones[L["shoulder"]])


def shoulder_limits(pb):
    """Stiffness and an angle envelope on the collarbone. See CLAV_STIFFNESS / CLAV_LIMIT_DEG.

    The envelope is SYMMETRIC and the same on all three axes, deliberately: which local axis is
    protraction and which is elevation is a fact about this rig's bone roll, and an envelope written
    per axis would be a second place that fact lives (and would be wrong on a body whose roll
    differs). "At most 60 deg away from rest, whichever way" needs no such knowledge and is the
    thing being asked for.
    """
    lim = math.radians(CLAV_LIMIT_DEG)
    pb.ik_stretch = 0.0
    for axis in "xyz":
        setattr(pb, "ik_stiffness_%s" % axis, CLAV_STIFFNESS)
        setattr(pb, "use_ik_limit_%s" % axis, True)
        setattr(pb, "ik_min_%s" % axis, -lim)
        setattr(pb, "ik_max_%s" % axis, lim)


def dress(arm, scale):
    """Bone collection + widgets, so the controls are visible and hideable in the viewport."""
    coll = arm.data.collections.get(COLLECTION) if hasattr(arm.data, "collections") else None
    if coll is None:
        coll = arm.data.collections.new(COLLECTION)
    names = ["CTRL_root"] + [n for L in LIMBS for n in (L["ctrl"], L["pole"])]
    for n in names:
        b = arm.data.bones.get(n)
        if b is not None:
            try:
                coll.assign(b)
            except Exception:
                pass
    for L in LIMBS:
        pb = arm.pose.bones[L["ctrl"]]
        pb.custom_shape = widget("WGT_%s" % L["ctrl"], "cube", L["size"] * scale)
        pb.bone.show_wire = True
        pp = arm.pose.bones[L["pole"]]
        pp.custom_shape = widget("WGT_pole", "diamond", 0.06 * scale)
        pp.bone.show_wire = True
    r = arm.pose.bones["CTRL_root"]
    r.custom_shape = widget("WGT_root", "cube", 0.30 * scale)
    r.bone.show_wire = True


# ---------------------------------------------------------------- measuring

def wpos(arm, name):
    return (arm.matrix_world @ arm.pose.bones[name].matrix).translation.copy()


def wtail(arm, name):
    pb = arm.pose.bones[name]
    return (arm.matrix_world @ pb.matrix @ Vector((0.0, pb.bone.length, 0.0)))


def apply_action(arm, act, frame):
    """Put an action on the rig AND BIND ITS SLOT (Blender 4.4+; see SKELETON_CONTRACT.md §9)."""
    arm.animation_data_create()
    arm.animation_data.action = act
    if act is not None and act.slots:
        arm.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def bend_deg(arm, L):
    """The angle at the joint. 180 is a straight limb, which is useless for solving a pole."""
    chain_root = arm.pose.bones[L["owner"]].parent.name
    a = wpos(arm, chain_root) - wpos(arm, L["owner"])
    b = wtail(arm, L["owner"]) - wpos(arm, L["owner"])
    if a.length < 1e-6 or b.length < 1e-6:
        return 180.0
    return math.degrees(a.angle(b))


def most_bent(arm, L, actions):
    """The (action, frame) where this limb bends most -- a straight limb cannot place a pole."""
    best = (None, 0, 180.0)
    for act in actions:
        lo, hi = act.frame_range
        step = max(1, int((hi - lo) / 8))
        for f in range(int(lo), int(hi) + 1, step):
            apply_action(arm, act, f)
            d = bend_deg(arm, L)
            if d < best[2]:
                best = (act, f, d)
    return best


def place_control(arm, ctrl, target):
    """Move a control bone so its HEAD lands on `target` (world). The IK drives the chain tip onto
    exactly that point, so this is the FK->IK snap: do it before raising influence or the limb jumps
    to wherever the control was left."""
    pb = arm.pose.bones[ctrl]
    m = (arm.matrix_world @ pb.matrix).copy()
    m.translation = target
    pb.matrix = arm.matrix_world.inverted() @ m
    bpy.context.view_layer.update()


def solve_pole(arm, L, act, frame):
    """Sweep pole_angle and keep the one that disturbs the posed limb least.

    Turning IK on must not SNAP the elbow to a different plane, and the correct angle depends on the
    bone's roll -- per body, per rig -- so it is measured rather than written down. The control is
    placed on the posed tip FIRST: with the control left at its rest position the chain is dragged
    the whole way there (measured 0.83 m on the arms) and no pole angle can fix that.
    """
    apply_action(arm, act, frame)
    want_joint, want_tip = wpos(arm, L["owner"]), wtail(arm, L["owner"])
    place_control(arm, L["ctrl"], want_tip)
    con = arm.pose.bones[L["owner"]].constraints[IK_NAME]
    con.influence = 1.0

    def err(angle):
        con.pole_angle = math.radians(angle)
        bpy.context.view_layer.update()
        return (wpos(arm, L["owner"]) - want_joint).length

    best = min(((err(a), a) for a in range(-180, 180, 5)), key=lambda t: t[0])
    best = min(((err(a), a) for a in [best[1] + d for d in range(-5, 6)]), key=lambda t: t[0])
    residual = err(best[1])
    tip_err = (wtail(arm, L["owner"]) - want_tip).length
    con.pole_angle = math.radians(best[1])
    con.influence = 0.0
    # leave no pose on the control: it is a handle, not state
    arm.pose.bones[L["ctrl"]].matrix_basis.identity()
    bpy.context.view_layer.update()
    return best[1], residual, tip_err

def clavicle_deg(arm, name):
    """The collarbone's OWN rotation from rest, degrees -- its channel relative to its parent, not
    its world direction (a body that rolls turns every bone in it, and what a shoulder JOINT
    articulates is the channel).

    Read off the EVALUATED pose, which is the whole trap here: an IK constraint's result never
    reaches `matrix_basis`, so a shoulder the solver had swung 0.12 m still read 0.9 deg and the
    check passed a limit it was not testing. The formula is what `matrix_basis` would be -- the
    pose in the parent's posed frame, against the rest in the parent's rest frame -- so it agrees
    with `matrix_basis` exactly wherever no constraint is running.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    ev = arm.evaluated_get(dg).pose.bones
    pb = arm.pose.bones[name]
    here = ev[name].matrix
    rest = pb.bone.matrix_local
    if pb.parent is not None:
        p_now = ev[pb.parent.name].matrix
        p_rest = pb.parent.bone.matrix_local
        here = (p_now @ p_rest.inverted() @ rest).inverted() @ here
    else:
        here = rest.inverted() @ here
    q = here.to_quaternion()
    return math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))


def verify_shoulder(arm, L, act, frame):
    """Does moving the hand OUT actually recruit the shoulder, and does the limit hold?

    The feature is "reach past what the arm can do and the collarbone follows", so it is measured
    the way it is used, and the target is placed past the arm's OWN reach -- not merely further
    from where the clip left the hand, which on a bent arm the elbow alone absorbs (measured: 0.15 m
    out of a 95 deg bend recruited 0.9 deg of shoulder, i.e. nothing).

    Two cases, because they check different halves:
      REACHED  target just past the straight arm  -> the shoulder must move AND the hand must arrive
      CAPPED   target far past any reach          -> the shoulder must stop at the envelope
    """
    out = []
    chain = [L["shoulder"], L["owner"].replace("lower", "upper"), L["owner"]]
    # The reach is the two JOINT-TO-JOINT distances, not the two bone lengths: a bone's tail need
    # not sit on its child's head, and taking the lengths under-measured this arm by 4 cm -- enough
    # that the "past its reach" target was still reachable and the case tested nothing.
    up_b, lo_b = arm.data.bones[chain[1]], arm.data.bones[chain[2]]
    arm_len = ((up_b.head_local - lo_b.head_local).length
               + (lo_b.head_local - lo_b.tail_local).length)
    con = arm.pose.bones[L["owner"]].constraints[IK_NAME]
    for label, extra in (("reached", 0.04), ("capped", 0.60)):
        apply_action(arm, act, frame)
        shoulder_pos = wpos(arm, chain[1])
        tip = wtail(arm, L["owner"])
        place_control(arm, L["ctrl"], tip)
        con.influence = 1.0
        bpy.context.view_layer.update()
        d = tip - shoulder_pos
        d = d.normalized() if d.length > 1e-6 else Vector((0.0, 0.0, 1.0))
        want = shoulder_pos + d * (arm_len + extra)
        place_control(arm, L["ctrl"], want)
        bpy.context.view_layer.update()
        out.append((label, clavicle_deg(arm, L["shoulder"]), (wtail(arm, L["owner"]) - want).length))
        con.influence = 0.0
        arm.pose.bones[L["ctrl"]].matrix_basis.identity()
        arm.pose.bones[L["pole"]].matrix_basis.identity()
        bpy.context.view_layer.update()
    return out


def pose_signature(arm, actions):
    """Every contract bone's world head over a few frames -- the thing that must NOT change."""
    sig = []
    for act in actions:
        lo, hi = act.frame_range
        for f in (int(lo), int((lo + hi) / 2), int(hi)):
            apply_action(arm, act, f)
            for b in sorted(arm.pose.bones.keys()):
                if b.startswith("CTRL_"):
                    continue
                sig.append(wpos(arm, b).copy())
    return sig


def compare(a, b):
    return max((x - y).length for x, y in zip(a, b)) if a and len(a) == len(b) else float("inf")


# ---------------------------------------------------------------- the text block

NOTE = '''\
IK CONTROLS -- added by blender/tools/add_control_rig.py. Re-run that script; do not hand-build.

WHAT YOU GRAB
  CTRL_hand_l / CTRL_hand_r    move the hand, the arm AND THE SHOULDER follow
  CTRL_foot_l / CTRL_foot_r    move the foot, the leg follows
  CTRL_elbow_* / CTRL_knee_*   which way the joint bends
  CTRL_root                    parent of all of them, moves the lot
They live in the `CTRL` bone collection -- hide it and the rig looks exactly as it did.

THE SHOULDER IS IN THE ARM CHAIN.
Reach past what the arm can do and the collarbone protracts to follow, which is what a person does
and what the runtime support-hand IK already does in game. It is STIFF (it moves only once the arm
has run out) and it is LIMITED to 60 deg from rest on every axis, so it cannot be driven into a
pose no shoulder holds. If the hand still will not reach, it stops short -- that is the honest
answer, and it means the WEAPON's SupportPoint or the pose wants moving, not the shoulder forcing.

THE INFLUENCE STARTS AT 0, ON PURPOSE.
An IK constraint at full influence OVERRIDES the chain's own rotation channels, so leaving it on
would replace the arms of all 171 shared clips with wherever the control happens to sit. At 0 the
rig evaluates exactly as before. To pose a limb, raise the IK influence on lowerarm_l / lowerarm_r /
calf_l / calf_r (Bone Constraint tab, "CTRL_IK") -- or run the helper below.

THE WORKFLOW -- SNAP ON, pose, SNAP OFF
  1. run the script below with GRAB (it moves each control onto the hand/foot where the clip
     already has it, then raises influence). Nothing moves -- measured to 0.0000 m at the tip.
  2. move CTRL_hand_* / CTRL_foot_*, and CTRL_elbow_* / CTRL_knee_* for the bend
  3. run it again with BAKE: it writes what IK produced into the FK bones and influence goes to 0
  4. key the FK bones as usual

**STEP 1 IS NOT OPTIONAL.** A control you have not grabbed sits where it was left, and raising
influence drags the limb to it -- measured 0.83 m on an arm from the rest position. Grab first.
Step 3 is what keeps a clip portable: the action ends up keying only the 53 contract bones, exactly
as today, so `animation_review.blend`, every other body and the shared library are unaffected and
the export needs no extra flag.

(You CAN skip step 3 and key the controls instead -- the glTF export samples the evaluated pose, so
the .glb would still be right. But then the action keys control bones, every body needs this layer,
and export_def_bones must be on. Prefer the snap.)

SNAP -- select the armature, be in Pose mode, set MODE below, run it (Text > Run Script).
'''

SNAP = """
MODE = "GRAB"     # "GRAB" = put the controls on the limbs and switch IK on
                  # "BAKE" = write the IK result into the FK bones and switch IK off
# Select some bones to limit it to those limbs; select none and it does all four.

import bpy
from math import radians
from mathutils import Vector

arm = bpy.context.object
assert arm and arm.type == 'ARMATURE', "select the armature, in Pose mode"
# The BAKE must write every bone the solver drove, or the shoulder silently springs back to the
# clip's pose the moment influence drops: the arms are 3-bone chains (the collarbone is in them).
CHAINS = {"lowerarm_l": ["clavicle_l", "upperarm_l", "lowerarm_l"],
          "lowerarm_r": ["clavicle_r", "upperarm_r", "lowerarm_r"],
          "calf_l": ["thigh_l", "calf_l"], "calf_r": ["thigh_r", "calf_r"]}
SEL = {b.name for b in (bpy.context.selected_pose_bones or [])}


def world(name):
    \"\"\"The EVALUATED world matrix -- with constraints applied, which is the whole point.\"\"\"
    dg = bpy.context.evaluated_depsgraph_get()
    return arm.matrix_world @ arm.evaluated_get(dg).pose.bones[name].matrix


def tail_of(name):
    m = world(name)
    return m.translation + m.col[1].xyz.normalized() * arm.pose.bones[name].bone.length


def place(name, target):
    \"\"\"Move a control bone so its HEAD lands on `target` (world).\"\"\"
    m = world(name).copy()
    m.translation = target
    arm.pose.bones[name].matrix = arm.matrix_world.inverted() @ m
    bpy.context.view_layer.update()


done = []
for owner, chain in CHAINS.items():
    pb = arm.pose.bones.get(owner)
    con = pb.constraints.get("CTRL_IK") if pb else None
    if con is None:
        continue
    if SEL and not (SEL & set(chain + [con.subtarget, con.pole_subtarget])):
        continue

    if MODE == "GRAB":
        # Put BOTH handles where this pose already has them, then re-solve the pole angle.
        # The correct pole angle depends on the pose (the elbow plane differs from clip to clip),
        # so a single stored value cannot preserve every one -- measured, a value solved on a
        # crouch moved an aim pose's forearm 0.231 m. Re-solving here costs ~80 evaluations.
        # The bend plane is the one at the JOINT ABOVE the owner (elbow/knee), so the chain root
        # for that measurement is chain[-2] -- the upper arm or thigh -- not chain[0], which on a
        # 3-bone arm is the collarbone and would tilt the plane by the shoulder's own offset.
        root, elbow, tip = world(chain[-2]).translation, world(owner).translation, tail_of(owner)
        axis = tip - root
        if axis.length > 1e-6:                 # push the pole out along the way the joint bends
            along = (elbow - root).dot(axis.normalized())
            bend = elbow - (root + axis.normalized() * along)
        else:
            bend = Vector((0.0, 0.0, 0.0))
        if bend.length < 1e-4:                 # a straight limb has no plane; keep the pole put
            bend = (world(con.pole_subtarget).translation - elbow)
        reach = max(0.15, (tip - root).length * 0.6)
        place(con.pole_subtarget, elbow + bend.normalized() * reach)
        place(con.subtarget, tip)
        con.influence = 1.0
        bpy.context.view_layer.update()

        def miss(deg):
            con.pole_angle = radians(deg)
            bpy.context.view_layer.update()
            return (world(owner).translation - elbow).length
        best = min(((miss(d), d) for d in range(-180, 180, 5)), key=lambda t: t[0])
        best = min(((miss(d), d) for d in [best[1] + k for k in range(-5, 6)]), key=lambda t: t[0])
        con.pole_angle = radians(best[1])
        bpy.context.view_layer.update()
        done.append("%s (pole %+d, elbow %.4f m)" % (owner, best[1], best[0]))
    else:
        if con.influence <= 0.0:
            continue
        want = {b: world(b) for b in chain}    # read the IK result BEFORE switching it off
        con.influence = 0.0
        bpy.context.view_layer.update()
        for b in chain:                        # parents first: each is set in its final parent frame
            arm.pose.bones[b].matrix = arm.matrix_world.inverted() @ want[b]
            bpy.context.view_layer.update()
        arm.pose.bones[con.subtarget].matrix_basis.identity()
        arm.pose.bones[con.pole_subtarget].matrix_basis.identity()
        done.append(owner)

print("[snap] %s: %s" % (MODE, ", ".join(done) or "nothing matched"))
"""



def write_note(scale):
    t = bpy.data.texts.get(TEXT_BLOCK)
    if t is None:
        t = bpy.data.texts.new(TEXT_BLOCK)
    t.clear()
    t.write(NOTE + SNAP)


# ---------------------------------------------------------------- main

def main():
    a = args()
    arm = find_armature(a["armature"])
    bpy.context.view_layer.objects.active = arm
    arm.hide_set(False) if hasattr(arm, "hide_set") else None
    arm.select_set(True)

    # a body's own size, so the widgets and the pole reach suit a 1.49 m rig and a 1.91 m one alike
    pel = arm.data.bones.get("pelvis")
    scale = max(1e-3, (pel.head_local.z if pel else 1.0)) / 0.767
    log("%s: %d bones, scale %.3f vs the reference" % (arm.name, len(arm.data.bones), scale))

    acts = [x for x in (bpy.data.actions.get(n) for n in
                        ("upright_aim_rifle-loop", "upright_walk_forward-loop", "crouch_idle-loop"))
            if x is not None]
    if not acts:
        acts = sorted(bpy.data.actions, key=lambda x: x.name)[:3]
    # A body brought in from a .vrm carries NO clips at all (SKELETON_CONTRACT.md): there is then
    # no pose to disturb and nothing to solve a pole against. That is not an error -- GRAB re-solves
    # the pole angle per pose anyway, which is what makes the initial solve a convenience.
    log("reference clips: %s" % (", ".join(x.name for x in acts) if acts else "NONE (a body with no clips of its own)"))

    prev_action = arm.animation_data.action if arm.animation_data else None
    before = pose_signature(arm, acts) if acts else []

    made, moved = build_bones(arm, scale)
    build_constraints(arm)
    dress(arm, scale)
    write_note(scale)
    log("bones: %d created%s, %d updated" % (len(made), (" (%s)" % ", ".join(made)) if made else "", len(moved)))

    for L in LIMBS:
        act, frame, bend = most_bent(arm, L, acts)
        if act is None or bend > 172.0:
            log("%-13s NO BENT REFERENCE (best %.1f deg straight) -- pole angle left at 0"
                % (L["ctrl"], bend))
            continue
        angle, residual, tip_err = solve_pole(arm, L, act, frame)
        log("%-13s pole %+4d deg  (%s frame %d, bend %.1f deg)  elbow %.4f m  tip %.4f m"
            % (L["ctrl"], angle, act.name, frame, bend, residual, tip_err))
        if residual > POLE_TOLERANCE:
            log("%-13s WARNING: the solved plane is %.3f m off the posed elbow" % (L["ctrl"], residual))

    # THE FEATURE, measured rather than asserted from the constraint settings: pulling the hand
    # past the arm's reach must recruit the shoulder, and the shoulder must stop at the envelope.
    for L in LIMBS:
        if not L.get("shoulder") or not acts:
            continue
        act, frame, _ = most_bent(arm, L, acts)
        if act is None:
            continue
        for label, moved, miss in verify_shoulder(arm, L, act, frame):
            log("%-13s %-8s -> %s turned %5.1f deg (limit %.0f), hand %.3f m short"
                % (L["ctrl"], label, L["shoulder"], moved, CLAV_LIMIT_DEG, miss))
            if moved > CLAV_LIMIT_DEG + 1.0:
                raise SystemExit("[control-rig] FAILED: %s turned %.1f deg, past the %.0f deg envelope"
                                 % (L["shoulder"], moved, CLAV_LIMIT_DEG))
            if label == "reached" and moved < 1.0:
                raise SystemExit("[control-rig] FAILED: %s did not follow the hand past the arm's reach"
                                 % L["shoulder"])

    # the assertion this whole design rests on
    if acts:
        after = pose_signature(arm, acts)
        drift = compare(before, after)
        log("POSE UNCHANGED AT INFLUENCE 0: worst bone moved %.6f m over %d samples"
            % (drift, len(after)))
        if drift > 1e-5:
            raise SystemExit("[control-rig] FAILED: the control layer moved the rig by %.6f m" % drift)
    else:
        log("POSE UNCHANGED: no clips in this file to check against (influence is 0 regardless)")

    # the export rule: no active action, or it exports a second time (export_character.py)
    if arm.animation_data:
        arm.animation_data.action = prev_action
    bpy.context.scene.frame_set(int(bpy.context.scene.frame_start))

    dest = a["out"] or bpy.data.filepath
    if a["save"] or a["out"]:
        bpy.ops.wm.save_as_mainfile(filepath=dest)
        log("saved %s" % dest)
    else:
        log("NOT saved (pass --save, or --out=<path>)")


# Guarded so `fix_shoulder_overbend.py` can import the shoulder envelope and the evaluated-pose
# reading from here rather than keeping a second copy of either. Blender runs `--python <file>` with
# __name__ == "__main__", so the one-shot still runs exactly as before.
if __name__ == "__main__":
    main()
