#!/usr/bin/env python3
"""
smoketest_median_adjust.py -- headless verification for `RKA_OT_adjust_median_width` (2026-08):
median width ("mid lane separation") was previously build-time-only with no way to change it
after the fact short of hand-editing `rka_median_width` in Custom Properties and manually
rebuilding. Confirms the button updates the stored value, refreshes the spine's own pavement
Radius immediately (the same "don't let the sweep silently keep the old width" fix
`RKA_OT_adjust_segment_lanes` already needed), and refuses to go negative.

RUN: blender --background --python addons/road_kit_authoring/smoketest_median_adjust.py
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
from road_kit_authoring import ops_segment as opseg        # noqa: E402
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

    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], lane_width=5.0, lanes=2,
        lanes_backward=2, curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll = result["coll"]
    _assert(coll.get("rka_median_width", 0.0) == 0.0, "sanity: fresh segment has no median")
    spine = bpy.data.objects.get(coll["rka_curve_object"])
    r0 = spine.data.splines[0].points[0].radius
    _assert(abs(r0 - 2 * 5.0) < 1e-6, "sanity: no-median half-width should be lanes*lane_width, "
                                       "got %.3f" % r0)

    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = spine

    ret = bpy.ops.rka.adjust_median_width(delta=3.0)
    _assert(ret == {'FINISHED'}, "adjust_median_width did not finish: %s" % (ret,))
    coll = bpy.data.collections.get(coll.name)
    _assert(abs(coll.get("rka_median_width", -1.0) - 3.0) < 1e-6,
            "rka_median_width should now be 3.0, got %r" % coll.get("rka_median_width"))
    spine = bpy.data.objects.get(coll["rka_curve_object"])
    r1 = spine.data.splines[0].points[0].radius
    expected = 3.0 / 2.0 + 2 * 5.0   # median_half + max(lanes,lanes_backward)*lane_width
    _assert(abs(r1 - expected) < 1e-6,
            "spine radius should widen immediately by the new median -- expected %.3f, got %.3f"
            % (expected, r1))
    print("median_adjust smoketest: +3.0m widened rka_median_width AND the spine's own pavement "
          "radius immediately (%.3f -> %.3f)" % (r0, r1))

    ret = bpy.ops.rka.adjust_median_width(delta=-10.0)
    _assert(ret == {'FINISHED'}, "adjust_median_width (negative) did not finish: %s" % (ret,))
    coll = bpy.data.collections.get(coll.name)
    _assert(coll.get("rka_median_width", -1.0) == 0.0,
            "median width should clamp at 0, not go negative -- got %r" % coll.get("rka_median_width"))
    print("median_adjust smoketest: large negative delta clamped at 0 instead of going negative")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
