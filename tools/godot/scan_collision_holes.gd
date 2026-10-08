extends SceneTree
## Scans a square of World.tscn for spots where the first WORLD collider straight down is more than 0.5 m under the
## terrain surface (a hole a body falls through). Streams the spot in first. -- --at=x,z --half=m --step=m

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var at := Vector2(679, -140)
	var half := 40.0
	var step := 1.0
	for a in args:
		if a.begins_with("--at="):
			var p := a.substr(5).split(",")
			at = Vector2(float(p[0]), float(p[1]))
		elif a.begins_with("--half="):
			half = float(a.substr(7))
		elif a.begins_with("--step="):
			step = float(a.substr(7))
	var world: Node = (load("res://src/main/resources/com/openworld/world/World.tscn") as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await physics_frame
	var player: CharacterBody3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = Vector3(at.x, 30, at.y)
	var zm: Node = root.get_node_or_null("/root/ZoneManager")
	for i in 3000:
		await physics_frame
		if i > 200 and zm != null and int(zm.call("streaming_pending_now")) == 0:
			break
	var wb: Node = world.find_child("WorldBounds", true, false)
	var space := player.get_world_3d().direct_space_state
	var holes := 0
	var n := 0
	var worst := 0.0
	var x := at.x - half
	while x <= at.x + half:
		var z := at.y - half
		while z <= at.y + half:
			n += 1
			var th: float = wb.call("terrain_height", x, z)
			var q := PhysicsRayQueryParameters3D.create(Vector3(x, 80, z), Vector3(x, -60, z), 1)
			var hit := space.intersect_ray(q)
			var hy := -999.0
			if hit:
				hy = (hit.position as Vector3).y
			var gap := th - hy
			if gap > 0.5:
				holes += 1
				if gap > worst:
					worst = gap
				if holes <= 40:
					print("  hole at (%.1f, %.1f): terrain %.2f, first collider %.2f %s" % [x, z, th, hy, str(hit.get("collider")) if hit else "none"])
			z += step
		x += step
	print("RESULT %d of %d samples have no collider within 0.5 m of the terrain (worst %.2f m)" % [holes, n, worst])
	quit(0)
