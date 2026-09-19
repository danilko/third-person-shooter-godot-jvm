#!/usr/bin/env python3
"""island_roadgen.py -- shared helpers for the island's road generators (`island_expressway.py`,
`island_trunk_grid.py`, PLAN.md 3.13): the natural ground, plan shapes (a filleted polyline), a road from a list of
stations, a station inserted into a chain, a ground road CUT to land a junction, and the pier pass that keeps every
elevated road's columns off the roads under it.

Record frame throughout: x east, y north (= -Godot z), z up, in IslandRoads' network frame.
"""
import collections
import json
import math
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons", "road_kit_authoring"))
import point_model as pm        # noqa: E402
import point_presets as pr      # noqa: E402
import point_record_ops as ro   # noqa: E402

PIECES = os.path.join(ROOT, "assets", "world_source", "pieces")
RECORD = os.path.join(PIECES, "IslandRoads.roads.json")

CLEAR = 11.0          # deck surface over the highest ground under it (>= 4.7 m clearance + deck + margin)
GRADE = 0.04          # the steepest an expressway deck climbs
DECK_HALF = 12.0      # an expressway's half width (2 x 4.5 + shoulders + barrier), for the ground under it
STEP = 60.0           # station spacing along a straight
ARC_STEP = 30.0       # ... and round a curve
GROUND_CLEAR = 17.0   # a pier stands no nearer than this to the centreline of a road more than PIER_DZ below the deck
PIER_DZ = 4.0
MARK_CLEAR = 112.0    # no other station this near a ramp or joint station: its span is the ramp's taper
PREFIX = "shuto_"


# ------------------------------------------------------------------------------------------ ground

class Ground(object):
    """The network's NATURAL ground (`<stem>.ground.bin`, float32, NaN = no sample), bilinear."""

    def __init__(self, stem=os.path.join(PIECES, "IslandRoads")):
        import numpy as np
        h = json.load(open(stem + ".ground.json"))
        self.g = np.fromfile(os.path.join(PIECES, h["bin"]), dtype="<f4").reshape(h["ny"], h["nx"])
        self.ox, self.oy = h["origin"]
        self.step = h["step"]

    def z(self, x, y):
        i, j = (x - self.ox) / self.step, (y - self.oy) / self.step
        i0, j0 = int(math.floor(i)), int(math.floor(j))
        ny, nx = self.g.shape
        if not (0 <= i0 < nx - 1 and 0 <= j0 < ny - 1):
            return None
        fx, fy = i - i0, j - j0
        a, b = self.g[j0, i0], self.g[j0, i0 + 1]
        c, d = self.g[j0 + 1, i0], self.g[j0 + 1, i0 + 1]
        v = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
        return None if v != v else float(v)

    def highest(self, x, y, nx_, ny_, half):
        """The highest ground across the deck at (x, y), normal (nx_, ny_); the sea counts as 0."""
        best = 0.0
        for k in range(-2, 3):
            s = half * k / 2.0
            v = self.z(x + nx_ * s, y + ny_ * s)
            if v is not None:
                best = max(best, v)
        return best


# ------------------------------------------------------------------------------------------ plan shapes

def rounded_polygon(corners, radius, closed=True):
    """A polyline through `corners` with every interior corner filleted by an arc of `radius` (shrunk to fit the
    spans), sampled every STEP on the straights and ARC_STEP on the arcs. Returns [(x, y)]."""
    n = len(corners)
    idx = range(n) if closed else range(1, n - 1)
    fil = {}
    for i in idx:
        p0, p1, p2 = corners[(i - 1) % n], corners[i], corners[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        a, b = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
        ang = math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))       # interior angle
        if ang > math.pi - 1e-3:
            continue
        rad = radius[i] if isinstance(radius, (list, tuple)) else radius
        t = rad / math.tan(ang / 2.0)
        t = min(t, 0.45 * la, 0.45 * lb)
        r = t * math.tan(ang / 2.0)
        s = (p1[0] + a[0] * t, p1[1] + a[1] * t)            # arc start (towards p0)
        e = (p1[0] + b[0] * t, p1[1] + b[1] * t)            # arc end (towards p2)
        bis = (a[0] + b[0], a[1] + b[1])
        lbis = math.hypot(*bis)
        d = r / math.sin(ang / 2.0)
        c = (p1[0] + bis[0] / lbis * d, p1[1] + bis[1] / lbis * d)
        fil[i] = (s, e, c, r)
    out = []

    def line(p, q):
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        k = max(1, int(round(L / STEP)))
        for m in range(1, k + 1):
            out.append((p[0] + (q[0] - p[0]) * m / k, p[1] + (q[1] - p[1]) * m / k))

    def arc(f):
        s, e, c, r = f
        a0 = math.atan2(s[1] - c[1], s[0] - c[0])
        a1 = math.atan2(e[1] - c[1], e[0] - c[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        k = max(2, int(math.ceil(abs(da) * r / ARC_STEP)))
        for m in range(1, k + 1):
            a = a0 + da * m / k
            out.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))

    order = list(range(n)) if closed else list(range(n))
    start = fil[0][1] if (closed and 0 in fil) else corners[0]
    out.append(start)
    cur = start
    for i in (order[1:] + [0] if closed else order[1:]):
        if i in fil:
            line(cur, fil[i][0])
            arc(fil[i])
            cur = fil[i][1]
        else:
            line(cur, corners[i])
            cur = corners[i]
    if closed:
        out.pop()                                   # the start again
    return out


