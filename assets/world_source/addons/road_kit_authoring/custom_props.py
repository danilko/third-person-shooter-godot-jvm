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
