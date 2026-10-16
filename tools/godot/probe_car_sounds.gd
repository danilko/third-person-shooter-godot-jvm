extends SceneTree
## PLAN.md F11 -- a car's horn, tyre squeal and crash sounds (carrier.vehicle.CarSounds).
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_car_sounds.gd [-- --car=SPC1]
##   OW_CAR_SOUNDS=0 ... -- --expect=off      (the control: nothing may sound)
## A real Player at the wheel through `Input`, a camera on the car (the cost rule measures the distance to it):
##   1. horn: held 1 s -> the horn loop sounds; released -> it stops within 2 frames;
##   2. squeal: straight at 20 m/s with no pedal -> NO squeal; handbrake + full steer at 20 m/s -> it squeals, louder
##      the harder it slides; stopped -> the player is freed;
##   3. crash: 2 m/s into a wall -> no crash sound (under VehicleDamageRules.MIN_IMPACT_DV); 15 m/s -> one or more;
##   4. distance: the same squeal with the camera 200 m away -> no player is built (the cost rule).
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
var fails := 0
var checks := 0
var off := false

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	_run.call_deferred()

func _box(w: Node3D, size: Vector3, at: Vector3) -> void:
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = size
	cs.shape = b
	f.add_child(cs)
	f.position = at
	w.add_child(f)

func _run() -> void:
	var car_id := "SPC1"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
		elif a == "--expect=off":
			off = true
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	_box(w, Vector3(400, 1, 400), Vector3(0, -0.5, 0))
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var cam := Camera3D.new()
	w.add_child(cam)
	cam.current = true
	var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
	car.position = Vector3(0, 1.0, 150)
	w.add_child(car)
	await _tick(60)
	var p: CharacterBody3D = load(PLAYER).instantiate()
	p.position = Vector3(5, 1, 150)
	w.add_child(p)
	await _tick(5)
	helper.call("seat_character", car, p)
	await _tick(10)
	var follow := func() -> void:
		cam.global_position = car.global_position + Vector3(0, 3, 8)

	# 1. horn
	follow.call()
	Input.action_press("horn")
	var heard := 0
	for i in 60:
		await physics_frame
		follow.call()
		if car.call("horn_sounding_now"):
			heard += 1
	Input.action_release("horn")
	await _tick(2)
	var after: bool = car.call("horn_sounding_now")
	if off:
		_check("control: the horn is silent", heard == 0 and not after, "%d of 60 frames" % heard)
	else:
		_check("horn held 1 s sounds", heard >= 55, "%d of 60 frames" % heard)
		_check("horn released stops", not after)

	# 2. squeal: straight, then a handbrake turn
	var squeal := func(handbrake: bool, steer: float, frames: int) -> Array:
		car.linear_velocity = -car.global_basis.z * 20.0
		car.angular_velocity = Vector3.ZERO
		if handbrake:
			Input.action_press("handbrake")
		if steer > 0.0:
			Input.action_press("left")
		var n := 0
		var loudest := -99.0
		for i in frames:
			if not handbrake:
				var lv := car.linear_velocity
				var fwd := -car.global_basis.z
				car.linear_velocity = Vector3(fwd.x * 20.0, lv.y, fwd.z * 20.0)
			await physics_frame
			follow.call()
			if car.call("skid_sounding_now"):
				n += 1
				loudest = maxf(loudest, float(car.call("skid_level_now")))
		Input.action_release("handbrake")
		Input.action_release("left")
		return [n, loudest]
	var straight: Array = await squeal.call(false, 0.0, 90)
	_check("straight at 20 m/s: no squeal", straight[0] == 0, "%d frames" % straight[0])
	var drift: Array = await squeal.call(true, 1.0, 90)
	if off:
		_check("control: a handbrake turn is silent", drift[0] == 0, "%d frames" % drift[0])
	else:
		_check("handbrake turn at 20 m/s squeals", drift[0] >= 20, "%d of 90 frames, loudest %.1f dB" % drift)
	car.linear_velocity = Vector3.ZERO
	car.angular_velocity = Vector3.ZERO
	await _tick(90)
	_check("stopped: no squeal player left", car.get_node_or_null("Skid") == null)

	# 4. distance: a car nobody is in (scripted hands on the handbrake + full steer, a traffic car's case) squeals near
	# the camera and has no player at all with the camera 200 m away. (The local player's own car is always heard.)
	helper.call("exit_driver", car)
	p.global_position = Vector3(60, 1, 150)
	await _tick(5)
	cam.current = true          # the exit made the player's own camera current
	for dist in [8.0, 200.0]:
		car.global_rotation = Vector3.ZERO
		car.linear_velocity = -car.global_basis.z * 20.0
		cam.global_position = car.global_position + Vector3(0, 3, dist)
		helper.call("drive_craft", car, 0.0, 1.0, true)
		var built := 0
		for i in 60:
			await physics_frame
			cam.global_position = car.global_position + Vector3(0, 3, dist)
			if car.get_node_or_null("Skid") != null:
				built += 1
			if "--verbose" in OS.get_cmdline_user_args() and i % 10 == 0:
				print("    v %.1f side %.1f" % [car.linear_velocity.length(), absf(car.global_basis.x.dot(car.linear_velocity))])
		helper.call("drive_craft", car, 0.0, 0.0, false)
		car.linear_velocity = Vector3.ZERO
		car.angular_velocity = Vector3.ZERO
		await _tick(60)
		if dist > 100.0:
			_check("nobody aboard, camera 200 m off: no squeal player built", built == 0, "%d frames" % built)
		elif off:
			_check("control: nobody aboard, camera near: silent", built == 0, "%d frames" % built)
		else:
			_check("nobody aboard, camera near: it squeals", built >= 20, "%d of 60 frames" % built)
	helper.call("seat_character", car, p)
	await _tick(10)

	# 3. crashes: a wall 12 m ahead of the nose
	var hits := []
	for speed in [2.0, 15.0]:
		car.global_position = Vector3(0, car.global_position.y, 150)
		car.global_rotation = Vector3.ZERO
		car.linear_velocity = Vector3.ZERO
		car.angular_velocity = Vector3.ZERO
		await _tick(30)
		var wall := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var bx := BoxShape3D.new()
		bx.size = Vector3(10, 3, 1)
		cs.shape = bx
		wall.add_child(cs)
		wall.position = Vector3(0, 1.5, 150 - 12)
		w.add_child(wall)
		var c0: int = car.call("crash_sounds_now")
		for i in 150:
			if car.global_position.z > 150 - 9.0:
				var lv := car.linear_velocity
				car.linear_velocity = Vector3(0, lv.y, -speed)
			await physics_frame
			follow.call()
		hits.append(int(car.call("crash_sounds_now")) - c0)
		wall.queue_free()
		await _tick(5)
	_check("2 m/s into a wall: no crash sound", hits[0] == 0, "%d" % hits[0])
	if off:
		_check("control: 15 m/s into a wall is silent", hits[1] == 0, "%d" % hits[1])
	else:
		_check("15 m/s into a wall: a crash sound", hits[1] >= 1, "%d" % hits[1])
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
