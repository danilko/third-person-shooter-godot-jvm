#!/usr/bin/env python3
"""island_reshape.py -- the island's LAND, reshaped to the final plan (PLAN.md 3.29 / 3.30 L0.1, L1).

    python3 tools/island_reshape.py build   [--base <f32>] [--out <f32>] [--preview <png>]
    python3 tools/island_reshape.py check   [--base <f32>] [--land <f32>]
    python3 tools/island_reshape.py base    <dump.f32>       # clamp + widen a raw Terrain3D dump -> the committed base

WHAT IT IS. 3.29 decided the island's final shape (`reference/island_final_plan_2026-09-21.png`, v15) and drew it in
a scratchpad sketch; this is that sketch made a repo tool, on the WHOLE world grid, from a committed base. It writes
the LAND: the natural ground before any road is sculpted into it or stamped onto it. The touge sculpt, the beach
shelf and the stamps come after it, in `tools/island_terrain.sh`, which is the one order the terrain is built in.

THE BASE is `assets/world_source/terrain/island_base.f32`: the island as `island_to_terrain3d.py` imported it (the
Terrain3D data of 245ed60), with the seabed clamped to -24 m (`set_world_depths.gd`) and the first mountain's east face
widened (`island_widen_first_mountain.py`). Verified against the natural-ground sidecar it replaces: equal to 1 mm on
every land cell away from the touge. It is committed rather than re-derived from git history because the commit the
previous chain named (a389d61) did not survive a history rewrite; the base now does not depend on one.

WHAT IT CHANGES, each decided and measured in 3.29 (Godot x/z metres; the grid is `dump_height_grid.gd`'s layout,
row j = z0 + j*2, column i = x0 + i*2, x0 = z0 = -2304):
  * the GULF HEAD is landfill (v1): water inside GULF_FILL becomes the 0.6 m city plain, a quay on its south edge;
  * the HARBOUR's empty tip and its south 120 m are trimmed (v7): land south of HARBOUR_TRIM_Z inside its x range;
  * the far WEST and EAST coasts are pulled in (v6): flat land (< 40 m) within 240 m of the sea, west of x -1250 south
    of z 150, and east of x 1400 between z -950 and 420;
  * the farm and the city's east side end at a gently waving seawall near x 1350, the resort near x 1300 (v9);
  * the airport island ends at x 1500 (v9; it does NOT move north, R2);
  * the top of the island moves 150 m south (v10): the farm block (x >= 350, z < -700) is shifted, its old north
    edge becomes sea;
  * the MOUNTAIN (v11-v14):
    - every height above 200 m x0.55, then the old north summit x0.5 again (793 -> ~360 m);
    - a LEVEL 435 m summit plateau (radius 130 m) round a 330 m crest, turned 15 deg, the ground a dome round it
      falling off over 490 m; the interior is the 60 m-smoothed ground, and within ~60-220 m of the sea the real ground
      is kept so the coasts keep their shape;
    - the west shore pulled in to x ~ -1390 with a gentle wave, easing onto the residential shore (x -1500);
    - every mountain coast capped at <= 45 deg (h <= 1 + distance to the sea), the NE shoulder eased onto the farm
      (h <= 1 + (350 - x) north of z -760), which also removes the 125 m step at x 350 the source data carries.
Everything trimmed or vacated becomes the -24 m seabed; the beach shelf is re-laid afterwards by `island_coast.py`.

GATES (`check`, exit 1 on any failure):
  * the shrine plateau is kept: p90 slope within PLATEAU_R of its centre does not grow;
  * no LAND step over MAX_LAND_STEP metres between two neighbouring land cells;
  * every mountain coast within COAST_BAND of the sea is at most 45 deg (1:1) between any two land cells;
  * the snow (> 380 m) is about SNOW_KM2;
  * the summit plateau is level (its crest samples within 0.5 m of PLATEAU_Z + RAISE).
"""
import argparse
import json
import math
import os
import struct
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

TERRAIN_DIR = os.path.join(ROOT, "assets", "world_source", "terrain")
BASE = os.path.join(TERRAIN_DIR, "island_base.f32")
LAND = os.path.join(TERRAIN_DIR, "island_land.f32")

N = 2305
X0 = Z0 = -2304.0
STEP = 2.0
SEABED = -24.0
LAND_Z = 0.35                 # a cell above this is land (the land base stands +0.60 over the sea)
FLOOR_Z = 0.6                 # the city plain

# --- the coast edits (v1, v6, v7, v9, v10) ---
GULF_FILL = (300.0, 280.0, 900.0, 760.0)          # x0, z0, x1, z1: the gulf HEAD, filled
HARBOUR_TRIM = (-820.0, 300.0)                    # x range of the harbour peninsula...
HARBOUR_TRIM_Z = 1540.0                           # ...trimmed south of this
# THE CONTAINER QUAY IS STRAIGHT (user, 2026-09-25: "straighten up the harbour, so it is square"). The base's east quay
# ran from x 248 (z 1050) to x 204 (z 1500), 5.6 deg off north, and the terminal was fitted to it at yaw 85. Here it is a
# straight seawall at x = 250, in line with the coast north of it (no step): land east of the line becomes quay water (at the seabed, a berth), water
# west of it is filled to the city plain. The terminal stands square on it (IslandSites.json, yaw 90, east face 3.5 m in).
HARBOUR_QUAY = (250.0, 940.0, 1538.0, 140.0, 320.0)   # quay x, z0, z1, and the x window the edit may touch
EDGE_TRIM_M = 240.0                               # the far west and east coasts pulled in this far...
EDGE_TRIM_MAX_Z = 40.0                            # ...on flat land only
EAST_WALL = (1350.0, 80.0, 300.0)                 # x = a + b sin(z / c), north of z 420: the farm/city seawall
RESORT_WALL = (1300.0, 60.0, 250.0)               # the same for the resort, z 420..1150
AIRPORT_END_X = 1500.0
FARM_SHIFT = 150.0                                # the farm block moves this far south (x >= FARM_X, z < FARM_Z)
FARM_X, FARM_Z = 350.0, -700.0
FARM_RAMP = 300.0                                 # ...eased over this in x (about FARM_X) and in z (north of FARM_Z)
SHORE_TOP = 0.4                                   # island_v3_terrain.SHORE_Z + 0.6: dry sand one step off the land
SHORE_RUN = 350.0                                 # island_v3_terrain.SHELF_RUN (175 m x SCALE 2)

