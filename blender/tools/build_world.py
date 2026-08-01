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
  * LAYOUT: every BUILT district piece TRUE-library-linked (link=True, the link_world.py
    mechanism) as a `Piece_<gx>_<gy>` Collection-Instance at its true world position —
    opening world_master.blend shows the REAL assembled world, live-updating when a
    district source .blend is edited (linked data is read-only here, so the master can
    never corrupt a piece). A district not built yet falls back to the old theme-coloured
    elevation-stepped plate as its placeholder. (export_world.py drops LAYOUT + HARBOR
    before the master ever reaches the baker — both are pure Blender-side visualization,
    never meant to ship; each district streams in on its own at runtime.)

RUN: blender --background --python blender/tools/build_world.py
     blender --background world_master.blend --python blender/tools/render.py -- _preview_world 0 0 3400
"""
import bpy, os, sys, math
BLENDER_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import kit_common as kc
import road_network as rn
import assemble as asm
import piece_registry as pr
from world_grid import (
    CELL, DISTRICT, DCELLS, GRID_N, LANE_OFF, LANE_STRIDE, THEMES, MAP, LANDMARKS,
    PIECE_DIR, WORLD, ORIGIN,
    BAY_Y0, BAY_Y1, ISL_X0, ISL_X1, ISL_Y0, ISL_Y1, BR_X, BR_DECK_Z, BR_RAIL_Z,
    piece_id_for_cell, theme_at, elev_at, district_center, to_world,
    flank_z as _flank_z, sampled as _sampled, is_void,
)

# ---- grid geometry (all on the 168/56/7 m grid) -------------------------------
# CELL/DISTRICT/DCELLS/GRID_N/WORLD/THEMES/MAP/LANDMARKS/theme_at/elev_at/
# district_center now live in lib/world_grid.py (shared with build_district.py, so a
# district piece built in isolation computes the SAME seam coordinates/elevations the
# master expects there — see world_grid.py's docstring).
SPAN     = DCELLS * GRID_N            # 432 cells = 3024 m ~ 3 km
SEAM     = 4.0                        # visual gap between plates so pieces read apart
PIECE_COLLS = ["STREET", "MANUAL", "OVERLAY"]   # collections linked into LAYOUT if present --
                                      # STREET/MANUAL for a district, OVERLAY/MANUAL for a former
                                      # overlay (link_collections tolerates missing names, so one
                                      # list covers every piece kind uniformly, no branch needed)

# Tokyo Bay / Haneda island / bridge constants (BAY_*, ISL_*, BR_*) moved to lib/world_grid.py —
# shared with the overlay generators (overlays/build_rainbow_bridge_overlay.py) so the harbor
# blockout, slot_ anchors, and the overlay geometry all seat from one source.


def make_grid():
    """Arterial backbone on the district grid lines (cols/rows 0,72,...,576). The solver
    holds it for junction/portal derivation; landmark footprints are reserved manual."""
    g = rn.TownGrid()
    for k in range(GRID_N + 1):
        c = k * DCELLS
        g.arterial_v(c, 0, SPAN, width=3)
        g.arterial_h(c, 0, SPAN, width=3)
    for _, gx, gy, fc in LANDMARKS:
        cx, cy = int((gx + 0.5) * DCELLS), int((gy + 0.5) * DCELLS)
        h = fc // 2
        g.reserve_manual(cx - h, cy - h, cx + h, cy + h)
    return g


def backbone_deck(coll):
    """Always-resident collision-only deck (21 m wide) under every arterial line — the master
    OWNS the boundary roads, and this is their physical surface. Without it, anything on an
    arterial outside the streamed districts stands over void: districts only bring ground
    while streamed in and PLATEAU precincts ship no always-resident LOD_LOW tier, so ambient
    traffic spawned along the backbone simply fell into the void (0-moving traffic, headless
    smoke). Swept with the SAME _flank_z the lane markers use, so cars drop the marker's
    0.6 m onto the deck; V/H strips overlap at crossings (junction surface for free)."""
    half = (3 * CELL) / 2.0
    lines = [k * DCELLS * CELL for k in range(GRID_N + 1)]
    span = int(lines[-1])
    step = int(4 * CELL)
    n = 0
    for i, c in enumerate(lines):
        cw = to_world(c)
        vpts = [(cw, to_world(y), _flank_z(cw, to_world(y))) for y in range(0, span + 1, step)]
        kc.colonly_swept(f"ArtDeckV_{i}", vpts, half, coll, z0=-0.5, z1=0.0)
        hpts = [(to_world(x), cw, _flank_z(to_world(x), cw)) for x in range(0, span + 1, step)]
        kc.colonly_swept(f"ArtDeckH_{i}", hpts, half, coll, z0=-0.5, z1=0.0)
        n += 2
    return n


def build_harbor(coll, mk, land):
    """Tokyo Bay + Haneda airport island blockout + markers. The Rainbow Bridge road/rail is NO
    LONGER blocked out here — it lives in its own overlay blend
    (overlays/build_rainbow_bridge_overlay.py, AUTHORING_GUIDE §5), which actually ships
    (this HARBOR collection is dropped at export, preview-only) — keeping a blockout here too
    would just diverge from the real overlay geometry. The slot_rainbowbridge anchor stays as
    the coordinate record; the shared seat constants are in world_grid.py (BR_*, ISL_*)."""
    bay = kc.box("Bay", to_world(0.0), to_world(WORLD), to_world(BAY_Y0), to_world(BAY_Y1),
                 -2.0, -0.2, coll, "metal")
    island = kc.box("HanedaIsland", to_world(ISL_X0), to_world(ISL_X1),
                     to_world(ISL_Y0), to_world(ISL_Y1), -0.5, 0.5, coll, "roof")

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

    return 2  # blockout box count (Bay + island; the bridge moved to its overlay blend)


def parse_args():
    """CLI after `--`. DEFAULT IS MINIMAL (collision-diagnosis baseline, 2026-07): the master
    ships only region/landmark/water markers — no ArtDeck collision strips.
    `--full` restores the ArtDeck ground layer; `--with-deck` exists separately to A/B-bisect
    which body causes a collision artifact. (The old arterial lane markers /`--with-lanes`/
    `--driving-side` — `backbone_graph()`, `lib/road_graph.py` — were removed in P6.8:
    per-district ambient traffic now comes entirely from each district's own `.lanekit.json`,
    see the `has_lanekit` check in `build()` below. The world-spanning SafetyFloor slab —
    formerly here as `safety_floor()`/`--with-floor` — was removed outright: it silently
    trapped characters a meter-plus below visual ground with no recovery path, since neither
    `Character` nor `Player` has any fall-out-of-world safety net (unlike vehicles, which
    `WorldZoneManager.maintainTraffic` reclaims below Y=-30) — see AUTHORING_GUIDE.md.)"""
    import argparse
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_world.py")
    ap.add_argument("--full", action="store_true",
                    help="build everything: ArtDeck collision strips")
    ap.add_argument("--with-deck", action="store_true",
                    help="include the 14 ArtDeck collision strips")
    a = ap.parse_args(argv)
    if a.full:
        a.with_deck = True
    return a


def _emit_region_marker(mk, piece):
    """One region_<id> -> WorldZoneMarker + RegionConfig marker for `piece` (a piece_registry
    dict: id/position/footprint/load_radius/unload_radius/theme) -- the single emission path
    EVERY piece goes through, grid district or freestanding (former-overlay included) alike, no
    kind branch (FREESTANDING_PIECES_PLAN.md §D). `theme` is optional -- a themeless piece (e.g.
    the migrated Rainbow Bridge) simply omits the theme-derived properties and WorldBaker's
    buildRegion() falls back to its own sane defaults (region_name = the marker's own id,
    ambient_ai_density = 1.0, etc.) rather than this script inventing placeholder theme values."""
    stem = piece["id"]
    x, y, z = piece["position"]
    fx, fy, fz = piece["footprint"]
    r = bpy.data.objects.new(f"region_{stem}", None)
    r.empty_display_type = 'CUBE'; r.empty_display_size = max(fx, fz) / 2.0
    r.location = (x, y, z)
    r["size"] = [fx, fy, fz]; r["bounds"] = [fx, fy, fz]
    theme_key = piece.get("theme")
    if theme_key:
        t = THEMES[theme_key]
        r["region_name"] = t["name"]; r["ambient_ai_density"] = t["ai"]
        r["vehicle_density"] = t["veh"]; r["ai_lod_bias"] = t["lod"]
        r["light_temperature"] = t["light"]; r["fog_density"] = t["fog"]
    r["geometry"] = PIECE_DIR + stem + ".tscn"                # predictable, lazy-resolved
    r["geometry_lod_low"] = PIECE_DIR + stem + "_LOD_LOW.tscn"
    # No explicit load_radius/unload_radius meta = WorldBaker.buildZone falls back to its own
    # size-based default -- exactly what every migrated grid district relied on before this
    # existed, so leaving these None reproduces that behavior unchanged. Only a piece that needs
    # an explicit override (the bridge) sets them.
    if piece.get("load_radius") is not None:
        r["load_radius"] = piece["load_radius"]
    if piece.get("unload_radius") is not None:
        r["unload_radius"] = piece["unload_radius"]
    # Ambient-traffic recipe -- same `.lanekit.json`-beside-the-.blend convention for every piece.
    has_lanekit = os.path.exists(os.path.join(ROOT, "pieces", stem + ".lanekit.json"))
    if has_lanekit:
        r["traffic_count"] = 6
        r["traffic_route"] = stem
    else:
        r["traffic_count"] = 0
        r["traffic_route"] = ""
    mk.objects.link(r)


def build(opts):
    kc.setup_units()
    asm.wipe_scene()
    layout = kc.get_coll("LAYOUT")
    mk = kc.get_coll("MARKERS")
    land = kc.get_coll("LANDMARKS")
    harbor = kc.get_coll("HARBOR")

    counts = {k: 0 for k in THEMES}
    n_linked = n_plate = n_void = 0
    registered_stems = set()
    for gy in range(GRID_N):
        for gx in range(GRID_N):
            if is_void(gx, gy):
                # Deliberately nothing here — no placeholder plate (unlike "not built yet"),
                # no link, no region_ marker below. See AUTHORING_GUIDE.md §4 "void cells".
                n_void += 1
                continue
            key = theme_at(gx, gy); t = THEMES[key]; counts[key] += 1
            stem = piece_id_for_cell(gx, gy)

            # lib/piece_registry.py (assets/world_source/pieces.json) is now the source of truth
            # for a piece's position/footprint/radii (FREESTANDING_PIECES_PLAN.md §D) — the grid
            # walk above is still how void/plate/theme-count bookkeeping works (a separate,
            # smaller concern, see the plan's §D note), but the actual marker DATA comes from the
            # registry. A grid cell whose piece hasn't been registered yet (a fresh hand-built
            # district before running migrate_to_pieces.py / registering it by hand) falls back
            # to the old grid-derived values so it still gets a usable marker.
            piece = pr.piece_by_id(stem)
            if piece is None:
                cx, cy = district_center(gx, gy); elev = t["elev"]
                piece = {"id": stem, "position": (cx, cy, elev),
                         "footprint": (DISTRICT, 40.0, DISTRICT),
                         "load_radius": None, "unload_radius": None, "theme": key}
                print(f"WARNING: {stem} not in pieces.json — using grid-derived fallback "
                      f"(register it, e.g. via migrate_to_pieces.py or piece_registry.set_piece)")
            else:
                registered_stems.add(stem)
            cx, cy, elev = piece["position"]

            # District layer: TRUE library link (link=True, the link_world.py mechanism) of the
            # built piece's exported content (STREET + MANUAL), instanced at its true world
            # position — the SAME (cx, cy, elev) the region_ marker below hands the runtime, so
            # what lines up here lines up in-game. Live reference: edit + save a district .blend,
            # reload the master, the edit shows; read-only here, so the master can never corrupt
            # a piece. Purely Blender-side preview — export_world.py drops LAYOUT, and linking a
            # piece's STREET pulls in neither its NEIGHBOR_REF context (separate collection) nor
            # the master itself, so a district that links the master back via
            # link_neighbors.py --master creates no load cycle.
            piece_blend = os.path.join(ROOT, "pieces", stem + ".blend")
            colls = kc.link_collections(piece_blend, PIECE_COLLS) \
                if os.path.exists(piece_blend) else []
            if colls:
                for c in colls:
                    kc.instance_collection(
                        layout, f"Piece_{gx}_{gy}" + ("" if c.name == "STREET" else f"_{c.name}"),
                        c, (cx, cy, elev))
                n_linked += 1
            else:
                # Placeholder plate for a not-yet-built district (grid-space bounds, to_world()
                # at the box call). Plate top sits just BELOW piece-ground level (elev) so a
                # streamed district piece lands cleanly on top instead of z-fighting /
                # half-sinking the player into the plate.
                x0 = gx * DISTRICT + SEAM / 2.0; x1 = (gx + 1) * DISTRICT - SEAM / 2.0
                y0 = gy * DISTRICT + SEAM / 2.0; y1 = (gy + 1) * DISTRICT - SEAM / 2.0
                kc.box(f"Plate_{key}_{gx}_{gy}", to_world(x0), to_world(x1),
                       to_world(y0), to_world(y1), elev - 0.6, elev - 0.1, layout, t["col"])
                n_plate += 1

            # region_ marker -> WorldZoneMarker + RegionConfig, named after the ACTUAL piece stem
            # (Piece_<gx>_<gy> — coordinate-named for EVERY district, heroes included; the hero
            # identity lives in world_grid.LANDMARKS, not the filename) so WorldBaker's idOf()
            # derives a zoneId that is EXACTLY the piece's .blend/.tscn filename stem. That
            # zoneId is what ZoneDebugOverlay prints
            # ("District: <zoneId>") and WorldZoneManager logs on load/unload — traceable straight
            # to pieces/<stem>.blend with no lookup table. Same emission path every piece uses
            # (grid district or freestanding, see the pass below) — no kind branch.
            _emit_region_marker(mk, piece)

    # Freestanding pieces registered but not part of the grid walk above (e.g. the bridge,
    # Piece_2_3_b, or any future hand-placed island) — same emission path, and a LAYOUT
    # preview link from the piece's own .blend if it has OVERLAY/MANUAL content (no Plate_
    # placeholder — a freestanding piece has no grid cell to seam-align a plate against).
    n_freestanding = 0
    for piece in pr.all_pieces():
        if piece["id"] in registered_stems:
            continue
        piece_blend = os.path.join(ROOT, "pieces", piece["id"] + ".blend")
        colls = kc.link_collections(piece_blend, PIECE_COLLS) \
            if os.path.exists(piece_blend) else []
        for c in colls:
            kc.instance_collection(layout, f"{piece['id']}_{c.name}", c, tuple(piece["position"]))
        _emit_region_marker(mk, piece)
        n_freestanding += 1

    # ArtDeck collision strips (arterial LANE markers themselves were removed in P6.8 — see
    # parse_args' docstring; the deck is a pure collision safety net, independent of any lane
    # graph, and stays regardless of what (if anything) authors traffic on top of it).
    n_deck = 0
    if opts.with_deck:
        n_deck = backbone_deck(kc.get_coll("ARTDECK"))

    # harbor: Tokyo Bay + Haneda airport island + connecting road/rail bridge.
    build_harbor(harbor, mk, land)

    # Tokyo hero-district anchors (hand-craft hooks; set asset_path to bake-swap a piece).
    for name, gx, gy, fc in LANDMARKS:
        cx, cy = district_center(gx, gy); elev = elev_at(gx, gy)
        s = bpy.data.objects.new(f"slot_{name}", None)
        s.empty_display_type = 'ARROWS'; s.empty_display_size = fc * CELL / 2.0
        s.location = (cx, cy, elev + 1.0)
        s["landmark"] = name; s["district_piece"] = piece_id_for_cell(gx, gy) + ".tscn"
        s["footprint_m"] = fc * CELL
        land.objects.link(s)

    asm.add_camera_sun(layout, target=(to_world(WORLD / 2), to_world(WORLD / 2), 0.0),
                       cam_loc=(to_world(WORLD / 2), to_world(-WORLD * 0.4), WORLD * 0.75), lens=28)

    mode = "full" if opts.with_deck else "minimal"
    summary = "  ".join(f"{k}={v}" for k, v in counts.items())
    print("WORLD: %.0fx%.0f m  mode=%s  districts=%d (%dx%d, %.0f m)  linked=%d  plates=%d  void=%d  decks=%d  landmarks=%d  freestanding=%d  %s"
          % (WORLD, WORLD, mode, GRID_N * GRID_N, GRID_N, GRID_N, DISTRICT, n_linked, n_plate,
             n_void, n_deck, len(LANDMARKS), n_freestanding, summary))


def main():
    build(parse_args())
    if bpy.app.background:
        kc.save_blend(ROOT, "world_master.blend")


if __name__ == "__main__":
    main()
