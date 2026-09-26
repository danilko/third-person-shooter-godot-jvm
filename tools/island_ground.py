#!/usr/bin/env python3
"""THE GROUND A CITY BLOCK STANDS ON IS THE BLOCK'S, NOT THE BUILDINGS' (PLAN.md 3.18(c3)).

A lot is a rotated rectangle grown greedily per building (`island_buildings.grow_lots`), and a union of
rectangles is not a partition of a block: two lots in different frames cannot tile, and growth stops at the
first obstruction. So whatever the rectangles fail to claim is LEFTOVER -- raw heightmap 21 cm below the slab
beside it, and painted SAND, because `paint_terrain.gd` picks a texture by elevation alone and the city plain
is 0.6 m.

The industry answer (CityEngine, the Houdini city HDAs, Skylines, GTA's hand-built blocks) is that the BLOCK
owns its ground and a lot is drawn on top of it. Here that needs NO new geometry, because the ground already
exists: Terrain3D. This writes the block's own surface INTO the height field and paints it, so

  * the 21 cm lip is gone by construction -- inside a block there is no step at all, and at the footway there
    is the 6 cm 民地-proud-of-公道 lip 3.18(j) already decided on;
  * the leftover is gone too: there is nothing to fill, because the block's ground IS the surface. A gap
    between two lots reads as the block's ground 6 cm down, which is what a Japanese lot boundary looks like;
  * it costs no mesh, no collider and no draw call.

THE FILL IS GEODESIC, NEVER A BOX. It grows from the LOTS through land that is not road, so it can never
cross a street (roads bound it), never paves countryside a building does not reach, and needs no notion of a
region box:

    a component of (land minus road) that holds a lot and is <= BLOCK_MAX   -> filled whole (a 街区)
    anything else (the countryside, a huge block's core)                    -> filled to REACH_OPEN of a lot

Each fill vertex takes its nearest lot's top (propagated by the same walk), and the fill's outer edge ramps
back to the natural ground over RAMP cells, which is the batter that keeps the open frontage from ending on a
ledge.

    python3 tools/island_ground.py derive <heights.f32> [--area x0,z0,x1,z1] [--out <prefix>]
    python3 tools/island_ground.py report <heights.f32> [--area ...]      # measure only, write nothing

`<heights.f32>` is the CURRENT terrain, dumped by `tools/godot/dump_height_grid.gd -- <out> -2304 -2304 2305
2305 2`. The tool is idempotent BY CONSTRUCTION only against a terrain it has not stamped: run it on a dumped
grid, apply, and a second derive from a fresh dump sees the fill already at target and writes nothing new --
but it CANNOT know what was natural underneath, so keep the pre-stamp dump (`<prefix>.natural.f32`, written
beside the output) as the restore.

Applied with:
    godot --headless --path . --script tools/godot/apply_height_grid.gd -- <data dir> <prefix>.height.f32 \
        -2304 -2304 2305 2305 2
    godot --headless --path . --script tools/godot/apply_paint_grid.gd  -- <data dir> <prefix>.paint.u8 \
        -2304 -2304 2305 2305 2
"""

import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

HALF = 2304.0
STEP = 2.0
N = int(round(2 * HALF / STEP)) + 1        # 2305 vertices a side, matching dump_height_grid.gd

BLOCK_MAX = 40000.0    # m2: a component this size or smaller that holds a lot is a 街区 and is filled whole
REACH_OPEN = 12.0      # ...anything bigger is filled only this far from a lot (no countryside aprons)
UNDER_REACH = 20       # vertices (40 m): how far from paved ground the land under an elevated road is painted too
PAINT_BLEED = 3        # vertices the paint runs past the fill, into the road mask and across a diagonal gap
RAMP_DROP = 0.06       # metres the batter gives back per 2 m vertex outside the fill (a ~4.5% grade)
RAMP_MAX = 5           # ...and the furthest it walks, so a lot on a bank does not batter across a field
LAND_Z = 0.35
BURY_TOL = 0.05        # ground already above the target is left alone (the target would be buried)
MAX_STEP = 1.5         # ...and so is ground further below it than this (it would be a plinth, not a lot)
# A ROAD WITH NO FOOTWAY HAS NOTHING BETWEEN ITS CARRIAGEWAY AND THE BLOCK, so the fill's kerb-level ground can
# stand beside the tarmac -- and Terrain3D interpolates between vertices, so a vertex one cell past the paved edge
# decides the ground under the outer lane. Measured where the walkable coastal ring (footways) meets the cliff road
# `kaigan_dori` (none): ground 0.020 m proud of `ring_kita_F1`. Within CAP_REACH of such a road's paved edge the
# block ground is capped at the road surface less the stamp's own clearance (road_kit_stamp.gd CLEARANCE).
CAP_REACH = 3.0
CLEARANCE = 0.10


