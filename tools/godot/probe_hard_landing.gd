extends SceneTree
## PLAN.md 0.14: a hard landing must not bottom the HULL on the ground. The bump stop (VehicleConfig.bumpStopTravel /
## bumpStopRate, the kerb-catch fix) ends the spring's travel; a jump lands at several times the static load, which it
## was never measured against. Each car is settled on a flat stand, lifted `h` metres (level, no spin) and dropped:
## starting at 1 m/s down (a parked car re-sleeps below its park threshold): a landing at sqrt(1 + 2 g h) m/s
## (0.5 m: 3.3, 1 m: 4.5, 2 m: 6.3, 3 m: 7.7). The wheels are rays, so ANY body contact
## with the floor is the hull bottoming. Reported per drop: hull contact, health lost, and the bounce. The nose-down
## cases at speed are the real jump (off a crest). Result 2026-10-06: the overdamped suspension stops every level drop
## (up to 3 m, 7.7 m/s) ABOVE rest height with or without the bump stop; nose-down the bumper scrapes, at no damage.
##   godot --headless --path . --script tools/godot/probe_hard_landing.gd [-- --car=SPC1] [--control]
## --control drives with the bump stop off (bump_stop_rate 0 on the car's shared config).
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
## A landing from this height must not touch the hull (a GTA-scale jump off a crest or a kerb ramp).
const MUST_CLEAR_M := 1.0
## Upward speed (m/s) after touchdown that reads as the landing throwing the car: probe_road_launch RISE_DV.
const MAX_BOUNCE := 3.0
var fails := 0
var checks := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-56s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	_run.call_deferred()

func _health(car: Node) -> float:
	var h := car.get_node_or_null("Health")
	return float(h.call("health_now")) if h != null else -1.0

func _run() -> void:
	var car_id := "SPC1"
	var control := "--control" in OS.get_cmdline_user_args()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var cfg: Resource = load("res://src/main/resources/com/openworld/vehicle/%sConfig.tres" % car_id)
	if control and cfg != null:
		cfg.set("bump_stop_rate", 0.0)
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	f.name = "Floor"
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(400, 1, 400)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	w.add_child(load(HELPER).new())
	print("[landing] %s%s" % [car_id, " (CONTROL: bump stop off)" if control else ""])
	# [drop m, nose-down deg, forward m/s]: level drops, then the real jump -- off a crest at speed, nose first
	for case in [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0],
			[1.0, 10.0, 15.0], [2.0, 10.0, 15.0], [2.0, 20.0, 15.0], [3.0, 20.0, 20.0]]:
		var h: float = case[0]
		var pitch: float = case[1]
		var fwd: float = case[2]
		var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
		car.position = Vector3(0, 1.0, 0)
		car.contact_monitor = true
		car.max_contacts_reported = 16
		w.add_child(car)
		await _tick(240)
		var rest_y := car.global_position.y
		var hp0 := _health(car)
		var xf := car.global_transform
		xf.basis = Basis(Vector3.RIGHT, -deg_to_rad(pitch))   # nose (-Z) down
		xf.origin.y = rest_y + h
		car.global_transform = xf
		# 1 m/s down, over the park threshold: a parked car re-sleeps every frame while slower (Vehicle.parked)
		car.linear_velocity = Vector3(0, -1.0, -fwd)
		car.angular_velocity = Vector3.ZERO
		car.sleeping = false
		var touched := false
		var min_y := INF
		var peak_up := 0.0
		var landed := false
		for i in 240:
			await physics_frame
			for body in car.get_colliding_bodies():
				if body == f:
					touched = true
			min_y = minf(min_y, car.global_position.y)
			if OS.get_environment("LANDING_TRACE") != "" and i < 40 and i % 4 == 0:
				print("    f%d y %.3f vy %.2f sleeping %s freeze %s" % [i, car.global_position.y - rest_y, car.linear_velocity.y, car.sleeping, car.freeze])
			if car.global_position.y < rest_y + 0.05:
				landed = true
			if landed:
				peak_up = maxf(peak_up, car.linear_velocity.y)
		var lost := hp0 - _health(car)
		var v := sqrt(1.0 + 2.0 * 9.8 * h)
		var tag := "drop %.1f m" % h if pitch == 0.0 else "drop %.1f m, %.0f deg nose-down at %.0f m/s" % [h, pitch, fwd]
		var detail := "lands %.1f m/s, body %.3f m below rest, bounce %.2f m/s, health lost %.0f" % [
			v, rest_y - min_y, peak_up, lost]
		# A LEVEL landing must not touch the hull. A nose-down one may scrape the bumper (its overhang reaches the
		# ground first; a cab-over truck at 10 deg is its real approach angle), but it must cost nothing and not throw
		# the car: measured 2026-10-06, worst bounce 2.1 m/s (KET1, 3 m at 20 deg) and 0 damage on SPC1 KEC1 CRT1 KET1 TAX1.
		if pitch == 0.0 and h <= MUST_CLEAR_M:
			_check(tag + ": the hull does not touch the ground", not touched, detail)
		else:
			print("  INFO  %s: hull %s  %s" % [tag, "TOUCHED" if touched else "clear", detail])
		_check(tag + ": no damage", lost <= 0.5, detail)
		_check(tag + ": no launch off the landing", peak_up < MAX_BOUNCE, detail)
		car.queue_free()
		await _tick(2)
	print("RESULT %s (%d checks, %d failures)" % ["PASS" if fails == 0 else "FAIL", checks, fails])
	quit(1 if fails else 0)
