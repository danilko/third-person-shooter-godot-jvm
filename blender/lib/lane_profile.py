"""lane_profile.py -- pure-Python (no bpy), self-tested ordered cross-section for a road piece.
`python3 lib/lane_profile.py` self-tests, same convention as `intersection_kit.py`/`lane_kit.py`.

WHAT THIS REPLACES, AND WHY. Until now a piece's cross-section was described by SCALARS spread
across the piece collection -- `rka_lanes`, `rka_lanes_backward`, `rka_lane_width`,
`rka_median_width`, `rka_sidewalk_l_width`, `rka_sidewalk_r_width`, plus an `_end` twin for each
of the last five -- and **every consumer re-derived geometry from them using its own convention**:

  * the pavement sweep treated the carriageway as CENTRED on the spine
    (`half_w = median_half + max(lanes, lanes_backward) * lane_width`, mirrored),
  * `build_segment_from_spine` places lanes EDGE-ANCHORED off the fwd/rev divide
    (`+0.5w, +1.5w, ...` forward, mirrored negative backward),
  * `ops_split.branch_offsets` assumed a CENTRED frame again when seeding a branch.

Three confirmed defects (2026-08, measured against `assets/world_source/island_v3_roads.blend`,
not read off the code) all trace to that one root cause: one-way pavement built double-width, the
gore seeded ~3.25 m off in a place the trunk has no lane, and -- once those two were fixed in
Phase 0 -- the remaining structural problem that a lane which EXISTS ON ONE END ONLY (a ramp
peeling off, an aux lane tapering in) is not expressible as a lane *count* at all, which is why
`ops_split.py` had to fake a merge out of five unrelated collections with no lane data.

THE FIX IS THE `id` FIELD. A profile is an ORDERED list of slots, each with a stable `id` that
survives across stations. A lane that tapers away is the SAME slot id at width `w` on one station
and `0.0` on the next -- so `interpolate()` alone subsumes all five `_end` scalar pairs, and a
branch declares which slot IDS it adopts instead of recomputing an offset with a second formula.
`slot_offset()` is the single owner of "where is slot i laterally", so the frame mismatch that
caused defect 3 cannot recur -- there is no second formula to disagree with.

SIGN CONVENTION -- read this before using any offset from here. Slots are ordered most-NEGATIVE
to most-POSITIVE along the signed lateral coordinate `s`, where `+s` is the direction
`intersection_kit.offset_spine_line(+x)` displaces (the FORWARD-lane side; also the side the
existing `sidewalk_l_width` / `curbs[0]` naming calls "L"). This is the DRIVING frame, and it is
deliberately NOT the same as `GN_RoadProfile`'s own profile-line frame -- those two are related by
a `traffic_side`-dependent flip that `intersection_kit.sweep_profile_fracs` owns. Keep that flip
at the consumer boundary; never bake it into a profile.

`anchor` says where `s = 0` sits, and making it EXPLICIT is what ends the centred-vs-edge-anchored
argument:

    'DIVIDE'  (default)  s=0 at the boundary between the REV block and the FWD block; if a MEDIAN
                         slot separates them, s=0 at that median's CENTRE. This reproduces the
                         existing `build_segment_from_spine` layout exactly, for one-way and
                         two-way alike -- it is the driving datum and the spine IS that line.
    'CENTER'             s=0 at the geometric middle of the total width.
    'LEFT'  / 'RIGHT'    s=0 at that outer edge (so every slot is on one side of the spine).
"""

TRAVEL = 'TRAVEL'
AUX = 'AUX'
SHOULDER = 'SHOULDER'
MEDIAN = 'MEDIAN'
SIDEWALK = 'SIDEWALK'
PARKING = 'PARKING'

FWD = 'FWD'
REV = 'REV'
NONE = 'NONE'

#: Slot kinds a vehicle may actually drive on -- the ones that become lanes in `.lanekit.json`.
DRIVABLE_KINDS = (TRAVEL, AUX)

#: `mark_left` values. Each is a column of the Phase-4 trim sheet, NOT generated geometry (see
#: the plan's "markings are texture" decision, and godot-road-generator's `LaneType` being "the UV
#: column of the material trimsheet to use for each lane").
MARK_NONE = 'NONE'
MARK_DASH_W = 'DASH_W'
MARK_SOLID_W = 'SOLID_W'
MARK_DASH_Y = 'DASH_Y'
MARK_SOLID_Y = 'SOLID_Y'
MARK_DOUBLE_Y = 'DOUBLE_Y'

ANCHOR_DIVIDE = 'DIVIDE'
ANCHOR_CENTER = 'CENTER'
ANCHOR_LEFT = 'LEFT'
ANCHOR_RIGHT = 'RIGHT'


class Slot(object):
    """One lateral band of the cross-section. `id` is the identity that survives across stations
    and across a split -- it is what makes "this lane becomes that branch's lane" expressible, so
    ids must be unique within a profile and STABLE (never renumber on rebuild)."""

    __slots__ = ("id", "kind", "width", "dir", "mark_left")

    def __init__(self, id, kind=TRAVEL, width=3.5, dir=None, mark_left=MARK_NONE):
        self.id = id
        self.kind = kind
        self.width = float(width)
        # A drivable slot with no explicit direction is forward; a median/sidewalk/shoulder has
        # none. Defaulting here keeps every construction site from repeating the same ternary.
        self.dir = (FWD if kind in DRIVABLE_KINDS else NONE) if dir is None else dir
        self.mark_left = mark_left

    def copy(self, **kw):
        d = dict(id=self.id, kind=self.kind, width=self.width, dir=self.dir,
                 mark_left=self.mark_left)
        d.update(kw)
        return Slot(**d)

    def is_drivable(self):
        return self.kind in DRIVABLE_KINDS

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "width": self.width, "dir": self.dir,
                "mark_left": self.mark_left}

    @staticmethod
    def from_dict(d):
        return Slot(d["id"], d.get("kind", TRAVEL), d.get("width", 3.5), d.get("dir"),
                    d.get("mark_left", MARK_NONE))

    def __repr__(self):
        return "Slot(%r, %s, %.2f, %s)" % (self.id, self.kind, self.width, self.dir)


