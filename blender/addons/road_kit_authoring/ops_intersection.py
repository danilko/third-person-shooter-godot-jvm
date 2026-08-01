"""Prototype intersection builder: curb corners + lane-movement centerlines + a visual driving
ribbon, generated from nothing but a handful of approach-arm angles.

This is the resolved answer to Kit geometry v2 item 4's open turn-connector question (see
road_blender_godot.md): corners round to a FIXED radius via closed-form 2D fillet math
(`lib/intersection_kit.py`, no bpy, self-tested with `python3 lib/intersection_kit.py`), not a
hand-tagged curve and not a revived `road_graph.py` bezier. The default radius is deliberately
RELAXED well past the tight ~3.5 m real-world minimum-vehicle-turning-radius (see the reference
image this was designed against) -- a game AI driver should get a wide, easy arc, not a tight hug
of the curb.

Every object this operator creates is new (a fresh collection each run) -- it never edits
`lane_kit.blend` or any existing kit piece.

The actual build logic lives in `build_intersection_geometry()`, a plain function with no
`bpy.ops` dispatch of its own -- `RKA_OT_build_intersection.execute()` is a thin wrapper around
it, and so is `RKA_OT_insert_intersection_on_segment` (`ops_segment.py`). Calling this function
directly (instead of `bpy.ops.rka.build_intersection(...)`) from inside another operator's
`execute()` is what keeps a compound action (like "insert") a SINGLE undo step with a working F9
'Adjust Last Operation' panel -- a nested `bpy.ops.rka.X()` call pushes its own separate undo
step, and Blender's redo panel then shows that INNER operator's properties, not the outer one you
actually meant to tweak (arm name, split fraction, curb style, ...) -- this was the concrete cause
of "F9 doesn't work" and "curb style toggle doesn't work" after Extend/Insert.
"""
import math

import bpy

from . import custom_props, live_edit, paths
from .props import TRAFFIC_SIDE_ITEMS

_ik = None


def ik():
    """Lazy-import lib/intersection_kit.py (sys.path already set up by paths.py)."""
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


class RkaBuildError(Exception):
    """Raised by build_intersection_geometry/build_segment_geometry for a hard failure BEFORE any
    geometry is created (bad input, e.g. malformed NWAY angles or an out-of-range lane_map) -- the
    calling operator reports it and returns CANCELLED. Export failures are different: geometry
    already exists by the time those run, so they're collected in the return dict's `warnings`
    list instead and the operator still returns FINISHED."""


def parse_lane_map(text):
    """Parse the 'Lane Map Override' mini-syntax into `lib/intersection_kit.py`'s `lane_map`
    dict shape: 'From>To:in-out,in-out; From2>To2:in-out' -> {(from,to): [(in,out), ...]}.
    Semicolon-separates arm-pair clauses; each clause is 'From>To' then ':' then comma-separated
    'in-out' index pairs. Blank/whitespace-only text -> None (no override, default i->i pairing
    everywhere -- unchanged behavior). Raises ValueError with the offending clause on malformed
    syntax, so a typo surfaces as an operator error instead of silently doing nothing."""
    text = (text or "").strip()
    if not text:
        return None
    result = {}
    for clause in text.split(";"):
        clause = clause.strip()
        if not clause:
            continue
        if ">" not in clause or ":" not in clause:
            raise ValueError("expected 'From>To:in-out,in-out' in %r" % clause)
        arms_part, pairs_part = clause.split(":", 1)
        frm, to = (s.strip() for s in arms_part.split(">", 1))
        pairs = []
        for p in pairs_part.split(","):
            p = p.strip()
            if not p:
                continue
            if "-" not in p:
                raise ValueError("expected 'in-out' (e.g. '0-1') in %r" % p)
            li, lo = p.split("-", 1)
            pairs.append((int(li.strip()), int(lo.strip())))
        if not pairs:
            raise ValueError("no lane pairs given for %r" % clause)
        result[(frm, to)] = pairs
    return result


CURB_STYLE_ITEMS = (
    ('BOX', "Box (plain wall)", "A flat rectangular wall, the original/default style"),
    ('GUTTER', "City Gutter", "Stepped curb-and-gutter profile -- see kit_common.gutter_curb_profile"),
    ('ASSET', "Asset (kit piece)", "Repeat a mesh object from kit/curb_kit.blend along this curb "
     "line at regular intervals instead of a procedural sweep -- see 'Curb Asset Piece'/'Curb "
     "Asset Spacing' below. Link the library first via 'Link Curb Kit Library'"),
    ('NONE', "None (no curb)", "No curb geometry at all for this piece/side -- e.g. a rural "
     "shoulder, a merge zone, or a transition into open pavement with no curb wall"),
)


def _resolve_curb_asset(name):
    """A linked/appended kit/curb_kit.blend Collection name -> its one mesh Object, or None if
    the name is blank/unresolvable (caller must warn and skip -- never silently crash a build or
    a live-edit rebuild)."""
    if not name:
        return None
    coll = bpy.data.collections.get(name)
    if coll is None:
        return None
    return next((o for o in coll.objects if o.type == 'MESH'), None)


def build_curb(name, pts3, coll, style, height, thickness, asset_obj=None, asset_spacing=3.0,
                asset_rot_offset=0.0):
    """Dispatch on `curb_style`: 'NONE' -> no geometry at all (returns None, caller must skip it);
    'ASSET' -> repeat `asset_obj` along `pts3` at `asset_spacing` m intervals
    (`kit_common.curb_asset_row`; returns None if `asset_obj` wasn't resolved -- the caller
    already warned); 'BOX' -> the original flat `swept_wall`; 'GUTTER' -> a curb-and-gutter
    cross-section (`swept_profile` + `gutter_curb_profile`) swept along the same exact points.
    Shared by `ops_segment.build_segment_geometry` (intersections build curbs via
    `kit_common.curb_loop`/`curb_asset_row` directly instead -- see `_populate_intersection_mesh`)."""
    if style == 'NONE':
        return None
    if style == 'ASSET':
        if asset_obj is None:
            return None
        return paths.kc.curb_asset_row(name, pts3, coll, asset_obj, asset_spacing, asset_rot_offset)
    if style == 'GUTTER':
        return paths.kc.swept_profile(
            name, pts3, paths.kc.gutter_curb_profile(thickness, height), coll, matkey="concrete")
    return paths.kc.swept_wall(name, pts3, h=height, coll=coll, matkey="concrete",
                                thickness=thickness, z0=0.0)


def join_meshes(context, objs, name):
    """Join a list of freshly-created, already-linked-into-the-view-layer Objects into ONE mesh
    Object -- the "let the intersection mesh be one mesh" request: separate curb/pad/ribbon pieces
    are convenient to generate (and independently colour/debug during authoring), but a single
    combined mesh is what actually gets handed to Godot/an artist for export. A 0- or 1-object list
    is a no-op (just a rename, so callers can unconditionally use the returned object's name).

    Any non-Mesh object (e.g. `kit_common.junction_pad`/`curb_loop`'s Curve objects, whose actual
    visible geometry comes from a live Nodes modifier) is converted to a real Mesh datablock first
    (`bpy.ops.object.convert`, which bakes the modifier's evaluated output and removes it) --
    `bpy.ops.object.join()` itself can't combine mixed Curve/Mesh types, and joining a Curve
    object's own un-evaluated control points (instead of its GN-modifier mesh output) would silently
    join the wrong geometry."""
    if not objs:
        return None
    if len(objs) == 1:
        obj = objs[0]
        if obj.type != 'MESH':
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.convert(target='MESH')
            obj.select_set(False)
        obj.name = name
        return obj
    for o in context.selected_objects:
        o.select_set(False)
    for o in objs:
        if o.type != 'MESH':
            o.select_set(True)
            context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = context.view_layer.objects.active
    joined.name = name
    joined.select_set(False)
    return joined


