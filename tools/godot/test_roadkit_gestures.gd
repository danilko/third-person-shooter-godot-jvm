extends SceneTree
## PLAN.md 3.1 B4 gate: the Road Kit gestures (the kit's Blender operators rebuilt for Godot) author a
## network the kit's own gate ACCEPTS and whose lane graph exports. Headless — no editor API is used.
##
##   godot --headless --path . --script tools/godot/test_roadkit_gestures.gd -- <out.roads.json>
##
## Builds: an east-west main road and a north-south cross road meeting at a junction; a ramp road that
## leaves the main road (AUX); then exercises Extend from BOTH ends, Insert, Delete and the refusals.
## The shell side runs `roadkit_cli.py validate` and `lanekit` on the written record.

const G := preload("res://addons/road_kit/road_kit_gestures.gd")

var fails := 0

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-52s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	var out: String = OS.get_cmdline_user_args()[0]
	var net: Node3D = load("res://addons/road_kit/road_kit_network.gd").new()
	net.name = "GestureTest"
	root.add_child(net)

	# main: x -200 .. +200 along +X (east); cross: z -200 .. +200 along -Z (north)
	var r := G.new_road(net, "main", Vector3(-200, 0, 0), Vector3.RIGHT)
	check("new road", r["ok"], r["message"])
	var main: Node = r["node"]
	for i in 8:
		G.extend_road(main.points()[-1])
	check("extend from the tail", main.points().size() == 10, "%d points" % main.points().size())
	var head_before: Node = main.points()[0]
	var h := G.extend_road(head_before)
	check("extend from the HEAD prepends", h["ok"] and main.points()[0] == h["node"] and main.points()[1] == head_before, h["message"])
	var interior := G.extend_road(main.points()[4])
	check("extend refuses an interior point", not interior["ok"], interior["message"])
	# `_end`: both ends of a road that joins nothing yet (RoadKitPoint.point_name's tag).
	check("names follow the chain", main.points()[0].name == "main_p000_end" and main.points()[1].name == "main_p001" \
			and main.points()[-1].name == "main_p%03d_end" % (main.points().size() - 1), "%s .. %s" % [main.points()[0].name, main.points()[-1].name])

	r = G.new_road(net, "cross", Vector3(0, 0, 200), Vector3.FORWARD)
	var cross: Node = r["node"]
	for i in 8:
		G.extend_road(cross.points()[-1])

	# Junction, authored the way the kit does it: delete each road's station AT the crossing, which
	# leaves the two mouths either side of it chain-adjacent with no SEGMENT link (the pad's gap).
	for road in [main, cross]:
		for p in road.points():
			if p.network_transform().origin.length() < 1.0:
				G.delete_point(p)
	var m_w: Node = main.points().filter(func(p): return p.network_transform().origin.x < 0).back()
	var m_e: Node = main.points().filter(func(p): return p.network_transform().origin.x > 0).front()
	var c_s: Node = cross.points().filter(func(p): return p.network_transform().origin.z > 0).back()
	var c_n: Node = cross.points().filter(func(p): return p.network_transform().origin.z < 0).front()
	var j := G.make_intersection([m_w, m_e, c_s, c_n])
	check("make intersection builds a 4-clique", j["ok"] and m_w.links.filter(func(l): return l["type"] == "JUNCTION").size() == 3, j["message"])
	check("every mouth is typed INTERSECTION", [m_w, m_e, c_s, c_n].all(func(p): return p.fields["role"] == "INTERSECTION"))

	# Insert splits a real span and refuses the junction gap.
	var before: int = main.points().size()
	var ins := G.insert_after(main.points()[1])
	check("insert splits a span", ins["ok"] and main.points().size() == before + 1, ins["message"])
	var gap := G.insert_after(m_w)
	check("insert refuses a junction gap", not gap["ok"], gap["message"])

	# Delete strips inbound links.
	var victim: Node = main.points()[2]
	var nb: Node = main.points()[1]
	var vuid: String = victim.uid
	G.delete_point(victim)
	check("delete strips inbound links", not nb.links.any(func(l): return l["target"] == vuid))
	G.connect_points(main.points()[1], main.points()[2], "SEGMENT")

	# Ramp: a one-way road beside the main road's east end. Make Ramp is the SOLVER's gesture
	# (`roadkit_cli.py ramp`): it opens the aux slot, links AUX mainline -> ramp and puts the mouth on
	# the gore line. Selected RAMP-FIRST on purpose -- the mainline must be derived, not click order.
	var east: Node = main.points()[-2]
	r = G.new_road(net, "ramp", east.network_transform().origin + Vector3(20, 0, -12), Vector3.RIGHT)   # keep-left: eastbound lanes are on -Z
	var ramp: Node = r["node"]
	G.extend_road(ramp.points()[-1])
	for p in ramp.points():
		p.fields["lanes_bwd"] = 0
		p.fields["lanes_fwd"] = 1
	ramp.base["lanes_bwd"] = 0
	ramp.base["lanes_fwd"] = 1
	var err: int = net.save_record(out)
	check("record written", err == OK, out)
	var S := preload("res://addons/road_kit/road_kit_service.gd")
	var rr: Dictionary = S.run("ramp", out, [ramp.points()[0].uid, east.uid])
	check("make ramp (solver) derives mainline -> ramp", not rr.get("failed", false) and rr.get("mainline") == east.uid and rr.get("aligned", false), str(rr.get("error", "mainline %s, slot %s over %s station(s)" % [rr.get("mainline"), rr.get("field"), rr.get("slot_stations")])))
	var east_uid: String = east.uid
	net.load_record(out)   # rebuilds every node -- the old references are freed from here on
	var east2: Node = net.find_point(east_uid)
	check("the reloaded network carries the AUX link", east2 != null and east2.links.any(func(l): return l["type"] == "AUX"))
	var v: Dictionary = S.run("validate", out)
	var errs := []
	for f in v.get("findings", []):
		if f["severity"] == "ERROR":
			errs.append("%s %s" % [f["code"], f["message"].substr(0, 120)])
	check("the kit's gate accepts the authored network (0 errors)", v.get("errors", -1) == 0, "; ".join(errs) if not errs.is_empty() else "%d warning(s)" % v.get("warnings", 0))
	var lk: Dictionary = S.run("lanekit", out, [out.get_basename() + ".lanekit.json"])
	check("its lane graph exports", lk.get("written", false) and lk.get("lanes", 0) > 0, "lanes=%s junctions=%s" % [lk.get("lanes"), lk.get("junctions")])
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