class Profile(object):
    """An ordered cross-section: `slots` most-negative to most-positive in the driving frame,
    plus the `anchor` that fixes where `s = 0` is. See the module docstring for the sign rules."""

    __slots__ = ("slots", "anchor")

    def __init__(self, slots, anchor=ANCHOR_DIVIDE):
        self.slots = list(slots)
        self.anchor = anchor

    def copy(self):
        return Profile([s.copy() for s in self.slots], self.anchor)

    def index_of(self, slot_id):
        for i, s in enumerate(self.slots):
            if s.id == slot_id:
                return i
        return None

    def slot(self, slot_id):
        i = self.index_of(slot_id)
        return None if i is None else self.slots[i]

    def to_dict(self):
        return {"anchor": self.anchor, "slots": [s.to_dict() for s in self.slots]}

    @staticmethod
    def from_dict(d):
        return Profile([Slot.from_dict(s) for s in d.get("slots", ())],
                       d.get("anchor", ANCHOR_DIVIDE))

    def __repr__(self):
        return "Profile(%s, %r)" % (self.slots, self.anchor)


# --------------------------------------------------------------------------------------- geometry

def total_width(profile):
    return sum(s.width for s in profile.slots)


def _anchor_shift(profile):
    """Distance from the profile's own left edge to `s = 0`. Every offset in this module is
    `(cumulative width from the left edge) - _anchor_shift(profile)`, so this ONE function is the
    only place an anchor convention is interpreted."""
    if profile.anchor == ANCHOR_LEFT:
        return 0.0
    if profile.anchor == ANCHOR_RIGHT:
        return total_width(profile)
    if profile.anchor == ANCHOR_CENTER:
        return total_width(profile) / 2.0
    # ANCHOR_DIVIDE: s=0 is the LEFT EDGE OF THE FIRST FORWARD TRAVEL SLOT -- i.e. the driving
    # centreline, which is what the spine actually is. Everything to its left (reverse lanes, and
    # any shoulder/sidewalk/parking outboard of them) is negative.
    #
    # The one adjustment: when a MEDIAN sits immediately before that first forward slot AND both
    # directions genuinely exist, s=0 moves to the median's CENTRE -- because that is where the
    # legacy scalar model's datum sits (`carriageway_extents` adds `median_half` to BOTH extents,
    # not to one side). A median on a one-way road divides nothing and gets no such treatment; it
    # is simply paved surface on the negative side.
    #
    # NB the earlier version scanned left-to-right and stopped at the first slot that was not
    # reverse travel, which made a REVERSE-side SIDEWALK (the very first slot) collapse the datum
    # to the profile's outer edge. Anchor off the forward block instead -- it is the side that
    # defines the centreline, and it cannot be shadowed by a non-travel slot.
    i_fwd = None
    for i, s in enumerate(profile.slots):
        if s.is_drivable() and s.dir == FWD:
            i_fwd = i
            break
    if i_fwd is not None:
        run = sum(s.width for s in profile.slots[:i_fwd])
        prev = profile.slots[i_fwd - 1] if i_fwd > 0 else None
        if prev is not None and prev.kind == MEDIAN and _has_dir(profile, REV):
            return run - prev.width / 2.0
        return run
    # No forward lanes at all: a one-way road authored in the negative direction. The divide is
    # then the far edge of the last reverse lane (its own centreline side).
    i_rev = None
    for i, s in enumerate(profile.slots):
        if s.is_drivable() and s.dir == REV:
            i_rev = i
    if i_rev is not None:
        return sum(s.width for s in profile.slots[:i_rev + 1])
    return total_width(profile) / 2.0   # no travel lanes at all -- degenerate, centre it


def _has_dir(profile, d):
    return any(s.is_drivable() and s.dir == d for s in profile.slots)


def is_one_way(profile):
    """True when every drivable slot runs the same way. A profile with NO drivable slots at all
    (a pure median/sidewalk station) is not one-way; it is degenerate."""
    return _has_dir(profile, FWD) != _has_dir(profile, REV)


def slot_edges(profile, i):
    """`(near, far)` signed lateral coordinates of slot `i`'s two boundaries, `near < far`."""
    run = 0.0
    for j, s in enumerate(profile.slots):
        if j == i:
            shift = _anchor_shift(profile)
            return run - shift, run + s.width - shift
        run += s.width
    raise IndexError("slot index %r out of range (profile has %d slots)"
                     % (i, len(profile.slots)))


def slot_offset(profile, i):
    """Signed lateral coordinate of slot `i`'s CENTRE -- the single source of truth for lane
    centrelines, marking positions and branch seeding alike. Accepts an index or a slot id."""
    if not isinstance(i, int) or (isinstance(i, bool)):
        i = profile.index_of(i)
        if i is None:
            raise KeyError("no such slot id")
    lo, hi = slot_edges(profile, i)
    return (lo + hi) / 2.0


def extents(profile):
    """`(neg_extent, pos_extent)` -- both POSITIVE distances from `s = 0` out to each edge, the
    exact pair `intersection_kit.carriageway_extents` returns for the scalar model, and the pair
    `sweep_radius_and_shift` / `sweep_profile_fracs` consume. A one-way profile returns
    `(0.0, n*w)`, which is what makes the double-width defect unrepresentable here."""
    shift = _anchor_shift(profile)
    return shift, total_width(profile) - shift


def paved_extents(profile):
    """`(neg, pos)` of the DRIVEABLE + median surface only, excluding the sidewalk slots at either
    end -- what the asphalt sweep covers, as opposed to `extents()` which includes everything.
    Sidewalks ride their own modifier in the stack and must not widen the carriageway (that was
    the visible half of defect 2: the far curb and its sidewalk built out in the middle of
    nothing)."""
    lo, hi = None, None
    run = 0.0
    shift = _anchor_shift(profile)
    for s in profile.slots:
        if s.kind != SIDEWALK:
            if lo is None:
                lo = run
            hi = run + s.width
        run += s.width
    if lo is None:
        return 0.0, 0.0
    return shift - lo, hi - shift


def travel_lanes(profile):
    """Ordered drivable slots as `(slot, offset, dir, index_within_dir)`, where
    `index_within_dir` counts OUTWARD from the divide (0 = the lane nearest the centreline) --
    matching `intersection_kit.build_segment_from_spine`'s existing lane numbering, so exported
    lane ids do not renumber under the migration. Forward lanes are listed first, then reverse."""
    fwd, rev = [], []
    for i, s in enumerate(profile.slots):
        if not s.is_drivable():
            continue
        off = slot_offset(profile, i)
        (fwd if s.dir == FWD else rev).append((s, off))
    fwd.sort(key=lambda t: t[1])            # nearest the divide (smallest +s) first
    rev.sort(key=lambda t: -t[1])           # nearest the divide (largest -s, i.e. closest to 0)
    out = [(s, off, FWD, k) for k, (s, off) in enumerate(fwd)]
    out += [(s, off, REV, k) for k, (s, off) in enumerate(rev)]
    return out


