"""graph_build.py -- turn a solved road graph into geometry: emit the swept CARRIER, then hang the
layer stack off it.

WHY PYTHON EMITS THE CARRIER INSTEAD OF THE NODE TREE SPLITTING EDGES. The obvious Geometry Nodes
route is `Split Edges -> capture edge attributes -> Mesh to Curve`, which works because the split
makes every edge its own two-point spline so the edge->point interpolation is exact. It has one
fatal limitation: it splits EVERYWHERE. A vertex the author marked as a shape point
(`NODE_NONE`) must NOT break the sweep -- the ribbon has to run through it continuously -- and no
selection on Split Edges can express "join these two edges but not those". Since the solver has to
run anyway (trims, patches, corners are not expressible in nodes at all), it also walks the graph
into CHAINS, and Python emits one polyline per chain with every number already resolved onto its
points. The node tree then never reasons about topology, only about sweeping.

WHAT A CHAIN IS. A maximal run of edges joined end-to-end through `NODE_NONE` vertices. Every
other node kind (junction, gore, bend, taper, cap) ends the chain, because those are exactly the
places the solver trimmed the ends back and a patch fills the gap. A single edge between two
junctions is a one-edge chain.

THE PARAMETRIC-OR-ASSET RULE LIVES HERE. `<role>_asset_idx >= 0` means "use the palette mesh", and
the matching parametric band is suppressed by writing its width to 0 -- so a kerb is never built
twice, and the choice is made in one Python line rather than by a branch in the node graph.

MATERIALS are left unassigned in this pass; the layer sockets exist (`Material`) and are wired,
so assigning them is a per-project decision rather than a code change.
"""
import bmesh
import bpy
from mathutils import Vector

from . import graph_assets as gas
from . import graph_attrs as ga
from . import graph_edges as gedges
from . import graph_nodes as gn
from . import graph_solve as gsolve

SUFFIX_CARRIER = "_Carrier"
SUFFIX_EDGES = "_Edges"

#: Per-point carrier attributes. FLOAT unless listed in `INT_ATTRS`.
INT_ATTRS = ("rka_ix_curb", "rka_ix_median", "rka_ix_sidewalk",
             "rka_ix_pillar", "rka_ix_rail", "rka_ix_prop")


def _point_values(attrs, offsets, gap=(0.0, 0.0)):
    """Every per-point number one edge contributes, already resolved. The single place the
    parametric-or-asset choice and the per-side kerb switch are applied.

    `gap` is a per-side 0/1 flag (left, right, in the EDGE's own frame) saying "no barrier here".

    THE BARRIER FOLLOWS THE ROAD; IT DOES NOT GET DELETED BY IT. A kerb line sits at
    `curb_off_left/right`, which `offsets_for_counts` already computes from the point's own
    (fractional) lane counts -- so where an auxiliary lane opens, the kerb line slides outboard
    with it and back in as it tapers, all by itself. The barrier is therefore ALWAYS built along
    a carriageway: down the outside of the through lanes, out around the auxiliary lane, back in.
    The only thing that opens is the ramp's OWN inner barrier, over the short length where its
    pavement actually joins the carriageway's -- which is what `gap` carries.

    This replaced keying the barrier off "how far open is the auxiliary lane": a weaving section
    holds its lane open from end to end, so that test switched the wall off for the WHOLE chain
    and the outside of the merge had no barrier at all -- the "sometimes misses an entire section
    of wall" defect."""
    ix = {r: int(attrs.get("%s_asset_idx" % r, -1)) for r in gas.ROLE_NAMES}
    curb_h = float(attrs.get("curb_height", 0.15))
    # A side with its kerb switched off, one served by a palette asset, or one a ramp is merging
    # through, contributes no parametric kerb -- width 0 rather than a second "build this?" flag
    # in the node tree.
    gap_l, gap_r = gap
    hl = curb_h if (int(attrs.get("curb_left_on", 1)) and ix["curb"] < 0
                    and gap_l < 0.5) else 0.0
    hr = curb_h if (int(attrs.get("curb_right_on", 1)) and ix["curb"] < 0
                    and gap_r < 0.5) else 0.0
    med_raised = int(attrs.get("median_type", 0)) in ga.MEDIAN_RAISED
    med_h = 0.0 if ix["median"] >= 0 else offsets["median_half"]
    wl, wr = offsets["walk_w_left"], offsets["walk_w_right"]
    cl, cr = offsets["curb_off_left"], offsets["curb_off_right"]
    return {
        "rka_halfw": offsets["paved_half"],
        "rka_shift": offsets["paved_shift"],
        "rka_med_h": med_h,
        "rka_med_z": curb_h if med_raised else 0.0,
        # A footway is centred outboard of its kerb line; `curb_off_right` is already negative, so
        # outward is a further subtraction. Both are half-widths -- the band profile spans -1..1.
        "rka_walk_cl": cl + wl / 2.0,
        "rka_walk_hl": wl / 2.0,
        "rka_walk_cr": cr - wr / 2.0,
        "rka_walk_hr": wr / 2.0,
        "rka_curb_ol": cl,
        "rka_curb_or": cr,
        "rka_curb_hl": hl,
        "rka_curb_hr": hr,
        # THE FOOTWAY'S LEVEL IS NOT THE BARRIER'S HEIGHT, even though they are usually the same
        # number. A footway sits on top of its kerb, so it read its z straight off `rka_curb_h*`
        # -- fine until something switches the barrier off for a stretch, which now happens
        # wherever a barrier stands in a merge corridor. On a motorway that is invisible (no
        # footways), but a slip road touching down on a street has both, and the pavement would
        # drop to road level for the few metres of the setback. Carried separately so the two can
        # differ where they must.
        "rka_walk_zl": curb_h if int(attrs.get("curb_left_on", 1)) else 0.0,
        "rka_walk_zr": curb_h if int(attrs.get("curb_right_on", 1)) else 0.0,
        # Kerb thickness is half its height, so a taller kerb reads as a heavier one. The box is
        # swept as a narrow band extruded down, which is why this is a half-width.
        "rka_curb_tl": hl * 0.5,
        "rka_curb_tr": hr * 0.5,
        "rka_deck_h": float(attrs.get("deck_thickness", 0.0)),
        "rka_sp_asset": max(float(attrs.get("asset_spacing", 5.0)), 0.05),
        "rka_sp_pillar": max(float(attrs.get("pillar_spacing", 0.0)), 0.05),
        "rka_pillar_on": 1.0 if float(attrs.get("pillar_spacing", 0.0)) > 0.0 else 0.0,
        "rka_pillar_w": max(float(attrs.get("pillar_width", 1.4)), 0.1),
        # ONE ROW OR THE OTHER, never both. The parametric column runs only where no kit asset has
        # been picked; picking one hands the same points to the asset row instead.
        "rka_pillar_param": (1.0 if float(attrs.get("pillar_spacing", 0.0)) > 0.0
                             and ix["pillar"] < 0 else 0.0),
        # Carried per point so `build_carrier` can turn it into a column height once it knows the
        # point's own elevation -- the one number this cannot resolve from edge attributes alone.
        "rka_ground_z": float(attrs.get("ground_z", 0.0)),
        "rka_ix_curb": ix["curb"],
        "rka_ix_median": ix["median"],
        "rka_ix_sidewalk": ix["sidewalk"],
        # A pillar row with no spacing set is off, expressed by forcing its index negative so the
        # asset layer's own selection drops it -- no extra switch anywhere.
        "rka_ix_pillar": ix["pillar"] if float(attrs.get("pillar_spacing", 0.0)) > 0.0 else -1,
        "rka_ix_rail": ix["rail"],
        "rka_ix_prop": ix["prop"],
    }


def _chain_length(pts):
    return sum((pts[i + 1][0] - pts[i][0]).length for i in range(len(pts) - 1))


def _cut_front(pts, d):
    """Drop `d` metres off the FRONT of a `[(co, values), ...]` polyline, interpolating position
    and keeping the values of the segment the new endpoint lands in."""
    if d <= 1e-9:
        return pts
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i][0], pts[i + 1][0]
        seg = (b - a).length
        if seg < 1e-12:
            continue
        if acc + seg >= d:
            return [(a.lerp(b, (d - acc) / seg), pts[i + 1][1])] + pts[i + 1:]
        acc += seg
    return []


def _trim_chain(pts, t0, t1):
    """Trim both ends by arclength, or None if the two trims consume the whole chain."""
    if t0 + t1 >= _chain_length(pts) - 1e-6:
        return None
    out = _cut_front(pts, t0)
    if len(out) < 2:
        return None
    out = _cut_front(list(reversed(out)), t1)
    if len(out) < 2:
        return None
    return list(reversed(out))


def _mirror(values):
    """The same numbers for an edge walked BACKWARDS: left and right swap, and every signed
    lateral offset negates. Without this, a chain that happens to traverse one of its edges
    against its own direction would build that edge's footway on the wrong side."""
    m = dict(values)
    for a, b in (("rka_walk_cl", "rka_walk_cr"), ("rka_walk_hl", "rka_walk_hr"),
                 ("rka_walk_zl", "rka_walk_zr"),
                 ("rka_curb_ol", "rka_curb_or"), ("rka_curb_hl", "rka_curb_hr"),
                 ("rka_curb_tl", "rka_curb_tr")):
        m[a], m[b] = values[b], values[a]
    for k in ("rka_shift", "rka_walk_cl", "rka_walk_cr", "rka_curb_ol", "rka_curb_or"):
        m[k] = -m[k]
    return m


def _chain_end_verts(bm, chain):
    """(first_vertex_index, last_vertex_index) of a chain, honouring each edge's walk direction."""
    bm.edges.ensure_lookup_table()
    e0, f0 = chain[0]
    e1, f1 = chain[-1]
    first = bm.edges[e0].verts[0 if f0 else 1].index
    last = bm.edges[e1].verts[1 if f1 else 0].index
    return first, last


