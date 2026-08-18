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

from . import custom_props, live_edit, paths, spine_io
from .ops_intersection import (CURB_STYLE_ITEMS, MEDIAN_STYLE_ITEMS, PRESET_ITEMS,
                                TRAFFIC_SIDE_ITEMS, RkaBuildError,
                                active_marker_position, arm_or_port_anchor, build_curb,
                                build_intersection_geometry, clear_generated_mesh_objects,
                                join_meshes, local_collection, local_object,
                                parent_collection_of, _resolve_curb_asset,
                                _live_edit_target_collection, get_or_create_origin_marker,
                                sweep_untouched_boundaries, linked_asset_picker_items,
                                _asset_picker_value, _rebuild_piece_in_place)

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


_lp = None


def lp():
    """Lazy `lib/lane_profile` import -- same deferred-import idiom as `ik()`."""
    global _lp
    if _lp is None:
        import lane_profile as _mod
        _lp = _mod
    return _lp


def _stamp_link(new_coll, target_marker):
    """Mark `new_coll`'s own origin marker as LINKED TO `target_marker` (an arm/port Empty on a
    DIFFERENT, already-existing piece) -- see `live_edit.RKA_LINKED_TO_KEY`'s own docstring for
    the full convention. `live_edit.py`'s propagation pass reads this: when `target_marker` moves,
    `new_coll`'s own marker (and therefore this piece) is repositioned and rebuilt to match,
    automatically -- the fix for "adjusting one piece doesn't move whatever was built off it."
    No-op if `new_coll` has no origin marker (shouldn't happen for a piece this function's own
    callers just built) or `target_marker` is None (nothing to link to, e.g. building at the bare
    3D cursor)."""
    if target_marker is None:
        return
    marker = get_or_create_origin_marker(new_coll, custom_props.read_origin(new_coll))
    if marker is not None:
        marker[live_edit.RKA_LINKED_TO_KEY] = target_marker.name


# 2026-08, user-requested: "for the sidewalk, is it possible to default to 3.5 meters/4 meters by
# default instead of adding" -- a real-world city sidewalk width (ADA/typical urban minimum is
# ~1.5m, but 3.5m reads as a genuine pedestrian zone, not a token strip), used as the PANEL's
# first-click jump target (see _draw_sidewalk_and_props) rather than an operator-property default
# -- the build-time `sidewalk_l_width`/`sidewalk_r_width` properties stay at their existing 0.0
# default (every other optional-geometry field in this addon follows the same "0 = off, byte-
# identical to before it existed" convention; changing THAT default would silently add a sidewalk
# to every future build with no opt-in).
DEFAULT_SIDEWALK_WIDTH = 3.5


def _curb_outer_clearance(curb_style, curb_thickness, asset_obj=None):
    """Thin wrapper over `kit_common.curb_outer_clearance` (moved there 2026-08 so
    `ops_intersection.py`'s own sidewalk code can share the exact same rule without a circular
    import -- see that function's own docstring for the full rationale)."""
    return paths.kc.curb_outer_clearance(curb_style, curb_thickness, asset_obj)


def _sidewalk_offset_width(width, width_end, asset_obj):
    """The width value fed into `build_segment_from_spine`'s sidewalk OFFSET-LINE formula (its
    centerline sits at `half_w + curb_clearance + width/2`) -- the configured design width
    (`sidewalk_*_width[_end]`) when this side has no ASSET piece (a procedural `curb_loop` sweep's
    thickness genuinely equals that value), or the resolved piece's own REAL measured width
    (`kit_common.asset_row_width`) when one is set, since a kit tile's physical footprint is fixed
    by the mesh, not by the dial -- see that function's docstring for the gap this fixes. `0`/`off`
    and an explicit taper-to-`0` end are both preserved as-is (never substituted), so a sidewalk
    that's genuinely turned off, or genuinely narrows to nothing along the piece, stays that way;
    only a POSITIVE configured width is replaced by the asset's real one. `width_end=None` ("same
    as start", `build_segment_from_spine`'s own default) is passed through unchanged -- it then
    naturally resolves to the same overridden start value."""
    if asset_obj is None:
        return width, width_end
    real = paths.kc.asset_row_width(asset_obj)
    eff_start = real if width > 0.0 else width
    if width_end is None:
        return eff_start, None
    eff_end = real if width_end > 0.0 else width_end
    return eff_start, eff_end


def _taper_end(value):
    """The `-1`/`-1.0` sentinel every `*_end` taper property (`lanes_end`, `median_width_end`,
    `sidewalk_*_width_end`, ...) uses for "same as start" -> `None`, the shape
    `_build_segment_from_points`/`intersection_kit.build_segment_from_spine` expect for that same
    meaning. A plain `< 0` check works for both `IntProperty`/`FloatProperty` fields since neither
    allows any other negative value (lane counts: 0-4 real range; widths: 0.0+ real range) --
    `-1` is unambiguously the sentinel, never a real taper target."""
    return None if value < 0 else value


STREETLIGHT_EXCLUSION_ZONE = 2.0   # m, minimum clearance a segment's own prop/streetlight row
                                    # keeps from any intersection traffic-light pole/gantry --
                                    # 2026-08, user-requested "Intersection Exclusion Zone" rule
                                    # ("Maintain a minimum buffer offset of 2.0m from any P1/P2
                                    # pole... to avoid asset clipping").


def _nearby_signal_pole_positions():
    """World-space anchor positions of every `trafficlight_*`/`trafficgantry_*` instancer's own
    point cloud currently in the file -- used to keep a segment's own streetlight row clear of a
    nearby intersection's signal poles/gantries (`STREETLIGHT_EXCLUSION_ZONE`, see
    `curb_asset_row`'s own `exclude_positions` docstring). Scans by NAME PREFIX rather than via
    any specific intersection's own collection, since a segment doesn't know in advance which
    intersection (if any) it ends up near -- cheap for this addon's realistic file sizes (an
    authoring file, not a runtime scene with thousands of objects)."""
    out = []
    for obj in bpy.data.objects:
        if obj.library is not None or obj.type != 'MESH':
            continue
        if not (obj.name.startswith("trafficlight_") or obj.name.startswith("trafficgantry_")):
            continue
        out += [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]
    return out


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
    curb_pts3 = []
    for side, curb_pts in zip(("L", "R"), seg["curbs"]):
        pts3 = [to3(p) for p in curb_pts]
        curb_pts3.append(pts3)
        visual_objs.append(build_curb(
            "curb_%s" % side, pts3, coll, curb_style, curb_height, curb_thickness))

    # Pavement collision -- same fix/rationale as _populate_segment_mesh_gn (this legacy
    # point-segment path never even had curb-edge collision, only a visual ribbon -- see
    # kit_common.colonly_swept_between). Not added to visual_objs (collision proxies never are).
    paths.kc.colonly_swept_between("pave_%s" % coll.name, curb_pts3[0], curb_pts3[1], coll)

    for m in seg["lanes"]:
        pts3 = [to3(p) for p in m["points"]]
        tag = "%s%s_L%d" % (m["from"], m["to"], m["lane_in"])
        # `lanecl_*` no longer built here (2026-08) -- export-redundant, no visual mesh of its
        # own -- see ops_intersection.py's matching removal for the full rationale. `ribbon_*`
        # (the actual visible pavement in this legacy path) is unaffected.
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
    # local_collection (not a bare name-in-bpy.data.collections test) so a linked neighbor's
    # same-numbered piece never perturbs local auto-numbering -- see its docstring.
    while local_collection(base_name + ("_%03d" % n)) is not None:
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


@live_edit.rebuilding()
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

    clear_generated_mesh_objects(coll, keep_gn_boundaries=True)
    _populate_segment_mesh(context, coll, p0, p1, lane_width, lanes, lanes_backward, curb_style,
                            curb_height, curb_thickness, bend, curve_segments, elevation_delta,
                            bend_z, join_visual_mesh, z_base, traffic_side)
    sweep_untouched_boundaries(coll)   # delete anything provisionally spared above but never
                                        # reconfirmed this pass (fewer lanes/curb-style-off/etc.)

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
        name="Lanes Forward", default=1, min=0, max=4,
        description="Lane count in the A->B direction. 0 is only valid if Lanes Backward is "
                     "nonzero -- a road needs at least one lane SOMEWHERE")
    lanes_backward: bpy.props.IntProperty(
        name="Lanes Backward", default=1, min=0, max=4,
        description="Lane count in the B->A direction. 0 makes this a ONE-WAY road (e.g. "
                     "Lanes Forward=1, Lanes Backward=0 = a one-way single-lane road)")
    lanes_end: bpy.props.IntProperty(
        name="Lanes Forward (End)", default=-1, min=-1, max=4,
        description="Lane count in the A->B direction at the FAR end -- -1 (default) = same as "
                     "Lanes Forward, a plain constant-width segment. Any other value makes this a "
                     "lane-count TAPER (was the separate 'Build Lane Transition' tool -- now just "
                     "this field left non-default)")
    lanes_backward_end: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=-1, min=-1, max=4,
        description="-1 (default) = same as Lanes Backward (no taper on this direction)")
    align: bpy.props.EnumProperty(
        name="Taper Align", items=(
            ('right', "Right (curb-side continues)", "The outer/curb-side lane(s) run straight "
             "through; the inner lane(s) taper into them -- a real lane-drop"),
            ('left', "Left (median-side continues)", "Mirror of Right -- inner lane(s) stay put, "
             "outer lane(s) taper inward"),
        ), default='right',
        description="Only matters when Lanes Forward/Backward (End) differ from their start value")
    curb_l_style: bpy.props.EnumProperty(
        name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='NONE',
        description="PROFILE = the resolved kit piece's own real cross-section, swept "
                     "continuously (set 'Curb Asset Piece' below). NONE = no curb at all on this "
                     "side (e.g. a rural shoulder or a merge zone)")
    curb_r_style: bpy.props.EnumProperty(
        name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='NONE',
        description="Independent of the left side -- e.g. a curb on the sidewalk side and NONE "
                     "on a shoulder/merge side")
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Name of a linked kit/curb_kit.blend collection whose "
        "mesh object's own cross-section is swept, when a Curb Style above is 'Profile'. Use "
        "'Link Curb Kit Library' first", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", description="Distance between repeated instances -- should "
        "equal the chosen piece's own local X length (see its 'rka_curb_asset_length' custom "
        "property) for seamless tiling", default=2.0, min=0.1, unit='LENGTH')
    curb_asset_rot_offset_r: bpy.props.FloatProperty(
        name="Curb Asset R-Side Rotation Offset", default=180.0,
        description="Extra Z rotation (deg) for the right-side asset row -- 180 keeps an "
                     "asymmetric piece's front face pointing away from the road on both sides")
    traffic_side: bpy.props.EnumProperty(
        name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT',
        description="Which physical lateral half of this segment carries Lanes Forward vs. "
                     "Lanes Backward. Must match every intersection/transition it connects to")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(
        name="Curb Thickness", description="Ignored by Profile style -- the resolved piece's own "
        "cross-section sets its own width. Kept for legacy raw curb_loop() calls",
        default=0.25, min=0.01, unit='LENGTH')
    median_width: bpy.props.FloatProperty(
        name="Median Width", description="Extra gap (m) inserted between Lanes Forward and Lanes "
        "Backward, e.g. for a raised/barriered median -- 0 (default) is no median, byte-identical "
        "to before this existed. Only applies to a genuine two-way segment (both Lanes Forward "
        "and Lanes Backward > 0)", default=0.0, min=0.0, unit='LENGTH')
    median_style: bpy.props.EnumProperty(
        name="Median Style", items=MEDIAN_STYLE_ITEMS, default='NONE',
        description="NONE = no median mesh, just the gap distance. ASSET repeats ONE kit piece "
                     "along the median's own centerline (set 'Median Asset Piece' below). Ignored "
                     "when Median Width is 0")
    median_asset_collection: bpy.props.StringProperty(
        name="Median Asset Piece", description="Linked collection's mesh object to repeat along "
        "the median, when Median Style is 'Asset' or 'Asset (single, centerline)' -- a barrier/"
        "divider mesh, independent of the curb's own asset choice. Left blank, either Asset style "
        "silently builds NO median geometry at all (try 'Kit_Median_YellowSeparator' or "
        "'Kit_Median_Island' after linking the curb kit library)", default="")
    median_asset_spacing: bpy.props.FloatProperty(
        name="Median Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    median_width_end: bpy.props.FloatProperty(
        name="Median Width (End)", default=-1.0, min=-1.0, unit='LENGTH',
        description="-1 (default) = same as Median Width (no median-width taper). Lane count "
                     "stays whatever Lanes Forward/Backward (End) say -- taper JUST the "
                     "separation width by leaving those at -1 while setting this")
    sidewalk_l_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Left)", default=0.0, min=0.0, unit='LENGTH',
        description="A raised paved strip beyond the left curb -- 0 (default) is no sidewalk, "
                     "byte-identical to before this existed. Independent of the right side")
    sidewalk_r_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Right)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_l_width_end: bpy.props.FloatProperty(
        name="Sidewalk Width (Left, End)", default=-1.0, min=-1.0, unit='LENGTH',
        description="-1 (default) = same as Sidewalk Width (Left)")
    sidewalk_r_width_end: bpy.props.FloatProperty(
        name="Sidewalk Width (Right, End)", default=-1.0, min=-1.0, unit='LENGTH',
        description="-1 (default) = same as Sidewalk Width (Right)")
    sidewalk_height: bpy.props.FloatProperty(
        name="Sidewalk Height", default=0.15, min=0.01, unit='LENGTH',
        description="Ignored on a side whose Sidewalk Width is 0")
    sidewalk_l_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Left)", description="Name of a linked collection's mesh object to "
        "tile along the left sidewalk instead of a procedural sweep -- e.g. "
        "'Kit_Curb_SidewalkTile_L2'. Blank (default) = procedural BOX sweep", default="")
    sidewalk_r_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Right)", default="")
    sidewalk_asset_spacing: bpy.props.FloatProperty(
        name="Sidewalk Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    prop_l_asset_collection: bpy.props.StringProperty(
        name="Prop Asset (Left)", description="Name of a linked collection's mesh object to "
        "repeat along the left sidewalk (or, with no sidewalk, the left curb) -- e.g. a street "
        "lamp. Blank (default) = no props on this side", default="")
    prop_l_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Left)", default=30.0, min=0.5, unit='LENGTH')
    prop_r_asset_collection: bpy.props.StringProperty(
        name="Prop Asset (Right)", default="")
    prop_r_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Right)", default=30.0, min=0.5, unit='LENGTH')
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
    auto_lane_markings: bpy.props.BoolProperty(
        name="Auto Lane Markings", default=True,
        description="Generate dashed white internal-lane boundaries and a solid yellow "
                     "forward/backward boundary automatically (see Marking Dash/Gap Length in "
                     "the panel, and 'Add Marking Gap' to clear a stretch afterward)")
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

    def invoke(self, context, event):
        self.traffic_side = context.scene.rka.default_traffic_side
        return self.execute(context)

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
            traffic_side=self.traffic_side, curb_asset_collection=self.curb_asset_collection,
            curb_asset_spacing=self.curb_asset_spacing,
            curb_asset_rot_offset_r=self.curb_asset_rot_offset_r,
            auto_lane_markings=self.auto_lane_markings,
            median_width=self.median_width, median_style=self.median_style,
            median_asset_collection=self.median_asset_collection,
            median_asset_spacing=self.median_asset_spacing,
            sidewalk_l_width=self.sidewalk_l_width, sidewalk_r_width=self.sidewalk_r_width,
            sidewalk_height=self.sidewalk_height,
            sidewalk_l_asset_collection=self.sidewalk_l_asset_collection,
            sidewalk_r_asset_collection=self.sidewalk_r_asset_collection,
            sidewalk_asset_spacing=self.sidewalk_asset_spacing,
            prop_l_asset_collection=self.prop_l_asset_collection,
            prop_l_spacing=self.prop_l_spacing,
            prop_r_asset_collection=self.prop_r_asset_collection,
            prop_r_spacing=self.prop_r_spacing,
            lanes_end=_taper_end(self.lanes_end), lanes_backward_end=_taper_end(self.lanes_backward_end),
            align=self.align, median_width_end=_taper_end(self.median_width_end),
            sidewalk_l_width_end=_taper_end(self.sidewalk_l_width_end),
            sidewalk_r_width_end=_taper_end(self.sidewalk_r_width_end))

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
    lanes_end: bpy.props.IntProperty(
        name="Lanes Forward (End)", default=-1, min=-1, max=4,
        description="-1 (default) = same as the arm's own lane count (no taper). Any other value "
                     "tapers this extension into a lane-count transition -- the 'Build Transition "
                     "Here' workflow, now just this field on the same operator")
    lanes_backward_end: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=-1, min=-1, max=4)
    align: bpy.props.EnumProperty(
        name="Taper Align", items=(
            ('right', "Right (curb-side continues)", ""), ('left', "Left (median-side continues)", ""),
        ), default='right')
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Linked kit/curb_kit.blend collection's mesh "
        "object, when a Curb Style above is 'Asset'", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    curb_asset_rot_offset_r: bpy.props.FloatProperty(
        name="Curb Asset R-Side Rotation Offset", default=180.0,
        description="Extra Z rotation (deg) for the right-side asset row -- 180 keeps an "
                     "asymmetric piece's front face pointing away from the road on both sides")
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    median_width: bpy.props.FloatProperty(
        name="Median Width", default=0.0, min=0.0, unit='LENGTH',
        description="Extra gap (m) between forward/backward lanes -- see 'Build Straight "
                     "Segment's own Median Width tooltip")
    median_width_end: bpy.props.FloatProperty(
        name="Median Width (End)", default=-1.0, min=-1.0, unit='LENGTH',
        description="-1 (default) = same as Median Width (no median-width taper) -- see 'Build "
                     "Straight Segment's own Median Width (End) tooltip. 2026-08: a segment's "
                     "median also tapers automatically at a LINKED joint (e.g. to 0 at an arm, "
                     "which has no median) -- this field is for authoring an intentional taper "
                     "along the piece's own length up front instead")
    median_style: bpy.props.EnumProperty(
        name="Median Style", items=MEDIAN_STYLE_ITEMS, default='NONE',
        description="Ignored when Median Width is 0")
    median_asset_collection: bpy.props.StringProperty(name="Median Asset Piece", default="")
    median_asset_spacing: bpy.props.FloatProperty(
        name="Median Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    sidewalk_l_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Left)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_r_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Right)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_height: bpy.props.FloatProperty(
        name="Sidewalk Height", default=0.15, min=0.01, unit='LENGTH')
    sidewalk_l_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Left)", default="")
    sidewalk_r_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Right)", default="")
    sidewalk_asset_spacing: bpy.props.FloatProperty(
        name="Sidewalk Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    prop_l_asset_collection: bpy.props.StringProperty(name="Prop Asset (Left)", default="")
    prop_l_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Left)", default=30.0, min=0.5, unit='LENGTH')
    prop_r_asset_collection: bpy.props.StringProperty(name="Prop Asset (Right)", default="")
    prop_r_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Right)", default=30.0, min=0.5, unit='LENGTH')
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
        marker = get_or_create_origin_marker(coll, custom_props.read_origin(coll))
        lane_width = coll.get("rka_lane_width", 5.0)
        traffic_side = coll.get("rka_traffic_side", "LEFT")
        if arms is None or marker is None:
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
        # 2026-08 fix (user-reported regression: "extend from arm... no longer create from exact
        # port/arm location with align tangent"): this used to re-DERIVE the start point from
        # `origin + tail_length * direction(angle_deg)` -- exactly right while every arm was
        # forced onto that ray every rebuild, but WRONG the moment an arm can be `rka_arm_
        # tail_pos_locked` (`RKA_OT_aim_arm_at`, matched exactly onto an external target's
        # position, which generally does NOT sit on that ray -- see `intersection_kit.
        # Arm.tail_pos`): the formula would then start the new segment at the arm's OLD
        # ray-projected point, not its real matched position, silently reopening the exact gap
        # the match just closed. The arm Empty's own `.location` IS this arm's real current tail
        # position either way (kept in sync by `rebuild_intersection_in_place` for an ordinary
        # arm, or itself the authoritative match for a locked one) -- read it directly instead of
        # re-deriving it, byte-identical for the ordinary/unlocked case.
        if arm_obj is not None:
            p0 = (arm_obj.location.x, arm_obj.location.y)
            z = arm_obj.location.z
        else:
            # arm_obj not found (shouldn't normally happen -- arm_name was already matched
            # against the collection's own cached arm list above) -- fall back to the old
            # ray-derived formula with the collection's shared tail_length, the only info left.
            tail_length = coll.get("rka_tail_length", 12.0)
            ox, oy, oz = marker.location.x, marker.location.y, marker.location.z
            p0 = (ox + tail_length * math.cos(rad), oy + tail_length * math.sin(rad))
            rka = context.scene.rka
            z = oz + rka.lane_surface_z
        p1 = (p0[0] + self.length * math.cos(rad), p0[1] + self.length * math.sin(rad))
        k = ik()
        pts = k.segment_spine_3d(p0, p1, self.bend, self.curve_segments, 0.0,
                                  self.elevation_delta, self.bend_z)
        pts = [(x, y, z + zr) for (x, y, zr) in pts]

        try:
            result = _build_segment_from_points(
                context, parent_collection_of(coll), pts, lane_width, lanes_forward,
                lanes_backward, self.curb_l_style, self.curb_r_style, self.curb_height,
                self.curb_thickness, self.join_visual_mesh, self.export_path,
                self.gltf_export_path, traffic_side=traffic_side,
                curb_asset_collection=self.curb_asset_collection,
                curb_asset_spacing=self.curb_asset_spacing,
                curb_asset_rot_offset_r=self.curb_asset_rot_offset_r,
                median_width=self.median_width, median_style=self.median_style,
                median_asset_collection=self.median_asset_collection,
                median_asset_spacing=self.median_asset_spacing,
                sidewalk_l_width=self.sidewalk_l_width, sidewalk_r_width=self.sidewalk_r_width,
                sidewalk_height=self.sidewalk_height,
                sidewalk_l_asset_collection=self.sidewalk_l_asset_collection,
                sidewalk_r_asset_collection=self.sidewalk_r_asset_collection,
                sidewalk_asset_spacing=self.sidewalk_asset_spacing,
                prop_l_asset_collection=self.prop_l_asset_collection,
                prop_l_spacing=self.prop_l_spacing,
                prop_r_asset_collection=self.prop_r_asset_collection,
                prop_r_spacing=self.prop_r_spacing,
                lanes_end=_taper_end(self.lanes_end),
                lanes_backward_end=_taper_end(self.lanes_backward_end), align=self.align,
                median_width_end=_taper_end(self.median_width_end))
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _stamp_link(result["coll"], arm_obj)

        for w in result["warnings"]:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Extended '%s' arm '%s' by %.1fm, curve-backed%s" %
                     (coll.name, arm_name, self.length, result["export_note"]))
        return {'FINISHED'}


