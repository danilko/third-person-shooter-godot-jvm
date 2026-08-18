"""LINE SPLIT and LINE MERGE — one line becoming two, and two lines becoming one.

This is a TOPOLOGY primitive, not a ramp feature. Until now the addon could build exactly one
kind of road: a line that goes from A to B, optionally curving, optionally changing lane count.
Every place two roads met became an `ops_intersection` pad — stop lines, turn movements, traffic
arriving and waiting. That is correct for an at-grade crossing and wrong for everything that
happens at speed.

The missing concept is that **a line can divide**:

    SPLIT   one trunk (N lanes)  ->  two branches (a + b lanes)
    MERGE   two branches (a + b) ->  one trunk (N lanes)

An off-ramp is not a special case of road. It is a SPLIT whose minor branch happens to carry one
lane and happens to descend. Once split/merge exist as primitives, all of these are the same
piece with different numbers, and none of them needs its own tool:

    | shape                          | trunk | branches | note                              |
    |--------------------------------|------:|---------:|-----------------------------------|
    | motorway off-ramp              |     3 |    2 + 1 | aux lane tapered in first         |
    | motorway on-ramp               |     3 |    2 + 1 | MERGE, longer auxiliary lane      |
    | expressway JCT / Y-fork        |     4 |    2 + 2 | no aux lane — a pure split        |
    | carriageway around an island   |     2 |    1 + 1 | both branches rejoin later        |
    | lane drop into a slip road     |     2 |    1 + 1 | asymmetric, no widening           |

WHY IT CANNOT BE AN INTERSECTION, in one sentence: at a split the branches leave TANGENT to the
trunk and to each other, parting at a gore nose, so traffic never changes direction and never
stops — whereas an intersection pad exists precisely to make traffic turn and yield.

WHAT IS AUTHORED vs WHAT IS DERIVED. You author the trunk line and the branch lines. Everything
else is measured: where the gore falls (from the branches' own free ends), how wide the trunk
must become to carry `a + b` lanes, where the taper starts, and the lateral offset that puts each
branch's centreline in the right place so their edges meet at the nose. That is the same
"generator owns position, author owns type" split the rest of this pipeline uses.

GEOMETRY OF THE GORE. At the split station the trunk carries `a + b` lanes, so it spans
`(a+b)*w`. Branch A (the LEFT one, in keep-left travel) takes the left `a` lanes and branch B the
right `b`, so their centrelines sit at:

    A:  -(a+b)*w/2 + a*w/2 - nose/2          B:  +(a+b)*w/2 - b*w/2 + nose/2

measured along the trunk's left normal. That single expression is the whole split — it collapses
to the off-ramp offset when `b == 1`, and to a symmetric fork when `a == b`.

`line_split_pieces()` / `line_merge_pieces()` are PURE (no bpy), so all of it is verified
headless in `smoketest_line_split.py` without building a mesh.
"""
import math

import lane_profile as lp

import bpy

from .ops_intersection import RkaBuildError, parent_collection_of
from .ops_segment import _build_segment_from_points, _resolve_curve_object, \
    _sample_curve_world_points

# Metres. These are what make a split read as a split rather than a fork in a footpath.
DECEL_LENGTH = 90.0     # auxiliary lane held at full width before a SPLIT
ACCEL_LENGTH = 120.0    # after a MERGE — longer, joining traffic must reach trunk speed
TAPER_LENGTH = 60.0     # widening/narrowing the auxiliary lane
GORE_NOSE = 3.0         # painted nose where the two branch edges finally part
# Run over which that nose opens from nothing to its full width, immediately before the gore.
#
# THIS IS NOT COSMETIC, and getting it wrong is what made an exit read as two unrelated roads.
# The nose used to open on the SAME stations as the auxiliary lane, so as the exit lane widened
# in, a 3 m painted island widened in underneath it and held it 3 m clear of the carriageway for
# the whole deceleration run -- the lane never existed as part of the road you were driving on.
# A real deceleration lane is flush against the mainline for its full length; the gore only opens
# in the last stretch, where the two carriageways genuinely start to diverge. Measured on
# `IC_YAMATE_split_trunk_001`: GORE and A0 both ramp 0 -> full across stations 0.42 -> 0.65.
NOSE_LENGTH = 30.0


# --------------------------------------------------------------------------- pure geometry
def _plen(pts):
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:]))


def _stations(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.dist(a[:2], b[:2]))
    return out


def _at(pts, s):
    st = _stations(pts)
    if s <= 0:
        return tuple(pts[0])
    if s >= st[-1]:
        return tuple(pts[-1])
    for i in range(len(st) - 1):
        if st[i] <= s <= st[i + 1]:
            seg = st[i + 1] - st[i] or 1.0
            t = (s - st[i]) / seg
            return tuple(pts[i][d] + (pts[i + 1][d] - pts[i][d]) * t for d in range(3))
    return tuple(pts[-1])


def _with_stations(pts, base_pts, stations):
    """`pts` with an extra control point inserted at each arc-length station in `stations`.

    A profile station is a position ALONG THE ROAD, but the pavement's swept width and every lane
    centreline are only evaluated at CONTROL POINTS -- so a taper that begins 450 m along a trunk
    whose nearest points are at 400 m and 600 m actually begins at 400 m, and an auxiliary lane
    that only reaches full width in the final metres may not survive a single control point at
    all (measured: it exported as a one-point lane and was dropped entirely). Inserting the
    stations as real points is what makes the authored taper the built taper."""
    out = list(pts)
    for s in stations:
        if s <= 1e-6 or s >= _plen(base_pts) - 1e-6:
            continue
        p = _at(base_pts, s)
        if any(math.dist(p[:3], q[:3]) < 1e-3 for q in out):
            continue
        out.append(tuple(p))
    # Re-order by station along the base line so the spine stays monotone.
    return sorted(out, key=lambda q: _locate(base_pts, q)[0])


def _slice(pts, s0, s1):
    st = _stations(pts)
    out = [_at(pts, s0)]
    for p, s in zip(pts, st):
        if s0 < s < s1:
            out.append(tuple(p))
    out.append(_at(pts, s1))
    ded = [out[0]]
    for p in out[1:]:
        if math.dist(p[:2], ded[-1][:2]) > 1e-6:
            ded.append(p)
    return ded


def _tangent(pts, s, eps=1.0):
    a = _at(pts, max(0.0, s - eps))
    b = _at(pts, min(_plen(pts), s + eps))
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return dx / L, dy / L


def _left_normal(t):
    return (-t[1], t[0])


def gore_profile(lanes_a, lanes_b, lane_width, aux_a=0, nose=GORE_NOSE, opened=True,
                 aux_open=None):
    """The trunk's cross-section AT the gore: branch B's lanes, the painted nose, then branch A's.

    THIS REPLACES `branch_offsets`, which was the single expression the whole primitive rested on
    and was WRONG. It computed each branch's centreline in a CENTRED frame (`total/2 - lanes*w/2`),
    while `intersection_kit.build_segment_from_spine` places a one-way road's lanes EDGE-ANCHORED
    off the driving datum (`+0.5w, +1.5w, ...`, never negative). Measured: `branch_offsets(1, 3,
    3.5)` seeded branch B's lane 0 at -1.50 m, where the trunk has no lane at all -- every branch
    was laterally misplaced by ~3.25 m, geometry AND lane data. There is now no second formula:
    a branch's position is `lane_profile.slot_offset` of the slots it adopts, and this function
    is what says which slots those are.

    Layout, in `lane_profile`'s driving frame (`+s` = forward-lane side, so `+s` is the OUTSIDE
    of a keep-left carriageway -- the side an exit ramp departs to):

        [ B0 .. B{b-1} ] [ GORE ] [ A0 .. A{a-1} ]
          branch B         nose     branch A

    Branch B keeps the inner lanes, so its own datum coincides with the trunk's and THE MAINLINE
    DOES NOT MOVE SIDEWAYS AT AN EXIT -- which is both correct and the clearest sign the frame is
    right. Branch A sits outboard of the nose.

    `aux_a` is how many of A's lanes are AUXILIARY (added by the widening taper rather than
    carried the whole way); those are the OUTERMOST, which is what an auxiliary exit lane is.

    THE NOSE AND THE AUXILIARY LANE OPEN INDEPENDENTLY, and that is the whole point of having two
    flags rather than one `opened`:

        opened=False, aux_open=False   plain trunk       -- nose 0, aux 0
        opened=False, aux_open=True    deceleration run  -- nose 0, aux FULL (flush against the
                                                            mainline, which is what makes it a
                                                            lane of this road and not a parallel
                                                            strip of tarmac)
        opened=True,  aux_open=True    the gore itself   -- nose FULL, aux FULL

    `aux_open` defaults to `opened`, so the two-argument callers that predate this keep their old
    meaning. Because the slot IDS are identical at every combination, `ProfileSet` interpolation
    alone moves between them, which is the entire taper."""
    if aux_open is None:
        aux_open = opened
    slots = [lp.Slot("B%d" % i, lp.TRAVEL, lane_width, lp.FWD,
                     lp.MARK_DASH_W if i else lp.MARK_NONE) for i in range(lanes_b)]
    slots.append(lp.Slot("GORE", lp.SHOULDER, nose if opened else 0.0, lp.NONE,
                         lp.MARK_SOLID_W))
    for j in range(lanes_a):
        is_aux = j >= (lanes_a - aux_a)
        slots.append(lp.Slot("A%d" % j, lp.AUX if is_aux else lp.TRAVEL,
                             0.0 if (is_aux and not aux_open) else lane_width, lp.FWD,
                             lp.MARK_DASH_W))
    return lp.Profile(slots, lp.ANCHOR_DIVIDE)


