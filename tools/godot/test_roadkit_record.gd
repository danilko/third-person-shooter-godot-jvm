extends SceneTree
## PLAN.md 3.1 B2 gate: the Godot road-kit data model reads and writes the kit's `.roads.json`
## LOSSLESSLY. Imports a record into RoadKitNetwork/Road/Point nodes, then exports it again; the
## caller compares the two through `point_model` (tools/net-free: blender/tools/roadkit_cli.py path).
##
##   godot --headless --path . --script tools/godot/test_roadkit_record.gd -- <in.roads.json> <out.roads.json>

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var net: Node3D = load("res://addons/road_kit/road_kit_network.gd").new()
	root.add_child(net)
	var warnings: Array = net.load_record(args[0])
	for w in warnings:
		print("[roadkit] warning: ", w)
	print("[roadkit] imported %d roads, %d points" % [net.roads().size(), net.all_points().size()])
	var err: int = net.save_record(args[1])
	print("[roadkit] exported -> %s (%s)" % [args[1], error_string(err)])
	quit(0 if err == OK else 1)
