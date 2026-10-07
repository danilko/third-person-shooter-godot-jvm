extends SceneTree
## A body that dies standing plays the death CLIP and falls away from its killer; the ragdoll is kept for the air, for
## blasts and for cars; and game.WorldJanitor clears the corpses and the dropped weapons once nobody looks (user
## 2026-10-07: "the ragdoll falls in strange directions", "bodies and weapons stay lying round the konbini").
##
##   godot --headless --path . --script tools/godot/probe_death_anim.gd [-- --control]
##   (--control: deathAnimation off -- every death is the ragdoll, and the clip checks fail)
##
## Real AICharacter.tscn bodies (they drop their weapons through the ordinary death path), real ImpactManager /
## ExplosionManager hits through debug/VehicleProbeHelper, the real GameManager-built WorldJanitor.

const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"

var fails := 0
var helper: Node
var im: Node
var em: Node
var stand: Node3D
var cam: Camera3D

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-60s %s" % ["PASS" if ok else "FAIL", label, detail])

func _ai(at: Vector3, yaw: float) -> Node3D:
	var a: Node3D = (load(AI) as PackedScene).instantiate()
	stand.add_child(a)
	a.global_position = at
	a.rotation.y = yaw
	if OS.get_cmdline_user_args().has("--control"):
		a.set("death_animation", false)
	for i in 30:
		await physics_frame
	return a

func _alive(a: Node) -> bool:
	return float(a.get_node("Health").call("health_now")) > 0.0

func _mesh_root(a: Node) -> Node3D:
	return a.find_child("MeshRoot", true, false) as Node3D

func _head_y(a: Node) -> float:
	var b := a.find_child("Physical Bone head_2", true, false) as Node3D
	return b.global_position.y - a.global_position.y if b else 99.0

func _initialize() -> void:
	stand = Node3D.new()
	root.add_child(stand)
	current_scene = stand
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor_body.add_child(cs)
	stand.add_child(floor_body)
	floor_body.position = Vector3(0, -0.5, 0)
	cam = Camera3D.new()
	stand.add_child(cam)
	cam.global_position = Vector3(0, 3, 12)
	cam.current = true
	helper = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	em = load("res://src/main/java/com/openworld/world/manager/ExplosionManager.java").new()
	im = load("res://src/main/java/com/openworld/world/manager/ImpactManager.java").new()
	stand.add_child(helper)
	stand.add_child(em)
	stand.add_child(im)
	await process_frame
	var gm := root.get_node_or_null("GameManager")
	var jan: Node = gm.get_node_or_null("WorldJanitor") if gm else null

	print("== 1. shot from the east while facing north: the clip plays and the body turns to face the shooter")
	# armed through a real pickup, so its death drops a weapon the ordinary way
	var gun: Node3D = (load("res://src/main/resources/com/openworld/weapon/ASR1.tscn") as PackedScene).instantiate()
	stand.add_child(gun)
	gun.global_position = Vector3(0, 0.5, 0)
	for i in 10:
		await physics_frame
	var a := await _ai(Vector3(0, 0, 0), 0.0)
	for i in 60:
		await physics_frame
	var shooter := Vector3(20, 1.2, 0)
	var y0 := _head_y(a)
	helper.call("bone_hit_from", im, a, "spine_03", shooter, 1.0e6)
	await physics_frame
	_check("dead", not _alive(a))
	_check("the death is the clip, not the ragdoll", bool(a.call("death_clip_now")))
	var mr := _mesh_root(a)
	var fwd := -mr.global_transform.basis.z if mr else Vector3.ZERO
	var to_shooter := (shooter - a.global_position)
	to_shooter.y = 0
	var dot := Vector3(fwd.x, 0, fwd.z).normalized().dot(to_shooter.normalized())
	_check("the body faces its killer (falls away from it)", dot > 0.95, "dot %.3f" % dot)
	for i in 150:
		await physics_frame
	var y1 := _head_y(a)
	_check("after 2.5 s the body is on the ground", y1 < 0.7 and y0 > 1.2, "head %.2f -> %.2f m" % [y0, y1])
	var pelvis := a.find_child("Physical Bone pelvis", true, false) as Node3D
	var away := (pelvis.global_position - a.global_position) if pelvis else Vector3.ZERO
	_check("it fell AWAY from the shooter (west)", away.x < -0.2, "pelvis %.2f m along +x" % away.x)

	print("== 2. a body killed in the air, and one killed by a blast, are the ragdoll")
	var b := await _ai(Vector3(6, 0, 0), 0.0)
	b.global_position = Vector3(6, 4, 0)
	b.call("set_velocity", Vector3(0, -2, 0))
	await physics_frame
	await physics_frame
	helper.call("kill", b)
	await physics_frame
	_check("killed in the air -> ragdoll", not bool(b.call("death_clip_now")))
	var c := await _ai(Vector3(-6, 0, 0), 0.0)
	helper.call("blast", em, c.global_position + Vector3(1.0, 0.3, 0), 6.0, 1.0e6)
	await physics_frame
	_check("killed by a blast -> ragdoll (the throw is the point)", not _alive(c) and not bool(c.call("death_clip_now")))

	print("== 3. the janitor clears corpses and dropped weapons once nobody looks")
	_check("the WorldJanitor exists", jan != null)
	if jan:
		var drops := 0
		for n in get_nodes_in_group("pickups"):
			if n.has_meta("dropped_at_ms"):
				drops += 1
		cam.current = true
		await create_timer(1.5).timeout       # a sweep never takes a body dead under 1 s
		jan.call("sweep_now", true)
		await physics_frame
		_check("in view: nothing is cleared yet", is_instance_valid(a), "freed " + str(jan.call("freed_now")))
		cam.global_position = Vector3(0, 3, 500)
		cam.look_at(Vector3(0, 3, 1000))
		cam.current = true
		await process_frame
		jan.call("sweep_now", true)
		await process_frame
		await process_frame
		_check("out of view: every corpse is gone", not is_instance_valid(a) and not is_instance_valid(b) and not is_instance_valid(c),
			"freed %s, left a=%s b=%s c=%s" % [str(jan.call("freed_now")), is_instance_valid(a), is_instance_valid(b), is_instance_valid(c)])
		var left := 0
		for n in get_nodes_in_group("pickups"):
			if n.has_meta("dropped_at_ms") and not n.is_queued_for_deletion():
				left += 1
		_check("out of view: every dropped weapon is gone", drops > 0 and left == 0, "%d dropped, %d left" % [drops, left])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