class RKA_OT_extend_from_port(bpy.types.Operator):
    """Extend a new straight segment outward from an existing plain segment's `port_A`/`port_B`
    end marker (see `ops_segment._place_segment_ports`), continuing with the SAME lane width/
    lane counts/curb styles/traffic side/curb asset settings the source segment was built with --
    the segment counterpart of `RKA_OT_extend_from_arm`, for the common "keep building the road
    from where I left off" workflow without retyping every setting.

    Click a `port_A`/`port_B` marker Empty (the small arrow at each end of a plain GN segment)
    first -- poll fails otherwise."""
    bl_idname = "rka.extend_from_port"
    bl_label = "Extend From Port"
    bl_options = {'REGISTER', 'UNDO'}

    length: bpy.props.FloatProperty(name="Length", default=40.0, min=1.0, unit='LENGTH')
    bend: bpy.props.FloatProperty(name="Bend", default=0.0)
    curve_segments: bpy.props.IntProperty(name="Curve Segments", default=8, min=2, max=32)
    elevation_delta: bpy.props.FloatProperty(
        name="Elevation Delta", default=0.0, unit='LENGTH',
        description="Constant grade/slope from the port to this segment's far end")
    bend_z: bpy.props.FloatProperty(
        name="Vertical Bend", default=0.0, unit='LENGTH',
        description="Crest/dip bump (m) at the segment's midpoint")
    lanes_end: bpy.props.IntProperty(
        name="Lanes Forward (End)", default=-1, min=-1, max=4,
        description="-1 (default) = same as the source segment's own lane count (no taper). Any "
                     "other value tapers this extension into a lane-count transition")
    lanes_backward_end: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=-1, min=-1, max=4)
    align: bpy.props.EnumProperty(
        name="Taper Align", items=(
            ('right', "Right (curb-side continues)", ""), ('left', "Left (median-side continues)", ""),
        ), default='right')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')
    gltf_export_path: bpy.props.StringProperty(
        name="Export .glb", default="", subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and "rka_port" in obj.keys() and obj.users_collection

    def execute(self, context):
        port_obj = context.active_object
        if port_obj is None or "rka_port" not in port_obj.keys() or not port_obj.users_collection:
            self.report({'ERROR'}, "Select a 'port_A'/'port_B' marker Empty first")
            return {'CANCELLED'}
        coll = port_obj.users_collection[0]
        if "rka_curve_object" not in coll.keys() or "rka_lanes_a" in coll.keys():
            self.report({'ERROR'}, "'%s' is not a plain GN segment" % coll.name)
            return {'CANCELLED'}

        lane_width = coll.get("rka_lane_width", 5.0)
        lanes = coll.get("rka_lanes", 1)
        lanes_backward = coll.get("rka_lanes_backward", lanes)
        curb_l_style = coll.get("rka_curb_l_style", 'NONE')
        curb_r_style = coll.get("rka_curb_r_style", 'NONE')
        curb_height = coll.get("rka_curb_height", 0.15)
        curb_thickness = coll.get("rka_curb_thickness", 0.25)
        curb_asset_collection = coll.get("rka_curb_asset_collection", "")
        curb_asset_spacing = coll.get("rka_curb_asset_spacing", 2.0)
        curb_asset_rot_offset_r = coll.get("rka_curb_asset_rot_offset_r", 180.0)
        auto_lane_markings = coll.get("rka_auto_lane_markings", True)
        traffic_side = coll.get("rka_traffic_side", "LEFT")
        median_width = coll.get("rka_median_width", 0.0)
        median_style = coll.get("rka_median_style", "NONE")
        median_asset_collection = coll.get("rka_median_asset_collection", "")
        median_asset_spacing = coll.get("rka_median_asset_spacing", 2.0)
        sidewalk_l_width = coll.get("rka_sidewalk_l_width", 0.0)
        sidewalk_r_width = coll.get("rka_sidewalk_r_width", 0.0)
        sidewalk_height = coll.get("rka_sidewalk_height", 0.15)
        sidewalk_l_asset_collection = coll.get("rka_sidewalk_l_asset_collection", "")
        sidewalk_r_asset_collection = coll.get("rka_sidewalk_r_asset_collection", "")
        sidewalk_asset_spacing = coll.get("rka_sidewalk_asset_spacing", 2.0)
        prop_l_asset_collection = coll.get("rka_prop_l_asset_collection", "")
        prop_l_spacing = coll.get("rka_prop_l_spacing", 30.0)
        prop_r_asset_collection = coll.get("rka_prop_r_asset_collection", "")
        prop_r_spacing = coll.get("rka_prop_r_spacing", 30.0)

        angle_deg = port_obj.get("rka_port_heading_deg", 0.0)
        rad = math.radians(angle_deg)
        px, py, z = port_obj.location.x, port_obj.location.y, port_obj.location.z
        p0 = (px, py)
        p1 = (px + self.length * math.cos(rad), py + self.length * math.sin(rad))
        k = ik()
        pts = k.segment_spine_3d(p0, p1, self.bend, self.curve_segments, 0.0,
                                  self.elevation_delta, self.bend_z)
        pts = [(x, y, z + zr) for (x, y, zr) in pts]

        try:
            result = _build_segment_from_points(
                context, parent_collection_of(coll), pts, lane_width, lanes, lanes_backward,
                curb_l_style, curb_r_style, curb_height, curb_thickness, self.join_visual_mesh,
                self.export_path, self.gltf_export_path, traffic_side=traffic_side,
                curb_asset_collection=curb_asset_collection, curb_asset_spacing=curb_asset_spacing,
                curb_asset_rot_offset_r=curb_asset_rot_offset_r,
                auto_lane_markings=auto_lane_markings,
                median_width=median_width, median_style=median_style,
                median_asset_collection=median_asset_collection,
                median_asset_spacing=median_asset_spacing,
                sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width,
                sidewalk_height=sidewalk_height,
                sidewalk_l_asset_collection=sidewalk_l_asset_collection,
                sidewalk_r_asset_collection=sidewalk_r_asset_collection,
                sidewalk_asset_spacing=sidewalk_asset_spacing,
                prop_l_asset_collection=prop_l_asset_collection, prop_l_spacing=prop_l_spacing,
                prop_r_asset_collection=prop_r_asset_collection, prop_r_spacing=prop_r_spacing,
                lanes_end=_taper_end(self.lanes_end),
                lanes_backward_end=_taper_end(self.lanes_backward_end), align=self.align)
        except RkaBuildError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _stamp_link(result["coll"], port_obj)

        for w in result["warnings"]:
            self.report({'WARNING'}, w)
        self.report({'INFO'}, "Extended '%s' from '%s' by %.1fm%s" %
                     (coll.name, port_obj.name, self.length, result["export_note"]))
        return {'FINISHED'}


class RKA_OT_select_spine(bpy.types.Operator):
    """Isolate a GN segment/lane-transition's own `spine_*` Curve object as the sole selection/
    active object -- the quick way to jump from 'everything selected' (e.g. after
    `rka.select_piece`) straight to the one editable curve (Tab into Edit Mode to reshape/extend it
    live -- see the 'Straight Segment' panel section), instead of hunting for it by name in an
    Outliner/viewport that gets busy fast as a road network grows. `rka_curve_object` already
    stores the spine's exact (globally-unique, unlike `arm_*`) object name, so this is a direct
    lookup, not a scan."""
    bl_idname = "rka.select_spine"
    bl_label = "Select Spine"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_curve_object" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None:
            self.report({'ERROR'}, "Activate a segment/lane-transition (or one of its objects) "
                                    "first")
            return {'CANCELLED'}
        spine = local_object(coll.get("rka_curve_object"))
        if spine is None:
            self.report({'ERROR'}, "'%s' has no spine object (rka_curve_object missing/stale)"
                                    % coll.name)
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        spine.select_set(True)
        context.view_layer.objects.active = spine
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
        curb_l_style = coll.get("rka_curb_l_style", coll.get("rka_curb_style", 'NONE'))
        curb_r_style = coll.get("rka_curb_r_style", coll.get("rka_curb_style", 'NONE'))
        curb_height = coll.get("rka_curb_height", 0.15)
        curb_thickness = coll.get("rka_curb_thickness", 0.25)
        traffic_side = coll.get("rka_traffic_side", "LEFT")
        rka = context.scene.rka
        k = ik()
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
            # An intersection loop is one continuous curb, so it only takes one style -- Left is
            # the representative value (matches pre-existing behavior when L/R were equal; a
            # reasonable default when they differ, same tradeoff `build_intersection_geometry`'s
            # other callers already accept).
            ires = build_intersection_geometry(
                context, parent, (split_x, split_y, split_zr), self.preset, dir_deg,
                self.side_angle, "", lane_width, lanes, [0, 0, 0, 0], self.kerb_radius,
                self.tail_length, 8, curb_l_style, curb_height, curb_thickness, None,
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
            # GN-backed builder (2026-08) -- the old `build_segment_geometry`/
            # `_populate_segment_mesh` legacy path never got the update-in-place crash-surface
            # fix (its live-drag rebuild, `rebuild_segment_in_place`, still does a full Python
            # delete+recreate of curb_/ribbon_ objects on every depsgraph tick), so a segment
            # spliced in here would silently reintroduce the exact "crash mid-drag" class the
            # rest of the addon already closed. `_build_segment_from_points` is the same builder
            # `RKA_OT_build_straight_segment` uses -- same `segment_spine_3d` point generation,
            # just called directly instead of through `bpy.ops`.
            _, angle_deg, arm_lanes, _lanes_out = next(a for a in new_arms if a[0] == arm_name)
            rad = math.radians(angle_deg)
            px = split_x + self.tail_length * math.cos(rad)
            py = split_y + self.tail_length * math.sin(rad)
            p0 = (px, py)
            p1 = (px + length * math.cos(rad), py + length * math.sin(rad))
            z = split_zr + rka.lane_surface_z
            pts = [(x, y, z + zr) for (x, y, zr) in k.segment_spine_3d(p0, p1, 0.0, 8, 0.0, 0.0, 0.0)]
            r = _build_segment_from_points(
                context, parent, pts, lane_width, arm_lanes, arm_lanes,
                curb_l_style, curb_r_style, curb_height, curb_thickness,
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


def _effective_end_lanes(coll, backward):
    """The END-side lane count for one direction (`rka_lanes_backward_end`/`rka_lanes_end`),
    falling back to that direction's START value when no independent end value has been set yet
    -- `_taper_end`'s -1 sentinel becomes "key not written at all" (see
    `custom_props.write_build_settings`), so an untapered piece's end value IS its start value
    until something actually diverges them. The single place both `RKA_OT_adjust_segment_lanes_
    end` and `_refresh_pavement_radius` read this, so they can never disagree on what "currently
    untapered" means."""
    start_key = "rka_lanes_backward" if backward else "rka_lanes"
    end_key = "rka_lanes_backward_end" if backward else "rka_lanes_end"
    return int(coll.get(end_key, coll.get(start_key, 1)))


def _effective_end_median(coll):
    """Same fallback as `_effective_end_lanes`, for `rka_median_width_end`."""
    return coll.get("rka_median_width_end", coll.get("rka_median_width", 0.0))


def _effective_end_sidewalk(coll, side):
    """Same fallback as `_effective_end_lanes`/`_effective_end_median`, for one side's
    `rka_sidewalk_l_width_end`/`rka_sidewalk_r_width_end`."""
    start_key = "rka_sidewalk_l_width" if side == 'L' else "rka_sidewalk_r_width"
    end_key = "rka_sidewalk_l_width_end" if side == 'L' else "rka_sidewalk_r_width_end"
    return coll.get(end_key, coll.get(start_key, 0.0))


def _segment_only_collection(context):
    """The active plain GN segment's Collection (`rka_curve_object` present, `rka_lanes_a`
    absent) -- shared poll/target resolution for sidewalk/prop controls, which (like median
    width) only apply to a plain segment: `_populate_transition_visuals` never reads
    sidewalk/prop fields at all, so a lane-transition piece has nothing for these to act on.
    Same active-object-then-active-collection resolution order as
    `RKA_OT_adjust_median_width`/`_end`. None if nothing matching is active."""
    obj = context.active_object
    if (obj is not None and obj.users_collection
            and "rka_curve_object" in obj.users_collection[0].keys()
            and "rka_lanes_a" not in obj.users_collection[0].keys()):
        return obj.users_collection[0]
    coll = context.view_layer.active_layer_collection.collection
    if coll is not None and "rka_curve_object" in coll.keys() and "rka_lanes_a" not in coll.keys():
        return coll
    return None


def _refresh_pavement_radius(coll, spine_obj):
    """Recompute EVERY point of `spine_obj`'s own per-point pavement RADIUS from the segment's
    current start (`rka_lanes`/`rka_lanes_backward`/`rka_median_width`) AND end
    (`_effective_end_lanes`/`_effective_end_median`) properties -- the one place any button that
    changes a lane count or median width (either side) refreshes the spine's Radius before
    `rebuild_segment_gn_in_place` rebuilds curb/median/marking geometry around it.

    2026-08 fix: the two callers of this used to each flatten EVERY point to one uniform half-
    width computed from the START side only -- correct for an untapered piece, but silently
    ERASED any taper already in effect the moment the OTHER end (or even the same end again) was
    adjusted, since nothing ever re-derived the END side's own width. `_populate_segment_mesh_gn`
    itself never touches the spine's radius (`spine_obj`'s own control points are the live-edited
    source of truth -- see that function's docstring), so a wrong flatten here silently persisted
    until the next full geometry-edit-triggered rebuild. Always uses
    `intersection_kit.tapered_scalars` (arc-length blend, degenerates to one uniform value when
    start == end -- see its own docstring) so a genuinely tapered piece keeps tapering correctly
    no matter which end's control triggered the refresh.

    NO-OP ON A MODIFIER-STACK CARRIER, and that is the correct answer rather than a missing
    feature: the Curve spine's built-in per-point `radius` is the ONLY channel a Curve has for a
    varying width, so it has to be written here; a mesh carrier keeps the same quantity in its
    `rka_halfw` attribute, which `apply_segment_stack` recomputes from these very properties (plus
    everything else the radius alone cannot express). Every caller runs a rebuild straight after
    this, so the stack picks the new width up there. The guard lives HERE rather than at the call
    sites because `live_edit._sync_linked_width` was a fifth, unguarded caller -- it crashed with
    `'Mesh' object has no attribute 'splines'` the moment a stack piece was joined to anything."""
    if not spine_io.is_spine(spine_obj) or spine_io.is_stack_carrier(spine_obj):
        return
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    lanes_end = _effective_end_lanes(coll, backward=False)
    lanes_backward_end = _effective_end_lanes(coll, backward=True)
    median_width = coll.get("rka_median_width", 0.0)
    median_width_end = _effective_end_median(coll)
    median_half = median_width / 2.0 if (median_width > 0.0 and lanes > 0 and lanes_backward > 0) \
        else 0.0
    median_half_end = median_width_end / 2.0 if (median_width_end > 0.0 and lanes_end > 0
                                                   and lanes_backward_end > 0) else 0.0
    # Asymmetric carriageway -- must mirror `_build_segment_from_points`'s own computation exactly,
    # INCLUDING re-pushing the two profile fractions onto the live "Road" modifier. A rebuild that
    # only refreshed the radius would silently revert a one-way piece to the symmetric
    # double-width sweep the moment any lane/median control was touched.
    neg_w, pos_w = ik().carriageway_extents(lanes, lanes_backward, lane_width, median_half)
    neg_w_end, pos_w_end = ik().carriageway_extents(lanes_end, lanes_backward_end, lane_width,
                                                     median_half_end)
    half_w, _shift = ik().sweep_radius_and_shift(neg_w, pos_w)
    half_w_end, _shift_end = ik().sweep_radius_and_shift(neg_w_end, pos_w_end)
    paths.kc.set_road_spine_profile_fracs(
        spine_obj, *ik().sweep_profile_fracs(neg_w, pos_w,
                                              coll.get("rka_traffic_side", "LEFT")))
    pts = spine_obj.data.splines[0].points
    if half_w == half_w_end:
        for pt in pts:
            pt.radius = max(half_w, 1e-3)
        return
    radii = ik().tapered_scalars(_spine_control_points(spine_obj), half_w, half_w_end)
    for pt, r in zip(pts, radii):
        pt.radius = max(r, 1e-3)


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
        new_val = max(0, min(4, int(coll.get(key, 1)) + self.delta))
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
            #
            # This write happens OUTSIDE `rebuild_segment_gn_in_place` (which is itself
            # `@live_edit.rebuilding()`-guarded) -- so it needs its OWN guard here too, or
            # `_on_depsgraph_update` sees the spine's geometry change as fresh "dirt" on the very
            # next tick and silently re-queues a REDUNDANT rebuild of this same collection
            # ~_DEBOUNCE_SECONDS later via `bpy.app.timers`, entirely unprompted -- the confirmed
            # cause of a real segfault inside `clear_generated_mesh_objects` (a double rebuild
            # landing back-to-back right after a single 'Adjust Segment Lanes' click; see
            # `live_edit.rebuilding`'s docstring for the full crash-log trace).
            with live_edit.rebuilding():
                spine_name = coll.get("rka_curve_object")
                spine_obj = local_object(spine_name)
                if spine_obj is not None and spine_obj.type == 'CURVE':
                    _refresh_pavement_radius(coll, spine_obj)
                rebuild_segment_gn_in_place(context, coll)
        else:
            rebuild_segment_in_place(context, coll)
        self.report({'INFO'}, "'%s' %s lanes -> %d" %
                     (coll.name, "backward" if self.backward else "forward", new_val))
        return {'FINISHED'}


class RKA_OT_adjust_segment_lanes_end(bpy.types.Operator):
    """+/- a segment's lane count in ONE direction AT THE FAR (END) PORT (`backward=False` ->
    `rka_lanes_end`, `backward=True` -> `rka_lanes_backward_end`) and immediately rebuild it in
    place -- the missing counterpart to `RKA_OT_adjust_segment_lanes`, which only ever touched the
    START side. 2026-08, user-reported: "one port increase lane/one port decrease lane, the
    overall mesh seem not change" -- there was previously NO live control for the end side at all
    (only the build-time dialog's `Lanes Forward/Backward (End)` fields, or hand-editing the
    Custom Property and separately triggering a rebuild), so a segment could never actually be
    tapered after the fact. First click on an untapered piece (`rka_lanes_end` unset, i.e. same as
    start -- see `_effective_end_lanes`) makes it genuinely tapered from then on. Only for a GN
    spine-backed plain segment -- a lane-transition piece already exposes independent per-end
    control via its own Custom Properties, and the legacy ribbon-segment path never modeled a
    taper at all."""
    bl_idname = "rka.adjust_segment_lanes_end"
    bl_label = "Adjust Segment Lanes (End)"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.IntProperty(default=1)
    backward: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            return True
        coll = context.view_layer.active_layer_collection.collection
        return (coll is not None and "rka_curve_object" in coll.keys()
                and "rka_lanes_a" not in coll.keys())

    def execute(self, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            coll = obj.users_collection[0]
        else:
            coll = context.view_layer.active_layer_collection.collection
        key = "rka_lanes_backward_end" if self.backward else "rka_lanes_end"
        new_val = max(0, min(4, _effective_end_lanes(coll, self.backward) + self.delta))
        other_val = _effective_end_lanes(coll, not self.backward)
        if new_val == 0 and other_val == 0:
            self.report({'ERROR'}, "Can't set both directions to 0 at the end port -- a road "
                                    "needs at least one lane somewhere")
            return {'CANCELLED'}
        coll[key] = new_val
        with live_edit.rebuilding():
            spine_name = coll.get("rka_curve_object")
            spine_obj = local_object(spine_name)
            if spine_obj is not None and spine_obj.type == 'CURVE':
                _refresh_pavement_radius(coll, spine_obj)
            rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' %s lanes (end) -> %d" %
                     (coll.name, "backward" if self.backward else "forward", new_val))
        return {'FINISHED'}


class RKA_OT_adjust_median_width(bpy.types.Operator):
    """+/- a segment's median width (`rka_median_width`, the gap between forward/backward lanes)
    and immediately rebuild it in place -- 2026-08, the missing counterpart to
    `RKA_OT_adjust_segment_lanes`/`RKA_OT_set_curb_style`: median width was previously a
    BUILD-TIME-ONLY property (`RKA_OT_build_straight_segment`/`RKA_OT_extend_from_arm`'s own
    `median_width` field) with no way to change it afterward short of hand-editing
    `rka_median_width` in the Custom Properties panel and then separately clicking 'Rebuild From
    Handles'. Refuses to go negative; `step` (default 1.0 m) matches `Adjust Segment Lanes`'
    always-one-unit-per-click feel while staying a tunable float instead of a fixed lane-width
    unit. Only for a GN spine-backed plain segment (`rka_curve_object` present, `rka_lanes_a`
    absent) -- a lane-transition piece already exposes independent per-end median control
    (`median_width`/`median_width_end`) via its own Custom Properties, and the legacy
    ribbon-segment path never modeled a median at all."""
    bl_idname = "rka.adjust_median_width"
    bl_label = "Adjust Median Width"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            return True
        coll = context.view_layer.active_layer_collection.collection
        return (coll is not None and "rka_curve_object" in coll.keys()
                and "rka_lanes_a" not in coll.keys())

    def execute(self, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            coll = obj.users_collection[0]
        else:
            coll = context.view_layer.active_layer_collection.collection
        new_val = max(0.0, coll.get("rka_median_width", 0.0) + self.delta)
        coll["rka_median_width"] = new_val
        # Same "refresh the spine's own Radius before rebuilding curb/lanecl_*" reasoning as
        # `RKA_OT_adjust_segment_lanes` -- and the SAME guard requirement (a plain lane-count
        # change is not the only write that needs it; any spine.radius write does).
        with live_edit.rebuilding():
            spine_name = coll.get("rka_curve_object")
            spine_obj = local_object(spine_name)
            if spine_obj is not None and spine_obj.type == 'CURVE':
                _refresh_pavement_radius(coll, spine_obj)
            rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' median width -> %.2fm" % (coll.name, new_val))
        return {'FINISHED'}


class RKA_OT_adjust_median_width_end(bpy.types.Operator):
    """+/- a segment's median width AT THE FAR (END) PORT (`rka_median_width_end`) and
    immediately rebuild it in place -- the missing counterpart to `RKA_OT_adjust_median_width`,
    which only ever touched the START side. Same "first click on an untapered piece makes it
    genuinely tapered from then on" semantics as `RKA_OT_adjust_segment_lanes_end` -- see
    `_effective_end_median`. Refuses to go negative."""
    bl_idname = "rka.adjust_median_width_end"
    bl_label = "Adjust Median Width (End)"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            return True
        coll = context.view_layer.active_layer_collection.collection
        return (coll is not None and "rka_curve_object" in coll.keys()
                and "rka_lanes_a" not in coll.keys())

    def execute(self, context):
        obj = context.active_object
        if (obj is not None and obj.users_collection
                and "rka_curve_object" in obj.users_collection[0].keys()
                and "rka_lanes_a" not in obj.users_collection[0].keys()):
            coll = obj.users_collection[0]
        else:
            coll = context.view_layer.active_layer_collection.collection
        new_val = max(0.0, _effective_end_median(coll) + self.delta)
        coll["rka_median_width_end"] = new_val
        with live_edit.rebuilding():
            spine_name = coll.get("rka_curve_object")
            spine_obj = local_object(spine_name)
            if spine_obj is not None and spine_obj.type == 'CURVE':
                _refresh_pavement_radius(coll, spine_obj)
            rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' median width (end) -> %.2fm" % (coll.name, new_val))
        return {'FINISHED'}


class RKA_OT_set_curb_style(bpy.types.Operator):
    """Change curb style (NONE/PROFILE) on an ALREADY-BUILT GN segment or lane transition
    and rebuild it in place. The build operators (`RKA_OT_build_straight_segment`/
    `RKA_OT_build_lane_transition`) only expose Curb Style via Blender's own F9 'Adjust Last
    Operation' panel -- which silently stops applying to the piece the moment ANY other action
    runs (a well-known, easy-to-hit Blender behavior, not a bug in this addon) -- so there was
    previously no reliable way to change curb style on a piece after the fact from the Sidebar
    panel at all. This is that: a persistent button, always live for whatever piece is currently
    active/selected, regardless of what happened since it was built.

    `side` picks which lateral edge to change ('BOTH' sets L and R to the same style in one
    click); `asset_collection` only matters when `style == 'PROFILE'` -- set it via THIS operator's
    own F9 redo panel immediately after clicking (same convention the build operators already use
    for this field; left blank, PROFILE silently produces no curb on that side, same as at build
    time). Supports the GN spine-backed piece types (`rka_curve_object` present, which is every
    segment built via the default 'Build Straight Segment'/'Extend From...' operators, plus every
    lane transition -- the older ribbon-based legacy point-segment never gained per-side or asset
    curb support at all, see `_populate_segment_mesh`'s single `curb_style` param) AND
    intersections (2026-08, user-reported: intersections had no persistent curb-style control at
    all, unlike segments) -- an intersection has ONE curb style for every corner (`rka_curb_style`,
    not per-side), so `side` is simply ignored there."""
    bl_idname = "rka.set_curb_style"
    bl_label = "Set Curb Style"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(
        name="Side", items=[('L', "Left", ""), ('R', "Right", ""), ('BOTH', "Both", "")],
        default='BOTH')
    style: bpy.props.EnumProperty(name="Style", items=CURB_STYLE_ITEMS, default='NONE')
    asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Name of a linked kit/curb_kit.blend collection whose "
        "mesh object's own cross-section is swept, when Style is 'Profile'. Use 'Link Curb Kit "
        "Library' first, then type the name here via THIS operator's F9 panel", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and ("rka_curve_object" in coll.keys()
                                      or "rka_arm_names" in coll.keys())

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        is_intersection = coll is not None and "rka_arm_names" in coll.keys()
        if coll is None or not (is_intersection or "rka_curve_object" in coll.keys()):
            self.report({'ERROR'}, "No active GN segment/lane-transition/intersection piece")
            return {'CANCELLED'}
        if is_intersection:
            coll["rka_curb_style"] = self.style
        else:
            if self.side in ('L', 'BOTH'):
                coll["rka_curb_l_style"] = self.style
            if self.side in ('R', 'BOTH'):
                coll["rka_curb_r_style"] = self.style
        if self.style == 'PROFILE' and self.asset_collection:
            coll["rka_curb_asset_collection"] = self.asset_collection
        from . import ops_intersection as opint
        opint._rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' curb style (%s) -> %s"
                     % (coll.name, "intersection" if is_intersection else self.side, self.style))
        return {'FINISHED'}


class RKA_OT_pick_curb_asset(bpy.types.Operator):
    """Real DROPDOWN (`layout.operator_menu_enum`) picker for `rka_curb_asset_collection` -- the
    discoverable counterpart to `RKA_OT_set_curb_style`'s text-typed `asset_collection` (only ever
    editable via Blender's F9 redo panel). 2026-08, user-requested: "is it possible to also do
    drop down selection on asset or none" (see `linked_asset_picker_items`'s own docstring for the
    full rationale). Works on either a segment (both sides share one curb asset piece,
    `curb_asset_rot_offset_r` already handles the R-side flip) or an intersection (one piece for
    every corner) -- same dual scope `RKA_OT_set_curb_style` already has.

    Picking a REAL piece also switches curb style to 'Profile' (both sides, for a segment) if it
    wasn't already -- otherwise choosing a piece here would silently do nothing visible while
    style stayed 'None', reading as "the dropdown doesn't work." Picking 'None' only clears
    the piece reference; it does NOT change style back (matching `RKA_OT_set_median_style`'s same
    'asset name is independent of style' convention) -- switch style via the Curb Style buttons
    for that."""
    bl_idname = "rka.pick_curb_asset"
    bl_label = "Curb Asset Piece"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Curb Asset Piece", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and ("rka_curve_object" in coll.keys()
                                      or "rka_arm_names" in coll.keys())

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        is_intersection = coll is not None and "rka_arm_names" in coll.keys()
        if coll is None or not (is_intersection or "rka_curve_object" in coll.keys()):
            self.report({'ERROR'}, "No active GN segment/lane-transition/intersection piece")
            return {'CANCELLED'}
        value = _asset_picker_value(self.collection_name)
        coll["rka_curb_asset_collection"] = value
        # Only auto-switch style away from NONE -- if the piece is already PROFILE, picking a
        # DIFFERENT piece must keep that style, not silently re-set it.
        if value:
            if is_intersection:
                if coll.get("rka_curb_style", "NONE") != 'PROFILE':
                    coll["rka_curb_style"] = 'PROFILE'
            else:
                if coll.get("rka_curb_l_style", "NONE") != 'PROFILE':
                    coll["rka_curb_l_style"] = 'PROFILE'
                if coll.get("rka_curb_r_style", "NONE") != 'PROFILE':
                    coll["rka_curb_r_style"] = 'PROFILE'
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' curb asset piece -> '%s'" % (coll.name, value or "(none)"))
        return {'FINISHED'}


class RKA_OT_set_median_style(bpy.types.Operator):
    """Change median style (NONE/PROFILE) on an ALREADY-BUILT GN segment or lane transition and
    rebuild it in place -- the median counterpart of `RKA_OT_set_curb_style` (2026-08, user-
    reported: median style previously had NO persistent panel control at all, only a build-time F9
    field -- unlike median WIDTH, which already has live +/- buttons). Same reasoning as
    `RKA_OT_set_curb_style`'s docstring for why a persistent operator is needed. Two styles only
    (2026-08, user-requested: "only have none/profile... to simplify the code base" -- PROFILE
    replaces the earlier ASSET discrete-row style, sweeping the piece's own real cross-section
    continuously instead, see `MEDIAN_STYLE_ITEMS`'s own module comment for the full history).

    `asset_collection` only matters when `style` is `'PROFILE'` -- set it via THIS operator's own
    F9 redo panel immediately after clicking (same convention `RKA_OT_set_curb_style` uses); left
    blank, PROFILE silently produces no median geometry, same as at build time. Only supports the
    GN spine-backed piece types (`rka_curve_object` present) -- same scope as
    `RKA_OT_set_curb_style`."""
    bl_idname = "rka.set_median_style"
    bl_label = "Set Median Style"
    bl_options = {'REGISTER', 'UNDO'}

    style: bpy.props.EnumProperty(name="Style", items=MEDIAN_STYLE_ITEMS, default='NONE')
    asset_collection: bpy.props.StringProperty(
        name="Median Asset Piece", description="Name of a linked kit/curb_kit.blend collection's "
        "mesh object to sweep continuously, when Style is 'Profile'. Use 'Link Curb Kit Library' "
        "first, then type the name here via THIS operator's F9 panel", default="")

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_curve_object" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_curve_object" not in coll.keys():
            self.report({'ERROR'}, "No active GN segment/lane-transition piece")
            return {'CANCELLED'}
        coll["rka_median_style"] = self.style
        if self.style == 'PROFILE' and self.asset_collection:
            coll["rka_median_asset_collection"] = self.asset_collection
        from . import ops_intersection as opint
        opint._rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' median style -> %s" % (coll.name, self.style))
        return {'FINISHED'}


class RKA_OT_pick_median_asset(bpy.types.Operator):
    """Real DROPDOWN picker for `rka_median_asset_collection` -- the discoverable counterpart to
    `RKA_OT_set_median_style`'s text-typed `asset_collection` (see `RKA_OT_pick_curb_asset`'s
    docstring for the shared rationale). Picking a real piece also switches Median Style to
    'Asset' if it wasn't already; picking 'None' only clears the piece reference."""
    bl_idname = "rka.pick_median_asset"
    bl_label = "Median Asset Piece"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Median Asset Piece", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and "rka_curve_object" in coll.keys()

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_curve_object" not in coll.keys():
            self.report({'ERROR'}, "No active GN segment/lane-transition piece")
            return {'CANCELLED'}
        value = _asset_picker_value(self.collection_name)
        coll["rka_median_asset_collection"] = value
        if value and coll.get("rka_median_style", "NONE") != 'PROFILE':
            coll["rka_median_style"] = 'PROFILE'
        _rebuild_piece_in_place(context, coll)
        self.report({'INFO'}, "'%s' median asset piece -> '%s'" % (coll.name, value or "(none)"))
        return {'FINISHED'}


class RKA_OT_adjust_sidewalk_width(bpy.types.Operator):
    """+/- one side's sidewalk width (`rka_sidewalk_l_width`/`rka_sidewalk_r_width`) and
    immediately rebuild in place -- 2026-08, the missing discoverable "turn it off" path:
    sidewalk width has been a full build-time property (`RKA_OT_build_straight_segment`'s
    `sidewalk_l_width`/`sidewalk_r_width`) since it was added, but only ever settable via the F9
    redo panel (which stops applying the moment any other action runs) -- there was no persistent
    button to adjust or remove one after the fact, unlike median width. 0 is already the
    documented "no sidewalk on this side" state (`_populate_segment_mesh_gn`'s own `width <= 0.0`
    skip) -- this operator is just the reliable live control for it. Refuses to go negative. Only
    for a plain GN segment -- see `_segment_only_collection`."""
    bl_idname = "rka.adjust_sidewalk_width"
    bl_label = "Adjust Sidewalk Width"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(name="Side", items=(('L', "Left", ""), ('R', "Right", "")),
                                  default='L')
    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        key = "rka_sidewalk_l_width" if self.side == 'L' else "rka_sidewalk_r_width"
        new_val = max(0.0, coll.get(key, 0.0) + self.delta)
        coll[key] = new_val
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk width (%s) -> %.2fm" % (coll.name, self.side, new_val))
        return {'FINISHED'}


class RKA_OT_adjust_sidewalk_width_end(bpy.types.Operator):
    """+/- one side's sidewalk width AT THE FAR (END) PORT (`rka_sidewalk_l_width_end`/
    `rka_sidewalk_r_width_end`) -- the missing end-side counterpart, same "first click on an
    untapered piece makes it genuinely tapered from then on" semantics as
    `RKA_OT_adjust_median_width_end`/`RKA_OT_adjust_segment_lanes_end` (see
    `_effective_end_sidewalk`). Refuses to go negative."""
    bl_idname = "rka.adjust_sidewalk_width_end"
    bl_label = "Adjust Sidewalk Width (End)"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(name="Side", items=(('L', "Left", ""), ('R', "Right", "")),
                                  default='L')
    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        key = "rka_sidewalk_l_width_end" if self.side == 'L' else "rka_sidewalk_r_width_end"
        new_val = max(0.0, _effective_end_sidewalk(coll, self.side) + self.delta)
        coll[key] = new_val
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk width (end, %s) -> %.2fm"
                     % (coll.name, self.side, new_val))
        return {'FINISHED'}


class RKA_OT_set_sidewalk_asset(bpy.types.Operator):
    """Set (or clear) one side's sidewalk kit piece -- `rka_sidewalk_l_asset_collection`/
    `rka_sidewalk_r_asset_collection` -- on an ALREADY-BUILT plain GN segment and rebuild in
    place. 2026-08, user-requested: "will it be simpler and easily to regenerate all curb/side
    way from asset... just follow the asset library ones". Blank `collection_name` (default)
    falls back to the procedural BOX sweep on that side, matching the build-time convention
    exactly (`_populate_segment_mesh_gn` uses `curb_loop` when `sidewalk_*_asset_obj is None`)."""
    bl_idname = "rka.set_sidewalk_asset"
    bl_label = "Set Sidewalk Asset"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(name="Side", items=(('L', "Left", ""), ('R', "Right", "")),
                                  default='L')
    collection_name: bpy.props.StringProperty(
        name="Sidewalk Asset", description="Name of a linked collection's mesh object to tile "
        "along this side's sidewalk -- e.g. 'Kit_Curb_SidewalkTile_L2'. Blank = procedural BOX "
        "sweep", default="")

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        key = ("rka_sidewalk_l_asset_collection" if self.side == 'L'
               else "rka_sidewalk_r_asset_collection")
        coll[key] = self.collection_name
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk asset (%s) -> '%s'"
                     % (coll.name, self.side, self.collection_name or "(procedural)"))
        return {'FINISHED'}


