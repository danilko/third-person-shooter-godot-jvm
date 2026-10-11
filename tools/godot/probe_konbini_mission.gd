extends SceneTree
## PLAN.md 4.8 gate, and TIER 2 of the mission test kit for the reference activity (PLAN.md 2.1): the konbini job
## (`game.campaign.content.KonbiniActivity` on the activity framework, placed by `game.mission.KonbiniMission` /
## `game/mission/M01_Konbini.tscn` in World.tscn's downtown under `Missions`) plays end to end in the real world,
## both outcome variants. Its stage graph alone is tier 1, `KonbiniActivityTest`.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_konbini_mission.gd -- --case=kill|spare
##
## World.tscn, the real AutoLoads and streaming. The player is set down 40 m from the shop, so the crew's zone
## streams its three named characters (neutral, story characters); then walks into the start trigger (a teleport
## into the Area3D, which fires body_entered like a walk -> GameplayEvent.ZoneEntered); the activity starts for that
## player through the ActivityDirector and the crew turns gang_a. The crew is killed and the boss wounded past half health through the ordinary damage paths
## (VehicleProbeHelper.kill / weaponHit -> ImpactManager.processHit), and he must surrender (neutral, fleeing).
## --case=kill shoots him anyway -> BOSS_KILLED and m02_informant stays locked; --case=spare waits -> BOSS_SPARED and
## m02_informant opens. `-- --control` sets the surrender threshold to 0: the boss never surrenders, and the spare
## case must FAIL (it times out in the fight).

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const MISSION := "m01_konbini"
const IDS := ["m01_boss", "m01_crew_1", "m01_crew_2"]

var fails := 0
var w: Node
var completed := []

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _on_completed(mid, winner, variant) -> void:
	completed.append([str(mid), str(variant)])

func _find_ai(n: Node, id: String) -> Node:
	var info = n.get("character_info")
	if info != null and str(info.get("character_id")) == id and n.get("story_character") == true:
		return n
	for c in n.get_children():
		var r := _find_ai(c, id)
		if r != null:
			return r
	return null

## Unlocked doors of an open shop (`_Shop`) building within 14 m of `at` -- the job's konbini is 12.7 x 18.2 m
## about it; its front door slides (auto_open), so the lock is what is asked, not how it opens.
func _open_shop_doors(at: Vector3) -> int:
	var n_open := 0
	for n in get_nodes_in_group("breakable"):
		if n.get_script() == null or not str(n.get_script().resource_path).ends_with("Door.java"):
			continue
		if (n as Node3D).global_position.distance_to(at) > 14.0 or bool(n.get("locked")):
			continue
		var up: Node = n
		while up != null:
			if str(up.name).contains("_Shop"):
				n_open += 1
				break
			up = up.get_parent()
	return n_open

func _faction(id: String) -> String:
	var ai := _find_ai(w, id)
	return "" if ai == null else str(ai.get("character_info").get("faction"))

func _wait(cond: Callable, seconds: float) -> bool:
	for i in int(seconds * 60):
		if cond.call():
			return true
		await physics_frame
	return cond.call()

