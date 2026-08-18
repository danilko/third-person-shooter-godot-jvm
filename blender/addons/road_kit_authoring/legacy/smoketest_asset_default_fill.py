#!/usr/bin/env python3
"""
smoketest_asset_default_fill.py -- headless verification for a confirmed real bug found against
`world_session.blend` (2026-08, user-reported: "the lamp/street lamp seem never show up... no
object is created into world_session even after click on set lamp in panel... but also no error").
Root cause: every panel "Asset"/"Set" button for a piece/field that had never had its own asset
name set forwarded a BLANK `collection_name`/`asset_collection` to its operator -- silently
building nothing (the existing, correct "ASSET style + unresolved piece = no geometry" convention
working exactly as designed, just against an input that was never real in the first place). This
was already fixed for Median Style (`panel._MEDIAN_ASSET_DEFAULT`, 2026-08 earlier) but the SAME
gap existed, unfixed, for Curb Style, Sidewalk Asset (segment + intersection), Prop Asset
(segment), and Traffic Light Asset (intersection) -- confirmed directly against
`Intersection_4WAY_001` in `world_session.blend`: `rka_curb_style == 'ASSET'` but
`rka_curb_asset_collection` had NEVER been set, so the curb wall silently built nothing at every
corner.

This test reproduces exactly what each panel control now does on a piece that has never used
that field before, and asserts REAL evaluated geometry results -- not just that the property gets
written. Curb/Median Style still compute a fallback default the first time their button-row
'Asset' is clicked (`panel._CURB_ASSET_DEFAULT`/`_MEDIAN_ASSET_DEFAULT`). Sidewalk/Prop/
Traffic-Light no longer need an equivalent -- 2026-08, user-requested ("is it possible to also do
drop down selection on asset or none"): those are now real dropdown pickers (`RKA_OT_pick_*`,
`linked_asset_picker_items`) that always list REAL linked pieces, so there's no "first click on a
blank field" case left to default around; this test picks one of those real choices directly,
same as a user would from the menu.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_asset_default_fill.py
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
import piece_probe as pp                                    # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _real_geometry(context, obj):
    deps = context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    me = eo.to_mesh()
    vcount = len(me.vertices)
    eo.to_mesh_clear()
    return vcount


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()

    # ============================================================== segment: Curb Style 'Profile'
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=1, lanes_backward=1,
        curb_l_style='NONE', curb_r_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    seg = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())
    _assert(not seg.get("rka_curb_asset_collection"), "sanity: no curb asset set yet")
    computed = seg.get("rka_curb_asset_collection", "") or panel._CURB_ASSET_DEFAULT
    _assert(computed == "Kit_Curb_JerseyBarrier_L2", "unexpected computed default: %r" % computed)
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = bpy.data.objects.get(seg.get("rka_curve_object"))
    ret = bpy.ops.rka.set_curb_style(side='L', style='PROFILE', asset_collection=computed)
    _assert(ret == {'FINISHED'}, ret)
    # "did the click build something real" is asked of the ROAD -- is anything now standing above
    # the road surface on the left -- rather than of an object named `curb_<piece>_L`, which only
    # exists on the sibling-object build path (`ROAD_KIT_REDESIGN.md` §7). The whole point of this
    # test is that the first click used to build SILENT NOTHING, and "nothing" is precisely what
    # `raised_span` returning None means.
    curb = pp.raised_span(seg, 'L')
    _assert(curb is not None,
            "clicking Curb Style 'Profile' for the first time must actually raise a Left curb -- "
            "nothing stands above the road (summary: %r)" % (pp.geometry_summary(seg),))
    print("smoketest_asset_default_fill: segment Curb Style 'Profile' first click builds real "
          "geometry, raised at %.2f..%.2f m from the spine (was silently nothing)" % curb)

    # =========================================================== intersection: Curb Style 'Profile'
    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    inter = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    _assert(not inter.get("rka_curb_asset_collection"), "sanity: no curb asset set yet")
    computed = inter.get("rka_curb_asset_collection", "") or panel._CURB_ASSET_DEFAULT
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = inter.objects.get("pad_%s" % inter.name)
    ret = bpy.ops.rka.set_curb_style(style='PROFILE', asset_collection=computed)
    _assert(ret == {'FINISHED'}, ret)
    curb_objs = [o for o in inter.objects if o.name.startswith("curb_%s_" % inter.name)]
    _assert(len(curb_objs) > 0, "clicking Curb Style 'Profile' for the first time on an "
            "intersection should build real curb corner objects, got 0")
    for o in curb_objs:
        _assert(_real_geometry(context, o) > 0, "'%s' must have real evaluated geometry" % o.name)
    print("smoketest_asset_default_fill: intersection Curb Style 'Profile' first click builds real "
          "geometry at every corner (%d corners)" % len(curb_objs))

    # ============================================================ intersection: Traffic Light Asset
    _assert(not inter.get("rka_traffic_light_asset_collection"), "sanity: no light asset set yet")
    ret = bpy.ops.rka.pick_intersection_traffic_light_asset(collection_name="Kit_TrafficLight_L1")
    _assert(ret == {'FINISHED'}, ret)
    _assert(inter.get("rka_traffic_light_asset_collection") == "Kit_TrafficLight_L1",
            "traffic light asset should now be set")
    # Picking a piece the FIRST time (no arm enabled yet) also auto-enables every arm -- see
    # RKA_OT_pick_intersection_traffic_light_asset's own docstring -- so no separate toggle needed.
    tl_objs = [o for o in inter.objects if o.name.startswith("trafficlight_")]
    _assert(len(tl_objs) == 1, "picking the asset piece (auto-enabling every arm) should build "
            "exactly one instancer object, got %d" % len(tl_objs))
    _assert(_real_geometry(context, tl_objs[0]) > 0,
            "the traffic light instancer must have real evaluated geometry")
    print("smoketest_asset_default_fill: intersection Traffic Light Asset dropdown pick + "
          "auto-enabled arms builds a real, visible prop -- the exact reported bug")

    # ================================================================= sidewalk + prop defaults
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = bpy.data.objects.get(seg.get("rka_curve_object"))
    _assert(not seg.get("rka_sidewalk_l_asset_collection"), "sanity: no sidewalk asset set yet")
    ret = bpy.ops.rka.adjust_sidewalk_width(side='L', delta=3.5)
    _assert(ret == {'FINISHED'}, ret)
    ret = bpy.ops.rka.pick_sidewalk_asset_l(collection_name="Kit_Curb_SidewalkTile_L2")
    _assert(ret == {'FINISHED'}, ret)
    # A sidewalk is raised geometry FURTHER OUT than the curb was on its own -- so the check is
    # that the left raised band now reaches past where the bare curb ended, not that an object
    # called `sidewalk_<piece>_L` appeared.
    sw = pp.raised_span(seg, 'L')
    _assert(sw is not None and sw[1] > curb[1] + 1.0,
            "picking a Sidewalk Asset should carry raised geometry out past the curb (which "
            "reached %.2f m); the left side now reaches %r" % (curb[1], sw))
    print("smoketest_asset_default_fill: segment Sidewalk Asset dropdown pick builds real "
          "geometry, reaching %.2f m from the spine (curb alone reached %.2f m)" % (sw[1], curb[1]))

    _assert(not seg.get("rka_prop_l_asset_collection"), "sanity: no prop asset set yet")
    ret = bpy.ops.rka.pick_prop_asset_l(collection_name="Kit_Curb_StreetLamp_L1")
    _assert(ret == {'FINISHED'}, ret)
    # A prop ROW is several separate lamps spread along the piece, so it is counted as blobs in
    # the sidewalk's lateral band -- a count that is the same whether each lamp is its own object
    # or a geometry-node instance inside the carrier.
    lamps = pp.clusters_along(seg, sw[0], sw[1] + 2.0, min_dz=1.0)
    _assert(lamps > 0,
            "picking a Prop Asset should build a real street-lamp row -- nothing stands more than "
            "1 m above the road in the sidewalk band %r (summary: %r)"
            % ((sw[0], sw[1] + 2.0), pp.geometry_summary(seg)))
    print("smoketest_asset_default_fill: segment Prop Asset dropdown pick builds a real street-lamp "
          "row (%d lamp(s) along the piece)" % lamps)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
