"""lane_kit.py -- pure-Python (no bpy), self-tested combiner support for road_kit_authoring's
per-piece exports (`intersection_kit.py`'s `export_dict` / `export_segment_dict` /
`export_segment_from_spine_dict` / `export_lane_transition_dict`). `python3 lib/lane_kit.py`
self-tests, same convention as `intersection_kit.py` and the retired `road_graph.py`.

Turns a set of independently authored piece dicts (junctions, segments, transitions -- each
already Godot-space per its own `export_*_json` convention: `godot = (blender_x, z,
-blender_y)`) into ONE combined `.lanekit.json`, and does the authoring-time equivalent of
`LaneGraph`'s runtime endpoint-proximity clustering: two pieces connect at Godot bake/runtime
because their lane endpoints land within `JUNCTION_RADIUS` of each other in world space -- there
is no other authored link. This module finds those coincidences ahead of time (at the SAME
tolerance the runtime uses, by default) and flags anything that isn't a clean 1:1 match, so a
human (or `addons/road_kit_authoring/ops_connect.py`'s review UI) resolves it instead of a
combiner silently guessing, or the mistake only surfacing as a car driving off a road at runtime.

Only PIECE-EXTERNAL connection points are clustered, not every raw lane endpoint -- a junction's
own internal fan-out (several movements sharing one arm/lane's entry point) is already fully
described by that one piece's own `from_arm`/`lane_index`/`to_arm` fields and must never be
flagged as inter-piece ambiguity. Concretely: a junction dict's own `ports` list (already
deduplicated to one entry per arm/lane/direction by `intersection_kit.build_ports`) is used
directly; a segment/transition dict (which carries no `ports` list -- it doesn't fan out) has its
per-lane start/end synthesized as the equivalent one-port-per-lane-end list.
"""
import math

JUNCTION_RADIUS = 4.5   # matches LaneGraph.JUNCTION_RADIUS (Java) -- keep in sync by hand.


# --------------------------------------------------------------------------------- small 3D helpers

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dist(a, b):
    d = _sub(a, b)
    return math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else (0.0, 0.0, 0.0)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _pt3(v):
    """Pad a 2-component (x, y) tuple to 3D with z=0.0, or pass a 3-component tuple through
    unchanged. `intersection_kit.export_dict`'s `ports`/`lanes` points are plain 2D (Blender
    ground-plane) unless lifted to Godot-space 3D by `export_json`'s own z-lift -- callers that
    build a junction dict via `export_dict` directly (as `tools/save_lane_kit.py` does, to apply
    the lift itself and skip a temp-file round trip -- see its docstring) must lift `position`
    themselves before calling `combine_pieces`; `tangent` has no z component to lift (a junction's
    ground-plane direction) and is padded here regardless."""
    return (v[0], v[1], v[2]) if len(v) >= 3 else (v[0], v[1], 0.0)


# --------------------------------------------------------------------------------- connection points

def derive_connection_points(piece_id, piece_dict):
    """One dict per PIECE-EXTERNAL connection point: `{'key', 'piece', 'lane_id', 'position'
    (x,y,z tuple), 'tangent' (x,y,z tuple, direction of travel through this point), 'role'
    ('in'|'out')}`. `key` is globally unique (`<piece_id>::...`). See module docstring for why a
    junction uses its own `ports` list directly while a segment/transition synthesizes one
    start+end port per lane."""
    out = []
    ports = piece_dict.get("ports")
    if ports is not None:
        for p in ports:
            pos = _pt3(tuple(p["position"]))
            tan = _pt3(tuple(p.get("tangent", (0.0, 0.0))))
            out.append({"key": "%s::%s" % (piece_id, p["id"]), "piece": piece_id,
                        "lane_id": None, "position": pos, "tangent": _norm(tan),
                        "role": p.get("direction", "")})
        return out

    for lane in piece_dict.get("lanes", []):
        pts = lane.get("points") or []
        if len(pts) < 2:
            continue
        p_start, p_next = tuple(pts[0]), tuple(pts[1])
        p_prev, p_end = tuple(pts[-2]), tuple(pts[-1])
        out.append({"key": "%s::%s::start" % (piece_id, lane["id"]), "piece": piece_id,
                    "lane_id": lane["id"], "position": p_start,
                    "tangent": _norm(_sub(p_next, p_start)), "role": "out"})
        out.append({"key": "%s::%s::end" % (piece_id, lane["id"]), "piece": piece_id,
                    "lane_id": lane["id"], "position": p_end,
                    "tangent": _norm(_sub(p_end, p_prev)), "role": "in"})
    return out


