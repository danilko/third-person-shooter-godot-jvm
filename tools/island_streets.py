#!/usr/bin/env python3
"""island_streets.py -- the block streets and farm roads under the trunk grid (PLAN.md 3.13 step 4, 3.3).

    python3 tools/island_streets.py <record>

A REGION is a box and a road type (`point_presets`) with a set of north-south lines (x) and east-west lines (y). Each
line becomes streets between the ROADS it meets: it is clipped to the stretch between its first and last crossing
with an at-grade road inside the box, an existing road it crosses is CUT to land a junction there
(`island_roadgen.cut_road`), and two new lines crossing make a four-way junction. So every street ends on a road and
no dead end is made. A line is dropped (and said so) when any of its junctions would crowd an existing junction
(`JUNCTION_CLEAR`), when two of its junctions are closer than `MIN_SPAN`, or when it crosses water.

Regions (record frame: x east, y north):
* `city` -- inside the trunk grid south of y 560 (north of it the C1 diamond's ramps come down), one street down the
  middle of each trunk cell (block preset: 1 + 1, 2 m footways). Blocks are ~170 x 200 m: PLATEAU Tokyo's are
  60-120 m, stretched like the lanes are (the arcade world).
* `southwest` -- the residential lowland between rinkai_dori and the south-west coast (3.3's reach gap 2).
* `farm` -- the north-east farmland north of nogyo_michi (the farm preset: 1 + 1 at 3.5 m, no kerb, no footway).

Run on the record AFTER `island_trunk_grid.py` and BEFORE `island_expressway.py` (whose pier pass must see these
streets): `tools/island_layout.py` runs the whole chain.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from island_roadgen import *    # noqa: E402,F401,F403
import point_model as pm        # noqa: E402

MOUTH = 22.0
SPACING = 80.0
JUNCTION_CLEAR = 55.0     # a new junction no nearer an existing junction's centre than this
MIN_SPAN = 60.0           # consecutive junctions on a new street at least this far apart
PARALLEL_CLEAR = 35.0     # a new street no nearer than this to an existing road running ALONGSIDE it ...
PARALLEL_COS = 0.94       # ... "alongside" = within ~20 deg of parallel
PARALLEL_RUN = 40.0       # ... over more than this much of its length (a crossing's approach is not "alongside")
# A line set is either an explicit tuple of coordinates or a SPACING (a float): the spacing generates lines
# across the box, which is what closes BLOCKS (PLAN.md 3.18c). Measured on the hand-listed version: the road
# network enclosed almost nothing -- 44% of the island's 8.13 km2 of open land was ONE component of 3.60 km2,
# and only 16% sat in components under 5 ha, the size a real 街区 is. Hand-listing lines cannot close a mesh:
# every dropped line leaves a gap, and a gap joins two blocks into one.
#
# The spacing is the BLOCK size. PLATEAU Tokyo's blocks are 60-120 m; this world's lanes are stretched (4.5 m
# against the book's 3.25), so the blocks are stretched with them and the city's is 150 m.
# WHICH REGIONS GET A BLOCK GRID is the user's call (2026-09-20): "only need to do for city/downtown/resident;
# suburb/harbour/airport/mountain assume will be different". They are also the only ones it CAN be done for --
# `suburb` and `harbour` were tried and every line reported "meets no road", because those boxes have almost no
# arterials for a grid to attach to. They need arterials first (3.3's reach gaps), and they are meant to read
# differently anyway: a harbour is yards and sheds, a suburb is loose plots.
BLOCK_STEP = {"city": 150.0, "sw": 170.0, "farm": 260.0}
# The regions and their names are the final plan's (PLAN.md 3.30 L2): `island_plan.STREET_REGIONS`, one owner.
import island_plan as _PL   # noqa: E402
REGIONS = _PL.STREET_REGIONS
NAMES = _PL.STREET_NAMES
LINE_INSET = 60.0        # a generated line no nearer the box edge than this (its first crossing needs room)


def _crossings(net, a, b, skip=()):
    """[(t along a->b, road name, point)] where the segment a->b crosses an at-grade road's station polyline."""
    out = []
    for name, r in net.roads.items():
        if name in skip:
            continue
        pts = [net.points[u].pos for u in r.points]
        for p, q in zip(pts, pts[1:]):
            if max(p[2], q[2]) > 3.0:                   # elevated: a street passes under it
                continue
            rx, ry = b[0] - a[0], b[1] - a[1]
            sx, sy = q[0] - p[0], q[1] - p[1]
            den = rx * sy - ry * sx
            if abs(den) < 1e-9:
                continue
            t = ((p[0] - a[0]) * sy - (p[1] - a[1]) * sx) / den
            u = ((p[0] - a[0]) * ry - (p[1] - a[1]) * rx) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                out.append((t, name, (a[0] + rx * t, a[1] + ry * t)))
    return sorted(out)


