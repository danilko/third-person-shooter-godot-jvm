"""graph_solve.py -- run `lib/road_graph_solve.py` against a real graph mesh and write the answer
back as attributes plus two generated objects.

THE SEAM. `road_graph_solve` is pure maths and knows nothing about Blender; `lane_profile` is pure
maths and owns the cross-section; this module is the only place the two meet bpy. That split is
what keeps the geometry decisions testable with `python3 lib/road_graph_solve.py`, and it is why
neither of them may ever grow a `import bpy`.

WHAT IT PRODUCES, and why it is three things rather than one:

  * ATTRIBUTES back onto the graph mesh -- `trim_start` / `trim_end` per edge, `solved_radius` /
    `solved_kind` / `valency` per vertex. The node tree reads these and never re-derives them.
  * `<graph>_Nodes`, a MESH of the intersection/bend/gore patches (n-gon per node). Its own
    modifier stack gives it material and thickness; the solver only supplies the boundary.
  * `<graph>_Corners`, POLYLINES along each kerb corner arc. Swept by the same curb/sidewalk
    layers a straight edge uses, so a corner footway is built by the same code as a straight one
    -- the corner arc and the sidewalk's outer arc are concentric, which is what makes that work.

REGENERATION IS AN IN-PLACE MESH SWAP, NOT A DELETE-AND-RECREATE. Both generated objects carry
Geometry Nodes modifiers put there by `graph_build`; freeing the object would take those with it
and the stack would have to be rebuilt on every solve. So the object persists and only its
`data` is replaced -- the same reason `road_stack.build_stack` rebuilds modifiers but never the
carrier.

WIDTHS COME FROM `lane_profile`, ALWAYS. `edge_widths` is the single conversion from stamped
scalars to the (left, right, paved_left, paved_right) the solver needs, and it goes through
`profile_from_scalars` + `extents`/`paved_extents` rather than multiplying lane counts locally.
`extents` returns MAGNITUDES (neg, pos), where `pos` is the `+s` / forward / left side -- verified
against `road_stack.spine_attributes_for`, which consumes the same pair.
"""
import math
import bmesh
import bpy

from . import graph_attrs as ga

_lp = None
_rgs = None


def lp():
    global _lp
    if _lp is None:
        import lane_profile as _mod
        _lp = _mod
    return _lp


def rgs():
    global _rgs
    if _rgs is None:
        import road_graph_solve as _mod
        _rgs = _mod
    return _rgs


#: How far off straight two approaches may be and still count as a pass-through rather than a
#: corner. Mirrors `road_graph_solve.solve`'s `straight_tol_deg` -- the same threshold decides
#: there that a pair has no corner to fillet, and the two must agree or a vertex could be a chain
#: break here and a "needs a taper" defect there.
STRAIGHT_TOL_DEG = 6.0

#: Re-exported from `graph_attrs`, which owns it -- every module here already imports that one.
GENERATED_TAG = ga.GENERATED_TAG
SUFFIX_NODES = "_Nodes"
SUFFIX_CORNERS = "_Corners"


def edge_widths(attrs):
    """(left, right, paved_left, paved_right) outer/carriageway half-widths for one edge.

    Aux lanes widen their own side: they are real pavement the junction has to clear, and a GORE
    is exactly the node where they stop being part of the through road."""
    lanes_l = int(attrs.get("lanes_fwd", 2)) + int(attrs.get("aux_lanes_left", 0))
    lanes_r = int(attrs.get("lanes_bwd", 2)) + int(attrs.get("aux_lanes_right", 0))
    prof = lp().profile_from_scalars(
        lanes_l, lanes_r, float(attrs.get("lane_width", 3.5)),
        float(attrs.get("median_width", 0.0)),
        float(attrs.get("sidewalk_left_width", 0.0)),
        float(attrs.get("sidewalk_right_width", 0.0)))
    neg, pos = lp().extents(prof)
    pneg, ppos = lp().paved_extents(prof)
    return pos, neg, ppos, pneg


def is_oneway(attrs):
    """DERIVED, never stored. A ramp is one-way because it has no backward lanes -- that is
    already the geometry, so a separate `oneway` flag could only ever disagree with it. Matches
    `lane_profile.is_one_way`, which reads the same profile."""
    return int(attrs.get("lanes_bwd", 0)) + int(attrs.get("aux_lanes_right", 0)) == 0


def derived_offsets(attrs, traffic_side='LEFT', aux_scale=1.0):
    """Every lateral number the node tree consumes, computed HERE from `lane_profile` so no node
    ever multiplies a lane count.

    This is also the single place the `traffic_side` flip is applied: the stack measures along
    `rka_lat` (a purely geometric side), while `lane_profile` measures in the driving frame, and
    `road_stack.write_layer_offset`'s docstring records why applying that flip twice is invisible
    on symmetric content and wrong on everything else.

    `aux_scale` (0..1) OPENS THE AUXILIARY LANE GRADUALLY, and is PER SIDE: pass one number for
    both groups, or `(left, right)` to open the two independently. Independence is not a nicety --
    a carriageway pair between an entry gore and an exit gore carries an auxiliary lane on EACH
    side, each serving its own ramp at its own end, and one shared scale necessarily opens one of
    them at the wrong end (measured on the island: chains 29 and 33, both sides full at both ends
    and closed in the middle, so the exit lane a car was meant to take shut in front of it).

    A lane cannot be a fraction of a lane in `lane_profile` -- slots and markings are discrete,
    and inventing a 0.4-lane slot would put a lane line in the middle of nowhere. So the whole-lane
    profiles are built and their offsets interpolated (`offsets_for_counts`); `aux_scale = 1` is
    bit-identical to the untapered result, so nothing that does not taper can change."""
    aux_l = int(attrs.get("aux_lanes_left", 0))
    aux_r = int(attrs.get("aux_lanes_right", 0))
    try:
        sl, sr = aux_scale
    except TypeError:
        sl = sr = aux_scale
    sl = max(0.0, min(1.0, float(sl)))
    sr = max(0.0, min(1.0, float(sr)))
    return offsets_for_counts(attrs, traffic_side,
                              int(attrs.get("lanes_fwd", 2)) + aux_l * sl,
                              int(attrs.get("lanes_bwd", 2)) + aux_r * sr)


def offsets_for_counts(attrs, traffic_side='LEFT', lanes_fwd=None, lanes_bwd=None):
    """`derived_offsets` for EXPLICIT, possibly FRACTIONAL lane counts -- the one primitive every
    width change in the pipeline goes through.

    An opening auxiliary lane and a carriageway stepping 2 -> 3 -> 4 lanes are the same operation
    seen twice: a lane count that varies along the chain. Expressing both as "what are the counts
    at THIS point" is what lets one taper mechanism serve both, and stops the two from needing
    (and then disagreeing about) separate width formulas.

    FRACTIONAL COUNTS ARE EXACT, not an approximation: every number `_profile_offsets` returns is
    affine in the two lane counts (each lane adds exactly `lane_width` to its own side), so
    evaluating the whole-lane corners and adding the two deltas reproduces what a fractional-lane
    profile would give. The one deliberate exception is the median, which `profile_from_scalars`
    inserts only while BOTH directions carry lanes -- so a group fading out between 1 and 0 lanes
    fades the median with it, which is what a carriageway merging into a one-way stub should do."""
    sign = 1.0 if traffic_side == 'LEFT' else -1.0
    nf = float(attrs.get("lanes_fwd", 2) if lanes_fwd is None else lanes_fwd)
    nb = float(attrs.get("lanes_bwd", 2) if lanes_bwd is None else lanes_bwd)
    nf, nb = max(nf, 0.0), max(nb, 0.0)
    f0, b0 = int(math.floor(nf + 1e-9)), int(math.floor(nb + 1e-9))
    tf, tb = nf - f0, nb - b0
    base = _profile_offsets(attrs, sign, f0, b0)
    if tf <= 1e-9 and tb <= 1e-9:
        return base
    out = dict(base)
    if tf > 1e-9:
        step = _profile_offsets(attrs, sign, f0 + 1, b0)
        for k in out:
            out[k] += (step[k] - base[k]) * tf
    if tb > 1e-9:
        step = _profile_offsets(attrs, sign, f0, b0 + 1)
        for k in out:
            out[k] += (step[k] - base[k]) * tb
    return out


def _offsets_for(attrs, sign, aux_l, aux_r):
    """Back-compat shim: offsets with `aux_l`/`aux_r` whole auxiliary lanes added."""
    return _profile_offsets(attrs, sign,
                            int(attrs.get("lanes_fwd", 2)) + aux_l,
                            int(attrs.get("lanes_bwd", 2)) + aux_r)


def _profile_offsets(attrs, sign, lanes_l, lanes_r):
    prof = lp().profile_from_scalars(
        int(lanes_l), int(lanes_r), float(attrs.get("lane_width", 3.5)),
        float(attrs.get("median_width", 0.0)),
        float(attrs.get("sidewalk_left_width", 0.0)),
        float(attrs.get("sidewalk_right_width", 0.0)))
    neg, pos = lp().extents(prof)
    pneg, ppos = lp().paved_extents(prof)
    return {
        "paved_half": (pneg + ppos) / 2.0,
        "paved_shift": sign * (ppos - pneg) / 2.0,
        "curb_off_left": sign * ppos,
        "curb_off_right": -sign * pneg,
        "walk_w_left": max(pos - ppos, 0.0),
        "walk_w_right": max(neg - pneg, 0.0),
        "median_half": float(attrs.get("median_width", 0.0)) / 2.0,
    }