# ------------------------------------------------------------------------------------ interpolate

def _merge_order(a_ids, b_ids):
    """Union of two id sequences preserving both relative orders -- the classic merge every
    station interpolation needs, because a slot may be present in only one station (that IS the
    taper) and must still land in the right lateral position."""
    out, bi = [], 0
    b_pos = {sid: i for i, sid in enumerate(b_ids)}
    for sid in a_ids:
        if sid in b_pos:
            # emit any b-only ids that come before this shared one
            while bi < b_pos[sid]:
                if b_ids[bi] not in out and b_ids[bi] not in a_ids:
                    out.append(b_ids[bi])
                bi += 1
            bi = b_pos[sid] + 1
        if sid not in out:
            out.append(sid)
    for sid in b_ids[bi:]:
        if sid not in out:
            out.append(sid)
    return out


def interpolate(p0, p1, t):
    """The cross-section at fraction `t` between two stations, by per-slot WIDTH lerp keyed on
    `id`. A slot missing from one station counts as width 0 there -- so a lane that appears
    (`0 -> w`) or drops (`w -> 0`) is an ordinary interpolation, not a special case, and this one
    function subsumes `lanes_end` / `lanes_backward_end` / `median_width_end` /
    `sidewalk_l_width_end` / `sidewalk_r_width_end` all at once.

    Non-width attributes (`kind`/`dir`/`mark_left`) are taken from the station where the slot is
    present, preferring `p0` -- they describe what a slot IS, and a slot does not change identity
    mid-taper."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    a = {s.id: s for s in p0.slots}
    b = {s.id: s for s in p1.slots}
    slots = []
    for sid in _merge_order([s.id for s in p0.slots], [s.id for s in p1.slots]):
        sa, sb = a.get(sid), b.get(sid)
        w0 = sa.width if sa is not None else 0.0
        w1 = sb.width if sb is not None else 0.0
        proto = sa if sa is not None else sb
        slots.append(proto.copy(width=w0 + (w1 - w0) * t))
    return Profile(slots, p0.anchor)


def stations_at(profiles, ts, t):
    """The cross-section at `t` for a piece described by N stations at parameters `ts` (ascending,
    normally `[0.0, ..., 1.0]`). Segments between stations interpolate; outside the range the end
    station holds. Multi-station is what lets ONE piece be `[trunk] -> [trunk + ramp@0] ->
    [trunk + ramp@full]`, i.e. the whole `trunk_before`/`trunk_taper`/`trunk_aux` trio collapsed
    into a single live-editable piece."""
    if not profiles:
        raise ValueError("no stations")
    if len(profiles) == 1:
        return profiles[0].copy()
    if t <= ts[0]:
        return profiles[0].copy()
    if t >= ts[-1]:
        return profiles[-1].copy()
    for i in range(len(ts) - 1):
        if ts[i] <= t <= ts[i + 1]:
            span = ts[i + 1] - ts[i]
            local = 0.0 if span <= 0.0 else (t - ts[i]) / span
            return interpolate(profiles[i], profiles[i + 1], local)
    return profiles[-1].copy()


class ProfileSet(object):
    """A piece's whole cross-section description: N stations at parameters `ts` (ascending along
    the spine, normally starting at 0.0 and ending at 1.0), each with its own `Profile`.

    ONE station is an ordinary constant-width road. TWO is the classic taper (and replaces every
    `_end` scalar). THREE is a split/merge: `[trunk] -> [trunk + ramp@0] -> [trunk + ramp@full]`,
    which is the whole reason `ops_split.py` needed five separate collections -- as a ProfileSet
    it is ONE live-editable piece and the gore is just the middle station.

    This is also the serialization unit: `to_dict`/`from_dict` are plain JSON-safe nested
    dict/list, which Blender stores natively as a Collection custom property (verified: ragged
    lists of dicts round-trip), so `rka_profile` is hand-editable in the Custom Properties panel
    exactly like `rka_lane_map` already is."""

    __slots__ = ("stations", "profiles")

    def __init__(self, profiles, stations=None):
        self.profiles = list(profiles)
        if stations is not None:
            self.stations = [float(t) for t in stations]
        elif len(self.profiles) == 1:
            self.stations = [0.0]
        else:
            n = len(self.profiles) - 1
            self.stations = [i / float(n) for i in range(len(self.profiles))]
        if len(self.stations) != len(self.profiles):
            raise ValueError("%d stations for %d profiles"
                             % (len(self.stations), len(self.profiles)))

    def at(self, t):
        return stations_at(self.profiles, self.stations, t)

    def slot_ids(self):
        """Every slot id appearing at any station, in lateral order -- the set a branch may adopt
        and the set the per-vertex width attributes are keyed on."""
        ids = []
        for p in self.profiles:
            ids = _merge_order(ids, [s.id for s in p.slots])
        return ids

    def sample(self, n):
        """`[Profile]` at `n` EVENLY SPACED parameters. Correct only when the spine's control
        points are themselves evenly spaced -- prefer `sample_at` with the spine's real arc-length
        fractions whenever the spine is available."""
        if n <= 1:
            return [self.at(0.0)]
        return [self.at(i / float(n - 1)) for i in range(n)]

    def sample_at(self, fractions):
        """`[Profile]` at explicit parameters -- normally `intersection_kit.arc_length_fractions`
        of the spine, so each control point gets the cross-section that belongs at ITS OWN
        distance along the road.

        This matters as soon as a piece has a taper: a split's trunk gains control points exactly
        at the taper's start and end, which makes the point spacing deliberately uneven (e.g.
        0/200/400/450/510/600 m). Sampling that by list position would read the profile at
        0/20/40/60/80/100% of the LIST while the points sit at 0/33/67/75/85/100% of the LENGTH --
        sliding the auxiliary lane's opening hundreds of metres up the road."""
        return [self.at(t) for t in fractions]

    def to_dict(self):
        return {"stations": list(self.stations),
                "slots": [[s.to_dict() for s in p.slots] for p in self.profiles],
                "anchor": self.profiles[0].anchor if self.profiles else ANCHOR_DIVIDE}

    @staticmethod
    def from_dict(d):
        anchor = d.get("anchor", ANCHOR_DIVIDE)
        profiles = [Profile([Slot.from_dict(s) for s in station], anchor)
                    for station in d.get("slots", ())]
        return ProfileSet(profiles, d.get("stations"))

    def __repr__(self):
        return "ProfileSet(%d stations)" % len(self.profiles)


