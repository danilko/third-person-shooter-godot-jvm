#!/usr/bin/env python3
"""
smoketest_connect_markers_tangent.py -- headless verification for the 2026-08 fix confirmed
directly against world_session.blend (user-reported: "move arm w to left of intersection, will
case the edge of arm w to start to rotate clockwise like pull by center... major gap... adjust
the pad may work temporary, but when move arm/intersection, that strange angle is back again").

Root cause: `live_edit.move_dependent_marker`'s joint rotation used to be tracked INCREMENTALLY
(`rka_joint_last_angle`, only the delta since the last call) -- `RKA_OT_connect_markers`'s
one-time initial snap syncs POSITION but, on that very first call, has no previous angle to diff
against yet, so applied NO rotation at all. Any tangent mismatch that already existed at connect
time (the common case: `Connect Markers` links two INDEPENDENTLY built pieces, which have no
reason to already share a tangent) was baked in FOREVER -- every later arm drag only ever
corrected the CHANGE from that already-wrong baseline, never the original error. Confirmed live in
world_session.blend: a linked segment sat exactly on its arm (0.0000m position gap) with a
permanent ~12deg tangent mismatch no amount of further dragging ever closed.

Fixed by measuring the spine's actual current tangent directly (`live_edit._spine_tangent_angle`)
and rotating by however much it ACTUALLY differs from the target's angle every single call --
self-correcting, no baseline bookkeeping to go stale.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_connect_markers_tangent.py
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

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_w = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "W")
    arm_angle = arm_w.get("rka_arm_angle", 0.0)

    # Build a segment COMPLETELY INDEPENDENTLY, at an angle that does NOT match arm W at all --
    # exactly the "two independently-built pieces, no shared tangent" case Connect Markers exists
    # for. Positioned so it happens to sit at arm W's location but pointing the wrong way.
    wrong_angle_deg = (arm_angle + 47.0) % 360.0
    rad = math.radians(wrong_angle_deg)
    p0 = (arm_w.location.x, arm_w.location.y, arm_w.location.z)
    p1 = (p0[0] + 40.0 * math.cos(rad), p0[1] + 40.0 * math.sin(rad), p0[2])
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [p0, p1], lane_width=5.0, lanes=1, lanes_backward=1,
        curb_l_style='BOX', curb_r_style='BOX', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    seg_coll = seg_result["coll"]
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    origin = opint.get_or_create_origin_marker(seg_coll)

    tangent_before = math.degrees(live_edit._spine_tangent_angle(spine, "start")) % 360.0
    diff0 = abs((tangent_before - wrong_angle_deg + 180.0) % 360.0 - 180.0)
    _assert(diff0 < 0.1,
            "sanity: the independently-built segment's tangent should start at the WRONG angle "
            "(%.1f), got %.2f" % (wrong_angle_deg, tangent_before))

    # Connect Markers: link the segment's origin to arm W.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_w.select_set(True)
    origin.select_set(True)
    context.view_layer.objects.active = origin   # active = dependent
    _assert(bpy.ops.rka.connect_markers.poll(), "connect_markers should poll")
    ret = bpy.ops.rka.connect_markers('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "connect_markers did not finish: %s" % (ret,))

    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    origin = opint.get_or_create_origin_marker(seg_coll)
    dist_gap = (origin.location - arm_w.location).length
    _assert(dist_gap < 1e-4, "position should be synced exactly on connect, gap=%.6f" % dist_gap)

    tangent_after = live_edit._spine_tangent_angle(spine, "start")
    tangent_after_deg = math.degrees(tangent_after) % 360.0
    diff = abs((tangent_after_deg - arm_angle + 180.0) % 360.0 - 180.0)
    _assert(diff < 0.1,
            "THE BUG: Connect Markers must rotate the segment's tangent to match arm W's angle "
            "on the VERY FIRST connect, not just its position -- arm angle=%.2f, segment tangent "
            "after connect=%.2f (diff=%.2f deg) -- this is the exact world_session.blend mismatch "
            "(there it was ~12 deg and never self-corrected)" % (arm_angle, tangent_after_deg, diff))
    print("connect_markers_tangent smoketest: Connect Markers now rotates the segment's tangent "
          "to match the target arm's angle on the FIRST connect (position AND tangent both "
          "exact), not just position -- was %.1f deg off before connecting, now %.4f deg off"
          % (wrong_angle_deg - arm_angle, diff))

    # Move arm W again afterward -- the fix must still track correctly on SUBSEQUENT moves too
    # (not just the first one), with no reliance on any seeded baseline.
    origin_inter = opint.get_or_create_origin_marker(inter_coll)
    ox, oy = origin_inter.location.x, origin_inter.location.y
    dist = math.hypot(arm_w.location.x - ox, arm_w.location.y - oy)
    new_angle_deg = (arm_angle + 25.0) % 360.0
    rad2 = math.radians(new_angle_deg)
    arm_w.location.x = ox + dist * math.cos(rad2)
    arm_w.location.y = oy + dist * math.sin(rad2)
    # Arm angle is now authoritative via rotation_euler.z, not re-derived from position -- see
    # ops_intersection.ensure_arm_angle_migrated.
    arm_w.rotation_euler.z = rad2
    opint.rebuild_intersection_in_place(context, inter_coll)
    arm_w = next(o for o in opint.local_collection(inter_coll.name).objects
                 if o.get("rka_arm_name") == "W")

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_w.name})

    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    tangent_final = math.degrees(live_edit._spine_tangent_angle(spine, "start")) % 360.0
    diff2 = abs((tangent_final - new_angle_deg + 180.0) % 360.0 - 180.0)
    _assert(diff2 < 0.1,
            "after a SECOND arm move, tangent should still track exactly -- arm=%.2f, spine=%.2f "
            "(diff=%.2f)" % (new_angle_deg, tangent_final, diff2))
    print("connect_markers_tangent smoketest: a subsequent arm move also tracked exactly "
          "(%.2f deg)" % tangent_final)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
