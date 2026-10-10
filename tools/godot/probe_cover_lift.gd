extends SceneTree
## THE COVER LIFT (PLAN.md 1d, user 2026-10-09: "raise the gun against the aim target"): low cover the camera sees
## over but the gun's line meets -- a shelf, a car bonnet -- makes the arm RAISE the gun until its line clears, and
## the barrel is re-pointed at the aim target from there. A real Player with an ASR1 (pickup path) aims at a wall
## 25 m out; a shelf 1 m ahead of the muzzle has its top set between the gun's line and the camera's line (measured).
## Asserted: the arm lifts (and not past max_lift), the crosshair's blocked x goes away, a round from the REAL
## (lifted) muzzle reaches the wall, the barrel still points at the aim target, and with the shelf gone the arm
## comes back down.
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_cover_lift.gd [-- --control]
##   (--control: max_lift 0 -- the arm never lifts, the shelf keeps eating the shot)

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const ASR1 := "res://src/main/resources/com/openworld/weapon/ASR1.tscn"
const CROSSHAIR := "res://src/main/resources/com/openworld/ui/Crosshair.tscn"
const SENS := 0.07

var p: Node3D
var cam_ctrl: Node
var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame


func _box(world: Node, size: Vector3, at: Vector3) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = size
	cs.shape = sh
	b.add_child(cs)
	world.add_child(b)
	b.position = at
	return b


func _steer_to(target: Vector3, frames: int) -> void:
	for i in range(frames):
		var cam := p.get_node("ActiveCamera") as Node3D
		var to: Vector3 = target - cam.global_position
		var f := -cam.global_transform.basis.z
		var dy := wrapf(rad_to_deg(atan2(-to.x, -to.z)) - rad_to_deg(atan2(-f.x, -f.z)), -180.0, 180.0)
		var dp := rad_to_deg(atan2(to.y, Vector2(to.x, to.z).length())) - rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
		if absf(dy) + absf(dp) < 0.003:
			return
		var ev := InputEventMouseMotion.new()
		ev.relative = Vector2(-dy / SENS, -dp / SENS)
		cam_ctrl.call("_input", ev)
		await physics_frame


func _line_y(a: Vector3, b: Vector3, z: float) -> float:
	var t := (z - a.z) / (b.z - a.z)
	return a.y + (b.y - a.y) * t


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	_box(world, Vector3(400, 2, 400), Vector3(0, -1, 0))
	var wall := _box(world, Vector3(40, 10, 1), Vector3(0, 5, -25))
	await _tick(3)
	p = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(ASR1) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	if control:
		var mod := p.find_child("WeaponRecoilModifier", true, false)
		if mod == null:
			for n in p.find_children("*", "SkeletonModifier3D", true, false):
				if n.has_method("current_lift"):
					mod = n
		mod.set("max_lift", 0.0)
	cam_ctrl = p.get_node("TPSCameraController")
	var ch: Control = (load(CROSSHAIR) as PackedScene).instantiate() as Control
	world.add_child(ch)
	ch.set("weapon_controller", wc)
	ch.set("aim_character", p)
	Input.action_press("aim")
	await _tick(40)
	var aim_at := Vector3(0, 2.6, -24.4)
	await _steer_to(aim_at, 120)
	await _tick(30)
	_check(float(wc.call("cover_lift_now")) < 0.01, "with nothing in the way the arm carries no lift (%.3f)" % float(wc.call("cover_lift_now")))

	var muzzle: Node3D = gun.find_child("Muzzle", true, false)
	var cam := p.get_node("ActiveCamera") as Node3D
	var mp := muzzle.global_position
	var shelf_z := mp.z - 1.0
	var gun_y := _line_y(mp, aim_at, shelf_z)
	var cam_y := _line_y(cam.global_position, aim_at, shelf_z)
	var top := (gun_y + cam_y) / 2.0
	print("  at the shelf: gun line %.3f, camera line %.3f -> shelf top %.3f" % [gun_y, cam_y, top])
	_check(cam_y - gun_y > 0.04, "the camera's line passes over the gun's at the shelf (the case being tested)")
	var shelf := _box(world, Vector3(3.0, top, 0.4), Vector3(0, top / 2.0, shelf_z))
	await _tick(60)
	await _steer_to(aim_at, 60)
	await _tick(30)
	var lift := float(wc.call("cover_lift_now"))
	print("  lift %.3f m, crosshair blocked %s" % [lift, ch.call("blocked_now")])
	_check(lift > 0.02 and lift <= 0.301, "the arm raises the gun over the shelf, within max_lift (%.3f m)" % lift)
	_check(not bool(ch.call("blocked_now")), "the crosshair no longer says the line is blocked")
	mp = muzzle.global_position
	var shot := String(gun.call("probe_shot", mp, aim_at - mp, 36.0))
	print("  a round from the muzzle at %s -> %s" % [mp, shot])
	_check(shot.contains(str(wall.name)) or shot.split("|")[-1].to_float() > 20.0, "a round from the real muzzle reaches the wall")
	var bore := -muzzle.global_transform.basis.z
	var err := rad_to_deg(bore.angle_to((aim_at - mp).normalized()))
	_check(control or err < 4.0, "the barrel still points at the aim target (%.1f deg off)" % err)
	shelf.queue_free()
	await _tick(60)
	_check(float(wc.call("cover_lift_now")) < 0.01, "with the shelf gone the arm comes back down (%.3f)" % float(wc.call("cover_lift_now")))

	# FULL cover is not lifted over: a 2.5 m wall in the same place is beyond max_lift, so the arm stays down and a
	# round from the muzzle stops in the wall (the camera sees the wall too: the hide-behind-a-wall exploit stays shut).
	var tall := _box(world, Vector3(3.0, 2.5, 0.4), Vector3(0, 1.25, shelf_z))
	await _tick(60)
	mp = muzzle.global_position
	var into := String(gun.call("probe_shot", mp, aim_at - mp, 36.0))
	_check(float(wc.call("cover_lift_now")) < 0.01 and into.split("|")[-1].to_float() < 2.0,
			"a wall above max_lift is not lifted over; the round stops in it (lift %.3f, round %s)" % [float(wc.call("cover_lift_now")), into])
	tall.queue_free()
	Input.action_release("aim")
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
