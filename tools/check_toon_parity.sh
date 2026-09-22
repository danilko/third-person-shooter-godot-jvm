#!/usr/bin/env bash
# The character toon look is the same in Godot and in Blender (PLAN.md 6.10).
#
#   tools/check_toon_parity.sh
#
# 1. the Godot uniforms are generated from toon_params.json and not stale (tools/build_toon.py --check);
# 2. one lit sphere rendered by EACH (Godot under xvfb, Blender EEVEE headless) must put the lit->shade
#    edge at the JSON's shade_threshold, keep it narrow, and hold the shade side at shade_tint's luminance;
# 3. the CONTROL (a plain Lambert material, both DCCs) must FAIL the same test, so the gate can tell a ramp
#    from a gradient. Exits 0 only when all of it holds.
set -u
cd "$(dirname "$0")/.."
G=${GODOT:-/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64}
fail=0
python3 tools/build_toon.py --check || fail=1
read -r TH TL < <(python3 -c "
import json; p=json.load(open('assets/vfx/toon/toon_params.json')); t=p['shade_tint']
print(p['shade_threshold'], 0.2126*t[0]+0.7152*t[1]+0.0722*t[2])")
judge() {   # name, output, expect(pass|fail)
  local name=$1 out=$2 expect=$3
  local edge width ratio
  edge=$(grep -oP 'TERMINATOR_NDL \K[-0-9.nan]+' <<<"$out")
  width=$(grep -oP 'EDGE_WIDTH_NDL \K[-0-9.nan]+' <<<"$out")
  ratio=$(grep -oP 'shade/lit \K[0-9.]+' <<<"$out")
  if python3 -c "import sys; e,w,r=float('$edge'),float('$width'),float('$ratio'); sys.exit(0 if abs(e-$TH)<0.03 and w<0.1 and abs(r-$TL)<0.05 else 1)"; then got=pass; else got=fail; fi
  printf '  %-4s %-26s edge N.L %s (want %s)  width %s  shade/lit %s (want %.3f)\n' \
    "$([ "$got" = "$expect" ] && echo PASS || echo FAIL)" "$name" "$edge" "$TH" "$width" "$ratio" "$TL"
  [ "$got" = "$expect" ] || fail=1
}
judge "godot toon"      "$(timeout 300 xvfb-run -a "$G" --path . --script tools/godot/probe_toon_parity.gd 2>&1)" pass
judge "blender toon"    "$(timeout 600 blender -b --factory-startup --python blender/tools/toon_parity_blender.py 2>&1)" pass
judge "godot control"   "$(timeout 300 xvfb-run -a "$G" --path . --script tools/godot/probe_toon_parity.gd -- --control 2>&1)" fail
judge "blender control" "$(timeout 600 blender -b --factory-startup --python blender/tools/toon_parity_blender.py -- --control 2>&1)" fail
[ $fail = 0 ] && echo "toon parity: PASS" || echo "toon parity: FAIL"
exit $fail
