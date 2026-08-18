"""lane_ports.py -- pure-Python (no bpy), self-tested. A port is a LANE END, not a road end.
`python3 lib/lane_ports.py` self-tests, same convention as `lane_joints.py`/`lane_profile.py`.

WHY THIS EXISTS. Until now a piece had exactly two ports, `port_A`/`port_B`, and each sat on the
road CENTRELINE. That single fact is the root cause of three separate authoring complaints
(`ROAD_KIT_MIGRATION_STATUS.md` Step 7):

    "lane cannot be snapped to lane"          there is no per-lane anchor to snap TO
    "segment<->intersection snapping is       an arm port is one centre point, so the match is a
     unreliable"                              proximity guess about whole roads
    "cannot see which way traffic goes        a centre point has no direction of travel; a road
     through a connection point"              with two-way lanes has BOTH at the same point

A port at the centre of a 21 m carriageway is up to 10 m from the lane you actually meant, and
carries no direction, so everything downstream is reduced to guessing.

THE PORT IS THE EXPORTED LANE'S OWN ENDPOINT -- derived here from the very lane dicts
`lane_export.export_piece_dict` produces, never re-derived from the profile with a second
convention. That is the whole trick, and it is deliberate: a port that is computed independently
can disagree with the lane it names, and then snapping to the port does NOT align the lane. Since
these ports ARE the lane endpoints, `lane_joints`' edge measurement of a snapped seam necessarily
reads what the snap promised. One description, three consumers (viewport markers, the snap
operator, the alignment gate).

FLOW. `points` always run the way a car drives, so the first point of a lane is where traffic
ENTERS the piece and the last is where it LEAVES:

    points[0]   -> flow "IN",  heading = direction of travel entering
    points[-1]  -> flow "OUT", heading = direction of travel leaving

A two-way road therefore has an IN port and an OUT port at BOTH ends, one per lane, each pointing
the way its own traffic moves -- which is exactly the in/out arrow the viewport was missing. It
also makes one class of authoring error checkable rather than invisible: joining OUT to OUT is two
roads flowing head-on into the same seam, and joining IN to IN is a seam nothing feeds. Both are
reported by name (`flow_conflict`) instead of quietly producing a link the gate later calls
DISJOINT.

DEDUPE. An intersection emits one lane per movement, so every turn leaving one approach lane
starts at the same point; without merging, a 4-arm junction grows dozens of coincident markers.
Ports within `PORT_MERGE_TOL` that share a flow and a heading are ONE port carrying several lane
ids -- which is also the truth: that is one place on the ground where one stream of traffic
crosses the piece boundary.
"""

import math

#: Ground-plane axis pair -- see `lane_joints` for the full explanation of why this is a parameter
#: and not an assumption (getting it wrong is silent and looks like geometry).
BLENDER_AXES = (0, 1)
GODOT_AXES = (0, 2)

#: Ports this close, with the same flow and heading, are the same port. 25 cm: far below any lane
#: width (so two neighbouring lanes never merge), far above the float noise of an offset-and-
#: rotate chain (so an intersection's fan of movements off one approach lane collapses to one).
PORT_MERGE_TOL = 0.25

#: Two headings within this are the same heading, for merging only. Generous on purpose: a
#: junction movement leaves its stop line on the approach tangent, but the polyline is a COARSELY
#: sampled bezier, so a hard-turning movement's very first span already carries some of the turn.
#: Nothing legitimate is anywhere near this close -- distinct flows through one point differ by 90
#: deg (crossing) or 180 deg (opposed) -- so the tolerance discriminates sampling noise from
#: meaning with an order of magnitude to spare.
HEADING_MERGE_DEG = 25.0

IN = "IN"
OUT = "OUT"


def _up_axis(axes):
    return 3 - axes[0] - axes[1]


def _xy(p, axes):
    return (float(p[axes[0]]), float(p[axes[1]]))


def _first_distinct(pts, at_end, axes, tol=1e-6):
    """`(near, far)` -- the endpoint and the nearest point along the lane that is genuinely
    somewhere else on the ground plane. Two coincident points give no direction, and a lane whose
    last two samples are stacked would otherwise yield a heading of 0 deg that reads as valid.
    Returns None when the whole lane is degenerate."""
    idxs = range(len(pts) - 1, -1, -1) if at_end else range(len(pts))
    it = iter(idxs)
    near_i = next(it)
    near = _xy(pts[near_i], axes)
    for i in it:
        far = _xy(pts[i], axes)
        if math.hypot(far[0] - near[0], far[1] - near[1]) > tol:
            return near, far
    return None