# --------------------------------------------------------------------------------------- migration

def profile_from_scalars(lanes, lanes_backward, lane_width, median_width=0.0,
                         sidewalk_l_width=0.0, sidewalk_r_width=0.0, id_prefix=""):
    """The migration bridge: build the profile equivalent to the legacy scalar description, laid
    out exactly the way `intersection_kit.build_segment_from_spine` already places things, so a
    piece that has never been re-authored produces byte-identical geometry the first time it is
    read through `custom_props.read_profile`.

    Naming mirrors the existing convention (see `build_segment_from_spine`): the `+s` side carries
    the FORWARD lanes and is the side called "L" by `sidewalk_l_width`/`curbs[0]`; `-s` carries
    the backward lanes and is "R". Slot ids are `<prefix>F0..`, `<prefix>R0..` counting OUTWARD
    from the divide, matching `travel_lanes`' `index_within_dir`, so the ids line up with exported
    lane numbering with no translation table.

    A median is only inserted when BOTH directions carry lanes -- the same condition the scalar
    callers already apply before adding `median_half` to the extents."""
    lanes = int(lanes or 0)
    lanes_backward = int(lanes_backward or 0)
    slots = []
    if sidewalk_r_width > 0.0:
        slots.append(Slot(id_prefix + "SW_R", SIDEWALK, sidewalk_r_width, NONE))
    # Reverse lanes, outermost first (so the list stays ordered -s -> +s).
    #
    # `mark_left` is the line on a slot's LOW-`s` edge, and the reverse block runs outward-to-
    # inward, so the test is "am I the OUTERMOST lane" (my low edge is the road's edge -- a curb,
    # not a painted line), NOT "am I lane 0". Writing it as `k > 0` inverted the block at both
    # ends: it painted a line along the outside of the road and left the genuine R1|R0 boundary
    # bare. Invisible until `marking_runs` became the thing that reads these, which is exactly
    # when it was caught.
    for k in range(lanes_backward - 1, -1, -1):
        slots.append(Slot(id_prefix + "R%d" % k, TRAVEL, lane_width, REV,
                          MARK_NONE if k == lanes_backward - 1 else MARK_DASH_W))
    if median_width > 0.0 and lanes > 0 and lanes_backward > 0:
        # UNPAINTED (`MARK_NONE`), because a median with real width IS the separator -- painting a
        # solid yellow along its low edge draws a line through, or under, the physical island. That
        # was a real user report ("a solid yellow line painted straight through a raised median"),
        # fixed on the scalar path by `build_segment_lane_markings`'s `median_half_*` suppression;
        # this slot carried `MARK_SOLID_Y` and so reintroduced exactly that line the moment the
        # profile model became what markings are read from. Note the F0 slot below already agrees:
        # its double-yellow is gated on there being NO median, precisely because the median takes
        # over the dividing job when one exists.
        slots.append(Slot(id_prefix + "MED", MEDIAN, median_width, NONE, MARK_NONE))
    for k in range(lanes):
        slots.append(Slot(id_prefix + "F%d" % k, TRAVEL, lane_width, FWD,
                          MARK_DOUBLE_Y if (k == 0 and lanes_backward > 0 and median_width <= 0.0)
                          else (MARK_NONE if k == 0 else MARK_DASH_W)))
    if sidewalk_l_width > 0.0:
        slots.append(Slot(id_prefix + "SW_L", SIDEWALK, sidewalk_l_width, NONE))
    return Profile(slots, ANCHOR_DIVIDE)



