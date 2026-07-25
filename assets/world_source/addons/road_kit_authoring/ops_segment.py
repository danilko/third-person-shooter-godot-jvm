"""Straight two-way road segment builder -- the piece missing between intersections. Neither
`RKA_OT_build_intersection` (only ever draws ROUNDED corners, not the straight curb run along an
arm's own sides) nor anything else in this addon previously generated a plain connecting stretch
of road; this fills that gap with the same visual style (curb walls + per-lane driving ribbon)
and the exact same lane JSON shape `WorldBaker`'s sidecar loader already consumes -- no Java
changes needed to bake a segment alongside intersections.

Two intersections (or a segment and an intersection) connect automatically at Godot bake/runtime
via `LaneGraph`'s endpoint-proximity clustering as long as their lane endpoints land within
JUNCTION_RADIUS (4.5 m) of each other -- position this segment's start/end to land on an existing
piece's port (see `build_ports` / a prior run's printed port positions) and no extra stitching
step is needed on the Blender side at all.

The actual build logic lives in `build_segment_geometry()`, a plain function with no `bpy.ops`
dispatch of its own -- `RKA_OT_build_straight_segment.execute()` is a thin wrapper around it, and
so are `RKA_OT_extend_from_arm` and `RKA_OT_insert_intersection_on_segment`. See
`ops_intersection.py`'s module docstring for why calling this function directly (instead of
`bpy.ops.rka.build_straight_segment(...)`) matters for Blender's F9 'Adjust Last Operation' panel.
"""
import math

import bpy

from . import custom_props, paths
from .ops_intersection import (CURB_STYLE_ITEMS, PRESET_ITEMS, RkaBuildError, active_marker_position,
                                build_curb, build_intersection_geometry, clear_generated_mesh_objects,
                                join_meshes, parent_collection_of)

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


def _populate_segment_mesh(context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style,
                            curb_height, curb_thickness, bend, curve_segments, elevation_delta,
                            bend_z, join_visual_mesh, z_base):
    """Build the curb + lane-centerline + ribbon objects for one segment INTO `coll` (already
    created/linked) and return `visual_objs`. Shared by `build_segment_geometry` (fresh build,
    also creates the segend_A/segend_B/segbend marker Empties afterward) and
    `rebuild_segment_in_place` (live-edit rebuild, keeps the existing markers). `lanes_backward` --
    see `intersection_kit.build_segment_from_spine` -- may be 0 for a one-way road; `lanes` and
    `lanes_backward` may not both be 0."""
    k = ik()
    seg = k.build_straight_segment(p0, p1, lane_width, lanes, segment_id="SEG", bend=bend,
                                    segments=curve_segments, z0=0.0, z1=elevation_delta,
                                    bend_z=bend_z, lanes_backward=lanes_backward)

    def to3(pt):
        return (pt[0], pt[1], z_base + pt[2])

    # Short, collection-relative names -- see the matching comment in ops_intersection.py.
    visual_objs = []
    for side, curb_pts in zip(("L", "R"), seg["curbs"]):
        pts3 = [to3(p) for p in curb_pts]
        visual_objs.append(build_curb(
            "curb_%s" % side, pts3, coll, curb_style, curb_height, curb_thickness))

    for m in seg["lanes"]:
        pts3 = [to3(p) for p in m["points"]]
        tag = "%s%s_L%d" % (m["from"], m["to"], m["lane_in"])
        paths.kc.poly_curve(
            "lanecl_%s" % tag, pts3, coll, loop=False,
            lane_width=lane_width, oneway=True, end_behavior='CHAIN')
        visual_objs.append(paths.kc.flat_ribbon(
            "ribbon_%s" % tag, pts3, lane_width / 2.0, coll, matkey="asphalt"))

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return visual_objs


def _bend_control_point(k, p0, p1, bend):
    """The XY control point `bend` meters perpendicular from the p0->p1 chord's midpoint -- the
    canonical position `segbend` markers sit at/get re-snapped to. Shared by `build_segment_geometry`
    (placing the marker) and `rebuild_segment_in_place` (re-snapping it after a drag)."""
    mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
    dir_n = k.vnorm(k.vsub(p1, p0))
    return k.vadd(mid, k.vscale(k.perp_ccw(dir_n), bend))


