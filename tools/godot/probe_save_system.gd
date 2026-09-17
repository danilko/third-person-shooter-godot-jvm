extends SceneTree
## SaveSystem (PLAN.md 4.4 / I7): the campaign save, asserted on the real autoloads with a real
## Player, a real weapon taken through the ordinary pickup path and a real ZoneTrigger.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_save_system.gd
##   ... -- --control    # save_fired_beats off — the naive "only missions and variants are progress"
##                       # save. The graph still round-trips; the beat log does not, so the one-shot
##                       # ambush RE-ARMS and fires again after the load (3 checks fail).
##
## The method it always has to prove is the one the spec's verify states: reach a state, save, LOSE
## that state in this same session (the stand-in for quitting), load, and find it back. Losing it
## first is the whole point — a probe that only saves and loads cannot tell a working restore from a
## state that never went away.

const PLAYER  := "res://src/main/resources/com/openworld/character/Player.tscn"
const TRIGGER := "res://src/main/java/com/openworld/world/ZoneTrigger.java"
const WEAPON  := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const MISSION := "res://src/main/resources/com/openworld/game/mission/GangA_vs_Police_Mission.tres"

const SLOT := 7

var fails := 0
var control := false
var world: Node3D
var saves: Node
var director: Node
var factions: Node
var missions: Node
var player: Node3D

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _wc() -> Node:
	return player.get_node_or_null("WeaponController")

