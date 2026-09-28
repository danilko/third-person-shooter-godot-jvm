"""Build the shop interior .blend files (user, 2026-09-27: "the similar blender -> godot way like the station did, so
an artist can adjust in Blender and export"): one file per store TYPE in assets/world_source/kits/shops/.

    blender -b --python-exit-code 1 --python blender/tools/build_shop_blends.py -- [--only=KonbiniS] [--force=Name]

Each `Shop_<Id>.blend` holds ONE piece, the collection `<Id>_Interior` (category = the type, `bk_piece_path`), laid
out from the seed plan in tools/building_kit/shop_interiors.py:

* every fitting and interior wall is its own object, a copy of the library piece's mesh (shared per piece, so an edit
  to one bin's mesh edits every bin in THIS store; `Make Single User` to change one);
* `COL_<n>` Empties (cubes; location = box centre, scale = half size) are the colliders -- what the layout used to
  derive from each prop's bounds. Move or scale them with a wall; add one for a new solid part;
* `DOOR_<n>` Empties (single arrows on the floor at a doorway's centre, pointing OUT of the room) are the interior
  doors, built at runtime (`world.Door`): props `w`, `h`, `style` ("swing" hinged | "slide" a solid sliding leaf) and
  `slide_dir` (+1 / -1: the leaf runs to the right / left seen from where the arrow points; the wall must continue
  there for a leaf's width).

A `Reference (not exported)` collection draws the building's shell (its outer walls, split at the street and back
doors) as wire boxes, so the interior is edited against the real walls. It is never exported.

The file is then the ARTIST'S: a regenerate keeps a piece whose fingerprint (`sh_generated`) no longer matches and
says so; `--force=<Id>_Interior` overwrites it. After an edit: tools/building_kit/build_buildings.sh (it exports the
shop kit's .blend files like any kit's).
"""
import json
import math
import os
import sys

