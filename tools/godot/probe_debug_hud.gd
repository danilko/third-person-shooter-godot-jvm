extends SceneTree
## The debug HUD (PerfDebugOverlay, Shift+F3 / console `hud 0-3`): each level shows what it promises, for a real
## Player on a floor. With a display, `-- --shot=<png>` also saves level 3 to look at.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_debug_hud.gd

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-48s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await process_frame

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(60, 1, 60)
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	var wall := StaticBody3D.new()
	wall.name = "ProbeWall"
	var ws := CollisionShape3D.new()
	ws.shape = BoxShape3D.new()
	(ws.shape as BoxShape3D).size = Vector3(20, 10, 1)
	wall.add_child(ws)
	wall.position = Vector3(0, 2, -8)
	world.add_child(wall)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	var hud: CanvasLayer = load("res://src/main/java/com/openworld/debug/PerfDebugOverlay.java").new()
	root.add_child(hud)
	await _tick(30)

	hud.call("set_level", 0)
	await _tick(20)
	_check("level 0 is hidden", not hud.visible)

	hud.call("set_level", 1)
	await _tick(20)
	var t1: String = hud.call("text_now")
	_check("level 1: the corner FPS counter", hud.visible and t1.begins_with("FPS ") and t1.contains(" ms"), t1)

	hud.call("set_level", 2)
	await _tick(40)
	var t2: String = hud.call("text_now")
	_check("level 2: perf monitors + frame stats", t2.contains("draw ") and t2.contains("orphans") and t2.contains("1%low"))
	_check("level 2: no game state yet", not t2.contains("pos "))

	hud.call("set_level", 3)
	await _tick(40)
	var t3: String = hud.call("text_now")
	print(t3)
	_check("level 3: player position/speed/stance", t3.contains("pos ") and t3.contains("speed ") and t3.contains("stance UPRIGHT"))
	_check("level 3: held weapon and its state", t3.contains("weapon ") and t3.contains("IDLE"))
	_check("level 3: what the crosshair is on", t3.contains("aim "))
	_check("level 3: network line", t3.contains("net offline"))
	hud.call("set_level", 4)
	_check("cycling past 3 wraps to off", int(hud.call("level_now")) == 0)

	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			hud.call("set_level", 3)
			await _tick(60)
			RenderingServer.force_draw()
			await process_frame
			root.get_viewport().get_texture().get_image().save_png(a.substr(7))
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails > 0 else 0)
