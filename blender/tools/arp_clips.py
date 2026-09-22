"""Clips that live on the Auto-Rig Pro controls, and the bake that turns them back into game clips.

PLAN.md 6.17. The game reads 53 bones' keys; an artist wants to key ARP's IK controls. This module is
the bridge, one owner for both directions, used by the sidebar (game_export_ui.py) and headless:

  move_to_arp(clip, to_ik)   copy game clip `<clip>` onto ARP's controls as action `ARP_<clip>`.
                             Transferred in FK, which is EXACT (0.00 deg measured); `to_ik` then snaps
                             every limb to IK over the clip with ARP's own bake -- joints stay within
                             millimetres but the limb TWIST can change (13-70 deg measured), so look.
  bake_to_game(clip)         sample the body as ARP poses it and write that into the game action
                             `<clip>` -- same datablock, same NLA track, same interpolation per curve.
                             Bones ARP does not drive (`Root`, the stance drop) keep their own keys.
  bake_all()                 every `ARP_*` action; the Export button runs this first. A clip whose rig
                             action AND game action are both unchanged since its last bake is skipped
                             (the digests ride on the `ARP_` action), so an export stays fast with every
                             clip on the rig.
  move_all()                 every game clip not yet on the rig, in FK, each proved by an unedited bake
                             that must write 0 keys (2026-09-21: the whole library lives on the rig).
  new_clip(name, f0, f1)     a clip that exists only on the rig; its game action is CREATED by the bake.

THE `ARP_` PREFIX IS INTERNAL. The sidebar lists clips by their plain name; an artist picks one and edits
it on the rig. The game action `<clip>` is derived at export and is never edited by hand: a channel that
differs from the rig is overwritten by the rig's. Delete `ARP_<clip>` and the game action is what it was
at the last bake.

    blender -b shino.blend --python blender/tools/arp_clips.py -- move <clip> [--ik] [--save]
    blender -b shino.blend --python blender/tools/arp_clips.py -- move-all [--save]
    blender -b shino.blend --python blender/tools/arp_clips.py -- bake [<clip>] [--force] [--save]
"""
import hashlib
import math
import sys
import time
import types

import bpy

PREFIX = "ARP_"
# limb segments whose ROLL comes from the clip, not the IK (see bake_to_game), and the IK tips
TWIST_FROM_CLIP = {"upperarm_l": "lowerarm_l", "lowerarm_l": "hand_l", "upperarm_r": "lowerarm_r",
                   "lowerarm_r": "hand_r", "thigh_l": "calf_l", "calf_l": "foot_l", "thigh_r": "calf_r",
                   "calf_r": "foot_r"}                # segment -> the joint it ends at
TIPS = {"hand_l", "hand_r", "foot_l", "foot_r"}
TRANSLATES = {"Root", "pelvis"}  # build_character_anims.TRANSLATING_BONES: the only bones whose position ships
BAKE_TOLERANCE = 5e-4        # ~0.03 deg / 0.5 mm: the FK transfer's own float noise is 2e-4, measured
SWITCH = "drive_game_rig"


def rigs():
    rig = next((o for o in bpy.data.objects if o.type == 'ARMATURE' and "arp_rig_type" in o.keys()), None)
    game = next((o for o in bpy.data.objects if o.type == 'ARMATURE' and o is not rig
                 and not o.name.endswith("_ANIM_TEMP")), None)
    if rig is None or game is None:
        raise RuntimeError("needs an Auto-Rig Pro rig and the game armature in this file")
    return rig, game


def _bind(ob, act):
    ob.animation_data_create()
    ob.animation_data.action = act
    if act is not None and act.slots:
        ob.animation_data.action_slot = act.slots[0]


def _drive(rig, value):
    rig.pose.bones["c_pos"][SWITCH] = float(value)
    # tag + depsgraph update: re-setting (or stepping) the frame did NOT re-evaluate the switch drivers in
    # every file -- measured, all 312 influences stayed 1.0 and the export was refused
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            ob.update_tag(refresh={'OBJECT', 'DATA'})
    bpy.context.evaluated_depsgraph_get().update()
    sc = bpy.context.scene
    sc.frame_set(sc.frame_current)


