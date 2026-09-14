extends SceneTree
## Road Kit B6b, headless: write a scene's ground sidecar exactly as the dock's Build does -- the
## scene's Terrain3D sampled on a grid over a network's footprint -- so a road network can be built
## over the real ground from the command line.
##
##   godot --headless --path . --script tools/godot/write_roadkit_ground.gd -- <scene.tscn> [<network node name>]
##   blender/tools/build_roads_piece.sh <record> Roads_<network> <zones.json> <printed sidecar>
##
## Prints `GROUND <sidecar path>`. Like the dock's service calls, the stations' own `ground_z` are
## re-sampled into the record too (a pad reads its mouths' station ground). The scene is entered into
## the tree (Terrain3D loads its data on tree entry) and never saved; the record is.

const Ground := preload("res://addons/road_kit/road_kit_ground.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")
const Gestures := preload("res://addons/road_kit/road_kit_gestures.gd")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		print("usage: -- <scene.tscn> [<network node name>]")
		quit(2)
		return
	var scene: Node = (load(args[0]) as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var net: Node3D = null
	for c in scene.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript and (args.size() < 2 or str(c.name) == args[1]):
			net = c
			break
	var terrains := scene.find_children("*", "Terrain3D", true, false)
	if net == null or terrains.is_empty():
		print("ERROR %s in %s" % ["no RoadKitNetwork" if net == null else "no Terrain3D", args[0]])
		quit(1)
		return
	if net.all_points().is_empty():
		net.load_record()
	print(Gestures.sample_ground(net, terrains[0])["message"])
	if net.save_record() != OK:
		print("ERROR could not save ", net.record_path)
		quit(1)
		return
	var t0 := Time.get_ticks_msec()
	var r := Ground.write_for(net, terrains[0])
	print(r["message"], " (%d ms)" % (Time.get_ticks_msec() - t0))
	if r["ok"]:
		print("GROUND ", ProjectSettings.globalize_path(r["path"]))
	quit(0 if r["ok"] else 1)
