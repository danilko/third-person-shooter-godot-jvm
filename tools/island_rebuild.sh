#!/usr/bin/env bash
# island_rebuild.sh -- the island's whole road pipeline, in order (PLAN.md 3.13).
#
#   tools/island_rebuild.sh [--no-layout]
#
#   1. tools/island_layout.py         the record: arterials + trunk grid + streets + expressway + turnarounds + setback
#   2. write_roadkit_ground.gd        every station's ground_z, and the natural-ground sidecar
#   3. island_road_zones.py --split   the 504 m zone grid: joints on long runs, the zones sidecar, World.tscn's markers
#   4. build_roads_piece.sh           the pieces (NAV_FIT=1, DIRTY_ONLY=1: only zones whose output changed)
#   5. stamp_roadkit_terrain.gd       the roads written into World's Terrain3D
#   6. island_traffic_zones.py        the ambient traffic markers, from the lanekits
#   7. bake_road_map.gd               the map picture and routing graph
#
# --no-layout starts at step 2 (the record was edited by hand or by one generator).
set -euo pipefail
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
P=assets/world_source/pieces
W=src/main/resources/com/openworld/world/World.tscn
if [[ "${1:-}" != "--no-layout" ]]; then
    echo "── 1/7 layout"
    python3 tools/island_layout.py
fi
echo "── 2/7 ground"
timeout -k 5 900 stdbuf -oL "$G" --headless --path . --script tools/godot/write_roadkit_ground.gd -- "$W" IslandRoads \
    | grep -E "^(ground|GROUND)"
echo "── 3/7 zones"
python3 tools/island_road_zones.py "$P/IslandRoads.roads.json" "$W" --split | tail -1
echo "── 4/7 build"
NAV_FIT=1 DIRTY_ONLY=1 blender/tools/build_roads_piece.sh "$P/IslandRoads.roads.json" Roads_IslandRoads \
    "$P/IslandRoads.zones.json" "$P/IslandRoads.ground.json" | grep -E "gate:|^── 3/3|FAIL|ERROR" || true
# a zone the cut no longer makes leaves its piece behind, and every later step globs the lanekits: remove it
python3 - <<'PY'
import glob, json, os
P = "assets/world_source/pieces"
R = "src/main/resources/com/openworld/world/pieces"
zones = {z["zone_id"] if "zone_id" in z else z.get("id") for z in json.load(open(P + "/IslandRoads.zones.json"))["zones"]}
for f in sorted(glob.glob(P + "/Roads_IslandRoads_island_*.lanekit.json")):
    zid = os.path.basename(f)[len("Roads_IslandRoads_"):-len(".lanekit.json")]
    if zid not in zones:
        stem = "Roads_IslandRoads_" + zid
        for g in [f] + glob.glob(R + "/" + stem + ".*"):
            os.remove(g)
        print("pruned stale piece " + stem)
PY
echo "── 5/7 stamp"
timeout -k 5 1800 stdbuf -oL "$G" --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- "$W" IslandRoads \
    | grep -viE "^ZoneManager|^$" | tail -5
echo "── 6/7 traffic zones"
python3 tools/island_traffic_zones.py $P/Roads_IslandRoads_island_*.lanekit.json "$W" --load 1150 --unload 1550 | tail -3
echo "── 7/7 road map"
timeout -k 5 900 stdbuf -oL "$G" --headless --path . --script tools/godot/bake_road_map.gd -- --world=island | tail -3