def _arclengths(pts):
    cum, total = [0.0], 0.0
    for i in range(len(pts) - 1):
        total += (pts[i + 1][0] - pts[i][0]).length
        cum.append(total)
    return cum, total


def _insert_at(pts, d):
    """Insert a point at arclength `d` from the front, unless one already sits there.

    A TAPER NEEDS A VERTEX AT ITS BREAKPOINT. The carrier only has points where the graph has
    them, so a 100 m taper on a chain whose last segment is 150 m long would otherwise be smeared
    linearly across that whole segment -- the authored taper length silently ignored. Splitting
    the segment is what makes the number mean something."""
    if d <= 1e-6:
        return pts
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i][0], pts[i + 1][0]
        seg = (b - a).length
        if seg < 1e-12:
            continue
        if acc + seg >= d - 1e-6:
            if abs(acc - d) < 1e-4 or abs(acc + seg - d) < 1e-4:
                return pts                       # a vertex is already close enough
            # The new point belongs to the segment it splits, same rule `_cut_front` uses.
            return pts[:i + 1] + [(a.lerp(b, (d - acc) / seg), pts[i + 1][1])] + pts[i + 1:]
        acc += seg
    return pts


#: How long a carriageway may run between the two gores it serves before its auxiliary lane is
#: DROPPED in the middle rather than carried through. Under this, the lane between an entry and
#: the next exit is one continuous auxiliary lane -- the ordinary weaving section, and the "normal
#: 3 lane" stretch a driver sees between two ramps. Over it, carrying the lane would paint a lane
#: that exists for a kilometre with nothing using it, so it tapers shut after the entry and
#: reopens before the exit, which is what a real motorway does.
AUX_WEAVE_HOLD = 400.0

#: Shortest run a taper may be squeezed into. A lane closing over less than this is a wall, not a
#: taper (roughly a 1-in-15 slope for one 3.5 m lane), so a chain shorter than this carries the
#: lane open and lets its neighbour do the tapering.
AUX_TAPER_MIN_LENGTH = 50.0

#: How far past the gore an auxiliary lane is held at FULL width before it starts to taper -- the
#: buffer segment after the merge. Two things need it. A driver joining from a ramp needs a length
#: of full-width lane to settle in before it starts closing under them (a taper that begins at the
#: nose is a merge straight into a wedge). And the BARRIER needs it: the kerb line rides the
#: outboard edge of the auxiliary lane, so the ramp's own outer wall ends where the carriageway's
#: wall is already out at full auxiliary width -- the two meet in line instead of the mainline
#: wall diving back inboard the instant the ramp lands on it. Authored per edge as
#: `aux_buffer_length`; this is only the fallback.
AUX_MERGE_BUFFER = 40.0

#: How much of a ramp's own barrier opens AT THE NOSE, measured back from the junction vertex.
#: Its inner wall would otherwise stand on the line between the lane the ramp has become and the
#: through lane beside it -- a wall between two lanes of the same road. Only the last few metres
#: need to go: everything further back sits on the ramp's OWN edge, where it belongs, and is what
#: keeps the wedge between the two roads closed. Measured from the NODE, not from the end of the
#: ribbon: `align_ramp_ends` carries an aligned end `RAMP_OVERSHOOT` past the vertex, so a length
#: taken from the tip spent 8 of its 12 m on the far side of the junction and opened barely four
#: metres of the approach -- which is why the ramp's inner wall appeared to close again right at
#: the merge.
RAMP_WALL_OPEN = 12.0

#: Most of a chain that a merge-corridor setback may consume. A ramp that converges on the road at
#: a degree or two needs hundreds of metres to reach one lane of clearance (island node 116, at
#: 1.79 deg, asks for 122 m), and honouring that literally would strip the barrier from an entire
#: short approach. Same idiom, and the same trap, as `graph_solve.NOSE_MAX_CHAIN_FRACTION`: cap it,
#: keep a real fence behind, and PRINT which nodes hit the cap -- a ramp that near-parallel is a
#: layout question, not a geometry one.
MERGE_WALL_MAX_FRACTION = 0.5

#: Clear air left between the two barriers where they stop. THE LANE KEEPS ITS WIDTH; THE WALL
#: DOES NOT STAND A LANE AWAY. Those are different rules and the difference is 30 m of fence: a
#: barrier only has to stay out of the ramp's lane and off the ramp's own barrier, so the test is
#: a COLLISION with a small gap, not a lane-width clearance. Requiring the full lane pulled the
#: approach carriageway's wall back 37 m on the testbed and left 36 m of the mainline's own edge
#: with no barrier on it at all -- a hole in the road's fence, opened while closing a hole in the
#: ramp's. Half a metre is enough to stop two wall boxes sharing a face.
MERGE_WALL_GAP = 0.5

#: Longest diagonal that still counts as CLOSING A CORNER rather than bridging a gap. The joint
#: exists to turn one barrier into the next where the two stop beside each other; measured on the
#: island, 22 of 25 come out between 0.1 m and 8 m, which is that corner. The three that came out
#: 13-21 m were not corners at all -- the two wall ends were nowhere near each other and the
#: diagonal between them ran straight across a live carriageway. Past this, there is nothing
#: sensible to join, so nothing is built.
MERGE_JOINT_MAX = 10.0

#: How far a ramp's ribbon is carried PAST the junction, into the carriageway it merges with.
#: Its end cap is perpendicular to its own heading, so a ramp stopping exactly at the node leaves
#: a thin triangle between that diagonal cut and the mainline's cross-section -- the last sliver
#: of the merge, and the one that survived every attempt to close it with a pad. Running the ramp
#: a few metres further puts its cap inside the road, where the mainline's own surface is under
#: it. Geometry only: the lane routes still end at the junction, so nothing downstream sees a
#: route that overshoots its own node.
RAMP_OVERSHOOT = 8.0

#: How far a ribbon is carried past a GORE node where it is not trimmed. Two chains meeting there
#: end with caps perpendicular to their OWN tangents, and those differ: a carriageway whose
#: auxiliary lane is tapering has a centreline drifting sideways, so its cap is tilted a degree or
#: so against its neighbour's square one. The sliver between two caps that are not parallel is a
#: triangle of bare ground -- the last hole at the merge, and one no pad can close reliably
#: because its shape depends on how fast the lane is tapering. Overlapping them removes the
#: question, the same way it did for the ramp.
JOIN_OVERSHOOT = 2.0


def _walk_counts(attrs, forward):
    """`(through_fwd, through_bwd, aux_fwd, aux_bwd)` for one edge in the CHAIN'S walk frame.

    `lanes_fwd`/`aux_lanes_left` are expressed against the edge's own v0 -> v1 direction, and a
    chain may walk an edge backwards -- so every count is read through this one flip rather than
    each caller remembering to do it."""
    f = int(attrs.get("lanes_fwd", 2))
    b = int(attrs.get("lanes_bwd", 2))
    af = int(attrs.get("aux_lanes_left", 0))
    ab = int(attrs.get("aux_lanes_right", 0))
    return (f, b, af, ab) if forward else (b, f, ab, af)


def _keyframe_at(keys, d):
    """Linear interpolation of `[(distance, value), ...]` (sorted) at arclength `d`."""
    if d <= keys[0][0]:
        return keys[0][1]
    for i in range(1, len(keys)):
        d0, v0 = keys[i - 1]
        d1, v1 = keys[i]
        if d <= d1:
            span = d1 - d0
            return v1 if span < 1e-9 else v0 + (v1 - v0) * (d - d0) / span
    return keys[-1][1]


def lane_transition_keys(dists, counts, lengths, total):
    """Where a chain's THROUGH lane count changes, and over what distance it gets there.

    Returns `([(distance, lane count), ...], [extra breakpoint distances])`.

    A LANE COUNT CHANGES OVER A DISTANCE, NOT AT A VERTEX. Two adjacent edges stamped 2 and 4
    lanes used to step the ribbon's width at the vertex between them -- a wall across half the
    carriageway, which is the "the mesh just jumps/compresses there" defect. A real road opens one
    lane at a time over a taper each (`lane_transition_length`, ~60 m at expressway speed), so 2 ->
    4 is 2 -> 3 -> 4 with a whole-lane state in between, and the breakpoints returned here put a
    vertex at every one of those states so the geometry and the lane markings agree about where
    each new lane begins.

    The window is centred on the vertex and clipped so two nearby transitions cannot overlap (they
    would otherwise interpolate through each other and neither would reach its whole-lane state).
    """
    keys = [(0.0, float(counts[0]))]
    extra = []
    changes = [i for i in range(len(counts) - 1) if counts[i] != counts[i + 1]]
    for pos, i in enumerate(changes):
        d = dists[i]
        c0, c1 = float(counts[i]), float(counts[i + 1])
        steps = abs(c1 - c0)
        half = 0.5 * lengths[i] * steps
        # Clipped to half the gap to the neighbouring transition (so two windows cannot overlap
        # and interpolate through each other) and to the chain's own ends.
        lim_prev = d if pos == 0 else (d - dists[changes[pos - 1]]) * 0.5
        lim_next = (total - d) if pos + 1 == len(changes) \
            else (dists[changes[pos + 1]] - d) * 0.5
        half = max(min(half, lim_prev, lim_next), 0.0)
        if half <= 1e-6:
            keys.append((d, c0))
            keys.append((d, c1))
            continue
        keys.append((d - half, c0))
        keys.append((d + half, c1))
        extra.extend([d - half, d + half])
        # A vertex at each whole-lane state inside the window: 2 -> 4 gets one at the 3-lane point.
        n_steps = int(round(steps))
        for k in range(1, n_steps):
            extra.append(d - half + 2.0 * half * k / n_steps)
    keys.append((total, float(counts[-1])))
    keys.sort(key=lambda kv: kv[0])
    return keys, extra


