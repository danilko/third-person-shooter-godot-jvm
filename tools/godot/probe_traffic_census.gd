extends SceneTree
## HOW MANY CARS ARE ROUND THE PLAYER, BY DISTRICT (user, 2026-10-10: "barely more than 3 cars even in the busy city /
## suburb, residential barely any, the west centre the most crowded"). World.tscn with the real ZoneManager: the
## player is stood at each site in turn, the streamer is given time to go quiet, then the ambient cars are counted
## every 2 s for --seconds (default 40).
##   stdbuf -oL <godot> --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_census.gd -- \
##       [--seconds=40] [--sites=downtown_core,farm] [--budget=N] [--near-target=N] [--along-lanes | --along-share=0.5] [--on-road]
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

## The point of the through lane nearest `p` in plan (a street the player would stand on), or `p` when none
## within 300 m. --on-road: a box centre is often the inside of a block, where no car can ever be within 60 m.
func _on_road(p: Vector3) -> Vector3:
	var best := p
	var best_d := 300.0
	for n in root.find_children("*", "Node3D", true, false):
		var sc: Script = n.get_script()
		if sc == null or not str(sc.resource_path).ends_with("PathLaneRoute.java") or str(n.name).begins_with("c"):
			continue
		var path: Path3D = n.get_node_or_null("Path3D")
		if path == null or path.curve == null or path.curve.get_baked_length() < 60.0:
			continue
		var off := path.curve.get_closest_offset(path.to_local(p))
		if not is_finite(off):
			continue
		var at := path.to_global(path.curve.sample_baked(off))
		var d := Vector2(at.x - p.x, at.z - p.z).length()
		if d < best_d:
			best_d = d
			best = Vector3(at.x, p.y, at.z)
	return best

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
	# --fixed-fps game time is not wall time: the lights keep game time too (on the wall clock a 40 s sample sees a
	# few seconds of one phase, and a car at a red reads as standing for ever)
	var ts := root.find_child("TrafficSignals", true, false)
	if ts != null:
		ts.set("game_clock", true)
	if args.has("no-lazy-drivers"):
		zm.set("traffic_lazy_drivers", false)
	if args.has("no-cross-gap"):
		zm.set("traffic_gap_across_lanes", false)   # the control: an on-rails car joins a queue it cannot see
	if args.has("no-cap"):
		zm.set("traffic_speed_cap", false)   # V6's control: the brain fades its own throttle, the car has no limit
	if args.has("along-share"):
		zm.set("traffic_spawn_along_share", float(args["along-share"]))
	if args.has("along-lanes"):
		zm.set("traffic_spawn_along_lanes", true)
	var car := w.get_node_or_null("VehicleRoot")
	if car != null:
		car.queue_free()
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("max_health", 1000000.0)
	p.get_node("Health").set("invulnerable", true)
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
		if not is_instance_valid(p):
			# the respawn system replaced the body (something killed it between sites): take the new one
			p = current_scene.get_node("Characters/Player") as CharacterBody3D
			p.get_node("Health").set("invulnerable", true)
			p.set_physics_process(false)
			print("    (the player body was replaced before %s: taken again)" % site[0])
		p.global_position = Vector3(site[1], 30.0, site[2])
		p.velocity = Vector3.ZERO
		var waited := 0
		while waited < 60 * 90:
			await physics_frame
			waited += 1
			if waited > 240 and int(zm.call("streaming_pending_now")) == 0:
				break
		var moved := 0.0
		if args.has("on-road"):
			var q := _on_road(p.global_position)
			moved = (q - p.global_position).length()
			p.global_position = q
			for i in 600:
				await physics_frame
		var refused0: int = zm.call("traffic_spawns_refused_now")
		var s60 := 0.0
		var s100 := 0.0
		var s200 := 0.0
		var alive := 0.0
		var far := 0.0
		var mov := 0.0
		var why := {}
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
				# what the cars are DOING (an on-rails body's velocity reads zero: the brain is asked)
				mov += int(zm.call("traffic_moving_now", 200.0))
				for kv in str(zm.call("traffic_state_now", 200.0)).split(" "):
					var e := kv.split("=")
					if e[0] != "n" and e[0] != "moving":
						why[e[0]] = int(why.get(e[0], 0)) + int(e[1])
				n += 1
		var models: String = str(zm.call("traffic_models_now")) if zm.has_method("traffic_models_now") else "?"
		var d: int = maxi(n, 1)
		print("%-18s %6.1f %6.1f %6.1f %6.1f %6.1f %6d  %s  (settled in %.0f s, region '%s')" % [site[0], s60 / d, s100 / d,
			s200 / d, alive / d, far / d, int(zm.call("traffic_spawns_refused_now")) - refused0, models, waited / 60.0,
			str(zm.call("traffic_region_now")) if zm.has_method("traffic_region_now") else "?"])
		print("    drivers: %s" % str(zm.call("traffic_drivers_now")))
		print("    safety: %s" % str(zm.call("traffic_safety_now")))
		if args.has("lanes"):
			# where each ambient car is at the end: its lane, its distance and height against the player
			for c in _cars(p.global_position, 400.0):
				for ch in c.get_children():
					var sc: Script = ch.get_script()
					if sc != null and str(sc.resource_path).ends_with("VehicleAIController.java"):
						print("      %-44s %5.0f m  y %6.1f  %s" % [ch.call("lane_now"),
							Vector2(c.global_position.x - p.global_position.x, c.global_position.z - p.global_position.z).length(),
							c.global_position.y, "rails" if ch.call("dummy_now") else "real"])
		var parts := []
		for k in why:
			parts.append("%s %.1f" % [k, float(why[k]) / d])
		print("    of the %.1f within 200 m: moving %.1f; %s%s" % [s200 / d, mov / d, ", ".join(parts),
			"  (stood on a street %.0f m from the site)" % moved if args.has("on-road") else ""])
		if min_near >= 0.0 and s200 / d < min_near:
			fails += 1
	if min_near >= 0.0:
		print("PASS" if fails == 0 else "RESULT FAIL (%d site(s) under %.1f cars within 200 m)" % [fails, min_near])
	quit(1 if fails > 0 else 0)
