#!/usr/bin/env python3
"""island_buildings.py -- the island's buildings, placed by REGION along its streets and streamed per 252 m cell
(PLAN.md 3.6 "regions, then detail"; 3.13 step 7).

    python3 tools/island_buildings.py derive <heights.f32>     # writes IslandBuildings.json (needs a terrain dump)
    python3 tools/island_buildings.py write [--check]          # cell scenes + the BuildingZones / PedZones blocks
    python3 tools/island_buildings.py peds                     # the derived crowd density, per region

`derive` reads a Terrain3D height dump of World's terrain (`tools/godot/dump_height_grid.gd -- <out> -2304 -2304
2305 2305 2`: Godot frame, 2 m, the STAMPED terrain the buildings stand on) and the road record, and writes the
placements to `assets/world_source/buildings/IslandBuildings.json` -- reviewed like the record. `write` needs no
terrain: it turns that file into one scene per cell (`world/buildings/cells/Bld_island_<gx>_<gz>.tscn`, each
building an INSTANCE of its type scene at its world transform) and a `BuildingZones` block of ZoneMarkers in
World.tscn whose zones stream them (`geometry_world_placed`, identity: the instances carry world transforms).
A cell scene lives under `/world/buildings/`, so the Road Kit dock leaves its zone out of the road cut.

How a lot is found (nothing is typed in as a coordinate):
* **Blocked** = every solved road surface (`point_edges.band_corridors`: carriageways, junction pads, gores, at any
  height, so nothing stands under the expressway) grown by that road's own footway + `KERB_GAP`; the sea and
  `COAST_CLEAR` of shore; every streamed site's footprint and the landmarks (+ `SITE_CLEAR`).
* **Frontage rows**: each at-grade road's two edges are offset by (paved half + footway + gap); a building stands
  with its FRONT on that line, facing the road (Japanese frontage: the footway is the road's, the lot starts behind
  it). Rows behind it (`rows`) are the same line pushed back by the region's `pitch`, still facing the road, so a
  block fills from both of its streets toward the middle.
* **A lot is accepted** when its whole footprint (the type scene's own `metadata/building.aabb`, plus `ALLEY` on
  the sides and back) is on free land and the ground under it varies by no more than `RELIEF`; the building stands
  at the HIGHEST ground under it, so no floor is buried.
* **What stands there** is the region's weighted mix, chosen by a hash of (road, side, row, slot) so an unchanged
  record rebuilds byte-identically. Lots, gas stations and restaurants only front an arterial (>= 2 lanes a side)
  and keep a spacing from the next of their kind (`SPACING`).
"""
import json
import math
import os
import random
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import ROOT, PIECES     # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "blender", "lib"))
import point_model as pm                    # noqa: E402
import island_traffic_zones as itz          # noqa: E402

SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/world/World.tscn")
RECORD = os.path.join(PIECES, "IslandRoads.roads.json")
GROUND = os.path.join(PIECES, "IslandRoads.ground.json")
OUT = os.path.join(ROOT, "assets/world_source/buildings/IslandBuildings.json")
SIDEWALKS = os.path.join(ROOT, "src/main/resources/com/openworld/world/IslandSidewalks.json")   # read at runtime
BLD_DIR = os.path.join(ROOT, "src/main/resources/com/openworld/world/buildings")
BLD_RES = "res://src/main/resources/com/openworld/world/buildings"
CELL_DIR = os.path.join(BLD_DIR, "cells")
CELL_RES = BLD_RES + "/cells"

HALF = 2304.0          # the height dump covers [-HALF, HALF] in Godot x and z
DUMP_STEP = 2.0
RES = 1.0              # the lot masks' resolution (m)
CELL = 252.0           # a building cell is a QUARTER road cell: one cell's buildings are instantiated in ONE frame
                       # (ZoneManager GEO_INSTANTIATE), and a 504 m downtown cell (~250 buildings, ~5 k nodes) was a
                       # 20-26 ms frame (probe_city_perf.gd)
ORIGIN = 2016.0
LAND_Z = 0.35          # Godot height above which a sample is land
COAST_CLEAR = 16.0     # no building within this of the water line
KERB_GAP = 1.5         # past the footway (or the carriageway edge, where there is none)
ELEVATED_GAP = 3.0     # clear of an elevated deck's edge (its piers and caps)
PAD_GAP = 5.0          # clear of a junction pad (its corner footways)
SITE_CLEAR = 20.0
ALLEY = 1.5            # kept free on a building's sides and back (half the alley between two)
RELIEF = 0.7
SIDEWALK_STEP = 6.0    # sidewalk path sample spacing
KERB_H = 0.15          # a footway stands this far above its carriageway
LOT_BURY_TOL = 0.05    # the ground may stand this far above a lot's top (inside it: the slab covers it)
LOT_MAX_STEP = 1.2     # ... and fall at most this far below it
LOT_GROW_MAX = 10.0    # a lot grows at most this far to its back / front toward the pavement
LOT_GROW_SIDE = 30.0   # ... and this far along its street (to the corner)
PAD_WALK = 4.0         # a junction pad's corner footway width, for the lot-stop mask
LOT_SKIRT = 0.3        # the slab reaches this far below the lowest ground under it
LOT_FOOTWAY_GAP = 0.05 # the frontage slab stops this short of the footway's outer edge
SLOT_STEP = 3.0        # how far along a row a rejected slot moves before trying again
LOAD = 800.0           # a cell's buildings stream in within this of its centre
UNLOAD = 1100.0

# region: (name, record-frame box (x0, y0, x1, y1), rows, pitch, mix, skip chance). First box that holds a point wins.
REGIONS = (
    ("downtown", (150.0, 40.0, 1300.0, 720.0), 3, 24.0,
     {"OfficeMid": 4, "PencilBuilding": 4, "Mansion": 2, "ShopHouse": 1.5, "Konbini": 1, "FamilyRestaurant": 0.3},
     0.0),
    ("city", (-150.0, -330.0, 1700.0, 960.0), 2, 22.0,
     {"Mansion": 3, "ShopHouse": 3, "PencilBuilding": 2, "Apartment": 2, "Konbini": 1, "OfficeMid": 0.5,
      "FamilyRestaurant": 0.6, "KonbiniLot": 0.6, "GasStation": 0.5}, 0.05),
    ("harbour", (-820.0, -2050.0, 250.0, -1040.0), 2, 30.0, {"Warehouse": 1}, 0.2),
    ("residential", (-1800.0, -1160.0, -150.0, -200.0), 2, 18.0,
     {"Apartment": 4, "ShopHouse": 2, "Mansion": 1, "KonbiniLot": 0.6, "GasStation": 0.4, "FamilyRestaurant": 0.3,
      "Konbini": 0.4}, 0.15),
    ("suburb", (850.0, -1060.0, 1800.0, -330.0), 2, 18.0,
     {"Apartment": 4, "ShopHouse": 1.5, "Mansion": 1, "KonbiniLot": 0.6, "GasStation": 0.4,
      "FamilyRestaurant": 0.4}, 0.25),
    ("farm", (350.0, 960.0, 1850.0, 1900.0), 1, 30.0, {"Apartment": 2, "Warehouse": 1, "KonbiniLot": 0.2}, 0.65),
)
ARTERIAL_ONLY = {"GasStation", "KonbiniLot", "FamilyRestaurant"}
# Every building ships SHUT (user, 2026-09-19), with two exceptions, both placed as a variant of the same type:
# * `<Type>_Shop` -- unlocked, automatic doors: the shops a player walks into as ordinary play (GTA's konbini, diner,
#   petrol station, station hall) and the player's home base;
# * `<Type>_Open` -- `world.Door` nodes LOCKED until a MISSION unlocks them (KonbiniMission does).
SHOP_TYPES = {"Konbini", "KonbiniLot", "FamilyRestaurant", "GasStation", "GasKiosk", "StationBuilding",
              "StationRural"}
