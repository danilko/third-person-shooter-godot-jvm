"""Bring a VRoid `.vrm` in as a BODY on the shared skeleton contract (PLAN.md 6.9).

    blender -b --python-exit-code 1 --python blender/tools/import_vrm_body.py -- \
        --vrm "/path/to/xxxx.vrm" --name shino [--out assets/characters/shino] [--no-export]

What this is for, and the one rule behind all of it
---------------------------------------------------
A clip is a fact about the SKELETON, not about a body (see `blender/SKELETON_CONTRACT.md`). Every
body in this game plays the ONE shared library `character_anims.res`, so a new body's only job is
to present that contract: our 53 bone NAMES, in our rest ORIENTATIONS, facing the way we face.
Nothing else about the body has to match -- limb LENGTHS are free, which is the whole point of a
second body, and the library carries no position track that could overrule them (measured: 8414 of
8550 position tracks in the source are exporter noise and are dropped by
`tools/godot/build_character_anims.gd`).

So this script does exactly three things to the imported rig and leaves everything else alone:

  1. TURNS IT ROUND. Measured, Godot-chan faces -Y with its left arm at +X, and a VRoid avatar
     faces +Y with its left arm at -X: one 180 deg rotation about Z, not a mirror. The rotation is
     applied to the armature and its meshes, so the exported body faces the way the contract does.
  2. RENAMES the 54 humanoid bones, reading the map from the file's OWN `VRM.humanoid.humanBones`
     rather than matching `J_Bip_*` strings -- a VRoid export names its bones consistently, but the
     humanoid map is the published contract and a re-rigged model may not spell them the same way.
     It also builds `Root`, which VRM has no equivalent of: Godot-chan's is a ground-level bone above
     the hips and the library's root motion rides it.
  3. RE-ORIENTS each contract bone's rest to Godot-chan's orientation for that bone, keeping the
     VRoid HEAD position. This is the step that makes the shared clips play, and it is free: a
     Blender bone's deformation is `pose . rest^-1`, so at rest it is the identity WHATEVER the rest
     orientation is -- re-orienting a bone in edit mode does not move one vertex of the mesh. It only
     changes what a pose rotation means, which is precisely what has to agree between two rigs.
     Measured on Shino: after the turn, her limb directions already agree with Godot-chan's to within
     a few degrees (both are T-posed), so what this actually supplies is the ROLL.

Bones the contract does not name -- hair, skirt, the VRM spring-bone chains, eyes, tongue -- are
KEPT and untouched: the mesh is skinned to them, and a crowd simply never animates them (dropping
the spring-bone simulation is `CHARACTER_BASE_STUDY.md` section 4's decision, not this script's).

The `.vrm` is read from outside the repo and never modified. Output is a new `<name>.blend` plus
`<name>.glb`; re-running overwrites only those.
"""
import bpy
import json
import math
import os
import struct
import sys
import tempfile

from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

# The contract rig this body has to present. Its rest orientations are read from the file, never
# copied into this script: one owner, and it follows the rig if the rig is ever re-authored.
CONTRACT_BLEND = os.path.join(REPO, "assets/characters/godot_chan/merged_animation.blend")
CONTRACT_REST = os.path.join(REPO, "assets/characters/skeleton_rest.json")

# VRM humanoid bone name -> our bone name. VRM 0.x spelling; a 1.0 file uses the same words in the
# same place of its own map, so the lookup is by these keys either way.
BONE_MAP = {
    "hips": "pelvis",
    "spine": "spine_01",
    "chest": "spine_02",
    "upperChest": "spine_03",
    "neck": "neck_01",
    "head": "head_2",   # see GODOT_NAME_NOTE
}
for side, suf in (("left", "l"), ("right", "r")):
    BONE_MAP["%sShoulder" % side] = "clavicle_%s" % suf
    BONE_MAP["%sUpperArm" % side] = "upperarm_%s" % suf
    BONE_MAP["%sLowerArm" % side] = "lowerarm_%s" % suf
    BONE_MAP["%sHand" % side] = "hand_%s" % suf
    BONE_MAP["%sUpperLeg" % side] = "thigh_%s" % suf
    BONE_MAP["%sLowerLeg" % side] = "calf_%s" % suf
    BONE_MAP["%sFoot" % side] = "foot_%s" % suf
    BONE_MAP["%sToes" % side] = "ball_%s" % suf
    # VRM calls the little finger "Little"; ours is "pinky".
    for vrm_finger, ours in (("Thumb", "thumb"), ("Index", "index"), ("Middle", "middle"),
                             ("Ring", "ring"), ("Little", "pinky")):
        for vrm_seg, n in (("Proximal", "01"), ("Intermediate", "02"), ("Distal", "03")):
            BONE_MAP["%s%s%s" % (side, vrm_finger, vrm_seg)] = "%s_%s_%s" % (ours, n, suf)

