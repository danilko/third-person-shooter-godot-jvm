#!/usr/bin/env python3
"""
smoketest_end_side_adjust.py -- headless verification for `RKA_OT_adjust_segment_lanes_end`/
`RKA_OT_adjust_median_width_end` (2026-08, user-reported: "one port increase lane/one port
decrease lane, the overall mesh seem not change and reflect to do a transition"). Root cause:
there was NO live control for a segment's END-side lane count/median width at all -- only the
START side had adjust operators, so a segment could never actually become tapered after the
initial build. This also verifies the coupled fix in `_refresh_pavement_radius`: the OLD inline
radius-refresh in both start-side operators flattened the WHOLE spine to one uniform half-width
computed from the start side only, silently erasing any taper already in effect on the other end
every time either end was touched again.

RUN: blender --background --python addons/road_kit_authoring/smoketest_end_side_adjust.py
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

    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], lane_width=5.0, lanes=2,
        lanes_backward=2, curb_l_style='BOX', curb_r_style='BOX', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll = result["coll"]
    spine = coll.objects[coll["rka_curve_object"]]

    _assert(opseg._effective_end_lanes(coll, backward=False) == 2,
            "sanity: an untapered fresh build should report end==start (2)")
    _assert("rka_lanes_end" not in coll.keys(),
            "sanity: rka_lanes_end should not exist yet on an untapered piece")

    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = spine

    # --- the end-side operator must exist, poll, and write the END props, not the start ones.
    _assert(bpy.ops.rka.adjust_segment_lanes_end.poll(), "poll should succeed with the spine active")
    ret = bpy.ops.rka.adjust_segment_lanes_end('EXEC_DEFAULT', delta=2, backward=False)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes_end did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    _assert(coll.get("rka_lanes_end") == 4, "rka_lanes_end should now be 4, got %r" % coll.get("rka_lanes_end"))
    _assert(coll.get("rka_lanes") == 2, "the START-side rka_lanes must be UNTOUCHED, got %r" % coll.get("rka_lanes"))
    print("end_side_adjust smoketest: adjust_segment_lanes_end wrote rka_lanes_end (4), left "
          "rka_lanes (start) untouched at 2")

    # --- the pavement spine must now be genuinely TAPERED (start radius != end radius).
    spine = coll.objects[coll["rka_curve_object"]]
    r_start = spine.data.splines[0].points[0].radius
    r_end = spine.data.splines[0].points[-1].radius
    expected_start = max(2, 2) * 5.0   # lanes=2, lanes_backward=2 at start
    expected_end = max(4, 2) * 5.0     # lanes_end=4, lanes_backward_end falls back to 2
    _assert(abs(r_start - expected_start) < 1e-3, "start radius should be %.2f, got %.2f" % (expected_start, r_start))
    _assert(abs(r_end - expected_end) < 1e-3, "end radius should be %.2f, got %.2f" % (expected_end, r_end))
    print("end_side_adjust smoketest: pavement spine radius now tapers %.2f -> %.2f (start -> end)"
          % (r_start, r_end))

    # --- a SUBSEQUENT start-side adjust (a DIFFERENT direction) must NOT flatten the already-
    # established end-side forward taper -- the exact bug the old inline flatten logic had.
    ret = bpy.ops.rka.adjust_segment_lanes('EXEC_DEFAULT', delta=1, backward=True)
    _assert(ret == {'FINISHED'}, "adjust_segment_lanes (start, backward) did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    _assert(coll.get("rka_lanes_backward") == 3, "start backward should now be 3")
    _assert(opseg._effective_end_lanes(coll, backward=False) == 4,
            "the end-side FORWARD taper (4) must survive an unrelated start-side backward adjust")
    spine = coll.objects[coll["rka_curve_object"]]
    r_start2 = spine.data.splines[0].points[0].radius
    r_end2 = spine.data.splines[0].points[-1].radius
    expected_start2 = max(2, 3) * 5.0   # lanes=2 (fwd start, unchanged), lanes_backward=3 (new)
    expected_end2 = max(4, 2) * 5.0     # lanes_end=4 (unchanged), lanes_backward_end still 2
    _assert(abs(r_start2 - expected_start2) < 1e-3,
            "start radius after the backward-only adjust should be %.2f, got %.2f -- if this is "
            "%.2f instead, the old flatten-to-one-value bug regressed"
            % (expected_start2, r_start2, max(3, 3) * 5.0))
    _assert(abs(r_end2 - expected_end2) < 1e-3,
            "end radius should be UNCHANGED at %.2f (the taper must survive), got %.2f -- if "
            "this equals the start value, the taper was silently flattened away"
            % (expected_end2, r_end2))
    print("end_side_adjust smoketest: an unrelated start-side backward adjust preserved the "
          "existing end-side forward taper (%.2f -> %.2f), did not flatten it" % (r_start2, r_end2))

    # --- median end-side operator: same pattern.
    _assert(opseg._effective_end_median(coll) == 0.0, "sanity: median end should start at 0")
    ret = bpy.ops.rka.adjust_median_width_end('EXEC_DEFAULT', delta=3.0)
    _assert(ret == {'FINISHED'}, "adjust_median_width_end did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    _assert(coll.get("rka_median_width_end") == 3.0, "rka_median_width_end should now be 3.0")
    _assert(coll.get("rka_median_width", 0.0) == 0.0, "start-side median must be UNTOUCHED (0.0)")
    print("end_side_adjust smoketest: adjust_median_width_end wrote rka_median_width_end (3.0), "
          "left the start-side median untouched")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
