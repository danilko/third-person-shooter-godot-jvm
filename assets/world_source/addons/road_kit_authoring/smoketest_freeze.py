#!/usr/bin/env python3
"""
smoketest_freeze.py -- headless verification for RKA_OT_freeze_for_move/RKA_OT_unfreeze_and_rebuild:
while frozen (rka_live_edit=False), moving a piece's markers must NOT dirty it for live_edit's
rebuild queue (the crash-avoidance path); Unfreeze & Rebuild must then re-sync geometry in one
explicit, safe call.

RUN: blender --background --python addons/road_kit_authoring/smoketest_freeze.py
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

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")

    # --- Freeze via the operator (select the arm marker as active object first). Also move the
    # 3D cursor away and set Pivot Point to something else first, so we can confirm Freeze does
    # NOT touch the cursor (other tools rely on its position for their own placement) but DOES
    # switch Pivot Point to 'Active Element' with the origin marker made active -- the fix for
    # rotating the whole piece swinging through a huge arc around an unrelated point ('3D Cursor'
    # left at a stale/world-origin position, or 'Median Point' getting dragged toward world origin
    # by however many of the piece's own curb/pad/lanecl/mark objects sit at local (0,0,0) -- see
    # RKA_OT_freeze_for_move's docstring) instead of spinning it in place.
    cursor_before = (123.0, -45.0, 6.0)
    context.scene.cursor.location = cursor_before
    context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.freeze_for_move()
    _assert(ret == {'FINISHED'}, "freeze_for_move did not finish: %s" % (ret,))
    _assert(coll.get("rka_live_edit") is False, "rka_live_edit should be False after freezing")
    marker = opint.get_or_create_origin_marker(coll)
    cursor = tuple(context.scene.cursor.location)
    _assert(math.dist(cursor, cursor_before) < 1e-9,
            "Freeze For Move must NOT move the 3D cursor (other plugins rely on its position), "
            "got %s expected unchanged %s" % (cursor, cursor_before))
    _assert(context.scene.tool_settings.transform_pivot_point == 'ACTIVE_ELEMENT',
            "Freeze For Move should switch Pivot Point to 'Active Element', got %s"
            % context.scene.tool_settings.transform_pivot_point)
    _assert(context.view_layer.objects.active == marker,
            "Freeze For Move should make the origin marker the active object")
    _assert(coll.get("rka_prev_pivot_point") == 'MEDIAN_POINT',
            "Freeze For Move should stash the PREVIOUS pivot point setting for Unfreeze to "
            "restore, got %s" % coll.get("rka_prev_pivot_point"))
    print("freeze smoketest: RKA_OT_freeze_for_move left the 3D cursor untouched, switched Pivot "
          "Point to 'Active Element' on the origin marker, and stashed the previous pivot setting")

    # --- While frozen, move the arm and force a real depsgraph evaluation (the same mechanism
    # an interactive drag relies on) -- the collection must NOT end up in live_edit's pending set.
    live_edit._pending_inter.clear()
    arm_n.location.x += 5.0
    arm_n.location.y += 5.0
    context.view_layer.update()
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()
    _assert(coll.name not in live_edit._pending_inter,
            "frozen collection should NEVER be added to the live-edit pending set, got %s"
            % live_edit._pending_inter)
    print("freeze smoketest: moving a marker while frozen does not dirty the collection "
          "(pending_inter=%s)" % live_edit._pending_inter)

    # --- Unfreeze & Rebuild: re-enables live_edit AND performs one explicit, safe rebuild that
    # picks up the marker's NEW position.
    angle_before = None
    arms_before = custom_props.read_arms(coll)
    for name, angle, *_ in arms_before:
        if name == "N":
            angle_before = angle
    ret = bpy.ops.rka.unfreeze_and_rebuild()
    _assert(ret == {'FINISHED'}, "unfreeze_and_rebuild did not finish: %s" % (ret,))
    coll = bpy.data.collections.get(coll.name)
    _assert(coll.get("rka_live_edit", True) is True, "rka_live_edit should be True after unfreezing")
    arms_after = custom_props.read_arms(coll)
    angle_after = next(a for a in arms_after if a[0] == "N")[1]
    _assert(abs(angle_after - angle_before) > 1.0,
            "arm N's angle should have changed to reflect its new (moved) position: "
            "before=%.2f after=%.2f" % (angle_before, angle_after))
    print("freeze smoketest: Unfreeze & Rebuild re-enabled live_edit and rebuilt with the "
          "moved arm's new angle (before=%.2f after=%.2f)" % (angle_before, angle_after))
    _assert(context.scene.tool_settings.transform_pivot_point == 'MEDIAN_POINT',
            "Unfreeze & Rebuild should restore the pivot point setting Freeze stashed, got %s"
            % context.scene.tool_settings.transform_pivot_point)
    _assert("rka_prev_pivot_point" not in coll.keys(),
            "the stashed pivot-point custom prop should be cleaned up after Unfreeze")
    print("freeze smoketest: Unfreeze & Rebuild restored the previous Pivot Point setting "
          "('MEDIAN_POINT') and cleaned up the stash")

    # --- A plain GN segment's Freeze For Move must ALSO work when the object made active by a
    # "select everything, Grab" pass is one of the generated curb/pavement objects, not just a
    # small marker Empty -- previously only markers (segend/segbend/port/origin) and the spine
    # (by exact name match) resolved, so activating a `curb_*` mesh (far more numerous/visually
    # larger, very plausible to end up active during a box-select) made the poll fail silently and
    # a user would then move it unfrozen -- the exact crash Freeze exists to prevent. AND it must
    # go through the exact same cursor-untouched / Active-Element-on-origin-marker pivot mechanism
    # as an intersection -- Freeze/Unfreeze are ONE shared operator pair for every piece type
    # (see get_or_create_origin_marker's use in _build_segment_from_points/
    # RKA_OT_build_lane_transition), not a per-type reimplementation.
    context.scene.cursor.location = cursor_before
    context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    curb_obj = bpy.data.objects["curb_%s_L" % seg_coll.name]
    for o in bpy.data.objects:
        o.select_set(False)
    curb_obj.select_set(True)
    context.view_layer.objects.active = curb_obj
    ret = bpy.ops.rka.freeze_for_move()
    _assert(ret == {'FINISHED'}, "freeze_for_move should succeed with a curb mesh object (not a "
                                  "marker) active, got %s" % (ret,))
    _assert(seg_coll.get("rka_live_edit") is False,
            "segment collection should be frozen after activating one of its curb objects")
    seg_marker = opint.get_or_create_origin_marker(seg_coll)
    _assert(math.dist(tuple(context.scene.cursor.location), cursor_before) < 1e-9,
            "segment Freeze For Move must not move the 3D cursor either")
    _assert(context.scene.tool_settings.transform_pivot_point == 'ACTIVE_ELEMENT',
            "segment Freeze For Move should also switch Pivot Point to 'Active Element'")
    _assert(context.view_layer.objects.active == seg_marker,
            "segment Freeze For Move should make ITS origin marker the active object, not the "
            "curb object that was active when Freeze was pressed")
    print("freeze smoketest: Freeze For Move resolves a plain segment via a curb mesh object "
          "made active, and applies the same cursor-untouched/Active-Element-on-origin-marker "
          "pivot mechanism as an intersection")
    bpy.ops.rka.unfreeze_and_rebuild()
    _assert(context.scene.tool_settings.transform_pivot_point == 'MEDIAN_POINT',
            "Unfreeze & Rebuild should restore the pivot point for a segment too")

    # --- Lane transitions go through the identical mechanism too (rka_lanes_a collections,
    # dispatched by rebuild_lane_transition_in_place -- see _rebuild_piece_in_place).
    context.scene.cursor.location = cursor_before
    context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='BOX',
        curb_r_style='BOX')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    tr_curb = bpy.data.objects["curb_%s_L" % tr_coll.name]
    for o in bpy.data.objects:
        o.select_set(False)
    tr_curb.select_set(True)
    context.view_layer.objects.active = tr_curb
    ret = bpy.ops.rka.freeze_for_move()
    _assert(ret == {'FINISHED'}, "freeze_for_move should succeed on a lane transition via a curb "
                                  "mesh object active, got %s" % (ret,))
    tr_marker = opint.get_or_create_origin_marker(tr_coll)
    _assert(math.dist(tuple(context.scene.cursor.location), cursor_before) < 1e-9,
            "lane transition Freeze For Move must not move the 3D cursor either")
    _assert(context.scene.tool_settings.transform_pivot_point == 'ACTIVE_ELEMENT',
            "lane transition Freeze For Move should also switch Pivot Point to 'Active Element'")
    _assert(context.view_layer.objects.active == tr_marker,
            "lane transition Freeze For Move should make ITS origin marker the active object")
    print("freeze smoketest: Freeze For Move applies the same mechanism to a lane transition too")
    bpy.ops.rka.unfreeze_and_rebuild()
    _assert(context.scene.tool_settings.transform_pivot_point == 'MEDIAN_POINT',
            "Unfreeze & Rebuild should restore the pivot point for a lane transition too")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
