extends SceneTree
## A PLACED FIGHT (PLAN.md 2.2 / F6): game.encounter.Encounter on DebugWorld, built here the way a level designer
## would build it in the editor (an Encounter node with MARK_spawn / MARK_cover / MARK_patrol children).
##
##   ./gradlew build && stdbuf -oL godot --headless --path . --script tools/godot/probe_encounter.gd
##
##   A. waves "3,2": nothing far away; wave 1 stands up calm within spawn_near (armed, gang_a, not on the player);
##      the member with no cover walks its patrol route; inside the trigger every member turns on the player and the
##      ones with cover go to it; wave 1 down -> wave 2 at the points kept for it; wave 2 down -> CLEARED, the
##      `encounter_cleared` signal, the ledger flag set;
##   B. a player's hit on a member from outside the trigger sets it off; every player past despawn_far: the living
##      are taken away, it is DORMANT and stands up again;
##   C. manual: a player standing in it does nothing; start_now sets it off at once; stop_now takes everyone away;
##   D. the CONTROL: enabled = false -> nothing stands up with the player inside it.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ENC := "res://src/main/java/com/openworld/game/encounter/Encounter.java"

var fails := 0
var world: Node
var player: CharacterBody3D
var cleared_heard := 0
var triggered_heard := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _ground(x: float, z: float, y: float) -> Variant:
	var sp := world.get_viewport().world_3d.direct_space_state
	var q := PhysicsRayQueryParameters3D.create(Vector3(x, y + 30.0, z), Vector3(x, y - 30.0, z))
	var hit := sp.intersect_ray(q)
	if hit.is_empty():
		return null
	return hit["position"]

## A flat patch 30-60 m from the player (centre + a 12 m cross within 0.6 m of its height).
func _flat_spot(from: Vector3) -> Variant:
	for d in [40.0, 55.0, 30.0, 70.0]:
		for k in 16:
			var a := TAU * k / 16.0
			var c = _ground(from.x + cos(a) * d, from.z + sin(a) * d, from.y)
			if c == null:
				continue
			var ok := true
			for o in [Vector3(12, 0, 0), Vector3(-12, 0, 0), Vector3(0, 0, 12), Vector3(0, 0, -12)]:
				var g = _ground(c.x + o.x, c.z + o.z, c.y)
				if g == null or absf(g.y - c.y) > 0.6:
					ok = false
					break
			if ok:
				return c
	return null

func _put(at: Vector3) -> void:
	player.global_position = at + Vector3(0, 0.3, 0)
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	await _tick(4)

func _marker(enc: Node3D, name: String, local: Vector3, wave: int = 0) -> Marker3D:
	var m := Marker3D.new()
	m.name = name
	if wave > 0:
		m.set_meta("wave", wave)
	enc.add_child(m)
	m.position = local
	return m

func _encounter(at: Vector3, id: String, waves: String, manual: bool) -> Node3D:
	var e: Node3D = load(ENC).new()
	e.set("encounter_id", id)
	e.set("faction", "gang_a")
	e.set("loadout", "gang_heavy")  # guns only: a melee member closes in instead of holding its cover
	e.set("waves", waves)
	e.set("trigger_radius", 15.0)
	e.set("spawn_near", 60.0)
	e.set("despawn_far", 100.0)
	e.set("next_wave_at", 0)
	e.set("wave_gap", 1.0)
	e.set("manual", manual)
	e.set("cover_radius", 0.0)
	e.set("ledger_flag", "probe_%s_cleared" % id)
	world.add_child(e)
	e.global_position = at
	_marker(e, "MARK_spawn_1", Vector3(-4, 0.1, 0), 1)
	_marker(e, "MARK_spawn_2", Vector3(0, 0.1, -4), 1)
	_marker(e, "MARK_spawn_3", Vector3(4, 0.1, 0), 1)
	_marker(e, "MARK_spawn_4", Vector3(-8, 0.1, 8), 2)
	_marker(e, "MARK_spawn_5", Vector3(8, 0.1, 8), 2)
	_marker(e, "MARK_cover_1", Vector3(-7, 0.1, -6))
	_marker(e, "MARK_cover_2", Vector3(7, 0.1, -6))
	_marker(e, "MARK_patrol_1", Vector3(0, 0.1, 6))
	_marker(e, "MARK_patrol_2", Vector3(6, 0.1, 9))
	e.connect("encounter_cleared", func(): cleared_heard += 1)
	e.connect("encounter_triggered", func(): triggered_heard += 1)
	return e

