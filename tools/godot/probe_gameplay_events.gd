extends SceneTree
## PLAN.md 2.0: the typed action -> consequence stream (game.event.GameplayEvents, AR3) and the world's ledger
## (game.WorldLedger, CR3), on the real autoloads with real bodies.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_gameplay_events.gd
##
## EVENTS. Health no longer calls the wanted level or the gangs: it publishes ONE event and they subscribe. So: a
## player's hit on a civilian is a star, on a gang member a gang star -- with nothing but the event between them. The
## controls are inside the run: (a) the SAME hit while an activity-phase subscriber sanctions it gives no star (so the
## star above came through the stream, not a leftover direct call), (b) the same hit by an AI gives the player none.
##
## LEDGER. A story character (story_character, an authored id) killed is dead in the ledger; spawned again it is
## removed; an ambient AI killed is not recorded. Control: with the ledger reset the same boss spawns and LIVES. Then
## save -> lose it (reset) -> load: the death and a world flag are back, and the boss that was alive is swept.

const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const INFO   := "res://src/main/java/com/openworld/character/CharacterInfo.java"
const BOSS := "boss_ledger_probe"
const SLOT := 8

var fails := 0
var world: Node3D
var helper: Node

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _spawn_ai(id: String, faction: String, story: bool, pos: Vector3) -> Node3D:
	var b: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	b.set("story_character", story)
	var info: Resource = load(INFO).new()
	info.set("character_id", id)
	info.set("display_name", id)
	info.set("faction", faction)
	b.set("character_info", info)
	world.add_child(b)
	if is_instance_valid(b) and b.is_inside_tree():
		b.global_position = pos
	await _tick(3)
	return b

