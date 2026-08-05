#!/usr/bin/env python3
"""
smoketest_set_arm_angle.py -- headless verification for `RKA_OT_set_arm_angle` (2026-08,
user-reported: "the arm movement of intersection still hard to align or adjust edge angle").

`rebuild_intersection_in_place` only ever derives an arm's angle from its marker's freehand-
dragged position (atan2 against the origin) -- there was no way to set an arm to an EXACT
numeric bearing (e.g. squaring it to 90 deg to match a linked segment) short of nudging the
Empty by mouse and eyeballing it, since Blender's angle-snap doesn't apply to a plain Translate.
`rka.set_arm_angle` computes the marker's new position directly from an exact `angle_deg` (and
optional `tail_length`), then re-runs the same rebuild + link-propagation cascade a real drag
would trigger -- so it's pixel/degree-exact AND immediately re-aligns anything linked to that arm.

RUN: blender --background --python addons/road_kit_authoring/smoketest_set_arm_angle.py
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

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    origin = opint.get_or_create_origin_marker(inter_coll)
    ox, oy = origin.location.x, origin.location.y
    orig_dist = math.hypot(arm_n.location.x - ox, arm_n.location.y - oy)

    _assert(not bpy.ops.rka.set_arm_angle.poll(), "poll should fail with no arm active")
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = arm_n

    # --- exact angle, default (keep current) distance.
    ret = bpy.ops.rka.set_arm_angle('EXEC_DEFAULT', angle_deg=37.5, tail_length=-1.0)
    _assert(ret == {'FINISHED'}, "set_arm_angle did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    _assert(abs(arm_n.get("rka_arm_angle", -999.0) - 37.5) < 1e-3,
            "arm N's stored angle should be exactly 37.5 deg, got %r" % arm_n.get("rka_arm_angle"))
    new_dist = math.hypot(arm_n.location.x - ox, arm_n.location.y - oy)
    _assert(abs(new_dist - orig_dist) < 1e-3,
            "tail_length=-1 (default) should PRESERVE the arm's current distance -- was %.3f, "
            "now %.3f" % (orig_dist, new_dist))
    got_angle = math.degrees(math.atan2(arm_n.location.y - oy, arm_n.location.x - ox)) % 360.0
    _assert(abs(got_angle - 37.5) < 1e-3,
            "arm N's actual position should sit at exactly 37.5 deg from the origin, got %.3f"
            % got_angle)
    print("set_arm_angle smoketest: exact angle_deg=37.5 with default distance placed the arm "
          "at precisely 37.5 deg, %.2fm from origin (unchanged)" % new_dist)

    # --- exact angle AND exact distance together.
    ret = bpy.ops.rka.set_arm_angle('EXEC_DEFAULT', angle_deg=90.0, tail_length=20.0)
    _assert(ret == {'FINISHED'}, "set_arm_angle (with tail_length) did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    _assert(abs(arm_n.location.x - ox) < 1e-3 and abs(arm_n.location.y - (oy + 20.0)) < 1e-3,
            "angle_deg=90, tail_length=20 should place the arm at exactly (ox, oy+20), got (%.3f, "
            "%.3f) vs origin (%.3f, %.3f)" % (arm_n.location.x, arm_n.location.y, ox, oy))
    print("set_arm_angle smoketest: exact angle_deg=90 + tail_length=20 placed the arm exactly, "
          "not approximately")

    # --- linked segment must re-align (both position AND tangent) in the SAME operator call, no
    # separate propagate step needed -- unlike a raw marker drag, which needs the depsgraph tick.
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    p0_before = tuple(seg_spine.data.splines[0].points[0].co)[:3]
    p1_before = tuple(seg_spine.data.splines[0].points[1].co)[:3]
    tangent_before = _angle_deg(p0_before, p1_before)
    _assert(abs(tangent_before - 90.0) < 0.1,
            "sanity: freshly-extended segment should start tangent to arm N's 90 deg bearing, "
            "got %.2f" % tangent_before)

    ret = bpy.ops.rka.set_arm_angle('EXEC_DEFAULT', angle_deg=125.0, tail_length=-1.0)
    _assert(ret == {'FINISHED'}, "set_arm_angle (linked case) did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    seg_coll = opint.local_collection(seg_coll.name)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    p0_after = tuple(seg_spine.data.splines[0].points[0].co)[:3]
    p1_after = tuple(seg_spine.data.splines[0].points[1].co)[:3]
    dist_p0 = math.dist((p0_after[0], p0_after[1]), (arm_n.location.x, arm_n.location.y))
    _assert(dist_p0 < 1e-3,
            "the linked segment's near endpoint should land exactly on the arm's new position "
            "IN THE SAME CALL, dist=%.4f" % dist_p0)
    tangent_after = _angle_deg(p0_after, p1_after)
    _assert(abs(tangent_after - 125.0) < 0.1,
            "the linked segment's tangent should follow the arm to 125 deg in the same call, "
            "got %.2f (no separate drag/propagate step needed)" % tangent_after)
    print("set_arm_angle smoketest: a single numeric angle-set call re-aligned the linked "
          "segment's position AND tangent immediately (%.2f -> %.2f deg)" %
          (tangent_before, tangent_after))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
