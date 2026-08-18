#!/usr/bin/env python3
"""Tokyo-Bay Island v3 — geometry, in GAME METRES (X east, Y north, centre origin).

Plan A's fictional island, condensed to the original ~2 km proposal and re-planned as a
clean north->south transect:

    MOUNTAIN -> FARMLAND -> RESIDENTIAL -> NEON (three centres) -> HARBOUR / BAY

Frame: 2016 x 2016 m = 4 x 4 districts of 504 m (world_grid.GRID_N = 4). The grid maths is
GRID_N-parametric, so this is a constant change, not a pipeline change.

Consumed by tools/island_v3_plates.py — no drawing lives here.
"""

from __future__ import annotations

import math
import random

# --------------------------------------------------------------------------- grid
DISTRICT = 504.0
GRID_N = 4
WORLD = DISTRICT * GRID_N      # 2016
ORIGIN = WORLD / 2.0           # 1008

# --------------------------------------------------------------------------- land
# Organic north/west coast; straight south edges where land is reclaimed.
MAIN_BASE = [
    (-40, 962), (200, 940), (420, 880), (610, 780), (742, 640), (824, 470),
    (872, 275), (886, 80), (862, -110), (800, -250), (700, -350), (560, -430),
    (430, -470), (300, -500), (150, -520), (-40, -545), (-230, -570), (-420, -560),
    (-580, -510), (-712, -420), (-812, -290), (-872, -110), (-890, 110), (-858, 340),
    (-790, 560), (-672, 748), (-500, 878), (-280, 945),
]
# Reclaimed port peninsula — fused to the mainland by a wide land neck (drive straight in).
HARBOUR = [(-380, -520), (140, -500), (140, -880), (-120, -930), (-380, -845)]
# Offshore reclaimed airport island, south-east.
AIRPORT = [(380, -990), (960, -990), (960, -700), (560, -700), (380, -780)]

def fractalize(poly, iters=3, amp=30.0, decay=0.55, seed=5):
    """Midpoint displacement along each edge — multi-scale headlands and coves.

    The SMOOTH polygon stays the design skeleton (the ring road offsets from it, zones are
    authored against it); only the drawn/collided coastline is fractal, so detail can be
    retuned without moving a single road.
    """
    rng = random.Random(seed)
    pts = list(poly)
    for it in range(iters):
        a = amp * (decay ** it)
        out = []
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            out.append(p)
            dx, dy = q[0] - p[0], q[1] - p[1]
            L = math.hypot(dx, dy) or 1.0
            d = rng.uniform(-a, a) * min(1.0, L / 110.0)
            out.append(((p[0] + q[0]) / 2 - dy / L * d, (p[1] + q[1]) / 2 + dx / L * d))
        pts = out
    return pts


MAIN = fractalize(MAIN_BASE)

# Offshore rocks — scenery and boat targets only; deliberately NOT in LAND, so they carry
# no roads, no buildings and no streaming cost.
ISLETS = [
    [(-980, 690), (-930, 716), (-902, 686), (-936, 652)],
    [(966, 512), (1000, 536), (982, 574), (944, 552)],
    [(408, -1078), (452, -1064), (446, -1030), (404, -1042)],
]

LAND = [MAIN, HARBOUR, AIRPORT]

# THE BAY — a drowned river mouth (ria) cutting ~850 m north into the city. It is the
# river's own outlet, so one water feature does everything: snowmelt spine, city divider,
# harbour, and the reason the main arterial needs a 300 m bridge.
BAY = [(176, -148), (298, -142), (352, -262), (368, -436), (352, -628), (330, -1010),
       (86, -1010), (112, -628), (130, -436), (148, -262)]
WATER = [BAY]            # LAGOON appended below, once defined

# --------------------------------------------------------------------- point tests
def inside(poly, x, y):
    n, ins = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def on_land(x, y):
    if any(inside(p, x, y) for p in WATER):
        return False
    return any(inside(p, x, y) for p in LAND)


def ellipse(cx, cy, rx, ry, n=44, rot=0.0):
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + ex * c - ey * s, cy + ex * s + ey * c))
    return out


def pull_ashore(cx, cy, pts):
    """Shrink each point toward the centre until it lands — clips a band to the coast."""
    out = []
    for (x, y) in pts:
        for k in range(44):
            t = 1.0 - k * 0.023
            qx, qy = cx + (x - cx) * t, cy + (y - cy) * t
            if on_land(qx, qy):
                out.append((qx, qy))
                break
        else:
            out.append((cx, cy))
    return out


def plen(pts, close=False):
    q = pts + [pts[0]] if close else pts
    return sum(math.dist(a, b) for a, b in zip(q, q[1:]))


# ------------------------------------------------------------------------- terrain
# Main massif (north) + a SPUR ridge running south down the west side, ending in a hill
# directly behind the western neon centre — the "mountain on the neon side".
MASSIF = dict(cx=-300, cy=790, bands=[(470, 250, "+120"), (340, 178, "+240"),
                                      (215, 112, "+320 snow"), (120, 62, "peak +380")])
