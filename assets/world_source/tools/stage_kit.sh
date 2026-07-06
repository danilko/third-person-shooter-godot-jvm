#!/usr/bin/env bash
# stage_kit.sh — copy exported kit-leaf .glb into res:// so district pieces can instance them
# (each glb carries its -colonly/-convcolonly proxy → collision rides with the instance). Run this
# whenever a kit changes: kit/build_*.py -> <kit>.blend -> tools/export_kit.py -> export/*.glb -> HERE.
set -euo pipefail
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # assets/world_source
REPO="$(cd "$BP/../.." && pwd)"                                # repo root
DEST="$REPO/src/main/resources/com/openworld/world/kit"
mkdir -p "$DEST"
cp "$BP"/export/*.glb "$DEST"/
echo "staged $(ls "$BP"/export/*.glb | wc -l) kit glbs -> res://…/world/kit/"
echo "now re-import so Godot picks them up:"
echo "  <godot> --headless --path \"$REPO\" --import"
