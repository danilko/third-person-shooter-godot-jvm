extends SceneTree
func _initialize():
	var out: String = OS.get_cmdline_user_args()[0]
	root.size = Vector2i(1280, 720)
	var env := WorldEnvironment.new(); env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR; env.environment.background_color = Color(0.55,0.65,0.75)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; env.environment.ambient_light_color = Color(0.7,0.7,0.7)
	root.add_child(env)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-50, 30, 0); root.add_child(sun)
	var floor := MeshInstance3D.new(); floor.mesh = PlaneMesh.new(); (floor.mesh as PlaneMesh).size = Vector2(2000, 2000); root.add_child(floor)
	var cam := Camera3D.new(); root.add_child(cam); cam.current = true
	for sc in [1.0, 0.5]:
		var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/Vehicle.tscn").instantiate()
		root.add_child(car); car.global_position = Vector3(0, 0.6, 0); car.freeze = true
		for i in 3: await process_frame
		car.get_node("DamageVfx/Smoke").scale = Vector3.ONE * sc
		car.get_node("Health").call("apply_replicated_health", float(car.get_node("Health").get("max_health")) * 0.5)
		for i in 180:
			car.global_position += Vector3(0, 0, -16.0 / 60.0)
			cam.global_position = car.global_position + Vector3(0, 2.6, 6.5); cam.look_at(car.global_position + Vector3(0, 0.4, -2))
			await process_frame
		RenderingServer.force_draw(); await process_frame
		root.get_viewport().get_texture().get_image().save_png("%s/moving_%.2f.png" % [out, sc])
		car.queue_free()
		for i in 3: await process_frame
	quit()