def idx(v):
    return int(round((v + HALF) / STEP))


def load_record():
    import island_buildings as ib
    doc = json.load(open(ib.OUT))
    return ib, doc


def military_paint():
    """The military base, its air base strip and its piers are CONCRETE (2026-09-26): they stand at the port's 4.6 m,
    under the 5 m below which `paint_terrain.gd` paints everything sand. Their boxes are the plan's own
    (`island_plan.RESERVES` military_*, `island_reshape.MILITARY_PIERS`), so paint and land cannot disagree."""
    import island_plan as PL
    import island_reshape as ir
    X, Z = vertex_grid()
    m = np.zeros((N, N), dtype=bool)
    for name, (x0, z0, x1, z1) in PL.RESERVES:
        if name.startswith("military"):
            m |= (X >= x0) & (X <= x1) & (Z >= z0) & (Z <= z1)
    for x0, x1, z0, z1 in ir.MILITARY_PIERS:
        m |= (X >= x0) & (X <= x1) & (Z >= z0) & (Z <= z1)
    return m


def dike_paint(key="cells"):
    """The coastal SEAWALL is CONCRETE (user, 2026-09-26: it read as a sand dune): the cells `island_reshape`'s
    `coastal_works` built the wall on, from the runs it records in island_dike.json. Painted with the block's
    concrete (id 4). `key="works"` is the wall + its beach + the road fill in front of the old coast: nothing a
    block may fill."""
    m = np.zeros((N, N), dtype=bool)
    path = os.path.join(ROOT, "assets", "world_source", "island_dike.json")
    cells = json.load(open(path)).get(key) if os.path.exists(path) else None
    if not cells:
        print("island_ground: no dike cells recorded (re-run the land stage)")
        return m
    X, Z = vertex_grid()
    x0, z0, st = float(X[0, 0]), float(Z[0, 0]), cells["step"]
    oi, oj = int(round((cells["x0"] - x0) / st)), int(round((cells["z0"] - z0) / st))
    for j, a, b in cells["runs"]:
        jj = j + oj
        if 0 <= jj < N:
            m[jj, max(0, a + oi):min(N, b + oi + 1)] = True
    return m


