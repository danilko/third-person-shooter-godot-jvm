"""A building kit's Blender file: every piece of ONE kit, laid out on a grid, in one .blend.

    blender -b --python blender/tools/build_building_kit_blend.py -- assets/world_source/kits/<kit_id>

Writes `assets/world_source/kits/<kit_id>/<kit_id>.blend` from the kit's normalised `pieces/` (module_scale
already baked in, so the file is at game size).

STATUS: PLACEHOLDER. Today `pieces/` is generated from `source/` by tools/building_kit/normalize_kit.py, so an
edit made in this .blend is NOT exported and is lost when this script runs again. PLAN.md 3.6b step 1 flips the
owner: the .blend becomes the source of the pieces and an export script writes `pieces/` from it. Until then use
it to look, measure and try edits.

WHY ONE FILE PER KIT (not one per piece, not one for every kit)
--------------------------------------------------------------
* A kit's 150 pieces share ~20 materials and one module grid, and a facade change touches several pieces at once
  (a window and its plain partner, a wall and its band). One file edits them together, with ONE copy of each
  material. A file per piece copies the materials 150 times, or needs yet another library to link them from.
* A kit is also a LICENCE and a MODULE boundary. Quaternius' CC0 pieces and our own Japanese pieces (shutters,
  balconies, signs) stay in separate kits, so neither file mixes the two and each can be credited alone.
* Cost, accepted: every save is one new LFS object (~3 MB compressed; the textures are NOT packed, they stay in textures/) and two people cannot edit
  one kit at once.
The one-shot view of every BUILDING is a different file: BuildingLibrary.blend (build_building_library.py), which
LINKS these pieces, so an edit here shows there on File > External Data > Reload.

HOW IT IS LAID OUT
------------------
* One collection per category (walls, columns, ...), in kit.json's order; inside it one collection per piece,
  named exactly as the piece (`Brick_Plain_3`), holding that piece's object(s).
* Categories are rows along -Y, pieces run along +X, each at its own grid spot. The piece collection's
  `instance_offset` IS that spot, so instancing the collection puts the piece's origin at the instance: the
  object stays where you can see it and the instance still lands on the module.
* Blender axes: the glTF importer turns Godot's +Z (a wall's exterior) into Blender -Y. A wall's exterior faces -Y.
* Each piece collection carries `bk_category` and `bk_piece_path`; the scene carries `bk_kit`, `bk_module_scale`,
  `bk_status`. A text block `README_building_kit` repeats this status inside the file.
"""
import bpy
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit("usage: blender -b --python build_building_kit_blend.py -- assets/world_source/kits/<kit_id>")
KIT_DIR = os.path.abspath(os.path.join(ROOT, argv[0]))
KIT = json.load(open(os.path.join(KIT_DIR, "kit.json")))
PIECES = json.load(open(os.path.join(KIT_DIR, "pieces.json")))
OUT = os.path.join(KIT_DIR, KIT["id"] + ".blend")
GAP = 1.0
STATUS = ("PLACEHOLDER: pieces/ is still generated from source/ by normalize_kit.py, so edits here are not "
          "exported and are overwritten by build_building_kit_blend.py. PLAN.md 3.6b step 1 makes this file the owner.")


def godot_to_blender(v):
    x, y, z = v
    return (x, -z, y)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene["bk_kit"] = KIT["id"]
scene["bk_module_scale"] = KIT["module_scale"]
scene["bk_status"] = STATUS
bpy.ops.wm.save_as_mainfile(filepath=OUT)

order = [c for c, _ in KIT["categories"]]
by_cat = {}
for name, p in sorted(PIECES["pieces"].items()):
    by_cat.setdefault(p["category"], []).append((name, p))

row_y = 0.0
count = 0
for cat in order:
    items = by_cat.get(cat, [])
    if not items:
        continue
    c_cat = bpy.data.collections.new(cat)
    scene.collection.children.link(c_cat)
    depth = max(p["size"][2] for _, p in items)
    x = 0.0
    for name, p in items:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(KIT_DIR, p["path"]), import_pack_images=False)
        new = [o for o in bpy.data.objects if o not in before]
        col = bpy.data.collections.new(name)
        c_cat.children.link(col)
        col["bk_category"] = cat
        col["bk_piece_path"] = p["path"]
        # the piece's Godot-frame box -> Blender: x stays, godot z -> blender -y
        lo, hi = p["min"], p["max"]
        spot = (x - lo[0], row_y + lo[2], 0.0)       # blender y spans [row_y - depth, row_y]: rows never overlap
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
            if o.parent is None:
                o.location = (o.location[0] + spot[0], o.location[1] + spot[1], o.location[2] + spot[2])
        col.instance_offset = spot
        x += p["size"][0] + GAP
        count += 1
    row_y -= depth + 3.0

# one copy of each material and image: the importer makes MI_Trim.001, .002 ... per file
for datablocks in (bpy.data.materials, bpy.data.images):
    base = {}
    for d in list(datablocks):
        stem = re.sub(r"\.\d{3}$", "", d.name)
        if stem == d.name:
            base.setdefault(stem, d)
    for d in list(datablocks):
        stem = re.sub(r"\.\d{3}$", "", d.name)
        if stem != d.name and stem in base:
            d.user_remap(base[stem])
            datablocks.remove(d)

txt = bpy.data.texts.new("README_building_kit")
txt.write(__doc__.split("HOW IT IS LAID OUT")[0] + "\n" + STATUS + "\n")
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
if os.path.exists(OUT + "1"):
    os.remove(OUT + "1")
packed = [i.name for i in bpy.data.images if i.packed_file]
print(f"[building_kit_blend] {count} pieces, {len(bpy.data.materials)} materials, {len(bpy.data.images)} images "
      f"(packed: {len(packed)}) -> {OUT}")
