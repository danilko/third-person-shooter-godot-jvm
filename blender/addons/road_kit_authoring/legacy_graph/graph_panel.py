"""graph_panel.py -- the Road Graph N-panel UI.

Kept separate from `graph_attrs.py` (which owns the data) and `graph_solve.py` (which owns the
maths) so a layout change can never alter behaviour. The panel's whole job is to make the
authoring loop legible: STAMP attributes on edges/nodes, SOLVE, then read the result back.
"""
import bmesh
import bpy

from . import graph_assets as gas
from . import graph_attrs as ga

#: Brush fields grouped for display. Flat lists of eleven-plus properties are unreadable, and the
#: grouping is also the mental model: a road is a carriageway, a median, kerbs+footways, and a
#: structure underneath.
GROUPS = (
    ("Carriageway", 'AUTO', ("lanes_fwd", "lanes_bwd", "lane_width",
                             "aux_lanes_left", "aux_lanes_right", "aux_taper_length",
                             "aux_buffer_length", "lane_transition_length")),
    ("Median", 'MOD_MASK', ("median_type", "median_width", "median_asset_idx")),
    ("Kerb + Footway", 'MOD_BEVEL', ("curb_left_on", "curb_right_on", "curb_height",
                                     "sidewalk_left_width", "sidewalk_right_width",
                                     "curb_asset_idx", "sidewalk_asset_idx")),
    ("Structure", 'MESH_CYLINDER', ("deck_thickness", "pillar_spacing", "pillar_width",
                                    "ground_z", "pillar_asset_idx")),
    ("Rows", 'OUTLINER_OB_POINTCLOUD', ("asset_spacing", "rail_asset_idx", "prop_asset_idx")),
)


