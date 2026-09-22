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
##       [--no-peds] [--no-traffic] [--no-buildings] [--no-hlod]      (controls: remove that derived block before the world loads)

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
var w: Node
var cam: Camera3D
var player: Node3D
var vp_rid: RID
var args := {}
var cells := {}          # postal code -> {ft:[], phys:[], proc:[], ticks:[], dc:[], tris:[], chars:[]}
var legs_out := []

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

func _place(pos: Vector3, fwd: Vector3) -> void:
	player.global_position = pos
	var f := Vector3(fwd.x, 0, fwd.z)
	if f.length() < 1e-3:
		f = Vector3(0, 0, -1)
	f = f.normalized()
	cam.global_position = pos - f * 5.0 + Vector3(0, 2.2, 0)
	cam.look_at(pos + f * 20.0 + Vector3(0, 1.2, 0), Vector3.UP)

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
	await _settle(12.0)             # streaming + the crowd around the start
	var ft := []
	var ph := []
	var ticks := []
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
		var proc := Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
		var chars := get_nodes_in_group("characters").size()
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
	var slow := 0
	for v in ft:
		if v > 33.3:
			slow += 1
	legs_out.append([label, _pct(ft, 0.5), _pct(ft, 0.95), _pct(ft, 0.99), ft.max() if not ft.is_empty() else 0.0, slow, ft.size()])
	print("  %-22s %5d frames | frame ms p50 %6.2f p95 %6.2f p99 %6.2f worst %7.2f | %4.1f%% under 30 fps | phys ms p50 %.2f p95 %.2f | ticks/frame p95 %d"
			% [label, ft.size(), _pct(ft, 0.5), _pct(ft, 0.95), _pct(ft, 0.99), ft.max() if not ft.is_empty() else 0.0,
			100.0 * slow / max(1, ft.size()), _pct(ph, 0.5), _pct(ph, 0.95), int(_pct(ticks, 0.95))])

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
	player.get_node("Health").set("max_health", 1000000.0)
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
	# the busy station: up to Tokyo Station's front, into the concourse, along it and out
	await _leg("walk_station", [Vector3(592, g, -60), Vector3(592, g, -135), Vector3(592, g, -155),
			Vector3(470, g, -155), Vector3(470, g, -110)], 3.0)
	# into a downtown konbini (a shop with an interior and a door)
	await _leg("enter_konbini", [Vector3(600, g, -361.2), Vector3(559.7, g, -361.2), Vector3(553.9, g, -361.2),
			Vector3(550.0, g, -358.0)], 2.0)
	# round Tokyo Tower's park
	await _leg("walk_tower", [Vector3(620, g, -300), Vector3(740, g, -300), Vector3(740, g, -430),
			Vector3(620, g, -430)], 5.0)
	# a drive through downtown on the trunk grid, then on C1 (elevated)
	await _leg("drive_downtown", [Vector3(600, 1.4, 150), Vector3(600, 1.4, -800)], 20.0)
	await _leg("drive_c1", [Vector3(40, 12.5, 100), Vector3(1160, 12.5, 100), Vector3(1160, 12.5, -560),
			Vector3(40, 12.5, -560), Vector3(40, 12.5, 100)], 25.0)
	# a residential walk (the SW grid), as a quiet control
	await _leg("walk_residential", [Vector3(-1000, g, 600), Vector3(-300, g, 600)], 6.0)
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
	print("RESULT %s worst leg p95 %.2f ms (budget %.1f)" % ["PASS" if worst_p95 <= budget else "FAIL", worst_p95, budget])
	quit(0 if worst_p95 <= budget else 1)
