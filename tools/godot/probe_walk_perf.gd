extends SceneTree
## WHERE does the frame rate drop? (user, 2026-09-22: "driving / walking in the city, a busy station, entering a busy
## building ... 20-30 fps, sometimes below 20, depending on where I walk"). Runs World.tscn WITH A DISPLAY (the real
## renderer), vsync off, noon, and moves the REAL local player along walk and drive legs -- so zone streaming, the
## crowd's promotion into real bodies, AI LOD and traffic all react exactly as in play -- with a third-person camera
## behind it. Every frame it records the frame time, the engine's own process and physics timers, the physics ticks
## run that frame (a spiral shows up as > 1), draw calls, triangles, objects and the character count, and files the
## frame under the player's POSTAL CODE (PLAN.md 3.26), so a hotspot comes out as `12-7-5`, which
## `postal 12-7-5 tp` in the debug console goes straight to.
##
##   <godot> --path . --script tools/godot/probe_walk_perf.gd [-- --legs=a,b] [--budget=16.7] [--top=12]
##       [--no-peds] [--no-traffic] [--no-buildings] [--no-hlod] [--no-parked]      (controls: remove that derived block before the world loads)
##       [--wanted=N] [--gang=N]   PEAK LOAD (PLAN.md W5): hold the player at N police stars (lethal, so they shoot
##                  rather than arrest; the player is invulnerable) and/or N stars with gang_a, so the enforcement
##                  dispatch's officers, patrol cars and gang hunters are in the ring for every leg
##       [--no-interior-nav]   control: no building interior navmesh regions attach as cells stream (world.InteriorNav)
##       [--no-balance]   control: the dispatch adds on top of the ambient budgets (ZoneManager.enforcementBalancing)
##       [--traffic-budget=N] [--sim-radius=M] [--recycle=M]   PLAN.md 2c sweeps: ZoneManager's car budget, simulation
##                  ring and the leaving-car recycle distance (0 = off)
##       [--haze=<end m>]   PLAN.md 2b: Sky3D's distance haze on, ending at that distance (start at a third of it)
##       [--deck]   the Steam Deck PROXY (PLAN.md R-9): 1280x800, each frame's deck_ms = max(cpu x cpu_factor,
##                  gpu x gpu_factor) from tools/godot/perf_budget.json, judged against its frame and count budgets;
##                  prints a `DECK <leg> p50 p95` line per leg that tools/perf_gate.sh reads for per-system attribution

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var w: Node
var cam: Camera3D
var player: Node3D
var vp_rid: RID
var args := {}
var cells := {}          # postal code -> {ft:[], phys:[], proc:[], ticks:[], dc:[], tris:[], chars:[]}
var legs_out := []
var deck := false
var budget_cfg := {}
var deck_fail := []

func _arg(k: String, d = null):
	return args.get(k, d)

func _code(p: Vector3) -> String:
	var u := p.x + 2304.0
	var v := p.z + 2304.0
	var cx := clampi(int(floor(u / 192.0)) + 1, 1, 24)
	var cy := clampi(int(floor(v / 192.0)) + 1, 1, 24)
	var col := clampi(int(floor((u - (cx - 1) * 192.0) / 64.0)), 0, 2)
	var row := clampi(int(floor((v - (cy - 1) * 192.0) / 64.0)), 0, 2)
	return "%d-%d-%d" % [cx, cy, row * 3 + col + 1]

func _info(kind: int) -> int:
	return RenderingServer.viewport_get_render_info(vp_rid, RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, kind)

## The walkable surface under (x, z), so the player never stands UNDER the terrain (user, 2026-10-04: the legs had
## their heights typed from before the land raise -- y 1.65 on a 5.6 m plain -- and walked under the ground, which
## streams and draws a different world). An `elevated` leg (a hint over 10 m: C1) takes the topmost surface, i.e. the
## deck; a ground leg casts down from 2.5 m over the terrain, so a deck overhead is never taken for the street.
var under_terrain := 0
var world_bounds: Node
func _ground(pos: Vector3) -> Vector3:
	var wb := world_bounds
	var h: float = wb.call("terrain_height", pos.x, pos.z) if wb != null else NAN
	if is_nan(h):
		return pos
	var top := h + (60.0 if pos.y > 10.0 else 2.5)
	var q := PhysicsRayQueryParameters3D.create(Vector3(pos.x, top, pos.z), Vector3(pos.x, h - 1.0, pos.z), 1)
	q.exclude = [player.get_rid()]
	var hit := player.get_world_3d().direct_space_state.intersect_ray(q)
	var y: float = (hit["position"].y if not hit.is_empty() else h) + 0.1
	return Vector3(pos.x, maxf(y, h + 0.05), pos.z)

