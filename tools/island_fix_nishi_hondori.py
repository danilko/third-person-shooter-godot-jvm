#!/usr/bin/env python3
"""island_fix_nishi_hondori.py -- ONE-SHOT edit of the arterials INPUT (user, 2026-09-25, postal 14-14).

    python3 tools/island_fix_nishi_hondori.py [--check]

`island_network.py` (itself one-shot) made `nishi_hondori` end in a T on `rinkai_dori` by putting the junction mouth
at the HEAD of the chain while the road's old south end stayed after it, so the chain ran

    mouth (268, -223) -> (275, -284) -> (275, -232) -> (275, -171) -> ... north

i.e. south past the junction, a 174 deg fold back, and north again THROUGH the pad with no mouth of its own: a
U-turn drawn as a "circular reverse", with the kerbs and footway of the two overlapping legs standing in the lane.

What it is replaced with, per the user: the road does not turn back, it KEEPS GOING --
* the crossing at `rinkai_dori` becomes an ordinary 4-arm junction (north mouth + the existing south mouth);
* a south leg, `nishi_hondori__s`, runs on into 14-15 and ends in a T on `wangan_dori` (cut to land it).

Idempotent: refused once the fold is gone. `--check` exits 1 while the input still has the fold. The rule that
keeps it from coming back is `island_layout.chain_folds` (asserted on the output).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.PIECES, "IslandRoads.arterials.roads.json")
FOLD = ("p_3969a09e", "p_fc14d13e")     # (275, -284) and (275, -232): the station past the junction and back
SOUTH_MOUTH = "p_88064a00"              # the existing south mouth of the rinkai_dori junction
NORTH_MOUTH = "p_71a2221b"              # (275, -171): becomes the junction's north mouth
X = 275.0
WANGAN_Y = -430.0
MOUTH = 26.0                            # island_trunk_grid.MOUTH; `roadkit_cli.py setback` re-solves it
SPACING = 60.0


def main(argv):
    net = pm.load_network(INPUT)
    folded = all(u in net.points for u in FOLD)
    if "--check" in argv:
        print("island_fix_nishi_hondori: %s" % ("the fold is STILL in the input" if folded else "clean"))
        return 1 if folded else 0
    if not folded:
        print("island_fix_nishi_hondori: already applied (the folded stations are gone)")
        return 0
    road = net.roads["nishi_hondori"]
    for u in FOLD:
        net.remove_point(u)
    # the south mouth leaves the north road; the north road's head is now its own mouth on the junction
    road.points.remove(SOUTH_MOUTH)
    net.unlink(SOUTH_MOUTH, NORTH_MOUTH)
    jn = [SOUTH_MOUTH, NORTH_MOUTH] + sorted({l.target for l in net.points[SOUTH_MOUTH].links
                                              if l.type == pm.LINK_JUNCTION})
    make_junction(net, jn)
    # the south leg: the mouth at rinkai_dori, stations every SPACING, a mouth MOUTH short of wangan_dori
    kwr = {n: getattr(road, n) for n, _k, _d in pm.ROAD_FIELDS if n != "name"}
    south = net.add_road(pm.RoadData("nishi_hondori__s", road.base.copy(), (), **kwr))
    south.points.append(SOUTH_MOUTH)
    y0 = net.points[SOUTH_MOUTH].pos[1]
    y1 = WANGAN_Y + MOUTH
    n = max(1, int(round((y0 - y1) / SPACING)))
    prev = SOUTH_MOUTH
    for k in range(1, n + 1):
        y = y0 + (y1 - y0) * k / n
        p = net.add_station(south, (X, y, 0.0))
        net.link(prev, p.uid)
        prev = p.uid
    end = prev
    # the T on wangan_dori
    a, b = cut_road(net, (X, WANGAN_Y), "wangan_dori", MOUTH)
    make_junction(net, [a, b, end])
    ground = rg.Ground()
    for r in (south, net.road_of(a), net.road_of(b)):
        for u in r.points:
            q = net.points[u]
            if not q.has_ground_z:
                q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True
    pm.save_network(net, INPUT)
    print("island_fix_nishi_hondori: nishi_hondori crosses rinkai_dori (4 arms) and continues as "
          "nishi_hondori__s (%d stations) to a T on wangan_dori; wrote %s" % (n + 1, os.path.relpath(INPUT, rg.ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
