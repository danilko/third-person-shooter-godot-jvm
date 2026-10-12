extends SceneTree
## ENGINE SOUND, AND WHAT IT COSTS (PLAN.md P2b / S9 Q0 b; carrier.vehicle.EngineAudio). World.tscn with the real
## ZoneManager, the player stood on a downtown street among the ambient traffic; every 0.5 s for --seconds the
## playing engine players are counted, per car and in all.
##   stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_engine_audio.gd -- [--seconds=40]
## The cost rule is the gate: a voice only for a running car within 45 m of the camera (kept out to 55 m), at most 6
## cars at once, at most 2 players a car.
##   CONTROL        OW_ENGINE_AUDIO=all <the same command>      the rule off: must FAIL the count and the distance
##   OFF            OW_ENGINE_AUDIO=0 <the same command> -- --expect=off      nothing may play at all
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const SITE := Vector3(760.0, 30.0, -70.0)   # downtown_core (probe_traffic_census)
const HEAR := 45.0
const RELEASE := 55.0
const MAX_CARS := 6
var args := {}
var fails := 0
var checks := 0


func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-78s %s" % ["PASS" if ok else "FAIL", label, detail])


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()


func _cars() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and is_instance_valid(n) and n.has_method("engine_voices_now"):
			out.append(n)
	return out


func _on_road(p: Vector3) -> Vector3:
	var zm := root.get_node("/root/ZoneManager")
	var best := p
	var best_d := 300.0
	for n in _cars():
		var d: Vector3 = n.global_position - p
		d.y = 0
		if d.length() < best_d:
			best_d = d.length()
			best = n.global_position
	return best


func _run() -> void:
	var off := str(args.get("expect", "")) == "off"
	print("=== 1. the files ===")
	for band in ["idle", "low", "mid", "high"]:
		var st := load("res://assets/audio/engine/%s.wav" % band) as AudioStreamWAV
		_check("engine/%s loads and LOOPS (the smpl chunk)" % band, st != null and st.loop_mode == AudioStreamWAV.LOOP_FORWARD
			and st.loop_end > 0, "%.3f s" % st.get_length() if st else "missing")
	var start := load("res://assets/audio/engine/start.wav") as AudioStreamWAV
	_check("engine/start loads and does NOT loop", start != null and start.loop_mode == AudioStreamWAV.LOOP_DISABLED)

	print("=== 2. island traffic ===")
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	var ts := root.find_child("TrafficSignals", true, false)
	if ts != null:
		ts.set("game_clock", true)
	var own := w.get_node_or_null("VehicleRoot")
	if own != null:
		own.queue_free()
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("max_health", 1000000.0)
	p.get_node("Health").set("invulnerable", true)
	p.set_physics_process(false)
	p.global_position = SITE
	p.velocity = Vector3.ZERO
	var waited := 0
	while waited < 60 * 90:
		await physics_frame
		waited += 1
		if waited > 240 and int(zm.call("streaming_pending_now")) == 0:
			break
	# stand where the cars are: beside the nearest one's lane
	for i in 600:
		await physics_frame
	var road := _on_road(p.global_position)
	p.global_position = road + Vector3(4.0, 1.0, 0.0)
	for i in 300:
		await physics_frame

	var seconds := float(args.get("seconds", "40"))
	var max_cars := 0
	var max_players := 0
	var max_per_car := 0
	var far_voiced := 0.0
	var samples := 0
	var silent_now := {}
	var silent_before := {}
	var silent_before_cars := 0
	var refused := 0
	var near_running := 0
	var max_rpm := 0.0
	var bad_pitch := 0
	var counter_wrong := 0
	var all_cars := 0
	for f in range(int(seconds * 60.0)):
		await physics_frame
		if f % 30 != 29:
			continue
		var cam := root.get_camera_3d()
		var eye: Vector3 = cam.global_position if cam != null else p.global_position
		var cars := 0
		var players := 0
		var list := _cars()
		all_cars = max(all_cars, list.size())
		for c in list:
			var v := 0
			for ch in c.get_children():
				if ch is AudioStreamPlayer3D and String(ch.name).begins_with("Engine") and ch.playing:
					v += 1
					if ch.pitch_scale < 0.649 or ch.pitch_scale > 1.601:
						bad_pitch += 1
			var d: float = (c.global_position - eye).length()
			if v > 0:
				cars += 1
				players += v
				max_per_car = max(max_per_car, v)
				far_voiced = max(far_voiced, d)
				max_rpm = max(max_rpm, float(c.call("engine_rpm_now")))
			if v != int(c.call("engine_voices_now")):
				counter_wrong += 1
			if d < HEAR - 5.0 and bool(c.call("engine_running_now")):
				near_running += 1
				if v == 0:
					silent_now[c.get_instance_id()] = true
		samples += 1
		# a running car in earshot with no voice, twice running (one sample may fall inside its 0.2 s ask), while
		# there was a voice to give
		if cars < MAX_CARS and silent_before_cars < MAX_CARS:
			for id in silent_now:
				if silent_before.has(id):
					refused += 1
		silent_before = silent_now
		silent_before_cars = cars
		silent_now = {}
		max_cars = max(max_cars, cars)
		max_players = max(max_players, players)
	print("  %d samples, up to %d vehicles in the world; voiced cars at most %d, players at most %d, furthest voiced car %.1f m, top engine speed %.2f"
		% [samples, all_cars, max_cars, max_players, far_voiced, max_rpm])
	if off:
		_check("OFF: no engine player ever plays", max_players == 0, "%d" % max_players)
	else:
		_check("there was traffic to hear (a RUNNING car within 40 m in some sample)", near_running > 0, "%d car-samples" % near_running)
		_check("a running car within 40 m has a voice whenever one is free", refused == 0 and max_cars > 0, "%d left silent" % refused)
		_check("never more than %d cars voiced" % MAX_CARS, max_cars <= MAX_CARS, "%d" % max_cars)
		_check("never more than 2 players a car, %d in all" % (MAX_CARS * 2), max_per_car <= 2 and max_players <= MAX_CARS * 2,
			"%d a car, %d in all" % [max_per_car, max_players])
		_check("no voice beyond %d m (+5 m: a car asks 5 times a second)" % int(RELEASE), far_voiced <= RELEASE + 5.0, "%.1f m" % far_voiced)
		_check("the engine speed follows the road (some car above 0.3)", max_rpm > 0.3, "%.2f" % max_rpm)
		_check("every playing loop is pitched inside 0.65-1.6", bad_pitch == 0, "%d outside" % bad_pitch)
	_check("Vehicle.engine_voices_now agrees with the players counted", counter_wrong == 0, "%d disagreements" % counter_wrong)
	_check("every case ran", checks >= (7 if off else 13), "%d checks" % checks)
	print("RESULT %s (%d checks, %d failures)" % ["PASS" if fails == 0 else "FAIL", checks, fails])
	quit(1 if fails > 0 else 0)
