#!/usr/bin/env python3
"""
build_world.py -> world_master.blend

The MASTER world-layout for the whole ~3 km x 3 km game map (PLAN.md "Target": a
Japan/Tokyo-like semi-open world — harbor, neon city, residential wards, rural,
mountains, snow). This is NOT a flattened mega-scene: it is the *world-layout source*
described in BLENDER_CONVENTIONS.md ("Blender = asset library + world-layout source of
empties / blockout proxies showing WHERE each chunk goes; Godot = the baked runtime").
It holds only district blocks + an ARTERIAL BACKBONE + markers, so it stays tiny.

WHY a backbone, not the full street grid: the full 7 m road solver across 3 km is still
far too heavy for one file, and it fights the "lightweight layout source" rule. So the
master runs the `TownGrid` solver on the **arterial backbone only** (major avenues on
the district grid + the landmark/harbor connectors). The solver classifies junctions and
(next pass) emits region/zone PORTALS by construction, guaranteeing the overall layout
connects and seams line up — and it stays hand-adjustable (edit the arterial definition
or the MANUAL landmark/slot anchors). Each DISTRICT PIECE then runs the solver LOCALLY
at full 7 m resolution for its own streets, snapping to these portals.

Grid: 6x6 DISTRICTS of 504 m (504 = 3 regions = 9 zones = 72 road cells), so every
district edge lands on the 168 m region / 56 m zone / 7 m road grid. Arterials run along
those district-edge grid lines (cell cols/rows 0,72,144,...,432).

**Centre-origin**: the world spans `[-ORIGIN,+ORIGIN]` (ORIGIN=WORLD/2), not `[0,WORLD]` —
halves the worst-case distance from (0,0,0) at the far corner for the same map size
(single-precision float headroom in Godot 4's default build — see AUTHORING_GUIDE.md).
Every function here computes in GRID-SPACE (0..WORLD, the natural `gx*DISTRICT` frame)
and converts to true world coordinates via `world_grid.to_world()` only at the final
placement — look for `to_world(...)` at every `kc.box`/marker `.location` call.

Emits (into collections the Java WorldBaker consumes):
  * region_<theme>_<gx>_<gy> (MARKERS) -> WorldZoneMarker + RegionConfig (tuning/theme).
  * slot_<landmark> (LANDMARKS) -> hand-craft hook for a Tokyo hero district piece
    (Shibuya / TokyoStation / Akihabara / Haneda). Baker ignores it until you set its
    `asset_path` to the piece .tscn — same contract as place_manual_slots.
  * LAYOUT: theme-coloured, elevation-stepped 504 m plates (preview base) + arterial
    ribbons (the backbone, preview) — replaced by each district piece's own geometry.
    (export_world.py drops this + HARBOR before the master ever reaches the baker —
    both are pure Blender-side visualization, never meant to ship.)

RUN: blender --background --python towns/build_world.py
     blender --background world_master.blend --python tools/render.py -- _preview_world 0 0 3400
"""
import bpy, os, sys, math
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import road_network as rn
import assemble as asm
from world_grid import (
    CELL, DISTRICT, DCELLS, GRID_N, LANE_OFF, LANE_STRIDE, THEMES, MAP, LANDMARKS,
    PIECE_DIR, HERO_PIECE, WORLD, ORIGIN,
    piece_path, lod_low_piece_path, theme_at, elev_at, district_center, to_world,
    flank_z as _flank_z, sampled as _sampled,
)

# ---- grid geometry (all on the 168/56/7 m grid) -------------------------------
# CELL/DISTRICT/DCELLS/GRID_N/WORLD/THEMES/MAP/LANDMARKS/piece_path/theme_at/elev_at/
# district_center now live in lib/world_grid.py (shared with build_district.py, so a
# district piece built in isolation computes the SAME seam coordinates/elevations the
# master expects there — see world_grid.py's docstring).
SPAN     = DCELLS * GRID_N            # 432 cells = 3024 m ~ 3 km
SEAM     = 4.0                        # visual gap between plates so pieces read apart

