"""road_points.py -- the point/port road model's geometry core. PURE PYTHON, no bpy.

`python3 lib/road_points.py` runs the self-tests.

See `blender/ROAD_POINT_GRAPH.md` for the design. This module owns three things and deliberately
nothing else:

1.  **The chain.** A road is an ordered list of STATIONS (authored points). The shape between them
    is a Catmull-Rom spline through the station positions, so a curved road needs only the points
    where something actually changes -- not one vertex per bend. `SHARP` breaks the tangent at a
    station; `MANUAL` takes it from the station's own authored direction.

2.  **Resampling.** `resample()` turns the chain into evenly-spaced samples carrying position,
    tangent, left-normal and the profile parameter, with a sample FORCED at every station so a
    cross-section change always lands exactly where it was authored.

3.  **`lane_taper_route()` -- the one thing that is NOT free.** See its docstring; this is the
    correction the whole design rests on.

WHAT THIS MODULE MUST NEVER DO: compute a lateral offset of its own. `lane_profile.slot_offset()`
is the single owner of "where is slot i" (ROAD_KIT_REDESIGN.md defect 1). This module asks it and
then places geometry along the normal.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lane_profile as lp                                              # noqa: E402

AUTO = 'AUTO'
SHARP = 'SHARP'
MANUAL = 'MANUAL'

#: Default spacing of resampled points along a road, in metres. A station always gets its own
#: sample regardless, so this only controls how finely the curve BETWEEN stations is drawn.
SAMPLE_STEP = 4.0


# ------------------------------------------------------------------------------------- vectors

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _norm(a):
    n = _len(a)
    return (0.0, 0.0, 0.0) if n <= 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def left_normal(tangent, roll=0.0):
    """The +s direction at a sample: the tangent rotated +90 degrees in the XY plane, then rolled
    about the tangent by `roll` radians (superelevation).

    XY and not the full 3D frame, because a road's cross-section is level with the world except
    for the banking the author asked for -- deriving the normal from a 3D binormal would tilt the
    carriageway on every vertical curve, which is a crest, not a banked turn."""
    n = _norm((-tangent[1], tangent[0], 0.0))
    if abs(roll) < 1e-9:
        return n
    # Rotate n about the tangent axis (Rodrigues, with n perpendicular to the axis already).
    t = _norm(tangent)
    c, s = math.cos(roll), math.sin(roll)
    cross = (t[1] * n[2] - t[2] * n[1],
             t[2] * n[0] - t[0] * n[2],
             t[0] * n[1] - t[1] * n[0])
    return _norm(_add(_mul(n, c), _mul(cross, s)))


# --------------------------------------------------------------------------------- the chain

class Station(object):
    """One authored road point, as this module sees it: where it is, what its cross-section is,
    and how the curve behaves through it. The Blender Object and its links live in the addon;
    nothing here knows about bpy."""

    __slots__ = ("pos", "profile", "tangent_mode", "tangent", "roll", "name",
                 "handle_in", "handle_out")

    def __init__(self, pos, profile, tangent_mode=AUTO, tangent=None, roll=0.0, name="",
                 handle_in=0.0, handle_out=0.0):
        self.pos = (float(pos[0]), float(pos[1]), float(pos[2]) if len(pos) > 2 else 0.0)
        self.profile = profile
        self.tangent_mode = tangent_mode
        #: The authored direction (need not be normalised). MANUAL takes the curve from it; the
        #: other modes still carry it, because the overlay draws the authored facing either way.
        self.tangent = tangent
        #: Superelevation at this station, radians. Advisory: nothing gates on it.
        self.roll = float(roll)
        self.name = name
        #: Handle LENGTHS in metres, 0 = automatic (the chord, the Catmull-Rom default). They
        #: change how hard the curve leaves/arrives, never which way -- direction is the tangent.
        self.handle_in = float(handle_in)
        self.handle_out = float(handle_out)

    def __repr__(self):
        return "Station(%r, %s)" % (self.name or self.pos, self.tangent_mode)


def chain_tangents(stations, is_loop=False):
    """`[(tangent_in, tangent_out), ...]` -- one PAIR per station.

    A pair, not a single vector, because that is the only way `SHARP` can mean anything: a corner
    is precisely a station whose incoming and outgoing tangents DIFFER. With one tangent per
    station a "sharp" corner still curves on both sides of itself, which is the opposite of what
    was asked for.

    `AUTO` is the Catmull-Rom tangent (the vector between the neighbours) and gives an identical
    pair, so a road curves smoothly through its points with no handle to touch. `SHARP` gives the
    incoming chord in and the outgoing chord out. `MANUAL` gives the authored direction both ways.

    At an open chain's ends the single available chord is used -- extrapolating a phantom
    neighbour invents curvature the author did not author."""
    n = len(stations)
    if n == 0:
        return []
    if n == 1:
        t = _norm(stations[0].tangent or (1.0, 0.0, 0.0))
        return [(t, t)]
    out = []
    for i, st in enumerate(stations):
        if st.tangent_mode == MANUAL and st.tangent is not None:
            t = _norm(st.tangent)
            out.append((t, t))
            continue
        if is_loop:
            prev, nxt = stations[(i - 1) % n].pos, stations[(i + 1) % n].pos
        else:
            prev = stations[i - 1].pos if i > 0 else st.pos
            nxt = stations[i + 1].pos if i < n - 1 else st.pos
        d_in = _sub(st.pos, prev)
        d_out = _sub(nxt, st.pos)
        if st.tangent_mode == SHARP:
            # Corner: each side keeps its own chord, so neither segment bends to meet the other.
            t_in = _norm(d_in) if _len(d_in) > 1e-9 else _norm(d_out)
            t_out = _norm(d_out) if _len(d_out) > 1e-9 else _norm(d_in)
        else:
            d = _sub(nxt, prev)
            if _len(d) <= 1e-9:
                d = d_out if _len(d_out) > 1e-9 else d_in
            t_in = t_out = _norm(d)
        out.append((t_in, t_out))
    return out


#: Below this, a segment is STRAIGHT. Straightness is DETECTED, never authored: a "straight or
#: curved" flag on a link is one more piece of state to keep in sync with the geometry, and the
#: geometry already knows -- a Hermite whose two tangents both lie along the chord IS the chord.
STRAIGHT_TOL_DEG = 1.0


def _angle_deg(a, b):
    la, lb = _len(a), _len(b)
    if la <= 1e-9 or lb <= 1e-9:
        return 0.0
    c = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (la * lb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def segment_bend_deg(p0, t_out, p1, t_in):
    """How far this segment departs from a straight line, in degrees: the WORSE of the two angles
    between the chord and the tangents that bracket it. 0 = dead straight.

    This is the number the artist needs while rotating a point -- "the road is straight here" or
    "it leaves at 14 degrees" -- and it is what makes `STRAIGHT` a fact about the geometry rather
    than a checkbox someone has to remember to tick."""
    chord = _sub(p1, p0)
    if _len(chord) <= 1e-9:
        return 0.0
    return max(_angle_deg(t_out, chord), _angle_deg(t_in, chord))


def chain_bends(stations, is_loop=False):
    """`[(i, j, bend_deg)]` for every segment of the chain, in chain order."""
    n = len(stations)
    if n < 2:
        return []
    tans = chain_tangents(stations, is_loop)
    segs = list(range(n - 1)) + ([n - 1] if is_loop else [])
    out = []
    for i in segs:
        j = (i + 1) % n
        out.append((i, j, segment_bend_deg(stations[i].pos, tans[i][1],
                                           stations[j].pos, tans[j][0])))
    return out


def _hermite(p0, p1, m0, m1, t):
    """Cubic Hermite between two stations with the given (already scaled) tangents."""
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return (h00 * p0[0] + h10 * m0[0] + h01 * p1[0] + h11 * m1[0],
            h00 * p0[1] + h10 * m0[1] + h01 * p1[1] + h11 * m1[1],
            h00 * p0[2] + h10 * m0[2] + h01 * p1[2] + h11 * m1[2])


def _hermite_deriv(p0, p1, m0, m1, t):
    t2 = t * t
    d00 = 6 * t2 - 6 * t
    d10 = 3 * t2 - 4 * t + 1
    d01 = -6 * t2 + 6 * t
    d11 = 3 * t2 - 2 * t
    return (d00 * p0[0] + d10 * m0[0] + d01 * p1[0] + d11 * m1[0],
            d00 * p0[1] + d10 * m0[1] + d01 * p1[1] + d11 * m1[1],
            d00 * p0[2] + d10 * m0[2] + d01 * p1[2] + d11 * m1[2])


class Sample(object):
    """One resampled point along a road."""

    __slots__ = ("pos", "tangent", "normal", "seg", "local", "s", "at_station")

    def __init__(self, pos, tangent, normal, seg, local, s, at_station):
        self.pos = pos
        self.tangent = tangent
        self.normal = normal
        #: Index of the station this sample's segment STARTS at, and 0..1 within that segment.
        self.seg = seg
        self.local = local
        #: Arclength from the chain start.
        self.s = s
        #: Station index when this sample IS a station, else None. A cross-section change must
        #: land exactly where it was authored, so stations are never interpolated over.
        self.at_station = at_station

    def __repr__(self):
        return "Sample(%.2f,%.2f,%.2f s=%.1f%s)" % (
            self.pos[0], self.pos[1], self.pos[2], self.s,
            "" if self.at_station is None else " @st%d" % self.at_station)


def resample(stations, is_loop=False, step=SAMPLE_STEP):
    """Evenly-ish spaced `Sample`s along the chain, with a sample forced AT every station.

    Returns `[]` for fewer than two stations. The step is a maximum: each inter-station segment is
    divided into a whole number of pieces, so no sample ever drifts off a station."""
    n = len(stations)
    if n < 2:
        return []
    tans = chain_tangents(stations, is_loop)
    segs = list(range(n - 1)) + ([n - 1] if is_loop else [])
    out = []
    s_acc = 0.0
    for k, i in enumerate(segs):
        j = (i + 1) % n
        p0, p1 = stations[i].pos, stations[j].pos
        chord = _len(_sub(p1, p0))
        # Catmull-Rom scales the unit tangent by the chord so the curve neither loops nor flattens.
        # This segment LEAVES station i and ARRIVES at station j, so it takes i's OUT and j's IN --
        # which is what lets a SHARP station corner instead of bending its neighbours.
        # A handle length of 0 means "automatic" = the chord, which is exactly Catmull-Rom.
        # Authored lengths are in METRES, so a handle equal to the chord reproduces the default.
        h0 = stations[i].handle_out if stations[i].handle_out > 1e-6 else chord
        h1 = stations[j].handle_in if stations[j].handle_in > 1e-6 else chord
        m0, m1 = _mul(tans[i][1], h0), _mul(tans[j][0], h1)
        div = max(1, int(math.ceil(chord / step))) if chord > 1e-9 else 1
        last = out[-1].pos if out else None
        for d in range(div + 1):
            if d == 0 and out:
                continue                      # this station already emitted by the previous segment
            t = d / float(div)
            pos = _hermite(p0, p1, m0, m1, t)
            der = _hermite_deriv(p0, p1, m0, m1, t)
            if _len(der) <= 1e-9:
                der = _sub(p1, p0)
            tan = _norm(der)
            if last is not None:
                s_acc += _len(_sub(pos, last))
            last = pos
            at = i if d == 0 else (j if d == div else None)
            if at is not None and at == 0 and k > 0:
                at = None                     # a loop returning to station 0 is not a new station
            roll = 0.0
            if at is not None:
                roll = stations[at].roll
            else:
                roll = stations[i].roll + (stations[j].roll - stations[i].roll) * t
            out.append(Sample(pos, tan, left_normal(tan, roll), i, t, s_acc, at))
    return out


def profile_at(stations, sample, is_loop=False):
    """The cross-section at one sample: the two bracketing stations' profiles, interpolated.

    A station's own sample returns that station's profile untouched -- which is what makes "the
    taper length is the distance the author put between two points" literally true."""
    if sample.at_station is not None:
        return stations[sample.at_station].profile.copy()
    i = sample.seg
    j = (i + 1) % len(stations)
    return lp.interpolate(stations[i].profile, stations[j].profile, sample.local)


