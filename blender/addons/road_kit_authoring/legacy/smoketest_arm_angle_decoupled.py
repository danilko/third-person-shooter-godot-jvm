#!/usr/bin/env python3
"""
smoketest_arm_angle_decoupled.py -- headless verification for the 2026-08 fix (user-reported:
"even if manually modify pad/segment, slight change on interaction for the entire segment to
change, even though the [far] end segment... is original in correct location"). Root cause: an
arm's angle used to be recomputed FRESH from its marker's POSITION (`atan2` relative to the
intersection origin) on EVERY rebuild -- a plain Grab/translate (Blender's G key) can't be dragged
perfectly radially by hand, so even a drag meant only to nudge an arm's distance always changed
its angle at least slightly too, which then rigidly rotated a WHOLE linked segment -- including
its already-correctly-placed FAR end -- by that same small, unintended amount.

Fixed: angle now comes directly from the arm Empty's own `rotation_euler.z` (position only ever
supplies DISTANCE, via plain Euclidean `hypot`, which is not oversensitive) -- a pure translate
can no longer move the angle at all, only an explicit Rotate or `RKA_OT_set_arm_angle` can. Also
covers the one-time migration (`ops_intersection.ensure_arm_angle_migrated`) for content authored
before this fix, whose `rotation_euler.z` was only ever set at creation and can be stale relative
to wherever the arm was actually dragged to since (world_session.blend's exact failure mode).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_arm_angle_decoupled.py
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


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()

    scene_coll = bpy.context.scene.collection
    context = bpy.context

    # ============================================================ A: pure translate must NOT
    # change an arm's angle, even a slightly-off-radial drag.
    result = opint.build_intersection_geometry(
        context, scene_coll, (0.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter_coll = result["coll"]
    arm_n = next(o for o in inter_coll.objects if o.get("rka_arm_name") == "N")
    _assert(arm_n.get("rka_arm_angle_migrated") is True,
            "a freshly-built arm should be stamped already-migrated")
    orig_angle = arm_n.get("rka_arm_angle", 0.0)

    for o in bpy.data.objects:
        o.select_set(False)
    arm_n.select_set(True)
    context.view_layer.objects.active = arm_n
    ret = bpy.ops.rka.extend_from_arm('EXEC_DEFAULT', arm_name="N", length=100.0)
    _assert(ret == {'FINISHED'}, "extend_from_arm did not finish: %s" % (ret,))
    seg_coll = next(c for c in bpy.data.collections
                     if c.get("rka_curve_object") and "rka_lanes_a" not in c.keys()
                     and c is not inter_coll)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    far_before = tuple(spine_io.points(spine)[-1].co)[:3]

    # A "G-key-only" imprecise drag: nudge arm N's position slightly OFF the exact radial line
    # (never touching rotation_euler at all -- exactly what a real Grab in the viewport does).
    arm_pos_before = (arm_n.location.x, arm_n.location.y)
    arm_n.location.x += 0.4
    arm_n.location.y -= 0.15
    opint.rebuild_intersection_in_place(context, inter_coll)
    arm_n = next(o for o in opint.local_collection(inter_coll.name).objects
                 if o.get("rka_arm_name") == "N")
    _assert(abs(arm_n.get("rka_arm_angle", -999.0) - orig_angle) < 1e-4,
            "a pure translate (no explicit rotate) must NOT change the arm's angle at all -- "
            "was %.6f, now %.6f" % (orig_angle, arm_n.get("rka_arm_angle")))
    print("arm_angle_decoupled smoketest: an imprecise position-only nudge left the arm's angle "
          "completely unchanged (%.6f deg)" % arm_n.get("rka_arm_angle"))

    # `rebuild_intersection_in_place`'s own re-snap step pulls the marker back onto the clean
    # angle-0 ray (Y=0) at the drag's implied DISTANCE -- an off-radial nudge only ever changes
    # distance, exactly the intended effect -- so the arm's OWN final position isn't the raw
    # pre-rebuild nudge; read it back for the "near end's actual delta" the segment should carry.
    near_delta = (arm_n.location.x - arm_pos_before[0], arm_n.location.y - arm_pos_before[1])

    with live_edit.rebuilding():
        live_edit._propagate_links({arm_n.name})
    seg_coll = opint.local_collection(seg_coll.name)
    spine = seg_coll.objects[seg_coll["rka_curve_object"]]
    p_start_after = tuple(spine_io.points(spine)[0].co)[:3]
    far_after = tuple(spine_io.points(spine)[-1].co)[:3]
    dist_start = math.dist(p_start_after[:2], (arm_n.location.x, arm_n.location.y))
    _assert(dist_start < 1e-4,
            "the segment's near end should still track the arm's new (nudged) position exactly")
    # A translate-only nudge legitimately carries the WHOLE piece rigidly by that same delta (the
    # documented, intentional "carry the whole shape" behavior -- unchanged by this fix) -- the
    # actual bug this fix closes is any EXTRA rotational swing on top of that plain translate. So
    # the far end should move by EXACTLY the near end's own (re-snapped) delta, no more, no less.
    expected_far = (far_before[0] + near_delta[0], far_before[1] + near_delta[1])
    dist_far = math.dist(expected_far, far_after[:2])
    _assert(dist_far < 1e-3,
            "THE BUG: the segment's FAR end (100m away, already correctly placed) should move "
            "by EXACTLY the near end's own translate delta (%s) -- pure carry, no extra swing -- "
            "expected %s, got %s (off by %.4fm; a leftover unwanted rotation would show up here "
            "as a much larger error, growing with segment length)"
            % (near_delta, expected_far, far_after[:2], dist_far))
    print("arm_angle_decoupled smoketest: the segment's far end (100m away) moved by EXACTLY "
          "the near-end's own translate delta (off by %.6fm) -- no extra unwanted rotation" % dist_far)

    # ============================================================ B: migration of pre-existing
    # (stale rotation_euler) content preserves current visual state, then decouples from then on.
    result2 = opint.build_intersection_geometry(
        context, scene_coll, (500.0, 0.0, 0.0), '4WAY', 0.0, 90.0, "",
        5.0, 1, [0, 0, 0, 0], 9.0, 12.0, 8, 'BOX', 0.15, 0.25,
        None, False, "", "", 'LEFT')
    inter2 = result2["coll"]
    arm_n2 = next(o for o in inter2.objects if o.get("rka_arm_name") == "N")
    origin2 = opint.get_or_create_origin_marker(inter2)

    # Simulate PRE-FIX content: drag the arm to a new angle the OLD way (position only, as every
    # historical drag would have been), WITHOUT going through the new code at all this time --
    # rotation_euler stays frozen at creation time, exactly like a real old .blend file.
    old_style_angle = math.radians(37.0)
    dist2 = math.hypot(arm_n2.location.x - origin2.location.x, arm_n2.location.y - origin2.location.y)
    arm_n2.location.x = origin2.location.x + dist2 * math.cos(old_style_angle)
    arm_n2.location.y = origin2.location.y + dist2 * math.sin(old_style_angle)
    del arm_n2["rka_arm_angle_migrated"]   # simulate content saved before this fix existed
    stale_rotation = arm_n2.rotation_euler.z   # still the ORIGINAL creation-time angle (0 deg)
    _assert(abs(stale_rotation - old_style_angle) > 0.1,
            "sanity: rotation_euler should be STALE (still 0) relative to the dragged angle")

    opint.rebuild_intersection_in_place(context, inter2)
    inter2 = opint.local_collection(inter2.name)
    arm_n2 = next(o for o in inter2.objects if o.get("rka_arm_name") == "N")
    _assert(arm_n2.get("rka_arm_angle_migrated") is True,
            "the first rebuild should migrate and stamp the flag")
    migrated_angle = arm_n2.get("rka_arm_angle", -999.0)
    _assert(abs(migrated_angle - 37.0) < 0.1,
            "migration should preserve the CURRENT (position-derived, old-style-dragged) angle "
            "of 37 deg, not silently snap back to the stale creation-time rotation (0 deg) -- "
            "got %.2f" % migrated_angle)
    print("arm_angle_decoupled smoketest: migrating pre-fix content preserved its current "
          "visual angle (%.2f deg) instead of reverting to the stale rotation_euler" % migrated_angle)

    # After migration, a further pure translate must NOT change the angle again (now decoupled).
    arm_n2.location.x += 0.3
    opint.rebuild_intersection_in_place(context, inter2)
    arm_n2 = next(o for o in opint.local_collection(inter2.name).objects
                  if o.get("rka_arm_name") == "N")
    _assert(abs(arm_n2.get("rka_arm_angle", -999.0) - migrated_angle) < 0.05,
            "after migration, a pure translate must no longer change the angle -- was %.2f, now %.2f"
            % (migrated_angle, arm_n2.get("rka_arm_angle")))
    print("arm_angle_decoupled smoketest: after migration, further position-only nudges no "
          "longer change the angle at all")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
