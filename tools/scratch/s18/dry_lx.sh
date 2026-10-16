#!/bin/bash
# S18 踏切 batch dry run (any step): rail reserve (committed path, as island_world.sh) -> dry layout into $1 -> the rail record
# from the DRY roads into $1 -> the 踏切 judged on the pair
set -u
D=$1
cd /data/danilko/git/third-person-shooter
echo "== rail reserve"; python3 tools/island_rail_layout.py --layout tokyo_straight --reserve | grep -E "ON A CURVE|IN PLATFORM|reserve: .* -- |^reserve: [0-9]"
echo "== dry"; python3 -u tools/scratch/s15/dry.py "$D" --expect ""
echo "== rail record (dry roads)"
python3 - "$D" <<'PY'
import sys, os
sys.path.insert(0, "tools")
D = sys.argv[1]
import island_rail_layout as R
R.RECORD = os.path.join(D, "IslandRoads.roads.json")
import island_rail_record as RR
RR.main(["--layout", "tokyo_straight", "--out", os.path.join(D, "IslandRail.roads.json"), "--scene", ""])
import island_layout as IL
for r in IL.level_crossings(os.path.join(D, "IslandRoads.roads.json"), os.path.join(D, "IslandRail.roads.json"), IL.arterial_names()):
    print("LX %-22s x %-14s at %s angle %5.1f junction %5.1f  %s" % (r[0], r[1], r[2], r[3], r[4], "; ".join(r[5]) or "ok"))
PY
echo "== done"
