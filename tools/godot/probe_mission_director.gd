extends SceneTree
## MissionDirector (PLAN.md 4.2 / F1): the named-character registry, scripted commands, story beats,
## the mission-output graph and the mission-entity rule — each asserted on the real autoload with real
## AI bodies, never on a stand-in.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_mission_director.gd
##   ... -- --control      # the boss's `story_character` flag is off, so nothing registers it: the
##                         registry, the walk order, the invincibility and the release all FAIL (11),
##                         which is the gate showing it bites.
##
## Why a Player stands in the scene: an AICharacter with no player within 80 m is LOD-FROZEN and its
## whole FSM is skipped, so a probe without one measures an AI that never thinks. It is also the
## hostile for the "an order is not a mood" case — the boss must walk past it without engaging.
##
## Not covered here, on purpose: ZoneManager's half of the mission-vehicle rule (it asks
## `is_mission_protected` before reclaiming a car). That needs a streamed zone with live traffic —
## `probe_traffic_spawn.gd`'s stand — so what this probe asserts is the ANSWER the streamer reads.

const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const MISSION := "res://src/main/resources/com/openworld/game/mission/GangA_vs_Police_Mission.tres"
const CONSOLE := "res://src/main/java/com/openworld/debug/DebugConsole.java"
const INFO    := "res://src/main/java/com/openworld/character/CharacterInfo.java"

const BOSS := "boss_01"

