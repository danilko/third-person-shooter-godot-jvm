#!/usr/bin/env bash
# build_world.sh — the ONE-COMMAND master-world iteration loop (mirrors build_piece.sh's shape,
# but for the full 4 km layout instead of one district piece). Builds world_master.blend, exports
# it to res:// as glTF, and bakes it to a native .tscn via the checked-in BakeWorldMaster.tscn host
# (its source_scene_path/output_scene_path are fixed — unlike a district piece, there's only one
# master, so no per-run throwaway bake scene needs synthesizing).
#
#   tools/build_world.sh [--full | --with-deck]
#   then: <godot-jvm> --path <repo> res://src/main/resources/com/openworld/world/hosts/WorldMaster.tscn
#
# DEFAULT IS MINIMAL (region/landmark/water markers only — no ArtDeck collision strips; the
# collision-diagnosis baseline). `--full`/`--with-deck` restores the ArtDeck ground layer.
# The world-spanning SafetyFloor slab (formerly `--with-floor`) was removed outright — it
# silently trapped characters below visual ground with no recovery path (see build_world.py's
# parse_args docstring and AUTHORING_GUIDE.md).
#
# Per-district detail is untouched by this script — build_piece.sh handles each district
# separately; WorldMaster.tscn's zones resolve District_<Name>.tscn lazily at stream time.
set -euo pipefail

# Registered here so an interrupted/failed run still cleans up on exit (same convention as
# build_piece.sh) instead of leaving a stray export log behind.
CLEANUP_FILES=()
trap 'rm -f "${CLEANUP_FILES[@]}" 2>/dev/null || true' EXIT

BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"           # blender
REPO="$(cd "$BP/.." && pwd)"                                    # repo root
WORLD_SOURCE="$REPO/assets/world_source"                        # data root
source "$BP/tools/env.sh"
RES_DIR="src/main/resources/com/openworld/world/master"        # relative to res://
ABS_DIR="$REPO/$RES_DIR"
mkdir -p "$ABS_DIR"

echo "── 1/3 build world_master.blend"
BUILD_LOG="$($BLENDER --background --python "$BP/tools/build_world.py" -- "$@" 2>&1)"
echo "$BUILD_LOG" | grep -iE "^WORLD:" || true
BLEND="$WORLD_SOURCE/world_master.blend"
[ -f "$BLEND" ] || { echo "ERROR: build_world.py did not produce $BLEND"; exit 1; }

echo "── 2/3 export -> res://$RES_DIR/World_master.gltf"
EXPORT_LOG="/tmp/export_world_$$.log"
CLEANUP_FILES+=("$EXPORT_LOG")
if ! $BLENDER --background "$BLEND" --python "$BP/tools/export_world.py" -- "$ABS_DIR/World_master.gltf" >"$EXPORT_LOG" 2>&1; then
  cat "$EXPORT_LOG"; exit 1
fi
$GODOT --headless --path "$REPO" --import >/dev/null 2>&1 || true

echo "── 3/3 bake -> res://$RES_DIR/World_master.tscn"
# NOT --headless: WorldBaker's MultiMesh step needs a real RenderingServer (set_instance_transform
# routes through it; the headless dummy RS drops the transform buffer) — see build_piece.sh. The
# master rarely carries mmesh_ markers today, but stay consistent with the district bake path.
run=("$GODOT")
command -v xvfb-run >/dev/null 2>&1 && run=(xvfb-run -a "$GODOT")
"${run[@]}" --path "$REPO" res://src/main/resources/com/openworld/world/hosts/BakeWorldMaster.tscn 2>&1 \
    | grep -iE "WorldBaker: baked" | grep -viE "OCIO" || true

echo
echo "DONE. Walk-test it:"
echo "  $GODOT --path \"$REPO\" res://src/main/resources/com/openworld/world/hosts/WorldMaster.tscn"
