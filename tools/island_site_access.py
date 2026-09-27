#!/usr/bin/env python3
"""island_site_access.py -- every site gets a road to its door (PLAN.md 3.23 / tier B8).

    python3 tools/island_site_access.py <record> [--check]

`island_sites.py` sites each landmark by a search that asks for CLEAR ground, so the buildings stand and nothing led to
them: traffic could not reach them and the GPS could not route to them. This step (run by `island_layout.py` after
the streets, before the turnarounds) lays each site's ACCESS: a `block`-preset street (2 lanes, footways -- an access
road is not a through route, and an arterial would invite traffic the site does not want) from a junction on the
network to the site's visitor car park, where it ENDS. The car park itself is placed by `island_sites.py`
(`access_parking`) at that end, derived from this road every run.

An access road is a DEAD END by design -- a 観光駐車場 is entered and left the same way, and cars turn in the lot -- so
it is declared here (`ACCESS`) and the two places that would otherwise object read `access_roads()`:
`island_turnarounds.py` does not put a loop on it, and `island_layout.py`'s open-end assert exempts its lanes.

Access roads (one row each, record frame):
  * `todai_michi` -- the LIGHTHOUSE on the north-east headland, and `michinoeki_michi` -- the 道の駅 on the north
    coast road (2026-09-26): each leaves its road through a T cut in it (`_junction_of`), no junction being there.
  * `jokamachi_sando` -- SHURI CASTLE (user, 2026-09-22: "ensure a routing to castle"). The castle-town street
    `jokamachi_dori` the plan drew from the castle south to nishi_dori (`island_plan`) was trimmed back to its last
    crossing by `island_network` (a stub past the last junction is trimmed), so nothing reached the castle. The 参道
    (approach) leaves the nishi_dori x jokamachi_dori junction to the NORTH, making it a crossroads, and climbs to the
    visitor car park below the castle's south wall; the castle is walked up to, never driven into. The flat strip
    between nishi_dori and the wall is ~130 m deep, too small for a turnaround square (90 m, 30 m clear, flat within
    3 m), which is why the car park, not a loop, is the end.

Idempotent: an access road already in the record is left alone. `--check` exits 1 if an access is missing.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

MOUTH = 26.0                    # a new mouth this far from its junction's centre (island_trunk_grid.MOUTH)
SPACING = 40.0                  # stations along an access road
PARKING_GAP = 4.0               # the car park's entrance edge this far past the road's end

#: name, site id, the road whose junction it leaves (its station nearest `at`), the end (the car-park entrance, record
#: x, y), the ParkingLot composite placed there, the site's own clear distance it must keep (m, from the site centre)
ACCESS = [
    dict(name="jokamachi_sando", site="shuri_castle", from_road="jokamachi_dori", at=(-610.0, -245.0),
         # ends at CASTLE TOWN station's SOUTH forecourt (rail r0, 2026-09-26: the station stands at (-560, -160), right
         # below the castle, and the rail never crosses the approach); the castle is a walk up from the north exit
         end=(-606.0, -192.0), parking="ParkingLot14"),
    # the LIGHTHOUSE (灯台) on the north-east headland (PLAN.md 3.30 L3, user 2026-09-26): a lane off the coast ring
    # to a small car park short of the tip; the tower itself is a later model on the reserved site (island_plan)
    dict(name="todai_michi", site="lighthouse", from_road="ring_kita", at=(1250.0, 1297.0),
         end=(1360.0, 1292.0), parking="ParkingLot4"),
    # the 道の駅 (roadside station) on the north coast road beside the farm: its car park IS the station's core, and
    # it is entered off the coast road itself (the building is a later model on the reserved site)
    dict(name="michinoeki_michi", site="michi_no_eki", from_road="kaigan_machi", at=(442.0, 1757.0),
         end=(430.0, 1690.0), parking="ParkingLot14"),
    # THE PORT (PLAN.md 3.30 L3, 2026-09-26): the platform's interior streets meet no road at their south end (a quay),
    # so the planner cannot make them; these two dead ends leave the port road kichi_dori__2 (a U along the platform's
    # north strip). The MILITARY BASE's gate road enters on the base's north edge; the LOGISTICS road serves the
    # truck yards between the base and the container terminal.
    dict(name="kichi_mon_michi", site="military_base", from_road="kichi_dori", at=(-460.0, -1229.0),
         end=(-460.0, -1440.0), parking="ParkingLot14"),
    dict(name="butsuryu_michi", site="logistics_yard", from_road="kichi_dori", at=(-280.0, -1230.0),
         end=(-280.0, -1470.0), parking="ParkingLot14"),
]


LOT_LIFT = 0.05                 # the car park stands this far over the highest ground under it (ground never pokes up)


def parking_size(name):
    """(width, depth) of a ParkingLot composite, from building_types.json (depth is along its +Z, the entrance)."""
    import json
    doc = json.load(open(os.path.join(rg.ROOT, "assets/world_source/buildings/building_types.json")))
    return tuple({t["id"]: t for t in doc["composites"]}[name]["footprint_m"])


def lot_frame(end, u, a):
    """The car park at the road end `end` (x, y) heading `u` (unit, record frame): (centre (x, y), width, depth)."""
    w, d = parking_size(a["parking"])
    return (end[0] + u[0] * (PARKING_GAP + d / 2), end[1] + u[1] * (PARKING_GAP + d / 2)), w, d


def lot_top(ground, centre, u, w, d):
    """The height the car park stands at: the highest ground under its footprint (+ PARKING_GAP's apron in front of
    it), plus LOT_LIFT. The block-ground stage fills the terrain up to it (`island_ground`, as it does a lot)."""
    rx, ry = -u[1], u[0]
    hi = None
    for i in range(-4, 5):
        for j in range(-5, 5):
            x = centre[0] + rx * w / 2 * i / 4 + u[0] * (d / 2 + PARKING_GAP) * j / 4
            y = centre[1] + ry * w / 2 * i / 4 + u[1] * (d / 2 + PARKING_GAP) * j / 4
            z = ground.z(x, y) or 0.0
            hi = z if hi is None else max(hi, z)
    return hi + LOT_LIFT


def access_roads():
    """The names of every declared access road (read by island_turnarounds and island_layout)."""
    return {a["name"] for a in ACCESS}


def _junction_of(net, road_name, at):
    """The junction the access leaves from: the clique of the station nearest `at` on a road named `road_name` (or
    split from it: `road_name__...`) when that station is a junction mouth, else a T CUT into that road there
    (`cut_road`, the street planner's own way of making one) -- a lighthouse lane leaves the coast ring mid-stretch."""
    cands = [(n, q) for n, r in net.roads.items() if n == road_name or n.startswith(road_name + "__")
             for q in r.points]
    if not cands:
        raise SystemExit("island_site_access: no road %s" % road_name)
    name, u = min(cands, key=lambda c: math.hypot(net.points[c[1]].pos[0] - at[0], net.points[c[1]].pos[1] - at[1]))
    js = [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION]
    if js:
        return [u] + js
    a, b = cut_road(net, at, name, MOUTH)
    return [a, b]


def add(net, a, ground):
    members = _junction_of(net, a["from_road"], a["at"])
    cx = sum(net.points[u].pos[0] for u in members) / len(members)
    cy = sum(net.points[u].pos[1] for u in members) / len(members)
    ex, ey = a["end"]
    dx, dy = ex - cx, ey - cy
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    head = (cx + ux * MOUTH, cy + uy * MOUTH)
    run = L - MOUTH
    n = max(1, int(round(run / SPACING)))
    pts = [(head[0] + ux * run * k / n, head[1] + uy * run * k / n) for k in range(n + 1)]
    # the road CLIMBS to the car park's level rather than draping: the lot is flat and stands at the highest ground
    # under it, so the road's end must arrive at that height (the stamp builds the embankment under it)
    centre, w, d = lot_frame(pts[-1], (ux, uy), a)
    top = lot_top(ground, centre, (ux, uy), w, d)
    z0 = max(0.0, ground.z(*pts[0]) or 0.0)
    pts3 = [(x, y, z0 + (top - z0) * k / n) for k, (x, y) in enumerate(pts)]
    road = chain_road(net, a["name"], pts3, preset="block")
    make_junction(net, members + [road.points[0]])
    for u in road.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True
    return road, members


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    missing = [a for a in ACCESS if a["name"] not in net.roads]
    if "--check" in argv:
        print("island_site_access: %d of %d access roads present" % (len(ACCESS) - len(missing), len(ACCESS)))
        return 1 if missing else 0
    if not missing:
        print("island_site_access: every access road already present")
        return 0
    ground = rg.Ground()
    for a in missing:
        road, members = add(net, a, ground)
        p0, p1 = net.points[road.points[0]].pos, net.points[road.points[-1]].pos
        print("island_site_access: %s -> %s: %d stations from (%.0f, %.0f) to (%.0f, %.0f), a %d-arm junction"
              % (a["name"], a["site"], len(road.points), p0[0], p0[1], p1[0], p1[1], len(members) + 1))
    pm.save_network(net, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