def clear_generated_mesh_objects(coll):
    """Remove every curb_*/pad_*/pave_*/lanecl_*/ribbon_*/mesh_* object (+ its now-orphaned
    mesh/curve data) from `coll`, leaving marker Empties (arm_*/segend_*/segbend_*) untouched. The
    "delete the old generated geometry, keep the live-edit drag handles" step shared by both
    in-place rebuild paths (`rebuild_intersection_in_place`, `ops_segment.rebuild_segment_in_place`).
    `pave_*` is the pavement collision proxy (`kit_common.colonly_swept_between`) -- without it in
    this list, a rebuild would leave the old one orphaned and pile up a new one on every drag."""
    prefixes = ("curb_", "pad_", "pave_", "lanecl_", "ribbon_", "mesh_", "mark_")
    for obj in list(coll.objects):
        if not obj.name.startswith(prefixes):
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def active_marker_position(context):
    """If the active object is one of this addon's marker Empties (`rka_arm_name`/`rka_segend`/
    `rka_segbend`/`rka_port` -- the last being a plain GN segment's end-of-road click target, see
    `ops_segment._place_segment_ports`), return `((x, y), z_raw, parent_coll)` so a NEW piece can
    be built starting exactly there instead of at the 3D cursor -- `z_raw` is already converted
    back to the pre-`lane_surface_z` convention every `build_*_geometry` function expects, and
    `parent_coll` is the marker's own piece's parent (so the new piece lands as a SIBLING of it).
    This is the fix for "Build Intersection always uses the cursor, not wherever the
    segment/arm/port I just selected actually is" -- callers fall back to the 3D cursor when this
    returns None (no marker is the active object)."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    keys = obj.keys()
    if ("rka_arm_name" not in keys and "rka_segend" not in keys and "rka_segbend" not in keys
            and "rka_port" not in keys):
        return None
    rka = context.scene.rka
    loc = obj.location
    return ((loc.x, loc.y), loc.z - rka.lane_surface_z, parent_collection_of(obj.users_collection[0]))


def arm_or_port_anchor(context):
    """If the active object is an `arm_*` (intersection) or `port_A`/`port_B` (plain segment)
    marker, return `(pos_xy, z_raw, heading_deg, lanes_forward, lanes_backward, parent_coll)` --
    everything `RKA_OT_build_intersection`/`RKA_OT_build_lane_transition` need to anchor a NEW
    piece exactly where AND facing the way this marker does, with matching lane counts, instead of
    only picking up position the way `active_marker_position` does. None if the active object is
    neither kind of marker (callers fall back to their normal cursor/manual-property behavior).

    `heading_deg` always points OUTWARD, away from the source piece (`Arm.angle_deg`'s own
    convention, and `rka_port_heading_deg`'s) -- a straight piece continuing forward from here
    should face this heading directly; an intersection anchored here needs to place one of ITS OWN
    arms facing BACK at `heading_deg + 180` instead, since an intersection's `arm_*` tips sit away
    from its own center, not at it (see `RKA_OT_build_intersection.execute()`).

    `lanes_forward`/`lanes_backward` mirror the oneway-aware resolution `RKA_OT_extend_from_arm`
    already uses for an arm (an 'IN'-only arm has 0 lanes_forward, asymmetric `lanes_out` wins over
    the symmetric count when set), or the segment's own `rka_lanes`/`rka_lanes_backward` for a
    port (same as `RKA_OT_extend_from_port`) -- so a piece built here can seed itself with the
    source's actual lane counts instead of a generic default."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    coll = obj.users_collection[0]
    rka = context.scene.rka
    loc = obj.location
    pos_xy, z_raw = (loc.x, loc.y), loc.z - rka.lane_surface_z
    parent_coll = parent_collection_of(coll)
    if "rka_arm_name" in obj.keys():
        arms = custom_props.read_arms(coll)
        match = next((a for a in (arms or []) if a[0] == obj["rka_arm_name"]), None)
        if match is None:
            return None
        _, angle_deg, arm_lanes, arm_lanes_out = match
        oneway = obj.get("rka_arm_oneway", "") or None
        forward_lanes = arm_lanes_out if arm_lanes_out > 0 else arm_lanes
        lanes_forward = 0 if oneway == 'IN' else forward_lanes
        lanes_backward = 0 if oneway == 'OUT' else arm_lanes
        return pos_xy, z_raw, angle_deg, lanes_forward, lanes_backward, parent_coll
    if "rka_port" in obj.keys():
        heading_deg = obj.get("rka_port_heading_deg", 0.0)
        lanes_forward = coll.get("rka_lanes", 1)
        lanes_backward = coll.get("rka_lanes_backward", lanes_forward)
        return pos_xy, z_raw, heading_deg, lanes_forward, lanes_backward, parent_coll
    return None


def local_collection(name):
    """`bpy.data.collections[name]`, but skipping any READ-ONLY LINKED collection sharing that
    name -- mirrors `kit_common.get_coll()`'s own `c.library is None` filter, which the rest of
    the pipeline (`kit_common.get_coll`, `tools/link_neighbors.py`'s `_local_coll`) already relies
    on for the same reason: Blender's own duplicate-name auto-suffixing (`Segment_001.001`) only
    applies WITHIN local data, so a linked library's collection CAN carry the exact bare name a
    local one also uses, with no rename. This addon's own deterministic auto-naming
    (`Intersection_<preset>_%03d`, `Segment_%03d`, `Transition_%03d`) makes that collision likely
    the moment another road_kit_authoring-authored file is linked in read-only (neighbor-district
    reference while authoring a cross-district network, or two independently-built files sharing
    numbering) -- an unqualified `bpy.data.collections.get(name)` can then silently resolve onto
    the wrong (linked) collection instead of the local one being edited, and a rebuild attempt on
    it either raises (mutating library data) or silently misfires. Returns None if no LOCAL
    collection has this name (unlike `kit_common.get_coll`, never creates one -- this is a
    resolve-my-own-piece helper, not a get-or-create one)."""
    return next((c for c in bpy.data.collections if c.name == name and c.library is None), None)


def local_object(name):
    """Same as `local_collection` but for `bpy.data.objects` -- see its docstring. Used for
    by-name object lookups (a piece's own spine curve, an arm marker) that must resolve to the
    LOCAL object even when a linked file's same-named object is also present."""
    return next((o for o in bpy.data.objects if o.name == name and o.library is None), None)


def parent_collection_of(coll, root=None):
    """Walk the collection hierarchy from `root` (default: the current scene's root collection)
    to find whichever collection directly contains `coll` as a child -- Blender's Collection API
    has no direct '.parent' pointer. Used so a piece built FROM an existing one (extend-from-arm,
    insert-on-segment) lands as a SIBLING of it, not nested inside it. Falls back to `root` itself
    if `coll` isn't found nested anywhere."""
    root = root or bpy.context.scene.collection

    def search(node):
        for child in node.children:
            if child == coll:
                return node
            found = search(child)
            if found is not None:
                return found
        return None

    return search(root) or root


PRESET_ITEMS = (
    ('4WAY', "4-way", "Four arms, evenly spaced 90 deg apart -- 4 filleted corners"),
    ('3WAY_T', "3-way (T, direct through)", "Two collinear arms (through street -- straight, no "
     "fillet needed there) plus one side arm -- 2 filleted corners"),
    ('3WAY_Y', "3-way (Y, all turns)", "Three arms at generic angles, no through-street -- every "
     "movement is a turn, all 3 corners filleted"),
    ('NWAY', "N-way (custom angles)", "Any number of arms at arbitrary angles -- set via "
     "'Arm Angles' (comma-separated degrees, e.g. '0,60,130,200,280')"),
)


def _arm_lane_list(lanes, lane_arm_overrides, n):
    """`lanes` (a single scalar) applied to every arm, UNLESS one of the `lane_arm_overrides`
    (0 = "use the default") is set, in which case a list is built so each arm gets its own count
    -- e.g. a 2-lane main street crossing a 1-lane side street."""
    overrides = list(lane_arm_overrides) + [0] * max(0, 4 - len(lane_arm_overrides))
    if not any(overrides[:min(n, 4)]):
        return lanes
    return [overrides[i] if i < 4 and overrides[i] > 0 else lanes for i in range(n)]


def _populate_intersection_mesh(context, coll, arms, kerb_radius, tail_length, segments,
                                 lane_width, curb_style, curb_height, curb_thickness, lane_map,
                                 join_visual_mesh, origin_xy, z, curb_asset_obj=None,
                                 curb_asset_spacing=3.0, curb_asset_rot_offset=0.0):
    """Build the pad + curb + lane-centerline objects for one intersection INTO `coll` (already
    created/linked) and return `(boundary, movements, visual_objs)`. Shared by
    `build_intersection_geometry` (fresh build, also creates the arm_* marker Empties afterward)
    and `rebuild_intersection_in_place` (live-edit rebuild, keeps the existing markers) so the two
    paths can never drift apart -- exactly the same geometry math either way.

    Visual pavement is ONE `kit_common.junction_pad` (GN-backed, Fillet Curve + Fill Curve) from
    `intersection_kit.build_junction_boundary` (the FULL closed footprint, arm tail-caps included)
    -- purely a function of arm angles/widths, never of which lane movements happen to exist,
    which is what fixes the old "widen an arm -> curb moves but pavement has a gap" bug (the pad
    used to be the union of thin per-movement ribbons, capped at `min(a.lanes, b.lanes)` between
    arm pairs). Curb is ONE `kit_common.curb_loop(closed=False)` object PER CORNER, from
    `intersection_kit.build_junction_curb_segments` -- deliberately narrower than the pad's
    boundary: it excludes every arm's own tail-cap (a road can't have a curb wall across its own
    lanes where it enters the junction) and every through-pair (no wall needed where a road just
    continues straight). `lanecl_*` lane-centerline data curves (the AI/export layer) are
    untouched -- still one per legal movement from `build_lane_movements`, still what
    `export_json` reads.

    `tail_length` is floored to `intersection_kit.recommended_tail_length(arms, kerb_radius,
    start=tail_length)` before anything else uses it -- never shrinks the requested value (the
    search starts from it), only raises it for wide (3-4 lane) arms where the requested
    tail_length would otherwise leave some turn's own arc stranded well past the pad (see that
    function's docstring for why this needs a numerical search, not a formula). Both the pad/curb
    boundary and the lane movements use this SAME effective value, so they never disagree."""
    k = ik()
    tail_length = k.recommended_tail_length(arms, kerb_radius, start=tail_length)
    try:
        movements = k.build_lane_movements(arms, kerb_radius, segments, tail_length=tail_length,
                                            lane_map=lane_map)
    except ValueError as exc:
        raise RkaBuildError("Lane Map Override: %s" % exc)
    boundary = k.build_junction_boundary(arms, kerb_radius, tail_length=tail_length)
    curb_segments = k.build_junction_curb_segments(arms, kerb_radius, tail_length=tail_length)

    cx, cy = origin_xy

    def to3(pt2):
        return (cx + pt2[0], cy + pt2[1], z)

    def to3r(pt3):
        return (cx + pt3[0], cy + pt3[1], z, pt3[2])

    boundary3 = [to3r(p) for p in boundary]

    # Short, collection-relative names -- Blender's Outliner already nests these under their
    # collection (which itself carries the full junction_id), and nothing downstream parses these
    # specific names (WorldBaker's prefix table doesn't include curb_/pad_/lanecl_/arm_ at all --
    # every Godot-side lookup goes through the exported JSON's own `id`).
    # Read directly off `coll` (not threaded as a parameter, unlike curb_style etc.) -- both
    # build_intersection_geometry (fresh build, property absent -> the same "asphalt"/"concrete"
    # default as before) and rebuild_intersection_in_place (live-edit rebuild, coll already has
    # whatever RKA_OT_set_piece_matkey last set) read the SAME live value with zero signature
    # changes, and a fresh build's default behavior is unchanged. See RKA_OT_set_piece_matkey
    # (2026-07-28, user-reported: material was a hardcoded literal, no way to change it after the
    # initial build at all -- not even via F9, there was no exposed property anywhere).
    pad_matkey = coll.get("rka_pad_matkey", "asphalt")
    curb_matkey = coll.get("rka_curb_matkey", "concrete")

    visual_objs = []   # pad + curb(s) only -- fed to gltf_export_path / join_visual_mesh
    pad = paths.kc.junction_pad("pad_%s" % coll.name, boundary3, coll, matkey=pad_matkey,
                                 segments=segments)
    if pad is not None:
        visual_objs.append(pad)
        # Collision proxy for the pad footprint -- an exact copy of the pad's own EVALUATED
        # (post-GN-modifier) mesh, so it matches the real filleted/curved visual precisely instead
        # of approximating it. See kit_common.colonly_mesh_evaluated.
        paths.kc.colonly_mesh_evaluated(pad, coll)
    # One curb object PER CORNER (build_junction_curb_segments already excludes every arm's own
    # tail-cap and every through-pair -- an arm opening must never have a curb wall across its own
    # lanes) instead of a single loop spanning the whole boundary.
    for idx, seg in enumerate(curb_segments):
        seg3 = [to3r(p) for p in seg]
        name = "curb_%s_%d" % (coll.name, idx)
        if curb_style == 'ASSET':
            curb = build_curb(name, seg3, coll, 'ASSET', curb_height, curb_thickness,
                               asset_obj=curb_asset_obj, asset_spacing=curb_asset_spacing,
                               asset_rot_offset=curb_asset_rot_offset)
        else:
            curb = paths.kc.curb_loop(name, seg3, coll,
                                       curb_style=curb_style, curb_height=curb_height,
                                       curb_thickness=curb_thickness, matkey=curb_matkey,
                                       segments=segments, closed=False)
            if curb is not None:
                # Curb-wall collision -- an exact copy of the curb's own evaluated mesh (see
                # kit_common.colonly_mesh_evaluated), not a separately-swept approximation.
                paths.kc.colonly_mesh_evaluated(curb, coll)
        if curb is not None:
            visual_objs.append(curb)

    for m in movements:
        pts3 = [to3(p) for p in m["points"]]
        lane_tag = ("L%d" % m["lane_in"] if m["lane_in"] == m["lane_out"]
                    else "L%dto%d" % (m["lane_in"], m["lane_out"]))
        tag = "%s%s_%s" % (m["from"], m["to"], lane_tag)
        paths.kc.poly_curve("lanecl_%s" % tag, pts3, coll, loop=False, lane_width=lane_width,
                             oneway=True, end_behavior='CHAIN')

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return boundary, movements, visual_objs, tail_length


ORIGIN_MARKER_KEY = "rka_origin_marker"


def get_or_create_origin_marker(coll, fallback_xyz=None):
    """The LIVE Empty object anchoring an intersection's origin (created in
    `build_intersection_geometry`, tagged `rka_origin_marker`). Every place that used to derive a
    world position from the frozen `rka_origin` custom property (`rebuild_intersection_in_place`,
    `RKA_OT_add_arm`, `RKA_OT_extend_from_arm`) must read THIS object's current `.location`
    instead: `rka_origin` is a plain coordinate that does not move, so selecting an intersection's
    WHOLE collection (this marker included, since it's just another object in it) and Grab/
    Rotate-ing it as a rigid group correctly carries the origin along -- every arm's angle,
    re-derived as a bearing FROM this point, comes out identical to before the move, so the
    intersection reproduces itself at the new location/orientation instead of snapping back
    toward a stale coordinate that got left behind. `fallback_xyz`, if given, self-heals a piece
    built before this marker existed (or loaded from an old file) by creating one there the first
    time it's needed -- from then on it's a normal object and moves with the rest of the piece.
    Returns None if no marker exists and no `fallback_xyz` was given to create one."""
    markers = [o for o in coll.objects if o.get(ORIGIN_MARKER_KEY)]
    if markers:
        if len(markers) > 1:
            # A stray second marker (e.g. a Shift+D linked-duplicate landed in the same
            # collection) would otherwise make every future rebuild pick an ARBITRARY one of the
            # two -- silently "snapping" the piece back to whichever marker iteration happens to
            # return first. Keep the oldest-created (lowest name suffix sorts first for the
            # "origin_<coll.name>"/"origin_<coll.name>.001" naming Blender itself assigns to a
            # duplicate) and warn instead of guessing wrong forever.
            markers.sort(key=lambda o: o.name)
            print("road_kit_authoring: '%s' has %d origin markers (%s) -- using '%s', "
                  "delete the extra(s) by hand" %
                  (coll.name, len(markers), ", ".join(o.name for o in markers), markers[0].name))
        return markers[0]
    if fallback_xyz is None:
        return None
    marker = bpy.data.objects.new("origin_%s" % coll.name, None)
    marker.empty_display_type = 'PLAIN_AXES'
    marker.empty_display_size = 0.5
    marker.location = fallback_xyz
    marker[ORIGIN_MARKER_KEY] = True
    coll.objects.link(marker)
    return marker


@live_edit.rebuilding()
def rebuild_intersection_in_place(context, coll):
    """Live-editing counterpart to `build_intersection_geometry`: re-derive each arm's ANGLE from
    its `arm_*` marker Empty's CURRENT position (bearing from the LIVE origin marker -- see
    `get_or_create_origin_marker`), then rebuild curb/lane objects in place -- no new collection,
    the arm Empties themselves are the drag handles ("bevel-style" adjustment). Called from
    `live_edit.py`'s `depsgraph_update_post` handler whenever an arm Empty's transform changes.

    Each arm's RADIUS (distance from origin) IS now taken from the drag, same as its angle --
    `intersection_kit.Arm.tail_length` is a per-arm override (`eff_tail_length`), so an arm
    dragged/snapped to an arbitrary distance (e.g. Grab+Ctrl-snapped onto an external segment's
    port while the intersection is frozen -- see `RKA_OT_freeze_for_move`/`RKA_OT_select_arm`)
    keeps EXACTLY that distance after rebuild instead of being forced back onto one shared radius.
    An arm that was never deliberately moved off the shared `tail_length` simply keeps reporting
    that same distance, so this is a strict generalization of the old "arms share one radius"
    behavior, not a separate mode. The per-arm value is persisted on the arm Empty itself
    (`rka_arm_tail_length`, alongside `rka_arm_angle`) so it survives across rebuilds/reloads. A
    no-op (returns immediately) if there's no stored origin, fewer than 3 arms survive the current
    drag position (e.g. one was dropped exactly on the origin), or the lane-map/angle combination
    is momentarily degenerate mid-drag -- the next tick, once the drag moves past it, recovers on
    its own."""
    k = ik()
    prev_origin = custom_props.read_origin(coll)
    marker = get_or_create_origin_marker(coll, prev_origin)
    if marker is None:
        return
    ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
    rka = context.scene.rka
    z = oz + rka.lane_surface_z
    tail_length = coll.get("rka_tail_length", 12.0)
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    lane_width = coll.get("rka_lane_width", 5.0)
    segments = coll.get("rka_segments", 8)
    curb_style = coll.get("rka_curb_style", 'BOX')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    curb_asset_obj = _resolve_curb_asset(coll.get("rka_curb_asset_collection", ""))
    curb_asset_spacing = coll.get("rka_curb_asset_spacing", 2.0)
    lane_map = custom_props.read_lane_map_override(coll)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)
    traffic_side = coll.get("rka_traffic_side", "LEFT")

    arm_empties = [o for o in coll.objects if "rka_arm_name" in o.keys()]

    # If the origin marker itself moved since the LAST rebuild (its previously-persisted
    # position, `prev_origin`, differs from its current `marker.location`), carry every arm that
    # DIDN'T also move along with it, by that same delta, before re-deriving bearings below.
    # Without this, dragging JUST the origin marker to relocate the whole intersection (the
    # natural, single-handle way to use it -- the "regenerate along that arm/empty" ask this
    # marker exists for) instead re-derives each arm's angle against a now-mismatched center,
    # collapsing every arm onto a tiny bogus angular range while forcibly re-snapping each back
    # onto the `tail_length` radius -- the intersection "blows up" into a degenerate cluster
    # instead of relocating intact. An arm that already moved on its own (the correct "select the
    # WHOLE collection including the origin, Grab/Rotate together" workflow, or a normal one-arm
    # reshape drag) is left alone -- it no longer sits at its last-known position, so its NEW
    # position is trusted as intentional, exactly as before this carry existed.
    if prev_origin is not None:
        odx = ox - prev_origin[0]
        ody = oy - prev_origin[1]
        odz = oz - prev_origin[2]
        if abs(odx) > 1e-4 or abs(ody) > 1e-4 or abs(odz) > 1e-4:
            for o in arm_empties:
                prev_angle = o.get("rka_arm_angle")
                if prev_angle is None:
                    continue
                # This arm's OWN previous tail length (falls back to the shared scalar for an
                # older piece built before rka_arm_tail_length existed) -- using the shared value
                # here for an arm that already has its own override would wrongly predict its
                # last-known position, making a piece-wide move falsely look like an independent
                # arm drag.
                prev_tail = o.get("rka_arm_tail_length", tail_length)
                d = k.arm_dir(prev_angle)
                want_prev = (prev_origin[0] + d[0] * prev_tail,
                             prev_origin[1] + d[1] * prev_tail,
                             prev_origin[2] + rka.lane_surface_z)
                cur = (o.location.x, o.location.y, o.location.z)
                if math.dist(want_prev, cur) < 1e-3:
                    o.location.x += odx
                    o.location.y += ody
                    o.location.z += odz

    arms = []
    for o in arm_empties:
        dx, dy = o.location.x - ox, o.location.y - oy
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            continue   # dropped exactly on the origin mid-drag -- degenerate, skip this arm
        angle_deg = math.degrees(math.atan2(dy, dx)) % 360.0
        oneway = o.get("rka_arm_oneway", "") or None
        lanes_out_raw = int(o.get("rka_arm_lanes_out", 0))
        arms.append(k.Arm(o["rka_arm_name"], angle_deg, lane_width, int(o.get("rka_arm_lanes", 1)),
                           oneway=oneway, lanes_out=lanes_out_raw or None,
                           traffic_side=traffic_side, tail_length=dist))
    if len(arms) < 3:
        return

    clear_generated_mesh_objects(coll)
    try:
        _, _, _, tail_length = _populate_intersection_mesh(
            context, coll, arms, kerb_radius, tail_length, segments, lane_width, curb_style,
            curb_height, curb_thickness, lane_map, join_visual_mesh, (ox, oy), z,
            curb_asset_obj=curb_asset_obj, curb_asset_spacing=curb_asset_spacing)
    except RkaBuildError:
        return   # e.g. two arms briefly coincide mid-drag -- leave geometry as the last-good state
    # `tail_length` above is now the EFFECTIVE value (floored to recommended_tail_length inside
    # _populate_intersection_mesh) -- re-snapping arm markers and persisting rka_tail_length below
    # must use THIS value, not the original request, or the markers/stored setting would silently
    # drift out of sync with where the pad/curb/movements actually ended up.
    coll["rka_tail_length"] = tail_length

    # Re-snap each arm empty onto ITS OWN effective tail length (its live drag distance, or the
    # shared scalar if it was never individually overridden -- see the docstring) and keep its
    # arrow aligned with the new angle. Guarded by an epsilon so a clean drag (already exactly at
    # its own resolved distance) doesn't rewrite the transform and retrigger this same handler
    # pass -- in practice this is a near-no-op for the radius (each arm's `Arm.tail_length` was
    # itself just measured FROM this same marker's current position above), it mainly exists to
    # correct float drift and to keep every OTHER arm's stored `rka_arm_tail_length` in sync after
    # a `_populate_intersection_mesh` call that grew the shared scalar for wide-arm clearance.
    by_name = {a.name: a for a in arms}
    for o in arm_empties:
        a = by_name.get(o["rka_arm_name"])
        if a is None:
            continue
        eff_tail = a.tail_length if a.tail_length is not None else tail_length
        d = k.arm_dir(a.angle_deg)
        want = (ox + d[0] * eff_tail, oy + d[1] * eff_tail, z)
        cur = (o.location.x, o.location.y, o.location.z)
        if math.dist(want, cur) > 1e-4:
            o.location = want
        o["rka_arm_angle"] = a.angle_deg
        o["rka_arm_tail_length"] = eff_tail

    custom_props.write_build_settings(
        coll, arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms], arm_oneway=[a.oneway or "" for a in arms],
        arm_lanes_out=[a.lanes_out or 0 for a in arms],
        arm_tail_lengths=[(a.tail_length if a.tail_length is not None else tail_length)
                           for a in arms],
        # Keep the fallback-seed prop in sync with the LIVE marker on every rebuild -- otherwise
        # it freezes at the build-time position forever, and if the marker object is ever lost
        # (accidental delete, a linked-duplicate collision -- see get_or_create_origin_marker's
        # dedupe note) self-heal would resurrect it at the stale PRE-MOVE location instead of
        # where the piece actually is now.
        origin=[ox, oy, oz])


