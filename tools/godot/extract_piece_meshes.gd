extends SceneTree
## One kit piece -> one ArrayMesh resource a MultiMesh can draw (PLAN.md T5: the kerb-zone scatter).
##   godot --headless --path . --script tools/godot/extract_piece_meshes.gd -- <out res dir> <piece.gltf res path>...
## Every MeshInstance3D of the piece is merged, its node transform baked in, one surface per material; saved as
## <out>/<Piece>.res. Re-run after the piece changes in its .blend (tools/building_kit/build_buildings.sh does).

var materials_dir := ""

func _collect(n: Node, xf: Transform3D, tools: Dictionary, order: Array) -> void:
	var here := xf
	if n is Node3D:
		here = xf * (n as Node3D).transform
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var mi := n as MeshInstance3D
		for s in mi.mesh.get_surface_count():
			var mat: Material = mi.get_surface_override_material(s)
			if mat == null:
				mat = mi.mesh.surface_get_material(s)
			# a library piece's glTF carries a flat placeholder colour per material NAME; the look is the kit's
			# materials/<name>.tres (the building scenes' rule, build_building_scenes._kit_material)
			if mat != null and mat.resource_name != "":
				var lib := "%s/%s.tres" % [materials_dir, mat.resource_name.split(".")[0]]
				if ResourceLoader.exists(lib):
					mat = load(lib)
			var key := mat.resource_path if mat != null and mat.resource_path != "" else "<%d>" % order.size()
			if not tools.has(key):
				var st := SurfaceTool.new()
				tools[key] = [st, mat]
				order.append(key)
			(tools[key][0] as SurfaceTool).append_from(mi.mesh, s, here)
	for c in n.get_children():
		_collect(c, here, tools, order)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		print("usage: -- <out res dir> <piece res path>...")
		quit(2)
		return
	var out_dir: String = args[0]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_dir))
	var fails := 0
	for i in range(1, args.size()):
		var ps: PackedScene = load(args[i])
		if ps == null:
			print("FAIL cannot load %s" % args[i])
			fails += 1
			continue
		# <kit>/pieces/<category>/<Piece>.gltf -> <kit>/materials
		materials_dir = args[i].get_base_dir().get_base_dir().get_base_dir() + "/materials"
		var root := ps.instantiate()
		var tools := {}
		var order := []
		_collect(root, Transform3D.IDENTITY, tools, order)
		root.free()
		var mesh := ArrayMesh.new()
		for key in order:
			(tools[key][0] as SurfaceTool).commit(mesh)
			mesh.surface_set_material(mesh.get_surface_count() - 1, tools[key][1])
		var path := "%s/%s.res" % [out_dir, args[i].get_file().get_basename()]
		var err := ResourceSaver.save(mesh, path)
		print("%s %s: %d surface(s), aabb %s" % ["OK  " if err == OK else "FAIL", path, mesh.get_surface_count(), mesh.get_aabb().size])
		if err != OK or mesh.get_surface_count() == 0:
			fails += 1
	quit(1 if fails > 0 else 0)
