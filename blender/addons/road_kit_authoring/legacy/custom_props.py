"""Persist/read RKA_OT_build_intersection / RKA_OT_build_straight_segment settings as native
Blender custom properties (Collection ID properties) instead of only the operator's own
redo-panel fields, which are ephemeral (lost on file close/reopen, only replayable via F9 within
the same undo history). After a build, every setting used -- including a resolved `lane_map`, as
a plain nested dict/list, not a string -- is written onto the created Collection, so it's a
permanent record visible/editable via Blender's native Object/Collection Properties > Custom
Properties panel. `lane_map` specifically can ALSO be read back FROM there as an override: if the
collection active at build time already carries an `rka_lane_map` custom property, it wins over
the operator's `lane_map` string field entirely -- hand-edit the nested dict via Blender's own UI
(or the Python console) instead of writing the 'From>To:in-out,in-out' mini-syntax.
"""

LANE_MAP_KEY = "rka_lane_map"
PROFILE_KEY = "rka_profile"

_lp = None


def lp():
    """Lazy `lib/lane_profile` import -- same deferred-import idiom `lane_export.ik()` uses, so
    this module stays importable by anything that hasn't put `blender/lib` on `sys.path` yet."""
    global _lp
    if _lp is None:
        import lane_profile as _mod
        _lp = _mod
    return _lp


def plain(o):
    """Blender IDProperty wrappers (`IDPropertyGroup`, `IDPropertyArray`) -> plain dict/list/scalar.

    Needed because `lane_profile.ProfileSet.from_dict` is pure Python and uses `.get()`, which
    `IDPropertyGroup` does not provide -- it only supports `.keys()`/`[]`. Doing the conversion
    here (rather than teaching the pure module about Blender types) keeps `lane_profile.py`
    bpy-free and self-testable, which is the whole convention `intersection_kit.py` established."""
    if isinstance(o, (str, bytes, int, float, bool)) or o is None:
        return o
    if hasattr(o, "to_dict"):
        return {k: plain(v) for k, v in o.to_dict().items()}
    if hasattr(o, "to_list"):
        return [plain(x) for x in o.to_list()]
    if hasattr(o, "keys"):
        return {k: plain(o[k]) for k in o.keys()}
    try:
        return [plain(x) for x in o]
    except TypeError:
        return o


def read_profile(coll):
    """The piece's cross-section as a `lane_profile.ProfileSet` -- THE accessor every consumer
    (pavement sweep, curb/sidewalk offsets, lane export, branch seeding) reads, so there is
    exactly one description of the cross-section and no consumer re-derives it with its own
    convention. That divergence is the confirmed root cause of all three 2026-08 defects; see
    `lane_profile.py`'s module docstring.

    MIGRATION. When `rka_profile` is absent the set is synthesized from the legacy scalars via
    `lane_profile.profile_from_scalars`, using the piece's `_end` twins as a second station when
    any of them differs -- so every existing piece in `island_v3_roads.blend` reads back as a
    ProfileSet describing exactly the geometry it already has (`lane_profile`'s own self-test
    asserts `extents()` equals `intersection_kit.carriageway_extents` for every scalar case), and
    acquires a stored `rka_profile` the first time it is rebuilt. Precedent:
    `ops_intersection.ensure_arm_angle_migrated`.

    Returns None for a collection that carries no cross-section at all (an intersection piece --
    a filled boundary polygon from N arms is a different shape of problem and keeps its own
    `rka_arm_*` description)."""
    if coll is None:
        return None
    if PROFILE_KEY in coll.keys():
        return lp().ProfileSet.from_dict(plain(coll[PROFILE_KEY]))
    if "rka_lane_width" not in coll.keys():
        return None

    def g(key, default=None):
        return coll[key] if key in coll.keys() else default

    lane_width = float(g("rka_lane_width", 5.0))
    lanes = int(g("rka_lanes", 1))
    lanes_backward = int(g("rka_lanes_backward", lanes))
    median = float(g("rka_median_width", 0.0) or 0.0)
    sw_l = float(g("rka_sidewalk_l_width", 0.0) or 0.0)
    sw_r = float(g("rka_sidewalk_r_width", 0.0) or 0.0)
    start = lp().profile_from_scalars(lanes, lanes_backward, lane_width, median, sw_l, sw_r)

    # `None` means "same as start" throughout the legacy scalar model -- NOT zero. Reading a
    # missing `_end` twin as 0.0 would silently taper every existing piece to nothing.
    def end(key, fallback):
        v = g(key, None)
        return fallback if v is None else float(v)

    lanes_e = int(end("rka_lanes_end", lanes))
    lanes_b_e = int(end("rka_lanes_backward_end", lanes_backward))
    median_e = end("rka_median_width_end", median)
    sw_l_e = end("rka_sidewalk_l_width_end", sw_l)
    sw_r_e = end("rka_sidewalk_r_width_end", sw_r)
    if (lanes_e, lanes_b_e, median_e, sw_l_e, sw_r_e) == (lanes, lanes_backward, median,
                                                          sw_l, sw_r):
        return lp().ProfileSet([start])
    finish = lp().profile_from_scalars(lanes_e, lanes_b_e, lane_width, median_e, sw_l_e, sw_r_e)
    return lp().ProfileSet([start, finish])


