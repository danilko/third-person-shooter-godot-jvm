#!/usr/bin/env python3
"""
open_district_group.py -- APPEND (not link) a chosen small group of pieces' content into one
temporary scratch .blend, positioned at their true relative world offsets, so an author can
hand-edit/reshape geometry (roads AND ground/terrain) that spans a shared seam between two or more
pieces -- district-district, or a former overlay's touchdown onto a district (a bridge/highway
ramp meeting local roads) -- in ONE combined Edit-Mode session. No distinction between a grid
district and a freestanding piece anywhere in this file (FREESTANDING_PIECES_PLAN.md §E) -- both
are just "a piece id", resolved through the registry.

Why this exists: neither read-only linking (link_neighbors.py, world_master.blend,
tools/link_world.py, tools/build_debug_preview.py) nor Blender's Library Override system can
support this -- both are fundamentally read-only / whole-object-transform-only against linked
data, and Blender never allows editing linked mesh/curve vertex data under any circumstance. Every
piece is now permanently hand-edited (AUTHORING_GUIDE.md §2 -- there is no generator left to
regenerate STREET or MANUAL, so aligning road/ground geometry that genuinely spans two pieces'
seam (or a former overlay's touchdown) needs actual local mesh access to both at once, which only
APPENDING provides.

This is a SCOPED, TEMPORARY working session, not a permanent merge:
  * only the items you name are combined here (typically 2-4 districts sharing a seam, or one
    former overlay + the district(s) it touches down on), never the whole world (see
    tools/open_world_session.py for that, or tools/link_neighbors.py --all-districts for a
    whole-world READ-ONLY view if that's all you need)
  * each item's top-level collections are APPENDED (bpy.data.libraries.load(link=False)) as real,
    fully-local, freely-editable copies, nested under one `Piece__<id>` wrapper collection so
    provenance stays unambiguous for tools/writeback_district_group.py (see lib/session_common.py)
    -- shifted to its registered world position (lib/piece_registry.py), the SAME offset the
    runtime and every other tool use, so pieces named together always land at their correct
    real-world relative positions with no manual alignment step.
  * each piece's top-level (unparented) objects are shifted by that offset; parented children move
    automatically with their parent.
  * the scratch file is DISPOSABLE -- discard it once tools/writeback_district_group.py has
    written the results back into each item's own .blend and each has been rebuilt/re-validated
    (tools/build_piece.sh + tools/check_seams.py for any touched seam pair); never git-track it

Usage:
  blender --background --python blender/tools/open_district_group.py -- <out_name> <item1> [<item2> ...]

  Each <itemN> is any registered piece id (lib/piece_registry.py / assets/world_source/pieces.json)
  -- a coordinate-named grid piece (Piece_1_1) or a freestanding piece id (Piece_2_3_b, the
  bridge, or any future hand-placed piece) alike. Mix freely.

Example (two districts sharing a seam):
  blender --background --python blender/tools/open_district_group.py -- \\
      _edit_session_1_1_2_1 Piece_1_1 Piece_2_1
  # then open assets/world_source/_edit_session_1_1_2_1.blend normally in Blender and edit;
  # when done, run tools/writeback_district_group.py against it.

Example (a freestanding piece's touchdown onto the district it lands on):
  blender --background --python blender/tools/open_district_group.py -- \\
      _edit_rainbowbridge Piece_2_3_b Piece_5_0
  # build/adjust the bridge's ramp road pieces against the district's real ground/road content,
  # both visible and editable together in one viewport, then write back the same way.
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                                    # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import session_common as sc


def append_item(item, dest_scene):
    """Thin wrapper over session_common's shared append -- prints CLI-friendly progress/warning
    lines (the addon side reports through self.report instead, see ops_group_edit.py)."""
    piece, _abspath = sc.resolve_item(item)
    if piece is None:
        print(f"WARNING: {item}: not a registered piece (see pieces.json) -- skipped")
        return None
    wrapper, err = sc.append_piece_content(item, dest_scene)
    if wrapper is None:
        print(f"WARNING: {item}: {err} -- skipped")
        return None
    objs = sc.all_objects_recursive(wrapper)
    shifted = sum(1 for o in objs if o.parent is None)
    pieces = ", ".join(c.name for c in wrapper.children)
    print(f"  appended {item}: {len(objs)} objects ({shifted} top-level) across [{pieces}]")
    return wrapper


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    out_name, items = argv[0], argv[1:]

    scene = bpy.context.scene
    appended_any = False
    for item in items:
        if append_item(item, scene) is not None:
            appended_any = True
    if not appended_any:
        print("ERROR: nothing appended")
        sys.exit(1)

    out_path = out_name if os.path.isabs(out_name) else os.path.join(ROOT, out_name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_path)
    print(f"saved {out_path} -- edit the Piece__<id> collections' content directly (objects "
          f"tagged '{sc.GROUP_PROP}' for provenance). This file is a disposable working session "
          f"-- do not git-track it. Run tools/writeback_district_group.py against it when done.")


main()
