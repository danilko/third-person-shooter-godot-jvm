#!/usr/bin/env python3
"""
smoketest_move_segment.py -- headless verification that a plain GN segment AND a lane-transition
piece each get the same "origin_<coll>" UX anchor Empty an intersection's arm markers already
provide (see ops_intersection.get_or_create_origin_marker), and that moving/rotating the WHOLE
collection as a rigid group (the "select all objects, Grab/Rotate" workflow Freeze For Move exists
to make safe) still regenerates correct geometry afterward -- for these two piece types the actual
geometry math was ALREADY robust (curb/lanecl_* are re-derived from the spine object's own live
`matrix_world`, not a frozen origin coordinate), so this test's job is to prove that stays true and
that the new origin marker tracks the spine correctly (re-snapped on every rebuild, not just at
build time).

RUN: blender --background --python addons/road_kit_authoring/smoketest_move_segment.py
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                      # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg    # noqa: E402
import kit_common as kc                                 # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _rigid_transform(coll, dx, dy, rot_deg, ox, oy):
    """Apply ONE rigid-body `matrix_world` transform (translate by (dx, dy) then rotate `rot_deg`
    around world Z through (ox, oy)) to every object in `coll` -- the real-Blender-equivalent of
    "select all objects in the collection, G, then R (Median Point pivot)".

    Unlike `smoketest_move_intersection.py`'s simpler position-only version (correct THERE only
    because that math consumes pure-position marker Empties), this addon's segment/transition
    geometry is baked as ABSOLUTE world coordinates directly into curve/mesh point data with the
    owning object left at an IDENTITY transform (see `kit_common.road_spine`/`curb_loop`'s
    `_poly_curve_with_radius` -- points are `(x, y, z)` verbatim, never object-local-relative).
    So rotating the GROUP means rotating each object's `matrix_world` around the shared pivot --
    moving `.location` alone (as if every object were a dimensionless point) would leave an
    object's own baked shape unrotated, only its nominal origin displaced. Setting the full
    `matrix_world` is correct for BOTH conventions (point Empties and baked-absolute
    curves/meshes) since it's exactly what Blender's own transform operators do."""
    rad = math.radians(rot_deg)
    pivot = Vector((ox, oy, 0.0))
    xform = (Matrix.Translation(pivot) @ Matrix.Rotation(rad, 4, 'Z')
             @ Matrix.Translation(-pivot) @ Matrix.Translation(Vector((dx, dy, 0.0))))
    for o in list(coll.objects):
        o.matrix_world = xform @ o.matrix_world


def _check_segment(context, scene_coll):
    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    coll = result["coll"]

    marker = opint.get_or_create_origin_marker(coll)
    _assert(marker is not None, "plain segment should get an origin marker at build time")
    _assert(abs(marker.location.x) < 1e-6 and abs(marker.location.y) < 1e-6,
            "origin marker should sit at the spine's start point (0,0)")
    print("move-segment smoketest: plain segment got an origin marker at its spine start")

    def _curb_first_point_world(obj):
        # curb_loop's Curve object carries ABSOLUTE world coordinates baked directly into its
        # POLY spline points (see kit_common._poly_curve_with_radius) -- the object itself stays
        # at identity transform, so matrix_world is applied for correctness but is a no-op here.
        pt = obj.data.splines[0].points[0].co
        return tuple(obj.matrix_world @ pt.to_3d())

    curb_l_before = bpy.data.objects["curb_%s_L" % coll.name]
    p0_before = _curb_first_point_world(curb_l_before)

    dx, dy, rot_deg = 100.0, 50.0, 40.0
    # Rotate around the segment's own current origin marker -- the natural pivot for "move this
    # piece as a rigid group", same as the intersection test rotating around its own marker.
    ox, oy = marker.location.x + dx, marker.location.y + dy
    _rigid_transform(coll, dx, dy, rot_deg, ox, oy)

    opseg.rebuild_segment_gn_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    marker = opint.get_or_create_origin_marker(coll)
    _assert(abs(marker.location.x - dx) < 1e-3 and abs(marker.location.y - dy) < 1e-3,
            "segment origin marker should re-snap to the spine's (moved) start point, got "
            "(%.3f, %.3f) expected (%.1f, %.1f)" % (marker.location.x, marker.location.y, dx, dy))
    print("move-segment smoketest: origin marker re-snapped to the moved spine's start point "
          "after rebuild (%.2f, %.2f)" % (marker.location.x, marker.location.y))

    spine_obj = bpy.data.objects.get(coll.get("rka_curve_object"))
    spine = opseg._spine_control_points(spine_obj)
    expected_end = (dx + 40.0 * math.cos(math.radians(rot_deg)),
                    dy + 40.0 * math.sin(math.radians(rot_deg)))
    _assert(math.dist(spine[-1][:2], expected_end) < 1e-2,
            "spine end point should reflect the rigid move+rotate, got %s expected %s"
            % (spine[-1][:2], expected_end))
    print("move-segment smoketest: spine geometry reflects the rigid move+rotate correctly "
          "(end=%s)" % (spine[-1][:2],))

    matching = [o for o in coll.objects if o.name == "curb_%s_L" % coll.name]
    _assert(len(matching) == 1, "exactly one left-curb object should exist after rebuild "
                                 "(no stale/duplicate accumulation), found %d" % len(matching))
    curb_l_after = matching[0]
    p0_after = _curb_first_point_world(curb_l_after)
    _assert(math.dist(p0_before[:2], p0_after[:2]) > 1.0,
            "left curb geometry should have actually moved after the rigid transform+rebuild "
            "(stale geometry left behind would mean the curb never got regenerated)")
    print("move-segment smoketest: curb objects regenerated cleanly after the rigid move "
          "(no stale/duplicate objects, geometry moved)")


def _check_transition(context, scene_coll):
    bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='BOX',
        curb_r_style='BOX')
    coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))

    marker = opint.get_or_create_origin_marker(coll)
    _assert(marker is not None, "lane transition should get an origin marker at build time")
    _assert(abs(marker.location.x) < 1e-6 and abs(marker.location.y) < 1e-6,
            "origin marker should sit at the transition's start point (0,0)")
    print("move-transition smoketest: lane transition got an origin marker at its spine start")

    dx, dy, rot_deg = -30.0, 80.0, -25.0
    ox, oy = marker.location.x + dx, marker.location.y + dy
    _rigid_transform(coll, dx, dy, rot_deg, ox, oy)

    opseg.rebuild_lane_transition_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    marker = opint.get_or_create_origin_marker(coll)
    _assert(abs(marker.location.x - dx) < 1e-3 and abs(marker.location.y - dy) < 1e-3,
            "transition origin marker should re-snap to the spine's (moved) start point, got "
            "(%.3f, %.3f) expected (%.1f, %.1f)" % (marker.location.x, marker.location.y, dx, dy))
    print("move-transition smoketest: origin marker re-snapped after rebuild (%.2f, %.2f)"
          % (marker.location.x, marker.location.y))

    spine_obj = bpy.data.objects.get(coll.get("rka_curve_object"))
    spine = opseg._spine_control_points(spine_obj)
    expected_end = (dx + 20.0 * math.cos(math.radians(rot_deg)),
                    dy + 20.0 * math.sin(math.radians(rot_deg)))
    _assert(math.dist(spine[-1][:2], expected_end) < 1e-2,
            "transition spine end should reflect the rigid move+rotate, got %s expected %s"
            % (spine[-1][:2], expected_end))
    print("move-transition smoketest: spine geometry reflects the rigid move+rotate correctly "
          "(end=%s)" % (spine[-1][:2],))


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    scene_coll = context.scene.collection

    _check_segment(context, scene_coll)
    _check_transition(context, scene_coll)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
