extends SceneTree
## RIDING SMOOTHNESS (user, 2026-10-02: "if the player is on it, it chokes on almost every move"): runs at REAL
## time (no --fixed-fps), so physics steps are not evenly spaced in wall time, and measures each physics step's car
## displacement against the speed the timetable gives -- a train on a wall clock jumps when two steps share a frame.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_train_smooth.gd [-- --frame-ms=25]
##   --frame-ms adds that much render-frame work, so physics catches up two or more steps per frame (a busy scene).

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
var tr: Node
var car: Node3D
var last := Vector3.ZERO
var steps := []
var frame_ms := 0

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--frame-ms="):
			frame_ms = int(a.substr(11))
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	tr = root.get_node("TrainSystem")
	for i in 120:
		await physics_frame
	# put set 0 mid-run: find a moment it is at speed and jump the clock there
	var t0 := float(tr.call("clock_now"))
	var t := t0
	while absf((tr.call("set_state_at", 0, t) as PackedFloat64Array)[1]) < 9.0:
		t += 0.5
	tr.set("clock_offset", float(tr.get("clock_offset")) + (t - t0) - 1.0)
	var st: PackedFloat64Array = tr.call("set_state_at", 0, t)
	var player: Node3D = world.get_node("Characters/Player")
	player.global_position = Vector3(st[4] + 15.0, st[5] + 2.0, st[6])
	player.process_mode = Node.PROCESS_MODE_DISABLED
	for i in 30:
		await physics_frame
	if frame_ms > 0:
		process_frame.connect(func(): OS.delay_msec(frame_ms))   # a heavy RENDER frame: physics catches up
	car = tr.call("car_body_now", 0, 1)
	last = car.global_position
	for i in 300:
		await physics_frame
		var p := car.global_position
		var s: PackedFloat64Array = tr.call("set_state_at", 0, float(tr.call("clock_now")))
		steps.append([p.distance_to(last), absf(s[1]) / 60.0])
		last = p
	var worst := 0.0
	var bad := 0
	for e in steps:
		var dev := absf(e[0] - e[1])
		worst = maxf(worst, dev)
		if dev > 0.25 * e[1]:
			bad += 1
	print("probe_train_smooth: %d steps, %d off by more than 25%% of a step, worst %.3f m (a step is ~%.3f m)" % [
		steps.size(), bad, worst, steps[steps.size() / 2][1]])
	print("RESULT %s" % ("PASS" if bad == 0 else "FAIL"))
	quit(0 if bad == 0 else 1)
