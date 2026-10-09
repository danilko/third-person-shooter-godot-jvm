extends SceneTree
## "AI only hits the player when very close" (user, 2026-10-09): police at N stars on the island, the player standing
## still downtown with huge health. Every 5 s: health lost, and the distance + state of every unit. Shots counted
## from the units' own weapon counters (shots fired) so "fires but misses" and "never fires" are told apart.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_ai_range_hits.gd [-- --stars=3] [--no-think]
##       [--seconds=90] [--at=x,z]

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"


func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a == "--" + name:
			return true
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def


func _initialize() -> void:
	var stars := int(_arg("stars", "3"))
	var seconds := float(_arg("seconds", "90"))
	var at := Vector2(500, -100)
	if _arg("at") != null:
		var s := String(_arg("at")).split(",")
		at = Vector2(float(s[0]), float(s[1]))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var player: Node3D = world.get_node("Characters/Player")
	root.add_child(world)
	current_scene = world
	await physics_frame
	var wb: Node = world.find_child("WorldBounds", true, false)
	player.global_position = Vector3(at.x, float(wb.call("terrain_height", at.x, at.y)) + 1.0, at.y)
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	health.call("apply_replicated_health", 1000000.0)
	var zm: Node = root.get_node_or_null("ZoneManager")
	for i in 900:
		await physics_frame
		if i > 120 and zm != null and int(zm.call("streaming_pending_now")) == 0:
			break
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	ed.call("set_think_budget_now", not bool(_arg("no-think", false)))
	var pid: String = player.get("character_info").get("character_id")
	print("stars %d, think budget %s" % [stars, not bool(_arg("no-think", false))])
	var t0 := Time.get_ticks_msec()
	var next := 5.0
	var h0 := float(health.call("health_now"))
	var total := 0.0
	var shots0 := {}
	while (Time.get_ticks_msec() - t0) / 1000.0 < seconds:
		ws.call("set_stars_now", pid, stars, true)
		await physics_frame
		var t := (Time.get_ticks_msec() - t0) / 1000.0
		if t < next:
			continue
		next += 5.0
		var h := float(health.call("health_now"))
		var lost := h0 - h
		total += lost
		h0 = h
		var rows := []
		var fired := 0
		for b in ed.call("bodies_now", "police"):
			var wc: Node = b.get_node_or_null("WeaponController")
			var n := 0
			if wc != null and wc.has_method("shots_fired_now"):
				n = int(wc.call("shots_fired_now"))
			var key: int = b.get_instance_id()
			fired += n - int(shots0.get(key, n))
			shots0[key] = n
			var d: float = Vector2(b.global_position.x - player.global_position.x, b.global_position.z - player.global_position.z).length()
			var st := "?"
			var ai: Node = b.get_node_or_null("AIController")
			if ai != null and ai.has_method("current_state_name_now"):
				st = String(ai.call("current_state_name_now"))
			rows.append("%.0fm %s" % [d, st])
		rows.sort()
		print("t=%3.0f lost %6.0f  fired %3d  units: %s" % [t, lost, fired, ", ".join(rows)])
	print("TOTAL lost %.0f in %.0f s" % [total, seconds])
	quit(0)
