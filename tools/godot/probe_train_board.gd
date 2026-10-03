extends SceneTree
## BOARDING A TRAIN, AND WHAT A TRAIN DOES (PLAN.md NEXT item 11, user 2026-10-02): world.TrainSystem opens the
## doors on the platform side at a dwell, a real Player walks in, rides a leg in the car, and walks out at the next
## station; a moving train hits a body on the track; a blast hurts a set; a destroyed set leaves a wreck and comes
## back standing at a platform; the map draws the line and the trains.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_train_board.gd
##   ... -- --control      (TrainSystem.doors_enabled off: the doors stay shut and the walk in is blocked)
##
## The clock is the timetable's: the probe JUMPS it (TrainSystem.clock_offset) to the moment each case wants.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const FACTS := "res://assets/vehicles/trains/EMU1.train.json"

var world: Node
var tr: Node
var player: CharacterBody3D
var helper: Node
var fails := 0
var facts: Dictionary

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _t() -> float:
	return float(tr.call("clock_now"))

func _state(i: int, t: float) -> PackedFloat64Array:
	return tr.call("set_state_at", i, t)

## the first time after `from` set i is in the state `pred` wants (sampled every 0.25 s)
func _find(i: int, from: float, pred: Callable) -> float:
	var period := _state(i, 0.0)[8]
	var t := from
	var prev := _state(i, t)
	while t < from + 2.0 * period:
		t += 0.25
		var st := _state(i, t)
		if pred.call(prev, st):
			return t
		prev = st
	return -1.0

func _jump(to: float) -> void:
	tr.set("clock_offset", float(tr.get("clock_offset")) + to - _t())

func _frames(n: int) -> void:
	for k in n:
		await physics_frame

## car `car`'s door `k`: its doorway centre and its outside point (on the platform), world
func _door_points(car: Node3D, car_idx: int, k: int) -> Array:
	var key := "EMU1_Tc" if car_idx == 0 or car_idx == 3 else "EMU1_M"
	var d: Dictionary = facts["cars"][key]["doors"][k]
	var b: Array = d["box"]
	var flip := car_idx == 3
	var cx := -float(b[0]) if flip else float(b[0])
	var cz := -float(b[2]) if flip else float(b[2])
	var side := signf(cx)
	var xf := car.global_transform
	return [xf * Vector3(cx, 1.15, cz), xf * Vector3(side * 2.6, 1.15, cz), xf * Vector3(0.0, 1.15, cz)]

func _face(target: Vector3) -> void:
	var d := target - player.global_position
	helper.call("set_view", player, rad_to_deg(atan2(-d.x, -d.z)), 0.0)

## walk the player toward `target` (world) holding `forward`, re-aiming every frame
var trace_car = null

func _walk_to(target: Vector3, seconds: float) -> void:
	Input.action_press("forward")
	for k in int(seconds * 60.0):
		_face(target)
		await physics_frame
		if trace_car != null and k % 15 == 0:
			var tc = tr.call("car_body_now", 0, trace_car)
			print("      walk %d: local %s target local %s" % [k, str(_local(tc)), str((tc as Node3D).global_transform.affine_inverse() * target)])
		var d := target - player.global_position
		if Vector2(d.x, d.z).length() < 0.35:
			break
	Input.action_release("forward")
	await _frames(20)

func _local(car) -> Vector3:
	if car == null or not is_instance_valid(car):
		return Vector3(99, 99, 99)
	return car.global_transform.affine_inverse() * player.global_position

## the car of set 0 the player stands in (the cars are rebuilt at a terminus swap), or null
func _car_with_player() -> Node3D:
	for i in 4:
		var c: Node3D = tr.call("car_body_now", 0, i)
		if c == null or not is_instance_valid(c):
			continue
		var l := c.global_transform.affine_inverse() * player.global_position
		if absf(l.x) < 1.45 and absf(l.z) < 10.3 and l.y > 0.6 and l.y < 3.4:
			return c
	return null