def _pick_sidewalk_asset(context, side, collection_name):
    """Shared body for `RKA_OT_pick_sidewalk_asset_l`/`_r` -- real DROPDOWN pickers for
    `rka_sidewalk_{l,r}_asset_collection`, the discoverable counterpart to `RKA_OT_set_
    sidewalk_asset`'s text-typed field (see `RKA_OT_pick_curb_asset`'s docstring for the shared
    rationale). Split into two thin per-side operators (rather than one operator with a `side`
    property, like `RKA_OT_set_sidewalk_asset` above) because `layout.operator_menu_enum` -- the
    dropdown widget itself -- can only ever pop a menu over ONE property and runs the operator
    with every OTHER property left at its class default, so a single shared `side` property would
    silently always resolve to whichever side is listed first regardless of which dropdown was
    actually clicked."""
    coll = _segment_only_collection(context)
    if coll is None:
        return None, "No active plain GN segment"
    key = "rka_sidewalk_l_asset_collection" if side == 'L' else "rka_sidewalk_r_asset_collection"
    value = _asset_picker_value(collection_name)
    coll[key] = value
    rebuild_segment_gn_in_place(context, coll)
    return coll, value


class RKA_OT_pick_sidewalk_asset_l(bpy.types.Operator):
    """Dropdown picker for this segment's LEFT sidewalk asset piece -- see `_pick_sidewalk_asset`."""
    bl_idname = "rka.pick_sidewalk_asset_l"
    bl_label = "Sidewalk Asset (Left)"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Sidewalk Asset (Left)", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll, value = _pick_sidewalk_asset(context, 'L', self.collection_name)
        if coll is None:
            self.report({'ERROR'}, value)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' sidewalk asset (L) -> '%s'" % (coll.name, value or "(procedural)"))
        return {'FINISHED'}


