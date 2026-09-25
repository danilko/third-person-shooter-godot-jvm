#!/usr/bin/env python3
"""island_sites.py -- place the island's composite sites and landmarks in World.tscn, from MEASURED facts
(PLAN.md 3.8 steps 5 and 8).

    python3 tools/island_sites.py [--check]      # place the FROZEN sites (IslandSites.json) in World.tscn
    python3 tools/island_sites.py --resite       # search every site again, write IslandSites.json, then place

**Sites are frozen as data (PLAN.md R6 / 3.30 L0.4).** Each search below runs only with `--resite`, and its answer
-- a record-frame (x, y) and a yaw -- is written to `assets/world_source/buildings/IslandSites.json`, reviewed like the
road record. An ordinary run places the frozen sites, re-sampling only the GROUND height under each (a terrain edit
must not float a site), so a new access road -- which every search's road-clearance rule would read as an obstacle --
can never move the site it was built for. `--resite=<id>[,<id>]` searches only those.

Nothing is typed in as a coordinate; each placement is derived, like `island_rainbow_bridge.py`'s:

* `ContainerTerminal` (`tools/building_kit/site_container_terminal.py`) -- its FRONT (+Z, the quay line with the
  cranes' seaside rails on it) is laid on the industrial harbour's east quay: the edge where the natural ground
  (`IslandRoads.ground.bin`) drops from the 4 m reclaimed land to the dredged water is sampled every 10 m over
  `QUAY_SPAN`, a line is least-squares fitted through it, and the site stands on the land side of that line, centred
  on the span, at the land's height.
* `ShuriCastle` (library_landmarks.shuri_castle) -- the hill-castle site the 3.8 note asks for: the ~140 m patch at
  the massif's foot whose ground stays within 2-60 m and within `CASTLE_RELIEF` of itself, has no road within
  `CASTLE_CLEAR`, and scores best on (mountain behind it to the north-west, near downtown); turned so its front (the
  Seiden's face) looks at downtown, standing on the patch's lowest ground (its platform takes up the slope).

Each site STREAMS: a `ZoneMarker` under `SiteZones` whose Zone places the building scene in world space
(`geometry_world_placed`, the island road pieces' mechanism), zone id `site_<name>`; the block is found by name and
replaced whole. The Road Kit dock leaves a site zone out of the road cut (`road_kit_zones.is_traffic_only`). `--check`
writes nothing and exits 1 if the scene would change. Building scenes: `tools/building_kit/build_buildings.sh`.
"""
import collections
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import Ground, densify, ROOT     # noqa: E402
import point_model as pm                             # noqa: E402

SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
FROZEN = os.path.join(ROOT, "assets/world_source/buildings/IslandSites.json")
BUILDINGS = "res://src/main/resources/com/openworld/world/buildings/"

QUAY_SPAN = (-1150.0, -1480.0)       # record y range of the terminal's quay (north end of the east quay)
QUAY_X_RANGE = (0.0, 400.0)          # where to look for the edge
TERMINAL_D = 218.4                   # site_container_terminal.D
DOWNTOWN = (600.0, 100.0)            # the trunk grid's centre: naka_hondori x ekimae_dori, moved with the plan (3.30)
CASTLE_HALF = 70.0
# UP AND LEFT, as far as the terrain allows (user, 2026-09-21). MEASURED first, because the search had exactly
# ONE valid site at the old relief, so re-scoring it could not move the castle at all. Sweeping the constraint:
#   relief 30 -> 1 site (today's, godot -580, 40) | 45 -> 8 sites, most up-left godot (-620, -40) on 7-49 m
#   60 -> 32 sites but the best is 49-101 m, and 80 -> 126 at 125-188 m, i.e. a 山城 ON the mountain, which 3.8
#   explicitly rejects ("the grounds need flat land, with the mountain behind as the backdrop").
# So 45 is the setting that moves it up-left and keeps it a 平山城; the platform is what absorbs the extra slope.
CASTLE_RELIEF = 45.0
# WHERE it stands and WHICH WAY it looks are two decisions, so they get two constants. The site is drawn
# toward this point (record frame, up and left of the old one); the front still turns to face DOWNTOWN.
# A plain up-left weight was tried first and could not win: the relief term (0.3 per metre) is ~5 units of
# score across the candidates and the weight was worth 0.5, so the flattest patch kept winning whatever the
# bias said. Scoring the distance to a stated target says the intent instead of tuning against another term.
CASTLE_TARGET = (-700.0, 200.0)
CASTLE_CLEAR = 85.0
TERMINAL_LOAD = 900.0                # streamed in within this of the site (unload + 300 m)
CASTLE_LOAD = 2000.0                 # a landmark on a hill is seen from across the city

