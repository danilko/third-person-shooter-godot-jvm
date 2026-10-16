extends SceneTree
## THE CAMPAIGN FACTION LAYER (PLAN.md THE ORDER 0.35 / CR3): a story relationship survives region changes, mission
## starts / ends and a save round trip; only reset() (a new game) clears it.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_campaign_factions.gd [-- --control]
##   (--control: the story flip is made as an ordinary runtime flip, the old way -- it is lost at the first rebuild)
##
## On the real autoloads (FactionManager, SaveSystem), no scene. police <-> gang_a ships NEUTRAL, so HOSTILE is the
## observable change; police <-> gang_b is flipped as a plain runtime flip beside it, which a rebuild must still drop.

const SLOT := 7
const REGION := "res://src/main/resources/com/openworld/character/OpenWorldFactions.tres"
const MISSION := "res://src/main/resources/com/openworld/game/mission/M01_Konbini_Factions.tres"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _initialize() -> void:
	await process_frame
	var control := "--control" in OS.get_cmdline_user_args()
	var fm: Node = root.get_node("FactionManager")
	var saves: Node = root.get_node("SaveSystem")
	fm.call("reset")
	_check(not fm.call("hostile_now", "police", "gang_a"), "police and gang_a ship neutral")
	if control:
		fm.call("flip_relationship", "police", "gang_a", "HOSTILE")
	else:
		fm.call("flip_campaign_now", "police", "gang_a", "HOSTILE")
	fm.call("flip_relationship", "police", "gang_b", "HOSTILE")
	_check(fm.call("hostile_now", "police", "gang_a"), "the story turns the police on gang_a")

	fm.call("apply_table", load(REGION))
	_check(fm.call("hostile_now", "police", "gang_a"), "it survives entering a region")
	fm.call("clear_region_table")
	_check(fm.call("hostile_now", "police", "gang_a"), "and leaving it")
	_check(not fm.call("hostile_now", "police", "gang_b"), "a plain runtime flip is still dropped by a rebuild")

	fm.call("apply_mission_table", load(MISSION))
	_check(fm.call("active_layer_now") == "mission", "a mission table is the live layer")
	fm.call("clear_mission_table")
	_check(fm.call("hostile_now", "police", "gang_a"), "it is back when the mission ends")

	_check(saves.call("save_slot", SLOT), "saved: %s" % saves.call("last_save_message"))
	fm.call("reset")
	_check(not fm.call("hostile_now", "police", "gang_a"), "reset (a new game) clears it")
	_check(saves.call("load_slot", SLOT), "loaded: %s" % saves.call("last_save_message"))
	_check(fm.call("hostile_now", "police", "gang_a"), "the save brings it back")
	fm.call("clear_region_table")
	_check(fm.call("hostile_now", "police", "gang_a"), "and as the campaign layer, not a runtime flip")

	saves.call("delete_slot", SLOT) if saves.has_method("delete_slot") else null
	fm.call("reset")
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
