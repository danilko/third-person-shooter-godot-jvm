#!/usr/bin/env python3
"""
smoketest_curb_style_panel.py -- headless verification for `RKA_OT_set_curb_style` (2026-07-27,
user-reported: "the disable/enable of curb seem not work through panel"). Root cause: there was no
persistent panel control to change curb style on an ALREADY-BUILT segment/transition at all --
only the build operator's own F9 'Adjust Last Operation' panel, which Blender itself stops
applying the moment any other action runs. `RKA_OT_set_curb_style` is a standalone operator (now
wired into panel.py's Sidebar UI via `_draw_curb_style`) that sets `rka_curb_l_style`/
`rka_curb_r_style` on the target collection and rebuilds in place, independent of build history.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_curb_style_panel.py
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
import piece_probe as pp                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _colonly_objects(coll):
    return [o for o in coll.objects if o.name.endswith("-colonly")]


def _has_curb(coll, side):
    """Is there a curb on this side of the road?

    Asked of the GEOMETRY -- "does anything stand above the road surface on this side" -- not of an
    object called `curb_<piece>_<side>`. Per `ROAD_KIT_REDESIGN.md` §7: a curb is a curb whether it
    is a sibling Curve object or a `Curb<side>` modifier on the piece's carrier, and only the
    former has a name to look up."""
    return pp.raised_span(coll, side) is not None


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()   # needed for the PROFILE-style re-enable below

    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    coll = seg_result["coll"]
    _assert(coll.get("rka_curb_l_style", "BOX") == 'BOX', "should start Left=BOX")
    _assert(_has_curb(coll, "L"), "fresh BOX segment should have a Left curb (nothing is standing "
            "above the road on that side -- summary: %r)" % (pp.geometry_summary(coll),))
    _assert(_colonly_objects(coll) == [],
            "colonly proxies are export-time-only now -- a fresh build should have none live")

    # poll() must fail on a non-piece / non-GN-segment selection.
    context.view_layer.objects.active = None
    _assert(not bpy.ops.rka.set_curb_style.poll(), "poll should fail with nothing active")

    # Select something that resolves to the segment -- ANY of its objects does, per
    # `_live_edit_target_collection`'s own docs -- and disable the Left curb. Deliberately not the
    # curb object specifically: which objects a piece owns is what the stack migration changes.
    part = next(o for o in coll.objects
                if o.name != coll.get("rka_curve_object") and not o.name.endswith("-colonly"))
    context.view_layer.objects.active = part
    part.select_set(True)
    _assert(bpy.ops.rka.set_curb_style.poll(), "poll should succeed with a segment part active")
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='L', style='NONE')
    _assert(ret == {'FINISHED'}, "set_curb_style(NONE) did not finish: %s" % (ret,))
    _assert(coll.get("rka_curb_l_style") == 'NONE', "rka_curb_l_style should now be NONE")
    _assert(not _has_curb(coll, "L"),
            "nothing should stand above the road on the Left after style=NONE, found %r"
            % (pp.raised_span(coll, "L"),))
    _assert(_has_curb(coll, "R"), "the Right curb should be untouched by a Left-only change")
    print("smoketest_curb_style_panel: disabling the Left curb removed exactly that curb (nothing "
          "raised on the left, Right still at %r)" % (pp.raised_span(coll, "R"),))

    # Re-enable both sides via 'BOTH' and confirm no orphaned/duplicate objects accumulate.
    # (left_curb_obj no longer exists -- style=NONE just removed it -- so re-resolve to
    # something that survives, e.g. the still-present spine object.)
    context.view_layer.objects.active = coll.objects["spine_%s" % coll.name]
    # 'PROFILE' (not 'BOX'/'GUTTER' -- both removed 2026-08, see CURB_STYLE_ITEMS' docstring:
    # PROFILE supersedes both, sweeping the resolved kit piece's own real cross-section).
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='BOTH', style='PROFILE',
                                      asset_collection='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "set_curb_style(PROFILE, BOTH) did not finish: %s" % (ret,))
    _assert(coll.get("rka_curb_l_style") == 'PROFILE' and coll.get("rka_curb_r_style") == 'PROFILE',
            "both sides should now be PROFILE")
    _assert(_has_curb(coll, "L") and _has_curb(coll, "R"),
            "re-enabling both sides should raise a curb on each, got L=%r R=%r"
            % (pp.raised_span(coll, "L"), pp.raised_span(coll, "R")))
    _assert(_colonly_objects(coll) == [],
            "colonly proxies are export-time-only -- none should exist live after style changes")
    print("smoketest_curb_style_panel: re-enabling both sides (PROFILE) via one 'BOTH' call left "
          "no orphaned/duplicate curb objects")

    # Same operator must also work on a lane transition (the other GN spine-backed piece type).
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='PROFILE',
        curb_r_style='PROFILE', curb_asset_collection='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    context.view_layer.objects.active = tr_coll.objects["spine_%s" % tr_coll.name]
    _assert(bpy.ops.rka.set_curb_style.poll(), "poll should succeed on a lane-transition piece too")
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='R', style='NONE')
    _assert(ret == {'FINISHED'}, "set_curb_style on a transition did not finish: %s" % (ret,))
    _assert(tr_coll.get("rka_curb_r_style") == 'NONE', "transition's Right curb style should be NONE")
    print("smoketest_curb_style_panel: operator also works on a lane transition")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
