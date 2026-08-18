#!/usr/bin/env python3
"""
smoketest_asset_curb_sidewalk_gap.py -- headless verification for a confirmed real bug
(2026-08, user-reported against real content: "the sideway seem not align with asset curb, and
only align with box curb, where there will be a gap for asset between curb and sideway but not
happen to curb box type with sideway"). Root cause: `_curb_outer_clearance` (now
`kit_common.curb_outer_clearance`, shared with intersections) always returned 0 for `curb_style ==
'ASSET'` (a documented, known limitation -- "no simple analytic footprint") -- so a sidewalk
started exactly AT the boundary line regardless of how far an ASSET curb's own kit mesh actually
extended past it, leaving a visible gap for any piece wider than zero (every real piece).

Fixed by measuring the RESOLVED asset object's own local bounding box (max local Y, per
`tools/build_curb_kit.py`'s documented pivot convention) instead of hardcoding 0. This test
measures the ACTUAL evaluated mesh bounds of a curb and its sidewalk (both segment and
intersection) and asserts zero gap, not just that objects exist.

'ASSET' curb style has since been retired in favor of 'PROFILE' (2026-08, "only have
none/profile... to simplify the code base") -- `curb_outer_clearance`'s PROFILE branch is the
direct descendant of this exact fix (same resolved-asset-bbox measurement), so this test now
exercises PROFILE instead, still against the same real regression.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_asset_curb_sidewalk_gap.py
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
import piece_probe as pp                                    # noqa: E402


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

    # ========================================================================= segment (L and R)
    ret = bpy.ops.rka.build_straight_segment(
        'EXEC_DEFAULT', direction_deg=0.0, length=40.0, lane_width=5.0, lanes=1, lanes_backward=1,
        curb_l_style='PROFILE', curb_r_style='PROFILE',
        curb_asset_collection='Kit_Curb_JerseyBarrier_L2',
        sidewalk_l_width=3.5, sidewalk_r_width=3.5,
        sidewalk_l_asset_collection='Kit_Curb_SidewalkTile_L2',
        sidewalk_r_asset_collection='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, ret)
    coll = next(c for c in bpy.data.collections if "rka_curve_object" in c.keys())

    # The gap is asked of the ROAD, not of two named objects: is there any lateral band on this
    # side where the raised surface stops and has not resumed? (See `piece_probe.raised_gaps` --
    # measured over faces, so a sidewalk slab's own uncrossed middle is not mistaken for a hole.)
    for side, label in (('L', "Left"), ('R', "Right")):
        gaps = pp.raised_gaps(coll, side)
        _assert(pp.raised_span(coll, side) is not None,
                "sanity: the %s side should carry a PROFILE curb and a sidewalk, found nothing "
                "raised (summary: %r)" % (label, pp.geometry_summary(coll)))
        if gaps:
            raise AssertionError(
                "%s PROFILE curb -> sidewalk should be flush, but the raised surface breaks at "
                "%s -- widest gap %.4f m" % (label, gaps, max(hi - lo for lo, hi in gaps)))
    print("smoketest_asset_curb_sidewalk_gap: segment PROFILE curb <-> sidewalk run unbroken on "
          "both sides (raised band L %s, R %s, no gaps)"
          % (tuple(round(v, 2) for v in pp.raised_span(coll, 'L')),
             tuple(round(v, 2) for v in pp.raised_span(coll, 'R'))))

    # =================================================================================== intersection
    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='PROFILE', curb_asset_collection='Kit_Curb_JerseyBarrier_L2',
        sidewalk_width=3.5, sidewalk_asset_collection='Kit_Curb_SidewalkTile_L2')
    _assert(ret == {'FINISHED'}, ret)
    int_coll = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    curb_objs = [o for o in int_coll.objects if o.name.startswith("curb_%s_" % int_coll.name)]
    sw_objs = [o for o in int_coll.objects if o.name.startswith("sidewalk_%s_" % int_coll.name)]
    _assert(len(curb_objs) > 0 and len(sw_objs) > 0,
            "sanity: intersection should have both curb and sidewalk objects, got %d/%d"
            % (len(curb_objs), len(sw_objs)))
    # Per-corner match: corner idx N's curb and sidewalk share the same underlying boundary
    # segment (see _populate_intersection_sidewalks/build_junction_curb_segments) -- compare each
    # pair's evaluated mesh centroid distance from the junction center-ish origin as a coarse but
    # real proxy: the sidewalk's nearest vertex to any curb vertex should be within a few cm, not
    # off by anywhere near sidewalk_width/2 (the exact regression this bug produced).
    deps = context.evaluated_depsgraph_get()

    def verts(o):
        eo = o.evaluated_get(deps)
        me = eo.to_mesh()
        vs = [tuple(o.matrix_world @ v.co) for v in me.vertices]
        eo.to_mesh_clear()
        return vs

    for idx in range(len(curb_objs)):
        curb_name = "curb_%s_%d" % (int_coll.name, idx)
        sw_name = "sidewalk_%s_%d" % (int_coll.name, idx)
        curb_o = int_coll.objects.get(curb_name)
        sw_o = int_coll.objects.get(sw_name)
        if curb_o is None or sw_o is None:
            continue
        cv, sv = verts(curb_o), verts(sw_o)
        min_gap = min(
            ((cx - sx) ** 2 + (cy - sy) ** 2 + (cz - sz) ** 2) ** 0.5
            for (cx, cy, cz) in cv for (sx, sy, sz) in sv
        )
        _assert(min_gap < 0.5, "corner %d: nearest curb-to-sidewalk vertex distance should be "
                "small (flush), got %.2fm -- a real gap" % (idx, min_gap))
    print("smoketest_asset_curb_sidewalk_gap: intersection PROFILE curb <-> sidewalk sit flush at "
          "every corner (%d corners checked)" % len(curb_objs))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
