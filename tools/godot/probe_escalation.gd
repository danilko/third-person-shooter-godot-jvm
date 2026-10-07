extends SceneTree
## THE ENFORCEMENT ESCALATION (PLAN.md W6, user 2026-10-06: heavier units as the stars rise; vehicles that RAM;
## a light tank / tank with a main gun; snipers; light bars and sirens).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_escalation.gd [-- --stars=6] [--control]
##   (--control: 2 stars -- none of the escalation may appear)
##
## World.tscn, the player invulnerable at the safe house, held at N lethal stars for up to 120 s. Asserted at 6 stars:
##   1. an armoured model (ARV1 / LTK1 / TNK1) is dispatched;
##   2. a car RAMS (drives straight at the player, not stopping to unload);
##   3. a main gun fires a shell;
##   4. a sniper is placed;
##   5. a dispatched police vehicle's light bar flashes (lit at some samples, dark at others).

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var stars := 2 if control else 6
	for a in args:
		if a.begins_with("--stars="):
			stars = int(a.substr(8))
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	var pz := world.get_node_or_null("PedZones")
	if pz != null:
		world.remove_child(pz)
		pz.free()
	root.add_child(world)
	current_scene = world
	for i in 240:
		await physics_frame
	var player: Node3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node("WantedSystem")
	var ed: Node = gm.get_node("EnforcementDispatch")
	var pid: String = player.get("character_info").get("character_id")
	var armour := false
	var rammed := false
	var shells := 0
	var snipers := 0
	var lit := 0
	var dark := 0
	var t0 := Time.get_ticks_msec()
	var last := ""
	while Time.get_ticks_msec() - t0 < (40000 if control else 120000):
		ws.call("set_stars_now", pid, stars, true)
		await physics_frame
		if Engine.get_physics_frames() % 15 != 0:
			continue
		var e := String(ed.call("escalation_now")).split(";")
		last = String(ed.call("escalation_now"))
		for m in e[0].split(" "):
			if m in ["ARV1", "LTK1", "TNK1"]:
				armour = true
		rammed = rammed or int(e[1]) > 0
		shells = maxi(shells, int(e[2]))
		snipers = maxi(snipers, int(e[3]))
		for n in get_nodes_in_group("characters"):
			if n is RigidBody3D and n.has_method("emergency_now") and bool(n.call("emergency_now")):
				if bool(n.call("bar_lit_now")):
					lit += 1
				else:
					dark += 1
		if not control and armour and rammed and shells > 0 and snipers > 0 and lit > 0 and dark > 0:
			break
	print("probe_escalation: %d stars, last readout '%s'" % [stars, last])
	if control:
		_check(not armour, "no armour at %d stars" % stars)
		_check(not rammed, "no ramming at %d stars" % stars)
		_check(shells == 0, "no main gun at %d stars" % stars)
		_check(snipers == 0, "no sniper at %d stars" % stars)
	else:
		_check(armour, "an armoured vehicle is dispatched (ARV1 / LTK1 / TNK1)")
		_check(rammed, "a car RAMS the player")
		_check(shells > 0, "a main gun fired (%d shells)" % shells)
		_check(snipers > 0, "a sniper is placed (%d)" % snipers)
		_check(lit > 0 and dark > 0, "a police vehicle's light bar flashes (lit %d, dark %d samples)" % [lit, dark])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