func _health() -> Node:
	return player.get_node_or_null("Health")

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a == "--control":
			control = true
	await process_frame

	saves    = root.get_node_or_null("SaveSystem")
	director = root.get_node_or_null("MissionDirector")
	factions = root.get_node_or_null("FactionManager")
	missions = root.get_node_or_null("MissionManager")
	if saves == null or director == null or factions == null or missions == null:
		print("RESULT FAIL (SaveSystem / MissionDirector / FactionManager / MissionManager autoload missing)")
		quit(1)
		return
	saves.set("save_fired_beats", not control)
	# Autosave is measured on purpose in case 6; everywhere else it would write slot 0 behind the
	# cases and make `saves_written` meaningless.
	saves.set("autosave_enabled", false)
	saves.call("delete_slot", SLOT)
	saves.call("delete_slot", 0)

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
	await _tick(2)

	player = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.global_position = Vector3(0, 0, 0)
	await _tick(30)
	player.get("character_info").set("faction", "player")

	print("")
	print("=== 1. reach a campaign state worth saving ===")
	director.call("reset_campaign")
	factions.call("reset")
	director.call("declare_unlock_on", "chapter_2", "prologue#SPARED")
	_check("chapter_2 starts locked", not director.call("is_mission_unlocked", "chapter_2"), "")
	director.call("on_mission_completed", "prologue", "player", "SPARED")
	director.call("trigger_beat", "ambush_gate")
	_check("the declared variant opened chapter_2", director.call("is_mission_unlocked", "chapter_2"), "")
	_check("the unique item granted once", director.call("grant_unique_once", "gold_pistol"), "")
	# The flip has to DIFFER from the shipped default or it is unobservable: two different factions
	# are hostile by the inherent rule, so a flip to HOSTILE would prove nothing. FRIENDLY does.
	factions.call("flip_relationship", "player", "gang_a", "FRIENDLY")
	_check("the runtime flip took (player/gang_a are hostile by default)",
		not factions.call("hostile_now", "player", "gang_a"), "")

	# A weapon the ordinary way: dropped on the player, auto-picked up, brought to the hand.
	var gun: Node3D = (load(WEAPON) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = player.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = _wc()
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	var armed_slot: int = int(wc.call("active_slot_now"))
	_check("the player is holding ASR1 in a real slot", armed_slot > 0 and
		String(gun.get_parent().name).begins_with("Socket"),
		"slot %d, parent %s" % [armed_slot, gun.get_parent().name])
	gun.set("magazine", 7)
	gun.set("reserve", 42)
	player.global_position = Vector3(23, 0, -11)
	_health().call("apply_replicated_health", 61.0)
	await _tick(4)

	print("")
	print("=== 2. save the slot ===")
	var before := int(saves.call("saves_written"))
	_check("the slot did not exist yet", not saves.call("has_slot", SLOT), saves.call("slot_path", SLOT))
	_check("saveSlot wrote it", saves.call("save_slot", SLOT) and saves.call("has_slot", SLOT),
		str(saves.call("last_save_message")))
	_check("and counted it", int(saves.call("saves_written")) == before + 1, "")
	var text: String = FileAccess.get_file_as_string(saves.call("slot_path", SLOT))
	var doc: Variant = JSON.parse_string(text)
	_check("the file is a JSON object of the current schema",
		doc is Dictionary and int(doc.get("schema", -1)) == 1, "%d bytes" % text.length())
	_check("it carries the campaign, the factions, the mission and a player",
		doc.has("campaign") and doc.has("factions") and doc.has("mission")
			and (doc["players"] as Array).size() == 1,
		"players %d" % (doc["players"] as Array).size())
	_check("the fired-beat log is in the document",
		"ambush_gate" in (doc["campaign"]["fired_beats"] as Array), str(doc["campaign"]["fired_beats"]))

	print("")
	print("=== 3. LOSE the state — the stand-in for quitting the game ===")
	director.call("reset_campaign")
	factions.call("reset")
	player.global_position = Vector3(-90, 0, 90)
	_health().call("apply_replicated_health", 100.0)
	gun.set("magazine", 1)
	gun.set("reserve", 0)
	await _tick(4)
	_check("the graph is gone", not director.call("is_mission_unlocked", "chapter_2")
		and not director.call("has_achieved", "prologue", "SPARED"), "")
	_check("the beat log is gone", int(director.call("beat_fire_count", "ambush_gate")) == 0, "")
	_check("the faction flip is gone (hostile by default again)",
		factions.call("hostile_now", "player", "gang_a"), "")
	_check("the unique item would be granted again",
		director.call("grant_unique_once", "gold_pistol"), "")
	director.call("reset_campaign")

	print("")
	print("=== 4. load it back ===")
	# The requirement row is AUTHORING and is re-declared by code every launch, never saved — this
	# line stands for the Java that declares the campaign at startup.
	director.call("declare_unlock_on", "chapter_2", "prologue#SPARED")
	_check("loadSlot read it", saves.call("load_slot", SLOT), str(saves.call("last_save_message")))
	await _tick(6)
	_check("the achieved variant is back", director.call("has_achieved", "prologue", "SPARED"), "")
	_check("the completed mission is back", director.call("has_completed", "prologue"), "")
	_check("chapter_2 is unlocked again", director.call("is_mission_unlocked", "chapter_2"), "")
	_check("the unique item is NOT granted a second time",
		not director.call("grant_unique_once", "gold_pistol"), "")
	_check("the faction flip is back", not factions.call("hostile_now", "player", "gang_a"), "")
	_check("the beat log is back", int(director.call("beat_fire_count", "ambush_gate")) == 1,
		"beat count %d" % int(director.call("beat_fire_count", "ambush_gate")))
	_check("the player is back where it was saved",
		player.global_position.distance_to(Vector3(23, 0, -11)) < 0.5,
		"%.2f m off" % player.global_position.distance_to(Vector3(23, 0, -11)))
	_check("its health is back", absf(float(_health().call("health_now")) - 61.0) < 0.01,
		str(_health().call("health_now")))
	# The restore reconciles onto the item already in the slot (it matches by weaponId), so the same
	# node carries the saved ammo back — no duplicate weapon is instantiated.
	_check("the magazine and reserve are back",
		int(gun.get("magazine")) == 7 and int(gun.get("reserve")) == 42,
		"%d/%d" % [int(gun.get("magazine")), int(gun.get("reserve"))])
	_check("and it is still the same item in the hand, not a duplicate",
		is_instance_valid(gun) and String(gun.get_parent().name).begins_with("Socket"),
		gun.get_parent().name if is_instance_valid(gun) else "freed")
	_check("nothing is left pending", int(saves.call("pending_player_count")) == 0,
		str(saves.call("pending_player_count")))

	print("")
	print("=== 5. the one-shot trigger stays SPENT across the load (why the beat log is saved) ===")
	var t: Area3D = load(TRIGGER).new()
	t.set("beat_id", "ambush_gate")
	t.set("one_shot", true)
	var tcs := CollisionShape3D.new()
	var tbox := BoxShape3D.new()
	tbox.size = Vector3(10, 6, 10)
	tcs.shape = tbox
	t.add_child(tcs)
	world.add_child(t)
	t.global_position = player.global_position
	await _tick(10)
	# The player is standing inside the volume as it enters the tree, so an ambush that re-armed
	# fires immediately — which is exactly what the control does.
	_check("the spent trigger stays silent", int(t.get("trigger_count")) == 0,
		"trigger_count %d, beat count %d" % [int(t.get("trigger_count")),
			int(director.call("beat_fire_count", "ambush_gate"))])
	t.queue_free()
	await _tick(2)

	print("")
	print("=== 6. the active mission is recorded, and RESTARTS rather than resuming ===")
	director.call("reset_campaign")
	_check("the mission started", missions.call("start_mission_from_path", MISSION), "")
	await _tick(4)
	saves.set("autosave_enabled", true)
	var autos := int(saves.call("saves_written"))
	director.call("trigger_beat", "autosave_probe")
	await _tick(4)
	_check("a beat autosaved", int(saves.call("saves_written")) == autos + 1
		and saves.call("has_slot", 0), str(saves.call("saves_written")))
	saves.set("autosave_enabled", false)
	_check("saveSlot recorded the running mission", saves.call("save_slot", SLOT), "")
	var doc2: Variant = JSON.parse_string(FileAccess.get_file_as_string(saves.call("slot_path", SLOT)))
	_check("the slot names it with a loadable .tres path",
		bool(doc2["mission"]["active"]) and String(doc2["mission"]["path"]).ends_with(".tres"),
		str(doc2["mission"]))
	missions.call("complete_mission_now", "police", "ELIMINATED")
	await _tick(4)
	_check("completing it left no active mission", not missions.call("mission_active_now"), "")
	_check("loading brings it back", saves.call("load_slot", SLOT) and missions.call("mission_active_now"),
		str(missions.call("mission_active_now")))

	print("")
	print("=== 7. slot housekeeping ===")
	_check("deleteSlot removes it", saves.call("delete_slot", SLOT)
		and not saves.call("has_slot", SLOT), "")
	_check("loading a missing slot is refused, not half-applied",
		not saves.call("load_slot", SLOT), str(saves.call("last_save_message")))
	saves.call("delete_slot", 0)

	print("")
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
