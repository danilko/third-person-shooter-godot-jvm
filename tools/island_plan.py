#!/usr/bin/env python3
"""island_plan.py -- the island's FINAL PLAN as data (PLAN.md 3.29 v15, built by 3.30).

`reference/island_final_plan_2026-09-21.png` is the decision; this module is what the tools read from it, so no road
generator types a coordinate of its own again:

* `deform(x, y)` -- the plan's movement of the city, in the RECORD frame (x east, y north = -Godot z):
    - downtown and the core grid 125 m WEST (v9), ramped over x -150..150 and faded out north of the farm (z -1150..
      -1000) and south of the bay (z 420..570), so a road crossing those lines bends instead of jumping;
    - the top of the island 150 m SOUTH (v10): full north of Godot z -40, the band z -40..330 between downtown and the
      bay compressed linearly (the city between them is squeezed 370 -> 220 m), ramped over x -400..-150 so the castle
      and the residential south-west do not move. The land grid moved the farm block the same 150 m
      (`island_reshape.FARM_SHIFT`), so a farm road lands on its own shifted farm.
  The plan picture drew the same maps (scratchpad `review7/v16.py` `cshift`) with hard steps; these are the smooth
  version of them.
* `ARTERIAL_LINES` -- every arterial of the final plan, as a named polyline: the pre-redo arterials (their record,
  `IslandRoads.arterials.pre_redo.roads.json`) deformed, and the plan's NEW roads (the coastal ring, the bay roads,
  the suburb loop, the castle approach, the military access) in plan coordinates. `island_network.py` builds them.
* The expressway and site anchors the generators need (C1's rectangle, the spur, the Wangan, the JCTs, the bridge).

Everything here is in the RECORD frame unless a name says GODOT.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PIECES = os.path.join(ROOT, "assets", "world_source", "pieces")
PRE_REDO = os.path.join(PIECES, "IslandRoads.arterials.pre_redo.roads.json")

CITY_WEST = 125.0            # v9: downtown centred in the remaining city land
NORTH_SOUTH = 150.0          # v10: the top of the island pushed down


def _ramp(v, a, b):
    return max(0.0, min(1.0, (v - a) / (b - a)))


def deform_godot(x, z):
    """(x, z) Godot -> the plan's position of the same place."""
    dx = -CITY_WEST * _ramp(x, -150.0, 150.0) * _ramp(z, -1150.0, -1000.0) * (1.0 - _ramp(z, 420.0, 570.0))
    if z <= -40.0:
        f = 1.0
    elif z < 330.0:
        f = (330.0 - z) / 370.0
    else:
        f = 0.0
    dz = NORTH_SOUTH * _ramp(x, -400.0, -150.0) * f
    return x + dx, z + dz


def deform(x, y):
    """(x, y) record -> the plan's position of the same place."""
    gx, gz = deform_godot(x, -y)
    return gx, -gz


def g2r(pts):
    """Godot (x, z) points -> record (x, y)."""
    return [(float(x), -float(z)) for x, z in pts]


# ------------------------------------------------------------------ the arterials
#: pre-redo arterials that are NOT carried over: the old touges (re-derived on the new mountain, island_touges.py),
#: the NW coast road (re-derived on the new shore, island_coast_road.py), the free curve into the base (v15: reached
#: through the blocks now), the port road on the trimmed harbour tip, the old coast roads the coastal RING replaces
#: (on trimmed land after v6/v9), the airport road on the bridge's lower deck (R7: that deck is RAIL; cars take the
#: spur) and the east arterial on the trimmed east coast.
#: THE MOUNTAIN ROADS, by name prefix (S15: one owner -- ~15 tools keyed off the literal `shrine_touge`). Every tool
#: that treats the touge specially (no wiggle / fillet / align pass, no building or civic frontage, no block-split end,
#: its own picture colour, the touge sculpt) reads this; a new mountain road joins the tuple when it is derived.
MOUNTAIN_ROADS = ("shrine_touge", "kita_touge")
DROPPED = MOUNTAIN_ROADS + ("kaigan_dori", "port_road", "futo_dori", "kitahama_dori", "nishihama_dori", "kuko_dori",
           "hama_dori")

#: the plan's NEW at-grade roads, GODOT (x, z) as the plan drew them (v16.py `NEWR`, `RING_NEW`, `MILR`), and the
#: road type each is (point_presets). The third field: True = drawn in PRE-shift coordinates (v16 applied cshift to
#: them); "snap" = a sketch against the shore, each point moved inland until it has SNAP_MARGIN of land seaward
#: (v16's `snap_in`, which the plan picture applied to the ring's north-east and west sides).
NEW_ROADS_GODOT = [
    # the COASTAL RING (v8/v9), at grade, `arterial` preset (2 + 2 with footways: buildings front it, so no
    # wall -- user, 2026-09-21: a wall is for a ramp, an expressway or a stretch with no buildings). The NW coast road (island_coast_road.py) is its
    # fourth side: it runs from the residential SW shore (-1440, 330) round the mountain to the NE (631, -1652).
    ("ring_kita", "arterial", "snap", [(631, -1652), (900, -1610), (1150, -1500), (1250, -1300), (1270, -1050),
                                   (1260, -800), (1250, -450), (1240, -100), (1220, 200), (1190, 520)]),
    ("ring_minami", "arterial", False, [(1190, 520), (1150, 640), (1000, 672), (880, 672), (560, 672), (320, 672),
                                     (240, 700), (232, 960), (-224, 1112)]),
    ("ring_nishi", "arterial", "snap", [(-224, 1112), (-500, 1080), (-820, 1050), (-1000, 1000), (-1150, 920),
                                    (-1300, 700), (-1380, 480), (-1420, 330)]),
    # the bay (v1): the bay trunk E-W, the quay road, the Central -> Bay avenue, the suburb loop, the castle approach
    ("wangan_dori", "trunk", True, [(-160, 420), (300, 430), (880, 430), (1120, 560)]),
    # hatoba_dori (320, 735) -> (860, 735) was removed 2026-09-28 (user: no clear job, a hill between the two dike
    # stretches; tools/island_remove_hatoba.py took it out of the arterials input)
    ("eki_minami_dori", "trunk", True, [(580, -300), (580, 760)]),
    ("kogai_michi", "block", True, [(930, 420), (1000, 700), (1200, 850)]),
    ("jokamachi_dori", "block", False, [(-610, 20), (-610, 360)]),     # the castle (frozen at (-600, 40)) south to nishi_dori
    # the military base, reached THROUGH the blocks (v15): industry street x -500, logistics street z 1150, the gate
    ("kichi_dori", "block", False, [(-500, 150), (-500, 1054)]),
    # the PORT's own streets (3.30 L2, 2026-09-22): without them the logistics and military regions make no street at
    # all ("meets one road" -- only the ring touches them). futo_dori runs down the container terminal's west side
    # (the terminal is x 0..218); butsuryu_dori is v15's logistics street (drawn at z 1150, laid at 1230 so it clears
    # the Wangan's port-strip deck at 1128), crossing kichi_dori on its way to the base's north gate.
    # ONE road with rounded corners, not three lines: island_network turns a two-arm meeting into a joint between two
    # mouths that are not coincident, which left the corners' lanes as open ends. Its ends cross the ring, continuing
    # kichi_dori (x -500) and chuo_dori (x -160) as X junctions.
    ("futo_dori", "block", False, None),
]


