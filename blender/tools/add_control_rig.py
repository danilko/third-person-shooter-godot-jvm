"""Add an IK CONTROL LAYER to a character .blend, so a pose is made by moving a hand or a foot.

    blender -b assets/characters/shino/shino.blend --python-exit-code 1 \
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

WHAT IT ADDS (nothing else) -- the FULL-BODY layer since PLAN.md 6.17:
  * FK: every contract bone (pelvis, spine, neck, head, collarbones, arms, legs, fingers, Root)
    wears a typed control SHAPE sized from its own skin. THE RINGS ARE THE DEFORM BONES: rotating
    one keys the bone the export writes, so FK needs no switch and no bake (see body_shapes)
  * IK, per limb, Rigify / Auto-Rig Pro style: CTRL_hand_* (cube) / CTRL_foot_* (sole outline) that
    move AND turn the hand/foot, CTRL_elbow_* / CTRL_knee_* poles, CTRL_root carrying them; a plain
    2-bone chain hanging from the FK collarbone (arm) or pelvis (leg), solved on a hidden joint-to-
    joint MCH chain because VRoid deform bones are disconnected (MCH_DOC)
  * one slider per limb, CTRL_root["ik_arm_l"] etc., stored at **0**, driving that limb's constraints
  * the sidebar (N-panel > Rig): per-limb "to IK" / "to FK" snaps and the collection toggles --
    `control_rig_ui.py`, written into the .blend as a registered text block AND imported by this
    script's self-test, so the buttons are the code that was measured
  * bone collections CTRL / Body / Fingers / Extras, a hidden MCH, Rigify's colours, drawn in front

**AN IK LIMB IGNORES ITS CLIP, SO EVERY SLIDER IS STORED AT 0.** At 0 the rig evaluates exactly as
before -- asserted here over 1422 samples -- and export_character.py refuses a file with a limb in IK.
The workflow is snap to IK, pose, snap to FK, key: the action then keys only the 53 contract bones.

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
UI_TEXT = "control_rig_ui.py"

# (control, chain tip bone, IK owner = last bone of the chain, pole, pole direction in BLENDER axes)
# The rig rests facing -Y with the left arm at +X (the contract), so "behind" is +Y and "in front"
# is -Y. That is an anatomical fact about a humanoid, and it is used rather than derived from the
# rest pose because a T-posed arm is STRAIGHT: shoulder, elbow and wrist are collinear there, so
# the bend plane cannot be measured from it at all.
LIMBS = [
    {"ctrl": "CTRL_hand_l", "tip": "hand_l", "owner": "lowerarm_l", "pole": "CTRL_elbow_l",
     "joint": "lowerarm_l", "dir": Vector((0.0, 1.0, 0.0)), "size": 0.09,
     "key": "arm_l", "base": "clavicle_l",
     "segs": [("upperarm_l", "lowerarm_l"), ("lowerarm_l", "hand_l")]},
    {"ctrl": "CTRL_hand_r", "tip": "hand_r", "owner": "lowerarm_r", "pole": "CTRL_elbow_r",
     "joint": "lowerarm_r", "dir": Vector((0.0, 1.0, 0.0)), "size": 0.09,
     "key": "arm_r", "base": "clavicle_r",
     "segs": [("upperarm_r", "lowerarm_r"), ("lowerarm_r", "hand_r")]},
    {"ctrl": "CTRL_foot_l", "tip": "foot_l", "owner": "calf_l", "pole": "CTRL_knee_l",
     "joint": "calf_l", "dir": Vector((0.0, -1.0, 0.0)), "size": 0.11, "key": "leg_l", "base": "pelvis",
     "segs": [("thigh_l", "calf_l"), ("calf_l", "foot_l")]},
    {"ctrl": "CTRL_foot_r", "tip": "foot_r", "owner": "calf_r", "pole": "CTRL_knee_r",
     "joint": "calf_r", "dir": Vector((0.0, -1.0, 0.0)), "size": 0.11, "key": "leg_r", "base": "pelvis",
     "segs": [("thigh_r", "calf_r"), ("calf_r", "foot_r")]},
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
    out = {"armature": ARM_DEFAULT, "save": False, "out": None, "remove": False,
           "hand_factor": HAND_WIDGET_FACTOR, "deform_shape": DEFORM_SHAPE_FRACTION}
    for a in argv:
        if a == "--save":
            out["save"] = True
        elif a == "--remove":
            out["remove"] = True
        elif a.startswith("--armature="):
            out["armature"] = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out["out"] = a.split("=", 1)[1]
        elif a.startswith("--hand-widget-factor="):
            out["hand_factor"] = float(a.split("=", 1)[1])
        elif a.startswith("--deform-shape="):
            out["deform_shape"] = float(a.split("=", 1)[1])
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


## A BONE IN NO COLLECTION CANNOT BE FILTERED (user, 2026-09-21: "hide the CTRL and then I see no
## bone at all"). This rig shipped with exactly ONE collection, `CTRL` (9 bones), and the other 158
## in none -- so the only thing an artist could switch off was the controls, and what is left is
## noisy: `Global`, `Root` and `Position` are 1.0 / 1.0 / 0.935 m bones drawn as OCTAHEDRA, i.e. a
## metre-wide glowing diamond over the whole model, plus ~100 VRoid spring bones (`J_Sec_*`).
## Three collections, so either half can be hidden:
##   CTRL   the 9 IK controls
##   Body   the 53 contract bones (SKELETON_CONTRACT.md) -- what you actually pose
##   Extras everything else: the oversized transform bones and the body's own secondaries
BODY_COLL, EXTRA_COLL = "Body", "Extras"


def contract_bones():
    """The 53 names, read from the contract record rather than copied into a second list."""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, "assets", "characters", "skeleton_rest.json")
    try:
        with open(path) as fh:
            names = set(json.load(fh)["rest"].keys())
        # `head_2` vs `head` is the one recorded name asymmetry across the seam (W40): the
        # reference .blend calls the bone `head`, and Godot's importer renamed it because a MESH
        # called `head` sits beside it -- so the contract record, dumped from the Godot side, says
        # `head_2`. Both spellings are the same contract bone.
        if "head_2" in names:
            names.add("head")
        return names
    except Exception as exc:                      # a checkout without the record still builds
        log("no contract record (%s); Body collection skipped" % exc)
        return set()


def sort_collections(arm):
    """File every bone into CTRL / Body / Extras. Idempotent; it never moves a CTRL bone."""
    d = arm.data
    have = {c.name: c for c in d.collections_all}
    for name in (BODY_COLL, EXTRA_COLL, FINGER_COLL, MCH_COLL):
        if name not in have:
            have[name] = d.collections.new(name)
    have[MCH_COLL].is_visible = False          # the solving chain is machinery: never grabbed
    contract = contract_bones()
    if not contract:
        return
    n_body = n_extra = 0
    for b in d.bones:
        if b.name.startswith("CTRL_"):
            continue
        if b.name.startswith(MCH):
            if b.name not in {x.name for x in have[MCH_COLL].bones}:
                have[MCH_COLL].assign(b)
            for c in (have[BODY_COLL], have[EXTRA_COLL], have[FINGER_COLL]):
                if b.name in {x.name for x in c.bones}:
                    c.unassign(b)
            continue
        # A bone is drawn while ANY of its collections is visible, so the three are a PARTITION:
        # fingers are in their own collection and not also in Body, or hiding Fingers would hide
        # nothing. Thirty finger rings crowd the hand the IK control sits on; hide them to grab it.
        if b.name not in contract:
            want = have[EXTRA_COLL]
        elif b.name.startswith(FINGERS):
            want = have[FINGER_COLL]
        else:
            want = have[BODY_COLL]
        for c in (have[BODY_COLL], have[EXTRA_COLL], have[FINGER_COLL]):
            if c is not want and b.name in {x.name for x in c.bones}:
                c.unassign(b)
        if b.name not in {x.name for x in want.bones}:
            want.assign(b)
        if want is have[BODY_COLL]:
            n_body += 1
        elif want is have[EXTRA_COLL]:
            n_extra += 1
    ctrl = next((c for c in d.collections_all if c.name == COLLECTION), None)
    log("bone collections: %s %d, %s %d, %s %d, %s %d"
        % (COLLECTION, len(ctrl.bones) if ctrl else 0, BODY_COLL, n_body,
           FINGER_COLL, len(have[FINGER_COLL].bones), EXTRA_COLL, n_extra))


## EVERY DEFORM BONE WORE A 19 cm SPHERE (user, 2026-09-21, with a picture: "the sphere control for
## bone is too large, cover entire hand models"). Measured: `Icosphere` -- a 2.0 m unit sphere -- is
## the custom shape on EVERY non-CTRL bone of all three bodies (158 / 53 / 117), scaled by a flat
## `custom_shape_scale_xyz` 0.08-0.10 with `use_custom_shape_bone_size` OFF, so it draws at a fixed
## 0.155-0.190 m whatever bone it is on. A finger bone is 0.020-0.037 m, i.e. the ball is ~7x the
## bone it marks and the hand disappears inside a cluster of them.
##
## The fix is the flag that already exists for exactly this: turn bone-size scaling back ON for
## those bones, so the sphere follows the bone it belongs to. Drawn = mesh(2.0) x length x scale, so
## the scale that draws a ball `DEFORM_SHAPE_FRACTION` of the bone's own length is that over 2.
## It is REVERSIBLE -- the Icosphere is untouched and only two per-bone display fields move -- and it
## is skipped entirely for a bone whose shape an artist has changed to something else.
## CAPPED AT BOTH ENDS, because "a fraction of the bone" alone swaps one absurdity for another: the
## transform bones `Root`, `Global` and `Position` are 0.935-1.0 m long, so half of that is a HALF
## METRE ball -- measured 0.500 m on Shino and 0.567 on Fumiriya on the first pass, worse than the
## flat 0.19 it replaced. A marker sphere says "a joint is here"; it is never large, and it must
## still be visible on a fingertip.
DEFORM_SHAPE_FRACTION = 0.5
DEFORM_SHAPE_MIN, DEFORM_SHAPE_MAX = 0.006, 0.060


def tidy_deform_shapes(arm, fraction):
    """Make each deform bone's marker sphere follow ITS OWN length instead of a flat 19 cm."""
    if fraction <= 0.0:                      # --deform-shape=0 clears them instead
        n = 0
        for pb in arm.pose.bones:
            if not pb.name.startswith("CTRL_") and pb.custom_shape is not None:
                pb.custom_shape = None
                n += 1
        log("deform bone shapes: cleared %d (bones draw as their own octahedra)" % n)
        return
    n, before, after = 0, [], []
    for pb in arm.pose.bones:
        if pb.name.startswith("CTRL_") or pb.custom_shape is None:
            continue
        if pb.custom_shape.name.startswith("WGT_"):   # a typed control shape (body_shapes), not a marker
            continue
        mesh = _shape_extent(pb.custom_shape)
        if mesh <= 0.0:
            continue
        L = arm.data.bones[pb.name].length
        was = mesh * (L if pb.use_custom_shape_bone_size else 1.0) * pb.custom_shape_scale_xyz[0]
        pb.use_custom_shape_bone_size = True
        want = min(max(fraction * L, DEFORM_SHAPE_MIN), DEFORM_SHAPE_MAX)
        k = want / (mesh * L)                # drawn = mesh * L * k = want
        pb.custom_shape_scale_xyz = (k, k, k)
        before.append(was)
        after.append(mesh * L * k)
        n += 1
    if n:
        log("deform bone shapes: %d re-sized to %.2f x their own bone (was %.3f-%.3f m flat, now %.3f-%.3f m)"
            % (n, fraction, min(before), max(before), min(after), max(after)))


