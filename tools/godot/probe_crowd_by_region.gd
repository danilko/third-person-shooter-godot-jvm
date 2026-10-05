extends SceneTree
## How many people are actually AROUND a player in each kind of district (user, 2026-10-04: "the crowd seems more
## on the harbour / other areas than the city, which seems opposite"). Stands the player ON THE GROUND at the busiest
## crowd cell of each region (the record's own cell centres), waits for streaming, and counts the light peds that
## are drawn within 60 m and 150 m, the promoted walkers, and every other character on foot (AI from spawn configs,
## mission people) -- so a district that LOOKS busy can be told apart from one whose CROWD is.
##
##   <godot> --headless --path . --script tools/godot/probe_crowd_by_region.gd
const WORLD := "res://src/main/resources/com/openworld/world/World.tscn"
const SPOTS := {"nightlife": Vector2(882, -378), "downtown": Vector2(378, -126), "city": Vector2(126, -126),
		"residential": Vector2(-378, 378), "industry": Vector2(-126, 882), "harbour": Vector2(-378, 1134)}
var w: Node
var player: Node3D

func _initialize() -> void:
	_run.call_deferred()

func _crowds(n: Node, out: Array) -> void:
	if n.has_method("ped_positions_now"):
		out.append(n)
	for c in n.get_children():
		_crowds(c, out)

func _run() -> void:
	w = (load(WORLD) as PackedScene).instantiate()
	root.add_child(w)
	current_scene = w
	player = w.get_node("Characters/Player")
	player.get_node("Health").set("max_health", 1000000.0)
	var wb := w.find_child("WorldBounds", true, false)
	print("  %-12s %7s %7s %7s %8s %8s" % ["region", "ped60", "ped150", "promoted", "ai_foot", "cars"])
	for name in SPOTS:
		var s: Vector2 = SPOTS[name]
		var h: float = wb.call("terrain_height", s.x, s.y)
		player.global_position = Vector3(s.x, h + 0.5, s.y)
		var t0 := Time.get_ticks_msec()
		while Time.get_ticks_msec() - t0 < 20000:
			await process_frame
		var p := player.global_position
		var cs := []
		_crowds(w, cs)
		var n60 := 0
		var n150 := 0
		for c in cs:
			for v in c.call("ped_positions_now"):
				var d := Vector2(v.x - p.x, v.z - p.z).length()
				if d < 60.0: n60 += 1
				if d < 150.0: n150 += 1
		var walk := 0
		var foot := 0
		var cars := 0
		for n in get_nodes_in_group("characters"):
			var d2 := (n as Node3D).global_position.distance_to(p)
			if d2 > 150.0 or n == player:
				continue
			var sp := str(n.get_script().resource_path) if n.get_script() != null else ""
			if sp.contains("/vehicle/") or sp.contains("/carrier/"):
				cars += 1
			elif n.get("current_vehicle_node") == null:
				var sw := false
				for ch in n.get_children():
					if ch.get_script() != null and str(ch.get_script().resource_path).ends_with("SidewalkWalkerController.java"):
						sw = true
				if sw: walk += 1
				else: foot += 1
		print("  %-12s %7d %7d %7d %8d %8d   (player y %.2f, terrain %.2f)" % [name, n60, n150, walk, foot, cars, p.y, h])
	quit(0)
