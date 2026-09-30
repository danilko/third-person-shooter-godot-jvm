#!/usr/bin/env python3
"""CIVIC PLOTS (user, 2026-09-28): ground HELD, before the streets are planned, for the public buildings a Japanese town
has -- so filling them later is a derive, never another road rebuild.

    python3 tools/island_civic_sites.py            search every plot not yet in the record, write the record
    python3 tools/island_civic_sites.py --resite[=id,id]   search again (all, or the named plots)
    python3 tools/island_civic_sites.py --check    every plot in the table is in the record, and still clear

The record, `assets/world_source/buildings/IslandCivicSites.json`, is FROZEN data (the `IslandSites.json` rule, PLAN.md
R6): an ordinary run keeps every plot where it is, so an access road or a new street cannot move the plot it was built
for. Record frame (x, y), like IslandSites; each plot carries `yaw`/`size` in IslandSites' convention (local x = the
frontage, along the road) so `island_streets` reads it as a site (a block street routes round it, SITE_CLEAR outside),
plus the unit vectors along the road (`ux`, `uy`) and toward it (`nx`, `ny`).

Who reads it: `island_streets._sites` (streets keep out), `island_buildings.civic_plots` (no generated building on it;
each plot becomes a paved LOT at footway level, written into the building record's `civic` list), and
`island_ground` (paves it like a lot). Nothing stands on a plot until its building type exists.

THE SEARCH. A plot FRONTS a road that exists before the street planner runs (an arterial, a trunk road, the ring, a
core street -- never a generated block street, which re-routes round the plot, and never an expressway, a touge or the
cliff coast road), at grade there, with at least `lanes` lanes a side. Its front edge stands FRONT_GAP past that road's
paved edge (footway included). The whole footprint must be: on land, flat within RELIEF, clear of every other road's
paved edge by ROAD_CLEAR (a block street excepted), of the rail corridor and its stations, of every frozen site, of
`island_plan.RESERVES`, of the dike works, and of every plot placed before it. Among the candidates, the one nearest the
plot's TARGET wins (a district's centre, or a station for a 交番) -- sizes are Japanese standard sites, see `PLOTS`.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import island_roadgen  # noqa: E402  (the kit's path)
import point_model as pm  # noqa: E402
import island_plan as PL  # noqa: E402
import island_sites as IS  # noqa: E402
import island_streets as ST  # noqa: E402

RECORD = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandCivicSites.json")
ROADS = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.roads.json")
ARTERIALS = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json")
RAIL_RESERVE = os.path.join(ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")

FRONT_GAP = 1.5        # m between the frontage road's paved edge (footway included) and the plot's front
ROAD_CLEAR = 4.0       # m from any OTHER road's paved edge (a block street excepted: it re-routes)
RELIEF = 1.5           # m of ground relief the whole footprint may have
AT_GRADE = 1.5         # m: the frontage road's surface within this of the ground under it
PLOT_GAP = 6.0         # m between two plots
STEP = 10.0            # m between candidates along a road
NO_FRONT = ("shuto_", "shrine_touge", "kaigan_dori", "rail")

# (id, kind, 日本語, frontage m, depth m, min lanes a side, target) -- target is a RECORD (x, y) or "station:<Name>".
# Sizes are ordinary Japanese sites: a 警察署 / 消防署 本署 ~1 800-2 500 m2, a 消防出張所 ~500 m2, a 交番 ~80 m2, a
# 300-bed 総合病院 ~1 ha, a 診療所 ~250 m2, a 小学校 with its 校庭 ~1.1 ha, a 中学校 ~1.4 ha, a 区役所 ~3 600 m2.
PLOTS = (
    # civic core, on the trunk roads round downtown and the city
    ("police_hq", "police_station", "警察署", 40.0, 45.0, 2, (650.0, 250.0)),
    ("fire_hq", "fire_station", "消防署", 40.0, 50.0, 2, (250.0, 150.0)),
    ("ward_office", "ward_office", "区役所", 60.0, 60.0, 2, (450.0, 350.0)),
    ("hospital_general", "hospital", "総合病院", 100.0, 100.0, 2, (150.0, 550.0)),
    ("post_office_main", "post_office", "郵便局", 40.0, 40.0, 2, (900.0, 150.0)),
    # the west (residential SW, west centre, residential west)
    ("police_west", "police_station", "警察署", 35.0, 40.0, 2, (-800.0, -500.0)),
    ("fire_branch_west", "fire_branch", "消防出張所", 20.0, 25.0, 1, (-1200.0, -700.0)),
    ("fire_branch_rwest", "fire_branch", "消防出張所", 20.0, 25.0, 1, (-500.0, 100.0)),
    ("hospital_west", "hospital", "病院", 55.0, 60.0, 1, (-1000.0, -850.0)),
    ("school_west", "elementary_school", "小学校", 100.0, 110.0, 1, (-1300.0, -800.0)),
    ("school_rwest", "elementary_school", "小学校", 100.0, 110.0, 1, (-550.0, 150.0)),
    ("jhs_west", "junior_high_school", "中学校", 110.0, 130.0, 1, (-900.0, -950.0)),
    ("post_office_west", "post_office", "郵便局", 15.0, 20.0, 1, (-700.0, -600.0)),
    # the north (residential north) and the east (suburb)
    ("fire_branch_north", "fire_branch", "消防出張所", 20.0, 25.0, 1, (700.0, 800.0)),
    ("school_north", "elementary_school", "小学校", 100.0, 110.0, 1, (300.0, 810.0)),
    ("fire_branch_east", "fire_branch", "消防出張所", 20.0, 25.0, 1, (1080.0, -650.0)),
    ("post_office_east", "post_office", "郵便局", 15.0, 20.0, 1, (1100.0, -500.0)),
    # 診療所: one in every residential district
    ("clinic_west", "clinic", "診療所", 14.0, 18.0, 1, (-1400.0, -600.0)),
    ("clinic_sw", "clinic", "診療所", 14.0, 18.0, 1, (-700.0, -900.0)),
    ("clinic_rwest", "clinic", "診療所", 14.0, 18.0, 1, (-400.0, -50.0)),
    ("clinic_north", "clinic", "診療所", 14.0, 18.0, 1, (1100.0, 820.0)),
    ("clinic_city", "clinic", "診療所", 14.0, 18.0, 1, (0.0, 300.0)),
    ("clinic_east", "clinic", "診療所", 14.0, 18.0, 1, (1000.0, -850.0)),
    # 交番: on the station square
    ("koban_central", "koban", "交番", 8.0, 10.0, 1, "station:Central"),
    ("koban_suburb", "koban", "交番", 8.0, 10.0, 1, "station:Suburb"),
    ("koban_residential", "koban", "交番", 8.0, 10.0, 1, "station:Residential"),
    ("koban_city_west", "koban", "交番", 8.0, 10.0, 1, "station:City West"),
    # leisure, the neighbourhood and the shore
    ("water_resort", "water_resort", "温浴・プールリゾート", 150.0, 120.0, 1, "station:Waterpark"),
    ("shrine_city", "shrine", "神社", 50.0, 60.0, 1, (-250.0, 50.0)),
    ("temple_west", "temple", "寺", 50.0, 50.0, 1, (-1450.0, -450.0)),
    ("park_west", "park", "公園", 60.0, 60.0, 1, (-800.0, -800.0)),
    ("park_north", "park", "公園", 60.0, 60.0, 1, (900.0, 850.0)),
    ("park_city", "park", "公園", 60.0, 60.0, 1, (100.0, -150.0)),
    # THE MISSION BUILDINGS (user, 2026-09-29 night: "place every interiors building ... assume the current vacancy on
    # the maps is for these"): the enterable kits/interiors buildings, each on a plot its footprint + 2 m all round
    # (`island_buildings.CIVIC_TYPES` / `CIVIC_SCENE`: locked `_Open` for a mission building, `_Shop` for a shop).
    # downtown (C1's south half, round the Central station) -- the bank, the HQ, the department store, the civic centre
    ("mission_bank_large", "bank_large", "銀行 (本店)", 44.0, 34.0, 2, (450.0, 50.0)),
    ("mission_office_hq", "office_hq", "本社ビル", 32.0, 30.0, 1, (300.0, 150.0)),
    ("mission_department_store", "department_store", "百貨店", 84.0, 64.0, 2, (800.0, 60.0)),
    ("mission_civic_center", "civic_center", "区民センター", 60.0, 50.0, 2, (1050.0, -50.0)),
    ("mission_fashion", "fashion_building", "ファッションビル", 38.0, 36.0, 1, (680.0, 20.0)),
    ("mission_safehouse_city_large", "safehouse_city_large", "雑居ビル (隠れ家)", 10.0, 21.0, 1, (220.0, 350.0)),
    # the nightlife quarter and 秋葉原
    ("mission_izakaya", "izakaya", "居酒屋", 9.0, 19.0, 1, (620.0, 420.0)),
    ("mission_maid_cafe", "maid_cafe", "メイドカフェ", 10.0, 20.0, 1, (1080.0, 250.0)),
    ("mission_adult", "adult_services", "風俗ビル", 10.0, 22.0, 1, (850.0, 480.0)),
    ("mission_safehouse_city_small", "safehouse_city_small", "狭小住宅 (隠れ家)", 8.0, 15.0, 1, (700.0, 520.0)),
    # the west's 駅前
    ("mission_bank_small", "bank_small", "銀行 (支店)", 20.0, 20.0, 1, (-730.0, -520.0)),
    # the housing, the hill edge, the industry, the mountain
    ("mission_safehouse_small", "safehouse_small", "一戸建て (隠れ家)", 12.0, 17.0, 1, (-900.0, -700.0)),
    ("mission_safehouse_large", "safehouse_large", "邸宅 (隠れ家)", 21.0, 22.0, 1, (600.0, 820.0)),
    ("mission_secure_mansion", "secure_mansion", "要塞邸宅", 68.0, 55.0, 1, (-450.0, 300.0)),
    ("mission_warehouse_yard", "warehouse_yard", "倉庫", 48.0, 54.0, 1, (-300.0, -800.0)),
    ("mission_onsen_ryokan", "onsen_ryokan", "温泉旅館", 46.0, 43.0, 1, (-675.0, 1125.0), {"front": ("shrine_touge",)}),
)


def load():
    if os.path.exists(RECORD):
        return json.load(open(RECORD))
    return {"notes": "FROZEN civic plots (tools/island_civic_sites.py); record frame; nothing stands on one yet",
            "plots": []}


def station_targets():
    out = {}
    if os.path.exists(RAIL_RESERVE):
        for b in json.load(open(RAIL_RESERVE))["boxes"]:
            if b["id"].startswith("station:"):
                out[b["id"][len("station:"):]] = (b["x"], b["y"])
    return out


def reserves_hit(x, y):
    gx, gz = x, -y
    return any(x0 <= gx <= x1 and z0 <= gz <= z1 for _n, (x0, z0, x1, z1) in PL.RESERVES)


def rail_hit(x, y):
    R = ST._rail()
    if any(True for _q in ST._rail_near(x, y, R["half"] + 2.0)):
        return True
    for _bid, cx, cy, ux, uy, ha, hc in R["boxes"]:
        dx, dy = x - cx, y - cy
        if abs(dx * ux + dy * uy) <= ha and abs(-dx * uy + dy * ux) <= hc:
            return True
    return False


_FROZEN = None


def site_hit(x, y):
    """Inside a frozen SITE (IslandSites.json, grown by the streets' SITE_CLEAR) -- the civic plots are checked apart."""
    global _FROZEN
    if _FROZEN is None:
        _FROZEN = [s for s in ST._sites() if not s[0].startswith("civic:")]
    for _sid, cx, cy, c, s_, hx, hy in _FROZEN:
        dx, dy = x - cx, y - cy
        if abs(dx * c + dy * s_) <= hx and abs(-dx * s_ + dy * c) <= hy:
            return True
    return False


def plot_hit(x, y, placed):
    for p in placed:
        dx, dy = x - p["x"], y - p["y"]
        if (abs(dx * p["ux"] + dy * p["uy"]) <= p["size"][0] / 2 + PLOT_GAP
                and abs(-dx * p["uy"] + dy * p["ux"]) <= p["size"][1] / 2 + PLOT_GAP):
            return True
    return False


class RoadDist(object):
    """Exact "is a road's PAVED EDGE within R of (x, y)", segment by segment (IS.road_index is a square box test,
    which on a 45 deg road reads ~1.4x too wide). `skip(name)` leaves a road out; `near(..., but=name)` ignores one."""

    CELL = 40.0

    def __init__(self, net, skip):
        import collections
        self.grid = collections.defaultdict(list)
        for name, r in net.roads.items():
            name = str(name)
            if skip(name) or len(r.points) < 2:
                continue
            h = IS.road_half(r)
            P = [net.points[u].pos for u in r.points]
            for a, b in zip(P, P[1:]):
                seg = (a[0], a[1], b[0], b[1], h, name)
                pad = h + 30.0
                for i in range(int((min(a[0], b[0]) - pad) // self.CELL), int((max(a[0], b[0]) + pad) // self.CELL) + 1):
                    for j in range(int((min(a[1], b[1]) - pad) // self.CELL),
                                   int((max(a[1], b[1]) + pad) // self.CELL) + 1):
                        self.grid[(i, j)].append(seg)

    def near(self, x, y, R, but=None):
        for ax, ay, bx, by, h, name in self.grid.get((int(x // self.CELL), int(y // self.CELL)), ()):
            if name == but:
                continue
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1e-9
            t = min(max(((x - ax) * dx + (y - ay) * dy) / L2, 0.0), 1.0)
            if math.hypot(ax + t * dx - x, ay + t * dy - y) < h + R:
                return True
        return False


def frontage_samples(net, g, min_lanes, allow=()):
    """(x, y, ux, uy, half, road) every STEP along every road a plot may front, at grade. `allow`: road-name prefixes a
    plot may front although NO_FRONT excludes them (the onsen on the mountain road)."""
    out = []
    for name, r in net.roads.items():
        name = str(name)
        if IS.is_block_street(name) or len(r.points) < 2:
            continue
        if name.startswith(NO_FRONT) and not (allow and name.startswith(tuple(allow))):
            continue
        if allow and not name.startswith(tuple(allow)):
            continue
        b = r.base
        if min(b.lanes_fwd, b.lanes_bwd) < min_lanes and max(b.lanes_fwd, b.lanes_bwd) < min_lanes:
            continue
        half = IS.road_half(r)
        P = [net.points[u].pos for u in r.points]
        for a, c in zip(P, P[1:]):
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            if L < 1e-6:
                continue
            ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
            n = max(1, int(L / STEP))
            for k in range(n):
                t = (k + 0.5) / n
                x, y, z = (a[i] + (c[i] - a[i]) * t for i in range(3))
                gz = g.z(x, y)
                if gz is None or abs(z - gz) > AT_GRADE:
                    continue
                out.append((x, y, ux, uy, half, name))
    return out


def search(spec, g, net, clear, samples, targets, placed):
    pid, kind, jp, fw, dp, lanes, target = spec[:7]
    if isinstance(target, str):
        st = targets.get(target.split(":", 1)[1])
        if st is None:
            return None, "no station %s in the rail reserve" % target
        target = st
    best = None
    for x, y, ux, uy, half, road in samples:
        if math.hypot(x - target[0], y - target[1]) > 1500.0:
            continue
        for sgn in (1.0, -1.0):
            nx, ny = -uy * sgn, ux * sgn            # away from the road
            off = half + FRONT_GAP + dp / 2.0
            cx, cy = x + nx * off, y + ny * off
            d = math.hypot(cx - target[0], cy - target[1])
            if best is not None and d >= best[0]:
                continue
            zs, ok = [], True
            na, nd = max(2, int(fw / 5.0) + 1), max(2, int(dp / 5.0) + 1)
            for ia in range(na):
                for idp in range(nd):
                    s = -fw / 2 + fw * ia / (na - 1)
                    t = -dp / 2 + dp * idp / (nd - 1)
                    px, py = cx + ux * s + nx * t, cy + uy * s + ny * t
                    z = g.z(px, py)
                    # the frontage road itself only has to stay FRONT_GAP off; every other road ROAD_CLEAR
                    if (z is None or z < -0.2 or clear.near(px, py, ROAD_CLEAR, but=road)
                            or clear.near(px, py, FRONT_GAP - 0.25) or rail_hit(px, py)
                            or site_hit(px, py) or reserves_hit(px, py) or ST._dike_hit(px, py)
                            or plot_hit(px, py, placed)):
                        ok = False
                        break
                    zs.append(z)
                if not ok:
                    break
            if not ok or max(zs) - min(zs) > RELIEF:
                continue
            best = (d, dict(id=pid, kind=kind, jp=jp, x=round(cx, 2), y=round(cy, 2),
                            yaw=round(math.degrees(math.atan2(uy, ux)), 3), size=[fw, dp],
                            ux=round(ux, 5), uy=round(uy, 5), nx=round(-nx, 5), ny=round(-ny, 5),
                            road=road, ground=round(min(zs), 2), target_miss=round(d, 1)))
    return (best[1], None) if best else (None, "no clear frontage within 1.5 km of its target")


def main(argv):
    check = "--check" in argv
    resite = None
    for a in argv:
        if a.startswith("--resite"):
            resite = set(a.split("=", 1)[1].split(",")) if "=" in a else {s_[0] for s_ in PLOTS}
    doc = load()
    have = {p["id"]: p for p in doc["plots"]}
    if check:
        missing = [s[0] for s in PLOTS if s[0] not in have]
        # every plot still FRONTS a road: the layout re-plans the streets and the dike's side road, and a plot whose
        # road moved away is ground nobody can reach (re-site it: --resite=<id>)
        net = pm.load_network(ROADS)
        clear = RoadDist(net, IS.is_block_street)
        cut = RoadDist(net, lambda n: not IS.is_block_street(n))
        lost, crossed = [], []
        for p in doc["plots"]:
            fx = p["x"] + p["nx"] * (p["size"][1] / 2 + FRONT_GAP)
            fy = p["y"] + p["ny"] * (p["size"][1] / 2 + FRONT_GAP)
            if not clear.near(fx, fy, 2.0):
                lost.append(p["id"])
            # ...and no road of the new layout runs through it (a block street is told to keep out; anything else
            # was there when it was searched, so this catches a layout change)
            for ia in range(5):
                for idp in range(5):
                    s_ = (ia / 4.0 - 0.5) * p["size"][0] * 0.9
                    t = (idp / 4.0 - 0.5) * p["size"][1] * 0.9
                    px = p["x"] + p["ux"] * s_ - p["nx"] * t
                    py = p["y"] + p["uy"] * s_ - p["ny"] * t
                    if clear.near(px, py, 0.0) or cut.near(px, py, 0.0):
                        crossed.append(p["id"])
                        break
                else:
                    continue
                break
        print("island_civic_sites: %d plot(s) recorded, %d missing%s; %d lost their frontage%s; %d crossed by a road%s"
              % (len(have), len(missing), (": " + ", ".join(missing)) if missing else "",
                 len(lost), (": " + ", ".join(lost)) if lost else "",
                 len(set(crossed)), (": " + ", ".join(sorted(set(crossed)))) if crossed else ""))
        return 1 if (missing or lost or crossed) else 0
    g = island_roadgen.Ground()
    net = pm.load_network(ROADS if os.path.exists(ROADS) else ARTERIALS)
    # --avoid-streets: keep off the finished layout's block streets too -- a plot re-sited AFTER the streets were
    # planned must not need another layout pass to clear it
    clear = RoadDist(net, (lambda n: False) if "--avoid-streets" in argv else IS.is_block_street)
    targets = station_targets()
    placed = [p for p in doc["plots"] if not (resite and p["id"] in resite)]
    samples = {}
    misses = []
    for spec in PLOTS:
        if any(p["id"] == spec[0] for p in placed):
            continue
        lanes = spec[5]
        allow = tuple((spec[7] if len(spec) > 7 else {}).get("front", ()))
        if (lanes, allow) not in samples:
            samples[(lanes, allow)] = frontage_samples(net, g, lanes, allow)
        got, why = search(spec, g, net, clear, samples[(lanes, allow)], targets, placed)
        if got is None:
            misses.append("%s (%s)" % (spec[0], why))
            continue
        placed.append(got)
        print("  %-20s %-18s on %-22s %5.0f m from its target" % (got["id"], got["jp"], got["road"],
                                                                   got["target_miss"]))
    order = {s[0]: i for i, s in enumerate(PLOTS)}
    doc["plots"] = sorted(placed, key=lambda p: order.get(p["id"], 999))
    with open(RECORD, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("island_civic_sites: %d plot(s) -> %s%s" % (len(doc["plots"]), os.path.relpath(RECORD, ROOT),
          ("; NOT PLACED: " + "; ".join(misses)) if misses else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
