#!/usr/bin/env python3
"""
smoketest_boundary_sweep.py -- headless verification for `ops_intersection.sweep_untouched_
boundaries`: the mark-and-sweep mechanism that closes the gap `clear_generated_mesh_objects(coll,
keep_gn_boundaries=True)` opened on its own (see that function's docstring) -- a rebuild whose
lane/median/curb-style COUNT SHRINKS relative to the previous rebuild must not leave the
now-unwanted old boundary object behind as a permanent orphan, and a curb style that switches
between an ASSET (Mesh+GN instancer) and a swept (Curve+GN) representation at the SAME object name
must not let Blender auto-suffix a ".001" onto the new one because the stale old-typed object is
still sitting on that name.

RUN: blender --background --python addons/road_kit_authoring/smoketest_boundary_sweep.py
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


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # -------------------------------------------------------------- median shrinking to 0 must
    # remove its curb_*_median_A/B objects, not leave them behind.
    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], lane_width=5.0, lanes=1,
        lanes_backward=1, curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="",
        median_width=4.0, median_style='BOX')
    coll = result["coll"]
    median_objs_before = [o for o in coll.objects if "median_" in o.name]
    _assert(len(median_objs_before) == 2, "sanity: median_width=4 should build 2 median curb "
                                           "objects (A/B) -- colonly proxies are export-time-only "
                                           "now, not live -- got %d" % len(median_objs_before))

    for o in bpy.data.objects:
        o.select_set(False)
    spine = bpy.data.objects.get(coll["rka_curve_object"])
    context.view_layer.objects.active = spine
    ret = bpy.ops.rka.adjust_median_width(delta=-10.0)   # clamps to 0
    _assert(ret == {'FINISHED'}, "adjust_median_width did not finish: %s" % (ret,))
    coll = bpy.data.collections.get(coll.name)
    median_objs_after = [o for o in coll.objects if "median_" in o.name]
    _assert(len(median_objs_after) == 0,
            "median_width -> 0 should remove the now-unwanted median curb objects, %d survived "
            "as orphans" % len(median_objs_after))
    print("boundary_sweep smoketest: shrinking median_width to 0 swept away its stale curb "
          "objects (%d -> %d)" % (len(median_objs_before), len(median_objs_after)))

    # ----------------------------------------------------------------------- curb style switch
    # ASSET <-> BOX at the same object name must not orphan/duplicate.
    asset_mesh = bpy.data.meshes.new("SweepTestAssetMesh")
    asset_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    asset_obj = bpy.data.objects.new("SweepTestAsset", asset_mesh)
    asset_coll = bpy.data.collections.new("SweepTestAssetColl")
    scene_coll.children.link(asset_coll)
    asset_coll.objects.link(asset_obj)

    result2 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 200.0, 0.0), (40.0, 200.0, 0.0)], lane_width=5.0, lanes=1,
        lanes_backward=1, curb_l_style='BOX', curb_r_style='NONE', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll2 = result2["coll"]
    curb_l_name = "curb_%s_L" % coll2.name
    curb_before = coll2.objects[curb_l_name]
    _assert(curb_before.type == 'CURVE', "sanity: BOX curb should be a Curve object")

    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = coll2.objects.get(coll2["rka_curve_object"])
    ret = bpy.ops.rka.set_curb_style(
        'EXEC_DEFAULT', side='L', style='ASSET', asset_collection=asset_coll.name)
    _assert(ret == {'FINISHED'}, "set_curb_style to ASSET did not finish: %s" % (ret,))
    coll2 = opint.local_collection(coll2.name)
    matches = [o for o in coll2.objects if o.name.startswith(curb_l_name)]
    _assert(len(matches) == 1,
            "switching L curb from BOX to ASSET should leave exactly ONE object at that slot, "
            "not a stale Curve plus a renamed '.001' Mesh -- found %d: %s"
            % (len(matches), [o.name for o in matches]))
    _assert(matches[0].name == curb_l_name and matches[0].type == 'MESH',
            "the surviving object should be the clean-named ASSET instancer -- got name=%r type=%r"
            % (matches[0].name, matches[0].type))
    print("boundary_sweep smoketest: switching curb style BOX -> ASSET left exactly one clean-"
          "named object, no stale Curve orphan and no '.001' rename")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
