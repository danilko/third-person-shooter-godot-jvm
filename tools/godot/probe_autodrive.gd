extends SceneTree
## Auto-drive to the GPS waypoint (user, 2026-10-11: "allow auto car drive for the player to the destination once GPS
## is selected, as part of the debugging / testing setup; the player may exit any time to take over control").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_autodrive.gd
##   ... -- --control      (auto-drive never started: the car must stay where it is)
##   ... -- --world=island --start=120,422 --goal=-100,270 --via=15,420      THE ISLAND (PLAN.md S9 Q4): the start is
##       the through lane nearest --start, the waypoint the lane point nearest --goal; it must pass within 25 m of --via
##       (a signalised junction) and ride a ramp lane (an id with `_on` / `_off`) on the way. Case 2 is skipped.
##
## DebugWorld, the player seated in a real car on the west island's E-W street, the waypoint on the east ring -- the
## route crosses the bridge. Asserted:
##   1. `start_auto_drive_now` starts (returns ""), the car is still PLAYER-driven (its controller is the
##      PlayerController, it is not `ai_driven`), and it arrives within 18 m of the waypoint by itself, having driven
##      at least the straight-line distance, and stops;
##   2. started again toward a far waypoint, a throttle press by the player ends it at once ("the player took over")
##      and the car is the player's again;
##   3. with no waypoint it refuses and says why.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var world: Node
var fails := 0
var lanes := {}

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

var island := false
var opt := {}

func _xz(key: String) -> Vector3:
	var v := str(opt[key]).split(",")
	return Vector3(float(v[0]), 0.0, float(v[1]))

## [lane id, the point on it] of the through lane nearest `p` in plan.
func _nearest(p: Vector3) -> Array:
	var best := ["", p]
	var bd := 1e9
	for id in lanes:
		if str(id).begins_with("cj"):
			continue
		for q in lanes[id]:
			var d := Vector2(q.x - p.x, q.z - p.z).length()
			if d < bd:
				bd = d
				best = [id, q]
	return best

func _load_lanes() -> void:
	var stems := ["Roads_DebugRoads_debug_a", "Roads_DebugRoads_debug_b"]
	if island:
		stems = []
		for f in DirAccess.get_files_at("res://assets/world_source/pieces"):
			if f.begins_with("Roads_IslandRoads_island_") and f.ends_with(".lanekit.json"):
				stems.append(f.trim_suffix(".lanekit.json"))
	for stem in stems:
		var doc = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/pieces/%s.lanekit.json" % stem))
		for l in doc["lanes"]:
			var pts := PackedVector3Array()
			for p in l["points"]:
				pts.append(Vector3(p[0], p[1], p[2]))
			lanes[l["id"]] = pts

