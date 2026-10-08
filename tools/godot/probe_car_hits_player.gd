extends SceneTree
## A CAR KILLS THE PLAYER (PLAN.md 1a, user 2026-10-08: "run over by a car during an engagement, stuck at health 0 --
## no card, no respawn"). A real Player stands on a bare stand; a driverless SPC-1 is driven at them at --speed until
## 6 m short, then coasts through. Asserted: the player is hurt to 0, the RespawnSystem answers within 12 s (a respawn,
## the card), and the new Player is alive. Run once with no stars (hospital) and once wanted (--stars=3, jail).
##
##   <godot> --headless --path . --script tools/godot/probe_car_hits_player.gd [-- --speed=25] [--stars=3] [--hp=1] [--gang=2] [--contact]
##   --hp=<n>: the player's health before the hit (default 1, so any hit kills)
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + k + "="):
			return a.substr(k.length() + 3)
	return d

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var speed := float(_arg("speed", "25"))
	var stars := int(_arg("stars", "0"))
	var hp := float(_arg("hp", "1"))
	var gang := int(_arg("gang", "0"))
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var ground := StaticBody3D.new()
	var gs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	gs.shape = box
	ground.add_child(gs)
	w.add_child(ground)
	ground.position = Vector3(0, -0.5, 0)
	var spawn := Marker3D.new()
	spawn.name = "PlayerSpawn"
	w.add_child(spawn)
	spawn.position = Vector3(30, 0.2, 0)
	var player: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	player.position = Vector3(0, 0.1, -20)
	w.add_child(player)
	for i in 30:
		await physics_frame
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node_or_null("WantedSystem")
	var rs: Node = gm.get_node_or_null("RespawnSystem")
	var pid: String = player.get("character_info").get("character_id")
	if stars > 0 and ws != null:
		ws.call("set_stars_now", pid, stars, false)
	var gsys: Node = gm.get_node_or_null("GangSystem")
	if gang > 0 and gsys != null:
		gsys.call("set_gang_stars_now", pid, "gang_a", gang)
	var health: Node = player.get_node("Health")
	health.call("apply_replicated_health", hp)
	print("  player %s hp %.0f stars %d" % [pid, float(health.call("health_now")), stars])
	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	w.add_child(car)
	car.global_position = Vector3(0, 0.9, 25)
	if "--contact" in OS.get_cmdline_user_args():
		car.set("knock_people", false)   # only the contact path (_integrate_forces) deals the hit
	for i in 60:
		await physics_frame
	var r0 := int(rs.call("respawns_now"))
	var died_at := -1
	var f := 0
	while f < 900:
		if is_instance_valid(car):
			var d := car.global_position.z - (-20.0)
			if d > 6.0:
				car.linear_velocity = Vector3(0, car.linear_velocity.y, -speed)
		var h := float(health.call("health_now")) if is_instance_valid(health) else -1.0
		if died_at < 0 and h <= 0.0:
			died_at = f
			print("  f%d the player is at 0 HP; at %s" % [f, player.global_position if is_instance_valid(player) else Vector3.ZERO])
		if int(rs.call("respawns_now")) > r0:
			break
		if f % 60 == 0:
			print("  f%d hp %.1f card '%s' player valid %s" % [f, h, String(rs.call("card_text_now")), is_instance_valid(player)])
		f += 1
		await physics_frame
	_check(died_at >= 0, "the car killed the player")
	_check(int(rs.call("respawns_now")) > r0, "the RespawnSystem respawned the player (%s)" % String(rs.call("last_reason_now")))
	var fresh: Node = rs.call("respawned_player_now")
	_check(fresh != null and is_instance_valid(fresh) and float(fresh.get_node("Health").call("health_now")) > 0.0,
			"the new Player is alive")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