def _fcurves(act):
    if getattr(act, "layers", None):
        return [c for l in act.layers for s in l.strips for cb in s.channelbags for c in cb.fcurves]
    return list(act.fcurves)


def strip_switch_keys():
    """THE SWITCH IS NEVER ANIMATION. Keying "everything" on the rig (Insert Keyframe on all, or auto-key)
    keys `c_pos["drive_game_rig"]` too, and then every frame evaluation puts it back: measured, the
    export set it to 0, the clip's key put it straight back to 1, all 312 constraints stayed live and
    the export was refused. Removes that curve from every ARP clip. Returns how many were removed."""
    n = 0
    for a in bpy.data.actions:
        if not a.name.startswith(PREFIX):
            continue
        for l in getattr(a, "layers", []) or []:
            for st in l.strips:
                for cb in st.channelbags:
                    for fc in [c for c in cb.fcurves if SWITCH in c.data_path]:
                        cb.fcurves.remove(fc)
                        n += 1
        if not getattr(a, "layers", None):
            for fc in [c for c in a.fcurves if SWITCH in c.data_path]:
                a.fcurves.remove(fc)
                n += 1
    return n


def _qr_module():
    cls = getattr(bpy.types, "ARP_OT_quick_make_rig", None)
    if cls is None:
        raise RuntimeError("Auto-Rig Pro Quick Rig is not enabled")
    return sys.modules[cls.__module__], cls


def move_to_arp(clip, to_ik=False):
    """Copy game clip `clip` onto the ARP controls as `ARP_<clip>`. Returns the action."""
    rig, game = rigs()
    act = bpy.data.actions[clip]
    mod, cls = _qr_module()
    sc = bpy.context.scene
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    keep = (sc.frame_start, sc.frame_end, sc.frame_current, game.animation_data.action if game.animation_data else None,
            rig.animation_data.action if rig.animation_data else None, rig.pose.bones["c_pos"].get(SWITCH, 0.0))
    sc.frame_start, sc.frame_end = f0, f1

    # the retarget source: a constraint-free copy of the game armature carrying the clip
    src = game.copy()
    src.name = src_name = game.name + "_ANIM_TEMP"
    sc.collection.objects.link(src)
    if src.animation_data:
        for fc in list(src.animation_data.drivers):
            src.animation_data.drivers.remove(fc)
        while src.animation_data.nla_tracks:
            src.animation_data.nla_tracks.remove(src.animation_data.nla_tracks[0])
    for pb in src.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    _bind(src, act)
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)

    # Quick Rig's own retarget (the ANIM_BAKE path of its Make Rig), in FK: FK is exact, IK guesses the
    # pole (measured 70 deg). The per-build maps are empty here: fingers and hair are orphan `cc` bones.
    vals = dict(source_anim_rig_name=src.name, arp_armature_name=rig.name, animation='ANIM_BAKE',
                arm_ik_fk='FK', leg_ik_fk='FK', mode='PRESERVE', orphan_bones_loc_retarget='IK',
                fingers_ctrl={}, toes_ctrl={}, tail_ctrl={}, spline_ctrl={},
                match_to_rig=True, remove_root=True, neck_auto_twist=False)
    existing = {a.name for a in bpy.data.actions}
    mod._remap_animation(types.SimpleNamespace(**vals))
    if src_name in bpy.data.objects:                  # the retarget normally deletes it itself
        bpy.data.objects.remove(bpy.data.objects[src_name], do_unlink=True)

    new = rig.animation_data.action
    old = bpy.data.actions.get(PREFIX + clip)
    if old is not None and old is not new:
        bpy.data.actions.remove(old)
    new.name = PREFIX + clip
    new.use_fake_user = True
    # the retarget leaves a scratch action behind (`rigAction`); nothing uses it
    for a in [a for a in bpy.data.actions if a.name not in existing and a is not new]:
        bpy.data.actions.remove(a)
    if to_ik:
        to_ik_over_range(rig, f0, f1)
    strip_switch_keys()
    sc.frame_start, sc.frame_end = keep[0], keep[1]
    _bind(game, keep[3])
    sc.frame_set(keep[2])
    return new