var fails := 0
var control := false
var world: Node3D
var director: Node
var bus: Node
var helper: Node

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _spawn_ai(id: String, faction: String, story: bool, pos: Vector3) -> Node3D:
	var b: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	b.set("story_character", story and not control)
	# A fresh CharacterInfo, never the scene's: a .tscn-embedded sub-resource is SHARED by every
	# instantiation (CLAUDE.md "Known Quirks"), and Character._ready only privatizes one whose id is
	# still empty — so stamping the scene's own resource renames every AI spawned before this one.
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
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	await process_frame

	director = root.get_node_or_null("MissionDirector")
	bus = root.get_node_or_null("EventBus")
	var mm: Node = root.get_node_or_null("MissionManager")
	if director == null or bus == null or mm == null:
		print("RESULT FAIL (MissionDirector / EventBus / MissionManager autoload missing)")
		quit(1)
		return

	world = Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	helper = load(HELPER).new()
	world.add_child(helper)
	await _tick(2)

	# The player keeps the AI out of the FROZEN LOD tier, and is the hostile in case 3.
	var player: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = Vector3(6, 0, 10)
	await _tick(2)
	player.get("character_info").set("faction", "player")

	var boss: Node3D = await _spawn_ai(BOSS, "enemy", true, Vector3(0, 0, 20))
	var ambient: Node3D = await _spawn_ai("ambient_01", "enemy", false, Vector3(30, 0, 20))
	await _tick(4)

	print("")
	print("=== 1. the named-character registry ===")
	_check("the story AI registered under its authored id",
		director.call("is_named_character_loaded", BOSS), BOSS)
	_check("an ambient AI is NOT in the registry",
		not director.call("is_named_character_loaded", "ambient_01"), "")
	_check("the id listing names the boss",
		BOSS in str(director.call("named_character_ids")),
		str(director.call("named_character_ids")))

	var impostor: Node3D = await _spawn_ai(BOSS, "enemy", true, Vector3(40, 0, 20))
	await _tick(2)
	_check("a second body claiming the same id is refused, the loaded one kept",
		director.call("is_named_character_loaded", BOSS), "")
	impostor.queue_free()
	await _tick(2)
	_check("freeing the impostor does not drop the real boss's entry",
		director.call("is_named_character_loaded", BOSS), "")

	print("")
	print("=== 2. the spec's verify: commandCharacter(boss, moveTo origin) ===")
	var start_dist: float = boss.global_position.distance_to(Vector3.ZERO)
	var ordered: bool = director.call("command_move_to", BOSS, Vector3.ZERO)
	_check("the order was accepted", ordered, str(ordered))
	_check("the boss is in SCRIPTED_MOVE", director.call("state_name_of", BOSS) == "SCRIPTED_MOVE",
		str(director.call("state_name_of", BOSS)))

	var held := true
	var waited := 0
	var budget: int = 120 if control else 60 * 30
	while waited < budget and not director.call("has_arrived", BOSS):
		await _tick(15)
		waited += 15
		if director.call("state_name_of", BOSS) != "SCRIPTED_MOVE":
			held = false
	var end_dist: float = boss.global_position.distance_to(Vector3.ZERO)
	print("   walked %.2f m -> %.2f m from the origin in %.1f s" % [start_dist, end_dist, waited / 60.0])
	_check("the boss walked to the origin", end_dist < 1.5, "%.2f m" % end_dist)
	_check("has_arrived reports it", director.call("has_arrived", BOSS), "")

	print("")
	print("=== 3. an order is not a mood: a hostile in view does not cancel it ===")
	_check("SCRIPTED_MOVE held for the whole walk (a hostile player stood 10 m off the path)",
		held, "held" if held else "left the state")

	print("")
	print("=== 4. scripted invincibility is one rule, in Health.applyDamage ===")
	var hits := {"n": 0, "died": 0}
	var h: Node = boss.get_node("Health")
	h.connect("hit", func(_d): hits["n"] += 1)
	h.connect("died", func(): hits["died"] += 1)
	director.call("command_invincible", BOSS, true)
	helper.call("kill", boss)
	await _tick(10)
	_check("an invincible boss takes no damage at all",
		hits["n"] == 0 and hits["died"] == 0, "hits=%d died=%d" % [hits["n"], hits["died"]])

	print("")
	print("=== 5. releasing an order also clears what it set ===")
	var released: bool = director.call("release_character", BOSS)
	_check("released, and back to its own behaviour",
		released and director.call("state_name_of", BOSS) == "PATROL",
		str(director.call("state_name_of", BOSS)))
	helper.call("kill", boss)
	await _tick(10)
	_check("invulnerability went with the release — the boss is mortal again",
		hits["died"] == 1, "hits=%d died=%d" % [hits["n"], hits["died"]])

	print("")
	print("=== 6. story beats ===")
	var beats: Array[String] = []
	bus.connect("mission_beat_triggered", func(b): beats.append(b))
	director.call("trigger_beat", "ambush_gate")
	director.call("trigger_beat", "ambush_gate")
	await _tick(2)
	_check("a beat with no Java handler still emits the event",
		beats == ["ambush_gate", "ambush_gate"], str(beats))
	_check("the director counts its firings", director.call("beat_fire_count", "ambush_gate") == 2,
		str(director.call("beat_fire_count", "ambush_gate")))

	print("")
	print("=== 7. the mission-output graph ===")
	director.call("reset_campaign")
	director.call("declare_unlock_on", "mission_b", "mission_a#ESCAPED")
	_check("a mission nobody gated is open", director.call("is_mission_unlocked", "mission_a"), "")
	_check("a gated mission starts locked", not director.call("is_mission_unlocked", "mission_b"), "")

	bus.emit_signal("mission_completed", "mission_a", "player", "ELIMINATED")
	await _tick(2)
	_check("the wrong variant does not open it", not director.call("is_mission_unlocked", "mission_b"), "")
	bus.emit_signal("mission_completed", "mission_a", "player", "ESCAPED")
	await _tick(2)
	_check("the declared variant opens it", director.call("is_mission_unlocked", "mission_b"), "")
	_check("both variants are in the accumulated set",
		director.call("achieved_variant_count") == 2 and director.call("has_achieved", "mission_a", "ESCAPED"),
		str(director.call("achieved_variant_count")))

	bus.emit_signal("mission_completed", "mission_a", "player", "ESCAPED")
	bus.emit_signal("mission_completed", "mission_a", "player", "ESCAPED")
	await _tick(2)
	_check("idempotent on variant: replaying it adds no branch",
		director.call("achieved_variant_count") == 2, str(director.call("achieved_variant_count")))

	director.call("declare_unlock_on", "mission_b", "mission_a#NEVER_HAPPENS")
	_check("sticky: a branch once open never closes", director.call("is_mission_unlocked", "mission_b"), "")

	_check("a unique item is granted exactly once",
		director.call("grant_unique_once", "katana") and not director.call("grant_unique_once", "katana"), "")

	print("")
	print("=== 8. the director gates which mission may start ===")
	var started: Array[String] = []
	bus.connect("mission_started", func(id, _t): started.append(id))
	var mission: Resource = load(MISSION)
	var mission_id: String = str(mission.get("mission_id"))
	director.call("reset_campaign")
	director.call("declare_unlock_on", mission_id, "prologue#DONE")
	_check("a locked mission is refused", not director.call("start_mission_from_path", MISSION), mission_id)
	_check("and nothing started", started.is_empty(), str(started))
	bus.emit_signal("mission_completed", "prologue", "player", "DONE")
	await _tick(2)
	_check("once unlocked it starts through MissionManager",
		director.call("start_mission_from_path", MISSION) and started == [mission_id], str(started))

	print("")
	print("=== 9. a mission entity is not disposable, and losing it fails the mission ===")
	var car := Node3D.new()
	world.add_child(car)
	director.call("register_mission_entity", "getaway_car", car, true)
	_check("the streamer's question answers true", director.call("mission_protected_now", car), "")
	_check("an unregistered node is not protected", not director.call("mission_protected_now", boss), "")
	var failed: Array[String] = []
	bus.connect("mission_failed", func(_id, reason): failed.append(reason))
	car.queue_free()
	await _tick(5)
	_check("losing it failed the ACTIVE mission, naming the entity",
		failed.size() == 1 and "getaway_car" in failed[0], str(failed))
	_check("and it left the entity list", director.call("mission_entity_count") == 0,
		str(director.call("mission_entity_count")))

	print("")
	print("=== 10. the debug console reaches the director (F1's iteration prerequisite) ===")
	var console: Node = load(CONSOLE).new()
	world.add_child(console)
	await _tick(2)
	console.call("on_submit", "named")
	console.call("on_submit", "beat ambush_gate")
	console.call("on_submit", "unlock console_mission prologue#DONE")
	console.call("on_submit", "nonsense")          # must not throw, must not be silent
	await _tick(2)
	# 1, not 3: reset_campaign in case 7 cleared the fired-beat log, which is itself campaign state.
	_check("a console beat reached the director", director.call("beat_fire_count", "ambush_gate") == 1,
		str(director.call("beat_fire_count", "ambush_gate")))
	_check("a console unlock declaration reached the director",
		director.call("is_mission_unlocked", "console_mission"), "")

	print("")
	print("=== 11. registration ends with the body ===")
	boss.queue_free()
	await _tick(5)
	_check("a freed story character leaves the registry",
		not director.call("is_named_character_loaded", BOSS), "")

	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
