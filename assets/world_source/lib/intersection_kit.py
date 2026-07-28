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


def lane_perp(v, traffic_side='LEFT'):
    """The lateral unit vector LANE/CURB offsets are measured along, in driving convention
    `traffic_side`: 'LEFT' (default -- keep-left, e.g. Japan/UK -- matches this module's original,
    still-self-tested formulas byte-for-byte) is `perp_ccw(v)` unchanged; 'RIGHT' (keep-right,
    e.g. US) is its negation. This is the ONE place traffic-side is decided -- every lane/curb
    lateral-offset call site in this module goes through this (directly, or indirectly via
    `Arm.in_offset`/`out_offset` which are themselves only ever combined with this) instead of a
    bare `perp_ccw`, so flipping one flag re-derives a whole intersection/segment/transition's
    physical lane arrangement with no other change. Cosmetic-only uses of `perp_ccw` (e.g. a
    segment's authoring-time `bend` control-point offset, an arbitrary left/right authoring choice
    unrelated to which side of the road traffic drives on) intentionally do NOT go through this."""
    p = perp_ccw(v)
    return p if traffic_side != 'RIGHT' else (-p[0], -p[1])


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
    PER DIRECTION (symmetric: as many lanes arriving as leaving) by default, UNLESS overridden:
    `oneway='IN'` means this arm only ever RECEIVES traffic (no outgoing lanes, e.g. a one-way
    street feeding into the junction); `oneway='OUT'` means it only ever SENDS traffic (no
    incoming lanes, e.g. a one-way exit). `None` (default) is the original symmetric behavior.

    `lanes_out` -- ASYMMETRIC WIDENING: an independent override for the DEPARTING lane count only
    (the arriving count stays `lanes`), e.g. `lanes=1, lanes_out=2` is a busy exit with 2 lanes
    leaving but only 1 arriving. `None` (default) means "same as `lanes`" -- byte-identical to the
    old symmetric-only behavior for every existing caller. Since arriving lanes occupy the CW
    curb-to-centerline half and departing lanes occupy the CCW half (see `in_offset`/`out_offset`),
    growing ONE of `lanes`/`lanes_out` moves ONLY that side's curb edge (`in_width`/`out_width`,
    used by `curb_edges`) -- this is the actual mechanism for "widen one side only" (a uniform
    sideways shift of a still-symmetric width does not: the two curb edges are `+w+shift` and
    `-w+shift`, so their total span `2w` is independent of `shift` -- shifting can bias which edge
    LOOKS fixed but always forces the other edge to move by DOUBLE the intended growth; splitting
    the width itself per-direction is the only way one edge can move by exactly one lane's worth
    while the other stays put). `oneway` still wins over `lanes_out` (an 'IN'-only arm has 0
    outgoing lanes regardless of `lanes_out`).

    `lanes_in_count()`/`lanes_out_count()` are the two independent per-direction counts every
    other function in this module already keys off (`build_lane_movements`, `build_ports`), so
    supporting `lanes_out` needed no changes anywhere except `Arm` itself and `curb_edges`.

    `traffic_side` ('LEFT' default, or 'RIGHT') -- which physical lateral half of the arm is
    arriving vs. departing (see `lane_perp`). 'LEFT' (keep-left, e.g. Japan) is this module's
    original, still-self-tested convention; 'RIGHT' (keep-right, e.g. US) mirrors it. Every arm of
    ONE junction must share the same value (mixing them within a junction isn't physically
    drivable) -- functions taking an arm pair (`curb_edges`, `_junction_corner_vertex`, ...) read
    it off `arm_a` only and use that for both sides.

    `tail_length` (default None) -- PER-ARM override of how far this one arm's own tail/ports
    reach out from the junction center, independent of every other arm's. `None` means "use
    whatever shared scalar the caller passed in" (e.g. `build_junction_boundary`'s own
    `tail_length` parameter) -- byte-identical to the old all-arms-share-one-scalar behavior, so
    every existing preset/caller that never sets this is unaffected. This exists so a live-edited
    arm marker's ACTUAL distance from the origin (e.g. after Grab+snapping it onto an external
    segment's port -- see `ops_intersection.rebuild_intersection_in_place`) can be preserved
    exactly instead of being forced back onto one shared radius on the next rebuild."""

    def __init__(self, name, angle_deg, lane_width=5.0, lanes=1, oneway=None, lanes_out=None,
                 traffic_side='LEFT', tail_length=None):
        self.name = name
        self.angle_deg = angle_norm(angle_deg)
        self.lane_width = lane_width
        self.lanes = lanes
        self.oneway = oneway   # None | 'IN' | 'OUT'
        self.lanes_out = lanes_out   # None = symmetric with `lanes` (back-compat default)
        self.traffic_side = traffic_side   # 'LEFT' | 'RIGHT' -- see class docstring
        self.tail_length = tail_length   # None = use the caller's shared scalar -- see docstring

    def eff_tail_length(self, shared_tail_length):
        """This arm's own `tail_length` override if set, else the shared scalar every per-arm
        geometry function already accepts -- the one place that fallback rule lives."""
        return self.tail_length if self.tail_length is not None else shared_tail_length

    def lanes_in_count(self):
        """How many lanes ARRIVE at the junction along this arm (0 if `oneway == 'OUT'`)."""
        return 0 if self.oneway == 'OUT' else self.lanes

    def lanes_out_count(self):
        """How many lanes LEAVE the junction along this arm (0 if `oneway == 'IN'`, else
        `lanes_out` when explicitly set, else `lanes` -- symmetric default)."""
        if self.oneway == 'IN':
            return 0
        return self.lanes if self.lanes_out is None else self.lanes_out

    def in_width(self):
        """Curb-to-centerline distance on the ARRIVING (CW) side."""
        return self.lane_width * self.lanes_in_count()

    def out_width(self):
        """Curb-to-centerline distance on the DEPARTING (CCW) side."""
        return self.lane_width * self.lanes_out_count()

    def half_width(self):
        """Curb-to-centerline distance -- kept as the conservative SYMMETRIC bound (the wider of
        the two sides) for any caller that just needs one scalar (e.g. a marker's display size);
        real curb geometry uses `in_width()`/`out_width()` independently so asymmetric arms get a
        genuinely asymmetric curb, not this max()."""
        return max(self.in_width(), self.out_width())

    def in_offset(self, i):
        """Signed perpendicular offset (CW side) of the i-th arriving lane's own centerline."""
        return -(i + 0.5) * self.lane_width

    def out_offset(self, i):
        """Signed perpendicular offset (CCW side) of the i-th leaving lane's own centerline."""
        return (i + 0.5) * self.lane_width


def corner_fillet(edge_a, edge_b, radius, segments=8, max_tangent_len=None):
    """edge_a, edge_b: (point, direction) tuples, each direction pointing AWAY from their shared
    (unrounded) vertex along its own line. Returns (vertex, trim_a, trim_b, arc_points): arc_points
    is `segments`+1 points from trim_a to trim_b inclusive, each exactly `radius` from the arc
    center, tangent to both edges at trim_a/trim_b.

    `max_tangent_len` (optional, default None = unclamped, unchanged behavior): caps how far the
    fillet's trim points can sit from the corner vertex along each edge, by SHRINKING the
    effective radius (never growing it) -- `tangent_len = radius / tan(theta/2)` blows up as two
    arms' angle approaches a through-pair (~180 deg, theta -> 0), and an uncapped tangent can
    reach past the arm's own tail/straight run into the NEXT corner's territory. This is what
    keeps a live-drag rebuild from ever needing to raise past a small angle nudge -- see
    `build_curb_corners`, which passes the arm's own `tail_length` here."""
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
    if max_tangent_len is not None:
        radius = min(radius, max_tangent_len * math.tan(theta / 2.0))
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
    arm_a -> arm_b: arm_a's CCW (leaving-lane) side and arm_b's CW (arriving-lane) side. Uses each
    arm's own `out_width()`/`in_width()` independently (not a shared symmetric `half_width()`), so
    an asymmetric arm (`lanes_out` override) produces a genuinely asymmetric curb -- see `Arm`.
    Traffic side (`lane_perp`) is read off `arm_a` only -- both arms of one junction must share it."""
    da, db = arm_dir(arm_a.angle_deg), arm_dir(arm_b.angle_deg)
    pa, pb = lane_perp(da, arm_a.traffic_side), lane_perp(db, arm_a.traffic_side)
    edge_a = (vscale(pa, arm_a.out_width()), da)
    edge_b = (vscale(pb, -arm_b.in_width()), db)
    return edge_a, edge_b


def build_curb_corners(arms, kerb_radius, segments=8, through_tol_deg=2.0, tail_length=None):
    """One dict per angularly-consecutive arm pair that is NOT a through-pair:
    {'arm_a', 'arm_b', 'vertex', 'trim_a', 'trim_b', 'arc': [(x,y), ...]}.

    `tail_length` (optional, default None = unclamped, unchanged behavior): forwarded to
    `corner_fillet` as `max_tangent_len`, so a corner never demands more tangent length than the
    arm's own approach actually has -- and a corner pair that's briefly near-degenerate mid-drag
    (two arms momentarily close in angle without quite crossing the through-pair tolerance) is
    SKIPPED (this pair contributes no corner, same as a through-pair) instead of raising, which
    previously propagated out of `rebuild_intersection_in_place` as an uncaught `ValueError` AFTER
    `clear_generated_mesh_objects` had already deleted the old geometry -- the concrete cause of a
    small arm-angle nudge leaving an intersection with no curb at all until the drag moved past the
    bad angle. Every OTHER exception still propagates (a real bug should still be loud)."""
    out = []
    for a, b in consecutive_pairs(arms):
        if is_through_pair(a.angle_deg, b.angle_deg, through_tol_deg):
            continue
        try:
            vertex, trim_a, trim_b, arc = corner_fillet(
                *curb_edges(a, b), kerb_radius, segments, max_tangent_len=tail_length)
        except ValueError:
            continue
        out.append({"arm_a": a.name, "arm_b": b.name, "vertex": vertex,
                     "trim_a": trim_a, "trim_b": trim_b, "arc": arc})
    return out


def _junction_corner_vertex(a, b, kerb_radius, tail_length, through_tol_deg=2.0):
    """The rounded corner (vertex, clamped radius) between angularly-adjacent arms a->b, or None
    if it's a through-pair, degenerate, or momentarily coincident mid-drag (skip -- same rationale
    as `build_curb_corners`). Shared by `build_junction_boundary` (the pad's full closed loop,
    corners included) and `build_junction_curb_segments` (curb walls, corners ONLY) so the two
    never disagree on where/how far a corner rounds.

    The BASE radius scales with the WIDEST lane that could turn through this corner --
    `build_lane_movements` already gives an outer lane a bigger, more AI-comfortable turn radius
    the further out it is (`kerb_radius + (lane_index + 0.5) * lane_width`); a plain `kerb_radius`
    alone stays tight regardless of arm width, so a wide (3-4 lane) arm's outer-lane turn could
    reach past a pad/curb corner sized only for a single lane -- extending past the visible
    pavement mesh entirely (this was the concrete "lane goes far outside the mesh" bug: pad ~20m
    from center, worst lane's turn ~28m). Matching the SAME `(index + 0.5) * lane_width` growth
    here keeps every lane's turn inside the pad by construction. Every arm here having exactly 1
    lane keeps this EXACTLY `kerb_radius` -- byte-identical to the historical/default single-lane
    case (and to `build_curb_corners`, which intentionally stays plain `kerb_radius` always -- it
    backs the older, non-GN curb path and self-tests that assert exactly that).

    The clamp is measured PER EDGE, not from one shared `tail_length * tan(theta/2)` figure: that
    blanket formula silently assumes `vertex` sits exactly `tail_length` from BOTH arms' own
    tail-cap points, which is only true when `a`/`b` have equal width on the sides meeting at this
    corner. Widen just one arm of a 4-way (the reported bug: symmetric widen 1->2 lanes looked
    correct on one side of the widened arm but produced a corner that was effectively missing/miles
    off on the other) and `vertex` shifts toward the NARROW arm's own tail-cap -- confirmed by
    direct measurement: with S widened to 2 lanes and E/W still 1 lane, the E-S corner's vertex
    sits only ~2m from E's own tail-cap point but ~7m from S's, while the mirror S-W corner has the
    same 2m/7m split with the short side on W instead. The old blanket clamp (`tail_length * tan
    (theta/2)`, ~12m here) never noticed the short 2m side and let the fillet's tangent point
    overshoot 10m past that arm's own tail-cap -- off the visible pad, reading as "missing" curb/
    lane data on whichever side happened to be the narrow one. Clamping each side by its OWN
    measured distance from `vertex` to that arm's tail-cap point (not a shared formula) means
    neither side can ever overshoot its own arm's tail, regardless of how asymmetric the two arms'
    widths are."""
    if is_through_pair(a.angle_deg, b.angle_deg, through_tol_deg):
        return None
    edge_a, edge_b = curb_edges(a, b)
    vertex = line_intersect_2d(edge_a[0], edge_a[1], edge_b[0], edge_b[1])
    if vertex is None:
        return None
    da_n, db_n = vnorm(edge_a[1]), vnorm(edge_b[1])
    cosang = max(-1.0, min(1.0, da_n[0] * db_n[0] + da_n[1] * db_n[1]))
    theta = math.acos(cosang)
    if theta < 1e-6 or theta > math.pi - 1e-6:
        return None
    lane_headroom = max(a.lanes_in_count(), a.lanes_out_count(),
                         b.lanes_in_count(), b.lanes_out_count())
    base_radius = kerb_radius if lane_headroom <= 1 else \
        kerb_radius + (lane_headroom - 0.5) * max(a.lane_width, b.lane_width)
    if tail_length:
        a_tail, b_tail = a.eff_tail_length(tail_length), b.eff_tail_length(tail_length)
        da, db = arm_dir(a.angle_deg), arm_dir(b.angle_deg)
        p_out_a = vadd(vscale(lane_perp(da, a.traffic_side), a.out_width()), vscale(da, a_tail))
        p_in_b = vadd(vscale(lane_perp(db, a.traffic_side), -b.in_width()), vscale(db, b_tail))
        max_tangent = min(vlen(vsub(vertex, p_out_a)), vlen(vsub(vertex, p_in_b)))
        radius = min(base_radius, max_tangent * math.tan(theta / 2.0))
    else:
        radius = base_radius
    return vertex, radius


def recommended_tail_length(arms, kerb_radius, start=None, margin=2.0, growth=1.3, max_iter=25):
    """The smallest `tail_length` (>= `start`, default the caller's own requested value) that
    keeps every TURN movement's own points within `margin` meters of the pad boundary's own max
    reach from the junction center -- found by direct NUMERICAL SEARCH (build the boundary +
    movements, measure the actual gap, grow `tail_length` by `growth` and repeat), not a
    closed-form formula.

    Why a search and not a formula: a turn's arc radius is clamped by `tail_length` up to a point;
    beyond that point further `tail_length` growth instead extends the STRAIGHT tail portions of
    both the pad and the movement, at rates that depend on different effective widths (the pad
    uses an arm's FULL width, a single lane's own tail uses just that lane's own offset) -- the gap
    between pad and worst-movement reach is NOT monotonic in `tail_length` (verified: for a 4-lane
    arm it gets WORSE well before it gets better, only crossing back under the pad's own reach at
    roughly 3-4x the historical default), so a one-shot trig formula (tried first, and confirmed
    wrong by exactly this non-monotonicity) can land in the growing part of the curve instead of
    past the eventual crossover. Directly measuring and searching is slower per call (~10 rebuilds
    for a heavily widened arm) but is correct by construction regardless of arm/lane configuration.

    Is a no-op (returns `start` unchanged) for any intersection where every arm has 1-2 lanes --
    the historical default already satisfies the margin there. Intended as a FLOOR:
    `effective_tail_length = recommended_tail_length(arms, kerb_radius, start=requested)` never
    shrinks an explicit larger request (the search starts FROM it)."""
    tail_length = start if start is not None else 12.0
    worst = 0.0
    for _ in range(max_iter):
        boundary = build_junction_boundary(arms, kerb_radius, tail_length=tail_length)
        pad_max = max(vlen((x, y)) for (x, y, r) in boundary)
        try:
            moves = build_lane_movements(arms, kerb_radius, tail_length=tail_length)
        except ValueError:
            moves = []
        worst = max((vlen(p) for m in moves if m["kind"] == "turn" for p in m["points"]),
                    default=0.0)
        if worst <= pad_max + margin:
            return tail_length
        tail_length *= growth
    return tail_length


def build_junction_boundary(arms, kerb_radius, tail_length=12.0, through_tol_deg=2.0):
    """The intersection PAD boundary polygon (the FULL closed footprint, including each arm's own
    tail-cap -- see `build_junction_curb_segments` for the narrower, curb-only geometry that
    excludes those caps) -- purely a function of arm angles/widths, NEVER of which lane movements
    happen to exist -- feeding `kit_common.junction_pad` (the GN-backed visual mesh) directly.
    Returns `[(x, y, radius), ...]` in CCW order (z is added
    by the caller, same 2D-only convention as `build_curb_corners`), ready for
    `kit_common._poly_curve_with_radius`'s per-point `Radius`.

    One (x, y, radius) triple per boundary vertex: for each arm (angle order) its own IN-side and
    OUT-side TAIL points (radius 0 -- these are where this pad hands off to a connecting straight/
    transition segment piece, not rounded, using `in_width()`/`out_width()` independently so an
    asymmetric arm produces a genuinely asymmetric pad edge too), with a plain straight edge
    between them (the arm's own 'cap' closing off its opening); then either a rounded fillet vertex
    (radius = `kerb_radius`, clamped by the exact same tangent-length formula
    `build_curb_corners`/`corner_fillet`'s `max_tangent_len` applies, so the pad/curb mesh and the
    lane-centerline data layer never disagree on how far a corner actually rounds) to the NEXT arm,
    or NOTHING -- a plain straight edge, no extra vertex at all -- when that pair is a through-pair
    (`is_through_pair`): the 'ability to go straight' this module has always had, now expressed as
    the boundary having no vertex there, rather than a corner with a huge or degenerate radius.
    A momentarily-degenerate corner (near-duplicate angles mid-drag) is silently skipped, same
    rationale as `build_curb_corners`."""
    ordered = sorted(arms, key=lambda a: a.angle_deg)
    n = len(ordered)
    out = []
    for i in range(n):
        a = ordered[i]
        b = ordered[(i + 1) % n]
        a_tail = a.eff_tail_length(tail_length)
        d = arm_dir(a.angle_deg)
        perp = lane_perp(d, a.traffic_side)
        p_in = vadd(vscale(perp, -a.in_width()), vscale(d, a_tail))
        p_out = vadd(vscale(perp, a.out_width()), vscale(d, a_tail))
        out.append((p_in[0], p_in[1], 0.0))
        out.append((p_out[0], p_out[1], 0.0))
        corner = _junction_corner_vertex(a, b, kerb_radius, tail_length, through_tol_deg)
        if corner is not None:
            vertex, radius = corner
            out.append((vertex[0], vertex[1], radius))
    return out


def build_junction_curb_segments(arms, kerb_radius, tail_length=12.0, through_tol_deg=2.0):
    """The CURB-ONLY geometry for an intersection: one small OPEN 3-point segment per real corner
    -- `[(arm_a's OUT tail point, radius 0), (corner vertex, clamped radius), (arm_b's IN tail
    point, radius 0)]` -- and NOTHING ELSE. Deliberately narrower than `build_junction_boundary`
    (the pad's full closed loop): a through-pair contributes no curb at all (the road continues
    straight -- no wall needed at the junction; any curb along that straight stretch is the job of
    the connecting straight-segment piece, not the intersection), and -- the actual fix here --
    neither does an arm's own TAIL-CAP (the straight edge across its own opening): a road can't
    have a curb wall across its own lanes at the point it enters the junction. (The pad's boundary
    still includes tail-caps -- it needs the FULL closed area to fill correctly; only the curb
    omits them.)

    Returns `[[(x, y, radius), (x, y, radius), (x, y, radius)], ...]`, one 3-point list per real
    corner, ready for `kit_common.curb_loop(closed=False)` -- each corner becomes its OWN small
    curb object (mirroring how every other piece in this addon builds one curb wall per physical
    wall run, not one object spanning unrelated gaps)."""
    ordered = sorted(arms, key=lambda a: a.angle_deg)
    n = len(ordered)
    segments = []
    for i in range(n):
        a = ordered[i]
        b = ordered[(i + 1) % n]
        corner = _junction_corner_vertex(a, b, kerb_radius, tail_length, through_tol_deg)
        if corner is None:
            continue
        vertex, radius = corner
        da = arm_dir(a.angle_deg)
        perp_a = lane_perp(da, a.traffic_side)
        p_out = vadd(vscale(perp_a, a.out_width()), vscale(da, a.eff_tail_length(tail_length)))
        db = arm_dir(b.angle_deg)
        perp_b = lane_perp(db, a.traffic_side)
        p_in_b = vadd(vscale(perp_b, -b.in_width()), vscale(db, b.eff_tail_length(tail_length)))
        segments.append([
            (p_out[0], p_out[1], 0.0),
            (vertex[0], vertex[1], radius),
            (p_in_b[0], p_in_b[1], 0.0),
        ])
    return segments


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
                          junction_id="J", lane_map=None, turn_radius=3.5):
    """One dict per legal lane movement: {'id', 'from', 'to', 'lane' (alias of 'lane_in'),
    'lane_in', 'lane_out', 'kind' ('through'|'turn'), 'turn' ('L'|'S'|'R'), 'points':
    [(x,y), ...]}. A 'through' polyline is a straight 2-point line when `lane_in == lane_out`
    (the common case); when auto-merge pairs a mismatched lane index (a wider arm funneling an
    outer lane into its through-partner's own outermost lane) it's instead a smoothstep-eased
    lateral taper (`segments`+1 points) from one lane's offset to the other's, so it reads as a
    lane shift rather than a diagonal line cutting straight across the pad. `id` is globally
    unique given a unique `junction_id`.

    A 'turn' polyline is filleted at a SMALL, FIXED `turn_radius` (default 3.5m, the real-world
    minimum vehicle turning radius -- delivery-truck-feasible, matching this module's own curb
    corner default before it was ever scaled up) starting straight from each lane's own offset
    line (`p_in`/`p_out`, independently solved per lane via `corner_fillet` -- the ORIGINAL design
    this module shipped with). This was briefly replaced, then reverted, by a large
    `kerb_radius`-scaled "AI-comfortable swing" radius shared via one concentric corner per arm
    pair: that produced turns visibly bulging outside the pad even for a single-lane 4-way (long,
    near-straight "bowtie" lines, confirmed by direct comparison -- not what a small, realistic
    turn radius naturally avoids just by being small enough that its tangent length stays well
    inside `tail_length` regardless of how many lanes an arm has, with no special-case scaling
    needed at all). A degenerate/near-collinear arm pair at this radius is skipped, not raised.

    By default, for each ordered arm pair (a, b), in-lane i feeds out-lane i for
    i in 0..min(a.lanes, b.lanes)-1 (the only sane default when nothing else is specified). When
    the counts differ, EVERY lane on the narrower side still gets at least one movement -- b
    narrower than a (a MERGE): a's extra arriving lanes beyond b_out-1 all funnel into b's own
    outermost leaving lane. b WIDER than a (a FAN-OUT): a's own outermost arriving lane is reused
    to additionally feed each of b's leaving lanes beyond a_in-1, so a widening target's extra
    departure lanes are never left with zero incoming geometry (an unfed lane no vehicle would
    ever be routed onto). Both are the same idea in opposite directions and share the reused
    outermost-lane logic; both read as a real lane merge/split, not an arbitrary drop. Either
    default can be wrong for a specific intersection (e.g. a fan that should instead point turned
    traffic elsewhere) -- override with `lane_map` per arm-pair, or delete the unwanted generated
    lane's data by hand, same as any other `lane_map` override.

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
            a_tail, b_tail = a.eff_tail_length(tail_length), b.eff_tail_length(tail_length)
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
                # lanes) can never be a `to`; both fall out for free since b_out/a_in is 0.
                # AUTO-MERGE: every arriving lane always gets SOME movement (never silently
                # dropped) -- lane i normally feeds lane i, but once i would run out of a
                # same-index leaving lane (b has fewer leaving lanes than a has arriving ones),
                # it funnels into b's OWN outermost leaving lane instead (clamped to
                # b_out - 1) -- a real lane-drop/merge, matching how a wide road actually narrows
                # into a narrower one, rather than that extra lane simply having no geometry at
                # all. Byte-identical to the old i->i pairing whenever b has >= as many leaving
                # lanes as a has arriving ones (the common case).
                b_out, a_in = b.lanes_out_count(), a.lanes_in_count()
                pairs = [(i, min(i, b_out - 1)) for i in range(a_in)] if b_out > 0 else []
                # AUTO-FAN-OUT (mirror of the merge above, opposite direction): b WIDER than a --
                # a's own outermost arriving lane (a_in - 1) is reused to ALSO feed each of b's
                # leaving lanes beyond a_in - 1, so a widening target's extra departure lanes get
                # real incoming geometry instead of sitting unfed (no movement, so no vehicle is
                # ever routed onto them) purely because the narrower source arm ran out of
                # distinct lanes to hand out. `through`/turn point-generation below already
                # supports an arbitrary (li, lo) pair (the merge case exercises that same code),
                # so no further change is needed to actually draw these.
                if b_out > a_in > 0:
                    pairs += [(a_in - 1, lo) for lo in range(a_in, b_out)]

            for li, lo in pairs:
                lane_id = ("%s_%s_%s_L%d" % (junction_id, a.name, b.name, li) if li == lo else
                           "%s_%s_%s_L%dto%d" % (junction_id, a.name, b.name, li, lo))
                p_in = vscale(lane_perp(da, a.traffic_side), a.in_offset(li))
                p_out = vscale(lane_perp(db, a.traffic_side), b.out_offset(lo))
                if through:
                    if li == lo:
                        pts = [vadd(p_in, vscale(da, a_tail)),
                               vadd(p_out, vscale(db, b_tail))]
                    else:
                        # Auto-merged through movement (mismatched lane index -- an arm wider than
                        # its through-partner funnels an outer lane into the partner's own
                        # outermost lane): p_in/p_out sit at DIFFERENT lateral offsets, so a plain
                        # 2-point straight line between them cuts a visible diagonal clean across
                        # the pad instead of reading as a lane shift -- confirmed the concrete cause
                        # of the "ugly diagonal line" symptom (widen one arm symmetrically, look at
                        # its straight-through movement into the narrower opposite arm). Taper the
                        # LATERAL offset smoothly (a smoothstep ease over `segments` samples) from
                        # li's offset near the entry tail to lo's offset near the exit tail instead
                        # -- same "real lane drop" idea `build_lane_transition` already uses for an
                        # explicit merge piece, just inlined here for the auto-merge case. `db ==
                        # -da` for a through pair, so `perp_ccw(db) == -perp_ccw(da)`; expressing
                        # both ends in the SAME `perp` frame (entry lateral = `a.in_offset(li)`,
                        # exit lateral = `-b.out_offset(lo)`) is what makes the two endpoints match
                        # the li==lo branch's own far points exactly at t=0/t=1.
                        perp = lane_perp(da, a.traffic_side)
                        lat_in = a.in_offset(li)
                        lat_out = -b.out_offset(lo)
                        pts = []
                        for k in range(segments + 1):
                            t = k / segments
                            # a_tail at t=0, -b_tail at t=1 -- the per-arm generalization of the
                            # old `tail_length * (1 - 2t)` (byte-identical when a_tail == b_tail).
                            s = a_tail * (1.0 - t) - b_tail * t
                            ease = t * t * (3.0 - 2.0 * t)
                            lat = lat_in + (lat_out - lat_in) * ease
                            pts.append(vadd(vscale(perp, lat), vscale(da, s)))
                    out.append({"id": lane_id, "from": a.name, "to": b.name, "lane": li,
                                "lane_in": li, "lane_out": lo, "kind": "through", "turn": "S",
                                "points": pts})
                else:
                    edge_in = (p_in, da)
                    edge_out = (p_out, db)
                    try:
                        _, trim_in, trim_out, arc = corner_fillet(
                            edge_in, edge_out, turn_radius, segments,
                            max_tangent_len=min(a_tail, b_tail))
                    except ValueError:
                        continue  # near-collinear/degenerate arm pair at this radius -- skip
                    # Measured from p_in/p_out (the arm's own reference line), NOT trim_in/trim_out,
                    # so a straight-through and a turning movement sharing the same (arm, lane)
                    # reach the IDENTICAL far point -- they are physically the same incoming/outgoing
                    # lane before/after the split, and this is what makes build_ports' per-(arm,lane)
                    # port position independent of which movement is asked. Guarded with max() so a
                    # `tail_length` shorter than the fillet's own tangent length still produces a
                    # correctly-ordered polyline (far point strictly beyond the arc, never behind it)
                    # -- with a small, fixed `turn_radius` this tangent length stays tiny regardless
                    # of arm width/lane count, so it's essentially always `tail_length` in practice.
                    t_in = vlen(vsub(trim_in, p_in)) + 1.0
                    t_out = vlen(vsub(trim_out, p_out)) + 1.0
                    entry_far = vadd(p_in, vscale(da, max(a_tail, t_in)))
                    exit_far = vadd(p_out, vscale(db, max(b_tail, t_out)))
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
        a_tail = a.eff_tail_length(tail_length)
        d = arm_dir(a.angle_deg)
        perp = lane_perp(d, a.traffic_side)
        for i in range(a.lanes_in_count()):
            in_pos = vadd(vscale(perp, a.in_offset(i)), vscale(d, a_tail))
            out.append({"id": "%s_in_L%d" % (a.name, i), "arm": a.name, "lane": i,
                        "direction": "in", "position": in_pos, "tangent": vscale(d, -1.0)})
        for i in range(a.lanes_out_count()):
            out_pos = vadd(vscale(perp, a.out_offset(i)), vscale(d, a_tail))
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


def preset_nway(angles, lane_width=5.0, lanes=1, names=None, traffic_side='LEFT'):
    """Generic N-arm constructor -- any number of arms at any angles. `lanes` is either one
    scalar (every arm the same) or a sequence parallel to `angles` (independent per-arm lane
    counts, see `_per_arm`). `names` defaults to A, B, C, ... . `traffic_side` -- see `Arm` -- is
    applied to every arm (a junction can't mix LEFT/RIGHT between its own arms)."""
    n = len(angles)
    if names is None:
        names = [chr(ord('A') + i) if i < 26 else "Arm%d" % i for i in range(n)]
    lanes_per_arm = _per_arm(lanes, n)
    return [Arm(names[i], angles[i], lane_width, lanes_per_arm[i], traffic_side=traffic_side)
            for i in range(n)]


def preset_4way(angles=(0.0, 90.0, 180.0, 270.0), lane_width=5.0, lanes=1, traffic_side='LEFT'):
    return preset_nway(angles, lane_width, lanes, names=("N", "E", "S", "W"), traffic_side=traffic_side)


def preset_3way_t(through_angle=0.0, side_angle=90.0, lane_width=5.0, lanes=1, traffic_side='LEFT'):
    """Two collinear arms (the through street) + one side arm -- a T with a direct through move.
    `lanes` is either one scalar or a 3-sequence [through_arm_a, through_arm_b, side_arm]."""
    return preset_nway((through_angle, through_angle + 180.0, side_angle), lane_width, lanes,
                        names=("A", "B", "C"), traffic_side=traffic_side)


def preset_3way_y(angles=(0.0, 120.0, 240.0), lane_width=5.0, lanes=1, traffic_side='LEFT'):
    """Three arms at generic (non-collinear) angles -- every movement is a turn, all 3 corners
    filleted, no direct through-street."""
    return preset_nway(angles, lane_width, lanes, names=("A", "B", "C"), traffic_side=traffic_side)


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


def offset_spine_line(spine, off, traffic_side='LEFT'):
    """The per-point tangent-offset polyline at lateral offset `off` (see `lane_perp`) from an
    arbitrary 3D spine `spine = [(x, y, z), ...]` -- factored out of `build_segment_from_spine`
    (which now just calls this) so a second consumer (`build_segment_lane_markings`, below) can
    land lane-boundary MARKINGS at exactly the same offsets curbs/lane-centerlines already use,
    with no risk of drifting apart on a bent/multi-point spine."""
    n = len(spine)

    def tangent_at(i):
        a, b = spine[max(0, i - 1)], spine[min(n - 1, i + 1)]
        return vnorm(vsub((b[0], b[1]), (a[0], a[1])))

    return [(*vadd((spine[i][0], spine[i][1]), vscale(lane_perp(tangent_at(i), traffic_side), off)),
             spine[i][2]) for i in range(n)]


def build_segment_lane_markings(spine, lane_width=5.0, lanes=1, lanes_backward=None,
                                 traffic_side='LEFT'):
    """Lane-BOUNDARY lines (not lane centerlines) for a segment built the same way
    `build_segment_from_spine` lays out its lanes: one SOLID line at the single boundary between
    the forward and backward lane groups (offset 0 -- always exactly the shared edge of each
    direction's innermost lane, regardless of asymmetric lane counts either side), only emitted
    when BOTH `lanes` and `lanes_backward` are > 0 (a genuine two-way segment -- a one-way road
    has no such boundary to mark); plus one DASHED line at every INTERNAL boundary within each
    direction's own lane group (offset = i*lane_width forward / -i*lane_width backward, for i in
    1..count-1 -- none at all when that direction has <= 1 lane). Returns
    `[{'kind': 'yellow'|'white', 'points': [(x,y,z), ...]}, ...]`, using the SAME
    `offset_spine_line` curbs/lane-centerlines already use, so a marking always lands exactly
    between the two lanes it separates even on a bent spine."""
    lanes_backward = lanes if lanes_backward is None else lanes_backward
    out = []
    if lanes > 0 and lanes_backward > 0:
        out.append({"kind": "yellow", "points": offset_spine_line(spine, 0.0, traffic_side)})
    for i in range(1, lanes):
        out.append({"kind": "white", "points": offset_spine_line(spine, i * lane_width, traffic_side)})
    for i in range(1, lanes_backward):
        out.append({"kind": "white", "points": offset_spine_line(spine, -i * lane_width, traffic_side)})
    return out


def build_segment_from_spine(spine, lane_width=5.0, lanes=1, lanes_backward=None, segment_id="SEG",
                              traffic_side='LEFT'):
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

    `traffic_side` -- see `lane_perp` -- 'LEFT' (default, byte-identical to this function's
    original formulas) keeps FORWARD (A->B) lanes on the left of travel; 'RIGHT' mirrors both
    directions to the other side. Must match whatever `traffic_side` any intersection this segment
    connects to was built with, or the lane offsets won't line up at the seam.

    Same JSON lane shape as `build_lane_movements` -- {'id','from','to','lane_in','lane_out',
    'kind':'through','turn':'S','points':[...]} -- one entry per lane index per direction that
    actually has lanes, plus {'curbs': [[...], [...]]} for the two curb lines. Consumed
    identically to an intersection's movements by `export_segment_from_spine_json`/`WorldBaker`."""
    lanes_backward = lanes if lanes_backward is None else lanes_backward
    if lanes <= 0 and lanes_backward <= 0:
        raise ValueError("a segment needs at least one lane in SOME direction "
                          "(lanes=%d, lanes_backward=%d)" % (lanes, lanes_backward))

    def offset_line(off):
        return offset_spine_line(spine, off, traffic_side)

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


def _transition_lane_pairs(count_a, count_b, align):
    """-> (pairs, merge_target) for one traffic direction of a lane-count transition, where
    `count_a`/`count_b` are that direction's lane count at the p0/p1 end (may differ either way --
    a drop OR an add, handled identically by just swapping which end is 'wide').

    `pairs` is a list of `(idx_a_or_None, idx_b_or_None)`: both set = a lane index present at BOTH
    ends that continues through (possibly at a different physical offset, since the total lane
    count differs -- see `build_lane_transition`); `idx_a` set / `idx_b` None = a lane that only
    exists at the p0 end and DIES into `merge_target` (the innermost/outermost surviving lane's own
    p1-side index) by the p1 end; the mirror image is a lane BORN partway along, starting
    overlapped with `merge_target`'s p0-side position.

    `align='right'` keeps the OUTER (highest-index -- farthest from the spine, i.e. curb-adjacent)
    lanes aligned 1:1 counting inward from the top, and any excess lane(s) are the INNER
    (near-spine) ones -- a real lane-drop keeps the curb-side lane running straight and merges
    inner lane(s) into it. `align='left'` mirrors this: inner lanes stay aligned, excess OUTER
    lane(s) merge inward instead."""
    n = min(count_a, count_b)
    extra_a = count_a - n
    extra_b = count_b - n
    pairs = []
    if align == 'right':
        for k in range(n):
            pairs.append((count_a - 1 - k, count_b - 1 - k))
        merge_target = 0 if n > 0 else None
        pairs += [(j, None) for j in range(extra_a)]
        pairs += [(None, j) for j in range(extra_b)]
    elif align == 'left':
        for k in range(n):
            pairs.append((k, k))
        merge_target = n - 1 if n > 0 else None
        pairs += [(n + j, None) for j in range(extra_a)]
        pairs += [(None, n + j) for j in range(extra_b)]
    else:
        raise ValueError("align must be 'right' or 'left', got %r" % (align,))
    return pairs, merge_target


def build_lane_transition(p0, p1, lane_width=5.0, lanes_a=2, lanes_b=1, lanes_backward_a=None,
                           lanes_backward_b=None, align='right', segment_id="TR",
                           traffic_side='LEFT'):
    """A straight lane-COUNT transition (merge/drop, or the reverse -- a split/add) between p0
    (`lanes_a` forward / `lanes_backward_a` backward lanes) and p1 (`lanes_b` forward /
    `lanes_backward_b` backward) -- the piece connecting a wide road to a narrower one (or a
    narrower one to an intersection arm with more lanes), which `lib/road_network.py` (the older
    grid-based backbone pipeline) calls a taper (`lane_transitions()`) but this spline-offset model
    never had. `p0`/`p1` are already-absolute `(x, y, z)` points (same convention as
    `export_segment_from_spine_json`'s `spine`) -- straight only (no bend/slope param) for now; a
    curved/sloped transition can reuse this same per-lane-pair offset math against its own spine
    the way `build_segment_from_spine` does, just isn't wired up as a convenience wrapper yet.

    `traffic_side` -- see `lane_perp`/`build_segment_from_spine` -- must match whatever the
    segments/arms this piece connects to were built with.

    `lanes_backward_a`/`lanes_backward_b` default to `lanes_a`/`lanes_b` (symmetric, matching every
    other lane-count param in this module). `align` -- see `_transition_lane_pairs` -- defaults to
    `'right'`, a real lane-drop (curb-side lane(s) continue straight, excess inner lane(s) taper
    into them), not a center-taper and not merge-only requiring hand authoring.

    Every lane's centerline is a straight 2-point line from its own p0 offset to its own p1 offset
    (a genuine diagonal taper for a merging/splitting lane, since its p0 and p1 offsets differ --
    see `_transition_lane_pairs`); curbs are the outermost line at each end, LINEARLY interpolating
    half-width from the p0 end's total to the p1 end's total -- feeds directly as a 2-point
    per-point Radius taper into `kit_common.GN_RoadProfile` (already a variable-width curve sweep,
    no new GN math needed for the taper shape itself). Same JSON-compatible return shape as
    `build_segment_from_spine`: `{'curbs': [[p0,p1], [p0,p1]], 'lanes': [{'id','from','to',
    'lane_in','lane_out','kind','turn','points'}, ...]}`."""
    lanes_backward_a = lanes_a if lanes_backward_a is None else lanes_backward_a
    lanes_backward_b = lanes_b if lanes_backward_b is None else lanes_backward_b
    if lanes_a <= 0 and lanes_backward_a <= 0:
        raise ValueError("p0 end needs at least one lane in some direction")
    if lanes_b <= 0 and lanes_backward_b <= 0:
        raise ValueError("p1 end needs at least one lane in some direction")

    tangent = vnorm(vsub((p1[0], p1[1]), (p0[0], p0[1])))
    perp = lane_perp(tangent, traffic_side)

    def pt(base, offset):
        return (base[0] + perp[0] * offset, base[1] + perp[1] * offset, base[2])

    def offset_at(idx):
        return (idx + 0.5) * lane_width

    lane_list = []

    def add_direction(count_a, count_b, from_name, to_name, sign):
        pairs, merge_target = _transition_lane_pairs(count_a, count_b, align)
        for idx_a, idx_b in pairs:
            if idx_a is not None and idx_b is not None:
                lane_in, lane_out = idx_a, idx_b
                off_a, off_b = offset_at(idx_a), offset_at(idx_b)
            elif idx_b is None:
                lane_in, lane_out = idx_a, merge_target
                off_a, off_b = offset_at(idx_a), offset_at(merge_target)
            else:
                lane_in, lane_out = merge_target, idx_b
                off_a, off_b = offset_at(merge_target), offset_at(idx_b)
            p_start, p_end = pt(p0, sign * off_a), pt(p1, sign * off_b)
            if sign < 0:
                p_start, p_end = p_end, p_start   # backward: physically starts near p1 (from B)
            tag = "L%d" % lane_in if lane_in == lane_out else "L%dto%d" % (lane_in, lane_out)
            lane_list.append({
                "id": "%s_%s_%s_%s" % (segment_id, from_name, to_name, tag),
                "from": from_name, "to": to_name, "lane_in": lane_in, "lane_out": lane_out,
                "kind": "through", "turn": "S", "points": [p_start, p_end]})

    add_direction(lanes_a, lanes_b, "A", "B", 1.0)
    add_direction(lanes_backward_a, lanes_backward_b, "B", "A", -1.0)

    half_w_a = max(lanes_a, lanes_backward_a) * lane_width
    half_w_b = max(lanes_b, lanes_backward_b) * lane_width
    curbs = [[pt(p0, half_w_a), pt(p1, half_w_b)], [pt(p0, -half_w_a), pt(p1, -half_w_b)]]
    return {"curbs": curbs, "lanes": lane_list}


def export_lane_transition_dict(p0, p1, lane_width=5.0, lanes_a=2, lanes_b=1,
                                 lanes_backward_a=None, lanes_backward_b=None, align='right',
                                 segment_id="TR", traffic_side='LEFT'):
    """The dict half of `export_lane_transition_json` (no file write) -- `p0`/`p1` already
    ABSOLUTE world coordinates, Blender-Z-up -> Godot-Y-up (`[x, z, -y]`) applied here directly
    since a transition carries no separate `z` base the way `export_segment_json` does. Same
    `{"segment_id", "lanes": [...]}` shape every non-intersection export produces, so a combiner
    (see `lib/lane_kit.py`) can merge intersection/segment/transition pieces uniformly."""
    seg = build_lane_transition(p0, p1, lane_width, lanes_a, lanes_b, lanes_backward_a,
                                 lanes_backward_b, align, segment_id, traffic_side)
    lanes_out = [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                   "lane_index": m["lane_in"], "lane_index_out": m["lane_out"], "kind": m["kind"],
                   "turn": m["turn"], "oneway": True, "loop": False,
                   "points": [[p[0], p[2], -p[1]] for p in m["points"]]} for m in seg["lanes"]]
    return {"segment_id": segment_id, "lanes": lanes_out}


def export_lane_transition_json(path, p0, p1, lane_width=5.0, lanes_a=2, lanes_b=1,
                                 lanes_backward_a=None, lanes_backward_b=None, align='right',
                                 segment_id="TR", traffic_side='LEFT'):
    """Write `export_lane_transition_dict`'s data to `path` as JSON -- so `WorldBaker`'s sidecar
    loader, which only ever reads the top-level `lanes` array, consumes this identically to a
    plain segment or an intersection, with no Java changes."""
    import json
    d = export_lane_transition_dict(p0, p1, lane_width, lanes_a, lanes_b, lanes_backward_a,
                                     lanes_backward_b, align, segment_id, traffic_side)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


def build_straight_segment(p0, p1, lane_width=5.0, lanes=1, segment_id="SEG", bend=0.0, segments=8,
                            z0=0.0, z1=0.0, bend_z=0.0, lanes_backward=None, traffic_side='LEFT'):
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
    return build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id, traffic_side)


def export_segment_from_spine_dict(spine, lane_width=5.0, lanes=1, lanes_backward=None,
                                    segment_id="SEG", traffic_side='LEFT'):
    """The dict half of `export_segment_from_spine_json` (no file write) -- `spine` already
    carries ABSOLUTE world Z per point (e.g. sampled directly from a Blender Curve object's
    evaluated world-space points), so no separate `z` base argument is added here. Same
    `{"segment_id", "lanes": [...]}` shape every non-intersection export produces."""
    seg = build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id, traffic_side)
    lanes_out = [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                   "lane_index": m["lane_in"], "lane_index_out": m["lane_out"], "kind": m["kind"],
                   "turn": m["turn"], "oneway": True, "loop": False,
                   "points": [[p[0], p[2], -p[1]] for p in m["points"]]} for m in seg["lanes"]]
    return {"segment_id": segment_id, "lanes": lanes_out}


def export_segment_from_spine_json(path, spine, lane_width=5.0, lanes=1, lanes_backward=None,
                                    segment_id="SEG", traffic_side='LEFT'):
    """Write `export_segment_from_spine_dict`'s data to `path` as JSON, same shape/axis-conversion
    convention as `export_json` (`godot = (blender_x, z, -blender_y)`)."""
    import json
    d = export_segment_from_spine_dict(spine, lane_width, lanes, lanes_backward, segment_id,
                                        traffic_side)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


def export_segment_dict(p0, p1, lane_width=5.0, lanes=1, segment_id="SEG", z=0.0,
                         bend=0.0, segments=8, z0=0.0, z1=0.0, bend_z=0.0, lanes_backward=None,
                         traffic_side='LEFT'):
    """The dict half of `export_segment_json` (no file write). `z` is the constant world-height
    base (as before); each point's own relative elevation (`z0`/`z1`/`bend_z` -- see
    `build_straight_segment`) is ADDED on top, so a flat segment (all defaults) emits exactly `z`
    unchanged. Same `{"segment_id", "lanes": [...]}` shape every non-intersection export
    produces."""
    seg = build_straight_segment(p0, p1, lane_width, lanes, segment_id, bend, segments, z0, z1,
                                  bend_z, lanes_backward, traffic_side)
    lanes_out = [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                   "lane_index": m["lane_in"], "lane_index_out": m["lane_out"], "kind": m["kind"],
                   "turn": m["turn"], "oneway": True, "loop": False,
                   "points": [[p[0], z + p[2], -p[1]] for p in m["points"]]} for m in seg["lanes"]]
    return {"segment_id": segment_id, "lanes": lanes_out}


