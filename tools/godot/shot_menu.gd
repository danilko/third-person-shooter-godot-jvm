extends SceneTree
## Pictures of the full-screen menu's tabs (ui.GameMenu; needs a display):
##   xvfb-run -a /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --resolution 1280x720 \
##       --script tools/godot/shot_menu.gd -- <dir>
## Writes menu_<TAB>.png for the pause menu's four tabs (no player in the scene: STATUS shows the profile only).

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var dir: String = args[0] if args.size() > 0 else "/tmp"
	var layer := CanvasLayer.new()
	root.add_child(layer)
	var pm: Control = (load("res://src/main/resources/com/openworld/ui/PauseMenu.tscn") as PackedScene).instantiate()
	layer.add_child(pm)
	for i in 4:
		await process_frame
	pm.show()
	for t in String(pm.call("tabs_now")).split(","):
		pm.call("select_tab_now", t)
		for i in 6:
			await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s/menu_%s.png" % [dir, t])
		print("wrote %s/menu_%s.png" % [dir, t])
	quit(0)
