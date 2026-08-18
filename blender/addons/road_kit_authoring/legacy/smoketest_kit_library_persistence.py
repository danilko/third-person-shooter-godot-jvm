#!/usr/bin/env python3
"""
smoketest_kit_library_persistence.py -- headless verification for a confirmed real bug found
against `world_session.blend` (2026-08, user-reported: "the street lamp/traffic light still not
working, even after enable, there is no object being added into world_session... even after click
on set lamp in panel" -- and, separately, a segment's `rka_median_asset_collection` pointing at a
piece that had silently stopped resolving). Root cause: `RKA_OT_link_kit_library`/`RKA_OT_
link_curb_kit_library` linked every piece Collection into `bpy.data`, but nothing in the local
file held a REAL reference to the Collection itself (every caller resolves a piece purely by NAME,
`ops_intersection._resolve_curb_asset`) -- so a linked Collection with no other referencer is
silently DROPPED on the next save (Blender's normal orphan-data behavior), confirmed by direct
inspection of `world_session.blend`: its curb-kit library was still referenced (`bpy.data.
libraries`, users=1) but held ZERO of its piece Collections. `_kit_library_holder_collection`
(`ops_placement.py`) now parents every linked piece under a dedicated hidden holder collection --
a real, persistent reference -- the moment it's linked.

This test SAVES to a real temp .blend and REOPENS it (the only way to actually exercise Blender's
orphan-data-drop behavior -- it doesn't happen mid-session) to prove the fix, not just that linking
alone works (which the OTHER smoketests already cover plenty).

RUN: blender --background --python-exit-code 1 --python addons/road_kit_authoring/smoketest_kit_library_persistence.py
"""
import bpy
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(ADDONS_DIR)
sys.path.insert(0, ADDONS_DIR)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                          # noqa: E402
from road_kit_authoring import ops_placement as opplace    # noqa: E402
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

    ret = bpy.ops.rka.link_curb_kit_library()
    _assert(ret == {'FINISHED'}, ret)
    ret2 = bpy.ops.rka.link_kit_library()
    _assert(ret2 == {'FINISHED'}, ret2)

    holder = bpy.data.collections.get(opplace.KIT_LIBRARY_HOLDER_COLLECTION)
    _assert(holder is not None, "the kit-library holder collection should exist after linking")
    _assert(holder.name in context.scene.collection.children,
            "the holder should be linked into the scene root (a real reference)")
    _assert(bpy.data.collections.get("Kit_Median_YellowSeparator") is not None,
            "sanity: Kit_Median_YellowSeparator should resolve right after linking")
    holder_child_names = {c.name for c in holder.children}
    _assert("Kit_Median_YellowSeparator" in holder_child_names,
            "the curb kit library's pieces should be parented under the holder, got %s"
            % holder_child_names)
    _assert("Kit_TrafficLight_L1" in holder_child_names,
            "Kit_TrafficLight_L1 should also be parented under the holder")
    print("smoketest_kit_library_persistence: linking both libraries parents every piece under "
          "a dedicated holder collection (%d pieces)" % len(holder_child_names))

    # --- the actual regression: save to a real file, reopen it, confirm nothing was dropped.
    tmp_path = os.path.join(tempfile.gettempdir(), "rka_kit_library_persistence_test.blend")
    bpy.ops.wm.save_as_mainfile(filepath=tmp_path)
    bpy.ops.wm.open_mainfile(filepath=tmp_path)

    reopened_median = bpy.data.collections.get("Kit_Median_YellowSeparator")
    _assert(reopened_median is not None,
            "Kit_Median_YellowSeparator should STILL resolve after a real save + reopen cycle -- "
            "this is the exact bug: it silently vanished from world_session.blend the same way, "
            "leaving only a dangling library reference with 0 of its piece collections")
    reopened_light = bpy.data.collections.get("Kit_TrafficLight_L1")
    _assert(reopened_light is not None,
            "Kit_TrafficLight_L1 should also survive the save/reopen cycle")
    reopened_holder = bpy.data.collections.get(opplace.KIT_LIBRARY_HOLDER_COLLECTION)
    _assert(reopened_holder is not None and reopened_holder.name in bpy.context.scene.collection.children,
            "the holder collection itself should survive and stay linked into the scene")
    print("smoketest_kit_library_persistence: every linked piece survives a real save + reopen "
          "cycle -- the actual fix for 'lamp/asset piece stops working, even right after linking'")

    os.remove(tmp_path)
    print("SMOKETEST OK")


if __name__ == "__main__":
    main()
