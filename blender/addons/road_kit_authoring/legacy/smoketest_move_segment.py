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

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_move_segment.py
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
import piece_probe as pp                             # noqa: E402


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

    # Where the piece's raised geometry (its curbs) actually SITS IN THE WORLD, as a single
    # centroid. Asked of the evaluated geometry rather than of a `curb_<piece>_L` object's first
    # spline point, so it keeps meaning the same thing once a curb is a modifier on the carrier
    # instead of a sibling object (`ROAD_KIT_REDESIGN.md` §7).
    curb_centroid_before = pp.raised_centroid(coll)
    _assert(curb_centroid_before is not None,
            "sanity: a BOX-curbed segment should have raised geometry to track (summary: %r)"
            % (pp.geometry_summary(coll),))

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

    curb_centroid_after = pp.raised_centroid(coll)
    _assert(curb_centroid_after is not None,
            "the curbs vanished across the rigid move + rebuild (summary: %r)"
            % (pp.geometry_summary(coll),))
    _assert(math.dist(curb_centroid_before[:2], curb_centroid_after[:2]) > 1.0,
            "the curb geometry should have actually moved with the piece after the rigid "
            "transform + rebuild -- it is still centred at %s (stale geometry left behind means "
            "the curb never got regenerated)"
            % (tuple(round(v, 2) for v in curb_centroid_after),))
    # The curb must have followed the SPINE, not merely moved somewhere: measured against the
    # rebuilt spine it should sit at the same lateral offset as before the move. This is the part
    # the old "did the first spline point change" check could not tell apart from a curb that
    # moved wrongly.
    span_after = pp.raised_span(coll)
    _assert(span_after is not None and abs(abs(span_after[1]) - abs(span_after[0])) < 0.5,
            "after a rigid move the curbs should still sit symmetrically about the spine, got %r"
            % (span_after,))
    print("move-segment smoketest: curbs regenerated and travelled with the piece (centroid %s -> "
          "%s) while keeping their offset from the spine (%.2f..%.2f)"
          % (tuple(round(v, 1) for v in curb_centroid_before),
             tuple(round(v, 1) for v in curb_centroid_after), span_after[0], span_after[1]))


def _check_transition(context, scene_coll):
    bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='NONE',
        curb_r_style='NONE')
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