def to_ik_over_range(rig, f0, f1):
    """Every limb FK -> IK over the range with ARP's bake ("snap IK to FK": the IK controls take the
    FK pose, the limb is left in IK). The *_fk_to_ik pair is the opposite direction."""
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for side in (".l", ".r"):
        for op, b in ((bpy.ops.pose.arp_bake_arm_ik_to_fk, "c_hand_ik"),
                      (bpy.ops.pose.arp_bake_leg_ik_to_fk, "c_foot_ik")):
            for pb in rig.pose.bones:
                pb.select = False
            rig.pose.bones[b + side].select = True
            rig.data.bones.active = rig.data.bones[b + side]
            op('EXEC_DEFAULT', side=side, get_sel_side=False, multi_select=False,
               frame_start=f0, frame_end=f1, one_key_per_frame=True, get_action_range=False)
    bpy.ops.object.mode_set(mode='OBJECT')


def _digest(act):
    """What an action's KEYS say, and nothing else (a custom property or the fake user does not count)."""
    h = hashlib.sha1()
    for fc in sorted(_fcurves(act), key=lambda c: (c.data_path, c.array_index)):
        h.update(("%s[%d]" % (fc.data_path, fc.array_index)).encode())
        for k in fc.keyframe_points:
            h.update(("%.6g %.6g %s %.6g %.6g %.6g %.6g;" % (
                k.co[0], k.co[1], k.interpolation, k.handle_left[0], k.handle_left[1],
                k.handle_right[0], k.handle_right[1])).encode())
    return h.hexdigest()[:16]


BAKED_KEY = "game_bake"      # on the ARP_ action: "<rig digest>:<game digest>" as of the last bake


def _ensure_game_action(clip, src, game):
    """A clip made on the rig has no game action yet: create one the exporter will pick up -- one NLA
    track named after it, like every other clip -- with every rig-driven bone at its rest pose. The bake
    then keys whatever the rig moves."""
    act = bpy.data.actions.get(clip)
    if act is not None:
        return act
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and "arp_rig_type" in o.keys())
    act = bpy.data.actions.new(clip)
    keep = game.animation_data.action if game.animation_data else None
    _bind(game, act)
    f0 = int(round(src.frame_range[0]))
    rest = {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0)}
    for pb in game.pose.bones:
        if not any(getattr(c, "target", None) is rig for c in pb.constraints):
            continue
        for prop, vals in rest.items():
            for i, v in enumerate(vals):
                fc = act.fcurve_ensure_for_datablock(game, 'pose.bones["%s"].%s' % (pb.name, prop), index=i)
                fc.keyframe_points.insert(f0, v, options={'FAST'})
    _bind(game, keep)
    tracks = game.animation_data.nla_tracks
    like = tracks[0] if len(tracks) else None
    tr = tracks.new()
    tr.name = clip
    st = tr.strips.new(clip, f0, act)
    st.extrapolation = 'HOLD'
    if like is not None:
        tr.mute = like.mute
    return act


