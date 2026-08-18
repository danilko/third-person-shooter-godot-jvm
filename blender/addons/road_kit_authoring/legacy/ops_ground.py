"""Cut ground under a road -- boolean-remove a road piece's own footprint from a selected terrain
mesh, so freshly authored road_kit_authoring pavement doesn't z-fight with/sit on top of ground
that already models a road-shaped bump at that spot (the concrete case: `Piece_2_1`'s `STREET`
collection still carries the old baked `District_city_2_1_Terrain-col` + `..._Road` combo mesh
from the pre-registry PLATEAU-import era -- see CLAUDE.md's "Terrain & seam alignment" section for
that history). No automated ground/road compositing existed anywhere before this (confirmed:
`kit_common.cut()`, the existing generic box boolean-difference helper, was never called against
terrain) -- this is a new, EXPLICIT, artist-triggered operator (select the terrain object, then
click the road piece -- a segment's spine/curb, or an intersection's pad/curb/any marker -- last so
it's the active object, then run), not automatic magic: Blender's boolean modifier can produce
garbage on some concave/sloped terrain topologies, so a reviewable per-use operation is the safer
default (matches this addon's existing convention of explicit operators over implicit rebuilds,
e.g. `--hard-resync`/`--force-drop` in the world-session tools).
"""
import math

import bpy

from . import custom_props, paths, spine_io

_ik = None


def ik():
    global _ik
    if _ik is None:
        import intersection_kit as _mod
        _ik = _mod
    return _ik


def _road_collection(context):
    """The active object's own road-piece collection (a segment or an intersection built by this
    addon), or None if the active object isn't part of one."""
    obj = context.active_object
    if obj is None or not obj.users_collection:
        return None
    coll = obj.users_collection[0]
    if "rka_curve_object" in coll.keys() or "rka_arm_names" in coll.keys():
        return coll
    return None


def _segment_footprint(coll, margin):
    """World-space XY footprint polygon for a plain/curve GN segment: the two curb (or, if wider,
    outer) offset lines plus `margin` meters of extra clearance, using the EXACT SAME
    `intersection_kit.offset_spine_line` offset-from-spine machinery every other aligned feature
    on this piece already uses -- not a bounding box, so a bent/curved segment's cut follows its
    actual shape instead of over-cutting a rectangle around it. None if `coll` has no live spine
    (e.g. the spine object was deleted)."""
    k = ik()
    from .ops_segment import _spine_control_points
    spine_obj = bpy.data.objects.get(coll.get("rka_curve_object", ""))
    if not spine_io.is_spine(spine_obj):
        return None
    spine = _spine_control_points(spine_obj)
    lane_width = coll.get("rka_lane_width", 5.0)
    lanes = coll.get("rka_lanes", 1)
    lanes_backward = coll.get("rka_lanes_backward", lanes)
    traffic_side = coll.get("rka_traffic_side", "LEFT")
    median_width = coll.get("rka_median_width", 0.0)
    median_half = median_width / 2.0 if (median_width > 0.0 and lanes > 0 and lanes_backward > 0) \
        else 0.0
    half_w = median_half + max(lanes, lanes_backward) * lane_width
    sidewalk_l = coll.get("rka_sidewalk_l_width", 0.0)
    sidewalk_r = coll.get("rka_sidewalk_r_width", 0.0)
    outer_l = half_w + max(sidewalk_l, 0.0) + margin
    outer_r = half_w + max(sidewalk_r, 0.0) + margin
    left = k.offset_spine_line(spine, outer_l, traffic_side)
    right = k.offset_spine_line(spine, -outer_r, traffic_side)
    return [(p[0], p[1]) for p in left] + [(p[0], p[1]) for p in reversed(right)]


def _junction_footprint(coll, margin):
    """World-space XY footprint polygon for an intersection: `build_junction_boundary`'s own pad
    polygon (already the full closed footprint incl. arm tail-caps and rounded corners, as
    straight-line vertices), scaled radially outward from the junction's own origin by `margin`
    meters -- an approximation (exact for a vertex's own direction, only approximately `margin`
    meters normal-to-edge for two vertices far apart on a long straight tail-cap edge), acceptable
    for a clearance margin of this size (typically well under a meter). None if `coll` has no
    stored arm/origin data."""
    k = ik()
    arms = custom_props.read_arms_full(coll, k.Arm)
    origin = custom_props.read_origin(coll)
    if arms is None or origin is None:
        return None
    kerb_radius = coll.get("rka_kerb_radius", 9.0)
    tail_length = coll.get("rka_tail_length", 12.0)
    boundary = k.build_junction_boundary(arms, kerb_radius, tail_length=tail_length)
    cx, cy, _cz = origin
    pts = []
    for (x, y, _r) in boundary:
        d = math.hypot(x, y)
        scale = (d + margin) / d if d > 1e-6 else 1.0
        pts.append((cx + x * scale, cy + y * scale))
    return pts


