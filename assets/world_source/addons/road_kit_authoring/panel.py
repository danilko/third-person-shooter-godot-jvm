"""N-panel UI: View3D > Sidebar > 'Road Kit' tab."""
import os

import bpy

from . import paths


class RKA_PT_road_kit(bpy.types.Panel):
    bl_label = "Road Kit"
    bl_idname = "RKA_PT_road_kit"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Road Kit"

    def draw(self, context):
        layout = self.layout
        rka = context.scene.rka

        box = layout.box()
        box.label(text="Kit Library", icon='LIBRARY_DATA_DIRECT')
        box.label(text=os.path.relpath(paths.KIT_BLEND, paths.WORLD_SOURCE))
        box.operator("rka.link_kit_library", icon='LINKED')

        box = layout.box()
        box.label(text="Placement", icon='SNAP_GRID')
        box.prop(rka, "grid")
        box.prop_search(rka, "active_kit_collection", bpy.data, "collections", text="Piece")
        box.operator("rka.place_piece", icon='ADD')

        row = box.row(align=True)
        row.prop(rka, "place_direction", text="")
        row.operator("rka.duplicate_piece", text="Duplicate", icon='DUPLICATE').reverse = False
        row.operator("rka.duplicate_piece", text="Duplicate (reverse)", icon='ARROW_LEFTRIGHT').reverse = True

        row = box.row(align=True)
        row.operator("rka.rotate_piece_90", text="Rotate CW", icon='LOOP_FORWARDS').ccw = False
        row.operator("rka.rotate_piece_90", text="Rotate CCW", icon='LOOP_BACK').ccw = True

        box = layout.box()
        box.label(text="Multi-lane (seam marking)", icon='MOD_LINEART')
        box.prop(rka, "lane_surface_z")
        box.prop(rka, "lane_marking_width")
        box.operator("rka.combine_lanes", icon='SNAP_MIDPOINT')

        box = layout.box()
        box.label(text="Live Edit", icon='MOD_SIMPLEDEFORM')
        box.prop(rka, "live_edit_enabled")
        box.label(text="Drag an 'arm_*' Empty to rotate/reshape its intersection live.")
        box.label(text="Drag a segment's 'segend_A/B' to resize/redirect it, or its")
        box.label(text="'segbend' to bend/hill it -- all live, no F9 needed.")
        box.operator("rka.rebuild_from_handles", icon='FILE_REFRESH')
        box.label(text="(manual fallback -- use if a drag doesn't auto-update)")

        active_obj = context.active_object
        active_coll_le = context.view_layer.active_layer_collection.collection
        if active_obj is not None and "rka_arm_name" in active_obj.keys():
            row = box.row(align=True)
            row.label(text="Arm '%s' lanes: %d" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_lanes", 1)))
            row.operator("rka.adjust_arm_lanes", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_arm_lanes", text="", icon='ADD').delta = 1
            cur_dir = active_obj.get("rka_arm_oneway", "") or 'BOTH'
            row = box.row(align=True)
            row.label(text="Direction:")
            row.operator("rka.set_arm_oneway", text="Both").mode = 'BOTH'
            row.operator("rka.set_arm_oneway", text="In Only").mode = 'IN'
            row.operator("rka.set_arm_oneway", text="Out Only").mode = 'OUT'
            box.label(text="(currently: %s)" % cur_dir)
            box.operator("rka.remove_arm", icon='X')
        seg_coll_le = (active_obj.users_collection[0]
                       if active_obj is not None and active_obj.users_collection
                       and "rka_p0" in active_obj.users_collection[0].keys()
                       else (active_coll_le if active_coll_le is not None
                             and "rka_p0" in active_coll_le.keys() else None))
        if seg_coll_le is not None:
            row = box.row(align=True)
            row.label(text="Fwd: %d" % seg_coll_le.get("rka_lanes", 1))
            row.operator("rka.adjust_segment_lanes", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_segment_lanes", text="", icon='ADD').delta = 1
            row = box.row(align=True)
            row.label(text="Back: %d" % seg_coll_le.get("rka_lanes_backward", 1))
            op = row.operator("rka.adjust_segment_lanes", text="", icon='REMOVE')
            op.delta, op.backward = -1, True
            op = row.operator("rka.adjust_segment_lanes", text="", icon='ADD')
            op.delta, op.backward = 1, True
        if (active_coll_le is not None and "rka_arm_names" in active_coll_le.keys()) or \
                (active_obj is not None and "rka_arm_name" in active_obj.keys()):
            box.operator("rka.add_arm", icon='ADD', text="Add Arm (widest gap)")

        box = layout.box()
        box.label(text="Intersection (prototype)", icon='MESH_CIRCLE')
        box.operator("rka.build_intersection", icon='ADD')
        box.label(text="Builds at an active arm_*/segend_*/segbend_* marker if one is")
        box.label(text="selected, else at the 3D cursor. F9 (right after building, before")
        box.label(text="anything else) to tweak preset/radius/lanes/lane_map/join-mesh.")
        box.label(text="Each arm gets an 'arm_*' Empty at its tail -- click one, then")
        box.label(text="'Extend From Arm' below, to grow a road from it.")

        box = layout.box()
        box.label(text="Straight Segment", icon='MESH_PLANE')
        box.operator("rka.build_straight_segment", icon='ADD')
        box.label(text="Same active-marker-or-cursor start point as 'Build Intersection'.")
        box.label(text="Lanes Backward = 0 makes it one-way (1 fwd/0 back = single-lane")
        box.label(text="one-way). F9 (right after building) to tweak Bend/Vertical Bend/")
        box.label(text="Elevation Delta/curb style. Auto-Advance Cursor (on by default)")
        box.label(text="moves the cursor to this segment's end so the next build continues it.")
        box.label(text="LaneGraph auto-links coincident endpoints at bake time.")

        box = layout.box()
        box.label(text="Segment From Curve", icon='CURVE_PATH')
        active = context.active_object
        if active is not None and active.type == 'CURVE':
            box.label(text="Active: '%s'" % active.name)
        else:
            box.label(text="Select a Curve object (draw one, or Add > Curve) first.")
        box.operator("rka.build_segment_from_curve", icon='ADD')
        box.label(text="Follows the curve's EXACT evaluated points -- edit its control")
        box.label(text="points in Edit Mode (add more for a multi-point slope/bend) and")
        box.label(text="the road updates live (or press 'Rebuild From Handles' above).")

        box = layout.box()
        box.label(text="Extend / Insert", icon='CON_FOLLOWPATH')
        active_coll = context.view_layer.active_layer_collection.collection
        active_obj = context.active_object
        is_arm_empty = active_obj is not None and "rka_arm_name" in active_obj.keys()
        is_intersection = active_coll is not None and "rka_arm_names" in active_coll.keys()
        is_segment = active_coll is not None and "rka_p0" in active_coll.keys()
        if is_arm_empty:
            box.label(text="Active: arm '%s' (angle %.1f deg)" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_angle", 0.0)))
            box.operator("rka.extend_from_arm", icon='ADD')
        elif is_intersection:
            box.label(text="Active: '%s' (arms: %s)" % (active_coll.name, ", ".join(active_coll["rka_arm_names"])))
            box.label(text="(or click an 'arm_*' Empty instead of typing 'Arm' below)")
            box.operator("rka.extend_from_arm", icon='ADD')
        elif is_segment:
            box.label(text="Active: '%s' (a segment)" % active_coll.name)
            box.operator("rka.insert_intersection_on_segment", icon='ADD')
        else:
            box.label(text="Activate an Intersection/Segment collection, or click an")
            box.label(text="'arm_*' Empty, to extend/insert here.")

        box = layout.box()
        box.label(text="Centerline", icon='CURVE_DATA')
        active = context.active_object
        has_group = active is not None and active.type == 'MESH' and "lanedata" in active.vertex_groups
        if active is None or active.type != 'MESH':
            box.label(text="Select a lane mesh with a 'lanedata' vertex group")
        elif not has_group:
            box.label(text="'%s' has no 'lanedata' vertex group" % active.name)
        box.operator("rka.centerline_from_vertex_group", icon='ADD')

        box = layout.box()
        box.label(text="Connectivity (Phase 3, not wired yet)", icon='INFO')
        box.prop(rka, "connect_eps")


CLASSES = (RKA_PT_road_kit,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
