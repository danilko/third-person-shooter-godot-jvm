extends SceneTree
## PLAN.md 3.25 R2 gate: the RAIL, as built (the IslandRail Road Kit network, `tools/island_rail_record.py`,
## streamed by World.tscn's `RailZones`).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_rail_track.gd [-- --control]
##
## The probe instances every rail piece and every road piece itself, where `Zone.placeGeometry` puts them
## (`geometry_world_transform`), and frees the scene's ZoneMarkers so nothing streams a second copy
## (probe_road_clear's rule). Then:
##   1. every rail lane of every rail lanekit is a `PathLaneRoute` in the built pieces, and each one is in the
##      `rail_track` group;
##   2. no rail lane is in the traffic registry (`ZoneManager.registered_lane_counts_now`): a car never spawns on a track
##      and `LaneGraph` never hands one onto it at a 踏切;
##   3. at every LEVEL CROSSING (a rail lane sample inside a road lane's driving band, at the road's height) the
##      collision a car meets is the ROAD's: a ray down finds a surface within 0.08 m of the road lane -- no
##      ballast bed, fence or car wall stands proud in the carriageway;
##   4. at every station of the reserve (`IslandRailReserve.json`) the PLATFORMS stand: a ray down on each side of
##      the track, half a platform out from its edge, finds a surface 1.1-1.4 m over the rail bed (R3).
## `-- --control` puts a 0.5 m box across the first crossing: check 3 must FAIL there.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const PIECES := "res://assets/world_source/pieces/%s.lanekit.json"
const RESERVE := "res://assets/world_source/buildings/IslandRailReserve.json"
const WORLD_MASK := 1

var fails := 0
var w: Node

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", label, detail])

func _collect(n: Node, script_end: String, out: Array) -> void:
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with(script_end):
		out.append(n)
	for c in n.get_children():
		_collect(c, script_end, out)

func _godot(p) -> Vector3:
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

func _ray_down(at: Vector3) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(at + Vector3(0, 6, 0), at - Vector3(0, 6, 0), WORLD_MASK)
	return w.get_world_3d().direct_space_state.intersect_ray(q)

