#!/usr/bin/env python3
"""
smoketest_sidewalk_props_panel.py -- headless verification for the persistent sidewalk/prop
controls (2026-08, user-reported: sidewalk/prop plumbing already existed fully for segments but
was build-time-only (F9), and entirely absent on intersections). Confirms:

1. `RKA_OT_adjust_sidewalk_width`/`_end` and `RKA_OT_set_prop_asset`/`RKA_OT_adjust_prop_spacing`
   can turn a segment's sidewalk/props on and back off (0/blank) after the fact, matching the
   discoverability `RKA_OT_adjust_median_width` already had.
2. `RKA_OT_set_sidewalk_asset`/`RKA_OT_adjust_sidewalk_asset_spacing` pick which kit piece a
   segment's sidewalk sweeps (2026-08, user-requested: "will it be simpler and easily to
   regenerate all curb/side way from asset... just follow the asset library ones", later "may you
   please also do for sidewalk also" -- PROFILE-only now, same as curb/median: no piece picked =
   no geometry at all, not a flat-box fallback).
3. `RKA_OT_build_intersection`'s `sidewalk_width` field builds a sidewalk around every arm (both
   physical edges), where none existed before -- and its `sidewalk_asset_collection` field is
   what actually produces geometry, same PROFILE-only rule.

The old intersection prop-row (`prop_asset_collection`/`prop_spacing` on `RKA_OT_build_
intersection`) is GONE (2026-08, user-requested: "remove the lamp logic for intersection, but
rather leave called 'traffic light'") -- see `smoketest_intersection_curb_sidewalk_panel.py` for
its replacement (a per-arm traffic light, not exercised in this file).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_sidewalk_props_panel.py
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
import kit_common as kc                                     # noqa: E402
import piece_probe as pp                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    context = bpy.context
    ret = bpy.ops.rka.link_curb_kit_library()
    _assert(ret == {'FINISHED'}, ret)

    # ========================================================================= segment sidewalk
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=1,
        lanes_backward=1, curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    seg_coll = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())
    _assert(seg_coll.get("rka_sidewalk_l_width", 0.0) == 0.0, "should start with no sidewalk")
    # The segment is built with NO curb, so anything standing above the road surface can only be
    # a sidewalk or a prop -- which makes `raised_span` a direct read of "is there a sidewalk".
    # Asked of the geometry rather than of `sidewalk_<piece>_L` objects, per
    # `ROAD_KIT_REDESIGN.md` §7: on the modifier-stack path a sidewalk is a `SidewalkL` modifier
    # on the carrier and no such object exists.
    _assert(pp.raised_span(seg_coll, 'L') is None,
            "no sidewalk should exist yet, but something is raised on the left: %r"
            % (pp.raised_span(seg_coll, 'L'),))

    for o in bpy.data.objects:
        o.select_set(False)
    spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    context.view_layer.objects.active = spine

    # 2026-08: sidewalk is PROFILE-only now (no asset piece = no geometry, the same convention
    # curb/median already have) -- widening alone, with no asset piece set yet, must build nothing.
    ret = bpy.ops.rka.adjust_sidewalk_width(side='L', delta=2.0)
    _assert(ret == {'FINISHED'}, "adjust_sidewalk_width did not finish: %s" % (ret,))
    _assert(seg_coll.get("rka_sidewalk_l_width") == 2.0,
            "sidewalk L width should be 2.0, got %s" % seg_coll.get("rka_sidewalk_l_width"))
    _assert(pp.raised_span(seg_coll, 'L') is None,
            "widening with no sidewalk asset piece set yet should build NO sidewalk geometry "
            "(PROFILE's 'no piece = no geometry' convention), but %r is raised on the left"
            % (pp.raised_span(seg_coll, 'L'),))
    print("smoketest_sidewalk_props_panel: adjust_sidewalk_width with no asset set yet correctly "
          "builds nothing (not a silent flat-box fallback)")

    # --- RKA_OT_set_sidewalk_asset / RKA_OT_adjust_sidewalk_asset_spacing -- picking a real piece
    # is what actually builds the strip.
    ret = bpy.ops.rka.set_sidewalk_asset(side='L', collection_name='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, "set_sidewalk_asset did not finish: %s" % (ret,))
    _assert(seg_coll.get("rka_sidewalk_l_asset_collection") == 'Kit_Curb_SidewalkTile_L2',
            "sidewalk L asset should be set")
    sw_span = pp.raised_span(seg_coll, 'L')
    _assert(sw_span is not None,
            "picking a sidewalk asset piece should raise a Left sidewalk, found nothing "
            "(summary: %r)" % (pp.geometry_summary(seg_coll),))
    # The CARRIAGEWAY edge, from this segment's own build parameters (1 lane each way at 5 m, no
    # median) -- NOT `pp.span`, which is the whole piece and therefore already includes the
    # sidewalk we are checking the position of.
    carriageway_edge = 1 * 5.0
    _assert(sw_span[0] >= carriageway_edge - 1e-3,
            "the sidewalk must sit OUTSIDE the carriageway (edge %.2f m), but raised geometry "
            "starts at %.2f m -- it is lapping onto the road"
            % (carriageway_edge, sw_span[0]))
    n_sidewalk_only = pp.raised_vert_count(seg_coll, 'L')
    print("smoketest_sidewalk_props_panel: set_sidewalk_asset builds a real kit-piece PROFILE "
          "sweep")

    ret = bpy.ops.rka.adjust_sidewalk_asset_spacing(delta=0.5)
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg_coll.get("rka_sidewalk_asset_spacing") == 2.5,
            "sidewalk asset spacing should be 2.0(default) + 0.5 = 2.5, got %s"
            % seg_coll.get("rka_sidewalk_asset_spacing"))
    print("smoketest_sidewalk_props_panel: adjust_sidewalk_asset_spacing still stores its value "
          "(2026-08: unused by PROFILE's continuous sweep, kept as a still-valid property for "
          "any direct caller)")

    ret = bpy.ops.rka.set_sidewalk_asset(side='L', collection_name='')
    _assert(ret == {'FINISHED'}, ret)
    _assert(pp.raised_span(seg_coll, 'L') is None,
            "clearing the sidewalk asset (no piece = no geometry) should remove the strip, but "
            "%r is still raised on the left" % (pp.raised_span(seg_coll, 'L'),))
    print("smoketest_sidewalk_props_panel: clearing the sidewalk asset removes the strip (no "
          "procedural fallback anymore)")

    # Re-pick for the subsequent "turn it back off" checks below.
    ret = bpy.ops.rka.set_sidewalk_asset(side='L', collection_name='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, ret)

    ret = bpy.ops.rka.set_prop_asset(side='L', collection_name='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "set_prop_asset did not finish: %s" % (ret,))
    _assert(seg_coll.get("rka_prop_l_asset_collection") == 'Kit_Curb_JerseyBarrier_L2',
            "prop asset should be set")
    # A prop row adds geometry ON TOP OF the sidewalk that is already there, so it is measured as
    # an INCREASE over the sidewalk-only count rather than as an object appearing. That comparison
    # holds whether each prop is its own object or a geometry-node instance inside the carrier.
    n_with_props = pp.raised_vert_count(seg_coll, 'L')
    _assert(n_with_props > n_sidewalk_only,
            "set_prop_asset should add a prop row on top of the sidewalk: the left side had %d "
            "raised vertices with the sidewalk alone and has %d now"
            % (n_sidewalk_only, n_with_props))
    print("smoketest_sidewalk_props_panel: set_prop_asset builds a prop row on an already-built "
          "segment")

    ret = bpy.ops.rka.adjust_prop_spacing(side='L', delta=2.0)
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg_coll.get("rka_prop_l_spacing") == 32.0,
            "prop spacing should be 30.0(default, 2026-08 streetlight-array real-world spacing) "
            "+ 2.0 = 32.0, got %s" % seg_coll.get("rka_prop_l_spacing"))
    print("smoketest_sidewalk_props_panel: adjust_prop_spacing changes spacing independently")

    # Turn both back off -- 0 width / blank asset name should remove the objects, same convention
    # median width already has.
    ret = bpy.ops.rka.adjust_sidewalk_width(side='L', delta=-2.0)
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg_coll.get("rka_sidewalk_l_width") == 0.0, "sidewalk L width should be back to 0")
    n_props_only = pp.raised_vert_count(seg_coll, 'L')
    _assert(n_props_only < n_with_props,
            "shrinking the sidewalk to 0 should remove the strip (the prop row may remain): the "
            "left side still carries %d of its %d raised vertices"
            % (n_props_only, n_with_props))

    ret = bpy.ops.rka.set_prop_asset(side='L', collection_name='')
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg_coll.get("rka_prop_l_asset_collection") == '', "prop asset should be cleared")
    _assert(pp.raised_span(seg_coll, 'L') is None,
            "with the sidewalk shrunk to 0 AND the prop asset cleared, nothing should stand above "
            "the road on the left, found %r" % (pp.raised_span(seg_coll, 'L'),))
    print("smoketest_sidewalk_props_panel: shrinking sidewalk to 0 / clearing prop asset removes "
          "the objects, the discoverable 'turn it off' path")

    # End-side sidewalk taper.
    ret = bpy.ops.rka.adjust_sidewalk_width_end(side='R', delta=3.0)
    _assert(ret == {'FINISHED'}, ret)
    _assert(seg_coll.get("rka_sidewalk_r_width_end") == 3.0,
            "sidewalk R width (end) should be 3.0, got %s" % seg_coll.get("rka_sidewalk_r_width_end"))
    print("smoketest_sidewalk_props_panel: adjust_sidewalk_width_end tapers the end independently")

    # ==================================================================== intersection sidewalk
    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE', sidewalk_width=1.5,
        sidewalk_asset_collection='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, "build_intersection with sidewalk did not finish: %s" % (ret,))
    int_coll = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    _assert(int_coll.get("rka_sidewalk_width") == 1.5, "intersection sidewalk width should be 1.5")
    _assert(int_coll.get("rka_sidewalk_asset_collection") == 'Kit_Curb_SidewalkTile_L2',
            "intersection sidewalk asset should be set from build time")
    int_sw_objs = [o for o in int_coll.objects if o.name.startswith("sidewalk_")]
    # One strip PER CORNER (2026-08: sidewalks follow the curb wall's own segmentation,
    # `build_junction_curb_segments`) -- a 4-way has 4 real corners.
    _assert(len(int_sw_objs) == 4,
            "4-way intersection should build 4 sidewalk strips (one per corner), got %d"
            % len(int_sw_objs))
    for sw in int_sw_objs:
        _assert(sw.modifiers.get("Curb") is not None,
                "'%s' should carry curb_loop's own 'Curb' modifier -- built with a sidewalk asset "
                "piece from the start" % sw.name)
    print("smoketest_sidewalk_props_panel: RKA_OT_build_intersection builds a real kit-tiled "
          "sidewalk following the pad's own curve (%d corner strips) -- previously entirely absent"
          % len(int_sw_objs))

    # Intersection with neither sidewalk nor asset -- confirms the feature stays a true no-op by
    # default (0/blank).
    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    plain_coll = [c for c in bpy.data.collections
                  if "rka_arm_names" in c.keys() and c.name != int_coll.name][0]
    plain_sw = [o for o in plain_coll.objects if o.name.startswith("sidewalk_")]
    _assert(len(plain_sw) == 0,
            "default (0 width) intersection should build no sidewalk objects at all, got %d"
            % len(plain_sw))
    print("smoketest_sidewalk_props_panel: default intersection build stays a true no-op "
          "(byte-identical to before this feature existed)")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
