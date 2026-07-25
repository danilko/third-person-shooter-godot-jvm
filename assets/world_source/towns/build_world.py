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
    PIECE_DIR, WORLD, ORIGIN,
    BAY_Y0, BAY_Y1, ISL_X0, ISL_X1, ISL_Y0, ISL_Y1, BR_X, BR_DECK_Z, BR_RAIL_Z,
    piece_path, piece_stem, lod_low_piece_path, theme_at, elev_at, district_center, to_world,
    flank_z as _flank_z, sampled as _sampled,
)

# ---- grid geometry (all on the 168/56/7 m grid) -------------------------------
# CELL/DISTRICT/DCELLS/GRID_N/WORLD/THEMES/MAP/LANDMARKS/piece_path/theme_at/elev_at/
# district_center now live in lib/world_grid.py (shared with build_district.py, so a
# district piece built in isolation computes the SAME seam coordinates/elevations the
# master expects there — see world_grid.py's docstring).
SPAN     = DCELLS * GRID_N            # 432 cells = 3024 m ~ 3 km
SEAM     = 4.0                        # visual gap between plates so pieces read apart
PIECE_COLLS = ["STREET", "MANUAL"]    # per-district collections linked into LAYOUT (everything
                                      # exported: generated street + hand-authored content)

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
    for _, _, gx, gy, fc in LANDMARKS:
        cx, cy = int((gx + 0.5) * DCELLS), int((gy + 0.5) * DCELLS)
        h = fc // 2
        g.reserve_manual(cx - h, cy - h, cx + h, cy + h)
    return g


# Arterial half-footprint: the paved junction block is 3 cells (21 m) wide, so lane stop
# lines sit at its edge (10.5 m) + 1 m margin — NOT at the lane-count-derived radius
# road_graph would compute (8 m, inside the pavement).
ART_LANES = 2                                 # lanes per direction on the backbone
ART_STOP_RADIUS = (3 * CELL) / 2.0 + 1.0


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


def safety_floor(coll):
    """World-spanning collision-only safety slab (a `-colonly` box, so the Godot importer builds a
    CollisionShape3D and drops the visual). Districts bring ground only while streamed in, the
    arterial deck covers only the 21 m backbone strips, and the LAYOUT plates / HARBOR blockout are
    dropped at export — so anything that strays off both (a car overshooting a junction, a body
    knocked off a road) free-falls into the void forever. This slab guarantees a floor everywhere.
    Top at Z = -2.5: just BELOW every real surface (bay floor -2, deck ramps >= -1) so it never
    pokes above drivable geometry — a top at exactly 0 would stand proud of the low deck ramps.
    Authored here (not runtime Java) so it is inspectable/tunable in world_master.blend."""
    margin = 100.0
    x0, x1 = to_world(0.0) - margin, to_world(WORLD) + margin
    y0, y1 = to_world(BAY_Y0) - margin, to_world(WORLD) + margin   # include the bay/island band
    b = kc.box("SafetyFloor-colonly", x0, x1, y0, y1, -7.5, -2.5, coll, "col")
    b["proxy_for"] = "SafetyFloor"
    return b