# --- THE LANDMARKS THAT WERE BUILT AND NEVER PLACED (user, 2026-09-21: "for downtown, assume will combine to
# put some landmark such as tokyo tower ... bigger train station ... train/airport terminals seem missing").
# They were right: `TokyoTower`, `TokyoStation` and `AirportTerminal` have shipped as built scenes since 3.12c
# and nothing in World.tscn instanced any of them, which is that item's own open follow-up.
#
# Each is sited by the same measured search as the castle -- a patch flat enough, clear of roads, inside the
# region it belongs to -- with the one constraint that makes it that landmark:
#   * the tower stands in DOWNTOWN and wants nothing but flat ground and room (a 334 m tower is seen from
#     everywhere, so the score is simply how central it is);
#   * the station stands ALONG `ekimae_dori`, which is named 駅前通り -- "the street in front of the station" --
#     so the road the trunk grid already laid says where it goes and which way it faces;
#   * the terminal stands on the AIRPORT ISLAND (`island_coast.json`'s own box), on its flattest clear ground.
TOWER_HALF = 55.0                    # TokyoTower is 94.6 m across; leave room round its legs
TOWER_RELIEF = 3.0
TOWER_CLEAR = 70.0
TOWER_LOAD = 3000.0                  # 334 m: it is the skyline
STATION_L, STATION_D = 320.0, 29.8   # the station BUILDING scene (TokyoStation*), 320 x 29.8 m
STATION_ROAD = "ekimae_dori"         # 駅前通り: the street the station fronts
# The central station's RESERVE (PLAN.md B4 / 3.36, user 2026-09-25: "use Tokyo Station ... from PLATEAU for
# data/sizing; an artist rebuilds the models later"). Measured with tools/plateau2json/measure_stations.py on
# Chiyoda-ku 2025: the whole complex is ~430 m along the rail x ~250 m across it -- the Marunouchi building band
# 62 m (the building itself 58.7 x 316.7 m, 35.5 m tall) and the JR + Shinkansen platform canopies 21-33 m wide x
# 420-433 m long over ~200 m. This world compresses it to the building's own length and ONE block's depth:
# forecourt (the 駅前ロータリー, B8) + building + platform band. The reserve is what the roads, the block streets and
# the building placer keep clear of; the scene is only the building, standing at the reserve's front.
STATION_RESERVE_D = 130.0
STATION_FORECOURT = 30.0             # reserve front edge -> the building's front face (the rotary's room)
STATION_FRONT_GAP = 4.0              # the station road's own paved edge -> the reserve's front edge
STATION_ROAD_HALF = 18.5             # a trunk road's half width (point_presets "trunk": 3 x 4.5 + 1 + 4)
STATION_ROAD_CLEAR = 2.0             # no road's PAVED EDGE (block streets aside) within this of the reserve
STATION_LOAD = 1200.0
TERMINAL_HALF = (121.0, 85.0)        # AirportTerminal is 242 x 170
TERMINAL_RELIEF = 4.0
TERMINAL_CLEAR = 40.0
AIRPORT_BOX = (700.0, 1500.0, 1300.0, 2304.0)    # island_coast.json `airport_island`, GODOT (x0, x1, z0, z1); the island
                                                 # ends at x 1500 since the land redo (island_reshape.AIRPORT_END_X)
AIRPORT_LOAD = 1500.0
# the region boxes the placement uses, so a landmark cannot be sited outside the district it belongs to
REGION_BOX = {"downtown": (25.0, -110.0, 1175.0, 570.0)}   # inside C1 (island_plan.C1_CORNERS)


