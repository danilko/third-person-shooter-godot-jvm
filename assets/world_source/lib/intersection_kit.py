"""Pure-Python intersection corner/turn geometry -- no bpy, self-testable.

Companion to road_graph.py/lane_kit.py's convention (pure math module, `python3
lib/intersection_kit.py` self-tests). Consumed by the road_kit_authoring addon's
`ops_intersection.py` (RKA_OT_build_intersection).

Given a set of "arms" -- approach roads meeting at one point, each described only by an outward
angle -- computes:
  - a rounded CURB corner between every pair of angularly-adjacent arms, EXCEPT a "through pair"
    (two arms exactly opposite each other, i.e. one straight street passing through the
    junction): there the curb is already one continuous straight line and there is no corner to
    round, so it is skipped entirely (see `is_through_pair`, verified in self_test).
  - a driving CENTERLINE for every legal single-lane movement (arm A's incoming lane -> arm B's
    outgoing lane): a plain straight line for a through-pair movement, a filleted (rounded) arc
    for a turn, using a LARGER radius than the curb (kerb_radius + this lane's own offset from
    the curb, see `build_lane_movements`) -- a bigger, AI-comfortable arc, not the tight curb
    radius a real small vehicle would hug.

All geometry is 2D (x, y); callers add a constant world Z.
"""
import math

TAU = 2.0 * math.pi


def deg2rad(d):
    return d * math.pi / 180.0


def arm_dir(angle_deg):
    r = deg2rad(angle_deg)
    return (math.cos(r), math.sin(r))


def perp_ccw(v):
    return (-v[1], v[0])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def vscale(a, s):
    return (a[0] * s, a[1] * s)


def vlen(a):
    return math.hypot(a[0], a[1])


def vnorm(a):
    L = vlen(a)
    if L < 1e-9:
        raise ValueError("cannot normalize a zero-length vector")
    return (a[0] / L, a[1] / L)


def angle_norm(deg):
    return deg % 360.0


def is_through_pair(angle_a, angle_b, tol_deg=2.0):
    """True if two arm angles are ~180 degrees apart -- opposite ends of one straight street, so
    the curb between them (going around the junction) is already straight; skip filleting it."""
    diff = (angle_a - angle_b) % 360.0
    return abs(diff - 180.0) <= tol_deg


def line_intersect_2d(p1, d1, p2, d2, eps=1e-9):
    """Intersection of two infinite 2D lines, each given as point + direction. None if parallel."""
    det = d1[0] * (-d2[1]) - (-d2[0]) * d1[1]
    if abs(det) < eps:
        return None
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    t = (rx * (-d2[1]) - (-d2[0]) * ry) / det
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


class Arm:
    """One approach road meeting the intersection center. `angle_deg` points OUTWARD -- the
    direction a car travels leaving the intersection along this arm. `lanes` is the lane count
    PER DIRECTION (symmetric: as many lanes arriving as leaving), UNLESS `oneway` overrides one
    side to zero -- `oneway='IN'` means this arm only ever RECEIVES traffic (no outgoing lanes,
    e.g. a one-way street feeding into the junction); `oneway='OUT'` means it only ever SENDS
    traffic (no incoming lanes, e.g. a one-way exit). `None` (default) is the original symmetric
    behavior -- `lanes_in_count()`/`lanes_out_count()` both just return `lanes`, so every existing
    caller that never set `oneway` is unaffected."""

    def __init__(self, name, angle_deg, lane_width=5.0, lanes=1, oneway=None):
        self.name = name
        self.angle_deg = angle_norm(angle_deg)
        self.lane_width = lane_width
        self.lanes = lanes
        self.oneway = oneway   # None | 'IN' | 'OUT'

    def lanes_in_count(self):
        """How many lanes ARRIVE at the junction along this arm (0 if `oneway == 'OUT'`)."""
        return 0 if self.oneway == 'OUT' else self.lanes

    def lanes_out_count(self):
        """How many lanes LEAVE the junction along this arm (0 if `oneway == 'IN'`)."""
        return 0 if self.oneway == 'IN' else self.lanes

    def half_width(self):
        """Curb-to-centerline distance -- the physical road width, unaffected by `oneway` (a
        one-way arm is still as wide as its `lanes` count, just carrying traffic one direction)."""
        return self.lane_width * self.lanes

    def in_offset(self, i):
        """Signed perpendicular offset (CW side) of the i-th arriving lane's own centerline."""
        return -(i + 0.5) * self.lane_width

    def out_offset(self, i):
        """Signed perpendicular offset (CCW side) of the i-th leaving lane's own centerline."""
        return (i + 0.5) * self.lane_width


def corner_fillet(edge_a, edge_b, radius, segments=8):
    """edge_a, edge_b: (point, direction) tuples, each direction pointing AWAY from their shared
    (unrounded) vertex along its own line. Returns (vertex, trim_a, trim_b, arc_points): arc_points
    is `segments`+1 points from trim_a to trim_b inclusive, each exactly `radius` from the arc
    center, tangent to both edges at trim_a/trim_b."""
    va, da = edge_a
    vb, db = edge_b
    vertex = line_intersect_2d(va, da, vb, db)
    if vertex is None:
        raise ValueError("edges are parallel -- no corner to fillet (this is a through-pair; "
                          "skip filleting it, see is_through_pair)")
    da = vnorm(da)
    db = vnorm(db)
    cosang = max(-1.0, min(1.0, da[0] * db[0] + da[1] * db[1]))
    theta = math.acos(cosang)
    if theta < 1e-6 or theta > math.pi - 1e-6:
        raise ValueError("degenerate corner angle (~0 or ~180 deg) -- cannot fillet")
    tangent_len = radius / math.tan(theta / 2.0)
    trim_a = vadd(vertex, vscale(da, tangent_len))
    trim_b = vadd(vertex, vscale(db, tangent_len))
    bis = vnorm(vadd(da, db))
    center = vadd(vertex, vscale(bis, radius / math.sin(theta / 2.0)))
    ang_a = math.atan2(trim_a[1] - center[1], trim_a[0] - center[0])
    ang_b = math.atan2(trim_b[1] - center[1], trim_b[0] - center[0])
    dtheta = ang_b - ang_a
    while dtheta <= -math.pi:
        dtheta += TAU
    while dtheta > math.pi:
        dtheta -= TAU
    arc_points = []
    for k in range(segments + 1):
        t = ang_a + dtheta * (k / segments)
        arc_points.append((center[0] + radius * math.cos(t), center[1] + radius * math.sin(t)))
    return vertex, trim_a, trim_b, arc_points


