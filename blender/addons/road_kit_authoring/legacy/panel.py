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

_CURB_STYLE_BUTTONS = (('NONE', "None"), ('PROFILE', "Profile"))
_MEDIAN_STYLE_BUTTONS = (('NONE', "None"), ('PROFILE', "Profile"))

# Fallback default asset pieces, used ONLY by the CURB/MEDIAN STYLE button rows (NONE/PROFILE) when
# clicking 'Profile' on a piece/side that has never had its own asset name set (the custom property
# is absent/blank) -- 2026-07/08, user-reported: without this, clicking 'Asset' (the style
# PROFILE's picker-and-fallback machinery was inherited from, see CURB_STYLE_ITEMS' own retirement
# comment) silently built NOTHING (the resolved object is None, same "no piece = no geometry"
# convention every build_*/populate_* function already has) -- which reads as "the button doesn't
# work" rather than a style change, since there's no error either. Every "Profile" style-button call
# below falls back to these whenever the CURRENT value is blank; an already-set value is always
# preferred, so re-clicking never clobbers a deliberately-chosen piece. Sidewalk/Prop/Traffic-Light
# no longer need an equivalent -- those are picked directly via a real dropdown (`RKA_OT_pick_*`,
# see `linked_asset_picker_items`) that lists every real choice, so there's no "first click on a
# field with nothing set" case left to default around.
_CURB_ASSET_DEFAULT = "Kit_Curb_JerseyBarrier_L2"
_MEDIAN_ASSET_DEFAULT = "Kit_Median_YellowSeparator"


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
    A depressed button shows the piece's CURRENT style for that side.

    The Asset PIECE itself (shared by both sides -- `rka_curb_asset_collection` is one value for
    the whole piece) is a real DROPDOWN (`RKA_OT_pick_curb_asset`, `operator_menu_enum`) --
    2026-08, user-requested: "is it possible to also do drop down selection on asset or none,
    instead of current 'Set' and try use the op[era]tional panel and seem not unset/remove
    completely." A menu listing every linked kit piece plus 'None', always visible once the side is
    'Profile' (picking a real piece also switches style to 'Profile' automatically, so it can be
    used from 'None' directly too)."""
    cur_l = coll.get("rka_curb_l_style", coll.get("rka_curb_style", "NONE"))
    cur_r = coll.get("rka_curb_r_style", coll.get("rka_curb_style", "NONE"))
    cur_asset = coll.get("rka_curb_asset_collection", "")
    box.label(text="Curb Style:")
    for side_key, side_label, cur in (('L', "Left", cur_l), ('R', "Right", cur_r)):
        row = box.row(align=True)
        row.label(text="  %s:" % side_label)
        for style_key, style_label in _CURB_STYLE_BUTTONS:
            op = row.operator("rka.set_curb_style", text=style_label, depress=(cur == style_key))
            op.side, op.style = side_key, style_key
            # See the module-level "fallback default asset pieces" comment -- the FIRST click on
            # Profile (no piece ever set) must build something real, not silently nothing.
            op.asset_collection = cur_asset or (_CURB_ASSET_DEFAULT if style_key == 'PROFILE' else "")
    row = box.row(align=True)
    row.label(text="  Asset piece: '%s'" % (cur_asset or "(none)"))
    row.operator_menu_enum("rka.pick_curb_asset", "collection_name", text="Pick")


def _draw_median_style(box, coll):
    """Median Style button row for an EXISTING GN segment/lane-transition collection -- median
    style previously had NO persistent control at all (build-time F9 only), unlike curb style
    above it and median WIDTH below it (see `RKA_OT_set_median_style`). Two styles only (2026-08,
    user-requested: "median should always be single, but just the mesh + distance between...
    remove all choice and just load from asset too", later "only have none/profile... to simplify
    the code base" -- collapsed from an earlier BOX/GUTTER/ASSET-dual/SINGLE-procedural/profile-
    silhouette/discrete-ASSET set this session had grown through, down to just NONE and PROFILE --
    see `MEDIAN_STYLE_ITEMS`).

    2026-08 follow-up (user-reported: switching to 'Asset' still showed the old two-wall look): a
    piece that had never used an asset style before had no `rka_median_asset_collection` set at
    all, so clicking it silently built NOTHING (no error, no visible change) -- easy to read as
    "the button doesn't work." The 'Profile' button now falls back to `_MEDIAN_ASSET_DEFAULT`
    whenever no piece is already set, so clicking it always produces SOME visible geometry
    immediately; the existing value is still preferred whenever one is already set, so re-clicking
    never clobbers a deliberately-chosen piece. The Asset PIECE itself is a real dropdown
    (`RKA_OT_pick_median_asset`) -- see `_draw_curb_style`'s docstring for the shared rationale."""
    cur = coll.get("rka_median_style", "NONE")
    cur_asset = coll.get("rka_median_asset_collection", "")
    box.label(text="Median Style:")
    row = box.row(align=True)
    for style_key, style_label in _MEDIAN_STYLE_BUTTONS:
        op = row.operator("rka.set_median_style", text=style_label, depress=(cur == style_key))
        op.style = style_key
        op.asset_collection = cur_asset or (_MEDIAN_ASSET_DEFAULT if style_key == 'PROFILE' else "")
    row = box.row(align=True)
    row.label(text="  Asset piece: '%s'" % (cur_asset or "(none)"))
    row.operator_menu_enum("rka.pick_median_asset", "collection_name", text="Pick")
    if cur == 'PROFILE' and cur_asset and bpy.data.collections.get(cur_asset) is None:
        box.label(text="  WARNING: '%s' isn't linked in this file (yet) -- click 'Link Curb"
                   % cur_asset)
        box.label(text="  Kit Library' below, this row updates on the next rebuild/redraw.")