def _ascending(marks, eps=1e-6):
    """`(stations, profiles)` from `[(t, profile), ...]`, keeping the LAST profile at any repeated
    parameter and clamping to `[0, 1]`.

    A station list must be strictly increasing for `lane_profile.stations_at` to interpolate, and
    the taper parameters genuinely can collide: a short trunk makes the nose station land exactly
    on the auxiliary-lane station, and a gore very near the start collapses `s_taper0` onto 0.
    Keeping the last one is what makes those degenerate cases behave like a step (the narrower
    stretch simply has no room to exist) instead of raising on the author."""
    out = []
    for t, p in marks:
        t = min(1.0, max(0.0, float(t)))
        if out and t - out[-1][0] <= eps:
            out[-1] = (out[-1][0], p)
        else:
            out.append((t, p))
    return [t for t, _p in out], [p for _t, p in out]


def branch_seed_offsets(profile, lanes_a, lanes_b):
    """Where each branch's own spine starts, given the trunk's gore profile.

    A one-way branch's spine is its lane block's INNER edge (that is where `ANCHOR_DIVIDE` puts
    `s = 0` for a road with no reverse lanes), NOT the block's centre -- getting that wrong is how
    the old centred-frame formula drifted. Read straight off `lane_profile`, never recomputed."""
    b_lo, _ = lp.slot_edges(profile, profile.index_of("B0")) if lanes_b else (0.0, 0.0)
    a_lo, _ = lp.slot_edges(profile, profile.index_of("A0")) if lanes_a else (0.0, 0.0)
    return a_lo, b_lo


def branch_profile(n_lanes, lane_width, prefix):
    """A branch's own cross-section: `n_lanes` one-way lanes, ids carried over from the trunk so a
    lane keeps its identity across the gore (`A0` on the trunk is `A0` on the ramp). That shared id
    is what Phase 3's explicit `next_routes` will key on instead of endpoint proximity."""
    return lp.ProfileSet([lp.Profile(
        [lp.Slot("%s%d" % (prefix, i), lp.TRAVEL, lane_width, lp.FWD,
                 lp.MARK_DASH_W if i else lp.MARK_NONE) for i in range(n_lanes)],
        lp.ANCHOR_DIVIDE)])


def _locate(trunk_pts, probe):
    """Station along the trunk nearest a point — how the gore is FOUND rather than typed in.

    PROJECTS ONTO THE SEGMENTS, never snaps to the nearest vertex. A trunk authored with few
    control points (a chamfered expressway ring is eight) puts most of its length between
    vertices, so a branch meeting it mid-edge would otherwise locate its gore hundreds of metres
    away — and a wrong station does not fail, it just builds strange-looking pavement."""
    acc, best, s_best = 0.0, float("inf"), 0.0
    for a, b in zip(trunk_pts, trunk_pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        seg = math.sqrt(L2) if L2 > 0 else 0.0
        if seg > 0.0:
            t = max(0.0, min(1.0, ((probe[0] - a[0]) * dx + (probe[1] - a[1]) * dy) / L2))
            d = math.hypot(probe[0] - (a[0] + dx * t), probe[1] - (a[1] + dy * t))
            if d < best:
                best, s_best = d, acc + seg * t
        acc += seg
    return s_best, best


def line_split_pieces(trunk_pts, branch_a_pts, branch_b_pts, lanes_a=1, lanes_b=2,
                      lane_width=3.5, trunk_lanes=None, decel=DECEL_LENGTH,
                      taper=TAPER_LENGTH, nose=GORE_NOSE):
    """One trunk line dividing into two branch lines.

    `branch_a_pts` is the LEFT branch and `branch_b_pts` the right, both authored FROM the gore
    outward (their first point is the end that meets the trunk). `trunk_lanes` defaults to
    `lanes_a + lanes_b`, which is a pure split with no widening; give it a smaller number and an
    auxiliary lane is tapered in beforehand — that is the motorway off-ramp case.

    Returns `{name: {"pts", "lanes", "lanes_end", "align"}}` plus a `_gore` record.
    """
    a, b = int(lanes_a), int(lanes_b)
    if a < 1 or b < 1:
        raise RkaBuildError("a split needs at least one lane on each branch (got %d and %d)"
                            % (a, b))
    if len(trunk_pts) < 2 or len(branch_a_pts) < 2 or len(branch_b_pts) < 2:
        raise RkaBuildError("trunk and both branches need at least 2 points each")
    total = a + b
    n_in = total if trunk_lanes is None else int(trunk_lanes)
    if n_in > total:
        raise RkaBuildError("trunk carries %d lanes but the branches only take %d — a split "
                            "cannot drop lanes, taper the trunk down first" % (n_in, total))

    trunk_len = _plen(trunk_pts)
    s_a, _ = _locate(trunk_pts, branch_a_pts[0])
    s_b, _ = _locate(trunk_pts, branch_b_pts[0])
    s_gore = (s_a + s_b) / 2.0

    widen = total - n_in                       # 0 for a pure split, 1 for an aux-lane ramp
    need = (decel + taper) if widen else 0.0
    if s_gore < need + 1.0:
        raise RkaBuildError(
            "gore sits %.0f m along the trunk but widening to %d lanes needs %.0f m of taper + "
            "auxiliary lane behind it — lengthen the trunk, or shorten decel/taper"
            % (s_gore, total, need))

    t = _tangent(trunk_pts, s_gore)
    n = _left_normal(t)
    g = _at(trunk_pts, s_gore)
    open_p = gore_profile(a, b, lane_width, aux_a=widen, nose=nose, opened=True)
    # The deceleration station: every lane at full width, nose still shut, so the exit lane runs
    # flush against the mainline until the carriageways genuinely part. See `NOSE_LENGTH`.
    flush_p = gore_profile(a, b, lane_width, aux_a=widen, nose=nose, opened=False, aux_open=True)
    shut_p = gore_profile(a, b, lane_width, aux_a=widen, nose=nose, opened=False)
    off_a, off_b = branch_seed_offsets(open_p, a, b)
    start_a = (g[0] + n[0] * off_a, g[1] + n[1] * off_a, g[2])
    start_b = (g[0] + n[0] * off_b, g[1] + n[1] * off_b, g[2])

    # ONE trunk piece, whatever its cross-section does along the way. The taper and the auxiliary
    # lane are STATIONS of its profile, not separate collections: `trunk_before`/`trunk_taper`/
    # `trunk_aux` existed only because a piece could carry a single lane COUNT, so every change of
    # count had to become a new piece -- which is why the interchange merges in
    # `island_v3_roads.blend` were "a separate mesh, no lane data, hard to adjust". Stations are
    # placed by ARC LENGTH along the trunk, so they land exactly where the taper physically is.
    trunk_pts_out = _slice(trunk_pts, 0.0, s_gore)
    # The nose opens over the last `NOSE_LENGTH` metres, never earlier than the point the aux lane
    # reaches full width (on a very short trunk those two collapse onto each other, which just
    # means the nose opens as soon as the lane is there -- still never before it).
    s_nose0 = max(0.0, s_gore - NOSE_LENGTH)
    if widen:
        s_taper0 = max(0.0, s_gore - decel - taper)
        s_aux0 = s_gore - decel
        s_nose0 = max(s_nose0, s_aux0)
        trunk_pts_out = _with_stations(trunk_pts_out, trunk_pts, (s_taper0, s_aux0, s_nose0))
        span = max(_plen(trunk_pts_out), 1e-6)
        marks = []
        if s_taper0 > 1.0:
            marks.append((0.0, shut_p))                # plain trunk
        marks.append((s_taper0 / span, shut_p))        # taper begins
        marks.append((s_aux0 / span, flush_p))         # aux at full width, still flush
        marks.append((s_nose0 / span, flush_p))        # held flush to here
        marks.append((1.0, open_p))                    # nose opens into the gore
    else:
        # A pure fork has no auxiliary lane to taper -- both branches carry full-width travel
        # lanes the whole way -- but the nose still must not be open from the start, or the two
        # carriageways are born already separated.
        trunk_pts_out = _with_stations(trunk_pts_out, trunk_pts, (s_nose0,))
        span = max(_plen(trunk_pts_out), 1e-6)
        marks = [(0.0, flush_p), (s_nose0 / span, flush_p), (1.0, open_p)]
    stations, profiles = _ascending(marks)
    pieces = {"trunk": dict(pts=trunk_pts_out, lanes=total, lanes_end=None, align='right',
                            profile_set=lp.ProfileSet(profiles, stations))}

    # Each branch starts EXACTLY on its gore offset, tangent to the trunk. Replacing the authored
    # first point (rather than prepending to it) is what keeps the nose free of a kink — the one
    # place a kink is both most visible and worst to drive.
    pieces["branch_a"] = dict(pts=[start_a] + [tuple(p) for p in branch_a_pts[1:]],
                              lanes=a, lanes_end=None, align='right',
                              profile_set=branch_profile(a, lane_width, "A"))
    pieces["branch_b"] = dict(pts=[start_b] + [tuple(p) for p in branch_b_pts[1:]],
                              lanes=b, lanes_end=None, align='right',
                              profile_set=branch_profile(b, lane_width, "B"))
    pieces["_gore"] = dict(position=g, station=s_gore, tangent=t, normal=n,
                           offset_a=off_a, offset_b=off_b, widened=bool(widen),
                           trunk_lanes=n_in, total_lanes=total, profile=open_p)
    return pieces


def ramp_split_pieces(mainline_pts, ramp_pts, lanes=2, ramp_lanes=1, lane_width=3.5,
                      decel=DECEL_LENGTH, taper=TAPER_LENGTH, nose=GORE_NOSE):
    """An OFF-RAMP as TWO pieces: one uncut mainline, and the ramp. The shape to reach for whenever
    one of the two outgoing lines is simply the road carrying on.

    WHY NOT `line_split_pieces`. That function is a symmetric primitive -- trunk divides into
    branch A and branch B -- and it is exactly right for a Y-fork, where neither outgoing line has
    a better claim to being "the road". At an off-ramp it is wrong in a way that costs real
    editing pain: branch B *is* the mainline continuing straight on, so the mainline acquires a
    seam, a new collection and a new identity at every single exit. Measured on
    `island_v3_roads.blend`: `IC_YAMATE_split_trunk_001` ends at exactly the point
    `IC_YAMATE_split_branch_b_001` begins, and the two are the same carriageway.

    Here the mainline is ONE piece from end to end. The exit is expressed the way the road
    actually behaves, as stations of that one piece's cross-section:

        plain              -> aux lane tapers in (flush)  -> nose opens -> [gore] -> plain again

    Past the gore the auxiliary lane and the nose are simply GONE -- the ramp has taken that
    pavement with it -- which is a genuine STEP in the cross-section, emitted as two stations a
    hair apart rather than a taper, because the nose IS the point of separation.

    This is also what godot-road-generator does with a `TRANSITION_ADD` / `TRANSITION_REM` lane on
    a continuous chain of RoadPoints, with the ramp as its own container joined at a point.

    `mainline_pts` runs THROUGH the exit (it is not cut at the gore); `ramp_pts` is authored FROM
    the gore outward, its first point being the end that meets the mainline -- same convention as
    `line_split_pieces`' branches. Returns `{"mainline", "ramp"}` plus a `_gore` record.
    """
    n_main, n_ramp = int(lanes), int(ramp_lanes)
    if n_main < 1 or n_ramp < 1:
        raise RkaBuildError("a ramp split needs at least one lane on the mainline and one on the "
                            "ramp (got %d and %d)" % (n_main, n_ramp))
    if len(mainline_pts) < 2 or len(ramp_pts) < 2:
        raise RkaBuildError("mainline and ramp need at least 2 points each")

    main_len = _plen(mainline_pts)
    s_gore, _ = _locate(mainline_pts, ramp_pts[0])
    need = decel + taper
    if s_gore < need + 1.0:
        raise RkaBuildError(
            "the gore sits %.0f m along the mainline but the exit needs %.0f m of taper + "
            "deceleration lane behind it — move the ramp further along, or shorten decel/taper"
            % (s_gore, need))
    if main_len - s_gore < 1.0:
        raise RkaBuildError(
            "the gore sits at the very end of the mainline (%.0f m of %.0f m) — for an exit at "
            "the end of a road, use line_split_pieces, which cuts the trunk there"
            % (s_gore, main_len))

    t = _tangent(mainline_pts, s_gore)
    n = _left_normal(t)
    g = _at(mainline_pts, s_gore)

    open_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=True)
    flush_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=False,
                           aux_open=True)
    shut_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=False)
    off_ramp, off_main = branch_seed_offsets(open_p, n_ramp, n_main)
    start_ramp = (g[0] + n[0] * off_ramp, g[1] + n[1] * off_ramp, g[2])

    s_taper0 = max(0.0, s_gore - decel - taper)
    s_aux0 = s_gore - decel
    s_nose0 = max(s_gore - NOSE_LENGTH, s_aux0)
    # The step: the cross-section reverts one centimetre past the gore. A ProfileSet interpolates
    # between stations, so "instantly" has to be spelt as a very short station gap -- shorter than
    # any control-point spacing, so nothing samples the middle of it.
    s_after = min(main_len, s_gore + 0.01)
    pts_out = _with_stations(list(mainline_pts), mainline_pts,
                             (s_taper0, s_aux0, s_nose0, s_gore, s_after))
    span = max(_plen(pts_out), 1e-6)
    marks = []
    if s_taper0 > 1.0:
        marks.append((0.0, shut_p))
    marks.append((s_taper0 / span, shut_p))     # taper begins
    marks.append((s_aux0 / span, flush_p))      # exit lane at full width, flush to the mainline
    marks.append((s_nose0 / span, flush_p))     # held flush
    marks.append((s_gore / span, open_p))       # nose fully open -- the branches part HERE
    marks.append((s_after / span, shut_p))      # ramp gone; mainline back to its own lanes
    marks.append((1.0, shut_p))
    stations, profiles = _ascending(marks)

    pieces = {
        "mainline": dict(pts=pts_out, lanes=n_main, lanes_end=None, align='right',
                         profile_set=lp.ProfileSet(profiles, stations)),
        "ramp": dict(pts=seed_ramp(ramp_pts, start_ramp, t, 'split'),
                     lanes=n_ramp, lanes_end=None, align='right',
                     profile_set=branch_profile(n_ramp, lane_width, "A")),
    }
    pieces["_gore"] = dict(position=g, station=s_gore, tangent=t, normal=n,
                           offset_a=off_ramp, offset_b=off_main, widened=True,
                           trunk_lanes=n_main, total_lanes=n_main + n_ramp, profile=open_p)
    return pieces


