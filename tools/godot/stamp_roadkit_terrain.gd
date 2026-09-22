extends SceneTree
## Road Kit B7, headless: stamp a network's roads into the scene's Terrain3D (or restore it), exactly as
## the dock's Stamp Terrain / Restore Terrain do, and SAVE the terrain data directory.
##
##   godot --headless --path . --script tools/godot/stamp_roadkit_terrain.gd -- <scene.tscn> <network> [--restore] [--force]
##
## Refuses over a city's block ground (`urban_paint.marker`, see `road_kit_stamp.gd`); `--force` overrides.
##
## Order, and why: the NATURAL ground is sampled into the ground sidecar first (a stamped network keeps
## its sidecar as the natural record where it covers -- `road_kit_ground.gd`), the corridors are solved
## over that sidecar (`roadkit_cli.py corridors`), and the stamp derives every height from it, re-deriving
## what the previous stamp (`<stem>.stamp.json`) reached. Build and Stamp can therefore run in either
## order and any number of times.

const Stamp := preload("res://addons/road_kit/road_kit_stamp.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		print("usage: -- <scene.tscn> <network node name> [--restore]")
		quit(2)
		return
	var restore := args.has("--restore")
	var scene: Node = (load(args[0]) as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var net: Node3D = null
	for c in scene.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript and str(c.name) == args[1]:
			net = c
	var terrains := scene.find_children("*", "Terrain3D", true, false)
	if net == null or terrains.is_empty():
		print("ERROR %s in %s" % ["no RoadKitNetwork " + args[1] if net == null else "no Terrain3D", args[0]])
		quit(1)
		return
	if net.all_points().is_empty():
		net.load_record()
	var terrain: Node = terrains[0]
	var r := Stamp.stamp_network(net, terrain, restore, args.has("--force"))
	print(r["message"])
	if r["ok"] and r.get("changed", 0) > 0:
		var dir := str(terrain.get("data_directory"))
		terrain.data.save_directory(dir)
		print("saved ", dir)
	quit(0 if r["ok"] else 1)
