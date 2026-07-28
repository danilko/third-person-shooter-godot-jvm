#!/usr/bin/env python3
"""build_district_test_b.py -> districts/District_test_7_8.blend

Small COMPANION test district for the multi-district streaming/connectivity test (see
road_blender_godot.md P6.9 addendum) -- built to connect to District_test_8_8.blend (a copy of
the user-designated debug_road.blend fixture) at debug_road's own known dangling stub:
Segment_010's far end, local Blender point (-132.0, 0.0, 0.15) -- confirmed isolated (no other
piece reaches it) via `tools/save_lane_kit.py` + `lib/lane_kit.py`'s connectivity report.

Districts are authored in LOCAL coordinates and positioned entirely by their WorldZoneMarker's
world position at stream time (WorldZoneManager: `marker.addChild(geo)` -- confirmed by reading
the Java directly, not assumed). So this district's own "connector" arm is built reaching to ITS
OWN local origin (0, 0, ~0.15) -- placing this district's marker at world (-132, 0, 0) then makes
that connector point land exactly on District_test_8_8's Segment_010 stub in world space, with
zero coordinate-shifting math needed in either .blend.

Layout (local coordinates):
  - One 3-way intersection at local (-60, 0) -- arms: EAST (connector, extended to local (0,0)),
    WEST (a short dead-end stub, just for a bit of visual complexity), NORTH (another short stub).
  - Everything 1 lane/direction, addon operator defaults otherwise.

RUN: blender --background --python tools/build_district_test_b.py
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.dirname(HERE)                        # assets/world_source
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "addons"))

import road_kit_authoring as rka                              # noqa: E402
from road_kit_authoring import ops_intersection as opint       # noqa: E402
from road_kit_authoring import ops_segment as opseg            # noqa: E402
import kit_common as kc                                        # noqa: E402
import assemble as asm                                          # noqa: E402

OUT = os.path.join(BP, "districts", "District_test_7_8.blend")
INTERSECTION_CENTER = (-60.0, 0.0, 0.0)   # raw cursor (pre-lane_surface_z), local coordinates
CONNECTOR_TARGET = (0.0, 0.0, 0.0)        # local origin -- lands on District A's stub once this
                                            # district's marker sits at world (-132, 0, 0)


def main():
    context = bpy.context
    if not hasattr(bpy.types.Scene, "rka"):
        rka.register()
    kc.setup_units()
    asm.wipe_scene()

    manual = kc.get_coll("MANUAL")

    result = opint.build_intersection_geometry(
        context, manual, cursor=INTERSECTION_CENTER, preset='NWAY', rotation_deg=0.0,
        side_angle=90.0, arm_angles_str="0,90,180", lane_width=5.0, lanes=1,
        lane_arm_overrides="", kerb_radius=6.0, tail_length=10.0, segments=8, curb_style='BOX',
        curb_height=0.15, curb_thickness=0.25, lane_map=None, join_visual_mesh=False,
        export_path="", gltf_export_path="", traffic_side='LEFT')
    print("MIGRATE: built intersection '%s' (%d arms)" % (result["coll"].name, len(result["arms"])))

    # Arm A = 0deg (east, the connector toward District_test_8_8), B = 90deg (north stub),
    # C = 180deg (west stub) -- preset_nway names arms alphabetically in angle-string order.
    def arm_port(letter):
        marker = result["coll"].objects.get("arm_%s" % letter)
        return tuple(marker.location)

    def build_stub(label, port, target, base_name):
        spine = [port, target]
        seg = opseg._build_segment_from_points(
            context, manual, spine, 5.0, 1, 1, 'BOX', 'BOX', 0.15, 0.25, False, "", "",
            base_name=base_name, traffic_side='LEFT')
        print("MIGRATE: built segment '%s' for %s" % (seg["coll"].name, label))

    connector_target_lifted = (CONNECTOR_TARGET[0], CONNECTOR_TARGET[1],
                                CONNECTOR_TARGET[2] + context.scene.rka.lane_surface_z)
    build_stub("connector (east, toward District_test_8_8)", arm_port("A"),
               connector_target_lifted, "Segment_connector")
    build_stub("north stub", arm_port("B"),
               (INTERSECTION_CENTER[0], INTERSECTION_CENTER[1] + 40.0,
                INTERSECTION_CENTER[2] + context.scene.rka.lane_surface_z), "Segment_north_stub")
    build_stub("west stub", arm_port("C"),
               (INTERSECTION_CENTER[0] - 40.0, INTERSECTION_CENTER[1],
                INTERSECTION_CENTER[2] + context.scene.rka.lane_surface_z), "Segment_west_stub")

    for o in list(bpy.context.view_layer.objects):
        if o is not None:
            o.select_set(False)
    kc.save_blend(os.path.dirname(OUT), os.path.basename(OUT))
    print("MIGRATE: saved %s" % OUT)


if __name__ == "__main__":
    main()
