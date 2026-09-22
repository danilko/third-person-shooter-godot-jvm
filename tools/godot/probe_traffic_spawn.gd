extends SceneTree
## PLAN.md 0.4 -- ambient cars must spawn where, and facing the way, they can keep driving.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_spawn.gd
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_spawn.gd -- --world=island
##
## --world=debugworld (default) is the two-zone DebugRoads network; --world=island is World.tscn's
## IslandRoads with the 14 traffic zones `tools/island_traffic_zones.py` derives from its lane
## entries (PLAN.md 3.4).
##
## Runs the real DebugWorld (zone `debug_a`, whose route `debug_a` is the zone id its Road Kit lanes
## carry -- PLAN.md 3.1 B6) with the Player held alive and follows every streamed car from spawn to
## reclaim. The road is `Roads_DebugRoads_debug_a/_b`, streamed with the two zones; it was a
## road-generator network published by RoadNetworkBridge until both were removed (2026-09-13). Pair it with ZoneManager's own
## `traffic spawn ... lane=` / `traffic reclaim (...)` lines, which land in the same stdout.
##
## Three defects this guards, all found together (0.4):
##   1. `findRoute` took lanes in NAME order (`_1, _10, _11, _2 ...`), so a car could land on a lane
##      with no successor, drive one segment and be reclaimed as route-finished.
##   2. A top-up used `vehicles.size()` as its spawn index, which repeats: two respawns in a row were
##      set down on the same point, and the fleet went to "0 moving" for good (measured on HEAD: 19 of
##      21 spawns on one lane).
##   3. A car spawned at its default heading (-Z) whatever way its lane ran; one set across a
##      west-running lane crept 6 m north and stopped, 54 m from the Player -- inside the 60 m
##      stall-reclaim gate, so it was never reclaimed.
##
## Asserted: cars spawn; every spawn is at least CLEARANCE_M from any other car and faces its lane
## (within FACING_TOL_DEG of the lane's own tangent at that point); spawns rotate -- at least three
## lanes used and none takes more than half; no car reclaimed during the run drove less
## than MIN_DRIVE_M (longer than any single lane in range, 153.5 m -- rotating over EVERY lane,
## with no reach filter, failed this at 9 of 22); and at the end no car has sat
## without moving for more than MAX_IDLE_S.

const WORLDS := {
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
	"island": "res://src/main/resources/com/openworld/world/World.tscn",
}
const STREAMED := "streamed_vehicle"
const SECONDS := 240
const MIN_DRIVE_M := 160.0
const CLEARANCE_M := 9.9          # ZoneManager.TRAFFIC_SPAWN_CLEARANCE, minus float slack
const FACING_TOL_DEG := 30.0
const MAX_IDLE_S := 15.0          # past ZoneManager.vehicleStallTimeout (12 s)

var cars := {}      # instance id -> state
var done: Array = []
var left_range := 0     # reclaims that were legitimately out of range, exempt from MIN_DRIVE_M
var reclaim_radius := 0.0
var gaps: Array = []
var facing_errors: Array = []
var lane_counts := {}
var world: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", label, detail])

func _yaw(v: Vector3) -> float:
	return rad_to_deg(atan2(-v.x, -v.z))

## Every PathLaneRoute currently in the tree -- i.e. the lanes of the road pieces streamed in.
func _lanes() -> Array:
	return world.find_children("*", "Node", true, false).filter(func(n):
		var s = n.get_script()
		return s != null and str(s.resource_path).ends_with("PathLaneRoute.java"))

