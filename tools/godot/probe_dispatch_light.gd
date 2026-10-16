extends SceneTree
## THE DISPATCH AS A USER OF THE LIGHT TIER (PLAN.md 2.3 follow-up): at high stars the dispatch sends LIGHT combatants
## (ai.light) round the player beyond its full complement (crimes.json / gangs.json light_by_stars), and every foot
## unit the global body cap refuses is sent light too; they are drawn from the station pools and taken back when the
## standing no longer calls for them.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_dispatch_light.gd [-- --control]
##   (--control: EnforcementDispatch.lightReserve off -- no light unit may appear)
##
## World.tscn, the player invulnerable at the safe house.
##   A. 45 s at 5 lethal stars: light units are sent (>= half of light_by_stars[5]); some are promoted to full bodies
##      as they close in; the dispatched full bodies stay under the body cap.
##   B. the stars cleared: every light unit is taken back within 10 s (returned to its station, not lost).
##   C. the body cap forced to 2 at 3 stars (light_by_stars[3] = 0) for 30 s: the refused foot units are sent light.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"

var fails := 0


func _check(ok: bool, what: String, detail: String = "") -> void:
	print("  [%s] %-66s %s" % ["PASS" if ok else "FAIL", what, detail])
	if not ok:
		fails += 1


func _reserve(ed: Node) -> PackedInt32Array:
	var f := String(ed.call("light_reserve_now")).split(",")
	return PackedInt32Array([int(f[0]), int(f[1]), int(f[2]), int(f[3])])


func _promoted() -> int:
	for n in root.find_children("*", "Node", true, false):
		if n.has_method("promoted_readout_now"):
			var s := String(n.call("promoted_readout_now"))
			return 0 if s.is_empty() else s.split("|").size()
	return 0


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
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
	if control:
		ed.call("set_light_reserve_now", false)

	# A. five stars
	var most := 0
	var promoted := 0
	var over_cap := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 45000:
		ws.call("set_stars_now", pid, 5, true)
		await physics_frame
		if Engine.get_physics_frames() % 30 != 0:
			continue
		var r := _reserve(ed)
		most = maxi(most, r[0])
		promoted = maxi(promoted, _promoted())
		var bc := String(ed.call("body_cap_now")).split(",")
		if int(bc[1]) > 0 and int(bc[0]) > int(bc[1]):
			over_cap += 1
	var a := _reserve(ed)
	print("    A: most light units at once %d; sent %d lost %d released %d; promoted at once %d" % [most, a[1], a[2], a[3], promoted])
	if control:
		_check(most == 0 and a[1] == 0, "control: no light unit is sent", "%d sent" % a[1])
	else:
		_check(most >= 8, "5 stars: light units are sent round the player", "%d at once (light_by_stars[5] 16)" % most)
		_check(promoted > 0, "some are promoted to full bodies as they close in", "%d at once" % promoted)
	_check(over_cap == 0, "the dispatched full bodies stay under the body cap", "%d samples over" % over_cap)

	# B. cleared
	ws.call("clear_now", pid)
	var gone_at := -1.0
	var t1 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t1 < 10000:
		ws.call("clear_now", pid)
		await physics_frame
		if _reserve(ed)[0] == 0:
			gone_at = (Time.get_ticks_msec() - t1) / 1000.0
			break
	var b := _reserve(ed)
	if not control:
		_check(gone_at >= 0.0, "stars cleared: every light unit is taken back", "after %.1f s" % gone_at)
		_check(b[3] > 0 and b[3] >= b[1] - b[2] - b[0], "...returned to its station, not lost",
				"sent %d, lost %d, released %d" % [b[1], b[2], b[3]])

	# C. the cap refuses: the refused are sent light
	for i in 120:
		await physics_frame
	var sent0 := _reserve(ed)[1]
	ed.call("set_cap_and_merge_now", 2, 120.0)
	var most_c := 0
	var t2 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t2 < 30000:
		ws.call("set_stars_now", pid, 3, true)
		await physics_frame
		if Engine.get_physics_frames() % 30 == 0:
			most_c = maxi(most_c, _reserve(ed)[0])
	ed.call("set_cap_and_merge_now", -1, 120.0)
	var c := _reserve(ed)
	print("    C: cap 2 at 3 stars: most light %d, sent %d" % [most_c, c[1] - sent0])
	if control:
		_check(c[1] - sent0 == 0, "control: the cap's refusals are not sent light")
	else:
		_check(most_c >= 2, "cap 2 at 3 stars: the refused foot units are sent light", "%d at once" % most_c)
	ws.call("clear_now", pid)
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
