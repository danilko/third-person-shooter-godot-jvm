#!/usr/bin/env python3
"""island_rail_layout.py -- the rail network as a REVIEWABLE LAYOUT on the island as it is built now (PLAN.md 3.25).

    python3 tools/island_rail_layout.py [--out <png>] [--json <json>] [--check]

`tools/island_rail_plan.py` drew the first draft over the PRE-redo island; since the land redo (3.30) the station
sits inside C1 with its long axis east-west and every district moved, so that draft is stale. This tool is the
draft's successor and, once the user approves it, the ONE owner of the rail layout data that seeds the Road Kit
`rail` network (3.25) -- nothing in the road record, terrain or scenes is edited from here.

Everything it reports is MEASURED against what the game reads, in the RECORD frame (x east, y north, z = height
above the network):
  * the ground, from the committed land grid (`island_roadgen.Ground`);
  * every road, from the derived record `IslandRoads.roads.json`;
  * the frozen sites (`IslandSites.json`) and the placed buildings (`IslandBuildings.json`).

Per line it checks: the curve radius (>= R_MIN, the metro train's limit), that an at-grade stretch is on land,
the station spacing, and the vertical profile (elevated / at grade / bridge deck, ramped at <= GRADE_MAX between
them). Every place a line crosses a road is CLASSIFIED from the two heights there -- rail over road, road over rail,
or a level crossing (踏切) -- and a crossing the rules refuse (an arterial or expressway at grade, too little
clearance, a level crossing too oblique or too near a junction) is listed as a CONFLICT. The picture is the review.
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import island_roadgen as rg          # noqa: E402

RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
ARTERIALS = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.arterials.roads.json")
SITES = os.path.join(ROOT, "assets/world_source/buildings/IslandSites.json")
BUILDINGS = os.path.join(ROOT, "assets/world_source/buildings/IslandBuildings.json")
OUT_PNG = os.path.join(ROOT, "assets/world_source/reference/rail_layout_draft_2026-09-25.png")
OUT_JSON = os.path.join(ROOT, "assets/world_source/reference/rail_layout_draft_2026-09-25.json")

# ------------------------------------------------------------------------------------------ the rules
SHARE_M = 22.0           # a station stands on every line within this of it (parallel line pairs share a hub)
R_THROAT = 100.0         # m, a curve in a station THROAT (into a terminus / junction) may be this tight
R_MIN = 160.0            # m, the line's minimum radius (a 20 m-car metro EMU); a station throat may go to 100
GRADE_MAX = 0.035        # the metro train's ruling grade
TRACK_HALF = 5.5         # double track + clearances: ~11 m
CORRIDOR_HALF = 8.0      # the fenced corridor the derive must keep clear (track + walkway + fence)
VIADUCT_WIN = 50.0      # m either side: the ground a viaduct's deck height follows (its highest point)
CUT_Z = -7.8            # rail head in a cutting under a road: 6 m of catenary + ~1.5 m of road deck over it
ELEVATED_Z = 8.0         # rail head on a viaduct: 4.7 m road clearance + ~1.5 m structure + margin
DECK_T = 1.5             # viaduct structure depth under the rail head
CLEAR_ROAD_UNDER = 4.7   # a road passing under a rail viaduct
CLEAR_RAIL_UNDER = 6.0   # a train (catenary) passing under a road deck
LEVEL_DZ = 1.0           # within this, rail and road share the ground: a level crossing
LX_MIN_ANGLE = 60.0      # a 踏切 is kept near 90 deg; refused below this
LX_JUNCTION_CLEAR = 30.0 # a queue must not back into a crossing from a junction
STATION_MIN_GAP = 500.0  # Tokyo's metro rarely spaces stations under ~500 m
BRIDGE_DECK_Z = 24.0     # library_landmarks: the Rainbow Bridge's lower deck (R7: rail)
BRIDGE_Y = (-697.0, -1546.0)   # island_rainbow_bridge.crossing_plan: centre y -1122, half length 424.5
ROAD_HALF = {"expressway": 6.0, "arterial": 14.5, "street": 7.0}   # paved half width, for the side-by-side check

# ------------------------------------------------------------------------------------------ the layout (DRAFT)
# A line is a list of CORNERS (record x, y) filleted at `radius`, and a FORM per span between corners:
#   "elev"   the core viaduct at ELEVATED_Z over the ground under it
#   "grade"  on a low ballast bed at the ground
#   "bridge" the Rainbow Bridge's lower deck, BRIDGE_DECK_Z
# A ramp between two forms is laid by the profile (GRADE_MAX), centred on the span boundary.
LINES = {
    # MAIN: Farm -> Res. North -> CENTRAL -> Bay -> Suburb -> Airport, ELEVATED from Res. North to the airport.
    # Central's platforms run EAST-WEST (the station stands north of ekimae_dori, 320 m along it), so the main line
    # runs THROUGH them: from the north it comes down x 1110 (between higashi_hondori and C1's east side, clear of
    # the diamond ramps), enters Central from the EAST, leaves WEST, and turns south at x 160 -- west of the C1 south
    # JCT, whose ramps fill x 325..875. East along y -460 (over eki_minami, under the airport spur and the Wangan
    # JCT), then onto the Rainbow Bridge's LOWER deck (R7), leaving the spur's axis east at the south anchorage.
    "Main line": {
        "colour": (230, 70, 70), "radius": 220.0,
        "corners": [(1110.0, 1400.0), (1110.0, 215.0), (160.0, 215.0), (160.0, -460.0), (1250.0, -460.0),
                    (1250.0, -1480.0), (1300.0, -1700.0), (1300.0, -1960.0)],
        "radii": {1: 180.0},
        # (x, y, form from here on)
        "form": [(1110.0, 1400.0, "grade"), (1110.0, 1030.0, "elev"), (1250.0, -560.0, "bridge"),
                 (1300.0, -1700.0, "elev")],
    },
    # WEST: CENTRAL -> Castle Town -> Residential -> Industry -> Harbour (user, 2026-09-25: Tokyo Station is where the
    # lines MEET, so the West line starts there). It leaves Central's west throat with the main line and splits
    # from it at x ~380 (the main turns south at x 160), runs on west along y 215 over C1's west side, turns south
    # along x -150 and west along the foot of the castle's slope (y -170, the flat strip between the hill and
    # rinkai_dori) to Castle Town, 130 m below Shuri Castle. It turns south along x -900 over rinkai_dori to
    # Residential, east along y -550 (the residential/industry edge) to Industry, and south along x 0 (the street-free
    # strip east of chuo_dori) to Harbour, north of the coast ring. ELEVATED throughout:
    # it crosses rinkai_dori and C1, and at grade it could reach neither the castle's flat strip nor the grid.
    "West line": {
        "colour": (60, 150, 230), "radius": 200.0,
        "corners": [(782.0, 215.0), (-150.0, 215.0), (-150.0, -170.0), (-900.0, -170.0), (-900.0, -550.0),
                    (0.0, -550.0), (0.0, -1040.0)],
        "form": [(782.0, 215.0, "elev")],
    },
}

# name: (line, x, y, kind, platform length m, parking kind (3.24(f)), note)
STATIONS = {
    "Farm":              ("Main line", 1110.0, 1320.0, "small", 90.0, "park_and_ride", "terminus, at grade"),
    "Residential North": ("Main line", 1110.0, 820.0, "standard", 90.0, "small_lot", "elevated"),
    "Central":           ("Main line", 782.0, 215.0, "hub", 300.0, "multistorey",
                          "elevated; the hub: the North, South and West lines meet here"),
    "Bay":               ("Main line", 160.0, -190.0, "standard", 90.0, "small_lot", "elevated"),
    "Waterpark":         ("Main line", 470.0, -460.0, "standard", 90.0, "small_lot", "elevated; the south waterfront park"),
    "Suburb":            ("Main line", 880.0, -460.0, "standard", 90.0, "park_and_ride", "elevated"),
    "Airport":           ("Main line", 1300.0, -1850.0, "standard", 90.0, "park_and_ride", "terminus, elevated"),
    "Castle Town":       ("West line", -620.0, -170.0, "standard", 90.0, "park_and_ride", "elevated; Shuri Castle 0.13 km up"),
    "Residential":       ("West line", -720.0, -550.0, "standard", 90.0, "small_lot", "elevated"),
    "Industry":          ("West line", -260.0, -550.0, "standard", 90.0, "small_lot", "elevated"),
    "Harbour":           ("West line", 0.0, -960.0, "standard", 90.0, "park_and_ride", "terminus, elevated; freight yard beside it"),
}
FREIGHT_YARD = (90.0, -1020.0)
# ------------------------------------------------------------------------------------------ alternative layouts
# `--layout hub_at_bay` (user, 2026-09-25): the HUB (the Tokyo Station building) moves to where the lines really meet --
# Bay, on the main line's north-south leg at x 160 -- and the old Central site becomes a Downtown station. The West
# side becomes a Japanese-style Y: one junction station (分岐駅, cross-platform change, a flying junction just past
# it), one branch to Industry-side Harbour, the other to Residential and Castle Town (the last stop).
LAYOUTS = {"v2": None}
LAYOUTS["hub_at_bay"] = {
    "lines": {
        "Main line": dict(LINES["Main line"]),
        "West trunk": {
            "colour": (60, 150, 230), "radius": 200.0,
            "corners": [(160.0, 60.0), (160.0, -550.0), (-445.0, -550.0), (-900.0, -550.0), (-900.0, -170.0),
                        (-500.0, -170.0)],
            "form": [(160.0, 60.0, "elev")],
        },
        "Harbour branch": {
            "colour": (40, 190, 170), "radius": 200.0,
            "corners": [(60.0, -550.0), (-445.0, -550.0), (-445.0, -1040.0)],
            "form": [(60.0, -550.0, "elev")],
        },
    },
    "stations": {
        "Farm":              ("Main line", 1110.0, 1320.0, "small", 90.0, "park_and_ride", "terminus, at grade"),
        "Residential North": ("Main line", 1110.0, 820.0, "standard", 90.0, "small_lot", "elevated"),
        "Downtown":          ("Main line", 782.0, 215.0, "large", 200.0, "multistorey",
                              "elevated; the old Central site (the station reserve stays)"),
        "Central":           ("Main line", 160.0, -120.0, "hub", 230.0, "multistorey",
                              "elevated; the HUB: the Main line and the West Y meet here"),
        "Waterpark":         ("Main line", 470.0, -460.0, "standard", 90.0, "small_lot", "elevated"),
        "Suburb":            ("Main line", 880.0, -460.0, "standard", 90.0, "park_and_ride", "elevated"),
        "Airport":           ("Main line", 1300.0, -1850.0, "standard", 90.0, "park_and_ride", "terminus, elevated"),
        "Industry Jn":       ("West trunk", -150.0, -550.0, "junction", 120.0, "small_lot",
                              "elevated; the Y splits here: Harbour one way, Residential + Castle Town the other"),
        "Residential":       ("West trunk", -720.0, -550.0, "standard", 90.0, "small_lot", "elevated"),
        "Castle Town":       ("West trunk", -620.0, -170.0, "standard", 90.0, "park_and_ride",
                              "terminus, elevated; Shuri Castle 0.13 km up"),
        "Harbour":           ("Harbour branch", -445.0, -990.0, "standard", 90.0, "park_and_ride",
                              "terminus, elevated; freight yard beside it"),
    },
    "yard": (-445.0, -1075.0),
    "title": "option B: hub at Bay, under C1",
    "notes": ["Central (hub) at Bay; C1 crosses over its middle.", "The old Central site becomes Downtown."],
    # the hub's block: 130 m across the tracks x 320 m along them; block streets inside it go (drawn light green)
    "reserve": (160.0, -110.0, 130.0, 320.0),
}


# `--layout hub_south_of_c1` (user, 2026-09-25: "do B, moved up so the station is not directly under C1; the old
# Central becomes a smaller station"). The hub stays on the main line's north-south leg at x 160 but stands wholly
# SOUTH of C1 (platforms y -130..-370): the main line now turns east at y -600 (Waterpark then sits by the waterfront
# park), and the West line runs on south past the hub, splitting from the main line on a flying junction, to a Y at
# Industry Jn in the industry grid (y -770): Harbour one way, Residential and Castle Town (last) the other.
_MAIN_S = dict(LINES["Main line"])
_MAIN_S["radii"] = {1: 180.0, 3: R_MIN}   # the turn east at (160, -460) at the line minimum: the hub fits south of C1
LAYOUTS["hub_south_of_c1"] = {
    "lines": {
        "Main line": _MAIN_S,
        "West trunk": {
            "colour": (60, 150, 230), "radius": 200.0,
            "corners": [(160.0, -130.0), (160.0, -770.0), (-900.0, -770.0), (-900.0, -170.0), (-500.0, -170.0)],
            "form": [(160.0, -130.0, "elev")],
        },
        "Harbour branch": {
            "colour": (40, 190, 170), "radius": 200.0,
            "corners": [(0.0, -770.0), (-445.0, -770.0), (-445.0, -1050.0)],
            "form": [(0.0, -770.0, "elev")],
            "throat": [1],      # the curve into the Harbour terminus: a station throat, R >= R_THROAT
        },
    },
    "stations": {
        "Farm":              ("Main line", 1110.0, 1320.0, "small", 90.0, "park_and_ride", "terminus, at grade"),
        "Residential North": ("Main line", 1110.0, 820.0, "standard", 90.0, "small_lot", "elevated"),
        "Downtown":          ("Main line", 782.0, 215.0, "large", 200.0, "multistorey",
                              "elevated; the old Central site, a smaller station"),
        "Central":           ("Main line", 160.0, -215.0, "hub", 170.0, "multistorey",
                              "elevated; the HUB, wholly south of C1: the Main line and the West Y meet here"),
        "Waterpark":         ("Main line", 470.0, -460.0, "standard", 90.0, "small_lot", "elevated"),
        "Suburb":            ("Main line", 880.0, -460.0, "standard", 90.0, "park_and_ride", "elevated"),
        "Airport":           ("Main line", 1300.0, -1850.0, "standard", 90.0, "park_and_ride", "terminus, elevated"),
        "Industry Jn":       ("West trunk", -150.0, -770.0, "junction", 120.0, "small_lot",
                              "elevated; the Y splits here: Harbour one way, Residential + Castle Town the other"),
        "Residential":       ("West trunk", -900.0, -470.0, "standard", 90.0, "small_lot", "elevated"),
        "Castle Town":       ("West trunk", -620.0, -170.0, "standard", 90.0, "park_and_ride",
                              "terminus, elevated; Shuri Castle 0.13 km up"),
        "Harbour":           ("Harbour branch", -445.0, -1000.0, "standard", 90.0, "park_and_ride",
                              "terminus, elevated; freight yard beside it"),
    },
    "yard": (-445.0, -1075.0),
    "title": "B2: hub south of C1, West Y",
    "notes": ["Central (the hub) at Bay, wholly SOUTH of C1:",
              "its platforms start 20 m clear of the expressway.",
              "The old Central site becomes Downtown (smaller).",
              "West Y: Industry Jn splits to Harbour, and to",
              "Residential > Castle Town (the last stop)."],
    "reserve": (160.0, -225.0, 130.0, 210.0),
}


# `--layout loop` (user, 2026-09-25: "a separate line south from Downtown, and another for the suburb to make a full
# circle?"). The hub_south_of_c1 layout with the core closed into a LOOP (the Osaka Loop Line idea): Central -> north
# along x 160 -> east through Downtown -> south along x 1110 -> west through Suburb and Waterpark -> back to Central.
# Downtown becomes a junction too (the North line joins the loop at its east throat) and the Airport line leaves the
# loop east of Suburb. The West Y still leaves Central southwards.
_HS = LAYOUTS["hub_south_of_c1"]
LAYOUTS["loop"] = {
    "lines": {
        "Loop line": {
            "colour": (120, 200, 60), "radius": 180.0, "closed": True,
            "corners": [(160.0, 215.0), (1110.0, 215.0), (1110.0, -460.0), (160.0, -460.0)],
            "radii": {3: R_MIN},
            "form": [(160.0, 215.0, "elev")],
        },
        "North line": {
            "colour": (230, 70, 70), "radius": 180.0,
            "corners": [(1110.0, 1400.0), (1110.0, 215.0), (600.0, 215.0)],
            "form": [(1110.0, 1400.0, "grade"), (1110.0, 1030.0, "elev")],
        },
        "Airport line": {
            "colour": (255, 140, 200), "radius": 220.0,
            "corners": [(700.0, -460.0), (1250.0, -460.0), (1250.0, -1480.0), (1300.0, -1700.0), (1300.0, -1960.0)],
            "form": [(700.0, -460.0, "elev"), (1250.0, -697.0, "bridge"), (1300.0, -1700.0, "elev")],
        },
        "West trunk": _HS["lines"]["West trunk"],
        "Harbour branch": _HS["lines"]["Harbour branch"],
    },
    "stations": dict({k: v for k, v in _HS["stations"].items()
                      if k not in ("Downtown", "Central", "Waterpark", "Suburb", "Farm", "Residential North",
                                   "Airport")},
                     **{
        "Farm":              ("North line", 1110.0, 1320.0, "small", 90.0, "park_and_ride", "terminus, at grade"),
        "Residential North": ("North line", 1110.0, 820.0, "standard", 90.0, "small_lot", "elevated"),
        "Downtown":          ("Loop line", 782.0, 215.0, "large", 200.0, "multistorey",
                              "elevated; a junction: the North line joins the loop here"),
        "Central":           ("Loop line", 160.0, -215.0, "hub", 170.0, "multistorey",
                              "elevated; the HUB: the loop and the West Y meet here"),
        "Waterpark":         ("Loop line", 470.0, -460.0, "standard", 90.0, "small_lot", "elevated"),
        "Suburb":            ("Loop line", 880.0, -460.0, "standard", 90.0, "park_and_ride",
                              "elevated; the Airport line leaves just east of it"),
        "Airport":           ("Airport line", 1300.0, -1850.0, "standard", 90.0, "park_and_ride", "terminus, elevated"),
    }),
    "yard": _HS["yard"],
    "title": "C: B2 + a loop line",
    "notes": ["B2 with the core closed into a LOOP (Osaka Loop idea):",
              "Central > Downtown > Suburb > Waterpark > Central.",
              "Downtown is a junction too: the North line joins it.",
              "The Airport line leaves the loop east of Suburb."],
    "reserve": _HS["reserve"],
}


# `--layout tokyo_hub` (user, 2026-09-25: "Tokyo Station is a multi-line hub; redesign as a Japanese rail planner /
# senior level designer would, keeping the land and zones; C1 is fully elevated; the rail mostly at GRADE").
# Central stays at the Tokyo Station reserve and is a TERMINAL HUB: three lines use it -- the Main line runs through
# (Farm .. Airport), the West line and the Harbour line START there on their own platforms (the Chuo Line at Tokyo).
# Everything is at grade on a fenced ballast bed: block streets get a level crossing (fumikiri), arterials an
# underpass, C1 passes over. The one elevated stretch is the climb to the Rainbow Bridge's lower deck.
LAYOUTS["tokyo_hub"] = {
    "underpass": True,
    "lines": {
        "Main line": {
            "colour": (230, 70, 70), "radius": 220.0,
            "corners": [(1110.0, 1400.0), (1110.0, 215.0), (205.0, 215.0), (205.0, -475.0), (1250.0, -475.0),
                        (1250.0, -1480.0), (1300.0, -1700.0), (1300.0, -1960.0)],
            "radii": {1: 180.0, 3: R_MIN},
            "form": [(1110.0, 1400.0, "grade"), (835.0, -475.0, "elev"), (1250.0, -697.0, "bridge"),
                     (1300.0, -1700.0, "elev")],
        },
        "West line": {
            "colour": (60, 150, 230), "radius": 200.0,
            # Central -> City West -> Castle Town, along the flat strip at the castle's foot; south down the mid-block
            # corridor x -665 (under nishi_dori and rinkai_dori away from their junctions) to Residential, near the
            # district's centre; east along y -660 -- the residential/industry edge, the light-industry band -- to
            # Light Industry. Every block street it crosses is crossed square and mid-block (55 m from a junction).
            "corners": [(782.0, 225.0), (-115.0, 225.0), (-115.0, -160.0), (-665.0, -160.0), (-665.0, -660.0),
                        (-300.0, -660.0)],
            "radii": {3: R_MIN, 4: R_MIN},
            "form": [(782.0, 225.0, "grade")],
        },
        "Harbour line": {
            "colour": (40, 190, 170), "radius": 200.0,
            "corners": [(782.0, 205.0), (185.0, 205.0), (185.0, -930.0)],
            "form": [(782.0, 205.0, "grade")],
        },
    },
    "stations": {
        "Farm":              ("Main line", 1110.0, 1320.0, "small", 90.0, "park_and_ride", "terminus"),
        "Residential North": ("Main line", 1110.0, 820.0, "standard", 90.0, "small_lot", ""),
        "Central":           ("Main line", 782.0, 215.0, "hub", 300.0, "multistorey",
                              "the TERMINAL HUB: Main through; West and Harbour lines start here"),
        "Bay":               ("Main line", 205.0, -190.0, "junction", 120.0, "small_lot",
                              "junction: the Harbour line leaves the Main line here"),
        "Waterpark":         ("Main line", 470.0, -475.0, "standard", 90.0, "small_lot", ""),
        "Suburb":            ("Main line", 880.0, -475.0, "standard", 90.0, "park_and_ride",
                              "elevated: the climb to the bridge"),
        "Airport":           ("Main line", 1300.0, -1850.0, "standard", 90.0, "park_and_ride", "terminus"),
        "City West":         ("West line", -115.0, 20.0, "standard", 90.0, "small_lot", ""),
        "Castle Town":       ("West line", -450.0, -160.0, "standard", 90.0, "park_and_ride",
                              "Shuri Castle 0.19 km up"),
        "Residential":       ("West line", -665.0, -440.0, "standard", 90.0, "small_lot",
                              "near the residential district's centre"),
        "Light Industry":    ("West line", -345.0, -660.0, "standard", 90.0, "small_lot",
                              "terminus; the light-industry band between residential and industry"),
        "Industry":          ("Harbour line", 185.0, -560.0, "standard", 90.0, "small_lot", ""),
        "Harbour":           ("Harbour line", 185.0, -875.0, "standard", 90.0, "park_and_ride",
                              "terminus; freight yard beside it"),
    },
    "yard": (110.0, -900.0),
    "title": "Tokyo hub, at grade",
    "notes": ["Central stays at the Tokyo Station site and is a",
              "TERMINAL HUB: the Main line runs through it; the",
              "West and Harbour lines START there (the Chuo Line",
              "at Tokyo). At grade: level crossings at block",
              "streets, underpasses at arterials; C1 passes over."],
}


# `--layout tokyo_loop` (user, 2026-09-25: "should the industrial line cover light industry, or make it circular?").
# Japanese practice: never send a through line 500 m out and back to reach a station (Industry -> Light Industry ->
# Harbour would); when two branches run into one district, JOIN them. The shape is the Toei Oedo Line's "6": the LOOP
# line leaves Central's west throat on one track pair, runs City West > Castle Town > Residential > Light Industry >
# Industry > Bay and comes back into Central on another, so it needs no ring through downtown. The Harbour line runs
# Central > Bay and straight on south where the loop turns north, to Harbour, and FREIGHT carries on under the coast
# ring (an underpass) into the squared container terminal (IslandSites.json yaw 90, on the straight quay at x 224).
_TH = LAYOUTS["tokyo_hub"]
LAYOUTS["tokyo_loop"] = {
    "underpass": True,
    "lines": {
        "Main line": _TH["lines"]["Main line"],
        "Loop line": {
            "colour": (60, 150, 230), "radius": 200.0,
            "corners": [(782.0, 225.0), (-115.0, 225.0), (-115.0, -160.0), (-665.0, -160.0), (-665.0, -660.0),
                        (185.0, -660.0), (185.0, 205.0), (782.0, 205.0)],
            "radii": {3: R_MIN, 4: R_MIN, 5: R_MIN},
            "form": [(782.0, 225.0, "grade")],
        },
        "Harbour line": {
            "colour": (40, 190, 170), "radius": 200.0,
            # shares the loop's return tracks from Central to where the loop turns west at (185, -660)
            "corners": [(782.0, 205.0), (185.0, 205.0), (185.0, -1300.0)],
            "form": [(782.0, 205.0, "grade")],
            "into_site": "container_terminal",
        },
    },
    "stations": {
        "Farm":              _TH["stations"]["Farm"],
        "Residential North": _TH["stations"]["Residential North"],
        "Central":           ("Main line", 782.0, 215.0, "hub", 300.0, "multistorey",
                              "the TERMINAL HUB: Main through; the Loop and Harbour lines start here"),
        "Bay":               ("Main line", 205.0, -190.0, "junction", 120.0, "small_lot",
                              "junction: Main, Loop and Harbour lines"),
        "Waterpark":         _TH["stations"]["Waterpark"],
        "Suburb":            _TH["stations"]["Suburb"],
        "Airport":           _TH["stations"]["Airport"],
        "City West":         ("Loop line", -115.0, 20.0, "standard", 90.0, "small_lot", ""),
        "Castle Town":       ("Loop line", -450.0, -160.0, "standard", 90.0, "park_and_ride", "Shuri Castle 0.19 km up"),
        "Residential":       ("Loop line", -665.0, -440.0, "standard", 90.0, "small_lot", "near the district's centre"),
        "Light Industry":    ("Loop line", -445.0, -660.0, "standard", 90.0, "small_lot",
                              "the light-industry band between residential and industry"),
        "Industry":          ("Loop line", -25.0, -660.0, "standard", 90.0, "small_lot", ""),
        "Harbour":           ("Harbour line", 185.0, -875.0, "standard", 90.0, "park_and_ride",
                              "passenger terminus; FREIGHT runs on into the container terminal"),
    },
    "yard": (110.0, -800.0),
    "title": "Tokyo hub + a '6' loop",
    "notes": ["Central (Tokyo Station site) is the terminal hub.",
              "The LOOP line runs out and back into Central, like",
              "the Toei Oedo Line's '6': Light Industry and",
              "Residential get trains both ways. The Harbour line",
              "runs straight on to Harbour; freight on under the",
              "coast ring into the squared container terminal."],
}


# `--layout tokyo_branches` (user, 2026-09-25: "Industry -> Light Industry -> Harbour with Harbour the last station,
# and Residential the last station of the blue line"). Two radial branches from the hub, each with a clear terminus --
# the private-railway pattern out of Shinjuku / Shibuya. The HARBOUR line is the industrial chain: Central > Bay >
# Industry > Light Industry > Harbour, which moves west to the harbour block's middle so the line never doubles back;
# FREIGHT leaves it where it turns west and runs straight on south into the container terminal. The BLUE line is
# Central > City West > Castle Town > Residential (terminus).
LAYOUTS["tokyo_branches"] = {
    "underpass": True,
    "lines": {
        "Main line": _TH["lines"]["Main line"],
        "Blue line": {
            "colour": (60, 150, 230), "radius": 200.0,
            "corners": [(782.0, 225.0), (-115.0, 225.0), (-115.0, -160.0), (-665.0, -160.0), (-665.0, -482.0)],
            "radii": {3: R_MIN},
            "form": [(782.0, 225.0, "grade")],
            "throat": [3],      # the curve into the Residential terminus
        },
        "Harbour line": {
            "colour": (40, 190, 170), "radius": 200.0,
            # Bay > south to Industry, the freight junction (the siding carries straight on south just past it) >
            # west along y -770 (mid-block) > Light Industry > south down the mid-block at x -445 (kichi_dori, the
            # military base's access street at x -500, is kept open) > Harbour, towards
            # the gap between the military base (west) and the container terminal (east), north of the coast ring
            "corners": [(782.0, 205.0), (185.0, 205.0), (185.0, -770.0), (-445.0, -770.0), (-445.0, -1040.0)],
            "radii": {2: R_MIN, 3: R_MIN},
            "throat": [3],      # the curve into the Harbour terminus
            "form": [(782.0, 205.0, "grade")],
        },
        # the freight-only siding (a 臨港線): from the freight terminal at Industry straight on into the container
        # terminal. Freight TRAINS share the Harbour and Main lines' tracks, the JR Freight way.
        "Freight siding": {
            "colour": (150, 80, 200), "radius": 200.0,
            "corners": [(185.0, -550.0), (185.0, -1300.0)],
            "form": [(185.0, -550.0, "grade")],
            "into_site": "container_terminal",
        },
    },
    "stations": {
        "Farm":              _TH["stations"]["Farm"],
        "Residential North": _TH["stations"]["Residential North"],
        "Central":           ("Main line", 782.0, 215.0, "hub", 300.0, "multistorey",
                              "the TERMINAL HUB: Main through; the Blue and Harbour lines start here"),
        "Bay":               ("Main line", 205.0, -190.0, "junction", 120.0, "small_lot", "junction: Main and Harbour lines"),
        "Waterpark":         _TH["stations"]["Waterpark"],
        "Suburb":            _TH["stations"]["Suburb"],
        "Airport":           _TH["stations"]["Airport"],
        "City West":         ("Blue line", -115.0, 20.0, "standard", 90.0, "small_lot", ""),
        "Castle Town":       ("Blue line", -450.0, -160.0, "standard", 90.0, "park_and_ride", "Shuri Castle 0.19 km up"),
        "Residential":       ("Blue line", -665.0, -520.0, "standard", 90.0, "small_lot", "terminus, near the district's centre"),
        "Industry":          ("Harbour line", 185.0, -545.0, "junction", 100.0, "small_lot",
                              "the big one: passenger station + the FREIGHT TERMINAL (貨物駅) beside it; the "
                              "freight siding to the container terminal leaves here"),
        "Light Industry":    ("Harbour line", -207.0, -770.0, "standard", 90.0, "small_lot",
                              "the light-industry band between residential and industry"),
        "Harbour":           ("Harbour line", -445.0, -990.0, "standard", 90.0, "park_and_ride",
                              "terminus, passengers only: between the military base and the container terminal"),
    },
    "yard": (260.0, -640.0),
    "title": "Tokyo hub + two branches",
    "notes": ["Central (Tokyo Station site) is the terminal hub.",
              "Two radial branches, each with a clear terminus:",
              "the Blue line ends at Residential, the Harbour line",
              "(the industrial chain) at Harbour. Freight shares",
              "the tracks (JR Freight); the freight terminal is at",
              "Industry, and a freight siding runs into the terminal."],
}


# `--layout tokyo_straight` (user, 2026-09-25: "a straight line along the freight lane; split only at the harbour").
# The Harbour line runs straight south along x 185 -- the street-free strip east of chuo_dori, under the elevated
# Wangan -- and splits only at the harbour: FREIGHT straight on into the container terminal (the siding is its last
# few hundred metres, the freight terminal beside the container terminal, as Tokyo's is at Oi), PASSENGERS curve west
# to Harbour station on the terminal's west side, between it and the military base. Light Industry cannot sit on that
# straight line (the band is WEST, between Residential and the industry grid), so it is the Blue line's next stop after
# Residential.
_TB = LAYOUTS["tokyo_branches"]
LAYOUTS["tokyo_straight"] = {
    # user, 2026-09-25: the core elevated, rail at grade with 踏切 outside it (option A in the core + C outside). An underpass cannot be built: the world's one
    # water box tops out at y 0 and the city plain is at 0.6 m, so a road dipped under the rail floods.
    "crossing": "level",
    "lines": {
        # THE CITY CORE IS ELEVATED (連続立体交差), outside it the rail is at grade with 踏切 (user, 2026-09-25). The
        # core is C1's interior; each line passes UNDER C1 at grade (its deck leaves no room for a viaduct) and
        # climbs onto the viaduct ~250 m inside the ring (8 m at the 3.5 % ruling grade) -- a ramp lies on the
        # LOWER form's side, so the "elev" breakpoint is set back from C1 by the ramp's length.
        "Main line": dict(_TH["lines"]["Main line"], form=[
            (1110.0, 1400.0, "grade"), (1110.0, 300.0, "elev"), (205.0, 140.0, "grade"),
            (835.0, -475.0, "elev"), (1250.0, -697.0, "bridge"), (1300.0, -1700.0, "elev")]),
        "Blue line": {
            "colour": (60, 150, 230), "radius": 200.0,
            # Central > City West > Castle Town > Residential > Light Industry (user, 2026-09-26): the line runs on
            # south through the 準工業 district to its terminus there, so that district has TWO stations on two lines
            # -- this one on its west side, the Harbour line's Industry on its east -- and its commuters split between
            # them instead of all changing at Bay
            "corners": [(782.0, 225.0), (-115.0, 225.0), (-115.0, -160.0), (-665.0, -160.0), (-665.0, -990.0)],
            "radii": {3: R_MIN},
            "form": [(782.0, 225.0, "elev"), (295.0, 225.0, "grade")],
        },
        "Harbour line": {
            "colour": (40, 190, 170), "radius": 200.0,
            # straight all the way: Bay > Industry > Harbour at the container terminal's gate, where the passenger
            # tracks end at Harbour's platforms and the freight tracks run on beside them into the terminal
            "corners": [(782.0, 205.0), (185.0, 205.0), (185.0, -1110.0)],
            "form": [(782.0, 205.0, "elev"), (185.0, 140.0, "grade")],
        },
        "Freight siding": {
            "colour": (150, 80, 200), "radius": 200.0,
            # the E&S tracks (着発線荷役方式, JR Freight): freight trains share the Harbour line through Bay (the junction)
            # and Industry (its extra track is the refuge 待避線 where a freight waits to be overtaken), then take the
            # arrival/departure tracks on the east side of Harbour's passenger platforms and stop there; top lifters
            # work the boxes from a handling apron beside them at the container terminal's NORTH gate, and trucks carry
            # them the last 60 m into the stack. Rail never enters the terminal (Tokyo Freight Terminal beside the
            # Oi piers is the model); no shunting yard
            # STATION TRACKS: both ends inside Harbour's platform box (its north end used to stop 57 m out on open
            # ground beside the Harbour line with nothing joined to it). The turnout that lets a freight train in off
            # the Harbour line belongs with the train runtime.
            "corners": [(205.0, -1015.0), (205.0, -1115.0)],
            "form": [(205.0, -1015.0, "grade")],
        },
    },
    "stations": {
        "Farm":              _TH["stations"]["Farm"],
        "Residential North": _TH["stations"]["Residential North"],
        "Central":           _TB["stations"]["Central"],
        "Bay":               _TB["stations"]["Bay"],
        "Waterpark":         _TH["stations"]["Waterpark"],
        "Suburb":            _TH["stations"]["Suburb"],
        "Airport":           _TH["stations"]["Airport"],
        "City West":         _TB["stations"]["City West"],
        "Castle Town":       _TB["stations"]["Castle Town"],
        "Residential":       ("Blue line", -665.0, -520.0, "standard", 90.0, "small_lot",
                              "the housing's station, at the 準工業 belt's north edge"),
        "Light Industry":    ("Blue line", -665.0, -960.0, "standard", 90.0, "small_lot",
                              "terminus: the west station of the 準工業 district (町工場 + housing); Industry on the "
                              "Harbour line is its east station"),
        "Industry":          ("Harbour line", 185.0, -680.0, "large", 90.0, "small_lot",
                              "a LARGE station (more tracks side by side; a platform fits the 4-car train): one stop "
                              "for the industry and light-industry areas"),
        "Harbour":           ("Harbour line", 185.0, -1062.0, "large", 90.0, "park_and_ride",
                              "ONE combined station at the container terminal's north gate: the passenger island "
                              "platform, the E&S freight tracks beside it and the container handling apron"),
    },
    "yard": (232.0, -1117.0),
    "freight_gate": True,
    # the compressed world puts these pairs under Tokyo's ~500 m: accepted by the user on the 2026-09-25 review
    # ("5 short gaps (accepted)"), written down here so the check reports them as accepted, not as clean or silent
    "accept_gaps": [("Bay", "Waterpark"), ("Waterpark", "Suburb"), ("City West", "Castle Town"),
                    ("Residential", "Light Industry"), ("Bay", "Industry"), ("Industry", "Harbour")],
    "title": "Tokyo hub, straight Harbour",
    "notes": ["The Harbour line runs straight down the street-free",
              "strip under the Wangan to the container terminal's",
              "gate: passengers end at Harbour, freight runs on",
              "to the terminal gate (JR Freight shares the tracks).",
              "Harbour is ONE station at the terminal's north gate:",
              "passenger platforms + E&S freight tracks + the",
              "handling apron; trucks carry boxes into the stack.",
              "Stations: Bay > Industry > Harbour.",
              "The Blue line runs on past Residential to",
              "Light Industry: the 準工業 district has two stations."],
}


ACCEPT_GAPS = set()      # (a, b) station pairs closer than STATION_MIN_GAP that the layout accepts, written down


# THE r0 ROUTE FIXES -- ADOPTED by the user 2026-09-26 (fifty-fifth session): `tokyo_straight` IS this layout now. The
# layout as it was first drawn stays available as `--layout tokyo_straight_pre_r0` (the control: the check reports the
# three defects on it). The three route defects the check found on today's island, fixed, and nothing else moved:
#   1. BLUE LINE: its curve from the westbound leg into the southbound one swept diagonally across chuo_dori right at
#      its cho_192 junction (and ran ON chuo_dori for ~30 m). It now turns south INSIDE the core, on the viaduct, at
#      x 100 (City West becomes an ELEVATED station at (100, 180), 680 m from Central), comes down to grade before C1's
#      south-west corner (passed under at grade, as every line passes C1), and runs west along y -160 on a straight --
#      every arterial it meets is crossed on the straight.
#   2. MAIN LINE: its curve from southbound to eastbound ran along wangan_dori and across its nishi_hondori__s junction.
#      It now turns east NORTH of wangan_dori (a 100 m station-throat curve out of Bay's south end), along y -400, so
#      nishi_hondori__s is crossed square; Waterpark and Suburb move with the leg.
#   3. CASTLE: the Blue line's west corner moves to x -800, so nishi_dori is crossed on the straight; Residential and
#      Light Industry move with the leg. City West moves onto the westbound leg at grade (-100, -160) and Castle Town
#      to (-560, -160), right below the castle: the castle approach (`island_site_access` jokamachi_sando) ends at the
#      station's SOUTH forecourt with its car park, and the castle is a walk up from the north exit -- the rail never
#      crosses the approach (a Japanese 城下町 station).
import copy as _copy
_TS = LAYOUTS["tokyo_straight"]
_R0 = _copy.deepcopy(_TS)
_R0["lines"]["Main line"] = dict(_TS["lines"]["Main line"],
    # both TERMINI end ~20 m past their platforms (a buffer stop, user 2026-09-26: "if rail does end, ensure it is
    # ending in a station properly"): Farm's platform ends at y 1365, Airport's at y -1895 -- the line used to run on
    # 35 m and 65 m into open ground
    corners=[(1110.0, 1385.0), (1110.0, 215.0), (205.0, 215.0), (205.0, -400.0), (1250.0, -400.0),
             (1250.0, -1480.0), (1300.0, -1700.0), (1300.0, -1915.0)],
    radii={1: 180.0, 3: R_THROAT}, throat=[3],
    form=[(1110.0, 1385.0, "grade"), (1110.0, 300.0, "elev"), (205.0, 140.0, "grade"),
          (835.0, -400.0, "elev"), (1250.0, -697.0, "bridge"), (1300.0, -1700.0, "elev")])
_R0["lines"]["Blue line"] = dict(_TS["lines"]["Blue line"],
    corners=[(782.0, 225.0), (100.0, 225.0), (100.0, -160.0), (-800.0, -160.0), (-800.0, -990.0)],
    radii={1: R_MIN, 2: R_MIN, 3: R_MIN},
    form=[(782.0, 225.0, "elev"), (100.0, 120.0, "grade")])
# CENTRAL'S THREE LINES 14 m APART (2026-09-26): at 10 m the platform between two lines had to be ONE shared island
# (3 m), which the Road Kit builds as two overlapping footways whose fences end diagonally across the neighbour's
# track at the platform ends (probe_rail_track's gauge). 14 m = 2 x (2.0 track offset + 1.55 edge + 3.0 platform)
# + the fences: every line keeps its own side platforms and nothing crosses a neighbour's gauge.
_R0["lines"]["Blue line"]["corners"] = [(782.0, 229.0), (100.0, 229.0)] + _R0["lines"]["Blue line"]["corners"][2:]
_R0["lines"]["Blue line"]["form"] = [(782.0, 229.0, "elev")] + _R0["lines"]["Blue line"]["form"][1:]
_R0["lines"]["Harbour line"] = dict(_TS["lines"]["Harbour line"],
    corners=[(782.0, 201.0), (185.0, 201.0), (185.0, -1110.0)],
    form=[(782.0, 201.0, "elev")] + _TS["lines"]["Harbour line"]["form"][1:])
_R0["stations"] = dict(_TS["stations"])
_R0["stations"]["City West"] = ("Blue line", -100.0, -160.0, "standard", 90.0, "small_lot",
                                "at grade on the westbound leg, between chuo_dori and nishi_dori")
_R0["stations"]["Castle Town"] = ("Blue line", -560.0, -160.0, "standard", 90.0, "park_and_ride",
                                  "right below the castle: its approach (jokamachi_sando) ends at the station's south "
                                  "forecourt, and the castle is a walk up from the north exit")
_R0["stations"]["Waterpark"] = ("Main line", 470.0, -400.0) + tuple(_TS["stations"]["Waterpark"][3:])
_R0["stations"]["Suburb"] = ("Main line", 880.0, -400.0) + tuple(_TS["stations"]["Suburb"][3:])
_R0["stations"]["Residential"] = ("Blue line", -800.0, -520.0) + tuple(_TS["stations"]["Residential"][3:])
_R0["stations"]["Light Industry"] = ("Blue line", -800.0, -960.0) + tuple(_TS["stations"]["Light Industry"][3:])
# NO 踏切 THROUGH A PLATFORM (probe_rail_track, 2026-09-26): City West's platform was cut by chuo_dori's level crossing
# 36 m from its centre and Bay's by rinkai_dori's 16 m from its centre -- the road owns a crossing's ground, so the
# platform was simply missing there. Each slides along its own line until the crossing is ~10 m past its platform
# end, which is where a Japanese station keeps its 踏切.
_R0["stations"]["City West"] = ("Blue line", -125.0, -160.0) + tuple(_R0["stations"]["City West"][3:])
# Bay fits between the foot of the ramp down from the core viaduct (y -85) and rinkai_dori's crossing (y -205):
# 110 m, so its platform is 100 m (Industry's and Harbour's are 90)
_bay = _R0["stations"]["Bay"]
_R0["stations"]["Bay"] = ("Main line", 205.0, -140.0, _bay[3], 100.0) + tuple(_bay[5:])
_R0["title"] = "Tokyo hub, straight Harbour (r0 route fixes)"
LAYOUTS["tokyo_straight_pre_r0"] = _TS
LAYOUTS["tokyo_straight"] = _R0
LAYOUTS["tokyo_straight_r0"] = _R0      # the name the review picture was drawn under


def use_layout(name):
    """Swap in a named alternative layout (module-level data, so every check and picture sees it)."""
    global LINES, STATIONS, FREIGHT_YARD, RESERVE, TITLE, NOTES, UNDERPASS_OK, FREIGHT_GATE, LEVEL_OK, ACCEPT_GAPS
    lay = LAYOUTS[name]
    if lay is None:
        return
    LINES, STATIONS, FREIGHT_YARD, RESERVE = lay["lines"], lay["stations"], lay["yard"], lay.get("reserve")
    FREIGHT_GATE = lay.get("freight_gate", False)
    TITLE, NOTES = lay.get("title", name), lay.get("notes", [])
    UNDERPASS_OK = lay.get("underpass", False)
    LEVEL_OK = lay.get("crossing") == "level"
    ACCEPT_GAPS = {tuple(g) for g in lay.get("accept_gaps", ())}


RESERVE = None
FREIGHT_GATE = False     # the layout ends freight at the terminal gate (E&S at the station), not inside it
UNDERPASS_OK = False     # a layout may let the rail cross an arterial at grade, the road passing under it
LEVEL_OK = False         # a layout may cross ARTERIALS at grade too (踏切): the rail comes to the road's height
LEVEL_EASE = 4.0         # m: an at-grade line this far off a road's height is eased onto it for a 踏切
TITLE = "draft v2: Central at the Tokyo Station site"
NOTES = ["Central (the old Tokyo Station site) is the hub.", "The West line runs as one line to Harbour."]

# station width across the tracks (two tracks + platforms), and the parking footprint 3.24(f) reserves beside it
# (along x across, m): park-and-ride 16-30 bays, a small lot 8-16 bays + a 駐輪場, a hub a 立体駐車場 on a
# neighbouring plot (drawn as its footprint).
STATION_W = {"hub": 70.0, "large": 40.0, "junction": 30.0, "standard": 20.0, "small": 16.0}
STATION_BUILDING = (12.74, 7.28)     # the StationBuilding type's footprint (along the track, across it)
STATION_YARD = 3.8                   # the paid yard between a platform's outer edge and its building's back wall
PARKING = {"park_and_ride": (70.0, 35.0), "small_lot": (40.0, 25.0), "multistorey": (40.0, 30.0), "none": (0, 0)}

# ------------------------------------------------------------------------------------------ geometry


def seg_x(p, q, a, b):
    """Intersection of segments pq and ab: (t on pq, u on ab) or None."""
    r = (q[0] - p[0], q[1] - p[1])
    s = (b[0] - a[0], b[1] - a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((a[0] - p[0]) * s[1] - (a[1] - p[1]) * s[0]) / den
    u = ((a[0] - p[0]) * r[1] - (a[1] - p[1]) * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return t, u
    return None


def along_tracks(a, b, w, h):
    """A street segment running ALONG the hub's tracks (the reserve's long axis): it cannot stay. One crossing them
    passes under the elevated station (kōka-shita), as streets do under Tokyo's elevated lines."""
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return dy > dx if h > w else dx > dy


