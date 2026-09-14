"""point_record_ops.py -- the authoring REPAIRS and BRANCH gestures over the record, pure python3
(PLAN.md 3.1 B8).

The Blender operators in `point_ops` do these to Empties and collections. Authoring moved to the Godot
editor, where a road is a node whose CHILD ORDER is its chain, and the plugin reaches every rule that is
not a simple node edit through `roadkit_cli.py` -- so the rule lives once, here, over `NetworkData`,
and the Godot dock reloads the record the command rewrote (one undo step). Each function mutates `net`
and returns `(message, extra)`; the docstrings cite the operator whose rule they restate.

Where a Blender operator and a function here disagree, THIS is the owner: B9 retires the Blender
authoring panels and keeps only the pure modules.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "lib"))

try:
    from . import point_model as pm, point_profile as pp, point_solve as ps, point_validate as pv
except ImportError:
    import point_model as pm                                                 # noqa: E402
    import point_profile as pp                                               # noqa: E402
    import point_solve as ps                                                 # noqa: E402
    import point_validate as pv                                              # noqa: E402
import lane_profile as lp                                                    # noqa: E402

#: Precedence when the two rows of one pair disagree about the type (`RKA_OT_repair_links.RANK`):
#: a junction and a ramp are both things you went and did; SEGMENT is Extend Road's default.
RANK = {pm.LINK_SEGMENT: 0, pm.LINK_JUNCTION: 1, pm.LINK_AUX: 2}

#: `point_ops._MASK_GROUPS` -- which fields Apply Cross-Section copies per ticked group.
MASK_GROUPS = {
    "LANES": ("lanes_fwd", "lanes_bwd", "aux_fwd", "aux_bwd", "aux_side",
              "drop_side_fwd", "drop_side_bwd"),
    "WIDTH": ("lane_width", "shoulder_left_width", "shoulder_right_width",
              "parking_left_width", "parking_right_width"),
    "MEDIAN": ("median_width", "median_style"),
    "SIDES": ("left_kerb_height", "left_walk_width", "right_kerb_height", "right_walk_width"),
    "STRUCTURE": ("deck_thickness", "pillar_spacing", "pillar_skip", "pillar_offset"),
    "JUNCTION": ("fillet_radius", "allow_cross", "allow_uturn", "traffic_light"),
}


class GestureError(Exception):
    """A refused gesture. The message is the report the artist reads."""


def _road_of(net, uid):
    road = net.road_of(uid)
    if road is None:
        raise GestureError("%s is in no road" % uid)
    return road


def _unique_road_name(net, stem):
    name, n = stem, 1
    while name in net.roads:
        n += 1
        name = "%s%d" % (stem, n)
    return name


def complete_junction_cliques(net, seeds):
    """`point_ops.complete_junction_cliques`: every junction COMPONENT touching `seeds` becomes a clique
    of JUNCTION links with every member typed INTERSECTION. `(links_written, roles_fixed)`."""
    want = set(seeds)
    wrote = roles = 0
    for comp in net.junction_cliques():
        if want and not (want & set(comp)):
            continue
        for i, a in enumerate(comp):
            for b in comp[i + 1:]:
                if not net.points[a].has_link(b):
                    net.link(a, b, pm.LINK_JUNCTION)
                    wrote += 1
        for u in comp:
            if net.points[u].role != pm.INTERSECTION:
                net.points[u].role = pm.INTERSECTION
                roles += 1
    return wrote, roles


# ------------------------------------------------------------------------------- merge / split

def merge_points(net, uids, keep_uid=None, at_keep=False):
    """`RKA_OT_merge_points`: collapse a CONTIGUOUS run of ONE road into its first point (or `keep_uid`),
    carrying every link that left the run, at the run's centroid (or the kept point with `at_keep`).
    A merged station that inherits a JUNCTION link is a mouth, so its pad is completed (8q)."""
    uids = [u for u in uids if u in net.points]
    if len(uids) < 2:
        raise GestureError("select 2 or more points of one road")
    road = _road_of(net, uids[0])
    if any(net.road_of(u) is not road for u in uids):
        raise GestureError("all selected points must be in the same road -- two points in different "
                           "roads are joined with Connect / Make Intersection")
    chain = [u for u in road.points if u in net.points]
    idx = sorted(chain.index(u) for u in uids)
    if idx != list(range(idx[0], idx[0] + len(idx))):
        raise GestureError("select points that are next to each other in the chain")
    doomed = [chain[i] for i in idx]
    keep = keep_uid if keep_uid in doomed else doomed[0]
    gone = [u for u in doomed if u != keep]
    if at_keep:
        pos = net.points[keep].pos
    else:
        pos = tuple(sum(net.points[u].pos[k] for u in doomed) / len(doomed) for k in range(3))
    moved = 0
    for u in gone:
        for l in list(net.points[u].links):
            if l.target in doomed or l.target not in net.points:
                continue
            ltype, other = l.type, l.target
            # AUX is directed: keep the direction the row had (mainline -> ramp).
            net.unlink(u, other)
            if not net.points[keep].has_link(other) and not net.points[other].has_link(keep):
                if ltype == pm.LINK_AUX:
                    net.link(keep, other, pm.LINK_AUX)
                else:
                    net.link(keep, other, ltype)
                moved += 1
        # ...and an AUX row that pointed INTO the doomed point from a mainline.
        for p in net.points.values():
            for l in list(p.links):
                if l.target == u and l.type == pm.LINK_AUX and p.uid not in doomed:
                    p.unlink(u)
                    if not p.has_link(keep):
                        p.link_to(keep, pm.LINK_AUX)
                        moved += 1
    for a in doomed:
        for b in doomed:
            if a != b:
                net.points[a].unlink(b)
    for u in gone:
        net.remove_point(u)
    net.points[keep].pos = pos
    wrote, roles = complete_junction_cliques(net, [keep])
    return ("merged %d point(s) into %s (%d link(s) carried over%s)"
            % (len(doomed), keep, moved, ", pad completed" if wrote or roles else ""),
            {"keep": keep})


def split_road(net, uids, name=""):
    """`RKA_OT_split_road`: move the selected points of one road into a new road that inherits the
    source's road fields and base profile. Links are by uid, so every link survives the move."""
    uids = [u for u in uids if u in net.points]
    if not uids:
        raise GestureError("select the points to move out")
    src = _road_of(net, uids[0])
    if any(net.road_of(u) is not src for u in uids):
        raise GestureError("every selected point must be in the SAME road")
    if len(uids) >= len(src.points):
        raise GestureError("that is the whole of %s -- rename the road instead" % src.name)
    dst_name = _unique_road_name(net, name or (src.name + "_split"))
    moving = [u for u in src.points if u in set(uids)]
    dst = _clone_road(net, src, dst_name, moving)
    return "%d point(s) -> %s" % (len(moving), dst.name), {"road": dst.name}


