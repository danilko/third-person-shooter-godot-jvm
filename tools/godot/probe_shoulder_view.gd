extends SceneTree
## How much of the held gun the character's own body hides from the TPS aim camera, per shoulder.
## Runs WITH a display (xvfb-run is fine): it renders the real Player camera while `aim` is held, with the gun
## painted one flat colour, twice -- body shown, body hidden -- and counts the gun's pixels. visible = the ratio.
## The off-shoulder (left: the gun is on the right) is swept over CombatState.cameraLeftShoulderExtra x
## cameraLeftHeightExtra, which is what sized those two numbers (2026-10-04, a long-haired body's hair covered
## the shot from the left).
##
##   xvfb-run -a /data/danilko/bin/Godot_v4.7.2-stable_linux.x86_64 --path . --script tools/godot/probe_shoulder_view.gd \
##       -- [--weapon=ASR1] [--extras=0,0.1,0.2,0.3] [--heights=0,0.1,0.2] [--shots=<dir>] [--assert-left=0.6]

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const WEAPON := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const COMBAT := "res://src/main/resources/com/openworld/character/combatstates/Combat.tres"
const MARK := Color(1, 0, 1)

var shots := ""

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _arg(name: String, def: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return def

func _find_method(n: Node, m: String) -> Node:
	if n.has_method(m):
		return n
	for c in n.get_children():
		var r := _find_method(c, m)
		if r != null:
			return r
	return null

func _meshes(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_meshes(c, out)

func _count() -> int:
	await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_texture().get_image()
	var n := 0
	for y in range(0, img.get_height(), 2):
		for x in range(0, img.get_width(), 2):
			var c := img.get_pixel(x, y)
			if c.r > 0.85 and c.b > 0.85 and c.g < 0.2:
				n += 1
	return n

func _shot(tag: String) -> void:
	if shots == "":
		return
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("%s/%s.png" % [shots, tag])

func _initialize() -> void:
	shots = _arg("shots", "")
	if shots != "":
		DirAccess.make_dir_recursive_absolute(shots)
	DisplayServer.window_set_size(Vector2i(1280, 720))
	var weapon_id := _arg("weapon", "ASR1")
	var extras := Array(_arg("extras", "0,0.1,0.2,0.3").split(",")).map(func(v): return float(v))
	var heights := Array(_arg("heights", "0,0.1,0.2").split(",")).map(func(v): return float(v))
	var assert_left := float(_arg("assert-left", "-1"))

	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.3, 0.32, 0.35)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(1, 1, 1)
	world.add_child(env)
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	b.add_child(cs)
	b.position = Vector3(0, -0.5, 0)
	world.add_child(b)
	await _tick(3)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(WEAPON % weapon_id) as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	if not String(gun.get_parent().name).begins_with("Socket"):
		print("FAIL %s never reached the hand" % weapon_id)
		quit(1)
		return

	var gun_meshes: Array = []
	_meshes(gun.get_node("Model") if gun.has_node("Model") else gun, gun_meshes)   # not the muzzle-flash VFX
	var flat := StandardMaterial3D.new()
	flat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	flat.albedo_color = MARK
	for m in gun_meshes:
		(m as MeshInstance3D).material_override = flat
	var body_meshes: Array = []
	var all_meshes: Array = []
	_meshes(gun, all_meshes)
	_meshes(p.find_child("MeshRoot", true, false), body_meshes)
	print("body meshes hidden for the reference frame: %d" % body_meshes.size())
	body_meshes = body_meshes.filter(func(m): return not all_meshes.has(m))

	var cam := _find_method(p, "shoulder_side_now")
	var combat: Resource = load(COMBAT)
	var shipped := [combat.get("camera_left_shoulder_extra"), combat.get("camera_left_height_extra")]
	Input.action_press("aim")
	await _tick(60)
	print("weapon %s, combat=%s, shoulder side %d, shipped left extras: sideways %.2f m, height %.2f m"
		% [weapon_id, p.get("combat"), cam.call("shoulder_side_now"), shipped[0], shipped[1]])

	var measure := func(tag: String) -> float:
		await _tick(90)                        # the boom lerps to its target at shoulderOffsetLerpSpeed
		var seen: int = await _count()
		await _shot(tag)
		for m in body_meshes: (m as MeshInstance3D).visible = false
		var all: int = await _count()
		for m in body_meshes: (m as MeshInstance3D).visible = true
		return float(seen) / float(maxi(all, 1))

	var right: float = await measure.call("right")
	print("RIGHT  shoulder  gun visible %.0f%%" % (right * 100.0))
	Input.action_press("shoulder")
	await _tick(2)
	Input.action_release("shoulder")
	await _tick(2)
	if int(cam.call("shoulder_side_now")) != -1:
		print("FAIL the shoulder key did not move the camera to the left")
		quit(1)
		return
	var best := [-1.0, 0.0, 0.0]
	for h in heights:
		for e in extras:
			combat.set("camera_left_shoulder_extra", e)
			combat.set("camera_left_height_extra", h)
			cam.call("on_set_combat_state", combat)
			var v: float = await measure.call("left_e%.2f_h%.2f" % [e, h])
			print("LEFT   extra sideways %.2f m  height %+.2f m  gun visible %.0f%%" % [e, h, v * 100.0])
			if v > best[0]:
				best = [v, e, h]
	combat.set("camera_left_shoulder_extra", shipped[0])
	combat.set("camera_left_height_extra", shipped[1])
	cam.call("on_set_combat_state", combat)
	var shipped_v: float = await measure.call("left_shipped")
	print("LEFT   SHIPPED (%.2f, %+.2f)  gun visible %.0f%%   best of sweep %.0f%% at (%.2f, %+.2f)"
		% [shipped[0], shipped[1], shipped_v * 100.0, best[0] * 100.0, best[1], best[2]])
	var ok := true
	if right < 0.5:
		print("FAIL the right-shoulder view hides most of the gun (%.0f%%)" % (right * 100.0)); ok = false
	if assert_left >= 0.0 and shipped_v < assert_left:
		print("FAIL the shipped left-shoulder view shows %.0f%% of the gun (want %.0f%%)" % [shipped_v * 100.0, assert_left * 100.0]); ok = false
	print("RESULT %s" % ("PASS" if ok else "FAIL"))
	quit(0 if ok else 1)