PUBLIC_BUILDINGS = (      # (Godot x, z, why): a specific building that is always open, beside the shop types
    (682.0, -363.0, "the player's home base (placeholder: the block behind the konbini)"),
)
OPEN_BUILDINGS = (        # (Godot x, z, why): locked until its mission unlocks it. Wins over the two above.
    (685.0, -336.0, "m01_konbini: the shop the konbini job is played at"),
)
OPEN_MATCH = 12.0      # the placement nearest an OPEN_BUILDINGS point, within this
SPACING = {"GasStation": 450.0, "KonbiniLot": 250.0, "FamilyRestaurant": 350.0, "Konbini": 120.0}
SKIP_ROADS = ("shuto_", "shrine_touge", "kaigan_dori", "airport_", "kuko_dori")
TYPES = sorted({t for r in REGIONS for t in r[4]})

# --- the ambient crowd (PLAN.md 3.6d). A pedestrian zone is derived from the SAME footways the buildings front,
# on the SAME 252 m cell grid, so "where do people walk" has one owner. What a zone carries is a
# `SpawnConfig.behavior = "sidewalk"` group, which `ZoneManager` turns into a `PedCrowd` of script-free bodies and
# promotes from as a player comes within 80 m.
PED_HOLDER = "PedZones"
PED_ZONE_PREFIX = "Zone_ped_"
PED_CFG_PREFIX = "PedSpawn_"
PED_NODE_ID_BASE = 910017000
SPAWN_SCRIPT = "res://src/main/java/com/openworld/world/SpawnConfig.java"
SPAWN_UID = "uid://ctq8u5jyp6ijf"
# Pedestrians per 100 m of footway, by region -- the one tuning knob, and deliberately conservative: raise it
# against `tools/godot/probe_city_perf.gd --crowd` (a display), never by eye. A crowd's cost is per PHYSICS TICK
# and the cliff is Godot's catch-up spiral past 16.7 ms, so the number that matters is how many are in range at
# once, which `peds` prints.
PED_DENSITY = {"downtown": 2.0, "city": 1.2, "residential": 0.8, "suburb": 0.6, "harbour": 0.4, "farm": 0.3,
               None: 0.5}
PED_MAX = 40           # a single cell's crowd, however much footway it holds
PED_LOAD = 300.0       # > the cell's own half-diagonal (178 m) and just over the 252 m cell pitch, so the four
                       # orthogonal neighbours stream too and a crowd exists before it is in view
PED_UNLOAD = 420.0     # hysteresis, the Zone rule: unload > load > halfExtent
# `neutral` is never hostile whatever faction table is live (FactionRules), which is exactly what an ambient
# pedestrian must be. `civilian` reads better but is hostile to `player` by the INHERENT default unless a preset
# table is applied, and World.tscn applies none.
PED_FACTION = "neutral"

# --- where on a footway a pedestrian walks (PLAN.md 3.18a, user-reported: "the crowd gets stuck at a pole").
# The walk line used to be the footway's MIDDLE, and every street prop stands in the KERB-SIDE strip, so the two
# were laid on top of each other: measured over the island, 1081 of 1139 planters, 483 of 1061 lamps and 108 of
# 333 signals stood within a 0.35 m capsule of the line (worst -0.92 m). A body blocked by one never advances,
# and `SidewalkWalkerController` advances `along` by the step it actually took -- so it never reaches the end,
# never turns round, and is pinned there for ever.
#
# The line is now the middle of the CLEAR band: outboard of the furniture strip, inboard of the footway's outer
# edge. The strip is DERIVED from `furniture.json` -- the same table the placer reads, so the two cannot come to
# disagree about where a planter is -- never a constant repeated here.
PED_RADIUS = 0.35      # the character capsule (MeshConfig `body_radius`, measured on every body by measure_body.gd)
PED_EDGE = 0.10        # ... and the margin it keeps from the strip and from the footway's outer edge


def furniture_strip(walk):
    """How far outboard of the KERB the road furniture reaches on a footway `walk` m wide (m).

    Read off `furniture.json`: each kerb-side asset's own offset plus its own half width across the footway, and
    only the assets a footway that wide can carry (`*_min_footway`). A pad's bollards and a junction's signal are
    included on every road: they stand on the same footway and one line per road side is what the crowd walks."""
    global _STRIP_CACHE
    try:
        table = _STRIP_CACHE
    except NameError:
        table = None
    if table is None:
        for d in (os.path.join(ROOT, "blender", "addons", "road_kit_authoring"),):
            if d not in sys.path:
                sys.path.insert(0, d)
        import point_furniture as pfu
        table = _STRIP_CACHE = pfu.load()
    r, a = table.rules, table.assets

    def across(name):
        """Half the asset's extent ACROSS the footway: a pole is its shaft, anything else its own plan box
        (`Furniture.put` turns a piece to the road, so its local X is the across-footway axis)."""
        asset = a[name]
        if asset.get("collide_pole"):
            return float(asset["collide_pole"][0])
        return 0.5 * (asset["hi"][0] - asset["lo"][0]) * asset["scale"][0]

    reach = [r["lamp_inset"] + across("lamp"),
             r["signal_kerb_offset"] + across("signal"),
             r["bollard_inset"] + across("bollard")]
    if walk >= r["tree_min_footway"]:
        reach.append(r["tree_kerb_gap"] + across(r["tree_assets"][0]))
    if walk >= r["planter_min_footway"]:
        # `_edge_props` puts the planter's CENTRE at kerb_gap + half, so its far face is kerb_gap + 2 * half
        reach.append(r["planter_kerb_gap"] + 2.0 * across("planter"))
    return max(reach)


def ped_walk_offset(walk):
    """Where the walk line sits, measured from the kerb, on a footway `walk` m wide."""
    strip = min(furniture_strip(walk), max(0.0, walk - 2.0 * (PED_RADIUS + PED_EDGE)))
    return max(strip + PED_RADIUS + PED_EDGE,
               min(0.5 * (strip + walk), walk - PED_RADIUS - PED_EDGE))


def region_of(x, y):
    for r in REGIONS:
        x0, y0, x1, y1 = r[1]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return r
    return None


