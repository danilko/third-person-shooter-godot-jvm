@tool
extends MeshInstance3D
## Editor-only preview of a RoadKitNetwork: the solver's RESOLVED centrelines (what Build will
## sweep, from `roadkit_cli.py centrelines`) plus every link as a straight line coloured by type.
## Never saved (owner stays null); the plugin re-creates it.

const COLORS := {"SEGMENT": Color(0.3, 0.9, 0.3), "JUNCTION": Color(1.0, 0.85, 0.1), "AUX": Color(0.2, 0.8, 1.0)}

func redraw(net: Node, runs: Array) -> void:
	var im := ImmediateMesh.new()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.no_depth_test = true
	for run in runs:
		var pts: Array = run.get("points", [])
		if pts.size() < 2:
			continue
		im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, mat)
		for p in pts:
			im.surface_set_color(Color(1, 1, 1))
			im.surface_add_vertex(Vector3(p[0], p[1] + 0.3, p[2]))
		im.surface_end()
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
	mesh = im
