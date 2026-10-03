extends SceneTree
## Pictures of what a passenger reads (needs a display): a station's departure board (発車標) from the platform, and
## the screen over a door inside a car (ドア上LCD), on DebugWorld with the timetable jumped to a stop.
##
##   godot --path . --script tools/godot/shot_train_displays.gd -- --out=<dir>

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"

func _initialize() -> void:
	var out := OS.get_user_data_dir()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			out = a.substr(6)
	DirAccess.make_dir_recursive_absolute(out)
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var tr: Node = root.get_node("TrainSystem")
	for i in 60:
		await physics_frame
	# the next dwell of set 0, a little after it begins
	var t := float(tr.call("clock_now")) + 5.0
	var prev: PackedFloat64Array = tr.call("set_state_at", 0, t)
	while true:
		t += 0.25
		var st: PackedFloat64Array = tr.call("set_state_at", 0, t)
		if prev[2] < 0.5 and st[2] > 0.5:
			break
		prev = st
	tr.set("clock_offset", float(tr.get("clock_offset")) + t + 3.0 - float(tr.call("clock_now")))
	var player: Node3D = world.get_node("Characters/Player")
	var st0: PackedFloat64Array = tr.call("set_state_at", 0, t + 3.0)
	player.global_position = Vector3(st0[4] + 6.0, st0[5] + 1.3, st0[6])
	player.process_mode = Node.PROCESS_MODE_DISABLED
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.current = true
	cam.global_position = Vector3(st0[4], st0[5] + 3.0, st0[6] + 10.0)
	for i in 90:
		await process_frame
	# the board: stand on the platform a few metres along from it, looking at it
	for b in tr.get_children():
		if str(b.name).begins_with("Board_"):
			var bn := b as Node3D
			var along: Vector3 = bn.global_transform.basis.z
			cam.global_position = bn.global_position + along * 6.0 + Vector3(0, -1.2, 0)
			cam.look_at(bn.global_position, Vector3.UP)
			for i in 20:
				await process_frame
			RenderingServer.force_draw()
			get_root().get_texture().get_image().save_png(out + "/board.png")
			print("wrote board.png (%s)" % b.name)
			break
	# inside car 1, looking at a door-top screen
	var car: Node3D = tr.call("car_body_now", 0, 1)
	if car != null:
		var xf := car.global_transform
		cam.global_position = xf * Vector3(-0.6, 2.1, 7.23)
		cam.look_at(xf * Vector3(1.29, 3.13, 7.23), xf.basis.y)
		for i in 20:
			await process_frame
		RenderingServer.force_draw()
		get_root().get_texture().get_image().save_png(out + "/screen.png")
		print("wrote screen.png")
		cam.global_position = xf * Vector3(0.2, 2.6, -8.5)
		cam.look_at(xf * Vector3(0.0, 2.4, 8.0), xf.basis.y)
		for i in 20:
			await process_frame
		RenderingServer.force_draw()
		get_root().get_texture().get_image().save_png(out + "/interior.png")
		print("wrote interior.png")
	quit(0)
