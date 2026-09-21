extends SceneTree
## An ambient AI car STOPS for a person standing in the road (user, 2026-09-19: "the AI driver will not stop in
## front of player/character to block, whatever is neutral/hostile, is this normal?").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_ai_stops.gd
##   ... -- --control      (the obstacle rays back to the scene's fixed 7 m, single ray: the car drives through)
##
## It was NOT that the car could not see people: the scene's `ObstacleRay` mask is 18 (CHARACTER | VEHICLE).
## It was that the ray reached a fixed 7 m — 0.3 s at 22 m/s, where stopping takes 40-60 m — and was a single
## line down the centreline, so anyone not dead ahead was invisible. Cases, on a real DebugWorld lane with the
## shipped traffic brain:
##   1. a character standing ON the lane centre: the car stops short of them;
##   2. a character standing at the edge of the car's own width (the case a single ray misses entirely);
##   3. a clear lane: the car drives past the same point without braking (so the fix is not "always brake").

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const CTRL := "res://src/main/java/com/openworld/debug/LaneDriveProbeController.java"
const SPEED := 16.0
const RUN_S := 14.0
const NOSE := 2.28           # SPC-1's hull half length (assets/vehicles/SPC1.vehicle.json)

var world: Node
var fails := 0
var control := false

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _lanes() -> Array:
	var out := []
	for n in world.find_children("*", "Node", true, false):
		var s = n.get_script()
		if s != null and str(s.resource_path).ends_with("PathLaneRoute.java") and not str(n.name).begins_with("c"):
			out.append(n)
	return out

## A lane with `need` m of straight ahead of `from_s`, as [lane, path].
func _pick_lane(need: float) -> Array:
	for lane in _lanes():
		var path: Path3D = lane.get_node_or_null("Path3D")
		if path == null or path.curve == null or path.curve.get_baked_length() < need + 80.0:
			continue
		var a := path.to_global(path.curve.sample_baked(20.0))
		var b := path.to_global(path.curve.sample_baked(20.0 + need))
		var mid := path.to_global(path.curve.sample_baked(20.0 + need * 0.5))
		var dev := Vector2(mid.x - (a.x + b.x) * 0.5, mid.z - (a.z + b.z) * 0.5).length()
		if dev < 1.0 and absf(a.y - b.y) < 2.0:
			return [lane, path]
	return []

