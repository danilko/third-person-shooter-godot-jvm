extends SceneTree
## Pictures of an ELEVATED station's F1 (needs a DISPLAY: `xvfb-run -a <godot> --path . --script
## tools/godot/shot_station_hall.gd -- <out_dir> [--scene=<Station_X_Shop.tscn>]`): the paid box with gate banks on its
## four sides, the unpaid wings and end halls round it, the lowered ceiling. Writes <out_dir>/hall_<view>.png:
##   wing    in a wing by a corner gate bank, looking into the box;
##   end     in an end hall, looking along the axis at the end fare line and the box beyond;
##   box     inside the box, looking at the stair's foot and a side gate bank;
##   street  outside an entrance, the building's long face;
##   wc_paid / wc_unpaid  in front of each restroom block's doors;
##   wc_in_men / wc_in_women / wc_in_acc  inside the paid block's three rooms (the library fixtures).

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/buildings/Station_Suburb_Shop.tscn"

func _initialize() -> void:
	_run.call_deferred()

func _frames(n: int) -> void:
	for i in range(n):
		await process_frame

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var out := args[0]
	var scene := DEFAULT_SCENE
	for a in args:
		if a.begins_with("--scene="):
			scene = a.substr(8)
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1280, 800)
	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.62, 0.72, 0.82)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.85, 0.85, 0.85)
	e.ambient_light_energy = 0.9
	env.environment = e
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.shadow_enabled = true
	world.add_child(sun)
	var st: Node3D = (load(scene) as PackedScene).instantiate()
	world.add_child(st)
	var m: Dictionary = st.get_meta("building")["station"]
	var f1 := float(m["street"])
	var box: Array = m["paid_box"]
	var wo := float(m["outer"])
	var rw: Array = m["rail_wall"]
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	ground.mesh = pm
	ground.position = Vector3(0, f1 - 0.02, 0)
	world.add_child(ground)
	var line := (float(rw[0]) + float(rw[1])) / 2.0
	var hi := float(box[1])
	var eye := f1 + 1.6
	var views := {
		"wing": [Vector3(hi + 4.0, eye, -(line + 3.0)), Vector3(hi - 5.0, f1 + 1.0, -(line - 3.0))],
		"end": [Vector3(hi + 14.0, eye, 2.0), Vector3(hi - 10.0, f1 + 1.4, 0.0)],
		"box": [Vector3(hi - 3.0, eye, -2.0), Vector3(hi - 10.0, f1 + 1.2, -(line + 2.0))],
		"street": [Vector3(float(m["length"]) / 2.0 - 7.5 + 10.0, f1 + 2.5, -(wo + 16.0)),
				Vector3(float(m["length"]) / 2.0 - 12.0, f1 + 3.0, -wo)],
	}
	for wc in m.get("restrooms", []):
		# in front of each restroom block's doors, looking at them (the doors face Godot +z)
		views["wc_" + str(wc[2])] = [Vector3(float(wc[0]) - 2.0, eye, float(wc[1]) + 3.0),
				Vector3(float(wc[0]), f1 + 1.4, float(wc[1]))]
		if str(wc[2]) == "paid":
			# INSIDE the block, from high up (the rooms are small and the entries turn behind screens): the men's
			# stall, urinals and basins; the women's stalls and basins; the accessible room's washlet, rail, basin
			var x0 := float(wc[0])
			var z0 := float(wc[1])
			views["wc_in_men"] = [Vector3(x0 - 1.6, f1 + 3.3, z0 - 0.5), Vector3(x0 - 3.6, f1 + 0.6, z0 - 3.5)]
			views["wc_in_women"] = [Vector3(x0 + 0.4, f1 + 3.3, z0 - 0.5), Vector3(x0 - 0.8, f1 + 0.6, z0 - 4.0)]
			views["wc_in_acc"] = [Vector3(x0 + 3.0, f1 + 3.0, z0 - 0.4), Vector3(x0 + 3.4, f1 + 0.6, z0 - 4.3)]
	var cam := Camera3D.new()
	cam.fov = 75
	world.add_child(cam)
	cam.current = true
	for k in views:
		cam.global_position = views[k][0]
		cam.look_at(views[k][1], Vector3.UP)
		await _frames(12)
		RenderingServer.force_draw()
		await _frames(3)
		root.get_texture().get_image().save_png("%s/hall_%s.png" % [out, k])
		print("  -> %s/hall_%s.png" % [out, k])
	quit(0)
