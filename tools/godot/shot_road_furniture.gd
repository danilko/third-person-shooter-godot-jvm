extends SceneTree
## shot_road_furniture.gd -- render a Road Kit piece's decals and street furniture (needs a DISPLAY; no --headless).
## PLAN.md 3.6c's picture gate: the arrows point the way the lane goes, the stop line and zebra sit on the approach,
## and the kit props stand where `point_furniture.py` put them, wearing the kit's own materials.
##
##   godot --path . --script tools/godot/shot_road_furniture.gd -- <out_dir> [--piece=<res .tscn>] [--per=2]
##
## For each MultiMesh the bake made (`MM_<piece>`), `--per` of its instances are framed from behind and above along
## the instance's own forward (-Z), so an arrow reads tip-up in the picture when it points the way traffic runs.
## Writes <out_dir>/<piece>_<asset>_<n>.png and prints each instance's position.

const DEFAULT_PIECE := "res://src/main/resources/com/openworld/world/pieces/Roads_DebugRoads_debug_a.tscn"

var _out := ""
var _piece := DEFAULT_PIECE
var _per := 2


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if args.size() > 0 and not args[0].begins_with("--") else "user://furniture_shots"
	for a in args:
		if a.begins_with("--piece="):
			_piece = a.substr(8)
		elif a.begins_with("--per="):
			_per = int(a.substr(6))
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = Vector2i(1280, 800)
	_run.call_deferred()


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
	var cam := Camera3D.new()
	cam.fov = 60
	root.add_child(cam)
	cam.make_current()
	var stem := _piece.get_file().get_basename()
	var mms := piece.find_children("MM_*", "MultiMeshInstance3D", true, false)
	print("multimeshes: ", mms.size())
	for mmi in mms:
		var mm: MultiMesh = mmi.multimesh
		print("  %s  %d instances" % [mmi.name, mm.instance_count])
		var step: int = max(1, mm.instance_count / max(1, _per))
		var n := 0
		for i in range(0, mm.instance_count, step):
			if n >= _per:
				break
			var t: Transform3D = mmi.global_transform * mm.get_instance_transform(i)
			var fwd := -t.basis.z
			fwd.y = 0.0
			fwd = fwd.normalized()
			var small: bool = mm.mesh.get_aabb().size.length() < 1.5
			var back := 4.0 if small else 9.0
			var up := 2.5 if small else 6.0
			cam.global_position = t.origin - fwd * back + Vector3(0, up, 0)
			cam.look_at(t.origin + fwd * (1.0 if small else 3.0), Vector3.UP)
			for f in 8:
				await process_frame
			# an unfocused window may not redraw on its own: draw now, or every shot is the first frame again
			RenderingServer.force_draw(false)
			var path := "%s/%s_%s_%d.png" % [_out, stem, String(mmi.name).trim_prefix("MM_"), n]
			root.get_texture().get_image().save_png(path)
			print("    saved %s at %s" % [path, t.origin])
			n += 1
	quit()
