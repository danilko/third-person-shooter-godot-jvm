#!/usr/bin/env python3
"""island_dike_port_gap.py -- a ONE-SHOT edit of the arterials input (PLAN.md review 2026-10-02 night, port access (a)):
move the dike road `ring_kita__11` north between its two junctions (kichi_dori at x -500, chuo_dori at x -190), so the
port's EASTBOUND entrance (`island_expressway.port_entrance`) has room to climb between it and the Wangan.

    python3 tools/island_dike_port_gap.py [<arterials record>]

Measured before: the dike road's centreline runs 39 m north of the Wangan's at x -407, 31 m at x -340 and 24 m at
x -273; with the mainline's 10.5 m half band and the dike road's 13.25 m (2+2 lanes and a 4 m footway), the gap
between the two paved edges was 15 m, 8 m and 0 m. A one-lane ramp needs ~7 m of it and must run far enough to climb
the 5.6 m from the dike crest to the deck. Y1 holds the gap west of x -450, so the ramp climbs east of it.

The two end stations (the junction mouths) stay; the three interior stations move north by SHIFT (a gentle S at each
end, not a jog). Refuses to run twice (the x -340 station already north of y -1090).
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

INPUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
SHIFT = {-407.2: 10.0, -340.2: 16.0, -273.2: 16.0}     # station x -> metres north (record +y)


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
        if abs(p.pos[0] + 340.2) < 1.0 and p.pos[1] > -1090.0:
            raise SystemExit("island_dike_port_gap: already applied (x -340 at y %.1f)" % p.pos[1])
        p.pos = (p.pos[0], p.pos[1] + dy, p.pos[2])
        moved += 1
    if moved != len(SHIFT):
        raise SystemExit("island_dike_port_gap: found %d of %d stations" % (moved, len(SHIFT)))
    pm.save_network(net, path)
    print("island_dike_port_gap: %d station(s) of ring_kita__11 moved north -> %s" % (moved, path))


if __name__ == "__main__":
    main(sys.argv[1:])