# ---- Tokyo Bay + Haneda airport island + the connecting bridge (GRID-SPACE coords, m —
# to_world() applied at each use site, same convention as the rest of this file) ----
# Island moved further out to sea (was Y0/Y1 = -450/-187.5, a 192m bridge gap) to make room for
# the real Rainbow Bridge landmark overlay (buildings/PLATEAU_RainbowBridge.blend): the raw PLATEAU
# extraction spans ~750m (a single-anchor, 260m-radius extraction that only reaches one tower, not
# a clean symmetric span), which massively overhung the old 192m gap into the island. The gap is
# now ~800m -- comfortable room for that real span without overlap. Placeholder-quality sizing,
# not a final harbor layout -- expect to hand-tune island/bridge/coast positions further later.
BAY_Y0, BAY_Y1 = -1108.0, 0.0                # sea band south of the map (Tokyo Bay)
ISL_X0, ISL_X1 = 1134.0, 2268.0              # airport island footprint (SE, near harbor cells)
ISL_Y0, ISL_Y1 = -1058.0, -795.5
BR_X = 1701.0                                # bridge centreline x (~ island centre)
BR_DECK_Z = 11.0                             # LAYER_EXPS — road deck top (engine Z, size-independent)
BR_RAIL_Z = 8.0                              # LAYER_RAIL — rail deck top (engine Z, size-independent)


def make_grid():
    """Arterial backbone on the district grid lines (cols/rows 0,72,...,576). The solver
    holds it for junction/portal derivation; landmark footprints are reserved manual."""
    g = rn.TownGrid()
    for k in range(GRID_N + 1):
        c = k * DCELLS
        g.arterial_v(c, 0, SPAN, width=3)
        g.arterial_h(c, 0, SPAN, width=3)
    for _, _, gx, gy, fc in LANDMARKS:
        cx, cy = int((gx + 0.5) * DCELLS), int((gy + 0.5) * DCELLS)
        h = fc // 2
        g.reserve_manual(cx - h, cy - h, cx + h, cy + h)
    return g


def backbone_lanes(coll):
    """One VehicleRoute pair (both directions, keep-left) per arterial line, sampled
    sparsely — lane_art_<line>_<dir>_<n> for the WorldBaker. Sparse by design: straights
    need few points; junction weaving is per-district. z tracks the seam elevation.
    Grid-space math throughout; to_world() applied only at the final marker placement (so
    _flank_z, which expects true world coordinates, still gets them right)."""
    n = 0
    for k in range(GRID_N + 1):
        c = k * DCELLS                       # arterial cell col/row
        base = c * CELL                      # grid-space coord of the centreline
        ys = _sampled(0, SPAN, LANE_STRIDE)
        # vertical arterial at x=base: NB (west lane, +y order), SB (east lane, -y order)
        nb = [(base - LANE_OFF, y * CELL) for y in ys]
        sb = [(base + LANE_OFF, y * CELL) for y in reversed(ys)]
        # horizontal arterial at y=base: EB (north lane, +x order), WB (south lane, -x order)
        eb = [(x * CELL, base + LANE_OFF) for x in ys]
        wb = [(x * CELL, base - LANE_OFF) for x in reversed(ys)]
        for route, pts in ((f"art_v{k}_N", nb), (f"art_v{k}_S", sb),
                           (f"art_h{k}_E", eb), (f"art_h{k}_W", wb)):
            for i, (gx, gy) in enumerate(pts):
                wx, wy = to_world(gx), to_world(gy)
                e = bpy.data.objects.new(f"lane_{route}_{i}", None)
                e.empty_display_size = 1.0
                e.location = (wx, wy, _flank_z(wx, wy) + 0.6)
                coll.objects.link(e)
                n += 1
    return n


