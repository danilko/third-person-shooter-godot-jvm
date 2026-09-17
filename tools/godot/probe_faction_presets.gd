extends SceneTree
## Faction presets (PLAN.md 4.1 / F2): real AI under each shipped FactionTable pick the targets the
## table says, a mission's table is a LAYER that comes and goes with the mission, and under
## GangA_vs_Police.tres armed gang and police AI actually shoot each other while a civilian and the
## sitting-out gang are left alone.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_faction_presets.gd
##
## The cast stands still (MovementController off) but THINKS (the Character's own physics runs the FSM
## and the target scan). Distances are chosen so the shipped DefaultFactions table — which only knows
## "different factions are hostile" — sends the policeman at the CIVILIAN (the nearest body), which is
## the control every preset has to change.

const AI      := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const PLAYER  := "res://src/main/resources/com/openworld/character/Player.tscn"
const ASR1    := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const IMPACT  := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const OPEN_WORLD := "res://src/main/resources/com/openworld/character/OpenWorldFactions.tres"
const MISSION := "res://src/main/resources/com/openworld/game/mission/GangA_vs_Police_Mission.tres"

var fails := 0
var world: Node3D
var cast := {}        # role -> body
var ids := {}         # characterId -> role

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _spawn_ai(role: String, faction: String, pos: Vector3) -> Node3D:
	var b: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(b)
	b.global_position = pos
	await _tick(2)
	b.get("character_info").set("faction", faction)
	var mc: Node = b.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)
	b.global_position = pos
	cast[role] = b
	return b

func _role_of_target(role: String) -> String:
	var id: String = cast[role].call("target_id_now")
	return ids.get(id, "" if id == "" else "?" + id)

## Targets settle over a few scan intervals; read them after `frames`.
func _targets(frames: int) -> Dictionary:
	await _tick(frames)
	var out := {}
	for role in ["police", "gang_a", "gang_b", "civilian"]:
		out[role] = _role_of_target(role)
	return out

func _nobody_targets(t: Dictionary, victim: String) -> bool:
	for role in t:
		if t[role] == victim:
			return false
	return true

