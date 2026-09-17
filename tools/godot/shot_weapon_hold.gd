extends SceneTree
## Real-renderer close-ups of a held weapon: the firing hand and the support hand, in the HOLD (no aim) and
## AIM poses, through the shipped Player path (pickup, on_set_weapon, `aim` held through Input). Runs WITH a
## display (not --headless). For a weapon with a fire_animation it also fires once and shoots the part mid-clip.
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_weapon_hold.gd -- \
##       --weapons=SNR1,ASR1,REV1 --out=/tmp/shots [--no-aim]
##
## The camera is placed in the WEAPON's frame (origin = grip, -Z muzzle, +Y up), so every weapon is framed the
## same way: `right` from the firing-hand side, `left` from the support side, `under` from below and in front,
## `wide` a 1.1 m three-quarter view of the upper body.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"

var out := "/tmp/shots"

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _shoot(cam: Camera3D, gun: Node3D, local_eye: Vector3, local_look: Vector3, path: String) -> void:
	# The camera rides the weapon, so a kick or a physics step between placing it and the draw cannot move
	# the weapon on screen: frames of one clip line up pixel for pixel.
	if cam.get_parent() != gun:
		cam.get_parent().remove_child(cam)
		gun.add_child(cam)
	cam.transform = Transform3D(Basis.looking_at(local_look - local_eye, Vector3.UP), local_eye)
	cam.make_current()
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(path)
	print("  wrote ", path)

func _views(cam: Camera3D, gun: Node3D, tag: String) -> void:
	var sp: Node3D = gun.get_node_or_null("SupportPoint")
	var support := sp.position if sp else Vector3(0, 0, -0.25)
	await _shoot(cam, gun, Vector3(0.38, 0.04, -0.02), Vector3(0, 0.02, -0.03), "%s/%s_right.png" % [out, tag])
	await _shoot(cam, gun, Vector3(-0.38, 0.04, -0.02), Vector3(0, 0.02, -0.03), "%s/%s_inside.png" % [out, tag])
	await _shoot(cam, gun, support + Vector3(-0.36, 0.02, 0.0), support, "%s/%s_support.png" % [out, tag])
	await _shoot(cam, gun, Vector3(0.12, -0.30, -0.14), Vector3(0, 0.01, -0.06), "%s/%s_under.png" % [out, tag])
	await _shoot(cam, gun, Vector3(0.9, 0.35, -0.7), Vector3(-0.1, 0.1, 0.1), "%s/%s_wide.png" % [out, tag])

func _initialize() -> void:
	out = _arg("out", out)
	DirAccess.make_dir_recursive_absolute(out)
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(Vector2i(900, 700))
	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.32, 0.34, 0.37)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.55, 0.55, 0.58)
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 35, 0)
	world.add_child(sun)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(200, 2, 200)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var cam := Camera3D.new()
	cam.fov = 45.0
	cam.near = 0.01
	root.add_child(cam)
	var x := 0.0
	for id in _arg("weapons", "SNR1,ASR1").split(","):
		var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
		world.add_child(p)
		p.position = Vector3(x, 1.2, 0)
		x += 8.0
		await _tick(40)
		var gun: Node3D = (load(WEAPON % id) as PackedScene).instantiate()
		world.add_child(gun)
		gun.global_position = p.global_position + Vector3(0, 0.3, 0)
		await _tick(30)
		var wc: Node = p.get_node("WeaponController")
		for slot in range(7):
			if String(gun.get_parent().name).begins_with("Socket"):
				break
			wc.call("on_set_weapon", slot)
			await _tick(40)
		print(id, " in ", gun.get_parent().name)
		await _tick(60)
		await _views(cam, gun, "%s_hold" % id)
		if not "--no-aim" in OS.get_cmdline_user_args():
			Input.action_press("aim")
			await _tick(70)
			await _views(cam, gun, "%s_aim" % id)
			var clip := String(gun.get("fire_animation"))
			if clip != "":
				Input.action_press("fire")
				await _tick(2)
				Input.action_release("fire")
				# frames after the press (the press itself held 2 frames)
				var waited := 2
				for f in [6, 11, 15, 19, 26]:
					await _tick(f - waited)
					waited = f
					await _shoot(cam, gun, Vector3(0.30, 0.10, -0.08), Vector3(0, 0.07, -0.08), "%s/%s_fired_f%02d.png" % [out, id, f])
					waited += 2   # the shot itself spends frames
			Input.action_release("aim")
			await _tick(40)
		cam.get_parent().remove_child(cam)
		root.add_child(cam)
		p.queue_free()
		gun.queue_free()
		await _tick(5)
	quit(0)
