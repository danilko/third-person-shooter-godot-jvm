extends SceneTree
## shot_road_surface.gd -- render a Road Kit piece up close (needs a DISPLAY; no --headless). PLAN.md 3.6c's gate.
##
##   godot --path . --script tools/godot/shot_road_surface.gd -- <out_dir> [--piece=<res path .tscn>] [--flat]
##
## The piece at its baked frame (a Road Kit piece is written in its network's frame), a daylight sky and sun, and
## cameras at driver height and above a few lane samples read from the piece's own PathLaneRoutes. `--flat` swaps
## every library material back to a flat colour of the same name (the control: what the pieces looked like before
## the material library). Writes <out_dir>/<piece>_<n>.png.

const DEFAULT_PIECE := "res://src/main/resources/com/openworld/world/pieces/Roads_DebugRoads_debug_a.tscn"

var _out := ""
var _piece := DEFAULT_PIECE
var _flat := false


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if args.size() > 0 and not args[0].begins_with("--") else "user://road_shots"
	for a in args:
		if a.begins_with("--piece="):
			_piece = a.substr(8)
		elif a == "--flat":
			_flat = true
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = Vector2i(1600, 900)
	_run.call_deferred()


func _flatten(n: Node) -> int:
	var count := 0
	if n is MeshInstance3D and n.mesh:
		for s in n.mesh.get_surface_count():
			var m: Material = n.mesh.surface_get_material(s)
			if m is StandardMaterial3D and m.uv1_world_triplanar:
				var f := StandardMaterial3D.new()
				f.albedo_color = {"M_Asphalt": Color(0.28, 0.3, 0.33)}.get(m.resource_name, Color(0.82, 0.8, 0.76))
				n.set_surface_override_material(s, f)
				count += 1
	for c in n.get_children():
		count += _flatten(c)
	return count


func _run() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	e.sky = Sky.new()
	e.sky.sky_material = ProceduralSkyMaterial.new()
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.environment = e
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -35, 0)
	sun.shadow_enabled = true
	root.add_child(sun)
	var piece: Node3D = load(_piece).instantiate()
	root.add_child(piece)
	if _flat:
		print("flattened ", _flatten(piece), " surfaces")
	var lanes := []
	for n in piece.find_children("*", "Path3D", true, false):
		if n.curve and n.curve.get_baked_length() > 40.0:
			lanes.append(n)
	var cam := Camera3D.new()
	cam.fov = 70
	root.add_child(cam)
	cam.make_current()
	var stem := _piece.get_file().get_basename()
	var shots := 0
	for i in range(0, lanes.size(), max(1, lanes.size() / 3)):
		var lane: Path3D = lanes[i]
		var c := lane.curve
		var p := lane.to_global(c.sample_baked(10.0))
		var q := lane.to_global(c.sample_baked(30.0))
		for view in [["driver", Vector3(0, 1.4, 0), q + Vector3(0, 0.3, 0)], ["above", Vector3(0, 9.0, 0), q]]:
			cam.global_position = p + view[1]
			cam.look_at(view[2], Vector3.UP)
			for f in 8:
				await process_frame
			var img := root.get_texture().get_image()
			var path := "%s/%s_%s%d_%s.png" % [_out, stem, "flat_" if _flat else "", shots, view[0]]
			img.save_png(path)
			print("saved ", path)
		shots += 1
		if shots >= 3:
			break
	quit()