def type_aabb(name):
    """(x0, z0, x1, z1, height) of a type scene's own footprint, from its `metadata/building.aabb`."""
    text = open(os.path.join(BLD_DIR, name + ".tscn")).read()
    m = re.search(r'"aabb": \[Vector3\(([^)]*)\), Vector3\(([^)]*)\)\]', text)
    if not m:
        raise SystemExit("island_buildings: %s.tscn has no metadata/building aabb" % name)
    p = [float(v) for v in m.group(1).split(",")]
    s = [float(v) for v in m.group(2).split(",")]
    return (p[0], p[2], p[0] + s[0], p[2] + s[2], p[1] + s[1])


# ------------------------------------------------------------------------------------------ masks

class Field(object):
    """Godot-frame (x, z) masks at RES over [-HALF, HALF]; index (j, i) = (z, x)."""

    def __init__(self, heights_path):
        import numpy as np
        self.np = np
        n2 = int(round(2 * HALF / DUMP_STEP)) + 1
        self.h2 = np.fromfile(heights_path, dtype="<f4").reshape(n2, n2)
        self.n = int(round(2 * HALF / RES))
        land2 = self.h2 > LAND_Z
        # erode the land by COAST_CLEAR (a square structuring element, 2 m steps)
        er = land2.copy()
        for _ in range(int(math.ceil(COAST_CLEAR / DUMP_STEP))):
            e = er.copy()
            e[1:, :] &= er[:-1, :]
            e[:-1, :] &= er[1:, :]
            e[:, 1:] &= er[:, :-1]
            e[:, :-1] &= er[:, 1:]
            er = e
        k = int(DUMP_STEP / RES)
        self.blocked = ~np.repeat(np.repeat(er[:-1, :-1], k, 0), k, 1)[:self.n, :self.n]
        self.occupied = np.zeros((self.n, self.n), dtype=bool)
        self.owner = np.zeros((self.n, self.n), dtype=np.int32)     # 1 + index of the building whose lot holds it
        self.road = np.zeros((self.n, self.n), dtype=bool)          # carriageway + footway: where a lot must stop

    def idx(self, x, z):
        return int(math.floor((x + HALF) / RES)), int(math.floor((z + HALF) / RES))

    def block_capsule(self, a, b, r, target=None):
        np = self.np
        x0, x1 = min(a[0], b[0]) - r, max(a[0], b[0]) + r
        z0, z1 = min(a[1], b[1]) - r, max(a[1], b[1]) + r
        i0, j0 = self.idx(x0, z0)
        i1, j1 = self.idx(x1, z1)
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, self.n - 1), min(j1, self.n - 1)
        if i1 < i0 or j1 < j0:
            return
        xs = (np.arange(i0, i1 + 1) + 0.5) * RES - HALF
        zs = (np.arange(j0, j1 + 1) + 0.5) * RES - HALF
        X, Z = np.meshgrid(xs, zs)
        dx, dz = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dz * dz
        if L2 < 1e-9:
            t = 0.0
        else:
            t = np.clip(((X - a[0]) * dx + (Z - a[1]) * dz) / L2, 0.0, 1.0)
        d2 = (X - a[0] - t * dx) ** 2 + (Z - a[1] - t * dz) ** 2
        (self.blocked if target is None else target)[j0:j1 + 1, i0:i1 + 1] |= d2 <= r * r

    def block_box(self, cx, cz, yaw, hx, hz):
        """A rotated box, half sizes hx (local x) and hz (local z)."""
        pts = self.rect_points(cx, cz, yaw, -hx, -hz, hx, hz)
        self.blocked[pts[1], pts[0]] = True

    def rect_points(self, cx, cz, yaw, x0, z0, x1, z1):
        """Mask indices (i array, j array) of the cells whose centres lie in the local rect [x0,x1] x [z0,z1] of a
        frame at (cx, cz) turned by yaw (local +Z -> (sin yaw, cos yaw))."""
        np = self.np
        s, c = math.sin(yaw), math.cos(yaw)
        corners = [(x0, z0), (x1, z0), (x0, z1), (x1, z1)]
        wx = [cx + lx * c + lz * s for lx, lz in corners]
        wz = [cz - lx * s + lz * c for lx, lz in corners]
        i0, j0 = self.idx(min(wx), min(wz))
        i1, j1 = self.idx(max(wx), max(wz))
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, self.n - 1), min(j1, self.n - 1)
        if i1 < i0 or j1 < j0:
            return np.zeros(0, int), np.zeros(0, int)
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        X = (ii + 0.5) * RES - HALF - cx
        Z = (jj + 0.5) * RES - HALF - cz
        lx = X * c - Z * s
        lz = X * s + Z * c
        inside = (lx >= x0) & (lx <= x1) & (lz >= z0) & (lz <= z1)
        return ii[inside], jj[inside]

    def heights(self, i, j):
        """Nearest 2 m dump sample under each 1 m cell."""
        k = int(DUMP_STEP / RES)
        return self.h2[j // k, i // k]


# ------------------------------------------------------------------------------------------ roads

def solve_bands():
    for p in (os.path.join(ROOT, "blender", "lib"), os.path.join(ROOT, "blender", "addons", "road_kit_authoring")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import point_edges as ped
    import point_ground as pg
    net = pm.load_network(RECORD)
    grid = pg.load_ground(GROUND)
    bands = ped.solve_all(net, grid)[3]
    return net, grid, ped.band_corridors(bands, owners=True)


def road_walk(net, owner):
    r = net.roads.get(owner)
    if r is None:
        return 0.0, 0
    b = r.base
    return (max(float(getattr(b, "left_walk_width", 0.0) or 0.0), float(getattr(b, "right_walk_width", 0.0) or 0.0)),
            min(int(getattr(b, "lanes_fwd", 0) or 0), int(getattr(b, "lanes_bwd", 0) or 0)))


def godot_xz(x, y):
    return (x, -y)


def elevated(z, ground):
    return ground is not None and z - ground > 3.0


# ------------------------------------------------------------------------------------------ derive

def site_exclusions(text):
    """[(godot x, z, yaw, half x, half z)] of every streamed site and landmark in the scene."""
    out = []
    for m in re.finditer(r'\[sub_resource type="Resource" id="Zone_site_[^"]*"\]\n(.*?)\n\n', text, re.S):
        body = m.group(1)
        size = re.search(r"size = Vector3\(([^)]*)\)", body)
        xf = re.search(r"geometry_world_transform = Transform3D\(([^)]*)\)", body)
        if size and xf:
            s = [float(v) for v in size.group(1).split(",")]
            t = [float(v) for v in xf.group(1).split(",")]
            out.append((t[9], t[11], math.atan2(t[2], t[0]), s[0] / 2 + SITE_CLEAR, s[2] / 2 + SITE_CLEAR))
    for m in re.finditer(r'\[node name="(\w+)" parent="Landmarks"[^\]]*\]\ntransform = Transform3D\(([^)]*)\)', text):
        t = [float(v) for v in m.group(2).split(",")]
        # the Rainbow Bridge: its towers and anchorages along its own +Z over ~900 m, 60 m wide
        out.append((t[9], t[11], math.atan2(t[2], t[0]), 40.0 + SITE_CLEAR, 480.0 + SITE_CLEAR))
    return out


def offset_line(line, dist):
    """The corridor centreline [(gx, gz, half, surface y)] offset by `dist` to its LEFT (+) or right (-) of travel,
    as [(x, z, nx, nz, surface y)] with (nx, nz) the unit normal pointing BACK to the road."""
    out = []
    n = len(line)
    for k in range(n):
        a = line[max(k - 1, 0)]
        b = line[min(k + 1, n - 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, tz)
        if L < 1e-9:
            continue
        tx, tz = tx / L, tz / L
        lx, lz = -tz, tx          # left of travel in Godot x/z (y up): rotate +90 about -Y... sign handled by dist
        sgn = 1.0 if dist >= 0 else -1.0
        off = abs(dist) + line[k][2]
        out.append((line[k][0] + sgn * lx * off, line[k][1] + sgn * lz * off, -sgn * lx, -sgn * lz, line[k][3]))
    return out


def resample(pts, step):
    """[(x, z, nx, nz, y)] every `step` metres of arc length."""
    if len(pts) < 2:
        return []
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-9:
            continue
        t = step - acc
        while t <= L:
            f = t / L
            nx = a[2] + (b[2] - a[2]) * f
            nz = a[3] + (b[3] - a[3]) * f
            nl = math.hypot(nx, nz) or 1.0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, nx / nl, nz / nl, a[4] + (b[4] - a[4]) * f))
            t += step
        acc = L - (t - step)
    return out


def grow_lots(field, placed):
    """Pave each lot out to the pavement (user, 2026-09-19): every side of every lot moves out a metre at a time, up to
    LOT_GROW_MAX, while the new strip is free land that is not road or footway (`field.road`, stopping LOT_FOOTWAY_GAP
    short of it), not another building's lot, and at ground the slab covers (the same bury / step rule the lot had).
    So a corner building's SIDE reaches the cross street's footway and a block's gaps close, with no strip of bare
    heightmap between the pavement and a door. Greedy in placement order; each grown cell is claimed at once, so two
    lots never overlap (coplanar slabs would z-fight)."""
    for k, b in enumerate(placed):
        x0, z0, x1, z1 = b["lot"]
        top = b["pos"][1]
        a = math.radians(b["yaw"])
        cx, cz = b["pos"][0], b["pos"][2]
        lowest = top - (b["lot_depth"] - LOT_SKIRT)
        me = k + 1
        for side in ("x0", "x1", "z0", "z1"):
            # along the street a lot may run on to the corner (a street's frontage row starts at the junction MOUTH,
            # 15-25 m from the crossing, so a corner plot is otherwise bare); back and front only a little
            for _ in range(int(LOT_GROW_SIDE if side in ("x0", "x1") else LOT_GROW_MAX)):
                if side == "x0":
                    strip = (x0 - 1.0, z0, x0, z1)
                elif side == "x1":
                    strip = (x1, z0, x1 + 1.0, z1)
                elif side == "z0":
                    strip = (x0, z0 - 1.0, x1, z0)
                else:
                    strip = (x0, z1, x1, z1 + 1.0)
                ii, jj = field.rect_points(cx, cz, a, *strip)
                if ii.size == 0:
                    break
                own = field.owner[jj, ii]
                if field.road[jj, ii].any() or ((own != 0) & (own != me)).any():
                    break
                hs = field.heights(ii, jj)
                if float(hs.max()) > top + LOT_BURY_TOL or top - float(hs.min()) > LOT_MAX_STEP \
                        or float(hs.min()) <= LAND_Z:
                    break
                field.owner[jj, ii] = me
                lowest = min(lowest, float(hs.min()))
                if side == "x0":
                    x0 -= 1.0
                elif side == "x1":
                    x1 += 1.0
                elif side == "z0":
                    z0 -= 1.0
                else:
                    z1 += 1.0
        b["lot"] = [round(x0, 3), round(z0, 3), round(x1, 3), round(z1, 3)]
        b["lot_depth"] = round(top - lowest + LOT_SKIRT, 3)


def walk_lines(owner, cl, walk):
    """The footway walk lines of ONE road run -- what the ambient crowd walks (`world.Sidewalks`).

    One owner, shared by `derive` (which places the buildings in the same pass) and the `sidewalks` command
    (which re-derives only this record, so a walk-line change costs no terrain dump and moves no building)."""
    out = []
    if walk < 1.5:
        return out
    for side in (1.0, -1.0):
        walkway = resample(offset_line(cl, side * ped_walk_offset(walk)), SIDEWALK_STEP)
        # the footway's height: its carriageway's + the kerb
        line = [[round(wx, 2), round(wy + KERB_H, 2), round(wz, 2)] for wx, wz, _nx, _nz, wy in walkway]
        if len(line) >= 3:
            out.append({"road": owner, "side": int(side), "points": line})
    return out


def write_sidewalks(sidewalks):
    with open(SIDEWALKS, "w") as f:
        json.dump({"schema": 1, "source": "tools/island_buildings.py derive",
                   "note": "footway centrelines, Godot world frame, one per road-run side",
                   "sidewalks": sidewalks}, f, separators=(",", ":"))
        f.write("\n")
    print("island_buildings: %d sidewalks, %.1f km -> %s" % (len(sidewalks), sum(
        sum(math.dist(a, b) for a, b in zip(w["points"], w["points"][1:])) for w in sidewalks) / 1000.0,
        os.path.relpath(SIDEWALKS, ROOT)))


def sidewalks_only(check):
    """Re-derive ONLY `IslandSidewalks.json`. Needs no terrain dump and touches no building: the walk line is a
    fact about the ROAD (its footway width and what furniture stands on it), which the road solve already has."""
    net, grid, cors = solve_bands()
    text = open(SCENE).read()
    ny = float(re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
               .group(1).split(",")[10])
    out = []
    for line, _h, owner in cors:
        owner = str(owner)
        if owner.startswith(("JCT:", "GORE:")) or owner.startswith(SKIP_ROADS):
            continue
        pts = [(x, -y, z, half) for (x, y, z, half) in line]
        if any(elevated(z, grid(x, -gz)) for x, gz, z, _ in pts):
            continue
        walk, _lanes = road_walk(net, owner)
        out += walk_lines(owner, [(x, z, half, zz + ny) for x, z, zz, half in pts], walk)
    body = json.dumps({"schema": 1, "source": "tools/island_buildings.py derive",
                       "note": "footway centrelines, Godot world frame, one per road-run side",
                       "sidewalks": out}, separators=(",", ":")) + "\n"
    same = os.path.exists(SIDEWALKS) and open(SIDEWALKS).read() == body
    if check:
        print("island_buildings: sidewalks %s" % ("up to date" if same else "STALE"))
        return 0 if same else 1
    write_sidewalks(out)
    return 0


def derive(heights_path):
    net, grid, cors = solve_bands()
    field = Field(heights_path)
    text = open(SCENE).read()
    ny = float(re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
               .group(1).split(",")[10])
    # --- block every road surface, grown by its own footway
    frontage = []
    sidewalks = []
    for line, _h, owner in cors:
        owner = str(owner)
        pts = [(x, -y, z, half) for (x, y, z, half) in line]
        walk, lanes = road_walk(net, owner)
        if owner.startswith("JCT:"):
            grow = walk + PAD_GAP if walk else PAD_GAP
        elif owner.startswith("GORE:") or owner.startswith("shuto_"):
            grow = ELEVATED_GAP
        else:
            grow = walk + KERB_GAP
        high = any(elevated(z, grid(x, -gz)) for x, gz, z, _ in pts)
        if high:
            grow = max(grow, ELEVATED_GAP)
        hard = (walk if walk else PAD_WALK) if owner.startswith("JCT:") else walk
        for a, b in zip(pts, pts[1:]):
            field.block_capsule(a[:2], b[:2], max(a[3], b[3]) + grow)
            field.block_capsule(a[:2], b[:2], max(a[3], b[3]) + hard, field.road)
        if len(pts) == 1:
            field.block_capsule(pts[0][:2], pts[0][:2], pts[0][3] + grow)
            field.block_capsule(pts[0][:2], pts[0][:2], pts[0][3] + hard, field.road)
        if not owner.startswith(("JCT:", "GORE:")) and not owner.startswith(SKIP_ROADS) and not high:
            cl = [(x, z, half, zz + ny) for x, z, zz, half in pts]
            frontage.append((owner, cl, walk + KERB_GAP + 0.3, lanes, walk > 0.0))
            sidewalks += walk_lines(owner, cl, walk)
    for (cx, cz, yaw, hx, hz) in site_exclusions(text):
        field.block_box(cx, cz, yaw, hx, hz)
    aabbs = {t: type_aabb(t) for t in TYPES}
    placed, counts, seen_kind = [], {}, {}

    def far_from_kind(t, x, z):
        d = SPACING.get(t)
        if not d:
            return True
        return all((x - px) ** 2 + (z - pz) ** 2 >= d * d for px, pz in seen_kind.get(t, ()))

    def try_place(t, px, pz, nx, nz, key, region, road_y, front_gap, kerbed):
        x0, z0, x1, z1, hgt = aabbs[t]
        yaw = math.atan2(nx, nz)          # local +Z (the front) turned onto the road direction
        # the front face (local z1) on the row line
        cx, cz = px - nx * z1, pz - nz * z1
        ii, jj = field.rect_points(cx, cz, yaw, x0 - ALLEY, z0 - ALLEY, x1 + ALLEY, z1)
        if ii.size == 0:
            return None
        if field.blocked[jj, ii].any() or field.occupied[jj, ii].any():
            return None
        hs = field.heights(ii, jj)
        if float(hs.max() - hs.min()) > RELIEF or float(hs.min()) <= LAND_Z:
            return None
        # The LOT: a concrete slab at the sidewalk's height (the road's surface + the kerb; the carriageway's own
        # height where the road has no footway), under the building, its alleys and -- on the frontage row -- the
        # strip out to the footway, so the ground a player walks from the pavement to the door is one level surface.
        # The building stands on it, not on the heightmap. Refused where the ground stands above the slab (it would
        # bury it) or falls further below it than LOT_MAX_STEP (it would stand on a plinth).
        top = road_y + (KERB_H if kerbed else 0.0)
        if float(hs.max()) > top + LOT_BURY_TOL or top - float(hs.min()) > LOT_MAX_STEP:
            return None
        field.occupied[jj, ii] = True
        field.owner[jj, ii] = len(placed) + 1
        if front_gap > 0.0:
            fi, fj = field.rect_points(cx, cz, yaw, x0 - ALLEY, z1, x1 + ALLEY, z1 + front_gap)
            free = field.owner[fj, fi] == 0
            field.owner[fj[free], fi[free]] = len(placed) + 1
        return {"type": t, "region": region[0], "key": key,
                "pos": [round(cx, 3), round(top, 3), round(cz, 3)],
                "yaw": round(math.degrees(yaw), 3),
                # local rect of the slab and its bottom (below the lowest ground under it)
                "lot": [round(x0 - ALLEY, 3), round(z0 - ALLEY, 3), round(x1 + ALLEY, 3), round(z1 + front_gap, 3)],
                "lot_depth": round(top - float(hs.min()) + LOT_SKIRT, 3)}

    for owner, line, gap, lanes, kerbed in frontage:
        for side in (1.0, -1.0):
            for row in range(3):
                pts = resample(offset_line(line, side * gap), SLOT_STEP)
                if not pts:
                    continue
                pts_rows = pts
                k = 0
                while k < len(pts_rows):
                    px, pz, nx, nz, _y = pts_rows[k]
                    reg = region_of(px, -pz)
                    if reg is None or row >= reg[2]:
                        k += 1
                        continue
                    back = row * reg[3]
                    qx, qz = px - nx * back, pz - nz * back
                    key = "%s|%d|%d|%d" % (owner, int(side), row, int(k * SLOT_STEP))
                    rng = random.Random(zlib.crc32(key.encode()))
                    if rng.random() < reg[5]:
                        k += 1
                        continue
                    mix = dict(reg[4])
                    for t in list(mix):
                        if (t in ARTERIAL_ONLY and (row > 0 or lanes < 2)) or not far_from_kind(t, qx, qz):
                            mix.pop(t)
                    got = None
                    order = []
                    names = sorted(mix)
                    weights = [mix[n] for n in names]
                    while names:
                        pick = rng.choices(range(len(names)), weights)[0]
                        order.append(names.pop(pick))
                        weights.pop(pick)
                    for t in order:
                        # the row line is where the front stands; sample the lot's centre along the row
                        w = aabbs[t][2] - aabbs[t][0]
                        adv = w / 2.0 + ALLEY
                        j = k + int(round(adv / SLOT_STEP))
                        if j >= len(pts_rows):
                            continue
                        cx_, cz_, cnx, cnz, cy_ = pts_rows[j]
                        # the frontage row's slab reaches the footway (short of its edge, never over it)
                        got = try_place(t, cx_ - cnx * back, cz_ - cnz * back, cnx, cnz, key, reg, cy_,
                                        (KERB_GAP + 0.3 - LOT_FOOTWAY_GAP) if row == 0 else 0.0,
                                        kerbed)
                        if got:
                            k = j + int(math.ceil((w / 2.0 + ALLEY) / SLOT_STEP))
                            break
                    if got:
                        placed.append(got)
                        counts[got["type"]] = counts.get(got["type"], 0) + 1
                        seen_kind.setdefault(got["type"], []).append((got["pos"][0], got["pos"][2]))
                    else:
                        k += 1
    grow_lots(field, placed)
    shops = 0
    for b in placed:
        if b["type"] in SHOP_TYPES:
            b["scene"] = b["type"] + "_Shop"
            shops += 1
    print("island_buildings: %d shops are always open (%s)" % (shops, ", ".join(sorted(SHOP_TYPES))))
    for anchors, suffix, what in ((PUBLIC_BUILDINGS, "_Shop", "ALWAYS OPEN"), (OPEN_BUILDINGS, "_Open", "ENTERABLE")):
        for ox, oz, why in anchors:
            near = min(placed, key=lambda b: (b["pos"][0] - ox) ** 2 + (b["pos"][2] - oz) ** 2, default=None)
            if near is None or math.hypot(near["pos"][0] - ox, near["pos"][2] - oz) > OPEN_MATCH:
                print("island_buildings: no building within %.0f m of (%.0f, %.0f) -- %s" % (OPEN_MATCH, ox, oz, why))
                continue
            near["scene"] = near["type"] + suffix
            print("island_buildings: %s at (%.1f, %.1f) is %s (%s)" % (near["scene"], near["pos"][0],
                                                                        near["pos"][2], what, why))
    placed.sort(key=lambda b: (b["pos"][0], b["pos"][2]))
    by_region = {}
    for b in placed:
        by_region[b["region"]] = by_region.get(b["region"], 0) + 1
    doc = {"schema": 1, "source": "tools/island_buildings.py derive", "network_y": ny,
           "counts": dict(sorted(counts.items())), "regions": dict(sorted(by_region.items())),
           "buildings": placed}
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    write_sidewalks(sidewalks)
    print("island_buildings: %d buildings %s by region %s -> %s" % (len(placed), doc["counts"], doc["regions"],
                                                                    os.path.relpath(OUT, ROOT)))


# ------------------------------------------------------------------------------------------ write

HOLDER = "BuildingZones"
SUB_PREFIX = "Zone_bld_"
NODE_ID_BASE = 910016000


def cell_of(x, z):
    return int(math.floor((x + ORIGIN) / CELL)), int(math.floor((z + ORIGIN) / CELL))


def xf(pos, yaw_deg):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return "Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)" % (c, s, -s, c, pos[0], pos[1],
                                                                                     pos[2])


# The lot is WHITE TILE, not plain concrete (PLAN.md 3.18i, user: "the floor in Japanese buildings and stores is
# mostly white square tile ... as long as the internal floor is white it can run out past the building"). It is
# `M_ConcreteTile` tinted near-white and laid at a 0.6 m tile, so the forecourt a player crosses to a shop door
# and the floor inside it are one surface.
LOT_MATERIAL = "res://assets/world_source/kits/road_kit/materials/M_TileWhite.tres"

# ... and the slab's TOP sits this far BELOW the building's own origin (PLAN.md 3.18j, user-reported: "the gas
# station floor z-fights the station floor below it"). A composite draws its own apron at its origin height and
# `island_buildings` puts this slab under the same footprint, so the two were exactly coplanar -- which is what
# z-fighting IS, and no depth bias fixes it honestly. A Japanese shop floor stands a little above its forecourt
# anyway (10-15 cm, for drainage), so the slab dropping a couple of centimetres is both the fix and the look; it
# is far under `MovementController.stepHeight` (0.35 m), so nothing has to climb it.
LOT_DROP = 0.02


def lot_boxes(b):
    """(world transform rows [12 floats], size, centre) of a building's lot slab: its local rect, from the lot's top
    (the building's origin height) down `lot_depth`."""
    x0, z0, x1, z1 = b["lot"]
    depth = b["lot_depth"]
    sx, sz = x1 - x0, z1 - z0
    lx, lz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)
    ox = b["pos"][0] + lx * c + lz * s
    oz = b["pos"][2] - lx * s + lz * c
    oy = b["pos"][1] - LOT_DROP - depth / 2.0
    return (c, s), (sx, depth, sz), (ox, oy, oz)