# --- the mountain (v11-v14) ---
LOWER_ABOVE = 200.0
LOWER_K1, LOWER_K2 = 0.55, 0.5
PLATEAU_Z = 435.0
# v16 (PLAN.md 3.30 L2, user 2026-09-22: "move the crest west"): v14's crest (-475, -1120) at -15 deg stood 365 m from
# the city plain, so the dome's skirt climbed the plain (30-70 m of new hillside where the base was 0.6 m, a junction on
# a 42% slope). Searched for the centre and turn that keep the whole 330 m crest, its 130 m level plateau and a <= 1:1
# foot inside the massif on BOTH sides -- the sea (the coast cap) and the plain (PLAIN_K below): this one clears both by
# 9 m. The massif is only ~1.2 km wide between the west shore and the plain, so the crest now runs NW-SE along it.
CREST_C = (-675.0, -1125.0)
CREST_DEG = -45.0
CREST_HALF = 165.0
CREST_R0 = 130.0
CREST_W = 490.0
SMOOTH_K = 15                                     # the interior: a (2k+1)^2 box = 62 m
COAST_KEEP = (60.0, 160.0)                        # real ground kept within 60 m of the sea, blended over 160 m
WEST_X = -1390.0                                  # the west shore of the massif
COAST_SLOPE = 1.0                                 # a mountain coast is at most 45 deg
COAST_ROUND = 80.0                                # the massif's convex coast corners have at least this radius
MASS = "mass"                                     # (see mass_mask)
# THE CITY PLAIN IS NEVER RAISED (v16). `mass_mask` runs to x 350 and takes in the flat strip east of the massif's foot,
# and the dome falls off over CREST_W = 490 m, so without this its skirt stood 18-70 m of hillside on land the base had
# at 0.6 m, where the plan puts residential north and the chuo_dori x nishi_dori junction. Land under PLAIN_Z on the
# city side keeps its own height, and the massif rises from it at no more than PLAIN_K : 1 -- the coasts' 45 deg.
PLAIN_Z = 3.0
PLAIN_K = 1.0
PLAIN_BOX = (-400.0, -1300.0, 400.0, 300.0)       # x0, z0, x1, z1: the plain east of the massif (not its beaches)

# --- gates ---
# The shrine plateau (~281 m in the base, 0.39 km2, x -1634..-852) is HALVED by design: v14's west trim puts the sea
# at x ~ -1351, and its 45 deg shore slope reaches ~240 m in (the v14 note: "the plateau junction (-1113,-814) needs
# ~240 m of shore slope west of it"). The sketch measured the plateau at (-1250, -770) and read a 2.0 slope there
# afterwards -- its own gate was pointed at the half it removed. What must stay level is the half the touge uses.
# v16: the moved crest's west flank now covers the plateau's NORTH half (x -1100..-1000 north of z -750), so what must
# stay level -- and where phase 1 now tops out -- is its south half.
PLATEAU_C = (-1060.0, -600.0)
PLATEAU_R = 80.0
PLATEAU_LEVEL = 0.08
MAX_LAND_STEP = 8.0
COAST_BAND = 60.0
SNOW_Z = 380.0
SNOW_KM2 = (0.25, 0.45)


def grid():
    x = X0 + STEP * np.arange(N)
    z = Z0 + STEP * np.arange(N)
    return x[None, :], z[:, None]


def load(path):
    return np.fromfile(path, dtype=np.float32).reshape(N, N)


def box(xx, zz, b):
    return (xx >= b[0]) & (xx <= b[2]) & (zz >= b[1]) & (zz <= b[3])


def ramp(v, a, b):
    return np.clip((v - a) / (b - a), 0.0, 1.0)


def distance_from(src, max_m):
    """Metres from the nearest `src` cell (an octagonal dilation), inf past max_m. island_coast.distance_from."""
    import island_coast
    return island_coast.distance_from(src, max_m)


def box_mean(a, k):
    c = np.cumsum(np.cumsum(np.pad(a.astype(np.float64), ((k + 1, k), (k + 1, k)), mode="edge"), 0), 1)
    return ((c[2 * k + 1:, 2 * k + 1:] - c[:-2 * k - 1, 2 * k + 1:] - c[2 * k + 1:, :-2 * k - 1]
             + c[:-2 * k - 1, :-2 * k - 1]) / (2 * k + 1) ** 2)


def lower(g):
    g = np.where(g > LOWER_ABOVE, LOWER_ABOVE + (g - LOWER_ABOVE) * LOWER_K1, g)
    return np.where(g > LOWER_ABOVE, LOWER_ABOVE + (g - LOWER_ABOVE) * LOWER_K2, g)


def crest():
    a = math.radians(CREST_DEG)
    d = np.array([math.cos(a), math.sin(a)])
    c = np.array(CREST_C)
    return c - d * CREST_HALF, c + d * CREST_HALF


def crest_distance(xx, zz):
    A, B = crest()
    ab = B - A
    t = np.clip(((xx - A[0]) * ab[0] + (zz - A[1]) * ab[1]) / (ab @ ab), 0.0, 1.0)
    return np.hypot(xx - (A[0] + t * ab[0]), zz - (A[1] + t * ab[1]))


