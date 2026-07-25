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

from . import custom_props, paths

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
)


def build_curb(name, pts3, coll, style, height, thickness):
    """Dispatch on `curb_style`: 'BOX' -> the original flat `swept_wall`; 'GUTTER' -> a
    curb-and-gutter cross-section (`swept_profile` + `gutter_curb_profile`) swept along the same
    exact points. Shared by `build_intersection_geometry` and `ops_segment.build_segment_geometry`."""
    if style == 'GUTTER':
        return paths.kc.swept_profile(
            name, pts3, paths.kc.gutter_curb_profile(thickness, height), coll, matkey="concrete")
    return paths.kc.swept_wall(name, pts3, h=height, coll=coll, matkey="concrete",
                                thickness=thickness, z0=0.0)


def join_meshes(context, objs, name):
    """Join a list of freshly-created, already-linked-into-the-view-layer mesh Objects into ONE
    mesh Object -- the "let the intersection mesh be one mesh" request: separate curb/ribbon
    pieces are convenient to generate (and independently colour/debug during authoring), but a
    single combined mesh is what actually gets handed to Godot/an artist for export. A 0- or
    1-object list is a no-op (just a rename, so callers can unconditionally use the returned
    object's name)."""
    if not objs:
        return None
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    for o in context.selected_objects:
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
    """Remove every curb_*/lanecl_*/ribbon_*/mesh_* object (+ its now-orphaned mesh/curve data)
    from `coll`, leaving marker Empties (arm_*/segend_*/segbend_*) untouched. The "delete the old
    generated geometry, keep the live-edit drag handles" step shared by both in-place rebuild
    paths (`rebuild_intersection_in_place`, `ops_segment.rebuild_segment_in_place`)."""
    prefixes = ("curb_", "lanecl_", "ribbon_", "mesh_")
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
    `rka_segbend`), return `((x, y), z_raw, parent_coll)` so a NEW piece can be built starting
    exactly there instead of at the 3D cursor -- `z_raw` is already converted back to the
    pre-`lane_surface_z` convention every `build_*_geometry` function expects, and `parent_coll`
    is the marker's own piece's parent (so the new piece lands as a SIBLING of it). This is the
    fix for "Build Intersection always uses the cursor, not wherever the segment/arm I just
    selected actually is" -- callers fall back to the 3D cursor when this returns None (no marker
    is the active object)."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    keys = obj.keys()
    if "rka_arm_name" not in keys and "rka_segend" not in keys and "rka_segbend" not in keys:
        return None
    rka = context.scene.rka
    loc = obj.location
    return ((loc.x, loc.y), loc.z - rka.lane_surface_z, parent_collection_of(obj.users_collection[0]))


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
                                 join_visual_mesh, origin_xy, z):
    """Build the curb + lane-centerline + ribbon objects for one intersection INTO `coll` (already
    created/linked) and return `(corners, movements, visual_objs)`. Shared by
    `build_intersection_geometry` (fresh build, also creates the arm_* marker Empties afterward)
    and `rebuild_intersection_in_place` (live-edit rebuild, keeps the existing markers) so the two
    paths can never drift apart -- exactly the same geometry math either way."""
    k = ik()
    corners = k.build_curb_corners(arms, kerb_radius, segments)
    try:
        movements = k.build_lane_movements(arms, kerb_radius, segments, tail_length=tail_length,
                                            lane_map=lane_map)
    except ValueError as exc:
        raise RkaBuildError("Lane Map Override: %s" % exc)

    cx, cy = origin_xy

    def to3(pt2):
        return (cx + pt2[0], cy + pt2[1], z)

    # Short, collection-relative names -- Blender's Outliner already nests these under their
    # collection (which itself carries the full junction_id), and nothing downstream parses these
    # specific names (WorldBaker's prefix table doesn't include curb_/lanecl_/roadribbon_/arm_ at
    # all -- every Godot-side lookup goes through the exported JSON's own `id`).
    visual_objs = []   # curb walls + ribbons only -- fed to gltf_export_path / join_visual_mesh
    for c in corners:
        pts3 = [to3(p) for p in c["arc"]]
        visual_objs.append(build_curb("curb_%s%s" % (c["arm_a"], c["arm_b"]), pts3, coll,
                                       curb_style, curb_height, curb_thickness))

    for m in movements:
        pts3 = [to3(p) for p in m["points"]]
        lane_tag = ("L%d" % m["lane_in"] if m["lane_in"] == m["lane_out"]
                    else "L%dto%d" % (m["lane_in"], m["lane_out"]))
        tag = "%s%s_%s" % (m["from"], m["to"], lane_tag)
        paths.kc.poly_curve("lanecl_%s" % tag, pts3, coll, loop=False, lane_width=lane_width,
                             oneway=True, end_behavior='CHAIN')
        visual_objs.append(paths.kc.flat_ribbon("ribbon_%s" % tag, pts3, lane_width / 2.0, coll,
                                                 matkey="asphalt"))

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return corners, movements, visual_objs