def self_test():
    W = 3.5

    # ---------------------------------------------------------------- the defect-2 case, directly
    ow = profile_from_scalars(3, 0, W)
    assert extents(ow) == (0.0, 3 * W), \
        "a one-way 3-lane road must reach 0 m on the empty side and 10.5 m on the lane side -- " \
        "the old scalar model mirrored it to 10.5/10.5 (21 m of asphalt for 10.5 m of lanes)"
    assert abs(total_width(ow) - 10.5) < 1e-9
    offs = [slot_offset(ow, i) for i in range(len(ow.slots))]
    assert [round(o, 4) for o in offs] == [1.75, 5.25, 8.75], \
        "one-way lane centres must be edge-anchored off the divide, matching " \
        "build_segment_from_spine (+0.5w, +1.5w, +2.5w), got %r" % offs
    print("OK: one-way profile -- extents (0.0, 10.5), lane centres +1.75/+5.25/+8.75")

    # --------------------------------------------------------------------- symmetric is unchanged
    sym = profile_from_scalars(2, 2, W)
    assert extents(sym) == (2 * W, 2 * W)
    assert [round(slot_offset(sym, i), 4) for i in range(4)] == [-5.25, -1.75, 1.75, 5.25]
    lanes = travel_lanes(sym)
    assert [(s.id, d, k) for s, _o, d, k in lanes] == \
        [("F0", FWD, 0), ("F1", FWD, 1), ("R0", REV, 0), ("R1", REV, 1)], \
        "lane index must count OUTWARD from the divide in each direction, got %r" % (lanes,)
    assert [round(o, 4) for _s, o, _d, _k in lanes] == [1.75, 5.25, -1.75, -5.25]
    print("OK: symmetric 2+2 -- extents/offsets/lane numbering match the legacy layout exactly")

    # ------------------------------------------------------------------------- asymmetric two-way
    asym = profile_from_scalars(3, 2, W)
    assert extents(asym) == (2 * W, 3 * W), \
        "each edge must move by its OWN direction's lane count"
    print("OK: asymmetric 3fwd/2rev -- extents (7.0, 10.5)")

    # --------------------------------------------------------- median: s=0 at the median's centre
    med = profile_from_scalars(2, 2, W, median_width=2.0)
    assert extents(med) == (1.0 + 2 * W, 1.0 + 2 * W), \
        "median_half must be added to BOTH extents, as carriageway_extents does"
    assert abs(slot_offset(med, med.index_of("MED"))) < 1e-9, "median centre IS the datum"
    assert round(slot_offset(med, "F0"), 4) == 1.0 + W / 2.0
    # ...and a median on a ONE-WAY road is NOT a divide (there is nothing to divide): it is just
    # paved surface on the negative side, so it must NOT pull s=0 into its own centre.
    ow_med = Profile([Slot("MED", MEDIAN, 2.0, NONE), Slot("F0", TRAVEL, W, FWD)])
    assert extents(ow_med) == (2.0, W), \
        "with no reverse lanes s=0 stays on the forward lane's own edge; the median is simply " \
        "2 m of surface to its left, got %r" % (extents(ow_med),)
    # a REVERSE-side sidewalk must not shadow the datum (the bug the first _anchor_shift had)
    sw_first = profile_from_scalars(1, 1, W, sidewalk_r_width=2.0)
    assert extents(sw_first) == (2.0 + W, W), \
        "a sidewalk outboard of the reverse lane must not collapse the divide to the outer edge"
    print("OK: median anchors s=0 at its own centre when it genuinely divides two directions")

    # -------------------------------------------------------------- sidewalks widen, but not asphalt
    with_sw = profile_from_scalars(2, 2, W, sidewalk_l_width=3.0, sidewalk_r_width=1.0)
    assert extents(with_sw) == (1.0 + 2 * W, 3.0 + 2 * W)
    assert paved_extents(with_sw) == (2 * W, 2 * W), \
        "sidewalks must NOT widen the carriageway sweep -- that is the visible half of defect 2"
    l_off = slot_offset(with_sw, "SW_L")
    r_off = slot_offset(with_sw, "SW_R")
    assert l_off > 0 > r_off, "sidewalk_l is the +s (forward-lane) side, matching sidewalk_l_width"
    print("OK: sidewalks sit outside the paved extents and on the sides their legacy names imply")

    # ------------------------------------------------------- the taper: one mechanism, five scalars
    a = profile_from_scalars(2, 0, W)
    b = profile_from_scalars(3, 0, W)
    mid = interpolate(a, b, 0.5)
    assert round(mid.slot("F2").width, 4) == W / 2.0, \
        "a slot absent from station A must lerp from ZERO -- that IS the lane-add taper"
    assert round(total_width(mid), 4) == round(2 * W + W / 2.0, 4)
    assert round(slot_offset(mid, "F0"), 4) == round(W / 2.0, 4), \
        "the lanes that persist must NOT move while a lane grows outboard of them"
    assert interpolate(a, b, 0.0).slot("F2").width == 0.0
    assert round(interpolate(a, b, 1.0).slot("F2").width, 4) == W
    # a DROP is the same call with the stations swapped -- no separate code path
    assert round(interpolate(b, a, 0.5).slot("F2").width, 4) == W / 2.0
    print("OK: interpolate() expresses lane add AND drop as a plain width lerp on a stable id")

    # ------------------------------------------------ a mid-profile slot keeps its lateral place
    p_in = Profile([Slot("R0", TRAVEL, W, REV), Slot("F0", TRAVEL, W, FWD)])
    p_out = Profile([Slot("R0", TRAVEL, W, REV), Slot("MED", MEDIAN, 2.0, NONE),
                     Slot("F0", TRAVEL, W, FWD)])
    m = interpolate(p_in, p_out, 0.5)
    assert [s.id for s in m.slots] == ["R0", "MED", "F0"], \
        "a slot present in only one station must be merged at its own lateral position, got %r" \
        % [s.id for s in m.slots]
    assert round(m.slot("MED").width, 4) == 1.0
    print("OK: _merge_order places a station-only slot at the correct lateral position")

    # ------------------------------------------------------------------- multi-station (the split)
    st0 = profile_from_scalars(3, 0, W)                       # trunk alone
    st1 = interpolate(st0, st0, 0.0)
    st1.slots.append(Slot("RAMP", AUX, 0.0, FWD))             # ramp appears at zero width
    st2 = st1.copy()
    st2.slot("RAMP").width = W                                # ...and opens to full width
    ts = [0.0, 0.4, 1.0]
    at0 = stations_at([st0, st1, st2], ts, 0.0)
    at_mid = stations_at([st0, st1, st2], ts, 0.7)
    at_end = stations_at([st0, st1, st2], ts, 1.0)
    assert at0.slot("RAMP") is None or at0.slot("RAMP").width == 0.0
    assert round(at_mid.slot("RAMP").width, 4) == round(W * 0.5, 4), \
        "0.7 is halfway between stations 0.4 and 1.0 -> half the ramp width, got %r" \
        % at_mid.slot("RAMP").width
    assert round(at_end.slot("RAMP").width, 4) == W
    assert round(slot_offset(at_end, "RAMP"), 4) == round(3 * W + W / 2.0, 4), \
        "the ramp opens OUTBOARD of the trunk lanes and must not displace them"
    assert [round(slot_offset(at_end, i), 4) for i in range(3)] == [1.75, 5.25, 8.75]
    print("OK: stations_at -- one piece carries trunk -> gore -> trunk+ramp, trunk lanes fixed")

    # ------------------------------------------------------------------------- anchor conventions
    p = profile_from_scalars(2, 2, W)
    p_c = Profile(p.slots, ANCHOR_CENTER)
    assert extents(p_c) == (2 * W, 2 * W), "symmetric: CENTER and DIVIDE coincide"
    p_l = Profile(p.slots, ANCHOR_LEFT)
    assert extents(p_l) == (0.0, 4 * W)
    p_r = Profile(p.slots, ANCHOR_RIGHT)
    assert extents(p_r) == (4 * W, 0.0)
    ow_c = Profile(ow.slots, ANCHOR_CENTER)
    assert extents(ow_c) == (1.5 * W, 1.5 * W), \
        "CENTER on a one-way road is exactly the OLD (wrong) mirrored frame -- keeping it " \
        "available and NAMED is the point: the bug was that it was implicit"
    print("OK: all four anchors resolve, and the legacy mirrored frame is now an explicit name")

    # ------------------------------------------------------------------------------- ProfileSet
    ps = ProfileSet([st0, st1, st2], ts)
    assert ps.stations == [0.0, 0.4, 1.0]
    assert round(ps.at(0.7).slot("RAMP").width, 4) == round(W * 0.5, 4)
    assert ps.slot_ids() == ["F0", "F1", "F2", "RAMP"], \
        "slot_ids must union every station in lateral order, got %r" % ps.slot_ids()
    samp = ps.sample(5)                       # t = 0, .25, .5, .75, 1
    assert len(samp) == 5
    widths = [round((p.slot("RAMP").width if p.slot("RAMP") else 0.0), 4) for p in samp]
    assert widths[0] == 0.0 and widths[-1] == W, widths
    assert widths == sorted(widths), \
        "sampling a ramp-open ProfileSet must give a MONOTONIC width ramp, got %r" % widths
    # default stations are evenly spaced; a single-station set is a constant-width road
    assert ProfileSet([st0, st2]).stations == [0.0, 1.0]
    assert ProfileSet([st0]).stations == [0.0] and ProfileSet([st0]).at(0.5).slot("F2") is not None
    rt = ProfileSet.from_dict(ps.to_dict())
    assert rt.stations == ps.stations
    assert [[s.to_dict() for s in p.slots] for p in rt.profiles] == \
           [[s.to_dict() for s in p.slots] for p in ps.profiles]
    print("OK: ProfileSet -- 3-station split samples a monotonic ramp and round-trips exactly")

    # ------------------------------------------------------------------------ round-trip + inverse
    rt = Profile.from_dict(with_sw.to_dict())
    assert [s.to_dict() for s in rt.slots] == [s.to_dict() for s in with_sw.slots]
    assert rt.anchor == with_sw.anchor
    print("OK: dict round-trip is exact")

    # ------------------------------------------------------------------- profile-driven markings
    # The exact cross-section of `IC_YAMATE_split_mainline_001`: two mainline lanes, a painted
    # nose, and an auxiliary exit lane -- both of the last two opening partway along.
    def _yamate(nose, aux):
        return Profile([Slot("B0", TRAVEL, 3.5, FWD, MARK_NONE),
                        Slot("B1", TRAVEL, 3.5, FWD, MARK_DASH_W),
                        Slot("GORE", SHOULDER, nose, NONE, MARK_SOLID_W),
                        Slot("A0", AUX, aux, FWD, MARK_DASH_W)], ANCHOR_DIVIDE)
    yam = ProfileSet([_yamate(0.0, 0.0), _yamate(0.0, 3.5), _yamate(3.0, 3.5)], [0.0, 0.6, 1.0])
    mk = {m["slot_id"]: m for m in marking_runs(yam, 11)}
    assert set(mk) == {"B1", "GORE", "A0"}, \
        "every slot carrying a mark_left and separating two pieces of road must yield a run; " \
        "B0's edge is the road's outer edge and must NOT, got %s" % sorted(mk)
    assert mk["B1"]["i0"] == 0 and mk["B1"]["i1"] == 10, \
        "the mainline's own lane line runs the WHOLE piece"
    assert abs(mk["B1"]["offsets"][0] - 3.5) < 1e-9, "B0|B1 boundary sits one lane out"
    assert mk["A0"]["i0"] > 0, \
        "the exit lane's line must not start until the lane does -- this is the case the scalar " \
        "builder could not express at all (it emitted ONE line for this whole cross-section)"
    assert mk["GORE"]["i0"] > mk["A0"]["i0"], \
        "the painted nose's edge appears LATER than the exit lane's -- the lane runs flush first"
    # the nose's line moves outward with the lanes it separates, it is not a fixed offset
    assert mk["A0"]["offsets"][-1] > mk["A0"]["offsets"][mk["A0"]["i0"]] - 1e-9
    # a plain two-way street still yields exactly the legacy set: one line per internal boundary
    plain = ProfileSet([profile_from_scalars(2, 2, W)])
    ids = sorted(m["slot_id"] for m in marking_runs(plain, 5))
    assert ids == ["F0", "F1", "R0"], \
        "a 2+2 street marks the centre plus each direction's internal boundary, got %r" % ids
    print("OK: marking_runs -- a boundary is a slot property, so a line that opens with a ramp "
          "or with a gore is expressible; outer edges are never painted")

    # --------------------------------------------------- extents agree with intersection_kit's pair
    try:
        import intersection_kit as ik
        for lanes, back, med in ((3, 0, 0.0), (2, 2, 0.0), (3, 2, 0.0), (2, 2, 2.0)):
            pr = profile_from_scalars(lanes, back, W, med)
            mine = extents(pr)
            theirs = ik.carriageway_extents(lanes, back, W,
                                            med / 2.0 if (lanes and back) else 0.0)
            assert mine == theirs, \
                "lane_profile.extents and intersection_kit.carriageway_extents MUST agree for " \
                "every scalar case or the migration silently moves geometry: %r vs %r" \
                % (mine, theirs)
        print("OK: extents() matches intersection_kit.carriageway_extents on every scalar case")
    except ImportError:
        print("SKIP: intersection_kit not importable from here (cross-check skipped)")

    # ------------------------------------------------------------------- lane_runs / export
    # The case the scalar exporter structurally could not describe: a lane that does not exist at
    # the start of the piece and opens partway along it.
    runs = lane_runs(ps, 5)                       # ps = trunk(3) + RAMP opening from t=0.4
    by_id = {r["slot_id"]: r for r in runs}
    assert set(by_id) == {"F0", "F1", "F2", "RAMP"}, sorted(by_id)
    assert by_id["F0"]["i0"] == 0 and by_id["F0"]["i1"] == 4, by_id["F0"]
    assert by_id["RAMP"]["i0"] > 0, \
        "the ramp must START PARTWAY along the piece -- i0=0 means the run range is being " \
        "ignored, which is exactly what forced a split into separate pieces"
    assert by_id["RAMP"]["i1"] == 4
    spine5 = [(x, 0.0, 0.0) for x in (0.0, 30.0, 60.0, 90.0, 120.0)]
    d = export_segment_from_profile_dict(spine5, ps, segment_id="SP", godot_space=False)
    lanes_by = {l["slot_id"]: l for l in d["lanes"]}
    assert len(lanes_by["F0"]["points"]) == 5, "a full-length lane spans every station"
    assert len(lanes_by["RAMP"]["points"]) < 5, \
        "the ramp lane must be SHORTER than the piece -- it starts where it opens"
    assert all(abs(p[1] - 1.75) < 1e-9 for p in lanes_by["F0"]["points"]), \
        "F0 must not move while the ramp opens outboard of it"
    ramp_y = lanes_by["RAMP"]["points"][-1][1]
    assert abs(ramp_y - (3 * W + W / 2.0)) < 1e-9, \
        "the ramp centreline sits outboard of the three trunk lanes, got %r" % ramp_y
    # a slot that never gains width is not a lane at all
    ghost = ProfileSet([Profile([Slot("F0", TRAVEL, W, FWD), Slot("GHOST", AUX, 0.0, FWD)])])
    assert [r["slot_id"] for r in lane_runs(ghost, 3)] == ["F0"]
    # ...and a non-drivable slot (median, sidewalk, gore nose) is never exported as a lane
    withmed = ProfileSet([profile_from_scalars(2, 2, W, 2.0, 3.0, 1.0)])
    assert all(r["kind"] in (TRAVEL, AUX) for r in lane_runs(withmed, 3))
    assert len(lane_runs(withmed, 3)) == 4, "4 travel lanes, median+2 sidewalks excluded"
    print("OK: lane_runs/export -- a mid-piece lane gets a SHORT run, ghosts and non-drivable "
          "slots are excluded, and persisting lanes do not move")

    print("ALL SELF-TESTS PASSED")



