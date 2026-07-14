#!/usr/bin/env python3
"""
build_district.py -> districts/District_<Name>.blend

Builds ONE district piece (504 m square, or a smaller cells= for a cheap procedural fill —
see CONFIG below) at LOCAL ORIGIN, so it can be authored/baked in isolation and later streamed
in by WorldZoneManager at its zone's world position (a district's own local (0,0,0) becomes
that zone's world position — see world_grid.district_center()).

Two content sources, selected by CONFIG[name]["source"]:
  * "plateau"  — real PLATEAU precinct data (assets/world_source/plateau/extract_plateau.py JSON)
    imported via lib/plateau_import.py: real building/bridge footprints extruded to real height,
    real road polygons extruded flat (no real elevation at LOD1 unless --dem was extracted).
    cells=72 (full local-road resolution is NOT needed — roads come from the real polygon data,
    not the TownGrid solver — but the district square itself is still the full 504 m).
  * "recycled" — generic procedural filler (the 26 non-hero grid cells). A TownGrid road layout
    (cells=24 — cells=72 here was empirically confirmed to take 10+ minutes and was killed; the
    dense per-cell road/ground/sidewalk marker system does not need to run at full resolution for
    a background filler piece) + REAL recycled PLATEAU buildings (lib/recycled_buildings.py,
    curated from buildings/RecycledBuildingKit.blend) standing in for the old synthetic
    buildings.fill_frontage/tower_preset factory. A second `lib/lod_low.py` pass builds an
    independent low-detail placeholder tier (District_<Name>_LOD_LOW.tscn) for outer-radius
    streaming (see WorldZoneManager instantiateLodLow/removeLodLow).

RUN: blender --background --python towns/districts/build_district.py -- <name>
     (see tools/build_piece.sh — the one-command build+export+bake+navmesh loop)
"""
import bpy, os, sys, math, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import road_network as rn
import assemble as asm
import buildings as bd
import recycled_buildings as rb
import plateau_import as pi
import lod_low as ll
from world_grid import (
    CELL, DISTRICT, GRID_N, THEMES, LANDMARKS, PIECE_DIR,
    piece_path, lod_low_piece_path, theme_at, elev_at, district_center, seam_route_name,
)
import world_grid as wg

