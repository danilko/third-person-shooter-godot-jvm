"""Retarget the Quaternius Universal Animation Library onto the Godot-chan rig.

    blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \\
        --python blender/tools/retarget_ual.py -- [--only NAME,NAME] [--no-replace] [--save]

The table is `blender/tools/ual_retarget.json`: `clips` adds a source clip under a new action name,
`replace` writes a source clip (or `A+B`, played back to back) into an EXISTING action, keeping its
name and NLA track, so the AnimationTree picks it up with no scene edit. `Clip@N` holds frame N as a
static pose, `Clip@A:B` takes frames A..B, `Clip@N~K` holds frame N for K more frames; `fist_axis` [x, y, z] turns the right wrist so a held
handle points that way (armature space: -Y forward, +Z up); `drop` removes clips from the set. Re-running is idempotent:
an action this tool made before is rebuilt in place.

WHY A WORLD-SPACE DELTA, NOT A BONE-NAME COPY. The library is a UE-mannequin skeleton and its bone
NAMES match Godot-chan's (bar `root`/`Root`, `Head`/`head` and the `*_leaf` bones), but the bone
ROLLS and lengths do not, so a local rotation copied by name turns every bone about the wrong axis.
Both rigs are rested in a T-pose facing -Y (measured), so each bone is given the source bone's
world rotation RELATIVE TO ITS OWN REST, applied on top of the target's rest:

    R_target_world(t) = R_source_world(t) @ R_source_rest^-1 @ R_target_rest

Positions come from the target's own bone lengths down the chain, except the pelvis, which takes
the source pelvis position scaled by the ratio of the two rest pelvis heights (Godot-chan is 1.49 m;
the library body is taller). Root is held at the pose it has in the clip being replaced (or in
`reference_root_clip` for a new clip): the Root family check (`check_character_anim.py`) needs every
clip of one blendspace ring to agree on Root, and the pelvis is placed in WORLD space, so Root's
value does not move the body.
"""
import bpy
import json
import os
import sys
from mathutils import Matrix, Quaternion, Vector

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.path.join(ROOT_DIR, "blender", "tools", "ual_retarget.json")
ARM_NAME = "Godot_Chan_Stealth"
TAG = "ual_retarget"          # custom property on every action this tool writes


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = None
    if "--only" in a:
        only = set(a[a.index("--only") + 1].split(","))
    return {"only": only, "no_replace": "--no-replace" in a, "save": "--save" in a}


def rest_world(obj):
    """Armature-space rest matrices (the object transforms are identity rotation on both rigs)."""
    return {b.name: b.matrix_local.copy() for b in obj.data.bones}


def root_basis(tgt, action_name):
    """Root's (loc, quat, scale) at the first frame of an existing action, or rest."""
    act = bpy.data.actions.get(action_name)
    loc, rot, scl = [0.0] * 3, [1.0, 0.0, 0.0, 0.0], [1.0] * 3
    if act is None:
        return loc, rot, scl
    f0 = act.frame_range[0]
    for fc in fcurves(act):
        if fc.data_path.startswith('pose.bones["Root"].'):
            prop = fc.data_path.rsplit(".", 1)[1]
            v = fc.evaluate(f0)
            {"location": loc, "rotation_quaternion": rot, "scale": scl}[prop][fc.array_index] = v
    return loc, rot, scl


def fcurves(act):
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


def sample_source(src, act, frames):
    """[{bone: armature-space pose matrix}] for each frame."""
    ad = src.animation_data or src.animation_data_create()
    ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]
    scene = bpy.context.scene
    out = []
    for f in frames:
        scene.frame_set(int(f), subframe=f - int(f))
        out.append({pb.name: pb.matrix.copy() for pb in src.pose.bones})
    return out


ARM_ROOTS = ("clavicle_l", "clavicle_r")