def mass_mask(xx, zz):
    """The massif's region: where the mountain's own heights replace the base."""
    return ((xx < 350) & (zz < 260)) | ((xx < -1000) & (zz < 420)) | ((xx >= 350) & (xx < 900) & (zz < -700))


def shift_south(a, xx, fill):
    """The farm block moved FARM_SHIFT south; `fill` where the move uncovers the old north band.

    The shift is SMOOTH: full east of FARM_X + FARM_RAMP / 2 and north of FARM_Z - FARM_RAMP, easing to nothing over
    FARM_RAMP in both directions. A rigid block (the plan picture's) cut a 150 m STEP into the north coastline at
    x 350 that the coast road's walker cannot follow (it turns at most 5 deg per 8 m), and a seam at z -700."""
    zz = Z0 + STEP * np.arange(N)[:, None]
    s = FARM_SHIFT * ramp(xx, FARM_X - FARM_RAMP / 2, FARM_X + FARM_RAMP / 2) * (1.0 - ramp(zz, FARM_Z - FARM_RAMP,
                                                                                         FARM_Z))
    k = np.rint(s / STEP).astype(int)
    rows = np.arange(N)[:, None] - k
    src = np.clip(rows, 0, N - 1)
    out = np.take_along_axis(a, np.broadcast_to(src, a.shape), axis=0)
    return np.where(rows < 0, fill, out)


def reshape(base):
    xx, zz = grid()
    land0 = base > LAND_Z
    sea0 = ~land0
    # 1. the coast edits, on the original coordinates
    fill = sea0 & box(xx, zz, GULF_FILL)
    qx, qz0, qz1, qw0, qw1 = HARBOUR_QUAY
    in_quay = (zz >= qz0) & (zz <= qz1) & (xx >= qw0) & (xx <= qw1)
    qfill = sea0 & in_quay & (xx <= qx)
    fill |= qfill
    # the squared quay is filled to its own PLATFORM's height (the row's land inside the window), not the city floor:
    # the port platform stands at 4.6 m, and a 0.6 m fill left a 4 m step inside the container terminal
    qplat = np.where(land0 & in_quay, base, -np.inf).max(axis=1)[:, None]
    qplat = np.where(np.isfinite(qplat), qplat, FLOOR_Z)
    # a trim either leaves a QUAY (a seawall straight into deep water: the harbour, the city's east seawall, the
    # airport's end) or a SHORE (the base's own shelving seabed, laid from the new coast: the west, the resort)
    quay = land0 & (xx >= HARBOUR_TRIM[0]) & (xx <= HARBOUR_TRIM[1]) & (zz >= HARBOUR_TRIM_Z)
    near_sea = distance_from(sea0, EDGE_TRIM_M) < EDGE_TRIM_M
    shore = land0 & near_sea & (base < EDGE_TRIM_MAX_Z) & (xx < -1250) & (zz > 150)
    quay |= land0 & near_sea & (base < EDGE_TRIM_MAX_Z) & (xx > 1400) & (zz > -950) & (zz < 420)
    quay |= land0 & (xx > EAST_WALL[0] + EAST_WALL[1] * np.sin(zz / EAST_WALL[2])) & (zz < 420)
    shore |= land0 & (xx > RESORT_WALL[0] + RESORT_WALL[1] * np.sin(zz / RESORT_WALL[2])) & (zz >= 420) & (zz <= 1150)
    quay |= land0 & (xx > AIRPORT_END_X) & (zz >= 1050)
    quay |= land0 & in_quay & (xx > qx)
    shore &= ~quay
    trim = quay | shore
    land = (land0 | fill) & ~trim
    g = np.where(fill, np.where(qfill, qplat, FLOOR_Z), np.where(trim, SEABED, base)).astype(np.float64)
    # ...and one level platform: a low cell the base carried inside it (a ditch left by the old coastline) comes up
    g = np.where(in_quay & (xx <= qx) & ~trim, np.maximum(g, qplat), g)
    # 2. the farm block moves 150 m south
    g = shift_south(g, xx, SEABED)
    land = shift_south(land, xx, False)
    quay = shift_south(quay, xx, False)
    newsea = shift_south(shore, xx, True)                # the vacated north band is new sea as well
    # 3. the mountain
    mtn = (xx < 350) & (zz < 150)
    wz = ramp(zz, -1450, -1250) * ramp(260 - zz, 0, 100)
    xt = np.where(zz < 160, WEST_X + 40.0 * np.sin(zz / 170.0), WEST_X + (-1500.0 - WEST_X) * ramp(zz, 160, 300))
    cut_w = (xx < 350) & (zz < 420) & (zz > -1450) & (xx < xt - ramp(-zz, 1250, 1450) * 600)
    cut_ne = mtn & (zz < -1830 + (1 - ramp(xx, -50, 150)) * (-300))
    mcut = land & (cut_w | cut_ne)
    land &= ~(cut_w | cut_ne)
    # round the massif's CONVEX corners (a morphological opening, COAST_ROUND): the trims above are boxes and waves,
    # and the coast road walks the shore at a road's radius -- a corner sharper than that it cannot turn, and it ran
    # out over the sea round the north-west corner and the north-east notch
    mass0 = mass_mask(xx, zz)
    core = land & (distance_from(~land, COAST_ROUND + 4.0) >= COAST_ROUND)
    opened = distance_from(core, COAST_ROUND + 4.0) <= COAST_ROUND
    rounded = land & mass0 & ~opened
    mcut |= rounded
    land &= ~rounded
    d_sea = distance_from(~land, 480.0)
    d_sea[~np.isfinite(d_sea)] = 480.0
    rough = lower(g)
    smooth = lower(box_mean(g, SMOOTH_K))
    r = crest_distance(xx, zz)
    u = np.clip((r - CREST_R0) / CREST_W, 0.0, 1.0)
    dome = PLATEAU_Z * (1 - (3 * u ** 2 - 2 * u ** 3))
    inner = np.maximum(smooth, dome)
    plain = land & (g < PLAIN_Z) & box(xx, zz, PLAIN_BOX)
    d_plain = distance_from(plain, 700.0)
    d_plain[~np.isfinite(d_plain)] = 1e6
    inner = np.minimum(inner, np.maximum(g, PLAIN_Z + PLAIN_K * d_plain))
    wc = np.clip((d_sea - COAST_KEEP[0]) / COAST_KEEP[1], 0.0, 1.0)
    h = wc * inner + (1 - wc) * rough
    h = np.minimum(h, 1.0 + d_sea)                                      # every coast <= 45 deg...
    shoulder = mass_mask(xx, zz) & (zz < -700)
    h = np.where(shoulder, np.minimum(h, 1.0 + np.maximum(0.0, 350.0 - xx) + 1e4 * ramp(zz, -760, -700)), h)
    h = np.maximum(h, FLOOR_Z)
    mass = mass_mask(xx, zz)
    # ...and not only on AVERAGE: the cap bounds a cell by its distance to the sea, so a cliff the SOURCE carries (a
    # 0.6 m beach strip at the foot of an 11 m wall, all along the north coast) passes it cell by cell. The coast band
    # is therefore also clamped to a 1:1 slope from every neighbour (lowering only; interior cells hold still).
    # The whole massif is clamped, not only the coast band: a band boundary is itself a step (a band cell lowered
    # from the sea stood 10 m under the capped interior beside it). The sea cells hold 0.6 m, so this IS the 45 deg
    # coast cap as well, measured along the ground instead of as a straight distance.
    out = np.where(mass & land, h, g)
    newsea |= mcut
    # the SEA, laid again from the new coast: the base's own profile (0.4 m at the waterline -- a walkable step off the
    # 0.6 m land -- easing to the seabed over SHORE_RUN), never shallower than it was (a dredged harbour keeps its
    # depth), and the old nearshore ring left offshore by a trim sinks to the depth its new distance asks for
    d_land = distance_from(land, SHORE_RUN + 10.0)
    t = np.clip(d_land / SHORE_RUN, 0.0, 1.0)
    prof = SHORE_TOP + (SEABED - SHORE_TOP) * t * t * (3 - 2 * t)
    sea = np.where(quay, SEABED, np.where(newsea, prof, np.minimum(out, prof)))
    out = np.where(land, out, sea)
    out = slope_clamp(out, mass & land, COAST_SLOPE)
    out, dike, works = coastal_works(out, land, xx, zz)
    # THE MILITARY BASE's two finger piers and its air base strip (PLAN.md 3.30 L3, user 2026-09-26), at the
    # port platform's own height, vertical quay edges into the open deep water on every side
    for x0, x1, z0, z1 in MILITARY_PIERS:
        out = np.where((xx >= x0) & (xx <= x1) & (zz >= z0) & (zz <= z1), MILITARY_PIER_Z + RAISE, out)
    edits = {"fill": fill, "trim": trim | mcut, "dike": dike, "works": works}
    return out.astype(np.float32), land, edits


