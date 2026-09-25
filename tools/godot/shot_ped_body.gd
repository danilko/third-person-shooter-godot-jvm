extends SceneTree

## The LIGHT-PED body, beside the body it is an LOD of. NEEDS A DISPLAY (a --headless run draws with
## the dummy renderer and saves an empty frame).
##
##   xvfb-run -a <godot> --path . --script tools/godot/shot_ped_body.gd -- --out=<dir> [--dist=6,20,80]
##
## `probe_ped_body.gd` asserts the STRUCTURE -- one surface, one material, the clips, the skeleton --
## and none of that can see the one thing an atlas gets wrong: a cell mapped to the wrong face, or
## flipped. That is a picture question, so this takes the picture: the full body on the left and the
## LOD on the right, same pose, same frame, at each distance. 80 m is the nearest the crowd's far tier
## is ever drawn (PedCrowd.promoteDistance), so that frame is what a player actually sees.

const FULL := "res://assets/characters/shino/shino.tscn"
const PED  := "res://assets/characters/shino/shino_ped.tscn"
const CLIP := "upright_walk_forward"

func _arg(a: PackedStringArray, k: String, d: String) -> String:
	for s in a:
		if s.begins_with("--%s=" % k):
			return s.substr(k.length() + 3)
	return d

func _spawn(path: String, x: float) -> Node3D:
	var n: Node3D = (load(path) as PackedScene).instantiate()
	root.add_child(n)
	n.global_position = Vector3(x, 0, 0)
	var ap := n.get_node_or_null("AnimationPlayer") as AnimationPlayer
	if ap != null and ap.has_animation(CLIP):
		ap.play(CLIP)
		ap.seek(0.6, true, true)
		ap.pause()
	return n

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var out := _arg(args, "out", "/tmp/ped_shots")
	DirAccess.make_dir_recursive_absolute(out)
	var dists: Array = []
	for s in _arg(args, "dist", "6,20,80").split(","):
		dists.append(float(s))

	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.35, 0.40, 0.46)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(1, 1, 1)
	e.ambient_light_energy = 1.0
	env.environment = e
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	root.add_child(sun)
	sun.rotation_degrees = Vector3(-45, 35, 0)

	# 0.9 m apart: far enough not to touch, near enough that one frame holds both at 80 m
	var full := _spawn(FULL, -0.45)
	var ped := _spawn(PED, 0.45)
	print("full=%s ped=%s" % [full.name, ped.name])

	var cam := Camera3D.new()
	root.add_child(cam)
	cam.current = true
	cam.fov = 75.0
	await process_frame
	await process_frame

	for d in dists:
		# framed on the chest, which is what a crowd is read by
		# from -Z: the bodies carry the game's 180-degree turn, so they FACE this side
		cam.global_position = Vector3(0, 0.95, -d)
		cam.look_at(Vector3(0, 0.95, 0), Vector3.UP)
		# at 80 m the pair is a few pixels, so zoom instead of walking away: the FOV is what makes
		# the on-screen size honest, and a narrow FOV at 80 m shows what the atlas resolves to.
		cam.fov = 75.0 if d <= 20.0 else 6.0
		if d <= 3.0:
			cam.fov = 55.0
		for _i in 4:
			await process_frame
		RenderingServer.force_draw()
		var img := get_root().get_texture().get_image()
		var p := "%s/ped_vs_full_%dm.png" % [out, int(d)]
		img.save_png(p)
		print("  %s  (%dx%d, fov %.0f)" % [p, img.get_width(), img.get_height(), cam.fov])
	print("RESULT PASS")
	quit(0)