func _place(pos: Vector3, fwd: Vector3) -> void:
	pos = _ground(pos)
	player.global_position = pos
	# a hand placement keeps MovementController's own fall speed (CLAUDE.md Known Quirks): placed every frame and
	# never cleared, it built up to -648 m/s and dropped the body under the ground between placements (1242 frames)
	player.set("velocity", Vector3.ZERO)
	var mc := player.get_node_or_null("MovementController")
	if mc != null:
		mc.call("clear_motion")
	var f := Vector3(fwd.x, 0, fwd.z)
	if f.length() < 1e-3:
		f = Vector3(0, 0, -1)
	f = f.normalized()
	cam.global_position = pos - f * 5.0 + Vector3(0, 2.2, 0)
	cam.look_at(pos + f * 20.0 + Vector3(0, 1.2, 0), Vector3.UP)

func _hold_standing() -> void:
	# PEAK LOAD: keep the stars up (the heat would drain, the arrest would end the run)
	var gm := root.get_node_or_null("GameManager")
	if gm == null or player == null:
		return
	var pid: String = player.get("character_info").get("character_id")
	if _arg("wanted") != null and gm.get_node_or_null("WantedSystem") != null:
		gm.get_node("WantedSystem").call("set_stars_now", pid, int(_arg("wanted")), true)
	if _arg("gang") != null and gm.get_node_or_null("GangSystem") != null:
		gm.get_node("GangSystem").call("set_gang_stars_now", pid, "gang_a", int(_arg("gang")))

func _settle(seconds: float) -> void:
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < seconds * 1000.0:
		await process_frame

func _pct(a: Array, q: float) -> float:
	if a.is_empty():
		return 0.0
	var b := a.duplicate()
	b.sort()
	return b[min(b.size() - 1, int(b.size() * q))]

