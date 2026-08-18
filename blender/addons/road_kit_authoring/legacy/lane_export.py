"""lane_export.py -- per-piece lane-dict reconstruction, shared by `tools/save_lane_kit.py` (the
`.lanekit.json` sidecar writer) and `ops_lane_preview.py` (the interactive "Preview Lane Curves"
button). 2026-08: this logic used to live only in `tools/save_lane_kit.py`, which imported the
addon (`from road_kit_authoring import ops_intersection as opint`) to reach it -- the CLI tool
depended on the addon, not the other way around, so the addon itself couldn't reuse this code
without extra `sys.path` surgery. Moved here unchanged (pure move, no behavior change) so both the
CLI export and the interactive preview button call the SAME functions and can never drift apart.
Lives in the addon (not the bpy-free `lib/lane_kit.py`) because it reads live scene objects via
`ops_intersection.local_object`/`ops_segment._spine_control_points` -- genuinely bpy-dependent.

Every piece collection in the file (`ops_intersection._is_piece_collection`) is rebuilt into its
`export_*_dict` form straight from its own `rka_*` custom properties -- the same permanent
build-settings record `custom_props.write_build_settings` already writes at build/rebuild time, so
neither caller needs a separate "did you remember to set an export path" step per piece. Piece-type
dispatch mirrors `ops_intersection._rebuild_piece_in_place`'s exact check order (a transition's
`rka_lanes_a` MUST be checked before the GN-segment `rka_curve_object` check, since a transition
also carries `rka_curve_object`)."""
from . import ops_intersection as opint
from . import ops_segment as opseg
from . import custom_props
from . import spine_io

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


def _lane_surface_z(scene):
    return scene.rka.lane_surface_z


def _export_intersection(coll, scene, godot_space=True):
    k = ik()
    arms = custom_props.read_arms_full(coll, k.Arm)
    origin = custom_props.read_origin(coll)
    if arms is None or origin is None or len(arms) < 3:
        return None
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    tail_length = coll.get("rka_tail_length", 12.0)
    segments = coll.get("rka_segments", 8)
    lane_map = custom_props.read_lane_map_override(coll)
    z = origin[2] + _lane_surface_z(scene)
    # `export_dict`'s own geometry is junction-LOCAL (see its docstring) -- `center=(origin[0],
    # origin[1])` is REQUIRED, not optional, regardless of `godot_space` below: omitting it
    # silently exported every off-origin intersection at the wrong world position (found in the
    # original save_lane_kit.py session).
    d = k.export_dict(arms, kerb_radius, junction_id=coll.name, segments=segments,
                       tail_length=tail_length, lane_map=lane_map, center=(origin[0], origin[1]))
    if godot_space:
        # Same z-lift AND axis remap `intersection_kit.export_json` applies (Blender Z-up -> Godot
        # Y-up: height becomes the 2nd coordinate, northing negates into the 3rd) -- done by hand
        # here so this can call the dict-only `export_dict` directly instead of round-tripping
        # through a temp file. This is the shape `.lanekit.json`/`WorldBaker` need.
        for lane in d["lanes"]:
            lane["points"] = [[p[0], z, -p[1]] for p in lane["points"]]
        for port in d["ports"]:
            port["position"] = [port["position"][0], z, -port["position"][1]]
    else:
        # `godot_space=False` (2026-08, `ops_lane_preview.py`'s "Preview Lane Curves"): keep
        # points in plain Blender-native world space (x, y, z=height) instead -- the point is to
        # sit a preview curve directly over the authored mesh in the SAME space you're looking at
        # it in, not to reproduce the exported file's own axis convention (see that module's
        # docstring for why).
        for lane in d["lanes"]:
            lane["points"] = [[p[0], p[1], z] for p in lane["points"]]
        for port in d["ports"]:
            port["position"] = [port["position"][0], port["position"][1], z]
    return d