def build_intersection_geometry(context, parent_coll, cursor, preset, rotation_deg, side_angle,
                                 arm_angles_str, lane_width, lanes, lane_arm_overrides, kerb_radius,
                                 tail_length, segments, curb_style, curb_height, curb_thickness,
                                 lane_map, join_visual_mesh, export_path, gltf_export_path,
                                 traffic_side='LEFT', curb_asset_collection="",
                                 curb_asset_spacing=2.0):
    """Pure build logic behind `RKA_OT_build_intersection` -- no `bpy.ops` dispatch, so a caller
    that needs to build an intersection as ONE STEP of a larger flat operator
    (`RKA_OT_insert_intersection_on_segment`) can call this directly instead of going through
    `bpy.ops.rka.build_intersection(...)` (see module docstring for why that matters for F9).

    `cursor` is `(x, y, z)` -- `z` is the RAW cursor-equivalent height, before
    `context.scene.rka.lane_surface_z` is added (this function is the one place that offset is
    applied, same as before). `lane_map` is an already-resolved `{(from,to): [(in,out),...]}`
    dict or None (callers resolve a collection-custom-property override / mini-syntax string
    BEFORE calling this, since that resolution is itself context/UI-specific and doesn't belong in
    the pure geometry-building step).

    Returns a dict: `{'coll', 'arms', 'boundary', 'movements', 'visual_objs', 'export_note',
    'warnings'}` (`boundary` is the `[(x, y, radius), ...]` pad/curb polygon from
    `intersection_kit.build_junction_boundary`; `warnings` is a list of str -- non-fatal export
    failures the caller should
    surface via `self.report({'WARNING'}, ...)` but that don't prevent FINISHED). Raises
    `RkaBuildError` for anything that must abort before any geometry is created."""
    rka = context.scene.rka
    k = ik()

    if preset == '4WAY':
        arms = k.preset_4way(lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, 4),
                              traffic_side=traffic_side)
    elif preset == '3WAY_T':
        arms = k.preset_3way_t(side_angle=side_angle, lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3),
                                traffic_side=traffic_side)
    elif preset == '3WAY_Y':
        arms = k.preset_3way_y(angles=(0.0, side_angle, 2.0 * side_angle), lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3),
                                traffic_side=traffic_side)
    else:   # NWAY
        try:
            angles = [float(a.strip()) for a in arm_angles_str.split(",") if a.strip()]
        except ValueError:
            raise RkaBuildError("Arm Angles must be comma-separated numbers, e.g. '0,60,130,200,280'")
        if len(angles) < 3:
            raise RkaBuildError("NWAY needs at least 3 arm angles")
        arms = k.preset_nway(angles, lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, len(angles)),
                              traffic_side=traffic_side)

    if rotation_deg != 0.0:
        for a in arms:
            a.angle_deg = (a.angle_deg + rotation_deg) % 360.0

    cx, cy, cz_raw = cursor
    z = cz_raw + rka.lane_surface_z

    n = 1
    base_name = "Intersection_%s" % preset
    # local_collection (not a bare name-in-bpy.data.collections test) so a linked neighbor's
    # same-numbered piece never perturbs local auto-numbering -- see its docstring.
    while local_collection(base_name + ("_%03d" % n)) is not None:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)
    get_or_create_origin_marker(coll, (cx, cy, cz_raw))

    curb_asset_obj = _resolve_curb_asset(curb_asset_collection)
    boundary, movements, visual_objs, tail_length = _populate_intersection_mesh(
        context, coll, arms, kerb_radius, tail_length, segments, lane_width, curb_style,
        curb_height, curb_thickness, lane_map, join_visual_mesh, (cx, cy), z,
        curb_asset_obj=curb_asset_obj, curb_asset_spacing=curb_asset_spacing)
    # `tail_length` above is now the EFFECTIVE value (floored to recommended_tail_length inside
    # _populate_intersection_mesh) -- every use below (arm marker placement, the persisted
    # rka_tail_length, JSON export) must use THIS value, not the original request, or the markers
    # would be placed at the OLD (too-small) radius while the pad/curb/movements already reflect
    # the new one.

    # Arm marker Empties -- one per arm, at the tail's far end (the same port RKA_OT_extend_from_arm
    # extends from). This is the concrete "place arm at end of each intersection" handle: visible
    # and selectable in the viewport, carries the arm's angle/lane count as inspectable custom
    # properties, doubles as a click target for Extend From Arm (no typing the arm name), and is
    # also the LIVE-EDIT drag handle -- moving one re-derives its angle and rebuilds this
    # intersection in place (see `rebuild_intersection_in_place`, wired via `live_edit.py`'s
    # depsgraph handler).
    for a in arms:
        d = k.arm_dir(a.angle_deg)
        pos = (cx + d[0] * tail_length, cy + d[1] * tail_length, z)
        arm_obj = bpy.data.objects.new("arm_%s" % a.name, None)
        arm_obj.empty_display_type = 'SINGLE_ARROW'
        arm_obj.empty_display_size = min(2.0, lane_width * 0.4)
        arm_obj.location = pos
        arm_obj.rotation_euler = (0.0, 0.0, math.radians(a.angle_deg))
        arm_obj["rka_arm_name"] = a.name
        arm_obj["rka_arm_angle"] = a.angle_deg
        arm_obj["rka_arm_lanes"] = a.lanes
        arm_obj["rka_arm_oneway"] = a.oneway or ""
        arm_obj["rka_arm_lanes_out"] = a.lanes_out or 0
        arm_obj["rka_arm_tail_length"] = tail_length
        coll.objects.link(arm_obj)

    # Permanent record of exactly how this was built -- native custom properties on the
    # collection, editable via Blender's Object/Collection Properties panel even without the
    # addon's redo panel (which is lost the moment you close the file). See custom_props.py.
    custom_props.write_build_settings(
        coll, preset=preset, kerb_radius=kerb_radius, lane_width=lane_width,
        tail_length=tail_length, segments=segments, curb_style=curb_style,
        curb_height=curb_height, curb_thickness=curb_thickness,
        curb_asset_collection=curb_asset_collection or None, curb_asset_spacing=curb_asset_spacing,
        arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms], arm_lanes_out=[a.lanes_out or 0 for a in arms],
        arm_oneway=[a.oneway or "" for a in arms],
        arm_tail_lengths=[tail_length for a in arms],
        lane_map=lane_map, traffic_side=traffic_side,
        # Raw (pre-lane_surface_z-offset) cursor position -- lets RKA_OT_extend_from_arm
        # reconstruct exact world-space port positions/tangents from this collection's own stored
        # arm data, without guessing where it was built.
        origin=[cx, cy, cz_raw])

    warnings = []
    export_note = ""
    if export_path:
        try:
            k.export_json(bpy.path.abspath(export_path), arms, kerb_radius, junction_id=coll.name,
                           segments=segments, tail_length=tail_length, z=z, lane_map=lane_map,
                           center=(cx, cy))
            export_note += ", json -> '%s'" % export_path
        except OSError as exc:
            warnings.append("Built geometry OK, but json export failed: %s" % exc)
    if gltf_export_path:
        try:
            paths.kc.export_gltf(visual_objs, bpy.path.abspath(gltf_export_path))
            export_note += ", glb -> '%s'" % gltf_export_path
        except Exception as exc:   # noqa: BLE001 -- bpy.ops export can raise a variety of types
            warnings.append("Built geometry OK, but glTF export failed: %s" % exc)

    return {"coll": coll, "arms": arms, "boundary": boundary, "movements": movements,
            "visual_objs": visual_objs, "export_note": export_note, "warnings": warnings,
            "tail_length": tail_length}


