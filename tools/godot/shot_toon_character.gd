extends SceneTree
## Before/after of the character toon look (PLAN.md 6.10). NEEDS A DISPLAY (xvfb-run -a).
##
##   xvfb-run -a godot --path . --script tools/godot/shot_toon_character.gd -- --out=<dir> [--visuals=<tscn>]
##
## Two identical stands side by side in one frame, lit by one sun with a sky ambient: LEFT the imported
## materials, RIGHT `toon_look = true`. Saves <dir>/toon_front.png and <dir>/toon_side.png (the sun from
## the side, where the shade band shows). A probe owns its own Camera3D: the Player's rig keeps writing the
## current camera otherwise (probe_night_lights' trap).

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

func _initialize() -> void:
	var out := "user://"
	var visuals := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			out = a.substr(6)
		elif a.begins_with("--visuals="):
			visuals = a.substr(10)
	var world := Node3D.new()
	root.add_child(world)
	await process_frame
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.55, 0.68, 0.85)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.55, 0.6, 0.7)
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	world.add_child(we)
	var floor := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(20, 20)
	floor.mesh = pm
	world.add_child(floor)
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var bx := BoxShape3D.new()
	bx.size = Vector3(20, 1, 20)
	cs.shape = bx
	body.add_child(cs)
	body.position = Vector3(0, -0.5, 0)
	world.add_child(body)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	world.add_child(sun)
	var converted := []
	for i in range(2):
		var c: Node3D = (load(AI) as PackedScene).instantiate()
		if visuals != "":
			c.set("character_visuals", load(visuals))
		c.set("toon_look", i == 1)
		world.add_child(c)
		c.global_position = Vector3(-0.6 + 1.2 * i, 0.05, 0)
	await process_frame
	for c in world.get_children():
		if c.get("toon_look") != null:
			c.process_mode = Node.PROCESS_MODE_DISABLED       # stand still: no brain, no walking
			var tl: Node = c.get_node_or_null("ToonLook")
			converted.append(0 if tl == null else int(tl.call("surfaces_converted_now")))
	print("TOON surfaces converted: plain %d, toon %d" % [converted[0], converted[1]])
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.current = true
	cam.fov = 35
	for shot in [["toon_front.png", Vector3(0.4, -0.6, -1.0)], ["toon_side.png", Vector3(1.0, -0.5, 0.15)]]:
		sun.look_at_from_position(Vector3.ZERO - (shot[1] as Vector3).normalized() * 10.0, Vector3.ZERO, Vector3.UP)
		cam.look_at_from_position(Vector3(0, 1.2, 4.2), Vector3(0, 0.95, 0), Vector3.UP)
		for f in range(10):
			await process_frame
		RenderingServer.force_draw()
		await process_frame
		var img := root.get_texture().get_image()
		img.save_png(out.path_join(shot[0]))
		print("TOON saved " + out.path_join(shot[0]))
	quit(0)
