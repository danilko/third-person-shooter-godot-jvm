extends SceneTree
## PLAN.md 3.10 runtime gate: the island's roads stream as a 504 m grid of zones
## (`tools/island_road_zones.py`), and the grid is invisible to anyone on the road.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_island_zones.gd [-- --control]
##
## World.tscn, the real ZoneManager. The player is set down at a tour of places across the island
## (every road cell's centre, in a snake), and at each stop, once streaming has settled:
##   1. every road zone whose marker is within its LOAD radius is loaded, and none past its UNLOAD
##      radius is (the hysteresis band may be either);
##   2. every loaded piece sits at the NETWORK's transform (Y +0.6), not its marker's;
##   3. every streamed lane starts where its piece's lanekit says (0.05 m);
##   4. a successor that does not resolve names a lane of a zone that is NOT loaded -- the only
##      acceptable dangle, the cost of a cut;
##   5. every lane within 150 m of the player is streamed (no road missing where you stand).
## Then a DRIVE: the player is moved at 30 m/s along the whole tour (every cell boundary a car can
## cross), and the physics frame time is sampled; the worst frame, and the worst frame in which a
## piece entered the tree, are reported against the 4 ms stream budget.
## `-- --control` puts every road zone's load radius at 150 m (unload 200): steps 1-4 still hold
## against those radii, so the control is step 5's coverage check, which must FAIL.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const PIECES := "res://assets/world_source/pieces/%s.lanekit.json"
const NET_ORIGIN := Vector3(0, 0.6, 0)

var fails := 0
var w: Node
var zones := {}          # zone_id -> {marker, zone, load, unload, centre, piece}
var kits := {}           # zone_id -> lanekit doc
var zone_of_lane := {}   # lane id -> zone_id

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _frames(n: int) -> void:
	for i in n:
		await physics_frame

