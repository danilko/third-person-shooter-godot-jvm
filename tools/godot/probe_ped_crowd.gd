extends SceneTree
## probe_ped_crowd.gd -- the ambient crowd's two tiers (PLAN.md 3.6d). Headless.
##
##   godot --headless --path . --script tools/godot/probe_ped_crowd.gd [-- --control] [--count=120]
##
## Runs World.tscn with the real ZoneManager, PlayerRegistry and sidewalk data, drops one zone whose only
## SpawnConfig is `behavior = "sidewalk"`, and asserts the LOD both ways:
##   * the zone fills a PedCrowd with script-free peds and spawns NO character body for them;
##   * the peds walk, and they walk on the footway (their height stays at footway height);
##   * a player who comes near PROMOTES the ones in reach into real AICharacters carrying a
##     SidewalkWalkerController -- and the crowd loses exactly those;
##   * a player who leaves DEMOTES them back, so walking the length of a district does not promote the
##     whole crowd and keep it.
## `--control` turns `ZoneManager.light_crowd` off: the same zone then spawns every pedestrian as a full body,
## which is what this did before 3.6d, and the first two cases fail.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const ZONE_JAVA := "res://src/main/java/com/openworld/world/Zone.java"
const MARKER_JAVA := "res://src/main/java/com/openworld/world/ZoneMarker.java"
const SPAWN_JAVA := "res://src/main/java/com/openworld/world/SpawnConfig.java"
## Downtown, where `tools/island_buildings.py` derived footways: the crowd needs a sidewalk to stand on.
const AT := Vector3(560, 0.75, -350)
## Far enough that nothing promotes (the crowd's 80 m), near enough that the zone still STREAMS (its 900 m
## load radius): a player who leaves the load radius unloads the zone, which would test nothing.
const FAR := Vector3(560, 0.75, -50)

var w: Node
var player: Node3D
var args := {}
var pass_n := 0
var fail_n := 0


func _arg(k: String, d = null):
	return args.get(k, d)


func check(ok: bool, what: String) -> void:
	if ok:
		pass_n += 1
		print("PASS ", what)
	else:
		fail_n += 1
		print("FAIL ", what)


func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()


func _zm() -> Node:
	return root.get_node_or_null("/root/ZoneManager")


func _crowds() -> Array:
	var out := []
	_collect(w, "PedCrowd.java", out)
	return out


