#!/usr/bin/env python3
"""island_coast_road.py -- the north-west coast road (PLAN.md 3.15): a 2 + 2 BENCH road cut into the cliff foot, with
rock sheds where the cut face above it is tallest.

    python3 tools/island_coast_road.py derive <height dump .f32>   # ONE-SHOT: the alignment, from the natural ground
    python3 tools/island_coast_road.py add <record> [--from <record>]   # the layout step: the road, into a record

Two halves, on purpose (the touge's shape, 3.2d):

* **derive** reads a Terrain3D height dump (`tools/godot/dump_height_grid.gd -- <out> -2304 -2304 1153 1153 4`, the
  whole island at 4 m) and writes `assets/world_source/pieces/IslandCoastRoad.json`: the stations (record frame, z
  included) and each station's shed flag. It walks the coast with the sea on its left, `D_TARGET` inland of the
  water line: far enough that the paved band plus the stamp's flat verge (`road_kit_stamp.VERGE`) ends at the cliff
  edge, near enough that the sea is IN VIEW past the barrier -- and the road never stands on the sea, so nothing is
  filled into it (the user's decision: "cut into the mountain, not added from the seabed"). The height is the
  natural ground under the centreline, capped at `Z_BENCH` and lowered by a `GRADE` cone, so the road only ever
  CUTS; a hill it cannot climb it runs under. Run once; the file is the authored alignment and is reviewed like the
  record. Re-derive only on purpose (the terrain it reads is stamped with this road afterwards).
* **add** is deterministic and terrain-free: it puts the road into a record as a `coast`-preset road `kaigan_dori`,
  its head a JOINT on `kitahama_dori__3`'s end (the road continues it westward) and its tail one arm of a new T at the
  `nishihama_dori__2` / `rinkai_dori` corner (the corner's fillet dropped: the two become the through road and the
  stem). `island_layout.py` runs it first, on the arterials.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm              # noqa: E402
import point_presets as ppr           # noqa: E402

ALIGNMENT = os.path.join(ROOT, "assets", "world_source", "pieces", "IslandCoastRoad.json")
NAME = "kaigan_dori"
# THE COASTAL RING (PLAN.md 3.29 v8/v14, 3.30 L2): this road is its north-west side. Its two ends are FREE road ends
# of the arterial layer (`island_network.py`), found by position, never by name -- the builder names roads by how it
# cut them. HEAD: the ring's north-east end on the farm coast; the coast road continues it westward (a joint).
# CORNER: the residential south-west shore, where the ring's west side and rinkai_dori both end; the coast road's tail
# makes the T there.
HEAD_NEAR = (631.0, 1652.0)           # record: near the ring's north-east free end
CORNER_NEAR = (-1420.0, -330.0)       # record: near the ring's south-west free end (and rinkai's west end)
CORNER_R = 90.0                       # every free road end this near the corner is an arm of the T
CORNER_MOUTH = 45.0                   # the coast road's own mouth, this far from the corner (setback re-solves it)
START_BACK = 0.0                      # the walk starts AT the corner

# the dump
N, X0, CELL = 1153, -2304.0, 4.0
SEA_Z = 0.3                           # Godot height of the water line (sea level 0, the beach shelf starts under it)
GODOT_TO_RECORD = -0.6                # the IslandRoads node stands at Y +0.6

# the alignment
D_TARGET = 17.0                       # centreline to the water line: half 10 + verge 6 = the band ends 1 m short of it
D_MIN = 15.0
STEP = 8.0
MAX_TURN = math.radians(5.0)          # per STEP while walking
JOIN_M = 140.0                        # the walk hands over to a cubic onto the joint this far from it
SMOOTH_M = 90.0                       # moving average over this much road, three passes
STATION = 30.0
Z_BENCH = 12.0                        # the bench's height over the sea (record z) where the cliff meets the water
Z_MIN = 1.0                           # ... and never lower than this over it
SEA_EDGE = 5.0                        # the sea-side band edge the road may stand no higher than: paved edge + this
GRADE = 0.05
HALF = 10.0                           # the coast preset's paved half-width, for the uphill probe
SHED_H = 35.0                         # a shed where the cut face above the road is at least this tall ...
SHED_MIN, SHED_MAX = 90.0, 300.0      # ... for this long (shorter is not worth a roof, longer is a tunnel's job)
SHED_COUNT = 4
SHED_GAP = 250.0


class Dump(object):
    def __init__(self, path):
        import numpy as np
        self.np = np
        self.h = np.fromfile(path, dtype=np.float32).reshape(N, N)

    def z(self, x, y):
        """Natural ground, RECORD z, bilinear; None off the dump."""
        gx, gz = (x - X0) / CELL, (-y - X0) / CELL
        i, j = int(math.floor(gx)), int(math.floor(gz))
        if not (0 <= i < N - 1 and 0 <= j < N - 1):
            return None
        u, v = gx - i, gz - j
        h = self.h
        a = h[j, i] * (1 - u) + h[j, i + 1] * u
        b = h[j + 1, i] * (1 - u) + h[j + 1, i + 1] * u
        return float(a * (1 - v) + b * v) + GODOT_TO_RECORD

    def distance_field(self, rect, reach=100.0):
        """Distance to the water line (metres, capped at `reach`) over record `rect` (x0, y0, x1, y1), and the grid
        placement: (dist, i0, j0)."""
        np = self.np
        i0, i1 = int((rect[0] - X0) / CELL), int((rect[2] - X0) / CELL) + 1
        j0, j1 = int((-rect[3] - X0) / CELL), int((-rect[1] - X0) / CELL) + 1
        sea = self.h[j0:j1, i0:i1] < SEA_Z
        R = int(reach / CELL)
        H, W = sea.shape
        pad = np.pad(sea, R, constant_values=False)
        dist = np.full(sea.shape, reach, np.float32)
        for di in range(-R, R + 1):
            for dj in range(-R, R + 1):
                d = CELL * math.hypot(di, dj)
                if d > reach:
                    continue
                m = pad[R + dj:R + dj + H, R + di:R + di + W]
                np.minimum(dist, np.where(m, d, reach), out=dist)
        return dist, i0, j0


class Field(object):
    """Bilinear distance-to-sea and its gradient (pointing INLAND), record frame."""

    def __init__(self, dist, i0, j0):
        self.d, self.i0, self.j0 = dist, i0, j0

    def at(self, x, y):
        gx, gz = (x - X0) / CELL - self.i0, (-y - X0) / CELL - self.j0
        i, j = int(math.floor(gx)), int(math.floor(gz))
        H, W = self.d.shape
        if not (0 <= i < W - 1 and 0 <= j < H - 1):
            return None
        u, v = gx - i, gz - j
        d = self.d
        return float((d[j, i] * (1 - u) + d[j, i + 1] * u) * (1 - v) + (d[j + 1, i] * (1 - u) + d[j + 1, i + 1] * u) * v)

    def grad(self, x, y, e=4.0):
        a, b = self.at(x + e, y), self.at(x - e, y)
        c, d = self.at(x, y + e), self.at(x, y - e)
        if None in (a, b, c, d):
            return None
        gx, gy = (a - b) / (2 * e), (c - d) / (2 * e)
        n = math.hypot(gx, gy)
        return (gx / n, gy / n) if n > 1e-6 else None


def _heading_to(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def walk(field, start, heading, end, end_heading):
    """Walk the coast from `start` with the sea on the LEFT, `D_TARGET` inland, until the point nearest `end`; then a
    cubic onto `end` arriving along `end_heading`. Returns the plan polyline."""
    pts = [start]
    h = heading
    best = (1e18, 0)
    for k in range(4000):
        x, y = pts[-1]
        g = field.grad(x, y)
        d = field.at(x, y)
        if g is not None and d is not None and d < 99.0:
            tx, ty = -g[1], g[0]                      # along the coast, sea on the left
            corr = max(-1.0, min(1.0, (D_TARGET - d) / 10.0))
            want = math.atan2(ty + g[1] * corr * 0.8, tx + g[0] * corr * 0.8)
        else:
            # beyond the field's reach inland: head back toward the sea (turn left)
            want = h + MAX_TURN
        dh = max(-MAX_TURN, min(MAX_TURN, _wrap(want - h)))
        h += dh
        pts.append((x + STEP * math.cos(h), y + STEP * math.sin(h)))
        de = math.dist(pts[-1], end)
        if de < best[0]:
            best = (de, len(pts) - 1)
        if k > 50 and (de < JOIN_M or (de > best[0] + 300.0 and best[0] < 500.0)):
            break
    cut = best[1]
    pts = pts[:cut + 1]
    # the join: a cubic from the walk's last point along its heading onto `end` along `end_heading`
    a = pts[-1]
    ha = _heading_to(pts[-2], pts[-1])
    L = math.dist(a, end) / 3.0
    c1 = (a[0] + L * math.cos(ha), a[1] + L * math.sin(ha))
    c2 = (end[0] - L * math.cos(end_heading), end[1] - L * math.sin(end_heading))
    n = max(2, int(math.dist(a, end) / STEP))
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        pts.append(tuple(mt ** 3 * a[q] + 3 * mt * mt * t * c1[q] + 3 * mt * t * t * c2[q] + t ** 3 * end[q]
                         for q in range(2)))
    return pts


def remove_loops(pts):
    """A walk that meets a notch in the shore can circle once before it finds the coast again (measured on the
    reshaped island, 3.30: four full loops). Where the polyline crosses itself the loop between is cut out."""
    def cross(a, b, c, d):
        r = (b[0] - a[0], b[1] - a[1])
        s = (d[0] - c[0], d[1] - c[1])
        den = r[0] * s[1] - r[1] * s[0]
        if abs(den) < 1e-9:
            return None
        t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
        u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
        return (a[0] + r[0] * t, a[1] + r[1] * t) if 0 <= t <= 1 and 0 <= u <= 1 else None
    out = list(pts)
    cut = 0
    i = 0
    while i < len(out) - 3:
        hit = None
        for j in range(min(len(out) - 2, i + 400), i + 1, -1):      # the LATEST crossing: the widest loop
            q = cross(out[i], out[i + 1], out[j], out[j + 1])
            if q is not None:
                hit = (j, q)
                break
        if hit:
            j, q = hit
            out = out[:i + 1] + [q] + out[j + 1:]
            cut += 1
        i += 1
    return out, cut


def resample(pts, step):
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    out, s, k = [], 0.0, 0
    n = max(1, int(round(cum[-1] / step)))
    for m in range(n + 1):
        s = cum[-1] * m / n
        while k < len(cum) - 2 and cum[k + 1] < s:
            k += 1
        u = (s - cum[k]) / max(1e-9, cum[k + 1] - cum[k])
        out.append(tuple(pts[k][q] + (pts[k + 1][q] - pts[k][q]) * u for q in range(2)))
    return out


def smooth(pts, window_m, passes=3, fixed=3):
    """Moving average over `window_m` of road, ends held for `fixed` points."""
    k = max(1, int(window_m / STEP / 2))
    for _ in range(passes):
        out = list(pts)
        for i in range(fixed, len(pts) - fixed):
            lo, hi = max(0, i - k), min(len(pts), i + k + 1)
            out[i] = (sum(p[0] for p in pts[lo:hi]) / (hi - lo), sum(p[1] for p in pts[lo:hi]) / (hi - lo))
        pts = out
    return pts


def push_inland(field, pts, fixed=3):
    """Move every point nearer the water than `D_MIN` inland along the field's gradient, to `D_MIN`."""
    moved = 0
    out = list(pts)
    for i in range(fixed, len(pts) - fixed):
        d = field.at(*pts[i])
        g = field.grad(*pts[i])
        if d is not None and g is not None and d < D_MIN:
            out[i] = (pts[i][0] + g[0] * (D_MIN - d + 0.5), pts[i][1] + g[1] * (D_MIN - d + 0.5))
            moved += 1
    return out, moved


