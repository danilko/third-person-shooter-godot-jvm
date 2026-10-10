extends SceneTree
## PLAN.md 2.0: world.MarkerRegistry -- every level-design marker (a building's MARK_<kind>_<n> Empties, baked as
## nodes in the group `mission_marker`) found by KIND, by distance, or per building, through one reader.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --path . --script tools/godot/probe_markers.gd
##
## Two Koban (a police box: 2 x MARK_spawn team=police, 2 x MARK_weapon) 200 m apart. The expected numbers are read
## from the SCENE FILE'S TEXT, not from the registry, so the two cannot agree by sharing a mistake. Control: with one
## building freed its markers are gone from every query (the index follows streaming).

const KOBAN := "res://src/main/resources/com/openworld/world/buildings/Koban.tscn"

var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

## kind -> count, read off the .tscn text: a node header with groups=["mission_marker"], then its metadata/kind line.
func _expected(path: String) -> Dictionary:
	var out := {}
	var in_marker := false
	for line in FileAccess.get_file_as_string(path).split("\n"):
		if line.begins_with("[node "):
			in_marker = "\"mission_marker\"" in line
		elif in_marker and line.begins_with("metadata/kind = "):
			var k := line.trim_prefix("metadata/kind = ").strip_edges().trim_prefix("\"").trim_suffix("\"")
			out[k] = int(out.get(k, 0)) + 1
	return out

func _initialize() -> void:
	await process_frame
	var gm: Node = root.get_node_or_null("GameManager")
	if gm == null:
		print("RESULT FAIL (GameManager autoload missing)")
		quit(1)
		return
	var want := _expected(KOBAN)
	var total := 0
	for k in want:
		total += int(want[k])
	_check("the scene file has markers to find", total >= 4 and want.has("spawn") and want.has("weapon"), str(want))
	_check("an empty world has none", int(gm.call("marker_count_now", "")) == 0, "%d" % int(gm.call("marker_count_now", "")))

	var world := Node3D.new()
	root.add_child(world)
	var a: Node3D = (load(KOBAN) as PackedScene).instantiate() as Node3D
	var b: Node3D = (load(KOBAN) as PackedScene).instantiate() as Node3D
	world.add_child(a)
	world.add_child(b)
	a.global_position = Vector3(0, 0, 0)
	b.global_position = Vector3(200, 0, 0)
	b.rotation.y = PI / 2
	await process_frame

	_check("every marker of both buildings is indexed", int(gm.call("marker_count_now", "")) == 2 * total,
		"%d of %d" % [int(gm.call("marker_count_now", "")), 2 * total])
	for k in want:
		_check("by kind: " + k, int(gm.call("marker_count_now", k)) == 2 * int(want[k]),
			"%d of %d" % [int(gm.call("marker_count_now", k)), 2 * int(want[k])])
	var kinds := str(gm.call("marker_kinds_now")).split(",")
	var keys := want.keys()
	keys.sort()
	_check("the kinds listed are the file's", Array(kinds) == keys, "%s vs %s" % [kinds, keys])
	_check("a kind nobody authored finds nothing", int(gm.call("marker_count_now", "no_such_kind")) == 0, "")

	_check("near: only the building within the radius", int(gm.call("markers_near_now", "spawn", Vector3(0, 0, 0), 30.0)) == int(want["spawn"]),
		"%d" % int(gm.call("markers_near_now", "spawn", Vector3(0, 0, 0), 30.0)))
	_check("near: both within a wide one", int(gm.call("markers_near_now", "spawn", Vector3(100, 0, 0), 150.0)) == 2 * int(want["spawn"]), "")
	_check("under: one building's own markers", int(gm.call("markers_under_now", b, "")) == total and int(gm.call("markers_under_now", b, "weapon")) == int(want["weapon"]),
		"%d, weapon %d" % [int(gm.call("markers_under_now", b, "")), int(gm.call("markers_under_now", b, "weapon"))])

	# the typed marker: its props and its facing follow the building (b is turned a quarter)
	var na := str(gm.call("nearest_marker_now", "spawn", Vector3(0, 0, 0), 30.0)).split("|")
	var nb := str(gm.call("nearest_marker_now", "spawn", Vector3(200, 0, 0), 30.0)).split("|")
	_check("the nearest spawn marker carries its team", na.size() == 4 and na[1] == "police", str(na))
	var same := false
	if nb.size() == 4:
		var m: Node3D = b.get_node("Markers/" + nb[0])
		var f: Vector3 = -m.global_basis.z
		var got: PackedStringArray = nb[3].split(",")
		same = abs(float(got[0]) - f.x) < 0.02 and abs(float(got[1]) - f.z) < 0.02
	_check("its facing is the marker's -Z in the WORLD (the turned building's differs)", same and na.size() == 4 and nb[3] != na[3], "%s vs a %s" % [nb, na])

	print("")
	print("=== control: the index follows streaming ===")
	b.queue_free()
	await process_frame
	await process_frame
	_check("one building freed: its markers are gone", int(gm.call("marker_count_now", "")) == total,
		"%d of %d" % [int(gm.call("marker_count_now", "")), total])
	_check("  ... and nothing is found where it stood", int(gm.call("markers_near_now", "", Vector3(200, 0, 0), 30.0)) == 0, "")
	a.queue_free()
	await process_frame
	await process_frame
	_check("both freed: none", int(gm.call("marker_count_now", "")) == 0, "")

	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
