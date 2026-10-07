extends SceneTree
## The character beside the enforcement vehicles, side on, one picture (user 2026-10-07: "the helicopter / tank look
## much smaller than real"). NEEDS A DISPLAY (xvfb-run is fine):
##
##   xvfb-run -a <godot> --path . --script tools/godot/shot_vehicle_scale.gd -- --out=<png>
##
## Every scene is the shipped one at its real size; a 1 m pole stands beside the character for scale.

const V := "res://src/main/resources/com/openworld/vehicle/"
const BODY := "res://assets/characters/shino/shino.tscn"

func _initialize() -> void:
	var out := "/tmp/vehicle_scale.png"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			out = a.substr(6)
	var w := Node3D.new()
	root.add_child(w)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.75, 0.8, 0.85)
	env.environment.ambient_light_color = Color(1, 1, 1)
	env.environment.ambient_light_energy = 0.8
	w.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	w.add_child(sun)
	var x := 0.0
	for id in ["HLC1", "TNK1", "LTK1", "ARV1", "POC1"]:
		var c: Node3D = (load(V + id + ".tscn") as PackedScene).instantiate()
		c.process_mode = Node.PROCESS_MODE_DISABLED
		w.add_child(c)
		var half := 8.5 if id == "HLC1" else 6.5 if id in ["TNK1", "LTK1"] else 4.0
		x += half
		c.global_position = Vector3(x, 1.0 if id != "HLC1" else 1.9, 0)
		c.rotation_degrees = Vector3(0, 90, 0)
		x += half + 2.0
		var b: Node3D = (load(BODY) as PackedScene).instantiate()
		w.add_child(b)
		b.global_position = Vector3(x - 1.0, 0, 3.0)
		var ap := b.find_child("AnimationPlayer", true, false) as AnimationPlayer
		if ap and ap.has_animation("upright_idle"):
			ap.play("upright_idle")
		x += 1.5
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 60)
	ground.mesh = pm
	w.add_child(ground)
	var cam := Camera3D.new()
	w.add_child(cam)
	cam.global_position = Vector3(x * 0.5, 4.0, 48.0)
	cam.look_at(Vector3(x * 0.5, 2.5, 0))
	cam.fov = 45
	cam.current = true
	root.size = Vector2i(1920, 600)
	for i in 30:
		await process_frame
	RenderingServer.force_draw()
	await process_frame
	root.get_texture().get_image().save_png(out)
	print("SAVED ", out)
	quit()