class RKA_OT_build_intersection(bpy.types.Operator):
    """Build one intersection (a GN-filled pavement pad + one continuous GN-swept curb loop, both
    from the arm-angle-driven boundary polygon, plus a lanecl_* centerline for every legal
    single-lane movement and an 'arm_*' marker Empty at each arm's tail) at the 3D cursor. Purely
    additive: creates a new collection, never touches lane_kit.blend or
    any existing piece. Re-run with different settings and compare -- each run gets its own
    collection."""
    bl_idname = "rka.build_intersection"
    bl_label = "Build Intersection"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(name="Preset", items=PRESET_ITEMS, default='4WAY')
    rotation_deg: bpy.props.FloatProperty(
        name="Rotation", description="Degrees added to EVERY arm's angle after the preset is "
        "built -- rotates the whole intersection in place, e.g. to align a 3-way T's through "
        "street with an existing road's direction (RKA_OT_insert_intersection_on_segment sets "
        "this automatically)", default=0.0)
    side_angle: bpy.props.FloatProperty(
        name="Side/3rd Arm Angle", description="Degrees from the first arm -- the side street "
        "for 3-way T, or the spacing between all 3 arms for 3-way Y",
        default=90.0, min=1.0, max=179.0)
    arm_angles: bpy.props.StringProperty(
        name="Arm Angles", description="NWAY preset only: comma-separated approach angles in "
        "degrees, at least 3, e.g. '0,60,130,200,280'", default="0,90,180,270")
    lane_width: bpy.props.FloatProperty(
        name="Lane Width", default=5.0, min=0.5, unit='LENGTH')
    lanes: bpy.props.IntProperty(
        name="Lanes Per Direction", description="Default lane count applied to every arm, "
        "overridden per-arm by 'Lanes: Arm N' below (0 = use this default)",
        default=1, min=1, max=3)
    lanes_arm1: bpy.props.IntProperty(name="Lanes: Arm 1", default=0, min=0, max=3)
    lanes_arm2: bpy.props.IntProperty(name="Lanes: Arm 2", default=0, min=0, max=3)
    lanes_arm3: bpy.props.IntProperty(name="Lanes: Arm 3", default=0, min=0, max=3)
    lanes_arm4: bpy.props.IntProperty(name="Lanes: Arm 4", default=0, min=0, max=3)
    kerb_radius: bpy.props.FloatProperty(
        name="Kerb Radius",
        description="Curb corner fillet radius, in meters. Real-world urban minimum is ~3.5 m "
                     "(tight, delivery-truck-feasible -- see the reference diagram this tool was "
                     "designed against); the default here is deliberately more RELAXED so AI "
                     "drivers get a wide, comfortable arc instead of hugging the corner",
        default=9.0, min=1.0, unit='LENGTH')
    tail_length: bpy.props.FloatProperty(
        name="Approach Tail Length",
        description="How far each generated centerline/curb extends out from the corner along "
                     "its arm, in meters -- long enough to reach into an approach lane tile",
        default=12.0, min=1.0, unit='LENGTH')
    segments: bpy.props.IntProperty(
        name="Fillet Segments", description="Polyline segments per rounded corner/turn arc",
        default=8, min=2, max=32)
    curb_style: bpy.props.EnumProperty(
        name="Curb Style", items=CURB_STYLE_ITEMS, default='BOX',
        description="BOX = plain flat wall (original). GUTTER = a stepped curb-and-gutter "
                     "profile matching the real kit_side_straight_city_gutter_curb_w0p6m_l5m "
                     "piece's silhouette (kit/lane_kit.blend), width/height only")
    traffic_side: bpy.props.EnumProperty(
        name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT',
        description="Which physical lateral half of every arm is arriving vs. departing. Must "
                     "match every segment/transition this intersection connects to")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="BOX style: wall thickness. GUTTER style: total "
        "curb+gutter width (the real piece this mirrors is 0.6m)",
        default=0.25, min=0.01, unit='LENGTH')
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Name of a linked kit/curb_kit.blend collection's "
        "mesh object to repeat around every curb corner, when Curb Style is 'Asset'. Use 'Link "
        "Curb Kit Library' first", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", description="Distance between repeated instances -- should "
        "equal the chosen piece's own local X length (see its 'rka_curb_asset_length' custom "
        "property) for seamless tiling", default=2.0, min=0.1, unit='LENGTH')
    lane_map: bpy.props.StringProperty(
        name="Lane Map Override", description="Optional: hand-author exactly which incoming "
        "lane feeds which outgoing lane for specific arm pairs, instead of the default lane-i-"
        "feeds-lane-i pairing. Syntax: 'From>To:in-out,in-out; From2>To2:in-out', e.g. "
        "'N>E:0-1,1-0' to swap. Blank = default pairing everywhere", default="")
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine every curb wall + lane ribbon into a single mesh object after "
                     "building (instead of one object per curb/ribbon)")
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", description="Optional: write the graph-shaped lane/port "
        "sidecar (lib/intersection_kit.py's export_json) here after building. Blank = skip -- "
        "geometry-only, no file written", default="", subtype='FILE_PATH')
    gltf_export_path: bpy.props.StringProperty(
        name="Export .glb", description="Optional: export the built visual geometry (curb walls "
        "+ driving-surface ribbons -- NOT the lanecl_* data curves, which carry no separate "
        "meaning once exported since the .lanekit.json sidecar is the data source of truth) to a "
        ".glb here, ready for Godot to import. Blank = skip", default="", subtype='FILE_PATH')

    def invoke(self, context, event):
        self.traffic_side = context.scene.rka.default_traffic_side
        # Anchored build: an arm_*/port_* marker is active -- prefill Rotation and Arm 1's lane
        # count so the redo panel already shows a correctly-oriented, lane-matched intersection
        # (see `execute()`'s origin-offset math for the position half of this). `heading_deg + 180`
        # lands the FIRST preset arm (raw angle 0 deg in every built-in preset -- 4WAY/3WAY_T/
        # 3WAY_Y/NWAY's default "0,90,180,270" all start there) facing back at the source, so "Arm
        # 1" is always the one that ends up connected. A hand-typed NWAY 'Arm Angles' whose first
        # value isn't 0 breaks that assumption -- re-dial Rotation/Preset on the F9 panel if so.
        anchor = arm_or_port_anchor(context)
        if anchor is not None:
            _, _, heading_deg, lanes_forward, _, _ = anchor
            self.rotation_deg = (heading_deg + 180.0) % 360.0
            if lanes_forward > 0:
                self.lanes_arm1 = max(1, min(3, lanes_forward))
        return self.execute(context)

    def execute(self, context):
        active_coll = context.view_layer.active_layer_collection.collection

        # A custom property on the ACTIVE collection wins over the string field entirely -- lets
        # you hand-edit a native nested dict via Blender's own Object/Collection Properties panel
        # instead of the 'From>To:in-out,in-out' mini-syntax (see custom_props.py).
        lane_map = custom_props.read_lane_map_override(active_coll)
        lane_map_source = "custom property" if lane_map is not None else None
        if lane_map is None:
            try:
                lane_map = parse_lane_map(self.lane_map)
            except ValueError as exc:
                self.report({'ERROR'}, "Lane Map Override: %s" % exc)
                return {'CANCELLED'}
            if lane_map is not None:
                lane_map_source = "string field"

        # Anchored build (arm_*/port_* active): place the intersection's CENTER `tail_length`
        # further out along the source's own outward heading, so the back-facing arm's own tip
        # (see `build_intersection_geometry`'s arm marker placement, the identical `origin + dir *
        # tail_length` formula) lands EXACTLY on the source arm/port tip -- zero gap, no connecting
        # stub segment needed. Otherwise, fall back to `active_marker_position` (position only, no
        # offset -- covers segend_*/segbend_* markers, unchanged) or the 3D cursor.
        anchor = arm_or_port_anchor(context)
        if anchor is not None:
            (ax, ay), cz_raw, heading_deg, _, _, parent_coll = anchor
            rad = math.radians(heading_deg)
            cx = ax + self.tail_length * math.cos(rad)
            cy = ay + self.tail_length * math.sin(rad)
        else:
            marker = active_marker_position(context)
            if marker is not None:
                (cx, cy), cz_raw, parent_coll = marker
            else:
                cursor = context.scene.cursor.location
                cx, cy, cz_raw, parent_coll = cursor.x, cursor.y, cursor.z, active_coll

        try:
            result = build_intersection_geometry(
                context, parent_coll, (cx, cy, cz_raw), self.preset,
                self.rotation_deg, self.side_angle, self.arm_angles, self.lane_width, self.lanes,
                [self.lanes_arm1, self.lanes_arm2, self.lanes_arm3, self.lanes_arm4],
                self.kerb_radius, self.tail_length, self.segments, self.curb_style,
                self.curb_height, self.curb_thickness, lane_map, self.join_visual_mesh,
                self.export_path, self.gltf_export_path, self.traffic_side,
                curb_asset_collection=self.curb_asset_collection,
                curb_asset_spacing=self.curb_asset_spacing)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for w in result["warnings"]:
            self.report({'WARNING'}, w)

        note = result["export_note"]
        if lane_map_source:
            note += " (lane_map from %s)" % lane_map_source

        for o in context.selected_objects:
            o.select_set(False)
        corner_count = len([p for p in result["boundary"] if p[2] > 0])
        if result["tail_length"] > self.tail_length + 1e-3:
            note += " (tail_length auto-grown %.1fm -> %.1fm for wide arms)" % (
                self.tail_length, result["tail_length"])
        self.report(
            {'INFO'},
            "Built '%s': %d arm(s), %d curb corner(s), %d lane movement(s) (radius=%.1fm)%s"
            % (result["coll"].name, len(result["arms"]), corner_count,
               len(result["movements"]), self.kerb_radius, note))
        return {'FINISHED'}


