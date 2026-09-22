extends SceneTree
## The chase camera sits BEHIND a car whatever way the car was facing when it was built (user, 2026-09-22: "when I
## drive, the camera flips 180 and shows the character's front"). The car rig is top-level, which froze its frame
## at the car's rotation at _ready; a car placed rotated 180 deg drove with the camera in front of it.
##   stdbuf -oL <godot> --headless --path . --script tools/godot/probe_vehicle_camera_frame.gd
## For cars built at 0, 90, 180 and -90 deg, a player is seated as the driver and, after the follow settles, the
## camera must be BEHIND the car (camera->car along the car's forward) and looking the way the car points.
const CAR := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-44s %s" % ["PASS" if ok else "FAIL", label, detail])

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = BoxShape3D.new()
	(cs.shape as BoxShape3D).size = Vector3(400, 1, 400)
	floor.add_child(cs)
	floor.position = Vector3(0, -0.5, 0)
	world.add_child(floor)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	var i := 0
	for deg in [0.0, 90.0, 180.0, -90.0]:
		var car := (load(CAR) as PackedScene).instantiate() as RigidBody3D
		car.rotation = Vector3(0, deg_to_rad(deg), 0)     # BEFORE add_child, as a scene-placed car is
		car.position = Vector3(i * 30.0 - 45.0, 0.8, 0)
		world.add_child(car)
		var p := (load(PLAYER) as PackedScene).instantiate() as Node3D
		p.position = car.position + Vector3(0, 0, 6)
		world.add_child(p)
		for k in 20:
			await physics_frame
		helper.call("seat_character", car, p)
		for k in 180:
			await physics_frame
		var cam := car.get_node("ActiveCamera") as Camera3D
		var fwd := -car.global_transform.basis.z
		fwd.y = 0
		fwd = fwd.normalized()
		var rel := car.global_position - cam.global_position
		rel.y = 0
		var behind := rel.normalized().dot(fwd)
		var look := -cam.global_transform.basis.z
		look.y = 0
		var along := look.normalized().dot(fwd)
		_check("car built at %4.0f deg: camera behind, looking ahead" % deg, cam.current and behind > 0.9 and along > 0.9,
				"behind %.2f, looking %.2f, current %s" % [behind, along, cam.current])
		p.queue_free()
		car.queue_free()
		i += 1
		await physics_frame
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
