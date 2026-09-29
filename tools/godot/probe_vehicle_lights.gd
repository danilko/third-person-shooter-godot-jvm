extends SceneTree
## Vehicle lamps (user, 2026-09-28): headlights and tail lights come on at NIGHT; the brake lamps and the reversing
## lamps signal DAY AND NIGHT. A real Player is seated in a real car and drives it through the `Input` actions
## (forward / back / brake), with a sun DirectionalLight in the `sun_light` group turned for noon or midnight, so
## `DayNight` measures it the way it does in the game. A second car is FROZEN and moved kinematically, which is how a
## remote peer's puppet moves: it has no command, so its lamps must come from its motion alone.
##   godot --headless --path . --script tools/godot/probe_vehicle_lights.gd [-- --car=SPC1]
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
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

func _lamps(v: Node) -> String:
	return "head %s brake %s reverse %s" % [v.call("headlights_on_now"), v.call("brake_lights_on_now"), v.call("reverse_lights_on_now")]

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var car_id := "SPC1"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--car="):
			car_id = a.substr(6)
	var scene := "res://src/main/resources/com/openworld/vehicle/%s.tscn" % car_id
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	floor.add_child(cs)
	floor.position.y = -0.5
	world.add_child(floor)
	var sun := DirectionalLight3D.new()
	sun.add_to_group("sun_light")
	world.add_child(sun)
	sun.rotation_degrees = Vector3(-60, 0, 0)            # shines DOWN: noon
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	var car: Node3D = (load(scene) as PackedScene).instantiate()
	car.position = Vector3(0, 1.2, 0)
	world.add_child(car)
	var player: Node3D = (load(PLAYER) as PackedScene).instantiate()
	player.position = Vector3(6, 1, 0)
	world.add_child(player)
	await _tick(90)
	helper.call("seat_character", car, player)
	await _tick(30)
	print("== %s" % car_id)

	print("-- day")
	_check("parked by day: every lamp dark", not car.call("headlights_on_now") and not car.call("brake_lights_on_now")
			and not car.call("reverse_lights_on_now"), _lamps(car))
	Input.action_press("brake")
	await _tick(12)
	_check("brake held by day: the brake lamps light", car.call("brake_lights_on_now"), _lamps(car))
	_check("…and the headlights stay off", not car.call("headlights_on_now"))
	Input.action_release("brake")
	await _tick(12)
	_check("brake released: the brake lamps go out", not car.call("brake_lights_on_now"), _lamps(car))
	Input.action_press("back")
	await _tick(90)
	_check("backing up by day: the reversing lamps light", car.call("reverse_lights_on_now"), _lamps(car))
	_check("…and backing up is not braking", not car.call("brake_lights_on_now"))
	var faces: PackedStringArray = str(car.call("lamp_surfaces_now")).split(",")
	_check("the model's own lamp faces are found (head, tail)", int(faces[0]) > 0 and int(faces[1]) > 0, str(faces))
	_check("the head lamp face is dark by day", not car.call("lamp_face_lit_now", "head"))
	_check("no code-built lens stands on authored lamps", car.get_node_or_null("HeadLensR") == null and car.get_node_or_null("TailLensR") == null)
	if int(faces[2]) > 0:
		_check("backing up lights the model's reversing face", car.call("lamp_face_lit_now", "reverse"))
	else:
		_check("backing up lights the model's tail face (no reversing face)", car.call("lamp_face_lit_now", "tail"))
	Input.action_release("back")
	await _tick(60)
	Input.action_press("forward")
	await _tick(120)
	Input.action_release("forward")
	_check("driving forward: no reversing lamps", not car.call("reverse_lights_on_now"), _lamps(car))
	Input.action_press("back")
	await _tick(10)
	_check("throttle against the rolling direction is braking", car.call("brake_lights_on_now"), _lamps(car))
	Input.action_release("back")
	await _tick(90)

	print("-- night")
	sun.rotation_degrees = Vector3(40, 0, 0)             # shines UP from below the horizon: night
	await _tick(20)
	_check("at night the headlights and tail lamps are on", car.call("headlights_on_now"), _lamps(car))
	var lens: MeshInstance3D = car.get_node_or_null("HeadLensR")
	_check("the head lamp glows", car.call("lamp_face_lit_now", "head")
			or (lens != null and (lens.material_override as StandardMaterial3D).emission_enabled))
	Input.action_press("brake")
	await _tick(12)
	_check("brake at night: brake lamps AND headlights", car.call("brake_lights_on_now") and car.call("headlights_on_now"), _lamps(car))
	Input.action_release("brake")
	sun.rotation_degrees = Vector3(-60, 0, 0)
	await _tick(20)

	print("-- a puppet (frozen, moved kinematically, no command)")
	var pup: RigidBody3D = (load(scene) as PackedScene).instantiate()
	pup.position = Vector3(0, 1.2, 30)
	world.add_child(pup)
	await _tick(60)
	pup.freeze = true
	var fwd := -pup.global_basis.z
	for i in 60:                                         # rolling backward at 3 m/s
		pup.global_position -= fwd * 3.0 / 60.0
		await physics_frame
	_check("a puppet rolling backward shows its reversing lamps", pup.call("reverse_lights_on_now"), _lamps(pup))
	var v := 15.0
	for i in 30:
		pup.global_position += fwd * v / 60.0
		await physics_frame
	for i in 30:                                         # 15 -> 0 m/s in half a second: a hard stop
		v = maxf(0.0, v - 30.0 / 60.0)
		pup.global_position += fwd * v / 60.0
		await physics_frame
		if pup.call("brake_lights_on_now"):
			break
	_check("a puppet stopping hard shows its brake lamps", pup.call("brake_lights_on_now"), _lamps(pup))

	print("RESULT %s (%d passed, %d failed)" % ["PASS" if fails == 0 else "FAIL", checks - fails, fails])
	quit(0 if fails == 0 else 1)