## an open door on a car of set 0 with a platform beside it: [car index, door index] or []
func _open_door() -> Array:
	for c in [1, 2]:
		var d: PackedFloat64Array = tr.call("car_doors_now", 0, c)
		for k in d.size() / 2:
			if d[2 * k] > 0.95 and d[2 * k + 1] > 0.5:
				return [c, k]
	return []

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	facts = JSON.parse_string(FileAccess.get_file_as_string(FACTS))
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	helper = load(HELPER).new()
	root.add_child(helper)
	player = world.get_node("Characters/Player")
	tr = root.get_node("TrainSystem")
	tr.set("game_clock", true)
	tr.set("debug_hits", true)
	if control:
		tr.set("doors_enabled", false)
	for i in 60 * 10:
		await physics_frame
		if int(tr.call("set_count_now")) > 0:
			break
	_check(int(tr.call("set_count_now")) > 0, "DebugWorld's line carries a set")
	if int(tr.call("set_count_now")) == 0:
		quit(1)
		return

	# ── 1. a dwell: the doors on the platform side open ─────────────────────
	var t_dwell := _find(0, _t() + 5.0, func(a, b): return a[2] < 0.5 and b[2] > 0.5)
	var st := _state(0, t_dwell + 1.0)
	player.global_position = Vector3(st[4] + 12.0, st[5] + 1.5, st[6])
	await _frames(10)
	_jump(t_dwell - 1.0)
	await _frames(int((1.0 + 0.5 + 1.6) * 60.0))
	var first_stop := int(_state(0, _t())[3])
	var s_first := _state(0, _t())
	var first_at := Vector2(s_first[4], s_first[6])
	var od := _open_door()
	var car1: Node3D = tr.call("car_body_now", 0, 1)
	var doors1: PackedFloat64Array = tr.call("car_doors_now", 0, 1)
	var plat := 0
	for k in doors1.size() / 2:
		plat += int(doors1[2 * k + 1] > 0.5)
	print("probe_train_board: dwell at stop %d, car 1 has %d of %d doors at a platform" % [first_stop, plat, doors1.size() / 2])
	if not control:
		var bt := str(tr.call("board_text_now"))
		print("  board: %s" % bt.replace("\n", " | "))
		_check(int(tr.call("board_count_now")) > 0 and bt.contains("先発") and bt.contains("行"),
				"the platform has a departure board (%d built) listing the next trains" % int(tr.call("board_count_now")))
		var sc := str(tr.call("screen_text_now", 0, 1))
		print("  door screen at the stop: %s" % sc.replace("\n", " | "))
		_check(sc.contains("行"), "the screen over the doors names this station and where the train goes")
	if control:
		_check(od.is_empty(), "control: no door opens")
	else:
		_check(not od.is_empty() and plat > 0 and plat < doors1.size() / 2,
				"the doors on the PLATFORM side open, and only those (%d of %d)" % [plat, doors1.size() / 2])
	# ── 2. the player walks in through an open door (or, the control, into a shut one) ──
	var c_idx := 1
	var k_idx := 0
	if not od.is_empty():
		c_idx = od[0]
		k_idx = od[1]
	else:
		for k in doors1.size() / 2:
			if doors1[2 * k + 1] > 0.5:
				k_idx = k
	var car: Node3D = tr.call("car_body_now", 0, c_idx)
	var pts := _door_points(car, c_idx, k_idx)
	player.global_position = pts[1] + Vector3(0, 0.05, 0)
	await _frames(15)
	await _walk_to(pts[2], 4.0)
	var loc := _local(car)
	print("  player in car %d's frame after the walk: (%.2f, %.2f, %.2f)" % [c_idx, loc.x, loc.y, loc.z])
	if control:
		_check(absf(loc.x) > 1.4, "control: a shut door blocks the walk in (|x| %.2f)" % absf(loc.x))
		_finish()
		return
	_check(absf(loc.x) < 1.0 and absf(loc.y - 1.13) < 0.3, "the player walked in through the open door and stands on the car's floor")
	# ── 3. the doors shut and the train leaves: the player rides it, all the way to the next station ──
	var t_go := _find(0, _t(), func(a, b): return a[2] > 0.5 and b[2] < 0.5)
	_jump(t_go - 4.5)
	await _frames(60)
	var start := player.global_position
	var swaps0 := int(tr.call("swaps_now"))
	var worst := 0.0
	var moved := 0.0
	var top := 0.0
	var od2 := []
	var ride_screen := ""
	for f in 60 * 240:
		await physics_frame
		car = _car_with_player()
		var l := _local(car)
		worst = maxf(worst, maxf(absf(l.x) - 1.3, absf(l.y - 1.13) - 0.3))
		moved = maxf(moved, player.global_position.distance_to(start))
		var s3 := _state(0, _t())
		top = maxf(top, absf(s3[1]))
		if f == 60 * 4:
			ride_screen = str(tr.call("screen_text_now", 0, c_idx))
		# (at a terminus, after the mid-stop swap to the other track: until_depart is then at most half the stop)
		if s3[2] > 0.5 and Vector2(s3[4], s3[6]).distance_to(first_at) > 60.0 and s3[10] < 21.0:
			od2 = _open_door()
			if not od2.is_empty():
				break
	print("  track swaps while aboard: %d" % (int(tr.call("swaps_now")) - swaps0))
	print("  door screen while running: %s" % ride_screen.replace("\n", " | "))
	_check(ride_screen.begins_with("次は") and ride_screen.contains(":"), "running, the screen shows the next station and its arrival time")
	print("  rode %.0f m at up to %.1f m/s, worst excursion from the car's floor %.2f m" % [moved, top, worst])
	_check(moved > 60.0 and worst <= 0.0, "the player rides the moving car to the next station (%.0f m) without leaving its floor" % moved)
	# ── 4. the next station: the player walks out ────────────────────────────
	var st2 := _state(0, _t())
	print("  at the end of the ride: %s, od2 %s, %.0f m from the boarding station" % [str(st2), str(od2), Vector2(st2[4], st2[6]).distance_to(first_at)])
	od = od2
	_check(st2[2] > 0.5 and Vector2(st2[4], st2[6]).distance_to(first_at) > 60.0 and not od.is_empty(),
			"at the next station (stop %d) a door opens again" % int(st2[3]))
	# the open platform-side door nearest the player, in the car they stand in
	var mine := _car_with_player()
	var best := 1e9
	for ci in [0, 1, 2, 3]:
		var cb: Node3D = tr.call("car_body_now", 0, ci)
		var dd: PackedFloat64Array = tr.call("car_doors_now", 0, ci)
		if cb == null or cb != mine:
			continue
		for kk in dd.size() / 2:
			if dd[2 * kk] > 0.95 and dd[2 * kk + 1] > 0.5:
				var pp := _door_points(cb, ci, kk)
				var dist := player.global_position.distance_to(pp[2])
				if dist < best:
					best = dist
					od = [ci, kk]
	print("  walking out through car %s door %s (%.1f m away)" % [str(od[0]) if od else "-", str(od[1]) if od else "-", best])
	if not od.is_empty():
		car = tr.call("car_body_now", 0, od[0])
		pts = _door_points(car, od[0], od[1])
		# walk across the car to the doorway, then out onto the platform
		trace_car = od[0]
		await _walk_to(pts[2], 4.0)
		print("    at the aisle: local %s" % str(_local(tr.call("car_body_now", 0, od[0]))))
		await _walk_to(pts[1], 4.0)
		car = tr.call("car_body_now", 0, od[0])
		loc = _local(car)
		_check(absf(loc.x) > 1.7 and absf(loc.y - 1.13) < 0.35, "the player walked out onto the platform (|x| %.2f, y %.2f)" % [absf(loc.x), loc.y])
	_finish()

