#!/usr/bin/env python3
"""
smoketest_degenerate_spine.py -- coincident points in a road path must never reach the geometry.

WHY THIS EXISTS. A zero-length step has no defined tangent, and every part of a road piece
derives its frame from the tangent: the spine normal, the swept pavement cross-section, the curb
offsets, the lane centerlines. One repeated control point flips that frame and the road visibly
TWISTS at the spot -- and it never raises, so the only symptom is geometry that looks wrong in
the viewport. That was a real bug: a generated ramp emitted its gore point twice (as its lead-in
AND as its curve's own first sample) and the built pavement corkscrewed at the end.

The fix belongs to the ADDON, not to whatever produced the path. Duplicate points arrive from
everywhere -- a hand-authored curve with a double-clicked vertex, a closed ring carrying a
repeated closing vertex, any generator whose lead-in coincides with its first sample -- so
guarding at each producer means remembering the rule forever. `_build_segment_from_points` is
the single shared entry every segment in this addon passes through, so it is guarded there.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_degenerate_spine.py
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

import kit_common as kc
import road_kit_authoring as rka
from road_kit_authoring.ops_segment import _dedupe_spine_points, _build_segment_from_points
from road_kit_authoring.ops_intersection import RkaBuildError


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    ctx = bpy.context
    scene_coll = ctx.scene.collection

    # ------------------------------------------------------------------ the helper itself
    dup_lead = [(0.0, 0.0, 12.0), (0.0, 0.0, 12.0), (40.0, 0.0, 11.0), (80.0, 0.0, 10.0)]
    _assert(len(_dedupe_spine_points(dup_lead)) == 3,
            "a repeated LEAD-IN point must be removed (this was the ramp-gore bug)")
    dup_mid = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (40.0, 0.0, 0.0), (80.0, 0.0, 0.0)]
    _assert(len(_dedupe_spine_points(dup_mid)) == 3, "a repeated MIDDLE point must be removed")
    dup_end = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (80.0, 0.0, 0.0), (80.0, 0.0, 0.0)]
    _assert(len(_dedupe_spine_points(dup_end)) == 3, "a repeated CLOSING point must be removed")
    # Same XY, different Z is STILL degenerate for the horizontal frame.
    vert = [(0.0, 0.0, 0.0), (0.0, 0.0, 9.0), (60.0, 0.0, 9.0)]
    _assert(len(_dedupe_spine_points(vert)) == 2,
            "coincident XY at different Z is still a zero-length horizontal step")
    clean = [(0.0, 0.0, 0.0), (40.0, 0.0, 2.0), (80.0, 0.0, 4.0)]
    _assert(_dedupe_spine_points(clean) == [tuple(p) for p in clean],
            "a clean path must pass through completely unchanged")
    print("degenerate_spine smoketest: lead-in / middle / closing / vertical duplicates removed, "
          "clean paths untouched")

    # -------------------------------------------- a duplicate must not reach the geometry
    res = _build_segment_from_points(
        ctx, scene_coll, dup_lead, 3.5, 1, 0, 'NONE', 'NONE', 0.15, 0.25, True, "", "",
        base_name="DupLead")
    # `pts` in the result is the path the piece was ACTUALLY built from — the authoritative
    # answer to "did the duplicate reach the geometry", whatever object shape the spine takes.
    co = [tuple(p)[:3] for p in res["pts"]]
    _assert(len(co) == 3, "the built path should carry 3 points, got %d: %s" % (len(co), co))
    for a, b in zip(co, co[1:]):
        _assert(math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-4,
                "the built path still contains a zero-length step: %s -> %s" % (a, b))
    print("degenerate_spine smoketest: built path has no zero-length step (%d points)" % len(co))

    # ------------------------------------------------- the twist itself: frame stays upright
    # Sweep the piece and check no pavement quad flips its normal, which is what a frame flip
    # looks like in the geometry rather than in the control points.
    dg = ctx.evaluated_depsgraph_get()
    pave = None
    for o in res["coll"].objects:
        if o.name.startswith("mesh_") and o.type == 'MESH':
            pave = o
            break
    if pave is not None:
        me = bpy.data.meshes.new_from_object(pave.evaluated_get(dg), depsgraph=dg)
        ups = [p.normal.z for p in me.polygons]
        bpy.data.meshes.remove(me)
        if ups:
            flipped = sum(1 for z in ups if z < 0.0)
            _assert(flipped == 0 or flipped == len(ups),
                    "pavement normals are inconsistent (%d of %d flipped) — the cross-section "
                    "frame twisted along the sweep" % (flipped, len(ups)))
            print("degenerate_spine smoketest: pavement normals consistent across %d face(s) "
                  "— no frame twist" % len(ups))

    # ------------------------------------------------------- an all-duplicate path is refused
    try:
        _build_segment_from_points(
            ctx, scene_coll, [(5.0, 5.0, 0.0), (5.0, 5.0, 0.0), (5.0, 5.0, 1.0)],
            3.5, 1, 0, 'NONE', 'NONE', 0.15, 0.25, True, "", "", base_name="AllDup")
        raise AssertionError("a path that is one repeated point must be REFUSED, not built")
    except RkaBuildError as exc:
        _assert("2 distinct points" in str(exc), "unhelpful refusal message: %s" % exc)
    print("degenerate_spine smoketest: a path of one repeated point is refused with a reason")

    print("smoketest_degenerate_spine: OK")


if __name__ == "__main__":
    main()
