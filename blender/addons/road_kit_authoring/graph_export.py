"""graph_export.py -- lane centrelines out of the road graph: a `.lanekit.json` for Godot, and a
Blender preview of the same paths.

WHAT GODOT ACTUALLY CONSUMES (`WorldBaker.buildPathLaneRoute`): one flat `{"lanes": [...]}` array,
each entry `{id, points: [[x, y, z], ...], from_arm, turn, next, ...}`, turned into a `Curve3D` on
a `PathLaneRoute`. Coordinates are GODOT space -- `godot = (blender_x, blender_z, -blender_y)` --
the same convention every previous exporter in this pipeline used.

WHY CONNECTORS ARE NOT OPTIONAL. Godot's `LaneGraph` chains one lane to the next by ENDPOINT
PROXIMITY, within `JUNCTION_RADIUS` (4.5 m). In this model every chain is trimmed back from its
junction by the setback -- 40 m on an arterial -- so two roads meeting at a crossing leave their
lane ends 80 m apart and the runtime would find no successor at all: every car would drive to the
stop line and vanish. So the junction interior has to be REAL lane geometry, and this module emits
it: one cubic-bezier connector per legal in->out movement, tangent-matched to both lanes so a
vehicle's heading is continuous through the turn. That is the same "turning is a data lookup, not
runtime inference" rule the old roads-v2 pipeline established.

MOVEMENT LEGALITY comes from the vertex-domain `allow_cross`, and it is deliberately separate from
geometry: the junction still builds its full asphalt pad, only the movement set shrinks. In
keep-left traffic the RIGHT turn is the one that crosses the opposing stream, so `allow_cross = 0`
drops right turns and U-turns and keeps left and through. A U-turn (in and out on the same
approach) is never emitted.

LANE OFFSETS COME FROM `lane_profile.slot_offset`, like everything else here. This module must
never compute `lane_index * lane_width` itself -- that duplicated formula is the documented cause
of the three 2026-08 defects.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector

from . import graph_attrs as ga
from . import graph_solve as gsolve

PREVIEW_COLLECTION = "RKA_LANE_PREVIEW"
#: Edge-only mesh of direction chevrons for the whole network -- see `preview`.
FLOW_OBJECT = "RKA_LANE_FLOW"
CONNECTOR_SEGMENTS = 8
#: Minimum span an endpoint tangent is measured over. Long enough to outrun a trim stub or a taper
#: breakpoint, short enough not to straighten a real curve. See `_tangents`.
TANGENT_BASELINE = 2.0
#: Must stay <= LaneGraph.JUNCTION_RADIUS (4.5 m, Java) or a connector will not chain at runtime.
JUNCTION_RADIUS = 4.5
#: Below this the two lanes already meet (an untrimmed gore mainline), so they are chained
#: directly rather than bridged by a degenerate connector -- see the emission site.
MIN_CONNECTOR_LEN = 0.5
#: Shorter than this a "road" is not a road, it is the gap between two junctions that grew into
#: each other. Such chains emit no lanes and merge their end nodes instead -- see `collect`.
MIN_LANE_LENGTH = 5.0
#: Must match `road_graph_solve.solve`'s `gore_angle_deg`, or this module would disagree with the
#: solver about which arm of a gore is the trunk.
GORE_ANGLE_DEG = 35.0


def _godot(p):
    """Blender -> Godot axes. One conversion site, as every exporter in this pipeline has had."""
    return [round(p.x, 4), round(p.z, 4), round(-p.y, 4)]


def _tangents(pts):
    """Unit XY tangent per point of a polyline, measured over at least `TANGENT_BASELINE`.

    WHY NOT JUST THE ADJACENT POINT. A chain is trimmed at an arbitrary distance and then has
    taper breakpoints inserted, so its first or last segment is routinely a fraction of a metre --
    and at gore 387 the end segment was 0.28 m long and pointed slightly BACKWARDS, which made the
    mainline's exit heading read 177 degrees away from the lane feeding it. The connector logic
    then classified the continuation as a reversal and dropped it, leaving the whole downstream
    carriageway unfed. Widening the window until it spans a real distance makes an endpoint
    tangent mean the direction of the ROAD rather than the direction of its last stub."""
    out = []
    n = len(pts)
    for i in range(n):
        lo, hi = i, i
        while lo > 0 and (pts[i] - pts[lo]).length < TANGENT_BASELINE:
            lo -= 1
        while hi < n - 1 and (pts[hi] - pts[i]).length < TANGENT_BASELINE:
            hi += 1
        d = Vector((pts[hi].x - pts[lo].x, pts[hi].y - pts[lo].y, 0.0))
        if d.length <= 1e-9:                       # whole neighbourhood is one point
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
            d = Vector((b.x - a.x, b.y - a.y, 0.0))
        out.append(d.normalized() if d.length > 1e-9 else Vector((1.0, 0.0, 0.0)))
    return out


def _offset_polyline(pts, offset):
    """Shift a polyline laterally by `offset` -- signed (+left of travel), scalar or per point."""
    tans = _tangents(pts)
    offs = offset if isinstance(offset, (list, tuple)) else [offset] * len(pts)
    out = []
    for p, t, o in zip(pts, tans, offs):
        lat = Vector((-t.y, t.x, 0.0))
        out.append(Vector((p.x + lat.x * o, p.y + lat.y * o, p.z)))
    return out


def chain_lanes(pts, attrs, traffic_side='LEFT', counts=None):
    """Every drivable lane of one chain, as
    `[(suffix, direction, [points], is_aux, at_start, at_end), ...]`.

    `at_start` / `at_end` are `(kerb index, lane count)` for the lane's OWN direction of travel at
    the end it departs from and the end it arrives at -- what the junction there sees. They are
    reported per END, not once for the chain, because the two ends of a chain whose lane count
    varies do not present the same road; None means the lane does not reach that end at all.

    `counts` is `graph_build.chain_lane_counts`' per-point `(lanes_fwd, lanes_bwd)` in the chain's
    walk frame -- the SAME numbers the carrier is swept with, which is what stops a route from
    running off the asphalt. Two things fall out of it:

      * A LANE'S CENTRELINE IS CLAMPED TO THE OUTERMOST LANE THAT EXISTS THERE. Through lanes
        never move -- a lane is added OUTSIDE them, so their distance from the divide does not
        depend on how many there are -- while a lane that has not opened yet rides ON its inboard
        neighbour and slides out to its own position as its taper opens. That is what a
        deceleration lane physically IS: before the taper, the traffic that will take the exit is
        in the through lane, and it peels off along the taper. Clamping to the ROAD EDGE instead
        (the previous rule, and the reason this is spelled out) put that traffic half a lane
        outboard of the through lane -- driving down the edge line with two wheels off the
        asphalt for as long as the lane was closed.
      * THE ROUTE STILL RUNS THE WHOLE CHAIN, deliberately. An auxiliary lane has no entrance of
        its own: nothing flows into a route that begins in mid-carriageway, and the only lane
        change this pipeline can express today is the junction connector at the chain's end (see
        `movement_verdict`'s "only lane N may move into the opening kerb-side aux lane"). Cutting
        the route where its lane opens therefore made every ramp on the island unreachable. The
        honest fix is lane-change adjacency (`inner_lane`/`outer_lane`, which the sidecar and
        `PathLaneRoute` already carry and nothing yet emits or drives on); until then the route
        reaches back to the junction, riding its neighbour the whole way."""
    lp = gsolve.lp()
    sign = 1.0 if traffic_side == 'LEFT' else -1.0
    lane_w = float(attrs.get("lane_width", 3.5))
    aux_n = {lp.FWD: int(attrs.get("aux_lanes_left", 0)),
             lp.REV: int(attrs.get("aux_lanes_right", 0))}
    if counts is None:
        counts = [(int(attrs.get("lanes_fwd", 2)) + aux_n[lp.FWD],
                   int(attrs.get("lanes_bwd", 2)) + aux_n[lp.REV])] * len(pts)
    wide = {lp.FWD: max(c[0] for c in counts), lp.REV: max(c[1] for c in counts)}
    prof = lp.profile_from_scalars(
        int(math.ceil(wide[lp.FWD] - 1e-6)), int(math.ceil(wide[lp.REV] - 1e-6)), lane_w,
        float(attrs.get("median_width", 0.0)),
        float(attrs.get("sidewalk_left_width", 0.0)),
        float(attrs.get("sidewalk_right_width", 0.0)))

    raw = []
    for i, slot in enumerate(prof.slots):
        if not slot.is_drivable():
            continue
        off = lp.slot_offset(prof, i)
        raw.append((slot.dir, abs(off), off))
    built = []
    for direction in (lp.FWD, lp.REV):
        # Ranked from the DIVIDE outward: rank 1 is the median lane, rank n the kerb lane. That
        # is the order lanes appear in as the road widens -- a road gaining a lane gains it at the
        # kerb -- so "does lane r exist here" is simply "are there at least r lanes here".
        group = sorted([r for r in raw if r[0] == direction], key=lambda r: r[1])
        if not group:
            continue
        n_max = len(group)
        base_mag = group[0][1] - 0.5 * lane_w          # the divide: median half, or the centreline
        col = 0 if direction == lp.FWD else 1
        for rank, (_d, mag, off) in enumerate(group, start=1):
            side = 1.0 if off >= 0.0 else -1.0
            per_point, closed = [], False
            for k in range(len(pts)):
                ne = counts[k][col]
                # The centre of the outermost lane that exists here -- this lane's own place once
                # it is open, its neighbour's while it is not.
                held = base_mag + max(min(float(rank), ne) - 0.5, 0.0) * lane_w
                per_point.append(sign * side * min(mag, held))
                closed = closed or ne < rank - 1e-6
            line = _offset_polyline(pts, per_point)
            kerb_ix = n_max - rank
            # A lane is auxiliary when it is not part of the through road: inside the authored
            # aux count, or simply not open for the whole chain.
            is_aux = kerb_ix < aux_n[direction] or closed
            built.append({"suffix": "%s%d" % ("F" if direction == lp.FWD else "R", kerb_ix),
                          "dir": direction, "points": line, "mag": mag, "is_aux": is_aux,
                          "head": True, "tail": True})

    # END-LOCAL KERB INDEX. Ranked among the lanes that actually reach that end, so the lane
    # numbering a junction sees always starts at 0 on the kerb of the road that is really there.
    for end in ("head", "tail"):
        for direction in (lp.FWD, lp.REV):
            at = sorted([b for b in built if b["dir"] == direction and b[end]],
                        key=lambda b: -b["mag"])
            for k, b in enumerate(at):
                b[end + "_ix"] = (k, len(at))

    out = []
    for b in built:
        fwd = b["dir"] == lp.FWD
        start = b.get(("head" if fwd else "tail") + "_ix")
        end = b.get(("tail" if fwd else "head") + "_ix")
        out.append((b["suffix"], b["dir"], b["points"] if fwd else list(reversed(b["points"])),
                    b["is_aux"], start, end))
    return out


def allowed_turns(curb_index, count):
    """Which movements a lane may make, by its position in the approach.

    The project's keep-left rule, unchanged from roads-v2: a single-lane approach may do anything;
    otherwise the kerb lane turns left or goes through, the median lane turns right or goes
    through, and a middle lane goes through only. This is what keeps a junction's connector set
    proportional to its lanes instead of quadratic in them -- and it is also simply how the
    markings on a real approach are painted."""
    if count <= 1:
        return ('L', 'S', 'R')
    if curb_index == 0:
        return ('L', 'S')
    if curb_index == count - 1:
        return ('R', 'S')
    return ('S',)


def _bezier(p0, t0, p1, t1, segments=CONNECTOR_SEGMENTS):
    """Cubic Hermite-style connector: tangent-matched at both ends so a vehicle's heading is
    continuous through the turn rather than snapping at the stop line."""
    d = (p1 - p0).length / 3.0
    c0 = p0 + t0 * d
    c1 = p1 - t1 * d
    pts = []
    for i in range(segments + 1):
        u = i / segments
        v = 1.0 - u
        pts.append(p0 * (v ** 3) + c0 * (3 * v * v * u) + c1 * (3 * v * u * u) + p1 * (u ** 3))
    return pts


def _turn_of(t_in, t_out):
    """'L' / 'S' / 'R' from the heading change, in the same alphabet the traffic code already
    uses (`VehicleRoute.turn`)."""
    ang = math.degrees(math.atan2(t_in.x * t_out.y - t_in.y * t_out.x,
                                  t_in.x * t_out.x + t_in.y * t_out.y))
    return 'L' if ang > 30.0 else ('R' if ang < -30.0 else 'S')


def movement_verdict(lane_in, lane_out, turn, is_gore, tarms, allow_cross, ins, outs):
    """`None` if this in-lane -> out-lane movement is legal, else a short reason it is not.

    ONE PLACE, TWO CALLERS. `collect` emits connectors from it and `explain_node` prints the
    reasons, so the explanation can never describe rules the exporter is not using -- which is the
    only way a "why is there no turn here?" answer is worth reading.

    Each lane is `(id, point, tangent, curb_index, lane_count, is_aux)`."""
    lid_in, _p_in, t_in, cix_in, n_in, aux_in = lane_in
    lid_out, _p_out, t_out, cix_out, n_out, aux_out = lane_out
    arm_in = lid_in.rsplit("_", 1)[0]
    arm_out = lid_out.rsplit("_", 1)[0]
    if arm_out == arm_in:
        return "U-turn back down the same road"
    # NO MOVEMENT THROUGH A GORE MAY REVERSE. `_turn_of` reports a heading change through atan2,
    # so a 179-degree reversal comes back as a perfectly ordinary-looking 'R' and was emitted as a
    # real connector -- a car leaving a ramp and immediately driving back up the road it had just
    # joined. Every arm of a gore is tangential by definition, so anything past a right angle there
    # is nonsense. NOT applied at intersections, where arms meet at any angle and a genuinely sharp
    # turn between two acute arms is legal (gating it everywhere cost 155 connectors and left 9
    # more lanes with no successor).
    if is_gore and t_in.dot(t_out) < 0.0:
        return "reverses through a gore"
    if not is_gore:
        if turn not in allowed_turns(cix_in, n_in):
            return "turn %s not allowed from lane %d of %d" % (turn, cix_in, n_in)
        # Target lane is the same position from the kerb, clamped to what the exit actually has --
        # the whole mixed-lane-count answer, in one expression.
        if cix_out != min(cix_in, n_out - 1):
            return "kerb index %d does not continue into %d" % (cix_in, cix_out)
        # Keep-left: the RIGHT turn is the one crossing the opposing stream.
        if not allow_cross and turn == 'R':
            return "allow_cross is off and this is a right turn"
        return None
    # ---- gore
    # A GORE HAS NO TURN CHOICE. Nobody stops, and the mainline goes where the road goes, so
    # `allowed_turns` (which is about which lane may turn where at a junction) must not gate it. It
    # did: a trunk that bends more than 30 degrees through its own nose had its continuation
    # rejected as an illegal right turn even though the two lanes were 0.0 m apart, leaving the
    # whole downstream carriageway unfed. Which arms are the trunk comes from the solver's own
    # `_gore_trunk`/`_gore_mainline`, NOT from "whichever leaves straightest" -- measured at gore
    # 387 that heuristic picked the RAMP as the through arm.
    if arm_in in tarms and arm_out in tarms:
        # A DECELERATION LANE IS EXIT-ONLY. The trunk's lane matching clamps a missing counterpart
        # to the nearest lane the exit arm has (`min(..., n_out - 1)`), which is right for a
        # mixed-lane-count junction but wrong for the ONE lane that is leaving: the aux lane got
        # clamped back onto the through carriageway, so it both took the ramp and carried on, and
        # two lanes fed one. Only applies where a ramp actually departs here -- at an ON-ramp the
        # ramp arrives, the aux is the acceleration lane on the way out, and it must stay fed.
        ramp_departs = any(o[0].rsplit("_", 1)[0] not in tarms for o in outs)
        if aux_in and ramp_departs:
            return "deceleration lane leaves by the ramp, it does not continue on the trunk"
        # WHICH LANE MOVES INTO AN AUXILIARY LANE THAT OPENS HERE -- normally the one beside it,
        # but not when that lane is itself leaving. Two gores in a row (an exit whose deceleration
        # lane is exit-only, immediately followed by the next exit's lane opening) put an
        # exit-only lane where the feeder should be, so nothing moved into the new lane and it
        # opened as an unreachable stub: the road visibly widens for an exit that nothing can
        # enter. Measured on the island as three unfed auxiliary lanes (g26_R0, g30_R0, g33_R0).
        # The feeder is the nearest lane that is still ON the trunk after this node.
        def _feeder():
            same = [i for i in ins if i[0].rsplit("_", 1)[0] == arm_in
                    and not (i[5] and ramp_departs)]
            return min((i[3] for i in same), default=0)
        # THE MAINLINE IS ANCHORED AT THE END WHERE THE LANE COUNT DOES NOT CHANGE. The auxiliary
        # lane always opens at the KERB (see `auto_aux_lanes` for the convention), so the through
        # lanes hold their distance from the MEDIAN and keep their identity across the gore.
        med_in, med_out = n_in - 1 - cix_in, n_out - 1 - cix_out
        if med_out == min(med_in, n_out - 1):
            return None
        # ...except the lane that OPENS here. An auxiliary lane has no counterpart upstream, so the
        # through lane BESIDE it is the one that moves into it -- exactly how a driver enters a
        # deceleration lane.
        if not aux_out:
            return "median index %d does not continue into %d" % (med_in, med_out)
        # AN ACCELERATION LANE BELONGS TO THE RAMP THAT FEEDS IT. The rule below is about a
        # DEceleration lane -- one that opens for traffic leaving, which a driver enters from the
        # through lane beside it. Where the ramp ARRIVES instead, the lane opening at the gore is
        # the merge lane and the traffic entering it comes up the ramp; letting the trunk's kerb
        # lane move into it as well puts the mainline into the very lane the ramp is merging from,
        # which is the "the ramp shares the road's own lanes" case (measured at the island's
        # IC_YAMATE entry, node 417: g96_F0 fed both g97_F0 and g97_F1).
        # ...and only for the lane THAT ramp merges into. A gore can open an auxiliary lane on
        # each carriageway (an entry serving one, an exit serving the other), and an arriving ramp
        # cannot feed the one running the other way -- it would have to reverse through the gore,
        # which the guard at the top of this function already forbids. Testing it the same way
        # keeps the two agreeing; asking only "does a ramp arrive here" left the far carriageway's
        # lane fed by nothing at the island's node 377.
        if any(i[2].dot(t_out) > 0.0 for i in ins
               if i[0].rsplit("_", 1)[0] not in tarms):
            return "the acceleration lane opening here belongs to the ramp merging into it"
        feed = _feeder()
        if cix_in != feed:
            return "only lane %d may move into the opening kerb-side aux lane" % feed
        return None
    # A RAMP HANGS OFF ONE CARRIAGEWAY, and `allow_cross` says whether the median may be crossed
    # here. The gore branch used to ignore it entirely -- reasonable-looking, since a tangential
    # diverge's far carriageway is anti-parallel to the ramp and dies on the reversal guard above,
    # so the hole never showed. It is still a hole: the moment the two arms are NOT anti-parallel
    # (a trunk that bends through its own nose, or a diverge steep enough that the solver called it
    # an intersection and a ramp arm re-established the gore rules per movement) the far
    # carriageway gets a right turn into the exit, which is a drive across the middle of a
    # motorway. Applied ONLY to the ramp movements: the mainline continuation is exempt on purpose,
    # because a trunk bending more than 30 degrees reports its own continuation as a right turn and
    # rejecting that leaves the whole downstream carriageway unfed.
    if not allow_cross and turn == 'R':
        return "allow_cross is off and reaching this ramp means crossing the opposing carriageway"
    # A RAMP MOVEMENT CONNECTS TO THE AUXILIARY LANE. Asked as "which lane is the aux one?" rather
    # than "is this kerb index 0?", because a trunk may carry more than one and the aux is the lane
    # that exists FOR this ramp -- the index is a consequence, not the rule.
    if arm_in in tarms:
        arm_has_aux = any(i[5] for i in ins if i[0].rsplit("_", 1)[0] == arm_in)
        if aux_in:
            return None
        if arm_has_aux:
            return "this trunk has an aux lane and this is not it"
        if cix_in != 0:
            return "no aux lane here, so only the kerb lane may leave for a ramp"
        return None
    trunk_aux = [o for o in outs if o[5] and o[0].rsplit("_", 1)[0] in tarms]
    if trunk_aux and not aux_out:
        return "the ramp merges into the trunk's aux lane, not this one"
    if not trunk_aux and cix_out != min(cix_in, n_out - 1):
        return "kerb index %d does not continue into %d" % (cix_in, cix_out)
    return None


def gore_rule_for(clusters, arm_in, arm_out):
    """Trunk arms of the gore governing this movement, or `None` if no gore governs it.

    A GORE STUB-JOINED TO A CROSSING KEEPS ITS DIVERGE RULES FOR ITS OWN ARMS. Node *kind* is
    per-junction but the lane-matching rules are per-movement, and when a ramp nose sits a few
    metres from a surface crossing the two collapse into one merged node. Downgrading the whole
    thing to an intersection then dropped the gore rules entirely: every through lane got a
    connector into the ramp instead of only the auxiliary lane that widens out to meet it -- the
    "ramp sticks into the middle" merge. Movements whose two arms both belong to one gore get that
    gore's rules; every other movement at the same node stays an ordinary crossing."""
    for trunk, arms in clusters:
        if arm_in in arms and arm_out in arms:
            return trunk
    return None