## Drive one AI car down `path` from 20 m, with `blocker_side` metres of lateral offset for a person 70 m on
## (or none when `blocker_side` is NAN). Returns {stopped, gap, min_speed, travelled}.
func _run(path: Path3D, lane_name, blocker_side) -> Dictionary:
	var start := path.to_global(path.curve.sample_baked(20.0))
	var at := path.to_global(path.curve.sample_baked(90.0))
	var ahead := path.to_global(path.curve.sample_baked(95.0))
	var dir := (ahead - at)
	dir.y = 0
	dir = dir.normalized()
	var side := Vector3(-dir.z, 0, dir.x)
	var person: CharacterBody3D = null
	if typeof(blocker_side) == TYPE_FLOAT:
		person = (load(AI) as PackedScene).instantiate()
		world.add_child(person)
		# on the road surface, and NOT process-disabled: a Character enables the stance capsule that matches
		# its stance, and a body that never ticks never gets one -- an invisible person the car drives through
		person.global_position = at + side * float(blocker_side) + Vector3(0, 0.1, 0)
		for i in 10:
			await physics_frame
		person.global_position = at + side * float(blocker_side) + Vector3(0, 0.1, 0)
		var shapes := 0
		for n in person.find_children("*", "CollisionShape3D", true, false):
			if not n.disabled:
				shapes += 1
		print("probe:   blocker layer %d, %d active shape(s), at %.1f, %.1f" % [person.collision_layer, shapes,
				person.global_position.x, person.global_position.z])
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	# the shipped traffic brain, aimed at this lane by name: `LaneDriveProbeController` is normally blind to
	# other bodies (a launch run must not be spoiled by traffic), and `see_obstacles` gives it the SHIPPED
	# sensing back -- which is what this probe is about. The node is added to the car BEFORE the car enters the
	# tree, which is how Vehicle picks its controller up (probe_road_launch's idiom).
	var brain = load(CTRL).new()
	brain.set("cruise_speed", SPEED)
	brain.set("cruise_throttle", 1.0)
	brain.set("see_obstacles", true)
	if control:
		brain.set("obstacle_look_min", 7.0)
		brain.set("obstacle_look_max", 7.0)
	car.add_child(brain)
	world.add_child(car)
	car.global_position = start + Vector3(0, 0.8, 0)
	var f := path.to_global(path.curve.sample_baked(24.0)) - start
	f.y = 0
	car.look_at(car.global_position + f.normalized(), Vector3.UP)
	car.linear_velocity = f.normalized() * SPEED
	if not bool(brain.call("drive_lane", str(lane_name))):
		print("probe: could not put the car on lane %s" % lane_name)
	var r := {"min_speed": 99.0, "gap": -1.0, "travelled": 0.0}
	for i in int(RUN_S * 60):
		var v := Vector2(car.linear_velocity.x, car.linear_velocity.z).length()
		r["travelled"] = (car.global_position - start).length()
		if r["travelled"] > 20.0:
			r["min_speed"] = minf(r["min_speed"], v)
		if person != null:
			# measured from the car's NOSE, not its centre: SPC-1's half length is 2.28 m, so a centre-to-centre
			# 2.6 m IS contact, and a check written on the centre reads a collision as a comfortable stop
			var d: float = Vector2(car.global_position.x - person.global_position.x,
					car.global_position.z - person.global_position.z).length() - NOSE
			if r["gap"] < 0.0 or d < r["gap"]:
				r["gap"] = d
			if not r.has("brake_at") and v < SPEED - 1.5 and r["travelled"] > 25.0:
				var ray: RayCast3D = car.get_node_or_null("ObstacleRay")
				r["brake_at"] = d
				print("probe:   first slowing at gap %.1f m; ray reach %.1f m, hitting %s" % [d,
						ray.target_position.length() if ray else -1.0,
						ray.is_colliding() if ray else "no ray"])
		await physics_frame
	r["stopped"] = r["min_speed"] < 1.0
	r["car"] = car
	r["person"] = person
	return r

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	var waited := 0
	while _pick_lane(90.0).is_empty() and waited < 60 * 30:
		await physics_frame
		waited += 1
	var picked := _pick_lane(90.0)
	if picked.is_empty():
		print("RESULT: FAIL (no straight lane)"); quit(2); return
	var path: Path3D = picked[1]
	print("probe: lane %s, %.0f m long%s" % [picked[0].name, path.curve.get_baked_length(),
			"  (CONTROL: 7 m ray)" if control else ""])

	# --- 1. a person on the lane centre
	var a := await _run(path, picked[0].name, 0.0)
	print("probe: person on the centreline -> min speed %.2f m/s, closest %.1f m, drove %.0f m"
			% [a["min_speed"], a["gap"], a["travelled"]])
	_check(a["stopped"] and a["gap"] > 0.2, "the car stops short of a person standing in its lane")
	a["car"].queue_free()
	a["person"].queue_free()
	for i in 30:
		await physics_frame

	# --- 2. a person at the edge of the car's own width (what a single centre ray misses)
	var b := await _run(path, picked[0].name, 1.0)
	print("probe: person 1.0 m off the centreline -> min speed %.2f m/s, closest %.1f m"
			% [b["min_speed"], b["gap"]])
	_check(b["stopped"] and b["gap"] > 0.2, "... and for one at the edge of its own width")
	b["car"].queue_free()
	b["person"].queue_free()
	for i in 30:
		await physics_frame

	# --- 3. a clear lane: it does NOT brake
	var c := await _run(path, picked[0].name, null)
	print("probe: clear lane -> min speed %.2f m/s, drove %.0f m" % [c["min_speed"], c["travelled"]])
	_check(not c["stopped"] and c["travelled"] > 60.0, "a clear lane is driven without braking")
	c["car"].queue_free()

	print("RESULT: %s (%d failure%s)" % ["PASS" if fails == 0 else "FAIL", fails, "" if fails == 1 else "s"])
	quit(1 if fails else 0)