def field_soil():
    """The paddy fields' SOIL (user, 2026-09-25), painted as its own terrain texture (id 5) by a second
    `apply_paint_grid.gd` pass: every vertex whose 2 m cell (the cell the vertex is the lower-left corner of) is a
    field cell of `island_buildings.farm_fields`' chunks. The ground's HEIGHT under a field is left alone."""
    ib, doc = load_record()
    soil = np.zeros((N, N), dtype=bool)
    n, cell = ib.FIELD_CELLS, ib.FIELD_CHUNK / ib.FIELD_CELLS
    for f in doc.get("fields", ()):
        word = bin(int(f["mask"], 16))[2:].zfill(len(f["mask"]) * 4)
        for b in range(n * n):
            if word[b] != "1":
                continue
            i, j = idx(f["x0"] + (b % n) * cell), idx(f["z0"] + (b // n) * cell)
            if 0 <= i < N and 0 <= j < N:
                soil[j, i] = True
    return soil


def vertex_grid():
    xs = np.arange(N) * STEP - HALF
    return np.meshgrid(xs, xs)          # X (columns = Godot x), Z (rows = Godot z)


LEVELLED_UNDER = 0.02   # a levelled site's apron stands this far over the ground filled under it (z-fighting)


def levelled_sites(text):
    """[(godot x, z, yaw rad, half x, half z, godot y)] of every site zone carrying `metadata/site_level`."""
    import re
    out = []
    for m in re.finditer(r'\[sub_resource type="Resource" id="Zone_site_[^"]*"\]\n(.*?)\n\n', text, re.S):
        body = m.group(1)
        lv = re.search(r"metadata/site_level = ([-0-9.]+)", body)
        res = re.search(r"metadata/site_reserve = PackedFloat64Array\(([^)]*)\)", body)
        if lv and res:
            v = [float(x) for x in res.group(1).split(",")]
            out.append((v[0], v[1], v[2], v[3], v[4], float(lv.group(1))))
    return out


def rect_into(target, cx, cz, yaw_deg, x0, z0, x1, z1, value=True, heights=None, h=None):
    """Mark the rotated local rect [x0,x1]x[z0,z1] of a frame at (cx, cz) turned by yaw."""
    a = math.radians(yaw_deg)
    s, c = math.sin(a), math.cos(a)
    corners = [(x0, z0), (x1, z0), (x0, z1), (x1, z1)]
    wx = [cx + lx * c + lz * s for lx, lz in corners]
    wz = [cz - lx * s + lz * c for lx, lz in corners]
    i0, i1 = max(idx(min(wx)) - 1, 0), min(idx(max(wx)) + 1, N - 1)
    j0, j1 = max(idx(min(wz)) - 1, 0), min(idx(max(wz)) + 1, N - 1)
    if i1 < i0 or j1 < j0:
        return
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
    X = ii * STEP - HALF - cx
    Z = jj * STEP - HALF - cz
    lx = X * c - Z * s
    lz = X * s + Z * c
    m = (lx >= x0) & (lx <= x1) & (lz >= z0) & (lz <= z1)
    target[jj[m], ii[m]] = value
    if heights is not None:
        heights[jj[m], ii[m]] = h


def capsule_into(target, a, b, r):
    x0, x1 = min(a[0], b[0]) - r, max(a[0], b[0]) + r
    z0, z1 = min(a[1], b[1]) - r, max(a[1], b[1]) + r
    i0, i1 = max(idx(x0) - 1, 0), min(idx(x1) + 1, N - 1)
    j0, j1 = max(idx(z0) - 1, 0), min(idx(z1) + 1, N - 1)
    if i1 < i0 or j1 < j0:
        return
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
    X = ii * STEP - HALF
    Z = jj * STEP - HALF
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 < 1e-9 else np.clip(((X - a[0]) * dx + (Z - a[1]) * dz) / L2, 0.0, 1.0)
    d2 = (X - a[0] - t * dx) ** 2 + (Z - a[1] - t * dz) ** 2
    target[j0:j1 + 1, i0:i1 + 1] |= d2 <= r * r


def capsule_cap(cap, a, b, r, za, zb):
    """cap = min(cap, the segment's surface interpolated along it) within r of the segment a-b (Godot XZ)."""
    x0, x1 = min(a[0], b[0]) - r, max(a[0], b[0]) + r
    z0, z1 = min(a[1], b[1]) - r, max(a[1], b[1]) + r
    i0, i1 = max(idx(x0) - 1, 0), min(idx(x1) + 1, N - 1)
    j0, j1 = max(idx(z0) - 1, 0), min(idx(z1) + 1, N - 1)
    if i1 < i0 or j1 < j0:
        return
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
    X = ii * STEP - HALF
    Z = jj * STEP - HALF
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz
    t = np.zeros(X.shape) if L2 < 1e-9 else np.clip(((X - a[0]) * dx + (Z - a[1]) * dz) / L2, 0.0, 1.0)
    d2 = (X - a[0] - t * dx) ** 2 + (Z - a[1] - t * dz) ** 2
    zs = za + (zb - za) * t
    sub = cap[j0:j1 + 1, i0:i1 + 1]
    m = d2 <= r * r
    sub[m] = np.fmin(sub[m], zs[m])


def network_y(text):
    import re
    m = re.search(r'\[node name="IslandRoads"[^\]]*\]\s*\ntransform = Transform3D\(([^)]*)\)', text)
    return float(m.group(1).split(",")[10]) if m else 0.0


def road_mask(ib, grid_fn, text):
    """The carriageway + footway, exactly the mask `island_buildings.derive` calls `field.road`, at 2 m -- and the
    cap beside every at-grade road with no footway (see CAP_REACH)."""
    net, grid, cors = ib.solve_bands()
    ny = network_y(text)
    road = np.zeros((N, N), bool)
    under = np.zeros((N, N), bool)      # land under an ELEVATED road (a deck's footprint): painted, never raised
    cap = np.full((N, N), np.nan)
    for line, _h, owner in cors:
        owner = str(owner)
        pts = [(x, -y, z, half) for (x, y, z, half) in line]
        walk, _lanes = ib.road_walk(net, owner)
        hard = (walk if walk else ib.PAD_WALK) if owner.startswith("JCT:") else walk
        if hard <= 0.0 and not owner.startswith("JCT:"):
            hard = 0.0
        high = any(ib.elevated(z, grid(x, -gz)) for x, gz, z, _ in pts)
        if high or owner.startswith(("GORE:", "shuto_")):
            # an elevated deck is not ground: keep the whole footprint out of the fill
            hard = max(hard, ib.ELEVATED_GAP)
        for a, b in zip(pts, pts[1:]):
            capsule_into(road, a[:2], b[:2], max(a[3], b[3]) + hard)
            if high or owner.startswith("shuto_"):
                capsule_into(under, a[:2], b[:2], max(a[3], b[3]) + hard)
            if hard <= 0.0 and not high and not owner.startswith("JCT:"):
                capsule_cap(cap, a[:2], b[:2], max(a[3], b[3]) + CAP_REACH,
                            a[2] + ny - CLEARANCE, b[2] + ny - CLEARANCE)
        if len(pts) == 1:
            capsule_into(road, pts[0][:2], pts[0][:2], pts[0][3] + hard)
    # A SITE IS NOT A ROAD AND IT IS NOT A BLOCK EITHER. Its own scene carries whatever ground it has (a
    # terminal's apron, a station's platform), so nothing here may RAISE the terrain under it -- but leaving
    # it the colour of a beach is the defect this tool exists for, and Tokyo Station's forecourt is the
    # clearest case in the world. It is kept out of the fill and put into the paint.
    site = np.zeros((N, N), bool)
    for (cx, cz, yaw, hx, hz) in ib.site_exclusions(text):
        # site_exclusions' yaw is RADIANS (island_buildings.block_box's convention) and rect_into takes DEGREES: passed
        # straight through, every site mask was laid near axis-aligned (a yaw-90 terminal across its quay, not along it)
        rect_into(site, cx, cz, math.degrees(yaw), -hx, -hz, hx, hz)
    return road, site, cap, under


DIRS8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def shift_bool(a, dj, di):
    """`a` moved by (dj, di): out[j, i] = a[j - dj, i - di], False off the edge. A diagonal step is allowed --
    a corner wedge between a junction pad and a lot touches the lot only diagonally, and a 4-connected walk
    leaves exactly those wedges bare (measured: the tan triangles at every crossing)."""
    out = np.zeros_like(a)
    js = slice(dj, None) if dj > 0 else (slice(None, dj) if dj < 0 else slice(None))
    jd = slice(None, -dj) if dj > 0 else (slice(-dj, None) if dj < 0 else slice(None))
    iss = slice(di, None) if di > 0 else (slice(None, di) if di < 0 else slice(None))
    idd = slice(None, -di) if di > 0 else (slice(-di, None) if di < 0 else slice(None))
    out[js, iss] = a[jd, idd]
    return out


def shift_f(a, dj, di):
    out = np.full(a.shape, np.nan)
    js = slice(dj, None) if dj > 0 else (slice(None, dj) if dj < 0 else slice(None))
    jd = slice(None, -dj) if dj > 0 else (slice(-dj, None) if dj < 0 else slice(None))
    iss = slice(di, None) if di > 0 else (slice(None, di) if di < 0 else slice(None))
    idd = slice(None, -di) if di > 0 else (slice(-di, None) if di < 0 else slice(None))
    out[js, iss] = a[jd, idd]
    return out


def build(heights_path, area=None):
    ib, doc = load_record()
    text = open(ib.SCENE).read()
    nat = np.fromfile(heights_path, dtype="<f4").reshape(N, N).astype(np.float64)
    land = nat > LAND_Z

    lot = np.zeros((N, N), bool)
    lot_top = np.full((N, N), np.nan)
    for b in doc["buildings"]:
        top = b["pos"][1] + ib.LOT_RAISE
        rect_into(lot, b["pos"][0], b["pos"][2], b["yaw"], *b["lot"], heights=lot_top, h=top)
    for p in doc.get("passages", ()):
        w, dd = p["size"]
        # the 路地 stands with the lots it runs between, not with the carriageway (PLAN.md 3.18(c3)), so its
        # ground is theirs. There is no alley slab (3.18(c3a)): THIS raster is the only thing paving a 路地, so
        # do not drop passages from it
        rect_into(lot, p["pos"][0], p["pos"][2], p["yaw"], -w / 2.0, -dd / 2.0, w / 2.0, dd / 2.0,
                  heights=lot_top, h=p["pos"][1] + ib.LOT_RAISE)
    road, site, cap, under = road_mask(ib, None, text)
    # a LEVELLED site (an access car park, island_sites.access_parking) is ground this stage owns: the terrain under it
    # is filled up to its level exactly like a lot, and it is no longer a site the fill must keep out of
    levelled = np.zeros((N, N), bool)
    for (cx, cz, yaw, hx, hz, level) in levelled_sites(text):
        rect_into(levelled, cx, cz, math.degrees(yaw), -hx, -hz, hx, hz, heights=lot_top,
                  h=level - LEVELLED_UNDER + ib.LOT_FILL_GAP)
    site &= ~levelled
    lot |= levelled
    lot &= ~road & ~site
    print("island_ground: %d lot vertices, %d road vertices" % (int(lot.sum()), int(road.sum())))

    # the dike embankment, the beach and the fill in front of the old coast are not a block's
    open_ground = land & ~road & ~site & ~dike_paint("works") & ~dike_paint("cells")
    comp, sizes = components(open_ground)
    # which components hold a lot, and how big they are
    holds = np.zeros(len(sizes) + 1, bool)
    holds[comp[lot]] = True
    holds[0] = False
    block = np.zeros(len(sizes) + 1, bool)
    for cid in range(1, len(sizes) + 1):
        block[cid] = holds[cid] and sizes[cid] * STEP * STEP <= BLOCK_MAX
    whole = block[comp] & open_ground          # a 街区: filled whole
    print("island_ground: %d components, %d hold a lot, %d are 街区 (<= %.0f m2)"
          % (len(sizes), int(holds.sum()), int(block.sum()), BLOCK_MAX))

    # geodesic walk out of the lots through open ground, carrying the nearest lot's own level (footway +
    # LOT_RAISE, less LOT_FILL_GAP, which is 0 now): there is no lot slab any more (user, 2026-09-25) -- the fill IS
    # the private ground, from the lot's own frontage to the next street, and a building stands on its plinth on it.
    reach_cells = int(math.ceil(REACH_OPEN / STEP))
    target = np.where(lot, lot_top - ib.LOT_FILL_GAP, np.nan)
    frontier = lot.copy()
    filled = lot.copy()
    steps = 0
    while frontier.any():
        nxt = np.zeros((N, N), bool)
        nt = np.full((N, N), np.nan)
        for dj, di in DIRS8:
            src = shift_bool(frontier, dj, di)
            sv = shift_f(target, dj, di)
            take = src & ~filled & open_ground & np.isnan(nt)
            # past REACH_OPEN only a 街区 keeps growing
            if steps >= reach_cells:
                take &= whole
            nxt |= take
            nt[take] = sv[take]
        if not nxt.any():
            break
        target[nxt] = nt[nxt]
        filled |= nxt
        frontier = nxt
        steps += 1
        if steps > 200:
            break
    fill = filled & ~lot
    # The target must be honest about the ground: never bury it, never stand on a plinth. This is asked of
    # the LOTS AND THE 路地 as well as of the fill -- a lot's own placement already refused ground outside
    # this band, but a passage's did not, and one reserved across falling ground asked for a 2.49 m mound.
    have = (lot | fill) & ~np.isnan(target)
    bad = have & ((nat > target + BURY_TOL) | (target - nat > MAX_STEP))
    fill &= ~bad & ~np.isnan(target)
    lot = lot & ~bad
    print("island_ground: fill %.3f km2 (%d vertices), %d refused for ground (buried or a plinth)"
          % (fill.sum() * STEP * STEP * 1e-6, int(fill.sum()), int(bad.sum())))

    paved = fill | (lot & ~np.isnan(lot_top))
    height = np.where(paved, target, np.nan)
    # the batter: ramp back to the natural ground outside the paved edge, so an open frontage does not end
    # on a 21 cm ledge
    edge = paved.copy()
    ramp_from = np.where(paved, target, np.nan)
    land_only = nat > LAND_Z
    for _k in range(RAMP_MAX):
        grown = np.zeros((N, N), bool)
        gv = np.full((N, N), np.nan)
        for dj, di in DIRS8:
            src = shift_bool(edge, dj, di)
            sv = shift_f(ramp_from, dj, di)
            take = src & ~paved & ~road & ~site & land_only & np.isnan(gv) & np.isnan(height)
            grown |= take
            gv[take] = sv[take]
        # A RAMP IS A SLOPE, NOT A FIXED NUMBER OF CELLS. The drop to the natural ground is 0.21 m under a
        # flat city block and 0.82 m where a lot stands over falling ground, so a fixed 3-cell blend leaves a
        # 20 cm ledge on exactly the lots that most need the batter. Each cell gives back RAMP_DROP and the
        # walk stops where it has met the ground.
        gv = np.maximum(gv - RAMP_DROP, nat)
        # A BATTER GIVES BACK A STEP, NOT A BANK. Where the ground behind a lot falls further than the whole
        # ramp can return (measured: 2.49 m on one passage reserved across falling ground), a batter would be
        # a mound of fill standing in a field. Leave the drop -- that edge wants a 塀 or a 擁壁, which is art.
        grown &= ~np.isnan(gv) & (gv > nat + 0.001) & ((gv - nat) <= RAMP_MAX * RAMP_DROP + 0.001)
        if not grown.any():
            break
        height[grown] = gv[grown]
        edge = grown
        ramp_from = gv
    # beside a road with no footway, never above its surface less the stamp's clearance (CAP_REACH)
    capped = ~np.isnan(height) & ~np.isnan(cap) & (height > cap)
    height = np.where(capped, cap, height)
    print("island_ground: %d vertices capped beside a road with no footway" % int(capped.sum()))
    # never lower the ground: this is a fill, and lowering would cut under a road or into the sea -- EXCEPT on a
    # lot, which is the building's own ground and may stand up to BURY_TOL under the natural ground (a lot is
    # refused past that). The slab used to cover that; with no slab, ground left standing there would poke
    # through the shop floor.
    height = np.where(np.isnan(height), np.nan, np.where(lot, height, np.maximum(height, nat)))
    if area is not None:
        x0, z0, x1, z1 = area
        keep = np.zeros((N, N), bool)
        X, Z = vertex_grid()
        keep[(X >= x0) & (X <= x1) & (Z >= z0) & (Z <= z1)] = True
        height = np.where(keep, height, np.nan)
        fill &= keep
        paved &= keep
        print("island_ground: restricted to x %.0f..%.0f z %.0f..%.0f" % (x0, x1, z0, z1))
    moved = (~np.isnan(height)) & (np.abs(height - nat) > 0.001)
    print("island_ground: %d vertices move, biggest %+.3f m, median %+.3f m"
          % (int(moved.sum()), float(np.nanmax(height[moved] - nat[moved])) if moved.any() else 0.0,
             float(np.median(height[moved] - nat[moved])) if moved.any() else 0.0))
    return nat, height, paved, fill, lot, lot_top, road, site, under


def components(mask):
    """4-connected labels of `mask` as int32, plus an array of sizes indexed by label (0 unused)."""
    lab = np.zeros(mask.shape, np.int32)
    sizes = [0]
    cur = 0
    from collections import deque
    js, iss = np.nonzero(mask)
    for j0, i0 in zip(js, iss):
        if lab[j0, i0]:
            continue
        cur += 1
        lab[j0, i0] = cur
        q = deque([(j0, i0)])
        n = 0
        while q:
            j, i = q.popleft()
            n += 1
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                y, x = j + dj, i + di
                if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x] and not lab[y, x]:
                    lab[y, x] = cur
                    q.append((y, x))
        sizes.append(n)
    return lab, sizes


def walk_surface(nat, height, lot, lot_top):
    """What a player's feet are on at each vertex: the lot SLAB where there is one, else the ground (stamped
    where this tool stamped it, natural elsewhere). This is the surface the lip is measured on."""
    ground = np.where(np.isnan(height), nat, height)
    return np.where(lot & ~np.isnan(lot_top), lot_top, ground)


def measure(nat, height, lot, lot_top, road=None, where=None):
    """Metres of edge where two neighbouring vertices' walkable surfaces differ by more than 10 cm.

    An edge with a ROAD vertex on either side is skipped: the road mask is the carriageway plus its footway
    and the road piece's own paving is a MESH standing on it, so a step in the terrain there is under the
    pavement and cannot be seen -- on the industry trial that was 9.1 of 15.0 km, the same before and after."""
    s = walk_surface(nat, height, lot, lot_top)
    lip = 0
    for dj, di in ((1, 0), (0, 1)):
        a, b = (s[:-1, :], s[1:, :]) if dj else (s[:, :-1], s[:, 1:])
        step = np.abs(a - b) > 0.10
        if road is not None:
            ra, rb = (road[:-1, :], road[1:, :]) if dj else (road[:, :-1], road[:, 1:])
            step &= ~(ra | rb)
        if where is not None:
            wa, wb = (where[:-1, :], where[1:, :]) if dj else (where[:, :-1], where[:, 1:])
            step &= wa | wb
        lip += int(step.sum())
    return lip * STEP


def main(argv):
    if not argv or argv[0] not in ("derive", "report"):
        print(__doc__)
        return 2
    heights = argv[1]
    area = None
    prefix = os.path.join(ROOT, "assets/world_source/buildings/IslandGround")
    rest = argv[2:]
    while rest:
        if rest[0] == "--area":
            area = [float(v) for v in rest[1].split(",")]
            rest = rest[2:]
        elif rest[0] == "--out":
            prefix = rest[1]
            rest = rest[2:]
        else:
            print("unknown argument %s" % rest[0])
            return 2
    nat, height, paved, fill, lot, lot_top, road, site, under = build(heights, area)
    # Measure only the PAVING'S OWN edges. Over the whole island the natural relief carries thousands of km
    # of 10 cm steps -- mountains, cliffs, the shore -- and counting those buries the number this is about.
    where = paved.copy()
    for dj, di in DIRS8:
        where |= shift_bool(paved, dj, di)
    if area is not None:
        X, Z = vertex_grid()
        where &= (X >= area[0]) & (X <= area[2]) & (Z >= area[1]) & (Z <= area[3])
    flat = np.full((N, N), np.nan)
    before = measure(nat, flat, lot, lot_top, road, where)
    after = measure(nat, height, lot, lot_top, road, where)
    print("island_ground: edges with a step over 10 cm: %.1f km BEFORE -> %.1f km AFTER (%.0f%% gone)"
          % (before / 1000.0, after / 1000.0, 100.0 * (before - after) / max(before, 1.0)))
    if argv[0] == "report":
        return 0
    height.astype("<f4").tofile(prefix + ".height.f32")
    # THE PAINT BLEEDS PAST THE FILL, the height does not. A junction pad's road MASK is an over-estimate of
    # its paving (`PAD_WALK` where a mouth declares no footway), so a ring of ground shows between the pad's
    # own edge and where a lot may stand; and paint under a road mesh costs nothing and is never seen. Raising
    # that ring would be wrong -- it is the pad's business -- but leaving it the colour of a beach is what the
    # report is about.
    paint = paved.copy()
    for _ in range(PAINT_BLEED):
        g = paint.copy()
        for dj, di in DIRS8:
            g |= shift_bool(paint, dj, di)
        paint = g & (nat > LAND_Z)
    paint |= site & (nat > LAND_Z)
    # UNDER AN ELEVATED ROAD the land is the city's, not a beach (user, 2026-09-22: the strip under the expressway
    # stayed sand-coloured between two paved blocks). Its footprint is kept out of the FILL on purpose -- a deck is
    # not ground, so nothing raises it -- but where it adjoins paved ground (within UNDER_REACH vertices) it takes
    # the same paint, so the block's concrete runs on under the viaduct. Open country under a viaduct (the bay
    # approaches) stays as it is.
    near = paved.copy()
    for _ in range(UNDER_REACH):
        g = near.copy()
        for dj, di in DIRS8:
            g |= shift_bool(near, dj, di)
        near = g
    paint |= under & near & (nat > LAND_Z)
    paint |= military_paint() & (nat > LAND_Z)
    paint |= dike_paint()
    if area is not None:
        X, Z = vertex_grid()
        paint &= (X >= area[0]) & (X <= area[2]) & (Z >= area[1]) & (Z <= area[3])
    print("island_ground: paint %.3f km2 (%d vertices)" % (paint.sum() * STEP * STEP * 1e-6, int(paint.sum())))
    (paint.astype(np.uint8)).tofile(prefix + ".paint.u8")
    soil = field_soil()
    print("island_ground: soil %.3f km2 (%d vertices) under the paddy fields" % (
        soil.sum() * STEP * STEP * 1e-6, int(soil.sum())))
    (soil.astype(np.uint8)).tofile(prefix + ".soil.u8")
    nat.astype("<f4").tofile(prefix + ".natural.f32")
    print("island_ground: wrote %s.{height.f32,paint.u8,soil.u8,natural.f32}" % os.path.relpath(prefix, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
