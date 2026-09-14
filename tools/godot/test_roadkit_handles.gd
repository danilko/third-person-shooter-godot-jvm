extends SceneTree
## PLAN.md 3.1 B10.4 gate: the intersection handles do what they say, through the SAME functions a drag runs.
##   godot --headless --path . --script tools/godot/test_roadkit_handles.gd
##
## On the kit's sample network, faced by the solver as the editor faces it:
##   * ROTATE JUNCTION turns every mouth about the pad centre, positions and facings, and promotes NO mouth
##     to MANUAL -- CONTROL: the same turn applied to one mouth by hand does promote it;
##   * MOVE JUNCTION moves exactly the clique's mouths by the drag, nothing else;
##   * SETBACK slides a mouth along its own road axis only (0 off the axis line) and locks its setback;
##   * a LANE handle dragged to the edge of n lanes asks for n, and within half a lane either side too;
##   * FILLET reads the drag along the mouth axis as the radius;
##   * MOVE ROAD (B10.5): a dragged road's transform bakes into its points with no MANUAL promotion, and its
##     junction partners on other roads follow;
##   * the network each drag leaves behind still passes the kit's gate with 0 errors, and a drag through the
##     drag the gizmo runs (`road_kit_handles.gd` `drag_to` + `end`) round-trips: cancel restores the record exactly.

const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const Handles := preload("res://addons/road_kit/road_kit_handles.gd")
const Frame := preload("res://addons/road_kit/road_kit_frame.gd")
const SAMPLE := "res://assets/world_source/pieces/RoadKitSample.roads.json"
const SCRATCH := "user://test_roadkit_handles.roads.json"

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-70s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _gate(net: Node) -> int:
	net.save_record(SCRATCH, true)
	var r := Service.run("validate", net.record_path)
	return -1 if r.get("failed", false) else int(r["errors"])

