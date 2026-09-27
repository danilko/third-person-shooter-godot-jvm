#!/usr/bin/env python3
"""island_split_pads.py -- ONE-SHOT (2026-09-26, user): split the arterials input's two 5-arm pads into ordinary
junctions, the user's sketch for postal 12-11:

    ||       ||
    | ======= =======
    ||       ||

Both pads were TWO north-south roads ~100 m apart forced into ONE pad with an east-west road: a 5-arm pad folds
its footway corners into the carriageway and gives the traffic AI five-way movements. Each becomes a T where the
east-west road meets the first north-south road and a 4-way where it crosses the second, joined by a short piece
of the east-west road:

  * 12-11: nishi_dori (x ~-134) x yamate_dori (a T; yamate starts here, eastward) and chuo_dori (x ~-37) x
    yamate_dori (a 4-way).
  * 15-13/16-14: eki_minami_dori (x ~504) x rinkai_dori (a 4-way) and naka_hondori (x 600) x rinkai_dori (a T;
    naka_hondori starts here, northward).

    python3 tools/island_split_pads.py [<arterials record>]      # applied once; refuses to run twice

Mouth distances are provisional (26 m): `island_layout.py`'s setback solve places every mouth.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import point_model as pm        # noqa: E402

INPUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")


def station(net, road, i):
    return net.roads[road].points[i]


def clique_of(net, u):
    return [u] + [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION]


def dissolve(net, members):
    for a in members:
        for b in members:
            if a != b:
                net.points[a].unlink(b)


def junction(net, members):
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            net.link(a, b, pm.LINK_JUNCTION)
        net.points[a].role = pm.INTERSECTION


def drop_first(net, road):
    """Remove a road's first station (it stood on the wrong side of the new junction)."""
    u = net.roads[road].points[0]
    nxt = net.roads[road].points[1]
    net.points[u].unlink(nxt)
    net.points[nxt].unlink(u)
    net.roads[road].points.remove(u)
    del net.points[u]
    net.points[nxt].role = pm.INTERSECTION
    return nxt


def drop_last(net, road):
    u = net.roads[road].points[-1]
    prv = net.roads[road].points[-2]
    net.points[u].unlink(prv)
    net.points[prv].unlink(u)
    net.roads[road].points.remove(u)
    del net.points[u]
    net.points[prv].role = pm.INTERSECTION
    return prv


def link_piece(net, like, name, a, b):
    """A short piece of the east-west road between the two new junctions, of `like`'s cross-section."""
    src = net.roads[like]
    r = net.add_road(pm.RoadData(name, pm.PointData.from_dict(src.base.to_dict()), ()))
    for f in pm.ROAD_FIELDS:                     # (name, kind, default) rows -- all but the name itself
        if f[0] != "name":
            setattr(r, f[0], getattr(src, f[0]))
    r.road_class = src.road_class
    pa = net.add_station(r, (a[0], a[1], a[2]))
    pb = net.add_station(r, (b[0], b[1], b[2]))
    net.link(pa.uid, pb.uid)
    return pa.uid, pb.uid


def split_1211(net):
    old = clique_of(net, station(net, "yamate_dori", 0))
    assert len(old) == 5, ("12-11 is not a 5-arm pad any more", len(old))
    dissolve(net, old)
    n4, n5 = station(net, "nishi_dori__4", -1), station(net, "nishi_dori__5", 0)
    c4, c5 = station(net, "chuo_dori__4", -1), station(net, "chuo_dori__5", 0)
    # yamate's first station stood between the two roads (it pointed at the old merged pad): drop it, so the
    # next one (x 0) is its mouth east of chuo_dori
    y0 = net.points[station(net, "yamate_dori", 0)].pos
    ye = drop_first(net, "yamate_dori")
    cn = [(net.points[n4].pos[i] + net.points[n5].pos[i]) / 2 for i in range(3)]
    cc = [(net.points[c4].pos[i] + net.points[c5].pos[i]) / 2 for i in range(3)]
    z = y0[2]
    a, b = link_piece(net, "yamate_dori", "yamate_dori_w", (cn[0] + 24.0, cn[1], z), (cc[0] - 24.0, cc[1], z))
    junction(net, [n4, n5, a])
    junction(net, [c4, c5, b, ye])
    return "12-11: T at (%.0f, %.0f) + 4-way at (%.0f, %.0f)" % (cn[0], cn[1], cc[0], cc[1])


def split_1513(net):
    old = clique_of(net, station(net, "naka_hondori", 0))
    assert len(old) == 5, ("15-13 is not a 5-arm pad any more", len(old))
    dissolve(net, old)
    e1, e2 = station(net, "eki_minami_dori", -1), station(net, "eki_minami_dori__2", 0)
    nk = station(net, "naka_hondori", 0)
    # rinkai_dori__6's last station stood EAST of eki_minami (the old pad's west mouth): drop it; rinkai_dori__7's
    # first stood WEST of naka_hondori: drop it
    rw = drop_last(net, "rinkai_dori__6")
    re_ = drop_first(net, "rinkai_dori__7")
    ce = [(net.points[e1].pos[i] + net.points[e2].pos[i]) / 2 for i in range(3)]
    cn = net.points[nk].pos
    cy = (net.points[rw].pos[1] + net.points[re_].pos[1]) / 2
    z = net.points[rw].pos[2]
    a, b = link_piece(net, "rinkai_dori__6", "rinkai_dori__6m", (ce[0] + 24.0, cy, z), (cn[0] - 24.0, cy, z))
    junction(net, [e1, e2, rw, a])
    junction(net, [b, nk, re_])
    return "15-13: 4-way at (%.0f, %.0f) + T at (%.0f, %.0f)" % (ce[0], ce[1], cn[0], cy)


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    if "yamate_dori_w" in net.roads or "rinkai_dori__6m" in net.roads:
        raise SystemExit("island_split_pads: already applied to %s" % path)
    print("island_split_pads: " + split_1211(net))
    print("island_split_pads: " + split_1513(net))
    pm.save_network(net, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
