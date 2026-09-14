@tool
extends RefCounted
## Road Kit B6b (PLAN.md 3.1): the scene's Terrain3D -> the ground sidecar the mesh build reads.
## EDITOR TOOLING ONLY.
##
## The kit derives every support from `delta = surface_z - ground_z` PER SAMPLE (`point_solve.solve_road`,
## one call into `road_support` every 4 m). Its ground used to be a raycast into the Blender scene; a
## road authored in Godot is built in a Blender session with no terrain, so every sample fell back to a
## LERP of the stations' own `ground_z` -- and a 3-station road over a gap got a triangle of piers under
## its middle station, not a bridge. This file writes the ground itself: a height grid over the
## network's footprint, in the NETWORK's frame and the kit's axes (the frame the record is written in),
## which `point_ground.py` reads as the sampler.
##
##   <stem>.ground.json  {"schema_ver", "origin": [x0, y0], "step", "nx", "ny", "bin": "<stem>.ground.bin"}
##   <stem>.ground.bin   float32 little-endian, row-major: row j is kit y = y0 + j*step, column i is
##                       kit x = x0 + i*step; NaN where the terrain has no data (off the map).
##
## SAMPLE THE NATURAL GROUND. Once B7 stamps the road corridors into the height map
## (`road_kit_stamp.gd`), the terrain under a road IS the road, and a grid sampled from it reads every
## stretch as at grade -- the kit's CARVED_FLAG trap. So once a network has a stamp record
## (`<stem>.stamp.json`), THIS SIDECAR IS THE NATURAL GROUND wherever it covers: `natural_height` and
## `sample_grid` read it there and the terrain only outside it. To re-derive the natural ground after
## re-sculpting, Restore Terrain first (which deletes the stamp record).
##
## The grid is snapped to multiples of `step` in the network frame, so for a network that is not turned
## against the terrain (Terrain3D `vertex_spacing` 2 m) every grid sample IS a terrain vertex and the
## stamp's restore of the natural height is exact, not an interpolation.

const Frame := preload("res://addons/road_kit/road_kit_frame.gd")
const SCHEMA_VER := 1
## Grid spacing. A support is decided every 4 m (`road_points.SAMPLE_STEP`), so 2 m is Nyquist for it.
const STEP := 2.0
## How far past the stations the grid reaches. A swept curve bulges past its chord and a fill toe or a
## pad reaches past its station, so the footprint of the points alone is not enough.
const MARGIN := 60.0

static func _stem(record_path: String) -> String:
	if record_path.ends_with(".roads.json"):
		return record_path.substr(0, record_path.length() - ".roads.json".length())
	return record_path.get_basename()

static func sidecar_path(record_path: String) -> String:
	return _stem(record_path) + ".ground.json"

## B7's record of what it stamped: its existence means the terrain under this network is not natural.
static func stamp_record_path(record_path: String) -> String:
	return _stem(record_path) + ".stamp.json"

## `{"header", "heights"}` from a sidecar, or `{}` when there is none (or it is unreadable).
static func load_grid(json_path: String) -> Dictionary:
	if json_path == "" or not FileAccess.file_exists(json_path):
		return {}
	var head = JSON.parse_string(FileAccess.get_file_as_string(json_path))
	if typeof(head) != TYPE_DICTIONARY or int(head.get("schema_ver", 0)) != SCHEMA_VER:
		return {}
	var bin := json_path.get_base_dir().path_join(str(head["bin"]))
	if not FileAccess.file_exists(bin):
		return {}
	var heights := FileAccess.get_file_as_bytes(bin).to_float32_array()
	if heights.size() != int(head["nx"]) * int(head["ny"]):
		return {}
	return {"header": head, "heights": heights}

## Bilinear height in the network frame at kit `(kx, ky)`; NAN outside the grid or next to a NaN cell.
## The same rule as `point_ground.GroundGrid.__call__`.
static func lookup(grid: Dictionary, kx: float, ky: float) -> float:
	if grid.is_empty():
		return NAN
	var h: Dictionary = grid["header"]
	var nx := int(h["nx"])
	var ny := int(h["ny"])
	var step := float(h["step"])
	var fx := (kx - float(h["origin"][0])) / step
	var fy := (ky - float(h["origin"][1])) / step
	var i := int(floor(fx))
	var j := int(floor(fy))
	if i == nx - 1 and fx <= nx - 1 + 1e-6:
		i -= 1
	if j == ny - 1 and fy <= ny - 1 + 1e-6:
		j -= 1
	if i < 0 or j < 0 or i >= nx - 1 or j >= ny - 1:
		return NAN
	var hs: PackedFloat32Array = grid["heights"]
	var a := hs[j * nx + i]
	var b := hs[j * nx + i + 1]
	var c := hs[(j + 1) * nx + i]
	var d := hs[(j + 1) * nx + i + 1]
	if is_nan(a) or is_nan(b) or is_nan(c) or is_nan(d):
		return NAN
	var tx := fx - i
	var ty := fy - j
	return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty

## The natural-ground source for `net`: its sidecar once the terrain under it has been stamped, `{}`
## while the terrain is still natural (read the terrain).
static func natural_source(net: Node) -> Dictionary:
	var rec := str(net.get("record_path"))
	if rec == "" or not FileAccess.file_exists(stamp_record_path(rec)):
		return {}
	return load_grid(sidecar_path(rec))

