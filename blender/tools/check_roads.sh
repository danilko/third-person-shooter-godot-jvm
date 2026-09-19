#!/usr/bin/env bash
# check_roads.sh -- ONE COMMAND for the whole road-authoring gate (ROAD_POINT_GRAPH.md 9).
#
# The repo has no CI and the verification story has always been "run these by hand" -- which is the
# same story the previous addon had, with ~3.5 kLOC of smoketests, and it did not prevent this
# rewrite. Hand-run discipline is exactly what decays once a project gets boring, so the five steps
# are wrapped here for a git hook or a GitHub Action to run as a unit. Section 4 is the Godot plugin
# (PLAN.md 3.1 option B), which authors the records the rest of this gate checks.
#
# USAGE:
#     blender/tools/check_roads.sh          # everything
#     blender/tools/check_roads.sh --quick  # pure-Python only (no Godot)
#
# Exits non-zero if anything fails.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BP="$(dirname "$HERE")"
ROOT="$(dirname "$BP")"
ADDON="$BP/addons/road_kit_authoring"

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

pass=0
declare -a failed=()

run() {  # run <label> <cmd...>
  local label="$1"; shift
  local log; log="$(mktemp)"
  if "$@" >"$log" 2>&1; then
    pass=$((pass + 1)); printf 'PASS  %s\n' "$label"
  else
    failed+=("$label"); printf 'FAIL  %s\n' "$label"
    grep -A25 'Traceback (most recent call last)' "$log" | head -30 | sed 's/^/        /'
    tail -5 "$log" | sed 's/^/        /'
  fi
  rm -f "$log"
}

echo "== 1. pure-Python self-tests (no Blender) =="
for f in "$BP"/lib/road_points.py "$BP"/lib/lane_movements.py "$BP"/lib/lane_profile.py \
         "$BP"/lib/road_support.py \
         "$ADDON"/point_model.py "$ADDON"/point_profile.py "$ADDON"/point_solve.py \
         "$ADDON"/point_edges.py "$ADDON"/point_validate.py "$ADDON"/point_export.py \
         "$ADDON"/point_style.py "$ADDON"/point_zones.py "$ADDON"/point_ground.py "$ADDON"/point_record_ops.py "$ADDON"/point_presets.py "$ADDON"/point_digest.py "$ADDON"/point_mesh.py \
         "$ADDON"/point_kit.py "$ADDON"/point_gltf.py "$ADDON"/point_furniture.py; do
  [ -f "$f" ] && run "$(basename "$f")" python3 "$f"
done

echo
echo "== 2. the standing lanekit gate, on a freshly exported testbed =="
TMP="$(mktemp -d)"
run "export testbed -> .lanekit v2" python3 -c "
import sys; sys.path.insert(0, '$ADDON')
import point_validate as pv, point_export as pe
net, _mp, _cp, _rr = pv.build_testbed()
pe.write(net, '$TMP/testbed.lanekit.json')
"
[ -f "$TMP/testbed.lanekit.json" ] && \
  run "check_lanekit_graph.py" python3 "$BP/tools/check_lanekit_graph.py" \
      "$TMP/testbed.lanekit.json"
# PLAN.md 3.13 step 1: the diamond-interchange template, regenerated from the presets, must pass the gate and flow
run "roadkit_interchange.py --check" python3 "$ROOT/tools/roadkit_interchange.py" "$TMP/interchange.roads.json" --check
run "roadkit_interchange.py --kind loop --check" python3 "$ROOT/tools/roadkit_interchange.py" "$TMP/loop.roads.json" --kind loop --check
rm -rf "$TMP"

echo
echo "== 3. the Godot plugin (option B): field table, record, gestures, zones, ground, preview =="
run "gen_roadkit_godot_fields.py --check" python3 "$BP/tools/gen_roadkit_godot_fields.py" --check
# PLAN.md 3.10: World.tscn's road grid and traffic zones are derived; a stale one is a failure.
run "island_road_zones.py --check" python3 "$ROOT/tools/island_road_zones.py" \
    "$ROOT/assets/world_source/pieces/IslandRoads.roads.json" "$ROOT/src/main/resources/com/openworld/world/World.tscn" --check
