"""graph_overlay.py -- draw the road graph's authored values as coloured lines in the viewport.

THE PROBLEM THIS SOLVES. A mesh graph shows you topology and nothing else: 1600 identical grey
edges, every one of which carries a different cross-section you cannot see. The old per-piece model
at least named its pieces in the outliner. Without feedback the authoring loop is "stamp, build,
squint at the result, guess which edge was wrong" -- so the values are drawn directly on the graph,
in Edit Mode, where the decisions are made.

WHY A GPU OVERLAY RATHER THAN A COLOUR ATTRIBUTE. Blender renders colour attributes on the FACE
and POINT domains; a road graph is all edges and has no faces at all, so there is nothing for a
material to shade. A draw handler is the only way to tint an edge by an edge-domain value.

It is deliberately read-only and stateless: it reads the live edit-mesh every redraw and owns no
cached copy that could disagree with what the artist just stamped.
"""
import bmesh
import bpy

from . import graph_attrs as ga

_handle = None

#: Colour ramp for lane counts -- deliberately few, distinct steps rather than a smooth gradient.
#: The question an artist asks is "is this a 2-lane or a 4-lane?", which a continuous ramp answers
#: worse than six flat colours do.
_LANE_COLORS = (
    (0.45, 0.45, 0.50),      # 0-1  alley
    (0.25, 0.65, 0.95),      # 2    local
    (0.20, 0.85, 0.45),      # 3-4  collector
    (0.95, 0.80, 0.20),      # 5-6  arterial
    (0.95, 0.45, 0.15),      # 7-8  major
    (0.95, 0.20, 0.30),      # 9+   motorway
)

MODES = (
    ('LANES', "Lanes", "Total lane count, including aux lanes"),
    ('ROAD', "Road Id", "One colour per road_id; grey where untagged"),
    ('AUX', "Aux + Median", "Aux lanes red, raised median green, painted median yellow"),
    ('STRUCTURE', "Structure", "Deck thickness and pillar rows"),
)


def _lane_color(attrs):
    n = (int(attrs.get("lanes_fwd", 0)) + int(attrs.get("lanes_bwd", 0))
         + int(attrs.get("aux_lanes_left", 0)) + int(attrs.get("aux_lanes_right", 0)))
    return _LANE_COLORS[min(max(n, 0) // 2, len(_LANE_COLORS) - 1)]


def _road_color(attrs):
    rid = int(attrs.get("road_id", -1))
    if rid < 0:
        return (0.35, 0.35, 0.38)
    # Golden-ratio hue stepping: consecutive ids land far apart on the wheel, so neighbouring
    # roads never come out near-identical the way `hue = id * 0.1` would.
    import colorsys
    return colorsys.hsv_to_rgb((rid * 0.61803398875) % 1.0, 0.75, 0.95)


def _aux_color(attrs):
    if int(attrs.get("aux_lanes_left", 0)) or int(attrs.get("aux_lanes_right", 0)):
        return (0.95, 0.25, 0.25)
    mt = int(attrs.get("median_type", 0))
    if mt in ga.MEDIAN_RAISED:
        return (0.25, 0.85, 0.35)
    if mt != ga.MEDIAN_NONE:
        return (0.90, 0.85, 0.25)
    return (0.35, 0.35, 0.38)


def _structure_color(attrs):
    deck = float(attrs.get("deck_thickness", 0.0))
    if deck <= 0.0:
        return (0.35, 0.35, 0.38)
    if float(attrs.get("pillar_spacing", 0.0)) > 0.0:
        return (0.95, 0.45, 0.85)        # deck on piers
    return (0.45, 0.55, 0.95)            # deck on fill


_COLOR_FN = {'LANES': _lane_color, 'ROAD': _road_color, 'AUX': _aux_color,
             'STRUCTURE': _structure_color}


def _draw():
    """Read the live edit bmesh and draw one coloured segment per edge.

    Wrapped whole in a try/except on purpose: a draw handler that raises does so once per redraw,
    which floods the console and can wedge the viewport. An overlay is a convenience, and the
    correct failure for a convenience is to disappear."""
    try:
        ctx = bpy.context
        obj = ctx.edit_object
        if obj is None or obj.type != 'MESH':
            return
        settings = getattr(ctx.scene, "rka_graph", None)
        if settings is None or not settings.overlay_on:
            return
        bm = bmesh.from_edit_mesh(obj.data)
        layers = ga.ensure_edge_layers(bm, fill_defaults=False)
        if not layers:
            return
        fn = _COLOR_FN.get(settings.overlay_mode, _lane_color)

        mat = obj.matrix_world
        coords, colors = [], []
        for e in bm.edges:
            if e.hide:
                continue
            c = fn(ga.read_edge(bm, e, layers))
            rgba = (c[0], c[1], c[2], 1.0)
            for v in (e.verts[0], e.verts[1]):
                coords.append(mat @ v.co)
                colors.append(rgba)
        if not coords:
            return

        import gpu
        from gpu_extras.batch import batch_for_shader
        shader = gpu.shader.from_builtin('POLYLINE_FLAT_COLOR')
        region = ctx.region
        shader.uniform_float("viewportSize", (region.width, region.height))
        shader.uniform_float("lineWidth", float(settings.overlay_width))
        batch = batch_for_shader(shader, 'LINES', {"pos": coords, "color": colors})
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        batch.draw(shader)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')
    except Exception:                                     # noqa: BLE001 -- see docstring
        pass


def enable():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')


def disable():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None


class RKA_OT_graph_overlay_toggle(bpy.types.Operator):
    """Show or hide the authored-value colouring on the road graph."""
    bl_idname = "rka.graph_overlay_toggle"
    bl_label = "Toggle Graph Overlay"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.rka_graph
        s.overlay_on = not s.overlay_on
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        self.report({'INFO'}, "Graph overlay %s" % ("on" if s.overlay_on else "off"))
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_overlay_toggle,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    # Registering the handler at addon-enable time (rather than on first toggle) keeps the drawing
    # decision entirely in `overlay_on`, so there is one source of truth for whether it shows.
    if not bpy.app.background:
        enable()


def unregister():
    disable()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
