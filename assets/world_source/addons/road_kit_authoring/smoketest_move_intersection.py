#!/usr/bin/env python3
"""
smoketest_move_intersection.py -- headless verification that moving/rotating a whole
intersection's collection as a rigid group (the "select all objects, Grab/Rotate" workflow)
reproduces the SAME relative arm layout at the new location/orientation, instead of re-deriving
wrong angles against a frozen `rka_origin` coordinate that didn't move with the selection.

RUN: blender --background --python addons/road_kit_authoring/smoketest_move_intersection.py
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

import road_kit_authoring as rka                      # noqa: E402
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import custom_props            # noqa: E402
import kit_common as kc                                 # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _sorted_angles(coll):
    arms = custom_props.read_arms(coll)
    return sorted(a[1] % 360.0 for a in arms)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    coll = result["coll"]

    marker = opint.get_or_create_origin_marker(coll)
    _assert(marker is not None, "origin marker should exist after build_intersection_geometry")
    _assert(marker.get(opint.ORIGIN_MARKER_KEY) is True, "marker should be tagged rka_origin_marker")
    _assert(abs(marker.location.x) < 1e-6 and abs(marker.location.y) < 1e-6,
            "origin marker should sit at the build cursor (0,0)")
    print("move-intersection smoketest: origin marker created at the build position")

    angles_before = _sorted_angles(coll)

    # --- 1. TRANSLATE the whole collection (every object, including the origin marker) by a
    # fixed delta -- simulates "select all objects in the collection, G, move".
    dx, dy = 37.0, -22.0
    for o in list(coll.objects):
        o.location.x += dx
        o.location.y += dy
    opint.rebuild_intersection_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    marker = opint.get_or_create_origin_marker(coll)
    _assert(abs(marker.location.x - dx) < 1e-3 and abs(marker.location.y - dy) < 1e-3,
            "origin marker should have moved by the same delta")
    stored_origin = custom_props.read_origin(coll)
    _assert(stored_origin is not None
            and abs(stored_origin[0] - dx) < 1e-3 and abs(stored_origin[1] - dy) < 1e-3,
            "rka_origin custom prop should be re-persisted from the live marker on every "
            "rebuild (fix for the 'self-heal resurrects the piece at its stale PRE-MOVE "
            "position if the marker is ever lost' bug), got %s expected (%.1f, %.1f, ...)"
            % (stored_origin, dx, dy))
    print("move-intersection smoketest: rka_origin custom prop stays in sync with the live "
          "marker after rebuild (%s)" % (stored_origin,))
    angles_after_move = _sorted_angles(coll)
    _assert(all(abs(a - b) < 1e-3 for a, b in zip(angles_before, angles_after_move)),
            "arm angles should be UNCHANGED after a pure translation, got before=%s after=%s"
            % (angles_before, angles_after_move))
    print("move-intersection smoketest: pure translation preserves arm angles exactly "
          "(before=%s after=%s)" % (angles_before, angles_after_move))

    # --- 2. ROTATE the whole collection rigidly around the (already-moved) origin marker by 30
    # degrees -- simulates "select all objects, Rotate" with the pivot at the piece's own center.
    ox, oy = marker.location.x, marker.location.y
    rot_deg = 30.0
    rad = math.radians(rot_deg)
    ca, sa = math.cos(rad), math.sin(rad)
    for o in list(coll.objects):
        lx, ly = o.location.x - ox, o.location.y - oy
        o.location.x = ox + lx * ca - ly * sa
        o.location.y = oy + lx * sa + ly * ca
    opint.rebuild_intersection_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    angles_after_rotate = _sorted_angles(coll)
    expected = sorted((a + rot_deg) % 360.0 for a in angles_after_move)
    _assert(all(abs(a - b) < 1e-2 for a, b in zip(angles_after_rotate, expected)),
            "arm angles should shift by exactly the rotation amount, got %s expected %s"
            % (angles_after_rotate, expected))
    print("move-intersection smoketest: rigid rotation shifts every arm angle by exactly the "
          "rotation amount (%.1f deg), got=%s expected=%s" % (rot_deg, angles_after_rotate, expected))

    # --- 3. Move ONLY the origin marker (no arm empties touched at all) -- the single-handle
    # "drag this arrow to relocate the whole intersection" workflow the marker exists for. This
    # is the regression that shipped: re-deriving each arm's bearing against a moved-but-
    # unaccompanied origin used to collapse every arm onto a tiny bogus angular cluster while
    # forcibly re-snapping it back onto the tail_length radius (see
    # rebuild_intersection_in_place's docstring/carry-forward comment) -- the "blows up" bug.
    arm_positions_before = {o["rka_arm_name"]: (o.location.x, o.location.y, o.location.z)
                             for o in coll.objects if "rka_arm_name" in o.keys()}
    mdx, mdy, mdz = -15.0, 60.0, 2.0
    marker = opint.get_or_create_origin_marker(coll)
    marker.location.x += mdx
    marker.location.y += mdy
    marker.location.z += mdz
    opint.rebuild_intersection_in_place(context, coll)
    coll = bpy.data.collections.get(coll.name)
    angles_after_marker_only_move = _sorted_angles(coll)
    _assert(all(abs(a - b) < 1e-2 for a, b in zip(angles_after_rotate, angles_after_marker_only_move)),
            "arm angles must be UNCHANGED after moving ONLY the origin marker -- every untouched "
            "arm should be carried along by the marker's own delta, not re-derived against a "
            "mismatched center, got before=%s after=%s"
            % (angles_after_rotate, angles_after_marker_only_move))
    for o in coll.objects:
        name = o.get("rka_arm_name")
        if name is None:
            continue
        want = (arm_positions_before[name][0] + mdx, arm_positions_before[name][1] + mdy,
                arm_positions_before[name][2] + mdz)
        got = (o.location.x, o.location.y, o.location.z)
        _assert(math.dist(want, got) < 1e-2,
                "arm '%s' should have been carried by the origin marker's exact delta, got %s "
                "expected %s" % (name, got, want))
    print("move-intersection smoketest: moving ONLY the origin marker carries every untouched "
          "arm by the same delta, preserving the intersection's shape intact (angles=%s)"
          % (angles_after_marker_only_move,))

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
