extends SceneTree
## CAN THE POLICE BE LOST? (user, 2026-10-10: "even 1 to 3 stars cannot lose the police engagement").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_lose_police.gd \
##       [-- --stars=2] [--control] [--hide]
##
## The real World.tscn. The player is given stars downtown and waits until police have them IN SIGHT; then they are
## gone from there (set down 230 m away, out of every unit's reach -- the cleanest "got away" there is). With the
## search phase (EnforcementDispatch.searchPhase) the police must (1) be LOST within a few seconds, (2) NOT turn up
## at the player's new position (they search where the player was last seen), and (3) the stars must drain to
## nothing after the calm period. `--control` switches the search phase off: units keep being sent to the player's
## true position, reach alone keeps the heat up, and the stars must still be there at the end -- the reported bug.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
var fails := 0

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-64s %s" % ["PASS" if ok else "FAIL", label, detail])

func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a == "--" + name:
			return true
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def

func _police_near(ed: Node, at: Vector3) -> float:
	var best := 1e9
	for b in ed.call("bodies_now", "police"):
		if is_instance_valid(b):
			best = minf(best, Vector2(b.global_position.x - at.x, b.global_position.z - at.z).length())
	return best

## --hide: the player ducks out of sight NEARBY (the first spot 45-110 m off with a building between it and every
## police body), so the units SEARCH: they must be lost, stay alive round the last known place, and the run must end
## either with the stars gone or with a unit having found the player again (both are the feature working).
func _hide(player: Node3D, wb: Node, ws: Node, ed: Node, pid: String) -> void:
	var space := root.get_world_3d().direct_space_state
	var from := player.global_position
	var spot := Vector3.INF
	for r in [50.0, 70.0, 90.0, 110.0]:
		for k in 24:
			var ang := TAU * k / 24.0
			var q := Vector3(from.x + sin(ang) * r, 0, from.z + cos(ang) * r)
			q.y = float(wb.call("terrain_height", q.x, q.z)) + 1.0
			var hidden := true
			for body in ed.call("bodies_now", "police"):
				var ray := PhysicsRayQueryParameters3D.create(body.global_position + Vector3(0, 1.4, 0), q + Vector3(0, 0.4, 0), 1)
				if space.intersect_ray(ray).is_empty():
					hidden = false
			# and not INSIDE something: open sky above
			var up := PhysicsRayQueryParameters3D.create(q, q + Vector3(0, 60, 0), 1)
			if hidden and space.intersect_ray(up).is_empty() and spot == Vector3.INF:
				spot = q
	check("a hiding place exists near the scene", spot != Vector3.INF, str(spot))
	if spot == Vector3.INF:
		quit(1)
		return
	player.global_position = spot
	var mc := player.get_node_or_null("MovementController")
	if mc != null and mc.has_method("clear_motion"):
		mc.call("clear_motion")
	var lost := false
	var units_while_lost := 0
	var near_known := 1e9
	for i in 60 * 70:
		await physics_frame
		if i % 15 != 0:
			continue
		var sight := str(ed.call("sight_now", pid))
		if sight.contains("lost=true"):
			lost = true
			var n := 0
			for body in ed.call("bodies_now", "police"):
				if is_instance_valid(body):
					n += 1
					near_known = minf(near_known, Vector2(body.global_position.x - from.x, body.global_position.z - from.z).length())
			units_while_lost = maxi(units_while_lost, n)
		if i % 600 == 0:
			print("    t=%2.0f s  stars %d  %s  units %s  nearest police %.0f m" % [i / 60.0, int(ws.call("stars_now", pid)),
				sight, ed.call("units_now"), _police_near(ed, player.global_position)])
	var end := str(ed.call("sight_now", pid))
	check("the police lose a player hiding %.0f m away" % Vector2(spot.x - from.x, spot.z - from.z).length(), lost, end)
	check("units stay and search round the last known place", units_while_lost > 0 and near_known < 46.0,
		"%d unit(s) at once, the closest came to %.0f m of it" % [units_while_lost, near_known])
	check("it ends: the stars are gone, or a unit found the player again",
		int(ws.call("stars_now", pid)) == 0 or not end.contains("found_n=0"), "stars %d, %s" % [int(ws.call("stars_now", pid)), end])
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)