def _draw_intersection_curb_and_sidewalk(box, coll):
    """Curb Style + Sidewalk + Traffic Light controls for an EXISTING intersection collection --
    2026-08, user-reported: intersections had none of these persistently (only Material), unlike
    segments which already had curb style / median / sidewalk / props all as live panel controls.
    One value for the WHOLE intersection in every case (curb style, sidewalk width/asset piece,
    traffic light asset piece) -- not per-side/per-arm, since a corner isn't a single 2-endpoint
    direction the way a segment is (an individual arm's OWN median AND its own Traffic Light
    on/off already have per-arm controls elsewhere, via the active arm row -- not duplicated
    here).

    2026-08 follow-up (user-reported: sidewalks "result in strange half bake", and "will it be
    simpler... just follow the asset library ones" + "remove the lamp logic for intersection, but
    rather leave called 'traffic light'"): the old spaced prop row (a street-lamp asset repeated
    along the sidewalk) is GONE -- replaced by a Sidewalk Asset piece picker (tiles a real kit
    mesh along the sidewalk instead of a procedural sweep, still one value for the whole
    intersection) and a Traffic Light Asset piece picker (which mesh a per-arm-enabled signal
    uses -- see the active-arm 'Traffic Light' toggle for turning it on per arm)."""
    cur_curb = coll.get("rka_curb_style", "NONE")
    cur_curb_asset = coll.get("rka_curb_asset_collection", "")
    box.label(text="Curb Style:")
    row = box.row(align=True)
    for style_key, style_label in _CURB_STYLE_BUTTONS:
        op = row.operator("rka.set_curb_style", text=style_label, depress=(cur_curb == style_key))
        op.style = style_key
        # See the module-level "fallback default asset pieces" comment.
        op.asset_collection = cur_curb_asset or (_CURB_ASSET_DEFAULT if style_key == 'PROFILE' else "")
    row = box.row(align=True)
    row.label(text="  Asset piece: '%s'" % (cur_curb_asset or "(none)"))
    row.operator_menu_enum("rka.pick_curb_asset", "collection_name", text="Pick")

    cur_sw = coll.get("rka_sidewalk_width", 0.0)
    row = box.row(align=True)
    row.label(text="Sidewalk: %.2fm" % cur_sw)
    op = row.operator("rka.adjust_intersection_sidewalk_width", text="", icon='REMOVE')
    op.delta = -1.0
    op = row.operator("rka.adjust_intersection_sidewalk_width", text="", icon='ADD')
    op.delta = ops_segment.DEFAULT_SIDEWALK_WIDTH if cur_sw <= 0.0 else 1.0

    cur_sw_asset = coll.get("rka_sidewalk_asset_collection", "")
    row = box.row(align=True)
    row.label(text="  Asset piece: '%s'" % (cur_sw_asset or "(procedural)"))
    row.operator_menu_enum("rka.pick_intersection_sidewalk_asset", "collection_name", text="Pick")
    if cur_sw_asset:
        row = box.row(align=True)
        row.label(text="    every %.1fm" % coll.get("rka_sidewalk_asset_spacing", 2.0))
        row.operator("rka.adjust_intersection_sidewalk_asset_spacing", text="", icon='REMOVE').delta = -0.5
        row.operator("rka.adjust_intersection_sidewalk_asset_spacing", text="", icon='ADD').delta = 0.5

    cur_light_asset = coll.get("rka_traffic_light_asset_collection", "")
    row = box.row(align=True)
    row.label(text="Traffic Light Asset: '%s'" % (cur_light_asset or "(none)"))
    row.operator_menu_enum("rka.pick_intersection_traffic_light_asset", "collection_name", text="Pick")
    box.label(text="  Picking a piece here auto-enables every arm the first time (no arm on yet);")
    box.label(text="  toggle individual arms via 'Traffic Light: OFF' on the active arm row above.")