def _outward_chains(bm):
    """Per `(end vertex, end edge)` -> that chain's polyline running AWAY from the vertex.

    Shared by `_station_fn` and `_nose_fn`, which both need "what does the road actually do once
    it leaves this node?" and would otherwise each rebuild it -- and could then disagree about it.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    outward = {}
    for chain in chains(bm):
        pts = []
        for eidx, fwd in chain:
            e = bm.edges[eidx]
            v0, v1 = (e.verts[0], e.verts[1]) if fwd else (e.verts[1], e.verts[0])
            if (v1.co - v0.co).length < 1e-9:
                continue
            if not pts:
                pts.append(v0.co.copy())
            pts.append(v1.co.copy())
        if len(pts) < 2:
            continue
        e0, f0 = chain[0]
        e1, f1 = chain[-1]
        first = bm.edges[e0].verts[0 if f0 else 1].index
        last = bm.edges[e1].verts[1 if f1 else 0].index
        outward[(first, e0)] = pts
        outward[(last, e1)] = list(reversed(pts))
    return outward


def _station_fn(bm, aligns=None):
    """A `road_graph_solve.solve(station_fn=...)` callback giving each approach the point and
    heading where its ribbon REALLY ends.

    The solver measures a setback as a distance along the chain but can only see one edge, so on
    its own it has to assume that distance runs straight -- and a chain bends through its shape
    points. This walks the SAME chains `graph_build.build_carrier` builds from, so the junction
    pad's mouth lands exactly on the ribbon's cut end at exactly its heading. Straight approaches
    are unaffected (the two agree); sweeping ones were out by tens of metres."""
    outward = _outward_chains(bm)
    chain_of = ({eidx: ci for ci, ch in enumerate(chains(bm)) for eidx, _f in ch}
                if aligns else {})

    def _shift(node, appr, p, dist):
        """The alignment displacement at `dist` along an aligned ramp -- the SAME one
        `graph_build.align_ramp_ends` applies to the ribbon.

        THE SOLVER HAS TO SEE IT. The alignment moves a ramp's last stretch sideways onto the
        auxiliary lane, but the pad that closes the gap between ramp and road is built from the
        approach's MOUTH -- and an unshifted mouth is the ramp's old position, up to a full lane
        away. Measured in the testbed: the mouth reported (-4.41, 0.88) while the ribbon it is
        supposed to meet was at (-4.41, 7.98), so the pad was laid seven metres from the thing it
        was closing and the merge stayed visibly open."""
        if not aligns:
            return p
        al = aligns.get((node.index, chain_of.get(appr.edge.index)))
        if al is None:
            return p
        target, axis, sign = al
        from . import graph_build as gb
        blend = gb.ALIGN_BLEND_LENGTH
        f = gb._smoothstep(1.0 - dist / blend) if dist < blend else 0.0
        if f <= 0.0:
            return p
        return (p[0] - axis[1] * target * sign * f, p[1] + axis[0] * target * sign * f, p[2])

    def _at(pts, dist):
        """(point, unit direction) at `dist` along a polyline -- raw, before any alignment."""
        acc = 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            seg = (b - a).length
            if seg < 1e-12:
                continue
            if acc + seg >= dist:
                t = (dist - acc) / seg
                p = a.lerp(b, t)
                d = (b - a)
                return (p.x, p.y, p.z), (d.x / seg, d.y / seg)
            acc += seg
        d = pts[-1] - pts[-2]
        n = d.length or 1.0
        return (pts[-1].x, pts[-1].y, pts[-1].z), (d.x / n, d.y / n)

    def station(node, appr):
        pts = outward.get((node.index, appr.edge.index))
        if pts is None:
            return None
        p, d = _at(pts, appr.setback)
        p = _shift(node, appr, p, appr.setback)
        # THE HEADING HAS TO BE SHIFTED TOO, not just the point. The junction pad's boundary at
        # this arm is a cross-section PERPENDICULAR to this direction, and the ribbon's own end cap
        # is perpendicular to the direction of the DISPLACED polyline -- which curves as the
        # alignment eases the ramp onto the lane. Displacing only the position leaves the two
        # rotated against each other, and the sliver between them is a hole in the pavement
        # (measured in the testbed: a triangle 4 m long between the ramp's end and the pad).
        # Sampling the displaced polyline twice gives the heading it actually has there.
        q, _dq = _at(pts, appr.setback + 2.0)
        q = _shift(node, appr, q, appr.setback + 2.0)
        dx, dy = q[0] - p[0], q[1] - p[1]
        n = math.hypot(dx, dy)
        if n > 1e-9:
            d = (dx / n, dy / n)
        return p, d

    return station


def _nose_fn(bm, aligned=()):
    """A `road_graph_solve.solve(nose_fn=...)` callback: how far along a ramp its NOSE is.

    THE RAMP HAS TO START WHERE THE AUXILIARY LANE IS, which is the outer edge of the carriageway,
    not the road's centreline. Both live in the same place -- `_outward_chains` gives the ramp's
    real polyline, and `lane_profile` (via `derived_offsets`) gives the lateral position of the
    lane the ramp continues -- so the answer is a measurement rather than a formula: walk the ramp
    and stop at the first point whose PERPENDICULAR distance from the mainline has reached the
    auxiliary lane's own offset.

    Walking matters because these ramps curve. Solving it in closed form off the departure tangent
    (`target / sin(theta)`) and then travelling that far along a curve overshot by 60-150 m -- the
    ramp then started further outside the road than it had been inside it. Same failure, and same
    fix, as `_station_fn`."""
    outward = _outward_chains(bm)
    bm.edges.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm, fill_defaults=False)

    def nose(node, trunk, main, ramp):
        # NO RAMP IS SET BACK AT A GORE. A served ramp does not need it -- its last stretch is
        # displaced onto the auxiliary lane (`ramp_alignments`) and swept in full. An unserved one
        # must not have it: there is no lane for it to stop short of, so the setback buys nothing
        # and costs a hole tens of metres long between the ramp and the road, which is the "the
        # preview connects but the road underneath is not generated" report. What is left is
        # overlap where a ramp crosses the mainline it could not merge into -- and overlapping
        # asphalt reads as asphalt, while an unpaved gap reads as a hole in the world.
        return 0.0
        pts = outward.get((node.index, ramp.edge.index))
        if pts is None or len(pts) < 2:
            return None
        # WHERE THE LANE THE RAMP CONTINUES ACTUALLY SITS -- the auxiliary lane's CENTRE, half a
        # lane inside the carriageway edge. The trunk's own profile owns that number; deriving it
        # here from lane counts would be the duplicated-formula mistake this pipeline keeps paying
        # for.
        #
        # THIS IS DELIBERATELY *NOT* `road_graph_solve._gore_nose`'s "where the two pavements
        # separate" (`trunk half + ramp half`), which is what its closed-form fallback uses. A ramp
        # CONTINUES the auxiliary lane: the first stretch of it legitimately lies on the
        # carriageway, and the two ribbons overlap there exactly as the exit lane and the ramp
        # overlap on a real motorway. Moved out to the separation point instead -- tried, measured
        # -- every ramp starts clear of the road it comes off and the connection opens into a hole:
        # the island's gaps grew to 23 m and the movement audit went from 0 problems to 2. Keep the
        # overlap; if it ever z-fights, bias the ramp, do not move its nose.
        at = ga.read_edge(bm, bm.edges[trunk.edge.index], el)
        offs = derived_offsets(at)
        edge_off = max(abs(offs["curb_off_left"]), abs(offs["curb_off_right"]))
        target = max(edge_off - float(at.get("lane_width", 3.5)) * 0.5, 0.0)
        # The mainline axis through the node, as a unit direction.
        ref = main.angle if main is not None else trunk.angle + math.pi
        ux, uy = math.cos(ref), math.sin(ref)
        origin = pts[0]

        def _perp(p):
            return abs(ux * (p.y - origin.y) - uy * (p.x - origin.x))

        acc, best_d, best_off = 0.0, 0.0, -1.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            seg = (b - a).length
            if seg < 1e-12:
                continue
            pa, pb = _perp(a), _perp(b)
            if pb >= target:
                # INTERPOLATE WITHIN THE SEGMENT. Stopping at the first vertex PAST the target
                # overshoots by up to a whole sample -- 8-14 m on these ramps, which is two lane
                # widths and puts the nose back outside the road instead of on its edge.
                t = 1.0 if pb - pa < 1e-9 else max(0.0, min(1.0, (target - pa) / (pb - pa)))
                return acc + seg * t
            if pb > best_off:
                best_off, best_d = pb, acc + seg
            acc += seg
        # NEVER CLEARS -- a ramp that runs alongside its mainline for its whole length (a long
        # parallel merge, or a layout that needs fixing). Falling through to the caller's closed
        # form is the WRONG answer here, and was measured as such: that form solves
        # `target / sin(theta)` off the departure tangent, and a ramp that never separates has a
        # tiny theta, so it asks for 36-200 m of setback on a ramp that may be 30 m long. The
        # solver then clamps the trim, reports the edge as too short, and what is left of the ramp
        # is a scrap -- four of the island's fifteen gores, and the reason those exits read as
        # "the ramp is not connected to anything".
        #
        # The ramp's own shape is the better answer even when it disappoints: put the nose where
        # the ramp gets as far from the mainline as it ever does, and never eat more than half of
        # it, so there is always a ramp left to drive on and to join up to.
        return min(best_d, acc * NOSE_MAX_CHAIN_FRACTION)

    return nose


#: How far off the stream it joins a ONE-WAY arm may point and still be a MERGE (which grows the
#: road an auxiliary lane and needs no junction pad) rather than a TURN (which gets a stop line
#: and a pad). One number, read by the geometry (`road_graph_solve.solve`'s merge branch) and by
#: the lane logic (`ramp_candidates`), because a junction cannot be a merge for one and a corner
#: for the other. 70 deg is measured, not guessed: the island's motorway gores come in at 0-10
#: deg and its surface touchdowns at 63-68, while a genuine side road is square to the arterial.
MERGE_ANGLE_DEG = 70.0

#: Most of a ramp that a nose setback may consume when the ramp never clears the carriageway.
#: Half leaves a real road behind; the alternative (the caller's closed form) can ask for more
#: than the ramp's whole length.
NOSE_MAX_CHAIN_FRACTION = 0.5

#: How far along a ramp its side is measured. Long enough to outrun the departure tangent (a gore
#: leaves within a few degrees of the mainline, so the first edge says almost nothing about which
#: side the ramp ends up on) and short enough to stay within the interchange.
RAMP_SIDE_WINDOW = 80.0


def _ramp_side(outward, node, ramp, head):
    """Signed side of the ramp relative to the host stream: > 0 kerb (left), < 0 median (right).

    Measured over `RAMP_SIDE_WINDOW` of the ramp's REAL polyline and reported as the largest
    departure from the mainline axis in that window, so a ramp that leaves fractionally one way
    and then swings the other is classified by where it actually goes. `head` is the host stream's
    direction of travel, which is what makes left mean kerb under keep-left."""
    pts = outward.get((node.index, ramp.edge.index))
    if not pts or len(pts) < 2:
        return head[0] * ramp.dir[1] - head[1] * ramp.dir[0]
    origin, run, best = pts[0], 0.0, 0.0
    for i in range(1, len(pts)):
        run += (pts[i] - pts[i - 1]).length
        dx, dy = pts[i].x - origin.x, pts[i].y - origin.y
        cross = head[0] * dy - head[1] * dx
        if abs(cross) > abs(best):
            best = cross
        if run >= RAMP_SIDE_WINDOW:
            break
    return best


def ramp_candidates(bm, result, gore_angle_deg=35.0, merge_angle_deg=None, force_edges=(),
                    only_edges=None):
    """EVERY arm that might be a ramp merging into a wider road, with the verdict on each.

    Returns a list of records, one per candidate arm:

        {node, ramp (edge index), host (edge index), chain, fwd_group, align_deg, offside_m,
         verdict}

    `verdict` is None when the arm IS served -- an auxiliary lane belongs on `chain`'s `fwd_group`
    -- and otherwise a short sentence saying why not. THE REJECTIONS ARE THE POINT. "Nothing
    happened when I pressed the button" is the single least debuggable thing an authoring tool can
    do, and every reason here is invisible in the viewport: an arm two degrees past the merge
    limit looks exactly like one two degrees inside it. The panel prints this for the active edge,
    `rka.graph_ramp_aux` overrides it for the edges you select (`force_edges`), and
    `ramp_services` below is the same list with the rejects dropped.

    `fwd_group` is True when the serving group is the chain's FORWARD one -- the frame every edge's
    walk flag is expressed in, so a chain that walks an edge backwards flips it per edge.

    THE ONE OWNER OF "WHICH SIDE DOES THIS RAMP USE". `auto_aux_lanes` stamps the lane from this,
    `graph_build` anchors that lane's taper from it, and the two therefore cannot disagree about
    which END of a chain the lane must be full width at. They previously each answered it their
    own way -- the stamper per ramp, the builder as "this end is a gore and the edge carries SOME
    aux" -- and on a carriageway between two ramps the builder opened both sides at both ends and
    shut them in the middle, which closes the exit lane in front of the car meant to take it.

    THE CONVENTION, in one place, obeyed by this module, `graph_export` and the island generator:

      * OUT (exit)  -- traffic LEAVES the mainline onto the ramp.
      * IN  (entry) -- traffic JOINS the mainline from the ramp.
      * The SERVING CARRIAGEWAY is the one whose traffic uses the ramp: for OUT it is the
        carriageway ARRIVING at the gore, for IN the one DEPARTING it. Never the other one -- the
        two are separated by the median and nothing may cross it at a gore.
      * The auxiliary lane is added to that serving carriageway at its OUTERMOST (kerb) lane, and
        the ramp attaches to the outer edge of that lane. Deceleration for OUT, acceleration for
        IN; both taper to nothing away from the gore (`graph_build.aux_scale_keys`).

    So a ramp is always entered and left from the outermost lane, which is what a driver expects
    and what keeps the ramp aligned with the lane that opens for it. There is deliberately NO
    median-end option: it was derived rather than authored, it kept deriving the wrong side, and
    it forced a second anchoring case through every rule downstream. A ramp measured on the median
    side of the stream it serves is reported as a layout error instead -- one convention, one code
    path, and the layout is what gets fixed."""
    R = rgs()
    merge_angle_deg = MERGE_ANGLE_DEG if merge_angle_deg is None else merge_angle_deg
    el = ga.ensure_edge_layers(bm)
    vl = ga.ensure_vert_layers(bm, fill_defaults=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    all_chains = chains(bm)
    chain_of = {eidx: ci for ci, ch in enumerate(all_chains) for eidx, _f in ch}
    outward = _outward_chains(bm)
    tol = math.radians(gore_angle_deg)

    out = []

    def _lanes(appr):
        at = ga.read_edge(bm, bm.edges[appr.edge.index], el)
        return int(at.get("lanes_fwd", 0)) + int(at.get("lanes_bwd", 0))

    merge_tol = math.cos(math.radians(merge_angle_deg))
    for n in result.nodes:
        if len(n.approaches) < 3:
            continue
        # THE THROUGH ROAD, at a gore by tangency and anywhere else by width. A RAMP TOUCHING DOWN
        # ON A STREET IS NOT ALWAYS A GORE: a slip road meeting an arterial at 45 degrees solves
        # as an INTERSECTION (and `_gore_trunk` cannot name a trunk there even when the vertex is
        # stamped GORE by hand, because its test is that every other arm runs back within a few
        # degrees of opposite). Restricting this to solver-detected gores meant no acceleration
        # lane was ever added at such a touchdown, so the ramp merged straight into the street's
        # existing kerb lane -- "the ramp just takes over lane 1" -- and the panel offered no way
        # to fix it: a hand-stamped aux lane on the wrong group left the ramp with no successor at
        # all, and on the right group nothing told the author which group that was.
        trunk = R._gore_trunk(n, tol) if n.kind == R.KIND_GORE else None
        main = R._gore_mainline(n.approaches, trunk) if trunk is not None else None
        if trunk is None:
            widest = sorted(n.approaches, key=lambda a: (-_lanes(a), a.edge.index))[:2]
            trunk, main = widest[0], (widest[1] if len(widest) > 1 else None)
        # THE SAME TRUNK RULE THE EXPORTER USES (`graph_export.collect`): the mainline is the wider
        # road. `_gore_trunk`/`_gore_mainline` decide by tangency, and where the ramp is the
        # straightest arm at the node they hand back the RAMP as a trunk -- so the aux lane gets
        # stamped on the ramp instead of on the carriageway that feeds it. The stamper and the
        # exporter have to agree on which arm is the mainline, or the exporter goes looking for an
        # auxiliary lane on an arm nothing ever widened and the exit ends up fed from a through
        # lane (island gore 331). Only ever a correction: if tangency already picked the widest
        # pair, nothing changes.
        picked = [a for a in (trunk, main) if a is not None]
        rest = [a for a in n.approaches if a not in picked]
        if rest and picked and min(_lanes(a) for a in picked) < max(_lanes(a) for a in rest):
            widest = sorted(n.approaches, key=lambda a: (-_lanes(a), a.edge.index))[:2]
            trunk, main = widest[0], (widest[1] if len(widest) > 1 else None)
        for ramp in n.approaches:
            if ramp is trunk or ramp is main:
                continue
            if only_edges is not None and ramp.edge.index not in only_edges:
                continue
            forced = ramp.edge.index in force_edges
            rec = {"node": n.index, "ramp": ramp.edge.index, "host": None, "chain": None,
                   "fwd_group": None, "align_deg": None, "offside_m": 0.0, "host_aux": 0,
                   "verdict": None}
            # A RAMP IS A ONE-WAY ARM. An auxiliary lane is an acceleration or deceleration lane
            # for traffic that joins or leaves without stopping, which is what a one-way slip road
            # does; a two-way side street meeting an arterial is a junction with a stop line, and
            # widening the arterial for it would be a slip lane nobody asked for.
            if not is_oneway(ga.read_edge(bm, bm.edges[ramp.edge.index], el)):
                rec["verdict"] = ("not a one-way road -- a two-way arm is a junction with a stop "
                                  "line, not a merge")
                out.append(rec)
                continue
            # WHICH TRUNK ARM GETS THE LANE IS A QUESTION ABOUT TRAFFIC, NOT ABOUT TOPOLOGY.
            # Picking it from `at_start` (does the ramp edge point away from the node?) asks about
            # the direction the AUTHOR happened to draw the ramp, which has nothing to do with the
            # direction cars travel on it -- on the island that put every acceleration lane on the
            # arm upstream of the merge, so the mainline went 3 lanes -> ramp joins -> 2 lanes, and
            # the ramp fed the through carriageway's kerb lane instead of an aux lane that was
            # never there. Both directions are settled tangentially instead: the ramp's traffic is
            # continuous with whichever arm is most nearly anti-parallel to it, and that arm is the
            # one the aux lane belongs on -- upstream of an exit (deceleration) and downstream of
            # an entry (acceleration), which is the same expression because `dir` always points
            # away from the node.
            arms = [a for a in (trunk, main) if a is not None]
            if not arms:
                rec["verdict"] = "no through road at this junction to widen"
                out.append(rec)
                continue
            # THE RAMP'S OWN TRAFFIC, as a direction at this node. `dir` always points AWAY from
            # the node, and a one-way ramp is drawn in the direction it is driven, so a ramp that
            # STARTS here carries traffic outward (an exit) and one that ends here carries it
            # inward (an entry).
            exit_ramp = ramp.at_start
            flow = ramp.dir if exit_ramp else (-ramp.dir[0], -ramp.dir[1])
            # The trunk stream that uses the ramp has to be going the same way as that flow: an
            # exit is fed by a stream ARRIVING at the node, an entry feeds one DEPARTING it.
            def _heading(a, _d=exit_ramp):
                return (-a.dir[0], -a.dir[1]) if _d else a.dir
            host = max(arms, key=lambda a: _heading(a)[0] * flow[0] + _heading(a)[1] * flow[1])
            # ...AND IT HAS TO BE A MERGE, NOT A TURN. How closely the ramp's own traffic lines up
            # with the stream it joins is the whole difference between a slip road (a driver
            # accelerates and merges, so the street grows a lane for it) and a T-junction (a driver
            # stops and turns, so it does not). Measured as the alignment of the two headings and
            # cut at `merge_angle_deg`, which is a real design number -- a motorway gore is a few
            # degrees, an urban slip road 30-45, and anything approaching square is a junction.
            align = _heading(host)[0] * flow[0] + _heading(host)[1] * flow[1]
            rec["host"] = host.edge.index
            host_at = ga.read_edge(bm, bm.edges[host.edge.index], el)
            rec["host_aux"] = max(int(host_at.get("aux_lanes_left", 0)),
                                  int(host_at.get("aux_lanes_right", 0)))
            rec["align_deg"] = math.degrees(math.acos(max(-1.0, min(1.0, align))))
            if align < merge_tol and not forced:
                rec["verdict"] = ("meets the road at %.0f deg, past the %.0f deg merge limit -- "
                                  "read as a turn, not a merge"
                                  % (rec["align_deg"], merge_angle_deg))
                out.append(rec)
                continue
            # AN AUXILIARY LANE IS A MAINLINE FEATURE. Where every arm of a "gore" is a one-way
            # single-lane ramp -- a ramp forking into two ramps, which the island has at the port
            # touchdown -- there is no mainline to widen, and stamping one anyway grew a second
            # lane on a ramp that then had nowhere to go (measured: `g44_F1`, an aux lane with no
            # successor at all, which reads on screen as a road preparing an exit that nothing can
            # take). Requiring the host to be genuinely wider than the ramp is the same road-class
            # test the exporter uses to pick a gore's trunk, and it costs nothing at a real gore
            # where a 4-lane carriageway sheds a 1-lane exit.
            if _lanes(host) <= _lanes(ramp):
                rec["verdict"] = ("the road it joins (%d lanes) is no wider than the ramp (%d) -- "
                                  "there is no mainline here to widen"
                                  % (_lanes(host), _lanes(ramp)))
                out.append(rec)
                continue
            ci = chain_of.get(host.edge.index)
            if ci is None:
                rec["verdict"] = "the road it joins is not part of any chain"
                out.append(rec)
                continue
            chain = all_chains[ci]
            e1, f1 = chain[-1]
            last_v = bm.edges[e1].verts[1 if f1 else 0].index
            # Which way the WALK runs where it meets the gore -- the frame every edge's
            # forward/backward flag is expressed in.
            wd = ((-host.dir[0], -host.dir[1]) if last_v == n.index else host.dir)
            head = _heading(host)
            # WHICH LANE GROUP GAINS THE LANE IS DECIDED BY THE STREAM, NOT BY THE RAMP'S SIDE.
            # `aux_lanes_left` / `aux_lanes_right` are not geometric sides -- they add to the
            # FORWARD and BACKWARD lane groups (`lane_profile`'s driving frame). Choosing them
            # from the ramp's geometric side, as this did, put the lane on the group travelling
            # the OTHER way: the aux opened on the carriageway leaving the exit instead of the one
            # feeding it, so it was fed by nothing and the ramp still took the through kerb lane.
            # The stream that uses the ramp is the one that needs the lane, so ask it directly.
            fwd_group = (head[0] * wd[0] + head[1] * wd[1]) > 0.0
            # A ramp belongs at its stream's KERB -- the left in keep-left traffic. One on the
            # other side would have its traffic cross the opposing carriageway to reach it, and
            # then NO auxiliary lane is the right answer: the lane group that needs it and the
            # side of the road the ramp is actually on are opposite, so any lane built here opens
            # on the far edge of the carriageway from the ramp it exists to serve, and orphans
            # itself. Skipping leaves the ramp meeting the through kerb lane -- unremarkable, and
            # exactly what happens without this operator. The layout is what needs fixing, so say
            # which nodes rather than quietly building a lane that cannot work.
            # WHICH SIDE THE RAMP IS ON IS MEASURED ALONG THE RAMP, NOT OFF ITS DEPARTURE
            # TANGENT. `ramp.dir` is the straight-line bearing of the first edge, and these ramps
            # CURVE -- a ramp can leave a shade to the median side and then swing right across to
            # the kerb, or the reverse. Judging by the tangent put the auxiliary lane on the far
            # edge of the carriageway from the ramp it exists to serve at four of the island's
            # gores (measured: the lane at +3.12 m while the ramp ran at -6.49 m, opposite sides of
            # the road), which is the "aux opens but the ramp connects to the middle" defect.
            # Walking it is the same correction `_nose_fn` needed, for the same reason.
            side = _ramp_side(outward, n, ramp, head)
            # Keep-left puts the kerb on the stream's left, so a ramp on its LEFT is the ordinary
            # nearside case and gets its lane at the outermost slot. A ramp on its RIGHT is offside
            # and there is no lane that can serve it -- see below.
            # OFFSIDE IS A LAYOUT ERROR, NOT A LANE OPTION. Under the convention above the lane
            # always opens at the kerb, so a ramp measured on the MEDIAN side of the stream it
            # serves is a ramp on the wrong side of the road: its traffic would have to cross the
            # opposing carriageway to reach it. Reported with the angle so the two cases stay
            # distinguishable -- a ramp a couple of degrees off tangent is a near-parallel merge
            # whose side is decided by rounding, while one well off tangent genuinely needs moving
            # in the layout. This used to quietly build the lane at the median end instead, which
            # put it on the far edge of the carriageway from the ramp it exists to serve.
            # ...BUT ONLY WHERE THE MEDIAN CANNOT BE CROSSED. On a limited-access road nothing
            # breaks the median, so a ramp on the offside of the stream it serves is unreachable
            # and the layout has to move. At a SURFACE junction the median does break -- a
            # diamond's ramp is legitimately entered from either direction of the cross street --
            # so which kerb the lane opens at is a choice, not an error. `allow_cross` is already
            # the vertex-domain switch for exactly that distinction (0 on the expressway, 1 on the
            # arterials), so it decides this too rather than a second flag that could disagree
            # with it. Reporting every gore alike flagged three surface touchdowns that were fine.
            # OFFSIDE IS NEVER SERVED. The lane always opens at the kerb, so a ramp measured on
            # the MEDIAN side of the stream it feeds gets a lane on the far side of the road from
            # itself -- measured at the island's IC_YAMATE entry (node 417): the ramp ends at
            # y=200.6 while the lane that opened for it starts at y=217.6, seventeen metres and
            # two opposing lanes away, and the ramp's own mesh was then aligned onto the lane's
            # side of nothing. Refusing is what makes that visible: no lane appears, the readout
            # says why, and the fix is to move the ramp in the layout.
            #
            # `allow_cross` does NOT license it. That flag is about whether a MOVEMENT may cross
            # the opposing stream (a diamond's ramp is legitimately entered from either direction
            # of the cross street, and such a ramp still connects here as an ordinary junction
            # arm). It says nothing about which kerb a lane may open at, and using it as if it did
            # is what let this one through.
            if side <= 0.0:
                crossable = (vl.get("allow_cross") is None
                             or int(bm.verts[n.index][vl["allow_cross"]]))
                rec["verdict"] = ("runs on the offside of the carriageway it feeds (%.0f m), so "
                                  "no lane can serve it here%s"
                                  % (abs(side), " -- it connects as an ordinary junction arm"
                                     if crossable else "; the ramp needs moving"))
                # A LAYOUT ERROR ONLY WHERE THE MEDIAN CANNOT BE CROSSED. On a limited-access road
                # an offside ramp is unreachable and the alignment has to move. At a surface
                # junction the median does break: the ramp simply TURNS onto the street like any
                # other arm, which is ordinary and not worth reporting -- reporting it anyway
                # buried the two real ones among twelve.
                if not crossable:
                    rec["offside_m"] = abs(side)
                out.append(rec)
                continue
            rec["chain"] = ci
            rec["fwd_group"] = fwd_group
            rec["ramp_chain"] = chain_of.get(ramp.edge.index)
            # WHERE THE RAMP HAS TO END UP: the centre of the auxiliary lane it continues, as a
            # signed lateral offset from the host stream's axis. Same number `_nose_fn` measures
            # towards -- but used to MOVE the ramp there rather than to cut it short of it.
            host_offs = derived_offsets(host_at)
            edge_off = max(abs(host_offs["curb_off_left"]), abs(host_offs["curb_off_right"]))
            lane_centre = max(edge_off - float(host_at.get("lane_width", 3.5)) * 0.5, 0.0)
            # ...MINUS THE RAMP'S OWN SHIFT, because a ramp's band is not centred on its polyline.
            # A one-way profile puts every lane on one side of the spine, so `paved_shift` is half
            # the ramp's width (2.25 m on a 4.5 m ramp) and the band runs from the polyline
            # outward. Aiming the POLYLINE at the lane centre therefore lands the BAND a full
            # half-width outboard -- measured in the testbed: ramp band y 10.2..14.7 against an
            # auxiliary lane at 7.6..11.1, overlapping only its outer 0.9 m and hanging 3.6 m off
            # the road, which is the "the ramp mesh sits loosely outside and never connects"
            # report. What has to land on the lane is the band, so aim that.
            ramp_at = ga.read_edge(bm, bm.edges[ramp.edge.index], el)
            rec["target"] = max(lane_centre - abs(derived_offsets(ramp_at)["paved_shift"]), 0.0)
            rec["axis"] = (head[0], head[1])
            rec["side_sign"] = 1.0 if side > 0.0 else -1.0
            out.append(rec)
    return out


def ramp_alignments(bm, result, gore_angle_deg=35.0, merge_angle_deg=None):
    """`{(node index, ramp chain id): (target offset, axis, side sign)}` -- where each ramp's end
    has to sit so that it lines up with the auxiliary lane it becomes.

    THE RAMP IS MOVED ONTO THE LANE, NOT CUT SHORT OF IT. A ramp's polyline ends at the junction
    VERTEX, which is on the mainline's centreline -- so swept as authored, its last stretch drives
    diagonally across the carriageway. The nose setback existed to stop that by trimming the ramp
    back to where it was still clear of the road, but the distance that takes depends on the angle
    the ramp comes in at: at the island's 6-degree entries it is 46 m, so 46 m of ramp simply was
    not built, and what the author sees is a road that stops in mid-air short of the junction. Any
    setback derived from the entry angle has that failure built into it.

    The end the ramp is supposed to reach is not the vertex at all -- it is the auxiliary lane, one
    lane's offset out from the centreline. So the last stretch is displaced sideways onto it and
    swept in full: the ramp's edges line up with the lane's edges, there is no gap to fill, and the
    approach in between stays exactly as authored, which is what makes it adjustable by hand."""
    out = {}
    for rec in ramp_candidates(bm, result, gore_angle_deg, merge_angle_deg):
        if rec["verdict"] is not None or rec["ramp_chain"] is None:
            continue
        out[(rec["node"], rec["ramp_chain"])] = (rec["target"], rec["axis"], rec["side_sign"])
    return out


def ramp_services(bm, result, gore_angle_deg=35.0, merge_angle_deg=None, force_edges=(),
                  only_edges=None):
    """`ramp_candidates` with the rejects dropped: `({(node, chain): {fwd_group, ...}},
    [(node, metres offside), ...])` -- the map every consumer actually stamps or tapers from."""
    services, wrong_side = {}, []
    for rec in ramp_candidates(bm, result, gore_angle_deg, merge_angle_deg, force_edges,
                               only_edges):
        if rec["offside_m"]:
            # REPORTED EVEN THOUGH IT IS REJECTED -- especially because it is rejected. A ramp on
            # the median side of the stream it feeds gets no lane at all now, so without this it
            # would simply, silently, not be served. The number is how far offside it runs, which
            # separates a near-parallel merge whose side is decided by rounding from a ramp that
            # genuinely needs moving.
            wrong_side.append((rec["node"], rec["offside_m"]))
        if rec["verdict"] is not None:
            continue
        services.setdefault((rec["node"], rec["chain"]), set()).add(rec["fwd_group"])
    return services, wrong_side


def ramp_plan(bm, result, gore_angle_deg=35.0, merge_angle_deg=None):
    """`(services, aligns, hosts)` from ONE `ramp_candidates` walk -- everything `graph_build`
    needs to know about the graph's merges.

    `services` and `aligns` are exactly what `ramp_services`/`ramp_alignments` return; `hosts` is
    `{(node, ramp chain): host chain id}`, the carriageway that GAINS the auxiliary lane at that
    merge. The host is the missing third of the picture: `aligns` is keyed on the RAMP's chain and
    `services` on the HOST's, so between them there is no way to name the remaining arm -- the one
    the ramp runs alongside on its way in. That arm is the one whose barrier stands in the merge
    corridor (see `graph_build.merge_corridor_ends`), and it is found by elimination.

    One walk rather than two also halves what a build spends here: each accessor re-walks every
    node in the graph, which on the island is 1,682 edges' worth of candidate testing."""
    services, aligns, hosts = {}, {}, {}
    for rec in ramp_candidates(bm, result, gore_angle_deg, merge_angle_deg):
        if rec["verdict"] is not None:
            continue
        services.setdefault((rec["node"], rec["chain"]), set()).add(rec["fwd_group"])
        if rec["ramp_chain"] is not None:
            key = (rec["node"], rec["ramp_chain"])
            aligns[key] = (rec["target"], rec["axis"], rec["side_sign"])
            hosts[key] = rec["chain"]
    return services, aligns, hosts


