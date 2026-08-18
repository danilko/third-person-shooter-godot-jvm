#!/usr/bin/env python3
"""
smoketest_dual_end_link.py -- headless verification for the 2026-08 dual-end joint-linking fix
(ROAD_JOINT_TRANSITION_STUDY.md finding #3, user-reported: "the arm movement of intersection
still hard to align... major gap... when moving segment/port in certain direction"). Root cause:
a segment's FAR port could never be a genuine link dependent -- only its start (origin marker) --
so a segment bridging two intersections had ONE end that auto-followed a rigid whole-spine
transform and one end that just sat wherever it was last manually placed, with no way to keep both
ends' position/tangent/width in sync as EITHER intersection changed. Fixed by (1) letting
`port_A`/`port_B` be valid link dependents (`ops_intersection._is_link_dependent_marker`), and (2)
`live_edit.move_dependent_marker` detecting a dual-linked segment and reshaping the WHOLE spine to
match both live targets at once (`_blend_spine_endpoints`) instead of one rigid single-anchor
transform, with width syncing correctly to each end's own `rka_lanes[_backward][_end]` properties
(the coupled fix to `_sync_linked_width`, ROAD_JOINT_TRANSITION_STUDY.md finding #1).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_dual_end_link.py
"""
import bpy
import math
import os
import sys

from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import spine_io      # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
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

    # ================================================================== unit test: the blend math
    spine = kc.road_spine("UnitTestSpine", [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 5.0, 0.0)],
                           scene_coll, radius=5.0)
    start_new = Vector((-5.0, 10.0, 2.0))
    end_new = Vector((30.0, -5.0, -1.0))
    live_edit._blend_spine_endpoints(spine, start_new, end_new)
    p0 = Vector(spine_io.points(spine)[0].co[:3])
    p1 = Vector(spine_io.points(spine)[1].co[:3])
    p2 = Vector(spine_io.points(spine)[2].co[:3])
    _assert((p0 - start_new).length < 1e-6, "blend must land the FIRST point exactly on start_new")
    _assert((p2 - end_new).length < 1e-6, "blend must land the LAST point exactly on end_new")
    _assert(0.0 < (p1 - Vector((10.0, 0.0, 0.0))).length,
            "the interior point should have MOVED (not been left at its old position)")
    delta_start = start_new - Vector((0.0, 0.0, 0.0))
    delta_end = end_new - Vector((20.0, 5.0, 0.0))
    # Arc length fractions on the OLD 2D path: p0->p1 = 10, p1->p2 = hypot(10,5)=11.180..., total ~21.18
    t1 = 10.0 / (10.0 + math.hypot(10.0, 5.0))
    expected_p1 = Vector((10.0, 0.0, 0.0)) + delta_start.lerp(delta_end, t1)
    _assert((p1 - expected_p1).length < 1e-4,
            "interior point should land at the arc-length-blended position, expected %s got %s"
            % (tuple(expected_p1), tuple(p1)))
    print("dual_end_link smoketest: _blend_spine_endpoints pins both ends exactly and blends the "
          "interior point by arc-length fraction")
    bpy.data.objects.remove(spine, do_unlink=True)

    # ============================================================== integration: two intersections
    resultA = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interA = resultA["coll"]
    arm_n_a = next(o for o in interA.objects if o.get("rka_arm_name") == "N")

    resultB = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 200.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    interB = resultB["coll"]
    arm_s_b = next(o for o in interB.objects if o.get("rka_arm_name") == "S")

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n_a.select_set(True)
    context.view_layer.objects.active = arm_n_a
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=180.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not interA and c is not interB)
    port_b = next(o for o in seg_coll.objects if o.get("rka_port") == "B")

    # Link the segment's FAR port to intersection B's arm S -- previously impossible (port_* was
    # never a valid link dependent).
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s_b.select_set(True)
    port_b.select_set(True)
    context.view_layer.objects.active = port_b   # active = dependent, per RKA_OT_connect_markers
    _assert(bpy.ops.rka.connect_markers.poll(), "connect_markers should poll -- port_B is now a "
            "valid dependent, arm_S a valid target")
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers (port_B -> arm_S) did not finish: %s" % (ret,))

    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    p_start = Vector(spine_io.points(spine)[0].co[:3])
    p_end = Vector(spine_io.points(spine)[-1].co[:3])
    _assert((p_start - arm_n_a.location).length < 1e-3,
            "segment start should still match arm N (intersection A)")
    _assert((p_end - arm_s_b.location).length < 1e-3,
            "segment end should now match arm S (intersection B) right after Connect Markers")
    # Width: A's arm N has 1 lane, B's arm S has 2 -- the segment should now be genuinely TAPERED,
    # not have one end's value silently overwrite the other (the coupled fix to finding #1).
    _assert(seg_coll.get("rka_lanes") == 1, "start-side lanes should match arm N's 1 lane, got %r" % seg_coll.get("rka_lanes"))
    _assert(opseg._effective_end_lanes(seg_coll, backward=False) == 2,
            "end-side lanes should match arm S's 2 lanes, got %r"
            % opseg._effective_end_lanes(seg_coll, backward=False))
    print("dual_end_link smoketest: Connect Markers linked the far port to a SECOND intersection "
          "-- both ends' positions AND independent lane counts (1 -> 2) synced correctly")

    # Now move intersection B's arm S (simulating further editing of B) -- the segment's END must
    # follow, while its START (still linked to A, untouched) must NOT move.
    origin_b = opint.get_or_create_origin_marker(interB)
    obx, oby = origin_b.location.x, origin_b.location.y
    new_angle = math.radians(200.0)
    dist = math.hypot(arm_s_b.location.x - obx, arm_s_b.location.y - oby)
    arm_s_b.location.x = obx + dist * math.cos(new_angle)
    arm_s_b.location.y = oby + dist * math.sin(new_angle)
    # Arm angle is now authoritative via rotation_euler.z, not re-derived from position -- see
    # ops_intersection.ensure_arm_angle_migrated.
    arm_s_b.rotation_euler.z = new_angle
    opint.rebuild_intersection_in_place(context, interB)
    arm_s_b = next(o for o in opint.local_collection(interB.name).objects if o.get("rka_arm_name") == "S")

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_s_b.name})

    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    p_start_after = Vector(spine_io.points(spine)[0].co[:3])
    p_end_after = Vector(spine_io.points(spine)[-1].co[:3])
    _assert((p_start_after - arm_n_a.location).length < 1e-3,
            "segment start should be UNCHANGED (still matching arm N) after moving arm S -- "
            "dist=%.4f" % (p_start_after - arm_n_a.location).length)
    _assert((p_end_after - arm_s_b.location).length < 1e-3,
            "segment end should follow arm S's NEW position -- dist=%.4f"
            % (p_end_after - arm_s_b.location).length)
    _assert((p_end_after - p_end).length > 1.0,
            "sanity: arm S actually moved a meaningful distance")
    print("dual_end_link smoketest: moving intersection B's arm afterward correctly re-synced "
          "ONLY the segment's far end -- its near end (linked to A) stayed exactly put")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
