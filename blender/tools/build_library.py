"""Build library.blend: the project's own central library of Japanese building parts, interiors and props.

    blender -b --python-exit-code 1 --python blender/tools/build_library.py -- [--extract] [--procedural] [--force]

library.blend OWNS its pieces (the building-kit rule): after this has run, edit a piece in the .blend and run
`tools/building_kit/build_buildings.sh`, which exports them through `export_building_kit.py`.

* `--procedural` (re)builds only the pieces this script models itself (library_procedural.py, library_landmarks.py):
  the collections flagged `lib_procedural`. **A piece an artist has edited is never overwritten:** each generated
  piece stores a fingerprint of its mesh and materials (`lib_generated`); a piece whose fingerprint no longer matches
  has been hand-edited and is KEPT (and reported), becoming the artist's. `--force`, or `--only=Name,Name`, regenerates
  such a piece on purpose. Every piece carries an `edit_note` (Object/Collection properties) saying what the game
  assumes about it, and the file carries a `README_artist` text; see also `kits/library/ARTIST_NOTES.md`.
  Everything else in the file is left alone, so hand edits to extracted pieces survive.
* `--extract` cuts the pieces listed in `assets/world_source/kits/library/extract.json` out of the elbolilloduro
  downloads (CC0 models; their textures are NOT cleared and are never used), resizes and faces them, and gives
  every face a palette material. It needs the downloads, which are deleted afterwards, so it refuses to replace
  an extracted piece that already exists unless `--force`.
* no flag: both.

Every piece is a collection named after it holding one object; the collection's `instance_offset` is its grid spot
(export moves it back to the origin). Piece frame: Z up, origin at the footprint centre on the floor, the side a
person uses faces -Y (Godot +Z, the building convention). Materials are the palette's names with a flat viewport
colour; their real look is `materials/MI_*.tres` (tools/building_kit/build_library_palette.py).
"""
import json
import math
import os
import sys

import bmesh
import bpy
import mathutils

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KITS = os.path.join(ROOT, "assets", "world_source", "kits")
KIT = os.path.join(KITS, "library")
BLEND = os.path.join(KIT, "library.blend")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
_any = {"--extract", "--procedural", "--reframe"} & set(argv)
DO_EXTRACT = "--extract" in argv or not _any
DO_PROC = "--procedural" in argv or not _any
DO_REFRAME = "--reframe" in argv or not _any
FORCE = "--force" in argv
ONLY = {n for a in argv if a.startswith("--only=") for n in a[len("--only="):].split(",") if n}
GRID = 6.0          # metres between piece spots in the file
ROW = 8             # spots per row


# ── materials ────────────────────────────────────────────────────────────────────────────────────────────────

PALETTE = json.load(open(os.path.join(KIT, "palette.json")))["materials"]


def _mean_colour(entry):
    """A flat viewport colour for a palette entry: its colour, times its albedo texture's mean when it has one."""
    col = list(entry.get("color", [1, 1, 1]))[:3]
    path = None
    if "tex" in entry and entry.get("albedo_tex", True):
        for suffix in ("_Color.jpg", ".png"):
            p = os.path.join(KIT, "textures", entry["tex"] + suffix)
            if os.path.exists(p):
                path = p
    elif "tex_path" in entry:
        p = os.path.join(ROOT, entry["tex_path"].replace("res://", "") + "_BaseColor.png")
        path = p if os.path.exists(p) else None
    if path:
        img = bpy.data.images.load(path, check_existing=True)
        import numpy as np
        px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        m = px.reshape(-1, 4)[:, :3].mean(axis=0)
        col = [col[i] * float(m[i]) for i in range(3)]
        bpy.data.images.remove(img)
    return col + [entry.get("color", [1, 1, 1, 1])[3] if len(entry.get("color", [])) > 3 else 1.0]


def material(name):
    if name not in PALETTE:
        raise SystemExit("build_library: %s is not in palette.json" % name)
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_fake_user = False
        c = _mean_colour(PALETTE[name])
        m.diffuse_color = c
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = c
            bsdf.inputs["Roughness"].default_value = float(PALETTE[name].get("roughness", 0.7))
            bsdf.inputs["Metallic"].default_value = float(PALETTE[name].get("metallic", 0.0))
            if "emission" in PALETTE[name]:
                bsdf.inputs["Emission Color"].default_value = list(PALETTE[name]["emission"]) + [1.0]
                bsdf.inputs["Emission Strength"].default_value = float(PALETTE[name].get("emission_energy", 1.0))
    return m


# ── the file and its grid ────────────────────────────────────────────────────────────────────────────────────

def open_library():
    if os.path.exists(BLEND):
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.name = "library"
    return bpy.context.scene