#: The base's finger piers (Godot x0, x1, z0, z1): 50 m wide, reaching 260 m WEST of the platform's west edge
#: (x ~-760) into -24 m of water, 80 m apart so a ship berths between them. They were first drawn south, and the
#: air base's runway strip (user, 2026-09-26: "a small airlane/terminal for standard fighter flight/landing") now
#: takes that water.
MILITARY_PIERS = ((-1020.0, -740.0, 1300.0, 1350.0), (-1020.0, -740.0, 1430.0, 1480.0),
                  # the AIR BASE: a reclaimed strip off the south-west coast (Iwakuni / Naha are reclaimed too), its
                  # north edge on the platform's south edge, 1 210 m long for a 1 200 x 45 m runway + a parallel
                  # taxiway; the paving is reserved (island_plan.RESERVES) for a later regional pass
                  (-1650.0, -440.0, 1540.0, 1760.0))
MILITARY_PIER_Z = 4.6


#: THE LAND IS RAISED AND THE COAST IS A SEAWALL WITH A BEACH IN FRONT (user, 2026-09-26: "the land height should
#: overall increase ... the dike should follow 12 and 14.7 m from sea level, the Japan standard, inland raised 5 m or
#: more, a beach on the ocean side with a slower slope into the ocean, except the harbour, which stays steep and
#: higher to match a large cargo ship"). Three rules:
#:  * EVERY land cell stands RAISE higher (the city plain FLOOR_Z + RAISE = 5.6 m above the sea), the massif included;
#:    inland water keeps its level, so its banks fall at 1:BANK to it. The road network's node moves up by the same
#:    RAISE (island_roadgen.NET_Y), so every road RECORD is unchanged: a record height is Godot height less NET_Y.
#:  * a NATURAL SHELVING SHORE (open sea shallower than DIKE_SHELF_Z beside low land, out of every harbour-type zone)
#:    gets a seawall (海岸堤防) on RECLAIMED shallow sea in front of today's coastline, so the coast roads behind it do
#:    not move: from the old land edge a 1:DIKE_BACK back slope up from the raised plain to the crest, a DIKE_TOP crest,
#:    a 1:DIKE_FACE seaward face down to the beach top BEACH_TOP, a 1:BEACH beach to the water line, then the shelf
#:    (island_coast.shelf_target). The crest is DIKE_CREST_BAY (12.0 m) inside the bay and DIKE_CREST_OPEN (14.7 m,
#:    the post-2011 Sanriku standard) where the sea round it is open ocean (EXPOSURE_R).
#:  * a harbour / quay / seawall zone keeps its vertical edge into deep water, now RAISE higher: a quay deck ~5.6 m over
#:    the sea (the port platform 9.6 m), the height a large ship berths against.
#: Where a road stands too near for the wall (its band + DIKE_ROAD_CLEAR), the crest drops to the plain over
#: DIKE_END_W and only the beach remains. DIKE_ACCESS are the openings to the sand: a DIKE_GAP-wide gap whose face
#: eases to 1:DIKE_RAMP, recorded in island_dike.json for the stairs, gates (陸閘) or beach car parks a later pass puts
#: there. The cells the works raised are recorded as runs too: "cells" the wall (painted concrete), "works" the wall
#: and the beach (no building, no block fill, no field stands on them).
RAISE = 5.0
BANK = 2.0               # inland water's banks, horizontal per vertical
DIKE_CREST_BAY = 12.0
DIKE_CREST_OPEN = 14.7
EXPOSURE_R = 1000.0      # m: the open-ocean fraction within this decides the crest
EXPOSURE_OPEN = (0.50, 0.60)   # ...12.0 below the first, 14.7 above the second (measured at the coast: p10 0.33, median 0.58, p90 0.64)
DIKE_TOP = 6.0
DIKE_FACE = 2.0          # seaward face, horizontal per vertical
DIKE_BACK = 1.5          # landward slope
BEACH_TOP = 3.0          # the dry sand at the wall's toe
BEACH = 25.0             # the beach, horizontal per vertical, down to the water line
DIKE_LOW = 2.0           # only land lower than this (before the raise) gets a wall
DIKE_ROAD_CLEAR = 8.0    # m past a road's half width (+ the stamp's 6 m verge + margin)
DIKE_END_W = 60.0        # a wall's crest falls to the plain over this at every end
DIKE_GAP = 10.0
DIKE_ACCESS_SPACING = 150.0
DIKE_RAMP = 8.0
WATERLINE_WALL = False   # the wall at the waterline (superseded by the ring-road dike, island_dike.py)
SHORE_BANK = 3.0         # outside the dike: the plain falls to the beach's top at 1:3
#: (name, Godot x, z): the user's list, each laid at the nearest crest cell inside a run -- the suburb (the south-east
#: resort beach's east end), the city's side (the same beach's west end), residential north-east (the north coast's east
#: bend), the farmland (the north coast by the fields) and the west residential side, and the lighthouse side.
DIKE_ACCESS = (("suburb", 1250.0, 880.0), ("city", 950.0, 880.0), ("residential_ne", 880.0, -1580.0),
               ("farm", 700.0, -1650.0), ("residential_west", -1250.0, 640.0), ("lighthouse", 1330.0, -1330.0))