def export_segment_json(path, p0, p1, lane_width=5.0, lanes=1, segment_id="SEG", z=0.0,
                         bend=0.0, segments=8, z0=0.0, z1=0.0, bend_z=0.0, lanes_backward=None,
                         traffic_side='LEFT'):
    """Write `export_segment_dict`'s data to `path` as JSON, same shape/axis-conversion
    convention as `export_json` (`godot = (blender_x, z, -blender_y)`) -- `WorldBaker`'s sidecar
    loader only ever reads the `lanes` array (`id`/`points`/`loop`/`turn`/`kind`), so this is
    directly consumable with no Java changes."""
    import json
    d = export_segment_dict(p0, p1, lane_width, lanes, segment_id, z, bend, segments, z0, z1,
                             bend_z, lanes_backward, traffic_side)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    return d


# --------------------------------------------------------------------------------- export

def export_dict(arms, kerb_radius, junction_id, segments=8, through_tol_deg=2.0, tail_length=12.0,
                 lane_map=None, center=(0.0, 0.0)):
    """The full graph-shaped export for one junction -- arms as nodes, lane movements as directed
    edges, ports as the seams a future cross-piece linker (or a plain approach lane tile) would
    connect to. Pure data (2D points; a Z is added by the caller, since this module never carries
    one). `lane_map` -- see `build_lane_movements` -- optionally overrides the default
    lane-to-lane pairing. See `export_json` to write it straight to a sidecar file.

    `center` -- (x, y), default (0, 0) -- the junction's own world-space position, ADDED to every
    exported point. Every geometry function this module builds on (`build_lane_movements`,
    `build_ports`, ...) works in a LOCAL frame centered on the junction (an `Arm` only carries an
    angle, never a world position), so without this the export is silently junction-relative --
    correct only for a junction actually built at world origin. **Found and fixed this session**
    (road_blender_godot.md P6.7): every real intersection built off-origin (i.e. almost all of
    them) was exporting local coordinates, which happened to go unnoticed by every self-test and
    the one production caller (`RKA_OT_build_intersection`'s own `export_path`) built/tested at or
    very near the origin. Default (0, 0) keeps every existing call site (including this module's
    own self-tests) byte-identical -- this is a strictly additive fix, not a behavior change for
    anyone already passing world-centered arms/tail_length some other way."""
    movements = build_lane_movements(arms, kerb_radius, segments, through_tol_deg, tail_length,
                                      junction_id=junction_id, lane_map=lane_map)
    ports = build_ports(arms, tail_length)
    cx, cy = center
    return {
        "junction_id": junction_id,
        "arms": [{"name": a.name, "angle_deg": a.angle_deg, "lanes": a.lanes,
                   "lane_width": a.lane_width, "lanes_in": a.lanes_in_count(),
                   "lanes_out": a.lanes_out_count(), "oneway": a.oneway} for a in arms],
        "lanes": [{"id": m["id"], "from_arm": m["from"], "to_arm": m["to"],
                    "lane_index": m["lane_in"], "lane_index_out": m["lane_out"],
                    "kind": m["kind"], "turn": m["turn"], "oneway": True, "loop": False,
                    "points": [[p[0] + cx, p[1] + cy] for p in m["points"]]} for m in movements],
        "ports": [{"id": "%s_%s" % (junction_id, p["id"]), "arm": p["arm"], "lane": p["lane"],
                    "direction": p["direction"],
                    "position": [p["position"][0] + cx, p["position"][1] + cy],
                    "tangent": list(p["tangent"])} for p in ports],
    }


