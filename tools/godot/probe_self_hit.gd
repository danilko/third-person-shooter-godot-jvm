extends SceneTree
## PLAN.md 0.2 -- a shot flicked behind must leave a gun that is pointing at it, and never hit the shooter.
##
##   godot --headless --path . --script tools/godot/probe_self_hit.gd
##
## Drives a real Player: picks an ASR1 up, holds `aim`, then for each yaw offset injects one mouse
## motion through the camera controller's own `_input` (the path a real mouse takes) and presses
## `fire`. At the instant each shot is fired (`ammo_changed` is emitted synchronously inside the
## fire path) it records the angle between the gun's own forward (-Z) and the line from the gun to
## the aim point -- i.e. how far the visible gun points away from where its bullet goes.
##
## Why that angle is the assertion: both views (TPS and FPS) trace the bullet from the animated
## gun's muzzle, so a gun still pointing the old way launches the shot back across the shooter's
## own body. That is how the reported self-hit happened (a held weapon was then a RigidBody3D on a
## layer the AimRay sees). Also asserted: the shooter takes no damage, and every press still
## produces a shot -- a fix that simply refused to fire would pass the angle check.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const IMPACT := "res://src/main/java/com/openworld/world/manager/ImpactManager.java"
const ASR1    := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const YAW_SENS := 0.07                  # TPSCameraController.yawSensitivity, degrees per pixel
const MAX_GUN_OFF_AIM_DEG := 15.0

var world: Node3D
var player: Node3D
var gun: Node3D
var self_hits: Array = []
var shot_angles: Array = []
var shot_frames: Array = []
var press_frame := 0
var fails := 0

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-40s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _box(size: Vector3, pos: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	world.add_child(b)
	b.global_position = pos

func _flick(cam: Node, degrees: float) -> void:
	var ev := InputEventMouseMotion.new()
	ev.relative = Vector2(-degrees / YAW_SENS, 0)   # pendingYaw -= relative.x * sens
	cam.call("_input", ev)

func _on_shot(_a = null, _b = null) -> void:
	var aim: Vector3 = player.get_node("ActiveCamera/AimRay/AimTarget").global_position
	var to_aim: Vector3 = aim - gun.global_position
	to_aim.y = 0.0
	var fwd: Vector3 = -gun.global_basis.z
	fwd.y = 0.0
	if to_aim.length() < 0.5 or fwd.length() < 0.01:
		return
	shot_angles.append(rad_to_deg(fwd.angle_to(to_aim)))
	shot_frames.append(Engine.get_physics_frames() - press_frame)

func _initialize() -> void:
	world = Node3D.new()
	root.add_child(world)
	_box(Vector3(200, 1, 200), Vector3(0, -0.5, 0))
	world.add_child(load(IMPACT).new())
	await _tick(3)

	player = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(player)
	player.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var wc: Node = player.get_node("WeaponController")
	var cam: Node = player.get_node("TPSCameraController")
	player.get_node("Health").connect("hit", func(d): self_hits.append(d))

	gun = (load(ASR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = Vector3(6, 1, 0)
	await _tick(3)
	(gun.get_parent() as Node3D).global_position = player.global_position + Vector3(0, 0.6, 0)
	await _tick(30)
	for slot in range(6):
		wc.call("on_set_weapon", slot)
		await _tick(60)
		if String(gun.get_parent().name).begins_with("Socket"):
			break
	if not String(gun.get_parent().name).begins_with("Socket"):
		print("FAIL: ASR1 never reached a hand socket (parent %s)" % gun.get_parent().name)
		quit(1)
		return
	wc.connect("ammo_changed", _on_shot)

	# Walls all round, so the aim point is a few metres out at every heading.
	for i in range(8):
		var a := TAU * i / 8.0
		_box(Vector3(4, 6, 0.5), player.global_position + Vector3(sin(a), 0, cos(a)) * 4.0)
	Input.action_press("aim")
	await _tick(30)

	var worst := 0.0
	var worst_wait := 0
	var no_shot := 0
	for view in ["TPS", "FPS"]:
		if bool(player.get("is_fps_mode")) != (view == "FPS"):
			Input.action_press("view")           # the real toggle, PlayerCameraController
			await _tick(1)
			Input.action_release("view")
		await _tick(20)
		if bool(player.get("is_fps_mode")) != (view == "FPS"):
			_check("switched to %s" % view, false, "is_fps_mode = %s" % player.get("is_fps_mode"))
		print("")
		print("=== %s ===" % view)
		for settle in [0, 1, 3, 6]:
			for deg in [30.0, 90.0, 135.0, 160.0, 180.0, -135.0, -170.0]:
				if int(gun.get("magazine")) < 3:     # never press into a reload
					gun.set("magazine", int(gun.get("magazine_size")))
				self_hits.clear()
				shot_angles.clear()
				shot_frames.clear()
				_flick(cam, deg)
				await _tick(settle)
				press_frame = Engine.get_physics_frames()
				Input.action_press("fire")
				await _tick(1)
				Input.action_release("fire")
				await _tick(20)
				var off: float = shot_angles.max() if not shot_angles.is_empty() else -1.0
				worst = max(worst, off)
				if shot_angles.is_empty():
					no_shot += 1
				var wait: int = shot_frames.min() if not shot_frames.is_empty() else -1
				worst_wait = max(worst_wait, wait)
				print("    settle %d  flick %+6.1f  shots %d  gun-off-aim %6.1f  press->shot %d frame(s)  self-hits %d" % [settle, deg, shot_angles.size(), off, wait, self_hits.size()])
				if not self_hits.is_empty():
					_check("no self-hit (settle %d, flick %+.0f)" % [settle, deg], false, str(self_hits))
				await _tick(10)
	Input.action_release("aim")

	print("")
	_check("every press fired", no_shot == 0, "%d press(es) produced no shot" % no_shot)
	_check("the gun points at its shot", worst <= MAX_GUN_OFF_AIM_DEG,
		"worst %.1f deg off (limit %.0f)" % [worst, MAX_GUN_OFF_AIM_DEG])
	# An ungated shot reads 0 frames here. The gate may add a frame or two while the body turns
	# (measured: exactly 1, in 11 of 56 cases); more than that is a trigger that feels dead.
	_check("the gate waits at most 3 frames", worst_wait <= 3, "worst press->shot %d frame(s)" % worst_wait)
	print("")
	print("RESULT: %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
