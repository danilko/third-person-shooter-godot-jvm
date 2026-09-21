extends SceneTree
## Collision cross-section of a streamed DebugRoads lane (PLAN.md 0.1 diagnosis aid).
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_road_section.gd \
##       -- --lane=loop_R0 --at=-181,106 [--half=16] [--step=0.25]
##       -- --world=res://src/main/resources/com/openworld/world/World.tscn --park=1562,-464 ...   (another scene;
##       `park` puts the streaming player over that XZ so the island's zone piece is loaded)
##
## Finds the point on `lane` nearest to (x, z), then casts a ray straight down every `step` metres across
## the lane (from `half` m left to `half` m right, perpendicular to its travel direction) and prints every
## surface each ray passes through, top first: the collider and its height. That is the ground a wheel ray
## and the car's hull actually meet there, which the visual mesh does not tell you.

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PARK := Vector3(10, 400, 10)

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

## Every collider a vertical ray passes through at `o`'s XZ, top first, as "name height".
func _column(space: PhysicsDirectSpaceState3D, o: Vector3) -> Array:
	var hits := []
	var exclude := []
	for k in range(6):
		var rq := PhysicsRayQueryParameters3D.create(Vector3(o.x, o.y + 30.0, o.z), Vector3(o.x, o.y - 40.0, o.z), 0xFFFFFFFF, exclude)
		var hit := space.intersect_ray(rq)
		if hit.is_empty():
			break
		var who: Object = hit["collider"]
		hits.append("%s %.3f" % [str((who as Node).name) if who is Node else str(who), hit["position"].y])
		exclude.append(hit["rid"])
	return hits

func _initialize() -> void:
	var lane_name := _arg("lane", "loop_R0")
	var at_xz := _arg("at", "0,0").split(",")
	var half := float(_arg("half", "16"))
	var step := float(_arg("step", "0.25"))
	var world: Node = (load(_arg("world", WORLD)) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	player.global_position = PARK
	if _arg("park", "") != "":
		var pxz := _arg("park", "").split(",")
		player.global_position = Vector3(float(pxz[0]), 400.0, float(pxz[1]))
	var lane: Node = null
	for i in range(600):
		await physics_frame
		for n in world.find_children(lane_name, "Node", true, false):
			var s = n.get_script()
			if s != null and str(s.resource_path).ends_with("PathLaneRoute.java"):
				lane = n
		if lane != null:
			break
	if lane == null:
		print("lane %s never streamed" % lane_name)
		quit(2)
		return
	for i in range(30):
		await physics_frame
	var path: Path3D = lane.get_node("Path3D")
	var c: Curve3D = path.curve
	var q := Vector3(float(at_xz[0]), 0, float(at_xz[1]))
	var off := c.get_closest_offset(path.to_local(q))
	var at := path.to_global(c.sample_baked(off))
	var a := path.to_global(c.sample_baked(maxf(0.0, off - 1.0)))
	var b := path.to_global(c.sample_baked(minf(c.get_baked_length(), off + 1.0)))
	var dir := Vector3(b.x - a.x, 0, b.z - a.z).normalized()
	var right := Vector3(-dir.z, 0, dir.x)
	print("section of %s at offset %.1f m: lane point (%.2f, %.2f, %.2f), heading (%.2f, %.2f), right = +" %
			[lane_name, off, at.x, at.y, at.z, dir.x, dir.z])
	var space := (world as Node3D).get_world_3d().direct_space_state
	var along := float(_arg("along", "0"))
	if along > 0.0:
		# LENGTHWISE: `lat` metres right of the lane, every `step` metres from `along` behind to `along` ahead.
		var lat := float(_arg("lat", "0"))
		var d := -along
		while d <= along + 1e-6:
			var o2 := off + d
			if o2 >= 0.0 and o2 <= c.get_baked_length():
				var pa := path.to_global(c.sample_baked(maxf(0.0, o2 - 0.5)))
				var pb := path.to_global(c.sample_baked(minf(c.get_baked_length(), o2 + 0.5)))
				var pc := path.to_global(c.sample_baked(o2))
				var dd := Vector3(pb.x - pa.x, 0, pb.z - pa.z).normalized()
				var rr := Vector3(-dd.z, 0, dd.x)
				var oo := pc + rr * lat
				print("  %+7.2f m  (%.2f, %.2f)  %s" % [d, oo.x, oo.z, "  |  ".join(_column(space, oo))])
			d += step
		quit(0)
		return
	var s := -half
	while s <= half + 1e-6:
		print("  %+6.2f m  %s" % [s, "  |  ".join(_column(space, at + right * s))])
		s += step
	quit(0)
