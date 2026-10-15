extends SceneTree
## VEHICLE AMMO, ATTACK TOKENS AND THE REGROUP LULL (PLAN.md 1g b2/b3; item.AmmoSupply, game.EnforcementDispatch).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_ammo_supply.gd [-- --world=island] [-- --control]
##   --control: attack tokens, the dry retreat and the AI reserve rule OFF (everyone attacks; a dry unit fights on
##              with its fists; an AI's reload spends its reserve like a player's).
##
##   1. a police car carries spare ammunition at its rear; the PLAYER, standing there with an empty rifle, presses
##      interact and is full again, and the car's stock goes down by one;
##   2. three stars: never more units attacking at once than tokens_by_stars allows (the rest close in and hold);
##   3. every unit's ammo emptied: units walk back to the car's spare ammo (or leave), restock there, the squad's
##      regroup lull starts (no new unit sent for regroup_seconds), and units that restocked fight again;
##   4. (P1e step 1) while they fought in 2, the units RELOADED and their reserve stayed full (an AI's firearm never
##      spends its reserve); one unit killed drops a FINITE firearm (its magazine + 0..1 spare magazines).

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const POC1 := "res://src/main/resources/com/openworld/vehicle/POC1.tscn"

var fails := 0
var world: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _player() -> CharacterBody3D:
	for p in get_nodes_in_group("characters"):
		if p is CharacterBody3D and p.get_script() != null and String(p.get_script().resource_path).ends_with("Player.java"):
			return p
	return world.get_node_or_null("Characters/Player")

func _all(n: Node) -> Array:
	var out := [n]
	for c in n.get_children():
		out.append_array(_all(c))
	return out

