#!/usr/bin/env python3
"""island_port_road_square.py -- a ONE-SHOT edit of the arterials input (2026-10-05, user: "straighten the port road
so it is square, |___|, rather than wiggling at its corners -- easier to drive; and give the military base a direct
road").

    python3 tools/island_port_road_square.py [<arterials record>]

kichi_dori__2 (the port loop: down x -500, east along the platform's north strip, up x -160) turned each corner in ONE
60 m diagonal span (a single station on the old rounded polyline), so both corners read as slanted cuts. It is re-laid
as straight legs with SQUARE corners: a corner station exactly on the corner and one CORNER_LEAD m either side (the
kit's AUTO facing then turns it on a ~15 m radius, a city street corner). The east-west leg stays at Godot z 1230.
A separate gate road from the west corner was tried and does not fit: an east-west leg moved north to z 1190 (to leave
room for one) is only ~59 m south of the Wangan, too close for the port's westbound exit to turn onto it -- it needs
a north-south road to land on, the west leg, at PORT_T. So the military base's gate is ON the corner: the north fence
gate at x -500 (site_military.GATE_X), 20 m south of the corner, entered straight on from kichi_dori over a dropped
kerb and a paved apron (island_buildings.SITE_GATE_ENTRIES).

Refuses to run twice (kichi_dori__2's second station is no longer the one this was written against).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
START = "p_07f132e1"      # (-500, -1106) record: the junction it leaves (kept)
SECOND = "p_65fbe07b"     # its old second station (removed)
END = "p_4029df0b"        # (-160, -1117.8): the junction it ends on (kept)
WEST_X, EAST_X = -500.0, -160.0
PORT_Y = 1230.0           # the east-west leg, record y = -PORT_Y (Godot z 1230, where it was)
CORNER_LEAD = 15.0        # stations this far either side of a square corner
STEP = 60.0               # stations along the straights
PLATFORM_Z, PLATFORM_GROUND = 4.01, 3.906   # the old stations' road and ground height on the port platform (record)


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    r = net.roads["kichi_dori__2"]
    if r.points[0] != START or r.points[1] != SECOND or r.points[-1] != END:
        raise SystemExit("island_port_road_square: already applied, or kichi_dori__2 is not the road this was written "
                         "against")
    s, e = net.points[START], net.points[END]
    y = -PORT_Y
    pts = []
    # down x -500 to the west corner
    yy = s.pos[1] - STEP
    while yy > y + CORNER_LEAD + 20.0:
        pts.append((WEST_X, yy))
        yy -= STEP
    pts += [(WEST_X, y + CORNER_LEAD), (WEST_X, y), (WEST_X + CORNER_LEAD, y)]
    # east along the strip
    xx = WEST_X + CORNER_LEAD + STEP
    while xx < EAST_X - CORNER_LEAD - 20.0:
        pts.append((xx, y))
        xx += STEP
    pts += [(EAST_X - CORNER_LEAD, y), (EAST_X, y), (EAST_X, y + CORNER_LEAD)]
    # up x -160 to the junction it ends on
    yy = y + CORNER_LEAD + STEP
    while yy < e.pos[1] - 20.0:
        pts.append((EAST_X, yy))
        yy += STEP
    for u in r.points[1:-1]:
        net.remove_point(u)
    before = s
    for i, (x, yv) in enumerate(pts):
        p = net.add_station(r, (x, yv, PLATFORM_Z))
        p.ground_z, p.has_ground_z = PLATFORM_GROUND, True
        r.points.remove(p.uid)
        r.points.insert(1 + i, p.uid)
        net.link(before.uid, p.uid)
        before = p
    net.link(before.uid, e.uid)
    pm.save_network(net, path)
    print("island_port_road_square: kichi_dori__2 re-laid square, %d station(s), east-west leg at record y %.0f -> %s"
          % (len(pts), y, path))


if __name__ == "__main__":
    main(sys.argv[1:])
