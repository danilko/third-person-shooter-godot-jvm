#!/usr/bin/env python3
"""
smoketest_boundary_sweep.py -- a part that is edited away must LEAVE, and a part that is edited
back must not arrive twice.

WHAT CHANGED, AND WHY (2026-08-13, `ROAD_KIT_REDESIGN.md` §7). This test used to assert the
*mechanism*: that `ops_intersection.sweep_untouched_boundaries` removed an object named
`curb_<piece>_median`, and that `set_curb_style` left exactly one object named `curb_<piece>_L`
rather than a Blender-auto-suffixed `.001` twin. Both statements are about the sibling-object
build path -- Python-owned mesh objects with hand-managed lifetimes -- and both become
meaningless under the modifier-stack path, where the median and the curb are MODIFIERS on a single
carrier and there is no object to orphan in the first place. A test that fails when the road is
still correct is a test that blocks the migration, which is exactly what 19 of these did.

So it now asserts what a user would actually notice, in terms both build paths satisfy:

  * a median removed CLOSES THE GAP between the carriageways -- the piece's lateral span shrinks by
    exactly the median width, because the median *is* that gap;
  * a curb added RAISES GEOMETRY at the paved edge, and removed leaves nothing above the surface;
  * re-applying the same curb style does not accumulate a second copy of it (the invariant form of
    "no stray `.001` duplicate" -- a duplicate is invisible to a span check but doubles the raised
    vertex count).

Measurement is `lib/piece_probe.py`, which reads EVALUATED geometry against the piece's own spine,
so nothing here names a generated object.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_boundary_sweep.py
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
import piece_probe as pp                                    # noqa: E402

TOL = 1e-3
LANE_W = 5.0
MEDIAN_W = 4.0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _activate(context, obj):
    for o in bpy.data.objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()

    # ------------------------------------------------------------------ removing a median closes
    # the gap it held open. A median is not a decoration sitting on the road -- it is the distance
    # between the two carriageways, so a median that is edited to 0 and does not close that gap has
    # been left behind, whether it survives as an orphaned object or as a modifier producing
    # nothing.
    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], lane_width=LANE_W, lanes=1,
        lanes_backward=1, curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="",
        median_width=MEDIAN_W, median_style='PROFILE',
        median_asset_collection='Kit_Median_YellowSeparator')
    coll = result["coll"]
    span_before = pp.span(coll)
    _assert(span_before is not None, "the piece evaluated to no geometry at all")
    expect = LANE_W + MEDIAN_W / 2.0
    _assert(abs(span_before[1] - expect) < TOL and abs(span_before[0] + expect) < TOL,
            "sanity: a 1+1 lane road with a %.1f m median should span +-%.3f m, got %r"
            % (MEDIAN_W, expect, span_before))

    _activate(context, bpy.data.objects.get(coll["rka_curve_object"]))
    ret = bpy.ops.rka.adjust_median_width(delta=-10.0)   # clamps to 0
    _assert(ret == {'FINISHED'}, "adjust_median_width did not finish: %s" % (ret,))
    coll = opint.local_collection(coll.name)
    span_after = pp.span(coll)
    _assert(abs(span_after[1] - LANE_W) < TOL and abs(span_after[0] + LANE_W) < TOL,
            "median_width -> 0 must close the gap between the carriageways: the piece should now "
            "span +-%.3f m, got %r (summary: %r)"
            % (LANE_W, span_after, pp.geometry_summary(coll)))
    _assert(abs((span_before[1] - span_after[1]) - MEDIAN_W / 2.0) < TOL,
            "each carriageway should have moved inward by exactly half the median (%.3f m), "
            "moved %.3f" % (MEDIAN_W / 2.0, span_before[1] - span_after[1]))
    print("boundary_sweep smoketest: removing a %.1f m median closed the gap exactly -- piece span "
          "+-%.2f -> +-%.2f m, nothing left holding the carriageways apart"
          % (MEDIAN_W, span_before[1], span_after[1]))

    # ------------------------------------------------------------------------ curb style switch
    # NONE -> PROFILE -> NONE. A real box mesh is needed as the asset, not a degenerate flat
    # triangle -- `extract_cross_section_profile` bisects at the piece's own local-X midpoint and
    # requires a closed loop of >= 3 cut-edge vertices.
    asset_mesh = bpy.data.meshes.new("SweepTestAssetMesh")
    asset_mesh.from_pydata(
        [(0, -0.1, 0.0), (2, -0.1, 0.0), (2, 0.1, 0.0), (0, 0.1, 0.0),
         (0, -0.1, 0.3), (2, -0.1, 0.3), (2, 0.1, 0.3), (0, 0.1, 0.3)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    asset_obj = bpy.data.objects.new("SweepTestAsset", asset_mesh)
    asset_coll = bpy.data.collections.new("SweepTestAssetColl")
    scene_coll.children.link(asset_coll)
    asset_coll.objects.link(asset_obj)

    result2 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 200.0, 0.0), (40.0, 200.0, 0.0)], lane_width=LANE_W, lanes=1,
        lanes_backward=1, curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll2 = result2["coll"]
    _assert(pp.raised_span(coll2, 'L') is None,
            "sanity: curb style NONE should leave NOTHING standing above the road surface on the "
            "left, found %r" % (pp.raised_span(coll2, 'L'),))
    paved_edge = pp.span(coll2)[1]

    _activate(context, coll2.objects.get(coll2["rka_curve_object"]))
    ret = bpy.ops.rka.set_curb_style(
        'EXEC_DEFAULT', side='L', style='PROFILE', asset_collection=asset_coll.name)
    _assert(ret == {'FINISHED'}, "set_curb_style to PROFILE did not finish: %s" % (ret,))
    coll2 = opint.local_collection(coll2.name)

    raised = pp.raised_span(coll2, 'L')
    _assert(raised is not None,
            "switching the L curb to PROFILE must raise geometry above the road surface -- found "
            "none (summary: %r)" % (pp.geometry_summary(coll2),))
    _assert(raised[0] <= paved_edge + TOL <= raised[1] + TOL,
            "the curb must straddle the paved edge (%.3f m), but the raised geometry spans %r -- "
            "a curb floating off the road is the 'wrong lateral frame' defect"
            % (paved_edge, raised))
    _assert(pp.raised_span(coll2, 'R') is None,
            "only the LEFT curb was switched on; the right side must still carry nothing raised")
    n_raised = pp.raised_vert_count(coll2, 'L')
    print("boundary_sweep smoketest: NONE -> PROFILE raised %d vertices straddling the paved edge "
          "at %.3f m (span %.3f..%.3f), right side still bare"
          % (n_raised, paved_edge, raised[0], raised[1]))

    # Re-applying the SAME style must not stack a second copy of the curb on the first. This is the
    # invariant behind the old "no stray '.001' duplicate" assertion: a duplicate sits in exactly
    # the same place, so it moves no span and renames nothing a test can see -- it doubles the
    # geometry.
    _activate(context, coll2.objects.get(coll2["rka_curve_object"]))
    ret = bpy.ops.rka.set_curb_style(
        'EXEC_DEFAULT', side='L', style='PROFILE', asset_collection=asset_coll.name)
    _assert(ret == {'FINISHED'}, "re-applying set_curb_style did not finish: %s" % (ret,))
    coll2 = opint.local_collection(coll2.name)
    n_again = pp.raised_vert_count(coll2, 'L')
    _assert(n_again == n_raised,
            "re-applying the same curb style must REPLACE the curb, not accumulate a second copy "
            "of it: %d raised vertices before, %d after" % (n_raised, n_again))

    # Switching back to NONE must delete it, not merely hide or rename it.
    _activate(context, coll2.objects.get(coll2["rka_curve_object"]))
    ret = bpy.ops.rka.set_curb_style('EXEC_DEFAULT', side='L', style='NONE')
    _assert(ret == {'FINISHED'}, "set_curb_style back to NONE did not finish: %s" % (ret,))
    coll2 = opint.local_collection(coll2.name)
    _assert(pp.raised_span(coll2, 'L') is None,
            "switching back to NONE must leave nothing standing above the road, found %r "
            "(summary: %r)" % (pp.raised_span(coll2, 'L'), pp.geometry_summary(coll2)))
    _assert(abs(pp.span(coll2)[1] - paved_edge) < TOL,
            "with the curb gone the piece should be back to its bare paved edge %.3f m, got %.3f"
            % (paved_edge, pp.span(coll2)[1]))
    print("boundary_sweep smoketest: re-applying PROFILE did not accumulate a second curb (%d "
          "raised verts both times), and switching back to NONE removed it entirely" % n_raised)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
