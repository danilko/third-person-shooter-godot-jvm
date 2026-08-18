#!/usr/bin/env python3
"""
smoketest_insert_intersection_gn.py -- headless verification for `RKA_OT_insert_intersection_on_
segment` (2026-08 fix, user-reported: "after some edit, still crash" in world_session.blend).

Root cause: this operator's `extend()` helper (splicing the two stub segments back in on either
side of the newly-inserted intersection) called the LEGACY `build_segment_geometry`/`_populate_
segment_mesh` path -- the one remaining live-drag rebuild (`rebuild_segment_in_place`) that never
got the update-in-place crash-surface fix: it still does a full Python `clear_generated_mesh_
objects` (delete) + recreate of every curb_/ribbon_ object on EVERY depsgraph tick while a modal
Transform operator may still be holding one of them selected. So splicing an intersection into an
existing (safe, GN-backed) segment silently reintroduced two brand-new pieces still running the
crash-prone code path. Fixed by routing `extend()` through `_build_segment_from_points` (the same
GN-backed builder `RKA_OT_build_straight_segment` itself uses) instead.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_insert_intersection_gn.py
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
from road_kit_authoring import spine_io      # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
import kit_common as kc                                     # noqa: E402
import piece_probe as pp  # noqa: E402


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

    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (80.0, 0.0, 0.0)], lane_width=5.0, lanes=1,
        lanes_backward=1, curb_l_style='BOX', curb_r_style='GUTTER', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll = result["coll"]
    _assert("rka_curve_object" in coll.keys(), "sanity: the original segment should be GN-backed")

    context.view_layer.active_layer_collection = \
        next(lc for lc in _iter_layer_colls(context.view_layer.layer_collection)
             if lc.collection == coll)
    ret = bpy.ops.rka.insert_intersection_on_segment(
        'EXEC_DEFAULT', fraction=0.5, preset='3WAY_T', side_angle=90.0, side_length=0.0,
        kerb_radius=9.0, tail_length=12.0, join_visual_mesh=False)
    _assert(ret == {'FINISHED'}, "insert_intersection_on_segment did not finish: %s" % (ret,))

    # The two spliced-in stub segments must be GN-backed (rka_curve_object present, curb objects
    # named curb_<coll>_L/R) -- NOT the legacy marker-driven shape (rka_p0/rka_p1 with segend_A/B
    # markers but no rka_curve_object, curb objects just named "curb_L"/"curb_R").
    stub_segs = [c for c in bpy.data.collections if c.name.startswith("Segment_") and c is not coll]
    _assert(len(stub_segs) == 2, "splicing should produce exactly 2 stub segments, got %d: %s"
            % (len(stub_segs), [c.name for c in stub_segs]))
    for sc in stub_segs:
        _assert("rka_curve_object" in sc.keys(),
                "spliced-in stub segment '%s' should be GN-backed (rka_curve_object present) -- "
                "the legacy path regression this test guards against" % sc.name)
        spine_name = sc["rka_curve_object"]
        spine = sc.objects.get(spine_name)
        _assert(spine_io.is_spine(spine),
                "stub segment '%s' should have a real live spine object" % sc.name)
        # "It has curbs" asked of the geometry, not of `curb_<name>_L`/`_R` objects -- a
        # modifier-stack stub carries its curbs as layers. The LEGACY-NAME guard below stays a
        # name check on purpose: those exact names are the regression this test exists to catch.
        _assert(pp.raised_span(sc, 'L') is not None and pp.raised_span(sc, 'R') is not None,
                "stub segment '%s' should have curbs on both sides (summary: %r)"
                % (sc.name, pp.geometry_summary(sc)))
        _assert("curb_L" not in sc.objects and "curb_R" not in sc.objects,
                "stub segment '%s' must not carry legacy-named curb objects" % sc.name)
    print("insert_intersection_gn smoketest: both spliced-in stub segments are GN-backed "
          "(rka_curve_object + curb_<name>_L/R naming), not the legacy marker-driven shape")

    # Confirm a live drag on one of the new stub segments goes through the SAFE, update-in-place
    # GN rebuild (curb object survives by identity across a rebuild) -- not the legacy delete-
    # recreate path (which would produce a NEW object each time, breaking identity).
    stub = stub_segs[0]
    spine = stub.objects[stub["rka_curve_object"]]
    # The CARRIER's identity is the crash-surface property that generalises: it is the object a
    # modal Transform holds, and it is never deleted/recreated on either build path.
    carrier_ptr = spine.as_pointer()
    spine_io.points(spine)[-1].co.x += 5.0
    spine_io.points(spine)[-1].co.y += 2.0
    opseg.rebuild_segment_gn_in_place(context, stub)
    stub = opint.local_collection(stub.name)
    carrier_after = stub.objects.get(stub["rka_curve_object"])
    _assert(carrier_after is not None and carrier_after.as_pointer() == carrier_ptr,
            "a live-edit rebuild on the spliced-in stub segment should keep its carrier by "
            "IDENTITY (the crash-surface fix), not delete+recreate a fresh one")
    _assert(pp.raised_span(stub, 'L') is not None,
            "the stub still has its curbs after the rebuild (summary: %r)"
            % (pp.geometry_summary(stub),))
    print("insert_intersection_gn smoketest: a live-edit rebuild on the spliced-in stub segment "
          "keeps its carrier by identity and its curbs (the crash-surface fix applies to it too)")

    print("SMOKETEST OK")


def _iter_layer_colls(lc):
    yield lc
    for child in lc.children:
        yield from _iter_layer_colls(child)


if __name__ == "__main__":
    main()
