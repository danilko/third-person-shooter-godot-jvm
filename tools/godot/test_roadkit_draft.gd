extends SceneTree
## PLAN.md 3.1 B10.1 gate: the editor's DRAFT SURFACE is the geometry Build sweeps.
##   godot --headless --path . --script tools/godot/test_roadkit_draft.gd
##
## On DebugWorld's DebugRoads network: `roadkit_cli.py bands` answers inside the 300 ms budget; every
## tarmac and pad vertex of the draft lies (8 cm) on a tarmac triangle of the BUILT pieces
## `Roads_DebugRoads_debug_a/_b` -- the draft is Build's footprint, not a second road model; draft and
## build agree on whether each lane point of those pieces stands on paving, and every one of them DOES
## (B10.0b); every run-end vertex of the draft lies on the build too (B10.0b); the overlay uploads it; and
## a save writes none of it. CONTROL: the same draft from a copy of the record with one station moved 10 m no longer matches
## the build, so the parity check can see a draft that is not the build.

const Service := preload("res://addons/road_kit/road_kit_service.gd")
const Zones := preload("res://addons/road_kit/road_kit_zones.gd")
const OverlayScript := preload("res://addons/road_kit/road_kit_overlay.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const PIECES := ["res://src/main/resources/com/openworld/world/pieces/Roads_DebugRoads_debug_a.tscn",
		"res://src/main/resources/com/openworld/world/pieces/Roads_DebugRoads_debug_b.tscn"]
## Draft vertex -> built tarmac. Not 2 cm: the build's Geometry Nodes sweep lays each cross-section in
## the CURVE's own frame, which drifts from the solver's per-sample normal on a grade -- measured worst
## 0.067 m on DebugRoads' hillside loop, invisible in a preview.
const TOL := 0.08
## `point_build`'s SUFFIX_SURFACE / SUFFIX_PAD / SUFFIX_GORE mesh objects.
const TARMAC := ["__surface", "__pad", "__gore"]
const CELL := 4.0
## A lane point stands on paving within this of the surface (a turn path is a curve over a planar pad).
const LANE_TOL := 0.25
## A lane point this close (XZ) to a run end whose built sweep is off the draft is that finding, not a
## disagreement of its own.
const SEAM_REACH := 8.0

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-66s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

## Every TARMAC triangle of the built pieces, in the piece root's frame (= the network's frame, which is
## where `Zone.placeGeometry` puts a world-placed road piece), hashed by XZ cell for a near lookup. And
## every lane point, every 4 m, into `lanes`.
func _built_triangles(lanes: Array) -> Dictionary:
	var grid := {}
	for path in PIECES:
		var root: Node3D = (load(path) as PackedScene).instantiate()
		for mi in root.find_children("*", "MeshInstance3D", true, false):
			# The TARMAC only -- a kerb face or a collision proxy beside a lane is not paving.
			if not TARMAC.any(func(sfx): return String(mi.name).ends_with(sfx)):
				continue
			var xf := _rel(root, mi)
			for s in mi.mesh.get_surface_count():
				var arr: Array = mi.mesh.surface_get_arrays(s)
				var vs: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
				var idx = arr[Mesh.ARRAY_INDEX]
				var n: int = idx.size() if idx != null else vs.size()
				for t in range(0, n - 2, 3):
					var a: Vector3 = xf * vs[idx[t] if idx != null else t]
					var b: Vector3 = xf * vs[idx[t + 1] if idx != null else t + 1]
					var c: Vector3 = xf * vs[idx[t + 2] if idx != null else t + 2]
					_hash_tri(grid, PackedVector3Array([a, b, c]))
		for p3 in root.find_children("*", "Path3D", true, false):
			var xf := _rel(root, p3)
			var c: Curve3D = p3.curve
			var L := c.get_baked_length()
			var d := 0.0
			while d <= L:
				lanes.append(xf * c.sample_baked(d))
				d += 4.0
		root.free()
	return grid

func _hash_tri(grid: Dictionary, tri: PackedVector3Array) -> void:
	var lo := Vector2(minf(tri[0].x, minf(tri[1].x, tri[2].x)), minf(tri[0].z, minf(tri[1].z, tri[2].z)))
	var hi := Vector2(maxf(tri[0].x, maxf(tri[1].x, tri[2].x)), maxf(tri[0].z, maxf(tri[1].z, tri[2].z)))
	for gx in range(floori((lo.x - TOL) / CELL), floori((hi.x + TOL) / CELL) + 1):
		for gz in range(floori((lo.y - TOL) / CELL), floori((hi.y + TOL) / CELL) + 1):
			var k := Vector2i(gx, gz)
			if not grid.has(k):
				grid[k] = []
			grid[k].append(tri)