def _rounded(pts, r, step=10.0):
    """A polyline with every interior corner replaced by a curve of about radius r (points every ~`step` m)."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        u = (a[0] - b[0], a[1] - b[1]); lu = math.hypot(*u); u = (u[0] / lu, u[1] / lu)
        v = (c[0] - b[0], c[1] - b[1]); lv = math.hypot(*v); v = (v[0] / lv, v[1] / lv)
        half = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))) / 2.0
        t = min(r / math.tan(half), lu * 0.45, lv * 0.45)
        p0 = (b[0] + u[0] * t, b[1] + u[1] * t)
        p1 = (b[0] + v[0] * t, b[1] + v[1] * t)
        n = max(2, int(t * (math.pi - 2 * half) / step))
        for k in range(n + 1):                       # a quadratic through the corner, close to the arc at these sizes
            f = k / n
            out.append(((1 - f) ** 2 * p0[0] + 2 * (1 - f) * f * b[0] + f * f * p1[0],
                        (1 - f) ** 2 * p0[1] + 2 * (1 - f) * f * b[1] + f * f * p1[1]))
    out.append(pts[-1])
    return out


PORT_LOOP = _rounded([(-500, 1062), (-500, 1230), (-160, 1230), (-160, 1112)], 45.0)
NEW_ROADS_GODOT = [(n, pr, how, PORT_LOOP if pts is None else pts) for n, pr, how, pts in NEW_ROADS_GODOT]


def pre_redo_lines():
    """The pre-redo arterials as polylines by BASE name (a road and its `__n` continuations joined in chain order)."""
    r = json.load(open(PRE_REDO))
    pts = {p["uid"]: p for p in r["points"]}
    by = {}
    for rd in r["roads"]:
        base = rd["name"].split("__")[0]
        by.setdefault(base, []).append(rd)
    out = {}
    for base, rds in by.items():
        segs = [[tuple(pts[u]["pos"][:2]) for u in rd["points"]] for rd in rds]
        line = segs.pop(0)
        while segs:                                   # join the continuation whose end meets this line's end
            for k, s in enumerate(segs):
                if math.dist(s[0], line[-1]) < 1.0:
                    line += s[1:]
                elif math.dist(s[-1], line[0]) < 1.0:
                    line = s[:-1] + line
                elif math.dist(s[0], line[0]) < 1.0:
                    line = list(reversed(s))[:-1] + line
                elif math.dist(s[-1], line[-1]) < 1.0:
                    line += list(reversed(s))[1:]
                else:
                    continue
                segs.pop(k)
                break
            else:
                raise ValueError("%s: a continuation does not meet the chain" % base)
        out[base] = line
    return out


SNAP_MARGIN = 60.0
SNAP_CENTRE = (200.0, 100.0)       # record: the island's middle, which a shore point is walked toward


def snap_in(p, land_z, margin=SNAP_MARGIN):
    """Walk a record point toward SNAP_CENTRE until it stands on land with `margin` of land toward the sea."""
    def dry(a, b):
        v = land_z(a, b)                 # (0.0 is dry land: never `or` a height)
        return v is not None and v > -0.2
    x, y = p
    for _ in range(300):
        if dry(x, y):
            dx, dy = x - SNAP_CENTRE[0], y - SNAP_CENTRE[1]
            L = max(1.0, math.hypot(dx, dy))
            if all(dry(x + dx / L * k, y + dy / L * k) for k in (margin * 0.5, margin)):
                return (x, y)
        dx, dy = SNAP_CENTRE[0] - x, SNAP_CENTRE[1] - y
        L = max(1.0, math.hypot(dx, dy))
        x, y = x + dx / L * 10.0, y + dy / L * 10.0
    return (x, y)


def arterial_lines(land_z=None):
    """[(name, preset, deformed_new, [(x, y) record])]: the final plan's arterials."""
    out = []
    for base, line in sorted(pre_redo_lines().items()):
        if base.startswith(DROPPED):
            continue
        dense = []
        for a, b in zip(line, line[1:]):
            dense += _dense(a, b)[:-1]
        dense.append(line[-1])
        out.append((base, PRESET_OF.get(base), True, [deform(x, y) for x, y in dense]))
    out += trunk_lines()
    for name, preset, how, pts in NEW_ROADS_GODOT:
        p = [deform_godot(x, z) for x, z in pts] if how is True else pts
        r = g2r(p)
        if how == "snap" and land_z is not None:
            r = [snap_in(q, land_z) for q in r]
        out.append((name, preset, how, r))
    return out


# ------------------------------------------------------------------ the trunk grid (3.13 step 3), as arterial lines
#: The trunk grid used to be its own generator (`island_trunk_grid.py`) that CUT the arterials it met by NAME
#: (rinkai_dori / nogyo_michi / chuo_dori / hama_dori). hama_dori is gone (the coastal ring replaced it) and the builder
#: joins lines end to end, so names are no longer stable enough to cut by. The grid is simply more lines: the builder
#: makes every crossing a junction and trims the stub past the bounding road. Drawn in PRE-redo coordinates (the
#: generator's own), a little past the roads they end on, and deformed like everything else.
TRUNK_NS = (("nishi_hondori", 400.0), ("naka_hondori", 725.0), ("higashi_hondori", 1100.0))
TRUNK_EW = ("ekimae_dori", 250.0)
TRUNK_Y = (-260.0, 960.0)          # pre-redo record y range of the N-S trunks (rinkai_dori .. nogyo_michi, + a stub)
TRUNK_X = (-200.0, 1700.0)         # ... and the x range of ekimae_dori (chuo_dori .. the east coast, + a stub)
PRESET_OF = {"yamate_dori": "trunk"}   # a pre-redo arterial carried over on another section


def _dense(a, b, step=20.0):
    n = max(1, int(math.dist(a, b) / step))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def trunk_lines():
    out = []
    for name, x in TRUNK_NS:
        out.append((name, "trunk", True, [deform(*p) for p in _dense((x, TRUNK_Y[0]), (x, TRUNK_Y[1]))]))
    name, y = TRUNK_EW
    out.append((name, "trunk", True, [deform(*p) for p in _dense((TRUNK_X[0], y), (TRUNK_X[1], y))]))
    return out


