#!/usr/bin/env python3
"""
lod_low.py — a low-object-count PLACEHOLDER tier for a procedurally-built district, built
from the SAME underlying placement decisions as the full-detail pass (the same `TownGrid`
road-cell layout, the same frontage runs, the same building rng sequence) but emitting plain
`kc.box()` extrusions instead of kit-instanced markers — the same "simple box, real footprint"
style a real PLATEAU precinct already has (see `plateau_import.py`), just synthesized instead
of extracted.

Why this exists (two distinct consumers of the same output):
  1. Blender-authoring-time preview speed — `tools/build_debug_preview.py`/`world_master.blend`
     link this tier instead of the full `STREET` collection when composing a fast fly-around
     preview of many districts at once (a procedural district's full detail is thousands of
     `mmesh_`-marker Empty objects at AUTHOR TIME — see kit_common._emit_markers — even though
     WorldBaker folds them into a handful of MultiMeshInstance3D nodes at BAKE time; this tier
     sidesteps the authoring-time object-count cost entirely, not just the runtime one).
  2. A genuine PERSISTENT in-game LOD — baked to its own output scene (`District_<name>_LOD_LOW
     .tscn`) and swapped in at runtime for a distant district by `DistrictLodSwitcher.java`
     (`com.openworld.world`), not just a Blender-side authoring convenience.

Every emitted object gets a `-col` name suffix (BLENDER_CONVENTIONS: static collision, visual
mesh KEPT — unlike `-colonly`) so a placeholder building/road slab is simultaneously the thing
you see AND the thing you stand/drive on, with zero separate collision-proxy authoring.

No lane markers, no waypoints, no sidewalks, no auto-tiled road pieces, no signage/props —
"ensure the roadsystem/major building system", nothing else. AI streaming zones are unaffected
(WorldZoneManager keeps operating on the same district regardless of which visual LOD is shown).
"""
import math
import random
import kit_common as kc
import buildings as bd

CELL = kc.CELL
BAY, R_H = kc.R_BAY, kc.R_H


def _contig_runs(vals):
    """Sorted ints -> contiguous inclusive [(start, end), ...] runs (shared logic with
    buildings._contig, duplicated here to avoid a private cross-module coupling)."""
    out = []
    vals = sorted(vals)
    if not vals:
        return out
    a = p = vals[0]
    for v in vals[1:]:
        if v == p + 1:
            p = v
        else:
            out.append((a, p)); a = p = v
    out.append((a, p))
    return out


def build_roads_lod_low(coll, grid):
    """One flat asphalt `-col` slab per contiguous row-run of road cells (local + arterial —
    `grid.roads` carries both, see road_network.TownGrid.arterial_h/v). Same road-cell footprint
    as the full detail pass, no tile classification / lane composition / markers."""
    by_row = {}
    for (cx, cy) in grid.roads:
        by_row.setdefault(cy, []).append(cx)
    half = CELL / 2.0
    n = 0
    for cy, xs in by_row.items():
        for x0, x1 in _contig_runs(xs):
            wx0, wx1 = x0 * CELL - half, x1 * CELL + half
            wy0, wy1 = cy * CELL - half, cy * CELL + half
            kc.box(f"Road_lod_{cy}_{x0}-col", wx0, wx1, wy0, wy1, 0.0, 0.15, coll, "asphalt")
            n += 1
    return n


def _building_box(coll, name, center, W, D, rot, H):
    bw, bd_ = (W, D) if int(round(rot)) % 180 == 0 else (D, W)
    o = kc.box(name + "-col", -bw / 2, bw / 2, -bd_ / 2, bd_ / 2, 0.0, H, coll, "concrete")
    o.location = (center[0], center[1], 0.0)
    return o


def build_buildings_lod_low(coll, grid, kinds=None, hmin=2, hmax=6, seed=7):
    """Mirrors `buildings.fill_frontage`'s frontage-run walk EXACTLY (same iteration order,
    same rng.choice/randint call sequence, same seed) so every placeholder box lands on the
    identical footprint/height the full-detail building occupies — only the box vs. kit-detail
    choice differs. A fresh `random.Random(seed)` (NOT the caller's already-advanced rng) is
    required to reproduce that sequence independently of when this is called relative to the
    full-detail pass."""
    kinds = kinds or ["block", "block", "apt", "shop"]
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
        while ulen - s >= 5.0:
            w = rng.choice([3, 4, 3]); by = rng.choice([2, 2, 3])
            if w * BAY > ulen - s:
                w = max(2, int((ulen - s) // BAY))
            by = max(1, min(by, int(max_D // BAY)))
            W, D = w * BAY, by * BAY
            off = CELL / 2 - clear - D / 2.0
            cux = ox + u[0] * (s + W / 2) + ax * off
            cuy = oy + u[1] * (s + W / 2) + ay * off
            rot = bd.ROT_FOR_DIR[rdir]
            kind = rng.choice(kinds)          # consumed to keep the rng sequence identical
            floors = rng.randint(hmin, hmax)
            _building_box(coll, f"F{n}lod", (cux, cuy), W, D, rot, floors * R_H)
            n += 1
            s += W
    return n


def _box_tower_factory(coll, name, loc, rot, bx=4, by=4, floors=12, **_ignored):
    """Drop-in replacement for `buildings.tower` as a `place_on_block` factory — same
    bx/by/floors footprint, one visible+collision box instead of a full shaft build."""
    W, D = bx * BAY, by * BAY
    o = kc.box(name + "-col", 0, W, 0, D, 0.0, floors * R_H, coll, "concrete")
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    return o


def build_towers_lod_low(coll, tblocks):
    """Same reserved-block placement math as build_district.py's tower loop
    (`bd.place_on_block`), swapping in `_box_tower_factory` for `bd.tower`. `TOWER_PRESETS`
    entries are fixed dicts (no rng involved), so passing the whole preset through reproduces
    the exact same bx/by/floors footprint as the full-detail tower with no sequencing concerns."""
    n = 0
    for kind, cells in tblocks:
        kw = dict(bd.TOWER_PRESETS[kind])
        bx = kw.pop("bx"); by = kw.pop("by")
        bd.place_on_block(coll, f"T_{kind}lod{n}", cells, 'S', _box_tower_factory, bx, by, **kw)
        n += 1
    return n