def _is_piece_collection(coll):
    """True if `coll` carries one of this addon's piece-identifying custom properties --
    `rka_arm_names` (intersection), `rka_curve_object` (a GN segment OR a lane transition, both
    spine-backed), or `rka_p0` (the legacy ribbon-based segment, no spine)."""
    return coll is not None and ("rka_arm_names" in coll.keys() or "rka_p0" in coll.keys()
                                  or "rka_curve_object" in coll.keys())


def _live_edit_target_collection(context):
    """The collection a manual 'Rebuild From Handles'/'Freeze For Move'/'Unfreeze & Rebuild'
    should act on. Resolution order:

    1. ANY object the active object's own collection membership already identifies as a piece --
       not just a marker Empty (arm/segend/segbend/port/origin): a `curb_*`/`pad_*`/`lanecl_*`/
       `mark_*`/`ribbon_*`/`mesh_*`/`spine_*` object is linked into the exact same collection as
       every marker of that same piece, so this alone covers clicking (or box-selecting, making
       active) ANY part of a piece -- previously only the small marker Empties resolved, so
       selecting/making-active one of the far more numerous and visually larger generated mesh
       objects (very plausible during a "select everything, Grab" pass) made Freeze For Move's
       poll() silently fail, and a user unaware of that would proceed to move it unfrozen -- the
       exact crash Freeze exists to prevent, for segments/transitions in particular where there's
       no obvious single handle as prominent as an intersection's `arm_*` arrows.
    2. Back-compat fallback for an object that (unusually) isn't linked into its own piece's
       collection directly: the old marker-tag check, or an `rka_curve_object`-name search across
       every collection for a Curve object.
    3. The active LAYER collection itself, if it IS a piece (Outliner collection click, no object
       necessarily active/selected).

    None if nothing resolves."""
    obj = context.active_object
    if obj is not None and obj.users_collection:
        for coll in obj.users_collection:
            if _is_piece_collection(coll):
                return coll
        keys = obj.keys()
        if ("rka_arm_name" in keys or "rka_segend" in keys or "rka_segbend" in keys
                or "rka_port" in keys or ORIGIN_MARKER_KEY in keys):
            return obj.users_collection[0]
        if obj.type == 'CURVE':
            for coll in bpy.data.collections:
                if coll.library is not None:
                    continue   # a linked neighbor's spine could share this curve's exact name
                if coll.get("rka_curve_object") == obj.name:
                    return coll
    coll = context.view_layer.active_layer_collection.collection
    if _is_piece_collection(coll):
        return coll
    return None