func _initialize() -> void:
	await process_frame
	var fm: Node = root.get_node_or_null("FactionManager")
	var mm: Node = root.get_node_or_null("MissionManager")
	if fm == null or mm == null:
		print("RESULT FAIL (FactionManager / MissionManager autoload missing)")
		quit(1)
		return

	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	var impact: Node = load(IMPACT).new()
	impact.name = "ImpactManager"
	world.add_child(impact)
	await _tick(2)

	var player: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = Vector3(0, 0, 14)
	await _tick(2)
	player.get("character_info").set("faction", "player")
	cast["player"] = player

	# police sits 12.2 m from the civilian and 14 m from everyone else.
	await _spawn_ai("police", "police", Vector3(0, 0, 0))
	await _spawn_ai("gang_a", "gang_a", Vector3(14, 0, 0))
	await _spawn_ai("gang_b", "gang_b", Vector3(-14, 0, 0))
	await _spawn_ai("civilian", "civilian", Vector3(7, 0, -10))
	for role in cast:
		ids[cast[role].get("character_info").get("character_id")] = role

	print("")
	print("=== 1. the pair rule, read off the live manager ===")
	fm.call("apply_table", load(OPEN_WORLD))
	_check("OpenWorld: civilian neutral to everyone (wildcard)",
		not fm.call("hostile_now", "civilian", "gang_a") and not fm.call("hostile_now", "police", "civilian")
		and not fm.call("hostile_now", "civilian", "faction_added_later"), "")
	_check("OpenWorld: police neutral to the player", not fm.call("hostile_now", "police", "player"), "")
	_check("OpenWorld: police vs both gangs, gangs vs each other",
		fm.call("hostile_now", "police", "gang_a") and fm.call("hostile_now", "gang_b", "police")
		and fm.call("hostile_now", "gang_a", "gang_b"), "")
	_check("OpenWorld: a gang is not hostile to itself", not fm.call("hostile_now", "gang_a", "gang_a"), "")

	print("")
	print("=== 2. control: the shipped defaults (no preset) ===")
	fm.call("apply_table", null)
	var t: Dictionary = await _targets(90)
	print("   targets %s  layer=%s" % [t, fm.call("active_layer_now")])
	_check("defaults: police goes for the nearest body, the civilian", t["police"] == "civilian", t["police"])

	print("")
	print("=== 3. OpenWorldFactions.tres as the region layer ===")
	fm.call("apply_table", load(OPEN_WORLD))
	t = await _targets(90)
	print("   targets %s  layer=%s" % [t, fm.call("active_layer_now")])
	_check("layer is the region's", fm.call("active_layer_now") == "region", fm.call("active_layer_now"))
	_check("police targets a gang (not the civilian, not the player)", t["police"] in ["gang_a", "gang_b"], t["police"])
	_check("the civilian targets nobody", t["civilian"] == "", t["civilian"])
	_check("nobody targets the civilian", _nobody_targets(t, "civilian"), str(t))
	_check("gang_a targets someone hostile", t["gang_a"] in ["police", "gang_b", "player"], t["gang_a"])

	print("")
	print("=== 4. the mission layer: GangA_vs_Police_Mission.tres ===")
	var started: bool = mm.call("start_mission_from_path", MISSION)
	t = await _targets(90)
	print("   targets %s  layer=%s" % [t, fm.call("active_layer_now")])
	_check("the mission started and its table is the live layer",
		started and fm.call("active_layer_now") == "mission", str(started) + " " + str(fm.call("active_layer_now")))
	_check("police targets gang_a", t["police"] == "gang_a", t["police"])
	_check("gang_a targets police", t["gang_a"] == "police", t["gang_a"])
	_check("gang_b sits it out (gang_b>* NEUTRAL)", t["gang_b"] == "" and _nobody_targets(t, "gang_b"), str(t))
	_check("nobody targets the civilian", _nobody_targets(t, "civilian"), str(t))
	_check("the player sides with the police", not fm.call("hostile_now", "police", "player"), "")
	fm.call("apply_table", null)
	_check("a region change while the mission runs does not replace it",
		fm.call("active_layer_now") == "mission" and fm.call("hostile_now", "gang_a", "police")
		and not fm.call("hostile_now", "gang_b", "police"), fm.call("active_layer_now"))

	print("")
	print("=== 5. the spec's verify: gang and police actually fight ===")
	var hits := {}
	for role in ["police", "gang_a", "gang_b", "civilian"]:
		hits[role] = 0.0
		var h: Node = cast[role].get_node_or_null("Health")
		h.connect("hit", func(d): hits[role] += d)
	# The fighters get their MovementController back: it is what turns a body toward its aim, and with it
	# off a target 90 degrees to the side stays past the aim reach, so W21's fire gate holds every shot
	# (measured: the policeman targeted gang_a for 20 s with a full magazine).
	for role in ["police", "gang_a"]:
		cast[role].get_node("MovementController").set_physics_process(true)
	for role in ["police", "gang_a"]:
		var gun: Node3D = (load(ASR1) as PackedScene).instantiate() as Node3D
		world.add_child(gun)
		gun.global_position = cast[role].global_position + Vector3(0, 3, 0)
		await _tick(3)
		(gun.get_parent() as Node3D).global_position = cast[role].global_position + Vector3(0, 0.6, 0)
	var attackers := {}
	root.get_node("EventBus").connect("damage_dealt", func(aid, dmg, _hs, _k):
		var r: String = ids.get(aid, "?" + str(aid))
		attackers[r] = attackers.get(r, 0.0) + dmg)
	var waited := 0
	while waited < 60 * 20 and (hits["police"] <= 0.0 or hits["gang_a"] <= 0.0):
		await _tick(30)
		waited += 30
	print("   damage taken after %.1f s: %s, dealt by %s" % [waited / 60.0, hits, attackers])
	_check("police took gang_a's fire", hits["police"] > 0.0, str(hits["police"]))
	_check("gang_a took police fire", hits["gang_a"] > 0.0, str(hits["gang_a"]))
	_check("the civilian and gang_b were left alone", hits["civilian"] == 0.0 and hits["gang_b"] == 0.0,
		"%s / %s" % [hits["civilian"], hits["gang_b"]])

	print("")
	print("=== 6. the mission ends: its table goes with it ===")
	mm.call("complete_mission_now", "police", "ELIMINATED")
	_check("layer back to the defaults", fm.call("active_layer_now") == "default", fm.call("active_layer_now"))
	_check("defaults again: gang_b and police hostile", fm.call("hostile_now", "gang_b", "police"), "")

	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
