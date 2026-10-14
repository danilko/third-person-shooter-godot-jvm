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
         # (2026-10-03, the castle's walk in) it ENDS ON THE OUTER GATE'S AXIS: the castle's 歓会門 / 守礼門 line
         # (library_landmarks SH_GATE_Y, piece x SH_ROAD_X = -88, i.e. 9 m outside the site's footprint), the last
         # 29 m along that axis so a visitor looks straight up it at 守礼門. Move the gates, move these two points.
         via=[(-609.4, -164.2)], end=(-616.9, -135.2), parking=None),
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
    # (the MILITARY BASE has NO gate road, 2026-10-05: its gate is on the north fence 20 m south of the port road's
    # square west corner, entered straight on from kichi_dori over a dropped kerb -- island_port_road_square.py says
    # why a gate road does not fit. The old kichi_mon_michi, a T on the port road's bend running 93 m along the east
    # fence, was removed the same day.)
    # the AIRPORT'S SERVICE ROAD (user, 2026-09-29: the airside is fenced all round; "a vehicle service gate on the
    # landside for the hangar, off a service road -- it needs one"): a T off the forecourt loop's south leg, west of
    # the terminal, south to the locked gate in the airside fence (site_airport_fence.py GATE_GX)
    dict(name="kuko_service", site="airport_airfield", from_road="kuko_rotary", at=(1130.0, -1710.0),
         end=(1130.0, -1777.0), parking=None),
    # THE FISH MARKET (PLAN S11 P12, 2026-10-13; the Japanese layout the user approved on docs/previews/market_p12.png).
    # The market stands outside the dike on a quay 2 m over the water, 10 m below the crest, with ONE way in off the
    # dike road ring_kita:
    #  * `ichiba_michi`, the ONE truck ramp (坂路), from the existing signal at x 567 ("市場前", where eki_minami_dori
    #    climbs onto the dike from the land side: its 4th arm). South off the pad, a level R 15 bend, then WEST down the
    #    dike's sea face at ICHIBA_GRADE to the yard, skewed 5.8 deg seaward so it never cuts into the face. Its stations are AUTHORED (`stations`, see ichiba_stations): the
    #    bend as real arc stations faced on the arc, the fall with a 20 m vertical curve at each end -- so
    #    `_resample_square`, the dike's 5 % ramp pass and the grade smoothing all leave it alone (authored_roads()).
    #    It replaces the 2026-10-08 lane on z 703 (69 deg in one station, 5 % from the pad's edge).
    #  (The first build had a second gate, `ichiba_chushajo`: a T at x 375 to a car park on a terrace at the crest's
    #  height. With the yard lowered to a quay's height the ramp falls 10 m and its foot lands where the terrace stood;
    #  the public and the buyers park on the yard's east end instead. `signal` / `allow_cross` stay as ACCESS keys.)
    dict(name="ichiba_michi", site="fish_market", from_road="ring_kita", at=(567.0, -672.0),
         stations="ichiba", end=(379.0, -729.0), parking=None),
    # BEACH ACCESS over the dike (PLAN.md item 4, user 2026-10-08: "connect to the car parking just like the north east
    # top"). The dike IS the raised ring road, so cars already cross it on top and nothing needs an opening or a 陸閘;
    # what was missing is a way DOWN its sea face to the sand. Each lane is a T off the dike road, turns along the
    # dike's sea toe (where `island_dike.py raise` ramps it down off the crest, like ichiba_michi) and ends in a
    # beach car park on the flat strip between the toe and the sand; its footways are the pedestrian way down.
    # They replace island_reshape.DIKE_ACCESS's six points: "lighthouse" is todai_michi above, "farm" and
    # "residential_ne" share the north lane, "suburb" moved with the suburb fill (its old point is open sea now).
    #  * the FERRIS-WHEEL PARK (the "city" point): off ring_kita__13's west leg, north along the toe at x 893
    dict(name="kanransha_michi", site="waterfront_park", from_road="ring_kita", at=(945.0, -899.0),
         via=[(893.0, -899.0)], end=(893.0, -790.0), parking="ParkingLot14"),
    #  * the NORTH COAST beach (farm + residential north-east): west along the toe from x 840 to the farm's beach
    dict(name="kitahama_michi", site="north_beach", from_road="ring_kita", at=(852.0, 1541.0),
         via=[(845.0, 1598.0)], end=(705.0, 1628.0), parking="ParkingLot14"),
    #  * the WEST residential beach: south along the toe at x -1235 from ring_kita__12
    dict(name="nishihama_michi", site="west_beach", from_road="ring_kita", at=(-1188.0, -682.0),
         via=[(-1235.0, -690.0)], end=(-1235.0, -795.0), parking="ParkingLot14"),
    #  * the SUBURB beach behind the suburb fill: south off ring_kita__10, west along z 1145
    dict(name="kogaihama_michi", site="suburb_beach", from_road="ring_kita", at=(1065.0, -1085.0),
         via=[(1065.0, -1145.0)], end=(895.0, -1145.0), parking="ParkingLot14"),
    dict(name="butsuryu_michi", site="logistics_yard", from_road="kichi_dori", at=(-280.0, -1230.0),
         end=(-280.0, -1440.0), parking="ParkingLot14"),     # its car park short of the runway band (z 1480)
]


