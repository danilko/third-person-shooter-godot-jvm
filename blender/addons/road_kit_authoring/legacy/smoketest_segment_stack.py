#!/usr/bin/env python3
"""
smoketest_segment_stack.py -- a FULL segment built as one modifier stack must place every part
where the sibling-object builder placed it, and must keep doing so as the cross-section varies.

WHY THIS EXISTS. `segment_stack.layers_for_segment` is the seam between the operator's parameters
and `road_stack`'s layers, and it re-expresses offsets that `intersection_kit.
build_segment_from_spine` already computes for the Python-built siblings. If the two ever disagree
the road still builds -- the curb just sits in the wrong place, or the sidewalk overlaps the
roadway, which is exactly the failure the redesign is meant to make impossible. So every offset
here is checked against `build_segment_from_spine`'s OWN output for the same parameters, not
against a number retyped from the docs.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_segment_stack.py
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import intersection_kit as ik
import kit_common as kc
import lane_profile as lp
import road_stack as rs
from road_kit_authoring import segment_stack as ss

TOL = 1e-3
SPINE = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (80.0, 0.0, 0.0), (120.0, 0.0, 0.0)]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _profile_object(name, height=0.5):
    """Local X = lateral, local Y = up -- the kit's profile-asset convention."""
    cu = bpy.data.curves.new(name + "_cu", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(1)
    sp.points[0].co = (0.0, 0.0, 0.0, 1.0)
    sp.points[1].co = (0.0, height, 0.0, 1.0)
    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _asset_object(name):
    me = bpy.data.meshes.new(name + "_me")
    me.from_pydata([(-0.2, -0.2, 0.0), (0.2, -0.2, 0.0), (0.2, 0.2, 0.0), (-0.2, 0.2, 0.0)],
                   [], [(0, 1, 2, 3)])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _attr(spine, name):
    a = spine.data.attributes.get(name)
    _assert(a is not None, "attribute %r was never written" % name)
    return [d.value for d in a.data]


def main():
    coll = bpy.context.scene.collection
    LW, FWD, REV = 3.5, 3, 2
    SW_L, SW_R, CLEAR = 3.0, 2.0, 0.125

    ps = lp.ProfileSet([lp.profile_from_scalars(FWD, REV, LW)])
    spine = rs.make_spine_mesh("SS_full", SPINE, coll)

    curb_p = _profile_object("SS_curb", 0.15)
    sw_p = _profile_object("SS_sw", 0.12)
    med_p = _profile_object("SS_med", 0.20)
    lamp = _asset_object("SS_lamp")

    layers = ss.layers_for_segment(
        spine, ps, traffic_side='LEFT',
        curb_l_profile=curb_p, curb_r_profile=curb_p, median_profile=med_p,
        sidewalk_l_width=SW_L, sidewalk_r_width=SW_R,
        sidewalk_l_profile=sw_p, sidewalk_r_profile=sw_p,
        curb_clearance_l=CLEAR, curb_clearance_r=CLEAR,
        prop_l_asset=lamp, prop_l_spacing=30.0, prop_r_asset=lamp, prop_r_spacing=30.0,
        mat=kc.mat)
    rs.build_stack(spine, layers)

    names = [m.name for m in spine.modifiers]
    _assert(names == ["Spine", "Pavement", "CurbL", "CurbR", "Median", "SidewalkL", "SidewalkR",
                      "PropL", "PropR", "Finish"],
            "unexpected stack: %r" % names)
    print("segment_stack: one object, one stack: %r" % names)

    # ---------------------------------------------------------------- offsets match the Python
    # builder's own lines, for exactly the same parameters. This is the assertion that matters:
    # not "is the number plausible" but "does it equal what the lane data is derived from".
    seg = ik.build_segment_from_spine(
        SPINE, LW, FWD, REV, segment_id="SS", traffic_side='LEFT',
        sidewalk_l_width=SW_L, sidewalk_r_width=SW_R,
        curb_clearance_l=CLEAR, curb_clearance_r=CLEAR)
    left_pts, right_pts = seg["curbs"]
    ref = {
        ss.ATTR_CURB_L: left_pts[0][1],
        ss.ATTR_CURB_R: right_pts[0][1],
        ss.ATTR_SW_L: seg["sidewalks"]["L"][0][1],
        ss.ATTR_SW_R: seg["sidewalks"]["R"][0][1],
    }
    for attr, expect in ref.items():
        got = _attr(spine, attr)
        _assert(all(abs(v - expect) < TOL for v in got),
                "%s = %r but build_segment_from_spine puts that line at y=%.4f -- the stack and "
                "the lane data are in different lateral frames"
                % (attr, [round(v, 4) for v in got], expect))
    print("segment_stack: curb L/R and sidewalk L/R offsets equal build_segment_from_spine's "
          "own lines (%.3f / %.3f / %.3f / %.3f)"
          % tuple(ref[k] for k in (ss.ATTR_CURB_L, ss.ATTR_CURB_R, ss.ATTR_SW_L, ss.ATTR_SW_R)))

    # sidewalks must sit OUTSIDE the carriageway, never over it
    neg, pos = lp.paved_extents(ps.at(0.0))
    _assert(ref[ss.ATTR_SW_L] - SW_L / 2.0 >= pos - TOL,
            "the L sidewalk's inner edge (%.3f) laps onto the carriageway (edge %.3f)"
            % (ref[ss.ATTR_SW_L] - SW_L / 2.0, pos))
    _assert(ref[ss.ATTR_SW_R] + SW_R / 2.0 <= -neg + TOL,
            "the R sidewalk's inner edge laps onto the carriageway")

    # ---------------------------------------------------------------- geometry actually lands
    dg = bpy.context.evaluated_depsgraph_get()
    verts = [spine.matrix_world @ v.co for v in spine.evaluated_get(dg).to_mesh().vertices]
    _assert(max(v.y for v in verts) > ref[ss.ATTR_SW_L],
            "nothing was built out as far as the L sidewalk (max y %.2f)"
            % max(v.y for v in verts))
    _assert(max(v.z for v in verts) > 0.1,
            "every layer swept flat -- curb/sidewalk profiles did not rise (max z %.3f)"
            % max(v.z for v in verts))
    print("segment_stack: evaluated piece spans y %.2f..%.2f, z up to %.2f"
          % (min(v.y for v in verts), max(v.y for v in verts), max(v.z for v in verts)))

    # ---------------------------------------------- a VARYING cross-section carries the curb out
    # Two stations, 3+2 -> 5+2 lanes. The L curb must move outward by exactly two lane widths
    # along the piece, continuously -- the case the sibling-object model had to cut into separate
    # pieces because a per-piece constant cannot express it.
    ps2 = lp.ProfileSet([lp.profile_from_scalars(FWD, REV, LW),
                         lp.profile_from_scalars(FWD + 2, REV, LW)])
    spine2 = rs.make_spine_mesh("SS_widen", SPINE, coll)
    rs.build_stack(spine2, ss.layers_for_segment(
        spine2, ps2, curb_l_profile=curb_p, curb_r_profile=curb_p, mat=kc.mat))
    curb_l = _attr(spine2, ss.ATTR_CURB_L)
    curb_r = _attr(spine2, ss.ATTR_CURB_R)
    _assert(abs(curb_l[0] - FWD * LW) < TOL and abs(curb_l[-1] - (FWD + 2) * LW) < TOL,
            "the L curb must run %.2f -> %.2f m as two lanes are added, got %.2f -> %.2f"
            % (FWD * LW, (FWD + 2) * LW, curb_l[0], curb_l[-1]))
    _assert(curb_l == sorted(curb_l), "the widening must be monotonic, got %r" % curb_l)
    _assert(all(abs(v - curb_r[0]) < TOL for v in curb_r),
            "the R curb must NOT move -- lanes were added on the L side only, got %r" % curb_r)
    print("segment_stack: a 3+2 -> 5+2 widening carries the L curb %.2f -> %.2f m with the R "
          "curb pinned at %.2f" % (curb_l[0], curb_l[-1], curb_r[0]))

    # ---------------------------------------------------------------- keep-right mirrors, once
    spine3 = rs.make_spine_mesh("SS_right", SPINE, coll)
    rs.build_stack(spine3, ss.layers_for_segment(
        spine3, ps, traffic_side='RIGHT', curb_l_profile=curb_p, curb_r_profile=curb_p,
        mat=kc.mat))
    _assert(abs(_attr(spine3, ss.ATTR_CURB_L)[0] + ref[ss.ATTR_CURB_L]) < TOL,
            "keep-right must mirror every offset exactly once: L curb is %.3f, expected %.3f"
            % (_attr(spine3, ss.ATTR_CURB_L)[0], -ref[ss.ATTR_CURB_L]))
    print("segment_stack: traffic_side='RIGHT' mirrors the offsets exactly once")

    print("smoketest_segment_stack: OK")


if __name__ == "__main__":
    main()
