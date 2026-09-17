"""Measure, SOLVE and ADOPT how each weapon archetype is held (PLAN.md A2.4, CLAUDE.md W24/W25).

One row per archetype in blender/tools/weapon_archetypes.json `holds` (socket, reference weapon, mount marker,
support hand, clips, the solve arguments the shipped clips were written with). Every command takes --hold <name>
(default rifle); `--flag value` overrides a row argument.

    B="blender -b assets/merged_animation.blend --python-exit-code 1 --python blender/tools/pose_weapon_hold.py --"
    $B measure    [--hold H] [--action CLIP] [--frame F] [--placed OBJ] [--render DIR] [--poke-detail]
    $B adopt      --hold H [--placed OBJ] --apply   # derive socket / mount anchor / SupportPoint from the pose
    $B solve-aim  --hold H [--write --save]         # placement: mount | eye_line (or a --placed model)
    $B solve-hold --hold H [--write --save]         # a carry: grip placed off the shoulder, muzzle down/across
    $B body-anchor R U F | skin-anchor | remove-object NAME... --save
    blender -b assets/merged_animation_f.blend ... -- copy-from assets/merged_animation.blend --save

What shipped (2026-09-15): rifle aim ADOPTED from the artist's placed ASR1 (clip untouched); rifle hold, launcher
aim and hold SOLVED from their rows; pistol clips kept, PIS1's SupportPoint adopted from them.

NOT idempotent where a gesture is relative: the shoulder shrug and the head gestures apply to the clip they start
from, so a second rifle-style solve over a solved clip shrugs again. The launcher row (no shrug, head kept) is
idempotent. Pre-A2.4 copies: assets/merged_animation.pre-A24.blend / merged_animation_f.pre-A24.blend (local).

Why a script and not a hand edit. The rifle aim pose has to satisfy several GEOMETRIC facts at once --
the bore on the body's forward line, the butt pad in the shoulder pocket, the right eye over the bore,
the support hand on the handguard, nothing of the gun inside the body -- and each of them is measured by
the Godot probes against constants that live in Godot scenes (`SocketRifle`, the weapon markers,
`StockMountIKModifier.pocketOffset`). A pose nudged by eye passes some and silently fails the others
(the 2026-09-14 study pose: a good blade, the gun 33 deg off the aim). So the facts are solved here, from
the SAME constants, parsed out of the same files the game reads, and the artist keeps every choice the
facts do not decide (the blade, the elbow flare, the head clearance) as arguments.

Frames. Godot skeleton space = C @ Blender armature space (the glTF exporter applies the Z-up -> Y-up
change on the ROOT joint only, so every other bone's local frame is identical on both sides). So a Godot
bone-local transform (a socket under a BoneAttachment3D) applies unchanged to the Blender pose bone, and
a Godot weapon-local point p is `hand @ socket @ p` in armature space. Body frame (MeshRoot: +X right,
+Y up, -Z forward) is `(-x, z, y)` of armature space. A Godot `Transform3D(...)` in a .tscn is
ROW-major. Verified: this script reproduces `probe_pose_clip.gd` to the millimetre and 0.001 deg.

What is measured (all in the body frame; `measure` prints it, `solve-*` prints it before and after):
  blade        shoulder line vs hips, split into spine_03's share and the collarbones' share
  gun          bore yaw / pitch against the body's forward line
  stock        StockPoint vs the shoulder pocket, per weapon
  support      left hand (hand_l origin, what SupportHandIKModifier drives) vs SupportPoint, and the reach
  eye          right-eye centre vs the bore: lateral offset, and clearance over the gun's TOP at that station
  elbow        how far the firing elbow is flared out from straight down (0 = tucked, 90 = chicken wing)
  poke         how deep the gun's surface goes inside the body (skinned, hands and fingers excluded): the
               deepest point, the body part it is in, and how many surface samples are deeper than 1 cm
"""
import bpy
import json
import math
import os
import re
import sys
from mathutils import Matrix, Vector, Quaternion
from mathutils.bvhtree import BVHTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VISUALS = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")
WEAPON_SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/weapon/%s.tscn")
WEAPON_BLEND = os.path.join(ROOT, "assets/weapons/%s.blend")
STOCK_MOUNT = os.path.join(ROOT, "src/main/java/com/openworld/character/StockMountIKModifier.java")
ARMATURE = "Godot_Chan_Stealth"
ARCHETYPES = os.path.join(ROOT, "blender/tools/weapon_archetypes.json")
MODELS = os.path.join(ROOT, "blender/tools/weapon_models.json")
HOLDS = json.load(open(ARCHETYPES))["holds"]
CATALOG = json.load(open(os.path.join(ROOT, "src/main/resources/com/openworld/weapon/weapon_catalog.json")))["weapons"]


def hold_weapons(hold_name):
    """The weapons a hold covers: every catalog row with that archetype (PLAN.md 2.8 item 7 — one list)."""
    return [w["id"] for w in CATALOG if w["archetype"] == hold_name]
# Hair is left out: its strands are open cards, "inside" means nothing there, and a gun through a strand of
# hair is not what reads as a defect.
BODY_MESHES = ["armor", "head", "backpack", "headphones"]
# Vertices that belong to a hand are allowed to be inside the gun: a hand holds it.
HAND_BONE = re.compile(r"^(hand_[lr]|(thumb|index|middle|ring|pinky)_\d\d_[lr])$")
POKE_REPORT = 0.01
GRIP_FRACTION = 0.75
# The last few centimetres of the stock are the butt pad, which the pocket is derived to receive.
BUTT_PAD = 0.04


# ── constants read from the files the game reads (one owner each) ───────────────────────────────────

def _transform3d(text):
    v = [float(x) for x in text.split(",")]
    m = Matrix.Identity(4)
    for r in range(3):
        for c in range(3):
            m[r][c] = v[r * 3 + c]
    m[0][3], m[1][3], m[2][3] = v[9], v[10], v[11]
    return m


def _node_transform(path, name):
    src = open(path).read()
    m = re.search(r'\[node name="%s"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)' % re.escape(name), src)
    if m is None:
        return None
    return _transform3d(m.group(1))


def socket_of(name, visuals=VISUALS):
    return _node_transform(visuals, name)


def _vec3s(text):
    return [Vector([float(x) for x in m.split(",")]) for m in re.findall(r"Vector3\(([^)]*)\)", text)]


def mount_anchors(visuals=VISUALS):
    """{mount marker: body anchor offset (upperarm_r origin, clavicle_r frame)} -- the body scene's
    StockMountIKModifier values when it sets them, else the Java defaults. One owner per body (W25)."""
    src = open(visuals).read()
    node = re.search(r'\[node name="StockMountIKModifier"[^\]]*\](.*?)(?=\n\[|\Z)', src, re.S)
    java = open(STOCK_MOUNT).read()
    names = re.search(r"mount_markers = Array\[String\]\(\[([^\]]*)\]\)", node.group(1)) if node else None
    offs = re.search(r"mount_offsets = Array\[Vector3\]\(\[(.*?)\]\)", node.group(1)) if node else None
    if names is None:
        names = re.search(r"DEFAULT_MOUNT_MARKERS = \{([^}]*)\}", java)
    if offs is None:
        offs = re.search(r"DEFAULT_MOUNT_OFFSETS = \{(.*?)\};", java, re.S)
    keys = re.findall(r'"([^"]+)"', names.group(1))
    vals = _vec3s(offs.group(1).replace("new Vector3", "Vector3"))
    return dict(zip(keys, vals))


def weapon_markers(weapon):
    out = {}
    for n in ("StockPoint", "SupportPoint", "Muzzle", "ShoulderRestPoint"):
        t = _node_transform(WEAPON_SCENE % weapon, n)
        if t is not None:
            out[n] = t.translation.copy()
    return out


