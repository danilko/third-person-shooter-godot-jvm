#!/usr/bin/env python3
"""
smoketest_geometry_check.py -- the live-scene road-geometry warning (`ops_geometry_check`).

What it pins down:
  1. A well-formed road produces NO findings and NO markers -- a check that cries wolf gets
     ignored, taking the next real finding with it.
  2. A single sharp control point is reported as CORNER, on the live scene, with a marker dropped
     AT that point rather than at the piece's origin.
  3. A hairpin's fold is MEASURED (`turn_excursion_deg`) without being called an error -- ring
     roads, switchbacks and loop ramps all reverse on purpose, and the one consumer that must
     reject a fold is the ramp search, not this check.
  4. The markers are ONE object, rebuilt not accumulated, and `Clear` removes them.
  5. `check_scene_geometry` returns findings as data, so a batch build can gate on them without
     parsing a report.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_geometry_check.py
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

import road_kit_authoring as rka                             # noqa: E402
from road_kit_authoring import ops_geometry_check as ogc     # noqa: E402
from road_kit_authoring import ops_segment as opseg          # noqa: E402
import kit_common as kc                                       # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _build(context, pts):
    res = opseg._build_segment_from_points(
        context, context.scene.collection, pts, lane_width=3.5, lanes=1, lanes_backward=1,
        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15, curb_thickness=0.25,
        join_visual_mesh=False, export_path="", gltf_export_path="")
    return bpy.data.collections.get(res["coll"].name)


def _codes(findings):
    return sorted({f[2] for f in findings})


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context

    # ------------------------------------------------------------------- 1. a clean road is clean
    straight = _build(context, [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (120.0, 0.0, 0.0),
                                 (180.0, 0.0, 0.0)])
    findings = ogc.check_scene_geometry(context)
    _assert(not findings, "a straight flat road must produce no findings, got %s"
            % _codes(findings))
    print("geometry check: a straight road produces no findings at all")

    # ------------------------------------------------------------ 2. one sharp vertex is a CORNER
    corner = _build(context, [(0.0, 300.0, 0.0), (60.0, 300.0, 0.0), (100.0, 334.0, 0.0),
                               (160.0, 384.0, 0.0)])
    findings = ogc.check_scene_geometry(context)
    corners = [f for f in findings if f[2] == "CORNER"]
    _assert(corners, "a 40 deg dogleg must be reported as CORNER, got %s" % _codes(findings))
    _assert(all(f[1] == corner.name for f in corners),
            "the CORNER should be attributed to the piece that has it, got %s"
            % {f[1] for f in corners})
    # ...and the marker lands ON the corner, not on the piece origin -- a report that names an id
    # without a place is a report nobody acts on.
    where = corners[0][4]
    d = math.dist(where[:2], (60.0, 300.0))
    _assert(d < 8.0, "the marker should sit at the offending vertex (60, 300); it is %.1f m away "
                      "at (%.1f, %.1f)" % (d, where[0], where[1]))
    print("geometry check: a 40 deg control point is reported as CORNER on '%s', marker %.2f m "
          "from the vertex" % (corner.name, d))

    # ------------------------------------------- 3. a fold is measured, but is NOT an error here
    hair = _build(context, [(0.0, 600.0, 0.0), (300.0, 600.0, 0.0), (360.0, 620.0, 0.0),
                             (390.0, 660.0, 0.0), (360.0, 700.0, 0.0), (300.0, 720.0, 0.0),
                             (0.0, 720.0, 0.0)])
    findings = ogc.check_scene_geometry(context)
    _assert(not [f for f in findings if f[1] == hair.name and f[2] == "REVERSAL"],
            "doubling back must not be reported as an error -- a ring road, a switchback and a "
            "loop ramp all reverse on purpose")
    import road_geometry as rg
    from road_kit_authoring import ops_joint_check
    lanes = [l for l in ops_joint_check.collect_scene_lanes(context)
             if l.get("piece_id") == hair.name]
    _assert(lanes and max(rg.turn_excursion(l["points"]) for l in lanes) > 150.0,
            "...but the fold must still be MEASURED, so a ramp search has a number to reject on")
    print("geometry check: a fold is measured (%.0f deg of net turn) and deliberately not an "
          "error" % max(rg.turn_excursion(l["points"]) for l in lanes))

    # --------------------------------------------------- 4. markers: one object, rebuilt, clearable
    ogc.place_markers(context, findings)
    obj = bpy.data.objects.get(ogc.WARN_OBJ)
    _assert(obj is not None, "no marker object was built")
    first = len(obj.data.vertices)
    _assert(first == 2 * len([f for f in findings if f[4] is not None]),
            "one stick (2 verts) per finding, got %d verts for %d findings"
            % (first, len(findings)))
    ogc.place_markers(context, findings)
    objs = [o for o in bpy.data.objects if o.name.startswith(ogc.WARN_OBJ)]
    _assert(len(objs) == 1, "re-running must REBUILD the marker object, not accumulate copies "
                             "(found %d)" % len(objs))
    _assert(len(objs[0].data.vertices) == first, "marker count changed on an identical re-run")
    _assert(ogc.clear_markers() and bpy.data.objects.get(ogc.WARN_OBJ) is None,
            "Clear must remove the marker object")
    print("geometry check: markers are ONE object, rebuilt not accumulated, and Clear removes it")

    # ------------------------------------------------------------------ 5. usable as a data gate
    by_piece = {}
    for lane_id, piece, code, _detail, _where in ogc.check_scene_geometry(context):
        by_piece.setdefault(piece, set()).add(code)
    _assert(straight.name not in by_piece, "the clean piece must not appear in the findings")
    _assert("CORNER" in by_piece.get(corner.name, ()), by_piece)
    # The hairpin's own sharp vertices are CORNERs; its FOLD is measured, not flagged (step 3).
    _assert("REVERSAL" not in by_piece.get(hair.name, ()), by_piece)
    print("geometry check: findings come back as data keyed by piece -- a batch build can gate "
          "on them with no report parsing")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
