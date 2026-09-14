extends SceneTree
## PLAN.md 3.1 B8 gate: the remaining authoring gestures, driven exactly as the dock drives them.
##   godot --headless --path . --script tools/godot/test_roadkit_b8.gd
##
## On a scratch copy of the sample network: points are faced along their road by the solver
## (`roadkit_cli.py facings`); ROTATING an AUTO point promotes it to MANUAL and its tangent reaches the
## record while a DRAGGED point stays AUTO (the control); and every record gesture -- Merge Points,
## Split To New Road, Repair Links, Renumber Roads, Tidy Roads, Apply Cross-Section, Branch Ramp Here,
## Flow Report -- goes through `Service.record_gesture`, the path the dock's buttons take. Plus Select
## Junction and the gizmo's handle-drag projection.

const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const G := preload("res://addons/road_kit/road_kit_gestures.gd")
const GizmoScript := preload("res://addons/road_kit/road_kit_gizmo.gd")
const SAMPLE := "res://assets/world_source/pieces/RoadKitSample.roads.json"
const SCRATCH := "user://test_roadkit_b8.roads.json"

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-64s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _fresh() -> Node3D:
	DirAccess.copy_absolute(ProjectSettings.globalize_path(SAMPLE), ProjectSettings.globalize_path(SCRATCH))
	var net: Node3D = NetworkScript.new()
	net.name = "B8"
	root.add_child(net)
	net.record_path = SCRATCH
	net.load_record()
	return net

func _road(net: Node, name: String) -> Node:
	return net.get_node_or_null(NodePath(name))

