extends SceneTree
## PLAN.md 3.1 B7 gate: the roads are written into Terrain3D, and the result carries them.
##   godot --headless --path . --script tools/godot/probe_road_stamp.gd [-- <scene.tscn> <network>]
##
## Reads the terrain AS SAVED (after `stamp_roadkit_terrain.gd`) against the network's NATURAL ground
## (its ground sidecar) and every built lane, sampled every 4 m:
##   1. no ground stands proud of a road (terrain <= lane + tolerance) -- on every lane and on the
##      pad MESH (a turn path is not the pad's surface: it is not swept on the pad's IDW heights);
##   2. every lane sample the kit would call FILL (0.4-4 m over the natural ground) is now CARRIED:
##      by the kit's own rule it is AT GRADE on the stamped ground (within `AT_GRADE_TOL`, 0.40 m) --
##      a lane the kit put on piers (nearest corridor point PIER) is the bridge's, gated by B6b;
##   3. a bridge still stands over open ground: most clear-PIER samples see the natural ground below;
##   4. stamping again changes NOTHING (idempotent -- every height is derived from the natural ground);
##   5. restoring puts the natural ground back exactly;
## with a CONTROL: the natural ground fails (2). Steps 4-5 run in memory and are never saved.
##
## A terrain carrying a city's BLOCK GROUND (`urban_paint.marker` + `urban_block.layer`, laid after the stamp by
## `tools/island_world.sh`'s ground stage) is judged as the pipeline built it: 4 re-stamps WITH the layer over it,
## and 5 compares only the vertices the layer does not own (the restore is the stamp's, the block ground is not).

