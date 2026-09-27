#!/usr/bin/env python3
"""island_fix_0914.py -- ONE-SHOT edit of the arterials INPUT (user, 2026-09-26, postal 9-14).

    python3 tools/island_fix_0914.py [<arterials record>]      # refuses to run twice

`jokamachi_dori` (the castle approach, drawn by island_plan from the castle south PAST rinkai_dori) was trimmed back
to its last junction with its end station 6.4 m past rinkai_dori's centreline -- on the FAR side of the road it Ts
into. Its cap, kerb and footway then stood in the middle of rinkai_dori's carriageway ("the sidewalk pokes into the
middle of the road"), and the setback solve, which slides a mouth along its own road, cannot bring back a mouth that
has crossed over. The end station moves to the NEAR side (MOUTH m north of the centreline); `island_layout`'s
setback then places it.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

INPUT = os.path.join(rg.PIECES, "IslandRoads.arterials.roads.json")
ROAD = "jokamachi_dori"
MOUTH = 22.0


def main(argv):
    path = argv[0] if argv else INPUT
    net = pm.load_network(path)
    road_of = {u: n for n, r in net.roads.items() for u in r.points}
    r = net.roads[ROAD]
    for end in (r.points[0], r.points[-1]):
        p = net.points[end]
        others = [net.points[l.target] for l in p.links if l.type == pm.LINK_JUNCTION
                  and road_of.get(l.target, "").startswith("rinkai_dori")]
        if len(others) != 2:
            continue
        a, b = others
        dx, dy = b.pos[0] - a.pos[0], b.pos[1] - a.pos[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        k = r.points.index(end)
        far = net.points[r.points[-1] if k == 0 else r.points[0]]      # the road's OTHER end: the near side
        side = (far.pos[0] - a.pos[0]) * nx + (far.pos[1] - a.pos[1]) * ny
        here = (p.pos[0] - a.pos[0]) * nx + (p.pos[1] - a.pos[1]) * ny
        if here * side > 0 and abs(here) >= MOUTH - 0.5:
            raise SystemExit("island_fix_0914: already applied to %s" % path)
        # interior stations past the crossing go (the road overshot it); the end keeps its links
        for u in list(r.points):
            if u in (r.points[0], r.points[-1]):
                continue
            q = net.points[u]
            if ((q.pos[0] - a.pos[0]) * nx + (q.pos[1] - a.pos[1]) * ny) * side < MOUTH:
                i = r.points.index(u)
                nb = [r.points[i - 1], r.points[i + 1]]
                net.remove_point(u)
                if u in r.points:
                    r.points.remove(u)
                net.link(nb[0], nb[1])
        # project onto the crossing line, then MOUTH out on the stem's side
        t = ((p.pos[0] - a.pos[0]) * dx + (p.pos[1] - a.pos[1]) * dy) / (L * L)
        cx, cy = a.pos[0] + dx * t, a.pos[1] + dy * t
        s = math.copysign(1.0, side)
        p.pos = (round(cx + s * nx * MOUTH, 3), round(cy + s * ny * MOUTH, 3), p.pos[2])
        pm.save_network(net, path)
        print("island_fix_0914: %s end moved from %.1f m on the far side to %.0f m on the near side of rinkai_dori"
              % (ROAD, abs(here), MOUTH))
        return 0
    raise SystemExit("island_fix_0914: no rinkai_dori T at either end of %s" % ROAD)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
