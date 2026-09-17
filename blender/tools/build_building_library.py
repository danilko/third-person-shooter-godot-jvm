"""The building library ("zoo"): every building type assembled from LINKED kit pieces, in one view file.

    blender -b --python blender/tools/build_building_library.py [-- --render out.png]

Writes `assets/world_source/buildings/BuildingLibrary.blend`. It is a VIEW, like assets/weapons/WeaponLibrary.blend:
nothing in the game reads it and nothing exports it. Re-run it after changing building_types.json or a kit's rows.

* Each building is placed from the SAME layout the game's scenes are built from
  (tools/building_kit/layout_buildings.py), so a wrong piece here is a wrong piece in the game.
* Every piece is a collection instance LINKED from its kit's `<kit_id>.blend` (build_building_kit_blend.py). Edit
  a piece there, then File > External Data > Reload here, and every building using it updates.
* Per building: a root Empty `<Id>` (move it and the whole building follows), its pieces, the layout's
  collision boxes as wireframes (`<Id>_collision`, hidden in renders), one arrow Empty per door (points OUT),
  a red 1.49 m stick by the first door (the character's height), and a label with the Japanese name and size.
* Buildings stand in a row along +X in the order of building_types.json, fronts facing -Y (Godot +Z).
"""
import bpy
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "building_kit"))
import layout_buildings as LB  # noqa: E402

KITS = os.path.join(ROOT, "assets", "world_source", "kits")
BUILDINGS = os.path.join(ROOT, "assets", "world_source", "buildings")
OUT = os.path.join(BUILDINGS, "BuildingLibrary.blend")
TYPES = os.path.join(BUILDINGS, "building_types.json")
GAP = 12.0
CHARACTER_HEIGHT = 1.49

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = argv[argv.index("--render") + 1] if "--render" in argv else None


def godot_to_blender(v):
    x, y, z = v
    return (x, -z, y)


def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def box(name, collection, center, size, mat, parent=None, wire=False):
    me = bpy.data.meshes.new(name)
    hx, hy, hz = (s / 2 for s in size)
    v = [(x, y, z) for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    o.location = center
    o.parent = parent
    if wire:
        o.display_type = 'WIRE'
        o.hide_render = True
    collection.objects.link(o)
    return o


doc = LB.layout_all(TYPES)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.ops.wm.save_as_mainfile(filepath=OUT)             # first, so linked library paths are made relative
scene = bpy.context.scene

# link every piece collection each kit is asked for, once
wanted = {}
for b in doc["buildings"]:
    for p in b["pieces"]:
        wanted.setdefault(b["kit"], set()).add(p["piece"])
linked = {}
for kit, names in wanted.items():
    path = os.path.join(KITS, kit, kit + ".blend")
    if not os.path.exists(path):
        raise SystemExit(f"[building_library] {path} is missing: run build_building_kit_blend.py for {kit}")
    with bpy.data.libraries.load(path, link=True, relative=True) as (src, dst):
        missing = sorted(names - set(src.collections))
        if missing:
            raise SystemExit(f"[building_library] {kit}.blend has no collection for {missing[:5]}")
        dst.collections = sorted(names)
    for c in dst.collections:
        linked[(kit, c.name)] = c

m_stick = material("M_CharacterStick", (0.9, 0.15, 0.1, 1))
m_col = material("M_Collision", (0.1, 0.8, 0.2, 1))
m_label = material("M_Label", (0.05, 0.05, 0.05, 1))
x0 = 0.0
count = 0
for b in doc["buildings"]:
    W, D = b["footprint_m"]
    cx = x0 + W / 2
    c_b = bpy.data.collections.new(b["id"])
    scene.collection.children.link(c_b)
    root = bpy.data.objects.new(b["id"], None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 2.0
    root.location = (cx, 0, 0)
    root["bk_use"] = b.get("use", "")
    c_b.objects.link(root)
    for i, p in enumerate(b["pieces"]):
        inst = bpy.data.objects.new(f"{b['id']}.{i:04d}.{p['piece']}", None)
        inst.instance_type = 'COLLECTION'
        inst.instance_collection = linked[(b["kit"], p["piece"])]
        inst.location = godot_to_blender(p["pos"])
        inst.rotation_euler = (0, 0, math.radians(p["yaw"]))     # Godot yaw about +Y == Blender yaw about +Z
        inst.parent = root
        c_b.objects.link(inst)
        count += 1
    c_c = bpy.data.collections.new(b["id"] + "_collision")
    c_b.children.link(c_c)
    for k, bx in enumerate(b["boxes"]):
        sx, sy, sz = bx["size"]
        box(f"{b['id']}_box{k}", c_c, godot_to_blender(bx["center"]), (sx, sz, sy), m_col, root, wire=True)
    for d in b["doors"]:
        e = bpy.data.objects.new(f"{b['id']}_door_{d['side']}_{d['module']}", None)
        e.empty_display_type = 'SINGLE_ARROW'
        e.empty_display_size = 1.5
        e.location = godot_to_blender([d["center"][0], 1.0, d["center"][2]])
        out = godot_to_blender(d["outward"])
        # SINGLE_ARROW draws along local +Z; turn +Z onto the outward direction (horizontal)
        e.rotation_euler = (math.radians(90), 0, math.atan2(out[1], out[0]) - math.radians(90))
        e.parent = root
        c_b.objects.link(e)
    first = b["doors"][0] if b["doors"] else {"center": [0, 0, D / 2], "outward": [0, 0, 1]}
    side = (first["outward"][2], 0, -first["outward"][0])
    stick = [first["center"][0] + first["outward"][0] * 1.2 + side[0] * 1.0, CHARACTER_HEIGHT / 2,
             first["center"][2] + first["outward"][2] * 1.2 + side[2] * 1.0]
    box(f"{b['id']}_stick", c_b, godot_to_blender(stick), (0.3, 0.3, CHARACTER_HEIGHT), m_stick, root)
    jp = b.get("jp", {}).get("name", "")
    cu = bpy.data.curves.new(b["id"] + "_label", 'FONT')
    cu.body = f"{b['id']}  {jp}\n{W:.1f} x {D:.1f} x {b['height_m']:.1f} m"
    cu.size = 1.2
    lab = bpy.data.objects.new(b["id"] + "_label", cu)
    lab.location = (-W / 2, -D / 2 - 4.0, 0.05)
    lab.parent = root
    lab.data.materials.append(m_label)
    c_b.objects.link(lab)
    x0 += W + GAP

if RENDER:
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'TEXTURE'
    sc.render.resolution_x, sc.render.resolution_y = 3200, 900
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = x0 + 10
    cam.location = (x0 / 2, -200, 25)
    cam.rotation_euler = (math.radians(85), 0, 0)
    sc.camera = cam
    sc.render.filepath = RENDER
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)

bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
if os.path.exists(OUT + "1"):
    os.remove(OUT + "1")
print(f"[building_library] {len(doc['buildings'])} buildings, {count} linked piece instances -> {OUT}")
