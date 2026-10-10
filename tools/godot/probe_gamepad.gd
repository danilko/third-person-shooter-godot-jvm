extends SceneTree
## The gamepad (PLAN.md 1.1 / F1, 2026-10-09): real joypad events through Input.parse_input_event, the path a pad
## takes, on a real Player in WorldSystems.tscn (its MenuManager included). Every case has its control.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_gamepad.gd
##
## 1. a pad event makes the device PAD, a key press makes it keyboard again (InputDevice);
## 2. the left stick runs at full deflection and WALKS part way (ANALOG_WALK_BELOW) -- control: the full stick is
##    faster than the part stick;
## 3. the right stick turns at a rate: full right turns right, the response curve makes half deflection far slower
##    than half the full rate, and the turn boost adds speed after a held beat;
## 4. aim assist: an AI 4 deg off the crosshair, LT pressed on a pad -> the view snaps onto its chest; control: the
##    same with aim_assist off stays ~4 deg off; and a mouse player (device KEYBOARD_MOUSE) gets no snap;
## 5. friction: the stick turns slower with the crosshair on the body than off it;
## 6. Start pauses and opens the pause menu, B (crouch) never does; B backs out of the open pause menu;
## 7. in a car: Y enters, RT is the analog throttle (half trigger slower than full), LT reverses, and neither trigger
##    fires a gun or swings the camera into aim (they are aim / fire on foot).

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI     := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const SYSTEMS := "res://src/main/resources/com/openworld/world/WorldSystems.tscn"
const CAR    := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"

var p: CharacterBody3D
var cam: Camera3D
var ctrl: Node
var gm: Node
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _axis(axis: int, v: float) -> void:
	var e := InputEventJoypadMotion.new()
	e.device = 0
	e.axis = axis
	e.axis_value = v
	Input.parse_input_event(e)

func _button(b: int, down: bool) -> void:
	var e := InputEventJoypadButton.new()
	e.device = 0
	e.button_index = b
	e.pressed = down
	Input.parse_input_event(e)

func _key(code: Key) -> void:
	for down in [true, false]:
		var e := InputEventKey.new()
		e.physical_keycode = code
		e.keycode = code
		e.pressed = down
		Input.parse_input_event(e)

func _yaw() -> float:
	var f := -cam.global_transform.basis.z
	return rad_to_deg(atan2(-f.x, -f.z))

func _pitch() -> float:
	var f := -cam.global_transform.basis.z
	return rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))

func _hspeed() -> float:
	return Vector2(p.velocity.x, p.velocity.z).length()

## yaw change (deg) over `frames` with the right stick at `x`
func _turn(x: float, frames: int) -> float:
	var y0 := _yaw()
	var acc := 0.0
	_axis(JOY_AXIS_RIGHT_X, x)
	for i in range(frames):
		await physics_frame
		var y1 := _yaw()
		acc += wrapf(y1 - y0, -180.0, 180.0)
		y0 = y1
	_axis(JOY_AXIS_RIGHT_X, 0.0)
	await _tick(3)
	return acc

func _off_target(t: Node3D) -> float:
	var to: Vector3 = t.global_position + Vector3(0, 1.25, 0) - cam.global_position
	var f := -cam.global_transform.basis.z
	return rad_to_deg(f.angle_to(to))

func _steer_mouse(target: Vector3, frames: int) -> void:
	for i in range(frames):
		var to: Vector3 = target - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		if absf(dy) + absf(dp) < 0.01:
			return
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / 0.07, -dp / 0.07)
		ctrl.call("_input", ev)
		await physics_frame

