#!/usr/bin/env python3
"""link_world.py -> world_overview.blend — the WHOLE world as live library links.

One persistent, re-runnable inspection file that shows every built district at its true world
position, plus the master's markers (and ARTDECK when a --full master built one) and every
overlay (Rainbow Bridge, ...) — for seam debugging, layout visualization and "does the world
hang together" checks, WITHOUT copying anything:

  * TRUE LIBRARY LINKS (`link=True`, the build_debug_preview.py mechanism — measured seconds vs
    60+ s for append): each district contributes one Collection-Instance empty `Piece_<gx>_<gy>`
    holding its linked STREET + MANUAL collections. Linked data is a live reference — edit and
    save a district source .blend, reopen (or Blender: File > External Data > Reload) the
    overview, the edit is there. No rebuild step.
  * Content edits ALWAYS happen in the district's own .blend (linked data is read-only here —
    a feature: the overview can't corrupt a source file).
  * Moving a `Piece_*` empty is VISUALIZATION-ONLY: runtime positions come solely from
    lib/world_grid.py `district_center`/`elev_at` (the single source of truth), and every re-run
    of this tool rebuilds the file from scratch, snapping empties back.

RUN (re-run any time; the file is 100% regenerated):
  blender --background --python tools/link_world.py

Output: assets/world_source/world_overview.blend
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                                    # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import world_grid as wg         # noqa: E402
import kit_common as kc         # noqa: E402
import assemble as asm          # noqa: E402
import piece_registry as pr     # noqa: E402

# master collections worth showing when they exist (minimal masters have no ARTDECK — skip
# cleanly; MARKERS = region/zone/landmark empties, HARBOR/RING = authored world content).
# LAYOUT is deliberately NOT here: it holds the master's own linked-district Piece_* instances
# (tools/build_world.py) — the overview links every district directly below, so pulling the
# master's LAYOUT too would show each piece twice.
MASTER_COLLS = ["MARKERS", "ARTDECK", "HARBOR", "RING"]
# per-district collections to link (everything exported: generated street + hand-authored).
PIECE_COLLS = ["STREET", "MANUAL"]

# link/instance mechanics live in kit_common (shared with tools/build_world.py, whose LAYOUT
# now links every built district the same way — the overview stays useful as the file that
# ALSO shows overlays + master markers together, with a framing camera, and that never needs
# a master rebuild to refresh).
_link_collections = kc.link_collections
_instance = kc.instance_collection


def main():
    kc.setup_units()
    asm.wipe_scene()
    dest = kc.get_coll("WORLD_OVERVIEW")

    # ── districts: every built piece of the 6x6 grid at its true center + theme elevation ──
    linked = missing = 0
    grid_ids = set()
    for gy in range(wg.GRID_N):
        for gx in range(wg.GRID_N):
            stem = wg.piece_id_for_cell(gx, gy)
            grid_ids.add(stem)
            abspath = os.path.join(ROOT, "pieces", stem + ".blend")
            if not os.path.exists(abspath):
                print(f"  skip ({gx},{gy}) {stem}: not built yet")
                missing += 1
                continue
            colls = _link_collections(abspath, PIECE_COLLS)
            if not colls:
                print(f"  skip ({gx},{gy}) {stem}: no {'/'.join(PIECE_COLLS)} collections")
                missing += 1
                continue
            cx, cy = wg.district_center(gx, gy)
            loc = (cx, cy, wg.elev_at(gx, gy))
            for c in colls:
                _instance(dest, f"Piece_{gx}_{gy}" + ("" if c.name == "STREET" else f"_{c.name}"),
                          c, loc)
            print(f"  linked {stem} at ({cx:+.0f}, {cy:+.0f}, {loc[2]:+.1f})"
                  f" [{'+'.join(c.name for c in colls)}]")
            linked += 1

    # ── master (world-positioned content links at origin) ──
    master_path = os.path.join(ROOT, "world_master.blend")
    n_master = 0
    if os.path.exists(master_path):
        for c in _link_collections(master_path, MASTER_COLLS):
            _instance(dest, f"Master_{c.name}", c, (0.0, 0.0, 0.0))
            print(f"  linked master {c.name}")
            n_master += 1
    else:
        print(f"  WARNING: {master_path} not found — master layer skipped")

    # ── freestanding pieces: any registered piece the grid walk above didn't already cover
    # (e.g. the bridge) -- its own geometry is already authored directly in true world-space
    # coordinates (unlike a district's locally-centred content), so the instance itself needs
    # NO additional offset -- (0,0,0), same as before this was registry-driven.
    n_freestanding = 0
    for piece in pr.all_pieces():
        if piece["id"] in grid_ids:
            continue
        abspath = os.path.join(ROOT, "pieces", piece["id"] + ".blend")
        if not os.path.exists(abspath):
            continue
        for c in _link_collections(abspath, PIECE_COLLS + ["OVERLAY"]):
            _instance(dest, f"{piece['id']}_{c.name}", c, (0.0, 0.0, 0.0))
            n_freestanding += 1
        print(f"  linked freestanding {piece['id']}")

    # ── viewport aids: sun + top-down ortho camera framing the whole grid ──
    sun_data = bpy.data.lights.new("OverviewSun", type='SUN')
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("OverviewSun", sun_data)
    sun.location = (100, -100, 400)
    sun.rotation_euler = (0.9599, 0, 0.6109)
    dest.objects.link(sun)
    cam_data = bpy.data.cameras.new("OverviewCam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = wg.WORLD * 1.15
    cam_data.clip_end = kc.VIEW_CLIP_END
    cam = bpy.data.objects.new("OverviewCam", cam_data)
    cam.location = (0, 0, 600)
    dest.objects.link(cam)
    bpy.context.scene.camera = cam

    out_path = os.path.join(ROOT, "world_overview.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_path)
    print(f"link_world: saved {out_path} — {linked} districts linked, {missing} missing, "
          f"{n_master} master collections, {n_freestanding} freestanding-piece collections")


if __name__ == "__main__":
    main()