def seg_box(a, b, cx, cy, w, h):
    """Does segment ab cross the axis-aligned box (centre cx, cy; size w x h)?"""
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        if seg_x(a, b, p, q):
            return True
    return False


def removed_streets():
    """The block streets under the hub's reserve (RESERVE), by name: what the layout removes."""
    if not RESERVE:
        return []
    cx, cy, w, h = RESERVE
    out = set()
    for name, kind, ps in load_roads()[0]:
        if kind == "street":
            for a, b in zip(ps, ps[1:]):
                if along_tracks(a, b, w, h) and ((abs(a[0] - cx) <= w / 2 and abs(a[1] - cy) <= h / 2)
                                                 or seg_box(a, b, cx, cy, w, h)):
                    out.add(name)
    return sorted(out)


def fillets(corners, radius, closed=False):
    """The radius each interior corner ACTUALLY gets (rounded_polygon shrinks one to fit its spans)."""
    out = []
    n = len(corners)
    for i in (range(n) if closed else range(1, n - 1)):
        p0, p1, p2 = corners[(i - 1) % n], corners[i], corners[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        ang = math.acos(max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (la * lb))))
        if ang > math.pi - 1e-3:
            out.append((corners[i], None, 0.0))
            continue
        rad = radius[i] if isinstance(radius, list) else radius
        t = min(rad / math.tan(ang / 2.0), 0.45 * la, 0.45 * lb)
        out.append((corners[i], t * math.tan(ang / 2.0), math.degrees(math.pi - ang)))
    return out