def write_profile(coll, profile_set):
    """Store a `ProfileSet` on the piece as `PROFILE_KEY`. Plain nested dict/list, so it shows up
    hand-editable in Blender's Custom Properties panel exactly like `rka_lane_map`."""
    if coll is None or profile_set is None:
        return
    coll[PROFILE_KEY] = profile_set.to_dict()


def lane_map_to_custom(lane_map):
    """{(from,to): [(in,out), ...]} -> {'From>To': [[in,out], ...]} -- plain JSON-safe nested
    dict/list. Blender custom properties store nested dict/list natively via the Python API
    (IDPropertyGroup/IDPropertyArray under the hood), so no string encoding is needed here."""
    if not lane_map:
        return {}
    return {"%s>%s" % k: [list(p) for p in v] for k, v in lane_map.items()}


def lane_map_from_custom(data):
    """Inverse of `lane_map_to_custom`. Also accepts Blender's own IDPropertyGroup/IDPropertyArray
    wrapper types transparently -- they support .keys()/indexing like a plain dict/list."""
    if not data:
        return None
    result = {}
    for key in data.keys():
        frm, _, to = key.partition(">")
        pairs = [(int(p[0]), int(p[1])) for p in data[key]]
        result[(frm, to)] = pairs
    return result


def read_lane_map_override(coll):
    """Read `LANE_MAP_KEY` off a Collection's custom properties, or None if absent/empty --
    the "prefer native Blender data over the operator's string field" input path."""
    if coll is None or LANE_MAP_KEY not in coll.keys():
        return None
    return lane_map_from_custom(coll[LANE_MAP_KEY])


def read_arms(coll):
    """Reconstruct the `[(name, angle_deg, lanes, lanes_out), ...]` list this intersection
    collection was built with, from its `rka_arm_names`/`rka_arm_angles`/`rka_arm_lanes`/
    `rka_arm_lanes_out` custom properties (see `write_build_settings`) -- or None if `coll` wasn't
    built by `RKA_OT_build_intersection` (missing one or more of the first three keys).
    `angle_deg` here is already the FINAL, resolved angle (rotation_deg already applied at build
    time), so callers never need to re-derive it. `lanes_out` is 0 (= symmetric with `lanes`,
    `Arm.lanes_out=None`) unless `RKA_OT_adjust_arm_lanes_out` set an asymmetric-widening override
    on that arm -- `rka_arm_lanes_out` predates -- older collections without it default to all-0
    (fully back-compat)."""
    if coll is None:
        return None
    names, angles, lanes = coll.get("rka_arm_names"), coll.get("rka_arm_angles"), coll.get("rka_arm_lanes")
    if names is None or angles is None or lanes is None:
        return None
    lanes_out = coll.get("rka_arm_lanes_out")
    lanes_out = [int(n) for n in lanes_out] if lanes_out is not None else [0] * len(list(names))
    return list(zip(list(names), [float(a) for a in angles], [int(n) for n in lanes], lanes_out))


