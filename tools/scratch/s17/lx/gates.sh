#!/usr/bin/env bash
cd /data/danilko/git/third-person-shooter
G=/data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64
O=$1; mkdir -p $O
W=res://src/main/resources/com/openworld/world/World.tscn
run() { local n=$1; shift; timeout -k 15 1800 stdbuf -oL $G --headless "$@" > $O/$n.log 2>&1; echo "$n exit $? :: $(grep -E 'RESULT|PASS|FAIL' $O/$n.log | grep -v '^WARNING' | tail -2 | tr '\n' ' ' | cut -c1-300)"; }
run island_zones   --path . --script tools/godot/probe_island_zones.gd
run road_clear     --path . --script tools/godot/probe_road_clear.gd
run road_stamp     --path . --script tools/godot/probe_road_stamp.gd
run road_ground    --path . --script tools/godot/probe_road_ground.gd
run road_zones     --fixed-fps 60 --path . --script tools/godot/probe_road_zones.gd
run traffic_spawn  --path . --script tools/godot/probe_traffic_spawn.gd -- --world=island
run gps_route      --path . --script tools/godot/probe_gps_route.gd -- --world=island
run station_paid   --path . --script tools/godot/probe_station_paid.gd
run rail_track     --path . --script tools/godot/probe_rail_track.gd
run swim_exit      --path . --script tools/godot/probe_swim_exit.gd
run swim_exit_ctl  --path . --script tools/godot/probe_swim_exit.gd -- --control
run stairs         --path . --script tools/godot/probe_stairs.gd
run road_launch    --fixed-fps 60 --path . --script tools/godot/probe_road_launch.gd
for c in shiokaze_dori_F0: shiokaze_dori_R0: koba_waku_w_F0: koba_waku_w_x_F0: gyoko_michi_F0:-1632,-188:8 gyoko_michi_R0:-1452,-192:8 kaigan_dori__x1_F0:-525,-1900 kita_touge_F0:-488,-1857 kaigan_dori_F0:-198,-2008; do
  l=${c%%:*}; rest=${c#*:}; pk=${rest%%:*}; sp=17; [[ $rest == *:*:* ]] && sp=${rest##*:}; extra=""; [ -n "$pk" ] && extra="--park=$pk"
  run launch_$l --fixed-fps 60 --path . --script tools/godot/probe_road_launch.gd -- --world=$W --lane=$l --speed=$sp --seconds=15 $extra
done
echo ALL_DONE