# ------------------------------------------------------------------ the block streets (island_streets.py)
#: name, box (x0, y0, x1, y1) RECORD, preset, x lines, y lines (a float = at that spacing). The pre-redo boxes moved
#: with the plan, plus the districts the final plan fills (v3-v7): residential north on 120 m, residential SW on 110 m
#: (one row of houses a side needs more streets), industry and port logistics on big 200 / 220 m blocks, the suburb.
STREET_REGIONS = (
    # TIGHT BLOCKS (user, 2026-09-26: "no large vacancy ... tight rectangle blocks"): 64 m deep in the city (two
    # frontage rows of 11-30 m buildings back to back, the 4 m back lane between), 44 m in the housing (two houses).
    # ONE ROW EACH SIDE (user, 2026-09-26: "each building facing a street ... in rectangular blocks"): the city's
    # blocks are 150 x 76 m -- two frontage rows back to back with the 路地 passages reaching the middle, which is the
    # fire and delivery access into the block -- and the housing's 110/120 x 52 m, two houses back to back (Japan's
    # 接道義務: every plot on a street, fire access from the street side). A 150 m square left a car park of empty
    # ground in every block's middle.
    ("city", (-85.0, -282.0, 1250.0, 410.0), "block", 150.0, 64.0),
    # residential SW is the HOUSING only (2026-09-26): its box overlapped industry's and was planned first, so its
    # 110 m residential grid took the industry's ground and crowded out industry's own 200 m lines (12 -> 0 streets).
    # A sixth element is a region's HOLES (record boxes): a line running into one is CUT there, like a site, so each
    # piece keeps its end on an arterial (splitting the box instead lost the west's lines: 105 -> 50 streets).
    ("sw", (-1560.0, -1150.0, -100.0, -280.0), "block", 110.0, 44.0, ((-1000.0, -1040.0, 280.0, -640.0),)),
    # the 準工業 district's part of the old industry box (user, 2026-09-26): block streets, a size between the
    # housing's and the heavy industry's; the Blue line runs down x -665 through it (streets cross it at 踏切)
    # boxes reach NORTH past the south-west grid's y -603 street / to wangan_dori: their other anchor was the ring road,
    # which is the raised dike now and not a crossing (island_dike), so a line needs a street north as well as the 側道
    ("koba", (-1000.0, -1040.0, -300.0, -590.0), "block", 130.0, 64.0),
    # VACANT BLOCKS (user, 2026-10-03: "add more streets around vacant blocks"): koba_w and city_n hang their lines off
    # the AUTHORED frames island_core_streets adds there (`koba_waku_w*`, `c1_naka_yoko*`); before those, every line
    # in these blocks met ONE road and was dropped (no dead ends). Explicit line sets, boxes reaching the roads.
    # koba_w: the west industrial block, either side of the Blue line (x -800): north-south lines from nishi_cho_413
    # (y -413) down onto the authored U (y -655), one each side of the track
    # (2026-10-03, the vacancy re-scan) the lines sit in the MIDDLE of the two empty blocks either side of the Blue
    # line / Residential station (x -800, y -419..-603): x -910 (block x -1000..-820) and x -650 (block x -780..-500);
    # at -870 / -700 one was dropped and the other hugged the track, leaving ~8 ha with no street
    ("koba_w", (-1080.0, -800.0, -480.0, -400.0), "block", (-910.0, -650.0), ()),
    # (Residential station's 商店街 is the x -650 line's north half, koba_machi_w_650: island_buildings.STREET_MIXES)
    # city_n: inside C1's north half, between yamate_dori (y ~295) and c1_naka_yoko (y 465); the tower site stands at
    # (680, 365), x 623..737
    ("city_n", (250.0, 270.0, 1000.0, 490.0), "block", (360.0, 800.0), ()),
    # THE FARM IS JAPANESE PADDY SECTIONS (圃区, user 2026-09-25): 300 m east-west x 100 m north-south between farm
    # roads, laid round FARM STATION (1110, 1320, the Main line's terminus). The station road is the east-west line
    # y 1320, ending in a T on the station-front road x 1080; the 2 x 2 core is x 510..1080 x y 1220..1420, with a
    # ring of 1 x 1 sections round it. No north-south road at x 1110: the Main line runs there at grade. NOTE for the
    # rail build: the station's platform box straddles the coast ring (it crosses x 1110 at y ~1317).
    # The farm's pond (ため池, x 620..920 x y 980..1140) lies in one tall section, y 920..1220: no row crosses it, and
    # the x 810 road is two regions (south of it, north of it), because the planner drops a line that crosses water.
    # The west farm road (x 510, nishi_dori -> kaigan_machi) is its own region and comes FIRST: a new line may only
    # end on another new line inside that line's own extent, and the east-west lines meet no existing road at their
    # west end, so the road they end on must already exist when they are planned.
    # x 1080 is the STATION-FRONT road (駅前通り), just west of the track and clear of its corridor: the middle road
    # y 1320 ends on it in a T right in front of Farm station, which is the user's sketch ("=====farm station").
    # (2026-09-26, fifty-sixth session) the west road x 510, the station-front road x 1080 and the 農道 along the
    # dike's foot are ONE authored road now, `nodo_waku` (island_core_streets.py): since the ring became the dike no
    # farm line could end on it, and the whole grid was dropped. farm_w is gone; the rows end on the frame's legs, and
    # the old 1395 row is dropped (the frame's north leg runs 23 m north of it at x 1080). The station-front leg is at
    # x 1045 since 2026-09-28 (clear of the stations' buildings and car parks).
    ("farm", (400.0, 700.0, 1090.0, 1570.0), "farm", (), (920.0, 1220.0, 1320.0)),   # ends at the station-front road
    ("farm_s", (700.0, 700.0, 1100.0, 925.0), "farm", (810.0,), ()),
    ("farm_n", (700.0, 1215.0, 1300.0, 1570.0), "farm", (810.0,), ()),
    # residential north lies between C1 and the farm arterial -- where the C1 diamond comes down, so the ramps' band
    # (x 180..1020) is left out: a street under a descending ramp had 4.5 m of clearance
    ("north", (-330.0, 560.0, 180.0, 810.0), "lane", 120.0, 44.0),
    ("north_e", (1020.0, 560.0, 1250.0, 810.0), "lane", 120.0, 44.0),
    # (2026-10-03, the vacancy pass) 200 -> 140 m: a 200 m plot left ~100 m of empty ground behind every factory.
    # The east-west lines are listed, clear of y -650, where Industry station's access road meets kojo_waku
    ("industry", (-300.0, -1040.0, 280.0, -410.0), "block", 140.0, (-950.0, -810.0, -540.0)),
    ("logistics", (-820.0, -1540.0, -60.0, -1040.0), "block", 220.0, 220.0),
    # ONE ROW A SIDE (user, 2026-09-26): a 150 m square is two frontage rows and a car park of nothing in between
    # (2026-10-03) from x 1000: the suburb's west is the station front (Suburb station's access T on wangan_dori at x 929)
    # and kogai_michi; the loop inside the dike (island_suburb_dike.py) is authored
    # ...and not inside the loop: the water resort (150 x 70) stands there (a hole, record box)
    ("suburb", (1000.0, -1060.0, 1300.0, -330.0), "block", 150.0, 64.0, ((1000.0, -1000.0, 1130.0, -690.0),)),
    # THE VACANCY PASS (user, 2026-10-03: "reduce large vacancy behind buildings ... add streets"): single lines found
    # by a search over the deep-vacancy pockets (flat land > 48 m from any street) with this planner's own rules, each
    # the line that served the most empty ground; planned last, against everything above
    ("fill_c1w", (-254.0, 74.0, 506.0, 850.0), "block", (), (410.0,)),          # inside C1's west curve
    ("fill_c1w2", (-254.0, 218.0, 506.0, 970.0), "block", (75.0,), (620.0,)),
    ("fill_c1sw", (-266.0, -662.0, 474.0, 30.0), "block", (15.0,), (-345.0,)),  # C1's south-west, chuo_dori side
    ("fill_wek", (-894.0, -898.0, -254.0, -170.0), "block", (-595.0,), ()),     # Residential station's west front
    ("fill_r390", (-560.0, -640.0, -300.0, -280.0), "block", (-390.0,), ()),     # the sw grid's x -390 line, when a site cut it short
)
#: RESERVED GROUND (PLAN.md 3.30 L3/L4, user 2026-09-26: "the land-planning portion"): Godot-frame boxes
#: (x0, z0, x1, z1) that no generated BUILDING may stand on -- their contents are placed later, by region, once
#: their models exist. Streets are not kept out (a park may have a road through it; the base has its own).
RESERVES = (
    # the COMPACT air/naval base (user, 2026-09-28): the core at the platform's south-west corner, its gate on the east
    # side facing the gate road (kichi_mon_michi, x -460 -- REMOVED 2026-10-05: the gate is on the north fence), the runway along the platform's own south band abutting the
    # core's apron, the one pier (with its berth) at the core's west edge -- everything within ~300 m
    # (2026-09-29 night: the base core compressed NORTH to z 1440 and the runway pulled up onto the platform's south
    # quay line, the container terminal's south edge z 1488 -- one fence round the whole area, tools/building_kit/
    # site_military.py)
    ("military_base", (-760.0, 1250.0, -475.0, 1444.4)),
    # the runway lies right along the base's apron (user, 2026-09-29: "pull the runway back east toward the fence, so a
    # jet reaches it from the hangar without crossing open ground"): its east end in line with the base's east fence
    # (x -475), on the platform's own south band, its west half on the reclaimed strip (island_reshape)
    ("military_airfield", (-1015.0, 1443.0, -475.0, 1491.0)),
    ("military_pier", (-1020.0, 1301.0, -740.0, 1371.0)),     # the pier (z 1300..1350) + the ship's berth south of it
                                                               # (centred on z 1336: the MilitaryPier composite's frame)
    # the Wangan's west TERMINAL (NEXT PASS step 2, 2026-10-02): its junction and turnaround loop on a reclaimed platform
    # (island_reshape.WANGAN_TERMINAL_FILL) -- no building inside the loop
    ("wangan_terminal", (-1000.0, 1100.0, -820.0, 1225.0)),
    # the MARINA + FERRY TERMINAL (user, 2026-10-03: the yacht "reserve ground now" and the ferry terminal): the cove
    # strip OUTSIDE the dike west of the Wangan terminal (land at ~5.6 m, deep water to -17 m at its south edge). Ground
    # only: no road reaches it yet (the dike crest is the ring road at ~13 m) -- an access ramp or a dike gap comes with
    # the yacht / terminal models
    ("harbour_marina", (-1170.0, 990.0, -1005.0, 1052.0)),
    # the expressway PARKING AREA inside the Wangan terminal loop (the Daikoku shape: a PA inside a loop junction;
    # third review, user 2026-10-03): car meets, race starts, a police checkpoint -- reached from the loop road the way
    # every car park meets its street, so it needs no ramp of its own
    ("wangan_pa", (-970.0, 1142.0, -866.0, 1196.0)),
    # the airport's AIR-CARGO shed (the third review: a mission building on the airport island, cargo theft): the
    # pocket between the forecourt (to z 1727) and the apron (from z 1784), west of kuko_service; its docks face the
    # apron (south)
    ("airport_cargo", (1050.0, 1730.0, 1120.0, 1780.0)),
    # the Bay Quarter's waterfront park and its FERRIS WHEEL (user, 2026-09-29): the gulf's east shore between ring_kita
    # (z 672) and the suburb loop's west leg (x 886, the resort hotels beyond) -- a bayside leisure park beside the
    # seaside hotels, Odaiba's Palette Town / Kasai Rinkai Park precedent. (It used to be drawn over x 760..1000, z 700..960,
    # which the loop and hotels 1-2 were later laid through.)
    # (2026-10-02 night, the waterfront review: the Suburb WB entrance `shuto_sb_on` runs through the old box, z 690..890;
    # the park moved SOUTH of it, onto the plain that runs on to the beach at z ~960 -- its wheel faces the open sea)
    # (2026-10-03: the dike's suburb stretch now runs down x 945 beside it, so the park is OUTSIDE the dike, beach
    # leisure, reached on foot over the dike; no road reaches it)
    # (S13 D3, user 2026-10-13: "yes, the current decision is good"): 20 m off the NORTH edge (z 798 -> 818) -- the
    # Suburb entrance shuto_sb_on passed over x 760..805, z 798..817, the plot's north-west lawn
    ("waterfront_park", (760.0, 818.0, 870.0, 958.0)),
    # the resort hotels (history: inside the old suburb loop, then 2026-10-02 night on the beach front OUTSIDE the dike).
    # 2026-10-03 (user: "homes behind the dike, only beach leisure outside"): the ring swings south round the suburb
    # (tools/island_suburb_dike.py), so the hotels stand INSIDE it, in the 68 m band between the suburb loop's bottom leg
    # (kogai_loop, z 984) and the dike's land-side toe (~z 1055) -- their street side north, the sea over the dike. Two fit
    # the band (190 m); the third was dropped.
    ("resort_hotel_1", (980.0, 994.0, 1060.0, 1056.0)),
    ("resort_hotel_2", (1070.0, 994.0, 1150.0, 1056.0)),
    # THE LOGISTICS HUB (user, 2026-09-28: "fill the empty middle with a logistics park ... restrict to 1, or 2 if it
    # makes sense, for level design"): the port platform's middle, between the base's gate road (kichi_mon_michi, x -460)
    # and the container terminal, south of the port road (kichi_dori, z 1230). ONE truck terminal west of the logistics
    # road (butsuryu_michi, x -280) and ONE distribution centre east of it, both gated onto it. Street sites.
    ("logistics_truck_terminal", (-445.0, 1245.0, -295.0, 1470.0)),
    ("logistics_distribution", (-265.0, 1245.0, -25.0, 1470.0)),
    ("lighthouse", (1350.0, -1320.0, 1430.0, -1260.0)),       # the north-east headland
    # the 道の駅 (roadside station) on the north coast road. S16 C (2026-10-14): RE-SITED from the farm coast (385, -1720,
    # 475, -1640) to the NORTH CAPE's reclaimed terrace (island_reshape.CAPE_TERRACE), seaward of the crossroads where
    # kita_touge leaves kaigan_dori -- the 峠's foot, a race start / finish, a lookout over the north sea; one 道の駅 on the
    # north coast, not two 700 m apart (they stand ~10+ km apart in Japan, RECALLED). The kind is kept (user rule: a site
    # may move if it stays present and fronts a road).
    ("michi_no_eki", (-295.0, -2092.0, -145.0, -2026.0)),
    # 2026-09-28 (the step 7 rebuild): ground kept for what the batch did not author, so filling it later needs no road
    # rebuild. Each is already reached by a road: the ring / dike side road, the airport's own loop roads, yamate_dori.
    # (The bay MARKET needs no reserve: the gulf head between wangan_dori and the ring's dike is one 84 m block fronting
    # both, and Fish Market station's 駅前 row already lines it with shop-houses -- the market's types replace them there.)
    # (2026-10-02 night, the waterfront review: the Wangan's deck and both Suburb ramps crossed the old box's east part,
    # x 585..716 -- FishMarket stood under the viaduct; the market keeps the west part, clear of all three)
    # (PLAN S11 P12, 2026-10-13: the Japanese layout) the whole yard between the dike's sea toe (z 712) and the new
    # straight quay (z 780, island_reshape.MARKET_QUAY), from the filled west wedge (x 300) to the yard's east end
    # (x 610, where the Wangan's viaduct takes over). It was (405, 705)-(570, 775). The truck ramp ichiba_michi comes
    # down inside its north edge and the car-park terrace stands in its north-west corner: both are roads / sites of
    # their own (island_site_access), and library_civic.fish_market lays the piece out round them.
    # (S13, 2026-10-13: the quay moved south to z 808 for the yard's lane loop, island_reshape.MARKET_QUAY; the west
    # edge to x 290, the coast road's embankment, where the public car park and the 物揚場 are)
    # (S15, 2026-10-14: the quay to z 842 / 848, island_reshape.MARKET_QUAY_S, the moved Wangan south of it; the
    # VISITORS' strip east of the yard -- 直売所 + 食堂 and their lot north of the through link -- held too)
    ("fish_market", (290.0, 712.0, 610.0, 848.0)),
    ("fish_market_visitors", (725.0, 715.0, 890.0, 766.0)),
    # the airport's AIRSIDE (user, 2026-09-29: the runway "on a different side from the bridge"): behind the terminal,
    # the apron against its airside face (boarding bridges to z 1811.6), then the taxiway and the 540 x 45 m runway
    # along the island's SOUTH edge (the island reaches z 2040 for it, island_reshape AIRPORT_SOUTH). It stood between
    # the bridge's landing and the terminal, under the spur and the rail.
    # the airside reaches north to the terminal's airside face (z 1785.9) so the apron runs under the gate bridges (user,
    # 2026-09-29: the planes stood 8.6 m of open ground from the gates and 21 m from the runway)
    ("airport_airfield", (940.0, 1784.0, 1480.0, 1974.0)),
    # the airport's FORECOURT (user, 2026-09-29: "forecourt like central station"): the one-way loop kuko_rotary
    # (island_expressway FORE_BOX) with its lanes and footways, between the Airport station's west wall and the
    # terminal's curb canopy; the AirportForecourt composite dresses it (tools/building_kit/site_airport_forecourt.py)
    ("airport_forecourt", (1045.0, 1611.0, 1233.0, 1727.0)),
    ("broadcast_centre_parking", (728.0, -345.0, 792.0, -297.0)),  # the Tower's car park on yamate_dori, beside its east
                                                               # face (B9 kerb ramp); it has no car park of its own yet
    # THE CENTRAL STATION'S 駅前広場 (user, 2026-09-28): the ground between ekimae_dori (z -100, its paved edge -118.5)
    # and the station's south face (z -180), from naka_hondori's paved edge (x 619) to higashi_hondori's (x 956). The
    # one-way ekimae_rotary (island_core_streets) runs through it; everything else is the CentralForecourt composite
    # (the multistorey car park, the bus berths under a covered walk, the taxi rank, the koban, bike parking, the clock
    # island). A street site, and a LEVELLED site (island_sites.reserve_sites): the block ground is filled to footway
    # level round the rotary.
    ("central_forecourt", (619.0, -180.0, 956.0, -119.0)),
    # THE WEST SUB-CENTRE STATION'S 駅前広場 (S16 E [I5], user 2026-10-14: "B. Bays + plaza"): between the station's east
    # face (record x -736, the Blue line at BLUE_WEST_X -750), its front street y -413 (paved edge y -420), the 商店街 x
    # -650 (paved edge ~-657) and the station mall (north edge y -500). Bus stops + taxi rank on the street's kerb, a
    # plaza; the WestForecourt composite dresses it (tools/building_kit/site_west_forecourt.py). No rotary: two mouths
    # on the front street overlap its 踏切 and the x -650 junction.
    ("west_station_forecourt", (-734.0, 421.0, -662.0, 497.0)),
)
#: Streets the plan REMOVES by hand (user, 2026-09-22, marked on `reference/island_plan_v16_2026-09-22-remove-too-small-
#: street-blocks.png`): lines that cut a block too small for a building to be placed simply, so the grid stays larger
#: and more uniform. (region, axis, the line's final coordinate -- the number in its street name), matched to 1 m.
STREET_DROP = (
    ("city", "x", 342.0),        # machi_342, between nishi_hondori and the ring's west side
    ("city", "x", 1032.0),       # machi_1032, beside higashi_hondori
    ("sw", "x", -1100.0),        # nishi_machi_1100, the westmost N-S residential street
    ("sw", "x", -440.0),         # nishi_machi_440, beside kichi_dori (x -500)
    ("industry", "x", -200.0),   # kojo_michi_200, a one-block stub
    ("koba", "x", -850.0),       # koba_machi_850: [I7] shiokaze_dori runs on its line (S16 E)
    ("sw", "x", -1050.0),        # nishi_machi_1050: it met the factory ladder's two legs on their dike ramps (S16 E [I6])
    ("koba", "x", -780.0),       # koba_machi_780: with the Blue line at x -750 its junctions on the koba legs stood 18 m
                                 # from the 踏切 (< 20); the 100 m block between shiokaze_dori and the track needs none
)
STREET_NAMES = {"city": ("machi", "cho"), "sw": ("nishi_machi", "nishi_cho"), "farm": ("hata_michi", "hata_yoko"),
                "farm_w": ("hata_michi_w", "hata_yoko_w"), "farm_s": ("hata_michi_s", "hata_yoko_s"), "farm_n": ("hata_michi_n", "hata_yoko_n"),
                "north": ("kita_machi", "kita_cho"), "north_e": ("kita_machi_e", "kita_cho_e"), "industry": ("kojo_michi", "kojo_yoko"),
                "koba": ("koba_machi", "koba_cho"), "koba_w": ("koba_machi_w", "koba_cho_w"),
                "city_n": ("machi_n", "cho_n"),
                "fill_c1w": ("machi_w", "cho_w"), "fill_c1w2": ("machi_w2", "cho_w2"), "fill_c1sw": ("machi_sw", "cho_sw"),
                "fill_wek": ("ekimae_machi_w", "ekimae_cho_w"), "fill_r390": ("nishi_machi_f", "nishi_cho_f"),
                "logistics": ("butsuryu_michi", "butsuryu_yoko"), "suburb": ("kogai_machi", "kogai_cho")}


