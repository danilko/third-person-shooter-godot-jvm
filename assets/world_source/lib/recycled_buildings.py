#!/usr/bin/env python3
"""
recycled_buildings.py -- replaces the SYNTHETIC procedural building factory
(buildings.fill_frontage / buildings.tower_preset) for the 26 generic filler districts with REAL
PLATEAU buildings recycled from buildings/RecycledBuildingKit.blend (see
buildings/build_recycled_kit.py) -- 55 real, already-low-poly buildings curated from data already
extracted for the 10 real precincts, spanning low/mid/high-rise and a handful of genuine towers
(up to Shibuya's real 226.8m).

Reuses the IDENTICAL frontage-run walk (`bd._frontage_runs`) and reserved-tower-block placement
(`bd.place_on_block`) build_district.py's procedural path and lib/lod_low.py's placeholder tier
both already share -- only the building FACTORY differs: instead of a fixed-bay synthetic box or a
full kit-instanced shaft, each slot is filled by APPENDING one of the curated real-building
collections (best-fit by real footprint, chosen from buildings/RecycledBuildingKit.json's index --
never stretched/scaled, per the "keep original object data as much as possible" goal) at that
slot's position, rotated (never resized) to face the frontage/reserved-block direction.

Unlike the bay-grid-quantized synthetic walk, a real building's footprint isn't a bay multiple, so
the frontage walk here steps by each PICKED building's own real width instead of a fixed bay count.
lib/lod_low.py is unaffected -- it already only needs the same road cells/frontage runs/rng
sequence to mirror, not matching geometry, so it keeps using its own synthetic box placeholder tier
regardless of what the full-detail factory is.
"""
import json
import math
import os
import random

import bpy
import kit_common as kc
import buildings as bd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                          # assets/world_source
KIT_BLEND = os.path.join(ROOT, "buildings", "RecycledBuildingKit.blend")
KIT_JSON = os.path.join(ROOT, "buildings", "RecycledBuildingKit.json")

CELL = kc.CELL
BAY, R_H = kc.R_BAY, kc.R_H

_kit_index_cache = None


def _kit_index():
    global _kit_index_cache
    if _kit_index_cache is None:
        with open(KIT_JSON) as f:
            _kit_index_cache = json.load(f)
    return _kit_index_cache


def _candidates(bucket_names, avail_w, avail_d):
    """Every kit asset whose real footprint fits within (avail_w, avail_d) in EITHER orientation
    (its own w/d, or swapped -- a 90-degree placement) -- never stretched. Returns
    [(name, placed_w, placed_d, needs_extra_90), ...] where placed_w/placed_d are already the
    as-placed (post-swap) dimensions along (frontage, depth)."""
    idx = _kit_index()
    out = []
    for name, info in idx.items():
        if info["bucket"] not in bucket_names:
            continue
        w, d = info["footprint_w"], info["footprint_d"]
        if w <= avail_w and d <= avail_d:
            out.append((name, w, d, False))
        if d <= avail_w and w <= avail_d:
            out.append((name, d, w, True))
    return out


def _pick_building(rng, bucket_names, avail_w, avail_d):
    """Best-fit: prefer whichever candidate uses the most of the available lot (largest area,
    picked among near-ties for variety), falling back to the smallest asset in the bucket
    (accepting overhang) if nothing fits at all -- mirrors lod_low.py's own bay-count clamp for
    the same edge case (a lot too small for anything in the bucket)."""
    cands = _candidates(bucket_names, avail_w, avail_d)
    if cands:
        cands.sort(key=lambda c: c[1] * c[2], reverse=True)
        best_area = cands[0][1] * cands[0][2]
        top = [c for c in cands if c[1] * c[2] >= best_area * 0.7]
        return rng.choice(top)
    idx = _kit_index()
    pool = [n for n, i in idx.items() if i["bucket"] in bucket_names]
    smallest = min(pool, key=lambda n: idx[n]["footprint_w"] * idx[n]["footprint_d"])
    info = idx[smallest]
    return (smallest, info["footprint_w"], info["footprint_d"], False)


def _place_recycled(coll, collection_name, loc_xy, rot_deg):
    """Append one recycled-building collection (link=False -- becomes locally-owned real geometry,
    same convention as build_district.place_landmark) and place it at world (x,y), rotated
    `rot_deg` about Z. The asset was built footprint-centred at local origin (see
    build_recycled_kit.py), so rotate-in-place-then-translate keeps its real footprint centre
    exactly at loc_xy with no distortion."""
    with bpy.data.libraries.load(KIT_BLEND, link=False) as (src, dst):
        if collection_name in src.collections:
            dst.collections = [collection_name]
    for picked_coll in dst.collections:
        if picked_coll is None:
            continue
        for obj in list(picked_coll.objects):
            coll.objects.link(obj)
            if obj.parent is None:
                obj.rotation_euler = (0.0, 0.0, math.radians(rot_deg))
                obj.location = (loc_xy[0], loc_xy[1], 0.0)
    for c in list(dst.collections):
        if c is not None and c.name in bpy.data.collections and not c.objects:
            bpy.data.collections.remove(c)