# ------------------------------------------------------------------------------- lane export

LANE_EPS = 1e-4

#: The narrowest a DRIVABLE slot may be and still be exported as a lane. `LANE_EPS` (0.1 mm) is a
#: float-noise threshold and is right for asking "does this slot exist at all" -- it is badly wrong
#: for asking "is this a lane", and `lane_runs` was using it for both.
#:
#: What that cost, measured 2026-08-15 on the island: an expressway exit lane tapers to nothing
#: just past its gore, so its last live station was a 2 MILLIMETRE sliver. A sliver still has a
#: centreline, and the offset swings hard across the road as the slot collapses -- so the exported
#: lane's final vertex sat 4.7 m sideways of the road, and every consumer that takes an END TANGENT
#: from the last span read the taper instead of the road. `lane_joints` duly reported the mainline
#: meeting its own ramp at 86 degrees, which is not a thing that was wrong with the ramp.
#:
#: 0.5 m: narrower than any lane, aux lane or shoulder anyone would author, far wider than any
#: taper tail. A slot that never exceeds it is not exported as a lane at all -- correctly, since
#: nothing can drive down it.
LANE_MIN_WIDTH = 0.5


def lane_runs(profile_set, n_points, fractions=None):
    """Every drivable slot's life along the piece, as
    `[{"slot_id", "dir", "i0", "i1", "offsets", "widths"}, ...]`.

    `i0..i1` is the CONTIGUOUS index range over `n_points` stations where the slot is wider than
    `LANE_EPS` -- i.e. where the lane physically exists. A slot that is zero-width at the start and
    opens partway (a ramp, an auxiliary lane) yields `i0 > 0`; one that tapers out yields
    `i1 < n_points - 1`. **That range is the entire point of this function**: the old scalar export
    could only say "this piece has N lanes for its whole length", so a lane that appeared partway
    had to become its own piece, and the pieces either side had no lane data joining them. Here it
    is one slot with a start index.

    Slots that never reach a usable width anywhere are dropped entirely (a placeholder that stays
    at 0 is not a lane). A slot that switches on, off and on again is NOT modelled -- the run is
    first-to-last nonzero, which is the physically meaningful case; a lane does not blink."""
    stations = (profile_set.sample_at(fractions) if fractions is not None
                else profile_set.sample(n_points))
    runs = []
    for slot_id in profile_set.slot_ids():
        widths, offsets = [], []
        for prof in stations:
            s = prof.slot(slot_id)
            widths.append(s.width if s is not None else 0.0)
            offsets.append(slot_offset(prof, prof.index_of(slot_id))
                           if s is not None else 0.0)
        # Trimmed at a DRIVABLE width, not at float noise -- see `LANE_MIN_WIDTH` for the 4.7 m
        # phantom vertex this was producing at every expressway gore.
        live = [i for i, w in enumerate(widths) if w > LANE_MIN_WIDTH]
        if not live:
            continue
        proto = next((p.slot(slot_id) for p in stations if p.slot(slot_id) is not None), None)
        if proto is None or not proto.is_drivable():
            continue
        i0, i1 = live[0], live[-1]
        # A lane that opens partway starts at the station where it first has width, but its
        # OFFSET at the stations before that is meaningless (the slot has no extent there), so
        # carry the first live offset backwards -- this only affects a caller that samples outside
        # the run, and keeps the sequence monotone for anything that interpolates it.
        for i in range(i0):
            offsets[i] = offsets[i0]
        for i in range(i1 + 1, len(offsets)):
            offsets[i] = offsets[i1]
        runs.append({"slot_id": slot_id, "dir": proto.dir, "kind": proto.kind,
                     "i0": i0, "i1": i1, "offsets": offsets, "widths": widths})
    return runs


