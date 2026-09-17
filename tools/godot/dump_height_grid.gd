extends SceneTree
## Dump a Terrain3D data directory's heights on a regular grid to a float32 file (row-major, row j = Godot
## z0 + j*step, column i = Godot x0 + i*step). The input to heightfield tools written in numpy, e.g.
## `tools/island_widen_first_mountain.py`; `apply_height_grid.gd` writes such a grid back.
##
##   godot --headless --path . --script tools/godot/dump_height_grid.gd -- <out.f32> <x0> <z0> <nx> <nz> <step> [<data dir>]
##
## Runs in `_process`: in `_initialize` the data directory has not loaded yet and every height reads NaN.

var _terrain: Node
var _done := false

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	_terrain = ClassDB.instantiate("Terrain3D")
	root.add_child(_terrain)
	_terrain.set("vertex_spacing", 2.0)
	_terrain.set("data_directory", a[6] if a.size() > 6 else "res://assets/terrain3d/island")

func _process(_d: float) -> bool:
	if _done:
		return true
	_done = true
	var a := OS.get_cmdline_user_args()
	var x0 := float(a[1])
	var z0 := float(a[2])
	var nx := int(a[3])
	var nz := int(a[4])
	var st := float(a[5])
	var data = _terrain.get("data")
	var buf := PackedFloat32Array()
	buf.resize(nx * nz)
	for j in nz:
		for i in nx:
			buf[j * nx + i] = data.get_height(Vector3(x0 + i * st, 0, z0 + j * st))
	var f := FileAccess.open(a[0], FileAccess.WRITE)
	f.store_buffer(buf.to_byte_array())
	f.close()
	print("DUMP %d x %d at %.1f m -> %s" % [nx, nz, st, a[0]])
	quit(0)
	return true
