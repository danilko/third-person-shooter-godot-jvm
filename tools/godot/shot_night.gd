extends SceneTree
## Pictures of the night, for judging the LOOK (a probe can assert a light exists; only a picture says whether
## you can see). NEEDS A DISPLAY.
##
##   godot --path . --script tools/godot/shot_night.gd -- --out=/tmp/night [--world=island] [--hours=0,6,12,19,22]
##
## Saves one frame per hour listed, from a street-level camera beside a lit lamp with a car in shot, and prints
## each frame's MEAN LUMINANCE -- which is the number the complaint "night is barely able to see" is about, and
## the one to compare before and after a change to the moon, the lamps or the ambient.

const WORLDS := {
	"debugworld": "res://src/main/resources/com/openworld/world/DebugWorld.tscn",
	"island": "res://src/main/resources/com/openworld/world/World.tscn",
}
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"

func _arg(name: String, fallback: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.split("=", true, 1)[1]
	return fallback

func _mean_luma(img: Image) -> float:
	var total := 0.0
	var step := maxi(1, img.get_width() / 160)
	var n := 0
	for y in range(0, img.get_height(), step):
		for x in range(0, img.get_width(), step):
			var c := img.get_pixel(x, y)
			total += 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b
			n += 1
	return total / maxf(1.0, n)

func _initialize() -> void:
	var out := _arg("out", "/tmp/night")
	DirAccess.make_dir_recursive_absolute(out)
	var world_key := _arg("world", "debugworld")
	var hours := []
	for h in _arg("hours", "0,6,12,19,22").split(","):
		hours.append(float(h))
	var world: Node = (load(WORLDS[world_key]) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node_or_null("Characters/Player")
	if player != null:
		player.process_mode = Node.PROCESS_MODE_DISABLED
	for f in 240:
		await physics_frame

	# stand beside a lamp, looking down the road, with a car in front of us
	var lamp := Vector3.ZERO
	for n in world.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
		if str(n.get("asset_name")).begins_with("StreetLight") and int(n.call("pole_count_now")) > 3:
			lamp = n.call("pole_world_position_now", 2)
			break
	var eye := lamp + Vector3(9, 1.6, 9)
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.global_position = eye
	cam.look_at(lamp + Vector3(-30, 0.5, -30), Vector3.UP)
	cam.make_current()
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = lamp + Vector3(2, 1.0, -6)
	car.look_at(car.global_position + Vector3(-1, 0, -1), Vector3.UP)
	car.freeze = true

	for h in hours:
		for n in world.find_children("TimeOfDay", "Node", true, false):
			n.set("current_time", h)
		for f in 30:
			await process_frame
		RenderingServer.force_draw()
		var img := root.get_viewport().get_texture().get_image()
		var path := "%s/%s_%02d00.png" % [out, world_key, int(h)]
		img.save_png(path)
		var lamps := root.get_node_or_null("StreetLights")
		print("%02d:00  mean luma %.4f  lamps lit %d  headlights %s  -> %s"
				% [int(h), _mean_luma(img), int(lamps.call("lit_lamps_now")) if lamps else -1,
				   car.call("headlights_on_now"), path])
	quit(0)
