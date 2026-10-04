#!/usr/bin/env python3
"""The VEHICLE ENTRY test street (user, 2026-10-04: "build one test street for comparison"): one straight 200 m street,
one lane each way, 3 m footways and 15 cm kerbs, with three 5 m entries on its LEFT side -- one per
`PointData.entry_style`, so the three can be compared side by side:

    x =  50   DROP          the kerb and footway lowered to a 5 cm lip in their own concrete (切り下げ)
    x = 100   DROP_ASPHALT  the same drop, its footway paved in the road's asphalt
    x = 150   CUT           the kerb and footway removed, exposing the ground

    python3 tools/roadkit_entry_test.py            write assets/world_source/pieces/EntryTest.roads.json
    blender/tools/build_roads_piece.sh assets/world_source/pieces/EntryTest.roads.json Roads_EntryTest
    godot --path . --script tools/godot/shot_entry_test.gd -- <out dir>     (pictures; needs a display)
    godot --headless --path . --script tools/godot/probe_entry_test.gd      (the surface profile across each entry)

Record frame (Z-up); the street runs along +x at y = 0, its left side is +y (Godot -z).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm  # noqa: E402
import point_record_ops as ro  # noqa: E402

OUT = os.path.join(ROOT, "assets", "world_source", "pieces", "EntryTest.roads.json")
LENGTH = 200.0
WALK = 3.0
ENTRIES = ((50.0, pm.ENTRY_DROP), (100.0, pm.ENTRY_DROP_ASPHALT), (150.0, pm.ENTRY_CUT))
ENTRY_W = 5.0
LANE = 4.5          # point_model's default lane width


def build():
    net = pm.NetworkData()
    base = pm.PointData(uid="", lanes_fwd=1, lanes_bwd=1, lane_width=LANE, left_walk_width=WALK,
                        right_walk_width=WALK, left_kerb_height=0.15, right_kerb_height=0.15, design_speed=30.0)
    road = net.add_road(pm.RoadData("entry_test", base, road_class="street", barrier_height=0.0))
    prev = None
    for x in (0.0, LENGTH / 2.0, LENGTH):
        p = net.add_station(road, (x, 0.0, 0.0), has_ground_z=True)
        if prev is not None:
            net.link(prev.uid, p.uid, pm.LINK_SEGMENT)
        prev = p
    for x, style in ENTRIES:
        res = ro.add_entry(net, x, LANE + WALK - 0.5, ENTRY_W)        # a point on the left footway
        assert res is not None and res[2] == "left", res
        net.points[res[1]].entry_style = style
    return net


if __name__ == "__main__":
    net = build()
    pm.save_network(net, OUT)
    print("roadkit_entry_test: %d stations, entries %s -> %s"
          % (len(net.points), ", ".join("%s at x %.0f" % (s, x) for x, s in ENTRIES), OUT))