def arm_bones(tgt):
    """Every bone at or below a clavicle: what an ARMS-ONLY bake takes from the source."""
    out = set()
    for r in ARM_ROOTS:
        b = tgt.data.bones[r]
        out.add(b.name)
        out.update(c.name for c in b.children_recursive)
    return out


def action_bases(tgt, action_name):
    """{bone: (loc, quat, scale)} of an existing action at its first frame."""
    act = bpy.data.actions[action_name]
    f0 = act.frame_range[0]
    vals = {}
    for fc in fcurves(act):
        if not fc.data_path.startswith('pose.bones["'):
            continue
        bone = fc.data_path.split('"')[1]
        prop = fc.data_path.rsplit(".", 1)[1]
        vals.setdefault(bone, {}).setdefault(prop, {})[fc.array_index] = fc.evaluate(f0)
    out = {}
    for b, d in vals.items():
        loc = Vector([d.get("location", {}).get(i, 0.0) for i in range(3)])
        q = Quaternion([d.get("rotation_quaternion", {}).get(i, 1.0 if i == 0 else 0.0) for i in range(4)])
        scl = Vector([d.get("scale", {}).get(i, 1.0) for i in range(3)])
        out[b] = (loc, q.normalized(), scl)
    return out


def retarget_frame(src_pose, src_rest, tgt, tgt_rest, bone_map, k, root_trs, neutral=None, arms=None,
                   fist_axis=None):
    """Target pose-bone bases {bone: (loc, quat, scale)} for one sampled source frame.

    With `neutral` (bases of a standing reference pose) and `arms` (a bone set), only the arms take
    the source; every other bone holds the reference. The arms keep the source's WORLD directions,
    so a swing whose source body twists and lunges into it still sweeps in FRONT of a torso that
    stands square -- which is what the game draws: the Attack one-shot's filter leaves the pelvis
    and lower spine to locomotion, and the shoulder-aim modifier squares the chest to the aim."""
    inv_map = {v: k_ for k_, v in bone_map.items()}
    pose_arm = {}
    bases = {}
    for bone in tgt.data.bones:                              # parents before children
        name = bone.name
        rest = tgt_rest[name]
        if neutral is not None and name not in arms and name in neutral:
            loc, rot, scl = neutral[name]
            basis = Matrix.LocRotScale(loc, rot, scl)
            parent = bone.parent
            rel_rest = (tgt_rest[parent.name].inverted() @ rest) if parent else rest
            pose_arm[name] = (pose_arm[parent.name] @ rel_rest @ basis) if parent else rest @ basis
            bases[name] = (loc.copy(), rot.copy(), scl.copy())
            continue
        if name == "Root":
            loc, rot, scl = root_trs
            basis = Matrix.LocRotScale(Vector(loc), Quaternion(rot), Vector(scl))
            pose_arm[name] = rest @ basis
            bases[name] = (Vector(loc), Quaternion(rot), Vector(scl))
            continue
        sname = inv_map.get(name, name)
        parent = bone.parent
        rel_rest = (tgt_rest[parent.name].inverted() @ rest) if parent else rest
        if sname in src_pose:
            r_src = src_pose[sname].to_quaternion()
            r_src_rest = src_rest[sname].to_quaternion()
            r = r_src @ r_src_rest.inverted() @ rest.to_quaternion()
        else:                                                # keep the rest orientation relative
            r = (pose_arm[parent.name] @ rel_rest).to_quaternion() if parent else rest.to_quaternion()
        if name == "hand_r" and fist_axis is not None:
            # Turn the WRIST (only) so the fist's through-axis -- pinky knuckle -> index knuckle, the
            # line a held handle runs along -- points along `fist_axis` (armature space). A held
            # weapon then stands where the pose wants it with every other bone untouched.
            a_rest = (tgt_rest["index_01_r"].to_translation() - tgt_rest["pinky_01_r"].to_translation()).normalized()
            a_now = r @ rest.to_quaternion().inverted() @ a_rest
            r = a_now.rotation_difference(Vector(fist_axis).normalized()) @ r
        if name == "pelvis":
            pos = src_pose[sname].to_translation() * k
        else:
            pos = (pose_arm[parent.name] @ rel_rest).to_translation() if parent else rest.to_translation()
        m = Matrix.Translation(pos) @ r.to_matrix().to_4x4()
        pose_arm[name] = m
        parent_arm = pose_arm[parent.name] if parent else Matrix.Identity(4)
        basis = rel_rest.inverted() @ parent_arm.inverted() @ m
        l, q, s = basis.decompose()
        bases[name] = (l, q, Vector((1.0, 1.0, 1.0)))
    return bases


