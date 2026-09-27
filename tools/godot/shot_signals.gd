extends SceneTree
## A picture of a working signal (NEEDS A DISPLAY: xvfb-run -a): DebugWorld, a camera on a signalled lane looking
## at its junction, its lamps and the Japanese name plate. `-- <out.png> [--lane=link_F0] [--back=35] [--h=2.2]`.
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"

func _arg(n: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % n):
			return a.substr(n.length() + 3)
	return d

func _initialize() -> void:
	var out := "/tmp/signals.png"
	for a in OS.get_cmdline_user_args():
		if not a.begins_with("--"):
			out = a
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	(w.get_node("Characters/Player") as Node).process_mode = Node.PROCESS_MODE_DISABLED
	var lane: Node = null
	for i in 60 * 30:
		await process_frame
		var hits := w.find_children(_arg("lane", "link_F0"), "Node", true, false)
		if not hits.is_empty():
			lane = hits[0]
			break
	var path: Path3D = lane.get_node("Path3D")
	var L := path.curve.get_baked_length()
	(w.get_node("Characters/Player") as Node3D).global_position = path.to_global(path.curve.sample_baked(L)) + Vector3(0, 1, 0)
	for i in 400:
		await process_frame
	var cam := Camera3D.new()
	w.add_child(cam)
	var back := float(_arg("back", "35"))
	cam.global_position = path.to_global(path.curve.sample_baked(L - back)) + Vector3(0, float(_arg("h", "2.2")), 0)
	cam.look_at(path.to_global(path.curve.sample_baked(L)) + Vector3(0, 3.5, 0), Vector3.UP)
	cam.fov = 55
	if _arg("plate", "") != "":
		# look straight at the k-th name plate of the plan, from `--back` m in front of it
		var plan = JSON.parse_string(FileAccess.get_file_as_string("res://assets/world_source/pieces/Roads_DebugRoads.signals.json"))
		var plates := []
		for j in plan["junctions"]:
			plates += j["plates"]
		var pl = plates[int(_arg("plate", "0")) % plates.size()]
		var pp := Vector3(pl["pos"][0], pl["pos"][1], pl["pos"][2])
		var nn := Vector3(pl["normal"][0], pl["normal"][1], pl["normal"][2])
		cam.global_position = pp + nn * back
		cam.look_at(pp, Vector3.UP)
	cam.current = true
	for i in 90:
		await process_frame
	await RenderingServer.frame_post_draw
	RenderingServer.force_draw()
	root.get_viewport().get_texture().get_image().save_png(out)
	print("shot_signals: %s" % out)
	quit(0)
