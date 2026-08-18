"""lane_joints.py -- pure-Python (no bpy), self-tested. Is a claimed lane connection REAL?
`python3 lib/lane_joints.py` self-tests, same convention as `lane_profile.py`/`lane_kit.py`.

TOUCHING IS NOT CONNECTING. A link that says "lane A continues into lane B" is a promise about
geometry, and until now nothing checked it. Two lanes whose centrelines end within a metre of each
other look joined in the viewport and drive like a pothole: a car crossing the boundary jumps
sideways, or clips a curb that only exists on one side of the seam. The gate could already tell you
a link EXISTED; it could not tell you the link was true.

WHAT "FULLY ALIGNED" MEANS, and why it is one check and not three. A lane is a ribbon, so the
honest test is on its EDGES, not its centreline: the outgoing lane's left edge must land on the
incoming lane's left edge, and likewise right. That single test subsumes everything people
otherwise check separately --

    centrelines coincide?   both edges move together if the centre is off
    same width?             a width mismatch separates one or both edges
    same heading?           a heading mismatch rotates the cross-section, so the edges splay
                            apart even when the centres touch exactly

-- which is exactly the point. "The centres are 2 cm apart and the headings differ by 4 degrees"
is two numbers nobody can act on; "the left edges are 31 cm apart" is one number that says how bad
the seam is, in metres, on the ground.

EDGES ARE DERIVED, NOT STORED. A lane exports its centreline `points` plus `width_start`/
`width_end`; the edge endpoints come from the end point, the local tangent, and half that width.
Deriving beats storing here: there is no way for a stored edge to drift out of agreement with the
centreline it belongs to, and the sidecar does not grow by two more polylines per lane.

The frame is the lane's own direction of travel -- `points` always run the way a car drives (see
`lane_profile.export_profile_lanes`) -- so "left" means the same thing on both sides of a joint
even where the two pieces have opposite world headings.
"""

import math

#: Two edges closer than this are the same edge. 1 cm: tighter than any authoring gesture can
#: place a spine by hand, looser than float noise through a chain of offset/rotate maths.
EDGE_TOL = 0.01

#: Beyond this, the two lanes are not attempting to meet at all -- report it as "not a joint"
#: rather than as a misalignment, so a genuinely wrong link is not dressed up as a small gap.
DISJOINT_M = 5.0

#: Degrees the two directions of travel may differ across a seam. A joint is a HANDOVER: the car
#: leaves one ribbon at one heading and is already on the next, so any difference is a steering
#: step taken at zero distance. 8 deg is about the sharpest that reads as a road rather than as a
#: crease, and it is well above the couple of degrees a resampled polyline's end tangent carries.
HEADING_TOL_DEG = 8.0

#: Past this the lanes are not merely kinked, they point at each other (or away). Reported as
#: `FLIPPED` rather than as a large misalignment because it is a different fault with a different
#: fix -- see `joint_alignment`.
FLIP_DEG = 90.0


#: Which two components of a point are the GROUND PLANE. Blender-native points are
#: `(x, y, height)` so the default is `(0, 1)`; a `.lanekit.json` is written in GODOT space,
#: `(x, height, -northing)`, where the ground plane is `(0, 2)`.
#:
#: This is a parameter and not an assumption because getting it wrong is SILENT and looks like
#: geometry: measuring x-against-elevation on a flat road makes every lane's "left" and "right"
#: edge collapse onto the centreline, so nothing is ever more than a few centimetres from anything
#: else, `pair_lanes` matches lanes that do not touch and refuses lanes that do, and the numbers it
#: reports are all plausible. Found 2026-08-15: `lane_export.emit_joint_links` runs inside
#: `collect_pieces`, which the real export calls with `godot_space=True` -- so every joint in a
#: written sidecar was measured in the wrong plane, while the in-Blender preview path
#: (`godot_space=False`) was correct and every test passed.
BLENDER_AXES = (0, 1)
GODOT_AXES = (0, 2)


def _xy(p, axes=BLENDER_AXES):
    return (float(p[axes[0]]), float(p[axes[1]]))