def rebuild_intersection_in_place(context, coll):
    """Live-editing counterpart to `build_intersection_geometry`: re-derive each arm's ANGLE from
    its `arm_*` marker Empty's CURRENT position (bearing from the stored `rka_origin`), then
    rebuild curb/lane objects in place -- no new collection, the arm Empties themselves are the
    drag handles ("bevel-style" adjustment). Called from `live_edit.py`'s `depsgraph_update_post`
    handler whenever an arm Empty's transform changes.

    Each arm's RADIUS (distance from origin) is intentionally NOT taken from the drag -- it's
    re-snapped back to the stored `tail_length` after rebuilding, so dragging an arm purely
    ROTATES it around the junction (reshaping the intersection) rather than also changing tail
    length, which the data model treats as one shared scalar across every arm, not a per-arm
    value. A no-op (returns immediately) if there's no stored origin, fewer than 3 arms survive
    the current drag position (e.g. one was dropped exactly on the origin), or the lane-map/angle
    combination is momentarily degenerate mid-drag -- the next tick, once the drag moves past it,
    recovers on its own."""
    k = ik()
    origin = custom_props.read_origin(coll)
    if origin is None:
        return
    ox, oy, oz = origin
    rka = context.scene.rka
    z = oz + rka.lane_surface_z
    tail_length = coll.get("rka_tail_length", 12.0)
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    lane_width = coll.get("rka_lane_width", 5.0)
    segments = coll.get("rka_segments", 8)
    curb_style = coll.get("rka_curb_style", 'BOX')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    lane_map = custom_props.read_lane_map_override(coll)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)

    arm_empties = [o for o in coll.objects if "rka_arm_name" in o.keys()]
    arms = []
    for o in arm_empties:
        dx, dy = o.location.x - ox, o.location.y - oy
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue   # dropped exactly on the origin mid-drag -- degenerate, skip this arm
        angle_deg = math.degrees(math.atan2(dy, dx)) % 360.0
        oneway = o.get("rka_arm_oneway", "") or None
        arms.append(k.Arm(o["rka_arm_name"], angle_deg, lane_width, int(o.get("rka_arm_lanes", 1)),
                           oneway=oneway))
    if len(arms) < 3:
        return

    clear_generated_mesh_objects(coll)
    try:
        _populate_intersection_mesh(context, coll, arms, kerb_radius, tail_length, segments,
                                     lane_width, curb_style, curb_height, curb_thickness, lane_map,
                                     join_visual_mesh, (ox, oy), z)
    except RkaBuildError:
        return   # e.g. two arms briefly coincide mid-drag -- leave geometry as the last-good state

    # Re-snap each arm empty back onto the fixed tail_length radius (see docstring) and keep its
    # arrow aligned with the new angle. Guarded by an epsilon so a clean drag (already exactly on
    # the radius) doesn't rewrite the transform and retrigger this same handler pass.
    by_name = {a.name: a for a in arms}
    for o in arm_empties:
        a = by_name.get(o["rka_arm_name"])
        if a is None:
            continue
        d = k.arm_dir(a.angle_deg)
        want = (ox + d[0] * tail_length, oy + d[1] * tail_length, z)
        cur = (o.location.x, o.location.y, o.location.z)
        if math.dist(want, cur) > 1e-4:
            o.location = want
        o["rka_arm_angle"] = a.angle_deg

    custom_props.write_build_settings(
        coll, arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms], arm_oneway=[a.oneway or "" for a in arms])


