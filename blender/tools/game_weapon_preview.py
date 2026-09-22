"""Show the GAME's weapon placement inside a character .blend: one empty per hand socket, parented to the
hand bone exactly where the game puts it, with the real weapon model hanging from it and the weapon's
own markers (SupportPoint, StockPoint, Muzzle) as small empties.

    blender -b assets/characters/shino/shino.blend --python blender/tools/game_weapon_preview.py -- --save

WHY. An aim pose is authored against a gun, and in game the gun hangs from `hand_r` at the body's socket
for its grip archetype (SocketRifle, SocketPistol, ...). A reference gun placed by hand in the .blend is
somewhere else -- measured (2026-09-21): the rifle and shotgun aim poses were posed against placed
ASR1/SHG1 meshes, and in game the support hand came out flat under the handguard and turned fingers-up
behind the pump. Posing against THIS preview is posing against what the game does (before the in-game
stock mount and support-hand IK, which then only have to close the last few millimetres).

THE SOCKET EMPTY IS ALSO THE EDIT. Move or turn `SOCKET_Pistol` (etc.) and the export writes it into
`<body>.sockets.json`; build_character_visuals.gd applies that on top of the body's measured sockets.
So "hold the pistol a little lower in the hand" is: move the empty, Export to Game.

Idempotent: re-running rebuilds the preview from the body's current sockets (the generated
CharacterVisuals scene, which already includes any override). Nothing here is exported:
export_character.py leaves out every empty and every mesh the body's armature does not deform.
"""
import os
import re
import sys

import bpy
from mathutils import Matrix

COLL = "GAME_WEAPON_PREVIEW"
HAND = "hand_r"
# socket -> weapons shown on it (the first visible, the rest hidden until wanted)
SHOW = {
    "SocketPistol": ["PIS1", "PIS2", "REV1"],
    "SocketRifle": ["ASR1", "SMG1", "SNR1", "ASR2"],
    "SocketShotgun": ["SHG1"],
    "SocketMelee": ["MEW1", "MEW2"],
    "SocketThrowable": ["FRG1"],
}
MARKERS = ("SupportPoint", "StockPoint", "Muzzle")
# a weapon model is modelled Blender-native (+Y muzzle, +Z up) and imported into Godot's frame by the
# glTF convention (x, y, z) -> (x, z, -y): i.e. inside a Godot-frame socket it sits rotated -90 deg on X
MODEL_IN_GODOT = Matrix.Rotation(-1.5707963267948966, 4, 'X')


def repo_root():
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(d))


def godot_xform(text):
    v = [float(x) for x in re.search(r"Transform3D\(([^)]*)\)", text).group(1).split(",")]
    return Matrix(((v[0], v[1], v[2], v[9]), (v[3], v[4], v[5], v[10]), (v[6], v[7], v[8], v[11]),
                   (0.0, 0.0, 0.0, 1.0)))


def body_sockets(root, stem):
    """{socket: 4x4 in hand_r's frame} from the body's GENERATED scene (measured + overrides)."""
    scene = os.path.join(root, "src/main/resources/com/openworld/character",
                         "CharacterVisuals_%s.tscn" % stem.capitalize())
    txt = open(scene).read()
    out = {}
    for name in SHOW:
        m = re.search(r'\[node name="%s" type="Marker3D"[^\]]*WeaponAttachment"[^\]]*\]\n(transform = [^\n]+)'
                      % name, txt)
        out[name] = godot_xform(m.group(1)) if m else Matrix.Identity(4)
    return out


def mount_anchors(root, stem):
    """{marker: Vector} -- StockMountIKModifier's anchors (the shoulder pocket a StockPoint is pulled onto),
    each an offset from `upperarm_r` in `clavicle_r`'s orthonormalised frame, read from the body's scene."""
    from mathutils import Vector
    txt = open(os.path.join(root, "src/main/resources/com/openworld/character",
                            "CharacterVisuals_%s.tscn" % stem.capitalize())).read()
    names = re.search(r'mount_markers = Array\[String\]\(\[([^\]]*)\]', txt)
    offs = re.search(r'mount_offsets = Array\[Vector3\]\(\[(.*?)\]\)', txt)
    if not names or not offs:
        return {}
    ns = re.findall(r'"([^"]+)"', names.group(1))
    vs = [Vector(tuple(float(x) for x in v.split(","))) for v in re.findall(r'Vector3\(([^)]*)\)', offs.group(1))]
    return dict(zip(ns, vs))


