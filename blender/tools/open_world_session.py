#!/usr/bin/env python3
"""
open_world_session.py -- open (or refresh) the persistent whole-world editing session,
world_session.blend: every registered piece's content (MANUAL, STREET/OVERLAY, and anything else
its own .blend has, nested under a `Piece__<id>` wrapper) -- grid district or freestanding piece
alike, no distinction (FREESTANDING_PIECES_PLAN.md §E) -- see lib/session_common.py -- always in
the SAME file, so there is exactly one obvious file to open, every time. See AUTHORING_GUIDE.md §4.

This is the whole-world generalization of tools/open_district_group.py (same append mechanism,
lib/session_common.py), but PERSISTENT instead of disposable:

  * Stable filename (world_session.blend, gitignored -- a working session, not a build output,
    unlike the git-tracked world_master.blend which IS a build output).
  * REFRESH semantics on a second (or Nth) run: never re-appends/clobbers a `Piece__<id>` wrapper
    already present in the file -- it may hold unsynced edits. Only ADDS newly-registered pieces
    not yet in the session. Pass --hard-resync <item> ... to deliberately force-discard local
    edits and re-append specific items fresh from disk (never implicit).
  * --unload <item> ... removes a piece from THIS session file only -- a local scene-editing
    decision, NOT a world/game one (contrast the addon's "Remove Piece", which deletes the
    piece's .blend and its pieces.json entry for real and rebuilds the master). For trimming a
    large session (all
    37+ pieces) down to just what you're actively editing, to avoid the depsgraph-scale crash
    risk a very large scene can hit under heavy Geometry Nodes editing -- the piece's own .blend,
    its pieces.json entry, and the game world are all untouched; re-run without --unload (or use
    "Add District(s)"/the addon panel) to bring it back any time. If the piece had unsynced
    edits, they're discarded from this file (write it back first if you want to keep them).
    --unload-all is the same operation applied to EVERY currently-present item in one shot (drop
    to a near-empty session in one command instead of listing all 37+ ids) -- a plain re-run with
    no unload flag afterward brings everything back (step 3 re-adds anything missing).
  * Stale pruning: if a present piece's grid cell has since been marked void (lib/world_grid.py's
    is_void), or it's no longer in the registry / its .blend no longer exists, refresh drops it
    from the session -- but ONLY if its fingerprint still matches its recorded baseline (no
    pending edits). A piece with pending edits that's about to go void/missing/deregistered ABORTS
    the whole run with an error instead (write back first, or pass --force-drop <item> to discard
    those edits on purpose).
  * A WORLD_NAV collection, regenerated fresh every run (no hand data to preserve there): for
    every GRID cell (lib/world_grid.py, including void and not-yet-built ones) a theme-tinted flat
    plate (inset a few metres from its true boundary, so the gap between plates reads as the grid
    lines) + a named, floating-label Empty (`show_name`); every OTHER registered piece
    (freestanding -- no grid cell) gets just the floating label at its registered position, no
    plate (an arbitrary footprint has no fixed "grid inset" to draw). Either way, an artist can
    see every gap and every piece, built or not, and jump to any of them.

Usage:
  blender --background --python tools/open_world_session.py -- \\
      [--hard-resync <item> ...] [--force-drop <item> ...] [--unload <item> ...] [--unload-all]

  First run creates world_session.blend from every registered piece. Every later run refreshes it
  in place (adds newly-registered pieces, prunes stale ones, rebuilds WORLD_NAV) without touching
  any existing wrapper's content.

Then open assets/world_source/world_session.blend normally in Blender and edit anywhere. When
done, run tools/writeback_world_session.py against it.
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                                    # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import session_common as sc
import piece_registry as pr
import world_grid as wg
import kit_common as kc

SESSION_PATH = os.path.join(ROOT, "world_session.blend")
NAV_COLL = "WORLD_NAV"


def _local_coll(name):
    for c in bpy.data.collections:
        if c.name == name and c.library is None:
            return c
    return None


def _existing_wrapper_items():
    """{piece_id: wrapper_collection} for EVERY Piece__<id> wrapper currently in the file."""
    present = {}
    for c in bpy.data.collections:
        if c.library is not None:
            continue
        piece_id = sc.piece_id_from_wrapper(c.name)
        if piece_id is not None:
            present[piece_id] = c
    return present


def _rebuild_nav(scene, registered_ids):
    old = _local_coll(NAV_COLL)
    if old is not None:
        sc.remove_collection_recursive(old)
    nav = bpy.data.collections.new(NAV_COLL)
    scene.collection.children.link(nav)

    inset = 4.0                                   # gap between plates reads as the grid lines
    half = wg.DISTRICT / 2.0 - inset
    n_labels = 0
    grid_ids = set()
    for gy in range(wg.GRID_N):
        for gx in range(wg.GRID_N):
            cx, cy = wg.district_center(gx, gy)
            if wg.is_void(gx, gy):
                label_name, elev, tint = f"void_{gx}_{gy}", 0.0, "line_w"
            else:
                theme = wg.theme_at(gx, gy)
                stem = wg.piece_id_for_cell(gx, gy)
                grid_ids.add(stem)
                elev = wg.elev_at(gx, gy)
                tint = wg.THEMES[theme]["col"]
                built = stem in registered_ids
                label_name = stem if built else f"unbuilt_{stem}"

            kc.box(f"NAV_{gx}_{gy}", cx - half, cx + half, cy - half, cy + half,
                   elev - 0.3, elev - 0.2, nav, tint)

            label = bpy.data.objects.new(f"LABEL_{label_name}", None)
            label.empty_display_type = 'PLAIN_AXES'
            label.empty_display_size = 10.0
            label.location = (cx, cy, elev + 5.0)
            label.show_name = True
            nav.objects.link(label)
            n_labels += 1

    # Every registered piece that ISN'T a grid cell (freestanding) -- just a floating label at its
    # real position, no plate (an arbitrary footprint has no fixed "grid inset" to draw).
    n_freestanding = 0
    for piece_id in sorted(registered_ids - grid_ids):
        x, y, z = pr.piece_by_id(piece_id)["position"]
        label = bpy.data.objects.new(f"LABEL_{piece_id}", None)
        label.empty_display_type = 'PLAIN_AXES'
        label.empty_display_size = 10.0
        label.location = (x, y, z + 5.0)
        label.show_name = True
        nav.objects.link(label)
        n_freestanding += 1
    print(f"WORLD_NAV: {n_labels} grid-cell labels, {n_freestanding} freestanding-piece labels")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    hard_resync = set()
    force_drop = set()
    unload = set()
    unload_all = False
    mode = None
    for a in argv:
        if a == "--hard-resync":
            mode = "resync"; continue
        if a == "--force-drop":
            mode = "drop"; continue
        if a == "--unload":
            mode = "unload"; continue
        if a == "--unload-all":
            unload_all = True; mode = None; continue
        (hard_resync if mode == "resync" else force_drop if mode == "drop"
         else unload if mode == "unload" else set()).add(a)

    kc.setup_units()
    is_fresh = not os.path.exists(SESSION_PATH)
    if not is_fresh:
        bpy.ops.wm.open_mainfile(filepath=SESSION_PATH)
    scene = bpy.context.scene

    wanted = {p["id"] for p in pr.all_pieces() if os.path.exists(
        os.path.join(pr.PIECES_DIR, p["id"] + ".blend"))}
    present = _existing_wrapper_items()

    added = kept = pruned = resynced = errors = 0

    # 1) Stale pruning: present but no longer wanted (deregistered, or its .blend deleted, or a
    # grid cell gone void).
    for item, coll in list(present.items()):
        if item in wanted:
            continue
        if sc.is_dirty(coll) and item not in force_drop:
            print(f"ERROR: {item} has unsynced edits but is no longer in the world (void, "
                  f"deregistered, or its .blend deleted) -- write it back first, or pass "
                  f"--force-drop {item} to discard those edits on purpose. Aborting refresh with "
                  f"NOTHING saved.")
            errors += 1
            continue
        sc.remove_collection_recursive(coll)
        del present[item]
        pruned += 1
        print(f"  pruned {item} (no longer registered/built/void)"
              f"{' -- edits discarded' if item in force_drop else ''}")

    if errors:
        print(f"ABORTED: {errors} item(s) blocked pruning -- nothing written to {SESSION_PATH}")
        sys.exit(1)

    # 2) Hard-resync: force-discard local edits, re-append fresh from disk.
    for item in hard_resync:
        if item in present:
            sc.remove_collection_recursive(present[item])
            del present[item]
        wrapper, err = sc.append_piece_content(item, scene)
        if wrapper is None:
            print(f"  WARNING: --hard-resync {item}: {err}")
            continue
        present[item] = wrapper
        resynced += 1
        print(f"  hard-resynced {item}")

    # 3) Add newly-registered pieces not yet present (never touches an existing collection).
    for item in sorted(wanted - set(present)):
        wrapper, err = sc.append_piece_content(item, scene)
        if wrapper is None:
            print(f"  WARNING: {item}: {err}")
            continue
        present[item] = wrapper
        added += 1
        print(f"  added {item}")

    kept = len(wanted & set(present)) - added - resynced

    # 4) Explicit --unload (or --unload-all, its "every currently-present item" shorthand): a
    # local scene-editing decision (this file only), not a world/game one -- runs LAST so it
    # always wins even if this same invocation just added/resynced the item above. Discards
    # unsynced edits from THIS file if present (write back first to keep them); the piece's own
    # .blend/pieces.json entry/the game world are untouched.
    if unload_all:
        unload |= set(present)
    unloaded = 0
    for item in sorted(unload):
        was_dirty = sc.unload_piece(item)
        if was_dirty is None:
            print(f"  --unload {item}: not currently in this session -- nothing to do")
            continue
        del present[item]
        unloaded += 1
        print(f"  unloaded {item}"
              f"{' -- WARNING: had unsynced edits, now discarded from this file only '
                 '(its own .blend on disk is untouched)' if was_dirty else ''}")

    _rebuild_nav(scene, wanted)

    # Free every 0-user datablock any pruning/hard-resync/unload above left behind -- otherwise
    # they get saved into the file too (bloating world_session.blend on disk across repeated
    # refreshes) on top of the live-session slowdown session_common.purge_orphans() documents.
    sc.purge_orphans()

    bpy.ops.wm.save_as_mainfile(filepath=SESSION_PATH)
    verb = "created" if is_fresh else "refreshed"
    print(f"{verb} {SESSION_PATH}: {added} added, {resynced} hard-resynced, {kept} kept "
          f"as-is (may hold unsynced edits), {pruned} pruned, {unloaded} unloaded. Total items "
          f"in session: {len(wanted & set(present))}.")
    print("This file is a working session, not a source of truth -- never git-track it "
          "(already gitignored). Run tools/writeback_world_session.py when ready to export.")


main()
