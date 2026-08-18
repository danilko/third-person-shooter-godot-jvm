#!/usr/bin/env python3
"""
smoketest_viz_degenerate.py -- ONE bad piece must not blank the traffic overlay for the whole file,
and a curved road's arrows must point along the road, not along its chord.

THE BUG THIS PINS (found on `island_v3_roads.blend`, 2026-08-15). `traffic_viz` derived each
segment's direction from the two-endpoint CHORD (`p0 -> p1`). The island contains a vertical
connector ramp -- `SegmentCurve_062`, 22 points, one XY position, z 12 -> 4 -- whose endpoints
coincide in XY, so that chord has zero length and `vnorm` raised
`cannot normalize a zero-length vector`. `_gather` builds the entire overlay in one pass, so that
single piece produced ZERO gizmos for all 126 pieces: the user-visible symptom was "lost the
plugin's ability to show in/out of each port/connection point to debug which way traffic is going".

The chord was also simply the wrong quantity. Every island road is a Catmull-Rom fit resampled
every few metres; on a curving piece the chord can be tens of degrees away from the direction the
road actually runs at the end where the arrow is drawn. An arrow pointing somewhere the lane does
not go is worse than no arrow at all, because it gets read as the answer.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_viz_degenerate.py
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_segment as opseg        # noqa: E402
from road_kit_authoring import traffic_viz                 # noqa: E402
import kit_common as kc                                    # noqa: E402

LW = 5.0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    context = bpy.context
    context.scene.rka.show_traffic_indicators = True
    context.scene.rka.show_lane_indices = True
    scene_coll = context.scene.collection

    # ------------------------------------------------------------------ an ordinary road, plus a
    # QUARTER-CIRCLE one whose chord is nowhere near its end tangents.
    opseg._build_segment_from_points(
        context, scene_coll, [(0.0, 0.0, 0.0), (60.0, 0.0, 0.0)], LW, 1, 1,
        'NONE', 'NONE', 0.15, 0.25, False, "", "")
    R = 80.0
    arc = [(200.0 + R * math.sin(math.radians(a)), R * (1.0 - math.cos(math.radians(a))), 0.0)
           for a in range(0, 91, 10)]
    opseg._build_segment_from_points(
        context, scene_coll, arc, LW, 1, 1, 'NONE', 'NONE', 0.15, 0.25, False, "", "")

    base = traffic_viz._gather(context)
    _assert(base, "two ordinary roads produced no gizmos at all")
    n_base = len(base)

    # The arc's A end runs due +X (a=0 tangent). Its CHORD runs 45 degrees off that, so this
    # assertion is what separates a per-end tangent from the old whole-piece chord.
    a_end = [it for it in base
             if math.dist((it[0][0], it[0][1]), (200.0, 0.0)) < 6.0 and it[3].startswith("FWD")]
    _assert(a_end, "expected a FWD arrow at the curved road's A end")
    d = (a_end[0][1][0] - a_end[0][0][0], a_end[0][1][1] - a_end[0][0][1])
    ang = math.degrees(math.atan2(d[1], d[0])) % 360.0
    # The bound is one resample step (10 deg here), not zero: a polyline's direction AT an end is
    # its first span, which on a 10-deg-stepped arc sits ~5 deg off the ideal tangent. That is the
    # honest answer for the geometry that actually exists. The number being pinned is that it is
    # near the ROAD's direction (0 deg) and nowhere near the CHORD's (45 deg).
    off = min(ang, 360.0 - ang)
    _assert(off < 10.0,
            "the arrow at a curved road's A end must follow the road's own tangent there (~0 deg "
            "+/- one resample step), not the piece's chord (~45 deg) -- got %.1f deg" % ang)
    print("smoketest_viz_degenerate: on a 90-degree curve the end arrow follows the road (%.1f "
          "deg off, within one 10-deg resample step), not the chord (45 deg off)" % off)

    # ------------------------------------------------------------------ now add the killer: a
    # piece whose two ENDS coincide in XY while its interior does not -- a descending hairpin, the
    # shape `SegmentCurve_062` actually has (22 points, start and end at one XY, z 12 -> 4). The
    # builder rejects a path that is stacked at EVERY point, so this is also the only form the
    # defect can take in a real file: the CHORD is degenerate, the piece is not.
    opseg._build_segment_from_points(
        context, scene_coll,
        [(500.0, 500.0, 12.0), (512.0, 506.0, 10.0), (512.0, 494.0, 6.0), (500.0, 500.0, 4.0)],
        LW, 1, 1, 'NONE', 'NONE', 0.15, 0.25, False, "", "")

    after = traffic_viz._gather(context)
    _assert(len(after) >= n_base,
            "adding ONE degenerate piece cut the overlay from %d gizmos to %d -- a single bad "
            "piece must not blank the whole file's traffic indicators" % (n_base, len(after)))
    print("smoketest_viz_degenerate: a zero-XY-extent piece leaves the other roads' %d gizmos "
          "intact (it used to raise and blank all of them)" % len(after))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