func _initialize() -> void:
	var stars := int(_arg("stars", "2"))
	var control := bool(_arg("control", false))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var player: Node3D = world.get_node("Characters/Player")
	root.add_child(world)
	current_scene = world
	await physics_frame
	var wb: Node = world.find_child("WorldBounds", true, false)
	var a := Vector2(500, -100)
	var b := Vector2(500, -330)
	player.global_position = Vector3(a.x, float(wb.call("terrain_height", a.x, a.y)) + 1.0, a.y)
	player.get_node("Health").set("invulnerable", true)
	var zm: Node = root.get_node("ZoneManager")
	for i in 900:
		await physics_frame
		if i > 120 and int(zm.call("streaming_pending_now")) == 0:
			break
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	if control:
		ed.set("search_phase", false)
	var pid: String = player.get("character_info").get("character_id")
	ws.call("set_stars_now", pid, stars, false)
	# 1. the police arrive and have the player in sight
	var seen_at := -1
	for i in 60 * 60:
		await physics_frame
		if i % 60 == 0:
			ws.call("set_stars_now", pid, stars, false)      # held until they are here (the calm clock must not win)
		if i % 15 == 0 and _police_near(ed, player.global_position) < 40.0 \
				and str(ed.call("sight_now", pid)).contains("lost=false lost_for=0.0"):
			seen_at = i
			break
	check("police arrive and have the player in sight", seen_at >= 0, "after %.0f s; %s" % [seen_at / 60.0, ed.call("sight_now", pid)])
	if bool(_arg("hide", false)):
		await _hide(player, wb, ws, ed, pid)
		return
	# 2. gone: 230 m away, out of every unit's reach
	player.global_position = Vector3(b.x, float(wb.call("terrain_height", b.x, b.y)) + 1.0, b.y)
	var mc := player.get_node_or_null("MovementController")
	if mc != null and mc.has_method("clear_motion"):
		mc.call("clear_motion")
	var lost_at := -1
	var area := ""
	var nearest := 1e9
	var cleared_at := -1
	for i in 60 * 75:
		await physics_frame
		if i % 15 != 0:
			continue
		if lost_at < 0 and str(ed.call("sight_now", pid)).contains("lost=true"):
			lost_at = i
			area = str(ed.call("search_area_now", pid))
		if i > 120:
			nearest = minf(nearest, _police_near(ed, player.global_position))
		if cleared_at < 0 and int(ws.call("stars_now", pid)) == 0:
			cleared_at = i
		if i % 600 == 0:
			print("    t=%2.0f s  stars %d  %s  units %s  nearest police %.0f m" % [i / 60.0, int(ws.call("stars_now", pid)),
				ed.call("sight_now", pid), ed.call("units_now"), _police_near(ed, player.global_position)])
	if control:
		check("CONTROL (no search phase): the stars are still there after 75 s", int(ws.call("stars_now", pid)) > 0,
			"stars %d, nearest police came to %.0f m" % [int(ws.call("stars_now", pid)), nearest])
	else:
		check("the police LOSE a player who is gone", lost_at >= 0 and lost_at <= 60 * 6, "after %.1f s" % (lost_at / 60.0))
		check("the minimap is given the search disc (x, z, radius)", area.split(",").size() == 3, area)
		check("no unit turns up where the player went (they search the last known place)", nearest > 60.0,
			"nearest police body came to %.0f m" % nearest)
		check("the stars drain to nothing after the calm period", cleared_at >= 0, "after %.0f s" % (cleared_at / 60.0))
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
