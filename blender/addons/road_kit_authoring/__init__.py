bl_info = {
    "name": "Road Kit Authoring",
    "author": "third-person-shooter",
    "version": (0, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Road Kit",
    "description": "Mesh-graph road authoring: one mesh where vertices are junctions and edges "
                    "are road segments, carrying their cross-section as edge attributes.",
    "category": "Object",
}

# MESH-GRAPH ARCHITECTURE (v0.2). The whole road network is ONE mesh object:
#
#     vertex = node    (intersection / gore / bend / cap / shape point)
#     edge   = segment (its own cross-section, stored as edge-domain attributes)
#
#   graph_attrs   authoring: stamp attributes on selected edges/vertices in Edit Mode
#   graph_assets  asset palettes: an INT per edge selects a linked kit collection
#   graph_solve   runs lib/road_graph_solve.py, writes trims + node patches + kerb corners
#   graph_nodes   the Geometry Nodes vocabulary: spine, band, deck, assets, finish
#   graph_build   emits the swept carrier from the solved chains, hangs the stack on it
#   graph_export  lane centrelines -> .lanekit.json for Godot, and the viewport preview
#   graph_panel   UI
#
# The per-PIECE generators this addon used to be (`ops_intersection`, `ops_segment`, `ops_split`,
# their live-edit machinery and their smoketests) are archived under `legacy/` -- kept on disk for
# reference, deliberately not imported, because a piece-based generator and a graph-based one
# cannot share an authoring model. `blender/lib/` is untouched: `lane_profile.py` still owns the
# cross-section (this addon calls it and never re-derives a lateral offset), and the district
# tools under `blender/tools/` still depend on the rest of it.

from . import paths  # noqa: F401  (sets up sys.path to lib/, exposes KIT_BLEND / WORLD_SOURCE)
from . import graph_attrs
from . import graph_assets
from . import graph_solve
from . import graph_nodes  # noqa: F401  (node-group vocabulary; no operators of its own)
from . import graph_edges  # noqa: F401  (the road outline; pure geometry, no operators)
from . import graph_build
from . import graph_export
from . import graph_overlay
from . import graph_panel

MODULES = (graph_attrs, graph_assets, graph_solve, graph_build, graph_export,
           graph_overlay, graph_panel)


def register():
    for m in MODULES:
        m.register()


def _reload_lib_modules():
    """Force `lib/*.py` to be re-read from disk on the NEXT import instead of keeping whatever
    was cached before a script reload.

    These live outside this package (reached via a plain `sys.path.insert` in `paths.py`), so
    Blender's own "Reload Scripts" -- which reloads modules belonging to a registered addon's own
    package -- never touches them, and a plain `import road_graph_solve` returns whatever is
    already in `sys.modules`. That was the concrete cause of edits to `lib/` silently not taking
    effect after F8 or an addon disable/enable, fixable only by restarting Blender."""
    import importlib
    import sys

    for name in [n for n, m in sys.modules.items()
                 if getattr(m, "__file__", None) and m.__file__.startswith(paths.LIB_DIR)]:
        del sys.modules[name]
    graph_solve._lp = None
    graph_solve._rgs = None
    importlib.reload(paths)


def unregister():
    for m in reversed(MODULES):
        m.unregister()
    _reload_lib_modules()
