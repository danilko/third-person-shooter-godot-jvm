## A full-body render of one clip AS THE GAME PLAYS IT: the shipped body scene, the shared animation
## library (character_anims.res, what every body's AnimationTree reads), a real renderer. Runs WITH a
## display (xvfb-run is fine), never --headless: the dummy renderer draws nothing.
##
##   xvfb-run -a /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . \
##       --script tools/godot/shot_clip_pose.gd -- --clip=upright_aim_rifle --out=/tmp/shots [--tag=after] [--time=0]
##
## Writes <out>/<tag>_<view>.png for the views front / side / back34. Made to compare a clip before and
## after an edit in Blender (PLAN.md 6.17): the Blender renders show the .blend, this shows the export.
extends SceneTree

const BODY := "res://assets/characters/shino/shino.tscn"
const LIB := "res://src/main/resources/com/openworld/character/anim/character_anims.res"


func _arg(name: String, default: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return default


func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var s := _find_skeleton(c)
		if s != null:
			return s
	return null


func _initialize() -> void:
	var clip := _arg("clip", "upright_aim_rifle")
	var out := _arg("out", "/tmp/shots")
	var tag := _arg("tag", "shot")
	var t := float(_arg("time", "0"))
	DirAccess.make_dir_recursive_absolute(out)

	var root := Node3D.new()
	get_root().add_child(root)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.08, 0.08, 0.1)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.55, 0.55, 0.6)
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	root.add_child(sun)

	var body: Node3D = load(BODY).instantiate()
	root.add_child(body)
	await process_frame
	var skel := _find_skeleton(body)
	if skel == null:
		push_error("no Skeleton3D in %s" % BODY)
		quit(1)
		return
	# the library's tracks are `Skeleton3D:<bone>` -- relative to the skeleton's PARENT
	var ap := AnimationPlayer.new()
	skel.get_parent().add_child(ap)
	ap.root_node = ap.get_path_to(skel.get_parent())
	ap.add_animation_library("", load(LIB))
	if not ap.has_animation(clip):
		push_error("clip %s is not in the library" % clip)
		quit(1)
		return
	ap.play(clip)
	ap.seek(t, true)
	ap.pause()

	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 1.9
	root.add_child(cam)
	cam.make_current()
	# the game's body faces -Z
	var views := {"front": Vector3(0, 0.85, -4), "side": Vector3(4, 0.85, 0), "back34": Vector3(-2.8, 1.0, 2.8)}
	for v in views:
		cam.global_position = views[v]
		cam.look_at(Vector3(0, 0.85, 0), Vector3.UP)
		for i in 4:
			await process_frame
		RenderingServer.force_draw()
		await process_frame
		var img := get_root().get_texture().get_image()
		img.save_png("%s/%s_%s.png" % [out, tag, v])
		print("[shot_clip_pose] %s/%s_%s.png" % [out, tag, v])
	quit(0)
