extends SceneTree
## H1 (PLAN.md THE ORDER 0.1): ESCALATION AS IT RUNS IN PLAY, not on a stand.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_escalation_play.gd \
##       [-- --stars=5] [--gang=4] [--hold] [--at=x,z] [--seconds=120] [--no-peds]
##
## The real World.tscn WITH its crowd and traffic (probe_escalation.gd removes PedZones and holds the stars every
## frame, which is not how play looks). The player is invulnerable downtown; the stars are set ONCE (--hold re-sets
## them every second, the stand's way) and the run then logs, every 5 s: the stars as the wanted system has them,
## units (foot / cars en route / arrived), the escalation readout, the weapons police and gang_a carry, every
## helicopter's height over the ground under it, and the enforcement load ZoneManager balances against.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"


func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a == "--" + name:
			return true
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def


func _ground_under(p: Vector3, skip: Array) -> float:
	var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, -2, 0), p + Vector3(0, -400, 0), 1)
	q.exclude = skip
	var hit := root.get_world_3d().direct_space_state.intersect_ray(q)
	return p.y - (hit.position.y as float) if not hit.is_empty() else -1.0


func _initialize() -> void:
	var stars := int(_arg("stars", "5"))
	var gang := int(_arg("gang", "0"))
	var hold := bool(_arg("hold", false))
	var seconds := float(_arg("seconds", "120"))
	var at := Vector2(500, -100)
	if _arg("at") != null:
		var s := String(_arg("at")).split(",")
		at = Vector2(float(s[0]), float(s[1]))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	if _arg("no-peds", false):
		var pz := world.get_node_or_null("PedZones")
		if pz != null:
			world.remove_child(pz)
			pz.free()
	var player: Node3D = world.get_node("Characters/Player")
	root.add_child(world)
	current_scene = world
	await physics_frame
	var wb: Node = world.find_child("WorldBounds", true, false)
	var gy := 6.0
	if wb != null and wb.has_method("terrain_height"):
		gy = float(wb.call("terrain_height", at.x, at.y)) + 1.0
	player.global_position = Vector3(at.x, gy, at.y)
	player.get_node("Health").set("invulnerable", true)
	var zm: Node = root.get_node_or_null("ZoneManager")
	for i in 900:
		await physics_frame
		if i > 120 and zm != null and int(zm.call("streaming_pending_now")) == 0:
			break
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var gs: Node = gm.get_node("GangSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var pid: String = player.get("character_info").get("character_id")
	print("player at %s, stars %d, gang_a %d, hold %s" % [player.global_position, stars, gang, hold])
	if stars > 0:
		ws.call("set_stars_now", pid, stars, true)
	if gang > 0:
		gs.call("set_gang_stars_now", pid, "gang_a", gang)
	var t0 := Time.get_ticks_msec()
	var next := 0.0
	var seen := {}
	var min_clear := 1e9
	var min_at := Vector3.ZERO
	while (Time.get_ticks_msec() - t0) / 1000.0 < seconds:
		await physics_frame
		var t := (Time.get_ticks_msec() - t0) / 1000.0
		if hold and int(t * 60) % 60 == 0:
			if stars > 0:
				ws.call("set_stars_now", pid, stars, true)
			if gang > 0:
				gs.call("set_gang_stars_now", pid, "gang_a", gang)
		if Engine.get_physics_frames() % 10 == 0:
			for n in get_nodes_in_group("characters"):
				if n is RigidBody3D and n.has_method("ai_flying_now") and bool(n.call("ai_flying_now")):
					var c := _ground_under(n.global_position, [n.get_rid()]) + 2.0
					if c > 0.0 and c < min_clear:
						min_clear = c
						min_at = n.global_position
		if t < next:
			continue
		next += 5.0
		var helis := []
		for n in get_nodes_in_group("characters"):
			if n is RigidBody3D and n.has_method("ai_flying_now") and bool(n.call("ai_flying_now")):
				helis.append("%.0fm over ground, %.0fm from player" % [
					_ground_under(n.global_position, [n.get_rid()]), n.global_position.distance_to(player.global_position)])
		var pol := String(ed.call("unit_weapons_now", "police"))
		var gw := String(ed.call("unit_weapons_now", "gang_a"))
		for wid in (pol + "," + gw).split(","):
			if wid != "":
				seen[wid] = true
		print("t=%3.0f stars %d gang %d | units %s | esc %s | police[%s] gang[%s] | helis %s" % [
			t, int(ws.call("stars_now", pid)), int(gs.call("gang_stars_now", pid, "gang_a")),
			ed.call("units_now"), ed.call("escalation_now"), pol, gw, helis])
	print("AI helicopter lowest clearance over the WORLD under it: %.1f m at %s" % [min_clear, min_at])
	print("weapons seen: %s" % ", ".join(seen.keys()))
	print("units detail: %s" % ed.call("debug_units_now"))
	quit(0)