def explain_node(graph_obj, node_index, traffic_side='LEFT'):
    """Every candidate movement at one junction and the verdict on it, as printable lines.

    The question a road-network preview cannot answer on its own is "why is there no turn from
    here to there?", and guessing at it from the geometry is how three separate lane-matching bugs
    survived. This reports it from `movement_verdict`, the same function the exporter obeys."""
    lanes, _stats, ctx = collect(graph_obj, traffic_side, want_context=True)
    ins = ctx["arrivals"].get(node_index, [])
    outs = ctx["departures"].get(node_index, [])
    tarms = ctx["trunk_arms"].get(node_index, ())
    clusters = ctx["gore_clusters"].get(node_index, ())
    kind = ctx["kind_of"].get(node_index, "?")
    out = ["node %d (%s)%s" % (node_index, kind,
                              "  trunk arms %s" % sorted(tarms) if tarms else "")]
    if not ins and not outs:
        out.append("  nothing arrives or departs here -- try the merged root of a stub pair")
        return out
    out.append("  arrives: %s" % ", ".join(
        "%s[%d/%d%s]" % (i[0], i[3], i[4], " AUX" if i[5] else "") for i in ins))
    out.append("  departs: %s" % ", ".join(
        "%s[%d/%d%s]" % (o[0], o[3], o[4], " AUX" if o[5] else "") for o in outs))
    for i in ins:
        for o in outs:
            turn = _turn_of(i[2], o[2])
            mt = gore_rule_for(clusters, i[0].rsplit("_", 1)[0], o[0].rsplit("_", 1)[0])
            why = movement_verdict(i, o, turn, mt is not None, mt or (),
                                   ctx["allow_cross"].get(node_index, 1), ins, outs)
            out.append("    %-14s -> %-14s turn=%s %s %s"
                       % (i[0], o[0], turn, "gore" if mt is not None else "    ",
                          "EMIT" if why is None else "skip: " + why))
    return out