def marking_runs(profile_set, n_points, fractions=None):
    """Every painted lane BOUNDARY's life along the piece, as
    `[{"slot_id", "mark", "i0", "i1", "offsets"}, ...]` -- the marking counterpart of `lane_runs`,
    and the reason it has to exist at all.

    WHAT IT REPLACES. `intersection_kit.build_segment_lane_markings` derives boundaries from the
    SCALARS `lanes`/`lanes_backward`: one solid line at the fwd/rev divide, one dashed line at
    each internal boundary of each direction's block. That is correct only for a piece whose
    cross-section is one constant lane count. On anything the profile model exists for it is
    simply blind -- measured on `IC_YAMATE_split_mainline_001` (2 mainline lanes + an auxiliary
    exit lane + a gore), it emitted exactly ONE dashed line, at the B0|B1 boundary, and nothing at
    all for the exit lane or the painted nose. The boundaries it could not see are precisely the
    ones an interchange is made of.

    Here a boundary is a SLOT PROPERTY (`Slot.mark_left`, the line along that slot's low-`s` edge)
    sampled per station, so a line that appears when a lane opens, moves outward as a median
    widens, or ends when a ramp departs is the same mechanism as the lane itself -- and the marking
    type is authored per slot rather than inferred from counts.

    A boundary is only PRESENT where it genuinely separates two pieces of road: the slot itself
    must have width, and so must whatever is immediately inboard of it. That is what stops a line
    being painted along the outer edge of the road (nothing on the far side of it) and what makes
    the gore's solid edge appear exactly when the nose does.

    Like `lane_runs`, the run is first-to-last present; a boundary does not blink."""
    stations = (profile_set.sample_at(fractions) if fractions is not None
                else profile_set.sample(n_points))
    runs = []
    for slot_id in profile_set.slot_ids():
        proto = next((p.slot(slot_id) for p in stations if p.slot(slot_id) is not None), None)
        if proto is None or proto.mark_left == MARK_NONE:
            continue
        offsets, present = [], []
        for prof in stations:
            i = prof.index_of(slot_id)
            s = prof.slots[i] if i is not None else None
            if s is None:
                offsets.append(0.0)
                present.append(False)
                continue
            lo, _hi = slot_edges(prof, i)
            offsets.append(lo)
            # Something must exist on BOTH sides of the line, or it is the road's outer edge.
            inboard = sum(x.width for x in prof.slots[:i])
            present.append(s.width > LANE_EPS and inboard > LANE_EPS)
        live = [i for i, ok in enumerate(present) if ok]
        if not live:
            continue
        i0, i1 = live[0], live[-1]
        for i in range(i0):
            offsets[i] = offsets[i0]
        for i in range(i1 + 1, len(offsets)):
            offsets[i] = offsets[i1]
        runs.append({"slot_id": slot_id, "mark": proto.mark_left,
                     "i0": i0, "i1": i1, "offsets": offsets})
    return runs