# ------------------------------------------------------------------ the expressway (island_expressway.py)
#: C1 and its interchanges, the pre-redo numbers moved with the plan (x - 125 in the core; y by the band compress):
#: corners (150, 40)..(1300, 720) -> (25, -110)..(1175, 570); the JCT x 780 -> 655; the diamond on naka_hondori x 725
#: -> 600, its junctions y 615 / 815 -> 465 / 665, its ramp stations x 345 / 465 / 985 / 1105 -> -125.
C1_CORNERS = [(25.0, -110.0), (1175.0, -110.0), (1175.0, 570.0), (25.0, 570.0)]
C1_SIDE_CUT_Y = 150.0              # C1 is cut into roads half way up each side (pre-redo y 300)
C1_SOUTH_CUT_X = 775.0             # ...and on its south side between the W and E JCTs' aux lanes (the ring starts here)
# THE FOUR-POINT C1 (PLAN.md "NEXT", user + review 2026-09-29 night): one access point per side --
#   N a TIGHT diamond onto naka_hondori (the ramps hug the viaduct and land right beside it),
#   W the Wangan JCT (all four movements, the Wangan's north leg up beside the rail corridor),
#   E the airport JCT (the spur straight down x 1250 onto the Rainbow Bridge's upper deck),
# and NO south diamond: C1's south side (x 205..995, 790 m) carries both JCTs' ramp pairs (W: BWD exit + FWD
# entrance, x 300..760; E: FWD exit + BWD entrance, x 790..910), and a diamond's four ramps need ~2 x 265 m more.
# All x / y below are the RECORD frame (x east, y north = -Godot z). C1 runs COUNTER-clockwise in the record: FWD is
# the inner carriageway (eastbound on the south side), BWD the outer (westbound on the south side).
#
# the N TIGHT DIAMOND (each end: an exit on one carriageway and an entrance on the other 10 m apart, one ramp per
# station, so both carriageways widen over the same stretch; the ramps run parallel to C1 and land ~45 m off it)
DIAMOND_X = {"d_bwd_off": 295.0, "d_fwd_on": 305.0, "d_bwd_on": 895.0, "d_fwd_off": 905.0}   # 40 m further out
# (2026-10-01 review: the entrances climbed 11 m at 7.3 %; 40 m more of ramp takes them to ~6 %)
DIAMOND_ROAD = ("naka_hondori", 600.0)
DIAMOND_J = (533.0, 607.0)         # its two junctions on naka_hondori (inside C1, outside C1), C1 at y 570: TIGHT (item
                                   # 2), 37 m off C1 -- each pad's near mouth (MOUTH 26) just outside C1's deck edge