func _finish() -> void:
	if "--control" in OS.get_cmdline_user_args():
		print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
		quit(1 if fails else 0)
		return
	await _hits()

## ── 5. hits, a blast, destroy and respawn, the map ──────────────────────────
func _hits() -> void:
	player.global_position += Vector3(0, 0, 0)
	# a fast run: a body stood on the track where the set's centre will be in 8 s (well ahead of its nose)
	var t_fast := _find(0, _t(), func(a, b): return absf(b[1]) > 8.0)
	_jump(t_fast)
	var ahead := _state(0, _t() + 8.0)
	player.global_position = Vector3(ahead[4] + 18.0, ahead[5] + 2.0, ahead[6])
	var ai: Node3D = (load(AI) as PackedScene).instantiate()
	world.add_child(ai)
	ai.global_position = Vector3(ahead[4], ahead[5] + 0.05, ahead[6])
	# it stands still ON the track centre (its own brain would walk it off)
	ai.disable_mode = CollisionObject3D.DISABLE_MODE_KEEP_ACTIVE
	ai.process_mode = Node.PROCESS_MODE_DISABLED
	var hits0 := int(tr.call("hits_now"))
	var health: Node = ai.get_node("Health")
	for k in 16:
		await _frames(30)
		var c0: Node3D = tr.call("car_body_now", 0, 0)
		print("    t+%.1f ai (%.1f, %.1f, %.1f) car0 %s v %.1f hits %d" % [k * 0.5, ai.global_position.x, ai.global_position.y,
				ai.global_position.z, str(c0.global_position) if c0 else "-", _state(0, _t())[1], tr.call("hits_now")])
	var hp := float(health.call("health_now"))
	var out := true
	var car0: Node3D = tr.call("car_body_now", 0, 0)
	_check(int(tr.call("hits_now")) > hits0 and hp < 100.0,
			"a train at %.0f m/s hits a body on the track (health %.0f)" % [absf(_state(0, _t() - 4.0)[1]), hp])
	# a blast at a car hurts the set
	var hp0 := float(tr.call("set_health_now", 0))
	if car0 != null:
		tr.call("blast_now", car0.global_position + Vector3(0, 2, 0), 8.0, 300.0)
	await _frames(3)
	var hp1 := float(tr.call("set_health_now", 0))
	_check(hp1 < hp0 - 100.0, "a blast at a car hurts the set (%.0f -> %.0f)" % [hp0, hp1])
	# destroyed: a wreck stays, the set is out of service, the map loses it; it comes back at a platform
	var trains0 := int(tr.call("map_train_count_now"))
	tr.call("destroy_set_now", 0)
	await _frames(5)
	var back := float(tr.call("set_back_at_now", 0))
	_check(bool(tr.call("set_out_of_service_now", 0)) and int(tr.call("wrecks_now")) > 0
			and int(tr.call("map_train_count_now")) == trains0 - 1,
			"a destroyed set leaves a wreck and is out of service (back in %.0f s)" % (back - _t()))
	_jump(back + 1.0)
	await _frames(30)
	var st := _state(0, _t())
	_check(not bool(tr.call("set_out_of_service_now", 0)) and st[2] > 0.5 and int(tr.call("wrecks_now")) == 0
			and float(tr.call("set_health_now", 0)) >= 2999.0,
			"it comes back standing at a platform (stop %d), whole, and the wreck is gone" % int(st[3]))
	var lay = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/debug_world_layout.json"))
	var sp: Array = lay["stations"][0]["pos"]
	var panel := str(tr.call("station_panel_now", Vector3(float(sp[0]), 0, float(sp[2]))))
	print("  map panel: %s" % panel.replace("\n", " | "))
	_check(panel.split("\n").size() >= 2 and panel.contains("行") and panel.contains(":"),
			"a station's map panel lists its next departures each way")
	_check(int(tr.call("map_line_count_now")) >= 1 and int(tr.call("map_train_count_now")) >= 1,
			"the map has the line (%d) and its train(s) (%d)" % [tr.call("map_line_count_now"), tr.call("map_train_count_now")])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
