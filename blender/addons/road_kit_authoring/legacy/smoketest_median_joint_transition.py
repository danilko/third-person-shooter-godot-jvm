#!/usr/bin/env python3
"""
smoketest_median_joint_transition.py -- headless verification for the 2026-08 fix (user-reported:
"add a transition logic segment that allow[s] [the] median from [a] high number to [a] low number
act like [a] transition"). `intersection_kit.build_segment_from_spine`'s tapered path already
supports `median_width` != `median_width_end` (Option B, ROAD_JOINT_TRANSITION_STUDY.md finding
#2) -- no new piece type was needed. What was actually missing: `live_edit.move_dependent_marker`'s
joint sync (`_arm_joint_state`/`_segment_joint_state`/`_sync_linked_width`) never read or wrote
median width at all, so a segment's median stayed whatever it was independently authored as even
when linked to a joint with a very different one -- fixed by threading `median_width` through the
same `(angle, lane_width, lanes_forward, lanes_backward, median_width)` tuple already used for
tangent/lane sync.

Covers both directions:
  1. Linking to an ARM (which has no median concept -- always 0): a wide-median segment's linked
     end tapers DOWN to 0 at the joint, the far end's median is untouched -- "high to low".
  2. Linking to ANOTHER SEGMENT with a wider median: the dependent's linked end picks up the
     target's median width -- "low to high", and the two together read as one continuous taper.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_median_joint_transition.py
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
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import live_edit                   # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ============================================================== 1) arm link: high -> 0 (low)
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0, median_width=8.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    _assert(seg_coll.get("rka_median_width") == 8.0, "sanity: fresh segment should have an 8m "
                                                       "median at its start (the arm end)")

    # Simulate the far end (port_B) having its OWN, independently-authored median already -- a
    # segment can have any median at each end (already-shipped tapering), so far-end median must
    # be untouched by a NEAR-end joint sync, exactly like far-end position/tangent/Z already are.
    seg_coll["rka_median_width_end"] = 3.0

    port_a = next(o for o in seg_coll.objects if o.get("rka_port") == "A")
    origin = opint.get_or_create_origin_marker(seg_coll)
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    port_a.select_set(True)
    context.view_layer.objects.active = port_a
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (segment -> arm) did not finish: %s" % (ret,))

    seg_coll = opint.local_collection(seg_coll.name)
    _assert(seg_coll.get("rka_median_width") == 0.0,
            "linking to an ARM (no median concept) should taper the linked (start) end's median "
            "DOWN to 0 -- 'high to low' -- got %r" % seg_coll.get("rka_median_width"))
    _assert(seg_coll.get("rka_median_width_end") == 3.0,
            "the FAR end's independently-authored median must be untouched by the near-end sync "
            "-- got %r, want 3.0" % seg_coll.get("rka_median_width_end"))
    print("median_joint_transition smoketest: linking to an arm tapered the median from 8m down "
          "to 0 at the joint ('high to low'), leaving the far end's own 3m median untouched")

    # ============================================================== 2) segment link: low -> high
    resultA = opint.build_intersection_geometry(
        context, scene_coll, (500.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interA = resultA["coll"]
    arm_n_a = next(o for o in interA.objects if o.get("rka_arm_name") == "N")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_a.select_set(True)
    context.view_layer.objects.active = arm_n_a
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0, median_width=2.0,
                                       median_width_end=10.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (A) did not finish: %s" % (ret,))
    seg_a = next(c for c in bpy.data.collections
                 if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                 and c is not interA and c is not inter_coll and c is not seg_coll)
    _assert(seg_a.get("rka_median_width_end") == 10.0, "sanity: Segment_A's own end should be a "
                                                         "10m median")

    resultB = opint.build_intersection_geometry(
        context, scene_coll, (500.0, 300.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interB = resultB["coll"]
    arm_s_b = next(o for o in interB.objects if o.get("rka_arm_name") == "S")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s_b.select_set(True)
    context.view_layer.objects.active = arm_s_b
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="S", length=40.0, median_width=1.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (B) did not finish: %s" % (ret,))
    seg_b = next(c for c in bpy.data.collections
                 if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                 and c is not interA and c is not interB and c is not seg_a
                 and c is not inter_coll and c is not seg_coll)
    _assert(seg_b.get("rka_median_width") == 1.0, "sanity: Segment_B starts with a 1m median")

    port_b_a = next(o for o in seg_a.objects if o.get("rka_port") == "B")
    origin_b = opint.get_or_create_origin_marker(seg_b)
    for o in bpy.data.objects:
        o.select_set(False)
    port_b_a.select_set(True)
    origin_b.select_set(True)
    context.view_layer.objects.active = origin_b
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (segment -> segment) did not finish: %s" % (ret,))

    seg_b = opint.local_collection(seg_b.name)
    _assert(seg_b.get("rka_median_width") == 10.0,
            "Segment_B's linked (start) end should pick up Segment_A's END-side 10m median -- "
            "'low to high' -- got %r" % seg_b.get("rka_median_width"))
    print("median_joint_transition smoketest: linking Segment_B to Segment_A's 10m-median port "
          "widened Segment_B's own median from 1m to 10m at the joint ('low to high')")

    # ============================================== 3) an ARM can carry its OWN median (per-way)
    resultC = opint.build_intersection_geometry(
        context, scene_coll, (1000.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interC = resultC["coll"]
    arm_n_c = next(o for o in interC.objects if o.get("rka_arm_name") == "N")
    arm_e_c = next(o for o in interC.objects if o.get("rka_arm_name") == "E")
    _assert(arm_n_c.get("rka_arm_median_width", 0.0) == 0.0,
            "sanity: a fresh arm should have no median by default")

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_c.select_set(True)
    context.view_layer.objects.active = arm_n_c
    _assert(bpy.ops.rka.adjust_arm_median_width.poll(), "adjust_arm_median_width should poll")
    ret = bpy.ops.rka.adjust_arm_median_width('EXEC_DEFAULT', delta=6.0)
    _assert(ret == {'FINISHED'}, "adjust_arm_median_width did not finish: %s" % (ret,))
    interC = opint.local_collection(interC.name)
    arm_n_c = next(o for o in interC.objects if o.get("rka_arm_name") == "N")
    arm_e_c = next(o for o in interC.objects if o.get("rka_arm_name") == "E")
    _assert(arm_n_c.get("rka_arm_median_width") == 6.0, "arm N's own median should now be 6m")
    _assert(arm_e_c.get("rka_arm_median_width", 0.0) == 0.0,
            "PER-ARM: arm E (untouched) must still have NO median -- one arm's own value must "
            "not leak onto its neighbors")
    print("median_joint_transition smoketest: arm N carries its own 6m median while arm E (an "
          "untouched neighbor on the SAME intersection) still has none -- confirmed per-arm")

    # A segment linked to arm N (via the LIVE joint sync, not just a fresh build) should now
    # taper against arm N's REAL 6m median instead of the flat 0 an untouched arm gives.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_c.select_set(True)
    context.view_layer.objects.active = arm_n_c
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (arm with its own median) did not finish: %s"
            % (ret,))
    seg_c = next(c for c in bpy.data.collections
                 if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                 and c not in (interA, interB, interC, seg_a, seg_b, inter_coll, seg_coll))
    _assert(seg_c.get("rka_median_width", 0.0) == 0.0,
            "sanity: a fresh extend_from_arm defaults its OWN median to 0 regardless of the "
            "arm's -- only the LIVE joint sync (Connect Markers) picks up the arm's real value, "
            "verified next")
    port_a_c = next(o for o in seg_c.objects if o.get("rka_port") == "A")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_c.select_set(True)
    port_a_c.select_set(True)
    context.view_layer.objects.active = port_a_c
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (segment -> arm-with-median) did not finish: %s"
            % (ret,))
    seg_c = opint.local_collection(seg_c.name)
    _assert(seg_c.get("rka_median_width") == 6.0,
            "linking to arm N should taper the segment's median UP to arm N's real 6m value "
            "(not a flat 0) -- got %r" % seg_c.get("rka_median_width"))
    print("median_joint_transition smoketest: linking a segment to arm N's own 6m-median approach "
          "tapered the segment's median to 6m via the live joint sync")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