## a fresh AI standing `dist` m ahead of the player, `side_deg` to the right of the view
func _ai_at(world: Node3D, dist: float, side_deg: float) -> Node3D:
	var t: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	t.get_node("Health").set("max_health", 100000.0)
	world.add_child(t)
	var f := -cam.global_transform.basis.z
	f.y = 0
	f = f.normalized().rotated(Vector3.UP, deg_to_rad(-side_deg))
	t.global_position = Vector3(p.global_position.x, 0, p.global_position.z) + f * dist
	(t.get("character_info") as Resource).set("faction", "neutral")
	t.get_node("MovementController").set_physics_process(false)
	var brain := t.get_node_or_null("AIController")
	if brain:
		brain.process_mode = Node.PROCESS_MODE_DISABLED
	return t

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(600, 2, 600)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	var sys: Node = (load(SYSTEMS) as PackedScene).instantiate()
	for c in sys.get_children():
		if c.name == "HUDManager":
			c.free()
	world.add_child(sys)
	gm = root.get_node("GameManager")
	await _tick(3)
	p = (load(PLAYER) as PackedScene).instantiate() as CharacterBody3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(60)
	cam = p.get_node("ActiveCamera") as Camera3D
	ctrl = p.get_node("TPSCameraController")

	print("=== 1. the device ===")
	_key(KEY_V)
	await _tick(2)
	var d0: String = gm.call("input_device_now")
	_axis(JOY_AXIS_LEFT_X, 0.8)
	_axis(JOY_AXIS_LEFT_X, 0.0)
	await _tick(2)
	var d1: String = gm.call("input_device_now")
	_key(KEY_V)
	await _tick(2)
	var d2: String = gm.call("input_device_now")
	_check("a stick makes the device PAD, a key makes it keyboard again", d0 == "KEYBOARD_MOUSE" and d1 == "PAD"
		and d2 == "KEYBOARD_MOUSE", "%s -> %s -> %s" % [d0, d1, d2])
	_key(KEY_V)   # V is the view toggle: pressed twice above, so the view is back where it was
	await _tick(2)
	_key(KEY_V)
	await _tick(10)

	print("=== 2. the left stick ===")
	_axis(JOY_AXIS_LEFT_Y, -1.0)
	await _tick(80)
	var full := _hspeed()
	_axis(JOY_AXIS_LEFT_Y, -0.45)
	await _tick(80)
	var part := _hspeed()
	_axis(JOY_AXIS_LEFT_Y, 0.0)
	await _tick(60)
	_check("the full stick runs", full > 3.5, "%.2f m/s" % full)
	_check("  ... part way walks (slower) -- control: the full stick", part > 0.5 and part < full * 0.75,
		"%.2f m/s vs %.2f" % [part, full])

	print("=== 3. the right stick ===")
	gm.call("force_input_device", "PAD")
	var r_full := await _turn(1.0, 15)         # 0.25 s: before the turn boost
	var r_half := await _turn(0.5, 15)
	var r_long := await _turn(1.0, 60)         # 1 s: the boost ramps in after 0.25 s
	_check("full right turns right at ~220 deg/s", r_full < -40.0 and r_full > -70.0, "%.1f deg in 0.25 s" % r_full)
	_check("  ... half way is far less than half that (the curve)", absf(r_half) < absf(r_full) * 0.35 and absf(r_half) > 0.5,
		"%.1f deg vs %.1f" % [r_half, r_full])
	_check("  ... held over, the turn boost speeds it up", absf(r_long) > 4.0 * absf(r_full) * 1.15,
		"%.1f deg in 1 s (no boost would be %.1f)" % [r_long, 4.0 * r_full])

	print("=== 4. aim assist: the ADS snap ===")
	var results := {}
	for case_name in ["assist", "control_off", "control_mouse"]:
		ctrl.set("aim_assist", case_name != "control_off")
		gm.call("force_input_device", "KEYBOARD_MOUSE" if case_name == "control_mouse" else "PAD")
		var t := _ai_at(world, 20.0, 4.0)
		await _tick(30)
		var before := _off_target(t)
		if case_name == "control_mouse":
			Input.action_press("aim")      # the right mouse button: a pad axis would make the device PAD
		else:
			_axis(JOY_AXIS_TRIGGER_LEFT, 1.0)
		await _tick(30)
		var after := _off_target(t)
		_axis(JOY_AXIS_TRIGGER_LEFT, 0.0)
		Input.action_release("aim")
		await _tick(40)
		results[case_name] = [before, after]
		t.queue_free()
		await _tick(5)
	ctrl.set("aim_assist", true)
	gm.call("force_input_device", "PAD")
	var a: Array = results["assist"]
	var c_off: Array = results["control_off"]
	var c_mouse: Array = results["control_mouse"]
	_check("LT on a pad snaps onto a body 4 deg off", a[0] > 3.0 and a[1] < 1.0, "%.2f -> %.2f deg" % [a[0], a[1]])
	_check("  control: aim assist off stays off target", c_off[1] > 2.5, "%.2f -> %.2f deg" % [c_off[0], c_off[1]])
	_check("  control: a mouse player gets no snap", c_mouse[1] > 2.5, "%.2f -> %.2f deg" % [c_mouse[0], c_mouse[1]])

	print("=== 5. aim assist: friction ===")
	var t2 := _ai_at(world, 15.0, 0.0)
	await _tick(20)
	await _steer_mouse(t2.global_position + Vector3(0, 1.25, 0), 60)
	gm.call("force_input_device", "PAD")
	var on := await _turn(0.6, 4)
	await _steer_mouse(t2.global_position + Vector3(0, 1.25, 0) + (cam.global_transform.basis.x * 6.0), 60)
	gm.call("force_input_device", "PAD")
	var off := await _turn(0.6, 4)
	_check("the stick turns slower over a body (friction)", absf(on) < absf(off) * 0.7 and absf(off) > 0.1,
		"on %.2f deg vs off %.2f deg in 4 frames" % [on, off])
	t2.queue_free()

	print("=== 6. pause on Start, never on B ===")
	var mm: Node = sys.get_node("MenuManager")
	_button(JOY_BUTTON_B, true)
	await process_frame
	_button(JOY_BUTTON_B, false)
	await process_frame
	var paused_b := paused
	_button(JOY_BUTTON_START, true)
	await process_frame
	_button(JOY_BUTTON_START, false)
	await process_frame
	var paused_start := paused
	_button(JOY_BUTTON_B, true)
	await process_frame
	_button(JOY_BUTTON_B, false)
	await process_frame
	var paused_after_back := paused
	_check("B (crouch) does not pause", not paused_b, "")
	_check("Start pauses", paused_start, "")
	_check("  ... and B backs out of the pause menu", not paused_after_back, "")
	paused = false
	await _tick(5)

	print("=== 7. in a car: the triggers drive ===")
	var car: RigidBody3D = (load(CAR) as PackedScene).instantiate() as RigidBody3D
	world.add_child(car)
	var fwd := -cam.global_transform.basis.z
	fwd.y = 0
	car.global_position = p.global_position + fwd.normalized() * 30.0 + Vector3(0, 1.0, 0)
	await _tick(40)
	p.global_position = car.global_transform * Vector3(0, 0.2, 2.9)   # probe_driveby_aim's spot by the EntranceArea
	await _tick(20)
	_button(JOY_BUTTON_Y, true)
	await _tick(2)
	_button(JOY_BUTTON_Y, false)
	await _tick(60)
	var seated: bool = p.get("current_vehicle_node") != null
	_check("Y enters the car", seated, "")
	var speeds := {}
	for case_name in ["half", "full"]:
		car.linear_velocity = Vector3.ZERO
		await _tick(30)
		_axis(JOY_AXIS_TRIGGER_RIGHT, 0.5 if case_name == "half" else 1.0)
		await _tick(90)
		var cf := -car.global_transform.basis.z
		speeds[case_name] = car.linear_velocity.dot(cf)
		_axis(JOY_AXIS_TRIGGER_RIGHT, 0.0)
		await _tick(120)
	_check("RT drives forward", float(speeds["full"]) > 4.0, "%.2f m/s after 1.5 s" % float(speeds["full"]))
	_check("  ... a half trigger is slower (analog)", float(speeds["half"]) > 0.5 and float(speeds["half"]) < float(speeds["full"]) * 0.8,
		"%.2f vs %.2f m/s" % [float(speeds["half"]), float(speeds["full"])])
	car.linear_velocity = Vector3.ZERO
	await _tick(30)
	_axis(JOY_AXIS_TRIGGER_LEFT, 1.0)
	await _tick(120)
	var back := car.linear_velocity.dot(-car.global_transform.basis.z)
	_axis(JOY_AXIS_TRIGGER_LEFT, 0.0)
	_check("LT reverses", back < -1.0, "%.2f m/s" % back)
	var wc: Node = p.get_node("WeaponController")
	var shots_before: int = wc.call("shots_fired_now")
	_axis(JOY_AXIS_TRIGGER_RIGHT, 1.0)
	_axis(JOY_AXIS_TRIGGER_LEFT, 1.0)
	await _tick(30)
	var aim_cam := Input.is_action_pressed("vehicle_fire")
	_axis(JOY_AXIS_TRIGGER_RIGHT, 0.0)
	_axis(JOY_AXIS_TRIGGER_LEFT, 0.0)
	_check("  ... and the triggers neither fire nor aim in a car", int(wc.call("shots_fired_now")) == shots_before and not aim_cam,
		"shots +%d" % (int(wc.call("shots_fired_now")) - shots_before))
	print("")
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
