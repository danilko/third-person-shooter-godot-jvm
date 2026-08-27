"""graph_edges.py -- the road surface's OUTLINE, and the one curve every edge band rides.

THE PROBLEM THIS REPLACES. Every band outboard of the asphalt -- kerb, gutter, footway, wall,
railing, street props -- used to be placed by lateral offset from ONE chain's centreline. That is
correct only where that chain's ribbon is the outermost thing at that station. At a merge, a gore,
a parallel flyover or a junction it is not, and each of those cases had to be bought back with a
rule of its own (`merge_corridor_ends`, `RAMP_WALL_OPEN`, `MERGE_WALL_GAP`, `MERGE_JOINT_MAX`, a
joint emitter, and a refusal test for joints that would cross a carriageway). There is always
another case, because "offset from a centreline" is not what a road's edge IS.

WHAT THE EDGE ACTUALLY IS: the boundary of the union of every ribbon. Compute that once, and every
band outboard of it is a successive outward offset from that ONE curve -- which is also what makes
props work, since a lamp is placed relative to the footway, the footway relative to the kerb, and
the kerb is on the boundary. They cannot disagree because there is only one thing to agree with.
This is the `union` then `inflate` shape of a polygon-clipper pipeline, done here by walking the
curve pieces the solver already produced rather than by linking a clipper (see README).

WHY THIS IS CHEAP RATHER THAN A REWRITE. The resolved carrier points already carry both numbers
this needs, in the geometric frame, with aux-lane tapers and ramp alignment already applied:

    rka_shift +/- rka_halfw   the paved band's two edges
    rka_curb_ol / rka_curb_or the kerb lines

and those are THE SAME TWO NUMBERS -- `_profile_offsets` gives `curb_off_left = ppos` while
`paved_shift + paved_half = ppos` as well. So "clip the kerb line against other roads' asphalt" and
"union the asphalt, then take its boundary" are the same computation, and the containment test and
the curve being clipped can never drift apart.

THE STITCH IS NOT A SEPARATE STEP. Where chain A's kerb line enters chain B's band, the in/out
transition refined onto the band edge lands exactly ON B's kerb line -- because B's band edge IS
B's kerb line. So A's run ends where B's run passes, and the corner closes with no joint geometry,
no `gap / sin(theta)` estimate, no cap and no refusal. That is the whole of what
`merge_corridor_ends` was doing, arrived at by construction.
"""
import math

from mathutils import Vector

UP = Vector((0.0, 0.0, 1.0))

#: Vertical separation at which two roads stop being each other's neighbours. A flyover crosses
#: the street below it in plan but not in space, and clipping one against the other would eat the
#: boundary of both. Inherited from `graph_build._on_a_road`, where it was advisory (it vetoed a
#: single joint); here it decides every boundary, so it is reported rather than assumed.
Z_TOL = 3.0

#: Grid cell for the segment index, metres. The containment test is the only new O(n*m) step in
#: the build; bucketing by XY makes it O(n) in practice. Sized well above the widest ribbon so a
#: band segment lands in few cells, and well below the shortest chain so cells stay sparse.
CELL = 25.0

#: How far inboard of a band edge a point must be to count as "inside that road". Purely a
#: numerical guard so a chain's own neighbour at a shared junction mouth -- which sits exactly ON
#: the band edge -- is not read as buried in it.
INSIDE_EPS = 0.05

#: Bisection steps used to refine an in/out transition onto the band edge. 12 halvings take a
#: 25 m segment to under a millimetre, which is far below anything the sweep can show.
REFINE_STEPS = 12

#: A boundary run shorter than this is dropped rather than swept. A sliver of wall a few
#: centimetres long is never what anyone wants, and it is what a grazing overlap produces.
MIN_RUN = 1.5

#: How close two runs' ends must be to count as the same corner. A run cut by another road is
#: SUPPOSED to end where that road's own boundary passes, so the fence carries on -- that is the
#: whole merge case, and it needs no report. Only an end with nothing near it is a real hole.
#: Sized just above `REFINE_STEPS`' residual so a genuine crossing is never called a hole.
JOIN_TOL = 0.75


