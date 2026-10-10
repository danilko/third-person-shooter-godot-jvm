#!/usr/bin/env bash
# nightly_gates.sh -- run the headless Standard gates (PLAN.md "Standard gates") and write a dated PASS/FAIL table,
# so "it failed on HEAD too" is found the night it starts, not three sessions later (PLAN.md 0.5 / F12).
#
#     tools/nightly_gates.sh [--jobs=4] [--out=<dir>] [--quick] [--only=<substring>]
#
# --quick skips the slow island gates; --only runs the gates whose name contains the substring. Nothing here writes
# into the repo: it builds (./gradlew build), runs ./gradlew test, then each gate with a timeout. Two-process net
# tests run one at a time (they use fixed ports); the rest run --jobs at a time. A gate PASSES when it exits 0 and
# prints no "RESULT FAIL" / "RESULT: FAIL" / "SCRIPT ERROR". The table goes to <out>/gates_<date>.md (default
# ${XDG_STATE_HOME:-~/.local/state}/openworld_gates) and each gate's log beside it; the exit code is the number of
# failed gates (capped at 100). Cron, e.g. 03:00 nightly:
#     0 3 * * *  cd /data/danilko/git/third-person-shooter && tools/nightly_gates.sh >/dev/null 2>&1
set -u
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
JOBS=4 QUICK=0 ONLY="" OUT="${XDG_STATE_HOME:-$HOME/.local/state}/openworld_gates"
for a in "$@"; do
  case "$a" in
    --jobs=*) JOBS=${a#--jobs=} ;;
    --out=*) OUT=${a#--out=} ;;
    --quick) QUICK=1 ;;
    --only=*) ONLY=${a#--only=} ;;
    *) echo "unknown argument $a" >&2; exit 2 ;;
  esac
done
STAMP=$(date +%Y-%m-%d_%H%M)
LOGS="$OUT/logs_$STAMP"
mkdir -p "$LOGS"
TABLE="$OUT/gates_$STAMP.md"

H="stdbuf -oL $G --headless --path ."
HF="stdbuf -oL $G --headless --fixed-fps 60 --path ."
P=tools/godot
# name | timeout seconds | slow (1 = skipped by --quick) | serial (1 = never in parallel) | command
GATES=(
  "weapon_scale|300|0|0|$H --script $P/probe_weapon_scale.gd"
  "weapon_sockets|300|0|0|$H --script $P/probe_weapon_sockets.gd"
  "support_hand_ik|300|0|0|$H --script $P/probe_support_hand_ik.gd"
  "weapon_world_body|300|0|0|$H --script $P/probe_weapon_world_body.gd"
  "weapon_archetypes|300|0|0|$H --script $P/probe_weapon_archetypes.gd"
  "melee|400|0|0|$H --script $P/probe_melee.gd"
  "self_hit|400|0|0|$H --script $P/probe_self_hit.gd"
  "weapon_fit|600|0|0|$HF --script $P/probe_weapon_fit.gd"
  "weapon_fit_crouch|600|0|0|$HF --script $P/probe_weapon_fit.gd -- --stance=crouch"
  "shared_anims|300|0|0|$H --script $P/probe_shared_anims.gd"
  "body_contract_shino|300|0|0|$H --script $P/probe_body_contract.gd -- --body=res://assets/characters/shino/shino.glb"
  "body_contract_fumiriya|300|0|0|$H --script $P/probe_body_contract.gd -- --body=res://assets/characters/fumiriya/fumiriya.glb"
  "character_visuals_shino|400|0|0|$HF --script $P/probe_character_visuals.gd -- --visuals=res://src/main/resources/com/openworld/character/CharacterVisuals_Shino.tscn"
  "character_visuals_fumiriya|400|0|0|$HF --script $P/probe_character_visuals.gd -- --visuals=res://src/main/resources/com/openworld/character/CharacterVisuals_Fumiriya.tscn"
  "recoil_kick|400|0|0|$HF --script $P/probe_recoil_kick.gd"
  "fps_ads|400|0|0|$HF --script $P/probe_fps_ads.gd"
  "input_contexts|300|0|0|$HF --script $P/probe_input_contexts.gd"
  "rebind|300|0|0|$HF --script $P/probe_rebind.gd"
  "aim_debug_auto|600|0|0|$H res://src/main/resources/com/openworld/world/hosts/AimDebugAuto.tscn"
  "faction_presets|400|0|0|$HF --script $P/probe_faction_presets.gd"
  "campaign_factions|200|0|0|$H --script $P/probe_campaign_factions.gd"
  "mission_director|400|0|0|$HF --script $P/probe_mission_director.gd"
  "save_system|400|0|0|$H --script $P/probe_save_system.gd"
  "headshots|400|0|0|$HF --script $P/probe_headshots.gd"
  "muzzle_blocked|300|0|0|$H --script $P/probe_muzzle_blocked.gd"
  "hit_marker|300|0|0|$H --script $P/probe_hit_marker.gd"
  "gamepad|300|0|0|$HF --script $P/probe_gamepad.gd"
  "blood_hit|300|0|0|$HF --script $P/probe_blood_hit.gd"
  "interact|300|0|0|$HF --script $P/probe_interact.gd"
  "weapon_counter|400|0|0|$H --script $P/probe_weapon_counter.gd"
  "front_end|600|0|0|$HF --script $P/probe_front_end.gd"
  "title_continue|600|0|0|$HF --script $P/probe_title_actions.gd -- --role=continue"
  "profile|300|0|0|$HF --script $P/probe_profile.gd"
  "garage|450|0|0|$HF --script $P/probe_garage.gd"
  "race|300|0|0|$HF --script $P/probe_race.gd"
  "minimal_hud|300|0|0|$HF --script $P/probe_minimal_hud.gd"
  "gameplay_events|300|0|0|$HF --script $P/probe_gameplay_events.gd"
  "markers|200|0|0|$H --script $P/probe_markers.gd"
  "world_density|200|0|0|$H --script $P/probe_world_density.gd"
  "stairs|900|0|0|$H --script $P/probe_stairs.gd"
  "building_nav|600|0|0|$H --script $P/check_building_nav.gd"
  "konbini_kill|600|1|0|$H --script $P/probe_konbini_mission.gd -- --case=kill"
  "konbini_spare|600|1|0|$H --script $P/probe_konbini_mission.gd -- --case=spare"
  "activity_fail_retry|600|1|0|$H --script $P/probe_activity.gd -- --activity=m01_konbini --script=fail_retry"
  "activity_replay|600|1|0|$H --script $P/probe_activity.gd -- --activity=m01_konbini --script=replay"
  "console|300|1|0|$HF --script $P/probe_console.gd -- --no-warmup"
  "gang_hangout|400|1|0|$H --script $P/probe_gang_hangout.gd"
  "enforcement|700|1|0|$H --script $P/probe_enforcement.gd"
  "escalation|700|1|0|$H --script $P/probe_escalation.gd"
  "shop_clerk|600|1|0|$H --script $P/probe_shop_clerk.gd"
  "recovery|600|1|0|$H --script $P/probe_recovery.gd"
  "helicopter|400|1|0|$H --script $P/probe_helicopter.gd"
  "traffic_spawn|600|1|0|$HF --script $P/probe_traffic_spawn.gd"
  "traffic_census|1800|1|0|$HF --script $P/probe_traffic_census.gd -- --seconds=40 --min-near=4"
  "traffic_ahead|600|1|0|$H --script $P/probe_traffic_ahead.gd"
  "world_warmup|900|1|0|$HF --script $P/probe_world_warmup.gd"
  "road_clear|3600|1|0|$H --script $P/probe_road_clear.gd"
  "world_boot|300|0|0|$H --quit-after 600 res://src/main/resources/com/openworld/world/World.tscn"
  "net_shot|600|0|1|tools/net/run_net_shot_test.sh"
  "title_coop|400|0|1|tools/net/run_title_coop.sh"
  "net_debugworld|1200|1|1|tools/net/run_net_debugworld.sh"
)