def _clone_road(net, src, name, moving):
    kw = {n: getattr(src, n) for n, _k, _d in pm.ROAD_FIELDS if n != "name"}
    dst = pm.RoadData(name, src.base.copy(), (), **kw)
    net.add_road(dst)
    for u in moving:
        src.points.remove(u)
        dst.points.append(u)
    return dst


# ------------------------------------------------------------------------------- repairs

def renumber_roads(net):
    """`RKA_OT_renumber_roads`: each road's point ORDER follows its own links (`point_model.link_order`).
    In Godot the order is the child order, so this is the repair for a point dragged out of place in
    the scene tree. A road whose links branch is left alone and reported."""
    moved, tangled_roads = 0, []
    for name in sorted(net.roads):
        road = net.roads[name]
        comps, tangled = pm.link_order(net, road)
        if tangled:
            tangled_roads.append(name)
        order = [u for c in comps for u in c] + tangled
        order += [u for u in road.points if u not in order]
        if order != road.points:
            moved += sum(1 for a, b in zip(order, road.points) if a != b)
            road.points = order
    msg = "reordered %d point(s)" % moved
    if tangled_roads:
        msg += "; left %s alone (links branch)" % ", ".join(tangled_roads)
    return msg, {"tangled": tangled_roads}


def repair_links(net):
    """`RKA_OT_repair_links` over the record: drop impossible rows (dangling, self, duplicate), resolve a
    pair's type conflict (AUX > JUNCTION > SEGMENT), drop the ramp's half of an AUX pair, restore the
    missing half of a SEGMENT/JUNCTION link, and complete every junction component into a clique."""
    in_road = {u for r in net.roads.values() for u in r.points}
    dropped = retyped = restored = 0
    for p in net.points.values():
        seen, keep = set(), []
        for l in p.links:
            if l.target == p.uid or l.target not in net.points or l.target not in in_road \
                    or l.target in seen:
                dropped += 1
                continue
            seen.add(l.target)
            keep.append(l)
        p.links = keep
    for p in net.points.values():
        for l in p.links:
            back = next((x for x in net.points[l.target].links if x.target == p.uid), None)
            if back is not None and back.type != l.type:
                win = l.type if RANK[l.type] >= RANK[back.type] else back.type
                l.type = back.type = win
                retyped += 1
    for p in list(net.points.values()):
        for l in list(p.links):
            other = net.points[l.target]
            if l.type == pm.LINK_AUX:
                dropped += other.unlink(p.uid)
                continue
            if not other.has_link(p.uid):
                other.link_to(p.uid, l.type)
                restored += 1
    wrote, roles = complete_junction_cliques(net, ())
    restored += wrote
    parts = ["%d %s" % (n, what) for n, what in
             ((dropped, "link(s) dropped"), (restored, "half-link(s) restored"),
              (retyped, "type conflict(s) resolved"), (roles, "mouth role(s) fixed")) if n]
    return "; ".join(parts) if parts else "nothing to repair", {}


