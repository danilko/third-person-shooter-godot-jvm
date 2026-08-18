#!/usr/bin/env python3
"""
smoketest_lane_index_tags.py -- headless verification for `traffic_viz.py`'s per-lane index tag
overlay (2026-08, `scene.rka.show_lane_indices`): the viewport-visible replacement for the
lanecl_* lane-centerline curves dropped from live generation the same day. Confirms the toggle is
independent of `show_traffic_indicators`, and that an arm/segment with N lanes in a direction
produces exactly N labeled tick items ("L0".."L{N-1}"), positioned at that lane's REAL offset
(`Arm.in_offset`/`out_offset` for an arm -- the same formula the real curb/pavement geometry uses).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_lane_index_tags.py
"""
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import math                                                 # noqa: E402

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import traffic_viz                 # noqa: E402
import intersection_kit as k                                # noqa: E402
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
    rka_scene = context.scene.rka

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 3, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")

    # --- both toggles off -> nothing drawn at all.
    rka_scene.show_traffic_indicators = False
    rka_scene.show_lane_indices = False
    items = traffic_viz._gather(context)
    _assert(items == [], "both toggles off should draw nothing, got %d items" % len(items))
    print("lane_index_tags smoketest: both toggles off draws nothing")

    # --- lane indices independent of the traffic arrows toggle.
    rka_scene.show_traffic_indicators = False
    rka_scene.show_lane_indices = True
    items = traffic_viz._gather(context)
    _assert(items, "show_lane_indices alone should still draw lane tags")
    _assert(all(not lbl.startswith(("IN ", "OUT ", "FWD ", "BACK ")) for *_ , lbl in items),
            "with arrows off, no arrow-style label should appear -- got %r"
            % [lbl for *_ , lbl in items])
    print("lane_index_tags smoketest: show_lane_indices works independently of "
          "show_traffic_indicators")

    # --- arm N has 3 lanes each way (symmetric, no oneway/lanes_out override) -> exactly one tick
    # per lane index per direction, positioned EXACTLY at Arm.in_offset/out_offset(i) -- matched
    # by analytically recomputing the expected position (not a loose search radius, which can
    # accidentally catch a NEIGHBORING arm's own outer-lane ticks on a tight 4-way).
    angle = arm_n.get("rka_arm_angle", 0.0)
    lane_width = coll.get("rka_lane_width", 5.0)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    a = k.Arm("_check", angle, lane_width, 3, traffic_side=traffic_side)
    d = k.arm_dir(angle)
    perp = k.lane_perp(d, traffic_side)
    base = (arm_n.location.x, arm_n.location.y)

    def _expect(offset_fn, i):
        lat = offset_fn(i)
        return (base[0] + perp[0] * lat, base[1] + perp[1] * lat)

    def _find(expected_xy, color, label):
        for p, _tip, c, lbl in items:
            if (lbl == label and tuple(c) == tuple(color)
                    and math.hypot(p[0] - expected_xy[0], p[1] - expected_xy[1]) < 1e-3):
                return True
        return False

    for i in range(3):
        _assert(_find(_expect(a.in_offset, i), traffic_viz.IN_COLOR, "L%d" % i),
                "expected an IN L%d tick at arm N's exact in_offset(%d) position" % (i, i))
        _assert(_find(_expect(a.out_offset, i), traffic_viz.OUT_COLOR, "L%d" % i),
                "expected an OUT L%d tick at arm N's exact out_offset(%d) position" % (i, i))
    print("lane_index_tags smoketest: arm N (3 lanes) produced exactly-positioned L0/L1/L2 IN + "
          "L0/L1/L2 OUT ticks")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
