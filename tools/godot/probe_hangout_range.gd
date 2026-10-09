extends SceneTree
## Gang hangout members shooting a provoked player at a distance (the "only hits when very close" report): the player
## stands --dist m from gang_a's Gang Office door, one hit_member makes the gang hostile, then every 5 s: health lost,
## each member's weapon, distance and shots fired.
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_hangout_range.gd [-- --dist=25] [--seconds=40]
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const DOOR := Vector3(580.0, 5.75, -340.56)

func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def

func _initialize() -> void:
	var dist := float(_arg("dist", "25"))
	var seconds := float(_arg("seconds", "40"))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	for n in ["PedZones", "TrafficZones"]:
		var h := world.get_node_or_null(n)
		if h != null:
			world.remove_child(h)
			h.free()
	var player: Node3D = world.get_node("Characters/Player")
	root.add_child(world)
	current_scene = world
	await physics_frame
	var wb: Node = world.find_child("WorldBounds", true, false)
	var p := DOOR + Vector3(dist, 0, 0)
	player.global_position = Vector3(p.x, float(wb.call("terrain_height", p.x, p.z)) + 1.0, p.z)
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	health.call("apply_replicated_health", 1000000.0)
	var zm: Node = root.get_node_or_null("ZoneManager")
	var gm: Node = root.get_node("GameManager")
	var gh: Node = gm.get_node("GangHangouts")
	for i in 1200:
		await physics_frame
		if i > 120 and zm != null and int(zm.call("streaming_pending_now")) == 0 and gh.call("members_near", DOOR).size() > 0:
			break
	await physics_frame
	var pid: String = player.get("character_info").get("character_id")
	gm.get_node("GangSystem").call("report_now", "gang_a", "hit_member", pid)
	var members: Array = gh.call("members_near", DOOR)
	var shots0 := {}
	var t0 := Time.get_ticks_msec()
	var next := 5.0
	var h0 := float(health.call("health_now"))
	while (Time.get_ticks_msec() - t0) / 1000.0 < seconds:
		await physics_frame
		var t := (Time.get_ticks_msec() - t0) / 1000.0
		if t < next:
			continue
		next += 2.0
		var h := float(health.call("health_now"))
		var rows := []
		for m in members:
			if not is_instance_valid(m):
				continue
			var wc: Node = m.get_node("WeaponController")
			var n: int = int(wc.call("shots_fired_now"))
			var k: int = m.get_instance_id()
			var w = wc.get("current_weapon_id") if false else ""
			var dd: float = Vector2(m.global_position.x - player.global_position.x, m.global_position.z - player.global_position.z).length()
			var st := "-"
			for c in m.get_children():
				if c.has_method("current_state_name_now"):
					st = String(c.call("current_state_name_now"))
			var cur = wc.call("get_current_weapon_id_now") if wc.has_method("get_current_weapon_id_now") else ""
			rows.append("%.0fm fired %d %s %s v%.1f toward %.2f at %s" % [dd, n - int(shots0.get(k, 0)), st, cur, m.velocity.length(),
					Vector2(m.velocity.x, m.velocity.z).normalized().dot(Vector2(player.global_position.x - m.global_position.x, player.global_position.z - m.global_position.z).normalized()),
					m.global_position.snapped(Vector3(0.1, 0.1, 0.1))])
			shots0[k] = n
		print("t=%3.0f lost %5.0f player %s | %s" % [t, h0 - h, player.global_position.snapped(Vector3(0.1, 0.1, 0.1)), ", ".join(rows)])
		h0 = h
	print("weapons: %s" % gm.get_node("EnforcementDispatch").call("unit_weapons_now", "gang_a"))
	quit(0)