run "island_traffic_zones.py --check" python3 "$ROOT/tools/island_traffic_zones.py" \
    "$ROOT"/assets/world_source/pieces/Roads_IslandRoads_island_*.lanekit.json \
    "$ROOT/src/main/resources/com/openworld/world/World.tscn" --check
if [ "$QUICK" -eq 0 ]; then
  source "$HERE/env.sh"
  # `timeout -k`: a GDScript error inside `_initialize` HANGS instead of exiting, and a hung Godot
  # does not always honour SIGTERM.
  gd() { (cd "$ROOT" && timeout -k 5 300 "$GODOT" --headless --path . --script "$@"); }
  GT="$(mktemp -d)"
  SAMPLE="$ROOT/assets/world_source/pieces/RoadKitSample.roads.json"
  run "test_roadkit_record (round trip)" gd tools/godot/test_roadkit_record.gd -- "$SAMPLE" "$GT/rt.roads.json"
  run "compare_roads_records (Godot-written == kit)" python3 "$BP/tools/compare_roads_records.py" "$SAMPLE" "$GT/rt.roads.json"
  run "test_roadkit_gestures" gd tools/godot/test_roadkit_gestures.gd -- "$GT/g.roads.json"
  run "test_roadkit_b8 (repairs, branch, bend, gizmo)" gd tools/godot/test_roadkit_b8.gd
  run "test_roadkit_handles (B10.4 junction move/rotate, setback, lanes, fillet)" gd tools/godot/test_roadkit_handles.gd
  run "test_roadkit_tool (B10.3 viewport tool: select, draw, insert, delete, connect)" gd tools/godot/test_roadkit_tool.gd
  run "test_roadkit_native_delete (B10.8 Godot's own Delete + undo, name tags)" gd tools/godot/test_roadkit_native_delete.gd
  run "test_roadkit_ground" gd tools/godot/test_roadkit_ground.gd
  run "test_roadkit_zones" gd tools/godot/test_roadkit_zones.gd -- "$GT/z.json"
  run "test_roadkit_preview" gd tools/godot/test_roadkit_preview.gd
  run "test_roadkit_draft (B10.1 draft surface = the build)" gd tools/godot/test_roadkit_draft.gd
  run "test_roadkit_stamp_rules (3.15 steep cut face)" gd tools/godot/test_roadkit_stamp_rules.gd
  # B11: the road build has no Blender. The committed pieces must BE the build of their records (DebugRoads and
  # RoadKitZones rebuilt and compared, collision proxies included), and styles + profile assets must build.
  run "check_roadkit_build (committed pieces == the build; styles and profile assets)" python3 "$BP/tools/check_roadkit_build.py"
  run "probe_road_ground (DebugWorld supports on the ground)" gd tools/godot/probe_road_ground.gd
  run "probe_road_stamp (DebugWorld terrain carries the roads)" gd tools/godot/probe_road_stamp.gd
  # Inside the REAL editor, where a non-@tool JVM script is a placeholder (`plugin.gd _selftest`): the
  # plugin opens DebugWorld and must show its road pieces and LOAD its points without being asked, leave
  # the scene unmodified and the record byte-identical; a click on a point selects it; a sideways move
  # drapes it and locks a mouth's setback; a save writes exactly that into the record and no point into
  # the scene; Ctrl+Z commits nothing. It edits and saves the real files and restores them byte for byte.
  run "editor self-test (B10.0 editable points, pieces on open, draft materials)" bash -c "cd '$ROOT' && ROADKIT_EDITOR_SELFTEST=res://src/main/resources/com/openworld/world/DebugWorld.tscn timeout -k 5 300 '$GODOT' --headless --editor --path . > '$GT/selftest.log' 2>&1; grep '\[selftest\]' '$GT/selftest.log' >&2; grep -q 'selftest\] RESULT PASS' '$GT/selftest.log'"
  rm -rf "$GT"
fi

echo
printf 'PASS=%d FAIL=%d\n' "$pass" "${#failed[@]}"
if [ "${#failed[@]}" -gt 0 ]; then
  printf 'failed: %s\n' "${failed[*]}"
  exit 1
fi
