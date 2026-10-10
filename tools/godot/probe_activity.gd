extends SceneTree
## PLAN.md 2.1 / CR6, TIER 2 of the mission test kit: one generic headless stand that runs an ACTIVITY in the real
## world (World.tscn, the real AutoLoads, streaming) and drives a scripted case through the framework's lifecycle --
## what the tier-1 JUnit kit (FakeActivityHost) cannot see: real bodies, doors, the faction overlay, the profile, the
## ledger. `probe_konbini_mission.gd` is the same tier for the mission's own two outcomes.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_activity.gd -- \
##       --activity=m01_konbini --script=fail_retry|replay [--control]
##
##   fail_retry  the run FAILS from outside (as an arrest does): the crew gets its faction back, the doors lock, the
##               overlay goes, nothing is credited or paid, the checkpoint stays; RETRY starts it again from the
##               checkpoint stage and it can then be completed.
##               --control: a retry is asked for with NO failed run behind it: it must be refused ("nothing to
##               retry"), and the case's own "a retry starts the run again" line must then FAIL.
##   replay      complete it (spared), then REPLAY it and shoot the boss: the sandbox writes nothing -- no variant, no
##               flag, no ledger entry, no pay, no campaign checkpoint moved.
##               --control: the same kill in STORY mode DOES kill him in the ledger, and the replay is then refused
##               ("cannot be replayed in this world") -- so "the ledger did not change" above is not vacuous.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const CREW := ["m01_boss", "m01_crew_1", "m01_crew_2"]

var fails := 0
var w: Node
var rt: Node
var dir: Node
var saves: Node
var factions: Node
var helper: Node
var im: Node
var failed := []
var completed := []

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _find_ai(n: Node, id: String) -> Node:
	var info = n.get("character_info")
	if info != null and str(info.get("character_id")) == id and n.get("story_character") == true:
		return n
	for c in n.get_children():
		var r := _find_ai(c, id)
		if r != null:
			return r
	return null

func _faction(id: String) -> String:
	var ai := _find_ai(w, id)
	return "" if ai == null else str(ai.get("character_info").get("faction"))

func _wait(cond: Callable, seconds: float) -> bool:
	for i in int(seconds * 60):
		if cond.call():
			return true
		await physics_frame
	return cond.call()

func _finish() -> void:
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)

func _initialize() -> void:
	var activity := "m01_konbini"
	var script := "fail_retry"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--activity="):
			activity = a.substr(11)
		if a.begins_with("--script="):
			script = a.substr(9)
	var control := "--control" in OS.get_cmdline_user_args()
	if activity != "m01_konbini" or not (script in ["fail_retry", "replay"]):
		print("no case '%s' for activity '%s'" % [script, activity])
		quit(2)
		return
	w = (load(WORLD) as PackedScene).instantiate()
	var job: Node = w.get_node("Missions/M01_Konbini")
	job.set("spare_seconds", 2.0)
	root.add_child(w)
	current_scene = w
	await process_frame
	await process_frame
	rt = root.get_node("ActivityRuntime")
	dir = root.get_node("MissionDirector")
	saves = root.get_node("SaveSystem")
	factions = root.get_node("FactionManager")
	root.get_node("EventBus").connect("mission_failed", func(id, why): failed.append([str(id), str(why)]))
	root.get_node("EventBus").connect("mission_completed", func(id, _who, variant): completed.append([str(id), str(variant)]))
	helper = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	w.add_child(helper)
	im = load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new()
	w.add_child(im)
	var player: Node3D = w.get_node("Characters/Player")
	player.get_node("Health").set("max_health", 1000000.0)
	player.get_node("Health").call("heal", 1000000.0)
	var at: Vector3 = (job as Node3D).global_position
	print("  activity %s, script %s%s, placed at %s" % [activity, script, " (CONTROL)" if control else "", at])
	player.global_position = at + Vector3(0, 1.5, -12)
	var loaded := await _wait(func(): return CREW.all(func(id): return dir.call("is_named_character_loaded", id)), 40.0)
	check("the cast streams in", loaded, str(dir.call("named_character_ids")))
	await _wait(func(): return int(root.get_node("ZoneManager").call("streaming_pending_now")) == 0, 90.0)
	if script == "fail_retry":
		await _fail_retry(activity, job, control)
	else:
		await _replay(activity, job, control)
	_finish()

