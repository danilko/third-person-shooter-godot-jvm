#!/usr/bin/env python3
"""
smoketest_legacy_segment_persist.py -- headless verification for the 2026-08 crash-surface fix
applied to `ops_segment`'s LEGACY point-segment path (`build_segment_geometry`/`_populate_segment_
mesh`/`rebuild_segment_in_place`) -- the one piece shape that never got the GN-modifier treatment
the rest of the addon already has (its pavement is per-lane `flat_ribbon` quad strips, its curb is
`swept_wall`/`swept_profile`, its collision proxy is a live `colonly_swept_between` bake, none of
them GN-modifier-backed). No UI operator creates a fresh one anymore (`RKA_OT_insert_intersection_
on_segment`'s `extend()` now goes through the GN-backed `_build_segment_from_points` instead), but
`rebuild_segment_in_place` is still reachable for any ALREADY-EXISTING legacy piece (e.g. content
authored before that unification, or before this fix). Before this fix, EVERY drag on such a piece
deleted and recreated curb_L/curb_R/ribbon_*/pave_*-colonly from scratch -- the exact "delete an
object a modal Transform operator might still be holding" crash class the rest of the addon closed.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_legacy_segment_persist.py
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

    result = opseg.build_segment_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), direction_deg=0.0, length=40.0, lane_width=5.0,
        lanes=1, curb_style='BOX', curb_height=0.15, curb_thickness=0.25, bend=0.0,
        curve_segments=8, elevation_delta=0.0, bend_z=0.0, join_visual_mesh=False, export_path="",
        gltf_export_path="", lanes_backward=1)
    coll = result["coll"]
    _assert("rka_curve_object" not in coll.keys(),
            "sanity: this IS the legacy shape (no rka_curve_object, unlike the GN-backed path)")

    curb_l = coll.objects.get("curb_L")
    _assert(curb_l is not None, "sanity: legacy segment should have a curb_L object")
    curb_l_ptr = curb_l.as_pointer()
    ribbon_before = next(o for o in coll.objects if o.name.startswith("ribbon_"))
    ribbon_ptr = ribbon_before.as_pointer()
    n_generated_before = len([o for o in coll.objects
                               if o.name.startswith(("curb_", "ribbon_", "pave_"))])

    # Unlike the GN path, the legacy path bakes its pavement collision proxy LIVE (unconditionally,
    # inside `_populate_segment_mesh` itself) -- it already exists right after the initial build,
    # no separate export-time `bake_colonly_proxies` step needed to produce it.
    pave_col = coll.objects.get("pave_%s-colonly" % coll.name)
    _assert(pave_col is not None, "sanity: legacy segment pavement should get a colonly proxy")
    pave_col_ptr = pave_col.as_pointer()

    # Simulate a drag: move segend_B (changes length/direction) and rebuild in place.
    b_obj = next(o for o in coll.objects if o.get("rka_segend") == "B")
    b_obj.location.x += 15.0
    b_obj.location.y += 8.0
    opseg.rebuild_segment_in_place(context, coll)

    coll = opint.local_collection(coll.name)
    curb_l_after = coll.objects.get("curb_L")
    _assert(curb_l_after is not None, "curb_L should still exist after the rebuild")
    _assert(curb_l_after.as_pointer() == curb_l_ptr,
            "legacy segment's curb_L should survive a rebuild by IDENTITY (the crash-surface "
            "fix), not delete+recreate a fresh object")
    _assert(tuple(curb_l_after.location) == (0.0, 0.0, 0.0)
            and tuple(curb_l_after.rotation_euler) == (0.0, 0.0, 0.0),
            "reused curb_L's own transform should stay at identity (absolute world-space point "
            "data), got location=%r rotation=%r"
            % (tuple(curb_l_after.location), tuple(curb_l_after.rotation_euler)))

    ribbon_after = next((o for o in coll.objects if o.as_pointer() == ribbon_ptr), None)
    _assert(ribbon_after is not None,
            "at least the SAME NUMBER of ribbon_* objects should exist after rebuild, and (since "
            "lane count didn't change) one should be the SAME object identity as before")

    n_generated_after = len([o for o in coll.objects
                              if o.name.startswith(("curb_", "ribbon_", "pave_"))])
    _assert(n_generated_after == n_generated_before,
            "object count should stay the same across a rebuild with unchanged lane/curb-style "
            "settings -- before=%d after=%d (no orphan accumulation, no missing pieces)"
            % (n_generated_before, n_generated_after))
    print("legacy_segment_persist smoketest: curb_L/ribbon_* survived the rebuild by IDENTITY "
          "(no delete+recreate), transform stayed at identity, object count unchanged")

    pave_col_after = coll.objects.get("pave_%s-colonly" % coll.name)
    _assert(pave_col_after is not None and pave_col_after.as_pointer() == pave_col_ptr,
            "the legacy pavement collision proxy should also survive the rebuild by identity")
    print("legacy_segment_persist smoketest: the legacy pavement collision proxy also survived "
          "by identity")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
