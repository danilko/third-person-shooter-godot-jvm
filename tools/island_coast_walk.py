#!/usr/bin/env python3
"""island_coast_walk.py -- CAN A SWIMMER WALK OUT OF THE SEA AND BACK INTO TOWN? (S15, user 2026-10-14)

    python3 tools/island_coast_walk.py [--grid <f32>] [--picture <png>] [--max <n>]

User (verbatim): "some of land outside of dike (beside harbor area, once in beach, cannot climb more out, and result need
to go all due to steep clif like surbub, but should be slope beach out side of dike)". A beach you can wade onto but not
walk up from is a TRAP: the only way off it is back into the water.

On the land grid (default the built `island_natural.f32`: land, touge sculpt and dike), every land cell (Godot Y >
LAND_Y) is a node and two 4-neighbours are joined when the step between them is walkable: |dz| <= CELL * tan(WALK_DEG).
The walk floods from the city plain and the airport island (SEEDS). An EXIT is a land cell next to water whose ground is at most EXIT_Y above
the sea -- where a swimmer stands up. Every exit the flood does not reach is a trap; they are grouped into pockets
(cells within POCKET_M of each other) and listed with their size and centre, largest first.

What the grid does not hold is not counted: stairs, ladders, a quay's steps (a port's vertical quay has no exit, so it is
never a trap), the road stamp (a road on an embankment can make a pocket that the grid shows open). `--max` fails the run
when more than that many pockets remain (the gate); without it the run only reports.
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island_reshape as RS          # noqa: E402

LAND_Y = 0.35
WALK_DEG = 40.0          # a CharacterBody3D's floor_max_angle is 45 deg (Godot's default, MovementController reads it):
                         # 40 leaves the margin a 2 m cell's averaging hides
EXIT_Y = 1.0             # a swimmer stands up on ground at most this far above the water (y 0)
SEEDS = ((0.0, 0.0),      # Godot (x, z): the city plain
         (1100.0, 1750.0))  # ...and the airport island, which the bridge joins (the walk cannot cross water)
POCKET_M = 30.0
NATURAL = os.path.join(RS.TERRAIN_DIR, "island_natural.f32")


ROAD_GROUND_M = 4.0      # a road within this of the ground under it stands on it (cut / fill, the stamp's embankment);
                         # higher is a deck the ground walk cannot use
NET_Y = 5.6              # island_roadgen.NET_Y: a record height is the Godot height less this


def road_cells(h, record):
    """The ROADS as walkable ground: every road of the record within ROAD_GROUND_M of the grid under it, rasterised
    over its paved half width at its own height -- the stamp lays it there in the game, and a road is how a player walks
    inland. Returns (mask, height) grids."""
    sys.path.insert(0, os.path.join(RS.ROOT, "blender", "addons", "road_kit_authoring"))
    import point_model as pm
    net = pm.load_network(record)
    mask = np.zeros(h.shape, bool)
    hz = np.full(h.shape, -np.inf)
    for name, r in net.roads.items():
        b = r.base
        for u, v in zip(r.points, r.points[1:]):
            p, q = net.points[u], net.points[v]
            if not p.has_link(v):
                continue
            n = (p.lanes_fwd or 0) + (p.lanes_bwd or 0)
            half = 0.5 * (n * (b.lane_width or 3.25) + (b.median_width or 0.0)) + max(
                b.left_walk_width or 0.0, b.right_walk_width or 0.0) + max(
                b.shoulder_left_width or 0.0, b.shoulder_right_width or 0.0)
            L = math.dist(p.pos[:2], q.pos[:2])
            for k in range(int(L) + 1):
                t = k / max(L, 1e-9)
                x = p.pos[0] + (q.pos[0] - p.pos[0]) * t
                gz = -(p.pos[1] + (q.pos[1] - p.pos[1]) * t)            # Godot z
                y = p.pos[2] + (q.pos[2] - p.pos[2]) * t + NET_Y
                i0 = int((x - half - RS.X0) / RS.STEP)
                j0 = int((gz - half - RS.Z0) / RS.STEP)
                k_ = int(2 * half / RS.STEP) + 2
                sub = (slice(max(0, j0), max(0, j0) + k_), slice(max(0, i0), max(0, i0) + k_))
                ground = h[sub]
                if ground.size == 0 or abs(float(np.median(ground)) - y) > ROAD_GROUND_M:
                    continue
                mask[sub] = True
                hz[sub] = np.maximum(hz[sub], y)
    return mask, hz


def flood(h):
    land = h > LAND_Y
    step = RS.STEP * math.tan(math.radians(WALK_DEG))
    # the four walkable edges, each as a mask on the cell it starts from
    ex = land[:, :-1] & land[:, 1:] & (np.abs(h[:, 1:] - h[:, :-1]) <= step)      # (j, i) <-> (j, i+1)
    ez = land[:-1, :] & land[1:, :] & (np.abs(h[1:, :] - h[:-1, :]) <= step)      # (j, i) <-> (j+1, i)
    r = np.zeros_like(land)
    for sx, sz in SEEDS:
        j0, i0 = int(round((sz - RS.Z0) / RS.STEP)), int(round((sx - RS.X0) / RS.STEP))
        if not land[j0, i0]:
            raise SystemExit("island_coast_walk: the seed (%s, %s) is not land" % (sx, sz))
        r[j0, i0] = True
    # grow until nothing changes: each round sweeps the four directions repeatedly (a run along a row or a column
    # floods in one sweep, so a winding path costs rounds per turn, not per cell)
    while True:
        before = int(r.sum())
        for _ in range(8):
            # +x then -x along rows, +z then -z along columns (np.maximum.accumulate over an edge-gated run)
            r[:, 1:] |= _sweep(r[:, :-1], ex)
            r[:, :-1] |= _sweep(r[:, 1:][:, ::-1], ex[:, ::-1])[:, ::-1]
            r[1:, :] |= _sweep(r[:-1, :].T, ez.T).T
            r[:-1, :] |= _sweep(r[1:, :][::-1].T, ez[::-1].T).T[::-1]
        if int(r.sum()) == before:
            return land, r


def _sweep(src, edge):
    """For each row: a cell is reached from its predecessor when the predecessor is reached (src) and the edge between
    them is walkable, carried along unbroken runs of walkable edges (a cumulative OR reset at every broken edge)."""
    # label each run of consecutive True edges; within a run the reach propagates forward from the first reached cell
    seg = np.cumsum(~edge, axis=1)                     # a new segment id after each broken edge
    hit = src & edge                                   # reached cell whose forward edge is walkable
    # a cell k+1 is reached if some cell m <= k in the same segment has hit[m]: the running max of (hit * position)
    # compared with the segment's start
    pos = np.arange(edge.shape[1])[None, :]
    last = np.maximum.accumulate(np.where(hit, pos, -1), axis=1)
    start = np.zeros_like(pos) + pos
    # the segment's first position: the position right after the last broken edge
    brk = np.where(~edge, pos, -1)
    seg_start = np.maximum.accumulate(brk, axis=1) + 1
    del seg, start
    return (last >= seg_start) & edge


def exits(h, land):
    water = ~land
    near = np.zeros_like(land)
    near[1:, :] |= water[:-1, :]
    near[:-1, :] |= water[1:, :]
    near[:, 1:] |= water[:, :-1]
    near[:, :-1] |= water[:, 1:]
    return land & near & (h <= EXIT_Y)


def pockets(cells):
    """Trap cells grouped into pockets: [(count, (x, z) centre, (x0, z0, x1, z1))], largest first."""
    js, is_ = np.nonzero(cells)
    pts = list(zip((RS.X0 + is_ * RS.STEP).tolist(), (RS.Z0 + js * RS.STEP).tolist()))
    k = POCKET_M
    grid = {}
    for n, (x, z) in enumerate(pts):
        grid.setdefault((int(x // k), int(z // k)), []).append(n)
    seen, out = set(), []
    for n in range(len(pts)):
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            m = stack.pop()
            comp.append(m)
            x, z = pts[m]
            ci, cj = int(x // k), int(z // k)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for q in grid.get((ci + di, cj + dj), ()):
                        if q not in seen and math.hypot(pts[q][0] - x, pts[q][1] - z) <= k:
                            seen.add(q)
                            stack.append(q)
        xs = [pts[m][0] for m in comp]
        zs = [pts[m][1] for m in comp]
        out.append((len(comp), (sum(xs) / len(xs), sum(zs) / len(zs)), (min(xs), min(zs), max(xs), max(zs))))
    return sorted(out, key=lambda p: -p[0])


def zone_of(x, z, zones):
    """The coast design zone (island_coast.json, Godot x0, x1, z0, z1) a point is in, the working ones first."""
    for kind in ("fishing_port", "industrial_harbour", "military_harbour", "gulf", "airport_island", "seawall", "cliff",
                 "beach"):
        for x0, x1, z0, z1 in zones.get(kind, ()):
            if x0 <= x <= x1 and z0 <= z <= z1:
                return kind
    return "-"


def walls(h, land):
    """Shore with NO exit: land next to water standing over EXIT_Y (a quay, a fill's vertical face, a cliff)."""
    water = ~land
    near = np.zeros_like(land)
    near[1:, :] |= water[:-1, :]
    near[:-1, :] |= water[1:, :]
    near[:, 1:] |= water[:, :-1]
    near[:, :-1] |= water[:, 1:]
    return land & near & (h > EXIT_Y)


def postal(x, z):
    return "%d-%d" % (int((x + 2304.0) // 192.0) + 1, int((z + 2304.0) // 192.0) + 1)


def picture(h, land, reached, traps, path, wl=None):
    from PIL import Image
    s = 4                                                   # every 4th cell: 8 m per pixel
    img = np.zeros((h.shape[0] // s + 1, h.shape[1] // s + 1, 3), np.uint8)
    hv, lv, rv, tv = h[::s, ::s], land[::s, ::s], reached[::s, ::s], traps[::s, ::s]
    img[...] = (40, 70, 120)
    img[lv] = (170, 60, 60)                                 # land the walk does not reach: red
    img[lv & rv] = np.clip(np.stack([90 + hv * 2, 140 + hv * 1.5, 90 + hv], -1), 0, 255)[lv & rv]
    big = np.zeros_like(tv)
    for dj in range(-2, 3):
        for di in range(-2, 3):
            big |= np.roll(np.roll(tv, dj, 0), di, 1)
    if wl is not None:
        w2 = np.zeros_like(tv)
        wv = wl[::s, ::s]
        for dj in range(-1, 2):
            for di in range(-1, 2):
                w2 |= np.roll(np.roll(wv, dj, 0), di, 1)
        img[w2] = (255, 120, 0)                             # shore with no exit: orange
    img[big] = (255, 230, 0)                                # trapped exits: yellow
    Image.fromarray(img).save(path)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--grid", default=NATURAL)
    ap.add_argument("--picture", default="")
    ap.add_argument("--max", type=int, default=None, help="fail when more than this many trap pockets remain")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--record", default=os.path.join(RS.ROOT, "assets", "world_source", "pieces",
                                                     "IslandRoads.roads.json"),
                    help="roads to walk on (the stamp lays them; '' for the bare grid)")
    ap.add_argument("--walls", type=float, default=0.0, help="also list shore with no exit, runs at least this long (m)")
    a = ap.parse_args(argv)
    h = RS.load(a.grid).astype(np.float64)
    if a.record:
        mask, hz = road_cells(h, a.record)
        h = np.where(mask & (hz > LAND_Y), hz, h)
        print("island_coast_walk: %d road cell(s) laid at their own height from %s" % (int(mask.sum()),
                                                                                   os.path.basename(a.record)))
    land, reached = flood(h)
    ex = exits(h, land)
    traps = ex & ~reached
    ps = pockets(traps)
    import json
    zones = json.load(open(os.path.join(RS.ROOT, "assets", "world_source", "island_coast.json")))["zones"]
    # a cove at the foot of the massif's natural cliff coast (zone "cliff", 45 deg) cannot take a bank: it is reported
    # as a stair site for the hand pass, not counted by the gate
    coves = [p for p in ps if zone_of(p[1][0], p[1][1], zones) == "cliff"]
    ps = [p for p in ps if zone_of(p[1][0], p[1][1], zones) != "cliff"]
    area = RS.STEP * RS.STEP
    print("island_coast_walk: %s: land %.2f km2, walk-reached %.2f km2 (%.1f %%); exits %d, TRAPPED %d in %d pocket(s)"
          " + %d cliff cove(s)" % (os.path.basename(a.grid), land.sum() * area / 1e6, (land & reached).sum() * area / 1e6,
                                  100.0 * (land & reached).sum() / max(1, land.sum()), int(ex.sum()), int(traps.sum()),
                                  len(ps), len(coves)))
    for n, (cx, cz), (x0, z0, x1, z1) in coves:
        print("  cliff cove (stair site, not gated) %4.0f m of shore at Godot (%6.0f, %6.0f) postal %s"
              % (n * RS.STEP, cx, cz, postal(cx, cz)))
    for n, (cx, cz), (x0, z0, x1, z1) in ps[:a.top]:
        print("  pocket %5d exit cells (%5.0f m of shore)  centre Godot (%6.0f, %6.0f) postal %-6s box x %.0f..%.0f z %.0f..%.0f"
              % (n, n * RS.STEP, cx, cz, postal(cx, cz), x0, x1, z0, z1))
    if a.walls:
        import json
        zones = json.load(open(os.path.join(RS.ROOT, "assets", "world_source", "island_coast.json")))["zones"]
        wl = walls(h, land)
        wp = [p for p in pockets(wl) if p[0] * RS.STEP >= a.walls]
        by = {}
        for n, (cx, cz), b in wp:
            by.setdefault(zone_of(cx, cz, zones), []).append((n, (cx, cz), b))
        print("island_coast_walk: shore with NO exit (over %.1f m), runs >= %.0f m, by coast zone:" % (EXIT_Y, a.walls))
        for kind, rows in sorted(by.items(), key=lambda kv: -sum(r[0] for r in kv[1])):
            print("  %-18s %6.0f m in %d run(s)" % (kind, sum(r[0] for r in rows) * RS.STEP, len(rows)))
            for n, (cx, cz), (x0, z0, x1, z1) in rows[:8]:
                print("      %5.0f m  centre (%6.0f, %6.0f) postal %-6s box x %.0f..%.0f z %.0f..%.0f"
                      % (n * RS.STEP, cx, cz, postal(cx, cz), x0, x1, z0, z1))
    if a.picture:
        picture(h, land, reached, traps, a.picture, walls(h, land) if a.walls else None)
        print("island_coast_walk: picture %s (red = land the walk cannot reach, yellow = trapped exits)" % a.picture)
    if a.max is not None and len(ps) > a.max:
        print("island_coast_walk: FAIL %d trap pocket(s) > %d" % (len(ps), a.max))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