def read_arms_full(coll, arm_cls):
    """Reconstruct real `intersection_kit.Arm` objects (not `read_arms`'s plain 4-tuples --
    those drop `oneway`/`tail_length`/`traffic_side`, which a faithful rebuild needs) from a
    built intersection collection's `rka_arm_*`/`rka_traffic_side` custom properties -- the exact
    same fields `ops_intersection.rebuild_intersection_in_place` already reads to rebuild this
    piece in place, just assembled into `Arm(...)` calls instead of applied directly. `arm_cls` is
    `intersection_kit.Arm`, passed in rather than imported here so this module (like the rest of
    `custom_props.py`) stays free of any `intersection_kit`/`bpy` import of its own -- callers
    already lazily import `intersection_kit` themselves (see `ops_intersection.ik()`/
    `ops_segment.ik()`). Returns `None` if `coll` wasn't built by `RKA_OT_build_intersection`
    (mirrors `read_arms`'s own None contract).

    `tail_pos` (2026-08, the actual fix for a REAL bug, not just a preview cosmetic one):
    reconstructed from `rka_arm_tail_pos_x`/`_y` (see `ops_intersection.rebuild_intersection_
    in_place`'s matching write) when both are present, else `None` (a pre-fix saved piece --
    degrades to the OLD plain-ray-point behavior exactly as before, until it's rebuilt once).
    Without this, every caller of `read_arms_full` -- `lane_export.py`'s `_export_intersection`,
    used by BOTH `ops_lane_preview.py`'s interactive preview AND `tools/save_lane_kit.py`'s real
    `.lanekit.json`/Godot `Path3D` export -- reconstructed a `tail_pos_locked` (position-matched)
    arm with `tail_pos=None`, silently discarding the match and falling back to the plain angle-
    ray point for every lane movement/port touching that arm. This is DIFFERENT from `read_arms`'s
    call sites, which never needed `tail_pos` (`ops_intersection.rebuild_intersection_in_place`
    reconstructs it fresh from each arm marker's own LIVE position instead, byte-identical to
    round 2's original `_lane_far_point` fix for the in-memory rebuild path) -- confirmed directly:
    a `tail_pos`-locked arm's own `build_ports()` position (computed with the live `tail_pos`)
    matched its linked segment's own port to within 1cm, while the SAME arm reconstructed via
    `read_arms_full` (pre-fix, `tail_pos=None`) landed ~9m away for its 'in' side specifically --
    the user-reported "preview lane still not aligned... arm_w... very far away", and (unverified
    until this fix, but the SAME code path) the real exported Path3D data too."""
    tuples = read_arms(coll)
    if tuples is None:
        return None
    oneway = coll.get("rka_arm_oneway")
    oneway = [(o or None) for o in oneway] if oneway is not None else [None] * len(tuples)
    tail_lengths = coll.get("rka_arm_tail_lengths")
    tail_lengths = ([float(t) for t in tail_lengths] if tail_lengths is not None
                     else [None] * len(tuples))
    tail_pos_x = coll.get("rka_arm_tail_pos_x")
    tail_pos_y = coll.get("rka_arm_tail_pos_y")
    if tail_pos_x is not None and tail_pos_y is not None:
        tail_pos = list(zip([float(x) for x in tail_pos_x], [float(y) for y in tail_pos_y]))
    else:
        tail_pos = [None] * len(tuples)
    lane_width = float(coll.get("rka_lane_width", 5.0))
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    return [arm_cls(name, angle_deg, lane_width, lanes,
                     oneway=oneway[i], lanes_out=(lanes_out or None),
                     traffic_side=traffic_side, tail_length=tail_lengths[i], tail_pos=tail_pos[i])
            for i, (name, angle_deg, lanes, lanes_out) in enumerate(tuples)]


def read_origin(coll):
    """Read the raw (pre-lane_surface_z-offset) cursor position a piece was built at, as an
    `(x, y, z)` tuple -- or None if `coll` has no `rka_origin` (wasn't built by this addon, or
    predates this property)."""
    if coll is None or "rka_origin" not in coll.keys():
        return None
    o = coll["rka_origin"]
    return (float(o[0]), float(o[1]), float(o[2]))


def write_build_settings(coll, **kwargs):
    """Write every non-None kwarg onto `coll` as a custom property, prefixed 'rka_' -- the
    permanent "how was this built" record. `lane_map` (a {(from,to): [(in,out),...]} dict, if
    given) is converted via `lane_map_to_custom` first so it round-trips through
    `read_lane_map_override` unchanged."""
    for k, v in kwargs.items():
        if v is None:
            continue
        if k == "lane_map":
            v = lane_map_to_custom(v)
        coll["rka_%s" % k] = v
