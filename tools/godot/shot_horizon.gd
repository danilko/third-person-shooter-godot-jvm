extends SceneTree
## shot_horizon.gd -- render a world's horizon from several heights (needs a DISPLAY; no --headless). PLAN.md 3.7.
##
##   godot --path . --script tools/godot/shot_horizon.gd -- <out_dir> [--world=res://...tscn] [--heights=2,60,400,1500]
##                                                        [--yaw=180] [--pitch=-4] [--mark-sky-ground]
##
## Writes <out_dir>/horizon_<height>.png looking out to sea (yaw 180 = towards -Z from the island centre's edge) and
## prints, per shot, the colour of three rows just below the horizontal line and the mean of the far sea, so a band
## between the sea and the sky shows up as a number, not only as a picture.
## `--mark-sky-ground` paints the sky shader's below-horizon colour magenta: whatever turns magenta is SKY, not world.
## `--ground-color=r,g,b` tries a below-horizon colour without editing the scene.

var _out := ""
var _world := "res://src/main/resources/com/openworld/world/World.tscn"
var _heights: Array = [2.0, 60.0, 400.0, 1500.0]
var _yaw := 180.0
var _pitch := -4.0
var _mark := false
var _ground := Color(-1, 0, 0)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: shot_horizon.gd -- <out_dir> [--world=] [--heights=] [--yaw=] [--pitch=] [--mark-sky-ground]")
		quit(1)
		return
	_out = args[0]
	for a in args.slice(1):
		if a.begins_with("--world="):
			_world = a.substr(8)
		elif a.begins_with("--heights="):
			_heights = Array(a.substr(10).split(",")).map(func(s): return float(s))
		elif a.begins_with("--yaw="):
			_yaw = float(a.substr(6))
		elif a.begins_with("--pitch="):
			_pitch = float(a.substr(8))
		elif a == "--mark-sky-ground":
			_mark = true
		elif a.begins_with("--ground-color="):
			var c := a.substr(15).split(",")
			_ground = Color(float(c[0]), float(c[1]), float(c[2]))
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = Vector2i(1600, 900)
	_run.call_deferred()


func _sky_material(n: Node) -> ShaderMaterial:
	if n is WorldEnvironment and n.environment != null and n.environment.sky != null:
		return n.environment.sky.sky_material as ShaderMaterial
	for c in n.get_children():
		var m := _sky_material(c)
		if m != null:
			return m
	return null


func _run() -> void:
	var world: Node = (load(_world) as PackedScene).instantiate()
	root.add_child(world)
	for i in 30:
		await process_frame
	var sm := _sky_material(world)
	if sm != null and _mark:
		sm.set_shader_parameter("ground_color", Color(1, 0, 1))
		print("sky ground_color -> magenta")
	elif sm != null and _ground.r >= 0.0:
		sm.set_shader_parameter("ground_color", _ground)
		print("sky ground_color -> %s" % _ground)
	var cam := Camera3D.new()
	cam.far = 100000.0
	cam.fov = 60.0
	root.add_child(cam)
	for h in _heights:
		cam.global_position = Vector3(0.0, float(h), 0.0)
		cam.rotation_degrees = Vector3(_pitch, _yaw, 0.0)
		for i in 20:
			cam.make_current()
			await process_frame
		RenderingServer.force_draw()
		await process_frame
		var img := root.get_texture().get_image()
		var path := "%s/horizon_%d.png" % [_out, int(h)]
		img.save_png(path)
		# the horizontal line's row on screen: pitch below centre by the camera's own pitch
		var hy := int(img.get_height() * 0.5 - img.get_height() * 0.5 * tan(deg_to_rad(-_pitch)) / tan(deg_to_rad(cam.fov * 0.5)))
		var rows := []
		for d in [4, 20, 60]:
			rows.append(_row_mean(img, clampi(hy + d, 0, img.get_height() - 1)))
		print("h=%6.0f  horizon row %d  below: +4 %s  +20 %s  +60 %s  bottom %s  -> %s" % [h, hy, rows[0], rows[1],
				rows[2], _row_mean(img, img.get_height() - 5), path])
	quit(0)


func _row_mean(img: Image, y: int) -> String:
	var c := Color(0, 0, 0)
	var n := 0
	for x in range(0, img.get_width(), 8):
		c += img.get_pixel(x, y)
		n += 1
	c /= n
	return "(%.2f %.2f %.2f)" % [c.r, c.g, c.b]

