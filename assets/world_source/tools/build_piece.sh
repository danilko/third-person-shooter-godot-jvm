#!/usr/bin/env bash
# build_piece.sh <name> — the ONE-COMMAND district-piece iteration loop (see BLENDER_CONVENTIONS
# "district piece"). Builds the piece .blend, exports it to res:// as glTF, bakes it to a native
# .tscn via WorldBaker, and points SoloPiece.tscn at it so you can immediately walk-test it.
#
#   tools/build_piece.sh shibuya
#   then: <godot-jvm> --path <repo> res://src/main/resources/com/openworld/world/hosts/SoloPiece.tscn
#
# The master never needs re-baking: its zones' geometry_path already point at these predictable
# res://…/world/districts/District_<Name>.tscn files (resolved lazily at stream time).
#
# Procedural pieces (not PLATEAU precincts) ALSO get a second, independent bake of their
# STREET_LOD_LOW collection (lib/lod_low.py) -> District_<Name>_LOD_LOW.tscn, wired at the same
# predictable path world_grid.lod_low_piece_path() computes — WorldZoneMarker streams it in
# whenever the full-detail piece is unloaded (see WorldZoneManager load()/unload()). Detected by
# grepping step 1's own stdout for the "lod_low[" stat it only prints on that branch — PLATEAU
# precincts never build that collection, so the second export/bake is skipped for them.
set -euo pipefail

# Every throwaway bake-host .tscn/.import (and export log) bake_one() creates gets registered
# here, so an interrupted or failed run (Ctrl-C, a Blender/Godot crash) still cleans up on exit
# instead of leaving a stray _bake_*.tscn behind in districts/ — the per-call `rm -f` below only
# covers the success path.
CLEANUP_FILES=()
trap 'rm -f "${CLEANUP_FILES[@]}" 2>/dev/null || true' EXIT

# Two forms:
#   build_piece.sh <name>                      config-name form (e.g. shibuya, city_2_1):
#                                              REGENERATES the .blend first, then exports/bakes.
#   build_piece.sh District_<theme>_<gx>_<gy>  stem form (BAKE-ONLY): skips the regen and
#                                              exports/bakes the EXISTING .blend as-is — use this
#                                              after hand-editing a district .blend so your edits
#                                              go straight to the game without being regenerated
#                                              over (regen preserves only MANUAL/NEIGHBOR_REF).
NAME="${1:?usage: build_piece.sh <name>|District_<theme>_<gx>_<gy>   (e.g. shibuya, or District_city_1_1 to bake an existing .blend without regenerating)}"
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"           # assets/world_source
REPO="$(cd "$BP/../.." && pwd)"                                 # repo root
source "$BP/tools/env.sh"
# NOT --headless for bake/convert runs: MultiMesh data routes through the RenderingServer, and
# the headless dummy RS drops the transform buffers (instances collapse to origin).
RUN=("$GODOT")
command -v xvfb-run >/dev/null 2>&1 && RUN=(xvfb-run -a "$GODOT")
RES_DIR="src/main/resources/com/openworld/world/districts"     # relative to res://
ABS_DIR="$REPO/$RES_DIR"
mkdir -p "$ABS_DIR"

if [[ "$NAME" == District_* ]]; then
  STEM="$NAME"
  BLEND="$BP/districts/$STEM.blend"
  [ -f "$BLEND" ] || { echo "ERROR: $BLEND does not exist (stem form bakes an existing .blend)"; exit 1; }
  echo "── 1/4 SKIP regen (bake-only, stem form) — using existing $BLEND"
  # attempt the LOD_LOW bake and let export_world.py's "nothing to export" skip it cleanly
  # when this piece has no STREET_LOD_LOW collection (PLATEAU precincts).
  HAS_LOD_LOW=true
