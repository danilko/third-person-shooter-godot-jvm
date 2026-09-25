extends SceneTree
## shot_buildings.gd -- render each generated building (needs a DISPLAY; no --headless).
##
##   godot --path . --script tools/godot/shot_buildings.gd -- <out_dir> [--only=Id,Id] [--views=front,back,door]
##
## A daylight sky and sun, a ground plane, the building at the origin and a 1.49 m capsule (the character's
## height) outside its first door, so the scale reads. Writes <out_dir>/<Id>_<view>.png. A view: `front` 3/4 from the
## front-left, `back` 3/4 from the back-right, `door` close on the first door at eye height, `plan` straight down from
## just under the ceiling (orthographic, the roof behind the camera, shadows off) -- the floor plan, which is the only
## way to check an interior's layout (which way a counter faces, whether a room has its door); not in the default set.

const DIR := "res://src/main/resources/com/openworld/world/buildings"

var _out := ""
var _jobs := []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if args.size() > 0 else "user://building_shots"
	var only := []
	var views := ["front", "back", "door"]
	for a in args:
		if a.begins_with("--only="):
			only = a.substr(7).split(",")
		if a.begins_with("--views="):
			views = Array(a.substr(8).split(","))
	DirAccess.make_dir_recursive_absolute(_out)
	for f in DirAccess.get_files_at(DIR):
		if not f.ends_with(".tscn") or f in ["Door.tscn", "Breakable.tscn"]:
			continue
		var id := f.get_basename()
		if not only.is_empty() and not only.has(id):
			continue
		for v in views:
			_jobs.append([id, v])
	root.size = Vector2i(1600, 1000)
	_run.call_deferred()


func _run() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	e.sky = Sky.new()
	e.sky.sky_material = ProceduralSkyMaterial.new()
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.environment = e
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -35, 0)
	sun.shadow_enabled = true
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(200, 200)
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.42, 0.42, 0.4)
	pm.material = gm
	ground.mesh = pm
	ground.position.y = -0.02
	root.add_child(ground)
	var cam := Camera3D.new()
	cam.fov = 55
	root.add_child(cam)
	cam.make_current()

	for job in _jobs:
		var id: String = job[0]
		var view: String = job[1]
		var inst: Node3D = (load("%s/%s.tscn" % [DIR, id]) as PackedScene).instantiate()
		root.add_child(inst)
		var meta: Dictionary = inst.get_meta("building")
		var fp: Array = meta["footprint_m"]
		var h: float = meta["height_m"]
		var man := MeshInstance3D.new()
		var cap := CapsuleMesh.new()
		cap.radius = 0.25
		cap.height = 1.49
		var cm := StandardMaterial3D.new()
		cm.albedo_color = Color(0.9, 0.2, 0.15)
		cap.material = cm
		man.mesh = cap
		var door := Vector3(0, 0, fp[1] / 2.0)
		var outward := Vector3(0, 0, 1)
		for c in inst.get_children():
			if c is Marker3D and c.name.begins_with("Door_"):
				door = c.position
				outward = -(c as Marker3D).transform.basis.z
				break
		man.position = door + outward * 1.2 + outward.cross(Vector3.UP) * 0.9 + Vector3(0, 0.745, 0)
		root.add_child(man)
		var r: float = max(fp[0], fp[1], h) * 1.35 + 6.0
		cam.projection = Camera3D.PROJECTION_PERSPECTIVE
		sun.shadow_enabled = true
		match view:
			"plan":
				cam.projection = Camera3D.PROJECTION_ORTHOGONAL
				cam.size = max(fp[0], fp[1]) * 1.1
				cam.position = Vector3(0, 3.2, 0)
				cam.near = 0.05
				cam.rotation_degrees = Vector3(-90, 0, 0)
				sun.shadow_enabled = false
			"front":
				cam.position = Vector3(-0.55 * r, 0.45 * h + 3.0, 0.85 * r)
				cam.look_at(Vector3(0, 0.4 * h, 0))
			"back":
				cam.position = Vector3(0.55 * r, 0.45 * h + 3.0, -0.85 * r)
				cam.look_at(Vector3(0, 0.4 * h, 0))
			"door":
				cam.position = door + outward * 6.0 + outward.cross(Vector3.UP) * -2.5 + Vector3(0, 1.4, 0)
				cam.look_at(door + Vector3(0, 1.2, 0))
		for i in 12:
			await process_frame
		var img := root.get_texture().get_image()
		var path := "%s/%s_%s.png" % [_out, id, view]
		img.save_png(path)
		print("SHOT ", path)
		inst.queue_free()
		man.queue_free()
		await process_frame
	quit(0)