def densify(pts, step=4.0):
    out = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(L // step))
        for m in range(k):
            out.append((a[0] + (b[0] - a[0]) * m / k, a[1] + (b[1] - a[1]) * m / k))
    out.append(pts[-1])
    return out


def arclen(pts, closed):
    s = [0.0]
    seq = pts + ([pts[0]] if closed else [])
    for a, b in zip(seq, seq[1:]):
        s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return s


def at_s(pts, cum, s, closed):
    seq = pts + ([pts[0]] if closed else [])
    L = cum[-1]
    if closed:
        s %= L
    s = max(0.0, min(L, s))
    for i in range(len(seq) - 1):
        if cum[i + 1] >= s:
            f = (s - cum[i]) / max(1e-9, cum[i + 1] - cum[i])
            return (seq[i][0] + (seq[i + 1][0] - seq[i][0]) * f, seq[i][1] + (seq[i + 1][1] - seq[i][1]) * f)
    return seq[-1]


def deck_profile(pts, closed, ground, lo=None, hi=None):
    """Deck heights: the highest ground across the deck plus CLEAR, then a raise-only grade cone both ways.
    `lo`/`hi` pin the first/last station (a terminal coming down to ground)."""
    n = len(pts)
    z = []
    for i in range(n):
        p = pts[i]
        q = pts[(i + 1) % n] if (closed or i + 1 < n) else pts[i - 1]
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1.0
        z.append(ground.highest(p[0], p[1], -dy / L, dx / L, DECK_HALF) + CLEAR)
    fixed = {}
    if lo is not None:
        fixed[0] = lo
    if hi is not None:
        fixed[n - 1] = hi
    for i, v in fixed.items():
        z[i] = v
    d = [math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n)]
    for _it in range(3 if closed else 1):
        for i in range(1, n + (1 if closed else 0)):
            j, k = i % n, i - 1
            if j in fixed:
                continue
            z[j] = max(z[j], z[k] - GRADE * d[k])
        for i in range(n - 2, -1 if not closed else -2, -1):
            j, k = i % n, (i + 1) % n
            if j in fixed:
                continue
            z[j] = max(z[j], z[k] - GRADE * d[j])
    return [round(v, 2) for v in z]




# ------------------------------------------------------------------------------------------ building

def chain_road(net, name, pts3, preset="expressway", one_way=False):
    """A road through `pts3`, of the preset type; `one_way` makes it one carriageway of 2 lanes (a spur half)."""
    r = net.add_road(pm.RoadData(name, pm.PointData(uid=""), ()))
    if preset:
        pr.apply_preset(net, name, preset)
    if one_way:
        r.base.lanes_bwd = 0
        r.base.median_width = 0.0
    prev = None
    for q in pts3:
        p = net.add_station(r, q)
        if prev is not None:
            net.link(prev.uid, p.uid)
        prev = p
    return r


def freeze(net, uid, direction):
    t = (direction[0], direction[1], 0.0)
    L = math.hypot(t[0], t[1])
    net.points[uid].tangent_mode, net.points[uid].tangent = pm.MANUAL, (t[0] / L, t[1] / L, 0.0)


def station_at(plan_pts, cum, closed, want, loose=()):
    """Arclengths of the stations: the plan's own vertices, plus the marks. A vertex within MARK_CLEAR of a mark in
    `want` (a ramp or joint station, whose span is a taper) is dropped; one within 15 m of a mark in `loose` (a plain
    station the caller needs, like an anchorage) is dropped too."""
    marks = sorted(want)
    base = cum[:-1] if closed else cum
    kept = [c for c in base if all(abs(c - m) > MARK_CLEAR for m in marks)
            and all(abs(c - m) > 15.0 for m in loose)]
    return sorted(set(kept + marks + list(loose)))


