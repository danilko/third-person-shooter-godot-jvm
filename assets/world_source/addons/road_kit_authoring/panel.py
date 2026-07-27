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

        layout.prop(rka, "default_traffic_side")

        box = layout.box()
        box.label(text="Kit Library", icon='LIBRARY_DATA_DIRECT')
        box.label(text=os.path.relpath(paths.KIT_BLEND, paths.WORLD_SOURCE))
        box.operator("rka.link_kit_library", icon='LINKED')

        box = layout.box()
        box.label(text="Curb Kit Library", icon='LIBRARY_DATA_DIRECT')
        box.label(text=os.path.relpath(paths.CURB_KIT_BLEND, paths.WORLD_SOURCE))
        box.operator("rka.link_curb_kit_library", icon='LINKED')
        box.label(text="Set a Curb Style to 'Asset' on any build operator's F9 panel, then")
        box.label(text="'Curb Asset Piece' to a linked collection's name (e.g.")
        box.label(text="'Kit_Curb_JerseyBarrier_L2').")

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

        box.operator("rka.select_piece", icon='RESTRICT_SELECT_OFF')
        row = box.row(align=True)
        row.operator("rka.freeze_for_move", icon='PINNED')
        row.operator("rka.unfreeze_and_rebuild", icon='FILE_REFRESH')
        box.label(text="To move/rotate a WHOLE piece: select any part of it (a marker, or")
        box.label(text="even a generated curb/pad/spine), 'Select Piece' (selects every object")
        box.label(text="in it) -- or 'Freeze For Move' first if you want ZERO risk of live-edit")
        box.label(text="regenerating anything mid-drag -- then Grab/Rotate freely. Both set the")
        box.label(text="origin marker active + Pivot Point to 'Active Element' (the 3D cursor is")
        box.label(text="never touched, so other tools relying on it are unaffected).")
        box.label(text="Don't change Pivot Point away from 'Active Element' while rotating --")
        box.label(text="'3D Cursor'/'Median Point' both pivot on the wrong point for this addon.")
        box.label(text="If frozen, 'Unfreeze & Rebuild' when done to bring geometry back in")
        box.label(text="sync and restore your previous Pivot Point setting.")

        box.prop(rka, "show_traffic_indicators")
        box.label(text="Blue arrow = incoming (arriving) lanes, orange = outgoing")
        box.label(text="(departing) -- one pair per arm/segment end, updates live.")

        active_obj = context.active_object
        active_coll_le = context.view_layer.active_layer_collection.collection
        if active_obj is not None and "rka_arm_name" in active_obj.keys():
            row = box.row(align=True)
            row.label(text="Arm '%s' lanes: %d" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_lanes", 1)))
            row.operator("rka.adjust_arm_lanes", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_arm_lanes", text="", icon='ADD').delta = 1
            lanes_out = active_obj.get("rka_arm_lanes_out", 0)
            row = box.row(align=True)
            row.label(text="  Departing (asymmetric): %s" %
                       ("symmetric" if lanes_out == 0 else str(lanes_out)))
            row.operator("rka.adjust_arm_lanes_out", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_arm_lanes_out", text="", icon='ADD').delta = 1
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
        if seg_coll_le is not None and "rka_lanes_a" not in seg_coll_le.keys():
            box.prop(rka, "marking_dash_length")
            box.prop(rka, "marking_gap_length")
            gaps = seg_coll_le.get("rka_marking_gaps", [])
            for g in gaps:
                box.label(text="  Gap: %.2f -> %.2f" % (g[0], g[1]))
            row = box.row(align=True)
            row.operator("rka.add_marking_gap", icon='ADD')
            row.operator("rka.clear_marking_gaps", icon='X')
        intersection_coll_le = (active_obj.users_collection[0]
                                 if active_obj is not None and active_obj.users_collection
                                 and "rka_arm_names" in active_obj.users_collection[0].keys()
                                 else (active_coll_le if active_coll_le is not None
                                       and "rka_arm_names" in active_coll_le.keys() else None))
        if intersection_coll_le is not None:
            box.label(text="Select arm (isolate one for Grab+snap):")
            row = box.row(align=True)
            for name in intersection_coll_le["rka_arm_names"]:
                row.operator("rka.select_arm", text=name).arm_name = name
            box.operator("rka.add_arm", icon='ADD', text="Add Arm (widest gap)")

        box = layout.box()
        box.label(text="Intersection (prototype)", icon='MESH_CIRCLE')
        box.operator("rka.build_intersection", icon='ADD')
        box.label(text="Builds at an active arm_*/segend_*/segbend_* marker if one is")
        box.label(text="selected, else at the 3D cursor. F9 (right after building, before")
        box.label(text="anything else) to tweak preset/radius/lanes/lane_map/traffic side.")
        box.label(text="Each arm gets an 'arm_*' Empty at its tail -- click one, then")
        box.label(text="'Extend From Arm' below, to grow a road from it.")

        box = layout.box()
        box.label(text="Straight Segment", icon='MESH_PLANE')
        box.operator("rka.build_straight_segment", icon='ADD')
        box.label(text="Curve-backed: pavement lives on a live 'spine_*' Curve object --")
        box.label(text="select it and enter Edit Mode to add/drag points and reshape/")
        box.label(text="extend the road live, no rebuild needed for the pavement itself.")
        box.label(text="Same active-marker-or-cursor start point as 'Build Intersection'.")
        box.label(text="Lanes Backward = 0 makes it one-way (1 fwd/0 back = single-lane")
        box.label(text="one-way). F9 (right after building) to tweak Bend/Vertical Bend/")
        box.label(text="Elevation Delta/curb style. Auto-Advance Cursor (on by default)")
        box.label(text="moves the cursor to this segment's end so the next build continues it.")
        box.label(text="LaneGraph auto-links coincident endpoints at bake time.")
        box.label(text="Each end gets a 'port_A'/'port_B' arrow -- click one, then 'Extend")
        box.label(text="From Port' below, to continue with the same lanes/curb settings.")

        box = layout.box()
        box.label(text="Segment From Curve", icon='CURVE_PATH')
        active = context.active_object
        if active is not None and active.type == 'CURVE':
            box.label(text="Active: '%s'" % active.name)
        else:
            box.label(text="Select a Curve object (draw one, or Add > Curve) first.")
        box.operator("rka.build_segment_from_curve", icon='ADD')
        box.label(text="Samples that curve ONCE to seed a new self-contained spine --")
        box.label(text="from then on edit the NEW 'spine_*' object's own points (Edit")
        box.label(text="Mode), not the original curve, to reshape/extend it live.")

        box = layout.box()
        box.label(text="Lane Transition (merge/drop)", icon='MOD_EDGESPLIT')
        box.operator("rka.build_lane_transition", icon='ADD')
        box.label(text="Tapers Lanes A -> Lanes B over its length (pavement + curb taper")
        box.label(text="together) -- e.g. a 2-lane street narrowing into a 1-lane arm.")
        box.label(text="Align 'Right' keeps the curb-side lane straight and merges the")
        box.label(text="rest into it (a real lane-drop); 'Left' mirrors that.")

        box = layout.box()
        box.label(text="Extend / Insert", icon='CON_FOLLOWPATH')
        active_coll = context.view_layer.active_layer_collection.collection
        active_obj = context.active_object
        is_port_empty = active_obj is not None and "rka_port" in active_obj.keys()
        is_arm_empty = active_obj is not None and "rka_arm_name" in active_obj.keys()
        is_intersection = active_coll is not None and "rka_arm_names" in active_coll.keys()
        is_segment = active_coll is not None and "rka_p0" in active_coll.keys()
        if is_port_empty:
            owner = active_obj.users_collection[0].name if active_obj.users_collection else "?"
            box.label(text="Active: port '%s' on '%s'" % (active_obj["rka_port"], owner))
            box.operator("rka.extend_from_port", icon='ADD')
            box.operator("rka.build_intersection", icon='ADD', text="Build Intersection Here")
            box.operator("rka.build_lane_transition", icon='ADD', text="Build Transition Here")
        elif is_arm_empty:
            box.label(text="Active: arm '%s' (angle %.1f deg)" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_angle", 0.0)))
            box.operator("rka.extend_from_arm", icon='ADD')
            box.operator("rka.build_intersection", icon='ADD', text="Build Intersection Here")
            box.operator("rka.build_lane_transition", icon='ADD', text="Build Transition Here")
        elif is_intersection:
            box.label(text="Active: '%s' (arms: %s)" % (active_coll.name, ", ".join(active_coll["rka_arm_names"])))
            box.label(text="(or click an 'arm_*' Empty instead of typing 'Arm' below)")
            box.operator("rka.extend_from_arm", icon='ADD')
        elif is_segment:
            box.label(text="Active: '%s' (a segment)" % active_coll.name)
            box.label(text="(or click a 'port_A'/'port_B' Empty to extend from an end")
            box.label(text="with the same lanes/curb settings)")
            box.operator("rka.insert_intersection_on_segment", icon='ADD')
        else:
            box.label(text="Activate an Intersection/Segment collection, or click an")
            box.label(text="'arm_*'/'port_*' Empty, to extend/insert here.")

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