# the W JCT (the Wangan)
W_LEG_X = 370.0                    # the Wangan's north leg: a divided road up x 370, east of the rail (x 185 / 205), the
                                   # Bay station's box (x <= 250) and nishi_hondori (x 275), west of Fish Market (x 424)
W_JOINT_Y = -230.0                 # where the leg parts into its two one-way C1 ramps (a joint)
W_BWD_ON_X = 300.0                 # leg NB -> C1 BWD (westbound, outer): merges from the south, 95 m before the SW arc
W_BWD_OFF_X = 520.0                # C1 BWD -> leg SB: leaves to the south and swings down onto the leg's SB half
W_FWD_ON_X = 650.0                 # leg -> C1 FWD (eastbound, inner): a flyover off the leg NB, over the leg and C1
W_FWD_OFF_Y = 250.0                # C1 FWD -> leg: exits on C1's WEST side (heading south, inside), a flyover
                                   # diagonally over the SW corner and the leg, onto the leg's SB half from the east
W_FLY_Z = 18.5                     # both flyovers: over C1 (11) and over the leg (12.5) by 5.5 m + margin
W_LEG_Z = 12.5                     # the leg: over ring_kita (the dike, 6.4 m at y -672) by 5.5 m
# the E JCT (the airport)
E_JOINT_Y = -45.0                  # where the spur (x 1250) parts into its two one-way C1 ramps (a joint). As far north
                                   # as E2's diagonal allows (user, 2026-09-30: "merge the two ramps as fast as
                                   # possible"): E1 comes straight down onto the spur's line, no curve back in
E_BWD_OFF_Y = 230.0                # C1 BWD (southbound on the east side, outer) -> the spur SB: out east and straight
                                   # down x 1250.5 (over ring_kita, the dike at x ~1235, 6.4-8 m)
E_BWD_ON_X = 910.0                 # the spur NB -> C1 BWD (westbound on the south side): merges from the south
E_FWD_OFF_X = 900.0                # C1 FWD (eastbound, inner) -> the spur: a flyover east over the SE corner and the
                                   # SB ramp, round onto x 1268 and down onto the spur's SB half from the east
E_FWD_MERGE_Y = -375.0             # ...where it merges
E_JOINT_Z = 14.0                   # the joint: the two C1 ramps cross ring_kita (7-8 m on the dike) by 5.5 m
E_FLY_Z = 20.0                     # the flyover: over the SB ramp (~13-14 m) and C1 by 5.5 m + margin


# ------------------------------------------------------------------ THE EXPRESSWAY REDESIGN (PLAN.md item 1, 2026-09-30)
#: C1's south side carries ONLY the S diamond; the Wangan meets C1 on its WEST side (through a connector over
#: chuo_dori's median), the airport spur on its EAST side. Record frame. C1's cuts (joints): the ring starts at the
#: first; each run carries at most one ramp per carriageway.
C1_CUTS = [(600.0, -110.0), (1175.0, 90.0), (1122.28, 517.28), (600.0, 570.0), (77.72, 517.28), (77.72, -57.28)]

