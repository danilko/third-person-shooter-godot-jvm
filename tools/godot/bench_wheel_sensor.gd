extends SceneTree
## Wheel-sensor review: 1 ray vs 3 fore/aft rays (shipped) vs a swept sphere vs a swept tyre cylinder, on one car.
##
##   godot --headless --path . --script tools/godot/bench_wheel_sensor.gd [-- --car=SPC1 --cars=40]
##
## COST: `cars` cars coast across a big floor at 20 m/s (the suspension, grip and every wheel sample run each
## step); the physics-process time per step is averaged over 300 steps after a warm-up.
## BEHAVIOUR: one car coasts straight at a kerb that runs the full width - up a step, 4 m of plateau, down - at
## 15 m/s over 0.15 m and 25 m/s over 0.30 m. Recorded: the fastest the body rises (a LAUNCH), the fastest it
## pitches, and the time it spends with no wheel touching anything.
## WALL: the car slides along a 1.1 m wall at 20 m/s: a sensor that reads the wall's FACE as ground lifts that side.

var CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const MODES := {"rays_1": [0, 1], "rays_3": [0, 3], "sphere": [1, 1], "cylinder": [2, 1]}

func _floor(parent: Node, size: Vector3, at: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	b.position = at
	parent.add_child(b)

func _car(world: Node, mode: Array, at: Vector3) -> RigidBody3D:
	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate()
	var cfg: Resource = car.get("vehicle_config").duplicate()
	cfg.set("wheel_sensor", mode[0])
	cfg.set("suspension_samples", mode[1])
	car.set("vehicle_config", cfg)
	world.add_child(car)
	car.global_position = at
	return car

func _rest_height(car: RigidBody3D) -> float:
	var cfg: Resource = car.get("vehicle_config")
	var eq: float = cfg.rest_distance - car.mass * 9.8 / (4.0 * cfg.spring_strength)
	return cfg.wheel_radius + eq - (car.get_node("Wheels/FL") as Node3D).position.y

func _cost(mode_name: String, mode: Array, n: int) -> float:
	var world := Node3D.new()
	root.add_child(world)
	_floor(world, Vector3(400, 1, 4000), Vector3(0, -0.5, 0))
	var cars := []
	for i in n:
		var c := _car(world, mode, Vector3((i % 10) * 6.0 - 27.0, 0, 1500 - (i / 10) * 12.0))
		c.global_position.y = _rest_height(c)
		cars.append(c)
	for i in 30:
		await physics_frame
	for c in cars:
		c.linear_velocity = -c.global_basis.z * 20.0
	for i in 60:
		await physics_frame
	var total := 0.0
	for i in 200:
		await physics_frame
		total += Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)
	world.queue_free()
	await physics_frame
	return total / 200.0 * 1000.0

func _kerb(mode: Array, speed: float, height: float) -> Dictionary:
	var world := Node3D.new()
	root.add_child(world)
	_floor(world, Vector3(40, 1, 400), Vector3(0, -0.5, 0))
	_floor(world, Vector3(40, height, 4.0), Vector3(0, height / 2.0, -40.0))   # the kerb, 40 m ahead
	var car := _car(world, mode, Vector3(0, 0, 0))
	car.global_position.y = _rest_height(car)
	for i in 20:
		await physics_frame
	car.linear_velocity = -car.global_basis.z * speed
	var rise := 0.0
	var pitch := 0.0
	var air := 0
	var wheels: Array = car.get_node("Wheels").get_children()
	for i in 240:
		await physics_frame
		rise = maxf(rise, car.linear_velocity.y)
		pitch = maxf(pitch, absf((car.global_basis.inverse() * car.angular_velocity).x))
		var any := false
		for w in wheels:
			if (w as RayCast3D).is_colliding() or (w.get_node_or_null("SuspensionSphere") != null and (w.get_node("SuspensionSphere") as ShapeCast3D).is_colliding()):
				any = true
		if not any:
			air += 1
	world.queue_free()
	await physics_frame
	return {"rise": rise, "pitch": pitch, "air_s": air / 60.0}

func _wall(mode: Array) -> Dictionary:
	# a 1.1 m wall along the left, the car's side 5 cm off it, sliding INTO it at 20 m/s with 1.5 m/s of drift:
	# a sensor that reads the wall's face as ground lifts that side of the car (the barrier-climb launch)
	var world := Node3D.new()
	root.add_child(world)
	_floor(world, Vector3(40, 1, 400), Vector3(0, -0.5, 0))
	var car := _car(world, mode, Vector3(0, 0, 0))
	var half: float = car.get("vehicle_config").hull_half_width
	_floor(world, Vector3(0.4, 1.1, 400), Vector3(-half - 0.05 - 0.2, 0.55, 0))
	car.global_position.y = _rest_height(car)
	car.global_position.x = -0.6
	car.rotation.y = deg_to_rad(4.0)                   # nosed 4 deg into the wall: grip keeps it heading there
	for i in 20:
		await physics_frame
	car.linear_velocity = -car.global_basis.z * 20.0
	var rise := 0.0
	var roll := 0.0
	var h0 := car.global_position.y
	var top := 0.0
	for i in 180:
		await physics_frame
		rise = maxf(rise, car.linear_velocity.y)
		roll = maxf(roll, absf(rad_to_deg(car.global_rotation.z)))
		top = maxf(top, car.global_position.y - h0)
	world.queue_free()
	await physics_frame
	return {"rise": rise, "roll": roll, "lift": top}

func _initialize() -> void:
	var n := 40
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			CAR = "res://src/main/resources/com/openworld/vehicle/%s.tscn" % a.substr(6)
		if a.begins_with("--cars="):
			n = int(a.substr(7))
	current_scene = root
	# COST is measured one mode per PROCESS (`--only=<mode> --cost-only`, run by tools/godot/bench_wheel_sensor.sh):
	# in one process the step time climbed round after round (1 ray: 2.7 -> 11.2 ms over five rounds), so only a
	# fresh process's number compares with another's.
	var only := ""
	var cost_only := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			only = a.substr(7)
		cost_only = cost_only or a == "--cost-only"
	for name in MODES:
		if only != "" and name != only:
			continue
		var ms := await _cost(name, MODES[name], n)
		print("BENCH %-7s  %d cars: %.3f ms/step" % [name, n, ms])
		if cost_only:
			continue
		var small: Dictionary = await _kerb(MODES[name], 15.0, 0.15)
		var big: Dictionary = await _kerb(MODES[name], 25.0, 0.30)
		var wall: Dictionary = await _wall(MODES[name])
		print("BENCH %-7s  0.15 m kerb @15: rise %.2f m/s pitch %.2f rad/s  |  0.30 m @25: rise %.2f m/s pitch %.2f rad/s  |  wall @20: roll %.1f deg"
				% [name, small.rise, small.pitch, big.rise, big.pitch, wall.roll])
	quit()