const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const Stamp := preload("res://addons/road_kit/road_kit_stamp.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const STEP := 4.0
const AT_GRADE_TOL := 0.40
const FILL_MAX := 4.0
## Ground is never above a lane (the stamp leaves `Stamp.CLEARANCE`, 0.10 m, under it; the 2 m grid's
## interpolation spends part of that), nor more than 0.05 m above a pad mesh vertex.
const PROUD_TOL := 0.0
const PAD_PROUD_TOL := 0.05

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var path := "res://src/main/resources/com/openworld/world/DebugWorld.tscn" if args.size() < 2 else args[0]
	var net_name := "DebugRoads" if args.size() < 2 else args[1]
	var world: Node = (load(path) as PackedScene).instantiate()
	root.add_child(world)
	await process_frame
	await process_frame
	var net: Node3D = null
	for c in world.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript and str(c.name) == net_name:
			net = c
	var terrain: Node = world.find_children("*", "Terrain3D", true, false)[0]
	if net.all_points().is_empty():
		net.load_record()
	var record := Stamp.read_record(net)
	var natural := Ground.load_grid(Ground.sidecar_path(net.record_path))
	check(not record.is_empty() and not natural.is_empty(), "the network is stamped and has its natural ground", Ground.stamp_record_path(net.record_path))
	if record.is_empty() or natural.is_empty():
		_done()
		return
	var to_world := Ground._world_xf(net)
	var from_world := to_world.affine_inverse()
	var nat := func(w: Vector3) -> float:
		var local := from_world * w
		var k := Ground.Frame.to_kit(local)
		var h := Ground.lookup(natural, k.x, k.y)
		return NAN if is_nan(h) else (to_world * Vector3(local.x, h, local.z)).y

	var t0 := Time.get_ticks_msec()
	# Lanes from the pieces, placed as Zone.placeGeometry places them.
	var lanes := []
	var pad_verts := []
	for m in _markers(world):
		var z = m.get("zone")
		if z == null or not str(z.get("geometry_path")).contains("/Roads_"):
			continue
		var inst: Node3D = (load(str(z.get("geometry_path"))) as PackedScene).instantiate()
		var xf: Transform3D = z.get("geometry_world_transform") if z.get("geometry_world_placed") else (m as Node3D).global_transform
		for p3 in inst.find_children("*", "Path3D", true, false):
			var name := str(p3.get_parent().name)
			if name.begins_with("c"):
				continue        # a turn path is not the pad's surface -- the pad mesh is checked below
			lanes.append({"name": name, "curve": p3.curve, "xf": xf * _local_xf(inst, p3)})
		for mi in inst.find_children("*__pad", "MeshInstance3D", true, false):
			var mxf := xf * _local_xf(inst, mi)
			for si in mi.mesh.get_surface_count():
				for v in mi.mesh.surface_get_arrays(si)[Mesh.ARRAY_VERTEX]:
					pad_verts.append(mxf * v)
		inst.free()

	print("  INFO  %d lanes, %d pad vertices loaded in %d ms" % [lanes.size(), pad_verts.size(), Time.get_ticks_msec() - t0])
	t0 = Time.get_ticks_msec()
	var proud := 0
	var proud_pad := 0
	var worst := -INF
	var worst_at := ""
	var fill_n := 0
	var fill_ok := 0
	var fill_ok_natural := 0
	var fill_miss := ""
	var fill_under := 0
	var fill_abut := 0
	var pier_n := 0
	var pier_open := 0
	var n := 0
	for lane in lanes:
		var curve: Curve3D = lane["curve"]
		if curve == null:
			continue
		var d := 0.0
		while d <= curve.get_baked_length():
			var w: Vector3 = lane["xf"] * curve.sample_baked(d)
			d += STEP
			# On the 1 cm grid, as the pad vertices below and for the same reason: a lane sample a few mm off an exact
			# terrain vertex reads the FAR vertex, which on the 10% touge is 0.20 m up the grade (measured: two samples
			# "0.07/0.09 m proud" read 0.097/0.100 m UNDER the lane once snapped, PLAN.md 3.2d).
			var h: float = terrain.data.get_height(Vector3(snappedf(w.x, 0.01), w.y, snappedf(w.z, 0.01)))
			var g: float = nat.call(w)
			if is_nan(h) or is_nan(g):
				continue
			n += 1
			var above := h - w.y
			if above > worst:
				worst = above
				worst_at = "%s (%.1f, %.1f, %.1f)" % [lane["name"], w.x, w.y, w.z]
			if above > PROUD_TOL:
				proud += 1
				if OS.get_environment("PROBE_VERBOSE") != "":
					print("    proud %s (%.1f, %.1f, %.1f) by %.2f" % [lane["name"], w.x, w.y, w.z, above])
			var delta := w.y - g
			# The kit decided the support at the CENTRELINE: a lane beside a cliff edge whose own
			# sample is 3 m over the ground is still on the bridge if the road there is on piers.
			var kind := _kind_near(record, from_world * w)
			if kind == "PAD":
				continue        # over a junction pad: the pad MESH is what is checked
			if kind == "PIER":
				if delta > FILL_MAX + 2.0:
					pier_n += 1
					pier_open += 1 if absf(h - g) < 0.05 else 0
				continue
			if delta > AT_GRADE_TOL and delta <= FILL_MAX:
				if _over_lower_road(from_world * w, (from_world * w).y):
					fill_under += 1
					continue
				if _near_kind(from_world * w, "PIER", ABUTMENT_REACH):
					fill_abut += 1
					continue
				fill_n += 1
				if w.y - h <= AT_GRADE_TOL:
					fill_ok += 1
				else:
					if OS.get_environment("PROBE_VERBOSE") != "":
						var pv := Vector3(INF, INF, INF)
						for v in pad_verts:
							if Vector2(v.x - w.x, v.z - w.z).length() < Vector2(pv.x - w.x, pv.z - w.z).length():
								pv = v
						print("    fill miss %s (%.1f, %.1f, %.1f) %.2f over stamped, natural delta %.2f, kind %s; nearest pad vertex %.1f m away at y %.2f" % [lane["name"], w.x, w.y, w.z, w.y - h, delta, kind, Vector2(pv.x - w.x, pv.z - w.z).length(), pv.y])
					if fill_miss == "":
						fill_miss = "%s (%.1f, %.1f, %.1f) %.2f m over the stamped ground" % [lane["name"], w.x, w.y, w.z, w.y - h]
				fill_ok_natural += 1 if delta <= AT_GRADE_TOL else 0
	for v in pad_verts:
		# Queried on a 1 cm grid: a pad vertex placed through the piece's transform lands a fraction of a
		# millimetre off an exact terrain vertex, and Terrain3D's `get_height` a hair inside a cell edge
		# returns the FAR vertex's height (measured: (-150.0006, 72.0) read 11.09, the (-152, 72) vertex,
		# where (-150, 72) is 10.97 and (-150.1, 71.9) 10.98). B12's 1.5 m pad grid shares a vertex with the
		# 2 m terrain grid every 6 m, which is what turned that into 6 false "proud" pad vertices.
		var h: float = terrain.data.get_height(Vector3(snappedf(v.x, 0.01), v.y, snappedf(v.z, 0.01)))
		if not is_nan(h) and h - v.y > PAD_PROUD_TOL:
			proud_pad += 1
			if h - v.y > worst:
				worst = h - v.y
				worst_at = "pad vertex (%.1f, %.1f, %.1f)" % [v.x, v.y, v.z]
	print("  %d lane samples, %d pad vertices, %d FILL, %d clear PIER (%d ms)" % [n, pad_verts.size(), fill_n, pier_n, Time.get_ticks_msec() - t0])
	print("  INFO  %d FILL-height samples stand over a road more than %.1f m below (carried by that road's cap, not judged)" % [fill_under, Stamp.UNDERPASS])
	print("  INFO  %d FILL-height samples are ABUTMENTS (a PIER corridor point within %.0f m: the fill batter ends there, the lane stays above the ground)" % [fill_abut, ABUTMENT_REACH])
	t0 = Time.get_ticks_msec()
	check(proud == 0 and proud_pad == 0, "no ground proud of a road (%.2f m lanes, %.2f m pad mesh)" % [PROUD_TOL, PAD_PROUD_TOL], "%d + %d, highest %.3f m at %s" % [proud, proud_pad, worst, worst_at])
	check(fill_n > 0 and fill_ok == fill_n, "every FILL sample is carried (at grade, within %.2f m)" % AT_GRADE_TOL, "%d/%d %s" % [fill_ok, fill_n, fill_miss])
	check(fill_ok_natural < fill_n, "CONTROL: the natural ground does not carry them", "%d/%d" % [fill_ok_natural, fill_n])
	check(pier_n > 0 and pier_open >= int(ceil(pier_n * 0.8)), ">= 80% of clear PIER samples still span the natural ground", "%d/%d" % [pier_open, pier_n])

	# Where the fill went: a histogram of raise, so a wall would be visible as a number.
	var raised := [0, 0, 0, 0]
	var spacing := float(terrain.get("vertex_spacing"))
	var hs: Dictionary = natural["header"]
	for j in int(hs["ny"]):
		for i in int(hs["nx"]):
			var k := Vector3(float(hs["origin"][0]) + i * float(hs["step"]), float(hs["origin"][1]) + j * float(hs["step"]), 0.0)
			var w: Vector3 = to_world * Ground.Frame.to_godot(k)
			# On the 1 cm grid, as the pad vertices below and for the same reason: a lane sample a few mm off an exact
			# terrain vertex reads the FAR vertex, which on the 10% touge is 0.20 m up the grade (measured: two samples
			# "0.07/0.09 m proud" read 0.097/0.100 m UNDER the lane once snapped, PLAN.md 3.2d).
			var h: float = terrain.data.get_height(Vector3(snappedf(w.x, 0.01), w.y, snappedf(w.z, 0.01)))
			var g: float = nat.call(w)
			if is_nan(h) or is_nan(g):
				continue
			var r := h - g
			if r > 0.5:
				raised[0 if r <= 4.0 else (1 if r <= 8.0 else (2 if r <= 16.0 else 3))] += 1
	print("  INFO  raised vertices: <=4 m %d, 4-8 m %d, 8-16 m %d, >16 m %d (%d ms)" % (raised + [Time.get_ticks_msec() - t0]))
	t0 = Time.get_ticks_msec()

	# 4 + 5: in memory only.
	var corr := Service.run("corridors", net.record_path, ["--ground", ProjectSettings.globalize_path(Ground.sidecar_path(net.record_path))])
	var layer := Stamp.load_layer(terrain) if Stamp.has_block_layer(terrain) else {}
	if Stamp.has_block_layer(terrain):
		check(not layer.is_empty(), "the block ground carries its layer (%s)" % Stamp.URBAN_LAYER,
				"%d vertices" % int(layer.get("count", 0)))
	var again := Stamp.stamp(net, terrain, corr, record.get("corridors", []), false, layer)
	check(again["ok"] and again["changed"] == 0, "stamping again changes nothing", again["message"])
	print("  INFO  corridors + re-stamp %d ms" % (Time.get_ticks_msec() - t0))
	t0 = Time.get_ticks_msec()
	var back := Stamp.stamp(net, terrain, {}, record.get("corridors", []), true)
	var worst_back := 0.0
	for j in range(0, int(hs["ny"]), 3):
		for i in range(0, int(hs["nx"]), 3):
			var k := Vector3(float(hs["origin"][0]) + i * float(hs["step"]), float(hs["origin"][1]) + j * float(hs["step"]), 0.0)
			var w: Vector3 = to_world * Ground.Frame.to_godot(k)
			# On the 1 cm grid, as the pad vertices below and for the same reason: a lane sample a few mm off an exact
			# terrain vertex reads the FAR vertex, which on the 10% touge is 0.20 m up the grade (measured: two samples
			# "0.07/0.09 m proud" read 0.097/0.100 m UNDER the lane once snapped, PLAN.md 3.2d).
			if not layer.is_empty() and not is_nan(Stamp.layer_height(layer, w.x, w.z)):
				continue        # the block ground's vertex, not the stamp's
			var h: float = terrain.data.get_height(Vector3(snappedf(w.x, 0.01), w.y, snappedf(w.z, 0.01)))
			var g: float = nat.call(w)
			if not is_nan(h) and not is_nan(g):
				worst_back = maxf(worst_back, absf(h - g))
	# within the stamp's own change threshold: a vertex nearer its target than CHANGE_TOL is left (a float32 round trip)
	check(back["ok"] and worst_back <= Stamp.CHANGE_TOL + 1e-4, "restore puts the natural ground back", "%s; worst %.4f m" % [back["message"], worst_back])
	_done()

## The kit's support kind at the corridor point nearest `local` (network frame, Godot axes), or "PAD"
## when that point is on a junction pad. Through a 32 m bucket index built once: a scan of every corridor
## point per lane sample took the island (58 k points x 70 k samples) past 50 minutes.
const KIND_CELL := 32.0
## The stamp decides fill per corridor point (the NEARER end of a segment), so a lane sample the kit calls FILL within
## one corridor spacing of a PIER point is an abutment: the batter ends under it.
const ABUTMENT_REACH := 6.0

func _near_kind(local: Vector3, kind: String, reach: float) -> bool:
	var cx := int(floor(local.x / KIND_CELL))
	var cz := int(floor(local.z / KIND_CELL))
	for i in range(cx - 1, cx + 2):
		for j in range(cz - 1, cz + 2):
			for q in _kind_index.get(Vector2i(i, j), []):
				if q[2] == kind and Vector2(q[0] - local.x, q[1] - local.z).length() <= reach:
					return true
	return false
var _kind_index := {}

func _kind_near(record: Dictionary, local: Vector3) -> String:
	if _kind_index.is_empty():
		for c in record.get("corridors", []):
			var pad := str(c.get("owner", "")).begins_with("JCT:")
			for p in c["points"]:
				var key := Vector2i(int(floor(float(p[0]) / KIND_CELL)), int(floor(float(p[2]) / KIND_CELL)))
				if not _kind_index.has(key):
					_kind_index[key] = []
				_kind_index[key].append([float(p[0]), float(p[2]), "PAD" if pad else str(p[5]), float(p[1]), float(p[3])])
	var cx := int(floor(local.x / KIND_CELL))
	var cz := int(floor(local.z / KIND_CELL))
	var best := INF
	var kind := ""
	for r in range(1, 12):
		for i in range(cx - r, cx + r + 1):
			for j in range(cz - r, cz + r + 1):
				for q in _kind_index.get(Vector2i(i, j), []):
					var d: float = Vector2(q[0] - local.x, q[1] - local.z).length_squared()
					if d < best:
						best = d
						kind = q[2]
		# every cell within r of this one is searched: a nearer point cannot lie farther than (r - 1) cells out
		if best < pow((r - 1) * KIND_CELL, 2) or (r == 11 and kind != ""):
			break
	return kind


## True when a road more than `Stamp.UNDERPASS` BELOW `y` has its paved band within one terrain cell of `local`: the
## stamp caps the ground there to the lower road (a ramp or deck crossing a street), which is right, and a FILL
## sample above it is not the fill's to carry. The ramp over a street reads exactly like an unfilled embankment.
func _over_lower_road(local: Vector3, y: float) -> bool:
	var cx := int(floor(local.x / KIND_CELL))
	var cz := int(floor(local.z / KIND_CELL))
	for i in range(cx - 1, cx + 2):
		for j in range(cz - 1, cz + 2):
			for q in _kind_index.get(Vector2i(i, j), []):
				if q[3] < y - Stamp.UNDERPASS and Vector2(q[0] - local.x, q[1] - local.z).length() <= q[4] + 2.0:
					return true
	return false


func _done() -> void:
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)

func _local_xf(root_node: Node3D, n: Node) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur := n
	while cur != null and cur != root_node:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf

func _markers(n: Node) -> Array:
	var out := []
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("ZoneMarker.java"):
		out.append(n)
	for c in n.get_children():
		out.append_array(_markers(c))
	return out
