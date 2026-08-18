#!/usr/bin/env python3
"""
smoketest_aim_arm.py -- headless verification for `RKA_OT_aim_arm_at`/`RKA_OT_nudge_arm_angle`
(2026-08, user-reported with a screenshot: a road stub runs off diagonally but the arm/pad edge
cuts straight across it -- "cannot do horizontal move arm" now that a plain Grab/translate no
longer changes an arm's angle at all, see `ensure_arm_angle_migrated`, and setting an exact angle
"seem not accurate and kind of hard to change"). `Match Arm To Selected` snaps an arm EXACTLY onto
a target's position AND rotates it to EXACTLY match the target's tangent, both at once (2026-08
follow-up: this used to be two separate modes, "Aim At"/"Snap To", each only exact on ONE of
position/tangent -- collapsed into one operator once `intersection_kit.Arm.tail_pos` decoupled a
cap's position from its angle -- see that class's docstring for the full history). `Nudge Arm
Angle` gives quick +/- degree stepping for fine-tuning, both reusing the same rebuild +
link-propagation path as `RKA_OT_set_arm_angle`.

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_aim_arm.py
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

    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_s = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "S")
    origin = opint.get_or_create_origin_marker(inter_coll)
    other_arms_before = {o.get("rka_arm_name"): tuple(o.location)
                          for o in inter_coll.objects if "rka_arm_name" in o.keys()
                          and o.get("rka_arm_name") != "S"}
    origin_before = tuple(origin.location)

    # A "road stub" sitting off diagonally -- matches the screenshot's scenario -- represented by
    # a plain target object (any object with .location works, per the operator's docstring), NOT
    # on arm S's own angle-ray (deliberately: this is exactly the case a ray-based match could
    # only ever get half right).
    target = bpy.data.objects.new("RoadStub", None)
    target.location = (origin.location.x - 30.0, origin.location.y - 50.0, origin.location.z)
    scene_coll.objects.link(target)
    expected_angle = math.degrees(math.atan2(
        target.location.y - origin.location.y, target.location.x - origin.location.x)) % 360.0

    # --- poll: needs exactly the arm + one other object selected.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s.select_set(True)
    context.view_layer.objects.active = arm_s
    _assert(not bpy.ops.rka.aim_arm_at.poll(), "poll should fail with no target selected")
    target.select_set(True)
    context.view_layer.objects.active = arm_s   # active = the arm being re-aimed
    _assert(bpy.ops.rka.aim_arm_at.poll(), "poll should succeed with arm + one target selected")

    ret = bpy.ops.rka.aim_arm_at('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "aim_arm_at did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_s = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "S")

    # --- BOTH position and tangent exact, simultaneously -- the actual point of this fix (a bare
    # Empty target has no tangent of its own, so `_resolve_target_angle_deg` falls back to the raw
    # bearing -- still must be an EXACT match, not an approximation).
    gap = math.dist((arm_s.location.x, arm_s.location.y), (target.location.x, target.location.y))
    _assert(gap < 1e-4, "arm S should land EXACTLY on the target's position, gap=%.6f" % gap)
    got_angle = arm_s.get("rka_arm_angle", -999.0)
    diff = abs((got_angle - expected_angle + 180.0) % 360.0 - 180.0)
    _assert(diff < 0.05, "arm S should face exactly toward the target (%.2f deg), got %.2f"
            % (expected_angle, got_angle))
    _assert(arm_s.get("rka_arm_tail_pos_locked") is True,
            "a matched arm should be stamped tail_pos_locked so rebuilds don't re-snap it")
    print("aim_arm smoketest: arm S landed EXACTLY on the target (gap=%.6fm) AND exactly matched "
          "its bearing (%.2f deg) -- both at once, not a tradeoff" % (gap, got_angle))

    # --- every OTHER arm and the intersection's own origin/center must be completely untouched --
    # the user's explicit requirement ("other arm is correct position... center of intersection is
    # not moved").
    for name, loc_before in other_arms_before.items():
        o = next(x for x in inter_coll.objects if x.get("rka_arm_name") == name)
        moved = math.dist(loc_before[:2], (o.location.x, o.location.y))
        _assert(moved < 1e-6,
                "every OTHER arm ('%s') must stay exactly where it was -- moved %.6fm"
                % (name, moved))
    origin_after = opint.get_or_create_origin_marker(inter_coll)
    moved_origin = math.dist(origin_before[:2], (origin_after.location.x, origin_after.location.y))
    _assert(moved_origin < 1e-6,
            "the intersection's own origin/center must not move -- moved %.6fm" % moved_origin)
    print("aim_arm smoketest: every other arm and the intersection's own center stayed completely "
          "untouched")

    # --- the lock survives a SEPARATE rebuild (e.g. triggered by widening a different arm) --
    # without this, the very next rebuild would silently re-snap arm S back onto its clean
    # angle-ray, undoing the match (the exact regression this stamp exists to prevent).
    opint.rebuild_intersection_in_place(context, inter_coll)
    inter_coll = opint.local_collection(inter_coll.name)
    arm_s = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "S")
    gap_after_rebuild = math.dist((arm_s.location.x, arm_s.location.y),
                                   (target.location.x, target.location.y))
    _assert(gap_after_rebuild < 1e-4,
            "a locked arm's match must survive a later rebuild -- gap grew to %.6f"
            % gap_after_rebuild)
    print("aim_arm smoketest: the match survived a separate rebuild (gap=%.6fm) -- not silently "
          "re-snapped back onto the clean ray" % gap_after_rebuild)

    # --- nudge: quick +/- degree stepping. Also confirms Nudge/Set-Angle CLEAR the lock (an
    # explicit numeric angle is the classic ray-based workflow -- see _apply_arm_angle).
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s.select_set(True)
    context.view_layer.objects.active = arm_s
    _assert(bpy.ops.rka.nudge_arm_angle.poll(), "poll should succeed with an arm active")
    ret = bpy.ops.rka.nudge_arm_angle('EXEC_DEFAULT', delta_deg=5.0)
    _assert(ret == {'FINISHED'}, "nudge_arm_angle did not finish: %s" % (ret,))
    ret = bpy.ops.rka.nudge_arm_angle('EXEC_DEFAULT', delta_deg=5.0)
    _assert(ret == {'FINISHED'}, "second nudge_arm_angle did not finish: %s" % (ret,))
    ret = bpy.ops.rka.nudge_arm_angle('EXEC_DEFAULT', delta_deg=-1.0)
    _assert(ret == {'FINISHED'}, "third nudge_arm_angle did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_s = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "S")
    expected_nudged = (got_angle + 5.0 + 5.0 - 1.0) % 360.0
    got_nudged = arm_s.get("rka_arm_angle", -999.0)
    diff2 = abs((got_nudged - expected_nudged + 180.0) % 360.0 - 180.0)
    _assert(diff2 < 0.05, "three nudges (+5,+5,-1) should land at %.2f deg, got %.2f"
            % (expected_nudged, got_nudged))
    _assert(not arm_s.get("rka_arm_tail_pos_locked"),
            "nudging the angle should clear the tail_pos_locked flag -- back to ray-based")
    print("aim_arm smoketest: three angle nudges (+5,+5,-1) landed at exactly %.2f deg and "
          "cleared the position lock" % got_nudged)

    # --- aiming also cascades to a linked segment, same as RKA_OT_set_arm_angle.
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s.select_set(True)
    context.view_layer.objects.active = arm_s
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="S", length=40.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)

    target2 = bpy.data.objects.new("RoadStub2", None)
    target2.location = (origin.location.x + 60.0, origin.location.y + 5.0, origin.location.z)
    scene_coll.objects.link(target2)
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s.select_set(True)
    target2.select_set(True)
    context.view_layer.objects.active = arm_s
    ret = bpy.ops.rka.aim_arm_at('EXEC_DEFAULT')
    _assert(ret == {'FINISHED'}, "aim_arm_at (linked case) did not finish: %s" % (ret,))
    inter_coll = opint.local_collection(inter_coll.name)
    arm_s = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "S")
    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    p0 = tuple(spine_io.points(spine)[0].co)[:3]
    p1 = tuple(spine_io.points(spine)[1].co)[:3]
    tangent = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.0
    diff3 = abs((tangent - arm_s.get("rka_arm_angle") + 180.0) % 360.0 - 180.0)
    _assert(diff3 < 0.1, "the linked segment's tangent should follow the aim, arm=%.2f spine=%.2f"
            % (arm_s.get("rka_arm_angle"), tangent))
    print("aim_arm smoketest: aim_arm_at also re-aligned the linked segment's tangent (%.2f deg)"
          % tangent)

    # --- extend_from_arm on a LOCKED (off-ray-matched) arm must start the new segment at the
    # arm's REAL current position, not the old ray-projected point (2026-08 regression fix,
    # user-reported: "extend from arm/intersection... no longer create from exact port/arm
    # location with align tangent" -- this used to re-derive the start point from `origin +
    # tail_length * direction(angle)`, which stopped matching the arm's actual `.location` the
    # moment an arm could be off-ray). arm_s is still locked from the aim above.
    before_colls = set(c.name for c in bpy.data.collections)
    for o in bpy.data.objects:
        o.select_set(False)
    arm_s.select_set(True)
    context.view_layer.objects.active = arm_s
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="S", length=20.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm (locked arm) did not finish: %s" % (ret,))
    new_coll = next(c for c in bpy.data.collections
                     if c.name not in before_colls and c.get("rka_curve_object"))
    new_spine = new_coll.objects[new_coll["rka_curve_object"]]
    p0new = tuple(spine_io.points(new_spine)[0].co)[:3]
    gap_extend = math.dist(p0new, (arm_s.location.x, arm_s.location.y, arm_s.location.z))
    _assert(gap_extend < 1e-4,
            "a segment extended from a LOCKED arm should start EXACTLY at the arm's real "
            "position, not a stale ray-projected point -- gap=%.6f" % gap_extend)
    print("aim_arm smoketest: extend_from_arm on a locked (off-ray-matched) arm started the new "
          "segment exactly at the arm's real position (gap=%.6fm)" % gap_extend)

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
