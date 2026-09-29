extends SceneTree
## The placeholder AIRCRAFT and BOATS are controllable (user, 2026-09-28): FIJ1 / LIP1 fly (Airplane.tscn), WOB1 / FIB1
## float and make way (Boat.tscn). Driven by a constant command through the ordinary controller seat.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_craft.gd [-- --control]
##
##   boats:    set down 1 m above real water (a world.WaterVolume), each floats LEVEL at its waterline (the body within
##             1.2 m of the surface, upright), then under full throttle makes way (> 3 m/s forward);
##   aircraft: on a runway, full throttle takes it past its take-off speed, then the stick back lifts it off (> 15 m up).
## `--control` gives every craft no throttle: the boats still float (the buoyancy is not the throttle), nothing makes
## way and nothing leaves the runway -- 4 checks fail.

const DIR := "res://src/main/resources/com/openworld/vehicle/"
const WATER := "res://src/main/java/com/openworld/world/WaterVolume.java"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _static_box(parent: Node, size: Vector3, at: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	b.position = at
	parent.add_child(b)

func _initialize() -> void:
	_run.call_deferred()

func _spawn(world: Node3D, id: String, at: Vector3) -> Node3D:
	var v: Node3D = (load(DIR + id + ".tscn") as PackedScene).instantiate()
	world.add_child(v)
	v.global_position = at
	return v

func _run() -> void:
	var control := OS.get_cmdline_user_args().has("--control")
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	# the sea: a WaterVolume whose box top is the surface (y 0), a seabed under it
	var water := Area3D.new()
	water.set_script(load(WATER))
	var wcs := CollisionShape3D.new()
	var wbox := BoxShape3D.new()
	wbox.size = Vector3(400, 20, 400)
	wcs.shape = wbox
	wcs.position = Vector3(0, -10, 0)
	water.add_child(wcs)
	water.position = Vector3(5000, 0, 0)
	world.add_child(water)
	_static_box(world, Vector3(400, 0.2, 400), Vector3(5000, -25.0, 0))
	# the runway
	_static_box(world, Vector3(80, 0.2, 3000), Vector3(0, -0.1, 0))
	await _tick(5)
	# ── boats
	for i in 2:
		var id: String = ["WOB1", "FIB1"][i]
		var b := _spawn(world, id, Vector3(5000 + (i * 40 - 20), 1.0, 60))
		await _tick(360)
		var up: Vector3 = b.global_transform.basis.y
		_check("%s floats level at its waterline" % id, absf(b.global_position.y) < 1.2 and up.y > 0.95,
			"y %+.2f  up %.3f" % [b.global_position.y, up.y])
		helper.drive_craft(b, 0.0 if control else 1.0, 0.0, false)
		await _tick(480)
		var fwd: Vector3 = -b.global_transform.basis.z
		var v: float = (b as RigidBody3D).linear_velocity.dot(fwd)
		_check("%s makes way under full throttle" % id, v > 3.0, "%.1f m/s forward" % v)
	# ── aircraft
	for i in 2:
		var id: String = ["FIJ1", "LIP1"][i]
		var a := _spawn(world, id, Vector3(i * 30 - 15, 1.2, 1400))
		a.rotation.y = 0.0                         # nose -Z, down the runway
		await _tick(120)
		helper.drive_craft(a, 0.0 if control else 1.0, 0.0, false)
		var y0 := a.global_position.y
		var take_off: float = {"FIJ1": 60.0, "LIP1": 37.0}[id]
		var reached := 0.0
		for k in 60 * 12:
			await physics_frame
			reached = maxf(reached, (a as RigidBody3D).linear_velocity.length())
			if reached > take_off + 5.0:
				break
		# a pilot's rotation: the stick back until the nose is ~15 deg up, then neutral (holding it loops the plane)
		helper.drive_craft(a, 0.0 if control else 1.0, 0.0, not control)
		for k in 180:
			await physics_frame
			if (-a.global_transform.basis.z).y > 0.26:
				break
		helper.drive_craft(a, 0.0 if control else 1.0, 0.0, false)
		var peak := 0.0
		for k in 10:
			await _tick(60)
			peak = maxf(peak, a.global_position.y - y0)
			if OS.get_cmdline_user_args().has("--verbose"):
				print("    t%2d  y %+.1f  v %.1f  up %.2f" % [k + 1, a.global_position.y - y0,
					(a as RigidBody3D).linear_velocity.length(), a.global_transform.basis.y.y])
		var climb := peak
		_check("%s passes its take-off speed and the stick back lifts it off" % id,
			reached > take_off and climb > 15.0, "top %.0f m/s  climbed %.0f m" % [reached, climb])
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
