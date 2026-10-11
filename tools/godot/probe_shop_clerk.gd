extends SceneTree
## THE SHOP CLERK AND THE ROBBERY (PLAN.md W3/W5/W7, user 2026-10-03), on DebugWorld with a clerk spot and a counter
## built here (in the game they come from MARK_clerk / MARK_shop_counter in the shop's model).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_shop_clerk.gd
##
##   A. a clerk that SURRENDERS (surrender = 1): aiming at it is a crime (>= 1 star, not lethal), it crouches and
##      stays, the counter then offers the till; taking it pays the till and is LETHAL (police hostile to players,
##      no arrest offered);
##   B. a GRAY-AREA clerk that FIGHTS (surrender = 0, responders gang_a:2): it draws a weapon and turns hostile, two
##      gang members come out armed; once it is down the till is robbable; the robbery gives the same police stars as
##      an ordinary store, plus GANG stars (gang_a hostile to players);
##   C. clearing the police (a hospitalisation does it) calms the police but NOT the gang (a gang remembers); the
##      gang's heat holds above its pay threshold; paying the donation at the gray-area counter clears it.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const SPOT := "res://src/main/java/com/openworld/world/ShopClerkSpot.java"
const COUNTER := "res://src/main/java/com/openworld/item/ShopCounter.java"

var fails := 0
var world: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _setup(at: Vector3, surrender: float, responders: String) -> Array:
	var spot: Node3D = load(SPOT).new()
	spot.set("surrender", surrender)
	spot.set("responders", responders)
	world.add_child(spot)
	spot.global_position = at
	var counter: Area3D = load(COUNTER).new()
	counter.set("stock", "PIS1,onigiri")
	world.add_child(counter)
	counter.global_position = at + Vector3(0, 0, -1.5)
	await _tick(20)
	return [spot, counter]

func _gang_alive() -> int:
	var n := 0
	for c in world.get_node("Characters").get_children():
		var info = c.get("character_info")
		if info != null and String(info.get("faction")) == "gang_a":
			n += 1
	return n

func _initialize() -> void:
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var fm: Node = root.get_node("FactionManager")
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	var player: CharacterBody3D = world.get_node("Characters/Player")
	var pid: String = player.get("character_info").get("character_id")
	var at := player.global_position + Vector3(6, 0.2, 0)

	# A. surrender
	var a := await _setup(at, 1.0, "")
	var spot: Node3D = a[0]
	var counter: Area3D = a[1]
	_check(spot.call("clerk_now") != null, "the spot spawned a clerk")
	# fists (what a new player has) threaten from arm's reach: a punch cannot land over the counter, so squaring up
	# is the threat (user, 2026-10-11: "the robbery does not happen with normal melee")
	var reach := float(spot.call("threat_reach_now", player))
	_check(reach > 0.0 and reach <= 5.0, "what the player starts with (fists) threatens a clerk from close (%.1f m)" % reach)
	spot.call("threaten_now", player)
	await _tick(10)
	_check(int(spot.call("clerk_state_now")) == 1, "a surrender-1 clerk surrenders")
	_check(int(ws.call("stars_now", pid)) >= 1 and not bool(ws.call("lethal_now", pid)), "threatening a clerk is wanted, not lethal (%d)" % int(ws.call("stars_now", pid)))
	_check(bool(spot.call("robbable_now")), "a surrendered clerk's till can be taken")
	var cash0 := int(player.call("cash_now"))
	counter.call("grant_to_now", player, "till")
	await _tick(40)
	_check(int(player.call("cash_now")) > cash0, "taking the till pays (%d yen)" % (int(player.call("cash_now")) - cash0))
	_check(bool(ws.call("lethal_now", pid)) and int(ws.call("stars_now", pid)) >= 2, "a robbery is lethal (%d stars)" % int(ws.call("stars_now", pid)))
	_check(bool(fm.call("hostile_now", "police", "player")), "police are hostile to players while it lasts")
	var rs: Node = gm.get_node("RespawnSystem")
	_check(not bool(rs.call("arrest_now", player)), "no arrest is offered while lethal-wanted")
	_check(not bool(spot.call("robbable_now")), "a till is taken once")

	# B. gray area, fights back
	var b := await _setup(at + Vector3(20, 0, 0), 0.0, "gang_a:2:SMG1,SHG1")
	var spot2: Node3D = b[0]
	var clerk2: Node = spot2.call("clerk_now")
	spot2.call("threaten_now", player)
	await _tick(30)
	_check(int(spot2.call("clerk_state_now")) == 2, "a surrender-0 clerk fights back")
	_check(clerk2 != null and String(clerk2.get("character_info").get("faction")) == "vigilante", "the fighting clerk turns hostile")
	_check(_gang_alive() == 2, "two gang members come out (%d)" % _gang_alive())
	helper.call("kill", clerk2)
	await _tick(10)
	_check(bool(spot2.call("robbable_now")), "a downed clerk's till can be taken")
	var police_before := int(ws.call("stars_now", pid))
	b[1].call("grant_to_now", player, "till")
	await _tick(40)
	var gs: Node = gm.get_node("GangSystem")
	var gstars := int(gs.call("gang_stars_now", pid, "gang_a"))
	_check(gstars >= 2, "a gray-area robbery raises GANG stars (%d)" % gstars)
	_check(int(ws.call("stars_now", pid)) >= police_before, "and police stars as at any store (%d)" % int(ws.call("stars_now", pid)))
	_check(bool(fm.call("hostile_now", "gang_a", "player")), "the gang is hostile to players")
	_check(not bool(fm.call("hostile_now", "police", "gang_a")), "police and the gang do not fight each other")

	# C. police cleared, the gang remembers until paid
	ws.call("clear_now", pid)
	await _tick(60)
	_check(not bool(fm.call("hostile_now", "police", "player")), "cleared: police are not hostile")
	_check(bool(fm.call("hostile_now", "gang_a", "player")) and int(gs.call("gang_stars_now", pid, "gang_a")) == gstars,
			"the gang still is (a hospitalisation does not clear a gang)")
	var fee := int(gs.call("fee_now", pid, "gang_a"))
	player.call("give_cash_now", -int(player.call("cash_now")))
	b[1].call("grant_to_now", player, "donation")
	await _tick(5)
	_check(int(gs.call("gang_stars_now", pid, "gang_a")) == gstars, "no donation without the cash (fee %d yen)" % fee)
	player.call("give_cash_now", fee)
	b[1].call("grant_to_now", player, "donation")
	await _tick(60)
	_check(int(gs.call("gang_stars_now", pid, "gang_a")) == 0 and not bool(fm.call("hostile_now", "gang_a", "player")),
			"paying the donation clears the gang")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
