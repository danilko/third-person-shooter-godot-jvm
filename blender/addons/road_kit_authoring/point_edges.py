"""point_edges.py -- the road EDGE: what stands outboard of the asphalt, and where it opens.

THE RULE (3.2). Everything outboard of the carriageway -- kerb, gutter, footway, wall, railing,
prop rows -- is placed against the BOUNDARY OF THE UNION of every ribbon, not by lateral offset
from one centreline. Measured on the previous model's island: 257 of 3736 centreline kerb samples
stood on another road's asphalt; 0 of 3441 outline vertices did. That single change is what makes
gores, merges, flyovers and junction approaches work with NO case analysis, and it is why the whole
`merge_corridor_ends` / `MERGE_WALL_*` / `RAMP_WALL_OPEN` tier of the previous model does not exist
here.

------------------------------------------------------------------------------------------------
§3.2's OPEN DECISION, SETTLED -- and settled differently from the plan

The plan left one thing to decide on real content: two ribbons that run parallel and overlapping
WITHOUT ever converging have no crossing for a boundary walk to find (60 such ends on the previous
island). The plan's provisional answer was "do the union with Blender mesh booleans, keep the walk
as a fast path, gate on disagreement".

That answer is rejected, because the question it answers is not the question that is actually
asked. Working through what the union polygon is FOR, there are exactly two consumers:

  1. **Where does a kerb stop?**  -> "is this kerb sample standing on another road's asphalt?"
     That is a POINT-IN-POLYGON test against each band, not a union. It needs no crossing, so the
     parallel-overlap case -- the one that killed the walk -- is not a special case here at all.
  2. **What footprint does the ground cut use?** -> cutting the terrain with the union of N bands
     is identical to cutting it with each band in turn (difference distributes over union). So the
     union polygon is never actually needed.

So there is no polygon clipper in this module, no boundary walk, and no boolean-vs-walk
disagreement to gate on. `pyclipper` is not in Blender's bundled Python and pure-Python Clipper
ports are too slow for a live rebuild; not needing one is strictly better than choosing one.

What that costs, stated plainly: the kerb OPENS across an overlap rather than tracing a new line
around the combined shape. At a gore that is exactly right -- the kerb should open where the ramp
joins. Where two ribbons overlap and a merged outer edge really is wanted, the artist authors the
outer road's own footway/shoulder to cover it. That is a visible authored fact rather than an
emergent one, which is the trade this whole rewrite keeps making.

------------------------------------------------------------------------------------------------
ELEVATION IS PART OF THE TEST. A flyover 12 m above a street overlaps it in XY and must keep every
metre of its parapet. So a sample is suppressed only when the other band's surface is within
`Z_TOL` of it -- the same rule the previous model's `_on_a_road` used, and for the same reason.
"""

import collections
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "lib"))

try:
    from . import point_solve as ps
except ImportError:
    import point_solve as ps                                                 # noqa: E402


#: How close in elevation two surfaces must be before one is considered to stand ON the other.
#: Generous enough to cover a road on fill over a road at grade, tight enough that a viaduct keeps
#: its parapet.
Z_TOL = 3.0

#: How close to another band a sample has to get before its kerb opens. NOT a bare "is it inside"
#: test: an EXACTLY aligned ramp (which is what `Align Ramp To Aux` produces, and what the gate
#: demands) touches the mainline band tangentially with zero overlap, and a kerb built right up to
#: that tangent is a wall across the join. A little under a kerb-plus-gutter width, so the furniture
#: opens where there is no longer room for it and nowhere else.
NEAR_PAD = 0.6

#: A kerb run shorter than this is not worth building -- a 2 m stub of wall between two overlaps
#: reads as debris.
MIN_RUN_LENGTH = 4.0

#: How far INSIDE another band an edge has to be before it stops being anybody's outer boundary.
#:
#: A tolerance for "exactly on", not a width. `NEAR_PAD` asks whether the pavement continues past
#: the line and answers it by probing outboard -- and where the ramp's own band is only half a
#: metre wider than the mainline's at the mouth, that probe steps clean OVER it and each of the
#: two parallel edges kept a wall, half a metre apart, for the length of the overlap. That was
#: reported against the sample as "one extra wall at the ramp connection".
#:
#: Both questions matter and they are not the same question: *does the pavement continue past this
#: line* (probe outboard) and *is this line buried under someone else's pavement* (this). An edge
#: sitting exactly ON another band's boundary is the shared outer boundary and keeps its wall --
#: which is 8h.2's case and why this is a tolerance and not a margin.
BURIED_TOL = 0.05