func _initialize() -> void:
	w = (load(WORLD) as PackedScene).instantiate()
	var control := "--control" in OS.get_cmdline_user_args()
	var markers := []
	_collect(w, "ZoneMarker.java", markers)
	var rail_pieces := []      # [scene path, Transform3D]
	var road_pieces := []
	var other_pieces := []
	for m in markers:
		var z = m.get("zone")
		if z == null:
			continue
		var gp := str(z.get("geometry_path"))
		var file := gp.get_file()
		if file.begins_with("Roads_IslandRail_"):
			rail_pieces.append([gp, z.get("geometry_world_transform")])
		elif file.begins_with("Roads_IslandRoads_island_"):
			road_pieces.append([gp, z.get("geometry_world_transform")])
		elif gp != "" and gp != "<null>" and ResourceLoader.exists(gp):
			# building cells, sites, landmarks: the train's gauge must be clear of them too (check 5)
			other_pieces.append([gp, z.get("geometry_world_transform") if z.get("geometry_world_placed") else (m as Node3D).global_transform])
	for m in markers:
		m.get_parent().remove_child(m)
		m.free()
	root.add_child(w)
	await process_frame
	var holder := Node3D.new()
	w.add_child(holder)
	for pr in rail_pieces + road_pieces + other_pieces:
		var n := (load(pr[0]) as PackedScene).instantiate() as Node3D
		holder.add_child(n)
		n.global_transform = pr[1]
	for i in 3:
		await physics_frame
	print("probe_rail_track: %d rail piece(s), %d road piece(s)" % [rail_pieces.size(), road_pieces.size()])
	check("the world streams the rail (RailZones pieces exist)", rail_pieces.size() > 0)

	# 1-2. rail lanes
	var routes := []
	_collect(holder, "PathLaneRoute.java", routes)
	var by_name := {}
	for r in routes:
		by_name[str(r.name)] = r
	var rail_ids := []
	var road_lanes := []
	for pr in rail_pieces:
		var doc = JSON.parse_string(FileAccess.get_file_as_string(PIECES % str(pr[0]).get_file().get_basename()))
		for l in doc["lanes"]:
			if str(l.get("road_class", "")) == "rail":
				rail_ids.append(l)
	for pr in road_pieces:
		var doc = JSON.parse_string(FileAccess.get_file_as_string(PIECES % str(pr[0]).get_file().get_basename()))
		for l in doc["lanes"]:
			if str(l.get("kind", "")) == "through" and str(l.get("road_class", "")) != "rail":
				road_lanes.append(l)
	var missing := []
	var ungrouped := []
	for l in rail_ids:
		var n = by_name.get(str(l["id"]))
		if n == null:
			missing.append(l["id"])
		elif not (n as Node).is_in_group("rail_track"):
			ungrouped.append(l["id"])
	check("every rail lane is built as a PathLaneRoute", rail_ids.size() > 0 and missing.is_empty(),
			"%d rail lane(s), %d missing %s" % [rail_ids.size(), missing.size(), str(missing.slice(0, 4))])
	check("every rail lane is in the rail_track group", ungrouped.is_empty(), "%d not" % ungrouped.size())
	print("probe_rail_track: lanes checked at %d ms" % Time.get_ticks_msec())
	var zm := root.get_node_or_null("ZoneManager")
	if zm != null:
		var counts := str(zm.call("registered_lane_counts_now")).split(",")
		check("no rail lane is in the traffic registry", int(counts[1]) == 0,
				"%s registered lane(s), %s rail" % [counts[0], counts[1]])
	else:
		print("  INFO  no ZoneManager AutoLoad in this run: the registry check is skipped")

	print("probe_rail_track: registry checked at %d ms" % Time.get_ticks_msec())
	# 3. level crossings: a rail sample inside a road lane's band at the road's height
	var grid := {}
	for l in road_lanes:
		var pts: Array = l["points"]
		for i in range(pts.size() - 1):
			var a := _godot(pts[i])
			var b := _godot(pts[i + 1])
			for k in [Vector2i(int(floor(a.x / 16.0)), int(floor(a.z / 16.0))), Vector2i(int(floor(b.x / 16.0)), int(floor(b.z / 16.0)))]:
				if not grid.has(k):
					grid[k] = []
				grid[k].append([a, b, float(l.get("lane_width", 4.5)) * 0.5])
	var crossings := []
	for l in rail_ids:
		var pts: Array = l["points"]
		for i in range(pts.size() - 1):
			var a := _godot(pts[i])
			var b := _godot(pts[i + 1])
			var steps := int(ceil(a.distance_to(b) / 2.0))
			for s in steps + 1:
				var p := a.lerp(b, float(s) / max(1, steps))
				var key := Vector2i(int(floor(p.x / 16.0)), int(floor(p.z / 16.0)))
				for seg in grid.get(key, []):
					var sa: Vector3 = seg[0]
					var sb: Vector3 = seg[1]
					var d2 := Vector2(sb.x - sa.x, sb.z - sa.z)
					var t := clampf(Vector2(p.x - sa.x, p.z - sa.z).dot(d2) / maxf(1e-9, d2.length_squared()), 0.0, 1.0)
					var q: Vector3 = sa.lerp(sb, t)
					if Vector2(p.x - q.x, p.z - q.z).length() < float(seg[2]) - 0.3 and absf(p.y - q.y) < 1.0:
						var dup := false
						for c in crossings:
							if (c as Vector3).distance_to(q) < 6.0:
								dup = true
								break
						if not dup:
							crossings.append(q)
	if control and not crossings.is_empty():
		var box := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var sh := BoxShape3D.new()
		sh.size = Vector3(8, 0.5, 8)
		cs.shape = sh
		box.add_child(cs)
		holder.add_child(box)
		box.global_position = crossings[0] + Vector3(0, 0.25, 0)
		for i in 2:
			await physics_frame
	print("probe_rail_track: %d crossing(s) found at %d ms" % [crossings.size(), Time.get_ticks_msec()])
	# the lanekit heights are in the NETWORK's frame: the road network node's own Y lifts them into the world
	var rn_y := 0.0
	var roads_node := w.get_node_or_null("IslandRoads") as Node3D
	if roads_node != null:
		rn_y = roads_node.position.y
	var proud := []
	for q0 in crossings:
		var q: Vector3 = q0 + Vector3(0, rn_y, 0)
		var hit := _ray_down(q)
		if hit.is_empty() or (hit["position"] as Vector3).y - q.y > 0.08:
			proud.append("(%.0f, %.0f) %s" % [q.x, q.z, "no surface" if hit.is_empty() else "%.2f m up" % ((hit["position"] as Vector3).y - q.y)])
	check("every level crossing is the road's surface (nothing proud)", not crossings.is_empty() and proud.is_empty(),
			"%d crossing(s) %s" % [crossings.size(), str(proud.slice(0, 4))])

	# 4. platforms
	var res = JSON.parse_string(FileAccess.get_file_as_string(RESERVE))
	var ny := 5.6
	var rn := w.get_node_or_null("IslandRail") as Node3D
	if rn != null:
		ny = rn.position.y
	var bad := []
	var nst := 0
	for bx in res["boxes"]:
		if not str(bx["id"]).begins_with("station:"):
			continue
		nst += 1
		var ux := float(bx["ux"])
		var uy := float(bx["uy"])
		var nx := -uy
		var nyy := ux
		for sgn in [-1.0, 1.0]:
			var off := 3.5 + 1.2
			var rec := Vector2(float(bx["x"]) + nx * sgn * off, float(bx["y"]) + nyy * sgn * off)
			var at := Vector3(rec.x, ny + float(bx["z"]), -rec.y)
			var hit := _ray_down(at)
			var bed := ny + float(bx["z"]) - 0.16
			var dz := 999.0 if hit.is_empty() else (hit["position"] as Vector3).y - bed
			if dz < 1.1 or dz > 1.4:
				bad.append("%s %+d: %s" % [str(bx["id"]).substr(8), int(sgn), "none" if hit.is_empty() else "%.2f" % dz])
	check("every station has a platform each side, 1.1-1.4 m over the bed", nst > 0 and bad.is_empty(),
			"%d station(s) %s" % [nst, str(bad.slice(0, 6))])
	# 5. THE TRAIN'S GAUGE (user, 2026-09-26: "no tree/lamp/other in the middle of the rail"): along every track, every
	# 2 m, a box the size of a train (2.7 m wide, 0.5-4.2 m over the bed, the platforms' edges 1.5 m out stay clear)
	# must touch nothing solid -- a pole, a tree trunk, a building, a road's barrier or pier.
	var rail_y := ny
	var gauge := BoxShape3D.new()
	gauge.size = Vector3(2.7, 3.7, 1.6)
	var gq := PhysicsShapeQueryParameters3D.new()
	gq.shape = gauge
	gq.collision_mask = WORLD_MASK | 32
	var in_gauge := {}
	var gauge_samples := 0
	for l in rail_ids:
		var pts: Array = l["points"]
		for i in range(pts.size() - 1):
			var a := _godot(pts[i]) + Vector3(0, rail_y, 0)
			var b := _godot(pts[i + 1]) + Vector3(0, rail_y, 0)
			var dir := (b - a)
			dir.y = 0.0
			if dir.length() < 0.01:
				continue
			var yaw := atan2(dir.x, dir.z)
			var steps := int(ceil(a.distance_to(b) / 2.0))
			for k in steps:
				var p := a.lerp(b, float(k) / max(1, steps))
				gq.transform = Transform3D(Basis(Vector3.UP, yaw), p + Vector3(0, 0.5 + 1.85, 0))
				gauge_samples += 1
				for hit in w.get_world_3d().direct_space_state.intersect_shape(gq, 4):
					var col = hit["collider"]
					var owner_name := str(col.name)
					var n := col as Node
					while n != null and n.get_parent() != holder and n.get_parent() != w:
						n = n.get_parent()
					var key := "%s/%s" % [str(n.name) if n != null else "?", owner_name]
					if not in_gauge.has(key):
						in_gauge[key] = "%s @ (%.0f, %.1f, %.0f)" % [l["id"], p.x, p.y, p.z]
	var gl := []
	for k in in_gauge:
		gl.append("%s [%s]" % [k, in_gauge[k]])
		print("    in gauge: %s  first at %s" % [k, in_gauge[k]])
	check("nothing solid stands in a train's gauge along any track", gauge_samples > 0 and in_gauge.is_empty(),
			"%d sample(s), %d collider(s) %s" % [gauge_samples, in_gauge.size(), str(gl.slice(0, 3))])

	# 6. every track END is at a station: a lane with no successor must stop inside a station's platform box (its
	# buffer stop), never out on open track
	var stations := []
	for bx in res["boxes"]:
		if str(bx["id"]).begins_with("station:"):
			stations.append(bx)
	var loose := []
	for l in rail_ids:
		if not (l.get("next", []) as Array).is_empty():
			continue
		var last: Array = (l["points"] as Array)[-1]
		var rx := float(last[0])
		var ry := -float(last[2])
		var ok := false
		for bx in stations:
			var dx := rx - float(bx["x"])
			var dy := ry - float(bx["y"])
			var along := dx * float(bx["ux"]) + dy * float(bx["uy"])
			var across := -dx * float(bx["uy"]) + dy * float(bx["ux"])
			# + an overrun of up to 25 m past the platform box: a terminus's buffer stop stands ~20 m past its platform
			if absf(along) <= float(bx["h_along"]) + 25.0 and absf(across) <= float(bx["h_across"]) + 6.0:
				ok = true
				break
		if not ok:
			loose.append("%s ends at (%.0f, %.0f)" % [l["id"], rx, ry])
	check("every track that ends, ends at a station", loose.is_empty(), "%d loose %s" % [loose.size(), str(loose.slice(0, 4))])
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