def aux_anchors(ends, gore_nodes, services, chain_id):
    """`(served_at_start, served_at_end)` per side: `{'F': (bool, bool), 'B': (bool, bool)}`.

    `services` is `graph_solve.ramp_services`' answer -- the SAME derivation `auto_aux_lanes`
    stamped the lane from, so the lane is full width at exactly the end whose ramp it serves.
    Without a services map (an authored graph solved on its own, or a caller that has none) it
    falls back to "a gore end serves whichever sides carry an aux lane", which is what this did
    before and is right whenever only one side does."""
    out = {'F': [False, False], 'B': [False, False]}
    for which, node in enumerate(ends):
        groups = None if services is None else services.get((node, chain_id))
        if groups is not None:
            # A SERVICE ANCHORS THE TAPER WHEREVER IT IS, gore or not. An acceleration lane at a
            # slip road's touchdown is full width at the junction and closes going away from it,
            # exactly like one at a motorway gore; keying the anchor off the node KIND instead
            # left those lanes at constant width for the whole street.
            for fwd_group in groups:
                out['F' if fwd_group else 'B'][which] = True
        elif node in gore_nodes:
            # A gore we have no service for (no identifiable trunk): both sides, as before.
            out['F'][which] = True
            out['B'][which] = True
    return {k: tuple(v) for k, v in out.items()}


def aux_scale_keys(anchor, tap_s, tap_e, total, weave_hold=AUX_WEAVE_HOLD,
                   buf_s=0.0, buf_e=0.0):
    """`([(distance, openness 0..1), ...], [breakpoints])` for ONE side's auxiliary lane.

    The taper is anchored AT THE GORE, because that is where the extra lane is actually used: the
    ramp attaches there, so the lane must be at full width there and close going away. Between the
    gore and the taper sits the BUFFER (`buf_*`, `AUX_MERGE_BUFFER`): a stretch where the lane is
    still at full width, so the merge is `gore -> buffer -> taper` rather than `gore -> taper`.
    That is the extra segment after the merge -- room for a joining driver, and room for the
    barrier riding the lane's outboard edge to run in line with the ramp's own wall before it
    comes back in.

    A side served at BOTH ends is a weaving section and stays open the whole way when the gap
    between the two tapers is short enough to be one lane (`AUX_WEAVE_HOLD`) -- the "normal 3
    lane" stretch between an entry and the next exit -- and otherwise closes in the middle and
    reopens, which is what a real motorway does over a kilometre.

    A side served at NEITHER end keeps its authored lane at constant width (an aux stamped by hand
    on a road with no gore), and so does a zero-length taper: a taper that takes no distance
    cannot close the lane, so the lane is simply there."""
    at_s, at_e = anchor
    if not at_s and not at_e:
        return [(0.0, 1.0), (total, 1.0)], []
    tap_s = float(tap_s) if at_s else 0.0
    tap_e = float(tap_e) if at_e else 0.0
    buf_s = max(float(buf_s), 0.0) if at_s else 0.0
    buf_e = max(float(buf_e), 0.0) if at_e else 0.0
    if (at_s and tap_s <= 1e-6) or (at_e and tap_e <= 1e-6):
        return [(0.0, 1.0), (total, 1.0)], []
    # THE BUFFER YIELDS TO THE TAPER when there is not room for both: a lane that steps shut is
    # worse than one that never gets its settling length, so the buffer is trimmed to whatever is
    # left after the tapers have their room (and both ends share what is left evenly).
    room = max(total - tap_s - tap_e, 0.0)
    if buf_s + buf_e > room:
        scale = 0.0 if buf_s + buf_e <= 1e-9 else room / (buf_s + buf_e)
        buf_s, buf_e = buf_s * scale, buf_e * scale
    # A CHAIN SHORTER THAN ITS OWN TAPER SHORTENS THE TAPER -- down to a floor. Squeezing a 90 m
    # taper into a 5 m scrap of road between two junctions is not a taper, it is a step (measured
    # on the island: a 1.62 m width change over 4.8 m, a 1-in-3 slope across half a carriageway),
    # so below `AUX_TAPER_MIN_LENGTH` the lane simply stays open and lets the neighbouring chain
    # taper it where there is room. Above it, using the room there IS beats holding the lane open
    # all the way to the next junction, which lands a whole-lane width step on that junction.
    tap_s = min(tap_s, total)
    tap_e = min(tap_e, total)
    if ((at_s and tap_s < AUX_TAPER_MIN_LENGTH) or (at_e and tap_e < AUX_TAPER_MIN_LENGTH)) \
            and total < AUX_TAPER_MIN_LENGTH:
        return [(0.0, 1.0), (total, 1.0)], []
    if at_s and at_e and tap_s + tap_e >= total - 1e-6:
        return [(0.0, 1.0), (total, 1.0)], []
    if at_s and at_e and total - tap_s - tap_e <= weave_hold:
        return [(0.0, 1.0), (total, 1.0)], []
    keys, extra = [(0.0, 1.0 if at_s else 0.0)], []
    if at_s:
        if buf_s > 1e-6:
            keys.append((buf_s, 1.0))
            extra.append(buf_s)
        keys.append((buf_s + tap_s, 0.0))
        extra.append(buf_s + tap_s)
    if at_e:
        keys.append((total - buf_e - tap_e, 0.0))
        extra.append(total - buf_e - tap_e)
        if buf_e > 1e-6:
            keys.append((total - buf_e, 1.0))
            extra.append(total - buf_e)
    keys.append((total, 1.0 if at_e else 0.0))
    keys.sort(key=lambda kv: kv[0])
    return keys, extra


#: Over how much of a ramp its end is eased onto the auxiliary lane. Long enough that the shift
#: is a gentle drift rather than a kink (a lane's width over 120 m is about 1 in 34, gentler than
#: any taper the kit builds), and clamped to under half the chain so the far end of the ramp -- the
#: part the author placed -- is never moved.
ALIGN_BLEND_LENGTH = 120.0


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def align_ramp_ends(trimmed, ends, chain_id, aligns, overshoot=0.0):
    """Ease a ramp's end sideways onto the auxiliary lane it becomes.

    A ramp's polyline ends at the junction VERTEX, which sits on the mainline's centreline -- so
    swept as authored, a ramp's last stretch runs diagonally across the carriageway it is joining.
    The lane it actually becomes is one lane's offset out from that centreline, and this puts the
    ramp there: full displacement at the junction, easing back to nothing over `ALIGN_BLEND_LENGTH`
    so the rest of the ramp is exactly as authored and stays adjustable by hand.

    THIS REPLACES CUTTING THE RAMP SHORT. The nose setback that used to keep the ramp clear of the
    road was measured from the angle it came in at -- 46 m at the island's 6-degree entries, so 46 m
    of ramp was never built and the mesh visibly stopped in mid-air short of the junction. Moving
    the end is the same fix without the hole, and it is what a merge looks like from above: the
    ramp runs in alongside and becomes the lane.

    Shared by the carrier and the lane export, like every other geometry decision here, so the
    swept asphalt and the routes drawn on it cannot disagree about where the ramp is."""
    if not aligns:
        return trimmed
    out = list(trimmed)
    for which, node in enumerate(ends):
        al = aligns.get((node, chain_id))
        if al is None:
            continue
        # RE-MEASURED EACH TIME: the overshoot below appends a point, so arclengths taken once at
        # the top go stale for the second end (and index past the list).
        dists, total = _arclengths(out)
        target, axis, sign = al
        if target <= 1e-6:
            continue
        blend = min(ALIGN_BLEND_LENGTH, total * 0.45)
        if blend <= 1e-6:
            continue
        # LEFT of the host stream's own direction of travel, which is the side the kerb is on
        # under keep-left and therefore the side every auxiliary lane opens at.
        off = (-axis[1] * target * sign, axis[0] * target * sign)
        moved = []
        for i, (co, payload) in enumerate(out):
            d = dists[i] if which == 0 else (total - dists[i])
            f = _smoothstep(1.0 - d / blend) if d < blend else 0.0
            if f <= 0.0:
                moved.append((co, payload))
            else:
                p = co.copy()
                p.x += off[0] * f
                p.y += off[1] * f
                moved.append((p, payload))
        out = moved
        if overshoot > 1e-6 and len(out) >= 2:
            # Carry the ribbon past the junction along its own final heading.
            i, j = (0, 1) if which == 0 else (-1, -2)
            tip, prev = out[i][0], out[j][0]
            d = tip - prev
            if d.length > 1e-9:
                d = d.normalized() * overshoot
                ext = (tip + d, out[i][1])
                out = ([ext] + out) if which == 0 else (out + [ext])
    return out


def _half_at(pts, i):
    """The carriageway half-width and kerb half-thickness of one staged point, from its own edge
    attributes. Cheap on purpose: the corridor derivation runs BEFORE `chain_lane_counts`, so the
    tapered per-point counts do not exist yet -- and near a gore they do not need to, because the
    arm that carries the auxiliary lane is by definition not the arm being measured here."""
    attrs, forward = pts[i][1]
    off = gsolve.offsets_for_counts(attrs, 'LEFT')
    curb_h = float(attrs.get("curb_height", 0.15))
    return off["paved_half"], curb_h * 0.5