func _initialize() -> void:
	await process_frame
	var gm: Node = root.get_node_or_null("GameManager")
	var saves: Node = root.get_node_or_null("SaveSystem")
	var director: Node = root.get_node_or_null("MissionDirector")
	var wanted: Node = gm.get_node_or_null("WantedSystem") if gm else null
	# the witness call-in (P1e step 4) is probe_engagement_v2's: here a crime counts at once, as it did
	if wanted != null:
		wanted.call("set_call_in_now", 0.0)
	var gangs: Node = gm.get_node_or_null("GangSystem") if gm else null
	if gm == null or saves == null or director == null or wanted == null or gangs == null:
		print("RESULT FAIL (GameManager / SaveSystem / MissionDirector / WantedSystem / GangSystem missing)")
		quit(1)
		return
	saves.set("autosave_enabled", false)
	saves.call("ledger_reset_now")

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

	var player: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = Vector3(0, 0, 0)
	await _tick(4)
	player.get("character_info").set("faction", "player")
	var pid: String = player.get("character_info").get("character_id")

	var civ: Node3D = await _spawn_ai("civ_a", "civilian", false, Vector3(6, 0, 6))
	var civ2: Node3D = await _spawn_ai("civ_b", "civilian", false, Vector3(-6, 0, 6))
	var thug: Node3D = await _spawn_ai("thug_a", "gang_a", false, Vector3(0, 0, 12))
	await _tick(10)

	print("")
	print("=== 0. the data tables (util.DataTable, game.data.Tables) ===")
	var problems := str(gm.call("data_table_problems_now"))
	_check("every declared table loaded in the engine with no problem", problems == "", problems)

	print("")
	print("=== 1. a hit is an EVENT; the wanted level and the gangs hear it ===")
	gm.call("tap_gameplay_events_now", true)
	wanted.call("clear_now", pid)
	helper.call("hit_by", civ, player, 5.0)
	await _tick(2)
	var log1 := str(gm.call("gameplay_event_log_now"))
	_check("Health published Damaged with the player as the actor", "Damaged:PLAYER" in log1, log1)
	_check("the wanted level heard it: assaulting a civilian is a star", int(wanted.call("stars_now", pid)) >= 1,
		"%d star(s)" % int(wanted.call("stars_now", pid)))
	helper.call("hit_by", thug, player, 5.0)
	await _tick(2)
	_check("the gangs heard theirs: a hit member is gang heat", int(gangs.call("gang_stars_now", pid, "gang_a")) >= 1,
		"gang_a %d star(s)" % int(gangs.call("gang_stars_now", pid, "gang_a")))

	print("")
	print("=== 2. controls: a SANCTIONED act, and an AI's act, are no crime of the player's ===")
	wanted.call("clear_now", pid)
	gm.call("sanction_gameplay_events_now", true)
	helper.call("hit_by", civ, player, 5.0)
	await _tick(2)
	var log2 := str(gm.call("gameplay_event_log_now"))
	_check("an activity-phase subscriber sanctioned it before the wanted level heard it", "Damaged:PLAYER:sanctioned" in log2, "")
	_check("  ... so the same hit is NO star (the star in 1 came through the stream)", int(wanted.call("stars_now", pid)) == 0,
		"%d star(s)" % int(wanted.call("stars_now", pid)))
	gm.call("sanction_gameplay_events_now", false)
	helper.call("hit_by", civ2, thug, 5.0)
	await _tick(2)
	_check("an AI hurting a civilian is an event too", "Damaged:AI" in str(gm.call("gameplay_event_log_now")), "")
	_check("  ... and no crime of the player's", int(wanted.call("stars_now", pid)) == 0, "")
	var before := str(gm.call("gameplay_event_log_now")).count("BalanceChanged")
	saves.call("grant_profile_now", 100)
	await _tick(2)
	_check("money moving through Economy.transfer is an event", str(gm.call("gameplay_event_log_now")).count("BalanceChanged") == before + 1, "")

	print("")
	print("=== 3. the ledger: a story character killed stays dead ===")
	var boss: Node3D = await _spawn_ai(BOSS, "enemy", true, Vector3(20, 0, 20))
	_check("the story character is alive and registered", director.call("is_named_character_loaded", BOSS), "")
	helper.call("hit_by", thug, player, 1.0e6)
	await _tick(2)
	_check("an ambient AI killed is NOT in the ledger", not saves.call("ledger_dead_now", "thug_a"), str(saves.call("ledger_json_now")))
	helper.call("hit_by", boss, player, 1.0e6)
	await _tick(2)
	_check("the ledger heard Killed: the boss is dead in this world", saves.call("ledger_dead_now", BOSS), str(saves.call("ledger_json_now")))
	if is_instance_valid(boss):
		boss.queue_free()
	await _tick(4)
	var again: Node3D = await _spawn_ai(BOSS, "enemy", true, Vector3(20, 0, 20))
	await _tick(4)
	_check("spawned again, the dead boss is removed", not is_instance_valid(again) and not director.call("is_named_character_loaded", BOSS),
		"valid %s" % is_instance_valid(again))

	print("")
	print("=== 4. save -> lose it -> load ===")
	saves.call("ledger_set_flag_now", "probe_bridge_open", "1")
	saves.call("ledger_set_place_now", "konbini_probe", "gang_b", "")
	_check("saveSlot wrote the world", saves.call("save_slot", SLOT), str(saves.call("last_save_message")))
	saves.call("ledger_reset_now")
	_check("lost: the ledger is empty", not saves.call("ledger_dead_now", BOSS) and str(saves.call("ledger_flag_now", "probe_bridge_open")) == "", "")
	var alive: Node3D = await _spawn_ai(BOSS, "enemy", true, Vector3(20, 0, 20))
	await _tick(4)
	_check("control: with no ledger entry the same boss spawns and LIVES", is_instance_valid(alive) and director.call("is_named_character_loaded", BOSS), "")
	_check("loadSlot read it", saves.call("load_slot", SLOT), str(saves.call("last_save_message")))
	await _tick(4)
	_check("the death is back", saves.call("ledger_dead_now", BOSS), "")
	_check("the world flag is back", str(saves.call("ledger_flag_now", "probe_bridge_open")) == "1", "")
	_check("the place override is back", str(saves.call("ledger_owner_now", "konbini_probe", "gang_a")) == "gang_b", "")
	_check("the boss that was alive when the slot loaded is swept", not is_instance_valid(alive) and not director.call("is_named_character_loaded", BOSS), "")

	saves.call("delete_slot", SLOT)
	saves.call("ledger_reset_now")
	gm.call("tap_gameplay_events_now", false)
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
