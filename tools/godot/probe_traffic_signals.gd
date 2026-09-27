extends SceneTree
## The traffic signals WORK (user, 2026-09-26: "enable both pedestrian + traffic light"): world.TrafficSignals runs
## the road build's plan (`<network>.signals.json`, point_furniture.signal_plan) on DebugWorld's real streamed roads.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_signals.gd
##   ... -- --control      (TrafficSignals.enabled off: the car runs the red)
##
##   1. the plan is loaded: signalised junctions and signalled lanes exist;
##   2. near a junction its lamps are lit and its name plates built (a camera parked over it);
##   3. a traffic car driving a signalled lane at a RED stops with its nose short of the stop line, and holds;
##   4. when the light turns GREEN it drives on over the line.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const CTRL := "res://src/main/java/com/openworld/debug/LaneDriveProbeController.java"
const PLAN := "res://assets/world_source/pieces/Roads_DebugRoads.signals.json"
const NOSE := 2.28

var world: Node
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _lane(name: String) -> Node:
	for n in world.find_children(name, "Node", true, false):
		var s = n.get_script()
		if s != null and str(s.resource_path).ends_with("PathLaneRoute.java"):
			return n
	return null

func _nearest_car(me: Node3D) -> float:
	var best := 1e9
	for n in world.find_children("*", "RigidBody3D", true, false):
		if n != me and n.get_script() != null and str(n.get_script().resource_path).ends_with("Vehicle.java"):
			best = minf(best, (n as Node3D).global_position.distance_to(me.global_position))
	return best

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	var ts: Node = root.get_node("TrafficSignals")
	ts.set("game_clock", true)          # --fixed-fps game time is not wall time
	if control:
		ts.set("enabled", false)
	var plan = JSON.parse_string(FileAccess.get_file_as_string(PLAN))
	var stop_back := {}
	var centre := {}
	for j in plan["junctions"]:
		for a in j["arms"]:
			for l in a["in_lanes"]:
				stop_back[l] = float(a["stop_back"])
				centre[l] = Vector3(j["centre"][0], j["centre"][1], j["centre"][2])
	# 1. the plan, once the roads have streamed
	var lane: Node = null
	var lane_id := ""
	for i in 60 * 40:
		await physics_frame
		if int(ts.call("junctions_now")) == 0:
			continue
		for l in str(ts.call("signalled_lanes_now")).split(","):
			var n := _lane(l)
			if n == null:
				continue
			var p: Path3D = n.get_node_or_null("Path3D")
			if p != null and p.curve != null and p.curve.get_baked_length() > 70.0:
				lane = n
				lane_id = l
				break
		if lane != null:
			break
	_check(int(ts.call("junctions_now")) > 0 and lane != null,
			"the signal plan is loaded (%d junction(s)); a signalled lane streams (%s)" % [ts.call("junctions_now"), lane_id])
	if lane == null:
		print("RESULT: FAIL"); quit(1); return
	var path: Path3D = lane.get_node("Path3D")
	var L := path.curve.get_baked_length()

	# 2. lamps and plates near the junction (a camera over it); the parked player moved there so every zone of the
	# junction streams in (a lamp on a pole that has not streamed stays dark, by design)
	player.global_position = path.to_global(path.curve.sample_baked(L)) + Vector3(0, 1, 0)
	for i in 60 * 8:
		await physics_frame
	var cam := Camera3D.new()
	world.add_child(cam)
	var c: Vector3 = centre[lane_id] + Vector3(0, 5.6 if world.get_node_or_null("IslandRoads") else 0.0, 0)
	cam.global_position = path.to_global(path.curve.sample_baked(L - 30.0)) + Vector3(0, 6, 0)
	cam.look_at(path.to_global(path.curve.sample_baked(L)), Vector3.UP)
	cam.current = true
	for i in 30:
		await process_frame
	_check(int(ts.call("lit_lamps_now")) > 0 or control, "lamps are lit near the junction (%d lit, %d junction(s) built)"
			% [ts.call("lit_lamps_now"), ts.call("views_now")])
	# the vehicle heads light too (user, 2026-09-26: "the upper traffic light seem never work")
	_check(int(ts.call("lit_vehicle_lamps_now")) > 0 or control, "the vehicle heads are lit (%d vehicle lens(es))"
			% ts.call("lit_vehicle_lamps_now"))
	# the lit lamps are the LENS meshes of TrafficLight_2_Japan.blend (lamps.json), never the fallback ball
	_check(int(ts.call("lens_lamps_now")) > 0 or control, "the lamps are the lens meshes (%d lens node(s))"
			% ts.call("lens_lamps_now"))
	_check(int(ts.call("plates_now")) > 0 or control, "name plates are built (%d label(s))" % ts.call("plates_now"))

	# 3. wait for a red long enough for the approach, then drive the lane
	var waited := 0
	while not (str(ts.call("lane_state_now", lane_id)) == "R" and float(ts.call("seconds_until_now", lane_id, "G")) > 14.0):
		await physics_frame
		waited += 1
		if waited > 60 * 90:
			break
	var green_in := float(ts.call("seconds_until_now", lane_id, "G"))
	print("probe: lane %s (%.0f m), stop line %.2f m before its end; red for %.1f s more" % [lane_id, L,
			stop_back[lane_id], green_in])
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	var brain = load(CTRL).new()
	brain.set("cruise_speed", 12.0)
	brain.set("ignore_speed_limit", false)
	car.add_child(brain)
	world.add_child(car)
	var s0 := maxf(4.0, L - 60.0)
	var start := path.to_global(path.curve.sample_baked(s0))
	var f := path.to_global(path.curve.sample_baked(s0 + 4.0)) - start
	f.y = 0
	car.global_position = start + Vector3(0, 0.8, 0)
	car.look_at(car.global_position + f.normalized(), Vector3.UP)
	car.linear_velocity = f.normalized() * 10.0
	var ok_lane = brain.call("drive_lane", lane_id)
	print("probe: drive_lane -> %s, car at s %.1f" % [ok_lane, s0])
	var line := L - float(stop_back[lane_id])
	var best_speed := 99.0
	var nose_at := 0.0
	var first_stop := -1.0     # the car's OWN stop (an ambient car stopping behind may bump it on)
	var max_nose := -1e9
	for i in int((green_in - 1.0) * 60):
		await physics_frame
		var off := path.curve.get_closest_offset(path.to_local(car.global_position))
		nose_at = off + NOSE
		if off > s0 + 20.0:
			var v := Vector2(car.linear_velocity.x, car.linear_velocity.z).length()
			best_speed = minf(best_speed, v)
			if first_stop < -1e8 or (first_stop < 0.0 and v < 0.2):
				first_stop = nose_at if v < 0.2 else first_stop
		max_nose = maxf(max_nose, nose_at)
		if i % 120 == 0:
			print("probe:   t %.0f s  off %.1f  v %.2f  pos %s  %s" % [i / 60.0, off,
					Vector2(car.linear_velocity.x, car.linear_velocity.z).length(), car.global_position,
					str(ts.call("lane_state_now", lane_id)) + " lane=" + str(brain.call("current_lane_name")) + " nearest-car=%.1f" % _nearest_car(car)])
	print("probe: at the red the car's nose stopped %.2f m from the stop line (negative = short of it); furthest %.2f m;"
			% [first_stop - line, max_nose - line] + " speed now %.2f m/s" % best_speed)
	_check(first_stop >= 0.0 and first_stop <= line + 0.5 and first_stop > line - 12.0 and max_nose < line + 3.0,
			"a car stops at the RED with its nose at the stop line, and holds (a bump from behind does not send it through)")
	# 4. green: it goes
	for i in 60 * 10:                 # the green comes 1 s after the window above; 9 s to pull away
		await physics_frame
	var moved := car.global_position.distance_to(path.to_global(path.curve.sample_baked(minf(nose_at - NOSE, L))))
	print("probe: after the green the car is %.1f m on" % moved)
	_check(moved > 8.0, "at the GREEN it drives on over the line")
	# 5. the street name under the player on the minimap (world.StreetNames): parked on the lane, its kanji name
	player.global_position = path.to_global(path.curve.sample_baked(L * 0.5)) + Vector3(0, 1, 0)
	for i in 60:
		await process_frame
	var mm: Node = null
	for n in world.find_children("*", "Control", true, false):
		var sc = n.get_script()
		if sc != null and str(sc.resource_path).ends_with("MinimapController.java"):
			mm = n
	var street := str(mm.call("street_now")) if mm != null else ""
	_check(street != "" and street.unicode_at(0) > 0x3000, "the minimap names the street in kanji (%s)" % street)
	print("RESULT: %s (%d failure%s)" % ["PASS" if fails == 0 else "FAIL", fails, "" if fails == 1 else "s"])
	quit(1 if fails else 0)
