extends SceneTree
## EVERY RESPAWN POINT IS A PLACE A BODY CAN STAND (PLAN.md 1c, 2026-10-06).
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_respawn_points.gd
##   ... -- --control      (each point moved 6 m INTO its building: must fail)
##
## A downed player wakes outside a hospital, clinic or police station on one of the building's MARK_respawn points
## (carried in places/World.places.json). For every point on the island, with the world streamed round it:
##   * there is ground under it (a downward ray finds a surface within 0.6 m);
##   * the character's capsule (r 0.35, h 1.75) standing there touches nothing on WORLD / CAR_WALL;
##   * it is OUTSIDE the building: a wall stands between it and the building's centre.

const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const PLACES := "res://src/main/resources/com/openworld/world/places/World.places.json"
const KINDS := ["Hospital", "HospitalSmall", "Clinic", "PoliceStation"]

var fails := 0
var checked := 0


func _check(ok: bool, what: String) -> void:
	checked += 1
	if not ok:
		fails += 1
		print("  [FAIL] %s" % what)


func _inside(q: Array, x: float, z: float) -> bool:
	# q = [kind, x0, z0, x1, z1, x2, z2, x3, z3]; a convex quad
	var sgn := 0.0
	for i in 4:
		var ax: float = q[1 + 2 * i]
		var az: float = q[2 + 2 * i]
		var bx: float = q[1 + 2 * ((i + 1) % 4)]
		var bz: float = q[2 + 2 * ((i + 1) % 4)]
		var c := (bx - ax) * (z - az) - (bz - az) * (x - ax)
		if absf(c) < 1e-6:
			continue
		if sgn == 0.0:
			sgn = signf(c)
		elif signf(c) != sgn:
			return false
	return true


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world: Node = (load(ISLAND) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 60:
		await physics_frame
	var player: Node3D = world.find_child("Player", true, false)
	var zm: Node = root.get_node_or_null("ZoneManager")
	var doc: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PLACES))
	var space := (world as Node3D).get_world_3d().direct_space_state
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.35
	capsule.height = 1.75
	var n_points := 0
	for pl in doc["places"]:
		if not (pl["kind"] in KINDS) or pl.get("respawn", []).is_empty():
			continue
		var at := Vector3(pl["at"][0], pl["at"][1], pl["at"][2])
		# the building's own footprint: the quad whose centre is nearest `at`
		var quad: Array = []
		var best := 1e9
		for q in doc["footprints"]:
			var cx: float = (q[1] + q[3] + q[5] + q[7]) / 4.0
			var cz: float = (q[2] + q[4] + q[6] + q[8]) / 4.0
			var d := Vector2(cx, cz).distance_to(Vector2(at.x, at.z))
			if d < best:
				best = d
				quad = q
		if player != null:
			player.process_mode = Node.PROCESS_MODE_DISABLED
			player.global_position = at + Vector3(0, 30, 0)
		for k in 60 * 30:
			await physics_frame
			if k > 30 and (zm == null or int(zm.call("streaming_pending_now")) == 0):
				break
		for i in 10:
			await physics_frame
		for r in pl["respawn"]:
			n_points += 1
			var p := Vector3(r[0], r[1], r[2])
			if control:
				p += (at - p).normalized() * 6.0
			var tag := "%s at %s" % [pl["kind"], p]
			var ray := PhysicsRayQueryParameters3D.create(p + Vector3(0, 2.0, 0), p + Vector3(0, -2.0, 0), 1)
			var hit := space.intersect_ray(ray)
			_check(not hit.is_empty() and absf(hit["position"].y - p.y) < 0.6,
				"%s: ground under it (%s)" % [tag, "none" if hit.is_empty() else "%.2f" % (hit["position"].y - p.y)])
			var floor_y: float = hit["position"].y if not hit.is_empty() else p.y
			var q := PhysicsShapeQueryParameters3D.new()
			q.shape = capsule
			q.collision_mask = 1 | 32
			q.transform = Transform3D(Basis(), Vector3(p.x, floor_y + 0.05 + 0.875, p.z))
			var hits := space.intersect_shape(q, 4)
			var names := []
			for h in hits:
				names.append(str(h["collider"].name))
			_check(hits.is_empty(), "%s: the capsule stands clear (%s)" % [tag, ", ".join(names)])
			# OUTSIDE: a wall of the building stands between the point and the building's centre (the footprint is the
			# whole plot, forecourt included, so it cannot say this)
			var wall := space.intersect_ray(PhysicsRayQueryParameters3D.create(
				Vector3(p.x, floor_y + 1.2, p.z), Vector3(at.x, floor_y + 1.2, at.z), 1))
			_check(not wall.is_empty(), "%s: outside, a wall between it and the building's centre" % tag)
	_check(n_points >= 10, "the island has respawn points (%d)" % n_points)
	print("probe_respawn_points: %d points, %d checks" % [n_points, checked])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