# ---------------------------------------------------------------------------- the taper routes

class LaneRoute(object):
    """One drivable slot's centreline along a road, over the slot's FULL span."""

    __slots__ = ("slot_id", "dir", "kind", "points", "widths", "i0", "i1",
                 "merge_into", "opens_from")

    def __init__(self, slot_id, dir, kind, points, widths, i0, i1,
                 merge_into=None, opens_from=None):
        self.slot_id = slot_id
        self.dir = dir
        self.kind = kind
        self.points = points
        self.widths = widths
        #: First/last sample index at which the slot is a usable lane (`> LANE_MIN_WIDTH`). The
        #: route still SPANS the whole chain -- see `lane_taper_route`.
        self.i0 = i0
        self.i1 = i1
        #: Slot id this lane feeds when it tapers out / is fed by when it opens late. None when it
        #: runs the whole length, or when there is no neighbour to merge with (a validation error).
        self.merge_into = merge_into
        self.opens_from = opens_from

    def __repr__(self):
        return "LaneRoute(%s %s %d pts %d..%d%s)" % (
            self.slot_id, self.dir, len(self.points), self.i0, self.i1,
            "" if not self.merge_into else " ->%s" % self.merge_into)


def _neighbour_map(profiles):
    """`slot_id -> (inboard_id, outboard_id)` using the widest station's ordering.

    The widest station is used because a slot that is zero-width everywhere else still has to know
    who it merges into, and the station where every slot is present is the one that says."""
    best, best_n = None, -1
    for p in profiles:
        live = [s for s in p.slots if s.width > lp.LANE_MIN_WIDTH]
        if len(live) > best_n:
            best, best_n = p, len(live)
    order = [s.id for s in (best.slots if best else [])]
    out = {}
    for k, sid in enumerate(order):
        out[sid] = (order[k - 1] if k > 0 else None,
                    order[k + 1] if k + 1 < len(order) else None)
    return out