def profile(dump, pts, z_start, z_end):
    """Record z per point: the natural ground capped at the bench, lowered by a GRADE cone (cut only, never fill),
    pinned to the two connecting roads' heights at the ends, then vertical curves (a moving average, which cannot
    break the grade)."""
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    zt = []
    for i, p in enumerate(pts):
        g = dump.z(*p)
        # the ground at the band's SEA-side edge (the left of the SW->NE walk): the road stands no higher than it, so
        # where a beach lies at the cliff foot the road runs at the sand's level instead of on a wall above it (the
        # stamp does not fill a cut this deep, and filling would push an embankment into the sea)
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        off = HALF + SEA_EDGE
        ge = dump.z(p[0] - dy / n * off, p[1] + dx / n * off)
        cap = Z_BENCH if ge is None else max(Z_MIN, min(Z_BENCH, ge + 0.3))
        zt.append(min(cap, g if g is not None else cap))
    zt[0], zt[-1] = z_start, z_end
    n = len(pts)
    z = list(zt)
    for i in range(1, n):                              # forward and backward passes = the cone
        z[i] = min(z[i], z[i - 1] + GRADE * (cum[i] - cum[i - 1]))
    for i in range(n - 2, -1, -1):
        z[i] = min(z[i], z[i + 1] + GRADE * (cum[i + 1] - cum[i]))
    k = 3
    out = list(z)
    for i in range(1, n - 1):
        lo, hi = max(0, i - k), min(n, i + k + 1)
        out[i] = min(z[i], sum(z[lo:hi]) / (hi - lo))
    out[0], out[-1] = z_start, z_end
    return out, cum


