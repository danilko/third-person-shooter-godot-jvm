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
segment's curb (not just its pavement) actually shifts outward to match a linked arm's new width.

2026-08-13 (`ROAD_KIT_REDESIGN.md` §7). The INTERSECTION half still asserts object identity, because
an intersection's pad and curb corners are real objects on every build path and their identity is
precisely the crash-surface property under test. The SEGMENT half no longer does: it used to reach
for `seg_coll.objects["curb_<piece>_L"]` and read that Curve's control points, which is a statement
about the sibling-object build path rather than about the road. Under the modifier-stack path the
curb is a modifier on the carrier and no such object exists -- yet the two things a user cares
about are unchanged and still checkable, so that is what it checks now:

  * the piece's SPINE survives the rebuild by identity (the carrier is what a modal Transform
    operator holds, and it is never deleted/recreated on either path -- the generalisation of the
    old per-curb identity check);
  * widening the linked arm carries the raised curb geometry outward with the pavement, measured
    from the spine by `lib/piece_probe.py`.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_gn_boundary_persist.py
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
import piece_probe as pp                                    # noqa: E402


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
    bpy.ops.rka.link_curb_kit_library()   # needed for extend_from_arm's PROFILE curb below

    # ---------------------------------------------------------------- intersection pad/curb
    # object IDENTITY survives a rebuild (no delete+recreate, no ".001" duplicate).
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'PROFILE', 0.15, 0.25,
        None, False, "", "", 'LEFT', curb_asset_collection='Kit_Curb_JerseyBarrier_L2')
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
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=40.0,
                                       curb_l_style='PROFILE', curb_r_style='PROFILE',
                                       curb_asset_collection='Kit_Curb_JerseyBarrier_L2')
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    # The SPINE is the piece's carrier on both build paths, and it is the object a modal Transform
    # is holding when the user drags a road -- so its identity is the one that has to survive.
    spine_ptr_before = bpy.data.objects.get(seg_coll["rka_curve_object"]).as_pointer()
    curb_before = pp.raised_outer_edge(seg_coll, 'L')
    _assert(curb_before is not None,
            "sanity: a PROFILE-curbed segment should carry raised geometry on its left "
            "(summary: %r)" % (pp.geometry_summary(seg_coll),))

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.adjust_arm_lanes('EXEC_DEFAULT', delta=2)   # 1 -> 3 lanes
    _assert(ret == {'FINISHED'}, "adjust_arm_lanes did not finish: %s" % (ret,))

    seg_coll = opint.local_collection(seg_coll.name)
    spine_after = bpy.data.objects.get(seg_coll["rka_curve_object"])
    _assert(spine_after is not None and spine_after.as_pointer() == spine_ptr_before,
            "the segment's spine/carrier must survive the width sync by IDENTITY -- a rebuild that "
            "deletes and recreates it is the crash surface this whole mechanism removes")
    curb_after = pp.raised_outer_edge(seg_coll, 'L')
    _assert(curb_after is not None,
            "the curb vanished when the linked arm widened (summary: %r)"
            % (pp.geometry_summary(seg_coll),))
    _assert(curb_after > curb_before + 5.0,
            "widening the linked arm from 1 to 3 lanes should carry the segment's curb outward by "
            "~2 lane-widths (10 m) -- the raised geometry reached %.2f m from the spine, now "
            "%.2f m" % (curb_before, curb_after))
    print("gn_boundary_persist smoketest: the segment's curb moved outward with the widened arm "
          "(%.2fm -> %.2fm from the spine) while the carrier survived by identity" %
          (curb_before, curb_after))

    # NOTE: collision proxy (-colonly) identity/sweep-on-rebuild behavior is no longer tested
    # here -- colonly proxies are export-time-only now (kit_common.bake_colonly_proxies, called
    # from tools/export_world.py, never live during authoring/rebuild) -- see
    # smoketest_collision.py for that coverage.

    # --------------------------------------------------------------------------- PROFILE curb
    # sweep objects also survive by identity, and their point count updates with the curb.
    # (2026-08: this used to exercise ASSET style, since retired -- "only have none/profile...
    # to simplify the code base" -- PROFILE is the direct functional replacement, see
    # CURB_STYLE_ITEMS' own retirement comment. A real box mesh is needed here, not a degenerate
    # flat triangle -- `extract_cross_section_profile` requires a closed >= 3-vertex cut loop.)
    asset_mesh = bpy.data.meshes.new("TestCurbAssetMesh")
    asset_mesh.from_pydata(
        [(0, -0.1, 0.0), (2, -0.1, 0.0), (2, 0.1, 0.0), (0, 0.1, 0.0),
         (0, -0.1, 0.3), (2, -0.1, 0.3), (2, 0.1, 0.3), (0, 0.1, 0.3)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    asset_obj = bpy.data.objects.new("TestCurbAsset", asset_mesh)
    asset_coll = bpy.data.collections.new("TestCurbAssetColl")
    scene_coll.children.link(asset_coll)
    asset_coll.objects.link(asset_obj)

    asset_result = opint.build_intersection_geometry(
        context, scene_coll, (200.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'PROFILE', 0.15, 0.25,
        None, False, "", "", 'LEFT', curb_asset_collection=asset_coll.name)
    asset_inter_coll = asset_result["coll"]
    asset_curb = next((o for o in asset_inter_coll.objects
                        if o.name.startswith("curb_%s_" % asset_inter_coll.name)), None)
    _assert(asset_curb is not None, "sanity: PROFILE-style intersection should have a curb sweep")
    asset_curb_ptr = asset_curb.as_pointer()

    def _eval_vert_count(o):
        # PROFILE-style curb is a live Curve+GN_CurbLoop object -- read the GN-EVALUATED
        # geometry, not `.data.vertices` (a Curve datablock has no such attribute).
        deps = context.evaluated_depsgraph_get()
        eo = o.evaluated_get(deps)
        me = eo.to_mesh()
        n = len(me.vertices)
        eo.to_mesh_clear()
        return n

    n_pts_before = _eval_vert_count(asset_curb)

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
            "PROFILE-style curb sweep should survive a rebuild by IDENTITY, not delete+recreate")
    print("gn_boundary_persist smoketest: PROFILE-style curb sweep survived a rebuild by "
          "identity (%d pts before, %d pts after)" %
          (n_pts_before, _eval_vert_count(asset_curb_after)))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