def ramp_merge_pieces(mainline_pts, ramp_pts, lanes=2, ramp_lanes=1, lane_width=3.5,
                      accel=ACCEL_LENGTH, taper=TAPER_LENGTH, nose=GORE_NOSE):
    """An ON-RAMP as TWO pieces -- the mirror of `ramp_split_pieces`, and the same argument for
    existing: the mainline is not cut where traffic joins it.

    `ramp_pts` is authored TOWARD the mainline (its LAST point meets the gore). The auxiliary lane
    runs longer than an exit's because joining traffic has to reach mainline speed before the lane
    is taken away."""
    n_main, n_ramp = int(lanes), int(ramp_lanes)
    if n_main < 1 or n_ramp < 1:
        raise RkaBuildError("an on-ramp needs at least one lane on the mainline and one on the "
                            "ramp (got %d and %d)" % (n_main, n_ramp))
    if len(mainline_pts) < 2 or len(ramp_pts) < 2:
        raise RkaBuildError("mainline and ramp need at least 2 points each")

    main_len = _plen(mainline_pts)
    s_gore, _ = _locate(mainline_pts, ramp_pts[-1])
    need = accel + taper
    if main_len - s_gore < need + 1.0:
        raise RkaBuildError(
            "the gore sits %.0f m from the end of the mainline but the merge needs %.0f m of "
            "acceleration lane + taper ahead of it — move the ramp back, or shorten accel/taper"
            % (main_len - s_gore, need))
    if s_gore < 1.0:
        raise RkaBuildError(
            "the gore sits at the very start of the mainline — for a merge at the start of a "
            "road, use line_merge_pieces, which begins the trunk there")

    t = _tangent(mainline_pts, s_gore)
    n = _left_normal(t)
    g = _at(mainline_pts, s_gore)

    open_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=True)
    flush_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=False,
                           aux_open=True)
    shut_p = gore_profile(n_ramp, n_main, lane_width, aux_a=n_ramp, nose=nose, opened=False)
    off_ramp, off_main = branch_seed_offsets(open_p, n_ramp, n_main)
    end_ramp = (g[0] + n[0] * off_ramp, g[1] + n[1] * off_ramp, g[2])

    s_before = max(0.0, s_gore - 0.01)          # the step, mirrored -- see ramp_split_pieces
    s_nose1 = min(s_gore + NOSE_LENGTH, s_gore + accel)
    s_aux1 = s_gore + accel
    s_taper1 = min(main_len, s_aux1 + taper)
    pts_out = _with_stations(list(mainline_pts), mainline_pts,
                             (s_before, s_gore, s_nose1, s_aux1, s_taper1))
    span = max(_plen(pts_out), 1e-6)
    marks = [(0.0, shut_p),
             (s_before / span, shut_p),         # plain mainline right up to the gore
             (s_gore / span, open_p),           # nose fully open -- traffic joins HERE
             (s_nose1 / span, flush_p),         # nose closed; joining lane now flush
             (s_aux1 / span, flush_p),          # held for the acceleration run
             (s_taper1 / span, shut_p)]         # auxiliary lane tapered away
    if main_len - s_taper1 > 1.0:
        marks.append((1.0, shut_p))
    stations, profiles = _ascending(marks)

    pieces = {
        "mainline": dict(pts=pts_out, lanes=n_main, lanes_end=None, align='right',
                         profile_set=lp.ProfileSet(profiles, stations)),
        "ramp": dict(pts=seed_ramp(ramp_pts, end_ramp, t, 'merge'),
                     lanes=n_ramp, lanes_end=None, align='right',
                     profile_set=branch_profile(n_ramp, lane_width, "A")),
    }
    pieces["_gore"] = dict(position=g, station=s_gore, tangent=t, normal=n,
                           offset_a=off_ramp, offset_b=off_main, narrowed=True,
                           trunk_lanes=n_main, total_lanes=n_main + n_ramp, profile=open_p)
    return pieces


#: Metres of ramp that run PARALLEL to the mainline immediately at the gore, before the ramp is
#: allowed to turn away. A gore is a division, not a corner -- see the module docstring -- so the
#: first thing a ramp does is run alongside.
RAMP_LEAD = 25.0

#: Metres over which the gore seed's rigid slide is released, so the touchdown stays exactly where
#: it was authored. Everything before it is translated bodily -- see `seed_ramp` for the
#: measurements that set this shape.
RAMP_SEED_BLEND = 150.0

