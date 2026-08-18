#!/usr/bin/env python3
"""
smoketest_pinned_far_end.py -- headless verification for the 2026-08 fix (user-reported: "the end
port [the non-connecting end] is not moved, only move the connect spine to the arm tangent" -- the
old behavior, a rigid whole-spine rotation, swung a segment's FAR end (its far port, possibly
already correctly connected elsewhere on its own) by however far the segment is long times the
correction angle, every time the NEAR end's tangent was corrected to match a live arm joint).

Covers the two things that changed in `live_edit.move_dependent_marker`'s single-end branch:
  1. `_ensure_bend_room` -- a plain 2-point straight segment (the common case: `Segment_001` in
     `world_session.blend`, the real reported piece, is exactly this) has no interior point to
     carry a different tangent at one end without rotating the whole line -- one gets inserted.
  2. `_bend_near_end_to_angle` -- the near end lands EXACTLY on the joint's position AND EXACTLY
     matches its tangent, while the far end does not move AT ALL beyond wherever a plain
     position-only translate already carried it (verified separately: a translate-only carry, no
     angle change, must still move the far end -- see `smoketest_arm_angle_decoupled.py` -- this
     test isolates the TANGENT correction specifically).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_pinned_far_end.py
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
from road_kit_authoring import live_edit                   # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _angle_deg(p0, p1):
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.0


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # intersection --(Extend From Arm)--> a LONG segment (100m, so any unwanted rigid-rotation
    # swing at the far end would be large and easy to catch), matching Segment_001's own shape in
    # world_session.blend: a plain 2-point straight line (no interior points at all).
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 2, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_e = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "E")

    for o in bpy.data.objects:
        o.select_set(False)
    arm_e.select_set(True)
    context.view_layer.objects.active = arm_e
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="E", length=100.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    _assert(len(spine_io.points(seg_spine)) == 2,
            "sanity: a freshly-extended segment should be a plain 2-point straight line, got %d"
            % len(spine_io.points(seg_spine)))

    far_before = tuple(spine_io.points(seg_spine)[-1].co)[:3]
    lane_before = spine_io.points(seg_spine)[-1].radius
    arm_pos_before = (arm_e.location.x, arm_e.location.y)

    # Rotate arm E by a LARGE angle (25 deg -- bigger than the ~5 deg real-world mismatch measured
    # in world_session.blend, to make an unwanted EXTRA rotational swing impossible to miss: over
    # a 100m segment a 25 deg rigid rotation of the whole spine about the near end would move the
    # far end by roughly 100 * sin(25deg) =~ 42m ON TOP of the plain position carry below (the
    # arm's own (x,y) also moves by changing its angle at a fixed distance from the intersection
    # origin -- see intersection_kit.Arm -- so SOME far-end movement, the plain translate-carry,
    # is expected and correct; it's the EXTRA rotational swing this test isolates).
    origin = opint.get_or_create_origin_marker(inter_coll)
    ox, oy = origin.location.x, origin.location.y
    build_angle = arm_e.get("rka_arm_angle", 0.0)
    new_angle_deg = build_angle + 25.0
    dist = math.hypot(arm_e.location.x - ox, arm_e.location.y - oy)
    rad = math.radians(new_angle_deg)
    arm_e.location.x = ox + dist * math.cos(rad)
    arm_e.location.y = oy + dist * math.sin(rad)
    arm_e.rotation_euler.z = rad   # a real Rotate/Set Angle sets both -- see ensure_arm_angle_migrated
    opint.rebuild_intersection_in_place(context, inter_coll)
    arm_e = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "E")
    # rebuild_intersection_in_place re-snaps the arm onto its own effective tail length on the new
    # angle -- read back its FINAL position for the expected plain-translate-carry delta below.
    arm_carry_delta = (arm_e.location.x - arm_pos_before[0], arm_e.location.y - arm_pos_before[1])

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_e.name})

    seg_coll = opint.local_collection(seg_coll.name)
    seg_spine = bpy.data.objects.get(seg_coll.get("rka_curve_object"))
    pts = spine_io.points(seg_spine)
    _assert(len(pts) == 3,
            "a tangent correction on a 2-point line should have inserted exactly one bend point, "
            "got %d points" % len(pts))

    # --- near end: position AND tangent both exact.
    p0 = tuple(pts[0].co)[:3]
    dist_near = math.dist((p0[0], p0[1]), (arm_e.location.x, arm_e.location.y))
    _assert(dist_near < 1e-4,
            "the segment's near end should land exactly on the rotated arm, dist=%.6f" % dist_near)
    p1 = tuple(pts[1].co)[:3]
    tangent = _angle_deg(p0, p1)
    diff = abs((tangent - new_angle_deg + 180.0) % 360.0 - 180.0)
    _assert(diff < 0.01,
            "the near end's tangent should EXACTLY match the arm's new angle (%.2f deg), got "
            "%.4f deg (off by %.4f)" % (new_angle_deg, tangent, diff))
    print("pinned_far_end smoketest: near end landed exactly on the arm (dist=%.6f) with an exact "
          "tangent match (%.4f deg, off by %.6f deg)" % (dist_near, tangent, diff))

    # --- far end: moved by EXACTLY the plain translate-carry (the arm's own position shift), and
    # NO MORE -- this is the actual fix. The old behavior additionally applied a rigid rotation of
    # the whole spine around the near end, which would have swung this by a further ~42m.
    far_after = tuple(pts[-1].co)[:3]
    expected_far = (far_before[0] + arm_carry_delta[0], far_before[1] + arm_carry_delta[1])
    dist_far = math.dist(expected_far, far_after[:2])
    _assert(dist_far < 1e-4,
            "THE BUG: the segment's far end (already correctly placed, not itself linked to "
            "anything) must move by EXACTLY the plain translate-carry (%s) and no more when the "
            "near end's TANGENT is corrected -- expected %s, got %s (off by %.4fm; a leftover "
            "unwanted rotational swing would show up here as a much larger error, up to roughly "
            "100*sin(25deg) =~ 42m)" % (arm_carry_delta, expected_far, far_after[:2], dist_far))
    print("pinned_far_end smoketest: far end (100m away, unlinked) moved by EXACTLY the plain "
          "translate-carry (%.6fm off) -- NO extra rotational swing -- while the near end's "
          "tangent was corrected by 25 deg" % dist_far)

    # --- pavement radius (lane width) at the far end is untouched too -- only geometry changed,
    # not width, which is a separate (already-working) sync path.
    _assert(abs(pts[-1].radius - lane_before) < 1e-6,
            "far end's pavement radius should be untouched by a pure tangent correction")

    # --- the bend point's own radius should be a sane interpolation, not a stray 0/default value.
    _assert(pts[1].radius > 0.0, "the inserted bend point should carry a real interpolated radius")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
