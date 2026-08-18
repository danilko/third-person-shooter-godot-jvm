#!/usr/bin/env python3
"""
smoketest_stack_live_edit.py -- a MODIFIER-STACK piece must be as editable as a sibling-object one.

WHY THIS EXISTS (migration Step 2, 2026-08-13). `rebuild_segment_gn_in_place` used to begin with
`if spine_obj.type != 'CURVE': return`. A stack piece's carrier is a MESH, so every cross-section
edit -- add a lane, taper the end, widen the median, grow a sidewalk -- wrote its custom property,
reported `{'FINISHED'}`, and changed no geometry whatsoever. Nothing failed; the road just quietly
ignored you.

It was easy to miss for a specific reason worth remembering: DRAGGING the spine always worked, and
still needs no Python at all, because the entire stack is driven off the carrier's own vertices by
geometry nodes. So the piece looked live-editable right up until you touched its cross-section.

Everything here is asserted through `lib/piece_probe.py` -- measured geometry, never object names --
so these same assertions keep their meaning now that the stack is the only build path.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_stack_live_edit.py
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
from road_kit_authoring import spine_io                    # noqa: E402
import kit_common as kc                                     # noqa: E402
import piece_probe as pp                                    # noqa: E402

LW = 5.0
TOL = 1e-2


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _activate(context, coll):
    """Make the piece's carrier the active object -- what a user clicking the road does."""
    for o in bpy.data.objects:
        o.select_set(False)
    sp = bpy.data.objects.get(coll["rka_curve_object"])
    sp.select_set(True)
    context.view_layer.objects.active = sp
    return sp