def ring(net, name, plan, ground, marks=(), cut_marks=()):
    """A CLOSED expressway ring through `plan`: a station at each arclength in `marks` (the JCT's ramp stations), cut
    into roads at joints at each arclength in `cut_marks` (the first is where the ring starts and closes). Returns
    {arclength mark: uid} for every mark."""
    cum = arclen(plan, True)
    L = cum[-1]
    start = cut_marks[0] if cut_marks else 0.0
    ss = station_at(plan, cum, True, list(marks) + list(cut_marks))
    ss = [(v - start) % L for v in ss]
    ss = sorted(set(round(v, 3) for v in ss))
    pts = [at_s(plan, cum, v + start, True) for v in ss]
    z = deck_profile(pts, True, ground)
    pts3 = [(p[0], p[1], zz) for p, zz in zip(pts, z)] + [(pts[0][0], pts[0][1], z[0])]
    r = chain_road(net, name, pts3)
    uids = list(r.points)
    net.link(uids[-1], uids[0])
    freeze(net, uids[0], (pts[1][0] - pts[-1][0], pts[1][1] - pts[-1][1]))
    freeze(net, uids[-1], (pts[1][0] - pts[-1][0], pts[1][1] - pts[-1][1]))
    by_s = {}
    for v, u in zip(ss, uids):
        by_s[round((v + start) % L, 3)] = u
    out = {}
    for m in list(marks) + list(cut_marks):
        out[m] = by_s[round(m % L, 3)]
    k = 2
    for m in cut_marks[1:]:
        ro.split_at_joint(net, out[m], name="%s__%d" % (name, k))
        k += 1
    return out


def insert_after(net, road, uid, pos):
    """A station between `uid` and the next station of its road. Its lane counts are the next station's, and each aux
    count the SMALLER of the two ends', so a taper that opens over the span still opens over its last part."""
    chain = road.points
    i = chain.index(uid)
    nxt = chain[i + 1]
    src, dst = net.points[uid], net.points[nxt]
    q = pm.PointData(pos=pos, **{n: getattr(src, n) for n in pm.DELTA_FIELDS})
    q.aux_fwd, q.aux_bwd = min(src.aux_fwd, dst.aux_fwd), min(src.aux_bwd, dst.aux_bwd)
    q.lane_width = src.lane_width
    if src.profile_mode == pm.OVERRIDE and src.role == pm.SEGMENT:
        for n, _k, _d in pm.POINT_FIELDS:
            if n not in ("uid", "role", "tangent_mode", "handle_in", "handle_out", "pillar_skip", "ground_z",
                         "has_ground_z", "setback_locked", "setback_solved", "aux_fwd", "aux_bwd"):
                setattr(q, n, getattr(src, n))
    net.add_point(q)
    chain.insert(i + 1, q.uid)
    net.unlink(uid, nxt)
    net.link(uid, q.uid)
    net.link(q.uid, nxt)
    return q.uid


def _tapers(p, q):
    """True when the span p -> q is (part of) a ramp's taper: an aux count changes over it, or an end owns a ramp."""
    return (p.aux_fwd != q.aux_fwd or p.aux_bwd != q.aux_bwd or bool(p.targets(pm.LINK_AUX))
            or bool(q.targets(pm.LINK_AUX)) or p.role != pm.SEGMENT or q.role != pm.SEGMENT)


def _sample_chain(net, road):
    pts = [net.points[u].pos for u in road.points]
    out = []                      # (s, x, y, z, span index)
    s = 0.0
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(L // 4.0))
        for m in range(k):
            f = m / k
            out.append((s + f * L, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, i))
        s += L
    out.append((s, pts[-1][0], pts[-1][1], pts[-1][2], len(pts) - 1))
    return out


def clear_piers(net, prefix=PREFIX):
    """RETIRED (2026-09-19): the build drops each column that would stand on another road (`point_mesh.pier_on_road`).
    This station-span pass could only switch off a whole span, and could not split a taper span, so C1 flew 120 m and a
    loop ramp 250 m over the city with no column. Kept as a name so an old caller fails loudly."""
    raise RuntimeError("island_roadgen.clear_piers is retired: point_mesh.pier_on_road decides per column")


def sample_ground(net, ground, prefix=PREFIX):
    """`ground_z` from the natural ground: re-sampled on every road named `prefix*`, filled in wherever else a station
    has none (a mouth this tool added). The pipeline's `write_roadkit_ground.gd` re-samples from Terrain3D anyway."""
    for name, r in net.roads.items():
        for u in r.points:
            p = net.points[u]
            if not name.startswith(prefix) and p.has_ground_z:
                continue
            g = ground.z(p.pos[0], p.pos[1])
            p.ground_z, p.has_ground_z = (round(g, 3), True) if g is not None else (0.0, False)


def extend(net, road_name, pts):
    r = net.roads[road_name]
    prev = r.points[-1]
    for q in pts:
        p = net.add_station(r, q)
        net.link(prev, p.uid)
        prev = p.uid
    return prev


def arc(cx, cy, r, a0, a1, z0, z1, n):
    out = []
    for k in range(1, n + 1):
        t = k / n
        a = math.radians(a0 + (a1 - a0) * t)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a), z0 + (z1 - z0) * t))
    return out