#: Metres of ramp at the touchdown that the release window must stay CLEAR of. That stretch
#: belongs to whoever lands the ramp on its target road (`island_v3_to_roadkit.land_ramp_on_kerb`,
#: whose own `BLEND` this must be at least as large as). Two smoothsteps in the same 120 m stack,
#: and the sum is what matters to a driver: with the windows overlapping, IC_RINKAI_E came out at
#: 47.5 m against a planned 61.7 m and IC_RINKAI_W at 54.2 m against 74.2 m -- both still under
#: the 59.1 m a 45 km/h ramp needs, for no reason other than the two corrections being applied on
#: top of each other. Separated, each correction is a small one in a stretch of road that is
#: nobody else's.
RAMP_SEED_TAIL_CLEAR = 120.0


def seed_ramp(ramp_pts, seed, tangent, kind, lead=RAMP_LEAD):
    """Re-anchor an authored ramp onto its gore SEED, leaving (or arriving) tangent to the
    mainline.

    WHY REPLACING THE END POINT IS NOT ENOUGH. The authored ramp starts on the LOOP's own
    centreline, while the seed sits on the carriageway's auxiliary-lane slot -- a different line,
    tens of metres away once the carriageway offset and the slot offset are both counted. Simply
    swapping the first point for the seed therefore leaves a long first segment aimed at the
    SECOND authored point, which is only a dozen metres from where the first one used to be.
    Measured on the built pieces: a 47.9 m opening segment followed by a 12.1 m one, with a -55.3
    degree kink between them, where every other step turns by single digits. That kink at the deck
    end is the fold -- the ramp lurches sideways onto its slot and then snaps back onto its
    authored line.

    So the seed gets a LEAD: a second point one `lead` along the mainline tangent, and every
    authored point that falls behind it is dropped rather than reached backwards for. The ramp
    then leaves the gore parallel to the traffic it is leaving, which is both what a real gore
    looks like and what makes the exit driveable.

    `kind` is `'split'` (the ramp departs; seed at the START) or `'merge'` (it arrives; seed at
    the END)."""
    pts = [tuple(p) for p in ramp_pts]
    if len(pts) < 2:
        return pts
    # The authored ramp ALREADY leaves tangent -- `island_v3_plan.ramp_polyline` departs along
    # `loop_tangent(gore)` by construction. Nothing is wrong with its shape; only its END POINT is
    # on the wrong line. So SLIDE it onto the seed rather than rebuilding its start: that keeps the
    # authored alignment, and with it the grade and radius `fit_ramp` already proved.
    #
    # (Trimming the first stretch and re-leading along the tangent was tried and is wrong: a ramp
    # turns away from the mainline, so its points stop advancing along the tangent almost at once
    # and a "keep only what is ahead" test throws the whole ramp away -- measured, six of eight
    # ramps collapsed to a bare 25 m stub.)
    st = _stations(pts)
    total = st[-1] or 1.0
    anchor = 0 if kind == 'split' else -1
    dx = seed[0] - pts[anchor][0]
    dy = seed[1] - pts[anchor][1]
    dz = seed[2] - pts[anchor][2]
    # THE SLIDE IS A RIGID TRANSLATION over almost the whole ramp, released only in the last
    # `RAMP_SEED_BLEND` metres so the touchdown still lands exactly where it was authored (on its
    # arterial).
    #
    # It used to decay LINEARLY across the entire length, with the comment "over a 200 m ramp a
    # ~15 m shift is a fraction of a degree of extra curvature". That reasoning is wrong, and
    # measurably so: a weight that changes along the curve is a SHEAR, not a translation, and a
    # shear applied across a curving path rescales its radius. Measured on the eight authored
    # ramps against `road_geometry.min_radius_along` (min of the 25 m and 12 m windows, the same
    # pair `island_v3_plan.ramp_radius` uses), for a 15 m seed offset:
    #
    #       ramp             authored   linear decay   this (bounded)
    #       IC_RINKAI_W        74.2 m       27.5 m         74.2 m
    #       IC_PORT            48.4 m       23.5 m         48.4 m
    #       IC_RINKAI_E        61.7 m       39.9 m         76.7 m
    #
    # -- so the shape `fit_ramp` proved was being thrown away by the very step that claimed to
    # preserve it (its own docstring above: "that keeps the authored alignment, and with it the
    # grade and radius fit_ramp already proved"). At a 22 m offset the linear decay took
    # IC_PORT down to 18.1 m, a 65 km/h ramp reduced to a car-park corner.
    #
    # A translation cannot change curvature at all, so the middle of the ramp -- where the
    # governing radius lives -- now comes through untouched. The release window is a SMOOTHSTEP,
    # not linear, so it adds no step in curvature at either of its ends; over 150 m it costs at
    # worst ~35 m of radius on the flattest ramps and nothing on the tight ones (measured above),
    # and it is the same bounded-correction shape `island_v3_to_roadkit.land_ramp_on_kerb` uses
    # at the touchdown for the same reason.
    blend, clear = RAMP_SEED_BLEND, RAMP_SEED_TAIL_CLEAR
    room = total * 0.9
    if blend + clear > room:                          # a short ramp: shrink both, keep the ratio
        k = room / (blend + clear)
        blend, clear = blend * k, clear * k
    out = []
    for p, s in zip(pts, st):
        far = (total - s) if kind == 'split' else s
        t = 0.0 if blend <= 0 else max(0.0, min(1.0, (far - clear) / blend))
        w = t * t * (3.0 - 2.0 * t)
        out.append((p[0] + dx * w, p[1] + dy * w, p[2] + dz * w))
    out[anchor] = tuple(seed)
    return out


def _knot_at(seq, s):
    """One interchange's `(gore_width, ramp_width)` at arc-length `s`, linearly between its knots
    and ZERO outside them -- so an interchange contributes nothing to the stretches of carriageway
    it is not part of, without having to assert anything about them."""
    if not seq or s <= seq[0][0] or s >= seq[-1][0]:
        return (0.0, 0.0)
    for (s0, w0), (s1, w1) in zip(seq, seq[1:]):
        if s0 <= s <= s1:
            t = 0.0 if s1 <= s0 else (s - s0) / (s1 - s0)
            return (w0[0] + (w1[0] - w0[0]) * t, w0[1] + (w1[1] - w0[1]) * t)
    return (0.0, 0.0)


def two_way_carriageway_profile(lanes, lane_width, sided_ics, widths=None, nose=GORE_NOSE,
                                median=1.2):
    """A whole expressway cross-section carrying BOTH directions, with each direction's own
    exits and entries as auxiliary slots outboard of its own travel lanes.

    THIS IS THE SHAPE THE ROAD ACTUALLY HAS (`ROAD_KIT_REDESIGN.md` 2.3). Splitting the ring into
    two one-way carriageways was a workaround for the scalar model -- two directions whose lane
    counts vary independently could not live in one piece. A `ProfileSet` removes that limit, and
    the split cost real correctness: with every exit put on one carriageway and every entry on the
    other, the reverse carriageway had entrances and no exits, so traffic could drive onto it and
    never leave (defect 13, found by the connectivity gate).

    Slot order runs most-negative to most-positive `s`, with `ANCHOR_DIVIDE` putting `s = 0` on the
    median -- the real driving datum, which is also why the one-way anchor argument stops mattering
    here:

        [REV aux + gore]  [R{n-1}..R0]  [MED]  [F0..F{n-1}]  [FWD gore + aux]
              outboard of the reverse lanes            outboard of the forward lanes

    `sided_ics` is `[(ramp_id, 'FWD'|'REV'), ...]`; every interchange appears at EVERY station at
    zero width except its own, for the ordering reason `carriageway_profile` documents."""
    widths = widths or {}
    rev = [r for r, s in sided_ics if s == lp.REV]
    fwd = [r for r, s in sided_ics if s == lp.FWD]
    slots = []
    for rid in rev:
        g, a = widths.get(rid, (0.0, 0.0))
        # Outermost first: the auxiliary lane's own low edge is the road edge, so it carries no
        # line; the gore's low edge is the boundary with it.
        slots.append(lp.Slot("%s_A0" % rid, lp.AUX, a, lp.REV, lp.MARK_NONE))
        slots.append(lp.Slot("%s_GORE" % rid, lp.SHOULDER, g, lp.NONE, lp.MARK_SOLID_W))
    for k in range(lanes - 1, -1, -1):
        slots.append(lp.Slot("R%d" % k, lp.TRAVEL, lane_width, lp.REV,
                             lp.MARK_NONE if k == lanes - 1 else lp.MARK_DASH_W))
    # UNPAINTED, for the reason `lane_profile.profile_from_scalars` records at its own MED slot: a
    # median with real width IS the separator, so a solid yellow on its low edge draws a line
    # through (or under) the physical island. The scalar path had this fixed and the carriageway
    # profile reintroduced it -- the same defect in a second place, which is what having two
    # descriptions of one cross-section costs.
    slots.append(lp.Slot("MED", lp.MEDIAN, median, lp.NONE, lp.MARK_NONE))
    for k in range(lanes):
        slots.append(lp.Slot("F%d" % k, lp.TRAVEL, lane_width, lp.FWD,
                             lp.MARK_NONE if k == 0 else lp.MARK_DASH_W))
    for rid in fwd:
        g, a = widths.get(rid, (0.0, 0.0))
        slots.append(lp.Slot("%s_GORE" % rid, lp.SHOULDER, g, lp.NONE, lp.MARK_SOLID_W))
        slots.append(lp.Slot("%s_A0" % rid, lp.AUX, a, lp.FWD, lp.MARK_DASH_W))
    return lp.Profile(slots, lp.ANCHOR_DIVIDE)


