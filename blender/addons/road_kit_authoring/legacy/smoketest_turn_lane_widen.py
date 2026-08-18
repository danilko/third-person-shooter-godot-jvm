#!/usr/bin/env python3
"""
smoketest_turn_lane_widen.py -- headless verification that the existing tapered-segment mechanism
(`lanes_end`/`median_width_end`/`align` on `RKA_OT_build_straight_segment`) correctly handles a
segment GAINING a lane (e.g. a 6.0m-median 2-lane-forward road narrowing its median to make room
for a 3rd, left-turn-pocket lane) -- not just dropping one, the only direction every existing
taper smoketest (`smoketest_median_joint_transition.py`, `smoketest_transition_and_spine.py`)
exercises. 2026-08, user follow-up on the median-transition study: "is it possible... to transition
from 2 lane to 3 lane forward... just open an option for a [single] segment to do that logic."

Per `intersection_kit._transition_lane_pairs`'s own docstring, a lane born partway along a widening
taper should start OVERLAPPED with its `merge_target` neighbor's start-side position (a real gore
point, not a disconnected floating lane) -- this is read directly off the pure-Python
`build_segment_from_spine` dict (no rebuild/UI involved) for an exact numeric check, then the same
scenario is run through the real `RKA_OT_build_straight_segment` operator to confirm it builds
without error and the pavement/median widths move in the expected directions.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_turn_lane_widen.py
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
import intersection_kit as ik                              # noqa: E402
from road_kit_authoring import spine_io      # noqa: E402
import kit_common as kc                                     # noqa: E402
import piece_probe as pp  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    context = bpy.context
    scene_coll = context.scene.collection
    bpy.ops.rka.link_curb_kit_library()

    # ===================================================================== pure-Python geometry
    # 2 lanes forward/backward + a 6.0m median at the start; 3 lanes forward (a widen -- room for
    # a left-turn pocket) + a narrower 2.0m median at the end. align='left' so the INNER (median-
    # side) lane is the new/moving one -- the shape a real turn pocket needs (the new lane sits
    # against the narrowing median, not the curb).
    LANE_W = 5.0
    spine = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)]
    seg = ik.build_segment_from_spine(
        spine, LANE_W, lanes=2, lanes_backward=2, segment_id="TLW", median_width=6.0,
        lanes_end=3, lanes_backward_end=2, median_width_end=2.0, align='left')

    # Pavement widens (half_w grows: more lanes + smaller median -- net effect depends on which
    # dominates, but the OUTER curb on the growing side must move outward since a whole extra lane
    # was added while the median shrank, i.e. half_w_end - half_w_start > 0 for THIS scenario:
    # +1 lane (+5.0) - median shrink (+2.0 removed from half) = net +... let's just derive it the
    # same way build_segment_from_spine itself does, not re-guess the formula.)
    median_half_start, median_half_end = 3.0, 1.0   # median_width/2 at each end
    half_w_start = median_half_start + max(2, 2) * LANE_W    # 3.0 + 10.0 = 13.0
    half_w_end = median_half_end + max(3, 2) * LANE_W        # 1.0 + 15.0 = 16.0
    left_curb = seg["curbs"][0]
    _assert(abs(left_curb[0][1] - half_w_start) < 1e-6 and abs(left_curb[-1][1] - half_w_end) < 1e-6,
            "left curb should taper from %.2f to %.2f, got %.2f -> %.2f"
            % (half_w_start, half_w_end, left_curb[0][1], left_curb[-1][1]))
    print("smoketest_turn_lane_widen: pavement widens %.1fm -> %.1fm (extra lane outgrows the "
          "shrinking median)" % (half_w_start, half_w_end))

    # Median narrows (6.0m -> 2.0m), never disappears entirely (both ends stay a genuine two-way
    # median > 0, so median_edges is populated at both ends, not just one).
    med_left = seg["median_edges"][0]
    _assert(abs(med_left[0][1] - median_half_start) < 1e-6 and abs(med_left[-1][1] - median_half_end) < 1e-6,
            "median half-width should taper %.2f -> %.2f, got %.2f -> %.2f"
            % (median_half_start, median_half_end, med_left[0][1], med_left[-1][1]))
    print("smoketest_turn_lane_widen: median narrows %.1fm -> %.1fm (space freed for the new lane)"
          % (2 * median_half_start, 2 * median_half_end))

    # The new (3rd) forward lane is BORN partway along, not present from the start: its 'id' tag
    # is 'L1to2' (merge_target 1 at the start side, its own real index 2 at the end side) per
    # _transition_lane_pairs' align='left' pairing -- NOT a plain 'L2' (which would mean it existed
    # at full offset from t=0, i.e. the disconnected-floating-lane bug this smoketest exists to
    # catch).
    new_lane = next((m for m in seg["lanes"] if m["from"] == "A" and m["lane_out"] == 2), None)
    _assert(new_lane is not None, "no forward lane found ending at the new outer index (2)")
    _assert(new_lane["lane_in"] == 1,
            "the new lane should be born FROM merge_target (index 1, 'left' align's inner "
            "surviving lane), got lane_in=%s" % new_lane["lane_in"])
    _assert(new_lane["id"].endswith("L1to2"), "unexpected lane id: %s" % new_lane["id"])

    # The critical gore-point check: at t=0 the new lane's own centerline must sit EXACTLY on top
    # of merge_target (lane index 1)'s start-side offset -- a real gore point, not a disconnected
    # lane appearing at its own final offset from the very start of the segment.
    lane1_start_offset = median_half_start + (1 + 0.5) * LANE_W   # merge_target's own start offset
    new_lane_start_pt = new_lane["points"][0]
    expected_start_pt = (spine[0][0], spine[0][1] + lane1_start_offset)
    _assert(abs(new_lane_start_pt[0] - expected_start_pt[0]) < 1e-6
            and abs(new_lane_start_pt[1] - expected_start_pt[1]) < 1e-6,
            "new lane should start COINCIDENT with lane 1's start offset (%.3f, %.3f) -- a real "
            "gore point -- got (%.3f, %.3f) (a mismatch here means the new lane floats "
            "disconnected from the pavement at the segment's start)"
            % (expected_start_pt[0], expected_start_pt[1], new_lane_start_pt[0], new_lane_start_pt[1]))
    # ...and by the end it must have moved to its OWN genuine final offset (index 2, not still
    # overlapping lane 1) -- confirms it's a real taper, not a degenerate zero-length one.
    lane2_end_offset = median_half_end + (2 + 0.5) * LANE_W
    new_lane_end_pt = new_lane["points"][-1]
    _assert(abs(new_lane_end_pt[1] - lane2_end_offset) < 1e-6,
            "new lane should END at its own real offset %.3f, got %.3f"
            % (lane2_end_offset, new_lane_end_pt[1]))
    print("smoketest_turn_lane_widen: new (3rd) lane is born exactly coincident with its "
          "merge_target neighbor at t=0 (a real gore point) and reaches its own genuine offset "
          "by t=1 -- not a disconnected floating lane")

    # ============================================================================ real operator
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=LANE_W, lanes=2,
        lanes_backward=2, median_width=6.0, lanes_end=3, lanes_backward_end=2,
        median_width_end=2.0, align='left', curb_l_style='NONE', curb_r_style='NONE',
        median_style='PROFILE', median_asset_collection='Kit_Median_YellowSeparator')
    _assert(ret == {'FINISHED'}, "build_straight_segment (turn-lane widen) did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())
    _assert(seg_coll.get("rka_lanes") == 2 and seg_coll.get("rka_lanes_end") == 3,
            "built segment should record lanes 2 -> 3, got %s -> %s"
            % (seg_coll.get("rka_lanes"), seg_coll.get("rka_lanes_end")))
    _assert(seg_coll.get("rka_median_width") == 6.0 and seg_coll.get("rka_median_width_end") == 2.0,
            "built segment should record median 6.0 -> 2.0, got %s -> %s"
            % (seg_coll.get("rka_median_width"), seg_coll.get("rka_median_width_end")))
    spine_obj = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    # `is_spine`, not a type check: "there is a real live spine" is true of both carrier kinds.
    _assert(spine_io.is_spine(spine_obj), "segment spine should exist")
    # A MEDIAN IS A GAP, asked of the geometry rather than of a `curb_<piece>_median` object
    # (`ROAD_KIT_REDESIGN.md` §7 -- on the modifier-stack path it is a `Median` layer on the
    # carrier and there is no object to count). This piece tapers its median 6.0 -> 2.0 m, so the
    # invariant that actually matters is that the carriageways are held apart by half of that at
    # each end, and by LESS at the end than at the start.
    st = pp.stations(seg_coll)
    s_max = max(v[0] for v in st)
    near_r = min(lat for (s, lat, _d) in st if s < s_max * 0.1)
    far_r = min(lat for (s, lat, _d) in st if s > s_max * 0.9)
    _assert(near_r < far_r - 1.0,
            "the median tapers 6.0 -> 2.0 m, so the backward carriageway should sit FURTHER from "
            "the spine at the start (%.3f) than at the end (%.3f)" % (near_r, far_r))
    print("smoketest_turn_lane_widen: RKA_OT_build_straight_segment builds the same scenario "
          "cleanly end-to-end (no exception, geometry/custom-properties consistent)")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
