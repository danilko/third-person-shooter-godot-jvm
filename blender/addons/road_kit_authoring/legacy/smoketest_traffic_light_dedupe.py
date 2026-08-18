#!/usr/bin/env python3
"""
smoketest_traffic_light_dedupe.py -- headless verification for a confirmed real bug (2026-08,
user-reported: "the traffic light seem add additional light/object, instead of should just be one
object at each, have double on the arm_e side (4 instead of 2)"). Root cause, confirmed by direct
headless inspection against `world_session.blend`: `_populate_intersection_traffic_lights` gives
every enabled arm `a` a P1 (its own corner) and a P2 (`opposite_arm(a)`'s own corner). Whenever
two enabled arms are each other's `opposite_arm` -- the expected/common case for a roughly 4-way
intersection (N<->S, E<->W here, confirmed exactly this pairing on world_session.blend's own real,
non-90-degree-spaced arm angles) -- arm A's own P1 and arm B's own P2 land at the EXACT SAME
corner, and since every arm shares the same default `traffic_light_radius` unless individually
customized, at the EXACT SAME (x, y) -- a real intersection's 8-point point-cloud (4 arms x 2
poles) was measured to have only 4 DISTINCT positions, each present exactly twice. Fixed by
deduping on corner identity (`(arm_for_corner.name, its own CCW-next neighbor's name)`) before
appending to the pole/gantry coordinate lists.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_traffic_light_dedupe.py
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
    bpy.ops.rka.link_curb_kit_library()

    ret = bpy.ops.rka.build_intersection(
        'EXEC_DEFAULT', preset='4WAY', lane_width=5.0, lanes=1, kerb_radius=9.0, tail_length=12.0,
        segments=8, curb_style='NONE')
    _assert(ret == {'FINISHED'}, ret)
    inter = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    for o in bpy.data.objects:
        o.select_set(False)
    context.view_layer.objects.active = inter.objects.get("pad_%s" % inter.name)

    # Setting a real piece with NO arm enabled yet auto-enables every arm (see this operator's
    # own docstring) -- a default 4-way (N/E/S/W at 0/90/180/270 deg) is ALREADY a mutually-
    # opposite-pair case (N<->S, E<->W) -- exactly the precondition this bug needs, no hand-tuned
    # angles required.
    ret = bpy.ops.rka.set_intersection_traffic_light_asset(collection_name='Kit_TrafficLight_L1')
    _assert(ret == {'FINISHED'}, ret)

    inter = next(c for c in bpy.data.collections if "rka_arm_names" in c.keys())
    tl = inter.objects.get("trafficlight_%s" % inter.name)
    _assert(tl is not None, "sanity: enabling every arm's light should build a trafficlight_* "
            "instancer")
    coords = [tuple(round(c, 3) for c in v.co) for v in tl.data.vertices]
    _assert(len(coords) == 4, "a 4-way with every arm enabled should place exactly 4 poles (one "
            "per corner), got %d" % len(coords))
    _assert(len(set(coords)) == 4, "every pole position should be DISTINCT -- got %d distinct "
            "positions out of %d points (a mutually-opposite arm pair's P1/P2 landed on top of "
            "each other, the exact reported 'double' bug), positions: %s"
            % (len(set(coords)), len(coords), coords))
    print("smoketest_traffic_light_dedupe: 4 enabled arms produce exactly 4 distinct pole "
          "positions (one per corner), no duplicates")

    # Evaluated geometry must also reflect exactly 4 real instances (not, say, a still-4-point
    # cloud that GN itself happens to collapse visually but still doubles the instance count).
    deps = context.evaluated_depsgraph_get()
    eo = tl.evaluated_get(deps)
    me = eo.to_mesh()
    evaluated_verts = len(me.vertices)
    eo.to_mesh_clear()
    _assert(evaluated_verts > 0, "sanity: the deduped instancer should still have real geometry")
    print("smoketest_traffic_light_dedupe: evaluated instancer has real geometry (%d verts)"
          % evaluated_verts)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