def declined_merges(bm, result, gore_angle_deg=35.0, merge_angle_deg=None):
    """`[(node, ramp edge, reason), ...]` for every arm that could have been a merge and was not.

    Visibility, not decoration. A ramp that is refused a lane still CONNECTS -- it becomes an
    ordinary arm of the junction and its traffic turns there -- so on screen the difference between
    "merged into a lane of its own" and "turns in like a side street" is a lane's width of asphalt,
    with nothing to click on to find out which happened or why. The build prints a count from this,
    and `explain_ramp` prints the reason for one edge."""
    return [(r["node"], r["ramp"], r["verdict"])
            for r in ramp_candidates(bm, result, gore_angle_deg, merge_angle_deg)
            if r["verdict"] is not None and r["host"] is not None]


def auto_aux_lanes(bm, result, count=1, taper=None, gore_angle_deg=35.0,
                   merge_angle_deg=None, force_edges=(), only_edges=None, buffer=None):
    """Stamp an auxiliary lane on every chain that feeds a GORE, on the group its ramp serves.

    Authoring a ramp by hand means finding the trunk, working out which side the ramp peels off,
    and stamping the whole chain -- three chances to put the lane on the wrong side of a road that
    is walked backwards. `ramp_services` already derives all of it (and is the SAME answer
    `graph_build` anchors the taper with, so the lane opens at the end its ramp attaches to);
    this only writes it down.

    Returns `(chains stamped, [(node, metres offside), ...] whose ramp runs on the wrong side)`."""
    el = ga.ensure_edge_layers(bm)
    bm.edges.ensure_lookup_table()
    all_chains = chains(bm)
    services, wrong_side = ramp_services(bm, result, gore_angle_deg, merge_angle_deg,
                                        force_edges, only_edges)
    stamped = set()
    for (_node, ci), groups in services.items():
        chain = all_chains[ci]
        stamped.add(ci)
        for fwd_group in groups:
            for eidx, forward in chain:
                # An edge walked against the chain has its own forward group on the walk's back.
                is_fwd = fwd_group if forward else not fwd_group
                key = "aux_lanes_left" if is_fwd else "aux_lanes_right"
                e = bm.edges[eidx]
                e[el[key]] = max(int(e[el[key]]), int(count))
                if taper is not None:
                    e[el["aux_taper_length"]] = float(taper)
                if buffer is not None:
                    e[el["aux_buffer_length"]] = float(buffer)
    return len(stamped), wrong_side