def bake_to_game(clip, force=False):
    """Write the body, as `ARP_<clip>` poses it, into the game action `clip`. Returns keys written, or -1
    when both actions are unchanged since the last bake and it was skipped (`force` bakes anyway)."""
    rig, game = rigs()
    src = bpy.data.actions[PREFIX + clip]
    created = bpy.data.actions.get(clip) is None
    act = _ensure_game_action(clip, src, game)
    if not force and not created and src.get(BAKED_KEY) == "%s:%s" % (_digest(src), _digest(act)):
        return -1
    sc = bpy.context.scene
    keep = (sc.frame_current, game.animation_data.action if game.animation_data else None,
            rig.animation_data.action if rig.animation_data else None, rig.pose.bones["c_pos"].get(SWITCH, 0.0))

    driven = {pb.name for pb in game.pose.bones
              if any(getattr(c, "target", None) is rig for c in pb.constraints)}
    curves = {}
    for fc in _fcurves(act):
        if fc.data_path.startswith('pose.bones["'):
            bone = fc.data_path.split('"')[1]
            if bone in driven:
                curves[(bone, fc.data_path.rsplit(".", 1)[1], fc.array_index)] = fc
    # the RIG's range: an artist who lengthens a clip does it on the rig, and the game clip follows
    # to the last WHOLE frame of the longer of the two: the retarget stops at the last whole frame (a clip
    # keyed every 0.48 frame ends at 33.6, its rig copy at 33), and past its end each action only holds
    f0 = int(math.floor(src.frame_range[0] + 1e-6))
    f1 = int(math.floor(max(src.frame_range[1], src.frame_range[1] if created else act.frame_range[1]) + 1e-6))
    frames = list(range(f0, f1 + 1))                 # every frame: an edit can land anywhere
    if not frames:
        return 0

    # SWING FROM THE RIG, TWIST FROM THE CLIP. A 2-bone IK decides a limb's roll from its bend plane,
    # the clips carry their own -- measured on upright_aim_rifle, IK left calf_r / thigh_r / lowerarm_l
    # ~70 deg wrung round their own length, and in game that showed: a wrung forearm at the wrist, and the
    # skirt (hung from the thighs) re-folded. So the four limb segments take the DIRECTION the rig gives
    # them and the TWIST the clip had; the hand and foot keep exactly the orientation their IK control
    # gives; every other bone keeps its pose RELATIVE TO ITS PARENT, so a skirt follows the corrected
    # thigh. Unedited, that reproduces the clip; edited, a limb goes where it was put without wringing.
    world = {}                                        # (frame) -> {bone: armature-space matrix}
    order = sorted(game.pose.bones, key=lambda pb: len(pb.parent_recursive))
    _bind(game, act)
    _drive(rig, 0.0)
    orig = {}
    for f in frames:
        sc.frame_set(f)
        ev = game.evaluated_get(bpy.context.evaluated_depsgraph_get()).pose.bones
        orig[f] = {pb.name: ev[pb.name].matrix.copy() for pb in order}
    _bind(rig, src)                                   # the game action stays bound: undriven bones (Root)
    _drive(rig, 1.0)                                  # play their own keys
    for f in frames:
        sc.frame_set(f)
        ev = game.evaluated_get(bpy.context.evaluated_depsgraph_get()).pose.bones
        rigged = {pb.name: ev[pb.name].matrix.copy() for pb in order}
        final = {}
        for pb in order:
            n = pb.name
            M, O = rigged[n], orig[f][n]
            if n in TWIST_FROM_CLIP and n in driven:
                # the swing is measured on the JOINT-TO-JOINT line (this bone's head to the next joint's
                # head), not the bone's own axis: VRoid bones are disconnected, the next joint is off
                # that axis, and twisting about it moved the joints (measured 5 cm at the knee).
                # The rig's line is that SAME offset carried by the rig's ROTATION, never the rig's joint
                # POSITIONS: ARP's limb is a connected chain and puts the knee 3-6 mm off a VRoid knee,
                # which read as a 0.8 deg swing on every unedited leg (105 of 170 clips failed the
                # 0-key proof on it, while every rotation was exact).
                nxt = TWIST_FROM_CLIP[n]
                d_o = orig[f][nxt].translation - O.translation
                d_r = M.to_3x3() @ (O.to_3x3().inverted() @ d_o)
                swing = d_o.normalized().rotation_difference(d_r.normalized())
                F = (swing.to_matrix() @ O.to_3x3()).to_4x4()
                F.translation = M.translation
            elif n in TIPS or pb.parent is None or pb.parent.name not in final:
                F = M.copy()
            else:
                F = final[pb.parent.name] @ (rigged[pb.parent.name].inverted() @ M)
            # A bone's POSITION is the clip's own offset from its parent -- a body fact the game drops
            # anyway (build_character_anims keeps position tracks on Root and pelvis only) -- so the rig's
            # few-mm joint drift is never written. Root and pelvis are the bones that really translate.
            if pb.parent is not None and pb.parent.name in final and n not in TRANSLATES:
                F.translation = (final[pb.parent.name] @ (orig[f][pb.parent.name].inverted() @ O)).translation
            final[n] = F
        world[f] = final
    samples = {}
    for f in frames:
        final = world[f]
        for name in {b for b, _, _ in curves}:
            pb = game.pose.bones[name]
            rest = pb.bone.matrix_local
            if pb.parent is not None:
                basis = (final[pb.parent.name] @ pb.parent.bone.matrix_local.inverted() @ rest).inverted() @ final[name]
            else:
                basis = rest.inverted() @ final[name]
            loc, rot, scl = basis.decompose()
            samples[(name, f)] = {"location": loc, "rotation_quaternion": rot, "scale": scl,
                                  "rotation_euler": rot.to_euler(pb.rotation_mode if pb.rotation_mode not in
                                                                 ('QUATERNION', 'AXIS_ANGLE') else 'XYZ')}
    _drive(rig, keep[3])
    _bind(rig, keep[2])

    # A CHANNEL THE EDIT DID NOT CHANGE KEEPS ITS OWN KEYS, UNTOUCHED. A channel it did change is keyed on
    # every frame. Re-keying each curve only on its OWN frames lost edits: channels that do not move in
    # the clip are keyed at its first and last frame only, so a forearm raised mid-clip had nowhere to
    # land (measured: the ARP pose had the hand 8 cm up, the baked clip 2.8 cm up and 14 cm sideways).
    # Quaternions are compared and written sign-aligned to the original (q and -q are one rotation).
    n = 0
    quat_ref = {}
    for (bone, prop, idx), fc in curves.items():
        if prop == "rotation_quaternion":
            for f in frames:
                quat_ref.setdefault((bone, f), [0.0, 0.0, 0.0, 0.0])[idx] = fc.evaluate(f)
    for (bone, f), q in quat_ref.items():
        v = samples[(bone, f)]["rotation_quaternion"]
        if sum(a * b for a, b in zip(q, v)) < 0.0:
            samples[(bone, f)]["rotation_quaternion"] = -v
    # A QUATERNION IS COMPARED AS A ROTATION. A linearly interpolated quaternion curve is not unit length
    # between keys (the pose normalizes it), so component by component the SAME rotation read as changed
    # -- measured on `jump`, keyed every 0.48 frame: 0.0013 per component, 0.000 deg as a rotation.
    unchanged_rot = set()
    for bone in {b for (b, prop, _) in curves if prop == "rotation_quaternion"}:
        worst = 0.0
        for f in frames:
            q = quat_ref.get((bone, f))
            if q is None:
                worst = math.inf
                break
            norm = math.sqrt(sum(c * c for c in q)) or 1.0
            v = samples[(bone, f)]["rotation_quaternion"]
            # the CHORD form, theta = 4 asin(|q - v| / 2): 2 acos(q.v) is float noise near a dot of 1
            # (measured, it read a 0.0001 finger wobble as 0.03 deg and rewrote the curve)
            chord = min(math.sqrt(sum((a / norm - b) ** 2 for a, b in zip(q, v))),
                        math.sqrt(sum((a / norm + b) ** 2 for a, b in zip(q, v))))
            worst = max(worst, 4.0 * math.asin(min(1.0, chord / 2.0)))
        if worst < BAKE_TOLERANCE:
            unchanged_rot.add(bone)
    for (bone, prop, idx), fc in curves.items():
        if prop == "rotation_quaternion" and bone in unchanged_rot:
            continue                                   # the same rotation: original keys stay, bit for bit
        new = [samples[(bone, f)][prop][idx] for f in frames]
        if prop != "rotation_quaternion" and \
                max(abs(fc.evaluate(f) - v) for f, v in zip(frames, new)) < BAKE_TOLERANCE:
            continue                                   # unchanged: the original keys stay, bit for bit
        interp = fc.keyframe_points[0].interpolation if len(fc.keyframe_points) else 'LINEAR'
        fc.keyframe_points.clear()
        for f, v in zip(frames, new):
            k = fc.keyframe_points.insert(f, v, options={'FAST'})
            k.interpolation = interp
            n += 1
        fc.update()
    _bind(game, keep[1])
    sc.frame_set(keep[0])
    src[BAKED_KEY] = "%s:%s" % (_digest(src), _digest(act))
    return n