def cut_face(dump, pts, zs, inland_sign):
    """The tallest natural ground on the uphill side, 6-20 m past the paved edge, over the road: the cut face."""
    out = []
    for i, p in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        rx, ry = dy / n * inland_sign, -dx / n * inland_sign     # the right of travel, times the side
        best = -1e9
        for off in range(int(HALF + 6), int(HALF + 21), 3):
            g = dump.z(p[0] + rx * off, p[1] + ry * off)
            if g is not None:
                best = max(best, g)
        out.append(best - zs[i])
    return out


def shed_spans(cum, face):
    """[(s0, s1)]: up to `SHED_COUNT` windows `SHED_MIN`..`SHED_MAX` long where the cut face stays over `SHED_H`,
    chosen greedily by the tallest mean face, at least `SHED_GAP` apart (a cliff that is tall all the way round would
    otherwise be ONE window: rock sheds are where the rock falls, with daylight between them)."""
    ok = [f >= SHED_H for f in face]
    cands = []
    for a in range(len(face)):
        if not ok[a]:
            continue
        b = a
        while b + 1 < len(face) and ok[b + 1] and cum[b + 1] - cum[a] <= SHED_MAX:
            b += 1
        if cum[b] - cum[a] >= SHED_MIN:
            cands.append((sum(face[a:b + 1]) / (b - a + 1), cum[a], cum[b]))
    cands.sort(reverse=True)
    out = []
    for _m, s0, s1 in cands:
        if all(s1 + SHED_GAP <= t0 or s0 >= t1 + SHED_GAP for t0, t1 in out):
            out.append((s0, s1))
        if len(out) == SHED_COUNT:
            break
    return sorted(out)


