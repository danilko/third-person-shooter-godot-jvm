#!/usr/bin/env python3
"""
smoketest_joint_sync.py -- headless verification for the 2026-08 joint-unification fix: an
arm-linked segment's endpoint now tracks the arm's DIRECTION and WIDTH, not just its position
(`live_edit.move_dependent_marker`/`_arm_joint_state`/`_sync_linked_width`), and a `port_*`
marker is now a genuine drag handle for its own spine's endpoint instead of an inert, silently
re-snapped output (`live_edit._flush_port_drags`).

Before this fix: rotating a linked arm left the linked segment's near end at the right POSITION
but the wrong TANGENT (a kink at the joint -- the visible "curve rotated ~60 deg" symptom, since
every spine is a POLY curve with no tangent continuity), and the two sides' pavement/curb WIDTH
were two independently-stored numbers that could silently disagree even with a perfectly matched
position. Dragging a `port_*` marker did nothing at all (by original design -- see
`ops_segment._place_segment_ports`'s docstring).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_joint_sync.py
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
from road_kit_authoring import spine_io      # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import live_edit                   # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _angle_deg(p0, p1):
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.0


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ------------------------------------------------------------------ intersection --(Extend
    # From Arm)--> segment1, exactly like smoketest_link_propagation.py's first hop.
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
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg1_coll = next(c for c in bpy.data.collections
                      if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                      and c is not inter_coll)
    seg1_spine = bpy.data.objects.get(seg1_coll.get("rka_curve_object"))

    # -------------------------------------------------------------------------------- DIRECTION
    # Arm N starts at 90 deg (angle_start=0, side_angle=90 in build_intersection_geometry above
    # puts arms at 0/90/180/270) -- confirm the freshly-extended segment's own tangent already
    # matches that, then ROTATE the arm to a new angle (simulating the user dragging it) and
    # confirm the tangent follows instead of leaving a kink.
    p0_before = tuple(spine_io.points(seg1_spine)[0].co)[:3]
    p1_before = tuple(spine_io.points(seg1_spine)[1].co)[:3]
    tangent_before = _angle_deg(p0_before, p1_before)
    # preset_4way's default names=("N","E","S","W") zip onto angles=(0,90,180,270) IN ORDER, so
    # arm 'N' actually starts at 0 deg (a naming/compass mismatch elsewhere in the addon, not
    # something this test needs to fix) -- confirm THAT, whatever it is, matches the fresh segment.
    build_angle = arm_n.get("rka_arm_angle", 0.0)
    _assert(abs(tangent_before - build_angle) < 0.1,
            "sanity: freshly-extended segment's tangent should match arm N's build angle (%.2f "
            "deg), got %.2f" % (build_angle, tangent_before))

    origin = opint.get_or_create_origin_marker(inter_coll)
    ox, oy = origin.location.x, origin.location.y
    new_angle_deg = build_angle + 35.0   # rotate arm N -- position AND tangent must both follow
    dist = math.hypot(arm_n.location.x - ox, arm_n.location.y - oy)
    rad = math.radians(new_angle_deg)
    arm_n.location.x = ox + dist * math.cos(rad)
    arm_n.location.y = oy + dist * math.sin(rad)
    # Arm angle is now authoritative via rotation_euler.z, not re-derived from position (see
    # ops_intersection.ensure_arm_angle_migrated) -- a real Rotate (R key) or RKA_OT_set_arm_angle
    # sets both; simulate that here too, or this would just be a plain (angle-preserving) drag.
    arm_n.rotation_euler.z = rad
    opint.rebuild_intersection_in_place(context, inter_coll)
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_n.name})

    seg1_coll = opint.local_collection(seg1_coll.name)
    seg1_spine = bpy.data.objects.get(seg1_coll.get("rka_curve_object"))
    p0_after = tuple(spine_io.points(seg1_spine)[0].co)[:3]
    p1_after = tuple(spine_io.points(seg1_spine)[1].co)[:3]
    dist_p0 = math.dist((p0_after[0], p0_after[1]), (arm_n.location.x, arm_n.location.y))
    _assert(dist_p0 < 1e-3,
            "segment1's spine start point should still land exactly on the rotated arm, dist=%.4f"
            % dist_p0)
    tangent_after = _angle_deg(p0_after, p1_after)
    _assert(abs(tangent_after - new_angle_deg) < 0.1,
            "segment1's spine TANGENT should track the arm's new angle (%.1f deg) with no kink -- "
            "got %.2f deg (this is the gap/overlap/rotated-sweep bug if it fails)"
            % (new_angle_deg, tangent_after))
    print("joint_sync smoketest: position AND tangent direction both followed the rotated arm "
          "(tangent %.2f -> %.2f deg, target %.2f)" % (tangent_before, tangent_after, new_angle_deg))

    # ----------------------------------------------------------------------------------- WIDTH
    # Widen arm N from 2 to 3 lanes via the button path (bypasses the depsgraph handler entirely
    # -- RKA_OT_adjust_arm_lanes must itself cascade the sync, see _propagate_from_arm).
    lane_width_before = seg1_coll.get("rka_lane_width")
    lanes_before = seg1_coll.get("rka_lanes")
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.adjust_arm_lanes('EXEC_DEFAULT', delta=1)
    _assert(ret == {'FINISHED'}, "adjust_arm_lanes did not finish: %s" % (ret,))
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    _assert(int(arm_n.get("rka_arm_lanes")) == 3, "sanity: arm N should now have 3 lanes")

    seg1_coll = opint.local_collection(seg1_coll.name)
    _assert(seg1_coll.get("rka_lanes") == 3,
            "segment1's rka_lanes should follow the widened arm (button path, no drag) -- "
            "was %r, now %r" % (lanes_before, seg1_coll.get("rka_lanes")))
    _assert(seg1_coll.get("rka_lane_width") == lane_width_before,
            "segment1's rka_lane_width should still match the intersection's shared lane width")
    seg1_spine = bpy.data.objects.get(seg1_coll.get("rka_curve_object"))
    expected_half_w = max(3, seg1_coll.get("rka_lanes_backward", 3), 1) * lane_width_before
    joint_pt = next(p for p in spine_io.points(seg1_spine)
                     if math.dist((p.co[0], p.co[1]), (arm_n.location.x, arm_n.location.y)) < 1e-3)
    _assert(abs(joint_pt.radius - expected_half_w) < 1e-3,
            "segment1's spine RADIUS at the joint (the actual pavement half-width) should match "
            "the widened arm immediately -- expected %.3f, got %.3f" % (expected_half_w, joint_pt.radius))
    print("joint_sync smoketest: widening the arm via a BUTTON (no drag) propagated width/lanes "
          "to the linked segment, including the spine's own radius at the joint")

    # ------------------------------------------------------------------------------- PORT DRAG
    # port_B is segment1's FAR, unlinked end -- dragging it should now reshape the spine directly
    # instead of being silently re-snapped back and having no effect.
    port_b = next(o for o in seg1_coll.objects if o.get("rka_port") == "B")
    old_b = (port_b.location.x, port_b.location.y, port_b.location.z)
    port_b.location.x += 6.0
    port_b.location.y -= 4.0
    new_b = (port_b.location.x, port_b.location.y, port_b.location.z)

    curve_colls, transition_colls = live_edit._flush_port_drags({port_b.name})
    _assert(seg1_coll.name in curve_colls,
            "dragging port_B should flag its owning segment for a GN rebuild")
    seg1_spine = bpy.data.objects.get(seg1_coll.get("rka_curve_object"))
    last_pt = spine_io.points(seg1_spine)[-1]
    dist_last = math.dist((last_pt.co[0], last_pt.co[1], last_pt.co[2]), new_b)
    _assert(dist_last < 1e-6,
            "dragging port_B should move the spine's LAST control point to match -- "
            "old=%s new=%s got=%s" % (old_b, new_b, tuple(last_pt.co)[:3]))
    print("joint_sync smoketest: dragging port_B reshaped its own spine's endpoint (was inert "
          "before this fix)")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
