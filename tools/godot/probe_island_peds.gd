extends SceneTree
## probe_island_peds.gd -- the ISLAND is populated: the shipped PedZones block (PLAN.md 3.6d / 3.6). Headless.
##
##   godot --headless --path . --script tools/godot/probe_island_peds.gd [-- --control]
##
## `probe_ped_crowd.gd` asserts the crowd MECHANISM on a zone it builds itself. This one asserts the DERIVED
## PLACEMENT that `tools/island_buildings.py write` puts in World.tscn: that the island's streets carry people,
## that they stand on the footways the same tool derived, that a player's arrival promotes them, and that the
## number in range at once stays inside the budget `probe_city_perf.gd --crowd` was measured against.
##
## `--control` puts every crowd zone's load radius back below the 252 m cell pitch (so only the cell you are
## standing in ever streams), which is the radius decision this change makes: the street 150 m ahead is then empty.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const SIDEWALKS := "res://src/main/resources/com/openworld/world/IslandSidewalks.json"
const CONTROL_LOAD := 250.0     # just under the 252 m cell pitch: your own cell and nothing else
const COVER_R := 150.0          # "the street around the player has people on it"
const COVER_MIN := 20
const AHEAD_R := 300.0          # ... and so does the one two blocks ahead, BEFORE you get there: the crowd
const AHEAD_MIN := 15           # must already be walking when it comes into view, which is the load radius
const BUDGET := 150             # measured in probe_city_perf.gd --crowd: 150 peds is p50 12.7 ms downtown
const PED_MAX := 40             # island_buildings.PED_MAX

var w: Node
var player: Node3D
var args := {}
var pass_n := 0
var fail_n := 0
var walks := []          # [PackedVector3Array] the derived footways, for the placement check


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