class RKA_OT_pick_sidewalk_asset_r(bpy.types.Operator):
    """Dropdown picker for this segment's RIGHT sidewalk asset piece -- see `_pick_sidewalk_asset`."""
    bl_idname = "rka.pick_sidewalk_asset_r"
    bl_label = "Sidewalk Asset (Right)"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Sidewalk Asset (Right)", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll, value = _pick_sidewalk_asset(context, 'R', self.collection_name)
        if coll is None:
            self.report({'ERROR'}, value)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' sidewalk asset (R) -> '%s'" % (coll.name, value or "(procedural)"))
        return {'FINISHED'}


class RKA_OT_adjust_sidewalk_asset_spacing(bpy.types.Operator):
    """+/- the shared sidewalk-asset tiling spacing (`rka_sidewalk_asset_spacing`, one value for
    both sides -- a sidewalk tile piece is normally symmetric, unlike a prop) and rebuild in
    place. Clamped to a minimum of 0.1m (matches the build-time property's own `min=0.1`).
    Only visible/relevant while at least one side has a Sidewalk Asset piece set; harmless (just
    unused) otherwise."""
    bl_idname = "rka.adjust_sidewalk_asset_spacing"
    bl_label = "Adjust Sidewalk Asset Spacing"
    bl_options = {'REGISTER', 'UNDO'}

    delta: bpy.props.FloatProperty(default=0.5, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        new_val = max(0.1, coll.get("rka_sidewalk_asset_spacing", 2.0) + self.delta)
        coll["rka_sidewalk_asset_spacing"] = new_val
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' sidewalk asset spacing -> %.2fm" % (coll.name, new_val))
        return {'FINISHED'}


class RKA_OT_set_prop_asset(bpy.types.Operator):
    """Set (or clear) one side's prop row asset -- `rka_prop_l_asset_collection`/
    `rka_prop_r_asset_collection`, e.g. a street lamp -- on an ALREADY-BUILT plain GN segment and
    rebuild in place. 2026-08: prop rows have existed as a full build-time feature
    (`prop_l_asset_collection`/`prop_r_asset_collection` on `RKA_OT_build_straight_segment`) but,
    like sidewalk width, only via the F9 redo panel -- this is the persistent control. Blank
    `collection_name` (default) turns props off on that side, matching the build-time convention
    exactly (`_populate_segment_mesh_gn` skips the row when `prop_*_asset_obj is None`)."""
    bl_idname = "rka.set_prop_asset"
    bl_label = "Set Prop Asset"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(name="Side", items=(('L', "Left", ""), ('R', "Right", "")),
                                  default='L')
    collection_name: bpy.props.StringProperty(
        name="Prop Asset", description="Name of a linked collection's mesh object to repeat "
        "along this side's sidewalk (or curb, with no sidewalk) -- e.g. a street lamp. Blank = "
        "no props on this side", default="")

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        key = "rka_prop_l_asset_collection" if self.side == 'L' else "rka_prop_r_asset_collection"
        coll[key] = self.collection_name
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' prop asset (%s) -> '%s'"
                     % (coll.name, self.side, self.collection_name or "(none)"))
        return {'FINISHED'}


def _pick_prop_asset(context, side, collection_name):
    """Shared body for `RKA_OT_pick_prop_asset_l`/`_r` -- see `_pick_sidewalk_asset`'s docstring
    for why this is split into two thin per-side operators instead of a shared `side` property."""
    coll = _segment_only_collection(context)
    if coll is None:
        return None, "No active plain GN segment"
    key = "rka_prop_l_asset_collection" if side == 'L' else "rka_prop_r_asset_collection"
    value = _asset_picker_value(collection_name)
    coll[key] = value
    rebuild_segment_gn_in_place(context, coll)
    return coll, value


class RKA_OT_pick_prop_asset_l(bpy.types.Operator):
    """Dropdown picker for this segment's LEFT prop (street lamp, etc.) asset piece -- see
    `_pick_prop_asset`."""
    bl_idname = "rka.pick_prop_asset_l"
    bl_label = "Prop Asset (Left)"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Prop Asset (Left)", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll, value = _pick_prop_asset(context, 'L', self.collection_name)
        if coll is None:
            self.report({'ERROR'}, value)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' prop asset (L) -> '%s'" % (coll.name, value or "(none)"))
        return {'FINISHED'}


class RKA_OT_pick_prop_asset_r(bpy.types.Operator):
    """Dropdown picker for this segment's RIGHT prop (street lamp, etc.) asset piece -- see
    `_pick_prop_asset`."""
    bl_idname = "rka.pick_prop_asset_r"
    bl_label = "Prop Asset (Right)"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.EnumProperty(name="Prop Asset (Right)", items=linked_asset_picker_items)

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll, value = _pick_prop_asset(context, 'R', self.collection_name)
        if coll is None:
            self.report({'ERROR'}, value)
            return {'CANCELLED'}
        self.report({'INFO'}, "'%s' prop asset (R) -> '%s'" % (coll.name, value or "(none)"))
        return {'FINISHED'}


class RKA_OT_adjust_prop_spacing(bpy.types.Operator):
    """+/- one side's prop row spacing (`rka_prop_l_spacing`/`rka_prop_r_spacing`, e.g. street
    lamp interval) and immediately rebuild in place. Deliberately independent of sidewalk width --
    a prop's own spacing was already its own separate FloatProperty at build time (never tied to
    sidewalk continuity), so lamps can be spaced out along a road with or without a sidewalk
    (`_populate_segment_mesh_gn` places the row on the sidewalk line when one is active, else the
    curb line -- see that function's own docstring). Clamped to a minimum of 0.5m (matches the
    build-time property's own `min=0.5`) -- a spacing of 0 would divide by zero in
    `kit_common.sample_polyline`."""
    bl_idname = "rka.adjust_prop_spacing"
    bl_label = "Adjust Prop Spacing"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(name="Side", items=(('L', "Left", ""), ('R', "Right", "")),
                                  default='L')
    delta: bpy.props.FloatProperty(default=1.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return _segment_only_collection(context) is not None

    def execute(self, context):
        coll = _segment_only_collection(context)
        if coll is None:
            self.report({'ERROR'}, "No active plain GN segment")
            return {'CANCELLED'}
        key = "rka_prop_l_spacing" if self.side == 'L' else "rka_prop_r_spacing"
        new_val = max(0.5, coll.get(key, 8.0) + self.delta)
        coll[key] = new_val
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "'%s' prop spacing (%s) -> %.2fm" % (coll.name, self.side, new_val))
        return {'FINISHED'}


class RKA_OT_adjust_transition_lanes(bpy.types.Operator):
    """+/- lanes at ONE end of a lane transition (`end='A'`/`'B'`, `backward=False`/`True` for
    that end's forward/backward count) and immediately rebuild it in place -- the transition
    counterpart of `RKA_OT_adjust_segment_lanes`/`ops_intersection.RKA_OT_adjust_arm_lanes_out`.
    Transitions previously had NO dedicated lane-count buttons at all (`RKA_OT_adjust_segment_lanes`
    explicitly refuses a `rka_lanes_a` collection and tells the user to hand-edit `rka_lanes_a`/
    `rka_lanes_b`/`rka_lanes_backward_a`/`rka_lanes_backward_b` via the Custom Properties panel
    instead) -- this is the fix for that.

    Backward counts use the SAME 0-means-symmetric-with-forward sentinel
    `RKA_OT_adjust_arm_lanes_out`/`intersection_kit.build_lane_transition` already use (0 = "same
    as THIS end's own forward count", not "zero lanes") -- the first +/- press from 0 seeds the
    override at the CURRENT effective count before nudging, so it reads as "peel this side off and
    adjust it independently" rather than jumping straight to 1.

    Forward counts (`lanes_a`/`lanes_b`) are clamped to a MINIMUM OF 1, matching
    `RKA_OT_build_lane_transition`'s own property constraint (never 0) -- unlike a plain segment,
    a transition's cross-end taper math (`intersection_kit.build_lane_transition`'s
    `add_direction`/`_transition_lane_pairs`) pairs ONE direction's two ends together (e.g. a
    2->1 forward taper connects `lanes_a` directly to `lanes_b`), and going to exactly 0 lanes at
    only ONE end of that pairing (while the other end is still >0) is not a valid taper shape --
    it raises inside `_transition_lane_pairs` (confirmed by hand: `lanes_a=3, lanes_b=0` throws).
    Keeping forward >= 1 at both ends everywhere (as the build operator already guarantees)
    keeps every reachable backward sentinel resolution nonzero too, so backward never needs its
    own zero-guard here."""
    bl_idname = "rka.adjust_transition_lanes"
    bl_label = "Adjust Transition Lanes"
    bl_options = {'REGISTER', 'UNDO'}

    end: bpy.props.EnumProperty(name="End", items=(('A', "A", ""), ('B', "B", "")), default='A')
    backward: bpy.props.BoolProperty(default=False)
    delta: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is not None and obj.users_collection and "rka_lanes_a" in obj.users_collection[0].keys():
            return True
        coll = context.view_layer.active_layer_collection.collection
        return coll is not None and "rka_lanes_a" in coll.keys()

    def execute(self, context):
        obj = context.active_object
        if obj is not None and obj.users_collection and "rka_lanes_a" in obj.users_collection[0].keys():
            coll = obj.users_collection[0]
        else:
            coll = context.view_layer.active_layer_collection.collection

        fwd_key = "rka_lanes_a" if self.end == 'A' else "rka_lanes_b"
        bwd_key = "rka_lanes_backward_a" if self.end == 'A' else "rka_lanes_backward_b"
        forward = int(coll.get(fwd_key, 1))
        backward_stored = int(coll.get(bwd_key, 0))

        if self.backward:
            base = backward_stored if backward_stored > 0 else forward
            new_forward, new_backward = forward, max(0, min(4, base + self.delta))
        else:
            new_forward, new_backward = max(1, min(4, forward + self.delta)), backward_stored

        coll[fwd_key] = new_forward
        coll[bwd_key] = new_backward
        rebuild_lane_transition_in_place(context, coll)
        label = "symmetric (0)" if new_backward == 0 else str(new_backward)
        self.report({'INFO'}, "'%s' end %s -> forward %d, backward %s" %
                     (coll.name, self.end, new_forward, label))
        return {'FINISHED'}


