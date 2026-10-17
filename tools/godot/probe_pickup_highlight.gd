extends SceneTree
## A dropped weapon GLINTS within 26 m of the camera, and the one E would take wears the FOCUS rim (ui.PickupHighlight,
## user 2026-10-16). Local, cosmetic, no network.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_pickup_highlight.gd [-- --control]
##   xvfb-run -a godot --path . --script tools/godot/probe_pickup_highlight.gd -- --shot   (pictures in user://)
##   --control   the highlighter switched off (console `glint 0`): every look check must FAIL
##
## Checks: a rifle 6 m away glints, a pistol 40 m away does not, the gun at the player's feet whose "[E] Pick up" is on
## offer wears the focus rim (not the glint), the muzzle-flash Glow quad is never dressed, a picked-up gun loses its
## overlay the very next frame (no glint in the hand), and `glint 0` undresses everything.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const GLINT := "res://assets/vfx/outline/pickup_glint.tres"
const FOCUS := "res://assets/vfx/outline/pickup_focus.tres"

var fails := 0
var control := false
var shot := false

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _box(parent: Node, size: Vector3, at: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	b.add_child(mi)
	b.position = at
	parent.add_child(b)

func _overlay(item: Node) -> Material:
	var m: Node = item.get_node_or_null("Model")
	for c in (m if m != null else item).find_children("*", "MeshInstance3D", true, false):
		return (c as MeshInstance3D).material_overlay
	return null

func _glow_dressed(item: Node) -> bool:
	for c in item.find_children("Glow", "MeshInstance3D", true, false):
		if (c as MeshInstance3D).material_overlay != null:
			return true
	return false

func _drop(world: Node, id: String, at: Vector3) -> Node3D:
	var w := (load(WEAPON % id) as PackedScene).instantiate() as Node3D
	world.add_child(w)
	w.global_position = at
	return w

func _shoot(name: String) -> void:
	if not shot:
		return
	await RenderingServer.frame_post_draw
	var img := root.get_viewport().get_texture().get_image()
	img.save_png("user://pickup_highlight_%s.png" % name)
	print("  shot  user://pickup_highlight_%s.png" % name)

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	shot = "--shot" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	_box(world, Vector3(200, 1, 200), Vector3(0, -0.5, 0))
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	world.add_child(sun)
	await _tick(3)
	var gm: Node = root.get_node_or_null("GameManager")
	var ph: Node = gm.get_node_or_null("PickupHighlight") if gm else null
	_check("GameManager built a PickupHighlight", ph != null, "%s" % ph)
	if ph == null:
		quit(1)
		return
	if control:
		ph.call("set_enabled_now", false)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var cam := root.get_viewport().get_camera_3d()
	_check("a camera is current", cam != null, "%s" % cam)

	var near := _drop(world, "ASR1", Vector3(1.5, 0.6, -6))
	var far := _drop(world, "PIS1", Vector3(2, 0.6, -40))
	# the pistol slot filled by walking over one (auto pickup), so the next pistol at the feet is an E offer (a swap)
	_drop(world, "PIS1", p.global_position + Vector3(0, 0.2, 0))
	await _tick(60)
	var feet := (load(WEAPON % "PIS2") as PackedScene).instantiate() as Node3D
	feet.set("require_interact", true)
	world.add_child(feet)
	feet.global_position = p.global_position + Vector3(0, 0.2, 0.3)
	await _tick(90)
	ph.call("scan_now")
	await _tick(2)

	var gl: Material = load(GLINT)
	var fo: Material = load(FOCUS)
	_check("a rifle 6 m away glints", ph.call("look_of", near) == "GLINT" and _overlay(near) == gl,
		"look '%s', overlay %s" % [ph.call("look_of", near), _overlay(near)])
	_check("a pistol 40 m away does not", ph.call("look_of", far) == "" and _overlay(far) == null and not control,
		"look '%s'" % ph.call("look_of", far))
	_check("the gun on offer at the feet wears the rim", ph.call("look_of", feet) == "FOCUS" and _overlay(feet) == fo,
		"look '%s', offers %d" % [ph.call("look_of", feet), gm.call("interact_offers_now") if gm.has_method("interact_offers_now") else -1])
	_check("the muzzle-flash Glow quad is never dressed", not _glow_dressed(near) and not control,
		"glow dressed %s" % _glow_dressed(near))
	if shot:
		# a picture camera over the player's shoulder, the focused pistol at the feet and the rifle 6 m out in view,
		# plus a few more lying about; a burst, since a glint is on only 1/3 of each 1.9 s period
		_drop(world, "MEW6", Vector3(-1.2, 0.5, -3))
		_drop(world, "SNR1", Vector3(-3, 0.5, -14))
		_drop(world, "SMG1", Vector3(3, 0.5, -20))
		var rim := _drop(world, "ASR1", Vector3(0.9, 0.5, 0.2))     # the rim's LOOK, dressed by hand, close up
		await _tick(60)
		ph.call("scan_now")
		var m: Node = rim.get_node_or_null("Model")
		for c in m.find_children("*", "MeshInstance3D", true, false):
			(c as MeshInstance3D).material_overlay = fo
		p.process_mode = Node.PROCESS_MODE_DISABLED     # its camera rig re-takes `current` every frame
		var pc := Camera3D.new()
		world.add_child(pc)
		pc.global_position = Vector3(1.6, 1.4, 2.4)
		pc.look_at(Vector3(0.0, 0.0, -2.0))
		pc.make_current()
		for i in range(8):
			await _tick(10)
			await _shoot("t%d" % i)
		p.process_mode = Node.PROCESS_MODE_INHERIT
		cam.make_current()

	if shot:
		print("  (--shot: the pick-up checks are skipped -- the player was paused for the pictures)")
		quit(0)
		return
	# pick the focused one up with the interact path: its overlay must be gone the next frame
	Input.action_press("interact")
	await _tick(3)
	Input.action_release("interact")
	var ok_use := true
	await _tick(1)
	var lingering := _overlay(feet)
	await _tick(20)
	var held := feet.get_node_or_null("..") != null and not String(feet.get_parent().get_class()).contains("RigidBody")
	_check("picked up, the gun is held", held, "parent %s (used %s)" % [feet.get_parent().name, ok_use])
	_check("a held gun wears no overlay", _overlay(feet) == null and held and not control,
		"overlay %s (1 frame after E: %s)" % [_overlay(feet), lingering])

	ph.call("set_enabled_now", false)
	await _tick(2)
	_check("`glint 0` undresses everything", int(ph.call("dressed_count")) == 0 and _overlay(near) == null and not control,
		"%d dressed" % ph.call("dressed_count"))
	print("")
	print("probe_pickup_highlight: %s (%d fail)%s" % ["PASS" if fails == 0 else "FAIL", fails, " [control]" if control else ""])
	quit(1 if fails > 0 else 0)