ROOT_BONE = "Root"

# GODOT_NAME_NOTE: the head bone is `head_2`, not `head`, and that is not a typo. The reference
# .glb carries a MESH node called `head` as well as the bone, and Godot's glTF importer renames the
# BONE out of the way -- so the shared library's tracks, the AnimationTree's filters, the ragdoll's
# `Physical Bone head_2` and the Java bone-multiplier table all say `head_2`. A new body has no such
# collision and would import as `head`, which resolves to nothing and simply never animates. Naming
# it here is the cheap half of the fix; the clean half is renaming the reference's MESH and is worth
# doing the day Godot-chan is retired.
TURN = Matrix.Rotation(math.pi, 4, "Z")   # measured: VRoid faces +Y, the contract faces -Y


# ----------------------------------------------------------------------------- glTF / VRM reading

def vrm_humanoid_map(path):
    """{vrm bone name: glTF node name} straight out of the file's own VRM extension."""
    with open(path, "rb") as f:
        magic, _ver, total = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise SystemExit("[vrm] %s is not a GLB/VRM" % path)
        doc = None
        while f.tell() < total:
            ln, ctype = struct.unpack("<II", f.read(8))
            data = f.read(ln)
            if ctype == 0x4E4F534A:
                doc = json.loads(data.decode("utf-8"))
                break
    ext = (doc or {}).get("extensions", {})
    nodes = doc["nodes"]
    out = {}
    if "VRM" in ext:                                     # VRM 0.x
        for hb in ext["VRM"].get("humanoid", {}).get("humanBones", []):
            out[hb["bone"]] = nodes[hb["node"]].get("name")
    elif "VRMC_vrm" in ext:                              # VRM 1.0
        for name, hb in ext["VRMC_vrm"].get("humanoid", {}).get("humanBones", {}).items():
            out[name] = nodes[hb["node"]].get("name")
    if not out:
        raise SystemExit("[vrm] %s carries no VRM humanoid map" % path)
    return out


def contract_rest():
    """{bone: world rest matrix} of the contract rig, cached beside the assets as JSON."""
    if os.path.exists(CONTRACT_REST):
        raw = json.load(open(CONTRACT_REST))["rest"]
        return {n: Matrix([[*d["x"], 0.0], [*d["y"], 0.0], [*d["z"], 0.0],
                           [*d["head"], 1.0]]).transposed() for n, d in raw.items()}
    raise SystemExit("[vrm] %s is missing -- run blender/tools/dump_skeleton_rest.py first"
                     % CONTRACT_REST)