#: the S diamond (record x of each ramp station on C1's south side): the INSIDE pair lands at a junction on
#: naka_hondori (S_DIAMOND_IN_Y); the OUTSIDE pair are slip ramps T-ing into rinkai_dori (R6: naka_hondori starts 64 m
#: south of C1, at its own T on rinkai_dori, so an outside junction on it cannot exist)
S_DIAMOND_MARKS = {"s_fwd_off": (295.0, -110.0), "s_bwd_on": (305.0, -110.0),
                   "s_fwd_on": (895.0, -110.0), "s_bwd_off": (905.0, -110.0)}
#: The S diamond lands on naka_hondori like the N one (user, 2026-09-30): eki_minami_dori's stretch from its y -230
#: junction north through C1 was removed from the arterials input, so nothing passes under the west pair.
S_DIAMOND_W_ROAD = ("naka_hondori", 600.0)
#: (review 2026-09-30: the N diamond's own x, so the south pair gets the same length to descend -- it was 8.5 % and
#: 4.1 m over eki_minami_dori at 365/375)
#: the S diamond is the N diamond's MIRROR (user, 2026-09-30, option 3 + "aligned, more symmetric"): four ramps paired
#: the same distance each side of naka_hondori (an exit and an entrance 10 m apart at each end), all landing on
#: naka_hondori -- the inside pair at a junction S_DIAMOND_IN_Y, the outside pair at S_DIAMOND_OUT_Y. naka_hondori is
#: long enough outside C1 for that since rinkai_dori was moved ~50 m south (tools/island_rinkai_south.py, one-shot).
#: The west pair sits at 365/375, not the N diamond's 335/345: the inside exit must still be 5.5 m over eki_minami_dori.
S_DIAMOND_IN_Y = -73.0             # 37 m off C1 (y -110), as the N diamond
S_DIAMOND_OUT_Y = -147.0
#: the W JCT on C1's WEST straight (x 25, y 70..390): the connector's NB half merges into C1 BWD (northbound, the
#: outer carriageway, from its left); C1 FWD (southbound, inner) leaves inside and flies over C1 onto the connector's
#: SB half
W1_ON_Y = 210.0
W2_OFF_Y = 360.0
#: the E JCT on C1's EAST straight (x 1175, y 70..390): C1 BWD (southbound, outer) -> the spur (E1, `E_BWD_OFF_Y`); the
#: spur's NB half flies over C1 into C1 FWD (northbound, inner, from its left)
E2_ON_Y = 360.0      # the airport -> C1 ramp crosses C1's EAST STRAIGHT (y ~95), never its SE corner
E2_FLY_Z = 17.5
#: THE WANGAN, phase 1 (R1: long sweepers, not a ruler; user 2026-09-30: "the Wangan to airport lane is built later,
#: completely outside C1"): its WEST END (a terminal loop since 2026-10-02, WG_LOOP_*), then the coast east to a quarter-turn north (WG_TURN_*) onto chuo_dori's median, over it
#: to C1's west side (the W JCT). WG_CENTRE's vertices east of the turn are phase 2's line (PHASE2_CORRIDOR below
#: holds that ground); the build takes only those west of the turn. Record frame.
#: (WG_CENTRE / WG_RADII are phase 1's line, read by nothing since the complete Wangan: WG_MAIN below is the alignment.)
WG_CENTRE = [(-1030.0, -1030.0), (-940.0, -1113.0), (-700.0, -1128.0), (-350.0, -1126.0), (-60.0, -1112.0),
             (150.0, -1060.0), (370.0, -840.0), (470.0, -805.0), (640.0, -795.0), (780.0, -655.0),
             (930.0, -505.0), (1060.0, -500.0)]
WG_RADII = [0.0, 60.0, 600.0, 1500.0, 1500.0, 500.0, 160.0, 200.0, 200.0, 150.0, 120.0, 0.0]
WG_Z = 12.0                 # the deck along the coast
WG_TURN_Y = -1127.0         # the turn's corner, on the coast line, below chuo_dori
WG_TURN_R = 100.0           # the quarter-turn north onto chuo_dori's line (a 50 km/h class JCT curve)
#: THE COMPLETE WANGAN (user, 2026-09-30, second session: "make the Wangan from the airport spur to the west coastline
#: the main line, the connection to C1 west a ramp"). The MAINLINE runs from its west-end terminal loop along
#: the coast, passes over Harbour station (lifted, see WG_HARBOUR_*), up the waterfront corridor and ends at a
#: joint near the spur (WG_EAST_JOINT), where it parts into T1 (-> the spur SB, the airport) and T2 (the spur NB ->).
#: The connector to C1 west is now its own road from a joint at CONN_J_Y, fed by Y1 (Wangan EB ->) and feeding Y2
#: (-> Wangan WB, a flyover); Y3 (Wangan WB -> it) and Y4 (it -> Wangan EB) complete the four movements. Record frame.
#: J0 (2026-10-01, the lane-split T): the mainline ENDS on the straight waterfront diagonal and each carriageway splits
#: lane by lane into four one-lane ramps (分岐 / 合流), NW -> SE: T3 | T1 | median | T4 | T2 (see t_split)
WG_J0 = (880.0, -530.0)
#: THE BAY JOG IS TWO ARCS AND ONE STRAIGHT (PLAN S11 P12-5, user 2026-10-13: "can move the wangan further south", "have
#: curve as much as possible, and remove s wiggle"). The line up the waterfront (45 deg through (150, -1060)) and the line
#: into J0 (45 deg through (780, -655)) are PARALLEL, 159 m apart, so the mainline must turn right and then left between
#: them: a reverse curve is the least it can be. It was three corners ((370, -840) (470, -805) (640, -795), R 200 / 150 /
#: 150: two right turns and a left, a kink at x 470); it is two corners now, WG_BAY_W on the first line and WG_BAY_E on the
#: second, joined by one tangent heading 3.8 deg north of east: R 200 right, 91 m straight (x 454..545), R 200 left. That
#: tangent lies 16-20 m further SOUTH over x 450..580 than the old line: the water in front of the fish market's quay
#: (z 780) is 29 m to the deck's edge where it was 9, and the two Suburb gores stand on a straight.
#: S15 (user, 2026-10-14: "Move Wangan ~75 m south"): the whole jog slid 75 m south-west along BOTH 45 deg lines (each
#: corner (-75, -75)), so the arcs, the straight's 91 m and its 3.8 deg heading are unchanged and only its place moves:
#: the straight now runs at y ~-895..-901 (x 379..470) over open water, south of the fish market's quay (z 842 / 848),
#: and the mainline's piers leave the market's apron. Line 2 (into J0) is the same line, so east of x ~560 the deck
#: crosses the market's strip as before. Was (378.9, -831.1) / (620.0, -815.0).
WG_BAY_SHIFT = 75.0
WG_BAY_W = (378.9 - WG_BAY_SHIFT, -831.1 - WG_BAY_SHIFT)
WG_BAY_E = (620.0 - WG_BAY_SHIFT, -815.0 - WG_BAY_SHIFT)
WG_MAIN = [(-850.0, -1128.0), (-700.0, -1128.0), (-350.0, -1130.0), (-60.0, -1133.0),
           (150.0, -1060.0), WG_BAY_W, WG_BAY_E, (780.0, -655.0), WG_J0]