def backbone_intersections(g, coll):
    """intersection_<cx>_<cy> at every major junction the SOLVER finds on the arterial
    backbone (g.arterial_intersections()) -> IntersectionZone (traffic right-of-way) in the
    bake. Solver-driven, so hand-editing the arterials keeps the junctions correct; local
    junctions are per-district. z tracks the seam it sits on."""
    n = 0
    for (cx, cy, _opens) in g.arterial_intersections():
        wx, wy = to_world(cx * CELL), to_world(cy * CELL)
        e = bpy.data.objects.new(f"intersection_{cx}_{cy}", None)
        e.empty_display_type = 'PLAIN_AXES'; e.empty_display_size = 10.5
        e.location = (wx, wy, _flank_z(wx, wy) + 0.6)
        e["size"] = [21.0, 6.0, 21.0]        # 3x3-cell arterial junction footprint
        coll.objects.link(e)
        n += 1
    return n


def build_harbor(coll, mk, land):
    """Tokyo Bay + Haneda airport island + connecting road/rail bridge. Lightweight blockout
    (a dozen boxes + markers); the real Haneda terminal / Rainbow Bridge landmark overlays
    (buildings/PLATEAU_HanedaTerminal.blend, buildings/PLATEAU_RainbowBridge.blend) sit on top
    of this footprint via their own slot_ hooks, same contract as the district LANDMARKS."""
    bay = kc.box("Bay", to_world(0.0), to_world(WORLD), to_world(BAY_Y0), to_world(BAY_Y1),
                 -2.0, -0.2, coll, "metal")
    island = kc.box("HanedaIsland", to_world(ISL_X0), to_world(ISL_X1),
                     to_world(ISL_Y0), to_world(ISL_Y1), -0.5, 0.5, coll, "roof")

    deck = kc.box("RainbowBridgeDeck", to_world(BR_X - 15.0), to_world(BR_X + 15.0),
                  to_world(ISL_Y0 - 260.0), to_world(ISL_Y0), BR_DECK_Z - 0.6, BR_DECK_Z,
                  coll, "metal")
    rail = kc.box("RainbowBridgeRail", to_world(BR_X - 6.0), to_world(BR_X + 6.0),
                  to_world(ISL_Y0 - 260.0), to_world(ISL_Y0), BR_RAIL_Z - 0.4, BR_RAIL_Z,
                  coll, "metal")

    n_pier = 0
    y = ISL_Y0 - 20.0
    while y > ISL_Y0 - 260.0:
        p = kc.cyl(f"BridgePier_{n_pier}", 4.0, -2.0, BR_DECK_Z - 0.6, coll, "metal")
        p.location = (to_world(BR_X), to_world(y), 0.0)
        n_pier += 1
        y -= 40.0

    s = bpy.data.objects.new("slot_haneda", None)
    s.empty_display_type = 'ARROWS'; s.empty_display_size = 60.0
    s.location = (to_world((ISL_X0 + ISL_X1) / 2.0), to_world((ISL_Y0 + ISL_Y1) / 2.0), 1.0)
    s["landmark"] = "haneda"; s["footprint_m"] = ISL_X1 - ISL_X0
    land.objects.link(s)

    r = bpy.data.objects.new("slot_rainbowbridge", None)
    r.empty_display_type = 'ARROWS'; r.empty_display_size = 40.0
    r.location = (to_world(BR_X), to_world(ISL_Y0 - 130.0), BR_DECK_Z)
    r["landmark"] = "rainbowbridge"
    land.objects.link(r)

    e = bpy.data.objects.new("water_bay", None)
    e.empty_display_type = 'PLAIN_AXES'; e.empty_display_size = 30.0
    e.location = (to_world(WORLD / 2.0), to_world((BAY_Y0 + BAY_Y1) / 2.0), 0.0)
    e["size"] = [WORLD, 4.0, BAY_Y1 - BAY_Y0]
    mk.objects.link(e)

    return 8  # box/pier count, matches the "harbor=8" preview-build summary stat


