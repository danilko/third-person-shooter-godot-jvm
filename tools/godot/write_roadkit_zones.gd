extends SceneTree
## Road Kit B6, headless: write a scene's zones sidecar exactly as the dock's Build does, so a road
## network can be cut and built from the command line.
##
##   godot --headless --path . --script tools/godot/write_roadkit_zones.gd -- <scene.tscn> [<network node name>]
##   blender/tools/build_roads_piece.sh <record> Roads_<network> <printed sidecar>
##
## Prints `ZONES <sidecar path>` and each warning. The scene is instantiated, never added to the tree
## and never saved; wiring the built pieces back into the markers is the dock's job (or a hand edit
## of the Zone fields `plan_wiring` names).

const Z := preload("res://addons/road_kit/road_kit_zones.gd")
const NetworkScript := preload("res://addons/road_kit/road_kit_network.gd")

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: -- <scene.tscn> [<network node name>]")
		quit(2)
		return
	var scene: Node = (load(args[0]) as PackedScene).instantiate()
	var net: Node3D = null
	for c in scene.find_children("*", "Node3D", true, false):
		if c.get_script() == NetworkScript and (args.size() < 2 or str(c.name) == args[1]):
			net = c
			break
	if net == null:
		print("ERROR no RoadKitNetwork%s in %s" % ["" if args.size() < 2 else " named " + args[1], args[0]])
		scene.free()
		quit(1)
		return
	var rec := Z.zones_record(net, Z.markers_in(scene))
	for w in rec["warnings"]:
		print("WARN ", w)
	var path := Z.sidecar_path(net.record_path)
	var err := Z.write_sidecar(path, rec)
	print("ZONES %s (%d zone(s), %s)" % [ProjectSettings.globalize_path(path), rec["zones"].size(), error_string(err)])
	scene.free()
	quit(0 if err == OK else 1)
