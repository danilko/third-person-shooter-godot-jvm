#!/usr/bin/env python3
"""
smoketest_curb_rises_up.py -- headless regression check: a curb built via `curb_loop()`/
`GN_CurbLoop` must rise ABOVE the road surface (base flush with the road, top = base + curb
height), not hang below it (2026-07-28, user-reported: "the generated road mesh is on top of
curb rather than bottom of curb" -- Curve to Mesh maps the curb profile's local +Y to world -Z,
the same quirk `GN_BarrierProfile` already documents/compensates for; `_curb_profile_object`
never got the matching negation, so a curb's base ended up ABOVE its top instead of below it,
confirmed directly: a flat curb line at Z=5.0 evaluated to [4.85, 5.0] instead of [5.0, 5.15]).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_curb_rises_up.py
"""
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka   # noqa: E402
import kit_common as kc             # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _evaluated_z_range(obj):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    me = eo.to_mesh()
    zs = sorted(set(round((obj.matrix_world @ v.co).z, 4) for v in me.vertices))
    eo.to_mesh_clear()
    return zs


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    road_z = 5.0
    curb_height = 0.15
    pts = [(0.0, 0.0, road_z, 0.0), (20.0, 0.0, road_z, 0.0), (40.0, 0.0, road_z, 0.0)]

    coll = kc.get_coll("TEST_BOX")
    curb_box = kc.curb_loop("CurbBox", pts, coll, curb_style='BOX', curb_height=curb_height,
                             curb_thickness=0.25, closed=False)
    zs_box = _evaluated_z_range(curb_box)
    _assert(zs_box == [road_z, round(road_z + curb_height, 4)],
            "BOX curb at road Z=%.2f should span [%.2f, %.2f] (rising up), got %r"
            % (road_z, road_z, road_z + curb_height, zs_box))
    print("smoketest_curb_rises_up: BOX curb correctly rises from the road surface upward, "
          "Z range %r" % zs_box)

    coll2 = kc.get_coll("TEST_GUTTER")
    curb_gutter = kc.curb_loop("CurbGutter", pts, coll2, curb_style='GUTTER',
                                curb_height=curb_height, curb_thickness=0.6, closed=False)
    zs_gutter = _evaluated_z_range(curb_gutter)
    _assert(min(zs_gutter) == road_z, "GUTTER curb's lowest point should be exactly the road "
            "surface (%.2f), got min=%r" % (road_z, min(zs_gutter)))
    _assert(max(zs_gutter) == round(road_z + curb_height, 4),
            "GUTTER curb's highest point should be road + curb_height (%.2f), got max=%r"
            % (road_z + curb_height, max(zs_gutter)))
    print("smoketest_curb_rises_up: GUTTER curb also correctly rises from the road surface "
          "upward, Z range %r" % zs_gutter)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
