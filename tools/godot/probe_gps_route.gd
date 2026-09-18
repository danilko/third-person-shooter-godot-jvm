extends SceneTree
## PLAN.md 4.7 -- road lanes on the map, and the GPS arrow following a ROUTE along them.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_gps_route.gd
##   ... -- --world=island        World.tscn's IslandRoads instead of DebugWorld's DebugRoads
##   ... -- --control             GpsArrow.follow_roads off (the I5 straight-line arrow)
##
## Runs the real world with its real HUD. The waypoint is set the shipped way -- the map opened with
## the `map` action and left-clicked -- so every assertion is about what the player's own click
## produced. Asserted:
##   - the road map comes from the committed BAKE (4.7b; tools/godot/bake_road_map.gd), not a live
##     rebuild, and its picture is road under the route's ends and empty off the road;
##   - the minimap and the opened world map draw the road picture; the map opens FITTED to the whole
##     world; the wheel zooms about the cursor (the point under it stays put); a left drag pans and
##     drops no waypoint;
##   - the route is a chain of LEGAL movements (each lane an authored `next` or a lane change of the
##     one before, read independently here from the same sidecars), it ends on the lane nearest the
##     waypoint, and it is longer than the straight line;
##   - on DebugWorld it crosses the junction between the two zones (link -> connector -> spur);
##   - the arrow's target lies ON the route, about LOOKAHEAD metres ahead of the body;
##   - with the body well off the road, the arrow points at the road rather than at the waypoint
##     (the control -- follow_roads off -- fails exactly this and the "about 30 m ahead" check);
##   - within 40 m of the waypoint the arrow points straight at it; a right-click clears it.

const WORLDS := {
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
	"island": "res://src/main/resources/com/openworld/world/World.tscn",
}
const LOOKAHEAD := 30.0      # RoadMap.LOOKAHEAD_METERS
const SLACK := 10.0          # RoadGraph.CANDIDATE_SLACK
const OFF_ROAD := 65.0

