#!/usr/bin/env python3
"""island_coast.py -- the island's COAST, zoned, and the shallow shelf off its beaches (PLAN.md 3.8 steps 1-2).

    python3 tools/island_coast.py zones                       # (re)write assets/world_source/island_coast.json
    python3 tools/island_coast.py shelf <in.f32> <out.f32>    # the beach shelf, on a dump_height_grid.gd grid
    python3 tools/island_coast.py check <grid.f32> [<orig>]   # exit 1 unless every beach has its shelf, and (with
                                                              # the original) no quay/cliff/harbour/land cell moved
    python3 tools/island_coast.py sidecar <orig> <new>        # carry the shelf into IslandRoads' natural-ground sidecar
                                                              # (then re-stamp: stamp_roadkit_terrain.gd)

The ZONES are the design table of PLAN.md 3.8 ("hard edges where people work, soft sand where they play") as data
other steps read: which coast is beach, quay, cliff, harbour, gulf, the military harbour, the farm coast and the
airport island, each a rectangle in Godot x/z. Later placement (beach props, the fishing port, quay pieces) reads it.

The SHELF: today every coast drops from ~+0.5 m straight to the -24 m seabed within one cell -- right for a quay or a
cliff, wrong for a coral beach. Sea cells whose nearest land is BEACH land (inside a beach zone and under 3 m, so the
massif's cliffs never qualify) are raised to a shelf: -0.3 m at the waterline to -3 m 150 m out, then down to the
seabed by 350 m out (a cosine). Only sea is raised (h < 0); land and quays are never touched. The water shader colours
by depth (turquoise and caustics over the first 12 m, `depth_size`), so the shelf reads as a lagoon with no shader
change. Grid layout: `tools/godot/dump_height_grid.gd` (row j = z0 + j * step, column i = x0 + i * step); the
default window is the whole world square at the terrain's 2 m vertex spacing.
"""
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "assets", "world_source", "island_coast.json")
X0 = Z0 = -2304.0
STEP = 2.0
N = 2305

#: kind -> [(x0, x1, z0, z1), ...] in Godot metres. Beaches are the only kind the shelf reads.
ZONES = {
    "beach":            [(-2304.0, -1450.0, -600.0, 700.0),     # the west coast along rinkai_dori (resort beach)
                         (-2000.0, -780.0, 600.0, 1250.0),      # the south-west shore (0.57 km2, 99% flat): beach park
                         (700.0, 2304.0, -2304.0, -350.0)],     # the north-east farm coast (sugar cane to the sea)
    "cliff":            [(-2304.0, 700.0, -2304.0, -600.0)],    # the north-west massif meets the sea
    "industrial_harbour": [(-780.0, 220.0, 950.0, 2304.0)],     # the square peninsula: reclaimed land, quays
    "gulf":             [(220.0, 700.0, 400.0, 2304.0)],        # the U inlet, open water, the city's waterfront north
    "military_harbour": [(700.0, 1150.0, 450.0, 1050.0)],       # the inlet's east shore, beside the airport bridge
    "airport_island":   [(700.0, 2304.0, 1300.0, 2304.0)],      # one terminal, one or two runways
    "fishing_port":     [(1500.0, 1900.0, -1400.0, -1000.0)],   # a small 漁港 on the farm coast (placement later)
}
BEACH_LAND_MAX = 3.0
SHELF_EDGE, SHELF_DEEP = -0.3, -3.0
SHELF_W, DROP_W = 150.0, 200.0
HARD_FADE = 150.0
SEABED = -24.0
MAX_ADDED_STEP = 1.0     # m per 2 m cell: no underwater wall where the shelf meets deep water


def write_zones():
    doc = {"notes": "Written by tools/island_coast.py from its ZONES table (PLAN.md 3.8): the island's coast types as "
                    "Godot x0,x1,z0,z1 rectangles. Edit the table in the tool, not this file.",
           "zones": {k: [list(r) for r in v] for k, v in ZONES.items()}}
    text = json.dumps(doc, indent=1) + "\n"
    changed = not os.path.exists(OUT) or open(OUT).read() != text
    if changed:
        open(OUT, "w").write(text)
    print("island_coast: %s %s" % ("wrote" if changed else "unchanged", os.path.relpath(OUT, ROOT)))


