extends SceneTree
## PLAN.md 0.2 EXIT LEAK: a shop clerk spawned and returned three times (the player walks in and out past
## DESPAWN_FAR) must leave nothing off-tree. Run with --verbose and grep "Leaked instance" at exit: none.
##
##   stdbuf -oL godot --headless --verbose --path . --script tools/godot/probe_clerk_leak.gd

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const SHOP := "res://src/main/resources/com/openworld/world/buildings/KonbiniS_Shop.tscn"

var fails := 0


func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1


func _tick(n: int) -> void:
	for i in n:
		await physics_frame


func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	current_scene = world
	var floor := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(600, 2, 600)
	cs.shape = sh
	floor.add_child(cs)
	floor.position = Vector3(0, -1, 0)
	world.add_child(floor)
	var chars := Node3D.new()
	chars.name = "Characters"
	world.add_child(chars)
	var shop: Node3D = (load(SHOP) as PackedScene).instantiate()
	world.add_child(shop)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate()
	p.position = Vector3(0, 0.2, 20)
	chars.add_child(p)
	await _tick(10)
	var spots := shop.find_children("*", "", true, false).filter(func(n): return n.has_method("brain_held_now"))
	_check(spots.size() > 0, "the shop has a clerk spot (%d)" % spots.size())
	if spots.is_empty():
		quit(1)
		return
	var spot: Node = spots[0]
	for round in 3:
		p.global_position = Vector3(0, 0.2, 20)
		await _tick(60)
		var here: bool = spot.call("clerk_now") != null
		p.global_position = Vector3(0, 0.2, 220)
		await _tick(60)
		_check(here and spot.call("clerk_now") == null and not bool(spot.call("brain_held_now")),
				"round %d: a clerk came and went, and no brain is left behind" % (round + 1))
	world.queue_free()
	await _tick(5)
	print("RESULT %s (%d failure(s))" % ["PASS" if fails == 0 else "FAIL", fails])
	quit(0 if fails == 0 else 1)
