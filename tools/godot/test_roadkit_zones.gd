extends SceneTree
## PLAN.md 3.1 B6 gate, Godot half: the scene's ZoneMarkers become the zones sidecar the solver cuts a
## network by, and a build's pieces are wired back into each marker's Zone exactly as the dock does it.
##
##   godot --headless --path . --script tools/godot/test_roadkit_zones.gd -- [<zones.json out>] [<build log>]
##
## Reads world/hosts/RoadKitZones.tscn (never added to the tree — every function under test composes
## transforms itself, as it must in the editor). With a build log, the pieces it reports must wire
## into that host with ZERO changes: the committed host is what the dock would have written.

const Z := preload("res://addons/road_kit/road_kit_zones.gd")
const HOST := "res://src/main/resources/com/openworld/world/hosts/RoadKitZones.tscn"
const PIECES := "res://src/main/resources/com/openworld/world/pieces/"

var fails := 0

func check(label: String, ok: bool, detail := "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _near(a: Array, b: Array) -> bool:
	for i in b.size():
		if absf(float(a[i]) - float(b[i])) > 1e-4:
			return false
	return true

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var host: Node3D = (load(HOST) as PackedScene).instantiate()
	var net: Node3D = host.get_node("RoadKitZones")
	var markers := Z.markers_in(host)
	check("finds both markers", markers.size() == 2, str(markers.map(func(m): return m.name)))

	# 1. The sidecar: centres in the NETWORK's frame (the network sits at z = +40), kit axes.
	var rec := Z.zones_record(net, markers)
	var by := {}
	for z in rec["zones"]:
		by[z["zone_id"]] = z
	check("west centre in the network frame, kit axes", by.has("west") and _near(by["west"]["centre"], [250, 0, 0]), str(by.get("west", {}).get("centre")))
	check("east centre in the network frame, kit axes", by.has("east") and _near(by["east"]["centre"], [1400, 100, 0]), str(by.get("east", {}).get("centre")))
	check("half extents are the XZ footprint", by.has("east") and _near(by["east"]["half"], [700, 450]), str(by.get("east", {}).get("half")))
	check("no warnings on a clean host", rec["warnings"].is_empty(), str(rec["warnings"]))
	check("sidecar path follows the record", Z.sidecar_path("res://a/X.roads.json") == "res://a/X.zones.json")
	if args.size() > 0:
		check("sidecar written", Z.write_sidecar(args[0], rec) == OK, args[0])

	# 2. A duplicate id is reported, not silently cut.
	var dup: Node3D = markers[0].duplicate()
	dup.name = "Dup"
	dup.rotation_degrees = Vector3(0, 30, 0)
	host.get_node("Zones").add_child(dup)
	var rec2 := Z.zones_record(net, Z.markers_in(host))
	check("duplicate zone_id reported and dropped", rec2["zones"].size() == 2 and rec2["warnings"].size() == 1, str(rec2["warnings"]))
	host.get_node("Zones").remove_child(dup)
	dup.free()

	# 3. Wiring. The host is committed exactly as the dock writes it, so its own pieces change nothing.
	var pieces := [
		{"zone": "west", "piece": "Roads_RoadKitZones_west", "scene": PIECES + "Roads_RoadKitZones_west.tscn"},
		{"zone": "east", "piece": "Roads_RoadKitZones_east", "scene": PIECES + "Roads_RoadKitZones_east.tscn"}]
	if args.size() > 1:
		var logged := Z.pieces_from_log(FileAccess.get_file_as_string(args[1]))
		var got: Array = logged.map(func(p): return p["scene"])
		var want: Array = pieces.map(func(p): return p["scene"])
		got.sort()
		want.sort()
		check("build log reports the host's two pieces", got == want, str(got))
		pieces = logged
	var piece_of := {}
	for p in pieces:
		piece_of[p["zone"]] = p
	var plan := Z.plan_wiring(net, markers, pieces, "Roads_RoadKitZones")
	check("the committed host needs no wiring", plan["changes"].is_empty(), str(plan["changes"].map(func(c): return "%s.%s" % [c["marker"], c["property"]])))

	# 4. A zone that lost its roads is CLEARED, so a stale piece cannot stream.
	plan = Z.plan_wiring(net, markers, [piece_of["west"]], "Roads_RoadKitZones")
	var cleared: Array = plan["changes"].filter(func(c): return c["marker"] == "East" and c["property"] == "geometry_path" and c["new"] == "")
	check("east cleared when it gets no piece", cleared.size() == 1 and plan["changes"].size() == 2, str(plan["notes"]))

	# 5. A zone already streaming something else (a district) is not wired over.
	var east_zone = markers[1].get("zone")
	east_zone.set("geometry_path", "res://somewhere/District_harbour.tscn")
	plan = Z.plan_wiring(net, markers, pieces, "Roads_RoadKitZones")
	check("a foreign geometry is kept and reported", plan["changes"].is_empty() and plan["notes"].size() == 1, str(plan["notes"]))

	# 6. A blank zone is wired in full: path, world placement, the network's transform.
	east_zone.set("geometry_path", "")
	east_zone.set("geometry_world_placed", false)
	east_zone.set("geometry_world_transform", Transform3D.IDENTITY)
	plan = Z.plan_wiring(net, markers, pieces, "Roads_RoadKitZones")
	check("a blank zone gets three changes", plan["changes"].size() == 3, str(plan["changes"].map(func(c): return c["property"])))
	Z.apply_wiring(plan)
	check("applied: path", str(east_zone.get("geometry_path")) == piece_of["east"]["scene"], str(east_zone.get("geometry_path")))
	check("applied: world placed at the network", east_zone.get("geometry_world_placed") == true and (east_zone.get("geometry_world_transform") as Transform3D).origin.is_equal_approx(Vector3(0, 0, 40)))
	check("re-planning after apply changes nothing", Z.plan_wiring(net, markers, pieces, "Roads_RoadKitZones")["changes"].is_empty())

	# 7. The resident piece has no marker, and that is said out loud.
	plan = Z.plan_wiring(net, markers, pieces + [{"zone": "", "piece": "Roads_RoadKitZones", "scene": PIECES + "Roads_RoadKitZones.tscn"}], "Roads_RoadKitZones")
	check("resident piece reported", plan["notes"].size() == 1 and "no marker streams it" in str(plan["notes"][0]), str(plan["notes"]))

	host.free()
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
