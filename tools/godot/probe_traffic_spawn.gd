extends SceneTree
## PLAN.md 0.4 -- ambient cars must spawn where, and facing the way, they can keep driving.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_traffic_spawn.gd
##
## Runs the real DebugWorld (zone `debug_a`, plain `Lane_` route prefix) with the Player held alive
## and follows every streamed car from spawn to reclaim. Pair it with ZoneManager's own
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

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const STREAMED := "streamed_vehicle"
const SECONDS := 240
const MIN_DRIVE_M := 160.0
const CLEARANCE_M := 9.9          # ZoneManager.TRAFFIC_SPAWN_CLEARANCE, minus float slack
const FACING_TOL_DEG := 30.0
const MAX_IDLE_S := 15.0          # past ZoneManager.vehicleStallTimeout (12 s)

var cars := {}      # instance id -> state
var done: Array = []
var gaps: Array = []
var facing_errors: Array = []
var lane_counts := {}
var bridge: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-46s %s" % ["PASS" if ok else "FAIL", label, detail])

func _yaw(v: Vector3) -> float:
	return rad_to_deg(atan2(-v.x, -v.z))

## The published lane a spawn point sits on, and that lane's travel direction there.
func _lane_at(p: Vector3) -> Dictionary:
	var best := {"name": "", "dist": INF, "dir": Vector3.ZERO}
	for lane in bridge.get_children():
		var path: Path3D = lane.get_node_or_null(lane.get("source_path"))
		if path == null or path.curve == null:
			continue
		var c: Curve3D = path.curve
		var off := c.get_closest_offset(path.to_local(p))
		var at := path.to_global(c.sample_baked(off))
		var d := at.distance_to(p)
		if d < best["dist"]:
			var a := maxf(0.0, minf(off, c.get_baked_length() - 1.0))
			var dir := path.to_global(c.sample_baked(a + 1.0)) - path.to_global(c.sample_baked(a))
			best = {"name": str(lane.name), "dist": d, "dir": Vector3(dir.x, 0, dir.z)}
	return best

func _initialize() -> void:
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w   # ZoneManager and LaneGraph both resolve the world through current_scene
	bridge = w.get_node("RoadNetworkBridge")
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
				var early: bool = int(bridge.call("published_count")) == 0
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
				if not c["early"]:
					done.append({"dist": c["dist"], "secs": (f - c["spawn"]) / 60.0})
				print("  car gone after %5.1f s, drove %6.1f m" % [(f - c["spawn"]) / 60.0, c["dist"]])
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
	print("--- %d cars spawned after lanes published, %d reclaimed, %d alive at end"
			% [gaps.size(), done.size(), cars.size()])
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
			"%d of %d drove < %.0f m" % [short, done.size(), MIN_DRIVE_M])
	_check("no car left standing", idle_max <= MAX_IDLE_S, "longest idle %.1f s" % idle_max)
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