def _shape_extent(ob):
    vs = [v.co for v in ob.data.vertices]
    return max(max(abs(v[i]) for v in vs) for i in range(3)) * 2 if vs else 0.0


def hand_span(arm, side):
    """Wrist to the furthest fingertip, on this rig. The one number a hand control should follow."""
    b = arm.data.bones
    wrist = b.get("hand_%s" % side)
    if wrist is None:
        return None
    far = 0.0
    for bone in b:
        if bone.name.endswith("_%s" % side) and bone.name.split("_")[0] in (
                "index", "middle", "ring", "pinky", "thumb"):
            far = max(far, (bone.tail_local - wrist.head_local).length)
    return far if far > 1e-4 else None


def _widget_mesh(name, kind, size):
    """The wire mesh itself. Split out so an existing widget can be re-sized in place."""
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
    return me


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
        # RE-SIZE an existing widget rather than hand it back as it is. It used to return early,
        # which meant a change to the sizes here reached a body that had never been built and no
        # other -- the widgets stayed at whatever the first run made them, which is half of why the
        # controls were reported as hard to see. An artist who has shaped their own widget keeps it:
        # only a mesh this function itself made (same vertex and edge count) is rebuilt.
        want = 8 if kind == "cube" else 6
        if len(ob.data.vertices) == want:
            # reassign FIRST: removing a mesh an object still points at invalidates the object
            # ("StructRNA of type Object has been removed" on the next line that touches it).
            stale = ob.data
            ob.data = _widget_mesh(name, kind, size)
            bpy.data.meshes.remove(stale)
        return ob
    me = _widget_mesh(name, kind, size)
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

    wanted = set()
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

        # THE SOLVING CHAIN, joint to joint (see MCH_DOC). Its segment k runs from deform bone k's
        # head to deform bone k+1's head, so its last tail IS the wrist / ankle and the IK target
        # (the control's head) is exactly where the hand is. The FOLLOWER under each segment carries
        # the deform bone's own rest frame, so copying it moves the deform bone without re-meaning a
        # single rotation.
        # THE SOLVING CHAIN (MCH_DOC): joint to joint, hanging from the FK collarbone (an arm) or the
        # pelvis (a leg), with a follower under each segment carrying the deform bone's own rest.
        parent = eb.get(L["base"])
        for k, (bone, nxt) in enumerate(L["segs"]):
            d, n = eb.get(bone), eb.get(nxt)
            m = ensure(MCH + bone)
            m.head, m.tail = d.head.copy(), n.head.copy()
            m.align_roll(d.z_axis)
            m.parent = parent
            m.use_connect = k > 0
            f = ensure(MCH_F + bone)
            f.head, f.tail, f.roll = d.head.copy(), d.tail.copy(), d.roll
            f.parent = m
            parent = m
            wanted.update((MCH + bone, MCH_F + bone))

    # a layer of an older shape (the two-stage arm: MCH_clavicle_*, MCH_P_*) leaves bones behind
    for b in [b for b in eb if b.name.startswith(MCH) and b.name not in wanted]:
        eb.remove(b)

    bpy.ops.object.mode_set(mode='OBJECT')
    return made, moved


