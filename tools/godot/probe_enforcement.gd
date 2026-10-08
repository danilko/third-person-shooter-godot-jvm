extends SceneTree
## THE ENFORCEMENT DISPATCH (PLAN.md W5; game.EnforcementDispatch): police and gang units come for a wanted player,
## and the ambient traffic budget shrinks while they are out.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_enforcement.gd [-- --world=island]
##   ... -- --control    (the dispatch off: stars still count, nobody comes, the budget does not move)
##
##   1. ONE star (not lethal): police officers appear on foot round the player and HUNT them down (user 2026-10-07:
##      no arrest by proximity) -- the police faction is hostile at one star, and the player, put down, wakes 逮捕
##      ARRESTED (RecoveryRules: police stars decide the outcome even on a death);
##   2. FOUR stars: more officers (and, where a lane qualifies, a patrol car), police are hostile, and they hurt the
##      player; the ambient traffic budget is reduced by the load;
##   3. the stars cleared: every unit leaves (freed once out of view and away);
##   4. gang_a at three stars: gang hunters appear and are hostile.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0
var world: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _units(ed: Node) -> PackedInt32Array:
	var p := String(ed.call("units_now")).split(",")
	return PackedInt32Array([int(p[0]), int(p[1]), int(p[2]), int(p[3])])