def build_segment_geometry(context, parent_coll, p0_raw, direction_deg, length, lane_width, lanes,
                            curb_style, curb_height, curb_thickness, bend, curve_segments,
                            elevation_delta, bend_z, join_visual_mesh, export_path,
                            gltf_export_path, base_name="Segment", lanes_backward=None):
    """Pure build logic behind `RKA_OT_build_straight_segment` -- no `bpy.ops` dispatch (see
    module docstring). `p0_raw` is `(x, y, z)` -- `z` is the RAW cursor-equivalent height, before
    `context.scene.rka.lane_surface_z` is added (same convention as
    `ops_intersection.build_intersection_geometry`'s `cursor` param). `lanes_backward` -- see
    `intersection_kit.build_segment_from_spine` -- defaults to `lanes` (symmetric) when None; may
    be 0 for a one-way road (`lanes` and `lanes_backward` may not both be 0).

    Returns a dict: `{'coll', 'p0' (2D), 'p1' (2D), 'end_z_raw', 'visual_objs', 'export_note',
    'warnings'}`. `end_z_raw` is `p0_raw`'s z plus `elevation_delta` -- the raw height a caller
    should hand to the NEXT piece so a chain continues at the right elevation, not just the right
    XY (`RKA_OT_build_straight_segment`'s cursor auto-advance uses this)."""
    rka = context.scene.rka
    k = ik()
    lanes_backward = lanes if lanes_backward is None else lanes_backward

    cx, cy, cz_raw = p0_raw
    z = cz_raw + rka.lane_surface_z
    rad = math.radians(direction_deg)
    p0 = (cx, cy)
    p1 = (cx + length * math.cos(rad), cy + length * math.sin(rad))

    n = 1
    while base_name + ("_%03d" % n) in bpy.data.collections:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)

    visual_objs = _populate_segment_mesh(
        context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style, curb_height,
        curb_thickness, bend, curve_segments, elevation_delta, bend_z, join_visual_mesh, z)

    # Marker Empties -- the live-edit "drag to reshape" handles (see live_edit.py): segend_A/B sit
    # at the two endpoints (drag = change length/direction/elevation), segbend sits at the current
    # bend control point (drag sideways = lateral Bend, drag vertically = Vertical Bend). Any of
    # them moving re-derives p0/p1/bend/bend_z and rebuilds this segment in place -- see
    # `rebuild_segment_in_place`. Also doubles as the click target for "Build Intersection"/"Build
    # Straight Segment"'s active-marker snap (`ops_intersection.active_marker_position`).
    def make_marker(name, pos, prop_key, prop_val):
        o = bpy.data.objects.new(name, None)
        o.empty_display_type = 'PLAIN_AXES'
        o.empty_display_size = min(1.5, lane_width * 0.3)
        o.location = pos
        o[prop_key] = prop_val
        coll.objects.link(o)
        return o

    make_marker("segend_A", (p0[0], p0[1], z), "rka_segend", "A")
    make_marker("segend_B", (p1[0], p1[1], z + elevation_delta), "rka_segend", "B")
    control = _bend_control_point(k, p0, p1, bend)
    make_marker("segbend", (control[0], control[1], z + elevation_delta / 2.0 + bend_z),
                "rka_segbend", True)

    custom_props.write_build_settings(
        coll, direction_deg=direction_deg, length=length,
        lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward, curb_style=curb_style,
        curb_height=curb_height, curb_thickness=curb_thickness,
        bend=bend, curve_segments=curve_segments, elevation_delta=elevation_delta, bend_z=bend_z,
        # Full 3D points (raw cursor Z, matching RKA_OT_build_intersection's rka_origin
        # convention) -- lets RKA_OT_insert_intersection_on_segment reconstruct this segment
        # exactly (including its elevation at either end) without re-deriving anything.
        p0=[p0[0], p0[1], cz_raw], p1=[p1[0], p1[1], cz_raw + elevation_delta])

    warnings = []
    export_note = ""
    if export_path:
        try:
            k.export_segment_json(
                bpy.path.abspath(export_path), p0, p1,
                lane_width=lane_width, lanes=lanes, segment_id=coll.name, z=z, bend=bend,
                segments=curve_segments, z0=0.0, z1=elevation_delta, bend_z=bend_z,
                lanes_backward=lanes_backward)
            export_note += ", json -> '%s'" % export_path
        except OSError as exc:
            warnings.append("Built geometry OK, but json export failed: %s" % exc)

    if gltf_export_path:
        try:
            paths.kc.export_gltf(visual_objs, bpy.path.abspath(gltf_export_path))
            export_note += ", glb -> '%s'" % gltf_export_path
        except Exception as exc:   # noqa: BLE001 -- bpy.ops export can raise a variety of types
            warnings.append("Built geometry OK, but glTF export failed: %s" % exc)

    return {"coll": coll, "p0": p0, "p1": p1, "end_z_raw": cz_raw + elevation_delta,
            "visual_objs": visual_objs, "export_note": export_note, "warnings": warnings}