def radii(line):
    return [line.get("radii", {}).get(i, line["radius"]) for i in range(len(line["corners"]))]


def polyline(line):
    if line.get("closed"):
        ring = rg.rounded_polygon(line["corners"], radii(line), closed=True)
        return [tuple(q[:2]) for q in rg.densify(ring + [ring[0]], 5.0)]
    return [tuple(q[:2]) for q in rg.densify(rg.rounded_polygon(line["corners"], radii(line), closed=False), 5.0)]


def cumulative(pts):
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    return cum


def project(pts, cum, x, y):
    """Arc length of the nearest point on the polyline to (x, y), and the distance."""
    best = (1e18, 0.0)
    for i in range(len(pts) - 1):
        p, q = pts[i], pts[i + 1]
        dx, dy = q[0] - p[0], q[1] - p[1]
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((x - p[0]) * dx + (y - p[1]) * dy) / L2))
        cx, cy = p[0] + dx * t, p[1] + dy * t
        d = math.hypot(x - cx, y - cy)
        if d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best[1], best[0]


def form_at(line, pts, cum):
    """The form at every point: each (x, y, form) breakpoint, projected on the line, holds until the next."""
    br = sorted((project(pts, cum, x, y)[0], f) for x, y, f in line["form"])
    out = []
    for s in cum:
        f = br[0][1]
        for s0, ff in br:
            if s + 1e-6 >= s0:
                f = ff
        out.append(f)
    return out


