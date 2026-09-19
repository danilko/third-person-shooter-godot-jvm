"""Landmark buildings and structures for kits/library (managed like every other building; `landmark` is only a
tag in building_types.json). BASE models (imported by library_procedural.build_all). Ours, CC0.

Each is a simplified massing at the real building's key dimensions, not traced geometry. The dimensions come from
PLATEAU MEASUREMENTS (footprint rectangle, height, spacing; measured 2026-09-18 from the precinct extracts before they
were deleted) and from public record where PLATEAU has nothing (Tokyo Tower's lattice). The numbers are written here
so they need no data file. A modeller refines these by hand in library.blend; toon-style flat palette materials.

Frame as every library piece: Z up, origin at the footprint centre on the ground (water line for the bridge),
the main facade facing -Y.
"""
import math


def shell(b, x0, x1, y0, y1, h, t, wall, openings=None, floor="MI_Terrazzo", ceiling="MI_Plaster", side_mats=None):
    """A hollow room: a floor slab with its top at 0, four walls `t` thick inside [x0,x1] x [y0,y1] up to `h`, a
    ceiling slab under `h`. `openings` = {side: [(centre along the side, width, height)]}, sides front (-Y),
    back (+Y), left (-X), right (+X); a wall is built as the boxes around its openings. `side_mats` overrides a
    side's material (a glass front)."""
    openings = openings or {}
    side_mats = side_mats or {}
    b.box((x0, y0, -0.1), (x1, y1, 0.0), floor)
    b.box((x0, y0, h - 0.4), (x1, y1, h), ceiling)
    runs = {"front": (x0, x1), "back": (x0, x1), "left": (y0, y1), "right": (y0, y1)}
    for side, (a0, a1) in runs.items():
        mat = side_mats.get(side, wall)
        cuts = sorted(openings.get(side, []))
        cursor = a0
        pieces = []
        for c, w, oh in cuts:
            pieces.append((cursor, c - w / 2, 0.0, h))
            pieces.append((c - w / 2, c + w / 2, oh, h))
            cursor = c + w / 2
        pieces.append((cursor, a1, 0.0, h))
        for p0, p1, z0, z1 in pieces:
            if p1 - p0 < 1e-6 or z1 - z0 < 1e-6:
                continue
            if side == "front":
                b.box((p0, y0, z0), (p1, y0 + t, z1), mat)
            elif side == "back":
                b.box((p0, y1 - t, z0), (p1, y1, z1), mat)
            elif side == "left":
                b.box((x0, p0, z0), (x0 + t, p1, z1), mat)
            else:
                b.box((x1 - t, p0, z0), (x1, p1, z1), mat)


# ── Rainbow Bridge (レインボーブリッジ) ────────────────────────────────────────────────────────────────────────
# PLATEAU (rainbowbridge_full, 231 bridge parts): towers 575 m apart with tops at 127.8 m; side spans 115 m to the
# anchorages; main cables sagging to 69 m at midspan; the double deck's underside at ~43 m. Public record: a
# two-level suspension bridge, the Shuto expressway above, road + Yurikamome + walkways below, white.
RB_MAIN = 575.0
RB_SIDE = 115.0
# The ROAD LEVELS are this island's (PLAN.md 3.8): the lower deck carries the airport road (`kuko_dori`, its deck at
# 24 m) and, later, the metro; the upper deck is reserved for the expressway spur from C1 (the loop JCT template).
# Everything vertical is derived from them with the real bridge's proportions (PLATEAU: towers 75.3 m above the upper
# deck, cables sagging to 16.5 m above it), so the bridge fits any crossing by changing these two numbers.
RB_ROAD_LOWER = 24.0
RB_ROAD_UPPER = 32.0
RB_DECK_TOP = RB_ROAD_UPPER
RB_DECK_BOTTOM = RB_ROAD_LOWER - 1.5
RB_TOWER_TOP = RB_ROAD_UPPER + 75.3
RB_SAG = RB_ROAD_UPPER + 16.5
RB_BASE_Z = -30.0         # towers and anchorages stand on the seabed (-24 m), not on the water
RB_HALF_W = 15.5          # the side trusses stand here: the clear ROAD CORRIDOR is |y| < 15 (a 29 m T2 fits)
RB_LEG_Y = 20.0           # the tower legs straddle the corridor: their inner faces stay at |y| >= 16.2
RB_CABLE_Y = 18.0         # the main cables run over the legs' inner halves
# THE DECKS ARE ROAD KIT ROADS, not part of this model: the roads' stations at RB_ROAD_LOWER / RB_ROAD_UPPER along
# this piece's X axis, |y| < 15, with `pillar_skip` over the suspension span (the towers and anchorages carry them).


