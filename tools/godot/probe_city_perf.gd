extends SceneTree
## PLAN.md 3.6: is a zone-streamed city cheap enough? Runs World.tscn WITH A DISPLAY (the real renderer; headless
## has no draw cost to measure), vsync off, and flies a camera through downtown at street level and over it, with
## the player carried along so the ZoneManager streams around it. Reports per leg: frame time (p50 / p95 / p99 /
## worst), GPU time, draw calls, objects and primitives in view, and the frames in which a building cell finished
## entering the tree.
##
##   godot --path . --script tools/godot/probe_city_perf.gd [-- --no-buildings] [--shots=<dir>] [--budget=16.7]
##
## `--crowd` adds the crowd leg (at one downtown street view, pedestrians and traffic streamed by the real ZoneManager:
## sidewalk walkers vs navmesh wanderers vs an armed fight vs traffic, each with its own counts and costs);
## `--scenarios=a,b` picks some; `--strip-sequence` turns per-character nodes off one at a time (cumulative); `--no-rays` / `--no-springarm` / `--no-nameplates` / `--no-hitboxes` / `--no-modifiers` / `--no-anim` strip those from every character (cost split). `--no-lod` sets the viewport's mesh_lod_threshold to 0 (every mesh at full detail): the control for the LOD
## chain. `--shadow-distance=M` overrides the sun's directional_shadow_max_distance. `--legs=a,b` runs only those legs. `--no-buildings` removes the BuildingZones markers before the world enters the tree: the same flight over roads
## alone, the control that says what the buildings cost. `--shots=<dir>` saves a picture at the start of each leg.
## Exits 1 when the street-level p95 is over `--budget` ms (default 16.7, i.e. 60 fps).

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"

var w: Node
var cam: Camera3D
var player: Node3D
var vp_rid: RID
var args := {}

func _arg(k: String, d = null):
	return args.get(k, d)