def tidy_roads(net):
    """`RKA_OT_tidy_roads`: (1) a point with no SEGMENT link inside its own road whose SEGMENT links all
    land in ONE other road moves there, next to the neighbour it joins; (2) a road holding more than one
    corridor (`point_model.road_corridors`) splits, a corridor something AUX-links into named
    `<road>_ramp`; (3) an emptied road is removed."""
    moved = split = 0
    for uid in sorted(net.points):
        here = net.road_of(uid)
        if here is None:
            continue
        segs = [t for t in net.points[uid].targets(pm.LINK_SEGMENT) if t in net.points]
        if not segs or any(net.road_of(t) is here for t in segs):
            continue
        homes = {net.road_of(t).name for t in segs if net.road_of(t) is not None}
        if len(homes) != 1:
            continue
        dst = net.roads[homes.pop()]
        anchor = min((t for t in segs if t in dst.points), key=lambda t: dst.points.index(t))
        here.points.remove(uid)
        dst.points.insert(dst.points.index(anchor) + 1, uid)
        moved += 1
    aux_targets = {t for _m, t in net.aux_pairs()}
    for name in sorted(net.roads):
        road = net.roads.get(name)
        corridors = pm.road_corridors(net, road) if road is not None else []
        for k, corridor in enumerate(corridors[1:], start=1):
            stem = "%s_ramp" % name if any(u in aux_targets for u in corridor) else "%s_%d" % (name, k + 1)
            _clone_road(net, road, _unique_road_name(net, stem), list(corridor))
            split += 1
    empty = [n for n, r in net.roads.items() if not r.points]
    for n in empty:
        del net.roads[n]
    if not (moved or split or empty):
        return "every point is already in the right road", {}
    bits = ["%d point(s) re-filed" % moved, "%d corridor(s) split into their own road" % split]
    if empty:
        bits.append("%d empty road(s) removed" % len(empty))
    return ", ".join(bits), {}


def apply_cross_section(net, src_uid, uids, groups):
    """`RKA_OT_apply_cross_section`: copy the ticked field GROUPS from `src_uid` to every other point in
    `uids`, which become OVERRIDE (a copied section is authored on the point, not inherited)."""
    if src_uid not in net.points:
        raise GestureError("no source point")
    targets = [u for u in uids if u in net.points and u != src_uid]
    if not targets:
        raise GestureError("need a source point and at least one other selected")
    bad = [g for g in groups if g not in MASK_GROUPS]
    if bad or not groups:
        raise GestureError("pick one or more of %s -- nothing is copied by default" % ", ".join(sorted(MASK_GROUPS)))
    fields = [f for g in groups for f in MASK_GROUPS[g]]
    src = net.points[src_uid]
    for u in targets:
        for f in fields:
            setattr(net.points[u], f, getattr(src, f))
        net.points[u].profile_mode = pm.OVERRIDE
    return "%d field(s) -> %d point(s)" % (len(fields), len(targets)), {}


# ------------------------------------------------------------------------------- ramps

