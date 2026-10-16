extends SceneTree
## GUARDS AT GUARDED BUILDINGS (PLAN.md 1j / 2.2): game.encounter.SiteGuards on DebugWorld, with real baked building
## scenes placed here (on the island they stream in with their blocks). The guards come from the MARK_spawn markers
## the buildings already carry (team police / guard / soldier ...) and character/loadouts.json.
##
##   ./gradlew build && stdbuf -oL godot --headless --path . --script tools/godot/probe_site_guards.gd
##
##   A. PoliceStation_Shop: nobody far away; within `near` its police posts are manned (per_building), police, armed
##      from the police_station loadout, standing at their markers, calm with a clean record; at shoot_at stars they
##      turn on the player; once the record is clean and every player has gone past `far` they are taken away;
##   B. a SHUT variant (PoliceStation.tscn): the posts indoors stay empty, the two gate posts under open sky are manned;
##   C. BankSmall_Open: the lobby guard (team guard -> security loadout), NOT the staff / civilian / vip markers;
##   D. the CONTROL: SiteGuards.enabled = false -> nobody at the police station.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const B := "res://src/main/resources/com/openworld/world/buildings/"

var fails := 0
var world: Node
var player: CharacterBody3D
var sg: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _ground(x: float, z: float, y: float) -> Variant:
	var sp := world.get_viewport().world_3d.direct_space_state
	var hit := sp.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(x, y + 30.0, z), Vector3(x, y - 30.0, z)))
	return null if hit.is_empty() else hit["position"]

func _flat_spot(from: Vector3, d0: float) -> Variant:
	for d in [d0, d0 + 20.0, d0 + 40.0]:
		for k in 16:
			var a := TAU * k / 16.0
			var c = _ground(from.x + cos(a) * d, from.z + sin(a) * d, from.y)
			if c == null:
				continue
			var ok := true
			for o in [Vector3(25, 0, 0), Vector3(-25, 0, 0), Vector3(0, 0, 25), Vector3(0, 0, -25)]:
				var g = _ground(c.x + o.x, c.z + o.z, c.y)
				if g == null or absf(g.y - c.y) > 1.0:
					ok = false
					break
			if ok:
				return c
	return null

func _put(at: Vector3) -> void:
	var g = _ground(at.x, at.z, at.y)
	player.global_position = (g if g != null else at) + Vector3(0, 0.3, 0)
	player.velocity = Vector3.ZERO
	player.get_node("MovementController").call("clear_motion")
	await _tick(4)

func _live() -> int:
	return int(String(sg.call("guards_now")).get_slice(",", 1))

func _readouts() -> Array:
	var out := []
	for i in _live():
		out.append(String(sg.call("guard_readout_now", i)).split(";"))
	return out

func _place(scene: String, at: Vector3) -> Node3D:
	var b: Node3D = (load(B + scene) as PackedScene).instantiate()
	world.add_child(b)
	b.global_position = at
	await _tick(10)
	return b

func _wait_live(n: int, frames: int) -> void:
	for i in frames:
		if _live() == n:
			return
		await physics_frame