def profile(line, pts, cum, ground, level=()):
    """Rail head height (record z) per point. Each span's form gives a FLOOR (the bridge deck, ELEVATED_Z over the
    ground, or the ground); the profile is the highest of every floor's GRADE_MAX cone, so a ramp always lies on the
    LOWER form's side and an elevated section, a station on it and the bridge deck stay level. Returns (z, ground,
    ramps) with each ramp as (s0, s1, dz, lower form, upper form)."""
    fa = form_at(line, pts, cum)
    g = [max(0.0, ground.z(p[0], p[1]) or 0.0) for p in pts]
    # a viaduct does not follow every bump in the ground under it: its floor is the highest ground within VIADUCT_WIN
    gmax = []
    for i in range(len(pts)):
        lo, hi = i, i
        while lo > 0 and cum[i] - cum[lo - 1] <= VIADUCT_WIN:
            lo -= 1
        while hi < len(pts) - 1 and cum[hi + 1] - cum[i] <= VIADUCT_WIN:
            hi += 1
        gmax.append(max(g[lo:hi + 1]))
    base = []
    for i in range(len(pts)):
        f = fa[i]
        if f == "bridge" and BRIDGE_Y[1] <= pts[i][1] <= BRIDGE_Y[0]:
            base.append(BRIDGE_DECK_Z)
        elif f in ("elev", "bridge"):
            base.append(gmax[i] + ELEVATED_Z)
        elif f == "cut":
            base.append(-1e9)                   # takes no part in the floors: the cut is a CEILING below
        else:
            base.append(g[i] + 0.3)
    # a station's platform is LEVEL: over each (s0, s1) the deck stands at its highest floor there
    for s0, s1 in level:
        idx = [i for i in range(len(pts)) if s0 <= cum[i] <= s1]
        if idx:
            top = max(base[i] for i in idx)
            for i in idx:
                base[i] = top
    z = list(base)
    # the cone, both ways: z[i] >= z[j] - GRADE_MAX * |s_i - s_j|
    for i in range(1, len(z)):
        z[i] = max(z[i], z[i - 1] - GRADE_MAX * (cum[i] - cum[i - 1]))
    for i in range(len(z) - 2, -1, -1):
        z[i] = max(z[i], z[i + 1] - GRADE_MAX * (cum[i + 1] - cum[i]))
    # a cutting is a CEILING: the rail is at the cut depth there and climbs out at GRADE_MAX either side
    cut = [i for i in range(len(z)) if fa[i] == "cut"]
    for c in cut:
        zc = g[c] + CUT_Z
        base[c] = zc
        for i in range(len(z)):
            z[i] = min(z[i], zc + GRADE_MAX * abs(cum[i] - cum[c]))
    ramps = []
    i = 0
    while i < len(z):
        if abs(z[i] - base[i]) > 0.2:
            j = i
            while j + 1 < len(z) and abs(z[j + 1] - base[j + 1]) > 0.2:
                j += 1
            ramps.append((cum[i], cum[j], z[j] - z[i], fa[i], fa[j]))
            i = j + 1
        else:
            i += 1
    return z, g, ramps