else
  echo "── 1/4 build piece .blend ($NAME)"
  BUILD_LOG="$($BLENDER --background --python-exit-code 1 --python "$BP/towns/districts/build_district.py" -- "$NAME" 2>&1)" \
      || { echo "$BUILD_LOG" | tail -30; echo "ERROR: build_district.py failed for '$NAME'"; exit 1; }
  echo "$BUILD_LOG" | grep -iE "DISTRICT |PIECE=" || true
  STEM="$(echo "$BUILD_LOG" | grep -oE 'PIECE=[A-Za-z0-9_]+' | head -1 | cut -d= -f2)"
  [ -n "$STEM" ] || { echo "ERROR: build_district.py did not report PIECE=<stem>"; exit 1; }
  BLEND="$BP/districts/$STEM.blend"
  echo "   -> $STEM  ($BLEND)"
  HAS_LOD_LOW=false
  echo "$BUILD_LOG" | grep -q "lod_low\[" && HAS_LOD_LOW=true
fi

# bake_one <gltf-export-args...> <gltf-relpath> <tscn-relpath> — export (with the given extra
# export_world.py args) then bake via a throwaway WorldBaker host scene. Reads the outer-scope
# LANEKIT_PATH (set by the caller, only for the full-detail bake — see below) as an absolute
# filesystem path to a road_kit_authoring combined sidecar (tools/save_lane_kit.py,
# road_blender_godot.md P6.6); empty/unset means "no lanekit_path property at all" — byte-identical
# throwaway host scene to before this existed for every piece that has no sidecar yet.
bake_one() {
  local gltf_rel="$1" tscn_rel="$2"; shift 2
  echo "   export -> res://$gltf_rel"
  local export_log="/tmp/export_$$.log"
  CLEANUP_FILES+=("$export_log")
  # --python-exit-code 1: without it Blender exits 0 even when the export script dies on an
  # unhandled exception, and the bake below silently rebakes a STALE .gltf from the previous run.
  if ! $BLENDER --background "$BLEND" --python-exit-code 1 --python "$BP/tools/export_world.py" -- "$@" "$ABS_DIR/$(basename "$gltf_rel")" >"$export_log" 2>&1; then
    if grep -q "nothing to export" "$export_log"; then
      echo "   (skipped — collection missing/empty)"; return 1
    fi
    cat "$export_log"; return 1
  fi
  $GODOT --headless --path "$REPO" --import >/dev/null 2>&1 || true
  local bake_tscn="$REPO/$RES_DIR/_bake_$$_${RANDOM}.tscn"
  CLEANUP_FILES+=("$bake_tscn" "$bake_tscn.import")
  [[ -n "${LANEKIT_PATH:-}" ]] && echo "   lanekit -> $LANEKIT_PATH"
  {
    cat <<EOF
[gd_scene format=3 uid="uid://bpiecebake${RANDOM}"]
[ext_resource type="Script" path="res://src/main/java/com/openworld/world/WorldBaker.java" id="1"]
[node name="BakePiece" type="Node" unique_id=900000${RANDOM}]
script = ExtResource("1")
source_scene_path = "res://$gltf_rel"
output_scene_path = "res://$tscn_rel"
EOF
    if [[ -n "${LANEKIT_PATH:-}" ]]; then
      printf 'lanekit_path = "%s"\n' "$LANEKIT_PATH"
    fi
    cat <<EOF
bake_on_ready = true
quit_when_done = true
EOF
  } > "$bake_tscn"
  "${RUN[@]}" --path "$REPO" "res://$RES_DIR/$(basename "$bake_tscn")" 2>&1 \
      | grep -iE "WorldBaker: baked" | grep -viE "OCIO" || true
  rm -f "$bake_tscn" "$bake_tscn.import" 2>/dev/null || true
}

