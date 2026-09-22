extends SceneTree
## No car is born in front of a fast player (user, 2026-09-22). World.tscn, the real ZoneManager and traffic: the
## player is carried at --speed m/s along a downtown street (its velocity set, so the spawn rules see a mover) and
## every ambient car that appears is logged by where it was born relative to the player.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_traffic_ahead.gd -- [--speed=30] [--control]
## PASS: no car born within 4 s of travel AHEAD (the road and the side streets entering it) or within 60 m in any direction, and traffic still
## spawns at all. --control turns the three player rules off (the old gate) and should fail.
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var args := {}

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _vehicles() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D:
			out.append(n)
	return out

func _run() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	if args.has("control"):
		zm.set("traffic_spawn_min_dist", 0.0)
		zm.set("traffic_spawn_lead_seconds", 0.0)
		zm.set("traffic_spawn_view_dist", 0.0)
	var car := w.get_node_or_null("VehicleRoot")
	if car != null:
		car.queue_free()
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("max_health", 1000000.0)
	p.set_physics_process(false)
	var speed := float(args.get("speed", "30"))
	var a := Vector3(600, 1.4, 250)
	var b := Vector3(600, 1.4, -900)
	var dir := (b - a).normalized()
	p.global_position = a
	for i in range(240):            # let the world stream in round the start, standing still
		await physics_frame
	var known := {}
	for v in _vehicles():
		known[v.get_instance_id()] = true
	var ahead_close := 0
	var near := 0
	var spawned := 0
	var worst := INF
	var t := 0.0
	while t < (a.distance_to(b)) / speed:
		await physics_frame
		t += 1.0 / 60.0
		p.global_position = a + dir * speed * t
		p.velocity = dir * speed
		for v in _vehicles():
			var id: int = v.get_instance_id()
			if known.has(id):
				continue
			known[id] = true
			spawned += 1
			var d: Vector3 = v.global_position - p.global_position
			d.y = 0
			var along := d.dot(dir)
			var lateral := absf(d.cross(dir).y)
			var dist := d.length()
			worst = minf(worst, dist)
			if along > 0 and along < speed * 4.0 and lateral < 40.0 + along * 0.5:
				ahead_close += 1
				print("  born %.0f m ahead, %.0f m off the line" % [along, lateral])
			if dist < 60:
				near += 1
	var fails := 0
	for c in [["traffic still spawns while driving", spawned > 0, "%d cars born" % spawned],
			["no car born within 4 s of travel ahead (road + side streets)", ahead_close == 0, "%d" % ahead_close],
			["no car born within 60 m of the player", near == 0, "%d, nearest %.0f m" % [near, worst]]]:
		if not c[1]:
			fails += 1
		print("  %s  %-50s %s" % ["PASS" if c[1] else "FAIL", c[0], c[2]])
	print("  refused by the player rules: %d" % int(zm.call("traffic_spawns_refused_now")))
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
