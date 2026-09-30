extends SceneTree
## RUNNING TRAINS (PLAN.md "NEXT" piece 5, user 2026-09-29): world.TrainSystem runs EMU1 sets on the rail build's
## tracks on a clock-derived timetable.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_trains.gd -- [--world=island]
##   ... -- --control      (TrainSystem.enabled off: no trains, no closed crossing)
##
##   1. the tracks load from the rail lanekits and every line has a set (sets on distinct tracks, so two sets on one
##      line never meet);
##   2. over a whole cycle each set stops ONLY at its stops, each stop inside a station (within 30 m of a station's
##      centre), and its speed never exceeds 25 m/s nor jumps;
##   3. a set never occupies a level crossing that is open (every overlap of a set and a crossing reads CLOSED);
##   4. a crossing opens again once the set is well past it;
##   5. a camera parked beside a set brings its four cars into the world, on the track.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var world: Node
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _stations(island: bool) -> Array:
	var out := []
	if island:
		var d = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/buildings/IslandRailReserve.json"))
		for b in d["boxes"]:
			if str(b["id"]).begins_with("station:"):
				out.append(Vector2(float(b["x"]), -float(b["y"])))
	else:
		var d = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/debug_world_layout.json"))
		for s in d["stations"]:
			out.append(Vector2(float(s["pos"][0]), float(s["pos"][2])))
	return out

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var island := "--world=island" in args
	world = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node_or_null("Characters/Player")
	if player != null:
		player.process_mode = Node.PROCESS_MODE_DISABLED
	var tr: Node = root.get_node("TrainSystem")
	tr.set("game_clock", true)
	if control:
		tr.set("enabled", false)
	for i in 60 * 10:
		await physics_frame
		if int(tr.call("set_count_now")) > 0:
			break
	var n_sets := int(tr.call("set_count_now"))
	print("probe_trains: %d track(s), %d set(s), %d crossing lane(s), %d signal unit(s)" % [
		tr.call("track_count_now"), n_sets, tr.call("crossing_count_now"), tr.call("unit_count_now")])
	_check(int(tr.call("track_count_now")) > 0 and n_sets > 0, "the tracks load and the lines carry sets")
	var seen_tracks := {}
	for i in n_sets:
		seen_tracks[str(tr.call("set_track_now", i))] = true
	_check(seen_tracks.size() == n_sets, "every set runs on its own track (%d sets, %d tracks)" % [n_sets, seen_tracks.size()])
	# 2. stops and speeds over a whole cycle (the timetable is a pure function of time: sample it)
	var sts := _stations(island)
	var bad_stop := []
	var fast := 0.0
	var jumps := 0
	var closed_bad := []
	var reopen_ok := true
	var n_cross := int(tr.call("crossing_count_now"))
	for i in n_sets:
		var st0: PackedFloat64Array = tr.call("set_state_at", i, 0.0)
		var period := st0[8]
		var prev := st0
		var t := 0.0
		while t < period:
			var st: PackedFloat64Array = tr.call("set_state_at", i, t)
			fast = maxf(fast, absf(st[1]))
			if absf(st[0] - prev[0]) > 25.0 * 0.5 + 0.01:
				jumps += 1
			if st[2] > 0.5:
				var p := Vector2(st[4], st[6])
				var near := 1e9
				for s in sts:
					near = minf(near, p.distance_to(s))
				if near > 30.0 and bad_stop.size() < 6:
					bad_stop.append("set %d at (%.0f, %.0f) %.0f m from a station" % [i, p.x, p.y, near])
			prev = st
			t += 0.5
	_check(bad_stop.is_empty(), "every set dwells only at a station's platform%s" % (": " + ", ".join(bad_stop) if bad_stop else ""))
	_check(fast <= 25.0 + 1e-3 and jumps == 0, "speed never exceeds 25 m/s (top %.1f) and the position never jumps (%d)" % [fast, jumps])
	# 3. / 4. crossings: overlap => closed; well past => open
	var overlaps := 0
	for k in n_cross:
		var c: PackedFloat64Array = tr.call("crossing_now", k)
		var si := int(c[0])
		if si < 0:
			continue
		var period := (tr.call("set_state_at", si, 0.0) as PackedFloat64Array)[8]
		var t := 0.0
		while t < period:
			var st: PackedFloat64Array = tr.call("set_state_at", si, t)
			var gap := absf(c[1] - st[0])
			var closed := bool(tr.call("crossing_closed_at", k, t))
			if gap <= 40.0:
				overlaps += 1
				if not closed and closed_bad.size() < 6:
					closed_bad.append("crossing %d open with set %d on it at t %.0f" % [k, si, t])
			if gap > 40.0 + 150.0 + 60.0 and closed and st[2] < 0.5:
				reopen_ok = false
			t += 1.0
	_check(n_cross == 0 or (closed_bad.is_empty() and overlaps > 0),
			"a set never stands on an open crossing (%d overlap samples)%s" % [overlaps, (": " + ", ".join(closed_bad)) if closed_bad else ""])
	_check(reopen_ok, "a crossing opens again once the set is well past it")
	# 5. cars near the camera
	if n_sets > 0 and not control:
		var cam := Camera3D.new()
		world.add_child(cam)
		var now_t := Engine.get_physics_frames() / float(Engine.physics_ticks_per_second)
		var st: PackedFloat64Array = tr.call("set_state_at", 0, now_t)
		cam.global_position = Vector3(st[4] + 30.0, st[5] + 20.0, st[6])
		cam.current = true
		for i in 30:
			await physics_frame
		var cars := int(tr.call("cars_now"))
		var on_track := true
		for n in tr.get_children():
			if n is AnimatableBody3D and str(n.name).begins_with("Train_0_"):
				var p: Vector3 = (n as Node3D).global_position
				if p.distance_to(Vector3(st[4], st[5], st[6])) > 120.0:
					on_track = false
		_check(cars >= 4 and on_track, "a camera beside a set brings its cars in (%d car(s)), on the track" % cars)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