def scene_of(b):
    return b.get("scene", b["type"])


def cell_scene(name, blds):
    types = sorted({scene_of(b) for b in blds})
    ids = {t: str(i + 1) for i, t in enumerate(types)}
    out = ["[gd_scene format=3]\n\n"]
    for t in types:
        out.append('[ext_resource type="PackedScene" path="%s/%s.tscn" id="%s"]\n' % (BLD_RES, t, ids[t]))
    lots = [b for b in blds if "lot" in b]
    if lots:
        out.append('[ext_resource type="Material" path="%s" id="lotmat"]\n\n' % LOT_MATERIAL)
        # ONE draw call for every slab of the cell: a unit box, scaled per instance (the material is world-space
        # triplanar, so a scaled box is not a stretched texture)
        out.append('[sub_resource type="BoxMesh" id="LotBox"]\nmaterial = ExtResource("lotmat")\n\n')
        buf = []
        for b in lots:
            (c, s), (sx, sy, sz), (ox, oy, oz) = lot_boxes(b)
            buf += [c * sx, 0.0, s * sz, ox, 0.0, sy, 0.0, oy, -s * sx, 0.0, c * sz, oz]
        out.append('[sub_resource type="MultiMesh" id="Lots"]\ntransform_format = 1\ninstance_count = %d\n'
                   'mesh = SubResource("LotBox")\nbuffer = PackedFloat32Array(%s)\n\n'
                   % (len(lots), ", ".join("%.4f" % v for v in buf)))
        for k, b in enumerate(lots):
            _cs, (sx, sy, sz), _o = lot_boxes(b)
            out.append('[sub_resource type="BoxShape3D" id="LotShape%d"]\nsize = Vector3(%.3f, %.3f, %.3f)\n\n'
                       % (k, sx, sy, sz))
    out.append('[node name="%s" type="Node3D"]\n' % name)
    for k, b in enumerate(blds):
        out.append('\n[node name="%s_%03d" parent="." instance=ExtResource("%s")]\ntransform = %s\n'
                   % (scene_of(b), k, ids[scene_of(b)], xf(b["pos"], b["yaw"])))
    if lots:
        out.append('\n[node name="Lots" type="MultiMeshInstance3D" parent="."]\nmultimesh = SubResource("Lots")\n')
        out.append('\n[node name="LotCollision" type="StaticBody3D" parent="."]\ncollision_mask = 0\n')
        for k, b in enumerate(lots):
            (c, s), _size, (ox, oy, oz) = lot_boxes(b)
            out.append('\n[node name="Lot%d" type="CollisionShape3D" parent="LotCollision"]\n'
                       'transform = Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)\n'
                       'shape = SubResource("LotShape%d")\n' % (k, c, s, -s, c, ox, oy, oz, k))
    return "".join(out)


