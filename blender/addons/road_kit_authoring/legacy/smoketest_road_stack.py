#!/usr/bin/env python3
"""
smoketest_road_stack.py -- the layered modifier stack must put geometry exactly where
`lane_profile` says, including where the cross-section VARIES along the piece.

WHY THIS EXISTS. `road_stack.py` moves the swept parts of a road (pavement, curb, sidewalk,
median) and every prop row off Python-built sibling objects and onto one modifier stack on the
spine. The failure mode of that move is not a crash -- it is geometry that builds fine and sits in
the wrong place, which is precisely the class of defect (three of them) that motivated the whole
redesign. Two conventions in particular have already been wrong once and are pinned here by
MEASUREMENT, not by reading the node graph:

  * the lateral frame's SIGN. `rka_lat` must point the same way as
    `intersection_kit.offset_spine_line(+x)` under `traffic_side='LEFT'`. The Phase-0 bug was
    exactly this mismatch between the Python offset frame and Curve to Mesh's own profile frame,
    and it was invisible while everything was symmetric because a symmetric sweep is
    sign-invariant. Every assertion below therefore uses an ASYMMETRIC road.
  * PER-POINT variation. `rka_halfw`/`rka_shift` are the whole reason the carrier is a mesh: they
    let one piece open a ramp continuously instead of being cut into `trunk_before`/`trunk_taper`/
    `trunk_aux`. A stack that honours the average but not the per-point value would pass a
    width-only check at both ends.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_road_stack.py
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

TOL = 1e-3
SPINE = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (80.0, 0.0, 0.0), (120.0, 0.0, 0.0)]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _eval_verts(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    return [obj.matrix_world @ v.co for v in me.vertices]


def _span_y(verts, x_lo=-1e9, x_hi=1e9):
    ys = [v.y for v in verts if x_lo - TOL <= v.x <= x_hi + TOL]
    return (min(ys), max(ys)) if ys else (None, None)


def _profile_object(name):
    """A tiny 2-point vertical line to sweep -- stands in for a curb/sidewalk cross-section asset
    without depending on the kit library being linked in a headless test.

    Local X = lateral offset from the spine, local Y = UP. That is the profile-plane convention
    `kit_common._curb_profile_object` / `GN_BarrierProfile` / `GN_RoadProfile` already share, so
    every existing 2D profile asset drops into a stack layer with no re-authoring. (Putting the
    height on local Z instead produces a swept ribbon that is flat on the ground -- measured:
    z_max stayed 0.000.)"""
    cu = bpy.data.curves.new(name + "_cu", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(1)
    sp.points[0].co = (0.0, 0.0, 0.0, 1.0)
    sp.points[1].co = (0.0, 0.5, 0.0, 1.0)
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


def main():
    coll = bpy.context.scene.collection

    # =============================================================== 1. asymmetric one-way sweep
    # 3 forward lanes, none backward: the carriageway must span [0, +10.5] in the lateral frame,
    # NOT [-10.5, +10.5] (the old mirrored sweep) and NOT [-10.5, 0] (the sign flipped).
    ps = lp.ProfileSet([lp.profile_from_scalars(3, 0, 3.5)])
    spine = rs.make_spine_mesh("ST_oneway", SPINE, coll)
    rs.write_spine_attributes(spine, rs.spine_attributes_for(ps, len(SPINE), 'LEFT'))
    rs.build_stack(spine, [rs.layer("Pavement", rs.make_pavement_group(),
                                    offset_attr=rs.ATTR_SHIFT,
                                    Material=kc.mat("asphalt"))])
    lo, hi = _span_y(_eval_verts(spine))
    _assert(abs(hi - 10.5) < TOL and abs(lo - 0.0) < TOL,
            "one-way 3-lane carriageway spans [%.3f, %.3f]; expected [0.000, 10.500]. "
            "A span of [-10.5, 10.5] means the per-point shift never reached the sweep; a span "
            "of [-10.5, 0] means rka_lat points the wrong way relative to "
            "intersection_kit.offset_spine_line." % (lo, hi))

    # The sign must AGREE with intersection_kit, which is the authority for lane placement.
    probe = ik.offset_spine_line([(p[0], p[1], p[2]) for p in SPINE], 5.0, traffic_side='LEFT')
    _assert(probe[0][1] > 0.0,
            "intersection_kit.offset_spine_line(+5) should land on +y for a +X spine under LEFT; "
            "got y=%.3f -- the reference convention itself moved" % probe[0][1])
    print("road_stack: one-way sweep spans [%.2f, %.2f] and agrees with offset_spine_line's sign"
          % (lo, hi))

    # =============================================================== 2. symmetric is centred
    ps2 = lp.ProfileSet([lp.profile_from_scalars(2, 2, 3.25)])
    spine2 = rs.make_spine_mesh("ST_sym", SPINE, coll)
    rs.write_spine_attributes(spine2, rs.spine_attributes_for(ps2, len(SPINE), 'LEFT'))
    rs.build_stack(spine2, [rs.layer("Pavement", rs.make_pavement_group(),
                                     offset_attr=rs.ATTR_SHIFT, Material=kc.mat("asphalt"))])
    lo2, hi2 = _span_y(_eval_verts(spine2))
    _assert(abs(lo2 + 6.5) < TOL and abs(hi2 - 6.5) < TOL,
            "symmetric 2+2 must stay centred on the spine, got [%.3f, %.3f]" % (lo2, hi2))
    print("road_stack: symmetric 2+2 sweep spans [%.2f, %.2f], zero shift" % (lo2, hi2))

    # ====================================================== 3. PER-POINT variation (the ramp)
    # One piece, three stations: trunk -> ramp at zero width -> ramp at full width. The far end
    # must be one lane wider than the near end, and the middle genuinely in between.
    st0 = lp.profile_from_scalars(3, 0, 3.5)
    st1 = st0.copy(); st1.slots.append(lp.Slot("RAMP", lp.AUX, 0.0, lp.FWD))
    st2 = st1.copy(); st2.slot("RAMP").width = 3.5
    ramp = lp.ProfileSet([st0, st1, st2], [0.0, 0.34, 1.0])
    spine3 = rs.make_spine_mesh("ST_ramp", SPINE, coll)
    rs.write_spine_attributes(spine3, rs.spine_attributes_for(ramp, len(SPINE), 'LEFT'))
    rs.build_stack(spine3, [rs.layer("Pavement", rs.make_pavement_group(),
                                     offset_attr=rs.ATTR_SHIFT, Material=kc.mat("asphalt"))])
    verts3 = _eval_verts(spine3)
    # Measure the swept RINGS, not an x-slice. Curve to Mesh emits one cross-section per curve
    # point, in order, oriented perpendicular to the LOCAL tangent -- and as the ramp opens, the
    # paved centre shifts sideways, so the swept centreline genuinely curves and the mid-piece
    # cross-sections are no longer exactly on x=40/80. That rotation is correct road behaviour
    # (a widening carriageway's section stays square to its own centre line); slicing by x just
    # measures the wrong thing. The profile has 2 points, so verts arrive as consecutive pairs.
    _assert(len(verts3) == 2 * len(SPINE),
            "expected one 2-vert ring per spine point (%d verts), got %d"
            % (2 * len(SPINE), len(verts3)))
    rings = [(verts3[2 * i], verts3[2 * i + 1]) for i in range(len(SPINE))]
    widths = [(a - b).length for a, b in rings]
    _assert(abs(widths[0] - 10.5) < TOL,
            "the near end carries 3 lanes -> 10.5 m, got %.3f" % widths[0])
    _assert(abs(widths[-1] - 14.0) < TOL,
            "the far end carries 3 lanes + a full ramp -> 14.0 m, got %.3f" % widths[-1])
    _assert(widths == sorted(widths),
            "the ramp must open MONOTONICALLY along the piece, got %r" % [round(w, 3) for w in widths])
    _assert(10.5 < widths[2] < 14.0,
            "the mid-piece cross-section must be genuinely in between, got %.3f -- a stack that "
            "honours only the endpoints would still pass a width check at both ends" % widths[2])
    # ...and the trunk lanes must NOT move while the ramp opens outboard of them: the trunk edge
    # stays on y=0. Tolerance is looser than TOL purely because of the section rotation above
    # (3.5 m of opening over 120 m tilts each ring ~1.7 deg, worth a few mm at 10.5 m of width) --
    # a real frame error would be metres, not millimetres.
    for i, (a, b) in enumerate(rings):
        inner = min(a.y, b.y)
        _assert(abs(inner) < 0.02,
                "the trunk edge must stay at y=0 while the ramp opens; at ring %d it is %.4f"
                % (i, inner))
    print("road_stack: per-point ramp opens %.2f -> %.2f m monotonically, trunk edge fixed at y=0"
          % (widths[0], widths[-1]))

    # ====================================================== 4. a profile-sweep layer at an offset
    prof = _profile_object("ST_curbprofile")
    spine4 = rs.make_spine_mesh("ST_curb", SPINE, coll)
    rs.write_spine_attributes(spine4, rs.spine_attributes_for(ps, len(SPINE), 'LEFT'))
    rs.build_stack(spine4, [
        rs.layer("Pavement", rs.make_pavement_group(), offset_attr=rs.ATTR_SHIFT,
                 Material=kc.mat("asphalt")),
        rs.layer("CurbL", rs.make_profile_sweep_group(), offset=10.5, z=0.0,
                 Profile=prof, Material=kc.mat("concrete")),
    ])
    verts4 = _eval_verts(spine4)
    _assert(any(abs(v.y - 10.5) < TOL and v.z > 0.4 for v in verts4),
            "the curb layer must sweep its profile at y=+10.5 and rise 0.5 m; the swept vert "
            "set reaches y_max=%.3f z_max=%.3f"
            % (max(v.y for v in verts4), max(v.z for v in verts4)))
    lo4, hi4 = _span_y(verts4)
    _assert(abs(hi4 - 10.5) < TOL,
            "adding a curb at the pavement edge must not widen the piece past 10.5, got %.3f" % hi4)
    print("road_stack: a profile-sweep layer lands on the carriageway edge and rises 0.5 m")

    # ====================================================== 5. an asset row is a modifier
    lamp = _asset_object("ST_lamp")
    spine5 = rs.make_spine_mesh("ST_lamps", SPINE, coll)
    rs.write_spine_attributes(spine5, rs.spine_attributes_for(ps, len(SPINE), 'LEFT'))
    rs.build_stack(spine5, [
        rs.layer("Lamps", rs.make_asset_row_group(), offset=11.0, z=0.0,
                 Object=lamp, Spacing=30.0),
    ])
    verts5 = _eval_verts(spine5)
    # 120 m at 30 m spacing -> 4 instances (the end-inclusive 5th is deleted), 4 verts each.
    _assert(len(verts5) == 16,
            "120 m / 30 m spacing must place 4 lamp instances (16 verts), got %d verts -- an "
            "extra instance means the end-inclusive overshoot point was not deleted"
            % len(verts5))
    xs = sorted(set(round(v.x, 2) for v in verts5))
    _assert(all(abs(v.y - 11.0) < 0.5 for v in verts5),
            "every lamp must sit on the offset line y=+11.0, got y range %.2f..%.2f"
            % (min(v.y for v in verts5), max(v.y for v in verts5)))
    print("road_stack: asset row places 4 live instances at %r along the offset line" % xs[:8])

    # ...and the row genuinely FOLLOWS the spine: move a control point, the lamps move with it,
    # with no Python re-invocation. This is the property the Python tiling path did not have.
    spine5.data.vertices[3].co.y += 20.0
    spine5.data.update()
    moved = _eval_verts(spine5)
    before, after = max(v.y for v in verts5), max(v.y for v in moved)
    # The furthest lamp sits near x=90, and the drag was applied at x=120, so it picks up only
    # PART of the 20 m -- roughly 5 m by linear interpolation along the last span. Assert that it
    # moved substantially, not that it moved the full amount: the point is liveness, and pinning
    # an exact figure here would just encode the lamp spacing.
    _assert(after - before > 4.0,
            "after dragging the last spine vertex 20 m sideways the lamp row must follow; max y "
            "went %.2f -> %.2f -- the row is not live" % (before, after))
    print("road_stack: editing the spine moves the row live (max y %.1f -> %.1f)"
          % (max(v.y for v in verts5), max(v.y for v in moved)))

    # ====================================================== 6. Finish drops the carrier curve
    dg = bpy.context.evaluated_depsgraph_get()
    ev = spine4.evaluated_get(dg)
    _assert(ev.type == 'MESH', "the evaluated piece must be a MESH, got %s" % ev.type)
    names = [m.name for m in spine4.modifiers]
    _assert(names[0] == "Spine" and names[-1] == "Finish",
            "the stack must start with Spine and end with Finish, got %r" % names)
    print("road_stack: stack order %r, evaluates to a mesh" % names)

    print("smoketest_road_stack: OK")


if __name__ == "__main__":
    main()