def rebuild_segment_in_place(context, coll):
    """Live-editing counterpart to `build_segment_geometry`: re-derive p0/p1 from segend_A/
    segend_B's CURRENT world positions, bend/bend_z from segbend's position (projected onto the
    chord's perpendicular+vertical plane -- any along-the-chord component of its drag is ignored,
    then the marker is re-snapped so it doesn't visually drift off that plane), and rebuild
    curb/lane objects in place. Called from `live_edit.py`'s `depsgraph_update_post` handler
    whenever one of the three markers moves. A no-op if p0/p1 have collapsed to (near) the same
    point mid-drag -- the next tick, once the drag moves past it, recovers on its own."""
    k = ik()
    a_obj = b_obj = bend_obj = None
    for o in coll.objects:
        if o.get("rka_segend") == "A":
            a_obj = o
        elif o.get("rka_segend") == "B":
            b_obj = o
        elif "rka_segbend" in o.keys():
            bend_obj = o
    if a_obj is None or b_obj is None:
        return

    p0 = (a_obj.location.x, a_obj.location.y)
    p1 = (b_obj.location.x, b_obj.location.y)
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if length < 0.5:
        return

    rka = context.scene.rka
    z_base = a_obj.location.z
    cz_raw = z_base - rka.lane_surface_z
    z1_world = b_obj.location.z
    elevation_delta = z1_world - z_base
    direction_deg = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))

    bend, bend_z = 0.0, 0.0
    if bend_obj is not None:
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        dir_n = k.vnorm(k.vsub(p1, p0))
        perp = k.perp_ccw(dir_n)
        offset = k.vsub((bend_obj.location.x, bend_obj.location.y), mid)
        bend = offset[0] * perp[0] + offset[1] * perp[1]
        bend_z = bend_obj.location.z - (z_base + z1_world) / 2.0

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    curb_style = coll.get("rka_curb_style", 'BOX')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    curve_segments = coll.get("rka_curve_segments", 8)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)

    clear_generated_mesh_objects(coll)
    _populate_segment_mesh(context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style,
                            curb_height, curb_thickness, bend, curve_segments, elevation_delta,
                            bend_z, join_visual_mesh, z_base)

    if bend_obj is not None:
        control = _bend_control_point(k, p0, p1, bend)
        want = (control[0], control[1], (z_base + z1_world) / 2.0 + bend_z)
        cur = (bend_obj.location.x, bend_obj.location.y, bend_obj.location.z)
        if math.dist(want, cur) > 1e-4:
            bend_obj.location = want

    custom_props.write_build_settings(
        coll, direction_deg=direction_deg, length=length, bend=bend, bend_z=bend_z,
        elevation_delta=elevation_delta, p0=[p0[0], p0[1], cz_raw],
        p1=[p1[0], p1[1], cz_raw + elevation_delta])


class RKA_OT_build_straight_segment(bpy.types.Operator):
    """Build one straight (or gently curved/sloped) two-way road segment (curb walls + a
    lanecl_* centerline and visual asphalt ribbon per lane, both directions) from the 3D cursor,
    `length` meters along `direction_deg`. Purely additive: creates a new collection, never
    touches an existing piece. Position the cursor at an existing intersection's port (see its
    printed port positions, or `lib/intersection_kit.py`'s build_ports) to connect them --
    LaneGraph does the rest at bake time via proximity, no explicit stitching needed here.

    With 'Auto-Advance Cursor' on (default), the 3D cursor moves to this segment's end point
    after building -- so pressing this operator again continues the road from where the last one
    left off, instead of starting over at the same spot (e.g. the world origin, if the cursor was
    never moved)."""
    bl_idname = "rka.build_straight_segment"
    bl_label = "Build Straight Segment"
    bl_options = {'REGISTER', 'UNDO'}

    direction_deg: bpy.props.FloatProperty(
        name="Direction", description="Degrees from world +X the segment runs, starting at the "
        "3D cursor", default=0.0, min=-360.0, max=360.0)
    length: bpy.props.FloatProperty(
        name="Length", default=40.0, min=1.0, unit='LENGTH')
    lane_width: bpy.props.FloatProperty(
        name="Lane Width", default=5.0, min=0.5, unit='LENGTH')
    lanes: bpy.props.IntProperty(
        name="Lanes Forward", default=1, min=0, max=3,
        description="Lane count in the A->B direction. 0 is only valid if Lanes Backward is "
                     "nonzero -- a road needs at least one lane SOMEWHERE")
    lanes_backward: bpy.props.IntProperty(
        name="Lanes Backward", default=1, min=0, max=3,
        description="Lane count in the B->A direction. 0 makes this a ONE-WAY road (e.g. "
                     "Lanes Forward=1, Lanes Backward=0 = a one-way single-lane road)")
    curb_style: bpy.props.EnumProperty(
        name="Curb Style", items=CURB_STYLE_ITEMS, default='BOX',
        description="BOX = plain flat wall. GUTTER = stepped curb-and-gutter profile matching "
                     "the real kit_side_straight_city_gutter_curb_w0p6m_l5m piece's silhouette")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="BOX style: wall thickness. GUTTER style: total "
        "curb+gutter width (the real piece this mirrors is 0.6m)",
        default=0.25, min=0.01, unit='LENGTH')
    bend: bpy.props.FloatProperty(
        name="Bend", description="Lateral offset (m) of a control point at the segment's "
        "midpoint -- 0 (default) is dead straight; nonzero gently curves the road via a "
        "quadratic bezier (positive = bends left of travel)", default=0.0)
    curve_segments: bpy.props.IntProperty(
        name="Curve Segments", description="Polyline segments when Bend/Vertical Bend != 0 "
        "(ignored when both are 0)", default=8, min=2, max=32)
    elevation_delta: bpy.props.FloatProperty(
        name="Elevation Delta", description="Constant grade/slope: how much higher (or, if "
        "negative, lower) the segment's END is than its START", default=0.0, unit='LENGTH')
    bend_z: bpy.props.FloatProperty(
        name="Vertical Bend", description="Crest/dip bump (m) at the segment's midpoint, on top "
        "of Elevation Delta's straight grade -- positive = hill, negative = dip. Independent of "
        "the lateral Bend, so a road can curve sideways and/or up-down at once", default=0.0,
        unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine the two curb walls + every lane ribbon into a single mesh object "
                     "after building")
    auto_advance_cursor: bpy.props.BoolProperty(
        name="Auto-Advance Cursor", default=True,
        description="Move the 3D cursor to this segment's end point after building, so the NEXT "
                     "'Build Straight Segment' / 'Build Intersection' continues the road from "
                     "here instead of starting over at the same spot")
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", description="Optional: write the lane sidecar "
        "(lib/intersection_kit.py's export_segment_json) here after building. Blank = skip",
        default="", subtype='FILE_PATH')
    gltf_export_path: bpy.props.StringProperty(
        name="Export .glb", description="Optional: export the built visual geometry (curb walls "
        "+ driving-surface ribbons -- not the lanecl_* data curves) to a .glb here. Blank = skip",
        default="", subtype='FILE_PATH')

    def execute(self, context):
        if self.lanes == 0 and self.lanes_backward == 0:
            self.report({'ERROR'}, "Lanes Forward and Lanes Backward can't both be 0 -- a road "
                                    "needs at least one lane somewhere")
            return {'CANCELLED'}

        # If an arm_*/segend_*/segbend_* marker is the active object, start right there instead of
        # at the 3D cursor (same fix as RKA_OT_build_intersection -- see active_marker_position).
        marker = active_marker_position(context)
        if marker is not None:
            (cx, cy), cz_raw, parent_coll = marker
        else:
            cursor = context.scene.cursor.location
            cx, cy, cz_raw = cursor.x, cursor.y, cursor.z
            parent_coll = context.view_layer.active_layer_collection.collection

        result = build_segment_geometry(
            context, parent_coll, (cx, cy, cz_raw), self.direction_deg, self.length,
            self.lane_width, self.lanes, self.curb_style, self.curb_height, self.curb_thickness,
            self.bend, self.curve_segments, self.elevation_delta, self.bend_z,
            self.join_visual_mesh, self.export_path, self.gltf_export_path,
            lanes_backward=self.lanes_backward)

        for w in result["warnings"]:
            self.report({'WARNING'}, w)

        if self.auto_advance_cursor:
            context.scene.cursor.location = (result["p1"][0], result["p1"][1], result["end_z_raw"])

        for o in context.selected_objects:
            o.select_set(False)
        self.report(
            {'INFO'},
            "Built '%s': %d lane(s) forward, %d backward, %.1fm long%s"
            % (result["coll"].name, self.lanes, self.lanes_backward, self.length,
               result["export_note"]))
        return {'FINISHED'}