#: The most recent solve per graph object name: `{"result": SolveResult, "ramps": [record, ...]}`.
#: READ-ONLY UI DATA, and cached rather than recomputed because the panel's active-edge readout is
#: drawn on every redraw while `ramp_candidates` walks every node in the graph -- doing that live
#: would make the sidebar crawl on a 1,600-edge network. Refreshed by every Solve and every Build,
#: which is exactly when the answer can change. Holds no Blender data (the solver's specs are
#: plain Python), so it cannot keep a freed mesh alive.
_LAST_SOLVE = {}


def last_solve(obj):
    return _LAST_SOLVE.get(getattr(obj, "name", None))


def explain_ramp(obj, edge_index):
    """One line about what the road kit thinks the given edge is -- printed in the panel.

    "Nothing happened" is not a usable answer from an authoring tool. This says whether the edge
    is seen as a ramp merging into something, which road it would widen, and when it is not, the
    reason and the number behind it (the angle it meets at, the lane counts) so the author knows
    whether to move the road or to override the call with `rka.graph_ramp_aux`."""
    cached = last_solve(obj)
    if cached is None:
        return "press Solve to see how this arm is read"
    recs = [r for r in cached["ramps"] if r["ramp"] == edge_index]
    if not recs:
        return "not an arm of a junction that could merge"
    served = [r for r in recs if r["verdict"] is None]
    if served:
        r = served[0]
        return "merges at node %d into road g%d, %s group%s" % (
            r["node"], r["chain"], "forward" if r["fwd_group"] else "backward",
            "" if r["align_deg"] is None else " (%.0f deg)" % r["align_deg"])
    rec = recs[0]
    if rec.get("host_aux"):
        # STAMPED BY HAND (or forced), which beats the automatic call. Saying only "read as a
        # turn" here would report the rule while the file says otherwise -- the exact way a
        # readout stops being worth reading.
        return "%s -- but the road it joins already carries an aux lane, so the merge uses it" \
            % rec["verdict"]
    return rec["verdict"]