def open_aux_slot(net, main_uid, lanes, field, entrance):
    """`point_ops.open_aux_slot` over the record: open the slot back along the run to the first span long
    enough for the taper the gate asks for (`point_validate.taper_min_length`), so a one-click ramp does
    not leave the gate red. Returns `(stations, span, want)`."""
    road = net.road_of(main_uid)
    res = net.resolved(main_uid)
    width = lanes * res.lane_width
    want = pv.taper_min_length(width, res.design_speed, getattr(road, "taper_factor", 1.0))
    run = pm.run_of(net, main_uid)
    step = -1 if (field == "aux_fwd") != bool(entrance) else 1
    j, chain, span = run.index(main_uid), [main_uid], 0.0
    while True:
        p = net.points[chain[-1]]
        setattr(p, field, max(getattr(p, field), lanes))
        k = j + step
        if not (0 <= k < len(run)):
            span = 0.0
            break
        a, b = net.points[run[j]].pos, net.points[run[k]].pos
        span = math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))
        if span >= want:
            break
        chain.append(run[k])
        j = k
    return len(chain), span, want


def align_ramp(net, main_uid, ramp_uid):
    """`Align Ramp To Aux`: the mouth on the gore line, faced down the mainline (MANUAL). False when the
    mainline declares no aux slot to align to."""
    got = ps.ramp_target(net, main_uid, ramp_uid)
    if got is None:
        return False
    pos, ax, _side = got
    ax = ps.ramp_facing(net, main_uid, ramp_uid) or ax
    ramp = net.points[ramp_uid]
    ramp.pos = tuple(pos)
    ramp.tangent_mode = pm.MANUAL
    ramp.tangent = (ax[0], ax[1], 0.0)
    return True


def resolve_aux_pair(net, a, b):
    """`(mainline_uid, ramp_uid)` -- which of two points is the mainline is a fact about the two points
    (8i.2), never click order: scored on who declares an aux slot, who is typed a ramp, who is one-way."""
    pa, pb = net.points[a], net.points[b]

    def declares_aux(p):
        return int(p.aux_fwd) + int(p.aux_bwd) > 0

    def score(main, ramp):
        s = 0
        if declares_aux(main):
            s += 3
        if pm.is_ramp_role(ramp.role):
            s += 2
        if pm.is_ramp_role(main.role):
            s -= 2
        if declares_aux(ramp):
            s -= 1
        if ramp.lanes_bwd == 0 or ramp.lanes_fwd == 0:
            s += 1
        if main.lanes_bwd == 0 or main.lanes_fwd == 0:
            s -= 1
        return s
    return (a, b) if score(pa, pb) >= score(pb, pa) else (b, a)


def make_ramp(net, uid_a, uid_b, lanes=1):
    """`Make Ramp` + `Align Ramp To Aux`: an AUX link mainline -> ramp (direction resolved, not clicked),
    the ramp one-way and typed RAMP, the aux slot opened on the carriageway the mouth is on and back to a
    taper-length span, and the mouth placed on the gore line facing down the mainline."""
    main_uid, ramp_uid = resolve_aux_pair(net, uid_a, uid_b)
    ramp = net.points[ramp_uid]
    ramp.role = pm.RAMP
    if not ramp.lanes_fwd and not ramp.lanes_bwd:
        ramp.lanes_fwd = lanes
    elif ramp.lanes_fwd and ramp.lanes_bwd:
        ramp.lanes_bwd = 0
    ramp.profile_mode = pm.OVERRIDE
    field = "aux_fwd" if ps.ramp_carriageway(net, main_uid, ramp.pos) == lp.FWD else "aux_bwd"
    net.unlink(main_uid, ramp_uid)
    net.link(main_uid, ramp_uid, pm.LINK_AUX)
    entrance = pm.ramp_is_entrance(net, ramp_uid)
    stations, span, want = open_aux_slot(net, main_uid, lanes, field, entrance)
    aligned = align_ramp(net, main_uid, ramp_uid)
    return {"mainline": main_uid, "ramp": ramp_uid, "field": field, "entrance": entrance,
            "slot_stations": stations, "taper_span": span, "taper_want": want, "aligned": aligned}


