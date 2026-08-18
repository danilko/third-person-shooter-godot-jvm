#!/usr/bin/env python3
"""
smoketest_collision.py -- headless verification for road_kit_authoring's `-colonly` collision
proxies (`kit_common.bake_colonly_proxies`, `kit_common.colonly_mesh_evaluated`).

2026-08 (crash-surface fix): baking a `-colonly` proxy live during authoring/rebuild was the
single most expensive AND most crash-prone live-edit operation (a `to_mesh()` depsgraph bake) for
zero authoring-time value (the proxy is invisible, existing purely so Godot's importer builds a
`CollisionShape3D`). Moved to EXPORT TIME (`tools/export_world.py` calls `kc.bake_colonly_proxies`
once over the whole scene right before glTF export) -- same exact bake, same resulting mesh, just
deferred to when it's actually needed. This test therefore explicitly calls `bake_colonly_proxies`
itself (simulating what the export step does) rather than expecting colonly objects to already
exist right after a plain build -- they deliberately do NOT anymore.

2026-08-13 (`ROAD_KIT_REDESIGN.md` §7): the SEGMENT/TRANSITION cases no longer assert a proxy COUNT
("2 curb colonlies + 1 pavement colonly = 3") or proxy names. How many proxies a piece gets is a
property of how many objects it was built from -- three on the sibling-object path, one on the
modifier-stack path, where the whole road is one carrier -- and neither number says anything about
whether a car will drive on it. What matters, and what is asserted instead, is that the collision
pass COVERS the piece: every proxy carries real geometry, and their combined footprint reaches as
far laterally as the visible road does, measured from the spine by `lib/piece_probe.py`. A proxy
set that misses the curb line is a car clipping through a curb; a proxy set of the "wrong" count
covering the same ground is not a defect. The INTERSECTION cases keep their counts, since a pad and
four corner curbs are real objects on every path.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_collision.py
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

COVER_TOL = 0.05   # metres; a proxy may round a corner, it may not miss the road's edge


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _colonly_objects(coll):
    return [o for o in coll.objects if o.name.endswith("-colonly")]


def _assert_covers(coll, label):
    """The collision pass must cover the piece: real geometry everywhere, and a combined lateral
    footprint that reaches the visible road's own edges. Says nothing about HOW MANY proxies do
    it -- see this file's header."""
    proxies = _colonly_objects(coll)
    _assert(proxies, "%s: baking produced no collision proxy at all" % label)
    for c in proxies:
        _assert(len(c.data.vertices) > 0 and len(c.data.polygons) > 0,
                "%s: collision proxy %r has no geometry -- it would be an invisible hole"
                % (label, c.name))
    visual = pp.span(coll)
    covered = pp.span(coll, include_colonly=True, objects=proxies)
    _assert(visual is not None and covered is not None,
            "%s: could not measure the piece against its spine (summary: %r)"
            % (label, pp.geometry_summary(coll)))
    _assert(covered[0] <= visual[0] + COVER_TOL and covered[1] >= visual[1] - COVER_TOL,
            "%s: the collision pass does not cover the road -- the piece spans %.3f..%.3f m from "
            "its spine but the proxies only cover %.3f..%.3f m"
            % (label, visual[0], visual[1], covered[0], covered[1]))
    return proxies, visual, covered


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()   # needed for build_lane_transition's PROFILE curb below

    # ======================================================================== intersection pad + curb
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    _assert(_colonly_objects(coll) == [],
            "a fresh build should have NO -colonly objects yet (moved to export-time)")
    print("collision smoketest: a fresh build has no live -colonly objects (moved to export-time)")

    kc.bake_colonly_proxies(coll.objects, coll)
    colonly = _colonly_objects(coll)
    pad_col = next((o for o in colonly if o.name.startswith("pad_")), None)
    curb_cols = [o for o in colonly if o.name.startswith("curb_")]
    _assert(pad_col is not None, "intersection should get a pad_*-colonly collision proxy")
    _assert(len(pad_col.data.vertices) > 0 and len(pad_col.data.polygons) > 0,
            "pad colonly mesh should have real geometry")
    _assert(pad_col.get("proxy_for") == "pad_%s" % coll.name,
            "pad colonly should tag proxy_for back to the pad's own name")
    _assert(len(curb_cols) == 4, "4-way should get 4 curb_*-colonly proxies (one per corner), got %d"
            % len(curb_cols))
    for c in curb_cols:
        _assert(len(c.data.vertices) > 0 and len(c.data.polygons) > 0,
                "curb colonly '%s' mesh should have real geometry" % c.name)
    print("collision smoketest: bake_colonly_proxies produced a pad colonly + %d curb colonlies, "
          "all with real geometry" % len(curb_cols))

    # Regression check (2026-07-27, user-reported "vehicle/character some distance from the road
    # mesh"): GN_JunctionPad's `Fill Curve` node silently flattens every evaluated vertex to world
    # Z=0 regardless of the input curve's real height -- the visual pad and its colonly proxy must
    # sit at exactly the same height.
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
            "%.4f, got range [%.4f, %.4f]" % (expected_z, min(col_zs), max(col_zs)))
    print("collision smoketest: visual pad sits flush with its colonly proxy at the real "
          "lane_surface_z height (Z=%.4f), not flattened to 0 by Fill Curve" % expected_z)

    # A rebuild must NOT resurrect any colonly objects on its own (that's the whole point of
    # moving this to export-time) -- rebuild_intersection_in_place's own mark-and-sweep
    # (sweep_untouched_boundaries) correctly treats a previously-baked colonly as stale, since
    # nothing re-confirms it during a rebuild anymore, and removes it.
    opint.rebuild_intersection_in_place(context, coll)
    coll = opint.local_collection(coll.name)
    _assert(_colonly_objects(coll) == [],
            "rebuild_intersection_in_place must NOT leave colonly proxies live anymore -- they "
            "should have been swept as stale (nothing re-confirms them during a rebuild)")
    print("collision smoketest: rebuild correctly sweeps away colonly proxies baked before it "
          "(they're export-time-only now, never carried across a rebuild)")

    # Re-baking after the rebuild must be idempotent (same object identity, no duplicates) across
    # two CONSECUTIVE bakes (no rebuild in between) -- matching kit_common.junction_pad/curb_loop's
    # own update-in-place contract for the boundary objects colonly copies from.
    kc.bake_colonly_proxies(coll.objects, coll)
    colonly_after = _colonly_objects(coll)
    _assert(len(colonly_after) == len(colonly),
            "re-baking after a rebuild should produce exactly one colonly per pad/corner, no "
            "duplicates: before=%d after=%d" % (len(colonly), len(colonly_after)))
    pad_col2 = coll.objects["pad_%s" % coll.name + "-colonly"]
    pad_col2_ptr = pad_col2.as_pointer()
    kc.bake_colonly_proxies(coll.objects, coll)   # second consecutive bake, nothing changed
    pad_col3 = coll.objects["pad_%s" % coll.name + "-colonly"]
    _assert(pad_col3.as_pointer() == pad_col2_ptr,
            "two consecutive bakes with nothing changed in between should update the SAME "
            "colonly object in place, not create a new one")
    print("collision smoketest: re-baking is idempotent -- same object identity across repeated "
          "calls with no changes in between")

    # join_visual_mesh=True bakes pad_/curb_'s GN away into one combined "mesh_*" object BEFORE
    # bake_colonly_proxies ever runs -- so it gets exactly ONE colonly proxy covering the whole
    # combined footprint (the "mesh_*" special case), not the per-piece fragmentation a non-joined
    # build gets. This is intended: join_visual_mesh exists to reduce object count in the first
    # place, so collision collapsing the same way is consistent, not a regression.
    result2 = opint.build_intersection_geometry(
        context, scene_coll, (100.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, True, "", "", 'LEFT')   # join_visual_mesh=True
    coll2 = result2["coll"]
    mesh_objs = [o for o in coll2.objects if o.name.startswith("mesh_")]
    _assert(len(mesh_objs) == 1, "join_visual_mesh=True should produce exactly one joined "
            "visual mesh object")
    kc.bake_colonly_proxies(coll2.objects, coll2)
    colonly2 = _colonly_objects(coll2)
    _assert(len(colonly2) == 1, "join_visual_mesh=True should get exactly ONE colonly proxy "
            "covering the joined mesh's whole footprint, got %d" % len(colonly2))
    _assert(colonly2[0].name == mesh_objs[0].name + "-colonly",
            "the colonly proxy should be named after the joined mesh object, got %r"
            % colonly2[0].name)
    _assert(len(colonly2[0].data.vertices) > 0 and len(colonly2[0].data.polygons) > 0,
            "the joined-mesh colonly should have real geometry")
    print("collision smoketest: join_visual_mesh=True gets one combined colonly proxy matching "
          "the joined visual mesh")

    # ============================================================================== straight segment
    seg_result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], 5.0, 1, 1,
        'BOX', 'BOX', 0.15, 0.25, False, "", "")
    seg_coll = seg_result["coll"]
    kc.bake_colonly_proxies(seg_coll.objects, seg_coll)
    seg_proxies, seg_visual, seg_covered = _assert_covers(seg_coll, "straight segment")
    print("collision smoketest: a straight segment's %d collision prox%s cover its full width "
          "(road %.2f..%.2f m from the spine, collision %.2f..%.2f m)"
          % (len(seg_proxies), "y" if len(seg_proxies) == 1 else "ies",
             seg_visual[0], seg_visual[1], seg_covered[0], seg_covered[1]))

    # ============================================================================= lane transition
    ret = bpy.ops.rka.build_lane_transition(
        'EXEC_DEFAULT', direction_deg=0.0, length=20.0, lane_width=5.0, lanes_a=2, lanes_b=1,
        lanes_backward_a=0, lanes_backward_b=0, align='right', curb_l_style='PROFILE',
        curb_r_style='PROFILE', curb_asset_collection='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "build_lane_transition did not finish: %s" % (ret,))
    tr_coll = next(c for c in bpy.data.collections if c.name.startswith("Transition_"))
    kc.bake_colonly_proxies(tr_coll.objects, tr_coll)
    tr_proxies, tr_visual, tr_covered = _assert_covers(tr_coll, "lane transition")
    # A taper is the case a single-width proxy would silently get wrong: the piece is wider at one
    # end than the other, so a proxy that covered only the narrow end would still "have geometry".
    tr_st = pp.stations(tr_coll, include_colonly=True, objects=tr_proxies)
    s_max = max(s for (s, _l, _d) in tr_st)
    near = [abs(lat) for (s, lat, _d) in tr_st if s < s_max * 0.25]
    far = [abs(lat) for (s, lat, _d) in tr_st if s > s_max * 0.75]
    _assert(near and far and abs(max(near) - max(far)) > 1.0,
            "a 2 -> 1 lane transition's collision should TAPER like the road does, but its proxies "
            "are %.2f m wide at one end and %.2f m at the other" % (max(near), max(far)))
    print("collision smoketest: a lane transition's collision covers its full width and tapers "
          "with it (%.2f m -> %.2f m from the spine)" % (max(near), max(far)))

    # ==================================================================== GUTTER style curb collision
    seg_result2 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 200.0, 0.0), (40.0, 200.0, 0.0)], 5.0, 1, 1,
        'GUTTER', 'GUTTER', 0.2, 0.6, False, "", "")
    seg_coll2 = seg_result2["coll"]
    kc.bake_colonly_proxies(seg_coll2.objects, seg_coll2)
    _p2, _v2, _c2 = _assert_covers(seg_coll2, "GUTTER-style segment")
    print("collision smoketest: a GUTTER curb style is covered too (road %.2f..%.2f m, collision "
          "%.2f..%.2f m from the spine)" % (_v2[0], _v2[1], _c2[0], _c2[1]))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
