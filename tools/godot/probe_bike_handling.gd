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
##   3. SLIDE: 12 m/s, Space + FULL steer -- the lean into the slide and the counter-steered front wheel (see _slide).
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_bike_handling.gd [-- --only=SSB1] [--measure] [--control] [--control-slide]
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

## 3. SLIDE (BIKE DRIFT (2)): 12 m/s, then Space with FULL steer for 1.5 s. Read independently of the bike's own measure,
## from its place (0.1 s window differences, as the bike measures itself): the acceleration along the bike's left and the slip angle (nose left of the travel). Checks:
## it slides (slip past 15 deg) and stays up (tilt < 15 deg, nobody thrown); the lean is INTO the slide on >= 90 % of the
## frames slipping past 10 deg; the lean is what the force + slip ask for (mean error <= 3 deg against
## atan(a_lat / g) + slip / 3, eased at the bike's own lean rate -- the lean cannot jump); the front wheel points where
## the bike is GOING (within 6 deg of -slip between 14 deg of slip and its 45 deg lock). The slip is eased like the
## bike's (1/14 s). dust rises at the rear wheel while it slides and stops at a stand. --control-slide = the yaw-rate lean, the
## bars' front wheel and no dust (Motorcycle.slideLean false): those three fail.
func _slide(v: RigidBody3D, id: String, helper: Node) -> void:
	v.linear_velocity = Vector3.ZERO
	v.angular_velocity = Vector3.ZERO
	helper.call("drive_craft", v, 0.0, 0.0, true)
	await _tick(90)
	helper.call("drive_craft", v, 0.7, 0.0, false)
	for t in 600:
		await physics_frame
		if v.linear_velocity.length() >= 12.0:
			break
	var sp0 := v.linear_velocity.length()
	helper.call("drive_craft", v, 0.6, 1.0, true)
	var clock := 0.0
	var pos_trail := []
	var vel_trail := []
	var acc := 0.0
	var max_slip := 0.0
	var max_tilt := 0.0
	var n_slip := 0
	var n_into := 0
	var err_sum := 0.0
	var err_n := 0
	var yaw_err_sum := 0.0
	var wheel_n := 0
	var wheel_ok := 0
	var worst_wheel := 0.0
	var max_lean := 0.0
	var dust_n := 0
	var cap := float(load(DIR + id + "Config.tres").get("motorcycle_lean_degrees"))
	var slip_e := 0.0     # eased like the bike's own (SLIDE_EASE 14 /s)
	var ref_e := 0.0      # eased like the bike's lean (LEAN_RATE 6 /s): the lean cannot jump
	var yaw_e := 0.0
	for t in 90:
		await physics_frame
		# the bike's own measure: 0.1 s window differences of its place, then of that velocity (Motorcycle.MOTION_WINDOW)
		clock += 1.0 / 60.0
		pos_trail.append([clock, v.global_position])
		var vel := _window_rate(pos_trail, clock)
		vel.y = 0.0
		vel_trail.append([clock, vel])
		var a := _window_rate(vel_trail, clock)
		var left := -v.global_basis.x
		acc += (a.x * left.x + a.z * left.z - acc) * minf(1.0, 14.0 / 60.0)
		var slip_now := 0.0
		if vel.length() > 2.0:
			var b := v.global_basis.z
			slip_now = wrapf(atan2(b.x, b.z) - atan2(-vel.x, -vel.z), -PI, PI)
			if absf(slip_now) > PI / 2:       # folded about sideways, as the bike does (100 deg reads 80; backwards 0)
				slip_now = signf(slip_now) * PI - slip_now
		slip_e += (slip_now - slip_e) * minf(1.0, 14.0 / 60.0)
		var slip := slip_e
		var lean := float(v.call("lean_degrees_now"))
		var wheel := float(v.call("front_wheel_steer_degrees_now"))
		var tilt := rad_to_deg(acos(clampf(v.global_basis.y.dot(Vector3.UP), -1.0, 1.0)))
		max_tilt = maxf(max_tilt, tilt)
		max_slip = maxf(max_slip, absf(rad_to_deg(slip)))
		max_lean = maxf(max_lean, absf(lean))
		var ref := clampf(rad_to_deg(atan(acc / 9.81) + slip / 3.0 * minf(1.0, vel.length() / 6.0)), -cap, cap)
		ref_e += (ref - ref_e) * minf(1.0, 6.0 / 60.0)
		yaw_e += (clampf(rad_to_deg(atan(vel.length() * v.angular_velocity.y / 9.81)), -cap, cap) - yaw_e) * minf(1.0, 6.0 / 60.0)
		if measure and (t % 6 == 0 or absf(rad_to_deg(slip)) > 14.0 and absf(rad_to_deg(slip)) < 43.0 and absf(wheel + rad_to_deg(slip)) > 6.0):
			print("      t %2d  v %4.1f  slip %5.0f  a_lat %5.1f  yaw %5.0f deg/s  lean %5.1f  wheel %5.0f"
					% [t, vel.length(), rad_to_deg(slip), acc, rad_to_deg(v.angular_velocity.y), lean, wheel])
		if bool(v.call("dust_now")):
			dust_n += 1
		if t < 15:
			continue          # the lean eases in over ~0.2 s
		err_sum += absf(lean - ref_e)
		yaw_err_sum += absf(yaw_e - ref_e)
		err_n += 1
		if absf(rad_to_deg(slip)) > 10.0:
			n_slip += 1
			if signf(lean) == signf(slip) and absf(lean) > 2.0:
				n_into += 1
		if absf(rad_to_deg(slip)) > 14.0 and absf(rad_to_deg(slip)) < 43.0:     # the wheel's lock is 45 deg
			wheel_n += 1
			var e := absf(wheel + rad_to_deg(slip))
			worst_wheel = maxf(worst_wheel, e)
			if e <= 6.0:
				wheel_ok += 1
	var dust_frames := 0
	helper.call("drive_craft", v, 0.0, 0.0, true)
	for t in 240:                      # brake it to a stand: the dust must stop
		await physics_frame
		dust_frames = dust_frames + 1 if bool(v.call("dust_now")) else 0
	helper.call("drive_craft", v, 0.0, 0.0, false)
	var thrown := int(v.call("throws_now"))
	print("    slide from %.1f m/s: slip max %.0f deg, lean max %.0f (cap %.0f), tilt max %.0f, lean-vs-force error %.1f deg (the yaw lean would be %.1f)"
			% [sp0, max_slip, max_lean, cap, max_tilt, err_sum / maxf(1, err_n), yaw_err_sum / maxf(1, err_n)])
	_check("%s: Space + full steer slides it" % id, max_slip > 15.0, "slip %.0f deg" % max_slip)
	_check("%s: ... upright, nobody thrown" % id, max_tilt < 15.0 and thrown == 0, "tilt %.0f deg, %d thrown" % [max_tilt, thrown])
	_check("%s: ... leaning INTO the slide" % id, n_slip > 10 and n_into >= 0.9 * n_slip, "%d / %d frames" % [n_into, n_slip])
	_check("%s: ... by what the force and the slip ask for" % id, err_n > 0 and err_sum / err_n <= 3.0,
			"mean error %.1f deg over %d frames" % [err_sum / maxf(1, err_n), err_n])
	_check("%s: ... the front wheel along the travel (counter-steered)" % id, wheel_n > 5 and wheel_ok >= 0.9 * wheel_n,
			"%d / %d frames within 6 deg, worst %.0f" % [wheel_ok, wheel_n, worst_wheel])
	_check("%s: ... dust at the rear wheel while it slides, none at a stand" % id, dust_n >= 0.5 * n_slip and n_slip > 0 and dust_frames == 0,
			"%d dust frames of %d slipping; still dusting at the end: %s" % [dust_n, n_slip, dust_frames > 0])

## Motorcycle.windowRate: the newest entry less the oldest one at least 0.1 s back, per second.
func _window_rate(trail: Array, now: float) -> Vector3:
	while trail.size() > 2 and now - float(trail[1][0]) >= 0.1:
		trail.pop_front()
	var dt := float(trail[-1][0]) - float(trail[0][0])
	if dt < 0.05:
		return Vector3.ZERO
	return (trail[-1][1] - trail[0][1]) / dt

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
	if "--control-slide" in OS.get_cmdline_user_args():
		var m: Node = load("res://src/main/java/com/openworld/carrier/motorcycle/Motorcycle.java").new()
		m.call("set_slide_lean_now", false)
		m.free()
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
		if id != "SPC1":
			await _slide(v, id, helper)
		v.queue_free()
		await _tick(2)
	print("RESULT %s (%d failures)%s%s" % ["PASS" if fails == 0 else "FAIL", fails, "  (MEASURE)" if measure else "",
			"  (CONTROL)" if "--control" in OS.get_cmdline_user_args() else ""])
	quit(0 if fails == 0 else 1)
