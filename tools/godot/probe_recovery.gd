extends SceneTree
## WHERE A PLAYER WHO GOES DOWN WAKES, AND WHAT IT COSTS (user, 2026-10-06; game.RecoveryRules, RespawnSystem,
## GangSystem captivity, EnforcementDispatch guards).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_recovery.gd [-- --world=island]
##
##   1. down with no standing: 入院 HOSPITALIZED, the hospital fee taken;
##   2. down while the police want them (2 stars): 逮捕 ARRESTED -- jail, not hospital -- and (hospital + police) x 2;
##   3. down with a gang standing (gang_a 2 stars), police stars too: 拉致 ABDUCTED wins, no fee at waking, held with
##      guards over them and the ransom prompt; paying the ransom frees them, clears the standing and stands the guards
##      down;
##   4. abducted again and they RUN: past escape_start they are escaping (the gang turns hostile, the escape heat
##      added), past escape_free they are free.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0
var world: Node
var helper: Node
var gm: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _player() -> CharacterBody3D:
	var rs: Node = gm.get_node("RespawnSystem")
	var p = rs.call("respawned_player_now")
	if p != null and is_instance_valid(p):
		return p
	return world.get_node_or_null("Characters/Player")

func _pid(p: Node) -> String:
	return p.get("character_info").get("character_id")

## kill the player and wait for the new body; returns [card text seen, the new player]
func _go_down(p: CharacterBody3D) -> Array:
	var rs: Node = gm.get_node("RespawnSystem")
	var before := int(rs.call("respawns_now"))
	helper.call("kill", p)
	var card := ""
	for i in 60 * 10:
		await physics_frame
		var c := String(rs.call("card_text_now"))
		if c != "":
			card = c
		if int(rs.call("respawns_now")) > before:
			break
	await _tick(30)
	return [card, _player()]

func _move(p: CharacterBody3D, to: Vector3) -> void:
	p.global_position = to
	p.velocity = Vector3.ZERO
	var mc := p.get_node_or_null("MovementController")
	if mc != null:
		mc.call("clear_motion")

func _initialize() -> void:
	var island := "--world=island" in OS.get_cmdline_user_args()
	world = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(180)
	gm = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var gs: Node = gm.get_node("GangSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var fm: Node = root.get_node("FactionManager")
	ed.set("enabled", false)          # the dispatch's own units are probe_enforcement's; only the guards here
	for pair in [["police", "enemy"], ["enemy", "police"], ["gang_a", "enemy"], ["enemy", "gang_a"]]:
		fm.call("flip_relationship", pair[0], pair[1], "NEUTRAL")
	helper = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	var p := _player()

	# 1. hospital
	p.call("give_cash_now", 100000)
	var r := await _go_down(p)
	p = r[1]
	print("  1: card '%s', cash %d" % [String(r[0]).replace("\n", " "), int(p.call("cash_now"))])
	_check(String(r[0]).begins_with("入院"), "no standing: 入院 HOSPITALIZED")
	_check(int(p.call("cash_now")) == 95000, "the hospital fee was taken and the rest carried over (%d)" % int(p.call("cash_now")))

	# 2. jail, even on a death
	ws.call("set_stars_now", _pid(p), 2, false)
	r = await _go_down(p)
	p = r[1]
	print("  2: card '%s', cash %d" % [String(r[0]).replace("\n", " "), int(p.call("cash_now"))])
	_check(String(r[0]).begins_with("逮捕"), "down while wanted: 逮捕 ARRESTED")
	_check(int(p.call("cash_now")) == 95000 - 30000, "(hospital + police) x 2 stars was taken (%d)" % int(p.call("cash_now")))
	_check(int(ws.call("stars_now", _pid(p))) == 0, "the wanted level is cleared")

	# 3. abducted (a gang outranks the police), then pay
	ws.call("set_stars_now", _pid(p), 3, false)
	gs.call("set_gang_stars_now", _pid(p), "gang_a", 2)
	var cash_before := int(p.call("cash_now"))
	r = await _go_down(p)
	p = r[1]
	var pid := _pid(p)
	var rs: Node = gm.get_node("RespawnSystem")
	await _tick(30)
	print("  3: card '%s', ransom %d, guards %d, prompt '%s'" % [String(r[0]).replace("\n", " "), int(gs.call("ransom_now", pid)),
			int(ed.call("guards_now")), String(rs.call("captive_prompt_now")).replace("\n", " ")])
	_check(String(r[0]).begins_with("拉致"), "a gang standing wins: 拉致 ABDUCTED")
	_check(bool(gs.call("captive_now", pid)), "the player is held")
	_check(int(gs.call("ransom_now", pid)) == 200000, "the ransom is 2 stars x 100,000 (%d)" % int(gs.call("ransom_now", pid)))
	_check(int(p.call("cash_now")) == cash_before, "waking up held costs nothing yet")
	_check(int(ed.call("guards_now")) >= 2, "guards stand over them (%d)" % int(ed.call("guards_now")))
	_check(String(rs.call("captive_prompt_now")).find("ransom") >= 0, "the ransom prompt is up")
	_check(not bool(fm.call("hostile_now", "gang_a", "player")), "the guards do not shoot a captive who stays")
	_check(not bool(gs.call("pay_ransom_now", p)), "too little cash: no release")
	p.call("give_cash_now", 300000)
	var c0 := int(p.call("cash_now"))
	_check(bool(gs.call("pay_ransom_now", p)), "paying the ransom")
	await _tick(60)
	_check(not bool(gs.call("captive_now", pid)) and int(gs.call("gang_stars_now", pid, "gang_a")) == 0,
			"released, and the standing with gang_a cleared")
	_check(int(p.call("cash_now")) == c0 - 200000, "the ransom came out of their cash")
	_check(int(ed.call("guards_now")) == 0, "the guards stood down")

	# 4. abducted again, and they run
	gs.call("set_gang_stars_now", pid, "gang_a", 1)
	r = await _go_down(p)
	p = r[1]
	await _tick(30)
	var held_at: Vector3 = p.global_position
	_check(bool(gs.call("captive_now", pid)), "held again")
	_move(p, held_at + Vector3(25, 0, 0))
	await _tick(60)
	_check(bool(gs.call("escaping_now", pid)), "past escape_start they are escaping")
	_check(bool(fm.call("hostile_now", "gang_a", "player")), "the gang is hostile now")
	_check(int(gs.call("gang_stars_now", pid, "gang_a")) >= 2, "the escape added heat (%d stars)" % int(gs.call("gang_stars_now", pid, "gang_a")))
	_move(p, held_at + Vector3(120, 0, 0))
	await _tick(60)
	_check(not bool(gs.call("captive_now", pid)), "past escape_free they are free")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
