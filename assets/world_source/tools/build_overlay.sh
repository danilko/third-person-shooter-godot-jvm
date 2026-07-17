#!/usr/bin/env bash
# build_overlay.sh <name>|Overlay_<Name> — the one-command OVERLAY iteration loop (AUTHORING_GUIDE
# §5). Overlays are long-span connective structures (highway / rail / bridge) in their own
# world-coordinate .blend beside the master, exported + baked to their own always-resident .tscn
# and instanced as a permanent node in hosts/WorldMaster.tscn (the ARTDECK residency model).
#
#   tools/build_overlay.sh rainbow_bridge      generator form: runs
#                                              overlays/build_<name>_overlay.py (regen-in-place,
#                                              MANUAL preserved), then exports/bakes.
#   tools/build_overlay.sh Overlay_RainbowBridge
#                                              stem form (BAKE-ONLY): skips the generator and
#                                              exports/bakes the EXISTING .blend as-is — use after
#                                              hand-editing (e.g. MANUAL tuning of the span seat).
#
# Mirrors build_piece.sh minus navmesh (overlays carry no pedestrian nav), LOD_LOW, and the
# SoloPiece pointer. Same non-headless/xvfb rule for the bake: MultiMesh data routes through the
# RenderingServer and the headless dummy RS drops the transform buffers.
set -euo pipefail

CLEANUP_FILES=()
trap 'rm -f "${CLEANUP_FILES[@]}" 2>/dev/null || true' EXIT

NAME="${1:?usage: build_overlay.sh <name>|Overlay_<Name>   (e.g. rainbow_bridge, or Overlay_RainbowBridge to bake the existing .blend without regenerating)}"
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"           # assets/world_source
REPO="$(cd "$BP/../.." && pwd)"                                 # repo root
BLENDER="${BLENDER:-blender}"
GODOT="${GODOT:-/data/danilko/bin/godot.linuxbsd.editor.x86_64.jvm.0.15.0}"
RUN=("$GODOT")
command -v xvfb-run >/dev/null 2>&1 && RUN=(xvfb-run -a "$GODOT")
RES_DIR="src/main/resources/com/openworld/world/overlays"       # relative to res://
ABS_DIR="$REPO/$RES_DIR"
mkdir -p "$ABS_DIR"

if [[ "$NAME" == Overlay_* ]]; then
  STEM="$NAME"
  BLEND="$BP/overlays/$STEM.blend"
  [ -f "$BLEND" ] || { echo "ERROR: $BLEND does not exist (stem form bakes an existing .blend)"; exit 1; }
  echo "── 1/3 SKIP generator (bake-only, stem form) — using existing $BLEND"
else
  GEN="$BP/overlays/build_${NAME}_overlay.py"
  [ -f "$GEN" ] || { echo "ERROR: $GEN does not exist"; exit 1; }
  echo "── 1/3 build overlay .blend ($NAME)"
  BUILD_LOG="$($BLENDER --background --python-exit-code 1 --python "$GEN" 2>&1)" \
      || { echo "$BUILD_LOG" | tail -30; echo "ERROR: $GEN failed"; exit 1; }
  echo "$BUILD_LOG" | grep -iE "overlay|OVERLAY=" || true
  STEM="$(echo "$BUILD_LOG" | grep -oE 'OVERLAY=[A-Za-z0-9_]+' | head -1 | cut -d= -f2)"
  [ -n "$STEM" ] || { echo "ERROR: generator did not report OVERLAY=<stem>"; exit 1; }
  BLEND="$BP/overlays/$STEM.blend"
fi

echo "── 2/3 export -> res://$RES_DIR/$STEM.gltf"
EXPORT_LOG="/tmp/export_overlay_$$.log"
CLEANUP_FILES+=("$EXPORT_LOG")
if ! $BLENDER --background "$BLEND" --python-exit-code 1 --python "$BP/tools/export_world.py" -- "$ABS_DIR/$STEM.gltf" >"$EXPORT_LOG" 2>&1; then
  cat "$EXPORT_LOG"; exit 1
fi
$GODOT --headless --path "$REPO" --import >/dev/null 2>&1 || true

echo "── 3/3 bake -> res://$RES_DIR/$STEM.tscn"
BAKE_TSCN="$REPO/$RES_DIR/_bake_$$_${RANDOM}.tscn"
CLEANUP_FILES+=("$BAKE_TSCN" "$BAKE_TSCN.import")
cat > "$BAKE_TSCN" <<EOF
[gd_scene format=3 uid="uid://boverlaybake${RANDOM}"]
[ext_resource type="Script" path="res://src/main/java/com/openworld/world/WorldBaker.java" id="1"]
[node name="BakeOverlay" type="Node" unique_id=900002${RANDOM}]
script = ExtResource("1")
source_scene_path = "res://$RES_DIR/$STEM.gltf"
output_scene_path = "res://$RES_DIR/$STEM.tscn"
bake_on_ready = true
quit_when_done = true
EOF
"${RUN[@]}" --path "$REPO" "res://$RES_DIR/$(basename "$BAKE_TSCN")" 2>&1 \
    | grep -iE "WorldBaker: baked" | grep -viE "OCIO" || true
rm -f "$BAKE_TSCN" "$BAKE_TSCN.import" 2>/dev/null || true

echo
echo "DONE. res://$RES_DIR/$STEM.tscn"
echo "First overlay only: instance it as a permanent node in hosts/WorldMaster.tscn (beside 'Master')."
