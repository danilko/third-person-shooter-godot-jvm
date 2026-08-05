#!/usr/bin/env python3
"""
smoketest_rebuild_guard.py -- headless regression test for the crash fix in live_edit.rebuilding():
every `rebuild_*_in_place` function is now decorated with `@live_edit.rebuilding()` so a DIRECT
operator call (bypassing `_flush_rebuilds`) sets the SAME `_rebuilding` guard the debounced path
already used. Without it, `RKA_OT_adjust_segment_lanes` writing to the spine curve's own point
radii (before its own synchronous `rebuild_segment_gn_in_place` call) got picked up as fresh "dirt"
by `_on_depsgraph_update` on the very next tick, silently scheduling a SECOND, unprompted rebuild
of the same collection ~0.2s later via `bpy.app.timers` -- the confirmed cause of a real segfault
inside `clear_generated_mesh_objects` (see /tmp/debug_road.crash.txt's Python backtrace:
`_flush_rebuilds` -> `rebuild_segment_gn_in_place` -> `clear_generated_mesh_objects`, immediately
after an `adjust_segment_lanes` click with no user action in between).

This test reproduces the exact trigger (adjust a GN segment's lane count, which mutates the
spine's point radii) and asserts NOTHING ends up pending for a follow-up rebuild afterward.

RUN: blender --background --python addons/road_kit_authoring/smoketest_rebuild_guard.py
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
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
from road_kit_authoring import live_edit                   # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _settle(context):
    """Force a real depsgraph evaluation -- the same mechanism an interactive drag/edit relies
    on -- so `_on_depsgraph_update` gets a chance to observe whatever the last operator mutated."""
    context.view_layer.update()
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()


def _assert_nothing_pending(label):
    _assert(not live_edit._pending_inter, "%s: _pending_inter should be empty, got %s" % (label, live_edit._pending_inter))
    _assert(not live_edit._pending_seg, "%s: _pending_seg should be empty, got %s" % (label, live_edit._pending_seg))
    _assert(not live_edit._pending_curve_seg, "%s: _pending_curve_seg should be empty, got %s" % (label, live_edit._pending_curve_seg))
    _assert(not live_edit._pending_curve_transition, "%s: _pending_curve_transition should be empty, got %s" % (label, live_edit._pending_curve_transition))
    _assert(not live_edit._timer_scheduled, "%s: no redundant rebuild timer should be armed, got _timer_scheduled=%s"
            % (label, live_edit._timer_scheduled))


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ================================================== the exact crash trigger: adjust_segment_lanes
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = spine

    # Flush the BUILD's own depsgraph backlog first -- `_build_segment_from_points` was called
    # directly (not through an operator), so Blender hasn't evaluated a depsgraph tick for its
    # freshly-created objects yet; without this, the first `_settle()` below would misattribute
    # that unrelated backlog to the operator under test (confirmed empirically -- traced every
    # `depsgraph.updates` entry and found the whole segment's initial construction, not the
    # operator's own mutation, the first time this test was written).
    _settle(context)
    live_edit._pending_curve_seg.clear()
    live_edit._timer_scheduled = False
    ret = bpy.ops.rka.adjust_segment_lanes(delta=1)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes did not finish: %s" % (ret,))
    _settle(context)
    _assert_nothing_pending("adjust_segment_lanes (spine radius mutation)")
    print("rebuild_guard smoketest: adjust_segment_lanes's own spine-radius write no longer "
          "re-queues a redundant follow-up rebuild")

    # ================================================================== adjust_transition_lanes
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    tr_spine = bpy.data.objects.get(tr_coll.get("rka_curve_object"))
    context.view_layer.objects.active = tr_spine
    _settle(context)   # flush the build's own backlog -- see the segment case above
    live_edit._pending_curve_transition.clear()
    live_edit._timer_scheduled = False
    ret = bpy.ops.rka.adjust_transition_lanes(end='A', backward=False, delta=1)
    _assert(ret == {'FINISHED'}, "adjust_transition_lanes did not finish: %s" % (ret,))
    _settle(context)
    _assert_nothing_pending("adjust_transition_lanes")
    print("rebuild_guard smoketest: adjust_transition_lanes doesn't re-queue a redundant rebuild either")

    # ==================================================================== intersection rebuild path
    result = opint.build_intersection_geometry(
        context, scene_coll, (200.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")
    context.view_layer.objects.active = arm_n
    _settle(context)   # flush the build's own backlog -- see the segment case above
    live_edit._pending_inter.clear()
    live_edit._timer_scheduled = False
    ret = bpy.ops.rka.adjust_arm_lanes(delta=1)
    _assert(ret == {'FINISHED'}, "adjust_arm_lanes did not finish: %s" % (ret,))
    _settle(context)
    _assert_nothing_pending("adjust_arm_lanes")
    print("rebuild_guard smoketest: adjust_arm_lanes's direct rebuild_intersection_in_place call "
          "doesn't re-queue a redundant rebuild")

    # _rebuild_piece_in_place called directly (the same path live_edit._propagate_links uses for
    # its per-iteration cascade rebuild -- freeze/unfreeze used to be another direct caller of
    # this same function before it was removed; this still exercises the identical guard
    # requirement: a direct rebuild call outside `_flush_rebuilds` must not get picked up as
    # fresh "dirt" and re-queue a redundant second rebuild).
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    arm_n.location.x += 3.0
    context.view_layer.update()
    live_edit._pending_inter.clear()
    live_edit._timer_scheduled = False
    with live_edit.rebuilding():
        opint._rebuild_piece_in_place(context, coll)
    _settle(context)
    _assert_nothing_pending("_rebuild_piece_in_place")
    print("rebuild_guard smoketest: a direct _rebuild_piece_in_place call doesn't re-queue a "
          "redundant rebuild")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