func _initialize() -> void:
	var net: Node3D = NetworkScript.new()
	root.add_child(net)
	net.record_path = SCRATCH
	net.from_record(JSON.parse_string(FileAccess.get_file_as_string(SAMPLE)))
	net.save_record(SCRATCH, true)
	Service.face_network(net)
	var mouth: Node = null
	for p in net.all_points():
		if Gestures.is_mouth(p) and p.fields.get("tangent_mode", "AUTO") == "AUTO":
			mouth = p
			break
	check(mouth != null, "the sample has an AUTO junction mouth")
	var members: Array = Gestures.junction_members(mouth)
	check(members.size() >= 3, "its junction has %d mouths" % members.size())
	check(Handles.ids_for(mouth).size() == 8 and Handles.ids_for(net.all_points().filter(func(p): return not Gestures.is_mouth(p))[0]).size() == 4,
			"a mouth offers 8 handles, a plain station 4")
	var base_errors := _gate(net)
	check(base_errors == 0, "the sample passes the gate before any drag", str(base_errors))
	var before: Dictionary = net.to_record()

	# ── rotate ────────────────────────────────────────────────────────────────────────────────────
	var starts := Gestures.junction_starts(members)
	var centre := Gestures.junction_centre(members)
	var ang := deg_to_rad(25.0)
	Gestures.junction_rotate(members, starts, centre, ang)
	var worst := 0.0
	for m in members:
		var want: Vector3 = centre + Basis(Vector3.UP, ang) * ((starts[m.uid][0] as Transform3D).origin - centre)
		worst = maxf(worst, m.network_transform().origin.distance_to(want))
	var rec: Dictionary = net.to_record()
	var promoted := 0
	for pd in rec["points"]:
		if members.any(func(m): return m.uid == pd["uid"]) and pd.get("tangent_mode", "AUTO") == "MANUAL":
			promoted += 1
	check(worst < 1e-4 and promoted == 0, "ROTATE JUNCTION turns every mouth about the centre, promotes none", "worst %.6f m, %d promoted" % [worst, promoted])
	net.from_record(before)
	Service.face_network(net)
	members = Gestures.junction_members(net.find_point(mouth.uid))
	var one: Node = members[0]
	var xf: Transform3D = one.network_transform()
	one.set_network_transform(Transform3D(Basis(Vector3.UP, ang) * xf.basis, xf.origin))
	check(one.sync_promotion(), "CONTROL: the same turn on one mouth by hand promotes it")
	net.from_record(before)
	Service.face_network(net)
	members = Gestures.junction_members(net.find_point(mouth.uid))
	mouth = net.find_point(mouth.uid)

	# ── move ──────────────────────────────────────────────────────────────────────────────────────
	var others := {}
	for p in net.all_points():
		if not members.has(p):
			others[p.uid] = p.network_transform().origin
	starts = Gestures.junction_starts(members)
	var delta := Vector3(6.0, 0.0, -4.0)
	Gestures.junction_translate(members, starts, delta)
	var moved_ok: bool = members.all(func(m): return m.network_transform().origin.distance_to((starts[m.uid][0] as Transform3D).origin + delta) < 1e-4)
	var still: bool = net.all_points().filter(func(p): return others.has(p.uid)).all(func(p): return p.network_transform().origin.distance_to(others[p.uid]) < 1e-6)
	check(moved_ok and still, "MOVE JUNCTION moves exactly its mouths by the drag")
	var move_errors := _gate(net)
	check(move_errors == 0, "the moved junction still passes the gate", str(move_errors))
	net.from_record(before)
	Service.face_network(net)
	mouth = net.find_point(mouth.uid)

	# ── setback ───────────────────────────────────────────────────────────────────────────────────
	var start: Transform3D = mouth.network_transform()
	Gestures.slide_along_axis(mouth, start, 3.0)
	var axis := -start.basis.z
	axis.y = 0.0
	axis = axis.normalized()
	var d: Vector3 = mouth.network_transform().origin - start.origin
	var off_axis := (d - axis * d.dot(axis)).length()
	check(off_axis < 1e-5 and absf(d.dot(axis) - 3.0) < 1e-5 and mouth.fields["setback_locked"], "SETBACK slides the stop line along its own axis and locks it", "%.6f m off the axis" % off_axis)
	net.from_record(before)
	mouth = net.find_point(mouth.uid)

	# ── lanes ─────────────────────────────────────────────────────────────────────────────────────
	var sec := Gestures.section_of(mouth)
	var lanes_ok := true
	for fwd in [true, false]:
		for n in range(0, 5):
			var edge := Gestures.lane_edge_offset(sec, n, fwd)
			for jitter in [0.0, 0.45 * sec["lane_width"], -0.45 * sec["lane_width"]]:
				if n == 0 and jitter < 0.0:
					continue
				lanes_ok = lanes_ok and Gestures.lanes_for_offset(sec, edge + jitter, fwd) == n
	check(lanes_ok, "a LANE handle at the edge of n lanes (+/- half a lane) asks for n", "lane %.2f m, median %.2f m" % [sec["lane_width"], sec["median_width"]])

	# ── through the drag the gizmo runs (road_kit_handles.gd): fillet, then a rotate drag, both cancelled ───────────────────────────
	var giz = Handles.new()
	if true:
		mouth = net.find_point(mouth.uid)
		var mxf: Transform3D = mouth.network_transform()
		var local_c := mxf.affine_inverse() * Gestures.junction_centre(Gestures.junction_members(mouth))
		var toward := -1.0 if local_c.z < 0.0 else 1.0
		var aim := mxf * Vector3(0.0, 0.0, toward * 11.0)
		giz.drag_to(mouth, Handles.HANDLE_FILLET, aim + Vector3(0, 50, 0), Vector3.DOWN)
		check(absf(float(mouth.fields["fillet_radius"]) - 11.0) < 1e-6, "FILLET reads the drag along the mouth axis", str(mouth.fields["fillet_radius"]))
		giz.end(mouth, Handles.HANDLE_FILLET, true)
		mouth = net.find_point(mouth.uid)
		var c2 := Gestures.junction_centre(Gestures.junction_members(mouth))
		var target := c2 + Basis(Vector3.UP, deg_to_rad(40.0)) * Vector3(Handles.ROTATE_RADIUS, 0, 0)
		giz.drag_to(mouth, Handles.HANDLE_JCT_ROTATE, target + Vector3(0, 30, 0), Vector3.DOWN)
		var turned: bool = mouth.network_transform().origin.distance_to((before_point(before, mouth.uid))) > 0.5
		var rot_errors := _gate(net)
		check(turned and rot_errors == 0, "a ROTATE drag through the gizmo turns the crossing and passes the gate", "%d error(s)" % rot_errors)
		giz.end(mouth, Handles.HANDLE_JCT_ROTATE, true)
		check(net.to_record() == before, "cancelling a drag restores the record exactly")

	# ── B10.5: move a road ─────────────────────────────────────────────────────────────────────────
	net.from_record(before)
	Service.face_network(net)
	mouth = net.find_point(mouth.uid)
	var road: Node3D = mouth.get_parent()
	var starts_pos := {}
	var starts_xf := {}
	for p in net.all_points():
		starts_pos[p.uid] = p.network_transform().origin
	var shift := Transform3D(Basis(Vector3.UP, deg_to_rad(10.0)), Vector3(8.0, 0.0, 5.0))
	road.transform = shift
	for p in road.points():
		starts_xf[p.uid] = p.network_transform()
	check(Gestures.bake_road_transform(road) and road.transform.is_equal_approx(Transform3D.IDENTITY)
			and road.points().all(func(p): return p.network_transform().is_equal_approx(starts_xf[p.uid])),
			"MOVE ROAD: the road's transform is baked into its points (network transforms unchanged)")
	var bake_rec: Dictionary = net.to_record()
	var bake_promoted := 0
	for pd in bake_rec["points"]:
		if road.points().any(func(q): return q.uid == pd["uid"]) and pd.get("tangent_mode", "AUTO") == "MANUAL" \
				and before["points"].any(func(b): return b["uid"] == pd["uid"] and b.get("tangent_mode", "AUTO") == "AUTO"):
			bake_promoted += 1
	check(bake_promoted == 0, "MOVE ROAD: a turned road promotes none of its points", "%d promoted" % bake_promoted)
	var partners: Array = Gestures.junction_members(mouth).filter(func(q): return q.get_parent() != road)
	var n_moved := Gestures.move_junction_partners(net, road, starts_pos)
	var own_delta: Vector3 = mouth.network_transform().origin - starts_pos[mouth.uid]
	var followed: bool = partners.size() > 0 and n_moved >= partners.size()
	for q in partners:
		var dq: Vector3 = q.network_transform().origin - starts_pos[q.uid]
		followed = followed and dq.length() > 1.0
	var bystander_still: bool = net.all_points().filter(func(q): return q.get_parent() != road and not partners.has(q) and not Gestures.is_mouth(q)) \
			.all(func(q): return q.network_transform().origin.distance_to(starts_pos[q.uid]) < 1e-6)
	check(followed and bystander_still, "MOVE ROAD: the road's junction partners follow it, nothing else moves",
			"%d partner(s) moved, mouth moved %.1f m" % [n_moved, own_delta.length()])

	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)

## A point's record position, in the network frame (Godot axes).
func before_point(rec: Dictionary, uid: String) -> Vector3:
	for pd in rec["points"]:
		if pd["uid"] == uid:
			return Frame.to_godot(Frame.from_array(pd["pos"]))
	return Vector3.ZERO
