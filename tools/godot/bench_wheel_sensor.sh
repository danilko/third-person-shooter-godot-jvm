#!/usr/bin/env bash
# Wheel-sensor COST, one mode per fresh process, interleaved, N rounds; prints the median per mode.
#   tools/godot/bench_wheel_sensor.sh [rounds=5] [cars=40]
set -u
cd "$(dirname "$0")/../.."
GODOT="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
ROUNDS="${1:-5}"; CARS="${2:-40}"
declare -A ALL
for r in $(seq "$ROUNDS"); do
  for m in rays_1 rays_3 sphere cylinder; do
    ms=$(timeout -k 5 300 "$GODOT" --headless --path . --script tools/godot/bench_wheel_sensor.gd -- --only=$m --cost-only --cars=$CARS 2>/dev/null \
         | sed -n 's/.*cars: \([0-9.]*\) ms.*/\1/p')
    ALL[$m]="${ALL[$m]:-} $ms"
  done
done
for m in rays_1 rays_3 sphere cylinder; do
  med=$(echo ${ALL[$m]} | tr ' ' '\n' | sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}')
  echo "COST $m  median ${med} ms/step  (rounds:${ALL[$m]})"
done