def _end_extents(coll):
    """Left-side lateral reach near the piece's START and near its END -- the pair that shows a
    taper. Equal on a constant-width road, different on a tapered one."""
    st = pp.stations(coll)
    s_max = max(s for (s, _l, _d) in st)
    near = [lat for (s, lat, _d) in st if s < s_max * 0.1]
    far = [lat for (s, lat, _d) in st if s > s_max * 0.9]
    return max(near), max(far)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    scene_coll = context.scene.collection
    bpy.ops.rka.link_curb_kit_library()

    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (80.0, 0.0, 0.0)],
        lane_width=LW, lanes=2, lanes_backward=2,
        curb_l_style='BOX', curb_r_style='BOX', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    coll = result["coll"]
    carrier = bpy.data.objects.get(coll["rka_curve_object"])
    carrier_ptr = carrier.as_pointer()
    _assert(spine_io.is_stack_carrier(carrier),
            "sanity: every segment is built on a MESH carrier now, got type=%r" % carrier.type)
    _assert(not [o for o in coll.objects if o.name.startswith(("curb_", "sidewalk_", "prop_"))],
            "sanity: a stack piece owns NO generated sibling objects, found %r"
            % [o.name for o in coll.objects])
    base_span = pp.span(coll)
    print("stack_live_edit: built a stack piece -- carrier is a MESH, zero sibling objects, "
          "spans %.3f..%.3f m" % base_span)

    # ------------------------------------------------------------------ dragging the spine. This
    # path never went through Python at all; it is asserted so a future rebuild that DOES touch
    # the carrier's vertices cannot silently break it.
    pts = spine_io.points(carrier)
    pts[-1].co = (160.0, 0.0, 0.0)
    opseg.rebuild_segment_gn_in_place(context, coll)
    coll = opint.local_collection(coll.name)
    _assert(abs(pp.length(coll) - 160.0) < TOL,
            "dragging the last spine point to x=160 should make the piece 160 m long, got %.3f"
            % pp.length(coll))
    marks = [o for o in coll.objects if o.name.startswith("mark_")]
    _assert(marks, "sanity: this piece should carry lane markings")
    mark_reach = max(s for (s, _l, _d) in pp.stations(coll, objects=marks))
    _assert(mark_reach > 120.0,
            "the lane markings must be rebuilt to the piece's NEW length -- they still stop at "
            "%.1f m on a %.1f m road (stale markings floating over half the road)"
            % (mark_reach, pp.length(coll)))
    print("stack_live_edit: dragging the spine carried the road AND its markings out to %.0f m"
          % pp.length(coll))

    # --------------------------------------------------------------------------- add a lane. THE
    # regression this file exists for: this reported {'FINISHED'} and moved nothing.
    _activate(context, coll)
    before = pp.span(coll)
    ret = bpy.ops.rka.adjust_segment_lanes(delta=1)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    after = pp.span(coll)
    _assert(abs((after[1] - before[1]) - LW) < TOL,
            "adding one forward lane must widen the piece by exactly one lane width (%.2f m) on "
            "that side: was %.3f..%.3f, now %.3f..%.3f -- if NOTHING moved, the rebuild bailed on "
            "the carrier type again" % (LW, before[0], before[1], after[0], after[1]))
    _assert(abs(after[0] - before[0]) < TOL,
            "adding a FORWARD lane must not move the backward side: %.3f -> %.3f"
            % (before[0], after[0]))
    print("stack_live_edit: +1 forward lane widened the piece by exactly %.2f m on that side only"
          % LW)

    # ------------------------------------------------------------------------------ taper the end
    _activate(context, coll)
    start_before, end_before = _end_extents(coll)
    _assert(abs(start_before - end_before) < TOL,
            "sanity: the piece should be constant-width before tapering (%.3f vs %.3f)"
            % (start_before, end_before))
    ret = bpy.ops.rka.adjust_segment_lanes_end(delta=2, backward=False)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes_end did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    start_after, end_after = _end_extents(coll)
    _assert(abs(start_after - start_before) < TOL,
            "an END-side taper must leave the START width alone: %.3f -> %.3f"
            % (start_before, start_after))
    # Expected widening comes from the piece's OWN recorded lane counts, not from the operator's
    # `delta`: `_effective_end_lanes` falls back to the start count when no end value is pinned
    # yet, so `delta` is not the number of lanes actually added. Asking the owner of the value
    # keeps this true whatever that fallback does.
    lanes_start = coll.get("rka_lanes")
    lanes_end_val = opseg._effective_end_lanes(coll, backward=False)
    expected = (lanes_end_val - lanes_start) * LW
    _assert(expected > 0.0,
            "sanity: the end should now carry more lanes than the start (%d vs %d)"
            % (lanes_end_val, lanes_start))
    _assert(abs((end_after - start_after) - expected) < TOL,
            "the end should be exactly %d - %d = %.2f m wider than the start, but the piece "
            "measures %.3f m at the start and %.3f m at the end. A single-station ProfileSet (the "
            "bug) would make these two equal."
            % (lanes_end_val, lanes_start, expected, start_after, end_after))
    print("stack_live_edit: an end-side taper made the end %.2f m wider than the start (%d vs %d "
          "lanes, start pinned at %.2f m) -- one piece, two stations, no Transition_* collection"
          % (expected, lanes_end_val, lanes_start, start_after))

    # ------------------------------------------------------------------------- widen the median
    _activate(context, coll)
    span_before = pp.span(coll)
    ret = bpy.ops.rka.adjust_median_width(delta=6.0)
    _assert(ret == {'FINISHED'}, "adjust_median_width did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    span_after = pp.span(coll)
    _assert(abs((span_after[1] - span_before[1]) - 3.0) < TOL
            and abs((span_before[0] - span_after[0]) - 3.0) < TOL,
            "a 6 m median must push BOTH carriageways out by half of it (3 m each): %r -> %r"
            % (span_before, span_after))
    print("stack_live_edit: a 6 m median pushed both carriageways out by 3 m each")

    # ------------------------------------------------------------------------ grow a sidewalk
    _activate(context, coll)
    raised_before = pp.raised_outer_edge(coll, 'L')
    ret = bpy.ops.rka.adjust_sidewalk_width(side='L', delta=3.0)
    _assert(ret == {'FINISHED'}, "adjust_sidewalk_width did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    _assert(pp.raised_outer_edge(coll, 'L') == raised_before,
            "width alone must build NO sidewalk -- the geometry comes from the resolved kit piece "
            "('no piece = no geometry', the convention curb and median PROFILE already follow)")
    # Picking the piece is what actually builds it.
    _activate(context, coll)
    ret = bpy.ops.rka.set_sidewalk_asset(side='L', collection_name='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, "set_sidewalk_asset did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    raised_after = pp.raised_outer_edge(coll, 'L')
    _assert(raised_after is not None and raised_after > raised_before + 1.0,
            "picking a sidewalk asset should carry raised geometry further out: %.3f -> %r"
            % (raised_before, raised_after))
    print("stack_live_edit: width alone built nothing; picking the kit piece carried the raised "
          "edge %.2f -> %.2f m" % (raised_before, raised_after))

    # -------------------------------------------------------------------- through all of that,
    # the carrier is the SAME object. This is what makes a live drag safe: a rebuild that deleted
    # and recreated the object a modal Transform is holding is the crash class the whole
    # update-in-place design exists to remove.
    carrier_after = bpy.data.objects.get(coll["rka_curve_object"])
    _assert(carrier_after is not None and carrier_after.as_pointer() == carrier_ptr,
            "the carrier must survive every edit by IDENTITY -- it was deleted and recreated")
    _assert(not [o for o in coll.objects if o.name.startswith(("curb_", "sidewalk_", "prop_"))],
            "after five edits the piece STILL owns no generated sibling objects, but found %r"
            % [o.name for o in coll.objects])
    print("stack_live_edit: the carrier survived all five edits by identity, still with zero "
          "sibling objects")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