func _collect(n: Node, script_end: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(script_end):
		out.append(n)
	for c in n.get_children():
		_collect(c, script_end, out)

func _building_cells_loaded() -> int:
	var h := w.get_node_or_null("BuildingZones")
	if h == null:
		return 0
	var n := 0
	for m in h.get_children():
		for c in m.get_children():
			if str(c.scene_file_path).get_file().begins_with("Bld_island_"):
				n += 1
	return n

func _buildings_in_tree() -> int:
	var h := w.get_node_or_null("BuildingZones")
	if h == null:
		return 0
	var n := 0
	for m in h.get_children():
		for c in m.get_children():
			if str(c.scene_file_path).get_file().begins_with("Bld_island_"):
				n += c.get_child_count()
	return n

func _place(pos: Vector3, look: Vector3) -> void:
	cam.global_position = pos
	cam.look_at(look, Vector3.UP)
	player.global_position = Vector3(pos.x, 2.0, pos.z)

func _settle(seconds: float) -> void:
	# streaming starts on the ZoneManager's 0.5 s tick and parses on worker threads: wait at least 4 s, then until
	# the loaded set has not changed for 3 s
	var last := -1
	var still := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < seconds * 1000.0:
		await process_frame
		var n := _building_cells_loaded() * 1000 + _road_pieces_loaded()
		if n == last:
			still += 1
		else:
			still = 0
			last = n
		if Time.get_ticks_msec() - t0 > 4000 and still > 180:
			return

func _road_pieces_loaded() -> int:
	var h := w.get_node_or_null("RoadZones")
	var n := 0
	if h != null:
		for m in h.get_children():
			n += m.get_child_count()
	return n

func _info(kind: int) -> int:
	return RenderingServer.viewport_get_render_info(vp_rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, kind)

func _leg(label: String, path: Array, speed: float, look_ahead: bool, look_at_pt := Vector3.ZERO) -> Dictionary:
	if _arg("legs") != null and not (label in str(_arg("legs")).split(",")):
		return {}
	# path: [Vector3] waypoints at camera height; the camera moves `speed` m/s by REAL frame time
	_place(path[0], path[1] if look_ahead else look_at_pt)
	await _settle(40.0)
	var shots = _arg("shots")
	if shots != null:
		await process_frame
		await process_frame
		root.get_texture().get_image().save_png("%s/%s.png" % [shots, label])
	var ft := []
	var gpu := []
	var dc := []
	var objs := []
	var prims := []
	var sdc := []
	var sprims := []
	var enter_ft := []
	var seg := 0
	var along := 0.0
	var prev_cells := _building_cells_loaded()
	var t_prev := Time.get_ticks_usec()
	while seg < path.size() - 1:
		await process_frame
		var t := Time.get_ticks_usec()
		var dt := (t - t_prev) / 1000.0
		t_prev = t
		ft.append(dt)
		gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(vp_rid))
		dc.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		objs.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_OBJECTS_IN_FRAME))
		prims.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME))
		sdc.append(RenderingServer.viewport_get_render_info(vp_rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_SHADOW,
				RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		sprims.append(RenderingServer.viewport_get_render_info(vp_rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_SHADOW,
				RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME))
		var cells := _building_cells_loaded()
		if cells > prev_cells:
			enter_ft.append(dt)
		prev_cells = cells
		along += speed * minf(dt, 50.0) / 1000.0
		var a: Vector3 = path[seg]
		var b: Vector3 = path[seg + 1]
		var L := a.distance_to(b)
		while along > L and seg < path.size() - 1:
			along -= L
			seg += 1
			if seg >= path.size() - 1:
				break
			a = path[seg]
			b = path[seg + 1]
			L = a.distance_to(b)
		if seg >= path.size() - 1:
			break
		var p := a.lerp(b, along / L)
		_place(p, (p + (b - a).normalized() * 50.0) if look_ahead else look_at_pt)
	var r := {"label": label, "frames": ft.size()}
	for pair in [["ft", ft], ["gpu", gpu], ["dc", dc], ["objs", objs], ["prims", prims], ["sdc", sdc], ["sprims", sprims]]:
		var arr: Array = pair[1].duplicate()
		arr.sort()
		r[pair[0]] = [arr[arr.size() / 2], arr[int(arr.size() * 0.95)], arr[int(arr.size() * 0.99)], arr[-1]]
	enter_ft.sort()
	r["enter"] = enter_ft
	print("  %-22s %5d frames | frame ms p50 %.2f p95 %.2f p99 %.2f worst %.2f | gpu ms p50 %.2f p95 %.2f | draws p50 %d max %d | objects p50 %d max %d | tris p50 %.2fM max %.2fM | shadow draws p50 %d tris p50 %.2fM | %d cell(s) entered, worst such frame %.2f ms | buildings in tree %d"
			% [label, ft.size(), r.ft[0], r.ft[1], r.ft[2], r.ft[3], r.gpu[0], r.gpu[1], r.dc[0], r.dc[3], r.objs[0],
			r.objs[3], r.prims[0] / 1e6, r.prims[3] / 1e6, r.sdc[0], r.sprims[0] / 1e6, enter_ft.size(), enter_ft[-1] if not enter_ft.is_empty() else 0.0,
			_buildings_in_tree()])
	return r

# --- crowd scenarios: pedestrians and traffic streamed through the REAL ZoneManager, measured at one fixed view ------

const ZONE_JAVA := "res://src/main/java/com/openworld/world/Zone.java"
const MARKER_JAVA := "res://src/main/java/com/openworld/world/ZoneMarker.java"
const SPAWN_JAVA := "res://src/main/java/com/openworld/world/SpawnConfig.java"
const VSPAWN_JAVA := "res://src/main/java/com/openworld/world/VehicleSpawnConfig.java"
const ARMED := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"

func _counts() -> Dictionary:
	var c := {"chars": 0, "cars": 0, "active": 0, "passive": 0, "frozen": 0}
	for n in get_nodes_in_group("characters"):
		if n is RigidBody3D:
			c.cars += 1
		elif n is CharacterBody3D:
			c.chars += 1
			if n.has_method("lod_level_now"):
				var l: int = n.call("lod_level_now")
				c[["active", "passive", "frozen"][l]] += 1
	return c

func _light_peds() -> int:
	# The FAR tier (PLAN.md 3.6d): script-free bodies one PedCrowd walks, in no group and not CharacterBody3D,
	# so `_counts()` cannot see them and a scenario's "did they all arrive" wait must add them in.
	var out := []
	_collect(w, "PedCrowd.java", out)
	var n := 0
	for c in out:
		n += int(c.call("ped_count"))
	return n


func _crowd_zone(id: String, at: Vector3, groups: Array, cars: int) -> Node3D:
	# groups: [[count, behavior, faction, weapon]]
	var z: Resource = load(ZONE_JAVA).new()
	z.set("zone_id", id)
	z.set("size", Vector3(360, 20, 360))
	z.set("load_radius", 500.0)
	z.set("unload_radius", 800.0)
	for g in groups:
		var sc: Resource = load(SPAWN_JAVA).new()
		sc.set("count", g[0])
		sc.set("behavior", g[1])
		sc.set("faction", g[2])
		sc.set("weapon_scene_path", g[3])
		z.get("spawn_configs").append(sc)
	if cars > 0:
		var vc: Resource = load(VSPAWN_JAVA).new()
		vc.set("count", cars)
		vc.set("route_name", "island_")
		vc.set("cruise_throttle", 0.5)
		z.get("vehicle_spawn_configs").append(vc)
	var m: Node3D = load(MARKER_JAVA).new()
	m.name = id
	m.set("zone", z)
	m.set("show_debug_volume", false)
	w.add_child(m)
	m.global_position = at
	return m

func _strip_bodies() -> void:
	# variants that say where a character's cost is: its nameplate SubViewport, its hitbox bones, its skeleton
	for n in get_nodes_in_group("characters"):
		if not (n is CharacterBody3D):
			continue
		if _arg("no-nameplates", false):
			var np := n.get_node_or_null("Nameplate")
			if np != null and np.visible:
				np.visible = false
				for v in np.find_children("*", "SubViewport", true, false):
					(v as SubViewport).render_target_update_mode = SubViewport.UPDATE_DISABLED
		if _arg("no-rays", false):
			for rc in n.find_children("*", "RayCast3D", true, false):
				(rc as RayCast3D).enabled = false
		if _arg("no-springarm", false):
			for sa in n.find_children("*", "SpringArm3D", true, false):
				sa.process_mode = Node.PROCESS_MODE_DISABLED
		if _arg("no-modifiers", false):
			for m in n.find_children("*", "SkeletonModifier3D", true, false):
				(m as SkeletonModifier3D).active = false
		if _arg("no-anim", false):
			for t in n.find_children("*", "AnimationTree", true, false):
				(t as AnimationTree).active = false
		if _arg("no-hitboxes", false):
			for pb in n.find_children("*", "PhysicalBone3D", true, false):
				if (pb as PhysicalBone3D).collision_layer != 0:
					(pb as PhysicalBone3D).collision_layer = 0
					(pb as PhysicalBone3D).collision_mask = 0
					PhysicsServer3D.body_set_mode((pb as PhysicalBone3D).get_rid(), PhysicsServer3D.BODY_MODE_STATIC)

func _crowd_bodies() -> Array:
	var out := []
	for n in get_nodes_in_group("characters"):
		if n is CharacterBody3D and not (n == player) and n.get("character_info") != null \
				and str(n.get("character_info").get("faction")) == "neutral" and n.get("story_character") != true:
			out.append(n)
	return out

func _measure(label: String, seconds: float) -> Dictionary:
	_strip_bodies()
	for i in 30:
		await process_frame
	var ft := []
	var phys := []
	var proc := []
	var dc := []
	var objs := []
	var t_prev := Time.get_ticks_usec()
	var t0 := t_prev
	while Time.get_ticks_usec() - t0 < seconds * 1e6:
		await process_frame
		var t := Time.get_ticks_usec()
		ft.append((t - t_prev) / 1000.0)
		t_prev = t
		phys.append(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0)
		proc.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
		dc.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		objs.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_OBJECTS_IN_FRAME))
	for a in [ft, phys, proc, dc, objs]:
		a.sort()
	var c := _counts()
	var r := {"label": label, "ft50": ft[ft.size() / 2], "ft95": ft[int(ft.size() * 0.95)], "phys50": phys[phys.size() / 2],
			"proc50": proc[proc.size() / 2], "dc50": dc[dc.size() / 2], "objs50": objs[objs.size() / 2]}
	r.merge(c)
	r["phys_active"] = Performance.get_monitor(Performance.PHYSICS_3D_ACTIVE_OBJECTS)
	r["pairs"] = Performance.get_monitor(Performance.PHYSICS_3D_COLLISION_PAIRS)
	r["islands"] = Performance.get_monitor(Performance.PHYSICS_3D_ISLAND_COUNT)
	r["nodes"] = Performance.get_monitor(Performance.OBJECT_NODE_COUNT)
	r["nav_ms"] = Performance.get_monitor(Performance.TIME_NAVIGATION_PROCESS) * 1000.0
	r["steps"] = Engine.get_physics_frames()
	var walkers := 0
	var walked := 0.0
	for n in get_nodes_in_group("characters"):
		for ch in (n as Node).get_children():
			if ch.get_script() != null and str(ch.get_script().resource_path).ends_with("SidewalkWalkerController.java"):
				walkers += 1
				walked += float(ch.get("walked"))
	r["walkers"] = walkers
	var light := _light_peds()
	r["light_peds"] = light
	print("    walkers %d (full), light peds %d, mean walked %.1f m" % [walkers, light, walked / maxf(walkers, 1)])
	print("    engine: active bodies %d, collision pairs %d, islands %d, nodes %d, navigation ms %.2f, physics fps target %d"
			% [r.phys_active, r.pairs, r.islands, r.nodes, r.nav_ms, Engine.physics_ticks_per_second])
	print("  crowd %-18s chars %4d (active %3d passive %3d frozen %3d) light %4d cars %3d | frame ms p50 %.2f p95 %.2f | physics-process ms %.2f | process ms %.2f | draws %d | objects %d"
			% [label, c.chars, c.active, c.passive, c.frozen, r.light_peds, c.cars, r.ft50, r.ft95, r.phys50, r.proc50, r.dc50, r.objs50])
	return r