func _fail_retry(activity: String, job: Node, control: bool) -> void:
	if control:
		check("CONTROL: with no failed run there is nothing to retry", str(rt.call("retry_now")) == "nothing to retry",
				str(rt.call("retry_now")))
		check("CONTROL: and nothing runs", str(rt.call("running_ids_now")) == "", str(rt.call("running_ids_now")))
		# the case below must NOT pass without a failed run behind it
		check("a retry starts the run again from its checkpoint", str(rt.call("stage_now", activity)) == "FIGHT",
				"stage '%s'" % rt.call("stage_now", activity))
		return
	var balance := int(saves.call("profile_balance_now"))
	check("it starts", str(rt.call("start_now", activity, "STORY")) == "" and str(rt.call("stage_now", activity)) == "FIGHT",
			str(rt.call("stage_now", activity)))
	check("the crew is hostile, doors are held", CREW.all(func(id): return _faction(id) == "gang_a")
			and int(rt.call("doors_held_now", activity)) > 0, "%d door(s)" % rt.call("doors_held_now", activity))
	rt.call("fail_now", activity, "player_arrested")
	await physics_frame
	check("failing it from outside ends the run", not rt.call("running_now", activity) and failed == [[activity, "player_arrested"]],
			str(failed))
	check("a failed run gives the crew its faction back", CREW.all(func(id): return _faction(id) == "neutral"),
			str(CREW.map(func(id): return _faction(id))))
	check("... locks the doors and drops the overlay", int(factions.call("activity_overlays_now")) == 0
			and not factions.call("hostile_now", "player", "gang_a") and str(job.get("phase")) == "DONE"
			and str(job.get("outcome")) == "FAILED: player_arrested", "%s %s" % [job.get("phase"), job.get("outcome")])
	check("... credits and pays nothing", not rt.call("achieved_now", activity, "")
			and int(saves.call("profile_balance_now")) == balance
			and str(rt.call("last_results_now")).contains("FAILED") and str(rt.call("last_results_now")).contains("credit=false"),
			str(rt.call("last_results_now")))
	check("... and keeps its checkpoint", str(rt.call("activity_checkpoint_now")) == activity + "/FIGHT",
			str(rt.call("activity_checkpoint_now")))
	check("a retry starts the run again from its checkpoint", str(rt.call("retry_now")) == ""
			and str(rt.call("stage_now", activity)) == "FIGHT", "stage '%s'" % rt.call("stage_now", activity))
	check("the crew is hostile again", CREW.all(func(id): return _faction(id) == "gang_a"))
	helper.call("kill", _find_ai(w, "m01_boss"))
	var done := await _wait(func(): return not completed.is_empty(), 5.0)
	check("the retried run completes", done and completed[-1] == [activity, "BOSS_KILLED"]
			and rt.call("achieved_now", activity, "BOSS_KILLED"), str(completed))
	check("a completed run forgets its checkpoint", str(rt.call("activity_checkpoint_now")) == "",
			str(rt.call("activity_checkpoint_now")))

func _replay(activity: String, _job: Node, control: bool) -> void:
	check("a replay of something never completed is refused", str(rt.call("why_not_now", activity, "REPLAY")) == "not completed yet",
			str(rt.call("why_not_now", activity, "REPLAY")))
	check("it starts", str(rt.call("start_now", activity, "STORY")) == "")
	for id in ["m01_crew_1", "m01_crew_2"]:
		helper.call("kill", _find_ai(w, id))
	var boss := _find_ai(w, "m01_boss")
	if control:
		# the SAME kill, in the story: it must reach the ledger, and the replay must then be refused
		helper.call("kill", boss)
		await _wait(func(): return not completed.is_empty(), 5.0)
		check("CONTROL: the story kill is in the ledger", bool(saves.call("ledger_dead_now", "m01_boss")))
		check("CONTROL: a replay is refused where the boss is dead", str(rt.call("why_not_now", activity, "REPLAY"))
				.begins_with("cannot be replayed in this world"), str(rt.call("why_not_now", activity, "REPLAY")))
		check("the replay leaves the boss alive in the ledger", not bool(saves.call("ledger_dead_now", "m01_boss")))
		return
	helper.call("weapon_hit", im, boss, 60.0)
	var spared := await _wait(func(): return not completed.is_empty(), 12.0)
	check("the story run completes BOSS_SPARED", spared and completed[-1] == [activity, "BOSS_SPARED"], str(completed))
	var balance := int(saves.call("profile_balance_now"))
	check("the informant branch is open", rt.call("requirement_met_now", "m02_informant"))
	check("the replay is offered: the boss is alive here", str(rt.call("why_not_now", activity, "REPLAY")) == "",
			str(rt.call("why_not_now", activity, "REPLAY")))
	check("the replay starts", str(rt.call("start_now", activity, "REPLAY")) == "" and str(rt.call("stage_now", activity)) == "FIGHT",
			str(rt.call("stage_now", activity)))
	completed.clear()
	helper.call("kill", boss)
	var done := await _wait(func(): return not completed.is_empty(), 5.0)
	var res := str(rt.call("last_results_now"))
	check("the replay completes BOSS_KILLED -- another choice than the story's", done and completed[-1] == [activity, "BOSS_KILLED"],
			str(completed))
	check("its result is a REPLAY's: no credit, no world effect, no pay", res.contains("REPLAY credit=false world=false pay=0"), res)
	check("the replay leaves the boss alive in the ledger", not bool(saves.call("ledger_dead_now", "m01_boss")))
	check("the story still says BOSS_SPARED and only that", rt.call("achieved_now", activity, "BOSS_SPARED")
			and not rt.call("achieved_now", activity, "BOSS_KILLED"))
	check("the informant branch is still open", rt.call("requirement_met_now", "m02_informant"))
	check("nothing was paid", int(saves.call("profile_balance_now")) == balance, str(int(saves.call("profile_balance_now")) - balance))
