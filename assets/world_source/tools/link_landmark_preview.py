#!/usr/bin/env python3
"""
link_landmark_preview.py — link real, already-baked district piece(s)' "STREET" collection
directly into world_master.blend (true library link, same O(1)-per-piece mechanism
build_debug_preview.py uses), positioned at their real world_grid.district_center(gx,gy).

This is a VISUAL AID for opening world_master.blend and actually seeing real content next to the
harbor/ring/other hand-placed content, instead of just each district's flat `Plate_<theme>` box —
world_master.blend otherwise deliberately stays a lightweight marker/plate source (see
build_world.py's own docstring; the C1 Loop is the one other documented exception that loads real
kit geometry). Linked content lands in a dedicated "LANDMARK_PREVIEW" collection so
export_world.py can reliably strip it before every master export/bake (added to its existing
kit-SOURCE drop list) — it never reaches the game, purely a Blender-side reference.

Because it's a TRUE link (not append), re-opening world_master.blend after hand-editing a source
district .blend shows the edit immediately, no relink step.

RUN one district (edits world_master.blend in place):
  blender --background assets/world_source/world_master.blend \\
      --python tools/link_landmark_preview.py -- <district_blend_relpath> <gx> <gy> [<preview_name>]

Example (Dotonbori beside the harbor, gx=3 gy=0):
  blender --background world_master.blend --python tools/link_landmark_preview.py -- \\
      districts/District_harbor_3_0.blend 3 0 Dotonbori

RUN all built districts (every build_district.CONFIG entry with an existing .blend on disk):
  blender --background world_master.blend --python tools/link_landmark_preview.py -- --all
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(ROOT, "towns", "districts"))
import world_grid as wg


def _link_one(abspath, gx, gy, name, preview):
    if not os.path.exists(abspath):
        print(f"  skip {name}: {abspath} does not exist (not built yet)")
        return False

    existing = preview.objects.get(f"Preview_{name}")
    if existing:
        preview.objects.unlink(existing)

    with bpy.data.libraries.load(abspath, link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == "STREET"]
    st = dst.collections[0] if dst.collections else None
    if st is None:
        print(f"  skip {name}: {abspath} has no STREET collection")
        return False

    cx, cy = wg.district_center(gx, gy)
    inst = bpy.data.objects.new(f"Preview_{name}", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = st
    inst.location = (cx, cy, 0.0)
    preview.objects.link(inst)
    print(f"  linked {os.path.basename(abspath)} (STREET) -> district ({gx},{gy}) "
          f"world ({cx:.0f},{cy:.0f})")
    return True


def _get_preview_collection():
    preview = bpy.data.collections.get("LANDMARK_PREVIEW")
    if preview is None:
        preview = bpy.data.collections.new("LANDMARK_PREVIEW")
        bpy.context.scene.collection.children.link(preview)
    return preview


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    print(__doc__)
    sys.exit(2)

preview = _get_preview_collection()

if argv[0] == "--all":
    import build_district as bdmod
    linked = skipped = 0
    for key, cfg in sorted(bdmod.CONFIG.items()):
        abspath = os.path.join(ROOT, "districts", cfg["piece"] + ".blend")
        ok = _link_one(abspath, cfg["gx"], cfg["gy"], cfg["piece"].replace("District_", ""), preview)
        linked += ok
        skipped += not ok
    bpy.ops.wm.save_mainfile()
    print(f"LANDMARK_PREVIEW: linked {linked} districts, skipped {skipped} (not built) "
          f"into world_master.blend")
else:
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    path, gx, gy = argv[0], int(argv[1]), int(argv[2])
    name = argv[3] if len(argv) > 3 else os.path.splitext(os.path.basename(path))[0]
    abspath = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not _link_one(abspath, gx, gy, name, preview):
        sys.exit(1)
    bpy.ops.wm.save_mainfile()
    print(f"linked {os.path.basename(path)} (STREET) into world_master.blend's LANDMARK_PREVIEW "
          f"collection at district ({gx},{gy})")