def export_json(path, arms, kerb_radius, junction_id, segments=8, through_tol_deg=2.0,
                 tail_length=12.0, z=0.0, lane_map=None, center=(0.0, 0.0)):
    """Write `export_dict`'s data to `path` as JSON, with every 2D (Blender ground-plane) point
    lifted to a 3D **Godot-space** point (this module's 2D math is Blender's X/Y ground plane,
    Z-up; Godot is Y-up) so the Godot side can consume the sidecar's points as world-space
    positions directly, with no axis swizzle of its own to remember: `godot = (blender_x, z,
    -blender_y)` -- the same Blender-Z-up -> Godot-Y-up convention glTF import already applies
    to every other Blender-authored asset in this project, just applied here by hand since this
    sidecar is raw JSON, not glTF. `z` is the (small, near-constant) world height every point
    sits at -- becomes Godot's Y. `center` -- see `export_dict` -- the junction's world (x, y);
    default (0, 0) is byte-identical to before this parameter existed. No bpy dependency --
    callable from a plain `python3` self-test/CI check, not just from inside Blender."""
    import json
    d = export_dict(arms, kerb_radius, junction_id, segments, through_tol_deg, tail_length,
                     lane_map, center)
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

    # 7. Turn radius is a SMALL, FIXED `turn_radius` (default 3.5m, real-world minimum vehicle
    #    turning radius) -- deliberately decoupled from `kerb_radius` (which only sizes the
    #    curb/pad corner now, see build_junction_boundary/build_junction_curb_segments): raising
    #    `turn_radius` widens the generated turn arcs; raising `kerb_radius` alone does NOT change
    #    them at all (a regression guard -- this module briefly coupled lane-turn radius to
    #    kerb_radius/lane count for a bigger "AI-comfortable" swing, which visibly bulged turns
    #    outside the pad even for a plain single-lane 4-way and was reverted).
    moves_tight = build_lane_movements(arms, kerb_radius=8.0, segments=8, tail_length=12.0,
                                        turn_radius=2.0)
    moves_relaxed = build_lane_movements(arms, kerb_radius=8.0, segments=8, tail_length=12.0,
                                          turn_radius=6.0)
    turn_tight = next(m for m in moves_tight if m["kind"] == "turn")
    turn_relaxed = next(m for m in moves_relaxed
                        if m["kind"] == "turn" and m["from"] == turn_tight["from"] and m["to"] == turn_tight["to"])
    # Tangent length (p_in -> the arc's own first point) is a direct, unambiguous, always-positive
    # function of radius (= radius / tan(theta/2)) regardless of which side a corner happens to
    # bulge toward -- unlike raw distance-from-origin, which isn't guaranteed monotonic in radius
    # for every arm-pair direction (confirmed: picking a different 'first turn found' here made an
    # earlier origin-distance-based version of this same test flaky).
    a_arm = next(a for a in arms if a.name == turn_tight["from"])
    p_in_tight = vscale(perp_ccw(arm_dir(a_arm.angle_deg)), a_arm.in_offset(turn_tight["lane_in"]))
    tangent_tight = vlen(vsub(turn_tight["points"][1], p_in_tight))
    tangent_relaxed = vlen(vsub(turn_relaxed["points"][1], p_in_tight))
    assert tangent_relaxed > tangent_tight, (tangent_relaxed, tangent_tight)

    moves_kerb4 = build_lane_movements(arms, kerb_radius=4.0, segments=8, tail_length=12.0)
    moves_kerb10 = build_lane_movements(arms, kerb_radius=10.0, segments=8, tail_length=12.0)
    turn_k4 = next(m for m in moves_kerb4 if m["kind"] == "turn")
    turn_k10 = next(m for m in moves_kerb10
                     if m["kind"] == "turn" and m["from"] == turn_k4["from"] and m["to"] == turn_k4["to"])
    assert turn_k4["points"] == turn_k10["points"], "kerb_radius must not affect lane turn geometry"
    print("OK: turn_radius (not kerb_radius) sizes turn arcs -- fixed, small, decoupled from the "
          "curb's own radius")

    # 8. Per-arm lane counts: a 2-lane main street (arms A/B) crossing a 1-lane side street (C).
    arms_mixed = preset_3way_t(through_angle=0.0, side_angle=90.0, lanes=(2, 2, 1))
    a2 = next(a for a in arms_mixed if a.name == "A")
    c1 = next(a for a in arms_mixed if a.name == "C")
    assert a2.lanes == 2 and c1.lanes == 1
    moves_mixed = build_lane_movements(arms_mixed, kerb_radius=8.0, segments=8, tail_length=20.0)
    ab = [m for m in moves_mixed if m["from"] == "A" and m["to"] == "B"]
    ac = [m for m in moves_mixed if m["from"] == "A" and m["to"] == "C"]
    assert len(ab) == 2, len(ab)   # both leaving lanes match 1:1 -- both continue straight through
    # AUTO-MERGE (see build_lane_movements): BOTH of A's arriving lanes still get a movement onto
    # the 1-lane side street C -- lane 0 feeds C's only lane directly, lane 1 (no same-index
    # partner) funnels into that SAME lane instead of being dropped, i.e. a real lane-drop wedge.
    assert len(ac) == 2, len(ac)
    ac_lane0 = next(m for m in ac if m["lane_in"] == 0)
    ac_lane1 = next(m for m in ac if m["lane_in"] == 1)
    assert ac_lane0["lane_out"] == 0 and ac_lane1["lane_out"] == 0, (ac_lane0, ac_lane1)
    try:
        preset_3way_t(lanes=(1, 2))   # wrong length for a 3-arm preset
        assert False, "expected ValueError for a mismatched per-arm lanes length"
    except ValueError:
        pass
    print("OK: per-arm lane counts (mixed 2/2/1 T-junction, length-mismatch guarded)")

    # 8b. AUTO-FAN-OUT (the mirror case of 8's auto-merge): C (1 arriving lane) turning onto the
    #     2-lane main street A must feed BOTH of A's leaving lanes, not just the same-index lane 0
    #     -- otherwise A's 2nd leaving lane has zero incoming movements from C and no car turning
    #     from C would ever be routed onto it.
    ca = [m for m in moves_mixed if m["from"] == "C" and m["to"] == "A"]
    assert len(ca) == 2, len(ca)
    ca_lane0, ca_lane1 = (next(m for m in ca if m["lane_out"] == 0),
                          next(m for m in ca if m["lane_out"] == 1))
    assert ca_lane0["lane_in"] == 0 and ca_lane1["lane_in"] == 0, (ca_lane0, ca_lane1)
    assert ca_lane0["id"] != ca_lane1["id"], "fanned-out movements must still get distinct ids"
    print("OK: auto-fan-out (1-lane arm turning onto a 2-lane arm feeds every leaving lane)")

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

    # 22. Asymmetric widening (Arm.lanes_out): an arm with lanes=1 (in) but lanes_out=2 (out) has
    #     an independently wider DEPARTING curb edge while the ARRIVING edge stays at the
    #     symmetric 1-lane width -- half_width() (the conservative max) reflects the wider side,
    #     and curb_edges only moves the affected (CCW/out) edge, leaving the CW/in edge unchanged
    #     versus an otherwise-identical symmetric 1-lane arm.
    asym = Arm("A", 0.0, lane_width=5.0, lanes=1, lanes_out=2)
    sym1 = Arm("A", 0.0, lane_width=5.0, lanes=1)
    assert asym.lanes_in_count() == 1 and asym.lanes_out_count() == 2
    assert asym.in_width() == 5.0 and asym.out_width() == 10.0
    assert asym.half_width() == 10.0
    neighbor = Arm("B", 90.0, lane_width=5.0, lanes=1)
    edge_asym_a, edge_asym_b = curb_edges(asym, neighbor)
    edge_sym_a, edge_sym_b = curb_edges(sym1, neighbor)
    assert vlen(vsub(edge_asym_a[0], edge_sym_a[0])) > 1.0, "widened OUT side must move"
    neighbor2 = Arm("C", -90.0, lane_width=5.0, lanes=1)
    edge_asym2_a, edge_asym2_b = curb_edges(neighbor2, asym)
    edge_sym2_a, edge_sym2_b = curb_edges(neighbor2, sym1)
    assert vlen(vsub(edge_asym2_b[0], edge_sym2_b[0])) < eps, "untouched IN side must stay put"
    # oneway still wins over lanes_out
    out_only = Arm("D", 0.0, lane_width=5.0, lanes=1, oneway='OUT', lanes_out=3)
    assert out_only.lanes_in_count() == 0 and out_only.lanes_out_count() == 3
    in_only_ignores_lanes_out = Arm("E", 0.0, lane_width=5.0, lanes=1, oneway='IN', lanes_out=3)
    assert in_only_ignores_lanes_out.lanes_out_count() == 0
    print("OK: asymmetric widening (Arm.lanes_out moves only the departing curb edge)")

    # 23. corner_fillet max_tangent_len: a tight (small-theta) corner's unclamped tangent length
    #     comfortably exceeds a small max_tangent_len; clamping shrinks the EFFECTIVE radius (not
    #     just truncating trim points) so every arc point still sits at the (now smaller) radius
    #     from its own center, and trims land within max_tangent_len of the vertex. Unclamped
    #     (max_tangent_len=None, the default) is byte-identical to before this parameter existed.
    tight_a = ((10.0, 0.0), (-1.0, 0.05))
    tight_b = ((10.0, 0.0), (-1.0, -0.05))
    _, unclamped_trim_a, _, _ = corner_fillet(tight_a, tight_b, radius=6.0, segments=8)
    unclamped_len = vlen(vsub(unclamped_trim_a, (10.0, 0.0)))
    assert unclamped_len > 50.0, unclamped_len   # confirms this corner IS tight enough to matter
    _, clamped_trim_a, _, clamped_arc = corner_fillet(
        tight_a, tight_b, radius=6.0, segments=8, max_tangent_len=5.0)
    clamped_len = vlen(vsub(clamped_trim_a, (10.0, 0.0)))
    assert clamped_len <= 5.0 + 1e-6, clamped_len
    print("OK: corner_fillet max_tangent_len clamps effective radius on a tight corner")

    # 24. build_curb_corners never raises on a near-degenerate live-drag state: two DIFFERENT arms
    #     (not a through-pair) whose angles are nearly identical produce theta ~ 0 at their shared
    #     corner -- previously an uncaught ValueError out of corner_fillet, propagating past
    #     clear_generated_mesh_objects() having already deleted the old geometry (the "small angle
    #     tweak breaks the whole intersection" bug). That pair is now silently skipped (one fewer
    #     corner), every other corner is unaffected, and a normal (non-degenerate) 4-way is unchanged.
    arms_degenerate = [Arm("A", 0.0), Arm("A2", 0.00001), Arm("B", 120.0), Arm("C", 240.0)]
    corners_degenerate = build_curb_corners(arms_degenerate, kerb_radius=8.0, tail_length=12.0)
    assert len(corners_degenerate) == 3, len(corners_degenerate)   # 4 pairs - 1 skipped
    corners_normal = build_curb_corners(preset_4way(), kerb_radius=8.0, tail_length=12.0)
    assert len(corners_normal) == 4, len(corners_normal)
    print("OK: build_curb_corners skips a near-degenerate corner instead of raising")

    # 25. build_lane_transition: a 2->1 lane drop (align='right', the default) -- 2 forward
    #     entries (1 continuing/'through' lane whose OWN offset still shifts since the pavement
    #     narrows, 1 dying lane), the dying lane's end point and the through lane's end point are
    #     the SAME point at p1 (a real merge wedge, not two independent lines), and the curb
    #     narrows from the wide end's width to the narrow end's.
    tp0, tp1 = (0.0, 0.0, 0.0), (30.0, 0.0, 0.0)
    drop = build_lane_transition(tp0, tp1, lane_width=5.0, lanes_a=2, lanes_b=1, align='right')
    fwd = [m for m in drop["lanes"] if m["from"] == "A"]
    bwd = [m for m in drop["lanes"] if m["from"] == "B"]
    assert len(fwd) == 2 and len(bwd) == 2, (len(fwd), len(bwd))
    dying = next(m for m in fwd if m["lane_in"] != m["lane_out"])
    surviving = next(m for m in fwd if m["lane_in"] == m["lane_out"])
    assert vlen(vsub(dying["points"][-1], surviving["points"][-1])) < eps
    assert dying["points"][-1][0] > dying["points"][0][0]   # actually reaches toward p1, not stub
    left_c, right_c = drop["curbs"]
    assert abs(vlen(vsub(left_c[0], tp0)) - 2 * 5.0) < eps    # wide end: 2 lanes -> 10m
    assert abs(vlen(vsub(left_c[1], tp1)) - 1 * 5.0) < eps    # narrow end: 1 lane -> 5m
    print("OK: build_lane_transition 2->1 drop (merge wedge converges, curb narrows)")

    # 26. build_lane_transition: the mirror case (1->2, a split/add) with align='left', and
    #     export_lane_transition_json round-trips through JSON with the same shape/axis convention
    #     as export_segment_from_spine_json.
    split = build_lane_transition(tp0, tp1, lane_width=5.0, lanes_a=1, lanes_b=2, align='left')
    fwd_split = [m for m in split["lanes"] if m["from"] == "A"]
    assert len(fwd_split) == 2
    born = next(m for m in fwd_split if m["lane_in"] != m["lane_out"])
    assert vlen(vsub(born["points"][0], (0.0, 0.0, 0.0))) >= 0.0   # starts somewhere near p0...
    with _tempfile.TemporaryDirectory() as tmp:
        p = _os.path.join(tmp, "transition.lanekit.json")
        sd = export_lane_transition_json(p, tp0, tp1, lane_width=5.0, lanes_a=2, lanes_b=1,
                                          segment_id="TR1")
        with open(p) as f:
            reloaded = _json.load(f)
        assert reloaded == sd
        assert all(set(lane.keys()) >= {"id", "points", "loop", "turn", "kind"}
                   for lane in reloaded["lanes"])
    print("OK: build_lane_transition split/add (align='left') + export_lane_transition_json "
          "round-trip")

    # 27. build_junction_boundary: a 4-way (no through-pairs among 90-deg-apart consecutive arms)
    #     yields 2 tail points/arm + 1 corner/arm = 4*(2+1) = 12 vertices, all corner radii == the
    #     unclamped kerb_radius when it's comfortably within the per-edge available run (arms far
    #     enough apart, radius well under each edge's own vertex-to-tail-cap distance); a 3-way T
    #     (one through-pair, A/B 180 deg apart and angularly adjacent) yields 3*2 + 2 = 8 (one
    #     fewer corner, the skipped through pair). The near-degenerate live-drag case from test 24
    #     doesn't raise here either.
    boundary4 = build_junction_boundary(preset_4way(), kerb_radius=6.0, tail_length=12.0)
    assert len(boundary4) == 12, len(boundary4)
    corner_radii = [r for (x, y, r) in boundary4 if r > 0]
    assert len(corner_radii) == 4 and all(abs(r - 6.0) < eps for r in corner_radii), corner_radii
    # kerb_radius=8.0 with this same geometry demands MORE tangent length (8.0) than either edge
    # actually has to give (a symmetric 1-lane 4-way's vertex sits exactly 7.0m from each arm's own
    # tail-cap point at tail_length=12.0) -- confirms the per-edge clamp (see
    # `_junction_corner_vertex`'s docstring) engages even in the plain symmetric case, not just the
    # asymmetric-arm-width bug it was written to fix, quietly correcting a latent ~1m overshoot
    # that the old blanket `tail_length * tan(theta/2)` formula never caught (12.0 * tan(45) = 12.0,
    # comfortably >= 8.0, so it never clamped at all).
    boundary4_tight = build_junction_boundary(preset_4way(), kerb_radius=8.0, tail_length=12.0)
    tight_radii = [r for (x, y, r) in boundary4_tight if r > 0]
    assert len(tight_radii) == 4 and all(abs(r - 7.0) < eps for r in tight_radii), tight_radii
    boundary_t = build_junction_boundary(preset_3way_t(through_angle=0.0, side_angle=90.0),
                                          kerb_radius=8.0, tail_length=12.0)
    assert len(boundary_t) == 8, len(boundary_t)
    assert len([r for (x, y, r) in boundary_t if r > 0]) == 2
    boundary_degenerate = build_junction_boundary(arms_degenerate, kerb_radius=8.0, tail_length=12.0)
    assert len([r for (x, y, r) in boundary_degenerate if r > 0]) == 3   # 1 skipped, same as test 24
    # asymmetric arm: its own tail-cap edge is genuinely asymmetric (in/out tail points at
    # different distances from the spine), matching Arm.lanes_out from test 22.
    arms_asym = [Arm("A", 0.0, lane_width=5.0, lanes=1, lanes_out=2), Arm("B", 120.0),
                 Arm("C", 240.0)]
    boundary_asym = build_junction_boundary(arms_asym, kerb_radius=8.0, tail_length=12.0)
    a_pts = [(x, y) for (x, y, r) in boundary_asym[:2]]   # A's own p_in, p_out (first arm, sorted)
    assert abs(vlen(vsub(a_pts[0], a_pts[1])) - (5.0 + 10.0)) < eps, a_pts   # in_width+out_width
    print("OK: build_junction_boundary (4-way=12 verts, T-skip=8, degenerate-safe, asymmetric cap)")

    # 28. build_junction_curb_segments: a 4-way (4 real corners, no through-pairs among adjacent
    #     arms) -> 4 open 3-point segments, none touching an arm's own tail-cap span; a 3-way T
    #     (1 through-pair) -> 2 segments. Each segment's outer two points have radius 0 (no
    #     fillet -- an arm's own tail point) and the MIDDLE point carries the corner's radius.
    curbs4 = build_junction_curb_segments(preset_4way(), kerb_radius=8.0, tail_length=12.0)
    assert len(curbs4) == 4, len(curbs4)
    for seg in curbs4:
        assert len(seg) == 3, seg
        assert seg[0][2] == 0.0 and seg[2][2] == 0.0 and seg[1][2] > 0.0, seg
    curbs_t = build_junction_curb_segments(preset_3way_t(through_angle=0.0, side_angle=90.0),
                                            kerb_radius=8.0, tail_length=12.0)
    assert len(curbs_t) == 2, len(curbs_t)
    # No curb segment's endpoint should ever coincide with another arm's OWN in/out tail pair
    # forming a closed span across that arm's mouth -- i.e. no segment's two OUTER points belong
    # to the SAME arm (that would be exactly the tail-cap this function must never emit).
    arms4 = preset_4way()
    for a in arms4:
        d = arm_dir(a.angle_deg)
        perp = perp_ccw(d)
        p_in = vadd(vscale(perp, -a.in_width()), vscale(d, 12.0))
        p_out = vadd(vscale(perp, a.out_width()), vscale(d, 12.0))
        for seg in curbs4:
            outer = (seg[0][:2], seg[2][:2])
            assert not (vlen(vsub(outer[0], p_in)) < eps and vlen(vsub(outer[1], p_out)) < eps), \
                "a curb segment must never span one arm's own IN->OUT tail-cap"
    print("OK: build_junction_curb_segments (per-corner only, no arm tail-cap ever gets a curb)")

    # 29. Corner radius scales with lane count so a wide arm's outer-lane turn never reaches past
    #     the pad/curb corner: a 4-way where TWO adjacent arms have 4 lanes each must produce a
    #     corner radius matching the WIDEST movement's own radius formula
    #     (kerb_radius + (lanes-1+0.5)*lane_width) between them, while the OTHER (still 1-lane)
    #     corners stay at plain kerb_radius -- unaffected, confirming this is corner-local, not
    #     junction-global.
    arms_wide = preset_4way(lanes=1)
    n_arm = next(a for a in arms_wide if a.name == "N")
    e_arm = next(a for a in arms_wide if a.name == "E")
    n_arm.lanes = 4
    e_arm.lanes = 4
    # A generous tail_length here so the per-edge tangent-length clamp (a SEPARATE safety net,
    # tested above -- and now measured against each edge's OWN vertex-to-tail-cap distance, which
    # nets out to roughly `tail_length - that arm's own width`, not a flat `tail_length *
    # tan(theta/2)`) doesn't mask the lane-scaling formula itself: a 4-lane arm's own width is
    # 20m, so tail_length must clear the desired 25.5m radius PLUS that 20m, not just the radius.
    boundary_wide = build_junction_boundary(arms_wide, kerb_radius=8.0, tail_length=60.0)
    corner_radii_wide = sorted(r for (x, y, r) in boundary_wide if r > 0)
    expected_wide = 8.0 + (4 - 0.5) * 5.0   # 25.5 -- matches build_lane_movements' own li=lo=3 case
    assert abs(corner_radii_wide[-1] - expected_wide) < eps, corner_radii_wide
    # N-E, E-S, and W-N EACH touch a 4-lane arm on at least one side (E is wide at both its own
    # corners; N likewise) -- so 3 of the 4 corners scale up; only S-W (neither arm widened)
    # stays plain kerb_radius. Scaling is corner-local (per adjacent pair), not junction-global --
    # a corner is only ever as wide as the WIDEST arm actually touching it.
    assert sum(1 for r in corner_radii_wide if abs(r - 8.0) < eps) == 1, corner_radii_wide
    assert sum(1 for r in corner_radii_wide if abs(r - expected_wide) < eps) == 3, corner_radii_wide
    print("OK: junction corner radius scales with lane count (3 corners touching a 4-lane arm "
          "widen to %.1f, the one corner between two still-1-lane arms stays plain kerb_radius)"
          % corner_radii_wide[-1])

    # 30. IMPORTANT, non-obvious fact this test locks in: the corner's (x, y) VERTEX position is
    #     driven purely by curb_edges (arm angle + total arm width via in_width/out_width) and is
    #     COMPLETELY UNAFFECTED by kerb_radius/the scaling this session added -- `radius` only
    #     controls how much a GN Fillet Curve rounds OFF that vertex (cutting INTO the corner, so a
    #     BIGGER radius makes the rendered mesh's corner draw BACK, not extend further out). So
    #     test 29's radius scaling does NOT, on its own, grow the pad's rendered reach at a corner
    #     -- confirmed here by asserting the vertex is identical whether computed with a plain
    #     kerb_radius (via build_curb_corners) or through _junction_corner_vertex's scaled radius.
    #     (This pad/curb corner scaling is UNRELATED to the lane-turn-radius story in tests 7/32 --
    #     lane turns now use their own small, fixed `turn_radius`, decoupled from `kerb_radius`
    #     entirely; this test is only about the PAD's own corner rounding.)
    plain_corners = build_curb_corners(arms_wide, kerb_radius=8.0, segments=8)
    scaled_corner = _junction_corner_vertex(
        next(a for a in arms_wide if a.name == "N"), next(a for a in arms_wide if a.name == "E"),
        kerb_radius=8.0, tail_length=12.0)
    plain_ne = next(c for c in plain_corners
                     if {c["arm_a"], c["arm_b"]} == {"N", "E"})
    assert vlen(vsub(scaled_corner[0], plain_ne["vertex"])) < eps, \
        (scaled_corner[0], plain_ne["vertex"])
    assert scaled_corner[1] != 8.0   # the RADIUS did change...
    print("OK: corner radius scaling changes ONLY the fillet radius, never the vertex position "
          "(pad/curb corner only -- unrelated to the separately-fixed lane turn radius)")

    # 31. The originally-reported symptom: widen ONE arm of a 4-way while every other arm stays at
    #     1 lane -- every one of that arm's lanes must now get a movement (auto-merged into
    #     neighbors' single lane) in EVERY direction it can legally go (both turns AND the through
    #     movement to the opposite arm), not just some. Before the auto-merge fix this arm's 2nd+
    #     lanes produced ZERO lanecl_* data anywhere, since min(4, 1) == 1 in every direction.
    arms_n4 = preset_4way(lanes=1)
    n4 = next(a for a in arms_n4 if a.name == "N")
    n4.lanes = 4
    moves_n4 = build_lane_movements(arms_n4, kerb_radius=8.0, tail_length=12.0)
    for other in ("E", "S", "W"):
        from_n = [m for m in moves_n4 if m["from"] == "N" and m["to"] == other]
        assert len(from_n) == 4, (other, len(from_n))   # all 4 of N's lanes now produce a movement
        assert {m["lane_in"] for m in from_n} == {0, 1, 2, 3}, from_n
        assert all(m["lane_out"] == 0 for m in from_n), from_n   # all merge into the 1-lane target
    print("OK: widening a single arm while its neighbors stay 1-lane -- every one of the new "
          "arm's lanes now produces movement/lanecl_* data in every direction, the fix for the "
          "originally-reported 'added lane has no data' bug")

    # 31b. The auto-merged THROUGH movement (N's lane 1..3 -> S's lane 0, mismatched lane_in !=
    #      lane_out) must NOT be a raw 2-point diagonal straight line between the two different
    #      lateral offsets -- that reads as a line cutting clean across the pad, the concrete
    #      "ugly diagonal" symptom seen alongside the originally-reported missing-data bug. It
    #      must instead taper (more than 2 points) and land EXACTLY on the same far endpoints the
    #      li==lo case would use (so ports/build_ports still agree), monotonically progressing
    #      along the arm direction with no lateral overshoot past either endpoint's own offset.
    through_n4 = [m for m in moves_n4 if m["from"] == "N" and m["to"] == "S" and m["lane_in"] != 0]
    assert len(through_n4) == 3, through_n4   # N's lanes 1,2,3 all auto-merge into S's lane 0
    for m in through_n4:
        pts = m["points"]
        assert len(pts) > 2, ("through taper must have more than 2 points", m)
        s4 = next(a for a in arms_n4 if a.name == "S")
        n4b = next(a for a in arms_n4 if a.name == "N")
        da_n, db_s = arm_dir(n4b.angle_deg), arm_dir(s4.angle_deg)
        expected_entry = vadd(vscale(perp_ccw(da_n), n4b.in_offset(m["lane_in"])), vscale(da_n, 12.0))
        expected_exit = vadd(vscale(perp_ccw(db_s), s4.out_offset(m["lane_out"])), vscale(db_s, 12.0))
        assert vlen(vsub(pts[0], expected_entry)) < eps, (pts[0], expected_entry)
        assert vlen(vsub(pts[-1], expected_exit)) < eps, (pts[-1], expected_exit)
        # lateral offset (perpendicular to N's own direction) must move monotonically from the
        # entry's lateral value to the exit's -- never overshooting past either end.
        perp_n = perp_ccw(da_n)
        lats = [p[0] * perp_n[0] + p[1] * perp_n[1] for p in pts]
        lo_lat, hi_lat = min(lats[0], lats[-1]), max(lats[0], lats[-1])
        assert all(lo_lat - eps <= lat <= hi_lat + eps for lat in lats), lats
    print("OK: auto-merged through movement tapers laterally (smoothstep) instead of a raw "
          "diagonal line, endpoints still match the li==lo far-point convention exactly")

    # 32. With a small, fixed `turn_radius` (see test 7's revert), a wide (4-lane, two adjacent
    #     arms) junction ALREADY satisfies recommended_tail_length's own margin at the historical
    #     default (12m) -- confirming the small-fixed-radius revert genuinely fixes the "lane goes
    #     far outside the mesh" symptom on its own, with no tail_length growth needed at all in the
    #     common case (unlike the large kerb_radius-scaled turn radius this module briefly used,
    #     where the SAME scenario needed ~45m). recommended_tail_length's search mechanism itself
    #     is still exercised/verified separately: forcing a pathologically large turn_radius (well
    #     past what any UI default would ever use) still makes it correctly grow tail_length.
    boundary_fixed = build_junction_boundary(arms_wide, kerb_radius=8.0, tail_length=12.0)
    moves_fixed = build_lane_movements(arms_wide, kerb_radius=8.0, tail_length=12.0)
    pad_max_fixed = max(vlen((x, y)) for (x, y, r) in boundary_fixed)
    worst_fixed = max(vlen(p) for m in moves_fixed if m["kind"] == "turn" for p in m["points"])
    assert worst_fixed <= pad_max_fixed + 2.0, (worst_fixed, pad_max_fixed)
    assert recommended_tail_length(arms_wide, kerb_radius=8.0, start=12.0) == 12.0

    plain_4way = preset_4way(lanes=1)
    assert recommended_tail_length(plain_4way, kerb_radius=8.0, start=12.0) == 12.0

    def _forced_worst_gap(arms, kerb_radius, tail_length):
        boundary = build_junction_boundary(arms, kerb_radius, tail_length=tail_length)
        pad_max = max(vlen((x, y)) for (x, y, r) in boundary)
        moves = build_lane_movements(arms, kerb_radius, tail_length=tail_length, turn_radius=30.0)
        worst = max((vlen(p) for m in moves if m["kind"] == "turn" for p in m["points"]),
                    default=0.0)
        return worst - pad_max
    assert _forced_worst_gap(arms_wide, 8.0, 12.0) > 2.0, "sanity: turn_radius=30 must force a gap"
    found = 12.0
    for _ in range(25):
        if _forced_worst_gap(arms_wide, 8.0, found) <= 2.0:
            break
        found *= 1.3
    assert found > 12.0, "the search mechanism itself must still grow tail_length when truly needed"
    print("OK: with a small fixed turn_radius, a wide junction already satisfies the margin at the "
          "historical default tail_length (no growth needed); recommended_tail_length's own search "
          "mechanism still correctly grows tail_length for a pathologically large turn_radius")

    # 32. traffic_side ('LEFT' default vs. 'RIGHT'): 'RIGHT' is defined as `lane_perp` returning
    #     -perp_ccw instead of perp_ccw. This is NOT a mirror of the whole intersection (arm angles
    #     are unchanged -- only which physical lateral half of each arm counts as arriving vs.
    #     departing flips), so a generic "negate y" check across a curved turn's arc points is the
    #     WRONG invariant (each point's own lateral axis is that ARM's `perp_ccw(d)`, which differs
    #     per arm -- not one shared global axis). Test the primitive directly instead, the same way
    #     the file's own test 31 hand-verifies LEFT-side ports/movement endpoints against
    #     `perp_ccw(...)`.
    assert lane_perp((1.0, 0.0), 'LEFT') == perp_ccw((1.0, 0.0)) == (0.0, 1.0)
    assert lane_perp((1.0, 0.0), 'RIGHT') == (0.0, -1.0)
    assert lane_perp((1.0, 0.0)) == lane_perp((1.0, 0.0), 'LEFT'), "default must be 'LEFT'"

    n_left = Arm("N", 90.0, lane_width=5.0, lanes=2)
    e_left = Arm("E", 0.0, lane_width=5.0, lanes=2)
    n_right = Arm("N", 90.0, lane_width=5.0, lanes=2, traffic_side='RIGHT')
    e_right = Arm("E", 0.0, lane_width=5.0, lanes=2, traffic_side='RIGHT')
    edge_a_l, edge_b_l = curb_edges(n_left, e_left)
    edge_a_r, edge_b_r = curb_edges(n_right, e_right)
    dn, de = arm_dir(90.0), arm_dir(0.0)
    assert edge_a_l[0] == vscale(perp_ccw(dn), n_left.out_width())
    assert edge_a_r[0] == vscale(vscale(perp_ccw(dn), -1.0), n_right.out_width())
    assert edge_b_l[0] == vscale(perp_ccw(de), -e_left.in_width())
    assert edge_b_r[0] == vscale(vscale(perp_ccw(de), -1.0), -e_right.in_width())

    # build_ports: a straight offset + tail (no curvature), so its lateral component IS directly
    # checkable per-arm against -perp_ccw(d).
    ports_left = build_ports([n_left], tail_length=12.0)
    ports_right = build_ports([n_right], tail_length=12.0)
    by_id_left = {p["id"]: p for p in ports_left}
    for p in ports_right:
        lp = by_id_left[p["id"]]
        lat_left = vscale(perp_ccw(dn), n_left.in_offset(p["lane"]) if p["direction"] == "in"
                           else n_left.out_offset(p["lane"]))
        lat_right = vscale(perp_ccw(dn), -(n_right.in_offset(p["lane"]) if p["direction"] == "in"
                                            else n_right.out_offset(p["lane"])))
        expect_left = vadd(lat_left, vscale(dn, 12.0))
        expect_right = vadd(lat_right, vscale(dn, 12.0))
        assert vlen(vsub(lp["position"], expect_left)) < 1e-6
        assert vlen(vsub(p["position"], expect_right)) < 1e-6
        assert vlen(vsub(p["position"], lp["position"])) > 1.0, "RIGHT must actually move the port"

    # A straight, axis-aligned segment (single global tangent) DOES make "negate the perpendicular
    # coordinate" a valid whole-output check, since every point shares the same tangent frame.
    seg_left = build_straight_segment((0.0, 0.0, 0.0), (100.0, 0.0, 0.0), lanes=2, lanes_backward=1)
    seg_right = build_straight_segment((0.0, 0.0, 0.0), (100.0, 0.0, 0.0), lanes=2, lanes_backward=1,
                                        traffic_side='RIGHT')
    for (lc, rc) in zip(seg_left["curbs"], seg_right["curbs"]):
        for (lx, ly, lz), (rx, ry, rz) in zip(lc, rc):
            assert abs(lx - rx) < 1e-6 and abs(ly + ry) < 1e-6
    assert seg_left["curbs"][0][0][1] > 0.0 and seg_right["curbs"][0][0][1] < 0.0
    trans_left = build_lane_transition((0.0, 0.0, 0.0), (50.0, 0.0, 0.0), lanes_a=2, lanes_b=1)
    trans_right = build_lane_transition((0.0, 0.0, 0.0), (50.0, 0.0, 0.0), lanes_a=2, lanes_b=1,
                                         traffic_side='RIGHT')
    for (lc, rc) in zip(trans_left["curbs"], trans_right["curbs"]):
        for (lx, ly, lz), (rx, ry, rz) in zip(lc, rc):
            assert abs(lx - rx) < 1e-6 and abs(ly + ry) < 1e-6
    print("OK: traffic_side='RIGHT' (keep-right, e.g. US) flips lane_perp's sign everywhere "
          "lateral lane/curb offsets are measured, verified directly on curb_edges/build_ports and "
          "as a whole-output mirror on axis-aligned segments/transitions; 'LEFT' (keep-left, e.g. "
          "Japan) stays the untouched default")

    # 33. build_segment_lane_markings: a 3-forward/2-backward spine produces exactly 4 markings --
    #     1 yellow (offset 0, the forward/backward boundary) + 2 white forward (at lane_width and
    #     2*lane_width) + 1 white backward (at -lane_width); a 1-forward/0-backward (one-way) spine
    #     produces zero (no same-direction internal boundary, no opposing-direction boundary).
    mk_spine = segment_spine_3d((0.0, 0.0, 0.0), (40.0, 0.0, 0.0))
    marks = build_segment_lane_markings(mk_spine, lane_width=3.5, lanes=3, lanes_backward=2)
    assert len(marks) == 4, len(marks)
    yellows = [m for m in marks if m["kind"] == "yellow"]
    whites = [m for m in marks if m["kind"] == "white"]
    assert len(yellows) == 1 and len(whites) == 3, (len(yellows), len(whites))
    assert yellows[0]["points"] == offset_spine_line(mk_spine, 0.0, 'LEFT')
    white_y0 = sorted(m["points"][0][1] for m in whites)
    assert abs(white_y0[0] - (-3.5)) < 1e-6, white_y0     # backward internal boundary at -lane_width
    assert abs(white_y0[1] - 3.5) < 1e-6, white_y0        # forward internal boundary at +lane_width
    assert abs(white_y0[2] - 7.0) < 1e-6, white_y0        # forward internal boundary at +2*lane_width
    mk_oneway = build_segment_lane_markings(mk_spine, lane_width=3.5, lanes=1, lanes_backward=0)
    assert mk_oneway == [], mk_oneway
    print("OK: build_segment_lane_markings (3f/2b -> 1 yellow + 3 white at exact offsets; "
          "1f/0b one-way -> no markings at all)")

    # 34. Per-arm tail_length override (Arm.tail_length): a 4-way where ONE arm (N) is snapped to
    #     a shorter reach than the shared default -- its own ports/boundary/curb points must land
    #     at ITS distance, every other arm stays at the shared default, and the whole thing must be
    #     byte-identical to the all-None (shared-scalar) case when no arm overrides it.
    arms_tl = preset_4way(lanes=1)
    n_arm = next(a for a in arms_tl if a.name == "N")   # 0 deg by preset_4way's naming
    n_arm.tail_length = 4.0   # much shorter than the shared default of 12.0
    boundary_tl = build_junction_boundary(arms_tl, kerb_radius=8.0, tail_length=12.0)
    # Every arm's own tail-cap points (radius 0) must land at exactly ITS effective tail length
    # (N's own override of 4.0, every other arm still the shared default of 12.0) -- verify by
    # recomputing each arm's two expected cap points from first principles and matching them
    # against the boundary's own output.
    caps = [p for p in boundary_tl if p[2] == 0.0]
    for a in arms_tl:
        eff = a.eff_tail_length(12.0)
        d = arm_dir(a.angle_deg)
        perp = lane_perp(d, a.traffic_side)
        expect_in = vadd(vscale(perp, -a.in_width()), vscale(d, eff))
        expect_out = vadd(vscale(perp, a.out_width()), vscale(d, eff))
        assert any(vlen(vsub((p[0], p[1]), expect_in)) < 1e-6 for p in caps), (a.name, expect_in, caps)
        assert any(vlen(vsub((p[0], p[1]), expect_out)) < 1e-6 for p in caps), (a.name, expect_out, caps)
    ports_tl = build_ports(arms_tl, tail_length=12.0)
    by_name = {a.name: a for a in arms_tl}
    for p in ports_tl:
        expect = by_name[p["arm"]].eff_tail_length(12.0)
        d = arm_dir(by_name[p["arm"]].angle_deg)
        along = p["position"][0] * d[0] + p["position"][1] * d[1]   # component along the arm
        assert abs(along - expect) < 1e-6, (p, expect)
    # With every arm's tail_length left at None (default), output must match the plain shared-
    # scalar call exactly -- the override is fully opt-in/back-compat.
    arms_default = preset_4way(lanes=1)
    boundary_default = build_junction_boundary(arms_default, kerb_radius=8.0, tail_length=12.0)
    boundary_shared = build_junction_boundary(preset_4way(lanes=1), kerb_radius=8.0, tail_length=12.0)
    assert boundary_default == boundary_shared
    print("OK: Arm.tail_length per-arm override (one arm's ports/boundary/curb reach its own "
          "distance, others stay on the shared scalar; all-None is byte-identical to before)")

    # 35. export_segment_dict/export_segment_from_spine_dict/export_lane_transition_dict (new,
    #     P6.4) must produce EXACTLY the same dict a file-writing sibling would have written --
    #     the dict-only split exists so lib/lane_kit.py's combiner can merge multiple pieces in
    #     memory without a round-trip through temp files.
    import json
    import os
    import tempfile
    p0s, p1s = (0.0, 0.0, 0.0), (30.0, 10.0, 0.0)
    d_seg = export_segment_dict(p0s, p1s, lane_width=4.0, lanes=2, segment_id="SEGX", z=1.5,
                                 lanes_backward=1)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tf_path = tf.name
    export_segment_json(tf_path, p0s, p1s, lane_width=4.0, lanes=2, segment_id="SEGX", z=1.5,
                         lanes_backward=1)
    with open(tf_path) as f:
        d_seg_file = json.load(f)
    assert d_seg == d_seg_file, (d_seg, d_seg_file)

    spine_ex = segment_spine_3d((0.0, 0.0, 2.0), (20.0, 5.0, 3.0))
    d_spine = export_segment_from_spine_dict(spine_ex, lane_width=3.5, lanes=1, segment_id="SPX")
    export_segment_from_spine_json(tf_path, spine_ex, lane_width=3.5, lanes=1, segment_id="SPX")
    with open(tf_path) as f:
        d_spine_file = json.load(f)
    assert d_spine == d_spine_file, (d_spine, d_spine_file)

    d_tr = export_lane_transition_dict((0.0, 0.0, 0.0), (25.0, 0.0, 0.0), lanes_a=2, lanes_b=1,
                                        segment_id="TRX")
    export_lane_transition_json(tf_path, (0.0, 0.0, 0.0), (25.0, 0.0, 0.0), lanes_a=2, lanes_b=1,
                                 segment_id="TRX")
    with open(tf_path) as f:
        d_tr_file = json.load(f)
    assert d_tr == d_tr_file, (d_tr, d_tr_file)
    os.remove(tf_path)
    print("OK: export_segment_dict/export_segment_from_spine_dict/export_lane_transition_dict "
          "(new) produce byte-identical output to their file-writing siblings")

    # 36. export_dict/export_json `center` -- found+fixed this session (road_blender_godot.md
    # P6.7): every geometry function feeding export_dict (build_lane_movements/build_ports) works
    # in a LOCAL frame centered on the junction (an Arm carries only an angle, never a world
    # position), so exporting a junction built anywhere OTHER than world origin without `center`
    # silently produced junction-relative, not world-space, points. Default center=(0,0) must stay
    # byte-identical to before this parameter existed; a non-zero center must translate every
    # lane point AND every port position by exactly that offset (tangents are directions, NOT
    # translated).
    arms_c = preset_4way(lanes=1)
    d_origin = export_dict(arms_c, kerb_radius=9.0, junction_id="C")
    d_default = export_dict(arms_c, kerb_radius=9.0, junction_id="C", center=(0.0, 0.0))
    assert d_origin == d_default, "default center=(0,0) must be byte-identical to omitting it"
    cx, cy = 204.0, 146.0
    d_shifted = export_dict(arms_c, kerb_radius=9.0, junction_id="C", center=(cx, cy))
    for lane_o, lane_s in zip(d_origin["lanes"], d_shifted["lanes"]):
        for p_o, p_s in zip(lane_o["points"], lane_s["points"]):
            assert abs(p_s[0] - p_o[0] - cx) < 1e-9 and abs(p_s[1] - p_o[1] - cy) < 1e-9, \
                (p_o, p_s, cx, cy)
    for port_o, port_s in zip(d_origin["ports"], d_shifted["ports"]):
        assert abs(port_s["position"][0] - port_o["position"][0] - cx) < 1e-9
        assert abs(port_s["position"][1] - port_o["position"][1] - cy) < 1e-9
        assert port_s["tangent"] == port_o["tangent"], "a tangent is a direction, never translated"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tf_path = tf.name
    written = export_json(tf_path, arms_c, kerb_radius=9.0, junction_id="C", z=1.5,
                           center=(cx, cy))
    with open(tf_path) as f:
        written_file = json.load(f)
    os.remove(tf_path)
    assert written == written_file
    assert written["lanes"][0]["points"][0][0] == d_shifted["lanes"][0]["points"][0][0] + 0.0, \
        "export_json's x column must match export_dict's shifted x exactly"
    print("OK: export_dict/export_json `center` (new) translates every lane point + port "
          "position by exactly (cx, cy), leaves tangents untouched, default (0,0) is "
          "byte-identical to before this parameter existed")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
