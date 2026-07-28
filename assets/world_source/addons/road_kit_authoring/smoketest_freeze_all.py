#!/usr/bin/env python3
"""
smoketest_freeze_all.py -- headless verification for RKA_OT_freeze_all_for_move /
RKA_OT_unfreeze_all_and_rebuild (the bulk versions of Freeze For Move / Unfreeze & Rebuild --
road_blender_godot.md: moving/rotating EVERY piece in a file at once, with live-edit on, crashes
Blender; these bulk operators freeze/unfreeze every LOCAL piece in one click instead of once per
piece). Builds 3 pieces (2 intersections + 1 segment), freezes all, simulates a group transform
(moving every piece's own handle simultaneously -- the actual crash scenario) and confirms NONE
of them get queued for a live-edit rebuild while frozen, then unfreezes + rebuilds all and
confirms every piece's geometry actually picked up its new position.

RUN: blender --background --python addons/road_kit_authoring/smoketest_freeze_all.py
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
from road_kit_authoring import live_edit                   # noqa: E402
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

    r1 = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    r2 = opint.build_intersection_geometry(
        context, scene_coll, (200.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    r3 = opseg._build_segment_from_points(
        context, scene_coll, [(400.0, 0.0, 0.0), (440.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    colls = [r1["coll"], r2["coll"], r3["coll"]]
    _assert(all(c.get("rka_live_edit", True) for c in colls),
            "all 3 pieces should start un-frozen (default rka_live_edit is absent = True)")

    # --- Freeze ALL, with no particular object active/selected (mirrors "run it before touching
    # anything else" -- unlike the single-piece operator, this one doesn't need a target).
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    _assert(bpy.ops.rka.freeze_all_for_move.poll(), "freeze_all_for_move should poll True with "
                                                      "3 un-frozen pieces present")
    ret = bpy.ops.rka.freeze_all_for_move()
    _assert(ret == {'FINISHED'}, "freeze_all_for_move did not finish: %s" % (ret,))
    for c in colls:
        _assert(c.get("rka_live_edit") is False,
                "'%s' should be frozen after freeze_all_for_move" % c.name)
    print("freeze_all smoketest: freeze_all_for_move froze all 3 pieces (2 intersections + 1 "
          "segment) in one call")

    # --- Idempotent: running it again with everything already frozen should poll False (nothing
    # left to freeze) rather than erroring.
    _assert(not bpy.ops.rka.freeze_all_for_move.poll(),
            "freeze_all_for_move should poll False once every piece is already frozen")
    print("freeze_all smoketest: freeze_all_for_move is idempotent (poll() correctly refuses a "
          "second run with nothing left to freeze)")

    # --- Simulate a real group transform: move EVERY piece's own handle Empty simultaneously (the
    # exact "select everything, Grab" scenario that crashed Blender with live-edit on), then force
    # a real depsgraph evaluation -- the same mechanism an interactive drag relies on. NONE of the
    # 3 collections may end up in any live-edit pending set.
    live_edit._pending_inter.clear()
    live_edit._pending_seg.clear()
    live_edit._pending_curve_seg.clear()
    live_edit._pending_curve_transition.clear()
    arm_n_1 = next(o for o in r1["coll"].objects if o.get("rka_arm_name") == "N")
    arm_n_2 = next(o for o in r2["coll"].objects if o.get("rka_arm_name") == "N")
    # r3 is a curve-spine segment (_build_segment_from_points) -- it has no segend_A/B markers
    # (those are only for the point/direction/length-based build_segment_geometry); its own
    # "handle" is the live spine Curve object itself (moving/editing it is what dirties
    # dirty_curve_names in live_edit.py).
    spine_3 = bpy.data.objects["spine_%s" % r3["coll"].name]
    for o in (arm_n_1, arm_n_2, spine_3):
        o.location.x += 5.0
        o.location.y += 5.0
    context.view_layer.update()
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()
    _assert(not live_edit._pending_inter and not live_edit._pending_seg
            and not live_edit._pending_curve_seg and not live_edit._pending_curve_transition,
            "moving every frozen piece's handle at once (a group transform) must not queue ANY "
            "of them for a live-edit rebuild -- got pending_inter=%s pending_seg=%s "
            "pending_curve_seg=%s" % (live_edit._pending_inter, live_edit._pending_seg,
                                       live_edit._pending_curve_seg))
    print("freeze_all smoketest: a simulated group transform touching all 3 frozen pieces' "
          "handles simultaneously dirtied none of them (pending_inter=%s pending_seg=%s "
          "pending_curve_seg=%s)" % (live_edit._pending_inter, live_edit._pending_seg,
                                      live_edit._pending_curve_seg))

    # --- Unfreeze ALL & Rebuild: re-enables live_edit AND rebuilds every piece, picking up each
    # one's new (moved) handle position.
    angle1_before = next(a for a in custom_props.read_arms(r1["coll"]) if a[0] == "N")[1]
    angle2_before = next(a for a in custom_props.read_arms(r2["coll"]) if a[0] == "N")[1]
    p0_3_before = tuple(r3["coll"].get("rka_p0"))

    _assert(bpy.ops.rka.unfreeze_all_and_rebuild.poll(), "unfreeze_all_and_rebuild should poll "
                                                          "True with 3 frozen pieces present")
    ret = bpy.ops.rka.unfreeze_all_and_rebuild()
    _assert(ret == {'FINISHED'}, "unfreeze_all_and_rebuild did not finish: %s" % (ret,))

    r1_coll = bpy.data.collections.get(r1["coll"].name)
    r2_coll = bpy.data.collections.get(r2["coll"].name)
    r3_coll = bpy.data.collections.get(r3["coll"].name)
    for c in (r1_coll, r2_coll, r3_coll):
        _assert(c.get("rka_live_edit", True) is True,
                "'%s' should be un-frozen after unfreeze_all_and_rebuild" % c.name)

    angle1_after = next(a for a in custom_props.read_arms(r1_coll) if a[0] == "N")[1]
    angle2_after = next(a for a in custom_props.read_arms(r2_coll) if a[0] == "N")[1]
    p0_3_after = tuple(r3_coll.get("rka_p0"))
    _assert(abs(angle1_after - angle1_before) > 1.0,
            "intersection 1's arm N should reflect its new position after the bulk rebuild")
    _assert(abs(angle2_after - angle2_before) > 1.0,
            "intersection 2's arm N should reflect its new position after the bulk rebuild")
    _assert(math.dist(p0_3_after, p0_3_before) > 1.0,
            "segment 3's p0 should reflect its new position after the bulk rebuild")
    print("freeze_all smoketest: unfreeze_all_and_rebuild re-enabled live_edit on all 3 pieces "
          "AND rebuilt each with its new (moved) handle position "
          "(intersection1 %.2f->%.2f, intersection2 %.2f->%.2f, segment3 moved %.2fm)"
          % (angle1_before, angle1_after, angle2_before, angle2_after,
             math.dist(p0_3_after, p0_3_before)))

    _assert(not bpy.ops.rka.unfreeze_all_and_rebuild.poll(),
            "unfreeze_all_and_rebuild should poll False once nothing is frozen")
    print("freeze_all smoketest: unfreeze_all_and_rebuild is idempotent too")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
