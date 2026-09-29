"""Build library.blend: the project's own central library of Japanese building parts, interiors and props.

    blender -b --python-exit-code 1 --python blender/tools/build_library.py -- [--procedural] [--force]

library.blend OWNS its pieces (the building-kit rule): after this has run, edit a piece in the .blend and run
`tools/building_kit/build_buildings.sh`, which exports them through `export_building_kit.py`.

* `--procedural` (re)builds only the pieces this script models itself (library_procedural.py, library_landmarks.py):
  the collections flagged `lib_procedural`. **A piece an artist has edited is never overwritten:** each generated
  piece stores a fingerprint of its mesh and materials (`lib_generated`); a piece whose fingerprint no longer matches
  has been hand-edited and is KEPT (and reported), becoming the artist's. `--force`, or `--only=Name,Name`, regenerates
  such a piece on purpose. Every piece carries an `edit_note` (Object/Collection properties) saying what the game
  assumes about it, and the file carries a `README_artist` text; see also `kits/library/ARTIST_NOTES.md`.
  Everything else in the file is left alone, so hand edits and the placeholder pieces survive.
* The pieces once cut from elbolilloduro's packs are GONE (2026-09-28, owner decision: provenance not confirmable);
  they are same-size placeholder boxes listed in `kits/library/placeholders.json`, owned by library.blend like any
  hand-modelled piece (`blender/tools/replace_removed_meshes.py` is the record). This script never touches them.

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
DO_PROC = True    # the only job left: --procedural is accepted for old command lines
FORCE = "--force" in argv
ONLY = {n for a in argv if a.startswith("--only=") for n in a[len("--only="):].split(",") if n}
GRID = 6.0          # metres between piece spots in the file
ROW = 8             # spots per row


# ── materials: the palette's one owner is library_palette.py ─────────────────────────────────────────────────

from library_palette import PALETTE, material  # noqa: E402,F401


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


def mesh_dims(mesh):
    return [max(v.co[i] for v in mesh.vertices) - min(v.co[i] for v in mesh.vertices) for i in range(3)]


def main():
    open_library()
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