def piece_names():
    return sorted(c.name for c in bpy.data.collections if c.get("bk_piece_path"))


def remove_piece(name):
    col = bpy.data.collections.get(name)
    if col is None:
        return
    for o in list(col.all_objects):
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(col)


def fingerprint(col):
    """A generated piece's identity: its vertices (in the piece frame: the grid offset removed), faces and material
    names. Anything an artist does to the model changes it."""
    import hashlib
    h = hashlib.sha1()
    for o in sorted(col.objects, key=lambda o: o.name):
        if o.type != "MESH":
            continue
        me = o.data
        off = o.location - col.instance_offset
        for v in me.vertices:
            h.update(("%.4f,%.4f,%.4f;" % (v.co.x + off.x, v.co.y + off.y, v.co.z + off.z)).encode())
        h.update(("%d|%s" % (len(me.polygons), ",".join(m.name if m else "" for m in me.materials))).encode())
        h.update(("|" + ",".join(str(p.material_index) for p in me.polygons)).encode())
    return h.hexdigest()


def hand_edited(name):
    col = bpy.data.collections.get(name)
    return col is not None and col.get("lib_generated") and col["lib_generated"] != fingerprint(col)


def install_piece(name, cat, mesh, origin_note, procedural):
    """Put `mesh` (already in the piece frame) into collection `name` at the next free grid spot."""
    remove_piece(name)
    scene = bpy.context.scene
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    col["bk_piece_path"] = "pieces/%s/%s.gltf" % (cat, name)
    col["bk_category"] = cat
    col["lib_procedural"] = bool(procedural)
    col["lib_base_mesh"] = origin_note
    return col


