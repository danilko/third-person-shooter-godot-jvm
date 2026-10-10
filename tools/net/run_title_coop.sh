#!/usr/bin/env bash
# PLAN.md 1.3 rest: co-op started from the TITLE SCREEN's buttons (Host co-op / Join co-op), the way a player does it --
# FrontEnd carries the choice across the scene change into World.tscn. Two instances; each must see the session and
# both players (tools/godot/probe_title_actions.gd --role=host / --role=join). Exit 0 = pass.
set -u
cd "$(dirname "$0")/../.."
G="${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}"
OUT="${OUT:-$(mktemp -d)}"
P=tools/godot/probe_title_actions.gd

timeout 300 stdbuf -oL "$G" --headless --fixed-fps 60 --path . --script "$P" -- --role=host > "$OUT/host.log" 2>&1 &
HOST=$!
sleep 8   # the host's world loads first, so the join finds a server
timeout 280 stdbuf -oL "$G" --headless --fixed-fps 60 --path . --script "$P" -- --role=join > "$OUT/join.log" 2>&1 &
JOIN=$!
wait $JOIN; JRC=$?
wait $HOST; HRC=$?
for f in host join; do
  echo "--- $f"
  grep -E "  (PASS|FAIL)|RESULT|SUMMARY|FrontEnd:" "$OUT/$f.log"
done
echo "logs: $OUT"
[ $HRC -eq 0 ] && [ $JRC -eq 0 ]
