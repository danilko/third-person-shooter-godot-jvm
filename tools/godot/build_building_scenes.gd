extends SceneTree
## build_building_scenes.gd -- write one scene per building from a layout (tools/building_kit/layout_buildings.py).
##
##   godot --headless --path . --script tools/godot/build_building_scenes.gd -- <layout.json> [--only=Id,Id]
##
## For each building: every placed piece's surfaces are MERGED, one surface per material, into one ArrayMesh
## (`<Id>_mesh.res`), so a seven-storey building is one MeshInstance3D and ~8 draw calls, not 300 nodes. The
## layout's boxes become one StaticBody3D (world layer 1); a kit example gets a trimesh collider instead
## (`<Id>_collision.res`). Doors become Marker3D nodes facing out of the building, and the layout's facts are
## the root's `building` meta, which is what `probe_buildings.gd` checks.
##
## Materials have ONE copy per kit: `<kit>/materials/<name>.tres`, written from the imported glTF material the
## first time it is seen and NEVER overwritten, so a hand edit (a Japanese tile tint) survives every rebuild.
## Written with vertex colour OFF as albedo (see `_kit_material`).
## Nothing here decides where a piece goes: that is the layout's.

const OUT_DIR := "res://src/main/resources/com/openworld/world/buildings"

var _piece_cache := {}   # path -> Array of [Mesh, surface, Transform3D]
var _materials := {}     # "<kit>/<name>" -> Material


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: -- <layout.json> [--only=Id,Id]")
		quit(2)
		return
	var only := []
	for a in args:
		if a.begins_with("--only="):
			only = a.substr(7).split(",")
	var doc = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if doc == null:
		push_error("cannot read " + args[0])
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))
	var failed := 0
	for b in doc["buildings"]:
		if not only.is_empty() and not only.has(b["id"]):
			continue
		if not _build(b):
			failed += 1
	print("BUILD %s" % ("FAIL %d" % failed if failed else "OK"))
	quit(1 if failed else 0)


func _kit_res(piece_path: String) -> String:
	# res://assets/world_source/kits/<kit>/pieces/<cat>/<name>.gltf -> res://assets/world_source/kits/<kit>
	return piece_path.get_base_dir().get_base_dir().get_base_dir()


func _surfaces(path: String) -> Array:
	if _piece_cache.has(path):
		return _piece_cache[path]
	var ps: PackedScene = load(path)
	if ps == null:
		push_error("cannot load piece " + path)
		return []
	var root := ps.instantiate()
	var found := []
	_collect(root, Transform3D.IDENTITY, found)
	root.free()
	_piece_cache[path] = found
	return found


func _collect(n: Node, xf: Transform3D, found: Array) -> void:
	var here := xf
	if n is Node3D:
		here = xf * (n as Node3D).transform
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var mi := n as MeshInstance3D
		for s in mi.mesh.get_surface_count():
			var mat: Material = mi.get_surface_override_material(s)
			if mat == null:
				mat = mi.mesh.surface_get_material(s)
			found.append([mi.mesh, s, here, mat])
	for c in n.get_children():
		_collect(c, here, found)


func _kit_material(kit_res: String, mat: Material) -> Material:
	if mat == null:
		return null
	var name := mat.resource_name
	if name.is_empty():
		push_error("a piece surface has an unnamed material")
		return mat
	var key := kit_res + "/" + name
	if _materials.has(key):
		return _materials[key]
	var dir := kit_res + "/materials"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var path := dir + "/" + name + ".tres"
	if not ResourceLoader.exists(path):
		var copy := mat.duplicate()
		copy.resource_name = name
		# The kit's COLOR_0 is a wear/tint MASK for the Source version's shader, not a colour. The glTF importer
		# multiplies it into albedo, which turned MetalConcrete near-black and splashed red over the examples.
		if copy is BaseMaterial3D:
			(copy as BaseMaterial3D).vertex_color_use_as_albedo = false
		var err := ResourceSaver.save(copy, path)
		if err != OK:
			push_error("cannot save %s (%d)" % [path, err])
			return mat
		print("  material %s written" % path)
	var loaded: Material = load(path)
	_materials[key] = loaded
	return loaded