MCH, MCH_F = "MCH_", "MCH_F_"
MCH_COLL = "MCH"
SOLVE_NAME = "CTRL_IK_SOLVE"
## MCH_DOC -- WHY THE IK SOLVES ON A SEPARATE CHAIN. A VRoid body's deform bones are DISCONNECTED and
## short: Shino's lowerarm is 0.066 m long against a 0.214 m elbow-to-wrist, so its TAIL is not the
## wrist. An IK on the deform forearm (use_tail) reaches the forearm's tail to the control, which put
## the hand 15 cm from the cube you grab. Blender's other answer, use_tail OFF on the hand, does not
## solve at all on this rig (0.15 m residual at every chain length, measured). So the IK solves on a
## hidden chain whose segments run JOINT TO JOINT (shoulder, elbow, wrist), and each deform bone
## copies a follower bone that rides that chain with the deform bone's own rest frame -- Rigify's
## MCH-*_ik shape. It touches no rest: the deform bones keep every roll and length they had.
##
## THE COLLARBONE IS NOT IN THE CHAIN, and it was, twice (user, 2026-09-21: "not as fluid as Auto-Rig
## Pro or Rigify ... barely impacts the arm/shoulder or controls in wacky ways"). Measured by dragging
## the hand control in 1 cm steps: an IK that may spend the collarbone spends ALL of it the moment the
## arm runs out -- 10 deg to its 60 deg limit between 10 and 20 cm of forward drag, the same pulling
## the hand DOWN -- while short of full reach it moved the shoulder 1-4 mm, i.e. not at all. Rigify and
## ARP keep the shoulder its own FK control and hang a 2-bone arm from it, and that is what this is:
## the clavicle ring poses the shoulder in IK mode too, the arm follows the hand, and a hand past the
## arm's reach stops short where you can see it.


def ik_con(arm, L):
    """The IK constraint of one limb -- on the solving chain's last segment."""
    pb = arm.pose.bones.get(MCH + L["segs"][-1][0])
    return pb.constraints.get(SOLVE_NAME) if pb is not None else None


def ik_prop(L):
    return "ik_" + L["key"]


def _drive(con, arm, L):
    """Make a constraint's influence its LIMB's IK slider (the one owner of 'is this limb IK')."""
    con.influence = 0.0
    try:
        con.driver_remove("influence")
    except Exception:
        pass
    d = con.driver_add("influence").driver
    d.type = 'AVERAGE'
    v = d.variables.new()
    v.name = "ik"
    v.type = 'SINGLE_PROP'
    v.targets[0].id = arm
    v.targets[0].data_path = 'pose.bones["CTRL_root"]["%s"]' % ik_prop(L)


def _strip(pb, name):
    con = pb.constraints.get(name)
    if con is not None:
        try:
            con.driver_remove("influence")
        except Exception:
            pass
        pb.constraints.remove(con)


def build_constraints(arm):
    """Per limb: the IK on the solving chain, and each deform bone copying its follower -- that copy
    is what the limb's slider drives, stored at 0. Idempotent; an older layer's pieces are replaced."""
    r = arm.pose.bones["CTRL_root"]
    if "ik" in r:                                  # the single switch of the previous layer
        del r["ik"]
    for L in LIMBS:
        prop = ik_prop(L)
        if prop not in r:
            r[prop] = 0.0
        r.id_properties_ui(prop).update(
            min=0.0, max=1.0, description="0 = the clip's own FK, 1 = this limb follows its IK control")
        _strip(arm.pose.bones[L["base"]], IK_NAME)   # the collarbone copied the solver before
        _strip(arm.pose.bones[L["tip"]], IK_NAME)    # a mid-6.17 layer put the IK on the hand
        for bone, _ in L["segs"]:
            dpb = arm.pose.bones[bone]
            con = dpb.constraints.get(IK_NAME)
            if con is not None and con.type != 'COPY_TRANSFORMS':   # an older layer's IK
                _strip(dpb, IK_NAME)
                con = None
            if con is None:
                con = dpb.constraints.new('COPY_TRANSFORMS')
                con.name = IK_NAME
            con.target = arm
            con.subtarget = MCH_F + bone
            con.target_space = 'WORLD'
            con.owner_space = 'WORLD'
            _drive(con, arm, L)
            dpb.ik_stretch = 0.0
            arm.pose.bones[MCH + bone].ik_stretch = 0.0
        last = arm.pose.bones[MCH + L["segs"][-1][0]]
        # the two-stage arm's pole-less reach lived here; with the collarbone out of the solving
        # chain its 3-bone count would reach THROUGH the parent into the real clavicle
        _strip(last, "CTRL_IK_REACH")
        con = last.constraints.get(SOLVE_NAME)
        if con is None:
            con = last.constraints.new('IK')
            con.name = SOLVE_NAME
        con.target = arm
        con.subtarget = L["ctrl"]
        con.pole_target = arm
        con.pole_subtarget = L["pole"]
        con.chain_count = len(L["segs"])
        con.use_tail = True
        con.use_stretch = False        # a game skeleton does not stretch; W25's Limit Scale reason
        con.influence = 1.0            # the chain is not a deform bone; the COPY above is the switch


## Widget sizes. The first set was derived from the bone and came out 6-11 cm on a 1.5 m body, which
## is a control an artist has to hunt for -- half the "the IK shape is not visible" report. These are
## the sizes a hand and a foot control are drawn at in Rigify and in every rig an animator is used to.
## The most a rotation inside a per-axis envelope can measure as a TOTAL: three axes at the limit.
MAX_TOTAL_DEG = 3 ** 0.5 * CLAV_LIMIT_DEG + 1.0

POLE_WIDGET = 0.10
WIDGET_GROW = 1.6

## THE HAND CONTROL IS SIZED FROM THE HAND, NOT FROM THE BODY (user, 2026-09-21: "make it smaller so
## I can see the model when tweaking fingers"). Every other widget is `size * WIDGET_GROW * scale`,
## and `scale` is the pelvis height -- which is right for a foot (a foot grows with the leg) and
## wrong for a hand, because a hand barely varies between bodies. Measured, wrist -> middle
## fingertip: Godot-chan 0.1616, Shino 0.1498, Fumiriya 0.1648 m -- within 10% of each other, while
## the widget they were given ran 0.144 / 0.176 / 0.213. So the cube was 0.89x the hand on the
## reference (fingers poke out, which is why it was never reported there) and 1.17x / 1.29x on the
## two VRoid bodies, i.e. the taller the body the bigger the box over the smaller hand.
## The factor reproduces the reference's own ratio, so it is unchanged there and only the bodies
## that were wrong move. `--hand-widget-factor=` takes it lower for finger work.
## AND THE DRAWN SIZE IS THE MESH SIZE, because `use_custom_shape_bone_size` is off (below).
## With it ON -- which is Blender's default and what this rig shipped with -- the shape is scaled by
## the BONE's length, and a CTRL bone is a stub: measured, `CTRL_hand_r` is 0.0191 m on Shino, so a
## 0.1348 m mesh DREW AT 2.6 mm. That is the whole of W48's "the IK shape is not visible", and W48's
## own fix (mesh 0.09 -> 0.144) moved the drawn control from 1.7 mm to 2.6 mm, which is why it did
## not help. Measured drawn sizes with bone-size on: hand 2.6 mm, pole 7.4 mm, foot 27 mm, root 45 mm.
HAND_WIDGET_FACTOR = 0.6

