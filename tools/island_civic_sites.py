#!/usr/bin/env python3
"""CIVIC PLOTS (user, 2026-09-28): ground HELD, before the streets are planned, for the public buildings a Japanese town
has -- so filling them later is a derive, never another road rebuild.

    python3 tools/island_civic_sites.py            search every plot not yet in the record, write the record
    python3 tools/island_civic_sites.py --resite[=id,id]   search again (all, or the named plots)
    python3 tools/island_civic_sites.py --check    every plot in the table is in the record, and still clear
    python3 tools/island_civic_sites.py --coverage every district reaches a 交番, a fire station and a konbini (and a
                                                   residential one a bank and a clinic) -- after the buildings stage

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
    ("post_office_west", "post_office", "郵便局", 15.0, 20.0, 1, (-700.0, -600.0)),
    # the water resort FIRST in the east (the search is in table order): it needs the suburb loop's whole interior beside
    # the beach hotels, and the fire station and clinic take what it leaves
    ("water_resort", "water_resort", "温浴・プールリゾート", 150.0, 70.0, 1, (1065.0, -800.0)),   # inside the dike, inside the suburb loop (2026-10-03)
    # the north (residential north) and the east (suburb)
    ("fire_branch_north", "fire_branch", "消防出張所", 20.0, 25.0, 1, (700.0, 800.0)),
    ("fire_branch_east", "fire_branch", "消防出張所", 20.0, 25.0, 1, (1110.0, -720.0)),
    ("post_office_east", "post_office", "郵便局", 15.0, 20.0, 1, (1100.0, -500.0)),
    # 診療所: one in every residential district
    ("clinic_west", "clinic", "診療所", 14.0, 18.0, 1, (-1400.0, -600.0)),
    ("clinic_sw", "clinic", "診療所", 14.0, 18.0, 1, (-700.0, -900.0)),
    ("clinic_rwest", "clinic", "診療所", 14.0, 18.0, 1, (-400.0, -50.0)),
    ("clinic_north", "clinic", "診療所", 14.0, 18.0, 1, (1100.0, 820.0)),
    ("clinic_city", "clinic", "診療所", 14.0, 18.0, 1, (0.0, 300.0)),
    ("clinic_east", "clinic", "診療所", 14.0, 18.0, 1, (1120.0, -770.0)),
    # 交番: on the station square
    ("koban_central", "koban", "交番", 8.0, 10.0, 1, "station:Central"),
    ("koban_suburb", "koban", "交番", 8.0, 10.0, 1, "station:Suburb"),
    ("koban_residential", "koban", "交番", 8.0, 10.0, 1, "station:Residential"),
    ("koban_city_west", "koban", "交番", 8.0, 10.0, 1, "station:City West"),
    # PLAN.md item 6 (2026-10-02 night): every district within COVERAGE of a 交番 and a fire station, every residential
    # district of a bank and a clinic -- measured, these were the gaps (industry + the port 660-960 m from police and
    # fire, the farm 1 km from police, residential north / west 560-780 m from a bank)
    ("koban_port", "koban", "交番", 8.0, 10.0, 1, (-250.0, -1000.0)),
    ("fire_branch_port", "fire_branch", "消防出張所", 20.0, 25.0, 1, (-150.0, -900.0)),
    ("koban_farm", "koban", "交番", 8.0, 10.0, 1, "station:Farm"),
    ("bank_north", "bank_small", "銀行 (支店)", 20.0, 20.0, 1, (700.0, 790.0)),
    ("bank_rwest", "bank_small", "銀行 (支店)", 20.0, 20.0, 1, (-250.0, -20.0)),
    # 郵便局 (user, 2026-10-03): a branch in every residential district, the 集配 main office (post_office_main) in the
    # city; residential north is 2 km long, so it gets two
    ("post_office_rwest", "post_office", "郵便局", 15.0, 20.0, 1, (-500.0, 100.0)),
    ("post_office_sw", "post_office", "郵便局", 15.0, 20.0, 1, (-1350.0, -850.0)),
    ("post_office_north", "post_office", "郵便局", 15.0, 20.0, 1, (250.0, 820.0)),
    ("post_office_north_e", "post_office", "郵便局", 15.0, 20.0, 1, (1300.0, 820.0)),
    # THE REVIEW'S JAPANESE CITY TYPES (user, 2026-10-03: "do all, so less vacancy"; blender/tools/library_jp_city.py).
    # Targets are the large vacant blocks measured on the built island (a 4 m vacancy grid against roads, lots, sites).
    # ONE school (user: "all in one school ... one big building ... park land for baseball"): the K-12 学園 on the big
    # empty block by the industry district, and the UNIVERSITY as an urban campus north of the city (Waseda / Keio Mita
    # shape); the separate elementary / junior-high plots are retired
    ("campus", "campus", "学園 (幼稚園〜高校)", 260.0, 220.0, 1, (-380.0, -740.0)),   # the plot is the Campus piece (260 x 220): at 240 x 180 its wall stood on kichi_dori
    ("university", "university", "大学", 110.0, 100.0, 1, (130.0, 450.0)),
    ("public_library", "public_library", "区立図書館", 40.0, 36.0, 1, (1000.0, -100.0)),
    # the GANGS (gangs.json): 黒鉄会 Kurogane-kai downtown / nightlife (HQ = mission_secure_mansion, fronts =
    # mission_adult + the pachinko), 青木場組 Aokiba-gumi the harbour / industry (HQ = the port compound, front = the
    # scrapyard); each has a street office (組事務所)
    ("gang_office_kurogane", "gang_office", "組事務所 (黒鉄会)", 12.0, 20.0, 1, (700.0, 250.0), {"gang": "gang_a"}),
    ("pachinko", "pachinko", "パチンコ店", 60.0, 45.0, 2, (786.0, -190.0), {"gang": "gang_a"}),
    ("gang_hq_aokiba", "gang_port_compound", "青木場組 本部", 70.0, 55.0, 1, (-631.0, -1189.0), {"gang": "gang_b"}),
    ("gang_office_aokiba", "gang_office", "組事務所 (青木場組)", 12.0, 20.0, 1, (-360.0, -1008.0), {"gang": "gang_b"}),
    ("gang_scrapyard", "gang_scrapyard", "解体屋 (青木場組)", 50.0, 40.0, 1, (-639.0, -994.0), {"gang": "gang_b"}),
    # the city's other Japanese types
    ("shotengai", "shotengai", "アーケード商店街", 24.0, 112.0, 1, "station:City West"),
    ("danchi", "danchi", "団地", 130.0, 110.0, 1, (-1150.0, -780.0)),
    ("hotel_business", "hotel_business", "ビジネスホテル", 22.0, 22.0, 1, "station:Central"),
    ("hotel_love", "hotel_love", "ラブホテル", 22.0, 24.0, 1, (850.0, 420.0)),
    ("karaoke", "karaoke", "カラオケボックス", 14.0, 22.0, 1, (620.0, 330.0)),
    ("game_centre", "game_centre", "ゲームセンター", 18.0, 24.0, 1, (1100.0, 300.0)),
    ("construction_site", "construction_site", "工事現場", 60.0, 42.0, 1, (483.0, 398.0)),
    ("arena", "arena", "アリーナ", 150.0, 120.0, 1, (0.0, -620.0)),   # 2026-10-03: the dike side road runs through the old (377, -568); now on kojo_waku by Industry station (Ariake Arena by the bay industry)
    ("suburban_mall", "suburban_mall", "郊外型モール (シネコン)", 160.0, 130.0, 1, (31.0, -545.0)),   # on ex-
    # industrial land by Industry station (the LaLaport Toyosu pattern): the suburb has no 150 x 115 m of frontage, and
    # at the farm edge it took the paddy grid's lines and the farm rows collapsed. (2026-10-03) 160 x 130: the piece is
    # 160 x 120 with its origin 5 m off centre, and at 150 x 115 its wall stood on the road
    # THE SECOND REVIEW (2026-10-03: "all ... everything"): the roadside and the neighbourhood. A 交番 at EVERY
    # station front (police dispatch spawns); a supermarket by each housing station; 整備工場 (the wanted-clear
    # garage) in the working districts; temples with cemeteries; the roadside home centre pair; one frozen car dealer
    ("koban_res_north", "koban", "交番", 8.0, 10.0, 1, "station:Residential North"),
    ("koban_bay", "koban", "交番", 8.0, 10.0, 1, "station:Bay"),
    ("koban_fish_market", "koban", "交番", 8.0, 10.0, 1, "station:Fish Market"),
    ("koban_airport", "koban", "交番", 8.0, 10.0, 1, "station:Airport"),
    ("koban_castle_town", "koban", "交番", 8.0, 10.0, 1, "station:Castle Town"),
    ("koban_light_industry", "koban", "交番", 8.0, 10.0, 1, "station:Light Industry"),
    ("koban_industry", "koban", "交番", 8.0, 10.0, 1, "station:Industry"),
    ("koban_harbour", "koban", "交番", 8.0, 10.0, 1, "station:Harbour"),
    ("supermarket_residential", "supermarket", "スーパー", 38.0, 62.0, 1, "station:Residential"),
    ("supermarket_res_north", "supermarket", "スーパー", 38.0, 62.0, 1, "station:Residential North"),
    ("supermarket_suburb", "supermarket", "スーパー", 38.0, 62.0, 1, "station:Suburb"),
    ("supermarket_light_industry", "supermarket", "スーパー", 38.0, 62.0, 1, "station:Light Industry"),
    ("repair_west", "repair_shop", "整備工場", 30.0, 30.0, 1, (-1000.0, -800.0)),
    ("repair_light_industry", "repair_shop", "整備工場", 30.0, 30.0, 1, (-500.0, -520.0)),
    ("repair_north", "repair_shop", "整備工場", 30.0, 30.0, 1, (900.0, 780.0)),
    ("repair_suburb", "repair_shop", "整備工場", 30.0, 30.0, 1, (1000.0, -600.0)),
    ("temple_castle", "temple_cemetery", "寺と墓地", 70.0, 62.0, 1, (-450.0, -50.0)),
    ("temple_north", "temple_cemetery", "寺と墓地", 70.0, 62.0, 1, (400.0, 820.0)),
    ("temple_cemetery_west", "temple_cemetery", "寺と墓地", 70.0, 62.0, 1, (-1250.0, -650.0)),   # (was a second "temple_west")
    ("home_centre_suburb", "home_centre", "ホームセンター", 120.0, 90.0, 2, (1100.0, -550.0)),
    ("car_dealer_import", "car_dealer", "輸入車ディーラー", 40.0, 36.0, 2, (1250.0, 100.0)),
    # THE THIRD REVIEW (2026-10-03): player services (the respray is a repair shop near the CBD), a mission building
    # in every quiet district (the farm's barn, the suburb's スーパー銭湯, the port's warehouse; the airport's cargo shed is a
    # reserve site, island_plan.RESERVES airport_cargo -- no local road there counts as frontage
    # yard), the 大浴場 in the residential district and the city too (user), 立体駐車場 to hide in, and Okinawa's
    # 公設市場 by Castle Town (whose 参道 is the island's 国際通り-style shopping street, STREET_MIXES)
    ("respray_cbd", "repair_shop", "整備工場 (塗装)", 30.0, 30.0, 1, (1050.0, 500.0)),
    ("clothing_store", "clothing_store", "衣料品店", 30.0, 28.0, 1, (450.0, 150.0)),
    ("shooting_range", "shooting_range", "射撃場", 30.0, 60.0, 1, (-200.0, -780.0)),
    ("impound_lot", "impound_lot", "レッカー保管場所", 50.0, 42.0, 1, (650.0, 300.0)),
    ("parking_garage_nightlife", "parking_garage", "立体駐車場", 36.0, 50.0, 1, (900.0, 350.0)),
    ("parking_garage_west", "parking_garage", "立体駐車場", 36.0, 50.0, 1, (-700.0, -450.0)),
    ("mission_farm_barn", "farm_barn", "農家 (納屋)", 60.0, 50.0, 1, (700.0, 1350.0), {"gang": "gang_a"}),
    ("super_sento_suburb", "super_sento", "スーパー銭湯", 90.0, 70.0, 1, (1050.0, -500.0)),
    ("super_sento_residential", "super_sento", "スーパー銭湯", 90.0, 70.0, 1, (-1100.0, -350.0)),
    ("super_sento_city", "super_sento", "スーパー銭湯", 90.0, 70.0, 1, (200.0, -150.0)),
    ("mission_port_warehouse", "warehouse_yard", "倉庫 (密輸)", 48.0, 54.0, 1, (-100.0, -1150.0), {"gang": "gang_b"}),
    ("public_market", "public_market", "公設市場", 50.0, 40.0, 1, (-560.0, -200.0)),
    # leisure, the neighbourhood and the shore
    ("shrine_city", "shrine", "神社", 50.0, 60.0, 1, (-250.0, 50.0)),
    ("temple_west", "temple", "寺", 52.0, 52.0, 1, (-1450.0, -450.0)),
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
    ("mission_adult", "adult_services", "風俗ビル", 10.0, 22.0, 1, (850.0, 480.0), {"gang": "gang_a"}),
    ("mission_safehouse_city_small", "safehouse_city_small", "狭小住宅 (隠れ家)", 8.0, 15.0, 1, (700.0, 520.0)),
    # the west's 駅前
    ("mission_bank_small", "bank_small", "銀行 (支店)", 20.0, 20.0, 1, (-730.0, -520.0)),
    # the housing, the hill edge, the industry, the mountain
    ("mission_safehouse_small", "safehouse_small", "一戸建て (隠れ家)", 12.0, 17.0, 1, (-900.0, -700.0)),
    ("mission_safehouse_large", "safehouse_large", "邸宅 (隠れ家)", 21.0, 22.0, 1, (600.0, 820.0)),
    ("mission_secure_mansion", "secure_mansion", "要塞邸宅", 68.0, 55.0, 1, (-450.0, 300.0), {"gang": "gang_a"}),   # 黒鉄会's HQ
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

        # a junction PAD lies between its mouths, which are the ends of separate roads -- no segment above covers it
        # (a koban was placed across wangan_dori's crossing): each pair of mouths is a segment too, as wide as the wider
        for clique in net.junction_cliques():
            ms = [(net.points[u].pos, IS.road_half(net.road_of(u)), str(net.road_of(u).name)) for u in clique
                  if net.road_of(u) is not None and not skip(str(net.road_of(u).name))]
            for k, (a, ha, na) in enumerate(ms):
                for b, hb, nb in ms[k + 1:]:
                    seg = (a[0], a[1], b[0], b[1], max(ha, hb), "pad:" + na)
                    pad = max(ha, hb) + 30.0
                    for i in range(int((min(a[0], b[0]) - pad) // self.CELL),
                                   int((max(a[0], b[0]) + pad) // self.CELL) + 1):
                        for j in range(int((min(a[1], b[1]) - pad) // self.CELL),
                                       int((max(a[1], b[1]) + pad) // self.CELL) + 1):
                            self.grid[(i, j)].append(seg)

    def near(self, x, y, R, but=None, side=None):
        """`side` = (sx, sy, nx, ny, half): the frontage line (a sample on it, the normal toward the plot, the road's
        half width) -- a road whose nearest point lies within the frontage road's band or behind it (a junction pad,
        a street T-ing in from the FAR side) does not block the plot."""
        # `but` is the FRONTAGE road, and it is the same street past its own junctions: a long plot runs along
        # several of its zone/junction pieces (kichi_dori, kichi_dori__x2, kichi_dori__x2__x1 ...), so the pieces
        # are matched by base name (2026-10-03: a 240 m campus tripped on its own road's next piece)
        base = but.split("__")[0] if but else None
        for ax, ay, bx, by, h, name in self.grid.get((int(x // self.CELL), int(y // self.CELL)), ()):
            # (a junction PAD on the frontage road, "pad:<road>", is that road's too; a street joining it from the
            # plot's side still blocks the plot through its own segments)
            if name == but or (base and name.replace("pad:", "", 1).split("__")[0] == base):
                continue
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1e-9
            t = min(max(((x - ax) * dx + (y - ay) * dy) / L2, 0.0), 1.0)
            qx, qy = ax + t * dx, ay + t * dy
            if side is not None and (qx - side[0]) * side[2] + (qy - side[1]) * side[3] < side[4]:
                continue
            if math.hypot(qx - x, qy - y) < h + R:
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
                    if (z is None or z < -0.2 or clear.near(px, py, ROAD_CLEAR, but=road, side=(x, y, nx, ny, half))
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


#: PLAN.md item 6's coverage rule: from each district's building centroid, the nearest of each service within this
#: many metres; a bank and a clinic/hospital are required of the RESIDENTIAL districts only
COVERAGE = {"police": 600.0, "fire": 700.0, "konbini": 600.0}
COVERAGE_HOME = {"bank": 800.0, "medical": 800.0, "post": 800.0}   # post: a branch 郵便局 (user, 2026-10-03)
HOME_DISTRICTS = ("residential", "residential_north", "residential_west")
COVERAGE_MIN = 20            # a district with fewer buildings shares its neighbour's services (reported, not failed)


def coverage(doc):
    """PLAN.md item 6: every district with buildings has a 交番 / police station, a fire station and a konbini within
    COVERAGE of its buildings' centroid; every residential district a bank and a clinic or hospital. Reads the building
    record (`island_buildings.py derive`'s output) for the districts and the konbini, and this record for the rest.
    Returns the failures."""
    import island_buildings as IB
    if not os.path.exists(IB.OUT):
        print("island_civic_sites: coverage: no building record yet")
        return []
    blds = json.load(open(IB.OUT))["buildings"]

    def district(x, y):
        for r in IB.REGIONS:
            x0, y0, x1, y1 = r[1]
            if r[0] != "ekimae" and x0 <= x <= x1 and y0 <= y <= y1:
                return r[0]
        return None
    pts = {}
    for b in blds:
        x, y = b["pos"][0], -b["pos"][2]
        pts.setdefault(district(x, y), []).append((x, y))
    svc = {"police": [], "fire": [], "konbini": [], "bank": [], "medical": [], "post": []}
    for p in doc["plots"]:
        k = p["kind"]
        xy = (p["x"], p["y"])
        if k in ("koban", "police_station"):
            svc["police"].append(xy)
        if k in ("fire_branch", "fire_station"):
            svc["fire"].append(xy)
        if k.startswith("bank"):
            svc["bank"].append(xy)
        if k in ("hospital", "hospital_small", "clinic"):
            svc["medical"].append(xy)
        if k == "post_office":
            svc["post"].append(xy)
    svc["konbini"] = [(b["pos"][0], -b["pos"][2]) for b in blds if b["type"].startswith("Konbini")]
    bad = []
    for name, ps in sorted(pts.items(), key=lambda kv: -len(kv[1])):
        if name is None:
            continue
        cx = sum(p[0] for p in ps) / len(ps)
        cy = sum(p[1] for p in ps) / len(ps)
        rule = dict(COVERAGE, **(COVERAGE_HOME if name in HOME_DISTRICTS else {}))
        row = []
        for k, lim in rule.items():
            d = min((math.hypot(cx - x, cy - y) for x, y in svc[k]), default=1e9)
            over = d > lim
            row.append("%s %.0f%s" % (k, d, "!" if over else ""))
            if over and len(ps) >= COVERAGE_MIN:
                bad.append("%s %s %.0f m" % (name, k, d))
        print("  %-18s %4d bld  %s%s" % (name, len(ps), "  ".join(row),
                                         "" if len(ps) >= COVERAGE_MIN else "  (small: shares)"))
    print("island_civic_sites: coverage %s" % ("OK" if not bad else "FAILS: " + "; ".join(bad)))
    return bad


def piece_extents():
    """{plot kind: (along, deep)} a plot must have to cover its building: the library piece's extent, doubled about the
    piece's origin (a civic building stands with its origin on the plot's centre, `plot_origin`)."""
    import island_buildings as IB_
    pj = json.load(open(os.path.join(ROOT, "assets", "world_source", "kits", "library", "pieces.json")))
    pieces = pj.get("pieces", pj)
    bt = json.load(open(os.path.join(ROOT, "assets", "world_source", "buildings", "building_types.json")))
    custom = {r["id"]: r for r in bt.get("custom", [])}
    out = {}
    for kind, t in getattr(IB_, "CIVIC_TYPES", {}).items():
        t = t[0] if isinstance(t, (tuple, list)) else t
        pc = custom.get(t, {}).get("piece")
        if pc in pieces:
            mn, mx = pieces[pc]["min"], pieces[pc]["max"]
            out[kind] = (2 * max(abs(mn[0]), mx[0]), 2 * max(abs(mn[2]), mx[2]))
    return out


def main(argv):
    check = "--check" in argv
    if "--coverage" in argv:
        return 1 if coverage(load()) else 0
    resite = None
    for a in argv:
        if a.startswith("--resite"):
            resite = set(a.split("=", 1)[1].split(",")) if "=" in a else {s_[0] for s_ in PLOTS}
    doc = load()
    have = {p["id"]: p for p in doc["plots"]}
    ids = [s_[0] for s_ in PLOTS]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise SystemExit("island_civic_sites: plot id(s) used twice in PLOTS: %s" % ", ".join(dup))
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
        # ...and the plot COVERS its building (2026-10-03: the campus was a 240 x 180 plot under a 260 x 220 piece, and
        # its wall stood on kichi_dori; nothing compared the two). A record whose size differs from PLOTS is stale too.
        small = []
        need = piece_extents()
        spec = {s_[0]: s_ for s_ in PLOTS}
        for p in doc["plots"]:
            n_ = need.get(p["kind"])
            sp = spec.get(p["id"])
            if (n_ and (n_[0] > p["size"][0] + 0.5 or n_[1] > p["size"][1] + 0.5)) or (
                    sp and [float(sp[3]), float(sp[4])] != [float(v) for v in p["size"]]):
                small.append(p["id"])
        print("island_civic_sites: %d plot(s) recorded, %d missing%s; %d lost their frontage%s; %d crossed by a road%s; "
              "%d smaller than their building or stale%s"
              % (len(have), len(missing), (": " + ", ".join(missing)) if missing else "",
                 len(lost), (": " + ", ".join(lost)) if lost else "",
                 len(set(crossed)), (": " + ", ".join(sorted(set(crossed)))) if crossed else "",
                 len(small), (": " + ", ".join(small)) if small else ""))
        return 1 if (missing or lost or crossed or small) else 0
    g = island_roadgen.Ground()
    net = pm.load_network(ROADS if os.path.exists(ROADS) else ARTERIALS)
    # --avoid-streets: keep off the finished layout's block streets too -- a plot re-sited AFTER the streets were
    # planned must not need another layout pass to clear it
    clear = RoadDist(net, (lambda n: False) if "--avoid-streets" in argv else IS.is_block_street)
    targets = station_targets()
    known = {s[0] for s in PLOTS}
    gone = [p["id"] for p in doc["plots"] if p["id"] not in known]
    if gone:
        print("island_civic_sites: retired (no longer in PLOTS): %s" % ", ".join(gone))
    placed = [p for p in doc["plots"] if p["id"] in known and not (resite and p["id"] in resite)]
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
    # a plot's GANG (gangs.json): the HQ, office and fronts each gang owns -- the record carries it so the places and
    # the clerk markers can name the owner
    gangs = {s[0]: s[7]["gang"] for s in PLOTS if len(s) > 7 and "gang" in s[7]}
    for p in placed:
        if p["id"] in gangs:
            p["gang"] = gangs[p["id"]]
        else:
            p.pop("gang", None)
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
