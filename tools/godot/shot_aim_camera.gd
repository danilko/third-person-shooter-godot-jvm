extends SceneTree
## The TPS AIM camera at several shoulder offsets (user 2026-10-09: "move the camera closer to the character, so it
## lines up with the gun?"). NEEDS A DISPLAY. A real Player holding `aim` with an ASR1 (pickup path), looking at a
## wall 25 m out with a 1 m marker grid; for each shoulder offset it saves a picture and prints the camera's offset
## from the muzzle and the sideways gap between the camera's line and the gun's line 1 m past the muzzle -- the size
## of an edge that one of them sees past and the other does not.
##   xvfb-run -a godot --path . --script tools/godot/shot_aim_camera.gd -- --out=<dir> [--offsets=0.35,0.25,0.15]
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const ASR1 := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const COMBAT := "res://src/main/resources/com/openworld/character/combatstates/Combat.tres"

func _arg(name: String, def = null):
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
	return def

func _tick(n: int) -> void:
	for i in n:
		await process_frame

func _box(world: Node, size: Vector3, at: Vector3, col: Color) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = size
	cs.shape = sh
	b.add_child(cs)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	bm.material = m
	mi.mesh = bm
	b.add_child(mi)
	world.add_child(b)
	b.position = at

func _initialize() -> void:
	var out := String(_arg("out", "user://aimcam"))
	DirAccess.make_dir_recursive_absolute(out)
	var offsets := String(_arg("offsets", "0.35,0.25,0.15")).split(",")
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	world.add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.55, 0.7, 0.85)
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.6)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.add_child(env)
	_box(world, Vector3(200, 2, 200), Vector3(0, -1, 0), Color(0.45, 0.45, 0.45))
	_box(world, Vector3(30, 8, 0.5), Vector3(0, 4, -25), Color(0.85, 0.85, 0.8))
	for x in range(-6, 7, 2):
		_box(world, Vector3(0.1, 4, 0.1), Vector3(x, 2, -24.7), Color(0.1, 0.1, 0.1))
	_box(world, Vector3(1.2, 1.2, 0.3), Vector3(0, 0.6, -6), Color(0.8, 0.3, 0.2))  # a target box
	await _tick(3)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = Vector3(0, 0.2, 0)
	await _tick(40)
	var gun: Node3D = (load(ASR1) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(40)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	var combat: Resource = load(COMBAT)
	var keep: float = combat.get("camera_shoulder_offset")
	for o in offsets:
		# the rig reads the combat state's offsets when combat STARTS: leave combat, change, aim again
		Input.action_release("aim")
		await _tick(90)
		combat.set("camera_shoulder_offset", float(o))
		Input.action_press("aim")
		await _tick(90)
		var cam := p.get_node("ActiveCamera") as Node3D
		var muzzle: Node3D = gun.find_child("Muzzle", true, false)
		var aim := Vector3(0, 1.4, -24.7)
		var c := cam.global_position
		var m := muzzle.global_position
		var at := m + (aim - m).normalized() * 1.0
		# the camera line's point nearest `at`
		var d := (aim - c).normalized()
		var near := c + d * (at - c).dot(d)
		var rel := c - m
		print("shoulder %.2f: camera vs muzzle right %+.2f up %+.2f back %+.2f m | gap between the two lines 1 m past the muzzle %.2f m" % [
			float(o), rel.x, rel.y, rel.z, near.distance_to(at)])
		var img := root.get_texture().get_image()
		img.save_png("%s/aim_shoulder_%s.png" % [out, o])
	combat.set("camera_shoulder_offset", keep)
	Input.action_release("aim")
	quit()