def ped_cells():
    """[(gx, gz, count, region, footway metres)] -- one crowd per building cell that has footway.

    The length is measured over the cell's INSCRIBED circle, not its square, because that is the footway
    `ZoneManager` can actually pick from: `buildPedCrowd` asks `Sidewalks.randomNear(centre, size/2)`. Measuring
    the square would ask for peds the placement cannot seat, and the difference would show as a zone quietly
    short of its count."""
    doc = json.load(open(SIDEWALKS))
    lengths = {}
    for w in doc["sidewalks"]:
        pts = w["points"]
        for a, b in zip(pts, pts[1:]):
            mx, mz = (a[0] + b[0]) / 2.0, (a[2] + b[2]) / 2.0
            gx, gz = cell_of(mx, mz)
            cx, cz = (gx + 0.5) * CELL - ORIGIN, (gz + 0.5) * CELL - ORIGIN
            if math.hypot(mx - cx, mz - cz) > CELL / 2.0:
                continue
            lengths[(gx, gz)] = lengths.get((gx, gz), 0.0) + math.dist((a[0], a[2]), (b[0], b[2]))
    out = []
    for (gx, gz), metres in sorted(lengths.items()):
        cx, cz = (gx + 0.5) * CELL - ORIGIN, (gz + 0.5) * CELL - ORIGIN
        r = region_of(*godot_xz(cx, cz))       # godot_xz is its own inverse: record (x, y) = godot (x, -z)
        name = r[0] if r else None
        n = max(1, min(PED_MAX, int(round(metres / 100.0 * PED_DENSITY[name]))))
        out.append((gx, gz, n, name or "-", metres))
    return out