#: How many bisection steps put a run's end on the covering band's boundary. 12 halvings of a
#: 4 m sample step is a quarter of a millimetre; the cost is 24 `covered()` calls per run.
CLIP_ITERS = 12


class Band(object):
    """One paved footprint: a closed XY polygon, plus the centreline it came from so the test can
    ask "and how high is that surface here?" without a 3D containment test."""

    __slots__ = ("owner", "poly", "spine", "members", "carries_edge", "x0", "y0", "x1", "y1")

    def __init__(self, owner, poly, spine, members=(), carries_edge=False):
        self.owner = owner
        self.poly = poly
        #: The point uids this footprint belongs to, for a band that is not a whole road -- a pad,
        #: a gore.
        self.members = tuple(members)
        #: Does this footprint build the kerb and footway ONWARD itself?
        #:
        #: A PAD does: a run ends AT its mouth, on the pad boundary, and the pad's corner furniture
        #: starts at that same point -- so suppressing the run's last samples against it opens a
        #: gap between the street's footway and the corner's, at all four corners of every crossing.
        #: A GORE does NOT: the run runs ALONGSIDE it and the gore is bare paint, so the kerb must
        #: open across it exactly as it opens across another road's asphalt.
        #:
        #: Both are "a footprint this run is a member of", so membership alone cannot tell them
        #: apart -- which is why this is a flag the band's builder sets and not a rule inferred
        #: here. Getting it wrong put a 9 m barrier stub across a gore.
        self.carries_edge = bool(carries_edge)
        #: `[(x, y, z)]` -- the band's own surface height along its length.
        self.spine = spine
        xs = [p[0] for p in poly] or [0.0]
        ys = [p[1] for p in poly] or [0.0]
        self.x0, self.x1 = min(xs), max(xs)
        self.y0, self.y1 = min(ys), max(ys)

    def bbox_hit(self, x, y, pad=0.0):
        return (self.x0 - pad <= x <= self.x1 + pad) and (self.y0 - pad <= y <= self.y1 + pad)

    def surface_z(self, x, y):
        """This band's own surface height nearest `(x, y)`. Nearest-spine-sample rather than a
        barycentric interpolation: the spine is sampled every 4 m, which is finer than `Z_TOL`."""
        best, bz = None, 0.0
        for sx, sy, sz in self.spine:
            d = (sx - x) ** 2 + (sy - y) ** 2
            if best is None or d < best:
                best, bz = d, sz
        return bz

    def __repr__(self):
        return "Band(%s %d pts)" % (self.owner, len(self.poly))


