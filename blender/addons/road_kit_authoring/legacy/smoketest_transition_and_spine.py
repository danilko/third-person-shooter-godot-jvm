#!/usr/bin/env python3
"""
smoketest_transition_and_spine.py -- headless verification for RKA_OT_adjust_transition_lanes
(lane transitions previously had no dedicated lane-count buttons -- Custom Properties only) and
RKA_OT_select_spine (jump straight to a segment/transition's spine_* Curve object).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_transition_and_spine.py
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

    # ================================================================= adjust_transition_lanes
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='NONE',
        curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    _assert(tr_coll.get("rka_lanes_a") == 2 and tr_coll.get("rka_lanes_b") == 1
            and tr_coll.get("rka_lanes_backward_a") == 0 and tr_coll.get("rka_lanes_backward_b") == 0,
            "unexpected initial transition lane state: %s" % {k: tr_coll.get(k) for k in
            ("rka_lanes_a", "rka_lanes_b", "rka_lanes_backward_a", "rka_lanes_backward_b")})

    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = None
    context.view_layer.active_layer_collection = next(
        lc for lc in _iter_layer_colls(context.view_layer.layer_collection) if lc.collection == tr_coll)

    # Forward at end A: 2 -> 3.
    ret = bpy.ops.rka.adjust_transition_lanes(end='A', backward=False, delta=1)
    _assert(ret == {'FINISHED'}, "adjust_transition_lanes (A fwd +1) did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_lanes_a") == 3, "end A forward should be 3, got %s" % tr_coll.get("rka_lanes_a"))
    print("transition_lanes smoketest: end A forward 2 -> 3")

    # Backward at end A: sentinel(0, symmetric w/ forward=3) + 1 -> seeds from 3, becomes 4 (the
    # max lane count this addon's IntProperty fields allow elsewhere -- no clamping needed here).
    ret = bpy.ops.rka.adjust_transition_lanes(end='A', backward=True, delta=1)
    _assert(ret == {'FINISHED'}, "adjust_transition_lanes (A back +1) did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_lanes_backward_a") == 4,
            "end A backward should seed from forward (3) then +1 -> 4, got %s"
            % tr_coll.get("rka_lanes_backward_a"))
    print("transition_lanes smoketest: end A backward sentinel seeded from forward (3) then +1 -> 4")

    # Backward at end A: 4 -> 3 (now an explicit override, independent of forward).
    ret = bpy.ops.rka.adjust_transition_lanes(end='A', backward=True, delta=-1)
    _assert(tr_coll.get("rka_lanes_backward_a") == 3,
            "end A backward should be 3, got %s" % tr_coll.get("rka_lanes_backward_a"))
    _assert(tr_coll.get("rka_lanes_a") == 3, "end A forward should be untouched by a backward change")
    print("transition_lanes smoketest: end A backward explicit override (3), forward untouched")

    # End B: forward is at its minimum (1) -- a further "-" must clamp there, not reach 0. Unlike
    # a plain segment, a transition's forward direction pairs lanes_a directly with lanes_b in one
    # cross-end taper (intersection_kit.build_lane_transition's add_direction), so exactly 0 lanes
    # at only ONE end (while the other end is still >0) is not a valid taper shape at all -- it's
    # not just refused, it isn't even representable, so RKA_OT_adjust_transition_lanes clamps
    # forward to a floor of 1 (matching RKA_OT_build_lane_transition's own min=1 property), same
    # as this end never having been allowed to reach 0 through the build operator either.
    ret = bpy.ops.rka.adjust_transition_lanes(end='B', backward=False, delta=-1)
    _assert(ret == {'FINISHED'}, "end B forward -1 (already at floor) did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_lanes_b") == 1, "end B forward should clamp at floor 1, got %s" % tr_coll.get("rka_lanes_b"))
    print("transition_lanes smoketest: end B forward clamps at floor 1 (never reaches 0)")

    # Backward at end B: sentinel(0, symmetric w/ forward=1) + 1 -> seeds from 1, becomes 2.
    ret = bpy.ops.rka.adjust_transition_lanes(end='B', backward=True, delta=1)
    _assert(ret == {'FINISHED'}, "end B backward +1 did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_lanes_backward_b") == 2,
            "end B backward should seed from forward (1) then apply +1 -> 2, got %s"
            % tr_coll.get("rka_lanes_backward_b"))
    print("transition_lanes smoketest: end B backward sentinel seeded from forward (1) then +1 -> 2")

    # Rebuild geometry must still be consistent -- spine and curb objects should exist and no
    # exception should have propagated out of any of the rebuilds above.
    spine = bpy.data.objects.get(tr_coll.get("rka_curve_object"))
    _assert(spine is not None and spine.type == 'CURVE', "transition spine should still exist after all adjustments")
    print("transition_lanes smoketest: geometry stayed consistent through every adjustment")

    # ============================================================================ select_spine
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = spine   # any object of the transition's collection
    ret = bpy.ops.rka.select_spine()
    _assert(ret == {'FINISHED'}, "select_spine (transition) did not finish: %s" % (ret,))
    _assert(context.selected_objects == [spine] and context.view_layer.objects.active == spine,
            "select_spine should isolate exactly the transition's own spine object")
    print("select_spine smoketest: isolated transition spine '%s'" % spine.name)

    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    # ANY non-spine object of the piece, not specifically a `curb_*` one: what is under test is
    # that `select_spine` resolves the piece from whatever the user happened to click, and which
    # objects a piece is made of is exactly what the modifier-stack migration changes (a stack
    # piece has no curb object at all -- see `ROAD_KIT_REDESIGN.md` §7).
    other_obj = next(o for o in seg_coll.objects if o is not seg_spine)
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = other_obj   # activate a NON-spine object of the segment
    ret = bpy.ops.rka.select_spine()
    _assert(ret == {'FINISHED'},
            "select_spine (segment, via '%s' active) did not finish: %s" % (other_obj.name, ret))
    _assert(context.selected_objects == [seg_spine] and context.view_layer.objects.active == seg_spine,
            "select_spine should resolve the segment's own spine even when another of its objects "
            "('%s'), not the spine itself, was active" % other_obj.name)
    print("select_spine smoketest: isolated segment spine '%s' from '%s' being active"
          % (seg_spine.name, other_obj.name))

    print("SMOKETEST OK")


def _iter_layer_colls(lc):
    yield lc
    for child in lc.children:
        yield from _iter_layer_colls(child)


if __name__ == "__main__":
    main()