import bpy
import mathutils

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KITS = os.path.join(ROOT, "assets", "world_source", "kits")
KIT = os.path.join(KITS, "shops")
LIB = os.path.join(KITS, "library", "library.blend")
sys.path.insert(0, os.path.join(ROOT, "tools", "building_kit"))
import layout_buildings as LB  # noqa: E402
import shop_interiors as SI  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ONLY = {n for a in argv if a.startswith("--only=") for n in a[len("--only="):].split(",") if n}
FORCE = {n for a in argv if a.startswith("--force=") for n in a[len("--force="):].split(",") if n}
TYPES = json.load(open(os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")))["types"]
NOTE = ("A store's interior (build_shop_blends.py). Keep the frame: the footprint centre on the floor at the origin, the "
        "street (front) toward -Y. Every solid part needs a COL_ box; every doorway a DOOR_ arrow pointing out of the "
        "room (style swing|slide, slide_dir +1/-1 = right/left seen from the arrow's side). Keep 1.2 m clear inside "
        "each outer door and both sides of every DOOR_. After editing: tools/building_kit/build_buildings.sh.")


def blender(p):
    """Godot (x, y, z) -> Blender (x, -z, y)."""
    return mathutils.Vector((p[0], -p[2], p[1]))


def plan(tid):
    t = next(t for t in TYPES if t["id"] == tid)
    out = {"id": tid, "pieces": [], "boxes": []}
    W = t["modules"][0] * 1.82
    D = t["modules"][1] * 1.82
    LB.place_props(SI.PLANS[tid](), out, KITS, (W, D))
    LB.check_inner_doors_clear(out)
    shell = dict(t, props=[], doors=SI.DOORS[tid])
    return out, LB.layout_type(shell, KITS)


def library_meshes(names):
    """{piece: mesh} copied from library.blend (each piece is a collection holding one object)."""
    have = {n: bpy.data.meshes.get("LIB_" + n) for n in names}
    want = [n for n, m in have.items() if m is None]
    if want:
        with bpy.data.libraries.load(LIB, link=False) as (src, dst):
            dst.collections = [n for n in want if n in src.collections]
        for col in dst.collections:
            obj = col.objects[0]
            me = obj.data
            me.name = "LIB_" + col.name
            have[col.name] = me
            for o in list(col.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(col)
    # appending brings each library material again as MI_x.001, .002 ...: fold every copy back onto the one name the
    # game resolves (kits/library/materials/<name>.tres)
    import re
    for m in list(bpy.data.materials):
        base = re.sub(r"\.\d{3}$", "", m.name)
        if base != m.name:
            keep = bpy.data.materials.get(base)
            if keep is None:
                m.name = base
            else:
                m.user_remap(keep)
                bpy.data.materials.remove(m)
    missing = [n for n, m in have.items() if m is None]
    if missing:
        raise SystemExit("build_shop_blends: not in library.blend: %s" % missing)
    return have


def fingerprint(col):
    import hashlib
    h = hashlib.sha1()
    for o in sorted(col.objects, key=lambda o: o.name):
        m = o.matrix_world
        h.update(("%s|%s;" % (o.name.split(".")[0], ",".join("%.4f" % v for row in m for v in row))).encode())
        for k in ("w", "h", "style", "slide_dir"):
            if k in o:
                h.update(("%s=%s;" % (k, o[k])).encode())
        if o.type == "MESH":
            h.update(("%s|%d|%s" % (o.data.name, len(o.data.vertices),
                                    ",".join(m.name if m else "" for m in o.data.materials))).encode())
    return h.hexdigest()


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        return
    for o in list(col.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(col)


def install(tid, out, name):
    remove_collection(name)
    # a regenerate takes the library's CURRENT meshes: drop every library copy nothing uses any more (an artist's
    # single-user edit of one went with the piece it belonged to)
    for me in list(bpy.data.meshes):
        if me.users == 0 or (me.name.startswith("LIB_") and me.users == int(me.use_fake_user)):
            bpy.data.meshes.remove(me)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    meshes = library_meshes(sorted({p["piece"] for p in out["pieces"]}))
    for p in out["pieces"]:
        o = bpy.data.objects.new(p["piece"], meshes[p["piece"]])
        o.location = blender(p["pos"])
        o.rotation_euler = (0.0, 0.0, math.radians(p["yaw"]))
        col.objects.link(o)
    for i, b in enumerate(out["boxes"]):
        e = bpy.data.objects.new("COL_%02d" % i, None)
        e.empty_display_type = "CUBE"
        e.empty_display_size = 1.0
        e.location = blender(b["center"])
        e.scale = (b["size"][0] / 2, b["size"][2] / 2, b["size"][1] / 2)
        e.hide_render = True
        col.objects.link(e)
    for i, d in enumerate(out.get("inner_doors", [])):
        e = bpy.data.objects.new("DOOR_%d" % i, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.8
        e.location = blender(d["center"])
        o = d["outward"]
        # the arrow (local +Z) laid along +X, then turned about Z onto the outward direction (Blender axes)
        e.rotation_euler = (0.0, math.radians(90.0), math.atan2(-o[2], o[0]))
        e["w"], e["h"] = float(d["width"]), float(d["height"])
        e["style"] = str(d.get("style", "swing"))
        e["slide_dir"] = float(d.get("slide_dir", 1.0))
        col.objects.link(e)
    col["bk_piece_path"] = "pieces/%s/%s.gltf" % (tid.lower(), name)
    col["bk_category"] = tid.lower()
    col["edit_note"] = NOTE
    for o in col.objects:
        o["edit_note"] = NOTE
    col.instance_offset = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    col["sh_generated"] = fingerprint(col)
    return col


def reference(shell):
    """The building's outer walls as wire boxes (never exported: no bk_piece_path)."""
    name = "Reference (not exported)"
    remove_collection(name)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    for i, b in enumerate(shell["boxes"]):
        e = bpy.data.objects.new("REF_%02d" % i, None)
        e.empty_display_type = "CUBE"
        e.empty_display_size = 1.0
        e.location = blender(b["center"])
        e.scale = (b["size"][0] / 2, b["size"][2] / 2, b["size"][1] / 2)
        col.objects.link(e)
    for i, d in enumerate(shell["doors"]):
        e = bpy.data.objects.new("REF_door_%s_%d" % (d["side"], d["module"]), None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 1.2
        e.location = blender(d["center"])
        o = d["outward"]
        e.rotation_euler = (0.0, math.radians(90.0), math.atan2(-o[2], o[0]))
        col.objects.link(e)
    col.hide_render = True


def build(tid):
    path = os.path.join(KIT, "Shop_%s.blend" % tid)
    if os.path.exists(path):
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.name = "Shop_" + tid
    out, shell = plan(tid)
    name = tid + "_Interior"
    col = bpy.data.collections.get(name)
    kept = False
    if col is not None and col.get("sh_generated") and col["sh_generated"] != fingerprint(col) and name not in FORCE:
        kept = True
        print("[build_shop_blends] KEPT %s: edited by hand (--force=%s overwrites the artist's edit; ask first)"
              % (name, name))
    else:
        before = col.get("sh_generated") if col is not None else None
        install(tid, out, name)
        print("[build_shop_blends] %-26s %s: %d objects, %d colliders, %d doors" % (
            name, "regenerated" if before else "new", len(out["pieces"]), len(out["boxes"]),
            len(out.get("inner_doors", []))))
    reference(shell)
    readme = bpy.data.texts.get("README_artist") or bpy.data.texts.new("README_artist")
    readme.from_string(open(os.path.join(KIT, "ARTIST_NOTES.md")).read())
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("[build_shop_blends] %s -> %s" % (tid, os.path.relpath(path, ROOT)))
    return kept


def main():
    kept = [tid for tid in SI.PLANS if (not ONLY or tid in ONLY) and build(tid)]
    if kept:
        sys.exit(3)


main()
