extends SceneTree
## PLAN.md 3.1b -- the motorcycles ride: stand, lean, cross a kerb, and throw their rider in a crash.
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_motorcycle_ride.gd [-- --bike=SCT1]
##       [--stub] [--verbose]
## A real Player on the bike, driven through `Input` (throttle, left), on a flat strip. Per bike:
##   rest     -- dropped on the floor it settles upright (body tilt < 2 deg), its model wheels on the ground (< 4 cm),
##               and empty it rests on its side stand (lean 4-10 deg to the left);
##   seated   -- with the rider on, it stands up straight (|lean| < 1.5 deg) and the rider is in the seat;
##   2 m/s    -- held at walking pace for 3 s it stays up (body tilt < 3 deg);
##   turn     -- full left at speed: the bike LEANS left (> 8 deg, and within 25 % of atan(v w / g)), the body stays
##               level (< 6 deg), and the rider rolls with it (within 3 deg of the bike's lean);
##   kerb     -- a 0.15 m kerb crossed at 35 deg at 12 m/s: the body tilts < 15 deg, the rider stays on;
##   bump     -- into a wall at 2.5 m/s: the rider stays on;
##   crash    -- into a wall at 13 m/s (or 85 % of top speed): the rider is THROWN (off, > 0.3 m up off the seat, hurt);
##   parts    -- fairing / mirrors / top box / screen are damage parts; a front crash drops the cowl as debris, a
##               mirror comes off, and the part mask carried to a second copy reproduces both.
## "Stays up" / "level" / "no flip" read the body's ROLL (a fall is a roll; pitch is the probe holding a speed against
## the throttle).
## --control: no lean (motorcycle_lean_degrees 0) and no throw (motorcycle_eject_dv 1e6) -- the side stand, turn-lean
##   and crash cases must fail (rider-roll may fail too: with no lean the rider is pinned the car's way, not rolled with
##   the body's own few degrees of roll).
## --stub: the old two-ray Motorcycle.tscn (physical lean), a COMPARISON: measured 2026-10-16, it also stands, holds
##   2 m/s and crosses the kerb (it has no model, so its wheel / lean / crash cases are skipped).
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const DIR := "res://src/main/resources/com/openworld/vehicle/"
const BIKES := ["SCT1", "POB1", "TRB1", "SSB1", "PMB1"]
const PER_BIKE := 14
var fails := 0
var checks := 0
var verbose := false
var stub := false
var held: Array = []

func _check(label: String, ok: bool, detail: String = "") -> void:
	checks += 1
	if not ok:
		fails += 1
	print("  %s  %-48s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _initialize() -> void:
	_run.call_deferred()

## the body's roll about its own fore-aft axis (deg): how far it has fallen over
func _tilt(b: Node3D) -> float:
	return absf(rad_to_deg(asin(clampf(b.global_basis.x.y, -1.0, 1.0))))

func _box(w: Node3D, size: Vector3, at: Vector3, yaw_deg: float = 0.0) -> StaticBody3D:
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = size
	cs.shape = b
	f.add_child(cs)
	f.position = at
	f.rotation.y = deg_to_rad(yaw_deg)
	w.add_child(f)
	return f

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	stub = "--stub" in args
	var control := "--control" in args
	verbose = "--verbose" in args
	var bikes: Array = ["Motorcycle"] if stub else BIKES
	for a in args:
		if a.begins_with("--bike="):
			bikes = [a.substr(7)]
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	_box(w, Vector3(200, 1, 4000), Vector3(0, -0.5, 0))
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	var lane := 0
	if control and not stub:
		for id in bikes:
			var c: Resource = load(DIR + id + "Config.tres")
			held.append(c)          # a dropped reference unloads it, and the next load reads the file again
			c.set("motorcycle_lean_degrees", 0.0)
			c.set("motorcycle_eject_dv", 1000000.0)
	for id in bikes:
		await _bike(w, helper, id, lane * 12.0 - 30.0)
		lane += 1
	# a GDScript error aborts a case silently: every case must have reported
	var want := len(bikes) * (4 if stub else PER_BIKE)
	if checks != want:
		fails += 1
		print("  FAIL  %d checks reported, %d expected (a case aborted)" % [checks, want])
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)

