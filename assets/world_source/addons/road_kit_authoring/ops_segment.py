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
from .ops_intersection import (CURB_STYLE_ITEMS, PRESET_ITEMS, TRAFFIC_SIDE_ITEMS, RkaBuildError,
                                active_marker_position, build_curb, build_intersection_geometry,
                                clear_generated_mesh_objects, join_meshes, parent_collection_of)

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


def _populate_segment_mesh(context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style,
                            curb_height, curb_thickness, bend, curve_segments, elevation_delta,
                            bend_z, join_visual_mesh, z_base, traffic_side='LEFT'):
    """Build the curb + lane-centerline + ribbon objects for one segment INTO `coll` (already
    created/linked) and return `visual_objs`. Shared by `build_segment_geometry` (fresh build,
    also creates the segend_A/segend_B/segbend marker Empties afterward) and
    `rebuild_segment_in_place` (live-edit rebuild, keeps the existing markers). `lanes_backward` --
    see `intersection_kit.build_segment_from_spine` -- may be 0 for a one-way road; `lanes` and
    `lanes_backward` may not both be 0."""
    k = ik()
    seg = k.build_straight_segment(p0, p1, lane_width, lanes, segment_id="SEG", bend=bend,
                                    segments=curve_segments, z0=0.0, z1=elevation_delta,
                                    bend_z=bend_z, lanes_backward=lanes_backward,
                                    traffic_side=traffic_side)

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
                            gltf_export_path, base_name="Segment", lanes_backward=None,
                            traffic_side='LEFT'):
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
        curb_thickness, bend, curve_segments, elevation_delta, bend_z, join_visual_mesh, z,
        traffic_side)

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
        traffic_side=traffic_side,
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
                lanes_backward=lanes_backward, traffic_side=traffic_side)
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
    traffic_side = coll.get("rka_traffic_side", "LEFT")

    clear_generated_mesh_objects(coll)
    _populate_segment_mesh(context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style,
                            curb_height, curb_thickness, bend, curve_segments, elevation_delta,
                            bend_z, join_visual_mesh, z_base, traffic_side)

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
    """Build one straight (or gently curved/sloped) two-way road segment from the 3D cursor,
    `length` meters along `direction_deg` -- CURVE-BACKED BY DEFAULT: the segment's pavement lives
    on a live, editable spine Curve object (`kit_common.road_spine`, GN_RoadProfile attached
    directly), so extending or reshaping the road afterward is just entering Edit Mode on that
    spine and adding/dragging control points -- no separate "from curve" step needed (see
    `RKA_OT_build_segment_from_curve`, which now just seeds a fresh spine from an externally
    authored curve's sampled points and otherwise shares this exact code path,
    `_build_segment_from_points`). Purely additive: creates a new collection, never touches an
    existing piece. Position the cursor at an existing intersection's port (see its printed port
    positions, or `lib/intersection_kit.py`'s build_ports) to connect them -- LaneGraph does the
    rest at bake time via proximity, no explicit stitching needed here.

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
    curb_l_style: bpy.props.EnumProperty(
        name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='BOX',
        description="BOX = plain flat wall. GUTTER = stepped curb-and-gutter profile. NONE = no "
                     "curb at all on this side (e.g. a rural shoulder or a merge zone)")
    curb_r_style: bpy.props.EnumProperty(
        name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='BOX',
        description="Independent of the left side -- e.g. a curb on the sidewalk side and NONE "
                     "on a shoulder/merge side")
    traffic_side: bpy.props.EnumProperty(
        name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT',
        description="Which physical lateral half of this segment carries Lanes Forward vs. "
                     "Lanes Backward. Must match every intersection/transition it connects to")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="BOX style: wall thickness. GUTTER style: total "
        "curb+gutter width (the real piece this mirrors is 0.6m)",
        default=0.25, min=0.01, unit='LENGTH')
    bend: bpy.props.FloatProperty(
        name="Bend", description="Lateral offset (m) of a control point at the segment's "
        "midpoint -- 0 (default) is dead straight; nonzero gently curves the road via a "
        "quadratic bezier (positive = bends left of travel). Only shapes the INITIAL spine -- "
        "add more control points afterward (Edit Mode on the spine object) for anything beyond "
        "one bump", default=0.0)
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
        description="Combine the spine's pavement + curb wall(s) into a single mesh object "
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
        name="Export .glb", description="Optional: export the built visual geometry (spine "
        "pavement + curb wall(s) -- not the lanecl_* data curves) to a .glb here. Blank = skip",
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

        rka = context.scene.rka
        z = cz_raw + rka.lane_surface_z
        k = ik()
        p0 = (cx, cy)
        rad = math.radians(self.direction_deg)
        p1 = (cx + self.length * math.cos(rad), cy + self.length * math.sin(rad))
        pts = k.segment_spine_3d(p0, p1, self.bend, self.curve_segments, 0.0,
                                  self.elevation_delta, self.bend_z)
        pts = [(x, y, z + zr) for (x, y, zr) in pts]

        result = _build_segment_from_points(
            context, parent_coll, pts, self.lane_width, self.lanes, self.lanes_backward,
            self.curb_l_style, self.curb_r_style, self.curb_height, self.curb_thickness,
            self.join_visual_mesh, self.export_path, self.gltf_export_path,
            traffic_side=self.traffic_side)

        for w in result["warnings"]:
            self.report({'WARNING'}, w)

        if self.auto_advance_cursor:
            end = result["pts"][-1]
            context.scene.cursor.location = (end[0], end[1], end[2] - rka.lane_surface_z)

        for o in context.selected_objects:
            o.select_set(False)
        self.report(
            {'INFO'},
            "Built '%s': %d lane(s) forward, %d backward, %.1fm long, curve-backed%s"
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
    within `LaneGraph`'s proximity tolerance. Curve-backed via `_build_segment_from_points` --
    the exact same GN pipeline `RKA_OT_build_straight_segment` uses, so an extended segment looks
    and behaves identically to one built directly (previously this used the older ribbon-based
    `build_segment_geometry`, which visibly differed from a fresh 'Build Straight Segment').

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
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='BOX')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='BOX')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(
        name="Join Into One Mesh", default=False,
        description="Combine the spine's pavement + curb wall(s) into a single mesh object "
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
        traffic_side = coll.get("rka_traffic_side", "LEFT")
        if arms is None or origin is None:
            self.report({'ERROR'}, "'%s' has no stored arm data -- was it built by 'Build "
                                    "Intersection'?" % coll.name)
            return {'CANCELLED'}
        match = next((a for a in arms if a[0] == arm_name), None)
        if match is None:
            self.report({'ERROR'}, "Arm '%s' not found in '%s' (arms: %s)" %
                         (arm_name, coll.name, ", ".join(a[0] for a in arms)))
            return {'CANCELLED'}
        _, angle_deg, arm_lanes, arm_lanes_out = match

        # If the arm is one-way (RKA_OT_set_arm_oneway), the extended segment matches its
        # direction automatically: an 'IN'-only arm (only ever RECEIVES traffic, i.e. cars travel
        # TOWARD the junction along it) means 0 lanes LEAVING the junction (forward, A->B, since
        # `angle_deg` points outward/away from the junction) and `arm_lanes` lanes arriving
        # (backward, B->A); 'OUT'-only is the mirror. A plain (both-ways) arm stays symmetric --
        # the historical behavior. ASYMMETRIC WIDENING (`RKA_OT_adjust_arm_lanes_out`): the
        # forward (departing/CCW, A->B) count uses `arm_lanes_out` when it's a nonzero override,
        # else falls back to the symmetric `arm_lanes` -- so an extended segment continues an
        # asymmetric arm with the SAME asymmetric lane counts on each side, not silently
        # re-symmetrizing it.
        arm_obj = next((o for o in coll.objects if o.get("rka_arm_name") == arm_name), None)
        arm_oneway = (arm_obj.get("rka_arm_oneway", "") or None) if arm_obj is not None else None
        forward_lanes = arm_lanes_out if arm_lanes_out > 0 else arm_lanes
        lanes_forward = 0 if arm_oneway == 'IN' else forward_lanes
        lanes_backward = 0 if arm_oneway == 'OUT' else arm_lanes

        rad = math.radians(angle_deg)
        ox, oy, oz = origin
        px = ox + tail_length * math.cos(rad)
        py = oy + tail_length * math.sin(rad)

        rka = context.scene.rka
        z = oz + rka.lane_surface_z
        p0 = (px, py)
        p1 = (px + self.length * math.cos(rad), py + self.length * math.sin(rad))
        k = ik()
        pts = k.segment_spine_3d(p0, p1, self.bend, self.curve_segments, 0.0,
                                  self.elevation_delta, self.bend_z)
        pts = [(x, y, z + zr) for (x, y, zr) in pts]

        try:
            result = _build_segment_from_points(
                context, parent_collection_of(coll), pts, lane_width, lanes_forward,
                lanes_backward, self.curb_l_style, self.curb_r_style, self.curb_height,
                self.curb_thickness, self.join_visual_mesh, self.export_path,
                self.gltf_export_path, traffic_side=traffic_side)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for w in result["warnings"]:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Extended '%s' arm '%s' by %.1fm, curve-backed%s" %
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
        traffic_side = coll.get("rka_traffic_side", "LEFT")
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
                self.join_visual_mesh, "", "", traffic_side)
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
            _, angle_deg, arm_lanes, _lanes_out = next(a for a in new_arms if a[0] == arm_name)
            rad = math.radians(angle_deg)
            px = split_x + self.tail_length * math.cos(rad)
            py = split_y + self.tail_length * math.sin(rad)
            r = build_segment_geometry(
                context, parent, (px, py, split_zr), angle_deg, length, lane_width, arm_lanes,
                curb_style, curb_height, curb_thickness, 0.0, 8, 0.0, 0.0,
                self.join_visual_mesh, "", "", traffic_side=traffic_side)
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
        if "rka_lanes_a" in coll.keys():
            self.report({'ERROR'}, "'%s' is a lane-transition piece -- adjust 'Lanes A'/'Lanes B' "
                                    "via its Custom Properties panel instead" % coll.name)
            return {'CANCELLED'}
        key = "rka_lanes_backward" if self.backward else "rka_lanes"
        other_key = "rka_lanes" if self.backward else "rka_lanes_backward"
        new_val = max(0, min(3, int(coll.get(key, 1)) + self.delta))
        other_val = int(coll.get(other_key, 1))
        if new_val == 0 and other_val == 0:
            self.report({'ERROR'}, "Can't set both directions to 0 -- a road needs at least one "
                                    "lane somewhere")
            return {'CANCELLED'}
        coll[key] = new_val
        if "rka_curve_object" in coll.keys():
            # Curve-backed (RKA_OT_build_straight_segment/build_segment_from_curve/extend_from_arm)
            # -- the pavement's own width comes from the spine's per-point Radius, which a plain
            # lane-count change never touches on its own (unlike an intersection arm's curb, whose
            # geometry is re-derived from lanes every rebuild); refresh it here before rebuilding
            # curb/lanecl_*, else the curb/lane data would show the new count while the pavement
            # sweep silently kept the OLD width.
            spine_name = coll.get("rka_curve_object")
            spine_obj = bpy.data.objects.get(spine_name)
            if spine_obj is not None and spine_obj.type == 'CURVE':
                lane_width = coll.get("rka_lane_width", 5.0)
                fwd = coll.get("rka_lanes", 1) if self.backward else new_val
                bwd = new_val if self.backward else coll.get("rka_lanes_backward", 1)
                half_w = max(fwd, bwd) * lane_width
                for pt in spine_obj.data.splines[0].points:
                    pt.radius = max(half_w, 1e-3)
            rebuild_segment_gn_in_place(context, coll)
        else:
            rebuild_segment_in_place(context, coll)
        self.report({'INFO'}, "'%s' %s lanes -> %d" %
                     (coll.name, "backward" if self.backward else "forward", new_val))
        return {'FINISHED'}


def _populate_segment_mesh_gn(context, coll, spine_obj, lane_width, lanes, lanes_backward,
                               curb_l_style, curb_r_style, curb_height, curb_thickness,
                               join_visual_mesh, traffic_side='LEFT'):
    """Curb + lanecl_* objects for a segment whose PAVEMENT already lives on `spine_obj` itself
    (a live `GN_RoadProfile` modifier -- see `kit_common.road_spine`). Curbs are
    `paths.kc.curb_loop(closed=False)` (GN, correctly mitered even on a multi-point bent spine)
    from the SAME tangent-offset points `intersection_kit.build_segment_from_spine` already
    computes for its `curbs` field (radius 0 everywhere -- an open curb line has no corners to
    fillet). `lanecl_*` data curves are unchanged. Independent `curb_l_style`/`curb_r_style`
    (either may be 'NONE'). Returns `visual_objs` INCLUDING `spine_obj` itself, so join/export
    naturally pick up the pavement mesh too. Does NOT touch/recreate `spine_obj` -- its own
    control points are the live-edited source of truth (see `rebuild_segment_gn_in_place`)."""
    k = ik()
    spine = _spine_control_points(spine_obj)
    seg = k.build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id="SEG",
                                      traffic_side=traffic_side)

    visual_objs = [spine_obj]
    left_pts, right_pts = seg["curbs"]
    left = paths.kc.curb_loop(
        "curb_%s_L" % coll.name, [(p[0], p[1], p[2], 0.0) for p in left_pts], coll,
        curb_style=curb_l_style, curb_height=curb_height, curb_thickness=curb_thickness,
        closed=False)
    right = paths.kc.curb_loop(
        "curb_%s_R" % coll.name, [(p[0], p[1], p[2], 0.0) for p in right_pts], coll,
        curb_style=curb_r_style, curb_height=curb_height, curb_thickness=curb_thickness,
        closed=False)
    visual_objs += [o for o in (left, right) if o is not None]

    for m in seg["lanes"]:
        tag = "%s%s_L%d" % (m["from"], m["to"], m["lane_in"])
        paths.kc.poly_curve(
            "lanecl_%s" % tag, m["points"], coll, loop=False,
            lane_width=lane_width, oneway=True, end_behavior='CHAIN')

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs

    return visual_objs


def _build_segment_from_points(context, parent_coll, pts, lane_width, lanes, lanes_backward,
                                curb_l_style, curb_r_style, curb_height, curb_thickness,
                                join_visual_mesh, export_path, gltf_export_path,
                                base_name="Segment", traffic_side='LEFT'):
    """Shared core behind BOTH `RKA_OT_build_straight_segment` (`pts` from p0/p1/bend, via
    `intersection_kit.segment_spine_3d`) and `RKA_OT_build_segment_from_curve` (`pts` sampled ONCE
    from an externally authored curve, to seed this new self-contained spine) -- a NEW collection
    with a live GN-backed spine (`kit_common.road_spine`) through `pts`, plus curb/lanecl_*
    (`_populate_segment_mesh_gn`). One code path for both operators, so they can never drift
    apart. `pts` are already-absolute `(x, y, z)` world points (>= 2). `lanes`/`lanes_backward` --
    see `intersection_kit.build_segment_from_spine` -- may not both be 0."""
    if lanes <= 0 and lanes_backward <= 0:
        raise RkaBuildError("a segment needs at least one lane in SOME direction "
                             "(lanes=%d, lanes_backward=%d)" % (lanes, lanes_backward))
    half_w = max(lanes, lanes_backward) * lane_width

    n = 1
    while base_name + ("_%03d" % n) in bpy.data.collections:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)

    spine_obj = paths.kc.road_spine("spine_%s" % coll.name, pts, coll, half_w, matkey="asphalt")

    visual_objs = _populate_segment_mesh_gn(
        context, coll, spine_obj, lane_width, lanes, lanes_backward, curb_l_style, curb_r_style,
        curb_height, curb_thickness, join_visual_mesh, traffic_side)

    # rka_p0/p1 (first/last point) are an approximation for anything downstream expecting the old
    # 2-point model (e.g. RKA_OT_insert_intersection_on_segment) -- accurate for a straight/gently
    # bent segment, an approximation (ignores intermediate points) for a heavily curved one; that
    # operator's own straight-line splice logic was never curve-aware in the first place.
    custom_props.write_build_settings(
        coll, lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        curb_l_style=curb_l_style, curb_r_style=curb_r_style, curb_height=curb_height,
        curb_thickness=curb_thickness, curve_object=spine_obj.name, traffic_side=traffic_side,
        p0=list(pts[0]), p1=list(pts[-1]))

    warnings = []
    export_note = ""
    if export_path:
        try:
            ik().export_segment_from_spine_json(
                bpy.path.abspath(export_path), pts, lane_width, lanes, lanes_backward,
                segment_id=coll.name, traffic_side=traffic_side)
            export_note += ", json -> '%s'" % export_path
        except OSError as exc:
            warnings.append("Built geometry OK, but json export failed: %s" % exc)
    if gltf_export_path:
        try:
            paths.kc.export_gltf(visual_objs, bpy.path.abspath(gltf_export_path))
            export_note += ", glb -> '%s'" % gltf_export_path
        except Exception as exc:   # noqa: BLE001 -- bpy.ops export can raise a variety of types
            warnings.append("Built geometry OK, but glTF export failed: %s" % exc)

    return {"coll": coll, "pts": pts, "spine_obj": spine_obj, "visual_objs": visual_objs,
            "export_note": export_note, "warnings": warnings}


def _sample_curve_world_points(context, curve_obj):
    """Evaluate `curve_obj` (a Curve object, any spline type -- Bezier/NURBS/Poly) through the
    depsgraph (respecting handles/resolution) and return its points as a WORLD-SPACE list of
    `(x, y, z)` tuples, in spline order. Uses the standard 'evaluated-object to_mesh()' technique
    (no `bpy.ops`, no temporary scene objects) -- for a plain curve with no bevel/extrude/GN
    modifier this produces the same edge-strip vertex order as Blender's own Convert To Mesh.
    Assumes a single, non-cyclic spline (the expected shape for an authored road path) -- a
    multi-spline or cyclic curve isn't specifically rejected, just not a case this addon models.

    ONLY for an EXTERNALLY-authored curve with no mesh-producing modifier of its own (e.g. the
    curve `RKA_OT_build_segment_from_curve` samples ONCE to seed a new spine) -- do NOT call this
    on one of THIS addon's own `spine_*` objects: those carry a live `GN_RoadProfile` modifier, and
    `to_mesh()`'s depsgraph evaluation returns that modifier's SWEPT PAVEMENT MESH (a handful of
    offset quad-strip vertices), not the clean centerline the curb/lane math needs -- use
    `_spine_control_points` for that instead (verified via headless inspection: a 2-point spine
    with the Road modifier attached evaluates to 8 mesh vertices, not 2 points)."""
    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = curve_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    mat = curve_obj.matrix_world
    pts = [tuple(mat @ v.co) for v in mesh.vertices]
    eval_obj.to_mesh_clear()
    return pts


def _spine_control_points(spine_obj):
    """The RAW control points of `spine_obj`'s first spline (world-space `(x, y, z)` tuples, in
    order) -- read directly off the curve data, NO depsgraph/modifier evaluation. This is what
    every rebuild of THIS addon's own `spine_*` objects must use instead of
    `_sample_curve_world_points` (see that function's docstring for why: `to_mesh()` on a
    GN_RoadProfile-modified object returns the swept pavement mesh, not a centerline). Since
    `kit_common.road_spine` always builds a POLY spline (straight between consecutive control
    points, no resolution subdivision), the raw points ARE exactly the live-edited path -- editing
    them in Edit Mode is editing this exact list, so no resampling technique is needed at all."""
    mat = spine_obj.matrix_world
    return [tuple(mat @ pt.co.to_3d()) for pt in spine_obj.data.splines[0].points]


def _resolve_curve_object(context, name):
    """The Curve object `RKA_OT_build_segment_from_curve` should follow: by explicit `name` if
    given, else the active object if it's a Curve. None if neither resolves."""
    if name:
        obj = bpy.data.objects.get(name)
        return obj if obj is not None and obj.type == 'CURVE' else None
    obj = context.active_object
    return obj if obj is not None and obj.type == 'CURVE' else None


