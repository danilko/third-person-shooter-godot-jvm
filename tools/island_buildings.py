#!/usr/bin/env python3
"""island_buildings.py -- the island's buildings, placed by REGION along its streets and streamed per 252 m cell
(PLAN.md 3.6 "regions, then detail"; 3.13 step 7).

    python3 tools/island_buildings.py derive <heights.f32>     # writes IslandBuildings.json (needs a terrain dump)
    python3 tools/island_buildings.py write [--check]          # cell scenes + the BuildingZones / PedZones blocks
    python3 tools/island_buildings.py peds                     # the derived crowd density, per region
    python3 tools/island_buildings.py lots [--check]           # trim lot slabs so no two overlap (no dump needed)

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
import glob
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
# Per SCENE, like the road map's bake: the places are a fact about ONE world, and one fixed path put the
# island's shops on DebugWorld's map at island coordinates.
PLACES = os.path.join(ROOT, "src/main/resources/com/openworld/world/places/World.places.json")   # read at runtime
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
ALLEY = 1.5            # kept free on a building's sides and back (half the alley between two) -- the default
# ...and per district (user, 2026-09-26: "more occupied, like the PLATEAU city"): central Tokyo's median gap to a
# neighbour is 0.2 m, 59% touching (measure_plateau_blocks); housing keeps a narrow side gap
# Outside the 防火地域 core a building keeps about ONE PERSON's width to its neighbour (user, 2026-09-26: 0.5 each
# side = a 1 m gap; the Civil Code asks 50 cm from the boundary, i.e. the same 1 m between two houses)
REGION_ALLEY = {"downtown": 0.25, "nightlife": 0.2, "west_ekimae": 0.2, "west_centre": 0.5, "city": 0.5,
                "residential": 0.6, "residential_north": 0.6, "residential_west": 0.8, "light_industry": 0.6,
                "light_industry_w": 0.5, "bay_processing": 0.8}


def alley_of(reg):
    return REGION_ALLEY.get(reg[0], ALLEY) if reg else ALLEY
RELIEF = 0.7
REFUSED = {}          # why each tried lot was refused (derive prints it)
SIDEWALK_STEP = 6.0    # sidewalk path sample spacing
KERB_H = 0.15          # a footway stands this far above its carriageway
LOT_BURY_TOL = 0.05    # the ground may stand this far above a lot's top (inside it: the slab covers it)
LOT_MAX_STEP = 1.2     # ... and fall at most this far below it
LOT_GROW_MAX = 20.0    # a lot grows at most this far to its back / front toward the pavement
LOT_GROW_SIDE = 30.0   # ... and this far along its street (to the corner)
PAD_WALK = 4.0         # a junction pad's corner footway width, for the lot-stop mask
LOT_SKIRT = 0.3        # the slab reaches this far below the lowest ground under it
LOT_FOOTWAY_GAP = 0.05 # the frontage slab stops this short of the footway's outer edge
SLOT_STEP = 1.0        # how far along a row a rejected slot moves before trying again (3.0 left gaps)

# --- the 路地: how a block behind the frontage is reached (PLAN.md 3.18c, user's own design, and it is the one
# rule in it that is Japanese LAW rather than style). 接道義務 (Building Standards Act art. 43) says every
# buildable lot must front a road at least 4 m wide for at least 2 m, so a lot BEHIND the frontage row cannot
# exist without a private way out to the street -- a 私道, or the stem of a flag lot (旗竿地の竿部分). That is
# why a Japanese block is full of narrow alleys, and it is why the rows behind the frontage here had no reason
# to be reachable: nothing reserved the way in.
#
# So the frontage row now leaves a gap every PASSAGE_EVERY metres, running from the footway back past the row,
# and no lot may stand in it or grow into it. Dead ends are allowed and not worth avoiding: a Japanese alley is
# very often a 袋小路, and fire access is satisfied by the frontage, not by a loop.
PASSAGE_EVERY = 80.0   # along the frontage: about one per block side (user, 2026-09-26; was 46)
BACK_ACCESS = 3.0      # a back-row lot must have a 路地 / lane / street within this (接道, the 旗竿地 strip)
PASSAGE_W = 3.2        # wide enough for a scooter and two people to pass, the ordinary 路地
PASSAGE_DEPTH = 34.0   # back from the footway: past the frontage row's lot, into the block (the least)
PASSAGE_DEPTH_MAX = 80.0   # ...deeper where a district fills its blocks several rows deep (rows x pitch + 16)
# R9 (PLAN.md 3.32/3.34): each cell carries ONE merged, vertex-coloured box per building (its HLOD), shown only
# beyond HLOD_BEGIN of the cell's centre; every building's own Mesh has the HLOD as its `visibility_parent`, so
# Godot shows the detail exactly while the HLOD is hidden for being near. One draw call per far cell instead of a
# few hundred. The boxes are written here (`hlod/boxes.json`, the placement's facts) and turned into meshes by
# `tools/godot/build_building_hlod.gd` (a Godot tool: an ArrayMesh is a binary resource).
HLOD_BEGIN = 450.0
HLOD_MARGIN = 40.0
HLOD_DIR = os.path.join(BLD_DIR, "cells", "hlod")
HLOD_RES = CELL_RES + "/hlod"
HLOD_GLASS = {"OfficeMid": (78.0, 88.0, 102.0)}    # a curtain wall reads as dark glass, not as its facade tone
LOAD = 800.0           # a cell's buildings stream in within this of its centre
UNLOAD = 1100.0

# --- one tone per BUILDING (PLAN.md 3.18p, user 2026-09-21: "every facade is the same grey; Tokyo is a
# MIXTURE"). The merged mesh is per TYPE and shared, so the variation is an INSTANCE override: the cell scene
# ext_resources the four facade materials once and sets `surface_material_override/<facade surface>` per node.
# Neither of the two facts it needs is written down twice -- which materials exist is the retone tool's
# `facade_tones.json`, and which merged SURFACE is the facade is the meta `build_building_scenes.gd` writes into
# each type's own scene, because only the merge knows the order.
FACADE_TONES_JSON = os.path.join(ROOT, "assets/world_source/kits/quaternius_downtown_city/materials",
                                 "facade_tones.json")
FACADE_MAT_RES = "res://assets/world_source/kits/quaternius_downtown_city/materials/%s.tres"

# region: (name, record-frame box (x0, y0, x1, y1), rows, pitch, mix, skip chance, tone weights).
# First box that holds a point wins, so the order IS the priority.
#
# `tone bias` is None (draw facade tones in PLATEAU's own measured shares, PLAN.md 3.19(e)) or "dark" (the same
# shares, leaned towards the darker colours: a working district reads GREYER than a residential street). A tone
# is a measured central-Tokyo wall colour, so the bias moves the mixture, never the palette.
#
# THE WORKING WATERFRONT IS A BAND, NOT A LINE (user, 2026-09-21: "the harbour above should be industry +
# downtown ... then residential at the upward border instead of directly harbour -> residential"). The harbour's
# quays used to meet the residential grid across one street: a container terminal on one side, flats on the
# other, with nothing between. `industry` is the transition a real port city has -- warehouses, small factories,
# a few offices and a konbini for the workers -- and it is measured, not guessed: x -1000..200, z 600..1040 is
# 100% land at 0.6 m, and it sits exactly between the harbour box's north edge (z 1040) and the residential
# grid, which keeps its own box and simply loses the overlap to this one.
# THE ISLAND READS AS A GRADIENT FROM THE PORT TO THE FIELDS (user, 2026-09-21), and the region order below
# is that gradient, bottom (+z, the sea) to top (-z, the hills):
#
#     harbour -> industry -> residential -> nightlife/downtown/city (most urban) -> farm + beach (quietest)
#
# `nightlife` is the 歓楽街 the user asked for -- a Kabukichō beside the station, which is the relationship the
# real one has to Shinjuku: 雑居ビル packed shoulder to shoulder, no flats, and the same grey tone bias as the
# working districts. It is inside downtown's box, so it must come FIRST to win the first-match rule.
REGIONS = (
    ("nightlife", (520.0, 180.0, 980.0, 560.0), 1, 20.0,
     {"PencilBuilding": 6, "ShopHouse": 3, "KonbiniS": 1, "OfficeMid": 0.8, "FamilyRestaurant": 0.5},
     0.0, "dark"),
    # RESIDENTIAL WRAPS THE CITY (user, 2026-09-21, drawn on the district plan: "add resident around city
    # before castle/farmland"). Both bands are MEASURED, because a region only does anything where there is
    # street frontage on flat land -- buildings stand on road frontages, never on a box:
    #   north  x -330..1700  z -960..-700 -- 7.7 km of street, 7.4 km buildable (97%). It populates like `farm`
    #          (4.2 km) or `harbour` (4.0), so this is a real district. It takes the top slice of `city`, which
    #          is the quieter ring the user asked for between the urban core and the fields.
    #   west   x -900..-150 z -400..200 -- 1.5 km buildable of 4.6 km, because it is the massif. What it can
    #          be is a thin coastal 集落 along `kaigan_dori` at the mountain's foot, around the castle -- the
    #          honest shape of that ground, not a suburb. TRIMMED in x to where its buildings actually landed
    #          (x -828..-145): a box that claims the mountain costs nothing to the PLACEMENT, which only ever
    #          builds on frontage, but it makes the district plan read wrong and it makes the HUD announce
    #          "Residential West" while you stand on a 300 m peak, because `Places.regionAt` reads these boxes.
    ("residential_north", (-330.0, 700.0, 1700.0, 960.0), 1, 20.0,
     {"Apartment": 3, "ShopHouse": 2, "Mansion": 1, "KonbiniS": 0.5, "KonbiniL": 0.4, "GasStation": 0.3},
     0.15, None),
    ("residential_west", (-900.0, -200.0, -150.0, 400.0), 1, 18.0,
     {"Apartment": 3, "ShopHouse": 1.5, "Mansion": 0.8, "KonbiniS": 0.3}, 0.3, None),
    ("downtown", (150.0, 40.0, 1300.0, 720.0), 1, 24.0,
     {"OfficeMid": 4, "OfficeBlock": 1.5, "OfficeTower": 1, "PencilBuilding": 4, "Mansion": 2, "ShopHouse": 1.5,
      "KonbiniS": 1, "FamilyRestaurant": 0.3},
     0.0, None),
    ("city", (-150.0, -330.0, 1700.0, 960.0), 1, 22.0,
     {"Mansion": 3, "ShopHouse": 3, "PencilBuilding": 2, "Apartment": 2, "KonbiniS": 1, "OfficeMid": 0.5, "OfficeBlock": 0.3,
      "FamilyRestaurant": 0.6, "KonbiniL": 0.6, "GasStation": 0.5}, 0.05, None),
    # THE WEST SUB-CENTRE 副都心 (user, 2026-09-26: "combine the south-west with a CBD"): the second business district,
    # round the Blue line's Residential station where the housing meets the 準工業 district -- the Kamata / Kawasaki
    # shape: mid-rise offices and 雑居ビル on the station front, shops, flats over them. The main CBD stays inside C1.
    # It must come before the 準工業 rows, whose boxes it overlaps, to win the first-match rule.
    # ...and its 駅前商店街: the shopping street round the station itself -- shop-houses shoulder to shoulder, a konbini,
    # a family restaurant -- with the station shopping centre (the `west_station_mall` site, island_sites) beside it
    ("west_ekimae", (-900.0, -640.0, -560.0, -400.0), 1, 12.0,
     {"ShopHouse": 5, "PencilBuilding": 2, "KonbiniS": 1, "FamilyRestaurant": 0.4}, 0.0, None),
    ("west_centre", (-950.0, -700.0, -400.0, -380.0), 1, 22.0,
     {"OfficeMid": 3, "OfficeBlock": 0.8, "PencilBuilding": 2.5, "ShopHouse": 2.5, "Mansion": 1.5, "KonbiniS": 1,
      "FamilyRestaurant": 0.5,
      "KonbiniL": 0.3}, 0.05, None),
    ("harbour", (-820.0, -2050.0, 250.0, -1040.0), 1, 30.0, {"Warehouse": 1}, 0.2, "dark"),
    # BAY PROCESSING 水産加工 (PLAN.md 3.30 v3, 2026-09-26): the bay's west shore -- processing sheds and the 市場食堂
    # seafood diners along the quay. Existing types stand in (Warehouse = sheds, FamilyRestaurant = diners) until the
    # market hall and diner models exist.
    ("bay_processing", (150.0, -1000.0, 300.0, -600.0), 1, 26.0,
     {"Warehouse": 3, "FamilyRestaurant": 1, "KonbiniS": 0.3}, 0.2, "dark"),
    # THE 準工業 BELT (v7 item 2): ~140 m between industry and the housing, north of industry and along its west edge
    # -- 町工場, trucking depots, used-car lots, coin laundries. Stand-ins: ShopHouse (a works with a flat over it),
    # Warehouse (a depot), ParkingLot8 (a used-car lot), KonbiniS, GasStation.
    ("light_industry", (-1400.0, -600.0, 300.0, -460.0), 1, 22.0,
     {"ShopHouse": 2, "Warehouse": 2, "ParkingLot8": 0.5, "KonbiniS": 0.3, "GasStation": 0.2}, 0.3, "dark"),
    # THE SOUTH-WEST 準工業 DISTRICT (user, 2026-09-26: "combine the south-west with the light industry"): the housing's
    # industrial edge and the west third of the old industry box are ONE mixed district, the Ota / Kamata 町工場 town --
    # small works with a flat over them, workers' flats, depots and a few used-car lots on block streets. It has TWO
    # stations on two lines: Light Industry (the Blue line's terminus, x -665) on its west side and Industry (the
    # Harbour line, x 185) past its east edge, so its commuters split instead of all changing at Bay.
    ("light_industry_w", (-1450.0, -1040.0, -300.0, -600.0), 1, 20.0,
     {"ShopHouse": 3, "Apartment": 2, "Warehouse": 1.5, "ParkingLot8": 0.3, "KonbiniS": 0.4, "GasStation": 0.2},
     0.2, "dark"),
    # INDUSTRY: fewer, bigger plots with yards between (v6: "a 200 m grid at 50%") -- one row, a wide pitch, half skipped
    ("industry", (-1000.0, -1040.0, 200.0, -600.0), 1, 60.0,
     {"Warehouse": 4, "OfficeMid": 1, "ShopHouse": 0.5, "KonbiniS": 0.4, "GasStation": 0.3}, 0.5, "dark"),
    ("residential", (-1800.0, -1160.0, -150.0, -200.0), 1, 18.0,
     {"Apartment": 4, "ShopHouse": 2, "Mansion": 1, "KonbiniL": 0.6, "GasStation": 0.4, "FamilyRestaurant": 0.3,
      "KonbiniS": 0.4}, 0.15, None),
    # the SUBURB as a low-density beach resort (v3: "fewer, larger buildings ... 55% occupancy"): one row, wide pitch
    ("suburb", (850.0, -1060.0, 1800.0, -330.0), 1, 30.0,
     {"Apartment": 4, "ShopHouse": 1.5, "Mansion": 1, "KonbiniL": 0.6, "GasStation": 0.4,
      "FamilyRestaurant": 0.4}, 0.45, None),
    ("farm", (350.0, 960.0, 1850.0, 1900.0), 1, 30.0, {"Apartment": 2, "Warehouse": 1, "KonbiniL": 0.2},
     0.65, None),
)
ARTERIAL_ONLY = {"GasStation", "KonbiniL", "FamilyRestaurant"}
# THE CAR PARK IS AN ADDITION, NOT PART OF THE STORE (user, 2026-09-25: "extract the parking lot out as an addition
# instead of the left-over konbini lot"). A type named here gets that car park placed BESIDE it on the same row when
# the land allows -- to its right along the street, else its left -- and stands without one otherwise.
PARKING = {"KonbiniL": "ParkingLot8"}
# Every building ships SHUT (user, 2026-09-19), with two exceptions, both placed as a variant of the same type:
# * `<Type>_Shop` -- unlocked, automatic doors: the shops a player walks into as ordinary play (GTA's konbini, diner,
#   petrol station, station hall) and the player's home base;
# * `<Type>_Open` -- `world.Door` nodes LOCKED until a MISSION unlocks them (KonbiniMission does).
SHOP_TYPES = {"KonbiniS", "KonbiniL", "FamilyRestaurant", "GasStation", "GasKiosk", "StationBuilding",
              "StationRural"}
PUBLIC_BUILDINGS = (      # (Godot x, z, why, wanted TYPE, "", ROLE): a specific building that is always open
    # The WEAPON COUNTER (user, 2026-09-26: "large store will have all weapons, small one only pistol/light"): the
    # nearest LARGE konbini to the island's centre -- only a KonbiniL stocks the whole catalog. Resolved FIRST, so
    # the safe house can be found beside it. Its pads live in World.tscn (`WeaponCounter`, always loaded).
    (80.0, -3.0, "the konbini beside the safe house (every konbini sells weapons)", "KonbiniL", "", "armoury"),
    # The player's SAFE HOUSE (user, 2026-09-22): where a player starts and respawns -- `write` puts World.tscn's
    # `PlayerSpawn`, the `Player` and the starting car at its front door. A shop-house near that konbini.
    # `None` = "beside the building the named role resolved to".
    (None, "armoury", "the player's safe house", "ShopHouse", "", "safehouse"),
)
# every konbini is a weapon shop (user, 2026-09-26: "no need for a different weapon counter"), so the store beside
# the safe house is on the map as an ordinary Convenience Store; `armoury` is only how the safe house finds its street
ROLE_PLACES = {"safehouse": ("Safehouse", 2)}
ARMOURY_REACH = 1200.0   # the weapon counter is the nearest large konbini, however far (there are only a few)
# Every konbini sells weapons (free for now), each store in its OWN frame (front +Z):
# * KonbiniS (12.74 x 18.2 m): the clear aisle between the right-hand gondola run (x <= 2.67) and the side wall
#   (x 6.37), from the drink wall's front (z -6.29) to the customer toilet room (z >= 1.82) -- pistols and light
#   weapons only;
# * KonbiniL (21.84 m square): the clear floor between the gondola run at x 2.3 (<= 2.67) and the counter
#   (x >= 9.08), south of the WC partition (z -3.64) -- the whole catalog, in a 3 x 4 grid.
KONBINI_PADS = {
    "KonbiniS": (("PIS1", 3.7, -5.3), ("PIS2", 5.1, -5.3), ("REV1", 3.7, -4.1), ("DUP1", 5.1, -4.1),
                 ("SMG1", 3.7, -2.9), ("MEW1", 5.1, -2.9), ("FRG1", 3.7, -1.7)),
    "KonbiniL": tuple((wid, 4.0 + 1.3 * (i % 3), -2.3 + 1.3 * (i // 3)) for i, wid in enumerate(
        ("PIS1", "PIS2", "REV1", "DUP1", "SMG1", "ASR1", "ASR2", "SHG1", "SNR1", "ATL1", "FRG1", "MEW1"))),
}
PAD_SCRIPT = "res://src/main/java/com/openworld/item/WeaponPad.java"
# (Godot x, z, why, wanted TYPE or "", the `Missions` child to move onto it or ""): locked until its mission
# unlocks it, and wins over the two above.
#
# The point is a WISH, not an address. The street grid moved under it once (2026-09-20) and left no building
# within `OPEN_MATCH`, which silently cost the konbini job its shop until `derive` said so. So an anchor now
# names the TYPE it wants and is matched to the nearest one within `ANCHOR_REACH`, and `write` moves the mission
# node onto the building it actually chose -- one owner for "where is this mission", instead of a scene
# transform and a constant here that have to be kept in step by hand.
OPEN_BUILDINGS = (
    (685.0, -336.0, "m01_konbini: the shop the konbini job is played at", "KonbiniS", "M01_Konbini"),
)
OPEN_MATCH = 12.0      # the placement nearest an anchor with no wanted type, within this

# --- WHAT THE MAP CALLS A PLACE (PLAN.md 3.18n, user 2026-09-21: "the map should say WHERE you are").
#
# A place is somewhere you can GO IN or somewhere that names a part of the island, so the test is the one the
# placement already applies: a building whose scene is a `_Shop` or `_Open` variant is by definition enterable,
# and a `SiteZones` entry is a landmark. Nothing new is authored -- this table only gives each kind the short
# label a map draws beside its blip, and says which of them a player sees at map scale.
#
# The labels are English because the HUD's font (Aldrich) carries no CJK glyphs; the Japanese name each type
# already declares in `building_types.json` is the one to switch to when a font that can draw it lands.
PLACE_KINDS = {
    "KonbiniS":         ("Convenience Store", 1),
    "KonbiniL":         ("Convenience Store", 1),
    "FamilyRestaurant": ("Diner", 1),
    "GasStation":       ("Petrol Station", 1),
    "GasKiosk":         ("Petrol Station", 1),
    "StationBuilding":  ("Station", 2),
    "StationRural":     ("Station", 2),
}
SITE_PLACES = {       # a SiteZones / Landmarks child -> its label (a landmark: always drawn)
    "ContainerTerminal": ("Container Terminal", 2),
    "ShuriCastle":       ("Shuri Castle", 2),
    "RainbowBridge":     ("Rainbow Bridge", 2),
    "TokyoTower":        ("Tower", 2),
    "TokyoStation_Shop": ("Central Station", 2),
    "AirportTerminal_Shop": ("Airport", 2),
}
ANCHOR_REACH = 250.0   # ... and the furthest a WANTED TYPE may be found from the wish
SPACING = {"GasStation": 450.0, "KonbiniL": 250.0, "FamilyRestaurant": 350.0, "KonbiniS": 120.0}
SKIP_ROADS = ("shuto_", "shrine_touge", "kaigan_dori", "airport_", "kuko_dori")
TYPES = sorted({t for r in REGIONS for t in r[4]} | set(PARKING.values()) | {"ParkingLot4"})   # + the safe house's car park

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
PED_DENSITY = {"nightlife": 2.6, "downtown": 2.0, "city": 1.2, "residential": 0.8, "residential_north": 0.8,
               "residential_west": 0.5, "suburb": 0.6, "industry": 0.5, "harbour": 0.4, "farm": 0.3,
               "light_industry": 0.6, "light_industry_w": 0.8, "west_centre": 1.6, "west_ekimae": 2.2, "bay_processing": 0.7, None: 0.5}
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
        # the planter is the TREE's socket (3.18m), so it stands where the tree does and reaches its own half
        reach.append(r["tree_kerb_gap"] + max(across(r["tree_assets"][0]),
                                              across("planter") if r.get("tree_planter", True) else 0.0))
    if r.get("planter_spacing", 0.0) > 0.0 and walk >= r["planter_min_footway"]:
        # a standalone planter run, if one is ever turned back on: its CENTRE is at kerb_gap + half
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
        self.passage = np.zeros((self.n, self.n), dtype=bool)       # the 路地: reserved, no lot may stand or grow

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
        res = re.search(r"metadata/site_reserve = PackedFloat64Array\(([^)]*)\)", body)
        if res:        # island_sites writes the reserve outright when the scene stands off its centre
            v = [float(x) for x in res.group(1).split(",")]
            out.append((v[0], v[1], v[2], v[3] + SITE_CLEAR, v[4] + SITE_CLEAR))
            continue
        if size and xf:
            s = [float(v) for v in size.group(1).split(",")]
            t = [float(v) for v in xf.group(1).split(",")]
            out.append((t[9], t[11], math.atan2(t[2], t[0]), s[0] / 2 + SITE_CLEAR, s[2] / 2 + SITE_CLEAR))
    for m in re.finditer(r'\[node name="(\w+)" parent="Landmarks"[^\]]*\]\ntransform = Transform3D\(([^)]*)\)', text):
        t = [float(v) for v in m.group(2).split(",")]
        # the Rainbow Bridge: its towers and anchorages along its own +Z over ~900 m, 60 m wide
        out.append((t[9], t[11], math.atan2(t[2], t[0]), 40.0 + SITE_CLEAR, 480.0 + SITE_CLEAR))
    return out


RAIL_RESERVE = os.path.join(ROOT, "assets/world_source/buildings/IslandRailReserve.json")


LANE_W = 4.0            # a block's THROUGH lane: the 4 m of a Japanese road (建築基準法 42), a fire truck's width
LANE_BLOCK = (1500.0, 40000.0)   # m2: the blocks that get one (smaller is a single plot; larger is not a block)
LANE_MIN = 40.0         # m: a lane shorter than this is not worth one (a thin block is all frontage)
LANE_CELL = 4           # the block search's grid: this many 1 m cells


def through_lanes(field):
    """Each dense block's THROUGH LANE (user, 2026-09-26: "an opening for a car like an entrance on one side and an
    exit on another side, for fire escape / other hazard"). A block is a 4-connected piece of land between roads
    (`field.road`, water a wall too) whose area is in LANE_BLOCK and whose district fills its blocks at least two
    rows deep; its lane is a straight LANE_W strip through its centre, from the road on
    one side to the road on the other, square to the block's edges and across its SHORT side -- a vehicle drives in
    one street and out the opposite one, with no dead end. It is
    reserved like a 路地 (`field.passage`: no lot stands in it) before anything is placed. Returns the passage rows."""
    np = field.np
    import island_ground as ig
    k = LANE_CELL
    n = field.n // k
    road = field.road[:n * k, :n * k].reshape(n, k, n, k).any(axis=(1, 3))
    wet = field.blocked[:n * k, :n * k].reshape(n, k, n, k).all(axis=(1, 3))
    lab, sizes = ig.components(~road & ~wet)
    out = []
    for c in range(1, len(sizes)):
        area = sizes[c] * k * k
        if not LANE_BLOCK[0] <= area <= LANE_BLOCK[1]:
            continue
        js, iss = np.nonzero(lab == c)
        xs = (iss + 0.5) * k - HALF
        zs = (js + 0.5) * k - HALF
        cx, cz = float(xs.mean()), float(zs.mean())
        reg = region_of(cx, -cz)
        if reg is None or reg[2] < 2:
            continue
        # the lane runs SQUARE to the block's streets, across its SHORT side: the rotation of the block's tightest
        # bounding rectangle gives its edges (a PCA axis goes diagonal on a near-square block)
        best = None
        for deg in range(0, 90, 3):
            t = math.radians(deg)
            u = (xs - cx) * math.cos(t) + (zs - cz) * math.sin(t)
            w_ = -(xs - cx) * math.sin(t) + (zs - cz) * math.cos(t)
            ext = (float(u.max() - u.min()), float(w_.max() - w_.min()))
            if best is None or ext[0] * ext[1] < best[0]:
                best = (ext[0] * ext[1], t, ext)
        _a, t, ext = best
        if ext[0] <= ext[1]:
            ux, uz = math.cos(t), math.sin(t)                # across the short side
        else:
            ux, uz = -math.sin(t), math.cos(t)
        ends = []
        for sgn in (1.0, -1.0):
            t, hit = 0.0, None
            while t < 400.0:
                x, z = cx + sgn * ux * t, cz + sgn * uz * t
                i, j = field.idx(x, z)
                if not (0 <= i < field.n and 0 <= j < field.n):
                    break
                if field.road[j, i]:
                    hit = t
                    break
                if lab[min(j // k, n - 1), min(i // k, n - 1)] not in (c, 0):
                    break
                t += 1.0
            ends.append(hit)
        if ends[0] is None or ends[1] is None or ends[0] + ends[1] < LANE_MIN:
            continue
        a, b = ends[0] + 1.0, ends[1] + 1.0                   # a metre into each footway
        mx, mz = cx + ux * (a - b) / 2.0, cz + uz * (a - b) / 2.0
        L = a + b
        yaw = math.atan2(ux, uz)
        ii, jj = field.rect_points(mx, mz, yaw, -LANE_W / 2.0, -L / 2.0, LANE_W / 2.0, L / 2.0)
        if not ii.size:
            continue
        hs = field.heights(ii, jj)
        if float(hs.min()) <= LAND_Z:
            continue
        field.passage[jj, ii] = True
        out.append({"pos": [round(mx, 3), round(float(np.median(hs)) + KERB_H, 3), round(mz, 3)],
                    "yaw": round(math.degrees(yaw), 3), "size": [LANE_W, round(L, 2)], "kind": "through"})
    print("island_buildings: %d block(s) given a %.0f m through lane (in one street, out another)"
          % (len(out), LANE_W))
    return out


def rail_reserve(field):
    """PLAN.md B10: no building stands on the rail corridor, a station's footprint or its car park
    (`island_rail_layout.py --reserve`, record frame -> Godot x, z = x, -y). Absent -> nothing reserved."""
    if not os.path.exists(RAIL_RESERVE):
        return
    d = json.load(open(RAIL_RESERVE))
    half = d["corridor_half"]
    for c in d["corridors"]:
        P = [(q[0], -q[1]) for q in c["pts"]]
        for a, b in zip(P, P[1:]):
            field.block_capsule(a, b, half)
    for bx in d["boxes"]:
        # the box's local +Z runs along (ux, uy) in the record, i.e. (ux, -uy) in Godot x/z
        field.block_box(bx["x"], -bx["y"], math.atan2(bx["ux"], -bx["uy"]), bx["h_across"], bx["h_along"])


DIKE_JSON = os.path.join(ROOT, "assets/world_source/island_dike.json")


def seawall_works(field):
    """The seawall, its beach and the road fill in front of the old coast (`island_reshape.coastal_works`, its
    "works" runs in island_dike.json, Godot x, z on the 2 m dump grid): land now, but nothing a building or a field
    stands on. Absent -> nothing blocked."""
    if not os.path.exists(DIKE_JSON):
        return
    doc = json.load(open(DIKE_JSON))
    np = field.np
    m2 = None
    for key in ("works", "cells"):               # the beach works, and the ring-road dike's embankment
        w = doc.get(key)
        if not w:
            continue
        st = w["step"]
        k = int(round(st / RES))
        if m2 is None:
            m2 = np.zeros((int(round(2 * HALF / st)) + 1,) * 2, dtype=bool)
        oi, oj = int(round((w["x0"] + HALF) / st)), int(round((w["z0"] + HALF) / st))
        for j, a, b in w["runs"]:
            if 0 <= j + oj < m2.shape[0]:
                m2[j + oj, max(0, a + oi):min(m2.shape[1], b + oi + 1)] = True
    if m2 is None:
        return
    field.blocked |= np.repeat(np.repeat(m2[:-1, :-1], k, 0), k, 1)[:field.n, :field.n]
    print("island_buildings: seawall works %.2f km2 kept clear" % (m2.sum() * st * st * 1e-6))


def plan_reserves(field):
    """island_plan.RESERVES: ground held for a later, regional pass (the military base, the waterfront park, the
    resort hotels, the lighthouse, the 道の駅) -- no generated building stands on it."""
    import island_plan as PL
    for name, (x0, z0, x1, z1) in PL.RESERVES:
        field.block_box((x0 + x1) / 2.0, (z0 + z1) / 2.0, 0.0, (x1 - x0) / 2.0, (z1 - z0) / 2.0)
    print("island_buildings: %d reserve(s) held for later: %s" % (len(PL.RESERVES),
                                                                ", ".join(n for n, _b in PL.RESERVES)))


FIELD_BOX = (400.0, 700.0, 1300.0, 1570.0)   # record frame: the farm grid (island_plan's farm* street regions)
FIELD_CHUNK, FIELD_CELLS = 50.0, 25          # must match world.CropField.CHUNK / CELLS
FIELD_LEVEE = 1.5                              # m of levee (畦) kept clear of anything blocked round a field cell
WHEAT_ONE_IN = 4                               # one paddy section in this many grows wheat, the rest rice


FIELD_SEA_WINDOW = 300.0   # m round FIELD_BOX searched for the sea a field must not reach without crossing a road


def _seaward(field):
    """FARMLAND IS THE LAND INSIDE THE ROADS (user, 2026-09-26: "no farm on the coastal side of the street"). A 2 m
    cell is SEAWARD when the sea reaches it without crossing a road: a flood from every sea cell through everything that
    is not carriageway or footway. The strip between the coast road and the beach is seaward; a section enclosed by
    farm roads is not. Returns a (x, z) -> bool test in the Godot frame."""
    np = field.np
    x0r, y0r, x1r, y1r = FIELD_BOX
    gx0, gx1 = x0r - FIELD_SEA_WINDOW, x1r + FIELD_SEA_WINDOW
    gz0, gz1 = -y1r - FIELD_SEA_WINDOW, -y0r + FIELD_SEA_WINDOW
    s = int(round(DUMP_STEP / RES))
    i0, j0 = field.idx(gx0, gz0)
    i1, j1 = field.idx(gx1, gz1)
    i0, j0 = max(0, i0 - i0 % s), max(0, j0 - j0 % s)
    i1, j1 = min(field.n, i1 - i1 % s), min(field.n, j1 - j1 % s)
    road = field.road[j0:j1, i0:i1]
    road = road.reshape(road.shape[0] // s, s, road.shape[1] // s, s).any(axis=(1, 3))
    a0, b0 = j0 // s, i0 // s
    sea = field.h2[a0:a0 + road.shape[0], b0:b0 + road.shape[1]] <= LAND_Z
    open_ = ~road
    reach = sea & open_
    while True:
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= open_
        if (grown == reach).all():
            break
        reach = grown

    def test(x, z):
        i, j = field.idx(x, z)
        a, b = j // s - a0, i // s - b0
        if not (0 <= a < reach.shape[0] and 0 <= b < reach.shape[1]):
            return True
        return bool(reach[a, b])
    return test


def farm_fields(field):
    """The PADDY FIELDS (user, 2026-09-25): every 2 m cell of the farm grid that is dry land with nothing blocked
    (a road, the rail, a site, the sea) within FIELD_LEVEE of it. Returned as `world.CropField` chunks --
    `{x0, z0, y, kind, mask}` in the Godot frame, one per 50 m chunk and crop, so a chunk straddling two sections
    never spills one crop across the farm road between them -- and MARKED BLOCKED, so no building stands in a field.
    A section's crop is a hash of its grid position: rice, with one section in WHEAT_ONE_IN wheat."""
    import island_plan as PL
    np = field.np
    xs = sorted({v for r in PL.STREET_REGIONS if r[0].startswith("farm") for v in r[3]})
    ys = sorted({v for r in PL.STREET_REGIONS if r[0].startswith("farm") for v in r[4]})
    x0r, y0r, x1r, y1r = FIELD_BOX
    xe, ye = [x0r] + xs + [x1r], [y0r] + ys + [y1r]

    def section(x, y):
        return (sum(1 for v in xe if v <= x), sum(1 for v in ye if v <= y))

    def kind(sec):
        return 1 if zlib.crc32(("field_%d_%d" % sec).encode()) % WHEAT_ONE_IN == 0 else 0

    def free(x, z):
        for dx, dz in ((0, 0), (FIELD_LEVEE, 0), (-FIELD_LEVEE, 0), (0, FIELD_LEVEE), (0, -FIELD_LEVEE)):
            i, j = field.idx(x + dx, z + dz)
            if not (0 <= i < field.n and 0 <= j < field.n) or field.blocked[j, i]:
                return False
        i2, j2 = int((x + HALF) / DUMP_STEP), int((z + HALF) / DUMP_STEP)
        return float(field.h2[j2, i2]) > LAND_Z

    seaward = _seaward(field)

    cell = FIELD_CHUNK / FIELD_CELLS
    chunks, cells = [], []
    cx = math.floor(x0r / FIELD_CHUNK) * FIELD_CHUNK
    while cx < x1r:
        cz = math.floor(-y1r / FIELD_CHUNK) * FIELD_CHUNK
        while cz < -y0r:
            by_kind = {}
            for row in range(FIELD_CELLS):
                for col in range(FIELD_CELLS):
                    x, z = cx + (col + 0.5) * cell, cz + (row + 0.5) * cell
                    if not (x0r <= x <= x1r and y0r <= -z <= y1r) or seaward(x, z) or not free(x, z):
                        continue
                    k = kind(section(x, -z))
                    by_kind.setdefault(k, set()).add(row * FIELD_CELLS + col)
                    cells.append((x, z))
            for k, bits in sorted(by_kind.items()):
                n = FIELD_CELLS * FIELD_CELLS
                word = "".join("1" if b in bits else "0" for b in range(n)) + "0" * (-n % 4)
                hs = [float(field.h2[int((cz + (b // FIELD_CELLS + 0.5) * cell + HALF) / DUMP_STEP),
                                     int((cx + (b % FIELD_CELLS + 0.5) * cell + HALF) / DUMP_STEP)]) for b in bits]
                hs.sort()
                chunks.append({"x0": cx, "z0": cz, "y": round(hs[len(hs) // 2], 3), "kind": k,
                               "mask": "%0*x" % (len(word) // 4, int(word, 2))})
            cz += FIELD_CHUNK
        cx += FIELD_CHUNK
    half = cell / 2.0
    for x, z in cells:
        ii, jj = field.rect_points(x, z, 0.0, -half, -half, half, half)
        field.blocked[jj, ii] = True
    area = len(cells) * cell * cell
    print("island_buildings: %d field chunk(s), %.2f km2 of paddy (%d%% wheat)" % (
        len(chunks), area / 1e6, round(100.0 * sum(1 for c in chunks if c["kind"] == 1) / max(1, len(chunks)))))
    return chunks


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
                if field.road[jj, ii].any() or field.passage[jj, ii].any() or ((own != 0) & (own != me)).any():
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


LOT_SEPARATE_STEP = 0.05   # `separate_lots` trims a side this much at a time
LOT_OVERLAP_TOL = 1e-4     # m2: two slabs sharing less than this are touching (float round-off), not overlapping


def lot_polygon(b, lot=None):
    """The world-plan corners (x, z) of a lot slab, counter-clockwise in its own frame."""
    x0, z0, x1, z1 = lot or b["lot"]
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)
    cx, cz = b["pos"][0], b["pos"][2]
    return [(cx + lx * c + lz * s, cz - lx * s + lz * c) for lx, lz in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))]


def _clip(poly, a, b):
    """Sutherland-Hodgman: `poly` clipped to the left of the directed edge a -> b (or its right, for a clockwise
    clip polygon -- `overlap_area` passes the clip polygon in its own winding and checks the sign)."""
    out = []
    def side(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    for k in range(len(poly)):
        p, q = poly[k], poly[(k + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0.0:
            out.append(p)
        if (sp >= 0.0) != (sq >= 0.0):
            t = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _area(poly):
    return 0.5 * sum(poly[k][0] * poly[(k + 1) % len(poly)][1] - poly[(k + 1) % len(poly)][0] * poly[k][1]
                     for k in range(len(poly)))


def overlap_area(p, q):
    """Plan area two convex polygons share."""
    if _area(q) < 0.0:
        q = list(reversed(q))
    if _area(p) < 0.0:
        p = list(reversed(p))
    out = p
    for k in range(len(q)):
        out = _clip(out, q[k], q[(k + 1) % len(q)])
        if len(out) < 3:
            return 0.0
    return abs(_area(out))


def lot_overlaps(placed):
    """[(area, i, j)] of every pair of lot slabs that share plan area, with a 16 m bucket index."""
    polys = [lot_polygon(b) for b in placed]
    grid = {}
    for i, p in enumerate(polys):
        xs, zs = [v[0] for v in p], [v[1] for v in p]
        for gx in range(int(math.floor(min(xs) / 16.0)), int(math.floor(max(xs) / 16.0)) + 1):
            for gz in range(int(math.floor(min(zs) / 16.0)), int(math.floor(max(zs) / 16.0)) + 1):
                grid.setdefault((gx, gz), []).append(i)
    pairs = set()
    for ids in grid.values():
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                pairs.add((min(ids[a], ids[b]), max(ids[a], ids[b])))
    out = []
    for i, j in sorted(pairs):
        ar = overlap_area(polys[i], polys[j])
        if ar > LOT_OVERLAP_TOL:
            out.append((ar, i, j))
    return out


def separate_lots(placed, aabbs):
    """No two lot slabs overlap (PLAN.md P3 "lot-slab overlap slivers").

    `grow_lots` claims whole 1 m cells of `field.owner` by their CENTRES, so two lots never claim the same cell --
    but a rectangle's continuous edge runs up to a cell past the last centre it covers, and two neighbours grown
    toward each other end up sharing a strip up to ~0.9 m wide along their whole common side. Every such pair is
    coplanar (both lots stand at their footway's height), so the strip z-fights: measured 1421 of 1453 overlapping
    pairs, 5 890 m2, before this pass. The cell test cannot see it; the plan geometry can.

    For each overlapping pair, trim the one SIDE of either lot that clears it with the least cut, never into that
    building's own footprint (a side stops at the type's AABB), and repeat until nothing overlaps. A pair whose
    footprints themselves overlap cannot be separated by trimming and is reported."""
    stuck = set()
    for _ in range(8):
        pairs = [p for p in lot_overlaps(placed) if (p[1], p[2]) not in stuck]
        if not pairs:
            break
        for _ar, i, j in pairs:
            best = None
            for k, other in ((i, j), (j, i)):
                b = placed[k]
                fx0, fz0, fx1, fz1, _h = aabbs[b["type"]]
                q = lot_polygon(placed[other])
                for side, limit in ((0, fx0), (1, fz0), (2, fx1), (3, fz1)):
                    lot = list(b["lot"])
                    cut = 0.0
                    while overlap_area(lot_polygon(b, lot), q) > LOT_OVERLAP_TOL:
                        cut += LOT_SEPARATE_STEP
                        lot[side] = b["lot"][side] + (cut if side < 2 else -cut)
                        if (side < 2 and lot[side] > limit) or (side >= 2 and lot[side] < limit):
                            cut = None
                            break
                    if cut is not None and (best is None or cut < best[0]):
                        best = (cut, k, lot)
            if best is None:
                stuck.add((i, j))
                continue
            placed[best[1]]["lot"] = [round(v, 3) for v in best[2]]
    left = lot_overlaps(placed)
    print("island_buildings: lots separated; %d pair(s) still overlap (%.1f m2)%s"
          % (len(left), sum(a for a, _i, _j in left), "" if not left else " -- footprints clash"))
    return left


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


def site_places(text):
    """[(name, godot x, z)] of every SiteZones child and Landmarks child the map should name."""
    out = []
    for parent in ("SiteZones", "Landmarks"):
        for m in re.finditer(r'\[node name="(\w+)"[^\]]*parent="%s"[^\]]*\]\ntransform = Transform3D\(([^)]*)\)'
                             % parent, text):
            t = [float(v) for v in m.group(2).split(",")]
            out.append((m.group(1), t[9], t[11]))
    return out


def write_places(placed, aabbs, text):
    """PLAN.md 3.18n: the map's own record of somewhere a player can GO, derived from what is already placed.

    A place is a building the placement made enterable (its scene is a `_Shop` or `_Open` variant) or a site /
    landmark in the scene. `at` is where a blip sits; `go` is the FRONT face centre, which is where the door is
    -- a waypoint set on a blip should send you to the front of the shop, not into the middle of its footprint.
    (`RoadMap` then snaps the goal to the nearest lane, so `go` decides which SIDE of the block you are routed
    to, not the last two metres.)"""
    places = []
    for b in placed:
        scene = scene_of(b)
        if scene == b["type"]:
            continue                       # shut: not a place
        label, tier = ROLE_PLACES.get(b.get("role", ""), PLACE_KINDS.get(b["type"], ("", 0)))
        if not label:
            continue
        x0, z0, x1, z1, _h = aabbs[b["type"]]
        a = math.radians(b["yaw"])
        c, sn = math.cos(a), math.sin(a)
        places.append({"name": label, "kind": b["type"], "tier": tier,
                       "at": [round(b["pos"][0], 2), round(b["pos"][1], 2), round(b["pos"][2], 2)],
                       "go": [round(b["pos"][0] + sn * z1, 2), round(b["pos"][1], 2),
                              round(b["pos"][2] + c * z1, 2)]})
    for name, x, z in site_places(text):
        label, tier = SITE_PLACES.get(name, (name, 2))
        places.append({"name": label, "kind": name, "tier": tier,
                       "at": [round(x, 2), 0.0, round(z, 2)], "go": [round(x, 2), 0.0, round(z, 2)]})
    regions = [{"name": r[0], "box": [r[1][0], -r[1][3], r[1][2], -r[1][1]]} for r in REGIONS]   # record -> godot
    # every building's FOOTPRINT (its type's AABB, placed), for the map's building layer (user, 2026-09-22: "place
    # squares on the minimap / big map so the user knows the surroundings"): [kind, x0, z0, x1, z1, x2, z2, x3, z3]
    # with kind 1 for a place (enterable), 0 for any other building
    footprints = []
    for b in placed:
        x0, z0, x1, z1, _h = aabbs[b["type"]]
        a = math.radians(b["yaw"])
        c, sn = math.cos(a), math.sin(a)
        cx, cz = b["pos"][0], b["pos"][2]
        row = [1 if scene_of(b) != b["type"] else 0]
        for lx, lz in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
            row += [round(cx + lx * c + lz * sn, 1), round(cz - lx * sn + lz * c, 1)]
        footprints.append(row)
    os.makedirs(os.path.dirname(PLACES), exist_ok=True)
    with open(PLACES, "w") as f:
        json.dump({"schema": 1, "source": "tools/island_buildings.py derive",
                   "note": "map places and region boxes, Godot world frame (box = x0, z0, x1, z1)",
                   "regions": regions, "places": places, "footprints": footprints}, f, separators=(",", ":"))
        f.write("\n")
    by = {}
    for pl in places:
        by[pl["name"]] = by.get(pl["name"], 0) + 1
    print("island_buildings: %d map places %s, %d footprints -> %s"
          % (len(places), dict(sorted(by.items())), len(footprints), os.path.relpath(PLACES, ROOT)))


def places_only(check):
    """Rebuild only `IslandPlaces.json`, from the buildings record and the scene. A label or a tier is a fact
    about the MAP, so editing one must not need a terrain dump and a two-minute re-derive."""
    doc = json.load(open(OUT))
    aabbs = {t: type_aabb(t) for t in TYPES}
    before = open(PLACES).read() if os.path.exists(PLACES) else ""
    write_places(doc["buildings"], aabbs, open(SCENE).read())
    after = open(PLACES).read()
    if check and after != before:
        open(PLACES, "w").write(before)
        print("island_buildings: %s is STALE" % os.path.basename(PLACES))
        return 1
    return 0


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


def report_cover(field):
    """PLAN.md 3.18q: how much buildable land each region ends up COVERED by, and how much is left bare.

    Measured on the placement's own masks, so it is what the placer saw and not a re-derivation: buildable land
    is a region's land that is neither road/footway/pad nor a site, and covered land is a lot, a 路地 or the
    ground a building stands on. What is left is block INTERIOR -- yards, and, where a region's row cap stops
    short of the middle of a deep block, bare terrain. It is printed rather than gated because how much of a
    block should be yard is a look decision, and this is the number to argue about."""
    np = field.np
    ii = np.arange(field.n)
    xs = (ii + 0.5) * RES - HALF                      # Godot x of each column, z of each row
    X, Z = np.meshgrid(xs, xs)
    land = ~field.blocked & (np.repeat(np.repeat(field.h2[:-1, :-1], int(DUMP_STEP / RES), 0),
                                       int(DUMP_STEP / RES), 1)[:field.n, :field.n] > LAND_Z)
    covered = (field.owner != 0) | field.occupied | field.passage
    cell = RES * RES / 1e6                            # km2 per cell
    print("island_buildings: buildable land covered by lots (PLAN.md 3.18q)")
    for r in REGIONS:
        x0, y0, x1, y1 = r[1]                          # the region box is in the RECORD frame (x, y) = (x, -z)
        inside = (X >= x0) & (X <= x1) & (-Z >= y0) & (-Z <= y1) & land
        n = int(inside.sum())
        if not n:
            continue
        c = int((inside & covered).sum())
        print("  %-12s %6.3f km2 buildable, %5.1f%% covered, %6.3f km2 bare"
              % (r[0], n * cell, 100.0 * c / n, (n - c) * cell))


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
    rail_reserve(field)
    plan_reserves(field)
    seawall_works(field)
    fields = farm_fields(field)
    # --- the 路地 are reserved BEFORE anything is placed, so the frontage row grows round them rather than being
    # cut afterwards: a lot that has already claimed the ground cannot be asked to give it back.
    passages = through_lanes(field)
    for owner, line, gap, lanes, kerbed in frontage:
        for side in (1.0, -1.0):
            pts = resample(offset_line(line, side * gap), 1.0)
            if len(pts) < 4:
                continue
            total = float(len(pts) - 1)
            first = PASSAGE_EVERY * 0.5
            s = first
            while s < total - PASSAGE_EVERY * 0.35:
                px, pz, nx, nz, py = pts[int(s)]
                # deep enough to pass the district's back rows and reach the block's centre, where the lanes from
                # the surrounding streets meet (user, 2026-09-26: "enter the centre from three sides")
                reg_ = region_of(px, -pz)
                depth = min(PASSAGE_DEPTH_MAX, max(PASSAGE_DEPTH, reg_[2] * reg_[3] + 16.0)) if reg_ else PASSAGE_DEPTH
                # the corridor runs from the footway edge straight back into the block, along the frontage normal
                cx_, cz_ = px - nx * (depth / 2.0), pz - nz * (depth / 2.0)
                yaw_ = math.atan2(nx, nz)
                ii, jj = field.rect_points(cx_, cz_, yaw_, -PASSAGE_W / 2.0, -depth / 2.0,
                                           PASSAGE_W / 2.0, depth / 2.0)
                if ii.size:
                    hs = field.heights(ii, jj)
                    if float(hs.min()) > LAND_Z and not field.blocked[jj, ii].all():
                        field.passage[jj, ii] = True
                        # A 路地 STANDS WITH THE LOTS IT RUNS BETWEEN, NOT WITH THE CARRIAGEWAY. `py` is the
                        # road SURFACE, while a lot's top is `road + KERB_H`, so the alley shipped 0.17 m
                        # below the slabs either side of it (measured over 379 passages: median 0.170 m). The
                        # alley has no slab of its own now (3.18(c3a)); this height is what `island_ground.py`
                        # paves its ground to, so it is load-bearing.
                        passages.append({"pos": [round(cx_, 3), round(py + (KERB_H if kerbed else 0.0), 3),
                                                 round(cz_, 3)],
                                         "yaw": round(math.degrees(yaw_), 3),
                                         "size": [PASSAGE_W, depth]})
                s += PASSAGE_EVERY
    print("island_buildings: %d 路地 reserved through the frontage rows" % len(passages))

    aabbs = {t: type_aabb(t) for t in TYPES}
    placed, counts, seen_kind = [], {}, {}
    parking_misses = [0]

    def far_from_kind(t, x, z):
        d = SPACING.get(t)
        if not d:
            return True
        return all((x - px) ** 2 + (z - pz) ** 2 >= d * d for px, pz in seen_kind.get(t, ()))

    def try_place(t, px, pz, nx, nz, key, region, road_y, front_gap, kerbed, over_passage=False, back_row=False):
        x0, z0, x1, z1, hgt = aabbs[t]
        yaw = math.atan2(nx, nz)          # local +Z (the front) turned onto the road direction
        # the front face (local z1) on the row line
        cx, cz = px - nx * z1, pz - nz * z1
        al = alley_of(region)
        ii, jj = field.rect_points(cx, cz, yaw, x0 - al, z0 - al, x1 + al, z1)
        if ii.size == 0:
            return None
        # a CAR PARK may stand over a 路地 reservation: it is open ground and keeps the access open, and a 21.8 m
        # lot beside a 21.8 m store otherwise straddles the next reserved passage every time (2026-09-25)
        if field.blocked[jj, ii].any():
            REFUSED["blocked"] = REFUSED.get("blocked", 0) + 1
            return None
        if field.occupied[jj, ii].any() or (not over_passage and field.passage[jj, ii].any()):
            REFUSED["occupied/passage"] = REFUSED.get("occupied/passage", 0) + 1
            return None
        if back_row:
            # 接道 (user, 2026-09-26: no "ring within ring" of buildings nobody can reach): a back-row building
            # stands only where a 路地, a through lane or a street runs within BACK_ACCESS of its lot -- the flag-pole
            # lot (旗竿地) of a Japanese block, whose strip reaches the road
            ai, aj = field.rect_points(cx, cz, yaw, x0 - al - BACK_ACCESS, z0 - al - BACK_ACCESS,
                                       x1 + al + BACK_ACCESS, z1 + BACK_ACCESS)
            if ai.size and not (field.passage[aj, ai].any() or field.road[aj, ai].any()):
                REFUSED["back row with no access"] = REFUSED.get("back row with no access", 0) + 1
                return None
        hs = field.heights(ii, jj)
        if float(hs.max() - hs.min()) > RELIEF or float(hs.min()) <= LAND_Z:
            REFUSED["relief/water"] = REFUSED.get("relief/water", 0) + 1
            return None
        # The LOT: a concrete slab at the sidewalk's height (the road's surface + the kerb; the carriageway's own
        # height where the road has no footway), under the building, its alleys and -- on the frontage row -- the
        # strip out to the footway, so the ground a player walks from the pavement to the door is one level surface.
        # The building stands on it, not on the heightmap. Refused where the ground stands above the slab (it would
        # bury it) or falls further below it than LOT_MAX_STEP (it would stand on a plinth).
        top = road_y + (KERB_H if kerbed else 0.0)
        if float(hs.max()) > top + LOT_BURY_TOL:
            REFUSED["ground above the slab"] = REFUSED.get("ground above the slab", 0) + 1
            return None
        if top - float(hs.min()) > LOT_MAX_STEP:
            REFUSED["ground too far below"] = REFUSED.get("ground too far below", 0) + 1
            return None
        field.occupied[jj, ii] = True
        field.owner[jj, ii] = len(placed) + 1
        if front_gap > 0.0:
            fi, fj = field.rect_points(cx, cz, yaw, x0 - al, z1, x1 + al, z1 + front_gap)
            free = field.owner[fj, fi] == 0
            field.owner[fj[free], fi[free]] = len(placed) + 1
        return {"type": t, "region": region[0], "key": key,
                "pos": [round(cx, 3), round(top, 3), round(cz, 3)],
                "yaw": round(math.degrees(yaw), 3),
                # local rect of the slab and its bottom (below the lowest ground under it)
                "lot": [round(x0 - al, 3), round(z0 - al, 3), round(x1 + al, 3), round(z1 + front_gap, 3)],
                "lot_depth": round(top - float(hs.min()) + LOT_SKIRT, 3)}

    for owner, line, gap, lanes, kerbed in frontage:
        for side in (1.0, -1.0):
            for row in range(max(r[2] for r in REGIONS)):
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
                        adv = w / 2.0 + alley_of(reg)
                        j = k + int(round(adv / SLOT_STEP))
                        if j >= len(pts_rows):
                            continue
                        cx_, cz_, cnx, cnz, cy_ = pts_rows[j]
                        # the frontage row's slab reaches the footway (short of its edge, never over it)
                        got = try_place(t, cx_ - cnx * back, cz_ - cnz * back, cnx, cnz, key, reg, cy_,
                                        (KERB_GAP + 0.3 - LOT_FOOTWAY_GAP) if row == 0 else 0.0,
                                        kerbed, back_row=row > 0)
                        if got:
                            k = j + int(math.ceil((w / 2.0 + alley_of(reg)) / SLOT_STEP))
                            break
                    if got:
                        placed.append(got)
                        counts[got["type"]] = counts.get(got["type"], 0) + 1
                        seen_kind.setdefault(got["type"], []).append((got["pos"][0], got["pos"][2]))
                        lot_t = PARKING.get(got["type"])
                        if lot_t:
                            # the car park BESIDE the store, on the same row line: right (further along the
                            # street) first, else left; the store stands alone when neither fits
                            wp = aabbs[lot_t][2] - aabbs[lot_t][0]
                            ws = aabbs[got["type"]][2] - aabbs[got["type"]][0]
                            # ROUNDED UP: rounding put the car park 0.84 m into the store's own alley, and every
                            # one of the first rebuild's seven KonbiniL stood alone (2026-09-25)
                            step = int(math.ceil((ws / 2.0 + wp / 2.0 + 2 * alley_of(reg)) / SLOT_STEP))
                            jj0 = j
                            for jp in (jj0 + step, jj0 - step, jj0 + step + 1, jj0 - step - 1, jj0 + step + 2,
                                       jj0 - step - 2):
                                if not 0 <= jp < len(pts_rows):
                                    continue
                                lx, lz, lnx, lnz, ly = pts_rows[jp]
                                lot = try_place(lot_t, lx - lnx * back, lz - lnz * back, lnx, lnz, key + "|P", reg,
                                                ly, (KERB_GAP + 0.3 - LOT_FOOTWAY_GAP) if row == 0 else 0.0, kerbed,
                                                over_passage=True)
                                if lot is None:
                                    parking_misses[0] += 1
                                if lot:
                                    lot["with"] = len(placed) - 1
                                    if row == 0 and kerbed:
                                        # B9: the kerb line in the car park's own frame (its front face stands on the
                                        # row line, `gap` past the carriageway's edge), where its 段差スロープ goes
                                        lot["drive"] = round(aabbs[lot_t][3] + gap, 3)
                                    placed.append(lot)
                                    counts[lot_t] = counts.get(lot_t, 0) + 1
                                    if jp > jj0:
                                        k = max(k, jp + int(math.ceil((wp / 2.0 + alley_of(reg)) / SLOT_STEP)))
                                    break
                    else:
                        k += 1
    print("island_buildings: %d car park(s) placed beside their store, %d candidate spot(s) refused"
          % (sum(1 for b in placed if b["type"] in PARKING.values()), parking_misses[0]))
    grow_lots(field, placed)
    separate_lots(placed, aabbs)
    assign_tones(placed)
    shops = 0
    for b in placed:
        if b["type"] in SHOP_TYPES:
            b["scene"] = b["type"] + "_Shop"
            shops += 1
    print("island_buildings: %d shops are always open (%s)" % (shops, ", ".join(sorted(SHOP_TYPES))))
    anchored, roles = apply_anchors(placed)
    report_cover(field)
    placed.sort(key=lambda b: (b["pos"][0], b["pos"][2]))
    by_region = {}
    for b in placed:
        by_region[b["region"]] = by_region.get(b["region"], 0) + 1
    doc = {"schema": 1, "source": "tools/island_buildings.py derive", "network_y": ny,
           "counts": dict(sorted(counts.items())), "regions": dict(sorted(by_region.items())),
           "passages": passages, "anchored_missions": anchored, "roles": roles, "fields": fields,
           "buildings": placed}
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    write_sidewalks(sidewalks)
    write_places(placed, aabbs, text)
    print("island_buildings: lots refused %s" % dict(sorted(REFUSED.items(), key=lambda kv: -kv[1])))
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
# PRIVATE / PUBLIC are two materials with one look (user, 2026-09-25): the lot and the block fill wear the PRIVATE
# M_LotConcrete, the footway the PUBLIC M_ConcreteTile; both ship identical, so an artist can move either alone.
LOT_MATERIAL = "res://assets/world_source/buildings/materials/M_LotConcrete.tres"

# --- THREE heights, one rule (PLAN.md 3.18j, user-reported twice: the gas station's apron z-fighting the slab
# under it, and then a photograph of a Shibuya street showing what it should look like -- the public footway in
# dark asphalt with its yellow 点字ブロック, and each building's OWN frontage paving in a different material,
# slightly PROUD of it, with a clean lip where they meet). In Japan the footway belongs to the road and the strip
# in front of a building belongs to the lot (民地), so they are two surfaces at two heights, never one.
#
#   footway top            = the carriageway + KERB_H          (the Road Kit's, and not ours to move)
#   lot slab top           = footway top + LOT_RAISE           (the building's own paving, proud of the footway)
#   building floor / apron = lot slab top + FLOOR_LIFT         (so neither can ever be coplanar with the slab)
#
# FLOOR_LIFT is the z-fighting fix and it is a fix by CONSTRUCTION: a composite draws its apron at its own origin
# height, so while that was the slab's height too the two were exactly coplanar, which is what z-fighting IS and
# what no depth bias answers honestly. The whole step from footway to floor is 8 cm -- visible, the shallow end
# of the 10-15 cm a Japanese shop really stands up, and far under `MovementController.stepHeight` (0.35 m), so
# nothing has to climb it. Both are applied in `write`, so changing them re-writes the cell scenes and needs no
# terrain dump and no re-derive.
LOT_RAISE = 0.06
FLOOR_LIFT = 0.03
# THE BLOCK IS THE PRIVATE GROUND; THERE IS NO LOT SLAB (user, 2026-09-25). A lot was a rectangle grown out from
# its own building in its own frame, and rectangles in different frames cannot tile a block, so neighbouring slabs
# always left strips of the fill showing between them -- a gap no bevel could close, because it came from WHERE the
# slabs were, not from what their edges looked like. The block fill (`island_ground.py`, Terrain3D) paves every
# block from the kerb inward already, so it now stands AT the old slab's top (footway + LOT_RAISE) and is the one
# private surface; LOT_FILL_GAP is 0. The lot RECORD stays: it is the fill's seed (the geodesic walk starts from the
# lots) and where each building's own ground height is decided. What a building keeps is a PLINTH (基礎): its own
# footprint grown by PLINTH_MARGIN, its top PLINTH_LIFT over the fill and under the building's floor (FLOOR_LIFT),
# so the walls never meet the ground on a seam and neither face is coplanar with the other.
LOT_FILL_GAP = 0.0
PLINTH_MARGIN = 0.25
PLINTH_LIFT = 0.015


_AABBS = {}


def plinth_boxes(b):
    """(cos/sin, size, world centre) of a building's PLINTH: its type's footprint grown by PLINTH_MARGIN, its top
    PLINTH_LIFT above the fill (footway + LOT_RAISE), its foot where the lot's slab foot was (below the lowest ground
    under it)."""
    t = b["type"]
    if t not in _AABBS:
        _AABBS[t] = type_aabb(t)
    x0, z0, x1, z1, _h = _AABBS[t]
    x0, z0, x1, z1 = x0 - PLINTH_MARGIN, z0 - PLINTH_MARGIN, x1 + PLINTH_MARGIN, z1 + PLINTH_MARGIN
    top = LOT_RAISE + PLINTH_LIFT
    depth = b.get("lot_depth", 0.5) + top
    sx, sz = x1 - x0, z1 - z0
    lx, lz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)
    ox = b["pos"][0] + lx * c + lz * s
    oz = b["pos"][2] - lx * s + lz * c
    oy = b["pos"][1] + top - depth / 2.0
    return (c, s), (sx, depth, sz), (ox, oy, oz)


DRIVE_W = 5.0          # a 段差スロープ (kerb ramp): this wide along the kerb, in front of a car park's entrance...
DRIVE_D = 0.8          # ...this deep into the gutter, rising to the kerb's own height at the kerb line (B9). The
                       # Japanese answer to "a car must get over the kerb into the lot": a rubber or concrete wedge in
                       # the gutter, so the road's kerb and footway stay one owner's, built before any lot exists


def drive_ramp(b):
    """(basis columns, world centre) of a car park's kerb ramp: a unit right-triangle PrismMesh (left_to_right 1, its
    high side at +x) turned so +x points from the road back to the kerb, scaled DRIVE_D x KERB_H x DRIVE_W."""
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)
    kz = b["drive"] + DRIVE_D / 2.0
    ox, oz = b["pos"][0] + s * kz, b["pos"][2] + c * kz
    oy = b["pos"][1] - KERB_H + KERB_H / 2.0
    # lot local x = (c, -s), local z (toward the road) = (s, c); prism x -> -local z, y -> up, z -> local x
    return ((-s, 0.0, -c), (0.0, 1.0, 0.0), (c, 0.0, -s)), (ox, oy, oz)


def scene_of(b):
    return b.get("scene", b["type"])


DARK_BIAS = 1.5    # "dark": the darkest tone's weight is (1 + this) x its share, the lightest's 1 x


def tone_weights(region):
    """The draw weight of each facade tone in `region`: PLATEAU's measured share, leaned dark where the region
    says so (PLAN.md 3.19(e))."""
    levels = tone_levels()
    shares = [lv.get("share", 1.0) for lv in levels]
    bias = next((r[6] for r in REGIONS if r[0] == region and len(r) > 6), None)
    if bias != "dark":
        return shares
    lums = [lv.get("lum", 128.0) for lv in levels]
    lo, hi = min(lums), max(lums)
    return [sh * (1.0 + DARK_BIAS * (hi - l) / max(1e-6, hi - lo)) for sh, l in zip(shares, lums)]


def assign_tones(placed):
    """One tone per building (PLAN.md 3.18p). Chosen from the slot's OWN key with its own salt, never by drawing
    from the placement's `rng`: that stream decides which TYPE stands there, and taking one more number out of it
    would silently re-roll the whole city. So a new palette re-colours the city without moving a building."""
    n_tones = tone_count()
    if not n_tones:
        print("island_buildings: no facade_tones.json -- every building wears its type's own facade")
        return
    tone_counts, by_region, cache = {}, {}, {}
    for b in placed:
        if b["region"] not in cache:
            cache[b["region"]] = tone_weights(b["region"])
        w = cache[b["region"]]
        total = sum(w)
        u = (zlib.crc32((b["key"] + "|tone").encode()) % 1000003) / 1000003.0 * total
        pick = n_tones - 1
        for i in range(n_tones):
            u -= w[i]
            if u < 0:
                pick = i
                break
        b["tone"] = pick
        tone_counts[pick] = tone_counts.get(pick, 0) + 1
        by_region.setdefault(b["region"], {}).setdefault(pick, 0)
        by_region[b["region"]][pick] += 1
    print("island_buildings: facade tone mix %s over %d tones" % (dict(sorted(tone_counts.items())), n_tones))
    for reg in sorted(by_region):
        print("  %-18s %s" % (reg, dict(sorted(by_region[reg].items()))))


def lots_record(check):
    """`separate_lots` on the existing record (no terrain dump, no building moves: only lot rects shrink)."""
    doc = json.load(open(OUT))
    before = [list(b["lot"]) for b in doc["buildings"]]
    aabbs = {t: type_aabb(t) for t in {b["type"] for b in doc["buildings"]}}
    left = separate_lots(doc["buildings"], aabbs)
    changed = sum(1 for a, b in zip(before, doc["buildings"]) if a != b["lot"])
    print("island_buildings: %d of %d lots trimmed" % (changed, len(before)))
    if changed and not check:
        with open(OUT, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
    return 1 if (check and (changed or left)) else 0


def retone_record(check):
    """Re-assign every building's facade tone in the existing record (no terrain dump, no building moves)."""
    doc = json.load(open(OUT))
    before = [b.get("tone", 0) for b in doc["buildings"]]
    assign_tones(doc["buildings"])
    changed = sum(1 for a, b in zip(before, doc["buildings"]) if a != b.get("tone", 0))
    print("island_buildings: %d of %d buildings change tone" % (changed, len(before)))
    if changed and not check:
        with open(OUT, "w") as f:
            json.dump(doc, f, indent=1)      # derive's own format, so the diff is the tones and nothing else
            f.write("\n")
    return 1 if (check and changed) else 0



def facade_tones():
    """{facade material: [tone material per level]}. Empty if the record is absent, in which case the buildings
    ship with their type's own facades -- exactly what they did before."""
    if not os.path.exists(FACADE_TONES_JSON):
        return {}
    return json.load(open(FACADE_TONES_JSON))["facades"]


def tone_levels():
    if not os.path.exists(FACADE_TONES_JSON):
        return []
    return json.load(open(FACADE_TONES_JSON))["levels"]


def tone_count():
    tones = facade_tones()
    return len(next(iter(tones.values()))) if tones else 0


_FACADE_SURFACES = {}


def facade_surfaces(scene):
    """{facade material: merged surface index} for a building TYPE, from the meta its own scene carries.

    Read out of the `.tscn` text rather than kept in a second table: `build_building_scenes.gd` is the only
    thing that can know the merge order, so it is the only thing that writes it."""
    if scene not in _FACADE_SURFACES:
        path = os.path.join(BLD_DIR, scene + ".tscn")
        got = {}
        if os.path.exists(path):
            m = re.search(r'"facade_surfaces":\s*\{([^}]*)\}', open(path).read())
            if m:
                got = {k: int(v) for k, v in re.findall(r'"(\w+)":\s*(\d+)', m.group(1))}
        _FACADE_SURFACES[scene] = got
    return _FACADE_SURFACES[scene]


CROP_SCRIPT = "res://src/main/java/com/openworld/world/CropField.java"


def cell_scene(name, blds, passages=(), fields=()):
    """One streamed cell: every building instanced, and its lot slabs as ONE MultiMesh (+ box collision).

    A 路地 is NOT drawn here (PLAN.md 3.18(c3a)): it is a RESERVATION (`field.passage`, 接道義務) and its ground is
    the block's own, which `tools/island_ground.py` raises to the lots' footway level and paints. `passages` is
    still accepted so the record stays the one list a caller hands over.

    A `.tscn` is written in THREE phases and the order is not cosmetic: every `[ext_resource]` must precede every
    `[sub_resource]`, and both must precede `[node]`. Emitting the alley's material where its geometry was built
    put an ext_resource after the nodes and made 88 of 92 cells fail to LOAD -- silently, as a streaming error at
    run time rather than anything a build step reported."""
    types = sorted({scene_of(b) for b in blds})
    ids = {t: str(i + 1) for i, t in enumerate(types)}
    lots = [b for b in blds if "lot" in b]
    ext, sub, nodes = ["[gd_scene format=3]\n\n"], [], ['[node name="%s" type="Node3D"]\n' % name]

    for t in types:
        ext.append('[ext_resource type="PackedScene" path="%s/%s.tscn" id="%s"]\n' % (BLD_RES, t, ids[t]))
    tones = facade_tones()
    # only the (family, tone) pairs this cell actually wears, so a cell of one type does not carry eight
    # materials. Tone 0 IS the base material every type already references, so it needs no override at all.
    used = {}
    for b in blds:
        t = int(b.get("tone", 0))
        if t <= 0:
            continue
        for fam in facade_surfaces(scene_of(b)):
            if fam in tones:
                used.setdefault((fam, t), "tone%d_%d" % (len(used), t))
    for (fam, t), rid in sorted(used.items()):
        ext.append('[ext_resource type="Material" path="%s" id="%s"]\n' % (FACADE_MAT_RES % tones[fam][t], rid))
    if lots:
        ext.append('[ext_resource type="Material" path="%s" id="lotmat"]\n' % LOT_MATERIAL)
    if blds:
        ext.append('[ext_resource type="ArrayMesh" path="%s/%s.res" id="hlod"]\n' % (HLOD_RES, name))
    if fields:
        ext.append('[ext_resource type="Script" path="%s" id="crop"]\n' % CROP_SCRIPT)
    # every konbini sells weapons (user, 2026-09-26), the one beside the safe house included
    shops = [b for b in blds if b["type"] in KONBINI_PADS]
    if shops:
        ext.append('[ext_resource type="Script" path="%s" id="pad"]\n' % PAD_SCRIPT)
    ext.append("\n")
    for k, b in enumerate(shops):
        a = math.radians(b["yaw"])
        bs, bc = math.sin(a), math.cos(a)
        px, py, pz = b["pos"]
        holder = "Pads_%03d" % k
        nodes.append('\n[node name="%s" type="Node3D" parent="."]\n' % holder)
        for wid, lx, lz in KONBINI_PADS[b["type"]]:
            nodes.append('\n[node name="Pad_%s" type="Area3D" parent="%s"]\n'
                         'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\n'
                         'script = ExtResource("pad")\nweapon_id = "%s"\n'
                         % (wid, holder, px + lx * bc + lz * bs, py + LOT_RAISE + FLOOR_LIFT + 0.1,
                            pz - lx * bs + lz * bc, wid))
    if fields:
        # the paddy (user, 2026-09-25): world.CropField builds the crop quads from these chunks at load
        nodes.append('\n[node name="Crops" type="Node3D" parent="."]\nscript = ExtResource("crop")\n'
                     'chunks = PackedFloat32Array(%s)\nmasks = PackedStringArray(%s)\n'
                     % (", ".join("%.3f, %.3f, %.3f, %d" % (f["x0"], f["z0"], f["y"], f["kind"]) for f in fields),
                        ", ".join('"%s"' % f["mask"] for f in fields)))
    if blds:
        nodes.append('\n[node name="HLOD" type="MeshInstance3D" parent="."]\nmesh = ExtResource("hlod")\n'
                 'cast_shadow = 0\nvisibility_range_begin = %.1f\nvisibility_range_begin_margin = %.1f\n'
                 'visibility_range_fade_mode = 1\n' % (HLOD_BEGIN, HLOD_MARGIN))

    if lots:
        # ONE draw call for every PLINTH of the cell: a unit box, scaled per instance (the material is world-space
        # triplanar, so a scaled box is not a stretched texture). The lot slab is gone; the block fill is the ground.
        sub.append('[sub_resource type="BoxMesh" id="LotBox"]\nmaterial = ExtResource("lotmat")\n\n')
        buf = []
        for b in lots:
            (c, s), (sx, sy, sz), (ox, oy, oz) = plinth_boxes(b)
            buf += [c * sx, 0.0, s * sz, ox, 0.0, sy, 0.0, oy, -s * sx, 0.0, c * sz, oz]
        sub.append('[sub_resource type="MultiMesh" id="Lots"]\ntransform_format = 1\ninstance_count = %d\n'
                   'mesh = SubResource("LotBox")\nbuffer = PackedFloat32Array(%s)\n\n'
                   % (len(lots), ", ".join("%.4f" % v for v in buf)))
        for k, b in enumerate(lots):
            _cs, (sx, sy, sz), _o = plinth_boxes(b)
            sub.append('[sub_resource type="BoxShape3D" id="LotShape%d"]\nsize = Vector3(%.3f, %.3f, %.3f)\n\n'
                       % (k, sx, sy, sz))
    for k, b in enumerate(blds):
        pos = [b["pos"][0], b["pos"][1] + LOT_RAISE + FLOOR_LIFT, b["pos"][2]]
        nodes.append('\n[node name="%s_%03d" parent="." instance=ExtResource("%s")]\ntransform = %s\n'
                     % (scene_of(b), k, ids[scene_of(b)], xf(pos, b["yaw"])))
        tone = int(b.get("tone", 0))
        lines = ["surface_material_override/%d = ExtResource(\"%s\")" % (idx, used[(fam, tone)])
                 for fam, idx in sorted(facade_surfaces(scene_of(b)).items()) if (fam, tone) in used]
        lines.append('visibility_parent = NodePath("../../HLOD")')
        if lines:
            # the override is on the type's Mesh node, addressed by the surface index that type's own meta records
            nodes.append('\n[node name="Mesh" parent="./%s_%03d" index="0"]\n%s\n'
                         % (scene_of(b), k, "\n".join(lines)))
    drives = [b for b in blds if "drive" in b]
    if drives:
        sub.append('[sub_resource type="StandardMaterial3D" id="DriveMat"]\nalbedo_color = Color(0.16, 0.16, 0.17, 1)\n'
                   'roughness = 0.9\n\n')
        sub.append('[sub_resource type="PrismMesh" id="DriveRamp"]\nleft_to_right = 1.0\n'
                   'material = SubResource("DriveMat")\n\n')
        buf = []
        for b in drives:
            (c0, c1, c2), (ox, oy, oz) = drive_ramp(b)
            sx, sy, sz = DRIVE_D, KERB_H, DRIVE_W
            buf += [c0[0] * sx, c1[0] * sy, c2[0] * sz, ox, c0[1] * sx, c1[1] * sy, c2[1] * sz, oy,
                    c0[2] * sx, c1[2] * sy, c2[2] * sz, oz]
        sub.append('[sub_resource type="MultiMesh" id="Drives"]\ntransform_format = 1\ninstance_count = %d\n'
                   'mesh = SubResource("DriveRamp")\nbuffer = PackedFloat32Array(%s)\n\n'
                   % (len(drives), ", ".join("%.4f" % v for v in buf)))
        d2, h2, w2 = DRIVE_D / 2.0, KERB_H / 2.0, DRIVE_W / 2.0
        sub.append('[sub_resource type="ConvexPolygonShape3D" id="DriveShape"]\npoints = PackedVector3Array(%s)\n\n'
                   % ", ".join("%.3f, %.3f, %.3f" % q for q in
                               [(-d2, -h2, -w2), (-d2, -h2, w2), (d2, -h2, -w2), (d2, -h2, w2), (d2, h2, -w2),
                                (d2, h2, w2)]))
        nodes.append('\n[node name="Drives" type="MultiMeshInstance3D" parent="."]\nmultimesh = SubResource("Drives")\n')
        nodes.append('\n[node name="DriveCollision" type="StaticBody3D" parent="."]\ncollision_mask = 0\n')
        for k, b in enumerate(drives):
            (c0, c1, c2), (ox, oy, oz) = drive_ramp(b)
            nodes.append('\n[node name="Drive%d" type="CollisionShape3D" parent="DriveCollision"]\n'
                         'transform = Transform3D(%.6f, %.6f, %.6f, %.6f, %.6f, %.6f, %.6f, %.6f, %.6f, %.3f, %.3f, %.3f)\n'
                         'shape = SubResource("DriveShape")\n'
                         % (k, c0[0], c1[0], c2[0], c0[1], c1[1], c2[1], c0[2], c1[2], c2[2], ox, oy, oz))
    if lots:
        nodes.append('\n[node name="Plinths" type="MultiMeshInstance3D" parent="."]\nmultimesh = SubResource("Lots")\n')
        nodes.append('\n[node name="PlinthCollision" type="StaticBody3D" parent="."]\ncollision_mask = 0\n')
        for k, b in enumerate(lots):
            (c, s), _size, (ox, oy, oz) = plinth_boxes(b)
            nodes.append('\n[node name="Plinth%d" type="CollisionShape3D" parent="PlinthCollision"]\n'
                         'transform = Transform3D(%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f, %.3f, %.3f, %.3f)\n'
                         'shape = SubResource("LotShape%d")\n' % (k, c, s, -s, c, ox, oy, oz, k))
    return "".join(ext + sub + nodes)


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
        if name not in PED_DENSITY:
            raise SystemExit("island_buildings: region '%s' has no PED_DENSITY row" % name)
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


HOME_PARK = "ParkingLot4"     # the safe house's own car park (user, 2026-09-26)
HOME_PARK_KEEP = {"KonbiniS", "KonbiniL", "FamilyRestaurant", "GasStation", "GasKiosk", "StationBuilding",
                  "StationRural", "ParkingLot4", "ParkingLot8", "ParkingLot14"}


def home_park_neighbour(placed, b):
    """The street-front neighbour of `b` that can become its car park: same street side, touching it along the row
    (centres no further apart than the two half-widths + 3 m), a plain building whose lot is at least as wide as
    the car park. None when there is none."""
    pre = "|".join(b["key"].split("|")[:3]) + "|"
    need = type_aabb(HOME_PARK)[2] - type_aabb(HOME_PARK)[0]
    x0, _z0, x1, _z1, _h = type_aabb(b["type"])
    best = None
    for ob in placed:
        # a car park this already made (a second `anchors` run) is the answer, not a reason to make another
        if ob is not b and ob["type"] == HOME_PARK and ob.get("key", "").startswith(pre) \
                and math.hypot(ob["pos"][0] - b["pos"][0], ob["pos"][2] - b["pos"][2]) <= (x1 - x0) / 2.0 + 12.0:
            return ob
        if ob is b or ob.get("role") or ob["type"] in HOME_PARK_KEEP or not ob.get("key", "").startswith(pre) \
                or ob.get("key", "").endswith("|P") or "lot" not in ob:
            continue
        w = ob["lot"][2] - ob["lot"][0]
        d = math.hypot(ob["pos"][0] - b["pos"][0], ob["pos"][2] - b["pos"][2])
        if w + 1e-6 >= need and d <= (x1 - x0) / 2.0 + w / 2.0 + 3.0 and (best is None or d < best[0]):
            best = (d, ob)
    return best[1] if best else None


def apply_anchors(placed):
    """Give each anchored building its variant (and role), from PUBLIC_BUILDINGS and OPEN_BUILDINGS. Returns
    ({mission node: pos}, {role: {pos, yaw, type}}). Shared by `derive` and `anchors`, so moving an anchor needs
    no terrain dump."""
    anchored, roles = {}, {}
    for anchors, suffix, what in ((PUBLIC_BUILDINGS, "_Shop", "ALWAYS OPEN"), (OPEN_BUILDINGS, "_Open", "ENTERABLE")):
        for row in anchors:
            ox, oz, why = row[0], row[1], row[2]
            want = row[3] if len(row) > 3 else ""
            node = row[4] if len(row) > 4 else ""
            role = row[5] if len(row) > 5 else ""
            if ox is None:                 # beside the building another role resolved to
                ref = roles.get(oz)
                if ref is None:
                    print("island_buildings: no %s resolved -- %s has nowhere to go" % (oz, why))
                    continue
                ox, oz = ref["pos"][0], ref["pos"][2]
            # an anchored building must FRONT a street (user, 2026-09-26: the safe house had no door onto a street,
            # so the player could not get out): only a frontage-row slot, never a back row or a lot's parking
            pool = [b for b in placed if (b["type"] == want if want else True) and b is not None
                    and b.get("key", "|||").split("|")[2] == "0" and not b.get("key", "").endswith("|P")
                    and not b.get("role")]
            if role == "safehouse":
                # a safe house comes with its OWN car park beside it, where the starting car stands
                pool = [b for b in pool if home_park_neighbour(placed, b) is not None]
            reach = (ARMOURY_REACH if role == "armoury" else ANCHOR_REACH) if want else OPEN_MATCH
            near = min(pool, key=lambda b: (b["pos"][0] - ox) ** 2 + (b["pos"][2] - oz) ** 2, default=None)
            if near is None or math.hypot(near["pos"][0] - ox, near["pos"][2] - oz) > reach:
                print("island_buildings: no %s within %.0f m of (%.0f, %.0f) -- %s"
                      % (want or "building", reach, ox, oz, why))
                continue
            near["scene"] = near["type"] + suffix
            if node:
                anchored[node] = [round(v, 3) for v in near["pos"]]
            if role == "safehouse":
                park = home_park_neighbour(placed, near)
                if park["type"] == HOME_PARK:
                    park["role"] = "home_park"
                    print("island_buildings: the safe house keeps its car park")
                # the neighbour BECOMES the car park: same row line (front on it), same lot, a new type
                oa = math.radians(park["yaw"])
                dz = type_aabb(park["type"])[3] - type_aabb(HOME_PARK)[3] if park["type"] != HOME_PARK else 0.0
                park["pos"] = [round(park["pos"][0] + math.sin(oa) * dz, 3), park["pos"][1],
                               round(park["pos"][2] + math.cos(oa) * dz, 3)]
                if park["type"] != HOME_PARK:
                    print("island_buildings: the %s beside the safe house becomes its car park" % park["type"])
                park["type"], park["role"] = HOME_PARK, "home_park"
                park.pop("scene", None)
            if role:
                near["role"] = role
                roles[role] = {"pos": [round(v, 3) for v in near["pos"]], "yaw": near["yaw"], "type": near["type"]}
            print("island_buildings: %s at (%.1f, %.1f) is %s%s (%s)"
                  % (near["scene"], near["pos"][0], near["pos"][2], what,
                     ", and '%s' moves onto it" % node if node else "", why))
    return anchored, roles


def anchors_only(check):
    """Re-apply the anchors to the existing record (no terrain dump, no building moves), then the places."""
    doc = json.load(open(OUT))
    before = json.dumps(doc, sort_keys=True)
    for b in doc["buildings"]:
        b.pop("role", None)
        sc = b.get("scene", b["type"])
        if sc.endswith("_Open") or (sc.endswith("_Shop") and b["type"] not in SHOP_TYPES):
            b.pop("scene", None)
    doc["anchored_missions"], doc["roles"] = apply_anchors(doc["buildings"])
    changed = json.dumps(doc, sort_keys=True) != before
    if check:
        print("island_buildings: anchors %s" % ("STALE" if changed else "up to date"))
        return 1 if changed else 0
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1)
    return places_only(False)


def patch_missions(text, anchored):
    """Move each `Missions` child onto the building `derive` anchored it to.

    One owner for "where is this mission": the anchor's point in OPEN_BUILDINGS is a wish, the building actually
    chosen is the answer, and the scene follows it. Hand-editing the transform beside the constant is what let
    the two drift when the street grid moved (PLAN.md 3.18c)."""
    moved = []
    for node, pos in sorted(anchored.items()):
        pat = re.compile(r'(\[node name="%s" parent="Missions"[^\]]*\]\ntransform = Transform3D\()([^)]*)(\))'
                         % re.escape(node))
        m = pat.search(text)
        if m is None:
            print("island_buildings: Missions has no child '%s' to move" % node)
            continue
        v = [x.strip() for x in m.group(2).split(",")]
        if len(v) != 12:
            print("island_buildings: '%s' has an odd transform, left alone" % node)
            continue
        was = (float(v[9]), float(v[10]), float(v[11]))
        v[9], v[10], v[11] = "%.3f" % pos[0], "%.3f" % pos[1], "%.3f" % pos[2]
        text = text[:m.start()] + m.group(1) + ", ".join(v) + m.group(3) + text[m.end():]
        if math.dist(was, tuple(pos)) > 0.01:
            moved.append("%s %.1f m" % (node, math.dist(was, tuple(pos))))
    if moved:
        print("island_buildings: mission node(s) moved onto their building: %s" % ", ".join(moved))
    return text


START_NODE_ID = 910018000
START_HOLDER = "WeaponCounter"


def patch_start(text, doc):
    """PLAN.md 3 (user, 2026-09-22): the game starts at the SAFE HOUSE and the weapons are at the WEAPON COUNTER.

    One owner, like `patch_missions`: the anchors in PUBLIC_BUILDINGS choose the buildings, and this puts
      * `PlayerSpawn` (read by GameManager for every joining player and by WorldBounds for a fall-out recovery)
        and the `Player` 1.5 m out from the safe house's front door, facing the street;
      * the starting car (`VehicleRoot`) parked OFF the carriageway, nose to the street, in the nearest lot space
        beside the house (never in a lane: the traffic brain cannot pass a parked car);
      * the counter's `WeaponPad`s inside the weapon-counter konbini, in its own frame;
    and deletes the loose `Pickups` that used to lie at the old spawn point."""
    roles = doc.get("roles", {})
    home, shop = roles.get("safehouse"), roles.get("armoury")
    if home is None:
        print("island_buildings: no safe house anchored -- the start is left where it is")
        return text
    ny = doc["network_y"]
    x0, z0, x1, z1, _h = type_aabb(home["type"])
    a = math.radians(home["yaw"])
    sn, cs = math.sin(a), math.cos(a)
    hx, hy, hz = home["pos"]
    out = z1 + 1.5
    sx, sz = hx + sn * out, hz + cs * out
    sy = hy + LOT_RAISE + 0.9
    # facing OUT of the door: a character's forward is -Z, so the yaw is the building's plus 180
    fy = a + math.pi
    rot = "%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f" % (math.cos(fy), math.sin(fy), -math.sin(fy), math.cos(fy))
    spawn_tf = "Transform3D(%s, %.3f, %.3f, %.3f)" % (rot, sx, sy, sz)

    # the starting car: PARKED OFF THE CARRIAGEWAY, nose to the street, in the nearest lot space beside the safe
    # house (a car in the kerb lane is an obstacle the traffic brain cannot pass, so every car on that lane would
    # queue behind it). Searched along the frontage in the house's own frame: the car's footprint must lie on lots
    # and clear every building footprint by CAR_CLEAR.
    CAR_HX, CAR_HZ, CAR_CLEAR = 1.15, 2.4, 0.4
    rects = []                       # (cx, cz, cos, sin, x0, z0, x1, z1): a building footprint, world placement
    lots = []
    for ob in doc["buildings"]:
        if math.hypot(ob["pos"][0] - hx, ob["pos"][2] - hz) > 60.0:
            continue
        oa = math.radians(ob["yaw"])
        bx0, bz0, bx1, bz1, _bh = type_aabb(ob["type"])
        rects.append((ob["pos"][0], ob["pos"][2], math.cos(oa), math.sin(oa), bx0, bz0, bx1, bz1))
        if "lot" in ob:
            lx0, lz0, lx1, lz1 = ob["lot"]
            lots.append((ob["pos"][0], ob["pos"][2], math.cos(oa), math.sin(oa), lx0, lz0, lx1, lz1))

    def local(r, wx, wz):
        dx, dz = wx - r[0], wz - r[1]
        return dx * r[2] - dz * r[3], dx * r[3] + dz * r[2]      # inverse of x' = x c + z s, z' = -x s + z c

    def car_ok(wx, wz):
        pts = [(wx + cs * lx + sn * lz, wz - sn * lx + cs * lz)
               for lx in (-CAR_HX, 0.0, CAR_HX) for lz in (-CAR_HZ, 0.0, CAR_HZ)]
        for r in rects:
            for px, pz in pts:
                ux, uz = local(r, px, pz)
                if r[4] - CAR_CLEAR < ux < r[6] + CAR_CLEAR and r[5] - CAR_CLEAR < uz < r[7] + CAR_CLEAR:
                    return False
        for px, pz in pts:
            if not any(r[4] <= local(r, px, pz)[0] <= r[6] and r[5] <= local(r, px, pz)[1] <= r[7] for r in lots):
                return False
        return True

    # the nearest car park first (within 250 m): a bay, nose in (ParkingLot8: bays 2.5 x 5 m, centres at
    # x -8.75 + 2.5 k, z -3.87 in the lot's own frame, the front +Z on the street)
    car_tf = None
    best = (0.0,)
    if shop is not None:
        parks = [ob for ob in doc["buildings"] if ob.get("role") == "home_park"] or \
                [ob for ob in doc["buildings"] if ob["type"] == "ParkingLot8"
                 and math.hypot(ob["pos"][0] - hx, ob["pos"][2] - hz) < 250.0]
        park = min(parks, key=lambda ob: math.hypot(ob["pos"][0] - hx, ob["pos"][2] - hz), default=None)
        if park is not None:
            pa = math.radians(park["yaw"])
            ps, pc = math.sin(pa), math.cos(pa)
            # a bay, nose in: ParkingLot8's centres x -8.75 + 2.5 k, ParkingLot4's -3.75 + 2.5 k, both at z -3.87
            bx, bz = (-3.75 if park["type"] == "ParkingLot4" else -8.75), -3.87
            wx, wz = park["pos"][0] + bx * pc + bz * ps, park["pos"][2] - bx * ps + bz * pc
            # nose in: the car's forward (-Z) points to the lot's back (-Z)
            crot = "%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f" % (math.cos(pa), math.sin(pa), -math.sin(pa), math.cos(pa))
            car_tf = "Transform3D(%s, %.3f, %.3f, %.3f)" % (crot, wx, park["pos"][1] + LOT_RAISE + 0.6, wz)
            best = (math.hypot(wx - sx, wz - sz),)
    home_lot = next((ob["lot"] for ob in doc["buildings"]
                     if math.hypot(ob["pos"][0] - hx, ob["pos"][2] - hz) < 0.5 and "lot" in ob), [0, 0, 0, z1])
    for step in range(0 if car_tf is None else 161, 161):
        off = (step + 1) // 2 * 0.5 * (1 if step % 2 else -1)
        for back in (0.2, 2.0, 4.0, 6.0, 8.0, 10.0):
            lz = home_lot[3] - CAR_HZ - back
            wx, wz = hx + off * cs + lz * sn, hz - off * sn + lz * cs
            if car_ok(wx, wz):
                crot = "%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f" % (math.cos(fy), math.sin(fy), -math.sin(fy), math.cos(fy))
                car_tf = "Transform3D(%s, %.3f, %.3f, %.3f)" % (crot, wx, hy + LOT_RAISE + 0.6, wz)
                best = (math.hypot(wx - sx, wz - sz),)
                break
        if car_tf:
            break
    if car_tf is None and doc.get("passages"):
        # the one-row blocks leave no forecourt: park nose-in at the mouth of the nearest 路地 (3.2 m of open ground
        # off the street, out of every lane). A passage's centre is depth/2 back from its street end along -n.
        pg = min(doc["passages"], key=lambda q: math.hypot(q["pos"][0] - hx, q["pos"][2] - hz))
        qa = math.radians(pg["yaw"])
        qn = (math.sin(qa), math.cos(qa))
        back = pg["size"][1] / 2.0 - 3.5
        wx, wz = pg["pos"][0] + qn[0] * back, pg["pos"][2] + qn[1] * back
        crot = "%.6f, 0, %.6f, 0, 1, 0, %.6f, 0, %.6f" % (math.cos(qa), math.sin(qa), -math.sin(qa), math.cos(qa))
        car_tf = "Transform3D(%s, %.3f, %.3f, %.3f)" % (crot, wx, pg["pos"][1] + LOT_RAISE + 0.6, wz)
        best = (math.hypot(wx - sx, wz - sz),)
    if car_tf is None:
        print("island_buildings: no lot space beside the safe house fits a car -- the car is left where it is")

    def set_tf(t, name, parent, tf):
        pat = re.compile(r'(\[node name="%s" parent="%s"[^\]]*\]\n)(transform = Transform3D\([^)]*\)\n)?'
                         % (re.escape(name), re.escape(parent)))
        m = pat.search(t)
        if m is None:
            print("island_buildings: World.tscn has no %s/%s to move" % (parent, name))
            return t
        return t[:m.start()] + m.group(1) + "transform = %s\n" % tf + t[m.end():]

    text = set_tf(text, "Player", "Characters", spawn_tf)
    if car_tf:
        text = set_tf(text, "VehicleRoot", ".", car_tf)

    sections = itz.split_sections(text)
    added = []
    # no pads here any more: the konbini beside the safe house carries its own in its streamed cell, like every
    # other konbini. `generated` below still removes an old `WeaponCounter` block.
    nodes = ['[node name="PlayerSpawn" type="Node3D" parent="." unique_id=%d]\ntransform = %s\n\n'
             % (START_NODE_ID, spawn_tf)]

    def generated(header):
        if not header.startswith("[node"):
            return False
        name, parent = itz.attr(header, "name"), itz.attr(header, "parent")
        return ((parent == "." and name in ("PlayerSpawn", START_HOLDER, "Pickups"))
                or parent in (START_HOLDER, "Pickups"))
    new = itz.splice(sections, generated, [], nodes, ext=added)
    print("island_buildings: start at the safe house (%.1f, %.1f)%s; the konbini beside it is %s"
          % (sx, sz, ", car parked off the street %.1f m away" % best[0] if car_tf else "",
             shop["type"] if shop else "missing"))
    return new


def write(check):
    doc = json.load(open(OUT))
    cells = {}
    for b in doc["buildings"]:
        cells.setdefault(cell_of(b["pos"][0], b["pos"][2]), []).append(b)
    pass_cells = {}
    for p in doc.get("passages", ()):
        pass_cells.setdefault(cell_of(p["pos"][0], p["pos"][2]), []).append(p)
    for k in pass_cells:
        cells.setdefault(k, [])
    field_cells = {}
    half = FIELD_CHUNK / 2.0
    for f in doc.get("fields", ()):
        field_cells.setdefault(cell_of(f["x0"] + half, f["z0"] + half), []).append(f)
    for k in field_cells:
        cells.setdefault(k, [])
    changed = []
    want = set()
    os.makedirs(CELL_DIR, exist_ok=True)
    os.makedirs(HLOD_DIR, exist_ok=True)
    levels = tone_levels()
    aabbs = {}
    boxes = {}
    for (gx, gz), blds in sorted(cells.items()):
        out = []
        for b in blds:
            t = b["type"]
            if t not in aabbs:
                aabbs[t] = type_aabb(t)
            x0, z0, x1, z1, h = aabbs[t]
            tone = int(b.get("tone", 0))
            rgb = HLOD_GLASS.get(t) or (levels[tone]["srgb"] if tone < len(levels) else (150.0, 150.0, 150.0))
            out.append([round(b["pos"][0], 3), round(b["pos"][1] + LOT_RAISE + FLOOR_LIFT, 3), round(b["pos"][2], 3),
                        round(b["yaw"], 3), x0, z0, x1, z1, h, [round(c / 255.0, 4) for c in rgb]])
        if out:
            boxes["Bld_island_%d_%d" % (gx, gz)] = out
    body = json.dumps({"schema": 1, "source": "tools/island_buildings.py write",
                       "note": "per cell: [x, y, z, yaw deg, x0, z0, x1, z1, height, srgb 0-1] per building",
                       "cells": boxes}, separators=(",", ":")) + "\n"
    bpath = os.path.join(HLOD_DIR, "boxes.json")
    if not os.path.exists(bpath) or open(bpath).read() != body:
        changed.append(bpath)
        if not check:
            open(bpath, "w").write(body)
    for (gx, gz), blds in sorted(cells.items()):
        name = "Bld_island_%d_%d" % (gx, gz)
        path = os.path.join(CELL_DIR, name + ".tscn")
        want.add(name + ".tscn")
        body = cell_scene(name, blds, pass_cells.get((gx, gz), ()), field_cells.get((gx, gz), ()))
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
    new = patch_missions(new, doc.get("anchored_missions", {}))
    new = patch_start(new, doc)
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


def tones_gate(check):
    """PLAN.md 3.18p's gate, measured from the SHIPPED cell scenes rather than from the record that wrote them.

    Four things have to be true and each can fail on its own: the tone materials of a family are really
    DIFFERENT greys (a tone table whose entries render alike is the defect this item is about); every building
    whose type has a facade surface wears one; every override addresses the surface that type's OWN meta records
    (so a merge that re-ordered its surfaces cannot leave the overrides painting a roof); and the mixture is a
    mixture -- every tone used, none of them a rump."""
    tones = facade_tones()
    if not tones:
        print("island_buildings: no facade_tones.json -- run tools/building_kit/retone_downtown_kit.py")
        return 1 if check else 0
    bad = []
    # 1. within each family the tones are distinct COLOURS (PLAN.md 3.19(e): PLATEAU's measured wall palette)
    for fam, names in sorted(tones.items()):
        cols = {}
        for n in names:
            path = os.path.join(ROOT, "assets/world_source/kits/quaternius_downtown_city/materials", n + ".tres")
            m = re.search(r"^albedo_color = Color\(([\d.]+), ([\d.]+), ([\d.]+)", open(path).read(), re.M) \
                if os.path.exists(path) else None
            if m is None:
                bad.append("%s has no albedo_color" % n)
                continue
            cols[n] = tuple(float(m.group(k)) for k in (1, 2, 3))
        vals = list(cols.items())
        for a in range(len(vals)):
            for b2 in range(a + 1, len(vals)):
                d = math.dist(vals[a][1], vals[b2][1])
                if d < 0.06:          # a tint step under this is not a tone, it is noise
                    bad.append("%s: %s and %s differ by only %.3f" % (fam, vals[a][0], vals[b2][0], d))
        print("  %-24s %s" % (fam, ", ".join("%s (%.2f %.2f %.2f)" % (n, *cols[n]) for n in names if n in cols)))
    # 2-4. what the cell scenes actually say
    doc = json.load(open(OUT))
    want = [b for b in doc["buildings"] if facade_surfaces(scene_of(b))]
    expect = sum(len([f for f in facade_surfaces(scene_of(b)) if f in tones])
                 for b in want if int(b.get("tone", 0)) > 0)
    seen, wrong, used = 0, [], {}
    for f in sorted(os.listdir(CELL_DIR)) if os.path.isdir(CELL_DIR) else []:
        if not f.startswith("Bld_") or not f.endswith(".tscn"):
            continue
        text = open(os.path.join(CELL_DIR, f)).read()
        ids = {rid: name for name, rid in
               re.findall(r'\[ext_resource type="Material" path="[^"]*/([\w]+)\.tres" id="(tone[\w]+)"\]', text)}
        for node, body in re.findall(r'\[node name="Mesh" parent="\./(\S+?)" index="0"\]\n((?:surface_material_'
                                     r'override/\d+ = ExtResource\("tone[\w]+"\)\n)+)', text):
            scene = node.rsplit("_", 1)[0]
            surfs = facade_surfaces(scene)
            for surf, rid in re.findall(r'surface_material_override/(\d+) = ExtResource\("(tone[\w]+)"\)', body):
                seen += 1
                mat = ids.get(rid, "?")
                used[mat] = used.get(mat, 0) + 1
                fam = next((k for k, v in tones.items() if mat in v), None)
                if fam is None or surfs.get(fam) != int(surf):
                    wrong.append("%s/%s: %s on surface %s, its %s is %s"
                                 % (f, node, mat, surf, fam, surfs.get(fam)))
    if seen != expect:
        bad.append("%d overrides in the cells, %d wanted" % (seen, expect))
    bad += wrong[:5]
    # 4. the mixture: every tone worn by a fair share of the buildings that can wear one
    n = tone_count()
    mix = {}
    for b in want:
        mix[int(b.get("tone", 0))] = mix.get(int(b.get("tone", 0)), 0) + 1
    # every tone worn by at least half its MEASURED share (the regions lean dark, so not the full share)
    for t, lv in enumerate(tone_levels()[:n]):
        if mix.get(t, 0) < 0.5 * lv.get("share", 1.0 / n) * len(want):
            bad.append("tone %d is worn by only %d of %d buildings (PLATEAU share %.1f%%)"
                       % (t, mix.get(t, 0), len(want), 100 * lv.get("share", 0)))
    print("island_buildings: %d buildings wear a facade family, tone mix %s, %d overrides in %d materials"
          % (len(want), dict(sorted(mix.items())), seen, len(used)))
    for x in bad:
        print("  FAIL %s" % x)
    print("island_buildings: tones %s" % ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


def main(argv):
    if argv[:1] == ["derive"] and len(argv) >= 2:
        derive(argv[1])
        return 0
    if argv[:1] == ["write"]:
        return write("--check" in argv)
    if argv[:1] == ["anchors"]:
        return anchors_only("--check" in argv)
    if argv[:1] == ["places"]:
        return places_only("--check" in argv)
    if argv[:1] == ["sidewalks"]:
        return sidewalks_only("--check" in argv)
    if argv[:1] == ["clearance"]:
        return clearance("--check" in argv)
    if argv[:1] == ["tones"]:
        return tones_gate("--check" in argv)
    if argv[:1] == ["lots"]:
        return lots_record("--check" in argv)
    if argv[:1] == ["retone"]:
        return retone_record("--check" in argv)
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