def carriageway_profile(lanes, lane_width, ramp_ids, widths=None, nose=GORE_NOSE):
    """One cross-section for a WHOLE carriageway: the mainline lanes, then every interchange's
    gore + ramp slot, in a FIXED order, most of them at zero width.

    The fixed order is the load-bearing part. A carriageway's profile is sampled at dozens of
    stations along several kilometres, and `lane_profile._merge_order` places a slot that appears
    in only some stations by its neighbours -- which is exactly the situation six independent
    auxiliary lanes would put it in, all wanting the same lateral position just outboard of the
    mainline. Listing every interchange's slots at EVERY station, at zero width where that
    interchange is not happening, removes the ambiguity entirely: the order is authored once here
    and never inferred. Zero-width slots contribute nothing to `slot_offset`, so an auxiliary lane
    opening at the fifth interchange still sits immediately outboard of the mainline, not five
    dead slots away from it.

    `widths` is `{ramp_id: (gore_width, ramp_width)}` for whichever interchange is currently open;
    anything absent is zero."""
    widths = widths or {}
    slots = [lp.Slot("B%d" % i, lp.TRAVEL, lane_width, lp.FWD,
                     lp.MARK_DASH_W if i else lp.MARK_NONE) for i in range(lanes)]
    for rid in ramp_ids:
        g, a = widths.get(rid, (0.0, 0.0))
        slots.append(lp.Slot("%s_GORE" % rid, lp.SHOULDER, g, lp.NONE, lp.MARK_SOLID_W))
        slots.append(lp.Slot("%s_A0" % rid, lp.AUX, a, lp.FWD, lp.MARK_DASH_W))
    return lp.Profile(slots, lp.ANCHOR_DIVIDE)


def carriageway_pieces(mainline_pts, interchanges, lanes=2, lane_width=3.5,
                       decel=DECEL_LENGTH, accel=ACCEL_LENGTH, taper=TAPER_LENGTH,
                       nose=GORE_NOSE):
    """A WHOLE expressway carriageway as ONE piece, with every interchange on it expressed as
    stations of that one piece's cross-section -- plus one piece per ramp.

    WHY THIS REPLACES PER-INTERCHANGE PIECES. `ramp_split_pieces` already stopped cutting the
    mainline AT a gore, but each interchange still produced its own mainline piece, so a
    carriageway came out as (interchanges + gaps) separate roads: measured on `LOOP_A`, a 3,278 m
    ring with ZERO crossing cuts -- nothing about the road divides it -- built as 12 pieces purely
    because six interchanges each reserved a window. The lane count changing was the only reason a
    new piece was ever needed, and a `ProfileSet` removes that reason.

    Being one piece is not only tidier, it is what makes two other things possible:

      * ONE SPINE. Support, markings and the road surface can all derive from the same control
        points, so dragging the carriageway moves its piers with it. With twelve spines per
        carriageway there was no single spine for a continuous pier line to share, which is why
        support had to become an independent object.
      * ONE CONTINUOUS UNDERSTRUCTURE. `pier_stations` counts from the start of whatever it is
        given, so twelve pieces meant twelve independent bent sequences and a spacing that reset
        at every seam.

    `interchanges` is `[(ramp_id, ramp_pts, kind), ...]` with `kind` in `{'split', 'merge'}` --
    an exit and an entry respectively. Ramp points follow the same convention as elsewhere: a
    split's ramp is authored FROM the gore outward, a merge's TOWARD it.

    Returns `{"mainline": spec, "<ramp_id>": spec, ...}` plus `_gores`.
    """
    n_main = int(lanes)
    if n_main < 1:
        raise RkaBuildError("a carriageway needs at least one lane (got %d)" % n_main)
    if len(mainline_pts) < 2:
        raise RkaBuildError("the carriageway needs at least 2 points")

    base = list(mainline_pts)
    total = _plen(base)
    ramp_ids = [rid for rid, _pts, _k in interchanges]

    def prof(widths=None):
        return carriageway_profile(n_main, lane_width, ramp_ids, widths, nose)

    plain = prof()
    knots, gores, ramp_specs = {}, {}, {}

    for rid, ramp_pts, kind in interchanges:
        if len(ramp_pts) < 2:
            raise RkaBuildError("ramp %s needs at least 2 points" % rid)
        probe = ramp_pts[0] if kind == 'split' else ramp_pts[-1]
        s_gore, _d = _locate(base, probe)
        shut, flush, open_ = (0.0, 0.0), (0.0, lane_width), (nose, lane_width)

        if kind == 'split':
            s_taper0 = s_gore - decel - taper
            s_aux0 = s_gore - decel
            s_nose0 = max(s_gore - NOSE_LENGTH, s_aux0)
            if s_taper0 < 1.0:
                raise RkaBuildError(
                    "%s: the gore sits %.0f m along the carriageway but its exit needs %.0f m of "
                    "taper + deceleration lane behind it" % (rid, s_gore, decel + taper))
            seq = [(s_taper0, shut), (s_aux0, flush), (s_nose0, flush),
                   (s_gore, open_), (min(total, s_gore + 0.01), shut)]
        else:
            s_nose1 = min(s_gore + NOSE_LENGTH, s_gore + accel)
            s_aux1 = s_gore + accel
            s_taper1 = s_aux1 + taper
            if s_taper1 > total - 1.0:
                raise RkaBuildError(
                    "%s: the gore sits %.0f m from the carriageway end but its entry needs %.0f m "
                    "of acceleration lane + taper ahead of it"
                    % (rid, total - s_gore, accel + taper))
            seq = [(max(0.0, s_gore - 0.01), shut), (s_gore, open_), (s_nose1, flush),
                   (s_aux1, flush), (s_taper1, shut)]

        knots[rid] = seq

        # The ramp seeds on its OWN slot's inner edge, read off the open profile -- never a second
        # formula. `slot_edges` of `<rid>_A0`, exactly as `branch_seed_offsets` does for a split.
        op = prof({rid: open_})
        a_lo, _hi = lp.slot_edges(op, op.index_of("%s_A0" % rid))
        t = _tangent(base, s_gore)
        n = _left_normal(t)
        g = _at(base, s_gore)
        seed = (g[0] + n[0] * a_lo, g[1] + n[1] * a_lo, g[2])
        pts = seed_ramp(ramp_pts, seed, t, kind)
        ramp_specs[rid] = dict(pts=pts, lanes=1, lanes_end=None, align='right',
                               profile_set=branch_profile(1, lane_width, "A"))
        gores[rid] = dict(position=g, station=s_gore, tangent=t, normal=n, kind=kind,
                          offset_a=a_lo, profile=op)

    # EVERY interchange is evaluated at EVERY station, rather than each one emitting a "plain"
    # profile for the stretches it does not care about. Those plain marks assert something about
    # the WHOLE cross-section, so two interchanges whose approaches overlap would each keep
    # closing the other's auxiliary lane -- and they genuinely do overlap here (`JCT_AIRPORT`
    # begins 24 m before its neighbour's approach ends). Composing instead means an overlap simply
    # carries both lanes at once, which is also what the road does.
    def widths_at(s):
        return {rid: _knot_at(seq, s) for rid, seq in knots.items()}

    stations_to_insert = sorted(s for seq in knots.values() for s, _w in seq)
    pts_out = _with_stations(base, base, stations_to_insert)
    span = max(_plen(pts_out), 1e-6)
    all_s = sorted(set([0.0, total] + stations_to_insert))
    stations, profiles = _ascending([(s / span, prof(widths_at(s))) for s in all_s])

    pieces = {"mainline": dict(pts=pts_out, lanes=n_main, lanes_end=None, align='right',
                               profile_set=lp.ProfileSet(profiles, stations))}
    pieces.update(ramp_specs)
    pieces["_gores"] = gores
    return pieces