def rainbow_bridge(material, Builder):
    b = Builder("RainbowBridge", material)
    tx = RB_MAIN / 2
    ax = tx + RB_SIDE
    # the two stiffening trusses either side of the road corridor: chords and posts every 10 m, diagonals. No deck:
    # the two decks are Road Kit roads laid through the corridor (RB_ROAD_UPPER / RB_ROAD_LOWER).
    for y in (-RB_HALF_W, RB_HALF_W):
        b.box((-ax, y - 0.4, RB_DECK_BOTTOM), (ax, y + 0.4, RB_DECK_BOTTOM + 1.8), "MI_PaintedMetal")
        b.box((-ax, y - 0.4, RB_DECK_TOP - 1.8), (ax, y + 0.4, RB_DECK_TOP + 1.1), "MI_PaintedMetal")
        n = int(2 * ax / 10)
        for i in range(n + 1):
            x = -ax + 2 * ax * i / n
            b.box((x - 0.35, y - 0.35, RB_DECK_BOTTOM), (x + 0.35, y + 0.35, RB_DECK_TOP), "MI_PaintedMetal")
            if i < n:
                x1 = -ax + 2 * ax * (i + 1) / n
                zlo, zhi = (RB_DECK_BOTTOM + 1.5, RB_DECK_TOP - 1.5) if i % 2 == 0 else (RB_DECK_TOP - 1.5, RB_DECK_BOTTOM + 1.5)
                b.beam((x, y, zlo), (x1, y, zhi), 0.5, "MI_PaintedMetal")
    # the two towers: legs, portal beams, and aviation lights on top
    for sx in (-1, 1):
        x = sx * tx
        for y in (-RB_LEG_Y, RB_LEG_Y):
            b.frustum(x, y, RB_BASE_Z, RB_TOWER_TOP, 4.5, 3.8, 3.0, 2.6, "MI_PaintedMetal")
        mid = (RB_DECK_TOP + RB_TOWER_TOP) / 2
        for z0, z1 in ((RB_DECK_BOTTOM - 4.0, RB_DECK_BOTTOM - 1.0), (mid - 2.0, mid + 2.0), (RB_TOWER_TOP - 6.0, RB_TOWER_TOP - 1.0)):
            b.box((x - 2.5, -RB_LEG_Y, z0), (x + 2.5, RB_LEG_Y, z1), "MI_PaintedMetal")
        b.box((x - 1.0, -RB_LEG_Y - 1.0, RB_TOWER_TOP), (x + 1.0, -RB_LEG_Y + 1.0, RB_TOWER_TOP + 1.5), "MI_Light")
        b.box((x - 1.0, RB_LEG_Y - 1.0, RB_TOWER_TOP), (x + 1.0, RB_LEG_Y + 1.0, RB_TOWER_TOP + 1.5), "MI_Light")
        # the anchorage at the end of each side span
        b.box((sx * ax - 22, -24, RB_BASE_Z), (sx * ax + 22, 24, RB_DECK_BOTTOM - 1.0), "MI_ConcreteSmooth")

    # main cables: a parabola over the main span, a slack chord over each side span; hangers every 12.5 m
    def main_z(x):
        return RB_SAG + (RB_TOWER_TOP - RB_SAG) * (x / tx) ** 2

    for y in (-RB_CABLE_Y, RB_CABLE_Y):
        steps = 46
        pts = [(-tx + RB_MAIN * i / steps, y, main_z(-tx + RB_MAIN * i / steps)) for i in range(steps + 1)]
        for p, q in zip(pts, pts[1:]):
            b.beam(p, q, 1.1, "MI_PaintedMetal")
        for i in range(1, steps):
            x, _, z = pts[i]
            b.beam((x, y, z), (x, math.copysign(RB_HALF_W, y), RB_DECK_TOP + 1.1), 0.25, "MI_PaintedMetal")
        for sx in (-1, 1):
            x0, x1 = sx * tx, sx * ax
            side = [(x0 + (x1 - x0) * k / 8, y, RB_TOWER_TOP + (RB_DECK_TOP + 2 - RB_TOWER_TOP) * k / 8
                     - 6.0 * math.sin(math.pi * k / 8)) for k in range(9)]
            for p, q in zip(side, side[1:]):
                b.beam(p, q, 1.1, "MI_PaintedMetal")
            for p in side[1:-1]:
                b.beam(p, (p[0], math.copysign(RB_HALF_W, y), RB_DECK_TOP + 1.1), 0.25, "MI_PaintedMetal")
    return "RainbowBridge", "structure", b.mesh()


