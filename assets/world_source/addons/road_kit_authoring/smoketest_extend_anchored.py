#!/usr/bin/env python3
"""
smoketest_extend_anchored.py -- headless verification for anchored RKA_OT_build_intersection/
RKA_OT_build_lane_transition: selecting an arm_* or port_* marker and running either build
operator must produce a new piece that lands EXACTLY on the source's tip with matching
orientation/lane counts -- no manual rotation/lane dialing, no gap to bridge with a separate
connecting segment.

Blender's `--background` mode has no window manager, so `bpy.ops.rka.*('INVOKE_DEFAULT')` never
actually calls the operator's `invoke()` (confirmed empirically -- it silently falls straight to
`execute()` with the properties' plain defaults, same as `EXEC_DEFAULT`). `invoke()` is where the
Rotation/Direction/lane-count auto-fill lives (see ops_intersection.RKA_OT_build_intersection.
invoke / ops_segment.RKA_OT_build_lane_transition.invoke), so this test computes the SAME values
`arm_or_port_anchor()` would hand to `invoke()` and passes them explicitly via 'EXEC_DEFAULT' --
this still exercises the real, shared logic (`arm_or_port_anchor` itself, plus `execute()`'s
anchored origin-offset math, which runs unconditionally and is NOT invoke()-gated), just supplies
the two invoke()-only prefill values by hand since headless testing cannot exercise interactive
operator invocation.

RUN: blender --background --python addons/road_kit_authoring/smoketest_extend_anchored.py
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
from road_kit_authoring import custom_props                # noqa: E402
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

    # ===================================================================== anchored from an ARM
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    src_coll = result["coll"]
    arm_n = next(o for o in src_coll.objects if o.get("rka_arm_name") == "N")
    src_tip = (arm_n.location.x, arm_n.location.y)   # arm N: angle 0 deg, tip = origin + (12,0)

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n

    # What RKA_OT_build_intersection.invoke() would compute from this same active marker.
    anchor = opint.arm_or_port_anchor(context)
    _assert(anchor is not None, "arm_or_port_anchor should resolve the active arm_* marker")
    _, _, heading_deg, lanes_forward, _, _ = anchor
    _assert(abs(heading_deg - 0.0) < 1e-3, "arm N should report heading 0 deg, got %.2f" % heading_deg)
    _assert(lanes_forward == 2, "arm N (built with lanes=2) should report lanes_forward=2, got %d" % lanes_forward)
    rotation_deg = (heading_deg + 180.0) % 360.0

    before_colls = set(bpy.data.collections.keys())
    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', rotation_deg=rotation_deg, lanes_arm1=lanes_forward, tail_length=12.0)
    _assert(ret == {'FINISHED'}, "anchored build_intersection (from arm) did not finish: %s" % (ret,))
    new_coll = next(c for c in bpy.data.collections
                     if c.name not in before_colls and "rka_arm_names" in c.keys())

    new_arms = custom_props.read_arms(new_coll)
    # rotation_deg = heading(0) + 180 = 180 -- the first preset arm ('N', raw angle 0) ends up
    # facing back at the source, i.e. at 180 deg.
    back_arm = next((a for a in new_arms if abs(a[1] - 180.0) < 1e-3), None)
    _assert(back_arm is not None,
            "anchored build_intersection should orient one arm to face back at the source (180 "
            "deg), got angles=%s" % [a[1] for a in new_arms])
    _assert(back_arm[2] == 2,
            "the back-facing arm should inherit the source arm's lane count (2), got %d"
            % back_arm[2])
    back_arm_obj = next(o for o in new_coll.objects if o.get("rka_arm_name") == back_arm[0])
    tip = (back_arm_obj.location.x, back_arm_obj.location.y)
    dist = math.hypot(tip[0] - src_tip[0], tip[1] - src_tip[1])
    _assert(dist < 1e-3,
            "the new intersection's back-facing arm tip should land EXACTLY on the source arm's "
            "tip %s, got %s (dist=%.4f) -- no gap, no stub segment needed" % (src_tip, tip, dist))
    print("extend_anchored smoketest: build_intersection anchored from an arm landed its "
          "back-facing arm (lanes=%d) exactly on the source tip %s (dist=%.6f)"
          % (back_arm[2], src_tip, dist))

    # ===================================================================== anchored from a PORT
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(100.0, 0.0, 0.0), (140.0, 0.0, 0.0)], 5.0, 3, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    port_b = next(o for o in seg_coll.objects if o.get("rka_port") == "B")
    port_pos = (port_b.location.x, port_b.location.y)

    for o in bpy.data.objects:
        o.select_set(False)
    port_b.select_set(True)
    context.view_layer.objects.active = port_b

    anchor2 = opint.arm_or_port_anchor(context)
    _assert(anchor2 is not None, "arm_or_port_anchor should resolve the active port_* marker")
    _, _, port_heading, port_lanes_fwd, port_lanes_bwd, _ = anchor2
    _assert(abs(port_heading - 0.0) < 1e-3, "port_B should face outward at 0 deg, got %.2f" % port_heading)
    _assert(port_lanes_fwd == 3 and port_lanes_bwd == 1,
            "port_B should report the segment's own forward/backward lanes (3/1), got %d/%d"
            % (port_lanes_fwd, port_lanes_bwd))

    before_colls2 = set(bpy.data.collections.keys())
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=port_heading, lanes_a=port_lanes_fwd,
        lanes_backward_a=port_lanes_bwd)
    _assert(ret == {'FINISHED'}, "anchored build_lane_transition (from port) did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections
                    if c.name not in before_colls2 and "rka_lanes_a" in c.keys())
    tr_spine = bpy.data.objects.get(tr_coll.get("rka_curve_object"))
    _assert(tr_spine is not None, "anchored lane transition should have a spine object")
    p0 = tr_spine.data.splines[0].points[0].co
    dist2 = math.hypot(p0[0] - port_pos[0], p0[1] - port_pos[1])
    _assert(dist2 < 1e-3,
            "anchored build_lane_transition should start EXACTLY at the source port's position "
            "%s, got (%.3f, %.3f) (dist=%.4f)" % (port_pos, p0[0], p0[1], dist2))
    _assert(tr_coll.get("rka_lanes_a") == 3,
            "anchored build_lane_transition should inherit the source segment's forward lane "
            "count (3) into Lanes A, got %s" % tr_coll.get("rka_lanes_a"))
    print("extend_anchored smoketest: build_lane_transition anchored from a port started exactly "
          "at the source port %s (dist=%.6f) with matching Lanes A (3)" % (port_pos, dist2))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