SPUR = dict(cx=-640, cy=330, bands=[(255, 330, "+80"), (150, 205, "+140 hill")],
            rot=math.radians(-14))

PASS = (-452, 690)          # touge summit-of-drivable, +220
PEAK = (-300, 800)          # +380, scenery only
SPUR_TOP = (-648, 258)      # +140, city shrine

# ---------------------------------------------------------------------- green void
# Castle park — the Imperial Palace shrunk to a 260 x 210 m castle (v2's 520 x 440 would
# be a quarter of this map). Still does the same job: every road bends around it.
CASTLE = [(-215, 190), (-60, 200), (-15, 150), (-10, -5), (-70, -55), (-205, -48),
          (-248, 10), (-250, 130)]
MOAT = [(-248, 218), (-48, 230), (12, 172), (18, -20), (-58, -84), (-218, -76),
        (-282, -4), (-284, 142)]
SHIBA_PK = [(268, -258), (410, -250), (416, -140), (272, -148)]   # temple + tower park
SHRINE_PK = [(-742, 330), (-596, 348), (-566, 452), (-700, 470)]  # forest shrine, spur foot
UENO_PK = []
PARKS = (MOAT, SHIBA_PK, SHRINE_PK)

# ---------------------------------------------------------------------------- river
# One spine: snowmelt -> paddies -> residential -> becomes the harbour inlet at the sea.
RIVER = [(-320, 770), (-190, 668), (-30, 610), (140, 572), (300, 520), (392, 430),
         (402, 300), (360, 158), (300, 18), (262, -120), (238, -146)]

# Shinano-style: the river is the city's organising line, not scenery at the edge.
# Neon A (old town, west bank) and Neon B (new centre, east bank) face each other across
# it; one multi-arch stone bridge is the hero crossing and the natural chokepoint.
ARCH_BRIDGE = ((236, -46), (330, -52))          # 94 m, Bandai-bashi analogue, upstream

# Coastal pine windbreak (海岸松林) inside the ocean-facing dune line — the single
# cheapest "Sea of Japan coast" signal there is, and a continuous occluder wall.
PINE = [(872, 275), (824, 470), (742, 640), (610, 780), (556, 740), (672, 618),
        (750, 452), (800, 268)]

# Remnant lagoon (潟) stranded among the paddies — what the drained back-swamp left.
LAGOON = [(298, 646), (432, 664), (474, 592), (398, 538), (296, 562)]
WATER.append(LAGOON)

# ----------------------------------------------------------------------------- T1
def chamfer(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1),
            (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]


LOOP = chamfer(-560, -450, 500, 290, 115)        # flagship circuit, closed
# Airport access is a RAMP off the loop beside S3 — not a second route. It leaves the
# south-east chamfer, hugs the coast, and turns straight onto the bridge head.
AIRPORT_RAMP = [(500, -335), (620, -306), (722, -266), (788, -214), (800, -180)]
AIRPORT_ROAD = [(905, -720), (820, -800), (700, -848)]   # continues on the island
PORTSPUR = [(-150, -450), (-190, -570), (-215, -700), (-230, -810)]
WESTRAD = [(-560, 60), (-660, 130), (-742, 236), (-790, 380), (-800, 520)]
TUNNEL = (-800, 520)
TOUGE = [(-780, 592), (-620, 626), (-724, 668), (-566, 700), (-668, 740), (-520, 762),
         (-452, 690)]

# ------------------------------------------------------------------- T2 arterials
# The white lanes are AUTHORED, not a clipped lattice. Rule: every arterial is
# end-to-end and terminates on the RING or on another arterial — never in mid-air.
# RING is computed as an inward offset of the coastline (see plates.offset_inward).
RING_INSET = 62.0

ARTERIALS = [
    # N-S trunk: port -> Neon A -> castle -> residential -> farmland -> mountain foot
    ("Chuo-dori", [(-96, -598), (-70, -430), (-58, -300), (-30, -120), (26, 62),
                   (20, 250), (52, 430), (74, 600), (96, 792)]),
    # E-W trunk: west coast -> Neon C -> Neon A -> ARCH BRIDGE -> Neon B -> east coast
    ("Rinkai-dori", [(-806, -128), (-620, -150), (-430, -166), (-160, -140), (40, -80),
                     (236, -46), (330, -52), (500, -96), (680, -104), (818, -76)]),
    # residential cross-street
    ("Yamate-dori", [(-800, 214), (-520, 244), (-200, 236), (140, 228), (460, 218),
                     (700, 208), (812, 196)]),
    # farmland cross-street, bends around the lagoon
    ("Nogyo-michi", [(-556, 556), (-300, 604), (60, 620), (270, 700), (470, 660),
                     (620, 540), (742, 456)]),
    # east N-S: coastal station -> Neon B -> BAY BRIDGE -> port
    ("Hama-dori", [(804, 336), (762, 130), (706, -60), (620, -206), (500, -330),
                   (420, -400), (366, -440), (124, -424), (20, -486), (-96, -566)]),
    # west N-S: ring -> Neon C -> shrine -> tunnel approach
    ("Nishi-dori", [(-800, -214), (-660, -120), (-624, 60), (-654, 240), (-676, 400),
                    (-742, 512)]),
    # port distributor on the reclaimed peninsula
    ("Port road", [(-96, -560), (-180, -640), (-250, -740), (-300, -860)]),
]