class RKA_OT_graph_ramp_aux(bpy.types.Operator):
    """Give the SELECTED ramp its own lane in the road it joins, and merge it into that lane.

    The override for everything `Auto Aux Lanes At Ramps` declines. That operator has to guess
    which arms are ramps, and it is deliberately conservative about it -- a one-way arm meeting a
    street past the merge angle is read as a turn, because most of them are. Pointing at the edge
    IS the answer to that question, so this one skips the angle test entirely: the arms you select
    are ramps, their roads grow a lane, and the merge goes into that lane instead of into the
    traffic already in the kerb lane.

    Everything else is identical to the automatic path -- same derivation of which carriageway and
    which end (`ramp_candidates`), same taper -- so a forced ramp behaves exactly like a detected
    one from here on."""
    bl_idname = "rka.graph_ramp_aux"
    bl_label = "Merge Selected Ramp Via Aux Lane"
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(name="Aux Lanes", default=1, min=1, soft_max=3)
    taper: bpy.props.FloatProperty(name="Taper", default=90.0, min=0.0, soft_max=250.0,
                                   unit='LENGTH')
    buffer: bpy.props.FloatProperty(
        name="Buffer After Merge", default=40.0, min=0.0, soft_max=400.0, unit='LENGTH',
        description="Full-width run held past the gore before the taper starts (the extra "
                    "segment after the merge). Gives a joining driver a settling length, and "
                    "gives the barrier a stretch at full aux width so it meets the ramp's own "
                    "wall in line instead of diving back inboard at the nose. Default matches "
                    "graph_build.AUX_MERGE_BUFFER")

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        if ga.reject_generated(context, self):
            return {'CANCELLED'}
        obj = ga.graph_object(context)
        sel = {e.index for e in bmesh.from_edit_mesh(obj.data).edges if e.select and not e.hide}
        if not sel:
            self.report({'WARNING'}, "Select the ramp's edge(s) first")
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            result = solve_object(obj)
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            try:
                recs = ramp_candidates(bm, result, force_edges=sel, only_edges=sel)
                n, wrong = auto_aux_lanes(bm, result, self.count, self.taper,
                                          force_edges=sel, only_edges=sel,
                                          buffer=float(self.buffer))
                bm.to_mesh(obj.data)
            finally:
                bm.free()
            obj.data.update()
            from . import graph_build as gbuild
            gbuild.build_object(obj)
        finally:
            bpy.ops.object.mode_set(mode='EDIT')
        if not n:
            why = next((r["verdict"] for r in recs if r["verdict"]), None)
            self.report({'WARNING'}, "No lane added: %s"
                        % (why or "the selected edge is not an arm of a junction"))
            return {'CANCELLED'}
        served = [r for r in recs if r["verdict"] is None]
        where = ", ".join("node %d -> g%d %s" % (r["node"], r["chain"],
                                                 "fwd" if r["fwd_group"] else "bwd")
                          for r in served[:4])
        self.report({'INFO'}, "Added %d aux lane(s) on %d road(s): %s" % (self.count, n, where))
        return {'FINISHED'}