func _dry(ed: Node) -> PackedInt32Array:
	var p := String(ed.call("dry_now")).split(",")
	return PackedInt32Array([int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4])])

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
	var ed: Node = gm.get_node_or_null("EnforcementDispatch")
	var fm: Node = root.get_node("FactionManager")
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	if control:
		ed.set("attack_tokens", false)
		ed.set("dry_retreat", false)
		ed.call("set_ai_ammo_rules_now", false, true)
	for pair in [["police", "enemy"], ["enemy", "police"]]:
		fm.call("flip_relationship", pair[0], pair[1], "NEUTRAL")
	var player := _player()
	var pid: String = player.get("character_info").get("character_id")
	player.get_node("Health").set("invulnerable", true)

	# 1. a parked police car's spare ammunition, used by the player
	var car: Node3D = (load(POC1) as PackedScene).instantiate()
	world.add_child(car)
	var at := player.global_position
	car.global_position = at + Vector3(8, 0.5, 0)
	await _tick(90)
	var sup: Node3D = car.get_node_or_null("AmmoSupply")
	_check(sup != null, "a police car carries spare ammunition (AmmoSupply)")
	if sup == null:
		quit(1)
		return
	var stock0 := int(sup.call("stock_now"))
	helper.call("give_weapon", player, "ASR1")
	await _tick(40)
	helper.call("drain_ammo", player)
	player.global_position = sup.global_position + Vector3(0, 0.1, 0)
	player.get_node("MovementController").call("clear_motion")
	await _tick(20)
	Input.action_press("interact")
	await _tick(2)
	Input.action_release("interact")
	await _tick(10)
	var rounds := int(helper.call("rounds_of", player))
	print("  player restock: %d rounds, car stock %d -> %d" % [rounds, stock0, int(sup.call("stock_now"))])
	_check(rounds >= 120, "the player pressed interact at the car's rear and the empty ASR1 is full (%d rounds)" % rounds)
	_check(int(sup.call("stock_now")) == stock0 - 1, "the car's stock went down by one")
	player.global_position = at
	player.get_node("MovementController").call("clear_motion")
	await _tick(30)

	# 2. three stars: attack tokens
	ws.call("set_stars_now", pid, 3, false)
	var tokens := 3
	var max_attack := 0
	var t := 0.0
	while t < 40.0:
		await _tick(30)
		t += 0.5
		ws.call("set_stars_now", pid, 3, false)
		max_attack = max(max_attack, int(ed.call("attackers_now", "police")))
		if t > 20.0 and int(String(ed.call("units_now")).split(",")[0]) >= 3:
			break
	var foot := int(String(ed.call("units_now")).split(",")[0])
	print("  3 stars: %d on foot, at most %d attacking at once (tokens %d), holds counted %d" % [foot, max_attack, tokens, _dry(ed)[4]])
	if control:
		_check(_dry(ed)[4] == 0, "control: no unit held back")
	else:
		_check(max_attack >= 1 and max_attack <= tokens, "never more than %d attacking at once (%d)" % [tokens, max_attack])
		_check(foot <= tokens or _dry(ed)[4] > 0, "units beyond the tokens were held back")

	# 4a. the AI reserve rule, read after the case-2 fight
	var am := String(ed.call("unit_ammo_now", "police")).split(",")
	print("  unit ammo after the fight: magazines %s reserve %s of %s, reloads %s" % [am[0], am[1], am[2], am[3]])
	if control:
		_check(int(am[3]) == 0 or int(am[1]) < int(am[2]), "control: a reload spent the reserve")
	else:
		_check(int(am[3]) >= 1, "the units reloaded while fighting (%s)" % am[3])
		_check(int(am[1]) == int(am[2]), "and their reserve stayed full (%s of %s)" % [am[1], am[2]])

	# 3. everyone dry
	var stock1 := int(sup.call("stock_now"))
	ed.call("drain_unit_ammo_now", "police")
	var foot_at_drain := foot
	var max_foot_in_lull := 0
	var saw_lull := 0.0
	t = 0.0
	while t < 40.0:
		await _tick(30)
		t += 0.5
		ws.call("set_stars_now", pid, 3, false)
		var lull := float(ed.call("lull_left_now", pid, "police"))
		saw_lull = max(saw_lull, lull)
		if lull > 0.0:
			max_foot_in_lull = max(max_foot_in_lull, int(String(ed.call("units_now")).split(",")[0]))
		if int(t * 2) % 8 == 0:
			print("    t=%.1f dry %s lull %.1f stock %d | %s" % [t, String(ed.call("dry_now")), lull, int(sup.call("stock_now")), String(ed.call("debug_units_now")).left(400)])
		if _dry(ed)[2] >= 1 and t > 12.0:
			break
	var d := _dry(ed)
	print("  dry: retreated %d, walked to a car %d, restocked %d, lulls %d; car stock %d -> %d; peak lull %.1f s" % [d[0], d[1], d[2], d[3], stock1, int(sup.call("stock_now")), saw_lull])
	if control:
		_check(d[0] + d[1] == 0, "control: a dry unit neither leaves nor walks to a car")
	else:
		_check(d[1] >= 1, "dry units walked back to the police car's spare ammo (%d)" % d[1])
		_check(d[2] >= 1 and int(sup.call("stock_now")) < stock1, "a unit restocked there and the car's stock went down")
		_check(d[3] >= 1 and saw_lull > 5.0, "the squad's regroup lull started (%.1f s)" % saw_lull)
		_check(max_foot_in_lull <= foot_at_drain, "no new unit was sent during the lull (%d <= %d)" % [max_foot_in_lull, foot_at_drain])
	# 4b. a unit killed drops a finite firearm
	var bodies: Array = ed.call("bodies_now", "police")
	if not control and bodies.size() > 0:
		var stamped0 := int(String(ed.call("ai_ammo_counts_now")).split(",")[2])
		var victim: Node = bodies[0]
		var mag_size := int(helper.call("largest_magazine_of", victim))
		helper.call("kill", victim)
		await _tick(30)
		var stamped := int(String(ed.call("ai_ammo_counts_now")).split(",")[2]) - stamped0
		var worst := -1
		for n in _all(root):
			if n.has_meta("dropped_at_ms") and n.get("reserve") != null:
				worst = max(worst, int(n.get("reserve")))
		print("  killed a unit: %d drops stamped, highest dropped reserve %d (largest magazine %d)" % [stamped, worst, mag_size])
		_check(stamped >= 1, "the dead unit's firearm was made finite as it dropped")
		_check(worst >= 0 and worst <= mag_size, "a dropped AI firearm keeps at most one spare magazine (%d <= %d)" % [worst, mag_size])
	ws.call("clear_now", pid)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