def lateral_frame(points):
    """`rka_lat` per point: `normalize(cross(+Z, tangent))`, the SAME frame `GN_GraphSpine`
    computes (`graph_nodes.make_spine_group`). Recomputed here rather than read back, because the
    outline is built before any modifier evaluates -- but it must match, or a kerb offset written
    against this frame would be swept along a different one.

    The tangent is central where a point has both neighbours, one-sided at the two ends, so a
    polyline bend gets the average of its two segments instead of jumping."""
    n = len(points)
    out = []
    for i in range(n):
        if n == 1:
            out.append(Vector((0.0, 1.0, 0.0)))
            continue
        if i == 0:
            t = points[1] - points[0]
        elif i == n - 1:
            t = points[n - 1] - points[n - 2]
        else:
            a = points[i] - points[i - 1]
            b = points[i + 1] - points[i]
            if a.length > 1e-9:
                a = a.normalized()
            if b.length > 1e-9:
                b = b.normalized()
            t = a + b
        t = Vector((t.x, t.y, 0.0))
        if t.length < 1e-9:
            out.append(out[-1] if out else Vector((0.0, 1.0, 0.0)))
            continue
        out.append(UP.cross(t.normalized()).normalized())
    return out


class BandIndex:
    """Every chain's paved band, bucketed by XY cell, answering one question: is this world point
    on some OTHER road's asphalt?

    This is `graph_build._on_a_road` with two changes. It reads the RESOLVED `rka_shift`/
    `rka_halfw` instead of re-deriving offsets from edge attributes, so an auxiliary lane that is
    half-open at this station is measured at its actual width rather than its stamped one; and it
    is indexed, because it now runs per boundary sample rather than once per candidate joint."""

    def __init__(self, chains, cell=CELL, z_tol=Z_TOL):
        self.cell = cell
        self.z_tol = z_tol
        self.buckets = {}
        for chain_id, pts in chains:
            for i in range(len(pts) - 1):
                (a, pa), (b, pb) = pts[i], pts[i + 1]
                if (b - a).length < 1e-9:
                    continue
                seg = (chain_id, a, b,
                       float(pa.get("rka_shift", 0.0)), float(pa.get("rka_halfw", 0.0)),
                       float(pb.get("rka_shift", 0.0)), float(pb.get("rka_halfw", 0.0)))
                for key in self._cells_for(a, b, max(pa.get("rka_halfw", 0.0),
                                                     pb.get("rka_halfw", 0.0))):
                    self.buckets.setdefault(key, []).append(seg)

    def _cells_for(self, a, b, half):
        pad = half + self.cell
        x0, x1 = sorted((a.x, b.x))
        y0, y1 = sorted((a.y, b.y))
        cx0, cx1 = int(math.floor((x0 - pad) / self.cell)), int(math.floor((x1 + pad) / self.cell))
        cy0, cy1 = int(math.floor((y0 - pad) / self.cell)), int(math.floor((y1 + pad) / self.cell))
        return [(cx, cy) for cx in range(cx0, cx1 + 1) for cy in range(cy0, cy1 + 1)]

    def inside(self, p, skip):
        """Is `p` on the asphalt of any chain not in `skip`? Returns the chain id, or None.

        Returning WHICH road, not just whether, is what lets a caller report a tangential overlap
        by name instead of as a count."""
        key = (int(math.floor(p.x / self.cell)), int(math.floor(p.y / self.cell)))
        for (chain_id, a, b, sa, ha, sb, hb) in self.buckets.get(key, ()):
            if chain_id in skip:
                continue
            t = Vector((b.x - a.x, b.y - a.y, 0.0))
            length = t.length
            if length < 1e-9:
                continue
            t = t / length
            d = p - a
            along = d.x * t.x + d.y * t.y
            if along < 0.0 or along > length:
                continue
            f = along / length
            if abs((a.z + (b.z - a.z) * f) - p.z) > self.z_tol:
                continue                      # crosses in plan, not in space
            shift = sa + (sb - sa) * f
            half = ha + (hb - ha) * f
            lat = -t.y * d.x + t.x * d.y      # d . cross(+Z, t)
            if shift - half + INSIDE_EPS < lat < shift + half - INSIDE_EPS:
                return chain_id
        return None


def _refine(index, skip, outside_pt, inside_pt):
    """The point on the segment `outside_pt -> inside_pt` where it crosses the other road's band
    edge. Bisection rather than an analytic intersection because the band edge is a polyline whose
    width varies along it -- solving it exactly means solving against the same interpolation the
    containment test already does, which IS this."""
    lo, hi = outside_pt.copy(), inside_pt.copy()
    for _ in range(REFINE_STEPS):
        mid = lo.lerp(hi, 0.5)
        if index.inside(mid, skip) is None:
            lo = mid
        else:
            hi = mid
    return lo