def _tangent_xy(points, at_end, axes=BLENDER_AXES):
    """Unit XY direction of travel at one end of a lane's centreline.

    Taken from the last two DISTINCT points, not simply the last two: a polyline that repeats its
    final point (a closing vertex, a degenerate sample) has no tangent there, and silently
    returning `(1, 0)` would place both edges 90 degrees off and report a huge, wrong gap."""
    idx = range(len(points) - 1, -1, -1) if at_end else range(len(points))
    ref = None
    for i in idx:
        p = _xy(points[i], axes)
        if ref is None:
            ref = p
            continue
        dx, dy = ref[0] - p[0], ref[1] - p[1]
        if math.hypot(dx, dy) > 1e-9:
            if not at_end:
                dx, dy = -dx, -dy
            n = math.hypot(dx, dy)
            return (dx / n, dy / n)
    return None


def lane_edges(lane, at_end, axes=BLENDER_AXES):
    """`(left_xy, right_xy)` of one END of a lane's ribbon, in the lane's own travel frame.

    `None` when the lane cannot produce a tangent (fewer than two distinct points) or carries no
    width -- callers report that as an unmeasurable joint rather than guessing a width, because a
    guessed width turns a missing-data problem into a plausible-looking alignment number."""
    pts = lane.get("points") or []
    if len(pts) < 2:
        return None
    w = lane.get("width_end" if at_end else "width_start", lane.get("width"))
    if w is None:
        return None
    t = _tangent_xy(pts, at_end, axes)
    if t is None:
        return None
    # Left normal of the travel direction, matching `lane_profile`'s `+s` convention.
    nx, ny = -t[1], t[0]
    px, py = _xy(pts[-1] if at_end else pts[0], axes)
    h = float(w) / 2.0
    return ((px + nx * h, py + ny * h), (px - nx * h, py - ny * h))


def joint_alignment(from_lane, to_lane, axes=BLENDER_AXES):
    """Measure the seam where `from_lane` hands over to `to_lane`.

    Returns a dict: `aligned` (bool), `gap_left` / `gap_right` (metres between the corresponding
    edge points), `gap_centre`, `heading_deg` (how far the two directions of travel differ across
    the seam), `status` -- one of:

        `OK`           both edges within `EDGE_TOL` AND the headings agree; the ribbons continue
        `FLIPPED`      the two lanes point at each other, or away -- the seam may be perfect and
                       it still cannot be driven through
        `MISALIGNED`   the lanes meet, but an edge or the heading is off by more than tolerance
        `DISJOINT`     the ends are more than `DISJOINT_M` apart -- not a seam at all, so the
                       link is wrong about which lanes it joins, not merely imprecise
        `UNMEASURABLE` a lane lacks the width or the distinct points needed to have an edge

    WHY HEADING IS MEASURED SEPARATELY, when the edge test already "catches" a flip. It catches it
    only as a CONSEQUENCE -- a reversed lane's left edge lands where the right edge should be, so
    the seam reports a gap of one lane width -- and that is the wrong diagnosis to hand someone.
    "Edges apart by 3.5 m" sends you looking for a piece that is positioned wrongly; the piece is
    positioned perfectly and is pointing the wrong way, which is a different fix. Worse, the
    consequence is only reliable while the lane HAS width: it shrinks with the lane and vanishes
    entirely for an `UNMEASURABLE` one, so the property everything downstream depends on -- that a
    car can drive across this seam -- was never actually being tested. Now it is, directly.

    `from_lane`'s END meets `to_lane`'s START, because a lane's points always run in its own
    direction of travel."""
    a = lane_edges(from_lane, at_end=True, axes=axes)
    b = lane_edges(to_lane, at_end=False, axes=axes)
    ta = _tangent_xy(from_lane.get("points") or (), True, axes)
    tb = _tangent_xy(to_lane.get("points") or (), False, axes)
    dh = None
    if ta is not None and tb is not None:
        dh = abs(math.degrees(math.atan2(ta[0] * tb[1] - ta[1] * tb[0],
                                          ta[0] * tb[0] + ta[1] * tb[1])))
    if a is None or b is None:
        return {"status": "UNMEASURABLE", "aligned": False, "heading_deg": dh,
                "gap_left": None, "gap_right": None, "gap_centre": None}
    gl = math.dist(a[0], b[0])
    gr = math.dist(a[1], b[1])
    ac = ((a[0][0] + a[1][0]) / 2.0, (a[0][1] + a[1][1]) / 2.0)
    bc = ((b[0][0] + b[1][0]) / 2.0, (b[0][1] + b[1][1]) / 2.0)
    gc = math.dist(ac, bc)
    if gc > DISJOINT_M:
        status = "DISJOINT"
    elif dh is not None and dh > FLIP_DEG:
        # Reported ahead of the edge gaps deliberately: when a lane is reversed the edge numbers
        # are real but they describe the symptom, and naming the symptom first is what sends
        # someone to move a piece that does not need moving.
        status = "FLIPPED"
    elif gl <= EDGE_TOL and gr <= EDGE_TOL and (dh is None or dh <= HEADING_TOL_DEG):
        status = "OK"
    else:
        status = "MISALIGNED"
    return {"status": status, "aligned": status == "OK", "heading_deg": dh,
            "gap_left": gl, "gap_right": gr, "gap_centre": gc}


