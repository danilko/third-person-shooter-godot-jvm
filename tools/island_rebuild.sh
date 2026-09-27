#!/usr/bin/env bash
# island_rebuild.sh -- the island's whole road pipeline, in order (PLAN.md 3.13).
#
#   tools/island_rebuild.sh [--no-layout]
#
#   1. tools/island_layout.py         the record: arterials + trunk grid + streets + expressway + turnarounds + setback
#   R. the RAIL (PLAN.md 3.25 R2), a second Road Kit network (IslandRail.roads.json, written by the layout stage's
#      island_rail_record.py): its ground, its zones (RailZones), its pieces built AGAINST the roads (piers off their
#      carriageways, the bed cut out at every level crossing) and its stamp -- BEFORE the roads sample their ground,
#      so to the roads the rail's embankment is part of the land (a road re-stamp never undoes the rail's).
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
if [ -f "$P/IslandRail.roads.json" ]; then
    echo "── R rail: ground, zones, pieces, stamp"
    timeout -k 5 900 stdbuf -oL "$G" --headless --path . --script tools/godot/write_roadkit_ground.gd -- "$W" IslandRail \
        | grep -E "^(ground|GROUND)"
    python3 tools/island_road_zones.py "$P/IslandRail.roads.json" "$W" --split --network IslandRail --prefix rail \
        --holder RailZones --zone-prefix Zone_rail_ --marker-prefix Rail_ --node-id-base 910020000 | tail -1
    AVOID_GROUND=""; [ -f "$P/IslandRoads.ground.json" ] && AVOID_GROUND="--avoid-ground $P/IslandRoads.ground.json"
    # NOT DIRTY_ONLY: the rail's digest does not see the ROAD record it is built against, and a road change moves
    # its crossings and its dropped piers
    # furniture ON: a rail road carries none of the street's (point_furniture.place skips it), only the 踏切
    # signals its level crossings get (R4, point_furniture.crossing_signals)
    GLTF_EXTRA="--avoid $P/IslandRoads.roads.json $AVOID_GROUND" NAV_FIT=1 \
        blender/tools/build_roads_piece.sh "$P/IslandRail.roads.json" Roads_IslandRail \
        "$P/IslandRail.zones.json" "$P/IslandRail.ground.json" | grep -E "gate:|level crossing|^── 3/3|FAIL|ERROR" || true
    timeout -k 5 1800 stdbuf -oL "$G" --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- "$W" IslandRail \
        | grep -viE "^ZoneManager|^$" | tail -3
fi
echo "── 2/7 ground"
timeout -k 5 900 stdbuf -oL "$G" --headless --path . --script tools/godot/write_roadkit_ground.gd -- "$W" IslandRoads \
    | grep -E "^(ground|GROUND)"
echo "── 3/7 zones"
python3 tools/island_road_zones.py "$P/IslandRoads.roads.json" "$W" --split | tail -1
echo "── 4/7 build"
# the road furniture keeps out of the rail's tracks (`--keep-clear-lanekits`); the digest cannot see the rail, so a
# rail change needs this step run once without DIRTY_ONLY
# and its PIERS keep off the rail's tracks (`--avoid` the rail record: point_mesh.pier_on_road over its bands too --
# a C1 column stood on the Main line where it passes under the ring, probe_rail_track's gauge 2026-09-26)
RAIL_AVOID=""; [ -f "$P/IslandRail.roads.json" ] && RAIL_AVOID="--avoid $P/IslandRail.roads.json"
[ -f "$P/IslandRail.ground.json" ] && RAIL_AVOID="$RAIL_AVOID --avoid-ground $P/IslandRail.ground.json"
GLTF_EXTRA="--keep-clear-lanekits $P/Roads_IslandRail_ $RAIL_AVOID" NAV_FIT=1 DIRTY_ONLY=1 \
    blender/tools/build_roads_piece.sh "$P/IslandRoads.roads.json" Roads_IslandRoads \
    "$P/IslandRoads.zones.json" "$P/IslandRoads.ground.json" | grep -E "gate:|^── 3/3|FAIL|ERROR" || true
# a zone the cut no longer makes leaves its piece behind, and every later step globs the lanekits: remove it
python3 - <<'PY'
import glob, json, os
P = "assets/world_source/pieces"
R = "src/main/resources/com/openworld/world/pieces"
for net, pref in (("IslandRoads", "island_"), ("IslandRail", "rail_")):
    zf = "%s/%s.zones.json" % (P, net)
    if not os.path.exists(zf):
        continue
    zones = {z["zone_id"] if "zone_id" in z else z.get("id") for z in json.load(open(zf))["zones"]}
    for f in sorted(glob.glob("%s/Roads_%s_%s*.lanekit.json" % (P, net, pref))):
        zid = os.path.basename(f)[len("Roads_%s_" % net):-len(".lanekit.json")]
        if zid not in zones:
            stem = "Roads_%s_%s" % (net, zid)
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