def load_roads():
    d = json.load(open(RECORD))
    P = {p["uid"]: p for p in d["points"]}
    pads = []
    for p in d["points"]:
        for ln in p.get("links", []):
            if ln.get("type") == "JUNCTION":
                pads.append(p["pos"][:2])
                break
    roads = []
    for r in d["roads"]:
        name = r["name"]
        ps = [P[u]["pos"] for u in r["points"] if u in P]
        if len(ps) < 2:
            continue
        if name.startswith("shuto_"):
            kind = "expressway"
        elif r.get("road_class") == "arterial":
            kind = "arterial"
        else:
            kind = "street"
        roads.append((name, kind, ps))
    return roads, pads


def crossings(pts, cum, z, roads, pads):
    out = []
    for name, kind, ps in roads:
        for j in range(len(ps) - 1):
            a, b = ps[j], ps[j + 1]
            for i in range(len(pts) - 1):
                hit = seg_x(pts[i], pts[i + 1], a, b)
                if not hit:
                    continue
                t, u = hit
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
                rz = z[i] + (z[i + 1] - z[i]) * t
                road_z = a[2] + (b[2] - a[2]) * u
                r = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                s = (b[0] - a[0], b[1] - a[1])
                ang = math.degrees(math.acos(min(1.0, abs(r[0] * s[0] + r[1] * s[1]) /
                                                 (math.hypot(*r) * math.hypot(*s) or 1e-9))))
                jd = min((math.hypot(x - q[0], y - q[1]) for q in pads), default=1e9)
                dz = rz - road_z
                action = ""
                if dz > LEVEL_DZ:
                    form, ok = "rail over road", dz - DECK_T >= CLEAR_ROAD_UNDER
                    why = "" if ok else "only %.1f m under the rail deck" % (dz - DECK_T)
                    if not ok and kind == "arterial" and LEVEL_OK and dz <= LEVEL_EASE and ang >= LX_MIN_ANGLE:
                        # an at-grade line on ground a little higher than the road: it comes down onto the road
                        # for the crossing (the platform-free stretch either side takes the grade)
                        ok, form, why = True, "level crossing", ""
                        action = "踏切 on %s (rail eased %.1f m onto the road)" % (name, dz)
                    if not ok and kind == "arterial" and UNDERPASS_OK:
                        # an at-grade line on ground a little higher than the road: the road still dips under it,
                        # just deeper -- the same underpass, not a rail bridge
                        ok, form, action = True, "road underpass", "lower %s under the rail (underpass)" % name
                    if not ok and kind == "street":
                        # a block street under a ramp ends at the corridor (Japanese streets do; the other
                        # side is reached at the next crossing): an ACTION on the record, not a conflict
                        ok, form, action = True, "street closed", "close %s at the corridor" % name
                elif dz < -LEVEL_DZ:
                    form, ok = "road over rail", (-dz) - DECK_T >= CLEAR_RAIL_UNDER
                    need = rz + DECK_T + CLEAR_RAIL_UNDER
                    why = "" if ok else "only %.1f m over the catenary" % ((-dz) - DECK_T)
                    if not ok and kind == "street":
                        ok, form, action = True, "street closed", "close %s at the corridor" % name
                    if not ok and name.split("__")[0] in DIKE_ROADS:
                        # the ring road is the dike: it bridges the track (`island_dike.rail_lifts`), with a gap in
                        # the embankment under the span
                        ok, action = True, "the dike road %s bridges the rail here (crest to %.1f m)" % (name, need)
                    if not ok and kind == "expressway":
                        # the Shuto-over-JR pattern: the expressway deck rises over the rail viaduct
                        ok, action = True, "raise %s to %.1f m here (from %.1f)" % (name, need, road_z)
                else:
                    form = "level crossing"
                    ok, why, action = True, "", ""
                    if kind == "arterial" and UNDERPASS_OK:
                        # the road dips under the line (a Japanese underpass): an ACTION on the road record
                        ok, form, action = True, "road underpass", "lower %s under the rail (underpass)" % name
                    elif kind == "arterial" and LEVEL_OK:
                        # the user chose 踏切 over any road change (2026-09-25): an oblique one or one near a junction
                        # is a NOTE for the rail build (gates, signal pre-emption), never a blocker here
                        notes = ([] if ang >= LX_MIN_ANGLE else ["%.0f deg oblique" % ang]) + \
                                ([] if jd >= LX_JUNCTION_CLEAR else ["%.0f m from a junction" % jd])
                        action = "踏切 on %s%s" % (name, (" -- NOTE " + ", ".join(notes)) if notes else "")
                    elif kind != "street" and not (kind == "arterial" and LEVEL_OK):
                        ok, why = False, "a %s is never crossed at grade" % kind
                    elif ang < LX_MIN_ANGLE and UNDERPASS_OK:
                        # an at-grade line turning through the grid cuts a block diagonally: the street stub ends at
                        # the railway and the block merges with its neighbour (Japanese streets end at lines)
                        ok, form, action = True, "street closed", "close %s at the corridor (crossed at %.0f deg)" % (
                            name, ang)
                    elif (ang < LX_MIN_ANGLE or jd < LX_JUNCTION_CLEAR) and name in ACCESS_ROADS:
                        # a site's own access road (island_site_access) is never closed: its crossing is a
                        # finding the route must answer
                        ok, why = False, ("%.0f deg, too oblique" % ang) if ang < LX_MIN_ANGLE else \
                            ("%.0f m from a junction" % jd)
                    elif ang < LX_MIN_ANGLE or jd < LX_JUNCTION_CLEAR:
                        # a generated block street ends at the corridor instead (Japanese streets end at lines; a
                        # crossing near a junction backs its queue into the junction): the RESERVE marks the spot
                        # 'no', so the street planner closes it by rule, never by name
                        ok, form = True, "street closed"
                        action = "close %s at the corridor (%s)" % (
                            name, ("%.0f deg" % ang) if ang < LX_MIN_ANGLE else ("%.0f m from a junction" % jd))
                out.append({"road": name, "kind": kind, "s": cum[i] + t * math.hypot(*r), "x": x, "y": y,
                            "rail_z": rz, "road_z": road_z, "angle": ang, "junction_m": jd, "form": form,
                            "ok": ok, "why": why, "action": action})
    out.sort(key=lambda c: c["s"])
    return out


def alongside(pts, z, roads, xings):
    """Where the corridor runs BESIDE or ALONG a road (not across it): the vertical separation must clear either way,
    or the two occupy the same space. Crossings are measured by `crossings`, so a road within 25 m of one is skipped
    at that spot. Returns [(road, kind, x, y, rail_z, road_z, verdict)] -- the worst per road."""
    worst = {}
    for i in range(0, len(pts), 2):
        x, y = pts[i]
        # a crossing puts the road inside the corridor band for (road half + track half) / sin(angle) either side of
        # it: that stretch is the crossing, measured by `crossings`, not a road running alongside
        if any(math.hypot(c["x"] - x, c["y"] - y) <
               (ROAD_HALF[c["kind"]] + TRACK_HALF) / max(0.2, math.sin(math.radians(c["angle"]))) + 5.0
               for c in xings):
            continue
        for name, kind, ps in roads:
            for a, b in zip(ps, ps[1:]):
                if max(a[0], b[0]) < x - 40 or min(a[0], b[0]) > x + 40 or \
                        max(a[1], b[1]) < y - 40 or min(a[1], b[1]) > y + 40:
                    continue
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy or 1e-9
                t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
                d = math.hypot(x - a[0] - dx * t, y - a[1] - dy * t)
                if d >= ROAD_HALF[kind] + TRACK_HALF:
                    continue
                rz = a[2] + (b[2] - a[2]) * t
                dz = z[i] - rz
                if dz > 0:
                    ok = dz - DECK_T >= CLEAR_ROAD_UNDER
                    verdict = "rail over it, %.1f m clear" % (dz - DECK_T)
                else:
                    ok = -dz - DECK_T >= CLEAR_RAIL_UNDER
                    verdict = "under it, %.1f m clear" % (-dz - DECK_T)
                if abs(dz) < LEVEL_DZ:
                    ok, verdict = False, "ON it (same level, %.0f m apart)" % d
                key = name
                margin = (dz - DECK_T - CLEAR_ROAD_UNDER) if dz > 0 else (-dz - DECK_T - CLEAR_RAIL_UNDER)
                if key not in worst or margin < worst[key][-1]:
                    worst[key] = (name, kind, x, y, z[i], rz, verdict, ok, margin)
    return sorted(worst.values(), key=lambda w: w[-1])


def sites_hit(pts):
    d = json.load(open(SITES))
    hits = []
    for s in d["sites"]:
        if s["id"] == "tokyo_station":
            continue                    # Central's own reserve
        yaw = math.radians(s.get("yaw", 0.0))
        c, sn = math.cos(yaw), math.sin(yaw)
        hx, hy = s["size"][0] / 2 + CORRIDOR_HALF, s["size"][1] / 2 + CORRIDOR_HALF
        for p in pts:
            dx, dy = p[0] - s["x"], p[1] - s["y"]
            lx, ly = dx * c + dy * sn, -dx * sn + dy * c
            if abs(lx) < hx and abs(ly) < hy:
                hits.append(s["id"])
                break
    return hits


def buildings_hit(pts):
    """Placed buildings whose centre is within the corridor (+ a nominal 8 m half-footprint): what the derive will
    move off the reserved corridor."""
    b = json.load(open(BUILDINGS))["buildings"]
    n = 0
    for e in b:
        gx, _, gz = e["pos"]
        x, y = gx, -gz
        for i in range(0, len(pts), 2):
            if abs(pts[i][0] - x) < 30 and abs(pts[i][1] - y) < 30:
                if math.hypot(pts[i][0] - x, pts[i][1] - y) < CORRIDOR_HALF + 8.0:
                    n += 1
                    break
    return n


# ------------------------------------------------------------------------------------------ report + picture