var fails := 0
var lanes := {}          # id -> {pts: PackedVector3Array (world), next: Array, side: Array}
var world: Node
var player: Node3D
var gps: Node
var minimap: Node
var worldmap: Control

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	var which := "debugworld"
	var control := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--world="):
			which = a.substr(8)
		elif a == "--control":
			control = true
	print("probe_gps_route: world=%s control=%s" % [which, control])
	world = (load(WORLDS[which]) as PackedScene).instantiate()
	root.add_child(world)
	for i in 20:
		await physics_frame
	player = world.get_node("Characters/Player")
	gps = world.find_child("GpsArrow", true, false)
	minimap = world.find_child("Minimap", true, false)
	worldmap = world.find_child("WorldMap", true, false)
	if gps == null or minimap == null or worldmap == null:
		print("RESULT FAIL (HUD nodes missing)")
		quit(1)
		return
	gps.set("follow_roads", not control)
	_load_lanes(which)
	print("  %d lanes read from the sidecars" % lanes.size())
	# Hold the body still: it is teleported between cases and must stay where it is put.
	player.set_physics_process(false)
	var mc = player.get_node_or_null("MovementController")
	if mc != null:
		mc.set_physics_process(false)

	# ── pick a start and a goal ─────────────────────────────────────────────────────────────
	var start: Vector3
	var goal: Vector3
	if which == "debugworld":
		start = _at("link_F0", 0.5)
		goal = _at("spur_R0", 0.95)
	else:
		var longest := ""
		for id in lanes:
			if longest == "" or _len(id) > _len(longest):
				longest = id
		start = _at(longest, 0.5)
		var far := ""
		for id in lanes:
			if _len(id) > 60 and (far == "" or _at(id, 0.5).distance_to(start) > _at(far, 0.5).distance_to(start)):
				far = id
		goal = _at(far, 0.5)
		print("  start on %s, goal on %s (%.0f m apart)" % [longest, far, start.distance_to(goal)])
	_place(start)

	# ── 1. the baked road map, and the minimap draws it ──────────────────────────────────────
	for i in 3:
		await process_frame
	var src: String = minimap.call("road_map_source_now")
	_check("the road map is the committed bake, not a live rebuild", src == "bake", "source=%s" % src)
	var cov_on := minf(minimap.call("road_coverage_now", start), minimap.call("road_coverage_now", goal))
	var cov_off: float = minimap.call("road_coverage_now", _off_road_point(start, goal))
	_check("the picture is road on the lanes and empty off them", cov_on > 0.99 and cov_off == 0.0,
		"on %.2f, off %.2f" % [cov_on, cov_off])
	_check("minimap draws the road picture", minimap.call("road_map_drawn_now"), "")

	# ── 2. open the map: fitted to the world; zoom about the cursor; drag pans; click ────────
	_action("map")
	for i in 3:
		await process_frame
	_check("the opened world map draws the road picture", worldmap.visible and worldmap.call("road_map_drawn_now"),
		"visible=%s" % worldmap.visible)
	var bounds := world.find_child("WorldBounds", true, false) as Node3D
	var fitted := true
	if bounds != null:
		var he: float = bounds.get("half_extent")
		var c := bounds.global_position
		for corner in [Vector3(c.x - he, 0, c.z - he), Vector3(c.x + he, 0, c.z + he)]:
			var sp: Vector2 = worldmap.call("world_to_screen_now", corner)
			fitted = fitted and Rect2(Vector2.ZERO, worldmap.size).grow(1.0).has_point(sp)
	_check("the map opens fitted to the whole world (both wall corners on screen)", fitted,
		"range %.0f m" % float(worldmap.get("range_meters")))
	var cursor := worldmap.size * 0.3
	var under: Vector3 = worldmap.call("screen_to_world_now", cursor)
	var r0: float = worldmap.get("range_meters")
	_wheel(MOUSE_BUTTON_WHEEL_UP, cursor)
	_wheel(MOUSE_BUTTON_WHEEL_UP, cursor)
	var under2: Vector3 = worldmap.call("screen_to_world_now", cursor)
	_check("the wheel zooms in about the cursor", float(worldmap.get("range_meters")) < r0
		and Vector2(under.x - under2.x, under.z - under2.z).length() < 0.5,
		"range %.0f -> %.0f m, point under the cursor moved %.2f m" % [r0, float(worldmap.get("range_meters")),
		Vector2(under.x - under2.x, under.z - under2.z).length()])
	var before_drag: Vector3 = worldmap.call("screen_to_world_now", worldmap.size * 0.5)
	_mouse(MOUSE_BUTTON_LEFT, true, worldmap.size * 0.5)
	for k in 5:
		var mm := InputEventMouseMotion.new()
		mm.position = worldmap.size * 0.5 + Vector2(20.0 * (k + 1), 0)
		worldmap.call("_gui_input", mm)
	_mouse(MOUSE_BUTTON_LEFT, false, worldmap.size * 0.5 + Vector2(100, 0))
	var after_drag: Vector3 = worldmap.call("screen_to_world_now", worldmap.size * 0.5)
	_check("a left drag pans the map and drops no waypoint",
		after_drag.x < before_drag.x - 1.0 and gps.call("gps_target_now").distance_to(player.global_position) < 0.01,
		"centre moved %.0f m west" % (before_drag.x - after_drag.x))
	var px: Vector2 = worldmap.call("world_to_screen_now", goal)
	if not Rect2(Vector2.ZERO, worldmap.size).has_point(px):      # zoomed or panned it off -- re-fit
		_action("map")
		await process_frame
		_action("map")
		await process_frame
		px = worldmap.call("world_to_screen_now", goal)
	_mouse(MOUSE_BUTTON_LEFT, true, px)
	_mouse(MOUSE_BUTTON_LEFT, false, px)
	var wp: Vector3 = worldmap.call("screen_to_world_now", px)       # what the map itself computes from that pixel
	_action("map")                   # close it again
	await process_frame

	# ── 3. the route ─────────────────────────────────────────────────────────────────────────
	var target: Vector3 = gps.call("gps_target_now")
	var ids: PackedStringArray = str(gps.call("route_lanes_now")).split(",", false)
	var length: float = gps.call("route_length_now")
	print("  route: %d lanes, %.0f m: %s" % [ids.size(), length, ",".join(ids)])
	_check("a route was found", ids.size() > 0 and length > 0, "")
	var illegal := []
	for i in range(ids.size() - 1):
		var a: Dictionary = lanes.get(ids[i], {})
		if not (ids[i + 1] in a.get("next", []) or ids[i + 1] in a.get("side", [])):
			illegal.append("%s->%s" % [ids[i], ids[i + 1]])
	_check("every step is a legal successor or lane change", illegal.is_empty(), str(illegal))
	if ids.size() > 0:
		var near := _nearest_lanes(wp)
		var last_d := _dist_to_lane(ids[ids.size() - 1], wp)
		_check("the route ends on the lane nearest the waypoint", last_d <= near[1] + SLACK,
			"last %s at %.1f m, nearest %s at %.1f m" % [ids[ids.size() - 1], last_d, near[0], near[1]])
	var straight := Vector2(wp.x - start.x, wp.z - start.z).length()
	_check("the route is longer than the straight line", length > straight,
		"%.0f m vs %.0f m" % [length, straight])
	if which == "debugworld" and ids.size() > 0:
		var crosses := ids[0].begins_with("link_F") and ids[ids.size() - 1].begins_with("spur_R")
		var via := false
		for id in ids:
			via = via or id.contains("__spur_R")
		_check("it crosses the junction into the next zone (link -> connector -> spur)", crosses and via, "")

	# ── 4. the arrow points along the route ──────────────────────────────────────────────────
	var on_route := _dist_to_route(ids, target)
	var ahead := Vector2(target.x - start.x, target.z - start.z).length()
	_check("the arrow's target lies on the route", on_route < 1.0, "%.2f m off it" % on_route)
	_check("... about %.0f m ahead of the body" % LOOKAHEAD, absf(ahead - LOOKAHEAD) < 8.0, "%.1f m" % ahead)

	# ── 5. off the road: the arrow leads to the road, not across country ─────────────────────
	var off := _off_road_point(start, wp)
	_place(off)
	for i in 80:            # past RoadMap.REROUTE_SECONDS, so leaving the route re-routes
		await physics_frame
	_place(off)
	target = gps.call("gps_target_now")
	var to_target := Vector2(target.x - off.x, target.z - off.z)
	var to_wp := Vector2(wp.x - off.x, wp.z - off.z)
	var bend := rad_to_deg(absf(to_target.angle_to(to_wp)))
	var tgt_road: float = _nearest_lanes(target)[1]
	print("  off road at (%.0f, %.0f), %.0f m from the nearest lane" % [off.x, off.z, _nearest_lanes(off)[1]])
	_check("off the road, the arrow points at the road", tgt_road < 1.0 and bend > 20.0,
		"target %.2f m from a lane, %.0f deg off the straight bearing" % [tgt_road, bend])

	# ── 6. close to the waypoint: straight at it ─────────────────────────────────────────────
	var close_p := Vector3(wp.x + 20.0, wp.y, wp.z)
	_place(close_p)
	target = gps.call("gps_target_now")
	_check("within 40 m the arrow points straight at the waypoint",
		Vector2(target.x - wp.x, target.z - wp.z).length() < 0.5, "")

	# ── 7. a right-click clears it ───────────────────────────────────────────────────────────
	_action("map")
	await process_frame
	_mouse(MOUSE_BUTTON_RIGHT, true, px)
	_action("map")
	await process_frame
	target = gps.call("gps_target_now")
	_check("a right-click on the map clears the waypoint", target.distance_to(player.global_position) < 0.01, "")

	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)