IK_PROP = "ik"


def set_ik(arm, value):
    """Every limb's IK slider at once (the per-limb writer is control_rig_ui.set_ik)."""
    for L in LIMBS:
        arm.pose.bones["CTRL_root"][ik_prop(L)] = float(value)
    bpy.context.evaluated_depsgraph_get().update()
    bpy.context.view_layer.update()


def ik_is_on(arm):
    r = arm.pose.bones.get("CTRL_root")
    return r is not None and any(float(r.get(ik_prop(L), 0.0)) > 0.0 for L in LIMBS)


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
    # NO TWIST. A collarbone rolling about its own length moves no joint -- the shoulder is on that
    # axis -- so twist is never what the solver needs, and it is exactly what the pole alignment
    # hands the chain's ROOT on a 3-bone arm: measured 133 deg of roll on clavicle_r with the axis
    # free, i.e. a shoulder wrung like a towel for a hand 4 cm out of reach.
    pb.lock_ik_y = True
    for axis in "xyz":
        setattr(pb, "ik_stiffness_%s" % axis, CLAV_STIFFNESS)
        setattr(pb, "use_ik_limit_%s" % axis, True)
        setattr(pb, "ik_min_%s" % axis, -lim)
        setattr(pb, "ik_max_%s" % axis, lim)


def dress(arm, scale, hand_factor=HAND_WIDGET_FACTOR):
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
        # A HAND follows the hand; a FOOT follows the body (see HAND_WIDGET_FACTOR).
        span = hand_span(arm, L["ctrl"][-1]) if L["ctrl"].startswith("CTRL_hand") else None
        w_size = span * hand_factor if span is not None else L["size"] * WIDGET_GROW * scale
        if span is not None:
            log("  %s widget %.4f m (hand span %.4f x %.2f)" % (L["ctrl"], w_size, span, hand_factor))
        sole = foot_sole(arm, L) if L["ctrl"].startswith("CTRL_foot") else None
        if sole is not None:
            pb.custom_shape = sole
        else:
            pb.custom_shape = widget("WGT_%s" % L["ctrl"], "cube", w_size)
        pb.custom_shape_translation = (0.0, 0.0, 0.0)
        pb.custom_shape_rotation_euler = (0.0, 0.0, 0.0)
        pb.custom_shape_scale_xyz = (1.0, 1.0, 1.0)
        pb.use_custom_shape_bone_size = False
        pb.bone.show_wire = True
        pp = arm.pose.bones[L["pole"]]
        pp.custom_shape = widget("WGT_pole", "diamond", POLE_WIDGET * scale)
        pp.use_custom_shape_bone_size = False
        pp.bone.show_wire = True
    r = arm.pose.bones["CTRL_root"]
    r.custom_shape = widget("WGT_root", "cube", 0.30 * scale)
    r.use_custom_shape_bone_size = False
    r.bone.show_wire = True


# ---------------------------------------------------------------- the full body (PLAN.md 6.17)

## THE FK CONTROLS ARE THE DEFORM BONES THEMSELVES, WEARING A SHAPE. The plan's first sketch was a
## `CTRL_` duplicate per bone driving the deform bone through COPY_TRANSFORMS, which is what ARP did
## -- and it buys nothing for an FK control while costing the two defects this file keeps fighting:
## a second owner of every rotation (the control's, and the clip's) and a switch that has to be at 0
## for the library to play. A spine, a neck, a head or a finger is posed by ROTATING it, and the
## rotation an artist keys should land on the bone the export writes. So those bones are simply given
## a shape an artist can see and grab, and the action keys exactly the 53 contract bones -- with no
## BAKE step, no influence, and nothing for `export_character.py`'s guard to refuse.
##
## Only a control that is a DIFFERENT THING from a bone needs a bone of its own: a hand or foot IK
## target (a point the chain reaches for), a pole (a direction), and the layer's root. Those are the
## nine `CTRL_` bones that already existed.
##
## Every ring is SIZED FROM THE SKIN weighted to its bone (the radius a percentile of how far that
## bone's vertices sit from its axis, plus a margin), so it hugs a slim wrist and a wide chest alike
## and moves with the body when the body changes -- the rule `hand_span()` set for the hand control.

# Where each FK ring sits: the bone's SEGMENT, i.e. from its head to the head of the bone it leads
# to. Measured on Shino the bone TAILS do not reach their children (upperarm 0.108 m long against a
# 0.219 m shoulder-to-elbow), so the bone's own length is the wrong span for a limb ring.
def _segment_end(b):
    n = b.name
    nxt = None
    for pre, succ in (("spine_01", "spine_02"), ("spine_02", "spine_03"), ("spine_03", "neck_01"),
                      ("neck_01", "head_2"), ("clavicle_", "upperarm_"), ("upperarm_", "lowerarm_"),
                      ("lowerarm_", "hand_"), ("hand_", "middle_01_"), ("thigh_", "calf_"),
                      ("calf_", "foot_"), ("foot_", "ball_")):
        if n.startswith(pre):
            nxt = succ + n[len(pre):] if pre.endswith("_") else succ
            break
    if nxt is None and n[:-3] in ("index_0", "middle_0", "ring_0", "pinky_0", "thumb_0"):
        i = int(n[-3])                                   # index_01_l -> index_02_l
        if i < 3:
            nxt = "%s%d%s" % (n[:-3], i + 1, n[-2:])
    if nxt == "head_2" and "head_2" not in b.id_data.bones:
        nxt = "head"
    c = b.id_data.bones.get(nxt) if nxt else None
    return c.head_local.copy() if c is not None else b.tail_local.copy()


FINGERS = ("index_", "middle_", "ring_", "pinky_", "thumb_")

# The shape each bone wears. A TYPE is something an artist should be able to tell at a glance, and
# they are told apart by FORM first and colour second (colour alone fails colour-blind, and fails in
# a greyscale viewport theme).
#   hips    a square around the pelvis, level with the floor -- moves the whole body (the COG)
#   ring    a circle round the limb or the spine segment
#   head    a circle with a nose tick, so which way the head faces is on the widget
#   finger  a small circle (the Fingers collection, hidden on its own)
#   floor   the contract `Root`: a square on the floor with an arrow, which is the STANCE drop bone
#           (it carries the crouch/crawl metres, W47) -- distinct from CTRL_root, a circle, which
#           only carries the IK controls
def shape_kind(name):
    if name == "pelvis":
        return "hips"
    if name == "Root":
        return "floor"
    if name in ("head", "head_2"):
        return "head"
    if name.startswith(FINGERS):
        return "finger"
    return "ring"