# --------------------------------------------------------------------------------- clustering

def cluster_points(points, tolerance=JUNCTION_RADIUS):
    """Group `points` (see `derive_connection_points`) into clusters of mutual proximity --
    plain union-find over the `tolerance`-radius adjacency graph (any two points within
    `tolerance` of each other end up in the same cluster, even via a chain of intermediate
    points -- same transitive-closure behavior `LaneGraph`'s own runtime clustering has). O(n^2)
    pairwise distance checks -- fine at authoring-time piece counts (tens to low hundreds of
    connection points per combined district), not meant for whole-world scale in one call.
    Returns `[[point, ...], ...]`, each inner list one cluster (order not significant)."""
    n = len(points)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _dist(points[i]["position"], points[j]["position"]) <= tolerance:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(points[i])
    return list(groups.values())


def classify_cluster(cluster, tangent_dot_min=0.3):
    """One cluster -> a report dict: `{'status' ('isolated'|'paired'|'ambiguous'), 'members'
    (keys), 'position' (centroid), 'warnings' (list of str)}`.

    - size 1: 'isolated' -- a dangling connection point with no partner. Not necessarily a
      mistake (a network boundary/stub is legitimate), but worth a human glance.
    - size 2: 'paired' -- the clean, expected case (one piece's lane ending where another's
      begins). Also sanity-checks the two tangents roughly agree (both describe the same
      direction of travel through the shared point) -- a low/negative dot product usually means
      one of the two pieces was authored backwards.
    - size >=3: 'ambiguous' -- more than one plausible partner; the combiner cannot tell which
      pairing is intended. Needs manual review (`ops_connect.py`)."""
    n = len(cluster)
    cx = sum(p["position"][0] for p in cluster) / n
    cy = sum(p["position"][1] for p in cluster) / n
    cz = sum(p["position"][2] for p in cluster) / n
    members = [p["key"] for p in cluster]
    warnings = []
    if n == 1:
        status = "isolated"
    elif n == 2:
        status = "paired"
        dot = _dot(cluster[0]["tangent"], cluster[1]["tangent"])
        if dot < tangent_dot_min:
            warnings.append("tangent mismatch (dot=%.2f) -- one side may be authored backwards"
                             % dot)
    else:
        status = "ambiguous"
        warnings.append("%d connection points within tolerance -- cannot resolve automatically"
                         % n)
    return {"status": status, "members": members, "position": (cx, cy, cz), "warnings": warnings}


# --------------------------------------------------------------------------------- combine

def combine_pieces(pieces, tolerance=JUNCTION_RADIUS):
    """`pieces` = `[(piece_id, piece_dict, zone_id), ...]` -- each `piece_dict` one of
    `intersection_kit.py`'s `export_dict`/`export_segment_dict`/`export_segment_from_spine_dict`/
    `export_lane_transition_dict` results. Every lane/arm id is namespaced `<piece_id>__<id>`
    (globally unique across pieces that reused the same auto-generated local names) and tagged
    with `zone_id`/`piece_id`. Returns `(combined_dict, reports)`:
    - `combined_dict`: `{'lanes': [...], 'arms': [...]}` -- the exact shape `WorldBaker`'s sidecar
      loader already consumes for a single piece, just merged; write straight to
      `<stem>.lanekit.json`.
    - `reports`: `classify_cluster` output for every connection-point cluster across all pieces,
      most-actionable first (ambiguous, then isolated, then paired)."""
    lanes_out = []
    arms_out = []
    all_points = []
    for piece_id, piece_dict, zone_id in pieces:
        # `arms` is populated only by `export_dict` (junction pieces) -- segments/transitions
        # never carry one (see their own export_*_dict docstrings). Used below to blank `turn`
        # on non-junction lanes.
        is_junction_piece = bool(piece_dict.get("arms"))
        for lane in piece_dict.get("lanes", []):
            l = dict(lane)
            l["id"] = "%s__%s" % (piece_id, lane["id"])
            if lane.get("from_arm"):
                l["from_arm"] = "%s__%s" % (piece_id, lane["from_arm"])
            if lane.get("to_arm"):
                l["to_arm"] = "%s__%s" % (piece_id, lane["to_arm"])
            l["zone_id"] = zone_id
            l["piece_id"] = piece_id
            if not is_junction_piece:
                # intersection_kit.py stamps a 'turn' letter (S/L/R) on EVERY lane, including
                # plain segments/transitions, as internal steering-behavior metadata (see its
                # `assert (m["turn"] == "S") == (m["kind"] == "through")` invariant) -- but the
                # Godot-side consumer (WorldZoneManager.isSpawnCandidate) treats ANY non-empty
                # `turn` as "this lane is a junction connector, never spawn ambient traffic here"
                # (the old road_graph.py/assemble.py convention, where only junction connector
                # markers carried a turn meta at all). Left as-is, EVERY lane in a road_kit_authoring
                # district -- including ordinary straight road -- reads as a junction connector, so
                # findRoute() has zero legal spawn candidates and every ambient vehicle spawns
                # unrouted at the zone center, stacked on top of each other (reported as "vehicles
                # crash at a point rather than follow the path3d"). Blank `turn` for non-junction
                # (segment/transition) lanes here, matching the old convention exactly, so only real
                # junction-piece lanes are excluded from ambient spawn candidacy.
                l["turn"] = ""
            lanes_out.append(l)
        for arm in piece_dict.get("arms", []):
            a = dict(arm)
            a["name"] = "%s__%s" % (piece_id, arm["name"])
            a["zone_id"] = zone_id
            a["piece_id"] = piece_id
            arms_out.append(a)
        all_points.extend(derive_connection_points(piece_id, piece_dict))

    resolve_links(lanes_out)

    clusters = cluster_points(all_points, tolerance)
    reports = [classify_cluster(c) for c in clusters]
    order = {"ambiguous": 0, "isolated": 1, "paired": 2}
    reports.sort(key=lambda r: order[r["status"]])
    return {"lanes": lanes_out, "arms": arms_out}, reports


