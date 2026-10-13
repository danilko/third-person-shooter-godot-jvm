extends SceneTree
## INTERIOR LIGHTING, MEASURED (PLAN.md L1; user, 2026-10-11: "stores such as the konbini have room light meshes, but
## no actual light on ... do a performance test and suggest"). One process, one interior at a time, the same two
## cameras (standing inside; on the street looking at the front), day and night, and per variant the draw calls and
## the GPU's own frame time, plus a picture of each:
##   <godot> --path . --script tools/godot/measure_interior_light.gd -- [--out=<dir>] [--scenes=KonbiniL,Hospital]
##   (NEEDS A DISPLAY; prints LIGHT lines; a measurement, exits 0)
## control   as shipped: the ceiling panels are emissive meshes and light nothing
## omni N    an OmniLight3D (no shadow) at each of the N ceiling panels nearest the camera (--cap, default 12)
## omni 4    the same capped at 4
## fill      no light node: the environment's ambient raised while "inside" (what a per-interior ambient would do)
## The interior stands ALONE (no city round it), so the times are the cost of the interior and its lights, not a
## frame of the game: read the DIFFERENCES between variants.
const DIR := "res://src/main/resources/com/openworld/world/buildings/"
var args := {}

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=")
		args[kv[0]] = kv[1] if kv.size() > 1 else true
	_run.call_deferred()

func _info(k: int) -> int:
	return RenderingServer.viewport_get_render_info(root.get_viewport_rid(), RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, k)

func _measure(frames: int) -> Array:
	var d := 0.0
	var g := 0.0
	for i in 20:
		await process_frame
	for i in frames:
		await process_frame
		d += _info(RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME)
		g += RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid())
	return [d / frames, g / frames]

## The ceiling panels: the vertices of every MI_Light surface above 2 m, gathered on a 1.2 m grid.
func _panels(node: Node3D) -> Array:
	var cells := {}
	for n in node.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		var m := mi.mesh as ArrayMesh
		if m == null:
			continue
		for s in m.get_surface_count():
			var mat := m.surface_get_material(s)
			if args.has("materials"):
				print("  surface %d: %s" % [s, mat.resource_path if mat != null else "<none>"])
			if mat == null or not mat.resource_path.get_file().begins_with("MI_Light"):
				continue
			var verts: PackedVector3Array = m.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]
			for v in verts:
				var w: Vector3 = mi.global_transform * v
				if w.y < 2.0:
					continue
				var key := Vector3i(roundi(w.x / 1.2), roundi(w.y / 1.2), roundi(w.z / 1.2))
				if not cells.has(key):
					cells[key] = [Vector3.ZERO, 0]
				cells[key][0] += w
				cells[key][1] += 1
	var out := []
	for k in cells:
		out.append(cells[k][0] / float(cells[k][1]))
	return out

func _bounds(node: Node3D) -> AABB:
	var box := AABB()
	var first := true
	for n in node.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		var b := mi.global_transform * mi.mesh.get_aabb()
		box = b if first else box.merge(b)
		first = false
	return box

func _run() -> void:
	var out_dir := str(args.get("out", "user://interior_light"))
	DirAccess.make_dir_recursive_absolute(out_dir)
	var cap := int(args.get("cap", "12"))
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = Sky.new()
	env.sky.sky_material = ProceduralSkyMaterial.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.shadow_enabled = true
	root.add_child(sun)
	var cam := Camera3D.new()
	cam.fov = 70.0
	root.add_child(cam)
	cam.make_current()
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	for name in str(args.get("scenes", "KonbiniL,Hospital")).split(","):
		var ps: PackedScene = load(DIR + name + "_Shop.tscn")
		if ps == null:
			print("LIGHT %s: no _Shop scene" % name)
			continue
		var holder := Node3D.new()
		root.add_child(holder)
		var shop: Node3D = ps.instantiate()
		holder.add_child(shop)
		await process_frame
		var panels := _panels(shop)
		var box := _bounds(shop)
		var grid := false
		if panels.size() < 4:
			# no ceiling panel in the light material (the konbini's are shelf and fridge strips under 2 m): a light
			# every 4.5 m under a 2.8 m ceiling, which is what its panels would be
			grid = true
			panels.clear()
			var gx := box.position.x + 2.25
			while gx < box.end.x:
				var gz := box.position.z + 2.25
				while gz < box.end.z:
					panels.append(Vector3(gx, box.position.y + 2.85, gz))
					gz += 4.5
				gx += 4.5
		var c := box.get_center()
		var along := Vector3(1, 0, 0) if box.size.x >= box.size.z else Vector3(0, 0, 1)
		var inside_at := Vector3(c.x, box.position.y + 1.6, c.z) - along * (maxf(box.size.x, box.size.z) * 0.3)
		var views := [["inside", inside_at, inside_at + along], ["street", Vector3(c.x, 1.6, box.end.z + 14.0), Vector3(c.x, 1.6, c.z)]]
		print("LIGHT %s: %d ceiling %s, interior %.1f x %.1f x %.1f m" % [name, panels.size(), "points on a 4.5 m grid" if grid else "panels", box.size.x, box.size.y, box.size.z])
		for night in [false, true]:
			sun.visible = not night
			env.ambient_light_energy = 0.12 if night else 1.0
			env.background_energy_multiplier = 0.05 if night else 1.0
			for view in views:
				cam.look_at_from_position(view[1], view[2], Vector3.UP)
				var base := []
				for variant in ["control", "omni %d" % cap, "omni 4", "fill"]:
					var lights := []
					var n_lights := 0
					if variant.begins_with("omni"):
						n_lights = int(variant.split(" ")[1])
						var sorted := panels.duplicate()
						sorted.sort_custom(func(a, b): return a.distance_squared_to(cam.global_position) < b.distance_squared_to(cam.global_position))
						for p in sorted.slice(0, n_lights):
							var l := OmniLight3D.new()
							l.omni_range = 7.0
							l.light_energy = 1.2
							l.light_color = Color(1.0, 0.97, 0.9)
							l.shadow_enabled = false
							holder.add_child(l)
							l.global_position = p - Vector3(0, 0.25, 0)
							lights.append(l)
					var amb := env.ambient_light_energy
					var src := env.ambient_light_source
					if variant == "fill":
						env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
						env.ambient_light_color = Color(1.0, 0.97, 0.92)
						env.ambient_light_energy = 0.9
					var r := await _measure(240)
					if variant == "control":
						base = r
					print("LIGHT %-10s %-5s %-6s %-8s lights %2d  draws %6.0f  gpu %6.3f ms  (%+.3f ms, %+.0f draws)" % [
						name, "night" if night else "day", view[0], variant, lights.size(), r[0], r[1], r[1] - base[1], r[0] - base[0]])
					await RenderingServer.frame_post_draw
					root.get_viewport().get_texture().get_image().save_png("%s/%s_%s_%s_%s.png" % [
						out_dir, name, "night" if night else "day", view[0], variant.replace(" ", "")])
					env.ambient_light_energy = amb
					env.ambient_light_source = src
					for l in lights:
						l.queue_free()
		holder.queue_free()
		await process_frame
	quit(0)