func _initialize() -> void:
	world = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	var gm: Node = root.get_node("GameManager")
	sg = gm.get_node("SiteGuards")
	var ws: Node = gm.get_node("WantedSystem")
	player = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	# DebugWorld's zones stand armed `enemy` AI about the map: they fight anyone (police, gangs), which is the world's
	# business but not what this probe measures -- clear them (zones spawn once per load)
	for c in world.get_node("Characters").get_children():
		if c != player and c is CharacterBody3D:
			c.queue_free()
	await _tick(10)
	var pid: String = player.get("character_info").get("character_id")
	var home := player.global_position
	var spot = _flat_spot(home, 60.0)
	_check(spot != null, "DebugWorld has a flat patch for a police station")
	if spot == null:
		quit(1)
		return
	var dir: Vector3 = home - spot
	dir.y = 0
	dir = dir.normalized()
	var far: Vector3 = spot + dir * 160.0

	# A. ─────────────────────────────────────────────────────────────────────
	print("A. PoliceStation_Shop")
	await _put(far)
	var ps := await _place("PoliceStation_Shop.tscn", spot)
	await _tick(60)
	_check(_live() == 0, "a player 160 m away: nobody stands guard (%s)" % sg.call("guards_now"))
	await _put(spot + dir * 40.0)
	await _wait_live(4, 120)
	var rs := _readouts()
	_check(rs.size() == 4, "within near: per_building (4) of the 6 police posts are manned (%s)" % sg.call("guards_now"))
	# closer, so every post is inside the active AI tier (a frozen body's queued equips wait for it to wake)
	await _put(spot + dir * 26.0)
	await _tick(60)
	rs = _readouts()
	var police := 0
	var armed := 0
	for r in rs:
		if r[0] == "police":
			police += 1
		if (r[1].contains("PIS1") or r[1].contains("ASR2")) and r[1].contains("BAT1"):
			armed += 1
	_check(police == 4 and armed == 4, "police, armed from police_station: a gun + the baton (%s)" % str(rs.map(func(x): return x[1])))
	# calm, a guard stands on its post; a sound sends it to look, but never past its leash (6 m), and it goes back
	var worst := 0.0
	var at_post := 0
	var on_player := 0
	for f in 900:
		rs = _readouts()
		at_post = 0
		for r in rs:
			worst = maxf(worst, float(r[3]))
			if r[4] == "PatrolState" and float(r[3]) >= 0.0 and float(r[3]) < 1.5:
				at_post += 1
			if r[2] == "player":
				on_player += 1
		if f >= 90 and at_post == rs.size():
			break
		await physics_frame
	_check(at_post == rs.size() and rs.size() > 0, "each stands at its post (%d of %d: %s)" % [at_post, rs.size(), str(rs.map(func(x): return "/".join(x)))])
	_check(worst < 6.6, "nobody went past its leash looking about (%.1f m)" % worst)
	_check(on_player == 0, "a clean record: nobody on the player")
	ws.call("set_stars_now", pid, 3, false)
	for i in 300:
		on_player = 0
		for r in _readouts():
			if r[2] == "player":
				on_player += 1
		if on_player > 0:
			break
		await physics_frame
	_check(on_player > 0, "at shoot_at stars the guards turn on the player (%d)" % on_player)
	ws.call("clear_now", pid)
	await _put(far)
	await _wait_live(0, 120)
	_check(_live() == 0, "a clean record and every player past far: the guards are taken away (%s)" % sg.call("guards_now"))
	ps.queue_free()
	await _tick(30)

	# B. ─────────────────────────────────────────────────────────────────────
	print("B. a SHUT police station")
	var shut := await _place("PoliceStation.tscn", spot)
	await _put(spot + dir * 40.0)
	await _tick(150)
	rs = _readouts()
	_check(rs.size() == 2, "only the two gate posts under open sky are manned (%s)" % sg.call("guards_now"))
	await _put(far)
	await _wait_live(0, 120)
	shut.queue_free()
	await _tick(30)

	# C. ─────────────────────────────────────────────────────────────────────
	print("C. BankSmall_Open")
	var bank := await _place("BankSmall_Open.tscn", spot)
	await _put(spot + dir * 30.0)
	await _wait_live(1, 120)
	await _tick(30)
	rs = _readouts()
	_check(rs.size() == 1, "one guard: the lobby guard, not the staff / civilian / vip (%s)" % sg.call("guards_now"))
	_check(rs.size() == 1 and (rs[0][1] == "BAT1" or rs[0][1] == "PIS1"), "armed from the security loadout (%s)" % (rs[0][1] if rs.size() > 0 else "-"))
	await _put(far)
	await _wait_live(0, 120)
	bank.queue_free()
	await _tick(30)

	# D. ─────────────────────────────────────────────────────────────────────
	print("D. CONTROL: disabled")
	sg.set("enabled", false)
	var ps2 := await _place("PoliceStation_Shop.tscn", spot)
	await _put(spot + dir * 40.0)
	await _tick(150)
	_check(_live() == 0, "SiteGuards off: nobody at the police station (%s)" % sg.call("guards_now"))

	print("probe_site_guards: %s (%d failed)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
