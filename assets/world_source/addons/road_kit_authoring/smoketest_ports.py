#!/usr/bin/env python3
"""
smoketest_ports.py -- headless verification for:
  1. port_A/port_B end markers on GN segments (ops_segment._place_segment_ports) + RKA_OT_extend_from_port.
  2. live_edit.py's debounced rebuild (_flush_rebuilds) still performs the same rebuild dispatch
     it used to do synchronously, now decoupled from the depsgraph callback.

RUN: blender --background --python addons/road_kit_authoring/smoketest_ports.py
"""
import bpy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # .../addons/road_kit_authoring
ADDONS_DIR = os.path.dirname(HERE)                           # .../addons
ROOT = os.path.dirname(ADDONS_DIR)                            # assets/world_source
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                     # noqa: E402
from road_kit_authoring import ops_segment as opseg  # noqa: E402
from road_kit_authoring import live_edit             # noqa: E402
import kit_common as kc                               # noqa: E402


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

    # --- 1. port markers exist after a fresh build, with sane outward headings.
    pts = [(0.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    result = opseg._build_segment_from_points(
        context, scene_coll, pts, lane_width=5.0, lanes=1, lanes_backward=1,
        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    coll_name = result["coll"].name
    coll = bpy.data.collections.get(coll_name)
    ports = [o for o in coll.objects if "rka_port" in o.keys()]
    _assert(len(ports) == 2, "expected 2 port markers, got %d" % len(ports))
    port_a = next(o for o in ports if o["rka_port"] == "A")
    port_b = next(o for o in ports if o["rka_port"] == "B")
    _assert(abs(port_a.location.x - 0.0) < 1e-6, "port_A should sit at the spine start")
    _assert(abs(port_b.location.x - 20.0) < 1e-6, "port_B should sit at the spine end")
    _assert(abs(port_b.get("rka_port_heading_deg", -999.0) - 0.0) < 1e-3,
            "port_B heading should point outward along +X (0 deg)")
    _assert(abs(abs(port_a.get("rka_port_heading_deg", -999.0)) - 180.0) < 1e-3,
            "port_A heading should point outward along -X (180 deg)")
    print("ports smoketest: port_A/port_B present at correct positions with correct outward headings")

    # --- 2. RKA_OT_extend_from_port continues with the SAME lane setup.
    for o in bpy.data.objects:
        o.select_set(False)
    port_b.select_set(True)
    context.view_layer.objects.active = port_b
    ret = bpy.ops.rka.extend_from_port(length=15.0)
    _assert(ret == {'FINISHED'}, "RKA_OT_extend_from_port did not finish: %s" % (ret,))
    new_colls = [c for c in bpy.data.collections if c.name not in (coll_name, "Collection")
                 and "rka_curve_object" in c.keys()]
    _assert(len(new_colls) == 1, "expected exactly 1 new segment collection, got %d" % len(new_colls))
    new_coll = new_colls[0]
    _assert(new_coll.get("rka_lanes") == 1 and new_coll.get("rka_lanes_backward") == 1,
            "extended segment should inherit lanes=1/lanes_backward=1 from the source")
    new_spine = bpy.data.objects.get(new_coll["rka_curve_object"])
    p0 = new_spine.data.splines[0].points[0].co
    p1 = new_spine.data.splines[0].points[-1].co
    _assert(abs(p0.x - 20.0) < 1e-6, "extended segment should start at port_B's position (x=20)")
    _assert(abs(p1.x - 35.0) < 1e-6, "extended segment should run +15m outward along +X (x=35)")
    print("ports smoketest: RKA_OT_extend_from_port built a new segment from port_B, "
          "same lanes, correct outward direction")

    # --- 3. re-snap on rebuild: reshape the ORIGINAL segment's spine and confirm ports track it,
    # with no duplicate port objects.
    orig_spine = bpy.data.objects.get(coll["rka_curve_object"])
    orig_spine.data.splines[0].points[-1].co = (30.0, 0.0, 0.0, 1.0)   # was (20,0,0)
    opseg.rebuild_segment_gn_in_place(context, coll)
    coll = bpy.data.collections.get(coll_name)
    ports_after = [o for o in coll.objects if "rka_port" in o.keys()]
    _assert(len(ports_after) == 2, "expected still 2 port markers after rebuild, got %d "
                                    "(duplicate accumulation?)" % len(ports_after))
    port_b_after = next(o for o in ports_after if o["rka_port"] == "B")
    _assert(abs(port_b_after.location.x - 30.0) < 1e-6,
            "port_B should re-snap to the reshaped spine's new endpoint (x=30)")
    print("ports smoketest: port markers re-snap to a reshaped spine, no duplicate accumulation")

    # --- 4. live_edit.py's debounced rebuild still performs the correct dispatch (regression
    # check for the crash-fix refactor -- see live_edit.py's module docstring).
    live_edit._pending_curve_seg.add(coll_name)
    orig_spine = bpy.data.objects.get(coll["rka_curve_object"])
    orig_spine.data.splines[0].points[-1].co = (50.0, 0.0, 0.0, 1.0)
    live_edit._flush_rebuilds()
    _assert(not live_edit._pending_curve_seg, "pending set should be cleared after flush"
    )
    coll = bpy.data.collections.get(coll_name)
    port_b_final = next(o for o in coll.objects if o.get("rka_port") == "B")
    _assert(abs(port_b_final.location.x - 50.0) < 1e-6,
            "live_edit._flush_rebuilds should have rebuilt the segment (port_B now at x=50)")
    print("ports smoketest: live_edit._flush_rebuilds performs the deferred rebuild correctly")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