def _runs(index, chain_id, line, values):
    """Split one kerb line into its maximal OUTSIDE runs, ends refined onto the band edge.

    Returns `[(points, values, ended_on_road), ...]`. `ended_on_road` records, per end, the id of
    the road the run stopped against -- None where the run simply reached the end of its chain.
    That distinction is the whole of the tangential-overlap report: a run that ends against a road
    at a genuine crossing needs nothing more (the other road's boundary continues from that exact
    point), while one that ends against a road it never crosses is a grazing overlap with nothing
    to hand over to."""
    skip = {chain_id}
    flags = [index.inside(p, skip) is None for p in line]
    runs, i, n = [], 0, len(line)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and flags[j + 1]:
            j += 1
        pts = [line[k].copy() for k in range(i, j + 1)]
        vals = [values[k] for k in range(i, j + 1)]
        head_hit = tail_hit = None
        if i > 0:
            head_hit = index.inside(line[i - 1], skip)
            pts.insert(0, _refine(index, skip, line[i], line[i - 1]))
            vals.insert(0, values[i])
        if j + 1 < n:
            tail_hit = index.inside(line[j + 1], skip)
            pts.append(_refine(index, skip, line[j], line[j + 1]))
            vals.append(values[j])
        runs.append((pts, vals, (head_hit, tail_hit)))
        i = j + 1
    return runs


def _run_length(pts):
    return sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))


def _drop_offset_loops(pts, vals):
    """Remove the span where an offset line has folded back on itself.

    An inner bend tighter than the offset distance turns the offset curve inside out: it reverses,
    crosses itself and comes back. A polygon clipper removes that loop as part of offsetting; a
    sampled line keeps it, and it sweeps as a visible spike of kerb pointing into the road. Detect
    it as a reversal -- a segment running against the run's own local direction -- and drop the
    reversed span rather than trying to solve the self-intersection."""
    if len(pts) < 3:
        return pts, vals
    keep_p, keep_v = [pts[0]], [vals[0]]
    for i in range(1, len(pts)):
        step = pts[i] - keep_p[-1]
        if step.length < 1e-9:
            continue
        if len(keep_p) >= 2:
            prev = keep_p[-1] - keep_p[-2]
            if prev.length > 1e-9 and prev.normalized().dot(step.normalized()) < -0.5:
                continue                      # folded back: skip this sample
        keep_p.append(pts[i])
        keep_v.append(vals[i])
    return keep_p, keep_v


def _edge_values(pv, side):
    """One boundary point's per-point attributes, in the `build_corner_mesh` convention: THE
    POLYLINE IS THE KERB LINE, so the kerb sits at offset 0 and everything else rides outboard.

    `side` is which of the source chain's two edges this run came from, and it decides only one
    thing -- which way "outboard" points in the emitted run's own lateral frame. A run taken from
    the +lat edge keeps the chain's heading, so its own frame agrees and outboard is +1; the -lat
    edge's run has the road on its +lat side, so outboard is -1. There is no left and right on a
    boundary, only inboard and outboard, which is why the six `_mirror` pairs the carrier needs do
    not apply here.

    Everything the carrier still builds for itself is written as zero. That is how a band is
    switched off (`layer_has_content` asks the mesh, so a zeroed band is skipped rather than swept
    empty), and it is what keeps this mesh sweepable by the very same layer stack."""
    sign = 1.0 if side == 'L' else -1.0
    curb_h = float(pv.get("rka_curb_hl" if side == 'L' else "rka_curb_hr", 0.0))
    return {
        # The carriageway, median and deck belong to the carrier; the outline never builds them.
        "rka_halfw": 0.0, "rka_shift": 0.0,
        "rka_med_h": 0.0, "rka_med_z": 0.0, "rka_deck_h": 0.0,
        # PHASE A: kerb and railing only. The footway follows in phase B; until then it is zero
        # here and still built by the carrier, so nothing is drawn twice.
        "rka_walk_cl": 0.0, "rka_walk_hl": 0.0, "rka_walk_zl": 0.0,
        "rka_walk_cr": 0.0, "rka_walk_hr": 0.0, "rka_walk_zr": 0.0,
        "rka_curb_ol": 0.0,
        "rka_curb_hl": curb_h,
        "rka_curb_tl": curb_h * 0.5,
        "rka_curb_or": 0.0, "rka_curb_hr": 0.0, "rka_curb_tr": 0.0,
        "rka_pillar_h": 0.0, "rka_pillar_on": 0.0, "rka_pillar_param": 0.0,
        "rka_pillar_w": float(pv.get("rka_pillar_w", 1.4)),
        "rka_ground_z": float(pv.get("rka_ground_z", 0.0)),
        # Spacings must stay non-zero -- an asset row divides by them.
        "rka_sp_asset": float(pv.get("rka_sp_asset", 5.0)),
        "rka_sp_pillar": float(pv.get("rka_sp_pillar", 5.0)),
        "rka_ix_curb": int(pv.get("rka_ix_curb", -1)),
        "rka_ix_rail": int(pv.get("rka_ix_rail", -1)),
        "rka_ix_median": -1, "rka_ix_sidewalk": -1, "rka_ix_pillar": -1,
        "rka_ix_prop": -1,
        # Not consumed by any layer; carried so a gate or a report can say which road a boundary
        # point came from without re-deriving it.
        "rka_outboard": sign,
    }


