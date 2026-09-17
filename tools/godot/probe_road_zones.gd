extends SceneTree
## PLAN.md 3.1 B6 runtime gate: ONE road network cut into a piece per zone streams like one road.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_road_zones.gd [-- --control]
##
## world/hosts/RoadKitZones.tscn: the kit's sample network, cut by `point_zones.py` into
## Roads_RoadKitZones_west (26 lanes) and _east (17), each streamed by its own ZoneMarker, with the
## network 40 m off the origin. Asserts, in order:
##   1. both pieces stream in and are placed at the NETWORK's transform, not their markers';
##   2. a streamed lane sits where its lanekit says (network frame + network transform);
##   3. with both loaded every successor name resolves — including the cross-zone ones;
##   4. ambient traffic spawned on the west zone's lanes (route "west" = lane zone_id), drove, and a
##      car drove off a west lane onto an east one -- the cut is invisible to traffic;
##   5. walking east unloads the west piece, and exactly the east->west successors go unresolved;
##   6. walking back reloads it and every successor resolves again.
## Every lane is looked up by NAME among the PathLaneRoutes in the tree — the same key the
## ZoneManager registry resolves `next_routes` by.

const HOST := "res://src/main/resources/com/openworld/world/hosts/RoadKitZones.tscn"
const KIT := "res://assets/world_source/pieces/Roads_RoadKitZones_%s.lanekit.json"
const NET_ORIGIN := Vector3(0, 0, 40)

var fails := 0
var w: Node

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _lanes() -> Dictionary:
	var out := {}
	_collect(w, out)
	return out

func _collect(n: Node, out: Dictionary) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("PathLaneRoute.java") and n.is_inside_tree():
		out[str(n.name)] = n
	for c in n.get_children():
		_collect(c, out)

func _unresolved(lanes: Dictionary) -> Array:
	var out := []
	for nm in lanes:
		for nx in str(lanes[nm].get("next_routes")).split(",", false):
			if not lanes.has(nx.strip_edges()):
				out.append("%s->%s" % [nm, nx])
	return out

func _geometry(zone: String) -> Node3D:
	for c in w.get_node("Zones/" + zone.capitalize()).get_children():
		if c is Node3D and str(c.scene_file_path).get_file().begins_with("Roads_RoadKitZones_" + zone):
			return c
	return null

func _lane_at(lanes: Dictionary, pos: Vector3) -> String:
	var best := ""
	var bd := 1.5
	for nm in lanes:
		var path: Path3D = lanes[nm].get_node_or_null("Path3D")
		if path == null or path.curve == null:
			continue
		var c: Curve3D = path.curve
		# A lane whose exported Curve3D carries two COINCIDENT control points has a zero-length
		# first baked segment, and `get_closest_offset` then returns NaN — `sample_baked(NaN)`
		# errors and the attribution is silently wrong. The rule that produced them is fixed
		# (`point_solve.TURN_LEG_MIN`), but every piece baked before that still has them: on the
		# island 5 of 218 lanes, all turn connectors. Skip, never guess.
		var off := c.get_closest_offset(path.to_local(pos))
		if not is_finite(off):
			continue
		var at := path.to_global(c.sample_baked(off))
		var d := Vector2(at.x - pos.x, at.z - pos.z).length()
		if d < bd:
			bd = d
			best = nm
	return best

func _frames(n: int) -> void:
	for i in n:
		await physics_frame

func _wait_for(cond: Callable, seconds: float) -> bool:
	for i in int(seconds * 60):
		if cond.call():
			return true
		await physics_frame
	return cond.call()

func _kit(zone: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(KIT % zone))

