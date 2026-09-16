extends SceneTree
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PARK := Vector3(10, 400, 10)

func _col(space: PhysicsDirectSpaceState3D, x: float, z: float) -> Array:
	var out := []
	var exclude := []
	for k in range(8):
		var rq := PhysicsRayQueryParameters3D.create(Vector3(x, 60, z), Vector3(x, -40, z), 0xFFFFFFFF, exclude)
		var hit := space.intersect_ray(rq)
		if hit.is_empty():
			break
		out.append([hit["collider"], hit["position"].y, hit["normal"], hit["rid"]])
		exclude.append(hit["rid"])
	return out

func _nm(o: Object) -> String:
	return str((o as Node).name) if o is Node else str(o)

func _initialize() -> void:
	var world: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	var lane: Node = null
	for i in range(900):
		await physics_frame
		for n in world.find_children("loop_F0", "Node", true, false):
			lane = n
		if lane != null:
			break
	for i in range(60):
		await physics_frame
	var space := (world as Node3D).get_world_3d().direct_space_state
	var names := {}
	var proud := []
	var others := []
	var overl := {}
	var sphere := SphereShape3D.new()
	sphere.radius = 0.35
	var x := -410.0
	while x <= -320.0:
		var z := 40.0
		while z <= 135.0:
			var col := _col(space, x, z)
			var road_y := -INF
			var terr_y := -INF
			for h in col:
				var nm := _nm(h[0])
				names[nm] = names.get(nm, 0) + 1
				if nm.find("road") >= 0 and road_y == -INF:
					road_y = h[1]
				elif nm == "Terrain3D" and terr_y == -INF:
					terr_y = h[1]
			if road_y > -INF:
				if terr_y > road_y + 0.02:
					proud.append("(%.1f,%.1f) terrain %.3f above road %.3f by %.3f" % [x, z, terr_y, road_y, terr_y - road_y])
				for h in col:
					var nm2 := _nm(h[0])
					if nm2.find("road") < 0 and nm2 != "Terrain3D" and h[1] > road_y + 0.03 and h[1] < road_y + 3.0:
						others.append("(%.1f,%.1f) %s top %.3f (road %.3f)" % [x, z, nm2, h[1], road_y])
				var q := PhysicsShapeQueryParameters3D.new()
				q.shape = sphere
				q.transform = Transform3D(Basis(), Vector3(x, road_y + 0.9, z))
				for r in space.intersect_shape(q, 16):
					var n3 := _nm(r["collider"])
					overl[n3] = overl.get(n3, 0) + 1
					if overl[n3] <= 5:
						print("OVERLAP at (%.1f, %.1f, %.2f): %s  class %s  shape %d" % [x, road_y + 0.9, z, n3, r["collider"].get_class(), r["shape"]])
			z += 1.0
		x += 1.0
	print("colliders seen in columns: %s" % str(names))
	print("terrain proud of road: %d" % proud.size())
	for s in proud.slice(0, 25):
		print("  " + s)
	print("other colliders 3 cm - 3 m above road: %d" % others.size())
	for s in others.slice(0, 25):
		print("  " + s)
	print("sphere overlaps at 0.9 m above road: %s" % str(overl))
	quit(0)
