extends SceneTree
## THE POLICE STATION'S HELICOPTER CLIMBS (user 2026-10-15, keyboard: "can descend with ctrl, but not able to raise").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_helicopter_pad.gd [-- --bare]
##   (--bare: the same helicopter on a bare floor, no building -- the control, which climbs)
##   (--key: press the PHYSICAL keys (Space / Ctrl) through Input.parse_input_event, as a keyboard does, instead of
##    pressing the actions -- the whole input path, every _input / _unhandled_input on the way)
##
## PoliceStation.tscn on a floor; its MARK_vehicle_06 (ParkedVehicle, HLC1, faction police) spawns the helicopter on
## the pad; a real Player is seated as its pilot and holds the climb key (space = handbrake) for 4 s. Logged every
## 0.5 s: height, vertical speed, contacts and what it touches. PASS = it climbs > 10 m in 4 s.
## The real HUDManager is on the stand: taking the pilot's seat names the helicopter's keys ONCE a session (user
## 2026-10-15: "hard to spot" that Space climbs), as bound now -- a second seating shows nothing.

const STATION := "res://src/main/resources/com/openworld/world/buildings/PoliceStation.tscn"
const HELI := "res://src/main/resources/com/openworld/vehicle/HLC1.tscn"
const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const HUD := "res://src/main/resources/com/openworld/ui/HUDManager.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _log(h: RigidBody3D, label: String) -> void:
	var touching := []
	for b in h.get_colliding_bodies():
		touching.append("%s(%s)" % [b.name, b.get_parent().name if b.get_parent() else ""])
	print("  %s y %.2f  vy %+.2f  clear %.2f  sleeping %s  freeze %s  touching %s" % [label, h.global_position.y,
		h.linear_velocity.y, float(h.call("ground_clear_now")), h.sleeping, h.freeze, touching])


var use_keys := false


func _hold(action: String, keycode: int, down: bool) -> void:
	if not use_keys:
		if down: Input.action_press(action)
		else: Input.action_release(action)
		return
	var e := InputEventKey.new()
	e.physical_keycode = keycode
	e.keycode = keycode
	e.pressed = down
	Input.parse_input_event(e)


func _initialize() -> void:
	use_keys = "--key" in OS.get_cmdline_user_args()
	var bare := "--bare" in OS.get_cmdline_user_args()
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 1, 400)
	cs.shape = box
	floor_body.add_child(cs)
	floor_body.position = Vector3(0, -0.5, 0)
	world.add_child(floor_body)
	var cam := Camera3D.new()
	world.add_child(cam)
	cam.position = Vector3(0, 30, 60)
	var h: RigidBody3D = null
	if bare:
		h = (load(HELI) as PackedScene).instantiate()
		world.add_child(h)
		h.global_position = Vector3(-6, 9.5, 1.3)       # the pad's height, in the open
		var stand := StaticBody3D.new()
		var scs := CollisionShape3D.new()
		var sbox := BoxShape3D.new()
		sbox.size = Vector3(30, 1, 30)
		scs.shape = sbox
		stand.add_child(scs)
		stand.position = Vector3(-6, 7.5, 1.3)
		world.add_child(stand)
	else:
		var st: Node3D = (load(STATION) as PackedScene).instantiate()
		world.add_child(st)
		await _tick(30)
		for n in get_nodes_in_group("parked_vehicle"):
			if n is RigidBody3D and str(n.get("character_info").get("display_name")) == "HLC1":
				h = n
		if h == null:
			for n in get_nodes_in_group("parked_vehicle"):
				print("  parked: %s %s" % [n.name, n.get_script().resource_path if n.get_script() else ""])
	_check(h != null, "the helicopter is there (%s)" % ("bare stand" if bare else "PoliceStation MARK_vehicle_06"))
	if h == null:
		quit(1)
		return
	print("  script %s, mass %.0f, gravity_scale %.2f, linear_damp %.2f (%d)" % [h.get_script().resource_path, h.mass,
		h.gravity_scale, h.linear_damp, h.linear_damp_mode])
	await _tick(180)
	_log(h, "parked     ")
	var hud: Node = (load(HUD) as PackedScene).instantiate()
	world.add_child(hud)
	await _tick(3)
	var p: CharacterBody3D = (load(PLAYER) as PackedScene).instantiate()
	p.position = h.global_position + Vector3(8, 1, 0)
	world.add_child(p)
	p.get_node("Health").set("invulnerable", true)
	await _tick(30)
	var helper: Node = load(HELPER).new()
	world.add_child(helper)
	p.collision_layer = 0
	p.collision_mask = 0
	helper.call("seat_character", h, p)
	await _tick(30)
	_check(helper.call("occupant_of", h) == p, "the player is its pilot")
	_log(h, "seated     ")
	var hint := String(hud.call("helicopter_hint_now"))
	print("  hint: \"%s\"" % hint)
	_check(hint.contains("Space") and hint.contains("climb") and hint.contains("descend"),
		"the pilot's seat names the climb / descend keys")
	var y0 := h.global_position.y
	_hold("handbrake", KEY_SPACE, true)
	await _tick(2)
	print("  space down: handbrake %s jump %s" % [Input.is_action_pressed("handbrake"), Input.is_action_pressed("jump")])
	for i in 8:
		await _tick(30)
		_log(h, "climb %.1f s" % ((i + 1) * 0.5))
	_hold("handbrake", KEY_SPACE, false)
	var dy := h.global_position.y - y0
	_check(dy > 10.0, "holding the climb key (space = handbrake) climbs (%.1f m in 4 s)" % dy)
	await _tick(60)
	_hold("crouch", KEY_CTRL, true)
	for i in 4:
		await _tick(30)
		_log(h, "down  %.1f s" % ((i + 1) * 0.5))
	_hold("crouch", KEY_CTRL, false)
	helper.call("exit_driver", h)
	await _tick(30)
	helper.call("seat_character", h, p)
	await _tick(30)
	_check(helper.call("occupant_of", h) == p and int(hud.call("helicopter_hint_count_now")) == 1,
		"a second seating the same session shows no second hint (%d shown)" % hud.call("helicopter_hint_count_now"))
	print("probe_helicopter_pad: %s" % ("PASS" if fails == 0 else "FAIL (%d)" % fails))
	quit(0 if fails == 0 else 1)
