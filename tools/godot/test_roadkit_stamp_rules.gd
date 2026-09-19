extends SceneTree
## PLAN.md 3.15: the terrain stamp's steep cut face (`RoadData.cut_batter`). A corridor running along Godot +X at y 10,
## half-width 10, through natural ground at 100 m: the side the corridor point names as uphill is cut at the steep
## batter, the other side at the ordinary 1:1; with no steep value (the control) both sides are 1:1. A BENCH point
## (a cut_batter road) fills over land and never over the sea.
##
##   godot --headless --path . --script tools/godot/test_roadkit_stamp_rules.gd

const Stamp := preload("res://addons/road_kit/road_kit_stamp.gd")

var fails := 0

func _check(name: String, ok: bool, detail: String) -> void:
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", name, detail])
	if not ok:
		fails += 1

func _corridor(steep: float) -> Dictionary:
	# [x, y, z, half, ground, kind, steep]: travel +X, so cross(travel, offset) > 0 is the +Z side
	var pts := [[0.0, 10.0, 0.0, 10.0, 100.0, "TUNNEL", steep], [200.0, 10.0, 0.0, 10.0, 100.0, "TUNNEL", steep]]
	return {"corridors": [{"owner": "coast", "points": pts}], "cut_slope": 1.0, "fill_slope": 1.5}

func _initialize() -> void:
	var e := 4.0                                  # metres past the verge
	var d := 10.0 + Stamp.VERGE + e
	for case in [[10.0, "steep +Z"], [-10.0, "steep -Z"], [0.0, "control (none)"]]:
		var steep: float = case[0]
		var c := _corridor(steep)
		var idx: Dictionary = Stamp._index(c["corridors"], Transform3D.IDENTITY, c)
		var hp: float = Stamp.height_at(idx, c, 100.0, d, 100.0)
		var hm: float = Stamp.height_at(idx, c, 100.0, -d, 100.0)
		var surf := 10.0 - Stamp.CLEARANCE
		var want_p := surf + e * (absf(steep) if steep > 0.0 else 1.0)
		var want_m := surf + e * (absf(steep) if steep < 0.0 else 1.0)
		_check("%s: +Z side" % case[1], absf(hp - want_p) < 1e-4, "%.3f (want %.3f)" % [hp, want_p])
		_check("%s: -Z side" % case[1], absf(hm - want_m) < 1e-4, "%.3f (want %.3f)" % [hm, want_m])
		var on: float = Stamp.height_at(idx, c, 100.0, 0.0, 100.0)
		_check("%s: on the road" % case[1], absf(on - surf) < 1e-4, "%.3f" % on)
	# a BENCH point fills over land only: on the road over sand (0.5) the ground comes up to the road; over the sea
	# (-10) it stays sea, so the coast road never pushes an embankment into the water
	var bc := {"corridors": [{"owner": "coast", "points": [[0.0, 3.0, 0.0, 10.0, 0.5, "BENCH", 0.0],
			[200.0, 3.0, 0.0, 10.0, 0.5, "BENCH", 0.0]]}], "cut_slope": 1.0, "fill_slope": 1.5}
	var bidx: Dictionary = Stamp._index(bc["corridors"], Transform3D.IDENTITY, bc)
	var land: float = Stamp.height_at(bidx, bc, 100.0, 12.0, 0.5)
	var sea: float = Stamp.height_at(bidx, bc, 100.0, 12.0, -10.0)
	_check("bench over land fills to the road", absf(land - (3.0 - Stamp.CLEARANCE)) < 1e-4, "%.3f" % land)
	_check("bench over the sea stays sea", absf(sea - -10.0) < 1e-4, "%.3f" % sea)
	print("RESULT: %s" % ("PASS" if fails == 0 else "FAIL (%d)" % fails))
	quit(0 if fails == 0 else 1)
