#!/usr/bin/env python3
"""
smoketest_median_marking.py -- headless verification for the 2026-08 fix: a solid "yellow"
centerline marking must NOT be painted through/under a real median separator
(`intersection_kit.build_segment_lane_markings`'s `median_half_start`/`median_half_end`,
`ops_segment._populate_lane_markings`). Also verifies the internal white lane-boundary markings
shift outward to track the median's own half-width (previously always at a fixed offset,
independent of whether a median was pushing the lanes outward).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_median_marking.py
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
from road_kit_authoring import ops_segment as opseg        # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# Marking objects are named after the MATERIAL KEY they carry (`mark_<piece>_line_y_<i>`), not
# after a colour word -- `_populate_lane_markings` builds the name from the same `line_y`/`line_w`
# matkey the curated `ROAD_MATKEY_ITEMS` picker offers, so the object name and the material can
# never disagree. This map keeps the test's own vocabulary readable ("the yellow centreline") while
# matching what is actually built; the tests used to hardcode `_yellow_`/`_white_` and went silently
# stale when the naming moved to matkeys.
_MARK_MATKEY = {"yellow": "line_y", "white": "line_w"}


def _mark_objs(coll, kind):
    prefix = "mark_%s_%s_" % (coll.name, _MARK_MATKEY.get(kind, kind))
    return [o for o in coll.objects if o.name.startswith(prefix)]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context
    bpy.ops.rka.link_curb_kit_library()

    # --- no median: yellow centerline present, at offset 0.
    result = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0)], lane_width=5.0, lanes=2,
        lanes_backward=2, curb_l_style='BOX', curb_r_style='BOX', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="")
    coll = result["coll"]
    yellow = _mark_objs(coll, "yellow")
    # PRESENT and CENTRED, not "exactly one ribbon": how many ribbons a centreline is painted with
    # is the cross-section's business (an undivided two-way road takes a DOUBLE_Y -- two of them,
    # straddling the centre). What must hold is that the centreline exists and sits ON the spine.
    _assert(yellow, "a no-median segment should have a yellow centerline, got none")
    ys = [(o.matrix_world @ v.co).y for o in yellow for v in o.data.vertices]
    _assert(abs(sum(ys) / len(ys)) < 1e-3,
            "the no-median yellow centreline should be centred on the spine (Y=0), got %.3f"
            % (sum(ys) / len(ys)))
    print("median_marking smoketest: a no-median segment still gets its yellow centerline at "
          "the spine centerline (Y=0)")

    # --- with a median: NO yellow centerline (it's redundant/hidden inside the real median wall).
    result2 = opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 100.0, 0.0), (40.0, 100.0, 0.0)], lane_width=5.0, lanes=2,
        lanes_backward=2, curb_l_style='BOX', curb_r_style='BOX', curb_height=0.15,
        curb_thickness=0.25, join_visual_mesh=False, export_path="", gltf_export_path="",
        median_width=4.0, median_style='PROFILE',
        median_asset_collection='Kit_Median_YellowSeparator')
    coll2 = result2["coll"]
    yellow2 = _mark_objs(coll2, "yellow")
    _assert(len(yellow2) == 0,
            "a segment WITH a real median must have NO yellow centerline (it would be painted "
            "through/under the median object) -- got %d" % len(yellow2))
    # "There IS a median", counted across both carrier kinds: a sibling-object piece has a
    # `curb_<piece>_median` object, a modifier-stack piece a `Median` LAYER on its one carrier.
    median_n = len([o for o in coll2.objects
                    if "_median" in o.name and not o.name.endswith("-colonly")])
    median_n += sum(len([m for m in o.modifiers if m.type == 'NODES' and m.name == "Median"])
                    for o in coll2.objects)
    _assert(median_n == 1, "sanity: median_width=4 + PROFILE should build exactly 1 median, got %d"
            % median_n)
    print("median_marking smoketest: a segment with a real median (PROFILE style) has NO redundant "
          "yellow centerline, while the real median object still exists")

    # --- the white internal-lane-boundary lines must shift outward by the median half-width, not
    # stay at their no-median offset (which would land them INSIDE the median instead of between
    # the correct pair of lanes).
    white2 = _mark_objs(coll2, "white")
    _assert(len(white2) == 2, "2 forward + 2 backward lanes should produce exactly 2 internal "
            "white boundary lines (1 per direction), got %d" % len(white2))
    median_half = 4.0 / 2.0
    expected_offsets = sorted([median_half + 1 * 5.0, -(median_half + 1 * 5.0)])

    def _centerline_y(o):
        v0, v1 = o.data.vertices[0], o.data.vertices[1]
        return round((((o.matrix_world @ v0.co) + (o.matrix_world @ v1.co)) / 2.0).y, 3)

    got_offsets = sorted(round(v - 100.0, 3) for v in (_centerline_y(o) for o in white2))
    for got, want in zip(got_offsets, expected_offsets):
        _assert(abs(got - want) < 1e-3,
                "white boundary line should sit at median_half(%.1f) + 1*lane_width offset "
                "(%.3f), got %.3f -- if this equals the NO-median offset instead, the median "
                "shift wasn't applied" % (median_half, want, got))
    print("median_marking smoketest: internal white lane-boundary lines shifted outward by the "
          "median half-width (%.1fm), landing between the correct lane pair" % median_half)

    # --- the no-median segment's white lines must be UNAFFECTED (still at the plain offset).
    white1 = _mark_objs(coll, "white")
    _assert(len(white1) == 2, "sanity: no-median segment should also have 2 white boundary lines")
    got1 = sorted(_centerline_y(o) for o in white1)
    want1 = sorted([1 * 5.0, -1 * 5.0])
    for got, want in zip(got1, want1):
        _assert(abs(got - want) < 1e-3,
                "no-median white boundary line should stay at the plain offset %.3f, got %.3f"
                % (want, got))
    print("median_marking smoketest: no-median segment's white boundary lines are unchanged")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
