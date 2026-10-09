extends SceneTree
##
## Soften the edge of one painted Terrain3D texture (2026-10-08, from a picture: the urban block ground met the
## beach in a 2 m staircase -- `apply_paint_grid.gd` writes a hard base id per vertex, so every vertex is either
## all Urban or all sand). Every texel whose base is NOT `<texture id>` but which has a texel of that base within
## `RINGS` texels gets the texture as its OVERLAY, blended by how near it is (ring 1 BLEND[0], ring 2 BLEND[1]);
## its base is left alone, so the beach / grass / soil under it still shows through.
##
##   godot --headless --path . --script tools/godot/soften_paint_edge.gd -- <data dir> <texture id> [--dry]
##
## Idempotent: it reads only base ids and writes only the overlay + blend of texels whose base is something else,
## so a second run writes the same values. `apply_paint_grid.gd` overwrites a texel whole (base = overlay, blend
## 0), so re-painting the block ground clears the ring under it; run this after every paint.
##

const RINGS := 2
const BLEND := [0.55, 0.25]

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
	quit(_run())
	return true


func _run() -> int:
	var a := OS.get_cmdline_user_args()
	var tex := int(a[1])
	var dry := "--dry" in a
	var data = _terrain.get("data")
	var rs: int = _terrain.get("region_size")
	# Read every region's control map into one dictionary keyed by region location, so a ring can look across a
	# region edge.
	var maps := {}
	for loc in data.get("region_locations"):
		var region: Variant = data.call("get_region", loc)
		if region != null and region.call("get_control_map") != null:
			maps[loc] = region.call("get_control_map")
	var base_at := func(gx: int, gy: int) -> int:
		var loc := Vector2i(floori(float(gx) / rs), floori(float(gy) / rs))
		var img: Image = maps.get(loc)
		if img == null:
			return -1
		var c := Terrain3DUtil.as_uint(img.get_pixel(gx - loc.x * rs, gy - loc.y * rs).r)
		return Terrain3DUtil.get_base(c)
	var written := 0
	var touched := {}
	for loc in maps:
		var img: Image = maps[loc]
		for y in rs:
			for x in rs:
				var c := Terrain3DUtil.as_uint(img.get_pixel(x, y).r)
				var base := Terrain3DUtil.get_base(c)
				if base == tex:
					continue
				var gx: int = loc.x * rs + x
				var gy: int = loc.y * rs + y
				var ring := 0
				for r in range(1, RINGS + 1):
					var hit := false
					for dy in range(-r, r + 1):
						for dx in range(-r, r + 1):
							if maxi(absi(dx), absi(dy)) != r:
								continue
							if base_at.call(gx + dx, gy + dy) == tex:
								hit = true
								break
						if hit:
							break
					if hit:
						ring = r
						break
				if ring == 0:
					continue
				var blend: float = BLEND[ring - 1]
				var keep := c & ~(Terrain3DUtil.enc_overlay(31) | Terrain3DUtil.enc_blend(255))
				var nc := keep | Terrain3DUtil.enc_overlay(tex) | Terrain3DUtil.enc_blend(int(round(blend * 255.0)))
				if nc != c:
					img.set_pixel(x, y, Color(Terrain3DUtil.as_float(nc), 0.0, 0.0))
					written += 1
					touched[loc] = true
	print("soften_paint_edge: %d texels %s with texture %d as overlay" % [written, "would be blended" if dry else "blended", tex])
	if dry or written == 0:
		return 0
	for loc in touched:
		var region: Variant = data.call("get_region", loc)
		region.call("set_control_map", maps[loc])
		if region.has_method("set_modified"):
			region.call("set_modified", true)
	data.call("update_maps", 1, true, false)
	data.save_directory(a[0])
	return 0
