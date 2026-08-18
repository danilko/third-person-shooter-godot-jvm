#!/usr/bin/env python3
"""
smoketest_link_propagation.py -- headless verification for live connectivity between pieces
(`live_edit.RKA_LINKED_TO_KEY`, `ops_segment._stamp_link`, `ops_intersection.RKA_OT_connect_markers`/
`RKA_OT_disconnect_marker`, `live_edit._propagate_links`/`_break_stale_links`): the fix for
"adjusting one piece doesn't move whatever was built off it."

Blender's `bpy.app.timers` queue is driven by the window-manager modal timer, which does not run in
`--background` mode -- so, like every other live-edit smoketest in this addon (see
`smoketest_move_segment.py`), this test calls the underlying rebuild/propagation functions directly
instead of relying on `_on_depsgraph_update`'s debounce timer actually firing.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_link_propagation.py
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
from road_kit_authoring import ops_segment as opseg        # noqa: E402
from road_kit_authoring import live_edit                   # noqa: E402
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

    # ------------------------------------------------------------------ build a 3-piece chain:
    # intersection --(Extend From Arm)--> segment1 --(Extend From Port)--> segment2
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
    seg1_origin = opint.get_or_create_origin_marker(seg1_coll)
    _assert(seg1_origin.get(live_edit.RKA_LINKED_TO_KEY) == arm_n.name,
            "segment1's origin marker should be stamped as linked to arm '%s', got %r"
            % (arm_n.name, seg1_origin.get(live_edit.RKA_LINKED_TO_KEY)))
    print("link_propagation smoketest: Extend From Arm stamped the link (segment1 -> %s)" % arm_n.name)

    port_b = next(o for o in seg1_coll.objects if o.get("rka_port") == "B")
    for o in bpy.data.objects:
        o.select_set(False)
    port_b.select_set(True)
    context.view_layer.objects.active = port_b
    ret = bpy.ops.rka.extend_from_port('EXEC_DEFAULT', length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_port did not finish: %s" % (ret,))
    seg2_coll = next(c for c in bpy.data.collections
                      if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                      and c not in (inter_coll, seg1_coll))
    seg2_origin = opint.get_or_create_origin_marker(seg2_coll)
    _assert(seg2_origin.get(live_edit.RKA_LINKED_TO_KEY) == port_b.name,
            "segment2's origin marker should be stamped as linked to port '%s', got %r"
            % (port_b.name, seg2_origin.get(live_edit.RKA_LINKED_TO_KEY)))
    print("link_propagation smoketest: Extend From Port stamped the link (segment2 -> %s)" % port_b.name)

    # ------------------------------------------------------------------ drag the ROOT (the arm) and
    # cascade -- the literal repro of "move one piece, everything built off it should follow"
    dx, dy = 15.0, -8.0
    arm_n.location.x += dx
    arm_n.location.y += dy
    opint.rebuild_intersection_in_place(context, inter_coll)
    # re-fetch: rebuild_intersection_in_place deletes/recreates the pad/curb but NOT the arm
    # markers themselves, so `arm_n` is still the live object -- confirmed valid by construction,
    # re-fetched here only for defensive clarity matching the other smoketests' style.
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_n.name})

    seg1_coll = opint.local_collection(seg1_coll.name)
    seg1_origin = opint.get_or_create_origin_marker(seg1_coll)
    dist1 = math.dist((seg1_origin.location.x, seg1_origin.location.y),
                       (arm_n.location.x, arm_n.location.y))
    _assert(dist1 < 1e-3,
            "segment1's origin marker should follow arm '%s' to its new position, dist=%.4f"
            % (arm_n.name, dist1))
    seg1_spine = bpy.data.objects.get(seg1_coll.get("rka_curve_object"))
    p0 = spine_io.points(seg1_spine)[0].co
    dist1_spine = math.dist((p0[0], p0[1]), (arm_n.location.x, arm_n.location.y))
    _assert(dist1_spine < 1e-3,
            "segment1's spine START POINT (the actual geometry driver) should also follow, "
            "dist=%.4f" % dist1_spine)
    print("link_propagation smoketest: dragging the arm moved segment1's origin marker AND its "
          "spine start point to match (dist=%.6f / %.6f)" % (dist1, dist1_spine))

    # segment2 is linked to segment1's FAR-end port (port_B), not to segment1's own origin/start
    # -- rigidly translating segment1's whole spine (see `_translate_spine`) carries port_B along
    # by the same delta, so re-fetch its (rebuilt, moved) position as the real reference point.
    seg1_coll = opint.local_collection(seg1_coll.name)
    port_b = next(o for o in seg1_coll.objects if o.get("rka_port") == "B")
    seg2_coll = opint.local_collection(seg2_coll.name)
    seg2_origin = opint.get_or_create_origin_marker(seg2_coll)
    dist2 = math.dist((seg2_origin.location.x, seg2_origin.location.y),
                       (port_b.location.x, port_b.location.y))
    _assert(dist2 < 1e-3,
            "the cascade should reach segment2 (linked to segment1's port_B, which moved because "
            "segment1's whole spine was rigidly translated) -- dist=%.4f" % dist2)
    print("link_propagation smoketest: the cascade reached segment2 two hops away, following "
          "segment1's port_B to its new position (dist=%.6f)" % dist2)

    # ------------------------------------------------------------------ auto-break on manual drag
    seg2_origin.location.x += 999.0   # an independent drag, NOT via propagation
    with live_edit.rebuilding():
        live_edit._break_stale_links()
    seg2_origin = opint.get_or_create_origin_marker(opint.local_collection(seg2_coll.name))
    _assert(live_edit.RKA_LINKED_TO_KEY not in seg2_origin.keys(),
            "an independently-dragged dependent marker should have its link auto-cleared")
    print("link_propagation smoketest: auto-break cleared the link after an independent drag")

    stale_x = seg2_origin.location.x
    arm_n.location.x += 5.0
    opint.rebuild_intersection_in_place(context, inter_coll)
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    with live_edit.rebuilding():
        live_edit._propagate_links({arm_n.name})
    seg2_origin = opint.get_or_create_origin_marker(opint.local_collection(seg2_coll.name))
    _assert(abs(seg2_origin.location.x - stale_x) < 1e-6,
            "a later move of the (now-unrelated) target should NOT drag the detached piece along "
            "-- segment2's origin.x changed from %.3f to %.3f" % (stale_x, seg2_origin.location.x))
    print("link_propagation smoketest: the detached piece correctly ignored the target's further move")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
