#!/usr/bin/env python3
"""
smoketest_median_single.py -- headless verification for the median style system (2026-08,
user-reported: "the current median of road is still two curbs on each way internal lane... allow
to replace to single yellow separator or single separator mesh object" -- then, once built,
user-requested: "median should always be single, but just the mesh + distance between... remove
all choice and just load from asset too", then later "only have none/profile... to simplify the
code base" -- collapsing an earlier BOX/GUTTER/ASSET-dual/SINGLE-procedural/profile-silhouette/
discrete-ASSET set this session had grown through, down to just NONE and PROFILE).

Confirms: linking the curb kit library exposes 'Kit_Median_YellowSeparator'/'Kit_Median_Island'
(`tools/build_curb_kit.py`), setting Median Style to 'Profile' builds EXACTLY ONE
`curb_<name>_median` object (not the `_A`/`_B` pair every prior style built) swept continuously
along the segment's own spine centerline, `RKA_OT_set_median_style` can switch a built segment
between 'Profile' and 'None' live with correct object cleanup either way, and the panel's "first
click on a never-configured piece" default-fill fix still works with the simplified 2-style enum.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_median_single.py
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
from road_kit_authoring import panel                        # noqa: E402
import kit_common as kc                                     # noqa: E402
import piece_probe as pp  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _median_count(coll):
    """How many MEDIANS this piece has, counted across both carrier kinds.

    A sibling-object piece expresses its median as a `curb_<piece>_median` object; a
    modifier-stack piece as a `Median` LAYER on its single carrier (`ROAD_KIT_REDESIGN.md` §7 --
    there is no object to count there). The question this test asks -- "exactly ONE median, not the
    old per-side `_A`/`_B` pair" -- is the same either way, so it is asked of both."""
    n = len([o for o in coll.objects
             if o.name.startswith("curb_%s_median" % coll.name)
             and not o.name.endswith("-colonly")])
    for o in coll.objects:
        n += len([m for m in o.modifiers if m.type == 'NODES' and m.name == "Median"])
    return n


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    context = bpy.context

    ret = bpy.ops.rka.link_curb_kit_library()
    _assert(ret == {'FINISHED'}, "link_curb_kit_library did not finish: %s" % (ret,))
    _assert(bpy.data.collections.get("Kit_Median_YellowSeparator") is not None,
            "Kit_Median_YellowSeparator should be linked -- run tools/build_curb_kit.py first")
    _assert(bpy.data.collections.get("Kit_Median_Island") is not None,
            "Kit_Median_Island should be linked -- run tools/build_curb_kit.py first")
    print("smoketest_median_single: curb kit library linked, both median pieces present")

    # Default (no median_style given) should be 'NONE' -- fully back-compatible.
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=2,
        lanes_backward=2, median_width=6.0, curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    seg_coll = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())
    _assert(seg_coll.get("rka_median_style", "NONE") in ("NONE", None),
            "default median_style should be NONE, got %s" % seg_coll.get("rka_median_style"))
    _assert(_median_count(seg_coll) == 0, "NONE style should build no median at all")
    print("smoketest_median_single: default (NONE) style builds no median object")

    # Build with median_style='PROFILE' from the start.
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=2,
        lanes_backward=2, median_width=6.0, median_style='PROFILE',
        median_asset_collection='Kit_Median_YellowSeparator', median_asset_spacing=2.0,
        curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, "build_straight_segment (ASSET median) did not finish: %s" % (ret,))
    seg2 = [c for c in bpy.data.collections if "rka_curve_object" in c.keys()
            and c.name != seg_coll.name][0]
    _assert(seg2.get("rka_median_style") == 'PROFILE',
            "rka_median_style should be PROFILE, got %s" % seg2.get("rka_median_style"))

    _assert(_median_count(seg2) == 1,
            "PROFILE should build exactly ONE median (not the old _A/_B pair), got %d"
            % _median_count(seg2))
    print("smoketest_median_single: PROFILE builds exactly one median, swept continuously")

    # Live switch: PROFILE -> NONE via the persistent panel operator -- should clean up the object.
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = bpy.data.objects.get(seg2.get("rka_curve_object"))
    ret = bpy.ops.rka.set_median_style(style='NONE')
    _assert(ret == {'FINISHED'}, "set_median_style (-> NONE) did not finish: %s" % (ret,))
    _assert(seg2.get("rka_median_style") == 'NONE', "rka_median_style should now be NONE")
    _assert(_median_count(seg2) == 0, "NONE style should leave no median at all, got %d"
            % _median_count(seg2))
    print("smoketest_median_single: live switch PROFILE -> NONE cleans the median away")

    # And back again: NONE -> PROFILE (with a different kit piece).
    spine2 = bpy.data.objects.get(seg2.get("rka_curve_object"))
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = spine2
    ret = bpy.ops.rka.set_median_style(style='PROFILE', asset_collection='Kit_Median_Island')
    _assert(ret == {'FINISHED'}, "set_median_style (-> PROFILE) did not finish: %s" % (ret,))
    _assert(seg2.get("rka_median_style") == 'PROFILE', "rka_median_style should be PROFILE again")
    _assert(seg2.get("rka_median_asset_collection") == 'Kit_Median_Island',
            "rka_median_asset_collection should now be Kit_Median_Island, got %s"
            % seg2.get("rka_median_asset_collection"))
    _assert(_median_count(seg2) == 1,
            "switching back to PROFILE should leave exactly 1 median again, got %d"
            % _median_count(seg2))
    print("smoketest_median_single: live switch NONE -> PROFILE (with a different kit piece) "
          "round-trips cleanly, exactly 1 object again")

    # Shrinking the median to 0 removes the object entirely (same "0 = off" convention as
    # every other median style already has).
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = bpy.data.objects.get(seg2.get("rka_curve_object"))
    ret = bpy.ops.rka.adjust_median_width(delta=-6.0)
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg2.get("rka_median_width") == 0.0, "median width should be 0 now")
    _assert(_median_count(seg2) == 0,
            "shrinking median width to 0 should remove the median too, got %d left"
            % _median_count(seg2))
    print("smoketest_median_single: shrinking median width to 0 removes the object")

    # ============================================ regression: first-time click on the panel button
    # 2026-08, user-reported: "still draw parallel meshes instead of one at center." Root cause: a
    # segment built with the default median_style (NONE) never had `rka_median_asset_collection`
    # set, so clicking the panel's 'Asset' button (which used to forward that blank value verbatim)
    # silently built NOTHING at all -- easy to read as "the style switch had no effect."
    # `_draw_median_style` now falls back to a real default piece (`panel._MEDIAN_ASSET_DEFAULT`)
    # whenever none is set yet -- this reproduces that exact first-click scenario.
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=2,
        lanes_backward=2, median_width=6.0, curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    fresh_coll = [c for c in bpy.data.collections if "rka_curve_object" in c.keys()
                  and c.name not in (seg_coll.name, seg2.name)][0]
    _assert(not fresh_coll.get("rka_median_asset_collection"),
            "sanity check: a freshly-built segment should have no median asset set yet")

    # Exactly what _draw_median_style's 'Asset' button now computes and passes.
    cur_asset = fresh_coll.get("rka_median_asset_collection", "")
    computed = cur_asset or panel._MEDIAN_ASSET_DEFAULT
    _assert(computed == "Kit_Median_YellowSeparator",
            "panel should default an unset median asset to Kit_Median_YellowSeparator on first "
            "click of 'Asset', got %r" % computed)

    for o in bpy.data.objects:
        o.select_set(False)
    fresh_spine = bpy.data.objects.get(fresh_coll.get("rka_curve_object"))
    context.view_layer.objects.active = fresh_spine
    ret = bpy.ops.rka.set_median_style(style='PROFILE', asset_collection=computed)
    _assert(ret == {'FINISHED'}, ret)
    _assert(fresh_coll.get("rka_median_asset_collection") == "Kit_Median_YellowSeparator",
            "median asset collection should now be set from the panel's computed default")
    fresh_median_n = _median_count(fresh_coll)
    _assert(fresh_median_n == 1,
            "clicking 'Profile' for the FIRST time (no prior asset set) should build exactly 1 "
            "real median object, got %d -- the exact bug this regression test guards against"
            % fresh_median_n)
    # "It built something REAL", asked of the piece's own geometry rather than of one named
    # object's evaluated mesh -- the whole point of this regression test is that the first click
    # used to build silent nothing, and `span` returning None is exactly what nothing looks like.
    _assert(pp.span(fresh_coll) is not None,
            "the median built on first click must produce real, non-empty geometry (summary: %r)"
            % (pp.geometry_summary(fresh_coll),))
    print("smoketest_median_single: clicking 'Profile' for the first time (no prior asset ever "
          "set) now builds real, visible geometry instead of silently doing nothing")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