def lane_taper_route(stations, samples, is_loop=False):
    """Every drivable slot's route, with tapering lanes led INTO the lane that receives them.

    WHY THIS FUNCTION EXISTS -- the design's load-bearing correction, measured not assumed. Lane
    *widths* interpolate for free (`lane_profile.interpolate`); lane *routes* do not, and taking
    the raw slot centreline gives three wrong answers:

      1. A merging lane's centreline ends on the LANE LINE, not in the lane that receives it.
         Measured on a 3->2 drop with 3.5 m lanes and a 1.0 m median: the dying `F2` ends at
         offset 7.50, while `F1`'s centre is 5.75 and its OUTBOARD EDGE is 7.50. The car finishes
         its merge straddling the paint, half a lane out.
      2. An opening auxiliary lane's route carries its first-live offset BACKWARDS, so its head
         sits 2.1 m outboard of the through lane it is supposed to be fed from -- two wheels off
         the asphalt. (`lane_profile.lane_runs` does this deliberately, to keep the sequence
         monotone for callers that sample outside the run; it is right there and wrong here.)
      3. `LANE_MIN_WIDTH` truncates the run, so the polyline stops roughly a fifth of the taper
         short -- far outside `LaneGraph`'s 4.5 m junction radius, so the route never chains and
         the car is reclaimed as route-finished.

    THE RULE, one formula for both directions of the problem: a slot's route is a blend between
    the lane that receives it and its own centreline, keyed on how much of the lane exists yet.

        blend = width / max_width_along_the_run
        route = lerp(receiver_centre, own_centre, blend)

    At full width the route IS the lane centre; at zero width it IS the receiving lane's centre.
    So a lane that opens leaves the through lane and drifts out as it materialises, and a lane
    that dies converges onto the lane it merges into and ends exactly on its centreline. The route
    always spans the whole chain, so it reaches its successor.

    Routes are resolved MEDIAN-OUTWARD, so a receiver that is itself tapering already has its own
    corrected route to hand -- chained tapers compose instead of stacking errors.
    """
    if len(samples) < 2:
        return []
    profs = [profile_at(stations, sm, is_loop) for sm in samples]
    neigh = _neighbour_map(profs)

    # Per slot: width and true lateral offset at every sample. Computed here rather than taken
    # from `lane_runs` precisely because of defect 2 above -- we need the UNCARRIED offsets.
    ids = []
    for p in profs:
        for s in p.slots:
            if s.id not in ids:
                ids.append(s.id)
    widths, offsets, proto = {}, {}, {}
    for sid in ids:
        w, o = [], []
        for p in profs:
            k = p.index_of(sid)
            if k is None:
                w.append(0.0)
                o.append(None)
            else:
                w.append(p.slots[k].width)
                o.append(lp.slot_offset(p, k))
                proto.setdefault(sid, p.slots[k])
        widths[sid] = w
        offsets[sid] = o

    # Resolution order: median-outward, i.e. by |offset| at the widest station.
    def sort_key(sid):
        vals = [abs(v) for v in offsets[sid] if v is not None]
        return min(vals) if vals else 0.0

    n_all = len(samples)
    drivable = [sid for sid in ids
                if proto.get(sid) is not None and proto[sid].is_drivable()
                and any(x > lp.LANE_MIN_WIDTH for x in widths[sid])]

    def full_length(sid):
        w = widths[sid]
        return w[0] > lp.LANE_MIN_WIDTH and w[-1] > lp.LANE_MIN_WIDTH

    # RESOLUTION ORDER IS "RECEIVER FIRST", NOT MEDIAN-OUTWARD.
    # A kerb-side drop merges inboard and a median-side drop merges outboard, so no single lateral
    # sweep can guarantee the receiver is ready -- resolving F0 before F1 is exactly how an offside
    # drop ends up with no receiver at all. Lanes that run the full length are anchors (they
    # receive but never merge), so they go first; the rest resolve as soon as a neighbour of theirs
    # is resolved. This IS the design's "match lanes from the end where the count does not change".
    order = [sid for sid in sorted(drivable, key=sort_key) if full_length(sid)]
    pending = [sid for sid in sorted(drivable, key=sort_key) if not full_length(sid)]
    while pending:
        progressed = False
        for sid in list(pending):
            inb, outb = neigh.get(sid, (None, None))
            if any(c in order for c in (inb, outb) if c is not None):
                order.append(sid)
                pending.remove(sid)
                progressed = True
        if not progressed:
            order.extend(pending)          # isolated taper(s): no receiver, reported below
            break

    routes, centre_of = {}, {}
    for sid in order:
        s0 = proto[sid]
        w = widths[sid]
        live = [i for i, x in enumerate(w) if x > lp.LANE_MIN_WIDTH]
        i0, i1 = live[0], live[-1]
        wmax = max(w) or 1.0

        inb, outb = neigh.get(sid, (None, None))
        # Prefer the INBOARD neighbour (a kerb-side drop merges toward the median); fall back to
        # the OUTBOARD one for a median-side drop. That fallback is the whole of `drop_side`.
        recv = None
        for cand in (inb, outb):
            if cand is not None and cand in centre_of:
                recv = cand
                break

        pts, own = [], []
        for i, sm in enumerate(samples):
            off = offsets[sid][i]
            if off is None:
                # Slot absent from this interpolated station: hold the nearest known offset so the
                # blend still has something to lerp from.
                known = [v for v in offsets[sid] if v is not None]
                off = known[0] if known else 0.0
            own.append(off)
            own_pt = _add(sm.pos, _mul(sm.normal, off))
            if recv is None:
                pts.append(own_pt)
                continue
            blend = w[i] / wmax
            blend = 0.0 if blend < 0.0 else (1.0 if blend > 1.0 else blend)
            pts.append(_lerp(centre_of[recv][i], own_pt, blend))

        centre_of[sid] = pts
        routes[sid] = LaneRoute(
            sid, s0.dir, s0.kind, pts, w, i0, i1,
            merge_into=(recv if i1 < n_all - 1 else None),
            opens_from=(recv if i0 > 0 else None))
    return [routes[k] for k in sorted(routes, key=sort_key)]