# ── CONFIG ────────────────────────────────────────────────────────────────────────────────
# Every entry: piece (output .blend/.tscn stem), cells (TownGrid resolution — 72 = full-res /
# not used by plateau pieces' own roads, 24 = cheap filler), source, gx/gy (this piece's grid
# cell — must match world_grid.theme_at(gx,gy) for a "recycled" entry, or its LANDMARKS/explicit
# override for a real-data piece that keeps the natural grid theme), theme.
#
# 10 real PLATEAU precincts. plateau_json points at the extracted JSON (extract_plateau.py);
# `landmark` (tokyotower only) overlays a hand-modeled building-tier asset the real extraction
# can't produce (Tokyo Tower is a lattice structure with no solid footprint).
CONFIG = {
    # Hero precincts are coordinate-named like every other piece (District_<theme>_<gx>_<gy>);
    # the hero identity lives in the CONFIG key + plateau_json, not the filename — the old
    # District_Shibuya-style hero filenames were renamed for one consistent naming scheme
    # (see world_grid.piece_stem / LANDMARKS).
    "shibuya":        dict(piece="District_city_1_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "shibuya.json"),
                            gx=1, gy=1, theme="city"),
    "tokyostation":   dict(piece="District_city_2_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "tokyostation.json"),
                            gx=2, gy=2, theme="city"),
    "akihabara":      dict(piece="District_city_3_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "akihabara.json"),
                            gx=3, gy=3, theme="city"),
    "imperialpalace": dict(piece="District_city_2_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "imperialpalace.json"),
                            gx=2, gy=3, theme="city"),
    "tokyotower":     dict(piece="District_city_3_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "tokyotower_full.json"),
                            gx=3, gy=2, theme="city",
                            landmark=dict(blend=os.path.join(ROOT, "buildings", "PLATEAU_TokyoTower.blend"),
                                          collection="TokyoTower")),
    "dotonbori":      dict(piece="District_harbor_3_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "dotonbori.json"),
                            gx=3, gy=0, theme="harbor"),
    "city_2_1":       dict(piece="District_city_2_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "kabukicho.json"),
                            gx=2, gy=1, theme="city"),
    "resid_1_2":      dict(piece="District_resid_1_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "ueno.json"),
                            gx=1, gy=2, theme="resid"),
    "mtn_1_4":        dict(piece="District_mtn_1_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "akagitouge.json"),
                            gx=1, gy=4, theme="mtn"),
    "snow_0_5":       dict(piece="District_snow_0_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "osakacastle.json"),
                            gx=0, gy=5, theme="snow"),
    # Keihinjima (京浜島) -- real industrial island in Ota-ku, Tokyo Bay (anchor centred on the
    # actual building centroid within PLATEAU mesh 533926, not the island's nominal address
    # point -- that fell in a gap between building tiles). Real anchor ~139.7838E/35.5485N.
    # Sparse real factory/warehouse footprints (16 buildings/450m radius vs. Shibuya's 230) plus
    # 14 real pipe-rack/conveyor "bridges" between plants and one ~116m tower (crane/stack) --
    # authentic industrial density, not padded out with recycled-kit filler.
    "industry_5_1":   dict(piece="District_industry_5_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "keihinjima.json"),
                            gx=5, gy=1, theme="industry"),
    # Same PLATEAU mesh (533926), a different real building-dense tile ~700m east of Keihinjima
    # in the same Ota-ku Tokyo Bay industrial cluster -- second real industrial precinct so both
    # industry_ grid cells get authentic data instead of one real + one recycled-kit filler.
    "industry_4_2":   dict(piece="District_industry_4_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "showajima.json"),
                            gx=4, gy=2, theme="industry"),
    # Ginza (銀座) -- the last remaining "city"-themed grid cell without real data (every other
    # city_ cell already has a named real precinct: shibuya/city_2_1/tokyostation/tokyotower/
    # imperialpalace/akihabara). Extremely dense real commercial core -- 995 buildings/450m
    # radius, tallest 204.5m -- denser than any other precinct in the map.
    "city_3_1":       dict(piece="District_city_3_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "ginza.json"),
                            gx=3, gy=1, theme="city"),
    # Real Tokyo Bay waterfront precincts (PLATEAU mesh 533936) for all 6 "harbor"-themed grid
    # cells -- odaiba/toyosu/harumi/kachidoki (dense residential-tower waterfront, up to 1948
    # buildings/450m) plus sparser ariake/shinonome fill out the rest.
    "harbor_0_0":     dict(piece="District_harbor_0_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "odaiba.json"),
                            gx=0, gy=0, theme="harbor"),
    "harbor_1_0":     dict(piece="District_harbor_1_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "toyosu.json"),
                            gx=1, gy=0, theme="harbor"),
    "harbor_2_0":     dict(piece="District_harbor_2_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "harumi.json"),
                            gx=2, gy=0, theme="harbor"),
    "harbor_4_0":     dict(piece="District_harbor_4_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "ariake.json"),
                            gx=4, gy=0, theme="harbor"),
    "harbor_5_0":     dict(piece="District_harbor_5_0", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "kachidoki.json"),
                            gx=5, gy=0, theme="harbor"),
    "harbor_5_2":     dict(piece="District_harbor_5_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "shinonome.json"),
                            gx=5, gy=2, theme="harbor"),
    # Real residential-ward precincts (PLATEAU mesh 533945, western Tokyo) for 3 of the 6
    # remaining "resid"-themed grid cells.
    "resid_0_1":      dict(piece="District_resid_0_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "nakano.json"),
                            gx=0, gy=1, theme="resid"),
    "resid_4_1":      dict(piece="District_resid_4_1", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "nerima.json"),
                            gx=4, gy=1, theme="resid"),
    "resid_1_3":      dict(piece="District_resid_1_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "suginami.json"),
                            gx=1, gy=3, theme="resid"),
    "resid_4_3":      dict(piece="District_resid_4_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "itabashi.json"),
                            gx=4, gy=3, theme="resid"),
    "resid_3_4":      dict(piece="District_resid_3_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "kita.json"),
                            gx=3, gy=4, theme="resid"),
    "resid_4_4":      dict(piece="District_resid_4_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "nishitokyo.json"),
                            gx=4, gy=4, theme="resid"),
    # Okutama-machi (奥多摩町) -- genuine mountain village in western Tokyo, real PLATEAU
    # CityGML coverage (roads only -- like mtn_1_4/akagitouge, this municipality's PLATEAU
    # package ships CityGML bldg (not the pre-made OBJ Tokyo23ku has), so no real buildings;
    # real winding mountain-road curvature only, same precedent already established).
    "mtn_0_4":        dict(piece="District_mtn_0_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamalake.json"),
                            gx=0, gy=4, theme="mtn"),
    "mtn_1_5":        dict(piece="District_mtn_1_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamapass.json"),
                            gx=1, gy=5, theme="mtn"),
    "mtn_2_5":        dict(piece="District_mtn_2_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamaridge.json"),
                            gx=2, gy=5, theme="mtn"),
    # Same Okutama-machi PLATEAU coverage, 8 more distinct real mountain-road clusters across
    # the town for every remaining "rural"-themed grid cell -- real curvature, no buildings
    # (same CityGML-only limitation as the mtn_ cells above).
    "rural_0_2":      dict(piece="District_rural_0_2", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamavalley.json"),
                            gx=0, gy=2, theme="rural"),
    "rural_0_3":      dict(piece="District_rural_0_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamariver.json"),
                            gx=0, gy=3, theme="rural"),
    "rural_5_3":      dict(piece="District_rural_5_3", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamaforest.json"),
                            gx=5, gy=3, theme="rural"),
    "rural_2_4":      dict(piece="District_rural_2_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamaeast.json"),
                            gx=2, gy=4, theme="rural"),
    "rural_5_4":      dict(piece="District_rural_5_4", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamahighland.json"),
                            gx=5, gy=4, theme="rural"),
    "rural_3_5":      dict(piece="District_rural_3_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamapeak.json"),
                            gx=3, gy=5, theme="rural"),
    "rural_4_5":      dict(piece="District_rural_4_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamameadow.json"),
                            gx=4, gy=5, theme="rural"),
    "rural_5_5":      dict(piece="District_rural_5_5", cells=72, source="plateau",
                            plateau_json=os.path.join(ROOT, "plateau", "data", "okutamaspring.json"),
                            gx=5, gy=5, theme="rural"),
}

