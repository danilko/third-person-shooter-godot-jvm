"""Phase 2 centerline authoring: build lane curves from hand-tagged mesh topology.

The centerline is NOT guessed (no bbox-midline heuristic) — the artist marks the drivable
centerline of each lane strip in a mesh's `lanedata` vertex group (tag a chain of vertices
following existing edges; several disjoint lane paths, e.g. every turn movement through an
intersection, can share one `lanedata` group since edge-connectivity alone separates them). See
`kit_common.centerlines_from_vertex_group` for the extraction algorithm.
"""
import bpy

from . import paths

VGROUP_NAME = "lanedata"


class RKA_OT_centerline_from_vertex_group(bpy.types.Operator):
    """Build lanecl_* centerline curve(s) for the active mesh from its 'lanedata' vertex group —
    each edge-connected tagged region becomes one directional lane curve, added to the same
    collection as the source mesh so it travels with every linked instance of that Collection."""
    bl_idname = "rka.centerline_from_vertex_group"
    bl_label = "Centerline From Vertex Group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and VGROUP_NAME in obj.vertex_groups

    def execute(self, context):
        obj = context.active_object
        try:
            lanes, warnings = paths.kc.centerlines_from_vertex_group(obj, VGROUP_NAME)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for w in warnings:
            self.report({'WARNING'}, w)
        if not lanes:
            self.report({'WARNING'}, "No usable lane paths found in '%s' on %s" % (VGROUP_NAME, obj.name))
            return {'CANCELLED'}

        # the collection the mesh itself lives in, so the curve travels with the same linked
        # instance (Tier-1 kit pieces) or stays alongside a ROAD_MANUAL mesh (Tier-2 one-offs)
        dest_coll = obj.users_collection[0] if obj.users_collection else context.scene.collection

        created = []
        for i, lane in enumerate(lanes):
            curve_data = bpy.data.curves.new("lanecl_%s_%d" % (obj.name, i), type='CURVE')
            curve_data.dimensions = '3D'
            spline = curve_data.splines.new('POLY')
            pts = lane["points"]
            spline.points.add(len(pts) - 1)
            for pi, pt in enumerate(pts):
                spline.points[pi].co = (pt.x, pt.y, pt.z, 1.0)
            spline.use_cyclic_u = lane["loop"]
            curve_data.rka_curve.loop = lane["loop"]

            curve_obj = bpy.data.objects.new(curve_data.name, curve_data)
            dest_coll.objects.link(curve_obj)
            created.append(curve_obj)

        for o in context.selected_objects:
            o.select_set(False)
        for o in created:
            o.select_set(True)
        context.view_layer.objects.active = created[-1]

        self.report({'INFO'}, "Created %d lane centerline(s) for %s" % (len(created), obj.name))
        return {'FINISHED'}


CLASSES = (RKA_OT_centerline_from_vertex_group,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
