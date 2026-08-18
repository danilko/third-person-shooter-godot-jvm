#!/usr/bin/env python3
"""Tokyo 23-ku -> 6.048 km x 6.048 km playable map: the authored spatial compression.

This is the LEVEL DESIGN, not a solver.  compress.py solves band scales from feature
density (good for "squeeze this extract into a box"); a game map instead needs the
designer to nail tentpoles to chosen cells and let the *gaps* absorb the error.  So the
warp here is built from hand-placed CONTROL POINTS: (real EPSG:6677 metre) -> (game
metre).  Everything else -- roads, rail, coastline, PLATEAU features -- is pushed
through the same two monotonic piecewise-linear maps, so nothing tears or de-registers.

Two tiers, because one warp cannot do both jobs:

  TIER A  WARP    the Tokyo core (Nakano..Shinonome x Ueno..Haneda, ~12.5 x 20.1 km real)
                  is squeezed onto the 6.048 km square.  Continuous, monotonic, C0.
  TIER B  ANNEX   Okutama is 55 km west.  No warp survives that.  The mountain block is
                  CUT from the real world and RIGIDLY TRANSLATED (x, y, and a constant z
                  offset -- translation only, never scaled) into the NW corner, hidden
                  behind a ridge + tunnel portal so the seam is never in frame.

Game space matches blender/lib/world_grid.py exactly: X=east, Y=north, metres,
CENTRE-ORIGIN (the map spans [-3024, +3024] on both axes), 504 m districts on a 7 m cell.

    python3 tokyo6km_layout.py --out build/tokyo6km        # layout.json + the text matrix

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import json
import math
import os

# ---------------------------------------------------------------------------
# grid — mirrors blender/lib/world_grid.py (CELL/DISTRICT unchanged, GRID_N 6 -> 12)
# ---------------------------------------------------------------------------

CELL = 7.0
DISTRICT = 504.0          # 72 cells — the proven streaming chunk size, deliberately kept
GRID_N = 12               # 6 -> 12: the map doubles, the chunk does not
WORLD = DISTRICT * GRID_N  # 6048 m
ORIGIN = WORLD / 2.0      # 3024 — centre-origin, same convention as world_grid.to_world()


def to_world(v):
    return v - ORIGIN


def cell_bounds(gx, gy):
    return (to_world(gx * DISTRICT), to_world(gy * DISTRICT),
            to_world((gx + 1) * DISTRICT), to_world((gy + 1) * DISTRICT))


def cell_center(gx, gy):
    return (to_world((gx + 0.5) * DISTRICT), to_world((gy + 0.5) * DISTRICT))


# ---------------------------------------------------------------------------
# TIER A — the authored warp
# ---------------------------------------------------------------------------

class Warp:
    """Monotonic piecewise-linear real->game map through authored control points.

    Outside the first/last control point the end segment's slope is extrapolated, so a
    PLATEAU feature just off the edge still lands somewhere sane instead of clamping
    onto the boundary and piling up.
    """

    def __init__(self, points, axis):
        self.axis = axis
        self.pts = sorted(points, key=lambda p: p[0])
        for (r0, g0), (r1, g1) in zip(self.pts, self.pts[1:]):
            if r1 <= r0 or g1 <= g0:
                raise ValueError(f"{axis} control points must be strictly increasing "
                                 f"in BOTH real and game: {(r0, g0)} -> {(r1, g1)}")

    def __call__(self, v):
        p = self.pts
        if v <= p[0][0]:
            s = self.slope(0)
            return p[0][1] + (v - p[0][0]) * s
        if v >= p[-1][0]:
            s = self.slope(len(p) - 2)
            return p[-1][1] + (v - p[-1][0]) * s
        for i in range(len(p) - 1):
            if p[i][0] <= v <= p[i + 1][0]:
                t = (v - p[i][0]) / (p[i + 1][0] - p[i][0])
                return p[i][1] + t * (p[i + 1][1] - p[i][1])
        raise AssertionError

    def slope(self, i):
        (r0, g0), (r1, g1) = self.pts[i], self.pts[i + 1]
        return (g1 - g0) / (r1 - r0)

    def slope_at(self, v):
        """Local scale (d game / d real) at `v` — the jacobian of the warp.

        This is what `block_retention` means numerically: at 0.12 the band keeps an
        eighth of its length, so it can hold an eighth of its cross-streets.
        """
        p = self.pts
        if v <= p[0][0]:
            return self.slope(0)
        if v >= p[-1][0]:
            return self.slope(len(p) - 2)
        for i in range(len(p) - 1):
            if p[i][0] <= v <= p[i + 1][0]:
                return self.slope(i)
        return self.slope(0)

    def segments(self):
        out = []
        for i in range(len(self.pts) - 1):
            (r0, g0), (r1, g1) = self.pts[i], self.pts[i + 1]
            out.append(dict(real_from=r0, real_to=r1, game_from=g0, game_to=g1,
                            real_len_m=round(r1 - r0, 1), game_len_m=round(g1 - g0, 1),
                            scale=round(self.slope(i), 4),
                            deleted_m=round((r1 - r0) - (g1 - g0), 1)))
        return out

    def to_json(self):
        return dict(axis=self.axis,
                    control_points=[[round(r, 1), round(g, 1)] for r, g in self.pts],
                    segments=self.segments())


# Real anchors, EPSG:6677 (JGD2011 / Japan Plane Rectangular CS IX), X=east Y=north.
# Projected from WGS84/JGD2011 lon-lat with pyproj (see README "Projection").
REAL = {
    "kabukicho":      (-11741.1, -33963.6),   # Shinjuku neon core
    "shinjuku_stn":   (-12022.3, -34429.2),
    "shibuya":        (-12026.8, -37768.6),
    "nakano":         (-15168.9, -32638.2),
    "koenji":         (-16616.8, -32713.3),
    "ikebukuro":      (-11156.9, -30003.7),
    "yotsuya":        (-9352.8,  -34831.8),
    "ichigaya":       (-8836.2,  -34200.0),
    "palace":         (-7289.2,  -34922.5),
    "tokyo_tower":    (-7961.6,  -37873.0),
    "roppongi":       (-9228.7,  -37416.9),
    "tokyo_stn":      (-5995.2,  -35367.2),
    "nihonbashi":     (-5325.2,  -35079.2),
    "kanda":          (-5641.4,  -34191.5),
    "akihabara":      (-5450.9,  -33459.4),
    "ueno":           (-5097.0,  -31751.1),
    "asakusa":        (-3323.6,  -31641.0),
    "ginza":          (-5995.9,  -36421.2),
    "shimbashi":      (-6765.8,  -36997.5),
    "tsukiji":        (-5670.4,  -37120.3),
    "kachidoki":      (-5100.6,  -37941.6),
    "toyosu":         (-3380.4,  -38275.3),
    "shinonome":      (-3018.6,  -39384.8),
    "ariake":         (-3743.5,  -40494.0),
    "rainbow_br":     (-6360.8,  -40303.9),
    "odaiba":         (-5329.0,  -41380.7),
    "shinagawa":      (-8571.5,  -41211.7),
    "oi_futo":        (-6826.3,  -45040.7),
    "omori":          (-9545.4,  -45637.3),
    "keihinjima":     (-6465.4,  -47148.8),
    "showajima":      (-8097.0,  -47369.4),
    "kamata":         (-10636.4, -48620.4),
    "haneda_rwy_n":   (-4454.3,  -49257.9),
    "haneda_t1":      (-4336.8,  -50001.3),
    "tamagawa_mouth": (-6649.9,  -51586.3),
    "haneda_rwy_s":   (-4564.4,  -51809.5),
    # intermediate anchors — these exist so a traced polyline CURVES like the real
    # alignment instead of chording across three districts (see the preview: a 3-point
    # Yamanote drew a giant V across the north).
    "iidabashi":      (-8002.6,  -33058.0),
    "takadanobaba":   (-11720.2, -31855.7),
    "sugamo":         (-8515.0,  -29562.9),
    "nishi_nippori":  (-6009.5,  -29731.3),
    "ochanomizu":     (-6147.7,  -33348.0),
    "hamamatsucho":   (-6911.6,  -38240.0),
    "shiodome":       (-6639.3,  -37275.0),
    "tennozu":        (-7548.6,  -41933.8),
    "oimachi":        (-8954.4,  -43674.3),
    "gotanda":        (-9495.6,  -41432.7),
    "osaki":          (-9487.3,  -42187.1),
    "meguro":         (-10654.0, -40610.4),
    "ebisu":          (-11168.5, -39189.7),
    "anamori":        (-7918.2,  -50143.1),
    # TIER B source (annexed, NOT warped — listed for provenance only)
    "okutama_stn":    (-66634.3, -20906.6),
    "kazahari_toge":  (-66283.5, -28387.4),
    "mt_mitake":      (-61774.5, -23859.9),
    "ome":            (-53273.1, -23327.0),
}

# --- X control points (west -> east). Chosen so the four city tentpoles land on the
#     district centres they were assigned in the matrix below.
WARP_X = Warp([
    (REAL["nakano"][0],     -2100.0),   # outer residential belt, gx~1.8
    (REAL["kabukicho"][0],   -756.0),   # SHINJUKU -> gx 4 centre
    (REAL["yotsuya"][0],     -250.0),   # Yotsuya buffer -> gx 5
    (REAL["palace"][0],       250.0),   # Palace / Akasaka -> gx 6
    (REAL["tokyo_stn"][0],    756.0),   # TOKYO STATION -> gx 7 centre
    (REAL["akihabara"][0],   1260.0),   # AKIHABARA -> gx 8 centre
    (REAL["haneda_t1"][0],   1900.0),   # Haneda terminal column
    (REAL["toyosu"][0],      2500.0),   # Toyosu / Harumi waterfront
    (REAL["shinonome"][0],   2861.0),   # east shore (1.00 — uncompressed)
], "x")

# --- Y control points (south -> north).
WARP_Y = Warp([
    (REAL["haneda_rwy_s"][1],      -3010.0),   # south map edge (runway south apron)
    (REAL["haneda_t1"][1],         -2600.0),   # HANEDA terminal
    (REAL["haneda_rwy_n"][1],      -2400.0),
    (REAL["keihinjima"][1],        -2150.0),   # Keihin industrial belt
    (REAL["oi_futo"][1],           -1900.0),   # Oi wharf
    (REAL["odaiba"][1],            -1450.0),   # Odaiba
    (REAL["shinagawa"][1],         -1430.0),
    (REAL["rainbow_br"][1],        -1330.0),   # Rainbow Bridge
    (REAL["tokyo_tower"][1],        -930.0),
    (REAL["shibuya"][1],            -900.0),
    (REAL["ginza"][1],              -520.0),
    (REAL["tokyo_stn"][1],          -260.0),   # TOKYO STATION
    (REAL["kabukicho"][1],           150.0),   # SHINJUKU
    (REAL["akihabara"][1],           330.0),   # AKIHABARA
    (REAL["ueno"][1],               1250.0),   # Ueno / north rim of the core
    # North of Ueno the real city is its most homogeneous — mile after mile of the same
    # mid-rise ward. It is the cheapest thing on the map to delete, so this last band
    # takes the hardest collapse (0.14) and the whole north rail complex stays inside
    # gy8-9 instead of sprawling into the rural/mountain rows.
    (REAL["ikebukuro"][1],          1500.0),   # north residential
], "y")


def warp(pt):
    return (WARP_X(pt[0]), WARP_Y(pt[1]))


def game(name):
    return warp(REAL[name])


# ---------------------------------------------------------------------------
# TIER B — the annexed mountain block (rigid translation, no scale on any axis)
# ---------------------------------------------------------------------------

# Real 2016 x 2016 m window taken from the Okutama valley 1 km south of Okutama
# station, so the block carries the Tama gorge floor along its north edge and the
# ridges climbing away south — valley AND summit inside one window.  (Kazahari touge
# itself is 7.5 km further south; it is the *profile reference* for the authored pass
# road below — grade and hairpin radius — not literal annexed geometry.)
MTN_SRC_CENTER = (-66634.3, -21900.0)
MTN_SIZE = 2016.0                                  # 4 x 4 districts
MTN_DST_CELLS = (0, 8, 3, 11)                      # gx0..gx3, gy8..gy11 (NW corner)
MTN_DST_CENTER = (-2016.0, 2016.0)
MTN_Z_OFFSET = -280.0    # valley floor 340 m T.P. -> 60 m game; ridge ~900 -> ~620 m.
                         # A CONSTANT SUBTRACTION. Slope, relief and road gradient are
                         # untouched — that is the whole point of annexing instead of
                         # warping: the touge keeps real hairpin radii and real grade.

MTN_XFORM = dict(
    kind="rigid_translate",
    source_crs="EPSG:6677",
    source_window_center=list(MTN_SRC_CENTER),
    source_window_size_m=MTN_SIZE,
    dx=round(MTN_DST_CENTER[0] - MTN_SRC_CENTER[0], 1),
    dy=round(MTN_DST_CENTER[1] - MTN_SRC_CENTER[1], 1),
    dz=MTN_Z_OFFSET,
    scale=1.0,
)


def mtn(pt):
    """Real -> game for anything inside the annexed mountain window."""
    return (pt[0] + MTN_XFORM["dx"], pt[1] + MTN_XFORM["dy"])


# ---------------------------------------------------------------------------
# district matrix — 12 rows printed NORTH (gy=11) -> SOUTH (gy=0)
# ---------------------------------------------------------------------------

# Themes reuse world_grid.THEMES keywords so build_world.py needs no new vocabulary.
# `void` = permanently no district (open water / airfield apron owned by a hero piece).
# REDUCED FOOTPRINT (2nd pass). The first matrix built all 144 districts, and 60 of them
# were `resid` — the most expensive thing per unit of player interest on the whole map.
# Streaming cost is paid per BUILT district, so the cheapest optimisation available is to
# not build one. Three moves, all visible below:
#   * `void`   28 cells — open water and off-map. Nothing streams, nothing is authored.
#   * `mtn`    grown to a continuous NW massif that also forms the north + west EDGE, so
#              the boundary is terrain the player cannot climb, not an invisible wall.
#   * `resid`  cut 60 -> 33 and pushed to a single ring one district deep. Residential is
#              the taper between the city and the edge; it is not a destination, so it
#              never needs two districts of depth.
# Built cells drop 144 -> 116, and the *city* core is untouched.
MAP_ROWS = [
    #  gx: 0        1        2        3        4        5        6        7        8        9        10       11
    "   void     mtn      mtn      snow     mtn      mtn      rural    rural    rural    void     void     void   ",  # gy=11
    "   mtn      mtn      mtn      mtn      mtn      rural    rural    resid    rural    rural    void     void   ",  # gy=10
    "   mtn      mtn      mtn      mtn      rural    rural    resid    resid    resid    rural    rural    void   ",  # gy=9
    "   mtn      mtn      rural    rural    resid    resid    resid    resid    resid    resid    rural    rural  ",  # gy=8
    "   rural    rural    resid    resid    resid    resid    city     city     resid    resid    resid    rural  ",  # gy=7
    "   rural    resid    resid    resid    city     city     city     city     city     city     resid    resid  ",  # gy=6  SHINJUKU gx4 / AKIHABARA gx8
    "   rural    resid    resid    city     city     city     city     city     city     city     resid    resid  ",  # gy=5  TOKYO STN gx7
    "   rural    resid    resid    resid    city     city     city     city     city     city     harbor   harbor ",  # gy=4
    "   rural    resid    resid    resid    resid    city     city     city     harbor   harbor   harbor   harbor ",  # gy=3
    "   void     resid    resid    resid    resid    resid    resid    harbor   harbor   harbor   harbor   void   ",  # gy=2
    "   void     void     resid    industry industry industry industry industry harbor   harbor   harbor   void   ",  # gy=1  HANEDA apron gx8-10
    "   void     void     void     industry industry industry industry industry harbor   harbor   void     void   ",  # gy=0  HANEDA runway gx8-10
]


def theme_at(gx, gy):
    return MAP_ROWS[GRID_N - 1 - gy].split()[gx]


def matrix_text():
    """The text grid the design doc quotes."""
    lines = []
    head = "        " + "".join(f"gx{gx:<7d}" for gx in range(GRID_N))
    lines.append(head)
    for gy in range(GRID_N - 1, -1, -1):
        cells = MAP_ROWS[GRID_N - 1 - gy].split()
        lines.append(f"gy{gy:<2d} |  " + "".join(f"{c[:7]:<7s}" for c in cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# tentpoles — the eight things the map exists to contain
# ---------------------------------------------------------------------------

def tentpoles():
    """(id, label, game xy, district cell, footprint in districts, source)."""
    T = []

    def add(pid, label, xy, cells, foot, src, note=""):
        gx = int((xy[0] + ORIGIN) // DISTRICT)
        gy = int((xy[1] + ORIGIN) // DISTRICT)
        T.append(dict(id=pid, label=label,
                      game_xy=[round(xy[0], 1), round(xy[1], 1)],
                      district=[gx, gy], anchor_cells=cells,
                      footprint_districts=foot, source=src, note=note))

    add("shinjuku", "Shinjuku / Kabukicho", game("kabukicho"),
        [[3, 6], [5, 7]], [3, 2], "PLATEAU 13104 shinjuku-ku 2023",
        "neon vertical tentpole; highest building density, tightest alleys")
    add("tokyostation", "Tokyo Station / Marunouchi", game("tokyo_stn"),
        [[6, 4], [8, 6]], [3, 3], "PLATEAU 13101 chiyoda-ku 2025 (LOD2/3 tran)",
        "rail hub; Shinkansen viaduct terminus; C1 loop wraps its west side")
    add("akihabara", "Akihabara / Kanda", game("akihabara"),
        [[8, 6], [9, 7]], [2, 2], "PLATEAU 13101 chiyoda-ku 2025",
        "elevated-line tentpole: Yamanote+Chuo viaducts, under-guard alley strip")
    add("haneda", "Haneda Airport", (1980.0, -2500.0),
        [[8, 0], [11, 2]], [4, 3], "PLATEAU 13111 ota-ku 2025",
        "warp OVERRIDDEN: single 1300 m runway, 3 real runways deleted (see runway())")
    add("harbor", "Tokyo Bay waterfront / Odaiba", game("odaiba"),
        [[9, 2], [11, 4]], [3, 3], "PLATEAU 13108 koto-ku + 13103 minato-ku 2025",
        "Rainbow Bridge + Wangan bayshore run")
    add("industry", "Keihin industrial belt", game("keihinjima"),
        [[4, 0], [8, 1]], [5, 2], "PLATEAU 13111 ota-ku 2025",
        "Oi wharf / Keihinjima / Showajima: gantries, tank farms, truck traffic")
    add("mountain", "Okutama massif (annexed)", (-2016.0, 2016.0),
        [[0, 8], [3, 11]], [4, 4], "PLATEAU 13_tokyo prefecture 2023 (DEM, NOT YET EXTRACTED)",
        "TIER B rigid translate; keeps real slope + real hairpin radii")
    add("touge", "Okutama touge pass", (-1450.0, 1750.0),
        [[1, 9], [3, 11]], [2, 2], "authored on annexed DEM; Kazahari touge as profile ref",
        "the mountain tongue: switchback climb, the map's one true driving set-piece")
    return T


def runway():
    """Haneda RWY A (16R/34L) analogue — the one place the warp is overridden.

    Real 16R/34L is 3000 m on a 157/337 true heading.  Warping it would leave a 400 m
    stub; SCALING it would break the one rule this whole pipeline exists for.  So the
    middle is DELETED and a 1300 m runway is authored at the true heading — a 1.3 km
    drag strip, which is what the airport is actually for in a driving game.
    """
    # Runway A is the WESTERNMOST strip at Haneda; T1/T2 sit east of it — preserved here
    # (runway at gx8-9, terminal apron at gx10-11) so the airport reads the right way round.
    length, heading = 1300.0, 157.0
    cx, cy = 1500.0, -2380.0
    a = math.radians(heading)
    dx, dy = math.sin(a), math.cos(a)
    n = (cx - dx * length / 2, cy - dy * length / 2)
    s = (cx + dx * length / 2, cy + dy * length / 2)
    return dict(id="haneda_rwy_34L", length_m=length, width_m=60.0,
                true_heading_deg=heading,
                north_end=[round(n[0], 1), round(n[1], 1)],
                south_end=[round(s[0], 1), round(s[1], 1)],
                real_length_m=3000.0,
                method="middle deleted, ends authored — never scaled")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/tokyo6km")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    print(matrix_text())
    print()
    for t in tentpoles():
        print(f"  {t['id']:14s} {t['game_xy']} district {t['district']}")