class RKA_OT_cut_ground_under_road(bpy.types.Operator):
    """Boolean-remove the active road piece's own footprint (+ a margin) from EVERY selected mesh
    that isn't part of the road piece itself -- fixes newly authored pavement sitting on top of/
    z-fighting with ground that already models a road-shaped bump there.

    MULTIPLE MESHES UNDER THE SAME ROAD: cuts ALL of them, not just one. There is no "pick the
    nearest/topmost mesh" guessing -- every selected `MESH` object (other than an object that
    belongs to the active road piece's own collection, e.g. its `pave_*`/`curb_*`/`spine_*`) is
    cut independently with the identical footprint/depth/rise. So if a district's ground is split
    across several objects at that spot (a visual terrain mesh AND a separate `-col` collision
    mesh, or two overlapping legacy meshes like `Piece_2_1`'s old combined
    `District_city_2_1_Terrain-col` + `..._Road`), select ALL of them before running this -- a
    mesh you forget to select is left completely untouched, not skipped-with-a-warning. Check the
    'INFO' report after running (it lists every object actually cut) to confirm nothing was
    missed.

    Select every terrain/ground mesh you want cut FIRST, then shift-click the road piece (a
    segment's spine/curb, or any part of an intersection) LAST so it ends up ACTIVE, then run.
    Applies a real BOOLEAN modifier to each target (destructive, like every other 'apply' in this
    addon) -- undo (Ctrl+Z) reverses it like any other operator."""
    bl_idname = "rka.cut_ground_under_road"
    bl_label = "Cut Ground Under Road"
    bl_options = {'REGISTER', 'UNDO'}

    cut_depth: bpy.props.FloatProperty(
        name="Cut Depth", description="How far below the road piece's own Z to cut, in meters",
        default=10.0, min=0.1, unit='LENGTH')
    cut_rise: bpy.props.FloatProperty(
        name="Cut Rise", description="How far above the road piece's own Z to cut -- covers "
        "terrain that pokes up higher than the road too, e.g. a bumpy DEM crest", default=2.0,
        min=0.0, unit='LENGTH')
    margin: bpy.props.FloatProperty(
        name="Margin", description="Extra lateral clearance beyond the road's own curb/sidewalk "
        "edge, so no paper-thin sliver of old terrain is left right at the edge from floating-"
        "point/vertex misalignment", default=0.5, min=0.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        road_coll = _road_collection(context)
        if road_coll is None:
            return False
        return any(o.type == 'MESH' and o.users_collection and o.users_collection[0] != road_coll
                   for o in context.selected_objects)

    def execute(self, context):
        road_coll = _road_collection(context)
        if road_coll is None:
            self.report({'ERROR'}, "Active object isn't part of a segment or intersection built "
                                    "by this addon")
            return {'CANCELLED'}
        targets = [o for o in context.selected_objects
                   if o.type == 'MESH' and (not o.users_collection
                                             or o.users_collection[0] != road_coll)]
        if not targets:
            self.report({'ERROR'}, "Select a terrain mesh object (in addition to the active road "
                                    "piece) first")
            return {'CANCELLED'}

        if "rka_curve_object" in road_coll.keys():
            footprint = _segment_footprint(road_coll, self.margin)
            z_ref = context.active_object.matrix_world.translation.z
        else:
            footprint = _junction_footprint(road_coll, self.margin)
            origin = custom_props.read_origin(road_coll)
            rka = context.scene.rka
            z_ref = (origin[2] + rka.lane_surface_z) if origin is not None else \
                context.active_object.matrix_world.translation.z
        if footprint is None or len(footprint) < 3:
            self.report({'ERROR'}, "Couldn't derive a footprint for '%s' -- missing spine/arm "
                                    "data" % road_coll.name)
            return {'CANCELLED'}

        k = paths.kc
        cut_count = 0
        for target in targets:
            k.cut_polygon(target, footprint, z_ref - self.cut_depth, z_ref + self.cut_rise)
            cut_count += 1
        self.report({'INFO'}, "Cut '%s' footprint out of %d terrain object(s): %s" %
                     (road_coll.name, cut_count, ", ".join(o.name for o in targets)))
        return {'FINISHED'}


CLASSES = (RKA_OT_cut_ground_under_road,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
