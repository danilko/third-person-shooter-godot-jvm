extends SceneTree
## PLAN.md 4.7b -- screenshots of the baked road map as the player sees it: the minimap, and the full
## map opened (fitted to the whole world) with a GPS route to a far waypoint. Needs a display.
##
##   godot --path . --script tools/godot/shot_road_map.gd -- --world=island --out=/tmp/shots
##
## Writes <out>/<world>_minimap.png, <world>_map_fit.png and <world>_map_zoom.png (the map zoomed in
## four wheel steps about the player).

const WORLDS := {
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
	"island": "res://src/main/resources/com/openworld/world/World.tscn",
}

func _initialize() -> void:
	var which := "island"
	var out := OS.get_user_data_dir()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--world="):
			which = a.substr(8)
		elif a.begins_with("--out="):
			out = a.substr(6)
	DirAccess.make_dir_recursive_absolute(out)
	var world: Node = (load(WORLDS[which]) as PackedScene).instantiate()
	root.add_child(world)
	for i in 30:
		await process_frame
	var player: Node3D = world.get_node("Characters/Player")
	var worldmap: Control = world.find_child("WorldMap", true, false)
	var bounds := world.find_child("WorldBounds", true, false) as Node3D
	var he: float = bounds.get("half_extent") if bounds != null else 400.0
	# A waypoint across the world from the player, so the route crosses the map.
	var wp := Vector3(-player.global_position.x * 0.8, player.global_position.y, -player.global_position.z * 0.8)
	if wp.distance_to(player.global_position) < he * 0.3:
		wp = player.global_position + Vector3(he * 0.6, 0, he * 0.4)
	player.call("set_waypoint", wp)
	for i in 30:
		await process_frame
	await _save(out + "/%s_minimap.png" % which)
	var ev := InputEventAction.new()
	ev.action = "map"
	ev.pressed = true
	Input.parse_input_event(ev)
	for i in 10:
		await process_frame
	await _save(out + "/%s_map_fit.png" % which)
	var at: Vector2 = worldmap.call("world_to_screen_now", player.global_position)
	for k in 4:
		var w := InputEventMouseButton.new()
		w.button_index = MOUSE_BUTTON_WHEEL_UP
		w.pressed = true
		w.position = at
		worldmap.call("_gui_input", w)
	for i in 10:
		await process_frame
	await _save(out + "/%s_map_zoom.png" % which)
	quit()

func _save(path: String) -> void:
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(path)
	print("wrote ", path)
