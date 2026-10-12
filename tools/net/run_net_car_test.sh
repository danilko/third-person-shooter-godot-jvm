#!/usr/bin/env bash
# Co-op cars (user 2026-10-11: "co-op vehicle the guest / host should be able to interact with each other").
# Host + client headless on DebugWorld, DebugHarness `--car-test=<driver>:<obstacle>`: one peer's player takes the
# wheel and holds the throttle; the other peer's player stands in its way (ped), sits in the kei
# truck 10 m ahead of the police car (seated), or that truck is left empty (parked, host-simulated). Exit 0 = every case passes.
# Three players: a case naming guest2 (guest:seated:guest2 = a client into a client's car, which only the host's relay
# carries) starts a second joiner; the peer that is neither driver nor sitter is a bystander and must agree too.
#   tools/net/run_net_car_test.sh --three      the five cases with a third player
#   tools/net/run_net_car_test.sh [--control] [case ...]        default: all six; --control = a remote car is a wall and is never moved
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
SECS="${SECS:-42}"
SCENE=res://src/main/resources/com/openworld/world/DebugWorld.tscn
EXTRA=""
if [ "${1:-}" = "--control" ]; then EXTRA="--car-test-control"; shift; fi
THREE=(guest:seated:guest2 guest2:seated:guest host:seated:guest2 guest2:seated:host guest2:parked)
if [ "${1:-}" = "--three" ]; then shift; set -- "${THREE[@]}" "$@"; fi
CASES=("$@")
[ ${#CASES[@]} -eq 0 ] && CASES=(guest:ped host:ped guest:parked host:parked guest:seated host:seated)
run_case() {   # <case> <dir>
  mkdir -p "$2"
  local n=2 second=""
  case "$1" in *guest2*) n=3 ;; esac
  timeout -k 5 $((SECS + 18)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=host --car-test=$1 --car-peers=$n $EXTRA > "$2/host.log" 2>&1 &
  local host=$!
  sleep 6
  timeout -k 5 $((SECS + 6)) stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --car-test=$1 --car-peers=$n $EXTRA > "$2/client.log" 2>&1 &
  local first=$!
  if [ $n -eq 3 ]; then
    sleep 6
    timeout -k 5 $SECS stdbuf -oL "$G" --headless --path . "$SCENE" -- --net=join --car-test=$1 --car-peers=3 --car-role=guest2 $EXTRA > "$2/client2.log" 2>&1 &
    second=$!
  fi
  wait $first $second $host 2>/dev/null
}
for c in "${CASES[@]}"; do
  d="$OUT/${c//:/_}"
  run_case "$c" "$d"
  # the stand's own trouble, not the case's: a joiner whose body would not be moved to its mark (DebugHarness prints
  # STUCK with what it found). One retry, and it is said.
  if grep -q "\[cartest\] STUCK" "$d"/*.log; then
    echo "  NOTE  $c: a body would not be moved to its mark -- $(grep -h -m1 '\[cartest\] STUCK' "$d"/*.log | head -1)"
    mv "$d" "$d.stuck"; run_case "$c" "$d"
  fi
done
echo "logs in $OUT"
python3 tools/net/car_test_report.py "$OUT" "${CASES[@]}"