def _inside(poly, x, y):
    """Even-odd point-in-polygon. Plain and unclever on purpose: it is the ONE geometric predicate
    this whole module rests on, and it is called a few hundred thousand times per world build
    behind a bbox prefilter."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xc:
                inside = not inside
        j = i
    return inside


def _signed_depth(poly, x, y):
    """Signed distance to `poly`'s boundary: POSITIVE inside, NEGATIVE outside.

    Signed rather than a bare containment test because the two cases that matter are on opposite
    sides of zero and both need to suppress: a ramp genuinely buried in the mainline (positive),
    and a ramp aligned exactly onto the mainline's aux edge (zero, or a few millimetres outside).
    A boolean cannot tell the second from "a comfortable metre away"."""
    sign = 1.0 if _inside(poly, x, y) else -1.0
    best = None
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i][0], poly[i][1]
        bx, by = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        d = math.hypot(x - (ax + dx * t), y - (ay + dy * t))
        best = d if best is None else min(best, d)
    return sign * (best or 0.0)


def band_of(solve):
    """The paved footprint of one `RoadSolve`: left edge out, right edge back.

    Taken from `RoadSolve.edges_left/right`, which are themselves built from the numbers the
    asphalt is swept from -- so the boundary and the surface are two readings of ONE set of
    values and cannot drift apart. That identity is the whole reason `solve_road` returns the
    edges at all rather than letting this module re-derive them."""
    poly = [(p[0], p[1]) for p in solve.edges_left]
    poly += [(p[0], p[1]) for p in reversed(solve.edges_right)]
    return Band(solve.road.name, poly, [tuple(s.pos) for s in solve.samples])


def band_of_junction(jsolve):
    """A pad is a footprint like any other -- a kerb running into an intersection must open."""
    return Band("JCT:" + jsolve.uids[0][:8],
                [(p[0], p[1]) for p in jsolve.boundary],
                [tuple(m.pos) for m in jsolve.mouths] + [jsolve.centre],
                members=jsolve.uids, carries_edge=True)


def band_of_gore(gsolve):
    """A gore is a footprint like any other -- and it is the one that matters most, because the
    kerb the mainline would otherwise run down its outer edge is precisely the wall across the
    ramp join that `NEAR_PAD` exists to open."""
    return Band("GORE:" + gsolve.ramp_uid[:8], list(gsolve.poly),
                [tuple(p) for p in gsolve.main_edge] + [tuple(p) for p in gsolve.ramp_edge],
                members=(gsolve.main_uid, gsolve.ramp_uid))


def collect_bands(solves, junctions=(), gores=()):
    """Every footprint in the network, ready to test against."""
    out = [band_of(s) for s in solves]
    out += [band_of_junction(j) for j in junctions]
    out += [band_of_gore(g) for g in gores]
    return out


def covered(pt, bands, skip=(), z_tol=Z_TOL, pad=NEAR_PAD, outward=None):
    """Is `pt` (x, y, z) standing on -- or pressed right up against -- another road's paved
    surface?

    `skip` names the owners that do not count: a road's own band, and the pads it runs into.
    Elevation is part of the answer -- a viaduct crossing a street overlaps it in XY and keeps
    every metre of its parapet.

    `outward` IS THE EDGE'S OWN OUTBOARD DIRECTION, and passing it changes the question from
    *"is there asphalt within `pad` of this point, in any direction?"* to *"does the pavement
    CONTINUE past this line?"* -- which is the question the furniture actually turns on, and the
    difference is not academic:

        The kerb line is a road's paved boundary, so what decides whether a wall belongs on it is
        whether a vehicle could drive across it. An UNDIRECTED slop cannot tell "buried in the
        mainline, open the kerb" from "half a metre OUTSIDE the mainline's own outer edge, which
        is the edge of the world" -- and it suppressed both. Measured on the sample: where a ramp
        leaves along the mainline's outer edge, the two edges are within `NEAR_PAD` of each other
        and each band suppressed the OTHER's parapet, leaving an 11 m hole in the wall at the top
        of a 14 m drop, on the one stretch that most needs one.

    So with `outward`, the probe is taken `pad` metres OUTBOARD and must land strictly INSIDE the
    other band. A ramp's inboard edge probes toward the mainline it is leaving (open, as before);
    its outer edge probes into empty air (keep). Both roads' walls then meet where the two edges
    part instead of both vanishing.

    TWO QUESTIONS, NOT ONE. The probe alone is still not the whole test, because it can step clean
    OVER a band narrower than `pad`: at a ramp mouth the mainline's outer edge lies half a metre
    inside the ramp's band, the probe lands three centimetres past the ramp's own outer edge, and
    each of the two parallel edges kept a wall -- one extra wall at the ramp connection, reported
    against the sample. So a directional `covered` asks both:

      * *does the pavement CONTINUE past this line?*  -- the probe, `pad` metres outboard;
      * *is this line BURIED under someone else's pavement?* -- the point itself, `BURIED_TOL`
        inside.

    Either one suppresses. An edge sitting exactly ON another band's boundary answers no to both
    and keeps its wall, which is the 8h.2 case the directional probe was introduced for."""
    x, y, z = pt[0], pt[1], pt[2]
    px, py = x, y
    if outward is not None:
        px = x + outward[0] * pad
        py = y + outward[1] * pad
        pad = 0.0
    for b in bands:
        if b.owner in skip or not b.bbox_hit(px, py, max(pad, NEAR_PAD)):
            continue
        if _signed_depth(b.poly, px, py) < -pad:
            if outward is None or _signed_depth(b.poly, x, y) < BURIED_TOL:
                continue
        if abs(b.surface_z(px, py) - z) <= z_tol:
            return b
    return None


class Run(collections.namedtuple("Run", "i0 i1 head tail")):
    """One stretch of an edge polyline where the furniture IS built.

    Still `(i0, i1)` when you index it -- every call site that only wants the sample range is
    unchanged -- plus the two CLIPPED ENDPOINTS, which are the part a sample index cannot say.
    `head`/`tail` are `None` where the run reaches the polyline's own end."""

    __slots__ = ()


