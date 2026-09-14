#!/usr/bin/env bash
# build_roads_piece.sh <record.roads.json> <PieceName> [<zones.json>|""] [<ground.json>] -- road option B's whole build
# (PLAN.md 3.1).
#
#   1. python3 roadkit_cli.py pieces    -> pieces/<Piece>.lanekit.json   (lane graph, no Blender)
#   2. blender roadkit_build_mesh.py    -> pieces/<Piece>.blend          (the meshes -- Blender's only job)
#   3. build_piece.sh <Piece>           -> world/pieces/<Piece>.tscn/.scn (export, WorldBaker, navmesh)
#
# With a zones file (B6, written by the Godot plugin from the scene's ZoneMarkers) <PieceName> is a
# PREFIX and the network is cut into one piece per zone -- `<PieceName>_<zone>`, plus `<PieceName>`
# itself for any run in no zone -- by `point_zones.py`, the one owner of the cut. Without one the
# network is one piece named <PieceName>, exactly as before. The last line printed is
#   ROADKIT_PIECES {"pieces": [{"zone": ..., "piece": ..., "scene": "res://..."}]}
# which is what the plugin wires into each ZoneMarker's Zone.
#
# With a ground sidecar (B6b, `<stem>.ground.json`, the Terrain3D height grid the plugin samples) the
# supports stand on the real ground under every sample. Without one they stand on a lerp of the
# stations' own `ground_z`, which is only right where the ground between two stations is straight.
#
# Run by the Godot Road Kit plugin's Build button, or by hand. NO_SOLO=1 is set so the shared
# SoloPiece.tscn host is not re-pointed by a plugin build.
set -euo pipefail
USAGE="usage: build_roads_piece.sh <record.roads.json> <PieceName> [<zones.json>|\"\"] [<ground.json>]"
RECORD="$(cd "$(dirname "${1:?$USAGE}")" && pwd)/$(basename "$1")"
PIECE="${2:?$USAGE}"
ZONES=""
if [[ -n "${3:-}" ]]; then
  ZONES="$(cd "$(dirname "$3")" && pwd)/$(basename "$3")"
fi
GROUND=""
if [[ -n "${4:-}" ]]; then
  GROUND="$(cd "$(dirname "$4")" && pwd)/$(basename "$4")"
  [ -f "$GROUND" ] || { echo "ERROR: no ground sidecar at $GROUND"; exit 1; }
fi
BP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$BP/.." && pwd)"
source "$BP/tools/env.sh"
PIECES="$REPO/assets/world_source/pieces"
RES_DIR="src/main/resources/com/openworld/world/pieces"
mkdir -p "$PIECES"

echo "── 1/3 lane graph (python3)${ZONES:+, cut by zone}"
TABLE="$(mktemp)"
trap 'rm -f "$TABLE"' EXIT
python3 "$BP/tools/roadkit_cli.py" pieces "$RECORD" "${ZONES:-}" "$PIECES" "$PIECE" > "$TABLE"
python3 - "$TABLE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("failed"):
    sys.exit("ERROR: " + d["error"])
print("   gate: %s error(s), %s warning(s), lanes=%s, zones=%s, cross-zone successors=%s"
      % (d["errors"], d["warnings"], d["lanes"], d["zones"], d["cross_zone"]))
for f in d["findings"]:
    if f["code"].startswith("zone") or f["severity"] == "ERROR":
        print("   [%s] %s: %s" % (f["severity"], f["code"], f["message"]))
for p in d["pieces"]:
    print("   piece %-32s zone %-12r runs=%d pads=%d gores=%d lanes=%d"
          % (p["piece"], p["zone"], p["runs"], p["pads"], p["gores"], p["lanes"]))
if d["dangling"]:
    print("   ERROR: successor(s) naming no lane: %s" % d["dangling"][:4])
sys.exit(0 if d["written"] else 1)
PY
mapfile -t NAMES < <(python3 -c "import json,sys; [print(p['piece']) for p in json.load(open(sys.argv[1]))['pieces']]" "$TABLE")

echo "── 2/3 meshes (blender, headless)${GROUND:+, over the sampled ground}"
"$BLENDER" --background --python-exit-code 1 --python "$BP/tools/roadkit_build_mesh.py" -- \
    --record "$RECORD" --zones "${ZONES:-}" --prefix "$PIECE" --out-dir "$PIECES" --ground "${GROUND:-}" 2>&1 \
  | grep -E "^==|Error|refused|ground grid|terrain below" | grep -v OCIO || true
for n in "${NAMES[@]}"; do
  [ -f "$PIECES/$n.blend" ] || { echo "ERROR: mesh build produced no $n.blend"; exit 1; }
done

for n in "${NAMES[@]}"; do
  echo "── 3/3 export + bake $n"
  NO_SOLO=1 "$BP/tools/build_piece.sh" "$n"
done

python3 - "$TABLE" "$RES_DIR" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("ROADKIT_PIECES " + json.dumps({"pieces": [
    {"zone": p["zone"], "piece": p["piece"], "scene": "res://%s/%s.tscn" % (sys.argv[2], p["piece"])}
    for p in d["pieces"]]}))
PY