# ------------------------------------------------------------------------------------ conversion

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    vrm = name = out_dir = None
    do_export = True
    for i, a in enumerate(argv):
        if a == "--vrm":
            vrm = argv[i + 1]
        elif a == "--name":
            name = argv[i + 1]
        elif a == "--out":
            out_dir = argv[i + 1]
        elif a == "--no-export":
            do_export = False
    if not vrm or not name:
        raise SystemExit("usage: -- --vrm <file.vrm> --name <body> [--out dir] [--no-export]")
    out_dir = out_dir or os.path.join(REPO, "assets/characters", name)
    os.makedirs(out_dir, exist_ok=True)

    humanoid = vrm_humanoid_map(vrm)
    rest = contract_rest()

    # Blender's stock glTF importer reads a .vrm whole (CHARACTER_BASE_STUDY.md section 2) but it
    # goes by extension, so hand it a .glb copy. The source file is never touched.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    tmp = os.path.join(tempfile.mkdtemp(prefix="vrm_"), "%s_src.glb" % name)
    with open(vrm, "rb") as src, open(tmp, "wb") as dst:
        dst.write(src.read())
    bpy.ops.import_scene.gltf(filepath=tmp)
    os.remove(tmp)
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        raise SystemExit("[vrm] expected one armature, found %d" % len(arms))
    arm = arms[0]
    arm.name = name
    arm.data.name = name

    # 1. turn it round -----------------------------------------------------------------------
    arm.matrix_world = TURN @ arm.matrix_world
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 2. rename -------------------------------------------------------------------------------
    renamed, missing = {}, []
    for vrm_bone, ours in BONE_MAP.items():
        node = humanoid.get(vrm_bone)
        if node is None or node not in arm.data.bones:
            missing.append(vrm_bone)
            continue
        renamed[ours] = node
    # Rename through a scratch prefix, because a target name may already belong to another bone.
    for ours, node in renamed.items():
        arm.data.bones[node].name = "__c__" + ours
    for ours in renamed:
        arm.data.bones["__c__" + ours].name = ours
    print("[vrm] renamed %d bones; unmapped humanoid bones: %s"
          % (len(renamed), ", ".join(missing) if missing else "none"))

    # 3. Root, then the rest orientations ------------------------------------------------------
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones

    # `Root` is virtual -- nothing is skinned to it -- and it is where the library's root motion
    # rides, so it takes the contract's rest OUTRIGHT, position included, rather than the body's
    # own. A VRoid file ALREADY HAS a bone of this name (the armature root), which is why this is a
    # conform and not a create: written as "create it if it is missing" the branch simply never ran,
    # and the imported root's own frame -- pointing up from the origin -- survived into the export
    # 120 deg out from the contract, on every body.
    m = rest[ROOT_BONE]
    q = m.to_quaternion()
    length = max(0.05, rest[ROOT_BONE].to_scale().y)
    r = eb.get(ROOT_BONE) or eb.new(ROOT_BONE)
    r.use_connect = False
    # A zero-length bone has no direction for `matrix` to preserve, so give it a real tail first.
    r.head = m.translation
    r.tail = m.translation + (q @ Vector((0.0, 1.0, 0.0))) * length
    r.matrix = Matrix.Translation(m.translation) @ q.to_matrix().to_4x4()
    if eb["pelvis"].parent is not r:
        eb["pelvis"].parent = r
    eb["pelvis"].use_connect = False

    worst = 0.0
    worst_bone = ""
    for ours in sorted(renamed):
        if ours not in eb or ours not in rest:
            continue
        b = eb[ours]
        before = b.matrix.to_quaternion()
        target = rest[ours].to_quaternion()
        b.use_connect = False
        length = b.length if b.length > 1e-4 else 0.05
        b.matrix = Matrix.Translation(b.head) @ target.to_matrix().to_4x4()
        b.length = length
        d = math.degrees(before.rotation_difference(target).angle)
        if d > worst:
            worst, worst_bone = d, ours
    print("[vrm] re-oriented %d bones to the contract; biggest change %.1f deg (%s)"
          % (len(renamed), worst, worst_bone))
    bpy.ops.object.mode_set(mode="OBJECT")

    # report what the body is, in the numbers CHARACTER_BASE_STUDY.md section 5 compares
    bones = arm.data.bones
    def span(a, b):
        return (bones[a].head_local - bones[b].head_local).length if a in bones and b in bones else float("nan")
    height = max((v.co.z for ob in bpy.data.objects if ob.type == "MESH"
                  for v in ob.data.vertices), default=0.0)
    print("[vrm] %s: %d bones (%d contract), height %.3f m, arm %.3f m, leg %.3f m, hip %.3f m"
          % (name, len(bones), len(renamed) + 1, height, span("upperarm_l", "hand_l"),
             span("thigh_l", "foot_l"), bones["pelvis"].head_local.z if "pelvis" in bones else 0.0))

    blend = os.path.join(out_dir, "%s.blend" % name)
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("[vrm] wrote %s" % blend)

    if do_export:
        glb = os.path.join(out_dir, "%s.glb" % name)
        bpy.ops.export_scene.gltf(
            filepath=glb,
            export_format="GLB",
            use_visible=True,
            export_yup=True,
            export_apply=True,
            export_texcoords=True,
            export_normals=True,
            export_tangents=True,
            export_vertex_color="NONE",
            export_materials="EXPORT",
            export_extras=True,
            export_skins=True,
            export_all_influences=True,
            export_def_bones=False,
            export_animations=False,      # a BODY carries no clips -- that is the whole contract
            export_morph=False,           # 40-odd VRM expression morphs, no system reads them
        )
        print("[vrm] wrote %s (%d bytes)" % (glb, os.path.getsize(glb)))
        print("[vrm] now run: godot --headless --path . --import")


main()