def in_rects(kind):
    xs = X0 + np.arange(N) * STEP
    zs = Z0 + np.arange(N) * STEP
    m = np.zeros((N, N), dtype=bool)
    for x0, x1, z0, z1 in ZONES[kind]:
        ci = (xs >= x0) & (xs <= x1)
        rj = (zs >= z0) & (zs <= z1)
        m |= np.outer(rj, ci)
    return m


def hard_zones():
    """Water that keeps its depth whatever beach is near: cliffs, the harbours and the gulf."""
    return in_rects("cliff") | in_rects("industrial_harbour") | in_rects("gulf") | in_rects("military_harbour")


def distance_from(src, max_m):
    """Metres from the nearest `src` cell (an octagonal dilation, within ~8% of Euclidean), inf past max_m."""
    d = np.full(src.shape, np.inf, dtype=np.float32)
    d[src] = 0.0
    front = src.copy()
    reached = src.copy()
    steps = int(max_m / STEP) + 1
    for k in range(1, steps + 1):
        grown = front.copy()
        grown[1:, :] |= front[:-1, :]
        grown[:-1, :] |= front[1:, :]
        grown[:, 1:] |= front[:, :-1]
        grown[:, :-1] |= front[:, 1:]
        if k % 2 == 0:                                   # alternate 4- and 8-connected steps: an octagon
            g2 = grown.copy()
            g2[1:, 1:] |= front[:-1, :-1]
            g2[:-1, :-1] |= front[1:, 1:]
            g2[1:, :-1] |= front[:-1, 1:]
            g2[:-1, 1:] |= front[1:, :-1]
            grown = g2
        new = grown & ~reached
        d[new] = k * STEP
        reached |= new
        front = grown
    return d


def shelf_target(d):
    t = np.full(d.shape, -np.inf, dtype=np.float32)
    near = d <= SHELF_W
    t[near] = SHELF_EDGE + (SHELF_DEEP - SHELF_EDGE) * (d[near] / SHELF_W)
    mid = (d > SHELF_W) & (d <= SHELF_W + DROP_W)
    u = (d[mid] - SHELF_W) / DROP_W
    t[mid] = SHELF_DEEP + (SEABED - SHELF_DEEP) * (1 - np.cos(math.pi * u)) / 2
    return t


def shelf_grid(h):
    """The shelf applied to a height grid (N x N, Godot metres); returns the new grid."""
    land = h >= 0.0
    beach_land = land & (h < BEACH_LAND_MAX) & in_rects("beach")
    other_land = land & ~beach_land
    db = distance_from(beach_land, SHELF_W + DROP_W)
    do = distance_from(other_land, SHELF_W + DROP_W)
    sea = ~land & np.isfinite(h)
    # a sea cell takes the shelf only where BEACH land is its nearest shore (a quay or a cliff next door keeps depth)
    target = shelf_target(db)
    target[~np.isfinite(target)] = SEABED             # past the drop the shelf IS the seabed
    hard = hard_zones() & ~in_rects("beach")
    take = sea & (db <= do) & np.isfinite(db) & ~hard
    # fade the shelf out over HARD_FADE m approaching any water it does not take (a cliff/harbour zone, or sea whose
    # nearest shore is not a beach), so there is no underwater wall at its edge. The target itself fades toward the
    # seabed, so the result depends on the land mask only and the shelf of a shelved grid is itself (idempotent)
    w = np.clip(distance_from(sea & ~take, HARD_FADE) / HARD_FADE, 0.0, 1.0)
    faded = w * target + (1.0 - w) * SEABED
    out = h.copy()
    out[take] = np.maximum(h[take], faded[take])
    return out


def shelf(src_path, out_path):
    h = np.fromfile(src_path, dtype=np.float32).reshape(N, N)
    out = shelf_grid(h)
    raised = int(np.count_nonzero(out != h))
    out.astype(np.float32).tofile(out_path)
    print("island_coast: shelf raised %d sea cells (%.2f km2) -> %s" % (raised, raised * STEP * STEP / 1e6, out_path))