def _clip_end(edge_pts, normals, live, dead, bands, skip, z_tol, iters=CLIP_ITERS):
    """The point on the segment `live -> dead` where the furniture actually stops.

    `open_runs` decides per SAMPLE, and the sample grid is 4 m coarse next to the things it is
    deciding between. Snapping a run's end to the last live sample left up to a sample of wall
    standing PAST the mouth it should have handed over at, and up to a sample of GAP before the
    gore nose it should have met -- both reported against the sample blend, and both invisible in
    the predicate, which was right at every sample it was asked about.

    So the end is BISECTED onto the covering band's own boundary. The run then stops exactly where
    this edge stops being the outer boundary of the pavement, which is what the run means."""
    a, b = edge_pts[live], edge_pts[dead]
    na = normals[live] if normals is not None and live < len(normals) else None
    nb = normals[dead] if normals is not None and dead < len(normals) else None
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        p = tuple(a[k] + (b[k] - a[k]) * mid for k in range(3))
        n = None if na is None or nb is None else tuple(
            na[k] + (nb[k] - na[k]) * mid for k in range(3))
        if covered(p, bands, skip, z_tol, outward=n) is None:
            lo = mid
        else:
            hi = mid
    return tuple(a[k] + (b[k] - a[k]) * lo for k in range(3))


def open_runs(edge_pts, bands, skip=(), z_tol=Z_TOL, min_length=MIN_RUN_LENGTH, normals=None):
    """`[Run]` -- the stretches of an edge polyline where its furniture IS built.

    THIS IS THE WHOLE MECHANISM. The kerb, the wall and the railing all ride the same runs, and
    where a ramp band overlaps the mainline band the runs simply stop and restart -- that gap IS
    the gore opening. Nothing here knows what a ramp is, and there is no `RAMP_WALL_OPEN` constant
    to tune: the geometry says where the asphalt joins, and the furniture follows.

    Each end that stops against another band is CLIPPED onto that band's boundary (`_clip_end`)
    rather than snapped back to the last live sample -- so a run ends at the mouth it hands over
    at, and starts at the nose it has to meet, instead of a sample either side of it.

    A run shorter than `min_length` is dropped rather than built as a stub."""
    if len(edge_pts) < 2:
        return []
    n = len(edge_pts)
    flags = [covered(p, bands, skip, z_tol,
                     outward=(normals[i] if normals is not None and i < len(normals) else None))
             is None for i, p in enumerate(edge_pts)]
    spans, start = [], None
    for i, live in enumerate(flags):
        if live and start is None:
            start = i
        elif not live and start is not None:
            if i - 1 > start:
                spans.append((start, i - 1))
            start = None
    if start is not None and start < n - 1:
        spans.append((start, n - 1))
    keep = []
    for i0, i1 in spans:
        head = (_clip_end(edge_pts, normals, i0, i0 - 1, bands, skip, z_tol)
                if i0 > 0 else None)
        tail = (_clip_end(edge_pts, normals, i1, i1 + 1, bands, skip, z_tol)
                if i1 < n - 1 else None)
        run = Run(i0, i1, head, tail)
        pts = sub_polyline(edge_pts, run)
        L = sum(math.dist(pts[k][:2], pts[k + 1][:2]) for k in range(len(pts) - 1))
        if L >= min_length:
            keep.append(run)
    return keep


def kerb_runs(solve, bands, z_tol=Z_TOL, min_length=MIN_RUN_LENGTH):
    """`{'left': [(i0, i1)], 'right': [...]}` for one road run. `skip` is derived here so a road
    never suppresses its own kerb against its own asphalt -- nor against a footprint that carries
    the furniture onward for it (`Band.carries_edge`: a pad does, a gore does not)."""
    mine = set(solve.uids)
    skip = tuple({solve.road.name}
                 | {b.owner for b in bands
                    if b.carries_edge and b.members and (set(b.members) & mine)})
    return {side: open_runs(edge, bands, skip, z_tol, min_length,
                            normals=side_normals(solve, side))
            for side, edge in (("left", solve.edges_left), ("right", solve.edges_right))}


