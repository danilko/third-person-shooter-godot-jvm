#!/usr/bin/env python3
"""island_rinkai_south.py -- a ONE-SHOT edit of the arterials input (PLAN.md item 1e, user 2026-09-30, option 3):
move rinkai_dori ~50 m SOUTH between x ~300 and ~950 so naka_hondori, outside C1, is long enough for the S diamond's
OUTSIDE junction (a mirror of its inside one), instead of ending 95 m south of C1 in its own T on rinkai_dori.

    python3 tools/island_rinkai_south.py [<arterials record>]

The shift is smooth (a smoothstep in from x 300 to 470, full to 720, out to 950), so the arterial bends gently rather
than jogging. It moves every rinkai_dori station in that band and the cross roads' mouths at the two junctions it
carries (eki_minami_dori's north and south halves, naka_hondori's south end); a station the moved mouth would crowd
is removed. Refuses to run twice (naka_hondori's south end already south of y -200). The record is the hand-owned
INPUT (`island_layout.py` derives the rest from it), so the change is reviewed like any authored edit.
"""
import math
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402

INPUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
SHIFT = -50.0
X_IN = (300.0, 470.0)
X_OUT = (720.0, 950.0)
CROWD = 30.0          # a station of a moved cross road this close to its moved mouth is removed


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def weight(x):
    if x <= X_IN[0] or x >= X_OUT[1]:
        return 0.0
    if x < X_IN[1]:
        return _smooth((x - X_IN[0]) / (X_IN[1] - X_IN[0]))
    if x <= X_OUT[0]:
        return 1.0
    return 1.0 - _smooth((x - X_OUT[0]) / (X_OUT[1] - X_OUT[0]))


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    naka = net.roads["naka_hondori"]
    if net.points[naka.points[0]].pos[1] < -200.0:
        raise SystemExit("island_rinkai_south: already applied (naka_hondori ends at y %.0f)"
                         % net.points[naka.points[0]].pos[1])
    moved = 0
    for name, r in net.roads.items():
        if not name.startswith("rinkai_dori"):
            continue
        for u in r.points:
            p = net.points[u]
            w = weight(p.pos[0])
            if w > 0.0 and -300.0 < p.pos[1] < -150.0:
                p.pos = (p.pos[0], p.pos[1] + SHIFT * w, p.pos[2])
                moved += 1
    # the cross roads' mouths at the two junctions rinkai carries in the band
    for name, end in (("eki_minami_dori", -1), ("eki_minami_dori__2", 0), ("naka_hondori", 0)):
        r = net.roads[name]
        u = r.points[end]
        p = net.points[u]
        p.pos = (p.pos[0], p.pos[1] + SHIFT * weight(p.pos[0]), p.pos[2])
        moved += 1
        # a station now crowding the moved mouth goes (its neighbour takes the span)
        nb = r.points[end - 1] if end == -1 else r.points[1]
        q = net.points[nb]
        if math.hypot(q.pos[0] - p.pos[0], q.pos[1] - p.pos[1]) < CROWD and len(r.points) > 2:
            nxt = r.points[end - 2] if end == -1 else r.points[2]
            net.unlink(u, nb)
            net.unlink(nb, nxt)
            net.remove_point(nb)
            net.link(u, nxt)
            print("island_rinkai_south: %s: removed a station crowding its moved mouth" % name)
    pm.save_network(net, path)
    print("island_rinkai_south: %d station(s) moved south (up to %.0f m) -> %s" % (moved, -SHIFT, path))


if __name__ == "__main__":
    main(sys.argv[1:])