def lane_ports(lane, axes=BLENDER_AXES):
    """The IN and OUT port of one exported lane dict, as a list (empty when degenerate).

    `heading` is always the DIRECTION OF TRAVEL in degrees, so the two ports of a lane point the
    same way -- into the piece at the start, out of it at the end. That uniformity is what lets
    `snap_transform` be one subtraction instead of a case analysis over which end met which."""
    pts = lane.get("points") or ()
    if len(pts) < 2:
        return []
    out = []
    for at_end, flow, wkey in ((False, IN, "width_start"), (True, OUT, "width_end")):
        pair = _first_distinct(pts, at_end, axes)
        if pair is None:
            continue
        near, far = pair
        # Travel is start->end. At the END the endpoint is `near` and the interior sample is
        # `far`, so the vector must be flipped to still read as "the way the car is going".
        dx, dy = (near[0] - far[0], near[1] - far[1]) if at_end else (far[0] - near[0],
                                                                       far[1] - near[1])
        p = pts[-1] if at_end else pts[0]
        out.append({"flow": flow,
                    "pos": (float(p[0]), float(p[1]), float(p[2])),
                    "heading": math.degrees(math.atan2(dy, dx)),
                    "width": float(lane.get(wkey) or 0.0),
                    "lanes": [lane.get("id")],
                    "slots": [lane.get("slot_id")] if lane.get("slot_id") else [],
                    "arms": _arm_of(lane, at_end)})
    return out


def _arm_of(lane, at_end):
    """Intersection lanes name the arm they come from / go to; a segment lane's `from_arm`/
    `to_arm` are the literal strings "A"/"B" (see `export_segment_from_profile_dict`), which is
    the piece END and reads correctly here too."""
    a = lane.get("to_arm") if at_end else lane.get("from_arm")
    return [a] if a else []


def _angle_delta(a, b):
    return (b - a + 180.0) % 360.0 - 180.0


def ports_from_lanes(lanes, axes=BLENDER_AXES, merge_tol=PORT_MERGE_TOL):
    """Every lane end of a piece, merged into distinct ports. Order is stable (first appearance),
    so a rebuild does not reshuffle the markers a user has been clicking on."""
    merged = []
    for lane in lanes or ():
        for port in lane_ports(lane, axes=axes):
            hit = None
            for m in merged:
                if m["flow"] != port["flow"]:
                    continue
                if abs(_angle_delta(m["heading"], port["heading"])) > HEADING_MERGE_DEG:
                    continue
                d = math.hypot(*[m["pos"][k] - port["pos"][k] for k in axes])
                if d <= merge_tol:
                    hit = m
                    break
            if hit is None:
                merged.append(port)
                continue
            for key in ("lanes", "slots", "arms"):
                for v in port[key]:
                    if v not in hit[key]:
                        hit[key].append(v)
            hit["width"] = max(hit["width"], port["width"])
    return merged


def describe(port):
    what = "/".join(port["slots"]) or "/".join(port["arms"]) or "?"
    return "%s %-3s %5.1f deg  w=%.2f  [%s]" % (port["flow"], what, port["heading"],
                                                 port["width"], ", ".join(port["lanes"]))


# ------------------------------------------------------------------------------------- snapping

def flow_conflict(src, dst):
    """None when these two ports can legitimately be butted together, else the reason.

    Continuity across a seam is one lane LEAVING meeting one lane ENTERING. The two same-flow
    cases are real authoring mistakes with distinct meanings, so they are named rather than
    lumped into one 'invalid' -- OUT to OUT is two streams driving head-on into the seam, IN to IN
    is a seam nothing feeds."""
    if src["flow"] == OUT and dst["flow"] == OUT:
        return ("both lanes flow OUT of the seam -- joining these would put two streams head-on; "
                "pick the other end of one piece")
    if src["flow"] == IN and dst["flow"] == IN:
        return ("both lanes flow IN to the seam -- nothing would feed the joint; pick the other "
                "end of one piece")
    return None