func _state(e: Node) -> String:
	return String(e.call("state_now")).get_slice(",", 0)

func _live(e: Node) -> int:
	return int(e.call("live_now"))

## The live members: [body, readout fields] -- "alive;faction;weapons;hunts;target;hold;distToHold".
func _members(e: Node) -> Array:
	var out := []
	for i in int(e.call("member_count_now")):
		var r := String(e.call("member_readout_now", i))
		var m = e.call("member_now", i)
		if m != null and is_instance_valid(m) and r.begins_with("alive"):
			out.append([m, r.split(";")])
	return out

func _wait_for(e: Node, state: String, frames: int) -> bool:
	for i in frames:
		if _state(e) == state:
			return true
		await physics_frame
	return _state(e) == state

func _initialize() -> void:
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	player = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	# DebugWorld's zones stand armed `enemy` AI about the map: they fight anyone (police, gangs), which is the world's
	# business but not what this probe measures -- clear them (zones spawn once per load)
	for c in world.get_node("Characters").get_children():
		if c != player and c is CharacterBody3D:
			c.queue_free()
	await _tick(10)
	var home := player.global_position
	var spot = _flat_spot(home)
	_check(spot != null, "DebugWorld has a flat patch for the fight")
	if spot == null:
		quit(1)
		return
	var dir: Vector3 = (home - spot)
	dir.y = 0
	dir = dir.normalized()

	# A. ─────────────────────────────────────────────────────────────────────
	print("A. waves, trigger, cover, patrol, clear")
	var e := _encounter(spot, "yard", "3,2", false)
	await _put(spot + dir * 130.0)
	var far_g = _ground((spot + dir * 130.0).x, (spot + dir * 130.0).z, spot.y)
	if far_g != null:
		await _put(far_g)
	await _tick(30)
	_check(_state(e) == "DORMANT" and _live(e) == 0, "nobody near: nothing stands up (%s)" % e.call("state_now"))
	await _put(spot + dir * 45.0)
	await _wait_for(e, "STANDING", 60)
	_check(_state(e) == "STANDING" and _live(e) == 3, "wave 1 stands up within spawn_near (%s)" % e.call("state_now"))
	var ms := _members(e)
	var armed := 0
	var gang := 0
	for m in ms:
		if m[1][2] != "":
			armed += 1
		if m[1][1] == "gang_a":
			gang += 1
	_check(armed == 3 and gang == 3, "every member is gang_a and carries a weapon from the loadout (%d armed, %d gang_a: %s)" % [armed, gang, str(ms.map(func(x): return x[1][2]))])
	var patroller: Node3D = null
	var covered := []
	for m in ms:
		if m[1][5] == "1":
			covered.append(m[0])
		else:
			patroller = m[0]
	_check(covered.size() == 2 and patroller != null, "two members took the two covers, one walks the patrol route")
	var p0 := patroller.global_position if patroller != null else Vector3.ZERO
	await _tick(360)
	_check(patroller != null and patroller.global_position.distance_to(p0) > 2.0, "the patroller walked its route (%.1f m)" % (patroller.global_position.distance_to(p0) if patroller != null else 0.0))
	var others := {}
	for c in world.get_node("Characters").get_children():
		if c is CharacterBody3D and c != player and c.global_position.distance_to(spot) < 80.0:
			var info = c.get("character_info")
			var f := String(info.get("faction")) if info != null else "?"
			others[f] = int(others.get(f, 0)) + 1
	print("  (characters within 80 m of the fight: %s)" % str(others))
	var targeting := 0
	var hunting := 0
	for m in _members(e):
		if m[1][4] == "player":
			targeting += 1
		if m[1][3] == "1":
			hunting += 1
	_check(targeting == 0 and hunting == 0, "calm before the trigger: nobody on the player (%s; gang_a hostile to player: %s)" % [str(_members(e).map(func(x): return ";".join(x[1]))), root.get_node("FactionManager").call("hostile_now", "gang_a", "player")])
	await _put(spot + dir * 9.0)
	await _wait_for(e, "ENGAGED", 30)
	_check(_state(e) == "ENGAGED" and triggered_heard == 1, "inside the trigger it turns on the player (signal %d)" % triggered_heard)
	await _tick(360)
	targeting = 0
	var at_cover := 0
	for m in _members(e):
		if m[1][4] == "player":
			targeting += 1
		var dh := float(m[1][6])
		if dh >= 0.0 and dh < 1.6:
			at_cover += 1
	_check(targeting >= 2, "the members target the player (%d of %d)" % [targeting, _live(e)])
	_check(at_cover == 2, "the two with cover are AT it (%d: %s)" % [at_cover, str(_members(e).map(func(x): return "%s/%s/%s/%s/%.1fm" % [x[1][6], x[1][7], x[1][8], x[1][9], x[0].global_position.distance_to(player.global_position)]))])
	for m in _members(e):
		helper.call("kill", m[0])
	for i in 180:
		if _live(e) == 2:
			break
		await physics_frame
	_check(_live(e) == 2 and int(String(e.call("state_now")).get_slice(",", 2)) == 0, "wave 1 down -> wave 2 (%s)" % e.call("state_now"))
	var near_kept := 0
	for m in _members(e):
		for loc in [Vector3(-8, 0, 8), Vector3(8, 0, 8)]:
			if m[0].global_position.distance_to(spot + loc) < 2.0:
				near_kept += 1
	_check(near_kept == 2, "wave 2 stood up at the points kept for it (%d)" % near_kept)
	for m in _members(e):
		helper.call("kill", m[0])
	await _wait_for(e, "CLEARED", 60)
	_check(_state(e) == "CLEARED" and cleared_heard == 1, "wave 2 down -> CLEARED and the signal (%s, %d)" % [e.call("state_now"), cleared_heard])
	_check(bool(e.call("ledger_flag_set_now")), "the ledger flag is set")
	e.queue_free()
	await _tick(5)

	# B. ─────────────────────────────────────────────────────────────────────
	print("B. everyone leaves -> reset")
	var b := _encounter(spot, "reset", "3", false)
	await _put(spot + dir * 45.0)
	await _wait_for(b, "STANDING", 60)
	# a player's shot from outside the trigger sets it off (a sniper); an AI's would not (the zone enemies in A)
	helper.call("hit_by", _members(b)[0][0], player, 5.0)
	await _wait_for(b, "ENGAGED", 30)
	_check(_state(b) == "ENGAGED", "a player's hit from 45 m sets it off (%s)" % b.call("state_now"))
	var bodies := _members(b).map(func(x): return x[0])
	await _put(spot + dir * 130.0)
	await _wait_for(b, "DORMANT", 60)
	await _tick(5)
	var gone := 0
	for m in bodies:
		if not is_instance_valid(m):
			gone += 1
	_check(_state(b) == "DORMANT" and gone == bodies.size() and bodies.size() == 3, "past despawn_far: DORMANT, the living freed (%d of %d)" % [gone, bodies.size()])
	await _put(spot + dir * 45.0)
	await _wait_for(b, "STANDING", 60)
	_check(_state(b) == "STANDING" and _live(b) == 3, "and it stands up again (%s)" % b.call("state_now"))
	await _put(spot + dir * 130.0)
	await _tick(30)
	b.queue_free()
	await _tick(5)

	# C. ─────────────────────────────────────────────────────────────────────
	print("C. manual")
	var c := _encounter(spot, "job", "2", true)
	await _put(spot + dir * 9.0)
	await _tick(60)
	_check(_state(c) == "DORMANT" and _live(c) == 0, "manual: a player standing in it does nothing")
	c.call("start_now")
	await _wait_for(c, "ENGAGED", 30)
	_check(_state(c) == "ENGAGED" and _live(c) == 2, "start_now: wave 1 at once, engaged (%s)" % c.call("state_now"))
	c.call("stop_now")
	await _tick(5)
	_check(_state(c) == "DORMANT" and _live(c) == 0, "stop_now: everyone taken away (%s)" % c.call("state_now"))
	c.queue_free()
	await _tick(5)

	# D. ─────────────────────────────────────────────────────────────────────
	print("D. CONTROL: disabled")
	var d := _encounter(spot, "off", "3", false)
	d.set("enabled", false)
	await _put(spot + dir * 9.0)
	await _tick(90)
	_check(_state(d) == "DORMANT" and _live(d) == 0, "enabled = false: nothing stands up (%s)" % d.call("state_now"))

	print("probe_encounter: %s (%d failed)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