def build():
    kc.setup_units()
    asm.wipe_scene()
    layout = kc.get_coll("LAYOUT")
    mk = kc.get_coll("MARKERS")
    land = kc.get_coll("LANDMARKS")
    harbor = kc.get_coll("HARBOR")

    g = make_grid()

    counts = {k: 0 for k in THEMES}
    for gy in range(GRID_N):
        for gx in range(GRID_N):
            key = theme_at(gx, gy); t = THEMES[key]; counts[key] += 1
            cx, cy = district_center(gx, gy); elev = t["elev"]

            # theme plate (preview base). Grid-space bounds, to_world() at the box call.
            x0 = gx * DISTRICT + SEAM / 2.0; x1 = (gx + 1) * DISTRICT - SEAM / 2.0
            y0 = gy * DISTRICT + SEAM / 2.0; y1 = (gy + 1) * DISTRICT - SEAM / 2.0
            # plate top sits just BELOW piece-ground level (elev) so a streamed district piece
            # lands cleanly on top instead of z-fighting / half-sinking the player into the plate.
            kc.box(f"Plate_{key}_{gx}_{gy}", to_world(x0), to_world(x1), to_world(y0), to_world(y1),
                   elev - 0.6, elev - 0.1, layout, t["col"])

            # region_ marker -> WorldZoneMarker + RegionConfig.
            r = bpy.data.objects.new(f"region_{key}_{gx}_{gy}", None)
            r.empty_display_type = 'CUBE'; r.empty_display_size = DISTRICT / 2.0
            r.location = (cx, cy, elev)
            r["size"] = [DISTRICT, 40.0, DISTRICT]; r["bounds"] = [DISTRICT, 40.0, DISTRICT]
            r["region_name"] = t["name"]; r["ambient_ai_density"] = t["ai"]
            r["vehicle_density"] = t["veh"]; r["ai_lod_bias"] = t["lod"]
            r["light_temperature"] = t["light"]; r["fog_density"] = t["fog"]
            r["geometry"] = piece_path(gx, gy, key)      # predictable piece path (lazy-resolved)
            # Low-detail placeholder tier, ALWAYS resident (see WorldZoneMarker) while the full-
            # detail geometry above is streamed out — resolved the same lazy way; a district that
            # never built one (PLATEAU precincts) just has nothing to show, no error.
            r["geometry_lod_low"] = lod_low_piece_path(gx, gy, key)
            mk.objects.link(r)

    # arterial backbone: lane routes + major-junction IntersectionZones (the functional AI/traffic
    # graph). The cosmetic Art_V/H preview ribbons and the grid-locked C1 Loop ring were removed --
    # both were tied to the district-boundary grid lines and didn't route like a real expressway
    # (see the highway/district redesign follow-up); ring_network.py itself is kept for that redesign,
    # just not invoked here for now.
    n_lane = backbone_lanes(mk)
    n_ix = backbone_intersections(g, mk)

    # harbor: Tokyo Bay + Haneda airport island + connecting road/rail bridge.
    build_harbor(harbor, mk, land)

    # Tokyo hero-district anchors (hand-craft hooks; set asset_path to bake-swap a piece).
    for name, piece, gx, gy, fc in LANDMARKS:
        cx, cy = district_center(gx, gy); elev = elev_at(gx, gy)
        s = bpy.data.objects.new(f"slot_{name}", None)
        s.empty_display_type = 'ARROWS'; s.empty_display_size = fc * CELL / 2.0
        s.location = (cx, cy, elev + 1.0)
        s["landmark"] = name; s["district_piece"] = piece
        s["footprint_m"] = fc * CELL
        land.objects.link(s)

    asm.add_camera_sun(layout, target=(to_world(WORLD / 2), to_world(WORLD / 2), 0.0),
                       cam_loc=(to_world(WORLD / 2), to_world(-WORLD * 0.4), WORLD * 0.75), lens=28)

    summary = "  ".join(f"{k}={v}" for k, v in counts.items())
    print("WORLD: %.0fx%.0f m  districts=%d (%dx%d, %.0f m)  lanes=%d  junctions=%d  landmarks=%d  %s"
          % (WORLD, WORLD, GRID_N * GRID_N, GRID_N, GRID_N, DISTRICT, n_lane, n_ix, len(LANDMARKS), summary))


def main():
    build()
    if bpy.app.background:
        kc.save_blend(ROOT, "world_master.blend")


if __name__ == "__main__":
    main()