func _spawn(w: Node3D, id: String, at: Vector3) -> RigidBody3D:
	var bike: RigidBody3D = load(DIR + id + ".tscn").instantiate()
	bike.position = at
	w.add_child(bike)
	return bike

func _rider(w: Node3D, helper: Node, bike: RigidBody3D) -> CharacterBody3D:
	var p: CharacterBody3D = load(PLAYER).instantiate()
	p.position = bike.global_position + Vector3(3, 0.5, 0)
	w.add_child(p)
	await _tick(5)
	helper.call("seat_character", bike, p)
	await _tick(20)
	return p

## hold the bike at `v` m/s along its nose for `frames` (the springs settle under speed), throttle held
func _hold(bike: RigidBody3D, v: float, frames: int) -> void:
	Input.action_press("throttle")
	for i in frames:
		var nose := -bike.global_basis.z
		nose.y = 0
		nose = nose.normalized()
		var lv := bike.linear_velocity
		bike.linear_velocity = Vector3(nose.x * v, lv.y, nose.z * v)
		await physics_frame

func _release_all() -> void:
	for a in ["throttle", "left", "right", "brake"]:
		Input.action_release(a)

func _bike(w: Node3D, helper: Node, id: String, x: float) -> void:
	print("-- %s" % id)
	var cfg: Resource = load(DIR + id + "Config.tres") if not stub else null
	var top: float = float(cfg.get("max_speed")) if cfg else 45.0
	var max_lean: float = float(cfg.get("motorcycle_lean_degrees")) if cfg else 28.0
	var radius: float = float(cfg.get("wheel_radius")) if cfg else 0.4

	# ── rest + side stand ──
	var bike := _spawn(w, id, Vector3(x, 0.9, 1900))
	await _tick(150)
	var tilt := _tilt(bike)
	_check(id + " rest: upright", tilt < 2.0 and bike.linear_velocity.length() < 0.1,
			"tilt %.2f deg, %.3f m/s" % [tilt, bike.linear_velocity.length()])
	if not stub:
		var wf: Node3D = bike.get_node("Model/wheel_f")
		var wb: Node3D = bike.get_node("Model/wheel_b")
		# the bottom of a leaned wheel: its centre's height minus r cos(lean)
		var lean0: float = bike.call("lean_degrees_now")
		var gap_f := wf.global_position.y - radius * cos(deg_to_rad(lean0))
		var gap_b := wb.global_position.y - radius * cos(deg_to_rad(lean0))
		_check(id + " rest: wheels on the ground", absf(gap_f) < 0.04 and absf(gap_b) < 0.04,
				"front %+.3f m, back %+.3f m" % [gap_f, gap_b])
		_check(id + " rest: on its side stand", lean0 > 4.0 and lean0 < 10.0, "lean %.1f deg (+ = left)" % lean0)

	# ── seated ──
	var p := await _rider(w, helper, bike)
	await _tick(40)
	var seated: bool = helper.call("occupant_of", bike) == p
	if not stub:
		var lean_s: float = bike.call("lean_degrees_now")
		_check(id + " seated: stands up straight", seated and absf(lean_s) < 1.5, "lean %.2f deg, seated %s" % [lean_s, seated])
	else:
		_check(id + " seated", seated, "")

	# ── walking pace ──
	var worst := 0.0
	Input.action_press("throttle")
	for i in 180:
		var nose := -bike.global_basis.z
		bike.linear_velocity = Vector3(nose.x * 2.0, bike.linear_velocity.y, nose.z * 2.0)
		await physics_frame
		worst = maxf(worst, _tilt(bike))
	_release_all()
	_check(id + " 2 m/s: stays up", worst < 3.0 and helper.call("occupant_of", bike) == p, "worst tilt %.2f deg" % worst)

	# ── turn ──
	if not stub:
		var v := minf(15.0, top * 0.8)
		await _hold(bike, v, 60)
		Input.action_press("left")
		var lean_max := 0.0
		var expect := 0.0
		var body_worst := 0.0
		var rider_gap := 0.0
		for i in 120:
			await physics_frame
			if i >= 60:
				var lean: float = bike.call("lean_degrees_now")
				if lean > lean_max:
					lean_max = lean
					var sp := Vector2(bike.linear_velocity.x, bike.linear_velocity.z).length()
					var wr: float = bike.call("motion_yaw_rate_now")
					expect = minf(rad_to_deg(atan(sp * wr / 9.81)), max_lean)
				body_worst = maxf(body_worst, _tilt(bike))
				rider_gap = maxf(rider_gap, absf(rad_to_deg(p.global_rotation.z - bike.global_rotation.z) - lean))
		_release_all()
		_check(id + " turn: leans left", lean_max > 8.0 and absf(lean_max - expect) <= 0.25 * absf(expect) + 1.0,
				"lean %.1f deg, atan(v w / g) %.1f deg, cap %.0f" % [lean_max, expect, max_lean])
		_check(id + " turn: the body stays level", body_worst < 6.0, "worst tilt %.2f deg" % body_worst)
		_check(id + " turn: the rider rolls with it", rider_gap < 3.0, "rider vs bike %.2f deg" % rider_gap)
		await _tick(90)

	# ── kerb ──
	bike.linear_velocity = Vector3.ZERO
	bike.angular_velocity = Vector3.ZERO
	bike.global_transform = Transform3D(Basis(), Vector3(x, 0.6, 1800))
	await _tick(60)
	# a raised slab whose near edge (a 0.15 m step) crosses the path at 35 deg at z 1780: the bike climbs on and stays
	var yaw := deg_to_rad(35.0)
	var kerb := _box(w, Vector3(80, 0.15, 40), Vector3(x, 0.075, 1780) + Basis(Vector3.UP, yaw) * Vector3(0, 0, -20), 35.0)
	await physics_frame
	worst = 0.0
	var v_k := minf(12.0, top * 0.85)
	Input.action_press("throttle")
	for i in 150:
		var nose := -bike.global_basis.z
		nose.y = 0
		nose = nose.normalized()
		bike.linear_velocity = Vector3(nose.x * v_k, bike.linear_velocity.y, nose.z * v_k)
		await physics_frame
		worst = maxf(worst, _tilt(bike))
	_release_all()
	await _tick(60)
	var on: bool = helper.call("occupant_of", bike) == p
	_check(id + " kerb at %.0f m/s: no flip, rider on" % v_k, worst < 15.0 and on and _tilt(bike) < 5.0,
			"worst tilt %.1f deg, after %.1f, rider on %s" % [worst, _tilt(bike), on])
	kerb.queue_free()

	if stub:
		_end(helper, bike, p)
		return
	# ── bump and crash into a wall ──
	for case in [["bump", 2.5], ["crash", minf(13.0, top * 0.85)]]:
		if helper.call("occupant_of", bike) != p:
			helper.call("seat_character", bike, p)
			await _tick(20)
		bike.linear_velocity = Vector3.ZERO
		bike.angular_velocity = Vector3.ZERO
		bike.global_transform = Transform3D(Basis(), Vector3(x, 0.6, 1700))
		await _tick(60)
		var wall := _box(w, Vector3(8, 3, 1), Vector3(x, 1.5, 1700 - 14.0))
		var hp0: float = p.get_node("Health").call("current_health_now")
		var v_c: float = case[1]
		var thrown_at := -1
		var max_up := -INF
		var seat_y := p.global_position.y
		for i in 240:
			if helper.call("occupant_of", bike) == p:
				var nose := -bike.global_basis.z
				nose.y = 0
				nose = nose.normalized()
				# held at speed until the hit (a scripted throttle; the wall stops it, not the probe)
				if bike.global_position.z > 1700 - 12.0:
					bike.linear_velocity = Vector3(nose.x * v_c, bike.linear_velocity.y, nose.z * v_c)
			elif thrown_at < 0:
				thrown_at = i
			if thrown_at >= 0:
				max_up = maxf(max_up, p.global_position.y)
			await physics_frame
		var hp1: float = p.get_node("Health").call("current_health_now") if is_instance_valid(p) else 0.0
		var kept: bool = helper.call("occupant_of", bike) == p
		if case[0] == "bump":
			_check(id + " bump at 2.5 m/s: the rider stays on", kept and hp1 >= hp0, "seated %s, hp %.0f -> %.0f" % [kept, hp0, hp1])
		else:
			_check(id + " crash at %.0f m/s: the rider is thrown" % v_c, not kept and int(bike.call("throws_now")) >= 1
					and hp1 < hp0 and max_up - seat_y > 0.3,
					"thrown %s at tick %d, rose %.2f m off the seat, hp %.0f -> %.0f" % [not kept, thrown_at, max_up - seat_y, hp0, hp1])
		wall.queue_free()
		await _tick(2)
	_end(helper, bike, p)
	await _parts(w, id, x)

