#!/usr/bin/env bash
# build_interiors_only.sh -- the fast loop for kits/interiors buildings: export ONLY the named .blend files, import,
# lay out, build ONLY those scenes and probe ONLY them (build_buildings.sh does every kit and every building).
#
#     tools/building_kit/build_interiors_only.sh Id [Id ...]      (ACCEPT_BOUNDS=1 for a new or resized piece)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
BLENDER="${BLENDER:-blender}"
cd "$ROOT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ids="$(IFS=,; echo "$*")"
probe_ids="$(for i in "$@"; do printf "%s,%s_Open,%s_Shop," "$i" "$i" "$i"; done)"
python3 tools/building_kit/build_library_palette.py --check | tail -1
for id in "$@"; do
    "$BLENDER" -b "assets/world_source/kits/interiors/$id.blend" --python-exit-code 1 \
        --python blender/tools/export_building_kit.py > "$TMP/export.log" 2>&1 \
        || { grep -E "export_building_kit|Error" "$TMP/export.log" | grep -v "arp_\|callback_remove\|OCIO"; exit 1; }
    grep "\[export_building_kit\]" "$TMP/export.log"
done
timeout -k 5 900 "$GODOT" --headless --path . --import > "$TMP/import.log" 2>&1 || { tail -20 "$TMP/import.log"; exit 1; }
python3 tools/building_kit/layout_buildings.py assets/world_source/buildings/building_types.json "$TMP/layout.json"
timeout -k 5 600 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/build_building_scenes.gd -- \
    "$TMP/layout.json" --only="$ids" 2>&1 | grep -E "pieces ->|BUILD|ERROR|SCRIPT ERROR"
timeout -k 5 900 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/probe_buildings.gd -- --only="${probe_ids%,}" 2>&1 \
    | grep -E "^FAIL|^RESULT|SCRIPT ERROR"
