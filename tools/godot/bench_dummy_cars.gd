extends SceneTree
## WHAT DOES THE DUMMY CAR TIER BUY (PLAN.md 1g e / 2d): physics-process time per tick on World.tscn with the
## traffic filled, the dummy tier ON (ZoneManager.dummy_out_dist 90) and OFF (0), alternated.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/bench_dummy_cars.gd [-- --at=x,z] [--secs=6] [--rounds=3]

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"

var args := {}


func _cars() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and n.get_node_or_null("DamageModel") != null:
			out.append(n)
	return out


func _measure(secs: float) -> float:
	var sum := 0.0
	var n := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < secs * 1000.0:
		await physics_frame
		sum += Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
		n += 1
	return sum / max(1, n)


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "1"
	var at := Vector2(500, -100)
	if args.has("at"):
		var p: PackedStringArray = str(args["at"]).split(",")
		at = Vector2(float(p[0]), float(p[1]))
	var secs: float = float(args.get("secs", "6"))
	var rounds: int = int(args.get("rounds", "3"))
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	for k in ["PedZones"]:
		var h := w.get_node_or_null(k)
		if h != null:
			w.remove_child(h)
			h.free()
	root.add_child(w)
	current_scene = w
	var zm := root.get_node("ZoneManager")
	zm.set("debug_log", false)
	var player: Node3D = w.get_node("Characters/Player")
	player.set_physics_process(false)
	player.global_position = Vector3(at.x, 7.0, at.y)
	for i in 60 * 40:
		await physics_frame
		if i > 600 and _cars().size() >= int(zm.get("traffic_budget")) and int(zm.call("streaming_pending_now")) == 0:
			break
	var on_sum := 0.0
	var off_sum := 0.0
	for r in rounds:
		for on in [true, false]:
			zm.set("dummy_out_dist", 90.0 if on else 0.0)
			for i in 90:
				await physics_frame
			var ms := await _measure(secs)
			print("  round %d dummy %s: %.2f ms/tick, %d cars, %d dummies" % [r, "ON " if on else "OFF", ms,
				_cars().size(), int(zm.call("dummies_now"))])
			if on:
				on_sum += ms
			else:
				off_sum += ms
	print("RESULT dummy tier ON %.2f ms/tick, OFF %.2f ms/tick (saves %.2f)" % [on_sum / rounds, off_sum / rounds,
		(off_sum - on_sum) / rounds])
	quit(0)