def arp_clips():
    """Every clip that lives on the rig -- including one made there that has no game action yet."""
    return sorted(a.name[len(PREFIX):] for a in bpy.data.actions if a.name.startswith(PREFIX))


def game_clips():
    """The exported clips: the actions on the game armature's NLA tracks."""
    _, game = rigs()
    names = set()
    if game.animation_data:
        for tr in game.animation_data.nla_tracks:
            for st in tr.strips:
                if st.action is not None and not st.action.name.startswith(PREFIX):
                    names.add(st.action.name)
    return sorted(names)


def bake_all(force=False):
    strip_switch_keys()
    return {clip: bake_to_game(clip, force=force) for clip in arp_clips()}


def move_all(log=print):
    """Every game clip that is not on the rig yet goes there, in FK (exact). Each move is PROVED: an
    unedited bake must write 0 keys, i.e. the rig reproduces the clip to BAKE_TOLERANCE. A clip that
    fails keeps its rig action out (removed again) and is reported; its game action is restored from a
    copy taken before the bake, so a failed proof changes nothing. Returns {clip: keys an unedited bake
    would have written}. A clip ALREADY on the rig is never touched -- it may hold an artist's edit."""
    out = {}
    todo = [c for c in game_clips() if (PREFIX + c) not in bpy.data.actions]
    for i, clip in enumerate(todo):
        t = time.time()
        act = bpy.data.actions[clip]
        backup = act.copy()
        move_to_arp(clip, to_ik=False)
        n = bake_to_game(clip, force=True)
        out[clip] = n
        if n != 0:
            # a copy is a different datablock: put its keys back into the original (the NLA points there)
            for fc in _fcurves(act):
                bf = next((b for b in _fcurves(backup)
                           if b.data_path == fc.data_path and b.array_index == fc.array_index), None)
                if bf is None:
                    continue
                fc.keyframe_points.clear()
                for k in bf.keyframe_points:
                    nk = fc.keyframe_points.insert(k.co[0], k.co[1], options={'FAST'})
                    nk.interpolation = k.interpolation
                fc.update()
            bpy.data.actions.remove(bpy.data.actions[PREFIX + clip])
        bpy.data.actions.remove(backup)
        log("[arp-clips] %3d/%d %-40s %s (%.1fs)" % (i + 1, len(todo), clip,
                                                    "exact" if n == 0 else "NOT EXACT, %d keys -- left off the rig" % n,
                                                    time.time() - t))
    return out


