#!/usr/bin/env python3
"""
smoketest_gn_boundary_persist.py -- headless verification for the 2026-08 crash-surface fix:
`clear_generated_mesh_objects(coll, keep_gn_boundaries=True)` + `_poly_curve_with_radius`'s
update-in-place path mean an intersection's pad_*/curb_* and a segment's curb_* boundary
objects are no longer deleted and recreated on every live-edit rebuild -- they're the SAME
object, with its point data rewritten, exactly like a spine already was. This is what actually
removes the "delete the object a modal Transform operator is still holding" crash class the
(now-removed) Freeze/Unfreeze operators used to work around, rather than just avoiding
triggering it via debounce timing.

Also confirms the user-reported "curb doesn't move when a linked arm widens" gap is closed: a
segment's curb boundary points (not just its pavement spine radius) actually shift outward to
match a linked arm's new width.

RUN: blender --background --python addons/road_kit_authoring/smoketest_gn_boundary_persist.py
"""
import bpy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ---------------------------------------------------------------- intersection pad/curb
    # object IDENTITY survives a rebuild (no delete+recreate, no ".001" duplicate).
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    pad = inter_coll.objects["pad_%s" % inter_coll.name]
    pad_ptr_before = pad.as_pointer()
    curb0 = next(o for o in inter_coll.objects if o.name.startswith("curb_%s_" % inter_coll.name))
    curb_ptr_before = curb0.as_pointer()
    n_curbs_before = len([o for o in inter_coll.objects
                           if o.name.startswith("curb_%s_" % inter_coll.name)])

    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    origin = opint.get_or_create_origin_marker(inter_coll)
    ox, oy = origin.location.x, origin.location.y
    dist = math.hypot(arm_n.location.x - ox, arm_n.location.y - oy)
    rad = math.radians(20.0)   # rotate arm N by 20 deg -- same point count, should update in place
    arm_n.location.x = ox + dist * math.cos(rad)
    arm_n.location.y = oy + dist * math.sin(rad)
    opint.rebuild_intersection_in_place(context, inter_coll)

    inter_coll = opint.local_collection(inter_coll.name)
    pad_after = inter_coll.objects["pad_%s" % inter_coll.name]
    _assert(pad_after.as_pointer() == pad_ptr_before,
            "the intersection's pad object should be the SAME object after a rebuild, not a "
            "fresh delete+recreate")
    curbs_after = [o for o in inter_coll.objects if o.name.startswith("curb_%s_" % inter_coll.name)]
    _assert(len(curbs_after) == n_curbs_before,
            "curb object count should stay the same (%d), got %d -- no duplicate accumulation"
            % (n_curbs_before, len(curbs_after)))
    curb0_after = next((o for o in curbs_after if o.as_pointer() == curb_ptr_before), None)
    _assert(curb0_after is not None,
            "at least one curb object should have survived as the SAME object identity")
    print("gn_boundary_persist smoketest: intersection pad/curb objects survived a rebuild by "
          "IDENTITY (update-in-place, not delete+recreate)")

    # ---------------------------------------------------------------------------- segment curb
    # actually widens to match a linked arm's new lane count (not just the pavement radius).
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    curb_l = seg_coll.objects["curb_%s_L" % seg_coll.name]
    curb_l_ptr_before = curb_l.as_pointer()
    spine = bpy.data.objects.get(seg_coll["rka_curve_object"])
    p0 = spine.data.splines[0].points[0].co
    cpt_before = curb_l.data.splines[0].points[0].co
    dist_before = math.hypot(cpt_before[0] - p0[0], cpt_before[1] - p0[1])

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.adjust_arm_lanes('EXEC_DEFAULT', delta=2)   # 1 -> 3 lanes
    _assert(ret == {'FINISHED'}, "adjust_arm_lanes did not finish: %s" % (ret,))

    seg_coll = opint.local_collection(seg_coll.name)
    curb_l_after = seg_coll.objects["curb_%s_L" % seg_coll.name]
    _assert(curb_l_after.as_pointer() == curb_l_ptr_before,
            "segment curb_L should survive the width sync by IDENTITY too")
    spine = bpy.data.objects.get(seg_coll["rka_curve_object"])
    p0_after = spine.data.splines[0].points[0].co
    cpt_after = curb_l_after.data.splines[0].points[0].co
    dist_after = math.hypot(cpt_after[0] - p0_after[0], cpt_after[1] - p0_after[1])
    _assert(dist_after > dist_before + 5.0,
            "widening the linked arm from 1 to 3 lanes should push the segment's curb boundary "
            "outward by ~2 lane-widths (10m) -- was %.2fm from centerline, now %.2fm"
            % (dist_before, dist_after))
    print("gn_boundary_persist smoketest: segment curb boundary widened to match the linked arm "
          "(%.2fm -> %.2fm from centerline), by identity, no delete/recreate" %
          (dist_before, dist_after))

    # NOTE: collision proxy (-colonly) identity/sweep-on-rebuild behavior is no longer tested
    # here -- colonly proxies are export-time-only now (kit_common.bake_colonly_proxies, called
    # from tools/export_world.py, never live during authoring/rebuild) -- see
    # smoketest_collision.py for that coverage.

    # --------------------------------------------------------------------------- ASSET curb
    # instancer objects also survive by identity, and their point count updates with the curb.
    asset_mesh = bpy.data.meshes.new("TestCurbAssetMesh")
    asset_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    asset_obj = bpy.data.objects.new("TestCurbAsset", asset_mesh)
    asset_coll = bpy.data.collections.new("TestCurbAssetColl")
    scene_coll.children.link(asset_coll)
    asset_coll.objects.link(asset_obj)

    asset_result = opint.build_intersection_geometry(
        context, scene_coll, (200.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'ASSET', 0.15, 0.25,
        None, False, "", "", 'LEFT', curb_asset_collection=asset_coll.name, curb_asset_spacing=3.0)
    asset_inter_coll = asset_result["coll"]
    asset_curb = next((o for o in asset_inter_coll.objects
                        if o.name.startswith("curb_%s_" % asset_inter_coll.name)), None)
    _assert(asset_curb is not None, "sanity: ASSET-style intersection should have a curb instancer")
    asset_curb_ptr = asset_curb.as_pointer()
    n_pts_before = len(asset_curb.data.vertices)

    asset_arm = next(o for o in asset_inter_coll.objects if o.get("rka_arm_name") == "N")
    asset_origin = opint.get_or_create_origin_marker(asset_inter_coll)
    aox, aoy = asset_origin.location.x, asset_origin.location.y
    adist = math.hypot(asset_arm.location.x - aox, asset_arm.location.y - aoy)
    arad = math.radians(15.0)
    asset_arm.location.x = aox + adist * math.cos(arad)
    asset_arm.location.y = aoy + adist * math.sin(arad)
    opint.rebuild_intersection_in_place(context, asset_inter_coll)
    asset_inter_coll = opint.local_collection(asset_inter_coll.name)
    asset_curb_after = next((o for o in asset_inter_coll.objects
                              if o.name.startswith("curb_%s_" % asset_inter_coll.name)), None)
    _assert(asset_curb_after is not None and asset_curb_after.as_pointer() == asset_curb_ptr,
            "ASSET-style curb instancer should survive a rebuild by IDENTITY, not delete+recreate")
    print("gn_boundary_persist smoketest: ASSET-style curb instancer survived a rebuild by "
          "identity (%d pts before, %d pts after)" %
          (n_pts_before, len(asset_curb_after.data.vertices)))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
