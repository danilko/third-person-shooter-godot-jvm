extends SceneTree
## PLAN.md 3.1 B5 gate: Road Kit points take their ground height from the scene's Terrain3D.
##   godot --headless --path . --script tools/godot/test_roadkit_ground.gd
## Loads DebugWorld (real Terrain3D), lays a road across it, samples, and checks every point's
## record ground_z equals the terrain height under it — with a control: a point moved 5 km off the
## map keeps no sampled height.

const G := preload("res://addons/road_kit/road_kit_gestures.gd")

func _initialize() -> void:
	var world: Node = (load("res://src/main/resources/com/openworld/world/DebugWorld.tscn") as PackedScene).instantiate()
	root.add_child(world)
	await process_frame
	await process_frame
	var terrains := world.find_children("*", "Terrain3D", true, false)
	var fails := 0
	if terrains.is_empty():
		print("  FAIL  DebugWorld has a Terrain3D")
		quit(1)
		return
	var terrain: Node = terrains[0]
	var net: Node3D = load("res://addons/road_kit/road_kit_network.gd").new()
	world.add_child(net)
	var r: Dictionary = G.new_road(net, "probe", Vector3(-250, 0, 60), Vector3.RIGHT)
	for i in 6:
		G.extend_road(r["node"].points()[-1])
	var off: Node = r["node"].points()[-1]
	off.set_network_transform(Transform3D(Basis.IDENTITY, Vector3(5000, 0, 5000)))
	var s: Dictionary = G.sample_ground(net, terrain)
	print("  sample: ", s["message"])
	var worst := 0.0
	var sampled := 0
	for p in net.all_points():
		if p == off:
			continue
		var w: Vector3 = net.global_transform * p.network_transform().origin
		var h: float = terrain.data.get_height(w)
		worst = maxf(worst, absf(float(p.fields["ground_z"]) - h))
		sampled += 1 if p.fields["has_ground_z"] else 0
	var ok1: bool = sampled == net.all_points().size() - 1 and worst < 0.01
	print("  %s  every on-map point carries the terrain height   %d sampled, worst %.4f m" % ["PASS" if ok1 else "FAIL", sampled, worst])
	var ok2: bool = not off.fields["has_ground_z"]
	print("  %s  CONTROL: a point off the map stays unsampled" % ("PASS" if ok2 else "FAIL"))
	var rec: Dictionary = net.to_record()
	var in_rec: int = rec["points"].filter(func(d): return d.get("has_ground_z", false)).size()
	var ok3: bool = in_rec == sampled
	print("  %s  the heights reach the record                       %d point(s)" % ["PASS" if ok3 else "FAIL", in_rec])
	fails = int(not ok1) + int(not ok2) + int(not ok3)
	print("RESULT: %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