def _export_gn_segment(coll, godot_space=True):
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return None
    spine_obj = opint.local_object(spine_name)
    if not spine_io.is_spine(spine_obj):
        return None
    # Raw control points, NOT the GN-evaluated pavement-sweep mesh -- see
    # `ops_segment._spine_control_points`'s own docstring for why `to_mesh()` would be wrong here.
    spine = opseg._spine_control_points(spine_obj)
    if len(spine) < 2:
        return None
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    # A piece that carries a real `rka_profile` exports from THAT, not from the scalars -- it is
    # the only description that can express a lane which exists over part of the piece only (a
    # ramp opening, an auxiliary lane tapering in). The scalar path below cannot: it emits N
    # full-length lanes, which is precisely why a split had to be several pieces and why the
    # interchange merges in `island_v3_roads.blend` contributed no usable lane data.
    if custom_props.PROFILE_KEY in coll.keys():
        ps = custom_props.read_profile(coll)
        if ps is not None:
            import lane_profile as _lp
            d = _lp.export_segment_from_profile_dict(
                spine, ps, segment_id=coll.name, traffic_side=traffic_side,
                godot_space=godot_space)
            _stamp_links(coll, d)
            return d
    return ik().export_segment_from_spine_dict(
        spine, lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        segment_id=coll.name, traffic_side=traffic_side, godot_space=godot_space)



# Which role continues into which, and what the movement MEANS to an AI. Keyed by the role a piece
# plays in its `rka_link_group` (stamped by `ops_split`).
#
# A split's trunk feeds both branches -- but not lane-for-lane arbitrarily: a lane continues into
# the branch that adopted ITS OWN SLOT ID (`B*` stay on the mainline, `A*` become the ramp), which
# is exactly what the slot id was made stable for. A merge is the same relation reversed.
# `THROUGH` vs `EXIT`/`ENTRY` is the distinction endpoint proximity fundamentally cannot make --
# at a gore every lane end is within a few metres of every other, so geometry alone cannot tell a
# mainline continuing from a ramp departing, which is what an AI chasing a target through an
# interchange needs to know.
_LINK_RULES = {
    # role      -> [(target role, slot prefix, movement kind)]
    ("split", "trunk"): [("branch_b", "B", "THROUGH"), ("branch_a", "A", "EXIT")],
    ("merge", "branch_b"): [("trunk", "B", "THROUGH")],
    ("merge", "branch_a"): [("trunk", "A", "ENTRY")],
}


def _prop_str(coll, key):
    v = coll.get(key)
    if not v:
        return ""
    return "".join(v) if not isinstance(v, str) else v


def _carriageway_links(coll, d, group, role):
    """Successor refs for the ONE-PIECE carriageway model (`ROAD_KIT_REDESIGN.md` 2.3-2.5).

    The old `_LINK_RULES` table is keyed by the three-piece split's roles (`trunk`/`branch_a`/
    `branch_b`) and decides merge-vs-split from `"_merge"` being in the group name. A carriageway
    piece is `link_role='mainline'` in group `LOOP_A`, and each ramp is its own piece whose role
    is the interchange id -- so no rule matched and NOTHING was emitted. Measured: 717 lanes, zero
    successors, no movement kinds. The links were never missing as a feature; the table simply did
    not describe this shape.

    The relation is read off the SLOT ID, which is what stable ids were for: a mainline slot named
    `IC_YAMATE_A0` is the auxiliary lane belonging to the piece whose role is `IC_YAMATE`, and it
    hands over to that piece's own `A0`. Direction comes from the piece props the builder stamps:
    `rka_link_exits` lists the interchanges this carriageway EXITS to, `rka_link_entries` those it
    receives from, and a ramp carries its own `rka_link_kind`.

    A directed edge is emitted by its SOURCE only -- the mainline owns an EXIT, the ramp owns an
    ENTRY -- so no edge is written twice from both ends."""
    exits = set(filter(None, _prop_str(coll, "rka_link_exits").split(",")))
    entries = set(filter(None, _prop_str(coll, "rka_link_entries").split(",")))
    kind = _prop_str(coll, "rka_link_kind")
    for lane in d.get("lanes", []):
        lane["link_group"] = group
        lane["link_role"] = role
        slot = lane.get("slot_id") or ""
        refs = []
        if role == "mainline":
            # `<rid>_A0` -> that ramp piece's own `A0`, but only where this carriageway is the
            # one that EXITS (an entry's edge belongs to the ramp, below).
            if slot.endswith("_A0"):
                rid = slot[:-3]
                if rid in exits:
                    refs.append({"role": rid, "slot": "A0", "kind": "EXIT", "weight": 1.0})
        elif kind == "ENTRY" and slot == "A0":
            refs.append({"role": "mainline", "slot": "%s_A0" % role,
                         "kind": "ENTRY", "weight": 1.0})
        if refs:
            lane["next_refs"] = refs
    return d