def two_way_carriageway_pieces(mainline_pts, interchanges, lanes=2, lane_width=3.5,
                               median=1.2, decel=DECEL_LENGTH, accel=ACCEL_LENGTH,
                               taper=TAPER_LENGTH, nose=GORE_NOSE):
    """The whole expressway as ONE two-direction piece, plus one piece per ramp.

    The two-direction counterpart of `carriageway_pieces` -- see `two_way_carriageway_profile` for
    the cross-section and why the one-way split is retired.

    `interchanges` is `[(ramp_id, ramp_pts, kind, side), ...]` with `kind` in `{'split','merge'}`
    (an exit / an entry) and `side` in `{lp.FWD, lp.REV}` (which direction it serves). A direction
    with entries and no exits is a dead end, so both must be represented across the set; that is an
    authoring decision and lives in the layout source, not here.

    SIDE DECIDES SIGN, everywhere. A REV interchange's gore station is located the same way, but
    its auxiliary lane sits on the negative-`s` side and its ramp seeds off the negative normal --
    so the one thing that flips is which lateral edge of the aux slot the ramp is anchored to.
    `lane_profile.slot_edges` answers that directly (the FAR edge on the reverse side, the NEAR
    edge on the forward side), which keeps it a lookup rather than a second sign convention."""
    n = int(lanes)
    if n < 1:
        raise RkaBuildError("a carriageway needs at least one lane per direction (got %d)" % n)
    if len(mainline_pts) < 2:
        raise RkaBuildError("the carriageway needs at least 2 points")

    base = list(mainline_pts)
    total = _plen(base)
    sided = [(rid, side) for rid, _p, _k, side in interchanges]

    def prof(widths=None):
        return two_way_carriageway_profile(n, lane_width, sided, widths, nose, median)

    knots, gores, ramp_specs = {}, {}, {}
    for rid, ramp_pts, kind, side in interchanges:
        if len(ramp_pts) < 2:
            raise RkaBuildError("ramp %s needs at least 2 points" % rid)
        probe = ramp_pts[0] if kind == 'split' else ramp_pts[-1]
        s_gore, _d = _locate(base, probe)
        shut, flush, open_ = (0.0, 0.0), (0.0, lane_width), (nose, lane_width)

        if kind == 'split':
            s_taper0, s_aux0 = s_gore - decel - taper, s_gore - decel
            s_nose0 = max(s_gore - NOSE_LENGTH, s_aux0)
            if s_taper0 < 1.0:
                raise RkaBuildError(
                    "%s: the gore sits %.0f m along the carriageway but its exit needs %.0f m of "
                    "taper + deceleration lane behind it" % (rid, s_gore, decel + taper))
            seq = [(s_taper0, shut), (s_aux0, flush), (s_nose0, flush),
                   (s_gore, open_), (min(total, s_gore + 0.01), shut)]
        else:
            s_nose1 = min(s_gore + NOSE_LENGTH, s_gore + accel)
            s_aux1 = s_gore + accel
            s_taper1 = s_aux1 + taper
            if s_taper1 > total - 1.0:
                raise RkaBuildError(
                    "%s: the gore sits %.0f m from the carriageway end but its entry needs %.0f m "
                    "of acceleration lane + taper ahead of it"
                    % (rid, total - s_gore, accel + taper))
            seq = [(max(0.0, s_gore - 0.01), shut), (s_gore, open_), (s_nose1, flush),
                   (s_aux1, flush), (s_taper1, shut)]
        knots[rid] = seq

        op = prof({rid: open_})
        lo, hi = lp.slot_edges(op, op.index_of("%s_A0" % rid))
        # The ramp anchors on the edge of its slot NEAREST the carriageway it leaves: the far
        # (positive) edge on the reverse side, the near edge on the forward side.
        a_edge = hi if side == lp.REV else lo
        t = _tangent(base, s_gore)
        nrm = _left_normal(t)
        g = _at(base, s_gore)
        seed = (g[0] + nrm[0] * a_edge, g[1] + nrm[1] * a_edge, g[2])
        ramp_specs[rid] = dict(pts=seed_ramp(ramp_pts, seed, t, kind), lanes=1, lanes_end=None,
                               align='right', profile_set=branch_profile(1, lane_width, "A"))
        gores[rid] = dict(position=g, station=s_gore, tangent=t, normal=nrm, kind=kind,
                          side=side, offset_a=a_edge, profile=op)

    def widths_at(s):
        return {rid: _knot_at(seq, s) for rid, seq in knots.items()}

    stations_to_insert = sorted(s for seq in knots.values() for s, _w in seq)
    pts_out = _with_stations(base, base, stations_to_insert)
    span = max(_plen(pts_out), 1e-6)
    all_s = sorted(set([0.0, total] + stations_to_insert))
    stations, profiles = _ascending([(s / span, prof(widths_at(s))) for s in all_s])

    pieces = {"mainline": dict(pts=pts_out, lanes=n, lanes_end=None, align='right',
                               profile_set=lp.ProfileSet(profiles, stations))}
    pieces.update(ramp_specs)
    pieces["_gores"] = gores
    return pieces


# ------------------------------------------------------------------- carriageway AS SEGMENTS
#
# WHY THIS EXISTS ALONGSIDE `two_way_carriageway_pieces`. That function answers "one road, one
# piece": a 3.3 km expressway as a single carrier whose ProfileSet carries all eight interchanges
# as stations. It is correct, and it is the ONE thing in the network that is not shaped like
# everything else in it -- every other road on the island is a chain of ordinary SEGMENTS meeting
# at authored joints, trimmed to INTERSECTION arms. Two shapes means two of everything: two ways
# to attach support, two ways a joint is authored, two answers to "what do I select to edit this
# stretch", and a 3.3 km spine you cannot drag a control point on without moving a road four
# interchanges away.
#
# So the expressway is chunked here into the same two primitives the rest of the map is made of:
#
#     plain deck chunk    2+2, constant cross-section        <- an ordinary segment
#     interchange chunk   2+2 PLUS one auxiliary lane on the side that needs it, tapered in
#                         at one end and out at the other    <- an ordinary segment with an
#                                                               extra lane on the required side
#     ramp                one lane, its own piece            <- unchanged
#
# Nothing new is introduced: an interchange chunk is a segment whose ProfileSet opens one AUX slot,
# which is the same mechanism a turn-lane widening on an arterial already uses. What changes is
# that the extra lane lives on ITS OWN piece with plain cross-sections at both ends, so the joints
# either side of it are ordinary segment<->segment joints and `lane_export.emit_joint_links`
# measures them edge-to-edge like any other seam.

#: Metres over which the painted gore island opens (entry) or closes (exit) OUTSIDE the gore, so
#: an interchange chunk reaches its neighbours with the PLAIN cross-section.
#:
#: This is what makes chunking possible at all. In the one-piece model the auxiliary lane and its
#: gore both slam shut 1 cm past the gore station -- harmless in the middle of a 3.3 km piece, and
#: unusable as a piece END: the last two spine points would sit 1 cm apart, and an end tangent
#: taken from them (which is what every joint measurement, every port arrow and the traffic
#: overlay read) measures the taper instead of the road. Running the nose out over `NOSE_LENGTH`
#: -- the same figure it opens over on the other side -- gives the chunk a plain, full-length
#: final span to hand over on.
#:
#: The AUXILIARY LANE still closes abruptly at the gore, and deliberately: past the gore that lane
#: IS the ramp, so tapering it out would export a phantom lane running alongside the ramp for
#: 30 m. Only the (undrivable) gore shoulder runs out.
GORE_RUNOUT = NOSE_LENGTH

#: A deck chunk shorter than this is not worth being its own piece -- the interchange windows
#: either side of the gap are merged into one chunk instead. (`island_v3_to_roadkit.MIN_CHUNK`
#: is the same figure for ordinary roads; it is passed in rather than imported, since this module
#: has no business knowing about the island.)
MIN_DECK_CHUNK = 24.0


def _interchange_window(s_gore, kind, decel, accel, taper, runout):
    """`(start, end)` stations of the stretch of carriageway ONE interchange needs to itself --
    everything from where its auxiliary lane starts opening to where the gore island has run out.

    An exit needs its room BEHIND the gore (decelerate, then leave); an entry needs it AHEAD
    (arrive, then accelerate to trunk speed). The `runout` on the far side is the short stretch
    where only the painted island is left -- see `GORE_RUNOUT`."""
    if kind == 'split':
        return (s_gore - decel - taper, s_gore + runout)
    return (s_gore - runout, s_gore + accel + taper)


def _interchange_knots(s_gore, kind, lane_width, nose, decel, accel, taper, runout):
    """`[(station, (gore_width, aux_width)), ...]` for one interchange, in ascending station order.

    Identical to the sequence `two_way_carriageway_pieces` uses, with the far-side `runout` added
    so the sequence starts and ends on the PLAIN cross-section (both widths zero)."""
    shut, flush, open_ = (0.0, 0.0), (0.0, lane_width), (nose, lane_width)
    nose_only = (nose, 0.0)
    if kind == 'split':
        s_aux0 = s_gore - decel
        return [(s_gore - decel - taper, shut),
                (s_aux0, flush),
                (max(s_gore - NOSE_LENGTH, s_aux0), flush),
                (s_gore, open_),
                # The aux lane leaves AS the ramp: shut in 1 cm, then only the island runs out.
                (s_gore + 0.01, nose_only),
                (s_gore + runout, shut)]
    s_nose1 = min(s_gore + NOSE_LENGTH, s_gore + accel)
    s_aux1 = s_gore + accel
    return [(s_gore - runout, shut),
            (s_gore - 0.01, nose_only),
            (s_gore, open_),
            (s_nose1, flush),
            (s_aux1, flush),
            (s_aux1 + taper, shut)]


def _merge_windows(items, min_gap):
    """Group interchanges whose windows overlap, or are separated by less than `min_gap`, into one
    chunk. Returns `[(start, end, [item, ...]), ...]` in ascending station order.

    OVERLAPS ARE REAL, not a guard against a case that cannot happen: on this island
    `JCT_AIRPORT`'s approach begins 24 m before its neighbour's has finished. A chunk carrying two
    interchanges is not a special case either -- `two_way_carriageway_profile` already takes a LIST
    of interchanges and lays every one of their slots out in a fixed order, so two auxiliary lanes
    in one piece is the ordinary path with a longer list."""
    ordered = sorted(items, key=lambda it: it["window"][0])
    groups = []
    for it in ordered:
        w0, w1 = it["window"]
        if groups and w0 - groups[-1][1] < min_gap:
            groups[-1] = (groups[-1][0], max(groups[-1][1], w1), groups[-1][2] + [it])
        else:
            groups.append((w0, w1, [it]))
    return groups


def _rotate_ring_to(pts, seam_s):
    """A closed ring re-cut so its OPEN seam falls at arc-length `seam_s`, returned unrolled
    (first point repeated at the end).

    The seam is wherever the author happened to start drawing, and an interchange sitting across
    it would have its window split between the two ends of the unrolled polyline -- half its
    auxiliary lane on a chunk at station 0 and half on a chunk 3 km later, meeting nothing. Moving
    the seam is free (a ring has no distinguished start) and removes the whole case, so it is done
    unconditionally rather than guarded for."""
    ring = list(pts)
    if len(ring) > 2 and math.dist(ring[0][:2], ring[-1][:2]) < 1e-6:
        ring = ring[:-1]
    unrolled = ring + [ring[0]]
    st = _stations(unrolled)
    total = st[-1]
    seam_s = seam_s % total
    head = _at(unrolled, seam_s)
    out = [head]
    # everything after the new seam, then everything before it (the ring's own start point among
    # them), then back to the seam -- one lap, unrolled.
    out += [tuple(p) for p, s in zip(unrolled[:-1], st) if s > seam_s + 1e-6]
    out += [tuple(p) for p, s in zip(unrolled[:-1], st) if s < seam_s - 1e-6]
    ded = [out[0]]
    for p in out[1:]:
        if math.dist(p[:2], ded[-1][:2]) > 1e-6:
            ded.append(p)
    ded.append(head)
    return ded


