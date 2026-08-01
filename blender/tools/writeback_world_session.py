#!/usr/bin/env python3
"""
writeback_world_session.py -- read world_session.blend's live dirty flags (one per `Piece__<id>`
wrapper -- see lib/session_common.py/session_dirty.py) and write back ONLY the items that
actually changed (rebuild + seam-check included) -- the smart/partial counterpart to
tools/writeback_district_group.py, which this delegates to for the actual per-item write
mechanics (no duplicated write-back logic). Covers every top-level collection a piece's .blend
has (MANUAL, STREET, OVERLAY, ...) -- editing any of them marks the same per-item wrapper dirty.

Usage (run against the ALREADY-SAVED world_session.blend -- finish editing and save in your
interactive session first, same as any other Blender background-tool invocation):
  blender --background assets/world_source/world_session.blend \\
      --python tools/writeback_world_session.py -- [--force-all] [--dry-run]

  Default: only items whose wrapper is currently flagged dirty are written back. --force-all
  bypasses the filter (every item present is written back, for an explicit "export everything"
  request). --dry-run reports what WOULD be written back without touching any piece .blend or
  this session file's own dirty flags.

  A changed district's seam with an UNCHANGED neighbour can still be a real mismatch (e.g. a
  moved boundary object), so the seam check considers every adjacent DISTRICT pair where AT LEAST
  ONE side is in the changed set, evaluated against the full district universe present in the
  session -- not just pairs strictly within the changed set. A freestanding piece never seam-pairs
  this way (no grid coordinate to be adjacent by -- FREESTANDING_PIECES_PLAN.md §G will replace
  this grid-coordinate heuristic with real footprint-proximity adjacency; until then this only
  covers grid districts, same as before) and is simply excluded from this check.

After a successful (non-dry-run) write-back, each written-back item's dirty flag in THIS session
file is cleared and the session file is re-saved, so the next run reports it clean again.
"""
import os, subprocess, sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                                    # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import session_common as sc
import piece_registry as pr
import world_grid as wg

WRITEBACK_SCRIPT = os.path.join(HERE, "writeback_district_group.py")
CHECK_SEAMS_SCRIPT = os.path.join(HERE, "check_seams.py")
BUILD_PIECE_SH = os.path.join(HERE, "build_piece.sh")
PIECES_DIR = os.path.join(ROOT, "pieces")


def _grid_ids():
    """Every canonical Piece_<gx>_<gy> id the 6x6 grid walk owns -- used ONLY to gate the
    seam-adjacency heuristic below to real grid districts (a freestanding piece, e.g. the bridge,
    gets its own `grid` registry field too now, but its footprint spans several cells so a plain
    Manhattan-distance-1 check doesn't mean anything for it -- this is temporary scaffolding until
    §G's geometric-proximity adjacency replaces it, FREESTANDING_PIECES_PLAN.md Phase 5)."""
    return {wg.piece_id_for_cell(gx, gy) for gy in range(wg.GRID_N) for gx in range(wg.GRID_N)}


def _wrapper_items():
    """{piece_id: wrapper_collection} for EVERY Piece__<id> wrapper in the file."""
    present = {}
    for c in bpy.data.collections:
        if c.library is not None:
            continue
        piece_id = sc.piece_id_from_wrapper(c.name)
        if piece_id is not None:
            present[piece_id] = c
    return present


def _changed_items(present):
    return sorted(item for item, coll in present.items() if sc.is_dirty(coll))


def _adjacent_pairs_touching(changed, all_ids):
    """Every edge-adjacent grid-district pair among all_ids where at least one side is in
    `changed` -- a generalization of ops_group_edit._adjacent_pairs (which only considers pairs
    strictly within one passed-in list) so an unchanged neighbour's seam still gets checked
    against a changed district. Freestanding pieces are excluded (see `_grid_ids` docstring)."""
    grid_ids = _grid_ids()
    coords = {}
    for item in all_ids:
        if item not in grid_ids:
            continue
        piece = pr.piece_by_id(item)
        if piece is not None and piece.get("grid") is not None:
            coords[item] = tuple(piece["grid"])
    changed_set = set(changed)
    pairs, seen = [], set()
    ids_sorted = sorted(all_ids)
    for i, a in enumerate(ids_sorted):
        if a not in coords:
            continue
        ax, ay = coords[a]
        for b in ids_sorted[i + 1:]:
            if b not in coords:
                continue
            if a not in changed_set and b not in changed_set:
                continue
            bx, by = coords[b]
            if abs(ax - bx) + abs(ay - by) == 1 and (a, b) not in seen:
                seen.add((a, b))
                pairs.append((a, b))
    return pairs


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    force_all = "--force-all" in argv
    dry_run = "--dry-run" in argv

    session_path = bpy.data.filepath
    if not session_path:
        print("ERROR: run this WITH world_session.blend already open (blender --background "
              "world_session.blend --python tools/writeback_world_session.py -- ...)")
        sys.exit(2)

    present = _wrapper_items()
    if not present:
        print(f"ERROR: no {sc.WRAPPER_PREFIX}<id> collections found -- is this really "
              f"world_session.blend?")
        sys.exit(1)

    targets = sorted(present) if force_all else _changed_items(present)
    unchanged = sorted(set(present) - set(targets))
    print(f"{len(targets)} changed{' (--force-all)' if force_all else ''}: "
          f"{', '.join(targets) or '(none)'}")
    print(f"{len(unchanged)} unchanged, skipped: {', '.join(unchanged) or '(none)'}")

    if not targets:
        print("Nothing to write back.")
        return
    if dry_run:
        print("--dry-run: not writing anything back.")
        return

    cmd = [bpy.app.binary_path, "--background", "--python", WRITEBACK_SCRIPT, "--",
           session_path] + targets
    print(f"--- writing back {len(targets)} item(s) ---")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("ERROR: writeback_district_group.py failed -- this session file's baselines were "
              "NOT updated, re-run after fixing.")
        sys.exit(1)

    failures = []
    for item in targets:
        print(f"--- building {item} ---")
        r = subprocess.run(["bash", BUILD_PIECE_SH, item], cwd=ROOT,
                            capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr)
            failures.append(item)

    pairs = _adjacent_pairs_touching(targets, list(present))
    seam_warnings = 0
    for a, b in pairs:
        seam_a = os.path.join(PIECES_DIR, a + ".seam.json")
        seam_b = os.path.join(PIECES_DIR, b + ".seam.json")
        r = subprocess.run(["python3", CHECK_SEAMS_SCRIPT, seam_a, seam_b],
                            cwd=ROOT, capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr)
            seam_warnings += 1

    # Clear THIS session file's own dirty flags for what was just written, so the next run
    # reports these items clean again -- the piece file write already happened in the subprocess
    # above; this only updates the session's own bookkeeping copy.
    for item in targets:
        sc.mark_synced(present[item])
    bpy.ops.wm.save_mainfile()

    print(f"Write-back complete: {len(targets) - len(failures)}/{len(targets)} item(s) "
          f"rebuilt OK, {len(pairs)} district seam pair(s) checked, {seam_warnings} disagree.")
    if failures:
        print(f"Build FAILED for: {', '.join(failures)}")
        sys.exit(1)


main()