def _resolve_intersection_and_arm(context, requested_arm_name):
    """(coll, arm_name) for `RKA_OT_extend_from_arm` -- accepts EITHER the intersection's own
    collection active in the Outliner (original workflow, `arm_name` typed by hand) OR one of its
    `arm_*` marker Empties as the active object in the viewport (click the arm, press the
    operator, no typing needed -- the concrete answer to "use the arm to adjust/extend").
    `(None, None)` if neither resolves."""
    obj = context.active_object
    if obj is not None and "rka_arm_name" in obj.keys() and obj.users_collection:
        coll = obj.users_collection[0]
        if "rka_arm_names" in coll.keys():
            return coll, (requested_arm_name or obj["rka_arm_name"])
    coll = context.view_layer.active_layer_collection.collection
    if coll is not None and "rka_arm_names" in coll.keys():
        return coll, requested_arm_name
    return None, None


class RKA_OT_extend_from_arm(bpy.types.Operator):
    """Extend a new straight segment outward from an existing intersection's arm, positioned and
    oriented EXACTLY to continue it -- reads the intersection's own stored arm data
    (`RKA_OT_build_intersection`'s `rka_arm_names`/`rka_arm_angles`/`rka_arm_lanes`/`rka_origin`/
    `rka_tail_length` custom properties), so the new segment's own lane offsets land exactly on
    that arm's ports (both are built the same "centerline + symmetric offset" way), not just
    within `LaneGraph`'s proximity tolerance.

    Either select/activate the intersection's collection in the Outliner first, OR click one of
    its 'arm_*' marker Empties in the viewport (its name auto-fills 'Arm' below) -- poll fails if
    neither is active."""
    bl_idname = "rka.extend_from_arm"
    bl_label = "Extend From Arm"
    bl_options = {'REGISTER', 'UNDO'}

    arm_name: bpy.props.StringProperty(
        name="Arm", description="Name of the arm to extend from -- see the active intersection "
        "collection's 'rka_arm_names' custom property for the valid choices. Leave blank if an "
        "'arm_*' marker Empty is the active object; it fills this in automatically", default="")
    length: bpy.props.FloatProperty(name="Length", default=40.0, min=1.0, unit='LENGTH')
    bend: bpy.props.FloatProperty(name="Bend", default=0.0)
    curve_segments: bpy.props.IntProperty(name="Curve Segments", default=8, min=2, max=32)
    elevation_delta: bpy.props.FloatProperty(
        name="Elevation Delta", default=0.0, unit='LENGTH',
        description="Constant grade/slope from the arm's port to this segment's far end")
    bend_z: bpy.props.FloatProperty(
        name="Vertical Bend", default=0.0, unit='LENGTH',
        description="Crest/dip bump (m) at the segment's midpoint")
    curb_style: bpy.props.EnumProperty(name="Curb Style", items=CURB_STYLE_ITEMS, default='BOX')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine the two curb walls + every lane ribbon into a single mesh object "
                     "after building")
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')
    gltf_export_path: bpy.props.StringProperty(
        name="Export .glb", default="", subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        coll, _ = _resolve_intersection_and_arm(context, "")
        return coll is not None

    def execute(self, context):
        coll, arm_name = _resolve_intersection_and_arm(context, self.arm_name)
        if coll is None:
            self.report({'ERROR'}, "Activate an intersection's collection, or select one of its "
                                    "'arm_*' marker Empties, first")
            return {'CANCELLED'}
        arms = custom_props.read_arms(coll)
        origin = custom_props.read_origin(coll)
        tail_length = coll.get("rka_tail_length", 12.0)
        lane_width = coll.get("rka_lane_width", 5.0)
        if arms is None or origin is None:
            self.report({'ERROR'}, "'%s' has no stored arm data -- was it built by 'Build "
                                    "Intersection'?" % coll.name)
            return {'CANCELLED'}
        match = next((a for a in arms if a[0] == arm_name), None)
        if match is None:
            self.report({'ERROR'}, "Arm '%s' not found in '%s' (arms: %s)" %
                         (arm_name, coll.name, ", ".join(a[0] for a in arms)))
            return {'CANCELLED'}
        _, angle_deg, arm_lanes = match

        # If the arm is one-way (RKA_OT_set_arm_oneway), the extended segment matches its
        # direction automatically: an 'IN'-only arm (only ever RECEIVES traffic, i.e. cars travel
        # TOWARD the junction along it) means 0 lanes LEAVING the junction (forward, A->B, since
        # `angle_deg` points outward/away from the junction) and `arm_lanes` lanes arriving
        # (backward, B->A); 'OUT'-only is the mirror. A plain (both-ways) arm stays symmetric --
        # the historical behavior.
        arm_obj = next((o for o in coll.objects if o.get("rka_arm_name") == arm_name), None)
        arm_oneway = (arm_obj.get("rka_arm_oneway", "") or None) if arm_obj is not None else None
        lanes_forward = 0 if arm_oneway == 'IN' else arm_lanes
        lanes_backward = 0 if arm_oneway == 'OUT' else arm_lanes

        rad = math.radians(angle_deg)
        ox, oy, oz = origin
        px = ox + tail_length * math.cos(rad)
        py = oy + tail_length * math.sin(rad)

        result = build_segment_geometry(
            context, parent_collection_of(coll), (px, py, oz), angle_deg, self.length, lane_width,
            lanes_forward, self.curb_style, self.curb_height, self.curb_thickness, self.bend,
            self.curve_segments, self.elevation_delta, self.bend_z, self.join_visual_mesh,
            self.export_path, self.gltf_export_path, lanes_backward=lanes_backward)

        for w in result["warnings"]:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Extended '%s' arm '%s' by %.1fm%s" %
                     (coll.name, arm_name, self.length, result["export_note"]))
        return {'FINISHED'}


