"""Step 7's acceptance test: ONE road system in the tree, not three.

    blender --background --python-exit-code 1 \
            --python blender/addons/road_kit_authoring/smoketest_point_addon.py

Registration is the one thing every other smoketest routes around -- they import submodules
directly, so a broken `__init__.py` would not fail any of them while making the addon unusable in
the actual editor. This asserts the package itself: it enables, it registers the point model, it
does NOT register the archived mesh graph, and it unregisters without leaving operators or Scene
properties behind (a leaked `bpy.types.Scene` property survives an addon disable and then collides
with the next enable).
"""

import os
import sys

import addon_utils
import bpy

NAME = "road_kit_authoring"


def check(msg):
    print("OK:", msg)


def main():
    ok = 0
    addon_utils.disable(NAME, default_set=False)
    addon_utils.enable(NAME, default_set=False, persistent=False)

    for attr in ("RKA_OT_point_build", "RKA_OT_point_clear", "RKA_OT_auto_setback",
                 "RKA_OT_make_intersection", "RKA_OT_export_lanekit", "RKA_OT_validate",
                 "RKA_OT_preview_refresh", "RKA_OT_preview_report",
                 "RKA_PT_point", "RKA_PT_junction", "RKA_PT_road", "RKA_PT_preview",
                 "RKA_PT_build"):
        assert hasattr(bpy.types, attr), attr
    assert hasattr(bpy.types.Object, "rka_pt")
    assert hasattr(bpy.types.Collection, "rka_road")
    assert hasattr(bpy.types.Scene, "rka_live_rebuild")
    assert hasattr(bpy.types.Scene, "rka_overlay")
    assert hasattr(bpy.types.Scene, "rka_preview_flow")
    check("the addon enables and registers the point model end to end")
    ok += 1

    for attr in ("RKA_OT_graph_build", "RKA_OT_graph_solve", "RKA_PT_graph"):
        assert not hasattr(bpy.types, attr), "%s is still registered -- the archive is live" % attr
    here = os.path.dirname(os.path.abspath(__file__))
    stray = [f for f in os.listdir(here) if f.startswith("graph_")]
    assert not stray, stray
    assert not os.path.isdir(os.path.join(here, "legacy")), "the per-piece model is still on disk"
    assert os.path.isdir(os.path.join(here, "legacy_graph")), "the mesh graph was not archived"
    check("one road system in the tree: legacy deleted, legacy_graph archived and not imported")
    ok += 1

    addon_utils.disable(NAME, default_set=False)
    leaked = [a for a in ("RKA_OT_point_build", "RKA_PT_point", "RKA_OT_preview_refresh",
                          "RKA_PT_preview") if hasattr(bpy.types, a)]
    assert not leaked, leaked
    leaked = [a for a in ("rka_live_rebuild", "rka_overlay", "rka_overlay_text",
                          "rka_preview_flow", "rka_preview_cars", "rka_preview_labels",
                          "rka_preview_density", "rka_preview_speed")
              if hasattr(bpy.types.Scene, a)]
    assert not leaked, leaked
    assert not hasattr(bpy.types.Object, "rka_pt")
    check("unregister leaves no operator, panel or Scene property behind")
    ok += 1

    addon_utils.enable(NAME, default_set=False, persistent=False)
    addon_utils.disable(NAME, default_set=False)
    addon_utils.enable(NAME, default_set=False, persistent=False)
    assert hasattr(bpy.types, "RKA_OT_point_build")
    check("enable / disable / enable round-trips -- Reload Scripts is safe")
    ok += 1

    print("\nALL SMOKETESTS PASSED (%d)" % ok)


main()
