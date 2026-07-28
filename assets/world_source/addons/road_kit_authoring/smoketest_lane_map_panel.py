#!/usr/bin/env python3
"""
smoketest_lane_map_panel.py -- headless verification for `RKA_OT_set_lane_map` (2026-07-27,
user-reported: "apply lane kit seem not work with same reason as curb in panel, only work on
initial creation, but after change no longer able to modify"). Same root cause/fix shape as
`RKA_OT_set_curb_style`: 'Lane Map Override' previously only had a build-time-only F9 redo-panel
field -- no persistent way to change it on an already-built intersection. `RKA_OT_set_lane_map`
(a `invoke_props_dialog` text-entry operator, wired into panel.py) sets the `rka_lane_map` custom
property (via `custom_props.lane_map_to_custom`/`parse_lane_map`) and rebuilds in place.

Uses EXEC_DEFAULT with `lane_map_text` passed explicitly -- `invoke_props_dialog` needs a real GUI
event loop and can't be exercised headlessly (see reference_blender_headless_invoke); this tests
the operator's actual execute()/validation logic, which is the real risk surface.

RUN: blender --background --python addons/road_kit_authoring/smoketest_lane_map_panel.py
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
from road_kit_authoring import ops_intersection as opint  # noqa: E402
from road_kit_authoring import custom_props                # noqa: E402
import kit_common as kc                                     # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _lanecl_tags(coll):
    return sorted(o.name for o in coll.objects if o.name.startswith("lanecl_"))


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
    _assert("rka_lane_map" not in coll.keys(), "fresh build should have no lane_map override")
    default_tags = _lanecl_tags(coll)
    _assert(len(default_tags) > 0, "should have some default lane movements")

    context.view_layer.objects.active = next(o for o in coll.objects if "rka_arm_name" in o.keys())

    # poll() must fail on a non-intersection selection.
    seg = opint  # just needs any non-intersection object; reuse an arm-less dummy check instead
    context.view_layer.objects.active = None
    _assert(not bpy.ops.rka.set_lane_map.poll(), "poll should fail with nothing active")
    context.view_layer.objects.active = next(o for o in coll.objects if "rka_arm_name" in o.keys())
    _assert(bpy.ops.rka.set_lane_map.poll(), "poll should succeed with an intersection arm active")

    # Malformed syntax must be rejected WITHOUT touching stored state or geometry. bpy.ops raises
    # RuntimeError for an ERROR-reported CANCELLED result -- that IS the expected outcome here.
    try:
        bpy.ops.rka.set_lane_map('EXEC_DEFAULT', lane_map_text="garbage-no-colon")
        _assert(False, "malformed lane_map_text should have raised/CANCELLED, it did not")
    except RuntimeError as exc:
        _assert("Lane Map Override" in str(exc), "unexpected error message: %s" % exc)
    _assert("rka_lane_map" not in coll.keys(),
            "a rejected malformed override must not get stored")
    print("smoketest_lane_map_panel: malformed syntax rejected, no partial/corrupt state written")

    # Valid override, one clause: N->S single lane 0-0 (a real, resolvable pairing this fixture
    # already has going straight through).
    ret = bpy.ops.rka.set_lane_map('EXEC_DEFAULT', lane_map_text="N>S:0-0")
    _assert(ret == {'FINISHED'}, "valid lane_map_text did not finish: %s" % (ret,))
    _assert("rka_lane_map" in coll.keys(), "override should now be stored on the collection")
    stored = custom_props.read_lane_map_override(coll)
    _assert(stored == {("N", "S"): [(0, 0)]},
            "stored override should round-trip exactly, got %r" % (stored,))
    print("smoketest_lane_map_panel: applying a valid override via the operator (not the build-time "
          "F9 panel) persisted it to rka_lane_map and rebuilt without error")

    # Re-apply a DIFFERENT override on the SAME already-built piece (the actual bug being fixed --
    # confirms this isn't a one-shot, build-time-only mechanism).
    ret = bpy.ops.rka.set_lane_map('EXEC_DEFAULT', lane_map_text="N>S:0-0; E>W:0-0")
    _assert(ret == {'FINISHED'}, "second override change did not finish: %s" % (ret,))
    stored2 = custom_props.read_lane_map_override(coll)
    _assert(stored2 == {("N", "S"): [(0, 0)], ("E", "W"): [(0, 0)]},
            "second override should replace (not merge with/leak) the first, got %r" % (stored2,))
    print("smoketest_lane_map_panel: changing the override AGAIN on the same already-built "
          "intersection worked -- confirms it's not build-time-only")

    # Blank text clears the override back to default behavior.
    ret = bpy.ops.rka.set_lane_map('EXEC_DEFAULT', lane_map_text="")
    _assert(ret == {'FINISHED'}, "clearing did not finish: %s" % (ret,))
    _assert("rka_lane_map" not in coll.keys(), "blank text should remove the override entirely")
    cleared_tags = _lanecl_tags(coll)
    _assert(cleared_tags == default_tags,
            "clearing the override should restore the exact original default lane movements")
    print("smoketest_lane_map_panel: blank text cleared the override and restored default lane "
          "movements exactly")

    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