def _rebuild_piece_in_place(context, coll):
    """Dispatch to the right rebuild function for whatever kind of piece `coll` is -- shared by
    `RKA_OT_rebuild_from_handles` and `RKA_OT_unfreeze_and_rebuild` so the two can never drift
    apart on which check runs first (lane-transition's own discriminator, `rka_lanes_a`, MUST be
    checked before the plain-curve-segment one, since a transition also carries
    `rka_curve_object` and would otherwise silently un-taper)."""
    from . import ops_segment
    if "rka_arm_names" in coll.keys():
        rebuild_intersection_in_place(context, coll)
    elif "rka_lanes_a" in coll.keys():
        ops_segment.rebuild_lane_transition_in_place(context, coll)
    elif "rka_curve_object" in coll.keys():
        ops_segment.rebuild_segment_gn_in_place(context, coll)
    else:
        ops_segment.rebuild_segment_in_place(context, coll)


class RKA_OT_rebuild_from_handles(bpy.types.Operator):
    """Manual fallback for live-editing: re-derive geometry from the CURRENT positions of an
    intersection's arm_* Empties (or a segment's segend_A/segend_B/segbend Empties) and rebuild in
    place, exactly what the automatic depsgraph handler (`live_edit.py`) does on every drag.
    Use this if 'Live Edit From Handles' is off, or if a drag's automatic update didn't fire for
    any reason -- selecting the piece (or one of its handles) and pressing this always works."""
    bl_idname = "rka.rebuild_from_handles"
    bl_label = "Rebuild From Handles"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Select an intersection/segment (or one of its handle "
                                    "Empties) first")
            return {'CANCELLED'}
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "Rebuilt '%s' from its current handle positions" % coll.name)
        return {'FINISHED'}


class RKA_OT_set_lane_map(bpy.types.Operator):
    """Change the 'Lane Map Override' on an ALREADY-BUILT intersection and rebuild in place --
    the persistent counterpart to `RKA_OT_build_intersection`'s own `lane_map` field, which only
    ever appears on Blender's own F9 'Adjust Last Operation' panel and (like every F9 field)
    silently stops applying the moment any other action runs. Previously the only way to change
    it afterward was hand-editing the `rka_lane_map` Custom Property's raw nested dict directly via
    Blender's Object/Collection Properties panel, then separately triggering a rebuild yourself --
    workable but unfriendly, and easy to typo since there's no validation until the next
    (unrelated) rebuild silently reads it. This pops up a text-entry dialog with the SAME
    'From>To:in-out,in-out; From2>To2:in-out' mini-syntax the build operator uses
    (`parse_lane_map`), pre-filled with the intersection's current override if it has one, and
    validates immediately on OK -- a malformed clause reports an error and changes nothing, rather
    than corrupting the stored override.

    Blank text clears the override entirely (reverts to the default i->i lane pairing everywhere),
    the same as never having set one."""
    bl_idname = "rka.set_lane_map"
    bl_label = "Set Lane Map Override"
    bl_options = {'REGISTER', 'UNDO'}

    lane_map_text: bpy.props.StringProperty(
        name="Lane Map Override", description="'From>To:in-out,in-out; From2>To2:in-out' -- "
        "blank clears the override (default i->i pairing everywhere)", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def invoke(self, context, event):
        coll = _live_edit_target_collection(context)
        if coll is not None and custom_props.LANE_MAP_KEY in coll.keys():
            current = custom_props.read_lane_map_override(coll)
            self.lane_map_text = "; ".join(
                "%s>%s:%s" % (frm, to, ",".join("%d-%d" % p for p in pairs))
                for (frm, to), pairs in current.items())
        else:
            self.lane_map_text = ""
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_arm_names" not in coll.keys():
            self.report({'ERROR'}, "No active intersection piece")
            return {'CANCELLED'}
        try:
            lane_map = parse_lane_map(self.lane_map_text)
        except ValueError as exc:
            self.report({'ERROR'}, "Lane Map Override: %s" % exc)
            return {'CANCELLED'}
        if lane_map is None:
            if custom_props.LANE_MAP_KEY in coll.keys():
                del coll[custom_props.LANE_MAP_KEY]
        else:
            coll[custom_props.LANE_MAP_KEY] = custom_props.lane_map_to_custom(lane_map)
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' lane map override -> %s"
                     % (coll.name, "cleared" if lane_map is None else "%d clause(s)" % len(lane_map)))
        return {'FINISHED'}


MATKEY_ITEMS = tuple((k, k, "") for k in sorted(paths.kc.MATS.keys()))


def _set_piece_matkey(context, target, matkey):
    """Shared by RKA_OT_set_pavement_matkey/RKA_OT_set_curb_matkey -- see either's docstring for
    the full rationale (2026-07-28, user-reported: material was a hardcoded Python literal at
    every build call site, never exposed or persisted anywhere, so there was no way to change it
    after the initial build at all). Returns (coll, error_message_or_None)."""
    coll = _live_edit_target_collection(context)
    if coll is None:
        return None, "No active piece"
    key = "rka_curb_matkey" if target == 'CURB' else (
        "rka_pad_matkey" if "rka_arm_names" in coll.keys() else "rka_pave_matkey")
    coll[key] = matkey
    _rebuild_piece_in_place(context, coll)
    if target == 'PAVEMENT':
        # An intersection's pad is fully regenerated by _rebuild_piece_in_place (reads
        # rka_pad_matkey fresh every time) -- this direct update is only needed for a GN
        # segment/transition's spine, which a rebuild deliberately never deletes/recreates (its
        # own control points ARE the live-edited shape), so it wouldn't otherwise pick up the new
        # rka_pave_matkey. local_object() simply won't resolve "spine_<name>" on an intersection
        # collection, so this is a safe no-op there.
        spine = local_object("spine_%s" % coll.name)
        if spine is not None:
            paths.kc.set_road_spine_material(spine, matkey)
    return coll, None


class RKA_OT_set_pavement_matkey(bpy.types.Operator):
    """Change the pavement (segment/transition spine) or pad (intersection) material on an
    ALREADY-BUILT piece -- see `_set_piece_matkey`'s docstring for the full rationale. A separate
    operator (not a shared one with a `target` enum property) specifically so the panel can use
    `layout.operator_menu_enum` for a clean dropdown over the full material list -- that API
    invokes the operator with only the ONE enum property (`matkey`) set from the menu choice, with
    no way to also pre-select a second `target` property per button."""
    bl_idname = "rka.set_pavement_matkey"
    bl_label = "Set Pavement/Pad Material"
    bl_options = {'REGISTER', 'UNDO'}

    matkey: bpy.props.EnumProperty(name="Material", items=MATKEY_ITEMS, default='asphalt')

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll, err = _set_piece_matkey(context, 'PAVEMENT', self.matkey)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' pavement/pad material -> %s" % (coll.name, self.matkey))
        return {'FINISHED'}


class RKA_OT_set_curb_matkey(bpy.types.Operator):
    """Change the curb material on an ALREADY-BUILT piece -- see `_set_piece_matkey`'s docstring
    for the full rationale, and `RKA_OT_set_pavement_matkey`'s for why this is a separate operator
    rather than one shared class with a `target` property."""
    bl_idname = "rka.set_curb_matkey"
    bl_label = "Set Curb Material"
    bl_options = {'REGISTER', 'UNDO'}

    matkey: bpy.props.EnumProperty(name="Material", items=MATKEY_ITEMS, default='concrete')

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll, err = _set_piece_matkey(context, 'CURB', self.matkey)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' curb material -> %s" % (coll.name, self.matkey))
        return {'FINISHED'}