#: The gulf's west bank beside the city is a harbour inlet, not a beach, just outside the gulf zone's box.
DIKE_NOT_BOXES = ((230.0, 300.0, 380.0, 820.0),)
DIKE_JSON = os.path.join(ROOT, "assets", "world_source", "island_dike.json")
DIKE_SHELF_Z = -3.0      # open sea shallower than this beside the land is a shelving shore (a quay drops to -24 m)
DIKE_NOT_ZONES = ("industrial_harbour", "gulf", "military_harbour", "airport_island", "fishing_port", "seawall")


def open_sea(sea):
    """The sea connected to the map's edge (a flood fill at 8 m, then back to 2 m): inland water is not a coast."""
    k = 4
    n = sea.shape[0] // k
    c = sea[:n * k, :n * k].reshape(n, k, n, k).any(axis=(1, 3))
    reach = np.zeros_like(c)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = c[0, :], c[-1, :], c[:, 0], c[:, -1]
    while True:
        g = reach.copy()
        g[1:, :] |= reach[:-1, :]
        g[:-1, :] |= reach[1:, :]
        g[:, 1:] |= reach[:, :-1]
        g[:, :-1] |= reach[:, 1:]
        g &= c
        if (g == reach).all():
            break
        reach = g
    full = np.zeros_like(sea)
    full[:n * k, :n * k] = np.repeat(np.repeat(reach, k, 0), k, 1)
    full[n * k:, :] = sea[n * k:, :]
    full[:, n * k:] = sea[:, n * k:]
    return full & sea