def _on_a_road(staged, p, skip, z_tol=3.0):
    """Does world point `p` lie on any staged chain's asphalt, other than the ones in `skip`?

    The joint is the one piece the kit places by construction rather than by sweeping a road, so
    it is the one piece that can land somewhere nobody asked it to. Checking it against the same
    definition of "asphalt" the corridor rule uses keeps the generator honest: it refuses to build
    a barrier across a carriageway instead of relying on someone spotting it in the viewport."""
    for chain_id, _ends, pts in staged:
        if chain_id in skip or len(pts) < 2:
            continue
        for k in range(len(pts) - 1):
            a, b = pts[k][0], pts[k + 1][0]
            if abs((a.z + b.z) * 0.5 - p.z) > z_tol:
                continue                       # a flyover crosses in plan, not in space
            t = b - a
            t.z = 0.0
            if t.length < 1e-9:
                continue
            t = t.normalized()
            n = Vector((-t.y, t.x, 0.0))
            d = p - a
            along = d.dot(t)
            if along < 0.0 or along > (b - a).length:
                continue
            off = gsolve.offsets_for_counts(pts[k][1][0], 'LEFT')
            shift, half = off["paved_shift"], off["paved_half"]
            if not pts[k][1][1]:
                shift = -shift
            lat = d.dot(n)
            if shift - half + MERGE_WALL_GAP < lat < shift + half - MERGE_WALL_GAP:
                return True
    return False


def _wall_point(pts, which, dist, side):
    """Where one chain's barrier ENDS, in world space: the point `dist` along the ribbon from end
    `which`, pushed out to that side's kerb line. `side` is in the CHAIN'S walk frame, the frame
    every lateral number is expressed in before `_mirror` turns it into geometry."""
    # INTERPOLATED WITHIN THE SEGMENT, never snapped to a vertex. A trunk resampled every 200 m
    # would otherwise put a 15 m setback's joint at the 200 m mark -- measured, a joint that flew
    # 185 m up the road and across it.
    idx = list(range(len(pts))) if which == 0 else list(range(len(pts) - 1, -1, -1))
    acc, k, j, frac = 0.0, idx[-1], idx[-2] if len(idx) > 1 else idx[-1], 1.0
    for n in range(len(idx) - 1):
        a, b = idx[n], idx[n + 1]
        seg = (pts[b][0] - pts[a][0]).length
        if seg < 1e-9:
            continue
        if acc + seg >= dist - 1e-6:
            k, j, frac = b, a, (dist - acc) / seg
            break
        acc += seg
    # THE CANONICAL WALK DIRECTION, not the direction this walk happens to be going. `side` was
    # decided in the chain's own frame (lower index -> higher index); measuring the frame from an
    # end-inward tangent instead flips left and right for any chain entered at its far end, which
    # put the joint on the wrong kerb and sent it straight across the carriageway.
    lo, hi = (j, k) if j < k else (k, j)
    t = pts[hi][0] - pts[lo][0]
    if t.length < 1e-9:
        return None
    co = pts[j][0].lerp(pts[k][0], max(min(frac, 1.0), 0.0))
    t = t.normalized()
    off = gsolve.offsets_for_counts(pts[k][1][0], 'LEFT')
    # `curb_off_*` is written against the EDGE's own frame; a chain walking that edge backwards
    # sees the sides swapped, which is the same flip `_resolve_points` applies before `_mirror`.
    forward = pts[k][1][1]
    ol, orr = off["curb_off_left"], off["curb_off_right"]
    if not forward:
        ol, orr = -orr, -ol
    return co + Vector((-t.y, t.x, 0.0)) * (ol if side == 'L' else orr)


