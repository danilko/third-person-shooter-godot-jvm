extends SceneTree
## shot_coast_road.gd -- pictures of the north-west coast road's rock sheds (PLAN.md 3.15). Needs a DISPLAY.
##
##   godot --path . --script tools/godot/shot_coast_road.gd -- <out_dir>
##
## World.tscn's terrain, sea and sky with nothing that streams or simulates, plus every IslandRoads piece that carries a
## shed, placed at the network's frame. For each shed span (the `shed` stations of `kaigan_dori*` in the record): a
## driver's view along the road inside it, a view from the sea at the open side, and one from above. Writes
## <out_dir>/shed<n>_{inside,sea,above}.png.

const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const RECORD := "res://assets/world_source/pieces/IslandRoads.roads.json"
const PIECES := "res://src/main/resources/com/openworld/world/pieces/"
const DROP := ["Characters", "VehicleRoot", "DebugHarness", "Pickups", "RoadZones", "TrafficZones", "SiteZones",
		"AmmoRefill", "WorldSystems", "IslandRoads"]

var _out := ""

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	_out = a[0] if a.size() > 0 else "user://coast_shots"
	DirAccess.make_dir_recursive_absolute(_out)
	root.size = Vector2i(1600, 900)
	_run.call_deferred()

func _net_y() -> float:
	return 0.6

## [[a, b, open side], ...] Godot positions of each shed span's first and last shed station along its road.
func _spans() -> Array:
	var rec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(RECORD))
	var pts := {}
	for p in rec["points"]:
		pts[p["uid"]] = p
	var out := []
	for r in rec["roads"]:
		if not str(r["name"]).begins_with("kaigan_dori"):
			continue
		var cur := []
		var side := ""
		for u in r["points"] + [""]:
			var p = pts.get(u)
			var s: String = str(p.get("shed", "NONE")) if p != null else "NONE"
			if s != "NONE":
				cur.append(p["pos"])
				side = s
			elif cur.size() > 0:
				if p != null:
					cur.append(p["pos"])
				if cur.size() >= 2:
					out.append([_g(cur[0]), _g(cur[cur.size() - 1]), side, _g(cur[cur.size() / 2])])
				cur = []
	return out

func _g(k: Array) -> Vector3:
	return Vector3(float(k[0]), float(k[2]) + _net_y(), -float(k[1]))

func _run() -> void:
	var world: Node = (load(WORLD) as PackedScene).instantiate()
	for n in DROP:
		var c := world.get_node_or_null(n)
		if c != null:
			world.remove_child(c)
			c.free()
	root.add_child(world)
	var d := DirAccess.open(PIECES)
	for f in d.get_files():
		if f.begins_with("Roads_IslandRoads_island_") and f.ends_with(".gltf"):
			if FileAccess.get_file_as_string(PIECES + f).find("__shed") < 0:
				continue
			var scn := f.get_basename() + ".tscn"
			var ps: PackedScene = load(PIECES + scn)
			var inst := ps.instantiate() as Node3D
			inst.position = Vector3(0, _net_y(), 0)
			world.add_child(inst)
	var cam := Camera3D.new()
	cam.far = 6000.0
	cam.fov = 70.0
	world.add_child(cam)
	cam.make_current()
	for i in 40:
		await process_frame
	var spans := _spans()
	print("shot_coast_road: %d shed span(s)" % spans.size())
	for i in spans.size():
		var a: Vector3 = spans[i][0]
		var b: Vector3 = spans[i][1]
		var mid: Vector3 = spans[i][3]
		var fwd := (b - a)
		fwd.y = 0.0
		fwd = fwd.normalized()
		var right := fwd.cross(Vector3.UP)          # Godot: right of travel
		var open_right: bool = spans[i][2] == "OPEN_RIGHT"
		var sea := right if open_right else -right
		var views := {
			"inside": [mid - fwd * 40.0 + sea * 2.0 + Vector3.UP * 1.6, mid + fwd * 20.0 + Vector3.UP * 1.2],
			"entry": [a - fwd * 70.0 + sea * 2.0 + Vector3.UP * 1.6, a + Vector3.UP * 3.0],
			"sea": [mid + sea * 90.0 + fwd * -30.0 + Vector3.UP * 6.0, mid + Vector3.UP * 4.0],
			"above": [mid + sea * 120.0 + Vector3.UP * 110.0, mid],
		}
		for k in views:
			cam.look_at_from_position(views[k][0], views[k][1])
			for f in 6:
				await process_frame
			RenderingServer.force_draw()
			await process_frame
			var img := root.get_texture().get_image()
			var path := "%s/shed%d_%s.png" % [_out, i, k]
			img.save_png(path)
			print("  wrote " + path)
	quit(0)