def check(path, orig_path=None):
    """The beaches have their shelf; with the ORIGINAL grid, also that no quay, cliff or harbour cell was touched
    (a quay's depth is the terrain's own business -- measured, 13% of harbour/gulf water within 20 m of a quay is
    already under 10 m deep before any shelf, at the inlet's sloping ends -- so the rule is "unchanged", not a depth)."""
    h = np.fromfile(path, dtype=np.float32).reshape(N, N)
    land = h >= 0.0
    beach_land = land & (h < BEACH_LAND_MAX) & in_rects("beach")
    db = distance_from(beach_land, 60.0)
    # water within HARD_FADE of a cliff/harbour zone is faded back to depth on purpose; judge the rest
    shallow = (~land) & (db <= 60.0) & (db > 0) & ~np.isfinite(distance_from(hard_zones() & ~in_rects("beach"),
                                                                              HARD_FADE))
    frac = float(np.mean(h[shallow] > -2.5)) if shallow.any() else 0.0
    ok = frac >= 0.95
    msg = "%.1f%% of sea within 60 m of a beach is shallower than 2.5 m" % (100 * frac)
    if orig_path:
        o = np.fromfile(orig_path, dtype=np.float32).reshape(N, N)
        hard = hard_zones()
        touched = int(np.count_nonzero((h != o) & hard & ~in_rects("beach")))
        land_touched = int(np.count_nonzero((h != o) & (o >= 0.0)))
        added = 0.0                                      # the steepest step the shelf ADDED between two sea cells
        for ax in (0, 1):
            d = np.abs(np.diff(h, axis=ax)) - np.abs(np.diff(o, axis=ax))
            both = (h < 0)[1:, :] & (h < 0)[:-1, :] if ax == 0 else (h < 0)[:, 1:] & (h < 0)[:, :-1]
            if both.any():
                added = max(added, float(d[both].max()))
        ok = ok and touched == 0 and land_touched == 0 and added <= MAX_ADDED_STEP
        msg += ("; %d quay/cliff/harbour cell(s) and %d land cell(s) changed; steepest step added %.2f m per cell"
                % (touched, land_touched, added))
    print("island_coast: %s -> %s" % (msg, "PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def sidecar(orig_path, new_path, stem=os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads")):
    """Carry the shelf into a stamped road network's NATURAL-ground sidecar (`<stem>.ground.bin`, the kit frame:
    kit x = Godot x, kit y = -Godot z). A stamp re-derives its corridors from that sidecar, so without this a re-stamp
    or a restore would put the old seabed back under every stamped corridor. The shelf is re-run on the NATURAL
    ground (the terrain, with the sidecar's values where it covers), so a stamp-owned cell -- a fill toe in the sea
    -- gets the shelf its natural seabed would have had. Idempotent: the shelf of a shelved grid is itself. `<new>`
    is only used to size the report; the sidecar is derived from `<orig>` alone."""
    head = json.load(open(stem + ".ground.json"))
    nx, ny, st = head["nx"], head["ny"], head["step"]
    ox, oy = head["origin"]
    g = np.fromfile(stem + ".ground.bin", dtype=np.float32).reshape(ny, nx)
    o = np.fromfile(orig_path, dtype=np.float32).reshape(N, N)
    h = np.fromfile(new_path, dtype=np.float32).reshape(N, N)
    ii = np.round((ox + np.arange(nx) * st - X0) / STEP).astype(int)
    jj = np.round((-(oy + np.arange(ny) * st) - Z0) / STEP).astype(int)
    O, H = o[np.ix_(jj, ii)], h[np.ix_(jj, ii)]
    fin = np.isfinite(g)
    offset = float(np.median((g - O)[fin]))                  # the network's height offset (-0.6 on the island)
    # the natural ground as a whole-world grid: the terrain, with the sidecar's natural value wherever it covers
    nat = o.copy()
    nat[np.ix_(jj, ii)] = np.where(fin, g - offset, O)
    nat_new = shelf_grid(nat)
    want = (nat_new[np.ix_(jj, ii)] + offset).astype(np.float32)
    take = fin & (np.abs(want - g) > 1e-4)
    g[take] = want[take]
    if take.any():
        g.astype(np.float32).tofile(stem + ".ground.bin")
    print("island_coast: sidecar %s: %d cell(s) took the shelf (network offset %.2f m)"
          % (os.path.basename(stem), int(take.sum()), offset))

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["zones"]:
        write_zones()
    elif a[:1] == ["shelf"] and len(a) == 3:
        shelf(a[1], a[2])
    elif a[:1] == ["sidecar"] and len(a) == 3:
        sidecar(a[1], a[2])
    elif a[:1] == ["check"] and len(a) in (2, 3):
        check(a[1], a[2] if len(a) == 3 else None)
    else:
        raise SystemExit(__doc__)
