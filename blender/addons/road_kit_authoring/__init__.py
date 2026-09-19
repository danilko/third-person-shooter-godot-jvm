"""road_kit_authoring -- the Road Kit's rules and its build, in plain python3 (no Blender).

Roads are AUTHORED in the Godot editor (`addons/road_kit/`, the plugin) and saved as a git-diffable
`<stem>.roads.json`. Everything the plugin and the build ask of a network is answered here, reached
through `blender/tools/roadkit_cli.py`; the build writes each piece's glTF with no Blender
(`blender/tools/build_roads_piece.sh`, CLAUDE.md "THE ROAD BUILD HAS NO BLENDER (B11)").

    point_model       the authored schema + the .roads.json
    point_profile     station -> lane_profile.Profile; the slot-id vocabulary (F0.., R0.., AF0.., MED)
    point_solve       chain -> carrier numbers; clique -> pad, fillets, turns; markings; Auto Setback
    point_edges       the road EDGE (where kerbs open) and the corridors the terrain stamp reads
    point_validate    the gate -- a build that fails it is a failed build
    point_style / point_kit   what a road is MADE OF: material and profile-asset slots, by name
    point_mesh / point_gltf   the sweep and the glTF writer (the mesh build)
    point_furniture   decals, paint and street furniture placed from the solve
    point_export      .lanekit.json v2 -- bezier handles FITTED to the lane, junctions[], `spawnable`
    point_record_ops  the record-level gestures the Godot plugin calls (merge, split, joints, ramps)
    point_flow        the lane-graph flow report
    point_zones / point_ground / point_digest  the per-zone cut, the Terrain3D ground sidecar, the
                      per-piece digest that lets a build skip what did not change

The Blender half of this package -- the Empties, the operators, the Geometry Nodes build
(`point_ops`, `point_build`, `point_nodes`) and the archived mesh-graph model (`legacy_graph/`) --
was deleted on 2026-09-18 (PLAN.md 3.10): authoring moved to Godot at B9, the build at B11, and the
island's ground is Terrain3D, so nothing ran it any more. git history has it.
"""


def register():
    """No Blender half any more: kept so a Blender whose preferences still enable this addon loads it silently
    (without these, every Blender launch printed an AttributeError traceback)."""


def unregister():
    pass