ICHIBA_X = 567.0                # the market ramp: its arm's line off the x 567 junction (record x)
ICHIBA_MOUTH = 20.5             # its mouth from the junction's centre (the pad's solved setback: 20.4-20.6)
ICHIBA_ARM = 20.0               # deg: the arm leaves the pad this far WEST of due south. Due south it stands opposite
#                                 the 3+3 north arm (eki_minami_dori, 8 deg off north), and the kit's turn search for a
#                                 3-lane-to-1-lane "straight on" runs away: the pad solved 57.9 m (75 at 0 deg, 215 at
#                                 +5) where every arm 15 deg or more off the line solves 20.8 -- measured, 2026-10-13
ICHIBA_R = 15.0                 # the level bend onto the dike's face (a truck's walking-pace turn; the pad is its room)
ICHIBA_PI_Z = 706.1             # Godot z of the bend's corner on the arm's line: R 15 then starts at the mouth
ICHIBA_SKEW = 6.9               # deg: the ramp runs this far SEAWARD of the dike's own line as it falls. The face is a
#                                 1:2 slope (crest edge z 698 at 11.9, toe z ~718 at the yard's 2.0), so the contour at
#                                 the ramp's own height moves 20 m seaward over its fall: a ramp PARALLEL to the dike
#                                 that starts on the face ends cut metres into it (the 2026-10-08 lane on z 703 did).
#                                 Skewed, its land-side edge follows the face down: seaward fill only, never a notch
ICHIBA_GRADE = 0.07             # its fall: 10 m in 163 m (a ramp's limit at 40 km/h; trucks take it at 20). At 6 % it is
#                                 187 m and ends in the west corner with no room to turn
ICHIBA_VCURVE = 20.0            # a vertical curve this long at the top and at the foot (MLIT: >= 20 m at 20 km/h)
ICHIBA_FOOT_RUN = 4.0           # m of level road past the foot (the yard is flat beyond it; the terrace wall is 15 m on)