# ── helpers ─────────────────────────────────────────────────────────────────────────────────

func _place(p: Vector3) -> void:
	player.global_position = p + Vector3(0, 0.1, 0)

func _action(name: String) -> void:
	var ev := InputEventAction.new()
	ev.action = name
	ev.pressed = true
	Input.parse_input_event(ev)
	Input.flush_buffered_events()

func _wheel(button: int, at: Vector2) -> void:
	_mouse(button, true, at)

func _mouse(button: int, pressed: bool, at: Vector2) -> void:
	var ev := InputEventMouseButton.new()
	ev.button_index = button
	ev.pressed = pressed
	ev.position = at
	worldmap.call("_gui_input", ev)

func _load_lanes(which: String) -> void:
	var stems := ["Roads_DebugRoads_debug_a", "Roads_DebugRoads_debug_b"] if which == "debugworld" \
		else ["Roads_IslandRoads_island"]
	var dy := 0.0 if which == "debugworld" else 0.6      # the island network sits at Y +0.6
	for stem in stems:
		var doc = JSON.parse_string(FileAccess.get_file_as_string(
			"res://assets/world_source/pieces/%s.lanekit.json" % stem))
		for l in doc["lanes"]:
			var pts := PackedVector3Array()
			for p in l["points"]:
				pts.append(Vector3(p[0], p[1] + dy, p[2]))
			var side := []
			for k in ["inner_lane", "outer_lane"]:
				if str(l.get(k, "")) != "":
					side.append(l[k])
			lanes[l["id"]] = {"pts": pts, "next": l.get("next", []), "side": side}
	# lane changes are symmetric
	for id in lanes:
		for s in lanes[id]["side"]:
			if lanes.has(s) and not (id in lanes[s]["side"]):
				lanes[s]["side"].append(id)

