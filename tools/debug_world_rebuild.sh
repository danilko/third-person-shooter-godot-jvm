#!/bin/bash
# DebugWorld from scratch: layout -> scene -> terrain -> rail -> roads -> street names -> road map.
# Everything is derived by tools/debug_world_layout.py; nothing here is hand-edited. ~5 min.
set -euo pipefail
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
W=src/main/resources/com/openworld/world/DebugWorld.tscn
P=assets/world_source/pieces
q() { grep -vE "^ZoneManager|^\s*$|WARNING|  at: |invalid UID|GDScript backtrace|^\s+\[[0-9]+\]" || true; }
echo "── 1/7 layout + scene"
python3 tools/debug_world_layout.py
python3 blender/tools/roadkit_cli.py setback $P/DebugRoads.roads.json > /dev/null
python3 blender/tools/roadkit_cli.py setback $P/DebugRail.roads.json > /dev/null
python3 tools/debug_world_scene.py
echo "── 2/7 terrain (natural ground: the old stamps and ground samples go with it)"
rm -f $P/DebugRoads.stamp.json $P/DebugRail.stamp.json $P/DebugRoads.ground.* $P/DebugRail.ground.* $P/DebugRoads.build.json $P/DebugRail.build.json
timeout -k 5 300 "$G" --headless --path . --script tools/godot/apply_height_grid.gd -- res://assets/terrain3d/debug_world \
    assets/world_source/terrain/debug_world.f32 -512 -512 513 513 2 | grep APPLIED
timeout -k 5 300 "$G" --headless --path . --script tools/godot/paint_terrain.gd -- res://assets/terrain3d/debug_world | grep -E "saved"
echo "── 3/7 rail: ground, pieces, stamp"
timeout -k 5 600 "$G" --headless --path . --script tools/godot/write_roadkit_ground.gd -- "$W" DebugRail | grep -E "^GROUND"
GLTF_EXTRA="--avoid $P/DebugRoads.roads.json" NAV_FIT=1 \
    blender/tools/build_roads_piece.sh "$P/DebugRail.roads.json" Roads_DebugRail "$P/DebugRail.zones.json" "$P/DebugRail.ground.json" \
    | grep -E "gate:|level crossing|FAIL|ERROR" || true
timeout -k 5 900 "$G" --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- "$W" DebugRail | grep -E "^stamped"
echo "── 4/7 roads: ground, pieces, stamp"
timeout -k 5 600 "$G" --headless --path . --script tools/godot/write_roadkit_ground.gd -- "$W" DebugRoads | grep -E "^GROUND"
GLTF_EXTRA="--keep-clear-lanekits $P/Roads_DebugRail_ --avoid $P/DebugRail.roads.json --avoid-ground $P/DebugRail.ground.json" NAV_FIT=1 \
    blender/tools/build_roads_piece.sh "$P/DebugRoads.roads.json" Roads_DebugRoads "$P/DebugRoads.zones.json" "$P/DebugRoads.ground.json" \
    | grep -E "gate:|FAIL|ERROR" || true
timeout -k 5 900 "$G" --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- "$W" DebugRoads | grep -E "^stamped"
echo "── 5/7 street names + sign font"
python3 tools/island_street_names.py | tail -1
python3 tools/make_jp_font.py | tail -1
echo "── 6/7 road map"
timeout -k 5 600 "$G" --headless --path . --script tools/godot/bake_road_map.gd -- --world=debugworld | grep -E "^RESULT"
echo "── 7/7 checks"
# (no layout --check here: the setback and the ground sampling write into the records after the layout step)
python3 tools/debug_world_scene.py --check
