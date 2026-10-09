extends SceneTree
## THE BLOCKED-MUZZLE HINT (PLAN.md 1d / THE ORDER 0.3): the camera sees the aimed point, but the muzzle leg of the
## two-stage trace meets something first (a shelf, a wall corner) and the round never reaches the crosshair. The
## crosshair now dims and marks where the round will stop. A real Player with an ASR1 (pickup path) aiming at a wall
## 25 m out, and a thin post set ON the muzzle's line 1.2 m out, which the over-the-shoulder camera sees past. (A
## shelf between muzzle and camera height is the same code path, but on this body the combat camera is only ~5 cm
## above the muzzle, too marginal for a stand.)
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_muzzle_blocked.gd [-- --control]
##   (--control: show_blocked off -- the crosshair never says so)

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


func _initialize() -> void:
	var control := "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	_box(world, Vector3(400, 2, 400), Vector3(0, -1, 0))
	_box(world, Vector3(40, 10, 1), Vector3(0, 5, -25))
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
	cam_ctrl = p.get_node("TPSCameraController")
	var ch: Control = (load(CROSSHAIR) as PackedScene).instantiate() as Control
	world.add_child(ch)
	ch.set("weapon_controller", wc)
	ch.set("aim_character", p)
	ch.set("show_blocked", not control)
	Input.action_press("aim")
	await _tick(40)
	var aim_at := Vector3(0, 2.6, -24.4)
	await _steer_to(aim_at, 120)
	await _tick(20)
	_check(not bool(ch.call("blocked_now")), "an open line is not blocked")

	var muzzle: Node3D = gun.find_child("Muzzle", true, false)
	var mp := muzzle.global_position
	var on_line := mp + (aim_at - mp).normalized() * 1.2
	var shelf := _box(world, Vector3(0.12, 3.0, 0.12), Vector3(on_line.x, 1.5, on_line.z))
	await _tick(30)
	var cam := p.get_node("ActiveCamera") as Node3D
	var q := PhysicsRayQueryParameters3D.create(cam.global_position, aim_at)
	q.exclude = [p.get_rid()]
	var seen: Dictionary = root.get_world_3d().direct_space_state.intersect_ray(q)
	var cam_over: bool = seen.is_empty() or (seen.collider != shelf)
	print("  muzzle %s, camera %s, post at %s, camera sees past it: %s" % [mp, cam.global_position, on_line, cam_over])
	_check(cam_over, "the camera sees past the post (the case being tested)")
	_check(bool(ch.call("blocked_now")), "with the post on the muzzle's line the crosshair says the muzzle is blocked")
	var mark: Control = null
	for c in ch.get_children():
		if c is Label and c.text == "×":
			mark = c
	_check(mark != null and mark.visible, "and marks where the round stops")
	_check(ch.modulate.a < 0.5, "the reticle dims (alpha %.2f)" % ch.modulate.a)

	shelf.queue_free()
	await _tick(20)
	_check(not bool(ch.call("blocked_now")), "with the post gone the line is clear again")
	Input.action_release("aim")
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
