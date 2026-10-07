extends SceneTree
## THE REAR-VIEW MIRROR (ui.RearViewMirror, user 2026-10-07). NEEDS A DISPLAY (a headless run has no renderer, so
## the mirror's cost would read as nothing).
##
##   <godot> --path . --script tools/godot/probe_rear_view.gd [-- --world=island] [--shot=<dir>] [--secs=8]
##
## The scene's own placed car (VehicleRoot): the local Player is seated in it, and:
##   1. on foot the mirror is hidden;
##   2. driving in the CHASE view it shows and looks straight back (camera forward . car forward < -0.95), and renders
##      at about half the frame rate (updateEvery 2);
##   3. in the first-person (cockpit) view it shows and looks back too;
##   4. the rear_view key (C) hides it and stops it rendering, and brings it back; hidden, then out of the car and in
##      again, it is ON (it starts on every time the player takes the wheel);
##   5. the COST: frame ms p50/p95 and draw calls with the mirror on vs off, the car parked in the street.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const ISLAND := "res://src/main/resources/com/openworld/world/World.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _arg(k: String, d: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + k + "="):
			return a.substr(k.length() + 3)
	return d


func _frames(n: int) -> void:
	for i in n:
		await process_frame


func _press(a: String) -> void:
	Input.action_press(a)
	await _frames(3)
	Input.action_release(a)
	await _frames(3)


func _measure(secs: float) -> Array:
	var ft: Array[float] = []
	var dc: Array[float] = []
	var t0 := Time.get_ticks_msec()
	var last := Time.get_ticks_usec()
	while Time.get_ticks_msec() - t0 < int(secs * 1000.0):
		await process_frame
		var now := Time.get_ticks_usec()
		ft.append((now - last) / 1000.0)
		last = now
		dc.append(float(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)))
	ft.sort()
	dc.sort()
	return [ft[ft.size() / 2], ft[int(ft.size() * 0.95)], dc[dc.size() / 2]]


func _initialize() -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var island := _arg("world", "debug") == "island"
	var secs := float(_arg("secs", "8"))
	var shot := _arg("shot", "")
	var world: Node = (load(ISLAND if island else DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _frames(240)
	var player: Node = world.get_node("Characters/Player")
	var car: RigidBody3D = world.get_node("VehicleRoot")
	var mirror: Node = root.find_child("RearViewMirror", true, false)
	_check(mirror != null, "the HUD built the mirror")
	if mirror == null:
		quit(1)
		return
	_check(not bool(mirror.call("shown_now")), "on foot the mirror is hidden")
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	player.set("collision_layer", 0)
	player.set("collision_mask", 0)
	helper.call("seat_character", car, player)
	await _frames(90)
	var r0 := int(mirror.call("renders_now"))
	var f0 := Engine.get_process_frames()
	await _frames(60)
	var rate := float(int(mirror.call("renders_now")) - r0) / float(Engine.get_process_frames() - f0)
	var dot := float(mirror.call("look_dot_forward_now"))
	_check(bool(mirror.call("shown_now")), "driving (chase view), the mirror shows")
	_check(dot < -0.95, "chase view: it looks straight back (dot %.3f)" % dot)
	_check(rate > 0.4 and rate < 0.6, "it renders every other frame (%.2f renders/frame)" % rate)
	if shot != "":
		DirAccess.make_dir_recursive_absolute(shot)
		root.get_viewport().get_texture().get_image().save_png(shot.path_join("rear_view_chase.png"))
	# the cost: settle (streaming round a fresh spawn is the noise), then ON / OFF alternated, medians averaged
	await _frames(60 * 10)
	var on := [0.0, 0.0, 0.0]
	var off := [0.0, 0.0, 0.0]
	var hidden_ok := true
	for round in 3:
		var a := await _measure(secs / 3.0)
		await _press("rear_view")
		if round == 0:
			_check(not bool(mirror.call("shown_now")), "the rear_view key hides it")
		var r1 := int(mirror.call("renders_now"))
		var b := await _measure(secs / 3.0)
		hidden_ok = hidden_ok and int(mirror.call("renders_now")) == r1
		await _press("rear_view")
		for i in 3:
			on[i] += a[i] / 3.0
			off[i] += b[i] / 3.0
	_check(hidden_ok, "hidden, it renders nothing")
	_check(bool(mirror.call("shown_now")), "the key brings it back")
	# hidden, then out of the car and back in: it starts ON again
	await _press("rear_view")
	helper.call("exit_driver", car)
	await _frames(30)
	player.set("collision_layer", 0)
	player.set("collision_mask", 0)
	helper.call("seat_character", car, player)
	await _frames(30)
	_check(bool(mirror.call("shown_now")), "hidden with C, then out and back in: it is on again")
	await _press("view")
	await _frames(30)
	var dot2 := float(mirror.call("look_dot_forward_now"))
	_check(bool(mirror.call("shown_now")) and dot2 < -0.95, "first-person view: it shows and looks back (dot %.3f)" % dot2)
	if shot != "":
		await _frames(10)
		root.get_viewport().get_texture().get_image().save_png(shot.path_join("rear_view_cockpit.png"))
	print("  COST (chase view, parked): mirror ON frame p50 %.2f p95 %.2f ms, %d draws | OFF frame p50 %.2f p95 %.2f ms, %d draws" % [
		on[0], on[1], int(on[2]), off[0], off[1], int(off[2])])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