## Distance from `p` to the nearest hashed triangle (INF when none shares its cell).
func _dist(grid: Dictionary, p: Vector3) -> float:
	var best := INF
	for tri in grid.get(Vector2i(floori(p.x / CELL), floori(p.z / CELL)), []):
		# `if d < best`, never `minf`: a degenerate built triangle answers NaN, and `minf(0.0, NaN)` is
		# NaN -- it silently threw away an exact hit.
		var d := p.distance_to(_closest_on_tri(p, tri[0], tri[1], tri[2]))
		if d < best:
			best = d
	return best

## Ericson, Real-Time Collision Detection 5.1.5.
static func _closest_on_tri(p: Vector3, a: Vector3, b: Vector3, c: Vector3) -> Vector3:
	var ab := b - a
	var ac := c - a
	var ap := p - a
	var d1 := ab.dot(ap)
	var d2 := ac.dot(ap)
	if d1 <= 0.0 and d2 <= 0.0:
		return a
	var bp := p - b
	var d3 := ab.dot(bp)
	var d4 := ac.dot(bp)
	if d3 >= 0.0 and d4 <= d3:
		return b
	var vc := d1 * d4 - d3 * d2
	if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
		return a + ab * (d1 / (d1 - d3))
	var cp := p - c
	var d5 := ab.dot(cp)
	var d6 := ac.dot(cp)
	if d6 >= 0.0 and d5 <= d6:
		return c
	var vb := d5 * d2 - d1 * d6
	if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
		return a + ac * (d2 / (d2 - d6))
	var va := d3 * d6 - d5 * d4
	if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
		return b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)))
	var denom := 1.0 / (va + vb + vc)
	return a + ab * (vb * denom) + ac * (vc * denom)

func _rel(root: Node3D, n: Node3D) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur: Node = n
	while cur != root and cur != null:
		xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf

## `{"on", "total", "worst", "ends", "end_worst"}` over the draft's tarmac + pad vertices: how many lie on
## a built tarmac triangle within TOL. A road run's END cross-section (its first and last edge pair) is
## counted apart, in `ends`/`end_worst`: `Curve to Mesh` cuts a run's end on the carrier's last CHORD
## while the solver (and the pad ring it meets) cut it on the mouth's axis -- `point_build.END_LEAD` gives
## the carrier a lead chord along that axis, so this is asserted, and a seam far off it is its own case.
func _parity(grid: Dictionary, bands: Dictionary) -> Dictionary:
	var ends := {}
	var rf: Array = bands["surface"]["road"]
	for b in bands.get("bands", []):
		if b["kind"] == "road" and int(b["tri_count"]) >= 2:
			var t0 := int(b["tri_start"])
			var t1 := t0 + int(b["tri_count"]) - 1
			for vi in [t0 * 3, t0 * 3 + 1, t1 * 3 + 1, t1 * 3 + 2]:
				ends[Vector3(rf[3 * vi], rf[3 * vi + 1], rf[3 * vi + 2])] = true
	var r := {"on": 0, "total": 0, "worst": 0.0, "ends": 0, "end_worst": 0.0, "bad_ends": []}
	for key in ["road", "pad"]:
		var f: Array = bands["surface"][key]
		for i in range(0, f.size(), 3):
			var d := _dist(grid, Vector3(f[i], f[i + 1], f[i + 2]))
			if key == "road" and ends.has(Vector3(f[i], f[i + 1], f[i + 2])):
				r["ends"] += 1
				r["end_worst"] = maxf(r["end_worst"], d)
				if d > TOL:
					r["bad_ends"].append(Vector3(f[i], f[i + 1], f[i + 2]))
				continue
			r["total"] += 1
			r["on"] += 1 if d <= TOL else 0
			r["worst"] = maxf(r["worst"], d)
	return r

## The draft's triangles, hashed exactly as the build's are, so both sides of a comparison use one measure.
func _draft_triangles(bands: Dictionary) -> Dictionary:
	var grid := {}
	for key in ["road", "pad", "gore"]:
		var f: Array = bands["surface"][key]
		for i in range(0, f.size(), 9):
			_hash_tri(grid, PackedVector3Array([Vector3(f[i], f[i + 1], f[i + 2]),
					Vector3(f[i + 3], f[i + 4], f[i + 5]), Vector3(f[i + 6], f[i + 7], f[i + 8])]))
	return grid