def check_links(lanes, links=None, axes=BLENDER_AXES):
    """Every explicit link in `lanes`, measured. Returns a list of problem dicts (empty = clean),
    each `{"from", "to", "kind", ...alignment fields}`.

    `lanes` is the sidecar's own lane list; a link is a `next` entry (with the matching
    `next_kinds` when present). `links` overrides that with explicit `(from_id, to_id, kind)`
    triples, which is how the Blender-side checker feeds in a joint the user is about to create."""
    by_id = {l.get("id"): l for l in lanes if l.get("id")}
    if links is None:
        links = []
        for l in lanes:
            nxt = l.get("next") or []
            kinds = l.get("next_kinds") or []
            for i, dst in enumerate(nxt):
                links.append((l.get("id"), dst, kinds[i] if i < len(kinds) else ""))
    problems = []
    for src, dst, kind in links:
        a, b = by_id.get(src), by_id.get(dst)
        if a is None or b is None:
            problems.append({"from": src, "to": dst, "kind": kind, "status": "DANGLING",
                             "aligned": False, "gap_left": None, "gap_right": None,
                             "gap_centre": None})
            continue
        # A LANE_CHANGE is a sideways move WITHIN a piece, not an end-to-end handover -- its two
        # lanes run alongside each other, so measuring one's end against the other's start would
        # report the length of the piece as a "gap". Only through-travel links have a seam.
        if kind == "LANE_CHANGE":
            continue
        res = joint_alignment(a, b, axes)
        if not res["aligned"]:
            res.update({"from": src, "to": dst, "kind": kind})
            problems.append(res)
    return problems