class RKA_OT_freeze_for_move(bpy.types.Operator):
    """Set `rka_live_edit = False` on the active piece so its WHOLE collection can be selected
    (Outliner > right-click the collection > Select Objects -- more reliable than a viewport
    box-select, which can miss a small marker) and Grab/Rotate/moved as a rigid group with ZERO
    risk of the live-edit handler deleting/recreating objects mid-drag: while frozen,
    `live_edit.py`'s depsgraph handler skips this collection entirely (see its
    `coll.get("rka_live_edit", True)` checks), so NOTHING regenerates during or after the move,
    no matter how the transform is done or how long it takes. This is the direct fix for a crash
    debouncing alone couldn't fully close: a depsgraph-driven rebuild, even delayed, can still
    land while Blender's own modal Transform operator is still holding the selection (a slow drag,
    a mid-drag pause) -- freezing removes the rebuild from the picture entirely for the whole
    operation, instead of trying to time around it.

    Run `Unfreeze & Rebuild` once you're done moving it -- geometry stays exactly as it was
    (untouched) until then, and rebuilds correctly at the new location/orientation because
    `get_or_create_origin_marker`'s live origin object moved right along with everything else.

    Also makes the origin marker the ACTIVE object and temporarily switches 'Transform Pivot
    Point' (viewport header) to 'Active Element' (restored to whatever it was on Unfreeze) --
    Blender's Rotate (R) pivots around whichever point that setting names, and TWO of its other
    options are traps for this addon specifically:
    - '3D Cursor' pivots around wherever the cursor happens to be left (often world origin),
      swinging the whole piece through a huge arc around an unrelated point instead of spinning it
      in place -- and this addon deliberately never MOVES the cursor itself to "fix" that, since
      other tools/plugins rely on its position for their own placement at the same time.
    - 'Median Point' looks like the fix but ISN'T here: most of a piece's own objects
      (`curb_*`/`pad_*`/`lanecl_*`/`mark_*`/`ribbon_*`/`spine_*`) are built with their absolute
      world-space shape baked directly into the mesh/curve data while the OBJECT ITSELF is left at
      local (0,0,0) (see `kit_common.road_spine`/`_poly_curve_with_radius`) -- so the median of
      every selected object's own `.location` is dragged toward world origin by however many such
      objects happen to be selected, reproducing nearly the same bad pivot as '3D Cursor'.
    'Active Element' sidesteps both: it pivots on exactly ONE object's `.location` -- the origin
    marker, which this operator makes active for you -- regardless of the cursor or how many
    zero-origin mesh objects are also selected. If the active object later changes (e.g. a
    viewport box-select re-picks one under the mouse instead of using the Outliner's 'Select
    Objects'), just click the origin marker again before rotating. Avoid 'Individual Origins'
    entirely -- it spins each object about its own point instead of orbiting the group, breaking
    the rigid-move assumption this whole workflow depends on."""
    bl_idname = "rka.freeze_for_move"
    bl_label = "Freeze For Move"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and coll.get("rka_live_edit", True)

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        coll["rka_live_edit"] = False
        marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
        ts = context.scene.tool_settings
        if marker is not None:
            coll["rka_prev_pivot_point"] = ts.transform_pivot_point
            ts.transform_pivot_point = 'ACTIVE_ELEMENT'
            marker.select_set(True)
            context.view_layer.objects.active = marker
        self.report({'INFO'}, "'%s' frozen -- Pivot Point set to 'Active Element' (its origin "
                               "marker, now active) so Rotate pivots on the piece itself, not the "
                               "3D cursor/world origin. Outliner > right-click its collection > "
                               "Select Objects, then Grab/Rotate freely. Run 'Unfreeze & Rebuild' "
                               "when done" % coll.name)
        return {'FINISHED'}


class RKA_OT_unfreeze_and_rebuild(bpy.types.Operator):
    """Clear `rka_live_edit` (re-enabling automatic live-edit) on the active piece, restore
    whatever 'Transform Pivot Point' was set to before `Freeze For Move` changed it, and run ONE
    explicit rebuild immediately -- safe here because it runs as a normal operator call, not from
    inside a depsgraph handler mid-drag. Use after `Freeze For Move` once you've finished
    repositioning the piece."""
    bl_idname = "rka.unfreeze_and_rebuild"
    bl_label = "Unfreeze & Rebuild"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and not coll.get("rka_live_edit", True)

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        coll["rka_live_edit"] = True
        prev_pivot = coll.get("rka_prev_pivot_point")
        if prev_pivot is not None:
            context.scene.tool_settings.transform_pivot_point = prev_pivot
            del coll["rka_prev_pivot_point"]
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' unfrozen and rebuilt at its new position" % coll.name)
        return {'FINISHED'}


class RKA_OT_freeze_all_for_move(bpy.types.Operator):
    """Bulk `Freeze For Move`: freezes EVERY local road_kit_authoring piece in the file at once
    (not just the active one), so a WHOLE road network can be selected and Grab/Rotate/Moved
    together with zero risk of live-edit regenerating anything mid-drag -- the safe way to
    reposition many pieces together (e.g. aligning a whole test network onto another district's
    road, or any multi-piece rearrange), which the single-piece `Freeze For Move` would otherwise
    need running once per piece for (confirmed real need: road_blender_godot.md -- moving/rotating
    every piece in `debug_road.blend` at once crashed Blender; `Freeze For Move`'s own docstring
    already explains why debouncing alone can't fully prevent that -- a depsgraph-driven rebuild
    can still land mid-drag during a slow move or a pause, regardless of how many pieces are
    involved. This operator is a pure bulk application of that ALREADY-VERIFIED-SAFE mechanism,
    not new reentrancy-handling logic).

    Deliberately does NOT touch the active object or Pivot Point (unlike the single-piece
    version) -- there is no one 'correct' pivot for an arbitrary multi-piece selection; set Pivot
    Point yourself before rotating (e.g. '3D Cursor', placed at your intended pivot) and avoid
    'Median Point'/'Individual Origins' for the same reason `Freeze For Move`'s own docstring
    gives (most generated objects sit at local (0,0,0) with their real shape baked into the mesh/
    curve data, so a location-based median/individual-origins pivot is meaningless here).
    Already-frozen pieces are left alone (idempotent -- safe to run again after adding a piece)."""
    bl_idname = "rka.freeze_all_for_move"
    bl_label = "Freeze ALL For Move"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(coll.library is None and _is_piece_collection(coll)
                    and coll.get("rka_live_edit", True) for coll in bpy.data.collections)

    def execute(self, context):
        n = 0
        for coll in bpy.data.collections:
            if coll.library is not None or not _is_piece_collection(coll):
                continue
            if coll.get("rka_live_edit", True):
                coll["rka_live_edit"] = False
                n += 1
        self.report({'INFO'}, "Froze %d piece(s) -- select everything and Grab/Rotate/Move "
                               "freely, then 'Unfreeze ALL & Rebuild' when done" % n)
        return {'FINISHED'}


class RKA_OT_unfreeze_all_and_rebuild(bpy.types.Operator):
    """Bulk `Unfreeze & Rebuild`: re-enables live-edit and rebuilds EVERY currently-frozen local
    piece in the file. Safe for the same reason the single-piece version is (`Unfreeze & Rebuild`'s
    own docstring) -- runs as a normal operator call, sequentially, not from inside a depsgraph
    handler mid-drag, so there is no reentrancy risk no matter how many pieces are rebuilt here.
    Does not restore any per-piece Pivot Point (the bulk freeze never changed it)."""
    bl_idname = "rka.unfreeze_all_and_rebuild"
    bl_label = "Unfreeze ALL & Rebuild"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(coll.library is None and _is_piece_collection(coll)
                    and not coll.get("rka_live_edit", True) for coll in bpy.data.collections)

    def execute(self, context):
        n = 0
        for coll in bpy.data.collections:
            if coll.library is not None or not _is_piece_collection(coll):
                continue
            if not coll.get("rka_live_edit", True):
                coll["rka_live_edit"] = True
                _rebuild_piece_in_place(context, coll)
                n += 1
        self.report({'INFO'}, "Unfroze + rebuilt %d piece(s)" % n)
        return {'FINISHED'}


def _select_piece_objects(context, coll):
    """Select every object in `coll` (a piece collection), origin marker active + Pivot Point set
    to 'Active Element'. Shared by `RKA_OT_select_piece` (from whatever's already active) and
    `RKA_OT_select_piece_by_name` (from a name, no active-object precondition)."""
    for o in context.selected_objects:
        o.select_set(False)
    for o in coll.objects:
        o.select_set(True)
    marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
    if marker is not None:
        marker.select_set(True)
        context.view_layer.objects.active = marker
        context.scene.tool_settings.transform_pivot_point = 'ACTIVE_ELEMENT'
    return marker


class RKA_OT_select_piece(bpy.types.Operator):
    """Select EVERY object belonging to the active piece (intersection/segment/lane transition) --
    the "select the whole thing" answer, instead of manually hunting through the Outliner or
    box-selecting in the viewport (which can miss a small marker Empty). Reuses the same
    `_live_edit_target_collection` resolution `Freeze For Move` uses, so it works from any object
    (or Outliner collection) belonging to the piece, frozen or not -- this is a pure selection
    convenience, it never touches `rka_live_edit`. The piece's origin marker ends up active (and
    Pivot Point set to 'Active Element'), so a follow-up Grab/Rotate pivots sensibly whether or not
    you've also run `Freeze For Move`.

    **This operator's `poll()` needs something piece-related ALREADY active/selected** -- it's a
    "select the REST of this piece" tool, not a bootstrapping one. To pick a FIRST piece from
    nothing (no Outliner click needed), use `RKA_OT_select_piece_by_name` instead (the panel's
    piece list button -- see `panel.py`)."""
    bl_idname = "rka.select_piece"
    bl_label = "Select Piece"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _live_edit_target_collection(context) is not None

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Select an intersection/segment (or one of its handle "
                                    "Empties) first")
            return {'CANCELLED'}
        _select_piece_objects(context, coll)
        self.report({'INFO'}, "Selected all %d object(s) in '%s'" % (len(coll.objects), coll.name))
        return {'FINISHED'}


class RKA_OT_select_piece_by_name(bpy.types.Operator):
    """Select a piece by its COLLECTION NAME directly -- 2026-07-28, user-reported: with nothing
    already selected, `RKA_OT_select_piece`'s poll() always failed (it needs something
    piece-related ALREADY active), so there was no panel-only way to select a FIRST piece at all,
    only via the Outliner. Unconditional poll (`coll_name` just needs to resolve to a real LOCAL
    piece collection) -- the panel's "Pieces in this file" list (see `panel.py`) is built from
    every `_is_piece_collection` match and wires one of these per piece, `coll_name` preset to that
    piece's own name via the button's own operator properties."""
    bl_idname = "rka.select_piece_by_name"
    bl_label = "Select Piece By Name"
    bl_options = {'REGISTER', 'UNDO'}

    coll_name: bpy.props.StringProperty(name="Piece", default="")

    def execute(self, context):
        coll = local_collection(self.coll_name)
        if coll is None or not _is_piece_collection(coll):
            self.report({'ERROR'}, "'%s' is not a local road_kit_authoring piece collection"
                         % self.coll_name)
            return {'CANCELLED'}
        _select_piece_objects(context, coll)
        self.report({'INFO'}, "Selected all %d object(s) in '%s'" % (len(coll.objects), coll.name))
        return {'FINISHED'}


