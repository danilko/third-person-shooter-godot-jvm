extends SceneTree
## A ガードレール module is a RAIL to BreakableProps, not a post (user, 2026-10-11: "destructible ガードレール").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_guardrail.gd
##   ... -- --control      (pole_half_length 0: the batch is a row of POSTS, the world before this)
##
## A flat slab, one BreakableProps batch of five 4 m modules laid end to end along X (built here exactly as
## WorldBaker builds one: positions, yaws, pole_half_width 0.1, pole_height 0.8, pole_half_length 2), the middle one
## pitched to a grade. A car is driven square at a module 1.6 m from its POST -- at the beam, where a post-sized test
## sees nothing:
##   1. 15 m/s: the module goes down before the car touches it, the car keeps >= 85 % of its speed and drives on;
##      the modules two away stand;
##   2. 3 m/s: the module stands and the car stops against the BEAM (the collider is the module's whole length);
##   3. a ray down onto the beam 1.6 m from the post finds the collider; 0.6 m beside the beam it finds the slab.
## The control (posts): case 1's car is never asked about the beam, so the module stands; cases 2 and 3 find no beam.

const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const PROPS := "res://src/main/java/com/openworld/world/BreakableProps.java"
const OFF := 1.6          # m from the post, along the beam, where the car hits

var world: Node3D
var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _rails(control: bool, at: Vector3) -> Node:
	var b: MultiMeshInstance3D = load(PROPS).new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.2, 0.8, 4.0)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = 5
	b.multimesh = mm
	var pos := PackedVector3Array()
	var yaw := PackedFloat32Array()
	for k in 5:
		pos.append(at + Vector3((k - 2) * 4.0, 0, 0))
		yaw.append(PI * 0.5)                      # the module's own Z (its length) along world X
	b.set("positions", pos)
	b.set("yaws", yaw)
	b.set("pitches", PackedFloat32Array([0.0, 0.0, 0.05, 0.0, 0.0]))
	b.set("pole_half_width", 0.1)
	b.set("pole_height", 0.8)
	b.set("pole_half_length", 0.0 if control else 2.0)
	b.set("mass", 60.0)
	b.set("break_speed", 6.0)
	b.set("asset_name", "Guardrail_JP")
	world.add_child(b)
	return b

func _drive(target: Vector3, speed: float, b: Node) -> Dictionary:
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = target + Vector3(0, 0.8, 22.0)
	var r := {"past": -INF, "after": 0.0, "broke": -1}
	var held := true
	var after := -1
	for f in 60 * 12:
		var p := car.global_position
		var along := target.z - p.z
		r["past"] = maxf(r["past"], along)
		if held:
			car.linear_velocity = Vector3(0, car.linear_velocity.y, -speed)
			held = p.z - target.z > 7.0
		if r["broke"] < 0 and bool(b.call("pole_broken_now", 2)):
			r["broke"] = f
			after = 12
		if after > 0:
			after -= 1
			if after == 0:
				r["after"] = absf(car.linear_velocity.z)
		if not held and (car.linear_velocity.length() < 0.2 or along > 6.0) and f > 90:
			break
		await physics_frame
	r["final"] = car.linear_velocity.length()
	car.queue_free()
	await physics_frame
	return r

func _ray(p: Vector3) -> String:
	var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, 3, 0), p + Vector3(0, -1, 0))
	var hit := world.get_world_3d().direct_space_state.intersect_ray(q)
	return "" if hit.is_empty() else str(hit.collider.name)

func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	world = Node3D.new()
	root.add_child(world)
	current_scene = world
	var slab := StaticBody3D.new()
	slab.name = "Slab"
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	cs.position = Vector3(0, -0.5, 0)
	slab.add_child(cs)
	world.add_child(slab)
	print("probe_guardrail%s" % (" (CONTROL: posts, pole_half_length 0)" if control else ""))

	var b := _rails(control, Vector3.ZERO)
	for f in 20:
		await physics_frame
	var hit := Vector3(OFF, 0, 0)
	_check(_ray(hit + Vector3(0, 0, 0)) == "Poles", "a ray down onto the beam %.1f m from the post finds the rail's collider (%s)" % [OFF, _ray(hit)])
	_check(_ray(hit + Vector3(0, 0, 0.6)) == "Slab", "0.6 m beside the beam there is no collider (%s)" % _ray(hit + Vector3(0, 0, 0.6)))

	print("case 1: 15 m/s square at the beam")
	var r := await _drive(hit, 15.0, b)
	print("  broke at tick %d, %.2f m/s 0.2 s after, got %.1f m past" % [r["broke"], r["after"], r["past"]])
	_check(bool(b.call("pole_broken_now", 2)), "the module went down")
	_check(r["after"] >= 15.0 * 0.85, "the car kept >= 85 %% of its speed (%.0f %%)" % (r["after"] / 15.0 * 100.0))
	_check(r["past"] > 4.0, "the car drove on (%.1f m past)" % r["past"])
	_check(not bool(b.call("pole_broken_now", 0)) and not bool(b.call("pole_broken_now", 4)),
			"the modules two away stand (the one beside it may go: the car is 1.8 m wide and hits 0.4 m from the joint)")
	b.queue_free()
	await physics_frame

	print("case 2: 3 m/s square at the beam")
	b = _rails(control, Vector3(0, 0, -60))
	for f in 20:
		await physics_frame
	r = await _drive(Vector3(OFF, 0, -60), 3.0, b)
	print("  got %.2f m past the rail line, final %.2f m/s" % [r["past"], r["final"]])
	_check(not bool(b.call("pole_broken_now", 2)), "the module stands")
	_check(r["past"] < 0.0, "the car stopped against the beam (%.2f m short of the rail's line)" % -r["past"])

	print("RESULT: %s (%d fail)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