def carriageway_chunk_pieces(mainline_pts, interchanges, lanes=2, lane_width=3.5,
                             median=1.2, decel=DECEL_LENGTH, accel=ACCEL_LENGTH,
                             taper=TAPER_LENGTH, nose=GORE_NOSE, runout=GORE_RUNOUT,
                             min_chunk=MIN_DECK_CHUNK, closed=False):
    """The whole expressway as a CHAIN OF SEGMENTS -- plain deck chunks and interchange chunks --
    plus one piece per ramp. The chunked counterpart of `two_way_carriageway_pieces`; see the
    section header above for why the expressway stopped being one piece.

    `interchanges` is `[(ramp_id, ramp_pts, kind, side), ...]`, `kind` in `{'split','merge'}` and
    `side` in `{lp.FWD, lp.REV}` -- the same tuple `two_way_carriageway_pieces` takes, so the two
    are interchangeable at the call site.

    Returns::

        {"chunks": [ {name, pts, lanes, lanes_backward, profile_set, exits, entries}, ... ],
         "ramps":  {ramp_id: {pts, lanes, lanes_end, align, profile_set}},
         "gores":  {ramp_id: {...}}}

    `chunks` is in ring order and CONSECUTIVE CHUNKS SHARE AN ENDPOINT EXACTLY, which is what lets
    the joint between them be authored (and then measured) exactly like any other segment seam --
    no expressway-shaped exception anywhere downstream."""
    n = int(lanes)
    if n < 1:
        raise RkaBuildError("a carriageway needs at least one lane per direction (got %d)" % n)
    if len(mainline_pts) < 2:
        raise RkaBuildError("the carriageway needs at least 2 points")

    base = list(mainline_pts)
    if closed:
        # Windows first (on the ring as authored), then re-cut the ring so the seam sits in the
        # biggest gap between them -- see `_rotate_ring_to`.
        probe_s = []
        ring = base[:-1] if (len(base) > 2 and
                             math.dist(base[0][:2], base[-1][:2]) < 1e-6) else base
        unrolled = ring + [ring[0]]
        total0 = _plen(unrolled)
        for rid, ramp_pts, kind, _side in interchanges:
            probe = ramp_pts[0] if kind == 'split' else ramp_pts[-1]
            s_g, _d = _locate(unrolled, probe)
            probe_s.append(_interchange_window(s_g, kind, decel, accel, taper, runout))
        if probe_s:
            occupied = sorted((w0 % total0, w1 % total0) for w0, w1 in probe_s)
            best_gap, seam = -1.0, 0.0
            for k, (_a, b) in enumerate(occupied):
                nxt = occupied[(k + 1) % len(occupied)][0]
                gap = (nxt - b) % total0
                if gap > best_gap:
                    best_gap, seam = gap, (b + gap / 2.0) % total0
            base = _rotate_ring_to(unrolled, seam)
        else:
            base = unrolled

    total = _plen(base)
    items = []
    for rid, ramp_pts, kind, side in interchanges:
        if len(ramp_pts) < 2:
            raise RkaBuildError("ramp %s needs at least 2 points" % rid)
        probe = ramp_pts[0] if kind == 'split' else ramp_pts[-1]
        s_gore, _d = _locate(base, probe)
        w0, w1 = _interchange_window(s_gore, kind, decel, accel, taper, runout)
        if w0 < 1.0 or w1 > total - 1.0:
            raise RkaBuildError(
                "%s: its gore sits %.0f m along a %.0f m carriageway, but the interchange needs "
                "%.0f m before it and %.0f m after it" % (rid, s_gore, total, s_gore - w0,
                                                          w1 - s_gore))
        items.append(dict(rid=rid, ramp_pts=list(ramp_pts), kind=kind, side=side,
                          s_gore=s_gore, window=(w0, w1),
                          knots=_interchange_knots(s_gore, kind, lane_width, nose,
                                                   decel, accel, taper, runout)))

    groups = _merge_windows(items, min_chunk)

    def profile_for(members, widths=None):
        return two_way_carriageway_profile(
            n, lane_width, [(it["rid"], it["side"]) for it in members], widths, nose, median)

    # --- the ramps: seeded off the aux slot edge of the chunk they leave, exactly as before -----
    ramp_specs, gores = {}, {}
    for w0, w1, members in groups:
        for it in members:
            open_ = (nose, lane_width)
            op = profile_for(members, {it["rid"]: open_})
            lo, hi = lp.slot_edges(op, op.index_of("%s_A0" % it["rid"]))
            # NEAREST edge to the carriageway it leaves: the far (positive) edge on the reverse
            # side, the near edge on the forward side. Same rule as the one-piece model.
            a_edge = hi if it["side"] == lp.REV else lo
            t = _tangent(base, it["s_gore"])
            nrm = _left_normal(t)
            g = _at(base, it["s_gore"])
            seed = (g[0] + nrm[0] * a_edge, g[1] + nrm[1] * a_edge, g[2])
            ramp_specs[it["rid"]] = dict(
                pts=seed_ramp(it["ramp_pts"], seed, t, it["kind"]), lanes=1, lanes_end=None,
                align='right', profile_set=branch_profile(1, lane_width, "A"))
            gores[it["rid"]] = dict(position=g, station=it["s_gore"], tangent=t, normal=nrm,
                                    kind=it["kind"], side=it["side"], offset_a=a_edge, profile=op)

    # --- the chunks: plain deck between the groups, an interchange chunk on each ---------------
    chunks = []
    cuts = [0.0]
    for w0, w1, _members in groups:
        cuts += [w0, w1]
    cuts.append(total)

    def add_chunk(s0, s1, members):
        if s1 - s0 < 1e-3:
            return
        pts = _slice(base, s0, s1)
        if len(pts) < 2:
            return
        if members:
            knots = {it["rid"]: it["knots"] for it in members}
            local = sorted(s - s0 for seq in knots.values() for s, _w in seq
                           if s0 - 1e-6 <= s <= s1 + 1e-6)
            pts = _with_stations(pts, pts, local)
            span = max(_plen(pts), 1e-6)
            marks = []
            for ls in sorted(set([0.0, span] + local)):
                widths = {it["rid"]: _knot_at(it["knots"], s0 + ls) for it in members}
                marks.append((ls / span, profile_for(members, widths)))
            stations, profiles = _ascending(marks)
            pset = lp.ProfileSet(profiles, stations)
        else:
            pset = lp.ProfileSet([profile_for(())])
        chunks.append(dict(
            pts=pts, lanes=n, lanes_backward=n, profile_set=pset,
            interchanges=[it["rid"] for it in members],
            exits=[it["rid"] for it in members if it["kind"] == 'split'],
            entries=[it["rid"] for it in members if it["kind"] == 'merge']))

    prev = 0.0
    for w0, w1, members in groups:
        add_chunk(prev, w0, ())          # plain deck up to this interchange
        add_chunk(w0, w1, members)       # the interchange itself
        prev = w1
    add_chunk(prev, total, ())           # plain deck out to the end of the carriageway

    return {"chunks": chunks, "ramps": ramp_specs, "gores": gores}


