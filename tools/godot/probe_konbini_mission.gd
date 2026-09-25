extends SceneTree
## PLAN.md 4.8 gate: the konbini job (`game.mission.KonbiniMission`, `game/mission/M01_Konbini.tscn`, placed in
## World.tscn's downtown under `Missions`) plays end to end in the real world, both outcome variants.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_konbini_mission.gd -- --case=kill|spare
##
## World.tscn, the real AutoLoads and streaming. The player is set down 40 m from the shop, so the crew's zone
## streams its three named characters (neutral, story characters); then walks into the start trigger (a teleport
## into the Area3D, which fires body_entered like a walk); the mission starts through the director and the crew
## turns gang_a. The crew is killed and the boss wounded past half health through the ordinary damage paths
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
	check("no mission is running yet", not mm.call("mission_active_now"))

	# 2. walking into the trigger starts the job and turns the crew
	player.global_position = at + Vector3(0, 1.2, -3)
	var started := await _wait(func(): return mm.call("mission_active_now"), 3.0)
	check("the trigger starts the mission through the director", started and mm.call("active_mission_id_now") == MISSION,
			str(mm.call("active_mission_id_now")))
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
		if d3.global_position.distance_to(at) > 150.0:
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
			doors.append(n)
		elif owner_name.contains("_Shop"):
			shop_doors.append(n)
	for d in doors:
		print("    mission door %s at %s, %.1f m from the job, locked=%s" % [d.name, (d as Node3D).global_position,
				(d as Node3D).global_position.distance_to(at), d.get("locked")])
	check("the job unlocked the mission shop's doors", doors.size() > 0
			and doors.all(func(d): return not bool(d.get("locked"))) and int(job.call("unlocked_doors_now")) == doors.size(),
			"%d door(s), unlocked %s" % [doors.size(), job.call("unlocked_doors_now")])
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
	check("the director records the variant", dir.call("has_achieved", MISSION, want))
	var unlocked: bool = dir.call("is_mission_unlocked", "m02_informant")
	check("m02_informant is %s" % ("open" if case == "spare" else "still locked"), unlocked == (case == "spare"), str(unlocked))
	check("the mission shop is locked again once the job is over", doors.size() > 0
			and doors.all(func(d): return bool(d.get("locked"))), str(doors.map(func(d): return d.get("locked"))))
	check("the always-open shop door is still open after the job", shop_doors.size() > 0
			and shop_doors.all(func(d): return not bool(d.get("locked"))),
			str(shop_doors.map(func(d): return d.get("locked"))))
	check("the job is DONE", str(job.get("phase")) == "DONE" and str(job.get("outcome")) == want,
			"%s %s" % [job.get("phase"), job.get("outcome")])
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
