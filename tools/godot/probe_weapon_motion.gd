extends SceneTree
## A weapon's own moving parts move on every shot, about their own pivot, and are ready before the next shot.
##
##   stdbuf -oL /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --headless --fixed-fps 60 \
##       --path . --script tools/godot/probe_weapon_motion.gd   [-- --control]
##
## The clips are authored in each weapon's .blend (a part's ORIGIN is its PIVOT, its motion an NLA-track action)
## and arrive on the model's own AnimationPlayer (`Model/AnimationPlayer`, WeaponItem.weaponAnimatorPath). Every
## measurement is taken RELATIVE TO THE PART'S REST TRANSFORM, read before the first shot — the rest is the pivot,
## not the origin, so an absolute reading would say nothing.
##
##   SNR1  `bolt_work`: the handle lifts ~60 deg about the bore, the knob rises, the bolt draws back ~4 cm, and it
##         is home inside the 1.46 s fire interval.
##   REV1  `cylinder_index`: two shots, each turns the cylinder one chamber (60 deg) about its own axis,
##         counter-clockwise seen from behind (a S&W), without the axis moving, settled inside the 0.5 s interval.
##
## `--control` clears fire_animation on both weapons: nothing may move.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"
var fails := 0
var control := false

func _check(label: String, ok: bool, detail: String) -> void:
	if not ok:
		fails += 1
	print("  %s  %-58s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _armed(world: Node3D, id: String, at: Vector3) -> Array:
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	world.add_child(p)
	p.position = at
	await _tick(40)
	var gun: Node3D = (load(WEAPON % id) as PackedScene).instantiate()
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node("WeaponController")
	for slot in range(7):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(40)
	_check("%s reached the hand" % id, String(gun.get_parent().name).begins_with("Socket"), str(gun.get_parent().name))
	if control:
		gun.set("fire_animation", "")
	return [p, gun]

func _shoot() -> void:
	Input.action_press("fire")
	await _tick(2)
	Input.action_release("fire")

## The part's motion relative to its rest: [angle deg, signed angle about weapon +Z, offset from rest].
func _rel(part: Node3D, rest: Transform3D) -> Array:
	var d := rest.affine_inverse() * part.transform
	var q := d.basis.get_rotation_quaternion()
	var ang := rad_to_deg(q.get_angle())
	var about_z := signf(q.get_axis().dot(Vector3(0, 0, 1))) * ang if ang > 0.01 else 0.0
	return [ang, about_z, part.transform.origin - rest.origin]

func _bolt(world: Node3D) -> void:
	print("SNR1 bolt_work")
	var r := await _armed(world, "SNR1", Vector3(0, 1.2, 0))
	var gun: Node3D = r[1]
	var bolt: Node3D = gun.get_node_or_null("Model/Bolt")
	_check("the bolt is its own node", bolt != null, "Model/Bolt" if bolt else "missing")
	if bolt == null:
		return
	var anim: AnimationPlayer = gun.get_node_or_null("Model/AnimationPlayer")
	_check("the model carries the clip", anim != null and anim.has_animation("bolt_work"), "Model/AnimationPlayer")
	var rest := bolt.transform
	Input.action_press("aim")
	await _tick(90)
	var mag0 := int(gun.get("magazine"))
	await _shoot()
	var max_angle := 0.0
	var max_back := 0.0
	var max_up := 0.0
	for f in range(int(1.46 * 60)):
		await physics_frame
		var m := _rel(bolt, rest)
		max_angle = maxf(max_angle, m[0])
		max_back = maxf(max_back, (m[2] as Vector3).z)
		# the knob tip: 0.049 m right of the pivot at rest — how far it rises
		max_up = maxf(max_up, (bolt.transform * Vector3(0.049, 0, 0)).y - rest.origin.y)
	Input.action_release("aim")
	var end := _rel(bolt, rest)
	_check("the shot fired", int(gun.get("magazine")) == mag0 - 1, "mag %d -> %d" % [mag0, int(gun.get("magazine"))])
	if control:
		_check("control: no clip, the bolt does not move", max_angle < 0.5 and max_back < 0.005, "angle %.1f back %.3f" % [max_angle, max_back])
	else:
		_check("the handle lifts ~60 deg about the bore", absf(max_angle - 60.0) < 3.0, "%.1f deg" % max_angle)
		_check("the knob rises, not falls", max_up > 0.03, "tip up %.3f m" % max_up)
		_check("the bolt draws back ~4 cm", max_back > 0.035, "%.3f m" % max_back)
		_check("home before the next shot is allowed", (end[2] as Vector3).length() < 0.002 and end[0] < 0.5,
			"after 1.46 s: offset %.4f m, angle %.2f deg" % [(end[2] as Vector3).length(), end[0]])
	(r[0] as Node).queue_free()
	await _tick(5)

func _cylinder(world: Node3D) -> void:
	print("REV1 cylinder_index")
	var r := await _armed(world, "REV1", Vector3(10, 1.2, 0))
	var gun: Node3D = r[1]
	var cyl: Node3D = gun.get_node_or_null("Model/Cylinder")
	_check("the cylinder is its own node", cyl != null, "Model/Cylinder" if cyl else "missing")
	if cyl == null:
		return
	var rest := cyl.transform
	_check("its origin is on the cylinder axis, not the grip", rest.origin.length() > 0.05,
		"rest origin (%.4f, %.4f, %.4f)" % [rest.origin.x, rest.origin.y, rest.origin.z])
	Input.action_press("aim")
	await _tick(60)
	for shot in range(2):
		var mag0 := int(gun.get("magazine"))
		await _shoot()
		var max_angle := 0.0
		var signed_at_max := 0.0
		var drift := 0.0
		var frames := int(0.5 * 60) - 2
		for f in range(frames):
			await physics_frame
			var m := _rel(cyl, rest)
			if m[0] > max_angle:
				max_angle = m[0]
				signed_at_max = m[1]
			drift = maxf(drift, (m[2] as Vector3).length())
		var settled := _rel(cyl, rest)
		await physics_frame
		var after := _rel(cyl, rest)
		_check("shot %d fired" % (shot + 1), int(gun.get("magazine")) == mag0 - 1, "mag %d -> %d" % [mag0, int(gun.get("magazine"))])
		if control:
			_check("control: no clip, the cylinder does not turn", max_angle < 0.5, "%.1f deg" % max_angle)
			continue
		_check("shot %d turns it one chamber (60 deg)" % (shot + 1), absf(max_angle - 60.0) < 2.0, "%.1f deg" % max_angle)
		_check("shot %d: counter-clockwise seen from behind (+Z)" % (shot + 1), signed_at_max > 0.0, "%+.1f deg about +Z" % signed_at_max)
		_check("shot %d: the axis does not move" % (shot + 1), drift < 0.001, "%.5f m" % drift)
		_check("shot %d: settled before the next shot" % (shot + 1), absf(after[0] - settled[0]) < 0.05,
			"%.2f -> %.2f deg" % [settled[0], after[0]])
		await _tick(4)
	Input.action_release("aim")

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(80, 2, 80)
	cs.shape = sh
	floor.add_child(cs)
	world.add_child(floor)
	floor.position = Vector3(0, -1, 0)
	await _bolt(world)
	await _cylinder(world)
	print("PASS (0 failures)" if fails == 0 else "FAIL (%d failures)" % fails)
	quit(1 if fails > 0 else 0)