func _collect(n: Node, script_end: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(script_end):
		out.append(n)
	for c in n.get_children():
		_collect(c, script_end, out)

func _lanes() -> Dictionary:
	var arr := []
	_collect(w, "PathLaneRoute.java", arr)
	var out := {}
	for n in arr:
		if n.is_inside_tree():
			out[str(n.name)] = n
	return out

func _piece_node(zid: String) -> Node3D:
	var m: Node = zones[zid]["marker"]
	for c in m.get_children():
		if c is Node3D and str(c.scene_file_path).get_file().get_basename() == zones[zid]["piece"]:
			return c
	return null

func _loaded() -> Array:
	var out := []
	for zid in zones:
		if _piece_node(zid) != null:
			out.append(zid)
	return out

func _settle(seconds: float) -> void:
	# Streaming is a per-frame state machine; wait until the loaded set has not changed for 1 s.
	var last := []
	var still := 0
	for i in int(seconds * 60):
		await physics_frame
		var now := _loaded()
		now.sort()
		if now == last:
			still += 1
			if still >= 60:
				return
		else:
			still = 0
			last = now

func _xz(v: Vector3) -> Vector2:
	return Vector2(v.x, v.z)

func _initialize() -> void:
	w = (load(WORLD) as PackedScene).instantiate()
	var control := "--control" in OS.get_cmdline_user_args()
	var markers := []
	_collect(w, "ZoneMarker.java", markers)
	for m in markers:
		var z = m.get("zone")
		if z == null or not str(z.get("geometry_path")).get_file().begins_with("Roads_IslandRoads_island_"):
			continue
		if control:
			z.set("load_radius", 150.0)
			z.set("unload_radius", 200.0)
		var zid := str(z.get("zone_id"))
		var piece := str(z.get("geometry_path")).get_file().get_basename()
		zones[zid] = {"marker": m, "zone": z, "load": float(z.get("load_radius")),
				"unload": float(z.get("unload_radius")), "centre": (m as Node3D).position, "piece": piece}
		var doc = JSON.parse_string(FileAccess.get_file_as_string(PIECES % piece))
		kits[zid] = doc
		for l in doc["lanes"]:
			zone_of_lane[l["id"]] = zid
	if control:
		print("CONTROL: every road zone's load radius 150 m")
	check("World.tscn has the road grid", zones.size() >= 20, "%d road zones" % zones.size())
	root.add_child(w)
	current_scene = w
	var player: Node3D = w.get_node("Characters/Player")
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	player.set_physics_process(false)       # a teleported player falling into the sea is not the test

	# The tour: every road cell's centre, snaking row by row, so consecutive stops are neighbours.
	var cells := {}
	for zid in zones:
		var parts: PackedStringArray = str(zid).split("_")
		cells[Vector2i(int(parts[1]), int(parts[2]))] = zid
	var keys := cells.keys()
	keys.sort_custom(func(a, b): return a.y < b.y or (a.y == b.y and (a.x < b.x if a.y % 2 == 0 else a.x > b.x)))
	var tour := []
	for k in keys:
		tour.append(zones[cells[k]]["centre"])

	var worst_start := 0.0
	var bad_load := []
	var bad_unload := []
	var bad_place := []
	var bad_dangle := []
	var uncovered := []
	var stops := 0
	for at in tour:
		player.global_position = at + Vector3(0, 2, 0)
		await _settle(30.0)
		stops += 1
		var loaded := _loaded()
		for zid in zones:
			var d: float = _xz(at).distance_to(_xz(zones[zid]["centre"]))
			var is_in: bool = zid in loaded
			if d < zones[zid]["load"] - 1.0 and not is_in:
				bad_load.append("%s@%.0fm" % [zid, d])
			if d > zones[zid]["unload"] + 1.0 and is_in:
				bad_unload.append("%s@%.0fm" % [zid, d])
		for zid in loaded:
			var g := _piece_node(zid)
			if not g.global_transform.origin.is_equal_approx(NET_ORIGIN):
				bad_place.append("%s %s" % [zid, g.global_transform.origin])
		var lanes := _lanes()
		for zid in loaded:
			for l in kits[zid]["lanes"]:
				var node: Node = lanes.get(l["id"])
				var path: Path3D = node.get_node_or_null("Path3D") if node != null else null
				if path == null or path.curve == null or path.curve.point_count == 0:
					worst_start = INF
					continue
				var p0: Array = l["points"][0]
				worst_start = maxf(worst_start, path.to_global(path.curve.get_point_position(0)).distance_to(NET_ORIGIN + Vector3(p0[0], p0[1], p0[2])))
		for nm in lanes:
			for nx in str(lanes[nm].get("next_routes")).split(",", false):
				nx = nx.strip_edges()
				if not lanes.has(nx) and str(zone_of_lane.get(nx, "")) in loaded:
					bad_dangle.append("%s->%s" % [nm, nx])
		# Coverage: the road around the player is streamed. Every lane sample within 150 m of the
		# player belongs to a loaded zone.
		for zid in zones:
			if zid in loaded:
				continue
			for l in kits[zid]["lanes"]:
				for p in l["points"]:
					if Vector2(p[0], p[2]).distance_to(_xz(at)) < 150.0:
						uncovered.append("%s near stop %d" % [zid, stops])
						break
				if not uncovered.is_empty() and uncovered[-1].begins_with(zid):
					break
	check("every zone within its load radius is loaded (%d stops)" % stops, bad_load.is_empty(), str(bad_load.slice(0, 4)))
	check("no zone past its unload radius stays loaded", bad_unload.is_empty(), str(bad_unload.slice(0, 4)))
	check("every loaded piece sits at the network (Y +0.6)", bad_place.is_empty(), str(bad_place.slice(0, 3)))
	check("every streamed lane starts where its lanekit says", worst_start < 0.05, "worst %.4f m" % worst_start)
	check("a successor dangles only into an UNLOADED zone", bad_dangle.is_empty(), "%d %s" % [bad_dangle.size(), bad_dangle.slice(0, 3)])
	check("every road within 150 m of the player is streamed", uncovered.is_empty(), "%d %s" % [uncovered.size(), uncovered.slice(0, 3)])

	# The drive: 30 m/s along the tour, one physics frame per 0.5 m.
	player.global_position = tour[0] + Vector3(0, 2, 0)
	await _settle(30.0)
	var frame_us := []
	var enter_us := []
	var prev_loaded := _loaded()
	var t_prev := Time.get_ticks_usec()
	for i in range(1, tour.size()):
		var a: Vector3 = tour[i - 1]
		var b: Vector3 = tour[i]
		var steps := int(ceil(a.distance_to(b) / 0.5))
		for s in steps:
			player.global_position = a.lerp(b, float(s + 1) / steps) + Vector3(0, 2, 0)
			await physics_frame
			var t := Time.get_ticks_usec()
			var dt := t - t_prev
			t_prev = t
			frame_us.append(dt)
			var now := _loaded()
			if now.size() > prev_loaded.size():
				enter_us.append(dt)
			prev_loaded = now
	frame_us.sort()
	var p50: float = frame_us[frame_us.size() / 2] / 1000.0
	var p99: float = frame_us[int(frame_us.size() * 0.99)] / 1000.0
	var worst: float = frame_us[-1] / 1000.0
	enter_us.sort()
	var worst_enter: float = (enter_us[-1] / 1000.0) if not enter_us.is_empty() else 0.0
	print("  drive: %d frames at 30 m/s, frame p50 %.2f ms, p99 %.2f ms, worst %.2f ms; %d piece(s) finished entering, worst such frame %.2f ms" \
			% [frame_us.size(), p50, p99, worst, enter_us.size(), worst_enter])
	check("the drive streamed pieces in", enter_us.size() > 0, "%d" % enter_us.size())
	_finish()

func _finish() -> void:
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
