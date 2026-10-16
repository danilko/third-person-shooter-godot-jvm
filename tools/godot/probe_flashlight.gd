extends SceneTree
## THE FLASHLIGHT (PLAN.md 3.2, character.Flashlight): one toggle, two mounts -- on the GUN with a firearm (the beam
## follows the weapon: walk sway, reload dip, recoil), from the BODY with fists / melee / throwables (CS 1.6), off with
## them under Left 4 Dead's rule (Flashlight.onMelee false). A real Player at night (a DayNight + a sun below the
## horizon) facing a wall 9 m ahead:
##
##   1. own   -- without the profile unlock the key does nothing; BOUGHT at a counter stocking "flashlight" (economy
##               gadgets: $40) it is owned -- the counter then prices it -1 (OWNED) and refuses a second sale -- and the
##               key turns it on;
##   2. gun   -- ASR1 aimed: the mount is "gun", the beam starts within 8 cm of the muzzle and points along the bore
##               (<= 2 deg), and its axis hits the wall; the local player's beam casts shadows;
##   3. lit   -- (rendered runs only, under xvfb-run) the wall where the axis hits is brighter with the light on than off;
##   4. reload-- through a reload the beam stays on the muzzle (<= 8 cm every frame) while the muzzle itself moves
##               (> 3 cm in the body's frame): it FOLLOWS the gun;
##   5. body  -- on the fists the mount is "body": the beam starts within 0.5 m of the chest bone and points at the aim
##               point (<= 10 deg); with onMelee false (L4D) it is dark, back on with true;
##   6. night -- the authority posts LIGHT_SEEN once a second, and a hostile AI 25 m away hears it at the player;
##   7. off   -- the key turns it off.
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_flashlight.gd [-- --control]
##   xvfb-run -a godot --fixed-fps 60 --path . --script tools/godot/probe_flashlight.gd       (adds case 3)
## --control: the flashlight is never switched on -- cases 2-6 fail. FL_SHOT=<path prefix> saves case 3's frames.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const AI := "res://src/main/resources/com/openworld/character/AICharacter.tscn"
const WEAPON_DIR := "res://src/main/resources/com/openworld/weapon/%s.tscn"
const DAYNIGHT := "res://src/main/java/com/openworld/world/DayNight.java"
const COUNTER := "res://src/main/java/com/openworld/item/ShopCounter.java"

var control := false
var fails := 0

func _check(label: String, ok: bool, detail: String = "") -> void:
	if not ok:
		fails += 1
	print("  %s  %-62s %s" % ["PASS" if ok else "FAIL", label, detail])

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _box(parent: Node, size: Vector3, at: Vector3) -> void:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	b.add_child(mi)
	b.position = at
	parent.add_child(b)

func _angle_deg(a: Vector3, b: Vector3) -> float:
	return rad_to_deg(a.normalized().angle_to(b.normalized()))

