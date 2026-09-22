extends SceneTree
##
## One picture of the real world from a named viewpoint, after streaming has settled.
##
##   Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/shot_city.gd -- \
##       --out=/tmp/shots --shot=industry_block:-405,9,700:-405,1,737 [--shot=...] [--fov=70] [--time=12]
##
## NEEDS A DISPLAY (`xvfb-run -a` is enough). A `--headless` run renders with the dummy renderer, which
## drops MultiMesh transforms -- so the lots and the street furniture would be missing from the picture,
## which is exactly what the picture is being taken to judge.
##
## `--shot` is `<name>:<camera x,y,z>:<target x,y,z>`. The sun is pinned to `--time` (noon) so two runs
## are comparable; `--no-buildings` is the control.
##

var w: Node3D
var cam: Camera3D


func _arg(key: String, dflt: Variant = null) -> Variant:
	var out := []
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % key):
			out.append(a.substr(key.length() + 3))
		elif a == "--%s" % key:
			out.append("1")
	if out.is_empty():
		return dflt
	return out


func _vec(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2]))


func _settle(seconds: float) -> void:
	var last := -1
	var still := 0
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < seconds * 1000.0:
		await process_frame
		var n := 0
		for holder in ["BuildingZones", "RoadZones", "SiteZones"]:
			var h := w.get_node_or_null(holder)
			if h != null:
				for m in h.get_children():
					n += m.get_child_count() * 7 + 1
		if n == last:
			still += 1
		else:
			still = 0
			last = n
		if Time.get_ticks_msec() - t0 > 4000 and still > 120:
			return


func _initialize() -> void:
	_run()


func _run() -> void:
	await process_frame
	var out := str(_arg("out", ["/tmp"])[0])
	DirAccess.make_dir_recursive_absolute(out)
	w = load("res://src/main/resources/com/openworld/world/World.tscn").instantiate()
	if _arg("no-buildings") != null:
		var h := w.get_node_or_null("BuildingZones")
		if h != null:
			w.remove_child(h)
			h.free()
		print("CONTROL: no BuildingZones")
	var tod := w.get_node_or_null("Sky3D/TimeOfDay")
	if tod != null:
		tod.set("game_time_enabled", false)
		tod.set("current_time", float(str(_arg("time", ["12"])[0])))
	root.add_child(w)
	current_scene = w
	var player := w.get_node_or_null("Characters/Player")
	if player != null:
		player.get_node("Health").set("max_health", 1000000.0)
		player.set_physics_process(false)
		player.visible = false
	cam = Camera3D.new()
	cam.far = 4000.0
	cam.fov = float(str(_arg("fov", ["70"])[0]))
	w.add_child(cam)
	await process_frame
	cam.make_current()
	for spec in _arg("shot", []):
		var p := str(spec).split(":")
		var at := _vec(p[1])
		var look := _vec(p[2])
		cam.global_position = at
		cam.look_at(look, Vector3.UP)
		# the streamer keys on the player, not on the camera
		if player != null:
			player.global_position = Vector3(look.x, look.y + 1.0, look.z)
		await _settle(40.0)
		await process_frame
		await process_frame
		RenderingServer.force_draw()
		var path := "%s/%s.png" % [out, p[0]]
		root.get_texture().get_image().save_png(path)
		print("shot %s  cam %.1f,%.1f,%.1f -> %.1f,%.1f,%.1f" % [path, at.x, at.y, at.z, look.x, look.y, look.z])
	quit(0)
