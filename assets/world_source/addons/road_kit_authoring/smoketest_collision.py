#!/usr/bin/env python3
"""
smoketest_collision.py -- headless verification for P6.2 (road_blender_godot.md): road_kit_authoring
geometry now gets a `-colonly` collision proxy alongside its visual mesh -- previously road_kit_authoring
produced zero collision at all (explicitly deferred in road_blender_godot.md's "Collision strategy
note"). `kit_common.colonly_polygon` (new) covers an intersection's pad footprint; `kit_common.
colonly_swept` covers every curb wall (intersections, straight/curved segments, lane transitions).

Follow-up fix (2026-07-27, user-reported: vehicles sinking below the visual road, still following
their PathLaneRoute since that's pure geometry): curb-edge collision alone left the actual drivable
surface BETWEEN the two curb lines uncollided -- a vehicle in the middle of the road (not directly
under a curb) fell straight through to whatever's below. `kit_common.colonly_swept_between` (new)
adds a pavement collision slab from the segment/transition's own left/right curb-line points
(naturally tapering for a lane-count transition, via colonly_swept's per-point half-width). Junction
pads were never affected (`colonly_polygon` already covers the full footprint).

RUN: blender --background --python addons/road_kit_authoring/smoketest_collision.py
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


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _colonly_objects(coll):
    return [o for o in coll.objects if o.name.endswith("-colonly")]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ======================================================================== intersection pad + curb
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    colonly = _colonly_objects(coll)
    pad_col = next((o for o in colonly if o.name.startswith("pad_")), None)
    curb_cols = [o for o in colonly if o.name.startswith("curb_")]
    _assert(pad_col is not None, "intersection should have a pad_*-colonly collision proxy")
    _assert(len(pad_col.data.vertices) > 0 and len(pad_col.data.polygons) > 0,
            "pad colonly mesh should have real geometry")
    _assert(pad_col.get("proxy_for") == "pad_%s" % coll.name,
            "pad colonly should tag proxy_for back to the pad's own name")
    _assert(len(curb_cols) == 4, "4-way should have 4 curb_*-colonly proxies (one per corner), got %d"
            % len(curb_cols))
    for c in curb_cols:
        _assert(len(c.data.vertices) > 0 and len(c.data.polygons) > 0,
                "curb colonly '%s' mesh should have real geometry" % c.name)
    print("collision smoketest: intersection has a pad colonly + %d curb colonlies, all with real "
          "geometry" % len(curb_cols))

    # Regression check (2026-07-27, user-reported "vehicle/character some distance from the road
    # mesh"): GN_JunctionPad's `Fill Curve` node silently flattens every evaluated vertex to world
    # Z=0 regardless of the input curve's real height -- this sank the VISUAL pad ~lane_surface_z
    # below the (correctly-placed) pad colonly, a real gap between where the road renders and
    # where vehicles/characters actually rest. `junction_pad`'s Set Position restore must keep the
    # evaluated pad at its real height, matching the colonly EXACTLY (the pad colonly is now an
    # exact copy of the evaluated visual mesh via colonly_mesh_evaluated -- see the "AABB vs exact
    # mesh copy" follow-up below -- so it's a flat single-layer proxy at precisely the pad's own
    # height, not an extruded slab with a z0/z1 range to straddle; allow a tiny epsilon for
    # depsgraph-evaluation float noise, not the old z0/z1 margin).
    pad_visual = coll.objects["pad_%s" % coll.name]
    deps = context.evaluated_depsgraph_get()
    eo = pad_visual.evaluated_get(deps)
    me = eo.to_mesh()
    pad_zs = sorted(set(round((pad_visual.matrix_world @ v.co).z, 4) for v in me.vertices))
    eo.to_mesh_clear()
    expected_z = round(context.scene.rka.lane_surface_z, 4)
    _assert(pad_zs == [expected_z], "visual pad should sit flat at exactly Z=lane_surface_z "
            "(%.4f), got %r -- Fill Curve's Z-flattening regressed" % (expected_z, pad_zs))
    col_zs = [(pad_col.matrix_world @ v.co).z for v in pad_col.data.vertices]
    _assert(max(abs(z - expected_z) for z in col_zs) < 0.001,
            "pad colonly's Z values should all sit within 1mm of the visual pad's real height "
            "%.4f, got range [%.4f, %.4f] (collision should sit AT the road surface, not "
            "floating clear of it)" % (expected_z, min(col_zs), max(col_zs)))
    print("collision smoketest: visual pad sits flush with its colonly proxy at the real "
          "lane_surface_z height (Z=%.4f), not flattened to 0 by Fill Curve" % expected_z)

    # Rebuild in place must not leave stale/duplicate colonly objects (they carry the curb_/pad_
    # prefix clear_generated_mesh_objects already sweeps -- confirms no new cleanup code was needed).
    opint.rebuild_intersection_in_place(context, coll)
    colonly_after = _colonly_objects(coll)
    _assert(len(colonly_after) == len(colonly),
            "rebuild should not leave stale/duplicate colonly objects: before=%d after=%d"
            % (len(colonly), len(colonly_after)))
    print("collision smoketest: rebuild_intersection_in_place leaves exactly one colonly proxy per "
          "pad/corner, no duplicates or orphans")

    # join_visual_mesh must NOT swallow the collision proxies into the combined visual mesh.
    result2 = opint.build_intersection_geometry(
        context, scene_coll, (100.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, True, "", "", 'LEFT')   # join_visual_mesh=True
    coll2 = result2["coll"]
    colonly2 = _colonly_objects(coll2)
    _assert(len(colonly2) == 5, "join_visual_mesh=True should still leave pad+4 curb colonlies "
            "un-joined, got %d" % len(colonly2))
    mesh_objs = [o for o in coll2.objects if o.name.startswith("mesh_")]
    _assert(len(mesh_objs) == 1, "join_visual_mesh=True should still produce exactly one joined "
            "visual mesh object")
    print("collision smoketest: join_visual_mesh=True joins the visual pad/curbs but leaves "
          "collision proxies separate, as intended")

    # ============================================================================== straight segment
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    seg_colonly = _colonly_objects(seg_coll)
    _assert(len(seg_colonly) == 3, "straight segment should have 2 curb colonlies (L/R) + 1 "
            "pavement colonly, got %d" % len(seg_colonly))
    for c in seg_colonly:
        _assert(len(c.data.vertices) > 0 and len(c.data.polygons) > 0,
                "segment curb colonly '%s' should have real geometry" % c.name)
    pave_col = next((o for o in seg_colonly if o.name.startswith("pave_")), None)
    _assert(pave_col is not None, "straight segment should have a pave_*-colonly proxy covering "
            "the drivable surface, not just the curb edges")
    print("collision smoketest: straight segment has L/R curb colonlies + a pavement colonly, "
          "all with real geometry")

    # Rebuild in place must not leave stale/duplicate pavement colonly objects either (pave_* was
    # added to clear_generated_mesh_objects's swept prefixes alongside curb_/pad_).
    opseg.rebuild_segment_gn_in_place(context, seg_coll)
    seg_colonly_after = _colonly_objects(seg_coll)
    _assert(len(seg_colonly_after) == len(seg_colonly),
            "rebuilding a segment should not leave stale/duplicate colonly objects "
            "(including the pavement one): before=%d after=%d"
            % (len(seg_colonly), len(seg_colonly_after)))
    print("collision smoketest: rebuild_segment_gn_in_place leaves exactly one colonly proxy per "
          "curb/pavement, no duplicates or orphans")

    # ============================================================================= lane transition
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='BOX', curb_r_style='BOX')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    tr_colonly = _colonly_objects(tr_coll)
    _assert(len(tr_colonly) == 3, "lane transition should have 2 curb colonlies (L/R) + 1 "
            "pavement colonly, got %d" % len(tr_colonly))
    tr_pave = next((o for o in tr_colonly if o.name.startswith("pave_")), None)
    _assert(tr_pave is not None, "lane transition should have a pave_*-colonly proxy")
    _assert(len(tr_pave.data.vertices) > 0 and len(tr_pave.data.polygons) > 0,
            "transition pavement colonly should have real (tapering) geometry")
    print("collision smoketest: lane transition has L/R curb colonlies + a tapering pavement "
          "colonly")

    # ==================================================================== GUTTER style curb collision
    seg_result2 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 200.0, 0.0), (40.0, 200.0, 0.0)], 5.0, 1, 1,
        'GUTTER', 'GUTTER', 0.2, 0.6, False, "", "")
    seg_coll2 = seg_result2["coll"]
    seg_colonly2 = _colonly_objects(seg_coll2)
    _assert(len(seg_colonly2) == 3, "GUTTER-style segment should still get L/R curb colonlies + a "
            "pavement colonly, got %d" % len(seg_colonly2))
    print("collision smoketest: GUTTER curb style also gets collision proxies (incl. pavement)")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
