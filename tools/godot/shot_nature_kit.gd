extends SceneTree
## shot_nature_kit.gd -- render the Stylized Nature kit's pieces beside the character (PLAN.md 3.16 step 1).
## NEEDS A DISPLAY (no --headless: the dummy renderer draws nothing).
##
##   godot --path . --script tools/godot/shot_nature_kit.gd -- <out_dir> [--only=cat,cat] [--before] [--variants]
##
## One picture per CATEGORY: every piece of that family in a row on the ground with a 1.49 m capsule (the
## character's height) beside the first one, so the scale reads at a glance -- which is the only way to judge
## "is this Japanese, and is it the right size" once the numbers say it is in band.
## `--before` renders the same pieces at the size the DOWNLOAD had them -- each instance scaled by the inverse of
## its family's baked `category_scale` -- so the two pictures are the before and after of the rescale. It is drawn
## from the kit's own pieces on purpose: `source/` carries a `.gdignore` (Godot must never import the raw
## download), so a mode that tried to load from there would draw an empty ground and call it evidence.
##
## `--variants` renders ONE picture instead: the same broadleaf tree five times, each wearing a different leaf
## colour over the download's own WHITE leaf mask. The kit ships two textures per leaf shape -- `X.png`, which is
## pure white (measured mean 253,253,253 over its opaque texels), and `X_C.png`, the same shape already tinted --
## so a sakura, a fresh-green keyaki, an autumn ginkgo and a momiji are ONE albedo colour each over the white one,
## with no new texture and no new mesh. This is the picture that decides those colours (PLAN.md 3.16 step 3).
##
## It also PRINTS what it drew -- the measured size of each piece and the materials it resolved -- so a run
## without a display still says whether a piece loads and wears its kit material.

const KIT := "res://assets/world_source/kits/quaternius_stylized_nature"

var _out := ""
var _before := false
var _variants := false
var _only: Array = []

## Candidate leaf colours over the white mask: name, albedo. Measured starting points, not final art.
const TINTS := [
	["sakura", Color(0.98, 0.78, 0.84)],
	["fresh_green", Color(0.55, 0.74, 0.28)],
	["deep_green", Color(0.24, 0.42, 0.16)],
	["ginkgo_autumn", Color(0.95, 0.78, 0.18)],
	["momiji", Color(0.72, 0.13, 0.11)],
]
const WHITE_LEAF := KIT + "/textures/Leaves_NormalTree.png"
const VARIANT_PIECE := KIT + "/pieces/trees_broadleaf/CommonTree_3.gltf"


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if args.size() > 0 and not args[0].begins_with("--") else "user://nature_shots"
	for a in args:
		if a.begins_with("--only="):
			_only = Array(a.substr(7).split(","))
		if a == "--before":
			_before = true
		if a == "--variants":
			_variants = true
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = Vector2i(1600, 900)
	_run.call_deferred()


func _baked_scale(cat: String) -> float:
	var f := FileAccess.open(KIT + "/kit.json", FileAccess.READ)
	var kit: Dictionary = JSON.parse_string(f.get_as_text())
	var per: Dictionary = kit.get("category_scale", {})
	return float(per.get(cat, kit.get("module_scale", 1.0)))