# Blender (weapon .blend) coords -> Godot weapon-local coords: (x, y, z) -> (x, z, -y).
B2G = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def body(v):
    return Vector((-v.x, v.z, v.y))


def from_body(v):
    return Vector((-v.x, v.z, v.y))


UP = Vector((0, 0, 1))  # armature space


# ── the pose as data: {bone: [loc, quat, scale]}, forward kinematics without the depsgraph ─────────

def arm_obj():
    return bpy.data.objects[ARMATURE]


def channelbag(action):
    return action.layers[0].strips[0].channelbags[0]


def pose_of(action, frame=None):
    arm = arm_obj()
    pose = {pb.name: [Vector((0, 0, 0)), Quaternion((1, 0, 0, 0)), Vector((1, 1, 1))] for pb in arm.pose.bones}
    for fc in channelbag(action).fcurves:
        if not fc.data_path.startswith('pose.bones["'):
            continue
        name = fc.data_path.split('"')[1]
        prop = fc.data_path.rsplit(".", 1)[1]
        if name not in pose:
            continue
        v = fc.keyframe_points[0].co[1] if frame is None else fc.evaluate(frame)
        slot = {"location": 0, "rotation_quaternion": 1, "scale": 2}.get(prop)
        if slot is not None:
            pose[name][slot][fc.array_index] = v
    for p in pose.values():
        p[1].normalize()
    return pose


def copy_pose(pose):
    return {k: [v[0].copy(), v[1].copy(), v[2].copy()] for k, v in pose.items()}


def fk(pose):
    arm = arm_obj()
    out = {}

    def walk(bone):
        basis = Matrix.LocRotScale(pose[bone.name][0], pose[bone.name][1], pose[bone.name][2])
        if bone.parent is None:
            out[bone.name] = bone.matrix_local @ basis
        else:
            out[bone.name] = out[bone.parent.name] @ (bone.parent.matrix_local.inverted() @ bone.matrix_local) @ basis
        for c in bone.children:
            walk(c)

    for b in arm.data.bones:
        if b.parent is None:
            walk(b)
    return out


def set_global_rotation(pose, bone_name, world_rot):
    """Set a bone's local rotation so its armature-space rotation becomes `world_rot` (a 3x3)."""
    arm = arm_obj()
    bone = arm.data.bones[bone_name]
    M = fk(pose)
    parent = M[bone.parent.name].to_3x3() if bone.parent else Matrix.Identity(3)
    rest = (bone.parent.matrix_local.inverted() @ bone.matrix_local).to_3x3() if bone.parent else bone.matrix_local.to_3x3()
    q = (rest.inverted() @ parent.inverted() @ world_rot).to_quaternion()
    if q.dot(pose[bone_name][1]) < 0:
        q.negate()
    pose[bone_name][1] = q.normalized()


def rotate_bone(pose, bone_name, world_quat):
    """Pre-multiply a bone's armature-space rotation by `world_quat` (pivot: the bone's head)."""
    M = fk(pose)
    set_global_rotation(pose, bone_name, world_quat.to_matrix() @ M[bone_name].to_3x3())


# ── measurement ──────────────────────────────────────────────────────────────────────────────────

class Rig:
    """Everything constant across poses: sockets, markers, eye centres, weapon surfaces."""

    def __init__(self, hold_name="rifle", visuals=VISUALS):
        self.hold_name = hold_name
        self.hold = HOLDS[hold_name]
        self.weapons = hold_weapons(hold_name)
        self.reference = self.hold["reference"]
        self.socket = socket_of(self.hold["socket"], visuals)
        self.anchors = mount_anchors(visuals)
        self.mount = self.hold.get("mount")
        self.markers = {w: weapon_markers(w) for w in self.weapons}
        arm = arm_obj()
        eyes = bpy.data.objects["eyes"]
        head = arm.data.bones["head"].matrix_local
        right = [eyes.matrix_world @ v.co for v in eyes.data.vertices if v.co.x < 0]
        left = [eyes.matrix_world @ v.co for v in eyes.data.vertices if v.co.x > 0]
        # Eyes are rigid on the head: carry each centre in the head bone's REST frame.
        self.eye_r = head.inverted() @ (sum(right, Vector()) / len(right))
        self.eye_l = head.inverted() @ (sum(left, Vector()) / len(left))
        self.surfaces = {w: self._weapon_points(w) for w in self.weapons}
        bl = arm.data.bones
        self.arm_len_l = ((bl["lowerarm_l"].head_local - bl["upperarm_l"].head_local).length
                          + (bl["hand_l"].head_local - bl["lowerarm_l"].head_local).length)
        # The support hand's grip point in hand_l's frame: GRIP_FRACTION of the way to the middle knuckle.
        # SupportHandIKModifier derives the same from the skeleton rest -- keep GRIP_FRACTION in step.
        self.grip_l = (bl["hand_l"].matrix_local.inverted() @ bl["middle_01_l"].head_local) * GRIP_FRACTION

    def _weapon_points(self, weapon):
        """Surface samples of the weapon model in GODOT weapon-local coords: vertices + subdivided edges.
        A primitive weapon (weapon_models.json `primitives`, no .blend) is sampled as its box."""
        prim = json.load(open(MODELS)).get("primitives", {}).get(weapon)
        if prim is not None:
            size, centre = Vector(prim["size"]), Vector(prim["center"])
            pts = []
            steps = [max(2, int(size[i] / 0.01)) for i in range(3)]
            for i in range(steps[0] + 1):
                for j in range(steps[1] + 1):
                    for k in range(steps[2] + 1):
                        u = Vector((i / steps[0], j / steps[1], k / steps[2]))
                        if any(c in (0.0, 1.0) for c in u):
                            pts.append(centre + Vector(((u.x - 0.5) * size.x, (u.y - 0.5) * size.y, (u.z - 0.5) * size.z)))
            return pts
        before = set(bpy.data.objects)
        with bpy.data.libraries.load(WEAPON_BLEND % weapon, link=False) as (src, dst):
            dst.collections = [weapon]
        pts = []
        for o in set(bpy.data.objects) - before:
            if o.type != "MESH":
                continue
            mw = B2G @ o.matrix_world
            verts = [mw @ v.co for v in o.data.vertices]
            pts.extend(verts)
            for e in o.data.edges:
                a, b = verts[e.vertices[0]], verts[e.vertices[1]]
                n = int((a - b).length / 0.01)
                for i in range(1, n):
                    pts.append(a.lerp(b, i / n))
        for o in set(bpy.data.objects) - before:
            bpy.data.objects.remove(o)
        return pts

    def gun(self, M):
        return M["hand_r"] @ self.socket

    def anchor_at(self, M, marker=None):
        """The body anchor a mount marker is put on (the shoulder pocket for StockPoint, ...), armature space."""
        off = self.anchors[marker or self.mount]
        return M["upperarm_r"].translation + M["clavicle_r"].to_3x3().normalized() @ off

    def pocket_at(self, M):
        return self.anchor_at(M, "StockPoint")

    def eye(self, M, side="r"):
        return M["head"] @ (self.eye_r if side == "r" else self.eye_l)


def yaw(v):
    return math.degrees(math.atan2(v.z, v.x))


def blade_parts(M):
    pos = lambda b: body(M[b].translation)
    hips = pos("thigh_r") - pos("thigh_l")
    shoulders = pos("upperarm_r") - pos("upperarm_l")
    chest = body(M["spine_03"].to_3x3() @ Vector((1, 0, 0)))
    if chest.dot(hips) < 0:
        chest = -chest
    return yaw(shoulders) - yaw(hips), yaw(chest) - yaw(hips), yaw(shoulders) - yaw(chest)


def gun_angles(rig, M):
    bore = body(rig.gun(M).to_3x3() @ Vector((0, 0, -1))).normalized()
    return math.degrees(math.atan2(bore.x, -bore.z)), math.degrees(math.asin(max(-1, min(1, bore.y))))


