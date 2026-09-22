extends SceneTree
## Godot half of the toon parity gate (PLAN.md 6.10). NEEDS A DISPLAY (xvfb-run -a).
##
##   xvfb-run -a godot --path . --script tools/godot/probe_toon_parity.gd -- [--shot=<png>] [--control]
##
## An orthographic camera looks down -Z at a unit sphere wearing the character toon material, lit by ONE
## sun at SUN_AZIMUTH_DEG in the view plane, with no ambient. Along the sphere's horizontal midline each
## pixel's normal is known exactly (n = (x, 0, sqrt(1 - x^2))), so where the lit band turns to shade IS an
## N.L -- which must equal toon_params.json's shade_threshold. Prints `TERMINATOR_NDL <value>`; the Blender
## half (blender/tools/toon_parity_blender.py) prints the same from its node group, and
## tools/check_toon_parity.sh compares both against the JSON. `--control` uses a plain StandardMaterial3D,
## whose Lambert gradient has no band: its "edge" lands at N.L ~ 0.5 of the peak, not at the threshold.

const SUN_AZIMUTH_DEG := 50.0     # the sun's direction, measured from the camera axis toward +X

func _initialize() -> void:
	var shot := ""
	var control := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot = a.substr(7)
		elif a == "--control":
			control = true
	var world := Node3D.new()
	root.add_child(world)
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0, 0, 0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0, 0, 0)
	env.ambient_light_energy = 0.0
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	world.add_child(we)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 2.2
	cam.position = Vector3(0, 0, 5)
	world.add_child(cam)
	cam.current = true
	var mi := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 1.0
	sm.height = 2.0
	sm.radial_segments = 128
	sm.rings = 64
	mi.mesh = sm
	if control:
		var std := StandardMaterial3D.new()
		std.albedo_color = Color(1, 1, 1)
		mi.material_override = std
	else:
		var mat := ShaderMaterial.new()
		mat.shader = load("res://assets/vfx/toon/toon_character.gdshader")
		var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
		img.fill(Color(1, 1, 1))
		mat.set_shader_parameter("albedo_texture", ImageTexture.create_from_image(img))
		mat.set_shader_parameter("rim_strength", 0.0)       # measure the band alone
		mat.set_shader_parameter("specular_strength", 0.0)
		mi.material_override = mat
	world.add_child(mi)
	var sun := DirectionalLight3D.new()
	world.add_child(sun)
	# a DirectionalLight3D shines down its own -Z: point it FROM the light direction L toward the sphere
	var az := deg_to_rad(SUN_AZIMUTH_DEG)
	var to_light := Vector3(sin(az), 0, cos(az))
	sun.look_at_from_position(to_light * 10.0, Vector3.ZERO, Vector3.UP)
	sun.light_energy = 0.6    # nothing clips: both levels are read off the image
	for i in range(8):
		await process_frame
	RenderingServer.force_draw()
	await process_frame
	var img2: Image = root.get_texture().get_image()
	if shot != "":
		img2.save_png(shot)
	# the window size is the display's, not ours: read the geometry off the image (an orthographic camera's
	# `size` spans the image HEIGHT)
	var w := img2.get_width()
	var h := img2.get_height()
	var px_per_unit: float = h / cam.size
	var cx: float = w * 0.5
	var y := h / 2
	var row := []
	for x in range(w):
		row.append(img2.get_pixel(x, y).srgb_to_linear().get_luminance())   # LINEAR, as the shader works
	var at := func(u: float) -> float: return row[clampi(int(cx + u * px_per_unit), 0, w - 1)]
	var lit_level: float = at.call(sin(az))                # the sphere point facing the sun: N.L = 1
	var shade_level: float = at.call(-0.85)                # well round the dark side
	var mid := (lit_level + shade_level) * 0.5
	var ndl_edge := NAN
	# walk from the sun-facing point toward the dark side; the first pixel under the mid level is the edge
	var x0 := int(cx + sin(az) * px_per_unit)
	for x in range(x0, 0, -1):
		var u: float = (x + 0.5 - cx) / px_per_unit
		if absf(u) >= 1.0:
			break
		if row[x] < mid:
			var n := Vector3(u, 0, sqrt(1.0 - u * u))
			ndl_edge = n.dot(to_light)
			break
	# the edge's WIDTH, as N.L between the 75% and the 25% crossings: a ramp is narrow, Lambert is wide
	var ndl_at := func(level: float) -> float:
		for x in range(x0, 0, -1):
			var u: float = (x + 0.5 - cx) / px_per_unit
			if absf(u) >= 1.0:
				return NAN
			if row[x] < level:
				return Vector3(u, 0, sqrt(1.0 - u * u)).dot(to_light)
		return NAN
	var hi: float = ndl_at.call(shade_level + 0.75 * (lit_level - shade_level))
	var lo: float = ndl_at.call(shade_level + 0.25 * (lit_level - shade_level))
	print("LEVELS lit %.3f shade %.3f (shade/lit %.3f)" % [lit_level, shade_level, shade_level / maxf(lit_level, 1e-6)])
	print("EDGE_WIDTH_NDL %.4f" % (hi - lo))
	print("TERMINATOR_NDL %.4f" % ndl_edge)
	quit(0)
