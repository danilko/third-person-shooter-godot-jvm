extends SceneTree
## PLAN.md 3.1 B6b gate: a built road stands on the REAL ground -- Terrain3D -- not on a lerp of its
## stations' heights.
##
##   godot --headless --path . --script tools/godot/probe_road_ground.gd [-- <scene.tscn>]
##
## Loads the scene (DebugWorld by default) for its Terrain3D, instances every ZoneMarker's road piece
## where `Zone.placeGeometry` puts it, and walks every lane every 4 m. Each sample is classified by
## what the kit's `road_support` would call it against the terrain actually under it:
##   delta = lane height - terrain height;  PIER > FILL_MAX (4.0 m) >= FILL > 0.40 m >= at grade
## and then asked a physical question of the baked meshes (`<road>__surface`, where the GN stack
## sweeps the columns and the embankment):
##   * a PIER sample must have a column foot near it -- a vertex well below the deck that sits ON the
##     terrain (a column standing on a lerped ground ends metres above or below it) -- or be within
##     reach of where the ground comes back up to the deck (the abutment of a span over a cliff edge);
##   * (a FILL sample is only counted: the kit sweeps no embankment, the terrain stamp (B7) carries it);
##   * NO baked vertex under the deck may hang in the air over a pier stretch by more than a column's
##     worth -- i.e. no column stops short of the ground.
## CONTROL: the pieces built WITHOUT a ground sidecar fail it (their supports stand on the stations'
## lerped ground_z), which is what B6b fixed.

const DEFAULT_SCENE := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const STEP := 4.0
const AT_GRADE_TOL := 0.40
const FILL_MAX := 4.0
## A support foot "sits on the terrain" within this. Columns are swept to the sampled ground at the
## CENTRELINE sample, so a cross-slope under a wide deck is the whole allowance.
const FOOT_TOL := 0.75
## How far along/across the road a foot may be from the sample it serves: half of PIER_SPACING (30 m)
## along, plus the deck's half width across.
const PIER_REACH := 18.0
const FILL_REACH := 14.0
const CELL := 6.0

var terrain: Node
var feet := {}          # cell key -> [Vector3] of mesh vertices that sit on the terrain
var below := {}         # cell key -> [Vector3] of every vertex (for the "hanging" check)

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var path := DEFAULT_SCENE if args.is_empty() else args[0]
	var world: Node = (load(path) as PackedScene).instantiate()
	root.add_child(world)
	await process_frame
	await process_frame
	var ts := world.find_children("*", "Terrain3D", true, false)
	if ts.is_empty():
		print("  FAIL  %s has a Terrain3D" % path)
		quit(1)
		return
	terrain = ts[0]
	# The probe places the pieces itself, so the streamed copies ZoneManager may already hold are
	# irrelevant: everything is measured on the probe's own instances.
	var pieces := []
	for m in _markers(world):
		var z = m.get("zone")
		if z == null or str(z.get("geometry_path")) == "" or not str(z.get("geometry_path")).contains("/Roads_"):
			continue
		var inst: Node3D = (load(str(z.get("geometry_path"))) as PackedScene).instantiate()
		inst.name = "Probe_" + str(z.get("zone_id"))
		var xf: Transform3D = z.get("geometry_world_transform") if z.get("geometry_world_placed") else (m as Node3D).global_transform
		root.add_child(inst)
		inst.global_transform = xf
		pieces.append(inst)
	await process_frame
	print("  pieces: ", pieces.map(func(p): return str(p.name)))
	for p in pieces:
		_index_meshes(p)

	var rows := {}      # road -> {"grade", "fill", "pier", "pier_ok", "fill_ok", "worst"}
	var fails := 0
	var worst_pier := ""
	for p in pieces:
		for path3d in p.find_children("*", "Path3D", true, false):
			var lane := str(path3d.get_parent().name)
			if lane.begins_with("c"):        # a junction connector rides the pad, which has no supports
				continue
			var road := lane.substr(0, lane.rfind("_"))
			var curve: Curve3D = path3d.curve
			if curve == null or curve.get_baked_length() < STEP:
				continue
			var r: Dictionary = rows.get(road, {"grade": 0, "fill": 0, "pier": 0, "pier_ok": 0, "fill_ok": 0, "worst": 0.0})
			var d := 0.0
			while d <= curve.get_baked_length():
				var w: Vector3 = path3d.global_transform * curve.sample_baked(d)
				d += STEP
				var h: float = terrain.data.get_height(w)
				if is_nan(h):
					continue
				var delta := w.y - h
				r["worst"] = maxf(r["worst"], delta)
				if delta > FILL_MAX + 0.5:
					r["pier"] += 1
					if _foot_near(w, PIER_REACH, 2.0) or _abutment_near(w, PIER_REACH):
						r["pier_ok"] += 1
					else:
						if worst_pier == "":
							worst_pier = "%s at (%.1f, %.1f, %.1f), %.2f m over the terrain" % [lane, w.x, w.y, w.z, delta]
						if OS.get_environment("PROBE_VERBOSE") != "":
							print("    miss %s d=%.1f (%.1f, %.1f, %.1f) delta %.2f" % [lane, d - STEP, w.x, w.y, w.z, delta])
				elif delta > AT_GRADE_TOL + 0.5 and delta < FILL_MAX - 0.5:
					r["fill"] += 1
					if _foot_near(w, FILL_REACH, 0.3):
						r["fill_ok"] += 1
				elif absf(delta) <= AT_GRADE_TOL:
					r["grade"] += 1
			rows[road] = r
	var total_pier := 0
	var total_pier_ok := 0
	var total_fill := 0
	var total_fill_ok := 0
	for road in rows:
		var r: Dictionary = rows[road]
		print("  %-6s grade %4d  fill %4d (toe on ground %4d)  pier %4d (foot on ground %4d)  highest %.1f m" % [road, r["grade"], r["fill"], r["fill_ok"], r["pier"], r["pier_ok"], r["worst"]])
		total_pier += r["pier"]
		total_pier_ok += r["pier_ok"]
		total_fill += r["fill"]
		total_fill_ok += r["fill_ok"]
	var ok1 := total_pier > 0
	print("  %s  the scene has a stretch over a gap (PIER samples)                 %d" % ["PASS" if ok1 else "FAIL", total_pier])
	var ok2 := total_pier > 0 and total_pier_ok == total_pier
	print("  %s  every PIER sample has a column foot on the terrain within %.0f m   %d/%d%s" % ["PASS" if ok2 else "FAIL", PIER_REACH, total_pier_ok, total_pier, "" if ok2 else "  first miss: " + worst_pier])
	# FILL is reported, not asserted: the kit builds no embankment mesh (`road_support` sizes the toe,
	# nothing sweeps it), so a road 0.4-4 m over the ground is carried by the TERRAIN -- B7's corridor
	# stamp -- and this gate cannot see it yet.
	var ok3 := true
	print("  INFO  FILL samples (0.4-4 m over the ground; embankment is B7's terrain stamp) %d, toe on the terrain %d" % [total_fill, total_fill_ok])
	var hanging := _hanging_feet()
	var ok4: bool = hanging[0] == 0
	print("  %s  no column stops short of the ground (bottom vertex > %.2f m over it) %d  %s" % ["PASS" if ok4 else "FAIL", FOOT_TOL, hanging[0], hanging[1]])
	fails = int(not ok1) + int(not ok2) + int(not ok3) + int(not ok4)
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)

