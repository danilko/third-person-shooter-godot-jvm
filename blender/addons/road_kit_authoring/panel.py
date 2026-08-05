"""N-panel UI: View3D > Sidebar > 'Road Kit' tab."""
import os

import bpy

from . import ops_group_edit as ge
from . import ops_intersection as opint
from . import ops_segment
from . import ops_world_session as ws
from . import paths
import session_common as sc
import piece_registry as pr

_CURB_STYLE_BUTTONS = (('NONE', "None"), ('BOX', "Box"), ('GUTTER', "Gutter"), ('ASSET', "Asset"))


def _draw_material_controls(box, coll):
    """Pavement/pad + curb material dropdowns for an EXISTING piece (intersection, GN segment, or
    lane transition) -- 2026-07-28, user-reported: material was a hardcoded literal, no way to
    change it after the initial build at all (not even F9 -- no property was ever exposed).
    `layout.operator_menu_enum` gives a clean single-dropdown picker over the full material list
    without needing dozens of buttons like `_draw_curb_style`'s few-option row does."""
    pave_key = "rka_pad_matkey" if "rka_arm_names" in coll.keys() else "rka_pave_matkey"
    cur_pave = coll.get(pave_key, "asphalt")
    cur_curb = coll.get("rka_curb_matkey", "concrete")
    box.label(text="Material:")
    row = box.row(align=True)
    row.label(text="  Pavement/Pad (%s):" % cur_pave)
    row.operator_menu_enum("rka.set_pavement_matkey", "matkey", text="Change")
    row = box.row(align=True)
    row.label(text="  Curb (%s):" % cur_curb)
    row.operator_menu_enum("rka.set_curb_matkey", "matkey", text="Change")


