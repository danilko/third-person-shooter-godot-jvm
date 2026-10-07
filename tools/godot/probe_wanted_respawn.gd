extends SceneTree
## THE WANTED LEVEL AND THE JAIL RESPAWN (PLAN.md W5, user decisions 2026-10-03).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_wanted_respawn.gd [-- --world=island]
##   ... -- --control      (RespawnSystem.enabled off: a death is GAME_OVER, as before)
##
##   1. a player hitting a civilian with someone there to see it is wanted (>= 1 star);
##   2. killing a police officer is at least 3 stars at once;
##   3. the player dies (stars cleared first: a death while wanted is jail, probe_recovery.gd): the 入院 HOSPITALIZED card, the game is NOT over, a fresh Player stands at the nearest
##      hospital / clinic door (island) or the PlayerSpawn (DebugWorld has none), alive (only the fist), wanted 0, and
##      the running mission (if any) has failed;
##   4. the player is ARRESTED (RespawnSystem.arrest, the police dispatch's call): the 逮捕 ARRESTED card, a second
##      respawn; (island) once the station streams in the player is in a cell and the station's locked doors open.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const INFO := "res://src/main/java/com/openworld/character/CharacterInfo.java"

var fails := 0
var world: Node

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _spawn_ai(id: String, faction: String, pos: Vector3) -> Node3D:
	var b: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	var info: Resource = load(INFO).new()
	info.set("character_id", id)
	info.set("display_name", id)
	info.set("faction", faction)
	b.set("character_info", info)
	world.add_child(b)
	b.global_position = pos
	await _tick(2)
	return b

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var island := "--world=island" in args
	world = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	var gm: Node = root.get_node("GameManager")
	var ws: Node = gm.get_node_or_null("WantedSystem")
	var rs: Node = gm.get_node_or_null("RespawnSystem")
	_check(ws != null and rs != null, "GameManager built the WantedSystem and the RespawnSystem")
	if ws == null or rs == null:
		quit(1)
		return
	if control:
		rs.set("enabled", false)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	var player: CharacterBody3D = world.get_node("Characters/Player")
	var pid: String = player.get("character_info").get("character_id")
	var at := player.global_position

	# 1. assault, witnessed by the victim itself
	var civ := await _spawn_ai("probe_civ", "neutral", at + Vector3(3, 0.5, 0))
	helper.call("hit_by", civ, player, 20.0)
	await _tick(2)
	_check(int(ws.call("stars_now", pid)) >= 1, "hitting a civilian makes the player wanted (%d star(s))" % int(ws.call("stars_now", pid)))
	# 2. a dead policeman: three stars at once
	var cop := await _spawn_ai("probe_cop", "police", at + Vector3(-3, 0.5, 0))
	helper.call("hit_by", cop, player, 1.0e6)
	await _tick(2)
	_check(int(ws.call("stars_now", pid)) >= 3, "killing a police officer is >= 3 stars (%d)" % int(ws.call("stars_now", pid)))

	# 3. death -> hospitalised. Since 2026-10-06 a death WHILE WANTED is jail (probe_recovery.gd covers that), so the
	#    stars are cleared first: this case is the plain hospital path.
	ws.call("clear_now", pid)
	var mm: Node = root.get_node_or_null("MissionManager")
	helper.call("kill", player)
	await _tick(10)
	var card := String(rs.call("card_text_now"))
	for i in 60 * 6:
		await physics_frame
		if int(rs.call("respawns_now")) > 0:
			break
	await _tick(30)
	if control:
		_check(not bool(gm.call("playing_now")), "control: with the respawn off a death is game over")
		_check(int(rs.call("respawns_now")) == 0, "control: nobody respawned")
		print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
		quit(1 if fails else 0)
		return
	_check(card.begins_with("入院 HOSPITALIZED"), "a death shows the hospitalised card (%s)" % card.replace("\n", " "))
	_check(bool(gm.call("playing_now")), "a death is not game over")
	_check(int(rs.call("respawns_now")) == 1 and String(rs.call("last_reason_now")) == "HOSPITALIZED", "the player respawned, hospitalised")
	var fresh: Node3D = rs.call("respawned_player_now")
	_check(fresh != null and is_instance_valid(fresh) and float(fresh.get_node("Health").call("health_now")) > 0.0, "a fresh, living Player")
	_check(not is_instance_valid(player), "the dead body is gone")
	_check(int(ws.call("stars_now", pid)) == 0, "the wanted level is cleared")
	if mm != null:
		_check(not bool(mm.call("mission_active_now")), "no mission is left running")
	if fresh != null:
		print("probe_wanted_respawn: hospitalised at %s" % fresh.global_position)
		if island:
			var near := 1e9
			var places: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/world/places/World.places.json"))
			near = _near_respawn(fresh.global_position, ["Hospital", "HospitalSmall", "Clinic"])
			_check(near < 1.5, "the player woke on a hospital / clinic respawn point, outside (%.1f m)" % near)
	# 4. arrested
	await _tick(60)
	_check(bool(rs.call("arrest_now", fresh)), "the player can be arrested")
	await _tick(10)
	card = String(rs.call("card_text_now"))
	_check(card.begins_with("逮捕 ARRESTED"), "an arrest shows the arrested card (%s)" % card.replace("\n", " "))
	for i in 60 * 6:
		await physics_frame
		if int(rs.call("respawns_now")) > 1:
			break
	_check(int(rs.call("respawns_now")) == 2 and String(rs.call("last_reason_now")) == "ARRESTED", "the player respawned, arrested")
	if island:
		for i in 60 * 6:
			await physics_frame
			if bool(rs.call("faded_in_now")):
				break
		_check(bool(rs.call("faded_in_now")), "the arrested player's screen faded in")
		var jailed: Node3D = rs.call("respawned_player_now")
		if jailed != null:
			var nj := _near_respawn(jailed.global_position, ["PoliceStation"])
			_check(nj < 1.5, "the arrested player was let go on a police station respawn point, outside (%.1f m)" % nj)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)


func _near_respawn(pos: Vector3, kinds: Array) -> float:
	var near := 1e9
	var places: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://src/main/resources/com/openworld/world/places/World.places.json"))
	for pl in places["places"]:
		if pl["kind"] in kinds:
			for r in pl.get("respawn", []):
				near = minf(near, Vector2(pos.x, pos.z).distance_to(Vector2(r[0], r[2])))
	return near