## COLOURS -- Rigify's convention, which is what an animator's eye already reads: the BODY'S LEFT
## blue, RIGHT red, the centre line yellow; the IK targets in the strong shade of their side, the FK
## rings in the light one, the poles purple, the layer's root green. Pose-bone colours, so the
## armature data (which a .vrm re-import rewrites) is not where they live.
PALETTE = {"ik_l": 'THEME04', "ik_r": 'THEME01', "fk_l": 'THEME07', "fk_r": 'THEME05',
           "mid": 'THEME09', "pole": 'THEME06', "root": 'THEME03'}


def _side(name):
    return "l" if name.endswith("_l") else ("r" if name.endswith("_r") else "")


def _ring_mesh(name, kind):
    """A unit wire shape whose PLANE NORMAL is mesh +Y and whose 'forward' tick is mesh -Z."""
    me = bpy.data.meshes.new(name)
    vs, es = [], []
    if kind in ("ring", "head", "finger", "circle"):
        n = 32 if kind != "finger" else 16
        vs = [(math.cos(2 * math.pi * i / n), 0.0, math.sin(2 * math.pi * i / n)) for i in range(n)]
        es = [(i, (i + 1) % n) for i in range(n)]
        if kind == "head":                     # the nose: a tick out of the ring toward -Z
            k = len(vs)
            vs += [(-0.25, 0.0, -1.0), (0.0, 0.0, -1.45), (0.25, 0.0, -1.0)]
            es += [(k, k + 1), (k + 1, k + 2)]
    else:                                      # hips / floor: a square, the floor one with an arrow
        vs = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
        es = [(0, 1), (1, 2), (2, 3), (3, 0)]
        if kind == "floor":
            vs += [(-0.35, 0, -1.0), (0.0, 0, -1.6), (0.35, 0, -1.0)]
            es += [(4, 5), (5, 6)]
    me.from_pydata(vs, es, [])
    me.update()
    return me


SOLE_MARGIN = 0.012


def foot_sole(arm, L):
    """The FOOT IK control is the outline of the SOLE, measured off this body's own foot.

    It was a cube sized from the pelvis height -- 0.21 m on Shino, a box that swallowed the whole
    foot and half the shin, so the control you grab hid the thing you were posing. A sole outline is
    what a foot control is in every rig an animator knows: flat on the ground plane, heel to toe,
    and it cannot be confused with the hand cube. Built in the control bone's own rest frame, so it
    needs no transform and follows the control when the foot is turned."""
    side = L["ctrl"][-1]
    pts = dominated_points(arm).get("foot_" + side, []) + dominated_points(arm).get("ball_" + side, [])
    if len(pts) < 8:
        return None
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    z = min(p.z for p in pts)
    x0, x1 = min(xs) - SOLE_MARGIN, max(xs) + SOLE_MARGIN
    y0, y1 = min(ys) - SOLE_MARGIN, max(ys) + SOLE_MARGIN
    to_bone = arm.data.bones[L["ctrl"]].matrix_local.inverted()
    # the toe end (-Y, the body's front) is drawn pointed, so which way the foot faces is on the shape
    tip = (x0 + x1) * 0.5
    ring = [(x0, y1), (x1, y1), (x1, y0 + 0.25 * (y1 - y0) * 0.3), (tip, y0), (x0, y0 + 0.25 * (y1 - y0) * 0.3)]
    vs = [to_bone @ Vector((x, y, z)) for x, y in ring]
    name = "WGT_%s" % L["ctrl"]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [(i, (i + 1) % len(vs)) for i in range(len(vs))], [])
    me.update()
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = widget(name, "cube", 0.1)
    if len(ob.data.vertices) in (8, len(vs)):       # ours (the old cube, or a sole): rebuild; else keep
        stale = ob.data
        ob.data = me
        bpy.data.meshes.remove(stale)
    else:
        bpy.data.meshes.remove(me)
    return ob


def shape_widget(kind):
    """One mesh per TYPE, shared by every bone of that type; each bone scales and places it."""
    name = "WGT_body_%s" % kind
    coll = bpy.data.collections.get(WIDGETS)
    if coll is None:
        coll = bpy.data.collections.new(WIDGETS)
        bpy.context.scene.collection.children.link(coll)
        coll.hide_viewport = True
        coll.hide_render = True
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, _ring_mesh(name, kind))
        coll.objects.link(ob)
        ob.hide_viewport = True
        ob.hide_render = True
    return ob


_DOMINATED = {}


def dominated_points(arm):
    """{bone: [rest-pose vertex, armature space]} for the vertices each bone carries MOST of.

    Only the body and face meshes -- VRoid hair cards stand 10-20 cm off the skull and would size
    the head ring round the hairstyle, not the head. Cached per armature for one run."""
    if arm.name in _DOMINATED:
        return _DOMINATED[arm.name]
    inv = arm.matrix_world.inverted()
    per = {}
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob.name.startswith("WGT_"):
            continue
        if not any(m.type == 'ARMATURE' and m.object == arm for m in ob.modifiers):
            continue
        if "hair" in ob.name.lower():
            continue
        names = [g.name for g in ob.vertex_groups]
        to_arm = inv @ ob.matrix_world
        for v in ob.data.vertices:
            best, w = None, 0.0
            for g in v.groups:
                if g.weight > w:
                    best, w = names[g.group], g.weight
            if best is not None and w >= 0.5:
                per.setdefault(best, []).append(to_arm @ v.co)
    _DOMINATED[arm.name] = per
    return per


