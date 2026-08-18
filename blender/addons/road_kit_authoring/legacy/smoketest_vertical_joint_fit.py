#!/usr/bin/env python3
"""
smoketest_vertical_joint_fit.py -- headless verification for the 2026-08 fix (user-reported: after
`RKA_OT_aim_arm_at` ("Match Arm To Selected") matches an arm to a target's XY position + tangent
exactly, "3d vertical level is not aligned, need to manually adjust" -- an intersection pad is
flat (see `intersection_kit.py`'s "all geometry is 2D, one constant world Z" convention), so the
arm has no Z of its own to give; the remaining vertical gap has to be closed by the SEGMENT
instead, once linked via Connect Markers).

Covers `live_edit._bend_near_end_to_angle`'s Z handling: the near end lands EXACTLY on the arm's
Z (as well as X/Y/tangent, already covered elsewhere) while the FAR end (already correctly
connected/graded on its own) is not dragged up or down by even a millimeter -- Z is a LOCAL joint
fit, the same principle as the tangent fix, not a rigid whole-piece vertical shift.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_vertical_joint_fit.py
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


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_w = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "W")

    for o in bpy.data.objects:
        o.select_set(False)
    arm_w.select_set(True)
    context.view_layer.objects.active = arm_w
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="W", length=100.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    pts = spine_io.points(seg_spine)

    # Simulate a genuinely sloped segment (like world_session.blend's real Segment_001, where
    # port_A/port_B differ by ~0.4m in Z): lift the near end (port_A, index 0) up by 0.6m -- an
    # elevation mismatch a flat arm cannot resolve on its own.
    far_before = tuple(pts[-1].co)[:3]
    p0 = pts[0].co
    pts[0].co = (p0[0], p0[1], p0[2] + 0.6, p0[3])
    seg_coll["rka_curve_object"]  # keep the collection reference warm (no-op, clarity only)

    # Manually stamp the link the way RKA_OT_connect_markers does (target=arm, dependent=origin/
    # port_A) -- bypasses the operator's own poll/selection wiring, exercises move_dependent_marker
    # directly, matching this addon's other white-box smoketests' style.
    origin = opint.get_or_create_origin_marker(seg_coll)
    from road_kit_authoring import live_edit as le
    origin[le.RKA_LINKED_TO_KEY] = arm_w.name

    with live_edit.rebuilding():
        live_edit.move_dependent_marker(seg_coll, origin, arm_w)

    seg_coll = opint.local_collection(seg_coll.name)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    pts = spine_io.points(seg_spine)

    # --- near end: X, Y, AND Z all land exactly on the arm.
    p0_after = tuple(pts[0].co)[:3]
    gap3d = math.dist(p0_after, (arm_w.location.x, arm_w.location.y, arm_w.location.z))
    _assert(gap3d < 1e-4,
            "the segment's near end should land EXACTLY on the arm in 3D (X/Y/Z), gap=%.6f"
            % gap3d)
    print("vertical_joint_fit smoketest: near end matched the arm exactly in 3D (gap=%.6fm)"
          % gap3d)

    # --- far end: NOT moved at all, vertically or otherwise -- the actual fix (the old behavior
    # would have carried the far end's Z by the same 0.6m the near end was corrected by).
    far_after = tuple(pts[-1].co)[:3]
    dist_far = math.dist(far_before, far_after)
    _assert(dist_far < 1e-4,
            "THE BUG: the far end (already correctly graded, not itself linked to anything) must "
            "not move AT ALL -- expected %s, got %s (moved %.4fm; the old uniform-Z-carry "
            "behavior would move this by the full 0.6m Z correction)"
            % (far_before, far_after, dist_far))
    print("vertical_joint_fit smoketest: far end did not move at all (%.6fm) while the near end's "
          "elevation was corrected by 0.6m" % dist_far)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
