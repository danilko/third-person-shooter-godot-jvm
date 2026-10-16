extends SceneTree
## The safe house's BIKE ROW and the console's `spawn` (PLAN.md 3.1b: world.HomeBikes, DebugConsole spawn), on the
## real World.tscn.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_home_bikes.gd
##   OW_TEST_BIKES=1 stdbuf -oL ... --script tools/godot/probe_home_bikes.gd     (all five bikes in the row)
##   ... --script tools/godot/probe_home_bikes.gd -- --debug-world                  (DebugWorld.tscn instead)
##   The two runs are each other's control: the shipped run fails on a five-bike row, the OW_TEST_BIKES run on one bike.
##
## 1. the world has its row: SCT1 alone (shipped), or SCT1 POB1 TRB1 SSB1 PMB1 with OW_TEST_BIKES=1 -- each exactly once;
## 2. the row stands beside the starting car, outside the garage's bay, one bike per slot (none overlapping);
## 3. parked: after 3 s every bike is still where it was set down, at rest, upright on its stand;
## 4. the player gets on the home scooter (Vehicle.tryEnter, through VehicleProbeHelper);
## 5. `spawn` lists the ids, `spawn ssb1` parks an SSB1 ~4 m from the player, `spawn nope` spawns nothing.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const DEBUG_WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ROW_ALL := ["SCT1", "POB1", "TRB1", "SSB1", "PMB1"]

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _wait(cond: Callable, limit: int) -> bool:
	for i in range(limit):
		if cond.call():
			return true
		await physics_frame
	return cond.call()

func _vehicles(id: String) -> Array:
	var out: Array = []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and is_instance_valid(n) and n.get("character_info") != null \
				and String(n.get("character_info").get("display_name")) == id:
			out.append(n)
	return out

func _tilt(b: Node3D) -> float:
	return rad_to_deg(b.global_basis.y.angle_to(Vector3.UP))

func _initialize() -> void:
	var saves: Node = root.get_node("SaveSystem")
	var reg: Node = root.get_node("PlayerRegistry")
	saves.set("autosave_enabled", false)
	var all := OS.get_environment("OW_TEST_BIKES") == "1"
	var row: Array = ROW_ALL if all else ["SCT1"]
	print("=== row expected: %s ===" % " ".join(row))
	var scene := DEBUG_WORLD if OS.get_cmdline_user_args().has("--debug-world") else WORLD
	print("=== scene: %s ===" % scene.get_file())
	change_scene_to_file(scene)
	var up := await _wait(func(): return reg.call("local_player_now") != null and current_scene != null \
		and current_scene.get_node_or_null("HomeBikes") != null, 3600)
	_check("the world has had its bike row", up)
	if not up:
		print("RESULT: FAIL (%d failure(s))" % fails)
		quit(1)
		return
	await _tick(30)
	var start: Node3D = current_scene.get_node("VehicleRoot")
	var g: Node3D = current_scene.get_node_or_null("HomeGarage")

	print("=== 1. the row ===")
	var bikes: Array = []
	for id in ROW_ALL:
		var n := _vehicles(id).size()
		var want := 1 if row.has(id) else 0
		_check("%s at home: %d" % [id, want], n == want, str(n))
		bikes.append_array(_vehicles(id))

	print("=== 2. where ===")
	var set_at: Array = []
	for b in bikes:
		var d: float = b.global_position.distance_to(start.global_position)
		var in_bay: bool = g != null and bool(g.call("contains_now", b.global_position))
		_check("%s beside the starting car, not in the garage bay" % b.get("character_info").get("display_name"),
			d >= 1.5 and d <= 15.0 and not in_bay, "%.2f m from the car, in bay %s" % [d, in_bay])
		set_at.append(b.global_position)
	var closest := INF
	for i in bikes.size():
		for j in range(i + 1, bikes.size()):
			closest = minf(closest, bikes[i].global_position.distance_to(bikes[j].global_position))
	if bikes.size() > 1:
		_check("one bike per slot (closest pair >= 0.9 m)", closest >= 0.9, "%.2f m" % closest)

	print("=== 3. parked ===")
	await _tick(180)
	for i in bikes.size():
		var b: RigidBody3D = bikes[i]
		var moved: float = b.global_position.distance_to(set_at[i])
		_check("%s stays put, at rest, upright on its stand" % b.get("character_info").get("display_name"),
			moved < 0.5 and b.linear_velocity.length() < 0.3 and _tilt(b) < 15.0,
			"moved %.2f m, %.2f m/s, tilt %.1f deg" % [moved, b.linear_velocity.length(), _tilt(b)])

	print("=== 4. the player gets on the home scooter ===")
	var p: Node3D = reg.call("local_player_now")
	var sct: Array = _vehicles("SCT1")
	if sct.is_empty():
		_check("a home scooter to ride", false)
	else:
		var s: RigidBody3D = sct[0]
		p.global_position = s.global_position + s.global_basis.x * 1.2 + Vector3(0, 0.3, 0)
		await _tick(10)
		var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
		current_scene.add_child(helper)
		helper.call("seat_character", s, p)
		await _tick(30)
		_check("the player is seated on it", helper.call("occupant_of", s) == p)

	print("=== 5. spawn ===")
	var console: Node = load("res://src/main/java/com/openworld/debug/DebugConsole.java").new()
	root.add_child(console)
	await _tick(2)
	var before := _vehicles("SSB1").size()
	var bad_before := get_nodes_in_group("characters").size()
	console.call("on_submit", "spawn nope")
	await _tick(5)
	_check("`spawn nope` spawns nothing", get_nodes_in_group("characters").size() == bad_before)
	console.call("on_submit", "spawn ssb1")
	await _tick(60)
	var now := _vehicles("SSB1")
	_check("`spawn ssb1` adds one SSB1", now.size() == before + 1, "%d -> %d" % [before, now.size()])
	if now.size() == before + 1:
		var nearest := INF
		for v in now:
			nearest = minf(nearest, v.global_position.distance_to(p.global_position))
		_check("... about 4 m from the player", nearest > 2.5 and nearest < 6.0, "%.2f m" % nearest)

	print("RESULT: %s" % ("PASS" if fails == 0 else "FAIL (%d failure(s))" % fails))
	quit(0 if fails == 0 else 1)