def build_intersection_geometry(context, parent_coll, cursor, preset, rotation_deg, side_angle,
                                 arm_angles_str, lane_width, lanes, lane_arm_overrides, kerb_radius,
                                 tail_length, segments, curb_style, curb_height, curb_thickness,
                                 lane_map, join_visual_mesh, export_path, gltf_export_path):
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

    Returns a dict: `{'coll', 'arms', 'corners', 'movements', 'visual_objs', 'export_note',
    'warnings'}` (`warnings` is a list of str -- non-fatal export failures the caller should
    surface via `self.report({'WARNING'}, ...)` but that don't prevent FINISHED). Raises
    `RkaBuildError` for anything that must abort before any geometry is created."""
    rka = context.scene.rka
    k = ik()

    if preset == '4WAY':
        arms = k.preset_4way(lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, 4))
    elif preset == '3WAY_T':
        arms = k.preset_3way_t(side_angle=side_angle, lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3))
    elif preset == '3WAY_Y':
        arms = k.preset_3way_y(angles=(0.0, side_angle, 2.0 * side_angle), lane_width=lane_width,
                                lanes=_arm_lane_list(lanes, lane_arm_overrides, 3))
    else:   # NWAY
        try:
            angles = [float(a.strip()) for a in arm_angles_str.split(",") if a.strip()]
        except ValueError:
            raise RkaBuildError("Arm Angles must be comma-separated numbers, e.g. '0,60,130,200,280'")
        if len(angles) < 3:
            raise RkaBuildError("NWAY needs at least 3 arm angles")
        arms = k.preset_nway(angles, lane_width=lane_width,
                              lanes=_arm_lane_list(lanes, lane_arm_overrides, len(angles)))

    if rotation_deg != 0.0:
        for a in arms:
            a.angle_deg = (a.angle_deg + rotation_deg) % 360.0

    cx, cy, cz_raw = cursor
    z = cz_raw + rka.lane_surface_z

    n = 1
    base_name = "Intersection_%s" % preset
    while base_name + ("_%03d" % n) in bpy.data.collections:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)

    corners, movements, visual_objs = _populate_intersection_mesh(
        context, coll, arms, kerb_radius, tail_length, segments, lane_width, curb_style,
        curb_height, curb_thickness, lane_map, join_visual_mesh, (cx, cy), z)

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
        coll.objects.link(arm_obj)

    # Permanent record of exactly how this was built -- native custom properties on the
    # collection, editable via Blender's Object/Collection Properties panel even without the
    # addon's redo panel (which is lost the moment you close the file). See custom_props.py.
    custom_props.write_build_settings(
        coll, preset=preset, kerb_radius=kerb_radius, lane_width=lane_width,
        tail_length=tail_length, segments=segments, curb_style=curb_style,
        curb_height=curb_height, curb_thickness=curb_thickness,
        arm_names=[a.name for a in arms], arm_angles=[a.angle_deg for a in arms],
        arm_lanes=[a.lanes for a in arms],
        arm_oneway=[a.oneway or "" for a in arms], lane_map=lane_map,
        # Raw (pre-lane_surface_z-offset) cursor position -- lets RKA_OT_extend_from_arm
        # reconstruct exact world-space port positions/tangents from this collection's own stored
        # arm data, without guessing where it was built.
        origin=[cx, cy, cz_raw])

    warnings = []
    export_note = ""
    if export_path:
        try:
            k.export_json(bpy.path.abspath(export_path), arms, kerb_radius, junction_id=coll.name,
                           segments=segments, tail_length=tail_length, z=z, lane_map=lane_map)
            export_note += ", json -> '%s'" % export_path
        except OSError as exc:
            warnings.append("Built geometry OK, but json export failed: %s" % exc)
    if gltf_export_path:
        try:
            paths.kc.export_gltf(visual_objs, bpy.path.abspath(gltf_export_path))
            export_note += ", glb -> '%s'" % gltf_export_path
        except Exception as exc:   # noqa: BLE001 -- bpy.ops export can raise a variety of types
            warnings.append("Built geometry OK, but glTF export failed: %s" % exc)

    return {"coll": coll, "arms": arms, "corners": corners, "movements": movements,
            "visual_objs": visual_objs, "export_note": export_note, "warnings": warnings}


class RKA_OT_build_intersection(bpy.types.Operator):
    """Build one intersection (rounded curb corners + a lanecl_* centerline and visual asphalt
    ribbon for every legal single-lane movement, plus an 'arm_*' marker Empty at each arm's tail)
    at the 3D cursor. Purely additive: creates a new collection, never touches lane_kit.blend or
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
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="BOX style: wall thickness. GUTTER style: total "
        "curb+gutter width (the real piece this mirrors is 0.6m)",
        default=0.25, min=0.01, unit='LENGTH')
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

        # If an arm_*/segend_*/segbend_* marker is the active object, build right there instead of
        # at the 3D cursor -- so "select a segment's end, then Build Intersection" actually lands
        # the new intersection on that segment's end, not wherever the cursor happens to be.
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
                self.export_path, self.gltf_export_path)
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
        self.report(
            {'INFO'},
            "Built '%s': %d arm(s), %d curb corner(s), %d lane movement(s) (radius=%.1fm)%s"
            % (result["coll"].name, len(result["arms"]), len(result["corners"]),
               len(result["movements"]), self.kerb_radius, note))
        return {'FINISHED'}