class RKA_PT_road_graph(bpy.types.Panel):
    bl_label = "Road Graph"
    bl_idname = "RKA_PT_road_graph"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Road Kit"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        s = context.scene.rka_graph

        col = layout.column(align=True)
        # FIRST, because it is the answer to "I clicked the road and nothing can be edited": the
        # graph is a wireframe under the swept surface, so a click always lands on the carrier.
        col.operator("rka.graph_edit", icon='EDITMODE_HLT')
        col.operator("rka.graph_init_attrs", icon='FILE_REFRESH')
        # Build = solve + carrier + stack. Solve alone is offered too, for checking the topology
        # report (width steps, too-short edges) without paying for the geometry.
        row = col.row(align=True)
        row.operator("rka.graph_build", icon='MOD_BUILD')
        row.prop(s, "stage_edge_furniture", text="", icon='MOD_OUTLINE')
        col.operator("rka.graph_solve", icon='MOD_SIMPLIFY')
        col.operator("rka.graph_validate", icon='CHECKMARK')
        col.operator("rka.graph_weld_crossings", icon='AUTOMERGE_ON')
        col.operator("rka.graph_auto_aux", icon='MOD_ARRAY')
        col.operator("rka.graph_ramp_aux", icon='AUTOMERGE_ON')
        row = col.row(align=True)
        row.operator("rka.graph_preview_lanes", icon='CURVE_PATH')
        row.operator("rka.graph_export_lanekit", icon='EXPORT', text="")
        row.operator("rka.graph_explain_node", icon='QUESTION', text="")

        box = layout.box()
        row = box.row(align=True)
        row.prop(s, "overlay_on", text="", icon='OVERLAY')
        sub = row.row(align=True)
        sub.enabled = s.overlay_on
        sub.prop(s, "overlay_mode", text="")
        sub.prop(s, "overlay_width", text="")

        if context.edit_object is None or context.edit_object.type != 'MESH':
            # WHY THE BRUSH IS NOT SHOWN, and what to press. Attributes live on edges and
            # vertices, so there is nothing to stamp until edges can be selected -- but "no fields
            # at all" reads as a broken panel rather than as a mode.
            box = layout.box()
            graph = ga.graph_object(context)
            box.label(text="Edge + node settings need Edit Mode", icon='INFO')
            if graph is not None:
                box.label(text="graph: %s" % graph.name, icon='MESH_DATA')
            box.operator("rka.graph_edit", icon='EDITMODE_HLT')
            return
        if context.edit_object.get(ga.GENERATED_TAG):
            # Editing the swept output: a stamp here is rejected (`reject_generated`), and saying
            # so up front beats letting the artist set eight fields and press a dead button.
            box = layout.box()
            box.alert = True
            box.label(text="'%s' is generated geometry" % context.edit_object.name, icon='ERROR')
            box.label(text="its edges are overwritten by every Build")
            box.operator("rka.graph_edit", icon='EDITMODE_HLT')
            return

        # ONE LANE MORE / ONE LANE LESS, without the brush. The commonest edit there is, and
        # through the brush it is four steps and a chance to overwrite the median by accident.
        box = layout.box()
        box.label(text="Lanes on selected edges", icon='SNAP_MIDPOINT')
        for name, label in ga.NUDGE_FIELDS:
            row = box.row(align=True)
            row.label(text=label)
            op = row.operator("rka.graph_nudge", text="", icon='REMOVE')
            op.field, op.delta = name, -1
            op = row.operator("rka.graph_nudge", text="", icon='ADD')
            op.field, op.delta = name, 1

        for label, icon, names in GROUPS:
            box = layout.box()
            box.label(text=label, icon=icon)
            for name in names:
                row = box.row(align=True)
                row.prop(s, "use_%s" % name)
                sub = row.row(align=True)
                sub.enabled = getattr(s, "use_%s" % name)
                sub.prop(s, name)

        # WHAT ASSIGN IS ABOUT TO WRITE, spelled out. Every field is stamped or not by its own
        # tick, and eight of them are ticked by default -- so a stamp meant to change the lane
        # count also rewrites the median and the footways with whatever the brush happens to hold.
        # That is the single most confusing thing this UI can do, and the fix is to say it.
        writes = sorted(ga.brush_edge_values(s))
        info = layout.row()
        info.alert = not writes
        info.label(text=("writes: " + ", ".join(writes)) if writes
                   else "no fields ticked -- Assign will do nothing",
                   icon='GREASEPENCIL' if writes else 'ERROR')
        row = layout.row(align=True)
        row.operator("rka.graph_assign_edges", icon='CHECKMARK')
        row.operator("rka.graph_pick_edge", icon='EYEDROPPER', text="")
        # Shown right next to Assign because it decides whether Assign appears to do anything.
        row.prop(s, "auto_build", text="", icon='FILE_REFRESH', toggle=True)

        box = layout.box()
        box.label(text="Select", icon='RESTRICT_SELECT_OFF')
        row = box.row(align=True)
        row.operator("rka.graph_select_road", icon='PARTICLE_PATH')
        row.operator("rka.graph_tag_road", icon='TAG', text="")
        box.operator("rka.graph_select_similar", icon='SELECT_SET')

        self._draw_active_edge(layout, context)

        box = layout.box()
        box.label(text="Node (vertex)", icon='VERTEXSEL')
        box.prop(s, "node_type")
        box.prop(s, "node_radius")
        box.prop(s, "fillet_radius")
        box.prop(s, "allow_cross")
        box.operator("rka.graph_assign_verts", icon='CHECKMARK')

        box = layout.box()
        box.label(text="Asset Palettes", icon='ASSET_MANAGER')
        box.operator("rka.graph_assets_link_kit", icon='LINKED')
        box.operator_menu_enum("rka.graph_assets_add_selected", "role",
                               text="Add Active Collection")
        for role in gas.ROLE_NAMES:
            box.label(text="  %s: %d" % (gas.ROLE_LABEL[role], len(gas.catalog(role))))

    def _draw_active_edge(self, layout, context):
        """The brush shows what you are ABOUT to write; this shows what the edge actually holds.
        Conflating those two is how a stamping UI silently lies about the file's contents."""
        try:
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            edge = next((el for el in reversed(bm.select_history)
                         if isinstance(el, bmesh.types.BMEdge)), None)
            if edge is None:
                return
            v = ga.read_edge(bm, edge, ga.ensure_edge_layers(bm, fill_defaults=False))
        except (AttributeError, ReferenceError, TypeError, KeyError):
            return
        box = layout.box()
        # THE NODE NUMBERS, because every report the kit prints is keyed by node index ("2 ramps
        # run offside: node 377", "width step at node 776") and there was no way to find out which
        # node you were looking at from the viewport. These are the two ends of the edge you have
        # selected -- paste one into Explain Node.
        box.label(text="Active edge %d  (nodes %d - %d)"
                  % (edge.index, edge.verts[0].index, edge.verts[1].index), icon='EDGESEL')
        col = box.column(align=True)
        col.label(text="%dF/%dB (+%d/%d aux) x %.2fm%s"
                  % (v.get("lanes_fwd", 0), v.get("lanes_bwd", 0),
                     v.get("aux_lanes_left", 0), v.get("aux_lanes_right", 0),
                     v.get("lane_width", 0.0),
                     "  ONE-WAY" if _oneway(v) else ""))
        col.label(text="median %s %.2fm | kerb L%s R%s h%.2f"
                  % (ga.MEDIAN_INT_TO_TYPE.get(int(v.get("median_type", 0)), "?"),
                     v.get("median_width", 0.0),
                     "on" if v.get("curb_left_on", 1) else "off",
                     "on" if v.get("curb_right_on", 1) else "off",
                     v.get("curb_height", 0.0)))
        col.label(text="walk L%.2f R%.2f | deck %.2f | pillars %.1fm"
                  % (v.get("sidewalk_left_width", 0.0), v.get("sidewalk_right_width", 0.0),
                     v.get("deck_thickness", 0.0), v.get("pillar_spacing", 0.0)))
        col.label(text="solved: trim %.2f / %.2f, half %.2f"
                  % (v.get("trim_start", 0.0), v.get("trim_end", 0.0),
                     v.get("paved_half", 0.0)))
        for role in gas.ROLE_NAMES:
            idx = int(v.get("%s_asset_idx" % role, -1))
            if idx >= 0:
                col.label(text="  %s: %s" % (role, gas.name_at(role, idx) or "<missing #%d>" % idx))
        # IS THIS A RAMP, AND WHAT WOULD IT MERGE INTO? Only asked for a one-way edge, because
        # that is the only kind that can be one, and only from the cached solve -- the readout is
        # drawn on every redraw and must never solve the graph itself.
        if _oneway(v):
            from . import graph_solve as gsolve
            col.label(text="ramp: %s" % gsolve.explain_ramp(context.edit_object, edge.index),
                      icon='AUTOMERGE_ON')


def _oneway(v):
    return int(v.get("lanes_bwd", 0)) + int(v.get("aux_lanes_right", 0)) == 0


CLASSES = (RKA_PT_road_graph,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