def offset_line(edge_pts, normals, distance):
    """Successive OUTWARD offset from the boundary -- a footway outboard of its kerb, a wall
    outboard of that. `normals` is the per-sample outward unit direction (the road's own lateral
    frame, signed for the side), so this never has to guess which way "out" is."""
    return [(p[0] + n[0] * distance, p[1] + n[1] * distance, p[2] + n[2] * distance)
            for p, n in zip(edge_pts, normals)]


def side_normals(solve, side):
    """Per-sample OUTWARD unit direction for one side of a road. +1 is the profile's +s side."""
    sgn = 1.0 if side == "left" else -1.0
    return [(s.normal[0] * sgn, s.normal[1] * sgn, s.normal[2] * sgn) for s in solve.samples]


def sub_polyline(pts, run):
    """The run's own polyline, clipped ends included. A plain `(i0, i1)` tuple still works -- the
    self-tests and `measure_on_asphalt` pass ranges that have no clipped ends to carry."""
    out = list(pts[run[0]:run[1] + 1])
    head = run[2] if len(run) > 2 else None
    tail = run[3] if len(run) > 3 else None
    if head is not None:
        out.insert(0, head)
    if tail is not None:
        out.append(tail)
    return out


def run_values(values, run):
    """The per-sample records lined up 1:1 with `sub_polyline`'s points.

    A clipped end is a NEW point between two samples and takes the values of the live one it was
    cut back from -- the furniture is what the road declares at that station, and a fraction of a
    sample step does not change it. Emitted here rather than at each call site so the polyline and
    its attributes cannot come out different lengths."""
    out = list(values[run[0]:run[1] + 1])
    if len(run) > 2 and run[2] is not None:
        out.insert(0, values[run[0]])
    if len(run) > 3 and run[3] is not None:
        out.append(values[run[1]])
    return out


def measure_on_asphalt(samples, bands, skip=(), z_tol=Z_TOL):
    """How many of `samples` stand on another road's asphalt. The gate's number, and the one this
    module exists to drive to zero -- reported rather than asserted, because at a legitimate gore
    the answer for the CENTRELINE offset is supposed to be non-zero; it is the OUTLINE-derived
    kerb whose answer must be zero.

    `pad = -BURIED_TOL`, deliberately -- a NEGATIVE pad, which reads as "at least `BURIED_TOL`
    inside". This measures what its name says: a sample STANDING ON asphalt, not one within a
    kerb's width of some (`NEAR_PAD` is a rule about where furniture is BUILT -- see `covered`),
    and not one sitting exactly ON THE BOUNDARY either. Neither exclusion is academic: once the
    build rule became directional a kept sample may legitimately sit a few centimetres outside a
    band at the outer edge of the pavement, and `open_runs` now CLIPS each run's end onto a band's
    boundary, so the first and last point of most runs are at depth zero by construction. Counting
    either would make this number disagree with the thing it measures. The tolerance is the same
    constant the build rule uses, so the two cannot drift apart."""
    return sum(1 for p in samples
               if covered(p, bands, skip, z_tol, pad=-BURIED_TOL) is not None)


# ------------------------------------------------------------------------------- self-test

def _straight(net, pm, name, y, n=2, length=400.0, z=0.0, x0=0.0, **base):
    base.setdefault("lane_width", 3.5)
    road = net.add_road(pm.RoadData(name, pm.PointData(lanes_fwd=n, lanes_bwd=n, **base)))
    pts = [net.add_station(road, (x, y, z), has_ground_z=True)
           for x in (x0, x0 + length / 2.0, x0 + length)]
    for a, b in zip(pts, pts[1:]):
        net.link(a.uid, b.uid, pm.LINK_SEGMENT)
    return road


