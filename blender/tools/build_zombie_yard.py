"""Build the YARD pieces (containers, pallets, barrels, cones, barriers, a tyre stack, the expressway's median panel)
from the Zombie Apocalypse kit.

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/build_zombie_yard.py

Writes `assets/world_source/kits/quaternius_zombie_apocalypse/pieces/yard/<Piece>.gltf + .bin` and the kit's
`pieces.json` (the building layout's manifest: `layout_buildings.lib_piece` resolves `quaternius_zombie_apocalypse:
<Piece>` through it), for the container terminal (`tools/building_kit/site_container_terminal.py`, PLAN.md 3.8 step 5)
and any other composite site. The sources are CC0 (Quaternius, "Zombie Apocalypse Kit", the kit's License.txt): the
download's own .blend files, untouched, copied into the kit's `blends/` so the download (`source/`) can be deleted.

The model is the size (W19): each piece is exported with its transforms applied, nothing scaled at placement.
  * CONTAINERS are fitted to ISO 668: the download's is a 20 ft box, 5.71 x 2.56 x 2.60 m; `Container_20_*` is
    that fitted to 6.058 x 2.438 x 2.591 m, `Container_40_*` the same model stretched along its length to 12.192 m
    (the ribs stretch with it: a stand-in until a 40 ft box is modelled).
  * everything else keeps the download's size (a pallet 1.22 x 0.89 m, a 0.70 m drum, a 0.67 m cone).
Piece frame is the building kits' (`BLENDER_CONVENTIONS.md` "Asset"): Blender Z up, origin at the footprint centre
on the ground, exported +Y up. The material is renamed `MI_ZombieAtlas`, the kit's own `materials/` .tres
(`build_building_scenes.gd` resolves a piece's materials by name in its kit); the atlas is referenced in
`../../textures/`, never copied.
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
KIT = os.path.join(ROOT, "assets", "world_source", "kits", "quaternius_zombie_apocalypse")
SRC = os.path.join(KIT, "blends")
OUT = os.path.join(KIT, "pieces", "yard")
sys.path.insert(0, os.path.join(ROOT, "tools", "building_kit"))
import normalize_kit as nk   # noqa: E402  (measure / manifest_entry: the one measure of a piece)

ISO_20 = (6.058, 2.438, 2.591)
ISO_40 = (12.192, 2.438, 2.591)
#: A container's faces kept (Decimate, collapse). The download's is 664 faces of ribbing; a terminal stands ~800 boxes
#: (1.3 M vertices merged), so a yard box keeps its outline, doors and corner castings and loses most ribs.
CONTAINER_KEEP = 0.25
PIECES = (
    # name, source blend, fit size (x, y, z) or None
    ("Container_20_Red", "Container_Red", ISO_20),
    ("Container_20_Green", "Container_Green", ISO_20),
    ("Container_40_Red", "Container_Red", ISO_40),
    ("Container_40_Green", "Container_Green", ISO_40),
    # (the containers are decimated to CONTAINER_KEEP of their faces: ~800 of them stand in one terminal)
    ("Pallet", "Pallet", None),
    ("Barrel", "Barrel", None),
    ("TrafficCone", "TrafficCone_1", None),
    ("PlasticBarrier", "PlasticBarrier", None),
    ("TyreStack", "Wheels_Stack", None),
    # the expressway's median panel: turned to run ALONG the road (Blender +Y, the furniture's forward) and fitted to
    # point_solve.MEDIAN_WALL_HEIGHT (1.1 m; the download's is 0.975), its own length and thickness kept
    ("HighwayMidWall", "TrafficHighwayMidWall", ("turn", 0.149, 1.555, 1.1)),
)


def build(name, src, fit):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(os.path.join(SRC, src + ".blend")) as (data_from, data_to):
        data_to.objects = [n for n in data_from.objects]
    obj = next(o for o in data_to.objects if o is not None and o.type == "MESH")
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    obj.data = obj.data.copy()
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if name.startswith("Container_"):
        mod = obj.modifiers.new("decimate", "DECIMATE")
        mod.ratio = CONTAINER_KEEP
        bpy.ops.object.modifier_apply(modifier=mod.name)
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    if fit and fit[0] == "turn":                  # a quarter turn: its length from X onto Y
        for v in me.vertices:
            v.co.x, v.co.y = -v.co.y, v.co.x
        fit = fit[1:]
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
    lo, hi = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    size = [hi[i] - lo[i] for i in range(3)]
    s = [fit[i] / size[i] for i in range(3)] if fit else [1.0, 1.0, 1.0]
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for v in me.vertices:                       # centred on the footprint, standing on the ground, fitted
        v.co.x = (v.co.x - cx) * s[0]
        v.co.y = (v.co.y - cy) * s[1]
        v.co.z = (v.co.z - lo[2]) * s[2]
    obj.location = (0.0, 0.0, 0.0)
    me.update()
    for i, m in enumerate(me.materials):
        mat = m.copy()
        mat.name = "MI_ZombieAtlas"
        me.materials[i] = mat
    img = bpy.data.images.load(os.path.join(KIT, "textures", "Zombie_Atlas.png"), check_existing=True)
    for mat in me.materials:
        for n in mat.node_tree.nodes:
            if n.type == "TEX_IMAGE":
                n.image = img
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".gltf")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLTF_SEPARATE", use_selection=True, export_yup=True,
                              export_apply=True, export_keep_originals=True, export_extras=False,
                              export_cameras=False, export_lights=False, export_animations=False)
    g = json.load(open(path))
    for im in g.get("images", []):
        im["uri"] = "../../textures/" + os.path.basename(im["uri"])
    json.dump(g, open(path, "w"), indent=1)
    return path


def main():
    manifest = {"kit": "quaternius_zombie_apocalypse", "module_scale": 1.0,
                "generated_by": "blender/tools/build_zombie_yard.py", "pieces": {}}
    for name, src, fit in PIECES:
        path = build(name, src, fit)
        g = json.load(open(path))
        lo, hi = nk.measure(g)
        manifest["pieces"][name] = nk.manifest_entry(name, "yard", g, lo, hi)
        print("[build_zombie_yard] %-20s %6.3f x %6.3f x %6.3f m  %s" % ((name,) + tuple(manifest["pieces"][name]["size"])
              + (manifest["pieces"][name]["materials"],)))
    json.dump(manifest, open(os.path.join(KIT, "pieces.json"), "w"), indent=1)
    open(os.path.join(KIT, "pieces.json"), "a").write("\n")


main()
