# Road Kit — the headless model half

**Roads are authored in the Godot editor** — the `addons/road_kit/` plugin; its how-to is
`addons/road_kit/README.md`. Since PLAN.md 3.1 **B9** (2026-09-14) this Blender addon has no UI: no
sidebar panels, no viewport overlay, no flow-preview drawing, no live rebuild. The step-by-step guide to
the Blender authoring UI that used to live here is in git history (this file before B9; the kit's design
of record is `blender/ROAD_POINT_GRAPH.md`).

What it is now:

| module | job |
|---|---|
| `point_model` | the schema and the git-diffable `.roads.json` (pure) — plus the Empties the build reads |
| `point_profile`, `point_solve`, `point_edges`, `point_validate`, `point_export` | the rules: cross-sections, carriers, pads, gores, kerbs, the gate, the `.lanekit.json` export (pure) |
| `point_zones`, `point_ground` | the per-zone cut (B6) and the Terrain3D ground sidecar (B6b) (pure) |
| `point_record_ops`, `point_flow` | the record gestures and the flow report the Godot dock calls through `blender/tools/roadkit_cli.py` (pure) |
| `point_mesh`, `point_gltf`, `point_kit` | THE ROAD BUILD (B11, pure): the sweep (every layer, profile assets, `-colonly` proxies), the piece `.gltf` with auto-smooth normals, and the style slots / kit materials read from `assets/world_source/kits/road_kit/road_kit.json` |
| `point_build`, `point_nodes`, `point_style` | the Blender meshes (GN stacks) -- used only by the island build now (`build_island_base.py`); `point_style.SLOTS` is the one slot table both builds read |
| `point_ops` | the operators a TOOL drives: New/Extend Road, Connect, Make Intersection (the island seeder), Auto Setback, Load/Save Record, Export Lanekit, Link Road Kit |

Entry points: `blender/tools/roadkit_cli.py` (python3, no Blender) and `blender/tools/build_roads_piece.sh` (the piece
build, no Blender since B11), `blender/tools/export_road_kit_data.py` (road_kit.blend -> road_kit.json, run by
`build_road_kit.py`), `blender/tools/build_island_base.py` /
`seed_district_roads.py` (the island).

Gate: `blender/tools/check_roads.sh` — pure self-tests, the lanekit graph check, the headless Blender
smoketests (`smoketest_point_addon`, `_build`, `_coverage`, `_ops`) and every Godot plugin test.