# ---------------------------------------------------------------------------- rail
RAIL_MAIN = [(838, 300), (800, 120), (720, -30), (600, -140), (430, -205),
             (240, -240), (60, -230), (-120, -190), (-300, -140), (-470, -60),
             (-600, 90), (-660, 300), (-680, 470), (-760, 560)]
RAIL_BRANCH = [(-120, -190), (-90, 60), (-40, 260), (60, 430), (200, 540)]
RAIL_AIRPORT = [(800, -180), (905, -720), (820, -840)]

# ------------------------------------------------------------------------- bridges
BAY_BRIDGE = ((124, -424), (366, -440))                      # 243 m, the main crossing
AIRPORT_BRIDGE = ((800, -180), (905, -720))                  # 550 m, double-deck
RUNWAY = ((430, -930), (930, -778))                          # 522 x 45 m

# ------------------------------------------------------------------ urban envelopes
# name, rects, frontage, depth, perimeter retention, interior infill, colour
ZONES = [
    # three separated neon centres — not one blob
    ("neonA", [(-260, -430, 150, 30)],       6, 12, 0.92, 0.34, "#8b8577"),   # main core
    ("neonB", [(376, -330, 700, 60)],        6, 12, 0.86, 0.26, "#8b8577"),   # electric town
    ("neonC", [(-720, -300, -380, 90)],      7, 13, 0.80, 0.20, "#8b8577"),   # hillside strip
    ("resid", [(-830, 40, 620, 440), (600, 60, 850, 320)],
                                             8,  9, 0.80, 0.16, "#b0ab99"),
    ("farm",  [(-260, 420, 620, 760),                       # valley paddies
               (600, 60, 880, 520),                         # stretches to the ocean
               (-620, 500, -240, 730)],                     # terraces on the flank
                                            14, 11, 0.30, 0.00, "#a9af92"),
    ("port",  [(-380, -930, 140, -500)],    30, 40, 0.85, 0.10, "#9d9686"),
    ("air",   [(380, -990, 960, -700)],     26, 34, 0.45, 0.00, "#9d9686"),
]

DANCHI_BEARING = 18.0      # locked sun angle — every slab shares it
BLOCK = 168.0
STREET = 14.0

# --------------------------------------------------------------------- district map
# gy3 (north) -> gy0 (south); verified against measured land fraction, see plates output.
MATRIX = [
    ["void",   "mtn",    "rural",  "rural"],    # gy3
    ["mtn",    "resid",  "resid",  "rural"],    # gy2
    ["city",   "CITY",   "city",   "rural"],    # gy1
    ["void",   "harbor", "harbor", "harbor"],   # gy0
]

THEME = {
    "mtn":    ("#9DB47F", "Mountain / touge"),
    "rural":  ("#C6D5A6", "Farmland"),
    "resid":  ("#DCCFA8", "Residential"),
    "city":   ("#C99C86", "Neon (3 centres)"),
    "harbor": ("#8FA6A0", "Harbour / port / airport"),
    "void":   (None, "Void"),
}

# ------------------------------------------------------------------------ landmarks
# label, x, y, kind
LANDMARKS = [
    ("Tower — 333 m",            330, -196, "asset"),
    ("Temple + park",            300, -238, "kit"),
    ("Castle + moat",           -120,   78, "kit"),
    ("Central station",          -60, -222, "kit"),
    ("Electric town",            470, -140, "kit"),
    ("Hillside strip",          -560, -120, "kit"),
    ("Shrine at the foot",      -654,  398, "kit"),
    ("Summit shrine (okumiya)", -648,  258, "kit"),
    ("Pass shrine",             -452,  690, "kit"),
    ("Arch bridge — 91 m",       250, -182, "asset"),
    ("Lagoon",                   386,  600, ""),
    ("Bay bridge — 166 m",       223, -406, "asset"),
    ("Airport bridge — 550 m",   852, -450, "asset"),
    ("Airport terminal",         700, -880, "asset"),
    ("Container port",          -230, -740, ""),
    ("Coastal station",          800,  330, "kit"),
    ("Tunnel portal",           -800,  520, "asset"),
]

SECTORS = [("S1", -30, 290, "moat straight — start/finish"),
           ("S2", 500, 0, "electric-town esses"),
           ("S3", 330, -450, "port hairpin — braking point"),
           ("S4", -230, -450, "bayshore sweep, tower on the left"),
           ("S5", -560, -180, "hillside climb — blind crest"),
           ("S6", -560, 180, "spur descent into the moat")]