func _initialize() -> void:
	var case := "spare"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--case="):
			case = a.substr(7)
	var control := "--control" in OS.get_cmdline_user_args()
	w = (load(WORLD) as PackedScene).instantiate()
	var job: Node = w.get_node("Missions/M01_Konbini")
	if control:
		job.set("surrender_health_fraction", 0.0)
		print("CONTROL: the boss never surrenders")
	root.add_child(w)
	current_scene = w
	await process_frame
	await process_frame
	var dir: Node = root.get_node("MissionDirector")
	var mm: Node = root.get_node("MissionManager")
	var rt: Node = root.get_node("ActivityRuntime")
	var saves: Node = root.get_node("SaveSystem")
	var factions: Node = root.get_node("FactionManager")
	root.get_node("EventBus").connect("mission_completed", _on_completed)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	w.add_child(helper)
	var im: Node = load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new()
	w.add_child(im)
	var player: Node3D = w.get_node("Characters/Player")
	player.get_node("Health").set("max_health", 1000000.0)
	player.get_node("Health").call("heal", 1000000.0)
	var at: Vector3 = (job as Node3D).global_position
	print("  case %s, the job at %s" % [case, at])

	# 1. the crew streams in around the shop, neutral
	player.global_position = at + Vector3(0, 1.5, -40)
	var loaded := await _wait(func():
		for id in IDS:
			if not dir.call("is_named_character_loaded", id):
				return false
		return true, 40.0)
	check("the crew streams in (3 named story characters)", loaded, str(dir.call("named_character_ids")))
	# ...and the SHOP's own building cell: the crew's zone is small and loads first, while the cell holding the
	# `_Open` konbini is a big parse, and the doors below are counted off it. "Has the world finished streaming"
	# has one owner (ZoneManager.streamingPendingNow, PLAN.md 3.35); a probe watching only its own zone cannot tell.
	var zm: Node = root.get_node("ZoneManager")
	await _wait(func(): return int(zm.call("streaming_pending_now")) == 0, 90.0)
	check("the crew loiters neutral before the job", IDS.all(func(id): return _faction(id) == "neutral"),
			str(IDS.map(func(id): return _faction(id))))
	check("no mission is running yet", not rt.call("running_now", MISSION) and not mm.call("mission_active_now"))
	check("the player's story is new: the job may be started", str(rt.call("why_not_now", MISSION, "STORY")) == "",
			str(rt.call("why_not_now", MISSION, "STORY")))
	check("player and gang_a are not hostile before the job", not factions.call("hostile_now", "player", "gang_a"))
	# THE REDESIGN (user, 2026-10-11: "the player cannot enter the store ... should be able to trigger the mission
	# while inside"): the shop is open BEFORE the job, the crew is on its pavement, not in it
	var space := root.get_world_3d().direct_space_state
	var open_doors := _open_shop_doors(at)
	check("the shop's street doors are unlocked before the job", open_doors >= 1, "%d unlocked outer door(s) within 14 m" % open_doors)
	var outside := 0
	var crew_at := []
	for id in IDS:
		var body := _find_ai(w, id) as Node3D
		if body == null:
			continue
		crew_at.append("%s %.1f m" % [id, Vector2(body.global_position.x - at.x, body.global_position.z - at.z).length()])
		var up := PhysicsRayQueryParameters3D.create(body.global_position + Vector3(0, 1.0, 0), body.global_position + Vector3(0, 9.0, 0), 1)
		if space.intersect_ray(up).is_empty():
			outside += 1
	check("the crew stands OUTSIDE, on the pavement in front of the shop", outside == IDS.size(), "%d of %d under open sky; %s" % [outside, IDS.size(), crew_at])
	var balance_before := int(saves.call("profile_balance_now"))

	# 2. walking into the trigger starts the job and turns the crew
	player.global_position = at + Vector3(0, 1.2, -3)
	var offered := await _wait(func(): return str(rt.call("offered_now")) == MISSION, 3.0)
	await _wait(func(): return false, 1.0)
	var roof := PhysicsRayQueryParameters3D.create(player.global_position + Vector3(0, 0.5, 0), player.global_position + Vector3(0, 9.0, 0), 1)
	check("the job is offered to a player standing INSIDE the shop", offered and not space.intersect_ray(roof).is_empty(),
			"a roof over the player: %s" % (not space.intersect_ray(roof).is_empty()))
	check("walking into the trigger only OFFERS the job", offered and not rt.call("running_now", MISSION)
			and IDS.all(func(id): return _faction(id) == "neutral"), "offered '%s'" % rt.call("offered_now"))
	check("the offer is an interact prompt (E), and taking it starts the job", int(root.get_node("GameManager").call("interact_offers_now")) >= 1
			and rt.call("accept_offer_now"), "%d prompt(s) on offer" % root.get_node("GameManager").call("interact_offers_now"))
	var started := await _wait(func(): return rt.call("running_now", MISSION), 3.0)
	check("the activity starts for the player", started
			and str(rt.call("participants_now", MISSION)).ends_with(":OWNER:true"), str(rt.call("participants_now", MISSION)))
	check("the legacy mission slot is not used", not mm.call("mission_active_now"))
	check("the job's overlay makes player and gang_a hostile", factions.call("hostile_now", "player", "gang_a")
			and int(factions.call("activity_overlays_now")) == 1)
	check("the boss is the marked target, with a marker over him", str(rt.call("marked_now", MISSION)) == "m01_boss"
			and rt.call("marker_on_now", "m01_boss"), str(rt.call("marked_now", MISSION)))
	check("the objective is on screen, bright", str(rt.call("objective_now")) == "Take down Kaneda's crew"
			and float(rt.call("objective_alpha_now")) > 0.95, "'%s' alpha %.2f" % [rt.call("objective_now"), rt.call("objective_alpha_now")])
	check("the offer is gone once it is taken", str(rt.call("offered_now")) == "")
	check("the FIGHT is the run's checkpoint, kept in the profile", str(rt.call("activity_checkpoint_now")) == MISSION + "/FIGHT",
			str(rt.call("activity_checkpoint_now")))
	check("the crew turns gang_a", IDS.all(func(id): return _faction(id) == "gang_a"), str(IDS.map(func(id): return _faction(id))))
	check("the job is in its FIGHT phase", str(job.get("phase")) == "FIGHT", str(job.get("phase")))
	# the shop is the `_Open` variant of its type: shut (locked) everywhere else, unlocked while the job runs
	# the shop is the `_Open` variant of its type (locked everywhere else); a SHOP door near it -- the home base --
	# is always open and is NOT the mission's to touch
	var doors := []
	var shop_doors := []
	for n in get_nodes_in_group("breakable"):
		if n.get_script() == null or not str(n.get_script().resource_path).ends_with("Door.java"):
			continue
		var d3 := n as Node3D
		# 150 m: the nearest always-open shop to the job is ~99 m away since the 2026-09-25 layout (a family
		# restaurant); the mission's own reach is doorUnlockRadius (25 m), so anything in 25..150 m is a bystander
		# (400 m since the one-row blocks of 2026-09-26 moved the nearest shop further out)
		if d3.global_position.distance_to(at) > 400.0:
			continue
		# which BUILDING it belongs to, not how far away it is: the mission shop is a `_Open` variant, a shop (and
		# the home base) a `_Shop` one
		var owner_name := ""
		var up: Node = n
		while up != null and owner_name == "":
			if str(up.name).contains("_Open") or str(up.name).contains("_Shop"):
				owner_name = str(up.name)
			up = up.get_parent()
		if owner_name.contains("_Open"):
			# the mission's own building is within its unlock reach; other `_Open` buildings (civic plots, placed
			# 2026-09-29) are other missions' and stay locked
			if d3.global_position.distance_to(at) > float(job.get("door_unlock_radius")):
				continue
			# an INTERIOR door (staff room, toilet: automatic, never locked) is not the shop's to lock or unlock
			if not bool(n.get("auto_open")):
				doors.append(n)
		elif owner_name.contains("_Shop"):
			shop_doors.append(n)
	for d in doors:
		print("    mission door %s at %s, %.1f m from the job, locked=%s" % [d.name, (d as Node3D).global_position,
				(d as Node3D).global_position.distance_to(at), d.get("locked")])
	# since 2026-10-11 the job's shop is an ordinary open konbini (`_Shop`): the job holds no door of its own
	check("the job holds no door: its shop is an open one", doors.size() == 0 and int(job.call("unlocked_doors_now")) == 0,
			"%d locked-building door(s) in reach, unlocked %s" % [doors.size(), job.call("unlocked_doors_now")])
	check("an always-open shop door nearby was left alone", shop_doors.size() > 0
			and shop_doors.all(func(d): return not bool(d.get("locked"))), "%d shop door(s)" % shop_doors.size())

	# 3. the crew down, the boss past half health -> he surrenders
	for id in ["m01_crew_1", "m01_crew_2"]:
		helper.call("kill", _find_ai(w, id))
	await _wait(func(): return false, 0.3)
	check("with the crew up the boss has not surrendered", str(job.get("phase")) == "FIGHT", str(job.get("phase")))
	var boss := _find_ai(w, "m01_boss")
	helper.call("weapon_hit", im, boss, 60.0)
	var surrendered := await _wait(func(): return str(job.get("phase")) == "SURRENDER", 2.0)
	check("wounded past half with no crew, the boss surrenders", surrendered,
			"phase %s, boss health %.0f" % [job.get("phase"), boss.get_node("Health").call("health_now")])
	check("the objective changes with the stage", str(rt.call("objective_now")).begins_with("Kaneda gives up"), str(rt.call("objective_now")))
	if surrendered:
		check("a surrendered boss is neutral and fleeing", _faction("m01_boss") == "neutral"
				and str(dir.call("state_name_of", "m01_boss")) == "FLEE", "%s / %s" % [_faction("m01_boss"),
				dir.call("state_name_of", "m01_boss")])

	# 4. the choice
	var want := "BOSS_KILLED" if case == "kill" else "BOSS_SPARED"
	if case == "kill":
		helper.call("kill", boss)
	var done := await _wait(func(): return not completed.is_empty(), 25.0)
	check("the mission completes as %s" % want, done and completed[-1] == [MISSION, want], str(completed))
	check("the player's own story records the variant", rt.call("achieved_now", MISSION, want) and dir.call("has_achieved", MISSION, want))
	var res := str(rt.call("last_results_now"))
	check("one result for the one participant, with story credit", res.begins_with("%s COMPLETED %s OWNER STORY credit=true world=%s" % [
			MISSION, want, "true" if case == "kill" else "false"]), res)
	check("the boss is %s in the world's ledger" % ("dead" if case == "kill" else "not dead"),
			bool(saves.call("ledger_dead_now", "m01_boss")) == (case == "kill"))
	var paid := int(saves.call("profile_balance_now")) - balance_before
	check("the reward is paid to the participant's profile", paid > 0 and res.contains("pay=%d" % paid), "paid %d" % paid)
	check("a campaign checkpoint was taken, the activity's is forgotten", rt.call("has_story_checkpoint_now")
			and str(rt.call("activity_checkpoint_now")) == "", str(rt.call("activity_checkpoint_now")))
	check("the overlay is gone with the job", int(factions.call("activity_overlays_now")) == 0
			and not factions.call("hostile_now", "player", "gang_a"))
	# "is it over?" (user, 2026-10-11): a banner says so, and the pause menu's MISSIONS tab keeps the record
	check("a MISSION COMPLETE banner names the job and the pay", str(rt.call("result_banner_now")).begins_with("MISSION COMPLETE -- The konbini job")
			and str(rt.call("result_banner_now")).contains("¥"), str(rt.call("result_banner_now")))
	check("the mission log lists it COMPLETED, with how it ended", str(rt.call("mission_log_now")).contains("The konbini job|COMPLETED|boss " + ("spared" if case == "spare" else "killed")),
			str(rt.call("mission_log_now")))
	check("it cannot be started again", str(rt.call("why_not_now", MISSION, "STORY")) == "already completed",
			str(rt.call("why_not_now", MISSION, "STORY")))
	var unlocked: bool = dir.call("is_mission_unlocked", "m02_informant")
	check("m02_informant is %s" % ("open" if case == "spare" else "still locked"), unlocked == (case == "spare"), str(unlocked))
	check("the job's shop is still open once the job is over", _open_shop_doors(at) >= 1, "%d unlocked outer door(s)" % _open_shop_doors(at))
	check("the always-open shop door is still open after the job", shop_doors.size() > 0
			and shop_doors.all(func(d): return not bool(d.get("locked"))),
			str(shop_doors.map(func(d): return d.get("locked"))))
	check("the objective and the marker are gone with the job", str(rt.call("objective_now")) == "" and not rt.call("marker_on_now", "m01_boss"),
			str(rt.call("objective_now")))
	check("the job is DONE", str(job.get("phase")) == "DONE" and str(job.get("outcome")) == want,
			"%s %s" % [job.get("phase"), job.get("outcome")])
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
