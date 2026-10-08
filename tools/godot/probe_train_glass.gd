extends SceneTree
## TRAIN WINDOWS BREAK LIKE A CAR'S (PLAN.md 1g g, user 2026-10-07): every EMU1 window is its own piece
## (world.TrainWindows splits the car's glass surface into islands) and a round obeys the car's glass rule
## (WeaponItem.throughGlass): a heavy round (>= 20) breaks the window and carries on into the car, a light one breaks it
## and stops there, and an open window lets everything through.
##
##   stdbuf -oL godot --headless --path . --script tools/godot/probe_train_glass.gd
##
## DebugWorld; the shots are WeaponItem.probe_shot (the real trace + glass rule, as the authority) from a Player
## holding an ASR1, fired at a window's own centre in the same frame the window is read.

const DEBUG := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const HELPER := "res://src/main/java/com/openworld/debug/VehicleProbeHelper.java"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _weapon(c: Node) -> Node:
	for n in c.find_children("*", "", true, false):
		if n.has_method("probe_shot"):
			return n
	return null


## [world centre, outward normal] of window `w` of `car`
func _window(car: Node3D, w: int) -> Array:
	var mi: MeshInstance3D = car.get_node("Model/Win%d" % w)
	var ab := mi.get_aabb()
	var c: Vector3 = mi.global_transform * ab.get_center()
	var side: float = signf((car.global_transform.affine_inverse() * c).x)
	return [c, car.global_transform.basis.x.normalized() * side]


func _initialize() -> void:
	var world: Node = (load(DEBUG) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	for i in 120:
		await physics_frame
	var tr: Node = root.get_node("TrainSystem")
	var helper: Node = (load(HELPER) as Script).new()
	root.add_child(helper)
	var player: CharacterBody3D = world.get_node("Characters/Player")
	player.get_node("Health").set("invulnerable", true)
	helper.call("give_weapon", player, "ASR1")
	for i in 30:
		await physics_frame
	var gun := _weapon(player)
	var car: Node3D = null
	for k in 600:
		car = tr.call("car_body_now", 0, 1)
		if car != null:
			break
		await physics_frame
	_check(car != null and gun != null, "a train car and an armed player exist")
	if car == null or gun == null:
		print("RESULT FAIL (%d failures)" % fails)
		quit(0)
		return
	var n := int(tr.call("window_count_now", 0))
	print("  car windows: %d" % n)
	_check(n >= 6, "each window of the car is its own piece (%d)" % n)
	var b0 := int(tr.call("broken_windows_now"))
	# a heavy round through window 0: it breaks and the round goes on into the car (past the window's own plane)
	var w0 := _window(car, 0)
	var r: String = gun.call("probe_shot", w0[0] + w0[1] * 4.0, -w0[1], 30.0)
	var d0 := float(r.split("|")[1]) if r.contains("|") else 99.0
	print("  heavy round: %s" % r)
	_check(int(tr.call("broken_windows_now")) == b0 + 1, "a heavy round breaks the window")
	_check(d0 > 4.3, "...and carries on into the car (%.2f m, the window is at 4.0)" % d0)
	# a light round at another window: it breaks it and stops in it
	var w1 := _window(car, n / 2)
	r = gun.call("probe_shot", w1[0] + w1[1] * 4.0, -w1[1], 10.0)
	var d1 := float(r.split("|")[1]) if r.contains("|") else 99.0
	print("  light round: %s" % r)
	_check(int(tr.call("broken_windows_now")) == b0 + 2, "a light round breaks the window too")
	_check(d1 < 4.3, "...but stops in it (%.2f m)" % d1)
	# the opening now lets a light round through (window state holds while the cars stand)
	w1 = _window(car, n / 2)
	r = gun.call("probe_shot", w1[0] + w1[1] * 4.0, -w1[1], 10.0)
	d1 = float(r.split("|")[1]) if r.contains("|") else 99.0
	print("  light round through the open window: %s" % r)
	_check(d1 > 4.3, "an open window lets a light round through (%.2f m)" % d1)
	print("RESULT %s (%d failures)" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0)