func _initialize() -> void:
	w = (load(HOST) as PackedScene).instantiate()
	if "--control" in OS.get_cmdline_user_args():
		# The control: pieces placed in their MARKER's frame, as every district piece is. Steps 1-2
		# must FAIL, or they are not measuring the placement.
		for m in ["West", "East"]:
			w.get_node("Zones/" + m).get("zone").set("geometry_world_placed", false)
		print("CONTROL: geometry_world_placed = false on both zones")
	root.add_child(w)
	current_scene = w
	var player: Node3D = w.get_node("Characters/Player")
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)

	var west := _kit("west")
	var east := _kit("east")
	var zone_of := {}
	for l in west["lanes"]:
		zone_of[l["id"]] = "west"
	for l in east["lanes"]:
		zone_of[l["id"]] = "east"
	var east_to_west := 0
	for l in east["lanes"]:
		for nx in l.get("next", []):
			if zone_of.get(nx) == "west":
				east_to_west += 1

	# 1. Both stream in, placed at the network.
	var loaded := await _wait_for(func(): return _geometry("west") != null and _geometry("east") != null and _lanes().size() == 43, 30.0)
	check("both pieces stream in (43 lanes)", loaded, "%d lanes" % _lanes().size())
	if not loaded:
		_finish()
		return
	await _frames(30)
	for z in ["west", "east"]:
		var g := _geometry(z)
		check("%s piece placed at the network, not its marker" % z, g.global_transform.origin.is_equal_approx(NET_ORIGIN), str(g.global_transform.origin))

	# 2. A lane is where its lanekit says.
	var lanes := _lanes()
	var worst := 0.0
	for doc in [west, east]:
		for l in doc["lanes"]:
			var node: Node = lanes.get(l["id"])
			var path: Path3D = node.get_node_or_null("Path3D") if node != null else null
			if path == null or path.curve == null or path.curve.point_count == 0:
				worst = INF
				continue
			var p0: Array = l["points"][0]
			var want := NET_ORIGIN + Vector3(p0[0], p0[1], p0[2])
			worst = maxf(worst, path.to_global(path.curve.get_point_position(0)).distance_to(want))
	check("every lane starts where its lanekit says", worst < 0.05, "worst %.4f m" % worst)

	# 3. Cross-zone successors resolve with both loaded.
	var un := _unresolved(lanes)
	check("every successor resolves with both zones in", un.is_empty(), "%d unresolved %s" % [un.size(), un.slice(0, 3)])

	# 4. Traffic on the west zone's lanes, driving.
	var start := {}
	var drove := await _wait_for(func():
		for v in get_nodes_in_group("streamed_vehicle"):
			var id := v.get_instance_id()
			if not start.has(id):
				start[id] = (v as Node3D).global_position
			elif (v as Node3D).global_position.distance_to(start[id]) > 30.0:
				return true
		return false, 40.0)
	check("west traffic spawned and drove 30 m", drove, "%d car(s) seen" % start.size())

	# 4b. The cut is invisible to a car: one drives off a west lane onto an east one. Each car is
	# attributed to the nearest lane curve within 1.5 m, as probe_road_traffic.gd does.
	# Only a SUCCESSOR EDGE counts: two adjacent lanes 1.5 m apart can swap attribution without the
	# car going anywhere, and that is not a hand-over.
	var nexts := {}
	for doc in [west, east]:
		for l in doc["lanes"]:
			nexts[l["id"]] = l.get("next", [])
	var last_lane := {}
	var crossings := []
	var crossed := await _wait_for(func():
		for v in get_nodes_in_group("streamed_vehicle"):
			var ln := _lane_at(lanes, (v as Node3D).global_position)
			if ln == "":
				continue
			var id := v.get_instance_id()
			var prev: String = last_lane.get(id, ln)
			if prev != ln and zone_of.get(prev) != zone_of.get(ln) and ln in nexts.get(prev, []):
				crossings.append("%s(%s) -> %s(%s)" % [prev, zone_of[prev], ln, zone_of[ln]])
			last_lane[id] = ln
		return not crossings.is_empty(), 90.0)
	check("a car hands over across the cut along a successor edge", crossed, str(crossings))

	# 5. Walk east: the west piece unloads, and exactly the east->west successors dangle.
	player.global_position = Vector3(2300, 1, -60)
	var gone := await _wait_for(func(): return _geometry("west") == null and _lanes().size() == 17, 30.0)
	lanes = _lanes()
	check("west unloads when the player walks east", gone, "%d lanes left" % lanes.size())
	check("east stays loaded", _geometry("east") != null)
	un = _unresolved(lanes)
	check("exactly the east->west successors go unresolved", un.size() == east_to_west, "%d unresolved, %d cross edges" % [un.size(), east_to_west])

	# 6. Walk back: reloaded, whole again.
	player.global_position = Vector3(825, 1, 60)
	var back := await _wait_for(func(): return _geometry("west") != null and _lanes().size() == 43, 30.0)
	check("west reloads when the player returns", back, "%d lanes" % _lanes().size())
	await _frames(10)
	un = _unresolved(_lanes())
	check("every successor resolves again", un.is_empty(), "%d unresolved" % un.size())
	_finish()

func _finish() -> void:
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