def _stamp_links(coll, d):
    """Attach this piece's group/role and its SYMBOLIC successor references to every lane.

    Symbolic ("the piece in my group with role `branch_a`, its slot `A0`") rather than a concrete
    lane id, because a piece is exported on its own and cannot know what its siblings ended up
    being called -- collection names are auto-numbered at build time, and `lane_kit.combine_pieces`
    namespaces every id again on the way into the combined sidecar. The combiner sees all pieces,
    so that is where the references are resolved."""
    group = coll.get("rka_link_group")
    role = coll.get("rka_link_role")
    if not group or not role:
        return d
    group = "".join(group) if not isinstance(group, str) else group
    role = "".join(role) if not isinstance(role, str) else role
    # The one-piece carriageway model has its own relation -- see `_carriageway_links`.
    if role == "mainline" or coll.get("rka_link_kind"):
        return _carriageway_links(coll, d, group, role)
    kind = "merge" if "_merge" in group else "split"
    rules = _LINK_RULES.get((kind, role), [])
    for lane in d.get("lanes", []):
        lane["link_group"] = group
        lane["link_role"] = role
        slot = lane.get("slot_id") or ""
        refs = [{"role": tgt_role, "slot": slot, "kind": mv, "weight": 1.0}
                for tgt_role, prefix, mv in rules if slot.startswith(prefix)]
        # Chain to the NEXT structure when the two abut directly. Only the mainline continues
        # (`B*` slots on a split's branch_b); an exit ramp has left the carriageway by then.
        nxt = coll.get("rka_link_next_group")
        nxt = ("".join(nxt) if not isinstance(nxt, str) else nxt) if nxt else ""
        if nxt and role == "branch_b" and slot.startswith("B"):
            refs.append({"group": nxt, "role": "trunk", "slot": slot,
                         "kind": "THROUGH", "weight": 1.0})
        if refs:
            lane["next_refs"] = refs
    return d


def _export_transition(coll, godot_space=True):
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return None
    spine_obj = opint.local_object(spine_name)
    if not spine_io.is_spine(spine_obj):
        return None
    spine = opseg._spine_control_points(spine_obj)
    if len(spine) < 2:
        return None
    p0, p1 = spine[0], spine[-1]
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes_a = coll.get("rka_lanes_a", 2)
    lanes_b = coll.get("rka_lanes_b", 1)
    lanes_backward_a = coll.get("rka_lanes_backward_a", 0) or None
    lanes_backward_b = coll.get("rka_lanes_backward_b", 0) or None
    align = coll.get("rka_align", 'right')
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    return ik().export_lane_transition_dict(
        p0, p1, lane_width=lane_width, lanes_a=lanes_a, lanes_b=lanes_b,
        lanes_backward_a=lanes_backward_a, lanes_backward_b=lanes_backward_b, align=align,
        segment_id=coll.name, traffic_side=traffic_side, godot_space=godot_space)