def free_ends(net):
    """[(uid, road name, neighbour uid)] of every road END that joins nothing: no junction and no other road."""
    out = []
    for name, r in net.roads.items():
        for u, nb in ((r.points[0], r.points[1]), (r.points[-1], r.points[-2])):
            p = net.points[u]
            if any(l.type == pm.LINK_JUNCTION for l in p.links):
                continue
            if len([l for l in p.links if l.type == pm.LINK_SEGMENT]) > 1:
                continue
            out.append((u, name, nb))
    return out


def head_end(net):
    """(uid, previous station's uid) of the ring's free end the coast road continues."""
    u, _n, nb = min(free_ends(net), key=lambda e: math.dist(net.points[e[0]].pos[:2], HEAD_NEAR))
    if math.dist(net.points[u].pos[:2], HEAD_NEAR) > 250.0:
        raise SystemExit("island_coast_road: no free road end near %s for the head" % (HEAD_NEAR,))
    return u, nb


def corner_ends(net):
    """The free road ends of the corner T and the corner itself (their centroid). With no free end there (the ring's
    west side and rinkai_dori were built as ONE road through the corner), the corner is the nearest point of the
    nearest road, and `add` CUTS that road to land the T."""
    ends = [e for e in free_ends(net) if math.dist(net.points[e[0]].pos[:2], CORNER_NEAR) < CORNER_R + 150.0]
    if ends:
        c = (sum(net.points[e[0]].pos[0] for e in ends) / len(ends),
             sum(net.points[e[0]].pos[1] for e in ends) / len(ends))
        return ends, c
    from island_roadgen import nearest_span
    name, i, t, d = nearest_span(net, CORNER_NEAR, "")
    a, b = (net.points[u].pos for u in net.roads[name].points[i:i + 2])
    return [], (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def cmd_derive(dump_path):
    net = pm.load_network(os.path.join(ROOT, "assets", "world_source", "pieces", "IslandRoads.arterials.roads.json"))
    e_uid, e_nb = head_end(net)
    e_pos = net.points[e_uid].pos
    e_prev = net.points[e_nb].pos
    end = (e_pos[0], e_pos[1])
    _ends, START = corner_ends(net)
    dump = Dump(dump_path)
    rect = (-2100.0, min(START[1], end[1]) - 400.0, end[0] + 400.0, 2150.0)
    field = Field(*dump.distance_field(rect))
    # walked SW -> NE with the sea on the left; the road's chain runs the other way (kitahama's tail -> the corner)
    arrive = _heading_to(end, e_prev)                  # arriving at kitahama's tail, running against its chain
    plan = walk(field, START, math.pi / 2, end, arrive)
    plan, cut = remove_loops(resample(plan, STEP))
    plan = smooth(plan, SMOOTH_M)
    total_moved = 0
    for _ in range(12):
        plan, moved = push_inland(field, plan)
        total_moved += moved
        plan = smooth(plan, 40.0, passes=1)
    plan, moved = push_inland(field, plan)
    stations = resample(plan, STATION)
    for _ in range(4):                                  # a chord across a cove cuts toward the water: push the stations
        dense = resample(stations, STEP)
        near = min(field.at(*p) for p in dense[3:-3])
        if near >= D_MIN - 1.0:
            break
        stations, _m = push_inland(field, stations, fixed=1)
    near = min(field.at(*p) for p in resample(stations, STEP)[3:-3])
    zs, cum = profile(dump, stations, 0.0, e_pos[2])
    face = cut_face(dump, stations, zs, 1.0)           # inland = right of the SW->NE walk
    spans = shed_spans(cum, face)
    # into the chain's direction (kitahama's tail first): reverse, and the sea is on the RIGHT of travel
    total = cum[-1]
    stations, zs = stations[::-1], zs[::-1]
    spans = sorted((total - s1, total - s0) for s0, s1 in spans)
    doc = {"note": "PLAN.md 3.15: derived once by tools/island_coast_road.py derive from a natural-ground dump; "
                   "the authored alignment of kaigan_dori, chain order from kitahama_dori__3's tail to the "
                   "nishihama/rinkai corner. Shed spans are metres along that chain, open to the sea (right).",
           "length_m": round(total, 1), "sheds": [[round(a, 1), round(b, 1)] for a, b in spans],
           "shed_open": pm.SHED_OPEN_RIGHT,
           "stations": [[round(p[0], 2), round(p[1], 2), round(z, 2)] for p, z in zip(stations, zs)]}
    with open(ALIGNMENT, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    grades = [abs(zs[i + 1] - zs[i]) / max(1e-9, math.dist(stations[i], stations[i + 1])) for i in range(len(zs) - 1)]
    print("island_coast_road: %.0f m, %d stations, nearest the water %.1f m (target %.0f, %d pushes), z %.1f..%.1f, "
          "steepest %.1f%%, %d shed(s) %s -> %s" % (total, len(stations), near, D_TARGET, total_moved, min(zs), max(zs),
                                                    100 * max(grades), len(spans),
                                                    ", ".join("%.0f m" % (b - a) for a, b in spans),
                                                    os.path.relpath(ALIGNMENT, ROOT)))


def _drop_until(net, road, keep_uid, from_head):
    """Remove the stations of `road` before (from_head) or after `keep_uid`; `keep_uid` becomes the end."""
    chain = list(road.points)
    k = chain.index(keep_uid)
    doomed = chain[:k] if from_head else chain[k + 1:]
    for u in doomed:
        net.remove_point(u)
    return keep_uid


def _nearest_station(net, road, xy, want):
    """The station of `road` nearest `want` metres of chain from `xy`'s end (the corner)."""
    best = None
    for u in road.points:
        d = math.dist(net.points[u].pos[:2], xy)
        if best is None or abs(d - want) < best[0]:
            best = (abs(d - want), u)
    return best[1]


def add(net, doc=None):
    """`kaigan_dori` into `net` (see the module doc). Returns a one-line summary."""
    if NAME in net.roads:
        raise SystemExit("island_coast_road: %s is already in the record" % NAME)
    doc = doc or json.load(open(ALIGNMENT))
    e_uid, _nb = head_end(net)
    sts = doc["stations"]
    if math.dist(sts[0][:2], net.points[e_uid].pos[:2]) > 0.05:
        raise SystemExit("island_coast_road: the alignment starts %.2f m from the ring's end -- re-derive"
                         % math.dist(sts[0][:2], net.points[e_uid].pos[:2]))
    ends, corner = corner_ends(net)
    # the road: stations, then cut short so its last station is a mouth CORNER_MOUTH from the corner
    road = net.add_road(pm.RoadData(NAME, pm.PointData(uid=""), ()))
    cum = [0.0]
    for a, b in zip(sts, sts[1:]):
        cum.append(cum[-1] + math.dist(a[:2], b[:2]))
    keep = [i for i, p in enumerate(sts) if math.dist(p[:2], corner) >= CORNER_MOUTH - 1.0]
    last = max(keep)
    sheds = doc.get("sheds", [])
    marks = sorted({round(s, 1) for span in sheds for s in span})
    prev = None
    first = None
    for i in range(1, last + 1):                       # station 0 IS kitahama's tail: the joint's partner
        p = net.add_station(road, tuple(sts[i]))
        if prev is None:
            first = p.uid
        else:
            net.link(prev.uid, p.uid)
        prev = p
    # the joint: a station coincident with kitahama's tail, SEGMENT-linked to it
    j = pm.PointData(pos=tuple(sts[0]))
    net.add_point(j, road)
    road.points.remove(j.uid)
    road.points.insert(0, j.uid)
    net.link(j.uid, first)
    net.link(e_uid, j.uid)
    ppr.apply_preset(net, NAME, "coast")
    # shed stations: one at each span's start and end (the flag holds from a station to the next)
    for s0, s1 in sheds:
        for s in (s0, s1):
            _insert_at(net, road, cum, sts, s)
    open_side = doc.get("shed_open", pm.SHED_OPEN_RIGHT)
    rcum = _chain_cum(net, road)
    n_shed = 0
    for u, s in zip(road.points, rcum):
        if any(s0 - 0.5 <= s < s1 - 0.5 for s0, s1 in sheds):
            net.points[u].shed = open_side
            n_shed += 1
    # the corner: the coast road's tail joins the free ends there -- one road end is a joint, two or more a junction
    from island_roadgen import make_junction, cut_road, nearest_span
    arms = [e[0] for e in ends]
    if not arms:
        name = nearest_span(net, corner, "")[0]
        arms = list(cut_road(net, corner, name, CORNER_MOUTH))
    if len(arms) == 1:
        net.link(arms[0], road.points[-1])
        kind = "a joint"
    else:
        make_junction(net, arms + [road.points[-1]], signal=False)
        kind = "a %d-arm junction" % (len(arms) + 1)
    head = "%s: %d stations, %.0f m, %d under %d shed(s), a joint on the ring's north-east end, %s at the corner" % (
        NAME, len(road.points), rcum[-1], n_shed, len(sheds), kind)
    return head + open_built_up(net, road)


#: The part of the coast road inside a BUILT-UP region is a street with footways, not a road cut into a cliff (user,
#: 2026-09-21: "the wall is only for the coast road where it runs against the mountain; farmland, residential, city
#: and the harbour stay open, with a sidewalk, so the buildings on both sides can be entered"). The regions are the
#: ones the buildings are placed in (`island_buildings.REGIONS`, record frame), so "built-up" has one owner.
OPEN_PRESET = "arterial"
#: ... and it is its own STREET by name: `island_buildings.SKIP_ROADS` fronts no building on `kaigan_dori` (the cliff
#: road), so the open stretches must not carry that prefix or nothing would ever be built beside them.
OPEN_NAME = "kaigan_machi"


def _rename(net, road, name):
    del net.roads[road.name]
    road.name = name
    net.roads[name] = road


def _built_up(x, y):
    import island_buildings as ib
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for _n, b, *_r in ib.REGIONS)


def open_built_up(net, road):
    """Split the coast road at a JOINT where it enters and leaves a built-up region, and put the built-up ends on
    `OPEN_PRESET`. Only whole leading/trailing runs are opened (the road's middle is the mountain), a shed station is
    never one of them, and a run shorter than two spans is left walled. Returns a summary suffix."""
    import point_record_ops as pro
    chain = list(road.points)
    flag = [_built_up(*net.points[u].pos[:2]) and net.points[u].shed == pm.SHED_NONE for u in chain]
    lead = 0
    while lead < len(chain) and flag[lead]:
        lead += 1
    trail = 0
    while trail < len(chain) and flag[len(chain) - 1 - trail]:
        trail += 1
    if lead >= len(chain):
        _rename(net, road, OPEN_NAME)
        ppr.apply_preset(net, OPEN_NAME, OPEN_PRESET)
        return ", all of it open (built-up)"
    notes = []
    # the trailing run first, so the leading split does not move the chain the trailing index is counted in
    if trail >= 3:
        at = chain[len(chain) - trail]
        _msg, out = pro.split_at_joint(net, at, OPEN_NAME + "__2")
        ppr.apply_preset(net, out["road"], OPEN_PRESET)
        notes.append("%s (%d stations)" % (out["road"], trail))
    if lead >= 3:
        at = chain[lead - 1]
        _msg, out = pro.split_at_joint(net, at, NAME + "__mountain")
        # the part BEFORE the joint is the built-up one: it becomes the street; the rest keeps the cliff road's name
        mountain = net.roads[out["road"]]
        _rename(net, road, OPEN_NAME)
        _rename(net, mountain, NAME)
        ppr.apply_preset(net, OPEN_NAME, OPEN_PRESET)
        notes.append("%s (%d stations)" % (OPEN_NAME, lead))
    return (", footways where built up: " + ", ".join(notes)) if notes else ""


def _chain_cum(net, road):
    cum = [0.0]
    for a, b in zip(road.points, road.points[1:]):
        cum.append(cum[-1] + math.dist(net.points[a].pos[:2], net.points[b].pos[:2]))
    return cum


def _insert_at(net, road, _cum, _sts, s):
    """A station at chain distance `s` along `road`, unless one is within 3 m."""
    from island_roadgen import insert_after
    rc = _chain_cum(net, road)
    if any(abs(c - s) < 3.0 for c in rc):
        return
    k = max(i for i in range(len(rc) - 1) if rc[i] <= s)
    a, b = net.points[road.points[k]].pos, net.points[road.points[k + 1]].pos
    u = (s - rc[k]) / max(1e-9, rc[k + 1] - rc[k])
    insert_after(net, road, road.points[k], tuple(a[q] + (b[q] - a[q]) * u for q in range(3)))


def main(argv):
    if len(argv) >= 2 and argv[0] == "derive":
        cmd_derive(argv[1])
        return
    if len(argv) >= 2 and argv[0] == "add":
        out = argv[1]
        src = argv[argv.index("--from") + 1] if "--from" in argv else out
        net = pm.load_network(src)
        print("island_coast_road: " + add(net))
        pm.save_network(net, out)
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
