extends SceneTree
## BIKE HANDLING (PLAN.md 3.1b BIKE DRIFT; user 2026-10-16: "ssb1 ... very unstable at high speed (even in straight line will
## bounce right/left)" and "the drift ... even at slow speed will drift in continuous spin even with small press, unlike
## the vehicle's drift with space"). On a bare 4 km floor, each of the five bikes and the SPC1 car (the CONTROL: the
## car's drift and straight line are the reference the user compares against):
##
##   1. STRAIGHT: full throttle, no steering, from rest for 14 s -- the yaw rate's swing (peak-to-peak, deg/s) and how
##      far the vehicle wanders off its line (m) as the speed builds, sampled per second of speed band;
##   2. DRIFT: 10 m/s, then Space with a SMALL steer (0.3) for 1.5 s and release -- the yaw it turned (deg), the peak
##      yaw rate (deg/s), and whether it keeps spinning after the release.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_bike_handling.gd [-- --only=SSB1] [--measure] [--control]
## --measure: print only, no verdicts. --control: every bike's drift_yaw_accel 0, i.e. the car's FIXED 9000 N m torque on
## a bike's 17-82 kg m^2 (the spin the user reported): the drift checks fail. The straight line's control is the code
## before VehicleWheel damped along the ground normal (body-up damping): SSB1 swung 10.9 deg/s and left its line by
## 4.6 m above 60 m/s, every other vehicle passed (measured 2026-10-16, not switchable at runtime). Gates (the car's own numbers set the bar):
##   straight: yaw swing <= 6 deg/s and off the line <= 2.0 m over the run (the car itself wanders 1.7 m in 600 m), at every speed;
##   drift:    the turn in 1.5 s at most 1.5 x the car's, and the yaw rate 1 s after release under 20 deg/s (no spin-on).

const DIR := "res://src/main/resources/com/openworld/vehicle/"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const IDS := ["SPC1", "SCT1", "POB1", "TRB1", "SSB1", "PMB1"]

var fails := 0
var measure := false
var held := []

func _check(label: String, ok: bool, detail: String = "") -> void:
	if measure:
		print("  ----  %-62s %s" % [label, detail])
		return
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	_run.call_deferred()

func _heading(v: Node3D) -> float:
	var f := -v.global_basis.z
	return atan2(f.x, -f.z)

func _run() -> void:
	var only := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--only="):
			only = a.substr(7)
	measure = "--measure" in OS.get_cmdline_user_args()
	if "--control" in OS.get_cmdline_user_args():
		for id in IDS:
			if id != "SPC1":
				var cfg: Resource = load(DIR + id + "Config.tres")
				cfg.set("drift_yaw_accel", 0.0)
				held.append(cfg)          # held, or the cache drops it and the next load reads the file again
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(4000, 1, 4000)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var car_turn := -1.0
	for i in IDS.size():
		var id: String = IDS[i]
		if only != "" and id != only and id != "SPC1":
			continue
		print("-- %s" % id)
		var v: RigidBody3D = (load(DIR + id + ".tscn") as PackedScene).instantiate()
		v.position = Vector3(i * 40.0 - 100.0, 0.8, 1800.0)
		w.add_child(v)
		await _tick(60)
		# 1. straight
		var start := v.global_position
		var line := -v.global_basis.z
		var h0 := _heading(v)
		helper.call("drive_craft", v, 1.0, 0.0, false)
		var band := {}        # speed band (10 m/s) -> [min yaw rate, max yaw rate, max off-line]
		var last_h := h0
		var worst_swing := 0.0
		var worst_off := 0.0
		for t in 14 * 60:
			await physics_frame
			var h := _heading(v)
			var rate := wrapf(h - last_h, -PI, PI) * 60.0
			last_h = h
			var sp := v.linear_velocity.length()
			var k := int(sp / 10.0)
			var off := absf((v.global_position - start).cross(line).y)
			if t < 60:
				continue
			if not band.has(k):
				band[k] = [rate, rate, off]
			band[k][0] = minf(band[k][0], rate)
			band[k][1] = maxf(band[k][1], rate)
			band[k][2] = maxf(band[k][2], off)
		var parts := []
		for k in band.keys():
			var swing := rad_to_deg(band[k][1] - band[k][0])
			worst_swing = maxf(worst_swing, swing)
			worst_off = maxf(worst_off, band[k][2])
			parts.append("%d-%d m/s: swing %.1f deg/s, off %.2f m" % [k * 10, k * 10 + 10, swing, band[k][2]])
		print("    straight, top %.1f m/s, heading drift %.1f deg" % [v.linear_velocity.length(), rad_to_deg(wrapf(_heading(v) - h0, -PI, PI))])
		for p in parts:
			print("      " + p)
		_check("%s: straight at full throttle holds its line" % id, worst_swing <= 6.0 and worst_off <= 2.0,
				"yaw swing %.1f deg/s, off the line %.2f m" % [worst_swing, worst_off])
		# 2. drift
		v.linear_velocity = Vector3.ZERO
		v.angular_velocity = Vector3.ZERO
		helper.call("drive_craft", v, 0.0, 0.0, true)
		await _tick(90)
		helper.call("drive_craft", v, 0.6, 0.0, false)
		for t in 600:
			await physics_frame
			if v.linear_velocity.length() >= 10.0:
				break
		var sp0 := v.linear_velocity.length()
		helper.call("drive_craft", v, 0.6, 0.3, true)
		var hd := _heading(v)
		var turned := 0.0
		var peak := 0.0
		last_h = hd
		for t in 90:
			await physics_frame
			var h := _heading(v)
			var d := wrapf(h - last_h, -PI, PI)
			turned += d
			peak = maxf(peak, absf(d) * 60.0)
			last_h = h
		helper.call("drive_craft", v, 0.0, 0.0, false)
		await _tick(60)
		var after := absf(v.angular_velocity.y)
		var lean := float(v.call("lean_degrees_now")) if v.has_method("lean_degrees_now") else 0.0
		var up := rad_to_deg(acos(clampf(v.global_basis.y.dot(Vector3.UP), -1.0, 1.0)))
		print("    drift from %.1f m/s: turned %.0f deg in 1.5 s, peak %.0f deg/s, 1 s after release %.0f deg/s, %.1f m/s, body tilt %.0f deg, lean %.0f"
				% [sp0, rad_to_deg(absf(turned)), rad_to_deg(peak) if false else peak * 180.0 / PI, rad_to_deg(after), v.linear_velocity.length(), up, lean])
		if id == "SPC1":
			car_turn = rad_to_deg(absf(turned))
		else:
			_check("%s: a small steer on Space turns it no more than 1.5 x the car" % id, rad_to_deg(absf(turned)) <= 1.5 * car_turn,
					"%.0f vs the car's %.0f deg" % [rad_to_deg(absf(turned)), car_turn])
		_check("%s: ... and it stops turning when Space is let go" % id, rad_to_deg(after) < 20.0, "%.0f deg/s 1 s after" % rad_to_deg(after))
		v.queue_free()
		await _tick(2)
	print("RESULT %s (%d failures)%s%s" % ["PASS" if fails == 0 else "FAIL", fails, "  (MEASURE)" if measure else "",
			"  (CONTROL)" if "--control" in OS.get_cmdline_user_args() else ""])
	quit(0 if fails == 0 else 1)