def consecutive_pairs(arms):
    """Arms sorted by angle, paired with their angularly-next neighbour going counter-clockwise
    (wrapping from the last back to the first) -- one pair per curb corner around the loop."""
    ordered = sorted(arms, key=lambda a: a.angle_deg)
    n = len(ordered)
    return [(ordered[k], ordered[(k + 1) % n]) for k in range(n)]


def curb_edges(arm_a, arm_b):
    """The two curb-edge rays (point, direction) meeting at the corner between CCW-adjacent
    arm_a -> arm_b: arm_a's CCW (leaving-lane) side and arm_b's CW (arriving-lane) side."""
    da, db = arm_dir(arm_a.angle_deg), arm_dir(arm_b.angle_deg)
    pa, pb = perp_ccw(da), perp_ccw(db)
    edge_a = (vscale(pa, arm_a.half_width()), da)
    edge_b = (vscale(pb, -arm_b.half_width()), db)
    return edge_a, edge_b


def build_curb_corners(arms, kerb_radius, segments=8, through_tol_deg=2.0):
    """One dict per angularly-consecutive arm pair that is NOT a through-pair:
    {'arm_a', 'arm_b', 'vertex', 'trim_a', 'trim_b', 'arc': [(x,y), ...]}."""
    out = []
    for a, b in consecutive_pairs(arms):
        if is_through_pair(a.angle_deg, b.angle_deg, through_tol_deg):
            continue
        vertex, trim_a, trim_b, arc = corner_fillet(*curb_edges(a, b), kerb_radius, segments)
        out.append({"arm_a": a.name, "arm_b": b.name, "vertex": vertex,
                     "trim_a": trim_a, "trim_b": trim_b, "arc": arc})
    return out


def turn_side(entry_dir, exit_dir):
    """'L'/'R'/'S' classification of a movement from `entry_dir` (heading while arriving) to
    `exit_dir` (heading while leaving), both unit 2D vectors. Sign convention (fixed, self-tested
    below, arbitrary but consistent -- nothing downstream currently branches on L vs R, only on
    turn != 'S'/''): positive 2D cross product (exit CCW of entry) = 'L'."""
    cross = entry_dir[0] * exit_dir[1] - entry_dir[1] * exit_dir[0]
    if cross > 1e-6:
        return "L"
    if cross < -1e-6:
        return "R"
    return "S"


def build_lane_movements(arms, kerb_radius, segments=8, through_tol_deg=2.0, tail_length=12.0,
                          junction_id="J", lane_map=None):
    """One dict per legal lane movement: {'id', 'from', 'to', 'lane' (alias of 'lane_in'),
    'lane_in', 'lane_out', 'kind' ('through'|'turn'), 'turn' ('L'|'S'|'R'), 'points':
    [(x,y), ...]}. A 'turn' polyline is filleted at radius = kerb_radius + the wider of the two
    lanes' own offset from the curb (bigger than the curb's own radius -- a wider, AI-comfortable
    swing, not a tight hug of the corner). A 'through' polyline is a straight 2-point line. `id`
    is globally unique given a unique `junction_id`.

    By default, for each ordered arm pair (a, b), in-lane i feeds out-lane i for
    i in 0..min(a.lanes, b.lanes)-1 (the only sane default when nothing else is specified).

    `lane_map` -- optional {(from_arm_name, to_arm_name): [(in_lane, out_lane), ...]} --
    OVERRIDES that default pairing per arm-pair, so a movement's exact lane-to-lane connection can
    be hand-authored as data instead of derived: e.g. a deliberate lane shift/merge, or (this is
    the mechanism that resolves the "which incoming lane feeds which outgoing lane" ambiguity
    noted as the open question for asymmetric in/out lane counts -- see road_blender_godot.md)
    once an arm's own in/out counts ever differ. Every (in_lane, out_lane) pair is validated
    against the arms' own lane counts -- raises ValueError on an out-of-range index (an authoring
    mistake, not a case to silently drop)."""
    lane_map = lane_map or {}
    out = []
    for a in arms:
        for b in arms:
            if a is b:
                continue
            da, db = arm_dir(a.angle_deg), arm_dir(b.angle_deg)
            through = is_through_pair(a.angle_deg, b.angle_deg, through_tol_deg)
            override = lane_map.get((a.name, b.name))
            if override is not None:
                pairs = list(override)
                for li, lo in pairs:
                    if not (0 <= li < a.lanes_in_count()):
                        raise ValueError("lane_map[%r]: in_lane %d out of range for arm %r (%d "
                                          "incoming lanes)" % ((a.name, b.name), li, a.name, a.lanes_in_count()))
                    if not (0 <= lo < b.lanes_out_count()):
                        raise ValueError("lane_map[%r]: out_lane %d out of range for arm %r (%d "
                                          "outgoing lanes)" % ((a.name, b.name), lo, b.name, b.lanes_out_count()))
            else:
                # a's ARRIVING lanes feed b's LEAVING lanes -- an arm with oneway='OUT' (0
                # incoming lanes) can never be a `from`, and one with oneway='IN' (0 outgoing
                # lanes) can never be a `to`; both fall out for free since min(...) is 0.
                pairs = [(i, i) for i in range(min(a.lanes_in_count(), b.lanes_out_count()))]

            for li, lo in pairs:
                lane_id = ("%s_%s_%s_L%d" % (junction_id, a.name, b.name, li) if li == lo else
                           "%s_%s_%s_L%dto%d" % (junction_id, a.name, b.name, li, lo))
                p_in = vscale(perp_ccw(da), a.in_offset(li))
                p_out = vscale(perp_ccw(db), b.out_offset(lo))
                if through:
                    pts = [vadd(p_in, vscale(da, tail_length)),
                           vadd(p_out, vscale(db, tail_length))]
                    out.append({"id": lane_id, "from": a.name, "to": b.name, "lane": li,
                                "lane_in": li, "lane_out": lo, "kind": "through", "turn": "S",
                                "points": pts})
                else:
                    radius = kerb_radius + (max(li, lo) + 0.5) * max(a.lane_width, b.lane_width)
                    edge_in = (p_in, da)
                    edge_out = (p_out, db)
                    try:
                        _, trim_in, trim_out, arc = corner_fillet(edge_in, edge_out, radius, segments)
                    except ValueError:
                        continue  # near-collinear/degenerate arm pair at this radius -- skip
                    # Measured from p_in/p_out (the arm's own reference line), NOT trim_in/trim_out,
                    # so a straight-through and a turning movement sharing the same (arm, lane)
                    # reach the IDENTICAL far point -- they are physically the same incoming/outgoing
                    # lane before/after the split, and this is what makes build_ports' per-(arm,lane)
                    # port position independent of which movement is asked. Guarded with max() so a
                    # `tail_length` shorter than the fillet's own tangent length still produces a
                    # correctly-ordered polyline (far point strictly beyond the arc, never behind it).
                    t_in = vlen(vsub(trim_in, p_in)) + 1.0
                    t_out = vlen(vsub(trim_out, p_out)) + 1.0
                    entry_far = vadd(p_in, vscale(da, max(tail_length, t_in)))
                    exit_far = vadd(p_out, vscale(db, max(tail_length, t_out)))
                    pts = [entry_far] + arc + [exit_far]
                    tside = turn_side(vscale(da, -1.0), db)
                    out.append({"id": lane_id, "from": a.name, "to": b.name, "lane": li,
                                "lane_in": li, "lane_out": lo, "kind": "turn", "turn": tside,
                                "points": pts})
    return out


