extends SceneTree
## Measures every explosion effect's visible reach and writes it into the effect scene (needs a display):
## `blast_radius` = how far the shockwave (the `Rings` layer) reaches at scale 1, `fireball_radius` = the fireball
## (`Core`). ExplosionManager scales a blast by damage radius / blast_radius, so the shockwave ends where the damage
## does. Each layer is rendered alone, top-down and orthographic over black, through its whole animation; the reach
## is the furthest CLEARLY visible pixel from the centre (alpha and brightness over a threshold).
##
##   /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/measure_explosion_radii.gd [-- --check]
## --check writes nothing and exits 1 when a stored radius is more than 15% off a fresh measurement (particle
## spawns are random, so two runs of one effect differ by up to ~10%).

const DIR := "res://assets/vfx/explosion/effects"
const VIEW_M := 30.0          # the orthographic view spans 30 m (the largest effect, a nuke ring, fits)
const PX := 300
const VISIBLE := 3 * 110 * 140   # sum(rgb) x alpha: a pixel the eye reads against a dark scene
var cam: Camera3D

func _files(dir: String) -> Array[String]:
	var out: Array[String] = []
	var d := DirAccess.open(dir)
	for sub in d.get_directories():
		for f in DirAccess.open(dir + "/" + sub).get_files():
			if f.ends_with(".tscn"):
				out.append(dir + "/" + sub + "/" + f)
	out.sort()
	return out

## Furthest lit pixel from the image centre over the effect's run, in metres, with only `layer` visible.
func _reach(path: String, layer: String) -> float:
	var fx: Node3D = (load(path) as PackedScene).instantiate()
	root.add_child(fx)
	for c in fx.get_children():
		if c is GeometryInstance3D:
			(c as Node3D).visible = String(c.name) == layer
		if c is Light3D:
			(c as Light3D).visible = false
	await process_frame
	fx.call("play")
	var best := 0.0
	var frames := int(ceil(float(fx.call("main_length_now")) * 60.0)) + 30   # the whole run: a fireball can peak late
	for f in range(frames):
		await process_frame
		if f % 3 != 0:
			continue
		RenderingServer.force_draw()
		var img := root.get_viewport().get_texture().get_image()
		img.convert(Image.FORMAT_RGBA8)
		# the furthest CLEARLY VISIBLE pixel (alpha x brightness over VISIBLE): a layer's quads carry near-zero
		# alpha well past what the eye sees, and counting them overstated the shockwave's reach ~3x
		var data := img.get_data()
		var w := img.get_width()
		var h := img.get_height()
		var c := Vector2(w / 2.0, h / 2.0)
		var m_per_px := VIEW_M / float(h)
		for y in range(0, h, 2):
			var row := y * w * 4
			for x in range(0, w, 2):
				var i := row + x * 4
				var a := data[i + 3]
				if a < 90:
					continue
				if (data[i] + data[i + 1] + data[i + 2]) * a < VISIBLE:
					continue
				best = maxf(best, Vector2(x, y).distance_to(c) * m_per_px)
	fx.queue_free()
	await process_frame
	return best

func _initialize() -> void:
	var check := OS.get_cmdline_user_args().has("--check")
	# the project opens maximised; a small fixed window keeps the per-pixel scan quick and the scale known
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(Vector2i(PX, PX))
	root.size = Vector2i(PX, PX)
	await process_frame
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_CLEAR_COLOR
	root.add_child(env)
	root.transparent_bg = true
	cam = Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = VIEW_M
	root.add_child(cam)
	cam.current = true
	cam.look_at_from_position(Vector3(0, 60, 0.001), Vector3.ZERO)
	var bad := 0
	for path in _files(DIR):
		var ring := await _reach(path, "Rings")
		var core := await _reach(path, "Core")
		var text := FileAccess.get_file_as_string(path)
		var stored := _stored(text, "blast_radius")
		var off := absf(stored - ring) > 0.15 * maxf(ring, 0.1)   # particles are random: a re-measure varies ~10%
		print("%-48s shockwave %5.2f m  fireball %5.2f m%s" % [path.get_file(), ring, core,
			("  (stored %.2f)" % stored) if check else ""])
		if check:
			bad += 1 if off else 0
			continue
		FileAccess.open(path, FileAccess.WRITE).store_string(_store(_store(text, "blast_radius", ring), "fireball_radius", core))
	print("RESULT %s" % ("PASS" if bad == 0 else "FAIL (%d stale)" % bad))
	quit(1 if bad > 0 else 0)

func _stored(text: String, key: String) -> float:
	var re := RegEx.create_from_string("(?m)^%s = ([0-9.]+)$" % key)
	var m := re.search(text)
	return float(m.get_string(1)) if m else 0.0

## Set `key = value` on the ROOT node block (the first [node] with no parent): replace the line if present,
## else add it as the block's last property.
func _store(text: String, key: String, value: float) -> String:
	var lines := Array(text.split("\n"))
	var start := -1
	for i in range(lines.size()):
		if String(lines[i]).begins_with("[node") and not String(lines[i]).contains("parent="):
			start = i
			break
	if start < 0:
		return text
	var end := start + 1
	while end < lines.size() and String(lines[end]) != "" and not String(lines[end]).begins_with("["):
		end += 1
	var entry := "%s = %.2f" % [key, value]
	for i in range(start + 1, end):
		if String(lines[i]).begins_with(key + " = "):
			lines[i] = entry
			return "\n".join(PackedStringArray(lines))
	lines.insert(end, entry)
	return "\n".join(PackedStringArray(lines))