def _closest_arm(arms, target_deg):
    """The (name, angle_deg, lanes) entry whose angle is nearest `target_deg` -- used to find
    "the arm pointing roughly this way" without assuming a specific preset's arm-naming
    convention (3-way T's forward/backward arms are 'A'/'B', but a 4-way's are 'N'/'S' or
    whichever pair the rotation lined up with)."""
    def angdiff(a, b):
        d = (a - b) % 360.0
        return min(d, 360.0 - d)
    return min(arms, key=lambda a: angdiff(a[1], target_deg))


class RKA_OT_insert_intersection_on_segment(bpy.types.Operator):
    """Splice a new intersection into the middle of an existing straight segment: DELETES the
    active Segment collection and rebuilds it as two shorter segments on either side of a new
    intersection at the chosen point along it (auto-replace -- confirmed default; these
    collections are addon-generated only, this never touches anything hand-authored). The
    segment's own direction becomes the new intersection's through-street (a 3-way T by
    default); the new side arm is left as a dangling port unless `side_length` > 0. Select/
    activate the segment's collection first (poll fails otherwise).

    This whole splice runs as ONE flat operator (no nested bpy.ops.rka.* calls) so it is a single
    undo step and its own F9 'Adjust Last Operation' panel actually shows fraction/preset/curb
    style/etc. and re-applies them correctly."""
    bl_idname = "rka.insert_intersection_on_segment"
    bl_label = "Insert Intersection On Segment"
    bl_options = {'REGISTER', 'UNDO'}

    fraction: bpy.props.FloatProperty(
        name="Split Fraction", description="0 = at the segment's start, 1 = at its end",
        default=0.5, min=0.01, max=0.99)
    preset: bpy.props.EnumProperty(name="Preset", items=PRESET_ITEMS, default='3WAY_T')
    side_angle: bpy.props.FloatProperty(
        name="Side/3rd Arm Angle", default=90.0, min=1.0, max=179.0)
    side_length: bpy.props.FloatProperty(
        name="Side Arm Length", description="If > 0, also extend a segment out from the new "
        "side arm by this much. 0 = leave it a dangling port", default=0.0, min=0.0, unit='LENGTH')
    kerb_radius: bpy.props.FloatProperty(name="Kerb Radius", default=9.0, min=1.0, unit='LENGTH')
    tail_length: bpy.props.FloatProperty(
        name="Approach Tail Length", default=12.0, min=1.0, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine each rebuilt piece's curb walls + lane ribbons into one mesh object")

    @classmethod
    def poll(cls, context):
        coll = context.view_layer.active_layer_collection.collection
        return coll is not None and "rka_p0" in coll.keys() and "rka_p1" in coll.keys()

    def execute(self, context):
        coll = context.view_layer.active_layer_collection.collection
        p0, p1 = coll["rka_p0"], coll["rka_p1"]
        lane_width = coll.get("rka_lane_width", 5.0)
        lanes = coll.get("rka_lanes", 1)
        curb_style = coll.get("rka_curb_style", 'BOX')
        curb_height = coll.get("rka_curb_height", 0.15)
        curb_thickness = coll.get("rka_curb_thickness", 0.25)
        x0, y0, z0r = p0[0], p0[1], p0[2]
        x1, y1, z1r = p1[0], p1[1], p1[2]

        split_x = x0 + (x1 - x0) * self.fraction
        split_y = y0 + (y1 - y0) * self.fraction
        split_zr = z0r + (z1r - z0r) * self.fraction
        dir_deg = math.degrees(math.atan2(y1 - y0, x1 - x0))
        len_to_p1 = math.hypot(x1 - split_x, y1 - split_y) - self.tail_length
        len_to_p0 = math.hypot(split_x - x0, split_y - y0) - self.tail_length
        if len_to_p1 < 1.0 or len_to_p0 < 1.0:
            self.report({'ERROR'}, "Split point too close to an end for the new intersection's "
                                    "own tail_length (%.1fm) to fit -- adjust Split Fraction or "
                                    "reduce Approach Tail Length" % self.tail_length)
            return {'CANCELLED'}

        parent = parent_collection_of(coll)

        # Delete the original segment collection -- objects (+ their mesh/curve data) then the
        # collection itself. Confirmed auto-replace behavior (see class docstring).
        for obj in list(coll.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
        bpy.data.collections.remove(coll)
        # The just-deleted collection was necessarily the active one (poll requires it) -- fall
        # back to the view layer's root so nothing downstream depends on a dangling reference.
        context.view_layer.active_layer_collection = context.view_layer.layer_collection

        try:
            ires = build_intersection_geometry(
                context, parent, (split_x, split_y, split_zr), self.preset, dir_deg,
                self.side_angle, "", lane_width, lanes, [0, 0, 0, 0], self.kerb_radius,
                self.tail_length, 8, curb_style, curb_height, curb_thickness, None,
                self.join_visual_mesh, "", "")
        except RkaBuildError as exc:
            self.report({'ERROR'}, "Failed to build the replacement intersection: %s" % exc)
            return {'CANCELLED'}
        for w in ires["warnings"]:
            self.report({'WARNING'}, w)
        new_coll = ires["coll"]

        new_arms = custom_props.read_arms(new_coll)
        forward_arm = _closest_arm(new_arms, dir_deg)[0]
        backward_arm = _closest_arm(new_arms, dir_deg + 180.0)[0]

        def extend(arm_name, length):
            _, angle_deg, arm_lanes = next(a for a in new_arms if a[0] == arm_name)
            rad = math.radians(angle_deg)
            px = split_x + self.tail_length * math.cos(rad)
            py = split_y + self.tail_length * math.sin(rad)
            r = build_segment_geometry(
                context, parent, (px, py, split_zr), angle_deg, length, lane_width, arm_lanes,
                curb_style, curb_height, curb_thickness, 0.0, 8, 0.0, 0.0,
                self.join_visual_mesh, "", "")
            for w in r["warnings"]:
                self.report({'WARNING'}, w)

        extend(forward_arm, len_to_p1)
        extend(backward_arm, len_to_p0)

        if self.side_length > 0.0 and len(new_arms) >= 3:
            side_arm = next((a[0] for a in new_arms if a[0] not in (forward_arm, backward_arm)), None)
            if side_arm is not None:
                extend(side_arm, self.side_length)

        self.report({'INFO'}, "Inserted '%s' into the segment at fraction %.2f" %
                     (new_coll.name, self.fraction))
        return {'FINISHED'}


class RKA_OT_adjust_segment_lanes(bpy.types.Operator):
    """+/- a segment's lane count in ONE direction (`backward=False` -> `rka_lanes`, the A->B/
    forward count; `backward=True` -> `rka_lanes_backward`) and immediately rebuild it in place.
    Same reasoning as `ops_intersection.RKA_OT_adjust_arm_lanes` -- the live-edit drag handler
    only watches marker TRANSFORMS, not custom-property edits, so this button is the reliable live
    control for lane count. Either side may reach 0 (a one-way road), but refuses to drop BOTH to
    0 at once -- a road needs at least one lane somewhere."""
    bl_idname = "rka.adjust_segment_lanes"
    bl_label = "Adjust Segment Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)
    backward: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is not None and obj.users_collection and "rka_p0" in obj.users_collection[0].keys():
            return True
        coll = context.view_layer.active_layer_collection.collection
        return coll is not None and "rka_p0" in coll.keys()

    def execute(self, context):
        obj = context.active_object
        if obj is not None and obj.users_collection and "rka_p0" in obj.users_collection[0].keys():
            coll = obj.users_collection[0]
        else:
            coll = context.view_layer.active_layer_collection.collection
        key = "rka_lanes_backward" if self.backward else "rka_lanes"
        other_key = "rka_lanes" if self.backward else "rka_lanes_backward"
        new_val = max(0, min(3, int(coll.get(key, 1)) + self.delta))
        other_val = int(coll.get(other_key, 1))
        if new_val == 0 and other_val == 0:
            self.report({'ERROR'}, "Can't set both directions to 0 -- a road needs at least one "
                                    "lane somewhere")
            return {'CANCELLED'}
        coll[key] = new_val
        rebuild_segment_in_place(context, coll)
        self.report({'INFO'}, "'%s' %s lanes -> %d" %
                     (coll.name, "backward" if self.backward else "forward", new_val))
        return {'FINISHED'}


def _populate_segment_mesh_from_spine(context, coll, spine, lane_width, lanes, lanes_backward,
                                       curb_style, curb_height, curb_thickness, join_visual_mesh):
    """Like `_populate_segment_mesh`, but for an ARBITRARY 3D spine (already ABSOLUTE world
    coordinates, e.g. sampled from a hand-authored Curve object) instead of the p0/p1/bend
    parametric model -- shared by `RKA_OT_build_segment_from_curve` and
    `rebuild_segment_from_curve_in_place`."""
    k = ik()
    seg = k.build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id="SEG")

    visual_objs = []
    for side, curb_pts in zip(("L", "R"), seg["curbs"]):
        visual_objs.append(build_curb(
            "curb_%s" % side, curb_pts, coll, curb_style, curb_height, curb_thickness))

    for m in seg["lanes"]:
        tag = "%s%s_L%d" % (m["from"], m["to"], m["lane_in"])
        paths.kc.poly_curve(
            "lanecl_%s" % tag, m["points"], coll, loop=False,
            lane_width=lane_width, oneway=True, end_behavior='CHAIN')
        visual_objs.append(paths.kc.flat_ribbon(
            "ribbon_%s" % tag, m["points"], lane_width / 2.0, coll, matkey="asphalt"))

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return visual_objs


def _sample_curve_world_points(context, curve_obj):
    """Evaluate `curve_obj` (a Curve object, any spline type -- Bezier/NURBS/Poly) through the
    depsgraph (respecting handles/resolution/modifiers) and return its points as a WORLD-SPACE
    list of `(x, y, z)` tuples, in spline order. Uses the standard 'evaluated-object to_mesh()'
    technique (no `bpy.ops`, no temporary scene objects) -- for a plain curve with no bevel/
    extrude this produces the same edge-strip vertex order as Blender's own Convert To Mesh.
    Assumes a single, non-cyclic spline (the expected shape for an authored road path) -- a
    multi-spline or cyclic curve isn't specifically rejected, just not a case this addon models."""
    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = curve_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    mat = curve_obj.matrix_world
    pts = [tuple(mat @ v.co) for v in mesh.vertices]
    eval_obj.to_mesh_clear()
    return pts


def _resolve_curve_object(context, name):
    """The Curve object `RKA_OT_build_segment_from_curve` should follow: by explicit `name` if
    given, else the active object if it's a Curve. None if neither resolves."""
    if name:
        obj = bpy.data.objects.get(name)
        return obj if obj is not None and obj.type == 'CURVE' else None
    obj = context.active_object
    return obj if obj is not None and obj.type == 'CURVE' else None


class RKA_OT_build_segment_from_curve(bpy.types.Operator):
    """Build a road segment whose path follows a hand-authored Blender Curve object EXACTLY (its
    evaluated points, respecting Bezier handles/resolution) instead of the straight+Bend/Vertical
    Bend parametric model -- the "author the path with a real Curve" workflow: draw/edit the
    curve's control points in Edit Mode (add as many as you like, reshape freely, raise/lower
    individual points for a genuine multi-point slope, not just one bump) and re-run this operator
    (or just drag a point -- see `rebuild_segment_from_curve_in_place` / live_edit.py) to
    regenerate the road from it. The curve stays in the scene as the source of truth; this
    operator's output (curb/lane objects) is fully regenerated each run, same as every other build
    operator here.

    Select the curve (or set 'Curve' by name) first -- poll fails otherwise."""
    bl_idname = "rka.build_segment_from_curve"
    bl_label = "Build Segment From Curve"
    bl_options = {'REGISTER', 'UNDO'}

    curve_object: bpy.props.StringProperty(
        name="Curve", description="Name of the Curve object to follow. Leave blank to use the "
        "active object if it's a Curve", default="")
    lane_width: bpy.props.FloatProperty(name="Lane Width", default=5.0, min=0.5, unit='LENGTH')
    lanes: bpy.props.IntProperty(
        name="Lanes Forward", default=1, min=0, max=3,
        description="Lane count in the curve's own direction (start -> end). 0 is only valid if "
                     "Lanes Backward is nonzero")
    lanes_backward: bpy.props.IntProperty(
        name="Lanes Backward", default=1, min=0, max=3,
        description="Lane count against the curve's direction (end -> start). 0 makes this a "
                     "ONE-WAY road")
    curb_style: bpy.props.EnumProperty(name="Curb Style", items=CURB_STYLE_ITEMS, default='BOX')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        return _resolve_curve_object(context, "") is not None

    def execute(self, context):
        if self.lanes == 0 and self.lanes_backward == 0:
            self.report({'ERROR'}, "Lanes Forward and Lanes Backward can't both be 0 -- a road "
                                    "needs at least one lane somewhere")
            return {'CANCELLED'}
        curve_obj = _resolve_curve_object(context, self.curve_object)
        if curve_obj is None:
            self.report({'ERROR'}, "Select a Curve object, or set 'Curve' to one by name")
            return {'CANCELLED'}
        spine = _sample_curve_world_points(context, curve_obj)
        if len(spine) < 2:
            self.report({'ERROR'}, "'%s' evaluates to fewer than 2 points" % curve_obj.name)
            return {'CANCELLED'}

        parent_coll = (parent_collection_of(curve_obj.users_collection[0])
                        if curve_obj.users_collection
                        else context.view_layer.active_layer_collection.collection)
        n = 1
        while ("SegmentCurve_%03d" % n) in bpy.data.collections:
            n += 1
        coll = bpy.data.collections.new("SegmentCurve_%03d" % n)
        parent_coll.children.link(coll)

        visual_objs = _populate_segment_mesh_from_spine(
            context, coll, spine, self.lane_width, self.lanes, self.lanes_backward,
            self.curb_style, self.curb_height, self.curb_thickness, self.join_visual_mesh)

        # A reference back to the driving curve, so live-editing ITS control points can rebuild
        # this segment too (rebuild_segment_from_curve_in_place, watched by live_edit.py).
        driver = bpy.data.objects.new("segcurve_driver", None)
        driver.empty_display_type = 'PLAIN_AXES'
        driver.empty_display_size = 0.5
        driver.location = spine[0]
        driver["rka_curve_driver"] = curve_obj.name
        coll.objects.link(driver)

        custom_props.write_build_settings(
            coll, lane_width=self.lane_width, lanes=self.lanes, lanes_backward=self.lanes_backward,
            curb_style=self.curb_style, curb_height=self.curb_height,
            curb_thickness=self.curb_thickness, curve_object=curve_obj.name)

        export_note = ""
        if self.export_path:
            try:
                ik().export_segment_from_spine_json(
                    bpy.path.abspath(self.export_path), spine, self.lane_width, self.lanes,
                    self.lanes_backward, segment_id=coll.name)
                export_note = ", json -> '%s'" % self.export_path
            except OSError as exc:
                self.report({'WARNING'}, "Built geometry OK, but json export failed: %s" % exc)

        for o in context.selected_objects:
            o.select_set(False)
        self.report({'INFO'}, "Built '%s' from curve '%s': %d point(s)%s" %
                     (coll.name, curve_obj.name, len(spine), export_note))
        return {'FINISHED'}


def rebuild_segment_from_curve_in_place(context, coll):
    """Live-editing counterpart to `RKA_OT_build_segment_from_curve`: re-samples the driving
    curve's CURRENT evaluated points (`segcurve_driver`'s `rka_curve_driver` name) and rebuilds in
    place. Triggered by `live_edit.py` whenever that curve's geometry (editing control points) or
    transform (moving/rotating the whole curve object) changes. A no-op if the driver marker or
    the curve it references is missing/deleted, or the curve currently evaluates to under 2
    points."""
    driver = next((o for o in coll.objects if "rka_curve_driver" in o.keys()), None)
    if driver is None:
        return
    curve_obj = bpy.data.objects.get(driver["rka_curve_driver"])
    if curve_obj is None or curve_obj.type != 'CURVE':
        return
    spine = _sample_curve_world_points(context, curve_obj)
    if len(spine) < 2:
        return

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    curb_style = coll.get("rka_curb_style", 'BOX')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)

    clear_generated_mesh_objects(coll)
    _populate_segment_mesh_from_spine(context, coll, spine, lane_width, lanes, lanes_backward,
                                       curb_style, curb_height, curb_thickness, join_visual_mesh)
    driver.location = spine[0]


CLASSES = (RKA_OT_build_straight_segment, RKA_OT_extend_from_arm, RKA_OT_insert_intersection_on_segment,
           RKA_OT_adjust_segment_lanes, RKA_OT_build_segment_from_curve)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