def build_ports(arms, tail_length=12.0):
    """One 'in' and one 'out' port per (arm, lane index) -- the world position + outward tangent
    of the far end of each lane's tail, where generated geometry currently stops. These are the
    seams a future cross-piece linker (or a plain approach lane tile) would connect to: one dict
    per port: {'id', 'arm', 'lane', 'direction' ('in'|'out'), 'position': (x,y), 'tangent': (x,y)}.
    An 'in' port's tangent points INTO the junction (the direction a car heading toward the
    junction on that lane travels); an 'out' port's tangent points AWAY from it.

    Matches a 'through'/'turn' movement's own far point from `build_lane_movements` EXACTLY
    whenever `tail_length` comfortably exceeds that movement's fillet tangent length (true for any
    reasonable tail_length/kerb_radius pairing) -- movements only extend further than this plain
    `tail_length` via their own max()-guard in the rare case a too-short tail_length would
    otherwise land short of the arc."""
    out = []
    for a in arms:
        d = arm_dir(a.angle_deg)
        perp = perp_ccw(d)
        for i in range(a.lanes_in_count()):
            in_pos = vadd(vscale(perp, a.in_offset(i)), vscale(d, tail_length))
            out.append({"id": "%s_in_L%d" % (a.name, i), "arm": a.name, "lane": i,
                        "direction": "in", "position": in_pos, "tangent": vscale(d, -1.0)})
        for i in range(a.lanes_out_count()):
            out_pos = vadd(vscale(perp, a.out_offset(i)), vscale(d, tail_length))
            out.append({"id": "%s_out_L%d" % (a.name, i), "arm": a.name, "lane": i,
                        "direction": "out", "position": out_pos, "tangent": d})
    return out


# --------------------------------------------------------------------------------- presets

def _per_arm(value, n):
    """`value` is either one scalar (applied to all n arms, back-compat) or a sequence of n
    values (independent per-arm lane counts -- a 2-lane main street crossing a 1-lane side
    street). Raises if a sequence is the wrong length (a silent truncate/pad would hide a typo)."""
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError("expected %d per-arm values, got %d" % (n, len(value)))
        return list(value)
    return [value] * n


def preset_nway(angles, lane_width=5.0, lanes=1, names=None):
    """Generic N-arm constructor -- any number of arms at any angles. `lanes` is either one
    scalar (every arm the same) or a sequence parallel to `angles` (independent per-arm lane
    counts, see `_per_arm`). `names` defaults to A, B, C, ... ."""
    n = len(angles)
    if names is None:
        names = [chr(ord('A') + i) if i < 26 else "Arm%d" % i for i in range(n)]
    lanes_per_arm = _per_arm(lanes, n)
    return [Arm(names[i], angles[i], lane_width, lanes_per_arm[i]) for i in range(n)]


def preset_4way(angles=(0.0, 90.0, 180.0, 270.0), lane_width=5.0, lanes=1):
    return preset_nway(angles, lane_width, lanes, names=("N", "E", "S", "W"))


def preset_3way_t(through_angle=0.0, side_angle=90.0, lane_width=5.0, lanes=1):
    """Two collinear arms (the through street) + one side arm -- a T with a direct through move.
    `lanes` is either one scalar or a 3-sequence [through_arm_a, through_arm_b, side_arm]."""
    return preset_nway((through_angle, through_angle + 180.0, side_angle), lane_width, lanes,
                        names=("A", "B", "C"))


def preset_3way_y(angles=(0.0, 120.0, 240.0), lane_width=5.0, lanes=1):
    """Three arms at generic (non-collinear) angles -- every movement is a turn, all 3 corners
    filleted, no direct through-street."""
    return preset_nway(angles, lane_width, lanes, names=("A", "B", "C"))


# --------------------------------------------------------------------------------- straight segments

def _bezier_sample(p0, control, p1, segments):
    pts = []
    for k in range(segments + 1):
        t = k / segments
        mt = 1.0 - t
        pts.append((mt * mt * p0[0] + 2 * mt * t * control[0] + t * t * p1[0],
                    mt * mt * p0[1] + 2 * mt * t * control[1] + t * t * p1[1]))
    return pts


def segment_spine_3d(p0, p1, bend=0.0, segments=8, z0=0.0, z1=0.0, bend_z=0.0):
    """The raw 3D spine polyline `build_straight_segment` offsets curbs/lanes from, factored out
    so a caller with its OWN already-resolved spine (e.g. sampled from a hand-authored Blender
    Curve object -- see the addon's `RKA_OT_build_segment_from_curve`) can feed
    `build_segment_from_spine` directly instead of going through this p0/p1/bend parametric model.
    See `build_straight_segment`'s docstring for what `bend`/`z0`/`z1`/`bend_z` mean; z is RELATIVE
    (0-based), same convention as there."""
    if bend == 0.0 and bend_z == 0.0:
        spine_2d = [p0, p1]
    else:
        # Also subdivides a laterally-straight (bend=0) spine when bend_z != 0 -- a quadratic
        # bezier whose control point IS the midpoint (no lateral offset) degenerates to an exact
        # linear subdivision (B(t) = (1-t)*p0 + t*p1), so this stays byte-identical to a straight
        # line in XY while still producing `segments`+1 samples for z_at's midpoint bump to land on.
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        control = vadd(mid, vscale(perp_ccw(vnorm(vsub(p1, p0))), bend))
        spine_2d = _bezier_sample(p0, control, p1, segments)

    n = len(spine_2d)

    def z_at(i):
        t = (i / (n - 1)) if n > 1 else 0.0
        return z0 + (z1 - z0) * t + bend_z * 4.0 * t * (1.0 - t)

    return [(p[0], p[1], z_at(i)) for i, p in enumerate(spine_2d)]


