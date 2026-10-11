extends SceneTree
## PLAN.md V1 / V2 (user, 2026-10-11): "a driver appearing opens the door, and the car beside it is thrown aside";
## "a traffic driver sits holstered by default". A traffic car's driver is made when the car comes near a player and
## freed when it leaves (ZoneManager.trafficLazyDrivers): nobody got in or out, so no door may move, the cars beside
## it may not move, and the driver sits with empty hands. Three cars side by side at several hull gaps; the middle
## one gets a driver the way ZoneManager seats one, then loses it the way ZoneManager stows one.
##   godot --headless --path . --script tools/godot/probe_lazy_driver_seat.gd [-- --car=SPC1] [--control]
## --control: Vehicle.quietSeats off = the real enter / exit path that shipped (door swings, body stood beside the car).
## --real-door: a REAL enter and exit (the door must swing) beside another car: the door throws nothing.
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const MAX_MOVE := 0.05
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _half_width(car: Node3D) -> float:
	var hw := 0.0
	for n in car.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if not mi.is_visible_in_tree() or mi.mesh == null:
			continue
		var bb: AABB = car.global_transform.affine_inverse() * mi.global_transform * mi.get_aabb()
		hw = maxf(hw, maxf(absf(bb.position.x), absf(bb.end.x)))
	return hw

func _door_deg(car: Node) -> float:
	var dm := car.get_node_or_null("DamageModel")
	if dm == null:
		return 0.0
	var a := 0.0
	for d in ["door_lf", "door_rf", "door_lr", "door_rr"]:
		a = maxf(a, float(dm.call("part_angle_now", d)))   # -1 = this car has no such door
	return a

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	var real_door := "--real-door" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(400, 1, 400)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var scene: PackedScene = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id)
	var row := 0
	for gap in [0.5, 1.0, 1.5, 2.6]:
		var z := row * 30.0
		row += 1
		var cars: Array = []
		for i in 3:
			var car: RigidBody3D = scene.instantiate()
			car.position = Vector3(0, 1.0, z)
			w.add_child(car)
			cars.append(car)
		await _tick(2)
		var hw := _half_width(cars[1])
		cars[0].global_position = Vector3(-(2.0 * hw + gap), 1.0, z)
		cars[2].global_position = Vector3(2.0 * hw + gap, 1.0, z)
		await _tick(240)
		var mid: RigidBody3D = cars[1]
		if control or real_door:
			mid.set("quiet_seats", false)
		var p0: Array = [cars[0].global_position, cars[1].global_position, cars[2].global_position]
		# ── the driver appears ──
		var d: CharacterBody3D = load(AI).instantiate()
		d.position = mid.global_position
		w.add_child(d)
		helper.call("seat_driver_quietly", mid, d)
		var door := 0.0
		var moved := 0.0
		for i in 150:
			await physics_frame
			door = maxf(door, _door_deg(mid))
			for k in 3:
				moved = maxf(moved, (cars[k].global_position as Vector3).distance_to(p0[k]))
		var tag := "gap %.1f m" % gap
		if real_door:
			_check("%s: a real enter swings the door" % tag, door > 30.0, "%.1f deg" % door)
		else:
			_check("%s: seating a driver moves no door" % tag, door < 1.0, "%.1f deg" % door)
		_check("%s: ... and no car" % tag, moved < MAX_MOVE, "%.3f m" % moved)
		if row == 1 and not real_door:
			var wc := d.get_node("WeaponController")
			_check("the driver sits holstered, not in the combat state",
					bool(wc.call("holstered_now")) and not bool(d.call("combat_now")),
					"holstered %s combat %s" % [wc.call("holstered_now"), d.call("combat_now")])
			_check("the driver is not solid in its seat", d.collision_layer == 0, "layer %d" % d.collision_layer)
		# ── the driver is stowed ──
		for k in 3:
			p0[k] = cars[k].global_position
		helper.call("release_driver", mid, d)
		var stood: Vector3 = d.global_position - mid.global_position
		var layer := d.collision_layer
		d.queue_free()
		door = 0.0
		moved = 0.0
		for i in 150:
			await physics_frame
			door = maxf(door, _door_deg(mid))
			for k in 3:
				moved = maxf(moved, (cars[k].global_position as Vector3).distance_to(p0[k]))
		if not real_door:
			_check("%s: stowing the driver moves no door" % tag, door < 1.0, "%.1f deg" % door)
		_check("%s: ... and no car" % tag, moved < MAX_MOVE, "%.3f m" % moved)
		if row == 1 and not real_door:
			_check("a stowed driver is never stood beside the car, solid", layer == 0 and absf(stood.x) < 1.0,
					"layer %d, %.2f m to the side" % [layer, stood.x])
		for c in cars:
			c.queue_free()
		await _tick(5)
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