def new_clip(name, f0=0, f1=30):
    """A clip made on the rig from nothing: `ARP_<name>`, holding the rig's current pose over the range.
    Its game action does not exist until the first bake (the Export) creates it."""
    if name.startswith(PREFIX):
        name = name[len(PREFIX):]
    if (PREFIX + name) in bpy.data.actions or name in bpy.data.actions:
        raise RuntimeError("a clip called %r already exists" % name)
    rig, _ = rigs()
    act = bpy.data.actions.new(PREFIX + name)
    act.use_fake_user = True
    _bind(rig, act)
    sc = bpy.context.scene
    for f in (f0, f1):
        sc.frame_set(f)
        for pb in rig.pose.bones:
            if pb.name.startswith("c_") and pb.bone.use_deform is False:
                pb.keyframe_insert("location", frame=f, group=pb.name)
                pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == 'QUATERNION' else "rotation_euler",
                                   frame=f, group=pb.name)
    strip_switch_keys()
    return act


def _main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        return
    cmd, rest = argv[0], [a for a in argv[1:] if not a.startswith("--")]
    if cmd == "move":
        a = move_to_arp(rest[0], to_ik="--ik" in argv)
        print("[arp-clips] moved %s -> %s (%s)" % (rest[0], a.name, "IK" if "--ik" in argv else "FK"))
    elif cmd == "move-all":
        res = move_all()
        bad = {c: n for c, n in res.items() if n != 0}
        print("[arp-clips] moved %d clip(s) to the rig, %d exact, %d NOT exact: %s"
              % (len(res), len(res) - len(bad), len(bad), bad))
    elif cmd == "bake":
        force = "--force" in argv
        done = {c: bake_to_game(c, force=force) for c in rest} if rest else bake_all(force=force)
        print("[arp-clips] baked %s" % done)
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
        print("[arp-clips] saved")


if __name__ == "__main__":
    _main()