run_gate() {   # name timeout command
  local name=$1 to=$2 cmd=$3 log="$LOGS/$1.log" t0=$SECONDS
  timeout -k 10 "$to" bash -c "$cmd" >"$log" 2>&1
  local rc=$?
  local verdict=PASS
  if [ $rc -ne 0 ]; then verdict="FAIL(exit $rc)"; fi
  if [ $rc -eq 124 ] || [ $rc -eq 137 ]; then verdict="TIMEOUT"; fi
  if grep -qE "RESULT:? FAIL|SCRIPT ERROR" "$log"; then verdict="FAIL"; fi
  echo "$name|$verdict|$((SECONDS - t0))|$(grep -E "RESULT" "$log" | tail -1 | cut -c1-120)" >"$LOGS/$name.result"
}

echo "building..." >&2
build_ok=PASS
./gradlew build -q >"$LOGS/gradle_build.log" 2>&1 || build_ok=FAIL
./gradlew test -q -x shadowJar -x copyDesktopJars -x packageBootstrapJar >"$LOGS/gradle_test.log" 2>&1 && test_ok=PASS || test_ok=FAIL

running=0
serial=()
for row in "${GATES[@]}"; do
  IFS='|' read -r name to slow ser cmd <<<"$row"
  [ -n "$ONLY" ] && [[ "$name" != *"$ONLY"* ]] && continue
  [ "$QUICK" = 1 ] && [ "$slow" = 1 ] && continue
  if [ "$ser" = 1 ]; then serial+=("$row"); continue; fi
  run_gate "$name" "$to" "$cmd" &
  running=$((running + 1))
  if [ "$running" -ge "$JOBS" ]; then wait -n; running=$((running - 1)); fi
done
wait
for row in "${serial[@]}"; do
  IFS='|' read -r name to slow ser cmd <<<"$row"
  run_gate "$name" "$to" "$cmd"
done

fails=0
{
  echo "# Gates $STAMP ($(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD))"
  echo
  echo "| gate | verdict | s | last RESULT line |"
  echo "|---|---|---|---|"
  echo "| gradle build | $build_ok | | |"
  echo "| gradle test | $test_ok | | |"
  for f in "$LOGS"/*.result; do
    [ -e "$f" ] || continue
    IFS='|' read -r name verdict secs last <"$f"
    echo "| $name | $verdict | $secs | $last |"
    [ "$verdict" = PASS ] || fails=$((fails + 1))
  done
} >"$TABLE"
[ "$build_ok" = PASS ] || fails=$((fails + 1))
[ "$test_ok" = PASS ] || fails=$((fails + 1))
cat "$TABLE"
echo "logs: $LOGS" >&2
exit $(( fails > 100 ? 100 : fails ))
