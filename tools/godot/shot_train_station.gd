extends SceneTree
## Pictures of EMU1 (blender/tools/make_train.py) standing at a station's platforms: a 4-car set on every track, seen
## from the platform end, from above the tracks, and straight down. NEEDS A DISPLAY (`xvfb-run -a`).
##
##   godot --path . --script tools/godot/shot_train_station.gd -- --scene=res://.../Station_Farm_Shop.tscn --out=/tmp/x

const TRAIN := "res://assets/vehicles/trains/EMU1.train.json"
const TRACK_HALF := 2.0
const RAIL_H := 0.16

func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % k):
			return a.substr(k.length() + 3)
	return d

func _initialize() -> void:
	_run()

func _run() -> void:
	var out := _arg("out", "/tmp/train_shots")
	DirAccess.make_dir_recursive_absolute(out)
	var train: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(TRAIN))
	var w := Node3D.new()
	root.add_child(w)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.72, 0.84)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.7, 0.7, 0.7)
	w.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	w.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	ground.mesh = pm
	w.add_child(ground)
	var sc: Node3D = (load(_arg("scene", "")) as PackedScene).instantiate()
	w.add_child(sc)
	var st: Dictionary = sc.get_meta("building")["station"]
	var coupled := float(train["coupled_length_m"])
	var tc := load("res://assets/vehicles/trains/EMU1_Tc.glb") as PackedScene
	var mc := load("res://assets/vehicles/trains/EMU1_M.glb") as PackedScene
	# only the FIRST lane's two tracks get a train (the other stays open, to see the gap)
	var ln: Array = st["lanes"][0]
	for tsg in [-1.0, 1.0]:
		var tz: float = -(float(ln[1]) + tsg * TRACK_HALF)
		for k in 4:
			var car: Node3D = (tc if k == 0 or k == 3 else mc).instantiate()
			w.add_child(car)
			var yaw := -PI / 2.0 if k != 0 else PI / 2.0
			car.transform = Transform3D(Basis(Vector3.UP, yaw), Vector3((float(k) - 1.5) * coupled, RAIL_H, tz))
	var half := float(st["length"]) / 2.0
	var tz0 := -float(ln[1])
	var cam := Camera3D.new()
	w.add_child(cam)
	cam.current = true
	var views := {
		"platform_end": [Vector3(half + 6.0, 2.9, tz0 + 6.0), Vector3(-half, 1.5, tz0)],
		"along_tracks": [Vector3(half + 30.0, 7.0, tz0), Vector3(0.0, 1.5, tz0)],
		"top": [Vector3(half - 10.0, 25.0, tz0 + 0.01), Vector3(half - 10.0, 0.0, tz0)],
		"door_gap": [Vector3(0.0, 2.2, tz0 + 6.5), Vector3(0.0, 1.2, tz0 + 2.0)],
	}
	for n in views:
		var v: Array = views[n]
		cam.global_position = v[0]
		cam.look_at(v[1], Vector3.UP if n != "top" else Vector3(1, 0, 0))
		for i in 8:
			await process_frame
		RenderingServer.force_draw()
		root.get_texture().get_image().save_png("%s/%s_%s.png" % [out, str(st["name"]).replace(" ", ""), n])
		print("shot_train_station: %s" % n)
	quit(0)