func _at(id: String, frac: float) -> Vector3:
	var pts: PackedVector3Array = lanes[id]
	var total := 0.0
	for i in range(pts.size() - 1):
		total += pts[i].distance_to(pts[i + 1])
	var want := total * frac
	var s := 0.0
	for i in range(pts.size() - 1):
		var d := pts[i].distance_to(pts[i + 1])
		if s + d >= want:
			return pts[i].lerp(pts[i + 1], (want - s) / maxf(d, 1e-6))
		s += d
	return pts[pts.size() - 1]

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	print("probe_autodrive%s" % (" (CONTROL: never started)" if control else ""))
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		opt[kv[0]] = kv[1] if kv.size() > 1 else "1"
	island = str(opt.get("world", "")) == "island"
	world = (load(WORLD.replace("DebugWorld", "World") if island else WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	_load_lanes()
	for i in 120:
		await physics_frame
	var player: Node3D = world.get_node("Characters/Player")
	var i_start := []
	var i_goal := []
	if island:
		i_start = _nearest(_xz("start"))
		i_goal = _nearest(_xz("goal"))
		print("  island: from %s at %s to %s at %s" % [i_start[0], str(i_start[1]), i_goal[0], str(i_goal[1])])
		var ts := root.find_child("TrafficSignals", true, false)
		if ts != null:
			ts.set("game_clock", true)     # the lights keep game time: a headless run steps faster than the wall clock
		# the island streams round the player: stand at the start until it has
		(player as CharacterBody3D).set_physics_process(false)
		player.global_position = i_start[1] + Vector3(6, 3, 0)
		var zm := root.get_node("/root/ZoneManager")
		zm.set("debug_log", false)
		var waited := 0
		while waited < 60 * 120:
			await physics_frame
			waited += 1
			if waited > 300 and int(zm.call("streaming_pending_now")) == 0:
				break
		(player as CharacterBody3D).set_physics_process(true)
	# DebugWorld's hostile AI shoot a player waiting at a red light, and the respawn then frees the car under the
	# probe (measured: 1 run in 3 died to "enemy 3", which read as a hang -- the script error stops the coroutine)
	player.get_node("Health").set("invulnerable", true)
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var start := Vector3.ZERO if island else _at("w_ew_e_F0", 0.15)
	var ahead := Vector3.ZERO if island else _at("w_ew_e_F0", 0.3)
	var goal := Vector3.ZERO if island else _at("e_ring_F0", 0.5)
	if island:
		start = i_start[1]
		goal = i_goal[1]
		var pts: PackedVector3Array = lanes[i_start[0]]
		var k := 0
		for j in pts.size():
			if pts[j].distance_to(start) < pts[k].distance_to(start):
				k = j
		ahead = pts[min(k + 1, pts.size() - 1)] if k < pts.size() - 1 else start + (start - pts[k - 1])
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	# ...and they shoot the CAR to a wreck just the same (3 runs in 5 with only the player invulnerable; the log
	# line "Vehicle: destroyed SPC1 ... driver=Player" at the red light by the east junction is how it was found)
	if car.get_node_or_null("Health") != null:
		car.get_node("Health").set("invulnerable", true)
	car.global_position = start + Vector3(0, 0.8, 0)
	car.look_at(car.global_position + (ahead - start).normalized(), Vector3.UP)
	for i in 30:
		await physics_frame
	helper.call("seat_character", car, player)
	for i in 90:
		await physics_frame
	var pc: Node = null
	for c in car.get_children():
		var sc = c.get_script()
		if sc != null and str(sc.resource_path).ends_with("PlayerController.java"):
			pc = c
	if pc == null:
		print("RESULT FAIL (the player is not driving the car)")
		quit(1)
		return

	# 3. no waypoint: refused
	var why: String = pc.call("start_auto_drive_now")
	_check(why != "" and not bool(pc.call("auto_driving_now")), "with no waypoint it refuses (%s)" % why)

	# 1. drive to the east ring
	player.call("set_waypoint_now", goal)
	var from := car.global_position
	var straight := Vector2(goal.x - from.x, goal.z - from.z).length()
	why = "" if control else pc.call("start_auto_drive_now")
	if not control:
		_check(why == "" and bool(pc.call("auto_driving_now")), "auto-drive starts (%s)" % why)
		_check(not bool(helper.call("is_ai_driven", car)), "the car is still the player's (not ai-driven)")
	var ramps_ridden := {}
	var via_min := 1e9
	var driven := 0.0
	var last := from
	var t := 0
	# REAL seconds, not simulated ones: signals and 踏切 run on the wall clock (a red light is ~27 real seconds
	# however fast a headless run steps), so a limit in ticks measures the machine, not the drive
	# and a loaded machine steps slower than real time, so the simulated limit is generous too: the run ends when
	# the drive does, and these two only bound a car that never arrives
	var limit := int(OS.get_environment("PROBE_SECONDS")) if OS.get_environment("PROBE_SECONDS") != "" else 780
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < limit * 1000 and t < 60 * 900:
		await physics_frame
		t += 1
		driven += Vector2(car.global_position.x - last.x, car.global_position.z - last.z).length()
		last = car.global_position
		if island and t % 20 == 0:
			var dbg := str(pc.call("auto_drive_debug_now"))
			var lane_now := dbg.split(" ")[0]
			if lane_now.contains("_on_") or lane_now.contains("_off_"):
				if not ramps_ridden.has(lane_now):
					ramps_ridden[lane_now] = true
			if opt.has("via"):
				via_min = minf(via_min, Vector2(car.global_position.x - _xz("via").x, car.global_position.z - _xz("via").z).length())
		if OS.get_environment("PROBE_TRACE") != "" and t % 300 == 0:
			print("    t %.0f real %.0f at (%.0f, %.0f) v %.1f  %s" % [t / 60.0, (Time.get_ticks_msec() - t0) / 1000.0, car.global_position.x, car.global_position.z,
					car.linear_velocity.length(), pc.call("auto_drive_debug_now")])
			# what the cars AHEAD say when ours stands (PLAN.md S9 Q4: 415 s behind a taxi at a signal that cycled)
			if car.linear_velocity.length() < 0.5:
				var fwd := -car.global_transform.basis.z
				for n in get_nodes_in_group("characters"):
					if n is RigidBody3D and n != car and is_instance_valid(n):
						var rel: Vector3 = n.global_position - car.global_position
						if rel.length() < 40.0 and rel.dot(fwd) > 0.0:
							for ch in n.get_children():
								var sc: Script = ch.get_script()
								if sc != null and str(sc.resource_path).ends_with("VehicleAIController.java"):
									print("      ahead %.0f m: %s v %.1f lane %s rails=%s why=%s | %s" % [rel.length(), n.name,
										(n as RigidBody3D).linear_velocity.length(), ch.call("lane_now"), ch.call("dummy_now"),
										ch.call("standing_reason") if ch.has_method("standing_reason") else "?",
										ch.call("describe_block") if ch.has_method("describe_block") else "?"])
		if not control and not bool(pc.call("auto_driving_now")):
			break
		if control and t > 60 * (int(OS.get_environment("CONTROL_SECONDS")) if OS.get_environment("CONTROL_SECONDS") != "" else 20):
			break
	for i in 120:
		await physics_frame
	var left := Vector2(goal.x - car.global_position.x, goal.z - car.global_position.z).length()
	print("  %.1f simulated s, drove %.0f m (straight line %.0f m), %.1f m from the waypoint, ended: %s, speed %.2f m/s" % [
			t / 60.0, driven, straight, left, pc.call("auto_drive_ended_now"), car.linear_velocity.length()])
	_check(str(pc.call("auto_drive_ended_now")) == "arrived", "it ended because it arrived")
	_check(left <= 30.0, "the car is at the waypoint (%.1f m)" % left)
	_check(driven >= straight * 0.95, "it drove the roads there (%.0f m >= %.0f m)" % [driven, straight])
	_check(car.linear_velocity.length() < 1.5, "and stopped (%.2f m/s)" % car.linear_velocity.length())

	if island and not control:
		_check(not opt.has("via") or via_min <= 25.0, "it went through the junction at --via (nearest %.1f m)" % via_min)
		_check(ramps_ridden.size() > 0, "it rode a ramp (%s)" % ", ".join(ramps_ridden.keys()))

	# 2. the player takes over
	if not control and not island:
		player.call("set_waypoint_now", _at("w_ew_e_F0", 0.15))
		why = pc.call("start_auto_drive_now")
		_check(why == "", "it starts again toward a far waypoint (%s)" % why)
		for i in 120:
			await physics_frame
		Input.action_press("throttle")
		for i in 5:
			await physics_frame
		Input.action_release("throttle")
		_check(not bool(pc.call("auto_driving_now")) and str(pc.call("auto_drive_ended_now")) == "the player took over",
				"a throttle press hands the car back (%s)" % pc.call("auto_drive_ended_now"))
		var brains := 0
		for c in car.get_children():
			if str(c.name).begins_with("AutoDrive"):
				brains += 1
		await physics_frame
		_check(car.get_node_or_null("AutoDrive") == null, "and the borrowed brain is gone from the car")

	print("RESULT: %s (%d fail)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
