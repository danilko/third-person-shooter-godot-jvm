"""Conform models from the CC0 "Free CC0 Guns & Explosives Pack" (3DModelsCC0,
https://3dmodelscc0.itch.io/free-cc0-guns-explosives-pack) to the weapon standard, as assets/weapons/<id>.blend
+ textures/. To re-run, download the pack again into assets/weapons/free-cc0-melee-weapons-pack/ (the folder name is the
download's); it was removed from the repo after import (2026-09-19) and is in git history before that. This file is the record of what was done to each model, like
import_melee_pack.py.

    blender --background --factory-startup --python blender/tools/import_guns_pack.py -- [id ...]

THE TEXTURE DIET (Steam Deck). The pack ships five 2048 px maps per model (~17 MB of VRAM each once compressed),
and measured, they carry almost nothing the game can show:
  * normal maps: mean tilt 0.0-1.8 deg from flat, ~95% of texels under 10 deg (M4A1's is exactly flat) -> DROPPED;
  * height maps: glTF has no height channel -> DROPPED;
  * metallic / roughness: dropped for per-material constants, the values every other gun ships (metallic 0,
    roughness 0.5); a metallic surface with no reflection probe renders near-black anyway;
  * base colour: a palette image (50-256 colours of painted regions) -> kept, resized to TEX_PX (1024: the
    first-person view needs it, see TEX_PX).
So one gun costs one 1024 px colour map (~1.4 MB) instead of five 2048 px maps. Geometry is NOT reduced: the
held gun is seen up close in first person, and Godot's generated LODs cover distance.

For each model: the mesh parts are joined into one object named <id> (world transforms applied), turned so the
muzzle points down Blender +Y with the top up (and levelled, for a model authored tilted), moved so the origin is
the centre of the firing hand's fist on the grip, and scaled to the table's `length_m`. A MOVING PART (the
sniper's bolt) stays its own object with its origin on its pivot and its motion as an NLA clip (WEAPON_AUTHORING.md
"Moving parts"). `build_weapon.py` then verifies and exports the .glb.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = os.path.join(ROOT, "assets", "weapons", "free-cc0-melee-weapons-pack")
OUT = os.path.join(ROOT, "assets", "weapons")
TEX = os.path.join(OUT, "textures")
TEX_PX = 1024          # measured: the AK's UVs give 1324 texels/m at 1024, ~1:1 with a first-person view on a
                       # Steam Deck (~1300 px/m at 0.4 m); 512 was half that, blurry up close
METALLIC, ROUGHNESS = 0.0, 0.5

# folder/fbx/png: the pack's files. tip/up: raw axis the MUZZLE points along and raw UP, as (sign, axis).
# pitch: degrees the raw bore rises toward the muzzle (levelled out). grip: the fist centre in RAW (world,
# post-FBX) coordinates, an axis None = the model's bounding-box centre on it. length: overall length (m) after
# levelling, None = keep the raw size. drop: objects deleted (a loose spare magazine).
# parts: {object name: clip} kept as MOVING PARTS. slide: {object name: metres along the bore} moved in the
# final frame before the join. Grips read off a side render on a 1 cm grid.
MODELS = {
    # AK-47: already muzzle +Y / up +Z, 0.877 m. Fist on the slanted pistol grip 4-5 cm under the receiver; its
    # height is chosen so the bore sits 8.3 cm over the origin, as the old ASR1 did (the adopted rifle pose and
    # the SocketRifle fit were built on that).
    "ASR1": dict(folder="AK-47", fbx="AK47.fbx", png="AK47_Base_Color.png", tip=(+1, 1), up=(+1, 2),
                 grip=(-0.0026, -0.296, -0.100), length=0.88),
    # M4A1 (0.859 m raw, stock extended) scaled to the M4's 0.838. Fist on the pistol grip, bore ~9 cm over it
    # like the old ASR2.
    "ASR2": dict(folder="M4A1", fbx="M4A1.fbx", png="M4A1_Base_Color.png", tip=(+1, 1), up=(+1, 2),
                 grip=(None, -0.077, -0.068), length=0.838),
    # A Remington 700 / M24-pattern scoped rifle, authored with the bore pitched 10.46 deg up (the barrel's
    # principal axis), scaled to the M24's 1.092 m. Fist on the semi-pistol grip behind the trigger.
    "SNR1": dict(folder="Sniper", fbx="Sniper.fbx", png="Sniper_Base_Color.png", tip=(+1, 1), up=(+1, 2),
                 pitch=10.46, grip=(-0.0037, -0.315, -0.110), length=1.092, parts={"Bolt": "bolt_work"}),
    # A Remington 870-pattern pump gun, 1.219 m raw, scaled to the 870's 0.98 (18.5 in barrel). Stock-wrist grip.
    # The pump sat 0.36 m ahead of the grip, past this character's 0.416 m arm (grip missed by 9 cm in
    # probe_weapon_fit); an 870's pump travels ~9 cm, so it is slid 8.5 cm back along its tube (partly racked).
    "SHG1": dict(folder="Shotgun", fbx="Shotgun.fbx", png="Shotgun_Base_Color.png", tip=(+1, 1), up=(+1, 2),
                 grip=(None, -0.48, -0.037), length=0.98, slide={"Fore_Stock": -0.085}),
    # Makarov PM, 0.168 m raw, scaled to the real PM's 0.161. Its spare magazine lies loose behind the gun in the
    # file, so it is dropped. Fist on the grip, bore 6 cm over it like the old PIS1.
    "PIS1": dict(folder="Pistol_MK", fbx="Makarov.fbx", png="Makarov_Base_Color.png", tip=(+1, 1), up=(+1, 2),
                 grip=(0.0048, -0.0057, -0.015), length=0.161, drop=("Magazine",)),
    # Throwables and the charge: real-size already, kept at their raw size (length None). A grenade's origin is its
    # BODY CENTRE with the fuze forward (the FRG1 rule); raw +Z is the fuze on every one of them.
    "FRG1": dict(folder="FragGrenade", fbx="FragGrenadeModel.fbx", png="FragGrenade_Base_Color.png",
                 tip=(+1, 2), up=(+1, 1), grip=(None, None, None), length=None),
    "PIB1": dict(folder="Pipe_Bomb", fbx="Pipe_Bomb.fbx", png="Pipe_Bomb_Base_Color.png",
                 tip=(+1, 2), up=(+1, 1), grip=(None, None, None), length=None),
    "FLA1": dict(folder="Flashbang", fbx="Flashbang.fbx", png="Flashbang_Base_Color.png",
                 tip=(+1, 2), up=(+1, 1), grip=(None, None, None), length=None),
    "SMO1": dict(folder="Smoke_Grenade", fbx="Smoke_Grenade.fbx", png="Smoke_Grenade_Base_Color.png",
                 tip=(+1, 2), up=(+1, 1), grip=(None, None, None), length=None),
    # The remote charge: a block with its detonator on top, lying flat; forward along its length.
    "REC1": dict(folder="C4", fbx="C4.fbx", png="C4_Base_Color.png",
                 tip=(+1, 1), up=(+1, 2), grip=(None, None, None), length=None),
}

# the bore's height over the grip in the FINAL frame: a moving part turns about the bore
BORE_Z = {"SNR1": 0.078}   # measured at the muzzle

# bolt_work, keyed like the old SNR1's clip (60 fps): (frame, lift deg about the bore, travel m along it)
BOLT_KEYS = [(0, 0, 0), (18, 0, 0), (25, -60, 0), (35, -60, -0.05), (43, -60, 0), (50, 0, 0), (54, 0, 0)]


def axis_vec(sign, axis):
    v = Vector((0.0, 0.0, 0.0))
    v[axis] = float(sign)
    return v


def base_colour(folder, png, wid):
    img = bpy.data.images.load(os.path.join(PACK, folder, png))
    img.scale(TEX_PX, TEX_PX)
    path = os.path.join(TEX, wid + "_base_color.png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    out = bpy.data.images.load(path)
    out.filepath = "//textures/" + wid + "_base_color.png"
    return out


def join(objs, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = ob.data.name = name
    return ob


def bolt_clip(ob, clip):
    base = ob.location.copy()
    for f, lift, travel in BOLT_KEYS:
        ob.location = base + Vector((0, travel, 0))
        ob.rotation_euler = (0, math.radians(lift), 0)
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", frame=f)
    act = ob.animation_data.action
    act.name = clip
    track = ob.animation_data.nla_tracks.new()
    track.name = clip
    strip = track.strips.new(clip, 0, act)
    strip.extrapolation = 'HOLD'
    ob.animation_data.action = None
    ob.location = base
    ob.rotation_euler = (0, 0, 0)


def conform(wid, folder, fbx, png, tip, up, grip, length, pitch=0.0, parts=None, slide=None, drop=()):
    parts = parts or {}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.ops.import_scene.fbx(filepath=os.path.join(PACK, folder, fbx))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for o in meshes:                                # world transforms into the vertices, parents cut
        o.data.transform(o.matrix_world)
    for o in meshes:
        o.parent = None
        o.matrix_world = Matrix()
    for o in list(bpy.context.scene.objects):
        if o.type != 'MESH' or o.name in drop:
            bpy.data.objects.remove(o)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']

    vs = [v.co for o in meshes for v in o.data.vertices]
    g = [grip[i] if grip[i] is not None else (min(v[i] for v in vs) + max(v[i] for v in vs)) / 2 for i in range(3)]
    t, u = axis_vec(*tip), axis_vec(*up)
    xf = (Matrix.Rotation(math.radians(-pitch), 4, 'X')                  # level the bore
          @ Matrix((t.cross(u), t, u)).to_4x4()                         # rows: new x, y, z in raw axes
          @ Matrix.Translation(-Vector(g)))        # grip onto the origin
    for o in meshes:
        o.data.transform(xf)
    vs = [v.co for o in meshes for v in o.data.vertices]
    s = Matrix.Scale(1.0 if length is None else length / (max(v.y for v in vs) - min(v.y for v in vs)), 4)
    for o in meshes:
        o.data.transform(s)
        if slide and o.name in slide:
            o.data.transform(Matrix.Translation((0, slide[o.name], 0)))

    moving = [o for o in meshes if o.name in parts]
    ob = join([o for o in meshes if o not in moving], wid)
    col = bpy.data.collections.new(wid)
    bpy.context.scene.collection.children.link(col)
    for o in [ob] + moving:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)

    m = bpy.data.materials.new("M_" + wid)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = base_colour(folder, png, wid)
    nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = METALLIC
    bsdf.inputs["Roughness"].default_value = ROUGHNESS
    for o in [ob] + moving:
        o.data.materials.clear()
        o.data.materials.append(m)
        # keep the FBX's smoothing but weight it by face area, so bevels read without a normal map
        mod = o.modifiers.new("WN", 'WEIGHTED_NORMAL')
        mod.keep_sharp = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)

    for p in moving:                                # origin on the pivot: the bore axis, at the part's middle
        pv = [v.co for v in p.data.vertices]
        pivot = Vector((0.0, (min(v.y for v in pv) + max(v.y for v in pv)) / 2, BORE_Z[wid]))
        p.data.transform(Matrix.Translation(-pivot))
        p.location = pivot
        bolt_clip(p, parts[p.name])

    for img in list(bpy.data.images):               # the FBX's own references to the 2048 px maps
        if img.users == 0:
            bpy.data.images.remove(img)
    bpy.context.scene.render.fps = 60
    bpy.context.scene.frame_set(0)
    path = os.path.join(OUT, wid + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, relative_remap=True)
    vs = [o.matrix_world @ w.co for o in [ob] + moving for w in o.data.vertices]
    tris = 0
    for o in [ob] + moving:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    print(f"[guns_pack] {wid} <- {folder}: {max(v.y for v in vs) - min(v.y for v in vs):.3f} m, "
          f"grip->rear {-min(v.y for v in vs):.3f} m, {tris} tris, parts {[p.name for p in moving]}, wrote {path}")


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
os.makedirs(TEX, exist_ok=True)
for wid, row in MODELS.items():
    if not argv or wid in argv:
        conform(wid, **row)