def quay_line(g):
    """(point on the line, unit direction along the quay (south), unit normal to the SEA) from the ground edge."""
    pts = []
    y = QUAY_SPAN[0]
    while y >= QUAY_SPAN[1]:
        last = None
        x = QUAY_X_RANGE[0]
        while x <= QUAY_X_RANGE[1]:
            z = g.z(x, y)
            if z is not None and z < 0.0 and last is not None and last > 1.0:
                pts.append((x - 1.0, y))
                break
            last = z
            x += 2.0
        y -= 10.0
    n = len(pts)
    my = sum(p[1] for p in pts) / n
    mx = sum(p[0] for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    k = sxy / syy                                  # x = mx + k (y - my)
    u = (k, 1.0)
    L = math.hypot(*u)
    u = (-u[0] / L, -u[1] / L)                     # southward along the quay
    sea = (-u[1], u[0]) if (-u[1]) > 0 else (u[1], -u[0])   # the normal pointing east (+x), to the water
    resid = max(abs(p[0] - (mx + k * (p[1] - my))) for p in pts)
    return (mx, my), u, sea, n, resid


def castle_site(g, net):
    road = []
    for r in net.roads.values():
        road += densify([net.points[v].pos[:2] for v in r.points], 10.0)
    grid = collections.defaultdict(list)
    for x, y in road:
        grid[(int(x // 50), int(y // 50))].append((x, y))

    def near(x, y, R):
        for i in range(int((x - R) // 50), int((x + R) // 50) + 1):
            for j in range(int((y - R) // 50), int((y + R) // 50) + 1):
                if any(abs(p[0] - x) < R and abs(p[1] - y) < R for p in grid.get((i, j), ())):
                    return True
        return False
    best = None
    H = CASTLE_HALF
    for cx in range(-1500, 600, 20):
        for cy in range(-500, 1500, 20):
            zs = [g.z(cx + dx, cy + dy) for dx in range(-int(H), int(H) + 1, 20) for dy in range(-int(H), int(H) + 1, 20)]
            if any(z is None for z in zs):
                continue
            lo, hi = min(zs), max(zs)
            if lo < 2.0 or hi > 60.0 or hi - lo > CASTLE_RELIEF or near(cx, cy, CASTLE_CLEAR):
                continue
            back = g.z(cx - 250, cy + 250) or 0.0
            score = (math.hypot(cx - CASTLE_TARGET[0], cy - CASTLE_TARGET[1]) * 0.02
                     - back * 0.02 + (hi - lo) * 0.3)
            if best is None or score < best[0]:
                best = (score, cx, cy, lo, hi, back)
    return best


def road_half(r):
    """A road's paved half width from its BASE section (lanes, median, footway) -- the widest side."""
    b = r.base
    lanes = max(b.lanes_fwd, b.lanes_bwd) * b.lane_width
    return lanes + b.median_width / 2.0 + max(b.left_walk_width, b.right_walk_width)


def road_index(net, step=10.0, cell=50.0, skip=None, widths=False):
    """Every road centreline point, bucketed, so "is there a road within R" is a few array reads. `skip(name)` leaves
    a road out. With `widths`, `near(x, y, R)` asks for a road's PAVED EDGE within R (its own half width added)."""
    grid = collections.defaultdict(list)
    for name, r in net.roads.items():
        if skip is not None and skip(str(name)):
            continue
        h = road_half(r) if widths else 0.0
        for x, y in densify([net.points[v].pos[:2] for v in r.points], step):
            grid[(int(x // cell), int(y // cell))].append((x, y, h))
    pad = 25.0 if widths else 0.0

    def near(x, y, R):
        for i in range(int((x - R - pad) // cell), int((x + R + pad) // cell) + 1):
            for j in range(int((y - R - pad) // cell), int((y + R + pad) // cell) + 1):
                if any(abs(p[0] - x) < R + p[2] and abs(p[1] - y) < R + p[2] for p in grid.get((i, j), ())):
                    return True
        return False
    return near


FOOTPRINT_CLEAR = 10.0               # no road within this of a flat site's own footprint


def flat_site(g, near, box, half, relief, clear, target, zmin=-0.3, zmax=30.0, step=20.0):
    """The flattest clear patch in a RECORD-frame box, scored by how near it is to `target`.

    `box` is (x0, y0, x1, y1) and `half` is (hx, hy) of the footprint. Returns (x, y, lo, hi) or None. Shared by
    every landmark below so each one differs only in the constraint that makes it that landmark, rather than in
    a search of its own.

    `zmin` is in the RECORD frame, where the city plain measures about 0.00 m -- the +0.6 m everything sits at
    in Godot is the network node's own Y. A 0.4 m floor (the Godot land line) rejects the whole city, which is
    what it did: every clearance from 70 m down to 20 m returned nothing, and the road clearance was never the
    constraint that failed."""
    hx, hy = half
    best = None
    x0, y0, x1, y1 = box
    xs = range(int(x0 + hx), int(x1 - hx) + 1, int(step))
    ys = range(int(y0 + hy), int(y1 - hy) + 1, int(step))
    for cx in xs:
        for cy in ys:
            zs = [g.z(cx + dx, cy + dy)
                  for dx in range(-int(hx), int(hx) + 1, int(step))
                  for dy in range(-int(hy), int(hy) + 1, int(step))]
            if any(z is None for z in zs):
                continue
            lo, hi = min(zs), max(zs)
            if lo < zmin or hi > zmax or hi - lo > relief:
                continue
            if near(cx, cy, clear):
                continue
            # ...and no road under the FOOTPRINT itself: the clearance above is from the centre, and a 242 x 170 m
            # terminal passed it standing over the airport spur (3.30 L3)
            if any(near(cx + dx, cy + dy, FOOTPRINT_CLEAR)
                   for dx in range(-int(hx), int(hx) + 1, int(step)) for dy in range(-int(hy), int(hy) + 1, int(step))):
                continue
            score = math.hypot(cx - target[0], cy - target[1]) + (hi - lo) * 40.0
            if best is None or score < best[0]:
                best = (score, cx, cy, lo, hi)
    return None if best is None else best[1:]


def is_block_street(name):
    """A generated block street (`island_streets.py`, named by `island_plan.STREET_NAMES`): it re-routes around a
    frozen site on the next layout run by itself, so a site search may stand over one."""
    import island_plan as _PL
    stems = {v for pair in _PL.STREET_NAMES.values() for v in pair}
    return any(name == st or name.startswith(st + "_") for st in stems)


def station_site(g, net, near=None):
    """The central station's RESERVE along `ekimae_dori`, as (reserve centre x, y, lowest ground, yaw).

    Derived from the road, not from a coordinate, because the road is named for the station (駅前通り) -- so if
    the trunk grid moves, the station moves with it. The reserve (STATION_L x STATION_RESERVE_D) stands beside the
    street, its front edge STATION_FRONT_GAP past the street's paved edge, and must be CLEAR of every road except a
    block street: the first version checked only that the street was straight and the land flat, and put the
    station across `naka_hondori`, blocking three of its lanes (PLAN.md 0.10(d) / B4)."""
    # THE STREET IS MANY ROADS, NOT ONE. `island_road_zones.py --split` cuts a long run at every 504 m zone
    # boundary (PLAN.md 3.10), so `ekimae_dori` is `ekimae_dori`, `__2`, `__x1`, ... Re-joining the pieces by name
    # prefix and walking them along the street's own principal axis is recovering the street.
    parts = [r for k, r in net.roads.items() if str(k) == STATION_ROAD or str(k).startswith(STATION_ROAD + "_")]
    if not parts:
        return None
    pts = []
    for r in parts:
        pts += densify([net.points[v].pos[:2] for v in r.points], 10.0)
    if len(pts) < 2:
        return None
    span_x = max(p[0] for p in pts) - min(p[0] for p in pts)
    span_y = max(p[1] for p in pts) - min(p[1] for p in pts)
    pts.sort(key=lambda p: p[0] if span_x >= span_y else p[1])
    # candidates every 5 m along the JOINED line, across the junction gaps between the pieces too: the one place a
    # 320 m reserve fits between two trunk roads can be where a cross street meets the station street (measured:
    # east of naka_hondori it is x 780-795, and ekimae_dori is broken at x 777-808 by machi_792's junction)
    fine = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L > 80.0:                       # not a junction gap: two unrelated stretches
            fine.append(b)
            continue
        n = max(1, int(L / 5.0))
        fine += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    pts = fine
    clear = road_index(net, widths=True,
                       skip=lambda n: is_block_street(n) or n == STATION_ROAD or n.startswith(STATION_ROAD + "_"))
    street = road_index(net, skip=lambda n: not (n == STATION_ROAD or n.startswith(STATION_ROAD + "_")))
    off = STATION_ROAD_HALF + STATION_FRONT_GAP + STATION_RESERVE_D / 2
    best = None
    for i in range(1, len(pts) - 1):
        (ax, ay), (bx, by) = pts[i - 1], pts[i + 1]
        ux, uy = bx - ax, by - ay
        L = math.hypot(ux, uy)
        if L < 1e-6:
            continue
        ux, uy = ux / L, uy / L
        mx, my = pts[i]
        for sgn in (1.0, -1.0):
            nx, ny = -uy * sgn, ux * sgn
            cx, cy = mx + nx * off, my + ny * off
            ok, zs = True, []
            for ti in range(17):
                for di in range(8):
                    t = -STATION_L / 2 + STATION_L * ti / 16.0
                    d = -STATION_RESERVE_D / 2 + STATION_RESERVE_D * di / 7.0
                    x, y = cx + ux * t + nx * d, cy + uy * t + ny * d
                    z = g.z(x, y)
                    if z is None or clear(x, y, STATION_ROAD_CLEAR):
                        ok = False
                        break
                    zs.append(z)
                if not ok:
                    break
            if not ok:
                continue
            # ...and the station street runs along the WHOLE front, not past one end of it
            if not all(street(mx + ux * t, my + uy * t, 15.0) for t in range(-int(STATION_L / 2), int(STATION_L / 2) + 1, 40)):
                continue
            lo, hi = min(zs), max(zs)
            if lo < -0.3 or hi - lo > 2.5:     # record frame: the city plain is ~0.00 m
                continue
            score = (hi - lo) * 100.0 + math.hypot(cx - DOWNTOWN[0], cy - DOWNTOWN[1]) * 0.01
            if best is None or score < best[0]:
                # the station's front (+Z) looks back at the road it is named for
                best = (score, cx, cy, lo, yaw_to(-nx, ny))
    return None if best is None else best[1:]


def scene_offset(row):
    """The record-frame (dx, dy) from a site's reserve centre to where its SCENE stands. A site whose reserve is its
    scene has none; the central station's building stands at the FRONT of its reserve."""
    f = row.get("scene_front", 0.0)
    if not f:
        return 0.0, 0.0
    a = math.radians(row["yaw"])
    fx, fy = math.sin(a), -math.cos(a)          # +Z of the scene, in the record frame
    return fx * f, fy * f


SITE_ID_BASE = 910015000
HOLDER = "SiteZones"
SUB_PREFIX = "Zone_site_"


def site_xf(pos, yaw_deg):
    """The Godot Transform3D literal for a scene at record-frame `pos` (x, y, height), its +Z turned to `yaw_deg`."""
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return "Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)" % (c, s, -s, c, pos[0], pos[2], -pos[1])


def yaw_to(dx_g, dz_g):
    """The yaw (deg about +Y) that turns +Z onto the Godot direction (dx, dz)."""
    return math.degrees(math.atan2(dx_g, dz_g))


def search(g, net, only=None):
    """Every site's search, as frozen-data rows: {id, scene, x, y, yaw, size, load, ground}. `ground` says how an
    ordinary run re-samples its height: "centre" (the terminal stands at its quay's land) or "min" (the lowest ground
    under the footprint -- a platform or plinth takes up the rest). `only` limits it to those ids."""
    rows = []

    def want(zid):
        return only is None or zid in only
    if want("container_terminal"):
        (qx, qy), u, sea, n, resid = quay_line(g)
        cy = (QUAY_SPAN[0] + QUAY_SPAN[1]) / 2
        cx = qx + (u[0] / u[1]) * (cy - qy) if abs(u[1]) > 1e-9 else qx
        centre = (cx - sea[0] * TERMINAL_D / 2, cy - sea[1] * TERMINAL_D / 2)
        print("island_sites: quay fitted through %d edge samples (worst %.1f m off the line); terminal at (%.1f, %.1f)"
              ", front facing (%.3f, %.3f)" % (n, resid, centre[0], centre[1], sea[0], sea[1]))
        rows.append(dict(id="container_terminal", scene="ContainerTerminal", x=centre[0], y=centre[1],
                         yaw=yaw_to(sea[0], -sea[1]), size=[364.0, 218.4], load=TERMINAL_LOAD, ground="centre"))
    if want("shuri_castle"):
        site = castle_site(g, net)
        if site is None:
            raise SystemExit("island_sites: no castle site passes (relief %.0f m, road clearance %.0f m)"
                             % (CASTLE_RELIEF, CASTLE_CLEAR))
        _s, kx, ky, lo, hi, back = site
        print("island_sites: castle at (%d, %d), ground %.1f-%.1f m under it, the mountain %.0f m behind"
              % (kx, ky, lo, hi, back))
        rows.append(dict(id="shuri_castle", scene="ShuriCastle", x=kx, y=ky,
                         yaw=yaw_to(DOWNTOWN[0] - kx, -(DOWNTOWN[1] - ky)), size=[158.0, 128.0], load=CASTLE_LOAD,
                         ground="patch"))
    near = road_index(net)
    if want("tokyo_tower"):
        tower = flat_site(g, near, REGION_BOX["downtown"], (TOWER_HALF, TOWER_HALF), TOWER_RELIEF, TOWER_CLEAR,
                          DOWNTOWN, zmax=12.0)
        if tower is None:
            print("island_sites: NO tower site in downtown (flat within %.0f m, %.0f m clear of every road)"
                  % (TOWER_RELIEF, TOWER_CLEAR))
        else:
            tx, ty, tlo, thi = tower
            print("island_sites: Tokyo Tower at (%d, %d), ground %.1f-%.1f m" % (tx, ty, tlo, thi))
            rows.append(dict(id="tokyo_tower", scene="TokyoTower", x=tx, y=ty, yaw=0.0, size=[94.6, 94.6],
                             load=TOWER_LOAD, ground="min"))
    if want("tokyo_station"):
        st = station_site(g, net)
        if st is None:
            print("island_sites: NO station site along %s (no %.0f x %.0f m reserve beside it, flat and clear of "
                  "every road but a block street)" % (STATION_ROAD, STATION_L, STATION_RESERVE_D))
        else:
            sx, sy, slo, s_yaw = st
            print("island_sites: Tokyo Station at (%d, %d), along %s (yaw %.0f)" % (sx, sy, STATION_ROAD, s_yaw))
            rows.append(dict(id="tokyo_station", scene="TokyoStation_Shop", x=sx, y=sy, yaw=s_yaw,
                             size=[STATION_L, STATION_RESERVE_D], load=STATION_LOAD, ground="min",
                             scene_front=STATION_RESERVE_D / 2 - STATION_FORECOURT - STATION_D / 2))
    if want("airport_terminal"):
        ax0, ax1, az0, az1 = AIRPORT_BOX                 # godot (x0, x1, z0, z1) -> record (x0, y0, x1, y1)
        apt = flat_site(g, near, (ax0, -az1, ax1, -az0), TERMINAL_HALF, TERMINAL_RELIEF, TERMINAL_CLEAR,
                        ((ax0 + ax1) / 2, -(az0 + az1) / 2), zmax=12.0, step=25.0)
        if apt is None:
            print("island_sites: NO terminal site on the airport island (flat within %.0f m, %.0f m clear)"
                  % (TERMINAL_RELIEF, TERMINAL_CLEAR))
        else:
            px, py, plo, phi = apt
            print("island_sites: Airport terminal at (%d, %d), ground %.1f-%.1f m" % (px, py, plo, phi))
            rows.append(dict(id="airport_terminal", scene="AirportTerminal_Shop", x=px, y=py, yaw=0.0,
                             size=[242.0, 170.0], load=AIRPORT_LOAD, ground="min"))
    return rows


def site_ground(g, row):
    """The height a frozen site stands at on TODAY's ground (record frame, network-relative)."""
    if row["ground"] == "centre":
        return g.z(row["x"], row["y"])
    if row["ground"] == "patch":           # castle_site's own measure: the axis-aligned patch, 20 m apart
        H = int(CASTLE_HALF)
        return min(g.z(row["x"] + dx, row["y"] + dy) for dx in range(-H, H + 1, 20) for dy in range(-H, H + 1, 20))
    a = math.radians(row["yaw"])
    # +Z of the scene is its front; in the record frame (x, y) a Godot direction (dx, dz) is (dx, -dz)
    fx, fy = math.sin(a), -math.cos(a)
    rx, ry = -fy, fx
    hw, hd = row["size"][0] / 2, row["size"][1] / 2
    lo = None
    for i in range(-4, 5):
        for j in range(-4, 5):
            p = (row["x"] + rx * hw * i / 4 + fx * hd * j / 4, row["y"] + ry * hw * i / 4 + fy * hd * j / 4)
            v = g.z(*p)
            lo = v if lo is None else min(lo, v)
    return lo


def load_frozen():
    import json
    if not os.path.exists(FROZEN):
        return []
    return json.load(open(FROZEN))["sites"]


def save_frozen(rows):
    import json
    doc = {"notes": "Written by tools/island_sites.py --resite (PLAN.md R6): each site's record-frame (x, y) and yaw, "
                    "frozen. An ordinary run re-samples only the ground height. Re-search with --resite[=<id>].",
           "sites": [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]}
    text = json.dumps(doc, indent=1) + "\n"
    if not os.path.exists(FROZEN) or open(FROZEN).read() != text:
        open(FROZEN, "w").write(text)
        print("island_sites: wrote %s" % os.path.relpath(FROZEN, ROOT))


def main(argv):
    g = Ground()
    net = pm.load_network(RECORD)
    text = open(SCENE).read()
    ny = float(re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
               .group(1).split(",")[10])
    frozen = load_frozen()
    resite = [a for a in argv if a.startswith("--resite")]
    if resite or not frozen:
        only = None
        if resite and "=" in resite[0]:
            only = set(resite[0].split("=", 1)[1].split(","))
        found = search(g, net, only)
        keep = [r for r in frozen if only is not None and r["id"] not in only]
        order = [r["id"] for r in frozen] + [r["id"] for r in found if r["id"] not in {f["id"] for f in frozen}]
        byid = {r["id"]: r for r in keep + found}
        frozen = [byid[i] for i in order if i in byid]
        if "--check" not in argv:
            save_frozen(frozen)
    sites = []
    for r in frozen:
        h = site_ground(g, r)
        print("island_sites: %-18s at (%.0f, %.0f), ground %.2f m (frozen)" % (r["id"], r["x"], r["y"], h))
        sites.append((r["id"], r["scene"], (r["x"], r["y"], ny + h), r["yaw"], tuple(r["size"]), r["load"],
                      scene_offset(r)))
    sites = tuple(sites)
    import island_traffic_zones as itz
    sections = itz.split_sections(text)
    zone_ext = itz.ext_resource_id(sections, itz.ZONE_SCRIPT)
    marker_ext = itz.ext_resource_id(sections, itz.MARKER_SCRIPT)
    sub, nodes = [], ['[node name="%s" type="Node" parent="." unique_id=%d]\n\n' % (HOLDER, SITE_ID_BASE)]
    for i, (zid, scene, pos, yaw, size, load, (ox, oy)) in enumerate(sites):
        # the RESERVE (godot x, z, yaw, half x, half z), read by island_buildings.site_exclusions: the scene may
        # stand off its reserve's centre (the central station), so the scene transform cannot say where it is
        reserve = "PackedFloat64Array(%.3f, %.3f, %.6f, %.3f, %.3f)" % (pos[0], -pos[1], math.radians(yaw),
                                                                      size[0] / 2, size[1] / 2)
        spos = (pos[0] + ox, pos[1] + oy, pos[2])
        sub.append('[sub_resource type="Resource" id="%s%s"]\n'
                   'script = ExtResource("%s")\n'
                   'zone_id = "site_%s"\n'
                   'size = Vector3(%g, 120, %g)\n'
                   'load_radius = %.1f\n'
                   'unload_radius = %.1f\n'
                   'geometry_path = "%s%s.tscn"\n'
                   'geometry_world_placed = true\n'
                   'geometry_world_transform = %s\n'
                   'metadata/site_reserve = %s\n\n'
                   % (SUB_PREFIX, zid, zone_ext, zid, max(size), max(size), load, load + 300.0, BUILDINGS, scene,
                      site_xf(spos, yaw), reserve))
        nodes.append('[node name="%s" type="Node3D" parent="%s" unique_id=%d]\n'
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                     'script = ExtResource("%s")\n'
                     'zone = SubResource("%s%s")\n'
                     'show_debug_volume = false\n\n'
                     % (scene, HOLDER, SITE_ID_BASE + 1 + i, pos[0], pos[2], -pos[1], marker_ext, SUB_PREFIX, zid))

    def generated(header):
        if header.startswith("[sub_resource"):
            return (itz.attr(header, "id") or "").startswith(SUB_PREFIX)
        if header.startswith("[node"):
            name, parent = itz.attr(header, "name"), itz.attr(header, "parent")
            return name == HOLDER or parent == HOLDER
        return False
    new = itz.splice(sections, generated, sub, nodes)
    print("island_sites: scene %s" % ("changes" if new != text else "unchanged"))
    if "--check" in argv:
        sys.exit(1 if new != text else 0)
    if new != text:
        open(SCENE, "w").write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
