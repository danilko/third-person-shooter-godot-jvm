#!/usr/bin/env python3
"""ONE-SHOT (user, 2026-09-28): remove `hatoba_dori` (+ `hatoba_dori__2`) from the arterials INPUT.

It had no clear job and only added a strange hill between the two dike stretches. Its three junctions go with it:
the two where it met the ring become plain stations (the ring halves they split are merged back into one road), and
the one it shared with the ring and `eki_minami_dori` stays a T. Refuses to run twice.

    python3 tools/island_remove_hatoba.py [record]    (default: IslandRoads.arterials.roads.json)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import island_roadgen  # noqa: F401,E402  (the kit's path)
import point_model as pm  # noqa: E402

GONE = ("hatoba_dori", "hatoba_dori__2")
MERGE = (("ring_kita__7", "ring_kita__8"), ("ring_kita__9", "ring_kita__10"))   # (kept, absorbed), chain order


def main(argv):
    path = argv[0] if argv else os.path.join(ROOT, "assets", "world_source", "pieces",
                                             "IslandRoads.arterials.roads.json")
    net = pm.load_network(path)
    if not any(n in net.roads for n in GONE):
        raise SystemExit("island_remove_hatoba: %s has no hatoba_dori (already removed)" % path)
    for n in GONE:
        for u in list(net.roads[n].points):
            net.remove_point(u)
        del net.roads[n]
    for keep, absorb in MERGE:
        a, b = net.roads[keep], net.roads[absorb]
        ua, ub = a.points[-1], b.points[0]
        net.unlink(ua, ub)                 # the two ring mouths' own junction link: the pad is gone
        # the two former mouths: no junction left on either, so plain chain stations
        for u in (ua, ub):
            p = net.points[u]
            assert not p.targets(pm.LINK_JUNCTION), (u, p.links)
            p.role = pm.SEGMENT
            p.traffic_light = False
            p.setback_locked = False
        a.points.extend(b.points)
        del net.roads[absorb]
        net.link(ua, ub)
    pm.save_network(net, path)
    print("island_remove_hatoba: removed %s; merged %s" % (", ".join(GONE),
                                                          ", ".join("%s+%s" % m for m in MERGE)))


if __name__ == "__main__":
    main(sys.argv[1:])
