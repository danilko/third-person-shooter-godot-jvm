#!/usr/bin/env bash
# island_downstream.sh -- everything that READS the island's road pieces, re-derived after a hand edit
# (PLAN.md item 3, the handover; the Road Kit dock's "Downstream" button runs exactly this).
#
#   tools/island_downstream.sh [--check]
#
# After a designer edits a road and presses Build Piece (and Stamp Terrain), these still describe the OLD roads:
#   1. traffic zones        island_traffic_zones.py   (World.tscn TrafficZones: where cars spawn, from the lanekits)
#   2. road map             bake_road_map.gd          (the minimap / GPS picture and graph)
#   3. sidewalk lines       island_buildings.py sidewalks (the light crowd's walk lines, from the road solve)
#   4. buildings vs roads   island_buildings.py roads (no building on a road band at any height) -- a CHECK
#   5. civic plots          island_civic_sites.py --check (every plot fronts a road, none has one through it)
# Nothing here regenerates a hand-authored record, so it runs on a frozen island too. --check only reports.
set -uo pipefail
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
P=assets/world_source/pieces
W=src/main/resources/com/openworld/world/World.tscn
CHECK=""; [[ "${1:-}" == "--check" ]] && CHECK="--check"
FAIL=0
run() { echo "── $1"; shift; "$@" || { echo "   FAILED: $*"; FAIL=1; }; }
run "1/5 traffic zones" bash -c "python3 tools/island_traffic_zones.py $P/Roads_IslandRoads_island_*.lanekit.json $W --load 1150 --unload 1550 $CHECK | tail -3"
if [[ -z "$CHECK" ]]; then
    run "2/5 road map" bash -c "timeout -k 5 900 stdbuf -oL $G --headless --path . --script tools/godot/bake_road_map.gd -- --world=island | tail -3"
else
    run "2/5 road map" bash -c "timeout -k 5 900 stdbuf -oL $G --headless --path . --script tools/godot/bake_road_map.gd -- --world=island --check | tail -3"
fi
run "3/5 sidewalk lines" bash -c "python3 tools/island_buildings.py sidewalks $CHECK | tail -2"
run "4/5 buildings vs roads" bash -c "python3 tools/island_buildings.py roads | tail -3"
run "5/5 civic plots" bash -c "python3 tools/island_civic_sites.py --check | tail -3"
echo "RESULT $([[ $FAIL == 0 ]] && echo PASS || echo FAIL)"
exit $FAIL
