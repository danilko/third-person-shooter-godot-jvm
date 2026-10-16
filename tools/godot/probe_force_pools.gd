extends SceneTree
## FORCES HELD PER STATION, AND THE RESTRICTED AREAS (PLAN.md P1e step 3; game.ForcePools, game/forces.json,
## game.RestrictedAreas, ui.AreaWarning).
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_force_pools.gd [-- --control]
##   --control: force pools OFF (every side unlimited, as before step 3) -- case 3 then still sends units.
##
## World.tscn, the player invulnerable at the safe house:
##   1. the island's places became stations: police (14 koban + 2 stations + the air base) and both gangs;
##   2. three stars for 30 s: units are drawn (the police's on-hand count falls); a unit killed is LOST to its station,
##      and once the stars are cleared and the living walk off, they are back on hand (on hand = full - lost);
##   3. every police station emptied, three stars again: nobody comes for 20 s and the police rest ("no units");
##   4. the player set down inside the air base's fence: the area warning shows at once, and after warn_seconds the
##      trespass makes them wanted at four stars or more.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _pool(ed: Node, side: String) -> PackedInt32Array:
	var p := String(ed.call("pool_of_now", side)).split(",")
	return PackedInt32Array([int(p[0]), int(p[1])])


func _warning() -> Node:
	for n in root.find_children("*", "Control", true, false):
		if n.has_method("restricted_shown"):
			return n
	return null


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var pz := world.get_node_or_null("PedZones")
	if pz != null:
		world.remove_child(pz)
		pz.free()
	root.add_child(world)
	current_scene = world
	await _tick(240)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	if control:
		ed.set("force_pools", false)
	var player: Node3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	var pid: String = player.get("character_info").get("character_id")
	var home := player.global_position

	# 1. stations
	print(String(ed.call("pools_now")))
	var police := _pool(ed, "police")
	_check(police[1] >= 14 * 4 + 2 * 18, "the police stations are bound (%d bodies when full)" % police[1])
	_check(_pool(ed, "gang_a")[1] > 0 and _pool(ed, "gang_b")[1] > 0, "both gangs hold bodies at their own places")

	# 2. draw, lose one, the living go back
	var t := 0.0
	var killed := false
	while t < 30.0:
		ws.call("set_stars_now", pid, 3, false)
		await _tick(30)
		t += 0.5
		var bodies: Array = ed.call("bodies_now", "police")
		if not killed and t > 12.0 and bodies.size() > 0:
			helper.call("kill", bodies[0])
			killed = true
	var mid := _pool(ed, "police")
	print("  3 stars for 30 s: police on hand %d of %d, units %s" % [mid[0], mid[1], String(ed.call("units_now"))])
	if not control:
		_check(mid[0] < mid[1], "units were drawn from the stations (%d < %d)" % [mid[0], mid[1]])
	ws.call("clear_now", pid)
	t = 0.0
	while t < 90.0:
		await _tick(60)
		t += 1.0
		var u := String(ed.call("units_now")).split(",")
		if int(u[0]) == 0 and int(u[1]) == 0 and int(u[2]) == 0:
			break
	var after := _pool(ed, "police")
	print("  stood down after %.0f s: on hand %d of %d (%s)" % [t, after[0], after[1], String(ed.call("pools_now")).replace("\n", " | ")])
	if not control:
		_check(killed and after[0] < after[1], "the killed unit is LOST to its station (%d < %d)" % [after[0], after[1]])
		_check(after[0] > mid[0], "the living walked off and are back on hand (%d > %d)" % [after[0], mid[0]])

	# 3. every station emptied
	ed.call("drain_pool_now", "police")
	var came := 0
	t = 0.0
	while t < 20.0:
		ws.call("set_stars_now", pid, 3, false)
		await _tick(30)
		t += 0.5
		var u := String(ed.call("units_now")).split(",")
		came = maxi(came, int(u[0]) + int(u[1]))
	var report := String(ed.call("pools_now"))
	print("  all police stations empty, 3 stars for 20 s: %d units at most | %s" % [came, report.replace("\n", " | ")])
	if control:
		_check(came > 0, "control: unlimited, units still come (%d)" % came)
	else:
		_check(came == 0, "nobody comes while every station is empty (%d)" % came)
		_check(report.contains("empty-ladder lulls") and not report.ends_with("lulls 0"), "the police rest (no units available)")
	ws.call("clear_now", pid)
	await _tick(60)

	# 4. the restricted area
	var wb: Node = world.get_node_or_null("WorldBounds")
	var at := Vector3(-617.5, 0, 1262.0)
	at.y = (float(wb.call("terrain_height", at.x, at.z)) if wb != null else 6.0) + 1.0
	player.global_position = at
	var mc := player.get_node_or_null("MovementController")
	if mc != null and mc.has_method("clear_motion"):
		mc.call("clear_motion")
	await _tick(30)
	var warn := _warning()
	var shown_early := warn != null and bool(warn.call("restricted_shown"))
	var stars_early := int(ws.call("stars_now", pid))
	_check(shown_early, "inside the air base's fence: the RESTRICTED AREA warning shows")
	_check(stars_early == 0, "a warning first, not a crime (%d stars at 0.5 s)" % stars_early)
	var stars := 0
	t = 0.0
	while t < 12.0:
		player.global_position = at
		await _tick(30)
		t += 0.5
		stars = int(ws.call("stars_now", pid))
		if stars >= 4:
			break
	print("  in the air base for %.1f s: %d stars, %s" % [t, stars, String(ed.call("trespass_now", pid))])
	_check(stars >= 4 and t >= 7.0, "staying after the warning is a trespass: %d stars after %.1f s" % [stars, t])
	ws.call("clear_now", pid)
	player.global_position = home
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
