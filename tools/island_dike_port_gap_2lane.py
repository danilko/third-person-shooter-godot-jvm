#!/usr/bin/env python3
"""island_dike_port_gap_2lane.py -- a ONE-SHOT edit of the arterials input (2026-10-04, two-lane ramps): the dike road
`ring_kita__11` moves a further SHIFT north between its two junctions, after `island_dike_port_gap.py`'s first move.

    python3 tools/island_dike_port_gap_2lane.py [<arterials record>]

The port's eastbound entrance (`island_expressway.port_entrance`) is two lanes now (user: every ramp), and a one-way
road lays its lanes to the LEFT of its stations -- here the dike road's side. At PORT_ON_OFF 18 its second lane lay over
the dike road's footway (probe_road_clear: a corner prop in it) and the terrain stamp held the ground under it at the
dike road's height (probe_road_stamp: a FILL sample 3.1 m up). Running the ramp nearer the Wangan instead shrank its arc
into the T to R 9, and the setback solve then slid all three of the T's mouths 80 m west onto one point (flow: 2 broken
lanes). So the dike road moves: its three interior stations, the junction mouths staying.

Refuses to run twice (the x -340 station already north of y -1080).
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

INPUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
SHIFT = {-407.2: 5.0, -340.2: 6.0, -273.2: 5.0}     # station x -> metres north (record +y)


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    road = net.roads["ring_kita__11"]
    moved = 0
    for u in road.points[1:-1]:
        p = net.points[u]
        dy = next((v for x, v in SHIFT.items() if abs(p.pos[0] - x) < 1.0), None)
        if dy is None:
            continue
        if abs(p.pos[0] + 340.2) < 1.0 and p.pos[1] > -1080.0:
            raise SystemExit("island_dike_port_gap_2lane: already applied (x -340 at y %.1f)" % p.pos[1])
        p.pos = (p.pos[0], p.pos[1] + dy, p.pos[2])
        moved += 1
    pm.save_network(net, path)
    print("island_dike_port_gap_2lane: moved %d ring_kita__11 station(s) north -> %s" % (moved, path))


if __name__ == "__main__":
    main(sys.argv[1:])