# 26 generic filler districts — every remaining (gx,gy) cell in the 6x6 grid, themed per
# world_grid.theme_at(). Same recycled-real-building factory for every theme; only the
# reserved tower kinds + interior block size differ.
_THEME_FILL_DEFAULTS = {
    "city":     dict(block=4, towers=["office", "neon", "mixed", "pencil"]),
    "resid":    dict(block=4, towers=["resi", "resi", "resi", "mixed"]),
    "harbor":   dict(block=4, towers=["resi", "mixed"]),
    "rural":    dict(block=6, towers=["resi"]),
    "mtn":      dict(block=6, towers=[]),
    "snow":     dict(block=6, towers=[]),
    # Bigger blocks (warehouse-scale plots), few/no residential-style towers — "office"'s
    # footprint (bx=6,by=6, the largest preset) stands in for a warehouse shell; the recycled
    # factory only reuses TOWER_PRESETS for footprint SIZE, not the synthetic facade.
    "industry": dict(block=6, towers=["office"]),
}
_covered = {(cfg["gx"], cfg["gy"]) for cfg in CONFIG.values()}
for _gy in range(wg.GRID_N):
    for _gx in range(wg.GRID_N):
        if (_gx, _gy) in _covered:
            continue
        _theme = wg.theme_at(_gx, _gy)
        _defaults = _THEME_FILL_DEFAULTS[_theme]
        _key = f"{_theme}_{_gx}_{_gy}"
        CONFIG[_key] = dict(piece=f"District_{_theme}_{_gx}_{_gy}", cells=24, source="recycled",
                             block=_defaults["block"], scramble=False, rail=False,
                             towers=_defaults["towers"], gx=_gx, gy=_gy, theme=_theme)