def _open_ends(verts, run_of, cuts):
    """Of the run ends another road cut, which ones are actually HOLES in the fence?

    A cut end is the normal, wanted outcome at a merge: the run stops exactly where the other
    road's boundary passes, so the fence turns the corner and carries on. That is the entire
    merge case and it deserves no report at all -- reporting every cut end (the first version of
    this) buries the one thing worth saying in a hundred lines of correct behaviour.

    A hole is a cut end with no other run's point near it: the boundary stopped against a road it
    never crosses -- two ribbons grazing in parallel rather than converging -- and there is nothing
    to hand the fence over to. Those are the ones a person has to look at.

    THE MEETING POINT IS TWO CUT ENDS, not one cut end and one ordinary vertex. At a merge both
    fences stop against each other, a few centimetres apart -- so refusing to let cut ends count as
    each other's neighbour (the first version of this) reported every closed corner as a hole,
    which is the same "drown the real finding in correct behaviour" failure the whole report exists
    to avoid. Any point of ANOTHER run within `JOIN_TOL` closes the corner."""
    if not cuts:
        return []
    cell = max(JOIN_TOL * 2.0, 1e-3)
    buckets = {}
    for i, (x, y, z) in enumerate(verts):
        buckets.setdefault((int(x // cell), int(y // cell), int(z // cell)), []).append(i)
    out = []
    for idx, chain_id, side, hit in cuts:
        x, y, z = verts[idx]
        cx, cy, cz = int(x // cell), int(y // cell), int(z // cell)
        found = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in buckets.get((cx + dx, cy + dy, cz + dz), ()):
                        if run_of[j] == run_of[idx]:
                            continue                  # this run's own neighbouring vertex
                        ox, oy, oz = verts[j]
                        if (ox - x) ** 2 + (oy - y) ** 2 + (oz - z) ** 2 <= JOIN_TOL ** 2:
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if not found:
            out.append((chain_id, side, hit, (round(x, 1), round(y, 1), round(z, 1))))
    return out


def outline(chains, z_tol=Z_TOL, cell=CELL, report=None):
    """The road network's outer boundary from the RESOLVED carrier chains.

    `chains` is `[(chain_id, [(Vector co, values_dict), ...])]` exactly as `build_carrier` resolves
    them -- positions in world space, values in the geometric frame (post-`_mirror`).

    Returns `(verts, edges, per_point)` ready for `from_pydata` plus attribute writing, in the same
    shape `build_carrier` and `build_corner_mesh` already produce."""
    index = BandIndex(chains, cell=cell, z_tol=z_tol)
    verts, edges, per_point = [], [], []
    cuts, run_of, n_runs, clipped = [], [], 0, 0
    for chain_id, pts in chains:
        if len(pts) < 2:
            continue
        co = [p for p, _v in pts]
        lat = lateral_frame(co)
        for side in ('L', 'R'):
            key = "rka_curb_ol" if side == 'L' else "rka_curb_or"
            line = [co[i] + lat[i] * float(pts[i][1].get(key, 0.0)) for i in range(len(pts))]
            found = _runs(index, chain_id, line, [v for _p, v in pts])
            if len(found) != 1 or any(h is not None for h in found[0][2]):
                clipped += 1              # this kerb line was cut by another road somewhere
            for run_pts, run_vals, hits in found:
                run_pts, run_vals = _drop_offset_loops(run_pts, run_vals)
                if len(run_pts) < 2 or _run_length(run_pts) < MIN_RUN:
                    continue
                base = len(verts)
                for i, p in enumerate(run_pts):
                    verts.append((p.x, p.y, p.z))
                    run_of.append(n_runs)
                    per_point.append(_edge_values(run_vals[i], side))
                n_runs += 1
                edges.extend((base + i, base + i + 1) for i in range(len(run_pts) - 1))
                # Ends that another road cut. Whether that is a corner or a hole cannot be known
                # yet -- it depends on whether some OTHER run comes to meet it -- so record the
                # candidates and decide once every run exists.
                for which, hit in zip((base, len(verts) - 1), hits):
                    if hit is not None:
                        cuts.append((which, chain_id, side, hit))
    grazed = _open_ends(verts, run_of, cuts)
    if report is not None:
        report["grazed"] = grazed          # (chain, side, the road it stopped against)
        report["runs"] = n_runs            # boundary polylines emitted
        report["clipped"] = clipped        # kerb lines that another road cut
    return verts, edges, per_point


# --------------------------------------------------------------------------- self-test (no bpy)

def _selftest():
    """Engine-free checks of the two things that decide whether the outline is right at all: a
    point buried in another road is not on the boundary, and a road passing overhead clips
    nothing."""
    def chain(pid, xs, y, z, half, shift=0.0):
        return (pid, [(Vector((x, y, z)), {"rka_shift": shift, "rka_halfw": half,
                                           "rka_curb_ol": shift + half,
                                           "rka_curb_or": shift - half,
                                           "rka_curb_hl": 1.0, "rka_curb_hr": 1.0})
                      for x in xs])

    # A wide road and a narrow one lying inside it, same elevation.
    wide = chain(0, [0.0, 50.0, 100.0], 0.0, 0.0, 10.0)
    thin = chain(1, [20.0, 40.0], 0.0, 0.0, 2.0)
    idx = BandIndex([wide, thin])
    assert idx.inside(Vector((30.0, 0.0, 0.0)), skip={1}) == 0, "buried point not detected"
    assert idx.inside(Vector((30.0, 30.0, 0.0)), skip={1}) is None, "far point read as inside"

    verts, edges, per_point = outline([wide, thin])
    for (x, y, z) in verts:
        assert not (20.0 < x < 40.0 and abs(y) < 1.9), \
            "a boundary point was emitted inside the wide road at x=%.2f y=%.2f" % (x, y)
    assert len(verts) == len(per_point)
    assert all(0 <= a < len(verts) and 0 <= b < len(verts) for a, b in edges)

    # The same pair, but the thin one 8 m up: a flyover clips nothing.
    over = chain(1, [20.0, 40.0], 0.0, 8.0, 2.0)
    idx2 = BandIndex([wide, over])
    assert idx2.inside(Vector((30.0, 0.0, 8.0)), skip={1}) is None, "flyover clipped by the street"
    v2, _e2, _p2 = outline([wide, over])
    assert any(abs(z - 8.0) < 1e-6 for _x, _y, z in v2), "the flyover lost its own boundary"

    # `rka_shift +/- rka_halfw` and the kerb offsets are the same two numbers.
    for _pid, pts in (wide, thin):
        for _p, v in pts:
            assert abs((v["rka_shift"] + v["rka_halfw"]) - v["rka_curb_ol"]) < 1e-9
            assert abs((v["rka_shift"] - v["rka_halfw"]) - v["rka_curb_or"]) < 1e-9

    # A fold-back sample is dropped rather than swept as a spike.
    folded = [Vector((0, 0, 0)), Vector((10, 0, 0)), Vector((4, 0, 0)), Vector((20, 0, 0))]
    kept, _ = _drop_offset_loops(folded, [{}] * 4)
    assert len(kept) == 3 and all(kept[i].x < kept[i + 1].x for i in range(len(kept) - 1)), \
        "offset fold-back not removed: %s" % [p.x for p in kept]

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    _selftest()
