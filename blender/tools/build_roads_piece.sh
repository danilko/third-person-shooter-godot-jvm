#!/usr/bin/env bash
# build_roads_piece.sh <record.roads.json> <PieceName> -- road option B's whole build (PLAN.md 3.1).
#
#   1. python3 roadkit_cli.py lanekit   -> pieces/<Piece>.lanekit.json   (lane graph, no Blender)
#   2. blender roadkit_build_mesh.py    -> pieces/<Piece>.blend          (the meshes -- Blender's only job)
#   3. build_piece.sh <Piece>           -> world/pieces/<Piece>.tscn/.scn (export, WorldBaker, navmesh)
#
# Run by the Godot Road Kit plugin's Build button, or by hand. NO_SOLO=1 is set so the shared
# SoloPiece.tscn host is not re-pointed by a plugin build.
set -euo pipefail
RECORD="$(cd "$(dirname "${1:?usage: build_roads_piece.sh <record.roads.json> <PieceName>}")" && pwd)/$(basename "$1")"
PIECE="${2:?usage: build_roads_piece.sh <record.roads.json> <PieceName>}"
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$BP/.." && pwd)"
source "$BP/tools/env.sh"
PIECES="$REPO/assets/world_source/pieces"
mkdir -p "$PIECES"

echo "── 1/3 lane graph (python3)"
python3 "$BP/tools/roadkit_cli.py" lanekit "$RECORD" "$PIECES/$PIECE.lanekit.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   gate: %s error(s), %s warning(s), lanes=%s' % (d.get('errors'), d.get('warnings'), d.get('lanes'))); sys.exit(0 if d.get('written') else 1)"

echo "── 2/3 meshes (blender, headless)"
"$BLENDER" --background --python-exit-code 1 --python "$BP/tools/roadkit_build_mesh.py" -- \
    --record "$RECORD" --out "$PIECES/$PIECE.blend" 2>&1 | grep -E "^==|Error|refused" | grep -v OCIO || true
[ -f "$PIECES/$PIECE.blend" ] || { echo "ERROR: mesh build produced no $PIECE.blend"; exit 1; }

echo "── 3/3 export + bake"
NO_SOLO=1 "$BP/tools/build_piece.sh" "$PIECE"