def pair_lanes(out_lanes, in_lanes, tol=None, exclusive=True, axes=BLENDER_AXES):
    """Match lanes ENDING at a joint to lanes STARTING there, by which ribbons actually meet.

    Returns `[(out_id, in_id, gap), ...]`, best first.

    WHY MEASURE INSTEAD OF DERIVING. The obvious approach is to reason it out: same slot id,
    unless the two pieces meet end-to-end in which case the frames mirror and forward pairs with
    reverse and the slot order flips. That reasoning is correct and it is also four ways to get a
    sign wrong, silently, in a case nobody tests. Measuring asks the geometry the question the
    connection is actually about -- "do these two ribbons continue into each other" -- and a
    mirrored joint falls out with no special case at all.

    It is also exactly what a RAMP needs. A ramp's lane pairs with whichever mainline lane its
    edges genuinely meet: the auxiliary lane when one has been opened for the exit, and the
    outermost lane when none has, with no rule to encode and keep in step with the profile.

    Pairs worse than `tol` (default `EDGE_TOL`) are NOT returned. An unpaired lane is reported by
    the caller as an unmade connection, never rounded up into the nearest plausible one -- guessing
    here is how a graph ends up claiming a movement the road does not have.

    `exclusive` -- ONE-TO-ONE (the default) or a FAN. A plain butt joint between two segments is
    one-to-one: a lane continues into exactly one lane, and if two candidates tie, the closer wins
    and the other lane is left unpaired rather than sharing a successor. A JUNCTION is the opposite
    shape and needs `exclusive=False`: an approach lane legally feeds every movement that begins on
    it (left, straight and right all start on the same ribbon at the same stop line), and every
    movement ending on a departure lane feeds that single lane leaving the junction. Forcing
    one-to-one there would keep whichever movement happened to measure closest and silently delete
    the turns -- a junction that only goes straight. Which lanes may fan is a property of the
    joint, so the caller decides it; the measurement is identical either way."""
    t = EDGE_TOL if tol is None else tol
    cands = []
    for a in out_lanes:
        for b in in_lanes:
            r = joint_alignment(a, b, axes)
            # EDGE **AND** ANGLE. A pair whose ribbons coincide but whose directions of travel
            # disagree is not a continuation -- at best it is a crease the car takes at zero
            # distance, at worst it is head-on. The edge test alone cannot be relied on to refuse
            # it: the gap a flip produces is one lane width, so it shrinks with the lane and
            # disappears entirely for a lane with no width at all. Checking the heading here means
            # a pairing is only ever proposed where a car could actually drive through.
            head = r.get("heading_deg")
            if head is not None and head > HEADING_TOL_DEG:
                continue
            if r["status"] == "OK" or (r["gap_left"] is not None
                                       and max(r["gap_left"], r["gap_right"]) <= t):
                cands.append((max(r["gap_left"], r["gap_right"]), a.get("id"), b.get("id")))
    cands.sort()
    if not exclusive:
        return [(aid, bid, gap) for gap, aid, bid in cands]
    used_a, used_b, out = set(), set(), []
    for gap, aid, bid in cands:
        if aid in used_a or bid in used_b:
            continue
        used_a.add(aid)
        used_b.add(bid)
        out.append((aid, bid, gap))
    return out


def unjoined(name_a, name_b):
    """A problem record for two pieces the user LINKED that no lane actually crosses.

    This one cannot be found by measuring links, because there are none -- it is the absence that
    is wrong, and in the lane data it is indistinguishable from two pieces that were never linked
    at all. Only the authored side knows the difference, so it is reported from there
    (`lane_export.authored_joints`). It is the most common real failure by far: the connect gesture
    succeeded, the pieces sit next to each other, and the road has a hole in its graph."""
    return {"from": name_a, "to": name_b, "kind": "JOINT", "status": "UNJOINED", "aligned": False,
            "gap_left": None, "gap_right": None, "gap_centre": None}


def describe(problem):
    """One line a person can act on: which seam, how bad, in metres."""
    if problem["status"] == "UNJOINED":
        return ("%s <-> %s: pieces are linked, but NO lane crosses the seam -- their ribbons do "
                "not meet edge-to-edge anywhere (check lane widths, counts and heading)"
                % (problem["from"], problem["to"]))
    if problem["status"] == "DANGLING":
        return "%s -> %s (%s): target lane does not exist" % (
            problem["from"], problem["to"], problem["kind"] or "?")
    if problem["status"] == "UNMEASURABLE":
        return "%s -> %s (%s): no width/tangent to measure an edge from" % (
            problem["from"], problem["to"], problem["kind"] or "?")
    if problem["status"] == "FLIPPED":
        return ("%s -> %s (%s): FLIPPED, the two lanes' directions of travel differ by %.0f deg "
                "-- the seam can be perfect and still not be drivable. One of these pieces (or "
                "one of its lanes) runs the wrong way; turn it, do not move it"
                % (problem["from"], problem["to"], problem["kind"] or "?",
                   problem.get("heading_deg") or 0.0))
    head = problem.get("heading_deg")
    return "%s -> %s (%s): %s, edges apart by L=%.3fm R=%.3fm (centres %.3fm%s)" % (
        problem["from"], problem["to"], problem["kind"] or "?", problem["status"],
        problem["gap_left"], problem["gap_right"], problem["gap_centre"],
        "" if head is None else ", heading %.1f deg" % head)