def analyse():
    # WITHOUT the ring-road dike's crest: the rail never climbs the dike -- the ring bridges the track (the 臨港線
    # pattern: a harbour line runs at grade under the coastal road), `island_dike.rail_lifts` raising its crest
    ground = rg.Ground(dike=False)
    roads, pads = load_roads()
    res = {"lines": {}, "stations": {}}
    for name, line in LINES.items():
        pts = polyline(line)
        cum = cumulative(pts)
        level = []
        for sname, (lname, x, y, kind, plen, park, note) in STATIONS.items():
            s_, d_ = project(pts, cum, x, y)
            if d_ < SHARE_M:
                level.append((s_ - plen / 2 - 5.0, s_ + plen / 2 + 5.0))
        z, g, ramps = profile(line, pts, cum, ground, level)
        fil = fillets(line["corners"], radii(line), line.get("closed", False))
        def zg(p):
            v = ground.z(p[0], p[1])
            return -99.0 if v is None else v      # NOT `or`: the city plain is exactly 0.0, which is land
        wet = [i for i, p in enumerate(pts) if zg(p) < -0.25]
        fa = form_at(line, pts, cum)
        wet_grade = [i for i in wet if fa[i] == "grade"]
        res["lines"][name] = {
            "length_m": cum[-1], "pts": pts, "z": z, "ground": g, "ramps": ramps, "fillets": fil,
            "wet_grade_m": len(wet_grade) * (cum[-1] / max(1, len(pts) - 1)),
            "crossings": crossings(pts, cum, z, roads, pads),
            "sites": [x for x in sites_hit(pts) if x != line.get("into_site")],
            "along": None,
            "buildings": buildings_hit(pts), "cum": cum,
        }
        res["lines"][name]["along"] = alongside(pts, z, roads, res["lines"][name]["crossings"])
    # a street crossed at grade by two or more lines side by side (the approach to a hub) is CLOSED at the corridor:
    # a many-track level crossing is down almost all day (the 開かずの踏切); the next underpass serves it
    lxs = [(ln, c) for ln, L in res["lines"].items() for c in L["crossings"] if c["form"] == "level crossing"]
    for ln, c in lxs:
        others = {ln2 for ln2, c2 in lxs if c2["road"] == c["road"] and math.hypot(c2["x"] - c["x"], c2["y"] - c["y"]) < 40.0}
        if len(others) >= 2 and c["kind"] == "street":
            c["form"], c["action"] = "street closed", "close %s at the corridor (%d lines cross it)" % (c["road"], len(others))
        elif len(others) >= 2:
            # an ARTERIAL is never closed: it takes one wide, multi-track 踏切 (the rail geometry's business)
            c["action"] = "wide 踏切 on %s (%d lines side by side)" % (c["road"], len(others))
    for sname, (lname, x, y, kind, plen, park, note) in STATIONS.items():
        L = res["lines"][lname]
        s, d = project(L["pts"], L["cum"], x, y)
        i = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - s))
        # the platform's own grade: it must be level (< 0.5%) over its length
        a = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (s - plen / 2)))
        b = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (s + plen / 2)))
        pg = abs(L["z"][b] - L["z"][a]) / max(1.0, L["cum"][b] - L["cum"][a])
        res["stations"][sname] = {"line": lname, "s": s, "off_line_m": d, "z": L["z"][i], "kind": kind,
                                  "platform_m": plen, "platform_grade": pg, "parking": park, "note": note,
                                  "x": x, "y": y}
    return res


def report_gaps(res):
    """(a, b, gap m) for consecutive stations along every line a station stands on."""
    by_line = {}
    for n, st in res["stations"].items():
        for ln, L in res["lines"].items():
            s_, d_ = project(L["pts"], L["cum"], st["x"], st["y"])
            if d_ < SHARE_M:
                by_line.setdefault(ln, []).append((s_, n))
    out = []
    for ln, lst in by_line.items():
        lst.sort()
        for (s0, a), (s1, b) in zip(lst, lst[1:]):
            out.append((a, b, s1 - s0))
    return out


def report(res):
    bad = 0
    for name, L in res["lines"].items():
        print("== %s: %.0f m" % (name, L["length_m"]))
        throat = {LINES[name]["corners"][i] for i in LINES[name].get("throat", [])}
        for c, r, turn in L["fillets"]:
            lim = R_THROAT if tuple(c) in throat else R_MIN
            if r is not None and r < R_MIN - 1e-6 and r >= lim:
                print("   throat  corner (%.0f, %.0f): %.0f m (a station throat, >= %.0f)" % (c[0], c[1], r, lim))
            elif r is not None and r < lim - 1e-6:
                bad += 1
                print("   RADIUS  corner (%.0f, %.0f): %.0f m < %.0f (turn %.0f deg)" % (c[0], c[1], r, R_MIN, turn))
        for s0, s1, dz, fa, fb in L["ramps"]:
            print("   ramp over %-6s .. %-6s %+5.1f m over %.0f m at s %.0f..%.0f" % (fa, fb, dz, s1 - s0, s0, s1))
        if L["wet_grade_m"] > 1:
            bad += 1
            print("   WATER   %.0f m of at-grade track is not on land" % L["wet_grade_m"])
        if L["sites"]:
            bad += 1
            print("   SITES   the corridor crosses %s" % ", ".join(L["sites"]))
        print("   buildings the corridor displaces: %d" % L["buildings"])
        kinds = {}
        for c in L["crossings"]:
            kinds[c["form"]] = kinds.get(c["form"], 0) + 1
            if not c["ok"]:
                bad += 1
                print("   CONFLICT %-26s %-10s at (%.0f, %.0f): %s, rail %.1f road %.1f -- %s" %
                      (c["road"], c["kind"], c["x"], c["y"], c["form"], c["rail_z"], c["road_z"], c["why"]))
        print("   crossings: %s" % ", ".join("%d %s" % (v, k) for k, v in sorted(kinds.items())))
        for c in L["crossings"]:
            if c["action"]:
                print("   ACTION   %s" % c["action"])
        for name_, kind, x, y, rz, roz, verdict, ok, margin in L["along"]:
            if not ok:
                bad += 1
                print("   ALONGSIDE %-24s %-10s at (%.0f, %.0f): %s" % (name_, kind, x, y, verdict))
    print("== stations")
    by_line = {}
    for n, st in res["stations"].items():
        for ln, L in res["lines"].items():          # every line a station stands on (Central is on two)
            s_, d_ = project(L["pts"], L["cum"], st["x"], st["y"])
            if d_ < SHARE_M:
                by_line.setdefault(ln, []).append((s_, n))
        flag = ""
        if st["off_line_m"] > 5:
            flag += " OFF-LINE %.0f m" % st["off_line_m"]
        if st["platform_grade"] > 0.005:
            flag += " PLATFORM GRADE %.1f%%" % (st["platform_grade"] * 100)
        # a 踏切 THROUGH a platform: the road owns the crossing's ground, so the platform is missing there (City West
        # and Bay had one, 2026-09-26). A crossing belongs at least LX_PLATFORM_CLEAR past the platform's end.
        for ln, L in res["lines"].items():
            s_, d_ = project(L["pts"], L["cum"], st["x"], st["y"])
            if d_ >= SHARE_M:
                continue
            for c in L["crossings"]:
                if c["form"] == "level crossing" and abs(c["s"] - s_) < st["platform_m"] / 2.0 + LX_PLATFORM_CLEAR:
                    flag += " 踏切 IN PLATFORM (%s on the %s, %.0f m from its centre)" % (c["road"], ln, c["s"] - s_)
        if flag:
            bad += 1
        print("   %-18s %-9s z %5.1f  platform %3.0f m  parking %-13s%s" %
              (n, st["kind"], st["z"], st["platform_m"], st["parking"], flag))
    for ln, lst in by_line.items():
        lst.sort()
        for (s0, a), (s1, b) in zip(lst, lst[1:]):
            gap = s1 - s0
            acc = gap < STATION_MIN_GAP and (a, b) in ACCEPT_GAPS
            print("   %-18s -> %-18s %5.0f m%s" % (a, b, gap, "  CLOSE (accepted)" if acc else
                                                    ("  CLOSE" if gap < STATION_MIN_GAP else "")))
            if gap < STATION_MIN_GAP and not acc:
                bad += 1
    print("RESULT: %d finding(s)" % bad)
    return bad