def ichiba_stations(ground):
    """The market ramp's AUTHORED stations [(x, y, z, tangent or None)], record frame, mouth first: three on the level
    bend (start, middle, end -- none nearer the mouth than `tidy`'s 10 m MIN_MOUTH_CLEAR), then the fall along the
    skewed line: a 20 m parabola, ICHIBA_GRADE, a 20 m parabola onto the yard's ground, and ICHIBA_FOOT_RUN of level."""
    import island_dike as ID
    yj = -672.0
    top = ID.crest_at(ICHIBA_X, yj) - rg.NET_Y
    a = math.radians(ICHIBA_SKEW)
    w = (-math.cos(a), -math.sin(a))                                   # down the ramp: west, a little south
    k = math.radians(ICHIBA_ARM)
    t0 = (-math.sin(k), -math.cos(k))                                  # the arm: south-south-west off the pad
    m = (ICHIBA_X + t0[0] * ICHIBA_MOUTH, yj + t0[1] * ICHIBA_MOUTH)   # its mouth, on a ray from the pad's centre
    # the bend's corner: where the arm's line meets the ramp's line (through (ICHIBA_X, ICHIBA_PI_Z) along w)
    den = t0[0] * w[1] - t0[1] * w[0]
    sa = ((ICHIBA_X - m[0]) * w[1] - (-ICHIBA_PI_Z - m[1]) * w[0]) / den
    pi = (m[0] + t0[0] * sa, m[1] + t0[1] * sa)
    phi = math.acos(t0[0] * w[0] + t0[1] * w[1])
    T = ICHIBA_R * math.tan(phi / 2.0)
    s0 = (pi[0] - t0[0] * T, pi[1] - t0[1] * T)                        # the arc's start, on the arm
    e0 = (pi[0] + w[0] * T, pi[1] + w[1] * T)                          # its end, on the ramp's line
    c = (s0[0] + t0[1] * ICHIBA_R, s0[1] - t0[0] * ICHIBA_R)           # its centre: to the arm's right (the west)
    out = [(m[0], m[1], top, t0)]
    if sa - T > 10.0:                                                  # the arc's start, when it clears the mouth
        out.append((s0[0], s0[1], top, t0))
    h = -phi / 2.0                                                     # the arc's middle: s0 turned phi/2 clockwise
    rx, ry = s0[0] - c[0], s0[1] - c[1]
    out.append((c[0] + rx * math.cos(h) - ry * math.sin(h), c[1] + rx * math.sin(h) + ry * math.cos(h), top,
                (t0[0] * math.cos(h) - t0[1] * math.sin(h), t0[0] * math.sin(h) + t0[1] * math.cos(h))))
    out.append((e0[0], e0[1], top, w))

    def on_line(d):
        return (e0[0] + w[0] * d, e0[1] + w[1] * d)
    # the yard's own level at the foot, read clear of the dike's toe (8 m seaward of the ramp's line there)
    q = on_line(150.0)
    foot_z = ground.z(q[0], q[1] - 12.0) or 0.0     # (below the network's zero: the yard is under the plain)
    D = (top - foot_z) / ICHIBA_GRADE + ICHIBA_VCURVE

    def z_at(d):
        if d <= ICHIBA_VCURVE:
            return top - ICHIBA_GRADE * d * d / (2.0 * ICHIBA_VCURVE)
        if d >= D - ICHIBA_VCURVE:
            return foot_z + ICHIBA_GRADE * (D - d) ** 2 / (2.0 * ICHIBA_VCURVE)
        return top - ICHIBA_GRADE * (d - ICHIBA_VCURVE / 2.0)
    ds = [ICHIBA_VCURVE * k_ / 3.0 for k_ in (1, 2, 3)]
    run = D - 2.0 * ICHIBA_VCURVE
    n = max(1, int(math.ceil(run / 30.0)))
    ds += [ICHIBA_VCURVE + run * k_ / n for k_ in range(1, n + 1)]
    ds += [D - ICHIBA_VCURVE + ICHIBA_VCURVE * k_ / 3.0 for k_ in (1, 2, 3)]
    out += [on_line(d) + (z_at(d), None) for d in ds]
    out.append(on_line(D + ICHIBA_FOOT_RUN) + (foot_z, None))
    return out


STATIONS = {"ichiba": ichiba_stations}


def authored_roads():
    """The access roads whose stations AND heights are authored (`stations`): `island_dike.ramps` sets only their mouth
    on the pad and `island_grades smooth` holds every station (an 80 m moving average flattens a level bend and a 20 m
    vertical curve alike)."""
    return {a["name"] for a in ACCESS if a.get("stations")}


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
    if a.get("stations"):
        # AUTHORED stations, laid verbatim (the market ramp): no resampling, no squared corner, its own heights
        rows = STATIONS[a["stations"]](ground)
        road = chain_road(net, a["name"], [q[:3] for q in rows], preset="block")
        for u, q in zip(road.points, rows):
            if q[3] is not None:
                rg.freeze(net, u, q[3])
        _join(net, a, members, road)
        return road, members
    via = list(a.get("via", ()))
    first = via[0] if via else a["end"]
    dx, dy = first[0] - cx, first[1] - cy
    L = math.hypot(dx, dy)
    head = (cx + dx / L * MOUTH, cy + dy / L * MOUTH)
    ex, ey = a["end"]
    if via:
        # a street with corners (a hub station's, `station_access`): rounded, resampled like an authored street
        # square corners (user, 2026-10-05): a station on each corner and one 15 m either side, not a resampled fillet
        from island_core_streets import _resample_square
        plan = [head] + [tuple(v) for v in via] + [tuple(a["end"])]
        pts = _resample_square(rg.densify(plan, 4.0), SPACING)
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
    _join(net, a, members, road)
    return road, members


def _join(net, a, members, road):
    """The access road's mouth joins its junction. `signal` False = no lights (a minor T); `allow_cross` False = no turn
    across the oncoming lanes at any of its mouths (right-in / right-out: point_export drops the cross movement)."""
    make_junction(net, members + [road.points[0]], signal=a.get("signal", True))
    if not a.get("allow_cross", True):
        for u in members + [road.points[0]]:
            net.points[u].allow_cross = False
    ground = rg.Ground()
    for u in road.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True


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
