extends SceneTree
## Pictures of a station LIFT (needs a DISPLAY: `xvfb-run -a <godot> --path . --script tools/godot/shot_lift.gd --
## <out_dir> [--scene=<Station_X_Shop.tscn>] [--lift=N]`). For the lift's bottom and top stop, a camera 6 m out
## along its door axis at eye height looks back at the doors: once shut, once called open. Also a 3/4 view along the
## stair beside it. Writes <out_dir>/lift<N>_{low,high}_{shut,open}.png and lift<N>_stair.png.

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/buildings/Station_Suburb_Shop.tscn"

func _initialize() -> void:
	_run.call_deferred()

func _lifts(n: Node, out: Array) -> void:
	if n.has_method("phase_now"):
		out.append(n)
	for c in n.get_children():
		_lifts(c, out)

func _frames(n: int) -> void:
	for i in range(n):
		await process_frame

func _shot(path: String) -> void:
	RenderingServer.force_draw()
	await _frames(3)
	root.get_texture().get_image().save_png(path)
	print("  -> ", path)

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var out := args[0]
	var scene := DEFAULT_SCENE
	var which := 0
	for a in args:
		if a.begins_with("--scene="):
			scene = a.substr(8)
		elif a.begins_with("--lift="):
			which = int(a.substr(7))
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1280, 800)
	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.62, 0.72, 0.82)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.8, 0.8, 0.8)
	e.ambient_light_energy = 0.6
	env.environment = e
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.shadow_enabled = true
	world.add_child(sun)
	var st: Node3D = (load(scene) as PackedScene).instantiate()
	world.add_child(st)
	await _frames(5)
	var lifts: Array = []
	_lifts(st, lifts)
	var lift: Node3D = lifts[mini(which, lifts.size() - 1)]
	var cam := Camera3D.new()
	cam.fov = 70
	world.add_child(cam)
	cam.current = true
	var xf: Transform3D = lift.global_transform
	var ax := xf.basis.x.normalized()
	var rise := float(lift.get("rise"))
	for s in [0, 1]:
		var base: Vector3 = xf.origin + Vector3(0, rise * s, 0)
		cam.global_position = base - ax * 3.6 + Vector3(0, 1.6, 0)
		cam.look_at(base + Vector3(0, 1.2, 0), Vector3.UP)
		await _frames(10)
		await _shot("%s/lift%d_%s_shut.png" % [out, which, "low" if s == 0 else "high"])
		if s == 1:
			# fetch the car up first: a call up top, let it travel
			lift.call_stop(1)
			for i in range(900):
				await physics_frame
				if int(lift.stop_now()) == 1 and float(lift.door_now()) > 0.99:
					break
		else:
			lift.call_stop(0)
			for i in range(200):
				await physics_frame
				if float(lift.door_now()) > 0.99:
					break
		await _shot("%s/lift%d_%s_open.png" % [out, which, "low" if s == 0 else "high"])
	# the stair's open side, from the hall: across from the band toward the lane, at eye height, looking along it
	var inward := Vector3(0, 0, -signf(xf.origin.z - st.global_position.z))
	cam.global_position = xf.origin + inward * 5.0 + ax * 4.0 + Vector3(0, 1.6, 0)
	cam.look_at(xf.origin + ax * 11.0 + Vector3(0, rise * 0.35, 0), Vector3.UP)
	await _frames(10)
	await _shot("%s/lift%d_stair.png" % [out, which])
	quit(0)