def resolve_links(lanes):
    """Turn each lane's SYMBOLIC references into concrete combined-namespace lane ids:
    `next_refs` -> `next` / `next_weights` / `next_kinds`, and `neighbor_in`/`neighbor_out` ->
    `inner_lane`/`outer_lane`.

    Resolution happens HERE because this is the only place that sees every piece. A piece is
    exported alone and cannot know what its siblings were named -- collection names are
    auto-numbered at build time, and every id is namespaced `<piece>__<id>` on the way in here.
    So `lane_export` emits "the piece in my group with role `branch_a`, its slot `A0`" and this
    pass looks it up.

    EXPLICIT CONNECTIVITY IS ADDITIVE, NEVER SUBTRACTIVE. Only lanes that actually carry
    references gain a `next`; every plain butt joint stays on the runtime's endpoint-proximity
    path exactly as before (`LaneGraph`). That matters because proximity is right for the
    overwhelming majority of joints and wrong only where several lane ends coincide -- a gore,
    where it cannot tell a mainline continuing from a ramp departing. A reference that does not
    resolve is dropped rather than guessed at, so a half-built group degrades to proximity instead
    of inventing a movement."""
    by_group = {}
    for l in lanes:
        g, r, slot = l.get("link_group"), l.get("link_role"), l.get("slot_id")
        if g and r and slot:
            by_group.setdefault((g, r, slot), l)
    # lane-change neighbours are always within the SAME piece
    by_piece_slot = {(l.get("piece_id"), l.get("slot_id")): l for l in lanes if l.get("slot_id")}
    for l in lanes:
        # in/out, not left/right: measured against the driving divide, so the answer does
        # not flip with `traffic_side`. OUTER is always toward the road edge, which is
        # where an exit ramp is. See `lane_profile.lane_neighbors`.
        for src, dst in (("neighbor_in", "inner_lane"), ("neighbor_out", "outer_lane")):
            nb = l.pop(src, None)
            if nb:
                other = by_piece_slot.get((l.get("piece_id"), nb))
                if other is not None:
                    l[dst] = other["id"]
        refs = l.pop("next_refs", None)
        if not refs:
            continue
        ids, weights, kinds = [], [], []
        for ref in refs:
            if ref.get("piece"):
                # A PIECE-addressed ref: an ordinary joint between two collections that meet, with
                # no structure name to key on (`lane_export.emit_joint_links`). `lane_id` is the
                # target's own pre-namespace id, which pins the exact lane when several slots
                # share an id across pieces -- the slot alone is not unique between two arbitrary
                # collections the way it is within one split group.
                tgt = by_piece_slot.get((ref["piece"], ref.get("slot")))
                if tgt is None and ref.get("lane_id"):
                    tgt = next((o for o in lanes if o.get("piece_id") == ref["piece"]
                                and o.get("id", "").endswith("__" + ref["lane_id"])), None)
            else:
                # `group` present = a reference into a DIFFERENT structure (two interchanges that
                # abut with no ordinary road between them); absent = within this lane's own.
                tgt = by_group.get((ref.get("group") or l.get("link_group"),
                                    ref.get("role"), ref.get("slot")))
            if tgt is None:
                continue
            ids.append(tgt["id"])
            weights.append(float(ref.get("weight", 1.0)))
            kinds.append(ref.get("kind", "THROUGH"))
        if ids:
            l["next"] = ids
            l["next_weights"] = weights
            l["next_kinds"] = kinds
    return lanes


