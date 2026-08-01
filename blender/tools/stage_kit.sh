#!/usr/bin/env bash
# stage_kit.sh — copy exported kit-leaf .glb into res:// so district pieces can instance them
# (each glb carries its -colonly/-convcolonly proxy → collision rides with the instance). Run this
# whenever a kit changes: kit/build_*.py -> <kit>.blend -> tools/export_kit.py -> export/*.glb -> HERE.
set -euo pipefail
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # blender
REPO="$(cd "$BP/.." && pwd)"                                   # repo root
WORLD_SOURCE="$REPO/assets/world_source"                       # data root
DEST="$REPO/src/main/resources/com/openworld/world/kit"
mkdir -p "$DEST"
cp "$WORLD_SOURCE"/export/*.glb "$DEST"/
echo "staged $(ls "$WORLD_SOURCE"/export/*.glb | wc -l) kit glbs -> res://…/world/kit/"
echo "now re-import so Godot picks them up:"
echo "  <godot> --headless --path \"$REPO\" --import"
