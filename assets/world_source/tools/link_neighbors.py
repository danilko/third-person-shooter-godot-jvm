#!/usr/bin/env python3
"""
link_neighbors.py — link a district's ADJACENT district pieces (and optionally the master's
always-resident arterial/deck content) INTO that district's own .blend, positioned at their true
relative world offsets, so you can hand-edit the district's border ground/roads while SEEING what
it must meet — without ever combining/appending districts into one file.

This is the in-context seam-editing workflow (see AUTHORING_GUIDE.md "Editing across district
borders"). Key properties:
  * TRUE library links (link=True, the build_debug_preview.py mechanism) — the neighbours stay
    read-only references that live-update when their source .blend is rebuilt/edited; nothing is
    copied, the file stays light (a linked district loads in ~1s).
  * Everything lands in a dedicated NEIGHBOR_REF collection that (a) tools/export_world.py drops
    before every export — it can NEVER reach the game — and (b) build_district.py's regen
    preserves (reopen path), so you link once and the context survives rebuilds.
  * Offsets come from lib/world_grid.py (district_center/elev_at), i.e. the SAME numbers the
    runtime uses to place streamed districts — what you see lining up in Blender is what lines
    up in-game. A neighbour appears at ±504 m on X/Y and at its theme-elevation delta on Z.

RUN (on the district you want to edit; saves the .blend in place):
  blender --background assets/world_source/districts/District_city_1_1.blend \
      --python assets/world_source/tools/link_neighbors.py -- [options]

Options (after --):
  --diagonals          also link the 4 diagonal neighbours (default: the 4 edge-adjacent ones)
  --master[=C1,C2]     also link collections from world_master.blend at the correct offset
                       (default ARTDECK — the always-resident arterial deck + safety floor that
                       crosses every seam; the runtime keeps it resident too)
  --clear              remove all NEIGHBOR_REF content instead of adding, then save
"""
import bpy, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import world_grid as wg

REF_COLL = "NEIGHBOR_REF"


def _local_coll(name):
    """Local (non-library) collection by name — with neighbours linked in, several libraries can
    each contribute a same-named collection (e.g. STREET), so a bare bpy.data.collections.get()
    may return a linked one."""
    for c in bpy.data.collections:
        if c.name == name and c.library is None:
            return c
    return None


def _ref_coll():
    c = _local_coll(REF_COLL)
    if c is None:
        c = bpy.data.collections.new(REF_COLL)
        bpy.context.scene.collection.children.link(c)
    return c


def _clear_refs(ref):
    for o in list(ref.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    # drop now-unused linked collections/libraries so re-linking starts clean
    try:
        bpy.data.orphans_purge(do_recursive=True)
    except Exception:
        pass


def _link_collection(abspath, coll_name):
    with bpy.data.libraries.load(abspath, link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == coll_name]
    return dst.collections[0] if dst.collections else None


def _instance(ref, name, coll, loc):
    inst = bpy.data.objects.new(name, None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = coll
    inst.location = loc
    ref.objects.link(inst)
    return inst


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = bpy.data.filepath
    m = re.match(r"^District_([a-z]+)_(\d+)_(\d+)\.blend$", os.path.basename(blend))
    if not m:
        print(f"ERROR: open a coordinate-named district .blend "
              f"(District_<theme>_<gx>_<gy>.blend), got: {os.path.basename(blend) or '(none)'}")
        sys.exit(2)
    gx, gy = int(m.group(2)), int(m.group(3))
    my_elev = wg.elev_at(gx, gy)
    my_cx, my_cy = wg.district_center(gx, gy)

    ref = _ref_coll()
    _clear_refs(ref)                              # idempotent: full refresh every run

    if "--clear" in argv:
        bpy.ops.wm.save_mainfile()
        print(f"cleared {REF_COLL} in {os.path.basename(blend)}")
        return

    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if "--diagonals" in argv:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]

    linked = skipped = 0
    for dx, dy in offsets:
        nx, ny = gx + dx, gy + dy
        if not (0 <= nx < wg.GRID_N and 0 <= ny < wg.GRID_N):
            continue
        stem = wg.piece_stem(nx, ny, wg.theme_at(nx, ny))
        abspath = os.path.join(ROOT, "districts", stem + ".blend")
        if not os.path.exists(abspath):
            print(f"  skip {stem}: not built yet")
            skipped += 1
            continue
        st = _link_collection(abspath, "STREET")
        if st is None:
            print(f"  skip {stem}: no STREET collection")
            skipped += 1
            continue
        # neighbour's local origin relative to mine: grid offset on X/Y, theme-elevation
        # delta on Z — identical to how the runtime places both streamed pieces.
        loc = (dx * wg.DISTRICT, dy * wg.DISTRICT, wg.elev_at(nx, ny) - my_elev)
        _instance(ref, f"NB_{stem}", st, loc)
        print(f"  linked {stem} at ({loc[0]:+.0f}, {loc[1]:+.0f}, {loc[2]:+.1f})")
        linked += 1

    master_colls = None
    for a in argv:
        if a == "--master":
            master_colls = ["ARTDECK"]
        elif a.startswith("--master="):
            master_colls = [c for c in a.split("=", 1)[1].split(",") if c]
    if master_colls:
        master = os.path.join(ROOT, "world_master.blend")
        for cname in master_colls:
            mc = _link_collection(master, cname)
            if mc is None:
                print(f"  skip master {cname}: collection not found")
                continue
            # master content is world-placed; shift it into this district's local frame.
            _instance(ref, f"NB_MASTER_{cname}", mc, (-my_cx, -my_cy, -my_elev))
            print(f"  linked master {cname} at ({-my_cx:+.0f}, {-my_cy:+.0f}, {-my_elev:+.1f})")
            linked += 1

    bpy.ops.wm.save_mainfile()
    print(f"{REF_COLL}: {linked} linked, {skipped} skipped in {os.path.basename(blend)} "
          f"(read-only references; dropped automatically at export)")


main()