def build_segment_from_spine(spine, lane_width=5.0, lanes=1, lanes_backward=None, segment_id="SEG"):
    """Core segment geometry: offset curbs + per-lane centerlines from an ARBITRARY 3D spine
    polyline `spine = [(x, y, z), ...]` (already resolved -- straight, bent, sloped, or sampled
    from a hand-authored curve; this function doesn't care which). Every point is offset from a
    LOCAL per-point tangent, so the result genuinely follows whatever shape `spine` traces, not
    just a 2-point line or a single bezier bump.

    `lanes` is the FORWARD (A->B) lane count; `lanes_backward` is the REVERSE (B->A) count,
    defaulting to `lanes` (symmetric, the historical/default behavior) when left `None`. Either
    may be 0 -- a fully ONE-WAY road is `lanes=1, lanes_backward=0` (or vice versa); at least one
    of the two must be nonzero (raises `ValueError` otherwise -- a road with no lanes in either
    direction isn't a road). The curb offset uses the WIDER of the two directions, so the road is
    always at least as wide as its busiest side; a symmetric call (`lanes_backward=None` or equal
    to `lanes`) is byte-identical to the pre-asymmetric-lanes behavior.

    Same JSON lane shape as `build_lane_movements` -- {'id','from','to','lane_in','lane_out',
    'kind':'through','turn':'S','points':[...]} -- one entry per lane index per direction that
    actually has lanes, plus {'curbs': [[...], [...]]} for the two curb lines. Consumed
    identically to an intersection's movements by `export_segment_from_spine_json`/`WorldBaker`."""
    lanes_backward = lanes if lanes_backward is None else lanes_backward
    if lanes <= 0 and lanes_backward <= 0:
        raise ValueError("a segment needs at least one lane in SOME direction "
                          "(lanes=%d, lanes_backward=%d)" % (lanes, lanes_backward))
    n = len(spine)

    def tangent_at(i):
        a, b = spine[max(0, i - 1)], spine[min(n - 1, i + 1)]
        return vnorm(vsub((b[0], b[1]), (a[0], a[1])))

    def offset_line(off):
        return [(*vadd((spine[i][0], spine[i][1]), vscale(perp_ccw(tangent_at(i)), off)), spine[i][2])
                for i in range(n)]

    half_w = max(lanes, lanes_backward) * lane_width
    curbs = [offset_line(half_w), offset_line(-half_w)]

    lane_list = []
    for i in range(lanes):
        off = (i + 0.5) * lane_width
        lane_list.append({"id": "%s_A_B_L%d" % (segment_id, i), "from": "A", "to": "B",
                           "lane_in": i, "lane_out": i, "kind": "through", "turn": "S",
                           "points": offset_line(off)})
    for i in range(lanes_backward):
        off = (i + 0.5) * lane_width
        lane_list.append({"id": "%s_B_A_L%d" % (segment_id, i), "from": "B", "to": "A",
                           "lane_in": i, "lane_out": i, "kind": "through", "turn": "S",
                           "points": list(reversed(offset_line(-off)))})
    return {"curbs": curbs, "lanes": lane_list}


def build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="SEG", bend=0.0, segments=8,
                            z0=0.0, z1=0.0, bend_z=0.0, lanes_backward=None):
    """A two-way (or, with `lanes_backward`, asymmetric/one-way) road segment between two world
    points p0 -> p1 (2D XY) -- the piece missing between intersections (`build_curb_corners` only
    ever draws the ROUNDED corners, not the straight curb run along an arm's own sides). `bend`
    (meters, default 0.0 = dead straight) inserts a quadratic-bezier control point offset from the
    segment's own midpoint by that much (positive = left of p0->p1 travel), gently curving the
    road in the XY plane; `segments` is the resulting polyline's smoothness (ignored when bend is
    0). `z0`/`z1` (relative elevation at p0/p1 -- a constant grade when they differ) and `bend_z`
    (a vertical crest/dip bump at the midpoint, independent of the lateral `bend`) control slope --
    see `segment_spine_3d`. `lanes_backward` -- see `build_segment_from_spine` -- defaults to
    `lanes` (symmetric, unchanged from before this parameter existed).

    Thin wrapper: computes the spine via `segment_spine_3d`, then delegates the actual curb/lane
    geometry to `build_segment_from_spine` -- see that function's docstring for the returned
    shape. Kept as a separate entry point for the common "two points + a scalar bend" case; a
    hand-authored curve path goes through `build_segment_from_spine` directly instead."""
    spine = segment_spine_3d(p0, p1, bend, segments, z0, z1, bend_z)
    return build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id)


def export_segment_from_spine_json(path, spine, lane_width=5.0, lanes=1, lanes_backward=None,
                                    segment_id="SEG"):
    """Write `build_segment_from_spine`'s lane data to `path` as JSON, same shape/axis-conversion
    convention as `export_json` (`godot = (blender_x, z, -blender_y)`) -- unlike
    `export_segment_json`, `spine` already carries ABSOLUTE world Z per point (e.g. sampled
    directly from a Blender Curve object's evaluated world-space points), so no separate `z` base
    argument is added here."""
    import json
    seg = build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id)
    lanes_out = [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                   "lane_index": m["lane_in"], "lane_index_out": m["lane_out"], "kind": m["kind"],
                   "turn": m["turn"], "oneway": True, "loop": False,
                   "points": [[p[0], p[2], -p[1]] for p in m["points"]]} for m in seg["lanes"]]
    d = {"segment_id": segment_id, "lanes": lanes_out}
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


def export_segment_json(path, p0, p1, lane_width=5.0, lanes=1, segment_id="SEG", z=0.0,
                         bend=0.0, segments=8, z0=0.0, z1=0.0, bend_z=0.0, lanes_backward=None):
    """Write `build_straight_segment`'s lane data to `path` as JSON, same shape/axis-conversion
    convention as `export_json` (`godot = (blender_x, z, -blender_y)`) -- `WorldBaker`'s sidecar
    loader only ever reads the `lanes` array (`id`/`points`/`loop`/`turn`/`kind`), so this is
    directly consumable with no Java changes. `z` is the constant world-height base (as before);
    each point's own relative elevation (`z0`/`z1`/`bend_z` -- see `build_straight_segment`) is
    ADDED on top, so a flat segment (all defaults) emits exactly `z` unchanged, byte-identical to
    before this parameter existed. `curbs` are exported too (2D-only in this module; the caller
    building Blender geometry uses the un-exported `build_straight_segment` return directly for
    those, same as it already does for intersection corners)."""
    import json
    seg = build_straight_segment(p0, p1, lane_width, lanes, segment_id, bend, segments, z0, z1,
                                  bend_z, lanes_backward)
    lanes_out = [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                   "lane_index": m["lane_in"], "lane_index_out": m["lane_out"], "kind": m["kind"],
                   "turn": m["turn"], "oneway": True, "loop": False,
                   "points": [[p[0], z + p[2], -p[1]] for p in m["points"]]} for m in seg["lanes"]]
    d = {"segment_id": segment_id, "lanes": lanes_out}
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


# --------------------------------------------------------------------------------- export

