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
from . import traffic_viz
from . import ops_export
from . import panel

MODULES = (props, ops_placement, ops_centerline, ops_combine, ops_intersection, ops_segment,
           live_edit, traffic_viz, ops_export, panel)


def register():
    for m in MODULES:
        m.register()


def _reload_lib_modules():
    """Force `lib/*.py` (intersection_kit, kit_common, ...) to be re-read from disk on the NEXT
    import, instead of silently keeping whatever was cached from before a script reload.

    These live outside the `road_kit_authoring` PACKAGE (reached via a plain `sys.path.insert` in
    `paths.py`), so Blender's own "Reload Scripts" -- which reloads modules belonging to a
    registered addon's own package -- has no idea they exist and never touches them; a plain
    `import intersection_kit` always returns whatever is already sitting in `sys.modules`
    regardless of how many times the addon itself gets reloaded. `ops_intersection.py`/
    `ops_segment.py` compound this with their own lazy-singleton `ik()` (a module-level `_ik`
    cache) and `paths.py` imports `kit_common` at its own module top-level as `paths.kc` -- three
    separate places a stale reference can hide. This was the concrete cause of code changes to
    `lib/intersection_kit.py` silently not taking effect after "Reload Scripts" (F8) or an addon
    disable/enable toggle -- only a full Blender restart actually picked them up.

    Evicting every `sys.modules` entry whose `__file__` lives under `paths.LIB_DIR`, resetting the
    two ops modules' `_ik` singletons, and reloading `paths` itself (so `paths.kc` re-resolves
    against the now-evicted `kit_common`) makes a normal reload/toggle pick up `lib/` changes too,
    with no future lib module needing its own opt-in."""
    import importlib
    import sys

    for name in [n for n, m in sys.modules.items()
                 if getattr(m, "__file__", None) and m.__file__.startswith(paths.LIB_DIR)]:
        del sys.modules[name]
    ops_intersection._ik = None
    ops_segment._ik = None
    importlib.reload(paths)


def unregister():
    for m in reversed(MODULES):
        m.unregister()
    _reload_lib_modules()