func _initialize() -> void:
	var scene: Node = (load(WORLD) as PackedScene).instantiate()
	var net: Node3D = null
	for c in scene.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript:
			net = c
	check(net != null, "DebugWorld has the DebugRoads network")
	net.load_record()

	var t0 := Time.get_ticks_msec()
	var bands := Service.run("bands", net.record_path)
	var wall := Time.get_ticks_msec() - t0
	check(not bands.get("failed", false), "roadkit_cli bands answers", str(bands.get("error", "")))
	check(wall < 300, "bands on DebugRoads inside the 300 ms budget", "%d ms wall (solve %.1f ms)" % [wall, float(bands.get("ms", -1))])
	var counts: Dictionary = bands.get("counts", {})
	check(counts.get("roads", 0) == 4 and counts.get("pads", 0) == 2, "4 runs and 2 pads solved", str(counts))

	var lanes := []
	var grid := _built_triangles(lanes)
	var par := _parity(grid, bands)
	check(par["total"] > 0 and par["on"] == par["total"], "every draft tarmac/pad vertex lies on the built tarmac (%.0f cm)" % (TOL * 100.0), "%d/%d, worst %.3f m" % [par["on"], par["total"], par["worst"]])
	# B10.0b: the sweep's end frame is the mouth axis (`point_build.END_LEAD`). Before: 0.328 m at junction 1.
	check(par["ends"] > 0 and par["end_worst"] <= TOL, "every run-end vertex lies on the built sweep (%.0f cm)" % (TOL * 100.0), "%d vertices, worst %.3f m" % [par["ends"], par["end_worst"]])
	# Draft and build must AGREE on every lane sample -- whether it stands on paving or not. The ones on
	# NEITHER are a finding about the road (turn paths leaving a pad), reported, not a draft defect.
	var agree := 0
	var seam := 0
	var off := 0
	var dgrid := _draft_triangles(bands)
	for p in lanes:
		var d := _dist(dgrid, p) <= LANE_TOL
		var b := _dist(grid, p) <= LANE_TOL
		if d != b and par["bad_ends"].any(func(e): return Vector2(e.x, e.z).distance_to(Vector2(p.x, p.z)) <= SEAM_REACH):
			seam += 1
			continue
		agree += 1 if d == b else 0
		off += 0 if d else 1
	check(lanes.size() > 0 and agree + seam == lanes.size(), "draft and build agree on every built lane point", "%d/%d agree, %d at a run-end seam" % [agree, lanes.size(), seam])
	# B10.0b: a turn path stays on its pad (`point_solve.contain_turns`) and rides its surface
	# (`turn_path`). Before: 85 of 1781 samples off paving at both junctions.
	check(off == 0, "every built lane point stands on paving (%.2f m)" % LANE_TOL, "%d off" % off)

	var ov: MeshInstance3D = OverlayScript.new()
	ov.name = "_RoadKitOverlay"
	net.add_child(ov)
	# The kit's materials come off the BASE meshes -- here the built pieces themselves.
	var mats := {}
	for path in PIECES:
		var piece: Node = (load(path) as PackedScene).instantiate()
		mats.merge(OverlayScript.materials_from(piece))
		piece.free()
	var dc: Dictionary = ov.draft(bands, mats)
	var draft := ov.get_node_or_null(OverlayScript.DRAFT_NAME) as MeshInstance3D
	var tris := int(bands["surface"]["road"].size() + bands["surface"]["pad"].size() + bands["surface"]["gore"].size()) / 9
	check(draft != null and dc["tris"] == tris and dc["kerb_lines"] == bands["kerbs"].size(), "the overlay uploads every triangle and kerb line", str(dc))
	# DebugRoads has no footway, so two layers (tarmac, kerb lines) -- each with the kit's own material.
	var surf_mats := []
	if draft != null:
		for si in draft.mesh.get_surface_count():
			var m := draft.mesh.surface_get_material(si)
			surf_mats.append(m.resource_name if m != null else "<default>")
	check(dc["materials"] == draft.mesh.get_surface_count() and surf_mats == ["M_Asphalt", "M_LineW"], "the draft wears the kit's materials from the base meshes", str(surf_mats))
	check(draft != null and draft.owner == null, "the draft is unowned")
	var ps := PackedScene.new()
	ps.pack(scene)
	var saved := false
	for i in ps.get_state().get_node_count():
		saved = saved or str(ps.get_state().get_node_path(i)).contains(OverlayScript.DRAFT_NAME)
	check(not saved, "saving the scene does not write the draft")
	ov.clear_draft()
	check(ov.get_node_or_null(OverlayScript.DRAFT_NAME) == null, "turning the draft off removes it")

	# CONTROL: one station moved 10 m, re-solved -- the draft must stop matching the build.
	var copy := "user://test_roadkit_draft.roads.json"
	var rec = JSON.parse_string(FileAccess.get_file_as_string(net.record_path))
	var pts: Array = rec["points"]
	var moved: Dictionary = pts[pts.size() / 2]
	moved["pos"][0] = float(moved["pos"][0]) + 10.0
	var f := FileAccess.open(copy, FileAccess.WRITE)
	f.store_string(JSON.stringify(rec))
	f.close()
	var bad := Service.run("bands", copy)
	var par2 := _parity(grid, bad) if not bad.get("failed", false) else {"on": 0, "total": 0, "worst": 0.0}
	check(par2["total"] > 0 and par2["on"] < par2["total"], "CONTROL: a draft of a moved station no longer matches the build", "%d/%d, worst %.2f m (point %s)" % [par2["on"], par2["total"], par2["worst"], moved["uid"]])

	scene.free()
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