def _export_point_segment(coll, scene, godot_space=True):
    if "rka_p0" not in coll.keys() or "rka_p1" not in coll.keys():
        return None
    p0_raw, p1_raw = coll["rka_p0"], coll["rka_p1"]
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    bend = coll.get("rka_bend", 0.0)
    bend_z = coll.get("rka_bend_z", 0.0)
    curve_segments = coll.get("rka_curve_segments", 8)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    z = float(p0_raw[2]) + _lane_surface_z(scene)
    return ik().export_segment_dict(
        (p0_raw[0], p0_raw[1]), (p1_raw[0], p1_raw[1]), lane_width=lane_width, lanes=lanes,
        segment_id=coll.name, z=z, bend=bend, segments=curve_segments, z0=0.0,
        z1=float(p1_raw[2]) - float(p0_raw[2]), bend_z=bend_z, lanes_backward=lanes_backward,
        traffic_side=traffic_side, godot_space=godot_space)


def export_piece_dict(coll, scene, godot_space=True):
    """Dispatch mirrors `ops_intersection._rebuild_piece_in_place`'s own check order exactly --
    keep the two in sync if either changes. `scene` supplies the Scene-level `lane_surface_z` RKA
    setting (not a per-piece one) -- needed by the intersection AND plain point-segment paths.

    `godot_space` (default True, `save_lane_kit.py`'s existing behavior, unchanged) applies to
    EVERY piece type, intersection included. 2026-08, user-reported ("lane for segment is in
    totally different position [than] the actual... segment mesh"): this docstring used to claim
    "segment/transition/point-segment lane points are already plain Blender-native world-space...
    no axis remap ever applied to them either way" -- that was WRONG. `intersection_kit.py`'s own
    `export_segment_from_spine_dict`/`export_lane_transition_dict`/`export_segment_dict` all
    unconditionally applied the Godot `[x, z, -y]` remap regardless of caller intent, and this
    module's own `_export_gn_segment`/`_export_transition`/`_export_point_segment` never even
    accepted a `godot_space` argument to pass down -- so `ops_lane_preview.py`'s Blender-native
    preview (`godot_space=False`) silently got Godot-space points for every segment/transition/
    point-segment piece anyway, while only the intersection path (which DID already thread the
    flag through) previewed correctly. Fixed on both sides (see each function's own docstring for
    the confirmed repro) -- `godot_space` now genuinely means the same thing for every piece type."""
    if "rka_arm_names" in coll.keys():
        return _export_intersection(coll, scene, godot_space=godot_space)
    elif "rka_lanes_a" in coll.keys():
        return _export_transition(coll, godot_space=godot_space)
    elif "rka_curve_object" in coll.keys():
        return _export_gn_segment(coll, godot_space=godot_space)
    else:
        return _export_point_segment(coll, scene, godot_space=godot_space)


def collect_pieces(stem, scene, bpy_data, godot_space=True):
    """`[(coll_name, export_dict, zone_id), ...]` for every LOCAL piece collection currently in
    the file. `bpy_data`/`scene` passed explicitly (not imported as a global `bpy`) so this stays
    trivially callable from either a headless `--background --python` script (`tools/
    save_lane_kit.py`) or a live interactive operator (`ops_lane_preview.py`) with no import-time
    surprises. See `export_piece_dict` for `godot_space`."""
    pieces = []
    colls = sorted((c for c in bpy_data.collections
                     if c.library is None and opint._is_piece_collection(c)),
                    key=lambda c: c.name)
    for coll in colls:
        d = export_piece_dict(coll, scene, godot_space=godot_space)
        if d is None:
            print("  skipping %s: could not reconstruct build params from its rka_* properties"
                  % coll.name)
            continue
        # DESIGN SPEED rides on every lane, stamped here rather than inside each of the three
        # exporters -- it is a property of the PIECE (the road class it was built as), so one place
        # applies it uniformly, the same way `zone_id` is a piece-level fact. Absent when the piece
        # never declared one: `check_road_network` check 6 then says it is skipping rather than
        # inventing a speed, because a made-up design speed produces made-up curve verdicts.
        speed = coll.get("rka_design_speed")
        if speed:
            for lane in d.get("lanes", []):
                lane["design_speed"] = float(speed)
        zone_id = coll.get("rka_zone_id", stem)
        pieces.append((coll.name, d, zone_id))
    emit_joint_links(pieces, bpy_data, godot_space=godot_space)
    return pieces