def elbow_flare(M, side="r"):
    """Angle of the elbow out from straight down, about the shoulder->wrist line (0 tucked, 90 flared)."""
    s = body(M["upperarm_%s" % side].translation)
    e = body(M["lowerarm_%s" % side].translation)
    w = body(M["hand_%s" % side].translation)
    axis = (w - s).normalized()
    off = (e - s) - axis * (e - s).dot(axis)
    down = Vector((0, -1, 0))
    down = (down - axis * down.dot(axis)).normalized()
    if off.length < 1e-6:
        return 0.0
    out = Vector((1 if side == "r" else -1, 0, 0))
    ang = math.degrees(down.angle(off.normalized()))
    return ang if off.dot(out) >= 0 else -ang


def eye_report(rig, M, weapon):
    """Right-eye centre against the bore: (lateral, vertical off the bore line, clearance over the gun's top
    at the eye's station along the gun). Negative clearance = the eye is below the top of the gun."""
    G = rig.gun(M)
    bore = (G.to_3x3() @ Vector((0, 0, -1))).normalized()
    muzzle = G @ rig.markers[weapon]["Muzzle"]
    eye = rig.eye(M)
    rel = eye - muzzle
    perp = body(rel - bore * rel.dot(bore))
    t_eye = G.inverted() @ eye
    tops = [p.y for p in rig.surfaces[weapon] if abs(p.z - t_eye.z) < 0.04 and abs(p.x) < 0.03]
    top = max(tops) if tops else max(p.y for p in rig.surfaces[weapon] if abs(p.x) < 0.03)
    return perp.x, perp.y, t_eye.y - top


def body_bvh(pose):
    """Skinned body surface at `pose` (depsgraph-evaluated), hands and fingers removed."""
    arm = arm_obj()
    apply_pose(pose)
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys, owner = [], [], []
    for name in BODY_MESHES:
        o = bpy.data.objects.get(name)
        if o is None:
            continue
        groups = {g.index: g.name for g in o.vertex_groups}
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        base = len(verts)
        verts.extend(o.matrix_world @ v.co for v in me.vertices)
        dominant = []
        for v in o.data.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            dominant.append(groups.get(best.group, "") if best else "")
        for p in me.polygons:
            # Hands stay IN the tree (a hole at the wrist makes every point inside the fist read as deep
            # inside the forearm) and are skipped when a sample's nearest face is theirs.
            bones = [dominant[i] for i in p.vertices]
            polys.append([base + i for i in p.vertices])
            owner.append("%s/%s" % (name, max(set(bones), key=bones.count)))
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys), owner


def poke(rig, M, bvh, owner, weapon, detail=False):
    G = arm_obj().matrix_world @ rig.gun(M)
    deepest, where, count = 0.0, "-", 0
    parts = {}
    mount = rig.markers[weapon].get(rig.mount) if rig.mount else None
    butt = (mount.z - BUTT_PAD) if mount is not None else float("inf")
    for p in rig.surfaces[weapon]:
        if p.z > butt:
            continue  # the butt pad is MEANT to press into the pocket
        w = G @ p
        loc, normal, idx, dist = bvh.find_nearest(w, 0.25)
        if loc is None or (w - loc).dot(normal) >= 0 or HAND_BONE.match(owner[idx].split("/")[1]):
            continue
        if dist > POKE_REPORT:
            count += 1
            d, n = parts.get(owner[idx], (0.0, 0))
            parts[owner[idx]] = (max(d, dist), n + 1)
        if dist > deepest:
            deepest, where = dist, owner[idx]
    if detail:
        for k, (d, n) in sorted(parts.items(), key=lambda kv: -kv[1][0]):
            print("      %-28s deepest %.3f m, %d samples" % (k, d, n))
    return deepest, where, count


def apply_pose(pose):
    arm = arm_obj()
    if arm.animation_data is not None:
        arm.animation_data.action = None
        arm.animation_data.use_nla = False
    for pb in arm.pose.bones:
        pb.location, pb.rotation_quaternion, pb.scale = pose[pb.name]
    bpy.context.view_layer.update()


def report(rig, pose, label, with_poke=True):
    M = fk(pose)
    blade, spine, clav = blade_parts(M)
    gy, gp = gun_angles(rig, M)
    print("── %s" % label)
    print("  blade %+.1f deg (spine_03 %+.1f, collarbones %+.1f) ; gun yaw %+.2f pitch %+.2f ; "
          "firing elbow flare %+.0f deg ; support elbow flare %+.0f deg"
          % (blade, spine, clav, gy, gp, elbow_flare(M, "r"), elbow_flare(M, "l")))
    joint = M["upperarm_r"].translation
    print("  palm(hand_r) in front of the shoulder joint %.3f m ; hand_r below joint %.3f m"
          % (body(joint).z - body(M["hand_r"].translation).z, body(joint).y - body(M["hand_r"].translation).y))
    G = rig.gun(M)
    bvh = owner = None
    if with_poke:
        bvh, owner = body_bvh(pose)
    rows = {}
    for w in rig.weapons:
        m = rig.markers[w]
        parts = ["  %-5s" % w]
        mount_d = 0.0
        if rig.mount and rig.mount in m:
            st = body(G @ m[rig.mount] - rig.anchor_at(M))
            mount_d = st.length
            parts.append("%s-anchor r %+.3f u %+.3f f %+.3f (%.3f)" % (rig.mount, st.x, st.y, -st.z, st.length))
        if "SupportPoint" in m:
            sup = G @ m["SupportPoint"]
            parts.append("support %.3f (SupportPoint %.3f from the shoulder, arm %.3f)"
                         % ((sup - M["hand_l"] @ rig.grip_l).length, (sup - M["upperarm_l"].translation).length,
                            rig.arm_len_l))
        if "Muzzle" in m:
            er, eu, clear = eye_report(rig, M, w)
            parts.append("right eye off bore r %+.3f u %+.3f, over the gun's top %+.3f" % (er, eu, clear))
        if with_poke:
            d, where, n = poke(rig, M, bvh, owner, w, detail="--poke-detail" in sys.argv)
            parts.append("poke %.3f m in %s (%d samples > 1 cm)" % (d, where, n))
            rows[w] = (mount_d, d, n)
        print(" | ".join(parts))
    return rows


# ── solving ──────────────────────────────────────────────────────────────────────────────────────

def _solve_scalar(f, target, lo, hi, iters=40):
    """Bisection on a monotone-ish scalar function; returns x with f(x) ~= target."""
    flo = f(lo) - target
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fm = f(mid) - target
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def twist_to(pose, bone, measure, target, lo=-60, hi=60):
    """Rotate `bone` about world up until `measure(fk(pose))` reads `target` (deg)."""
    base = copy_pose(pose)

    def at(deg):
        p = copy_pose(base)
        rotate_bone(p, bone, Quaternion(UP, math.radians(deg)))
        return measure(fk(p))

    deg = _solve_scalar(at, target, lo, hi)
    rotate_bone(pose, bone, Quaternion(UP, math.radians(deg)))
    return deg


def swing(pose, bone, child, target):
    """Rotate `bone` by the shortest arc that points its child's head at `target`."""
    M = fk(pose)
    head = M[bone].translation
    q = (M[child].translation - head).normalized().rotation_difference((target - head).normalized())
    rotate_bone(pose, bone, q)


def two_bone(pose, upper, lower, hand, target, pole, reach_limit=0.995):
    """Two-bone IK in armature space: elbow on the `pole` side of the shoulder->target line."""
    M = fk(pose)
    a = (M[lower].translation - M[upper].translation).length
    b = (M[hand].translation - M[lower].translation).length
    s = M[upper].translation
    d = target - s
    dist = min(d.length, (a + b) * reach_limit)
    axis = d.normalized()
    goal = s + axis * dist
    cos_a = max(-1.0, min(1.0, (a * a + dist * dist - b * b) / (2 * a * dist)))
    side = (pole - axis * pole.dot(axis)).normalized()
    elbow = s + axis * (a * cos_a) + side * (a * math.sqrt(max(0.0, 1 - cos_a * cos_a)))
    swing(pose, upper, lower, elbow)
    swing(pose, lower, hand, goal)
    return (target - goal).length


