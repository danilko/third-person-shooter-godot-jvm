@tool
extends MeshInstance3D
## Editor-only preview of a RoadKitNetwork: the solver's RESOLVED centrelines (what Build will
## sweep, from `roadkit_cli.py centrelines`) plus every link as a straight line coloured by type.
## Never saved (owner stays null); the plugin re-creates it.
##
## B6c: with zones, each run is coloured by the zone `point_zones` cuts it into (white = the resident
## piece, which no marker streams), a run or pad past its zone's load radius gets an ORANGE second
## strip above it, every successor edge that leaves its lane's zone is drawn in MAGENTA, and each
## ZoneMarker's box and load/unload rings are drawn in its zone's colour. All in the network's frame,
## which is this node's parent.

const Zones := preload("res://addons/road_kit/road_kit_zones.gd")
const COLORS := {"SEGMENT": Color(0.3, 0.9, 0.3), "JUNCTION": Color(1.0, 0.85, 0.1), "AUX": Color(0.2, 0.8, 1.0)}
const BEYOND := Color(1.0, 0.5, 0.1)
const CROSS := Color(1.0, 0.2, 0.9)
const RING_SEGMENTS := 72

## Zone id -> colour: evenly spaced hues over the ids in sorted order, so the same scene draws the same
## colours every time. "" (resident) is white.
static func zone_colors(ids: Array) -> Dictionary:
	var sorted := ids.duplicate()
	sorted.sort()
	var out := {"": Color(1, 1, 1)}
	for i in sorted.size():
		out[sorted[i]] = Color.from_hsv(fmod(0.33 + float(i) / maxf(1.0, sorted.size()), 1.0), 0.75, 1.0)
	return out

## `data` is the CLI's `centrelines` object (`runs`, and with `--zones` also `pads` and `cross`);
## `markers` the scene's ZoneMarkers. Returns `{"runs", "zones", "cross", "beyond"}` counts drawn.
func redraw(net: Node, data, markers: Array = []) -> Dictionary:
	var runs: Array = data if data is Array else data.get("runs", [])
	var extra: Dictionary = {} if data is Array else data
	var im := ImmediateMesh.new()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.no_depth_test = true
	var ids := []
	for m in markers:
		var z = m.get("zone")
		if z != null and str(z.get("zone_id")) != "" and not ids.has(str(z.get("zone_id"))):
			ids.append(str(z.get("zone_id")))
	for r in runs:
		if r.has("zone") and str(r["zone"]) != "" and not ids.has(str(r["zone"])):
			ids.append(str(r["zone"]))
	var palette := zone_colors(ids)
	var counts := {"runs": 0, "zones": 0, "cross": 0, "beyond": 0}
	for run in runs:
		var pts: Array = run.get("points", [])
		if pts.size() < 2:
			continue
		var col: Color = palette.get(str(run.get("zone", "")), Color(1, 1, 1))
		_strip(im, mat, pts, col, 0.3)
		counts["runs"] += 1
		if run.get("beyond", false):
			_strip(im, mat, pts, BEYOND, 1.4)
			counts["beyond"] += 1
	for pad in extra.get("pads", []):
		var c: Array = pad["centre"]
		var col: Color = BEYOND if pad.get("beyond", false) else palette.get(str(pad["zone"]), Color(1, 1, 1))
		_cross_mark(im, mat, Vector3(c[0], c[1] + 0.3, c[2]), 6.0, col)
		counts["beyond"] += 1 if pad.get("beyond", false) else 0
	for edge in extra.get("cross", []):
		var pts: Array = edge.get("points", [])
		if pts.size() >= 2:
			_strip(im, mat, pts, CROSS, 1.0)
			counts["cross"] += 1
	var by_uid := {}
	for p in net.all_points():
		by_uid[p.uid] = p
	var drawn := {}
	for p in net.all_points():
		for l in p.links:
			var q = by_uid.get(l["target"])
			if q == null:
				continue
			var key := [p.uid, q.uid] if p.uid < q.uid else [q.uid, p.uid]
			if drawn.has(str(key) + l["type"]):
				continue
			drawn[str(key) + l["type"]] = true
			im.surface_begin(Mesh.PRIMITIVE_LINES, mat)
			im.surface_set_color(COLORS.get(l["type"], Color.WHITE))
			im.surface_add_vertex(p.network_transform().origin + Vector3.UP * 0.6)
			im.surface_set_color(COLORS.get(l["type"], Color.WHITE))
			im.surface_add_vertex(q.network_transform().origin + Vector3.UP * 0.6)
			im.surface_end()
	# Zones: world -> this network's frame.
	var net_inv: Transform3D = Zones.world_xf(net).affine_inverse()
	for m in markers:
		var zone = m.get("zone")
		if zone == null:
			continue
		var col: Color = palette.get(str(zone.get("zone_id")), Color(1, 1, 1))
		var mw: Transform3D = Zones.world_xf(m)
		var c: Vector3 = mw.origin
		var size: Vector3 = zone.get("size")
		_box(im, mat, net_inv, c, size * 0.5, col)
		for radius in [float(zone.get("load_radius")), float(zone.get("unload_radius"))]:
			if radius > 0.0:
				_ring(im, mat, net_inv, c, radius, col.darkened(0.35 if radius == float(zone.get("unload_radius")) else 0.0))
		counts["zones"] += 1
	mesh = im
	return counts

func _strip(im: ImmediateMesh, mat: Material, pts: Array, col: Color, lift: float) -> void:
	im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, mat)
	for p in pts:
		im.surface_set_color(col)
		im.surface_add_vertex(Vector3(p[0], p[1] + lift, p[2]))
	im.surface_end()

func _cross_mark(im: ImmediateMesh, mat: Material, c: Vector3, r: float, col: Color) -> void:
	im.surface_begin(Mesh.PRIMITIVE_LINES, mat)
	for d in [Vector3(r, 0, 0), Vector3(0, 0, r)]:
		im.surface_set_color(col)
		im.surface_add_vertex(c - d)
		im.surface_set_color(col)
		im.surface_add_vertex(c + d)
	im.surface_end()

func _box(im: ImmediateMesh, mat: Material, xf: Transform3D, c: Vector3, h: Vector3, col: Color) -> void:
	var corners := []
	for sx in [-1, 1]:
		for sy in [-1, 1]:
			for sz in [-1, 1]:
				corners.append(xf * (c + Vector3(h.x * sx, h.y * sy, h.z * sz)))
	im.surface_begin(Mesh.PRIMITIVE_LINES, mat)
	for i in 8:
		for bit in [1, 2, 4]:
			var j: int = i | bit
			if j != i:
				im.surface_set_color(col)
				im.surface_add_vertex(corners[i])
				im.surface_set_color(col)
				im.surface_add_vertex(corners[j])
	im.surface_end()

func _ring(im: ImmediateMesh, mat: Material, xf: Transform3D, c: Vector3, radius: float, col: Color) -> void:
	im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, mat)
	for i in RING_SEGMENTS + 1:
		var a := TAU * i / RING_SEGMENTS
		im.surface_set_color(col)
		im.surface_add_vertex(xf * (c + Vector3(cos(a) * radius, 0.0, sin(a) * radius)))
	im.surface_end()