def write_action(tgt, name, keyed, start=0.0):
    """Build a fresh action `name` from [{bone: (loc,quat,scale)}] one per frame from `start`."""
    old = bpy.data.actions.get(name)
    tmp = bpy.data.actions.new(name + "__new")
    ad = tgt.animation_data or tgt.animation_data_create()
    prev_action = ad.action
    ad.action = tmp
    n = len(keyed)
    for bone in tgt.data.bones:
        b = bone.name
        chans = [("location", 3), ("rotation_quaternion", 4), ("scale", 3)]
        prev_q = None
        qs = []
        for fr in keyed:
            q = fr[b][1].copy()
            if prev_q is not None and prev_q.dot(q) < 0:
                q.negate()
            prev_q = q
            qs.append(q)
        for prop, size in chans:
            for i in range(size):
                fc = tmp.fcurve_ensure_for_datablock(tgt, f'pose.bones["{b}"].{prop}', index=i)
                fc.group = None
                fc.keyframe_points.add(n)
                co = []
                for j, fr in enumerate(keyed):
                    v = qs[j][i] if prop == "rotation_quaternion" else fr[b][0 if prop == "location" else 2][i]
                    co += [start + j, v]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
                fc.update()
    ad.action = prev_action
    tmp[TAG] = True
    # Swap into the NLA: an existing track of that name keeps its place and mute state.
    track = ad.nla_tracks.get(name)
    mute = track.mute if track is not None else True
    if track is not None:
        ad.nla_tracks.remove(track)
    if old is not None:
        bpy.data.actions.remove(old)
    tmp.name = name
    track = ad.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, int(start), tmp)
    strip.extrapolation = 'HOLD'
    track.mute = mute
    return tmp


