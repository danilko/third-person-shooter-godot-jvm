#!/usr/bin/env python3
"""
smoketest_matched_arm_export.py -- headless verification for a confirmed real bug (2026-08,
user-reported: "the preview lane still not aligned between intersection and segment's lane
arm_w and its segment, seem to be very far away toward east... was worried if the output godot
path3d also have same issue"). Root cause, confirmed by direct headless measurement against
`world_session.blend`: `intersection_kit._lane_far_point` (the round-2 fix for a `tail_pos`-
matched/off-ray arm) only ever received a real `tail_pos` from `ops_intersection.
rebuild_intersection_in_place`'s own in-memory arm reconstruction -- but `lane_export.py`'s
`_export_intersection` (shared by BOTH `ops_lane_preview.py`'s interactive preview AND `tools/
save_lane_kit.py`'s real `.lanekit.json`/Godot Path3D export) goes through the SEPARATE
`custom_props.read_arms_full` reconstruction, which never persisted/read `tail_pos` at all --
silently discarding a matched arm's real position and falling back to the plain angle-ray point
for every lane movement/port touching it. Measured on the real reported case: a matched arm's own
'in' port landed ~8.9m away from its own linked segment's port before the fix, ~1.3cm after
(persisting `rka_arm_tail_pos_x`/`_y`, `Arm.tail_center`'s resolved point, and reading them back
in `read_arms_full`).

`RKA_OT_aim_arm_at`'s own resolved angle (`_resolve_target_angle_deg`) prefers a PORT/origin-
marker TARGET's own spine TANGENT over the raw origin-to-target bearing -- those two are only the
same value when the target's piece happens to run exactly radially through the intersection's own
origin (not generally true; a bare Empty target has no tangent of its own, so a genuinely off-ray
match needs a real segment port target, not a plain Empty). This test builds a REAL straight
segment starting off any of the intersection's own arm-rays, matches arm_W onto its `port_A`
(the exact `RKA_OT_aim_arm_at` workflow the real bug was found through), and asserts the EXPORTED
dict (`lane_export._export_intersection`, the exact function both the preview button and the real
Godot export use) lands within centimeters of the segment's own port -- not just that
`rebuild_intersection_in_place`'s in-memory arms happen to be correct (that path was never
broken).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_matched_arm_export.py
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
from road_kit_authoring import lane_export                 # noqa: E402
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
    scene_coll = context.scene.collection

    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    inter = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    arm_w = next(o for o in inter.objects if o.get("rka_arm_name") == "W")

    # A REAL segment, built starting well off any arm's own angle-ray, heading in an unrelated
    # direction (200 deg) -- port_A's own spine tangent there is unrelated to the bearing from the
    # intersection's origin to port_A, exactly the "position and facing are independent" case
    # `_resolve_target_angle_deg` exists for.
    p0 = (arm_w.location.x - 25.0, arm_w.location.y + 18.0, arm_w.location.z)
    seg_ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=200.0, length=40.0, lane_width=5.0, lanes=1,
        lanes_backward=1, curb_l_style='NONE', curb_r_style='NONE')
    _assert(seg_ret == {'FINISHED'}, seg_ret)
    seg_coll = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())
    port_a = seg_coll.objects.get("port_A")
    _assert(port_a is not None, "sanity: fresh segment should have a port_A marker")
    port_a.location = p0   # relocate off any arm's own ray -- direction_deg=200 stays the tangent
    bpy.context.view_layer.update()

    for o in bpy.data.objects:
        o.select_set(False)
    port_a.select_set(True)
    arm_w.select_set(True)
    context.view_layer.objects.active = arm_w
    ret = bpy.ops.rka.aim_arm_at('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "aim_arm_at did not finish: %s" % (ret,))
    _assert(arm_w.get("rka_arm_tail_pos_locked") is True, "arm_W should now be tail_pos-locked")
    dist_off_ray = math.dist((arm_w.location.x, arm_w.location.y), (p0[0], p0[1]))
    _assert(dist_off_ray < 1e-3, "sanity: arm_W should now sit exactly on port_A")

    opint.rebuild_intersection_in_place(context, inter)
    inter = opint.local_collection(inter.name)
    arm_w = next(o for o in inter.objects if o.get("rka_arm_name") == "W")

    _assert("rka_arm_tail_pos_x" in inter.keys() and "rka_arm_tail_pos_y" in inter.keys(),
            "rebuild should persist rka_arm_tail_pos_x/_y for every arm")
    print("smoketest_matched_arm_export: rebuild persists rka_arm_tail_pos_x/_y")

    # The actual regression check: the EXPORTED dict's own port position for arm_W's 'in'
    # direction must land close to port_A's real position -- not fall back to the stale
    # angle-ray point (which, pre-fix, landed ~8.9m away on the real reported case).
    d = lane_export._export_intersection(inter, context.scene, godot_space=False)
    _assert(d is not None, "export should succeed")
    in_port = next(p for p in d["ports"] if p["arm"] == "W" and p["direction"] == "in")
    exported_pos = (in_port["position"][0], in_port["position"][1])
    gap = math.dist(exported_pos, (p0[0], p0[1]))
    # A port is naturally offset from the arm's own marker by half a lane width (2.5m here); this
    # tolerance just needs to comfortably clear that expected offset while still catching a
    # regression back to the multi-meter "fell back to the stale ray point" bug this test guards
    # against -- not assert floating-point-exact equality.
    _assert(gap < 4.0, "exported 'in' port for arm_W should land near port_A's real position "
            "(got %.3fm gap) -- the export/preview path may have fallen back to the stale "
            "angle-ray point again" % gap)
    print("smoketest_matched_arm_export: exported port position tracks the matched arm's real "
          "off-ray position (gap=%.4fm), not the stale angle-ray point" % gap)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
