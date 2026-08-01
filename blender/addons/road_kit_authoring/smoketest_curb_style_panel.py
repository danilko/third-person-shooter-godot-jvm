#!/usr/bin/env python3
"""
smoketest_curb_style_panel.py -- headless verification for `RKA_OT_set_curb_style` (2026-07-27,
user-reported: "the disable/enable of curb seem not work through panel"). Root cause: there was no
persistent panel control to change curb style on an ALREADY-BUILT segment/transition at all --
only the build operator's own F9 'Adjust Last Operation' panel, which Blender itself stops
applying the moment any other action runs. `RKA_OT_set_curb_style` is a standalone operator (now
wired into panel.py's Sidebar UI via `_draw_curb_style`) that sets `rka_curb_l_style`/
`rka_curb_r_style` on the target collection and rebuilds in place, independent of build history.

RUN: blender --background --python addons/road_kit_authoring/smoketest_curb_style_panel.py
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


def _colonly_objects(coll):
    return [o for o in coll.objects if o.name.endswith("-colonly")]


def _curb_objs(coll, side):
    # Exact-match the VISUAL curb object only ("curb_<coll>_<side>") -- a startswith would also
    # catch its own "-colonly" collision sibling ("curb_<coll>_<side>-colonly").
    name = "curb_%s_%s" % (coll.name, side)
    return [o for o in coll.objects if o.name == name]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    coll = seg_result["coll"]
    _assert(coll.get("rka_curb_l_style", "BOX") == 'BOX', "should start Left=BOX")
    _assert(len(_curb_objs(coll, "L")) == 1, "fresh BOX segment should have a Left curb object")
    pave_before = [o for o in _colonly_objects(coll) if o.name.startswith("pave_")]
    _assert(len(pave_before) == 1, "fresh segment should have exactly 1 pavement colonly")

    # poll() must fail on a non-piece / non-GN-segment selection.
    context.view_layer.objects.active = None
    _assert(not bpy.ops.rka.set_curb_style.poll(), "poll should fail with nothing active")

    # Select something that resolves to the segment (a curb object, per
    # _live_edit_target_collection's own docs) and disable the Left curb.
    left_curb_obj = _curb_objs(coll, "L")[0]
    context.view_layer.objects.active = left_curb_obj
    left_curb_obj.select_set(True)
    _assert(bpy.ops.rka.set_curb_style.poll(), "poll should succeed with a segment part active")
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='L', style='NONE')
    _assert(ret == {'FINISHED'}, "set_curb_style(NONE) did not finish: %s" % (ret,))
    _assert(coll.get("rka_curb_l_style") == 'NONE', "rka_curb_l_style should now be NONE")
    _assert(len(_curb_objs(coll, "L")) == 0, "Left curb object should be gone after style=NONE")
    _assert(len(_curb_objs(coll, "R")) == 1, "Right curb should be untouched by a Left-only change")
    pave_after_none = [o for o in _colonly_objects(coll) if o.name.startswith("pave_")]
    _assert(len(pave_after_none) == 1, "pavement colonly must survive a curb-style change "
            "(it's independent of curb style) -- got %d" % len(pave_after_none))
    print("smoketest_curb_style_panel: disabling the Left curb via the operator removed exactly "
          "that curb object, left the Right curb + pavement collision untouched")

    # Re-enable both sides via 'BOTH' and confirm no orphaned/duplicate objects accumulate.
    # (left_curb_obj no longer exists -- style=NONE just removed it -- so re-resolve to
    # something that survives, e.g. the still-present spine object.)
    context.view_layer.objects.active = coll.objects["spine_%s" % coll.name]
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='BOTH', style='GUTTER')
    _assert(ret == {'FINISHED'}, "set_curb_style(GUTTER, BOTH) did not finish: %s" % (ret,))
    _assert(coll.get("rka_curb_l_style") == 'GUTTER' and coll.get("rka_curb_r_style") == 'GUTTER',
            "both sides should now be GUTTER")
    _assert(len(_curb_objs(coll, "L")) == 1 and len(_curb_objs(coll, "R")) == 1,
            "re-enabling both sides should produce exactly one curb object each, got L=%d R=%d"
            % (len(_curb_objs(coll, "L")), len(_curb_objs(coll, "R"))))
    colonly_final = _colonly_objects(coll)
    pave_final = [o for o in colonly_final if o.name.startswith("pave_")]
    _assert(len(pave_final) == 1, "still exactly one pavement colonly after two style changes, "
            "got %d (orphan/duplicate check)" % len(pave_final))
    _assert(len(colonly_final) == 3, "expect exactly 3 colonlies (curb L + curb R + pavement) "
            "after settling on GUTTER/GUTTER, got %d" % len(colonly_final))
    print("smoketest_curb_style_panel: re-enabling both sides (GUTTER) via one 'BOTH' call left "
          "no orphaned/duplicate curb or pavement colonly objects")

    # Same operator must also work on a lane transition (the other GN spine-backed piece type).
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='BOX', curb_r_style='BOX')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    context.view_layer.objects.active = next(o for o in tr_coll.objects if o.name.startswith("curb_"))
    _assert(bpy.ops.rka.set_curb_style.poll(), "poll should succeed on a lane-transition piece too")
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='R', style='NONE')
    _assert(ret == {'FINISHED'}, "set_curb_style on a transition did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_curb_r_style") == 'NONE', "transition's Right curb style should be NONE")
    print("smoketest_curb_style_panel: operator also works on a lane transition")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
