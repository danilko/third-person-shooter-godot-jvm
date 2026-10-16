extends SceneTree
## PLAN.md 2c.1 -- a car stops by itself when nobody drives it (GTA / Forza / NFS all do this).
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_car_stop.gd [-- --control]
##       [--car=SPC1] [--verbose]
## A real Player at the wheel, driven through `Input` (the throttle action), on a long flat strip. Each car (SPC1 the
## sports car, KEC1 the kei car, CRT1 the cart) is brought to 5 / 10 / 25 / 45 m/s (or its top speed, whichever is lower)
## and then (a) the throttle is RELEASED with the player still in the seat, or (b) the player presses use_carrier and
## GETS OUT. Asserted against a table:
##   (a) lift: at rest (< 0.3 m/s) within v / LIFT_MIN_DECEL s, and no harder than a brake (mean <= LIFT_MAX_DECEL);
##   (b) exit: below the bail speed it brakes at once; at a bail (>= 8 m/s) it ROLLS on ~1 s (covers >= 80 % of v in
##       that second), then brakes: at rest within 1 s + v / EXIT_MIN_DECEL + 1.5 s.
## --control: rollingResistance / engineBrakeDecel 0 and Vehicle.brakesWhenLeft off = the car as it shipped (coasts).
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"
const CARS := ["SPC1", "KEC1", "CRT1"]
const SPEEDS := [5.0, 10.0, 25.0, 45.0]
const REST := 0.3
const LIFT_MIN_DECEL := 1.0        # m/s^2, mean over the whole stop
const LIFT_MAX_DECEL := 3.5
const EXIT_MIN_DECEL := 5.0
const BAIL_SPEED := 8.0
var fails := 0
var checks := 0
var verbose := false

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

func _run() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	verbose = "--verbose" in OS.get_cmdline_user_args()
	var cars: Array = CARS
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			cars = [a.substr(6)]
	var w := Node3D.new()
	root.add_child(w)
	current_scene = w
	var f := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var b := BoxShape3D.new()
	b.size = Vector3(60, 1, 4000)
	cs.shape = b
	f.add_child(cs)
	f.position.y = -0.5
	w.add_child(f)
	var helper: Node = load(HELPER).new()
	w.add_child(helper)
	for car_id in cars:
		if control:
			# the shared .tres through the resource cache: an @Export resource reads null off-tree (Known Quirks)
			var cfg: Resource = load("res://src/main/resources/com/openworld/vehicle/%sConfig.tres" % car_id)
			cfg.set("rolling_resistance", 0.0)
			cfg.set("engine_brake_decel", 0.0)
		var top: float = float((load("res://src/main/resources/com/openworld/vehicle/%sConfig.tres" % car_id) as Resource).get("max_speed"))
		var done := {}
		for v in SPEEDS:
			var at: float = minf(v, top * 0.92)
			if done.has(at):
				continue
			done[at] = true
			for mode in ["lift", "exit"]:
				await _case(w, helper, car_id, at, mode, control)
	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)

func _case(w: Node3D, helper: Node, car_id: String, want: float, mode: String, control: bool) -> void:
	var car: RigidBody3D = load("res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id).instantiate()
	car.position = Vector3(0, 1.0, 1900)
	w.add_child(car)
	if control:
		car.set("brakes_when_left", false)
	await _tick(90)
	var p: CharacterBody3D = load(PLAYER).instantiate()
	p.position = Vector3(6, 1, 1900)
	w.add_child(p)
	await _tick(5)
	helper.call("seat_character", car, p)
	await _tick(10)
	var v0 := want
	# up to speed: the velocity along the nose (-Z), the throttle held a second (springs settle), held AT v0
	Input.action_press("throttle")
	for i in 60:
		var lv := car.linear_velocity
		car.linear_velocity = Vector3(lv.x, lv.y, -v0)
		await physics_frame
	var speed0 := car.linear_velocity.length()
	var at0 := car.global_position
	if mode == "lift":
		Input.action_release("throttle")
	else:
		Input.action_release("throttle")
		Input.action_press("use_carrier")
		await physics_frame
		Input.action_release("use_carrier")
	var rest_at := -1.0
	var in_first_s := 0.0
	var trace := ""
	for i in 60 * 60:
		await physics_frame
		var t := (i + 1) / 60.0
		if i == 59:
			in_first_s = car.global_position.distance_to(at0)
		if verbose and i % 30 == 0:
			trace += " %.1f" % car.linear_velocity.length()
		if car.linear_velocity.length() < REST:
			rest_at = t
			break
	var dist := Vector2(car.global_position.x - at0.x, car.global_position.z - at0.z).length()
	if verbose:
		print("    speed every 0.5 s:", trace)
	var seated: bool = helper.call("occupant_of", car) == p
	var detail := "from %.1f m/s: %s, %.1f m" % [speed0, ("rest after %.1f s" % rest_at) if rest_at > 0 else "never at rest in 60 s", dist]
	var label := "%s %s at %.0f m/s" % [car_id, mode, v0]
	if mode == "lift":
		var mean := speed0 / rest_at if rest_at > 0 else 0.0
		_check(label + ": stops, not a brake", seated and rest_at > 0 and rest_at <= speed0 / LIFT_MIN_DECEL
				and mean <= LIFT_MAX_DECEL, detail + ", mean %.2f m/s^2" % mean)
	else:
		var bail := speed0 >= BAIL_SPEED
		var limit := (1.0 if bail else 0.0) + speed0 / EXIT_MIN_DECEL + 1.5
		var rolled := in_first_s >= 0.8 * speed0 if bail else true
		_check(label + (": rolls ~1 s, then brakes" if bail else ": brakes at once"),
				not seated and rest_at > 0 and rest_at <= limit and rolled,
				detail + ", %.1f m in the first second (limit %.1f s)" % [in_first_s, limit])
	if helper.call("occupant_of", car) == p:
		helper.call("exit_driver", car)
	await _tick(2)
	if is_instance_valid(p):
		p.queue_free()
	if is_instance_valid(car):
		car.queue_free()
	await _tick(5)
