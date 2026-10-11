extends SceneTree
## PLAN.md V3 (user, 2026-10-11): "the player's car pushes through a person most of the time, forward and in
## reverse (GTA)". Reported: an engaged AI standing directly in front of or behind the player's car -- the player can
## neither drive through nor back out. A living character is a kinematic capsule, which a rigid car cannot move, so
## below the hit speed (VehicleConfig.vehicleCollisionMinSpeed, 5 m/s) it was a wall.
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_car_vs_ped.gd [-- --control] [--car=SPC1]
## A PLAYER-driven car (a Player body at the wheel, a scripted pair of hands), full throttle for 4 s, into a standing
## AICharacter: touching the bumper from a standstill, and from 6 m off (arrives at ~3-4 m/s); nose (forward) and tail
## (reverse). PASS = the car is past where the person stood on its own line, the person is alive, unhurt, out of the car's
## path, and was not thrown (moved under 4 m). Then an alley one car wide: the car still gets past, the person is not
## pushed through a wall (driven over slowly; hurt only if the car stays on them).
## --control: Vehicle.shovePeople off = the car as it shipped (blocked).
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _half_length(car: Node3D) -> float:
	var hl := 0.0
	for n in car.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if not mi.is_visible_in_tree() or mi.mesh == null:
			continue
		var bb: AABB = car.global_transform.affine_inverse() * mi.global_transform * mi.get_aabb()
		hl = maxf(hl, maxf(absf(bb.position.z), absf(bb.end.z)))
	return hl

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	var verbose := "--verbose" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(800, 1, 800)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var scene: PackedScene = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id)
	var row := 0
	# [label, gap from bumper to the person (m), motor (+1 forward / -1 reverse), a wall behind the person]
	for c in [
		["standstill, nose", 0.25, 1.0, false], ["standstill, tail", 0.25, -1.0, false],
		["half throttle from 1 m, nose", 1.0, 0.35, false], ["half throttle from 1 m, tail", 1.0, -0.35, false],
		["half throttle from 1 m, nose, in an alley", 1.0, 0.35, true],
		# V3 (a) / V5: a car with NOBODY in it and a brain's pedal (a traffic car), the person at its front corner
		# where the brain's rays do not look; and the same car told to stand: it leaves the person alone
		["a driverless brain's car, person at the corner", 0.25, 0.35, false, 1.15],
		["a standing car (no pedal)", 0.25, 0.0, false, 0.0],
	]:
		var x := row * 40.0
		row += 1
		var car: RigidBody3D = scene.instantiate()
		car.position = Vector3(x, 1.0, 0)
		w.add_child(car)
		if control:
			car.set("shove_people", false)
		await _tick(150)
		var hl := _half_length(car)
		var hw := 0.95
		var p: CharacterBody3D = null
		var off: float = c[4] if c.size() > 4 else 0.0
		if c.size() <= 4:
			p = load(PLAYER).instantiate()
			p.position = Vector3(x + 6, 1, 0)
			w.add_child(p)
			await _tick(5)
			helper.call("scripted_walk", p, Vector3.ZERO, false)
			helper.call("seat_character", car, p)
		var dirz: float = -signf(c[2]) if float(c[2]) != 0.0 else -1.0            # the car's nose is -Z
		var ped: CharacterBody3D = load(AI).instantiate()
		ped.position = Vector3(x + off, 1.0, dirz * (hl + float(c[1]) + 0.35))
		w.add_child(ped)
		helper.call("scripted_walk", ped, Vector3.ZERO, false)
		if c[3]:
			# an alley one car wide: there is nowhere to step aside to
			for sx in [-1.0, 1.0]:
				var wall := StaticBody3D.new()
				var wcs := CollisionShape3D.new()
				var wb := BoxShape3D.new()
				wb.size = Vector3(0.3, 3, 60)
				wcs.shape = wb
				wall.add_child(wcs)
				wall.position = Vector3(x + sx * (hw + 0.6), 1.5, dirz * 25.0)
				w.add_child(wall)
		await _tick(40)
		var ped0 := ped.global_position
		var car0 := car.global_position
		var hp0 := float(ped.get_node("Health").call("health_now"))
		helper.call("drive_craft", car, float(c[2]), 0.0, false)
		var vmax := 0.0
		var drift := 0.0
		var yaw0 := car.global_rotation.y
		var turned := 0.0
		var passed_at := -1
		var trace := ""
		for i in 240:
			await physics_frame
			vmax = maxf(vmax, car.linear_velocity.length())
			drift = maxf(drift, absf(car.global_position.x - car0.x))
			turned = maxf(turned, absf(rad_to_deg(angle_difference(yaw0, car.global_rotation.y))))
			if passed_at < 0 and (car.global_position.z - car0.z) * dirz > float(c[1]) + 2.0 * hl + 1.0:
				passed_at = i
			if verbose and i % 20 == 0:
				trace += " %.1f/%.1f" % [(car.global_position.z - car0.z) * dirz, car.linear_velocity.length()]
		if verbose:
			print("    travel/speed every 1/3 s:", trace)
		helper.call("drive_craft", car, 0.0, 0.0, false)
		var alive: bool = float(ped.get_node("Health").call("health_now")) > 0.0
		var travel := (car.global_position.z - car0.z) * dirz
		var ped_moved := ped.global_position.distance_to(ped0)
		var clear := absf(ped.global_position.x - car.global_position.x)
		var hp1 := float(ped.get_node("Health").call("health_now"))
		var detail := "car %.1f m, past at %s, top %.1f m/s, drift %.1f m, turned %.0f deg; person moved %.2f m, hp %.0f -> %.0f" % [
				travel, ("%.1f s" % (passed_at / 60.0)) if passed_at >= 0 else "never", vmax, drift, turned, ped_moved, hp0, hp1]
		if float(c[2]) == 0.0:
			_check("%s: the person is left alone" % c[0], ped_moved < 0.05 and travel < 0.2, detail)
		elif c[3]:
			_check("%s: the car gets past, the person is inside the walls and alive" % c[0],
					passed_at >= 0 and alive and absf(ped.global_position.x - x) < hw + 0.45, detail)
		else:
			_check("%s: the car gets past, on its line" % c[0], passed_at >= 0 and drift < 1.5 and turned < 20.0, detail)
			_check("%s: the person is shoved aside, alive, not thrown" % c[0], alive and ped_moved > 0.3 and ped_moved < 4.0
					and clear > 0.5 and hp1 >= hp0, "%.2f m off the car's line" % clear)
		helper.call("exit_driver", car)
		if p != null:
			p.queue_free()
		ped.queue_free()
		await _tick(2)
		car.queue_free()
		await _tick(5)
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