func _collect(n: Node, ends: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(ends):
		out.append(n)
	for c in n.get_children():
		_collect(c, ends, out)


func _crowds() -> Array:
	var out := []
	_collect(w, "PedCrowd.java", out)
	return out


func _peds() -> Array:
	## Every light ped's node, over every loaded crowd.
	var out := []
	for c in _crowds():
		for p in c.get_children():
			if p is Node3D:
				out.append(p)
	return out


func _walkers() -> Array:
	## Every promoted body: a full AICharacter driven by the sidewalk brain.
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


func _near(list: Array, at: Vector3, r: float) -> int:
	var n := 0
	for b in list:
		var p: Vector3 = (b as Node3D).global_position
		if Vector2(p.x - at.x, p.z - at.z).length() <= r:
			n += 1
	return n


func _wait(seconds: float) -> void:
	var t := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t < int(seconds * 1000.0):
		await process_frame


func _load_walks() -> void:
	var doc = JSON.parse_string(FileAccess.get_file_as_string(SIDEWALKS))
	for s in doc["sidewalks"]:
		var pts := PackedVector3Array()
		for p in s["points"]:
			pts.append(Vector3(p[0], p[1], p[2]))
		walks.append(pts)


func _footway_error(at: Vector3) -> float:
	## Vertical distance to the nearest derived footway point within 4 m in plan; 1e9 when there is none.
	var best := 1e9
	for pts in walks:
		for p in pts:
			if absf(p.x - at.x) > 4.0 or absf(p.z - at.z) > 4.0:
				continue
			if Vector2(p.x - at.x, p.z - at.z).length() <= 4.0:
				best = minf(best, absf(p.y - at.y))
	return best


func _run() -> void:
	_load_walks()
	w = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	await process_frame
	var zm := root.get_node_or_null("/root/ZoneManager")
	player = w.get_node_or_null("Characters/Player")
	var holder := w.get_node_or_null("PedZones")
	if zm == null or player == null or holder == null:
		print("RESULT FAIL (no ZoneManager / Player / PedZones in World.tscn)")
		quit(1)
		return
	zm.set("debug_log", false)
	player.get_node("Health").set("max_health", 1000000.0)
	player.set_physics_process(false)

	# --- the shipped block itself
	var markers := holder.get_children()
	var total := 0
	var busiest: Node3D = null
	var busiest_n := 0
	var bad := 0
	for m in markers:
		var z = m.get("zone")
		var n := 0
		for c in z.get("spawn_configs"):
			if str(c.get("behavior")) != "sidewalk":
				bad += 1                                  # a crowd zone carries nothing else
			elif str(c.get("weapon_scene_path")) != "":
				bad += 1                                  # an armed "pedestrian" is not one
			else:
				n += int(c.get("count"))
		if n > PED_MAX or n < 1:
			bad += 1
		total += n
		if n > busiest_n:
			busiest_n = n
			busiest = m
		if _arg("control", false):
			z.set("load_radius", CONTROL_LOAD)
			z.set("unload_radius", CONTROL_LOAD + 120.0)
	print("  PedZones: %d crowd zones, %d pedestrians, busiest %d at %s"
		% [markers.size(), total, busiest_n, busiest.global_position if busiest else Vector3.ZERO])
	check(markers.size() >= 50, "the island's streets carry crowd zones (%d)" % markers.size())
	check(total >= 300, "the island is populated (%d pedestrians derived)" % total)
	check(bad == 0, "every crowd is one unarmed pedestrian group inside the per-cell cap (%d bad)" % bad)

	# --- stand in the busiest cell
	player.global_position = busiest.global_position + Vector3(0, 2, 0)
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 25000 and _peds().is_empty():
		await process_frame
	await _wait(4.0)
	var peds := _peds()
	var walkers := _walkers()
	var in_range := peds.size() + walkers.size()
	var cover := _near(peds, player.global_position, COVER_R) + _near(walkers, player.global_position, COVER_R)
	print("  standing downtown: %d crowds, %d light peds, %d promoted, %d within %.0f m"
		% [_crowds().size(), peds.size(), walkers.size(), cover, COVER_R])
	check(cover >= COVER_MIN, "the street around the player has people on it (%d within %.0f m)" % [cover, COVER_R])
	check(in_range <= BUDGET,
		"the crowd in range stays inside the measured budget (%d <= %d)" % [in_range, BUDGET])
	var ahead := (_near(peds, player.global_position, AHEAD_R) + _near(walkers, player.global_position, AHEAD_R)
		- cover)
	check(ahead >= AHEAD_MIN,
		"the streets ahead are already populated before the player reaches them (%d between %.0f and %.0f m)"
		% [ahead, COVER_R, AHEAD_R])
	check(walkers.size() > 0, "the player's arrival promoted pedestrians into real bodies (%d)" % walkers.size())
	var far_bodies := 0
	for b in walkers:
		var p: Vector3 = (b as Node3D).global_position
		if Vector2(p.x - player.global_position.x, p.z - player.global_position.z).length() > 110.0:
			far_bodies += 1
	check(far_bodies == 0, "no full body is kept for a pedestrian out of reach (%d)" % far_bodies)

	# --- they stand on the footways the same tool derived, and they walk
	var worst := 0.0
	var off := 0
	for b in peds:
		var e := _footway_error((b as Node3D).global_position)
		if e > 1.5:
			off += 1
		elif e < 1e8:
			worst = maxf(worst, e)
	check(off == 0, "every ped stands on a derived footway (%d off, worst %.2f m of height)" % [off, worst])
	var before := []
	for b in peds:
		before.append((b as Node3D).global_position)
	await _wait(4.0)
	var moved := 0
	for i in range(peds.size()):
		if is_instance_valid(peds[i]) and (peds[i] as Node3D).global_position.distance_to(before[i]) > 1.0:
			moved += 1
	check(moved > peds.size() * 0.7, "the crowd walks (%d of %d peds moved)" % [moved, peds.size()])
	var hostile := 0
	for b in walkers:
		var info = b.get("character_info")
		if info != null and str(info.get("faction")) != "neutral":
			hostile += 1
	check(hostile == 0, "every promoted pedestrian is neutral (%d are not)" % hostile)

	# --- walk two cells away: the crowd behind is handed back and unloaded, the one ahead streams
	var away: Vector3 = busiest.global_position + Vector3(700, 2, 0)
	player.global_position = away
	await _wait(8.0)
	var back := _near(_peds(), busiest.global_position, 60.0) + _near(_walkers(), busiest.global_position, 60.0)
	check(back == 0, "the crowd left behind was unloaded with its zone (%d left)" % back)

	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fail_n == 0 else "FAIL", pass_n, fail_n])
	quit(1 if fail_n > 0 else 0)
