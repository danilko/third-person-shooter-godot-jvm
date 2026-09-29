"""ONE-SHOT (2026-09-28, owner decision): replace every library mesh whose source was REMOVED with a placeholder box.

    blender -b <file.blend> --python-exit-code 1 --python blender/tools/replace_removed_meshes.py

The pieces listed in `assets/world_source/kits/library/placeholders.json` had been cut from elbolilloduro's itch.io
packs. Their provenance could not be confirmed to the project's licence standard, so their geometry leaves the repo.
Each mesh is replaced IN PLACE (same datablock, so every object and link that uses it follows) by a box of EXACTLY
its old bounds, keeping its first material. The export's bounds contract, every layout, collider and door-clearance
rule is therefore unchanged. Run on `library.blend` (collections named after the piece) and on each
`kits/shops/Shop_*.blend` (the interior's own copies, meshes named `LIB_<piece>`); the station blends LINK
library.blend and follow it. Idempotent: a mesh that is already the placeholder box is left alone. Like
`import_melee_pack.py` this is the record of what was done, and nothing depends on it running again.
"""
import json
import os

import bmesh
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = os.path.join(ROOT, "assets", "world_source", "kits", "library", "placeholders.json")
NOTE = "REMOVED 2026-09-28: base mesh was from %s; this is a same-size PLACEHOLDER BOX, needs a modeller " \
       "(see kits/library/placeholders.json)"


def box_of(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def is_placeholder(me):
    return len(me.vertices) == 8 and len(me.polygons) == 6 and len(me.materials) <= 1


def replace(me, source):
    if is_placeholder(me):
        return False
    lo, hi = box_of(me)
    mat = me.materials[0] if len(me.materials) else None
    bm = bmesh.new()
    vs = [bm.verts.new((hi[0] if i & 1 else lo[0], hi[1] if i & 2 else lo[1], hi[2] if i & 4 else lo[2]))
          for i in range(8)]
    for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me.clear_geometry()
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    if mat is not None:
        me.materials.append(mat)
    for uv in list(me.uv_layers):
        me.uv_layers.remove(uv)
    for ca in list(me.color_attributes):
        me.color_attributes.remove(ca)
    me["placeholder_note"] = NOTE % source
    me.update()
    nlo, nhi = box_of(me)
    assert max(abs(a - b) for a, b in zip(lo + hi, nlo + nhi)) < 1e-6, me.name
    return True


def main():
    spec = json.load(open(SPEC))["pieces"]
    done = []
    for p in spec:
        name, src = p["name"], p["removed_source"]
        meshes = []
        col = bpy.data.collections.get(name)
        if col is not None and col.library is None:
            meshes += [o.data for o in col.objects if o.type == "MESH" and o.data.library is None]
            col["lib_base_mesh"] = NOTE % src
            col["lib_review"] = "placeholder: " + (p.get("brief") or "model this piece at its listed size")
            if "lib_generated" in col:
                del col["lib_generated"]
        me = bpy.data.meshes.get("LIB_" + name)
        if me is not None and me.library is None:
            meshes.append(me)
        for me in dict.fromkeys(meshes):
            if replace(me, src):
                done.append(me.name)
    for block in (bpy.data.images, bpy.data.textures):
        for d in list(block):
            if d.users == 0:
                block.remove(d)
    print("[replace_removed_meshes] %s: %d meshes replaced %s" % (os.path.basename(bpy.data.filepath), len(done), done))
    if done:
        bpy.ops.wm.save_mainfile()


main()
