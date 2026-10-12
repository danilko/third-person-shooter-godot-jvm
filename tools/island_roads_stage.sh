#!/bin/bash
# island_roads_stage.sh -- island_rebuild.sh steps 3-7 for the roads WITHOUT the layout and WITHOUT re-sampling the ground,
# then the dirty rail pieces, the footbridge check and the sidewalks (s8, 2026-10-12). Each step timed.
set -uo pipefail
cd /data/danilko/git/third-person-shooter
G=/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64
P=assets/world_source/pieces
W=src/main/resources/com/openworld/world/World.tscn
T0=$SECONDS; step() { echo "── $1 (+$((SECONDS-T0)) s)"; }
step "3 zones"
python3 tools/island_road_zones.py "$P/IslandRoads.roads.json" "$W" --split | tail -1
step "4 build"
GLTF_EXTRA="--keep-clear-lanekits $P/Roads_IslandRail_ --avoid $P/IslandRail.roads.json --avoid-ground $P/IslandRail.ground.json --keep-out $P/IslandRoads.keepout.json,$P/IslandFootbridges.keepout.json" NAV_FIT=1 DIRTY_ONLY=1 \
    blender/tools/build_roads_piece.sh "$P/IslandRoads.roads.json" Roads_IslandRoads "$P/IslandRoads.zones.json" "$P/IslandRoads.ground.json" \
    | grep -E "gate:|^── 3/3|FAIL|ERROR|nothing changed" | cut -c1-160
step "4b rail (dirty only)"
GLTF_EXTRA="--avoid $P/IslandRoads.roads.json --avoid-ground $P/IslandRoads.ground.json --keep-clear-lanekits $P/Roads_IslandRoads_" NAV_FIT=1 DIRTY_ONLY=1 \
    blender/tools/build_roads_piece.sh "$P/IslandRail.roads.json" Roads_IslandRail "$P/IslandRail.zones.json" "$P/IslandRail.ground.json" \
    | grep -E "gate:|^── 3/3|FAIL|ERROR|nothing changed" | cut -c1-160
step "5 stamp"
timeout -k 5 1800 stdbuf -oL "$G" --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- "$W" IslandRoads | grep -viE "^ZoneManager|^$" | tail -5 | cut -c1-200
step "6 traffic zones"
python3 tools/island_traffic_zones.py $P/Roads_IslandRoads_island_*.lanekit.json "$W" --load 1150 --unload 1550 | tail -3 | cut -c1-200
step "7 road map"
timeout -k 5 900 stdbuf -oL "$G" --headless --path . --script tools/godot/bake_road_map.gd -- --world=island | tail -3 | cut -c1-200
step "8 footbridges"
python3 tools/island_footbridges.py --check 2>&1 | tail -4 | cut -c1-200
step "9 sidewalks"
python3 tools/island_buildings.py sidewalks 2>&1 | tail -2 | cut -c1-200
step done