## the component parts: every bike part has a mask slot, a front crash takes the cowl off as debris, a mirror comes
## off, and the part mask carried to another copy (a remote peer's) reproduces them
func _parts(w: Node3D, id: String, x: float) -> void:
	var bike := _spawn(w, id, Vector3(x, 0.9, 1600))
	await _tick(60)
	var dm: Node = bike.get_node("DamageModel")
	var names := ["fairing", "mirror_l", "mirror_r"]
	for n in ["top_box", "windscreen"]:
		if bike.get_node_or_null("Model/" + n) != null:
			names.append(n)
	var missing := []
	for n in names:
		if int(dm.call("part_state_now", n)) < 0:
			missing.append(n)
	_check(id + " parts: every part is a damage part", missing.is_empty(), "%s; missing %s" % [names, missing])
	var debris0: int = dm.call("debris_count_now")
	var nose: float = bike.get_node("Model/fairing").position.z if bike.has_node("Model/fairing") else -0.6
	# crash by crash until the cowl drops (four at once wreck a light bike: health is the car's rule too)
	for i in 8:
		if int(dm.call("part_state_now", "fairing")) == 3 or not is_instance_valid(bike):
			break
		dm.call("crash_at", Vector3(0, 0.0, nose - 0.3), 9.0)
		await _tick(8)
	if not is_instance_valid(bike):
		_check(id + " parts: the bike outlives its cowl", false, "wrecked first")
		return
	dm.call("damage_part", "mirror_l", 130.0)
	await _tick(10)
	var st_f: int = dm.call("part_state_now", "fairing")
	var st_m: int = dm.call("part_state_now", "mirror_l")
	_check(id + " parts: a front crash takes the cowl off", st_f == 3 and int(dm.call("debris_count_now")) > debris0,
			"fairing state %d, mirror_l %d, debris %d -> %d" % [st_f, st_m, debris0, int(dm.call("debris_count_now"))])
	var mask: int = dm.call("part_mask_now")
	var copy := _spawn(w, id, Vector3(x + 4, 0.9, 1600))
	await _tick(30)
	var dm2: Node = copy.get_node("DamageModel")
	dm2.call("apply_replicated_mask", mask)
	await _tick(5)
	var same := true
	for n in names:
		if int(dm2.call("part_state_now", n)) != int(dm.call("part_state_now", n)):
			same = false
	_check(id + " parts: the mask reproduces them on a copy", same and st_m == 3,
			"mask %d, copy fairing %d mirror_l %d" % [mask, int(dm2.call("part_state_now", "fairing")), int(dm2.call("part_state_now", "mirror_l"))])
	bike.queue_free()
	copy.queue_free()
	await _tick(2)

func _end(helper: Node, bike: RigidBody3D, p: CharacterBody3D) -> void:
	_release_all()
	if is_instance_valid(p) and helper.call("occupant_of", bike) == p:
		helper.call("exit_driver", bike)
	await _tick(2)
	if is_instance_valid(p):
		p.queue_free()
	bike.queue_free()
	await _tick(2)