def collect(graph_obj, traffic_side='LEFT', want_context=False):
    """Every lane and connector of the whole graph.

    Returns `(lanes, stats)` where a lane is a plain dict ready for `.lanekit.json`."""
    result = gsolve.solve_object(graph_obj)
    me = graph_obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    lanes, arrivals, departures = [], {}, {}
    #: edge index -> the arm name ("g<chain id>") its lanes are published under. Needed to ask
    #: the solver which arms of a gore are the TRUNK, since lane ids only carry chain ids.
    edge_arm = {}
    #: chain id -> (head node, tail node) and its ordered raw polyline. Kept for every chain,
    #: including the stubs that emit no lanes, because resolving a stub's identity needs its
    #: geometry (see `stub_cont` below).
    chain_ends, chain_pts = {}, {}
    try:
        el = ga.ensure_edge_layers(bm, fill_defaults=False)
        vl = ga.ensure_vert_layers(bm, fill_defaults=False)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        from . import graph_build as gb
        kinds = {n.index: n.kind for n in result.nodes}
        gore = gsolve.rgs().KIND_GORE
        gore_nodes = {i for i, k in kinds.items() if k == gore}
        # WHICH LANE GROUP EACH RAMP USES -- the same derivation `auto_aux_lanes` stamped the
        # lane from and the carrier tapers it with, so all three agree about which end of a chain
        # the auxiliary lane is full width at.
        services, _wrong = gsolve.ramp_services(bm, result)
        aligns = gsolve.ramp_alignments(bm, result)

        # PASS 1 -- resolve every chain's real, trimmed centreline.
        built = []
        for cid, chain in enumerate(gsolve.chains(bm)):
            for _e, _f in chain:
                edge_arm[_e] = "g%d" % cid
            # WALK THE CHAIN THE WAY ITS EDGES POINT. `lanes_fwd`/`lanes_bwd` are defined relative
            # to an edge's own v0->v1 direction, but `chains()` may hand back a run walked against
            # it -- and unlike the carrier (which mirrors per point) this export resolves one
            # cross-section for the whole chain, so a backwards walk silently emitted every lane
            # reversed. A reversed lane arrives where it should depart, so nothing at the junction
            # matches up and the chain ends up with no successors at all.
            if chain and not chain[0][1]:
                chain = [(e, not f) for e, f in reversed(chain)]
            # PER POINT, LIKE THE CARRIER. Each point carries the attrs of the edge it arrives
            # on and that edge's walk direction, because a chain's cross-section is not one
            # record: a road can gain a lane halfway along, and reading only the last edge (which
            # is what this did) exported the wrong lane count for everything before it.
            pts, attrs = [], None
            for eidx, forward in chain:
                e = bm.edges[eidx]
                v0, v1 = (e.verts[0], e.verts[1]) if forward else (e.verts[1], e.verts[0])
                if (v1.co - v0.co).length < 1e-9:
                    continue
                ea = ga.read_edge(bm, e, el)
                if attrs is None or (int(ea.get("lanes_fwd", 0)) + int(ea.get("lanes_bwd", 0))
                                     > int(attrs.get("lanes_fwd", 0))
                                     + int(attrs.get("lanes_bwd", 0))):
                    # The chain-level record (lane width, median, footways) comes from its WIDEST
                    # edge -- the state the full profile has to be able to hold.
                    attrs = ea
                if not pts:
                    pts.append((v0.co.copy(), v0.index, (ea, forward)))
                pts.append((v1.co.copy(), v1.index, (ea, forward)))
            if len(pts) < 2 or attrs is None:
                continue
            head_node, tail_node = pts[0][1], pts[-1][1]
            chain_ends[cid] = (head_node, tail_node)
            chain_pts[cid] = [p for p, _i, _a in pts]
            head_e, head_f = chain[0]
            tail_e, tail_f = chain[-1]
            t0 = result.trim_start[head_e] if head_f else result.trim_end[head_e]
            t1 = result.trim_end[tail_e] if tail_f else result.trim_start[tail_e]
            trimmed = gb._trim_chain([(p, a) for p, _i, a in pts], t0, t1)
            if trimmed is None:
                continue
            # THE SAME WIDTHS THE CARRIER IS SWEPT WITH, from the same function, so the routes sit
            # on the asphalt that actually gets built rather than on some second interpretation of
            # the same attributes.
            trimmed = gb.align_ramp_ends(trimmed, (head_node, tail_node), cid, aligns)
            trimmed, counts, _opens = gb.chain_lane_counts(
                trimmed, (head_node, tail_node), gore_nodes, services, cid)
            line = [co for co, _v in trimmed]
            # MEASURE THE LANES, NOT THE CENTRELINE. A chain can span 8 m down the middle while
            # its inner lane collapses to 0.2 m through a tight bend -- offsetting shortens the
            # inside of a curve -- so the centreline alone still let stub routes through.
            built_lanes = chain_lanes(line, attrs, traffic_side, counts)
            span = min((sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))
                        for _s, _d, pts, _a, _st, _en in built_lanes), default=0.0)
            built.append((cid, attrs, built_lanes, head_node, tail_node, span))

        # A ROAD EATEN TO NOTHING BY ITS JUNCTIONS *IS* THE JUNCTION. Two junctions close enough
        # that the road between them trims away leave a stub -- the island had 36 lanes under 2 m
        # and one of 0.2 m, a fifth of the network. Those are not drivable segments: nothing can
        # enter them (their length is shorter than the connector tolerance that would feed them),
        # and a 0.2 m `Curve3D` is noise in the runtime lane graph. So the stub emits no lanes and
        # its two end nodes are MERGED instead, which makes the roads on either side connect
        # straight through the combined junction -- one big junction rather than two junctions
        # with a scrap of road wedged between them.
        parent = {}

        def _find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def _union(a, b):
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[ra] = rb

        stubs = set()
        for cid, _attrs, _lanes, head_node, tail_node, span in built:
            if span >= MIN_LANE_LENGTH:
                continue
            stubs.add(cid)
            if head_node != tail_node:
                _union(head_node, tail_node)
            # A stub that returns to the SAME node needs no merge -- there is nothing to join --
            # but it is still not a road. The island had four 0.22 m "lanes" looping out of one
            # intersection and back into it, which is a junction's own geometry, not a route.

        # ARM IDENTITY ACROSS A STUB. A stub emits no lanes, so its chain id names nothing the
        # merged junction publishes -- and when the arm that is a stub belongs to a GORE, the
        # gore's trunk/ramp arms are names that appear in no lane at all, which silently voided
        # every gore rule at that junction (the island's interchange diverged onto two parallel
        # 5 m stubs, so all three through lanes got a connector into the ramp instead of only the
        # auxiliary lane -- the "ramp sticks into the middle" merge). A stub is a scrap of road,
        # so its identity is the road it points at: match each stub to the real chain leaving its
        # far end most collinearly. Best pair first, one continuation per chain, so two
        # near-parallel stubs at the same node cannot both claim the same road.
        def _terminal_dir(cid, node, outward):
            pts = chain_pts.get(cid)
            ends = chain_ends.get(cid)
            if not pts or len(pts) < 2 or ends is None:
                return None
            if node == ends[0]:
                near, nxt = pts[0], pts[1]
            elif node == ends[1]:
                near, nxt = pts[-1], pts[-2]
            else:
                return None
            d = (nxt - near) if outward else (near - nxt)
            return d.normalized() if d.length > 1e-9 else None

        stub_at, real_at = {}, {}
        for cid, ends in chain_ends.items():
            bucket = stub_at if cid in stubs else real_at
            for n in set(ends):
                bucket.setdefault(n, []).append(cid)
        stub_cont = {}
        for node, scids in stub_at.items():
            pairs = []
            for s in scids:
                din = _terminal_dir(s, node, outward=False)
                if din is None:
                    continue
                for c in real_at.get(node, ()):
                    dout = _terminal_dir(c, node, outward=True)
                    if dout is not None:
                        pairs.append((din.dot(dout), s, c))
            pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
            used_s, used_c = set(), set()
            for dot, s, c in pairs:
                if dot <= 0.0 or s in used_s or c in used_c:
                    continue
                used_s.add(s)
                used_c.add(c)
                stub_cont[(s, node)] = "g%d" % c

        def _arm_at(edge_index, node_index):
            """The published arm name an approach edge speaks for, seen from `node_index`."""
            name = edge_arm.get(edge_index)
            if name is None:
                return None
            cid = int(name[1:])
            if cid not in stubs:
                return name
            ends = chain_ends.get(cid)
            if ends is None:
                return name
            far = ends[1] if ends[0] == node_index else ends[0]
            return stub_cont.get((cid, far), name)

        # PASS 2 -- emit lanes, registering them at the MERGED node.
        for cid, attrs, built_lanes, head_node, tail_node, _span in built:
            if cid in stubs:
                continue
            for suffix, direction, lpts, is_aux, at_start, at_end in built_lanes:
                lid = "g%d_%s" % (cid, suffix)
                lanes.append({"id": lid, "points": [_godot(p) for p in lpts],
                              "from_arm": "g%d" % cid, "kind": "through",
                              "lane_width": round(float(attrs.get("lane_width", 3.5)), 3),
                              "next": []})
                # A lane DEPARTS the node its first point is nearest and ARRIVES at the other --
                # but only if it REACHES that end. A lane that opens partway along the chain is
                # not an approach to the junction behind it, and registering it as one invented a
                # movement into a lane that does not exist there.
                start_node = head_node if direction == gsolve.lp().FWD else tail_node
                end_node = tail_node if direction == gsolve.lp().FWD else head_node
                tans = _tangents(lpts)
                if at_start is not None:
                    departures.setdefault(_find(start_node), []).append(
                        (lid, lpts[0], tans[0], at_start[0], at_start[1], is_aux))
                if at_end is not None:
                    arrivals.setdefault(_find(end_node), []).append(
                        (lid, lpts[-1], tans[-1], at_end[0], at_end[1], is_aux))
        merged = {n: _find(n) for n in parent if _find(n) != n}

        # ---- junction connectors
        R = gsolve.rgs()
        gore_kind = R.KIND_GORE
        allow_cross_by_node = {}
        # A merged node answers for all its members. It is a GORE only if EVERY member is one:
        # a gore absorbed into an intersection stops behaving like a diverge, and treating the
        # combination as a gore would apply the "only the kerb lane may leave" rule to a junction
        # that is really a crossing.
        kind_of = {}
        for n in result.nodes:
            root = _find(n.index)
            prev = kind_of.get(root)
            kind_of[root] = n.kind if prev is None else (
                prev if prev == n.kind else R.KIND_INTERSECTION)
        # WHICH ARMS OF A GORE ARE THE TRUNK, from the same two helpers that classified the node.
        # A movement between two trunk arms is the mainline carrying on; anything else involves
        # the ramp, and the two obey OPPOSITE lane-matching rules (see the emission site).
        # COLLECTED PER GORE, NOT PER NODE, and NOT gated on the merged node still being a gore:
        # the rules are applied per movement by `gore_rule_for`, so a gore absorbed into a
        # crossing keeps them for its own three arms while the crossing keeps intersection rules
        # for everything else.
        gore_clusters, trunk_arms = {}, {}
        for n in result.nodes:
            if n.kind != gore_kind:
                continue
            tr = R._gore_trunk(n, math.radians(GORE_ANGLE_DEG))
            if tr is None:
                continue
            mn = R._gore_mainline(n.approaches, tr)
            trunk = {_arm_at(a.edge.index, n.index) for a in (tr, mn) if a is not None} - {None}
            if not trunk:
                continue
            arms = {_arm_at(a.edge.index, n.index) for a in n.approaches} - {None}
            root = _find(n.index)
            # THE TRUNK IS THE MAINLINE, AND THE MAINLINE IS THE WIDER ROAD. `_gore_trunk` /
            # `_gore_mainline` choose it from tangency alone, which is right while a ramp peels off
            # a straight carriageway and wrong the moment the ramp is the straightest thing at the
            # node: at island gore 331 they returned the ONE-LANE RAMP as a trunk arm and a
            # three-lane carriageway as the ramp. That inverts every rule downstream -- the
            # carriageway's auxiliary lane was rejected as "a deceleration lane that must leave by
            # the ramp" while its two through lanes took the exit, which is precisely the "ramp
            # connects to the centre instead of the lane that opens for it" symptom. Road class
            # settles what tangency cannot: a single-lane one-way arm is not a motorway's mainline
            # while a multi-lane arm is standing next to it. Only ever a correction -- if the
            # solver's pick is already the widest pair, it is left exactly as it was.
            width = {}
            for lane in arrivals.get(root, []) + departures.get(root, []):
                a = lane[0].rsplit("_", 1)[0]
                width[a] = max(width.get(a, 0), lane[4])
            rest = arms - trunk
            if rest and width and (min((width.get(a, 0) for a in trunk), default=0)
                                   < max(width.get(a, 0) for a in rest)):
                trunk = set(sorted(arms, key=lambda a: (-width.get(a, 0), a))[:2])
            gore_clusters.setdefault(root, []).append((frozenset(trunk), frozenset(arms)))
            trunk_arms.setdefault(root, set()).update(trunk)
        n_conn = 0
        for node_index, ins in arrivals.items():
            outs = departures.get(node_index, [])
            if not outs:
                continue
            # A merged node is as restrictive as its most restrictive member.
            members = [i for i in (list(parent) + [node_index]) if _find(i) == node_index]
            allow_cross = 1
            if vl.get("allow_cross") is not None:
                allow_cross = min(int(bm.verts[i][vl["allow_cross"]]) for i in set(members))
            allow_cross_by_node[node_index] = allow_cross
            clusters = gore_clusters.get(node_index, ())
            for lid_in, p_in, t_in, cix_in, n_in, aux_in in ins:
                arm_in = lid_in.rsplit("_", 1)[0]
                for lid_out, p_out, t_out, cix_out, n_out, aux_out in outs:
                    arm_out = lid_out.rsplit("_", 1)[0]
                    tarms = gore_rule_for(clusters, arm_in, arm_out)
                    is_gore = tarms is not None
                    turn = _turn_of(t_in, t_out)
                    why = movement_verdict(
                        (lid_in, p_in, t_in, cix_in, n_in, aux_in),
                        (lid_out, p_out, t_out, cix_out, n_out, aux_out),
                        turn, is_gore, tarms or (), allow_cross, ins, outs)
                    if why is not None:
                        continue
                    # A GORE'S MAINLINE IS NOT TRIMMED, so its in-lane ends exactly where the
                    # out-lane begins and there is no gap to bridge. Emitting a bezier between two
                    # coincident points yields a zero-length "lane" that `WorldBaker` silently
                    # skips -- the through movement then has no successor at all, which is a car
                    # sink at every merge. Chain the two lanes directly instead: a connector only
                    # exists to close a gap that trimming opened.
                    if math.dist(p_in, p_out) < MIN_CONNECTOR_LEN:
                        for lane in lanes:
                            if lane["id"] == lid_in and lid_out not in lane["next"]:
                                lane["next"].append(lid_out)
                        continue
                    pts_c = _bezier(p_in, t_in, p_out, t_out)
                    cid_name = "c%d_%s__%s" % (node_index, lid_in, lid_out)
                    lanes.append({"id": cid_name,
                                  "points": [_godot(p) for p in pts_c],
                                  "from_arm": arm_in, "kind": "connector", "turn": turn,
                                  "next": [lid_out]})
                    n_conn += 1
                    for lane in lanes:
                        if lane["id"] == lid_in and cid_name not in lane["next"]:
                            lane["next"].append(cid_name)
    finally:
        bm.free()
    stats = dict(lanes=len(lanes) - n_conn, connectors=n_conn,
                 nodes=sum(1 for k in kind_of.values() if k not in ('NONE', 'CAP')),
                 merged=len(merged), stubs=len(stubs))
    if want_context:
        return lanes, stats, dict(arrivals=arrivals, departures=departures,
                                  trunk_arms=trunk_arms, gore_clusters=gore_clusters,
                                  kind_of=kind_of,
                                  allow_cross=allow_cross_by_node, merged=merged)
    return lanes, stats