class RKA_OT_build_segment_from_curve(bpy.types.Operator):
    """Build a road segment whose INITIAL path follows a hand-authored Blender Curve object
    exactly (its evaluated points, respecting Bezier handles/resolution) -- the "author the path
    with a real Curve first" workflow. This samples that curve ONCE to seed a NEW, self-contained
    spine (`_build_segment_from_points`, the exact same shared core `RKA_OT_build_straight_segment`
    uses) living inside this operator's own generated collection; from then on THAT new spine, not
    the original curve you selected, is the live source of truth -- edit its control points
    (Edit Mode, add as many as you like, reshape freely, raise/lower for a genuine multi-point
    slope) and the road updates live with no rebuild step for the pavement at all (see
    `kit_common.road_spine`). The originally-selected curve is left untouched and no longer
    referenced afterward -- this is a one-time seed, not an ongoing link.

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
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='BOX')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='BOX')
    traffic_side: bpy.props.EnumProperty(name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        return _resolve_curve_object(context, "") is not None

    def execute(self, context):
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

        try:
            result = _build_segment_from_points(
                context, parent_coll, spine, self.lane_width, self.lanes, self.lanes_backward,
                self.curb_l_style, self.curb_r_style, self.curb_height, self.curb_thickness,
                self.join_visual_mesh, self.export_path, "", base_name="SegmentCurve",
                traffic_side=self.traffic_side)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for w in result["warnings"]:
            self.report({'WARNING'}, w)
        for o in context.selected_objects:
            o.select_set(False)
        self.report({'INFO'}, "Built '%s' from curve '%s': %d point(s)%s" %
                     (result["coll"].name, curve_obj.name, len(spine), result["export_note"]))
        return {'FINISHED'}


def rebuild_segment_gn_in_place(context, coll):
    """Live-editing counterpart to `_build_segment_from_points`: finds this segment's own spine
    object (`rka_curve_object`, living INSIDE `coll` -- not an external reference) and re-derives
    curb/lanecl_* from its CURRENT evaluated points. Triggered by `live_edit.py` whenever that
    curve's geometry (editing/adding control points) or transform changes -- the exact same
    `is_updated_geometry` watch that already drove the old external-curve-driver design, now
    pointed at the segment's own self-contained spine instead.

    Deliberately does NOT delete/recreate the spine object itself (unlike every other rebuild in
    this addon) -- its own control points ARE the live-edited state; `GN_RoadProfile` already
    tracks them automatically with zero Python involvement, so touching the spine here would be
    both unnecessary and wasteful. Only curb_*/lanecl_* (genuinely-separate offset objects) are
    cleared and regenerated. A no-op if the spine reference is missing/deleted or currently
    evaluates to under 2 points (e.g. all points briefly deleted mid-edit)."""
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return
    spine_obj = bpy.data.objects.get(spine_name)
    if spine_obj is None or spine_obj.type != 'CURVE':
        return
    spine = _spine_control_points(spine_obj)
    if len(spine) < 2:
        return

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    curb_l_style = coll.get("rka_curb_l_style", coll.get("rka_curb_style", 'BOX'))
    curb_r_style = coll.get("rka_curb_r_style", coll.get("rka_curb_style", 'BOX'))
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)
    traffic_side = coll.get("rka_traffic_side", "LEFT")

    clear_generated_mesh_objects(coll)
    _populate_segment_mesh_gn(context, coll, spine_obj, lane_width, lanes, lanes_backward,
                               curb_l_style, curb_r_style, curb_height, curb_thickness,
                               join_visual_mesh, traffic_side)
    coll["rka_p0"] = list(spine[0])
    coll["rka_p1"] = list(spine[-1])


# Back-compat alias -- live_edit.py and any external caller referencing the pre-GN name.
rebuild_segment_from_curve_in_place = rebuild_segment_gn_in_place


def _populate_transition_visuals(context, coll, spine_obj, seg, lane_width, curb_l_style,
                                  curb_r_style, curb_height, curb_thickness, join_visual_mesh):
    """Curb + lanecl_* objects for a lane-count transition piece, from an already-computed
    `intersection_kit.build_lane_transition` result `seg` -- shared by
    `RKA_OT_build_lane_transition` and `rebuild_lane_transition_in_place` so they can't drift
    apart, same reasoning as every other paired build/rebuild function in this addon."""
    visual_objs = [spine_obj]
    left_pts, right_pts = seg["curbs"]
    left = paths.kc.curb_loop(
        "curb_%s_L" % coll.name, [(p[0], p[1], p[2], 0.0) for p in left_pts], coll,
        curb_style=curb_l_style, curb_height=curb_height, curb_thickness=curb_thickness,
        closed=False)
    right = paths.kc.curb_loop(
        "curb_%s_R" % coll.name, [(p[0], p[1], p[2], 0.0) for p in right_pts], coll,
        curb_style=curb_r_style, curb_height=curb_height, curb_thickness=curb_thickness,
        closed=False)
    visual_objs += [o for o in (left, right) if o is not None]

    for m in seg["lanes"]:
        lane_tag = ("L%d" % m["lane_in"] if m["lane_in"] == m["lane_out"]
                    else "L%dto%d" % (m["lane_in"], m["lane_out"]))
        tag = "%s%s_%s" % (m["from"], m["to"], lane_tag)
        paths.kc.poly_curve("lanecl_%s" % tag, m["points"], coll, loop=False,
                             lane_width=lane_width, oneway=True, end_behavior='CHAIN')

    if join_visual_mesh and visual_objs:
        joined = join_meshes(context, visual_objs, "mesh_%s" % coll.name)
        visual_objs = [joined] if joined else visual_objs
    return visual_objs


class RKA_OT_build_lane_transition(bpy.types.Operator):
    """Build a lane-COUNT transition (a merge/drop, or the reverse -- a split/add) between p0
    (`Lanes A` forward/backward) and p1 (`Lanes B`) -- the piece connecting a wide road to a
    narrower one (or a narrow one to a wider intersection arm), e.g. a 2-lane street narrowing
    into a 1-lane side street. Straight only (no bend) for now -- see
    `intersection_kit.build_lane_transition`'s docstring for how a curved/sloped transition could
    reuse the same per-lane-pair offset math against a custom spine later.

    The pavement is a single `GN_RoadProfile` sweep with a LINEARLY TAPERING per-point Radius
    (`kit_common.road_spine` already supports a per-point radius list -- no new GN work needed for
    the taper itself); curbs are `curb_loop(closed=False)` from the SAME tangent-offset points
    `build_lane_transition` computes, so they narrow/widen exactly in step with the pavement.
    `Align` -- 'right' (default, a real lane-drop: the curb-side lane(s) continue straight, excess
    inner lane(s) taper into them) or 'left' (mirror)."""
    bl_idname = "rka.build_lane_transition"
    bl_label = "Build Lane Transition"
    bl_options = {'REGISTER', 'UNDO'}

    direction_deg: bpy.props.FloatProperty(
        name="Direction", description="Degrees from world +X the transition runs, starting at "
        "the 3D cursor", default=0.0, min=-360.0, max=360.0)
    length: bpy.props.FloatProperty(name="Length", default=20.0, min=1.0, unit='LENGTH')
    lane_width: bpy.props.FloatProperty(name="Lane Width", default=5.0, min=0.5, unit='LENGTH')
    lanes_a: bpy.props.IntProperty(name="Lanes Forward (Start)", default=2, min=1, max=3)
    lanes_b: bpy.props.IntProperty(name="Lanes Forward (End)", default=1, min=1, max=3)
    lanes_backward_a: bpy.props.IntProperty(
        name="Lanes Backward (Start)", default=0, min=0, max=3,
        description="0 = symmetric with Lanes Forward (Start)")
    lanes_backward_b: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=0, min=0, max=3,
        description="0 = symmetric with Lanes Forward (End)")
    align: bpy.props.EnumProperty(
        name="Align", items=(
            ('right', "Right (curb-side continues)", "The outer/curb-side lane(s) run straight "
             "through; the inner lane(s) taper into them -- a real lane-drop"),
            ('left', "Left (median-side continues)", "Mirror of Right -- inner lane(s) stay put, "
             "outer lane(s) taper inward"),
        ), default='right')
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='BOX')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='BOX')
    traffic_side: bpy.props.EnumProperty(name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')

    def execute(self, context):
        marker = active_marker_position(context)
        if marker is not None:
            (cx, cy), cz_raw, parent_coll = marker
        else:
            cursor = context.scene.cursor.location
            cx, cy, cz_raw = cursor.x, cursor.y, cursor.z
            parent_coll = context.view_layer.active_layer_collection.collection

        rka = context.scene.rka
        z = cz_raw + rka.lane_surface_z
        rad = math.radians(self.direction_deg)
        p0 = (cx, cy, z)
        p1 = (cx + self.length * math.cos(rad), cy + self.length * math.sin(rad), z)
        lanes_backward_a = self.lanes_backward_a or None
        lanes_backward_b = self.lanes_backward_b or None

        k = ik()
        try:
            seg = k.build_lane_transition(p0, p1, self.lane_width, self.lanes_a, self.lanes_b,
                                           lanes_backward_a, lanes_backward_b, self.align,
                                           segment_id="TR", traffic_side=self.traffic_side)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        n = 1
        while ("Transition_%03d" % n) in bpy.data.collections:
            n += 1
        coll = bpy.data.collections.new("Transition_%03d" % n)
        parent_coll.children.link(coll)

        half_w_a = max(self.lanes_a, lanes_backward_a or self.lanes_a) * self.lane_width
        half_w_b = max(self.lanes_b, lanes_backward_b or self.lanes_b) * self.lane_width
        spine_obj = paths.kc.road_spine("spine_%s" % coll.name, [p0, p1], coll,
                                         [half_w_a, half_w_b], matkey="asphalt")

        visual_objs = _populate_transition_visuals(
            context, coll, spine_obj, seg, self.lane_width, self.curb_l_style, self.curb_r_style,
            self.curb_height, self.curb_thickness, self.join_visual_mesh)

        custom_props.write_build_settings(
            coll, lane_width=self.lane_width, lanes_a=self.lanes_a, lanes_b=self.lanes_b,
            lanes_backward_a=self.lanes_backward_a, lanes_backward_b=self.lanes_backward_b,
            align=self.align, curb_l_style=self.curb_l_style, curb_r_style=self.curb_r_style,
            traffic_side=self.traffic_side,
            curb_height=self.curb_height, curb_thickness=self.curb_thickness,
            curve_object=spine_obj.name, p0=list(p0), p1=list(p1))

        export_note = ""
        if self.export_path:
            try:
                ik().export_lane_transition_json(
                    bpy.path.abspath(self.export_path), p0, p1, self.lane_width, self.lanes_a,
                    self.lanes_b, lanes_backward_a, lanes_backward_b, self.align,
                    segment_id=coll.name, traffic_side=self.traffic_side)
                export_note = ", json -> '%s'" % self.export_path
            except OSError as exc:
                self.report({'WARNING'}, "Built geometry OK, but json export failed: %s" % exc)

        for o in context.selected_objects:
            o.select_set(False)
        self.report({'INFO'}, "Built '%s': %d->%d lanes forward over %.1fm (align=%s)%s" %
                     (coll.name, self.lanes_a, self.lanes_b, self.length, self.align, export_note))
        return {'FINISHED'}


def rebuild_lane_transition_in_place(context, coll):
    """Live-editing counterpart to `RKA_OT_build_lane_transition`: re-derives p0/p1 from the
    piece's own spine object's CURRENT first/last evaluated points, re-applies the (stored, not
    user-draggable) per-end taper radii, and rebuilds curb/lanecl_* in place -- same 'don't
    delete/recreate the spine itself' rule as `rebuild_segment_gn_in_place`, except this piece
    uses `build_lane_transition`'s tapering lane math instead of the plain
    `build_segment_from_spine` (a transition's two ends have DIFFERENT lane counts by definition).
    Routed here instead of `rebuild_segment_gn_in_place` by `live_edit.py` checking for
    `rka_lanes_a` (a transition-only collection key -- plain segments use singular `rka_lanes`).
    A no-op if the spine reference is missing/deleted or evaluates to under 2 points."""
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return
    spine_obj = bpy.data.objects.get(spine_name)
    if spine_obj is None or spine_obj.type != 'CURVE':
        return
    spine = _spine_control_points(spine_obj)
    if len(spine) < 2:
        return
    p0, p1 = spine[0], spine[-1]

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes_a = coll.get("rka_lanes_a", 2)
    lanes_b = coll.get("rka_lanes_b", 1)
    lanes_backward_a = coll.get("rka_lanes_backward_a", 0) or None
    lanes_backward_b = coll.get("rka_lanes_backward_b", 0) or None
    align = coll.get("rka_align", 'right')
    curb_l_style = coll.get("rka_curb_l_style", 'BOX')
    curb_r_style = coll.get("rka_curb_r_style", 'BOX')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)
    traffic_side = coll.get("rka_traffic_side", "LEFT")

    k = ik()
    try:
        seg = k.build_lane_transition(p0, p1, lane_width, lanes_a, lanes_b, lanes_backward_a,
                                       lanes_backward_b, align, segment_id="TR",
                                       traffic_side=traffic_side)
    except ValueError:
        return

    half_w_a = max(lanes_a, lanes_backward_a or lanes_a) * lane_width
    half_w_b = max(lanes_b, lanes_backward_b or lanes_b) * lane_width
    sp = spine_obj.data.splines[0]
    for i, w in enumerate((half_w_a, half_w_b)):
        if i < len(sp.points):
            sp.points[i].radius = max(w, 1e-3)

    clear_generated_mesh_objects(coll)
    _populate_transition_visuals(context, coll, spine_obj, seg, lane_width, curb_l_style,
                                  curb_r_style, curb_height, curb_thickness, join_visual_mesh)
    coll["rka_p0"] = list(p0)
    coll["rka_p1"] = list(p1)


CLASSES = (RKA_OT_build_straight_segment, RKA_OT_extend_from_arm, RKA_OT_insert_intersection_on_segment,
           RKA_OT_adjust_segment_lanes, RKA_OT_build_segment_from_curve, RKA_OT_build_lane_transition)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
