bl_info = {
    "name": "Road Kit Authoring",
    "author": "third-person-shooter",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "headless: blender/tools/build_island_base.py (roads are authored in, and built by, the Godot Road Kit plugin)",
    "description": "Point/port road authoring: an Empty per road station, carrying its own "
                    "cross-section and its own typed links.",
    "category": "Object",
}

# POINT/PORT GRAPH (v0.3) -- see blender/ROAD_POINT_GRAPH.md, the design of record.
#
#     road  = an ordered chain of points (a Collection under ROAD_MANAGER)
#     point = a STATION and a PORT at once: cross-section + typed links (an Empty, `obj.rka_pt`)
#     link  = SEGMENT (symmetric) / JUNCTION (symmetric) / AUX (mainline -> ramp)
#     pad   = a clique over JUNCTION links; the member points ARE the stop lines
#
# Every along-the-length change -- lane drop, lane opening, one-way, an acceleration lane and its
# taper -- is just "two stations that differ", which is what deletes the ~900 lines of special-case
# inference the mesh-graph model needed for the same road.
#
#   point_model    the authored schema + the git-diffable .roads.json; the Empties are a VIEW of it
#   point_profile  station -> lane_profile.Profile; the slot-id vocabulary (F0.., R0.., AF0.., MED)
#   point_solve    chain -> carrier numbers; clique -> pad, fillets, turns; markings; Auto Setback
#   point_edges    the road EDGE: where kerbs open, from the paved footprints
#   point_validate the gate (5) -- a build that fails it is a failed build
#   point_nodes    the GN vocabulary: spine, band, deck, profile, pillars, assets, finish
#   point_build    carrier + stack + pads + ground cut + collision; ROAD_MANAGER_GEN lifetime
#   point_style    what a road is MADE OF: a material or a swept profile asset, per layer
#   point_export   .lanekit.json v2 -- bezier handles FITTED to the lane, junctions[], `spawnable`
#   point_ops      the headless pipeline's operators (seeder + builds); authoring is the Godot plugin's
#   point_record_ops  the record-level repairs and ramp gestures the Godot plugin calls (pure)
#   point_flow     the lane-graph flow report (pure)
#   point_zones / point_ground  the per-zone cut and the Terrain3D ground sidecar (pure)
#
# The two models this replaces are archived under `legacy_graph/` (the mesh graph) and were
# deleted (the per-piece generators) -- see `legacy_graph/README.md`. Neither is imported.
# `blender/lib/` is untouched: `lane_profile.py` still owns the cross-section (this addon calls it
# and never re-derives a lateral offset), `intersection_kit.py` owns junction geometry, and the
# district tools under `blender/tools/` still depend on the rest of it.

from . import paths  # noqa: F401  (sets up sys.path to lib/, exposes KIT_BLEND / WORLD_SOURCE)
from . import point_nodes  # noqa: F401  (node-group vocabulary; no operators of its own)
from . import point_style  # noqa: F401  (style slots; pure resolution, no operators)
from . import point_edges  # noqa: F401  (the road edge; pure geometry, no operators)
from . import point_ops
from . import point_build

# B9 (PLAN.md 3.1, 2026-09-14): authoring is the Godot plugin's. The panels, the GPU overlay, the flow
# preview's drawing (`point_flow` keeps the report) and the live rebuild are deleted; what registers
# is what the headless pipeline drives.
MODULES = (point_ops, point_build)


def register():
    for m in MODULES:
        m.register()


def _reload_lib_modules():
    """Force `lib/*.py` to be re-read from disk on the NEXT import instead of keeping whatever
    was cached before a script reload.

    These live outside this package (reached via a plain `sys.path.insert` in `paths.py`), so
    Blender's own "Reload Scripts" -- which reloads modules belonging to a registered addon's own
    package -- never touches them, and a plain `import lane_profile` returns whatever is already in
    `sys.modules`. That was the concrete cause of edits to `lib/` silently not taking effect after
    F8 or an addon disable/enable, fixable only by restarting Blender."""
    import importlib
    import sys

    for name in [n for n, m in sys.modules.items()
                 if getattr(m, "__file__", None) and m.__file__.startswith(paths.LIB_DIR)]:
        del sys.modules[name]
    importlib.reload(paths)


def unregister():
    for m in reversed(MODULES):
        m.unregister()
    _reload_lib_modules()
