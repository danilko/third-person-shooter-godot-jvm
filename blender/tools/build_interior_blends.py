"""Build the mission buildings' .blend files (user, 2026-09-28: "one more complex / detailed internal for a Japanese
office building (office layout, elevator, stairs), yard, resort, fire station, police station, hospital ... so
characters compete in it for missions, usable by a level designer instead of the current block"; "use the Blender ->
Godot path, and note for the artist to change placeholders").

    blender -b --python-exit-code 1 --python blender/tools/build_interior_blends.py -- [--only=Koban] [--force=Name]

One file per building in assets/world_source/kits/interiors/<Id>.blend, holding ONE piece collection `<Id>` (the
whole building: shell, floors, stairs, lift shafts, rooms, furniture) laid out from blender/tools/interior_plans.py.
The file is then the ARTIST'S: a regenerate keeps a piece whose fingerprint (`ib_generated`) no longer matches and
says so; `--force=<Id>` overwrites it (ask first). After an edit: tools/building_kit/build_buildings.sh.
"""
import hashlib
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import interior_kit as IK  # noqa: E402
import interior_plans as IP  # noqa: E402
import interior_plans_jp as IPJ  # noqa: E402
from library_palette import material  # noqa: E402
from library_procedural import Builder  # noqa: E402

ROOT = IK.ROOT
KIT = os.path.join(ROOT, "assets", "world_source", "kits", "interiors")
PLANS = {**IP.PLANS, **IPJ.PLANS}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ONLY = {n for a in argv if a.startswith("--only=") for n in a[len("--only="):].split(",") if n}
FORCE = {n for a in argv if a.startswith("--force=") for n in a[len("--force="):].split(",") if n}


def fingerprint(col):
    h = hashlib.sha1()
    for o in sorted(col.objects, key=lambda o: o.name):
        m = o.matrix_world
        h.update(("%s|%s;" % (o.name.split(".")[0], ",".join("%.4f" % v for row in m for v in row))).encode())
        for k in sorted(o.keys()):
            if k != "edit_note":
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


def build(bid):
    path = os.path.join(KIT, "%s.blend" % bid)
    if os.path.exists(path):
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.name = bid
    col = bpy.data.collections.get(bid)
    if col is not None and col.get("ib_generated") and col["ib_generated"] != fingerprint(col) and bid not in FORCE:
        print("[build_interior_blends] KEPT %s: edited by hand (--force=%s overwrites the artist's edit; ask first)"
              % (bid, bid))
        return True
    b = IK.Bld(bid, Builder, material)
    spec = PLANS[bid](b)
    remove_collection(bid)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    meshes = IK.library_meshes(sorted({o[0] for o in b.objs}))
    b.check_doorways(meshes)
    col = bpy.data.collections.new(bid)
    bpy.context.scene.collection.children.link(col)
    b.install(col, meshes)
    col["bk_piece_path"] = "pieces/%s/%s.gltf" % (bid.lower(), bid)
    col["bk_category"] = bid.lower()
    note = IP.NOTE + " " + spec.get("note", "")
    col["edit_note"] = note
    for o in col.objects:
        o["edit_note"] = note
    col.instance_offset = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    col["ib_generated"] = fingerprint(col)
    readme = bpy.data.texts.get("README_artist") or bpy.data.texts.new("README_artist")
    readme.from_string(open(os.path.join(KIT, "ARTIST_NOTES.md")).read())
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    n_mesh = sum(1 for o in col.objects if o.type == "MESH")
    print("[build_interior_blends] %-14s %4d objects (%d furniture), %d doors, %d exits, %d lifts, %d markers -> %s"
          % (bid, len(col.objects), len(b.objs), sum(1 for e in b.empties if e[0].startswith("DOOR_")),
             sum(1 for e in b.empties if e[0].startswith("EXIT_")), sum(1 for e in b.empties if e[0].startswith("LIFT_")),
             sum(1 for e in b.empties if e[0].startswith("MARK_")), os.path.relpath(path, ROOT)))
    return False


def main():
    os.makedirs(KIT, exist_ok=True)
    kept = [bid for bid in PLANS if (not ONLY or bid in ONLY) and build(bid)]
    if kept:
        sys.exit(3)


main()