#: THE WEST END IS A TERMINAL LOOP (NEXT PASS step 2, 2026-10-02, user: "ground terminal loop"; the second independent
#: review: a west-end TURNAROUND joins the two one-way systems in BOTH directions, where a port-side PA would join only
#: one). The mainline comes down to the ground on its straight coast line and ends at WG_LOOP_J, a signalised 4-arm
#: junction on a small reclaimed platform outside the dike (island_reshape.WANGAN_TERMINAL_FILL): east the mainline, north
#: a short access road to a T on the dike road (ring_kita), west and south the two ends of a ONE-WAY turnaround loop, a
#: rounded square (WG_LOOP_BOX, corners WG_LOOP_R) laid counter-clockwise -- out west, back from the south. WB -> the
#: loop -> EB turns a car round; the access road serves the port and the west coast both ways. It replaces the west T on
#: the coast road and its R 34 bend, and the port's EB entrance (port_on), whose T stood here. Record frame.
#: (Was: the T on the west coast road at (-1170, -900) with WG_WEST_PATH's corners down the strip outside the dike.)
WG_LOOP_J = (-850.0, -1128.0)      # on the coast line WG_MAIN[1] -> WG_MAIN[2] (y -1128..-1130), so the approach is straight
WG_LOOP_BOX = (-985.0, -1210.0)    # the loop's far corner: its stations (the OUTER edge: a one-way road lays its lanes
                                   # on its left, the inside of a counter-clockwise loop) run x -985..J, y -1210..J
WG_LOOP_R = 38.0
WG_LOOP_Z = 5.75                   # the platform (the plain, 5.6) + the stamp's clearance
WG_WEST_RISE = 230.0               # the mainline climbs from the junction to WG_Z over this far (2.7 %), level by Y1's gore
WG_APPROACH = 85.0                 # the approach's last stretch, posted 50 (its own road `shuto_wangan`)
WG_MAIN_R = [90.0, 600.0, 1500.0, 1500.0, 250.0, 150.0, 200.0, 120.0, 0.0]   # S15: WG_BAY_W 200 -> 150 (see Y3_OFF_X)
#: THE LANE-SPLIT T at the spur (2026-10-01, island_expressway.t_split): T1 (Wangan EB -> spur SB) runs along J0's
#: line, turns right OVER T4, and makes ONE clockwise circle of T1_R over the spur (centre (T1_LEG_X - T1_R, T1_LOOP_Y)),
#: then straight down the spur's east side at T1_LEG_X to its merge
T1_R = 110.0
T1_LEG_X = 1264.0
T1_LOOP_Y = -545.0  # T1's circle centre (its apex T1_R north of it, west of the spur)
T1_SWAP = 190.0              # T1 runs this far along J0's line, then turns right OVER T4 (still low there)
T1_SWAP_R = 100.0
T3_STRAIGHT = 230.0          # T3 runs on along J0's line this far before its S onto the spur's west side
T4_TURN_Y = -330.0           # T4 runs down the spur's east side to here before it turns over the spur
T_HOLD = 35.0                # the EB pair (T1 + T3) stays level this far past J0 while the WB pair peels away
T_EAST_Y = -500.0            # the WB pair (T4 + T2) peels off J0 onto this line (record y), so the EB pair climbs alone
T4_NORTH_X = 1010.0          # where T4 leaves the east line north-east (under T1's lead, nearly square)
T4_RC = 120.0                # ...on this radius
T4_RF = 90.0                 # T4 turns north up the spur's east side on this radius
T2_RC = 80.0                 # T2 turns south onto the spur's west side on this radius (inside T1's loop)
#: between the container terminal (north edge y -1124: its stacks and cranes) and Harbour station there is 16 m, so
#: the mainline passes OVER the station's building, lifted to WG_HARBOUR_Z (a ground hub stands ~10 m)
WG_HARBOUR_X = 185.0
WG_HARBOUR_Z = 18.0
WG_EAST_Z = 14.0             # the mainline's height at J0 (the lane split): T1 climbs from it over T4, which stays low there
WG_EAST_RISE = 320.0
Y1_OFF_X = -600.0            # Y1, Wangan EB -> the connector: its gore (EB exit, north side; east of the west end
                             # joint by its taper; was -680)
Y2_ON_X = -500.0             # Y2, the connector -> Wangan WB: its merge (WB entrance, south side)
CONN_J_Y = -930.0            # the connector's south joint (its two one-way halves start here)
WG_CUT_X = -380.0            # a mainline joint between the Y's west ramps (Y1 EB exit, Y2 WB merge) and Y4 (EB merge)
Y4_OFF_Y = -760.0            # Y4, the connector SB -> Wangan EB: it leaves the connector here (review 2026-09-30: it
Y4_ON_X = 80.0              # closes the outer loop C1 -> connector -> Wangan -> spur -> C1), and merges here
Y2_Z = 20.5                  # Y2 over the mainline (12, lifted to ~14 by the dike pass there) by 5.5 m + margin
T1_ON_Y = -640.0             # T1 merges into the spur SB here: its lane closes by the bridge's north end (-696.5)
T2_OFF_Y = -620.0            # T2 leaves the spur NB here
T4_OFF_Y = -100.0            # T4 leaves the spur SB here (its 1-lane taper opens from the E joint at -45)
#: T3 (user, 2026-09-30: "a true Japanese JCT"): Wangan EB -> the spur NB (toward C1). It leaves the waterfront
#: diagonal on its north side, veers left on one gentle curve, runs a straight diagonal north of T1 and the Main line,
#: and turns north onto the spur's west side, merging at T3_ON_Y. A mainline joint at WG_CUT2_X keeps it off Y4's run
#: (both on EB) and a spur joint at SPUR_CUT_Y off T2's (both on NB).
T3_ON_Y = -170.0
WG_CUT2_X = 705.0
SPUR_CUT_Y = -410.0
#: Y3 (user, 2026-09-30: the connector's fourth movement): Wangan WB -> the connector NB. It leaves the waterfront straight
#: on its south side, runs straight on west while the mainline bends south-west beneath it, crosses it, Y4 and the
#: connector on ONE large right-hand turn (each crossing at that road's own height + 6.3 m), and merges into the
#: connector's west (NB) side at Y3_ON_Y.
#: S15: the bay jog slid 75 m south-west (WG_BAY_SHIFT) and its first arc came 75 m nearer this gore: 44 m of straight
#: was left upstream of it (150 before) and Y3 bent back ACROSS the WB lanes (validate: ramp_wrong_side, 2.7 m); x 160
#: put it on the mainline's corner at x 150 and on Y4's aux slot. The arc at WG_BAY_W is tightened instead (WG_MAIN_R),
#: and the gore swept (Y3's JCT grade, limit 6 %, measured on the exported lanes): x 210 5.95 %, 215 5.75 % K 9.6, 220
#: 6.4 %, 225 6.5 % K 4.9 -- 215 (was 220).
Y3_OFF_X = 215.0
Y3_CLIMB = 150.0             # Y3 keeps beside (not over) the mainline this far from its gore...
Y3_KEEP = 11.0               # ...its station at least this far off the mainline's centreline
#: the SUBURB EXIT (user, 2026-09-30: "can that ramp be on the Suburb side"): Wangan EB -> the ground, off the waterfront
#: diagonal's north side at SB_OFF_X, one S of two arcs beside the mainline, down into wangan_dori's junction by Suburb
#: station as its south arm, at SB_JUNCTION. A mainline joint at WG_CUT3_X keeps it
#: off Y4's run (both on EB).
SB_OFF_X = 540.0
#: P2-6: the Suburb's WB entrance -- from a new T on the dike road (ring_kita) east of the Wangan's crossing, where the
#: road is already on the sea side, merging onto the WB carriageway's left here
SB_ON_T = (850.0, -672.0)
#: (P12-6, 2026-10-13) its gore stood at x 640 ON the mainline's left arc, where the tangent points almost at the T's
#: mouth: no one-way curve reaches the T from there, and the ramp was an S. On the bay straight (x 454..545) the tangent
#: passes 113 m south of the mouth: a straight, ONE arc of R 100 and a straight (island_expressway.one_arc)
SB_ON_X = 520.0
#: P3-8: the port's WB exit -- off the WB's left under Y2's flyover, landing at a new T on the port loop's west leg
#: (kichi_dori__2) from inside the loop; a mainline joint at WG_CUT4_X keeps it off Y3's run
PORT_OFF_X = -170.0          # -200 -> -170 (2026-10-04): a two-lane exit holds ~30 m longer at the deck height
PORT_T = (-494.0, -1190.0)
WG_CUT4_X = -10.0
#: the port's EASTBOUND entrance (review 2026-10-02 night, port access (a)): from a new T on the dike road (ring_kita__11,
#: moved ~16 m north by tools/island_dike_port_gap.py to make the room) east of Y1's crossing of it, down the gap and
#: east, climbing the 5.6 m from the dike crest to the deck, merging onto EB's left at PORT_ON_X -- after Y1's exit
#: (exit -> entrance, no weave) and in wangan__2's run, whose only other ramp is the WB port exit
PORT_ON_T = (-440.0, -1082.0)
PORT_ON_X = -230.0   # -270 -> -250 -> -230 (2026-10-04): two-lane ramps; -230 clears port_off now it leaves at -170
SB_JUNCTION = (775.0, -437.0)
#: ...the junction is the nearest pad of one of these roads (2026-10-03 night: wangan_dori's own, opposite
#: eki_ginza_suburb; the side road's pad by kogai_michi sat inside wangan_dori's junction -- island_suburb_kogai.py)
SB_JUNCTION_ROADS = ("wangan_dori",)
WG_CUT3_X = 400.0
Y3_ON_Y = -650.0
#: THE CONNECTOR (R3): the Wangan's last stretch runs north OVER chuo_dori's median (piers in the median) from
#: CONN_S_Y to its end at CONN_N_Y, the W JCT's joint on C1's west side. It follows chuo_dori's own stations.
CONN_S_Y = -900.0          # south of here the chuo line is extended straight to the turn
CONN_N_Y = -25.0
CONN_Z = 13.0               # over ring_kita's dike (6.4 m) by 5.5 + margin
#: P2-5 (review 2026-10-01): the connector's half interchange to the west city -- the SB exit lands at a new T on
#: wangan_dori east of chuo, the NB entrance leaves a new T on rinkai_dori west of chuo (chuo itself has a junction
#: every 25-60 m here: no room for slip ramps onto its kerb lanes). A connector joint at CONN_CUT_Y keeps both off
#: Y3's and Y4's runs. Gores at the deck's height (13 m) right over the Blue line's at-grade track (y -160).
CONN_CUT_Y = -280.0
CONN_EXIT_Y = -150.0        # the SB exit's gore (review R3, 2026-10-02: 125 m after the W joint at -25, was 75)
CONN_ENT_Y = -200.0         # the NB entrance's gore (moved with the exit: one ramp per station); its lane is carried
                            # into W1
