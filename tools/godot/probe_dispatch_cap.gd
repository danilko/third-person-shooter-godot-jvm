extends SceneTree
## ONE INCIDENT FOR PLAYERS TOGETHER, AND ONE CEILING ON BODIES (PLAN.md P1e step 2; game.UnitSpawner.spawnFor,
## crimes.json dispatch body_cap / merge_radius, gangs.json hunters merge_radius).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_dispatch_cap.gd [-- --control]
##   --control: merge_radius 0 and no cap -- each player draws their own full complement (the old rule).
##
## DebugWorld, a SECOND Player body set 8 m from the first (both invulnerable), both at 3 police stars for 45 s:
##   1. the police round them stay near ONE 3-star complement (<= 12 with crews out of their cars), not two (17);
##   2. then a cap of 6 at 5 stars: the dispatched bodies (every side) never pass 6.
## The control prints the doubled count (case 1) and the uncapped count (case 2).

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(240)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var a: Node3D = world.get_node("Characters/Player")
	var b: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.get_node("Characters").add_child(b)
	b.global_position = a.global_position + Vector3(8, 0.3, 0)
	await _tick(30)
	for p in [a, b]:
		p.get_node("Health").set("invulnerable", true)
	var ida: String = a.get("character_info").get("character_id")
	var idb: String = b.get("character_info").get("character_id")
	_check(ida != idb and ida != "" and idb != "", "two players with their own ids")
	if control:
		ed.call("set_cap_and_merge_now", 0, 0.0)
	var cap_merge := String(ed.call("body_cap_now")).split(",")
	print("  dispatched,cap = %s" % String(ed.call("body_cap_now")))

	# 1. both at 3 stars, side by side
	var peak := 0
	var t := 0.0
	while t < 45.0:
		ws.call("set_stars_now", ida, 3, false)
		ws.call("set_stars_now", idb, 3, false)
		await _tick(30)
		t += 0.5
		var u := String(ed.call("units_now")).split(",")
		peak = maxi(peak, int(u[0]) + 2 * int(u[1]))
		if int(t * 2) % 20 == 0:
			print("    t=%.0f units %s bodies,cap %s" % [t, String(ed.call("units_now")), String(ed.call("body_cap_now"))])
	print("  two players at 3 stars: peak %d police bodies (on foot + 2 a car on its way)" % peak)
	# one 3-star complement: 4 on foot + 2 cars of 2 on their way, plus crews already out of their cars (they join
	# those on foot) -- at most ~12; two complements (the control) measured 17
	if control:
		_check(peak > 12, "control: each player drew their own complement (%d > 12)" % peak)
	else:
		_check(peak >= 3 and peak <= 12, "one complement for the pair (%d in 3..12)" % peak)
	ws.call("clear_now", ida)
	ws.call("clear_now", idb)
	await _tick(60)

	# 2. a low cap at 5 stars
	if not control:
		ed.call("set_cap_and_merge_now", 6, 120.0)
	var top := 0
	t = 0.0
	while t < 40.0:
		ws.call("set_stars_now", ida, 5, true)
		await _tick(30)
		t += 0.5
		top = maxi(top, int(String(ed.call("body_cap_now")).split(",")[0]))
	print("  5 stars with %s: at most %d dispatched bodies at once" % ["no cap" if control else "a cap of 6", top])
	if control:
		_check(top > 6, "control: past 6 with no cap (%d)" % top)
	else:
		_check(top >= 2 and top <= 6, "never past the cap (%d <= 6)" % top)
	ws.call("clear_now", ida)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
