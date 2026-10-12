extends SceneTree
## Draw calls with and without poles / guardrails / wires, standing still at four sites, in ONE process (PLAN S9 Q2):
##   <godot> --path . --script tools/godot/measure_furniture_draws.gd      (NEEDS A DISPLAY; prints STATIC lines)
## 2026-10-12: downtown 67-81 of ~3 600 draws (2 %), nightlife ~120 of 4 080 (3 %), residential 134-239 of ~2 350 (6-10 %).
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const SITES := [["downtown_core", Vector3(760, 0, -70)], ["nightlife", Vector3(750, 0, -370)], ["residential", Vector3(-975, 0, 680)], ["suburb", Vector3(1085, 0, 665)]]
var hidden := []
var wires := []

func _info(k: int) -> int:
	return RenderingServer.viewport_get_render_info(root.get_viewport_rid(), RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, k)

func _measure(frames: int) -> Array:
	var d := 0.0
	var g := 0.0
	var t := 0.0
	for i in frames:
		await process_frame
		d += _info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME)
		t += _info(RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME)
		g += RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid())
	return [d / frames, g / frames, t / frames]

func _set_furniture(w: Node, on: bool) -> void:
	if not on:
		hidden.clear(); wires.clear()
		for n in w.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
			var nm := String(n.name)
			if (nm.begins_with("Breakable_Pole_Denchu") or nm.begins_with("Breakable_Guardrail_JP")) and n.visible:
				n.visible = false
				hidden.append(n)
		for n in w.find_children("*", "MeshInstance3D", true, false):
			var m := (n as MeshInstance3D).mesh as ArrayMesh
			if m == null:
				continue
			for i in m.get_surface_count():
				var mat := m.surface_get_material(i)
				if mat != null and mat.resource_path.ends_with("M_Wire.tres") and n.get_surface_override_material(i) == null:
					# a surface cannot be hidden: give it a material that is culled both ways is not possible either,
					# so the mesh instance gets a copy of the mesh without the wire surface
					wires.append([n, m])
		for pair in wires:
			var src: ArrayMesh = pair[1]
			var cp := ArrayMesh.new()
			for i in src.get_surface_count():
				var mat := src.surface_get_material(i)
				if mat != null and mat.resource_path.ends_with("M_Wire.tres"):
					continue
				cp.add_surface_from_arrays(src.surface_get_primitive_type(i), src.surface_get_arrays(i))
				cp.surface_set_material(cp.get_surface_count() - 1, mat)
			(pair[0] as MeshInstance3D).mesh = cp
	else:
		for n in hidden:
			if is_instance_valid(n):
				n.visible = true
		for pair in wires:
			if is_instance_valid(pair[0]):
				(pair[0] as MeshInstance3D).mesh = pair[1]

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	await process_frame
	DisplayServer.window_set_size(Vector2i(1280, 800))
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	var w: Node = (load(WORLD) as PackedScene).instantiate()
	var tod := w.get_node_or_null("Sky3D/TimeOfDay")
	if tod != null:
		tod.set("game_time_enabled", false)
		tod.set("current_time", 12.0)
	root.add_child(w)
	current_scene = w
	var zm := root.get_node("/root/ZoneManager")
	zm.set("debug_log", false)
	var p := w.get_node("Characters/Player") as CharacterBody3D
	p.get_node("Health").set("invulnerable", true)
	p.set_physics_process(false)
	var wb := w.find_child("WorldBounds", true, false)
	for site in SITES:
		var at: Vector3 = site[1]
		p.global_position = at + Vector3(0, 30, 0)
		var waited := 0
		while waited < 60 * 120:
			await physics_frame
			waited += 1
			if waited > 300 and int(zm.call("streaming_pending_now")) == 0:
				break
		# onto the nearest car's street, as the census does
		var best := at
		var bd := 300.0
		for n in get_nodes_in_group("characters"):
			if n is RigidBody3D:
				var d: Vector3 = n.global_position - at
				d.y = 0
				if d.length() < bd:
					bd = d.length(); best = n.global_position
		p.global_position = best + Vector3(0, 1.2, 0)
		for i in 240:
			await physics_frame
		for yaw in [0.0, 90.0]:
			var vph := load("res://tools/godot/VehicleProbeHelper.gd") if ResourceLoader.exists("res://tools/godot/VehicleProbeHelper.gd") else null
			p.rotation_degrees.y = yaw
			if p.has_method("set_control_yaw_now"):
				p.call("set_control_yaw_now", yaw)
			for i in 60:
				await process_frame
			var a: Array = await _measure(90)
			_set_furniture(w, false)
			for i in 20:
				await process_frame
			var b: Array = await _measure(90)
			_set_furniture(w, true)
			for i in 20:
				await process_frame
			var a2: Array = await _measure(90)
			print("STATIC %-14s yaw %3d: draws with %.0f / without %.0f / with again %.0f  (furniture %.0f = %.1f %%); gpu ms %.2f / %.2f / %.2f; tris %.0fk / %.0fk; hid %d batches, %d wire meshes" % [
				site[0], int(yaw), a[0], b[0], a2[0], (a[0] + a2[0]) * 0.5 - b[0], 100.0 * ((a[0] + a2[0]) * 0.5 - b[0]) / maxf(1.0, (a[0] + a2[0]) * 0.5),
				a[1], b[1], a2[1], a[2] / 1000.0, b[2] / 1000.0, hidden.size(), wires.size()])
	print("RESULT DONE")
	quit()
