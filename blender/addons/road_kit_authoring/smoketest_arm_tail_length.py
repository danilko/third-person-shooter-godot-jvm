#!/usr/bin/env python3
"""
smoketest_arm_tail_length.py -- headless verification for the per-arm tail-length fix in
rebuild_intersection_in_place: an arm deliberately snapped to a non-default distance from the
origin (simulating Grab+Ctrl-snapping it onto an external segment's port) must keep EXACTLY that
distance after a rebuild, while every untouched arm stays on the shared tail_length -- the
concrete fix for "a careful snap gets discarded on rebuild".

RUN: blender --background --python addons/road_kit_authoring/smoketest_arm_tail_length.py
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
from road_kit_authoring import custom_props                # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _dist_from_origin(obj, marker):
    return math.hypot(obj.location.x - marker.location.x, obj.location.y - marker.location.y)


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
    coll = result["coll"]
    marker = opint.get_or_create_origin_marker(coll)
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")
    arm_e = next(o for o in coll.objects if o.get("rka_arm_name") == "E")
    arm_s = next(o for o in coll.objects if o.get("rka_arm_name") == "S")
    arm_w = next(o for o in coll.objects if o.get("rka_arm_name") == "W")

    _assert(abs(_dist_from_origin(arm_n, marker) - 12.0) < 1e-4,
            "fresh build: arm N should sit at the default tail_length (12.0), got %.3f"
            % _dist_from_origin(arm_n, marker))
    _assert(abs(arm_n.get("rka_arm_tail_length", -1.0) - 12.0) < 1e-4,
            "fresh build: arm N's rka_arm_tail_length custom prop should be 12.0, got %s"
            % arm_n.get("rka_arm_tail_length"))

    # --- Simulate a Grab+Ctrl-snap that moves arm N to an ARBITRARY new distance (6.5m, shorter
    # than the shared 12.0) WITHOUT changing its angle, then rebuild. Arm N's distance must come
    # out at exactly 6.5 -- NOT reset to 12.0 -- while E/S/W (never touched) must stay at exactly
    # 12.0. Rebuild called directly (matching every other smoketest in this suite) since
    # `bpy.app.timers` doesn't run in `--background` mode.
    new_dist = 6.5
    arm_n.location.x = marker.location.x + new_dist   # angle stays 0 deg (arm N is +X)
    arm_n.location.y = marker.location.y
    context.view_layer.update()

    opint.rebuild_intersection_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    marker = opint.get_or_create_origin_marker(coll)
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")
    arm_e = next(o for o in coll.objects if o.get("rka_arm_name") == "E")
    arm_s = next(o for o in coll.objects if o.get("rka_arm_name") == "S")
    arm_w = next(o for o in coll.objects if o.get("rka_arm_name") == "W")

    n_dist = _dist_from_origin(arm_n, marker)
    _assert(abs(n_dist - new_dist) < 1e-3,
            "arm N's deliberately-snapped distance (%.2f) should survive a rebuild "
            "unchanged, got %.3f (old behavior would force it back to 12.0)" % (new_dist, n_dist))
    _assert(abs(arm_n.get("rka_arm_tail_length", -1.0) - new_dist) < 1e-3,
            "arm N's rka_arm_tail_length custom prop should be updated to %.2f, got %s"
            % (new_dist, arm_n.get("rka_arm_tail_length")))
    for name, obj in (("E", arm_e), ("S", arm_s), ("W", arm_w)):
        d = _dist_from_origin(obj, marker)
        _assert(abs(d - 12.0) < 1e-3,
                "untouched arm %s should stay at the shared tail_length (12.0), got %.3f"
                % (name, d))
    print("arm_tail_length smoketest: arm N kept its manually-snapped distance (%.2f) through "
          "a rebuild; E/S/W stayed at the shared default (12.0)" % n_dist)

    # --- The stored arm_tail_lengths array on the collection must reflect the per-arm values too
    # (mirrors rka_arm_angles -- see custom_props.write_build_settings).
    stored = coll.get("rka_arm_tail_lengths")
    _assert(stored is not None, "rka_arm_tail_lengths should be persisted on the collection")
    arms = custom_props.read_arms(coll)
    by_name = {a[0]: i for i, a in enumerate(arms)}
    _assert(abs(stored[by_name["N"]] - new_dist) < 1e-3,
            "stored arm_tail_lengths[N] should be %.2f, got %.3f" % (new_dist, stored[by_name["N"]]))
    print("arm_tail_length smoketest: rka_arm_tail_lengths persisted correctly on the collection")

    # --- RKA_OT_extend_from_arm must extend from arm N's ACTUAL (snapped) tip, not the shared
    # tail_length -- otherwise a segment built from the just-snapped arm would start at the wrong
    # point, defeating the whole point of snapping it to an external target first.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.extend_from_arm(arm_name="N", length=20.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    new_segs = [c for c in bpy.data.collections if "rka_curve_object" in c.keys()
                and "rka_lanes_a" not in c.keys()]
    _assert(len(new_segs) == 1, "expected exactly one extended segment, got %d" % len(new_segs))
    seg_coll = new_segs[0]
    port_a = next(o for o in seg_coll.objects if o.get("rka_port") == "A")
    expect_x = marker.location.x + new_dist   # arm N points +X, so tip.x = origin.x + new_dist
    _assert(abs(port_a.location.x - expect_x) < 1e-3,
            "extend_from_arm should start exactly at arm N's SNAPPED tip (x=%.2f), got x=%.3f "
            "(old behavior would use the shared tail_length=12.0 instead)"
            % (expect_x, port_a.location.x))
    print("arm_tail_length smoketest: extend_from_arm started from arm N's actual snapped tip "
          "(x=%.2f), not the shared tail_length" % port_a.location.x)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