func _initialize() -> void:
	var net := _fresh()
	var fr := Service.face_network(net)
	var f := Service.run("facings", SCRATCH)
	var worst := 0.0
	var autos := 0
	for p in net.all_points():
		if p.fields["tangent_mode"] == "AUTO" and f["facings"].has(p.uid):
			var want: Array = f["facings"][p.uid]
			worst = maxf(worst, rad_to_deg((-p.network_transform().basis.z).angle_to(Vector3(want[0], want[1], want[2]))))
			autos += 1
	check(autos > 10 and worst < 0.5, "every AUTO point faces along its road (solver facings)", "%d points, worst %.3f deg; %s" % [autos, worst, fr["message"]])

	# The bend gesture, and its control.
	var main: Node = _road(net, "demo_main")
	var turned: Node = main.points()[3]
	var dragged: Node = main.points()[5]
	turned.fields["tangent_mode"] = "AUTO"
	dragged.fields["tangent_mode"] = "AUTO"
	Service.face_network(net)
	turned.rotate_y(deg_to_rad(20.0))
	dragged.position += Vector3(3, 0, 2)
	var rec: Dictionary = net.to_record()
	var by := {}
	for d in rec["points"]:
		by[d["uid"]] = d
	var td: Dictionary = by[turned.uid]
	check(td.get("tangent_mode") == "MANUAL" and td.has("tangent"), "a ROTATED point becomes MANUAL and its tangent reaches the record")
	check(by[dragged.uid].get("tangent_mode", "AUTO") == "AUTO" and not by[dragged.uid].has("tangent"), "CONTROL: a DRAGGED point stays AUTO")
	var cl := Service.run("centrelines", SCRATCH)
	net.save_record()
	var cl2 := Service.run("centrelines", SCRATCH)
	check(str(cl) != str(cl2), "the rotation reshapes the solved centreline")

	# Merge two plain stations of one road.
	var n0: int = net.all_points().size()
	# A record gesture RELOADS the network, so node references do not survive it -- carry uids.
	var mp: Array = main.points().map(func(p): return p.uid)
	var r := Service.record_gesture(net, "merge", ["%s,%s" % [mp[5], mp[6]]])
	check(not r.get("failed", false) and net.all_points().size() == n0 - 1 and int(r["errors"]) == 0, "Merge Points collapses a run, gate stays green", str(r.get("message", r.get("error", ""))))
	r = Service.record_gesture(net, "merge", ["%s,%s" % [mp[1], mp[4]]])
	check(r.get("failed", false), "Merge Points refuses a non-contiguous selection", str(r.get("error", "")))

	# Split To New Road keeps the links.
	var spur: Node = _road(net, "demo_spur")
	var sp: Array = spur.points().map(func(p): return p.uid)
	var tail_uids := [sp[-2], sp[-1]]
	r = Service.record_gesture(net, "split", [",".join(PackedStringArray(tail_uids)), "--name", "demo_spur_tail"])
	var moved: Node = _road(net, "demo_spur_tail")
	var kept: bool = moved != null and moved.points().size() == 2 and net.find_point(sp[-3]).links.any(func(l): return l["target"] == tail_uids[0])
	check(not r.get("failed", false) and kept, "Split To New Road moves the points and keeps every link", str(r.get("message", r.get("error", ""))))

	# Repair Links restores a half link a hand edit dropped.
	var a_uid: String = _road(net, "demo_cross").points()[0].uid
	var b_uid: String = _road(net, "demo_cross").points()[1].uid
	net.find_point(a_uid).unlink(b_uid)
	r = Service.record_gesture(net, "repair", [])
	check(net.find_point(a_uid).links.any(func(l): return l["target"] == b_uid), "Repair Links restores the missing half of a link", str(r.get("message", "")))

	# Renumber Roads puts a child dragged out of order back.
	var cross: Node = _road(net, "demo_cross")
	var right: Array = cross.points().map(func(p): return p.uid)
	cross.move_child(cross.points()[0], cross.get_child_count() - 1)
	r = Service.record_gesture(net, "renumber", [])
	check(_road(net, "demo_cross").points().map(func(p): return p.uid) == right, "Renumber Roads restores the chain order from the links", str(r.get("message", "")))

	# Tidy Roads re-files nothing on a tidy network (idempotent).
	r = Service.record_gesture(net, "tidy", [])
	check(not r.get("failed", false) and str(r.get("message", "")).contains("already"), "Tidy Roads leaves a tidy network alone", str(r.get("message", "")))

	# Apply Cross-Section copies only the ticked group.
	var hwy: Array = _road(net, "demo_main").points()
	hwy[0].fields["lanes_fwd"] = 3
	var walk_before: float = hwy[2].fields["left_walk_width"]
	hwy[0].fields["left_walk_width"] = walk_before + 1.5
	var t_uid: String = hwy[2].uid
	r = Service.record_gesture(net, "cross_section", [hwy[0].uid, t_uid, "LANES"])
	var t: Node = net.find_point(t_uid)
	check(int(t.fields["lanes_fwd"]) == 3 and is_equal_approx(float(t.fields["left_walk_width"]), walk_before) and t.fields["profile_mode"] == "OVERRIDE", "Apply Cross-Section copies only LANES and marks OVERRIDE", str(r.get("message", r.get("error", ""))))

	# Branch Ramp Here on a fresh straight highway authored by gestures.
	var h: Dictionary = G.new_road(net, "b8_hwy", Vector3(0, 0, 900), Vector3.RIGHT)
	for i in 6:
		G.extend_road(h["node"].points()[-1])
	for p in h["node"].points():
		p.set_network_transform(Transform3D(p.network_transform().basis, Vector3(p.network_transform().origin.x * 7.5, 0, 900)))
	var mid_uid: String = h["node"].points()[3].uid
	r = Service.record_gesture(net, "branch_ramp", [mid_uid])
	var ramp: Node = _road(net, "b8_hwy_ramp")
	var aux: bool = net.find_point(mid_uid) != null and net.find_point(mid_uid).links.any(func(l): return l["type"] == "AUX")
	check(ramp != null and ramp.points().size() == 2 and aux, "Branch Ramp Here grows a ramp road AUX-linked from the station", "%s; gate %s error(s)" % [r.get("message", r.get("error", "")), r.get("errors", "?")])

	# Flow Report.
	var fl := Service.run("flow", SCRATCH)
	check(fl.get("report") != null and int(fl["report"]["lanes"]) > 0, "Flow Report answers over the exported lane graph", "%s" % (str(fl.get("report", {}).get("broken", "?")) if fl.get("report") != null else str(fl.get("errors"))))

	# Select Junction.
	var mouth: Node = null
	for p in net.all_points():
		if p.links.any(func(l): return l["type"] == "JUNCTION"):
			mouth = p
			break
	var members: Array = G.junction_members(mouth)
	var clique: bool = members.size() >= 3 and members.all(func(m): return members.all(func(o): return m == o or m.links.any(func(l): return l["target"] == o.uid and l["type"] == "JUNCTION")))
	check(clique, "Select Junction selects the whole clique", "%d mouths" % members.size())

	# Gizmo: dragging a handle is a LENGTH along the point's own axis.
	var len1: float = GizmoScript.handle_length(Vector3.ZERO, Vector3(0, 0, -1), Vector3(3, 20, -7), Vector3(0, -1, 0))
	var len2: float = GizmoScript.handle_length(Vector3.ZERO, Vector3(0, 0, -1), Vector3(0, 20, 9), Vector3(0, -1, 0))
	check(absf(len1 - 7.0) < 1e-4 and len2 == 0.0, "a handle drag projects onto the axis, never through the point", "%.3f, %.3f" % [len1, len2])

	net.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SCRATCH))
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