def merge_corridor_ends(staged, node_co, aligns, hosts):
    """`{(node, chain id): {"which": 0|1, "side": 'L'|'R', "setback": m, "target_half": m}}` --
    where the barrier standing IN a merge corridor has to stop, derived per ramp.

    THE CORRIDOR IS THE GAP BETWEEN TWO ROADS, so no single authored number can describe it. A
    ramp converging at 64 degrees clears the carriageway a few metres before the nose; one
    converging at 1.8 degrees does not clear it for a hundred. Measured across the island's served
    ramps that is a 30x spread, so any constant is right for one merge and wrong for the rest --
    which is exactly what "the knob does not seem to do anything" looks like from the outside. The
    distance is therefore MEASURED, from the two polylines as they will actually be swept (after
    `align_ramp_ends`, which is what moves the ramp onto the lane).

    IT IS A COLLISION TEST, NOT A CLEARANCE ONE (`MERGE_WALL_GAP`). The lane keeps its full width;
    the barrier does not have to stand a lane away from it. Requiring the whole lane pulled the
    approach carriageway's wall back far enough to leave 36 m of the mainline's OWN edge unfenced
    -- a hole in the road's fence, opened while closing one in the ramp's.

    WHICH BARRIER STOPS. Three arms meet at a merge: the ramp, the carriageway that gains the
    auxiliary lane (the HOST -- departing at an entry, arriving at an exit), and the remaining one,
    which is the carriageway the ramp runs ALONGSIDE on its way in. Only that last arm's
    merge-side barrier is in the corridor; the host's is outboard of the ramp, and the ramp's own
    inner wall sits on the ramp's own edge and blocks nothing. So the answer is found by
    elimination -- everything at the node that is neither the ramp's chain nor `hosts`'.

    `target_half` rides along because it is the same lookup: the half-width the ramp must narrow
    to so that its outer wall arrives in line with the carriageway's rather than a lane's fraction
    proud of it."""
    at_node, by_id, joints, refused = {}, {}, [], []
    for chain_id, ends, pts in staged:
        by_id[chain_id] = (ends, pts)
        for which, node in enumerate(ends):
            at_node.setdefault(node, []).append((chain_id, which))
    out, capped = {}, []
    for (node, ramp_chain), (_target, axis, _sign) in aligns.items():
        if ramp_chain not in by_id or node not in node_co:
            continue
        host = hosts.get((node, ramp_chain))
        origin = node_co[node]
        ax = Vector((axis[0], axis[1], 0.0))
        if ax.length < 1e-9:
            continue
        ax.normalize()
        rpts = by_id[ramp_chain][1]
        _rh, ramp_thick = _half_at(rpts, 0)
        # The ramp seen in the host stream's own frame: how far along it each point sits, and how
        # far off to the side its NEAR EDGE is. `axis` is the same vector `align_ramp_ends`
        # displaced the ramp along, so this costs no new frame maths and cannot disagree with the
        # alignment. The near EDGE, not the centreline: a one-way ramp's ribbon hangs entirely to
        # one side of its polyline (`paved_shift`), so the centreline is a lane's width away from
        # where the asphalt actually stops.
        prof = []
        for k in range(len(rpts)):
            co = rpts[k][0]
            nb = rpts[k + 1][0] if k + 1 < len(rpts) else rpts[k - 1][0]
            t = (nb - co) if k + 1 < len(rpts) else (co - nb)
            if t.length < 1e-9:
                continue
            t = t.normalized()
            off = gsolve.offsets_for_counts(rpts[k][1][0], 'LEFT')
            lat = None
            for edge_off in (off["paved_shift"] + off["paved_half"],
                             off["paved_shift"] - off["paved_half"]):
                e = co + Vector((-t.y, t.x, 0.0)) * edge_off
                d = e - origin
                l = abs(d.x * ax.y - d.y * ax.x)
                lat = l if lat is None else min(lat, l)
            d = co - origin
            prof.append((d.dot(ax), lat))
        for chain_id, which in at_node.get(node, ()):
            if chain_id == ramp_chain or chain_id == host:
                continue
            ends, pts = by_id[chain_id]
            own_half, own_thick = _half_at(pts, 0 if which == 0 else -1)
            need = own_half + own_thick + ramp_thick + MERGE_WALL_GAP
            # THE FIRST STATION THAT CLEARS, walking away from the node -- not the last. Nearer
            # the node the barrier would stand in the corridor; further out the roads only
            # separate more, so the crossing point is the whole answer. Interpolated across the
            # segment it falls in, because a ramp polyline is sampled every hundred metres or so
            # and snapping to a vertex would round a 35 m setback up to 110.
            reach = None
            for k in range(len(prof) - 1):
                (s0, l0), (s1, l1) = prof[k], prof[k + 1]
                if (l0 - need) * (l1 - need) > 0.0 or abs(l1 - l0) < 1e-9:
                    continue
                cross = abs(s0 + (s1 - s0) * (need - l0) / (l1 - l0))
                reach = cross if reach is None else min(reach, cross)
            if reach is None:
                # Never crosses: either clear everywhere (no corridor, nothing to do) or clear
                # nowhere, in which case the cap below decides how much fence can go.
                if prof and prof[0][1] >= need:
                    continue
                reach = max((abs(st) for st, _l in prof), default=0.0)
            if reach <= 1e-6:
                continue
            _d, total = _arclengths(pts)
            cap = total * MERGE_WALL_MAX_FRACTION
            if reach > cap:
                capped.append((node, round(reach, 1), round(cap, 1)))
                reach = cap
            # Which side of THIS chain the ramp is on, in the chain's own walk frame at that end.
            i, j = (0, 1) if which == 0 else (-1, -2)
            t = pts[i][0] - pts[j][0]
            if which == 0:
                t = -t
            if t.length < 1e-9:
                continue
            t.normalize()
            probe = None
            for co, _payload in rpts:
                if (co - pts[i][0]).length > 1e-6:
                    probe = co
                    break
            if probe is None:
                continue
            rel = probe - pts[i][0]
            side = 'L' if (t.x * rel.y - t.y * rel.x) > 0.0 else 'R'
            prev = out.get((node, chain_id))
            if prev is None or prev["setback"] < reach:
                out[(node, chain_id)] = {"which": which, "side": side, "setback": reach,
                                         "target_half": 0.0}
            # THE RAMP'S INNER WALL STOPS AT THE SAME PLACE, expressed as arclength along the ramp
            # rather than along the axis. Both barriers bound the SAME wedge, so one station ends
            # them both -- and it is a derivation, where the fixed 12 m it replaces was a guess
            # that happened to be right at one angle. `RAMP_WALL_OPEN` stays as the fallback for a
            # ramp with no identifiable approach arm.
            rwhich = 0 if by_id[ramp_chain][0][0] == node else 1
            ridx = list(range(len(rpts))) if rwhich == 0 else list(range(len(rpts) - 1, -1, -1))
            racc, rstop = 0.0, None
            for n in range(len(ridx) - 1):
                a, b = ridx[n], ridx[n + 1]
                sa = abs((rpts[a][0] - origin).dot(ax))
                sb = abs((rpts[b][0] - origin).dot(ax))
                seg = (rpts[b][0] - rpts[a][0]).length
                if sb >= reach - 1e-6:
                    f = 0.0 if abs(sb - sa) < 1e-9 else (reach - sa) / (sb - sa)
                    rstop = racc + seg * max(min(f, 1.0), 0.0)
                    break
                racc += seg
            if rstop is not None:
                rrec = out.setdefault((node, ramp_chain),
                                      {"which": rwhich, "side": 'L', "setback": 0.0,
                                       "target_half": 0.0})
                rrec["inner_stop"] = rstop
            # THE ANGLED PIECE THAT CLOSES THE CORNER. Two barriers that simply stop leave the
            # wedge between the roads open at its wide end and the fence with two loose ends; the
            # kit already answers this shape at a junction, where `graph_solve.build_corner_mesh`
            # turns one kerb line into the next. Same answer here, and the same mechanism: a short
            # polyline carrying the kerb attributes, swept by the same layer stack.
            jm = _wall_point(pts, which, reach, side)
            jr = None if rstop is None else _wall_point(rpts, rwhich, rstop, 'R')
            if jm is not None and jr is not None \
                    and 1e-3 < (jm - jr).length <= MERGE_JOINT_MAX \
                    and not any(_on_a_road(staged, jm.lerp(jr, f), (chain_id, ramp_chain))
                                for f in (0.0, 0.25, 0.5, 0.75, 1.0)):
                joints.append((jm, jr,
                               max(float(pts[0][1][0].get("curb_height", 0.15)),
                                   float(rpts[0][1][0].get("curb_height", 0.15)))))
            elif jm is not None and jr is not None:
                refused.append(node)
        # The ramp's own end learns the width it has to arrive at, from the lane it becomes.
        if host is not None and host in by_id:
            hends, hpts = by_id[host]
            hi = 0 if hends[0] == node else -1
            hattrs = hpts[hi][1][0]
            n_aux = max(int(hattrs.get("aux_lanes_left", 0)),
                        int(hattrs.get("aux_lanes_right", 0)))
            if n_aux:
                tgt = n_aux * float(hattrs.get("lane_width", 3.5)) * 0.5
                rwhich = 0 if by_id[ramp_chain][0][0] == node else 1
                rec = out.setdefault((node, ramp_chain),
                                     {"which": rwhich, "side": 'L', "setback": 0.0,
                                      "target_half": 0.0})
                rec["target_half"] = tgt
    if out:
        # WHAT THE DERIVATION DECIDED, in one line. The setback is the number an author would
        # otherwise have to guess at, and its spread is the argument for deriving it: printing the
        # range makes both visible without opening the blend.
        got = sorted(r["setback"] for r in out.values() if r["setback"] > 1e-6)
        if got:
            print("[graph_build] %d merge corridor(s): approach barrier pulled back %.0f-%.0f m "
                  "(median %.0f) to clear the ramp, joined to the ramp's own wall"
                  % (len(got), got[0], got[-1], got[len(got) // 2]))
    if refused:
        print("[graph_build] %d merge joint(s) not built -- the two barriers do not stop beside "
              "each other, so the piece that would close the corner would cross a carriageway "
              "(node %s)" % (len(refused), ", ".join(str(n) for n in sorted(set(refused))[:6])))
    if capped:
        print("[graph_build] %d merge(s) too shallow to clear the ramp within half their approach; "
              "barrier shortened as far as the cap allows: %s"
              % (len(capped), ", ".join("node %d wanted %.0f m, capped at %.0f" % c
                                        for c in capped[:5])))
    return out, joints


def chain_lane_counts(trimmed, ends, gore_nodes, services=None, chain_id=None,
                      extra_breaks=()):
    """`(trimmed with breakpoints, [(lanes_fwd, lanes_bwd), ...], [(open_f, open_b), ...])`,
    counts and openness both in the CHAIN'S walk frame. `open_*` is 0..1, how far that side's
    auxiliary lane is open, before the lane count is multiplied by it. (The barrier does NOT read
    it -- see `_point_values`; it is kept because it says where a chain is at full auxiliary width
    and callers that want to know that should not have to re-derive the keyframes.)

    THE ONE PLACE A CHAIN'S WIDTH VARIES. An opening auxiliary lane and a carriageway stepping
    from 2 lanes to 4 are the same thing -- a lane count that is a function of arclength -- so
    both are resolved here, into one per-point pair of (possibly fractional) counts that
    `graph_solve.offsets_for_counts` turns into geometry. The CARRIER and the LANE EXPORT both
    call this, which is what stops the swept asphalt and the routes drawn on it from disagreeing:
    a route computed against the untapered width sits off the road for the whole taper, which is a
    car driving on air."""
    walk = [_walk_counts(a, f) for _co, (a, f) in trimmed]
    dists, total = _arclengths(trimmed)
    trans_len = [max(float(a.get("lane_transition_length", 60.0)), 0.0)
                 for _co, (a, _f) in trimmed]
    keys_f, extra_f = lane_transition_keys(dists, [w[0] for w in walk], trans_len, total)
    keys_b, extra_b = lane_transition_keys(dists, [w[1] for w in walk], trans_len, total)

    anchors = aux_anchors(ends, gore_nodes, services, chain_id)
    # THE TAPER IS A CHAIN-LEVEL FACT, not a per-point one: its LENGTH comes from the edge at the
    # gore end (one ramp opens over one distance -- letting each edge along the chain contribute
    # its own would kink the ribbon halfway up the taper) and its lane COUNT is the widest stamped
    # anywhere on the chain, so a partly-stamped chain opens one lane rather than flickering.
    tap = [float(trimmed[0][1][0].get("aux_taper_length", 0.0)),
           float(trimmed[-1][1][0].get("aux_taper_length", 0.0))]
    buf = [float(trimmed[0][1][0].get("aux_buffer_length", AUX_MERGE_BUFFER)),
           float(trimmed[-1][1][0].get("aux_buffer_length", AUX_MERGE_BUFFER))]
    aux_keys, extra_a = {}, []
    for si, side in enumerate(('F', 'B')):
        anchor = anchors[side]
        n_aux = max([w[2 + si] for w in walk], default=0)
        if not n_aux:
            aux_keys[side] = ([(0.0, 0.0), (total, 0.0)], 0)
            continue
        k, ex = aux_scale_keys(anchor, tap[0], tap[1], total,
                               buf_s=buf[0], buf_e=buf[1])
        aux_keys[side] = (k, n_aux)
        extra_a.extend(ex)

    for d in sorted(set(round(x, 4) for x in (extra_f + extra_b + extra_a
                                                     + list(extra_breaks)))):
        if 1e-6 < d < total - 1e-6:
            trimmed = _insert_at(trimmed, d)
    dists, total2 = _arclengths(trimmed)
    counts, opens = [], []
    for d in dists:
        of = _keyframe_at(aux_keys['F'][0], d) if aux_keys['F'][1] else 0.0
        ob = _keyframe_at(aux_keys['B'][0], d) if aux_keys['B'][1] else 0.0
        counts.append((_keyframe_at(keys_f, d) + aux_keys['F'][1] * of,
                       _keyframe_at(keys_b, d) + aux_keys['B'][1] * ob))
        opens.append((of, ob))
    return trimmed, counts, opens


def _inner_stop(merges, node, chain_id):
    """How much of a ramp's INNER wall opens at the nose. The corridor derivation's answer when it
    has one -- both barriers bound the same wedge, so one station ends them both -- and
    `RAMP_WALL_OPEN` when it does not (a ramp with no identifiable approach arm to measure
    against, e.g. a touchdown where every other arm is a through road)."""
    rec = (merges or {}).get((node, chain_id))
    got = None if rec is None else rec.get("inner_stop")
    return RAMP_WALL_OPEN if got is None else max(got, 0.0)


def _resolve_points(trimmed, ends, gore_nodes, services=None, chain_id=None,
                    aligns=None, merges=None):
    """Turn `[(co, (attrs, forward)), ...]` into `[(co, point_values), ...]`, with every lane count
    resolved per point by `chain_lane_counts` -- the opening auxiliary lane AND any lane the road
    gains or drops along the way.

    Counts come back in the CHAIN'S walk frame and are flipped back into each edge's own frame
    before the profile is built, because `lanes_fwd`/`lanes_bwd` are defined against the edge's
    v0 -> v1 direction; `_mirror` then handles the geometric left/right for a backwards walk, the
    same two-step this has always done."""
    # A WALL THAT FADES IS STILL A WALL, AND LOOKS LIKE NEITHER. Height is a per-point value, so
    # a point with the barrier off next to one with it on ramps the height between them -- across
    # a sparse ramp polyline that is tens of metres of steadily shrinking wall, which reads as the
    # barrier "almost not existing" rather than as an opening. Asking for a vertex a metre either
    # side of the ramp's own opening makes it end instead: full height, then nothing.
    breaks = []
    _d0, total0 = _arclengths(trimmed)
    for which, node in enumerate(ends):
        cuts = []
        if aligns and (node, chain_id) in aligns:
            # From the NODE, so the overshoot past it does not count against the opening.
            cuts.append(_inner_stop(merges, node, chain_id) + RAMP_OVERSHOOT)
            cuts.append(RAMP_OVERSHOOT)
        rec = (merges or {}).get((node, chain_id))
        if rec is not None and rec["setback"] > 1e-6:
            cuts.append(rec["setback"])
        for cut in cuts:
            for off in (cut - 1.0, cut + 1.0):
                if off > 0.0:
                    breaks.append(off if which == 0 else max(total0 - off, 0.0))
    trimmed, counts, _opens = chain_lane_counts(trimmed, ends, gore_nodes, services, chain_id,
                                                breaks)
    # ONE THING, AND ONLY ONE THING, TAKES A BARRIER AWAY: a RAMP's own inner wall, over the last
    # `RAMP_WALL_OPEN` metres before it lands. That wall would otherwise stand between the ramp
    # and the lane it is merging into. The carriageway's own barrier is never removed -- it rides
    # the kerb line, which `offsets_for_counts` has already pushed outboard by the width of the
    # auxiliary lane, so it wraps AROUND the merge (`|| i1 | i2  i3 ||`) instead of vanishing at
    # it. That is the whole fix for "the outside wall does not connect between the merge and the
    # lane tapering back", and it is why nothing here reads lane openness any more.
    gaps = [(0.0, 0.0)] * len(trimmed)
    dists, total = _arclengths(trimmed)
    for which, node in enumerate(ends):
        for i, d in enumerate(dists):
            near = d if which == 0 else total - d
            if aligns and (node, chain_id) in aligns \
                    and near <= _inner_stop(merges, node, chain_id) + RAMP_OVERSHOOT:
                gl, gr = gaps[i]
                # ONLY THE INNER WALL, AND ONLY AT THE NOSE. The mainline lies to the RIGHT of a
                # ramp merging into it -- the auxiliary lane opens at the stream's kerb, which is
                # its left under keep-left, so the ramp sits outboard of that and the road is on
                # its right. A ramp is drawn in the direction it is driven, so the walk frame IS
                # the travel frame and "right" is the backward group's side. Opening BOTH walls
                # for the whole nose (the first cut of this) took the OUTER barrier away too, and
                # then nothing wrapped the outside of the merge at all -- the wall vanished there.
                gaps[i] = (gl, 1.0)
                # PAST THE NODE, NEITHER WALL. The overshoot exists to put the ramp's end cap
                # inside the carriageway so the two surfaces overlap instead of abutting -- it is
                # geometry, and only geometry. Its OUTER wall, swept on a ribbon still angling in
                # at several degrees, walks diagonally across the auxiliary lane it has just
                # become: measured here, 1.4 m onto the asphalt by the end of the overshoot. From
                # the node on, the carriageway's own barrier is the outer wall.
                if near <= RAMP_OVERSHOOT:
                    gaps[i] = (1.0, 1.0)
            # THE BARRIER STANDING IN THE CORRIDOR STOPS. Everything about where is decided by
            # `merge_corridor_ends` from the two roads' geometry; all that is left here is to
            # apply it to the side it named, in this chain's own walk frame.
            rec = (merges or {}).get((node, chain_id))
            if rec is not None and rec["setback"] > 1e-6 and near <= rec["setback"]:
                gl, gr = gaps[i]
                gaps[i] = (1.0, gr) if rec["side"] == 'L' else (gl, 1.0)
    out = []
    for (co, (attrs, forward)), (nf, nb), (gl, gr) in zip(trimmed, counts, gaps):
        ef, eb = (nf, nb) if forward else (nb, nf)
        # The forward group is the edge's LEFT side, so a backwards walk swaps which side opens.
        pv = _point_values(attrs, gsolve.offsets_for_counts(attrs, 'LEFT', ef, eb),
                           (gl, gr) if forward else (gr, gl))
        if not forward:
            pv = _mirror(pv)
        out.append((co, pv))

    # A RAMP ARRIVES AT THE WIDTH OF THE LANE IT BECOMES. A ramp is wider than a lane -- it has
    # shoulders -- so swept at its authored width to the very nose its edges finish a half-metre
    # proud of the carriageway's on both sides, and the outer wall hands over to the road's with a
    # sideways step. Real ramps lose their shoulders over the acceleration lane, so this narrows
    # the ribbon onto the lane over the SAME `ALIGN_BLEND_LENGTH` smoothstep that slides it
    # sideways: one gentle movement (a metre over 120 m) rather than two, ending exactly in line.
    # `rka_shift` is deliberately untouched -- the lane centre is `point + shift`, so leaving it
    # alone keeps the ramp's exported route where the alignment put it and confines this to the
    # ribbon's two edges.
    if merges:
        for which, node in enumerate(ends):
            rec = merges.get((node, chain_id))
            tgt = 0.0 if rec is None else rec["target_half"]
            if tgt <= 1e-6:
                continue
            dists, total = _arclengths(out)
            blend = min(ALIGN_BLEND_LENGTH, total * 0.45)
            if blend <= 1e-6:
                continue
            for i, d in enumerate(dists):
                near = d if which == 0 else total - d
                if near >= blend:
                    continue
                pv = out[i][1]
                h_own = float(pv["rka_halfw"])
                if h_own <= tgt + 1e-6:
                    continue
                f = _smoothstep(1.0 - near / blend)
                h_new = h_own + (tgt - h_own) * f
                k = h_new / h_own
                shift = float(pv["rka_shift"])
                pv = dict(pv)
                for key in ("rka_curb_ol", "rka_curb_or", "rka_walk_cl", "rka_walk_cr"):
                    pv[key] = shift + (pv[key] - shift) * k
                pv["rka_halfw"] = h_new
                out[i] = (out[i][0], pv)

    # CARRY AN END PAST ITS GORE, so neighbouring ribbons overlap instead of abutting. Done HERE,
    # after every per-point number is resolved, and carrying the end point's own values outward:
    # extending the polyline BEFORE the lane maths lengthens the chain, which moves every taper
    # station along with it -- measured as an auxiliary lane 1.715 m wide at the gore where it
    # should be exactly 1.75. The extension is geometry, and only geometry.
    for which, node in enumerate(ends):
        if node not in gore_nodes or len(out) < 2:
            continue
        i, j = (0, 1) if which == 0 else (-1, -2)
        d = out[i][0] - out[j][0]
        if d.length < 1e-9:
            continue
        ext = (out[i][0] + d.normalized() * JOIN_OVERSHOOT, out[i][1])
        out = ([ext] + out) if which == 0 else (out + [ext])
    return out


def build_carrier(graph_obj, result, collect=None):
    """Emit `<graph>_Carrier`: one polyline per chain, trimmed at both ends, with every per-point
    number already written.

    `collect`, when given a list, is filled with `(chain_id, [(co, values), ...])` per chain -- the
    RESOLVED points, in world space and in the geometric frame. That is what `graph_edges.outline`
    needs, and taking it from here rather than re-deriving it is the point: the road's boundary and
    the road's asphalt are then two readings of the same numbers, and cannot drift apart. An
    out-parameter rather than a second return value so the one existing caller and every test that
    goes through `build_object` are unaffected."""
    me = graph_obj.data
    # Edit Mode owns the mesh: the datablock only reflects the live bmesh after an
    # `update_edit_mesh`. Reading the edit bmesh directly (rather than relying on `solve_object`
    # having just flushed) is what lets a rebuild run WITHOUT dropping the artist out of Edit Mode
    # and losing their selection -- see the auto-build in `graph_attrs`.
    own = graph_obj.mode != 'EDIT'
    bm = bmesh.new() if own else bmesh.from_edit_mesh(me)
    if own:
        bm.from_mesh(me)
    try:
        elayers = ga.ensure_edge_layers(bm, fill_defaults=False)
        verts, edges, per_point = [], [], []
        starved = []
        gore_nodes = {n.index for n in result.nodes if n.kind == gsolve.rgs().KIND_GORE}
        # WHICH GROUP EACH RAMP SERVES, derived once for the whole graph. The taper has to open
        # at the end whose ramp uses it, and that is the same answer `auto_aux_lanes` stamped the
        # lane from -- so it is read from the same function rather than guessed again here. NOT
        # gated on the graph having gores: a ramp touching down on a street is an ordinary
        # junction, and it needs its acceleration lane just as much.
        services, aligns, hosts = gsolve.ramp_plan(bm, result)
        bm.verts.ensure_lookup_table()
        node_co = {v.index: v.co.copy() for v in bm.verts}
        # PASS ONE IS GEOMETRY ONLY. The merge-corridor setback is a fact about TWO chains at once
        # -- how far a ramp is from the road it runs alongside -- so it cannot be answered inside a
        # loop that only ever holds one. Every chain's ribbon is staged first, already trimmed and
        # already aligned (the alignment is what puts the ramp on the lane, so measuring before it
        # would measure a road that is not going to be built), and only then are the per-point
        # numbers resolved.
        staged = []
        for chain_id, chain in enumerate(gsolve.chains(bm)):
            # The chain's FULL polyline first -- one point per vertex, each carrying the ATTRS of
            # the edge it arrives on -- and only then trimmed by arclength at the two real ends.
            # Attributes rather than resolved numbers, because the aux-lane taper below needs to
            # re-resolve them per point once the final arclength is known.
            pts = []
            for n, (eidx, forward) in enumerate(chain):
                e = bm.edges[eidx]
                v0, v1 = (e.verts[0], e.verts[1]) if forward else (e.verts[1], e.verts[0])
                if (v1.co - v0.co).length < 1e-9:
                    continue
                attrs = ga.read_edge(bm, e, elayers)
                if not pts:
                    pts.append((v0.co.copy(), (attrs, forward)))
                pts.append((v1.co.copy(), (attrs, forward)))
            if len(pts) < 2:
                continue
            head_e, head_f = chain[0]
            tail_e, tail_f = chain[-1]
            ends = _chain_end_verts(bm, chain)
            t0 = result.trim_start[head_e] if head_f else result.trim_end[head_e]
            t1 = result.trim_end[tail_e] if tail_f else result.trim_start[tail_e]
            # TRIM THE CHAIN, NOT THE EDGE. A 40 m junction setback on a polyline resampled every
            # 12 m has to eat through several shape points; trimming each sample edge instead
            # (the first version of this) left 189 of the island's 1634 edges reporting
            # "too short" and shredded every road near a junction.
            trimmed = _trim_chain(pts, t0, t1)
            if trimmed is None:
                starved.append((chain[0][0], round(_chain_length(pts), 2),
                                round(t0 + t1, 2)))
                continue
            # May insert taper breakpoints, so the edge run is built from ITS length, not the
            # pre-resolve one.
            trimmed = align_ramp_ends(trimmed, ends, chain_id, aligns, RAMP_OVERSHOOT)
            staged.append((chain_id, ends, trimmed))

        merges, joints = merge_corridor_ends(staged, node_co, aligns, hosts)

        for chain_id, ends, trimmed in staged:
            resolved = _resolve_points(trimmed, ends, gore_nodes, services, chain_id,
                                       aligns, merges)
            base = len(verts)
            for co, pv in resolved:
                verts.append((co.x, co.y, co.z))
                # THE COLUMN HEIGHT IS RESOLVED HERE, where the point's own elevation is known.
                # `soffit - ground` is the whole definition of a support, and it varies point by
                # point along a ramp; an edge attribute cannot express it and a fixed-height kit
                # asset cannot either. Clamped at 0 so a road on grade asks for no column rather
                # than a negative one.
                pv = dict(pv)
                soffit = co.z - float(pv.get("rka_deck_h", 0.0))
                pv["rka_pillar_h"] = max(soffit - float(pv.get("rka_ground_z", 0.0)), 0.0)
                per_point.append(pv)
            edges.extend((base + i, base + i + 1) for i in range(len(resolved) - 1))
            if collect is not None:
                # AFTER the pillar height is stamped, so the outline sees exactly the values the
                # carrier was built from -- not a near-copy resolved a second time.
                collect.append((chain_id, [(co, per_point[base + i])
                                           for i, (co, _pv) in enumerate(resolved)]))

        # THE JOINTS, AS ORDINARY CARRIER CHAINS. A merge joint is a kerb line and nothing else,
        # so it is emitted the way `graph_solve.build_corner_mesh` emits a junction's kerb corner:
        # a short polyline carrying the SAME per-point attribute names, with every band it does
        # not want written as zero. The one layer stack then sweeps it, and there is no second
        # implementation of "what a wall looks like" to drift out of step with the first.
        for p0, p1, curb_h in joints:
            if not per_point:
                break
            tpl = dict(per_point[0])
            for k in tpl:
                if k in INT_ATTRS:
                    tpl[k] = -1                       # no kit asset on a joint
                elif k not in ("rka_sp_asset", "rka_sp_pillar"):
                    tpl[k] = 0.0                      # spacings must stay non-zero; nothing else
            tpl["rka_curb_ol"] = 0.0                  # the polyline IS the kerb line
            tpl["rka_curb_hl"] = curb_h
            tpl["rka_curb_tl"] = curb_h * 0.5
            base = len(verts)
            for pt in (p0, p1):
                verts.append((pt.x, pt.y, pt.z))
                per_point.append(dict(tpl))
            edges.append((base, base + 1))
        if starved:
            print("[graph_build] %d chain(s) fully consumed by their own junctions, skipped: %s"
                  % (len(starved), starved[:5]))
    finally:
        if own:
            bm.free()          # freeing an EDIT bmesh would pull it out from under Blender

    cme = bpy.data.meshes.new(graph_obj.name + SUFFIX_CARRIER)
    cme.from_pydata(verts, edges, [])
    cme.update()
    if verts:
        keys = sorted(per_point[0].keys())
        for name in keys:
            dtype = 'INT' if name in INT_ATTRS else 'FLOAT'
            attr = cme.attributes.new(name=name, type=dtype, domain='POINT')
            attr.data.foreach_set("value", [per_point[i][name] for i in range(len(verts))])
    return gsolve._generated_object(graph_obj, SUFFIX_CARRIER, cme)


# ------------------------------------------------------------------------------------ the stack

#: How far the structural deck's top face is sunk below the carriageway it carries. Big enough to
#: beat depth-buffer precision at world scale, small enough to be invisible. See the Deck layer.
DECK_Z_BIAS = -0.02

#: How far flush-with-the-road paint is lifted clear of the asphalt. Same reasoning, other sign.
PAINT_Z_BIAS = 0.01


def _layer(name, inner, offset=0.0, offset_attr="", z=0.0, z_attr="", require_attr="",
           **inputs):
    return {"name": name, "inner": inner, "offset": offset, "offset_attr": offset_attr,
            "z": z, "z_attr": z_attr, "require_attr": require_attr, "inputs": inputs}


#: Material slot per band, created on demand. Names only -- look and shader are a project
#: decision, and a road that ships with four flat colours is still four separable surfaces in the
#: glTF bake, which is what the downstream `-colonly` and material-key passes actually need.
MATERIALS = {
    "asphalt": (0.05, 0.05, 0.055, 1.0),
    "concrete": (0.55, 0.54, 0.52, 1.0),
    "footway": (0.42, 0.41, 0.40, 1.0),
    "median": (0.20, 0.30, 0.16, 1.0),
}


def material(key):
    """Get-or-create a flat material by key, so a rebuild reuses the same datablock and any
    hand-edited shading on it survives."""
    mat = bpy.data.materials.get("rka_%s" % key)
    if mat is None:
        mat = bpy.data.materials.new("rka_%s" % key)
        mat.use_nodes = True
        mat.diffuse_color = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
            bsdf.inputs["Roughness"].default_value = 0.9
    return mat


def stack_spec():
    """The whole road, as data. Adding a band is one entry here, not a node tree."""
    band, deck, assets = gn.make_band_group(), gn.make_deck_group(), gn.make_assets_group()
    pillars = gn.make_pillars_group()
    reg = gas.registry
    return [
        _layer("Carriageway", band, offset_attr="rka_shift", WidthAttr="rka_halfw",
               Material=material("asphalt")),
        # A PAINTED median is deliberately flush with the road (`rka_med_z` = 0 for it), which is
        # the same coplanar-surface trap the deck fell into, just narrower -- so lift the paint by
        # the same kind of bias. A raised median already clears the asphalt and is unaffected.
        _layer("Median", band, WidthAttr="rka_med_h", z=PAINT_Z_BIAS, z_attr="rka_med_z",
               Material=material("median")),
        _layer("SidewalkL", band, offset_attr="rka_walk_cl", z_attr="rka_walk_zl",
               WidthAttr="rka_walk_hl", Material=material("footway")),
        _layer("SidewalkR", band, offset_attr="rka_walk_cr", z_attr="rka_walk_zr",
               WidthAttr="rka_walk_hr", Material=material("footway")),
        # A kerb is a narrow band at kerb-top height extruded back DOWN to the road surface, so
        # its box comes from the same two groups every other band uses.
        _layer("CurbL", deck, offset_attr="rka_curb_ol", z_attr="rka_curb_hl",
               WidthAttr="rka_curb_tl", ThicknessAttr="rka_curb_hl",
               Material=material("concrete")),
        _layer("CurbR", deck, offset_attr="rka_curb_or", z_attr="rka_curb_hr",
               WidthAttr="rka_curb_tr", ThicknessAttr="rka_curb_hr",
               Material=material("concrete")),
        # THE DECK TOP MUST SIT BELOW THE ROAD, NOT ON IT. The slab spans the same width as the
        # carriageway, so a top face at z = 0 is coplanar with the asphalt over the entire road --
        # measured by vertical ray sampling, 73.7% of the road surface had asphalt and concrete
        # within 5 mm, which is z-fighting across the whole network. It is worst where
        # `rka_deck_h` is 0 (every non-bridge edge): a zero-thickness deck is a bare concrete
        # sheet lying exactly on the asphalt. Dropping the slab by `DECK_Z_BIAS` is invisible --
        # it is buried under the road it carries -- and leaves the asphalt unambiguously on top.
        _layer("Deck", deck, offset_attr="rka_shift", z=DECK_Z_BIAS,
               WidthAttr="rka_halfw", ThicknessAttr="rka_deck_h",
               Material=material("concrete")),
        _layer("CurbAssetL", assets, offset_attr="rka_curb_ol", Palette=reg(gas.ROLE_CURB),
               IndexAttr="rka_ix_curb", SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        _layer("MedianAsset", assets, Palette=reg(gas.ROLE_MEDIAN), IndexAttr="rka_ix_median",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        # Two pillar layers, and only one of them ever builds for a given edge: the parametric
        # column whenever `pillar_asset_idx` is -1 (the default), the instanced kit piece when an
        # author has picked one. That is the same "-1 = build this band from its numbers instead"
        # convention every other band already uses, so choosing a decorative column is one stamp
        # and needs no switch.
        _layer("Pillars", pillars, offset_attr="rka_shift", SpacingAttr="rka_sp_pillar",
               Material=material("concrete"), require_attr="rka_pillar_param"),
        _layer("PillarAssets", assets, offset_attr="rka_shift", Palette=reg(gas.ROLE_PILLAR),
               IndexAttr="rka_ix_pillar", SpacingAttr="rka_sp_pillar"),
        _layer("RailL", assets, offset_attr="rka_curb_ol", z_attr="rka_curb_hl",
               Palette=reg(gas.ROLE_RAIL), IndexAttr="rka_ix_rail",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        _layer("PropsL", assets, offset_attr="rka_walk_cl", z_attr="rka_curb_hl",
               Palette=reg(gas.ROLE_PROP), IndexAttr="rka_ix_prop",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
    ]


def _attr_values(mesh, name):
    """Every value of a point-domain attribute, or None if the mesh does not carry it."""
    att = mesh.attributes.get(name)
    if att is None or not hasattr(att, "data"):
        return None
    try:
        return [d.value for d in att.data]
    except AttributeError:                          # not a scalar attribute
        return None


def layer_has_content(mesh, entry):
    """Would this layer build anything on THIS mesh?

    A layer whose width (or asset index) is zero everywhere still gets swept: Geometry Nodes
    happily extrudes a zero-width band and emits the polygons anyway, and a Named Attribute node
    pointed at a name the mesh does not carry reads 0 rather than erroring. So the junction
    corners -- which carry no `rka_halfw`, no median, no deck and no right-hand side at all --
    were being swept by the full 13-layer road stack, producing 11,400 concrete polygons totalling
    392 m2 of actual area plus two entirely empty bands. Every asset layer was in the same
    position on the main carrier, since every `rka_ix_*` is -1 ("parametric, no asset").

    Asking the mesh is better than hand-listing which layers a corner gets: it stays correct when
    a layer is added, and it also drops asset layers automatically until someone actually stamps
    an asset index."""
    inputs = entry.get("inputs") or {}
    # An explicit "this layer needs this attribute to be set somewhere" declaration, for a layer
    # whose switch is not a width or an asset index (the parametric pillar row).
    req = entry.get("require_attr")
    if req:
        vals = _attr_values(mesh, req)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    idx = inputs.get("IndexAttr")
    if idx:
        vals = _attr_values(mesh, idx)
        return bool(vals) and max(vals) >= 0
    for key in ("WidthAttr", "ThicknessAttr"):
        name = inputs.get(key)
        if not name:
            continue
        vals = _attr_values(mesh, name)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    return True


def build_stack(carrier_obj, spec=None):
    """(Re)build the carrier's modifier stack: head, every layer that has content, finish.

    Rebuilt wholesale rather than reconciled, because the stack is DERIVED from the spec -- and
    reconciling a live stack against a spec is exactly the bookkeeping this design exists to
    delete. It is cheap: modifiers hold no geometry, so this is a few dozen property writes."""
    for m in list(carrier_obj.modifiers):
        carrier_obj.modifiers.remove(m)
    head = carrier_obj.modifiers.new("Spine", 'NODES')
    head.node_group = gn.make_spine_group()

    for s in (spec if spec is not None else stack_spec()):
        if not layer_has_content(carrier_obj.data, s):
            continue
        wrapper, ids = gn.wrap_layer(s["inner"], "GN_Layer_" + s["inner"].name)
        mod = carrier_obj.modifiers.new(s["name"], 'NODES')
        mod.node_group = wrapper
        _set(mod, ids, "Offset", float(s.get("offset", 0.0)))
        _set(mod, ids, "OffsetAttr", s.get("offset_attr", "") or "")
        _set(mod, ids, "ZOffset", float(s.get("z", 0.0)))
        _set(mod, ids, "ZOffsetAttr", s.get("z_attr", "") or "")
        for k, v in (s.get("inputs") or {}).items():
            if v is not None:
                _set(mod, ids, k, v)

    tail = carrier_obj.modifiers.new("Finish", 'NODES')
    tail.node_group = gn.make_finish_group()
    return carrier_obj


def _set(mod, ids, name, value):
    """Set one Geometry Nodes modifier input by interface-socket identifier.

    NOT `mod[socket_id] = value`. Older Blenders exposed GN modifier inputs as plain ID-properties
    and that is what most examples still show; this one's `NodesModifier` does not support
    IDProperties at all (`mod["Socket_1"] = 1.0` raises "id properties not supported for this
    type" for EVERY socket, including plain floats -- so it fails loudly rather than silently, at
    least). Inputs live on a structured `mod.properties.inputs`, whose per-socket attributes are
    read-only pointers to a struct carrying the mutable `.value`. `kit_common.set_mod_input`
    records the same finding from the previous time this API moved."""
    if name in ids:
        getattr(mod.properties.inputs, ids[name]).value = value


#: Layers that belong to the ROAD SURFACE and are swept on the carrier. Everything else in
#: `stack_spec` is edge furniture and moves to the outline once staging is on.
SURFACE_LAYERS = ("Carriageway", "Median", "Deck", "Pillars", "PillarAssets", "MedianAsset")

#: Layers swept on `<graph>_Edges`. PHASE A is kerb and railing only: the footway, its assets and
#: the street props still ride the carrier until phase B, so nothing is built twice while the two
#: paths are being compared.
EDGE_LAYERS = ("CurbL", "RailL")


def staged_edges(graph_obj=None):
    """Is the outline-driven edge build switched on?

    Off by default: with it off, `build_object` takes exactly the path it always did, so the flag
    is what makes "the old behaviour is unchanged" checkable rather than asserted."""
    scn = bpy.context.scene if bpy.context else None
    settings = getattr(scn, "rka_graph", None) if scn else None
    return bool(getattr(settings, "stage_edge_furniture", False))


def surface_spec():
    """`stack_spec` minus the edge furniture -- the carriageway, its median and what carries it."""
    return [s for s in stack_spec() if s["name"] in SURFACE_LAYERS]


def edge_spec():
    """The layers that ride the outline. Same entries, same node groups, same attribute names as
    on the carrier -- only the curve underneath them changes, which is the whole point: there is
    still exactly one description of what a kerb looks like."""
    return [s for s in stack_spec() if s["name"] in EDGE_LAYERS]


def build_edges(graph_obj, staged):
    """Emit `<graph>_Edges`: the road surface's outer boundary, as polylines carrying the same
    `rka_*` attributes every other swept thing carries.

    The mesh is built by `graph_edges.outline` from the resolved carrier chains; this function only
    turns its three lists into a Blender mesh and hangs it off the graph, the same way
    `build_carrier` and `build_corner_mesh` do. The report is printed rather than swallowed: a
    boundary that stops against a road it never crosses is a grazing overlap the generator cannot
    close, and saying so beats leaving a silent gap in the fence."""
    report = {}
    verts, edges, per_point = gedges.outline(staged, report=report)
    me = bpy.data.meshes.new(graph_obj.name + SUFFIX_EDGES)
    me.from_pydata(verts, edges, [])
    me.update()
    if verts:
        for name in sorted(per_point[0].keys()):
            dtype = 'INT' if name in INT_ATTRS else 'FLOAT'
            attr = me.attributes.new(name=name, type=dtype, domain='POINT')
            attr.data.foreach_set("value", [per_point[i][name] for i in range(len(verts))])
    grazed = report.get("grazed", [])
    print("[graph_edges] outline: %d run(s), %d vert(s); %d kerb line(s) cut by another road"
          % (report.get("runs", 0), len(verts), report.get("clipped", 0)))
    if grazed:
        print("[graph_edges] %d boundary end(s) stopped against a road they do not cross "
              "(grazing overlap -- the fence has an open end there): %s"
              % (len(grazed), grazed[:5]))
    return gsolve._generated_object(graph_obj, SUFFIX_EDGES, me)


def build_object(graph_obj, arc_segments=8):
    """Solve, emit the carrier, hang the stack. The whole build, in the order it must happen.

    The junction CORNERS get the very same stack. `graph_solve.build_corner_mesh` writes the same
    per-point attribute names, with every band it does not want set to zero -- so a corner's kerb
    and footway are swept by the identical layers a straight road uses, and there is no second
    description of what a footway looks like to drift out of sync."""
    result = gsolve.solve_object(graph_obj, arc_segments)
    staged = [] if staged_edges(graph_obj) else None
    carrier = build_carrier(graph_obj, result, collect=staged)
    build_stack(carrier, surface_spec() if staged is not None else None)
    if staged is not None:
        edges_obj = build_edges(graph_obj, staged)
        build_stack(edges_obj, edge_spec())
    else:
        # A BUILD WITH THE FLAG OFF MUST TAKE THE OUTLINE AWAY AGAIN. `_generated_object` only
        # refreshes an object it is asked to build, so an `_Edges` left over from an earlier
        # outline build would keep its stack, keep sweeping and keep rendering -- next to the kerb
        # the carrier has just gone back to building itself. Two fences, and a flag that looked
        # like it did nothing.
        stale = bpy.data.objects.get(graph_obj.name + SUFFIX_EDGES)
        if stale is not None:
            bpy.data.objects.remove(stale, do_unlink=True)
    corners = bpy.data.objects.get(graph_obj.name + gsolve.SUFFIX_CORNERS)
    if corners is not None and len(corners.data.vertices):
        build_stack(corners)
    nodes = bpy.data.objects.get(graph_obj.name + gsolve.SUFFIX_NODES)
    if nodes is not None and len(nodes.data.polygons) and not nodes.data.materials:
        nodes.data.materials.append(material("asphalt"))
    return result, carrier


class RKA_OT_graph_build(bpy.types.Operator):
    """Solve and build the active road graph: carrier, layer stack, node patches, kerb corners."""
    bl_idname = "rka.graph_build"
    bl_label = "Build Road Graph"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        result, carrier = build_object(obj)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, "Built %d carrier polyline(s) from %d node(s)"
                    % (len(carrier.data.vertices), len(result.nodes)))
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_build,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