func _pieces() -> Dictionary:
	var f := FileAccess.open(KIT + "/pieces.json", FileAccess.READ)
	assert(f != null, "no pieces.json -- run tools/building_kit/normalize_kit.py")
	var doc: Dictionary = JSON.parse_string(f.get_as_text())
	var by_cat := {}
	for name in doc["pieces"]:
		var p: Dictionary = doc["pieces"][name]
		if not _only.is_empty() and not _only.has(p["category"]):
			continue
		by_cat.get_or_add(p["category"], []).append([name, p])
	for c in by_cat:
		by_cat[c].sort_custom(func(a, b): return a[0] < b[0])
	return by_cat


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
	sun.rotation_degrees = Vector3(-48, -40, 0)
	sun.shadow_enabled = true
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.34, 0.38, 0.28)
	pm.material = gm
	ground.mesh = pm
	ground.position.y = -0.005
	root.add_child(ground)
	var cam := Camera3D.new()
	cam.fov = 45
	cam.far = 2000.0
	root.add_child(cam)
	cam.make_current()

	# The ruler: the character's own height, beside every family.
	var man := MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.radius = 0.25
	cap.height = 1.49
	var cm := StandardMaterial3D.new()
	cm.albedo_color = Color(0.85, 0.18, 0.14)
	cap.material = cm
	man.mesh = cap
	root.add_child(man)

	if _variants:
		await _shoot_variants(cam, man)
		quit(0)
		return
	for cat in _pieces():
		var row: Array = _pieces()[cat]
		var holder := Node3D.new()
		root.add_child(holder)
		var x := 0.0
		var tallest := 0.0
		var tris := 0
		for entry in row:
			var name: String = entry[0]
			var p: Dictionary = entry[1]
			var path := KIT + "/" + (p["path"] as String)
			var scene := load(path) as PackedScene
			if scene == null:
				push_error("could not load " + path)
				continue
			var inst: Node3D = scene.instantiate()
			holder.add_child(inst)
			var sz: Array = p["size"]
			if _before:
				var back := 1.0 / maxf(_baked_scale(cat), 0.0001)
				inst.scale = Vector3.ONE * back
				sz = [sz[0] * back, sz[1] * back, sz[2] * back]
			var w: float = maxf(sz[0], sz[2])
			var gap: float = maxf(w, 0.35) * 0.65
			x += gap
			inst.position = Vector3(x, 0, 0)
			x += gap
			tallest = maxf(tallest, sz[1])
			var mats := PackedStringArray()
			for mi in _meshes(inst):
				tris += _tris(mi)
				for s in mi.mesh.get_surface_count():
					var m: Material = mi.get_active_material(s)
					if m != null and not mats.has(m.resource_name):
						mats.append(m.resource_name)
			print("  %-24s %5.2f x %5.2f x %5.2f m  %s" % [name, sz[0], sz[1], sz[2], ", ".join(mats)])
		man.position = Vector3(-0.9, 0.745, 0)
		var span: float = maxf(x, 2.0)
		var h: float = maxf(tallest, 1.6)
		var r: float = maxf(span, h) * 0.95 + 3.0
		cam.position = Vector3(span * 0.5 - 0.9, h * 0.45 + 1.2, r)
		cam.look_at(Vector3(span * 0.5 - 0.9, h * 0.42, 0))
		for i in 14:
			await process_frame
		RenderingServer.force_draw()
		var img := root.get_texture().get_image()
		var path2 := "%s/%s%s.png" % [_out, cat, "_before" if _before else ""]
		img.save_png(path2)
		print("SHOT %s  (%d pieces, %d triangles, tallest %.2f m)" % [path2, row.size(), tris, tallest])
		holder.queue_free()
		await process_frame
	quit(0)


func _shoot_variants(cam: Camera3D, man: MeshInstance3D) -> void:
	var tex: Texture2D = load(WHITE_LEAF)
	assert(tex != null, "no white leaf mask at " + WHITE_LEAF)
	var scene := load(VARIANT_PIECE) as PackedScene
	var holder := Node3D.new()
	root.add_child(holder)
	var x := 0.0
	for t in TINTS:
		var inst: Node3D = scene.instantiate()
		holder.add_child(inst)
		inst.position = Vector3(x, 0, 0)
		x += 6.0
		for mi in _meshes(inst):
			for si in (mi as MeshInstance3D).mesh.get_surface_count():
				var m: Material = mi.get_active_material(si)
				if m == null or not (m.resource_name as String).begins_with("MI_Leaves"):
					continue
				var leaf := StandardMaterial3D.new()
				leaf.albedo_texture = tex
				leaf.albedo_color = t[1]
				leaf.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				leaf.alpha_scissor_threshold = 0.2
				leaf.cull_mode = BaseMaterial3D.CULL_DISABLED
				leaf.roughness = 1.0
				mi.set_surface_override_material(si, leaf)
		print("  variant %-14s albedo %s" % [t[0], t[1]])
	man.position = Vector3(-2.2, 0.745, 0)
	cam.position = Vector3(x * 0.5 - 3.2, 5.0, x * 0.8 + 6.0)
	cam.look_at(Vector3(x * 0.5 - 3.2, 4.2, 0))
	for i in 16:
		await process_frame
	RenderingServer.force_draw()
	var path := _out + "/leaf_variants.png"
	root.get_texture().get_image().save_png(path)
	print("SHOT %s  (%d tints over the white leaf mask, one material each)" % [path, TINTS.size()])
	holder.queue_free()
	await process_frame


func _meshes(n: Node) -> Array:
	var out := []
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		out.append(n)
	for c in n.get_children():
		out.append_array(_meshes(c))
	return out


func _tris(mi: MeshInstance3D) -> int:
	var n := 0
	for s in mi.mesh.get_surface_count():
		var a := mi.mesh.surface_get_arrays(s)
		var idx: PackedInt32Array = a[Mesh.ARRAY_INDEX]
		n += (idx.size() if idx.size() > 0 else (a[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()) / 3
	return n
