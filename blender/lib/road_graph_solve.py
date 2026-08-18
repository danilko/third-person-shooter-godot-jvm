"""road_graph_solve.py -- pure-Python (no bpy), self-tested topology solver for the MESH-GRAPH
road model. `python3 lib/road_graph_solve.py` self-tests, same convention as `lane_profile.py`.

THE MODEL. One mesh is the whole network: every VERTEX is a node (intersection / bend / gore /
terminus), every EDGE is a road segment carrying its own cross-section attributes. This module
answers the three questions Geometry Nodes cannot:

  1. how far back must each segment be TRIMMED at each of its two ends, so the swept ribbons of
     everything meeting at that node do not overlap each other,
  2. what POLYGON fills the resulting hole (the intersection's asphalt patch),
  3. where do the kerb CORNER ARCS go, and at what radii, so a sidewalk can be swept around them.

WHY THIS IS NOT A GEOMETRY NODES PROBLEM. Every one of those needs, at a single node, the
incident edges SORTED BY ANGLE and a max taken over pairs. Geometry Nodes has no per-vertex loop
and no per-group max (`Accumulate Field` only sums), so the closest it can express is an average
of the incident edges' widths -- which is wrong exactly where trimming matters most, at a wide
arterial meeting a narrow street. `self_test` measures that error rather than asserting it in a
comment. So Python owns the graph, and the node tree receives numbers it never re-derives -- the
same "generated data, not runtime inference" rule the rest of this pipeline runs on, and the same
"nodes never do slot math" discipline `road_stack.py`'s docstring fixes for the cross-section.

THE SETBACK FORMULA. Put node N at the origin. Approach `i` leaves along unit `d_i` and carries
half-width `W_i` on the side facing approach `j`, which leaves along `d_j` at CCW angle `theta`.
Approach i's boundary is the line offset `W_i` from its centreline; j's is offset `W_j` from its.
Those two lines cross at distance

    t_i(j) = (W_j + W_i * cos theta) / sin theta

along `d_i` (and symmetrically for j, swapping the two widths). Add a kerb fillet of radius `r`
tangent to both boundaries and the tangent point sits a further `r / tan(theta/2)` back, so

    setback_i = max over corners of [ t_i(j) + r / tan(theta/2) ],  clamped to >= 0

Only ANGULARLY ADJACENT pairs are considered: a non-adjacent pair's boundaries are screened by
the approach between them and never form the binding corner.

THE TWO DEGENERATE ANGLES, both real and both common:

  * `theta -> pi` (collinear pass-through) makes `sin theta -> 0` with `cos theta -> -1`, so the
    formula diverges. It is not a corner at all -- the two boundaries are PARALLEL. Equal widths
    means they are the same line (setback 0, a plain joint); different widths means the road
    steps in width and needs a TAPER, not a junction. Reported as `width_steps` rather than
    silently trimmed, because a taper is authoring work no setback can substitute for.
  * `theta -> 0` (an edge doubling back on itself) diverges the other way, toward an infinite
    setback. Clamped by `min_angle_deg`, and then again by `max_trim_fraction` of the edge's own
    length -- an edge trimmed to nothing from both ends is the single most common mesh-graph
    authoring failure and it must fail loudly, as `too_short`, not produce a hole.

SIGN CONVENTION. `+lat` (the left side of an edge, travelling v0 -> v1) is `rotate_ccw_90(dir)`,
matching `road_stack.ATTR_LAT` = `normalize(cross(+Z, tangent))`. An approach reaching a node from
its far end travels the reverse direction, so ITS left is the edge's right -- `Approach.from_edge`
is the one place that flip happens, and every width below is already in approach-local terms.
"""
import math