def audit_movements(graph_obj, traffic_side='LEFT'):
    """Movements that are geometrically fine and physically impossible, as printable lines.

    `graph_validate` checks the graph; this checks what the graph MEANS once it is turned into
    routes, which is where a whole class of defect lives that no amount of looking at the mesh
    reveals. Two rules, both learned from the island:

    * A ONE-WAY ARM FED FROM MORE THAN ONE CARRIAGEWAY. An exit ramp hangs off one side of a
      divided road; traffic on the other side reaching it has driven over the median. This is
      normally prevented by `allow_cross = 0` on the road's nodes -- so a hit here usually means
      that stamp is missing on a limited-access road, not that the rule is wrong (a diamond's
      on-ramp at a surface junction IS entered from both directions, and that junction breaks its
      median, so it should be reported only where the stamp says crossing is forbidden).
    * A RAMP NOT FED BY THE AUXILIARY LANE THAT OPENS FOR IT. If a trunk widens by a lane into a
      gore and the ramp is then fed from a through lane instead, the extra lane leads nowhere and
      the exit is taken from the middle of the carriageway."""
    lanes, _stats, ctx = collect(graph_obj, traffic_side, want_context=True)
    arrivals, departures = ctx["arrivals"], ctx["departures"]
    allow = ctx["allow_cross"]
    out = []

    def _arm(lid):
        return lid.rsplit("_", 1)[0]

    def _group(lid):
        return lid.rsplit("_", 1)[1][0]

    for node in sorted(set(list(arrivals) + list(departures))):
        ins, outs = arrivals.get(node, []), departures.get(node, [])
        groups = {}
        for lane in list(ins) + list(outs):
            groups.setdefault(_arm(lane[0]), set()).add(_group(lane[0]))
        # WHICH ARM IS THE RAMP IS NOT GUESSWORK -- `collect` already decided it, and this must use
        # the same answer or it reports on arms that are not ramps at all. Two false positives came
        # from guessing: "one-way" alone calls an expressway CARRIAGEWAY a ramp (they are one-way
        # by construction), and "one-way and narrower" additionally calls the trunk CONTINUATION a
        # ramp, because it is exactly one lane narrower wherever an auxiliary lane has just
        # dropped. The gore cluster names the trunk arms explicitly; everything else in the cluster
        # is a ramp. Where there is no cluster there is no gore, and no ramp to check.
        ramp_arms = set()
        for trunk, cluster_arms in ctx["gore_clusters"].get(node, ()):
            ramp_arms |= set(cluster_arms) - set(trunk)
        for arm in sorted(ramp_arms):
            if len(groups.get(arm, ())) != 1:
                continue                       # two-way arm: not a ramp
            exits = {o[0] for o in outs if _arm(o[0]) == arm}
            if not exits:
                continue
            feeders = set()
            for lane in lanes:
                if not set(lane["next"]) & exits:
                    continue
                src = (lane["id"].split("_", 1)[1].split("__")[0]
                       if lane["kind"] == "connector" else lane["id"])
                if _arm(src) != arm:
                    feeders.add(src)
            ways = {(_arm(f), _group(f)) for f in feeders}
            if len(ways) > 1 and not allow.get(node, 1):
                out.append("node %d: one-way arm %s is fed from %d carriageways (%s) although "
                           "allow_cross is off here" % (node, arm, len(ways), sorted(ways)))
            aux_feed = [i for i in ins if i[5] and _arm(i[0]) != arm]
            if aux_feed and not any(f in {a[0] for a in aux_feed} for f in feeders):
                out.append("node %d: one-way arm %s is fed from %s, not from the auxiliary lane "
                           "%s that opens for it"
                           % (node, arm, sorted(feeders), sorted(a[0] for a in aux_feed)))

    # AN AUXILIARY LANE THAT GOES NOWHERE, OR THAT NOTHING ENTERS. Both read on screen as a road
    # widening for an exit and are invisible to every check above, because each individual
    # movement at each individual node is legal -- the lane is simply orphaned at one end. Two
    # ways it happened here: an aux stamped on a one-way ramp at a fork of ramps (no mainline to
    # widen, so its second lane had no successor), and two gores in a row, where the first exit's
    # deceleration lane is exit-only and so could not also be the lane that feeds the second
    # exit's opening lane.
    # JUDGED AGAINST ITS OWN CARRIAGEWAY, not absolutely. A road that begins or ends at the edge of
    # the network has no upstream and no downstream, and every lane on it is unfed or unfollowed
    # for a reason that is not a defect. What IS a defect is an auxiliary lane orphaned while the
    # through lanes beside it are connected -- that is the lane the exit needs, missing exactly the
    # end that makes it usable.
    by_id = {lane["id"]: lane for lane in lanes}
    aux_ids, fed = set(), set()
    for lane in lanes:
        fed.update(lane["next"])
    for node_lanes in list(arrivals.values()) + list(departures.values()):
        aux_ids.update(lane[0] for lane in node_lanes if lane[5])
    for aid in sorted(aux_ids):
        lane = by_id.get(aid)
        if lane is None:
            continue
        siblings = [l for l in lanes if l["kind"] == "through" and l["id"] != aid
                    and _arm(l["id"]) == _arm(aid) and _group(l["id"]) == _group(aid)]
        if not lane["next"] and any(s["next"] for s in siblings):
            out.append("auxiliary lane %s opens into nothing while the through lanes beside it "
                       "carry on" % aid)
        if aid not in fed and any(s["id"] in fed for s in siblings):
            out.append("auxiliary lane %s is unreachable -- nothing moves into it, though the "
                       "through lanes beside it are fed" % aid)
    return out