def _draw_sidewalk_and_props(box, coll):
    """Sidewalk width/asset + street-lamp/prop row controls for an EXISTING plain GN segment --
    all three fields have been full build-time properties for a while
    (`RKA_OT_build_straight_segment`'s `sidewalk_l/r_width`, `sidewalk_l/r_asset_collection`,
    `prop_l/r_asset_collection` + spacing) but, like median style above, only ever settable via
    the F9 redo panel -- 0 width / a blank asset name is already the documented 'off'/'procedural'
    state (`_populate_segment_mesh_gn`), this just makes turning it on/off after the fact
    discoverable (see `RKA_OT_adjust_sidewalk_width`/`_end`, `RKA_OT_set_sidewalk_asset`,
    `RKA_OT_adjust_sidewalk_asset_spacing`, `RKA_OT_set_prop_asset`, `RKA_OT_adjust_prop_spacing`).

    2026-08, user-requested ("will it be simpler and easily to regenerate all curb/side way from
    asset... just follow the asset library ones"): the sidewalk asset piece is a per-side pick
    (mirrors curb, which is also per-side) but SHARES one spacing value across both sides -- a
    sidewalk tile is normally a symmetric slab, unlike a prop, so a single spacing knob is enough
    and matches how `sidewalk_asset_spacing` is stored (one collection-level property, not L/R)."""
    box.label(text="Sidewalk:")
    for side_key, side_label in (('L', "Left"), ('R', "Right")):
        start_key = "rka_sidewalk_l_width" if side_key == 'L' else "rka_sidewalk_r_width"
        cur_w = coll.get(start_key, 0.0)
        row = box.row(align=True)
        row.label(text="  %s (start): %.2fm" % (side_label, cur_w))
        op = row.operator("rka.adjust_sidewalk_width", text="", icon='REMOVE')
        op.side, op.delta = side_key, -1.0
        op = row.operator("rka.adjust_sidewalk_width", text="", icon='ADD')
        # First click (currently 0/off) jumps straight to a real, usable sidewalk width instead of
        # +1m -- 2026-08, user-requested: "default to 3.5 meters/4 meters... instead of adding".
        # Every click after that is a plain +1m fine-tune, same as before.
        op.side, op.delta = side_key, (ops_segment.DEFAULT_SIDEWALK_WIDTH if cur_w <= 0.0 else 1.0)
        cur_w_end = ops_segment._effective_end_sidewalk(coll, side_key)
        row = box.row(align=True)
        row.label(text="  %s (end): %.2fm" % (side_label, cur_w_end))
        op = row.operator("rka.adjust_sidewalk_width_end", text="", icon='REMOVE')
        op.side, op.delta = side_key, -1.0
        op = row.operator("rka.adjust_sidewalk_width_end", text="", icon='ADD')
        op.side, op.delta = side_key, (ops_segment.DEFAULT_SIDEWALK_WIDTH if cur_w_end <= 0.0 else 1.0)
        asset_key = ("rka_sidewalk_l_asset_collection" if side_key == 'L'
                     else "rka_sidewalk_r_asset_collection")
        cur_sw_asset = coll.get(asset_key, "")
        row = box.row(align=True)
        row.label(text="    Asset: '%s'" % (cur_sw_asset or "(procedural)"))
        pick_idname = ("rka.pick_sidewalk_asset_l" if side_key == 'L'
                        else "rka.pick_sidewalk_asset_r")
        row.operator_menu_enum(pick_idname, "collection_name", text="Pick")

    cur_sw_spacing = coll.get("rka_sidewalk_asset_spacing", 2.0)
    row = box.row(align=True)
    row.label(text="  Sidewalk asset spacing: every %.1fm" % cur_sw_spacing)
    row.operator("rka.adjust_sidewalk_asset_spacing", text="", icon='REMOVE').delta = -0.5
    row.operator("rka.adjust_sidewalk_asset_spacing", text="", icon='ADD').delta = 0.5

    box.label(text="Street Lamps / Props (along sidewalk, or curb with none):")
    for side_key, side_label in (('L', "Left"), ('R', "Right")):
        asset_key = "rka_prop_l_asset_collection" if side_key == 'L' else "rka_prop_r_asset_collection"
        spacing_key = "rka_prop_l_spacing" if side_key == 'L' else "rka_prop_r_spacing"
        cur_asset = coll.get(asset_key, "")
        row = box.row(align=True)
        row.label(text="  %s: '%s'" % (side_label, cur_asset or "(none)"))
        pick_idname = "rka.pick_prop_asset_l" if side_key == 'L' else "rka.pick_prop_asset_r"
        row.operator_menu_enum(pick_idname, "collection_name", text="Pick")
        row = box.row(align=True)
        row.label(text="    every %.1fm" % coll.get(spacing_key, 30.0))
        op = row.operator("rka.adjust_prop_spacing", text="", icon='REMOVE')
        op.side, op.delta = side_key, -1.0
        op = row.operator("rka.adjust_prop_spacing", text="", icon='ADD')
        op.side, op.delta = side_key, 1.0
    box.label(text="  'Pick' opens a dropdown of every linked piece, plus 'None' -- link the")
    box.label(text="  kit library below first.")


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
        box.label(text="'Kit_Curb_JerseyBarrier_L2'). Same library/link button for Median Style")
        box.label(text="= 'Single' -- try 'Kit_Median_YellowSeparator' or 'Kit_Median_Island'.")

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
            cur_light = active_obj.get("rka_arm_traffic_light", False)
            row = box.row(align=True)
            row.operator("rka.toggle_arm_traffic_light",
                          text="Traffic Light: ON" if cur_light else "Traffic Light: OFF",
                          depress=cur_light)
            if cur_light:
                row = box.row(align=True)
                row.label(text="  Offset: %.1fm beyond corner" %
                           active_obj.get("rka_arm_traffic_light_radius", 3.5))
                row.operator("rka.adjust_arm_traffic_light_radius", text="", icon='REMOVE').delta = -0.5
                row.operator("rka.adjust_arm_traffic_light_radius", text="", icon='ADD').delta = 0.5
                box.label(text="(needs a piece set under 'Traffic Light Asset' below)")
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
            _draw_median_style(box, seg_coll_le)
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
        if seg_coll_le is not None and "rka_lanes_a" not in seg_coll_le.keys() \
                and "rka_curve_object" in seg_coll_le.keys():
            # Sidewalk/props are plain-segment-only (see `_draw_sidewalk_and_props`'s docstring) --
            # excluded here even though this branch's own outer `seg_coll_le` gate (rka_p0) doesn't
            # distinguish plain segments from transitions, unlike curb/median style above (which DO
            # apply to transitions, hence no such exclusion there).
            _draw_sidewalk_and_props(box, seg_coll_le)

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
            # No _draw_median_style here: `_populate_transition_visuals` never reads
            # `median_edges`/builds median geometry at all (a transition's median, if any, is
            # width-only bookkeeping) -- a style selector here would have no visual effect.

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
            _draw_intersection_curb_and_sidewalk(box, intersection_coll_le)

        box = layout.box()
        box.label(text="Intersection (prototype)", icon='MESH_CIRCLE')
        box.operator("rka.build_intersection", icon='ADD')
        box.label(text="Builds at an active arm_*/segend_*/segbend_* marker if one is")
        box.label(text="selected, else at the 3D cursor. F9 (right after building, before")
        box.label(text="anything else) to tweak preset/radius/lanes/traffic side. Lane Map")
        box.label(text="Override can be set at any time after, below.")
        box.label(text="Each arm gets an 'arm_*' Empty at its tail -- click one, then")
        box.label(text="'Extend From Arm' below, to grow a road from it.")
        box.label(text="Sidewalk Width/Prop Asset (F9 after building) add a corner sidewalk +")
        box.label(text="street-lamp row around every arm -- 0/blank (default) = neither, same")
        box.label(text="convention as a segment's own Sidewalk/Prop fields below.")

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

        # RAMPS. `rka.build_line_split`/`build_line_merge` have existed and been registered since
        # `ops_split.py` landed, and were reachable ONLY from the F3 operator search -- so from the
        # panel there was no way to make an exit ramp at all, or to reach the four dials that
        # decide its shape (user-reported 2026-08-15: "seem not able to control how the exit ramp
        # is created"). The operators were never the missing part; the buttons were.
        box = layout.box()
        box.label(text="Ramps: Split / Merge", icon='IPO_EASE_IN_OUT')
        curves = [o for o in context.selected_objects if o.type == 'CURVE']
        if len(curves) >= 3:
            box.label(text="Selected curves: %s" % ", ".join(o.name for o in curves[:3]))
        else:
            box.label(text="Select THREE curves: a trunk and two branches.")
            box.label(text="Split: trunk first.   Merge: trunk LAST.")
        col = box.column()
        col.enabled = len(curves) >= 3
        col.operator("rka.build_line_split", icon='ADD')
        col.operator("rka.build_line_merge", icon='ADD')
        box.label(text="An off-ramp is 'Trunk Lanes' one BELOW the branch total --")
        box.label(text="that tapers the auxiliary lane in. Auxiliary Length,")
        box.label(text="Taper Length and Gore Nose shape it (F9 to adjust).")

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
        box.label(text="Lane Data Preview", icon='CURVE_DATA')
        box.label(text="Build a real curve per exported lane (every piece in this file), from")
        box.label(text="the SAME data tools/save_lane_kit.py writes to .lanekit.json -- a way to")
        box.label(text="eyeball the actual ported Path3D shape before exporting. Manual/on-")
        box.label(text="demand (not live-synced) -- Clear removes them again, no trace left.")
        row = box.row(align=True)
        row.operator("rka.preview_lane_curves", icon='CURVE_DATA', text="Preview Lane Curves")
        row.operator("rka.clear_lane_curve_preview", icon='X', text="Clear")

        box = layout.box()
        box.label(text="Lane Ports (per-lane connection points)", icon='TRACKING_FORWARDS')
        box.label(text="One marker per LANE END, on that lane's own centreline, with an arrow")
        box.label(text="pointing the way its traffic drives -- 'lp_IN_*' enters the piece,")
        box.label(text="'lp_OUT_*' leaves it. A two-way road end shows both, so which way")
        box.label(text="traffic goes through a connection is visible instead of guessed.")
        box.label(text="Opt-in per piece: Show builds them for the selection, and every")
        box.label(text="rebuild then keeps them on the geometry. Hide removes them again.")
        row = box.row(align=True)
        row.operator("rka.show_lane_ports", icon='TRACKING_FORWARDS', text="Show Lane Ports")
        row.operator("rka.hide_lane_ports", icon='X', text="Hide")
        sel_ports = [o for o in context.selected_objects if "rka_lane_port" in o.keys()]
        if len(sel_ports) == 2:
            act = context.view_layer.objects.active
            if act is not None and "rka_lane_port" in act.keys():
                box.label(text="Moving: %s (%s)" % (act.name, act.get("rka_lane_port")))
        else:
            box.label(text="Select TWO lane ports to snap (active one = the end that moves)")
        box.operator("rka.snap_lane_to_lane", icon='SNAP_ON', text="Snap Lane To Lane")

        box = layout.box()
        box.label(text="Joint Alignment", icon='SNAP_MIDPOINT')
        box.label(text="Touching is not connecting. A link only counts when the two lanes'")
        box.label(text="ribbon EDGES meet -- left on left, right on right. Coincident")
        box.label(text="centrelines still leave a seam if the widths differ, the heading")
        box.label(text="breaks, or the pair is head-on. Reports every seam in metres,")
        box.label(text="worst first; same check the export gate runs.")
        box.operator("rka.check_joint_alignment", icon='CHECKMARK',
                     text="Check Joint Alignment")

        box = layout.box()
        box.label(text="Road Geometry", icon='IPO_EASE_IN_OUT')
        box.label(text="Can a car actually drive this? Reports GRADE (too steep), KINK")
        box.label(text="(missing vertical curve), RADIUS (too tight to bank) and CORNER")
        box.label(text="(one control point turning too sharply -- a facet in the swept")
        box.label(text="pavement, which no radius test can see: it averages over a window).")
        box.label(text="Drops a marker stick at each finding. Smoothing is NOT the fix --")
        box.label(text="it moves control points the seams and lane export depend on.")
        row = box.row(align=True)
        row.operator("rka.check_road_geometry", icon='CHECKMARK', text="Check Road Geometry")
        row.operator("rka.clear_geometry_warnings", icon='X', text="Clear")

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
