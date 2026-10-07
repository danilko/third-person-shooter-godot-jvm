extends SceneTree
## DOES THE HELD GUN COVER THE CROSSHAIR? (user 2026-10-07: "all pistols' grip seems too low, the gun blocks the
## crosshair"). A real Player armed with each weapon through the ordinary equip path, aim held, in third person and in
## first person: saves a frame per case, a red cross marking the screen centre (where the crosshair is). Judge the
## pictures: a numeric box from the meshes' AABBs was tried and read the gun's transform before its bone attachment
## updated, so it disagreed with what was drawn.
## Runs WITH a display.
##
##   <godot> --path . --script tools/godot/shot_pistol_sight.gd -- [--weapons=PIS1,PIS2,DUP1,REV1] [--out=<dir>]

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
	var out := _arg("out", "/tmp/pistol_sight")
	var ids := _arg("weapons", "PIS1,PIS2,DUP1,REV1").split(",")
	if out != "":
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
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.62)
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
	for id in ids:
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
		for fps in [false, true]:
			p.set("is_fps_mode", fps)
			Input.action_press("aim")
			await _tick(90)
			await RenderingServer.frame_post_draw
			print("%s %s: saved" % [id, "FPS" if fps else "TPS"])
			if out != "":
				var img := root.get_viewport().get_texture().get_image()
				for d in range(-12, 13):
					img.set_pixel(960 + d, 540, Color.RED)
					img.set_pixel(960, 540 + d, Color.RED)
				img.save_png(out.path_join("%s_%s.png" % [id, "fps" if fps else "tps"]))
			Input.action_release("aim")
			await _tick(10)
		p.queue_free()
		gun.queue_free()
		await _tick(10)
	quit(0)