def _heading_deg(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _place_segment_ports(coll, pts, lane_width):
    """Create/re-snap `port_A`/`port_B` marker Empties at the spine's first/last points -- pure
    CLICK TARGETS for `active_marker_position`/`RKA_OT_extend_from_port` (so a new segment,
    intersection, or lane transition can start exactly at the end of an existing plain segment,
    the same way `arm_*` markers already let you continue from an intersection), NOT drag
    handles: a GN segment's own control points, edited via Edit Mode on the spine itself, are the
    live-edited source of truth (see `kit_common.road_spine`) -- dragging a port marker does
    nothing to the geometry, and the marker gets silently re-snapped back to the spine's current
    endpoint on the next rebuild anyway.

    Deliberately tagged `rka_port` -- NOT `rka_segend` (the legacy ribbon path's marker key) --
    because `live_edit.py`'s depsgraph handler routes ANY `rka_segend`-tagged marker's owning
    collection to the LEGACY `rebuild_segment_in_place` (ribbon) rebuild, which would corrupt a
    modern GN segment's geometry (wrong object set, spine ignored). A key `live_edit.py` doesn't
    recognize at all means dragging one is simply inert, which is exactly the intended behavior.

    Idempotent (find existing by `rka_port` value within `coll` and update in place, else
    create) so this same call from `_populate_segment_mesh_gn` handles BOTH the fresh-build case
    and the re-snap-after-a-spine-edit case with no separate code path to drift out of sync."""
    ends = (("A", pts[0], _heading_deg(pts[1], pts[0])),      # outward = away from the segment
            ("B", pts[-1], _heading_deg(pts[-2], pts[-1])))
    size = min(1.2, lane_width * 0.25)
    for tag, pos, hd in ends:
        port = next((o for o in coll.objects if o.get("rka_port") == tag), None)
        if port is None:
            port = bpy.data.objects.new("port_%s" % tag, None)
            port.empty_display_type = 'SINGLE_ARROW'
            port.empty_display_size = size
            port["rka_port"] = tag
            coll.objects.link(port)
        port.location = pos
        port.rotation_euler = (0.0, 0.0, math.radians(hd))
        port["rka_port_heading_deg"] = hd


def _join_visuals_keeping_spine(context, coll, spine_obj, visual_objs, join_visual_mesh):
    """`join_visual_mesh`'s combine, with the SPINE ALWAYS EXCLUDED -- shared by
    `_populate_segment_mesh_gn` and `_populate_transition_visuals` (both start their `visual_objs`
    with `[spine_obj]`, so both hit this identically).

    2026-08, the "the merge is a separate mesh, which does not include lane data... and is hard to
    adjust" report. `ops_intersection.join_meshes` converts every non-Mesh input via
    `bpy.ops.object.convert(target='MESH')`, which BAKES the spine's live "Road" `GN_RoadProfile`
    modifier and leaves a plain mesh behind -- and because the spine is `visual_objs[0]`,
    `join_meshes` then renames THAT object to `mesh_<piece>`. Three things break at once, all
    silently:

      * `_build_segment_from_points` records `curve_object=spine_obj.name`, which is now
        "mesh_<piece>". `lane_export._export_gn_segment` requires `type == 'CURVE'`, so it returns
        None and `collect_pieces` SKIPS the piece entirely -- it contributes ZERO lanes to
        `.lanekit.json`, with only a "could not reconstruct build params" line to show for it.
      * the piece can no longer be live-edited -- its control points are gone, so
        `rebuild_segment_gn_in_place`/`live_edit.py` have nothing left to reshape.
      * `kit_common.bake_colonly_proxies` identifies the pavement by its "Road" GN modifier, so
        the baked piece silently loses its road collision too.

    Confirmed against real content: 40 of the 111 piece collections in `island_v3_roads.blend`
    had a MESH spine, while all 71 normally-built segments had a live CURVE + `GN_RoadProfile`.
    The 40 are exactly the `ops_split._emit` / `tools/island_v3_to_roadkit.py` interchange pieces
    -- the only callers that pass `join_visual_mesh=True`.

    Excluding the spine does NOT lose the pavement: the spine object still renders it through its
    live modifier, and the glTF exporter bakes GN output on the way out. That is precisely how the
    default `join_visual_mesh=False` path (every normal segment) has always worked."""
    if not join_visual_mesh:
        return visual_objs
    joinable = [o for o in visual_objs if o is not spine_obj]
    if not joinable:
        return visual_objs
    joined = join_meshes(context, joinable, "mesh_%s" % coll.name)
    return [spine_obj] + ([joined] if joined else joinable)


def _populate_segment_mesh_gn(context, coll, spine_obj, lane_width, lanes, lanes_backward,
                               curb_l_style, curb_r_style, curb_height, curb_thickness,
                               join_visual_mesh, traffic_side='LEFT', curb_asset_obj=None,
                               curb_asset_spacing=2.0, curb_asset_rot_offset_r=180.0,
                               auto_lane_markings=True, marking_gaps=None,
                               median_width=0.0, median_style='NONE',
                               median_asset_obj=None, median_asset_spacing=2.0,
                               sidewalk_l_width=0.0, sidewalk_r_width=0.0, sidewalk_height=0.15,
                               sidewalk_l_asset_obj=None, sidewalk_r_asset_obj=None,
                               sidewalk_asset_spacing=2.0,
                               prop_l_asset_obj=None, prop_l_spacing=30.0,
                               prop_r_asset_obj=None, prop_r_spacing=30.0,
                               lanes_end=None, lanes_backward_end=None, align='right',
                               median_width_end=None, sidewalk_l_width_end=None,
                               sidewalk_r_width_end=None, profile_set=None):
    """Curb + lanecl_* objects for a segment whose PAVEMENT already lives on `spine_obj` itself
    (a live `GN_RoadProfile` modifier -- see `kit_common.road_spine`). Curbs are
    `paths.kc.curb_loop(closed=False)` (GN, correctly mitered even on a multi-point bent spine)
    from the SAME tangent-offset points `intersection_kit.build_segment_from_spine` already
    computes for its `curbs` field (radius 0 everywhere -- an open curb line has no corners to
    fillet). `curb_l_style`/`curb_r_style` are independent and each one of `'NONE'`/`'PROFILE'`
    (2026-08, "only have none/profile... to simplify the code base" -- the ASSET-style discrete
    `curb_asset_row` tiling this replaced is documented on `kit_common.curb_loop`'s own PROFILE
    branch, not dispatched from here anymore); `curb_asset_obj` feeds `curb_loop`'s PROFILE sweep
    directly (harmless/unused when a side is NONE). `curb_asset_spacing`/`curb_asset_rot_offset_r`
    are no longer read here (ASSET-only knobs, kept as still-valid `build_curb`/`curb_asset_row`
    args for any direct caller, e.g. `median_merge.py`). `lanecl_*` data curves are unchanged.
    Returns `visual_objs` INCLUDING `spine_obj` itself, so join/export naturally pick up the
    pavement mesh too. Does NOT touch/recreate `spine_obj` -- its own control points are the
    live-edited source of truth (see `rebuild_segment_gn_in_place`).

    `median_width`/`median_style`/`median_asset_obj` -- see `intersection_kit.
    build_segment_from_spine`'s `median_width` docstring. When the segment's own
    `seg["median_edges"]` comes back non-empty (median genuinely active) and `median_style ==
    'PROFILE'`, ONE more object is built along the spine's own centerline (the two lane groups are
    offset outward from the spine by `median_half`, so the spine points already ARE the median's
    centerline -- no separate edge-line math needed) via `curb_loop(curb_style='PROFILE',
    asset_obj=median_asset_obj)` -- the resolved kit piece's own real cross-section, swept
    CONTINUOUSLY, same mechanism curb/sidewalk PROFILE already use. `median_style='NONE'` (or
    `median_width=0` at both ends) is a flush painted gap only -- the continuous `road_spine`
    pavement already covers that width, so no new object is built at all.

    `sidewalk_l_width`/`sidewalk_r_width`/`sidewalk_height` -- see `intersection_kit.
    build_segment_from_spine`'s `sidewalk_l_width` docstring. Built via `curb_loop(curb_style=
    'PROFILE', asset_obj=sidewalk_*_asset_obj)` from `seg["sidewalks"]`'s already-correctly-offset
    centerline (0 width on a side = no object at all, not just an invisible one) -- the resolved
    kit piece's own cross-section swept continuously, same mechanism as curb/median (2026-08, "may
    you please also do for sidewalk also" -- extends the curb/median PROFILE work to sidewalks;
    `curb_loop` returns `None`/skips the side when no piece resolves, same 'no piece = no
    geometry' convention every PROFILE caller already has).

    `prop_l_asset_obj`/`prop_l_spacing`/`prop_r_asset_obj`/`prop_r_spacing` -- optional per-side
    prop scatter (street lamps, etc.), reusing `kit_common.curb_asset_row` UNCHANGED (it already
    just repeats any given mesh Object along any offset polyline at a fixed spacing with
    per-point heading -- the exact primitive `assemble.py`'s older master-graph pipeline uses for
    its own lamp placement, ported here rather than reinvented). Placed along that side's
    SIDEWALK centerline when a sidewalk is active on that side (so props sit ON the sidewalk, the
    natural spot for a lamp/bench), else along that side's own CURB line (so props still align to
    the street even with no sidewalk at all) -- either way, always the same offset-from-spine
    machinery every other aligned feature here already uses, never a separately-authored line.
    `prop_l_asset_obj=None` (default) = no props on that side, the opt-in the tooltip already
    promises ("not always, but need alignment")."""
    k = ik()
    spine = _spine_control_points(spine_obj)
    _place_segment_ports(coll, spine, lane_width)
    origin_marker = get_or_create_origin_marker(coll, tuple(spine[0]))
    if origin_marker is not None:
        origin_marker.location = spine[0]
    sidewalk_l_offset_w, sidewalk_l_offset_w_end = _sidewalk_offset_width(
        sidewalk_l_width, sidewalk_l_width_end, sidewalk_l_asset_obj)
    sidewalk_r_offset_w, sidewalk_r_offset_w_end = _sidewalk_offset_width(
        sidewalk_r_width, sidewalk_r_width_end, sidewalk_r_asset_obj)
    seg = k.build_segment_from_spine(spine, lane_width, lanes, lanes_backward, segment_id="SEG",
                                      traffic_side=traffic_side, median_width=median_width,
                                      sidewalk_l_width=sidewalk_l_offset_w,
                                      sidewalk_r_width=sidewalk_r_offset_w, lanes_end=lanes_end,
                                      lanes_backward_end=lanes_backward_end, align=align,
                                      median_width_end=median_width_end,
                                      curb_clearance_l=_curb_outer_clearance(
                                          curb_l_style, curb_thickness, curb_asset_obj),
                                      curb_clearance_r=_curb_outer_clearance(
                                          curb_r_style, curb_thickness, curb_asset_obj),
                                      sidewalk_l_width_end=sidewalk_l_offset_w_end,
                                      sidewalk_r_width_end=sidewalk_r_offset_w_end)

    curb_matkey = coll.get("rka_curb_matkey", "concrete")
    visual_objs = [spine_obj]
    left_pts, right_pts = seg["curbs"]
    left_name, right_name = "curb_%s_L" % coll.name, "curb_%s_R" % coll.name
    # `asset_obj=curb_asset_obj` matters for `curb_style == 'PROFILE'` -- see `kit_common.
    # curb_loop`'s own docstring; harmless/unused for NONE. Both sides go through this ONE
    # `curb_loop` call now (2026-08, "only have none/profile... to simplify the code base" --
    # the old `if style == 'ASSET': build_curb(...) else: curb_loop(...)` split retired along
    # with the ASSET style itself; `curb_asset_spacing`/`curb_asset_rot_offset_r` are unused by
    # PROFILE's continuous sweep, kept only as still-valid `build_curb`/`curb_asset_row` args for
    # any direct caller). "-colonly" no longer baked live (2026-08) -- see
    # kit_common.bake_colonly_proxies.
    left = paths.kc.curb_loop(
        left_name, [(p[0], p[1], p[2], 0.0) for p in left_pts], coll,
        curb_style=curb_l_style, curb_height=curb_height, curb_thickness=curb_thickness,
        matkey=curb_matkey, closed=False, asset_obj=curb_asset_obj)
    right = paths.kc.curb_loop(
        right_name, [(p[0], p[1], p[2], 0.0) for p in right_pts], coll,
        curb_style=curb_r_style, curb_height=curb_height, curb_thickness=curb_thickness,
        matkey=curb_matkey, closed=False, asset_obj=curb_asset_obj)
    visual_objs += [o for o in (left, right) if o is not None]

    # Median -- the resolved kit piece's own real cross-section, swept CONTINUOUSLY down the
    # median's own CENTERLINE (2026-08, user-requested: "only have none/profile... to simplify
    # the code base" -- 'PROFILE' replaces the discrete `curb_asset_row` tiled row this used to be,
    # same continuous-sweep mechanism `curb_loop`'s CURB/SIDEWALK callers already use). The
    # centerline is exactly `spine` itself: `build_segment_from_spine` offsets both lane groups
    # outward from the spine by `median_half`, so the spine points ARE the median's centerline
    # already -- no offset-line math needed. Gated on `seg["median_edges"]` being non-empty (the
    # "genuinely active median" check) so a width<=0 median stays a true no-op; `curb_loop` itself
    # handles the "no piece resolved = no geometry" case (`median_asset_obj is None`).
    if median_style == 'PROFILE' and seg["median_edges"]:
        spine4 = [(p[0], p[1], p[2], 0.0) for p in spine]
        med = paths.kc.curb_loop("curb_%s_median" % coll.name, spine4, coll, curb_style='PROFILE',
                                  matkey=curb_matkey, closed=False, asset_obj=median_asset_obj)
        if med is not None:
            visual_objs.append(med)

    # Sidewalk (see this function's own docstring) -- one CONTINUOUS curb_loop(PROFILE) strip per
    # side with a nonzero width, from the already-correctly-offset centerline `build_segment_
    # from_spine` computed (spans exactly curb edge -> sidewalk outer edge, never overlapping the
    # roadway). 2026-08, user-requested ("only have none/profile... to simplify the code base"):
    # collapsed from the earlier procedural-BOX/discrete-ASSET-tiling pair down to just this --
    # PROFILE sweeps the resolved kit piece's own real cross-section CONTINUOUSLY (same mechanism
    # `curb_loop`'s CURB callers use), so a sidewalk follows any corner with zero seams, the same
    # fix that replaced curb's own ASSET tiling. `sidewalk_l_width`/`_r_width` remain the ON/OFF
    # gate (>0 = wanted on this side) and the FIRST-click default-width UX -- the actual swept
    # width always comes from the resolved piece's own real geometry once one is set (see
    # `_sidewalk_offset_width`'s docstring), same as curb's own PROFILE width is asset-driven, not
    # dial-driven. No piece resolved = no geometry (the same "ASSET/PROFILE + unresolved piece =
    # nothing" convention every style like this already has) -- pick one via the Sidewalk Asset
    # dropdown.
    sidewalk_objs = {}
    for side, width, pts, asset_obj in (
            ("L", sidewalk_l_width, seg["sidewalks"]["L"], sidewalk_l_asset_obj),
            ("R", sidewalk_r_width, seg["sidewalks"]["R"], sidewalk_r_asset_obj)):
        if width <= 0.0 or pts is None:
            continue
        line = [(p[0], p[1], p[2], 0.0) for p in pts]
        name = "sidewalk_%s_%s" % (coll.name, side)
        sw = paths.kc.curb_loop(name, line, coll, curb_style='PROFILE', curb_height=sidewalk_height,
                                 curb_thickness=width, matkey=curb_matkey, closed=False,
                                 asset_obj=asset_obj)
        # "-colonly" no longer baked live (2026-08) -- see kit_common.bake_colonly_proxies.
        if sw is not None:
            visual_objs.append(sw)
            sidewalk_objs[side] = sw

    # Props (see this function's own docstring) -- placed along that side's sidewalk line if one
    # is active, else its plain curb line, so a lamp/prop row is always aligned to the street.
    # 2026-08, user-requested streetlight-array rules: R side is STAGGERED half a spacing behind
    # L (`phase_offset`, real-world "alternating sides" convention -- poles don't line up straight
    # across from each other), and any anchor within `STREETLIGHT_EXCLUSION_ZONE` of a nearby
    # intersection's own traffic-light pole/gantry is dropped (`exclude_positions`) so a
    # streetlight never clips a signal pole right at a junction corner.
    nearby_poles = None
    for side, asset_obj, spacing, curb_pts in (
            ("L", prop_l_asset_obj, prop_l_spacing, left_pts),
            ("R", prop_r_asset_obj, prop_r_spacing, right_pts)):
        if asset_obj is None:
            continue
        if nearby_poles is None:
            nearby_poles = _nearby_signal_pole_positions()
        line_pts = seg["sidewalks"][side] if side in sidewalk_objs else curb_pts
        prop_row = paths.kc.curb_asset_row(
            "prop_%s_%s" % (coll.name, side), [(p[0], p[1], p[2], 0.0) for p in line_pts], coll,
            asset_obj, spacing, rot_offset_deg=180.0 if side == "R" else 0.0,
            phase_offset=(spacing / 2.0 if side == "R" else 0.0),
            exclude_positions=nearby_poles, exclude_radius=STREETLIGHT_EXCLUSION_ZONE)
        if prop_row is not None:
            visual_objs.append(prop_row)

    # Pavement collision ("-colonly") no longer baked live here (2026-08) -- see
    # kit_common.bake_colonly_proxies (export-time, `tools/export_world.py`); it identifies the
    # spine via its "Road" GN modifier and applies the SAME `name="pave_<piece>"` override this
    # call used to pass explicitly (the spine object itself is "spine_<piece>", never
    # deleted/recreated by a rebuild -- see that function's own docstring).

    # `lanecl_*` no longer built here (2026-08) -- see ops_intersection.py's matching removal.

    visual_objs = _join_visuals_keeping_spine(context, coll, spine_obj, visual_objs,
                                              join_visual_mesh)

    # Markings are deliberately kept OUT of join_visual_mesh's combine (same rationale
    # kit_common.lane_marking_strip's docstring already gives for Tier-1 seam marking: separate
    # objects can later be swapped for a dashed/textured decal without touching lane geometry) --
    # added to visual_objs AFTER the join so gltf_export_path still exports them.
    median_half_start = median_width / 2.0 if (median_width > 0.0 and lanes > 0
                                                and lanes_backward > 0) else 0.0
    lanes_end_eff = lanes if lanes_end is None else lanes_end
    lanes_backward_end_eff = lanes_backward if lanes_backward_end is None else lanes_backward_end
    median_width_end_eff = median_width if median_width_end is None else median_width_end
    median_half_end = median_width_end_eff / 2.0 if (median_width_end_eff > 0.0
        and lanes_end_eff > 0 and lanes_backward_end_eff > 0) else 0.0
    visual_objs += _populate_lane_markings(
        context, coll, spine, lane_width, lanes, lanes_backward, traffic_side,
        auto_lane_markings=auto_lane_markings, marking_gaps=marking_gaps,
        median_half_start=median_half_start, median_half_end=median_half_end,
        profile_set=profile_set)

    return visual_objs


#: `lane_profile` mark type -> (material key, dashed?, how many parallel lines).
_MARK_STYLE = {
    "DASH_W":   ("line_w", True,  1),
    "SOLID_W":  ("line_w", False, 1),
    "DASH_Y":   ("line_y", True,  1),
    "SOLID_Y":  ("line_y", False, 1),
    "DOUBLE_Y": ("line_y", False, 2),
}


def _profile_lane_markings(spine, profile_set, traffic_side, marking_width):
    """Lane-boundary lines read off the PROFILE instead of the scalar lane counts.

    WHY THIS PATH EXISTS. `intersection_kit.build_segment_lane_markings` derives boundaries from
    `lanes`/`lanes_backward` -- one solid line at the fwd/rev divide, one dashed line per internal
    boundary of each direction's block. That is exactly right for a piece whose cross-section is
    one constant lane count, and blind to everything else. Measured on the rebuilt
    `LOOP_A_carriageway_001` (2 mainline lanes plus six interchanges' auxiliary lanes and gores):
    it emitted ONE dashed line, at the B0|B1 boundary, and nothing whatever for any exit lane or
    painted nose. The boundaries it cannot see are precisely the ones an interchange is made of.

    `lane_profile.marking_runs` instead treats a boundary as a SLOT PROPERTY (`Slot.mark_left`)
    sampled per station, so a line that appears when a ramp lane opens, tracks it outward, and
    ends when the ramp departs is the same mechanism as the lane itself. Each run carries its own
    per-point offsets and its own live index range, which become one ribbon each via
    `offset_spine_line_varying` -- the same primitive every lane centreline and curb already uses,
    so a marking cannot drift from the lane it divides.

    Returns the same `[{'kind', 'points'}]` shape the scalar builder does, so the caller's ribbon
    loop is unchanged."""
    lpm = lp()
    fracs = ik().arc_length_fractions(spine)
    out = []
    for run in lpm.marking_runs(profile_set, len(spine), fractions=fracs):
        style = _MARK_STYLE.get(run["mark"])
        if style is None:
            continue
        matkey, dashed, count = style
        # A double line is two parallel ribbons a marking-width apart, straddling the boundary;
        # a single one sits on it.
        shifts = ([-marking_width, marking_width] if count == 2 else [0.0])
        for sh in shifts:
            offs = [o + sh for o in run["offsets"]]
            line = ik().offset_spine_line_varying(spine, offs, traffic_side)
            # Only the stretch where the boundary actually separates two pieces of road.
            seg = line[run["i0"]:run["i1"] + 1]
            if len(seg) >= 2:
                out.append({"kind": matkey, "dashed": dashed, "points": seg})
    return out


def _populate_lane_markings(context, coll, spine, lane_width, lanes, lanes_backward, traffic_side,
                             auto_lane_markings=True, marking_gaps=None, median_half_start=0.0,
                             median_half_end=0.0, profile_set=None):
    """mark_* objects (dashed white internal-lane boundaries + a solid yellow forward/backward
    boundary, see `intersection_kit.build_segment_lane_markings`/`kit_common.marking_ribbon`) for
    one segment's spine. `marking_gaps` -- see `RKA_OT_add_marking_gap` -- is a list of
    `(t0, t1)` normalized-arc-length exclusion ranges (persisted as the segment Collection's
    `rka_marking_gaps` custom property) so a manually-cleared stretch (a driveway crossing, a
    merge zone) SURVIVES the addon's delete-and-rebuild-from-scratch live-edit cycle instead of
    reappearing on the next drag -- see `rebuild_segment_gn_in_place`, which reads it back off
    `coll` and passes it here; a fresh build has none yet, so it defaults to empty. A no-op
    (returns []) when `auto_lane_markings` is False.

    `median_half_start`/`median_half_end` -- see `intersection_kit.build_segment_lane_markings`'s
    own docstring -- suppress the redundant/physically-wrong "yellow" centerline wherever a real
    median separator exists, and keep the internal white boundary lines tracking the median's own
    taper (2026-08, user-reported: a solid yellow line painted straight through a raised median)."""
    if not auto_lane_markings:
        return []
    rka = context.scene.rka
    gaps = list(marking_gaps or [])
    if profile_set is not None:
        markings = _profile_lane_markings(spine, profile_set, traffic_side,
                                          rka.lane_marking_width)
    else:
        markings = ik().build_segment_lane_markings(
            spine, lane_width, lanes, lanes_backward, traffic_side,
            median_half_start=median_half_start, median_half_end=median_half_end)
    objs = []
    for i, m in enumerate(markings):
        # The scalar builder labels a line by COLOUR ("yellow"/"white") and infers dashing from
        # it; the profile builder names the material directly and says whether it is dashed,
        # because a profile has both a solid white gore edge and a dashed white lane line and the
        # colour alone can no longer decide.
        if "dashed" in m:
            matkey, dashed = m["kind"], m["dashed"]
        else:
            matkey = "line_y" if m["kind"] == "yellow" else "line_w"
            dashed = (m["kind"] != "yellow")
        dash_len = rka.marking_dash_length if dashed else 0.0
        gap_len = rka.marking_gap_length if dashed else 0.0
        obj = paths.kc.marking_ribbon(
            "mark_%s_%s_%d" % (coll.name, matkey, i), m["points"], rka.lane_marking_width / 2.0,
            coll, matkey, dash_len=dash_len, gap_len=gap_len, exclude_ranges=gaps)
        if obj is not None:
            objs.append(obj)
    return objs


SPINE_MIN_SPACING = 1e-4      # metres; below this two points are the same point


def _dedupe_spine_points(pts, tol=SPINE_MIN_SPACING):
    """Drop consecutive coincident points from a spine path, in XY.

    XY, not XYZ, deliberately: two points at the same XY but different Z are still a zero-length
    step as far as the horizontal tangent is concerned, and the horizontal tangent is what the
    cross-section frame is built from. A purely vertical 'segment' in a road spine is never
    intended anyway -- a road that climbs does so along its length."""
    if not pts:
        return []
    out = [tuple(pts[0])]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(tuple(p))
    return out


def segment_profile_set(lane_width, lanes, lanes_backward, lanes_end=None,
                        lanes_backward_end=None, median_width=0.0, median_width_end=None,
                        sidewalk_l_width=0.0, sidewalk_r_width=0.0,
                        sidewalk_l_width_end=None, sidewalk_r_width_end=None, profile_set=None):
    """The piece's cross-section as a `ProfileSet`, from an authored one if it has one and from the
    legacy scalars otherwise.

    ONE STATION OR TWO. A piece whose `_end` scalars all match its start scalars is a constant
    cross-section and gets a single station. As soon as ANY of them differs, it gets two, and
    `ProfileSet.interpolate` carries every slot between them -- which is what makes a taper an
    ordinary piece rather than a separate `Transition_*` collection with its own builder. This is
    `ROAD_KIT_REDESIGN.md` §2.1's "`interpolate()` subsumes every `_end` scalar", and until this
    existed the stack path read the START scalars only and silently built a constant-width road
    where the user had asked for a taper.

    An explicitly authored `profile_set` always wins: it can express things no pair of scalar
    endpoints can (a gore opening at a mid-piece station), so it must never be re-derived from
    them."""
    if profile_set is not None:
        return profile_set
    lanes_end_eff = lanes if lanes_end is None else lanes_end
    lanes_backward_end_eff = lanes_backward if lanes_backward_end is None else lanes_backward_end
    median_end_eff = median_width if median_width_end is None else median_width_end
    sw_l_end_eff = sidewalk_l_width if sidewalk_l_width_end is None else sidewalk_l_width_end
    sw_r_end_eff = sidewalk_r_width if sidewalk_r_width_end is None else sidewalk_r_width_end

    start = lp().profile_from_scalars(
        lanes, lanes_backward, lane_width, median_width=median_width,
        sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width)
    tapers = (lanes_end_eff != lanes or lanes_backward_end_eff != lanes_backward
              or median_end_eff != median_width or sw_l_end_eff != sidewalk_l_width
              or sw_r_end_eff != sidewalk_r_width)
    if not tapers:
        return lp().ProfileSet([start])
    end = lp().profile_from_scalars(
        lanes_end_eff, lanes_backward_end_eff, lane_width, median_width=median_end_eff,
        sidewalk_l_width=sw_l_end_eff, sidewalk_r_width=sw_r_end_eff)
    return lp().ProfileSet([start, end])


def apply_segment_stack(coll, spine_obj, lane_width, lanes, lanes_backward,
                        lanes_end=None, lanes_backward_end=None,
                        curb_l_style='NONE', curb_r_style='NONE', curb_height=0.15,
                        curb_thickness=0.25, traffic_side='LEFT',
                        median_width=0.0, median_style='NONE', median_width_end=None,
                        sidewalk_l_width=0.0, sidewalk_r_width=0.0, sidewalk_height=0.15,
                        sidewalk_l_width_end=None, sidewalk_r_width_end=None,
                        sidewalk_l_asset_collection="", sidewalk_r_asset_collection="",
                        prop_l_asset_collection="", prop_l_spacing=30.0,
                        prop_r_asset_collection="", prop_r_spacing=30.0,
                        profile_set=None):
    """(Re)build `spine_obj`'s whole modifier stack from the piece's parameters.

    THE SINGLE OWNER of "what layers does this piece have", called by BOTH the initial build
    (`_build_segment_from_points`) and every live edit (`rebuild_segment_gn_in_place`). Keeping
    them one function is not tidiness -- a build path and a rebuild path that each derive the
    cross-section separately is `ROAD_KIT_REDESIGN.md` defect 1, and it has already bitten twice in
    this file (the two-direction carriageway swept onto one side, and lane markings that come out
    single-yellow on build and double-yellow on rebuild).

    Idempotent, because a rebuild runs it over a carrier that already has a stack: `build_stack`
    replaces the modifier list wholesale and `layers_for_segment` rewrites every per-point
    attribute, so calling it twice with the same parameters leaves the same road. The carrier
    object itself is never deleted or recreated -- that is what makes a live drag safe, and it is
    the same guarantee the Curve spine already had.

    Curb / sidewalk / median profiles resolve to `None` when that part is absent, and
    `layers_for_segment` then omits the layer entirely -- so "no curb" is the absence of a modifier
    rather than a modifier that produces nothing."""
    import road_stack as _rs
    from . import segment_stack as _ss

    ps_eff = segment_profile_set(
        lane_width, lanes, lanes_backward, lanes_end=lanes_end,
        lanes_backward_end=lanes_backward_end, median_width=median_width,
        median_width_end=median_width_end, sidewalk_l_width=sidewalk_l_width,
        sidewalk_r_width=sidewalk_r_width, sidewalk_l_width_end=sidewalk_l_width_end,
        sidewalk_r_width_end=sidewalk_r_width_end, profile_set=profile_set)

    curb_l = _ss.curb_profile_object(curb_l_style, curb_height, curb_thickness)
    curb_r = _ss.curb_profile_object(curb_r_style, curb_height, curb_thickness)
    # A SIDEWALK NEEDS A RESOLVED KIT PIECE, not just a width. `sidewalk_*_width` is the on/off
    # gate and the first-click default; the geometry comes from the asset (see
    # `_populate_segment_mesh_gn`'s sidewalk block -- "no piece resolved = no geometry", the same
    # convention curb and median PROFILE styles already follow). Building a plain slab from the
    # width alone here would have made the stack path quietly disagree with the sibling path about
    # when a sidewalk exists, which is the two-models class of defect this migration exists to end.
    sw_l = (_ss.sidewalk_profile_object(sidewalk_l_width, sidewalk_height)
            if _resolve_curb_asset(sidewalk_l_asset_collection) is not None else None)
    sw_r = (_ss.sidewalk_profile_object(sidewalk_r_width, sidewalk_height)
            if _resolve_curb_asset(sidewalk_r_asset_collection) is not None else None)
    med = _ss.median_profile_object(median_width if median_style != 'NONE' else 0.0, curb_height)

    _rs.build_stack(spine_obj, _ss.layers_for_segment(
        spine_obj, ps_eff, traffic_side=traffic_side,
        # Both matkeys are read off the collection, exactly as the sibling-object builder reads
        # them -- otherwise `Set Curb Material` writes `rka_curb_matkey` and the road never
        # changes colour, which is the "stored and ignored" failure `RKA_OT_set_curb_matkey` was
        # written to fix in the first place.
        curb_matkey=coll.get("rka_curb_matkey", "concrete"),
        curb_l_profile=curb_l, curb_r_profile=curb_r, median_profile=med,
        sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width,
        sidewalk_l_profile=sw_l, sidewalk_r_profile=sw_r,
        curb_clearance_l=curb_thickness / 2.0, curb_clearance_r=curb_thickness / 2.0,
        prop_l_asset=_resolve_curb_asset(prop_l_asset_collection), prop_l_spacing=prop_l_spacing,
        prop_r_asset=_resolve_curb_asset(prop_r_asset_collection), prop_r_spacing=prop_r_spacing,
        pave_matkey=coll.get("rka_pave_matkey", "asphalt"), mat=paths.kc.mat))
    return ps_eff


def _build_segment_from_points(context, parent_coll, pts, lane_width, lanes, lanes_backward,
                                curb_l_style, curb_r_style, curb_height, curb_thickness,
                                join_visual_mesh, export_path, gltf_export_path,
                                base_name="Segment", traffic_side='LEFT',
                                curb_asset_collection="", curb_asset_spacing=2.0,
                                curb_asset_rot_offset_r=180.0, auto_lane_markings=True,
                                median_width=0.0, median_style='NONE',
                                median_asset_collection="", median_asset_spacing=2.0,
                                sidewalk_l_width=0.0, sidewalk_r_width=0.0, sidewalk_height=0.15,
                                sidewalk_l_asset_collection="", sidewalk_r_asset_collection="",
                                sidewalk_asset_spacing=2.0,
                                prop_l_asset_collection="", prop_l_spacing=30.0,
                                prop_r_asset_collection="", prop_r_spacing=30.0,
                                lanes_end=None, lanes_backward_end=None, align='right',
                                median_width_end=None, sidewalk_l_width_end=None,
                                sidewalk_r_width_end=None, profile_set=None,
                                link_group="", link_role="", link_next_group=""):
    """Shared core behind BOTH `RKA_OT_build_straight_segment` (`pts` from p0/p1/bend, via
    `intersection_kit.segment_spine_3d`) and `RKA_OT_build_segment_from_curve` (`pts` sampled ONCE
    from an externally authored curve, to seed this new self-contained spine) -- a NEW collection
    with a live GN-backed spine (`kit_common.road_spine`) through `pts`, plus curb/lanecl_*
    (`_populate_segment_mesh_gn`). One code path for both operators, so they can never drift
    apart. `pts` are already-absolute `(x, y, z)` world points (>= 2). `lanes`/`lanes_backward` --
    see `intersection_kit.build_segment_from_spine` -- may not both be 0.

    `median_width`/`median_style` -- see `intersection_kit.build_segment_from_spine`'s
    `median_width` docstring -- default 0.0/no median, fully back-compatible.

    `lanes_end`/`lanes_backward_end`/`align`/`median_width_end`/`sidewalk_*_width_end` -- see
    `intersection_kit.build_segment_from_spine`'s taper docstring (this is the unification of the
    formerly-separate "Build Lane Transition" tool -- a taper is now just these fields left
    non-default on the same segment builder). `half_w_start`/`half_w_end` (below, sizing the
    single continuous `road_spine` pavement sweep) mirror that function's own median-half
    calculation at EACH end exactly, since they must be computed here BEFORE
    `build_segment_from_spine` runs (the spine object has to exist first -- `_populate_segment_mesh_gn`
    calls `build_segment_from_spine` itself, later, for the curb/lane/median-edge data) -- when
    they're equal, `road_spine` gets one plain scalar radius (byte-identical to before tapering
    existed); when they differ, `intersection_kit.tapered_scalars` gives it the matching per-point
    radius list, tapering the pavement in exact lockstep with the curbs it's built from."""
    # DEGENERATE POINTS ARE REMOVED HERE, at the single shared entry, not by each caller.
    #
    # A zero-length segment has no defined tangent, and EVERYTHING downstream derives its frame
    # from the tangent -- the spine's normal, the swept cross-section, the curb offsets, the lane
    # centerlines. One repeated point makes that frame flip, and the road visibly twists at the
    # spot, usually an end where it is most obvious. It never raises; it just builds something
    # wrong-looking, which is the worst kind of failure to debug from the viewport.
    #
    # Every producer can emit one: a hand-authored curve with a double-clicked control point, a
    # generator whose lead-in point coincides with its first sampled point, a closed ring carrying
    # a repeated closing vertex. Guarding at each of those means remembering the rule forever, so
    # the guard lives here instead -- every segment in this addon goes through this function.
    pts = _dedupe_spine_points(pts)
    if len(pts) < 2:
        raise RkaBuildError("a segment needs at least 2 distinct points (got %d after removing "
                             "coincident ones -- is the whole path a single repeated point?)"
                             % len(pts))
    if lanes <= 0 and lanes_backward <= 0:
        raise RkaBuildError("a segment needs at least one lane in SOME direction "
                             "(lanes=%d, lanes_backward=%d)" % (lanes, lanes_backward))
    lanes_end_eff = lanes if lanes_end is None else lanes_end
    lanes_backward_end_eff = lanes_backward if lanes_backward_end is None else lanes_backward_end
    if lanes_end_eff <= 0 and lanes_backward_end_eff <= 0:
        raise RkaBuildError("the END of a segment needs at least one lane in SOME direction "
                             "(lanes_end=%d, lanes_backward_end=%d)" %
                             (lanes_end_eff, lanes_backward_end_eff))
    median_width_end_eff = median_width if median_width_end is None else median_width_end

    median_half = median_width / 2.0 if (median_width > 0.0 and lanes > 0 and lanes_backward > 0) \
        else 0.0
    median_half_end = median_width_end_eff / 2.0 if (median_width_end_eff > 0.0
        and lanes_end_eff > 0 and lanes_backward_end_eff > 0) else 0.0
    # ASYMMETRIC carriageway -- see `intersection_kit.carriageway_extents`/`sweep_radius_and_shift`
    # and `kit_common.make_road_profile_group`. `half_w`/`half_w_end` stay the SWEEP RADIUS (so the
    # existing `tapered_scalars` per-point taper is untouched); the asymmetry rides in the two
    # profile fractions, which is why a one-way road no longer sweeps an empty mirror carriageway.
    neg_w, pos_w = ik().carriageway_extents(lanes, lanes_backward, lane_width, median_half)
    neg_w_end, pos_w_end = ik().carriageway_extents(lanes_end_eff, lanes_backward_end_eff,
                                                     lane_width, median_half_end)
    half_w, _shift = ik().sweep_radius_and_shift(neg_w, pos_w)
    half_w_end, _shift_end = ik().sweep_radius_and_shift(neg_w_end, pos_w_end)
    pave_radius = half_w if half_w_end == half_w else ik().tapered_scalars(pts, half_w, half_w_end)
    if profile_set is not None:
        # A ProfileSet describes the cross-section PER STATION, so the sweep radius becomes a
        # per-point list read straight off it instead of a two-endpoint blend. This is what lets
        # ONE piece carry a trunk that widens to an auxiliary lane and then reaches a gore --
        # three pieces (`trunk_before`/`trunk_taper`/`trunk_aux`) in the scalar model, because a
        # piece could only ever hold one lane COUNT.
        #
        # Only the RADIUS varies here, not the neg:pos ratio, and that is exactly right for the
        # pieces that use this: every split/merge piece is one-way (`lanes_backward=0`), so
        # `carriageway_extents` gives `(0, pos)` at every station and the ratio is the constant
        # `(2, 0)` however the width changes. A profile whose asymmetry genuinely varies along the
        # piece needs the per-point `rka_shift` attribute of `road_stack`'s mesh carrier -- that
        # is the modifier-stack path, and it is why the carrier had to stop being a Curve.
        pave_radius = [(lambda ex: (ex[0] + ex[1]) / 2.0)(lp().paved_extents(prof))
                       for prof in profile_set.sample_at(ik().arc_length_fractions(pts))]
    # Fractions of radius, so they are taper-invariant whenever the neg:pos RATIO is constant --
    # true for every one-way road and every fixed-asymmetry road, including under a lane-count
    # taper. Taken at the start station (the ratio only differs end-to-end if a taper also flips
    # which direction is busier, e.g. 3+0 -> 2+2, which the profile rewrite handles properly).
    # `sweep_profile_fracs` (not a bare division) also applies the GN-frame axis flip -- see it.
    pave_neg_frac, pave_pos_frac = ik().sweep_profile_fracs(neg_w, pos_w, traffic_side)
    if profile_set is not None:
        # THE PROFILE OWNS THE RATIO TOO, not just the radius. Deriving the neg:pos split from the
        # scalar `lanes`/`lanes_backward` while the width comes from the profile is exactly the
        # two-conventions-for-one-cross-section defect this module exists to prevent -- and it bit:
        # a TWO-DIRECTION carriageway built with `lanes_backward=0` swept its whole width onto one
        # side of the spine, so one direction had no pavement at all while the other sat offset.
        #
        # Taken at the BASE station (no auxiliary lane open), which is symmetric for a two-way road
        # and therefore the ratio the road holds for most of its length. A piece whose asymmetry
        # genuinely VARIES along it -- aux lanes opening on either side of a divided highway --
        # needs the per-point `rka_shift` attribute of `road_stack`'s mesh carrier, since a Curve
        # spine can carry one scalar ratio and no more. That is the modifier-stack path
        # (ROAD_KIT_REDESIGN.md step 4); until then the base ratio is the honest approximation.
        _neg, _pos = lp().paved_extents(profile_set.at(0.0))
        if _neg + _pos > 0.0:
            pave_neg_frac, pave_pos_frac = ik().sweep_profile_fracs(_neg, _pos, traffic_side)

    n = 1
    # local_collection (not a bare name-in-bpy.data.collections test) so a linked neighbor's
    # same-numbered piece never perturbs local auto-numbering -- see its docstring.
    while local_collection(base_name + ("_%03d" % n)) is not None:
        n += 1
    coll = bpy.data.collections.new(base_name + ("_%03d" % n))
    parent_coll.children.link(coll)
    # Same visible/clickable "grab the whole piece from here" anchor RKA_OT_build_intersection
    # gives every intersection -- see get_or_create_origin_marker's docstring. Purely a UX handle
    # for a plain/curve segment: the geometry itself already re-derives from the SPINE object's
    # own live matrix_world (_spine_control_points), so nothing downstream reads this marker's
    # position for math -- it exists so Freeze For Move / Unfreeze & Rebuild / Rebuild From
    # Handles have an obvious, consistently-named target to click, instead of relying on the user
    # finding the (often curb-occluded) spine curve itself. Re-snapped to the spine's current
    # start point on every rebuild (see rebuild_segment_gn_in_place).
    get_or_create_origin_marker(coll, tuple(pts[0]))

    # coll.get(...) here is always the "asphalt" default at fresh-build time (coll is brand new,
    # no custom props yet) -- see RKA_OT_set_piece_matkey/set_road_spine_material for the
    # after-the-fact change path (this object's own material can't just be re-derived on rebuild
    # like curb/lane data, since the spine itself is never deleted/recreated).
    # THE MODIFIER-STACK PATH (`ROAD_KIT_REDESIGN.md` step 4). One carrier object whose whole
    # road is its modifier stack, instead of a swept Curve plus a family of Python-owned sibling
    # meshes. The carrier is a MESH polyline because only a mesh can hold the per-vertex
    # cross-section attributes that let the profile vary along the piece -- a Curve datablock has
    # no `.attributes` at all.
    #
    # This also ends the two-models problem: the ProfileSet is the ONLY description of the
    # cross-section, so there is no scalar twin to disagree with it (the bug where the profile set
    # the sweep's width while `lanes_backward` set its left/right split, and a two-direction
    # carriageway came out entirely on one side of its spine).
    import road_stack as _rs
    spine_obj = _rs.make_spine_mesh("spine_%s" % coll.name, pts, coll)
    stack_profile_set = apply_segment_stack(
        coll, spine_obj,
        lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        lanes_end=lanes_end, lanes_backward_end=lanes_backward_end,
        curb_l_style=curb_l_style, curb_r_style=curb_r_style, curb_height=curb_height,
        curb_thickness=curb_thickness, traffic_side=traffic_side,
        median_width=median_width, median_style=median_style,
        median_width_end=median_width_end,
        sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width,
        sidewalk_height=sidewalk_height,
        sidewalk_l_width_end=sidewalk_l_width_end,
        sidewalk_r_width_end=sidewalk_r_width_end,
        sidewalk_l_asset_collection=sidewalk_l_asset_collection,
        sidewalk_r_asset_collection=sidewalk_r_asset_collection,
        prop_l_asset_collection=prop_l_asset_collection, prop_l_spacing=prop_l_spacing,
        prop_r_asset_collection=prop_r_asset_collection, prop_r_spacing=prop_r_spacing,
        profile_set=profile_set)
    # Ports are how every other piece attaches to this one, so they are part of BUILDING a
    # segment, not part of populating sibling meshes -- they only ever lived inside
    # `_populate_segment_mesh_gn` because that used to be the one place a segment got built.
    # A piece without them cannot be linked to an arm or to another segment at all.
    _place_segment_ports(coll, pts, lane_width)

    visual_objs = []
    if auto_lane_markings:
        # Markings are still separate objects (see `_populate_lane_markings`) -- the one part of a
        # segment the modifier stack does not own, because a dashed line is discrete geometry
        # rather than a swept profile.
        #
        # `stack_profile_set`, NOT the caller's `profile_set`, and that difference is a bug fix.
        # `profile_set` is None for a piece described by plain scalars, which sent the BUILD down
        # `build_segment_lane_markings` (scalar) while every later REBUILD went down
        # `_profile_lane_markings` (profile) -- because `custom_props.read_profile` SYNTHESIZES a
        # ProfileSet from those same scalars when none is stored. The two disagree (a two-way
        # centreline comes out single-solid from one and DOUBLE_Y from the other), so a road
        # changed appearance the first time it was dragged. Handing the markings the same
        # ProfileSet the stack itself was built from makes build and rebuild the same operation.
        visual_objs += _populate_lane_markings(
            context, coll, pts, lane_width, lanes, lanes_backward, traffic_side,
            auto_lane_markings=True, marking_gaps=None, profile_set=stack_profile_set)

    # rka_p0/p1 (first/last point) are an approximation for anything downstream expecting the old
    # 2-point model (e.g. RKA_OT_insert_intersection_on_segment) -- accurate for a straight/gently
    # bent segment, an approximation (ignores intermediate points) for a heavily curved one; that
    # operator's own straight-line splice logic was never curve-aware in the first place.
    custom_props.write_build_settings(
        coll, lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        curb_l_style=curb_l_style, curb_r_style=curb_r_style, curb_height=curb_height,
        curb_thickness=curb_thickness, curve_object=spine_obj.name, traffic_side=traffic_side,
        curb_asset_collection=curb_asset_collection or None, curb_asset_spacing=curb_asset_spacing,
        curb_asset_rot_offset_r=curb_asset_rot_offset_r, auto_lane_markings=auto_lane_markings,
        median_width=median_width, median_style=median_style,
        median_asset_collection=median_asset_collection or None,
        median_asset_spacing=median_asset_spacing,
        sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width,
        sidewalk_height=sidewalk_height,
        sidewalk_l_asset_collection=sidewalk_l_asset_collection or None,
        sidewalk_r_asset_collection=sidewalk_r_asset_collection or None,
        sidewalk_asset_spacing=sidewalk_asset_spacing,
        prop_l_asset_collection=prop_l_asset_collection or None,
        prop_l_spacing=prop_l_spacing, prop_r_asset_collection=prop_r_asset_collection or None,
        prop_r_spacing=prop_r_spacing, lanes_end=lanes_end, lanes_backward_end=lanes_backward_end,
        align=align, median_width_end=median_width_end, sidewalk_l_width_end=sidewalk_l_width_end,
        sidewalk_r_width_end=sidewalk_r_width_end,
        p0=list(pts[0]), p1=list(pts[-1]))
    # The profile is the piece's real cross-section description; the scalars above are written
    # alongside it only so anything not yet ported off them still reads something sane. When both
    # are present `custom_props.read_profile` returns THIS, not the scalars.
    if profile_set is not None:
        custom_props.write_profile(coll, profile_set)
    # A piece that is one part of a multi-piece structure (a split's trunk and its two branches)
    # records the structure it belongs to and its role in it. That is what lets the exporter emit
    # EXPLICIT connectivity -- "this trunk lane continues into that branch's lane of the same slot
    # id" -- instead of leaving the runtime to infer everything from endpoint proximity, which
    # cannot distinguish a mainline continuing from a ramp peeling off, and cannot see a lane
    # change at all.
    if link_group:
        coll["rka_link_group"] = link_group
        coll["rka_link_role"] = link_role
    # Where this piece hands over to a DIFFERENT structure. Needed when two interchanges are so
    # close that no ordinary road is built between them (their approach footprints overlap), so
    # there is no intermediate piece for endpoint proximity to join through -- see
    # `island_v3_to_roadkit.interchange_reservations`.
    if link_next_group:
        coll["rka_link_next_group"] = link_next_group

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
    them in Edit Mode is editing this exact list, so no resampling technique is needed at all.

    Carrier-agnostic since the `road_stack` rework: a spine may be the legacy POLY Curve or the
    MESH polyline the modifier stack uses (a Curve datablock cannot hold the per-point
    cross-section attributes -- see `spine_io`). Both answer here identically."""
    return spine_io.world_points(spine_obj)


def _resolve_curve_object(context, name):
    """The Curve object `RKA_OT_build_segment_from_curve` should follow: by explicit `name` if
    given, else the active object if it's a Curve. None if neither resolves."""
    if name:
        obj = local_object(name)
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
        name="Lanes Forward", default=1, min=0, max=4,
        description="Lane count in the curve's own direction (start -> end). 0 is only valid if "
                     "Lanes Backward is nonzero")
    lanes_backward: bpy.props.IntProperty(
        name="Lanes Backward", default=1, min=0, max=4,
        description="Lane count against the curve's direction (end -> start). 0 makes this a "
                     "ONE-WAY road")
    lanes_end: bpy.props.IntProperty(
        name="Lanes Forward (End)", default=-1, min=-1, max=4,
        description="-1 (default) = same as Lanes Forward -- see 'Build Straight Segment's own "
                     "Lanes Forward (End) tooltip")
    lanes_backward_end: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=-1, min=-1, max=4)
    align: bpy.props.EnumProperty(
        name="Taper Align", items=(
            ('right', "Right (curb-side continues)", ""), ('left', "Left (median-side continues)", ""),
        ), default='right')
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Linked kit/curb_kit.blend collection's mesh "
        "object, when a Curb Style above is 'Asset'", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    curb_asset_rot_offset_r: bpy.props.FloatProperty(
        name="Curb Asset R-Side Rotation Offset", default=180.0)
    traffic_side: bpy.props.EnumProperty(name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    median_width: bpy.props.FloatProperty(
        name="Median Width", default=0.0, min=0.0, unit='LENGTH',
        description="Extra gap (m) between forward/backward lanes -- see 'Build Straight "
                     "Segment's own Median Width tooltip")
    median_style: bpy.props.EnumProperty(
        name="Median Style", items=MEDIAN_STYLE_ITEMS, default='NONE',
        description="Ignored when Median Width is 0")
    median_asset_collection: bpy.props.StringProperty(name="Median Asset Piece", default="")
    median_asset_spacing: bpy.props.FloatProperty(
        name="Median Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    median_width_end: bpy.props.FloatProperty(
        name="Median Width (End)", default=-1.0, min=-1.0, unit='LENGTH')
    sidewalk_l_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Left)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_r_width: bpy.props.FloatProperty(
        name="Sidewalk Width (Right)", default=0.0, min=0.0, unit='LENGTH')
    sidewalk_l_width_end: bpy.props.FloatProperty(
        name="Sidewalk Width (Left, End)", default=-1.0, min=-1.0, unit='LENGTH')
    sidewalk_r_width_end: bpy.props.FloatProperty(
        name="Sidewalk Width (Right, End)", default=-1.0, min=-1.0, unit='LENGTH')
    sidewalk_height: bpy.props.FloatProperty(
        name="Sidewalk Height", default=0.15, min=0.01, unit='LENGTH')
    sidewalk_l_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Left)", default="")
    sidewalk_r_asset_collection: bpy.props.StringProperty(
        name="Sidewalk Asset (Right)", default="")
    sidewalk_asset_spacing: bpy.props.FloatProperty(
        name="Sidewalk Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    prop_l_asset_collection: bpy.props.StringProperty(name="Prop Asset (Left)", default="")
    prop_l_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Left)", default=30.0, min=0.5, unit='LENGTH')
    prop_r_asset_collection: bpy.props.StringProperty(name="Prop Asset (Right)", default="")
    prop_r_spacing: bpy.props.FloatProperty(
        name="Prop Spacing (Right)", default=30.0, min=0.5, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    auto_lane_markings: bpy.props.BoolProperty(
        name="Auto Lane Markings", default=True,
        description="Generate dashed white internal-lane boundaries and a solid yellow "
                     "forward/backward boundary automatically")
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        return _resolve_curve_object(context, "") is not None

    def invoke(self, context, event):
        self.traffic_side = context.scene.rka.default_traffic_side
        return self.execute(context)

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
                traffic_side=self.traffic_side, curb_asset_collection=self.curb_asset_collection,
                curb_asset_spacing=self.curb_asset_spacing,
                curb_asset_rot_offset_r=self.curb_asset_rot_offset_r,
                auto_lane_markings=self.auto_lane_markings,
                median_width=self.median_width, median_style=self.median_style,
                median_asset_collection=self.median_asset_collection,
                median_asset_spacing=self.median_asset_spacing,
                sidewalk_l_width=self.sidewalk_l_width, sidewalk_r_width=self.sidewalk_r_width,
                sidewalk_height=self.sidewalk_height,
                sidewalk_l_asset_collection=self.sidewalk_l_asset_collection,
                sidewalk_r_asset_collection=self.sidewalk_r_asset_collection,
                sidewalk_asset_spacing=self.sidewalk_asset_spacing,
                prop_l_asset_collection=self.prop_l_asset_collection,
                prop_l_spacing=self.prop_l_spacing,
                prop_r_asset_collection=self.prop_r_asset_collection,
                prop_r_spacing=self.prop_r_spacing,
                lanes_end=_taper_end(self.lanes_end),
                lanes_backward_end=_taper_end(self.lanes_backward_end), align=self.align,
                median_width_end=_taper_end(self.median_width_end),
                sidewalk_l_width_end=_taper_end(self.sidewalk_l_width_end),
                sidewalk_r_width_end=_taper_end(self.sidewalk_r_width_end))
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