def branch_ramp(net, main_uid, name="", aux_lanes=1, carriageway="FWD", entrance=False,
                length=80.0, spread=25.0, drop=0.0):
    """`RKA_OT_branch_ramp`: a NEW one-way ramp road leaving (or joining) `main_uid`, which may be any
    station of its corridor. The aux slot is opened over the taper length, the mouth is placed and faced
    by `align_ramp`, and the second station is bent OUTBOARD (`point_solve.ramp_target`'s side)."""
    if main_uid not in net.points:
        raise GestureError("no mainline point")
    main_road = _road_of(net, main_uid)
    field = "aux_fwd" if carriageway == "FWD" else "aux_bwd"
    stations, span, want = open_aux_slot(net, main_uid, aux_lanes, field, entrance)
    res = net.resolved(main_uid)
    rname = _unique_road_name(net, name or "%s_ramp" % main_road.name)
    fwd, bwd = (0, aux_lanes) if entrance else (aux_lanes, 0)
    base = pm.PointData(uid="", lanes_fwd=fwd, lanes_bwd=bwd, lane_width=res.lane_width,
                        median_width=0.0, design_speed=max(30.0, res.design_speed - 20.0))
    road = net.add_road(pm.RoadData(rname, base, (), road_class="ramp",
                                    ped_access=getattr(main_road, "ped_access", False)))
    mouth = net.add_station(road, net.points[main_uid].pos)
    mouth.role = pm.RAMP
    mouth.lanes_fwd, mouth.lanes_bwd = fwd, bwd
    mouth.profile_mode = pm.OVERRIDE
    net.link(main_uid, mouth.uid, pm.LINK_AUX)
    if not align_ramp(net, main_uid, mouth.uid):
        raise GestureError("%s declares no aux slot to branch from" % main_uid)
    _want, ax, side = ps.ramp_target(net, main_uid, mouth.uid)
    along = (ax[0], ax[1])
    if (carriageway == "BWD") != bool(entrance):
        along = (-along[0], -along[1])
    outward = (-ax[1] * side, ax[0] * side)
    far_pos = (mouth.pos[0] + along[0] * length + outward[0] * spread,
               mouth.pos[1] + along[1] * length + outward[1] * spread,
               mouth.pos[2] + drop)
    far = net.add_station(road, far_pos)
    far.lanes_fwd, far.lanes_bwd = fwd, bwd
    net.link(mouth.uid, far.uid, pm.LINK_SEGMENT)
    # RE-ALIGN NOW THE RAMP HAS A DIRECTION. With one station the ramp's own axis is undefined, and
    # `ramp_target` reads which of the ramp's edges lands on the gore line off it -- so a reverse-
    # carriageway exit aligned before its second station existed sat one lane width off the line
    # (`ramp_edge_residual` 4.50 m). The far station is placed from the first alignment and stays.
    align_ramp(net, main_uid, mouth.uid)
    short = span < want - 1e-6
    return ("%s: %d-lane %s off %s; aux slot on %d station(s), opens over %.0f m%s"
            % (rname, aux_lanes, "entrance" if entrance else "exit", main_uid, stations, span,
               (" (wants %.0f)" % want) if short else "")), {"road": rname, "mouth": mouth.uid, "far": far.uid}


# ------------------------------------------------------------------------------- facings

def facings(net):
    """`{uid: (x, y, z)}` -- `point_profile.chain_facings`, the direction the tool gives a point it owns
    (AUTO). The Godot plugin faces AUTO points with it and stamps the baseline a hand rotation is
    measured against (`point_model.was_rotated`'s rule)."""
    return pp.chain_facings(net)


# ------------------------------------------------------------------------------- self-test

