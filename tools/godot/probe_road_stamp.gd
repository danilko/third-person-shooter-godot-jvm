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

const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const Stamp := preload("res://addons/road_kit/road_kit_stamp.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const STEP := 4.0
const AT_GRADE_TOL := 0.40
const FILL_MAX := 4.0
const PROUD_TOL := 0.05
const PAD_PROUD_TOL := 0.15

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

	var proud := 0
	var proud_pad := 0
	var worst := -INF
	var worst_at := ""
	var fill_n := 0
	var fill_ok := 0
	var fill_ok_natural := 0
	var fill_miss := ""
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
			var h: float = terrain.data.get_height(w)
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
		var h: float = terrain.data.get_height(v)
		if not is_nan(h) and h - v.y > PAD_PROUD_TOL:
			proud_pad += 1
			if h - v.y > worst:
				worst = h - v.y
				worst_at = "pad vertex (%.1f, %.1f, %.1f)" % [v.x, v.y, v.z]
	print("  %d lane samples, %d pad vertices, %d FILL, %d clear PIER" % [n, pad_verts.size(), fill_n, pier_n])
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
			var h: float = terrain.data.get_height(w)
			var g: float = nat.call(w)
			if is_nan(h) or is_nan(g):
				continue
			var r := h - g
			if r > 0.5:
				raised[0 if r <= 4.0 else (1 if r <= 8.0 else (2 if r <= 16.0 else 3))] += 1
	print("  INFO  raised vertices: <=4 m %d, 4-8 m %d, 8-16 m %d, >16 m %d" % raised)

	# 4 + 5: in memory only.
	var corr := Service.run("corridors", net.record_path, ["--ground", ProjectSettings.globalize_path(Ground.sidecar_path(net.record_path))])
	var again := Stamp.stamp(net, terrain, corr, record.get("corridors", []))
	check(again["ok"] and again["changed"] == 0, "stamping again changes nothing", again["message"])
	var back := Stamp.stamp(net, terrain, {}, record.get("corridors", []), true)
	var worst_back := 0.0
	for j in range(0, int(hs["ny"]), 3):
		for i in range(0, int(hs["nx"]), 3):
			var k := Vector3(float(hs["origin"][0]) + i * float(hs["step"]), float(hs["origin"][1]) + j * float(hs["step"]), 0.0)
			var w: Vector3 = to_world * Ground.Frame.to_godot(k)
			var h: float = terrain.data.get_height(w)
			var g: float = nat.call(w)
			if not is_nan(h) and not is_nan(g):
				worst_back = maxf(worst_back, absf(h - g))
	check(back["ok"] and worst_back < 0.001, "restore puts the natural ground back", "%s; worst %.4f m" % [back["message"], worst_back])
	_done()

## The kit's support kind at the corridor point nearest `local` (network frame, Godot axes), or "PAD"
## when that point is on a junction pad.
func _kind_near(record: Dictionary, local: Vector3) -> String:
	var best := INF
	var kind := ""
	for c in record.get("corridors", []):
		for p in c["points"]:
			var d := Vector2(p[0] - local.x, p[2] - local.z).length_squared()
			if d < best:
				best = d
				kind = "PAD" if str(c.get("owner", "")).begins_with("JCT:") else str(p[5])
	return kind

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
