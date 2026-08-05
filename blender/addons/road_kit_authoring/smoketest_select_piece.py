#!/usr/bin/env python3
"""
smoketest_select_piece.py -- headless verification for RKA_OT_select_piece/RKA_OT_select_arm:
'Select Piece' must select every object in a piece's collection (not just its origin marker) and
make that marker active with Pivot Point 'Active Element'; 'Select Arm' must isolate exactly one
named arm within the CORRECT intersection (not a same-named arm belonging to a different one).

RUN: blender --background --python addons/road_kit_authoring/smoketest_select_piece.py
"""
import bpy
import math
import os
import sys

import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
import kit_common as kc                                    # noqa: E402


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

    # --- Select Piece: build a 4-way, activate just its origin marker (the minimal selection),
    # run Select Piece, and confirm every object in the collection ends up selected.
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    marker = opint.get_or_create_origin_marker(coll)
    for o in bpy.data.objects:
        o.select_set(False)
    marker.select_set(True)
    context.view_layer.objects.active = marker
    context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'

    ret = bpy.ops.rka.select_piece()
    _assert(ret == {'FINISHED'}, "select_piece did not finish: %s" % (ret,))
    selected = set(context.selected_objects)
    expected = set(coll.objects)
    _assert(selected == expected,
            "select_piece should select EVERY object in the collection -- missing=%s extra=%s"
            % (expected - selected, selected - expected))
    _assert(context.view_layer.objects.active == marker,
            "select_piece should leave the origin marker active")
    _assert(context.scene.tool_settings.transform_pivot_point == 'ACTIVE_ELEMENT',
            "select_piece should set Pivot Point to 'Active Element'")
    print("select_piece smoketest: selected all %d object(s) in '%s', origin marker active, "
          "pivot set to Active Element" % (len(expected), coll.name))

    # --- Select Arm: build a SECOND 4-way (so both intersections have an arm named 'N') and
    # confirm rka.select_arm resolves the arm WITHIN the currently-active piece, not a same-named
    # arm belonging to the other intersection -- the concrete bug a naive global-name lookup would
    # hit (arm names are only unique PER intersection).
    result2 = opint.build_intersection_geometry(
        context, scene_coll, (500.0, 500.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll2 = result2["coll"]
    arm_n_2 = next(o for o in coll2.objects if o.get("rka_arm_name") == "N")

    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = arm_n_2   # active object belongs to coll2, not coll
    ret = bpy.ops.rka.select_arm(arm_name="N")
    _assert(ret == {'FINISHED'}, "select_arm did not finish: %s" % (ret,))
    _assert(context.selected_objects == [arm_n_2],
            "select_arm('N') with coll2's arm active should isolate coll2's own 'N' arm, got %s"
            % context.selected_objects)
    _assert(context.view_layer.objects.active == arm_n_2,
            "select_arm should make the resolved arm the active object")
    print("select_arm smoketest: resolved 'N' within the correct (currently-active) intersection "
          "'%s', not the same-named arm on '%s'" % (coll2.name, coll.name))

    # Switch active object to the FIRST intersection's arm marker and confirm select_arm now
    # resolves to THAT collection's own 'N' instead (same name, different object).
    arm_n_1 = next(o for o in coll.objects if o.get("rka_arm_name") == "N")
    context.view_layer.objects.active = arm_n_1
    ret = bpy.ops.rka.select_arm(arm_name="N")
    _assert(ret == {'FINISHED'}, "select_arm did not finish (second call): %s" % (ret,))
    _assert(context.selected_objects == [arm_n_1],
            "select_arm('N') with coll's own arm active should isolate coll's own 'N' arm "
            "(different object than coll2's), got %s" % context.selected_objects)
    print("select_arm smoketest: switching the active piece correctly re-resolves 'N' to '%s's "
          "own arm object" % coll.name)

    # --- Select Piece By Name: 2026-07-28, user-reported -- with NOTHING selected/active,
    # rka.select_piece's own poll() always fails (it needs something piece-related already
    # active), so there was no way to select a FIRST piece from the panel at all. Confirm the
    # by-name variant works from a totally clean slate (nothing selected, nothing active) and its
    # poll() is unconditional (always True, unlike select_piece).
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    _assert(not bpy.ops.rka.select_piece.poll(),
            "select_piece's poll should fail with nothing active (the bug this fixes)")
    _assert(bpy.ops.rka.select_piece_by_name.poll(),
            "select_piece_by_name's poll should always succeed (no active-object precondition)")
    ret = bpy.ops.rka.select_piece_by_name(coll_name=coll2.name)
    _assert(ret == {'FINISHED'}, "select_piece_by_name did not finish: %s" % (ret,))
    _assert(set(context.selected_objects) == set(coll2.objects),
            "select_piece_by_name should select every object in the NAMED collection, from a "
            "clean slate with nothing previously active")
    print("select_piece_by_name smoketest: selected '%s' from a completely clean slate (nothing "
          "active/selected beforehand) -- the bootstrapping gap select_piece's poll() left" % coll2.name)

    # bpy.ops raises RuntimeError for an ERROR-reported CANCELLED result -- that IS the expected
    # outcome here (see smoketest_lane_map_panel.py for the same pattern).
    try:
        bpy.ops.rka.select_piece_by_name(coll_name="NotARealPiece")
        _assert(False, "a bogus coll_name should have raised/CANCELLED, it did not")
    except RuntimeError as exc:
        _assert("not a local road_kit_authoring piece" in str(exc), "unexpected error: %s" % exc)
    print("select_piece_by_name smoketest: a bogus/non-piece collection name is rejected cleanly")

    # --- Regression (2026-08, user-reported: "the arm/pad generation seem in strange shape...
    # still wrong after releasing/finishing the drag"): select_piece selects every generated
    # pad_/curb_ object too, not just markers, so a real Grab/Rotate on that selection (Pivot
    # Point = Active Element, exactly what select_piece sets up) rigidly transforms THEIR OWN
    # object transform -- but pad_/curb_ shape is baked as absolute world-space point data, which
    # must sit on an identity-transform object. Confirm a rebuild resets that transform back to
    # identity instead of silently carrying the corruption forward forever.
    for o in bpy.data.objects:
        o.select_set(False)
    for o in coll.objects:
        o.select_set(True)
    context.view_layer.objects.active = marker
    pivot = marker.location.copy()
    angle = math.radians(25.0)
    rot_mat = mathutils.Matrix.Rotation(angle, 4, 'Z')
    for o in coll.objects:
        rel = o.location - pivot
        o.location = pivot + rot_mat @ rel
        o.rotation_euler.z += angle
    pad = coll.objects["pad_%s" % coll.name]
    _assert(abs(pad.rotation_euler.z) > 1e-6,
            "sanity: the simulated rigid rotate should have moved pad's own rotation off identity")

    opint.rebuild_intersection_in_place(context, coll)
    coll = opint.local_collection(coll.name)
    pad_after = coll.objects["pad_%s" % coll.name]
    _assert(pad_after.rotation_euler.z == 0.0 and tuple(pad_after.location) == (0.0, 0.0, 0.0),
            "a rebuild must reset a reused pad_/curb_ object's transform back to identity -- got "
            "rotation.z=%.6f location=%r (this was the 'strange shape after drag' bug)"
            % (pad_after.rotation_euler.z, tuple(pad_after.location)))
    curb0 = next(o for o in coll.objects if o.name.startswith("curb_%s_" % coll.name))
    _assert(curb0.rotation_euler.z == 0.0 and tuple(curb0.location) == (0.0, 0.0, 0.0),
            "a rebuild must also reset a reused curb boundary object's transform to identity")
    print("select_piece smoketest: a rebuild after a whole-piece Grab/Rotate resets pad_/curb_ "
          "object transforms back to identity (the select_piece + rigid-transform corruption fix)")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
