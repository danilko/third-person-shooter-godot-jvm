extends SceneTree
## Road Kit: GODOT'S OWN DELETE IS A ROAD GESTURE. The Scene dock's Delete (and the viewport's Delete key)
## takes a node out of its parent with `remove_child` and keeps it in the undo history; undo puts it back
## with `add_child` + `move_child`. Nothing in the plugin hooks either -- the record's links are DERIVED from
## the live tree (`RoadKitNetwork.record_links`) -- so this drives exactly those two calls.
##   godot --headless --path . --script tools/godot/test_roadkit_native_delete.gd
##
##   * an interior station removed: no link names it, its two neighbours are joined, the gate stays at 0
##     errors, the road is still ONE run of centreline, names renumber;
##   * two consecutive interior stations removed: joined across both;
##   * a junction mouth removed: the pad keeps its other mouths; with one left it is a plain station;
##   * a whole road removed: no link names any of its points;
##   * each put back (the undo): the record is IDENTICAL to the one before the delete -- also after the
##     network was reloaded from the post-delete record in between (a gesture ran meanwhile; link order aside);
##   * the Delete gesture (`Gestures.delete_point`) joins the neighbours the same way;
##   * names say what a point is: `_jct` a junction mouth, `_end` a road end joining nothing, no tag a plain
##     station, and the Scene-dock tooltip lists the links.

const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const RECORD := "res://assets/world_source/pieces/DebugRoads.roads.json"
const SCRATCH := "user://test_roadkit_native_delete.roads.json"

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-74s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _gate(net: Node) -> int:
	net.save_record(SCRATCH, true)
	var r := Service.run("validate", SCRATCH)
	return -1 if r.get("failed", false) else int(r["errors"])

func _runs_of(net: Node, road_name: String) -> int:
	net.save_record(SCRATCH, true)
	var r := Service.run("centrelines", SCRATCH)
	return (r.get("runs", []) as Array).filter(func(x): return x["road"] == road_name).size()

func _links_to(rec: Dictionary, uid: String) -> int:
	var n := 0
	for pd in rec["points"]:
		for l in pd["links"]:
			n += 1 if l["target"] == uid else 0
	return n

func _point(rec: Dictionary, uid: String) -> Dictionary:
	for pd in rec["points"]:
		if pd["uid"] == uid:
			return pd
	return {}

func _linked(rec: Dictionary, a: String, b: String, type: String) -> bool:
	var pa := _point(rec, a)
	var pb := _point(rec, b)
	return pa["links"].any(func(l): return l["target"] == b and l["type"] == type) \
			and pb["links"].any(func(l): return l["target"] == a and l["type"] == type)

## `rec` with each point's links sorted by target -- a reload re-orders a point's links, which is not a change.
func _canon(rec: Dictionary) -> Dictionary:
	var out: Dictionary = rec.duplicate(true)
	for pd in out["points"]:
		pd["links"].sort_custom(func(x, y): return str(x["target"]) + str(x["type"]) < str(y["target"]) + str(y["type"]))
	return out

func _same(a: Dictionary, b: Dictionary) -> bool:
	var ca := _canon(a)
	var cb := _canon(b)
	if ca == cb:
		return true
	for i in ca["points"].size():
		if ca["points"][i] != cb["points"][i]:
			print("    differs: ", ca["points"][i], "\n         vs ", cb["points"][i])
	if ca["roads"] != cb["roads"]:
		print("    roads differ")
	return false

## What the Scene dock's Delete does to the tree, and what its undo does.
func _delete(p: Node) -> Array:
	var parent := p.get_parent()
	var at := p.get_index()
	parent.remove_child(p)
	return [parent, p, at]

func _undelete(d: Array) -> void:
	d[0].add_child(d[1])
	d[0].move_child(d[1], d[2])