def snap_transform(src, dst):
    """`(theta_deg, delta)` -- rotate the moving piece by `theta_deg` about `src["pos"]` in the
    ground plane, then translate by `delta`, and `src` lands exactly on `dst` flowing the same
    way.

    It is one subtraction because `heading` is always the direction of travel: continuity at a
    butt joint means the two lanes carry traffic in the SAME direction through the coincident
    point, whichever end of whichever piece each port belongs to. Elevation rides in `delta` --
    the rotation is deliberately planar, because banking a whole piece to make a seam meet is not
    a snap, it is a different edit."""
    theta = _angle_delta(src["heading"], dst["heading"])
    delta = tuple(dst["pos"][i] - src["pos"][i] for i in range(3))
    return theta, delta


def apply_transform(p, pivot, theta_deg, delta, axes=BLENDER_AXES):
    """Rotate `p` about `pivot` by `theta_deg` in the ground plane, then translate by `delta`.
    THE one implementation -- the operator moves spine points with it and the self-test checks it,
    so a snap that verifies here is the snap that happens in Blender."""
    a, b = axes
    up = _up_axis(axes)
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    da, db = float(p[a]) - float(pivot[a]), float(p[b]) - float(pivot[b])
    out = [0.0, 0.0, 0.0]
    out[a] = float(pivot[a]) + da * c - db * s + delta[a]
    out[b] = float(pivot[b]) + da * s + db * c + delta[b]
    out[up] = float(p[up]) + delta[up]
    return tuple(out)


# ----------------------------------------------------------------------------------- self-tests

def _lane(lid, pts, w, slot=None, from_arm="A", to_arm="B"):
    return {"id": lid, "points": [list(p) for p in pts], "width_start": w, "width_end": w,
            "slot_id": slot, "from_arm": from_arm, "to_arm": to_arm}


