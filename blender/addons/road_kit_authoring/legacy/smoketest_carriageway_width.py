#!/usr/bin/env python3
"""
smoketest_carriageway_width.py -- the swept pavement must cover exactly the lanes that exist,
and a piece built with `join_visual_mesh=True` must keep its live GN spine.

WHY THIS EXISTS. Two defects found together (2026-08) against real content in
`assets/world_source/island_v3_roads.blend`, both silent -- no exception, no warning, just wrong
geometry and missing data:

1. ONE-WAY ROADS WERE BUILT DOUBLE-WIDTH. Every caller sized the carriageway as
   `median_half + max(lanes, lanes_backward) * lane_width` on BOTH sides, i.e. it mirrored the
   busier direction onto the quieter one. `build_segment_from_spine` meanwhile places forward
   lanes on the positive side and backward lanes on the negative one, so a one-way road swept a
   whole empty mirror carriageway -- measured on `IC_CHUO_merge_trunk_aux_001`: 21.00 m of
   asphalt for 10.50 m of lanes, with the curb and its sidewalk built out in the middle of
   nothing. An asymmetric two-way road (3 forward, 2 back) was over-wide by one lane for the same
   reason. See `intersection_kit.carriageway_extents` / `kit_common.make_road_profile_group`.

2. `join_visual_mesh=True` DESTROYED THE SPINE. `ops_intersection.join_meshes` converts every
   non-Mesh input with `bpy.ops.object.convert(target='MESH')`, which bakes the spine's live
   "Road" `GN_RoadProfile` modifier away -- and since the spine is `visual_objs[0]`, it was then
   renamed to `mesh_<piece>`. `rka_curve_object` recorded that name, so
   `lane_export._export_gn_segment` (which requires a CURVE) returned None and the piece was
   SKIPPED from `.lanekit.json` entirely -- 40 of the 111 piece collections in
   `island_v3_roads.blend` contributed zero lanes. It also broke live editing and `-colonly`
   collision baking, which both identify the pavement by that same modifier.
   See `ops_segment._join_visuals_keeping_spine`.

WHAT IS ASSERTED. Not just the width number -- the property that actually matters is that the
LANE DATA AND THE MESH AGREE: every exported lane centreline must fall inside the swept pavement,
with a sane margin on each side. A width check alone would still pass if the pavement were the
right size but in the wrong place.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_carriageway_width.py
(the flag matters -- blender exits 0 on an uncaught script exception without it)
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
import road_kit_authoring as rka  # noqa: F401  (registers the addon's operators)
from road_kit_authoring import spine_io  # noqa: E402
from road_kit_authoring import lane_export
from road_kit_authoring.ops_segment import _build_segment_from_points

STRAIGHT = [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (120.0, 0.0, 0.0)]   # along +X, so |y| is lateral


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _swept_span(ctx, spine_obj):
    """(min_y, max_y) of the EVALUATED pavement -- the GN sweep's real extent, not the radius we
    asked for. Evaluating through the depsgraph is the only honest check: it is what the glTF
    exporter and the collision baker will see."""
    dg = ctx.evaluated_depsgraph_get()
    me = spine_obj.evaluated_get(dg).to_mesh()
    ys = [(spine_obj.matrix_world @ v.co).y for v in me.vertices]
    return min(ys), max(ys)


def main():
    ctx = bpy.context
    scene_coll = ctx.scene.collection

    # ------------------------------------------------- pavement covers exactly the lanes present
    # (name, lanes_fwd, lanes_back, lane_width, expected total width)
    cases = [
        ("oneway_1f", 1, 0, 3.5, 1 * 3.5),    # the degenerate case: 1 lane => 1 lane of asphalt
        ("oneway_3f", 3, 0, 3.5, 3 * 3.5),    # the real island_v3 trunk_aux shape (was 21.00 m)
        ("asym_3f2b", 3, 2, 3.5, 5 * 3.5),    # each edge moves by its OWN direction's count
        ("sym_2f2b", 2, 2, 3.25, 4 * 3.25),   # symmetric: must be byte-identical to before
    ]
    for name, fwd, back, lw, expect in cases:
        r = _build_segment_from_points(
            ctx, scene_coll, STRAIGHT, lw, fwd, back, 'NONE', 'NONE', 0.15, 0.25,
            False, "", "", base_name="CW_%s" % name, traffic_side='LEFT')
        lo, hi = _swept_span(ctx, r["spine_obj"])
        width = hi - lo
        _assert(abs(width - expect) < 1e-4,
                "%s: swept pavement is %.2f m wide, expected %.2f m (%d fwd + %d back lanes of "
                "%.2f m). A mirrored empty carriageway is the classic symptom -- see "
                "intersection_kit.carriageway_extents." % (name, width, expect, fwd, back, lw))

        # THE REAL ASSERTION: the exported lane centrelines live inside that pavement.
        d = lane_export.export_piece_dict(r["coll"], ctx.scene, godot_space=False)
        _assert(d is not None, "%s: exported no lane data at all" % name)
        _assert(len(d["lanes"]) == fwd + back,
                "%s: expected %d lanes, got %d" % (name, fwd + back, len(d["lanes"])))
        for lane in d["lanes"]:
            for p in lane["points"]:
                _assert(lo - 1e-4 <= p[1] <= hi + 1e-4,
                        "%s: lane %s runs at y=%.2f, outside the swept pavement [%.2f, %.2f] -- "
                        "the mesh and the lane data disagree"
                        % (name, lane["id"], p[1], lo, hi))
            # ...and no lane centre may sit closer than a half-lane to an edge, which is what
            # would happen if the pavement were the right WIDTH but the wrong PLACE.
            margin = min(min(abs(p[1] - lo), abs(hi - p[1])) for p in lane["points"])
            _assert(margin >= lw / 2.0 - 1e-4,
                    "%s: lane %s comes within %.2f m of a pavement edge (half a lane is %.2f m) "
                    "-- pavement is offset from the lanes"
                    % (name, lane["id"], margin, lw / 2.0))
        print("carriageway_width: %-10s %dfwd/%dback -> %.2f m, all %d lanes inside"
              % (name, fwd, back, width, len(d["lanes"])))

    # ------------------------------------------------------------- the pure helper's own contract
    _assert(ik.carriageway_extents(2, 2, 5.0) == (10.0, 10.0), "symmetric extents changed")
    _assert(ik.carriageway_extents(3, 0, 3.5) == (0.0, 10.5), "one-way extents wrong")
    _assert(ik.sweep_radius_and_shift(0.0, 10.5) == (5.25, 5.25), "radius/shift wrong")
    _assert(ik.sweep_radius_and_shift(10.0, 10.0) == (10.0, 0.0),
            "a symmetric road must still sweep with zero lateral shift")
    print("carriageway_width: carriageway_extents/sweep_radius_and_shift contracts hold")

    # ----------------------------------------- join_visual_mesh must NOT consume the live spine
    # This is what `ops_split`/`island_v3_to_roadkit` pass, and what silently baked 40 pieces.
    r = _build_segment_from_points(
        ctx, scene_coll, STRAIGHT, 3.5, 3, 0, 'PROFILE', 'PROFILE', 0.15, 0.25,
        True, "", "", base_name="CW_joined", traffic_side='LEFT')
    coll, spine_obj = r["coll"], r["spine_obj"]
    # The point is that `join_visual_mesh` must NOT bake the spine away into inert geometry --
    # asked as "is this still a live spine driven by geometry nodes", which both carrier kinds
    # answer, rather than as "is it a Curve carrying GN_RoadProfile", which is one carrier's
    # spelling of it (a modifier-stack piece sweeps its pavement in a `Pavement` layer instead).
    _assert(spine_io.is_spine(spine_obj),
            "join_visual_mesh baked the spine into inert %s geometry -- the piece can no longer "
            "be live-edited" % spine_obj.type)
    _assert(any(m.type == 'NODES' and m.node_group for m in spine_obj.modifiers),
            "the spine lost its live geometry-node modifiers (colonly baking finds the pavement "
            "through them)")
    recorded = coll.get("rka_curve_object")
    recorded = "".join(recorded) if not isinstance(recorded, str) else recorded
    _assert(recorded == spine_obj.name,
            "rka_curve_object records %r but the spine is %r" % (recorded, spine_obj.name))
    _assert(not recorded.startswith("mesh_"),
            "rka_curve_object points at a joined MESH (%r) -- lane_export requires a CURVE and "
            "will silently SKIP this piece" % recorded)
    d = lane_export.export_piece_dict(coll, ctx.scene, godot_space=False)
    _assert(d is not None and len(d["lanes"]) == 3,
            "a joined piece must still export its lanes, got %r"
            % (None if d is None else len(d["lanes"])))
    print("carriageway_width: join_visual_mesh keeps the live spine and still exports 3 lanes")

    print("smoketest_carriageway_width: OK")


if __name__ == "__main__":
    main()