def backbone_graph():
    """Junction-split arterial RoadGraph (lib/road_graph.py): nodes at every gridline
    crossing, one edge per inter-crossing segment, ART_LANES per direction. Replaces the
    old whole-line backbone_lanes pairs — lanes now END at each junction and continue via
    generated turn connectors (data-wired next_routes), so backbone traffic turns at
    junctions instead of sailing through and despawning at map edges only.

    Edge points are sampled every 4 cells so the emitted marker z (via _flank_z) tracks the
    seam elevation; road_graph.simplify_polyline then thins the straights back out."""
    import road_graph as rgm
    rg = rgm.RoadGraph()
    lines = [k * DCELLS * CELL for k in range(GRID_N + 1)]   # grid-space coords of arterials
    step = 4 * CELL

    def samples(a, b):
        out = list(range(int(a), int(b), int(step)))
        return out + [int(b)]

    span = SPAN * CELL
    for i, c in enumerate(lines):
        for j in range(GRID_N):
            y0, y1 = lines[j], lines[j + 1]
            pts = [(to_world(c), to_world(y), 0.0) for y in samples(y0, y1)]
            rg.add_edge(f"art_v{i}_{j}", pts, lanes_f=ART_LANES, lanes_r=ART_LANES,
                        cls='arterial', eps=1.0)
    for j, c in enumerate(lines):
        for i in range(GRID_N):
            x0, x1 = lines[i], lines[i + 1]
            pts = [(to_world(x), to_world(c), 0.0) for x in samples(x0, x1)]
            rg.add_edge(f"art_h{j}_{i}", pts, lanes_f=ART_LANES, lanes_r=ART_LANES,
                        cls='arterial', eps=1.0)
    assert span == lines[-1], "arterial span drifted off the district grid"
    return rg


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
    ships only region/landmark/water markers — no arterial lane markers, no ArtDeck collision
    strips, no SafetyFloor. `--full` restores the complete traffic/ground layer; the granular
    `--with-*` flags exist to A/B-bisect which body causes a collision artifact."""
    import argparse
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_world.py")
    ap.add_argument("--full", action="store_true",
                    help="build everything: arterial lanes + ArtDeck strips + SafetyFloor")
    ap.add_argument("--with-lanes", action="store_true",
                    help="include the arterial lane/connector/junction markers")
    ap.add_argument("--with-deck", action="store_true",
                    help="include the 14 ArtDeck collision strips")
    ap.add_argument("--with-floor", action="store_true",
                    help="include the world-spanning SafetyFloor slab")
    a = ap.parse_args(argv)
    if a.full:
        a.with_lanes = a.with_deck = a.with_floor = True
    return a


def build(opts):
    kc.setup_units()
    asm.wipe_scene()
    layout = kc.get_coll("LAYOUT")
    mk = kc.get_coll("MARKERS")
    land = kc.get_coll("LANDMARKS")
    harbor = kc.get_coll("HARBOR")

    counts = {k: 0 for k in THEMES}
    n_linked = n_plate = 0
    for gy in range(GRID_N):
        for gx in range(GRID_N):
            key = theme_at(gx, gy); t = THEMES[key]; counts[key] += 1
            cx, cy = district_center(gx, gy); elev = t["elev"]
            stem = piece_stem(gx, gy, key)

            # District layer: TRUE library link (link=True, the link_world.py mechanism) of the
            # built piece's exported content (STREET + MANUAL), instanced at its true world
            # position — the SAME (cx, cy, elev) the region_ marker below hands the runtime, so
            # what lines up here lines up in-game. Live reference: edit + save a district .blend,
            # reload the master, the edit shows; read-only here, so the master can never corrupt
            # a piece. Purely Blender-side preview — export_world.py drops LAYOUT, and linking a
            # piece's STREET pulls in neither its NEIGHBOR_REF context (separate collection) nor
            # the master itself, so a district that links the master back via
            # link_neighbors.py --master creates no load cycle.
            piece_blend = os.path.join(ROOT, "districts", stem + ".blend")
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

            # region_ marker -> WorldZoneMarker + RegionConfig. Named after the ACTUAL piece stem
            # (District_<theme>_<gx>_<gy> — coordinate-named for EVERY district, heroes included;
            # the hero identity lives in world_grid.LANDMARKS / build_district.py's plateau_json,
            # not the filename) so WorldBaker's idOf() derives a zoneId that is EXACTLY the
            # piece's .blend/.tscn filename stem. That zoneId is what ZoneDebugOverlay prints
            # ("District: <zoneId>") and WorldZoneManager logs on load/unload — traceable straight
            # to districts/<stem>.blend with no lookup table.
            r = bpy.data.objects.new(f"region_{stem}", None)
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
            # Ambient-traffic recipe → VehicleSpawnConfig at bake time (WorldBaker.buildZone).
            # traffic_route is a route-name PREFIX: WorldZoneManager.findRoute collects the
            # matching lanes near the zone and distributes spawns round-robin. Districts with
            # a hand-authored roads sidecar (districts/<piece>.roads.json → save_roads.py)
            # use their own internal lanes ("<piece_stem>__"); the rest fall back to the
            # master arterial lanes crossing the district ("art_"). Re-run this master build
            # after adding a sidecar so the meta flips. Count is further scaled by the
            # theme's vehicle_density at load.
            has_roads = os.path.exists(os.path.join(ROOT, "districts", stem + ".roads.json"))
            if has_roads:
                r["traffic_count"] = 6
                r["traffic_route"] = f"{stem}__"
            elif opts.with_lanes:
                r["traffic_count"] = 6
                r["traffic_route"] = "art_"
            else:
                # Minimal master builds no arterial lanes, so the "art_" fallback would name
                # routes that don't exist. Empty route + 0 count = WorldBaker.buildZone emits
                # no VehicleSpawnConfig at all (verified graceful) — the zone simply has no
                # ambient traffic until this district gets a roads sidecar.
                r["traffic_count"] = 0
                r["traffic_route"] = ""
            mk.objects.link(r)

    # arterial backbone: junction-split multi-lane routes + turn connectors + IntersectionZones
    # (the functional AI/traffic graph), all generated from one RoadGraph. The cosmetic Art_V/H
    # preview ribbons and the grid-locked C1 Loop ring were removed -- both were tied to the
    # district-boundary grid lines and didn't route like a real expressway (see the
    # highway/district redesign follow-up); ring_network.py itself is kept for that redesign,
    # just not invoked here for now.
    n_lane = n_conn = n_ix = n_deck = 0
    if opts.with_lanes:
        n_lane, n_conn, n_ix = asm.lay_road_graph(
            backbone_graph(), z_fn=_flank_z, z_off=0.6,
            radius_fn=lambda _rg, _node: ART_STOP_RADIUS)
    if opts.with_deck:
        n_deck = backbone_deck(kc.get_coll("ARTDECK"))
    if opts.with_floor:
        safety_floor(kc.get_coll("ARTDECK"))   # always-resident catch-all floor (ships with the deck)

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

    mode = "full" if (opts.with_lanes and opts.with_deck and opts.with_floor) else \
           ("minimal" if not (opts.with_lanes or opts.with_deck or opts.with_floor) else "partial")
    summary = "  ".join(f"{k}={v}" for k, v in counts.items())
    print("WORLD: %.0fx%.0f m  mode=%s  districts=%d (%dx%d, %.0f m)  linked=%d  plates=%d  lanes=%d  connectors=%d  junctions=%d  decks=%d  floor=%d  landmarks=%d  %s"
          % (WORLD, WORLD, mode, GRID_N * GRID_N, GRID_N, GRID_N, DISTRICT, n_linked, n_plate,
             n_lane, n_conn, n_ix, n_deck, 1 if opts.with_floor else 0, len(LANDMARKS), summary))


def main():
    build(parse_args())
    if bpy.app.background:
        kc.save_blend(ROOT, "world_master.blend")


if __name__ == "__main__":
    main()