# ------------------------------------------------------------------------------------ self-test

def _lane(id, pts, w, **kw):
    d = {"id": id, "points": [list(p) for p in pts], "width_start": w, "width_end": w}
    d.update(kw)
    return d


def self_test():
    W = 3.5
    # --- a clean seam: B starts exactly where A ends, same width, same heading.
    a = _lane("A", [(0, 0, 0), (10, 0, 0)], W)
    b = _lane("B", [(10, 0, 0), (20, 0, 0)], W)
    r = joint_alignment(a, b)
    assert r["status"] == "OK" and r["aligned"], r
    assert r["gap_left"] < 1e-9 and r["gap_right"] < 1e-9, r
    print("OK: end-to-end, same width, same heading -> aligned (both edge gaps 0)")

    # --- centres touch EXACTLY, widths differ -> NOT connected. This is the case the old
    # proximity test called a connection: the centrelines are coincident to the millimetre.
    b2 = _lane("B", [(10, 0, 0), (20, 0, 0)], W + 1.0)
    r = joint_alignment(a, b2)
    assert r["status"] == "MISALIGNED", r
    assert r["gap_centre"] < 1e-9, "centres DO coincide -- that is the whole point"
    assert abs(r["gap_left"] - 0.5) < 1e-9 and abs(r["gap_right"] - 0.5) < 1e-9, r
    print("OK: coincident centrelines + a 1.0m width mismatch -> MISALIGNED, each edge out by "
          "exactly half the difference (0.500m) -- touching is not connecting")

    # --- centres touch exactly, headings differ -> NOT connected, and the gap grows with the
    # angle rather than being invisible.
    ang = math.radians(30.0)
    b3 = _lane("B", [(10, 0, 0), (10 + 10 * math.cos(ang), 10 * math.sin(ang), 0)], W)
    r = joint_alignment(a, b3)
    assert r["status"] == "MISALIGNED", r
    assert r["gap_centre"] < 1e-9, "centres still coincide exactly"
    expect = 2.0 * (W / 2.0) * math.sin(ang / 2.0)      # chord between the two edge positions
    assert abs(r["gap_left"] - expect) < 1e-9 and abs(r["gap_right"] - expect) < 1e-9, r
    print("OK: coincident centrelines + a 30-degree heading break -> MISALIGNED, edges out by "
          "%.3fm each -- a kink the centreline test cannot see" % expect)

    # --- a real seam that is merely sloppy: 2 cm of centre offset shows up on both edges.
    b4 = _lane("B", [(10, 0.02, 0), (20, 0.02, 0)], W)
    r = joint_alignment(a, b4)
    assert r["status"] == "MISALIGNED" and abs(r["gap_left"] - 0.02) < 1e-9, r
    print("OK: a 2cm lateral offset is reported as 0.020m on both edges, not swept under a "
          "'close enough' proximity radius")

    # --- lanes that are not trying to meet at all are DISJOINT, not 'a big misalignment'.
    b5 = _lane("B", [(40, 0, 0), (50, 0, 0)], W)
    assert joint_alignment(a, b5)["status"] == "DISJOINT"
    print("OK: ends 30m apart -> DISJOINT (the link names the wrong lanes; it is not a seam)")

    # --- HEAD-ON is not a connection. `rev` starts exactly where `a` ends, with the same width,
    # but travels back the way `a` came. The centres coincide perfectly; the ribbons face opposite
    # ways, so `a`'s left edge lands on `rev`'s RIGHT edge -- a full lane width apart. A checker
    # that only looked at centres would call this a clean joint and let an AI drive into oncoming
    # traffic.
    rev = _lane("R", [(10, 0, 0), (0, 0, 0)], W)
    r = joint_alignment(a, rev)
    assert r["status"] == "FLIPPED" and abs(r["heading_deg"] - 180.0) < 1e-9, r
    assert abs(r["gap_left"] - W) < 1e-9, r
    assert r["gap_centre"] < 1e-9, "the centres coincide exactly -- that is what makes it a trap"
    print("OK: a head-on link (same point, same width, opposite travel) is FLIPPED at %.0f deg, "
          "and NAMED as a direction fault rather than as the %.3fm edge gap it also produces"
          % (r["heading_deg"], W))

    # --- ...and the direction test does not depend on the lane HAVING width, which is the whole
    # reason it is measured rather than inferred. Shrink the lane and the edge symptom shrinks
    # with it -- 2 cm apart, inside `EDGE_TOL` on a hair -- while the fault is unchanged: this
    # seam still cannot be driven through.
    thin_a = _lane("TA", [(0, 0, 0), (10, 0, 0)], 0.02)
    thin_b = _lane("TB", [(10, 0, 0), (0, 0, 0)], 0.02)
    r = joint_alignment(thin_a, thin_b)
    assert r["status"] == "FLIPPED", r
    assert max(r["gap_left"], r["gap_right"]) < 0.03, r
    print("OK: a reversed HAIRLINE lane is still FLIPPED although its edges are only %.3fm apart "
          "-- the edge test's ability to catch a flip scales with lane width; the heading test "
          "does not" % r["gap_left"])

    # --- a seam with matching edges but an 30-degree kink is MISALIGNED and now SAYS the heading.
    kinked = _lane("K", [(10, 0, 0), (10 + 8.66, 5.0, 0)], W)
    r = joint_alignment(a, kinked)
    assert r["status"] == "MISALIGNED" and abs(r["heading_deg"] - 30.0) < 0.5, r
    assert "heading 30.0 deg" in describe(dict(r, **{"from": "A", "to": "K", "kind": "THROUGH"}))
    print("OK: a 30 deg kink reports the ANGLE as well as the edge gaps, so the report says what "
          "to fix instead of only how bad it is")

    # --- two lanes that both travel -X do join, even though their points run 'backwards' in world
    # terms: the frame is the lane's own direction, so left still meets left.
    ra = _lane("RA", [(20, 0, 0), (10, 0, 0)], W)
    rb = _lane("RB", [(10, 0, 0), (0, 0, 0)], W)
    assert joint_alignment(ra, rb)["status"] == "OK", joint_alignment(ra, rb)
    print("OK: two reverse-direction lanes join end-to-start correctly -- 'left' is measured in "
          "the lane's own travel frame, not the world's")

    # --- missing width is UNMEASURABLE, never a silent pass.
    now = dict(a)
    now.pop("width_start"); now.pop("width_end")
    assert joint_alignment(now, b)["status"] == "UNMEASURABLE"
    print("OK: a lane with no width is UNMEASURABLE, not assumed-aligned")

    # --- check_links over a whole lane list, including a dangling ref and a lane change.
    lanes = [
        _lane("A", [(0, 0, 0), (10, 0, 0)], W, next=["B", "C", "GONE"],
              next_kinds=["THROUGH", "LANE_CHANGE", "THROUGH"]),
        _lane("B", [(10, 0, 0), (20, 0, 0)], W),
        _lane("C", [(0, 3.5, 0), (10, 3.5, 0)], W),
    ]
    probs = check_links(lanes)
    ids = sorted((p["to"], p["status"]) for p in probs)
    assert ids == [("GONE", "DANGLING")], ids
    print("OK: check_links passes a good THROUGH, SKIPS the LANE_CHANGE (a sideways move has no "
          "seam), and reports the dangling ref")

    # --- a degenerate repeated end point must not fake a tangent.
    degen = _lane("D", [(0, 0, 0), (10, 0, 0), (10, 0, 0)], W)
    assert joint_alignment(degen, b)["status"] == "OK", \
        "a repeated final point should fall back to the last DISTINCT pair, not report a kink"
    print("OK: a repeated final control point does not fake a 90-degree tangent")

    # --- pairing: a 2-lane road continuing into a 2-lane road matches lane-for-lane by geometry.
    outs = [_lane("F0", [(0, 0, 0), (10, 0, 0)], W),
            _lane("F1", [(0, W, 0), (10, W, 0)], W)]
    ins = [_lane("G0", [(10, 0, 0), (20, 0, 0)], W),
           _lane("G1", [(10, W, 0), (20, W, 0)], W)]
    pairs = {a: b for a, b, _g in pair_lanes(outs, ins)}
    assert pairs == {"F0": "G0", "F1": "G1"}, pairs
    print("OK: pair_lanes matches a 2-lane continuation lane-for-lane, by measurement")

    # --- pairing is EXCLUSIVE: two lanes cannot both claim the same successor.
    dup = [_lane("H0", [(10, 0, 0), (20, 0, 0)], W)]
    pairs2 = pair_lanes(outs, dup)
    assert len(pairs2) == 1 and pairs2[0][0] == "F0", pairs2
    print("OK: pairing is mutually exclusive -- F1 is left unpaired rather than sharing F0's "
          "successor")

    # --- THE JUNCTION CASE: an approach lane feeds EVERY movement that starts on it. All three
    # begin on the same ribbon at the same stop line and only diverge inside the pad, so all three
    # are equally, exactly aligned -- and one-to-one pairing would keep whichever sorted first and
    # silently drop the two turns, leaving a junction that only goes straight.
    appr = [_lane("APPR", [(0, 0, 0), (10, 0, 0)], W)]
    movements = [
        _lane("MOV_S", [(10, 0, 0), (20, 0, 0)], W, turn="S"),
        _lane("MOV_L", [(10, 0, 0), (14, 0, 0), (18, 4, 0)], W, turn="L"),
        _lane("MOV_R", [(10, 0, 0), (14, 0, 0), (18, -4, 0)], W, turn="R"),
    ]
    fan = pair_lanes(appr, movements, exclusive=False)
    assert sorted(b for _a, b, _g in fan) == ["MOV_L", "MOV_R", "MOV_S"], fan
    assert len(pair_lanes(appr, movements)) == 1, "the default is still one-to-one"
    print("OK: at a junction (exclusive=False) one approach lane feeds all %d of its movements; "
          "the default one-to-one rule would have kept 1 and deleted the turns" % len(fan))

    # --- THE RAMP CASE: a mainline with an auxiliary lane opened for an exit. The ramp's lane
    # meets the AUX lane's edges, so that is what it pairs with -- no rule about which lane a ramp
    # takes, and the same code picks the outermost lane when no aux exists.
    main = [_lane("M_F0", [(0, 0, 0), (10, 0, 0)], W),
            _lane("M_AUX", [(0, W, 0), (10, W, 0)], W)]
    # The ramp leaves TANGENTIALLY and only then curves away -- which is what a gore physically
    # is. Its first span is collinear with the aux lane it departs from.
    ramp = [_lane("RAMP_A0", [(10, W, 0), (15, W, 0), (20, W + 4.0, 0)], W)]
    pairs3 = pair_lanes(main, ramp)
    assert pairs3 and pairs3[0][0] == "M_AUX" and pairs3[0][1] == "RAMP_A0", pairs3
    print("OK: a ramp pairs with the AUX lane its edges actually meet, not with the mainline "
          "lane next to it -- the ramp rule falls out of measurement")

    # --- and a ramp that KINKS straight off the mainline pairs with nothing, on purpose. A gore
    # is a tangential divergence; a ramp that turns the instant it leaves has a step in it, which
    # is the "ramps meet the mainline at a poor angle" defect (`ROAD_KIT_MIGRATION_STATUS.md` §5)
    # showing up as an unmade connection instead of as a link that lies about the geometry.
    kinked = [_lane("RAMP_BAD", [(10, W, 0), (20, W + 4.0, 0)], W)]
    assert pair_lanes(main, kinked) == [], pair_lanes(main, kinked)
    print("OK: a ramp that kinks away instead of departing tangentially pairs with NOTHING -- the "
          "bad-gore-angle defect surfaces as a missing link, not a false one")

    # --- nothing within tolerance pairs with nothing. An unmade connection stays unmade.
    far = [_lane("X", [(10, 40, 0), (20, 40, 0)], W)]
    assert pair_lanes(outs, far) == []
    print("OK: lanes that do not meet produce NO pairing -- never rounded up to the nearest "
          "plausible lane")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
