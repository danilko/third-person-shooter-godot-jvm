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
## are comparable; `--no-buildings` is the control. `--fogs=` takes the haze variants (PLAN.md 2b, see _set_fog).
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


## `--fogs=off;0,700,0.001;sky:0,1000,0.0007+depth:550,700+far:700;...` (PLAN.md 2b): per shot, one picture
## per variant. A variant is `off` or `+`-joined parts:
##   `start,end,density` or `sky:start,end,density` -- Sky3D's screen fog (SkyDome fog_start/end/density);
##   `depth:begin,end[,curve]` -- Godot's DEPTH fog on the Environment, fully opaque at `end`, coloured by the sky
##     behind it (fog_aerial_perspective 1), the sky itself left clear (fog_sky_affect 0);
##   `far:D` -- the camera's far plane (note: it also clips Sky3D's own fog layer, so the sky changes);
##   `cull:D` -- every mesh outside the terrain and the sky gets visibility_range_end <= D + its own radius (its
##     nearest point is then at least D away, i.e. fully fogged), which is what a `world.ViewDistance` would do; a
##     mesh wider than CULL_MAX_R (a cell's lots, its HLOD) is left alone. A `cull` picture must match the same
##     variant without it.
var _ranges := {}
const CULL_MAX_R := 150.0


func _cull(d: float) -> void:
	var stack: Array = [w]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n.name == "Sky3D" or n.get_class() == "Terrain3D":
			continue
		if n is GeometryInstance3D:
			var g := n as GeometryInstance3D
			var id := g.get_instance_id()
			if not _ranges.has(id):
				_ranges[id] = g.visibility_range_end
			var orig: float = _ranges[id]
			var r := g.get_aabb().size.length() * 0.5
			if g is MultiMeshInstance3D or r > CULL_MAX_R:
				r = INF
			var e := d + r
			g.visibility_range_end = e if d > 0.0 and r < INF and (orig <= 0.0 or orig > e) else orig
		for c in n.get_children():
			stack.append(c)


func _set_fog(spec: String) -> void:
	var sky := w.get_node_or_null("Sky3D")
	var dome := w.get_node_or_null("Sky3D/SkyDome")
	if sky == null or dome == null:
		return
	var env: Environment = sky.get("environment")
	sky.set("fog_enabled", false)
	if env != null:
		env.fog_enabled = false
	cam.far = 4000.0
	_cull(0.0)
	if spec == "off":
		return
	for part in spec.split("+", false):
		var kind := "sky"
		var body := str(part)
		if body.contains(":"):
			kind = body.get_slice(":", 0)
			body = body.get_slice(":", 1)
		var v := body.split(",")
		match kind:
			"sky":
				sky.set("fog_enabled", true)
				dome.set("fog_visible", true)
				dome.set("fog_start", float(v[0]))
				dome.set("fog_end", float(v[1]))
				if v.size() > 2:
					dome.set("fog_density", float(v[2]))
			"depth":
				env.fog_enabled = true
				env.fog_mode = Environment.FOG_MODE_DEPTH
				env.fog_depth_begin = float(v[0])
				env.fog_depth_end = float(v[1])
				env.fog_depth_curve = float(v[2]) if v.size() > 2 else 1.0
				env.fog_density = 1.0
				env.fog_height_density = 0.0
				env.fog_aerial_perspective = 1.0
				env.fog_sky_affect = 0.0
			"far":
				cam.far = float(v[0])
			"cull":
				_cull(float(v[0]))


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
	# the clouds drift with the wind: freeze them so two variants of one shot differ only by the variant
	root.add_child(w)
	current_scene = w
	for n in ["Sky3D", "Sky3D/SkyDome"]:
		var s3 := w.get_node_or_null(n)
		if s3 != null:
			s3.set("wind_speed", 0.0)
	var player := w.get_node_or_null("Characters/Player")
	if player != null:
		player.get_node("Health").set("max_health", 1000000.0)
		player.set_physics_process(false)
		player.visible = false
		# the Player's camera rigs rewrite the CURRENT camera every frame even with the player's own processing off
		# (CLAUDE.md, the night-lights probe trap): switch them off, or every picture is taken from behind the player
		# frozen whole: its camera rigs rewrite the CURRENT camera every frame even with its own processing off
		# (CLAUDE.md, the night-lights probe trap), and its movement would carry it off the viewpoint
		player.process_mode = Node.PROCESS_MODE_DISABLED
	# --fogs sets the fog and the cut by hand, so world.ViewDistance (which owns both in the game) stands down
	var vd := root.get_node_or_null("ViewDistance")
	if vd != null and _arg("fogs") != null:
		vd.call("set_enabled_now", false)
		await process_frame
		await process_frame
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
			# the game places the local player at its spawn a few frames after it is ready: place it again once that
			# has happened, or the streamer loads the spawn's surroundings and the picture shows bare terrain
			for i in 30:
				await process_frame
			player.global_position = Vector3(look.x, look.y + 1.0, look.z)
		await _settle(40.0)
		cam.make_current()
		cam.global_position = at
		cam.look_at(look, Vector3.UP)
		await process_frame
		await process_frame
		var fogs: Array = str(_arg("fogs", [""])[0]).split(";", false)
		if fogs.is_empty():
			fogs = [""]
		for fog in fogs:
			var tag := ""
			if fog != "":
				tag = "_fog_" + str(fog).replace(",", "-").replace(":", "").replace("+", "_")
				_set_fog(str(fog))
				for i in 6:
					await process_frame
			RenderingServer.force_draw()
			var path := "%s/%s%s.png" % [out, p[0], tag]
			root.get_texture().get_image().save_png(path)
			print("shot %s  cam %.1f,%.1f,%.1f -> %.1f,%.1f,%.1f" % [path, at.x, at.y, at.z, look.x, look.y, look.z])
			if vd != null and fog == "":
				print("view distance %.0f m, cut %.0f m, %d meshes" % [vd.call("distance_now"), vd.call("cull_now"), vd.call("tracked_now")])
	quit(0)