func _len(id: String) -> float:
	var pts: PackedVector3Array = lanes[id]["pts"]
	var s := 0.0
	for i in range(pts.size() - 1):
		s += pts[i].distance_to(pts[i + 1])
	return s

func _at(id: String, frac: float) -> Vector3:
	var pts: PackedVector3Array = lanes[id]["pts"]
	var want := _len(id) * frac
	var s := 0.0
	for i in range(pts.size() - 1):
		var d := pts[i].distance_to(pts[i + 1])
		if s + d >= want:
			return pts[i].lerp(pts[i + 1], (want - s) / maxf(d, 1e-6))
		s += d
	return pts[pts.size() - 1]

func _dist_to_lane(id: String, p: Vector3) -> float:
	var pts: PackedVector3Array = lanes[id]["pts"]
	var best := INF
	var q := Vector2(p.x, p.z)
	for i in range(pts.size() - 1):
		var c := Geometry2D.get_closest_point_to_segment(q, Vector2(pts[i].x, pts[i].z), Vector2(pts[i + 1].x, pts[i + 1].z))
		best = minf(best, c.distance_to(q))
	return best

func _nearest_lanes(p: Vector3) -> Array:
	var best := ["", INF]
	for id in lanes:
		var d := _dist_to_lane(id, p)
		if d < best[1]:
			best = [id, d]
	return best

func _dist_to_route(ids: PackedStringArray, p: Vector3) -> float:
	var best := INF
	for id in ids:
		if lanes.has(id):
			best = minf(best, _dist_to_lane(id, p))
	return best

## A point OFF_ROAD metres from every lane, on the far side of the start from the waypoint.
func _off_road_point(start: Vector3, wp: Vector3) -> Vector3:
	var away := Vector2(start.x - wp.x, start.z - wp.z).normalized()
	var perp := Vector2(-away.y, away.x)
	for k in 40:
		for dir in [perp, -perp, away]:
			var c: Vector2 = Vector2(start.x, start.z) + dir * (OFF_ROAD + k * 10.0)
			var p := Vector3(c.x, start.y, c.y)
			if _nearest_lanes(p)[1] >= OFF_ROAD:
				return p
	return start + Vector3(OFF_ROAD, 0, 0)