func _initialize() -> void:
	var net: Node3D = NetworkScript.new()
	root.add_child(net)
	net.record_path = SCRATCH
	net.from_record(JSON.parse_string(FileAccess.get_file_as_string(RECORD)))
	await process_frame
	var original: Dictionary = net.to_record()
	check(_gate(net) == 0, "the DebugRoads record passes the gate before any delete")
	check(net.all_points().filter(func(p): return String(p.name).ends_with("_jct")).size() \
			== net.all_points().filter(func(p): return p.fields["role"] == "INTERSECTION").size(),
			"every INTERSECTION point's name carries _jct")
	var spur: Node = net.get_node("spur")
	check(String(spur.points()[0].name) == "spur_p000_end", "a road end that joins nothing is tagged _end", String(spur.points()[0].name))
	var loop: Node = net.get_node("loop")
	check(String(loop.points()[1].name) == "loop_p001", "a plain station carries no tag", String(loop.points()[1].name))
	check(loop.points()[0].editor_description.contains("JUNCTION -> "), "a mouth's Scene-dock tooltip lists its junction links", loop.points()[0].editor_description.replace("\n", " | "))
	var runs0 := _runs_of(net, "loop")

	# ── one interior station ──
	var pts: Array = loop.points()
	var victim: Node = pts[3]
	var a: String = pts[2].uid
	var b: String = pts[4].uid
	var d := _delete(victim)
	var rec: Dictionary = net.to_record()
	check(_links_to(rec, victim.uid) == 0, "no link names the deleted station")
	check(_linked(rec, a, b, "SEGMENT"), "its two neighbours are joined by a SEGMENT")
	check(_gate(net) == 0, "the gate stays at 0 errors")
	check(_runs_of(net, "loop") == runs0, "the road is not cut (%d run(s))" % runs0)
	net.renumber()
	check(loop.points().size() == pts.size() - 1 and String(loop.points()[3].name) == "loop_p003", "names renumber along the chain")
	_undelete(d)
	net.renumber()
	check(net.to_record() == original, "putting it back restores the record exactly")
	check(String(victim.name) == "loop_p003", "and its name")

	# ── two consecutive interior stations ──
	pts = loop.points()
	var d1 := _delete(pts[4])
	var d2 := _delete(pts[5])
	rec = net.to_record()
	check(_linked(rec, pts[3].uid, pts[6].uid, "SEGMENT"), "two consecutive stations deleted: joined across both")
	check(_gate(net) == 0, "gate 0 errors")
	_undelete(d2)
	_undelete(d1)
	check(net.to_record() == original, "both put back: record identical")

	# ── deleted, then the network reloaded from the post-delete record (a gesture ran), then undone ──
	pts = loop.points()
	d = _delete(pts[3])
	net.from_record(net.to_record())
	check(pts[2].links.any(func(l): return l["target"] == pts[4].uid), "a reload writes the bridge into the nodes")
	_undelete(d)
	check(_same(net.to_record(), original), "undo after a reload: the record is identical (bridge dropped, partner links restored)")

	# ── junction mouths ──
	var mouth: Node = loop.points()[0]
	var members: Array = Gestures.junction_members(mouth)
	check(members.size() == 3, "loop's head is a mouth of a 3-way junction", str(members.map(func(m): return m.name)))
	var others: Array = members.filter(func(m): return m != mouth)
	d1 = _delete(mouth)
	rec = net.to_record()
	check(_links_to(rec, mouth.uid) == 0 and _linked(rec, others[0].uid, others[1].uid, "JUNCTION"), "a mouth deleted: the other two keep their JUNCTION link")
	d2 = _delete(others[0])
	rec = net.to_record()
	check(_point(rec, others[1].uid).get("role", "SEGMENT") == "SEGMENT", "the last mouth of a pad is written as a plain station")
	net.renumber()
	check(not String(others[1].name).ends_with("_jct"), "and loses its _jct tag", String(others[1].name))
	_undelete(d2)
	_undelete(d1)
	net.renumber()
	check(_same(net.to_record(), original) and String(mouth.name).ends_with("_jct"), "both put back: record identical, tags back")

	# ── a whole road ──
	var link: Node = net.get_node("link")
	var uids: Array = link.points().map(func(p): return p.uid)
	d = _delete(link)
	rec = net.to_record()
	check(uids.all(func(u): return _links_to(rec, u) == 0), "a road deleted: no link names any of its points")
	check(_gate(net) == 0, "gate 0 errors")
	_undelete(d)
	check(_same(net.to_record(), original), "the road put back: record identical")

	# ── the Delete gesture joins the neighbours too ──
	pts = loop.points()
	var g := Gestures.delete_point(pts[3])
	rec = net.to_record()
	check(g["ok"] and _linked(rec, pts[2].uid, pts[4].uid, "SEGMENT") and _gate(net) == 0, "Gestures.delete_point joins the neighbours, gate 0 errors")

	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
