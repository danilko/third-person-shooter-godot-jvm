extends SceneTree
## What does the crowd's far tier cost per ped? (user, 2026-09-27). NEEDS A DISPLAY (vsync off).
##
##   godot --path . --script tools/godot/bench_crowd.gd -- --mode=skeletal|vat [--n=600] [--dist=100] [--body=shino]
##
## skeletal = the old light ped: a skinned `<body>_ped.tscn` with its own AnimationPlayer, walking.
## vat      = one MultiMesh instance per ped, animated in the vertex shader (tools/godot/bake_ped_vat.gd),
##            every transform re-written each frame the way PedCrowd does (one set_buffer call).
## Peds stand in a fan in front of the camera at --dist +-40 m. Prints the frame time (ms), the renderer's
## CPU and GPU time, draw calls and primitives, over 3 s after a 30-frame warm-up.
## Measured 2026-09-27 on this PC: see CLAUDE.md "The crowd's far tier is a vertex animation".

var n := 600
var dist := 100.0
var mode := "vat"
var body := "shino"

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--n="): n = int(a.substr(4))
		elif a.begins_with("--dist="): dist = float(a.substr(7))
		elif a.begins_with("--mode="): mode = a.substr(7)
		elif a.begins_with("--body="): body = a.substr(7)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	_run.call_deferred()

func _run() -> void:
	var w := Node3D.new()
	root.add_child(w)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	w.add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	w.add_child(env)
	var cam := Camera3D.new()
	cam.position = Vector3(0, 1.7, 0)
	cam.far = 2000
	w.add_child(cam)
	cam.make_current()
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var xforms: Array[Transform3D] = []
	for i in n:
		var ang := rng.randf_range(-0.6, 0.6)
		var r := dist + rng.randf_range(-40, 40)
		xforms.append(Transform3D(Basis(Vector3.UP, rng.randf() * TAU), Vector3(sin(ang) * r, 0, -cos(ang) * r)))
	var mm: MultiMesh = null
	var buf := PackedFloat32Array()
	if mode == "skeletal":
		var scene: PackedScene = load("res://assets/characters/%s/%s_ped.tscn" % [body, body])
		for t in xforms:
			var b: Node3D = scene.instantiate()
			w.add_child(b)
			b.transform = t
			var ap: AnimationPlayer = b.get_node_or_null("AnimationPlayer")
			if ap:
				ap.play("upright_walk_forward")
				ap.seek(rng.randf(), true)
	else:
		var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			"res://assets/characters/%s/%s_vat.json" % [body, body]))
		mm = MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_custom_data = true
		mm.use_colors = true
		mm.mesh = load(meta["mesh"])
		mm.instance_count = n
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		var mat := ShaderMaterial.new()
		mat.shader = load("res://assets/characters/crowd/ped_vat.gdshader")
		mat.set_shader_parameter("albedo_tex", load(meta["atlas"]))
		mat.set_shader_parameter("vat_pos", load(meta["positions"]))
		mmi.material_override = mat
		mmi.custom_aabb = AABB(Vector3(-400, -5, -400), Vector3(800, 20, 800))
		w.add_child(mmi)
		var walk: Dictionary = meta["clips"]["walk"]
		buf.resize(n * 20)
		for i in n:
			var t := xforms[i]
			var o := i * 20
			buf[o] = t.basis.x.x; buf[o + 1] = t.basis.y.x; buf[o + 2] = t.basis.z.x; buf[o + 3] = t.origin.x
			buf[o + 4] = t.basis.x.y; buf[o + 5] = t.basis.y.y; buf[o + 6] = t.basis.z.y; buf[o + 7] = t.origin.y
			buf[o + 8] = t.basis.x.z; buf[o + 9] = t.basis.y.z; buf[o + 10] = t.basis.z.z; buf[o + 11] = t.origin.z
			buf[o + 12] = 1.0; buf[o + 13] = 1.0; buf[o + 14] = 1.0; buf[o + 15] = 0.0
			buf[o + 16] = float(walk["row"]); buf[o + 17] = float(walk["frames"])
			buf[o + 18] = -rng.randf() * 2.0; buf[o + 19] = float(walk["fps"])
		mm.buffer = buf
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	for i in 30: await process_frame
	var t0 := Time.get_ticks_usec()
	var frames := 0
	var cpu := 0.0
	var gpu := 0.0
	while Time.get_ticks_usec() - t0 < 3e6:
		if mm != null:
			mm.buffer = buf          # the per-frame transform write PedCrowd makes (one call)
		await process_frame
		frames += 1
		cpu += RenderingServer.viewport_get_measured_render_time_cpu(root.get_viewport_rid())
		gpu += RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid())
	var ms := (Time.get_ticks_usec() - t0) / 1000.0 / frames
	print("[bench] %-8s n=%d dist=%.0f  frame %.2f ms  render-cpu %.2f  gpu %.2f  draws %d  prims %d"
		% [mode, n, dist, ms, cpu / frames, gpu / frames,
		   Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		   Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)])
	quit()