def pole_for(M, side, flare_deg, back=0.0):
    """A pole: straight down, turned OUT by `flare_deg` about the body's forward axis, then pushed back."""
    out = Vector((1 if side == "r" else -1, 0, 0))
    down = Vector((0, -1, 0))
    v = down * math.cos(math.radians(flare_deg)) + out * math.sin(math.radians(flare_deg)) + Vector((0, 0, back))
    return from_body(v.normalized())


def set_hand(pose, hand, world_rot):
    set_global_rotation(pose, hand, world_rot)


def minimise(cost, x, step=8.0, floor=0.05):
    """Coordinate descent with step halving: small, derivative-free, and enough for 3 smooth angles."""
    x = list(x)
    best = cost(x)
    while step > floor:
        improved = False
        for i in range(len(x)):
            for d in (step, -step):
                y = list(x)
                y[i] += d
                c = cost(y)
                if c < best:
                    x, best, improved = y, c, True
        if not improved:
            step *= 0.5
    return x


def args_after_dashdash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(args, name, default):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        return type(default)(v) if not isinstance(default, bool) else True
    return default


def param(rig, a, kind, name, default):
    """A solve argument: the command line wins, then the archetype's row in weapon_archetypes.json."""
    flag = "--" + name.replace("_", "-")
    if flag in a:
        if isinstance(default, (list, bool)):
            return a[a.index(flag) + 1] if not isinstance(default, bool) else True
        return opt(a, flag, default)
    return rig.hold.get(kind, {}).get(name, default)


def level_forward():
    """The gun's rotation for a bore on the body's forward line, level and uncanted (armature space)."""
    return Matrix((from_body(Vector((1, 0, 0))), from_body(Vector((0, 1, 0))), from_body(Vector((0, 0, 1))))).transposed()


def solve_aim(rig, pose, a):
    """An archetype's aim pose, from the artist's pose: keep the choices, solve the facts.

    Order matters and each step reads the result of the previous one: the blade places the collarbones,
    the collarbones place the body anchor, the anchor (or a placed model, or the eye line) places the gun,
    the gun places both hands and the eye the head is brought to.

    Placements (`placement` in the archetype row, or --placed OBJECT):
      placed    a weapon model the artist put in the scene IS the gun; the torso and head are left as authored
      mount     the weapon's mount marker on the body anchor, bore level and forward (rifle stock, launcher tube)
      eye_line  no mount: the bore `sight_drop` under the right eye, the grip `reach` ahead of the shoulder (pistol)
    """
    placement = param(rig, a, "aim", "placement", "mount")
    placed = opt(a, "--placed", "")
    if placed:
        placement = "placed"
    spine_share = param(rig, a, "aim", "spine", 24.0)
    clav_share = param(rig, a, "aim", "collarbones", 8.0)
    shrug = param(rig, a, "aim", "shrug", 0.0)
    flare_r = param(rig, a, "aim", "elbow_flare", 40.0)
    flare_l = param(rig, a, "aim", "support_flare", 15.0)
    eye_clear = param(rig, a, "aim", "eye_clearance", 0.035)
    head_share = param(rig, a, "aim", "head_lean", 0.5)
    ref = rig.reference
    m = rig.markers[ref]
    M0 = fk(pose)
    # the support hand's grip on the gun as the ARTIST left it: relative to the placed model when there is one
    gun_before = object_gun(placed) if placement == "placed" else rig.gun(M0)
    rel = gun_before.to_3x3().normalized().inverted() @ M0["hand_l"].to_3x3()

    if placement != "placed":
        # 1. the blade, in the TORSO: spine_03 twists, the collarbones do only a little (the left one reaches)
        twist_to(pose, "spine_03", lambda M: blade_parts(M)[1], spine_share)
        twist_to(pose, "clavicle_l", lambda M: blade_parts(M)[2], clav_share)
        if shrug:  # a shrug of the firing collarbone lifts the anchor toward the cheek
            rotate_bone(pose, "clavicle_r", Quaternion(from_body(Vector((0, 0, -1))), math.radians(-shrug)))

    # 2. the gun
    M = fk(pose)
    gun_rot = level_forward()
    if placement == "placed":
        gun = object_gun(placed)
    elif placement == "mount":
        gun = Matrix.LocRotScale(rig.anchor_at(M) - gun_rot @ m[rig.mount], gun_rot.to_quaternion(), None)
    elif placement == "eye_line":
        reach = param(rig, a, "aim", "reach", 0.36)
        drop = param(rig, a, "aim", "sight_drop", 0.08)
        eye = body(rig.eye(M))
        joint = body(M["upperarm_r"].translation)
        bore_at_grip = Vector((eye.x, eye.y - drop, joint.z - reach))
        grip = bore_at_grip - Vector((0, m["Muzzle"].y, 0))
        gun = Matrix.LocRotScale(from_body(grip), gun_rot.to_quaternion(), None)
    else:
        raise SystemExit("unknown placement %r" % placement)
    hand_target = gun @ rig.socket.inverted()

    # 3. firing arm to the grip, elbow flared the chosen amount
    for _ in range(3):  # the pocket rides the collarbone, which the arm does not move -- converges in one
        two_bone(pose, "upperarm_r", "lowerarm_r", "hand_r", hand_target.translation, pole_for(fk(pose), "r", flare_r, 0.35))
        set_hand(pose, "hand_r", hand_target.to_3x3())

    # 4. support arm to the weapon's SupportPoint, keeping the artist's grip orientation relative to the gun
    short = 0.0
    sup_local = m.get("SupportPoint", Vector()).copy()
    if opt(a, "--support-z", 0.0) != 0.0:
        sup_local.z = opt(a, "--support-z", 0.0)
    hand_rot = gun.to_3x3() @ rel
    sup = gun @ sup_local
    if "SupportPoint" not in m:
        print("    %s declares no SupportPoint: the support arm is left as authored" % ref)
    else:
        # SupportPoint is where the hand GRIPS (the knuckle line), not where the wrist is: the wrist target is
        # the grip point pulled back through the hand's kept orientation (SupportHandIKModifier does the same).
        short = two_bone(pose, "upperarm_l", "lowerarm_l", "hand_l", sup - hand_rot @ rig.grip_l,
                         pole_for(fk(pose), "l", flare_l, 0.2))
        set_hand(pose, "hand_l", hand_rot)
        curl = param(rig, a, "aim", "curl", 1.0)
        if curl:
            curl_fingers(pose, curl, Vector((opt(a, "--curl-axis-sign", 1.0), 0, 0)))
        Ms = fk(pose)
        shoulder_l = Ms["upperarm_l"].translation
        reach = 0.99 * rig.arm_len_l
        z = sup_local.z
        while z < 0.0 and (gun @ Vector((sup_local.x, sup_local.y, z)) - hand_rot @ rig.grip_l - shoulder_l).length > reach:
            z += 0.005
        print("    support grip: this arm reaches %.3f m ahead of the firing grip (SupportPoint at %.3f)" % (-z, -sup_local.z))

    # 5. head: bring the right eye over the bore, `eye_clear` above the gun's top, with the eye line square
    #    to the aim. Three gestures, each shared between the neck and the head the way a neck moves: a NOD
    #    (flex), a TILT toward the stock (lateral bend) and a turn. Minimised together, from the arm-solved
    #    pose each time (never accumulated), preferring the smallest gesture that does the job.
    def face_yaw(M):  # the eye line square to the aim = the face looks down the gun
        return yaw(body(rig.eye(M, "r") - rig.eye(M, "l")))

    if placement == "placed" or "Muzzle" not in m or not param(rig, a, "aim", "head", True):
        return short  # the artist placed the gun against the head they posed: leave the head as authored

    right_axis = from_body(Vector((1, 0, 0)))
    fwd = from_body(Vector((0, 0, -1)))
    base = copy_pose(pose)

    def head_pose(x):
        nod, tilt, turn = x
        p = copy_pose(base)
        rotate_bone(p, "neck_01", Quaternion(UP, math.radians(turn * 0.4)))
        rotate_bone(p, "neck_01", Quaternion(fwd, math.radians(tilt * 0.4)))
        rotate_bone(p, "neck_01", Quaternion(right_axis, math.radians(-nod * (1 - head_share))))
        rotate_bone(p, "head", Quaternion(UP, math.radians(turn * 0.6)))
        rotate_bone(p, "head", Quaternion(fwd, math.radians(tilt * 0.6)))
        rotate_bone(p, "head", Quaternion(right_axis, math.radians(-nod * head_share)))
        return p

    def cost(x):
        M = fk(head_pose(x))
        lat, _, clear = eye_report(rig, M, ref)
        nod, tilt, turn = x
        # a neck's comfortable range: flex 0..35, lateral bend to 18, turn to 50. Past it the head reads as
        # broken, so it costs far more than a centimetre of weld.
        over = (max(0.0, nod - 35) + max(0.0, -nod) + max(0.0, abs(tilt) - 18) + max(0.0, abs(turn) - 50))
        return ((lat / 0.01) ** 2 + ((clear - eye_clear) / 0.01) ** 2 + (face_yaw(M) / 5.0) ** 2
                + 0.002 * sum(v * v for v in x) + (over / 0.5) ** 2)

    x = minimise(cost, [0.0, 0.0, 0.0], step=8.0)
    pose.clear()
    pose.update(head_pose(x))
    M = fk(pose)
    print("    head: nod %.1f deg, tilt toward the stock %.1f deg, turn %.1f deg -> eye lat %+.3f, over the "
          "gun's top %+.3f, eye line %+.1f deg" % (x[0], x[1], x[2], eye_report(rig, M, ref)[0],
                                                 eye_report(rig, M, ref)[2], face_yaw(M)))
    return short


