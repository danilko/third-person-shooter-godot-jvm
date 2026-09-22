#!/usr/bin/env bash
# island_world.sh -- the WHOLE island, in the one order it may be built (PLAN.md 3.30 L0.2, review R4).
#
#   tools/island_world.sh [--from <stage>] [--to <stage>] [--only <stage>]
#
# Everything on the island is derived from the step before it: the land, the roads laid on it, the terrain stamped to
# the roads, the sites, the lots and buildings, the block ground. So each stage is ONE pass, and a later stage never
# edits an earlier one's output by hand -- it re-runs it. The terrain is rebuilt from the committed BASE every time
# (never edited in place), which is what makes it restorable: there is no stamp to undo, only a base to start from.
#
#   land       island_reshape.py build + check              -> assets/world_source/terrain/island_land.f32
#   layout     island_layout.py                             -> IslandRoads.roads.json (from the arterials INPUT)
#   bridge     island_rainbow_bridge.py                     -> World.tscn's Rainbow Bridge on the plan's crossing
#   natural    island_touges.py sculpt ; island_coast.py zones + shelf + check
#                                                           -> assets/world_source/terrain/island_natural.f32
#   terrain    apply_height_grid.gd (every vertex) ; the road stamp record, the natural-ground sidecar and the urban
#              paint marker removed (none of them describes this ground) ; paint_terrain.gd
#   roads      island_rebuild.sh --no-layout (ground sidecar, zones, pieces, stamp, traffic zones, road map)
#   sites      island_sites.py (the FROZEN sites; re-search by hand with --resite)
#   buildings  dump the stamped terrain ; island_buildings.py derive + write ; build_building_hlod.gd
#   ground     dump ; island_ground.py derive ; apply_height_grid.gd + apply_paint_grid.gd
#
# The natural grid is committed: it is the restore (a stamp can always be undone by applying it again), and the
# `terrain` stage is the only thing that writes Terrain3D's heights wholesale.
set -euo pipefail
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
P=assets/world_source/pieces
T=assets/world_source/terrain
W=src/main/resources/com/openworld/world/World.tscn
D=res://assets/terrain3d/island
TMP=${TMPDIR:-/tmp}/island_world.$$
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT
STAGES=(land layout bridge natural terrain roads sites buildings ground)
FROM=${STAGES[0]}; TO=${STAGES[-1]}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from) FROM=$2; shift 2 ;;
        --to) TO=$2; shift 2 ;;
        --only) FROM=$2; TO=$2; shift 2 ;;
        *) echo "unknown argument $1"; exit 2 ;;
    esac
done
idx() { local i; for i in "${!STAGES[@]}"; do [[ ${STAGES[$i]} == "$1" ]] && { echo "$i"; return; }; done
        echo "unknown stage $1" >&2; exit 2; }
LO=$(idx "$FROM"); HI=$(idx "$TO")
want() { local i; i=$(idx "$1"); (( i >= LO && i <= HI )); }
godot() { timeout -k 5 "$1" stdbuf -oL "$G" --headless --path . --script "${@:2}"; }

if want land; then
    echo "── land"
    python3 tools/island_reshape.py build | tail -2
fi
if want layout; then
    echo "── layout"
    python3 tools/island_layout.py | grep -E "^island_layout|^island_grades" | tail -6
fi
if want bridge; then
    echo "── bridge"
    python3 tools/island_rainbow_bridge.py | tail -2
fi
if want natural; then
    echo "── natural"
    python3 tools/island_touges.py sculpt "$T/island_land.f32" "$P/IslandRoads.roads.json" "$TMP/sculpted.f32"
    python3 tools/island_coast.py zones
    python3 tools/island_coast.py shelf "$TMP/sculpted.f32" "$T/island_natural.f32"
    python3 tools/island_coast.py check "$T/island_natural.f32" "$TMP/sculpted.f32"
fi
if want terrain; then
    echo "── terrain"
    godot 900 tools/godot/apply_height_grid.gd -- "$D" "$T/island_natural.f32" -2304 -2304 2305 2305 2 | tail -2
    rm -f "$P/IslandRoads.stamp.json" "$P/IslandRoads.ground.bin" "$P/IslandRoads.ground.json" \
          assets/terrain3d/island/urban_paint.marker assets/terrain3d/island/urban_block.layer
    godot 900 tools/godot/paint_terrain.gd -- "$D" | tail -2
fi
if want roads; then
    echo "── roads"
    tools/island_rebuild.sh --no-layout
fi
if want sites; then
    echo "── sites"
    python3 tools/island_sites.py | tail -2
fi
if want buildings; then
    echo "── buildings"
    godot 900 tools/godot/dump_height_grid.gd -- "$TMP/stamped.f32" -2304 -2304 2305 2305 2 | tail -1
    python3 tools/island_buildings.py derive "$TMP/stamped.f32" | tail -3
    python3 tools/island_buildings.py write | tail -2
    godot 600 tools/godot/build_building_hlod.gd | tail -1      # R9: each cell's HLOD, from write's boxes
fi
if want ground; then
    echo "── ground"
    godot 900 tools/godot/dump_height_grid.gd -- "$TMP/before_ground.f32" -2304 -2304 2305 2305 2 | tail -1
    python3 tools/island_ground.py derive "$TMP/before_ground.f32" --out "$TMP/block" | tail -3
    godot 900 tools/godot/apply_height_grid.gd -- "$D" "$TMP/block.height.f32" -2304 -2304 2305 2305 2 | tail -1
    godot 900 tools/godot/apply_paint_grid.gd -- "$D" "$TMP/block.paint.u8" -2304 -2304 2305 2305 2 4 "$TMP/block.height.f32" | tail -2   # 4 = Urban
fi
echo "── done"