# bake_nav <tscn-relpath> — bake a NavigationRegion3D into an already-baked district .tscn (from
# ITS OWN collision geometry) via a throwaway NavBaker host scene, same shape as bake_one() above.
# STATIC_COLLIDERS parsing only reads PhysicsServer3D data (see NavBaker.java), so unlike
# bake_one()'s MultiMesh step this runs --headless — no xvfb dependency, no RenderingServer needed.
bake_nav() {
  local tscn_rel="$1"
  echo "   navmesh -> res://$tscn_rel"
  local nav_tscn="$REPO/$RES_DIR/_navbake_$$_${RANDOM}.tscn"
  CLEANUP_FILES+=("$nav_tscn" "$nav_tscn.import")
  cat > "$nav_tscn" <<EOF
[gd_scene format=3 uid="uid://bnavbake${RANDOM}"]
[ext_resource type="Script" path="res://src/main/java/com/openworld/world/NavBaker.java" id="1"]
[node name="BakeNav" type="Node" unique_id=900001${RANDOM}]
script = ExtResource("1")
scene_path = "res://$tscn_rel"
bake_on_ready = true
quit_when_done = true
EOF
  $GODOT --headless --path "$REPO" "res://$RES_DIR/$(basename "$nav_tscn")" 2>&1 \
      | grep -iE "NavBaker: baked" || true
  rm -f "$nav_tscn" "$nav_tscn.import" 2>/dev/null || true
}

# road_kit_authoring combined traffic sidecar (tools/save_lane_kit.py) — only wired into the
# FULL-DETAIL bake (LOD_LOW is a distant visual-only placeholder, no traffic lanes needed there).
LANEKIT_PATH=""
if [[ -f "$BP/districts/$STEM.lanekit.json" ]]; then
  LANEKIT_PATH="$BP/districts/$STEM.lanekit.json"
fi

echo "── 2-3/5 export + bake full detail -> $STEM.tscn"
bake_one "$RES_DIR/$STEM.gltf" "$RES_DIR/$STEM.tscn"

echo "── 4/5 bake navmesh into $STEM.tscn"
bake_nav "$RES_DIR/$STEM.tscn"

if $HAS_LOD_LOW; then
  echo "── (LOD_LOW) export + bake -> ${STEM}_LOD_LOW.tscn"
  LANEKIT_PATH="" bake_one "$RES_DIR/${STEM}_LOD_LOW.gltf" "$RES_DIR/${STEM}_LOD_LOW.tscn" --only STREET_LOD_LOW || \
      echo "   (no STREET_LOD_LOW content — leaving ${STEM}_LOD_LOW.tscn unbaked)"
else
  echo "── (no STREET_LOD_LOW collection for this piece — PLATEAU precinct, skipping LOD_LOW bake)"
fi

echo "── 5/6 refresh binary district scenes (.tscn -> .scn)"
# The runtime prefers a sibling .scn over the .tscn (WorldZoneManager.resolveGeometryPath) — a
# stale .scn from a previous bake would silently shadow the scene just baked. ConvertDistricts
# mtime-skips unchanged districts, so this only reconverts what this run touched. Same
# non-headless/xvfb pattern as bake_one(): MultiMesh data doesn't survive the headless dummy RS.
"${RUN[@]}" --path "$REPO" res://src/main/resources/com/openworld/world/hosts/ConvertDistricts.tscn 2>&1 \
    | grep -iE "DistrictBinaryConverter: done" || true

echo "── 6/6 point SoloPiece.tscn at $STEM.tscn"
SOLO="$REPO/src/main/resources/com/openworld/world/hosts/SoloPiece.tscn"
python3 - "$SOLO" "res://$RES_DIR/$STEM.tscn" <<'PY'
import re, sys
p, path = sys.argv[1], sys.argv[2]
s = open(p).read()
s = re.sub(r'(\[ext_resource type="PackedScene" path=")[^"]*(" id="piece"\])',
           lambda m: m.group(1) + path + m.group(2), s)
open(p, 'w').write(s)
PY

echo
echo "DONE. Walk-test it:"
echo "  $GODOT --path \"$REPO\" res://src/main/resources/com/openworld/world/hosts/SoloPiece.tscn"