def main():
    opt = args()
    table = json.load(open(TABLE))
    tgt = bpy.data.objects[ARM_NAME]
    tgt_rest = rest_world(tgt)
    scene = bpy.context.scene
    keep = (scene.render.fps, scene.render.fps_base, scene.frame_start, scene.frame_end, scene.frame_current)

    jobs = {}   # target action -> (list of "SRC/clip[@frame]", root reference action, arms-only reference)
    fist_axes = {}   # target action -> armature-space direction for the right fist's through-axis
    for src_clip, dst in table["clips"].items():
        if isinstance(dst, dict):                    # {"name", "arms_over"}: a new arms-only clip
            jobs[dst["name"]] = (src_clip.split("+"), table["reference_root_clip"], dst.get("arms_over"))
        else:
            jobs[dst] = (src_clip.split("+"), table["reference_root_clip"], None)
    if not opt["no_replace"]:
        for dst, spec in table["replace"].items():
            if bpy.data.actions.get(dst) is None:
                raise SystemExit(f"[retarget_ual] replace target {dst!r} is not an action in this .blend")
            if isinstance(spec, str):
                spec = {"src": spec}
            jobs[dst] = (spec["src"].split("+"), dst, spec.get("arms_over"))
            if spec.get("fist_axis"):
                fist_axes[dst] = spec["fist_axis"]
    if opt["only"]:
        jobs = {k: v for k, v in jobs.items() if k in opt["only"]}

    # Root pose per job read BEFORE anything is rewritten (a replace overwrites its own reference).
    roots = {dst: root_basis(tgt, ref) for dst, (_, ref, _a) in jobs.items()}
    neutrals = {dst: action_bases(tgt, ref) for dst, (_, _r, ref) in jobs.items() if ref}
    arms = arm_bones(tgt)
    needed = {s.split("/")[0] for srcs, _, _a in jobs.values() for s in srcs}

    sampled = {}
    for lib in sorted(needed):
        path = os.path.join(ROOT_DIR, table["sources"][lib])
        before_obj, before_act = set(bpy.data.objects), set(bpy.data.actions)
        before_misc = {c: set(getattr(bpy.data, c)) for c in ("meshes", "armatures", "materials", "images")}
        bpy.ops.import_scene.gltf(filepath=path)
        new_objs = [o for o in bpy.data.objects if o not in before_obj]
        src = next(o for o in new_objs if o.type == 'ARMATURE')
        new_acts = {a.name.split(".")[0]: a for a in bpy.data.actions if a not in before_act}
        src_rest = rest_world(src)
        k = tgt_rest["pelvis"].to_translation().z / src_rest["pelvis"].to_translation().z
        print(f"[retarget_ual] {lib}: {len(new_acts)} clips, pelvis scale {k:.4f}")
        for dst, (srcs, _, _a) in jobs.items():
            for s in srcs:
                slib, clip = s.split("/")
                clip, _, at = clip.partition("@")
                if slib != lib or s in sampled:
                    continue
                act = new_acts[clip]
                a, b = act.frame_range
                frames = [a + i for i in range(int(round(b - a)) + 1)]
                if "~" in at:                            # frame N held for K more frames
                    n, k = (int(x) for x in at.split("~"))
                    frames = [frames[n]] * (k + 1)
                elif ":" in at:                          # a slice, frames a..b inclusive
                    lo, hi = (int(x) for x in at.split(":"))
                    frames = frames[lo:hi + 1]
                elif at:                                 # one held pose: a 2-key static loop
                    frames = [frames[int(at)]] * 2
                sampled[s] = (sample_source(src, act, frames), src_rest, k)
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in [a for a in bpy.data.actions if a not in before_act]:
            bpy.data.actions.remove(a)
        for c, before in before_misc.items():
            coll = getattr(bpy.data, c)
            for d in [d for d in coll if d not in before]:
                coll.remove(d)

    for dst, (srcs, _, arms_over) in sorted(jobs.items()):
        keyed = []
        for s in srcs:
            poses, src_rest, k = sampled[s]
            frames = [retarget_frame(p, src_rest, tgt, tgt_rest, table["bone_map"], k, roots[dst],
                                     neutrals.get(dst), arms, fist_axes.get(dst)) for p in poses]
            if keyed:
                frames = frames[1:] if len(frames) > 1 else frames
            keyed += frames
        write_action(tgt, dst, keyed)
        how = f", arms over {arms_over!r}" if arms_over else ""
        print(f"[retarget_ual] {dst:34s} <- {'+'.join(srcs)} ({len(keyed)} frames{how})")

    ad = tgt.animation_data
    for name in table.get("drop", []):               # clips taken out of the set on purpose
        track = ad.nla_tracks.get(name) if ad else None
        if track is not None:
            ad.nla_tracks.remove(track)
        act = bpy.data.actions.get(name)
        if act is not None:
            bpy.data.actions.remove(act)
            print(f"[retarget_ual] dropped {name}")

    scene.render.fps, scene.render.fps_base, scene.frame_start, scene.frame_end, fc = keep
    scene.frame_set(fc)
    if tgt.animation_data is not None:
        tgt.animation_data.action = None
    if opt["save"]:
        bpy.ops.wm.save_mainfile()
        print(f"[retarget_ual] saved {bpy.data.filepath}")
    print(f"[retarget_ual] done: {len(jobs)} actions")


main()