# --------------------------------------------------------------------------------- small vectors


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _mul(a, s):
    return (a[0] * s, a[1] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _length(a):
    return math.hypot(a[0], a[1])


def _norm(a):
    n = _length(a)
    return (0.0, 0.0) if n < 1e-12 else (a[0] / n, a[1] / n)


def _left(d):
    """+90 degrees (CCW). The left side of something travelling along `d`."""
    return (-d[1], d[0])


def _right(d):
    return (d[1], -d[0])


def _line_intersect(p0, d0, p1, d1):
    """Intersection of two parametric lines, or None if near-parallel."""
    den = _cross(d0, d1)
    if abs(den) < 1e-9:
        return None
    t = _cross(_sub(p1, p0), d1) / den
    return _add(p0, _mul(d0, t))


# ------------------------------------------------------------------------------------ input data

#: Node kinds. AUTO is resolved from valency + geometry by `solve`; the rest are artist overrides
#: stamped on the vertex domain (see `graph_attrs.NODE_TYPE_ITEMS` -- these integers must match).
AUTO = 0
BEND = 1
INTERSECTION = 2
CAP = 3
GORE = 4
#: Shape point: bend the road, build no junction. See `graph_attrs.NODE_NONE`.
NONE = 5

#: Resolved kinds `solve` reports back per node.
KIND_CAP = 'CAP'
KIND_JOINT = 'JOINT'            # valency 2, straight, same width -- nothing to build
KIND_BEND = 'BEND'              # valency 2, turning -- a patch fills the wedge
KIND_TAPER = 'TAPER'            # valency 2, straight, width steps -- needs an authored transition
KIND_INTERSECTION = 'INTERSECTION'
KIND_GORE = 'GORE'              # valency 3+, all approaches within `gore_angle_deg` -- a split
KIND_NONE = 'NONE'              # shape point -- continuous ribbon, no junction of any kind


class EdgeSpec(object):
    """One graph edge's solver input: its two endpoint indices and the widths its cross-section
    reaches on each side. Widths come from `lane_profile.extents()` (via `graph_solve.py`), NOT
    recomputed here -- this module must never grow a second opinion about where a slot is."""

    __slots__ = ("index", "v0", "v1", "w_left", "w_right", "paved_left", "paved_right", "avail",
                 "chain")

    def __init__(self, index, v0, v1, w_left, w_right, paved_left=None, paved_right=None,
                 avail=None, chain=None):
        #: Id of the CHAIN this edge belongs to -- a run of edges joined through shape points,
        #: which is the unit a road is actually trimmed as. Defaults to the edge's own index, so
        #: an unchained graph behaves exactly as before.
        self.chain = index if chain is None else chain
        self.index = index
        self.v0 = v0
        self.v1 = v1
        #: How much road length is actually available to be trimmed back at this edge's ends --
        #: the length of the whole CHAIN it belongs to, not of this edge. A polyline resampled
        #: every 12 m has 12 m edges, and a junction on an arterial legitimately sets back 40 m;
        #: clamping that against the edge would truncate every real junction, while measuring it
        #: against the chain lets the setback eat through the intermediate shape points, which is
        #: what actually happens on the ground. None = fall back to this edge's own length.
        self.avail = None if avail is None else float(avail)
        #: outer half-widths, sidewalk included -- what must clear at a junction.
        self.w_left = float(w_left)
        self.w_right = float(w_right)
        #: carriageway-only half-widths -- what the asphalt patch spans.
        self.paved_left = float(w_left if paved_left is None else paved_left)
        self.paved_right = float(w_right if paved_right is None else paved_right)


class NodeSpec(object):
    __slots__ = ("index", "pos", "node_type", "radius_override", "fillet")

    def __init__(self, index, pos, node_type=AUTO, radius_override=-1.0, fillet=4.0):
        self.index = index
        self.pos = (float(pos[0]), float(pos[1]), float(pos[2]) if len(pos) > 2 else 0.0)
        self.node_type = int(node_type)
        self.radius_override = float(radius_override)
        self.fillet = float(fillet)


class Approach(object):
    """One edge as seen FROM one node: direction away from the node, plus that edge's widths
    already flipped into approach-local left/right."""

    __slots__ = ("edge", "at_start", "dir", "angle", "w_left", "w_right",
                 "paved_left", "paved_right", "length", "setback", "grade",
                 "station_pos", "station_dir")

    def __init__(self, edge, at_start, direction, length, grade=0.0):
        self.edge = edge
        self.at_start = at_start
        self.dir = direction
        self.angle = math.atan2(direction[1], direction[0])
        self.length = length
        self.setback = 0.0
        #: Filled in by `solve(station_fn=...)` -- see `mouth()`.
        self.station_pos = None
        self.station_dir = None
        #: Rise per metre travelling AWAY from the node along this approach. The junction pad has
        #: to follow it: a flat pad at the node's own height leaves the ribbon floating above or
        #: sunk into the asphalt wherever an approach is on a slope.
        self.grade = grade
        if at_start:
            self.w_left, self.w_right = edge.w_left, edge.w_right
            self.paved_left, self.paved_right = edge.paved_left, edge.paved_right
        else:
            # Reaching the node from the far end reverses travel, so the edge's LEFT is this
            # approach's RIGHT. This flip lives here and nowhere else.
            self.w_left, self.w_right = edge.w_right, edge.w_left
            self.paved_left, self.paved_right = edge.paved_right, edge.paved_left

    def mouth(self, node_pos):
        """((x, y, z), (dx, dy)) where this approach's ribbon ACTUALLY ends, and which way it
        points there.

        A setback is a distance measured ALONG THE CHAIN, and a chain bends through its shape
        points. Assuming the trim lands `setback` metres down the straight line from the node --
        which is all this module can compute on its own, since it only ever sees one edge -- puts
        the junction's mouth in the wrong place and at the wrong angle the moment the road curves:
        measured on the island, 38 of 144 approaches were over a metre out and one by 38.8 m, with
        angle errors up to 180 degrees. That is the pad not lining up with the road it meets, and
        it is worst on exactly the sweeping approaches where it is most visible.

        So a caller that HAS the real polyline (`graph_solve`, which walks the same chains the
        carrier is built from) supplies the true station through `solve(station_fn=...)`. Without
        one, this falls back to the straight-line estimate, which is exact for a straight
        approach and is what the pure self-tests use."""
        if self.station_pos is not None and self.station_dir is not None:
            p = self.station_pos
            z = p[2] if len(p) > 2 else node_pos[2]
            return (p[0], p[1], z), self.station_dir
        return ((node_pos[0] + self.dir[0] * self.setback,
                 node_pos[1] + self.dir[1] * self.setback,
                 node_pos[2] + self.rise()), self.dir)

    def rise(self):
        """Height gain from the node to this approach's trim station.

        CLAMPED TO THE EDGE, because `grade` was measured over THIS edge only while a setback may
        be far longer -- it eats through shape points into the rest of the chain. Extrapolating a
        short resampled edge's slope over a 100 m setback invents elevation that is not on the
        road at all (it produced 76 m tall junction pads). Clamping stops at the far vertex, whose
        height is at least a real point on the carriageway."""
        return self.grade * min(self.setback, self.length)


class Corner(object):
    """The kerb fillet between two angularly adjacent approaches. `center`/`radius`/`start_angle`/
    `sweep` describe the arc in world XY; `sidewalk_radius` is the concentric outer arc a sidewalk
    profile sweeps along -- concentric because the kerb line and the sidewalk's outer line share
    this centre, which is what makes a corner sidewalk one swept arc instead of a stitch."""

    __slots__ = ("node", "a", "b", "center", "radius", "start_angle", "sweep",
                 "tangent_a", "tangent_b", "sidewalk_radius", "z_a", "z_b", "mouth_a", "mouth_b")

    def __init__(self, node, a, b, center, radius, start_angle, sweep, ta, tb, sidewalk_radius,
                 z_a=0.0, z_b=0.0, mouth_a=None, mouth_b=None):
        #: Where each approach's own kerb line ENDS -- the outer corner of its mouth cross-bar.
        #: The fillet is tangent at `tangent_a`/`tangent_b`, and those coincide with the mouths
        #: only when the fillet fits inside the setback. When the setback is capped (a skew
        #: junction) or clamped (a short chain) the tangent points sit further IN, and the stretch
        #: between mouth and tangent is real kerb that something has to cover -- see `kerb_line`.
        self.mouth_a = mouth_a
        self.mouth_b = mouth_b
        #: Elevation at each tangent point. A kerb return between two approaches on different
        #: grades has to ramp between them, exactly as the pad it edges does.
        self.z_a = z_a
        self.z_b = z_b
        self.node = node
        self.a = a
        self.b = b
        self.center = center
        self.radius = radius
        self.start_angle = start_angle
        self.sweep = sweep
        self.tangent_a = ta
        self.tangent_b = tb
        self.sidewalk_radius = sidewalk_radius

    def sample(self, segments=8):
        """Arc points, tangent A -> tangent B."""
        return [(self.center[0] + self.radius * math.cos(self.start_angle + self.sweep * i / segments),
                 self.center[1] + self.radius * math.sin(self.start_angle + self.sweep * i / segments))
                for i in range(segments + 1)]

    def sample_z(self, segments=8):
        """Elevation for each `sample()` point, ramping tangent A -> tangent B."""
        return [self.z_a + (self.z_b - self.z_a) * i / segments for i in range(segments + 1)]

    def kerb_line(self, segments=8):
        """The COMPLETE kerb line of this corner: `[((x, y), z), ...]` from where approach A's own
        kerb ends, around the fillet, to where approach B's begins.

        ONE DEFINITION, TWO CONSUMERS -- the asphalt pad edges along it and the corner footway is
        swept along it, so they cannot disagree.

        Two problems this fixes, both of which are the same problem:

          * THE PAD WAS NOTCHED INWARD. The pad walked mouth cross-bar, then jumped to the
            fillet's tangent point. Whenever that tangent sits inside the mouth -- which is every
            capped skew junction -- the jump cuts a notch into the middle of the junction, and a
            turning car drove through it (measured 0.38-0.49 m outside the asphalt at node 58).
          * THE FOOTWAY STOPPED AT THE ARC. A wide-angle corner has a short fillet a long way from
            the mouths, so the swept corner footway covered the bend and nothing else, leaving the
            stretch between the arc and the road's own footway bare. Narrow-angle corners looked
            fine only because there the fillet nearly reaches the mouths by itself.

        So the line always REACHES BOTH MOUTHS: straight from mouth A to tangent A, the arc,
        straight from tangent B to mouth B. A degenerate stretch (tangent already at the mouth)
        contributes nothing, so a corner that fits is unchanged."""
        arc = self.sample(segments)
        zs = self.sample_z(segments)
        out = []
        if self.mouth_a is not None and _length(_sub(self.mouth_a, arc[0])) > 1e-4:
            out.append((self.mouth_a, self.z_a))
        out.extend(zip(arc, zs))
        if self.mouth_b is not None and _length(_sub(self.mouth_b, arc[-1])) > 1e-4:
            out.append((self.mouth_b, self.z_b))
        return out


class NodeResult(object):
    __slots__ = ("index", "kind", "radius", "approaches", "corners", "patch", "notes")

    def __init__(self, index, kind, radius, approaches, corners, patch, notes):
        self.index = index
        self.kind = kind
        self.radius = radius
        self.approaches = approaches
        self.corners = corners
        self.patch = patch
        self.notes = notes


class SolveResult(object):
    __slots__ = ("nodes", "trim_start", "trim_end", "width_steps", "too_short", "truncated")

    def __init__(self, nodes, trim_start, trim_end, width_steps, too_short, truncated=None):
        self.nodes = nodes
        #: (node_index, edge_index, wanted, capped) -- corners whose apex was past the size cap.
        #: NOT an error: a skew crossing genuinely has a distant apex and this is the decision not
        #: to pave out to it. Reported so an author can see which junctions are skewed enough to
        #: be worth re-laying closer to square.
        self.truncated = truncated if truncated is not None else []
        #: per edge index -> metres trimmed off that end
        self.trim_start = trim_start
        self.trim_end = trim_end
        #: (node_index, edge_a, edge_b, delta_metres) -- collinear pairs whose widths disagree
        self.width_steps = width_steps
        #: (edge_index, length, requested_trim) -- edges the trims would consume
        self.too_short = too_short


# ----------------------------------------------------------------------------------------- solve

def solve(nodes, edges, min_angle_deg=12.0, max_trim_fraction=0.9, gore_angle_deg=35.0,
          straight_tol_deg=6.0, arc_segments=8, station_fn=None, max_setback_factor=1.5,
          stub_length=5.0, gore_nose_max=200.0, nose_fn=None):
    """Trim distances, node kinds, corner arcs and patch polygons for the whole graph.

    `max_setback_factor` BOUNDS THE JUNCTION, in multiples of the widest approach half-width at
    that corner (floored at the right-angle answer, so it can only ever remove a blow-up). The apex formula below is geometrically exact -- it is where the two carriageway
    edges really do cross -- but that distance diverges as the crossing angle closes, and paving
    out to it means a 16 m road crossing at 15 degrees produces a 136 m setback and a 7,352 m2
    junction: a crater, not an intersection, taking the footway and the lane routes with it (the
    island had 24 of 45 pads over 1,000 m2 where a square crossing wants ~256). Real skew
    junctions are not paved to their apex either; they are truncated. So a corner is capped at
    `factor * max(w_a, w_b)`, which leaves every crossing above ~50 degrees untouched (a square
    one asks `w + r`, well inside the cap) and truncates only the shallow ones.

    THE COST IS OVERLAP, DELIBERATELY. Below the apex the two ribbons cross each other inside the
    junction instead of stopping short of it, so their asphalt overlaps. That is the same trade
    the sub-`min_angle_deg` gore branch already makes, and it is the right way round: overlapping
    asphalt reads as asphalt, while an un-paved gap reads as a hole in the world.

    `max_trim_fraction` caps the SUM of a chain's setbacks at that fraction of its length, so a
    road can never be entirely eaten by its own junctions. Hitting the cap is reported in
    `too_short` rather than silently accepted -- the geometry it produces is a hole, and a hole in
    a road reads as a bug in the generator rather than as authoring that needs a longer road."""
    incident = {n.index: [] for n in nodes}
    node_by_index = {n.index: n for n in nodes}
    lengths = {}
    for e in edges:
        p0, p1 = node_by_index[e.v0].pos, node_by_index[e.v1].pos
        d = _sub((p1[0], p1[1]), (p0[0], p0[1]))
        ln = _length(d)
        lengths[e.index] = ln
        if ln < 1e-6:
            continue
        u = _norm(d)
        grade = (p1[2] - p0[2]) / ln
        incident[e.v0].append(Approach(e, True, u, ln, grade))
        incident[e.v1].append(Approach(e, False, (-u[0], -u[1]), ln, -grade))

    min_sin = math.sin(math.radians(min_angle_deg))
    straight_tol = math.radians(straight_tol_deg)
    gore_tol = math.radians(gore_angle_deg)
    results, width_steps, truncated = [], [], []
    # setback[(edge_index, at_start)] -- accumulated as a max over that end's two corners.
    setbacks = {}
    # pending[node_index] -> [(a, b, theta, fillet_radius, walk_width), ...]
    # Corner ARCS ARE NOT BUILT IN THIS PASS. An arc is only valid relative to the setbacks its
    # approaches finally get, and those are not known until the per-chain clamp below has run --
    # building arcs here and clamping afterwards is what desynchronised the two and produced
    # self-intersecting patches (a hole in the junction) with spikes off it.
    pending = {}

    for node in nodes:
        appr = sorted(incident[node.index], key=lambda a: a.angle)
        for a in appr:
            setbacks.setdefault((a.edge.index, a.at_start), 0.0)
        if not appr:
            results.append(NodeResult(node.index, KIND_CAP, 0.0, [], [], [], ["isolated vertex"]))
            continue
        if len(appr) == 1:
            results.append(NodeResult(node.index, KIND_CAP, 0.0, appr, [], [], []))
            continue
        if node.node_type == NONE:
            # A shape point contributes no setback to either end, so the ribbons stay welded and
            # the road reads as one continuous sweep through it. Skipped here rather than filtered
            # later so it also cannot push a neighbouring edge into `too_short`.
            results.append(NodeResult(node.index, KIND_NONE, 0.0, appr, [], [], []))
            continue

        notes = []
        records = pending.setdefault(node.index, [])
        n = len(appr)

        # A GORE IS NOT A CORNER, AND MUST NOT USE THE CORNER FORMULA. Its approaches are nearly
        # parallel by definition (that is what makes it a tangential split), so `sin theta -> 0`
        # and the setback diverges: the island's ramps asked for 210 m of trim on a 23 m chain.
        # Physically a split needs only enough room to seat the nose between the diverging
        # ribbons, and the width TRANSITION is authored with aux lanes, not produced by trimming.
        # Classified here, before the corner loop, because the kind depends only on angles.
        pre = NodeResult(node.index, AUTO, 0.0, appr, [], [], notes)
        if _resolve_kind(node, pre, straight_tol, gore_tol) == KIND_GORE:
            # THE MAINLINE RUNS THROUGH A GORE UNCUT. Only the ramp is trimmed, back to its nose.
            # Setting back every approach (what this used to do) chews a hole out of the trunk
            # carriageway at every merge -- the road visibly narrows into the junction pad instead
            # of carrying straight on, which is the wrong read entirely: a driver on the mainline
            # does not slow, stop or change lanes at a merge, and the geometry should say so.
            # `_gore_trunk` gives the arriving trunk; its continuation is whichever branch runs
            # most nearly opposite it, and that PAIR is the mainline.
            trunk = _gore_trunk(pre, gore_tol)
            main = _gore_mainline(appr, trunk) if trunk else None
            through = {id(trunk), id(main)} if trunk else set()
            for a in appr:
                if id(a) in through:
                    continue          # mainline: no setback, the ribbon stays continuous
                key = (a.edge.index, a.at_start)
                setbacks[key] = max(setbacks[key],
                                    _gore_nose(node, trunk, main, a, gore_nose_max, nose_fn))
            if trunk is None:
                notes.append("gore with no identifiable trunk -- every approach set back")
            results.append(NodeResult(node.index, KIND_GORE, 0.0, appr, [], [], notes))
            continue

        for k in range(n):
            a, b = appr[k], appr[(k + 1) % n]
            theta = (b.angle - a.angle) % (2.0 * math.pi)
            if n == 2 and k == 1:
                # A valency-2 node has two "corners" (the two sides of the road); the second is
                # simply the complementary angle and must not be skipped -- it is the outside of
                # the bend, where the wedge that needs filling actually is.
                pass
            wa, wb = a.w_left, b.w_right
            r = max(node.fillet, 0.0)

            if abs(math.pi - theta) < straight_tol:
                # Collinear pass-through: parallel boundaries, no corner. A width mismatch here
                # is a taper the author has to build, so surface it instead of trimming.
                if abs(wa - wb) > 0.05:
                    width_steps.append((node.index, a.edge.index, b.edge.index,
                                        round(abs(wa - wb), 3)))
                continue

            key_a, key_b = (a.edge.index, a.at_start), (b.edge.index, b.at_start)
            sin_t, cos_t = math.sin(theta), math.cos(theta)
            if sin_t < min_sin:
                # A NEAR-PARALLEL PAIR IS A GORE, NOT A CORNER -- the same reasoning as the
                # whole-node gore branch above, applied to one pair. `(wb + wa cos t)/sin t`
                # diverges as the pair approaches parallel, and merely CLAMPING the angle does not
                # tame it: at the 12 degree floor a 16 m road still asks for a 190 m setback, and
                # the island has valency-7 nodes with approaches 0.0 degrees apart (roads welded
                # into one junction all leaving the same way) which produced exactly that -- the
                # long spikes off a junction. Two ribbons running side by side only need room to
                # seat between them, so size it like a gore and grow no fillet.
                setbacks[key_a] = max(setbacks[key_a], max(a.paved_left, a.paved_right))
                setbacks[key_b] = max(setbacks[key_b], max(b.paved_left, b.paved_right))
                notes.append("approach pair below %.0f deg, treated as a gore" % min_angle_deg)
                continue
            fillet_back = r / math.tan(theta / 2.0) if theta > 1e-6 else 0.0
            t_a = max((wb + wa * cos_t) / sin_t + fillet_back, 0.0)
            t_b = max((wa + wb * cos_t) / sin_t + fillet_back, 0.0)
            # Bound the junction. See the `max_setback_factor` paragraph in the docstring: the
            # apex is exact but unbounded, and a junction the size of a city block is a worse
            # answer than two ribbons overlapping for a few metres.
            # FLOORED AT THE RIGHT-ANGLE ANSWER (`max(w) + r`, what this same formula returns at
            # theta = 90) so the cap can only ever remove a skew blow-up, never shrink a junction
            # below the square one it is modelled on. Without the floor the factor silently
            # becomes a second, wrong width model the moment someone raises `fillet_radius`.
            cap = max(max_setback_factor * max(wa, wb), max(wa, wb) + r)
            if t_a > cap or t_b > cap:
                truncated.append((node.index, a.edge.index, round(max(t_a, t_b), 2),
                                  round(cap, 2)))
                notes.append("corner truncated to %.1f m (apex wanted %.1f m at %.0f deg)"
                             % (cap, max(t_a, t_b), math.degrees(theta)))
                t_a, t_b = min(t_a, cap), min(t_b, cap)
            setbacks[key_a] = max(setbacks[key_a], t_a)
            setbacks[key_b] = max(setbacks[key_b], t_b)
            if r > 1e-6:
                walk = max(a.w_left - a.paved_left, b.w_right - b.paved_right, 0.0)
                records.append((a, b, theta, r, walk))

        results.append(NodeResult(node.index, AUTO, 0.0, appr, [], [], notes))

    # ---- clamp, then resolve kind + patch with the FINAL setbacks
    # CLAMP PER CHAIN, JOINTLY. The real constraint is that a road's two end setbacks together
    # must not eat the road; capping each end at a fraction on its own is a bad proxy that
    # truncates a chain trimmed hard at one end and not at all at the other (the island had 75 m
    # chains with a legitimate 46 m junction setback reported as too short). Summing over the
    # chain also handles the case the ends belong to DIFFERENT edges, which is the normal case
    # once shape points exist -- an interior edge simply contributes 0.
    too_short = []
    by_chain = {}
    for e in edges:
        by_chain.setdefault(e.chain, []).append(e)
    for cid, group in by_chain.items():
        ln = group[0].avail if group[0].avail is not None else sum(lengths[e.index] for e in group)
        cap = ln * max_trim_fraction
        keys = [(e.index, at_start) for e in group for at_start in (True, False)]
        total = sum(setbacks.get(k, 0.0) for k in keys)
        if total > cap and total > 1e-9:
            scale = cap / total
            for k in keys:
                if setbacks.get(k, 0.0) > 0.0:
                    setbacks[k] *= scale
            too_short.append((group[0].index, round(ln, 2), round(total, 2)))
    trim_start = {e.index: setbacks.get((e.index, True), 0.0) for e in edges}
    trim_end = {e.index: setbacks.get((e.index, False), 0.0) for e in edges}

    for res in results:
        node = node_by_index[res.index]
        for a in res.approaches:
            a.setback = setbacks.get((a.edge.index, a.at_start), 0.0)
            # Only NOW is the setback final, so only now can a caller resolve where that distance
            # along the real chain actually lands -- see `Approach.mouth`.
            if station_fn is not None:
                st = station_fn(node, a)
                if st is not None:
                    a.station_pos, a.station_dir = st
        res.radius = (node.radius_override if node.radius_override >= 0.0
                      else max([a.setback for a in res.approaches] or [0.0]))
        res.kind = _resolve_kind(node, res, straight_tol, gore_tol)
        res.corners = _build_corners(node, pending.get(res.index, ()), res.notes, min_sin)
        if res.kind in (KIND_INTERSECTION, KIND_BEND, KIND_GORE):
            res.patch = _patch_polygon(node, res, arc_segments)
    _merge_stub_joined_patches(results, edges, setbacks, lengths, by_chain, stub_length)
    return SolveResult(results, trim_start, trim_end, width_steps, too_short, truncated)


def _merge_stub_joined_patches(results, edges, setbacks, lengths, by_chain, stub_length):
    """ONE PAD WHERE TWO JUNCTIONS HAVE EATEN THE ROAD BETWEEN THEM.

    A ramp that splits a few metres before a surface crossing leaves a scrap of road shorter than
    a car. Both nodes still solve, so two pads land almost on top of each other, overlap, and
    close through one another -- a bow-tie of asphalt with the ramp appearing to drive into the
    middle of the mainline instead of connecting to it. `graph_export` already merges such a pair
    into one junction for the lane graph (a stub is not a drivable segment), and the mesh has to
    agree or the routes are right while the road under them is not. Their convex hull is one
    honest interchange pad -- the same repair the gore nose already uses, and the shape a real
    diverge-at-a-crossing has."""
    if stub_length <= 0.0:
        return
    parent = {}

    def _root(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _cid, group in by_chain.items():
        ln = group[0].avail if group[0].avail is not None else sum(lengths[e.index] for e in group)
        used = sum(setbacks.get((e.index, s), 0.0) for e in group for s in (True, False))
        if ln - used >= stub_length:
            continue
        # The chain's two ENDS are the vertices it touches exactly once; everything else is a
        # shape point it runs through.
        seen = {}
        for e in group:
            for v in (e.v0, e.v1):
                seen[v] = seen.get(v, 0) + 1
        ends = [v for v, c in seen.items() if c == 1]
        if len(ends) == 2:
            ra, rb = _root(ends[0]), _root(ends[1])
            if ra != rb:
                parent[ra] = rb

    groups = {}
    for res in results:
        groups.setdefault(_root(res.index), []).append(res)
    for root, members in groups.items():
        if len(members) < 2:
            continue
        pts = [p for m in members for p in m.patch]
        if len(pts) < 3:
            continue
        hull = _convex_hull([(p[0], p[1]) for p in pts])
        if len(hull) < 3:
            continue
        zof = {(round(p[0], 4), round(p[1], 4)): p[2] for p in pts}
        zmean = sum(p[2] for p in pts) / float(len(pts))
        pad = [(h[0], h[1], zof.get((round(h[0], 4), round(h[1], 4)), zmean)) for h in hull]
        keep = next((m for m in members if m.index == root), members[0])
        for m in members:
            if m is keep:
                m.patch = pad
            elif m.patch:
                m.patch = []
                m.notes.append("junction merged into node %d -- the road between them trims away"
                               % keep.index)


def _build_corners(node, records, notes, min_sin):
    """Kerb fillets, built from the FINAL setbacks -- the whole reason this is a second pass.

    THE ARC IS TANGENT TO THE KERB LINES, NOT TO THE OUTER RIBBON. The setback had to clear the
    widest thing at this node (sidewalks included), but the "corner radius" an artist means is the
    kerb radius a bus wheel tracks, which is the carriageway edge. So the two use different
    offsets on purpose: `w_*` (outer) sizes the trim, `paved_*` (asphalt) places the arc.

    THE FILLET SITS OUTSIDE THE APEX, NOT INSIDE IT. A kerb return flares the asphalt OUT into the
    corner so a truck can track round it; its centre is in the block beyond the corner, and its
    tangent points are `r/tan(theta/2)` PAST the apex, further from the node. That is not a
    stylistic choice -- it is what the setback formula already assumes:

        setback = (wb + wa cos t)/sin t + r/tan(t/2)  ==  apex_reach + fillet_back

    so with the outward convention the tangent point lands EXACTLY on the trim station and the
    boundary walk in `_patch_polygon` closes with no gap. The original code subtracted instead of
    added, putting the fillet a full `2 * fillet_back` inside the junction (10 m in on a 20 m
    road); the walk then had to jump inward to the arc and back out to the next approach, which is
    what self-intersected 35 of the island's 45 junctions.

    The per-chain clamp can still scale a setback below `apex_reach + fillet_back`. The fillet is
    then SHRUNK (never grown) so its tangents stay at or inside the trim, and dropped entirely if
    no positive radius fits -- the patch simply chords across, which is the right look for a
    junction too cramped to round."""
    corners = []
    for a, b, theta, r, walk in records:
        # Both boundary lines are taken from the MOUTHS, not from offsets at the node: the fillet
        # has to be tangent to the kerb lines the ribbons actually present, or it meets them at an
        # angle and the corner reads as a crease.
        (max_, may, za), mad = a.mouth(node.pos)
        (mbx, mby, zb), mbd = b.mouth(node.pos)
        corner_a = _add((max_, may), _mul(_left(mad), a.paved_left))
        corner_b = _add((mbx, mby), _mul(_right(mbd), b.paved_right))
        # THE ANGLE MUST COME FROM THE SAME DIRECTIONS AS THE LINES. Taking the boundary lines
        # from the mouths but the fillet angle from the node put the apex kilometres away whenever
        # a curving approach left its mouth pointing differently from its start (one island
        # junction's pad spanned 4.3 km). Re-derive it here, and treat a near-parallel pair as the
        # non-corner it is.
        theta_m = math.atan2(_cross(mad, mbd), _dot(mad, mbd)) % (2.0 * math.pi)
        if math.sin(theta_m) < min_sin:
            notes.append("corner dropped: mouths near-parallel")
            continue
        P = _line_intersect(corner_a, mad, corner_b, mbd)
        if P is None:
            continue
        bis = _norm(_add(mad, mbd))
        if _length(bis) < 1e-9:
            continue
        half = math.tan(theta_m / 2.0)
        if half <= 1e-9:
            continue                # reflex pair (the outside of a bend) -- no kerb return here
        # The fillet may reach no further than each mouth's own outer corner, measured from the
        # apex. When the geometry is consistent it lands exactly ON them and the patch closes with
        # no gap; when a clamp has pulled a mouth in, it stops short and the patch chords across.
        back = min(r / half,
                   _dot(_sub(corner_a, P), mad),
                   _dot(_sub(corner_b, P), mbd))
        if back <= 1e-6:
            notes.append("corner dropped: no fillet fits the trimmed ends")
            continue
        r_eff = back * half
        if r_eff <= 1e-6:
            continue
        center = _add(P, _mul(bis, r_eff / math.sin(theta_m / 2.0)))
        ta = _add(P, _mul(mad, back))
        tb = _add(P, _mul(mbd, back))
        start_angle = math.atan2(ta[1] - center[1], ta[0] - center[0])
        end_angle = math.atan2(tb[1] - center[1], tb[0] - center[0])
        sweep = end_angle - start_angle
        while sweep > math.pi:
            sweep -= 2.0 * math.pi
        while sweep < -math.pi:
            sweep += 2.0 * math.pi
        # The footway rides OUTBOARD of the kerb on the SAME centre, so a corner sidewalk is one
        # concentric sweep rather than a stitched patch. Width is whichever adjacent footway is
        # wider -- they have to meet at the tangent points. Stored as `radius + width` so the
        # width survives; which physical SIDE outboard is (the centre is now beyond the kerb, so
        # outboard points toward it) is resolved from the arc winding in `build_corner_mesh`.
        corners.append(Corner(node.index, a, b, center, r_eff, start_angle, sweep, ta, tb,
                              r_eff + walk, za, zb, mouth_a=corner_a, mouth_b=corner_b))
    return corners


def _resolve_kind(node, res, straight_tol, gore_tol):
    if node.node_type == NONE:
        return KIND_NONE
    if node.node_type == CAP:
        return KIND_CAP
    if node.node_type == BEND:
        return KIND_BEND
    if node.node_type == INTERSECTION:
        return KIND_INTERSECTION
    if node.node_type == GORE:
        return KIND_GORE
    n = len(res.approaches)
    if n <= 1:
        return KIND_CAP
    if n == 2:
        a, b = res.approaches
        theta = (b.angle - a.angle) % (2.0 * math.pi)
        if abs(math.pi - theta) < straight_tol:
            step = abs(a.w_left - b.w_right) > 0.05 or abs(a.w_right - b.w_left) > 0.05
            return KIND_TAPER if step else KIND_JOINT
        return KIND_BEND
    if _gore_trunk(res, gore_tol) is not None:
        return KIND_GORE
    return KIND_INTERSECTION


def _angular_spread(angles):
    """Width of the smallest arc containing every angle -- i.e. 2*pi minus the largest gap."""
    if len(angles) < 2:
        return 0.0
    s = sorted(angles)
    gaps = [(s[(i + 1) % len(s)] - s[i]) % (2.0 * math.pi) for i in range(len(s))]
    return 2.0 * math.pi - max(gaps)


def _gore_nose(node, trunk, main, ramp, nose_max, nose_fn=None):
    """How far along a ramp its NOSE is: where its pavement has CLEARED the carriageway.

    THE RAMP MUST START AT THE EDGE OF THE ROAD, NOT AT THE MIDDLE OF IT. This used to set the
    ramp back by its own half-width alone -- about 2.25 m on a 4.5 m ramp -- so the ramp's lane
    began 2.6 m from the trunk's centreline while the auxiliary lane it is supposed to continue sat
    9.35 m out at the carriageway edge. Measured across the island, 7 of 10 gores had their ramp
    starting 6.5-9.6 m away from their own auxiliary lane. Everything that looks wrong about those
    interchanges follows from that one number: the exit connector has to cut diagonally across
    every through lane to reach the ramp, so the ramp appears to drive out of the middle of the
    road, and the auxiliary lane that opened for it leads to a lane that is nowhere near it.

    A real gore nose is where the two pavements separate, which is `trunk half-width + ramp
    half-width` MEASURED PERPENDICULAR to the mainline. Along a ramp leaving at angle `theta` that
    is `target / sin(theta)` -- the same apex geometry a skew crossing has, and it diverges the
    same way as the ramp approaches parallel, so it is capped. The cap is generous (`nose_max`,
    default 200 m) because a motorway exit genuinely does take 100-150 m to separate; this is not
    a tolerance to tighten, it is the length of a real gore."""
    own = max(ramp.paved_left, ramp.paved_right)
    if trunk is None:
        return own
    # WALK THE REAL RAMP WHERE THE CALLER CAN SUPPLY IT. The closed form below assumes the ramp
    # leaves in a straight line, and these ramps CURVE away hard: solving `target / sin(theta)`
    # off the departure tangent and then travelling that far along a curve overshot by 60-150 m,
    # which is the same class of error `station_fn` exists to remove for junction mouths. The
    # callback measures the perpendicular offset along the actual chain and stops at the first
    # point that has cleared the carriageway.
    if nose_fn is not None:
        walked = nose_fn(node, trunk, main, ramp)
        if walked is not None:
            return max(own, min(float(walked), nose_max))
    target = max(trunk.paved_left, trunk.paved_right) + own
    # The mainline's heading THROUGH the node -- the direction the ramp diverges from. `trunk`
    # points back up the arriving road, so its continuation is the opposite bearing.
    ref = main.angle if main is not None else trunk.angle + math.pi
    theta = abs((ramp.angle - ref + math.pi) % (2.0 * math.pi) - math.pi)
    sin_t = math.sin(theta)
    if sin_t < 1e-6:
        return min(nose_max, max(own, target))
    return max(own, min(target / sin_t, nose_max))


def _gore_trunk(res, gore_tol):
    """The trunk approach if this node is a SPLIT/MERGE rather than a crossing, else None.

    A gore is defined by TANGENCY, not by valency: one approach (the trunk) arrives, and every
    other leaves in a tight cone pointing the opposite way, so no stream ever crosses another and
    nothing has to stop. That is why an off-ramp must not be built as an intersection pad -- the
    pad exists to make traffic turn and yield, which is exactly what a split does not do.

    Tested per candidate trunk rather than by looking at angular gaps alone: a plain T-junction
    also has one large gap, and calling that a gore would build a motorway split where a stop line
    belongs."""
    for t in res.approaches:
        others = [a for a in res.approaches if a is not t]
        if len(others) < 2 or _angular_spread([a.angle for a in others]) > gore_tol:
            continue
        mx = sum(math.cos(a.angle) for a in others) / len(others)
        my = sum(math.sin(a.angle) for a in others) / len(others)
        if _length((mx, my)) < 1e-9:
            continue
        opposed = math.atan2(-my, -mx)
        delta = abs((t.angle - opposed + math.pi) % (2.0 * math.pi) - math.pi)
        if delta <= gore_tol:
            return t
    return None


def _gore_mainline(approaches, trunk):
    """The branch that CONTINUES the trunk through a gore -- the one running most nearly opposite
    it. Together they are the through carriageway; every other approach is a ramp.

    Picked by straightness rather than by width, because a merge legitimately changes the trunk's
    lane count (that is what the aux lane is for) while the through movement is always the one a
    driver takes without steering."""
    if trunk is None:
        return None
    best, best_delta = None, None
    for a in approaches:
        if a is trunk:
            continue
        # 0 = exactly opposite the trunk, i.e. dead straight through the node.
        delta = abs((a.angle - trunk.angle + math.pi) % (2.0 * math.pi) - math.pi)
        delta = abs(math.pi - delta)
        if best_delta is None or delta < best_delta:
            best, best_delta = a, delta
    return best


def _patch_polygon(node, res, arc_segments):
    """The node's asphalt boundary, CCW. Walks each approach's trimmed end from its right
    boundary to its left, then follows the kerb arc round to the next approach.

    Uses `paved_*` (carriageway) widths, not the outer widths the setback cleared with -- the
    patch is asphalt, and sidewalks ride their own swept corner arcs above it.

    `_build_corners` guarantees every tangent point lies at or inside its approach's final
    setback, which is what makes this walk simple. That guarantee is checked rather than trusted:
    a self-intersecting n-gon triangulates into overlapping inverted faces, and reads in the
    viewport as a HOLE in the middle of the junction with spikes off it -- a failure mode too
    quiet and too ugly to leave to an invariant holding. On a violation the boundary falls back to
    its convex hull, which is always simple and always covers the junction; over-covering a
    concave junction slightly is a far better failure than a hole.

    THE PAD IS NOT FLAT. Each approach's mouth sits at the road's own elevation where the ribbon
    was trimmed (`node z + grade * setback`), and a corner arc ramps between its two neighbours.
    A pad held flat at the node's height leaves the carriageway floating above it or buried in it
    wherever an approach is on a grade -- up to a metre on this island's ramps, which reads as the
    junction not lining up with the roads that meet it."""
    # A GORE'S PAD IS ITS NOSE, AND THE MOUTH WALK CANNOT BUILD IT. A gore deliberately does not
    # trim its mainline (cutting the through road at a merge is the defect that rule exists to
    # prevent), so BOTH trunk mouths sit exactly on the node. Walking mouths in angular order then
    # lays two overlapping cross-bars through one point and closes them into a bow-tie: measured,
    # all 11 island gores came out at 6-43% of the area their own width needs, four of them
    # self-intersecting, which is the scrambled sliver a gore shows instead of a nose.
    #
    # What is actually missing at a diverge is only the WEDGE between the two ribbons as they
    # separate -- everything else is already paved by the ribbons themselves, untrimmed. The convex
    # hull of the mouth ends is exactly the smallest region that closes that wedge, and being convex
    # it cannot fold. So a gore takes the hull directly rather than being repaired into one after
    # the fact.
    if res.kind == KIND_GORE:
        ring = []
        for a in res.approaches:
            (mx, my, za), md = a.mouth(node.pos)
            for lat, w in ((_right(md), a.paved_right), (_left(md), a.paved_left)):
                q = _add((mx, my), _mul(lat, w))
                ring.append((q[0], q[1], za))
        hull = _convex_hull([(p[0], p[1]) for p in ring])
        if len(hull) >= 3:
            zof = {(round(p[0], 4), round(p[1], 4)): p[2] for p in ring}
            return [(h[0], h[1], zof.get((round(h[0], 4), round(h[1], 4)), node.pos[2]))
                    for h in hull]
    pts = []
    corners = {(c.a.edge.index, c.a.at_start): c for c in res.corners}
    for a in res.approaches:
        # The mouth is the ribbon's REAL end -- position and heading both (see `Approach.mouth`).
        (mx, my, za), md = a.mouth(node.pos)
        base = (mx, my)
        r = _add(base, _mul(_right(md), a.paved_right))
        l = _add(base, _mul(_left(md), a.paved_left))
        pts.append((r[0], r[1], za))
        pts.append((l[0], l[1], za))
        c = corners.get((a.edge.index, a.at_start))
        if c is not None and abs(c.sweep) > 1e-6:
            # The FULL kerb line, mouth to mouth -- not the bare arc. The arc alone left the
            # boundary jumping from the mouth to a tangent point further in, notching the pad
            # inward exactly where a turning lane runs. See `Corner.kerb_line`.
            pts.extend((p[0], p[1], z) for p, z in c.kerb_line(arc_segments))
    # An unclamped fillet's tangent lands exactly on the trim station, so the cross-bar's outer
    # point and the arc's first sample coincide. Dropping the duplicate keeps the n-gon clean.
    pts = [p for i, p in enumerate(pts)
           if _length(_sub(p, pts[i - 1])) > 1e-4 or len(pts) < 2]
    if len(pts) >= 3 and not _is_simple(pts):
        hull = _convex_hull(pts)
        if len(hull) >= 3:
            res.notes.append("patch self-intersected, replaced with convex hull")
            # The hull is a plan-view repair and carries no elevation; fall back to node height.
            pts = [(p[0], p[1], node.pos[2]) for p in hull]
    return [(p[0], p[1], p[2]) for p in pts]


def _cross_2d(a0, a1, b0, b1):
    """True when two XY segments properly cross. Separate from `_segment_cross` because that one
    interpolates a Z for the grade-separation check and so requires 3D endpoints."""
    p, r = a0, _sub(a1, a0)
    q, s = b0, _sub(b1, b0)
    den = _cross(r, s)
    if abs(den) < 1e-9:
        return False
    t = _cross(_sub(q, p), s) / den
    u = _cross(_sub(q, p), r) / den
    return 1e-9 < t < 1.0 - 1e-9 and 1e-9 < u < 1.0 - 1e-9


def _is_simple(pts):
    """True when the closed polyline `pts` has no two non-adjacent edges crossing."""
    n = len(pts)
    for i in range(n):
        a0, a1 = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue            # first and last edges share a vertex
            if _cross_2d(a0, a1, pts[j], pts[(j + 1) % n]):
                return False
    return True


def _convex_hull(pts):
    """Monotone-chain hull in XY, CCW. Used only to repair a boundary that failed `_is_simple`."""
    uniq = sorted(set((round(p[0], 6), round(p[1], 6)) for p in pts))
    if len(uniq) < 3:
        return []

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and _cross(_sub(out[-1], out[-2]), _sub(p, out[-2])) <= 0.0:
                out.pop()
            out.append(p)
        return out[:-1]

    return half(uniq) + half(list(reversed(uniq)))


# --------------------------------------------------------------------- grade-separation check

def find_crossings(nodes, edges, z_tol=4.0):
    """Edge pairs that cross in XY WITHOUT sharing a vertex, at heights closer than `z_tol`.

    THE ONE AUTHORING ERROR A MESH GRAPH CANNOT SELF-DETECT. Two roads that cross without a shared
    vertex are, by definition, not connected -- which is exactly right for an overpass and exactly
    wrong for a junction the author forgot to make. The geometry is identical in both cases; only
    the height difference distinguishes them. So a flyover is silent (heights differ) and a
    same-grade crossing is reported, and no flag is needed on either: grade separation is
    expressed by NOT merging the vertices, which is what the mesh graph already means.

    Returns `(edge_a, edge_b, x, y, dz)` per finding. Segments are bucketed by their bounding
    boxes first, so a whole island's few thousand edges cost a scan rather than an all-pairs test.
    """
    pos = {n.index: n.pos for n in nodes}
    boxes = []
    for e in edges:
        p0, p1 = pos[e.v0], pos[e.v1]
        boxes.append((e, min(p0[0], p1[0]), min(p0[1], p1[1]),
                      max(p0[0], p1[0]), max(p0[1], p1[1])))
    boxes.sort(key=lambda b: b[1])

    out = []
    for i, (ea, ax0, ay0, ax1, ay1) in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            eb, bx0, by0, bx1, by1 = boxes[j]
            if bx0 > ax1:
                break                        # sorted by min-x: nothing further can overlap
            if by0 > ay1 or by1 < ay0:
                continue
            if {ea.v0, ea.v1} & {eb.v0, eb.v1}:
                continue                     # they meet at a node; that IS a junction
            hit = _segment_cross(pos[ea.v0], pos[ea.v1], pos[eb.v0], pos[eb.v1])
            if hit is None:
                continue
            x, y, za, zb = hit
            if abs(za - zb) < z_tol:
                out.append((ea.index, eb.index, x, y, abs(za - zb)))
    return out


def _segment_cross(a0, a1, b0, b1):
    """(x, y, z_on_a, z_on_b) where two 3D segments cross in plan, or None."""
    p, r = (a0[0], a0[1]), _sub((a1[0], a1[1]), (a0[0], a0[1]))
    q, s = (b0[0], b0[1]), _sub((b1[0], b1[1]), (b0[0], b0[1]))
    den = _cross(r, s)
    if abs(den) < 1e-9:
        return None
    t = _cross(_sub(q, p), s) / den
    u = _cross(_sub(q, p), r) / den
    # Strict interior: an endpoint landing exactly on another edge is a T-junction the author
    # may still need to weld, but it is not a CROSSING and reporting it would drown the signal.
    if not (1e-6 < t < 1 - 1e-6 and 1e-6 < u < 1 - 1e-6):
        return None
    return (p[0] + r[0] * t, p[1] + r[1] * t,
            a0[2] + (a1[2] - a0[2]) * t, b0[2] + (b1[2] - b0[2]) * u)


# ------------------------------------------------------------------------------------- self-test

def _edge(i, v0, v1, wl, wr, pl=None, pr=None):
    return EdgeSpec(i, v0, v1, wl, wr, pl, pr)


def self_test():
    # ---- 1. straight pass-through: no trimming, no patch
    nodes = [NodeSpec(0, (-50, 0, 0)), NodeSpec(1, (0, 0, 0)), NodeSpec(2, (50, 0, 0))]
    edges = [_edge(0, 0, 1, 8.0, 8.0), _edge(1, 1, 2, 8.0, 8.0)]
    r = solve(nodes, edges)
    assert r.nodes[1].kind == KIND_JOINT, r.nodes[1].kind
    assert r.trim_end[0] == 0.0 and r.trim_start[1] == 0.0
    assert not r.width_steps

    # ---- 2. straight pass-through with a width step: reported, not silently trimmed
    edges = [_edge(0, 0, 1, 8.0, 8.0), _edge(1, 1, 2, 12.0, 12.0)]
    r = solve(nodes, edges)
    assert r.nodes[1].kind == KIND_TAPER, r.nodes[1].kind
    assert r.width_steps and r.width_steps[0][3] == 4.0, r.width_steps

    # ---- 3. symmetric 4-way, half-width W, fillet r: setback must be exactly W + r
    W, R = 10.0, 5.0
    nodes = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (100, 0, 0)), NodeSpec(2, (-100, 0, 0)),
             NodeSpec(3, (0, 100, 0)), NodeSpec(4, (0, -100, 0))]
    edges = [_edge(i, 0, i + 1, W, W) for i in range(4)]
    r4 = solve(nodes, edges)
    assert r4.nodes[0].kind == KIND_INTERSECTION, r4.nodes[0].kind
    for i in range(4):
        got = r4.trim_start[i]
        assert abs(got - (W + R)) < 1e-6, "4-way setback %r should be W+r=%r" % (got, W + R)
    assert len(r4.nodes[0].corners) == 4
    assert len(r4.nodes[0].patch) >= 8

    # ---- 4. THE CASE A GEOMETRY-NODES AVERAGE GETS WRONG.
    # A 24 m half-width arterial crossing a 4 m half-width lane at 90 deg. The narrow lane must be
    # trimmed back by the ARTERIAL's width (24 + r), not by the mean of the two (14 + r).
    Wa, Wn, R2 = 24.0, 4.0, 3.0
    nodes = [NodeSpec(0, (0, 0, 0), fillet=R2), NodeSpec(1, (200, 0, 0)), NodeSpec(2, (-200, 0, 0)),
             NodeSpec(3, (0, 200, 0)), NodeSpec(4, (0, -200, 0))]
    edges = [_edge(0, 0, 1, Wa, Wa), _edge(1, 0, 2, Wa, Wa),
             _edge(2, 0, 3, Wn, Wn), _edge(3, 0, 4, Wn, Wn)]
    r5 = solve(nodes, edges)
    narrow, arterial = r5.trim_start[2], r5.trim_start[0]
    assert abs(narrow - (Wa + R2)) < 1e-6, "narrow lane must clear the ARTERIAL: %r" % narrow
    assert abs(arterial - (Wn + R2)) < 1e-6, "arterial only clears the narrow lane: %r" % arterial
    mean_approx = (Wa + Wn) / 2.0 + R2
    assert abs(narrow - mean_approx) > 9.0, "the mean-width approximation should be badly wrong"

    # ---- 5. a 90 deg bend at valency 2 still gets a patch (the wedge on the outside)
    nodes = [NodeSpec(0, (0, 0, 0)), NodeSpec(1, (0, 0, 0), fillet=4.0), NodeSpec(2, (0, 0, 0))]
    nodes[0].pos, nodes[1].pos, nodes[2].pos = (-60, 0, 0), (0, 0, 0), (0, 60, 0)
    edges = [_edge(0, 0, 1, 7.0, 7.0), _edge(1, 1, 2, 7.0, 7.0)]
    rb = solve(nodes, edges)
    assert rb.nodes[1].kind == KIND_BEND, rb.nodes[1].kind
    assert rb.trim_end[0] > 0.0, "a turning bend must trim, or the ribbons overlap on the inside"
    assert len(rb.nodes[1].patch) >= 4

    # ---- 6. a gore (motorway split) is NOT an intersection: all branches leave forward
    nodes = [NodeSpec(0, (-200, 0, 0)), NodeSpec(1, (0, 0, 0)),
             NodeSpec(2, (200, 20, 0)), NodeSpec(3, (200, -20, 0))]
    edges = [_edge(0, 0, 1, 12.0, 12.0), _edge(1, 1, 2, 6.0, 6.0), _edge(2, 1, 3, 6.0, 6.0)]
    rg = solve(nodes, edges)
    assert rg.nodes[1].kind == KIND_GORE, rg.nodes[1].kind

    # ...but a T-junction has the same valency and the same one-big-gap shape, and must NOT be
    # mistaken for one -- a gore builds a tangential split where a T needs a stop line.
    nodes = [NodeSpec(0, (-200, 0, 0)), NodeSpec(1, (0, 0, 0)),
             NodeSpec(2, (200, 0, 0)), NodeSpec(3, (0, 200, 0))]
    edges = [_edge(0, 0, 1, 8.0, 8.0), _edge(1, 1, 2, 8.0, 8.0), _edge(2, 1, 3, 8.0, 8.0)]
    rt = solve(nodes, edges)
    assert rt.nodes[1].kind == KIND_INTERSECTION, rt.nodes[1].kind

    # ---- 8. a SHAPE POINT is not a junction: a 90 deg corner marked NONE trims nothing and
    # builds nothing, so the ribbon stays continuous through it.
    nodes = [NodeSpec(0, (-60, 0, 0)), NodeSpec(1, (0, 0, 0), node_type=NONE, fillet=4.0),
             NodeSpec(2, (0, 60, 0))]
    edges = [_edge(0, 0, 1, 7.0, 7.0), _edge(1, 1, 2, 7.0, 7.0)]
    rn = solve(nodes, edges)
    assert rn.nodes[1].kind == KIND_NONE, rn.nodes[1].kind
    assert rn.trim_end[0] == 0.0 and rn.trim_start[1] == 0.0, "a shape point must not trim"
    assert not rn.nodes[1].patch, "a shape point must not emit a patch"

    # ---- 7. an edge too short for its own junctions is reported, never silently holed
    nodes = [NodeSpec(0, (0, 0, 0), fillet=5.0), NodeSpec(1, (12, 0, 0), fillet=5.0),
             NodeSpec(2, (0, 100, 0)), NodeSpec(3, (12, 100, 0))]
    edges = [_edge(0, 0, 1, 15.0, 15.0), _edge(1, 0, 2, 15.0, 15.0), _edge(2, 1, 3, 15.0, 15.0)]
    rs = solve(nodes, edges)
    assert rs.too_short, "a 12 m edge between two 15 m-wide junctions must be reported"
    assert rs.trim_start[0] + rs.trim_end[0] < 12.0, "trims must stay inside the edge"

    # ---- 9. grade separation: a flyover is silent, a same-grade crossing is reported
    nodes = [NodeSpec(0, (-100, 0, 0)), NodeSpec(1, (100, 0, 0)),
             NodeSpec(2, (0, -100, 0)), NodeSpec(3, (0, 100, 0))]
    edges = [_edge(0, 0, 1, 8.0, 8.0), _edge(1, 2, 3, 8.0, 8.0)]
    same = find_crossings(nodes, edges)
    assert len(same) == 1 and same[0][:2] == (0, 1), same
    assert abs(same[0][2]) < 1e-9 and abs(same[0][3]) < 1e-9, "crossing point should be the origin"

    nodes[2] = NodeSpec(2, (0, -100, 12))
    nodes[3] = NodeSpec(3, (0, 100, 12))
    assert not find_crossings(nodes, edges), "a 12 m flyover must NOT be reported as a crossing"

    # sharing a vertex is a junction, not a crossing
    nodes = [NodeSpec(0, (-100, 0, 0)), NodeSpec(1, (100, 0, 0)), NodeSpec(2, (0, 100, 0))]
    edges = [_edge(0, 0, 1, 8.0, 8.0), _edge(1, 0, 2, 8.0, 8.0)]
    assert not find_crossings(nodes, edges), "edges meeting at a node are not a crossing"

    # ---- patch integrity. A junction patch that self-intersects triangulates into overlapping
    # inverted faces and renders as a HOLE with spikes -- the defect that took 35 of the island's
    # 45 junctions. These assert the two conditions that used to break the boundary walk.
    def _patch_ok(result, label):
        for nr in result.nodes:
            if not nr.patch:
                continue
            pts = [(p[0], p[1]) for p in nr.patch]
            assert len(pts) >= 3, "%s: node %d patch has %d point(s)" % (label, nr.index, len(pts))
            assert _is_simple(pts), "%s: node %d patch self-intersects" % (label, nr.index)
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            radii = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
            med = radii[len(radii) // 2]
            if med > 1e-6:
                assert radii[-1] / med < 3.0, (
                    "%s: node %d has a spike (max %.1f vs median %.1f)"
                    % (label, nr.index, radii[-1], med))

    # a. the ordinary symmetric 4-way
    _patch_ok(r4, "4-way")

    # b. THE CLAMP CASE. Arms so short the per-chain clamp scales the setbacks well below what
    # the corners asked for. Arcs are recomputed against the clamped values, so the tangents stay
    # inside the trimmed ends instead of hanging out past them.
    W, R = 10.0, 5.0
    short = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (5, 0, 0)), NodeSpec(2, (-5, 0, 0)),
             NodeSpec(3, (0, 5, 0)), NodeSpec(4, (0, -5, 0))]
    rs = solve(short, [_edge(i, 0, i + 1, W, W) for i in range(4)])
    assert rs.too_short, "arms this short must be reported"
    _patch_ok(rs, "clamped 4-way")
    for c in rs.nodes[0].corners:
        assert c.radius <= R + 1e-6, \
            "a clamped setback must SHRINK the fillet, never grow it: %.2f > %.2f" % (c.radius, R)
        for t, ap in ((c.tangent_a, c.a), (c.tangent_b, c.b)):
            reach = _dot(_sub(t, (0.0, 0.0)), ap.dir)
            assert reach <= ap.setback + 1e-6, \
                "tangent at %.2f pokes past the trim at %.2f" % (reach, ap.setback)

    # b2. THE SIGN OF THE FILLET. A kerb return flares the asphalt OUT into the corner; its centre
    # must lie beyond the apex, not back inside the junction. Getting this backwards is what made
    # the boundary walk double back on itself.
    c0 = r4.nodes[0].corners[0]
    assert _length(_sub(c0.center, (0.0, 0.0))) > W, \
        "the kerb-return centre must sit outside the carriageway, not inside the junction"
    for t, ap in ((c0.tangent_a, c0.a), (c0.tangent_b, c0.b)):
        assert abs(_dot(_sub(t, (0.0, 0.0)), ap.dir) - ap.setback) < 1e-6, \
            "an unclamped fillet must be tangent exactly at the trim station"

    # c. THE SHALLOW-ANGLE CASE. Two boundary lines a few degrees apart meet hundreds of metres
    # away; a fillet tangent to them there is a spike, not a kerb. Such a pair sizes a setback but
    # grows no arc.
    ang = math.radians(4.0)
    narrow = [NodeSpec(0, (0, 0, 0), fillet=R),
              NodeSpec(1, (200.0, 0.0, 0)),
              NodeSpec(2, (200.0 * math.cos(ang), 200.0 * math.sin(ang), 0)),
              NodeSpec(3, (-200.0, 0.0, 0))]
    rn = solve(narrow, [_edge(i, 0, i + 1, W, W) for i in range(3)])
    _patch_ok(rn, "shallow 3-way")
    for c in rn.nodes[0].corners:
        theta = (c.b.angle - c.a.angle) % (2.0 * math.pi)
        assert theta > math.radians(11.0), "a sub-min-angle pair must not grow a fillet"

    # e. A GORE MUST NOT CUT ITS MAINLINE. Trunk arrives from the west, carries straight on east,
    # and a ramp peels off to the south-east. Only the ramp may be trimmed; trimming the through
    # pair narrows the carriageway into the merge, which is not what a merge does.
    gn = [NodeSpec(0, (0, 0, 0)), NodeSpec(1, (-300, 0, 0)), NodeSpec(2, (300, 0, 0)),
          NodeSpec(3, (280, -110, 0))]
    ge = [_edge(0, 1, 0, 8.0, 8.0), _edge(1, 0, 2, 8.0, 8.0), _edge(2, 0, 3, 4.0, 4.0)]
    rg = solve(gn, ge)
    assert rg.nodes[0].kind == KIND_GORE, "trunk + straight-on + ramp is a gore, got %s" % \
        rg.nodes[0].kind
    trunk = _gore_trunk(rg.nodes[0], math.radians(35.0))
    assert trunk is not None, "the gore's trunk must be identifiable"
    main = _gore_mainline(rg.nodes[0].approaches, trunk)
    assert main is not None and main.edge.index == 1, \
        "the through carriageway is the straight-on branch, got edge %s" % \
        (main.edge.index if main else None)
    assert trunk.setback == 0.0 and main.setback == 0.0, \
        "mainline must run through the gore uncut, got %.2f / %.2f" % (trunk.setback, main.setback)
    ramp = next(a for a in rg.nodes[0].approaches if a.edge.index == 2)
    assert ramp.setback > 0.0, "the ramp must still be set back to its nose"

    # e2. A GORE FOUR METRES FROM A CROSSING IS ONE PAD, NOT TWO. Both nodes solve, so without the
    # merge two pads land almost on top of each other and close through one another -- a bow-tie
    # of asphalt with the ramp apparently driving into the middle of the mainline. The pair must
    # end up with a single simple pad between them, and `graph_export` merges the same pair for
    # the lane graph so the routes and the road agree.
    mn = [NodeSpec(0, (0, 0, 0)), NodeSpec(1, (-300, 0, 0)), NodeSpec(2, (280, -110, 0)),
          NodeSpec(3, (4, 0, 0)), NodeSpec(4, (300, 0, 0)), NodeSpec(5, (4, 200, 0)),
          NodeSpec(6, (4, -200, 0))]
    me = [_edge(0, 1, 0, 8.0, 8.0), _edge(1, 0, 2, 4.0, 4.0), _edge(2, 0, 3, 8.0, 8.0),
          _edge(3, 3, 4, 8.0, 8.0), _edge(4, 3, 5, 8.0, 8.0), _edge(5, 3, 6, 8.0, 8.0)]
    rm = solve(mn, me)
    padded = [n for n in rm.nodes if n.index in (0, 3) and n.patch]
    assert len(padded) == 1, \
        "a gore 4 m from a crossing must leave ONE pad, got %d" % len(padded)
    pad = [(p[0], p[1]) for p in padded[0].patch]
    assert _is_simple(pad), "the merged pad self-intersects"
    assert any("merged into node" in n for r in rm.nodes for n in r.notes), \
        "the swallowed junction must say so in its notes"
    def _in_convex(p, poly):                       # the pad is a hull, so sign consistency is all
        return all(_cross(_sub(poly[(i + 1) % len(poly)], poly[i]), _sub(p, poly[i])) >= -1e-6
                   for i in range(len(poly)))
    for idx in (0, 3):
        nr = next(n for n in mn if n.index == idx)
        assert _in_convex((nr.pos[0], nr.pos[1]), pad), \
            "node %d is not covered by the merged pad" % idx
    # A crossing with a REAL road between it and the gore keeps its own pad -- the merge must key
    # on the road vanishing, not on the two being near each other in the graph.
    far = list(mn)
    far[3] = NodeSpec(3, (140, 0, 0))
    far[5] = NodeSpec(5, (140, 200, 0))
    far[6] = NodeSpec(6, (140, -200, 0))
    rf = solve(far, me)
    assert len([n for n in rf.nodes if n.index in (0, 3) and n.patch]) == 2, \
        "two junctions with a drivable road between them must keep their own pads"

    # f. THE PAD FOLLOWS THE GRADE. A junction whose arms climb must not produce a flat pad -- the
    # ribbon would float above it or sink into it at every mouth.
    W, R = 10.0, 5.0
    slope = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (100, 0, 10)),
             NodeSpec(2, (-100, 0, 0)), NodeSpec(3, (0, 100, 0)), NodeSpec(4, (0, -100, 0))]
    rgr = solve(slope, [_edge(i, 0, i + 1, W, W) for i in range(4)])
    climb = next(a for a in rgr.nodes[0].approaches if a.edge.index == 0)
    assert abs(climb.grade - 0.1) < 1e-6, "a 10 m rise over 100 m is a 0.1 grade, got %.4f" % \
        climb.grade
    expected = climb.grade * climb.setback
    zs = [p[2] for p in rgr.nodes[0].patch]
    assert abs(max(zs) - expected) < 1e-6, \
        "the climbing mouth should sit at %.3f m, pad tops out at %.3f m" % (expected, max(zs))
    assert abs(min(zs)) < 1e-6, "the level arms should stay at 0, got %.3f" % min(zs)

    # f2. THE GRADE MUST NOT BE EXTRAPOLATED PAST ITS OWN EDGE. A setback routinely outruns the
    # short resampled edge it starts on; multiplying that edge's slope by the full setback invents
    # heights that are nowhere on the road (it built 76 m tall pads on the island).
    # The short steep edge is the FIRST of a long chain (that is the only way a setback outruns
    # its edge -- the per-chain clamp caps a lone edge at 90% of its own length).
    steep = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (6, 0, 3), node_type=NONE),
             NodeSpec(2, (-100, 0, 0)), NodeSpec(3, (0, 100, 0)), NodeSpec(4, (0, -100, 0)),
             NodeSpec(5, (200, 0, 3))]
    chained = [EdgeSpec(0, 0, 1, W, W, avail=200.0, chain=0),
               EdgeSpec(4, 1, 5, W, W, avail=200.0, chain=0)]
    rex = solve(steep + [], chained + [_edge(i, 0, i + 1, W, W) for i in (1, 2, 3)])
    short = next(a for a in rex.nodes[0].approaches if a.edge.index == 0)
    assert short.setback > short.length, "test needs a setback longer than its edge"
    assert abs(short.rise() - 3.0) < 1e-6, \
        "rise must stop at the far vertex (3.00 m), got %.2f" % short.rise()
    assert max(p[2] for p in rex.nodes[0].patch) <= 3.0 + 1e-6, \
        "a pad must never rise above the highest real point on its approaches"

    # g. A SKEW CROSSING MUST NOT BUILD A CRATER. Two 16 m roads crossing at 15 degrees have their
    # apex ~136 m away; paving out to it was the island's 7,352 m2 junction. The cap bounds it,
    # reports it, and -- the part that matters -- leaves a square crossing completely alone.
    skew = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (-300, 0, 0)), NodeSpec(2, (300, 0, 0)),
            NodeSpec(3, (-290, -78, 0)), NodeSpec(4, (290, 78, 0))]
    sk_edges = [_edge(i, 0, i + 1, W, W) for i in range(4)]
    uncapped = solve(skew, sk_edges, max_setback_factor=1e9)
    capped = solve(skew, sk_edges)
    worst_un = max(a.setback for a in uncapped.nodes[0].approaches)
    worst_cap = max(a.setback for a in capped.nodes[0].approaches)
    assert worst_un > 60.0, "test needs a genuinely divergent apex, got %.1f m" % worst_un
    assert worst_cap <= 3.0 * W + 1e-6, "cap did not bind: %.1f m" % worst_cap
    assert capped.truncated, "a truncated corner must be reported, not silently applied"
    # ... and the square crossing is untouched, so the cap only ever removes craters.
    square = [NodeSpec(0, (0, 0, 0), fillet=R), NodeSpec(1, (-300, 0, 0)),
              NodeSpec(2, (300, 0, 0)), NodeSpec(3, (0, -300, 0)), NodeSpec(4, (0, 300, 0))]
    sq_edges = [_edge(i, 0, i + 1, W, W) for i in range(4)]
    sq_cap = solve(square, sq_edges)
    sq_un = solve(square, sq_edges, max_setback_factor=1e9)
    assert not sq_cap.truncated, "the cap must not touch a square crossing"
    assert abs(max(a.setback for a in sq_cap.nodes[0].approaches)
               - max(a.setback for a in sq_un.nodes[0].approaches)) < 1e-9

    # d. `_is_simple` must actually detect a bow-tie, or every assertion above is vacuous.
    assert not _is_simple([(0, 0), (10, 10), (10, 0), (0, 10)]), "_is_simple missed a bow-tie"
    assert _is_simple([(0, 0), (10, 0), (10, 10), (0, 10)]), "_is_simple rejected a square"
    hull = _convex_hull([(0, 0), (10, 10), (10, 0), (0, 10), (5, 5)])
    assert len(hull) == 4, "hull of a bow-tie plus an interior point should be the square: %s" % hull

    print("road_graph_solve self-test OK")


if __name__ == "__main__":
    self_test()
