extends SceneTree
## PLAN.md 3.1 B6c gate: the dock can SHOW the built roads and the zones while editing, and a save
## writes none of it.
##   godot --headless --path . --script tools/godot/test_roadkit_preview.gd
##
## On DebugWorld: Preview Pieces instances the two DebugRoads pieces at the transform
## `Zone.placeGeometry` would use (the network's, for a world-placed zone; the marker's position
## otherwise), and packing the scene -- what a save does -- contains neither the preview nor the
## overlay. CONTROL: the same pack with the preview given an owner DOES contain it, so the check can
## see what it asserts is absent. The zone overlay draws every run in its zone's colour, both markers,
## and every cross-zone successor `roadkit_cli.py pieces` reports.

const Preview := preload("res://addons/road_kit/road_kit_preview.gd")
const Zones := preload("res://addons/road_kit/road_kit_zones.gd")
const Service := preload("res://addons/road_kit/road_kit_service.gd")
const OverlayScript := preload("res://addons/road_kit/road_kit_overlay.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"

var fails := 0

func check(ok: bool, what: String, detail: String = "") -> void:
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", what, detail])
	fails += 0 if ok else 1

func _in_pack(scene: Node, name: String) -> bool:
	var ps := PackedScene.new()
	ps.pack(scene)
	var st := ps.get_state()
	for i in st.get_node_count():
		if str(st.get_node_path(i)).contains(name):
			return true
	return false

func _initialize() -> void:
	var scene: Node = (load(WORLD) as PackedScene).instantiate()
	var net: Node3D = null
	for c in scene.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript:
			net = c
	var markers := Zones.markers_in(scene)
	check(net != null and markers.size() == 2, "DebugWorld has the DebugRoads network and 2 markers", "%d marker(s)" % markers.size())

	var r := Preview.build(scene, net, markers)
	print("  preview: ", r["message"])
	var holder: Node3D = r["node"]
	check(r["pieces"].size() == 2 and holder.get_child_count() == 2, "Preview Pieces instances both zone pieces", str(r["pieces"].map(func(p): return p["name"])))
	var worst := 0.0
	for m in markers:
		var z = m.get("zone")
		var child := holder.get_node_or_null(str(z.get("zone_id"))) as Node3D
		if child == null:
			worst = INF
			continue
		var want: Transform3D = z.get("geometry_world_transform") if z.get("geometry_world_placed") else Transform3D(Basis.IDENTITY, Zones.world_xf(m).origin)
		worst = maxf(worst, child.transform.origin.distance_to(want.origin) + (child.transform.basis.x - want.basis.x).length())
		worst = maxf(worst, child.transform.origin.distance_to(Zones.world_xf(net).origin))
	check(worst < 0.001, "each piece sits at the network's transform (placeGeometry)", "worst %.4f" % worst)
	check(holder.top_level and holder.owner == null, "the preview is top_level and unowned")
	check(holder.get_node("debug_a").find_children("*", "Path3D", true, false).size() > 0, "the preview carries the built lanes (a real piece, not a stub)")

	# A marker whose zone is NOT world-placed puts its piece at the marker -- the other half of the rule.
	var m0: Node3D = markers[0]
	var z0 = m0.get("zone").duplicate()
	z0.set("geometry_world_placed", false)
	m0.set("zone", z0)
	m0.position += Vector3(37, 0, -11)
	r = Preview.build(scene, net, markers)
	var moved := (r["node"] as Node3D).get_node_or_null(str(z0.get("zone_id"))) as Node3D
	var d := moved.transform.origin.distance_to(Zones.world_xf(m0).origin) if moved != null else INF
	check(d < 0.001, "a marker-framed zone's piece follows its marker", "%.4f m" % d)
	holder = r["node"]

	var ov: MeshInstance3D = OverlayScript.new()
	ov.name = "_RoadKitOverlay"
	net.add_child(ov)
	var zones_path := "user://test_roadkit_preview.zones.json"
	# The marker moved above: restore it so the cut is the committed one.
	m0.position -= Vector3(37, 0, -11)
	Zones.write_sidecar(zones_path, Zones.zones_record(net, markers))
	var data := Service.run("centrelines", net.record_path, ["--zones", ProjectSettings.globalize_path(zones_path)])
	check(not data.get("failed", false), "roadkit_cli centrelines --zones answers", str(data.get("error", "")))
	var counts: Dictionary = ov.redraw(net, data, markers)
	var zones_of_runs := {}
	for run in data.get("runs", []):
		zones_of_runs[run.get("zone", "?")] = true
	check(counts["runs"] == 4 and zones_of_runs.size() == 2 and not zones_of_runs.has(""), "every run is drawn in one of the two zones' colours", "%s, zones %s" % [counts, zones_of_runs.keys()])
	check(counts["zones"] == 2 and counts["cross"] == 10, "both markers' boxes + rings, the 10 cross-zone successors", "zones %d cross %d" % [counts["zones"], counts["cross"]])

	check(not _in_pack(scene, Preview.NAME) and not _in_pack(scene, "_RoadKitOverlay"), "saving the scene writes neither the preview nor the overlay")
	holder.owner = scene
	check(_in_pack(scene, Preview.NAME), "CONTROL: an owned preview WOULD be saved")
	holder.owner = null

	Preview.clear(scene)
	check(Preview.find(scene) == null, "turning the preview off removes it")
	scene.free()
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