# ------------------------------------------------------------------------------------------ junctions on ground roads

def nearest_span(net, xy, prefix):
    """(road name, span index, parameter, distance) of the span of a road named `prefix*` nearest to `xy`."""
    best = None
    for name, r in net.roads.items():
        if not name.startswith(prefix):
            continue
        pts = [net.points[u].pos for u in r.points]
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((xy[0] - a[0]) * dx + (xy[1] - a[1]) * dy) / L2))
            d = math.hypot(a[0] + dx * t - xy[0], a[1] + dy * t - xy[1])
            if best is None or d < best[3]:
                best = (name, i, t, d)
    return best


def cut_road(net, xy, prefix, gap, new_name=None):
    """CUT the ground road named `prefix*` nearest `xy` to land a junction there: the road ends at a mouth `gap`
    before the point and a new road (the rest of its chain, `new_name` or `<road>__x<n>`) starts at a mouth `gap`
    after it; stations between are dropped. Returns (mouth before, mouth after) uids."""
    name, i, t, d = nearest_span(net, xy, prefix)
    if d > 30.0:
        raise ValueError("no %s road within 30 m of %s (nearest %.1f m)" % (prefix, xy, d))
    road = net.roads[name]
    chain = list(road.points)
    pts = [net.points[u].pos for u in chain]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    s0 = cum[i] + t * (cum[i + 1] - cum[i])

    def at(s):
        k = max(j for j in range(len(cum) - 1) if cum[j] <= s) if s < cum[-1] else len(cum) - 2
        f = (s - cum[k]) / max(1e-9, cum[k + 1] - cum[k])
        return tuple(pts[k][c] + (pts[k + 1][c] - pts[k][c]) * f for c in range(3)), k

    (pa, ka), (pb, kb) = at(s0 - gap), at(s0 + gap)
    if s0 - gap <= 1.0 or s0 + gap >= cum[-1] - 1.0:
        raise ValueError("%s: a junction at %s is within %.0f m of the road's end" % (name, xy, gap))
    keep = [u for j, u in enumerate(chain) if cum[j] < s0 - gap - 6.0]
    rest = [u for j, u in enumerate(chain) if cum[j] > s0 + gap + 6.0]
    doomed = [u for u in chain if u not in keep and u not in rest]
    src = net.points[chain[ka]]
    kw = {n: getattr(src, n) for n in pm.DELTA_FIELDS}
    ma = pm.PointData(pos=pa, **kw)
    mb = pm.PointData(pos=pb, **kw)
    ma.lane_width = mb.lane_width = src.lane_width
    for u in doomed:
        net.remove_point(u)
    net.unlink(keep[-1], rest[0])
    kwr = {n: getattr(road, n) for n, _k, _d in pm.ROAD_FIELDS if n != "name"}
    k = 1
    while (new_name or "%s__x%d" % (name, k)) in net.roads:
        k += 1
    dst = net.add_road(pm.RoadData(new_name or "%s__x%d" % (name, k), road.base.copy(), (), **kwr))
    road.points[:] = keep
    net.add_point(ma, road)
    net.link(keep[-1], ma.uid)
    net.add_point(mb, dst)
    for u in rest:
        dst.points.append(u)
    net.link(mb.uid, rest[0])
    return ma.uid, mb.uid


def make_junction(net, mouths, signal=True):
    """A pad over `mouths`: a clique of JUNCTION links, each typed INTERSECTION."""
    for i in range(len(mouths)):
        for j in range(i + 1, len(mouths)):
            net.link(mouths[i], mouths[j], pm.LINK_JUNCTION)
    for u in mouths:
        net.points[u].role = pm.INTERSECTION
        net.points[u].traffic_light = bool(signal)