def junction_centres(net):
    out = []
    for comp in net.junction_cliques():
        xs = [net.points[u].pos for u in comp]
        out.append((sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs)))
    return out


def _obstacles(net):
    """Points a new junction must keep JUNCTION_CLEAR from: every junction's centre, and every road END (a joint, a
    mouth, a loop's arm) -- a road cannot be cut within a mouth's length of its end."""
    pts = list(junction_centres(net))
    for r in net.roads.values():
        for u in (r.points[0], r.points[-1]):
            if net.points[u].role == pm.SEGMENT:
                pts.append(tuple(net.points[u].pos[:2]))
    return pts


class _Segs(object):
    """Every road's plan segments on a grid, for "does this street run alongside a road that is already there".
    A street 12.5 m from a trunk road and parallel to it is a second carriageway nobody drew: measured, `machi_612`
    ran 12.5 m off `naka_hondori` for 460 m and died inside that road's own junction (`open_end`)."""
    CELL = 50.0

    def __init__(self, net):
        self.cells = {}
        for r in net.roads.values():
            pts = [net.points[u].pos[:2] for u in r.points]
            for a, b in zip(pts, pts[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 1e-6:
                    continue
                d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                for i in range(int(math.floor(min(a[0], b[0]) / self.CELL)), int(math.floor(max(a[0], b[0]) / self.CELL)) + 1):
                    for j in range(int(math.floor(min(a[1], b[1]) / self.CELL)),
                                   int(math.floor(max(a[1], b[1]) / self.CELL)) + 1):
                        self.cells.setdefault((i, j), []).append((a, b, d))

    def alongside(self, p, u):
        i0, j0 = int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))
        for i in (i0 - 1, i0, i0 + 1):
            for j in (j0 - 1, j0, j0 + 1):
                for a, b, d in self.cells.get((i, j), ()):
                    if abs(d[0] * u[0] + d[1] * u[1]) < PARALLEL_COS:
                        continue
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    n = vx * vx + vy * vy
                    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / n))
                    if math.hypot(p[0] - a[0] - vx * t, p[1] - a[1] - vy * t) < PARALLEL_CLEAR:
                        return True
        return False


def _parallel_run(segs, kind, v, lo, hi):
    """Metres of the line between `lo` and `hi` (along its own axis) that run alongside an existing road."""
    u = (0.0, 1.0) if kind == "x" else (1.0, 0.0)
    run = best = 0.0
    t = lo
    while t <= hi:
        p = (v, t) if kind == "x" else (t, v)
        run = run + 5.0 if segs.alongside(p, u) else 0.0
        best = max(best, run)
        t += 5.0
    return best


def _line_ok(net, ground, obst, kind, v, box, segs=None):
    x0, y0, x1, y1 = box
    a, b = ((v, y0), (v, y1)) if kind == "x" else ((x0, v), (x1, v))
    cr = _crossings(net, a, b)
    if not cr:
        return None, "meets no road"
    # A crowding crossing is dropped, not the LINE. Dropping the line was right while the lines were hand-listed
    # and few; with a generated grid one bad crossing would discard a whole street, and one missing street is a
    # gap that merges two blocks into one (PLAN.md 3.18c). A line that keeps nothing is still dropped.
    nodes, crowded = [], 0
    for c in cr:
        p = c[2]
        if min((math.hypot(p[0] - o[0], p[1] - o[1]) for o in obst), default=1e9) < JUNCTION_CLEAR:
            crowded += 1
            continue
        nodes.append((p, c[1]))
    if not nodes:
        return None, "every one of its %d crossings crowds an existing junction" % len(cr)
    if segs is not None:
        ax = 1 if kind == "x" else 0
        along = [p[ax] for p, _r in nodes]
        run = _parallel_run(segs, kind, v, min(along), max(along))
        if run > PARALLEL_RUN:
            return None, "runs alongside an existing road for %.0f m" % run
    return nodes, None


