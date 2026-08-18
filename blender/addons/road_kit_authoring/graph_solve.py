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

    `aux_scale` (0..1) OPENS THE AUXILIARY LANE GRADUALLY. A lane cannot be a fraction of a lane
    in `lane_profile` -- slots and markings are discrete, and inventing a 0.4-lane slot would put
    a lane line in the middle of nowhere. So the two ENDPOINT profiles are built (no aux, and full
    aux) and their offsets interpolated: the road's edge sweeps outward exactly as a real taper
    does, while every lane slot stays a whole lane at both ends. `aux_scale = 1` is bit-identical
    to the untapered result, so nothing that does not taper can change."""
    sign = 1.0 if traffic_side == 'LEFT' else -1.0
    aux_l = int(attrs.get("aux_lanes_left", 0))
    aux_r = int(attrs.get("aux_lanes_right", 0))
    full = _offsets_for(attrs, sign, aux_l, aux_r)
    if (aux_l == 0 and aux_r == 0) or aux_scale >= 1.0 - 1e-9:
        return full
    base = _offsets_for(attrs, sign, 0, 0)
    t = max(0.0, min(1.0, float(aux_scale)))
    return {k: base[k] + (full[k] - base[k]) * t for k in full}


def _offsets_for(attrs, sign, aux_l, aux_r):
    lanes_l = int(attrs.get("lanes_fwd", 2)) + aux_l
    lanes_r = int(attrs.get("lanes_bwd", 2)) + aux_r
    prof = lp().profile_from_scalars(
        lanes_l, lanes_r, float(attrs.get("lane_width", 3.5)),
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


def _station_fn(bm):
    """A `road_graph_solve.solve(station_fn=...)` callback giving each approach the point and
    heading where its ribbon REALLY ends.

    The solver measures a setback as a distance along the chain but can only see one edge, so on
    its own it has to assume that distance runs straight -- and a chain bends through its shape
    points. This walks the SAME chains `graph_build.build_carrier` builds from, so the junction
    pad's mouth lands exactly on the ribbon's cut end at exactly its heading. Straight approaches
    are unaffected (the two agree); sweeping ones were out by tens of metres."""
    outward = _outward_chains(bm)

    def station(node, appr):
        pts = outward.get((node.index, appr.edge.index))
        if pts is None:
            return None
        acc = 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            seg = (b - a).length
            if seg < 1e-12:
                continue
            if acc + seg >= appr.setback:
                t = (appr.setback - acc) / seg
                p = a.lerp(b, t)
                d = (b - a)
                return (p.x, p.y, p.z), (d.x / seg, d.y / seg)
            acc += seg
        # Setback longer than the whole chain: the far end is the best real point there is.
        d = pts[-1] - pts[-2]
        n = d.length or 1.0
        return (pts[-1].x, pts[-1].y, pts[-1].z), (d.x / n, d.y / n)

    return station


def _nose_fn(bm):
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
        pts = outward.get((node.index, ramp.edge.index))
        if pts is None or len(pts) < 2:
            return None
        # WHERE THE LANE THE RAMP CONTINUES ACTUALLY SITS. The trunk's own profile owns that
        # number; deriving it here from lane counts would be the duplicated-formula mistake this
        # pipeline keeps paying for. `curb_off_*` is the carriageway edge, and the lane centre is
        # half a lane inside it.
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

        acc = 0.0
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
            acc += seg
        return None                        # never clears: leave it to the closed-form fallback

    return nose


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


def auto_aux_lanes(bm, result, count=1, taper=None, gore_angle_deg=35.0, side_mode='AUTO'):
    """Stamp an auxiliary lane on every chain that feeds a GORE, on the side its ramp leaves.

    Authoring a ramp by hand means finding the trunk, working out which side the ramp peels off,
    and stamping the whole chain -- three chances to put the lane on the wrong side of a road that
    is walked backwards. The solver already knows all of it, so derive it.

    OFF-RAMP vs ON-RAMP decides WHICH chain gets the lane: a ramp that LEAVES the node is an exit,
    so the deceleration lane belongs upstream on the trunk; a ramp that ARRIVES is an entry, and
    its acceleration lane belongs downstream on the continuation. Both then taper to nothing away
    from the gore, which is what `graph_build.taper_scales` does with them.

    Returns `(chains stamped, [(node, degrees off tangent), ...] built as left-hand ramps)`."""
    R = rgs()
    el = ga.ensure_edge_layers(bm)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    all_chains = chains(bm)
    chain_of = {eidx: ci for ci, ch in enumerate(all_chains) for eidx, _f in ch}
    outward = _outward_chains(bm)
    tol = math.radians(gore_angle_deg)

    stamped = 0
    #: `(node index, degrees off tangent)` for gores whose ramp is on the OFFSIDE of the stream it
    #: serves, so its aux lane was built at the median end. Reported because it is worth knowing
    #: which junctions are left-hand ramps, not because it is an error -- see the side test below.
    wrong_side = []

    def _lanes(appr):
        at = ga.read_edge(bm, bm.edges[appr.edge.index], el)
        return int(at.get("lanes_fwd", 0)) + int(at.get("lanes_bwd", 0))

    for n in result.nodes:
        if n.kind != R.KIND_GORE:
            continue
        trunk = R._gore_trunk(n, tol)
        if trunk is None:
            continue
        main = R._gore_mainline(n.approaches, trunk)
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
            # AN AUXILIARY LANE IS A MAINLINE FEATURE. Where every arm of a "gore" is a one-way
            # single-lane ramp -- a ramp forking into two ramps, which the island has at the port
            # touchdown -- there is no mainline to widen, and stamping one anyway grew a second
            # lane on a ramp that then had nowhere to go (measured: `g44_F1`, an aux lane with no
            # successor at all, which reads on screen as a road preparing an exit that nothing can
            # take). Requiring the host to be genuinely wider than the ramp is the same road-class
            # test the exporter uses to pick a gore's trunk, and it costs nothing at a real gore
            # where a 4-lane carriageway sheds a 1-lane exit.
            if _lanes(host) <= _lanes(ramp):
                continue
            ci = chain_of.get(host.edge.index)
            if ci is None:
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
            # WHICH END OF THE GROUP THE LANE GOES AT. Keep-left puts the kerb on the stream's
            # left, so a ramp on its left gets an ordinary nearside aux lane at the OUTERMOST lane;
            # a ramp on its RIGHT is an offside (left-hand) ramp and the lane belongs at the median
            # end. `side_mode` forces either answer for a layout that wants the exit taken from the
            # outermost lane regardless of what the geometry measures.
            if side_mode == 'KERB':
                at_median = False
            elif side_mode == 'MEDIAN':
                at_median = True
            else:
                at_median = side <= 0.0
            if at_median:
                # REPORT THE ANGLE, because the two failures it covers are not the same problem.
                # A ramp well off tangent is genuinely on the wrong side of the road and its
                # traffic must cross the opposing stream to reach it -- a layout error. A ramp
                # within a few degrees of tangent is a near-parallel merge whose "side" is decided
                # by a fraction of a degree of approach angle; there the classification is marginal
                # rather than a crossing, and knowing which is which is the difference between
                # "move this ramp" and "ignore this".
                wrong_side.append((n.index, math.degrees(math.asin(min(1.0, max(-1.0, -side))))))
            for eidx, forward in chain:
                # An edge walked against the chain has its own forward group on the walk's back.
                is_fwd = fwd_group if forward else not fwd_group
                key = "aux_lanes_left" if is_fwd else "aux_lanes_right"
                med = "aux_median_left" if is_fwd else "aux_median_right"
                e = bm.edges[eidx]
                e[el[key]] = max(int(e[el[key]]), int(count))
                if at_median:
                    e[el[med]] = 1
                if taper is not None:
                    e[el["aux_taper_length"]] = float(taper)
        stamped += 1
    return stamped, wrong_side


class RKA_OT_graph_auto_aux(bpy.types.Operator):
    """Add a tapered auxiliary lane to every ramp gore in the active road graph."""
    bl_idname = "rka.graph_auto_aux"
    bl_label = "Auto Aux Lanes At Gores"
    bl_options = {'REGISTER', 'UNDO'}

    count: bpy.props.IntProperty(name="Aux Lanes", default=1, min=1, soft_max=3)
    taper: bpy.props.FloatProperty(name="Taper", default=90.0, min=0.0, soft_max=250.0,
                                   unit='LENGTH')
    #: WHICH END OF THE CARRIAGEWAY THE LANE OPENS AT. Auto measures the ramp; the two overrides
    #: exist because a layout may want every exit and entry taken from the OUTERMOST lane
    #: regardless -- which is the ordinary nearside answer and the one a driver expects.
    side_mode: bpy.props.EnumProperty(
        name="Aux At",
        items=(('AUTO', "Auto (measure the ramp)",
                "Put the lane at the end of the carriageway the ramp is actually on"),
               ('KERB', "Outermost lane",
                "Always open the lane at the kerb -- enter and exit from the outermost lane"),
               ('MEDIAN', "Median lane",
                "Always open the lane at the median end (offside / left-hand ramps)")),
        default='AUTO')

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
                                      side_mode=self.side_mode)
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        from . import graph_build as gbuild
        gbuild.build_object(obj)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        msg = "Stamped %d aux lane(s) at ramp gores" % n
        if wrong:
            msg += " | %d ramp(s) on the wrong side: %s" % (
                len(wrong), ", ".join("node %d (%.0f deg)" % w for w in wrong[:6]))
        self.report({'WARNING'} if wrong else {'INFO'}, msg)
        return {'FINISHED'}


def chains(bm):
    """Group edges into maximal runs through `NODE_NONE` shape points.

    Returns `[[(edge_index, forward), ...], ...]`, `forward` meaning the edge is walked v0->v1.
    Direction matters: the cross-section is expressed relative to the edge's own direction, so a
    chain walking an edge backwards must mirror its left/right.

    Depends only on the AUTHORED `node_type`, never on a solve result -- so it can run before the
    solve and hand it the chain lengths it needs to clamp trimming against."""
    vl = ga.ensure_vert_layers(bm, fill_defaults=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    def passthrough(v):
        return (len(v.link_edges) == 2
                and vl.get("node_type") is not None
                and int(v[vl["node_type"]]) == ga.NODE_NONE)

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


def build_specs(bm):
    """Graph mesh -> (`NodeSpec` list, `EdgeSpec` list) for the pure solver."""
    R = rgs()
    vlayers = ga.ensure_vert_layers(bm, fill_defaults=False)
    elayers = ga.ensure_edge_layers(bm, fill_defaults=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    avail = chain_lengths(bm, chains(bm))

    nodes = []
    for v in bm.verts:
        a = ga.read_vert(bm, v, vlayers)
        nodes.append(R.NodeSpec(v.index, (v.co.x, v.co.y, v.co.z),
                                int(a.get("node_type", 0)),
                                float(a.get("node_radius", -1.0)),
                                float(a.get("fillet_radius", 4.0))))
    edges = []
    for e in bm.edges:
        a = ga.read_edge(bm, e, elayers)
        wl, wr, pl, pr = edge_widths(a)
        edges.append(R.EdgeSpec(e.index, e.verts[0].index, e.verts[1].index, wl, wr, pl, pr,
                                avail=(avail.get(e.index) or (None, None))[1],
                                chain=(avail.get(e.index) or (None, None))[0]))
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
        result = rgs().solve(nodes, edges, arc_segments=arc_segments,
                             station_fn=_station_fn(bm), nose_fn=_nose_fn(bm))
        write_solution(bm, result)
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


CLASSES = (RKA_OT_graph_solve, RKA_OT_graph_auto_aux, RKA_OT_graph_weld_crossings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