class RKA_OT_graph_auto_aux(bpy.types.Operator):
    """Add a tapered auxiliary lane wherever a ramp joins or leaves a wider road.

    Covers a motorway gore AND a slip road touching down on a street: both are traffic joining or
    leaving without stopping, and both need the road to grow a lane rather than the ramp to take
    over a through lane."""
    bl_idname = "rka.graph_auto_aux"
    bl_label = "Auto Aux Lanes At Ramps"
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(name="Aux Lanes", default=1, min=1, soft_max=3)
    taper: bpy.props.FloatProperty(name="Taper", default=90.0, min=0.0, soft_max=250.0,
                                   unit='LENGTH')
    buffer: bpy.props.FloatProperty(
        name="Buffer After Merge", default=40.0, min=0.0, soft_max=400.0, unit='LENGTH',
        description="Full-width run held past the gore before the taper starts (the extra "
                    "segment after the merge). Gives a joining driver a settling length, and "
                    "gives the barrier a stretch at full aux width so it meets the ramp's own "
                    "wall in line instead of diving back inboard at the nose. Default matches "
                    "graph_build.AUX_MERGE_BUFFER")
    merge_angle: bpy.props.FloatProperty(
        name="Merge Angle (deg)", default=MERGE_ANGLE_DEG, min=5.0, max=90.0,
        description="How far off the through stream a one-way arm may point and still count as a "
                    "MERGE that earns an auxiliary lane. Beyond it the arm is a turn at a "
                    "junction, which gets a stop line, not an acceleration lane")

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        result = solve_object(obj)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        try:
            n, wrong = auto_aux_lanes(bm, result, self.count, self.taper,
                                      merge_angle_deg=float(self.merge_angle),
                                      buffer=float(self.buffer))
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        from . import graph_build as gbuild
        gbuild.build_object(obj)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        msg = "Stamped aux lanes on %d chain(s) where a ramp joins or leaves" % n
        if wrong:
            msg += " | %d ramp(s) on the wrong side: %s" % (
                len(wrong), ", ".join("node %d (%.0f deg)" % w for w in wrong[:6]))
        self.report({'WARNING'} if wrong else {'INFO'}, msg)
        return {'FINISHED'}


def is_lane_transition(bm, vert, el):
    """A vertex where the carriageway WIDTH changes -- where a road gains or loses a lane.

    Kept separate from `is_passthrough` because it is also the answer to "why is there no junction
    here?": parallel boundaries have no corner to fillet, which is why `road_graph_solve` refuses
    to trim such a pair and reports it as a `width_steps` defect. It is a TAPER, and
    `graph_build.chain_lane_counts` builds it as one."""
    if len(vert.link_edges) != 2:
        return False
    e0, e1 = vert.link_edges
    w0 = sum(edge_widths(ga.read_edge(bm, e0, el))[2:])
    w1 = sum(edge_widths(ga.read_edge(bm, e1, el))[2:])
    return abs(w0 - w1) > 0.05


def is_passthrough(bm, vert, node_type, el):
    """Does the road run CONTINUOUSLY through this vertex -- no trim, no patch, ONE ribbon?

    TRUE FOR EVERY VALENCY-2 VERTEX THE AUTHOR HAS NOT SAID OTHERWISE ABOUT. A vertex with exactly
    two edges is a point on ONE road: the road bends there, or changes width there, and neither is
    a junction. Treating it as one was the single biggest gap between what the island GENERATOR
    produces and what the panel does by hand -- the generator stamps `NODE_NONE` on all 1543 of
    its shape points, while an artist extruding a vertex in Edit Mode gets `AUTO`, so a hand-drawn
    six-vertex expressway came out as FIVE separate two-point ribbons that merely abutted. Every
    chain-level feature (the auxiliary-lane taper, the lane-count transition, a continuous sweep
    with no crease) was then confined to one segment, which reads exactly as "the panel does
    nothing" -- and the only cure was to know that you must stamp "Shape point" on every interior
    vertex first.

    A real junction is where roads MEET, which is valency >= 3, or where the author says so:
    `INTERSECTION` forces a trimmed, patched junction at valency 2 (a road that genuinely stops
    and starts -- a toll plaza, a control-of-access change), and `CAP` / `GORE` / `BEND` are
    likewise explicit. Only `AUTO` is inferred, and inferring "shape point" is what an artist
    drawing a road means every time.

    One predicate for both readers of the question (`chains`, which decides where a swept polyline
    ends, and `build_specs`, which decides what the solver is even shown). They must agree: a
    chain running through a vertex the solver trimmed would drop a junction patch into the middle
    of an unbroken ribbon."""
    if node_type == ga.NODE_NONE:
        return True
    return node_type == ga.NODE_AUTO and len(vert.link_edges) == 2


