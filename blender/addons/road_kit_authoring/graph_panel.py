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
                             "aux_median_left", "aux_median_right")),
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
        col.operator("rka.graph_init_attrs", icon='FILE_REFRESH')
        # Build = solve + carrier + stack. Solve alone is offered too, for checking the topology
        # report (width steps, too-short edges) without paying for the geometry.
        col.operator("rka.graph_build", icon='MOD_BUILD')
        col.operator("rka.graph_solve", icon='MOD_SIMPLIFY')
        col.operator("rka.graph_validate", icon='CHECKMARK')
        col.operator("rka.graph_weld_crossings", icon='AUTOMERGE_ON')
        col.operator("rka.graph_auto_aux", icon='MOD_ARRAY')
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
            layout.label(text="Enter Edit Mode to author edges and nodes", icon='INFO')
            return

        for label, icon, names in GROUPS:
            box = layout.box()
            box.label(text=label, icon=icon)
            for name in names:
                row = box.row(align=True)
                row.prop(s, "use_%s" % name)
                sub = row.row(align=True)
                sub.enabled = getattr(s, "use_%s" % name)
                sub.prop(s, name)

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
        box.label(text="Active edge %d" % edge.index, icon='EDGESEL')
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


def _oneway(v):
    return int(v.get("lanes_bwd", 0)) + int(v.get("aux_lanes_right", 0)) == 0


CLASSES = (RKA_PT_road_graph,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