def line_merge_pieces(branch_a_pts, branch_b_pts, trunk_pts, lanes_a=1, lanes_b=2,
                      lane_width=3.5, trunk_lanes=None, accel=ACCEL_LENGTH,
                      taper=TAPER_LENGTH, nose=GORE_NOSE):
    """Two branch lines joining into one trunk line — the exact mirror of a split.

    Branches are authored TOWARD the gore (their LAST point meets the trunk), and the trunk runs
    away from it. The auxiliary lane is longer than a split's because joining traffic has to
    reach trunk speed before the lane is taken away.
    """
    a, b = int(lanes_a), int(lanes_b)
    total = a + b
    n_out = total if trunk_lanes is None else int(trunk_lanes)
    if len(trunk_pts) < 2 or len(branch_a_pts) < 2 or len(branch_b_pts) < 2:
        raise RkaBuildError("trunk and both branches need at least 2 points each")

    trunk_len = _plen(trunk_pts)
    s_a, _ = _locate(trunk_pts, branch_a_pts[-1])
    s_b, _ = _locate(trunk_pts, branch_b_pts[-1])
    s_gore = (s_a + s_b) / 2.0
    narrow = total - n_out
    need = (accel + taper) if narrow else 0.0
    if trunk_len - s_gore < need + 1.0:
        raise RkaBuildError(
            "gore sits %.0f m from the trunk end but narrowing from %d lanes needs %.0f m of "
            "acceleration lane + taper ahead of it — lengthen the trunk"
            % (trunk_len - s_gore, total, need))

    t = _tangent(trunk_pts, s_gore)
    n = _left_normal(t)
    g = _at(trunk_pts, s_gore)
    open_p = gore_profile(a, b, lane_width, aux_a=narrow, nose=nose, opened=True)
    flush_p = gore_profile(a, b, lane_width, aux_a=narrow, nose=nose, opened=False, aux_open=True)
    shut_p = gore_profile(a, b, lane_width, aux_a=narrow, nose=nose, opened=False)
    off_a, off_b = branch_seed_offsets(open_p, a, b)
    end_a = (g[0] + n[0] * off_a, g[1] + n[1] * off_a, g[2])
    end_b = (g[0] + n[0] * off_b, g[1] + n[1] * off_b, g[2])

    pieces = {"branch_a": dict(pts=[tuple(p) for p in branch_a_pts[:-1]] + [end_a],
                               lanes=a, lanes_end=None, align='right',
                               profile_set=branch_profile(a, lane_width, "A")),
              "branch_b": dict(pts=[tuple(p) for p in branch_b_pts[:-1]] + [end_b],
                               lanes=b, lanes_end=None, align='right',
                               profile_set=branch_profile(b, lane_width, "B"))}
    # The exact mirror of the split: ONE trunk piece running away from the gore, whose auxiliary
    # lane is held for `accel` (joining traffic must reach trunk speed) and then tapered out.
    trunk_out = _slice(trunk_pts, s_gore, trunk_len)
    # Mirror of the split's nose handling: the gore CLOSES over the first `NOSE_LENGTH` metres
    # after the gore point, so joining traffic gets a lane flush against the mainline for the rest
    # of its acceleration run rather than a strip held 3 m away from the road it is merging into.
    s_nose1 = min(trunk_len, s_gore + NOSE_LENGTH)
    if narrow:
        s_aux1 = s_gore + accel
        s_taper1 = min(trunk_len, s_aux1 + taper)
        s_nose1 = min(s_nose1, s_aux1)
        trunk_out = _with_stations(trunk_out, trunk_pts, (s_nose1, s_aux1, s_taper1))
        span = max(_plen(trunk_out), 1e-6)
        marks = [(0.0, open_p),                              # the gore itself
                 ((s_nose1 - s_gore) / span, flush_p),       # nose closed, lane now flush
                 ((s_aux1 - s_gore) / span, flush_p),        # held to the end of the accel run
                 ((s_taper1 - s_gore) / span, shut_p)]       # auxiliary lane tapered away
        if trunk_len - s_taper1 > 1.0:
            marks.append((1.0, shut_p))
    else:
        trunk_out = _with_stations(trunk_out, trunk_pts, (s_nose1,))
        span = max(_plen(trunk_out), 1e-6)
        marks = [(0.0, open_p), ((s_nose1 - s_gore) / span, flush_p), (1.0, flush_p)]
    stations, profiles = _ascending(marks)
    pieces["trunk"] = dict(pts=trunk_out, lanes=total, lanes_end=None, align='right',
                           profile_set=lp.ProfileSet(profiles, stations))
    pieces["_gore"] = dict(position=g, station=s_gore, tangent=t, normal=n,
                           offset_a=off_a, offset_b=off_b, narrowed=bool(narrow),
                           trunk_lanes=n_out, total_lanes=total, profile=open_p)
    return pieces


# ------------------------------------------------------------------------------- operators
def _pick_curves(context, trunk_name, a_name, b_name):
    trunk = _resolve_curve_object(context, trunk_name)
    named = [bpy.data.objects.get(n) for n in (a_name, b_name)]
    picked = [o for o in named if o is not None and o.type == 'CURVE']
    if len(picked) < 2:
        rest = [o for o in context.selected_objects if o.type == 'CURVE' and o is not trunk]
        for o in rest:
            if o not in picked:
                picked.append(o)
            if len(picked) == 2:
                break
    return trunk, (picked + [None, None])[:2]


class RKA_OT_build_line_split(bpy.types.Operator):
    """Split one road line into two — a motorway off-ramp, an expressway Y-fork, a carriageway
    dividing around an island. The branches leave TANGENT at a gore, so traffic never stops and
    never turns: this is what an intersection pad cannot express.

    Select the TRUNK curve, then the two BRANCH curves (or name them below). Branch A is the LEFT
    one in keep-left travel. Set Trunk Lanes below the branch total to taper an auxiliary lane in
    beforehand — that is the off-ramp; leave it at the default for a pure fork."""
    bl_idname = "rka.build_line_split"
    bl_label = "Split Line (one road -> two)"
    bl_options = {'REGISTER', 'UNDO'}

    trunk_curve: bpy.props.StringProperty(name="Trunk Curve", default="")
    branch_a_curve: bpy.props.StringProperty(name="Branch A (left)", default="")
    branch_b_curve: bpy.props.StringProperty(name="Branch B (right)", default="")
    lanes_a: bpy.props.IntProperty(name="Lanes: Branch A", default=1, min=1, max=4)
    lanes_b: bpy.props.IntProperty(name="Lanes: Branch B", default=2, min=1, max=4)
    trunk_lanes: bpy.props.IntProperty(
        name="Trunk Lanes", default=0, min=0, max=8,
        description="Lanes on the trunk BEFORE the split. 0 = branch total (a pure fork, no "
                    "widening). Set it one lower to taper an auxiliary lane in first — the "
                    "motorway off-ramp")
    lane_width: bpy.props.FloatProperty(name="Lane Width", default=3.5, min=0.5, unit='LENGTH')
    decel_length: bpy.props.FloatProperty(name="Auxiliary Length", default=DECEL_LENGTH,
                                          min=10.0, unit='LENGTH')
    taper_length: bpy.props.FloatProperty(name="Taper Length", default=TAPER_LENGTH,
                                          min=5.0, unit='LENGTH')
    nose: bpy.props.FloatProperty(name="Gore Nose", default=GORE_NOSE, min=0.0, unit='LENGTH')

    def execute(self, context):
        trunk, (ba, bb) = _pick_curves(context, self.trunk_curve,
                                       self.branch_a_curve, self.branch_b_curve)
        if trunk is None or ba is None or bb is None:
            self.report({'ERROR'}, "Select the trunk curve and BOTH branch curves")
            return {'CANCELLED'}
        try:
            pieces = line_split_pieces(
                _sample_curve_world_points(context, trunk),
                _sample_curve_world_points(context, ba),
                _sample_curve_world_points(context, bb),
                lanes_a=self.lanes_a, lanes_b=self.lanes_b, lane_width=self.lane_width,
                trunk_lanes=(self.trunk_lanes or None), decel=self.decel_length,
                taper=self.taper_length, nose=self.nose)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        n = _emit(context, trunk, pieces, self.lane_width, "Split")
        g = pieces["_gore"]
        self.report({'INFO'}, "Split built: %d piece(s), gore at %.1f m, branches %+.2f / %+.2f m "
                    "off the trunk centreline%s"
                    % (n, g["station"], g["offset_a"], g["offset_b"],
                       " (auxiliary lane tapered in)" if g["widened"] else " (pure fork)"))
        return {'FINISHED'}


class RKA_OT_build_line_merge(bpy.types.Operator):
    """Merge two road lines into one — a motorway on-ramp, two carriageways rejoining. The mirror
    of Split Line, with a longer auxiliary lane because joining traffic has to reach trunk speed.

    Select the two BRANCH curves and then the TRUNK curve (or name them below)."""
    bl_idname = "rka.build_line_merge"
    bl_label = "Merge Lines (two roads -> one)"
    bl_options = {'REGISTER', 'UNDO'}

    trunk_curve: bpy.props.StringProperty(name="Trunk Curve", default="")
    branch_a_curve: bpy.props.StringProperty(name="Branch A (left)", default="")
    branch_b_curve: bpy.props.StringProperty(name="Branch B (right)", default="")
    lanes_a: bpy.props.IntProperty(name="Lanes: Branch A", default=1, min=1, max=4)
    lanes_b: bpy.props.IntProperty(name="Lanes: Branch B", default=2, min=1, max=4)
    trunk_lanes: bpy.props.IntProperty(name="Trunk Lanes", default=0, min=0, max=8)
    lane_width: bpy.props.FloatProperty(name="Lane Width", default=3.5, min=0.5, unit='LENGTH')
    accel_length: bpy.props.FloatProperty(name="Auxiliary Length", default=ACCEL_LENGTH,
                                          min=10.0, unit='LENGTH')
    taper_length: bpy.props.FloatProperty(name="Taper Length", default=TAPER_LENGTH,
                                          min=5.0, unit='LENGTH')
    nose: bpy.props.FloatProperty(name="Gore Nose", default=GORE_NOSE, min=0.0, unit='LENGTH')

    def execute(self, context):
        trunk, (ba, bb) = _pick_curves(context, self.trunk_curve,
                                       self.branch_a_curve, self.branch_b_curve)
        if trunk is None or ba is None or bb is None:
            self.report({'ERROR'}, "Select both branch curves and the trunk curve")
            return {'CANCELLED'}
        try:
            pieces = line_merge_pieces(
                _sample_curve_world_points(context, ba),
                _sample_curve_world_points(context, bb),
                _sample_curve_world_points(context, trunk),
                lanes_a=self.lanes_a, lanes_b=self.lanes_b, lane_width=self.lane_width,
                trunk_lanes=(self.trunk_lanes or None), accel=self.accel_length,
                taper=self.taper_length, nose=self.nose)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        n = _emit(context, trunk, pieces, self.lane_width, "Merge")
        g = pieces["_gore"]
        self.report({'INFO'}, "Merge built: %d piece(s), gore at %.1f m" % (n, g["station"]))
        return {'FINISHED'}


def _emit(context, anchor, pieces, lane_width, tag):
    parent = (parent_collection_of(anchor.users_collection[0]) if anchor.users_collection
              else context.view_layer.active_layer_collection.collection)
    built = 0
    for name, spec in pieces.items():
        if name.startswith("_"):
            continue
        _build_segment_from_points(
            context, parent, spec["pts"], lane_width, spec["lanes"], 0,
            'NONE', 'NONE', 0.15, 0.25, False, "", "",
            base_name="%s_%s" % (tag, name), traffic_side='LEFT',
            lanes_end=spec["lanes_end"], align=spec["align"],
            profile_set=spec.get("profile_set"),
            link_group=tag, link_role=name)
        built += 1
    return built


CLASSES = (RKA_OT_build_line_split, RKA_OT_build_line_merge)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