class RKA_OT_select_arm(bpy.types.Operator):
    """Isolate a single arm_* marker Empty as the sole selection/active object -- the quick way to
    go from 'everything selected' (e.g. after `Select Piece`) back to just one arm, so its own
    origin is what a subsequent Grab+snap (Shift+S / Ctrl-drag) moves and pivots around. Safe to
    do while the intersection is frozen (`Freeze For Move`): a frozen piece's `live_edit.py`
    handler skips it entirely, so nothing fights a manual reposition of one arm until you run
    `Unfreeze & Rebuild` -- see `rebuild_intersection_in_place`'s docstring for how a deliberately
    snapped arm's exact position (angle AND distance) is now preserved on that rebuild.

    Resolves the arm WITHIN the active piece's own collection (via
    `_live_edit_target_collection`), not by a global `arm_<name>` object-name lookup -- arm names
    are only unique PER intersection ('A', 'B', ... on every one of them), so a global lookup could
    silently select a same-named arm belonging to a completely different intersection."""
    bl_idname = "rka.select_arm"
    bl_label = "Select Arm"
    bl_options = {'REGISTER', 'UNDO'}

    arm_name: bpy.props.StringProperty(name="Arm", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Activate an intersection's collection, or one of its "
                                    "markers/objects, first")
            return {'CANCELLED'}
        obj = next((o for o in coll.objects if o.get("rka_arm_name") == self.arm_name), None)
        if obj is None:
            self.report({'ERROR'}, "No arm named '%s' in '%s'" % (self.arm_name, coll.name))
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


def _next_arm_name(existing):
    """First unused single letter A-Z, else 'ArmN' -- matches `preset_nway`'s default naming."""
    for i in range(26):
        c = chr(ord('A') + i)
        if c not in existing:
            return c
    n = 0
    while ("Arm%d" % n) in existing:
        n += 1
    return "Arm%d" % n


def _widest_gap_angle(angles):
    """Midpoint angle (deg) of the largest angular gap between `angles` (wrapping) -- where a
    newly added arm is placed by default so it doesn't collide with an existing one."""
    if not angles:
        return 0.0
    ordered = sorted(a % 360.0 for a in angles)
    n = len(ordered)
    best_gap, best_mid = -1.0, 0.0
    for i in range(n):
        a, b = ordered[i], ordered[(i + 1) % n]
        gap = (b - a) % 360.0
        if gap == 0.0:
            gap = 360.0
        if gap > best_gap:
            best_gap, best_mid = gap, (a + gap / 2.0) % 360.0
    return best_mid


class RKA_OT_adjust_arm_lanes(bpy.types.Operator):
    """+/- the active arm_* marker's lane count (`rka_arm_lanes`) and immediately rebuild its
    intersection in place. The live-edit drag handler only watches for TRANSFORM changes, not
    custom-property edits, so hand-editing `rka_arm_lanes` in the Custom Properties panel needs a
    manual 'Rebuild From Handles' afterward to take effect -- this button does both in one click,
    the reliable answer to "still can't tweak lane count"."""
    bl_idname = "rka.adjust_arm_lanes"
    bl_label = "Adjust Arm Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        new_lanes = max(1, min(3, int(obj.get("rka_arm_lanes", 1)) + self.delta))
        obj["rka_arm_lanes"] = new_lanes
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Arm '%s' lanes -> %d" % (obj.get("rka_arm_name", "?"), new_lanes))
        return {'FINISHED'}


class RKA_OT_add_arm(bpy.types.Operator):
    """Add a new arm to an existing intersection, placed at the widest angular gap between its
    current arms, and rebuild in place. The answer to "still can't tweak number of arms per
    intersection" -- `rebuild_intersection_in_place` already generalizes to whatever `arm_*`
    Empties exist in the collection (no preset/arm-count is hardcoded downstream), so adding one
    marker is enough. Activate the intersection's collection, or any of its markers, first."""
    bl_idname = "rka.add_arm"
    bl_label = "Add Arm"
    bl_options = {'REGISTER', 'UNDO'}

    lanes: bpy.props.IntProperty(name="Lanes", default=1, min=1, max=3)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_arm_names" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        k = ik()
        marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
        if marker is None:
            self.report({'ERROR'}, "'%s' has no stored origin" % coll.name)
            return {'CANCELLED'}
        ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
        rka = context.scene.rka
        z = oz + rka.lane_surface_z
        tail_length = coll.get("rka_tail_length", 12.0)

        existing = [o for o in coll.objects if "rka_arm_name" in o.keys()]
        existing_names = {o["rka_arm_name"] for o in existing}
        existing_angles = [o.get("rka_arm_angle", 0.0) for o in existing]
        angle_deg = _widest_gap_angle(existing_angles)
        name = _next_arm_name(existing_names)

        d = k.arm_dir(angle_deg)
        arm_obj = bpy.data.objects.new("arm_%s" % name, None)
        arm_obj.empty_display_type = 'SINGLE_ARROW'
        arm_obj.empty_display_size = min(2.0, coll.get("rka_lane_width", 5.0) * 0.4)
        arm_obj.location = (ox + d[0] * tail_length, oy + d[1] * tail_length, z)
        arm_obj.rotation_euler = (0.0, 0.0, math.radians(angle_deg))
        arm_obj["rka_arm_name"] = name
        arm_obj["rka_arm_angle"] = angle_deg
        arm_obj["rka_arm_lanes"] = self.lanes
        arm_obj["rka_arm_oneway"] = ""
        arm_obj["rka_arm_lanes_out"] = 0
        arm_obj["rka_arm_tail_length"] = tail_length
        coll.objects.link(arm_obj)

        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Added arm '%s' at %.1f deg to '%s'" % (name, angle_deg, coll.name))
        return {'FINISHED'}


class RKA_OT_remove_arm(bpy.types.Operator):
    """Remove the active arm_* marker from its intersection and rebuild in place. Refuses to drop
    below 3 arms (a 2-arm 'intersection' is just a through street -- use a Straight Segment
    instead; this tool only ever adds/removes ARMS, never converts collection types)."""
    bl_idname = "rka.remove_arm"
    bl_label = "Remove Arm"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        remaining = len([o for o in coll.objects if "rka_arm_name" in o.keys()]) - 1
        if remaining < 3:
            self.report({'ERROR'}, "Can't remove -- an intersection needs at least 3 arms "
                                    "(has %d)" % (remaining + 1))
            return {'CANCELLED'}
        name = obj.get("rka_arm_name", "?")
        bpy.data.objects.remove(obj, do_unlink=True)
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Removed arm '%s' from '%s'" % (name, coll.name))
        return {'FINISHED'}


class RKA_OT_set_arm_oneway(bpy.types.Operator):
    """Set the active arm_* marker's traffic direction and rebuild in place: BOTH (default,
    symmetric -- lanes arrive and leave), IN (this arm only ever RECEIVES traffic -- no outgoing
    lanes, e.g. a one-way street feeding INTO this junction), OUT (this arm only ever SENDS
    traffic -- no incoming lanes, e.g. a one-way exit). Combine with 1 lane
    (`RKA_OT_adjust_arm_lanes`) for a true single-lane one-way arm -- the concrete "can an
    intersection accommodate a one-way, one-lane road" answer."""
    bl_idname = "rka.set_arm_oneway"
    bl_label = "Set Arm Direction"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(name="Direction", items=(
        ('BOTH', "Both Ways", "Symmetric -- lanes arrive and leave"),
        ('IN', "In Only", "Traffic only arrives via this arm (no outgoing lanes)"),
        ('OUT', "Out Only", "Traffic only leaves via this arm (no incoming lanes)"),
    ), default='BOTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        obj["rka_arm_oneway"] = "" if self.mode == 'BOTH' else self.mode
        rebuild_intersection_in_place(context, coll)
        self.report({'INFO'}, "Arm '%s' direction -> %s" % (obj.get("rka_arm_name", "?"), self.mode))
        return {'FINISHED'}


class RKA_OT_adjust_arm_lanes_out(bpy.types.Operator):
    """ASYMMETRIC WIDENING: +/- the active arm_* marker's `rka_arm_lanes_out` override -- the
    DEPARTING (CCW) lane count only, independent of `rka_arm_lanes` (which keeps governing the
    ARRIVING/CW count) -- and immediately rebuild in place. 0 means "no override, symmetric with
    Lanes" (`Arm.lanes_out=None`, `intersection_kit.py`'s back-compat default); the FIRST press
    from 0 seeds it at the current symmetric lane count before nudging, so pressing +/- from a
    fresh arm feels like "peel this side off and adjust it independently" rather than jumping
    straight to 1. This is the actual "widen only one side" answer -- since arriving lanes occupy
    the CW curb-to-centerline half and departing lanes occupy the CCW half, growing ONE of
    lanes/lanes_out moves ONLY that side's curb edge (see `Arm`'s docstring for why a raw sideways
    shift of an otherwise-symmetric width can't do this correctly)."""
    bl_idname = "rka.adjust_arm_lanes_out"
    bl_label = "Adjust Arm Departing Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_arm_name" in obj.keys()

    def execute(self, context):
        obj = context.active_object
        coll = obj.users_collection[0]
        current = int(obj.get("rka_arm_lanes_out", 0))
        base = current if current > 0 else int(obj.get("rka_arm_lanes", 1))
        new_lanes_out = max(0, min(3, base + self.delta))
        obj["rka_arm_lanes_out"] = new_lanes_out
        rebuild_intersection_in_place(context, coll)
        label = "symmetric (0)" if new_lanes_out == 0 else str(new_lanes_out)
        self.report({'INFO'}, "Arm '%s' departing lanes -> %s" %
                     (obj.get("rka_arm_name", "?"), label))
        return {'FINISHED'}


CLASSES = (RKA_OT_build_intersection, RKA_OT_rebuild_from_handles, RKA_OT_freeze_for_move,
           RKA_OT_unfreeze_and_rebuild, RKA_OT_freeze_all_for_move, RKA_OT_unfreeze_all_and_rebuild,
           RKA_OT_select_piece, RKA_OT_select_piece_by_name, RKA_OT_select_arm,
           RKA_OT_adjust_arm_lanes, RKA_OT_add_arm, RKA_OT_remove_arm, RKA_OT_set_arm_oneway,
           RKA_OT_adjust_arm_lanes_out, RKA_OT_set_lane_map,
           RKA_OT_set_pavement_matkey, RKA_OT_set_curb_matkey)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
