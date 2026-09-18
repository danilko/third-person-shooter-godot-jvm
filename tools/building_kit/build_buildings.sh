#!/usr/bin/env bash
# build_buildings.sh -- rebuild every building scene from the kits and the type table, then gate it.
#
#     tools/building_kit/build_buildings.sh [--only=Id,Id]
#
# 1. export_building_kit.py  each kit's .blend -> pieces/ + pieces.json (the .blend OWNS the pieces, PLAN.md
#                       3.6b step 1; refuses a piece whose bounds moved unless ACCEPT_BOUNDS=1)
# 2. godot --import     so new or changed pieces and textures are importable
# 3. layout_buildings.py building_types.json -> piece placements, collision boxes, doors (self-tested first)
# 4. build_building_scenes.gd -> world/buildings/<Id>.tscn + <Id>_mesh.res (merged, one surface per material)
# 5. probe_buildings.gd  size, materials, roof, floor, every door fits the character capsule, walls block it
#
# Renders for looking at it (needs a display): godot --path . --script tools/godot/shot_buildings.gd -- <dir>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
cd "$ROOT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BLENDER="${BLENDER:-blender}"
for kit in assets/world_source/kits/*/kit.json; do
    dir="$(dirname "$kit")"
    blend="$dir/$(basename "$dir").blend"
    [ -f "$blend" ] || continue          # a kit with no .blend yet (not a building kit, or not initialised)
    "$BLENDER" -b "$blend" --python-exit-code 1 --python blender/tools/export_building_kit.py > "$TMP/export.log" 2>&1 \
        || { grep -E "export_building_kit|Error" "$TMP/export.log"; exit 1; }
    grep "\[export_building_kit\]" "$TMP/export.log"
done
timeout -k 5 900 "$GODOT" --headless --path . --import > "$TMP/import.log" 2>&1 || { tail -20 "$TMP/import.log"; exit 1; }
python3 tools/building_kit/layout_buildings.py --self-test | tail -1
python3 tools/building_kit/layout_buildings.py assets/world_source/buildings/building_types.json "$TMP/layout.json"
timeout -k 5 600 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/build_building_scenes.gd -- "$TMP/layout.json" "$@" 2>&1 \
    | grep -E "pieces ->|material|BUILD|ERROR"
timeout -k 5 600 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/probe_buildings.gd 2>&1 | grep -E "^FAIL|^RESULT"