def skin_radii(arm):
    """For every bone: (radial p85, axial median) of the vertices it DOMINATES, in armature space."""
    out = {}
    for bname, pts in dominated_points(arm).items():
        b = arm.data.bones.get(bname)
        if b is None or len(pts) < 4:
            continue
        a, e = b.head_local, _segment_end(b)
        ax = e - a
        L = ax.length
        if L < 1e-6:
            continue
        u = ax / L
        radial = sorted(((p - a) - u * (p - a).dot(u)).length for p in pts)
        axial = sorted((p - a).dot(u) / L for p in pts)
        if bname in ("head", "head_2"):
            # the HEAD ring goes round the skull, i.e. the middle of what the bone carries top to
            # bottom -- the median sat at the jaw, because a face mesh is dense round the mouth
            out[bname] = (radial[int(0.90 * (len(radial) - 1))], 0.5 * (axial[0] + axial[-1]))
            continue
        out[bname] = (radial[int(0.85 * (len(radial) - 1))], axial[len(axial) // 2])
    return out


def _frame_rotation(b, normal_arm):
    """The rotation (bone space) putting mesh +Y on `normal_arm` and mesh -Z toward the body's front.

    The body faces -Y in armature space (the contract), so 'front' is -Y projected off the normal;
    for a bone that itself runs front-to-back (a foot) the reference falls back to up."""
    to_bone = b.matrix_local.to_3x3().inverted()
    y = (to_bone @ normal_arm).normalized()
    for ref in (Vector((0.0, -1.0, 0.0)), Vector((0.0, 0.0, 1.0))):
        f = to_bone @ ref
        f = f - y * f.dot(y)
        if f.length > 0.2:
            break
    z = -f.normalized()
    x = y.cross(z).normalized()
    from mathutils import Matrix
    m = Matrix((x, y, z)).transposed()
    return m.to_euler('XYZ')


RING_MARGIN = 1.25           # the ring sits 25% outside the skin it is measured from
RING_MIN = {"finger": 0.006, "ring": 0.020}
RING_FALLBACK = {"finger": 0.010, "ring": 0.045, "head": 0.11, "hips": 0.16, "floor": 0.30}


def body_shapes(arm, scale):
    """Give every contract bone its typed shape, sized from the skin. Returns {kind: count}."""
    contract = contract_bones()
    radii = skin_radii(arm)
    icosphere = bpy.data.objects.get("Icosphere")
    counts = {}
    up = Vector((0.0, 0.0, 1.0))
    for pb in arm.pose.bones:
        b = pb.bone
        if b.name not in contract:
            continue
        # an artist's own shape is theirs; only a marker sphere, nothing, or one of ours is replaced
        cur = pb.custom_shape
        if cur is not None and cur is not icosphere and not cur.name.startswith("WGT_body_"):
            continue
        kind = shape_kind(b.name)
        a, e = b.head_local, _segment_end(b)
        seg = e - a
        rad, mid = radii.get(b.name, (None, 0.5))
        if kind in ("hips", "floor"):
            normal = up
            centre = a.copy() if kind == "hips" else Vector((a.x, a.y, 0.0))
            if kind == "hips":        # as wide as the hips: the thighs' own spread + their skin
                tl, tr = arm.data.bones.get("thigh_l"), arm.data.bones.get("thigh_r")
                r = (tl.head_local - tr.head_local).length * 0.5 if tl and tr else 0.0
                r += radii.get("thigh_l", (0.08,))[0] * RING_MARGIN
                size = max(r, RING_FALLBACK["hips"] * scale)
            else:
                size = RING_FALLBACK["floor"] * scale
        else:
            normal = seg.normalized() if seg.length > 1e-6 else up
            t = mid if kind in ("head", "finger") else min(max(mid, 0.25), 0.75)
            if b.name.startswith(("upperarm_", "thigh_")):
                t = 0.5                                   # a limb's ring belongs on the limb's middle
            centre = a + seg * t
            if rad is None:
                size = RING_FALLBACK[kind] * (1.0 if kind == "finger" else scale)
            else:
                size = max(rad * RING_MARGIN, RING_MIN.get(kind, 0.02))
        pb.custom_shape = shape_widget("circle" if kind == "ring" else kind)
        pb.use_custom_shape_bone_size = False
        pb.custom_shape_translation = b.matrix_local.inverted() @ centre
        pb.custom_shape_rotation_euler = _frame_rotation(b, normal)
        pb.custom_shape_scale_xyz = (size, size, size)
        if hasattr(pb, "custom_shape_wire_width"):
            pb.custom_shape_wire_width = 2.0
        side = _side(b.name)
        pb.color.palette = PALETTE["fk_" + side] if side else PALETTE["mid"]
        b.show_wire = True
        counts[kind] = counts.get(kind, 0) + 1
    # the IK layer, in the strong shades
    for L in LIMBS:
        side = L["ctrl"][-1]
        for n, key in ((L["ctrl"], "ik_" + side), (L["pole"], "pole")):
            pb = arm.pose.bones.get(n)
            if pb is not None:
                pb.color.palette = PALETTE[key]
                if hasattr(pb, "custom_shape_wire_width"):
                    pb.custom_shape_wire_width = 2.5
    r = arm.pose.bones.get("CTRL_root")
    if r is not None:
        # a CIRCLE on the floor, not the cube it was: the contract `Root` stands on the same spot
        # and wears a SQUARE, so the two roots differ in form, not only in colour
        r.custom_shape = shape_widget("circle")
        r.use_custom_shape_bone_size = False
        r.custom_shape_translation = (0.0, 0.0, 0.0)
        r.custom_shape_rotation_euler = _frame_rotation(r.bone, up)
        s = 0.45 * scale
        r.custom_shape_scale_xyz = (s, s, s)
        r.color.palette = PALETTE["root"]
    return counts


## THE HAND AND FOOT FOLLOW THEIR CONTROL'S ROTATION. The IK constraint puts the wrist and ankle on
## the control's HEAD; nothing turned the hand or foot with it, so rotating CTRL_hand_* did nothing
## at all -- a second shape of the "I grab it and nothing happens" report. A world-space
## COPY_ROTATION on the tip bone, driven by the same `ik` switch, so it is 0 whenever IK is.
ROT_NAME = "CTRL_IK_ROT"


def build_tip_rotation(arm):
    for L in LIMBS:
        pb = arm.pose.bones[L["tip"]]
        con = pb.constraints.get(ROT_NAME)
        if con is None:
            con = pb.constraints.new('COPY_ROTATION')
            con.name = ROT_NAME
        con.target = arm
        con.subtarget = L["ctrl"]
        con.target_space = 'WORLD'
        con.owner_space = 'WORLD'
        con.mix_mode = 'REPLACE'
        _drive(con, arm, L)


FINGER_COLL = "Fingers"


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
    b = wpos(arm, L["tip"]) - wpos(arm, L["owner"])
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


def _ui():
    """The sidebar module, imported: its snaps are the ones this script measures (one owner)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import control_rig_ui
    return control_rig_ui


def solve_pole(arm, L, act, frame):
    """Find the limb's pole ANGLE: the one that leaves the posed elbow where it is on switch-on.

    For a 2-bone chain it is a constant of the rig (it relates the solving bones' roll to the bend
    plane), so it is solved ONCE here and stored; the snap only places the pole along the bend. It is
    measured rather than written down because the roll is per body."""
    ui = _ui()
    apply_action(arm, act, frame)
    arm.animation_data.action = None
    bpy.context.view_layer.update()
    want_joint = wpos(arm, L["owner"])
    ui.to_ik(arm, L["key"])
    con = ik_con(arm, L)

    def err(angle):
        con.pole_angle = math.radians(angle)
        bpy.context.view_layer.update()
        return (wpos(arm, L["owner"]) - want_joint).length

    best = min(((err(a), a) for a in range(-180, 180, 5)), key=lambda t: t[0])
    best = min(((err(a), a) for a in [best[1] + d * 0.5 for d in range(-10, 11)]), key=lambda t: t[0])
    con.pole_angle = math.radians(best[1])
    bpy.context.view_layer.update()
    tip_err = (wpos(arm, L["tip"]) - (arm.matrix_world @ arm.pose.bones[L["ctrl"]].matrix).translation).length
    ui.set_ik(arm, L["key"], 0.0)
    return best[1], best[0], tip_err


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


def clavicle_axes_deg(arm, name):
    """The same channel, PER AXIS -- which is what the IK envelope actually bounds.

    `shoulder_limits` sets `ik_min/max_{x,y,z}` to +-CLAV_LIMIT_DEG, i.e. a limit on each local axis
    INDEPENDENTLY. The total magnitude `clavicle_deg` returns is a different quantity and can reach
    sqrt(3) x the limit (~104 deg at 60) with every axis legal -- so asserting the total against the
    per-axis number compares two things that are not the same, and it passed only while the left arm
    happened to land near 60. Measured the day the IK first solved properly: left 60.1 (passed),
    right 98.7 (failed), with both arms inside their envelopes on every axis.
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
    e = here.to_euler('XYZ')
    return [abs(math.degrees(a)) for a in (e.x, e.y, e.z)]


DRAG_PATHS = {"forward": (0, -1, 0), "back": (0, 1, 0), "up": (0, 0, 1), "down": (0, 0, -1),
              "out": (1, 0, 0), "in": (-1, 0, 0)}
DRAG_STEP, DRAG_STEPS = 0.01, 15          # 1 cm steps, 15 cm each way: inside the arm's reach
DRAG_JUMP_DEG = 12.0                      # no bone may turn more than this for 1 cm of drag
DRAG_REACH_MM = 1.0


def verify_drag(arm, L, act, frame):
    """Drag the IK control the way an artist does and measure what the limb does.

    This is the test the previous layer did not have and failed in the hand (user, 2026-09-21): the
    hand must FOLLOW the control, every step must be SMOOTH (no bone turns more than DRAG_JUMP_DEG for
    a centimetre of drag -- a flip or a snap is exactly that), and the shoulder must NOT MOVE (it is
    FK now; the old reach stage slammed it from 10 to 60 deg). Returns per-path numbers."""
    ui = _ui()
    apply_action(arm, act, frame)
    arm.animation_data.action = None
    bpy.context.view_layer.update()
    snap = ui.to_ik(arm, L["key"])
    ctrl = arm.pose.bones[L["ctrl"]]
    start = ctrl.matrix.copy()
    watch = [L["base"]] + [b for b, _ in L["segs"]] + [L["tip"]]
    sh0 = wpos(arm, L["segs"][0][0])
    b = arm.data.bones
    reach = ((b[L["segs"][0][0]].head_local - b[L["segs"][1][0]].head_local).length
             + (b[L["segs"][1][0]].head_local - b[L["tip"]].head_local).length)
    out = []
    for name, d in DRAG_PATHS.items():
        ctrl.matrix = start
        bpy.context.view_layer.update()
        prev = {b: ui.world(arm, b).to_quaternion() for b in watch}
        jump, miss, where = 0.0, 0.0, ""
        for k in range(1, DRAG_STEPS + 1):
            m = start.copy()
            m.translation = start.translation + arm.matrix_world.inverted().to_3x3() @ (Vector(d) * DRAG_STEP * k)
            ctrl.matrix = m
            bpy.context.view_layer.update()
            for b in watch:
                q = ui.world(arm, b).to_quaternion()
                a = math.degrees(q.rotation_difference(prev[b]).angle)
                a = min(a, 360.0 - a)                  # q and -q are one rotation
                if a > jump:
                    jump, where = a, "%s@%dcm" % (b, k)
                prev[b] = q
            target = (arm.matrix_world @ ctrl.matrix).translation
            # judged only where the limb CAN reach: past that it stops short on purpose
            if (target - wpos(arm, L["segs"][0][0])).length < reach - 0.002:
                miss = max(miss, (wpos(arm, L["tip"]) - target).length)
        out.append((name, jump, where, miss, (wpos(arm, L["segs"][0][0]) - sh0).length))
    ctrl.matrix = start
    bpy.context.view_layer.update()
    back = ui.to_fk(arm, L["key"])
    return out, back, snap


def pose_signature(arm, actions):
    """Every contract bone's world head over a few frames -- the thing that must NOT change."""
    sig = []
    for act in actions:
        lo, hi = act.frame_range
        for f in (int(lo), int((lo + hi) / 2), int(hi)):
            apply_action(arm, act, f)
            for b in sorted(arm.pose.bones.keys()):
                if b.startswith(("CTRL_", MCH)):
                    continue
                sig.append(wpos(arm, b).copy())
    return sig


def compare(a, b):
    return max((x - y).length for x, y in zip(a, b)) if a and len(a) == len(b) else float("inf")


# ---------------------------------------------------------------- the text block

NOTE = '''\
CONTROLS -- added by blender/tools/add_control_rig.py. Re-run that script; do not hand-build.

THE BUTTONS ARE IN THE SIDEBAR: N-panel > "Rig" tab (select the armature). If the tab is missing,
allow this file's scripts when Blender asks, or open the text `control_rig_ui.py` and Run Script.

WHAT YOU GRAB (colour: body's LEFT blue, RIGHT red, centre yellow; IK strong, FK light)
  square round the hips   pelvis      the COG -- moves and turns the whole body
  rings on the spine      spine_01..03  bend the torso; the arms and head ride it
  rings on neck / head    neck_01, head (the head ring has a nose tick: it shows the facing)
  ring on each collarbone clavicle    THE SHOULDER. It is FK in IK mode too: shrug / reach with it
  rings on arms and legs  upperarm, lowerarm, hand, thigh, calf, foot (FK mode), ball (toe bend)
  small rings on fingers  30, in their own `Fingers` collection -- hide it to reach the hand
  square with an arrow    Root        the STANCE bone (it carries the crouch/crawl drop). Rarely touched.
  cube / sole outline     CTRL_hand_* / CTRL_foot_*   IK: move AND turn the hand/foot, the limb follows
  diamonds                CTRL_elbow_* / CTRL_knee_*  which way the elbow/knee points
  green circle on floor   CTRL_root   carries the IK controls

THE WORKFLOW, per limb (Rigify / Auto-Rig Pro style)
  1. "to IK": the controls jump onto the limb as it is posed, the limb switches to IK. Nothing moves.
  2. move / turn the cube or sole, drag the diamond for the elbow/knee, rotate the collarbone ring
     for the shoulder. A hand pulled past the arm's reach stops short -- move the shoulder instead.
  3. "to FK": the limb keeps the pose, as ordinary rotations on its own bones, and leaves IK.
  4. key the bones as usual. (With auto-keying on, step 3 keys the limb for you.)

EVERY IK SLIDER MUST BE 0 TO EXPORT OR TO PLAY THE CLIPS. An IK limb ignores its clip -- right while
posing, wrong while playing -- and export_character.py refuses a file with a limb left in IK.
The FK rings (spine, head, fingers, collarbones) never need a switch: they ARE the exported bones.
'''


def write_note(scale):
    t = bpy.data.texts.get(TEXT_BLOCK)
    if t is None:
        t = bpy.data.texts.new(TEXT_BLOCK)
    t.clear()
    t.write(NOTE)
    # the sidebar: the SAME file this script imports for its self-test, registered on load
    ui = bpy.data.texts.get(UI_TEXT)
    if ui is None:
        ui = bpy.data.texts.new(UI_TEXT)
    ui.clear()
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), UI_TEXT)) as fh:
        ui.write(fh.read())
    ui.use_module = True


