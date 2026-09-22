extends SceneTree
## R9 (PLAN.md 3.32/3.34): one merged HLOD mesh per building cell, from the boxes `tools/island_buildings.py write`
## records (`cells/hlod/boxes.json`: per building its placement, footprint, height and facade tone colour).
##   <godot> --headless --path . --script tools/godot/build_building_hlod.gd [-- --check]
## Each building is a box of its type's own footprint and height; the walls wear the building's facade tone, the
## roof a darker grey, and each storey (3.0 m) a darker window band, so a far block still reads as a city at 500 m.
## One surface, vertex colours, one material (`MI_HLOD.tres`): one draw call per cell. The mesh is written only
## when it changes, so re-running is free.
const DIR := "res://src/main/resources/com/openworld/world/buildings/cells/hlod"
const MAT := DIR + "/MI_HLOD.tres"
const STOREY := 3.0
const BAND := 1.1          # the dark window band's height in each storey
const BAND_DARK := 0.55
const ROOF := Color(0.36, 0.36, 0.37)

var st: SurfaceTool

func _quad(a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3, col: Color) -> void:
	for v in [a, b, c, a, c, d]:
		st.set_color(col)
		st.set_normal(n)
		st.add_vertex(v)

func _box(b: Array) -> void:
	var pos := Vector3(b[0], b[1], b[2])
	var basis := Basis(Vector3.UP, deg_to_rad(float(b[3])))
	var x0: float = b[4]
	var z0: float = b[5]
	var x1: float = b[6]
	var z1: float = b[7]
	var h: float = b[8]
	var c: Array = b[9]
	var wall := Color(c[0], c[1], c[2])
	var dark := Color(c[0] * BAND_DARK, c[1] * BAND_DARK, c[2] * BAND_DARK)
	var corners := [Vector3(x0, 0, z1), Vector3(x1, 0, z1), Vector3(x1, 0, z0), Vector3(x0, 0, z0)]
	# walls in bands: plain wall, then a dark window band near the top of each storey
	var levels := [0.0]
	var y := 0.0
	var dark_at := {}
	while y + STOREY <= h - 0.5:
		levels.append(y + STOREY - BAND - 0.4)
		dark_at[levels.size() - 1] = true
		levels.append(y + STOREY - 0.4)
		y += STOREY
	levels.append(h)
	for i in range(4):
		var p: Vector3 = corners[i]
		var q: Vector3 = corners[(i + 1) % 4]
		var n := basis * (q - p).cross(Vector3.UP).normalized()
		for k in range(levels.size() - 1):
			var ya: float = levels[k]
			var yb: float = levels[k + 1]
			if yb - ya < 0.01:
				continue
			var col := dark if dark_at.has(k) else wall
			_quad(pos + basis * Vector3(p.x, ya, p.z), pos + basis * Vector3(q.x, ya, q.z),
					pos + basis * Vector3(q.x, yb, q.z), pos + basis * Vector3(p.x, yb, p.z), n, col)
	_quad(pos + basis * Vector3(x0, h, z1), pos + basis * Vector3(x1, h, z1), pos + basis * Vector3(x1, h, z0),
			pos + basis * Vector3(x0, h, z0), Vector3.UP, ROOF)

func _initialize() -> void:
	var check := "--check" in OS.get_cmdline_user_args()
	var doc: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DIR + "/boxes.json"))
	var mat: Material = load(MAT)
	var changed := 0
	var tris := 0
	for name in doc["cells"]:
		st = SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		for b in doc["cells"][name]:
			_box(b)
		st.set_material(mat)
		var mesh := st.commit()
		var path: String = DIR + "/" + name + ".res"
		tris += mesh.surface_get_array_len(0) / 3 if mesh.get_surface_count() > 0 else 0
		# written only when its source boxes changed: the mesh carries a hash of them
		var src := JSON.stringify(doc["cells"][name]).hash()
		mesh.set_meta("src", src)
		var same := false
		if ResourceLoader.exists(path):
			var old = load(path)
			same = old is ArrayMesh and old.has_meta("src") and int(old.get_meta("src")) == src
		if same:
			continue
		changed += 1
		if not check:
			ResourceSaver.save(mesh, path, ResourceSaver.FLAG_COMPRESS)
	print("build_building_hlod: %d cells, %d triangles, %d %s" % [doc["cells"].size(), tris, changed,
			"stale" if check else "written"])
	quit(1 if check and changed > 0 else 0)