def _road_near(cells, xx, zz, clear):
    """Which of `cells` lie within a (non-expressway) road's half width + `clear` of the committed road record."""
    near_all = np.zeros_like(cells)
    js, is_ = np.nonzero(cells)
    if not js.size:
        return near_all
    rec = json.load(open(os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.roads.json")))
    pts = {p["uid"]: p["pos"] for p in rec["points"]}
    wx, wz = xx[0, is_], zz[js, 0]
    near = np.zeros(js.size, dtype=bool)
    for r in rec["roads"]:
        if r["name"].startswith("shuto_"):
            continue
        half = (14.5 if r.get("road_class") == "arterial" else 7.0) + clear
        ps = [(pts[u][0], -pts[u][1]) for u in r["points"] if u in pts]
        for (ax, az), (bx, bz) in zip(ps, ps[1:]):
            if max(ax, bx) < wx.min() - half or min(ax, bx) > wx.max() + half:
                continue
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz + 1e-9
            t = np.clip(((wx - ax) * dx + (wz - az) * dz) / L2, 0.0, 1.0)
            near |= np.hypot(ax + t * dx - wx, az + t * dz - wz) < half
    near_all[js[near], is_[near]] = True
    return near_all


def _runs(mask):
    runs = []
    for j in np.nonzero(mask.any(axis=1))[0]:
        row = np.concatenate(([0], mask[j].astype(np.int8), [0]))
        edge = np.nonzero(np.diff(row))[0]
        runs += [[int(j), int(a_), int(b_) - 1] for a_, b_ in zip(edge[0::2], edge[1::2])]
    return runs


def coastal_works(out, land, xx, zz):
    """The RAISE, the seawall and the beach (see the note above RAISE). Returns (grid, wall mask, works mask)."""
    import island_coast as IC
    zones = json.load(open(os.path.join(ROOT, "assets", "world_source", "island_coast.json")))["zones"]
    plain = FLOOR_Z + RAISE
    # only what is really above water is land here: the farm's southward shift leaves some cells in the land MASK at a
    # sea depth (the old coastline's shelf), and raised they surfaced as a sand shelf beside the wall
    land = land & (out > LAND_Z)
    ocean = open_sea(~land)
    inland_water = ~land & ~ocean
    # 1. the raise: every land cell, easing to nothing at inland water's edge (its banks fall at 1:BANK to it)
    d_iw = distance_from(inland_water, RAISE * BANK + 4.0)
    d_iw[~np.isfinite(d_iw)] = 1e6
    new = np.where(land, out + RAISE * np.clip(d_iw / (RAISE * BANK), 0.0, 1.0), out)
    # 2. which coast is a natural shelving shore
    port = np.zeros_like(land)
    for kind in DIKE_NOT_ZONES:
        for x0, x1, z0, z1 in zones.get(kind, ()):
            port |= (xx >= x0) & (xx <= x1) & (zz >= z0) & (zz <= z1)
    for x0, x1, z0, z1 in DIKE_NOT_BOXES:
        port |= (xx >= x0) & (xx <= x1) & (zz >= z0) & (zz <= z1)
    shelf_sea = ocean & (out > DIKE_SHELF_Z)
    near_shelf = distance_from(shelf_sea, 6.0) <= 6.0
    edge = land & ~port & (out < DIKE_LOW) & near_shelf              # the old coastline the works stand in front of
    other = land & ~edge
    # the profile's widest reach: a 14.7 m wall, its beach and the whole shelf
    bw = (DIKE_CREST_OPEN - plain) * DIKE_BACK
    s3_max = bw + DIKE_TOP + (DIKE_CREST_OPEN - BEACH_TOP) * DIKE_RAMP + BEACH_TOP * BEACH
    reach = s3_max + IC.SHELF_W + IC.DROP_W
    # a road standing near the old coastline is not a reason to drop the wall: the wall moves SEAWARD of the road's
    # reserve (half width + DIKE_ROAD_CLEAR, filled at plain level) and its back toe starts there, so the run stays
    # continuous and at full height in front of the coast road
    s0 = distance_from(edge, reach + 4.0)
    road_res = _road_near((np.isfinite(s0) & ocean & ~port) | edge, xx, zz, DIKE_ROAD_CLEAR)
    origin = edge | road_res
    s = distance_from(origin, reach + 4.0)
    so = distance_from(other & ~road_res, reach + 4.0)
    take = ocean & np.isfinite(s) & (s <= so) & ~port
    road_fill = take & road_res
    # 3. the crest: exposure (open ocean round it) -> 12.0 or 14.7
    k = 16
    n = N // k
    oc = ocean[:n * k, :n * k].reshape(n, k, n, k).mean(axis=(1, 3))
    frac = box_mean(oc, int(EXPOSURE_R / (k * STEP)))
    frac = np.repeat(np.repeat(frac, k, 0), k, 1)
    fr = np.full(ocean.shape, float(frac.mean()))
    fr[:n * k, :n * k] = frac
    crest = DIKE_CREST_BAY + (DIKE_CREST_OPEN - DIKE_CREST_BAY) * ramp(fr, *EXPOSURE_OPEN)
    # 4. every end tapers to the plain over DIKE_END_W. Since the ring road became the dike (island_dike.py, user
    # 2026-09-26) there is NO wall at the waterline: the land outside the dike stays at the plain and falls to the
    # beach down a 1:SHORE_BANK bank (WATERLINE_WALL False); the wall machinery is kept behind the flag
    wall_ok = take & ~road_fill & WATERLINE_WALL
    # a run ENDS where the coastline stops being a low shelving shore (a cliff, higher land, a quay) or at a port's water
    coast = land & (distance_from(ocean, 6.0) <= 6.0)
    end = distance_from((coast & ~edge) | (ocean & port), DIKE_END_W + 4.0)
    end[~np.isfinite(end)] = 1e6
    end_w = np.clip(end / DIKE_END_W, 0.0, 1.0)
    # 5. the openings: a gap in the crest whose face eases to 1:DIKE_RAMP
    access = []
    gap_w = np.ones(out.shape)
    cand = wall_ok & (end_w >= 1.0) & (s >= bw) & (s <= bw + DIKE_TOP)
    cj, ci = np.nonzero(cand)
    for name, gx, gz in (DIKE_ACCESS if WATERLINE_WALL else ()):
        if not cj.size:
            break
        cost = (xx[0, ci] - gx) ** 2 + (zz[cj, 0] - gz) ** 2
        for a in access:
            cost = np.where((xx[0, ci] - a["x"]) ** 2 + (zz[cj, 0] - a["z"]) ** 2 < DIKE_ACCESS_SPACING ** 2,
                            np.inf, cost)
        if not np.isfinite(cost).any():
            continue
        kk = int(np.argmin(cost))
        ax, az = float(xx[0, ci[kk]]), float(zz[cj[kk], 0])
        r = np.hypot(xx - ax, zz - az)
        gap_w = np.minimum(gap_w, np.clip((r - DIKE_GAP / 2.0) / 30.0, 0.0, 1.0))
        access.append({"name": name, "x": round(ax, 1), "z": round(az, 1), "kind": "ramp",
                       "note": "a gap in the seawall, its face eased to 1:%g down to the beach; stairs / a gate / a "
                               "beach car park go here" % DIKE_RAMP})
    # 6. the profile along s, with this cell's own crest and face
    c = plain + (crest - plain) * end_w * gap_w * wall_ok
    face = DIKE_FACE * gap_w + DIKE_RAMP * (1.0 - gap_w) if WATERLINE_WALL else np.full(out.shape, SHORE_BANK)
    b0 = (c - plain) * DIKE_BACK
    s1 = b0 + (DIKE_TOP if WATERLINE_WALL else 0.0)
    s2 = s1 + (c - BEACH_TOP) * face
    s3 = s2 + BEACH_TOP * BEACH
    sv = np.where(np.isfinite(s), s, 1e6)
    shelf = IC.shelf_target(np.maximum(sv - s3, 0.0))
    shelf[~np.isfinite(shelf)] = SEABED
    prof = np.where(sv < b0, plain + sv / DIKE_BACK,
                    np.where(sv < s1, c,
                             np.where(sv < s2, c - (sv - s1) / face,
                                      np.where(sv < s3, BEACH_TOP - (sv - s2) / BEACH, shelf))))
    # fade out approaching water the works do not take (a harbour, a cliff's sea), so no underwater wall at the edge
    w = np.clip(distance_from(ocean & ~take, IC.HARD_FADE) / IC.HARD_FADE, 0.0, 1.0)
    w[~np.isfinite(w)] = 1.0
    prof = w * prof + (1.0 - w) * SEABED
    prof = np.where(road_fill, plain, prof)          # a road's reserve is filled level, the wall stands beyond it
    grid = np.where(take, np.maximum(new, prof), new)
    # nothing the works laid stands more than 1:1 under the land or wall beside it: where a beach ends against land it
    # does not front (a headland, higher ground) or a wall's end fades out, the sand banks up at 1:1 (the land's or the
    # wall's height, falling STEP per cell) instead of ending in a cliff the height of the raise
    # (and the dry-sand strip the sea profile leaves at every other shelving waterline, SHORE_TOP, which the raise
    # would otherwise leave 5 m under the land it touches)
    dom = take | (ocean & ~port & (grid > LAND_Z))
    src = (land | take) & ~port
    bank = np.where(src, grid, -np.inf)
    for _ in range(int((DIKE_CREST_OPEN + RAISE) / STEP) + 2):
        g2 = bank.copy()
        g2[1:, :] = np.maximum(g2[1:, :], bank[:-1, :] - STEP)
        g2[:-1, :] = np.maximum(g2[:-1, :], bank[1:, :] - STEP)
        g2[:, 1:] = np.maximum(g2[:, 1:], bank[:, :-1] - STEP)
        g2[:, :-1] = np.maximum(g2[:, :-1], bank[:, 1:] - STEP)
        bank = np.where(dom | src, np.maximum(g2, np.where(src, grid, -np.inf)), -np.inf)
    grid = np.where(dom & (grid > LAND_Z), np.maximum(grid, bank), grid)
    works = take & (grid > LAND_Z) & (grid > new + 0.05)
    wall = works & (grid > plain - 0.5) & (sv < s2)
    json.dump({"schema": 2, "source": "tools/island_reshape.py (coastal_works)", "frame": "godot x, z",
               "raise_m": RAISE, "crest_m": [DIKE_CREST_BAY, DIKE_CREST_OPEN], "access": access,
               "cells": {"x0": float(xx[0, 0]), "z0": float(zz[0, 0]), "step": float(xx[0, 1] - xx[0, 0]),
                         "runs": _runs(wall)},
               "works": {"x0": float(xx[0, 0]), "z0": float(zz[0, 0]), "step": float(xx[0, 1] - xx[0, 0]),
                         "runs": _runs(works)}},
              open(DIKE_JSON, "w"), separators=(",", ":"))
    hi = wall & (grid > DIKE_CREST_BAY - 0.2)
    top = wall & (np.abs(sv - (b0 + s1) / 2.0) <= STEP / 2.0)      # one cell along the crest line: its length
    print("island_reshape: raise %.1f m; seawall %.2f km2, crest line %.1f km (%.1f km >= 12 m, %.1f km >= 14.5 m), "
          "works (wall + beach + road fill) %.2f km2, %d opening(s)"
          % (RAISE, wall.sum() * 4e-6, top.sum() * STEP / 1e3, (top & (grid > DIKE_CREST_BAY - 0.2)).sum() * STEP / 1e3,
             (top & (grid > DIKE_CREST_OPEN - 0.2)).sum() * STEP / 1e3, works.sum() * 4e-6, len(access)))
    return grid, wall, works


def slope_clamp(h, where, k, max_iter=400):
    """h lowered (only in `where`) until no cell stands more than k x the distance above a neighbour: the lower
    Lipschitz envelope, by min-plus relaxation over the 8 neighbours (2 m and 2.83 m apart)."""
    j0, j1 = np.nonzero(where.any(axis=1))[0][[0, -1]]
    i0, i1 = np.nonzero(where.any(axis=0))[0][[0, -1]]
    j0, i0 = max(0, j0 - 2), max(0, i0 - 2)
    sub = h[j0:j1 + 3, i0:i1 + 3].copy()
    w = where[j0:j1 + 3, i0:i1 + 3]
    c1, c2 = k * STEP, k * STEP * math.sqrt(2.0)
    for _ in range(max_iter):
        p = np.pad(sub, 1, mode="edge")
        m = np.minimum.reduce([p[:-2, 1:-1] + c1, p[2:, 1:-1] + c1, p[1:-1, :-2] + c1, p[1:-1, 2:] + c1,
                               p[:-2, :-2] + c2, p[:-2, 2:] + c2, p[2:, :-2] + c2, p[2:, 2:] + c2])
        new = np.where(w, np.minimum(sub, m), sub)
        if np.array_equal(new, sub):
            break
        sub = new
    out = h.copy()
    out[j0:j1 + 3, i0:i1 + 3] = sub
    return out


# ------------------------------------------------------------------ gates
def slope(h):
    gz, gx = np.gradient(h.astype(np.float64), STEP)
    return np.hypot(gx, gz)


def report(base, out):
    xx, zz = grid()
    land = out > LAND_Z
    rep = {}
    pm = (np.hypot(xx - PLATEAU_C[0], zz - PLATEAU_C[1]) < PLATEAU_R) & land
    rep["plateau_p90_slope"] = [round(float(np.percentile(slope(base)[pm], 90)), 3),
                                round(float(np.percentile(slope(out)[pm], 90)), 3)]
    worst = 0.0
    changed = np.abs(out - (base + RAISE * (base > LAND_Z))) > 0.01   # the raise is uniform; judge what else changed
    for ax in (0, 1):                                    # (a step the SOURCE carries elsewhere is not this tool's)
        d = np.abs(np.diff(out, axis=ax))
        both = (land[1:, :] & land[:-1, :]) if ax == 0 else (land[:, 1:] & land[:, :-1])
        ch = (changed[1:, :] | changed[:-1, :]) if ax == 0 else (changed[:, 1:] | changed[:, :-1])
        worst = max(worst, float(d[both & ch].max()))
    rep["max_land_step_m"] = round(worst, 2)
    d_sea = distance_from(~land, COAST_BAND)
    band = land & (d_sea <= COAST_BAND) & mass_mask(xx, zz)
    worst_s = 0.0                                        # between two LAND cells: the waterline drop is a quay's
    for ax in (0, 1):
        d = np.abs(np.diff(out, axis=ax)) / STEP
        pair = (band[1:, :] & land[:-1, :]) | (band[:-1, :] & land[1:, :]) if ax == 0 else \
            (band[:, 1:] & land[:, :-1]) | (band[:, :-1] & land[:, 1:])
        worst_s = max(worst_s, float(d[pair].max()))
    rep["mountain_coast_max_slope"] = round(worst_s, 3)
    rep["snow_km2"] = round(float((land & (out > SNOW_Z + RAISE)).sum() * STEP * STEP / 1e6), 3)
    A, B = crest()
    cs = [out[int(round((p[1] - Z0) / STEP)), int(round((p[0] - X0) / STEP))]
          for p in (A + (B - A) * t for t in np.linspace(0, 1, 9))]
    rep["crest_z"] = [round(float(min(cs)), 2), round(float(max(cs)), 2)]
    rep["peak_m"] = round(float(out.max()), 1)
    rep["land_km2"] = [round(float((base > LAND_Z).sum() * 4e-6), 3), round(float(land.sum() * 4e-6), 3)]
    xs = np.nonzero(land.any(axis=0))[0]
    rep["land_x_extent"] = [X0 + STEP * xs.min(), X0 + STEP * xs.max()]
    # level = not steeper than it was, or under PLATEAU_LEVEL (a road grade): the v16 sample point was dead flat in the
    # base (0.00) and reads 0.047 after the x0.55 lowering's smoothing, which is level for anything that stands on it
    ok = (rep["plateau_p90_slope"][1] <= max(rep["plateau_p90_slope"][0] + 0.01, PLATEAU_LEVEL)
          and worst <= MAX_LAND_STEP
          and rep["mountain_coast_max_slope"] <= COAST_SLOPE + 0.01
          and SNOW_KM2[0] <= rep["snow_km2"] <= SNOW_KM2[1]
          and abs(rep["crest_z"][0] - PLATEAU_Z - RAISE) < 0.5 and abs(rep["crest_z"][1] - PLATEAU_Z - RAISE) < 0.5)
    return rep, ok


def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))

    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def preview(out, path, edits=None, base=None):
    """Land by height (contours every 50 m, snow white), sea by depth, the BASE coastline in yellow."""
    land = out > LAND_Z
    v = np.clip(out / PLATEAU_Z, 0, 1)[..., None]
    dep = np.clip(-out / 24.0, 0, 1)[..., None]
    rgb = np.array([70, 150, 190]) * (1 - dep) + np.array([18, 34, 60]) * dep
    col = np.array([70, 96, 60]) * (1 - v) + np.array([150, 130, 100]) * v
    rgb = np.where(land[..., None], col, rgb)
    rgb[land & (out > SNOW_Z)] = (236, 240, 246)
    band = land & ((np.floor(out / 50) % 2) != (np.floor(np.roll(out, 1, 0) / 50) % 2))
    rgb[band] = (40, 40, 34)
    if base is not None:
        b0 = base > LAND_Z
        edge = b0 & ~(np.roll(b0, 1, 0) & np.roll(b0, -1, 0) & np.roll(b0, 1, 1) & np.roll(b0, -1, 1))
        rgb[edge] = (255, 220, 120)
    png(path, rgb[::2, ::2].astype(np.uint8).copy())