def emit_joint_links(pieces, bpy_data, godot_space=True):
    """Turn each AUTHORED piece-to-piece link into real per-lane connections.

    `godot_space` MUST match what the pieces were exported in, because the pairing is geometric and
    the two frames put the ground plane on different axes (`lane_joints.GODOT_AXES`). It defaulted
    to nothing at all until 2026-08-15, so the real export -- which runs `godot_space=True` --
    measured every joint in the x/elevation plane and produced no links, while the in-Blender
    preview path measured correctly and every test passed.

    THE DIVISION OF LABOUR MATTERS. Which two pieces are connected is authored -- the user said so
    by linking a port to an arm or to another port (`live_edit.RKA_LINKED_TO_KEY`), and nothing
    here second-guesses that. Which LANE continues into which lane is then MEASURED, by
    `lane_joints.pair_lanes`: the pairing is whichever ribbons actually meet edge-to-edge.

    That split is deliberate. Deriving the pairing instead -- same slot id, unless the pieces meet
    end-to-end, in which case the lateral frames mirror and forward pairs with reverse and the slot
    order flips -- is correct reasoning and four chances to get a sign wrong in a case nobody
    tests. Measuring asks the question the connection is actually about. It also means a RAMP needs
    no rule of its own: it pairs with the auxiliary lane when one was opened for the exit and with
    the outermost lane when none was, because those are the edges it meets.

    A lane that meets nothing gets no link. Proximity is never used to fill the gap -- an unmade
    connection stays visibly unmade, which is the whole reason the gate exists."""
    import lane_joints as lj
    axes = lj.GODOT_AXES if godot_space else lj.BLENDER_AXES
    by_name = {name: d for name, d, _z in pieces}
    is_junction = {}
    for name, _d, _z in pieces:
        coll = bpy_data.collections.get(name)
        is_junction[name] = coll is not None and "rka_arm_names" in coll.keys()

    report = []
    for a, b in authored_joints(set(by_name), bpy_data):
        report.append((a, b, _pair_across(by_name[a], a, by_name[b], b, is_junction, lj, axes)))
    return report


def authored_joints(piece_names, bpy_data):
    """Every piece-to-piece connection the USER authored, as sorted `(name_a, name_b)` pairs.

    This is the authored half of the division of labour (see `emit_joint_links`) on its own, so a
    checker can ask the question the geometry cannot answer: which pieces were MEANT to connect.
    A joint that produces no lane pairs is invisible in the lane data -- it looks exactly like two
    pieces that were never linked -- and that is the single most useful thing to report, because it
    means an authoring gesture silently did nothing.

    One pair per joint however many markers describe it: both ends usually carry an
    `rka_linked_to`, and an intersection arm meeting a segment stamps only one."""
    seen = set()
    for name in sorted(piece_names):
        coll = bpy_data.collections.get(name)
        if coll is None:
            continue
        for marker in coll.objects:
            target_name = marker.get("rka_linked_to")
            if not target_name:
                continue
            target = bpy_data.objects.get(target_name)
            if target is None or not target.users_collection:
                continue
            other = next((c.name for c in target.users_collection
                          if c.name in piece_names), None)
            if other is None or other == name:
                continue
            seen.add(tuple(sorted((name, other))))
    return sorted(seen)