func _collect(n: Node, ends: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(ends):
		out.append(n)
	for c in n.get_children():
		_collect(c, ends, out)


func _ped_total() -> int:
	var n := 0
	for c in _crowds():
		n += int(c.call("ped_count"))
	return n


func _walkers() -> Array:
	# Every full body driven by the sidewalk brain: the promoted tier.
	var out := []
	for n in get_nodes_in_group("characters"):
		if not (n is CharacterBody3D):
			continue
		for c in n.get_children():
			var s = c.get_script()
			if s != null and str(s.resource_path).ends_with("SidewalkWalkerController.java"):
				out.append(n)
				break
	return out


func _put_player(at: Vector3) -> void:
	player.global_position = at


func _wait(seconds: float) -> void:
	var t := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t < int(seconds * 1000.0):
		await process_frame


func _make_zone(id: String, at: Vector3, count: int) -> Node3D:
	var z: Resource = load(ZONE_JAVA).new()
	z.set("zone_id", id)
	z.set("size", Vector3(360, 20, 360))
	z.set("load_radius", 900.0)
	z.set("unload_radius", 1400.0)
	var sc: Resource = load(SPAWN_JAVA).new()
	sc.set("count", count)
	sc.set("behavior", "sidewalk")
	sc.set("faction", "neutral")
	sc.set("weapon_scene_path", "")
	z.get("spawn_configs").append(sc)
	var m: Node3D = load(MARKER_JAVA).new()
	m.set("zone", z)
	m.set("show_debug_volume", false)
	w.add_child(m)
	m.global_position = at
	return m


func _run() -> void:
	var want := int(_arg("count", 120))
	w = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w          # ZoneManager finds the Characters container through the CURRENT scene
	await process_frame
	var zm := _zm()
	if zm == null:
		print("RESULT FAIL (no ZoneManager autoload)")
		quit(1)
		return
	zm.set("light_crowd", not _arg("control", false))
	zm.set("debug_log", false)
	# The island ships its own crowd (PLAN.md 3.6d, `island_buildings.py`'s PedZones block), and this probe
	# measures ONE zone it builds itself -- so drop the shipped block, or the counts below are the world's.
	var shipped := w.get_node_or_null("PedZones")
	if shipped != null:
		shipped.free()
	player = w.get_node_or_null("Characters/Player")
	if player == null:
		print("RESULT FAIL (no player in World.tscn)")
		quit(1)
		return
	player.get_node("Health").set("max_health", 1000000.0)
	# Invulnerable, not just a big max: parked at FAR the player was killed (max_health does not raise the
	# CURRENT health), game-over PAUSED the tree, and every crowd stopped ticking -- which read as "the crowd
	# does not hear a gunshot".
	player.get_node("Health").set("invulnerable", true)
	player.set_physics_process(false)     # the probe teleports it; nothing here tests movement
	_put_player(FAR)
	await _wait(3.0)

	var before_set := get_nodes_in_group("characters")
	var m := _make_zone("probe_peds", AT, want)
	# The zone streams in as a task; give it room, then let the crowd walk.
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 25000 and _ped_total() == 0 and _walkers().is_empty():
		await process_frame
	await _wait(3.0)

	var peds := _ped_total()
	var walkers := _walkers().size()
	print("  crowd: %d light peds, %d full walkers (asked %d)" % [peds, walkers, want])
	check(peds > want * 0.5, "the zone filled its crowd (%d light peds of %d asked)" % [peds, want])
	check(walkers == 0, "no full body was spawned for a pedestrian out of reach (%d)" % walkers)
	var added := []
	for c in get_nodes_in_group("characters"):
		if not before_set.has(c):
			added.append(c)
	print("  characters group grew by %d: %s" % [added.size(), added.map(func(c): return "%s(%s)" % [c.name, c.get_class()])])
	# traffic streams in round the stand too (3.32's ring): a car, or a body seated in one, is not the crowd's
	var foot := added.filter(func(c): return not (c is RigidBody3D) and c.get("current_vehicle_node") == null)
	check(foot.is_empty(), "the crowd added nothing on foot to the characters group (%d traffic bodies aside)"
		% (added.size() - foot.size()))

	# They walk, and they walk on the footway.
	var crowd: Node = _crowds()[0] if not _crowds().is_empty() else null
	var walked0: float = crowd.call("walked_total_now") if crowd else 0.0
	var ys := []
	var p0 := []
	if crowd:
		for v in crowd.call("ped_positions_now"):
			p0.append(v)
	await _wait(4.0)
	var walked1: float = crowd.call("walked_total_now") if crowd else 0.0
	var moved := 0
	var i := 0
	if crowd:
		for v in crowd.call("ped_positions_now"):
			if i < p0.size():
				if (v as Vector3).distance_to(p0[i]) > 1.0:
					moved += 1
				ys.append((v as Vector3).y)
				i += 1
	check(walked1 - walked0 > peds * 2.0,
		"the crowd walked (%.0f m in 4 s over %d peds)" % [walked1 - walked0, peds])
	check(moved > peds * 0.8, "%d of %d peds moved more than 1 m" % [moved, peds])
	var y_lo := 1e9
	var y_hi := -1e9
	for y in ys:
		y_lo = minf(y_lo, y)
		y_hi = maxf(y_hi, y)
	check(ys.is_empty() or (y_hi - y_lo) < 12.0,
		"every ped is on a footway, not in the air or under the ground (y %.2f..%.2f)" % [y_lo, y_hi])

	# Promotion: stand next to the crowd.
	var target := AT
	if crowd and crowd.get_child_count() > 0:
		target = crowd.call("ped_positions_now")[0]
	_put_player(target + Vector3(0, 1.0, 0))
	await _wait(4.0)
	var peds_near := _ped_total()
	var walkers_near := _walkers().size()
	print("  with the player in the crowd: %d light peds, %d full walkers" % [peds_near, walkers_near])
	check(walkers_near > 0, "a player in reach promoted %d peds to real bodies" % walkers_near)
	check(peds_near < peds, "the crowd gave them up (%d -> %d light peds)" % [peds, peds_near])
	check(peds_near + walkers_near >= peds - 2,
		"nobody was lost in the swap (%d + %d vs %d)" % [peds_near, walkers_near, peds])

	# Demotion: walk away again. A promoted body is held for 10 s after its promotion (ZoneManager
	# DEMOTE_AFTER_MSEC: a body a player just dealt with stays one), so wait past that.
	_put_player(FAR)
	await _wait(12.0)
	var peds_far := _ped_total()
	var walkers_far := _walkers().size()
	print("  after walking away: %d light peds, %d full walkers" % [peds_far, walkers_far])
	check(walkers_far == 0, "every promoted body was handed back (%d left)" % walkers_far)
	check(peds_far >= peds_near, "the crowd took them back (%d -> %d)" % [peds_near, peds_far])

	# Fight back: every ped a fighter, a gunshot 60 m from the crowd, the player 70 m off (outside the 25 m
	# promote ring, inside the 120 m panic range). Exactly the FIGHTER BUDGET are promoted -- armed or fists,
	# turned `vigilante` (ZoneManager.FIGHTER_FACTION), keeping the ordinary AI brain -- and no more.
	if crowd and not _arg("control", false):
		crowd.set("fight_percent", 100)
		crowd.set("cower_percent", 0)
		var here: Vector3 = crowd.call("ped_positions_now")[0]
		_put_player(here + Vector3(70, 1.0, 0))
		await _wait(1.0)
		var sm := root.get_node_or_null("StimulusManager")
		# temperament is rolled when a ped is added, so re-roll it from the shares just set
		crowd.call("reroll_temper_now")
		sm.call("post_noise", 0, here, 150.0)
		await _wait(3.0)
		var fighters := 0
		var armed := 0
		for n in get_nodes_in_group("characters"):
			var info = n.get("character_info")
			if info != null and str(info.get("faction")) == "vigilante":
				fighters += 1
				var wc = n.get_node_or_null("WeaponController")
				if wc != null and int(wc.call("active_slot_now")) > 0: armed += 1
		var budget := int(zm.get("fighter_budget"))
		print("  a gunshot by a crowd of fighters: %d promoted to fight (%d with a weapon), budget %d" % [fighters, armed, budget])
		check(fighters == budget, "exactly the fighter budget turned to fight (%d of %d)" % [fighters, budget])
		check(int(crowd.call("promoted_now")) >= budget, "the crowd handed them over (%d promoted)" % int(crowd.call("promoted_now")))
		_put_player(FAR)
		await _wait(1.0)

	# A light ped has no collider: a shot asks the crowds (PedCrowd.shoot) and the ped it reaches becomes a
	# real body at once, whatever the budget, so the damage lands (FirearmItem.resolvePellets).
	if crowd and not _arg("control", false):
		var shot_at: Vector3 = crowd.call("ped_positions_now")[0]
		_put_player(shot_at + Vector3(0, 1.0, 70))
		await _wait(1.0)
		shot_at = crowd.call("ped_positions_now")[0]
		var before := int(crowd.call("ped_count"))
		var from := shot_at + Vector3(0, 1.2, 30)
		var at: Vector3 = crowd.call("shoot_now", from, (shot_at + Vector3(0, 1.2, 0)) - from, 100.0)
		var ok := at.y > -1000.0
		await _wait(0.5)
		var near := 0
		for n in get_nodes_in_group("characters"):
			if ok and n is Node3D and (n as Node3D).global_position.distance_to(at) < 3.0: near += 1
		check(ok and int(crowd.call("ped_count")) == before - 1 and near >= 1,
			"a shot at a light ped 70 m out made it a real body where it stood (%s, %d -> %d peds, %d body)"
			% [ok, before, int(crowd.call("ped_count")), near])
		_put_player(FAR)
		await _wait(1.0)

	# Unload frees the crowd with the zone.
	m.queue_free()
	await _wait(3.0)
	check(_ped_total() == 0, "the crowd went with its zone marker (%d peds left)" % _ped_total())

	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fail_n == 0 else "FAIL", pass_n, fail_n])
	quit(1 if fail_n > 0 else 0)