## The streamed lane a spawn point sits on, and that lane's travel direction there.
func _lane_at(p: Vector3) -> Dictionary:
	var best := {"name": "", "dist": INF, "dir": Vector3.ZERO}
	for lane in _lanes():
		var path: Path3D = lane.get_node_or_null("Path3D")
		if path == null or path.curve == null:
			continue
		var c: Curve3D = path.curve
		# A lane whose exported Curve3D carries two COINCIDENT control points has a zero-length
		# first baked segment, and `get_closest_offset` then returns NaN — `sample_baked(NaN)`
		# errors and the attribution is silently wrong. The rule that produced them is fixed
		# (`point_solve.TURN_LEG_MIN`), but every piece baked before that still has them: on the
		# island 5 of 218 lanes, all turn connectors. Skip, never guess.
		var off := c.get_closest_offset(path.to_local(p))
		if not is_finite(off):
			continue
		var at := path.to_global(c.sample_baked(off))
		var d := at.distance_to(p)
		if d < best["dist"]:
			var a := maxf(0.0, minf(off, c.get_baked_length() - 1.0))
			var dir := path.to_global(c.sample_baked(a + 1.0)) - path.to_global(c.sample_baked(a))
			best = {"name": str(lane.name), "dist": d, "dir": Vector3(dir.x, 0, dir.z)}
	return best

## The widest unload radius among the zones that actually spawn traffic. It is BOTH the reclaim
## radius and (x 0.9) the spawn gate, so it is what separates "this car was reclaimed for leaving
## range" from "this car could not drive" -- read off the scene rather than written down here, since
## every world sizes its own zones (DebugWorld 500 m, the island 1400).
func _traffic_reclaim_radius() -> float:
	var r := 0.0
	for n in world.find_children("*", "Node3D", true, false):
		var sc = n.get_script()
		if sc == null or not str(sc.resource_path).ends_with("ZoneMarker.java"):
			continue
		var z = n.get("zone")
		if z == null:
			continue
		var vs = z.get("vehicle_spawn_configs")
		if vs != null and vs.size() > 0:
			r = maxf(r, float(z.get("unload_radius")))
	# the traffic ring (ZoneManager.trafficSimRadius): a car past ring + margin is reclaimed as out-of-range
	var zm := root.get_node_or_null("ZoneManager")
	if zm != null and float(zm.get("traffic_sim_radius")) > 0.0:
		r = minf(r, float(zm.get("traffic_sim_radius")) + float(zm.get("traffic_reclaim_margin")))
	return r