CONN_EXIT_T = (90.0, -427.0)    # the T on wangan_dori the exit lands at (from the north)
CONN_ENT_T = (-330.0, -285.0)   # the T on rinkai_dori the entrance leaves from (to the north)
CONN_MEDIAN = 4.0           # chuo_dori's raised median under the connector (a hammerhead's 2.6 m column + margins)

#: THE RAINBOW BRIDGE on the final plan's crossing (v9): the spur and the airport road come down the resort's new
#: south-east corner and cross at x 1250 (the water there is 852..1392 m south, 540 m against the bridge's 575 m main
#: span, so the towers stand at the water's edges). The lower deck is RAIL (R7); cars cross on the UPPER deck, the spur.
BRIDGE_X = 1250.0
BRIDGE_SEARCH_Y = (-500.0, -1700.0)    # record y range the water gap is looked for in


# ------------------------------------------------------------------ the Wangan (PLAN.md 3.30 L2; NEXT 2026-09-29)
#: GODOT (x, z). ONE divided road from a T on the west-coast ring's straight (moved SOUTH, user 2026-09-29 night, onto
#: the ring's straight x ~-1161 between z 725 and 900, a mouth clearance short of its corner), due west offshore,
#: round the south-west corner, east along the south waterfront past the port platform, then NORTH up the leg
#: (`W_LEG_X`) beside the rail corridor to its joint below C1 (`W_JOINT_Y`): the W JCT. Its old east end -- the
#: partial Y onto the airport spur (the underpass, the spur's 27.5 m hump) -- is removed: Wangan <-> airport goes
#: THROUGH C1, JCT to JCT. The waterfront continuation east to the spur is PHASE 2 (a held corridor, see RESERVES).
WANGAN_T = (-1161.0, 860.0)    # the west-coast ring point the Wangan meets, a T from the sea side
WANGAN_CENTRE = [(-1187.0, 860.0), (-1345.0, 860.0), (-1180.0, 1110.0), (-900.0, 1128.0), (-100.0, 1128.0),
                 (120.0, 1060.0), (370.0, 840.0), (370.0, 230.0)]
WANGAN_RADII = [0.0, 85.0, 160.0, 160.0, 160.0, 160.0, 160.0, 0.0]
WANGAN_LOW = 4.0               # the low sea viaduct: west of the port the Wangan crosses no road, so it need not fly
WANGAN_LOW_FROM_X = -900.0     # west of this (the shoreline past the port platform) the deck is WANGAN_LOW
WANGAN_DECK_FROM_X = -700.0    # the deck is at full height (11 m) east of this, over the whole port platform
WANGAN_RING_X = 150.0          # east of this the Wangan climbs to 14 m: it crosses ring_kita at the ring's corner
                               # (x ~236, 7.8 m on the dike) and north of it the leg holds W_LEG_Z

#: PHASE 2 HELD (PLAN.md NEXT, user 2026-09-29 night; re-drawn 2026-09-30 when phase 1 turned north onto chuo_dori): the
#: Wangan's continuation EAST along the south coast -- from east of phase 1's turn below chuo_dori, past the fish market, the
#: Ferris wheel park and the resort hotels -- to ONE directional T on the airport spur north of the Rainbow Bridge.
#: Record frame. The corridor is a divided expressway's width plus its piers and barriers; the T's footprint is its
#: flyover's arc and both ramps' tapers, beside the spur. Nothing but
#: the future Wangan may stand in either: no generated building (island_buildings), no site and no street running
#: ALONG it (island_streets treats each segment as a site); an existing road may cross UNDER it (it will be elevated).
#: BUILT now (2026-09-30, the complete Wangan): the corridor follows the mainline's own plan from where it leaves the
#: connector's Y, and the "T box" covers T1 / T2. It still keeps generated streets from running along under the
#: viaduct and generated buildings off it.
PHASE2_CORRIDOR = WG_MAIN[3:]
PHASE2_HALF = 17.5
PHASE2_T_BOX = (1000.0, -640.0, 1310.0, -400.0)    # x0, y0, x1, y1 (record): T1 and T2 (the lane-split T, 2026-10-01)


def diamond_strips():
    """The ground between each diamond ramp and C1 (PLAN.md item 2): no generated building stands in it. GODOT boxes
    (x0, z0, x1, z1), like RESERVES: per diamond and side of C1, from the gore x to the junction's mouth, between C1's
    centreline and the ramp's arm line."""
    out = []
    x0 = DIAMOND_ROAD[1]
    for yc, (yi, yo), xs, xw in ((C1_CORNERS[2][1], DIAMOND_J, DIAMOND_X, x0),
                                 (C1_CORNERS[0][1], (S_DIAMOND_IN_Y, S_DIAMOND_OUT_Y),
                                  {k: v[0] for k, v in S_DIAMOND_MARKS.items()}, S_DIAMOND_W_ROAD[1])):
        west = min(xs.values())
        east = max(xs.values())
        for y in (yi, yo):
            lo, hi = min(y, yc), max(y, yc)
            out.append((west, -hi, xw - 26.0, -lo))
            out.append((x0 + 26.0, -hi, east, -lo))
    return out


def phase2_boxes(grow=0.0):
    """The held phase-2 ground as oriented boxes (record frame): [(cx, cy, cos, sin, half along, half across)] -- one
    per corridor segment (grown `grow` all round) and the T's footprint."""
    import math as _m
    out = []
    for (x0, y0), (x1, y1) in zip(PHASE2_CORRIDOR, PHASE2_CORRIDOR[1:]):
        L = _m.hypot(x1 - x0, y1 - y0)
        out.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0, (x1 - x0) / L, (y1 - y0) / L, L / 2.0 + grow, PHASE2_HALF + grow))
    bx0, by0, bx1, by1 = PHASE2_T_BOX
    out.append(((bx0 + bx1) / 2.0, (by0 + by1) / 2.0, 1.0, 0.0, (bx1 - bx0) / 2.0 + grow, (by1 - by0) / 2.0 + grow))
    return out
