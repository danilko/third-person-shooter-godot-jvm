extends SceneTree
##
## Paint a Terrain3D control map from a u8 mask on the `dump_height_grid.gd` grid: 1 = this texel is the named
## texture, 0 = leave it as it is. Written for PLAN.md 3.18(c3), where the mask is a city block's own ground
## (`tools/island_ground.py`) -- the ground inside a block must not read as the beach `paint_terrain.gd` gives
## every texel under 5 m.
##
##   godot --headless --path . --script tools/godot/apply_paint_grid.gd -- \
##       <data dir> <mask.u8> <x0> <z0> <nx> <nz> <step> <texture id> [<heights.f32>]
##
## The last argument is the height grid the mask was derived from. It is not optional in spirit: a control map
## is addressed by REGION texel and the mask by world metre, and getting that mapping wrong paints somewhere
## else entirely with nothing to see in the log. Given it, this refuses to paint when the terrain's own heights
## disagree with the grid by more than 1 cm.
##

var _terrain: Node
var _done := false


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	_terrain = ClassDB.instantiate("Terrain3D")
	root.add_child(_terrain)
	_terrain.set("vertex_spacing", float(a[6]))
	_terrain.set("data_directory", a[0])


func _process(_d: float) -> bool:
	if _done:
		return true
	_done = true
	quit(_run())
	return true


func _run() -> int:
	var a := OS.get_cmdline_user_args()
	var x0 := float(a[2])
	var z0 := float(a[3])
	var nx := int(a[4])
	var nz := int(a[5])
	var st := float(a[6])
	var tex := int(a[7])
	var mask := FileAccess.get_file_as_bytes(a[1])
	if mask.size() != nx * nz:
		print("ERROR mask has %d cells, expected %d" % [mask.size(), nx * nz])
		return 1
	var heights := PackedFloat32Array()
	if a.size() > 8:
		heights = FileAccess.get_file_as_bytes(a[8]).to_float32_array()
		if heights.size() != nx * nz:
			print("ERROR heights grid has %d cells, expected %d" % [heights.size(), nx * nz])
			return 1
	var data = _terrain.get("data")
	var rs: int = _terrain.get("region_size")
	var painted := 0
	var checked := 0
	var worst := 0.0
	var ctl: float = Terrain3DUtil.as_float(
		Terrain3DUtil.enc_base(tex) | Terrain3DUtil.enc_overlay(tex) | Terrain3DUtil.enc_blend(0))
	for loc in data.get("region_locations"):
		var region: Variant = data.call("get_region", loc)
		if region == null:
			continue
		var cmap: Image = region.call("get_control_map")
		var hmap: Image = region.call("get_height_map")
		if cmap == null:
			continue
		var touched := false
		for y in rs:
			var wz: float = (float(loc.y) * rs + y) * st
			var j := int(round((wz - z0) / st))
			if j < 0 or j >= nz:
				continue
			for x in rs:
				var wx: float = (float(loc.x) * rs + x) * st
				var i := int(round((wx - x0) / st))
				if i < 0 or i >= nx:
					continue
				if not heights.is_empty() and hmap != null:
					var want := heights[j * nx + i]
					if is_finite(want):
						var got: float = hmap.get_pixel(x, y).r
						worst = maxf(worst, absf(got - want))
						checked += 1
				if mask[j * nx + i] == 0:
					continue
				cmap.set_pixel(x, y, Color(ctl, 0.0, 0.0))
				painted += 1
				touched = true
		if touched:
			region.call("set_control_map", cmap)
			if region.has_method("set_modified"):
				region.call("set_modified", true)
	if checked > 0:
		print("alignment: %d texels checked against the grid, worst height difference %.4f m" % [checked, worst])
		if worst > 0.01:
			print("ERROR the grid and the terrain disagree -- refusing to paint somewhere else")
			return 1
	data.call("update_maps", 1, true, false)
	data.save_directory(a[0])
	# paint_terrain.gd refuses to run over this (it would repaint the city as beach), and so does the road stamp
	# (it would take the block ground back down); the stamp and its probe read the layer itself from URBAN_LAYER
	var layer_n := 0
	if not heights.is_empty():
		layer_n = _write_layer(a[0].path_join("urban_block.layer"), heights, nx, nz, x0, z0, st)
	var m := FileAccess.open(a[0].path_join("urban_paint.marker"), FileAccess.WRITE)
	m.store_string("written by apply_paint_grid.gd from %s; block layer urban_block.layer (%d vertices)\n" % [a[1], layer_n])
	m.close()
	print("painted %d texels with texture %d -> %s" % [painted, tex, a[0]])
	return 0


## The block ground as a sparse layer (the format `road_kit_stamp.gd load_layer` reads): every finite cell of the
## height grid this paint was derived with, which is exactly what `apply_height_grid.gd` wrote.
func _write_layer(path: String, heights: PackedFloat32Array, nx: int, nz: int, x0: float, z0: float, st: float) -> int:
	var idx := PackedInt32Array()
	var val := PackedFloat32Array()
	for k in heights.size():
		if is_finite(heights[k]):
			idx.append(k)
			val.append(heights[k])
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_32(0x314C4255)
	f.store_32(nx)
	f.store_32(nz)
	f.store_float(x0)
	f.store_float(z0)
	f.store_float(st)
	f.store_32(idx.size())
	for i in idx.size():
		f.store_32(idx[i])
		f.store_float(val[i])
	f.close()
	return idx.size()