func _markers(n: Node) -> Array:
	var out := []
	var s = n.get_script()
	if s != null and str(s.resource_path).ends_with("ZoneMarker.java"):
		out.append(n)
	for c in n.get_children():
		out.append_array(_markers(c))
	return out

func _key(x: float, z: float) -> Vector2i:
	return Vector2i(int(floor(x / CELL)), int(floor(z / CELL)))

func _index_meshes(piece: Node) -> void:
	for mi in piece.find_children("*__surface*", "MeshInstance3D", true, false):
		var mesh: Mesh = mi.mesh
		if mesh == null:
			continue
		var xf: Transform3D = mi.global_transform
		for s in mesh.get_surface_count():
			var verts: PackedVector3Array = mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]
			for v in verts:
				var w := xf * v
				var h: float = terrain.data.get_height(w)
				if is_nan(h):
					continue
				var k := _key(w.x, w.z)
				if absf(w.y - h) <= FOOT_TOL:
					if not feet.has(k):
						feet[k] = []
					feet[k].append(w)
				if not below.has(k):
					below[k] = []
				below[k].append(Vector4(w.x, w.y, w.z, h))

## A vertex within `reach` (XZ) of `w`, at least `under` metres below it, that sits on the terrain.
func _foot_near(w: Vector3, reach: float, under: float) -> bool:
	var k := _key(w.x, w.z)
	var n := int(ceil(reach / CELL))
	for dx in range(-n, n + 1):
		for dz in range(-n, n + 1):
			for v in feet.get(k + Vector2i(dx, dz), []):
				if v.y < w.y - under and Vector2(v.x - w.x, v.z - w.z).length() <= reach:
					return true
	return false

## The span ends on the ground within `reach`: somewhere that close the terrain comes up to within
## FILL_MAX of the deck. A pier stretch starting at a cliff edge is carried by that edge (the
## abutment), and the first column stands up to one PIER_SPACING in from it.
func _abutment_near(w: Vector3, reach: float) -> bool:
	var r := -reach
	while r <= reach:
		var q := -reach
		while q <= reach:
			if r * r + q * q <= reach * reach:
				var h: float = terrain.data.get_height(Vector3(w.x + r, 0, w.z + q))
				if not is_nan(h) and h >= w.y - FILL_MAX:
					return true
			q += 2.0
		r += 2.0
	return false

## `[count, first]` -- columns whose lowest vertex is well above the terrain: for every XZ cell that
## holds a vertex more than 3 m below some other vertex of that cell (i.e. a column, not a flat deck),
## the cell's LOWEST vertex must sit on the ground.
func _hanging_feet() -> Array:
	var count := 0
	var first := ""
	for k in below:
		var lo := Vector4(0, INF, 0, 0)
		var hi := -INF
		for v in below[k]:
			if v.y < lo.y:
				lo = v
			hi = maxf(hi, v.y)
		if hi - lo.y < 3.0:
			continue
		if lo.y - lo.w > FOOT_TOL:
			count += 1
			if first == "":
				first = "first at (%.1f, %.1f, %.1f), %.2f m over the terrain" % [lo.x, lo.y, lo.z, lo.y - lo.w]
	return [count, first]