def make_base(dump, out):
    """A raw full-world Terrain3D dump (the 245ed60 island) -> the committed base: seabed clamp + widen."""
    import island_widen_first_mountain as WM
    h = np.maximum(load(dump), SEABED)
    i0 = int(round((WM.X0 - X0) / STEP))
    j0 = int(round((-WM.Y0 - Z0) / STEP))
    w = h[j0:j0 + WM.NY, i0:i0 + WM.NX].copy()
    out_w, _w, _t = WM.widen(w)
    h[j0:j0 + WM.NY, i0:i0 + WM.NX] = out_w
    os.makedirs(os.path.dirname(out), exist_ok=True)
    h.astype(np.float32).tofile(out)
    print("island_reshape: base -> %s" % out)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "check", "base"])
    ap.add_argument("dump", nargs="?")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default=LAND)
    ap.add_argument("--land", default=LAND)
    ap.add_argument("--preview", default="")
    a = ap.parse_args(argv)
    if a.cmd == "base":
        make_base(a.dump, a.out if a.out != LAND else BASE)
        return 0
    base = load(a.base)
    if a.cmd == "build":
        out, _land, edits = reshape(base)
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        out.tofile(a.out)
        if a.preview:
            preview(out, a.preview, edits, base)
        rep, ok = report(base, out)
        print("island_reshape: -> %s\n%s\n%s" % (a.out, json.dumps(rep), "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    out = load(a.land)
    rep, ok = report(base, out)
    print("island_reshape: %s\n%s" % (json.dumps(rep), "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