func _player() -> CharacterBody3D:
	for p in get_nodes_in_group("characters"):
		if p is CharacterBody3D and p.get_script() != null and String(p.get_script().resource_path).ends_with("Player.java"):
			return p
	return world.get_node_or_null("Characters/Player")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var island := "--world=island" in args
	world = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(240)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node_or_null("WantedSystem")
	var gs: Node = gm.get_node_or_null("GangSystem")
	var ed: Node = gm.get_node_or_null("EnforcementDispatch")
	var rs: Node = gm.get_node_or_null("RespawnSystem")
	var zm: Node = root.get_node("ZoneManager")
	var fm: Node = root.get_node("FactionManager")
	_check(ws != null and gs != null and ed != null and rs != null, "GameManager built the wanted, gang, dispatch and respawn systems")
	if ed == null:
		quit(1)
		return
	if control:
		ed.set("enabled", false)
	if "--no-think" in args:
		ed.call("set_think_budget_now", false)   # PLAN.md 1g d's control: every AI decides every tick
	# DebugWorld's zone AI are armed "enemy", hostile to every other faction: they shot the officers before they
	# reached anyone. Police and enemy are made neutral here, so what is measured is the dispatch.
	for pair in [["police", "enemy"], ["enemy", "police"]]:
		fm.call("flip_relationship", pair[0], pair[1], "NEUTRAL")
	var player := _player()
	var pid: String = player.get("character_info").get("character_id")
	var budget0 := int(zm.call("effective_traffic_budget_now"))
	print("  traffic budget at rest %d (alive %d)" % [budget0, int(zm.call("traffic_alive_now"))])

	# 1. one star: they hunt the player down; the player is mortal (a small health pool, so the fight is short) and,
	#    down while wanted, wakes arrested
	var street := player.global_position
	player.get_node("Health").set("max_health", 60.0)
	player.get_node("Health").call("apply_replicated_health", 60.0)
	ws.call("set_stars_now", pid, 1, false)
	var seen_foot := 0
	var hostile1 := false
	var weapons1 := {}
	var respawns0 := int(rs.call("respawns_now"))
	var t := 0.0
	while t < 90.0:
		await _tick(30)
		t += 0.5
		if int(rs.call("respawns_now")) == respawns0:
			ws.call("set_stars_now", pid, 1, false)   # hold the star until the player is down
		var u := _units(ed)
		seen_foot = max(seen_foot, u[0])
		for w in String(ed.call("unit_weapons_now", "police")).split(",", false):
			weapons1[w] = true
		hostile1 = hostile1 or bool(fm.call("hostile_now", "police", "player"))
		if int(t * 2) % 10 == 0:
			print("    t=%.1f player %s | %s" % [t, (str(player.global_position.round()) if is_instance_valid(player) else "gone"), String(ed.call("debug_units_now"))])
		if int(rs.call("respawns_now")) > respawns0:
			break
	var reason := String(rs.call("last_reason_now"))
	print("  1 star: peak foot units %d, hostile %s, respawn '%s', %.1f s" % [seen_foot, hostile1, reason, t])
	if control:
		_check(seen_foot == 0, "control: nobody came (%d)" % seen_foot)
	else:
		_check(seen_foot >= 1, "one star sends officers on foot (%d)" % seen_foot)
		_check(hostile1, "at one star police are already hostile (they hunt the player down)")
		_check(weapons1.size() == 1 and weapons1.has("BAT1"), "at one star police carry only the BAT1 baton (%s)" % [weapons1.keys()])
		_check(int(rs.call("respawns_now")) > respawns0 and reason == "ARRESTED", "the player, put down while wanted, woke ARRESTED (%s, %.1f s)" % [reason, t])
	await _tick(60 * 6)   # the arrest card and the respawn
	player = _player()
	pid = player.get("character_info").get("character_id")
	# back out on the street where it happened (the arrest put them in a cell, inside a police station)
	await _tick(60 * 4)
	player.global_position = street
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	ws.call("clear_now", pid)
	await _tick(60 * 3)

	# 2. four stars: a fight, and the ambient budget shrinks
	player.get_node("Health").set("invulnerable", false)
	player.get_node("Health").set("max_health", 100000.0)
	player.get_node("Health").call("apply_replicated_health", 100000.0)
	var hp1 := float(player.get_node("Health").call("health_now"))
	ws.call("set_stars_now", pid, 4, false)
	var peak := PackedInt32Array([0, 0, 0, 0])
	var weapons4 := {}
	var min_budget := budget0
	t = 0.0
	while t < 90.0:
		await _tick(30)
		t += 0.5
		ws.call("set_stars_now", pid, 4, false)   # hold the stars (the heat would otherwise drain)
		var u := _units(ed)
		for i in 3:
			peak[i] = max(peak[i], u[i])
		for w in String(ed.call("unit_weapons_now", "police")).split(",", false):
			weapons4[w] = true
		min_budget = min(min_budget, int(zm.call("effective_traffic_budget_now")))
		if int(t * 2) % 10 == 0:
			print("    4* t=%.1f player %s | %s" % [t, (str(player.global_position.round()) if is_instance_valid(player) else "gone"), String(ed.call("debug_units_now"))])
		var hurt_now := not is_instance_valid(player) or float(player.get_node("Health").call("health_now")) < hp1 - 10.0
		if t >= 25.0 and hurt_now and (peak[2] > 0 or not island or t >= 90.0):
			break
	var hostile := bool(fm.call("hostile_now", "police", "player"))
	var hurt := not is_instance_valid(player) or float(player.get_node("Health").call("health_now")) < hp1
	print("  4 stars: peak foot %d, cars en route %d, cars arrived %d; budget %d -> %d; %.1f s" % [peak[0], peak[1], peak[2], budget0, min_budget, t])
	if control:
		_check(peak[0] == 0 and peak[1] == 0, "control: no units at four stars")
		_check(min_budget == budget0, "control: the ambient budget does not move")
	else:
		_check(hostile, "at four stars police are hostile to players")
		_check(peak[0] >= 3, "four stars brings more officers (%d)" % peak[0])
		_check(hurt, "they fight: the player was hurt")
		_check(weapons4.has("SMG1") or weapons4.has("ASR2") or weapons4.has("SHG1"), "at four stars police carry firearms (%s)" % [weapons4.keys()])
		if island:
			_check(peak[2] >= 1, "a patrol car drove the road route to the player and its crew got out (%d)" % peak[2])
		_check(budget0 <= 0 or min_budget < budget0, "the ambient traffic budget shrank while they were out (%d -> %d)" % [budget0, min_budget])
	# 3. cleared: they leave
	if is_instance_valid(player):
		player.get_node("Health").set("invulnerable", true)
	player = _player()
	pid = player.get("character_info").get("character_id")
	ws.call("clear_now", pid)
	t = 0.0
	while t < 90.0:
		await _tick(30)
		t += 0.5
		var u := _units(ed)
		if u[0] + u[1] == 0:
			break
	var left := _units(ed)
	print("    left: %s" % String(ed.call("debug_units_now")))
	print("  cleared: %d foot, %d cars left after %.1f s; budget %d" % [left[0], left[1] + left[2], t, int(zm.call("effective_traffic_budget_now"))])
	if not control:
		# an ARRIVED patrol car stays parked where it stopped until it is out of view (a car never vanishes in front
		# of anyone), so only officers and cars still en route are asked to go
		_check(left[0] + left[1] == 0, "with the stars gone every officer left and no car is still coming (%.1f s; %d parked car(s) wait to be out of view)" % [t, left[2]])
		_check(not bool(fm.call("hostile_now", "police", "player")), "police are no longer hostile")

	# 4. a gang hunts
	gs.call("set_gang_stars_now", pid, "gang_a", 3)
	var gang_peak := 0
	t = 0.0
	while t < 20.0:
		await _tick(30)
		t += 0.5
		gs.call("set_gang_stars_now", pid, "gang_a", 3)
		gang_peak = max(gang_peak, (ed.call("bodies_now", "gang_a") as Array).size())
		if gang_peak >= 2:
			break
	print("  gang_a at 3 stars: %d hunters" % gang_peak)
	if control:
		_check(gang_peak == 0, "control: no hunters")
	else:
		_check(gang_peak >= 1, "gang_a hunters came (%d)" % gang_peak)
		_check(bool(fm.call("hostile_now", "gang_a", "player")), "gang_a is hostile to players")
		# PLAN.md 1g c: every unit wears its force's uniform (crimes.json / gangs.json bodies + outfits.json)
		var dressed := String(ed.call("dressed_now"))
		print("  dressed: %s" % dressed)
		_check(dressed.contains(":police="), "officers wear the police uniform (%s)" % dressed)
		_check(dressed.contains(":gang_a="), "gang_a hunters wear gang_a colours (%s)" % dressed)
	gs.call("set_gang_stars_now", pid, "gang_a", 0)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
