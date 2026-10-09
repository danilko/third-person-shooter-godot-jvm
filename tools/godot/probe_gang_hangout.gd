extends SceneTree
## GANG HANGOUTS (PLAN.md THE ORDER 0.1 / H1): gang members in front of their gang's places, neutral until provoked.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_gang_hangout.gd [-- --control]
##   (--control: GangHangouts.enabled off -- nobody stands there, so nothing can be provoked)
##
## World.tscn, the player 200 m from gang_a's Gang Office, then 30 m from its door. Asserted:
##   1. nobody stands there while the player is far;
##   2. members appear in front of the door when the player comes near, in gang_a;
##   3. they leave a player with no standing alone (no damage over 8 s, standing 0);
##   4. one hit on a member (hit_member) is a star, and the members then shoot the player;
##   5. when the player leaves past `far`, the living members are taken away.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const DOOR := Vector3(580.0, 5.75, -340.56)
const OUT := Vector3(1, 0, 0)

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _place(player: Node3D, wb: Node, p: Vector3) -> void:
	var y := p.y
	if wb != null:
		y = float(wb.call("terrain_height", p.x, p.z)) + 1.0
	player.global_position = Vector3(p.x, y, p.z)
	player.velocity = Vector3.ZERO


func _wait(seconds: float) -> void:
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < seconds * 1000.0:
		await physics_frame


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
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
	var gm: Node = root.get_node("GameManager")
	var gh: Node = gm.get_node("GangHangouts")
	var gs: Node = gm.get_node("GangSystem")
	gh.set("enabled", not control)
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	health.call("apply_replicated_health", 1000000.0)
	var pid: String = player.get("character_info").get("character_id")
	var zm: Node = root.get_node_or_null("ZoneManager")

	_place(player, wb, DOOR + OUT * 200.0)
	await _wait(6.0)
	_check(gh.call("members_near", DOOR).size() == 0, "nobody stands at the office while the player is 200 m away")

	_place(player, wb, DOOR + OUT * 30.0)
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 20000:
		await physics_frame
		if zm != null and int(zm.call("streaming_pending_now")) == 0 and gh.call("members_near", DOOR).size() > 0:
			break
	await _wait(2.0)
	var members: Array = gh.call("members_near", DOOR)
	var in_gang := 0
	var near_door := 0
	for m in members:
		if String(m.get("character_info").get("faction")) == "gang_a":
			in_gang += 1
		if Vector2(m.global_position.x - DOOR.x, m.global_position.z - DOOR.z).length() < 14.0:
			near_door += 1
	print("  hangouts %s, members %d (gang_a %d, within 14 m of the door %d)" % [gh.call("hangouts_now"), members.size(), in_gang, near_door])
	_check(members.size() >= 3 and in_gang == members.size(), "members stand at the office, all gang_a")
	_check(near_door >= 3, "they stand in front of its door")

	var h0 := float(health.call("health_now"))
	await _wait(8.0)
	var lost := h0 - float(health.call("health_now"))
	_check(lost <= 0.0 and int(gs.call("gang_stars_now", pid, "gang_a")) == 0,
			"a player with no standing is left alone (lost %.0f, standing %d)" % [lost, int(gs.call("gang_stars_now", pid, "gang_a"))])

	gs.call("report_now", "gang_a", "hit_member", pid)
	var stars := int(gs.call("gang_stars_now", pid, "gang_a"))
	h0 = float(health.call("health_now"))
	t0 = Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 20000 and float(health.call("health_now")) >= h0:
		await physics_frame
	lost = h0 - float(health.call("health_now"))
	_check(stars >= 1 and lost > 0.0, "one hit is %d star(s) and the members shoot (lost %.0f in %.1f s)" % [
			stars, lost, (Time.get_ticks_msec() - t0) / 1000.0])

	gs.call("set_gang_stars_now", pid, "gang_a", 0)
	_place(player, wb, DOOR + OUT * 400.0)
	await _wait(4.0)
	_check(gh.call("members_near", DOOR).size() == 0, "they are taken away once the player has left")

	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
