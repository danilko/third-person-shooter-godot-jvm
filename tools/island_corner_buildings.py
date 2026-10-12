#!/usr/bin/env python3
"""island_corner_buildings.py -- after tools/island_fillet_corners.py: move back (or take out) the buildings a
rounded corner now reaches (user, 2026-10-12: "if kerbs under building means squash/reduce building, it is possible").

    python3 tools/island_corner_buildings.py <x,z> [<x,z> ...] [--only key,key] [--write] [--grow 2.5]

--only names the buildings to treat (the ones a corner NEWLY reaches: compare the dry run with one on the record
before the fillet -- a street whose footway is narrower than --grow lists its whole frontage otherwise).

For every derived building within 90 m of one of the given corners (Godot x, z) whose footprint lies inside a road
band grown by --grow (the footway and a little), the building is slid straight away from that band, 0.5 m at a time
up to 8 m, to the first place where it is clear of every band and 1 m clear of every other building; one that finds
no such place is removed. A civic compound (`civic|...`) is reported and left: its footprint is its whole site.
Then: `island_buildings.py lots`, `island_buildings.py write`.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv, sys.argv = sys.argv, ["island_buildings.py"]
import island_buildings as ib          # noqa: E402
sys.argv = _argv
from shapely.geometry import Polygon   # noqa: E402
from shapely.strtree import STRtree    # noqa: E402
import point_edges as ped              # noqa: E402


def main(argv):
    skip = {i + 1 for i, a in enumerate(argv) if a in ("--grow", "--only")}
    corners = [tuple(float(v) for v in a.split(",")) for i, a in enumerate(argv) if not a.startswith("--") and i not in skip]
    grow = float(next((argv[i + 1] for i, a in enumerate(argv) if a == "--grow"), 2.5))
    net = ib.pm.load_network(ib.RECORD)
    quads = []
    for line, _h, _owner in ped.band_corridors(ped.solve_all(net, None)[3], owners=True):
        pts = [(x, -y, half + grow) for (x, y, _z, half) in line]
        for (x0, z0, h0), (x1, z1, h1) in zip(pts, pts[1:]):
            if not any(math.hypot(x0 - cx, z0 - cz) < 120 for cx, cz in corners):
                continue
            dx, dz = x1 - x0, z1 - z0
            L = math.hypot(dx, dz)
            if L < 1e-6:
                continue
            nx, nz = -dz / L, dx / L
            quads.append(Polygon([(x0 + nx * h0, z0 + nz * h0), (x1 + nx * h1, z1 + nz * h1),
                                  (x1 - nx * h1, z1 - nz * h1), (x0 - nx * h0, z0 - nz * h0)]))
    tree = STRtree(quads)
    doc = json.load(open(ib.OUT))
    near = [b for b in doc["buildings"] if any(math.hypot(b["pos"][0] - x, b["pos"][2] - z) < 90 for x, z in corners)]

    def fp(b, dx=0.0, dz=0.0):
        return ib._footprint(b["type"], b["pos"][0] + dx, b["pos"][2] + dz, b["yaw"])

    def on_road(poly):
        return max([poly.intersection(quads[i]).area for i in tree.query(poly)] + [0.0])
    only = next((argv[i + 1].split(",") for i, a in enumerate(argv) if a == "--only"), None)
    moved = removed = 0
    for b in near:
        if only is not None and b["key"] not in only:
            continue
        worst = on_road(fp(b))
        if worst <= 0.5:
            continue
        if b["key"].startswith("civic|"):
            print("LEFT    %-16s %-34s %.1f m2 inside the road + %.1f m (a compound's site, not a wall)" % (
                b["type"], b["key"], worst, grow))
            continue
        here = fp(b)
        hit = max((quads[i] for i in tree.query(here)), key=lambda q: here.intersection(q).area)
        c = here.intersection(hit).centroid
        ax, az = b["pos"][0] - c.x, b["pos"][2] - c.y
        al = math.hypot(ax, az) or 1.0
        others = [fp(o).buffer(1.0) for o in near if o is not b]
        done = False
        for k in range(1, 17):
            dx, dz = ax / al * 0.5 * k, az / al * 0.5 * k
            cand = fp(b, dx, dz)
            if on_road(cand) <= 0.05 and not any(cand.intersects(o) for o in others):
                print("MOVED   %-16s %-34s %.1f m away from the corner (was %.1f m2 inside)" % (
                    b["type"], b["key"], 0.5 * k, worst))
                b["pos"] = [round(b["pos"][0] + dx, 3), b["pos"][1], round(b["pos"][2] + dz, 3)]
                moved += 1
                done = True
                break
        if not done:
            print("REMOVED %-16s %-34s no clear place within 8 m (was %.1f m2 inside)" % (b["type"], b["key"], worst))
            doc["buildings"] = [o for o in doc["buildings"] if o is not b]
            removed += 1
    print("%d moved, %d removed%s" % (moved, removed, "" if "--write" in argv else " (dry run)"))
    if "--write" in argv and (moved or removed):
        with open(ib.OUT, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