def unjoined_joints(lanes, bpy_data):
    """The authored joints that NO lane crosses -- `[(name_a, name_b), ...]`.

    The one failure the lane data cannot show on its own: with no link across the seam there is
    nothing to measure, so a checker that only measures links sees a clean scene with a hole in it.
    Reported via `lane_joints.unjoined`.

    Works on lanes either BEFORE `lane_kit.resolve_links` (symbolic `next_refs`, which is what the
    in-Blender checker has) or AFTER it (resolved `next` ids, which is what the written sidecar
    has), so the authoring-time button and the export gate answer from the same function rather
    than from two implementations that can drift."""
    id_piece = {l.get("id"): l.get("piece_id") for l in lanes}
    crossed = set()
    for l in lanes:
        src = l.get("piece_id")
        if not src:
            continue
        for ref in l.get("next_refs") or []:
            if ref.get("piece"):
                crossed.add(tuple(sorted((src, ref["piece"]))))
        for dst in l.get("next") or []:
            other = id_piece.get(dst)
            if other and other != src:
                crossed.add(tuple(sorted((src, other))))
    pieces = {l.get("piece_id") for l in lanes if l.get("piece_id")}
    return [j for j in authored_joints(pieces, bpy_data) if j not in crossed]


def _link_kind(dst_lane):
    """What the movement being ENTERED means to an AI: a junction movement says so itself.

    An intersection lane carries its own `turn` (`L`/`S`/`R`, decided by `intersection_kit` from
    the two arm angles), so the kind is read off the movement rather than inferred from "one end of
    this joint is a junction" -- which would label a straight-through crossing as a TURN and make
    the runtime's straight-bias weighting meaningless at exactly the junctions that have one. A
    lane LEAVING a junction onto a road is a plain continuation: the turn already happened."""
    turn = (dst_lane.get("turn") or "").upper()
    return "TURN" if turn in ("L", "R") else "THROUGH"


def _pair_across(da, na, db, nb, is_junction, lj, axes):
    """Emit links BOTH ways across one joint. Each direction is measured separately, because a
    joint carries opposing carriageways: A's forward lanes end here and continue into B, while B's
    forward lanes for the other direction end here and continue into A.

    A JUNCTION FANS, a butt joint does not (`exclusive`, see `lane_joints.pair_lanes`). Where a
    segment meets an intersection arm, the approach lane feeds every movement that starts on it --
    left, straight and right all begin on that same ribbon at the stop line -- and every movement
    arriving at a departure lane feeds that one lane. One-to-one pairing would keep whichever
    measured closest and drop the rest, i.e. build a junction cars can only drive straight through.
    Between two ordinary segments a lane continues into exactly one lane, so the tie-break stays.

    Returns how many links it emitted, so a caller can tell "these two pieces are linked and no
    lane crosses the seam" from "these two pieces were never linked" -- identical in the lane data,
    and only the first is a mistake."""
    n = 0
    for (src_d, src_n, dst_d, dst_n) in ((da, na, db, nb), (db, nb, da, na)):
        fan = bool(is_junction.get(src_n) or is_junction.get(dst_n))
        pairs = lj.pair_lanes(src_d.get("lanes", []), dst_d.get("lanes", []),
                              exclusive=not fan, axes=axes)
        if not pairs:
            continue
        by_id = {l.get("id"): l for l in src_d.get("lanes", [])}
        dst_by_id = {l.get("id"): l for l in dst_d.get("lanes", [])}
        for src_id, dst_id, _gap in pairs:
            lane = by_id.get(src_id)
            dst = dst_by_id.get(dst_id)
            if lane is None or dst is None:
                continue
            kind = _link_kind(dst)
            # Addressed by PIECE, not by the group/role pair the split/carriageway rules use: an
            # ordinary joint has no structure name, only two collections that meet.
            lane.setdefault("next_refs", []).append(
                {"piece": dst_n, "slot": dst.get("slot_id"), "lane_id": dst.get("id"),
                 "kind": kind, "weight": 1.0})
            n += 1
    return n
