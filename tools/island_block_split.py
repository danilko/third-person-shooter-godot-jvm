#!/usr/bin/env python3
"""island_block_split.py -- SPLIT THE BIG BLOCKS (user, 2026-10-03: "for some of the parks, can't they just build
additional streets ... split into smaller rectangles with more buildings?", with sketches of a block cut by one street
across it, and of the halves cut again by a T).

    python3 tools/island_block_split.py derive <layout record>   # -> assets/world_source/pieces/IslandBlockSplits.json
    python3 tools/island_block_split.py check                    # the recorded splits still parse

The street grid leaves some blocks far deeper than one row of buildings on each side can fill: the frontage rows face
out, and the middle is empty (`island_buildings.deep_fill` then puts car parks there). This cuts such a block with a
straight street across its middle, from one boundary road to the opposite one (a T at each end), square to the
block's long axis -- and then, where a half is still deep, cuts that half again with a street that ends on the first
one (the T the sketch shows).

The splits are DERIVED ONCE against a layout and FROZEN as data (the IslandSites rule): `island_core_streets.py
--after` adds them in every later layout, after the grid planner, as authored streets. Re-derive after a layout
change that moves the blocks (the check reports splits whose roads are gone).

A cut is taken only if:
  * both ends land on an at-grade street (not an expressway, the dike, the touge or the coast road), at least
    JUNCTION_CLEAR from any junction on it, and `island_core_streets.add` can actually cut the road there;
  * its whole length runs over buildable ground: no site, reserve, civic plot, rail corridor, dike or water, and no
    other road within PARALLEL_CLEAR along it;
  * both halves stay at least MIN_HALF deep (a row of buildings each side of every street), and
  * it serves at least MIN_GAIN of the block's empty ground (cells > 48 m from any street a building can front).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np                       # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandBlockSplits.json")
JUNCTION_CLEAR = 34.0    # m from any junction centre on the road an end lands on (a mouth stands ~26 m out)
END_CLEAR = 40.0         # m from the end of the road an end lands on
PARALLEL_CLEAR = 30.0    # m: no other road this near the cut's interior
MIN_HALF = 45.0          # m: each half at least this deep, measured square to the cut
MIN_GAIN = 2500.0        # m2 of empty ground the cut must serve
REACH = 48.0             # m: a cell is "served" within this of a street (the deep-vacancy measure)
DEPTH = 2                # a block is cut, and each half once more
from island_plan import MOUNTAIN_ROADS  # noqa: E402
NO_END = ("shuto_", "ring_kita", "kaigan_", "rail", "JCT", "GORE") + MOUNTAIN_ROADS   # the dike's side road (teibo_) is an ordinary street
SKIP_REGIONS = (None, "farm", "airport")


def deep_mask(record):
    """(field, deep 4 m mask, frontage segments) for `record`, the deep-vacancy measure."""
    import island_buildings as IB
    IB.RECORD = record
    if os.environ.get("GROUND"):
        IB.GROUND = os.environ["GROUND"]
    net, grid, cors = IB.solve_bands()
    f = IB.Field(os.environ.get("HGRID", os.path.join(ROOT, "assets", "world_source", "terrain", "island_land.f32")))
    segs = []
    for line, _h, owner in cors:
        owner = str(owner)
        pts = [(x, -y, z, half) for (x, y, z, half) in line]
        walk, _lanes = IB.road_walk(net, owner)
        for a, b in zip(pts, pts[1:]):
            f.block_capsule(a[:2], b[:2], max(a[3], b[3]) + walk + 2.0)
        if not owner.startswith(("JCT:", "GORE:")) and not owner.startswith(IB.SKIP_ROADS):
            for a, b in zip(pts, pts[1:]):
                segs.append((a[0], a[1], b[0], b[1], max(a[3], b[3]) + walk))
    text = open(IB.SCENE).read()
    for (cx, cz, yaw, hx, hz) in IB.site_exclusions(text):
        f.block_box(cx, cz, yaw, hx, hz, hold=True)
    IB.rail_reserve(f)
    IB.plan_reserves(f)
    frontage = []
    IB.civic_plots(f, frontage)
    IB.seawall_works(f)
    return IB, net, f, segs


def main(argv):
    if not argv or argv[0] not in ("derive", "check"):
        raise SystemExit(__doc__)
    if argv[0] == "check":
        d = json.load(open(OUT))
        print("island_block_split: %d split(s) recorded" % len(d["splits"]))
        return 0
    record = argv[1]
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    import point_model as pm
    import island_core_streets as CS
    import island_roadgen as rg
    IB, net0, f, segs = deep_mask(record)
    k = 4
    n = f.n // k
    B = f.blocked[:n * k, :n * k].reshape(n, k, n, k).any(axis=(1, 3))
    hs = f.h2[:2 * n:2, :2 * n:2]
    gy, gx = np.gradient(hs, 4.0)
    buildable = (hs > 0.4) & (np.hypot(gx, gy) < 0.08) & ~B
    X0 = -IB.HALF
    cen = X0 + (np.arange(n) + 0.5) * k
    near = np.zeros((n, n), bool)
    for x0, z0, x1, z1, half in segs:
        r = half + REACH
        i0 = max(0, int((min(x0, x1) - r - X0) // k)); i1 = min(n, int((max(x0, x1) + r - X0) // k) + 1)
        j0 = max(0, int((min(z0, z1) - r - X0) // k)); j1 = min(n, int((max(z0, z1) + r - X0) // k) + 1)
        if i1 <= i0 or j1 <= j0:
            continue
        px = cen[i0:i1][None, :]; pz = cen[j0:j1][:, None]
        dx, dz = x1 - x0, z1 - z0
        L2 = dx * dx + dz * dz or 1e-9
        t = np.clip(((px - x0) * dx + (pz - z0) * dz) / L2, 0, 1)
        near[j0:j1, i0:i1] |= np.hypot(px - (x0 + t * dx), pz - (z0 + t * dz)) <= r
    deep = buildable & ~near

    def cells_of(poly):
        """record-frame polygon -> (deep cell count inside)"""
        x0, y0, x1, y1 = poly.bounds
        i0, i1 = int((x0 - X0) // k), int((x1 - X0) // k) + 1
        j0, j1 = int((-y1 - X0) // k), int((-y0 - X0) // k) + 1
        c = 0
        from shapely import prepared
        pp = prepared.prep(poly)
        for j in range(max(j0, 0), min(j1, n)):
            for i in range(max(i0, 0), min(i1, n)):
                if deep[j, i] and pp.contains(Point(cen[i], -cen[j])):
                    c += 1
        return c * k * k

    def hard_at(x, y):
        """the cut may not run here: blocked ground that is not a road band (a site, reserve, plot, rail, water)"""
        i, j = int((x - X0) // k), int((-y - X0) // k)
        if not (0 <= i < n and 0 <= j < n):
            return True
        return not buildable[j, i] and not near_road_band(x, y)

    # the road bands alone (grown), so a cut may cross the band of the road it ENDS on
    rb = np.zeros((n, n), bool)
    for x0, z0, x1, z1, half in segs:
        r = half + 3.0
        i0 = max(0, int((min(x0, x1) - r - X0) // k)); i1 = min(n, int((max(x0, x1) + r - X0) // k) + 1)
        j0 = max(0, int((min(z0, z1) - r - X0) // k)); j1 = min(n, int((max(z0, z1) + r - X0) // k) + 1)
        if i1 <= i0 or j1 <= j0:
            continue
        px = cen[i0:i1][None, :]; pz = cen[j0:j1][:, None]
        dx, dz = x1 - x0, z1 - z0
        L2 = dx * dx + dz * dz or 1e-9
        t = np.clip(((px - x0) * dx + (pz - z0) * dz) / L2, 0, 1)
        rb[j0:j1, i0:i1] |= np.hypot(px - (x0 + t * dx), pz - (z0 + t * dz)) <= r

    def near_road_band(x, y):
        i, j = int((x - X0) // k), int((-y - X0) // k)
        return 0 <= i < n and 0 <= j < n and rb[j, i]

    net = pm.load_network(record)

    def lines_of(net_):
        out = []
        for name, r in net_.roads.items():
            ch = net_.chain(r)
            if len(ch) >= 2:
                out.append((str(name), LineString([p.pos[:2] for p in ch])))
        return out

    def junction_centres(net_):
        cs = []
        for cl in net_.junction_cliques():
            ps = [net_.points[u].pos for u in cl]
            cs.append((sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)))
        return cs

    def at_grade(net_, name):
        return not str(name).startswith(NO_END)

    ground = rg.Ground()
    splits = []
    WHY = {}

    def no(r):
        WHY[r] = WHY.get(r, 0) + 1
    made = 0

    def try_cut(net_, poly, depth, tag):
        nonlocal made
        if poly.area < 2 * MIN_HALF * 60.0:
            return
        mrr = poly.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:4]
        e0 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        L0, L1 = math.hypot(*e0), math.hypot(*e1)
        long_ = e0 if L0 >= L1 else e1
        Ll = max(L0, L1)
        ux, uy = long_[0] / Ll, long_[1] / Ll                      # the block's long axis
        c = poly.centroid
        good = []
        lines = lines_of(net_)
        jcs = junction_centres(net_)
        cands = []
        for axis in ((ux, uy), (-uy, ux)):                       # square to the long axis first, then along it
            La = Ll if axis == (ux, uy) else min(L0, L1)
            for frac in (0.0, -0.06, 0.06, -0.12, 0.12, -0.18, 0.18, -0.24, 0.24, -0.3, 0.3, -0.36, 0.36):
                cands.append((axis, frac, La))
        for (ax_, ay_), frac, La in cands:
            px, py = c.x + ax_ * frac * La, c.y + ay_ * frac * La
            # the cut runs SQUARE to `axis`, across the block
            vx, vy = -ay_, ax_
            far = LineString([(px - vx * 2000, py - vy * 2000), (px + vx * 2000, py + vy * 2000)])
            inter = far.intersection(poly)
            if inter.is_empty:
                continue
            parts = [inter] if inter.geom_type == "LineString" else list(getattr(inter, "geoms", []))
            seg = next((p for p in parts if p.geom_type == "LineString" and p.distance(Point(px, py)) < 1.0), None)
            if seg is None or seg.length < 60.0:
                no("short"); continue
            a, b = seg.coords[0], seg.coords[-1]
            # each end on an at-grade road (the boundary), clear of junctions and road ends
            ends = []
            ok = True
            for q in (a, b):
                best_r = min(((ln.distance(Point(q)), nm, ln) for nm, ln in lines), default=None)
                if best_r is None or best_r[0] > 3.0 or not at_grade(net_, best_r[1]):
                    no("end not on a street" if best_r is None or best_r[0] > 3.0 else "end on " + best_r[1].split('_')[0]); ok = False
                    break
                ln = best_r[2]
                s0 = ln.project(Point(q))
                # (a road PIECE ends at a junction's mouth: the junction clearance below covers it, and a piece too
                # short to cut is refused by the road kit itself)
                if any(math.dist(q, jc) < JUNCTION_CLEAR for jc in jcs):
                    no("junction"); ok = False
                    break
                ends.append(best_r[1])
            if not ok:
                continue
            # the interior: buildable, no other road alongside
            interior = LineString([seg.interpolate(20.0).coords[0], seg.interpolate(seg.length - 20.0).coords[0]])
            if any(hard_at(*interior.interpolate(t).coords[0]) for t in np.arange(0.0, interior.length, 3.0)):
                no("hard ground"); continue
            if any(ln.distance(interior) < PARALLEL_CLEAR for nm, ln in lines if nm not in ends):
                no("road alongside"); continue
            # both halves deep enough for a row each side
            halves = [g for g in _split(poly, seg) if g.area > 1.0]
            if len(halves) != 2 or any(_depth_across(h, (vx, vy)) < MIN_HALF for h in halves):
                no("halves"); continue
            gain = sum(cells_of(h.intersection(seg.buffer(REACH))) for h in halves)
            if gain < MIN_GAIN:
                no("gain"); continue
            good.append((gain, a, b, ends, halves))
        # the best cut the road kit can actually make: a cut whose road piece is too short for a mouth is refused
        # there, so the next one is tried (on a copy: the first T may succeed before the second fails)
        import copy
        good.sort(key=lambda g_: -g_[0])
        name = "%s_%d" % (tag, made)
        best = None
        for gain, a, b, ends, halves in good[:12]:
            frame = dict(name=name, first=ends[0].split("__")[0], corners=[a, b], last=ends[1].split("__")[0],
                         after=True)
            trial = copy.deepcopy(net_)
            try:
                CS.add(trial, frame, ground)
            except (ValueError, StopIteration, KeyError) as e:
                no("road kit")
                continue
            net_.points, net_.roads = trial.points, trial.roads
            best = (gain, a, b, ends, halves)
            break
        if best is None:
            return
        gain, a, b, ends, halves = best
        made += 1
        splits.append(dict(frame, corners=[[round(a[0], 1), round(a[1], 1)], [round(b[0], 1), round(b[1], 1)]],
                           gain_m2=int(gain)))
        print("island_block_split: %s %.0f m across a %.0f m2 block, serves %.0f m2 (%s .. %s)"
              % (name, LineString([a, b]).length, poly.area, gain, frame["first"], frame["last"]))
        if depth + 1 < DEPTH:
            for h in halves:
                try_cut(net_, h, depth + 1, tag)

    # the blocks: faces of the at-grade street graph
    ls = [ln for nm, ln in lines_of(net) if at_grade(net, nm) or str(nm).startswith(("ring_kita", "teibo_", "kaigan_"))]
    # a road stops at its junction's MOUTH, short of the crossing: join every mouth to its pad's centre, or no block
    # closes
    for cl in net.junction_cliques():
        ps = [net.points[u].pos for u in cl]
        cx, cy = sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)
        for p in ps:
            ls.append(LineString([p[:2], (cx, cy)]))
    faces = list(polygonize(unary_union(ls)))
    faces = [p for p in faces if p.area > 2 * MIN_HALF * 60.0]
    scored = []
    for p in faces:
        reg = IB.region_of(p.centroid.x, p.centroid.y)
        if (reg[0] if reg else None) in SKIP_REGIONS:
            continue
        g = cells_of(p)
        if g >= MIN_GAIN:
            scored.append((g, p))
    scored.sort(key=lambda t: -t[0])
    print("island_block_split: %d block(s) with >= %.0f m2 of empty ground" % (len(scored), MIN_GAIN))
    if os.environ.get("FACES_PNG"):
        _draw(scored, deep, cen, X0, net, os.environ["FACES_PNG"])
    for fi, (g, p) in enumerate(scored):
        before = dict(WHY)
        m0 = made
        try_cut(net, p, 0, "kukaku")
        if os.environ.get("FACES_PNG"):
            diff = {k_: WHY[k_] - before.get(k_, 0) for k_ in WHY if WHY[k_] != before.get(k_, 0)}
            print("  face %d (%.0f m2 empty, %.0f m2): %s %s" % (fi, g, p.area, "CUT" if made > m0 else "-", diff))
    print("island_block_split: refusals %s" % WHY)
    json.dump({"schema": 1, "source": "tools/island_block_split.py derive %s" % os.path.basename(record),
               "splits": splits}, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("island_block_split: %d split(s) -> %s" % (len(splits), os.path.relpath(OUT, ROOT)))
    return 0


def _draw(scored, deep, cen, X0, net, path):
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = -1500.0, -1600.0, 1600.0, 1500.0
    sc = 0.32
    im = Image.new("RGB", (int((x1 - x0) * sc), int((z1 - z0) * sc)), (25, 25, 35))
    d = ImageDraw.Draw(im)
    T = lambda x, z: ((x - x0) * sc, (z - z0) * sc)
    js, is_ = np.nonzero(deep)
    for j, i in zip(js, is_):
        x, z = cen[i], cen[j]
        d.point(T(x, z), fill=(200, 110, 40))
    for name, r in net.roads.items():
        ch = net.chain(r)
        d.line([T(p.pos[0], -p.pos[1]) for p in ch], fill=(150, 150, 255) if str(name).startswith("shuto") else (200, 200, 200))
    for k, (g, p) in enumerate(scored):
        d.polygon([T(x, -y) for x, y in p.exterior.coords], outline=(80, 255, 80))
        c = p.centroid
        d.text(T(c.x, -c.y), "%d" % k, fill=(255, 255, 80))
    im.save(path)


def _split(poly, seg):
    from shapely.ops import split
    from shapely.geometry import LineString
    a, b = seg.coords[0], seg.coords[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    ext = LineString([(a[0] - dx / L * 5, a[1] - dy / L * 5), (b[0] + dx / L * 5, b[1] + dy / L * 5)])
    try:
        return list(split(poly, ext).geoms)
    except Exception:
        return []


def _depth_across(poly, v):
    """the polygon's extent measured along the unit vector square to v (the cut's direction): its depth from the cut"""
    nx, ny = -v[1], v[0]
    vals = [x * nx + y * ny for x, y in poly.exterior.coords]
    return max(vals) - min(vals)


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
    sys.exit(main(sys.argv[1:]))