def _draw_curb_style(box, coll):
    """Curb Style (Left/Right) buttons for an EXISTING GN segment or lane-transition collection --
    previously the only way to change curb style after building was Blender's own F9 'Adjust Last
    Operation' panel, which stops applying the moment any other action runs; these buttons work on
    whatever piece is currently active/selected, always (see `ops_segment.RKA_OT_set_curb_style`).
    A depressed button shows the piece's CURRENT style for that side."""
    cur_l = coll.get("rka_curb_l_style", coll.get("rka_curb_style", "BOX"))
    cur_r = coll.get("rka_curb_r_style", coll.get("rka_curb_style", "BOX"))
    box.label(text="Curb Style:")
    for side_key, side_label, cur in (('L', "Left", cur_l), ('R', "Right", cur_r)):
        row = box.row(align=True)
        row.label(text="  %s:" % side_label)
        for style_key, style_label in _CURB_STYLE_BUTTONS:
            op = row.operator("rka.set_curb_style", text=style_label, depress=(cur == style_key))
            op.side, op.style = side_key, style_key
            op.asset_collection = coll.get("rka_curb_asset_collection", "")
    if 'ASSET' in (cur_l, cur_r):
        box.label(text="  Asset piece: '%s'" % coll.get("rka_curb_asset_collection", "(not set)"))
        box.label(text="  To change it: click Asset above, then set 'Curb Asset Piece' in the")
        box.label(text="  'Adjust Last Operation' panel (bottom-left of the viewport).")


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
        box.label(text="Godot Export", icon='EXPORT')
        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else ""
        if bpy.data.filepath and pr.piece_by_id(stem) is not None:
            box.operator("rka.export_to_godot", icon='EXPORT',
                          text="Export '%s' to Godot" % stem)
            box.label(text="Regenerates the lanekit sidecar + exports/bakes/navmeshes this")
            box.label(text="piece (tools/save_lane_kit.py + build_piece.sh). Watch the")
            box.label(text="System Console for progress -- takes ~20-40s.")
        else:
            box.label(text="Save as a registered piece (see pieces.json) to enable one-click export.")

        box = layout.box()
        box.label(text="Pieces", icon='WORLD')
        in_session = bpy.data.filepath == ws.SESSION_PATH
        coords = ge.current_district_coords()

        if in_session:
            wrappers = [c for c in bpy.data.collections if sc.is_wrapper(c.name)]
            dirty = [sc.piece_id_from_wrapper(c.name) for c in wrappers if c.get("rka_dirty")]
            box.label(text="World session: %d pieces, %d with unsynced edits" %
                      (len(wrappers), len(dirty)))
            if dirty:
                box.label(text="  " + ", ".join(dirty))
            box.operator("rka.jump_to_district", icon='VIEWZOOM')
            box.operator("rka.open_world_session", icon='FILE_REFRESH',
                         text="Refresh (add new / prune stale)")
            box.label(text="Also re-adds ANY registered piece missing from this file -- the")
            box.label(text="way to bring EVERYTHING back after an Unload/Unload All below.")
            row = box.row(align=True)
            row.operator("rka.load_piece", icon='HIDE_OFF', text="Load Piece")
            row.operator("rka.unload_piece", icon='HIDE_ON', text="Unload Piece")
            row.operator("rka.unload_all_pieces", icon='HIDE_ON', text="Unload All")
            box.label(text="Load/unload piece(s) in THIS file only (not deleted -- shrinks a")
            box.label(text="large session to dodge the depsgraph-scale crash risk; reload any")
            box.label(text="time). Load Piece brings back just ONE, not everything.")
            box.separator()
            box.operator("rka.writeback_world_session", icon='EXPORT',
                         text="Write Back Changed").force_all = False
            box.operator("rka.writeback_world_session", icon='EXPORT',
                         text="Write Back All").force_all = True
            box.label(text="Changed = edited since last sync (live-tracked, see the System")
            box.label(text="Console). Rebuilds + seam-checks only what's written back.")
        else:
            box.operator("rka.open_world_session", icon='WORLD', text="Open World Session")
            box.label(text="Every registered piece's content -- grid district or freestanding")
            box.label(text="alike, always the same file (world_session.blend) -- the default")
            box.label(text="way to edit anywhere without tracking which piece file is which.")

            box.separator()
            box.label(text="Scoped Group (a few pieces at a time, e.g. one seam):")
            manual_group = any(sc.is_wrapper(c.name) for c in bpy.data.collections)
            if manual_group:
                items = sorted(sc.piece_id_from_wrapper(c.name) for c in bpy.data.collections
                                if sc.is_wrapper(c.name))
                box.label(text="Group session: %s" % ", ".join(items))
                box.prop(rka, "group_extra_stems", text="")
                box.operator("rka.add_district_to_group", icon='ADD')
                box.label(text="Realize the fix reaches further? Type more piece ids above")
                box.label(text="and pull them in without restarting this session.")
                box.separator()
                box.operator("rka.writeback_district_group", icon='EXPORT')
                box.label(text="Writes each item's content back to its own file, rebuilds each,")
                box.label(text="and checks the seam for any district pair. Discard this file")
                box.label(text="when done -- it's disposable, never git-tracked.")
            elif coords is not None:
                gx, gy = coords
                box.label(text="Include neighbours (built districts only):")
                row = box.row(align=True)
                for key, dx, dy in ge.NEIGHBOR_OFFSETS:
                    stem = ge.neighbor_stem(gx + dx, gy + dy)
                    sub = row.row(align=True)
                    sub.enabled = stem is not None
                    sub.prop(rka, "group_include_%s" % key, text=key.capitalize(), toggle=True)
                box.prop(rka, "group_extra_stems", text="")
                box.label(text="^ other piece id(s) (e.g. 'Piece_2_3_b'), comma-")
                box.label(text="separated -- not just adjacent neighbours")
                box.operator("rka.open_district_group", icon='ADD')
                box.label(text="Appends this district + the checked/typed pieces' content")
                box.label(text="(roads AND ground/terrain) into one editable scratch file at")
                box.label(text="their true offsets/positions -- for reshaping geometry across a")
                box.label(text="seam, or a former overlay's touchdown ramp against a district.")
            else:
                box.label(text="Open a registered, grid-addressed piece .blend to group with")
                box.label(text="neighbours, or open the World Session above to edit any piece.")

        box.separator()
        row = box.row(align=True)
        row.operator("rka.place_piece_anchor", icon='ADD', text="Add Piece")
        row.operator("rka.remove_piece", icon='TRASH', text="Remove Piece")
        box.label(text="Add: register a new freestanding piece at the 3D cursor. Remove:")
        box.label(text="permanently delete a piece's .blend + registry entry (confirms first).")

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

        row = box.row(align=True)
        row.operator("rka.select_piece", icon='RESTRICT_SELECT_OFF')
        row.operator("rka.delete_piece", icon='TRASH')
        box.label(text="(needs something piece-related already active -- click a piece below")
        box.label(text="first if nothing is selected yet). Delete removes the WHOLE piece --")
        box.label(text="markers included, confirmation prompt first.")

        box = layout.box()
        box.label(text="Connect Pieces (live connectivity)", icon='LINKED')
        box.label(text="'Extend From Arm'/'Extend From Port' already link the new piece to the")
        box.label(text="arm/port it started from -- drag that arm/port later and the extension")
        box.label(text="follows automatically, no manual re-adjustment. To link two pieces built")
        box.label(text="separately: select the TARGET marker (arm_*/port_*/origin) first, then")
        box.label(text="Shift-click the DEPENDENT's origin marker (or arm_*) LAST so it's active,")
        row = box.row(align=True)
        row.operator("rka.connect_markers", icon='LINKED')
        row.operator("rka.disconnect_marker", icon='UNLINKED')
        box.label(text="then run Connect. Dragging a linked piece away from its target breaks")
        box.label(text="the link automatically; Disconnect breaks it without moving anything.")

        box = layout.box()
        box.label(text="Ground / Road Alignment", icon='MOD_BOOLEAN')
        box.operator("rka.cut_ground_under_road", icon='MOD_BOOLEAN')
        box.label(text="Select ALL terrain/ground meshes to cut FIRST (if the ground under a")
        box.label(text="road is split across several meshes, e.g. a visual + a separate -col")
        box.label(text="mesh, select every one -- it cuts EACH selected mesh, none are skipped")
        box.label(text="or auto-picked), then shift-click the road piece LAST so it's active,")
        box.label(text="then run. Applies a real boolean cut -- undo reverses it.")

        pieces = sorted((c for c in bpy.data.collections
                          if c.library is None and opint._is_piece_collection(c)),
                         key=lambda c: c.name)
        if pieces:
            box2 = layout.box()
            box2.label(text="Pieces in this file (%d)" % len(pieces), icon='OUTLINER_OB_EMPTY')
            box2.label(text="Click to select from nothing -- no Outliner click needed first.")
            for p in pieces:
                op = box2.operator("rka.select_piece_by_name", text=p.name)
                op.coll_name = p.name
        box.label(text="To move/rotate a WHOLE piece: select any part of it (a marker, or")
        box.label(text="even a generated curb/pad/spine), 'Select Piece' (selects every object")
        box.label(text="in it), then Grab/Rotate freely -- sets the origin marker active +")
        box.label(text="Pivot Point to 'Active Element' (the 3D cursor is never touched, so")
        box.label(text="other tools relying on it are unaffected).")
        box.label(text="Don't change Pivot Point away from 'Active Element' while rotating --")
        box.label(text="'3D Cursor'/'Median Point' both pivot on the wrong point for this addon.")

        box.operator("rka.select_road_network", icon='RESTRICT_SELECT_OFF')
        box.label(text="Moving/rotating MANY pieces at once (e.g. the whole file): 'Select")
        box.label(text="Whole Road Network' (set your own Pivot Point first, e.g. 3D Cursor at")
        box.label(text="your pivot), then Grab/Rotate/Move freely -- every piece's geometry")
        box.label(text="updates in place with no freeze step needed.")

        box.prop(rka, "show_traffic_indicators")
        box.label(text="Blue arrow = incoming (arriving) lanes, orange = outgoing")
        box.label(text="(departing) -- one pair per arm/segment end, updates live.")
        box.prop(rka, "show_lane_indices")
        box.label(text="Per-lane 'L0'/'L1'/... tags at each connection point -- independent")
        box.label(text="of the arrows above, no lanecl_* objects needed.")

        active_obj = context.active_object
        active_coll_le = context.view_layer.active_layer_collection.collection
        if active_obj is not None and "rka_arm_name" in active_obj.keys():
            row = box.row(align=True)
            row.label(text="Arm '%s': %.1f deg" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_angle", 0.0)))
            row.operator("rka.set_arm_angle", text="Set Angle...")
            row = box.row(align=True)
            row.operator("rka.nudge_arm_angle", text="-5°").delta_deg = -5.0
            row.operator("rka.nudge_arm_angle", text="-1°").delta_deg = -1.0
            row.operator("rka.nudge_arm_angle", text="+1°").delta_deg = 1.0
            row.operator("rka.nudge_arm_angle", text="+5°").delta_deg = 5.0
            row = box.row(align=True)
            row.operator("rka.aim_arm_at", text="Match Arm To Selected")
            box.label(text="(select the target first, Shift-click the arm last)")
            box.label(text="Moves this arm EXACTLY onto the target's position AND rotates it")
            box.label(text="to EXACTLY match the target's own tangent, both at once -- other")
            box.label(text="arms/the intersection center are never touched.")
            row = box.row(align=True)
            row.label(text="Lanes: %d" % active_obj.get("rka_arm_lanes", 1))
            row.operator("rka.adjust_arm_lanes", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_arm_lanes", text="", icon='ADD').delta = 1
            lanes_out = active_obj.get("rka_arm_lanes_out", 0)
            row = box.row(align=True)
            row.label(text="  Departing (asymmetric): %s" %
                       ("symmetric" if lanes_out == 0 else str(lanes_out)))
            row.operator("rka.adjust_arm_lanes_out", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_arm_lanes_out", text="", icon='ADD').delta = 1
            row = box.row(align=True)
            row.label(text="Median: %.1fm" % active_obj.get("rka_arm_median_width", 0.0))
            row.operator("rka.adjust_arm_median_width", text="", icon='REMOVE').delta = -1.0
            row.operator("rka.adjust_arm_median_width", text="", icon='ADD').delta = 1.0
            box.label(text="(this ONE arm's own median -- a segment linked here tapers its")
            box.label(text="median against this value, e.g. down to 0 on an untouched arm)")
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
            row.label(text="Fwd (start): %d" % seg_coll_le.get("rka_lanes", 1))
            row.operator("rka.adjust_segment_lanes", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_segment_lanes", text="", icon='ADD').delta = 1
            row = box.row(align=True)
            row.label(text="Back (start): %d" % seg_coll_le.get("rka_lanes_backward", 1))
            op = row.operator("rka.adjust_segment_lanes", text="", icon='REMOVE')
            op.delta, op.backward = -1, True
            op = row.operator("rka.adjust_segment_lanes", text="", icon='ADD')
            op.delta, op.backward = 1, True
        if seg_coll_le is not None and "rka_curve_object" in seg_coll_le.keys():
            row = box.row(align=True)
            row.label(text="Fwd (end): %d" % ops_segment._effective_end_lanes(seg_coll_le, False))
            row.operator("rka.adjust_segment_lanes_end", text="", icon='REMOVE').delta = -1
            row.operator("rka.adjust_segment_lanes_end", text="", icon='ADD').delta = 1
            row = box.row(align=True)
            row.label(text="Back (end): %d" % ops_segment._effective_end_lanes(seg_coll_le, True))
            op = row.operator("rka.adjust_segment_lanes_end", text="", icon='REMOVE')
            op.delta, op.backward = -1, True
            op = row.operator("rka.adjust_segment_lanes_end", text="", icon='ADD')
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
        if seg_coll_le is not None and "rka_curve_object" in seg_coll_le.keys():
            _draw_curb_style(box, seg_coll_le)
            _draw_material_controls(box, seg_coll_le)
            row = box.row(align=True)
            row.label(text="Median (start): %.2fm" % seg_coll_le.get("rka_median_width", 0.0))
            op = row.operator("rka.adjust_median_width", text="", icon='REMOVE')
            op.delta = -1.0
            op = row.operator("rka.adjust_median_width", text="", icon='ADD')
            op.delta = 1.0
            row = box.row(align=True)
            row.label(text="Median (end): %.2fm" % ops_segment._effective_end_median(seg_coll_le))
            op = row.operator("rka.adjust_median_width_end", text="", icon='REMOVE')
            op.delta = -1.0
            op = row.operator("rka.adjust_median_width_end", text="", icon='ADD')
            op.delta = 1.0

        transition_coll_le = (active_obj.users_collection[0]
                               if active_obj is not None and active_obj.users_collection
                               and "rka_lanes_a" in active_obj.users_collection[0].keys()
                               else (active_coll_le if active_coll_le is not None
                                     and "rka_lanes_a" in active_coll_le.keys() else None))
        if transition_coll_le is not None:
            for end in ('A', 'B'):
                fwd = transition_coll_le.get("rka_lanes_a" if end == 'A' else "rka_lanes_b", 1)
                bwd = transition_coll_le.get(
                    "rka_lanes_backward_a" if end == 'A' else "rka_lanes_backward_b", 0)
                row = box.row(align=True)
                row.label(text="End %s Fwd: %d" % (end, fwd))
                op = row.operator("rka.adjust_transition_lanes", text="", icon='REMOVE')
                op.end, op.delta = end, -1
                op = row.operator("rka.adjust_transition_lanes", text="", icon='ADD')
                op.end, op.delta = end, 1
                row = box.row(align=True)
                row.label(text="End %s Back: %s" % (end, "symmetric" if bwd == 0 else str(bwd)))
                op = row.operator("rka.adjust_transition_lanes", text="", icon='REMOVE')
                op.end, op.backward, op.delta = end, True, -1
                op = row.operator("rka.adjust_transition_lanes", text="", icon='ADD')
                op.end, op.backward, op.delta = end, True, 1
            _draw_curb_style(box, transition_coll_le)
            _draw_material_controls(box, transition_coll_le)

        spine_coll_le = (active_obj.users_collection[0]
                          if active_obj is not None and active_obj.users_collection
                          and "rka_curve_object" in active_obj.users_collection[0].keys()
                          else (active_coll_le if active_coll_le is not None
                                and "rka_curve_object" in active_coll_le.keys() else None))
        if spine_coll_le is not None:
            box.operator("rka.select_spine", icon='CURVE_DATA',
                          text="Select Spine ('%s')" % spine_coll_le.get("rka_curve_object", "?"))

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
            has_override = "rka_lane_map" in intersection_coll_le.keys()
            box.operator("rka.set_lane_map", icon='NODE_COMPOSITING',
                          text="Edit Lane Map Override" if has_override else "Set Lane Map Override")
            if has_override:
                box.label(text="  (override active -- clear the text field and OK to remove)")
            _draw_material_controls(box, intersection_coll_le)

        box = layout.box()
        box.label(text="Intersection (prototype)", icon='MESH_CIRCLE')
        box.operator("rka.build_intersection", icon='ADD')
        box.label(text="Builds at an active arm_*/segend_*/segbend_* marker if one is")
        box.label(text="selected, else at the 3D cursor. F9 (right after building, before")
        box.label(text="anything else) to tweak preset/radius/lanes/traffic side. Lane Map")
        box.label(text="Override can be set at any time after, below.")
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
        box.label(text="Lane-count TAPER (was the separate 'Lane Transition' tool): F9 after")
        box.label(text="building, set 'Lanes Forward/Backward (End)' -- e.g. a 2-lane street")
        box.label(text="narrowing into 1 -- Align 'Right' keeps the curb-side lane straight")
        box.label(text="and merges the rest into it, 'Left' mirrors that. 'Median/Sidewalk")
        box.label(text="Width (End)' taper the separation/sidewalk width the same way, even")
        box.label(text="with lane count unchanged. 'Extend From Arm'/'Extend From Port' below")
        box.label(text="have the same End fields, for starting a taper exactly at a marker.")

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
        elif is_arm_empty:
            box.label(text="Active: arm '%s' (angle %.1f deg)" %
                       (active_obj["rka_arm_name"], active_obj.get("rka_arm_angle", 0.0)))
            box.operator("rka.extend_from_arm", icon='ADD')
            box.operator("rka.build_intersection", icon='ADD', text="Build Intersection Here")
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