# ── Recycled/procedural TownGrid layout ──────────────────────────────────────────────────

def make_grid(cfg):
    """A simple border-loop + interior cross layout on `cfg["cells"]` cells, block-quantized by
    `cfg["block"]` — enough structure for auto_lots() to find contiguous street frontage and for
    a handful of interior blocks to be reserved for towers. Local origin = district centre."""
    n = cfg["cells"]
    b = cfg["block"]
    half = n // 2
    g = rn.TownGrid()

    # Perimeter loop (2-lane locals) — every seam edge carries a road so a neighbour's seam
    # connector stub always lands on pavement, not an empty lot.
    g.road_h(0, 0, n, lanes=2)
    g.road_h(n, 0, n, lanes=2)
    g.road_v(0, 0, n, lanes=2)
    g.road_v(n, 0, n, lanes=2)

    # Interior cross at the block-quantized centre (keeps the block/2 * 2 == block identity the
    # original CONFIG comment warns about) + a ring one block in from the perimeter, carving the
    # interior into reservable/buildable quadrant blocks.
    mid = (n // b // 2) * b
    g.road_h(mid, 0, n, lanes=1)
    g.road_v(mid, 0, n, lanes=1)
    ring = b
    if ring < mid:
        g.road_h(ring, ring, n - ring, lanes=1)
        g.road_h(n - ring, ring, n - ring, lanes=1)
        g.road_v(ring, ring, n - ring, lanes=1)
        g.road_v(n - ring, ring, n - ring, lanes=1)

    g.auto_lots()
    return g


def _reserve_tower_blocks(g, cfg, n, b):
    """One reserved b x b block per requested tower kind, spaced along the interior ring so
    place_on_block's road-facing setback math has a real adjacent road cell to face."""
    mid = (n // b // 2) * b
    slots = [
        (mid - b, mid - b), (mid + b, mid - b),
        (mid - b, mid + b), (mid + b, mid + b),
    ]
    tblocks = []
    for i, kind in enumerate(cfg.get("towers", [])):
        if i >= len(slots):
            break
        cx, cy = slots[i]
        cells = [(x, y) for x in range(cx, cx + b) for y in range(cy, cy + b)]
        g.reserve(cx, cy, cx + b, cy + b, f"tower_{i}")
        tblocks.append((kind, cells))
    return tblocks


def build_recycled(cfg, coll, mk_coll):
    n = cfg["cells"]
    b = cfg["block"]
    g = make_grid(cfg)
    tblocks = _reserve_tower_blocks(g, cfg, n, b)

    asm.lay_ground(g, coll)
    asm.lay_roads(g, coll)
    asm.lay_sidewalks(g, coll)
    asm.lay_lane_markers(g, coll)

    seed = abs(hash(cfg["piece"])) % 10000
    n_front = rb.build_buildings_recycled(coll, g, seed=seed)
    n_tow = rb.build_towers_recycled(coll, tblocks, seed=seed + 1)
    # The dense road/ground core only covers cfg["cells"] (cheap — cells=72 here was empirically
    # too slow, see CONFIG's own comment), but every district — recycled or not — is still the
    # TRUE 504m square (DISTRICT) the world_master.blend Plate_<theme> placeholder promises.
    # build_outskirts_recycled fills that remaining outer band with background scenery only
    # (no road infrastructure), per its own docstring.
    core_half = (n * CELL) / 2.0
    n_out = rb.build_outskirts_recycled(coll, 0.0, DISTRICT / 2.0, core_half, seed=seed + 2)

    return g, tblocks, n_front, n_tow, n_out


def build_recycled_lod_low(cfg, coll, g):
    n_roads = ll.build_roads_lod_low(coll, g)
    n_bldg = ll.build_buildings_lod_low(coll, g)
    tblocks = _reserve_tower_blocks(rn.TownGrid(), cfg, cfg["cells"], cfg["block"])
    n_tow = ll.build_towers_lod_low(coll, tblocks)
    return n_roads, n_bldg, n_tow


# ── PLATEAU (real-data) districts ────────────────────────────────────────────────────────

def build_plateau(cfg, coll):
    data = pi.load(cfg["plateau_json"])
    edge_half = DISTRICT / 2.0
    # Seam elevation targets (LOCAL frame = world flank elevation minus this district's own
    # theme elev): the same per-seam height world_grid.flank_z gives the master's arterials,
    # so DEM ground tapers to meet BOTH the neighbouring district's ground and the deck.
    # theme_at clamps off-grid, so a map-edge border simply tapers to the district's own datum.
    gx, gy, own = cfg["gx"], cfg["gy"], wg.elev_at(cfg["gx"], cfg["gy"])
    seam_targets = {
        "+x": (own + wg.elev_at(gx + 1, gy)) / 2.0 - own,
        "-x": (own + wg.elev_at(gx - 1, gy)) / 2.0 - own,
        "+y": (own + wg.elev_at(gx, gy + 1)) / 2.0 - own,
        "-y": (own + wg.elev_at(gx, gy - 1)) / 2.0 - own,
    }
    stats = pi.import_precinct(coll, data, 0.0, 0.0, tag=cfg["piece"], edge_half=edge_half,
                               seam_targets=seam_targets)

    landmark = cfg.get("landmark")
    landmark_name = None
    if landmark:
        kc.place_landmark(coll, landmark["blend"], landmark["collection"], (0.0, 0.0, 0.0))
        landmark_name = landmark["collection"]

    return stats, landmark_name


# ── Safety-net ground plane ──────────────────────────────────────────────────────────────

def add_ground_safety_plane(cfg, coll):
    """A large collision-only floor spanning the district's full 504 m footprint, just below
    ground level. Real geometry (roads/buildings/PLATEAU extraction) sits on top of it; anywhere
    that real geometry has a gap — a PLATEAU precinct's terrain=0 with no continuous ground mesh
    (extract_plateau.py's `--dem` wasn't used, so no real terrain was extracted), or an
    under-detailed recycled outskirts area — the player lands on this instead of falling through
    into the void. Collision-only (kc.colonly's "-colonly" suffix convention: Godot's import drops
    the visual, keeps a CollisionShape3D) — deliberately invisible, a pure stopgap.

    SKIPPED for a PLATEAU precinct whose real DEM terrain fully covers the district square
    (stats["terrain_covers_square"], see extract_plateau.py --augment / import_precinct) — there
    the real terrain mesh IS the ground (visual + collision), and this flat slab at elev-1.0
    would poke above it as an invisible hovering floor wherever the real ground dips lower.
    A partial-coverage terrain (e.g. a legacy extraction whose DEM radius stops short of the
    square's corners) still gets the plane, exactly as before."""
    half = DISTRICT / 2.0
    elev = elev_at(cfg["gx"], cfg["gy"])
    visual = kc.box(f"{cfg['piece']}_GroundSafety", -half, half, -half, half,
                     elev - 1.0, elev - 0.8, coll, "concrete")
    kc.colonly(visual, coll=coll)
    bpy.data.objects.remove(visual, do_unlink=True)


# ── Hand-authored road spines (districts/<piece>.roads.json sidecar) ────────────────────
#
# PLATEAU districts have no solver grid and their road meshes are raw polygon slabs with no
# centerlines — so internal traffic comes from HAND-AUTHORED centerline curves drawn over
# the road meshes in Blender (road_<name> poly/bezier curves + lanes/oneway/class custom
# props). Because this build REGENERATES the .blend (wipe_scene), the curves persist in a
# git-diffable JSON sidecar, not the blend: edit curves → tools/save_roads.py exports the
# sidecar → this build re-imports them into a ROADS_SRC collection (round-trip editing,
# excluded from the glTF export) and generates the full traffic layer from them
# (lib/road_graph.from_curves → junction-split lanes + turn connectors + intersection
# markers, all namespaced lane_<piece>__…). No sidecar = arterials-only district, no error.

def load_roads_sidecar(cfg):
    path = os.path.join(ROOT, "districts", cfg["piece"] + ".roads.json")
    if not os.path.exists(path):
        return None
    import json
    with open(path) as f:
        return json.load(f)


def import_roads_src(data):
    """Rebuild the sidecar's road_* curves as editable POLY curve objects in ROADS_SRC."""
    src = kc.get_coll("ROADS_SRC")
    for c in data.get("curves", []):
        cu = bpy.data.curves.new(c["name"], 'CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('POLY')
        pts = c["points"]
        sp.points.add(len(pts) - 1)
        for i, (x, y, z) in enumerate(pts):
            sp.points[i].co = (x, y, z, 1.0)
        ob = bpy.data.objects.new(c["name"], cu)
        ob["lanes"] = int(c.get("lanes", 1))
        ob["oneway"] = bool(c.get("oneway", False))
        ob["class"] = c.get("class", "local")
        src.objects.link(ob)
    return len(data.get("curves", []))


def emit_authored_roads(data):
    """Sidecar curves → RoadGraph → traffic markers. Route stems drop the road_ prefix to
    stay inside Blender's 63-char object-name cap once the piece prefix is added."""
    import road_graph as rgm
    curves = []
    for c in data.get("curves", []):
        stem = c["name"]
        stem = stem[len("road_"):] if stem.startswith("road_") else stem
        curves.append((stem, [tuple(p) for p in c["points"]],
                       {"lanes": c.get("lanes", 1), "oneway": c.get("oneway", False),
                        "class": c.get("class", "local")}))
    return asm.lay_road_graph(rgm.from_curves(curves), z_off=0.3)


# ── Seams (cross-district route continuity — see world_grid.seam_route_name) ────────────

def emit_seam_routes(cfg, mk_coll):
    """One connector stub per district edge (N/S/E/W) — a short lane_ empty pair just inside
    the seam, named per world_grid.seam_route_name so both neighbours' VehicleRoute.nextRoutes
    resolve to each other once both pieces are streamed in — plus a .seam.json sidecar
    tools/check_seams.py cross-validates against the neighbour's own recorded edge."""
    gx, gy, theme = cfg["gx"], cfg["gy"], cfg["theme"]
    half = DISTRICT / 2.0
    elev = elev_at(gx, gy)
    manifest = dict(piece=cfg["piece"], gx=gx, gy=gy, theme=theme, cells=cfg["cells"], elev=elev,
                     edges={})
    if "plateau_json" in cfg:
        manifest["plateau_source"] = os.path.splitext(os.path.basename(cfg["plateau_json"]))[0]

    n = 0
    for side, (nx, ny), (ex, ey) in (
        ("N", (gx, gy + 1), (0.0,  half)),
        ("S", (gx, gy - 1), (0.0, -half)),
        ("E", (gx + 1, gy), ( half, 0.0)),
        ("W", (gx - 1, gy), (-half, 0.0)),
    ):
        if not (0 <= nx < GRID_N and 0 <= ny < GRID_N):
            continue
        n_elev = elev_at(nx, ny)
        exit_route = seam_route_name(gx, gy, nx, ny, 0, "exit_lo" if (gx, gy) <= (nx, ny) else "exit_hi")
        entry_route = seam_route_name(gx, gy, nx, ny, 0, "entry_lo" if (gx, gy) <= (nx, ny) else "entry_hi")
        expects_next = seam_route_name(gx, gy, nx, ny, 0, "entry_hi" if (gx, gy) <= (nx, ny) else "entry_lo")

        # exit_route: heading OUT toward the edge (0.90 -> 1.00, ENDS ON the boundary).
        # entry_route: starting AT the edge (1.00 -> 0.90), heading back IN — the two
        # directions of travel this district owns on its own side of the seam. Fracs reach
        # 1.00 so this exit's end coincides with the neighbour's entry start (both districts
        # abut on the seam line) — the old 0.65–0.85 stubs left a ~75 m dead gap a chained
        # car had to teleport across. The exit stub carries the actual runtime chain:
        # next_routes = the NEIGHBOUR's entry route name (resolves once both stream in;
        # unresolved = harmless despawn-at-end, same as a map edge). lane_offset=-1.75 is
        # deliberate here (unlike solver lanes, whose positions are truth): stubs sit on the
        # road CENTRELINE and rely on the runtime shift. VehicleRoute offsets along the RIGHT
        # normal of travel, so keep-left (northbound rides the west lane, matching
        # backbone_lanes) needs the NEGATIVE sign — the old implicit baker default (+1.75)
        # had seam traffic on the wrong (right-hand-drive) side.
        for route, fracs, props in (
            (exit_route, (0.90, 1.00),
             dict(lane_offset=-1.75, end_behavior="CHAIN", next_routes=expects_next)),
            (entry_route, (1.00, 0.90),
             dict(lane_offset=-1.75)),
        ):
            for i, frac in enumerate(fracs):
                e = bpy.data.objects.new(f"lane_{route}_{i}", None)
                e.empty_display_size = 1.0
                e.location = (ex * frac if side in ("E", "W") else ex,
                              ey * frac if side in ("N", "S") else ey, elev + 0.6)
                if i == 0:
                    for k, v in props.items():
                        e[k] = v
                mk_coll.objects.link(e)
            n += 1

        manifest["edges"][side] = dict(
            neighbour=[nx, ny], world_x=ex, world_y=ey, elev=elev, neighbour_elev=n_elev,
            lanes=1, exit_route=exit_route, entry_route=entry_route, expects_next=expects_next)

    return n, manifest


# ── Driver ────────────────────────────────────────────────────────────────────────────────

def build(name):
    cfg = CONFIG[name]
    # Regenerate IN PLACE when the piece .blend already exists: open it and clear only the
    # PROCEDURAL collections, so hand-authored content survives a rebuild — the MANUAL
    # collection (your own meshes/markers; exported + baked like any generated content) and
    # NEIGHBOR_REF (tools/link_neighbors.py's linked seam-editing context; export-dropped).
    # Same preserve idiom as assemble.setup(reopen=...) in the towns generator.
    existing = os.path.join(ROOT, "districts", cfg["piece"] + ".blend")
    if os.path.exists(existing):
        bpy.ops.wm.open_mainfile(filepath=existing)
        for cn in ("STREET", "MARKERS", "STREET_LOD_LOW", "ROADS_SRC"):
            asm._clear_coll(cn)
        # purge data orphaned by the clear (freshly regenerated below); local blocks only —
        # library-linked data belongs to the NEIGHBOR_REF references.
        for data in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.images):
            for blk in list(data):
                if blk.users == 0 and blk.library is None:
                    data.remove(blk)
    else:
        asm.wipe_scene()
    kc.setup_units()
    # Namespace every district-local route name (lane_<piece>__<route>_<n>): recycled
    # districts emit identical local names, and VehicleRoute.findRoute/pickNextRoute search
    # the LIVE scene tree by name — two streamed districts would cross-resolve otherwise.
    # Seam routes bypass the prefix (their names are the cross-district contract).
    asm.set_route_prefix(cfg["piece"])
    # Marker mode: instancer()/kit placement emit instance_<piece>/mmesh_<piece> EMPTIES
    # (asset_path = kc.MARKER_KIT_DIR + <piece>.glb) instead of GN-instancing a Blender-loaded
    # kit source — the Java WorldBaker resolves those against res://.../world/kit/ at bake time.
    # No consolidated kit .blend to load/hide here (that source-append path is for the OLD
    # real-geometry-in-Blender mode; this project's kit lives as individual kit/*.glb files).
    kc.MARKER_MODE = True
    coll = kc.get_coll("STREET")
    mk_coll = kc.get_coll("MARKERS")

    stats = ""
    has_lod_low = False
    terrain_is_ground = False
    if cfg["source"] == "plateau":
        pstats, landmark_name = build_plateau(cfg, coll)
        terrain_is_ground = pstats.get("terrain_covers_square", False)
        stats = (f"[PLATEAU: {pstats.get('buildings', 0)}/{pstats.get('buildings_total', 0)} buildings, "
                  f"{pstats.get('bridges', 0)} bridges, {pstats.get('roads', 0)}/"
                  f"{pstats.get('roads_total', 0)} roads, terrain={pstats.get('terrain_triangles', 0)} tris"
                  f"{' (GROUND)' if terrain_is_ground else ''}, "
                  f"edge_clipped={pstats.get('edge_clipped', 0)}]")
    else:
        g, tblocks, n_front, n_tow, n_out = build_recycled(cfg, coll, mk_coll)
        stats = (f"frontage={n_front} towers={n_tow} outskirts={n_out} "
                  f"scramble={cfg.get('scramble', False)} rail={cfg.get('rail', False)}")
        lod_coll = kc.get_coll("STREET_LOD_LOW")
        n_roads, n_bldg, n_tow_lod = build_recycled_lod_low(cfg, lod_coll, g)
        stats += f" lod_low[roads={n_roads} buildings={n_bldg} towers={n_tow_lod}]"
        has_lod_low = True

    if not terrain_is_ground:
        add_ground_safety_plane(cfg, coll)

    n_seam, manifest = emit_seam_routes(cfg, mk_coll)
    stats += f" seam_routes={n_seam}"

    roads = load_roads_sidecar(cfg)
    if roads:
        import_roads_src(roads)
        n_rd, n_cn, n_jn = emit_authored_roads(roads)
        stats += f" roads[lanes={n_rd} connectors={n_cn} junctions={n_jn}]"
    if cfg["source"] == "plateau" and landmark_name:
        stats += f" landmark={landmark_name}"

    print("DISTRICT %s: %.0fm cells=%d %s"
          % (name, cfg["cells"] * CELL, cfg["cells"], stats))

    # view-layer objects only: with NEIGHBOR_REF present, bpy.data.objects also holds
    # library-linked datablocks, and select_set raises on objects not in the view layer.
    # Snapshot + skip None: object removals during the regen leave stale None slots in
    # view_layer.objects until the next depsgraph update (Blender 5.x) — same guard as
    # export_world.py's deselect loop.
    for o in list(bpy.context.view_layer.objects):
        if o is not None:
            o.select_set(False)
    kc.save_blend(os.path.join(ROOT, "districts"), cfg["piece"] + ".blend")
    with open(os.path.join(ROOT, "districts", cfg["piece"] + ".seam.json"), "w") as f:
        import json
        json.dump(manifest, f, indent=2)

    return cfg, manifest


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[0] if argv else "shibuya"
    cfg, manifest = build(name)
    if bpy.app.background:
        print("PIECE=" + cfg["piece"])       # parsed by tools/build_piece.sh


if __name__ == "__main__":
    main()