@live_edit.rebuilding()
def _rebuild_segment_stack_in_place(context, coll, spine_obj, spine):
    """Re-derive a MODIFIER-STACK piece's road from its stored parameters, in place.

    The stack path's counterpart to `clear_generated_mesh_objects` + `_populate_segment_mesh_gn`,
    and much smaller than either, which is the point of the migration: there are no sibling objects
    whose lifetime has to be reconciled, so "rebuild" is "rewrite the per-point attributes and the
    modifier list". `apply_segment_stack` does both, and the carrier object survives untouched.

    MARKINGS ARE STILL SEPARATE OBJECTS on both paths (see `_populate_lane_markings`), so they --
    and only they -- are cleared and regenerated the old way. Without this a piece dragged from
    40 m to 80 m kept its 40 m centreline, floating over the second half of a road that had
    already followed the spine correctly."""
    clear_generated_mesh_objects(coll, keep_gn_boundaries=True)
    profile_set = custom_props.read_profile(coll)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    lane_width = coll.get("rka_lane_width", 5.0)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    # Re-snap the end markers to the spine's CURRENT endpoints. They are how every other piece
    # attaches to this one -- `extend_from_port`, `connect_markers`, and the whole joint-sync
    # chain in `live_edit` find a segment through its ports -- so a piece without them is
    # unlinkable, and one whose ports lag behind a drag links to where the road used to be.
    _place_segment_ports(coll, spine, lane_width)
    apply_segment_stack(
        coll, spine_obj,
        lane_width=lane_width, lanes=lanes, lanes_backward=lanes_backward,
        lanes_end=coll.get("rka_lanes_end", None),
        lanes_backward_end=coll.get("rka_lanes_backward_end", None),
        curb_l_style=coll.get("rka_curb_l_style", coll.get("rka_curb_style", 'NONE')),
        curb_r_style=coll.get("rka_curb_r_style", coll.get("rka_curb_style", 'NONE')),
        curb_height=coll.get("rka_curb_height", 0.15),
        curb_thickness=coll.get("rka_curb_thickness", 0.25),
        traffic_side=traffic_side,
        median_width=coll.get("rka_median_width", 0.0),
        median_style=coll.get("rka_median_style", "NONE"),
        median_width_end=coll.get("rka_median_width_end", None),
        sidewalk_l_width=coll.get("rka_sidewalk_l_width", 0.0),
        sidewalk_r_width=coll.get("rka_sidewalk_r_width", 0.0),
        sidewalk_height=coll.get("rka_sidewalk_height", 0.15),
        sidewalk_l_width_end=coll.get("rka_sidewalk_l_width_end", None),
        sidewalk_r_width_end=coll.get("rka_sidewalk_r_width_end", None),
        sidewalk_l_asset_collection=coll.get("rka_sidewalk_l_asset_collection", "") or "",
        sidewalk_r_asset_collection=coll.get("rka_sidewalk_r_asset_collection", "") or "",
        prop_l_asset_collection=coll.get("rka_prop_l_asset_collection", "") or "",
        prop_l_spacing=coll.get("rka_prop_l_spacing", 30.0),
        prop_r_asset_collection=coll.get("rka_prop_r_asset_collection", "") or "",
        prop_r_spacing=coll.get("rka_prop_r_spacing", 30.0),
        profile_set=profile_set)
    if coll.get("rka_auto_lane_markings", True):
        _populate_lane_markings(
            context, coll, spine, lane_width, lanes, lanes_backward, traffic_side,
            auto_lane_markings=True,
            marking_gaps=[tuple(g) for g in coll.get("rka_marking_gaps", [])],
            profile_set=profile_set)
    # The other half of `clear_generated_mesh_objects(coll, keep_gn_boundaries=True)`: it SPARES
    # `mark_*` objects and stamps them unconfirmed, expecting this sweep to remove whichever the
    # repopulation above did not claim. Without it the previous pass's markings survive alongside
    # the new ones -- two centrelines on one road, the old one still showing a marking gap the
    # user had just removed (or missing one they had just added).
    sweep_untouched_boundaries(coll)


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
    evaluates to under 2 points (e.g. all points briefly deleted mid-edit).

    CARRIER-AGNOSTIC (2026-08-13, migration Step 2). This used to bail on
    `spine_obj.type != 'CURVE'`, which meant every cross-section edit on a modifier-stack piece --
    add a lane, widen the median, taper the end -- reported success and changed nothing at all:
    the operator wrote its custom property, called this, and this returned immediately because the
    carrier is a MESH. (Pure spine DRAGGING always worked on the stack, and still needs no Python
    at all, because the whole stack is driven off the carrier's own vertices. That is exactly why
    the no-op was easy to miss.) A stack piece now re-derives its layers through
    `apply_segment_stack`, the same function the initial build calls."""
    spine_name = coll.get("rka_curve_object")
    if not spine_name:
        return
    spine_obj = local_object(spine_name)
    if not spine_io.is_spine(spine_obj):
        return
    spine = _spine_control_points(spine_obj)
    if len(spine) < 2:
        return

    if spine_io.is_stack_carrier(spine_obj):
        _rebuild_segment_stack_in_place(context, coll, spine_obj, spine)
        coll["rka_p0"] = list(spine[0])
        coll["rka_p1"] = list(spine[-1])
        return

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    curb_l_style = coll.get("rka_curb_l_style", coll.get("rka_curb_style", 'NONE'))
    curb_r_style = coll.get("rka_curb_r_style", coll.get("rka_curb_style", 'NONE'))
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    curb_asset_obj = _resolve_curb_asset(coll.get("rka_curb_asset_collection", ""))
    curb_asset_spacing = coll.get("rka_curb_asset_spacing", 2.0)
    curb_asset_rot_offset_r = coll.get("rka_curb_asset_rot_offset_r", 180.0)
    auto_lane_markings = coll.get("rka_auto_lane_markings", True)
    marking_gaps = [tuple(g) for g in coll.get("rka_marking_gaps", [])]
    join_visual_mesh = any(o.name.startswith("mesh_") for o in coll.objects)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    median_width = coll.get("rka_median_width", 0.0)
    median_style = coll.get("rka_median_style", "NONE")
    median_asset_obj = _resolve_curb_asset(coll.get("rka_median_asset_collection", ""))
    median_asset_spacing = coll.get("rka_median_asset_spacing", 2.0)
    median_width_end = coll.get("rka_median_width_end", None)
    sidewalk_l_width = coll.get("rka_sidewalk_l_width", 0.0)
    sidewalk_r_width = coll.get("rka_sidewalk_r_width", 0.0)
    sidewalk_height = coll.get("rka_sidewalk_height", 0.15)
    sidewalk_l_width_end = coll.get("rka_sidewalk_l_width_end", None)
    sidewalk_r_width_end = coll.get("rka_sidewalk_r_width_end", None)
    sidewalk_l_asset_obj = _resolve_curb_asset(coll.get("rka_sidewalk_l_asset_collection", ""))
    sidewalk_r_asset_obj = _resolve_curb_asset(coll.get("rka_sidewalk_r_asset_collection", ""))
    sidewalk_asset_spacing = coll.get("rka_sidewalk_asset_spacing", 2.0)
    prop_l_asset_obj = _resolve_curb_asset(coll.get("rka_prop_l_asset_collection", ""))
    prop_l_spacing = coll.get("rka_prop_l_spacing", 30.0)
    prop_r_asset_obj = _resolve_curb_asset(coll.get("rka_prop_r_asset_collection", ""))
    prop_r_spacing = coll.get("rka_prop_r_spacing", 30.0)
    lanes_end = coll.get("rka_lanes_end", None)
    lanes_backward_end = coll.get("rka_lanes_backward_end", None)
    align = coll.get("rka_align", "right")

    # ---------------------------------------------------------------- LEGACY CARRIER FROM HERE
    # Everything below rebuilds a piece whose spine is still a POLY **Curve**, via the
    # sibling-object builder. No NEW piece takes this path -- `_build_segment_from_points` builds
    # only stack carriers since 2026-08-14 -- but every segment already authored in
    # `island_v3_roads.blend`, `world_session.blend` and `District_industry_5_1`'s `MANUAL`
    # collection is a Curve, and deleting this would make all of them uneditable.
    #
    # IT GOES WHEN THOSE FILES ARE CONVERTED, not before: migration Step 7 must run before the
    # rest of Step 3's deletion list (`_populate_segment_mesh_gn`, `clear_generated_mesh_objects`,
    # `_rka_touched`, `sweep_untouched_boundaries`). The plan had these the other way round; they
    # are ordered this way because authored content outranks tidiness.
    #
    # Known-weaker than the stack path, and deliberately not fixed here (see
    # `ROAD_KIT_MIGRATION_STATUS.md` Step 3): its build and rebuild derive markings differently,
    # and a declared median taper never reaches its geometry.
    clear_generated_mesh_objects(coll, keep_gn_boundaries=True)
    _populate_segment_mesh_gn(context, coll, spine_obj, lane_width, lanes, lanes_backward,
                               curb_l_style, curb_r_style, curb_height, curb_thickness,
                               join_visual_mesh, traffic_side, curb_asset_obj=curb_asset_obj,
                               curb_asset_spacing=curb_asset_spacing,
                               lanes_end=lanes_end, lanes_backward_end=lanes_backward_end,
                               align=align, median_width_end=median_width_end,
                               sidewalk_l_width_end=sidewalk_l_width_end,
                               sidewalk_r_width_end=sidewalk_r_width_end,
                               curb_asset_rot_offset_r=curb_asset_rot_offset_r,
                               auto_lane_markings=auto_lane_markings, marking_gaps=marking_gaps,
                               median_width=median_width, median_style=median_style,
                               median_asset_obj=median_asset_obj,
                               median_asset_spacing=median_asset_spacing,
                               sidewalk_l_width=sidewalk_l_width, sidewalk_r_width=sidewalk_r_width,
                               sidewalk_height=sidewalk_height,
                               sidewalk_l_asset_obj=sidewalk_l_asset_obj,
                               sidewalk_r_asset_obj=sidewalk_r_asset_obj,
                               sidewalk_asset_spacing=sidewalk_asset_spacing,
                               prop_l_asset_obj=prop_l_asset_obj,
                               prop_l_spacing=prop_l_spacing, prop_r_asset_obj=prop_r_asset_obj,
                               prop_r_spacing=prop_r_spacing,
                               # The piece's own cross-section, read back off the collection --
                               # without it a live-edit drag would rebuild an interchange
                               # carriageway's markings from the scalar lane count and quietly
                               # lose every exit-lane and gore line the profile describes.
                               profile_set=custom_props.read_profile(coll))
    sweep_untouched_boundaries(coll)   # delete anything provisionally spared above but never
                                        # reconfirmed this pass (fewer lanes/median/etc.)
    coll["rka_p0"] = list(spine[0])
    coll["rka_p1"] = list(spine[-1])


# Back-compat alias -- live_edit.py and any external caller referencing the pre-GN name.
rebuild_segment_from_curve_in_place = rebuild_segment_gn_in_place


class RKA_OT_add_marking_gap(bpy.types.Operator):
    """Append a `[t0, t1]` exclusion range (normalized 0=start/1=end along the active segment's
    spine) to its `rka_marking_gaps` custom property and rebuild markings in place -- the "clear
    lane markings across a driveway/merge zone" answer. Survives live-edit rebuilds because it's
    a persisted custom property read back by `_populate_lane_markings` on every rebuild, NOT a
    delete-the-object action -- hand-deleting a `mark_*` object directly would just get recreated
    by the next drag's `clear_generated_mesh_objects` + rebuild sweep.

    Select a plain (non-transition) GN segment's spine, one of its `segend_*`/`segbend` markers,
    or activate its collection first -- poll fails otherwise."""
    bl_idname = "rka.add_marking_gap"
    bl_label = "Add Marking Gap"
    bl_options = {'REGISTER', 'UNDO'}

    t0: bpy.props.FloatProperty(name="From", default=0.4, min=0.0, max=1.0)
    t1: bpy.props.FloatProperty(name="To", default=0.6, min=0.0, max=1.0)

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return (coll is not None and "rka_curve_object" in coll.keys()
                and "rka_lanes_a" not in coll.keys())

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        if coll is None or "rka_curve_object" not in coll.keys() or "rka_lanes_a" in coll.keys():
            self.report({'ERROR'}, "Select a plain segment (not a lane transition) first")
            return {'CANCELLED'}
        t0, t1 = sorted((self.t0, self.t1))
        gaps = [list(g) for g in coll.get("rka_marking_gaps", [])]
        gaps.append([t0, t1])
        coll["rka_marking_gaps"] = gaps
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "Added marking gap [%.2f, %.2f] to '%s'" % (t0, t1, coll.name))
        return {'FINISHED'}


class RKA_OT_clear_marking_gaps(bpy.types.Operator):
    """Remove every marking gap from the active segment and rebuild -- the inverse of
    `RKA_OT_add_marking_gap`."""
    bl_idname = "rka.clear_marking_gaps"
    bl_label = "Clear Marking Gaps"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        coll = _live_edit_target_collection(context)
        return coll is not None and bool(coll.get("rka_marking_gaps"))

    def execute(self, context):
        coll = _live_edit_target_collection(context)
        coll["rka_marking_gaps"] = []
        rebuild_segment_gn_in_place(context, coll)
        self.report({'INFO'}, "Cleared marking gaps on '%s'" % coll.name)
        return {'FINISHED'}


def _populate_transition_visuals(context, coll, spine_obj, seg, lane_width, curb_l_style,
                                  curb_r_style, curb_height, curb_thickness, join_visual_mesh,
                                  curb_asset_obj=None, curb_asset_spacing=2.0,
                                  curb_asset_rot_offset_r=180.0):
    """Curb + lanecl_* objects for a lane-count transition piece, from an already-computed
    `intersection_kit.build_lane_transition` result `seg` -- shared by
    `RKA_OT_build_lane_transition` and `rebuild_lane_transition_in_place` so they can't drift
    apart, same reasoning as every other paired build/rebuild function in this addon. See
    `_populate_segment_mesh_gn`'s docstring for the curb_asset_* parameters (PROFILE style)."""
    curb_matkey = coll.get("rka_curb_matkey", "concrete")
    visual_objs = [spine_obj]
    left_pts, right_pts = seg["curbs"]
    left_name, right_name = "curb_%s_L" % coll.name, "curb_%s_R" % coll.name
    # `asset_obj=curb_asset_obj` matters for `curb_style == 'PROFILE'` -- see `kit_common.
    # curb_loop`'s own docstring; harmless/unused for NONE. Both sides go through this ONE
    # `curb_loop` call now (2026-08, "only have none/profile... to simplify the code base" --
    # the old `if style == 'ASSET': build_curb(...) else: curb_loop(...)` split retired along
    # with the ASSET style itself; `curb_asset_spacing`/`curb_asset_rot_offset_r` are unused by
    # PROFILE's continuous sweep, kept only as still-valid `build_curb`/`curb_asset_row` args for
    # any direct caller). "-colonly" no longer baked live (2026-08) -- see
    # kit_common.bake_colonly_proxies.
    left = paths.kc.curb_loop(
        left_name, [(p[0], p[1], p[2], 0.0) for p in left_pts], coll,
        curb_style=curb_l_style, curb_height=curb_height, curb_thickness=curb_thickness,
        matkey=curb_matkey, closed=False, asset_obj=curb_asset_obj)
    right = paths.kc.curb_loop(
        right_name, [(p[0], p[1], p[2], 0.0) for p in right_pts], coll,
        curb_style=curb_r_style, curb_height=curb_height, curb_thickness=curb_thickness,
        matkey=curb_matkey, closed=False, asset_obj=curb_asset_obj)
    visual_objs += [o for o in (left, right) if o is not None]

    # Pavement collision ("-colonly") no longer baked live here (2026-08) -- see
    # kit_common.bake_colonly_proxies (export-time), same rationale as _populate_segment_mesh_gn.

    # `lanecl_*` no longer built here (2026-08) -- see ops_intersection.py's matching removal.

    return _join_visuals_keeping_spine(context, coll, spine_obj, visual_objs, join_visual_mesh)