def _wet(ground, p, q):
    for f in [k / 20.0 for k in range(1, 20)]:
        g = ground.z(p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
        if g is None or g < -0.3:
            return True
    return False


def _line_values(box, kind, spec):
    """The coordinates of one axis's lines: a tuple is taken as given, a float is a SPACING laid across the box.

    Generated, because a mesh only closes if the lines really cross: a hand-listed set leaves a gap wherever one
    line is dropped, and one gap merges two blocks. Laid symmetrically about the box's centre so a region reads
    as a grid rather than as a set of lines counted from one edge."""
    if not isinstance(spec, (int, float)):
        return tuple(spec)
    lo, hi = (box[0], box[2]) if kind == "x" else (box[1], box[3])
    lo, hi = lo + LINE_INSET, hi - LINE_INSET
    if hi <= lo:
        return ()
    mid = 0.5 * (lo + hi)
    n = int(math.floor((hi - lo) / float(spec)))
    if n <= 0:
        return (mid,)
    return tuple(mid + (k - n / 2.0) * float(spec) for k in range(n + 1))


def plan_region(net, ground, region):
    """The lines of one region that survive, each as [(point, road name or None)] from its first to last crossing. A
    line that fails is nudged up to 60 m either way before it is dropped."""
    name, box, _preset, xs, ys = region
    xs, ys = _line_values(box, "x", xs), _line_values(box, "y", ys)
    obst = _obstacles(net)
    segs = _Segs(net)
    kept, why = [], []
    for kind, vals in (("x", xs), ("y", ys)):
        for v0 in vals:
            tried = []
            for dv in (0.0, 30.0, -30.0, 60.0, -60.0):
                nodes, last = _line_ok(net, ground, obst, kind, v0 + dv, box, segs)
                if nodes:
                    kept.append([kind, v0 + dv, nodes])
                    break
                tried.append("%+.0f: %s" % (dv, last))
            else:
                why.append("%s %s=%.0f dropped (%s)" % (name, kind, v0, "; ".join(tried)))
    # crossings of two new lines: kept only where at least one of the two runs THROUGH the point (a crossing that is
    # the end of both would be a two-armed pad, which the kit refuses); lines re-clipped until nothing changes
    cross = {}
    for i, L in enumerate(kept):
        for j, M in enumerate(kept):
            if L[0] == "x" and M[0] == "y":
                cross[(i, j)] = (L[1], M[1])
    alive = set(range(len(kept)))
    active = set(cross)
    while True:
        ext = {}
        for i in alive:
            kind, v, nodes = kept[i]
            ax = 1 if kind == "x" else 0
            vals = [p[ax] for p, _r in nodes] + [cross[k][ax] for k in active if i in (k[0] if kind == "x" else k[1],)]
            ext[i] = (min(vals), max(vals)) if vals else (0.0, 0.0)
        changed = False
        for k in list(active):
            i, j = k
            if i not in alive or j not in alive:
                active.discard(k)
                changed = True
                continue
            x, y = cross[k]
            in_i, in_j = ext[i][0] - 1e-6 <= y <= ext[i][1] + 1e-6, ext[j][0] - 1e-6 <= x <= ext[j][1] + 1e-6
            thru_i, thru_j = ext[i][0] + 1e-6 < y < ext[i][1] - 1e-6, ext[j][0] + 1e-6 < x < ext[j][1] - 1e-6
            if not (in_i and in_j) or not (thru_i or thru_j):
                active.discard(k)
                changed = True
        verdict = {}
        for i in list(alive):
            kind, v, nodes = kept[i]
            n = len(nodes) + sum(1 for k in active if i == (k[0] if kind == "x" else k[1]))
            ax = 1 if kind == "x" else 0
            pts = sorted([pp[ax] for pp, _r in nodes] + [cross[k][ax] for k in active
                                                       if i == (k[0] if kind == "x" else k[1])])
            if n < 2:
                verdict[i] = "meets one road and no other street"
            elif any(b_ - a_ < MIN_SPAN for a_, b_ in zip(pts, pts[1:])):
                # prefer giving up the CROSSING with another new line: a crossing is one junction of a grid,
                # while the line is a whole street, and losing the street is what leaves a gap
                mine = [k for k in active if i == (k[0] if kind == "x" else k[1])]
                worst, wk = None, None
                for k in mine:
                    c = cross[k][ax]
                    near = min((abs(c - q) for q in pts if abs(c - q) > 1e-6), default=1e9)
                    if near < MIN_SPAN and (worst is None or near < worst):
                        worst, wk = near, k
                if wk is not None:
                    active.discard(wk)
                    changed = True
                else:
                    verdict[i] = "two of its junctions on ROADS are closer than %.0f m" % MIN_SPAN
        if not verdict and not changed:
            # water is judged only once everything else has settled: a partner dropped may shorten the line
            for i in list(alive):
                kind, v, _nodes = kept[i]
                lo, hi = ext[i]
                p = (v, lo) if kind == "x" else (lo, v)
                q = (v, hi) if kind == "x" else (hi, v)
                if _wet(ground, p, q):
                    verdict[i] = "crosses water"
                    break                       # one at a time: dropping it may clear another
        for i, reason in verdict.items():
            kind, v, _nodes = kept[i]
            why.append("%s %s=%.0f dropped: %s" % (name, kind, v, reason))
            alive.discard(i)
            changed = True
        if not changed:
            break
    out = []
    for i in sorted(alive):
        kind, v, nodes = kept[i]
        nodes = list(nodes) + [(cross[k], None) for k in active if i == (k[0] if kind == "x" else k[1])]
        ax = 1 if kind == "x" else 0
        nodes.sort(key=lambda n: n[0][ax])
        out.append((kind, v, nodes))
    return out, why


def build_region(net, ground, region):
    lines, why = plan_region(net, ground, region)
    rname, _box, preset, _xs, _ys = region
    fixed = lines
    junctions = {}
    skipped = []

    def add(c, u):
        junctions.setdefault((round(c[0], 1), round(c[1], 1)), []).append(u)
    cut, dead = set(), set()
    for kind, v, nodes in fixed:
        for p, road in nodes:
            key = (round(p[0], 1), round(p[1], 1))
            if road is not None and key not in cut:
                try:
                    ma, mb = cut_road(net, p, road.split("__")[0], MOUTH)
                except ValueError as e:
                    # No room on that road for a mouth here (its end is too near). The junction cannot be made,
                    # so the street must not be built OUT to it either: doing that leaves a dangling end, which
                    # is what `flow`'s `open_end` reported on four new streets the first time this ran.
                    skipped.append(str(e))
                    dead.add(key)
                    continue
                add(p, ma)
                add(p, mb)
                cut.add(key)
    made = 0
    for kind, v, nodes in fixed:
        # a node whose junction could not be made is no longer an end this street may run to
        nodes = [n for n in nodes if (round(n[0][0], 1), round(n[0][1], 1)) not in dead]
        if len(nodes) < 2:
            continue
        stem = NAMES[rname][0 if kind == "x" else 1]
        base = "%s_%d" % (stem, int(round(abs(v))))
        seg = 0
        for (p, _r), (q, _s) in zip(nodes, nodes[1:]):
            dx, dy = q[0] - p[0], q[1] - p[1]
            L = math.hypot(dx, dy)
            ux, uy = dx / L, dy / L
            a = (p[0] + ux * MOUTH, p[1] + uy * MOUTH)
            b = (q[0] - ux * MOUTH, q[1] - uy * MOUTH)
            k = max(1, int(round((L - 2 * MOUTH) / SPACING)))
            pts = [(a[0] + (b[0] - a[0]) * m / k, a[1] + (b[1] - a[1]) * m / k) for m in range(k + 1)]
            pts = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
            seg += 1
            r = chain_road(net, base if seg == 1 else "%s__%d" % (base, seg), pts, preset=preset)
            add(p, r.points[0])
            add(q, r.points[-1])
            made += 1
    for c, mouths in junctions.items():
        make_junction(net, mouths, signal=(preset != "farm" and len(mouths) >= 4))
    if skipped:
        why.append("%s: %d junction(s) skipped for want of room on the road they would cut" % (rname, len(skipped)))
    return made, len(junctions), why


def build(net, ground):
    report = []
    for region in REGIONS:
        made, nj, why = build_region(net, ground, region)
        report.append((region[0], made, nj, why))
    return report


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    if any(n.startswith(NAMES["city"][0] + "_") for n in net.roads):
        raise SystemExit("island_streets: %s already has the streets" % path)
    ground = Ground()
    for name, made, nj, why in build(net, ground):
        print("island_streets: %-5s %3d street(s), %3d junction(s)" % (name, made, nj))
        for w in why:
            print("    " + w)
    sample_ground(net, ground, prefix="\0")
    pm.save_network(net, path)


if __name__ == "__main__":
    main(sys.argv[1:])