## The wall's brightness at `at` as the player's camera sees it (rendered runs only), the mean of a 5x5 patch.
func _brightness(at: Vector3) -> float:
	var vp := root.get_viewport()
	var cam := vp.get_camera_3d()
	if cam == null or cam.is_position_behind(at):
		return -1.0
	await RenderingServer.frame_post_draw
	var img := vp.get_texture().get_image()
	if OS.get_environment("FL_SHOT") != "":
		img.save_png(OS.get_environment("FL_SHOT") + "_%d.png" % Time.get_ticks_msec())
	# the camera projects into the viewport's own size, the picture is the window's: scale between them
	var px := cam.unproject_position(at) * Vector2(img.get_size()) / vp.get_visible_rect().size
	var sum := 0.0
	var n := 0
	for dx in range(-2, 3):
		for dy in range(-2, 3):
			var x := int(px.x) + dx * 2
			var y := int(px.y) + dy * 2
			if x >= 0 and y >= 0 and x < img.get_width() and y < img.get_height():
				sum += img.get_pixel(x, y).get_luminance()
				n += 1
	return sum / maxf(1, n)

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	var rendered := DisplayServer.get_name() != "headless"
	print("flashlight probe: %s, %s" % ["CONTROL (never switched on)" if control else "on", "rendered" if rendered else "headless"])
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	_box(world, Vector3(200, 1, 200), Vector3(0, -0.5, 0))
	_box(world, Vector3(20, 6, 0.4), Vector3(0, 3, -9))
	# NIGHT: a sun below the horizon (its -Z points up) and the DayNight that reads it; a dark sky for the render
	var sun := DirectionalLight3D.new()
	sun.name = "SunLight"
	sun.light_energy = 0.0
	sun.rotation = Vector3(deg_to_rad(90), 0, 0)
	world.add_child(sun)
	var dn: Node = load(DAYNIGHT).new()
	world.add_child(dn)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.01, 0.01, 0.02)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.03, 0.03, 0.04)
	world.add_child(env)
	await _tick(3)

	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(40)
	var gun: Node3D = (load(WEAPON_DIR % "ASR1") as PackedScene).instantiate() as Node3D
	world.add_child(gun)
	gun.global_position = p.global_position + Vector3(0, 0.3, 0)
	await _tick(30)
	var wc: Node = p.get_node_or_null("WeaponController")
	for slot in range(1, 6):
		if String(gun.get_parent().name).begins_with("Socket"):
			break
		wc.call("on_set_weapon", slot)
		await _tick(50)
	if not String(gun.get_parent().name).begins_with("Socket"):
		_check("ASR1 reaches the hand", false, "parent %s" % gun.get_parent().name)
		quit(1)
		return
	var muzzle: Node3D = gun.get_node("Muzzle")
	Input.action_press("aim")
	await _tick(60)
	_check("it is night (DayNight reads the sun below the horizon)", bool(dn.call("lights_wanted_now")))

	print("=== 1. own ===")
	p.call("forget_flashlight_now")
	p.call("toggle_flashlight_now")
	await _tick(2)
	_check("without the unlock the key does nothing", not bool(p.call("flashlight_on_now")))
	var shop: Node3D = load(COUNTER).new()
	shop.set("stock", "flashlight")
	world.add_child(shop)
	shop.global_position = p.global_position
	await _tick(2)
	var save: Node = root.get_node_or_null("SaveSystem")
	if save != null and int(save.call("profile_balance_now")) < 100:
		save.call("grant_profile_now", 100)      # the probe's profile (user://test under --script) may be spent
	var price := int(shop.call("price_for_now", p, "flashlight"))
	_check("a counter stocking it sells it (economy.json gadgets)", String(shop.call("stock_now")) == "flashlight" and price == 40,
			"stock '%s', $%d" % [shop.call("stock_now"), price])
	var before := int(save.call("profile_balance_now")) if save != null else -1
	_check("buying it puts the unlock in the profile", bool(shop.call("grant_to_now", p, "flashlight")),
			"balance %d -> %d" % [before, int(save.call("profile_balance_now")) if save != null else -1])
	_check("... then it is OWNED: no price, a second sale refused",
			int(shop.call("price_for_now", p, "flashlight")) == -1 and not bool(shop.call("grant_to_now", p, "flashlight")))
	shop.queue_free()
	if not control:
		p.call("toggle_flashlight_now")
	await _tick(10)
	_check("with it the key turns the light on", bool(p.call("flashlight_on_now")))
	var fl: Node = p.get_node_or_null("Flashlight")

	print("=== 2. gun ===")
	var mount := String(fl.call("mount_now")) if fl != null else "none"
	var o: Vector3 = fl.call("beam_origin_now") if fl != null else Vector3.ZERO
	var d: Vector3 = fl.call("beam_direction_now") if fl != null else Vector3.FORWARD
	var bore: Vector3 = -muzzle.global_basis.z
	_check("the mount is the gun", mount == "gun", mount)
	_check("the beam starts at the muzzle", o.distance_to(muzzle.global_position) <= 0.08, "%.3f m" % o.distance_to(muzzle.global_position))
	_check("... and points along the bore", _angle_deg(d, bore) <= 2.0, "%.2f deg" % _angle_deg(d, bore))
	var q := PhysicsRayQueryParameters3D.create(o, o + d * 30.0)
	var hit := world.get_world_3d().direct_space_state.intersect_ray(q)
	var on_wall: bool = not hit.is_empty() and absf(float(hit["position"].z) + 8.8) < 0.3
	_check("its axis hits the wall ahead", fl != null and bool(fl.call("beam_visible_now")) and on_wall,
			str(hit.get("position", "nothing")))
	_check("the local player's beam casts shadows", fl != null and bool(fl.call("beam_shadow_now")))

	print("=== 3. lit ===")
	if rendered and on_wall:
		var spot: Vector3 = hit["position"] + Vector3(0, 0, 0.05)
		var lit := await _brightness(spot)
		p.call("set_flashlight_now", false)
		await _tick(3)
		var dark := await _brightness(spot)
		p.call("set_flashlight_now", true)
		await _tick(3)
		_check("the wall is lit where the beam hits", lit >= 0.0 and lit - dark >= 0.10, "on %.3f, off %.3f" % [lit, dark])
	elif rendered:
		_check("the wall is lit where the beam hits", false, "the beam does not reach the wall")
	else:
		print("  ----  headless: no picture to measure (run under xvfb-run for case 3)")

	print("=== 4. reload ===")
	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	gun.set("magazine", 1)
	var start: Vector3 = mesh_root.global_transform.affine_inverse() * muzzle.global_position
	var worst := 0.0
	var travel := 0.0
	Input.action_press("reload")
	await _tick(2)
	Input.action_release("reload")
	for i in range(150):
		await process_frame
		if fl == null:
			break
		var oo: Vector3 = fl.call("beam_origin_now")
		worst = maxf(worst, oo.distance_to(muzzle.global_position))
		travel = maxf(travel, (mesh_root.global_transform.affine_inverse() * muzzle.global_position).distance_to(start))
	_check("through a reload the beam stays on the muzzle", fl != null and worst <= 0.08, "worst %.3f m" % worst)
	_check("... while the muzzle itself moves (it follows the gun)", travel > 0.03, "muzzle moved %.3f m" % travel)

	print("=== 5. body ===")
	wc.call("on_set_weapon", 0)
	await _tick(60)
	var sk: Skeleton3D = _find(p, "Skeleton3D") as Skeleton3D
	var chest: Vector3 = sk.global_transform * sk.get_bone_global_pose(sk.find_bone("spine_03")).origin
	mount = String(fl.call("mount_now")) if fl != null else "none"
	o = fl.call("beam_origin_now") if fl != null else Vector3.ZERO
	d = fl.call("beam_direction_now") if fl != null else Vector3.FORWARD
	var aim: Node3D = _find(p, "AimTarget") as Node3D
	_check("on the fists the mount is the body", mount == "body", mount)
	_check("... the beam starts at the chest", o.distance_to(chest) <= 0.5, "%.2f m" % o.distance_to(chest))
	_check("... aimed at the aim point", aim != null and _angle_deg(d, aim.global_position - o) <= 10.0,
			"%.1f deg" % (_angle_deg(d, aim.global_position - o) if aim != null else 999.0))
	if fl != null:
		fl.call("set_on_melee_now", false)
	await _tick(3)
	_check("Left 4 Dead's rule (onMelee false): dark on the fists", fl != null and not bool(fl.call("beam_visible_now")))
	if fl != null:
		fl.call("set_on_melee_now", true)
	await _tick(3)
	_check("... and back on with CS 1.6's", fl != null and bool(fl.call("beam_visible_now")))

	print("=== 6. night ===")
	var ai: Node3D = (load(AI) as PackedScene).instantiate() as Node3D
	world.add_child(ai)
	ai.global_position = Vector3(0, 1.0, 25)
	var info: Resource = ai.get("character_info")
	if info != null:
		info.set("faction", "enemy")
	await _tick(130)
	var posts := int(fl.call("seen_posts_now")) if fl != null else 0
	_check("the beam is posted as LIGHT_SEEN at night", posts >= 1, "%d posts" % posts)
	var heard: Vector3 = ai.call("hear_alarm_now")
	_check("a hostile AI 25 m away hears it at the player", heard.distance_to(p.global_position) < 2.0,
			"%s vs the player at %s" % [heard, p.global_position])

	print("=== 7. off ===")
	p.call("toggle_flashlight_now")
	await _tick(3)
	_check("the key turns it off", not bool(p.call("flashlight_on_now")) and (fl == null or not bool(fl.call("beam_visible_now"))))
	Input.action_release("aim")
	print("RESULT %s (%d failures)%s" % ["PASS" if fails == 0 else "FAIL", fails, "  (CONTROL)" if control else ""])
	quit(0 if fails == 0 else 1)
