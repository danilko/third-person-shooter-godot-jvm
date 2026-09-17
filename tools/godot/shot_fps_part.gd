extends SceneTree
## Is a weapon's moving part visible from the PLAYER'S OWN first-person camera? Fires once in FPS view (aim held,
## so the gun is up) and saves the game camera's frames through the part's clip, plus numbers: the part's size on
## screen and how many pixels a point on its rim moves per rendered frame. Runs WITH a display.
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_fps_part.gd -- \
##       --weapon=REV1 --part=Model/Cylinder --out=/tmp/fps [--hip]
##
## Rule of thumb used in the report: under ~2 px of motion per frame, or a part under ~20 px across, reads as still.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r := _find(c, nm)
		if r != null:
			return r
	return null

func _initialize() -> void:
	var out := _arg("out", "/tmp/fps")
	var id := _arg("weapon", "REV1")
	var part_path := _arg("part", "Model/Cylinder")
	DirAccess.make_dir_recursive_absolute(out)
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(Vector2i(1920, 1080))
	root.size = Vector2i(1920, 1080)
	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.45, 0.5, 0.55)
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
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(200, 200)
	mi.mesh = pm
	mi.position = Vector3(0, 1, 0)
	floor.add_child(mi)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
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
	p.set("is_fps_mode", true)
	var hip := "--hip" in OS.get_cmdline_user_args()
	if not hip:
		Input.action_press("aim")
	await _tick(90)
	var cam: Camera3D = _find(p, "ActiveCamera") as Camera3D
	var part: Node3D = gun.get_node(part_path) as Node3D
	var mesh := part as MeshInstance3D
	var aabb := mesh.get_aabb() if mesh else AABB(Vector3(-0.03, -0.03, -0.06), Vector3(0.06, 0.06, 0.12))
	# a rim point: on the part's local +X at its largest extent, in the middle of its length
	var rim_local := Vector3(aabb.end.x, 0, aabb.get_center().z)
	var view := "hip" if hip else "aim"
	print("%s %s from the FPS camera (fov %.1f, %s):" % [id, part_path, cam.fov, view])
	var prev := Vector2.INF
	for f in range(0, 30):
		if f == 1:
			Input.action_press("fire")
		if f == 3:
			Input.action_release("fire")
		await physics_frame
		await RenderingServer.frame_post_draw
		var xf := part.global_transform
		var corners: Array[Vector2] = []
		for i in range(8):
			corners.append(cam.unproject_position(xf * aabb.get_endpoint(i)))
		var lo := corners[0]
		var hi := corners[0]
		for c in corners:
			lo = lo.min(c)
			hi = hi.max(c)
		# rim motion relative to the GUN (so the kick moving the whole weapon is not counted as the part moving)
		var rim_now := cam.unproject_position(xf * rim_local)
		var rim_rest := cam.unproject_position(gun.global_transform * (part.transform.origin + rim_local))
		var rel := rim_now - rim_rest
		var step := 0.0 if prev == Vector2.INF else (rel - prev).length()
		prev = rel
		var ang := rad_to_deg(part.transform.basis.get_rotation_quaternion().get_angle())
		print("  frame %2d  part on screen %4.0f x %4.0f px  angle %5.1f deg  rim moved %4.1f px this frame  %s" % [
			f, hi.x - lo.x, hi.y - lo.y, ang, step, "on screen" if cam.is_position_in_frustum(xf.origin) else "OFF SCREEN"])
		if f in [0, 5, 9, 13, 17, 21, 26]:
			root.get_texture().get_image().save_png("%s/%s_fps_%s_f%02d.png" % [out, id, view, f])
	Input.action_release("aim")
	quit(0)
