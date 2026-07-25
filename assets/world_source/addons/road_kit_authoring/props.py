"""Scene + per-curve settings for road_kit_authoring.

`RKA_SceneSettings` drives placement (Phase 1). `RKA_CurveSettings` is the per-lane-centerline
authoring metadata consumed starting Phase 2/3 (`RKA_OT_add_centerline`, `lib/lane_kit.py`
export) — registered now so a kit piece's curves can carry it from the start. It lives on the
Curve *datablock* (`obj.data.rka_curve`), not the Object, so every linked instance of a kit piece
shares one edit.
"""
import bpy

END_BEHAVIOR_ITEMS = (
    ('CLAMP', "Clamp", "Stop at the path end"),
    ('LOOP', "Loop", "Wrap around to the path start"),
    ('CHAIN', "Chain", "Continue onto a linked lane"),
)

ROAD_CLASS_ITEMS = (
    ('local', "Local", "Local street"),
    ('arterial', "Arterial", "Arterial road"),
    ('highway', "Highway", "Highway"),
)


class RKA_SceneSettings(bpy.types.PropertyGroup):
    grid: bpy.props.FloatProperty(
        name="Grid Size", description="Placement snap grid, in meters",
        default=5.0, min=0.1, unit='LENGTH')
    connect_eps: bpy.props.FloatProperty(
        name="Connect Epsilon",
        description="Max distance between lane endpoints to auto-link them, in meters "
                     "(consumed by lib/lane_kit.py's connectivity pass — Phase 3, not yet wired)",
        default=1.0, min=0.01, unit='LENGTH')
    active_kit_collection: bpy.props.StringProperty(
        name="Active Kit Piece",
        description="Name of the linked kit Collection that 'Place Piece' instances")
    place_direction: bpy.props.EnumProperty(
        name="Duplicate Direction",
        description="Local axis (of the selected instance) that 'Duplicate' offsets along",
        items=(
            ('POS_X', "+X", "Duplicate along local +X"),
            ('NEG_X', "-X", "Duplicate along local -X"),
            ('POS_Y', "+Y", "Duplicate along local +Y"),
            ('NEG_Y', "-Y", "Duplicate along local -Y"),
        ),
        default='POS_X')
    lane_surface_z: bpy.props.FloatProperty(
        name="Lane Surface Z",
        description="Local height of a lane tile's drivable surface above its placement origin "
                     "(matches the hand-modeled kit pieces' z=0.15) — used to sit seam markings "
                     "flush on the road surface",
        default=0.15, unit='LENGTH')
    lane_marking_width: bpy.props.FloatProperty(
        name="Lane Marking Width",
        description="Width of a generated white/yellow seam-marking strip",
        default=0.1, min=0.01, unit='LENGTH')
    live_edit_enabled: bpy.props.BoolProperty(
        name="Live Edit From Handles", default=True,
        description="Drag an arm_*/segend_*/segbend_* marker Empty in the viewport and the "
                     "owning intersection/segment rebuilds immediately (see live_edit.py). "
                     "Global kill switch -- turn off if it feels laggy on a complex piece; a "
                     "single piece can also opt out via its own 'rka_live_edit' custom property")


class RKA_CurveSettings(bpy.types.PropertyGroup):
    lane_width: bpy.props.FloatProperty(name="Lane Width", default=3.0, min=0.1, unit='LENGTH')
    oneway: bpy.props.BoolProperty(name="One-way", default=True)
    road_class: bpy.props.EnumProperty(name="Class", items=ROAD_CLASS_ITEMS, default='local')
    loop: bpy.props.BoolProperty(name="Loop", default=False)
    end_behavior: bpy.props.EnumProperty(
        name="End Behavior", items=END_BEHAVIOR_ITEMS, default='CHAIN')


CLASSES = (RKA_SceneSettings, RKA_CurveSettings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rka = bpy.props.PointerProperty(type=RKA_SceneSettings)
    bpy.types.Curve.rka_curve = bpy.props.PointerProperty(type=RKA_CurveSettings)


def unregister():
    del bpy.types.Curve.rka_curve
    del bpy.types.Scene.rka
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
