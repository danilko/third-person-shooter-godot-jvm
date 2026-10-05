extends SceneTree
## An AI car STOPS before every 踏切 (Road Traffic Act art. 33, 一時停止) and enters only with room past it (PLAN.md
## R-1 / decision 1). On DebugWorld's level crossings, with the shipped traffic brain (VehicleAIController's
## `crossing_stops`), the crossing forced OPEN (`TrainSystem.crossings_forced_open`) so the rule is measured alone:
##   1. an open crossing: the car stands at the hold line for >= 1 s, then drives over it;
##   2. a car standing just past the crossing: the car holds at the line and never enters (it would be left on the
##      tracks behind it);
##   ...and `-- --control` (`crossing_stops` off) fails both: it rolls over without stopping, and it drives onto the
##   crossing behind the standing car.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_lx_stop.gd [-- --control]

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const CTRL := "res://src/main/java/com/openworld/debug/LaneDriveProbeController.java"
const HOLD_BACK := 9.0       # world.TrainSystem.HOLD_BACK
const SPEED := 12.0

var world: Node
var trains: Node
var fails := 0
var checks := 0
var control := false
var verbose := false

func _check(ok: bool, what: String) -> void:
	checks += 1
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _lane(name: String) -> Node:
	for n in world.find_children(name, "Node", true, false):
		if n.get_node_or_null("Path3D") != null:
			return n
	return null

func _car(path: Path3D, s: float, lane_name: String, brain_on: bool) -> RigidBody3D:
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	var at := path.to_global(path.curve.sample_baked(s))
	var f := path.to_global(path.curve.sample_baked(s + 4.0)) - at
	f.y = 0
	if brain_on:
		var brain = load(CTRL).new()
		brain.set("cruise_speed", SPEED)
		brain.set("cruise_throttle", 1.0)
		brain.set("see_obstacles", true)
		brain.set("crossing_stops", not control)
		brain.name = "Brain"
		car.add_child(brain)
	world.add_child(car)
	car.global_position = at + Vector3(0, 0.8, 0)
	car.look_at(car.global_position + f.normalized(), Vector3.UP)
	if brain_on:
		car.linear_velocity = f.normalized() * SPEED * 0.5
		car.get_node("Brain").call("drive_lane", lane_name)
	else:
		car.freeze = true
	return car

## Drive from `s0` for `secs`; returns {stop_s (longest stand within 3 m of the hold line), max_s, min_v_near}.
func _drive(path: Path3D, car: RigidBody3D, hold: float, secs: float) -> Dictionary:
	var r := {"stand": 0.0, "max_s": -1.0, "min_v_near": 99.0}
	var stand := 0.0
	for i in int(secs * 60):
		await physics_frame
		var s := path.curve.get_closest_offset(path.to_local(car.global_position))
		var v := Vector2(car.linear_velocity.x, car.linear_velocity.z).length()
		r["max_s"] = maxf(r["max_s"], s)
		if verbose and i % 30 == 0:
			var br = car.get_node_or_null("Brain")
			print("    t %.1f s %.1f v %.2f stops %s" % [i / 60.0, s, v, str(br.call("crossing_stops_now")) if br else "-"])
		# the longest stand BEFORE the crossing (the hold line is the controller's own number: judged by its count)
		if s < hold:
			r["min_v_near"] = minf(r["min_v_near"], v) if s > hold - 15.0 else r["min_v_near"]
			stand = stand + 1.0 / 60.0 if v < 0.5 else 0.0
			r["stand"] = maxf(r["stand"], stand)
		var brn = car.get_node_or_null("Brain")
		r["stops"] = int(brn.call("crossing_stops_now")) if brn else 0
	return r

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	verbose = "--verbose" in OS.get_cmdline_user_args()
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	world.get_node("Characters/Player").process_mode = Node.PROCESS_MODE_DISABLED
	trains = root.get_node_or_null("TrainSystem")
	if trains == null:
		print("RESULT: FAIL (no TrainSystem)"); quit(2); return
	trains.set("crossings_forced_open", true)
	var pick := []
	for i in 60 * 30:
		await physics_frame
		if i % 60 != 0:
			continue
		for row in str(trains.call("crossing_lanes_now")).split(";", false):
			var kv := row.split("|")
			var ln := _lane(kv[0])
			if ln != null and float(kv[1]) > 80.0 and not ln.is_in_group("rail_track"):
				pick = [ln, kv[0], float(kv[1])]
				break
		if not pick.is_empty():
			break
	if pick.is_empty():
		print("RESULT: FAIL (no streamed lane with a crossing 80 m in)"); quit(2); return
	var path: Path3D = pick[0].get_node("Path3D")
	var xs: float = pick[2]
	var hold: float = xs - HOLD_BACK
	print("probe: lane %s, crossing at %.1f m, hold line %.1f m%s" % [pick[1], xs, hold, "  (CONTROL)" if control else ""])

	# --- 1. an open crossing: stop, wait, cross
	var car := _car(path, hold - 55.0, pick[1], true)
	var a := await _drive(path, car, hold, 16.0)
	print("probe: open crossing -> stood %.2f s at the line, min speed there %.2f, reached %.1f m (crossing %.1f)"
			% [a["stand"], a["min_v_near"], a["max_s"], xs])
	_check(a["stand"] >= 0.9 and a["stand"] < 3.0 and a["stops"] == 1,
			"the car stands at the hold line for 1 s (一時停止): %.2f s, %d stop(s)" % [a["stand"], a["stops"]])
	_check(a["max_s"] > xs + 12.0, "... and then drives over the crossing")
	car.queue_free()
	for i in 30:
		await physics_frame

	# --- 2. a car standing just past the crossing: hold, never enter
	var blocker := _car(path, xs + HOLD_BACK + 3.0, pick[1], false)
	car = _car(path, hold - 55.0, pick[1], true)
	var b := await _drive(path, car, hold, 14.0)
	print("probe: queued far side -> reached %.1f m (hold line %.1f, crossing %.1f), stood %.2f s"
			% [b["max_s"], hold, xs, b["stand"]])
	_check(b["max_s"] + 2.3 < hold + 1.0, "with a car standing past it, the car does not enter the crossing")
	car.queue_free()
	blocker.queue_free()

	print("RESULT: %s (%d of %d checks failed)" % ["PASS" if fails == 0 else "FAIL", fails, checks])
	quit(1 if fails else 0)