def self_test():
    ok = 0

    def road(net, name, xs, y=0.0, **kw):
        r = net.add_road(pm.RoadData(name, pm.PointData(uid=""), (), **kw))
        prev = None
        for x in xs:
            p = net.add_station(r, (x, y, 0.0))
            if prev is not None:
                net.link(prev.uid, p.uid)
            prev = p
        return r

    # merge: a run of three collapses into the first, keeps the outside links, centroid position.
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100, 150, 200])
    pts = list(a.points)
    msg, extra = merge_points(net, pts[1:4])
    assert extra["keep"] == pts[1] and len(a.points) == 3, (msg, a.points)
    assert net.points[pts[1]].has_link(pts[0]) and net.points[pts[1]].has_link(pts[4])
    assert abs(net.points[pts[1]].pos[0] - 100.0) < 1e-9
    ok += 1
    try:
        merge_points(net, [pts[0], pts[4]])
        raise AssertionError("non-contiguous merge accepted")
    except GestureError:
        ok += 1

    # merge into a junction completes the pad (8q).
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100])
    b = road(net, "b", [100, 150], y=10.0)
    c = road(net, "c", [100, 150], y=-10.0)
    for u, v in ((a.points[2], b.points[0]), (a.points[2], c.points[0]), (b.points[0], c.points[0])):
        net.link(u, v, pm.LINK_JUNCTION)
    for u in (a.points[2], b.points[0], c.points[0]):
        net.points[u].role = pm.INTERSECTION
    keep = a.points[1]
    merge_points(net, [a.points[1], a.points[2]])
    comp = [x for x in net.junction_cliques() if keep in x][0]
    assert len(comp) == 3 and all(net.points[u].role == pm.INTERSECTION for u in comp)
    assert all(net.points[u].has_link(w) for u in comp for w in comp if u != w)
    ok += 1

    # split keeps links; tidy re-files a stray and splits a second corridor.
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100, 150])
    moving = a.points[2:]
    split_road(net, moving, "a_ramp")
    assert net.roads["a_ramp"].points == moving and net.points[a.points[1]].has_link(moving[0])
    ok += 1
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100])
    b = road(net, "b", [500, 550])
    stray = net.add_station(a, (150.0, 0.0, 0.0))      # filed in a, joined to nothing in a...
    a.points.remove(stray.uid)
    b.points.append(stray.uid)                           # ...but actually filed in b
    net.link(a.points[-1], stray.uid)                    # joined to a's tail only
    tidy_roads(net)
    assert stray.uid in net.roads["a"].points and stray.uid not in net.roads["b"].points
    ok += 1
    net = pm.NetworkData()
    a = road(net, "a", [0, 50])
    extra_pts = [net.add_station(a, (x, 90.0, 0.0)) for x in (0, 50)]
    net.link(extra_pts[0].uid, extra_pts[1].uid)
    tidy_roads(net)
    assert "a_2" in net.roads and net.roads["a_2"].points == [p.uid for p in extra_pts]
    ok += 1

    # renumber: an order the links contradict is put back.
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100])
    right = list(a.points)
    a.points = [right[0], right[2], right[1]]
    renumber_roads(net)
    assert a.points == right, a.points
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100, 150, 200])
    right = list(a.points)
    # The HEAD dragged to the tail. (On three points this is genuinely ambiguous -- it is equally the
    # middle point dragged to the head of a reversed road -- so the case is a longer road.)
    a.points = right[1:] + right[:1]
    renumber_roads(net)
    assert a.points == right, ("reversed the road", a.points)
    ok += 1

    # repair: a half link restored, a dangling row dropped, a type conflict resolved upward.
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100])
    p0, p1, p2 = a.points
    net.points[p1].unlink(p0)
    net.points[p2].link_to("p_deadbeef")
    net.points[p1].links[0].type = pm.LINK_JUNCTION
    repair_links(net)
    assert net.points[p1].has_link(p0) and not net.points[p2].has_link("p_deadbeef")
    ok += 1

    # apply cross-section copies only the ticked group and marks OVERRIDE.
    net = pm.NetworkData()
    a = road(net, "a", [0, 50, 100])
    net.points[a.points[0]].lanes_fwd = 3
    net.points[a.points[0]].left_walk_width = 4.0
    apply_cross_section(net, a.points[0], a.points[1:], ["LANES"])
    assert net.points[a.points[2]].lanes_fwd == 3 and net.points[a.points[2]].left_walk_width != 4.0
    assert net.points[a.points[2]].profile_mode == pm.OVERRIDE
    ok += 1

    # branch ramp: an exit on either carriageway and an entrance, each leaving the gate green.
    for cw, ent in (("FWD", False), ("BWD", False), ("FWD", True)):
        net = pm.NetworkData()
        hwy = net.add_road(pm.RoadData("hwy", pm.PointData(uid="", lanes_fwd=2, lanes_bwd=2,
                                                          design_speed=80.0), (), road_class="expressway"))
        prev = None
        for x in (0, 300, 600, 900, 1200):
            p = net.add_station(hwy, (x, 0.0, 0.0))
            if prev is not None:
                net.link(prev.uid, p.uid)
            prev = p
        branch_ramp(net, hwy.points[2], carriageway=cw, entrance=ent)
        errs = pv.errors(pv.validate(net))
        assert not errs, (cw, ent, [(f.code, f.message) for f in errs])
        ok += 1

    print("point_record_ops.py: %d checks PASS" % ok)


if __name__ == "__main__":
    self_test()
