"""One-shot: conform the CC0 "Free CC0 Melee Weapons Pack" (3DModelsCC0, https://3dmodelscc0.itch.io/free-cc0-melee-weapons-pack)
to the weapon standard, as assets/weapons/<id>.blend + textures/. Run once, with the pack unpacked at
assets/weapons/MeleeWeaponsPack/; the pack is then deleted (CREDITS.md names the source), so this file is the
record of exactly what was done to each model.

    blender --background --factory-startup --python blender/tools/import_melee_pack.py

For each model (all measured first, see the table below): the FBX's object transform is applied, the model is
turned so its tip/head points down Blender +Y (Godot -Z) with its edge (or hook, or blade face) DOWN, scaled to its
`length_m` in weapon_models.json, and moved so its origin is the centre of the firing hand's fist on the grip.
Textures are baked to 1024 px (2048 is far more than a hand prop shows): base colour, metallic, roughness and a
normal map, the DirectX-convention normal maps (Spade, Machete) green-flipped to glTF's OpenGL convention. The
height maps are dropped: glTF has no height channel. Then `build_weapon.py` verifies and exports the .glb.
"""
import os

import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = os.path.join(ROOT, "assets", "weapons", "MeleeWeaponsPack")
OUT = os.path.join(ROOT, "assets", "weapons")
TEX = os.path.join(OUT, "textures")
TEX_PX = 1024

# id, pack folder, raw axis the TIP points along (sign, axis), raw axis the model's UP is (sign, axis),
# grip centre in raw (post-transform) coordinates, target overall length (m).
# Measured by slicing each FBX along its length (handle = the narrow uniform run, edge = the side that tapers
# to ~0 thickness); see the commit that added this file.
MODELS = [
    ("MEW1", "Combat_Knife", (+1, 2), (+1, 0), (-0.001, 0.0, -0.075), 0.297),   # handle -0.134..-0.015; edge -X
    ("MEW2", "FireAxe",      (+1, 2), (-1, 0), ( 0.008, 0.0, -0.282), 0.81),    # head +Z, edge +X; hand 0.10 m from the butt at 0.81
    ("MEW3", "Crowbar",      (-1, 1), (+1, 2), ( 0.0, 0.210, 0.002), 0.607),    # hook -Y curls to -Z; hand 0.10 m from the straight end
    ("MEW4", "Spade",        (-1, 1), (+1, 2), ( 0.0, 0.700, -0.005), 1.181),   # blade -Y; hand on the shaft under the D-grip
    ("MEW5", "Dagger",       (+1, 2), (+1, 0), ( 0.0, 0.0, 0.005), 0.225),      # handle -0.037..+0.047; double edged
    ("MEW6", "Katana",       (+1, 2), (+1, 1), ( 0.0, -0.002, -0.335), 1.079),  # tsuba at -0.25; edge -Y (convex side)
    ("MEW7", "Machete",      (+1, 0), (+1, 2), ( 0.0, 0.0, -0.005), 0.515),     # handle -0.058..+0.06; edge -Z
]


def axis_vec(sign, axis):
    v = Vector((0.0, 0.0, 0.0))
    v[axis] = float(sign)
    return v


def texture(folder, stem, key, out_name, flip_green=False):
    """Load <stem>_<key>*.png, resize to TEX_PX, save as textures/<out_name>.png, return the saved image."""
    src = next((f for f in sorted(os.listdir(os.path.join(PACK, folder)))
                if f.startswith(stem + "_" + key) and f.endswith(".png")), None)
    if src is None:
        return None
    img = bpy.data.images.load(os.path.join(PACK, folder, src))
    img.scale(TEX_PX, TEX_PX)
    if flip_green:
        px = list(img.pixels)
        for i in range(0, len(px), 4):
            if flip_green:
                px[i + 1] = 1.0 - px[i + 1]
        img.pixels[:] = px
    path = os.path.join(TEX, out_name + ".png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    out = bpy.data.images.load(path)
    out.filepath = "//textures/" + out_name + ".png"
    if key != "Base_Color":
        out.colorspace_settings.name = "Non-Color"
    return out


def conform(wid, folder, tip, up, grip, length):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.ops.import_scene.fbx(filepath=os.path.join(PACK, folder, folder + ".fbx"))
    ob = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
    for o in list(bpy.context.scene.objects):
        if o is not ob:
            bpy.data.objects.remove(o)
    ob.data.transform(ob.matrix_world)          # apply the FBX's rotation + 0.01 scale
    ob.matrix_world = Matrix()

    # rotate raw (tip, up) onto Blender (+Y, +Z), then scale, then put the grip on the origin
    t, u = axis_vec(*tip), axis_vec(*up)
    r = t.cross(u)
    rot = Matrix((r, t, u)).to_4x4()            # rows: new x, y, z expressed in raw axes
    ob.data.transform(Matrix.Translation(-Vector(grip)))
    ob.data.transform(rot)
    vs = [v.co for v in ob.data.vertices]
    raw_len = max(v.y for v in vs) - min(v.y for v in vs)
    ob.data.transform(Matrix.Scale(length / raw_len, 4))
    ob.name = ob.data.name = wid

    col = bpy.data.collections.new(wid)
    bpy.context.scene.collection.children.link(col)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    col.objects.link(ob)

    # one clean material from the pack's maps
    ob.data.materials.clear()
    m = bpy.data.materials.new("M_" + wid)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    dx = any("DirectX" in f for f in os.listdir(os.path.join(PACK, folder)))
    maps = {
        "Base Color": texture(folder, folder, "Base_Color", wid + "_base_color"),
        "Metallic": texture(folder, folder, "Metallic", wid + "_metallic"),
        "Roughness": texture(folder, folder, "Roughness", wid + "_roughness"),
    }
    for socket, img in maps.items():
        if img:
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = img
            nt.links.new(n.outputs["Color"], bsdf.inputs[socket])
    nimg = texture(folder, folder, "Normal", wid + "_normal", flip_green=dx)
    if nimg:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = nimg
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    ob.data.materials.append(m)

    bpy.context.scene.render.fps = 60
    path = os.path.join(OUT, wid + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, relative_remap=True)
    vs = [v.co for v in ob.data.vertices]
    print(f"[melee_pack] {wid} <- {folder}: {max(v.y for v in vs) - min(v.y for v in vs):.3f} m, "
          f"grip->rear {-min(v.y for v in vs):.3f} m, dx normal {dx}, wrote {path}")


os.makedirs(TEX, exist_ok=True)
for row in MODELS:
    conform(*row)