def solve_hold(rig, pose, a):
    """The non-combat carry: the GRIP placed relative to the firing shoulder, muzzle down and across the body.
    (A forward low ready was measured first and the support hand cannot reach it -- CLAUDE.md W24.)"""
    drop = param(rig, a, "hold", "muzzle_down", 35.0)
    across = param(rig, a, "hold", "muzzle_across", 12.0)
    flare_r = param(rig, a, "hold", "elbow_flare", 20.0)
    flare_l = param(rig, a, "hold", "support_flare", 10.0)
    clav_share = param(rig, a, "hold", "collarbones", 0.0)
    grip = param(rig, a, "hold", "grip", [0.0, -0.25, 0.2])
    if isinstance(grip, str):
        grip = [float(v) for v in grip.split(",")]
    m = rig.markers[rig.reference]
    M_old = fk(pose)
    rel = rig.gun(M_old).to_3x3().normalized().inverted() @ M_old["hand_l"].to_3x3()
    if clav_share:
        twist_to(pose, "clavicle_l", lambda M: blade_parts(M)[2], clav_share)
    M = fk(pose)
    joint = body(M["upperarm_r"].translation)
    q = Quaternion(Vector((0, 1, 0)), math.radians(across)) @ Quaternion(Vector((1, 0, 0)), math.radians(-drop))
    gun_rot = level_forward() @ q.to_matrix()
    gun = Matrix.LocRotScale(from_body(joint + Vector((grip[0], grip[1], -grip[2]))), gun_rot.to_quaternion(), None)
    hand_target = gun @ rig.socket.inverted()
    two_bone(pose, "upperarm_r", "lowerarm_r", "hand_r", hand_target.translation, pole_for(M, "r", flare_r, 0.3))
    set_hand(pose, "hand_r", hand_target.to_3x3())
    short = 0.0
    if "SupportPoint" in m:
        hand_rot = gun.to_3x3() @ rel
        short = two_bone(pose, "upperarm_l", "lowerarm_l", "hand_l", gun @ m["SupportPoint"] - hand_rot @ rig.grip_l,
                         pole_for(fk(pose), "l", flare_l, 0.2))
        set_hand(pose, "hand_l", hand_rot)
        curl = param(rig, a, "hold", "curl", 1.0)
        if curl:
            curl_fingers(pose, curl, Vector((opt(a, "--curl-axis-sign", 1.0), 0, 0)))
    return short


# ── writing back ─────────────────────────────────────────────────────────────────────────────────

FINGERS_L = ["%s_%02d_l" % (f, j) for f in ("index", "middle", "ring", "pinky") for j in (1, 2, 3)]
SOLVED_BONES = ["spine_03", "clavicle_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
                "upperarm_l", "lowerarm_l", "hand_l", "neck_01", "head"] + FINGERS_L


def curl_fingers(pose, amount, axis=Vector((1, 0, 0))):
    """Close the support hand round the handguard: each finger joint flexes about its own local axis to a
    target angle from the REST pose (knuckle 45, middle 60, tip 40 deg at amount 1). Absolute, not added
    to the clip's curl, so re-running the solve cannot keep closing the fist."""
    per_joint = {1: 45.0, 2: 60.0, 3: 40.0}
    for b in FINGERS_L:
        if b in pose:
            pose[b][1] = Quaternion(axis, math.radians(per_joint[int(b.split("_")[1])] * amount))


def write_pose(action, old, new, frame_ref):
    """Write the solved rotations into the action. A static clip (one key) takes them outright; an animated
    one (the hold's breathing) takes the same LOCAL delta at every key, so its motion survives."""
    cb = channelbag(action)
    changed = []
    for bone in SOLVED_BONES:
        delta = new[bone][1] @ old[bone][1].inverted()
        if abs(delta.angle) < 1e-5:
            continue
        curves = [cb.fcurves.find('pose.bones["%s"].rotation_quaternion' % bone, index=i) for i in range(4)]
        if any(c is None for c in curves):
            curves = [cb.fcurves.new('pose.bones["%s"].rotation_quaternion' % bone, index=i, group_name=bone)
                      for i in range(4)]
            for i, c in enumerate(curves):
                c.keyframe_points.insert(frame_ref, old[bone][1][i])
        frames = sorted({k.co[0] for c in curves for k in c.keyframe_points})
        prev = None
        for f in frames:
            q_old = Quaternion([c.evaluate(f) for c in curves]).normalized()
            q = (delta @ q_old).normalized()
            if prev is not None and q.dot(prev) < 0:
                q.negate()
            prev = q
            for i, c in enumerate(curves):
                for k in c.keyframe_points:
                    if abs(k.co[0] - f) < 1e-4:
                        k.co[1] = q[i]
        for c in curves:
            c.update()
        changed.append("%s %.1f deg" % (bone, math.degrees(delta.angle)))
    print("  wrote %s: %s" % (action.name, ", ".join(changed)))


