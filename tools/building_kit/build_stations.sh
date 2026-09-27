#!/usr/bin/env bash
# build_stations.sh -- rebuild every station scene from the station kit, then gate it (PLAN.md "NEXT STEP
# 2026-09-27": the three station forms, one .blend each).
#
#     tools/building_kit/build_stations.sh [--only=Farm,Bay]
#
# 1. export_building_kit.py  each Station_<Form>.blend in kits/stations -> pieces/ + pieces.json (the .blend OWNS its
#                       pieces; a piece whose bounds moved is refused unless ACCEPT_BOUNDS=1)
# 2. godot --import     so new or changed pieces are importable
# 3. station_layout.py  --self-test, then the rail plan -> each station's layout (form, pieces, colliders, gate lanes)
# 4. build_building_scenes.gd -> world/buildings/Station_<Name>{,_Open,_Shop}.tscn (the _Shop one is placed)
# 5. probe_station_paid.gd --scene=... on each: the street and the bed reach no platform with the gates shut, and a
#    platform IS reached through them with the gates open
#
# The .blend files are made ONCE by blender/tools/build_station_blends.py and are then the artist's.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
BLENDER="${BLENDER:-blender}"
cd "$ROOT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ONLY=""
for a in "$@"; do case "$a" in --only=*) ONLY="${a#--only=}" ;; esac; done
for blend in assets/world_source/kits/stations/Station_*.blend; do
    "$BLENDER" -b "$blend" --python-exit-code 1 --python blender/tools/export_building_kit.py > "$TMP/export.log" 2>&1 \
        || { grep -E "export_building_kit|Error" "$TMP/export.log"; exit 1; }
    grep "\[export_building_kit\]" "$TMP/export.log"
done
timeout -k 5 900 "$GODOT" --headless --path . --import > "$TMP/import.log" 2>&1 || { tail -20 "$TMP/import.log"; exit 1; }
python3 tools/station_layout.py --self-test
python3 tools/station_layout.py --write "$TMP/stations.json" ${ONLY:+--only="$ONLY"} | grep -E "station_layout|FINDING" || true
timeout -k 5 900 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/build_building_scenes.gd -- "$TMP/stations.json" 2>&1 \
    | grep -E "pieces ->|BUILD|ERROR"
fail=0
for id in $(python3 -c "import json,sys;print(' '.join(b['id'] for b in json.load(open('$TMP/stations.json'))['buildings']))"); do
    timeout -k 5 600 stdbuf -oL "$GODOT" --headless --path . --script tools/godot/probe_station_paid.gd -- \
        --scene="res://src/main/resources/com/openworld/world/buildings/${id}_Shop.tscn" 2>&1 | grep -E "FAIL|^RESULT" || fail=1
done
exit $fail
