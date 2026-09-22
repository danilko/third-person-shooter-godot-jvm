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
DROPPED = ("shrine_touge", "kaigan_dori", "port_road", "futo_dori", "kitahama_dori", "nishihama_dori", "kuko_dori",
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
    ("hatoba_dori", "block", True, [(320, 735), (860, 735)]),
    ("eki_minami_dori", "trunk", True, [(580, -300), (580, 760)]),
    ("kogai_michi", "block", True, [(930, 420), (1000, 700), (1200, 850)]),
    ("jokamachi_dori", "block", False, [(-610, 20), (-610, 360)]),     # the castle (frozen at (-600, 40)) south to nishi_dori
    # the military base, reached THROUGH the blocks (v15): industry street x -500, logistics street z 1150, the gate
    ("kichi_dori", "block", False, [(-500, 150), (-500, 1150), (-490, 1150), (-490, 1250)]),
]


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
    ("city", (-85.0, -282.0, 1250.0, 410.0), "block", 150.0, 150.0),
    ("sw", (-1560.0, -1150.0, -100.0, -280.0), "block", 110.0, 110.0),
    ("farm", (850.0, 750.0, 1350.0, 1570.0), "farm", 260.0, 260.0),
    # residential north lies between C1 and the farm arterial -- where the C1 diamond comes down, so the ramps' band
    # (x 180..1020) is left out: a street under a descending ramp had 4.5 m of clearance
    ("north", (-330.0, 560.0, 180.0, 810.0), "lane", 120.0, 120.0),
    ("north_e", (1020.0, 560.0, 1250.0, 810.0), "lane", 120.0, 120.0),
    ("industry", (-1000.0, -1040.0, 280.0, -640.0), "block", 200.0, 200.0),
    ("logistics", (-820.0, -1540.0, -60.0, -1040.0), "block", 220.0, 220.0),
    ("suburb", (880.0, -1060.0, 1300.0, -330.0), "block", 150.0, 150.0),
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
)
STREET_NAMES = {"city": ("machi", "cho"), "sw": ("nishi_machi", "nishi_cho"), "farm": ("hata_michi", "hata_yoko"),
                "north": ("kita_machi", "kita_cho"), "north_e": ("kita_machi_e", "kita_cho_e"), "industry": ("kojo_michi", "kojo_yoko"),
                "logistics": ("butsuryu_michi", "butsuryu_yoko"), "suburb": ("kogai_machi", "kogai_cho")}


# ------------------------------------------------------------------ the expressway (island_expressway.py)
#: C1 and its interchanges, the pre-redo numbers moved with the plan (x - 125 in the core; y by the band compress):
#: corners (150, 40)..(1300, 720) -> (25, -110)..(1175, 570); the JCT x 780 -> 655; the diamond on naka_hondori x 725
#: -> 600, its junctions y 615 / 815 -> 465 / 665, its ramp stations x 345 / 465 / 985 / 1105 -> -125.
C1_CORNERS = [(25.0, -110.0), (1175.0, -110.0), (1175.0, 570.0), (25.0, 570.0)]
C1_SIDE_CUT_Y = 150.0              # C1 is cut into roads half way up each side (pre-redo y 300)
JCT_X = 655.0
DIAMOND_X = {"d_bwd_off": 220.0, "d_fwd_on": 340.0, "d_bwd_on": 860.0, "d_fwd_off": 980.0}
DIAMOND_ROAD = ("naka_hondori", 600.0)
DIAMOND_J = (465.0, 665.0)

#: THE RAINBOW BRIDGE on the final plan's crossing (v9): the spur and the airport road come down the resort's new
#: south-east corner and cross at x 1250 (the water there is 852..1392 m south, 540 m against the bridge's 575 m main
#: span, so the towers stand at the water's edges). The lower deck is RAIL (R7); cars cross on the UPPER deck, the spur.
BRIDGE_X = 1250.0
BRIDGE_SEARCH_Y = (-500.0, -1700.0)    # record y range the water gap is looked for in
SPUR_EAST_Y = -500.0                   # the spur runs south from the JCT, then east at this y to the bridge axis


# ------------------------------------------------------------------ the Wangan, east section (PLAN.md 3.30 L2)
#: GODOT (x, z). The plan's orange line from the spur JCT along the south waterfront to the port corner (v8). The WEST
#: section (R6, over the port's north edge to the west coast) is not built yet: this section ends at grade on the
#: coastal ring's north-south stretch at the port corner, as v8 drew it before v11 extended it.
#: The spur JCT is PARTIAL -- Wangan <-> airport only (the racing route, "off the airport spur"): the Wangan meets the
#: spur's east leg from the south-west, where airport -> Wangan leaves spur_in to its own left and Wangan -> airport
#: passes under both spur carriageways to join spur_out from its left. Wangan <-> C1 would need two loops.
WANGAN_S_X = 1000.0            # the spur station the two Wangan ramps leave / join (spur_in diverge, spur_out merge)
WANGAN_J_X = 890.0             # a joint on spur_out before it: the loop JCT's acceleration lane and the Wangan's
                               # entrance are both on spur_out, and one run carries one aux slot
WANGAN_CENTRE = [(430.0, 800.0), (600.0, 800.0), (780.0, 585.0)]   # the shared corridor, offshore of the park
WANGAN_T_E = (237.0, 760.0)    # where the eastbound carriageway starts, at a T on the ring (ring_kita, x ~237)
WANGAN_T_W = (237.0, 880.0)    # where the westbound carriageway ends, at its own T