def export(graph_obj, path, traffic_side='LEFT'):
    lanes, stats = collect(graph_obj, traffic_side)
    with open(path, "w") as fh:
        json.dump({"lanes": lanes}, fh, indent=1)
    return stats


#: Spacing and size of the direction chevrons drawn along every previewed lane.
FLOW_ARROW_SPACING = 22.0
FLOW_ARROW_SIZE = 2.6
#: Viewport display colour per lane kind, so flow reads at a glance in Solid mode with the
#: viewport shading colour set to "Object". Through lanes are the network; the three turn classes
#: are separated because "which movements exist at this junction" is the question a preview is for.
FLOW_COLOURS = {
    "through": (0.20, 0.75, 1.00, 1.0),
    "L": (0.30, 1.00, 0.35, 1.0),
    "S": (1.00, 0.85, 0.20, 1.0),
    "R": (1.00, 0.35, 0.30, 1.0),
}


def _lane_group(lane):
    """Which preview sub-collection a lane belongs in: the through network, or one turn class."""
    if lane.get("kind") != "connector":
        return "through"
    return "turn_%s" % (lane.get("turn") or "S")


def _flow_chevrons(lane_points, spacing=FLOW_ARROW_SPACING, size=FLOW_ARROW_SIZE):
    """`(verts, edges)` for a row of V chevrons along a polyline, opening BACKWARDS along travel.

    A chevron rather than a cone or a taper: it is two edges, so it costs nothing, it survives
    wireframe and Solid shading alike, and a V unambiguously reads as a direction even from
    directly above -- which is the view you actually plan a road network from. Spaced by arclength
    so a long straight gets a readable rhythm instead of one arrow per authored vertex."""
    verts, edges = [], []
    if len(lane_points) < 2:
        return verts, edges
    acc = spacing * 0.5          # first arrow half a step in, never exactly on the junction mouth
    for i in range(len(lane_points) - 1):
        a, b = lane_points[i], lane_points[i + 1]
        seg = math.dist((a[0], a[1], a[2]), (b[0], b[1], b[2]))
        if seg < 1e-6:
            continue
        while acc <= seg:
            t = acc / seg
            px = a[0] + (b[0] - a[0]) * t
            py = a[1] + (b[1] - a[1]) * t
            pz = a[2] + (b[2] - a[2]) * t
            dx, dy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            lx, ly = -dy, dx                      # left of travel
            base = len(verts)
            verts.append((px, py, pz))                                     # the point of the V
            verts.append((px - dx * size + lx * size * 0.55,
                          py - dy * size + ly * size * 0.55, pz))          # left barb
            verts.append((px - dx * size - lx * size * 0.55,
                          py - dy * size - ly * size * 0.55, pz))          # right barb
            edges.append((base, base + 1))
            edges.append((base, base + 2))
            acc += spacing
        acc -= seg
    return verts, edges


