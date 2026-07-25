"""Multi-lane composition: mark the seams between adjacent placed lane tiles.

Per the "combine mesh" design in road_blender_godot.md's Kit geometry v2 section: a same-direction
seam gets a flush white divider strip; an opposite-direction seam gets a yellow divider (and a
warning if the tiles are sitting flush with no median gap/barrier). Direction is read straight off
each placed instance's own rotation (matrix_world), not the underlying mesh data — the same
lane-tile mesh serves both directions of travel just by being rotated 180 degrees on placement.
"""
import bpy
from mathutils import Vector

from . import paths


def _direction_sign(obj):
    """+1 if the instance's local +Y (forward) points toward world +Y, else -1."""
    fwd = obj.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))
    return 1 if fwd.y >= 0 else -1


def _world_y_span(obj, local_length):
    a = obj.matrix_world @ Vector((0.0, 0.0, 0.0))
    b = obj.matrix_world @ Vector((0.0, local_length, 0.0))
    return (min(a.y, b.y), max(a.y, b.y))


class RKA_OT_combine_lanes(bpy.types.Operator):
    """Mark the seams between adjacent, already-placed lane-tile instances: a flush white divider
    for two lanes running the same direction, a yellow divider (and a warning if they're flush
    with no extra gap) for two lanes running opposite directions. Operates on the selected
    collection-instance objects, sorted left-to-right by local X — place/duplicate the lanes
    first (RKA_OT_place_piece / RKA_OT_duplicate_piece), select them, then run this. Assumes each
    selected instance's own local length equals the scene grid size (true for every kit lane
    tile, by design — see Kit geometry v2 item 1)."""
    bl_idname = "rka.combine_lanes"
    bl_label = "Mark Lane Seams"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len([o for o in context.selected_objects if o.instance_type == 'COLLECTION']) >= 2

    def execute(self, context):
        rka = context.scene.rka
        insts = sorted(
            (o for o in context.selected_objects if o.instance_type == 'COLLECTION'),
            key=lambda o: o.matrix_world.translation.x)

        dest = insts[0].users_collection[0] if insts[0].users_collection else context.scene.collection
        created, n_warn = [], 0
        for a, b in zip(insts, insts[1:]):
            same_dir = _direction_sign(a) == _direction_sign(b)
            seam_x = (a.matrix_world.translation.x + b.matrix_world.translation.x) / 2.0
            ya = _world_y_span(a, rka.grid)
            yb = _world_y_span(b, rka.grid)
            y0, y1 = max(ya[0], yb[0]), min(ya[1], yb[1])
            if y1 <= y0:
                self.report({'WARNING'}, "'%s'/'%s': no overlapping length to mark a seam" % (a.name, b.name))
                continue
            z = a.matrix_world.translation.z + rka.lane_surface_z

            gap = abs(b.matrix_world.translation.x - a.matrix_world.translation.x) - rka.grid
            if same_dir:
                matkey, tag = 'line_w', 'white'
            else:
                matkey, tag = 'line_y', 'yellow'
                if gap < 0.05:
                    n_warn += 1
                    self.report({'WARNING'},
                                "'%s'/'%s' run opposite directions but sit flush (no median gap) "
                                "— consider extra separation or a barrier piece" % (a.name, b.name))

            strip = paths.kc.lane_marking_strip(
                "laneline_%s_%d" % (tag, len(created)), seam_x, y0, y1, z,
                rka.lane_marking_width, matkey, dest)
            created.append(strip)

        if not created:
            self.report({'WARNING'}, "No seams marked")
            return {'CANCELLED'}
        self.report({'INFO'}, "Marked %d seam(s), %d warning(s)" % (len(created), n_warn))
        return {'FINISHED'}


CLASSES = (RKA_OT_combine_lanes,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