def self_test():
    try:
        from . import point_model as pm, point_validate as pv
    except ImportError:
        import point_model as pm                                             # noqa: E402
        import point_validate as pv                                          # noqa: E402
    ok = 0

    # ---- THE CASE THAT KILLED THE BOUNDARY WALK ------------------------------------------------
    # Two ribbons parallel and overlapping for their whole length, never converging: there is no
    # crossing for a walk to find. Main is 7.5 m half-width; the neighbour's near edge sits at
    # y = 6.5, so they overlap by a metre from end to end.
    net = pm.NetworkData()
    main = _straight(net, pm, "main", 0.0, n=2, median_width=1.0)
    near = _straight(net, pm, "near", 10.0, n=1, length=600.0, x0=-100.0)
    solves = [ps.solve_road(net, main), ps.solve_road(net, near)]
    bands = collect_bands(solves)
    assert abs(solves[0].values[0]["rka_halfw"] - 7.5) < 1e-6
    assert abs(solves[1].values[0]["rka_halfw"] - 3.5) < 1e-6
    runs = kerb_runs(solves[0], bands)
    assert runs["right"], "the far side is clear and must keep its kerb"
    assert not runs["left"], "the buried side must open for its whole length, not stub"
    ok += 1

    # ...and the CENTRELINE-offset kerb -- the thing this module replaces -- would have stood on
    # the neighbour's asphalt for every single sample. That is the 257-of-3736 defect, reproduced.
    naive = solves[0].edges_left
    assert measure_on_asphalt(naive, bands, skip=("main",)) == len(naive), "premise check"
    kept = [p for r in runs["left"] for p in sub_polyline(solves[0].edges_left, r)]
    assert measure_on_asphalt(kept, bands, skip=("main",)) == 0
    ok += 1

    # ---- ELEVATION IS PART OF THE TEST ---------------------------------------------------------
    fly = pm.NetworkData()
    lower = _straight(fly, pm, "lower", 0.0, n=2, median_width=1.0)
    upper = _straight(fly, pm, "upper", 10.0, n=1, z=12.0, length=600.0, x0=-100.0)
    fs = [ps.solve_road(fly, lower), ps.solve_road(fly, upper)]
    fb = collect_bands(fs)
    assert kerb_runs(fs[0], fb)["left"], "a viaduct overhead must not delete the street's kerb"
    assert kerb_runs(fs[1], fb)["right"], "nor the viaduct's own parapet"
    ok += 1

    # ---- A GORE OPENS WITH NO RAMP-SPECIFIC CODE -----------------------------------------------
    net2, mp, cp, rr = pv.build_testbed()
    solves2, jsolves = [], ps.solve_junctions(net2)
    for road in net2.roads.values():
        for uids in ps.road_runs(net2, road):
            s = ps.solve_road(net2, road, uids)
            if s is not None:
                solves2.append(s)
    bands2 = collect_bands(solves2, jsolves)
    ramp = next(s for s in solves2 if s.road.name == "ramp_e")
    rr_runs = kerb_runs(ramp, bands2)
    # The ramp's inboard side is buried in the mainline at the gore and clear further out, so its
    # kerb must START LATE rather than either vanish or run through the asphalt.
    inboard = rr_runs["right"]
    assert inboard and inboard[0][0] > 0, ("the gore did not open", inboard)
    kept = [p for r in inboard for p in sub_polyline(ramp.edges_right, r)]
    assert measure_on_asphalt(kept, bands2, skip=("ramp_e",)) == 0
    ok += 1

    # ---- a kerb never opens against its OWN asphalt --------------------------------------------
    lone = pm.NetworkData()
    solo = _straight(lone, pm, "solo", 0.0, n=2, median_width=1.0)
    s_solo = ps.solve_road(lone, solo)
    b_solo = collect_bands([s_solo])
    r_solo = kerb_runs(s_solo, b_solo)
    n = len(s_solo.samples)
    assert r_solo["left"] == [Run(0, n - 1, None, None)], r_solo
    assert r_solo["right"] == [Run(0, n - 1, None, None)], r_solo
    # ...and a run that reaches its polyline's own ends has nothing to clip: no head, no tail.
    assert sub_polyline(s_solo.edges_left, r_solo["left"][0]) == list(s_solo.edges_left)
    ok += 1

    # ---- successive outward offset -------------------------------------------------------------
    nrm = side_normals(s_solo, "left")
    walk = offset_line(s_solo.edges_left, nrm, 3.0)
    assert all(abs(w[1] - (e[1] + 3.0)) < 1e-6 for w, e in zip(walk, s_solo.edges_left))
    ok += 1

    # ---- a stub run is dropped rather than built ------------------------------------------------
    assert open_runs(s_solo.edges_left, b_solo, ("solo",), min_length=1e9) == []
    ok += 1

    print("point_edges.py: %d checks PASS" % ok)
    return True


if __name__ == "__main__":
    self_test()