def picture(res, out, legend=True):
    import island_plan_picture as ipp
    from PIL import Image, ImageDraw
    tmp = out + ".base.png"
    ipp.main(["--out", tmp, "--title", "RAIL LAYOUT (draft for review) -- tools/island_rail_layout.py"]
             + ([] if legend else ["--no-legend"]))
    img = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    d = ImageDraw.Draw(img, "RGBA")
    f = ipp.font(15, True)
    fs = ipp.font(12)
    if RESERVE:
        cx, cy, w, h = RESERVE
        d.rectangle([ipp.P(cx - w / 2, cy + h / 2), ipp.P(cx + w / 2, cy - h / 2)],
                    outline=(255, 255, 255, 255), fill=(255, 255, 255, 50), width=3)
        for name_, kind, ps in load_roads()[0]:
            if kind != "street":
                continue
            for a_, b_ in zip(ps, ps[1:]):
                inside = lambda q: abs(q[0] - cx) <= w / 2 and abs(q[1] - cy) <= h / 2
                if along_tracks(a_, b_, w, h) and (inside(a_) or inside(b_) or seg_box(a_, b_, cx, cy, w, h)):
                    d.line([ipp.P(a_[0], a_[1]), ipp.P(b_[0], b_[1])], fill=(140, 255, 140, 255), width=9)
    for name, L in res["lines"].items():
        line = LINES[name]
        col = line["colour"]
        fa = form_at(line, L["pts"], L["cum"])
        for i in range(len(L["pts"]) - 1):
            form = fa[i]
            w = {"elev": 9, "grade": 5, "bridge": 9, "cut": 3}[form]
            p, q = ipp.P(*L["pts"][i]), ipp.P(*L["pts"][i + 1])
            d.line([p, q], fill=col + (255,), width=w)
            if form == "elev" and i % 6 == 0:
                d.line([p, q], fill=(255, 255, 255, 255), width=2)
        for c in L["crossings"]:
            x, y = ipp.P(c["x"], c["y"])
            if c["form"] == "street closed":
                d.ellipse([x - 11, y - 11, x + 11, y + 11], fill=(140, 255, 140, 255), outline=(0, 0, 0, 255), width=2)
            if not c["ok"]:
                d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(255, 0, 0, 255), width=4)
            elif c["form"] == "level crossing":
                d.rectangle([x - 5, y - 5, x + 5, y + 5], fill=(255, 220, 0, 255), outline=(0, 0, 0, 255))
    for n, st in res["stations"].items():
        L = res["lines"][st["line"]]
        # the platform band (the corridor at the station, platform length x the station width), drawn along the line
        i0 = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (st["s"] - st["platform_m"] / 2)))
        i1 = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (st["s"] + st["platform_m"] / 2)))
        seg = [ipp.P(*L["pts"][k]) for k in range(i0, i1 + 1)]
        if len(seg) > 1:
            d.line(seg, fill=(255, 255, 255, 200), width=int(STATION_W[st["kind"]] * ipp.S))
        (px_, py_), (qx_, qy_) = L["pts"][i0], L["pts"][i1]
        ux, uy = qx_ - px_, qy_ - py_
        ul = math.hypot(ux, uy) or 1.0
        nx, ny = -uy / ul, ux / ul
        # THE STATION BUILDING (駅舎, PLAN.md R3): in the 10 m between the platform box and the car park, its back to
        # the platform fence and its front to the car park / street side. A hub's is its own site (Central: the
        # Tokyo Station building), so it gets none here. `island_sites.rail_stations` places it from THIS box.
        if st["kind"] != "hub":
            boxes.append({"id": "building:" + n, "x": round(st["x"] + nx * (hw + 5.0), 2),
                          "y": round(st["y"] + ny * (hw + 5.0), 2), "ux": round(ux, 5), "uy": round(uy, 5),
                          "h_along": STATION_BUILDING[0] / 2 + 0.5, "h_across": STATION_BUILDING[1] / 2 + 0.5,
                          "nx": round(nx, 5), "ny": round(ny, 5)})
        w, h = PARKING[st["parking"]]
        if w:
            off = STATION_W[st["kind"]] / 2 + 10 + h / 2
            cx, cy = st["x"] + nx * off, st["y"] + ny * off
            corners = [(cx + ux / ul * a + nx * b, cy + uy / ul * a + ny * b)
                       for a, b in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon([ipp.P(*c) for c in corners], outline=(90, 200, 255, 255), fill=(90, 200, 255, 90))
        x, y = ipp.P(st["x"], st["y"])
        r = {"hub": 14, "large": 12, "junction": 11, "standard": 8, "small": 7}[st["kind"]]
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
        d.text((x + r + 4, y - 9), n, fill=(255, 255, 255, 255), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
        d.text((x + r + 4, y + 8), "%s, %s" % (st["kind"], st["parking"].replace("_", " ")),
               fill=(230, 230, 230, 255), font=fs, stroke_width=2, stroke_fill=(0, 0, 0))
    x, y = ipp.P(*FREIGHT_YARD)
    d.rectangle([x - 18, y - 8, x + 18, y + 8], outline=(150, 80, 200, 255), width=3)
    d.text((x + 22, y - 8), "E&S apron" if FREIGHT_GATE else "freight yard", fill=(255, 255, 255, 255), font=fs, stroke_width=2, stroke_fill=(0, 0, 0))
    if not legend:
        img.save(out)
        return
    # legend
    lx, ly = 20, img.size[1] - 360
    d.rectangle([lx - 10, ly - 10, lx + 600, ly + 180], fill=(0, 0, 0, 230))
    rows = [("thick = elevated / bridge deck, thin = at grade", None)]
    for name, line in LINES.items():
        rows.append((name, line["colour"]))
    rows += [("white band = station platform footprint; blue box = its parking", (90, 200, 255)),
             ("yellow square = level crossing (fumikiri)", (255, 220, 0)),
             ("red ring = a crossing the rules refuse", (255, 0, 0))]
    for k, (t, c) in enumerate(rows):
        if c:
            d.line([(lx, ly + 10 + k * 22), (lx + 40, ly + 10 + k * 22)], fill=c + (255,), width=6)
        d.text((lx + 50, ly + k * 22), t, fill=(255, 255, 255, 255), font=fs)
    img.save(out)
    print("island_rail_layout: wrote %s" % os.path.relpath(out, ROOT))


def preview(res, out):
    """A REVIEW picture: the rail area only, larger, with each decision the draft asks for marked where it is."""
    import island_plan_picture as ipp
    from PIL import Image, ImageDraw
    full = out + ".full.png"
    picture(res, full, legend=False)
    img = Image.open(full).convert("RGB")
    os.remove(full)
    x0, y1, x1, y0 = -1200.0, 1450.0, 1650.0, -2000.0          # record window
    (px0, py0), (px1, py1) = ipp.P(x0, y1), ipp.P(x1, y0)
    k = 1.6
    crop = img.crop((int(px0), int(py0), int(px1), int(py1)))
    crop = crop.resize((int(crop.size[0] * k), int(crop.size[1] * k)), Image.LANCZOS)
    W = crop.size[0] + 1100
    canvas = Image.new("RGB", (W, crop.size[1]), (18, 22, 30))
    canvas.paste(crop, (0, 0))
    d = ImageDraw.Draw(canvas, "RGBA")

    def P(x, y):
        a, b = ipp.P(x, y)
        return ((a - px0) * k, (b - py0) * k)

    big, mid, small = ipp.font(54, True), ipp.font(38, True), ipp.font(31)
    marks = []
    for L in res["lines"].values():
        for c in L["crossings"]:
            if c["action"].startswith("raise"):
                marks.append(("1", c["x"], c["y"], (255, 150, 0)))
            elif c["action"].startswith("close") and not any(
                    t == "C" and math.hypot(x_ - c["x"], y_ - c["y"]) < 60.0 for t, x_, y_, _c in marks):
                marks.append(("C", c["x"], c["y"], (140, 255, 140)))
    if not FREIGHT_GATE and not any(l.get("into_site") for l in LINES.values()):
        marks.append(("4", FREIGHT_YARD[0], FREIGHT_YARD[1], (255, 120, 120)))
    marks.append(("B", 1250.0, -1122.0, (255, 255, 255)))
    for t, x, y, col in marks:
        a0, b0 = P(x, y)
        a, b = a0 + 40, b0 - 70                     # beside the spot, clear of the station labels
        d.line([(a0, b0), (a, b)], fill=(0, 0, 0, 255), width=5)
        d.line([(a0, b0), (a, b)], fill=col + (255,), width=3)
        d.ellipse([a - 30, b - 30, a + 30, b + 30], fill=col + (235,), outline=(0, 0, 0, 255), width=4)
        d.text((a, b), t, fill=(0, 0, 0, 255), font=mid, anchor="mm")
    tx, ty = crop.size[0] + 40, 40
    km = lambda n: res["lines"][n]["length_m"] / 1000.0
    lines = [(big, "RAIL -- %s" % TITLE, (255, 255, 255)),
             (small, "2026-09-25, measured on the island as built now", (190, 190, 190)),
             (small, "", None)]
    for n in NOTES:
        lines.append((small, n, (230, 230, 230)))
    lines.append((small, "", None))
    for ln, line in LINES.items():
        L = res["lines"][ln]
        forms = sorted({f for _x, _y, f in line["form"]})
        lines.append((mid, "%s  %.1f km%s" % (ln, km(ln), "  (loop)" if line.get("closed") else ""), line["colour"]))
        seq = sorted((project(L["pts"], L["cum"], st["x"], st["y"])[0], n) for n, st in res["stations"].items()
                     if project(L["pts"], L["cum"], st["x"], st["y"])[1] < SHARE_M)
        text = " > ".join(n for _s, n in seq) or "(no station of its own)"
        while text:
            cut = text if len(text) <= 46 else text[:text.rfind(" > ", 0, 46)]
            lines.append((small, "  " + cut, (230, 230, 230)))
            text = text[len(cut):].lstrip(" >")
    if RESERVE:
        lines += [(small, "", None), (mid, "Streets removed (light green)", (140, 255, 140)),
                  (small, "  " + ", ".join(removed_streets()), (140, 255, 140)),
                  (small, "  they run along the hub's tracks; cross streets", (140, 255, 140)),
                  (small, "  pass under the elevated station (koka-shita)", (140, 255, 140))]
    raises = sorted({c["action"].split(" to ")[0].replace("raise ", "") for L in res["lines"].values()
                     for c in L["crossings"] if c["action"].startswith("raise")})
    gaps = [g for g in report_gaps(res) if g[2] < STATION_MIN_GAP]
    lines += [(small, "", None), (mid, "What it costs", (255, 220, 0))]
    if raises:
        lines += [(small, "C1 / expressway rises to 15.5 m over the rail at %d" % len(raises), (255, 170, 60)),
                  (small, "  crossing(s): %s" % ", ".join(raises), (255, 170, 60))]
    else:
        lines.append((small, "C1 and the Wangan pass over the rail as built (no raise)", (255, 170, 60)))
    under = sorted({c["road"] for L in res["lines"].values() for c in L["crossings"] if c["form"] == "road underpass"})
    lx = sum(1 for L in res["lines"].values() for c in L["crossings"] if c["form"] == "level crossing")
    if under:
        lines.append((small, "road underpasses: %d (arterials under the line)" % len(under), (255, 170, 60)))
    noted = sum(1 for L in res["lines"].values() for c in L["crossings"]
                if c["form"] == "level crossing" and "NOTE" in c["action"])
    lines.append((small, "level crossings (fumikiri): %d, %d of them oblique" % (lx, noted), (255, 170, 60)))
    lines.append((small, "  or < 30 m from a junction (a note for the rail build)", (255, 170, 60)))
    closed = sorted({c["road"] for L in res["lines"].values() for c in L["crossings"] if c["form"] == "street closed"})
    if closed:
        lines.append((small, "(C) streets closed at the rail: %d" % len(closed), (140, 255, 140)))
        for k in range(0, len(closed), 2):
            lines.append((small, "  " + ", ".join(closed[k:k + 2]), (140, 255, 140)))
    lines.append((small, "stations under 500 m apart: %d" % len(gaps), (210, 150, 255)))
    for a_, b_, g_ in gaps:
        lines.append((small, "  %s - %s %.0f m" % (a_, b_, g_), (210, 150, 255)))
    lines += [(small, "corridors displace %d placed buildings" %
               sum(L["buildings"] for L in res["lines"].values()), (190, 190, 190)),
              ] + ([(small, "freight ends at Harbour, the terminal's north gate:", (140, 255, 140)),
                    (small, "  E&S tracks + handling apron; trucks into the stack", (140, 255, 140))]
                   if FREIGHT_GATE else
                   [(small, "freight runs into the container terminal; the coast", (140, 255, 140)),
                    (small, "  ring dips under it (one of the underpasses)", (140, 255, 140))]
                   if any(l.get("into_site") for l in LINES.values()) else
                   [(small, "freight into the container terminal: needs the", (255, 120, 120)),
                    (small, "  coast ring lifted over the rail (now or later?)", (255, 120, 120))]) + [
              (small, "", None),
              (small, "thick line = elevated / bridge; white band = platform;", (190, 190, 190)),
              (small, "blue box = parking", (190, 190, 190))]
    for f, t, col in lines:
        if col:
            d.text((tx, ty), t, fill=col + (255,), font=f)
        ty += {big: 72, mid: 54, small: 42}[f] if t else 20
    canvas.save(out)
    print("island_rail_layout: wrote %s" % os.path.relpath(out, ROOT))


def dump(res, out):
    doc = {"schema": 1, "notes": "DRAFT rail layout (PLAN.md 3.25), written by tools/island_rail_layout.py; "
                                 "record frame (x east, y north).",
           "lines": {n: {"corners": LINES[n]["corners"], "radius": LINES[n]["radius"], "form": LINES[n]["form"],
                         "length_m": round(L["length_m"], 1)} for n, L in res["lines"].items()},
           "stations": {n: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in st.items()}
                        for n, st in res["stations"].items()},
           "freight_yard": FREIGHT_YARD}
    json.dump(doc, open(out, "w"), indent=1, ensure_ascii=False)


DIKE_ROADS = ("ring_kita", "kaigan_machi")
try:
    import island_site_access as _isa
    ACCESS_ROADS = {a["name"] for a in getattr(_isa, "ACCESS", ())}
except Exception:                                      # the tool is optional here
    ACCESS_ROADS = set()     # island_dike.DIKE_ROADS (not imported: that module pulls numpy)
LX_PLATFORM_CLEAR = 5.0   # a level crossing stands at least this far past a platform's end
OTHER_TRACK_CLEAR = 7.0   # a station building / car park keeps this far (plan) from another line's track centre
RESERVE_OUT = os.path.join(ROOT, "assets/world_source/buildings/IslandRailReserve.json")
MULTI_M = 25.0           # two at-grade lines closer than this are ONE multi-track band: no street crosses it
RESERVE_STEP = 10.0      # m between corridor samples in the reserve record


def _cross_rule(dz):
    """What a road may do where the rail head stands `dz` over the ground: 'level' (a 踏切), 'under' (pass under the
    viaduct) or 'no' (a ramp too high to cross and too low to pass under)."""
    if dz <= LEVEL_DZ:
        return "level"
    if dz - DECK_T >= CLEAR_ROAD_UNDER:
        return "under"
    return "no"


def reserve(res, out):
    """THE RESERVE RECORD the derive reads (PLAN.md B10), record frame (x east, y north). Every rule is DERIVED from
    the rail's own profile, never a list of street names:
      * `corridors`: each line sampled every RESERVE_STEP with its half width and `cross` -- what a street may do
        there ('level' 踏切, 'under' the viaduct, 'no'). Buildings keep off every sample; a street never RUNS ALONG
        one and never crosses a 'no'. An at-grade sample with another line's at-grade sample within MULTI_M is 'no'
        too: a multi-track 踏切 is down almost all day (開かずの踏切), so a block street ends there.
      * `boxes`: each station's platform footprint and its car park -- hard for buildings; hard for streets too,
        except an ELEVATED station (`street_under`), which a street passes under as Tokyo's do.
    An ARTERIAL is not generated by the street planner, so this record never closes one: it takes a (wide) 踏切 or
    passes under, as the layout's report says."""
    lines = {}
    for name, L in res["lines"].items():
        pts, cum, z, g = L["pts"], L["cum"], L["z"], L["ground"]
        samp, nxt = [], 0.0
        for i in range(len(pts)):
            if cum[i] + 1e-6 >= nxt or i == len(pts) - 1:
                samp.append([round(pts[i][0], 2), round(pts[i][1], 2), round(z[i], 2), round(g[i], 2),
                             _cross_rule(z[i] - g[i])])
                nxt = cum[i] + RESERVE_STEP
        lines[name] = samp
    # a STREET crossing the layout closes (too near a junction, too oblique, several lines side by side): its samples
    # are 'no', so the street planner ends the street at the corridor by the reserve's own rule
    for name, samp in lines.items():
        for c in res["lines"][name]["crossings"]:
            if c["form"] != "street closed":
                continue
            reach = ROAD_HALF["street"] + TRACK_HALF + 5.0
            for q in samp:
                if q[4] == "level" and math.hypot(q[0] - c["x"], q[1] - c["y"]) < reach:
                    q[4] = "no"
    grade = {n: [q[:2] for q in samp if q[4] == "level"] for n, samp in lines.items()}   # BEFORE any is re-marked
    for name, samp in lines.items():
        for q in samp:
            if q[4] == "level" and any(other != name and any(math.hypot(r[0] - q[0], r[1] - q[1]) < MULTI_M
                                                             for r in pts_)
                                       for other, pts_ in grade.items()):
                q[4] = "no"
    boxes = []
    # WHICH SIDE the station building and its car park go on (PLAN.md R3): the side an at-grade ARTERIAL is nearer --
    # a station's front faces the town, never the dike or the sea. The arterials INPUT is used, not the derived record:
    # it is what exists before this reserve is read, and a block street is planned round the station afterwards.
    art_pts = []
    try:
        ad = json.load(open(ARTERIALS))
        AP = {p["uid"]: p for p in ad["points"]}
        for r in ad["roads"]:
            ps = [AP[u]["pos"] for u in r["points"] if u in AP]
            for a_, b_ in zip(ps, ps[1:]):
                if max(a_[2], b_[2]) > 3.0:
                    continue
                k = max(1, int(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) // 10.0))
                art_pts += [(a_[0] + (b_[0] - a_[0]) * j / k, a_[1] + (b_[1] - a_[1]) * j / k) for j in range(k + 1)]
    except (OSError, ValueError):
        pass
    gnd = rg.Ground(dike=False)
    crest = rg.Ground()          # with the dike: a ring stretch on the dike is no at-grade frontage (it is 12 m up)
    art_pts = [q for q in art_pts if crest.z(*q) - gnd.z(*q) < 1.0]
    # the arterials' PAVED footprint (centreline samples every 4 m with the road's own half width + 1 m), so a station
    # building or car park is never laid across one (probe_road_clear, 2026-09-26: the Bay and Waterpark buildings
    # stood on rinkai_dori and wangan_dori)
    art_paved = {}
    try:
        for r in ad["roads"]:
            b = r.get("base", {})
            half = (max(b.get("lanes_fwd", 1), b.get("lanes_bwd", 1)) * b.get("lane_width", 4.5)
                    + b.get("median_width", 0.0) / 2.0
                    + max(b.get("left_walk_width", 0.0), b.get("right_walk_width", 0.0)) + 1.0)
            ps = [AP[u]["pos"] for u in r["points"] if u in AP]
            for a_, b_ in zip(ps, ps[1:]):
                if max(a_[2], b_[2]) > 3.0:
                    continue
                k = max(1, int(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) // 4.0))
                for j in range(k + 1):
                    q = (a_[0] + (b_[0] - a_[0]) * j / k, a_[1] + (b_[1] - a_[1]) * j / k, half)
                    art_paved.setdefault((int(q[0] // 50), int(q[1] // 50)), []).append(q)
    except (NameError, KeyError):
        pass

    # every OTHER line's track (a station building beside one line must not stand on the next line's track: Bay's and
    # Harbour's did, probe_rail_track's gauge 2026-09-26); the station's own line is kept off by the placement itself
    rail_paved = {}
    for lname, samp in lines.items():
        for q in samp:
            rail_paved.setdefault((int(q[0] // 50), int(q[1] // 50)), []).append((q[0], q[1], OTHER_TRACK_CLEAR, lname))

    def box_clear(cx, cy, ux, uy, ha, hc, own_line=None):
        """No arterial's paved edge, and no other rail line's track, inside the box (centre, along-axis, half along,
        half across)."""
        nxb, nyb = -uy, ux
        for i in range(-int(ha // 2), int(ha // 2) + 1):
            for j in range(-int(hc // 2), int(hc // 2) + 1):
                x, y = cx + ux * i * 2 + nxb * j * 2, cy + uy * i * 2 + nyb * j * 2
                for gi in (int(x // 50) - 1, int(x // 50), int(x // 50) + 1):
                    for gj in (int(y // 50) - 1, int(y // 50), int(y // 50) + 1):
                        if any(math.hypot(q[0] - x, q[1] - y) < q[2] for q in art_paved.get((gi, gj), ())):
                            return False
                        if any(q[3] != own_line and math.hypot(q[0] - x, q[1] - y) < q[2]
                               for q in rail_paved.get((gi, gj), ())):
                            return False
        return True

    def over_dike(a_, b_):
        L = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
        k = max(1, int(L // 6.0))
        return any(crest.z(a_[0] + (b_[0] - a_[0]) * j / k, a_[1] + (b_[1] - a_[1]) * j / k)
                   - gnd.z(a_[0] + (b_[0] - a_[0]) * j / k, a_[1] + (b_[1] - a_[1]) * j / k) > 1.0
                   for j in range(k + 1))

    def side_cost(px, py):
        """How far the town is from this side: the nearest at-grade arterial reachable WITHOUT crossing the dike (a
        harbour road beyond it is not this station's street), plus a kilometre if the side is water."""
        d = 3000.0
        for q in sorted(art_pts, key=lambda q: math.hypot(px - q[0], py - q[1]))[:60]:
            if not over_dike((px, py), q):
                d = math.hypot(px - q[0], py - q[1])
                break
        return d + (1000.0 if gnd.z(px, py) < -1.0 else 0.0)    # record 0 is the city plain (NET_Y)
    for n, st in res["stations"].items():
        L = res["lines"][st["line"]]
        i0 = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (st["s"] - st["platform_m"] / 2)))
        i1 = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - (st["s"] + st["platform_m"] / 2)))
        (px, py), (qx, qy) = L["pts"][i0], L["pts"][i1]
        ux, uy = qx - px, qy - py
        ul = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ul, uy / ul
        nx, ny = -uy, ux
        hw = STATION_W[st["kind"]] / 2
        probe = hw + 40.0
        if side_cost(st["x"] - nx * probe, st["y"] - ny * probe) < side_cost(st["x"] + nx * probe, st["y"] + ny * probe):
            nx, ny = -nx, -ny
        # the building and the car park must not stand on an arterial: slide them along the platform, then try the
        # other side; the town side at its centre is the preference, the first clear placement wins
        pw, ph = PARKING[st["parking"]]
        shift = 0.0
        # the building's back stands STATION_YARD behind its platform's outer edge (the paid yard its stair lands in),
        # else where the reserve always put it, at the station box's edge
        import island_rail_record as IRR
        boffs = (IRR.platform_outer(st["kind"]) + STATION_YARD + STATION_BUILDING[1] / 2, hw + 5.0)
        boff = boffs[-1]
        if st["kind"] != "hub":
            span = max(0.0, ul / 2 - STATION_BUILDING[0] / 2)
            tries = [(sg, bo, d) for sg in (1.0, -1.0) for bo in boffs
                     for d in (0.0, 10.0, -10.0, 20.0, -20.0, 30.0, -30.0, 45.0, -45.0) if abs(d) <= span + 1e-6]
            for sg, bo, d in tries:
                bx, by = st["x"] + sg * nx * bo + ux * d, st["y"] + sg * ny * bo + uy * d
                ok = box_clear(bx, by, ux, uy, STATION_BUILDING[0] / 2 + 0.5, STATION_BUILDING[1] / 2 + 0.5, st["line"])
                if ok and pw:
                    off = hw + 10 + ph / 2
                    ok = box_clear(st["x"] + sg * nx * off + ux * d, st["y"] + sg * ny * off + uy * d,
                                   ux, uy, pw / 2, ph / 2, st["line"])
                if ok:
                    nx, ny, shift, boff = sg * nx, sg * ny, d, bo
                    break
            else:
                print("reserve: %s -- no placement of its building/car park clears the arterials" % n)
        # an ELEVATED station (a road clears its deck) keeps buildings off but lets a street pass under it
        gi = min(range(len(L["cum"])), key=lambda k: abs(L["cum"][k] - st["s"]))
        boxes.append({"id": "station:" + n, "x": round((px + qx) / 2, 2), "y": round((py + qy) / 2, 2),
                      "ux": round(ux, 5), "uy": round(uy, 5), "h_along": round(ul / 2 + 5.0, 2), "h_across": hw,
                      "z": round(st["z"], 2),
                      "street_under": _cross_rule(st["z"] - L["ground"][gi]) == "under"})
        # THE STATION BUILDING (駅舎, PLAN.md R3): in the 10 m between the platform box and the car park, its back to
        # the platform fence and its front to the car park / street side. A hub's is its own site (Central: the
        # Tokyo Station building), so it gets none here. `island_sites.rail_stations` places it from THIS box.
        if st["kind"] != "hub":
            boxes.append({"id": "building:" + n, "x": round(st["x"] + nx * boff + ux * shift, 2),
                          "y": round(st["y"] + ny * boff + uy * shift, 2), "ux": round(ux, 5), "uy": round(uy, 5),
                          "h_along": STATION_BUILDING[0] / 2 + 0.5, "h_across": STATION_BUILDING[1] / 2 + 0.5,
                          "nx": round(nx, 5), "ny": round(ny, 5)})
        # ...and ONE ON THE FAR SIDE (user, 2026-09-27: "station on both side of rail rather than just one side due
        # to gating"): an open-air station's two side platforms each have their OWN gated building, so neither
        # platform needs a footbridge to reach the gates -- the small-station layout (上下線で別改札). A hub is one
        # building over the whole rail with a bridge inside the paid area (3.36), so it gets neither. No car park on
        # the far side: the town side has it. Slid along the platform like the near one; none if nothing clears.
        if st["kind"] != "hub":
            span = max(0.0, ul / 2 - STATION_BUILDING[0] / 2)
            for bo, d in [(bo, d) for bo in boffs for d in (shift, 0.0, 10.0, -10.0, 20.0, -20.0, 30.0, -30.0, 45.0,
                                                               -45.0)]:
                if abs(d) > span + 1e-6:
                    continue
                bx, by = st["x"] - nx * bo + ux * d, st["y"] - ny * bo + uy * d
                if box_clear(bx, by, ux, uy, STATION_BUILDING[0] / 2 + 0.5, STATION_BUILDING[1] / 2 + 0.5,
                             st["line"]) and not over_dike((st["x"], st["y"]), (bx, by)) and gnd.z(bx, by) > -1.0:
                    boxes.append({"id": "building_far:" + n, "x": round(bx, 2), "y": round(by, 2),
                                  "ux": round(ux, 5), "uy": round(uy, 5),
                                  "h_along": STATION_BUILDING[0] / 2 + 0.5, "h_across": STATION_BUILDING[1] / 2 + 0.5,
                                  "nx": round(-nx, 5), "ny": round(-ny, 5)})
                    break
            else:
                print("reserve: %s -- no far-side station building clears (its far platform has no gates)" % n)
        w, h = PARKING[st["parking"]]
        if w:
            off = hw + 10 + h / 2           # the same place the picture draws it
            boxes.append({"id": "parking:" + n, "x": round(st["x"] + nx * off + ux * shift, 2),
                          "y": round(st["y"] + ny * off + uy * shift, 2),
                          "ux": round(ux, 5), "uy": round(uy, 5), "h_along": w / 2, "h_across": h / 2,
                          "kind": st["parking"]})
    doc = {"schema": 1, "layout": LAYOUT_NAME,
           "notes": "Rail corridor + station reserve, written by tools/island_rail_layout.py --reserve; record frame. "
                    "Read by island_buildings.py (buildings keep off) and island_streets.py (streets keep off).",
           "corridor_half": CORRIDOR_HALF,
           "corridors": [{"line": n, "pts": s} for n, s in lines.items()],
           "boxes": boxes}
    json.dump(doc, open(out, "w"), indent=1, ensure_ascii=False)
    nno = sum(1 for s in lines.values() for q in s if q[4] == "no")
    print("reserve: %d corridor samples (%d no-cross), %d boxes -> %s" % (
        sum(len(s) for s in lines.values()), nno, len(boxes), os.path.relpath(out, ROOT)))


LAYOUT_NAME = "v2"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_PNG)
    ap.add_argument("--json", default=OUT_JSON)
    ap.add_argument("--check", action="store_true", help="report only; exit 1 on any finding")
    ap.add_argument("--preview", default=OUT_PNG.replace(".png", "_preview.png"),
                    help="the review picture (the rail area, larger, decisions marked)")
    ap.add_argument("--layout", default="v2", choices=sorted(LAYOUTS))
    ap.add_argument("--reserve", action="store_true",
                    help="write the reserve record the derive reads (%s)" % os.path.relpath(RESERVE_OUT, ROOT))
    a = ap.parse_args(argv)
    global LAYOUT_NAME
    LAYOUT_NAME = a.layout
    use_layout(a.layout)
    if a.layout != "v2":
        a.out = a.out.replace(".png", "_%s.png" % a.layout)
        a.preview = a.preview.replace("_preview.png", "_%s_preview.png" % a.layout)
        a.json = a.json.replace(".json", "_%s.json" % a.layout)
    res = analyse()
    bad = report(res)
    if a.reserve:
        reserve(res, RESERVE_OUT)
        return 0
    if a.check:
        return 1 if bad else 0
    picture(res, a.out)
    preview(res, a.preview)
    if a.json:
        dump(res, a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