def export_dict(arms, kerb_radius, junction_id, segments=8, through_tol_deg=2.0, tail_length=12.0,
                 lane_map=None):
    """The full graph-shaped export for one junction -- arms as nodes, lane movements as directed
    edges, ports as the seams a future cross-piece linker (or a plain approach lane tile) would
    connect to. Pure data (2D points; a Z is added by the caller, since this module never carries
    one). `lane_map` -- see `build_lane_movements` -- optionally overrides the default
    lane-to-lane pairing. See `export_json` to write it straight to a sidecar file."""
    movements = build_lane_movements(arms, kerb_radius, segments, through_tol_deg, tail_length,
                                      junction_id=junction_id, lane_map=lane_map)
    ports = build_ports(arms, tail_length)
    return {
        "junction_id": junction_id,
        "arms": [{"name": a.name, "angle_deg": a.angle_deg, "lanes": a.lanes,
                   "lane_width": a.lane_width, "lanes_in": a.lanes_in_count(),
                   "lanes_out": a.lanes_out_count(), "oneway": a.oneway} for a in arms],
        "lanes": [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                    "lane_index": m["lane_in"], "lane_index_out": m["lane_out"],
                    "kind": m["kind"], "turn": m["turn"], "oneway": True, "loop": False,
                    "points": [list(p) for p in m["points"]]} for m in movements],
        "ports": [{"id": "%s_%s" % (junction_id, p["id"]), "arm": p["arm"], "lane": p["lane"],
                    "direction": p["direction"], "position": list(p["position"]),
                    "tangent": list(p["tangent"])} for p in ports],
    }


def export_json(path, arms, kerb_radius, junction_id, segments=8, through_tol_deg=2.0,
                 tail_length=12.0, z=0.0, lane_map=None):
    """Write `export_dict`'s data to `path` as JSON, with every 2D (Blender ground-plane) point
    lifted to a 3D **Godot-space** point (this module's 2D math is Blender's X/Y ground plane,
    Z-up; Godot is Y-up) so the Godot side can consume the sidecar's points as world-space
    positions directly, with no axis swizzle of its own to remember: `godot = (blender_x, z,
    -blender_y)` -- the same Blender-Z-up -> Godot-Y-up convention glTF import already applies
    to every other Blender-authored asset in this project, just applied here by hand since this
    sidecar is raw JSON, not glTF. `z` is the (small, near-constant) world height every point
    sits at -- becomes Godot's Y. No bpy dependency -- callable from a plain `python3`
    self-test/CI check, not just from inside Blender."""
    import json
    d = export_dict(arms, kerb_radius, junction_id, segments, through_tol_deg, tail_length, lane_map)
    for lane in d["lanes"]:
        lane["points"] = [[p[0], z, -p[1]] for p in lane["points"]]
    for port in d["ports"]:
        port["position"] = [port["position"][0], z, -port["position"][1]]
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


# --------------------------------------------------------------------------------- self-test