def ped_in_range(cells, load=PED_LOAD):
    """The worst and median number of pedestrians a player can have streamed at once -- the number the crowd's
    cost is actually paid on (PLAN.md 3.6d: the cliff is the physics tick, not the total population)."""
    pts = [((gx + 0.5) * CELL - ORIGIN, (gz + 0.5) * CELL - ORIGIN, n) for gx, gz, n, _r, _m in cells]
    totals = []
    for px, pz, _n in pts:
        totals.append(sum(m for qx, qz, m in pts if math.hypot(px - qx, pz - qz) <= load))
    totals.sort()
    return (totals[len(totals) // 2], totals[-1]) if totals else (0, 0)


def patch_peds(text, cells, network_y):
    """The `PedZones` block: one geometry-less Zone + ZoneMarker per cell, carrying one sidewalk SpawnConfig."""
    sections = itz.split_sections(text)
    ids, added = {}, []
    counter = itz.next_ext_id(sections)
    uids = dict(itz.SCRIPT_UIDS)
    uids[SPAWN_SCRIPT] = SPAWN_UID
    for path in (itz.ZONE_SCRIPT, itz.MARKER_SCRIPT, SPAWN_SCRIPT):
        rid = itz.ext_resource_id(sections, path)
        if rid is None:
            rid = "gen_%d" % counter
            counter += 1
            added.append('[ext_resource type="Script" uid="%s" path="%s" id="%s"]\n\n' % (uids[path], path, rid))
        ids[path] = rid
    sub, nodes = [], ['[node name="%s" type="Node" parent="." unique_id=%d]\n\n' % (PED_HOLDER, PED_NODE_ID_BASE)]
    for i, (gx, gz, n, _region, _m) in enumerate(cells):
        cx, cz = (gx + 0.5) * CELL - ORIGIN, (gz + 0.5) * CELL - ORIGIN
        sub.append('[sub_resource type="Resource" id="%s%d_%d"]\n'
                   'script = ExtResource("%s")\n'
                   'faction = "%s"\n'
                   'count = %d\n'
                   'weapon_scene_path = ""\n'
                   'behavior = "sidewalk"\n\n'
                   % (PED_CFG_PREFIX, gx, gz, ids[SPAWN_SCRIPT], PED_FACTION, n))
        sub.append('[sub_resource type="Resource" id="%s%d_%d"]\n'
                   'script = ExtResource("%s")\n'
                   'zone_id = "ped_island_%d_%d"\n'
                   'size = Vector3(%g, 20, %g)\n'
                   'load_radius = %.1f\n'
                   'unload_radius = %.1f\n'
                   'spawn_configs = Array[ExtResource("%s")]([SubResource("%s%d_%d")])\n\n'
                   % (PED_ZONE_PREFIX, gx, gz, ids[itz.ZONE_SCRIPT], gx, gz, CELL, CELL, PED_LOAD, PED_UNLOAD,
                      ids[SPAWN_SCRIPT], PED_CFG_PREFIX, gx, gz))
        nodes.append('[node name="Ped_%d_%d" type="Node3D" parent="%s" unique_id=%d]\n'
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                     'script = ExtResource("%s")\n'
                     'zone = SubResource("%s%d_%d")\n'
                     'show_debug_volume = false\n\n'
                     % (gx, gz, PED_HOLDER, PED_NODE_ID_BASE + 1 + i, cx, network_y, cz,
                        ids[itz.MARKER_SCRIPT], PED_ZONE_PREFIX, gx, gz))

    def generated(header):
        if header.startswith("[sub_resource"):
            rid = itz.attr(header, "id") or ""
            return rid.startswith(PED_ZONE_PREFIX) or rid.startswith(PED_CFG_PREFIX)
        if header.startswith("[node"):
            return itz.attr(header, "name") == PED_HOLDER or itz.attr(header, "parent") == PED_HOLDER
        return False

    return itz.splice(sections, generated, sub, nodes, ext=added)


def write(check):
    doc = json.load(open(OUT))
    cells = {}
    for b in doc["buildings"]:
        cells.setdefault(cell_of(b["pos"][0], b["pos"][2]), []).append(b)
    changed = []
    want = set()
    os.makedirs(CELL_DIR, exist_ok=True)
    for (gx, gz), blds in sorted(cells.items()):
        name = "Bld_island_%d_%d" % (gx, gz)
        path = os.path.join(CELL_DIR, name + ".tscn")
        want.add(name + ".tscn")
        body = cell_scene(name, blds)
        if not os.path.exists(path) or open(path).read() != body:
            changed.append(path)
            if not check:
                open(path, "w").write(body)
    for f in os.listdir(CELL_DIR):
        if f.startswith("Bld_island_") and f.endswith((".tscn", ".scn")) and f.split(".")[0] + ".tscn" not in want:
            changed.append(os.path.join(CELL_DIR, f))
            if not check:
                os.remove(os.path.join(CELL_DIR, f))
    # the World.tscn block
    text = open(SCENE).read()
    sections = itz.split_sections(text)
    zone_ext = itz.ext_resource_id(sections, itz.ZONE_SCRIPT)
    marker_ext = itz.ext_resource_id(sections, itz.MARKER_SCRIPT)
    sub, nodes = [], ['[node name="%s" type="Node" parent="." unique_id=%d]\n\n' % (HOLDER, NODE_ID_BASE)]
    for i, ((gx, gz), blds) in enumerate(sorted(cells.items())):
        zid = "bld_island_%d_%d" % (gx, gz)
        cx, cz = (gx + 0.5) * CELL - ORIGIN, (gz + 0.5) * CELL - ORIGIN
        sub.append('[sub_resource type="Resource" id="%s%d_%d"]\n'
                   'script = ExtResource("%s")\n'
                   'zone_id = "%s"\n'
                   'size = Vector3(%g, 120, %g)\n'
                   'load_radius = %.1f\n'
                   'unload_radius = %.1f\n'
                   'geometry_path = "%s/Bld_island_%d_%d.tscn"\n'
                   'geometry_world_placed = true\n'
                   'geometry_world_transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)\n\n'
                   % (SUB_PREFIX, gx, gz, zone_ext, zid, CELL, CELL, LOAD, UNLOAD, CELL_RES, gx, gz))
        nodes.append('[node name="Bld_%d_%d" type="Node3D" parent="%s" unique_id=%d]\n'
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                     'script = ExtResource("%s")\n'
                     'zone = SubResource("%s%d_%d")\n'
                     'show_debug_volume = false\n\n'
                     % (gx, gz, HOLDER, NODE_ID_BASE + 1 + i, cx, doc["network_y"], cz, marker_ext, SUB_PREFIX, gx, gz))

    def generated(header):
        if header.startswith("[sub_resource"):
            return (itz.attr(header, "id") or "").startswith(SUB_PREFIX)
        if header.startswith("[node"):
            return itz.attr(header, "name") == HOLDER or itz.attr(header, "parent") == HOLDER
        return False
    new = itz.splice(sections, generated, sub, nodes)
    peds = ped_cells()
    new = patch_peds(new, peds, doc["network_y"])
    if new != text:
        changed.append(SCENE)
        if not check:
            open(SCENE, "w").write(new)
    p50, worst = ped_in_range(peds)
    print("island_buildings: %d pedestrians over %d crowd zones (%d in range at once at worst, %d typical)"
          % (sum(n for _gx, _gz, n, _r, _m in peds), len(peds), worst, p50))
    print("island_buildings: %d buildings in %d cells; %s" % (len(doc["buildings"]), len(cells),
                                                              "%d files change" % len(changed) if changed
                                                              else "up to date"))
    return 1 if (check and changed) else 0


def clearance(check):
    """PLAN.md 3.18a's gate: no SOLID street prop may stand on the walk line the ambient crowd follows.

    Measured from the other side of the pipeline -- the placer's own output (`point_furniture.place`, the thing
    that really puts a planter down) against the derived `IslandSidewalks.json` -- so it cannot agree with
    `furniture_strip` by construction. A prop further than `AWAY` from any walk line is not on a footway the
    crowd uses (a median lamp, a barrier lamp, a pole on a road with no sidewalk) and is not this check's
    business."""
    import glob
    for d in (os.path.join(ROOT, "blender", "lib"), os.path.join(ROOT, "blender", "addons", "road_kit_authoring")):
        if d not in sys.path:
            sys.path.insert(0, d)
    import point_edges as ped
    import point_kit as pk
    import point_furniture as pfu
    import point_ground as pg

    AWAY = 12.0
    net = pm.load_network(RECORD)
    grid = pg.load_ground(GROUND)
    solved = ped.solve_all(net, grid)
    table = pfu.load()
    lanes_doc = {"lanes": [], "junctions": []}
    for lk in sorted(glob.glob(os.path.join(PIECES, "Roads_IslandRoads_island_*.lanekit.json"))):
        with open(lk) as fh:
            d = json.load(fh)
        lanes_doc["lanes"] += d.get("lanes", [])
        lanes_doc["junctions"] += d.get("junctions", [])
    kit = pk.load()
    styles = {n: pk.resolve(r, kit) for n, r in net.roads.items()}
    default_mark = pk.resolve(object(), kit).material("mark_w")
    fur = pfu.place(table, solved, lanes_doc, lambda l: True, lambda s: True, lambda j: True,
                    lambda lane: (styles.get(lane.get("road_name")) or pk.resolve(object(), kit)).material("mark_w")
                    if styles.get(lane.get("road_name")) is not None else default_mark, grid)

    segs = []
    for w in json.load(open(SIDEWALKS))["sidewalks"]:
        pts = w["points"]
        segs += [(a[0], a[2], b[0], b[2]) for a, b in zip(pts, pts[1:])]
    cell, idx = 20.0, {}
    for k, (x0, z0, x1, z1) in enumerate(segs):
        for cx in range(int(math.floor(min(x0, x1) / cell)) - 1, int(math.floor(max(x0, x1) / cell)) + 2):
            for cz in range(int(math.floor(min(z0, z1) / cell)) - 1, int(math.floor(max(z0, z1) / cell)) + 2):
                idx.setdefault((cx, cz), []).append(k)

    def nearest(x, z):
        best = 1e9
        c = (int(math.floor(x / cell)), int(math.floor(z / cell)))
        cand = set()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cand.update(idx.get((c[0] + dx, c[1] + dz), ()))
        for k in cand:
            x0, z0, x1, z1 = segs[k]
            vx, vz = x1 - x0, z1 - z0
            L2 = vx * vx + vz * vz
            u = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - x0) * vx + (z - z0) * vz) / L2))
            best = min(best, math.hypot(x - x0 - u * vx, z - z0 - u * vz))
        return best

    rows, worst_all = {}, []
    for pl in fur.placements:
        if not pl.get("solid"):
            continue
        a = table.assets[pl["asset"]]
        half = (float(a["collide_pole"][0]) if a.get("collide_pole")
                else max(0.5 * (a["hi"][0] - a["lo"][0]) * a["scale"][0],
                         0.5 * (a["hi"][2] - a["lo"][2]) * a["scale"][2]))
        gx, gz = pl["pos"][0], -pl["pos"][1]            # kit (x, y) -> godot (x, -z)
        d = nearest(gx, gz)
        if d > AWAY:
            continue
        c = d - half - PED_RADIUS
        r = rows.setdefault(pl["asset"], [0, 0, 1e9])
        r[0] += 1
        r[2] = min(r[2], c)
        if c < 0.0:
            r[1] += 1
            worst_all.append((round(c, 2), pl["asset"], round(gx, 1), round(gz, 1), pl.get("road", "")))
    bad = sum(r[1] for r in rows.values())
    print("island_buildings: pedestrian clearance -- %d solid props on a footway, %d block the walk line"
          % (sum(r[0] for r in rows.values()), bad))
    for k in sorted(rows):
        n, b, worst = rows[k]
        print("  %-10s %5d on a footway, %4d blocking, worst clearance %+.2f m" % (k, n, b, worst))
    if worst_all:
        worst_all.sort()
        print("  worst: %s" % (worst_all[:5],))
    return 1 if (check and bad) else 0


def main(argv):
    if argv[:1] == ["derive"] and len(argv) >= 2:
        derive(argv[1])
        return 0
    if argv[:1] == ["write"]:
        return write("--check" in argv)
    if argv[:1] == ["sidewalks"]:
        return sidewalks_only("--check" in argv)
    if argv[:1] == ["clearance"]:
        return clearance("--check" in argv)
    if argv[:1] == ["peds"]:
        cells = ped_cells()
        by = {}
        for gx, gz, n, region, metres in cells:
            r = by.setdefault(region, [0, 0, 0.0])
            r[0] += 1
            r[1] += n
            r[2] += metres
        for region in sorted(by):
            c, n, metres = by[region]
            print("  %-12s %3d cells %5.1f km footway -> %4d peds (%.1f per cell)" % (region, c, metres / 1000.0,
                                                                                      n, n / float(c)))
        p50, worst = ped_in_range(cells)
        print("  total %d peds; streamed at once: %d typical, %d worst (load radius %.0f m)"
              % (sum(n for _gx, _gz, n, _r, _m in cells), p50, worst, PED_LOAD))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
