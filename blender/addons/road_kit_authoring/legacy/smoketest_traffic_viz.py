#!/usr/bin/env python3
"""
smoketest_traffic_viz.py -- headless verification for traffic_viz.py's IN/OUT gizmo direction
fix: an intersection arm with a REAL segment attached must draw its arrow along that segment's
own tangent, not the bearing re-derived from the intersection's origin marker through the arm
(`rka_arm_angle`) -- the latter is a GLOBAL quantity that can shift on an unrelated edit (another
arm added/removed, kerb radius changed, the whole piece moved) even though the attached road
itself didn't move, which made the gizmo visibly swing to a different, hard-to-read angle.

Only exercises `traffic_viz._gather()` (pure Python, returns plain tuples) -- `_draw_3d`/`_draw_2d`
need a live OpenGL context and are not covered here.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_traffic_viz.py
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
from road_kit_authoring import traffic_viz                 # noqa: E402
import kit_common as kc                                     # noqa: E402


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
    scene_coll = context.scene.collection

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]
    arm_n = next(o for o in coll.objects if o.get("rka_arm_name") == "N")
    arm_n_pos = (arm_n.location.x, arm_n.location.y)
    original_angle = arm_n.get("rka_arm_angle", 0.0)
    expected_dir = (math.cos(math.radians(original_angle)), math.sin(math.radians(original_angle)))

    # --- Extend a REAL segment from arm N -- it starts exactly at the arm's own angle, so
    # initially the arm's origin-bearing and the segment's own tangent agree.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.extend_from_arm(length=30.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))

    items = traffic_viz._gather(context)
    arm_items = [it for it in items if math.dist((it[0][0], it[0][1]), arm_n_pos) < 6.0]
    _assert(len(arm_items) > 0, "expected at least one gizmo arrow near arm N")
    out_item = next(it for it in arm_items if it[3].startswith("OUT"))
    out_dir = (out_item[1][0] - out_item[0][0], out_item[1][1] - out_item[0][1])
    out_dir_n = (out_dir[0] / math.hypot(*out_dir), out_dir[1] / math.hypot(*out_dir))
    _assert(math.dist(out_dir_n, expected_dir) < 1e-2,
            "OUT arrow at arm N should point along its %.1f deg angle (matching both the arm's "
            "own angle AND the attached segment's tangent initially), got %s expected %s"
            % (original_angle, out_dir_n, expected_dir))
    print("traffic_viz smoketest: OUT arrow at a freshly-extended arm points along the attached "
          "segment (%.1f deg), got %s" % (original_angle, out_dir_n))

    # --- Now desync: perturb ONLY the arm's stored bearing (rka_arm_angle), simulating the
    # origin-to-arm bearing drifting from an unrelated edit elsewhere on the intersection, WITHOUT
    # touching the actually-attached segment's spine at all. The old behavior (arm_dir(rka_arm_angle))
    # would swing the gizmo to point along the new (wrong) angle; the fix must keep following the
    # real, unmoved segment instead.
    perturbed_angle = (original_angle + 55.0) % 360.0   # a big, obviously-wrong swing if not ignored
    arm_n["rka_arm_angle"] = perturbed_angle
    items2 = traffic_viz._gather(context)
    arm_items2 = [it for it in items2 if math.dist((it[0][0], it[0][1]), arm_n_pos) < 6.0]
    out_item2 = next(it for it in arm_items2 if it[3].startswith("OUT"))
    out_dir2 = (out_item2[1][0] - out_item2[0][0], out_item2[1][1] - out_item2[0][1])
    out_dir2_n = (out_dir2[0] / math.hypot(*out_dir2), out_dir2[1] / math.hypot(*out_dir2))
    _assert(math.dist(out_dir2_n, expected_dir) < 1e-2,
            "OUT arrow must keep following the attached (unmoved) segment's actual tangent even "
            "after the arm's stored origin-bearing (rka_arm_angle) drifted, got %s expected %s"
            % (out_dir2_n, expected_dir))
    print("traffic_viz smoketest: gizmo direction stays locked to the attached segment's real "
          "tangent even after rka_arm_angle drifts out of sync (got %s, not the perturbed %.1f deg)"
          % (out_dir2_n, perturbed_angle))

    # --- A dangling arm (nothing attached yet) must still fall back to arm_dir(rka_arm_angle) --
    # there's no real road to defer to.
    arm_e = next(o for o in coll.objects if o.get("rka_arm_name") == "E")
    items3 = traffic_viz._gather(context)
    arm_e_pos = (arm_e.location.x, arm_e.location.y)
    arm_e_items = [it for it in items3 if math.dist((it[0][0], it[0][1]), arm_e_pos) < 6.0]
    _assert(len(arm_e_items) > 0, "expected gizmo arrows near dangling arm E")
    out_e = next(it for it in arm_e_items if it[3].startswith("OUT"))
    out_e_dir = (out_e[1][0] - out_e[0][0], out_e[1][1] - out_e[0][1])
    expected_angle = arm_e.get("rka_arm_angle", 0.0)
    got_angle = math.degrees(math.atan2(out_e_dir[1], out_e_dir[0])) % 360.0
    _assert(abs((got_angle - expected_angle + 180) % 360 - 180) < 1.0,
            "a dangling arm (nothing attached) should fall back to arm_dir(rka_arm_angle), "
            "expected ~%.1f deg got %.1f deg" % (expected_angle, got_angle))
    print("traffic_viz smoketest: a dangling arm with no attached segment falls back to its own "
          "stored angle (%.1f deg)" % expected_angle)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