func _initialize() -> void:
	var which := "debugworld"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--world="):
			which = a.substr(8)
	if not WORLDS.has(which):
		print("unknown --world=%s (want one of %s)" % [which, WORLDS.keys()])
		quit(2)
		return
	print("--- traffic spawn probe on '%s'" % which)
	var w: Node = (load(WORLDS[which]) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w   # ZoneManager and LaneGraph both resolve the world through current_scene
	world = w
	reclaim_radius = _traffic_reclaim_radius()
	print("  traffic reclaim radius %.0f m" % reclaim_radius)
	var player: Node3D = w.get_node("Characters/Player")
	var health: Node = player.get_node("Health")
	health.set("max_health", 1000000.0)
	var frames := SECONDS * 60
	for f in range(frames):
		await physics_frame
		if f % 30 == 0:
			health.call("heal", 1000000.0)
		for v in get_nodes_in_group(STREAMED):
			var id := v.get_instance_id()
			var p: Vector3 = (v as Node3D).global_position
			if not cars.has(id):
				var gap := INF
				for o in get_nodes_in_group(STREAMED):
					if o != v:
						gap = min(gap, (o as Node3D).global_position.distance_to(p))
				var early: bool = _lanes().is_empty()
				var heading := _yaw(-(v as Node3D).global_basis.z)
				cars[id] = {"node": v, "spawn": f, "last": p, "dist": 0.0, "early": early, "mark": p,
						"moved_frame": f}
				var lane_note := ""
				if not early:
					gaps.append(gap)
					var lane := _lane_at(p)
					var err: float = abs(wrapf(_yaw(lane["dir"]) - heading, -180.0, 180.0))
					facing_errors.append(err)
					lane_counts[lane["name"]] = int(lane_counts.get(lane["name"], 0)) + 1
					lane_note = "  on %s (%.1f m off it), lane heads %.0f deg" % [lane["name"], lane["dist"], _yaw(lane["dir"])]
				print("  car spawned at (%.1f, %.1f) facing %.0f deg, nearest other car %.1f m%s%s"
						% [p.x, p.z, heading, gap, lane_note, "  [before lanes published]" if early else ""])
			var c: Dictionary = cars[id]
			c["dist"] += Vector2(p.x - c["last"].x, p.z - c["last"].z).length()
			c["last"] = p
			if p.distance_to(c["mark"]) > 1.0:
				c["mark"] = p
				c["moved_frame"] = f
		for id in cars.keys():
			var c: Dictionary = cars[id]
			if not is_instance_valid(c["node"]) or not (c["node"] as Node).is_inside_tree():
				# A car reclaimed for LEAVING RANGE has not failed to drive -- it drove out of the
				# zone. On a long arterial the spawn gate sets cars down up to 0.9 x unload from the
				# player, so one heading away legitimately covers only the remaining tenth. The
				# MIN_DRIVE_M check below is about a car that stopped driving while still in range.
				var gone: float = Vector2(c["last"].x - player.global_position.x,
						c["last"].z - player.global_position.z).length()
				var out_of_range: bool = gone > reclaim_radius * 0.95
				# A car whose lane's successors are in a road piece that is not streamed ran off the EDGE of the loaded
				# road (road pieces stream nearer than traffic spawns), far out of sight: not a failure to drive either.
				var zm := root.get_node_or_null("ZoneManager")
				var why: String = str(zm.call("reclaim_reason_of", id)) if zm != null else ""
				if why == "stream-edge" or why == "out-of-range":
					out_of_range = true
				if not c["early"]:
					if out_of_range:
						left_range += 1
					else:
						done.append({"dist": c["dist"], "secs": (f - c["spawn"]) / 60.0})
				print("  car gone after %5.1f s, drove %6.1f m at (%.1f, %.1f, %.1f), last idle %.1f s%s"
						% [(f - c["spawn"]) / 60.0, c["dist"], c["last"].x, c["last"].y, c["last"].z,
						(f - c["moved_frame"]) / 60.0,
						("  [%.0f m out — left range%s]" % [gone, ", stream edge" if why == "stream-edge" else ""])
								if out_of_range else ("  [%s]" % why if why != "" else "")])
				cars.erase(id)

	var idle_max := 0.0
	for id in cars.keys():
		var c: Dictionary = cars[id]
		var v: Node3D = c["node"]
		var idle: float = (frames - c["moved_frame"]) / 60.0
		idle_max = max(idle_max, idle)
		print("  alive car at (%.1f, %.1f) speed %.2f m/s, idle %.1f s, %.1f m from player"
				% [v.global_position.x, v.global_position.z, (v as RigidBody3D).linear_velocity.length(),
				idle, v.global_position.distance_to(player.global_position)])
	var short := 0
	for d in done:
		if d["dist"] < MIN_DRIVE_M:
			short += 1
	var min_gap: float = gaps.min() if not gaps.is_empty() else INF
	var worst_facing: float = facing_errors.max() if not facing_errors.is_empty() else 0.0
	print("--- %d cars spawned after lanes published, %d reclaimed in range, %d left range, %d alive at end"
			% [gaps.size(), done.size(), left_range, cars.size()])
	_check("cars spawned", gaps.size() > 0, "%d" % gaps.size())
	_check("spawn clearance", min_gap >= CLEARANCE_M, "nearest other car at spawn %.1f m" % min_gap)
	_check("spawned facing its lane", worst_facing <= FACING_TOL_DEG,
			"worst %.0f deg over %d cars" % [worst_facing, facing_errors.size()])
	var top := 0
	var top_name := ""
	for n in lane_counts:
		if lane_counts[n] > top:
			top = lane_counts[n]
			top_name = n
	_check("spawns rotate across lanes", lane_counts.size() >= 3 and top * 2 <= gaps.size(),
			"%d lanes used, busiest %s took %d of %d" % [lane_counts.size(), top_name, top, gaps.size()])
	_check("no car reclaimed on its spawn lane", short == 0,
			"%d of %d in-range reclaims drove < %.0f m (%d left range, exempt)"
			% [short, done.size(), MIN_DRIVE_M, left_range])
	_check("no car left standing", idle_max <= MAX_IDLE_S, "longest idle %.1f s" % idle_max)
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