def summarize_reports(reports):
    """Plain-text summary lines, most-actionable first -- what `tools/save_lane_kit.py` prints."""
    counts = {"ambiguous": 0, "isolated": 0, "paired": 0}
    for r in reports:
        counts[r["status"]] += 1
    lines = ["lane_kit: %d paired, %d isolated, %d ambiguous connection point cluster(s)"
             % (counts["paired"], counts["isolated"], counts["ambiguous"])]
    for r in reports:
        if r["status"] == "paired":
            continue
        lines.append("  [%s] %s at (%.2f, %.2f, %.2f)%s" % (
            r["status"].upper(), ", ".join(r["members"]), r["position"][0], r["position"][1],
            r["position"][2], ("" if not r["warnings"] else " -- " + "; ".join(r["warnings"]))))
    return lines


# --------------------------------------------------------------------------------- self-test

def self_test():
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import intersection_kit as ik

    # 1. Two segments meeting cleanly end-to-end -> exactly one 'paired' cluster. One-way
    # (lanes_backward=0) so each segment contributes exactly one lane/two endpoints -- a two-way
    # segment's forward/backward lanes sit at different lateral offsets and correctly form TWO
    # separate paired clusters (one per direction), which is a different, equally-valid case not
    # what this specific assertion is isolating.
    seg_a = ik.export_segment_dict((0.0, 0.0), (20.0, 0.0), lanes=1, lanes_backward=0, segment_id="A")
    seg_b = ik.export_segment_dict((20.0, 0.0), (40.0, 0.0), lanes=1, lanes_backward=0, segment_id="B")
    combined, reports = combine_pieces([("A", seg_a, "zoneX"), ("B", seg_b, "zoneX")])
    paired = [r for r in reports if r["status"] == "paired"]
    assert len(paired) == 1, "expected exactly one paired cluster, got %d" % len(paired)
    assert not reports[-1]["warnings"] or "paired" not in [r["status"] for r in reports], \
        "clean forward-forward stitch should not warn"
    print("OK: two segments meeting end-to-end -> one paired cluster")

    # 2. Namespacing + zone tagging: ids are piece-prefixed and carry the right zone_id.
    ids = {l["id"] for l in combined["lanes"]}
    assert all(i.startswith("A__") or i.startswith("B__") for i in ids), \
        "lane ids should be piece-namespaced: %r" % ids
    assert all(l["zone_id"] == "zoneX" for l in combined["lanes"])
    print("OK: lane ids namespaced by piece, zone_id tagged")

    # 3. A lone segment far from anything else -> isolated clusters at both its own ends.
    seg_c = ik.export_segment_dict((500.0, 500.0), (520.0, 500.0), lanes=1, lanes_backward=0,
                                    segment_id="C")
    _, reports_c = combine_pieces([("C", seg_c, "zoneY")])
    assert all(r["status"] == "isolated" for r in reports_c), \
        "a single unconnected segment's own ends should both be isolated: %r" % reports_c
    assert len(reports_c) == 2
    print("OK: an unconnected segment's two ends are both isolated")

    # 4. Three pieces' endpoints all landing within tolerance of one point -> ambiguous, not
    # three separate paired guesses. Each lane's own per-direction lateral offset (see test 1's
    # comment) means three segments approaching from three different headings won't land their
    # *offset* lane centerlines on the exact same point just because their *nominal* p0/p1
    # endpoints do -- force it directly on the exported points instead (same technique as test 6),
    # which is also the more realistic case: an authoring mistake that leaves three lanes each a
    # couple meters apart, all mutually within JUNCTION_RADIUS.
    seg_d = ik.export_segment_dict((0.0, 0.0), (20.0, 0.0), lanes=1, lanes_backward=0,
                                    segment_id="D")
    seg_e = ik.export_segment_dict((20.0, 0.0), (40.0, 0.0), lanes=1, lanes_backward=0,
                                    segment_id="E")
    seg_f = ik.export_segment_dict((20.0, 0.0), (20.0, -20.0), lanes=1, lanes_backward=0,
                                    segment_id="F")
    target = [20.0, 0.0, 0.0]
    seg_d["lanes"][0]["points"][-1] = list(target)
    seg_e["lanes"][0]["points"][0] = list(target)
    seg_f["lanes"][0]["points"][0] = list(target)
    _, reports_def = combine_pieces([("D", seg_d, "z"), ("E", seg_e, "z"), ("F", seg_f, "z")])
    ambiguous = [r for r in reports_def if r["status"] == "ambiguous"]
    assert len(ambiguous) == 1 and len(ambiguous[0]["members"]) == 3, \
        "three coincident endpoints should combine into one 3-member ambiguous cluster: %r" \
        % reports_def
    print("OK: three coincident endpoints flagged as one ambiguous cluster, not silently paired")

    # 5. A junction's own internal fan-out (several movements sharing one arm/lane's entry point)
    # must NOT be flagged as inter-piece ambiguity -- only the deduplicated `ports` list is
    # clustered, one connection point per arm/lane/direction, even though a >=3-arm junction has
    # more lane MOVEMENTS than ports at the shared entry point.
    arms = ik.preset_4way(lanes=1)
    junction = ik.export_dict(arms, kerb_radius=9.0, junction_id="J")
    assert len(junction["lanes"]) > len(junction["ports"]), \
        "sanity: a 4-way should have more movements than ports (fan-out exists to test against)"
    _, reports_j = combine_pieces([("J", junction, "z")])
    # Every arm has exactly lanes_in + lanes_out = 2 ports on a symmetric 1-lane 4-way = 8 ports
    # total, each its own piece (nothing else in the scene) -> every one isolated, none ambiguous.
    assert all(r["status"] == "isolated" for r in reports_j), \
        "an isolated junction's own internal fan-out must not read as ambiguous: %r" % reports_j
    assert len(reports_j) == len(junction["ports"]), \
        "cluster count should match port count (%d), not movement count (%d): got %d" % (
            len(junction["ports"]), len(junction["lanes"]), len(reports_j))
    print("OK: a junction's internal fan-out does not appear as inter-piece ambiguity")

    # 6. A segment authored to land exactly on one of that junction's arm ports stitches cleanly
    # (real integration, not just synthetic points).
    port = next(p for p in junction["ports"] if p["direction"] == "out")
    px, py = port["position"]   # export_dict (used directly, not export_json) keeps ports 2D
    # Build an arbitrary one-way segment, then force its start point exactly onto the port's
    # (padded-to-3D, see `_pt3`) position -- simpler and unambiguous than deriving real geometry
    # that happens to land there. One-way (lanes_backward=0) so there's exactly one lane endpoint
    # to pair against the port, not two laterally-offset ones.
    seg_g = ik.export_segment_dict((0.0, 500.0), (20.0, 500.0), lanes=1, lanes_backward=0,
                                    segment_id="G")
    seg_g["lanes"][0]["points"][0] = [px, py, 0.0]
    combined_jg, reports_jg = combine_pieces([("J", junction, "z"), ("G", seg_g, "z")])
    # Connection-point keys are "<piece_id>::<...>" (see derive_connection_points), distinct from
    # the "<piece_id>__<...>" namespacing combine_pieces applies to the OUTPUT lane/arm ids -- two
    # different namespaces for two different purposes, both piece_id-prefixed.
    matched = [r for r in reports_jg if r["status"] == "paired"
               and any(m.startswith("G::") for m in r["members"])
               and any(m.startswith("J::") for m in r["members"])]
    assert len(matched) == 1, "segment G's start should pair with junction J's out-port: %r" \
        % reports_jg
    # (This pair legitimately warns on tangent mismatch -- G's own line direction has nothing to
    # do with the port's real tangent, since only its endpoint was teleported for the test; a real
    # authored connection wouldn't trigger this.)
    print("OK: a segment authored onto a junction's arm port stitches into a paired cluster")

    # 7. Tolerance is respected: a point just outside JUNCTION_RADIUS does not pair.
    seg_h = ik.export_segment_dict((0.0, 0.0), (20.0, 0.0), lanes=1, lanes_backward=0,
                                    segment_id="H")
    seg_i = ik.export_segment_dict((20.0 + JUNCTION_RADIUS + 1.0, 0.0), (40.0, 0.0), lanes=1,
                                    lanes_backward=0, segment_id="I")
    _, reports_hi = combine_pieces([("H", seg_h, "z"), ("I", seg_i, "z")])
    assert all(r["status"] == "isolated" for r in reports_hi), \
        "endpoints beyond JUNCTION_RADIUS should not cluster together: %r" % reports_hi
    print("OK: endpoints beyond tolerance stay isolated (not falsely paired)")

    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