# ── Tokyo Tower (東京タワー) ──────────────────────────────────────────────────────────────────────────────────
# Public record (PLATEAU has no lattice tower): 332.9 m to the antenna tip; base ~88 m square; Main Deck at 150 m,
# Top Deck at 249.6 m; international-orange and white aviation bands.
TT_BASE_HALF = 44.0
TT_WAIST_Z, TT_WAIST_HALF = 90.0, 8.0
TT_MAIN_Z, TT_TOP_Z, TT_TIP = 150.0, 249.6, 332.9


def tokyo_tower(material, Builder):
    b = Builder("TokyoTower", material)

    def band(z):
        return "MI_AviationOrange" if int(z // 24.0) % 2 == 0 else "MI_PaintWhite"

    # four legs splaying from the base corners to the waist, in banded segments, with arches between them
    for sx in (-1, 1):
        for sy in (-1, 1):
            segs = 6
            for k in range(segs):
                t0, t1 = k / segs, (k + 1) / segs
                h0 = TT_BASE_HALF + (TT_WAIST_HALF - TT_BASE_HALF) * t0
                h1 = TT_BASE_HALF + (TT_WAIST_HALF - TT_BASE_HALF) * t1
                z0, z1 = TT_WAIST_Z * t0, TT_WAIST_Z * t1
                b.beam((sx * h0, sy * h0, z0), (sx * h1, sy * h1, z1), 5.0, band(z0))
    for z, h in ((22.0, 34.0), (48.0, 23.0), (70.0, 14.0)):
        for (x0, y0, x1, y1) in ((-h, -h, h, -h), (h, -h, h, h), (h, h, -h, h), (-h, h, -h, -h)):
            b.beam((x0, y0, z), (x1, y1, z), 2.0, band(z))
    # the shaft: tapered banded segments, the two decks, the antenna
    for z0, z1, h0, h1 in ((TT_WAIST_Z, TT_MAIN_Z, TT_WAIST_HALF, 6.0), (TT_MAIN_Z + 6.0, TT_TOP_Z, 6.0, 3.5)):
        n = int((z1 - z0) // 12)
        for k in range(n):
            za, zb = z0 + (z1 - z0) * k / n, z0 + (z1 - z0) * (k + 1) / n
            ha, hb = h0 + (h1 - h0) * k / n, h0 + (h1 - h0) * (k + 1) / n
            b.frustum(0, 0, za, zb, ha, ha, hb, hb, band(za))
    b.box((-15, -15, TT_MAIN_Z), (15, 15, TT_MAIN_Z + 6.0), "MI_GlassClear")
    b.box((-16, -16, TT_MAIN_Z - 0.5), (16, 16, TT_MAIN_Z), "MI_PaintWhite")
    b.box((-8, -8, TT_TOP_Z), (8, 8, TT_TOP_Z + 4.0), "MI_GlassClear")
    b.frustum(0, 0, TT_TOP_Z + 4.0, TT_TIP - 30.0, 2.5, 2.5, 1.2, 1.2, "MI_AviationOrange")
    b.frustum(0, 0, TT_TIP - 30.0, TT_TIP, 1.2, 1.2, 0.4, 0.4, "MI_PaintWhite")
    return "TokyoTower", "structure", b.mesh()


# ── Tokyo Station, Marunouchi building (東京駅丸の内駅舎) ───────────────────────────────────────────────────────
# PLATEAU (tokyostation): the station building's footprint rectangle 320 m long, roofline 21.4 m. Public record: red
# brick with white stone bands, three storeys, a domed pavilion at each end entrance (north and south) and a
# central pavilion; slate roofs.
TS_LEN, TS_DEPTH, TS_WALL, TS_ROOF = 320.0, 22.0, 17.2, 21.4
# The main block's long facades are CLAD in Godot with the downtown kit's own brick-and-glass wall modules
# (Brick_Window_Trim_Single / Brick_Plain_3, six storeys of 2.73 m = 16.38 m; building_types.json), the same glass
# and brick the konbini and the city's buildings use (user, 2026-09-18). This model is the core behind them: the kit's
# brick texture (MI_BrickKit), no windows of its own, a white cornice above the cladding.
TS_CLAD_TOP = 16.38


def tokyo_station(material, Builder):
    b = Builder("TokyoStation", material)
    hx, hy = TS_LEN / 2, TS_DEPTH / 2
    # the main block is solid (offices, the hotel); it stops at the two domed halls, which are hollow, and at the
    # central pavilion, so no roof or string course runs through a hall
    segs = [(-hx, -139.0), (-111.0, -18.0), (18.0, 111.0), (139.0, hx)]
    for a0, a1 in segs:
        b.box((a0, -hy, 0.0), (a1, hy, TS_WALL), "MI_BrickKit")
        b.box((a0, -hy - 0.4, TS_CLAD_TOP), (a1, hy + 0.4, TS_WALL), "MI_PaintWhite")       # cornice over the cladding
        cx, half = (a0 + a1) / 2, (a1 - a0) / 2
        outer = abs(a0) > hx - 1 or abs(a1) > hx - 1
        b.frustum(cx, 0, TS_WALL, TS_ROOF, half, hy, half - (4.0 if outer else 0.5), 3.0, "MI_RoofSlate")
    # the domed pavilions (north and south entrances) and the central pavilion
    for sx in (-1, 1):
        cx = sx * 125.0
        # the domed hall (the ticket-gate concourse): hollow, a 6 x 7 m entrance from the street (-Y) and a
        # passage to the platforms behind (+Y); furnished in Godot from the library (building_types.json)
        shell(b, cx - 14, cx + 14, -hy - 3, hy + 3, 24.0, 0.8, "MI_BrickKit",
              openings={"front": [(cx, 6.0, 7.0)], "back": [(cx, 6.0, 7.0)]})
        b.box((cx - 14.4, -hy - 3.4, 22.8), (cx + 14.4, hy + 3.4, 24.0), "MI_PaintWhite")
        b.frustum(cx, 0, 24.0, 33.0, 13.0, 13.0, 5.0, 5.0, "MI_RoofSlate")
        b.frustum(cx, 0, 33.0, 36.0, 1.5, 1.5, 0.4, 0.4, "MI_Gold")
    b.box((-18, -hy - 4, 0.0), (18, hy + 2, 22.0), "MI_BrickKit")
    b.box((-18.4, -hy - 4.4, 20.8), (18.4, hy + 2.4, 22.0), "MI_PaintWhite")
    b.frustum(0, -1.0, 22.0, 29.0, 18.0, hy + 3.0, 10.0, 4.0, "MI_RoofSlate")
    b.box((-4, -hy - 4.2, 0.0), (4, -hy - 3.9, 6.5), "MI_PlasticDark")
    return "TokyoStation", "building", b.mesh()


# ── Osaka Castle keep (大阪城天守閣) ──────────────────────────────────────────────────────────────────────────
# PLATEAU (osakacastle): the keep with its stone bases 40.6 x 69.3 m (the main base and the adjoining minor-keep
# base), 54.6 m to the top. Public record (the 1931 reconstruction): a battered stone base, five roofs over white
# walls, copper-green tiles, a black-and-gold top storey, gold shachihoko on the ridge.
OC_BASE_H = 13.5


def osaka_castle(material, Builder):
    b = Builder("OsakaCastle", material)
    b.frustum(0, 0, 0.0, OC_BASE_H, 20.3, 22.0, 18.0, 19.5, "MI_StoneWall")            # the main base
    b.frustum(0, 34.65, 0.0, 10.0, 17.0, 12.65, 15.0, 11.0, "MI_StoneWall")            # the minor base (+Y)
    tiers = [(16.0, 18.0, 5.5), (14.0, 16.0, 5.0), (12.0, 14.0, 5.0), (10.0, 12.0, 5.0), (7.5, 9.0, 6.0)]
    z = OC_BASE_H
    for k, (hx, hy, h) in enumerate(tiers):
        top = k == len(tiers) - 1
        b.box((-hx, -hy, z), (hx, hy, z + h), "MI_PlasticDark" if top else "MI_Plaster")
        if top:
            b.box((-hx - 0.1, -hy - 0.1, z + h - 1.6), (hx + 0.1, hy + 0.1, z + h - 0.8), "MI_Gold")
        for wz in (z + 1.8,):                                                    # a window band per tier
            b.box((-hx + 1.5, -hy - 0.1, wz), (hx - 1.5, -hy + 0.05, wz + 1.2), "MI_PlasticDark")
        z += h
        if not top:
            b.frustum(0, 0, z, z + 2.0, hx + 3.0, hy + 3.0, hx - 1.5, hy - 1.5, "MI_RoofCopper")
            z += 2.0
    b.frustum(0, 0, z, z + 5.0, tiers[-1][0] + 3.5, tiers[-1][1] + 3.5, 1.0, tiers[-1][1] - 3.0, "MI_RoofCopper")
    ridge = z + 5.0
    for sy in (-1, 1):
        b.box((-1.0, sy * (tiers[-1][1] - 3.0) - 0.8, ridge), (1.0, sy * (tiers[-1][1] - 3.0) + 0.8, ridge + 2.2), "MI_Gold")
    return "OsakaCastle", "building", b.mesh()


# ── The airport: ONE compact terminal, Haneda-flavoured (羽田空港), and runway pieces ──────────────────────────
# User direction (2026-09-18): keep the airport's feeling without an over-complex map, as GTA's earlier games did:
# one terminal, one or two runways. PLATEAU measured Haneda's real halls at 40-42 m and its complex at 266 x 938 m;
# this is deliberately a fraction of that: a 150 m hollow departure hall (25 m), a hollow 240 m concourse with two
# piers, the elevated departure drive in front, and a small control tower. Runways are laid from the pieces below.
def haneda_terminal(material, Builder):
    b = Builder("AirportTerminal", material)
    # the departure hall: glass front with four 4 x 3.5 m entrances, two 8 x 4 m openings to the concourse behind
    shell(b, -75, 75, -30, 30, 25.0, 0.6, "MI_PaintedMetalDark",
          openings={"front": [(x, 4.0, 3.5) for x in (-45.0, -15.0, 15.0, 45.0)],
                    "back": [(x, 8.0, 4.0) for x in (-40.0, 40.0)]},
          ceiling="MI_PaintedMetal", side_mats={"front": "MI_GlassClear"})
    b.box((-80, -42, 25.0), (80, 34, 27.5), "MI_PaintedMetal")                # the roof, overhanging the drive
    # the concourse, hollow, glass on the apron side; its hall-side wall has the hall's two openings
    shell(b, -120, 120, 30, 60, 12.0, 0.6, "MI_PaintedMetal",
          openings={"front": [(x, 8.0, 4.0) for x in (-40.0, 40.0)]}, side_mats={"back": "MI_GlassClear"})
    b.box((-121, 29, 12.0), (121, 61, 13.0), "MI_PaintedMetal")
    for x in (-90.0, 90.0):                                                    # two piers
        b.box((x - 12, 60, 0.0), (x + 12, 120, 10.0), "MI_PaintedMetal")
        b.box((x - 12.3, 60, 3.5), (x + 12.3, 120, 7.5), "MI_GlassClear")
    b.box((-75, -50, 7.0), (75, -38, 8.2), "MI_ConcreteSmooth")               # the elevated departure drive
    for x in range(-70, 71, 20):
        b.box((x - 1.0, -45.0, 0.0), (x + 1.0, -43.0, 7.0), "MI_ConcreteSmooth")
    # a small control tower beside the terminal
    b.box((104, -14, 0.0), (112, -6, 40.0), "MI_PaintedMetal")
    b.frustum(108, -10, 40.0, 46.0, 5.0, 5.0, 7.0, 7.0, "MI_GlassClear")
    b.box((100.5, -17.5, 46.0), (115.5, -2.5, 47.0), "MI_PaintedMetalDark")
    return "AirportTerminal", "building", b.mesh()


def runway_section(material, Builder):
    """A 60 m runway section along X: 45 m of asphalt, white edge lines, a 30 m centreline dash and its gap."""
    b = Builder("Airport_Runway", material)
    b.box((-30, -22.5, -0.05), (30, 22.5, 0.0), "MI_AsphaltLot")
    for y in (-21.5, 21.5):
        b.box((-30, y - 0.45, 0.0), (30, y + 0.45, 0.01), "MI_PaintWhite")
    b.box((-15, -0.45, 0.0), (15, 0.45, 0.01), "MI_PaintWhite")
    return "Airport_Runway", "airport", b.mesh()


def runway_end(material, Builder):
    """A runway's 60 m threshold end: the piano-key stripes and the threshold bar, the runway continuing at +X."""
    b = Builder("Airport_RunwayEnd", material)
    b.box((-30, -22.5, -0.05), (30, 22.5, 0.0), "MI_AsphaltLot")
    for y in (-21.5, 21.5):
        b.box((-30, y - 0.45, 0.0), (30, y + 0.45, 0.01), "MI_PaintWhite")
    for k in range(12):                                                         # piano keys, 6 each side
        y = -19.5 + k * 3.2 + (2.0 if k >= 6 else 0.0)
        b.box((-26, y, 0.0), (4, y + 1.8, 0.01), "MI_PaintWhite")
    b.box((8, -21.0, 0.0), (11, 21.0, 0.01), "MI_PaintWhite")
    return "Airport_RunwayEnd", "airport", b.mesh()


# ── Shuri Castle (首里城), the Okinawan landmark (PLAN.md 3.8 step 8) ─────────────────────────────────────────────
# User direction (2026-09-18): Okinawa's CHARACTER on the island, a Shuri-style castle sited as a hill castle at the
# massif's south-east foot (measured site: ground 3-27 m under a 140 m patch, `tools/island_sites.py`). Shuri is not a
# tower keep: its heart is the SEIDEN (正殿, 28.97 x 16.9 m, two storeys, red lacquer, red-tile roofs, a karahafu gable
# over the entrance and two gold dragon pillars) facing the UNA (御庭), a courtyard paved in red and white stripes, with
# the Hokuden and Nanden to either side and the Houshinmon gate opposite, all inside curved Ryukyu-limestone walls
# (石垣). Here the walls are one platform, SH_PLAT_H tall, that the hill slopes into: its top clears the uphill ground,
# and on the downhill side it stands as the castle wall. The Seiden faces -Y (the piece's front, +Z in Godot).
SH_PLAT_H = 25.0
SH_PLAT = (75.0, 60.0)          # half-sizes of the platform's top


def shuri_castle(material, Builder):
    b = Builder("ShuriCastle", material)
    hx, hy = SH_PLAT
    top = SH_PLAT_H
    b.frustum(0, 0, 0.0, top, hx + 4.0, hy + 4.0, hx, hy, "MI_Limestone")        # the walls, battered
    for (x0, y0, x1, y1) in ((-hx, -hy, hx, -hy + 1.2), (-hx, hy - 1.2, hx, hy),   # the parapet round the top
                             (-hx, -hy, -hx + 1.2, hy), (hx - 1.2, -hy, hx, hy)):
        b.box((x0, y0, top), (x1, y1, top + 1.4), "MI_Limestone")
    b.box((-8.0, -hy - 0.2, top), (8.0, -hy + 1.4, top + 1.4), "MI_Limestone")    # (the gate's gap is its own box)
    # the Una: red and white stripes, 2 m bands running toward the Seiden
    ux0, ux1, uy0, uy1 = -22.0, 22.0, -30.0, 12.0
    for k in range(22):
        x = ux0 + 2.0 * k
        b.box((x, uy0, top), (x + 2.0, uy1, top + 0.03), "MI_RoofTileRed" if k % 2 else "MI_PaintWhite")
    # the Seiden, at the back of the Una
    sx, sy, sy0 = 14.5, 8.45, 22.0
    b.box((-sx, sy0 - sy, top), (sx, sy0 + sy, top + 9.0), "MI_LacquerRed")
    b.frustum(0, sy0, top + 9.0, top + 11.5, sx + 2.5, sy + 2.5, sx - 1.0, sy - 1.0, "MI_RoofTileRed")
    b.box((-sx + 2.0, sy0 - sy + 2.0, top + 11.5), (sx - 2.0, sy0 + sy - 2.0, top + 15.0), "MI_LacquerRed")
    b.frustum(0, sy0, top + 15.0, top + 21.0, sx + 1.0, sy + 1.0, sx - 6.0, 1.0, "MI_RoofTileRed")
    b.box((-sx + 5.5, sy0 - 0.4, top + 21.0), (sx - 5.5, sy0 + 0.4, top + 22.0), "MI_RoofTileRed")   # the ridge
    b.box((-7.0, sy0 - sy - 4.0, top + 8.0), (7.0, sy0 - sy + 0.5, top + 11.0), "MI_RoofTileRed")    # karahafu
    for x in (-4.0, 4.0):                                                            # the gold dragon pillars
        b.box((x - 0.5, sy0 - sy - 3.2, top), (x + 0.5, sy0 - sy - 2.2, top + 8.0), "MI_Gold")
    b.box((-5.0, sy0 - sy - 3.6, top), (5.0, sy0 - sy, top + 0.6), "MI_Limestone")  # the steps
    # the Hokuden (north) and the Nanden (south) flank the Una
    for x0, x1, mat in ((-44.0, -26.0, "MI_LacquerRed"), (26.0, 44.0, "MI_Plaster")):
        b.box((x0, -24.0, top), (x1, 6.0, top + 7.0), mat)
        b.frustum((x0 + x1) / 2, -9.0, top + 7.0, top + 11.0, (x1 - x0) / 2 + 1.5, 16.5, 2.0, 12.0, "MI_RoofTileRed")
    # the Houshinmon gate, opposite the Seiden
    b.box((-12.0, -40.0, top), (12.0, -34.0, top + 6.0), "MI_LacquerRed")
    b.frustum(0, -37.0, top + 6.0, top + 9.0, 14.0, 4.5, 11.0, 1.0, "MI_RoofTileRed")
    return "ShuriCastle", "building", b.mesh()


def build_all(material, Builder):
    return [rainbow_bridge(material, Builder), tokyo_tower(material, Builder), tokyo_station(material, Builder),
            osaka_castle(material, Builder), shuri_castle(material, Builder), haneda_terminal(material, Builder),
            runway_section(material, Builder), runway_end(material, Builder)]