# ------------------------------------------------------------------------------------ self-test

def _profile(fwd, bwd, lw=3.5, median=1.0, aux_fwd=0):
    """A test cross-section, built median-outward with the ids the design uses."""
    slots = []
    for i in range(bwd - 1, -1, -1):
        slots.append(lp.Slot("R%d" % i, lp.TRAVEL, lw, lp.REV))
    if median > 0:
        slots.append(lp.Slot("MED", lp.MEDIAN, median, lp.NONE))
    for i in range(fwd):
        slots.append(lp.Slot("F%d" % i, lp.TRAVEL, lw, lp.FWD))
    for i in range(aux_fwd):
        slots.append(lp.Slot("AF%d" % i, lp.AUX, lw, lp.FWD))
    return lp.Profile(slots, lp.ANCHOR_DIVIDE)


def _straight(profiles, spacing=100.0):
    return [Station((i * spacing, 0.0, 0.0), p, name="p%03d" % i)
            for i, p in enumerate(profiles)]


def self_test():
    # --- chain + resample -------------------------------------------------------------------
    sts = _straight([_profile(2, 2), _profile(2, 2), _profile(2, 2)])
    sm = resample(sts, step=10.0)
    assert len(sm) == 21, len(sm)
    assert abs(sm[-1].s - 200.0) < 1e-6, sm[-1].s
    at = [s.at_station for s in sm if s.at_station is not None]
    assert at == [0, 1, 2], at
    assert abs(sm[0].normal[1] - 1.0) < 1e-9, sm[0].normal   # +X tangent -> +Y is the +s side
    print("OK: resample -- station samples preserved, arclength exact, normal is tangent+90")

    # A bend must actually curve: the midpoint of a right-angle chain leaves the chord.
    bent = [Station((0, 0, 0), _profile(1, 1)),
            Station((100, 0, 0), _profile(1, 1)),
            Station((100, 100, 0), _profile(1, 1))]
    b = resample(bent, step=5.0)
    mid = [s for s in b if s.at_station == 1][0]
    off_chord = max(abs(s.pos[1]) for s in b if s.s < mid.s)
    assert off_chord > 1.0, off_chord
    print("OK: AUTO tangents curve through a station (%.1f m off the chord)" % off_chord)

    sharp = [Station((0, 0, 0), _profile(1, 1)),
             Station((100, 0, 0), _profile(1, 1), tangent_mode=SHARP),
             Station((100, 100, 0), _profile(1, 1))]
    sb = resample(sharp, step=5.0)
    assert max(abs(s.pos[1]) for s in sb if s.s < 100.0) < 1e-6
    print("OK: SHARP corners instead of curving")

    # --- MANUAL: the station's own facing drives the curve, and STRAIGHT is DETECTED ----------
    # This is the bridge the addon was missing: `tangent_mode = MANUAL` was declared, the library
    # honoured it, and nothing ever passed a tangent -- so rotating a point did nothing.
    aligned = [Station((0, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(1, 0, 0)),
               Station((100, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(1, 0, 0))]
    sm = resample(aligned, step=5.0)
    assert max(abs(x.pos[1]) for x in sm) < 1e-9, "aligned facings must give a dead straight run"
    bends = chain_bends(aligned)
    assert len(bends) == 1 and bends[0][2] < STRAIGHT_TOL_DEG, bends
    print("OK: MANUAL facings that agree with the chord give a straight line (bend %.3f deg)"
          % bends[0][2])

    turned = [Station((0, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(1, 0, 0)),
              Station((100, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(0, 1, 0))]
    tb = resample(turned, step=5.0)
    bow = max(abs(x.pos[1]) for x in tb)
    assert bow > 5.0, bow
    assert chain_bends(turned)[0][2] > 45.0 - 1e-6, chain_bends(turned)
    print("OK: rotating one station bends the road (%.1f m of bow, %.0f deg)"
          % (bow, chain_bends(turned)[0][2]))

    # --- handle length changes how HARD it leaves, never which way ---------------------------
    soft = [Station((0, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(1, 0, 0),
                    handle_out=20.0),
            Station((100, 0, 0), _profile(1, 1), tangent_mode=MANUAL, tangent=(0, 1, 0),
                    handle_in=20.0)]
    sbow = max(abs(x.pos[1]) for x in resample(soft, step=5.0))
    assert sbow < bow, (sbow, bow)
    # ...and the DIRECTION it leaves in is untouched: the first step still goes along +X.
    first = resample(soft, step=5.0)[1].pos
    assert abs(first[1]) < abs(first[0]) * 0.05, first
    print("OK: a shorter handle tightens the curve (%.1f m -> %.1f m) without turning it"
          % (bow, sbow))

    # --- the three measured defects ----------------------------------------------------------
    # 3 -> 2 forward. F2 dies. Its route must END ON F1's centreline, not on the lane line.
    sts = _straight([_profile(3, 3), _profile(2, 3)])
    sm = resample(sts, step=10.0)
    rts = {r.slot_id: r for r in lane_taper_route(sts, sm)}
    f1, f2 = rts["F1"], rts["F2"]
    tail_gap = _len(_sub(f2.points[-1], f1.points[-1]))
    assert tail_gap < 0.3, "defect 1: merging tail %.2f m off the receiving centreline" % tail_gap
    assert f2.merge_into == "F1", f2.merge_into
    assert len(f2.points) == len(sm), (len(f2.points), len(sm))
    print("OK: defect 1 -- merging lane ends %.3f m from F1's centreline (was 1.75)" % tail_gap)

    # Same road, raw slot centreline: this is what NOT fixing it looks like.
    p_end = sts[1].profile
    raw = lp.slot_offset(p_end, p_end.index_of("F2")) if p_end.index_of("F2") is not None else None
    p_full = lp.interpolate(sts[0].profile, sts[1].profile, 1.0)
    raw = lp.slot_offset(p_full, p_full.index_of("F2"))
    f1_off = lp.slot_offset(p_full, p_full.index_of("F1"))
    assert abs(raw - (f1_off + 1.75)) < 1e-6, (raw, f1_off)
    print("   (raw slot centreline would have ended at %.2f, F1 centre %.2f -- half a lane out)"
          % (raw, f1_off))

    # An auxiliary lane opening: its HEAD must not be outboard of the lane it comes from.
    sts = _straight([_profile(2, 2, aux_fwd=0), _profile(2, 2, aux_fwd=1)])
    sm = resample(sts, step=10.0)
    rts = {r.slot_id: r for r in lane_taper_route(sts, sm)}
    af, f1 = rts["AF0"], rts["F1"]
    head_gap = _len(_sub(af.points[0], f1.points[0]))
    assert head_gap < 0.3, "defect 2: aux head %.2f m from the through lane" % head_gap
    assert af.opens_from == "F1", af.opens_from
    assert len(af.points) == len(sm), "defect 3: route truncated to %d of %d" % (
        len(af.points), len(sm))
    print("OK: defect 2 -- opening aux head %.3f m from F1 (was 2.10)" % head_gap)
    print("OK: defect 3 -- route spans all %d samples (lane_runs would give %d)"
          % (len(af.points), af.i1 - af.i0 + 1))

    # And it must actually GET THERE: full width at the end, on its own centreline.
    p1 = sts[1].profile
    want = lp.slot_offset(p1, p1.index_of("AF0"))
    got = _sub(af.points[-1], sm[-1].pos)[1]
    assert abs(got - want) < 1e-6, (got, want)
    print("OK: opened aux reaches its own centreline (%.2f m)" % got)

    # --- offside (median-side) drop ----------------------------------------------------------
    a = _profile(3, 3)
    b = _profile(3, 3)
    b.slots = [s for s in b.slots if s.id != "F0"]        # drop the MEDIAN lane, not the kerb one
    sts = _straight([a, b])
    sm = resample(sts, step=10.0)
    rts = {r.slot_id: r for r in lane_taper_route(sts, sm)}
    f0 = rts["F0"]
    assert f0.merge_into == "F1", f0.merge_into
    gap = _len(_sub(f0.points[-1], rts["F1"].points[-1]))
    assert gap < 0.3, gap
    print("OK: offside drop -- F0 merges OUTBOARD into F1 (%.3f m), no spine shift needed" % gap)

    # --- a lane that runs the whole way is untouched -------------------------------------------
    sts = _straight([_profile(2, 2), _profile(2, 2)])
    sm = resample(sts, step=10.0)
    rts = {r.slot_id: r for r in lane_taper_route(sts, sm)}
    p = lp.interpolate(sts[0].profile, sts[1].profile, 0.5)
    want = lp.slot_offset(p, p.index_of("F1"))
    mid = len(sm) // 2
    got = _sub(rts["F1"].points[mid], sm[mid].pos)[1]
    assert abs(got - want) < 1e-9, (got, want)
    assert rts["F1"].merge_into is None and rts["F1"].opens_from is None
    print("OK: a constant lane is exactly its own centreline (no blend applied)")

    # --- one-way ------------------------------------------------------------------------------
    sts = _straight([_profile(2, 0, median=0.0), _profile(2, 0, median=0.0)])
    sm = resample(sts, step=25.0)
    rts = lane_taper_route(sts, sm)
    assert {r.slot_id for r in rts} == {"F0", "F1"}, [r.slot_id for r in rts]
    assert all(r.dir == lp.FWD for r in rts)
    print("OK: lanes_bwd = 0 yields a one-way road (2 forward lanes, no reverse)")

    # --- loop ---------------------------------------------------------------------------------
    ring = [Station((math.cos(a) * 100, math.sin(a) * 100, 0.0), _profile(1, 1))
            for a in [i * math.pi / 4 for i in range(8)]]
    rs = resample(ring, is_loop=True, step=15.0)
    assert rs[0].at_station == 0
    assert sum(1 for s in rs if s.at_station is not None) == 8, \
        [s.at_station for s in rs if s.at_station is not None]
    closing = _len(_sub(rs[-1].pos, rs[0].pos))
    assert closing < 1e-6, closing
    print("OK: closed loop -- 8 stations, wraps exactly (%.2e m)" % closing)

    print("\nALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
