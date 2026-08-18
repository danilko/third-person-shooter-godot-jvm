#!/usr/bin/env python3
"""
smoketest_segment_to_segment_joint.py -- headless verification for the 2026-08 fix (user-reported:
"support segment to segment alignment, at least for the port point (if the segment now has like 6
points, only the last point port is force move to align) for both arm/[segment]"). Root cause:
`move_dependent_marker`'s tangent/Z/width sync (`_bend_near_end_to_angle`, `_sync_linked_width`)
was gated on `"rka_arm_name" in target_obj.keys()` -- linking one segment's port to ANOTHER
segment's port/origin (instead of to an arm) got a rigid position carry but NEVER a tangent match,
regardless of how many interior points either spine had; only the linked endpoint's raw position
moved. Fixed with `_segment_joint_state` (the segment-port counterpart to `_arm_joint_state`) and a
unified `_joint_state` dispatcher used everywhere the arm-only check used to be.

Covers the exact scenario described: the DEPENDENT segment has 6 control points (a real bend, not
a plain straight line) -- `_ensure_bend_room`/`_bend_near_end_to_angle`/`_blend_endpoints_range`
must reshape smoothly from the point right after the joint through the far end, not just force-move
the single port point in isolation (which would leave a sharp kink at the second-to-last point).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_segment_to_segment_joint.py
"""
import bpy
import math
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
from road_kit_authoring import spine_io      # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _tangent_deg(spine, end):
    pts = spine_io.points(spine)
    a, b = (pts[0].co, pts[1].co) if end == "start" else (pts[-2].co, pts[-1].co)
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # --- Segment_A (the TARGET): a plain straight 1-lane extension off intersection A.
    resultA = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interA = resultA["coll"]
    arm_n_a = next(o for o in interA.objects if o.get("rka_arm_name") == "N")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_a.select_set(True)
    context.view_layer.objects.active = arm_n_a
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (A) did not finish: %s" % (ret,))
    seg_a = next(c for c in bpy.data.collections
                 if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys() and c is not interA)
    spine_a = seg_a.objects[seg_a["rka_curve_object"]]

    # --- Segment_B (the DEPENDENT): a BENT, 2-lane extension off a SECOND, unrelated intersection
    # (far away, unrelated angle -- guarantees a real tangent mismatch to correct), with enough
    # curve_segments to have 6+ control points -- the exact "6 points" scenario reported.
    resultB = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 300.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interB = resultB["coll"]
    arm_s_b = next(o for o in interB.objects if o.get("rka_arm_name") == "S")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s_b.select_set(True)
    context.view_layer.objects.active = arm_s_b
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="S", length=60.0, bend=8.0,
                                       curve_segments=6)
    _assert(ret == {'FINISHED'}, "extend_from_arm (B) did not finish: %s" % (ret,))
    seg_b = next(c for c in bpy.data.collections
                 if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                 and c is not interA and c is not interB and c is not seg_a)
    spine_b = seg_b.objects[seg_b["rka_curve_object"]]
    n_pts_before = len(spine_io.points(spine_b))
    _assert(n_pts_before >= 6, "sanity: the bent extension should have >=6 points, got %d"
            % n_pts_before)

    port_b_a = next(o for o in seg_a.objects if o.get("rka_port") == "B")
    origin_b = opint.get_or_create_origin_marker(seg_b)
    tangent_a_before = _tangent_deg(spine_a, "end")
    far_b_before = tuple(spine_io.points(spine_b)[-1].co)[:3]
    origin_b_pos_before = (origin_b.location.x, origin_b.location.y)
    lane_width_a = seg_a.get("rka_lane_width")
    lanes_end_a = seg_a.get("rka_lanes_end", seg_a.get("rka_lanes"))
    lanes_bwd_end_a = seg_a.get("rka_lanes_backward_end", seg_a.get("rka_lanes_backward"))

    # --- link: select the TARGET (Segment_A's port_B) first, Shift-click the DEPENDENT
    # (Segment_B's origin/port_A) last -- same convention as everywhere else in this addon.
    for o in bpy.data.objects:
        o.select_set(False)
    port_b_a.select_set(True)
    origin_b.select_set(True)
    context.view_layer.objects.active = origin_b
    _assert(bpy.ops.rka.connect_markers.poll(), "connect_markers should poll (segment -> segment)")
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (segment -> segment) did not finish: %s" % (ret,))

    seg_a = opint.local_collection(seg_a.name)
    spine_a = seg_a.objects[seg_a["rka_curve_object"]]
    seg_b = opint.local_collection(seg_b.name)
    spine_b = seg_b.objects[seg_b["rka_curve_object"]]
    port_b_a = next(o for o in seg_a.objects if o.get("rka_port") == "B")
    pts_b = spine_io.points(spine_b)

    # --- point count unchanged (6+ points already had room to bend -- no bend-point insertion
    # needed, unlike the plain-2-point case covered elsewhere).
    _assert(len(pts_b) == n_pts_before,
            "a spine that already has interior points should keep its point count -- had %d, now %d"
            % (n_pts_before, len(pts_b)))

    # --- near end: position AND tangent both exact, matching Segment_A's OWN tangent at port_B
    # (not just the raw bearing to its position).
    p0 = tuple(pts_b[0].co)[:3]
    gap3d = math.dist(p0, tuple(port_b_a.location))
    _assert(gap3d < 1e-4, "Segment_B's near end should land EXACTLY on Segment_A's port_B, "
                           "gap=%.6f" % gap3d)
    tangent_b_after = _tangent_deg(spine_b, "start")
    diff = abs((tangent_b_after - tangent_a_before + 180.0) % 360.0 - 180.0)
    _assert(diff < 0.05,
            "Segment_B's near-end tangent should EXACTLY match Segment_A's own tangent at port_B "
            "(%.2f deg), got %.2f (diff %.4f)" % (tangent_a_before, tangent_b_after, diff))
    print("segment_to_segment smoketest: a 6-point segment's near end matched another segment's "
          "port position (gap=%.6fm) AND its real tangent (%.2f deg) exactly" %
          (gap3d, tangent_b_after))

    # --- far end (Segment_B's OWN port_B, not itself linked to anything): moved by EXACTLY the
    # plain HORIZONTAL translate-carry (the two source intersections are ~300m apart, so the near
    # end's own relocation is large and legitimately carries the whole piece in X/Y -- see
    # move_dependent_marker's docstring) -- but NOT vertically, and no extra tangent-driven swing.
    far_b_after = tuple(pts_b[-1].co)[:3]
    carry_xy = (port_b_a.location.x - origin_b_pos_before[0],
                port_b_a.location.y - origin_b_pos_before[1])
    expected_far = (far_b_before[0] + carry_xy[0], far_b_before[1] + carry_xy[1], far_b_before[2])
    dist_far = math.dist(expected_far, far_b_after)
    _assert(dist_far < 1e-4,
            "Segment_B's far end should move by EXACTLY the plain horizontal translate-carry and "
            "no more (no extra tangent swing, no vertical shift) -- expected %s, got %s (off by "
            "%.4fm)" % (expected_far, far_b_after, dist_far))
    print("segment_to_segment smoketest: Segment_B's far end moved by EXACTLY the horizontal "
          "translate-carry (%.6fm off) -- no extra tangent swing, no vertical shift" % dist_far)

    # --- width/lane sync: Segment_B's linked (start) end now matches Segment_A's END-side values,
    # not just carried its own old (2-lane) config.
    _assert(seg_b.get("rka_lane_width") == lane_width_a,
            "Segment_B's lane_width should sync to Segment_A's, got %r want %r"
            % (seg_b.get("rka_lane_width"), lane_width_a))
    _assert(seg_b.get("rka_lanes") == lanes_end_a,
            "Segment_B's rka_lanes should sync to Segment_A's END-side lane count, got %r want %r"
            % (seg_b.get("rka_lanes"), lanes_end_a))
    _assert(seg_b.get("rka_lanes_backward") == lanes_bwd_end_a,
            "Segment_B's rka_lanes_backward should sync to Segment_A's END-side backward count, "
            "got %r want %r" % (seg_b.get("rka_lanes_backward"), lanes_bwd_end_a))
    print("segment_to_segment smoketest: width/lane-count synced from Segment_A's own end-side "
          "values (lane_width=%r, lanes=%r/%r)" % (lane_width_a, lanes_end_a, lanes_bwd_end_a))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