class RKA_OT_build_lane_transition(bpy.types.Operator):
    """LEGACY / BACK-COMPAT ENTRY POINT -- no longer on the panel. A lane-count (or median/
    sidewalk-width) taper is now just `RKA_OT_build_straight_segment`/`RKA_OT_build_segment_from_curve`/
    `RKA_OT_extend_from_arm`/`RKA_OT_extend_from_port` with their own `lanes_end`/`median_width_end`/
    `sidewalk_*_width_end` fields left non-default (see `intersection_kit.build_segment_from_spine`'s
    taper docstring) -- those ALSO support a bent/multi-point spine and median/sidewalk/props, which
    this straight-2-point-only operator never gained. Kept registered (its own `rka_lanes_a`-keyed
    collection shape and `rebuild_lane_transition_in_place` still fully work) so an ALREADY-BUILT
    transition piece from before this unification keeps live-editing correctly, and so F9/scripting
    can still reach it directly -- just not a fresh "how do I taper" entry point an artist needs to
    learn separately anymore.

    Build a lane-COUNT transition (a merge/drop, or the reverse -- a split/add) between p0
    (`Lanes A` forward/backward) and p1 (`Lanes B`) -- the piece connecting a wide road to a
    narrower one (or a narrow one to a wider intersection arm), e.g. a 2-lane street narrowing
    into a 1-lane side street. Straight only (no bend).

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
    lanes_a: bpy.props.IntProperty(name="Lanes Forward (Start)", default=2, min=1, max=4)
    lanes_b: bpy.props.IntProperty(name="Lanes Forward (End)", default=1, min=1, max=4)
    lanes_backward_a: bpy.props.IntProperty(
        name="Lanes Backward (Start)", default=0, min=0, max=4,
        description="0 = symmetric with Lanes Forward (Start)")
    lanes_backward_b: bpy.props.IntProperty(
        name="Lanes Backward (End)", default=0, min=0, max=4,
        description="0 = symmetric with Lanes Forward (End)")
    align: bpy.props.EnumProperty(
        name="Align", items=(
            ('right', "Right (curb-side continues)", "The outer/curb-side lane(s) run straight "
             "through; the inner lane(s) taper into them -- a real lane-drop"),
            ('left', "Left (median-side continues)", "Mirror of Right -- inner lane(s) stay put, "
             "outer lane(s) taper inward"),
        ), default='right')
    curb_l_style: bpy.props.EnumProperty(name="Curb Style (Left)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_r_style: bpy.props.EnumProperty(name="Curb Style (Right)", items=CURB_STYLE_ITEMS, default='NONE')
    curb_asset_collection: bpy.props.StringProperty(
        name="Curb Asset Piece", description="Linked kit/curb_kit.blend collection's mesh "
        "object, when a Curb Style above is 'Asset'", default="")
    curb_asset_spacing: bpy.props.FloatProperty(
        name="Curb Asset Spacing", default=2.0, min=0.1, unit='LENGTH')
    curb_asset_rot_offset_r: bpy.props.FloatProperty(
        name="Curb Asset R-Side Rotation Offset", default=180.0)
    traffic_side: bpy.props.EnumProperty(name="Traffic Side", items=TRAFFIC_SIDE_ITEMS, default='LEFT')
    curb_height: bpy.props.FloatProperty(name="Curb Height", default=0.15, min=0.01, unit='LENGTH')
    curb_thickness: bpy.props.FloatProperty(name="Curb Thickness", default=0.25, min=0.01, unit='LENGTH')
    join_visual_mesh: bpy.props.BoolProperty(name="Join Into One Mesh", default=False)
    export_path: bpy.props.StringProperty(
        name="Export .lanekit.json", default="", subtype='FILE_PATH')

    def invoke(self, context, event):
        self.traffic_side = context.scene.rka.default_traffic_side
        # Anchored build: an arm_*/port_* marker is active -- prefill Direction and Lanes A/
        # Backward A so the redo panel already shows a transition facing the right way with
        # matching lane counts. No position offset is needed here (unlike
        # `RKA_OT_build_intersection`'s anchored build) -- a transition's own start point can sit
        # exactly at the marker's position with no gap, and `execute()`'s existing
        # `active_marker_position` call below already places it there.
        anchor = arm_or_port_anchor(context)
        if anchor is not None:
            _, _, heading_deg, lanes_forward, lanes_backward, _ = anchor
            self.direction_deg = heading_deg
            if lanes_forward > 0:
                self.lanes_a = max(1, min(4, lanes_forward))
            if lanes_backward != lanes_forward:
                self.lanes_backward_a = max(0, min(4, lanes_backward))
        return self.execute(context)

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
        # local_collection (not a bare name-in-bpy.data.collections test) so a linked neighbor's
        # same-numbered piece never perturbs local auto-numbering -- see its docstring.
        while local_collection("Transition_%03d" % n) is not None:
            n += 1
        coll = bpy.data.collections.new("Transition_%03d" % n)
        parent_coll.children.link(coll)
        # Same UX-only anchor plain segments get -- see the matching comment in
        # _build_segment_from_points. Re-snapped to the spine's current start point on every
        # rebuild (rebuild_lane_transition_in_place).
        get_or_create_origin_marker(coll, p0)

        half_w_a = max(self.lanes_a, lanes_backward_a or self.lanes_a) * self.lane_width
        half_w_b = max(self.lanes_b, lanes_backward_b or self.lanes_b) * self.lane_width
        spine_obj = paths.kc.road_spine("spine_%s" % coll.name, [p0, p1], coll,
                                         [half_w_a, half_w_b],
                                         matkey=coll.get("rka_pave_matkey", "asphalt"))

        curb_asset_obj = _resolve_curb_asset(self.curb_asset_collection)
        visual_objs = _populate_transition_visuals(
            context, coll, spine_obj, seg, self.lane_width, self.curb_l_style, self.curb_r_style,
            self.curb_height, self.curb_thickness, self.join_visual_mesh,
            curb_asset_obj=curb_asset_obj, curb_asset_spacing=self.curb_asset_spacing,
            curb_asset_rot_offset_r=self.curb_asset_rot_offset_r)

        custom_props.write_build_settings(
            coll, lane_width=self.lane_width, lanes_a=self.lanes_a, lanes_b=self.lanes_b,
            lanes_backward_a=self.lanes_backward_a, lanes_backward_b=self.lanes_backward_b,
            align=self.align, curb_l_style=self.curb_l_style, curb_r_style=self.curb_r_style,
            traffic_side=self.traffic_side,
            curb_asset_collection=self.curb_asset_collection or None,
            curb_asset_spacing=self.curb_asset_spacing,
            curb_asset_rot_offset_r=self.curb_asset_rot_offset_r,
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


@live_edit.rebuilding()
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
    spine_obj = local_object(spine_name)
    if spine_obj is None or spine_obj.type != 'CURVE':
        return
    spine = _spine_control_points(spine_obj)
    if len(spine) < 2:
        return
    p0, p1 = spine[0], spine[-1]
    origin_marker = get_or_create_origin_marker(coll, p0)
    if origin_marker is not None:
        origin_marker.location = p0

    lane_width = coll.get("rka_lane_width", 5.0)
    lanes_a = coll.get("rka_lanes_a", 2)
    lanes_b = coll.get("rka_lanes_b", 1)
    lanes_backward_a = coll.get("rka_lanes_backward_a", 0) or None
    lanes_backward_b = coll.get("rka_lanes_backward_b", 0) or None
    align = coll.get("rka_align", 'right')
    curb_l_style = coll.get("rka_curb_l_style", 'NONE')
    curb_r_style = coll.get("rka_curb_r_style", 'NONE')
    curb_height = coll.get("rka_curb_height", 0.15)
    curb_thickness = coll.get("rka_curb_thickness", 0.25)
    curb_asset_obj = _resolve_curb_asset(coll.get("rka_curb_asset_collection", ""))
    curb_asset_spacing = coll.get("rka_curb_asset_spacing", 2.0)
    curb_asset_rot_offset_r = coll.get("rka_curb_asset_rot_offset_r", 180.0)
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

    clear_generated_mesh_objects(coll, keep_gn_boundaries=True)
    _populate_transition_visuals(context, coll, spine_obj, seg, lane_width, curb_l_style,
                                  curb_r_style, curb_height, curb_thickness, join_visual_mesh,
                                  curb_asset_obj=curb_asset_obj, curb_asset_spacing=curb_asset_spacing,
                                  curb_asset_rot_offset_r=curb_asset_rot_offset_r)
    sweep_untouched_boundaries(coll)   # delete anything provisionally spared above but never
                                        # reconfirmed this pass (fewer lanes/median/etc.)
    coll["rka_p0"] = list(p0)
    coll["rka_p1"] = list(p1)


CLASSES = (RKA_OT_build_straight_segment, RKA_OT_extend_from_arm, RKA_OT_extend_from_port,
           RKA_OT_select_spine, RKA_OT_insert_intersection_on_segment,
           RKA_OT_adjust_segment_lanes, RKA_OT_adjust_segment_lanes_end,
           RKA_OT_adjust_transition_lanes, RKA_OT_adjust_median_width,
           RKA_OT_adjust_median_width_end,
           RKA_OT_set_curb_style, RKA_OT_pick_curb_asset,
           RKA_OT_set_median_style, RKA_OT_pick_median_asset,
           RKA_OT_adjust_sidewalk_width, RKA_OT_adjust_sidewalk_width_end,
           RKA_OT_set_sidewalk_asset, RKA_OT_adjust_sidewalk_asset_spacing,
           RKA_OT_pick_sidewalk_asset_l, RKA_OT_pick_sidewalk_asset_r,
           RKA_OT_set_prop_asset, RKA_OT_adjust_prop_spacing,
           RKA_OT_pick_prop_asset_l, RKA_OT_pick_prop_asset_r,
           RKA_OT_build_segment_from_curve, RKA_OT_build_lane_transition,
           RKA_OT_add_marking_gap, RKA_OT_clear_marking_gaps)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
