#!/usr/bin/env bash
# run a list of godot probes, print the last result line of each
cd "$(dirname "$0")/../../.."
G=/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64
for spec in "$@"; do
  name=${spec%%:*}; args=""; [[ "$spec" == *:* ]] && args="-- ${spec#*:}"
  if [[ "$name" == res://* ]]; then
    out=$(timeout -k 5 600 stdbuf -oL $G --headless --fixed-fps 60 --path . "$name" $args 2>&1)
  else
    out=$(timeout -k 5 600 stdbuf -oL $G --headless --fixed-fps 60 --path . --script tools/godot/$name.gd $args 2>&1)
  fi
  rc=$?
  echo "=== $spec rc=$rc"
  echo "$out" | grep -E "FAIL|^PASS|PASS \(|RESULT|SUMMARY|yaw [0-9]+/|SCRIPT ERROR|Exception" | grep -vE "^\s+PASS\s" | tail -8
done