def lane_neighbors(runs):
    """For each drivable run, which run you can CHANGE LANE into, as
    `{slot_id: {"in": slot_id|None, "out": slot_id|None}}`.

    WHY THE GRAPH NEEDS THIS. Longitudinal successors alone cannot describe an interchange. An
    auxiliary/exit lane BEGINS in the middle of the carriageway -- it has nothing upstream to
    connect to, which is why `save_lane_kit`'s lint correctly reports its free end as ISOLATED.
    A car reaches it by moving sideways, not by following a route. So an AI asked to "take the
    next exit" (or to cut off a target that is taking it) needs to know which lane is beside it,
    not only which lane is ahead.

    "IN" and "OUT" rather than "left" and "right" on purpose: in/out is measured against the
    driving divide (`|s|` decreasing / increasing) and is therefore the same answer whichever side
    of the road the world drives on, whereas left/right flips with `traffic_side` and would need a
    second sign convention -- the exact class of thing that caused the defects this redesign
    exists to remove. OUT is always toward the road's edge, which is where an exit ramp is.

    Adjacency requires the two runs to be in the SAME direction and to actually overlap in
    stations -- you cannot change into a lane that does not exist beside you yet."""
    out = {}
    for direction in (FWD, REV):
        same = [r for r in runs if r["dir"] == direction]
        # order by |offset| ascending == inner (nearest the divide) first, for both directions
        same.sort(key=lambda r: abs(r["offsets"][max(r["i0"], 0)]))
        def overlaps(a, b):
            return min(a["i1"], b["i1"]) >= max(a["i0"], b["i0"])

        for k, r in enumerate(same):
            nb = {"in": None, "out": None}
            # SCAN OUTWARD for the nearest lane on each side that actually exists beside this one,
            # rather than taking only the immediately-adjacent entry in the sorted list.
            #
            # Several auxiliary lanes on one carriageway occupy the SAME lateral position at
            # DIFFERENT stations -- six exit lanes on a ring, each open for a few hundred metres
            # around its own interchange. Sorted by offset they land next to each other, so the
            # k+-1 test made each one's neighbour the next AUXILIARY lane (which never overlaps it
            # in stations, so the answer came back None) instead of the travel lane they all
            # actually sit beside. Measured: of six exit lanes on LOOP_A exactly one was linked to
            # B1, and the other five were unreachable -- an exit lane with no way in.
            for step, key in ((-1, "in"), (1, "out")):
                j = k + step
                while 0 <= j < len(same):
                    if overlaps(r, same[j]):
                        nb[key] = same[j]["slot_id"]
                        break
                    j += step
            out[r["slot_id"]] = nb
    return out


def export_segment_from_profile_dict(spine, profile_set, segment_id="SEG", traffic_side='LEFT',
                                     godot_space=True):
    """`{"segment_id", "lanes": [...]}` for a spine whose cross-section is a `ProfileSet` --
    the profile-aware counterpart of `intersection_kit.export_segment_from_spine_dict`, and the
    same output shape, so `lane_kit.combine_pieces` / `WorldBaker` need no change at all.

    Each lane is emitted only over the stations where its slot actually has width, using
    `intersection_kit.offset_spine_line_varying` so its centreline follows a per-point offset --
    a lane keeps its true position even while its neighbours change width around it.

    REVERSE lanes are emitted in reversed point order, matching
    `build_segment_from_spine`'s convention that a lane's points run in its own direction of
    travel (which is what makes the runtime's endpoint-proximity joining work at all)."""
    import intersection_kit as ik
    n = len(spine)
    fractions = ik.arc_length_fractions(spine)
    pts_out = ((lambda p: [p[0], p[2], -p[1]]) if godot_space
               else (lambda p: [p[0], p[1], p[2]]))
    lanes_out = []
    runs = lane_runs(profile_set, n, fractions=fractions)
    nbrs = lane_neighbors(runs)
    for run in runs:
        line = ik.offset_spine_line_varying(spine, run["offsets"], traffic_side)
        seg_pts = line[run["i0"]:run["i1"] + 1]
        if len(seg_pts) < 2:
            continue
        if run["dir"] == REV:
            seg_pts = list(reversed(seg_pts))
        lane_id = "%s_%s" % (segment_id, run["slot_id"])
        # WIDTH AT EACH END, so `lane_joints` can derive the lane's ribbon EDGES and check that a
        # claimed connection actually lines up rather than merely touching. Taken at the run's own
        # first/last station (`i0`/`i1`), not the piece's, because a lane that tapers in partway
        # along is full width where it starts, not zero. Reported in the lane's own travel
        # direction, so a REV lane -- whose points were reversed just above -- reports the ends
        # swapped to match.
        w0, w1 = run["widths"][run["i0"]], run["widths"][run["i1"]]
        if run["dir"] == REV:
            w0, w1 = w1, w0
        lanes_out.append({"id": lane_id, "from_arm": "A", "to_arm": "B",
                          "lane_index": 0, "lane_index_out": 0, "kind": "segment",
                          "turn": "S", "oneway": True, "loop": False,
                          "slot_id": run["slot_id"], "slot_kind": run["kind"],
                          "width_start": w0, "width_end": w1,
                          "neighbor_in": nbrs.get(run["slot_id"], {}).get("in"),
                          "neighbor_out": nbrs.get(run["slot_id"], {}).get("out"),
                          "points": [pts_out(p) for p in seg_pts]})
    return {"segment_id": segment_id, "lanes": lanes_out}


if __name__ == "__main__":
    self_test()