def self_test():
    W = 3.5

    # --- a plain two-way segment: one IN and one OUT at EACH end, pointing opposite ways.
    fwd = _lane("SEG_F0", [(0, 1.75, 0), (50, 1.75, 0)], W, slot="F0")
    rev = _lane("SEG_R0", [(50, -1.75, 0), (0, -1.75, 0)], W, slot="R0")
    ports = ports_from_lanes([fwd, rev])
    assert len(ports) == 4, [describe(p) for p in ports]
    at_west = [p for p in ports if abs(p["pos"][0]) < 1e-6]
    assert sorted(p["flow"] for p in at_west) == [IN, OUT], [describe(p) for p in at_west]
    fin = next(p for p in at_west if p["flow"] == IN)
    fout = next(p for p in at_west if p["flow"] == OUT)
    assert abs(fin["heading"] - 0.0) < 1e-6, fin
    assert abs(abs(fout["heading"]) - 180.0) < 1e-6, fout
    print("OK: a two-way segment end carries an IN port and an OUT port, arrows opposed -- the "
          "direction-of-travel readout a single centre port could never give")

    # --- ports name the LANE, and they sit on the lane centreline, not the road centre.
    assert fin["lanes"] == ["SEG_F0"] and abs(fin["pos"][1] - 1.75) < 1e-9
    assert fout["lanes"] == ["SEG_R0"] and abs(fout["pos"][1] + 1.75) < 1e-9
    print("OK: each port sits on its own lane's centreline (+/-1.75 m), naming that lane -- a "
          "road-centre port is 1.75 m from either of them and names neither")

    # --- an intersection's fan: three movements off ONE approach lane collapse to ONE port. The
    # fixture is shaped like the real thing -- a coarsely sampled bezier that leaves the stop line
    # on the approach tangent and is already bending by its second sample.
    # (Measured against the real `island_v3_roads.lanekit.json`: of 160 same-arm/same-index
    # groups, 158 agree to within 5 deg and the other 2 differ by 180 -- so the fixture's first
    # span carries only the small deviation real sampling produces.)
    fan = [_lane("X_%s" % t, [(0, 0, 0), (d[0] * 0.03, 8.0, 0), (d[0], d[1], 0)], W,
                  from_arm="N", to_arm=t)
           for t, d in (("E", (30, 30)), ("S", (0, 40)), ("W", (-30, 30)))]
    # they all ENTER at the same point heading (near enough) the same way
    fan_in = [p for p in ports_from_lanes(fan) if p["flow"] == IN]
    assert len(fan_in) == 1, [describe(p) for p in fan_in]
    assert sorted(fan_in[0]["lanes"]) == ["X_E", "X_S", "X_W"], fan_in[0]
    print("OK: a junction's fan of movements off one approach lane merges into ONE port naming "
          "all three -- markers stay readable instead of stacking")

    # --- ...but a movement leaving the SAME point the OPPOSITE way stays its own port. Those
    # exist in the real file (2 of 160 groups) and merging them would hide a reversed lane behind
    # a marker pointing the other way.
    back = fan + [_lane("X_U", [(0, 0, 0), (-1.0, -8.0, 0), (-30, -30, 0)], W,
                         from_arm="N", to_arm="U")]
    assert len([p for p in ports_from_lanes(back) if p["flow"] == IN]) == 2
    print("OK: a movement leaving the same point in the OPPOSITE direction stays a separate port "
          "-- a reversed lane cannot hide behind a marker pointing the other way")

    # --- ...but two neighbouring lanes 3.5 m apart do NOT merge.
    nb = ports_from_lanes([_lane("A", [(0, 0, 0), (10, 0, 0)], W),
                            _lane("B", [(0, W, 0), (10, W, 0)], W)])
    assert len([p for p in nb if p["flow"] == IN]) == 2, [describe(p) for p in nb]
    print("OK: adjacent lanes one lane-width apart stay TWO ports -- the merge tolerance cannot "
          "swallow a real lane")

    # --- the snap: an arbitrarily rotated and displaced piece lands exactly, flowing on.
    import lane_joints as lj
    src_pts = [(100.0, 200.0, 3.0), (100.0 + 40.0 * math.cos(math.radians(37.0)),
                                      200.0 + 40.0 * math.sin(math.radians(37.0)), 3.0)]
    src = ports_from_lanes([_lane("M_F0", src_pts, W, slot="F0")])
    src_out = next(p for p in src if p["flow"] == OUT)
    dst_in = next(p for p in ports_from_lanes(
        [_lane("T_F0", [(0.0, 0.0, 1.0), (30.0, 30.0, 1.0)], W, slot="F0")]) if p["flow"] == IN)
    assert flow_conflict(src_out, dst_in) is None
    theta, delta = snap_transform(src_out, dst_in)
    moved = [apply_transform(p, src_out["pos"], theta, delta) for p in src_pts]
    landed = next(p for p in ports_from_lanes([_lane("M_F0", moved, W, slot="F0")])
                  if p["flow"] == OUT)
    assert max(abs(landed["pos"][i] - dst_in["pos"][i]) for i in range(3)) < 1e-9, landed
    assert abs(_angle_delta(landed["heading"], dst_in["heading"])) < 1e-9, landed
    print("OK: snap_transform lands the moving lane end exactly on the target, travelling the "
          "same way -- from an arbitrary rotation, offset and elevation")

    # --- and the seam it produces is what `lane_joints` calls aligned, EDGE to edge. This is the
    # point of deriving ports from the exported lanes: the snap and the gate cannot disagree.
    ok = lj.check_links([_lane("M_F0", moved, W, slot="F0"),
                          _lane("T_F0", [(0.0, 0.0, 1.0), (30.0, 30.0, 1.0)], W, slot="F0")],
                         [("M_F0", "T_F0", "THROUGH")])
    assert ok == [], [lj.describe(p) for p in ok]
    print("OK: the snapped seam passes lane_joints' EDGE test with no problems -- the snap and "
          "the alignment gate read the same geometry, so one cannot pass while the other fails")

    # --- flow conflicts are named, not silently snapped.
    assert "head-on" in (flow_conflict(src_out, src_out) or "")
    assert "nothing would feed" in (flow_conflict(dst_in, dst_in) or "")
    print("OK: OUT-to-OUT and IN-to-IN are refused by name -- the two mistakes a centre port "
          "made unrepresentable")

    # --- a degenerate lane yields no ports rather than a heading of 0 deg that looks fine.
    assert lane_ports(_lane("D", [(5, 5, 0), (5, 5, 2)], W)) == []
    assert lane_ports(_lane("D", [(5, 5, 0)], W)) == []
    print("OK: a lane with no ground-plane extent produces NO ports -- never a plausible-looking "
          "0 deg heading")

    # --- Godot-space points measure in their own plane.
    g = ports_from_lanes([{"id": "G", "points": [[0, 9, 0], [50, 9, 0]],
                            "width_start": W, "width_end": W}], axes=GODOT_AXES)
    assert len(g) == 2 and abs(g[0]["heading"]) < 1e-9, [describe(p) for p in g]
    print("OK: GODOT_AXES measures the ground plane as (x, -northing), so a sidecar's lanes read "
          "the same as the blend's")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