def self_test():
    eps = 1e-6

    # 1. corner_fillet: trims are exactly `radius` from the arc center and lie on their edges.
    edge_a = ((5.0, 0.0), (1.0, 0.0))   # arm at 0 deg, half_width=5
    edge_b = ((0.0, -5.0), (0.0, 1.0))  # arm at 90 deg, half_width=5, CW side (-perp)
    vertex, trim_a, trim_b, arc = corner_fillet(edge_a, edge_b, radius=6.0, segments=8)
    assert abs(vertex[0]) < eps and abs(vertex[1]) < eps, vertex  # y=0 line meets x=0 line at origin
    # recompute center explicitly from trim_a/trim_b and verify all arc points sit at `radius`
    # (trim_a, trim_b, and the bisector direction already computed inside corner_fillet; redo the
    # center calc here independently as a cross-check)
    da = vnorm((1.0, 0.0)); db = vnorm((0.0, 1.0))
    theta = math.acos(da[0]*db[0] + da[1]*db[1])
    bis = vnorm(vadd(da, db))
    true_center = vadd(vertex, vscale(bis, 6.0 / math.sin(theta / 2.0)))
    for p in arc:
        d = vlen(vsub(p, true_center))
        assert abs(d - 6.0) < 1e-6, (p, d)
    assert vlen(vsub(arc[0], trim_a)) < eps
    assert vlen(vsub(arc[-1], trim_b)) < eps
    print("OK: corner_fillet trims + arc all at exact radius")

    # 2. is_through_pair
    assert is_through_pair(0.0, 180.0)
    assert is_through_pair(10.0, 189.5)
    assert not is_through_pair(0.0, 90.0)
    assert not is_through_pair(0.0, 170.0)
    print("OK: is_through_pair")

    # 3. 4-way symmetric cross: 4 corners, all congruent (same distance from origin, 90 deg apart)
    arms = preset_4way()
    corners = build_curb_corners(arms, kerb_radius=8.0, segments=8)
    assert len(corners) == 4, len(corners)
    dists = sorted(round(vlen(c["vertex"]), 6) for c in corners)
    assert max(dists) - min(dists) < eps, dists
    print("OK: 4-way produces 4 congruent corners, dist=%.3f" % dists[0])

    # 4. 3-way T: only 2 corners (through-pair gap skipped); confirm the skipped pair's edges
    #    really are collinear (both curb_edges lines pass through the same points/directions).
    arms_t = preset_3way_t(through_angle=0.0, side_angle=90.0)
    corners_t = build_curb_corners(arms_t, kerb_radius=8.0, segments=8)
    assert len(corners_t) == 2, len(corners_t)
    a_arm = next(a for a in arms_t if a.name == "A")   # 0 deg
    b_arm = next(a for a in arms_t if a.name == "B")   # 180 deg (through partner of A)
    edge_a, edge_b = curb_edges(a_arm, b_arm)
    # collinear check: cross product of directions ~0, and edge_b's point lies on edge_a's line
    cross = edge_a[1][0] * edge_b[1][1] - edge_a[1][1] * edge_b[1][0]
    assert abs(cross) < eps, cross
    onlinecheck = (edge_b[0][0] - edge_a[0][0]) * edge_a[1][1] - (edge_b[0][1] - edge_a[0][1]) * edge_a[1][0]
    assert abs(onlinecheck) < eps, onlinecheck
    print("OK: 3-way T skips the through-pair corner (edges verified collinear)")

    # 5. 3-way Y: all generic angles, no through-pair -> 3 corners
    arms_y = preset_3way_y()
    corners_y = build_curb_corners(arms_y, kerb_radius=8.0, segments=8)
    assert len(corners_y) == 3, len(corners_y)
    print("OK: 3-way Y produces 3 corners (no through-street)")

    # 6. Lane movements: 4-way has 4*3=12 ordered from!=to pairs, all single-lane (lanes=1) ->
    #    12 movements; 4 of them ('through', opposite arms) should be straight 2-point lines,
    #    the remaining 8 should be filleted turns with a LARGER radius than the curb corner.
    moves = build_lane_movements(arms, kerb_radius=8.0, segments=8, tail_length=12.0)
    assert len(moves) == 12, len(moves)
    kinds = [m["kind"] for m in moves]
    assert kinds.count("through") == 4, kinds.count("through")
    assert kinds.count("turn") == 8, kinds.count("turn")
    for m in moves:
        if m["kind"] == "through":
            assert len(m["points"]) == 2
            # straight: the two points plus the shared street-line offset point must be collinear
            p0, p1 = m["points"]
            assert abs(p0[0] - p1[0]) < eps or abs(p0[1] - p1[1]) < eps, m  # axis-aligned for this preset
        else:
            assert len(m["points"]) == 8 + 1 + 2  # tail + arc(segments+1) + tail... arc already has 9 pts
    print("OK: 4-way lane movements = 12 (4 through, straight; 8 turns, filleted)")

    # 7. Relaxed turn radius: bump kerb_radius and confirm the turn arcs widen (spot check one).
    moves_tight = build_lane_movements(arms, kerb_radius=4.0, segments=8, tail_length=12.0)
    moves_relaxed = build_lane_movements(arms, kerb_radius=10.0, segments=8, tail_length=12.0)
    turn_tight = next(m for m in moves_tight if m["kind"] == "turn")
    turn_relaxed = next(m for m in moves_relaxed
                        if m["kind"] == "turn" and m["from"] == turn_tight["from"] and m["to"] == turn_tight["to"])
    mid_tight = turn_tight["points"][len(turn_tight["points"]) // 2]
    mid_relaxed = turn_relaxed["points"][len(turn_relaxed["points"]) // 2]
    assert vlen(mid_relaxed) > vlen(mid_tight), (vlen(mid_relaxed), vlen(mid_tight))
    print("OK: raising kerb_radius widens the generated turn arcs")

    # 8. Per-arm lane counts: a 2-lane main street (arms A/B) crossing a 1-lane side street (C).
    arms_mixed = preset_3way_t(through_angle=0.0, side_angle=90.0, lanes=(2, 2, 1))
    a2 = next(a for a in arms_mixed if a.name == "A")
    c1 = next(a for a in arms_mixed if a.name == "C")
    assert a2.lanes == 2 and c1.lanes == 1
    moves_mixed = build_lane_movements(arms_mixed, kerb_radius=8.0, segments=8, tail_length=20.0)
    ab = [m for m in moves_mixed if m["from"] == "A" and m["to"] == "B"]
    ac = [m for m in moves_mixed if m["from"] == "A" and m["to"] == "C"]
    assert len(ab) == 2, len(ab)   # min(2,2) lanes -- both continue straight through
    assert len(ac) == 1, len(ac)   # min(2,1) -- only lane 0 can turn onto the 1-lane side street
    try:
        preset_3way_t(lanes=(1, 2))   # wrong length for a 3-arm preset
        assert False, "expected ValueError for a mismatched per-arm lanes length"
    except ValueError:
        pass
    print("OK: per-arm lane counts (mixed 2/2/1 T-junction, length-mismatch guarded)")

    # 9. preset_nway: an arbitrary 5-way, all default single-lane, all turns filleted (angles
    #    chosen so no pair is a through-pair).
    arms5 = preset_nway((0.0, 60.0, 130.0, 200.0, 280.0))
    assert len(arms5) == 5
    corners5 = build_curb_corners(arms5, kerb_radius=8.0, segments=8)
    assert len(corners5) == 5, len(corners5)   # no collinear pair among these angles
    print("OK: preset_nway builds an arbitrary 5-way")

    # 10. turn_side: a consistent, self-verified sign convention (not compared to any external
    #     real-world compass meaning -- only that it's deterministic and that straight is 'S').
    assert turn_side((1.0, 0.0), (1.0, 0.0)) == "S"
    left = turn_side((1.0, 0.0), (0.0, 1.0))
    right = turn_side((1.0, 0.0), (0.0, -1.0))
    assert {left, right} == {"L", "R"} and left != right
    for m in moves:
        assert m["turn"] in ("L", "S", "R")
        assert (m["turn"] == "S") == (m["kind"] == "through")
    print("OK: turn_side classification (%s/%s split, through always 'S')" % (left, right))

    # 11. Lane ids: unique across TWO junctions built with distinct junction_id (the intended
    #     usage once a district has more than one intersection).
    moves_j1 = build_lane_movements(arms, kerb_radius=8.0, junction_id="J1")
    moves_j2 = build_lane_movements(arms, kerb_radius=8.0, junction_id="J2")
    ids = [m["id"] for m in moves_j1] + [m["id"] for m in moves_j2]
    assert len(ids) == len(set(ids)), "duplicate lane id across junctions"
    assert all(i.startswith("J1_") for i in [m["id"] for m in moves_j1])
    print("OK: lane ids are globally unique given distinct junction_id")

    # 12. Port / lane round-trip: with a generously large tail_length (comfortably beyond any
    #     fillet's own tangent length for this radius), every movement's far endpoint must land
    #     EXACTLY on the corresponding port -- a turn and a through movement sharing an (arm,
    #     lane) reach the identical physical point before/after the junction splits them.
    big_tail = 20.0
    moves_big = build_lane_movements(arms, kerb_radius=8.0, tail_length=big_tail, junction_id="J")
    ports_big = build_ports(arms, tail_length=big_tail)
    port_by_key = {(p["arm"], p["lane"], p["direction"]): p["position"] for p in ports_big}
    for m in moves_big:
        in_port = port_by_key[(m["from"], m["lane"], "in")]
        out_port = port_by_key[(m["to"], m["lane"], "out")]
        assert vlen(vsub(m["points"][0], in_port)) < 1e-6, (m["id"], m["points"][0], in_port)
        assert vlen(vsub(m["points"][-1], out_port)) < 1e-6, (m["id"], m["points"][-1], out_port)
    print("OK: every movement's far endpoints match their (arm, lane) ports exactly")

    # 13. export_dict / export_json: shape check + a real file round-trip (JSON stdlib, no bpy).
    d = export_dict(arms, kerb_radius=9.0, junction_id="J4")
    assert d["junction_id"] == "J4"
    assert len(d["arms"]) == 4 and len(d["lanes"]) == 12 and len(d["ports"]) == 8
    assert all(len(pt) == 2 for lane in d["lanes"] for pt in lane["points"])  # still 2D pre-export_json
    import json as _json
    import tempfile as _tempfile
    import os as _os
    with _tempfile.TemporaryDirectory() as tmp:
        p = _os.path.join(tmp, "test.lanekit.json")
        written = export_json(p, arms, kerb_radius=9.0, junction_id="J4", z=1.5)
        with open(p) as f:
            reloaded = _json.load(f)
        assert reloaded == written
        assert all(pt[1] == 1.5 for lane in reloaded["lanes"] for pt in lane["points"]), \
            "z should land in Godot's Y slot (index 1), not raw index 2"
        assert all(port["position"][1] == 1.5 for port in reloaded["ports"])
    print("OK: export_dict/export_json shape + JSON file round-trip (Z lifted correctly)")

    # 14. lane_map: explicit override replaces the default i->i pairing for one arm-pair only,
    #     every other pair keeps the default; an out-of-range index in the override raises.
    arms2 = preset_4way(lanes=2)   # 2 lanes per direction on every arm
    default_ne = [m for m in build_lane_movements(arms2, kerb_radius=8.0)
                  if m["from"] == "N" and m["to"] == "E"]
    assert sorted((m["lane_in"], m["lane_out"]) for m in default_ne) == [(0, 0), (1, 1)]
    mapped = build_lane_movements(arms2, kerb_radius=8.0,
                                   lane_map={("N", "E"): [(0, 1), (1, 0)]})
    ne = sorted((m["lane_in"], m["lane_out"]) for m in mapped if m["from"] == "N" and m["to"] == "E")
    assert ne == [(0, 1), (1, 0)], ne
    other_pair_unchanged = sorted((m["lane_in"], m["lane_out"]) for m in mapped
                                   if m["from"] == "N" and m["to"] == "S")
    assert other_pair_unchanged == [(0, 0), (1, 1)], other_pair_unchanged
    swapped_id = next(m["id"] for m in mapped if m["from"] == "N" and m["to"] == "E" and m["lane_in"] == 0)
    assert swapped_id.endswith("_L0to1"), swapped_id
    try:
        build_lane_movements(arms2, kerb_radius=8.0, lane_map={("N", "E"): [(0, 5)]})
        assert False, "expected ValueError for an out-of-range lane_map index"
    except ValueError:
        pass
    print("OK: lane_map explicit override (per-arm-pair, validated, id reflects a swap)")

    # 15. build_straight_segment: 2 lanes each direction between two axis-aligned points -- curbs
    #     are the outermost lines, lane points sit exactly on the p0->p1 axis (only the
    #     perpendicular offset differs), and the two directions never overlap in offset.
    p0, p1 = (0.0, 0.0), (20.0, 0.0)   # due +X, so "perpendicular" is pure Y
    seg = build_straight_segment(p0, p1, lane_width=5.0, lanes=2, segment_id="S1")
    assert len(seg["lanes"]) == 4  # 2 lanes x 2 directions
    ab = sorted((m["lane_in"], m["points"][0][1]) for m in seg["lanes"] if m["from"] == "A")
    ba = sorted((m["lane_in"], m["points"][0][1]) for m in seg["lanes"] if m["from"] == "B")
    assert ab == [(0, 2.5), (1, 7.5)], ab      # A->B lanes offset to +Y (out side), widening outward
    assert ba == [(0, -2.5), (1, -7.5)], ba    # B->A lanes offset to -Y, never crossing A->B's side
    for m in seg["lanes"]:
        assert abs(m["points"][0][0] - (p0[0] if m["from"] == "A" else p1[0])) < 1e-9
        assert abs(m["points"][1][0] - (p1[0] if m["from"] == "A" else p0[0])) < 1e-9
    left, right = seg["curbs"]
    assert left[0][1] == 10.0 and right[0][1] == -10.0   # outermost -- past every lane's offset
    print("OK: build_straight_segment (curbs outermost, lanes offset outward per direction)")

    # 16. export_segment_json: same axis-conversion + shape as export_json, loadable by the exact
    #     same WorldBaker sidecar reader (only needs top-level 'lanes' -- verified structurally,
    #     not by invoking Java from here).
    with _tempfile.TemporaryDirectory() as tmp:
        p = _os.path.join(tmp, "seg.lanekit.json")
        sd = export_segment_json(p, p0, p1, lane_width=5.0, lanes=1, segment_id="S2", z=0.75)
        with open(p) as f:
            reloaded = _json.load(f)
        assert reloaded == sd
        assert len(reloaded["lanes"]) == 2
        assert all(pt[1] == 0.75 for lane in reloaded["lanes"] for pt in lane["points"])
        assert all(set(lane.keys()) >= {"id", "points", "loop", "turn", "kind"} for lane in reloaded["lanes"])
    print("OK: export_segment_json shape matches what WorldBaker's sidecar loader needs")

    # 17. build_straight_segment with bend != 0: still exactly straight when bend=0 (no
    #     regression, checked above); a nonzero bend must actually curve (midpoint displaced
    #     from the straight chord), start/end points stay anchored at p0/p1 exactly, every
    #     curved lane/curb line's arc length exceeds the straight chord length (a real bulge, not
    #     a no-op), and a bigger bend curves more.
    curved = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="C1", bend=5.0, segments=8)
    ab = next(m for m in curved["lanes"] if m["from"] == "A")
    assert len(ab["points"]) == 9   # segments+1
    # lane 0 is exactly lane_width/2 = 2.5m off the spine at each end (direction varies along a
    # curve, so check the offset MAGNITUDE, not a fixed +Y direction like the straight case)
    assert abs(vlen(vsub(ab["points"][0], p0)) - 2.5) < 1e-6
    assert abs(vlen(vsub(ab["points"][-1], p1)) - 2.5) < 1e-6
    mid_curved = ab["points"][4]
    straight_mid_y = 2.5   # the dead-straight case's constant Y offset
    assert abs(mid_curved[1] - straight_mid_y) > 1.0, mid_curved   # genuinely bulged, not flat
    chain_len = sum(vlen(vsub(ab["points"][i], ab["points"][i - 1])) for i in range(1, len(ab["points"])))
    straight_len = vlen(vsub(ab["points"][-1], ab["points"][0]))
    assert chain_len > straight_len + 0.5, (chain_len, straight_len)   # a real arc, not collinear
    curved_more = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="C2", bend=10.0, segments=8)
    ab_more = next(m for m in curved_more["lanes"] if m["from"] == "A")
    assert abs(ab_more["points"][4][1] - straight_mid_y) > abs(mid_curved[1] - straight_mid_y)
    print("OK: build_straight_segment bend (anchored endpoints, genuine curve, scales with bend)")

    # 18. build_straight_segment with z0/z1 (constant grade) and bend_z (crest/dip): every point
    #     is now a 3-tuple; flat (all defaults) still emits z=0.0 everywhere (no regression); a
    #     slope linearly interpolates z from z0 at p0 to z1 at p1; bend_z adds a midpoint bump on
    #     top of that, zero at both ends.
    flat = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="F1")
    flat_ab = next(m for m in flat["lanes"] if m["from"] == "A")
    assert all(pt[2] == 0.0 for pt in flat_ab["points"]), flat_ab["points"]
    sloped = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="SL1", z0=0.0, z1=10.0,
                                     bend=0.001, segments=8)   # tiny bend forces spine subdivision
    sloped_ab = next(m for m in sloped["lanes"] if m["from"] == "A")
    assert abs(sloped_ab["points"][0][2] - 0.0) < eps
    assert abs(sloped_ab["points"][-1][2] - 10.0) < eps
    assert abs(sloped_ab["points"][4][2] - 5.0) < eps   # midpoint of a linear 0->10 grade
    hill = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="H1", z0=0.0, z1=0.0, bend_z=4.0)
    hill_ab = next(m for m in hill["lanes"] if m["from"] == "A")
    assert abs(hill_ab["points"][0][2]) < eps and abs(hill_ab["points"][-1][2]) < eps  # ends flat
    assert abs(hill_ab["points"][4][2] - 4.0) < eps   # midpoint hits the full bend_z bump
    left_c, right_c = sloped["curbs"]
    assert abs(left_c[0][2] - 0.0) < eps and abs(left_c[-1][2] - 10.0) < eps   # curbs slope too
    print("OK: build_straight_segment z0/z1 grade + bend_z crest/dip (flat case unaffected)")

    # 19. One-way arms (Arm.oneway): a 4-way with the S arm set 'IN' (only ever receives traffic,
    #     e.g. a one-way street feeding IN) and the W arm set 'OUT' (only ever sends, e.g. a
    #     one-way exit) -- verify no movement originates FROM W (0 incoming lanes) or terminates
    #     AT S (0 outgoing lanes), the reverse directions (TO W, FROM S) are unaffected, ports only
    #     exist for the direction each arm actually carries, and half_width/curb geometry (still
    #     driven by the plain `lanes` count) is untouched -- a one-way arm is still full width.
    arms_ow = preset_4way(lanes=1)
    s_arm = next(a for a in arms_ow if a.name == "S")
    w_arm = next(a for a in arms_ow if a.name == "W")
    s_arm.oneway = 'IN'
    w_arm.oneway = 'OUT'
    assert s_arm.lanes_in_count() == 1 and s_arm.lanes_out_count() == 0
    assert w_arm.lanes_in_count() == 0 and w_arm.lanes_out_count() == 1
    assert s_arm.half_width() == 5.0 and w_arm.half_width() == 5.0   # curb width unaffected
    moves_ow = build_lane_movements(arms_ow, kerb_radius=8.0, tail_length=12.0)
    assert not any(m["from"] == "W" for m in moves_ow), "W is OUT-only -- must never be a 'from'"
    assert not any(m["to"] == "S" for m in moves_ow), "S is IN-only -- must never be a 'to'"
    assert any(m["to"] == "W" for m in moves_ow)      # W can still be arrived AT
    assert any(m["from"] == "S" for m in moves_ow)    # S can still depart FROM
    corners_ow = build_curb_corners(arms_ow, kerb_radius=8.0)
    assert len(corners_ow) == 4, len(corners_ow)   # curb geometry itself is unaffected
    ports_ow = build_ports(arms_ow, tail_length=12.0)
    w_ports = [p for p in ports_ow if p["arm"] == "W"]
    s_ports = [p for p in ports_ow if p["arm"] == "S"]
    assert {p["direction"] for p in w_ports} == {"out"}, w_ports
    assert {p["direction"] for p in s_ports} == {"in"}, s_ports
    print("OK: one-way arms (oneway='IN'/'OUT') correctly gate movements/ports, curb unaffected")

    # 20. Asymmetric / one-way segment lanes (build_segment_from_spine / build_straight_segment's
    #     `lanes_backward`): a fully one-way single-lane road (lanes=1, lanes_backward=0) produces
    #     exactly ONE lane (A->B only), curb width matches the ACTIVE side (1 lane, not 2), and
    #     asking for zero lanes in BOTH directions is a hard error, not silently-empty geometry.
    #     Also verifies `segment_spine_3d` + `build_segment_from_spine` (called directly, not via
    #     `build_straight_segment`) reproduce the exact same result -- one code path either way.
    oneway_seg = build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="OW1",
                                         lanes_backward=0)
    assert len(oneway_seg["lanes"]) == 1, len(oneway_seg["lanes"])
    assert oneway_seg["lanes"][0]["from"] == "A" and oneway_seg["lanes"][0]["to"] == "B"
    ow_left, ow_right = oneway_seg["curbs"]
    assert ow_left[0][1] == 5.0 and ow_right[0][1] == -5.0   # 1 lane wide (5m), not the old 2-lane 10m
    try:
        build_straight_segment(p0, p1, lane_width=5.0, lanes=0, segment_id="OW2", lanes_backward=0)
        assert False, "expected ValueError for a segment with zero lanes in both directions"
    except ValueError:
        pass
    spine_direct = segment_spine_3d(p0, p1)
    via_spine = build_segment_from_spine(spine_direct, lane_width=5.0, lanes=1, lanes_backward=0,
                                          segment_id="OW1")
    assert via_spine == oneway_seg, "build_straight_segment and the spine path must agree exactly"
    print("OK: asymmetric/one-way segment lanes (lanes_backward=0 -> exactly 1 lane, curb "
          "matches active width, zero-both-directions rejected, spine path matches exactly)")

    # 21. export_segment_from_spine_json: absolute-Z spine (as if sampled from a real Curve
    #     object's world-space points, unlike export_segment_json's relative-Z + base-z model) --
    #     axis conversion still lands Z in Godot's Y slot, X/Y swizzle unchanged.
    spine_abs = [(0.0, 0.0, 3.0), (10.0, 0.0, 3.0), (20.0, 5.0, 7.0)]
    with _tempfile.TemporaryDirectory() as tmp:
        p = _os.path.join(tmp, "curveseg.lanekit.json")
        sd = export_segment_from_spine_json(p, spine_abs, lane_width=4.0, lanes=1, segment_id="CV1")
        with open(p) as f:
            reloaded = _json.load(f)
        assert reloaded == sd
        assert len(reloaded["lanes"]) == 2   # symmetric default (lanes_backward=None -> =lanes)
        ab_pts = next(m for m in reloaded["lanes"] if m["from_arm"] == "A")["points"]
        assert abs(ab_pts[0][1] - 3.0) < 1e-6 and abs(ab_pts[-1][1] - 7.0) < 1e-6, ab_pts
    print("OK: export_segment_from_spine_json (absolute-Z spine, correct Godot axis lift)")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
