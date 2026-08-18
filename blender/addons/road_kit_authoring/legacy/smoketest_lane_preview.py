#!/usr/bin/env python3
"""
smoketest_lane_preview.py -- headless verification for RKA_OT_preview_lane_curves /
RKA_OT_clear_lane_curve_preview (2026-08, user-requested: "a manual one-time click to form the
curve, and remove afterward with button click, to ensure the port/other data will form current
path3d logic is correct in blender"). Confirms: the preview builds exactly one curve per lane
across every piece in the file (matching `lane_export.collect_pieces`'s own lane count, the SAME
function `tools/save_lane_kit.py` uses for the real `.lanekit.json` export), re-running rebuilds
cleanly (no leaked/duplicated objects from a stale previous preview), and Clear removes every
object/curve datablock it created with no leftovers (`bpy.data.curves`/`bpy.data.objects` counts
return exactly to their pre-preview baseline).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_lane_preview.py
"""
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import spine_io      # noqa: E402
from road_kit_authoring import lane_export                 # noqa: E402
from road_kit_authoring.ops_lane_preview import LANE_PREVIEW_COLLECTION  # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    context = bpy.context

    # A no-op: nothing built yet.
    ret = bpy.ops.rka.preview_lane_curves()
    _assert(ret == {'CANCELLED'}, "preview with no pieces built should CANCEL, got %s" % (ret,))
    print("smoketest_lane_preview: no-pieces case correctly cancels, no crash")

    # Build a real intersection + a widening segment (the same scenario
    # smoketest_turn_lane_widen.py uses) so there's real multi-piece lane data to preview.
    ret = bpy.ops.rka.build_intersection('EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=2,
                                          kerb_radius=9.0, tail_length=12.0, segments=8,
                                          curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=2,
        lanes_backward=2, median_width=6.0, lanes_end=3, median_width_end=2.0, align='left',
        curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, ret)

    baseline_objs = len(bpy.data.objects)
    baseline_curves = len(bpy.data.curves)

    pieces = lane_export.collect_pieces("smoketest", context.scene, bpy.data, godot_space=False)
    expected_lanes = sum(len(d["lanes"]) for _name, d, _zone in pieces)
    _assert(expected_lanes > 0, "expected at least one lane across the built pieces")

    ret = bpy.ops.rka.preview_lane_curves()
    _assert(ret == {'FINISHED'}, "preview_lane_curves did not finish: %s" % (ret,))
    coll = bpy.data.collections.get(LANE_PREVIEW_COLLECTION)
    _assert(coll is not None, "RKA_LanePreview collection should exist after preview")
    _assert(len(coll.objects) == expected_lanes,
            "preview should build exactly %d curves (one per exported lane), got %d"
            % (expected_lanes, len(coll.objects)))
    _assert(all(o.type == 'CURVE' for o in coll.objects), "every preview object should be a Curve")
    # Blender-native space check: every preview point should land within the same rough bounding
    # volume as the authored geometry (a coarse sanity check that no Godot axis-flip slipped in --
    # a flipped/rotated preview would have wildly different X/Y/Z ranges than the ~40m-long
    # segment + ~24m-wide intersection actually built).
    all_pts = [tuple(p.co)[:3] for o in coll.objects for p in spine_io.points(o)]
    xs = [p[0] for p in all_pts]
    _assert(max(xs) - min(xs) < 100.0, "preview X extent looks wrong for this scene: %.1f"
            % (max(xs) - min(xs)))
    print("smoketest_lane_preview: built %d preview curves matching the exported lane count "
          "(%d), in Blender-native space" % (len(coll.objects), expected_lanes))

    # Re-running clears the stale preview first -- no duplication/leak across repeated clicks.
    ret = bpy.ops.rka.preview_lane_curves()
    _assert(ret == {'FINISHED'}, ret)
    coll = bpy.data.collections.get(LANE_PREVIEW_COLLECTION)
    _assert(len(coll.objects) == expected_lanes,
            "re-running Preview should still have exactly %d curves (no duplication), got %d"
            % (expected_lanes, len(coll.objects)))
    print("smoketest_lane_preview: re-running Preview does not duplicate/leak objects")

    ret = bpy.ops.rka.clear_lane_curve_preview()
    _assert(ret == {'FINISHED'}, "clear_lane_curve_preview did not finish: %s" % (ret,))
    _assert(bpy.data.collections.get(LANE_PREVIEW_COLLECTION) is None,
            "RKA_LanePreview collection should be gone after Clear")
    _assert(len(bpy.data.objects) == baseline_objs,
            "object count should return to baseline (%d) after Clear, got %d"
            % (baseline_objs, len(bpy.data.objects)))
    _assert(len(bpy.data.curves) == baseline_curves,
            "curve datablock count should return to baseline (%d) after Clear, got %d -- a "
            "leaked curve datablock" % (baseline_curves, len(bpy.data.curves)))
    print("smoketest_lane_preview: Clear removes every object/curve datablock, back to baseline")

    # Clear with nothing to clear is a graceful no-op, not an error.
    ret = bpy.ops.rka.clear_lane_curve_preview()
    _assert(ret == {'FINISHED'}, "clear with nothing to clear should still FINISH, got %s" % (ret,))
    print("smoketest_lane_preview: clearing an already-empty preview is a graceful no-op")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
