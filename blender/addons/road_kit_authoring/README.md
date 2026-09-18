# Road Kit — the rules and the build, in plain python3

**Roads are authored in the Godot editor** (the `addons/road_kit/` plugin; its how-to is
`addons/road_kit/README.md`) and saved as `<stem>.roads.json`. This folder holds everything the plugin
and the build ask of a network. **None of it needs Blender.** The name is historical: it began as a
Blender addon. Its Blender half was deleted on 2026-09-18, after authoring moved to Godot (PLAN.md 3.1
B9) and the build moved to Python (B11). That half was the Empties, the operators, the Geometry Nodes
build (`point_ops`, `point_build`, `point_nodes`), the mesh-graph model (`legacy_graph/`), the island
bake (`blender/tools/build_island_base.py`) and the district seeder (`seed_district_roads.py`). git
history has it. The design of record is still `blender/ROAD_POINT_GRAPH.md`.

| module | job |
|---|---|
| `point_model` | the schema and the git-diffable `.roads.json` |
| `point_profile`, `point_solve`, `point_edges`, `point_validate`, `point_export` | the rules: cross-sections, carriers, pads, gores, kerbs, the gate, the `.lanekit.json` export |
| `point_zones`, `point_ground`, `point_digest` | the per-zone cut (B6), the Terrain3D ground sidecar (B6b), the per-piece digest (B10.6) |
| `point_record_ops`, `point_flow` | the record gestures (merge, split, joints, ramps, repairs) and the flow report the Godot dock calls |
| `point_mesh`, `point_gltf`, `point_kit`, `point_style`, `point_furniture` | THE ROAD BUILD (B11): the sweep, the piece `.gltf`, the style slots and kit materials (`assets/world_source/kits/road_kit/road_kit.json`), the decals and street furniture |

Entry points: `blender/tools/roadkit_cli.py` (every command the plugin runs) and
`blender/tools/build_roads_piece.sh` (the piece build). The one Blender tool left in the road
pipeline is `blender/tools/build_road_kit.py`, which authors `road_kit.blend` (materials, profile
sections, piers) and exports `road_kit.json` from it through `export_road_kit_data.py`.

Gate: `blender/tools/check_roads.sh`: the pure self-tests, the lanekit graph check, the derived-scene
checks (`tools/island_road_zones.py --check`, `tools/island_traffic_zones.py --check`) and every Godot
plugin test.
