extends SceneTree
## Write a float32 height grid (the `dump_height_grid.gd` layout) into a Terrain3D data directory and save it.
## Only vertices whose height changes by more than 1 mm are written; NaN cells are skipped. The grid's step
## should equal the terrain's vertex spacing (2 m) so every write lands on a vertex.
##
##   godot --headless --path . --script tools/godot/apply_height_grid.gd -- <data dir> <grid.f32> <x0> <z0> <nx> <nz> <step>

var _terrain: Node
var _done := false

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	_terrain = ClassDB.instantiate("Terrain3D")
	root.add_child(_terrain)
	_terrain.set("vertex_spacing", 2.0)
	_terrain.set("data_directory", a[0])

func _process(_d: float) -> bool:
	if _done:
		return true
	_done = true
	var a := OS.get_cmdline_user_args()
	var x0 := float(a[2])
	var z0 := float(a[3])
	var nx := int(a[4])
	var nz := int(a[5])
	var st := float(a[6])
	var bytes := FileAccess.get_file_as_bytes(a[1])
	var grid := bytes.to_float32_array()
	if grid.size() != nx * nz:
		print("ERROR grid has %d cells, expected %d" % [grid.size(), nx * nz])
		quit(1)
		return true
	var data = _terrain.get("data")
	var regions := {}
	var changed := 0
	var biggest := 0.0
	for j in nz:
		for i in nx:
			var h := grid[j * nx + i]
			if is_nan(h):
				continue
			var p := Vector3(x0 + i * st, 0, z0 + j * st)
			var cur: float = data.get_height(p)
			if is_nan(cur) or absf(cur - h) <= 0.001:
				continue
			data.set_height(p, h)
			regions[data.get_region_location(p)] = true
			changed += 1
			biggest = maxf(biggest, absf(cur - h))
	for loc in regions:
		data.set_region_modified(loc, true)
	if changed > 0:
		data.update_maps(0, true, false)
		data.calc_height_range(true)
		data.save_directory(a[0])
	print("APPLIED %d vertex(es) in %d region(s), largest change %.2f m" % [changed, regions.size(), biggest])
	quit(0)
	return true
