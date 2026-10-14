extends SceneTree
## A SWIMMER GETS OUT OF THE SEA up a FishMarket landing stair (PLAN S13, 2026-10-14; docs/island-world.md "The fish
## market rebuilt for cars"): the built scene, not a replica.
##
##   godot --headless --path . --script tools/godot/probe_swim_exit.gd [-- --x=400|500]
##
## The piece is placed with its yard at y 1.5 (the sea at y 0) and turned +90 deg so the stair, which rises toward +x,
## rises toward -z: the probe's "forward". The swimmer starts 4 m off the stair's foot and holds forward for 15 s.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"
const MARKET := "res://src/main/resources/com/openworld/world/buildings/FishMarket.tscn"

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

func _initialize() -> void:
	var sx := 400.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--x="):
			sx = float(a.substr(4))
	var world := Node3D.new()
	root.add_child(world)
	await process_frame
	var m: Node3D = load(MARKET).instantiate()
	world.add_child(m)
	m.rotation = Vector3(0, PI / 2.0, 0)
	m.position = Vector3(0, 1.5, 0)
	var bed := StaticBody3D.new()
	var bcs := CollisionShape3D.new()
	var bb := BoxShape3D.new()
	bb.size = Vector3(400, 1, 400)
	bcs.shape = bb
	bed.add_child(bcs)
	world.add_child(bed)
	bed.position = Vector3(0, -7.5, 0)
	var water: Area3D = load("res://src/main/java/com/openworld/world/WaterVolume.java").new()
	water.collision_layer = 0
	water.collision_mask = 2
	var wcs := CollisionShape3D.new()
	var wbox := BoxShape3D.new()
	wbox.size = Vector3(400, 7, 400)
	wcs.shape = wbox
	water.add_child(wcs)
	world.add_child(water)
	water.position = Vector3(0, -3.5, 0)    # top at y 0
	# the stair: Godot x (sx - 6 .. sx), z 809.6 .. 811.6 about the piece's centre (450, 760) -> local x, z
	var lx := sx - 6.0 - 450.0 - 4.0       # 4 m off the foot, in the water
	var lz := 810.6 - 760.0
	var start := m.transform * Vector3(lx, -1.5 - 0.5, lz)
	var p: Node3D = load(PLAYER).instantiate()
	world.add_child(p)
	p.global_position = start
	await _tick(120)
	var s := p.global_position
	Input.action_press("forward")
	var best := -99.0
	for i in range(900):
		await physics_frame
		best = maxf(best, p.global_position.y)
	Input.action_release("forward")
	var e := p.global_position
	var ok := best >= 1.3
	print("[swim_market] stair x %.0f: start (%.2f %.2f %.2f) end (%.2f %.2f %.2f) highest %.2f -> %s"
		% [sx, s.x, s.y, s.z, e.x, e.y, e.z, best, "OUT" if ok else "STILL IN"])
	print("RESULT %s" % ("PASS" if ok else "FAIL"))
	quit(0 if ok else 1)