def render(rig, pose, out_dir, weapons=("ASR1",), tag="pose"):
    """Workbench renders of the posed body holding the gun(s): front, side, top, three-quarter, and the
    over-the-shoulder view the game's TPS camera has. Never saved: call after any --save."""
    os.makedirs(out_dir, exist_ok=True)
    apply_pose(pose)
    M = fk(pose)
    arm = arm_obj()
    before = set(bpy.data.objects)
    for w in [w for w in weapons if w]:
        G = arm.matrix_world @ rig.gun(M) @ B2G
        prim = json.load(open(MODELS)).get("primitives", {}).get(w)
        if prim is not None:  # a primitive weapon: a box of its size, in Blender weapon coords
            me = bpy.data.meshes.new(w)
            sz, c = Vector(prim["size"]), Vector(prim["center"])
            bl_c, bl_s = Vector((c.x, -c.z, c.y)), Vector((sz.x, sz.z, sz.y))
            corners = [bl_c + Vector((sx * bl_s.x, sy * bl_s.y, sz_ * bl_s.z)) * 1.0
                       for sx in (-0.5, 0.5) for sy in (-0.5, 0.5) for sz_ in (-0.5, 0.5)]
            faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
            me.from_pydata(corners, [], faces)
            ob = bpy.data.objects.new(w, me)
            bpy.context.scene.collection.objects.link(ob)
            ob.matrix_world = G
            continue
        with bpy.data.libraries.load(WEAPON_BLEND % w, link=False) as (src, dst):
            dst.collections = [w]
        col = [c for c in bpy.data.collections if c.name.split(".")[0] == w][-1]
        bpy.context.scene.collection.children.link(col)
        for o in col.all_objects:
            o.matrix_world = G @ o.matrix_world
    weapons_added = {o.name for o in set(bpy.data.objects) - before}
    if "--show-placed" in sys.argv:
        weapons_added |= {o.name for o in before}
    known = {w for h in HOLDS for w in hold_weapons(h)}
    for o in bpy.data.objects:
        if o.name == "Icosphere" or (o.name.split(".")[0] in known and o.name not in weapons_added):
            o.hide_render = True
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x, scene.render.resolution_y = 900, 900
    scene.render.film_transparent = False
    cam_data = bpy.data.cameras.new("probe_cam")
    cam = bpy.data.objects.new("probe_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    # frame the upper body and the gun: halfway between the chest and the gun's grip, a little up
    chest = arm.matrix_world @ ((M["spine_03"].translation + rig.gun(M).translation) * 0.5 + Vector((0, 0, 0.08)))
    views = {
        # body-frame offsets from the chest: +x right, +y up, +z BEHIND
        "front": Vector((-0.25, 0.1, -1.2)),
        "right": Vector((1.2, 0.1, -0.1)),
        "left": Vector((-1.2, 0.1, -0.1)),
        "top": Vector((0.05, 1.3, 0.05)),
        "threequarter": Vector((0.85, 0.3, -0.85)),
        "tps": Vector((0.55, 0.3, 1.0)),
    }
    for name, off in views.items():
        cam.location = chest + from_body(off)
        target = chest + (from_body(Vector((0.1, 0.0, -1.0))) if name == "tps" else Vector())
        direction = target - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = 40
        scene.render.filepath = os.path.join(out_dir, "%s_%s.png" % (tag, name))
        bpy.ops.render.render(write_still=True)
    names = " ".join(os.path.join(out_dir, "%s_%s.png" % (tag, n)) for n in views)
    os.system("montage %s -tile 3x%d -geometry 600x600+2+2 %s" % (names, (len(views) + 2) // 3, os.path.join(out_dir, "%s_sheet.png" % tag)))
    print("  rendered %s/%s_sheet.png" % (out_dir, tag))


def object_gun(name):
    """A weapon model placed by hand in the scene (origin = grip, W19) as a gun transform in armature space."""
    o = bpy.data.objects[name]
    return arm_obj().matrix_world.inverted() @ o.matrix_world @ B2G.inverted()


def compare_placed(rig, pose, name):
    """Where the artist put the weapon model vs where the clip's hand holds it, and the body anchor it implies."""
    M = fk(pose)
    G_obj = object_gun(name)
    G_clip = rig.gun(M)
    d = body(G_obj.translation - G_clip.translation)
    turn = math.degrees(G_clip.to_quaternion().rotation_difference(G_obj.to_quaternion()).angle)
    bore = body(G_obj.to_3x3() @ Vector((0, 0, -1))).normalized()
    up = body(G_obj.to_3x3() @ Vector((0, 1, 0))).normalized()
    print("── placed %s vs the clip's grip: move r %+.3f u %+.3f f %+.3f (%.3f m), turn %.1f deg ; bore yaw %+.2f pitch %+.2f cant %+.1f"
          % (name, d.x, d.y, -d.z, d.length, turn, math.degrees(math.atan2(bore.x, -bore.z)),
             math.degrees(math.asin(max(-1, min(1, bore.y)))), math.degrees(math.atan2(-up.x, up.y))))
    m = rig.markers[rig.reference]
    implied = None
    if rig.mount and rig.mount in m:
        st = body(G_obj @ m[rig.mount] - rig.anchor_at(M))
        cb = M["clavicle_r"].to_3x3().normalized()
        implied = cb.inverted() @ (G_obj @ m[rig.mount] - M["upperarm_r"].translation)
        print("   %s vs its anchor r %+.3f u %+.3f f %+.3f ; implied anchor (clavicle_r frame) (%.4f, %.4f, %.4f) [now %s]"
              % (rig.mount, st.x, st.y, -st.z, implied.x, implied.y, implied.z,
                 tuple(round(x, 4) for x in rig.anchors[rig.mount])))
    if "Muzzle" in m:
        er, _, clear = eye_report(rig_with_gun(rig, G_obj), M, rig.reference)
        print("   right eye off bore r %+.3f, over the top %+.3f" % (er, clear))
    return G_obj, implied


def rig_with_gun(rig, G):
    class R:
        pass
    r = R()
    r.__dict__.update(rig.__dict__)
    r.gun = lambda M: G
    r.eye = rig.eye
    return r


def adopt_placed(rig, pose, name):
    """The artist posed the hands around a placed model: derive the DATA that reproduces it in game instead
    of re-solving the pose. Returns (socket, anchor offset, support grip point in weapon coords)."""
    M = fk(pose)
    G = object_gun(name) if name else rig.gun(M)  # no placed model: the clip's own grip is the truth
    socket = M["hand_r"].inverted() @ G
    socket_q = socket.to_quaternion()
    old_q = rig.socket.to_quaternion()
    print("   socket %s: move %.3f m, turn %.1f deg from the current one"
          % (rig.hold["socket"], (socket.translation - rig.socket.translation).length,
             math.degrees(old_q.rotation_difference(socket_q).angle)))
    m = rig.markers[rig.reference]
    anchor = None
    if rig.mount and rig.mount in m:
        anchor = M["clavicle_r"].to_3x3().normalized().inverted() @ (G @ m[rig.mount] - M["upperarm_r"].translation)
    grip = G.inverted() @ (M["hand_l"] @ rig.grip_l)
    print("   support grip in %s coords (%.4f, %.4f, %.4f)  [SupportPoint now %s]"
          % (rig.reference, grip.x, grip.y, grip.z, tuple(round(x, 4) for x in m.get("SupportPoint", Vector()))))
    return socket, anchor, grip


def _godot_transform_text(M):
    r = [M[i][j] for i in range(3) for j in range(3)]  # ROW-major, like the .tscn
    return "Transform3D(%s)" % ", ".join("%.8g" % v for v in r + [M[0][3], M[1][3], M[2][3]])


def write_node_transform(path, node, M):
    src = open(path).read()
    pat = r'(\[node name="%s"[^\]]*\]\s*\ntransform = )Transform3D\([^)]*\)' % re.escape(node)
    new, n = re.subn(pat, lambda mm: mm.group(1) + _godot_transform_text(M), src)
    if n != 1:
        raise SystemExit("no single %s transform in %s" % (node, path))
    open(path, "w").write(new)
    print("  wrote %s transform into %s" % (node, os.path.relpath(path, ROOT)))


def insert_marker(path, name, pos):
    """Add a Marker3D child of the weapon root before its Model instance (unique_id derived from the name)."""
    src = open(path).read()
    uid = abs(hash(os.path.basename(path) + name)) % 900000000 + 100000000
    node = ('[node name="%s" type="Marker3D" parent="." unique_id=%d]\ntransform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, '
            '%.5f, %.5f, %.5f)\n\n' % (name, uid, pos.x, pos.y, pos.z))
    i = src.index('[node name="Model"')
    open(path, "w").write(src[:i] + node + src[i:])
    print("  added %s to %s" % (name, os.path.relpath(path, ROOT)))


def write_anchors(anchors, visuals_paths):
    """Write {marker: offset} into each body scene's StockMountIKModifier (the per-body owner of the anchors)."""
    names = list(anchors)
    line_m = 'mount_markers = Array[String]([%s])' % ", ".join('"%s"' % n for n in names)
    line_o = 'mount_offsets = Array[Vector3]([%s])' % ", ".join(
        "Vector3(%.4f, %.4f, %.4f)" % tuple(anchors[n]) for n in names)
    for path in visuals_paths:
        src = open(path).read()
        head = re.search(r'\[node name="StockMountIKModifier"[^\]]*\]\n', src)
        end = src.find("\n[", head.end())
        block = src[head.end():end]
        block = re.sub(r"mount_markers = .*\n", "", block)
        block = re.sub(r"mount_offsets = .*\n", "", block)
        block = block.rstrip("\n") + "\n" + line_m + "\n" + line_o + "\n"
        open(path, "w").write(src[:head.end()] + block + src[end:])
        print("  wrote mount anchors into %s" % os.path.relpath(path, ROOT))


VISUALS_ALL = [VISUALS, VISUALS.replace("CharacterVisuals_GodotChan.tscn", "CharacterVisuals_GodotChanF.tscn")]


def skin_shoulder_top(pose):
    """The top of the firing shoulder, off the skinned body: the highest `armor` vertex within 5 cm of the
    shoulder joint in plan, as an anchor offset (upperarm_r origin, clavicle_r frame). Where a tube rests."""
    apply_pose(pose)
    M = fk(pose)
    dg = bpy.context.evaluated_depsgraph_get()
    o = bpy.data.objects["armor"]
    me = o.evaluated_get(dg).to_mesh()
    joint = M["upperarm_r"].translation
    jb = body(joint)
    best = None
    for v in me.vertices:
        w = arm_obj().matrix_world.inverted() @ (o.matrix_world @ v.co)
        b = body(w)
        if (Vector((b.x, b.z)) - Vector((jb.x, jb.z))).length < 0.05 and (best is None or b.y > body(best).y):
            best = w
    o.evaluated_get(dg).to_mesh_clear()
    off = M["clavicle_r"].to_3x3().normalized().inverted() @ (best - joint)
    d = body(best) - jb
    print("  shoulder top: body r %+.3f u %+.3f f %+.3f of the joint -> anchor (clavicle_r frame) (%.4f, %.4f, %.4f)"
          % (d.x, d.y, -d.z, off.x, off.y, off.z))
    return off


# ── whole-clip edits: symmetry and hip sway (crawl, 2026-09-15) ─────────────────────────────────────────

MIRROR_S = Matrix(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))  # armature X-mirror (the rig is X-symmetric to 0.0002)


def mirror_name(n):
    return n[:-2] + "_r" if n.endswith("_l") else n[:-2] + "_l" if n.endswith("_r") else n


def mirror_basis(bone, loc, quat):
    """The pose basis bone `mirror_name(bone)` needs to mirror `bone`'s basis across the body's midplane."""
    B = arm_obj().data.bones
    src, dst = B[bone].matrix_local.to_3x3(), B[mirror_name(bone)].matrix_local.to_3x3()
    A = src.inverted() @ MIRROR_S @ dst            # a reflection taking dst's frame to src's
    R = A @ quat.to_matrix() @ A.inverted()
    return (A @ loc), R.to_quaternion()


def action_frames(action):
    return sorted({round(k.co[0], 4) for fc in channelbag(action).fcurves for k in fc.keyframe_points})


def symmetrize_pose(pose):
    out = copy_pose(pose)
    B = arm_obj().data.bones
    for n in pose:
        if n == "Root" or B[n].parent is None:
            continue
        m = mirror_name(n)
        if m not in pose:
            continue
        ml, mq = mirror_basis(m, pose[m][0], pose[m][1])  # the partner's pose, expressed as this bone's
        q = pose[n][1].slerp(mq if mq.dot(pose[n][1]) >= 0 else -mq, 0.5).normalized()
        out[n] = [(pose[n][0] + ml) * 0.5, q, pose[n][2].copy()]
    return out


def hip_yaw(M):
    tl, tr = body(M["thigh_l"].translation), body(M["thigh_r"].translation)
    return math.degrees(math.atan2(tr.z - tl.z, tr.x - tl.x))


def damp_hip_yaw(pose, factor, keep="spine_03"):
    """Turn the pelvis about world up by -factor * its hip yaw, then give `keep` back its world orientation, so
    the chest (and the aim hanging off it) does not move while the hips swing less."""
    M = fk(pose)
    keep_rot = M[keep].to_3x3().copy()
    y = hip_yaw(M)
    # hip_yaw is measured in the body frame; a +yaw there is a rotation about armature -Z (body up is +Z,
    # body x is -armature x), so undo it about armature up with the matching sign
    for sign in (1.0, -1.0):
        trial = copy_pose(pose)
        rotate_bone(trial, "pelvis", Quaternion(UP, math.radians(sign * factor * y)))
        if abs(hip_yaw(fk(trial))) < abs(y) or abs(y) < 1e-6:
            break
    rotate_bone(pose, "pelvis", Quaternion(UP, math.radians(sign * factor * y)))
    set_global_rotation(pose, keep, keep_rot)
    return y, hip_yaw(fk(pose))


def write_frames(action, poses, bones):
    """Write per-frame poses {frame: pose} for `bones` into the action (inserting keys where a curve lacks one)."""
    cb = channelbag(action)
    for bone in bones:
        for prop, size, slot in (("rotation_quaternion", 4, 1), ("location", 3, 0)):
            path = 'pose.bones["%s"].%s' % (bone, prop)
            curves = [cb.fcurves.find(path, index=i) for i in range(size)]
            if any(c is None for c in curves):
                if prop == "location":
                    continue
                curves = [cb.fcurves.new(path, index=i, group_name=bone) for i in range(size)]
            prev = None
            for f in sorted(poses):
                v = poses[f][bone][slot]
                if prop == "rotation_quaternion":
                    v = v.copy()
                    if prev is not None and v.dot(prev) < 0:
                        v.negate()
                    prev = v
                for i, c in enumerate(curves):
                    key = next((k for k in c.keyframe_points if abs(k.co[0] - f) < 1e-3), None)
                    if key is None:
                        c.keyframe_points.insert(f, v[i], options={"FAST"})
                    else:
                        key.co[1] = v[i]
            for c in curves:
                c.update()


def clip_report(action, label):
    frames = action_frames(action)
    yaws, asym = [], []
    for f in frames:
        M = fk(pose_of(action, f))
        yaws.append(hip_yaw(M))
        s3 = body(M["spine_03"].translation).x
        kl, kr = body(M["calf_l"].translation).x - s3, body(M["calf_r"].translation).x - s3
        asym.append(kl + kr)   # 0 = the knees sit symmetric about the chest
    print("  %-30s %-10s hip yaw mean %+6.1f  p2p %5.1f | knee asymmetry mean %+.3f m  p2p %.3f m  (%d frames)"
          % (action.name, label, sum(yaws) / len(yaws), max(yaws) - min(yaws), sum(asym) / len(asym),
             max(asym) - min(asym), len(frames)))


G2B = B2G.inverted()  # Godot skeleton / weapon axes -> Blender armature axes (the same axis change as a weapon's)


def pose_from_dump(frame):
    """A pose dict from an in-game FINAL pose dump (probe_crawl_balance.gd --dump): skeleton-space bone transforms,
    after every aim/IK modifier, converted to Blender pose-bone basis transforms."""
    arm = arm_obj()
    def mat(v):
        m = Matrix.Identity(4)
        for r in range(3):
            for c in range(3):
                m[r][c] = v[r * 3 + c]
        m[0][3], m[1][3], m[2][3] = v[9], v[10], v[11]
        return m
    glob = {}
    for name, v in frame.items():
        if name == "__gun__":
            continue
        bl = name if name in arm.data.bones else re.sub(r"_\d+$", "", name)
        if bl in arm.data.bones:
            glob[bl] = G2B @ mat(v)  # the axis change sits on the ROOT joint only: bone frames are shared
    pose = {}
    for bone in arm.data.bones:
        B = glob.get(bone.name)
        if B is None:
            pose[bone.name] = [Vector((0, 0, 0)), Quaternion((1, 0, 0, 0)), Vector((1, 1, 1))]
            continue
        if bone.parent is None:
            basis = bone.matrix_local.inverted() @ B
        else:
            PB = glob.get(bone.parent.name, bone.parent.matrix_local)
            basis = (bone.parent.matrix_local.inverted() @ bone.matrix_local).inverted() @ PB.inverted() @ B
        loc, rot, sc = basis.decompose()
        pose[bone.name] = [loc, rot, sc]
    gun = G2B @ mat(frame["__gun__"]) if "__gun__" in frame else None
    return pose, gun


def main():
    a = args_after_dashdash()
    cmd = a[0] if a else "measure"
    if cmd in ("symmetrize", "damp-hip-yaw", "clip-report"):
        names = opt(a, "--action", "crawl_idle-loop").split(",")
        for n in names:
            action = bpy.data.actions[n]
            clip_report(action, "before")
            if cmd == "clip-report":
                continue
            frames = action_frames(action)
            poses = {}
            for f in frames:
                pose = pose_of(action, f)
                if cmd == "symmetrize":
                    pose = symmetrize_pose(pose)
                else:
                    damp_hip_yaw(pose, opt(a, "--factor", 0.75))
                poses[f] = pose
            bones = [b.name for b in arm_obj().data.bones if b.name != "Root"] if cmd == "symmetrize" else \
                ["pelvis", "spine_03"]
            if "--write" in a:
                write_frames(action, poses, bones)
                clip_report(action, "after")
        if "--save" in a:
            arm = arm_obj()
            if arm.animation_data is not None:
                arm.animation_data.action = None
            bpy.ops.wm.save_mainfile()
            print("  saved %s" % bpy.data.filepath)
        return
    if cmd == "render-dump":
        data = json.load(open(a[1]))
        rig = Rig(opt(a, "--hold", "rifle"))
        keys = [k for k in sorted(data["frames"]) if all(t in k for t in opt(a, "--match", "").split(",") if t)]
        for k in keys[:opt(a, "--max", 4)]:
            pose, gun = pose_from_dump(data["frames"][k])
            r = rig_with_gun(rig, gun) if gun is not None else rig
            render(r, pose, opt(a, "--render", "/tmp"), [data["weapon"]] if gun is not None else [],
                   k.replace(" ", "_"))
        return
    if cmd == "remove-object":
        for n in a[1:]:
            if n.startswith("--"):
                break
            o = bpy.data.objects.get(n)
            if o is None:
                print("  no object %s" % n)
                continue
            me = o.data
            bpy.data.objects.remove(o)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
            print("  removed object %s" % n)
        if "--save" in a:
            bpy.ops.wm.save_mainfile()
            print("  saved %s" % bpy.data.filepath)
        return
    if cmd == "body-anchor":  # body-frame offset (right, up, forward of the shoulder joint) -> clavicle_r frame
        r, u, f = [float(x) for x in a[1:4]]
        M = fk(pose_of(bpy.data.actions["upright_hold_rifle-loop"], 0.0))
        off = M["clavicle_r"].to_3x3().normalized().inverted() @ from_body(Vector((r, u, -f)))
        print("  anchor (clavicle_r frame) (%.4f, %.4f, %.4f)" % tuple(off))
        return
    if cmd == "skin-anchor":
        rig = Rig("rifle")
        skin_shoulder_top(pose_of(bpy.data.actions["upright_hold_rifle-loop"], 0.0))
        return
    if cmd == "copy-from":
        copy_actions(a[1], a[2:])
        return
    rig = Rig(opt(a, "--hold", "rifle"))
    kind = "hold" if cmd == "solve-hold" else "aim"
    name = opt(a, "--action", rig.hold["%s_clip" % kind])
    action = bpy.data.actions[name]
    frame = opt(a, "--frame", -1.0)
    frame = None if frame < 0 else frame
    at = frame if frame is not None else (action.frame_range[0] if kind == "hold" else None)
    old = pose_of(action, at)
    print("== %s  hold %s  %s (mtime %s)" % (bpy.data.filepath, rig.hold_name, name, os.path.getmtime(bpy.data.filepath)))
    report(rig, old, "as authored", with_poke="--no-poke" not in a)
    weapons = opt(a, "--weapons", rig.reference).split(",")
    if cmd == "measure":
        if opt(a, "--placed", ""):
            compare_placed(rig, old, opt(a, "--placed", ""))
        if "--render" in a:
            render(rig, old, opt(a, "--render", ""), weapons, opt(a, "--tag", "authored"))
        return
    new = copy_pose(old)
    implied = None
    if opt(a, "--placed", ""):
        _, implied = compare_placed(rig, old, opt(a, "--placed", ""))
    if cmd == "adopt":
        socket, anchor, grip = adopt_placed(rig, old, opt(a, "--placed", ""))
        if "--apply" in a:
            for v in VISUALS_ALL if opt(a, "--placed", "") else []:
                write_node_transform(v, rig.hold["socket"], socket)
            if anchor is not None:
                anchors = dict(rig.anchors)
                anchors[rig.mount] = anchor
                write_anchors(anchors, VISUALS_ALL)
            if "SupportPoint" in rig.markers[rig.reference]:
                write_node_transform(WEAPON_SCENE % rig.reference, "SupportPoint", Matrix.Translation(grip))
            else:
                insert_marker(WEAPON_SCENE % rig.reference, "SupportPoint", grip)
        return
    short = (solve_aim if kind == "aim" else solve_hold)(rig, new, a)
    report(rig, new, "solved (support hand short of its target by %.3f m)" % short, with_poke="--no-poke" not in a)
    if "--write" in a:
        write_pose(action, old, new, action.frame_range[0])
        check = pose_of(action, at)
        worst = max(math.degrees(check[b][1].rotation_difference(new[b][1]).angle) for b in SOLVED_BONES)
        print("  read back: worst bone %.4f deg from the solve" % worst)
        if implied is not None and "--apply-anchor" in a:
            anchors = dict(rig.anchors)
            anchors[rig.mount] = implied
            write_anchors(anchors, VISUALS_ALL)
        if "--save" in a:
            arm = arm_obj()
            if arm.animation_data is not None:
                arm.animation_data.action = None
                arm.animation_data.use_nla = True
            bpy.ops.wm.save_mainfile()
            print("  saved %s" % bpy.data.filepath)
    if "--render" in a:
        render(rig, new, opt(a, "--render", ""), weapons, opt(a, "--tag", cmd))


def copy_actions(src_blend, a):
    """Replace this .blend's long-gun actions with another .blend's (W18: weapon clips are shared)."""
    names = [n for n in opt(a, "--actions", ",".join(h[k] for h in HOLDS.values() for k in ("aim_clip", "hold_clip"))).split(",")]
    with bpy.data.libraries.load(os.path.join(ROOT, src_blend) if not os.path.isabs(src_blend) else src_blend,
                                 link=False) as (src, dst):
        dst.actions = names
    for new in dst.actions:
        target = new.name.rsplit(".", 1)[0]
        old = bpy.data.actions.get(target)
        if old is None or old == new:
            continue
        old.user_remap(new)
        bpy.data.actions.remove(old)
        new.name = target
        print("  replaced %s from %s" % (target, src_blend))
    if "--save" in a:
        bpy.ops.wm.save_mainfile()
        print("  saved %s" % bpy.data.filepath)


main()