def preview(graph_obj, traffic_side='LEFT'):
    """Draw every exported lane as a real Blender Curve in `RKA_LANE_PREVIEW`, WITH ITS DIRECTION.

    The SAME `collect()` the exporter uses, converted back from Godot axes -- so the preview
    cannot drift from the file, which is exactly how the previous preview tool went stale.

    A bare polyline shows where a lane is and says nothing about which way it runs, which is half
    of what a road network is: you cannot tell an exit from an entry, a one-way from a two-way, or
    a correct merge from a head-on one. So the preview also gets:

      * `RKA_LANE_FLOW`, one edge-only mesh of direction chevrons along every lane. Edges, so it
        draws in any shading mode and costs almost nothing even at island scale.
      * sub-collections per kind -- the through network, and one per turn class -- so a junction's
        movement set can be isolated in the outliner, which is where you actually check whether
        the turns you expect exist.
      * a per-object viewport colour by the same classification (visible in Solid shading with
        Color set to Object).
    """
    lanes, stats = collect(graph_obj, traffic_side)
    coll = bpy.data.collections.get(PREVIEW_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(PREVIEW_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    for child in list(coll.children):
        for ob in list(child.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        coll.children.unlink(child)
        if not child.users:
            bpy.data.collections.remove(child)
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    groups = {}

    def _group(name):
        if name not in groups:
            sub = bpy.data.collections.new("%s_%s" % (PREVIEW_COLLECTION, name))
            coll.children.link(sub)
            groups[name] = sub
        return groups[name]

    flow_verts, flow_edges = [], []
    for lane in lanes:
        pts = [(gp[0], -gp[2], gp[1]) for gp in lane["points"]]   # Godot -> Blender
        cu = bpy.data.curves.new(lane["id"], 'CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p[0], p[1], p[2], 1.0)
        ob = bpy.data.objects.new(lane["id"], cu)
        ob["rka_lane_kind"] = lane.get("kind", "")
        ob["rka_lane_turn"] = lane.get("turn", "")
        ob["rka_lane_next"] = ", ".join(lane.get("next", []))
        group = _lane_group(lane)
        ob.color = FLOW_COLOURS.get(group.replace("turn_", "") if group != "through"
                                    else "through", (1.0, 1.0, 1.0, 1.0))
        _group(group).objects.link(ob)
        v, e = _flow_chevrons(pts)
        base = len(flow_verts)
        flow_verts.extend(v)
        flow_edges.extend((a + base, b + base) for a, b in e)

    old = bpy.data.objects.get(FLOW_OBJECT)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(FLOW_OBJECT)
    me.from_pydata(flow_verts, flow_edges, [])
    me.update()
    flow = bpy.data.objects.new(FLOW_OBJECT, me)
    flow.color = (1.0, 1.0, 1.0, 1.0)
    coll.objects.link(flow)
    stats["arrows"] = len(flow_edges) // 2
    return stats


class RKA_OT_graph_explain_node(bpy.types.Operator):
    """Print every candidate movement at the selected junction, and why each is or is not built."""
    bl_idname = "rka.graph_explain_node"
    bl_label = "Explain Selected Junction"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        sel = [v.index for v in obj.data.vertices if v.select]
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        if not sel:
            self.report({'WARNING'}, "Select the junction vertex first")
            return {'CANCELLED'}
        total = 0
        for idx in sel[:4]:
            for line in explain_node(obj, idx):
                print("[rka] " + line)
            total += 1
        self.report({'INFO'}, "Explained %d junction(s) -- see the console" % total)
        return {'FINISHED'}


class RKA_OT_graph_export_lanekit(bpy.types.Operator):
    """Write a `.lanekit.json` for Godot beside the .blend."""
    bl_idname = "rka.graph_export_lanekit"
    bl_label = "Export Lanes (.lanekit.json)"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        base = bpy.data.filepath or os.path.join(bpy.app.tempdir, "untitled.blend")
        path = os.path.splitext(base)[0] + ".lanekit.json"
        stats = export(obj, path)
        self.report({'INFO'}, "%d lanes + %d connectors across %d junctions -> %s"
                    % (stats["lanes"], stats["connectors"], stats["nodes"],
                       os.path.basename(path)))
        return {'FINISHED'}


class RKA_OT_graph_preview_lanes(bpy.types.Operator):
    """Draw the exported lane paths in the viewport."""
    bl_idname = "rka.graph_preview_lanes"
    bl_label = "Preview Lane Paths"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return RKA_OT_graph_export_lanekit.poll(context)

    def execute(self, context):
        stats = preview(ga.graph_object(context))
        self.report({'INFO'}, "%d lanes + %d connectors previewed"
                    % (stats["lanes"], stats["connectors"]))
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_export_lanekit, RKA_OT_graph_preview_lanes,
           RKA_OT_graph_explain_node)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