def remove_layer(arm):
    """Take the hand-made CTRL layer back out -- every piece this script added, and nothing else.

    It exists for the body that has adopted a REAL control rig (Auto-Rig Pro, Rigify). Two control
    rigs in one file is worse than none: ARP's `c_hand_ik.l` and our `CTRL_hand_l` are drawn at the
    same place on the same hand, and ours is stored at influence 0 BY DESIGN (see `master_switch`),
    so the artist grabs whichever is on top and half the time nothing happens -- which is the very
    report the CTRL layer was built to answer, now caused by it. Reported on Shino after her Quick
    Rig: "the hand control ... when move them, nothing happen ... rest seem work pretty well".

    The deform bones, their constraints from any other source, the clips and the pose are untouched,
    and the caller asserts that: the removal must move the rig by 0.
    """
    removed = {"bones": [], "constraints": [], "widgets": [], "collections": []}
    # constraints + their drivers first: a driver whose target bone is gone is a broken driver
    # every deform bone a layer of any vintage put CTRL_IK on: the chain bones (COPY_TRANSFORMS since
    # 6.17, an IK before it) and the hand/foot (a mid-6.17 layer)
    for bone in {b for L in LIMBS for b in [s for s, _ in L["segs"]] + [L["tip"], L["base"]]}:
        pb = arm.pose.bones.get(bone)
        if pb is None:
            continue
        con = pb.constraints.get(IK_NAME)
        if con is not None:
            try:
                con.driver_remove("influence")
            except Exception:
                pass
            pb.constraints.remove(con)
            removed["constraints"].append("%s/%s" % (pb.name, IK_NAME))
    for L in LIMBS:
        pb = arm.pose.bones.get(L["tip"])
        con = pb.constraints.get(ROT_NAME) if pb is not None else None
        if con is not None:
            try:
                con.driver_remove("influence")
            except Exception:
                pass
            pb.constraints.remove(con)
            removed["constraints"].append("%s/%s" % (pb.name, ROT_NAME))
    # the typed body shapes go back to the marker sphere they replaced
    ico = bpy.data.objects.get("Icosphere")
    for pb in arm.pose.bones:
        if pb.custom_shape is not None and pb.custom_shape.name.startswith("WGT_body_"):
            pb.custom_shape = ico
            pb.custom_shape_translation = (0.0, 0.0, 0.0)
            pb.custom_shape_rotation_euler = (0.0, 0.0, 0.0)
            pb.color.palette = 'DEFAULT'
    r = arm.pose.bones.get("CTRL_root")
    for key in [IK_PROP] + [ik_prop(L) for L in LIMBS]:
        if r is not None and key in r:
            del r[key]

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in [b for b in arm.data.edit_bones if b.name.startswith(("CTRL_", MCH))]:
        removed["bones"].append(eb.name)
        arm.data.edit_bones.remove(eb)
    bpy.ops.object.mode_set(mode='OBJECT')

    for c in list(arm.data.collections_all):
        if c.name in (COLLECTION, FINGER_COLL, MCH_COLL):
            removed["collections"].append(c.name)
            arm.data.collections.remove(c)

    # by NAME, not by user count: a datablock's users are not re-counted until the depsgraph runs,
    # so "unused now" is not yet true on the line after the bones went.
    ours = {"WGT_pole", "WGT_root"} | {"WGT_%s" % L["ctrl"] for L in LIMBS}
    for ob in [o for o in bpy.data.objects if o.name in ours or o.name.startswith("WGT_body_")]:
        removed["widgets"].append(ob.name)
        bpy.data.objects.remove(ob, do_unlink=True)

    for name in (TEXT_BLOCK, UI_TEXT):
        t = bpy.data.texts.get(name)
        if t is not None:
            bpy.data.texts.remove(t)
    return removed


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

    if a["remove"]:
        gone = remove_layer(arm)
        for k in ("bones", "constraints", "collections", "widgets"):
            log("removed %-12s %d%s" % (k, len(gone[k]), (" (%s)" % ", ".join(gone[k])) if gone[k] else ""))
        if acts:
            worst = compare(before, pose_signature(arm, acts))
            log("pose after removal: worst bone moved %.6f m over %d samples" % (worst, len(before)))
            if worst > 1e-5:
                raise SystemExit("[control-rig] REFUSED: removing the layer moved the rig %.6f m" % worst)
        if arm.animation_data:
            arm.animation_data.action = prev_action
        dest = a["out"] or bpy.data.filepath
        if (a["save"] or a["out"]) and dest:
            bpy.ops.wm.save_as_mainfile(filepath=dest)
            log("saved %s" % dest)
        else:
            log("NOT saved (pass --save)")
        return

    made, moved = build_bones(arm, scale)
    build_constraints(arm)
    build_tip_rotation(arm)
    dress(arm, scale, a["hand_factor"])
    sort_collections(arm)
    tidy_deform_shapes(arm, a["deform_shape"])
    counts = body_shapes(arm, scale)
    # The controls draw IN FRONT of the mesh: a ring round a thigh sits under a VRoid skirt and one
    # round the head inside the hair, and a control you cannot see is a control you cannot grab.
    arm.show_in_front = True
    log("body shapes: %s" % ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    write_note(scale)
    log("bones: %d created%s, %d updated" % (len(made), (" (%s)" % ", ".join(made)) if made else "", len(moved)))

    for L in LIMBS:
        act, frame, bend = most_bent(arm, L, acts)
        if act is None or bend > 172.0:
            log("%-13s NO BENT REFERENCE (best %.1f deg straight) -- pole angle left at 0"
                % (L["ctrl"], bend))
            continue
        angle, residual, tip_err = solve_pole(arm, L, act, frame)
        log("%-13s pole %+6.1f deg  (%s frame %d, bend %.1f deg)  elbow %.4f m  tip %.4f m"
            % (L["ctrl"], angle, act.name, frame, bend, residual, tip_err))
        if residual > POLE_TOLERANCE:
            log("%-13s WARNING: the solved plane is %.3f m off the posed elbow" % (L["ctrl"], residual))

    # THE FEEL, measured the way it is used: snap to IK on a pose, drag each control 15 cm six ways
    # in 1 cm steps, snap back to FK. See verify_drag for what each number means.
    for L in LIMBS:
        if not acts:
            break
        act, frame, _ = most_bent(arm, L, acts)
        if act is None:
            continue
        paths, back, snap = verify_drag(arm, L, act, frame)
        worst = max(paths, key=lambda t: t[1])
        miss = max(t[3] for t in paths)
        shoulder = max(t[4] for t in paths)
        log("%-13s to IK moved the joint %.4f m / the tip %.4f m; drag: worst step %4.1f deg (%s %s), "
            "tip off its control %.4f m, shoulder moved %.4f m; to FK left the limb %.4f m off"
            % (L["ctrl"], snap[0], snap[1], worst[1], worst[0], worst[2], miss, shoulder, back))
        if (worst[1] > DRAG_JUMP_DEG or miss > DRAG_REACH_MM / 1000.0 or shoulder > 1e-4 or back > 1e-3
                or snap[0] > POLE_TOLERANCE or snap[1] > 1e-3):
            raise SystemExit("[control-rig] FAILED: %s does not drag cleanly" % L["ctrl"])
        set_ik(arm, 0.0)
        for pb in arm.pose.bones:                 # leave no test pose on the controls
            if pb.name.startswith(("CTRL_", MCH)):
                pb.matrix_basis.identity()
        bpy.context.view_layer.update()

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
