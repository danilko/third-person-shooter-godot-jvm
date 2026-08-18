#!/usr/bin/env python3
"""
smoketest_intersection_curb_sidewalk_panel.py -- headless verification for the persistent
intersection curb-style/sidewalk/traffic-light controls (2026-08, user-reported: "the
intersection seem not able to do these kind of curb/sidewalk setup, please update intersection to
allow similar setup as segment"). Confirms `RKA_OT_set_curb_style` (extended to intersections),
`RKA_OT_adjust_intersection_sidewalk_width`, `RKA_OT_set_intersection_sidewalk_asset`,
`RKA_OT_adjust_intersection_sidewalk_asset_spacing`, `RKA_OT_set_intersection_traffic_light_asset`,
`RKA_OT_toggle_arm_traffic_light`, and `RKA_OT_adjust_arm_traffic_light_radius` all work live on an
already-built intersection.

2026-08 follow-up (user-reported: sidewalks "result in strange half bake" at each arm's near end,
and "remove the lamp logic for intersection, but rather leave called 'traffic light'... the lamp
is per arm"): the old spaced prop-row (`RKA_OT_set_intersection_prop_asset`/
`RKA_OT_adjust_intersection_prop_spacing`) is GONE, replaced by a sidewalk-asset-piece option and a
per-arm traffic light. This file exercises the NEW surface only -- see git history for the old
prop-row version.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_intersection_curb_sidewalk_panel.py
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


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()
    _assert(bpy.data.collections.get("Kit_Curb_SidewalkTile_L2") is not None,
            "Kit_Curb_SidewalkTile_L2 should be linked -- run tools/build_curb_kit.py first")
    _assert(bpy.data.collections.get("Kit_TrafficLight_L1") is not None,
            "Kit_TrafficLight_L1 should be linked -- run tools/build_curb_kit.py first")

    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    coll = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    pad = coll.objects["pad_%s" % coll.name]
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = pad

    # --- RKA_OT_set_curb_style, extended to intersections. ('PROFILE', not 'BOX'/'GUTTER'/
    # 'ASSET' -- all three removed 2026-08, see CURB_STYLE_ITEMS' docstring.)
    ret = bpy.ops.rka.set_curb_style(style='PROFILE', asset_collection='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "set_curb_style on an intersection did not finish: %s" % (ret,))
    _assert(coll.get("rka_curb_style") == 'PROFILE', "rka_curb_style should now be PROFILE")
    print("smoketest_intersection_curb_sidewalk_panel: set_curb_style works live on an "
          "intersection (previously segment/transition only)")

    # --- RKA_OT_adjust_intersection_sidewalk_width -- 2026-08: sidewalk is PROFILE-only now (no
    # asset piece = no geometry, same convention curb/median already have), so widening alone
    # with no asset set yet must NOT build anything.
    _assert(coll.get("rka_sidewalk_width", 0.0) == 0.0, "should start with no sidewalk")
    ret = bpy.ops.rka.adjust_intersection_sidewalk_width(delta=3.5)
    _assert(ret == {'FINISHED'}, ret)
    _assert(coll.get("rka_sidewalk_width") == 3.5, "sidewalk width should now be 3.5")
    sw_objs = [o for o in coll.objects if o.name.startswith("sidewalk_")]
    _assert(len(sw_objs) == 0, "widening with no sidewalk asset piece set yet should build NO "
            "sidewalk geometry (PROFILE's 'no piece = no geometry' convention), got %d"
            % len(sw_objs))
    print("smoketest_intersection_curb_sidewalk_panel: widening with no sidewalk asset set yet "
          "correctly builds nothing (not a silent flat-box fallback)")

    # --- RKA_OT_set_intersection_sidewalk_asset -- picking a real piece is what actually builds
    # the strips.
    ret = bpy.ops.rka.set_intersection_sidewalk_asset(collection_name='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, ret)
    _assert(coll.get("rka_sidewalk_asset_collection") == 'Kit_Curb_SidewalkTile_L2',
            "rka_sidewalk_asset_collection should now be set")
    sw_objs = [o for o in coll.objects if o.name.startswith("sidewalk_")]
    # One strip PER CORNER (2026-08: sidewalks follow the SAME segmentation as the curb wall,
    # `build_junction_curb_segments`, not the old per-arm-per-side approximation) -- a 4-way has 4
    # real corners (N-E, E-S, S-W, W-N), none of which are through-pairs.
    _assert(len(sw_objs) == 4, "picking a sidewalk asset piece should build 4 strips (one per "
            "corner), got %d" % len(sw_objs))
    for sw in sw_objs:
        mod = sw.modifiers.get("Curb")
        _assert(mod is not None, "'%s' should carry curb_loop's own 'Curb' modifier once a "
                "sidewalk asset is set" % sw.name)
    print("smoketest_intersection_curb_sidewalk_panel: set_intersection_sidewalk_asset builds "
          "every strip as a real kit-piece PROFILE sweep")

    # Every sidewalk strip's near end must sit on the TRUE curb corner now (not the old
    # tail-length-based approximation) -- confirm each strip's evaluated mesh is real, non-empty
    # geometry (the concrete regression signature of the "half bake" bug: an empty/degenerate
    # near-end collapses the swept profile to near-zero footprint).
    deps = context.evaluated_depsgraph_get()
    for sw in sw_objs:
        eo = sw.evaluated_get(deps)
        me = eo.to_mesh()
        vcount = len(me.vertices)
        eo.to_mesh_clear()
        _assert(vcount > 0, "sidewalk strip '%s' should have real evaluated geometry, got %d "
                "vertices -- the 'half bake at start/end' regression" % (sw.name, vcount))
    print("smoketest_intersection_curb_sidewalk_panel: every sidewalk strip has real evaluated "
          "geometry (corner-flush near end, no half-bake)")

    ret = bpy.ops.rka.adjust_intersection_sidewalk_asset_spacing(delta=0.5)
    _assert(ret == {'FINISHED'}, ret)
    _assert(coll.get("rka_sidewalk_asset_spacing") == 2.5,
            "sidewalk asset spacing should be 2.0(default) + 0.5 = 2.5, got %s"
            % coll.get("rka_sidewalk_asset_spacing"))
    print("smoketest_intersection_curb_sidewalk_panel: adjust_intersection_sidewalk_asset_spacing "
          "still stores its value (2026-08: unused by PROFILE's continuous sweep, kept as a "
          "still-valid property for any direct caller)")

    ret = bpy.ops.rka.set_intersection_sidewalk_asset(collection_name='')
    _assert(ret == {'FINISHED'}, ret)
    sw_objs = [o for o in coll.objects if o.name.startswith("sidewalk_")]
    _assert(len(sw_objs) == 0,
            "clearing the sidewalk asset (no piece = no geometry) should remove every strip, "
            "got %d left" % len(sw_objs))
    print("smoketest_intersection_curb_sidewalk_panel: clearing the sidewalk asset removes every "
          "strip (no procedural fallback anymore)")

    ret = bpy.ops.rka.set_intersection_sidewalk_asset(collection_name='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, ret)
    sw_objs = [o for o in coll.objects if o.name.startswith("sidewalk_")]
    _assert(len(sw_objs) == 4, "re-picking the asset should rebuild 4 strips, got %d"
            % len(sw_objs))

    ret = bpy.ops.rka.adjust_intersection_sidewalk_width(delta=-3.5)
    _assert(ret == {'FINISHED'}, ret)
    _assert(coll.get("rka_sidewalk_width") == 0.0, "sidewalk width should be back to 0")
    sw_objs = [o for o in coll.objects if o.name.startswith("sidewalk_")]
    _assert(len(sw_objs) == 0, "shrinking to 0 should remove every sidewalk strip, got %d left"
            % len(sw_objs))
    print("smoketest_intersection_curb_sidewalk_panel: shrinking sidewalk width to 0 removes "
          "every strip")

    # --- Traffic light: intersection-level asset piece + per-arm enable/radius. Replaces the old
    # spaced prop-row entirely for intersections (2026-08, user-requested).
    arm_empties = [o for o in coll.objects if "rka_arm_name" in o.keys()]
    _assert(len(arm_empties) == 4, "4WAY should have 4 arm markers, got %d" % len(arm_empties))
    _assert(not any(o.get("rka_arm_traffic_light", False) for o in arm_empties),
            "sanity: no arm should have its light enabled yet")

    # 2026-08, user-reported ("traffic light not generate... even when set (no objects are
    # added)"): setting the asset piece the FIRST time (no arm enabled yet) now auto-enables
    # EVERY arm too (`RKA_OT_set_intersection_traffic_light_asset`) -- mirrors the "first click
    # also seeds a sensible default" convention every other asset picker in this addon already
    # uses, so "Set" alone is enough to see real geometry, not a silent two-step requirement.
    ret = bpy.ops.rka.set_intersection_traffic_light_asset(collection_name='Kit_TrafficLight_L1')
    _assert(ret == {'FINISHED'}, ret)
    _assert(coll.get("rka_traffic_light_asset_collection") == 'Kit_TrafficLight_L1',
            "rka_traffic_light_asset_collection should now be set")
    _assert(all(o.get("rka_arm_traffic_light", False) for o in arm_empties),
            "setting the asset piece the first time (no arm enabled yet) should auto-enable "
            "every arm's own light")
    tl_objs = [o for o in coll.objects if o.name.startswith("trafficlight_")]
    _assert(len(tl_objs) == 1, "auto-enabling every arm should build exactly one traffic-light "
            "instancer object (all lights share one GN instancer, one point per enabled arm), "
            "got %d" % len(tl_objs))
    tl = tl_objs[0]
    deps = context.evaluated_depsgraph_get()
    eo = tl.evaluated_get(deps)
    me = eo.to_mesh()
    vcount = len(me.vertices)
    eo.to_mesh_clear()
    _assert(vcount > 0, "the traffic light instancer must have real evaluated geometry once an "
            "arm is enabled, got %d vertices" % vcount)
    print("smoketest_intersection_curb_sidewalk_panel: set_intersection_traffic_light_asset alone "
          "auto-enables every arm and builds real, visible traffic-light props")

    one_arm = arm_empties[0]
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = one_arm
    _assert(bpy.ops.rka.toggle_arm_traffic_light.poll(), "poll should succeed with an arm active")

    # Re-setting the SAME asset piece again (e.g. re-clicking 'Set') must NOT re-fire the
    # auto-enable now that at least one arm is already on -- it should never override a
    # deliberately partial per-arm setup.
    ret = bpy.ops.rka.toggle_arm_traffic_light()   # turn this one arm back off by hand
    _assert(ret == {'FINISHED'}, ret)
    _assert(one_arm.get("rka_arm_traffic_light") is False, "this arm's light should be OFF")
    ret = bpy.ops.rka.set_intersection_traffic_light_asset(collection_name='Kit_TrafficLight_L1')
    _assert(ret == {'FINISHED'}, ret)
    _assert(one_arm.get("rka_arm_traffic_light") is False,
            "re-setting the asset piece must NOT re-auto-enable an arm the user turned off by "
            "hand -- at least one other arm is still on, so this is no longer the 'first set'")
    print("smoketest_intersection_curb_sidewalk_panel: re-setting the asset piece never "
          "overrides an already-partial per-arm enable state")

    # Per-arm radius adjust (on a still-enabled arm).
    other_arm = arm_empties[1]
    _assert(other_arm.get("rka_arm_traffic_light", False) is True,
            "sanity: this arm should still be enabled from the earlier auto-enable")
    cur_radius = other_arm.get("rka_arm_traffic_light_radius", 3.5)
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = other_arm
    ret = bpy.ops.rka.adjust_arm_traffic_light_radius(delta=1.0)
    _assert(ret == {'FINISHED'}, ret)
    _assert(abs(other_arm.get("rka_arm_traffic_light_radius", 0.0) - (cur_radius + 1.0)) < 1e-6,
            "this arm's traffic light radius should have grown by 1.0m")
    print("smoketest_intersection_curb_sidewalk_panel: adjust_arm_traffic_light_radius changes "
          "this arm's own offset")

    # Toggle every remaining enabled arm off -- the instancer object should be gone entirely
    # (0 points = no object, matching every other optional-geometry convention in this addon).
    for arm in arm_empties:
        if arm.get("rka_arm_traffic_light", False):
            for o in bpy.data.objects:
                o.select_set(False)
            context.view_layer.objects.active = arm
            ret = bpy.ops.rka.toggle_arm_traffic_light()
            _assert(ret == {'FINISHED'}, ret)
    tl_objs = [o for o in coll.objects if o.name.startswith("trafficlight_")]
    _assert(len(tl_objs) == 0, "toggling every enabled arm back off should remove the instancer "
            "object entirely, got %d left" % len(tl_objs))
    print("smoketest_intersection_curb_sidewalk_panel: toggling every arm back off removes the "
          "traffic-light object entirely")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
