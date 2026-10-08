extends SceneTree
## DYING IN A VEHICLE, THEN THE RESPAWN (PLAN.md 1i, user 2026-10-08: "the ui / other character state seem not
## resume"). A body that dies seated is a seated corpse; RespawnSystem used to free it without unseating it, so the
## car kept the dead player's PlayerController and camera (WASD still drove it) and the HUD never heard vehicleExited.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_die_seated.gd [-- --seat=driver|passenger] [--control]
##
## DebugWorld: the player is seated in the parked car, killed, respawned (hospitalised); then: the HUD is ON_FOOT, the
## camera on screen is the fresh Player's own, the car holds nobody and no PlayerController, and holding `forward`
## moves the fresh body. --control turns RespawnSystem.release_seat off (the defect) and fails.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"

var fails := 0

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _tick(n: int) -> void:
	for i in n:
		await physics_frame

func _find(n: Node, cls: String) -> Node:
	if n.get_script() != null and String(n.get_script().resource_path).ends_with("/" + cls + ".java"):
		return n
	for c in n.get_children():
		var f := _find(c, cls)
		if f != null:
			return f
	return null

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var control := "--control" in args
	var passenger := "--seat=passenger" in args
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	await _tick(120)
	var gm: Node = root.get_node("GameManager")
	var rs: Node = gm.get_node_or_null("RespawnSystem")
	var hud: Node = _find(root, "HUDManager")
	_check(rs != null and hud != null, "the respawn system and the HUD exist")
	if rs == null or hud == null:
		quit(1)
		return
	if control:
		rs.set("release_seat", false)
	var helper: Node = load("res://src/main/java/com/openworld/debug/VehicleProbeHelper.java").new()
	world.add_child(helper)
	var player: CharacterBody3D = world.get_node("Characters/Player")
	var car: Node3D = world.get_node_or_null("VehicleRoot")
	if car == null:
		car = _find(world, "Vehicle")
	_check(car != null, "a car to sit in (%s)" % (car.name if car != null else "none"))
	if passenger:
		helper.call("seat_passenger", car, player, 1)
	else:
		helper.call("seat_character", car, player)
	await _tick(30)
	_check(String(hud.call("situation_now")) != "ON_FOOT", "seated: the HUD is in a vehicle situation (%s)" % hud.call("situation_now"))
	helper.call("kill", player)
	for i in 60 * 12:
		await physics_frame
		if int(rs.call("respawns_now")) > 0:
			break
	await _tick(90)
	var fresh: Node3D = rs.call("respawned_player_now")
	_check(fresh != null and is_instance_valid(fresh), "a fresh Player")
	if fresh == null:
		print("RESULT FAIL (%d failures)" % (fails + 1))
		quit(1)
		return
	_check(String(hud.call("situation_now")) == "ON_FOOT", "after the respawn the HUD is on foot (%s)" % hud.call("situation_now"))
	var cam := root.get_viewport().get_camera_3d()
	_check(cam != null and fresh.is_ancestor_of(cam), "the camera on screen is the fresh Player's own (%s)" % (cam.get_path() if cam != null else "none"))
	var occ: Node = helper.call("occupant_of", car)
	_check(occ == null or not is_instance_valid(occ), "the car holds no driver")
	var ctrl := _find(car, "PlayerController")
	_check(ctrl == null, "the car carries no PlayerController")
	var p0 := fresh.global_position
	Input.action_press("forward")
	await _tick(90)
	Input.action_release("forward")
	var moved := Vector2(fresh.global_position.x - p0.x, fresh.global_position.z - p0.z).length()
	_check(moved > 1.0, "holding forward walks the fresh body (%.2f m)" % moved)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(1 if fails else 0)
