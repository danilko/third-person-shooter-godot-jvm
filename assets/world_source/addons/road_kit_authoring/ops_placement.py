"""Phase 1 placement operators: link the kit library, place/duplicate/rotate pieces on a grid."""
import os
from math import radians

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from . import paths


def _target_collection(context):
    """Dest collection for placed/duplicated instances — whatever's active in the outliner
    (falls back to the scene root), same convention as manual object creation."""
    return context.view_layer.active_layer_collection.collection


def _snap(value, grid):
    return round(value / grid) * grid


def _ground_hit(context, event, grid):
    """Ray from the mouse through the view, intersected with the world Z=0 ground plane, snapped
    to `grid`. Returns None if the view is edge-on to the ground (no intersection)."""
    region = context.region
    rv3d = context.region_data
    coord = (event.mouse_region_x, event.mouse_region_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    hit = intersect_line_plane(origin, origin + direction, Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)))
    if hit is None:
        return None
    return Vector((_snap(hit.x, grid), _snap(hit.y, grid), 0.0))


class RKA_OT_link_kit_library(bpy.types.Operator):
    """Link every piece Collection from kit/lane_kit.blend into this file (linked, not appended —
    editing a piece in lane_kit.blend and reopening this file picks up the change)."""
    bl_idname = "rka.link_kit_library"
    bl_label = "Link Kit Library"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not os.path.exists(paths.KIT_BLEND):
            self.report({'ERROR'}, "Kit library not found: %s (run kit/build_lane_kit.py first)" % paths.KIT_BLEND)
            return {'CANCELLED'}
        with bpy.data.libraries.load(paths.KIT_BLEND, link=True) as (src, dst):
            dst.collections = list(src.collections)
        linked = [c for c in dst.collections if c is not None]
        if not linked:
            self.report({'WARNING'}, "No collections found in %s" % paths.KIT_BLEND)
            return {'CANCELLED'}
        if not context.scene.rka.active_kit_collection:
            context.scene.rka.active_kit_collection = linked[0].name
        self.report({'INFO'}, "Linked %d kit piece(s): %s" % (len(linked), ", ".join(c.name for c in linked)))
        return {'FINISHED'}


class RKA_OT_place_piece(bpy.types.Operator):
    """Click to drop linked instances of the active kit piece on the placement grid; Esc/right-click to stop"""
    bl_idname = "rka.place_piece"
    bl_label = "Place Piece"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.rka.active_kit_collection)

    def invoke(self, context, event):
        rka = context.scene.rka
        self.coll = bpy.data.collections.get(rka.active_kit_collection)
        if self.coll is None:
            self.report({'ERROR'}, "Active kit piece '%s' not found — link the kit library first" % rka.active_kit_collection)
            return {'CANCELLED'}
        self._count = 0
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(
            "Road Kit: click to place '%s'  |  Esc / right-click to stop" % self.coll.name)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            loc = _ground_hit(context, event, context.scene.rka.grid)
            if loc is not None:
                self._count += 1
                dest = _target_collection(context)
                inst = paths.kc.instance_collection(dest, "%s_%03d" % (self.coll.name, self._count), self.coll, loc)
                for obj in context.selected_objects:
                    obj.select_set(False)
                inst.select_set(True)
                context.view_layer.objects.active = inst
            return {'RUNNING_MODAL'}
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            context.workspace.status_text_set(None)
            return {'FINISHED'}
        # swallow everything else so orbit/pan don't fight click-placement; nav keys still pass
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class RKA_OT_duplicate_piece(bpy.types.Operator):
    """Duplicate each selected kit-piece instance, offset one grid step along its own local
    placement direction (so it continues correctly after a 90 degree rotation).

    With `reverse` on, the new copy is rotated 180 degrees to run the opposite direction (for a
    2-way street's other-direction lane) -- and, since a lane tile is endpoint-pivoted at local
    Y=0 (see Kit geometry v2 item 1), its placement is ALSO pushed one grid step further along the
    source's own forward direction. Without that push a 180-degree spin happens around the tile's
    own Y=0 end and swings its footprint clean off the segment it's meant to share with its
    same-direction neighbours (caught by the ops_combine.py smoke test — a naive "same spot,
    rotated 180" reverse lane doesn't overlap the forward lane's road segment at all)."""
    bl_idname = "rka.duplicate_piece"
    bl_label = "Duplicate Piece"
    bl_options = {'REGISTER', 'UNDO'}

    DIRS = {
        'POS_X': Vector((1.0, 0.0, 0.0)),
        'NEG_X': Vector((-1.0, 0.0, 0.0)),
        'POS_Y': Vector((0.0, 1.0, 0.0)),
        'NEG_Y': Vector((0.0, -1.0, 0.0)),
    }

    reverse: bpy.props.BoolProperty(
        name="Reverse Direction", default=False,
        description="New copy runs the opposite direction (for a 2-way street's other lane) -- "
                    "auto-corrects placement so its footprint still covers the same road segment")

    @classmethod
    def poll(cls, context):
        return any(o.instance_type == 'COLLECTION' for o in context.selected_objects)

    def execute(self, context):
        rka = context.scene.rka
        local_dir = self.DIRS[rka.place_direction]
        dest = _target_collection(context)
        sources = [o for o in context.selected_objects
                   if o.instance_type == 'COLLECTION' and o.instance_collection]
        new_objs = []
        for obj in sources:
            world_dir = (obj.matrix_world.to_3x3() @ local_dir).normalized()
            loc = obj.location + world_dir * rka.grid
            world_fwd = (obj.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
            if self.reverse:
                loc = loc + world_fwd * rka.grid
            new = paths.kc.instance_collection(dest, obj.instance_collection.name, obj.instance_collection, loc)
            new.rotation_euler = obj.rotation_euler.copy()
            if self.reverse:
                new.rotation_euler.rotate_axis('Z', radians(180.0))
            new_objs.append(new)
        for obj in context.selected_objects:
            obj.select_set(False)
        for new in new_objs:
            new.select_set(True)
        if new_objs:
            context.view_layer.objects.active = new_objs[-1]
        self.report({'INFO'}, "Duplicated %d piece(s)" % len(new_objs))
        return {'FINISHED'}


class RKA_OT_rotate_piece_90(bpy.types.Operator):
    """Rotate each selected kit-piece instance 90 degrees around world Z, in place"""
    bl_idname = "rka.rotate_piece_90"
    bl_label = "Rotate 90"
    bl_options = {'REGISTER', 'UNDO'}

    ccw: bpy.props.BoolProperty(name="Counter-clockwise", default=False)

    @classmethod
    def poll(cls, context):
        return any(o.instance_type == 'COLLECTION' for o in context.selected_objects)

    def execute(self, context):
        angle = radians(-90.0 if self.ccw else 90.0)
        n = 0
        for obj in context.selected_objects:
            if obj.instance_type != 'COLLECTION':
                continue
            obj.rotation_euler.rotate_axis('Z', angle)
            n += 1
        self.report({'INFO'}, "Rotated %d piece(s)" % n)
        return {'FINISHED'}


CLASSES = (RKA_OT_link_kit_library, RKA_OT_place_piece, RKA_OT_duplicate_piece, RKA_OT_rotate_piece_90)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