## The NATURAL ground height at a world position: the stamped network's sidecar where it covers, the
## terrain everywhere else. NAN where neither has data.
static func natural_height(net: Node3D, terrain: Node, src: Dictionary, world: Vector3) -> float:
	if not src.is_empty():
		var to_world := _world_xf(net)
		var local := to_world.affine_inverse() * world
		var k := Frame.to_kit(local)
		var h := lookup(src, k.x, k.y)
		if not is_nan(h):
			return (to_world * Vector3(local.x, h, local.z)).y
	return terrain.data.get_height(world)

## The network's footprint in the KIT frame (x, y), grown by `margin`: `Rect2(x0, y0, w, h)`.
static func footprint(net: Node3D, margin: float = MARGIN) -> Rect2:
	var pts: Array = net.all_points()
	if pts.is_empty():
		return Rect2()
	var r := Rect2()
	var first := true
	for p in pts:
		var k := Frame.to_kit(p.network_transform().origin)
		if first:
			r = Rect2(k.x, k.y, 0, 0)
			first = false
		else:
			r = r.expand(Vector2(k.x, k.y))
	return r.grow(margin)

## `{"ok", "message", "header", "heights": PackedFloat32Array, "hits", "misses"}`. The world transform
## of the network is composed up its ancestors (so it answers the same in the editor, a running tree
## and an unparented node); heights come back in the network's frame.
static func sample_grid(net: Node3D, terrain: Node, step: float = STEP, margin: float = MARGIN) -> Dictionary:
	if terrain == null or terrain.get("data") == null:
		return {"ok": false, "message": "no Terrain3D data to sample"}
	var rect := footprint(net, margin)
	if rect.size == Vector2.ZERO:
		return {"ok": false, "message": "%s has no points" % net.name}
	var lo := (rect.position / step).floor() * step
	rect = Rect2(lo, rect.end - lo)
	var src := natural_source(net)
	if src.is_empty() and FileAccess.file_exists(stamp_record_path(str(net.get("record_path")))):
		# Stamped, and the natural record is gone: sampling now would read the roads back as ground.
		return {"ok": false, "message": "%s is stamped into the terrain but its natural ground %s is missing -- restore it from version control; re-sampling would read the stamped roads as ground" % [net.name, sidecar_path(str(net.get("record_path")))]}
	var to_world := _world_xf(net)
	var from_world := to_world.affine_inverse()
	var nx := int(ceil(rect.size.x / step)) + 1
	var ny := int(ceil(rect.size.y / step)) + 1
	var heights := PackedFloat32Array()
	heights.resize(nx * ny)
	var hits := 0
	var misses := 0
	for j in ny:
		var ky := rect.position.y + j * step
		for i in nx:
			var kx := rect.position.x + i * step
			var world: Vector3 = to_world * Frame.to_godot(Vector3(kx, ky, 0.0))
			var h: float = natural_height(net, terrain, src, world)
			if is_nan(h):
				heights[j * nx + i] = NAN
				misses += 1
				continue
			heights[j * nx + i] = (from_world * Vector3(world.x, h, world.z)).y
			hits += 1
	var header := {"schema_ver": SCHEMA_VER, "origin": [snappedf(rect.position.x, 0.000001), snappedf(rect.position.y, 0.000001)],
			"step": step, "nx": nx, "ny": ny}
	return {"ok": hits > 0, "header": header, "heights": heights, "hits": hits, "misses": misses,
			"message": "ground grid %dx%d at %.1f m: %d sample(s), %d off the terrain%s" % [nx, ny, step, hits, misses, "" if src.is_empty() else " (stamped: the previous sidecar is the natural ground where it covers)"]}

## Writes `<stem>.ground.json` + `<stem>.ground.bin` beside the record. Returns the JSON path, "" on failure.
static func write_sidecar(record_path: String, grid: Dictionary) -> String:
	var json_path := sidecar_path(record_path)
	var bin_path := json_path.get_basename() + ".bin"
	var header: Dictionary = grid["header"].duplicate()
	header["bin"] = bin_path.get_file()
	var fb := FileAccess.open(bin_path, FileAccess.WRITE)
	if fb == null:
		return ""
	fb.big_endian = false
	fb.store_buffer((grid["heights"] as PackedFloat32Array).to_byte_array())
	fb.close()
	var fj := FileAccess.open(json_path, FileAccess.WRITE)
	if fj == null:
		return ""
	fj.store_string(JSON.stringify(header, " ", true) + "\n")
	fj.close()
	return json_path

## Sample + write in one call, for the dock and the headless tool alike.
static func write_for(net: Node3D, terrain: Node) -> Dictionary:
	var grid := sample_grid(net, terrain)
	if not grid["ok"]:
		return {"ok": false, "message": grid["message"], "path": ""}
	var path := write_sidecar(net.record_path, grid)
	return {"ok": path != "", "path": path, "message": grid["message"] + ("" if path != "" else " -- could not write the sidecar")}

static func _world_xf(n: Node) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur := n
	while cur != null:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf
