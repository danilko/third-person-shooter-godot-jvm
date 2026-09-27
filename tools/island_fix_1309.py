#!/usr/bin/env python3
"""island_fix_1309.py -- ONE-SHOT edit of the arterials INPUT (user, 2026-09-26, postal 13-9).

    python3 tools/island_fix_1309.py [<arterials record>]      # refuses to run twice

`nishi_dori__5` ran north to (-115, 540) and then cut NORTH-EAST to meet `chuo_dori` where it ends, so the two
arterials' mouths left that junction only 28 deg apart: a thin Y whose kerb corner stood between two carriageways
(the "sidewalk poking out in the middle of the road"), with a folded pad further south where `kita_cho_625` crossed
the two roads 50 m apart.

Reshaped as a T: `nishi_dori` keeps going north to the junction's latitude, turns east on a wide corner and meets it
from the WEST, so the junction's arms are west (nishi_dori), east (nishi_dori__6) and south (chuo_dori, the stem).
Only the three stations after (-115, 540) move; every link is unchanged. `island_layout.py`'s setback solve places
the mouths.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.PIECES, "IslandRoads.arterials.roads.json")
ROAD = "nishi_dori__5"
# record frame (x, y); the road's stations from index 4 on. The last is the junction mouth.
NEW = [(-110.0, 615.0), (-85.0, 680.0), (-29.0, 703.0)]


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    r = net.roads[ROAD]
    if len(r.points) != 7:
        raise SystemExit("island_fix_1309: %s has %d stations, expected 7" % (ROAD, len(r.points)))
    last = net.points[r.points[-1]].pos
    if abs(last[1] - NEW[-1][1]) < 1.0 and abs(last[0] - NEW[-1][0]) < 1.0:
        raise SystemExit("island_fix_1309: already applied to %s" % path)
    for u, (x, y) in zip(r.points[4:], NEW):
        p = net.points[u]
        p.pos = (x, y, p.pos[2])
    pm.save_network(net, path)
    print("island_fix_1309: %s reshaped into a T on chuo_dori at (%.0f, %.0f)" % (ROAD, NEW[-1][0], NEW[-1][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