func _crowd() -> void:
	# `--light-crowd=0` is the control for PLAN.md 3.6d: every pedestrian spawned as a full body, which is what
	# this measured before the far tier existed.
	var zm := root.get_node_or_null("/root/ZoneManager")
	if zm != null and _arg("light-crowd") != null:
		zm.set("light_crowd", str(_arg("light-crowd")) != "0")
	# each scenario below IS the crowd being measured, so the island's own shipped one (PLAN.md 3.6d) must not
	# be streaming beside it
	var shipped := w.get_node_or_null("PedZones")
	if shipped != null:
		shipped.free()
	var at := Vector3(560, 0.75, -350)
	_place(at + Vector3(0, 1.65, 0), at + Vector3(80, 1.0, 0))
	await _settle(40.0)
	var scenarios := [
		["base", [], 0],
		["walkers_60", [[60, "sidewalk", "neutral", ""]], 0],
		["walkers_150", [[150, "sidewalk", "neutral", ""]], 0],
		["walkers_300", [[300, "sidewalk", "neutral", ""]], 0],
		["wanderers_60", [[60, "", "neutral", ""]], 0],
		["wanderers_150", [[150, "", "neutral", ""]], 0],
		["armed_fight_40", [[20, "", "gang_a", ARMED], [20, "", "gang_b", ARMED]], 0],
		["traffic_20", [], 20],
		["traffic_40", [], 40],
		["mixed_150w_20c", [[150, "sidewalk", "neutral", ""]], 20],
	]
	var base_chars := 0
	for sc in scenarios:
		if _arg("scenarios") != null and not (sc[0] in str(_arg("scenarios")).split(",")):
			continue
		var want := 0
		for g in sc[1]:
			want += g[0]
		var m: Node3D = null
		if not sc[1].is_empty() or sc[2] > 0:
			m = _crowd_zone("perf_" + sc[0], at, sc[1], sc[2])
			# frame-spread spawning: wait until the bodies are in (or 30 s), then 3 s for them to get going
			var t0 := Time.get_ticks_msec()
			while Time.get_ticks_msec() - t0 < 30000 and _counts().chars + _light_peds() < base_chars + want:
				await process_frame
			var t1 := Time.get_ticks_msec()
			while Time.get_ticks_msec() - t1 < 4000:
				await process_frame
		else:
			base_chars = _counts().chars
		await _measure(sc[0], 8.0)
		if _arg("child-bisect", false) and m != null:
			var bodies := _crowd_bodies()
			var names := []
			for c in (bodies[0] as Node).get_children():
				names.append(str(c.name))
			print("    children: %s" % [names])
			for nm in names:
				for n in bodies:
					if not is_instance_valid(n):
						continue
					var c := (n as Node).get_node_or_null(NodePath(nm))
					if c != null:
						c.process_mode = Node.PROCESS_MODE_DISABLED
				await _measure("-%s" % nm, 4.0)
		if _arg("subtree-test", false) and m != null:
			for n in _crowd_bodies():
				n.process_mode = Node.PROCESS_MODE_DISABLED
			await _measure(sc[0] + " -subtree disabled", 6.0)
			for n in _crowd_bodies():
				n.process_mode = Node.PROCESS_MODE_INHERIT
				n.visible = false
			await _measure(sc[0] + " -hidden (processing on)", 6.0)
			for n in _crowd_bodies():
				n.visible = true
				for co in n.find_children("*", "CollisionObject3D", true, false):
					PhysicsServer3D.body_set_space((co as CollisionObject3D).get_rid(), RID()) if not (co is Area3D) else \
							PhysicsServer3D.area_set_space((co as CollisionObject3D).get_rid(), RID())
				PhysicsServer3D.body_set_space((n as CollisionObject3D).get_rid(), RID())
			await _measure(sc[0] + " -out of the physics space", 6.0)
		if _arg("free-test", false) and m != null:
			var nfree := 0
			for n in get_nodes_in_group("characters"):
				if n is CharacterBody3D and not (n == player) and n.get("character_info") != null \
						and str(n.get("character_info").get("faction")) == "neutral" and n.get("story_character") != true:
					n.queue_free()
					nfree += 1
			for i in 10:
				await process_frame
			print("    freed %d crowd bodies (the zone marker kept)" % nfree)
			await _measure(sc[0] + " -bodies freed", 6.0)
		if _arg("strip-sequence", false) and m != null:
			# cumulative: switch one per-character node's processing off at a time, and measure again
			for nm in ["TPSCameraController", "FPSCameraController", "AnimationController", "WeaponController",
					"MovementController", "NavigationAgent3D", "Stances"]:
				for n in get_nodes_in_group("characters"):
					if n is CharacterBody3D and not (n == player):
						var c := n.get_node_or_null(nm)
						if c != null:
							c.process_mode = Node.PROCESS_MODE_DISABLED
				await _measure(sc[0] + " -" + nm, 6.0)
			for n in get_nodes_in_group("characters"):
				if n is CharacterBody3D and not (n == player):
					for sim in n.find_children("*", "PhysicalBoneSimulator3D", true, false):
						sim.queue_free()
			await _measure(sc[0] + " -hitbox bones freed", 6.0)
			for n in get_nodes_in_group("characters"):
				if n is CharacterBody3D and not (n == player):
					n.set_physics_process(false)
			await _measure(sc[0] + " -body tick", 6.0)
			var freed := 0
			for n in get_nodes_in_group("characters"):
				if n is CharacterBody3D and not (n == player) and n.get("character_info") != null \
						and str(n.get("character_info").get("faction")) == "neutral" and n.get("story_character") != true:
					n.queue_free()
					freed += 1
			for i in 10:
				await process_frame
			print("    freed %d bodies of the crowd zone (marker kept)" % freed)
			await _measure(sc[0] + " -bodies freed", 6.0)
		if m != null:
			m.queue_free()
			var t2 := Time.get_ticks_msec()
			while Time.get_ticks_msec() - t2 < 20000 and _counts().chars > base_chars:
				await process_frame
			for i in 60:
				await process_frame

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var zm := root.get_node_or_null("ZoneManager")
	if zm != null:
		zm.set("debug_log", false)     # ~100 streaming lines a second through a pipe is a cost of its own
	DisplayServer.window_set_size(Vector2i(1920, 1080))
	Engine.max_fps = 0
	w = (load(WORLD) as PackedScene).instantiate()
	if _arg("no-buildings", false):
		var h := w.get_node_or_null("BuildingZones")
		if h != null:
			w.remove_child(h)
			h.free()
		print("CONTROL: no BuildingZones")
	# a fixed noon: the sky's clock runs a day in 15 min, and a night leg has no sun shadows to pay for
	var tod := w.get_node_or_null("Sky3D/TimeOfDay")
	if tod != null:
		tod.set("game_time_enabled", false)
		tod.set("current_time", 12.0)
	if _arg("shadow-distance") != null:
		var sun := w.get_node_or_null("Sky3D/SunLight") as DirectionalLight3D
		if sun != null:
			sun.directional_shadow_max_distance = float(_arg("shadow-distance"))
			print("VARIANT: sun shadow distance %.0f m" % sun.directional_shadow_max_distance)
	if _arg("no-lod", false):
		root.mesh_lod_threshold = 0.0
		print("CONTROL: mesh LOD off (full detail everywhere)")
	root.add_child(w)
	current_scene = w
	player = w.get_node("Characters/Player")
	player.get_node("Health").set("max_health", 1000000.0)
	player.set_physics_process(false)
	player.visible = false
	cam = Camera3D.new()
	cam.far = 4000.0
	cam.fov = 75.0
	w.add_child(cam)
	vp_rid = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp_rid, true)
	await process_frame
	await process_frame
	cam.make_current()
	# Legs (Godot frame; downtown is inside C1, record x 150..1300, y 40..720 -> z -720..-40; the street grid's
	# east-west streets run at record y 110 / 350 / 540, the north-south ones at x 224 / 562 / 912 / 1250).
	var street_y := 2.4
	var results := []
	results.append(await _leg("street_ew_downtown", [Vector3(180, street_y, -350), Vector3(1320, street_y, -350)], 15.0, true))
	results.append(await _leg("street_ns_downtown", [Vector3(912, street_y, 60), Vector3(912, street_y, -760)], 15.0, true))
	results.append(await _leg("street_residential", [Vector3(-1300, street_y, 530), Vector3(-150, street_y, 530)], 15.0, true))
	results.append(await _leg("drive_fast_arterial", [Vector3(-1600, street_y, 330), Vector3(-200, street_y, 330),
			Vector3(600, street_y, 100), Vector3(1500, street_y, 60)], 40.0, true))
	results.append(await _leg("overview_60m", [Vector3(-100, 60, 150), Vector3(1500, 60, 150)], 25.0, false, Vector3(725, 0, -380)))
	results.append(await _leg("overview_200m_orbit", [Vector3(725, 200, 600), Vector3(1700, 200, -380), Vector3(725, 200, -1300),
			Vector3(-250, 200, -380), Vector3(725, 200, 600)], 60.0, false, Vector3(725, 0, -380)))
	if _arg("crowd", false):
		await _crowd()
	var budget := float(_arg("budget", "16.7"))
	var street_p95: float = results[0].ft[1] if results[0].has("ft") else 0.0
	print("RESULT %s street p95 %.2f ms (budget %.1f)" % ["PASS" if street_p95 <= budget else "FAIL", street_p95, budget])
	quit(0 if street_p95 <= budget else 1)