def relayout():
    """Every piece on the grid in name order; instance_offset = its spot (what the export moves back)."""
    for i, name in enumerate(piece_names()):
        col = bpy.data.collections[name]
        spot = mathutils.Vector(((i % ROW) * GRID, -(i // ROW) * GRID, 0.0))
        delta = spot - col.instance_offset
        for o in col.objects:
            if o.parent is None:
                o.location = o.location + delta
        col.instance_offset = spot


# ── extraction (one-time, from local downloads) ──────────────────────────────────────────────────────────────

def _import(path):
    before = set(bpy.data.objects)
    if path.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def _palette_for(spec, src_mat):
    low = (src_mat or "").lower()
    for key, target in (spec.get("mat") or {}).items():
        if key in low:
            return target
    for key, target in (("glass", "MI_GlassClear"), ("light", "MI_Light"), ("emissor", "MI_Light"),
                        ("mirror", "MI_Steel")):
        if key in low:
            return target
    return spec["default"]


def _joined_mesh(spec, objs):
    """One mesh from the listed source objects, world transforms applied, faces on palette materials."""
    bm = bmesh.new()
    mats = []
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        remap = []
        for slot in (o.material_slots or []):
            target = _palette_for(spec, slot.material.name if slot.material else "")
            if target not in mats:
                mats.append(target)
            remap.append(mats.index(target))
        if not remap:
            if spec["default"] not in mats:
                mats.append(spec["default"])
            remap = [mats.index(spec["default"])]
        for p in me.polygons:
            p.material_index = remap[min(p.material_index, len(remap) - 1)]
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    mesh = bpy.data.meshes.new(spec["name"])
    bm.to_mesh(mesh)
    bm.free()
    for name in mats:
        mesh.materials.append(material(name))
    for attr in list(mesh.color_attributes):
        mesh.color_attributes.remove(attr)
    return mesh


def _frame(mesh, spec):
    """Rotate about Z, fit to the Japanese size, and put the origin at the footprint centre on the floor."""
    rot = mathutils.Matrix.Rotation(math.radians(spec.get("rot_z", 0)), 4, "Z")
    mesh.transform(rot)
    lo = mathutils.Vector((min(v.co[i] for v in mesh.vertices) for i in range(3)))
    hi = mathutils.Vector((max(v.co[i] for v in mesh.vertices) for i in range(3)))
    s = 1.0
    if spec.get("fit"):
        axis, size = spec["fit"]
        k = "xyz".index(axis)
        s = size / (hi[k] - lo[k])
    base = float(spec.get("base", 0.0))
    move = mathutils.Matrix.Translation((0, 0, base)) @ mathutils.Matrix.Scale(s, 4) @ \
        mathutils.Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
    mesh.transform(move)
    mesh.update()
    return s


def extract():
    spec = json.load(open(os.path.join(KIT, "extract.json")))
    by_src = {}
    for p in spec["pieces"]:
        by_src.setdefault(p["src"], []).append(p)
    report = []
    for src, pieces in by_src.items():
        path = os.path.join(KITS, spec["sources"][src])
        todo = [p for p in pieces if FORCE or bpy.data.collections.get(p["name"]) is None]
        if not todo:
            continue
        if not os.path.exists(path):
            raise SystemExit("build_library --extract: %s is gone (the downloads are deleted after extraction);"
                             " the pieces already in library.blend are the owners" % spec["sources"][src])
        imported = _import(path)
        by_name = {o.name: o for o in imported}
        for p in todo:
            missing = [n for n in p["objects"] if n not in by_name]
            if missing:
                raise SystemExit("build_library: %s: no object(s) %s in %s" % (p["name"], missing, src))
            mesh = _joined_mesh(p, [by_name[n] for n in p["objects"]])
            s = _frame(mesh, p)
            note = "elbolilloduro %s (%s), objects %s, scaled %.3f, re-textured" % (
                src, os.path.basename(spec["sources"][src]), ", ".join(p["objects"]), s)
            install_piece(p["name"], p["cat"], mesh, note, procedural=False)
            d = mesh_dims(mesh)
            report.append("%-24s %-10s %5.2f x %5.2f x %5.2f m  %5d tris  scale %.3f" % (
                p["name"], p["cat"], d[0], d[1], d[2], sum(len(f.vertices) - 2 for f in mesh.polygons), s))
        for o in imported:
            me = o.data if o.type == "MESH" else None
            bpy.data.objects.remove(o, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
        for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.textures):
            for d in list(block):
                if d.users == 0 and not d.name.startswith("MI_"):
                    block.remove(d)
    for line in report:
        print("[build_library] extract " + line)


def reframe():
    """Apply extract.json's `fit_box` (a non-uniform resize to a real Japanese size) and its `jp` review to the
    extracted pieces ALREADY in the file. Idempotent: a piece at its size is left alone."""
    spec = json.load(open(os.path.join(KIT, "extract.json")))
    for p in spec["pieces"]:
        col = bpy.data.collections.get(p["name"])
        if col is None:
            continue
        review = p.get("jp", {})
        col["lib_review"] = "%s: %s" % (review.get("status", "?"), review.get("note", ""))
        if not p.get("fit_box"):
            continue
        obj = col.objects[0]
        me = obj.data
        dims = mesh_dims(me)
        k = [p["fit_box"][i] / dims[i] for i in range(3)]
        if all(abs(v - 1.0) < 1e-4 for v in k):
            continue
        me.transform(mathutils.Matrix.Diagonal((k[0], k[1], k[2], 1.0)))
        me.update()
        print("[build_library] reframe %-24s %.2f x %.2f x %.2f -> %s m" % (p["name"], dims[0], dims[1], dims[2],
                                                                           p["fit_box"]))


def mesh_dims(mesh):
    return [max(v.co[i] for v in mesh.vertices) - min(v.co[i] for v in mesh.vertices) for i in range(3)]


def main():
    open_library()
    if DO_EXTRACT:
        extract()
    if DO_REFRAME:
        reframe()
    if DO_PROC:
        import library_procedural as proc
        built = proc.build_all(material)
        names = {n for n, _c, _m in built}
        kept = set()
        for name in [n for n in piece_names() if bpy.data.collections[n].get("lib_procedural")]:
            if hand_edited(name) and not FORCE and name not in ONLY:
                kept.add(name)
                print("[build_library] KEPT %s: hand-edited since it was generated (the artist's now; --only=%s "
                      "regenerates it)" % (name, name))
                continue
            if name not in names or not ONLY or name in ONLY:
                remove_piece(name)
        for name, cat, mesh in built:
            if name in kept or (ONLY and name not in ONLY and bpy.data.collections.get(name) is not None):
                bpy.data.meshes.remove(mesh)
                continue
            col = install_piece(name, cat, mesh, "procedural (blender/tools/library_procedural.py)", procedural=True)
            col["edit_note"] = proc.EDIT_NOTES.get(name, proc.EDIT_NOTE_DEFAULT)
            d = mesh_dims(mesh)
            print("[build_library] procedural %-22s %-8s %5.2f x %5.2f x %5.2f m" % (name, cat, d[0], d[1], d[2]))
        relayout()
        for name in names:
            col = bpy.data.collections.get(name)
            if col is not None and name not in kept:
                col["lib_generated"] = fingerprint(col)
                for o in col.objects:
                    o["edit_note"] = col["edit_note"]
        readme = bpy.data.texts.get("README_artist") or bpy.data.texts.new("README_artist")
        readme.from_string(open(os.path.join(KIT, "ARTIST_NOTES.md")).read())
    relayout()
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print("[build_library] %d pieces -> %s" % (len(piece_names()), os.path.relpath(BLEND, ROOT)))


main()
