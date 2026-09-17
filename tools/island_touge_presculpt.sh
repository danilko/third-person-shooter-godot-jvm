#!/usr/bin/env bash
# island_touge_presculpt.sh -- rebuild the terrain the shrine touge is generated FROM (PLAN.md 3.2d).
#
#     tools/island_touge_presculpt.sh <out.f32>
#     python3 tools/island_shrine_touge.py <out.f32> assets/world_source/pieces/IslandRoads.roads.json --sculpt <new.f32>
#
# `island_shrine_touge.py` walks, profiles and sculpts on the ground as it was BEFORE any touge was cut into it.
# That ground is on disk nowhere: the Terrain3D data holds it sculpted and stamped. It is exactly derivable, though:
# the island terrain as committed in a389d61 (before 3.2b's stamp), clamped to the -24 m seabed
# (`set_world_depths.gd`), with the first mountain widened (`island_widen_first_mountain.py`). Verified: the
# generator run on this grid reproduced the 3.2c touge to under 1 mm, and its sculpt equals the stored natural
# ground to 0.9 mm (p99.9).
#
# Then, in THIS order (a stamp record changes what "the ground" reads, see CLAUDE.md):
#   1. stamp_roadkit_terrain.gd -- World.tscn IslandRoads --restore
#   2. dump_height_grid.gd -- <nat_old.f32> -2200 -2000 1301 1351 2.0 ; write nat_old + (sculpt(new) - sculpt(old))
#      with apply_height_grid.gd (a delta, so nothing else in the window moves)
#   3. roadkit_cli.py setback ; write_roadkit_ground.gd ; build_roads_piece.sh ; stamp_roadkit_terrain.gd
set -euo pipefail
OUT="${1:?usage: $0 <out.f32>}"
COMMIT=a389d61
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$ROOT"
mkdir -p "$TMP/island"
for f in $(git ls-tree --name-only "$COMMIT" assets/terrain3d/island/); do
    git show "$COMMIT:$f" | git lfs smudge > "$TMP/island/$(basename "$f")"
done
timeout -k 5 300 "$GODOT" --headless --path . --script tools/godot/dump_height_grid.gd -- \
    "$TMP/head.f32" -2200 -2000 1301 1351 2.0 "$TMP/island" 2>&1 | grep DUMP
python3 - "$TMP/head.f32" "$OUT" <<'EOF'
import sys
import numpy as np
sys.path.insert(0, "tools")
import island_widen_first_mountain as WM
H = np.fromfile(sys.argv[1], dtype=np.float32).reshape(WM.NY, WM.NX)
H = np.where(np.isnan(H), H, np.maximum(H, -24.0)).astype(np.float32)    # set_world_depths.gd TERRAIN_FLOOR
out, _w, _t = WM.widen(H)
out.tofile(sys.argv[2])
print("pre-sculpt grid ->", sys.argv[2])
EOF
