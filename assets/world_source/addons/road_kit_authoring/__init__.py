bl_info = {
    "name": "Road Kit Authoring",
    "author": "third-person-shooter",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Road Kit",
    "description": "Place/duplicate/rotate road-kit pieces on a grid, author lane centerlines, "
                    "and export lane connectivity for Godot Path3D. See road_blender_godot.md.",
    "category": "Object",
}

from . import paths  # noqa: F401  (sets up sys.path to lib/, exposes KIT_BLEND / WORLD_SOURCE)
from . import props
from . import ops_placement
from . import ops_centerline
from . import ops_combine
from . import ops_intersection
from . import ops_segment
from . import live_edit
from . import panel

MODULES = (props, ops_placement, ops_centerline, ops_combine, ops_intersection, ops_segment,
           live_edit, panel)


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