def build_buildings_recycled(coll, grid, seed=11):
    """Real-building counterpart to buildings.fill_frontage. Same bd._frontage_runs(grid) walk as
    the procedural path and lib/lod_low.py both use, but steps by each picked building's own real
    footprint width (not a fixed bay count) and stamps a best-fit recycled asset per slot instead
    of a synthetic kit shell."""
    rng = random.Random(seed)
    n = 0
    for rdir, cells in bd._frontage_runs(grid):
        ax, ay = bd.DVEC[rdir]
        u = (0, 1) if ax else (1, 0)
        cells = sorted(cells, key=lambda c: c[0] * u[0] + c[1] * u[1])
        nb = (cells[0][0] + ax, cells[0][1] + ay)
        clear = bd.ALLEY_CLEAR if grid.class_of(nb) == 'alley' else bd.SIDEWALK_CLEAR
        run_depth = min(bd._lot_depth(grid, c, ax, ay) for c in cells)
        max_D = run_depth * CELL - clear
        head = clear if (cells[0][0] - u[0], cells[0][1] - u[1]) in grid.roads else 0.0
        tail = clear if (cells[-1][0] + u[0], cells[-1][1] + u[1]) in grid.roads else 0.0
        ox = cells[0][0] * CELL - u[0] * (CELL / 2) + u[0] * head
        oy = cells[0][1] * CELL - u[1] * (CELL / 2) + u[1] * head
        ulen = len(cells) * CELL - head - tail
        s = 0.0
        while ulen - s >= 4.0:
            name, w, d, swap = _pick_building(rng, ("low", "mid"), ulen - s, max_D)
            off = CELL / 2 - clear - d / 2.0
            cux = ox + u[0] * (s + w / 2) + ax * off
            cuy = oy + u[1] * (s + w / 2) + ay * off
            rot = bd.ROT_FOR_DIR[rdir] + (90 if swap else 0)
            _place_recycled(coll, name, (cux, cuy), rot)
            n += 1
            s += w + 0.5   # small real-footprint-to-real-footprint gap, not butted flush
    return n


def build_outskirts_recycled(coll, ax, reach, core_half, connector_half_w=20.0, spacing=48.0,
                              margin=6.0, edge_margin=20.0, seed=17):
    """Scatter recycled low/mid buildings across the area OUTSIDE the dense road/ground core but
    still inside the TRUE district square (`reach` from centre `ax` on both axes) -- filling the
    rest of the 504 m footprint the Plate_<theme> placeholder in world_master.blend promises,
    WITHOUT touching the expensive per-cell road/ground/sidewalk marker system
    (kit_common._emit_markers) that caps the dense core at cells=24 (build_district.CONFIG's own
    comment: cells=72 there took 10+ minutes and was killed -- re-confirmed empirically before this
    was written, see the plan). This is just direct library-append placement (cheap regardless of
    count, no markers involved), so it can freely cover the full footprint.

    Skips the core box and the 4 cross-shaped connector strips `emit_seam_routes()` lays along
    the centre lines, so nothing overlaps the piece's own road network; also skips within
    `edge_margin` of the true district boundary (same convention plateau_import.py uses) so a
    neighbouring piece's connector-stub always has clear ground to land on. No road/sidewalk/curb
    out here -- just buildings on flat ground, background scenery visible from the connector road."""
    rng = random.Random(seed)
    n = 0
    y = ax - reach + spacing / 2.0
    while y < ax + reach:
        x = ax - reach + spacing / 2.0
        while x < ax + reach:
            dx = x - ax + rng.uniform(-spacing * 0.3, spacing * 0.3)
            dy = y - ax + rng.uniform(-spacing * 0.3, spacing * 0.3)
            in_core = abs(dx) < core_half + margin and abs(dy) < core_half + margin
            in_connector = abs(dx) < connector_half_w + margin or abs(dy) < connector_half_w + margin
            near_edge = abs(dx) > reach - edge_margin or abs(dy) > reach - edge_margin
            if not in_core and not in_connector and not near_edge:
                name, w, d, swap = _pick_building(rng, ("low", "mid"), spacing - 4.0, spacing - 4.0)
                rot = rng.choice([0, 90, 180, 270]) + (90 if swap else 0)
                _place_recycled(coll, name, (ax + dx, ax + dy), rot)
                n += 1
            x += spacing
        y += spacing
    return n


def _corner_to_center(loc, rot_deg, w, d):
    """place_on_block hands its factory a CORNER `loc` + rotation, with the box (before rotation)
    spanning local [0,w]x[0,d] from that corner (see buildings.tower/_box_tower_factory) -- convert
    to the reserved footprint's actual centre so a recycled (centre-pivoted) asset lands in the
    same place a synthetic tower's box would have occupied."""
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    return loc[0] + w / 2.0 * ca - d / 2.0 * sa, loc[1] + w / 2.0 * sa + d / 2.0 * ca


def _recycled_tower_factory(coll, name, loc, rot, bx=4, by=4, rng=None, **_ignored):
    """place_on_block-compatible factory: picks a best-fit real tower/high-rise asset for the
    reserved (bx,by)-bay block and places it at the block's true centre, rotated to face `rot` --
    never stretched to fill the reserved footprint (a real tower may occupy less of the block than
    the synthetic preset assumed, which is expected)."""
    rng = rng or random.Random()
    avail_w, avail_d = bx * BAY, by * BAY
    name_, w, d, swap = _pick_building(rng, ("tower", "high"), avail_w, avail_d)
    cx, cy = _corner_to_center(loc, rot, avail_w, avail_d)
    _place_recycled(coll, name_, (cx, cy), rot + (90 if swap else 0))


def build_towers_recycled(coll, tblocks, seed=13):
    """Same reserved-block placement math as build_district.py's tower loop (bd.place_on_block),
    swapping in `_recycled_tower_factory` for `buildings.tower`. TOWER_PRESETS entries are only
    used here for their bx/by (the reserved footprint SIZE) -- not their synthetic facade params."""
    rng = random.Random(seed)
    n = 0
    for kind, cells in tblocks:
        kw = dict(bd.TOWER_PRESETS[kind])
        bx = kw.pop("bx"); by = kw.pop("by")
        bd.place_on_block(coll, f"T_{kind}rb{n}", cells, 'S', _recycled_tower_factory, bx, by,
                           rng=rng)
        n += 1
    return n
