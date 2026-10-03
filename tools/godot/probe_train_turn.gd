extends SceneTree
## THE TURN AT A TERMINUS WITH A RIDER (user, 2026-10-02: "when it turns around the player lands somewhere invisible
## instead of the train"). REAL time (no --fixed-fps, no clock jump through the turn), so the turn happens the way it
## does in play: the cars are rebuilt on the other track mid-stop and the rider must end up standing in one.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_train_turn.gd [-- --frame-ms=25] [-- --walk]
##   --walk     the player is walking along the aisle during the turn
##   --control  TrainSystem.pin_riders off (riders are moved once, not held while the new cars settle)

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
var SET := 0
var tr: Node
var player: CharacterBody3D
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _car_with_player() -> Node3D:
	for i in 4:
		var c = tr.call("car_body_now", SET, i)
		if c == null or not is_instance_valid(c):
			continue
		var l: Vector3 = (c as Node3D).global_transform.affine_inverse() * player.global_position
		if absf(l.x) < 1.45 and absf(l.z) < 10.5 and l.y > 0.8 and l.y < 3.4:
			return c
	return null

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var frame_ms := 0
	for a in args:
		if a.begins_with("--frame-ms="):
			frame_ms = int(a.substr(11))
	var scene := "res://src/main/resources/com/openworld/world/World.tscn" if "--world=island" in args else DEBUG
	var set_i := 0
	for a in args:
		if a.begins_with("--set="):
			set_i = int(a.substr(6))
	SET = set_i
	var world: Node = (load(scene) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	player = world.get_node("Characters/Player")
	tr = root.get_node("TrainSystem")
	if "--control" in args:
		tr.set("pin_riders", false)
	if frame_ms > 0:
		process_frame.connect(func(): OS.delay_msec(frame_ms))
	for i in 600:
		await physics_frame
		if int(tr.call("set_count_now")) > 0:
			break
	for i in 60:
		await physics_frame
	# the first half of a terminus stop of set 0: a dwell whose train changes track before it leaves
	var t := float(tr.call("clock_now")) + 2.0
	var prev: PackedFloat64Array = tr.call("set_state_at", SET, t)
	var found := -1.0
	while t < float(tr.call("clock_now")) + 2400.0:
		t += 0.25
		var st: PackedFloat64Array = tr.call("set_state_at", SET, t)
		var want_from := -1
		for a3 in args:
			if a3.begins_with("--from-track="):
				want_from = int(a3.substr(13))
		if prev[2] > 0.5 and st[2] > 0.5 and int(prev[9]) != int(st[9]) and (want_from < 0 or int(prev[9]) == want_from):
			found = t
			break
		prev = st
	_check(found > 0, "found a terminus turn of set 0")
	# 6 s before the turn: stand the player in car 1's aisle
	tr.set("clock_offset", float(tr.get("clock_offset")) + (found - 6.0) - float(tr.call("clock_now")))
	# cars exist only near the camera: bring the player and a camera to the train first
	var at: PackedFloat64Array = tr.call("set_state_at", SET, float(tr.call("clock_now")))
	player.global_position = Vector3(at[4] + 8.0, at[5] + 3.0, at[6])
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.global_position = Vector3(at[4] + 15.0, at[5] + 12.0, at[6])
	cam.current = true
	for i in 300:
		await physics_frame
		if tr.call("car_body_now", SET, 1) != null:
			break
	for i in 30:
		await physics_frame
	var car: Node3D = tr.call("car_body_now", SET, 1)
	var spot := Vector3(0.0, 1.2, 3.0)
	for a in args:
		if a.begins_with("--at="):
			var v := a.substr(5).split(",")
			spot = Vector3(float(v[0]), 1.2, float(v[1]))
	player.global_position = car.global_transform * spot
	for i in 60:
		await physics_frame
	_check(_car_with_player() != null, "the player stands in a car before the turn")
	if "--walk" in args:
		Input.action_press("forward")
	var swaps0 := int(tr.call("swaps_now"))
	var lost := 0
	var worst_y := 9.0
	var frames := 0
	# through the turn and 3 s past it, real time
	while frames < 60 * 30:
		await physics_frame
		frames += 1
		if int(tr.call("swaps_now")) > swaps0:
			var c := _car_with_player()
			if c == null:
				lost += 1
			else:
				worst_y = minf(worst_y, (c.global_transform.affine_inverse() * player.global_position).y)
			if int(tr.call("swaps_now")) > swaps0 and frames > 0 and lost + 1 > 0 and _after_frames(frames):
				break
	Input.action_release("forward")
	_check(int(tr.call("swaps_now")) > swaps0, "the set turned at the terminus (%d swap(s))" % (int(tr.call("swaps_now")) - swaps0))
	print("    player after the turn: %s" % str(player.global_position))
	_check(lost == 0 and worst_y > 0.9, "the player stays standing in a car through the turn (%d frame(s) out of every car, lowest %.2f m over the rail)" % [lost, worst_y])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)

var _since := -1
func _after_frames(f: int) -> bool:
	if _since < 0:
		_since = f
	return f - _since > 180
