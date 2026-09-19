#!/usr/bin/env python3
"""island_remove_gulf_crossing.py -- remove the road bridge across the gulf (PLAN.md 3.8, user decision 2026-09-18).

    python3 tools/island_remove_gulf_crossing.py assets/world_source/pieces/IslandRoads.roads.json

The island keeps ONE sea bridge, the airport's (`kuko_dori`, to become the Rainbow Bridge). The gulf crossing was
`hama_dori`'s three bridge pieces from the inlet's east shore (1077, 581) west over the water to the harbour junction
(-162, 1101); both shores are already joined by land roads. This deletes those pieces (`hama_dori__2/3/4`) and the
harbour junction's fourth mouth with them, so the junction becomes a three-arm one. `hama_dori` itself is kept to the
inlet's east shore: it ends there as the future military harbour's access road (a dead end until 3.3b's turnarounds).

Idempotent: with the pieces already gone it changes nothing. Afterwards re-run the island pipeline (PLAN.md "Road Kit
gate is ONE command" block): `roadkit_cli.py setback`, `island_road_zones.py`, the piece build, the terrain re-stamp,
`island_traffic_zones.py`, and the road-map bake.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

GONE = ("hama_dori__2", "hama_dori__3", "hama_dori__4")


def main(path):
    net = pm.load_network(path)
    doomed = [r for r in GONE if r in net.roads]
    if not doomed:
        print("island_remove_gulf_crossing: already removed, nothing to do")
        return
    uids = [u for r in doomed for u in net.roads[r].points]
    for u in uids:
        net.remove_point(u)
    for r in doomed:
        del net.roads[r]
    # a junction member left with no JUNCTION link is an ordinary station again
    for p in net.points.values():
        if p.role == pm.INTERSECTION and not any(l.type == pm.LINK_JUNCTION for l in p.links):
            p.role = pm.SEGMENT
    pm.save_network(net, path)
    print("island_remove_gulf_crossing: removed %s (%d stations) -> %s" % (", ".join(doomed), len(uids), path))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json"))