def weapon_markers(root, wid):
    p = os.path.join(root, "src/main/resources/com/openworld/weapon", "%s.tscn" % wid)
    if not os.path.exists(p):
        return {}
    txt = open(p).read()
    out = {}
    for name in MARKERS:
        m = re.search(r'\[node name="%s" type="Marker3D" parent="\."[^\]]*\]\n(transform = [^\n]+)' % name, txt)
        if m:
            out[name] = godot_xform(m.group(1))
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    root = repo_root()
    stem = next((a.split("=", 1)[1] for a in argv if a.startswith("--body=")),
                os.path.splitext(os.path.basename(bpy.data.filepath))[0])
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and "arp_rig_type" not in o.keys()
               and any(m.type == 'ARMATURE' and m.object is o for ob in bpy.data.objects for m in ob.modifiers))
    coll = bpy.data.collections.get(COLL)
    if coll is None:
        coll = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(coll)
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    bone_len = arm.data.bones[HAND].length
    to_head = Matrix.Translation((0.0, -bone_len, 0.0))   # a bone-parented child's frame is the bone TAIL
    sockets = body_sockets(root, stem)
    for sname, weapons in SHOW.items():
        e = bpy.data.objects.new("SOCKET_" + sname[len("Socket"):], None)
        e.empty_display_type = 'ARROWS'
        e.empty_display_size = 0.06
        coll.objects.link(e)
        e.parent, e.parent_type, e.parent_bone = arm, 'BONE', HAND
        e.matrix_parent_inverse = Matrix.Identity(4)
        e.matrix_basis = to_head @ sockets[sname]
        e["game_socket"] = sname
        for i, wid in enumerate(weapons):
            path = os.path.join(root, "assets/weapons/%s.blend" % wid)
            if not os.path.exists(path):
                continue
            rel = bpy.path.relpath(path)
            with bpy.data.libraries.load(path, link=True, relative=True) as (src, dst):
                dst.collections = [c for c in src.collections if c == wid]
            wc = bpy.data.collections.get((wid, rel)) or next(
                (c for c in bpy.data.collections if c.name == wid and c.library is not None), None)
            if wc is None:
                continue
            inst = bpy.data.objects.new("PREVIEW_%s" % wid, None)
            inst.instance_type = 'COLLECTION'
            inst.instance_collection = wc
            coll.objects.link(inst)
            inst.parent = e
            inst.matrix_parent_inverse = Matrix.Identity(4)
            inst.matrix_basis = MODEL_IN_GODOT
            inst.hide_set(i > 0)
            inst.hide_viewport = False
            for mname, mm in weapon_markers(root, wid).items():
                me = bpy.data.objects.new("%s_%s" % (wid, mname), None)
                me.empty_display_type = 'SPHERE' if mname == "SupportPoint" else 'PLAIN_AXES'
                me.empty_display_size = 0.015 if mname == "SupportPoint" else 0.02
                coll.objects.link(me)
                me.parent = e
                me.matrix_parent_inverse = Matrix.Identity(4)
                me.matrix_basis = mm
                me.hide_set(i > 0)
        print("[weapon-preview] %s on %s: %s" % (e.name, HAND, ", ".join(weapons)))
    # The game pulls each stocked weapon's StockPoint onto this anchor (StockMountIKModifier), moving the
    # firing hand AND the gun. A pose whose butt is not on it is dragged there in game -- this shows where.
    arm.data.pose_position = 'POSE'
    cl, ua = arm.pose.bones["clavicle_r"], arm.pose.bones["upperarm_r"]
    for marker, off in mount_anchors(root, stem).items():
        local = cl.matrix.inverted() @ (ua.matrix.translation + cl.matrix.to_3x3().normalized() @ off)
        a = bpy.data.objects.new("ANCHOR_" + marker, None)
        a.empty_display_type = 'SPHERE'
        a.empty_display_size = 0.03
        coll.objects.link(a)
        a.parent, a.parent_type, a.parent_bone = arm, 'BONE', "clavicle_r"
        a.matrix_parent_inverse = Matrix.Identity(4)
        a.matrix_basis = Matrix.Translation((0.0, -cl.length, 0.0)) @ Matrix.Translation(local)
        a.show_in_front = True
        print("[weapon-preview] %s on clavicle_r (the game seats a weapon's %s here)" % (a.name, marker))
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
        print("[weapon-preview] saved")


main()