def _live_edit_target_collection(context):
    """The collection a manual 'Rebuild From Handles' should act on: the active object's own
    piece if it's a marker Empty (arm/segend/segbend, OR a curve-segment's `segcurve_driver`, OR
    the driving Curve object itself), else the active collection itself if it IS a piece. None if
    neither resolves."""
    obj = context.active_object
    if obj is not None and obj.users_collection:
        keys = obj.keys()
        if "rka_arm_name" in keys or "rka_segend" in keys or "rka_segbend" in keys \
                or "rka_curve_driver" in keys:
            return obj.users_collection[0]
        if obj.type == 'CURVE':
            for coll in bpy.data.collections:
                if coll.get("rka_curve_object") == obj.name:
                    return coll
    coll = context.view_layer.active_layer_collection.collection
    if coll is not None and ("rka_arm_names" in coll.keys() or "rka_p0" in coll.keys()
                              or "rka_curve_object" in coll.keys()):
        return coll
    return None


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
        from . import ops_segment
        if "rka_arm_names" in coll.keys():
            rebuild_intersection_in_place(context, coll)
        elif "rka_curve_object" in coll.keys():
            ops_segment.rebuild_segment_from_curve_in_place(context, coll)
        else:
            ops_segment.rebuild_segment_in_place(context, coll)
        self.report({'INFO'}, "Rebuilt '%s' from its current handle positions" % coll.name)
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
        origin = custom_props.read_origin(coll)
        if origin is None:
            self.report({'ERROR'}, "'%s' has no stored origin" % coll.name)
            return {'CANCELLED'}
        ox, oy, oz = origin
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


CLASSES = (RKA_OT_build_intersection, RKA_OT_rebuild_from_handles, RKA_OT_adjust_arm_lanes,
           RKA_OT_add_arm, RKA_OT_remove_arm, RKA_OT_set_arm_oneway)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