func _leg(label: String, path: Array, speed: float) -> void:
	if _arg("legs") != null and not (label in str(_arg("legs")).split(",")):
		return
	_place(path[0], path[1] - path[0])
	_hold_standing()
	await _settle(12.0)             # streaming + the crowd around the start
	var under0 := under_terrain
	var near_sum := [0.0, 0.0]
	var navt := []
	var near_n := 0
	var ft := []
	var ph := []
	var ticks := []
	var dk := []
	var gp := []
	var dcs := []
	var chs := []
	var seg := 0
	var along := 0.0
	var t_prev := Time.get_ticks_usec()
	var pf_prev := Engine.get_physics_frames()
	while seg < path.size() - 1:
		await process_frame
		var t := Time.get_ticks_usec()
		var dt := (t - t_prev) / 1000.0
		t_prev = t
		var pf := Engine.get_physics_frames()
		var nt := pf - pf_prev
		pf_prev = pf
		var phys := Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
		navt.append(Performance.get_monitor(Performance.TIME_NAVIGATION_PROCESS) * 1000.0)
		var proc := Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
		var chars := get_nodes_in_group("characters").size()
		if world_bounds != null:
			var th: float = world_bounds.call("terrain_height", player.global_position.x, player.global_position.z)
			if not is_nan(th) and player.global_position.y < th - 0.2:
				under_terrain += 1
				if under_terrain - under0 <= 5 or (under_terrain - under0) % 200 == 0:
					print("    under at %s, terrain %.2f, vel %s" % [str(player.global_position), th, str(player.velocity)])
		if _arg("no-interior-nav", false) and Engine.get_physics_frames() % 30 == 0:
			# control: the dispatch exists only after GameManager's ready, so the switch is applied here, and any
			# region a door attached before it is removed
			var edn := root.get_node_or_null("GameManager/EnforcementDispatch")
			if edn != null and bool(edn.get("interior_nav")):
				edn.set("interior_nav", false)
				var gone := 0
				for r in w.find_children("InteriorNav", "NavigationRegion3D", true, false):
					r.queue_free()
					gone += 1
				print("CONTROL: interior navmeshes off (world.InteriorNav), %d already attached removed" % gone)
		if _arg("no-parked", false) and Engine.get_physics_frames() % 30 == 0:
			# control: the placed-but-unused vehicles (world.ParkedVehicle remembers a spot, so it does not respawn)
			for pv in get_nodes_in_group("parked_vehicle"):
				pv.queue_free()
		if Engine.get_process_frames() % 60 == 0:
			_hold_standing()
			var zmn := root.get_node_or_null("ZoneManager")
			if zmn != null:
				near_sum[0] += int(zmn.call("traffic_near_now", 100.0))
				near_sum[1] += int(zmn.call("traffic_near_now", 200.0))
				near_n += 1
		var code := _code(player.global_position)
		if not cells.has(code):
			cells[code] = {"ft": [], "phys": [], "proc": [], "ticks": [], "dc": [], "tris": [], "chars": [], "legs": {}}
		var c: Dictionary = cells[code]
		c.ft.append(dt); c.phys.append(phys); c.proc.append(proc); c.ticks.append(nt)
		c.dc.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		c.tris.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME))
		c.chars.append(chars)
		c.legs[label] = true
		ft.append(dt); ph.append(phys); ticks.append(nt)
		var gpu := RenderingServer.viewport_get_measured_render_time_gpu(vp_rid)
		gp.append(gpu)
		dk.append(maxf(dt * float(budget_cfg.get("cpu_factor", 1.0)), gpu * float(budget_cfg.get("gpu_factor", 1.0))))
		dcs.append(_info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		chs.append(chars)
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
		_place(a.lerp(b, along / L), b - a)
	var census := {"vehicle": 0, "seated": 0, "ai_walking": 0, "player": 0, "other": 0, "near100": 0}
	for n in get_nodes_in_group("characters"):
		var sp := str(n.get_script().resource_path) if n.get_script() != null else ""
		if (n as Node3D).global_position.distance_to(player.global_position) < 100.0:
			census["near100"] += 1
		if sp.contains("/vehicle/") or sp.contains("/carrier/"):
			census["vehicle"] += 1
		elif sp.ends_with("Player.java"):
			census["player"] += 1
		elif sp.ends_with("AICharacter.java"):
			census["seated" if n.get("current_vehicle_node") != null else "ai_walking"] += 1
		else:
			census["other"] += 1
	var light := 0
	for c in w.find_children("*", "", true, false):
		if str(c.get_script().resource_path if c.get_script() != null else "").ends_with("PedCrowd.java"):
			light += c.get_child_count()
	var doors := 0
	var ticking := 0
	for dn in w.find_children("*", "", true, false):
		if dn.has_method("ticking_now"):
			doors += 1
			ticking += 1 if dn.call("ticking_now") else 0
	print("    census at leg end: %s, light peds %d, doors %d (%d ticking)" % [str(census), light, doors, ticking])
	var ed := root.get_node_or_null("GameManager/EnforcementDispatch")
	var zmc := root.get_node_or_null("ZoneManager")
	if ed != null and zmc != null:
		print("    enforcement units (foot,cars en route,cars arrived,arrests) %s; ambient traffic %d / budget %d" % [
				str(ed.call("units_now")), int(zmc.call("traffic_alive_now")), int(zmc.call("effective_traffic_budget_now"))])
		print("    traffic near the player over the leg: mean %.1f within 100 m, %.1f within 200 m; recycled (leaving) %d" % [
				near_sum[0] / maxf(1.0, near_n), near_sum[1] / maxf(1.0, near_n), int(zmc.call("traffic_recycled_now"))])
	if under_terrain > under0:
		print("    UNDER the terrain on %d frames of this leg" % (under_terrain - under0))
	var slow := 0
	var over60 := 0
	for v in ft:
		if v > 33.3:
			slow += 1
		if v > 16.7:
			over60 += 1
	legs_out.append([label, _pct(ft, 0.5), _pct(ft, 0.95), _pct(ft, 0.99), ft.max() if not ft.is_empty() else 0.0, slow, ft.size()])
	navt.sort()
	print("    navigation server ms per frame: p50 %.3f p95 %.3f max %.3f" % [navt[navt.size() / 2], navt[int(navt.size() * 0.95)], navt[navt.size() - 1]])
	print("  %-22s %5d frames | frame ms p50 %6.2f p95 %6.2f p99 %6.2f worst %7.2f | %4.1f%% over 16.7 ms | %4.1f%% under 30 fps | phys ms p50 %.2f p95 %.2f | ticks/frame p95 %d"
			% [label, ft.size(), _pct(ft, 0.5), _pct(ft, 0.95), _pct(ft, 0.99), ft.max() if not ft.is_empty() else 0.0,
			100.0 * over60 / max(1, ft.size()), 100.0 * slow / max(1, ft.size()), _pct(ph, 0.5), _pct(ph, 0.95), int(_pct(ticks, 0.95))])
	if deck:
		var fb := float(budget_cfg.get("frame_deck_ms_p95", 33.3))
		var cb: Dictionary = budget_cfg.get("counts_p95", {})
		print("DECK %s p50 %.2f p95 %.2f gpu_p95 %.2f draws_p95 %d chars_p95 %d" % [label, _pct(dk, 0.5), _pct(dk, 0.95),
				_pct(gp, 0.95), int(_pct(dcs, 0.95)), int(_pct(chs, 0.95))])
		if _pct(dk, 0.95) > fb:
			deck_fail.append("%s deck p95 %.1f > %.1f ms" % [label, _pct(dk, 0.95), fb])
		if cb.has("draws") and _pct(dcs, 0.95) > float(cb["draws"]):
			deck_fail.append("%s draws p95 %d > %d" % [label, int(_pct(dcs, 0.95)), int(cb["draws"])])
		if cb.has("characters") and _pct(chs, 0.95) > float(cb["characters"]):
			deck_fail.append("%s characters p95 %d > %d" % [label, int(_pct(chs, 0.95)), int(cb["characters"])])

func _strip_hlod(n: Node) -> void:
	if n is MeshInstance3D and n.name == "HLOD":
		(n as MeshInstance3D).visible = false
		(n as MeshInstance3D).visibility_range_begin = 0.0
	elif n is MeshInstance3D and n.name == "Mesh" and str((n as MeshInstance3D).visibility_parent).ends_with("HLOD"):
		(n as MeshInstance3D).visibility_parent = NodePath("")

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	deck = _arg("deck", false) != false
	if deck:
		budget_cfg = JSON.parse_string(FileAccess.get_file_as_string("res://tools/godot/perf_budget.json"))
		var res: Array = budget_cfg.get("resolution", [1280, 800])
		DisplayServer.window_set_size(Vector2i(int(res[0]), int(res[1])))
		print("DECK PROXY: %dx%d, cpu x%.1f, gpu x%.1f, frame budget p95 %.1f ms" % [int(res[0]), int(res[1]),
				float(budget_cfg["cpu_factor"]), float(budget_cfg["gpu_factor"]), float(budget_cfg["frame_deck_ms_p95"])])
	else:
		DisplayServer.window_set_size(Vector2i(1920, 1080))
	Engine.max_fps = 0
	var zm := root.get_node_or_null("ZoneManager")
	if zm != null:
		zm.set("debug_log", false)
	if _arg("no-hlod", false):
		# R9's control: every cell's HLOD hidden and its buildings freed of it, i.e. the city as it was before
		node_added.connect(_strip_hlod)
	w = (load(WORLD) as PackedScene).instantiate()
	for flag in [["no-peds", "PedZones"], ["no-traffic", "TrafficZones"], ["no-buildings", "BuildingZones"]]:
		if _arg(flag[0], false):
			var h := w.get_node_or_null(flag[1])
			if h != null:
				w.remove_child(h)
				h.free()
				print("CONTROL: no %s" % flag[1])
	var tod := w.get_node_or_null("Sky3D/TimeOfDay")
	if tod != null:
		tod.set("game_time_enabled", false)
		tod.set("current_time", 12.0)
	root.add_child(w)
	current_scene = w
	player = w.get_node("Characters/Player")
	world_bounds = w.find_child("WorldBounds", true, false)
	player.get_node("Health").set("max_health", 1000000.0)
	if _arg("wanted") != null or _arg("gang") != null:
		player.get_node("Health").set("invulnerable", true)
	if zm != null and _arg("traffic-budget") != null:
		zm.set("traffic_budget", int(_arg("traffic-budget")))
		print("SWEEP: traffic budget %d" % int(_arg("traffic-budget")))
	if zm != null and _arg("recycle") != null:
		zm.set("traffic_recycle_dist", float(_arg("recycle")))
		print("SWEEP: traffic recycle distance %.0f m (0 = off)" % float(_arg("recycle")))
	if zm != null and _arg("sim-radius") != null:
		zm.set("traffic_sim_radius", float(_arg("sim-radius")))
		print("SWEEP: traffic simulation ring %.0f m" % float(_arg("sim-radius")))
	if _arg("haze") != null:
		var sky := w.get_node_or_null("Sky3D")
		var dome := w.get_node_or_null("Sky3D/SkyDome")
		var end_m := float(_arg("haze"))
		if sky != null:
			sky.set("fog_enabled", true)
		if dome != null:
			dome.set("fog_visible", true)
			dome.set("fog_start", end_m / 3.0)
			dome.set("fog_end", end_m)
		print("SWEEP: haze %.0f .. %.0f m" % [end_m / 3.0, end_m])
	if _arg("no-balance", false) and zm != null:
		zm.set("enforcement_balancing", false)
		print("CONTROL: no enforcement balancing")
	player.set_physics_process(false)      # moved by the probe; everything that reads its position still does
	cam = Camera3D.new()
	cam.far = 4000.0
	cam.fov = 75.0
	w.add_child(cam)
	vp_rid = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp_rid, true)
	await process_frame
	await process_frame
	cam.make_current()
	var g := 0.75 + 0.9     # standing on a footway / lot (world y of the plain is 0.6 + kerb)
	# walk the downtown grid (the E-W street through the station quarter), walking pace
	await _leg("walk_downtown", [Vector3(80, g, -100), Vector3(1150, g, -100)], 6.0)
	# the busy station: along Central's forecourt (the bus terminal), into the elevated hub's F1 hall and along it
	# (Central Station is at (782, -215); the forecourt reserve's centre at (787.5, -149.5))
	await _leg("walk_station", [Vector3(700, g, -125), Vector3(870, g, -125), Vector3(787, g, -150),
			Vector3(787, g, -205), Vector3(720, g, -205)], 3.0)
	# into a downtown konbini (KonbiniS at (569.1, -322.0), its door facing +X at (579.0, -322.0))
	await _leg("enter_konbini", [Vector3(605, g, -322.0), Vector3(579.5, g, -322.0), Vector3(575.0, g, -322.0),
			Vector3(570.0, g, -320.0)], 2.0)
	# round the Broadcast Centre (the site at (680, -365) that replaced Tokyo Tower)
	await _leg("walk_tower", [Vector3(620, g, -300), Vector3(740, g, -300), Vector3(740, g, -430),
			Vector3(620, g, -430)], 5.0)
	# a drive through downtown on the trunk grid, then on C1 (elevated)
	await _leg("drive_downtown", [Vector3(600, 1.4, 150), Vector3(600, 1.4, -800)], 20.0)
	await _leg("drive_c1", [Vector3(40, 12.5, 100), Vector3(1160, 12.5, 100), Vector3(1160, 12.5, -560),
			Vector3(40, 12.5, -560), Vector3(40, 12.5, 100)], 25.0)
	# a residential walk (the SW grid), as a quiet control
	# kichi_dori's east FOOTWAY (IslandSidewalks.json walk line): the straight line this leg used to walk crossed the
	# SupermarketSite and the physics pushed the placed capsule out under the ground
	await _leg("walk_residential", [Vector3(-492.0, g, 312.3), Vector3(-493.6, g, 396.3), Vector3(-493.6, g, 1065.9)], 6.0)
	var rows := []
	for code in cells:
		var c: Dictionary = cells[code]
		if c.ft.size() < 20:
			continue
		rows.append([_pct(c.ft, 0.95), code, c])
	rows.sort()
	rows.reverse()
	var top := int(_arg("top", "12"))
	print("\n  WORST POSTAL CELLS (by frame-time p95; `postal <code> tp` in the console goes there)")
	print("  %-8s %5s %7s %7s %7s | %7s %7s %5s | %6s %7s %5s | %s" % ["code", "n", "p50", "p95", "worst", "phys", "proc",
			"tick", "draws", "tris M", "chars", "legs"])
	for r in rows.slice(0, top):
		var c: Dictionary = r[2]
		print("  %-8s %5d %7.2f %7.2f %7.2f | %7.2f %7.2f %5d | %6d %7.2f %5d | %s" % [r[1], c.ft.size(), _pct(c.ft, 0.5),
				r[0], c.ft.max(), _pct(c.phys, 0.5), _pct(c.proc, 0.5), int(_pct(c.ticks, 0.95)), int(_pct(c.dc, 0.5)),
				_pct(c.tris, 0.5) / 1e6, int(_pct(c.chars, 0.5)), ",".join(c.legs.keys())])
	var budget := float(_arg("budget", "16.7"))
	var worst_p95 := 0.0
	for l in legs_out:
		worst_p95 = maxf(worst_p95, l[2])
	print("  frames with the player UNDER the terrain: %d (must be 0, or the numbers are of the wrong world)" % under_terrain)
	if under_terrain > 0:
		worst_p95 = INF
	if deck:
		for f in deck_fail:
			print("  DECK OVER BUDGET: " + f)
		var ok := deck_fail.is_empty() and under_terrain == 0
		print("RESULT %s deck proxy (%d over budget)" % ["PASS" if ok else "FAIL", deck_fail.size()])
		quit(0 if ok else 1)
		return
	print("RESULT %s worst leg p95 %.2f ms (budget %.1f)" % ["PASS" if worst_p95 <= budget else "FAIL", worst_p95, budget])
	quit(0 if worst_p95 <= budget else 1)
