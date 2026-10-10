extends SceneTree
## HOW MANY CARS ARE ROUND THE PLAYER, BY DISTRICT (user, 2026-10-10: "barely more than 3 cars even in the busy city /
## suburb, residential barely any, the west centre the most crowded"). World.tscn with the real ZoneManager: the
## player is stood at each site in turn, the streamer is given time to go quiet, then the ambient cars are counted
## every 2 s for --seconds (default 40).
##   stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_census.gd -- \
##       [--seconds=40] [--sites=downtown_core,farm] [--budget=N] [--near-target=N]
## A MEASUREMENT (it prints a table and exits 0); --min-near=<n> turns it into a gate: every site's mean count of
## simulated cars within 200 m must reach n.
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
## name, Godot x, z -- the centre of the region's box in tools/island_buildings.REGIONS (z = -y)
const SITES := [
	["downtown_core", 760.0, -70.0], ["nightlife", 750.0, -370.0], ["akiba", 1080.0, -250.0],
	["residential_north", 685.0, -810.0], ["residential_west", -525.0, -100.0], ["residential", -975.0, 680.0],
	["suburb", 1085.0, 665.0], ["west_centre", -675.0, 540.0], ["industry", -400.0, 820.0],
	["harbour", -285.0, 1300.0], ["farm", 1100.0, -1410.0],
]
var args := {}

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _cars(p: Vector3, r: float) -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D and is_instance_valid(n):
			var d: Vector3 = n.global_position - p
			d.y = 0
			if d.length() <= r:
				out.append(n)
	return out

func _run() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	if args.has("budget"):
		zm.set("traffic_budget", int(args["budget"]))
	if args.has("ring"):
		zm.set("traffic_sim_radius", float(args["ring"]))
	if args.has("idle"):
		zm.set("traffic_idle_recycle_seconds", float(args["idle"]))
	if args.has("recycle"):
		zm.set("traffic_recycle_dist", float(args["recycle"]))
	if args.has("near-radius"):
		zm.set("traffic_near_radius", float(args["near-radius"]))
	if args.has("near-target"):
		zm.set("traffic_near_target", int(args["near-target"]))
	var car := w.get_node_or_null("VehicleRoot")
	if car != null:
		car.queue_free()
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("max_health", 1000000.0)
	p.set_physics_process(false)
	var seconds := float(args.get("seconds", "40"))
	var only: PackedStringArray = str(args.get("sites", "")).split(",", false)
	var min_near := float(args.get("min-near", "-1"))
	var fails := 0
	print("budget %d, near target %d within %.0f m, sim ring %.0f m" % [int(zm.get("traffic_budget")),
		int(zm.get("traffic_near_target")), float(zm.get("traffic_near_radius")), float(zm.get("traffic_sim_radius"))])
	print("%-18s %6s %6s %6s %6s %6s %6s  %s" % ["site", "<60m", "<100m", "<200m", "alive", "far", "refuse", "traffic models at the end"])
	for site in SITES:
		if not only.is_empty() and not only.has(site[0]):
			continue
		p.global_position = Vector3(site[1], 30.0, site[2])
		p.velocity = Vector3.ZERO
		var waited := 0
		while waited < 60 * 90:
			await physics_frame
			waited += 1
			if waited > 240 and int(zm.call("streaming_pending_now")) == 0:
				break
		var refused0: int = zm.call("traffic_spawns_refused_now")
		var s60 := 0.0
		var s100 := 0.0
		var s200 := 0.0
		var alive := 0.0
		var far := 0.0
		var n := 0
		var frames := int(seconds * 60.0)
		for f in range(frames):
			await physics_frame
			if f % 120 == 119:
				# ambient traffic only (ZoneManager's own cars): parked vehicles and police units are not traffic
				s60 += int(zm.call("traffic_near_now", 60.0))
				s100 += int(zm.call("traffic_near_now", 100.0))
				s200 += int(zm.call("traffic_near_now", 200.0))
				alive += int(zm.call("traffic_alive_now"))
				far += int(zm.call("far_traffic_cars_now"))
				n += 1
		var models: String = str(zm.call("traffic_models_now")) if zm.has_method("traffic_models_now") else "?"
		var d: int = maxi(n, 1)
		print("%-18s %6.1f %6.1f %6.1f %6.1f %6.1f %6d  %s  (settled in %.0f s, region '%s')" % [site[0], s60 / d, s100 / d,
			s200 / d, alive / d, far / d, int(zm.call("traffic_spawns_refused_now")) - refused0, models, waited / 60.0,
			str(zm.call("traffic_region_now")) if zm.has_method("traffic_region_now") else "?"])
		if min_near >= 0.0 and s200 / d < min_near:
			fails += 1
	if min_near >= 0.0:
		print("PASS" if fails == 0 else "RESULT FAIL (%d site(s) under %.1f cars within 200 m)" % [fails, min_near])
	quit(1 if fails > 0 else 0)
