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
  * `ekimae_<station>` -- each HUB station's street (`station_access()`, from the rail reserve; `island_rail_layout
    .HUB_ACCESS` owns them, 2026-09-29).
  * `ekimae_farm` -- FARM STATION's street across the Main line (2026-09-28): the station's ramps meet it, its car
    park fronts it; no lot at its end.
  * `jokamachi_sando` -- SHURI CASTLE (user, 2026-09-22: "ensure a routing to castle"). The castle-town street
    `jokamachi_dori` the plan drew from the castle south to nishi_dori (`island_plan`) was trimmed back to its last
    crossing by `island_network` (a stub past the last junction is trimmed), so nothing reached the castle. The 参道
    (approach) leaves the nishi_dori x jokamachi_dori junction to the NORTH, making it a crossroads, crosses the Blue
    line level beside Castle Town station and ends below the castle's south wall; the castle is walked up to, never
    driven into, and its visitors park at the station's lot (2026-09-29: its own lot stood 2.6 m above the 踏切). The flat strip
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
         # STRAIGHT NORTH from the nishi_dori x jokamachi_dori junction and OVER the Blue line (a 踏切 beside Castle
         # Town station, 2026-09-28): the station's two entrance ramps come down to it on either side of the track
         # (island_rail_layout STATION_FRONT), and it ends north of the track at the castle's car park below the
         # castle's south wall -- the castle is a walk up from there. It used to end south of the track 40 m from the
         # station, the station standing in open ground with no way in (user, 2026-09-28).
         # (2026-09-29) it ENDS 10 m past the track with NO car park of its own: the castle's lot stood against the
         # castle wall 2.6 m above the 踏切 with 20 m between them -- a climb no road makes and a crossing the Blue line
         # stood 1.5 m under (probe_rail_track). Drivers park at Castle Town station's lot, which opens onto this
         # street just south of the track, and walk up; the street follows the ground, so it crosses LEVEL.
         end=(-608.4, -150.0), parking=None),
    # FARM STATION'S STREET (駅前通り, 2026-09-28): the farm row hata_yoko_1220 continued east from its nodo_waku
    # junction, over the Main line (a 踏切 beside the station's end buildings, whose ramps come down to it), ending
    # just past the track; the station's car park stands on it (island_rail_layout STATION_FRONT)
    dict(name="ekimae_farm", site="station_farm", from_road="nodo_waku", at=(1045.0, 1220.0),
         end=(1136.0, 1220.0), parking=None),
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
    # the AIRPORT'S SERVICE ROAD (user, 2026-09-29: the airside is fenced all round; "a vehicle service gate on the
    # landside for the hangar, off a service road -- it needs one"): a T off the forecourt loop's south leg, west of
    # the terminal, south to the locked gate in the airside fence (site_airport_fence.py GATE_GX)
    dict(name="kuko_service", site="airport_airfield", from_road="kuko_rotary", at=(1130.0, -1710.0),
         end=(1130.0, -1777.0), parking=None),
    dict(name="butsuryu_michi", site="logistics_yard", from_road="kichi_dori", at=(-280.0, -1230.0),
         end=(-280.0, -1440.0), parking="ParkingLot14"),     # its car park short of the runway band (z 1480)
]


REUSE_M = 15.0                  # a junction whose centre is this close to `at` is joined, not cut beside
VIA_R = 15.0                    # a corner of an access street with `via` points (a block street's kerb return)


def _resample(poly, step):
    """Stations along a polyline every <= `step` m, keeping its first and last point."""
    cum = [0.0]
    for p, q in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    n = max(1, int(math.ceil(cum[-1] / step)))
    out = []
    for k in range(n + 1):
        t = cum[-1] * k / n
        j = max(i for i in range(len(cum) - 1) if cum[i] <= t) if t < cum[-1] else len(cum) - 2
        f = (t - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


LOT_LIFT = 0.05                 # the car park stands this far over the highest ground under it (ground never pokes up)


def parking_size(name):
    """(width, depth) of a ParkingLot composite, from building_types.json (depth is along its +Z, the entrance)."""
    import json
    doc = json.load(open(os.path.join(rg.ROOT, "assets/world_source/buildings/building_types.json")))
    return tuple({t["id"]: t for t in doc["composites"]}[name]["footprint_m"])


LX_HOLD = 12.0                  # m past a 踏切 an access road stays on the ground (the rail record's CROSS_HOLD)


def rail_crossings(pts):
    """[(arc length along `pts`, rail head z)] where the polyline crosses an AT-GRADE rail line (the reserve's corridor
    samples whose rail head stands within 1 m of the ground)."""
    import json
    path = os.path.join(rg.ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")
    if not os.path.exists(path):
        return []
    out = []
    cum = [0.0]
    for p_, q_ in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(q_[0] - p_[0], q_[1] - p_[1]))
    for c in json.load(open(path))["corridors"]:
        q = c["pts"]
        for r0, r1 in zip(q, q[1:]):
            if abs(r0[2] - r0[3]) >= 1.0 or abs(r1[2] - r1[3]) >= 1.0:
                continue
            for i in range(len(pts) - 1):
                a0, a1 = pts[i], pts[i + 1]
                ex, ey = a1[0] - a0[0], a1[1] - a0[1]
                fx, fy = r1[0] - r0[0], r1[1] - r0[1]
                den = ex * fy - ey * fx
                if abs(den) < 1e-9:
                    continue
                t = ((r0[0] - a0[0]) * fy - (r0[1] - a0[1]) * fx) / den
                u = ((r0[0] - a0[0]) * ey - (r0[1] - a0[1]) * ex) / den
                if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                    out.append((cum[i] + t * (cum[i + 1] - cum[i]), r0[2] + (r1[2] - r0[2]) * u))
    return sorted(out)


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


def station_access():
    """THE HUB STATIONS' STREETS (2026-09-29): one row per station box in the rail reserve that carries "access"
    (`island_rail_layout.HUB_ACCESS`, which owns them -- its end is the foot of the station's entrance, so it moves with
    the station). No car park at the end: the reserve places the station's car park beside the street."""
    import json
    path = os.path.join(rg.ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")
    if not os.path.exists(path):
        return []
    out = []
    for b in json.load(open(path))["boxes"]:
        acc = b.get("access")
        if not acc or not b["id"].startswith("station:"):
            continue
        slug = b["id"].split(":", 1)[1].lower().replace(" ", "_")
        out.append(dict(name="ekimae_" + slug, site="station_" + slug, from_road=acc["from_road"],
                        at=tuple(acc["at"]), via=[tuple(v) for v in acc.get("via", [])], end=tuple(acc["end"]),
                        parking=None))
    return out


def all_access():
    return ACCESS + station_access()


def access_roads():
    """The names of every declared access road (read by island_turnarounds and island_layout)."""
    return {a["name"] for a in all_access()}


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
        # a JUNCTION is joined only when `at` names it (its centre within REUSE_M): a street authored off a road's
        # mid-stretch whose nearest station happens to be a mouth 27 m away (Bay's, 2026-09-29) cuts its own T instead
        # of becoming a fifth, skewed arm of that crossing
        cx = sum(net.points[q].pos[0] for q in [u] + js) / (len(js) + 1)
        cy = sum(net.points[q].pos[1] for q in [u] + js) / (len(js) + 1)
        if math.hypot(cx - at[0], cy - at[1]) <= REUSE_M:
            return [u] + js
    a, b = cut_road(net, at, name, MOUTH)
    return [a, b]


def add(net, a, ground):
    members = _junction_of(net, a["from_road"], a["at"])
    cx = sum(net.points[u].pos[0] for u in members) / len(members)
    cy = sum(net.points[u].pos[1] for u in members) / len(members)
    via = list(a.get("via", ()))
    first = via[0] if via else a["end"]
    dx, dy = first[0] - cx, first[1] - cy
    L = math.hypot(dx, dy)
    head = (cx + dx / L * MOUTH, cy + dy / L * MOUTH)
    ex, ey = a["end"]
    if via:
        # a street with corners (a hub station's, `station_access`): rounded, resampled like an authored street
        plan = rg.rounded_polygon([head] + via + [a["end"]], VIA_R, closed=False)
        pts = _resample(rg.densify(plan, 4.0), SPACING)
        n = len(pts) - 1
        q = pts[-2]
        L = math.hypot(ex - q[0], ey - q[1]) or 1.0
        ux, uy = (ex - q[0]) / L, (ey - q[1]) / L
    else:
        ux, uy = dx / L, dy / L
        run = L - MOUTH
        n = max(1, int(round(run / SPACING)))
        pts = [(head[0] + ux * run * k / n, head[1] + uy * run * k / n) for k in range(n + 1)]
    # the road CLIMBS to the car park's level rather than draping: the lot is flat and stands at the highest ground
    # under it, so the road's end must arrive at that height (the stamp builds the embankment under it)
    _poly = list(pts)
    z0 = max(0.0, ground.z(*pts[0]) or 0.0)
    xs = rail_crossings(pts)
    if a.get("parking") and xs:
        # ...but a road that crosses an at-grade track on the way crosses it LEVEL (a 踏切 is the road's surface at the
        # rail's height): it follows the ground to LX_HOLD past the last crossing, the crossing itself at the rail
        # head, and climbs to the lot only after that. Climbing straight across put the castle approach 1.5 m over
        # the Blue line (2026-09-29, probe_rail_track's gauge: the road and terrain stood in the train's way)
        centre, w, d = lot_frame(pts[-1], (ux, uy), a)
        top = lot_top(ground, centre, (ux, uy), w, d)
        cum = [0.0]
        for p_, q_ in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(q_[0] - p_[0], q_[1] - p_[1]))
        hold = max(sc for sc, _z in xs) + LX_HOLD
        want = sorted(set([round(c, 3) for c in cum] + [round(sc, 3) for sc, _z in xs]
                          + [round(min(hold, cum[-1] - 1.0), 3)]))
        pts, zs = [], []
        zh = None
        for sv in want:
            j = max(i for i in range(len(cum) - 1) if cum[i] <= sv) if sv < cum[-1] else len(cum) - 2
            f = (sv - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
            x_ = _poly[j][0] + (_poly[j + 1][0] - _poly[j][0]) * f
            y_ = _poly[j][1] + (_poly[j + 1][1] - _poly[j][1]) * f
            pts.append((x_, y_))
            rz = next((z_ for sc, z_ in xs if abs(sc - sv) < 0.01), None)
            zs.append(rz if rz is not None else max(0.0, ground.z(x_, y_) or 0.0))
        k_h = max(i for i, sv in enumerate(want) if sv <= hold + 1e-6)
        zh = zs[k_h]
        L2 = want[-1] - want[k_h]
        pts3 = [(x_, y_, zs[i] if i <= k_h else zh + (top - zh) * (want[i] - want[k_h]) / max(1e-9, L2))
                for i, (x_, y_) in enumerate(pts)]
    elif a.get("parking"):
        centre, w, d = lot_frame(pts[-1], (ux, uy), a)
        top = lot_top(ground, centre, (ux, uy), w, d)
        pts3 = [(x, y, z0 + (top - z0) * k / n) for k, (x, y) in enumerate(pts)]
    else:
        # no car park at the end: the road drapes (a station's street crosses its track level with it)
        pts3 = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
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
    rows = all_access()
    missing = [a for a in rows if a["name"] not in net.roads]
    if "--check" in argv:
        print("island_site_access: %d of %d access roads present" % (len(rows) - len(missing), len(rows)))
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
