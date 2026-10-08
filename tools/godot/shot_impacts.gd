extends SceneTree
## Pictures of the impact marks and bursts (needs a display):
##   xvfb-run -a /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_impacts.gd -- <dir>
## WorldSystems.tscn's real ParticleManager and DecalManager on a concrete floor and wall beside a 1.65 m figure:
## bullet holes on stone / metal / wood, a slash, a scorch, then a blood burst and a dust burst caught mid-flight.

const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"
var out := "user://shot_impacts"

func _tick(n: int) -> void:
	for i in range(n):
		await process_frame

func _snap(name: String) -> void:
	RenderingServer.force_draw()
	await process_frame
	root.get_texture().get_image().save_png(out + "/" + name + ".png")
	print("saved ", out + "/" + name + ".png")

func _box(size: Vector3, at: Vector3, col: Color) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = size
	b.add_child(cs)
	var m := MeshInstance3D.new()
	m.mesh = BoxMesh.new()
	(m.mesh as BoxMesh).size = size
	var mat := StandardMaterial3D.new()
	mat.albedo_color = col
	m.material_override = mat
	b.add_child(m)
	b.position = at
	current_scene.add_child(b)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		out = args[0]
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1600, 900)
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.55, 0.65, 0.75)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.6)
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	world.add_child(sun)
	_box(Vector3(40, 1, 40), Vector3(0, -0.5, 0), Color(0.62, 0.6, 0.57))
	_box(Vector3(10, 4, 0.4), Vector3(0, 2, -3), Color(0.7, 0.68, 0.64))
	var fig := MeshInstance3D.new()
	fig.mesh = CapsuleMesh.new()
	(fig.mesh as CapsuleMesh).height = 1.65
	(fig.mesh as CapsuleMesh).radius = 0.22
	fig.position = Vector3(-3.5, 0.825, -2)
	world.add_child(fig)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	for c in sys.get_children():
		if c.name in ["MenuManager", "HUDManager"]:
			c.free()
	world.add_child(sys)
	await _tick(5)
	var dm: Node = sys.get_node("DecalManager")
	var pm: Node = sys.get_node("ParticleManager")
	var n := Vector3(0, 0, 1)
	var x := -2.4
	for surf in ["STONE", "METAL", "WOOD"]:
		for k in 3:
			dm.call("mark_now", Vector3(x + k * 0.18, 1.4 + k * 0.12, -2.8), n, "HOLE", surf, 0.0)
		x += 0.9
	dm.call("mark_now", Vector3(0.6, 1.3, -2.8), n, "SLASH", "STONE", 0.0)
	dm.call("mark_now", Vector3(2.2, 0.0, -0.5), Vector3.UP, "SCORCH", "DEFAULT", 3.0)
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.position = Vector3(0, 1.6, 3.2)
	cam.look_at(Vector3(0, 1.0, -2.5))
	cam.current = true
	await _tick(10)
	await _snap("marks")
	Engine.time_scale = 0.08     # a software renderer under xvfb is slow: slow the burst so the picture catches it
	pm.call("burst_now", "FLESH", Vector3(-1.0, 1.3, -2.0), Vector3(0, 0.2, 1).normalized())
	pm.call("burst_now", "DEFAULT", Vector3(1.0, 1.3, -2.78), Vector3(0, 0, 1))
	await _tick(4)
	await _snap("bursts_early")
	await _tick(8)
	await _snap("bursts_late")
	cam.position = Vector3(-1.0, 1.4, -0.6)
	cam.look_at(Vector3(-1.0, 1.25, -2.2))
	pm.call("burst_now", "FLESH", Vector3(-1.0, 1.3, -2.0), Vector3(0, 0.2, 1).normalized())
	await _tick(5)
	await _snap("blood_close")
	quit()