func _build(b: Dictionary) -> bool:
	var id: String = b["id"]
	var tools := {}          # material key -> SurfaceTool
	var mats := {}           # material key -> Material
	var order := []
	for p in b["pieces"]:
		var path: String = p["path"]
		var kit_res := _kit_res(path)
		var pos: Array = p["pos"]
		var xf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(p["yaw"]))), Vector3(pos[0], pos[1], pos[2]))
		var surfs := _surfaces(path)
		if surfs.is_empty():
			return false
		for s in surfs:
			var mat := _kit_material(kit_res, s[3])
			var key := mat.resource_path if mat != null else "<none>"
			if not tools.has(key):
				var st := SurfaceTool.new()
				tools[key] = st
				mats[key] = mat
				order.append(key)
			(tools[key] as SurfaceTool).append_from(s[0], s[1], xf * (s[2] as Transform3D))
	var mesh := ArrayMesh.new()
	for key in order:
		var st: SurfaceTool = tools[key]
		st.commit(mesh)
		mesh.surface_set_material(mesh.get_surface_count() - 1, mats[key])
		mesh.surface_set_name(mesh.get_surface_count() - 1, (mats[key] as Material).resource_name if mats[key] else "none")
	var mesh_path := "%s/%s_mesh.res" % [OUT_DIR, id]
	if ResourceSaver.save(mesh, mesh_path, ResourceSaver.FLAG_COMPRESS) != OK:
		push_error("cannot save " + mesh_path)
		return false
	mesh = load(mesh_path)

	var root := Node3D.new()
	root.name = id
	var mi := MeshInstance3D.new()
	mi.name = "Mesh"
	mi.mesh = mesh
	root.add_child(mi)
	mi.owner = root

	var body := StaticBody3D.new()
	body.name = "Collision"
	body.collision_layer = 1
	body.collision_mask = 0
	root.add_child(body)
	body.owner = root
	var k := 0
	for bx in b["boxes"]:
		var cs := CollisionShape3D.new()
		cs.name = "Box%d" % k
		k += 1
		var shape := BoxShape3D.new()
		shape.size = Vector3(bx["size"][0], bx["size"][1], bx["size"][2])
		cs.shape = shape
		cs.position = Vector3(bx["center"][0], bx["center"][1], bx["center"][2])
		body.add_child(cs)
		cs.owner = root
	var hi := 0
	for h in b.get("hulls", []):
		# a convex hull of a library piece (a ramp): its own mesh, placed as the layout says
		var hpos: Array = h["pos"]
		var hxf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(h["yaw"]))), Vector3(hpos[0], hpos[1], hpos[2]))
		var pts := PackedVector3Array()
		for s in _surfaces(h["path"]):
			var arr := (s[0] as Mesh).surface_get_arrays(s[1])
			for v in arr[Mesh.ARRAY_VERTEX]:
				pts.append(hxf * ((s[2] as Transform3D) * v))
		var hull := ConvexPolygonShape3D.new()
		hull.points = pts
		var hs := CollisionShape3D.new()
		hs.name = "Hull%d" % hi
		hi += 1
		hs.shape = hull
		body.add_child(hs)
		hs.owner = root
	if b.get("collision", "") == "trimesh":
		# the collider is the building's own shell (the first `trimesh_pieces` placed pieces), never its cladding or
		# furniture: a clad facade is ~100k visual vertices a physics server has no business testing
		var n_col := int(b.get("trimesh_pieces", b["pieces"].size()))
		var tri: Shape3D
		if n_col >= b["pieces"].size():
			tri = mesh.create_trimesh_shape()
		else:
			var faces := PackedVector3Array()
			for pi in n_col:
				var pp: Dictionary = b["pieces"][pi]
				var ppos: Array = pp["pos"]
				var pxf := Transform3D(Basis(Vector3.UP, deg_to_rad(float(pp["yaw"]))), Vector3(ppos[0], ppos[1], ppos[2]))
				for sf in _surfaces(pp["path"]):
					var fx: Transform3D = pxf * (sf[2] as Transform3D)
					var st2 := SurfaceTool.new()
					st2.append_from(sf[0], sf[1], fx)
					var m2 := st2.commit()
					for v in m2.get_faces():
						faces.append(v)
			var cps := ConcavePolygonShape3D.new()
			cps.set_faces(faces)
			tri = cps
		var shape_path := "%s/%s_collision.res" % [OUT_DIR, id]
		ResourceSaver.save(tri, shape_path, ResourceSaver.FLAG_COMPRESS)
		var cs := CollisionShape3D.new()
		cs.name = "Trimesh"
		cs.shape = load(shape_path)
		body.add_child(cs)
		cs.owner = root

	var di := 0
	for d in b["doors"]:
		var mk := Marker3D.new()
		mk.name = "Door_%s_%d" % [d["side"], d["module"]]
		var out := Vector3(d["outward"][0], d["outward"][1], d["outward"][2])
		# -Z of the marker points OUT of the building (the way a player leaving it walks)
		mk.transform = Transform3D(Basis.looking_at(out, Vector3.UP), Vector3(d["center"][0], d["center"][1], d["center"][2]))
		root.add_child(mk)
		mk.owner = root
		di += 1

	var meta := b.duplicate(true)
	meta.erase("pieces")
	meta.erase("boxes")
	meta.erase("hulls")
	meta["piece_count"] = b["pieces"].size()
	meta["aabb"] = [mesh.get_aabb().position, mesh.get_aabb().size]
	root.set_meta("building", meta)

	var packed := PackedScene.new()
	if packed.pack(root) != OK:
		push_error("cannot pack " + id)
		root.free()
		return false
	var scene_path := "%s/%s.tscn" % [OUT_DIR, id]
	var err := ResourceSaver.save(packed, scene_path)
	root.free()
	var aabb := mesh.get_aabb()
	print("%-18s %5d pieces -> %d surfaces, %d verts, aabb %s, %s" % [id, b["pieces"].size(), mesh.get_surface_count(),
		_vert_count(mesh), aabb.size, "OK" if err == OK else "SAVE FAILED"])
	return err == OK


func _vert_count(mesh: ArrayMesh) -> int:
	var n := 0
	for s in mesh.get_surface_count():
		n += (mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	return n
