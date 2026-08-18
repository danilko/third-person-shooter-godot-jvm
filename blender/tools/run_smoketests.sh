#!/usr/bin/env bash
# run_smoketests.sh -- run the road_kit_authoring headless smoketest suite and report honestly.
#
# WHY THIS SCRIPT EXISTS (2026-08-13). The suite was being run by hand as:
#
#     blender --background --python "$f" --python-exit-code 1
#
# and that reports SUCCESS FOR EVERY TEST, including ones that raise on their first assertion.
# Blender parses its arguments IN ORDER: `--python` runs the script at the point it is parsed, so a
# `--python-exit-code` sitting to its right is not read until after the script has already finished
# and the exit status has been decided. The flag must come BEFORE `--python`. Verified directly:
#
#     blender -b --python boom.py --python-exit-code 1   -> exit 0   (silently green, always)
#     blender -b --python-exit-code 1 --python boom.py    -> exit 1   (correct)
#
# This is the twin of `ROAD_KIT_REDESIGN.md` defect 11 -- there, a gate that could never pass; here,
# a gate that could never fail. Both carry no information, and this one is worse because it looks
# like reassurance. `tools/build_piece.sh` already had the order right; only the test suite did not.
#
# So the invocation lives in a script rather than in a README line anyone can retype wrongly.
#
# USAGE:
#     blender/tools/run_smoketests.sh              # all smoketests
#     blender/tools/run_smoketests.sh median curb  # only tests whose name matches a filter
#
# Exits non-zero if any test fails, and prints the failing test's output.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
TESTS="$ROOT/addons/road_kit_authoring"
BLENDER="${BLENDER:-blender}"

shopt -s nullglob
files=()
for f in "$TESTS"/smoketest_*.py; do
  if [ "$#" -eq 0 ]; then
    files+=("$f")
  else
    for pat in "$@"; do
      case "$(basename "$f")" in *"$pat"*) files+=("$f"); break;; esac
    done
  fi
done

pass=0
declare -a failed=()
for f in "${files[@]}"; do
  name="$(basename "$f" .py)"
  log="$(mktemp)"
  # --python-exit-code BEFORE --python. See the header.
  if "$BLENDER" --background --python-exit-code 1 --python "$f" >"$log" 2>&1; then
    pass=$((pass + 1))
    printf 'PASS  %s\n' "$name"
  else
    failed+=("$name")
    printf 'FAIL  %s\n' "$name"
    # The traceback, not the whole Blender startup banner.
    grep -A30 'Traceback (most recent call last)' "$log" | head -40 | sed 's/^/        /'
  fi
  rm -f "$log"
done

echo
printf 'PASS=%d FAIL=%d\n' "$pass" "${#failed[@]}"
if [ "${#failed[@]}" -gt 0 ]; then
  printf 'failed: %s\n' "${failed[*]}"
  exit 1
fi