def chains(bm):
    """Group edges into maximal runs through `NODE_NONE` shape points.

    Returns `[[(edge_index, forward), ...], ...]`, `forward` meaning the edge is walked v0->v1.
    Direction matters: the cross-section is expressed relative to the edge's own direction, so a
    chain walking an edge backwards must mirror its left/right.

    A LANE-COUNT CHANGE IS ALSO A PASS-THROUGH. A straight valency-2 vertex whose two edges carry
    DIFFERENT carriageway widths is where the road gains or loses a lane, and that is a taper, not
    a junction: the solver refuses to trim it (it reports the pair as a `width_steps` defect --
    parallel boundaries have no corner to fillet), so left as a chain break it produced two
    separate ribbons with a step between them, which is the "the mesh just jumps/compresses there"
    report. Joined into one chain, `graph_build.chain_lane_counts` opens the lanes one at a time
    over `lane_transition_length` instead. Only ever applies where the solver would otherwise
    report a defect: same widths, or a real bend, still end the chain exactly as before.

    Depends only on AUTHORED data, never on a solve result -- so it can run before the solve and
    hand it the chain lengths it needs to clamp trimming against."""
    vl = ga.ensure_vert_layers(bm, fill_defaults=False)
    el = ga.ensure_edge_layers(bm, fill_defaults=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    def passthrough(v):
        if vl.get("node_type") is None:
            return False
        return is_passthrough(bm, v, int(v[vl["node_type"]]), el)

    def next_edge(v, came_from):
        return next((e for e in v.link_edges if e is not came_from), None)

    out, seen = [], set()
    starts = [e for e in bm.edges
              if not passthrough(e.verts[0]) or not passthrough(e.verts[1])]
    for e0 in starts:
        if e0.index in seen:
            continue
        head_v = e0.verts[0] if not passthrough(e0.verts[0]) else e0.verts[1]
        chain, edge, v = [], e0, head_v
        while edge is not None and edge.index not in seen:
            seen.add(edge.index)
            chain.append((edge.index, v is edge.verts[0]))
            v = edge.verts[1] if v is edge.verts[0] else edge.verts[0]
            edge = next_edge(v, edge) if passthrough(v) else None
        if chain:
            out.append(chain)
    for e in bm.edges:                     # closed loops made only of shape points
        if e.index not in seen:
            seen.add(e.index)
            out.append([(e.index, True)])
    return out


def chain_lengths(bm, chain_list):
    """{edge_index: (chain id, length of the whole chain)} -- what the solver clamps against."""
    out = {}
    for cid, chain in enumerate(chain_list):
        total = sum(bm.edges[i].calc_length() for i, _f in chain)
        for i, _f in chain:
            out[i] = (cid, total)
    return out


def build_specs(bm, force_intersection=()):
    """Graph mesh -> (`NodeSpec` list, `EdgeSpec` list) for the pure solver.

    `force_intersection` names nodes to show the solver as INTERSECTION whatever their valency
    says -- see `solve_object`, which uses it for a "gore" whose ramp turns out to be unservable."""
    R = rgs()
    vlayers = ga.ensure_vert_layers(bm, fill_defaults=False)
    elayers = ga.ensure_edge_layers(bm, fill_defaults=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    avail = chain_lengths(bm, chains(bm))

    nodes = []
    for v in bm.verts:
        a = ga.read_vert(bm, v, vlayers)
        kind = int(a.get("node_type", 0))
        # A PASS-THROUGH VERTEX IS SHOWN TO THE SOLVER AS A SHAPE POINT, so the two agree about
        # where a road ends (see `is_passthrough`). The solver has no taper and no continuous
        # bend: shown a valency-2 vertex it trims both approaches and patches the gap, dropping a
        # junction into the middle of a road that is only bending or getting wider.
        if is_passthrough(bm, v, kind, elayers):
            kind = ga.NODE_NONE
        if v.index in force_intersection:
            kind = ga.NODE_INTERSECTION
        nodes.append(R.NodeSpec(v.index, (v.co.x, v.co.y, v.co.z), kind,
                                float(a.get("node_radius", -1.0)),
                                float(a.get("fillet_radius", 4.0))))
    edges = []
    for e in bm.edges:
        a = ga.read_edge(bm, e, elayers)
        wl, wr, pl, pr = edge_widths(a)
        edges.append(R.EdgeSpec(e.index, e.verts[0].index, e.verts[1].index, wl, wr, pl, pr,
                                avail=(avail.get(e.index) or (None, None))[1],
                                chain=(avail.get(e.index) or (None, None))[0],
                                # A ramp is one-way, and the solver treats an acute corner against
                                # a one-way arm as a MERGE (a nose) rather than a junction (a pad).
                                oneway=is_oneway(a)))
    return nodes, edges


def write_solution(bm, result):
    """Trims onto the edge domain, node facts onto the point domain."""
    R = rgs()
    elayers = ga.ensure_edge_layers(bm)
    vlayers = ga.ensure_vert_layers(bm)
    for e in bm.edges:
        e[elayers["trim_start"]] = float(result.trim_start.get(e.index, 0.0))
        e[elayers["trim_end"]] = float(result.trim_end.get(e.index, 0.0))
        for name, value in derived_offsets(ga.read_edge(bm, e, elayers)).items():
            e[elayers[name]] = float(value)
    kind_code = {R.KIND_CAP: 0, R.KIND_JOINT: 1, R.KIND_BEND: 2, R.KIND_TAPER: 3,
                 R.KIND_INTERSECTION: 4, R.KIND_GORE: 5}
    by_index = {n.index: n for n in result.nodes}
    for v in bm.verts:
        n = by_index.get(v.index)
        if n is None:
            continue
        v[vlayers["solved_radius"]] = float(n.radius)
        v[vlayers["solved_kind"]] = kind_code.get(n.kind, 0)
        v[vlayers["valency"]] = len(v.link_edges)


def _generated_object(graph_obj, suffix, mesh):
    """Get-or-create the sibling that holds generated geometry, swapping only its mesh data so
    any Geometry Nodes stack already on it survives."""
    name = graph_obj.name + suffix
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != 'MESH':
        obj = bpy.data.objects.new(name, mesh)
        obj[GENERATED_TAG] = graph_obj.name
        for coll in graph_obj.users_collection:
            coll.objects.link(obj)
        obj.parent = graph_obj
        obj.matrix_parent_inverse = graph_obj.matrix_world.inverted()
        return obj
    old = obj.data
    # CARRY THE MATERIALS ACROSS. The mesh is replaced wholesale on every solve, and a fresh mesh
    # has no material slots -- so the asphalt `graph_build.build_object` assigns to the node pads
    # survived only until the next solve. Export re-solves (`collect` calls `solve_object`), which
    # meant the shipped island's 45 junction pads were untextured default grey: every intersection
    # a different colour from the road running into it. The stack-driven objects are unaffected
    # (GN assigns their materials each evaluation), so this only ever restores what was lost.
    for slot in old.materials:
        if slot is not None and slot.name not in mesh.materials:
            mesh.materials.append(slot)
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def build_node_mesh(name, result):
    """A TRIANGLE FAN per patched node, not one n-gon.

    A junction pad is a 40-plus-vertex polygon that is both CONCAVE (the mouths cut into it
    between kerb returns) and NON-PLANAR (each mouth sits at its own approach's elevation, so a
    graded junction is a saddle). Handing that to Blender as a single n-gon leaves its tessellation
    to the importer, and the result had holes: measured at node 58, three points in the MIDDLE of
    the junction were 0.38-0.49 m off any triangle, which is a turning car driving through a gap
    in the asphalt.

    Fanning it here removes the question. The pad is star-shaped about its own node -- every
    boundary point was constructed by walking outward from it -- so a fan from the node covers the
    whole region with triangles that are each individually planar. The hub sits at the mean of the
    boundary heights so the fan follows the pad's grade instead of tilting it."""
    verts, faces = [], []
    for n in result.nodes:
        if not n.patch or len(n.patch) < 3:
            continue
        ring = list(n.patch)
        hub = (sum(p[0] for p in ring) / len(ring),
               sum(p[1] for p in ring) / len(ring),
               sum(p[2] for p in ring) / len(ring))
        base = len(verts)
        verts.append(hub)
        verts.extend(ring)
        for i in range(len(ring)):
            faces.append([base, base + 1 + i, base + 1 + (i + 1) % len(ring)])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def build_corner_mesh(name, result, arc_segments=8, extra=None, node_z=None):
    """One open polyline per kerb corner arc, carrying THE SAME per-point attribute names the
    straight carrier uses -- so the identical layer stack sweeps a junction corner's kerb and
    footway, and there is no second implementation of "what a footway looks like".

    The arc IS the kerb line, so the kerb sits at offset 0 and the footway rides outboard of it.
    Which lateral direction is "outboard" depends on the arc's winding: `rka_lat` is
    `cross(+Z, tangent)`, which for a CCW arc points at the centre and for a CW arc away from it.
    Rather than make the node tree reason about that, the sign is resolved here and baked into the
    signed offsets -- the same rule as everywhere else, that Python owns lateral maths.

    Every other band's attribute is written as 0, which is exactly how they are switched off: a
    zero-width band sweeps nothing and a -1 asset index instances nothing."""
    extra = extra or {}
    verts, edges, radii, per_point = [], [], [], []
    for n in result.nodes:
        # Elevation now rides on the Corner itself (`z_a`/`z_b`, both derived from the same graph
        # vertex heights `node_z` carries), so a corner ramps with its approaches instead of
        # sitting flat. `node_z` is kept in the signature for callers that pre-date that.
        for c in n.corners:
            if abs(c.sweep) < 1e-6:
                continue
            # SWEEP THE WHOLE KERB LINE, mouth to mouth -- not just the fillet arc. A wide-angle
            # corner has a short fillet sitting well inside the mouths, so sweeping the arc alone
            # covered the bend and left the straight stretches between it and each road's own
            # footway completely bare. The straight parts get their own tangent from the polyline,
            # so the same layer stack sweeps them with no extra code. `kerb_line` is shared with
            # `_patch_polygon`, so the asphalt edge and the footway cannot disagree.
            line = c.kerb_line(arc_segments)
            pts = [p for p, _z in line]
            # Follow the grade between the two tangent points rather than sitting flat at the
            # node's height -- the pad the kerb edges does the same (`_patch_polygon`).
            zs = [z for _p, z in line]
            # The kerb-return centre lies BEYOND the kerb (see `_build_corners`), so the footway
            # is on the side TOWARD the centre. `rka_lat` = cross(+Z, tangent) points toward the
            # centre on a CCW arc (sweep > 0) and away from it on a CW one.
            sign = 1.0 if c.sweep > 0 else -1.0
            ea = extra.get(c.a.edge.index, {})
            eb = extra.get(c.b.edge.index, {})
            curb_h = max(float(ea.get("curb_height", 0.0)), float(eb.get("curb_height", 0.0)))
            walk = max(c.sidewalk_radius - c.radius, 0.0)
            base = len(verts)
            verts.extend([(p[0], p[1], zs[i]) for i, p in enumerate(pts)])
            radii.extend([c.sidewalk_radius] * len(pts))
            per_point.extend([{
                "rka_curb_hl": curb_h,
                "rka_curb_tl": curb_h * 0.5,
                "rka_curb_ol": 0.0,
                "rka_walk_cl": sign * (walk / 2.0),
                "rka_walk_hl": walk / 2.0,
            }] * len(pts))
            edges.extend([(base + i, base + i + 1) for i in range(len(pts) - 1)])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    me.update()
    if verts:
        attr = me.attributes.new(name="corner_radius", type='FLOAT', domain='POINT')
        attr.data.foreach_set("value", radii)
        for key in sorted(per_point[0].keys()):
            a = me.attributes.new(name=key, type='FLOAT', domain='POINT')
            a.data.foreach_set("value", [p[key] for p in per_point])
    return me


def solve_object(graph_obj, arc_segments=8):
    """Solve `graph_obj`'s network, write attributes back, refresh both generated objects.

    Returns the `SolveResult` so a caller can report `width_steps` / `too_short` -- the two
    outcomes that are authoring problems rather than solver failures."""
    me = graph_obj.data
    own = graph_obj.mode != 'EDIT'
    bm = bmesh.new() if own else bmesh.from_edit_mesh(me)
    try:
        if own:
            bm.from_mesh(me)
        nodes, edges = build_specs(bm)
        # Kept for the corner sweep, which needs each approach edge's kerb height -- carried
        # separately rather than widening `EdgeSpec`, which is the pure solver's input contract
        # and must stay about widths and topology only.
        elayers = ga.ensure_edge_layers(bm, fill_defaults=False)
        extra = {e.index: ga.read_edge(bm, e, elayers) for e in bm.edges}
        node_z = {v.index: v.co.z for v in bm.verts}
        # ONE MERGE THRESHOLD for the geometry and for the lanes. The solver uses it to decide
        # that an acute corner against a one-way arm is a nose rather than a pad; `ramp_candidates`
        # uses it to decide the same arm earns an auxiliary lane. A junction cannot be a merge for
        # one and a corner for the other.
        #
        # TWO PASSES, because which ramps get aligned is an answer only a solved graph can give
        # (it needs each node's approaches), and the alignment then changes what the solve should
        # do with them -- an aligned ramp must NOT be set back. The first pass is thrown away
        # except for that one question; on the island it costs about a second.
        def _solve(aligned=(), force=(), aligns=None):
            ns, es = (nodes, edges) if not force else build_specs(bm, force)
            return rgs().solve(ns, es, arc_segments=arc_segments,
                               station_fn=_station_fn(bm, aligns),
                               nose_fn=_nose_fn(bm, aligned),
                               merge_angle_deg=MERGE_ANGLE_DEG)

        first = _solve()
        recs = ramp_candidates(bm, first)
        aligned = {(rec["node"], rec["ramp"]) for rec in recs if rec["verdict"] is None}
        # A "GORE" WHOSE RAMP CANNOT MERGE IS A JUNCTION. A gore is defined by nothing having to
        # stop -- but a ramp that is refused a lane (offside, or the road no wider than itself)
        # has nowhere to merge INTO, so its traffic turns here like any other arm. Solved as a
        # gore it kept a gore's geometry: no pad, only the nose wedge, and the ramp left hanging a
        # few metres short of a road it never joins. Shown to the solver as an intersection it
        # gets the ordinary corner setbacks and a real pad, which is what closes that gap -- the
        # same machinery every crossing already uses.
        served_at = {rec["node"] for rec in recs if rec["verdict"] is None}
        gore_kind = rgs().KIND_GORE
        kinds_first = {n.index: n.kind for n in first.nodes}
        # ONLY THE OFFSIDE CASE. A ramp declined because the road is no wider than itself is a
        # FORK -- a 2-lane road splitting into two 2-lane roads, where nothing stops and both
        # halves carry on -- and that is a gore whether or not a lane was stamped for it. An
        # OFFSIDE ramp is the one that has nowhere to merge into at all, so it turns instead.
        # ...AND ONLY WHERE A JUNCTION IS EVEN POSSIBLE. `allow_cross = 0` means a limited-access
        # road: nothing crosses its median and there is no at-grade junction anywhere on it, so an
        # offside ramp there stays a gore (its nose runs alongside) and the layout is what gets
        # fixed. Re-solving it as an intersection instead drops a full at-grade pad across a
        # motorway, which is a worse answer than the problem it was fixing.
        vl_cross = ga.ensure_vert_layers(bm, fill_defaults=False).get("allow_cross")
        bm.verts.ensure_lookup_table()

        def _crossable(i):
            return vl_cross is None or int(bm.verts[i][vl_cross])

        force = {r["node"] for r in recs
                 if r["verdict"] and "offside" in r["verdict"] and r["node"] not in served_at
                 and kinds_first.get(r["node"]) == gore_kind and _crossable(r["node"])}
        result = (_solve(aligned, force, ramp_alignments(bm, first))
                  if (aligned or force) else first)
        write_solution(bm, result)
        _LAST_SOLVE[graph_obj.name] = {"result": result,
                                       "ramps": ramp_candidates(bm, result)}
        if own:
            bm.to_mesh(me)
            me.update()
        else:
            bmesh.update_edit_mesh(me)
    finally:
        if own:
            bm.free()

    # Node z comes from the graph vertices, which already carry elevation, so the patches land at
    # the right height without a second source of truth for grade.
    _generated_object(graph_obj, SUFFIX_NODES,
                      build_node_mesh(graph_obj.name + SUFFIX_NODES, result))
    _generated_object(graph_obj, SUFFIX_CORNERS,
                      build_corner_mesh(graph_obj.name + SUFFIX_CORNERS, result, arc_segments,
                                        extra=extra, node_z=node_z))
    return result


def crossings_for(graph_obj, z_tol=4.0):
    """Same-grade XY crossings with no shared vertex -- junctions the author forgot to weld.
    See `road_graph_solve.find_crossings` for why this is the one error the graph cannot
    self-detect."""
    own = graph_obj.mode != 'EDIT'
    bm = bmesh.new() if own else bmesh.from_edit_mesh(graph_obj.data)
    try:
        if own:
            bm.from_mesh(graph_obj.data)
        nodes, edges = build_specs(bm)
        return rgs().find_crossings(nodes, edges, z_tol)
    finally:
        if own:
            bm.free()


def weld_crossings(bm, z_tol=4.0, max_passes=200):
    """Weld every same-grade XY crossing that has no shared vertex, in place.

    A crossing with no shared vertex is not an intersection -- in a mesh graph, connectivity IS
    the vertex, so two roads laid over each other at the same height simply pass through without
    meeting. `graph_validate` has always REPORTED these; this fixes them, which matters because
    the report is easy to read as cosmetic when it is actually "cars cannot turn here".

    Generators miss them for their own reasons (the island's builder tests only pairs of DIFFERENT
    roads, and merges junctions within 12 m, which can leave the true crossing point a few metres
    from where the shared vertex was placed), so repairing the built graph is more robust than
    fixing any one producer -- and it works on hand-authored graphs too.

    One crossing per pass, re-detecting between passes: splitting an edge renumbers everything
    after it, so a batch of indices collected up front goes stale on the first split."""
    R = rgs()
    welded = 0
    for _ in range(max_passes):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        nodes, edges = build_specs(bm)
        found = R.find_crossings(nodes, edges, z_tol)
        if not found:
            break
        ia, ib, x, y, _dz = found[0]
        ea, eb = bm.edges[ia], bm.edges[ib]
        va = _split_at(bm, ea, x, y)
        bm.edges.ensure_lookup_table()
        # `eb` survives the first split (a different edge), but its index may not -- re-find it by
        # its two endpoints rather than trusting the stale index.
        vb = _split_at(bm, eb, x, y)
        if va is None or vb is None:
            break
        z = (va.co.z + vb.co.z) * 0.5
        bmesh.ops.pointmerge(bm, verts=[va, vb], merge_co=(x, y, z))
        # The new node must be a REAL junction: an island shape point is stamped NODE_NONE, and
        # a split inherits that, which would weld the roads and then still build no junction.
        vl = ga.ensure_vert_layers(bm)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            if abs(v.co.x - x) < 1e-4 and abs(v.co.y - y) < 1e-4:
                v[vl["node_type"]] = ga.NODE_AUTO
        welded += 1
    return welded


def _split_at(bm, edge, x, y):
    """Split `edge` at the point nearest (x, y) and return the new vertex.

    `bmesh.utils.edge_split` copies the edge's custom data onto the new half, so both halves keep
    the cross-section that was authored on the original -- which is the whole reason a weld can be
    a repair rather than a re-author."""
    import bmesh.utils
    v0, v1 = edge.verts
    dx, dy = v1.co.x - v0.co.x, v1.co.y - v0.co.y
    den = dx * dx + dy * dy
    if den < 1e-12:
        return None
    t = ((x - v0.co.x) * dx + (y - v0.co.y) * dy) / den
    t = max(1e-4, min(1.0 - 1e-4, t))
    _new_edge, new_vert = bmesh.utils.edge_split(edge, v0, t)
    new_vert.co.x, new_vert.co.y = x, y
    return new_vert


class RKA_OT_graph_weld_crossings(bpy.types.Operator):
    """Insert a shared vertex wherever two roads cross at the same height without one."""
    bl_idname = "rka.graph_weld_crossings"
    bl_label = "Weld Same-Grade Crossings"
    bl_options = {'REGISTER', 'UNDO'}

    z_tol: bpy.props.FloatProperty(
        name="Height Tolerance", default=4.0, min=0.0, soft_max=20.0, unit='LENGTH',
        description="Roads whose heights differ by more than this cross as a flyover and are "
                    "left alone")

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        try:
            n = weld_crossings(bm, self.z_tol)
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        if n:
            from . import graph_build as gbuild
            gbuild.build_object(obj)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, "Welded %d crossing(s) into real junctions" % n)
        return {'FINISHED'}


class RKA_OT_graph_solve(bpy.types.Operator):
    """Solve trims, node kinds, patches and kerb corners for the active road graph."""
    bl_idname = "rka.graph_solve"
    bl_label = "Solve Road Graph"
    bl_options = {'REGISTER', 'UNDO'}

    arc_segments: bpy.props.IntProperty(
        name="Corner Segments", default=8, min=2, max=32,
        description="Points per kerb corner arc -- raise for a large radius, lower for density")

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        result = solve_object(obj, self.arc_segments)
        kinds = {}
        for n in result.nodes:
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        msg = ", ".join("%d %s" % (v, k) for k, v in sorted(kinds.items()))
        level = {'INFO'}
        if result.width_steps:
            msg += " | %d width step(s) need a taper" % len(result.width_steps)
            level = {'WARNING'}
        if result.too_short:
            msg += " | %d edge(s) too short for their junctions: %s" % (
                len(result.too_short), result.too_short[:4])
            level = {'WARNING'}
        for ws in result.width_steps:
            print("[rka.graph_solve] width step at node %d between edges %d/%d: %.2f m"
                  % ws)
        for ts in result.too_short:
            print("[rka.graph_solve] edge %d is %.2f m but its junctions want %.2f m" % ts)
        xs = crossings_for(obj)
        if xs:
            msg += " | %d same-grade crossing(s) with no shared vertex" % len(xs)
            level = {'WARNING'}
            for a, b, x, y, dz in xs[:10]:
                print("[rka.graph_solve] edges %d/%d cross at (%.1f, %.1f), dz %.2f m -- weld a "
                      "vertex there, or separate them vertically" % (a, b, x, y, dz))
        self.report(level, msg)
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_solve, RKA_OT_graph_auto_aux, RKA_OT_graph_ramp_aux,
           RKA_OT_graph_weld_crossings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
